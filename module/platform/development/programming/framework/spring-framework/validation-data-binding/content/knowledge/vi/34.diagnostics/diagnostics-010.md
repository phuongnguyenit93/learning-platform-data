# Dữ liệu đã gắn một phần khi còn lỗi và cách ngăn dùng tiếp trong Spring MVC

Trong Spring MVC, **data binding không phải một giao dịch all-or-nothing**. Khi `WebDataBinder` nhận nhiều request parameters, một số property có thể đã được gán thành công vào JavaBean trước khi một property khác gặp lỗi chuyển kiểu hoặc validation. Vì vậy, việc `BindingResult.hasErrors()==true` **không đồng nghĩa target object chưa hề bị thay đổi**.

Ví dụ form gửi:

~~~http
POST /api/reservations HTTP/1.1
Content-Type: application/x-www-form-urlencoded

guestName=Lan&seats=abc&contactEmail=lan%40example.org
~~~

Với JavaBean có `String guestName`, `Integer seats` và `String contactEmail`, binder có thể:

- Gắn thành công `guestName = "Lan"`.
- Gắn thành công `contactEmail = "lan@example.org"`.
- Không chuyển được chuỗi `"abc"` thành `Integer seats`, ghi một `FieldError` mã `typeMismatch` vào `BindingResult`.
- Để `seats` giữ giá trị ban đầu, ví dụ `null` nếu đó là form mới.
- Vẫn chuyển JavaBean và `BindingResult` đến handler **nếu handler khai báo `BindingResult` đúng vị trí và lỗi có thể được xử lý cục bộ**.

**Rủi ro:** code phía sau thấy `guestName` đã có giá trị, cho rằng form “đã được xử lý”, rồi gọi service, cập nhật entity, lưu DB, gửi thông báo hoặc tính phí **dù dữ liệu còn lỗi**. Lúc này một phần input đã được chấp nhận về mặt kỹ thuật nhưng toàn bộ request **chưa hợp lệ về nghiệp vụ**.

Bài học thuộc nhóm **Chẩn đoán** của module **Spring Framework — validation-data-binding**. Mục tiêu là hiểu chính xác cơ chế **partial binding**, phân biệt **binding errors** với **validation errors**, không nhầm dữ liệu đã gắn với dữ liệu hợp lệ, và thiết kế “validation gate” để **chỉ gọi nghiệp vụ sau khi mọi lỗi đã được xử lý**.

Ví dụ dùng **Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, Spring MVC Servlet, Jakarta Bean Validation và JUnit 5/MockMvc**.

## 1. Ba trạng thái không được đánh đồng

Trong một request handler có form JavaBean, cần phân biệt:

1. **Dữ liệu đã được gắn (bound)**: binder đã ghi một số property vào target object; có thể còn property không chuyển kiểu được.
2. **Dữ liệu đã qua validation**: constraints như `@NotBlank`, `@Min` và cross-field rules đã được đánh giá, với mọi errors nằm trong `BindingResult` hoặc bị framework ném exception.
3. **Dữ liệu được phép sử dụng (accepted for business action)**: cả binding, validation, allowlist, authorization và các điều kiện nghiệp vụ liên quan đều thành công.

Việc đạt (1) **không đảm bảo** đạt (2) hoặc (3). Việc đạt (2) cũng **không thay thế** authorization, uniqueness checks, transaction integrity và những domain invariants khác.

~~~text
HTTP form/query parameters
          |
          v
@ModelAttribute / WebDataBinder
          |
          +-- Property A chuyển kiểu được -> setter A chạy
          +-- Property B chuyển kiểu được -> setter B chạy
          +-- Property C chuyển kiểu lỗi -> FieldError(typeMismatch)
          +-- Property D không được phép -> suppressed field
          |
          v
Bean Validation @Valid (nếu được kích hoạt)
          |
          +-- FieldError / ObjectError được thêm
          |
          v
BindingResult
          |
          +-- hasErrors() == true? ----- Yes ----> 400 / form view
          |                                     KHÔNG gọi service
          |
          +-- getSuppressedFields() không rỗng?
          |                         ----- Yes ----> Reject theo policy
          |
          v
Chuyển sang immutable command/snapshot
          |
          v
Authorization + domain checks
          |
          v
Service / transaction / repository / notification
~~~

**Chốt quan trọng:** chặn ở handler trước khi gọi service chỉ bảo đảm **không tiếp tục các thao tác downstream**. Nó **không tự hoàn tác** việc các setters đã chạy trên target trong bước binding. Vì thế phải chọn target là **DTO dành riêng cho request**, không phải một entity/đối tượng session nhạy cảm đang được quản lý với side effects.

## 2. Binding error và validation error khác nhau

| Khía cạnh | Binding error | Validation error |
|---|---|---|
| Xảy ra khi nào | Đọc/gắn input vào property, đặc biệt khi conversion | Sau khi có object/giá trị phù hợp để kiểm tra rule |
| Ví dụ | `"abc"` → `Integer seats` thất bại | `seats=0` vi phạm `@Min(1)` |
| Nơi lưu trong MVC form | `BindingResult` | Cũng là `BindingResult` nếu xử lý cục bộ |
| Lớp lỗi thường gặp | `FieldError` | `FieldError` hoặc `ObjectError` |
| Error code thường thấy | `typeMismatch` | `NotBlank`, `Min`, custom code |
| `FieldError.isBindingFailure()` | Thường `true` | Thường `false` |
| Giá trị target | Field lỗi có thể còn giá trị cũ/null | Đã convert thành Java type, nhưng không đạt rule |
| Rejected value | Thường là chuỗi raw từ request | Thường là Java value vi phạm |
| Có gọi service không? | Không, khi policy chặn | Không, khi policy chặn |

Cả hai nguồn lỗi đều có thể cùng xuất hiện trong **một request**. Một field hợp lệ có thể được gắn và một field khác bị từ chối. Vì thế `getFieldErrorCount()` là số error entries, không phải số property chưa từng được gắn.

### Ví dụ trạng thái cụ thể

Giả sử trước bind:

~~~text
ReservationForm:
  guestName    = null
  seats        = null
  contactEmail = null
~~~

Sau bind request `guestName=Lan&seats=abc&contactEmail=lan@example.org`:

~~~text
ReservationForm:
  guestName    = "Lan"              <- đã gắn
  seats        = null               <- conversion thất bại
  contactEmail = "lan@example.org"  <- đã gắn

BindingResult:
  FieldError(
    field = "seats",
    code = "typeMismatch",
    bindingFailure = true,
    rejectedValue = "abc"
  )
~~~

Nếu lập trình viên chỉ log `form.getGuestName()`, sẽ thấy dữ liệu như có vẻ đã được nhận. Nhưng nếu `errors.hasErrors()` true, toàn bộ request **chưa được phép tạo reservation**.

## 3. `DataBinder.bind(...)` là mutate-in-place, không phải transactional rollback

Spring `org.springframework.validation.DataBinder` nhận target và bind `PropertyValues`. Với **property binding**, các property được gán khi conversion và property access thành công. Khi một phần gặp lỗi, kết quả có thể chứa các giá trị đã gắn thành công **cùng với lỗi**.

Snippet đơn giản:

~~~java
ReservationForm form = new ReservationForm();

DataBinder binder =
    new DataBinder(form, "reservationForm");

MutablePropertyValues values =
    new MutablePropertyValues();

values.add("guestName", "Lan");
values.add("seats", "abc");
values.add("contactEmail", "lan@example.org");

binder.bind(values);

BindingResult errors = binder.getBindingResult();
~~~

Đây là snippet, những class hoàn chỉnh có ở phần thực hành. **`binder.bind(...)` không tự chạy tất cả Jakarta `@NotBlank`/`@Min`**. Nếu dùng DataBinder thủ công và muốn chạy Spring `Validator`, phải đăng ký validator rồi gọi `binder.validate()`.

Mô hình cần ghi nhớ:

~~~text
bind(PropertyValues)
   |
   +-- convert + set được từng property
   +-- collect binding failures
   |
   v
BindingResult
   |
   +-- getTarget()
   +-- getFieldErrors()
   +-- getSuppressedFields()
   +-- hasErrors()
~~~

### Binding result không phải bản copy an toàn của target

`BindingResult.getTarget()` có thể trả chính object mà binder đang thao tác. Khi target mutable, việc đọc lại target sau lỗi không cho phép suy ra đây là snapshot của một “lệnh giao dịch” đã được chấp nhận.

Nếu muốn cập nhật domain data, hãy tạo **command mới** chỉ sau khi errors và policies đã được kiểm tra; không chuyển thẳng reference của binding target vào repository.

## 4. Cách đọc `BindingResult` để biết chuyện gì đã xảy ra

Các API đáng dùng:

| API | Ý nghĩa |
|---|---|
| `hasErrors()` | Có ít nhất một binding hoặc validation error |
| `getErrorCount()` | Tổng số error entries |
| `getFieldErrorCount()` | Số field error entries |
| `getGlobalErrorCount()` | Số lỗi toàn object |
| `getFieldError("seats")` | Một lỗi đầu tiên liên quan field `seats` |
| `getFieldErrors("seats")` | Mọi lỗi của field `seats` |
| `getFieldErrors()` | Tất cả field errors |
| `getGlobalErrors()` | Các lỗi không gắn riêng một field |
| `getAllErrors()` | Field + global errors |
| `getSuppressedFields()` | Tên những field bị chặn khỏi binding |
| `getTarget()` | Object target |
| `getObjectName()` | Tên model object dùng cho message resolution |
| `getFieldValue("seats")` | Giá trị hiển thị/rejected value theo semantics BindingResult |
| `getFieldType("seats")` | Type property được biết |
| `resolveMessageCodes(...)` | Các mã thông báo để `MessageSource` lựa chọn |

Mẫu kiểm tra một conversion failure:

~~~java
FieldError issue = errors.getFieldError("seats");

assertNotNull(issue);
assertEquals("seats", issue.getField());
assertEquals("typeMismatch", issue.getCode());
assertTrue(issue.isBindingFailure());
assertEquals("abc", issue.getRejectedValue());
~~~

Đây là snippet trong test đã có `errors`, dùng assertions của JUnit. `getCode()` thường là mã gốc cuối cùng trong `getCodes()`; mã cụ thể có thể mang thêm tên object/field/type, ví dụ `typeMismatch.reservationForm.seats`.

**Không nên serialize `FieldError.getRejectedValue()` ra client.** Với field chứa password, token, nội dung biểu mẫu riêng tư hoặc input cực dài, rejected value có thể gây rò rỉ hoặc làm response/log quá lớn. Ví dụ test dùng `"abc"` là dữ liệu giả an toàn.

### Cẩn thận với `getFieldValue(...)`

`BindingResult.getFieldValue("seats")` có thể ưu tiên giá trị bị từ chối nhằm giúp web form hiển thị input cũ. Nó **không nhất thiết** bằng `form.getSeats()` sau một conversion failure. Muốn biết JavaBean thực sự có giá trị gì, đọc getter của form; muốn hiển thị rejected input theo policy, dùng cơ chế view/binding result thích hợp và escape output.

## 5. `@ModelAttribute` và `BindingResult` ngay sau tham số

Spring MVC handler:

~~~java
@PostMapping("/reservations")
public ResponseEntity<?> create(
        @Valid @ModelAttribute("reservationForm")
        ReservationForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().build();
    }

    return ResponseEntity.ok().build();
}
~~~

**`BindingResult` phải đứng ngay sau argument liên quan.** Framework có thể truyền form và errors đến method, cho phép xử lý validation/binding errors cục bộ. Đây là lý do một handler vẫn có thể **được gọi dù form đang sai**.

Nếu không nhận `BindingResult` và lỗi không thể được xử lý cục bộ, Spring MVC thường ném `MethodArgumentNotValidException` cho lỗi validation/binding đối với model attribute được validate. Chính xác kiểu lỗi và đường xử lý phụ thuộc handler signature và các direct method constraints.

### Quy tắc chặn trước business call

~~~java
if (errors.hasErrors()) {
    return invalidResponse(errors);
}

// Chỉ đến đây nếu không có binding/validation errors.
service.create(toCommand(form));
~~~

Phải kiểm tra **trước** bất kỳ thao tác có side effect. Nếu bạn gọi `service.create(...)` rồi mới `errors.hasErrors()`, việc “trả 400 ở cuối” có thể đến quá muộn.

### Chỉ kiểm tra `hasErrors()` có đủ không?

Chưa chắc. `DataBinder` hỗ trợ **allowlist** và ghi các trường không được phép vào `getSuppressedFields()`. Các suppressed fields **không mặc nhiên được tính như FieldError**. Nếu chính sách bảo mật quy định request không được chứa field ngoài allowlist, phải kiểm tra **cả**:

~~~java
if (errors.getSuppressedFields().length > 0) {
    return rejectUnexpectedFields();
}
if (errors.hasErrors()) {
    return rejectBindingOrValidationErrors();
}
~~~

Hai nhánh này nên nằm trước service call. Có hệ thống chỉ im lặng bỏ qua field lạ; điều đó có thể hợp lý theo contract, nhưng phải là quyết định có chủ đích, không giả định `hasErrors()` sẽ luôn phản ánh suppressed fields.

## 6. Partial binding không có nghĩa một transaction DB đã chạy

Cần tách **in-memory mutation** và **database transaction**:

- `WebDataBinder` có thể đã gọi setter trên JavaBean trước khi tìm thấy conversion failure.
- `BindingResult` ghi nhận lỗi. Nó không phải transactional undo log.
- `@Transactional` ở service có thể rollback DB changes trong một số điều kiện, nhưng **không tự đảo ngược mọi thay đổi đã có trên object trong heap**.
- Nếu binder nhắm tới một **JPA managed entity**, việc thay đổi property có thể trở thành dirty state, rồi được flush trong transaction ở thời điểm không mong muốn.
- Nếu setter có side effect (gọi service, event publishing), việc bind đã gây tác động **trước khi bạn kiểm tra errors**.
- Nếu `@ModelAttribute` lấy object từ `@SessionAttributes`, một object đã có sẵn trong session có thể bị mutate dù input tổng thể sai.
- Một object dùng chung ngoài request hoặc stored in session có thể còn giữ state một phần nếu không được quản lý cẩn thận.

**Vì vậy cách phòng ngừa mạnh nhất là:** bind vào **DTO không có side effect**, dùng allowlist hoặc constructor binding, chặn errors, sau đó tạo một command immutable chuyển vào service. Không cố “rollback binding” bằng cách gọi setters thêm lần nữa trên entity.

## 7. Vì sao bind trực tiếp JPA entity là nguy hiểm?

Phản ví dụ:

~~~java
@PostMapping("/accounts/{id}")
public String update(
        @ModelAttribute AccountEntity entity,
        BindingResult errors) {

    repository.save(entity);
    if (errors.hasErrors()) {
        return "error";
    }
    return "ok";
}
~~~

Đây là **phản ví dụ**, không dùng trong sản phẩm. Nó có nhiều vấn đề:

- Repository được gọi **trước** kiểm tra errors.
- Form có thể bind các field ngoài ý muốn nếu entity có public setters.
- Entity có thể chứa `role`, `ownerId`, `balance`, `isAdmin` hoặc foreign key không được phép sửa.
- Một conversion failure không đảm bảo các property khác chưa đổi.
- Một entity có thể được quản lý bởi persistence context, khiến dirty checking tạo side effects.
- Thiếu authorization kiểm tra quyền sửa entity cụ thể.

**Mô hình tốt hơn:**

~~~text
HTTP input
  -> Create/UpdateForm DTO chỉ gồm fields được nhận
  -> allowedFields / constructor binding
  -> bind + validate
  -> reject nếu lỗi
  -> authenticate + authorize
  -> map thành immutable command
  -> service load entity, verify invariants
  -> update authorized fields trong transaction
  -> commit
~~~

Không cần serialize entity từ trực tiếp từ request; domain entity không nên bị gắn request fields ngoài ý định.

## 8. Giới hạn thuộc tính được bind bằng `@InitBinder`

Một controller có thể giới hạn property binding:

~~~java
@InitBinder("reservationForm")
void initReservationBinder(WebDataBinder binder) {
    binder.setAllowedFields(
        "guestName",
        "seats",
        "contactEmail");
    binder.setAutoGrowCollectionLimit(32);
}
~~~

Những điểm chính:

- `setAllowedFields(...)` xác định các field names được phép gắn qua **property binding**.
- Các property không được allowlist có thể xuất hiện trong `BindingResult.getSuppressedFields()`.
- `setAutoGrowCollectionLimit(32)` hạn chế auto-grow collection khi property binder gặp indices, **không** phải giới hạn JSON body bytes.
- `@InitBinder("reservationForm")` áp dụng cho tên model attribute tương ứng, không tự động mọi attribute khác.
- Cần test đúng tên `"reservationForm"` vì nếu handler dùng tên khác, binder configuration scoped có thể không chạy như dự kiến.

Spring khuyến nghị dùng **dedicated form/DTO** và nếu property binding là cần thiết, dùng **allowed fields** thay vì chỉ dùng danh sách cấm. Blacklist có thể quên field mới sau khi object được mở rộng.

### `setDeclarativeBinding(true)` trong Spring 6.1+

Spring `DataBinder` hỗ trợ:

~~~java
binder.setDeclarativeBinding(true);
~~~

Chế độ này ưu tiên **constructor binding**, không cho property binding tràn lan nếu chưa khai báo `allowedFields` phù hợp. Nó có ích với immutable DTO/constructor parameters. Tuy nhiên cần kiểm tra thực tế command object, Spring version, tên constructor parameters và cách chuyển đổi; đừng bật toàn cục mà không có integration tests.

**Lưu ý:** allowlist kiểm soát field nào có thể gắn, không tự chứng minh giá trị của field đó hợp lệ. Vì vậy vẫn cần `@Valid`/`@Validated` và domain checks.

## 9. `@RequestBody` JSON khác `@ModelAttribute` form

Phân biệt hai pipeline:

### Form/query với `@ModelAttribute`

~~~text
Request parameters
  -> WebDataBinder property/constructor binding
  -> BindingResult: conversion + validation errors
  -> Handler (khi có Errors/BindingResult phù hợp)
~~~

Đường này minh họa rõ **partial binding** vì setters thành công có thể đã chạy trong khi các setters khác thất bại.

### JSON với `@RequestBody`

~~~text
JSON bytes
  -> HttpMessageConverter / Jackson
  -> DTO
  -> validation nếu @Valid/@Validated
  -> Handler hoặc exception
~~~

Khi JSON sai cú pháp hoặc không thể decode, Jackson/Spring có thể ném `HttpMessageNotReadableException` trước khi có argument hợp lệ đến handler. **Không khẳng định** rằng mọi JSON parse failure sẽ tạo `BindingResult` chứa partial properties và handler vẫn chạy.

Với JSON parse thành công nhưng DTO vi phạm `@Valid`, Spring MVC thường ném `MethodArgumentNotValidException` nếu không có `Errors`/`BindingResult` ngay sau argument. Khi có `BindingResult` tại đúng vị trí, handler có thể xử lý validation errors cục bộ, tùy hình thức method validation và signatures.

Đối với JSON, tốt nhất vẫn là tạo **request DTO**, validate trước business và không để deserializer bind trực tiếp managed entity.

## 10. Ví dụ chạy được: Spring Boot 3.5 và Java 17+

Ứng dụng mẫu có một endpoint `POST /api/reservations` nhận `application/x-www-form-urlencoded`. Nó minh họa đúng vấn đề:

- JavaBean `ReservationForm` có fields `guestName`, `seats`, `contactEmail` và một field `vip` chỉ để mô phỏng mass assignment.
- `@InitBinder` chỉ cho phép ba field đầu, không cho phép gắn `vip`.
- `@Valid` chạy Jakarta Bean Validation trên bean.
- Handler kiểm tra **suppressed fields** và **BindingResult errors** trước khi gọi `ReservationService`.
- Sau khi hợp lệ, handler tạo immutable `ReservationService.Command` và mới gọi service.
- Error response chỉ đưa tên field, error code và cờ binding failure; **không trả rejected values**.
- Tests chứng minh các property hợp lệ đã có thể được gắn dù một field bị type mismatch và chứng minh service **không được gọi** ở request lỗi.

Project theo Spring Boot **3.5.x**, JDK 17+, starter Web/Validation/Test. Tất cả Java classes ở package `com.example.partialbinding`.

### 10.1. Gradle dependencies

Trong project đã có Spring Boot Gradle plugin và dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Starter Web cung cấp Spring MVC/Servlet, starter Validation cung cấp Jakarta provider, starter Test cung cấp JUnit 5, MockMvc và Mockito. Với Spring Boot 3.5/Spring Framework 6.2, `@MockitoBean` nằm trong `org.springframework.test.context.bean.override.mockito`.

Nếu project chạy Spring Boot 4 hoặc framework đời khác, hãy đối chiếu module dependencies/API mới trước khi sao chép nguyên ví dụ.

### 10.2. `PartialBindingApplication.java`

`src/main/java/com/example/partialbinding/PartialBindingApplication.java`:

~~~java
package com.example.partialbinding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PartialBindingApplication {

    public static void main(String[] args) {
        SpringApplication.run(PartialBindingApplication.class, args);
    }
}
~~~

### 10.3. `ReservationForm.java`

`src/main/java/com/example/partialbinding/ReservationForm.java`:

~~~java
package com.example.partialbinding;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class ReservationForm {

    @NotBlank
    private String guestName;

    @NotNull
    @Min(1)
    private Integer seats;

    @NotBlank
    @Email
    private String contactEmail;

    // Để minh họa nguy cơ mass assignment.
    // Không thuộc các trường client được phép thiết lập.
    private boolean vip;

    public ReservationForm() {
    }

    public String getGuestName() {
        return guestName;
    }

    public void setGuestName(String guestName) {
        this.guestName = guestName;
    }

    public Integer getSeats() {
        return seats;
    }

    public void setSeats(Integer seats) {
        this.seats = seats;
    }

    public String getContactEmail() {
        return contactEmail;
    }

    public void setContactEmail(String contactEmail) {
        this.contactEmail = contactEmail;
    }

    public boolean isVip() {
        return vip;
    }

    public void setVip(boolean vip) {
        this.vip = vip;
    }
}
~~~

`vip` tồn tại và có public setter chỉ để kiểm thử allowlist; production DTO lý tưởng **không nên chứa một field không được phép khách hàng sửa**. Ví dụ vẫn có nó để bạn nhìn rõ sự khác nhau giữa object writable và field allowed for binding.

`@NotNull @Min(1)` đảm bảo `seats` không được null và phải tối thiểu là 1; `@Min` riêng không tự từ chối null. `@NotBlank @Email` yêu cầu email có nội dung và format cơ bản; `@Email` không phải bằng chứng email đã được xác minh quyền sở hữu.

### 10.4. `ReservationService.java`

`src/main/java/com/example/partialbinding/ReservationService.java`:

~~~java
package com.example.partialbinding;

import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

@Service
public class ReservationService {

    private final AtomicLong sequence = new AtomicLong();

    public Receipt create(Command command) {
        long id = sequence.incrementAndGet();

        // Thay cho persistence thật trong bài tập.
        return new Receipt(
            id, command.guestName(), command.seats());
    }

    public record Command(
        String guestName,
        int seats,
        String contactEmail
    ) {
    }

    public record Receipt(
        long id,
        String guestName,
        int seats
    ) {
    }
}
~~~

`Command` immutable record, chỉ gồm **ba fields được chấp nhận**. Service có một counter in-memory mô phỏng thay đổi state; ở production có thể là insert DB/emit event. Điều quan trọng không phải persistence cụ thể mà là **không gọi `create` khi BindingResult còn lỗi**.

### 10.5. `ReservationController.java`

`src/main/java/com/example/partialbinding/ReservationController.java`:

~~~java
package com.example.partialbinding;

import java.util.ArrayList;
import java.util.List;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/reservations")
public class ReservationController {

    private final ReservationService service;

    public ReservationController(ReservationService service) {
        this.service = service;
    }

    @InitBinder("reservationForm")
    void configureBinding(WebDataBinder binder) {
        binder.setAllowedFields(
            "guestName", "seats", "contactEmail");
        binder.setAutoGrowCollectionLimit(32);
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<?> create(
            @Valid @ModelAttribute("reservationForm")
            ReservationForm form,
            BindingResult errors) {

        // Các field bị chặn không nhất thiết tăng hasErrors().
        if (errors.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest()
                .body(new Problem(
                    "UNEXPECTED_FIELDS", List.of()));
        }

        // Chặn trước mọi lời gọi service.
        if (errors.hasErrors()) {
            List<Issue> issues = new ArrayList<>();

            for (FieldError field : errors.getFieldErrors()) {
                issues.add(new Issue(
                    field.getField(),
                    field.getCode(),
                    field.isBindingFailure()));
            }

            for (ObjectError global : errors.getGlobalErrors()) {
                issues.add(new Issue(
                    "$object",
                    global.getCode(),
                    false));
            }

            return ResponseEntity.badRequest()
                .body(new Problem(
                    "INVALID_RESERVATION", issues));
        }

        ReservationService.Command command =
            new ReservationService.Command(
                form.getGuestName(),
                form.getSeats(),
                form.getContactEmail());

        ReservationService.Receipt receipt =
            service.create(command);

        return ResponseEntity.status(HttpStatus.CREATED)
            .body(receipt);
    }

    public record Problem(
        String code,
        List<Issue> issues
    ) {
    }

    public record Issue(
        String field,
        String code,
        boolean bindingFailure
    ) {
    }
}
~~~

**Đây là complete class** cho Spring MVC 6.2 trong project nêu trên. Các điểm đáng chú ý:

1. `BindingResult` nằm **ngay sau** `@Valid @ModelAttribute("reservationForm") ReservationForm`.
2. `@InitBinder("reservationForm")` áp dụng allowlist cho đúng object name.
3. `getSuppressedFields()` được kiểm tra riêng với `hasErrors()`; client gửi `vip=true` sẽ bị từ chối theo policy của demo.
4. Nhánh lỗi trả **400** rồi thoát ngay, không gọi `service.create(...)`.
5. `FieldError.isBindingFailure()` phân biệt conversion errors với constraint violations; trường hợp có nhiều errors trên cùng field vẫn giữ tất cả.
6. Các lỗi toàn object được đưa vào `"$object"` theo schema riêng của demo. Trong sản phẩm, nên đặt scope riêng thay vì lạm dụng field path giả.
7. Không đưa `getRejectedValue()` hoặc target object vào response.
8. Dữ liệu được chuyển thành immutable `Command` **chỉ ở nhánh thành công**, sau khi đã qua validation gate.
9. Việc `form.getSeats()` unbox từ Integer thành int chỉ an toàn ở đây vì `@NotNull` chạy và errors đã được chặn; nếu thay cấu hình validator, có thể cần thêm domain assertions trong service.
10. Nếu form binding target có setter độc hại, validation gate vẫn đến quá muộn để undo setter đó; vì vậy DTO phải không có side effects.

### 10.6. Chạy thử

Tại root project có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Form hợp lệ:

~~~bash
curl -i -X POST \
  "http://localhost:8080/api/reservations" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "guestName=Lan" \
  --data-urlencode "seats=2" \
  --data-urlencode "contactEmail=lan@example.org"
~~~

Kỳ vọng HTTP **201 Created**, body với ID tăng từ 1 trong một instance mới chưa nhận request nào khác:

~~~json
{
  "id": 1,
  "guestName": "Lan",
  "seats": 2
}
~~~

Với server đang chạy lâu, ID có thể khác vì `AtomicLong` tăng; **đừng hard-code 1 trong integration test cần chạy độc lập**.

Form bị conversion failure:

~~~bash
curl -i -X POST \
  "http://localhost:8080/api/reservations" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "guestName=Lan" \
  --data-urlencode "seats=abc" \
  --data-urlencode "contactEmail=lan@example.org"
~~~

Kỳ vọng HTTP **400 Bad Request**. Response có thể có nhiều issues nếu Jakarta validation cũng ghi lỗi `@NotNull` khi field không thể convert; vì vậy không nên ép số lượng issue bằng 1. Một mục quan trọng là:

~~~json
{
  "field": "seats",
  "code": "typeMismatch",
  "bindingFailure": true
}
~~~

Ví dụ trên là **một phần tử trong `issues[]`**, không phải toàn bộ response. Đồng thời `guestName` và `contactEmail` có thể đã được gắn thành công trên JavaBean; handler chặn trước khi gọi service.

Form hợp lệ về ba field nhưng cố set `vip`:

~~~bash
curl -i -X POST \
  "http://localhost:8080/api/reservations" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "guestName=Lan" \
  --data-urlencode "seats=2" \
  --data-urlencode "contactEmail=lan@example.org" \
  --data-urlencode "vip=true"
~~~

Kỳ vọng HTTP **400** và:

~~~json
{
  "code": "UNEXPECTED_FIELDS",
  "issues": []
}
~~~

Chú ý: `vip` bị chặn **không phải bằng `@Min` hoặc `@NotBlank`** mà bằng allowlist. Nếu bạn chỉ kiểm tra `hasErrors()` mà không kiểm tra suppressed fields, request vẫn có thể bị coi là hợp lệ dù chứa field không được phép; demo chọn chính sách từ chối.

## 11. Unit test DataBinder: chứng minh dữ liệu đã gắn một phần

Unit test này không gửi HTTP request, chỉ dùng Spring `DataBinder` và JavaBean. Nhờ vậy, nó chứng minh trực tiếp sự khác nhau giữa **trạng thái Java object** và **BindingResult**.

`src/test/java/com/example/partialbinding/PartialBindingDataBinderTest.java`:

~~~java
package com.example.partialbinding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PartialBindingDataBinderTest {

    private static DataBinder newBinder(ReservationForm form) {
        DataBinder binder =
            new DataBinder(form, "reservationForm");
        binder.setAllowedFields(
            "guestName", "seats", "contactEmail");
        return binder;
    }

    @Test
    void validFieldsAreAppliedEvenWhenSeatsCannotConvert() {
        ReservationForm form = new ReservationForm();
        DataBinder binder = newBinder(form);

        MutablePropertyValues input =
            new MutablePropertyValues();
        input.add("guestName", "Lan");
        input.add("seats", "abc");
        input.add("contactEmail", "lan@example.org");

        binder.bind(input);

        BindingResult errors = binder.getBindingResult();
        FieldError badSeats = errors.getFieldError("seats");

        // Các property khác vẫn đã được set thành công.
        assertEquals("Lan", form.getGuestName());
        assertEquals(
            "lan@example.org", form.getContactEmail());

        // Conversion failure không biến "abc" thành Integer.
        assertNull(form.getSeats());
        assertTrue(errors.hasFieldErrors("seats"));

        assertNotNull(badSeats);
        assertTrue(badSeats.isBindingFailure());
        assertEquals("typeMismatch", badSeats.getCode());
        assertEquals("abc", badSeats.getRejectedValue());
        assertEquals("reservationForm",
            errors.getObjectName());
    }

    @Test
    void deniedVipFieldIsSuppressedNotApplied() {
        ReservationForm form = new ReservationForm();
        DataBinder binder = newBinder(form);

        MutablePropertyValues input =
            new MutablePropertyValues();
        input.add("guestName", "Lan");
        input.add("seats", "2");
        input.add("contactEmail", "lan@example.org");
        input.add("vip", "true");

        binder.bind(input);

        BindingResult errors = binder.getBindingResult();

        assertFalse(form.isVip());
        assertEquals("Lan", form.getGuestName());
        assertEquals(2, form.getSeats());
        assertArrayEquals(
            new String[] {"vip"},
            errors.getSuppressedFields());

        // Suppression là cơ chế riêng, không mặc định FieldError.
        assertFalse(errors.hasErrors());
    }

    @Test
    void bindWithoutValidationDoesNotRunNotBlank() {
        ReservationForm form = new ReservationForm();
        DataBinder binder = newBinder(form);

        MutablePropertyValues input =
            new MutablePropertyValues();
        input.add("guestName", " ");
        input.add("seats", "2");
        input.add("contactEmail", "lan@example.org");

        binder.bind(input);

        assertEquals(" ", form.getGuestName());

        // Chỉ bind() không tự gọi Bean Validation annotations.
        assertFalse(binder.getBindingResult().hasErrors());
    }

    @Test
    void noValuesDoesNotInitializeFields() {
        ReservationForm form = new ReservationForm();
        DataBinder binder = newBinder(form);

        binder.bind(new MutablePropertyValues());

        assertNull(form.getGuestName());
        assertNull(form.getSeats());
        assertNull(form.getContactEmail());

        // Chưa chạy Bean Validation, dù @NotBlank/@NotNull sai.
        assertFalse(binder.getBindingResult().hasErrors());
    }
}
~~~

**Bốn tests** xác nhận được:

- JavaBean **thật sự đã đổi một phần** khi có lỗi conversion.
- `getRejectedValue()` là raw `"abc"`, trong khi getter `form.getSeats()` vẫn null.
- Một field có public setter nhưng không nằm trong allowlist bị suppressed.
- Suppressed field **không mặc định tăng `hasErrors()`**, nên security policy phải kiểm tra riêng nếu muốn reject.
- `DataBinder.bind(...)` thủ công không đồng nghĩa gọi Jakarta Bean Validation.

Những tests này dùng JUnit, Spring DataBinder và JavaBean, **không cần Spring Boot application context**.

## 12. MockMvc test: đảm bảo service không được gọi khi còn lỗi

Unit test DataBinder chứng minh partial binding; còn MockMvc kiểm tra **handler có chặn business action không**.

Dùng `@WebMvcTest(ReservationController.class)` để nạp Spring MVC slice và `@MockitoBean` để thay service bằng Mockito mock. Vì thế có thể dùng `verifyNoInteractions(service)` nhằm chứng minh request không chạm vào service.

`src/test/java/com/example/partialbinding/ReservationControllerTest.java`:

~~~java
package com.example.partialbinding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItem;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ReservationController.class)
class ReservationControllerTest {

    @Autowired
    private MockMvc mvc;

    @MockitoBean
    private ReservationService service;

    @Test
    void invalidNumberCannotReachService() throws Exception {
        mvc.perform(post("/api/reservations")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("guestName", "Lan")
                .param("seats", "abc")
                .param("contactEmail", "lan@example.org"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("INVALID_RESERVATION"))
            .andExpect(jsonPath("$.issues[*].field",
                hasItem("seats")))
            .andExpect(jsonPath(
                "$.issues[*].bindingFailure",
                hasItem(true)));

        verifyNoInteractions(service);
    }

    @Test
    void invalidMinConstraintCannotReachService()
            throws Exception {
        mvc.perform(post("/api/reservations")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("guestName", "Lan")
                .param("seats", "0")
                .param("contactEmail", "lan@example.org"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("INVALID_RESERVATION"))
            .andExpect(jsonPath("$.issues[*].field",
                hasItem("seats")));

        verifyNoInteractions(service);
    }

    @Test
    void blankGuestCannotReachService() throws Exception {
        mvc.perform(post("/api/reservations")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("guestName", "   ")
                .param("seats", "2")
                .param("contactEmail", "lan@example.org"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[*].field",
                hasItem("guestName")));

        verifyNoInteractions(service);
    }

    @Test
    void deniedVipFieldCannotReachService()
            throws Exception {
        mvc.perform(post("/api/reservations")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("guestName", "Lan")
                .param("seats", "2")
                .param("contactEmail", "lan@example.org")
                .param("vip", "true"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("UNEXPECTED_FIELDS"));

        verifyNoInteractions(service);
    }

    @Test
    void validFormCreatesImmutableCommand()
            throws Exception {

        ReservationService.Receipt fakeReceipt =
            new ReservationService.Receipt(
                17L, "Lan", 2);

        when(service.create(
                any(ReservationService.Command.class)))
            .thenReturn(fakeReceipt);

        mvc.perform(post("/api/reservations")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("guestName", "Lan")
                .param("seats", "2")
                .param("contactEmail", "lan@example.org"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value(17))
            .andExpect(jsonPath("$.guestName").value("Lan"))
            .andExpect(jsonPath("$.seats").value(2));

        verify(service).create(
            new ReservationService.Command(
                "Lan", 2, "lan@example.org"));
    }

    @Test
    void malformedEmailCannotReachService()
            throws Exception {

        mvc.perform(post("/api/reservations")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("guestName", "Lan")
                .param("seats", "2")
                .param("contactEmail", "not-an-email"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[*].field",
                hasItem("contactEmail")));

        verifyNoInteractions(service);
    }
}
~~~

**Sáu tests** ở class này kiểm chứng validation gate đúng các nhánh: conversion failure, `@Min`, `@NotBlank`, suppressed field, success path và email format. Đặc biệt `verifyNoInteractions(service)` kiểm tra **không có business call**, chứ không chỉ nhìn status 400.

**Chú ý:** Mockito mock được Spring test quản lý/đặt lại theo lifecycle mặc định của `@MockitoBean`. Test production có Spring Security có thể cần mock authentication/CSRF trong MVC slice tùy filter chain; ví dụ này dùng Web + Validation + Test starters, không thêm security config.

### Chạy test

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Tổng cộng project có **10 JUnit test methods**: bốn DataBinder tests và sáu MockMvc tests. Với dependencies và cấu hình nêu trên, chúng **được thiết kế để PASS**; đây là kết quả mong đợi theo phân tích code, **không phải xác nhận đã chạy Gradle trong bài viết**.

Nếu muốn tách kiểm thử cho từng nhóm:

~~~bash
./gradlew test \
  --tests "com.example.partialbinding.PartialBindingDataBinderTest"
~~~

và:

~~~bash
./gradlew test \
  --tests "com.example.partialbinding.ReservationControllerTest"
~~~

## 13. Vì sao `errors.hasErrors()` có thể false dù dữ liệu không an toàn?

Có ít nhất năm nguyên nhân độc lập:

1. **Chưa bật validation:** một `DataBinder.bind(...)` thủ công chỉ gắn fields và ghi conversion errors; nếu field đã convert nhưng vi phạm `@NotBlank` mà chưa gọi validator, `hasErrors()` vẫn false.
2. **Không có provider Jakarta:** project compile annotation nhưng runtime không có `spring-boot-starter-validation`/provider phù hợp, khiến validation không chạy theo kỳ vọng.
3. **Thiếu `@Valid`/`@Validated` trên MVC parameter:** DTO có annotations nhưng không được kích hoạt.
4. **Field bị suppressed** theo `setAllowedFields(...)`: suppressed fields **không bắt buộc** thành FieldError.
5. **Business authorization/invariant chưa được kiểm tra:** một form hợp lệ về type và constraints vẫn có thể trái quyền truy cập hoặc trạng thái nghiệp vụ.

Vì vậy điều kiện đi tiếp không nên viết giản lược “`!hasErrors()` tức mọi thứ đã an toàn”, mà phải định nghĩa những checks cụ thể trước service boundary.

### Một validation gate tốt có thể gồm

~~~text
[ ] Parse/bind hoàn chỉnh theo contract
[ ] Không có suppressed field trái policy
[ ] Không có BindingResult errors
[ ] Không có group/cross-field rule chưa thực thi
[ ] Request field allowlist/size limits hợp lệ
[ ] Authentication và authorization phù hợp
[ ] Mapping chỉ lấy fields đã cho phép
[ ] Service tái kiểm tra business invariants
[ ] Chỉ khi đó mới ghi DB hoặc phát side effect
~~~

Các bước cuối có thể ở service/transaction boundary; không nên nhồi toàn bộ domain authorization vào một `ConstraintValidator` chỉ dành cho cú pháp input.

## 14. Khi nào nên ném exception và khi nào nên dùng BindingResult?

Hai kiểu đều hợp lệ, nhưng phục vụ nhu cầu khác nhau.

### Controller xử lý lỗi cục bộ

~~~java
public ResponseEntity<?> submit(
        @Valid @ModelAttribute("form") FormDto form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().build();
    }
    // ...
}
~~~

Phù hợp khi muốn trả view cũ với lỗi ở từng field, hoặc tự tạo error response ngay tại handler. Điều kiện: **BindingResult đứng ngay sau argument** và mọi đường code đều chặn trước side effect.

### Global exception handler

Nếu handler không nhận `BindingResult`, Spring MVC có thể ném `MethodArgumentNotValidException` khi validation của `@ModelAttribute`/`@RequestBody` thất bại, rồi `@RestControllerAdvice` hoặc `ResponseEntityExceptionHandler` map thành error body.

Mẫu này giảm nguy cơ handler vô tình sử dụng form sai, **nhưng không biến binding thành atomic**; việc gắn một phần property vào object đã diễn ra trong lifecycle trước khi exception.

Chọn chiến lược phù hợp và kiểm thử. Nếu dùng global advice, ưu tiên extend `ResponseEntityExceptionHandler` rồi override `handleMethodArgumentNotValid(...)` đúng hook, tránh thêm `@ExceptionHandler` trùng mapping.

### Không được trộn nhiều cơ chế rồi giả định cùng exception

- Lỗi JSON parse: thường `HttpMessageNotReadableException`.
- `@ModelAttribute` form conversion/validation: `BindingResult` hoặc `MethodArgumentNotValidException` theo signature.
- Direct `@Min @RequestParam`: MVC 6.1+ method validation có thể phát `HandlerMethodValidationException`.
- Một `@RequestParam Integer` nhận `abc`: type mismatch ở argument resolution, thường `MethodArgumentTypeMismatchException`.
- Multipart upload errors có thể xảy ra trước handler.

Không phải mọi HTTP 400 đều mang cùng `BindingResult` hay phải được chặn ở cùng điểm.

## 15. Nếu có nhiều constraints trên một field

Ví dụ:

~~~java
@NotNull
@Min(1)
private Integer seats;
~~~

Với `seats=null`, `@NotNull` sai, còn `@Min` thường cho null là hợp lệ. Với `seats=0`, `@Min` sai. Với input form `seats=abc`, binder không thể chuyển thành `Integer`, ghi `typeMismatch`; sau đó provider có thể còn ghi `@NotNull` nếu chạy trên bean có seats null.

Vì vậy:

- Không giả định một field chỉ có một error.
- Không giả định chỉ có một error code khi conversion fail.
- Không giả định thứ tự errors giữa Jakarta provider và binder là contract lâu dài.
- Không dùng `getFieldError("seats")` để khẳng định **toàn bộ** lỗi của field; dùng `getFieldErrors("seats")` nếu cần đầy đủ.
- Trong response, map errors thành danh sách, có thể chuẩn hóa/deduplicate có chủ đích.
- Không lưu rejected raw input vào domain command.

Một field có `typeMismatch` không phải “đã gắn thất bại cho toàn DTO”; những field khác vẫn có thể đã được gán.

## 16. Không được gắn object có side effects trước validation gate

Hãy xem một setter nguy hiểm:

~~~java
public void setAccountStatus(String status) {
    auditService.publish(
        new StatusChangedEvent(status));
    this.accountStatus = status;
}
~~~

Đây là **phản ví dụ**, các types chỉ mang tính minh họa. Nếu binder gọi setter này, event đã được phát **trong lúc binding**, trước khi code handler kiểm tra `hasErrors()`. Trả HTTP 400 sau đó không tự hủy event.

Một JavaBean dùng làm request DTO lý tưởng nên:

- Có setters đơn giản chỉ gán fields.
- Không gọi repository, không gửi email, không publish event.
- Không dùng JPA entity đang managed.
- Không có setters trên fields client không được sửa.
- Không lẫn business invariants phải được kiểm tra trong transaction.
- Được tạo mới cho mỗi request nếu không có lý do đặc biệt để giữ state.

Nếu phải bind vào object đang có sẵn từ session/model, cần đánh giá tác động của partial mutations và cách bảo vệ lifecycle; tốt hơn là bind vào **copy/command riêng** rồi áp dụng vào domain sau validation.

## 17. Field allowlist, suppressed fields và mass assignment

Một attacker có thể gửi thêm:

~~~text
guestName=Lan
seats=2
contactEmail=lan@example.org
vip=true
ownerId=other-user
status=APPROVED
~~~

Nếu bạn bind trực tiếp một entity với setters tương ứng và không có allowlist, những fields ngoài UI vẫn có thể được gán. `setDisallowedFields(...)` dạng blacklist có thể bỏ sót field mới khi domain mở rộng.

Bảo vệ theo thứ tự ưu tiên:

1. **Dedicated request DTO** chỉ có các properties thực sự được phép nhập.
2. **Constructor binding** hoặc declarative binding khi thích hợp.
3. **`setAllowedFields(...)`** cho property binding còn cần.
4. **Kiểm tra `getSuppressedFields()`** nếu contract quyết định reject unknown/disallowed fields.
5. **Authorization ở service** cho danh tính/tài nguyên được sửa.
6. **Không truyền nguyên DTO/entity vào repository.update(...)`** khi chứa nhiều fields ngoài contract.

Trong demo, `vip` nằm trên DTO chỉ để thử allowlist, nhưng trong hệ thống thật nên loại bỏ field nhạy cảm khỏi request DTO ngay từ đầu.

### Suppressed không nhất thiết đồng nghĩa illegal

Một API có thể cho phép client gửi extra fields và âm thầm bỏ qua theo contract. Khi đó `getSuppressedFields()` phục vụ metrics/troubleshooting mà không cần trả 400. Demo chọn chính sách **strict**: có suppressed fields là reject. Cách nào đúng phụ thuộc yêu cầu tương thích, an toàn và phiên bản API; quan trọng là **chủ động quyết định**.

## 18. Đừng nhầm partial binding với partial persistence

Có ba khái niệm cần phân biệt:

| Khái niệm | Khi nào xảy ra | Có tự rollback không? |
|---|---|---|
| Partial property binding | Khi binder đã set một số properties trên object | Không mặc định |
| Partial business processing | Khi controller/service đã thực hiện một phần công việc trước khi thấy errors | Không tự động |
| Partial persistence | Khi DB/external systems đã nhận một số writes | Tùy transaction/consistency design, không do BindingResult đảm bảo |

Trong transaction DB, một exception có thể kích hoạt rollback theo propagation/rollback rules. Nhưng:

- Nếu handler trả `400` mà không ném exception trong cùng transaction, rollback không tự được kích hoạt chỉ vì HTTP status là 400.
- External side effects như email, HTTP outbound hoặc message publish không nhất thiết nằm trong DB transaction.
- JPA dirty checking có thể flush changes trên managed entity dù không gọi `save` trực tiếp, tùy context/transaction.
- In-memory field mutations vẫn tồn tại trên object reference hiện tại dù DB rollback.

**Tốt nhất: không bắt đầu business transaction/side effects cho request chưa qua binding và validation gate.** Các invariants phải kiểm tra dưới transaction vẫn cần được service bảo vệ.

## 19. Validation group và custom Spring Validator cũng cần được kích hoạt

`@Valid` thường yêu cầu Jakarta Bean Validation Default group. Nếu dùng `@Validated(SomeGroup.class)` nhưng rule chỉ thuộc group khác, `BindingResult` có thể không có lỗi bạn mong đợi.

Một Spring custom `Validator`:

~~~java
public final class FormRules implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return ReservationForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        // errors.rejectValue(...) hoặc errors.reject(...)
    }
}
~~~

Đây là snippet cần imports `org.springframework.validation.Validator`/`Errors` và class trong scope. Chỉ tạo class không khiến `DataBinder.bind(...)` tự gọi nó. Với binder thủ công:

~~~java
binder.addValidators(customValidator);
binder.validate();
~~~

Trong Spring MVC có thể dùng `@InitBinder` để đăng ký thêm validator phù hợp và trigger validation trên argument. Đừng vô tình thay global Jakarta validator bằng một custom validator không chạy annotations.

Nếu `hasErrors()==false` với form trắng, hãy kiểm tra xem validation provider/trigger thực sự đã có chưa, không chỉ xem một lời gọi `bind(...)`.

## 20. Thiết kế API lỗi ổn định và không lộ input

Response nên cho client biết:

- Mã lỗi public ổn định, ví dụ `INVALID_RESERVATION`.
- Những field names được phép công khai và đang sai.
- Mã lỗi theo loại, ví dụ `INVALID_NUMBER`, `REQUIRED_FIELD`, `VALUE_BELOW_MIN`.
- Message được resolve theo locale qua `MessageSource` nếu cần.
- Object-level errors không bị bỏ quên.

Không cần gửi:

- Toàn bộ `BindingResult`.
- `getTarget()` là form/managed object.
- `FieldError.getRejectedValue()` cho mọi field.
- Internal Java class names, stack trace và database IDs không được phép lộ.
- Raw suppressed fields khi chúng có thể chứa tên property nội bộ nhạy cảm.

Schema ví dụ:

~~~json
{
  "code": "INVALID_RESERVATION",
  "issues": [
    {
      "field": "seats",
      "code": "typeMismatch",
      "bindingFailure": true
    }
  ]
}
~~~

Đây là schema học tập với mã Spring gốc; production API có thể ánh xạ `typeMismatch` thành code ổn định như `INVALID_NUMBER` và dùng messages đã localize. Không nhận định code example là output mặc định của Spring Boot.

### Vì sao không gửi rejected input?

Với lỗi conversion, rejected raw value có thể rất dài hoặc chứa secrets. Để form hiển thị giá trị người dùng vừa nhập, dùng cơ chế template/form binding phù hợp và output encoding; không bắt API public phải phát lại toàn bộ input.

## 21. Quan sát và logging khi lỗi binding

Một số metrics hữu ích:

- Tỷ lệ request có `typeMismatch`.
- Số `BindingResult.getFieldErrorCount()` theo endpoint/field được phép.
- Số request có suppressed fields.
- Tỷ lệ HTTP 400 do binding so với validation và domain rules.
- Số business calls được chặn trước service.
- Latency p95/p99 của binding và validation.
- Số request vượt giới hạn params/body/collection.

Tránh log toàn bộ request bodies và rejected values; đặc biệt ở API nhận thông tin cá nhân. Nếu muốn điều tra, dùng request ID, route template và mã lỗi, không ghi input raw tùy ý.

### Smoke test cho production

Một regression test sau khi đổi DTO, framework hoặc binder config nên gửi form có một field hợp lệ và một field sai, rồi assert **service không được gọi**. Nếu test chỉ assert 400, có thể bỏ sót bug gọi service **trước khi trả 400**.

Khi dùng @Transactional, nên có integration test kiểm tra DB không có row mới sau request invalid và external event mock không được publish, nhưng đặt test ở đúng boundary; `MockMvc` + `@MockitoBean` đủ để học nguyên tắc không gọi service.

## 22. Các lỗi triển khai thường gặp

| Dấu hiệu | Nguyên nhân | Cách sửa |
|---|---|---|
| `hasErrors()==true` nhưng `guestName` đã được set | Partial binding là expected | Không dùng target trước validation gate |
| Một field bị lỗi nhưng controller gọi service | Check errors quá muộn hoặc thiếu | Early return trước service |
| Form có `BindingResult` và handler vẫn chạy | Handler tự chịu trách nhiệm error handling | Kiểm tra `errors.hasErrors()` |
| `getSuppressedFields()` không rỗng mà `hasErrors()==false` | Suppression khác FieldError | Chặn riêng nếu strict input policy |
| Client gửi `vip=true` dù UI không có | Mass assignment attempt | DTO riêng + allowedFields |
| Email hợp lệ, seats `abc` làm DTO chưa hợp lệ | Conversion chỉ thất bại ở seats | Reject toàn request, đừng “nhận một nửa” |
| `getFieldValue("seats")` khác `form.getSeats()` | Rejected input được giữ cho hiển thị | Phân biệt field value vs target getter |
| `@Min` không thấy khi seats `abc` | Conversion thất bại trước | Xem `typeMismatch` |
| `@NotBlank` không thấy sau manual bind | Chưa gọi validator | `binder.validate()` hoặc MVC `@Valid` |
| Lỗi global bị bỏ khỏi response | Chỉ map `getFieldErrors()` | Map `getGlobalErrors()` riêng |
| Service gọi rồi mới trả 400 | Sai thứ tự validation gate | Chặn trước side effects |
| Trả 400 nhưng DB vẫn thay đổi | Entity managed/saved trước validation | DTO riêng + service transaction after gate |
| `@Transactional` không undo setter | In-memory mutation ngoài rollback DB | Không bind entity/domain object |
| Custom setter phát event khi binding | Setter có side effect | Dùng side-effect-free DTO |
| Test HTTP 400 PASS nhưng service vẫn gọi | Không verify no interactions | Mock service + `verifyNoInteractions` |
| `@InitBinder` không áp allowlist | Attribute name/scope không khớp | Test `"reservationForm"` và binder configuration |
| Form JSON malformed không tới handler | `@RequestBody` decoder fail | Xử lý `HttpMessageNotReadableException` |
| `BindingResult` đặt xa argument | Không gắn với model parameter mong muốn | Đặt ngay sau validated argument |
| Multiple errors nhưng test chỉ kiểm tra first | `getFieldError` trả một entry | Dùng `getFieldErrors(field)` |
| Formatter/type conversion khác giữa unit và MVC | DataBinder setup khác | Bổ sung MockMvc test cho binder config |
| JavaBean chứa admin/owner setters | DTO thiết kế không phù hợp | Loại field khỏi request DTO |
| Validator class có nhưng annotations không chạy | Provider/entry point/group thiếu | Test provider + `@Valid`/`@Validated` |

### Debug theo thứ tự

1. Xác định endpoint đang dùng `@ModelAttribute` hay `@RequestBody`.
2. Xác nhận target object được tạo mới hay lấy từ session/model/entity.
3. Kiểm tra `BindingResult` đặt đúng ngay sau argument chưa.
4. Kiểm tra lỗi là conversion (`typeMismatch`) hay Jakarta constraint (`Min`, `NotBlank`).
5. Sau binding, so các property hợp lệ trên target với field bị từ chối.
6. Kiểm tra `getSuppressedFields()` độc lập với `hasErrors()`.
7. Rà thứ tự code: có gọi service/repository trước nhánh lỗi không?
8. Rà DTO setters: có side effects hoặc writable fields không cho phép không?
9. Kiểm tra `@InitBinder`/allowedFields/declarative binding và scope.
10. Kiểm tra provider, `@Valid`/groups nếu đáng ra phải có validation errors.
11. Dùng MockMvc và `verifyNoInteractions(service)` cho request invalid.
12. Thêm DB integration test nếu yêu cầu chứng minh không có persistence side effects.

## 23. Câu hỏi tự luyện

**1. `BindingResult.hasErrors()==true` có đảm bảo tất cả fields giữ nguyên giá trị trước request không?**

Không. Những property bind thành công có thể đã được gán vào target, dù field khác thất bại.

**2. `DataBinder.bind(...)` có tự rollback mọi setter khi gặp `typeMismatch` không?**

Không. Nó không phải cơ chế transaction rollback.

**3. Vì sao `getRejectedValue()` có thể khác getter trên JavaBean?**

BindingResult giữ raw input bị từ chối để báo lỗi/hiển thị form; Java property không thể nhận giá trị sai kiểu đó.

**4. Handler có `@Valid @ModelAttribute` và `BindingResult` vẫn được gọi khi input sai là bug Spring không?**

Không. Đây là cơ chế xử lý lỗi cục bộ; handler phải kiểm tra và return sớm.

**5. Chỉ kiểm tra `hasErrors()` có phát hiện mọi field bị chặn bằng allowlist không?**

Không nhất thiết; suppressed fields có API riêng `getSuppressedFields()`.

**6. Vì sao không bind trực tiếp managed JPA entity?**

Partial binding có thể thay đổi entity trong persistence context trước khi validation hoàn thành; cùng với mass assignment và dirty checking, có nguy cơ side effect.

**7. `@Transactional` có tự undo một sự kiện đã gửi từ setter lúc binding không?**

Không. DB transaction không bảo đảm rollback external side effects hoặc mọi in-memory mutation.

**8. Thời điểm nên tạo immutable command từ form là khi nào?**

Sau khi xác nhận không có binding/validation errors và không vi phạm input policy.

**9. Với `seats=abc` và `@Min(1)`, loại lỗi quan trọng nhất phát sinh từ đâu?**

Type conversion thất bại khi cố tạo `Integer`, thường có `typeMismatch`; không cần `@Min` chạy trên chuỗi raw.

**10. Test nào cho thấy handler không gây business side effect khi input sai?**

MockMvc gửi request invalid và Mockito `verifyNoInteractions(service)`.

**11. `@RequestBody` malformed JSON có luôn đưa partial DTO vào handler không?**

Không. Decoder thường ném exception trước khi handler có argument hợp lệ.

**12. `setAllowedFields(...)` và `@Valid` có thay thế nhau không?**

Không. Một cơ chế chọn fields có thể bind; cơ chế kia kiểm tra constraints trên giá trị.

**13. Một field có nhiều errors, dùng `getFieldError(field)` đủ không?**

Không nếu cần tất cả; phải dùng `getFieldErrors(field)`.

**14. Vì sao cần tách lỗi suppressed fields khỏi lỗi constraint?**

Chúng phát sinh từ những chính sách khác nhau; suppressed fields không nhất thiết được biểu diễn thành `FieldError`.

## 24. Checklist phòng tránh partial-data misuse

- [ ] Dùng DTO chuyên biệt, không bind trực tiếp entity đang managed.
- [ ] DTO setters không có side effects.
- [ ] Rà model object có thể được reuse từ session/model không.
- [ ] `BindingResult` nằm ngay sau validated argument nếu cần xử lý cục bộ.
- [ ] Kiểm tra `hasErrors()` **trước** mọi service/persistence call.
- [ ] Kiểm tra `getSuppressedFields()` nếu API reject fields ngoài allowlist.
- [ ] Dùng `setAllowedFields(...)` và/hoặc declarative/constructor binding phù hợp.
- [ ] Không chỉ dựa vào `setDisallowedFields(...)` blacklist.
- [ ] Xác minh `@Valid`/`@Validated` và provider thực sự hoạt động.
- [ ] Phân biệt conversion failure và constraint violation.
- [ ] Không coi `getFieldValue(...)` là JavaBean property chắc chắn đã gắn.
- [ ] Không truyền rejected raw values vào immutable business command.
- [ ] Map field/global errors có cấu trúc, không lộ target và secrets.
- [ ] Domain service vẫn thực hiện authorization và invariants.
- [ ] Đảm bảo commit/side effects chỉ sau validation gate phù hợp.
- [ ] Bổ sung checks cho idempotency, retry và concurrency theo nghiệp vụ.
- [ ] Test partial binding bằng `DataBinder` thực.
- [ ] Test invalid request không gọi service bằng Mockito/MockMvc.
- [ ] Test allowlist với field có setter nhưng không được client sửa.
- [ ] Khi thay Spring/Boot/DTO, chạy lại regression tests về thứ tự xử lý.
- [ ] Không khẳng định dữ liệu được rollback chỉ vì HTTP 400.
- [ ] Chạy Gradle và kiểm tra kết quả test thật trước khi deploy.

**Ghi nhớ:** Trong Spring MVC, **partial binding là trạng thái có thể xảy ra**, không phải sự bảo đảm atomic của `DataBinder`. Một số fields đã được set trong khi `BindingResult` có lỗi ở field khác. Hãy **bind vào request DTO không có side effects**, giới hạn fields được phép gắn, kiểm tra **`getSuppressedFields()` và `hasErrors()`**, rồi mới chuyển sang immutable command và gọi service. Một test thật sự có giá trị không chỉ thấy **HTTP 400**, mà còn chứng minh **không có lời gọi business service khi request còn lỗi**.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Model Attribute Method Arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — @InitBinder và Model Design](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework 6.2 — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.2 — BindingResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework 6.2 — FieldError Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring Framework 6.2 — Data Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation/data-binding.html)
- [Spring Framework 6.2 — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — Method Arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/arguments.html)
- [Spring Boot 3.5 — Validation](https://docs.spring.io/spring-boot/3.5/reference/io/validation.html)
- [Spring Framework 6.2 — MockitoBean Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/context/bean/override/mockito/MockitoBean.html)
