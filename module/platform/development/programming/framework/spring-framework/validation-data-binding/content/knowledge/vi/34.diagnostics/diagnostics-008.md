# Chẩn đoán GroupSequence sai hoặc nhóm mong muốn không được kích hoạt trong Spring Framework

## Mục tiêu học tập

Một lỗi rất khó phát hiện khi sử dụng Jakarta Bean Validation với Spring MVC là: **constraint được khai báo đúng, object đã gắn `@Valid`, nhưng kiểm thử hoặc request thực tế lại không chạy nhóm mong muốn**. Ngược lại, đôi khi nhóm đã được yêu cầu nhưng **cố ý không chạy** vì một nhóm đứng trước nó trong `@GroupSequence` đã sinh lỗi. Nếu chỉ nhìn HTTP 400 hoặc số lượng violations, ta dễ chẩn đoán nhầm thành “Hibernate Validator bỏ qua annotation”.

Bài thuộc nhóm **Chẩn đoán** của module **Spring Framework — validation-data-binding**, đi sâu vào:

- Nhóm `jakarta.validation.groups.Default` và nhóm tùy chỉnh như `BusinessChecks`, `FinalChecks`.
- `@Valid` của Jakarta và `@Validated` của Spring: khi nào nhóm được chọn và ai thực sự gọi validation.
- `@GroupSequence` trên **interface** để tạo chuỗi theo thứ tự, phân biệt với `@GroupSequence` trên **class** để **định nghĩa lại Default** của chính class đó.
- Quy tắc **dừng tại nhóm đầu tiên có ít nhất một violation**, so với việc truyền nhiều nhóm cùng lúc nhưng **không đặt thứ tự**.
- Nhóm kế thừa; lỗi sequence vòng lặp; `GroupDefinitionException`.
- Cascade `@Valid` sang object lồng/List; `@ConvertGroup`; lý do nhóm Default tùy biến của object cha **không tự truyền** sang object con.
- `@GroupSequenceProvider` của Hibernate Validator cho default sequence động (phần mở rộng không thuộc chuẩn Jakarta).
- Kiểm tra `ConstraintViolation.getConstraintDescriptor().getGroups()`, property path, metadata và `BindingResult` trong các lớp test.
- Cách dựng ví dụ Java 17+, Spring Boot 3.5.7, MockMvc + JUnit để biết nhóm nào chạy, nhóm nào bị skip, và vì sao.

**Kết luận định hướng:** Trước khi sửa annotation, phải biết **nhóm thực sự được yêu cầu** và **nhóm nào đã làm sequence dừng**. Một annotation tồn tại trên model **không có nghĩa** nó luôn được kiểm tra trong mọi lần gọi validator.

## 1. Các khái niệm nền tảng

### 1.1. Mỗi constraint thuộc một hoặc nhiều nhóm

Ví dụ:

~~~java
public interface BusinessChecks {}
public interface FinalChecks {}

public class Registration {
    @NotBlank
    private String email;

    @NotBlank(groups = BusinessChecks.class)
    private String companyCode;

    @AssertTrue(groups = FinalChecks.class)
    private boolean acceptedTerms;
}
~~~

Đoạn trên là **snippet giải thích**, chưa phải file chạy độc lập. Các imports liên quan thuộc `jakarta.validation.constraints`.

Ba rule không có cùng nhóm:

| Constraint | Nhóm khai báo | Khi nào được kiểm tra? |
| --- | --- | --- |
| `@NotBlank email` | `Default` (ngầm định) | Khi gọi validation với Default |
| `@NotBlank(groups=BusinessChecks.class) companyCode` | `BusinessChecks` | Khi yêu cầu BusinessChecks hoặc một nhóm/sequence bao gồm nó |
| `@AssertTrue(groups=FinalChecks.class) acceptedTerms` | `FinalChecks` | Khi yêu cầu FinalChecks hoặc một sequence bao gồm nó |

Với Jakarta `Validator`:

~~~java
validator.validate(registration);
validator.validate(registration, Default.class);
~~~

Hai lệnh thường tương đương về việc yêu cầu **nhóm Default**. Chúng không tự kích hoạt BusinessChecks hoặc FinalChecks, trừ khi có **default group sequence redefinition** trên class, hoặc quan hệ group sequence/group inheritance thích hợp.

### 1.2. @Valid không phải lệnh “chạy tất cả nhóm”

`jakarta.validation.Valid` thường được dùng trên controller argument hoặc property lồng:

~~~java
@PostMapping("/register")
ResponseEntity<?> register(
        @Valid @RequestBody Registration input) {
    // ...
}
~~~

`@Valid` cho Spring biết object cần được validate; khi không có group hint, thường áp dụng `Default`. Nó **không** có tham số `groups` và không có nghĩa “mọi constraint trong toàn bộ các nhóm đều được đánh giá”.

Để yêu cầu một nhóm trong Spring MVC, dùng Spring `@Validated`:

~~~java
@PostMapping("/register/final")
ResponseEntity<?> finalSubmit(
        @Validated(FinalChecks.class)
        @RequestBody Registration input) {
    // ...
}
~~~

`@Validated` thuộc `org.springframework.validation.annotation.Validated`, khác package với Jakarta `@Valid`. `@Validated(FinalChecks.class)` thường chỉ kích hoạt FinalChecks (cộng các nhóm được kế thừa/sequence nếu có), **không tự thêm Default**.

### 1.3. Một tập nhiều nhóm không tương đương một sequence

Ví dụ:

~~~java
validator.validate(
        registration,
        Default.class,
        BusinessChecks.class,
        FinalChecks.class);
~~~

Lời gọi yêu cầu **cả ba nhóm**, nhưng Jakarta Bean Validation **không bảo đảm thứ tự** giữa những nhóm được yêu cầu độc lập. Một constraint Default thất bại không phải lý do chuẩn để bỏ qua tất cả constraints của BusinessChecks/FinalChecks trong lời gọi không sequenced.

Nếu cần **thứ tự và short-circuit**, phải dùng `@GroupSequence` một cách đúng đắn.

## 2. @GroupSequence trên interface: thứ tự và dừng sớm

Tạo một nhóm có ý nghĩa “thực hiện kiểm tra theo quy trình”:

~~~java
import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

@GroupSequence({
        Default.class,
        BusinessChecks.class,
        FinalChecks.class
})
public interface OrderedChecks {
}
~~~

Đây là một **group sequence interface**. Nó được sử dụng khi caller yêu cầu **OrderedChecks**:

~~~java
Set<ConstraintViolation<Registration>> violations =
        validator.validate(
                registration,
                OrderedChecks.class);
~~~

Trong Spring MVC:

~~~java
@PostMapping("/register/ordered")
ResponseEntity<?> registerOrdered(
        @Validated(OrderedChecks.class)
        @RequestBody Registration input) {
    // ...
}
~~~

**Quan trọng:** Chỉ vì interface `OrderedChecks` có `@GroupSequence` **không làm mọi lệnh `validator.validate(registration)` tự chuyển sang OrderedChecks**. Caller phải yêu cầu group sequence này, trừ trường hợp dùng nó qua một định nghĩa hợp lệ khác.

### 2.1. Quy tắc short-circuit

Các nhóm được đánh giá theo thứ tự:

~~~text
Default
   |
   +-- có violation? ---- CÓ ---> DỪNG
   |
   +-- KHÔNG
         |
         v
    BusinessChecks
         |
         +-- có violation? --- CÓ ---> DỪNG
         |
         +-- KHÔNG
               |
               v
          FinalChecks
               |
               v
          Kết quả
~~~

Giả sử cả email, companyCode và acceptedTerms đều sai:

- `Default` bắt lỗi email.
- `BusinessChecks` **không chạy** vì Default chưa đạt.
- `FinalChecks` **không chạy** vì sequence đã dừng.
- Tập violations chỉ chứa những lỗi thu được ở Default.

Đó là **hành vi đúng của @GroupSequence**. Nó không có nghĩa rằng constraints thuộc hai nhóm sau đã bị khai báo sai.

Khi Default đã đạt nhưng BusinessChecks thất bại, chỉ Default và BusinessChecks được xử lý; FinalChecks bị bỏ qua. Khi cả hai bước trước đạt thì FinalChecks mới được kiểm tra.

### 2.2. Không hiểu short-circuit thành “chỉ một lỗi”

Trong một nhóm, provider có thể ghi nhận **nhiều violations**: email rỗng, tuổi quá nhỏ, city rỗng... Khi một nhóm tạo ít nhất một violation, sequence dừng **sau nhóm đó**. Mặc định đây không phải cơ chế “gặp lỗi đầu tiên ở một field rồi dừng”; số lượng và thứ tự các violations trong cùng nhóm không được dùng để suy ra thứ tự khai báo fields.

Hibernate Validator có chế độ **fail-fast** mở rộng, nhưng đó là một cấu hình khác và có thể làm test số lượng violations thay đổi. Đừng trộn fail-fast provider-specific với chuẩn short-circuit theo nhóm.

### 2.3. Không gán constraint trực tiếp cho sequence interface

Không viết:

~~~java
@NotBlank(groups = OrderedChecks.class)
private String companyCode;
~~~

khi `OrderedChecks` là interface được đánh dấu `@GroupSequence`. Theo quy tắc khai báo của Bean Validation, group sequence interface không nên có superinterfaces và không nên dùng trực tiếp trong `groups` của constraints. Hãy gán constraint vào **BusinessChecks** hoặc **FinalChecks**, và chỉ dùng `OrderedChecks` để **yêu cầu chuỗi**.

### 2.4. Kế thừa nhóm không phải tự động chạy Default

Ví dụ:

~~~java
public interface AdvancedBusinessChecks
        extends BusinessChecks {
}
~~~

Khi validate `AdvancedBusinessChecks.class`, constraints thuộc `BusinessChecks` được đưa vào nhờ group inheritance. Nhưng điều đó **không mặc nhiên yêu cầu Default** trừ khi quan hệ nhóm/sequence thực sự bao gồm Default.

Group inheritance phục vụ tái sử dụng chính sách nhóm. Không lạm dụng chuỗi kế thừa dài khiến developer khó biết constraint thuộc nhóm nào; đặt tên mô tả use case.

## 3. @GroupSequence đặt trên class: định nghĩa lại Default

Một trường hợp khác với `@GroupSequence` trên interface là đặt annotation **trực tiếp trên bean class**:

~~~java
import jakarta.validation.GroupSequence;
import jakarta.validation.constraints.NotBlank;

@GroupSequence({
        StrictProfile.class,
        ComplianceChecks.class
})
public record StrictProfile(
        @NotBlank String displayName,
        @NotBlank(groups = ComplianceChecks.class)
        String identityNumber) {
}
~~~

Khi `validator.validate(new StrictProfile(...))` yêu cầu Default, sequence được định nghĩa lại cho **chính class StrictProfile**:

1. Kiểm các constraints Default nằm trên StrictProfile (được biểu diễn trong sequence bằng `StrictProfile.class`).
2. Chỉ khi nhóm đầu đạt, kiểm `ComplianceChecks`.
3. Nếu nhóm đầu sai, ComplianceChecks bị skip.

### 3.1. Vì sao phải chứa class thay vì Default.class?

Đây là lỗi chẩn đoán thường gặp:

~~~java
@GroupSequence({
        Default.class,
        ComplianceChecks.class
})
public class BrokenProfile {
    @NotBlank
    private String displayName;
}
~~~

Khi `@GroupSequence` **định nghĩa lại Default trên class**, sequence **phải chứa chính class đó** (ở đây `BrokenProfile.class`), không được thay bằng `Default.class`. Một sequence không hợp lệ có thể ném `jakarta.validation.GroupDefinitionException` khi metadata được tra hoặc khi validate.

Sửa lại:

~~~java
@GroupSequence({
        BrokenProfile.class,
        ComplianceChecks.class
})
public class BrokenProfile {
    @NotBlank
    private String displayName;
}
~~~

Chú ý: với **interface** `OrderedChecks` ở mục 2, `Default.class` trong sequence là **đúng**; còn với **class-level Default redefinition** trên `BrokenProfile`, nó là **sai**. Không thể chỉ đọc một dòng `@GroupSequence` mà bỏ qua **annotation đang nằm trên interface hay class**.

### 3.2. Default mới chỉ áp dụng cục bộ cho class

Khi StrictProfile định nghĩa lại Default, điều đó **không tự thay nhóm truyền xuống đối tượng liên kết** qua `@Valid` thành toàn bộ sequence của StrictProfile. Quy tắc Default redefinition là **local to that class**. Các đối tượng con được cascade theo group propagation của Jakarta Validation; nếu cần đổi nhóm khi cascade, sử dụng `@ConvertGroup` trên association.

Vì vậy, “@GroupSequence trên cha đã có ComplianceChecks nhưng lỗi ComplianceChecks của object con không xuất hiện” có thể là **hành vi đúng**, không phải provider bỏ qua nested validation.

### 3.3. Tránh chuỗi phụ thuộc vòng lặp

Các sequences không được có dependency cycle trái quy tắc chuẩn, kể cả cycle gián tiếp qua group inheritance. Ví dụ mô hình sai:

~~~text
SequenceA → SequenceB → SequenceA
~~~

Khi metadata được xử lý hoặc nhóm đó được yêu cầu, provider có thể ném `GroupDefinitionException`. Đừng cố sửa bằng cách gọi validator nhiều lần không kiểm soát; cần sửa sơ đồ nhóm thành DAG/thứ tự hợp lệ và đặt test metadata.

## 4. @ConvertGroup và đối tượng lồng

### 4.1. @Valid chỉ cascade theo nhóm đang áp dụng

Giả sử:

~~~java
public record Address(
        @NotBlank String city,
        @NotBlank(groups = BusinessChecks.class)
        String zipCode,
        @NotBlank(groups = AddressReview.class)
        String districtCode) {
}
~~~

Root:

~~~java
public record RegistrationRequest(
        @NotBlank String email,
        @Valid Address address) {
}
~~~

Nếu chỉ gọi:

~~~java
validator.validate(registrationRequest);
~~~

thì Default được áp dụng cho root và, theo cascade, Default được truyền vào `Address`. Constraint `city` được kiểm tra, nhưng `zipCode` (BusinessChecks) và `districtCode` (AddressReview) **không tự chạy**. Nếu caller yêu cầu `OrderedChecks`, provider sẽ đánh giá từng nhóm tương ứng, bao gồm các nested constraints trong nhóm đó, theo quy tắc propagation và sequence.

### 4.2. @ConvertGroup dùng khi cần đổi nhóm ở cạnh cascade

~~~java
public record ConvertedRequest(
        @NotBlank String label,
        @NotNull
        @Valid
        @ConvertGroup(
                from = Default.class,
                to = AddressReview.class)
        Address address) {
}
~~~

`@ConvertGroup` thuộc `jakarta.validation.groups.ConvertGroup`, và chỉ có ý nghĩa trên cạnh được cascade qua `@Valid`. Khi caller validate **Default** trên ConvertedRequest, phần address được validate theo **AddressReview** thay cho Default, do rule conversion.

Nếu address có:

~~~text
city=""         → thuộc Default
zipCode=""      → thuộc BusinessChecks
districtCode="" → thuộc AddressReview
~~~

thì theo conversion nói trên, **lỗi districtCode xuất hiện**, còn city/zipCode không được kiểm tra chỉ từ Default propagated qua cạnh này. Đây là cách mô tả tốt tại sao “field nested của nhóm mong muốn chưa được kích hoạt” hoặc “field default bất ngờ không có lỗi”.

### 4.3. Các giới hạn quan trọng của ConvertGroup

- `@ConvertGroup` cần `@Valid` trên cùng cascade point/container element tương ứng.
- `from` là nhóm đầu vào **sau khi sequence đã được mở rộng**; không được đặt một group sequence vào `from`.
- `to` có thể trỏ tới một group sequence hợp lệ.
- Conversion ở một cạnh không tự được áp dụng đệ quy thành nhiều phép nối tiếp trên cùng cạnh: `A→B` rồi `B→C` không có nghĩa A tự chuyển tiếp thành C tại chính cạnh đó.
- Không khai báo hai mappings có cùng `from` trên cùng conversion point; provider có thể ném `ConstraintDeclarationException`.
- Conversion không cấp quyền hoặc thay authentication; nó chỉ chọn nhóm constraint trong Bean Validation.

Khi chẩn đoán một nested field không báo lỗi, phải kiểm: **có @Valid hay chưa, object có null không, nhóm nào được propagate, có @ConvertGroup không, constraint thuộc nhóm nào**.

## 5. @GroupSequenceProvider: phần mở rộng của Hibernate Validator

`@GroupSequenceProvider` thuộc `org.hibernate.validator.group.GroupSequenceProvider`. Nó **không phải annotation tiêu chuẩn Jakarta**. Hibernate Validator cung cấp cơ chế tái định nghĩa Default sequence **động theo trạng thái object**.

Ví dụ ý tưởng:

~~~text
Registration isDraft=true
  → chỉ kiểm tra nhóm mặc định của bean

Registration isDraft=false
  → kiểm nhóm mặc định rồi FinalChecks
~~~

Default group sequence provider có thể lấy object hiện tại để quyết định các groups, đồng thời phải đưa **class được validate** vào sequence theo quy tắc provider.

Trước khi dùng, cần trả lời:

1. Dự án có dùng Hibernate Validator hay một Jakarta provider khác?
2. Validation có được gọi trên object đúng với trạng thái dùng để chọn sequence không?
3. Khi object null/provider khởi tạo metadata, logic provider có null-safe không?
4. Có test khi state thay đổi Draft→Final, đảm bảo nhóm thật sự được kích hoạt?
5. Có tạo conflict với `@GroupSequence` tĩnh trên cùng bean không?

**Không dùng input flag tự gửi từ client làm cơ chế phân quyền.** Một client không được quyền tự đặt `isAdmin=true` hoặc `isApproved=true` chỉ để nhóm validation thay đổi; nhóm chỉ quyết định tính hợp lệ dữ liệu, còn quyền thực thi nằm ở service/security.

Nếu portability quan trọng, ưu tiên `@Validated(SomeSequence.class)` hoặc gọi `Validator.validate(object, group)` rõ ràng từ use case, thay vì phụ thuộc provider-specific feature.

## 6. Spring MVC: @Valid và @Validated trong pipeline

### 6.1. Đối với @RequestBody

~~~java
@PostMapping("/default")
ResponseEntity<?> createDefault(
        @Valid @RequestBody RegistrationRequest input) {
    // ...
}
~~~

Thông thường Spring MVC kiểm tra Default. Nếu constraint chỉ được gán `groups=FinalChecks.class`, nó **không chạy**.

~~~java
@PostMapping("/ordered")
ResponseEntity<?> createOrdered(
        @Validated(OrderedChecks.class)
        @RequestBody RegistrationRequest input) {
    // ...
}
~~~

Spring truyền group hint `OrderedChecks.class` cho validator. Sequence được mở rộng bởi Jakarta provider; nếu Default sai, BusinessChecks và FinalChecks bị bỏ qua. Khi không có `BindingResult` ngay sau parameter, Spring MVC có thể ném `MethodArgumentNotValidException`.

### 6.2. Với @ModelAttribute và BindingResult

~~~java
@PostMapping("/submit-form")
String submit(
        @Validated(OrderedChecks.class)
        @ModelAttribute("registrationForm")
        RegistrationForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "registration-form";
    }
    return "redirect:/success";
}
~~~

Đây là **snippet** dành cho form MVC truyền thống; cần `RegistrationForm` và view tương ứng, không nằm trong project demo JSON. Khi `BindingResult` đặt **ngay sau** form argument, Spring có thể trao errors cho controller thay vì bắt buộc ném exception. Điều này **không có nghĩa validation không chạy**. Hãy inspect:

~~~java
errors.getFieldErrors();
errors.getGlobalErrors();
errors.getAllErrors();
errors.getErrorCount();
~~~

Nếu đặt `BindingResult` sai vị trí, hoặc có method validation trên các tham số khác, đường xử lý exception có thể khác. Không chẩn đoán chỉ dựa trên việc một `@ExceptionHandler` có được gọi hay không.

### 6.3. Method validation trong Spring 6.1+

Từ Spring Framework 6.1, MVC có native controller method validation cho direct constraints:

~~~java
@GetMapping("/limits")
String limits(@RequestParam @Min(1) int count) {
    return "ok";
}
~~~

Khi có direct method constraint như `@Min`, validation ở cấp method có thể **bao phủ** những argument cần `@Valid` và phát `HandlerMethodValidationException` thay vì `MethodArgumentNotValidException` của một object đơn lẻ.

Nếu controller có **class-level `@Validated`**, method validation có thể đi qua AOP proxy thay vì native MVC. Tài liệu Spring khuyên bỏ annotation cấp class khi muốn dùng native controller method validation của 6.1+. Vì thế, một handler advice chỉ xử lý `MethodArgumentNotValidException` có thể không bắt được mọi lỗi; đó không đồng nghĩa “group không được kích hoạt”.

### 6.4. @Validated trên service và self-invocation

Một service:

~~~java
@Service
@Validated
public class RegistrationService {

    public void approve(
            @Validated(FinalChecks.class)
            RegistrationRequest request) {
        // ...
    }
}
~~~

Đây là snippet phụ thuộc cấu hình method validation/AOP thực tế. Với Spring method validation thông qua proxy, **gọi method qua proxy** mới kích hoạt interceptor; self-invocation như `this.approve(...)` bên trong cùng instance thường bỏ qua proxy advice. Đây là vấn đề **điểm gọi validation** khác với `@GroupSequence` short-circuit.

Đừng kết luận “constraint group sai” trước khi chứng minh có một `Validator.validate(...)` hoặc interceptor thực sự được thực thi.

## 7. Quy trình chẩn đoán từ ngoài vào trong

Khi một test mong lỗi của nhóm FinalChecks nhưng chỉ thấy một lỗi Default, thực hiện theo thứ tự này.

### Bước 1 — Xác minh constraint và nhóm sở hữu

Đọc annotation đầy đủ:

~~~java
@NotBlank(groups = BusinessChecks.class)
String companyCode;
~~~

Nếu không ghi `groups`, annotation thuộc Default. Nếu ghi `groups={BusinessChecks.class,FinalChecks.class}`, constraint có mặt trong cả hai nhóm, không có thứ tự ưu tiên nội tại.

Có thể kiểm metadata:

~~~java
BeanDescriptor bean = validator
        .getConstraintsForClass(RegistrationRequest.class);

PropertyDescriptor property =
        bean.getConstraintsForProperty("companyCode");

Set<ConstraintDescriptor<?>> definitions =
        property.getConstraintDescriptors();
~~~

Đây là snippet; imports từ `jakarta.validation.metadata`. Kiểm `descriptor.getGroups()` để biết **constraint thực sự được khai báo thuộc những nhóm nào**, thay vì suy luận từ tên field.

### Bước 2 — Xác nhận caller yêu cầu nhóm gì

Đối chiếu:

~~~java
validator.validate(input);
validator.validate(input, BusinessChecks.class);
validator.validate(input, OrderedChecks.class);
validator.validate(input,
        Default.class,
        BusinessChecks.class,
        FinalChecks.class);
~~~

Bốn cách gọi cho ra những tập violations có thể khác nhau. Trong MVC, xem `@Valid` hay `@Validated(...)` gắn **đúng parameter** hay chưa. Trong service, xem call site có đi qua proxy method validation hay không.

### Bước 3 — Nếu dùng @GroupSequence, tìm nhóm đầu tiên thất bại

Đừng chỉ hỏi “vì sao FinalChecks không chạy?”. Hãy xác nhận:

~~~text
Default có lỗi?         → DỪNG, các nhóm sau bị skip
Default đạt, Business lỗi? → DỪNG, Final bị skip
Hai nhóm trước đều đạt?   → Final mới chạy
~~~

Viết một test cho từng cổng. Khi muốn kiểm riêng rule của FinalChecks, gọi `validator.validate(input,FinalChecks.class)` để biết rule hoạt động, sau đó chạy `OrderedChecks` để kiểm sequence.

### Bước 4 — Phân biệt interface sequence với class Default redefinition

- `@GroupSequence` trên interface: caller phải yêu cầu interface đó, ví dụ `OrderedChecks.class`.
- `@GroupSequence` trên class: định nghĩa lại Default cục bộ của class, **bắt buộc có chính class trong sequence**, không dùng Default.class thay thế.

Nếu nhận `GroupDefinitionException`, kiểm cycles/inheritance và danh sách của @GroupSequence trước khi thay constraints.

### Bước 5 — Kiểm nested/cascade/ConvertGroup

Object lồng có `@Valid` hay không? Có null không? Nhóm trên root có được propagate? Có `@ConvertGroup` chuyển Default thành nhóm khác? Có phần tử list/map với `@Valid`/type-use constraints không?

### Bước 6 — Phân biệt lỗi binding với lỗi validation

`age="abc"` ở form có thể thành `typeMismatch` trước khi `@Min` chạy. JSON không parse được có thể gây `HttpMessageNotReadableException` và không có Bean Validation trên DTO. Cần sửa input để deserialize được, rồi mới xác minh group sequence.

### Bước 7 — Kiểm provider, groups và test environment

- Có `spring-boot-starter-validation`/Hibernate Validator trên classpath không?
- Có một `LocalValidatorFactoryBean` hợp lệ cho Spring MVC không?
- Có tùy biến `Validator`/`WebMvcConfigurer.getValidator()`/`@InitBinder` vô tình thay adapter không?
- Có dùng Javax `javax.validation.*` cũ trong project Jakarta Boot 3 không?
- Có cấu hình fail-fast của provider không?
- Test chỉ tạo controller bằng `new` mà không dựng MVC validation infrastructure không?
- Có method-level validation làm exception class đổi không?

### Bước 8 — Đọc paths và descriptors, không đoán từ defaultMessage

Viết test kiểm các `ConstraintViolation.getPropertyPath().toString()` và `getConstraintDescriptor().getGroups()`. Tránh assert một câu tiếng Anh của Hibernate Validator, vì localization có thể thay đổi dù rule và group vẫn đúng.

## 8. Project Java 17+ / Spring Boot 3.5.7 chạy được

Dự án minh họa bốn tình huống:

1. **Default vs Business vs Final:** một form có Default constraints, BusinessChecks và FinalChecks.
2. **OrderedChecks:** sequence `Default → BusinessChecks → FinalChecks`, dừng tại nhóm đầu có lỗi.
3. **ConvertedRequest:** `@ConvertGroup(Default→AddressReview)` thay nhóm khi cascade vào nested Address.
4. **StrictProfile:** class-level `@GroupSequence` định nghĩa lại Default.

Có controller JSON với bốn endpoint: `/default`, `/ordered`, `/business`, `/unordered` để chứng minh cách chọn nhóm trong Spring MVC. Có unit tests với `jakarta.validation.Validator` và MockMvc tests cho status/path/group selection.

### 8.1. Cấu trúc tệp

~~~text
validation-group-diagnostics/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/groups/
    │   │   ├── Application.java
    │   │   ├── BusinessChecks.java
    │   │   ├── FinalChecks.java
    │   │   ├── AddressReview.java
    │   │   ├── ComplianceChecks.java
    │   │   ├── OrderedChecks.java
    │   │   ├── Address.java
    │   │   ├── RegistrationRequest.java
    │   │   ├── ConvertedRequest.java
    │   │   ├── StrictProfile.java
    │   │   ├── RegistrationController.java
    │   │   └── ValidationAdvice.java
    │   └── resources/application.properties
    └── test/java/com/example/groups/
        ├── GroupValidationTest.java
        └── GroupMvcTest.java
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>validation-group-diagnostics</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
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
~~~

Dự án dùng `jakarta.validation` chứ không dùng `javax.validation` của Spring Boot 2. `spring-boot-starter-validation` cần thiết để Spring Boot đăng ký provider như Hibernate Validator. Không cần tự khai báo thêm bean `Validator` nếu Boot auto-configuration đã cung cấp đúng bean.

### 8.3. Application.java

~~~java
package com.example.groups;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

### 8.4. BusinessChecks.java

~~~java
package com.example.groups;

public interface BusinessChecks {
}
~~~

### 8.5. FinalChecks.java

~~~java
package com.example.groups;

public interface FinalChecks {
}
~~~

### 8.6. AddressReview.java

~~~java
package com.example.groups;

public interface AddressReview {
}
~~~

### 8.7. ComplianceChecks.java

~~~java
package com.example.groups;

public interface ComplianceChecks {
}
~~~

Các marker interfaces này không có method. Chúng đại diện cho **những nhóm validation**, không phải roles/authorities bảo mật và cũng không phải Spring `@Component`.

### 8.8. OrderedChecks.java — sequence interface đúng

~~~java
package com.example.groups;

import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

@GroupSequence({
        Default.class,
        BusinessChecks.class,
        FinalChecks.class
})
public interface OrderedChecks {
}
~~~

Không viết `extends BusinessChecks` trên `OrderedChecks`; không gắn constraints trực tiếp vào `groups=OrderedChecks.class`. Đây là nhóm sequence được yêu cầu rõ ràng ở controller và tests.

### 8.9. Address.java

~~~java
package com.example.groups;

import jakarta.validation.constraints.NotBlank;

public record Address(
        @NotBlank String city,

        @NotBlank(groups = BusinessChecks.class)
        String zipCode,

        @NotBlank(groups = AddressReview.class)
        String districtCode) {
}
~~~

Ba properties thuộc ba nhóm khác nhau. Nếu chỉ validate Default trên Address, chỉ `city` được kiểm tra; nếu validate BusinessChecks, chỉ `zipCode` được kiểm tra; nếu validate AddressReview, chỉ `districtCode` được kiểm tra.

### 8.10. RegistrationRequest.java

~~~java
package com.example.groups;

import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record RegistrationRequest(
        @NotBlank @Email String email,

        @NotNull @Min(18) Integer age,

        @NotBlank(groups = BusinessChecks.class)
        String companyCode,

        @AssertTrue(groups = FinalChecks.class)
        boolean acceptedTerms,

        @NotNull @Valid Address address) {
}
~~~

Dùng boolean primitive `acceptedTerms` trong demo; mặc định false. Khi validate Default, `@AssertTrue(groups=FinalChecks.class)` **không** chạy. Khi validate FinalChecks, giá trị false tạo violation `acceptedTerms`. Trong sản phẩm thật, nếu cần phân biệt field vắng mặt với false, dùng `Boolean` và thêm `@NotNull(groups=FinalChecks.class)`.

Nhờ `@Valid Address`, khi group BusinessChecks được yêu cầu, nested `address.zipCode` cũng được kiểm tra. Không có `@ConvertGroup` trên cạnh này nên group propagation thông thường được giữ nguyên.

### 8.11. ConvertedRequest.java

~~~java
package com.example.groups;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.groups.Default;

public record ConvertedRequest(
        @NotBlank String label,

        @NotNull
        @Valid
        @ConvertGroup(
                from = Default.class,
                to = AddressReview.class)
        Address address) {
}
~~~

Đây là case chẩn đoán riêng: caller chỉ yêu cầu Default trên ConvertedRequest, nhưng nested Address được validate theo AddressReview. Không đưa loại request có group conversion này vào production chỉ để “chạy thêm tất cả nested checks”; cần thiết kế use case rõ ràng.

### 8.12. StrictProfile.java

~~~java
package com.example.groups;

import jakarta.validation.GroupSequence;
import jakarta.validation.constraints.NotBlank;

@GroupSequence({
        StrictProfile.class,
        ComplianceChecks.class
})
public record StrictProfile(
        @NotBlank String displayName,

        @NotBlank(groups = ComplianceChecks.class)
        String identityNumber) {
}
~~~

Khác với `OrderedChecks` (interface), annotation trên record/class ở đây **định nghĩa lại Default**. Thành viên đầu là `StrictProfile.class`, không phải Default.class. `validator.validate(profile)` sẽ kiểm displayName trước, rồi identityNumber nếu displayName hợp lệ.

### 8.13. RegistrationController.java

~~~java
package com.example.groups;

import jakarta.validation.Valid;
import jakarta.validation.groups.Default;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/registrations")
public class RegistrationController {

    public record Accepted(
            String result,
            String email) {
    }

    private ResponseEntity<Accepted> accept(
            RegistrationRequest input) {

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new Accepted("accepted", input.email()));
    }

    @PostMapping(
            path = "/default",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Accepted> defaultSubmit(
            @Valid @RequestBody RegistrationRequest input) {
        return accept(input);
    }

    @PostMapping(
            path = "/ordered",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Accepted> orderedSubmit(
            @Validated(OrderedChecks.class)
            @RequestBody RegistrationRequest input) {
        return accept(input);
    }

    @PostMapping(
            path = "/business",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Accepted> businessOnly(
            @Validated(BusinessChecks.class)
            @RequestBody RegistrationRequest input) {
        return accept(input);
    }

    @PostMapping(
            path = "/unordered",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Accepted> unorderedAll(
            @Validated({
                    Default.class,
                    BusinessChecks.class,
                    FinalChecks.class
            })
            @RequestBody RegistrationRequest input) {
        return accept(input);
    }
}
~~~

**Bốn endpoint dùng để học và đối chiếu**, không phải thiết kế production khuyến nghị dùng nguyên xi:

- `/default`: chỉ yêu cầu Default.
- `/ordered`: yêu cầu sequence Default→Business→Final, dừng khi nhóm trước lỗi.
- `/business`: chỉ yêu cầu BusinessChecks; có thể cho qua dữ liệu không đạt Default vì Default không nằm trong yêu cầu. Điều này giúp tìm bug nhưng **không có nghĩa nên triển khai endpoint nghiệp vụ thiếu checks cơ bản**.
- `/unordered`: yêu cầu ba nhóm độc lập; không có short-circuit theo thứ tự cố định như OrderedChecks.

Controller **không có class-level @Validated**, tránh trộn native method validation của Spring MVC 6.1+ với cơ chế AOP không cần thiết. Các method không có direct constraints như `@Min` trên tham số khác, nên lỗi bean input thông thường đi qua `MethodArgumentNotValidException`.

### 8.14. ValidationAdvice.java

~~~java
package com.example.groups;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

import java.util.Comparator;
import java.util.List;
import java.util.Objects;

@RestControllerAdvice
public class ValidationAdvice
        extends ResponseEntityExceptionHandler {

    public record FieldIssue(
            String field,
            String code) {
    }

    public record ErrorReport(
            String code,
            List<FieldIssue> fieldErrors,
            List<String> globalErrors) {
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        BindingResult errors = ex.getBindingResult();

        List<FieldIssue> fields = errors.getFieldErrors()
                .stream()
                .map(error -> new FieldIssue(
                        error.getField(),
                        Objects.toString(
                                error.getCode(), "invalid")))
                .sorted(Comparator
                        .comparing(FieldIssue::field)
                        .thenComparing(FieldIssue::code))
                .toList();

        List<String> globals = errors.getGlobalErrors()
                .stream()
                .map(error -> Objects.toString(
                        error.getCode(), "invalid"))
                .sorted()
                .toList();

        return handleExceptionInternal(
                ex,
                new ErrorReport(
                        "VALIDATION_FAILED",
                        fields,
                        globals),
                headers,
                status,
                request);
    }
}
~~~

`ResponseEntityExceptionHandler` đã xử lý nhiều Spring MVC exceptions. Ở đây ta chỉ override hook cho `MethodArgumentNotValidException`, tránh đăng ký thêm một `@ExceptionHandler(MethodArgumentNotValidException.class)` gây mapping trùng trên cùng advice.

Body chỉ gồm **field path** và **constraint code**, không đưa `FieldError.getRejectedValue()` vào JSON; rejected value có thể là password, token hoặc dữ liệu nhạy cảm. Đường lỗi `address.zipCode` giúp test cascade và group propagation.

**Không thể suy ra một cách chắc chắn nhóm đã được chạy chỉ từ `FieldError.getCode()`:** một annotation như `@NotBlank` có thể thuộc nhiều nhóm. Muốn chẩn đoán chính xác, dùng metadata `ConstraintDescriptor.getGroups()` và đối chiếu các lời gọi `Validator.validate(...groups)` trong unit tests.

### 8.15. application.properties

~~~properties
server.port=8080
spring.mvc.problemdetails.enabled=false
server.error.include-message=never
~~~

Demo dùng custom advice cho error shape dễ kiểm thử, không phụ thuộc vào response mặc định của Spring Boot. Nếu sản phẩm dùng RFC 9457 `ProblemDetail`, vẫn phải kiểm groups và binding/validation tương tự; format body lỗi không làm sequence thay đổi.

## 9. Unit tests: xác định chính xác nhóm hoạt động

Tạo `src/test/java/com/example/groups/GroupValidationTest.java`:

~~~java
package com.example.groups;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.GroupDefinitionException;
import jakarta.validation.GroupSequence;
import jakarta.validation.Validator;
import jakarta.validation.groups.Default;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class GroupValidationTest {

    @Autowired
    Validator validator;

    private static RegistrationRequest input(
            String email,
            int age,
            String companyCode,
            boolean acceptedTerms,
            String city,
            String zipCode) {

        return new RegistrationRequest(
                email,
                age,
                companyCode,
                acceptedTerms,
                new Address(city, zipCode, "D1"));
    }

    private static RegistrationRequest valid() {
        return input(
                "lan@example.com",
                25,
                "COMPANY-1",
                true,
                "Ha Noi",
                "12345");
    }

    private static <T> Set<String> paths(
            Set<ConstraintViolation<T>> violations) {

        return violations.stream()
                .map(v -> v.getPropertyPath().toString())
                .collect(Collectors.toSet());
    }

    @Test
    void defaultDoesNotActivateCustomGroups() {
        RegistrationRequest request = input(
                "", 16, "", false,
                "", "");

        var result = validator.validate(request);

        assertEquals(
                Set.of("email", "age", "address.city"),
                paths(result));

        assertFalse(paths(result).contains("companyCode"));
        assertFalse(paths(result).contains("acceptedTerms"));
        assertFalse(paths(result).contains(
                "address.zipCode"));
    }

    @Test
    void businessOnlyDoesNotImplicitlyIncludeDefault() {
        RegistrationRequest request = input(
                "", 16, "", false,
                "", "");

        var result = validator.validate(
                request,
                BusinessChecks.class);

        assertEquals(
                Set.of("companyCode", "address.zipCode"),
                paths(result));
    }

    @Test
    void orderedStopsAfterDefaultFailures() {
        RegistrationRequest request = input(
                "", 16, "", false,
                "", "");

        var result = validator.validate(
                request,
                OrderedChecks.class);

        assertEquals(
                Set.of("email", "age", "address.city"),
                paths(result));
    }

    @Test
    void orderedStopsAfterBusinessFailures() {
        RegistrationRequest request = input(
                "lan@example.com", 25, "", false,
                "Ha Noi", "");

        var result = validator.validate(
                request,
                OrderedChecks.class);

        assertEquals(
                Set.of("companyCode", "address.zipCode"),
                paths(result));

        assertFalse(paths(result).contains("acceptedTerms"));
    }

    @Test
    void orderedReachesFinalOnlyAfterPreviousPass() {
        RegistrationRequest request = input(
                "lan@example.com", 25,
                "COMPANY-1", false,
                "Ha Noi", "12345");

        var result = validator.validate(
                request,
                OrderedChecks.class);

        assertEquals(Set.of("acceptedTerms"), paths(result));
    }

    @Test
    void allValidPassesOrderedChecks() {
        assertTrue(validator.validate(
                valid(),
                OrderedChecks.class).isEmpty());
    }

    @Test
    void independentGroupsDoNotShortCircuit() {
        RegistrationRequest request = input(
                "", 16, "", false, "", "");

        var result = validator.validate(
                request,
                Default.class,
                BusinessChecks.class,
                FinalChecks.class);

        assertEquals(
                Set.of(
                    "email",
                    "age",
                    "address.city",
                    "companyCode",
                    "address.zipCode",
                    "acceptedTerms"),
                paths(result));
    }

    public interface AdvancedBusinessChecks
            extends BusinessChecks {
    }

    @Test
    void inheritedGroupIncludesParentConstraints() {
        RegistrationRequest request = input(
                "", 16, "", false,
                "", "");

        var result = validator.validate(
                request,
                AdvancedBusinessChecks.class);

        assertEquals(
                Set.of("companyCode", "address.zipCode"),
                paths(result));
    }

    @Test
    void convertGroupChangesNestedGroupOnly() {
        ConvertedRequest request =
                new ConvertedRequest(
                        "ok",
                        new Address("", "", ""));

        var result = validator.validate(request);

        assertEquals(
                Set.of("address.districtCode"),
                paths(result));

        assertEquals(
                Set.of("city"),
                paths(validator.validate(request.address())));
    }

    @Test
    void classLevelDefaultSequenceStopsOnFirstStage() {
        StrictProfile p = new StrictProfile("", "");

        assertEquals(
                Set.of("displayName"),
                paths(validator.validate(p)));

        StrictProfile later = new StrictProfile(
                "Lan", "");

        assertEquals(
                Set.of("identityNumber"),
                paths(validator.validate(later)));
    }

    @GroupSequence({
            Default.class,
            ComplianceChecks.class
    })
    static class BrokenProfile {

        @jakarta.validation.constraints.NotBlank
        private String displayName = "";
    }

    @Test
    void invalidDefaultRedefinitionThrows() {
        assertThrows(
                GroupDefinitionException.class,
                () -> validator.validate(
                        new BrokenProfile()));
    }

    @Test
    void metadataShowsDeclaredGroup() {
        var descriptor = validator
                .getConstraintsForClass(
                        RegistrationRequest.class)
                .getConstraintsForProperty("companyCode");

        assertNotNull(descriptor);

        assertTrue(descriptor
                .getConstraintDescriptors()
                .stream()
                .anyMatch(constraint ->
                    constraint.getGroups()
                            .contains(BusinessChecks.class)));

        assertFalse(descriptor
                .getConstraintDescriptors()
                .stream()
                .anyMatch(constraint ->
                    constraint.getGroups()
                            .contains(Default.class)));
    }
}
~~~

### 9.1. Đọc kết quả của 12 tests

| Test | Điều nó chứng minh |
| --- | --- |
| `defaultDoesNotActivateCustomGroups` | Không mặc định chạy Business/Final |
| `businessOnlyDoesNotImplicitlyIncludeDefault` | Chọn Business riêng không tự thêm Default |
| `orderedStopsAfterDefaultFailures` | Chuỗi dừng tại bước Default |
| `orderedStopsAfterBusinessFailures` | Default đạt, Business lỗi thì Final bị skip |
| `orderedReachesFinalOnlyAfterPreviousPass` | Final chỉ chạy khi hai nhóm trước đã đạt |
| `allValidPassesOrderedChecks` | Cấu hình sequence đúng cho dữ liệu hợp lệ |
| `independentGroupsDoNotShortCircuit` | Truyền nhiều nhóm không tạo sequence |
| `inheritedGroupIncludesParentConstraints` | Group inheritance hoạt động |
| `convertGroupChangesNestedGroupOnly` | Nested Address được chuyển từ Default sang AddressReview |
| `classLevelDefaultSequenceStopsOnFirstStage` | Default redefinition trên class |
| `invalidDefaultRedefinitionThrows` | Sai khi dùng Default.class thay class sở hữu |
| `metadataShowsDeclaredGroup` | Đọc metadata xác nhận groups đã khai báo |

**Vì sao test so tập path?** `Validator.validate(...)` trả `Set<ConstraintViolation<?>>`, không bảo đảm thứ tự violations tương ứng thứ tự khai báo fields. Việc dùng `Set.of(...)` và so paths giúp test không bị phụ thuộc vào thứ tự ngẫu nhiên của provider.

Trong project này, fixture cố ý làm mỗi field có một rule lỗi tại một thời điểm (ví dụ email rỗng làm `@NotBlank` lỗi, còn `@Email` chấp nhận chuỗi rỗng). Nếu thêm constraints khác, cần cập nhật test theo tập mã/paths thực tế.

## 10. MockMvc tests: @Valid, @Validated và group hints qua HTTP

Tạo `src/test/java/com/example/groups/GroupMvcTest.java`:

~~~java
package com.example.groups;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class GroupMvcTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    private ObjectNode validJson() {
        ObjectNode root = mapper.createObjectNode();
        root.put("email", "lan@example.com");
        root.put("age", 25);
        root.put("companyCode", "COMPANY-1");
        root.put("acceptedTerms", true);

        root.putObject("address")
                .put("city", "Ha Noi")
                .put("zipCode", "12345")
                .put("districtCode", "D1");

        return root;
    }

    private ResultActions send(
            String endpoint,
            ObjectNode json) throws Exception {

        return mvc.perform(post(
                        "/api/registrations/" + endpoint)
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsBytes(json)));
    }

    @Test
    void defaultEndpointIgnoresNonDefaultGroups()
            throws Exception {

        ObjectNode request = validJson();

        request.put("companyCode", "");
        request.put("acceptedTerms", false);
        ((ObjectNode) request.get("address"))
                .put("zipCode", "");

        send("default", request)
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.result")
                        .value("accepted"));
    }

    @Test
    void defaultEndpointRejectsDefaultViolation()
            throws Exception {

        ObjectNode request = validJson();
        request.put("email", "");

        send("default", request)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_FAILED"))
                .andExpect(jsonPath(
                        "$.fieldErrors[0].field")
                        .value("email"))
                .andExpect(jsonPath(
                        "$.fieldErrors[0].code")
                        .value("NotBlank"));
    }

    @Test
    void orderedStopsAtDefault() throws Exception {
        ObjectNode request = validJson();

        request.put("email", "");
        request.put("age", 16);
        request.put("companyCode", "");
        request.put("acceptedTerms", false);

        ((ObjectNode) request.get("address"))
                .put("city", "")
                .put("zipCode", "");

        send("ordered", request)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors.length()")
                        .value(3))
                .andExpect(jsonPath(
                        "$.fieldErrors[0].field")
                        .value("address.city"))
                .andExpect(jsonPath(
                        "$.fieldErrors[1].field")
                        .value("age"))
                .andExpect(jsonPath(
                        "$.fieldErrors[2].field")
                        .value("email"));
    }

    @Test
    void orderedStopsAtBusiness() throws Exception {
        ObjectNode request = validJson();

        request.put("companyCode", "");
        request.put("acceptedTerms", false);

        ((ObjectNode) request.get("address"))
                .put("zipCode", "");

        send("ordered", request)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors.length()")
                        .value(2))
                .andExpect(jsonPath(
                        "$.fieldErrors[0].field")
                        .value("address.zipCode"))
                .andExpect(jsonPath(
                        "$.fieldErrors[1].field")
                        .value("companyCode"));
    }

    @Test
    void orderedReachesFinalAfterEarlierStagesPass()
            throws Exception {

        ObjectNode request = validJson();
        request.put("acceptedTerms", false);

        send("ordered", request)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors.length()")
                        .value(1))
                .andExpect(jsonPath(
                        "$.fieldErrors[0].field")
                        .value("acceptedTerms"))
                .andExpect(jsonPath(
                        "$.fieldErrors[0].code")
                        .value("AssertTrue"));
    }

    @Test
    void orderedAcceptsValidBody() throws Exception {
        send("ordered", validJson())
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.result")
                        .value("accepted"));
    }

    @Test
    void businessOnlyCanMissDefaultViolations()
            throws Exception {

        ObjectNode request = validJson();
        request.put("email", "");
        request.put("age", 16);
        request.put("acceptedTerms", false);
        ((ObjectNode) request.get("address"))
                .put("city", "");

        // Cảnh báo có chủ đích: đây là endpoint minh họa
        // cách lựa chọn sai nhóm có thể bỏ lọt Default.
        send("business", request)
                .andExpect(status().isCreated());
    }

    @Test
    void unorderedChecksAllRequestedGroups()
            throws Exception {

        ObjectNode request = validJson();

        request.put("email", "");
        request.put("age", 16);
        request.put("companyCode", "");
        request.put("acceptedTerms", false);

        ((ObjectNode) request.get("address"))
                .put("city", "")
                .put("zipCode", "");

        send("unordered", request)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors.length()")
                        .value(6));
    }

    @Test
    void malformedJsonFailsBeforeBeanValidation()
            throws Exception {

        mvc.perform(post("/api/registrations/ordered")
                        .contentType(
                                MediaType.APPLICATION_JSON)
                        .content("{"))
                .andExpect(status().isBadRequest());
    }
}
~~~

### 10.1. Vì sao kiểm thử hai lớp?

`GroupValidationTest` gọi Jakarta `Validator` trực tiếp để xác minh rules và group sequence **không phụ thuộc HTTP**. `GroupMvcTest` kiểm Spring argument resolution, `@Valid`/`@Validated` hints, Jackson, exception handling và response contract.

Nếu unit test PASS mà MockMvc không chạy nhóm mong muốn, tập trung vào annotation ở controller, validation provider integration, method signature và cấu hình MVC. Nếu cả unit test cũng không có violation, tập trung vào annotation `groups`, data fixture, cascade/ConvertGroup và sequence.

**Tổng cộng có 21 bài kiểm thử:** 12 unit và 9 MockMvc, theo nội dung nguồn trình bày. Chúng kiểm tra cả các tình huống hệ thống *cố ý* không chạy nhóm phía sau, thay vì chỉ thử input hoàn toàn hợp lệ.

## 11. Chạy thử và kết quả HTTP dự kiến

### 11.1. Lệnh chạy

Ở thư mục chứa `pom.xml`, cần JDK 17+ và Maven:

~~~bash
mvn test
mvn spring-boot:run
~~~

Chạy riêng:

~~~bash
mvn -Dtest=GroupValidationTest test
mvn -Dtest=GroupMvcTest test
~~~

### 11.2. Mẫu JSON hợp lệ

~~~json
{
  "email": "lan@example.com",
  "age": 25,
  "companyCode": "COMPANY-1",
  "acceptedTerms": true,
  "address": {
    "city": "Ha Noi",
    "zipCode": "12345",
    "districtCode": "D1"
  }
}
~~~

Gửi:

~~~bash
curl -i -X POST \
  http://localhost:8080/api/registrations/ordered \
  -H "Content-Type: application/json" \
  -d '{
    "email":"lan@example.com",
    "age":25,
    "companyCode":"COMPANY-1",
    "acceptedTerms":true,
    "address":{
      "city":"Ha Noi",
      "zipCode":"12345",
      "districtCode":"D1"
    }
  }'
~~~

Response dự kiến HTTP **201 Created**:

~~~json
{
  "result": "accepted",
  "email": "lan@example.com"
}
~~~

### 11.3. Default có lỗi nên không tới Business/Final

~~~bash
curl -i -X POST \
  http://localhost:8080/api/registrations/ordered \
  -H "Content-Type: application/json" \
  -d '{
    "email":"",
    "age":16,
    "companyCode":"",
    "acceptedTerms":false,
    "address":{
      "city":"",
      "zipCode":"",
      "districtCode":""
    }
  }'
~~~

Dù nhiều fields đều sai nếu xét toàn bộ các nhóm, **OrderedChecks dừng sau Default**. Response 400 chính:

~~~json
{
  "code": "VALIDATION_FAILED",
  "fieldErrors": [
    {"field": "address.city", "code": "NotBlank"},
    {"field": "age", "code": "Min"},
    {"field": "email", "code": "NotBlank"}
  ],
  "globalErrors": []
}
~~~

Không có `companyCode`, `address.zipCode` hay `acceptedTerms` ở đây **không phải bug**; chúng nằm ở nhóm chưa được chạy. `districtCode` thuộc AddressReview, nhóm này không nằm trong OrderedChecks và cũng không được convert ở RegistrationRequest, nên không được xét ở endpoint này.

### 11.4. Business có lỗi nên Final bị skip

Một request có Default hợp lệ, nhưng `companyCode=""`, `address.zipCode=""` và `acceptedTerms=false` trả 400 với:

~~~json
{
  "code": "VALIDATION_FAILED",
  "fieldErrors": [
    {"field": "address.zipCode", "code": "NotBlank"},
    {"field": "companyCode", "code": "NotBlank"}
  ],
  "globalErrors": []
}
~~~

`acceptedTerms` không xuất hiện do chưa đến FinalChecks.

### 11.5. Những case hỗ trợ phân biệt lỗi

| Endpoint | Input | Kết quả |
| --- | --- | --- |
| `/default` | Default hợp lệ, Business/Final sai | **201**, vì không yêu cầu nhóm tùy chỉnh |
| `/ordered` | Default sai | **400**, chỉ errors của Default |
| `/ordered` | Default đạt, Business sai | **400**, chỉ errors của Business |
| `/ordered` | Default/Business đạt, Final sai | **400**, chỉ errors của Final |
| `/ordered` | Tất cả đạt | **201** |
| `/business` | Business đạt, Default sai | **201** minh họa bug chọn nhóm không đủ |
| `/unordered` | Các nhóm đều có lỗi | **400**, errors của các nhóm được yêu cầu |
| `/ordered` | JSON không parse được | **400** do decoding, không dùng kết quả group sequence |

Trạng thái 201 của `/business` là một **cảnh báo kiến trúc có chủ đích**, không phải thiết kế production được khuyên dùng.

## 12. Các sai lầm chẩn đoán thường gặp

| Triệu chứng | Nguyên nhân có thể | Kiểm tra và sửa |
| --- | --- | --- |
| Constraint có `groups=FinalChecks.class` không báo lỗi với `@Valid` | `@Valid` mặc định chỉ yêu cầu Default | Dùng `@Validated(FinalChecks.class)` hoặc sequence thích hợp |
| Đã tạo `OrderedChecks` nhưng `validator.validate(bean)` không thay đổi | Chưa yêu cầu sequence | Gọi `validate(bean,OrderedChecks.class)` |
| Final không chạy mặc dù field Final sai | Default hoặc Business trước đó có violation | Test từng giai đoạn của sequence |
| Truyền ba groups cùng lúc nhưng lỗi xuất hiện ở cả ba | Truyền nhiều nhóm không bảo đảm thứ tự/short-circuit | Dùng một interface `@GroupSequence` |
| `@GroupSequence({Default.class,...})` trên class báo `GroupDefinitionException` | Sai Default redefinition | Thay Default.class bằng chính class |
| Sequence interface extends group khác | Quan hệ sequence/inheritance không hợp lệ | Sequence interface không nên extends |
| Sequence A bao gồm B và B bao gồm A | Chu kỳ nhóm | Gỡ cycle, kiểm metadata |
| Constraint khai báo `groups=OrderedChecks.class` | Dùng sequence interface như constraint group trực tiếp | Gán vào nhóm thành phần |
| Group Business được yêu cầu nhưng nested zip không được kiểm | Thiếu `@Valid` ở cạnh cascade hoặc object null | Kiểm `@NotNull @Valid` và path |
| Cha có Default sequence nhưng con không chạy nhóm phụ của cha | Default redefinition local | Dùng `@ConvertGroup` ở association khi cần |
| Sau ConvertGroup, city Default của Address không được báo | Default trên cạnh đã chuyển sang AddressReview | Điều chỉnh conversion/rules theo use case |
| `@ConvertGroup` không có hiệu lực | Thiếu `@Valid` hoặc from không khớp group sau expansion | Kiểm cascade và nhóm thật |
| Nhóm Final không chạy dù DTO có `@Validated` | Annotation đặt sai điểm hoặc method validation khác | Đọc method signature và exception type |
| Service `@Validated` nhưng tự gọi method không validate | Bypass Spring AOP proxy | Gọi qua proxy/service boundary hoặc Validator trực tiếp |
| Test thiếu Hibernate Validator | Thiếu validation provider/starter | Thêm `spring-boot-starter-validation` |
| Thấy `MethodArgumentNotValidException` thay vì expected exception | Argument-level MVC validation | Kiểm `BindingResult` và advice |
| Thấy `HandlerMethodValidationException` | Direct method constraints trên MVC 6.1+ | Test native method validation/handler khác |
| Field `age="abc"` không tạo Min violation | Type conversion/deserialization sai trước Bean Validation | Test decoding riêng |
| Test group khác kết quả khi bật fail-fast | Provider dừng sớm trong cùng nhóm | Không phụ thuộc số lỗi khi fail-fast |
| Violation order đổi giữa máy | `Set` không có thứ tự được bảo đảm | So tập path/codes, không dùng iterator().next() |
| `Default` của bean được redefine nhưng behavior khác con | Rule cục bộ không propagate sequence nguyên vẹn | Test parent và nested riêng |
| Dùng class-level `@Validated` trên controller mới | AOP method validation có thể thay native behavior | Xác định kiến trúc controller và Spring version |
| Dùng `@Valid` trên `Mono<T>` trong MVC mà mong tức thì | Reactive arguments khác Servlet binding | Chọn đúng MVC/WebFlux pipeline |

## 13. Khi nào dùng @Validated({Default, Business, Final}) và khi nào dùng sequence?

Có hai ý đồ nghiệp vụ khác nhau:

### 13.1. Muốn thu tất cả lỗi liên quan trong một lượt

~~~java
validator.validate(
        request,
        Default.class,
        BusinessChecks.class,
        FinalChecks.class);
~~~

Điều này phù hợp khi frontend muốn hiển thị **tất cả lỗi ở nhiều nhóm** và việc kiểm tra các nhóm không phụ thuộc vào trạng thái ổn định của nhóm trước. **Không** dựa vào thứ tự đánh giá giữa các nhóm độc lập.

### 13.2. Muốn thực hiện kiểm tra theo giai đoạn

~~~java
validator.validate(
        request,
        OrderedChecks.class);
~~~

Phù hợp khi business checks chỉ có ý nghĩa sau khi dữ liệu nền tảng đầy đủ, hoặc final checks tốn kém nên không cần chạy nếu basic validation đã hỏng. Nếu một giai đoạn có lỗi, các giai đoạn sau bị skip theo định nghĩa sequence.

**Đừng chọn sequence chỉ để “test dễ viết hơn”**: nó thay đổi tập lỗi trả cho người dùng. Hãy quyết định UX/contract có muốn hiển thị đồng thời tất cả lỗi hay theo từng giai đoạn.

## 14. Định nghĩa nhóm theo chức năng thay vì theo vị trí công nghệ

Một mô hình tốt:

~~~text
Default         → cú pháp, null/blank, kiểu và giới hạn cơ bản
BusinessChecks  → điều kiện nghiệp vụ của màn hình đó
FinalChecks     → điều kiện chỉ áp dụng khi submit cuối
AddressReview   → dữ liệu địa chỉ ở bước riêng
~~~

Không bắt buộc mọi constraint cơ bản phải trong Default. Tuy nhiên, khi chia nhóm, một developer mới có thể hiểu sai rằng `@Valid` “đã kiểm hết”. Vì vậy:

- Viết tài liệu nhóm được dùng ở mỗi endpoint/use case.
- Đặt tên nhóm có nghĩa nghiệp vụ (`FinalSubmit`, `DraftChecks`, `PaymentChecks`) thay vì `Group1`.
- Tránh lồng nhóm có dependency phức tạp nếu chỉ cần validation thủ công rõ ràng.
- Không dùng validation groups để quyết định quyền truy cập (`role`, `owner`, `approval` phải do authorization/service xác định).
- Khi thay đổi một constraint từ Default sang nhóm khác, cập nhật integration tests vì endpoint `@Valid` có thể không còn bắt lỗi đó.

## 15. Group conversion trong List, Map và nested graph

Với collection:

~~~java
public record BatchRequest(
        @Valid
        List<@Valid Address> addresses) {
}
~~~

Đây là snippet. Cascading vào từng phần tử giúp kiểm các constraints thuộc **nhóm đang được propagate**. Nếu Address có `zipCode` trong BusinessChecks, Default-only call không kích hoạt zipCode chỉ vì nó nằm trong list.

Có thể khai báo `@ConvertGroup` trên vị trí type-use/cascade phù hợp của Jakarta Bean Validation để chuyển group khi đi qua collection elements, ví dụ:

~~~java
public record BatchReview(
        List<
            @Valid
            @ConvertGroup(
                from = Default.class,
                to = AddressReview.class)
            Address> addresses) {
}
~~~

Đây là snippet type-use được hỗ trợ bởi provider tương thích Jakarta Validation 3.0; cần imports `List`, `Valid`, `ConvertGroup`, `Default`. Test property path, chẳng hạn `addresses[0].districtCode`, với provider/version thật. Chỉ khai báo `@ConvertGroup` trên collection mà không có cascade ở đúng chỗ sẽ không tạo sự chuyển nhóm mong muốn.

Đặc biệt, khi class cha có Default sequence redefine, bạn không nên giả định toàn bộ sequence được truyền nguyên cho mỗi element; hãy dựa vào **expanded groups và conversion rule trên cạnh**. Debug theo từng cấp của graph.

## 16. Kiểm tra custom constraint và meta-annotation

Nếu viết constraint tùy chỉnh:

~~~java
@Target({ FIELD, PARAMETER })
@Retention(RUNTIME)
@Constraint(validatedBy = UniqueCodeValidator.class)
public @interface UniqueCode {
    String message() default "Code already in use";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Đây là snippet thiết kế annotation, không phải file runnable trong demo (cần validator và imports). Với Jakarta Bean Validation, custom constraint annotation phải công bố `groups()` và `payload()` phù hợp; caller chọn nhóm khi gắn:

~~~java
@UniqueCode(groups = BusinessChecks.class)
private String companyCode;
~~~

Nếu custom annotation bị khai báo sai target/retention/validator type, có thể phát sinh `ConstraintDefinitionException` hoặc `UnexpectedTypeException`. Đây là **lỗi metadata/validator configuration**, khác việc một nhóm được skip do sequence. Đừng bắt mọi exception thành “group không chạy” rồi bỏ qua stack trace nội bộ.

Khi một constraint hợp thành (composed constraint) có nhiều annotations bên trong, test số lượng violations có thể cần hiểu `@ReportAsSingleViolation`; kiểm **codes, paths và descriptors** thay vì chỉ số lượng.

## 17. Checklist kiểm thử hồi quy khi nâng cấp

1. Xác nhận Java 17+, Boot/Spring Framework/Hibernate Validator versions và namespace Jakarta.
2. Kiểm `@Valid`, `@Validated(...)`, `@ModelAttribute` hoặc `@RequestBody` ở đúng controller argument.
3. Liệt kê group declarations thực tế của từng constraint qua metadata.
4. Dựng test `validator.validate(bean)` cho Default.
5. Dựng test `validator.validate(bean,Custom.class)` cho từng nhóm.
6. Dựng test `validator.validate(bean,Sequence.class)` cho từng stage.
7. Dựng test “nhiều nhóm độc lập” để tránh nhầm với sequence.
8. Nếu có class-level Default redefine, kiểm class nằm trong danh sách `@GroupSequence`.
9. Nếu nested validation không hoạt động, kiểm `@Valid`, null state và group conversion.
10. Nếu dùng Hibernate `@GroupSequenceProvider`, test mọi nhánh trạng thái và null-safe logic.
11. Nếu Spring MVC exception type đổi, kiểm direct method constraints và class-level `@Validated`.
12. Nếu custom validator phụ thuộc service/data access, test cả việc gọi được, không chỉ Spring Bean metadata.
13. Nếu message bị thiếu, tách test i18n/MessageSource khỏi test group activation.
14. Không dựa vào iteration order của `Set<ConstraintViolation<?>>`.
15. Nếu bật fail-fast, đừng giả định mỗi nhóm thu đủ tất cả violations.
16. Với form/JSON có conversion errors, test parse/binding riêng.
17. Nếu có validation groups cho draft/final, test mỗi endpoint theo đúng nhóm nghiệp vụ.
18. Đảm bảo lỗi validation không tạo side effect (ghi DB, gửi event, kích hoạt workflow).
19. Không coi validation group là authorization group; test quyền trong security/service.
20. Có một unit test cố ý tạo Default redefinition sai để nhóm học biết nhận diện `GroupDefinitionException`.

## 18. Bài tập thực hành

**Bài 1 — Default và Final.** Có `@NotBlank(groups=FinalChecks.class)` trên `approvalCode`. Gọi `validator.validate(bean)` với approvalCode rỗng; giải thích vì sao không có violation. Viết test gọi `validator.validate(bean,FinalChecks.class)`.

**Bài 2 — Short-circuit.** Dùng `@GroupSequence({Default,BusinessChecks,FinalChecks})` trên interface. Tạo bean có lỗi ở cả ba nhóm; xác minh chỉ nhóm đầu được báo. Sau khi sửa lỗi Default, nhóm nào được báo tiếp?

**Bài 3 — Sai kiểu GroupSequence.** Đặt `@GroupSequence({Default.class, BusinessChecks.class})` trên class bean. Dự đoán exception và sửa bằng cách thay `Default.class` thành class bean.

**Bài 4 — Group inheritance.** Tạo `PremiumBusinessChecks extends BusinessChecks`. Constraint thuộc BusinessChecks có được chạy khi chỉ yêu cầu PremiumBusinessChecks không? Default có được tự thêm không?

**Bài 5 — Nested cascade.** Bỏ `@Valid` khỏi `Address` trong RegistrationRequest. Vì sao `address.zipCode` biến mất khỏi lỗi BusinessChecks? Viết test chứng minh.

**Bài 6 — ConvertGroup.** Gắn `@ConvertGroup(from=Default.class,to=AddressReview.class)` cho nested Address. Gửi city="", districtCode="" và validate Default; đường lỗi nào còn xuất hiện?

**Bài 7 — Spring MVC.** Đổi endpoint từ `@Validated(OrderedChecks.class)` về `@Valid`. Với companyCode rỗng nhưng Default hợp lệ, HTTP status đổi thế nào? Vì sao?

**Bài 8 — Không có thứ tự.** Thay sequence bằng `@Validated({Default.class,BusinessChecks.class,FinalChecks.class})`. Viết test assert tập paths, không assert order.

**Bài 9 — Native method validation.** Thêm `@Min(1)` trên một `@RequestParam` ở Spring MVC 6.1+. Dự đoán khi nào `HandlerMethodValidationException` thay thế `MethodArgumentNotValidException`.

**Bài 10 — Service AOP.** Service gắn `@Validated` tự gọi `this.submit(...)`. Viết test gọi qua proxy so với gọi nội bộ, giải thích self-invocation và cách tổ chức boundary hợp lệ.

**Bài 11 — Hibernate extension.** Dùng `@GroupSequenceProvider` cho trạng thái Draft và Final. Hãy kiểm provider null-safe và tránh dựa vào client-controlled flag để phân quyền.

**Bài 12 — API contract.** Thiết kế response JSON gồm `field`, `code` và group diagnostic chỉ cho logs/test; không lộ rejectedValue. Viết test lỗi Default/Business/Final ở từng stage.

## Kết luận

Khi gặp hiện tượng “nhóm không chạy”, hãy đối chiếu **nhóm yêu cầu → sequence → cascade/conversion → Spring validation entry point**:

~~~text
@Valid hoặc Validator.validate(bean)
        |
        v
Default (trừ khi class định nghĩa lại Default)
        |
        +-- Có @GroupSequence trên interface?
        |      Phải gọi chính sequence interface.
        |
        +-- Có class-level @GroupSequence?
        |      Phải chứa chính class, không dùng Default.class.
        |
        +-- Có lỗi ở nhóm trước?
        |      Sequence STOP; nhóm sau không chạy là đúng.
        |
        +-- Có nested @Valid?
        |      Nhóm được propagate, có thể bị @ConvertGroup đổi.
        |
        +-- Có @Validated ở Spring boundary?
               Kiểm hints/method validation/AOP proxy.
~~~

**Ba điều cần nhớ:** `@Valid` mặc định không tự chạy mọi nhóm; `@GroupSequence` cho phép thứ tự **và dừng khi một nhóm thất bại**; `@GroupSequence` trên **class** phải chứa chính class để định nghĩa lại Default. Các test trực tiếp bằng `jakarta.validation.Validator` kết hợp MockMvc và metadata descriptors sẽ giúp bạn phân biệt một nhóm thực sự không được yêu cầu, bị short-circuit hợp lệ, bị đổi qua cascade, hay hoàn toàn chưa có validation ở Spring boundary.

## Tài liệu tham khảo

- [Jakarta Bean Validation 3.0 — Specification](https://jakarta.ee/specifications/bean-validation/3.0/)
- [Hibernate Validator 8 — Reference Guide, Chapter 5 Validation groups](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/#chapter-groups)
- [Spring Framework 6.2 — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — MVC Validation Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html)
- [Spring Framework 6.2 — @Validated Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/annotation/Validated.html)
- [Spring Framework 6.2 — Java Bean Validation Integration](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
- [Spring Framework 6.2 — MethodArgumentNotValidException API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/bind/MethodArgumentNotValidException.html)
- [Jakarta Validation — ConstraintDescriptor API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/metadata/ConstraintDescriptor.html)
