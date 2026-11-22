# UnexpectedTypeException do constraint không hỗ trợ kiểu dữ liệu trong Spring Validation

## 1. Nhận diện lỗi: HV000030 không phải một lỗi nhập liệu thông thường

Khi chạy một API dùng `@Valid`, bạn có thể gặp stack trace dạng:

```text
jakarta.validation.UnexpectedTypeException:
HV000030: No validator could be found for constraint
'jakarta.validation.constraints.NotBlank'
validating type 'java.lang.Integer'.
Check configuration for 'quantity'
```

Đây là **mẫu thông báo của Hibernate Validator**, không phải stdout thực tế đã thu được từ một lần chạy trong bài. Mã `HV000030` là **mã log/exception của Hibernate Validator**, không phải mã HTTP hoặc chuẩn Jakarta bắt buộc các provider khác phải sử dụng.

Một đoạn code có thể gây lỗi này:

```java
public record CreateOrderRequest(
        @NotBlank Integer quantity) {
}
```

Code trên **biên dịch Java được** nhưng khai báo constraint sai kiểu dữ liệu: `@NotBlank` được thiết kế cho `CharSequence`, còn `Integer` không phải `CharSequence`.

Khi Bean Validation đánh giá constraint, provider tìm một `ConstraintValidator<NotBlank, T>` có thể xử lý kiểu được khai báo của field `quantity`. Nếu không có validator phù hợp, provider ném **`jakarta.validation.UnexpectedTypeException`**, thay vì trả một `ConstraintViolation` như trường hợp giá trị thật sự không đạt yêu cầu.

Cách sửa đúng:

```java
public record CreateOrderRequest(
        @NotNull @Min(1) Integer quantity) {
}
```

- `@NotNull`: quantity bắt buộc phải tồn tại.
- `@Min(1)`: giá trị số phải lớn hơn hoặc bằng 1.
- `Integer`: đúng kiểu dữ liệu để tính toán và so sánh numeric.
- Không gắn `@NotBlank` chỉ để diễn đạt “bắt buộc nhập số”.

**Bài thuộc nhóm Chẩn đoán** của module **Spring Framework — validation-data-binding**. Mục tiêu là phân biệt cấu hình constraint sai kiểu với input vi phạm constraint, hiểu cách Jakarta Validation chọn validator, và sửa triệt để trong DTO, collection, custom constraint và Spring MVC. Ví dụ dùng **Java 17+ / Spring Boot 3.4.5 / Spring MVC / Hibernate Validator 8**.

## 2. Bản chất của UnexpectedTypeException

### 2.1. Hệ thống đã có constraint nhưng không tìm được validator phù hợp

Jakarta Bean Validation định nghĩa một annotation constraint, ví dụ `@NotBlank`, sẽ gắn với một hoặc nhiều implementation của `ConstraintValidator<A, T>`.

- `A`: kiểu annotation constraint.
- `T`: kiểu giá trị mà implementation kiểm tra.
- Bean Validation provider lựa chọn validator dựa trên **kiểu khai báo của phần tử được gắn constraint**, có tính đến rules subtype, primitive/wrapper và value extraction khi phù hợp.
- **Không có validator tương thích:** ném `UnexpectedTypeException`.
- **Nhiều validator cùng phù hợp nhưng không có lựa chọn cụ thể nhất duy nhất:** cũng có thể ném `UnexpectedTypeException`.
- **Có một validator phù hợp:** chạy `isValid(...)` để trả `true` hoặc `false`.

Sơ đồ tư duy:

```text
Constraint được gắn lên field/parameter
                |
                v
Xác định declared type của phần tử được kiểm tra
                |
                v
Lấy các ConstraintValidator của annotation
                |
                v
Có một validator tương thích và cụ thể nhất?
           /                      \
         Không                      Có
          |                         |
          v                         v
UnexpectedTypeException       Gọi isValid(value)
                                  /       \
                               false       true
                                 |           |
                                 v           v
                          ConstraintViolation  hợp lệ
```

**Điểm quan trọng:** lỗi “không có validator cho kiểu dữ liệu” không có nghĩa giá trị của field **không hợp lệ**. Nó có nghĩa **mô tả cách kiểm tra field bị sai**.

### 2.2. Ngoại lệ nằm trong hệ phân cấp nào?

Trong Jakarta Validation 3.x:

```text
java.lang.RuntimeException
└── jakarta.validation.ValidationException
    └── jakarta.validation.ConstraintDeclarationException
        └── jakarta.validation.UnexpectedTypeException
```

`UnexpectedTypeException` không phải `ConstraintViolationException`. `ConstraintViolationException` thường biểu diễn một tập violations trong các môi trường gọi method/JPA hoặc khi ứng dụng chủ động ném exception; còn `UnexpectedTypeException` báo provider không thể chọn validator phù hợp.

Một lời gọi trực tiếp:

```java
Set<ConstraintViolation<CreateOrderRequest>> errors =
        validator.validate(new CreateOrderRequest(0));
```

Với DTO **đã sửa** dùng `@NotNull @Min(1)`, provider trả một tập có violation cho `quantity`. Với DTO **sai** dùng `@NotBlank Integer`, chính lời gọi `validate(...)` có thể ném exception trước khi trả tập violations.

Điều này giải thích vì sao handler Spring MVC có thể không vào nhánh `BindingResult.hasErrors()`: provider **không hoàn tất được việc validation** để chuyển thành danh sách field errors.

### 2.3. Không phải lỗi biên dịch Java

Java compiler kiểm tra annotation có được dùng ở vị trí cho phép theo `@Target`, ví dụ FIELD, METHOD, PARAMETER, TYPE_USE hoặc RECORD_COMPONENT, nhưng **không tự bảo đảm annotation phù hợp với type đã gắn** theo mọi rule của Bean Validation.

Ví dụ `@Size(min=1) Integer count` có thể biên dịch được vì `@Size` cho phép đặt trên field/record component; chỉ đến lúc provider chọn validator nó mới phát hiện `Integer` không có khái niệm size được validator chuẩn hỗ trợ.

Một số công cụ static analysis hoặc Hibernate Validator Annotation Processor có thể cảnh báo sớm, nhưng **không được mặc định compiler của mọi build đều báo lỗi trước runtime**.

## 3. Bảng chọn constraint theo kiểu dữ liệu

| Mục đích | Kiểu Java | Constraint thường phù hợp | Sai lầm dễ gây UnexpectedTypeException |
| --- | --- | --- | --- |
| Bắt buộc có tham chiếu | `Integer`, `Long`, `String`, object | `@NotNull` | Dùng `@NotBlank` trên `Integer` |
| Chuỗi không blank | `String` / `CharSequence` | `@NotBlank` | Dùng `@NotBlank` trên `List` |
| Collection/array/map không rỗng | `List`, `Set`, `Map`, array | `@NotEmpty` | Dùng `@NotBlank` trên collection |
| Độ dài chuỗi | `String` | `@Size(min=..., max=...)` | Dùng `@Size` trên `Integer` để kiểm tra “số chữ số” |
| Số phần tử collection | `List`, `Set`, `Map`, array | `@Size(min=..., max=...)` | Dùng `@Min` trên list |
| Giá trị số tối thiểu | `Integer`, `Long`, `BigDecimal`... | `@Min` / `@DecimalMin` | Dùng `@Size` trên số |
| Giá trị số dương | Numeric types | `@Positive` | Dùng `@NotBlank` trên số |
| Mẫu regex | `CharSequence` | `@Pattern` | Dùng `@Pattern` trên `Long` |
| Email được định dạng | `String` / `CharSequence` | `@Email`, thường thêm `@NotBlank` | Dùng `@Email` trên `Integer` |
| Giá trị ngày trong tương lai | `Instant`, `LocalDate`, các temporal types hỗ trợ | `@Future` / `@FutureOrPresent` | Dùng `@Future` trên chuỗi thời gian chưa chuyển kiểu |
| Giá trị ngày trong quá khứ | Temporal types được hỗ trợ | `@Past` / `@PastOrPresent` | Dùng `@Past` trên `String` |
| Validate bean lồng nhau | Domain/command object | `@Valid` trên association/element | Dùng `@NotBlank` trực tiếp trên bean |

**Phạm vi type có thể khác theo provider/phiên bản.** Ví dụ Hibernate Validator hỗ trợ `@Min` hoặc `@Positive` trên một số `CharSequence` chứa số như phần mở rộng, mặc dù bạn thường nên deserialize về một kiểu numeric trong DTO. Đừng đưa ra quy tắc “`@Min String` luôn gây UnexpectedTypeException” khi Hibernate Validator có thể hỗ trợ nó. Hãy xem danh sách **supported data types** trong tài liệu provider đang chạy.

### 3.1. @NotNull, @NotEmpty và @NotBlank không hoán đổi được

```java
// Đúng: Integer là tham chiếu cần có giá trị.
@NotNull
Integer quantity;

// Đúng: String cần có nội dung không chỉ whitespace.
@NotBlank
String customerName;

// Đúng: list phải có phần tử.
@NotEmpty
List<String> tags;

// Đúng: kiểm tra từng String element.
@NotEmpty
List<@NotBlank String> tags2;
```

Đây là các **field fragments**, không phải một class hoàn chỉnh. Các annotation có phạm vi:

- `@NotNull` không quan tâm chuỗi rỗng hay list rỗng; chỉ cấm null.
- `@NotEmpty` cấm null/empty đối với chuỗi, collection, map hoặc array được hỗ trợ.
- `@NotBlank` yêu cầu một `CharSequence` có ít nhất một ký tự không phải whitespace theo validator; không áp dụng cho collection như một đối tượng.
- `@NotEmpty List<@NotBlank String>` kết hợp **container size** và **element value** để mô tả đúng ý định.

Nếu `quantity` là primitive `int`, nó không thể nhận null; `@NotNull int quantity` không giúp phát hiện “client không gửi field” nếu binding tạo giá trị mặc định 0. Với input HTTP cần phân biệt thiếu giá trị và số 0, nên dùng `Integer` cùng `@NotNull` và constraint numeric, đồng thời hiểu hành vi Jackson/argument binder.

### 3.2. @Size trên số không kiểm tra số chữ số

Sai:

```java
@Size(min = 1, max = 3)
Integer code;
```

`@Size` đo “size” của CharSequence, Collection, Map hoặc array. Một `Integer` không có `length()`/`size()` theo loại dữ liệu mà `@Size` hỗ trợ.

Nếu nghiệp vụ yêu cầu **giá trị số từ 1 đến 999**, dùng:

```java
@NotNull
@Min(1)
@Max(999)
Integer code;
```

Nếu nghiệp vụ yêu cầu **đúng ba chữ số** và cho phép số 0 ở đầu như `"007"`, đó là **mã định danh bằng chuỗi**, không phải số học:

```java
@NotBlank
@Pattern(regexp = "[0-9]{3}")
String code;
```

Nếu nghiệp vụ yêu cầu số lượng chữ số thập phân của một giá trị số, cân nhắc `@Digits(integer=..., fraction=...)` theo semantics và kiểu numeric. Không máy móc thay `@Size` bằng `@Digits` khi business thực sự yêu cầu **range**.

### 3.3. @Future trên String không tự parse ISO timestamp

Sai:

```java
@Future
String departureAt;
```

Một String nhìn giống timestamp như `"2031-04-02T09:00:00Z"` **vẫn có declared type là String**. `@Future` tiêu chuẩn áp dụng trên temporal types được provider hỗ trợ, không tự coi String là Instant.

Đúng:

```java
@NotNull
@Future
Instant departureAt;
```

Khi API nhận JSON, Jackson cần deserialize JSON string thành `Instant` trước. Nếu timestamp sai cú pháp, lỗi có thể xảy ra ở **HTTP message conversion** và trở thành `HttpMessageNotReadableException`, chứ không phải `UnexpectedTypeException`.

### 3.4. @Pattern trên Long không tự stringify để match regex

Sai:

```java
@Pattern(regexp = "[0-9]{10}")
Long phoneNumber;
```

Nếu số điện thoại là identifier có số 0 đầu, dấu cộng, mã quốc gia và không dùng phép tính, hãy dùng `String`:

```java
@NotBlank
@Pattern(regexp = "\\+?[0-9]{8,15}")
String phoneNumber;
```

Một số tình huống có thể viết custom validator cho numeric type, nhưng đừng dùng `@Pattern` trên `Long` và mong Bean Validation tự gọi `toString()`.

## 4. Đọc thông báo HV000030 có hệ thống

Ví dụ minh họa:

```text
HV000030: No validator could be found for constraint
'jakarta.validation.constraints.Size'
validating type 'java.lang.Integer'.
Check configuration for 'maxAttempts'
```

Đọc theo ba thành phần:

1. **Constraint:** `jakarta.validation.constraints.Size` — annotation nào đang được đánh giá?
2. **Validated type:** `java.lang.Integer` — kiểu declared của field/element có phù hợp với annotation đó không?
3. **Property path:** `maxAttempts` — vị trí trong model/DTO tại thời điểm provider đang xử lý.

Checklist:

- Mở đúng Java class/record được nêu; xác định `maxAttempts` là Integer, Long, String, List hay kiểu khác.
- Kiểm tra annotation nằm ở **field**, **getter**, **record component**, **method parameter**, **return value** hay **container element**.
- Đọc tài liệu supported types của chính constraint.
- Kiểm tra class cha/interface hoặc nested DTO nếu annotation được thừa kế/cascade.
- Kiểm tra các custom validators được đăng ký qua `@Constraint(validatedBy=...)`, XML hoặc programmatic mappings.
- Sửa **mô hình constraint** để phù hợp semantics, không chỉ bắt exception cho qua.

**Không parse cứng câu log HV000030 để suy ra nguyên nhân cho mọi provider.** Mã và format thông báo là chi tiết Hibernate Validator; dựa vào exception type để phân loại, property/annotation/type qua stack trace và code review để sửa.

### 4.1. Khi nào lỗi phát sinh?

Không nhất thiết ngay khi Spring Boot khởi động. Jakarta Validation spec cho phép lỗi xuất hiện khi:

- Provider đánh giá một bean qua `Validator#validate(...)`.
- Đánh giá một property qua `validateProperty(...)` hoặc `validateValue(...)`.
- Validation của method/constructor parameters hoặc return value được chạy.
- Một bean lồng nhau được cascade validate.
- Provider xây metadata model cho một bean có declaration sai.

Do đó một API có thể khởi động bình thường, test happy path pass, nhưng **đến khi chạm vào DTO hoặc validation group cụ thể** mới ném `UnexpectedTypeException`. Điều này là lý do nên có test cho mọi nhóm/cấu trúc input đã khai báo.

### 4.2. Tại sao thử giá trị null không chứng minh được annotation đúng?

Constraint thường trả true cho null để `@NotNull` là điều kiện riêng, nhưng **một declaration không hỗ trợ kiểu có thể bị từ chối khi provider resolve validator ngay cả trước khi chạy isValid trên giá trị**. Không sử dụng việc “input null chưa gây lỗi” (nếu thấy ở một cấu hình) làm chứng cứ `@NotBlank Integer` là hợp lệ.

## 5. Cơ chế chọn ConstraintValidator theo declared type

### 5.1. Generic signature quyết định type được hỗ trợ

Một custom constraint có implementation:

```java
public final class StartsWithValidator
        implements ConstraintValidator<StartsWith, CharSequence> {

    @Override
    public boolean isValid(
            CharSequence value,
            ConstraintValidatorContext context) {
        // ...
        return true;
    }
}
```

Đây là **fragment**; code runnable của `@StartsWith` xuất hiện ở mục 8. Provider hiểu implementation này có khả năng validate **CharSequence và những subtype tương thích**, ví dụ `String`.

Nếu khai báo:

```java
@StartsWith("SKU-")
Integer sku;
```

provider không thể dùng `ConstraintValidator<StartsWith, CharSequence>` cho `Integer`. Nó không tự chuyển `Integer` thành `String` để phù hợp generic type; dùng sai annotation sẽ dẫn đến `UnexpectedTypeException`.

### 5.2. Provider chọn theo declared type, không phải runtime subtype ngẫu nhiên

Ví dụ một custom validator chỉ hỗ trợ `String`:

```java
class OnlyStringValidator
        implements ConstraintValidator<MyConstraint, String> {
    // ...
}
```

Đây là fragment minh họa chưa khai báo `MyConstraint`. Nếu field được khai báo là `CharSequence value`, dù runtime object là một `String`, chỉ có validator `String` chưa bảo đảm phù hợp cho **declared type CharSequence**. Quy tắc tương thích dựa trên generic target type của phần tử được đánh dấu, không tùy tiện cast runtime object cho vừa.

Điều này đặc biệt quan trọng khi refactor DTO từ `String` thành một interface/base type hoặc khi custom constraint có nhiều implementations.

### 5.3. “Không có validator” và “có quá nhiều validator” đều có thể gây UnexpectedTypeException

Jakarta spec quy định chọn validator phù hợp **cụ thể nhất**. Nếu:

- Không validator nào hỗ trợ target type ⇒ không thể validate.
- Có hai implementations đều hỗ trợ target type, nhưng kiểu hỗ trợ của chúng không phân cấp rõ và không có một implementation cụ thể nhất ⇒ không thể chọn duy nhất.

Ví dụ về mặt ý tưởng, một class implement đồng thời `Serializable` và một interface riêng; annotation custom có các validators cho hai interface không có quan hệ subtype với nhau. Khi cả hai cùng match, resolution có thể **mơ hồ**. Không khắc phục bằng cách tự đoán provider sẽ chọn validator theo thứ tự khai báo trong `validatedBy`; thứ tự không phải giải pháp cho ambiguity.

**Định hướng sửa:** định nghĩa tập validators không chồng lấn mơ hồ; dùng một validator hỗ trợ base type thật sự phù hợp hoặc thêm một implementation cụ thể nhất khi semantics cho phép. Có thể cần tách annotation nếu cùng tên constraint đang cố bao phủ những domain concepts không cùng ý nghĩa.

### 5.4. Không tự sửa bằng ép kiểu bên trong isValid()

Nếu provider không thể chọn validator, `isValid(...)` có thể **chưa bao giờ được gọi**. Viết code như:

```java
String text = String.valueOf(value);
```

bên trong một validator chỉ nhận `CharSequence` không làm nó tự hỗ trợ `Integer`. Bạn phải thiết kế validator generic type phù hợp với target hoặc đổi field/annotation.

## 6. Khác biệt giữa lỗi cấu hình, lỗi giá trị và lỗi chuyển kiểu

| Tình huống | Điểm xảy ra | Hành vi thường gặp |
| --- | --- | --- |
| `@NotBlank Integer quantity` | Jakarta constraint resolution | **UnexpectedTypeException** |
| `@Min(1) Integer quantity = 0` | `isValid(...)` trả false | **ConstraintViolation** / `FieldError` |
| `@NotNull Integer quantity = null` | `isValid(...)` trả false | **ConstraintViolation** / `FieldError` |
| Form `quantity=abc` vào `Integer` | Spring property conversion | Có thể thành `FieldError.isBindingFailure() == true` |
| JSON `{"quantity":{}}` vào `Integer` | Jackson HTTP message converter | Thường `HttpMessageNotReadableException` |
| Custom `ConstraintValidator#isValid()` ném bug exception | Validator runtime | Có thể bị bọc bởi `ValidationException` |
| Constraint annotation có metadata bất hợp lệ | Bean Validation definition | `ConstraintDefinitionException` |
| Cascaded validation/parameter declaration sai quy tắc | Bean Validation declaration | `ConstraintDeclarationException` hoặc subtype |
| Multiple matching validators mơ hồ | ConstraintValidator resolution | **UnexpectedTypeException** |

Ba đường cần phân biệt khi chẩn đoán REST API:

**A. Giá trị không đạt constraint:** trả violations ⇒ Spring MVC thường chuyển sang `BindingResult` hoặc `MethodArgumentNotValidException` ⇒ HTTP 400 theo contract thông thường.

**B. JSON/form chưa chuyển được sang DTO:** lỗi message conversion hoặc binding ⇒ xử lý theo nguồn lỗi tương ứng.

**C. Constraint được đặt sai kiểu:** provider không chạy được validation đúng cách ⇒ exception cấu hình/triển khai; **không nên tự chuyển thành lỗi người dùng 400** và che giấu bug server.

### 6.1. HTTP 500 khi constraint khai báo sai không có nghĩa request “nguy hiểm”

Một `@NotBlank Integer` đặt sai là **lỗi lập trình của server**. Một request hợp lệ như `{"quantity":2}` vẫn có thể làm validator ném lỗi. Nếu Spring MVC không có handler đặc biệt cho `UnexpectedTypeException`, lỗi chưa được xử lý có thể đi theo đường **5xx**.

Khi điều tra, xem server logs/stacks có kiểm soát, xác nhận annotation và sửa code. Nếu buộc phải có global fallback, chỉ trả response 5xx an toàn như `INTERNAL_VALIDATION_CONFIGURATION_ERROR` hoặc `INTERNAL_ERROR`, đồng thời alert và giữ trace chi tiết ở logs. **Không viết catch rồi trả 400 INPUT_INVALID** cho mọi UnexpectedTypeException.

### 6.2. BindingResult không thể tạo kết quả nếu provider không validate được

Trong controller:

```java
@PostMapping("/order")
public String submit(
        @Valid @ModelAttribute("form") OrderForm form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "form";
    }
    return "done";
}
```

Đây là fragment. Nếu `OrderForm` chứa `@NotBlank Integer quantity`, Spring có thể ném `UnexpectedTypeException` trong quá trình gọi provider, **trước khi handler được invoke**. Có `BindingResult` liền sau DTO là đúng cú pháp, nhưng không biến một invalid constraint declaration thành field violation.

**Chẩn đoán đúng:** nếu stack trace báo `UnexpectedTypeException`, tập trung vào annotation/type; không nhầm với lỗi đặt `BindingResult` sai thứ tự (đó là một lỗi khác trong MVC).

## 7. Các trường hợp lồng nhau và container element

### 7.1. @NotBlank đặt trên cả List là sai

Sai:

```java
public record SearchRequest(
        @NotBlank List<String> keywords) {
}
```

Mục tiêu “danh sách có phần tử” nên dùng `@NotEmpty`:

```java
public record SearchRequest(
        @NotEmpty List<String> keywords) {
}
```

Mục tiêu “danh sách có phần tử, và từng phần tử là chuỗi không blank” nên dùng **cả hai tầng**:

```java
public record SearchRequest(
        @NotEmpty List<@NotBlank String> keywords) {
}
```

`@NotEmpty` đánh giá container `List`; `@NotBlank` đánh giá từng `String` (được provider hỗ trợ thông qua container element constraints). Nếu viết `List<@NotBlank Integer>`, provider có thể ném `UnexpectedTypeException` khi validate element kiểu Integer.

### 7.2. Map key/value phải dùng constraint hợp với kiểu từng phía

Một DTO:

```java
public record SettingsRequest(
        @NotEmpty
        Map<@NotBlank String, @NotNull Integer> settings) {
}
```

Ý nghĩa:

- `@NotEmpty` kiểm tra Map không null/rỗng.
- `@NotBlank` kiểm tra **key String** không blank.
- `@NotNull` kiểm tra **value Integer** không null.

Đây là fragment cần import `java.util.Map` và Jakarta constraints. Nếu muốn value phải dương thì thêm `@Positive` hoặc `@Min(1)` trên `Integer`, **không** dùng `@NotBlank` cho value số.

### 7.3. Nested object: dùng @Valid để cascade, constraint cho từng field

Sai:

```java
public record Order(
        @NotBlank Address shippingAddress) {
}
```

`Address` là Java bean/domain object, không phải CharSequence. Đúng hơn:

```java
public record Address(
        @NotBlank String street) {
}

public record Order(
        @NotNull @Valid Address shippingAddress) {
}
```

Đây là fragment cần imports và các record trong package thích hợp. `@Valid` khiến provider đi vào `Address.street`, trong khi `@NotNull` yêu cầu `shippingAddress` phải tồn tại. Lưu ý `@Valid` không phải constraint tự cấm null; null reference thường bị bỏ qua trong cascade.

### 7.4. Optional và value extraction

Các kiểu bao như `Optional<String>` có cơ chế **value extraction** trong Jakarta Validation/Hibernate Validator. Constraint đặt ở container và constraint đặt trên type argument **không luôn tương đương**. Ví dụ:

```java
Optional<@NotBlank String> nickname;
```

Đây là fragment. Provider cần value extractor hỗ trợ `Optional` để áp dụng constraint lên phần tử. Với wrapper tùy biến thiếu extractor hoặc unwrapping mơ hồ, có thể gặp `ConstraintDeclarationException` về value extraction, không nhất thiết `HV000030`.

Không sửa mọi lỗi container bằng cách gắn thêm `@Valid` hoặc tự cast Optional thành String. Xác định **ràng buộc áp dụng cho container hay element**, extractor nào hiện diện, và declared element type.

### 7.5. Các constraint ở record components

Java record hỗ trợ Bean Validation annotations trên components và constructor-related declarations tùy `@Target` của annotation. Điều này không làm `@NotBlank Integer` hợp lệ; records vẫn trải qua cùng validator resolution.

Cần test cả record DTO mới hoặc những field vừa refactor từ String thành Integer/enum; **đổi kiểu mà quên đổi annotation** là nguyên nhân rất phổ biến của lỗi này.

## 8. Project Maven Java 17 hoàn chỉnh: sai, sửa và kiểm thử

Ta xây một project Spring Boot MVC nhỏ có:

1. DTO bị khai báo sai **chỉ được dùng trong unit test** để minh họa `UnexpectedTypeException`, tránh đưa endpoint lỗi ra production.
2. DTO đúng sử dụng `@NotBlank` trên String, `@NotNull @Min(1)` trên Integer, `@NotEmpty List<@NotBlank String>`.
3. Một custom constraint `@StartsWith` dùng `ConstraintValidator<StartsWith, CharSequence>`, cho thấy generic type matching.
4. REST endpoint `POST /items` nhận `@Valid @RequestBody ItemRequest`, trả 201 nếu hợp lệ, 400 có error codes nếu dữ liệu sai.
5. Unit tests chứng minh **sai kiểu => exception** và **đúng kiểu, sai giá trị => violation**.
6. `MockMvc` integration tests chứng minh MVC dùng provider và error handling đúng, bao gồm JSON không deserialize được.

### 8.1. Cấu trúc thư mục

```text
unexpected-type-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── UnexpectedTypeApplication.java
    │   ├── StartsWith.java
    │   ├── StartsWithValidator.java
    │   ├── ItemRequest.java
    │   ├── ItemController.java
    │   └── InputErrorAdvice.java
    └── test/java/demo/
        ├── ConstraintTypeTest.java
        └── ItemControllerTest.java
```

### 8.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>unexpected-type-demo</artifactId>
    <version>1.0.0</version>

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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-validation` cung cấp Hibernate Validator phù hợp với Spring Boot 3.4.x; không trộn API `javax.validation.*` cũ với `jakarta.validation.*` của Boot 3.x.

### 8.3. src/main/java/demo/UnexpectedTypeApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UnexpectedTypeApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                UnexpectedTypeApplication.class, args);
    }
}
```

### 8.4. src/main/java/demo/StartsWith.java

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Target({
        ElementType.FIELD,
        ElementType.METHOD,
        ElementType.PARAMETER,
        ElementType.RECORD_COMPONENT,
        ElementType.ANNOTATION_TYPE,
        ElementType.TYPE_USE
})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = StartsWithValidator.class)
public @interface StartsWith {

    String value();

    String message()
            default "must start with the configured prefix";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
```

Một custom constraint hợp lệ cần annotation metadata phù hợp:

- `@Target` quy định những vị trí có thể dùng annotation.
- `@Retention(RUNTIME)` để provider đọc được annotation khi validation.
- `@Constraint(validatedBy=...)` khai báo implementation(s).
- `message`, `groups` và `payload` tuân thủ yêu cầu của Jakarta constraint definition.
- `value()` là một attribute riêng chứa prefix cần kiểm tra.

`@Target` có `TYPE_USE` giúp áp dụng trong container elements như `List<@StartsWith("SKU-") String>`; kiểu element vẫn phải được validator hỗ trợ.

### 8.5. src/main/java/demo/StartsWithValidator.java

```java
package demo;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class StartsWithValidator
        implements ConstraintValidator<StartsWith, CharSequence> {

    private String expectedPrefix;

    @Override
    public void initialize(StartsWith annotation) {
        expectedPrefix = annotation.value();
    }

    @Override
    public boolean isValid(
            CharSequence value,
            ConstraintValidatorContext context) {

        // @NotNull được dùng riêng nếu field bắt buộc.
        if (value == null) {
            return true;
        }

        return value.toString()
                .startsWith(expectedPrefix);
    }
}
```

**Điểm cần nhớ:**

- Generic type `CharSequence` tương thích với field `String`.
- Nó không tương thích với field `Integer`; provider không tự gọi `toString()` trước bước chọn validator.
- Nếu business yêu cầu bắt buộc không rỗng, kết hợp thêm `@NotBlank`.
- `initialize(...)` nhận configuration cho từng annotation instance; `isValid(...)` phải thread-safe, không ghi mutable shared request state trong validator.
- Code không gọi external I/O, không phụ thuộc Spring DI; phù hợp làm ví dụ constraint thuần.

Nếu custom logic cần kiểm tra một enum, hãy viết một `ConstraintValidator<YourConstraint, YourEnum>` hoặc một constraint class-level phù hợp với model — đừng gắn một annotation dành cho String trực tiếp lên enum rồi hy vọng “provider hiểu ý”.

### 8.6. src/main/java/demo/ItemRequest.java

```java
package demo;

import java.util.List;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public record ItemRequest(

        @NotBlank
        @StartsWith("SKU-")
        String sku,

        @NotNull
        @Min(1)
        Integer quantity,

        @NotEmpty
        List<@NotBlank String> tags
) {
}
```

**Thiết kế annotation đúng type:**

- `sku` là String, nên `@NotBlank` và custom `@StartsWith` (CharSequence) đều hỗ trợ.
- `quantity` là Integer, nên `@NotNull` và `@Min(1)` hỗ trợ.
- `tags` là List, nên `@NotEmpty` áp vào collection.
- `@NotBlank` nằm **trên type argument String** để kiểm tra từng tag, không nằm trên List.

Từ JSON `{"sku":"SKU-1","quantity":2,"tags":["spring"]}`, Jackson có thể tạo record và Jakarta Validator đánh giá từng constraint. Trong demo, null SKU đồng thời được `@NotBlank` kiểm tra, còn custom validator tự chọn cho null là hợp lệ để tránh chồng trách nhiệm.

### 8.7. src/main/java/demo/ItemController.java

```java
package demo;

import java.util.Map;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ItemController {

    @PostMapping("/items")
    public ResponseEntity<Map<String, Object>> create(
            @Valid @RequestBody ItemRequest request) {

        // Chỉ chạy khi JSON deserialize được
        // và tất cả constraints của DTO hợp lệ.
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of(
                        "status", "accepted",
                        "sku", request.sku(),
                        "quantity", request.quantity(),
                        "tagCount", request.tags().size()
                ));
    }
}
```

Không khai báo direct method constraints trên handler parameter, chỉ có `@Valid`; theo Spring MVC 6.x, individual argument validation là trường hợp điển hình. Nếu DTO bị vi phạm constraint, thường có `MethodArgumentNotValidException`; nếu JSON không đọc được, converter ném `HttpMessageNotReadableException`.

**Đừng thêm một endpoint cố tình nhận `@NotBlank Integer` vào ứng dụng production.** Những declarations sai nằm trong unit test riêng để học và tránh tạo một lỗi 5xx không cần thiết cho người dùng thực.

### 8.8. src/main/java/demo/InputErrorAdvice.java

```java
package demo;

import java.util.List;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation
        .ResponseEntityExceptionHandler;

@RestControllerAdvice
public class InputErrorAdvice
        extends ResponseEntityExceptionHandler {

    public record ErrorBody(
            String code,
            List<String> fields) {
    }

    @Override
    protected ResponseEntity<Object>
            handleMethodArgumentNotValid(
                    MethodArgumentNotValidException ex,
                    HttpHeaders headers,
                    HttpStatusCode status,
                    WebRequest request) {

        List<String> fields = ex.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(FieldError::getField)
                .distinct()
                .sorted()
                .toList();

        return new ResponseEntity<>(
                new ErrorBody("INPUT_INVALID", fields),
                headers,
                status
        );
    }

    @Override
    protected ResponseEntity<Object>
            handleHttpMessageNotReadable(
                    HttpMessageNotReadableException ex,
                    HttpHeaders headers,
                    HttpStatusCode status,
                    WebRequest request) {

        return new ResponseEntity<>(
                new ErrorBody(
                        "UNREADABLE_BODY",
                        List.of()
                ),
                headers,
                status
        );
    }
}
```

Handler **chỉ map những lỗi request cụ thể**. Nó không có nhánh:

```java
@ExceptionHandler(UnexpectedTypeException.class)
public ResponseEntity<?> badRequest() {
    return ResponseEntity.badRequest().build();
}
```

Đây là **anti-pattern fragment**, không phải code cần đưa vào project. Một lỗi cấu hình `ConstraintValidator` không nên bị ngụy trang thành “client gửi dữ liệu invalid”. Nếu production có global fallback 5xx cho mọi exception, hãy vẫn log/monitor nguyên nhân và không xuất exception details cho caller.

### 8.9. src/test/java/demo/ConstraintTypeTest.java

```java
package demo;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.UnexpectedTypeException;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Future;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ConstraintTypeTest {

    private static ValidatorFactory factory;
    private static Validator validator;

    @BeforeAll
    static void openValidatorFactory() {
        factory = Validation.buildDefaultValidatorFactory();
        validator = factory.getValidator();
    }

    @AfterAll
    static void closeValidatorFactory() {
        if (factory != null) {
            factory.close();
        }
    }

    record BadNotBlank(@NotBlank Integer quantity) {
    }

    record BadSize(@Size(min = 1, max = 3) Integer digits) {
    }

    record BadPattern(
            @Pattern(regexp = "[0-9]+") Long reference) {
    }

    record BadFuture(@Future String startsAt) {
    }

    record BadCustom(@StartsWith("SKU-") Integer sku) {
    }

    record CorrectQuantity(
            @NotNull @Min(1) Integer quantity) {
    }

    record Line(@NotBlank String name) {
    }

    record Shipment(
            @NotEmpty List<@Valid Line> lines) {
    }

    private <T> Set<String> invalidFields(T value) {
        return validator.validate(value)
                .stream()
                .map(v -> v.getPropertyPath().toString())
                .collect(Collectors.toSet());
    }

    @Test
    void notBlankIntegerThrowsUnexpectedType() {
        assertThrows(UnexpectedTypeException.class,
                () -> validator.validate(new BadNotBlank(2)));
    }

    @Test
    void sizeIntegerThrowsUnexpectedType() {
        assertThrows(UnexpectedTypeException.class,
                () -> validator.validate(new BadSize(12)));
    }

    @Test
    void patternLongThrowsUnexpectedType() {
        assertThrows(UnexpectedTypeException.class,
                () -> validator.validate(new BadPattern(123L)));
    }

    @Test
    void futureStringThrowsUnexpectedType() {
        assertThrows(UnexpectedTypeException.class,
                () -> validator.validate(
                        new BadFuture("2031-01-01")));
    }

    @Test
    void customStringConstraintOnIntegerThrows() {
        assertThrows(UnexpectedTypeException.class,
                () -> validator.validate(new BadCustom(42)));
    }

    @Test
    void correctNumericConstraintsReturnViolation() {
        assertEquals(
                Set.of("quantity"),
                invalidFields(new CorrectQuantity(0))
        );
    }

    @Test
    void correctNumericConstraintsAcceptPositiveValue() {
        assertTrue(invalidFields(
                new CorrectQuantity(3)).isEmpty());
    }

    @Test
    void validDtoProducesNoViolations() {
        ItemRequest input = new ItemRequest(
                "SKU-123", 2, List.of("spring", "mvc")
        );
        assertTrue(validator.validate(input).isEmpty());
    }

    @Test
    void customConstraintReturnsViolationNotException() {
        ItemRequest input = new ItemRequest(
                "ABC-123", 2, List.of("spring")
        );
        assertEquals(
                Set.of("sku"),
                invalidFields(input)
        );
    }

    @Test
    void containerElementConstraintReportsBadTag() {
        ItemRequest input = new ItemRequest(
                "SKU-123", 2, List.of("")
        );

        assertFalse(validator.validate(input).isEmpty());
        assertTrue(invalidFields(input).stream()
                .anyMatch(path -> path.contains("tags")));
    }

    @Test
    void validCascadeTraversesNestedObject() {
        Shipment shipment = new Shipment(
                List.of(new Line(""))
        );

        assertTrue(invalidFields(shipment).stream()
                .anyMatch(path -> path.contains("name")));
    }
}
```

**Mười một unit tests** kiểm tra rõ hai loại kết quả:

- **5 tests cố ý cấu hình sai**: `@NotBlank Integer`, `@Size Integer`, `@Pattern Long`, `@Future String`, và custom `@StartsWith Integer` phải ném `UnexpectedTypeException`.
- **6 tests cấu hình đúng**: kiểm tra numeric violations, numeric value hợp lệ, DTO hợp lệ, custom `isValid=false` trả violation, container element invalid và cascaded nested object.

Các tests dùng trực tiếp Jakarta `Validator`, không phụ thuộc HTTP conversion. Chúng **không assert chuỗi HV000030** để tránh khóa test vào nội dung log message của một phiên bản provider. Assertion quan trọng là **exception type** đối với declaration sai và **violation set** đối với value sai.

### 8.10. src/test/java/demo/ItemControllerTest.java

```java
package demo;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet
        .AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders
        .post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .status;

@SpringBootTest
@AutoConfigureMockMvc
class ItemControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validItemReturnsCreated() throws Exception {
        mvc.perform(post("/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "sku":"SKU-123",
                              "quantity":2,
                              "tags":["spring","mvc"]
                            }
                            """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status")
                        .value("accepted"))
                .andExpect(jsonPath("$.tagCount")
                        .value(2));
    }

    @Test
    void zeroQuantityIsInputViolation() throws Exception {
        mvc.perform(post("/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "sku":"SKU-123",
                              "quantity":0,
                              "tags":["spring"]
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INPUT_INVALID"))
                .andExpect(jsonPath("$.fields",
                        hasItem("quantity")));
    }

    @Test
    void missingQuantityViolatesNotNull() throws Exception {
        mvc.perform(post("/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "sku":"SKU-123",
                              "tags":["spring"]
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields",
                        hasItem("quantity")));
    }

    @Test
    void emptyTagsViolatesNotEmpty() throws Exception {
        mvc.perform(post("/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "sku":"SKU-123",
                              "quantity":1,
                              "tags":[]
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields",
                        hasItem("tags")));
    }

    @Test
    void blankTagViolatesElementNotBlank() throws Exception {
        mvc.perform(post("/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "sku":"SKU-123",
                              "quantity":1,
                              "tags":[""]
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields",
                        hasItem(containsString("tags"))));
    }

    @Test
    void wrongPrefixIsValidationFailure() throws Exception {
        mvc.perform(post("/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "sku":"ABC-123",
                              "quantity":1,
                              "tags":["spring"]
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INPUT_INVALID"))
                .andExpect(jsonPath("$.fields",
                        hasItem("sku")));
    }

    @Test
    void blankSkuFailsNotBlank() throws Exception {
        mvc.perform(post("/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "sku":"",
                              "quantity":1,
                              "tags":["spring"]
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields",
                        hasItem("sku")));
    }

    @Test
    void incompatibleJsonTypeIsConverterError()
            throws Exception {
        mvc.perform(post("/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "sku":"SKU-123",
                              "quantity":{"nested":true},
                              "tags":["spring"]
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNREADABLE_BODY"));
    }

    @Test
    void malformedJsonIsConverterError()
            throws Exception {
        mvc.perform(post("/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"sku\":,}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNREADABLE_BODY"));
    }
}
```

**Chín MockMvc integration tests** chứng minh:

- Correct DTO đi qua Spring MVC validation thành công.
- Integer quantity bằng 0 là **normal validation violation** ⇒ HTTP 400 `INPUT_INVALID`, không phải `UnexpectedTypeException`.
- Missing quantity bị `@NotNull` chặn.
- Empty List bị `@NotEmpty` chặn.
- Element String blank bên trong List bị `@NotBlank` chặn.
- Custom constraint phù hợp type mà trả false tạo normal violation.
- String blank gây normal violation.
- JSON shape không thể chuyển sang Integer gây `UNREADABLE_BODY`.
- JSON sai cú pháp cũng là converter failure, không phải bean constraint mismatch.

Hai nhóm tests chạy với cùng project, nhưng lỗi sai kiểu chỉ nằm trong unit tests. Không tạo endpoint lỗi cố ý trong main code.

### 8.11. Chạy project

Tại thư mục `unexpected-type-demo` trên máy có **JDK 17+ và Maven**:

```bash
mvn -q clean test
```

**Kỳ vọng:** 11 unit tests + 9 MockMvc tests = **20 tests** thành công, Maven trả exit code 0 trong môi trường tương thích. Đây là kỳ vọng từ mã mẫu, **không phải build đã thực thi hoặc stdout đã được quan sát tại đây**. Nếu một API/provider có khác biệt, kiểm tra bản Spring Boot/Hibernate Validator và error log thực tế.

Khởi chạy server:

```bash
mvn spring-boot:run
```

Request hợp lệ:

```bash
curl -i -X POST 'http://localhost:8080/items' \
  -H 'Content-Type: application/json' \
  --data '{
    "sku":"SKU-123",
    "quantity":2,
    "tags":["spring","mvc"]
  }'
```

Response theo contract demo:

```json
{
  "status": "accepted",
  "sku": "SKU-123",
  "quantity": 2,
  "tagCount": 2
}
```

Nếu gửi `quantity=0` (dưới dạng JSON number):

```bash
curl -i -X POST 'http://localhost:8080/items' \
  -H 'Content-Type: application/json' \
  --data '{
    "sku":"SKU-123",
    "quantity":0,
    "tags":["spring"]
  }'
```

Response dự kiến HTTP 400:

```json
{
  "code": "INPUT_INVALID",
  "fields": ["quantity"]
}
```

Nếu gửi `{"quantity":{"nested":true}}` thay vì JSON number, Jackson không thể tạo Integer từ object này với cấu hình thông thường, response dự kiến HTTP 400 mang `UNREADABLE_BODY`. Trong khi đó, một lỗi `@NotBlank Integer` cố ý **không** xuất hiện qua endpoint này vì DTO chính đã sửa.

## 9. Khi lỗi xuất hiện trong Spring MVC, điều tra như thế nào?

### 9.1. Bắt đầu từ exception class, không từ HTTP status

Ví dụ request có thể không vào controller và trả 500. Hãy kiểm tra stack trace ở server:

- Có `jakarta.validation.UnexpectedTypeException` không?
- Có `HV000030` không?
- Annotation nào và validated type nào được nhắc đến?
- Vị trí property/parameter nào?
- DTO thuộc `@ModelAttribute`, `@RequestBody` hay `@RequestPart`?
- Có nested List/Map element constraints hoặc custom validator không?

Khi exception là `UnexpectedTypeException`, đừng vội thay `@RestControllerAdvice` để che lỗi, thay đổi `BindingResult` hoặc disable `@Valid`. Sửa annotation/type mismatch trước.

### 9.2. Đường đi của một request JSON

```text
HTTP JSON
  |
  v
HttpMessageConverter / Jackson
  |  lỗi syntax/type -> HttpMessageNotReadableException
  v
ItemRequest được tạo thành công
  |
  v
Spring MVC gọi Jakarta Validator
  |
  +-- annotation/type mismatch
  |       -> UnexpectedTypeException (cấu hình server)
  |
  +-- đúng validator, value invalid
  |       -> ConstraintViolation(s)
  |       -> BindingResult / MethodArgumentNotValidException
  |
  +-- đúng validator, value valid
          -> controller được gọi
```

Nếu một DTO có nhiều constraints, lỗi có thể xuất hiện ở constraint đầu tiên mà provider đánh giá sai. Không giả định thứ tự duyệt constraints ổn định; sửa **tất cả** declarations sai, không chỉ cái đầu tiên trong stack.

### 9.3. Form-urlencoded có thêm một lớp conversion

Với `@ModelAttribute`, WebDataBinder chuyển request parameters sang các Java properties:

- `quantity=abc` cho `Integer`: thường là binding conversion failure, có thể thành `FieldError.isBindingFailure()`.
- `quantity=0` cho `@Min(1) Integer`: convert thành công rồi constraint trả false.
- `quantity=2` cho `@NotBlank Integer`: convert thành công nhưng validator selection thất bại.
- `quantity=` cho `Integer`: có thể được chuyển thành null; `@NotNull` chặn, tùy binder configuration.

Vì vậy phải xác định **thứ gì thất bại trước**: message conversion, type conversion, validator resolution hay `isValid`.

### 9.4. @RequestBody và BindingResult không tự khắc phục lỗi sai annotation

Một controller có:

```java
@PostMapping("/bad")
public String handle(
        @Valid @RequestBody BadRequest body,
        BindingResult errors) {

    return errors.hasErrors() ? "bad" : "ok";
}
```

Đây là fragment, `BadRequest` chưa được định nghĩa. Spring MVC yêu cầu result ngay sau validated argument nếu muốn xử lý local errors. Nhưng kể cả vị trí đúng, một `@NotBlank Integer` trong BadRequest vẫn có thể ném `UnexpectedTypeException` khi Bean Validation không chọn được validator.

Local `BindingResult` dùng để nhận **binding/constraint errors đã được xác định**, không phải để biến invalid validator declaration thành field error.

## 10. Custom constraints: các lỗi triển khai cần tránh

### 10.1. @Constraint khai báo thiếu validator cho target type

Ví dụ bạn định nghĩa một annotation `@ValidSku` chỉ có:

```java
class SkuValidator
        implements ConstraintValidator<ValidSku, String> {
    // ...
}
```

Đây là fragment, không phải implementation chạy được. Nếu gắn `@ValidSku` lên một field `SkuId` (value object) trong lúc class `SkuId` không phải subtype String, provider sẽ không thể dùng validator này.

Cách sửa có cơ sở:

- Chuyển DTO field về String nếu external representation thật là String và service chuyển thành value object.
- Hoặc implement `ConstraintValidator<ValidSku, SkuId>` riêng, có semantics rõ cho value object.
- Hoặc đặt constraint lên nested property `SkuId.value` nếu domain model/validation cascade phù hợp.
- Không dùng một `ConstraintValidator<ValidSku, Object>` chỉ để chấp nhận mọi kiểu rồi runtime `instanceof` phức tạp, trừ khi ý nghĩa constraint thực sự là generic trên mọi object.

### 10.2. Xung đột do nhiều validators

Nếu một annotation custom khai báo validators cho những interfaces chồng lấn, provider có thể không chọn được một implementation cụ thể nhất. Cần thiết kế generic type hierarchy rõ hoặc tách constraint names.

Không dựa vào **thứ tự liệt kê** classes trong `validatedBy` để giải quyết ambiguous resolution.

### 10.3. Constraint định nghĩa sai có thể gây exception khác

Nếu thiếu `message`/`groups`/`payload` đúng chuẩn trong annotation constraint, provider có thể ném **`ConstraintDefinitionException`**, không nhất thiết `UnexpectedTypeException`. Nếu rule cho executable methods hoặc value extractor sai, có thể gặp `ConstraintDeclarationException`. Phân biệt exception subclass trước khi sửa.

### 10.4. Không đổi kiểu generic rồi kỳ vọng Spring tự cast

Nếu validator là `ConstraintValidator<A, CharSequence>`, Spring không tự chuyển `Long` thành String cho Jakarta Validator sau khi request đã bind vào Long. Bean Validation nhìn thấy type của element. Nếu muốn kiểm tra regex, dùng String representation trong DTO hoặc custom validation hợp kiểu.

### 10.5. Không dùng state mutable theo request trong singleton validator

ConstraintValidators có thể được provider cache và dùng đồng thời; `isValid(...)` cần thread-safe. Tránh lưu giá trị request hiện tại vào field rồi dùng cho request tiếp theo. Configuration từ annotation `initialize(...)` có thể được giữ như immutable value, như prefix trong `StartsWithValidator`, nhưng đừng sửa nó trong `isValid(...)`.

## 11. Các ví dụ refactor hay làm phát sinh HV000030

### 11.1. Refactor String sang Integer nhưng giữ @NotBlank

Trước:

```java
@NotBlank
String attemptCount;
```

Sau refactor sai:

```java
@NotBlank
Integer attemptCount;
```

Sau refactor đúng:

```java
@NotNull
@Min(1)
Integer attemptCount;
```

Test migration nên gọi Bean Validator trên DTO thật, không chỉ test Jackson deserialize. Một JSON đúng type có thể decode thành công rồi mới lỗi ở validation phase.

### 11.2. Refactor String time sang Instant nhưng giữ @Pattern

Trước:

```java
@NotBlank
@Pattern(regexp = "\\d{4}-\\d{2}-\\d{2}")
String date;
```

Sau refactor sai:

```java
@Pattern(regexp = "\\d{4}-\\d{2}-\\d{2}")
LocalDate date;
```

Đúng hơn:

```java
@NotNull
@Future
LocalDate date;
```

Đây là fragment cho một business yêu cầu ngày tương lai; nếu chỉ yêu cầu ngày bất kỳ thì bỏ `@Future`. Validation “chuỗi có format yyyy-MM-dd” trở nên không còn phù hợp khi field đã là `LocalDate`; Jackson đảm nhận parsing, Jakarta Validation kiểm tra business/date constraints sau decode.

### 11.3. Thay list bằng count nhưng giữ @Size

Trước:

```java
@Size(max = 10)
List<String> items;
```

Sau sai:

```java
@Size(max = 10)
Integer itemCount;
```

Sau đúng nếu business yêu cầu 0–10:

```java
@NotNull
@Min(0)
@Max(10)
Integer itemCount;
```

### 11.4. Đưa @NotBlank từ element lên container

Trước đúng:

```java
List<@NotBlank String> names;
```

Sau sai:

```java
@NotBlank
List<String> names;
```

Sau đúng nếu muốn cả danh sách không rỗng và phần tử không blank:

```java
@NotEmpty
List<@NotBlank String> names;
```

### 11.5. Thay String code bằng enum nhưng giữ @Pattern

Trước:

```java
@Pattern(regexp = "NEW|PAID|CANCELLED")
String state;
```

Sau refactor:

```java
@Pattern(regexp = "NEW|PAID|CANCELLED")
OrderState state;
```

Nếu `OrderState` là enum, annotation `@Pattern` trên enum không có validator chuẩn phù hợp. Nên dùng `@NotNull OrderState state`; Jackson/mapper kiểm soát chuỗi nào chuyển thành enum hợp lệ. Nếu business chỉ cho một subset transitions, kiểm tra rule ở service/domain, không giả định regex trên enum.

## 12. Phân biệt @NotBlank sai kiểu với các lỗi dữ liệu khác

### 12.1. Lỗi giá trị: constraint hợp kiểu nhưng dữ liệu không đạt

```java
@NotBlank
String name = "";
```

Validator `NotBlank` có thể chạy trên String và trả false; framework tạo violation bình thường. Đây mới là trường hợp người dùng cần sửa input.

### 12.2. Lỗi constraint: annotation không hỗ trợ declared type

```java
@NotBlank
Integer name = 12;
```

Không có validator tương thích; dù 12 là “có giá trị”, annotation không có định nghĩa kiểm tra Integer. Đây là bug cấu hình phía server.

### 12.3. Lỗi conversion: request không thể tạo Java value

```json
{"quantity":{"unexpected":true}}
```

Đối với DTO có `Integer quantity`, Jackson thường không thể deserialize JSON object thành Integer. Lỗi này xảy ra **trước Jakarta Validation** và có thể được map thành `UNREADABLE_BODY`. Không phải `HV000030`.

### 12.4. Lỗi dependency namespace: javax vs jakarta

Spring Boot 3.x / Spring Framework 6 dùng **`jakarta.validation.*`**. Nếu dự án còn import `javax.validation.*` từ thế hệ cũ, một số annotations/provider integration có thể không hoạt động hoặc dependency graph có xung đột. Đây là vấn đề migration/classpath riêng; không mặc định nó tạo cùng `UnexpectedTypeException` với `@NotBlank Integer`.

Kiểm tra:

```bash
mvn dependency:tree
```

Đảm bảo các dependency validation của project thuộc cùng thế hệ Jakarta/Boot. Không thêm một validator provider cũ vào cùng classpath như giải pháp “khắc phục HV000030”.

### 12.5. Lỗi annotation processing và code generation

Nếu dùng Lombok, MapStruct, Jackson records, Kotlin hoặc code generator, hãy kiểm tra **kiểu sau khi generated code/compiled class xuất hiện** và vị trí annotation được giữ. Một annotation `@NotBlank` có thể đã được copy từ String property sang numeric field. Test trên compiled application giúp phát hiện mismatch không lộ từ snippet gốc.

## 13. Kiểm thử phòng ngừa: không chỉ test happy path

Một smoke test chỉ gọi endpoint với input hợp lệ có thể bắt mismatch nếu nó thực sự validate DTO, nhưng các constraints thuộc **validation groups khác**, nested branches hoặc object types khác có thể chưa được chạy.

Nên có ít nhất:

1. Unit test cho từng input DTO qua Jakarta `Validator#validate(...)`.
2. Test cho từng `@Validated(Group.class)` nếu dùng nhiều groups.
3. Test container elements, nested objects và subtype/custom constraints.
4. Test MockMvc cho form-urlencoded và JSON request nếu ứng dụng hỗ trợ cả hai.
5. Negative test giá trị sai *nhưng đúng Java type* để xác nhận nhận **field violations**, không ném exception cấu hình.
6. Test một valid payload đi đến service; đừng chỉ test lỗi.
7. Static analysis/annotation processor khi có, nhưng vẫn giữ runtime tests vì mapping/provider thực sự có thể khác.

### 13.1. Test mutation nhỏ nhưng có giá trị cao

Một test như:

```java
assertThrows(UnexpectedTypeException.class,
        () -> validator.validate(new BadNotBlank(2)));
```

là bằng chứng tối giản cho lỗi **declaration/type**. Sau khi sửa, thay bằng:

```java
Set<ConstraintViolation<CorrectQuantity>> violations =
        validator.validate(new CorrectQuantity(0));

assertEquals(1, violations.size());
```

Đây là **fragment** dựa trên nested records của test ở phần 8. Bài học là kiểm tra kết quả thay đổi từ **exception** thành **normal violation**; không chỉ xem HTTP status từ 500 thành 400 rồi bỏ qua loại lỗi.

### 13.2. Đừng assert nguyên stack trace/message

Thông báo Hibernate Validator bao gồm constraint class, type, property path; vị trí dấu nháy, tên internal classes, line numbers và bản dịch có thể đổi theo phiên bản. Unit tests nên assert `UnexpectedTypeException.class` hoặc `ConstraintViolation<?>` với property path và constraint annotation phù hợp.

Nếu observability cần tìm `HV000030`, có thể dựa trên mã provider trong logs như một **tín hiệu vận hành**, nhưng không dùng nó làm public API error code hoặc tính năng bắt buộc cross-provider.

## 14. Chẩn đoán theo decision tree

```text
Có lỗi khi validate một DTO?
        |
        v
Exception là UnexpectedTypeException?
        |
        +-- Có
        |    |
        |    v
        |  Xác định constraint + declared type + path
        |    |
        |    v
        |  Có ConstraintValidator phù hợp không?
        |    |
        |    +-- Không -> đổi annotation/type hoặc bổ sung validator
        |    |
        |    +-- Có nhiều match -> sửa ambiguous validators
        |    |
        |    v
        |  Rerun unit validation + MockMvc tests
        |
        +-- Không
             |
             v
        Có ConstraintViolation/MethodArgumentNotValidException?
             |
             +-- Có -> xử lý invalid input theo API contract
             |
             +-- Không
                  |
                  v
        HttpMessageNotReadableException?
             |
             +-- Có -> kiểm tra JSON shape/conversion
             |
             +-- Không -> kiểm tra các exception/phase khác
```

**Lưu ý:** `ConstraintDeclarationException` có nhiều nguyên nhân; một issue về value extractor hoặc method constraints có thể không phải `UnexpectedTypeException`. Thực hiện chẩn đoán theo **class exception + stack trace + annotation metadata**, không dựa vào một từ “validation” trong log.

## 15. Những lỗi thường gặp khi khắc phục HV000030

### 15.1. Bỏ @Valid để endpoint không còn lỗi

Điều này **tắt validation path** thay vì sửa constraint sai. Các field khác có thể không còn được kiểm tra. Cách sửa là dùng annotation phù hợp với declared type.

### 15.2. Catch UnexpectedTypeException rồi trả 400 cho mọi request

Đây là lỗi lập trình server, không phải “người dùng nhập số 2 sai”. Chỉ trả input error khi có **ConstraintViolation/FieldError** hợp lệ hoặc conversion error thật. Mismatch nên gây alert và được sửa.

### 15.3. Thêm @NotNull và giữ nguyên @NotBlank Integer

```java
@NotNull
@NotBlank
Integer quantity;
```

Thêm `@NotNull` không vô hiệu hóa `@NotBlank` sai kiểu. Provider vẫn cần resolve validator cho `NotBlank`. **Phải bỏ annotation không tương thích**.

### 15.4. Thay @Size(Integer) thành @Digits mà không hiểu business rule

`@Digits` kiểm tra số chữ số nguyên/thập phân theo cách định nghĩa của annotation. Nó không đồng nghĩa numeric range; nếu business muốn 1 ≤ quantity ≤ 999, dùng `@Min(1) @Max(999)`.

### 15.5. Dùng @NotBlank trên enum hoặc nested bean

`@NotBlank` dành cho CharSequence. Enum/bean thường dùng `@NotNull`; với bean lồng nhau thêm `@Valid` và constraints cho từng field. Không tự động stringify enum để lấy một “tên hợp lệ”.

### 15.6. Chỉ sửa một field khi có nhiều mismatch

Provider có thể dừng ở annotation đầu tiên không thể resolve. Sau khi sửa, một lỗi thứ hai ở DTO khác có thể lộ ra. Chạy tests trên các DTO và validation groups liên quan.

### 15.7. Tự viết validator generic Object để che mọi mismatch

Một validator `ConstraintValidator<A, Object>` nhận mọi kiểu có thể làm lỗi biến mất nhưng khiến semantics mơ hồ. Chỉ dùng khi constraint được định nghĩa thực sự áp dụng cho mọi Object; thông thường **type-specific validators** dễ bảo trì hơn.

### 15.8. Nhầm supported types theo một blog hoặc provider khác

Những extension của Hibernate Validator có thể không portable sang provider khác. Kiểm tra đúng phiên bản Jakarta spec/provider; với constraint phổ biến hãy ưu tiên kiểu được chuẩn hỗ trợ.

### 15.9. Tin rằng Java compiler bắt được mọi lỗi annotation/type

`@Target(FIELD)` không giới hạn field phải là String hay Integer. Compiler cho phép nhiều declaration không hợp lệ về mặt Bean Validation. Cần runtime validation tests và static tooling hỗ trợ.

### 15.10. Nhầm @Pattern String với @Future Instant

Nếu đầu vào là ngày giờ, dùng proper temporal type rồi `@Future`; nếu đầu vào là mã định danh text, dùng `@Pattern`. Không dùng regex để thay thế kiểm tra time semantics hoặc ngược lại.

### 15.11. Đổi BindingResult sang Errors

`BindingResult` và `Errors` cùng biểu diễn validation result trong Spring; đổi kiểu parameter không bổ sung ConstraintValidator cho Integer. Nếu root exception là `UnexpectedTypeException`, cần sửa DTO/custom validator.

### 15.12. Lỗi chỉ xuất hiện trong JPA flush

Hibernate ORM có thể tích hợp Bean Validation ở pre-persist/update. Một entity có annotation sai type có thể gây exception khi persist/flush, không chỉ khi REST controller gọi `@Valid`. Đặt constraints đúng trên entity và dùng database constraints để bảo vệ final state; đừng giả định sửa controller DTO đã giải quyết mọi entity-level declarations.

### 15.13. Đưa nội dung exception raw lên REST response

Stack trace có thể chứa internal class, package, property path hoặc dữ liệu không nên công bố. Trả response server error ngắn gọn; log an toàn và sửa bug qua deployment, không để client phụ thuộc message `HV000030`.

## 16. Checklist review trước khi deploy

### Constraint/type matching

- [ ] `@NotBlank` chỉ áp lên CharSequence hoặc element String tương thích.
- [ ] `@Size` áp lên CharSequence/Collection/Map/array phù hợp.
- [ ] Numeric range dùng `@Min/@Max`, `@Positive` hoặc variants thích hợp.
- [ ] `@Pattern` áp lên CharSequence, không lên numeric/enum/object.
- [ ] Temporal constraints áp lên temporal type được hỗ trợ, không lên raw String.
- [ ] `@NotNull` được khai báo nếu field reference bắt buộc.
- [ ] Collections có constraint container và element đúng tầng.
- [ ] Nested object dùng `@Valid` để cascade, không dùng string constraints trên bean.
- [ ] Custom constraint có `ConstraintValidator<A,T>` tương thích declared type.
- [ ] Không có nhiều custom validators mơ hồ cho cùng target type.
- [ ] Annotation `message/groups/payload` hợp chuẩn Jakarta.
- [ ] Có provider/namespace nhất quán với Spring Boot 3.x.

### Controller và exception handling

- [ ] Phân biệt `UnexpectedTypeException` với `ConstraintViolationException`.
- [ ] Không tự map invalid constraint declaration thành client HTTP 400.
- [ ] Xử lý `MethodArgumentNotValidException` cho DTO constraint violations.
- [ ] Xử lý `HttpMessageNotReadableException` cho JSON decoding errors.
- [ ] Nếu dùng method-level constraints, hiểu `HandlerMethodValidationException` trong Spring MVC 6.1+.
- [ ] Giữ `BindingResult` ngay sau object nếu muốn xử lý local field errors.
- [ ] Không xuất raw validation/exception details hoặc rejected values lên API.

### Kiểm thử

- [ ] Có direct Jakarta Validator tests cho DTO/record.
- [ ] Có negative test xác nhận invalid value tạo violation, không exception cấu hình.
- [ ] Có tests cho container elements và nested cascade.
- [ ] Có tests cho custom validator types.
- [ ] Có MockMvc integration tests trên DTO đã sửa.
- [ ] Không phụ thuộc nội dung message HV000030 theo exact string.
- [ ] Có regression tests sau refactor String → Integer/enum/LocalDate.
- [ ] Có kiểm thử những validation groups, routes hoặc methods không thường xuyên chạy.
- [ ] CI phát hiện mismatch trước khi người dùng gặp HTTP 500.

## 17. Kết luận

**`UnexpectedTypeException` là lỗi không thể lựa chọn validator phù hợp cho declared type**, điển hình với `@NotBlank Integer` hoặc `@Size Integer`. Nó khác với constraint thông thường thất bại: **provider không thể đánh giá đúng annotation**, chứ không chỉ phát hiện giá trị sai.

Để sửa:

1. Xác định **annotation + declared Java type + property path** từ exception.
2. Chọn constraint đúng semantics và đúng type, ví dụ `@NotNull @Min(1) Integer` thay `@NotBlank Integer`.
3. Nếu là custom constraint, sửa `ConstraintValidator<A,T>`, `validatedBy` hoặc thiết kế type hierarchy để có đúng một validator phù hợp nhất.
4. Với nested List/Map, đặt annotation đúng **container hoặc type argument**, dùng `@Valid` để cascade.
5. Phân biệt lỗi configuration với `MethodArgumentNotValidException`, JSON conversion error và normal field violations.
6. Bảo vệ bằng unit tests Jakarta Validator và MockMvc, không che bug bằng cách tắt `@Valid` hoặc trả 400 cho mọi exception.

Khi sửa đúng, cùng một request có giá trị `quantity=0` sẽ tạo **validation violation có thể trả HTTP 400**, còn `quantity=2` sẽ được chấp nhận; không còn tình trạng **HTTP 500 do annotation khai báo sai kiểu**.

## Tài liệu tham khảo

- [Jakarta Bean Validation 3.0 — Specification, ConstraintValidator resolution algorithm và UnexpectedTypeException](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Jakarta Validation — UnexpectedTypeException API](https://javadoc.io/doc/jakarta.validation/jakarta.validation-api/3.0.2/jakarta/validation/UnexpectedTypeException.html)
- [Hibernate Validator 8 — Reference Guide: supported constraints and supported data types](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/)
- [Hibernate Validator — Annotation Processor Reference](https://docs.jboss.org/hibernate/stable/validator/reference/en-US/html_single/#validator-annotation-processor)
- [Spring Framework — Core Validation](https://docs.spring.io/spring-framework/reference/core/validation/validator.html)
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — MVC @RequestBody and Bean Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — MethodArgumentNotValidException API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/bind/MethodArgumentNotValidException.html)
- [Spring Framework — ResponseEntityExceptionHandler API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
- [Spring Boot 3.4 — Validation](https://docs.spring.io/spring-boot/3.4/reference/io/validation.html)
