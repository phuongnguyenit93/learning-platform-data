# Đăng ký editor cục bộ bằng registerCustomEditor trong Spring Framework

## 1. Bài toán và mục tiêu

Spring MVC và Spring WebFlux có thể bind các tham số của HTTP form/query vào JavaBean qua `@ModelAttribute`. Phần lớn input xuất phát từ chuỗi, trong khi object đích có thể chứa `LocalDate`, `Date`, `Integer`, `String`, danh sách hay kiểu domain riêng. `DataBinder` cần chuyển chuỗi thành kiểu property trước khi đặt giá trị bằng setter hoặc qua cơ chế binding phù hợp.

Ví dụ form gửi:

~~~text
title=  Java Workshop
startDate=25/12/2026
endDate=2026-12-31
coupon=  vip10
tags[0]=spring
approved=true
~~~

Object đích có `String title`, `LocalDate startDate`, `LocalDate endDate`, `String coupon`, `List<String> tags` và `boolean approved`. Ta muốn trim `title`, parse hai ngày theo **hai định dạng khác nhau**, uppercase `coupon` và không cho client cập nhật `approved`.

Spring có sẵn `ConversionService`, `Converter`, `Formatter` và nhiều editor mặc định. Khi muốn thiết lập một quy tắc JavaBeans riêng trong phạm vi binder, ta dùng **`registerCustomEditor`**:

~~~java
@InitBinder("eventForm")
void configure(WebDataBinder binder) {
    binder.registerCustomEditor(
            LocalDate.class, "startDate",
            new StrictLocalDateEditor("dd/MM/uuuu"));
}
~~~

Đây là **method minh họa** đặt trong một controller, chưa phải file Java đầy đủ. Nó yêu cầu binder tên `eventForm` áp dụng editor `StrictLocalDateEditor` cho property `startDate` thuộc type `LocalDate`.

**Kết quả học tập:** sau bài này, người đọc biết phân biệt đăng ký theo type và theo property path, biết viết `PropertyEditorSupport`, đăng ký editor qua `@InitBinder`, đọc conversion errors bằng `BindingResult`, bảo vệ input với allowlist, và chọn `Formatter`/`Converter` khi không nên dùng editor truyền thống.

## 2. PropertyEditor là gì?

### 2.1. API JavaBeans

`java.beans.PropertyEditor` là interface của JavaBeans dành cho việc biến đổi text ↔ object. Spring `BeanWrapper`/`DataBinder` hỗ trợ editor khi chuyển dữ liệu vào property. `java.beans.PropertyEditorSupport` cung cấp cách triển khai thuận tiện: override những method thực sự cần, thay vì implement toàn bộ interface.

| Method | Mục đích |
| --- | --- |
| `setAsText(String text)` | Parse text gửi tới, gọi `setValue(...)` để giữ kết quả |
| `setValue(Object value)` | Đặt giá trị Java nội bộ |
| `getValue()` | Đọc giá trị Java của editor |
| `getAsText()` | Chuyển giá trị Java hiện tại về text, phục vụ những đường biểu diễn JavaBeans thích hợp |

Ví dụ editor biến mã coupon thành chữ hoa:

~~~java
import java.beans.PropertyEditorSupport;
import java.util.Locale;

public final class CouponCodeEditor extends PropertyEditorSupport {
    @Override
    public void setAsText(String text) {
        setValue(text == null
                ? ""
                : text.strip().toUpperCase(Locale.ROOT));
    }

    @Override
    public String getAsText() {
        Object value = getValue();
        return value == null ? "" : value.toString();
    }
}
~~~

Với input `"  vip10  "`, editor đặt giá trị `"VIP10"`. `Locale.ROOT` giúp uppercase của mã kỹ thuật ổn định giữa các máy.

**Editor chỉ chuẩn hóa cú pháp.** Nó không xác minh mã coupon có tồn tại, còn hạn, thuộc người dùng hiện tại hay có được phép áp dụng không. Các quy tắc đó phải nằm trong validation hoặc service/domain logic.

### 2.2. Tính stateful và thread safety

`PropertyEditorSupport` có state nội bộ (`value`). Vì vậy một instance editor **không được mặc định xem là thread-safe**. Tránh đưa editor mutable vào `static final` rồi đăng ký chung cho nhiều request binders.

Cách an toàn khi dùng `@InitBinder` là khởi tạo editor mới cho mỗi binder. Đặc biệt, `SimpleDateFormat` (khi dùng editor cho `java.util.Date`) cũng mutable và không thread-safe nếu chia sẻ xuyên threads. `DateTimeFormatter` của Java Time là immutable và có thể dùng lại; tuy nhiên instance `PropertyEditorSupport` vẫn có state nên tạo mới theo binder.

### 2.3. Hai công đoạn khác nhau

~~~text
HTTP text "25/12/2026"
       |
       v
PropertyEditor / Converter / Formatter
       |
       v
LocalDate.of(2026, 12, 25)
       |
       v
Jakarta Bean Validation / Spring Validator
       |
       v
Hợp lệ hoặc có constraint violation
~~~

Sai cú pháp ngày phát sinh **type conversion/binding error**. Ngày parse được nhưng không đúng business rule phát sinh **validation error** khi một validator có liên quan thực sự chạy.

## 3. Hai overload của registerCustomEditor

Spring `PropertyEditorRegistry` cung cấp hai overload:

~~~java
// Chữ ký API rút gọn, không khai báo lại trong ứng dụng.
void registerCustomEditor(Class<?> requiredType,
                          PropertyEditor editor);

void registerCustomEditor(Class<?> requiredType,
                          String propertyPath,
                          PropertyEditor editor);
~~~

### 3.1. Đăng ký theo type

~~~java
binder.registerCustomEditor(
        String.class, new StringTrimmerEditor(true));
~~~

Mọi property kiểu `String` trong phạm vi binder có thể được trim, trừ khi một property có editor cụ thể hơn. `StringTrimmerEditor(true)` trim và đổi chuỗi trở nên rỗng thành `null`. Vì `@NotBlank` cấm null, một field chỉ chứa khoảng trắng sẽ bị phát hiện khi Bean Validation chạy.

Dùng cách này khi mọi `String` input của **binder đó** cùng chấp nhận chính sách trim. Không áp dụng đại trà cho mật khẩu, chuỗi có chữ ký số hoặc text cần bảo toàn whitespace.

### 3.2. Đăng ký theo type và property

~~~java
binder.registerCustomEditor(
        String.class, "coupon", new CouponCodeEditor());
~~~

Đối với `coupon`, editor riêng có ưu tiên so với editor chung `StringTrimmerEditor`. Kết quả: `title` được trim, còn `coupon` vừa trim vừa uppercase. Đây là **khác biệt giữa type-scope và property-scope** ngay bên trong một binder.

Tương tự, cùng kiểu `LocalDate` nhưng khác format:

~~~java
binder.registerCustomEditor(
        LocalDate.class, "startDate",
        new StrictLocalDateEditor("dd/MM/uuuu"));
binder.registerCustomEditor(
        LocalDate.class, "endDate",
        new StrictLocalDateEditor("uuuu-MM-dd"));
~~~

Nếu đăng ký một editor `LocalDate.class` không có path, cả hai ngày có nguy cơ bị ép vào cùng format. Khi contract có định dạng riêng cho từng field, overload có `propertyPath` là lựa chọn rõ ràng.

### 3.3. Bảng quyết định

| Yêu cầu | Cách đăng ký | Phạm vi |
| --- | --- | --- |
| Trim mọi property `String` của form | `registerCustomEditor(String.class, editor)` | Theo type |
| Uppercase riêng `coupon` | `registerCustomEditor(String.class, "coupon", editor)` | Theo property |
| Parse mọi `java.util.Date` cùng pattern | `registerCustomEditor(Date.class, editor)` | Theo type |
| Parse riêng `startDate` theo ngày/tháng/năm | `registerCustomEditor(LocalDate.class, "startDate", editor)` | Theo property |
| Parse `address.city` trong nested object | `registerCustomEditor(String.class, "address.city", editor)` | Theo nested path |
| Parse `items[n].quantity` | `registerCustomEditor(Integer.class, "items.quantity", editor)` | Theo canonical path của phần tử list |

`propertyPath` là đường dẫn **tương đối với object đích của binder**, không phải URI, URL path hay tên đầy đủ có tiền tố model attribute. Với binder của `eventForm`, dùng `"startDate"`, không phải `"eventForm.startDate"`.

### 3.4. Một editor trên một path

Javadoc `PropertyEditorRegistry` lưu ý: chỉ **một custom editor được đăng ký cho một property path**. Với collection/array, editor có thể được chọn để xử lý **toàn collection** hoặc **mỗi element** tùy `requiredType`. Đừng đăng ký đồng thời editor cho collection và cho mỗi element trên cùng property path với giả định Spring sẽ xâu chuỗi hai lần conversion.

Ví dụ tài liệu Spring dùng path `"items.quantity"` cho các field thực tế như `items[0].quantity`, `items[1].quantity`. Cần giữ đúng `requiredType` (`Integer.class` nếu property là Integer), cấu trúc DTO và test những tên field request đang thực sự gửi.

## 4. Phạm vi local: @InitBinder trên controller

### 4.1. Local theo controller và attribute name

~~~java
@RestController
class FormController {

    @InitBinder("eventForm")
    void init(WebDataBinder binder) {
        binder.registerCustomEditor(
                String.class, new StringTrimmerEditor(true));
    }
}
~~~

Đây là ví dụ về cấu hình, chưa có handler. Spring gọi `@InitBinder` khi khởi tạo binder thích hợp trong **controller đó**. `"eventForm"` là object name, ví dụ được chỉ ra bằng `@ModelAttribute("eventForm")`. Nếu controller có các attributes khác với formatting khác, không đặt editor type-wide vào `@InitBinder` không giới hạn tên khi không có chủ đích.

Dùng nhiều tên khi cùng quy tắc áp dụng cho nhiều forms:

~~~java
@InitBinder({"eventForm", "reminderForm"})
void initTwo(WebDataBinder binder) {
    binder.registerCustomEditor(
            String.class, new StringTrimmerEditor(true));
}
~~~

Hai ví dụ trên là các phương án độc lập, không phải chỉ dẫn đặt hai method cùng sửa một binder. Nhiều `@InitBinder` cùng chạy trong phạm vi liên quan có thể khiến cấu hình khó theo dõi; giữ mỗi hook có trách nhiệm rõ ràng.

### 4.2. Scope của @ControllerAdvice

~~~java
@ControllerAdvice(assignableTypes = EventController.class)
class EventBindingAdvice {

    @InitBinder
    void shared(WebDataBinder binder) {
        binder.registerCustomEditor(
                String.class, new StringTrimmerEditor(true));
    }
}
~~~

Cấu hình này áp dụng cho những controller mà advice chọn. `@ControllerAdvice` có thể giới hạn bằng `assignableTypes`, `basePackageClasses`, `basePackages` hoặc `annotations`. Không đặt advice này vào project runnable ở mục 6, vì ta muốn test sự khác biệt giữa controller có editor local và controller không có editor.

Với WebFlux annotated controllers, các `@InitBinder` từ `@ControllerAdvice` áp dụng trước các `@InitBinder` local trên controller. Tránh dựa vào việc hai nơi ghi đè cùng loại editor theo thứ tự ngầm định; thay vào đó xác định policy chung và field-specific rõ ràng.

### 4.3. Không làm công việc bất đồng bộ trong hook

`@InitBinder` thường nhận `WebDataBinder` và có return type `void`. Đây là hook cấu hình **đồng bộ**; không nên trả `Mono<Void>` từ `@InitBinder` rồi kỳ vọng Spring subscribe để đăng ký editor. Không gọi database hoặc HTTP blocking trong `setAsText(...)`.

Spring WebFlux đọc form body theo reactive contract; nhưng hành vi format/convert trong binder là logic nên nhanh, có thể chạy trong request processing. Validation nghiệp vụ cần truy cập hệ thống ngoài nên được chuyển sang reactive service sau khi parse/bind.

## 5. Xây StrictLocalDateEditor đúng cách

### 5.1. Strict parsing

Để xử lý `25/12/2026` theo `dd/MM/uuuu`, dùng `DateTimeFormatter` và `ResolverStyle.STRICT`:

~~~java
import java.beans.PropertyEditorSupport;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;

public final class StrictLocalDateEditor extends PropertyEditorSupport {

    private final DateTimeFormatter formatter;

    public StrictLocalDateEditor(String pattern) {
        formatter = DateTimeFormatter.ofPattern(pattern)
                .withResolverStyle(ResolverStyle.STRICT);
    }

    @Override
    public void setAsText(String text) {
        if (text == null || text.isBlank()) {
            setValue(null);
            return;
        }
        setValue(LocalDate.parse(text.strip(), formatter));
    }

    @Override
    public String getAsText() {
        LocalDate date = (LocalDate) getValue();
        return date == null ? "" : date.format(formatter);
    }
}
~~~

Trong strict parsing, `uuuu` (proleptic year) phù hợp hơn `yyyy` (year-of-era) khi pattern không có era. `LocalDate.parse` sẽ ném `DateTimeParseException` cho ngày sai. Khi đi qua binder, lỗi này thường được chuyển thành `FieldError` với code loại `typeMismatch`.

| Input với pattern `dd/MM/uuuu` | Kết quả |
| --- | --- |
| `25/12/2026` | `LocalDate.of(2026, 12, 25)` |
| ` 25/12/2026 ` | Hợp lệ vì `strip()` |
| `2026-12-25` | Lỗi format |
| `31/02/2026` | Lỗi ngày không tồn tại |
| Chuỗi rỗng | `null`; `@NotNull` có thể bắt lỗi khi validation chạy |

`getAsText()` mô tả JavaBeans text rendering; nó **không tự thay đổi định dạng JSON** của Jackson khi một `@RestController` trả object. Format JSON phải được cấu hình ở cơ chế serialize/deserialze tương ứng.

### 5.2. So với CustomDateEditor

Spring có `org.springframework.beans.propertyeditors.CustomDateEditor` cho `java.util.Date`, ví dụ:

~~~java
@InitBinder
void initLegacyDate(WebDataBinder binder) {
    SimpleDateFormat format = new SimpleDateFormat("yyyy-MM-dd");
    format.setLenient(false);
    binder.registerCustomEditor(
            java.util.Date.class,
            new CustomDateEditor(format, false));
}
~~~

Đây là method minh họa, cần imports `SimpleDateFormat`, `CustomDateEditor` và `WebDataBinder`. `CustomDateEditor` không dành cho `java.time.LocalDate`. `SimpleDateFormat` là mutable, nên tạo instance mới bên trong init method; không chia sẻ singleton xuyên requests.

Với Java Time, các ứng dụng mới thường dùng `@DateTimeFormat` hoặc một `Formatter<LocalDate>` nếu yêu cầu chỉ là định dạng đơn giản. Bài này dùng `PropertyEditorSupport` để chỉ rõ hành vi của `registerCustomEditor`.

## 6. Ví dụ chạy được: Java 17, Spring Boot 3.5.7, WebFlux

Project dùng Spring WebFlux để thử form URL-encoded và `@InitBinder`, đồng thời dùng `WebDataBinder` trực tiếp trong unit test. Các API đăng ký editor là chung cho MVC và WebFlux.

### 6.1. Cấu trúc project

~~~text
pom.xml
src/main/java/com/example/localeditor/
  LocalEditorApplication.java
  EventForm.java
  StrictLocalDateEditor.java
  CouponCodeEditor.java
  EventController.java
  RawEventController.java
src/test/java/com/example/localeditor/
  EventControllerTest.java
  EventBinderTest.java
~~~

### 6.2. Maven dependencies

~~~xml
<!-- pom.xml -->
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
    <artifactId>local-editor-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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
</project>
~~~

`spring-boot-starter-webflux` bảo đảm app theo reactive stack khi không thêm Servlet MVC starter. `spring-boot-starter-validation` có Jakarta Validation provider; `spring-boot-starter-test` có JUnit 5 và WebFlux test utilities. Không cần database.

### 6.3. Spring Boot application

~~~java
// src/main/java/com/example/localeditor/LocalEditorApplication.java
package com.example.localeditor;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LocalEditorApplication {

    public static void main(String[] args) {
        SpringApplication.run(LocalEditorApplication.class, args);
    }
}
~~~

### 6.4. Form object

~~~java
// src/main/java/com/example/localeditor/EventForm.java
package com.example.localeditor;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;

public class EventForm {

    @NotBlank(message = "Tiêu đề không được trống")
    private String title;

    @NotNull(message = "Ngày bắt đầu là bắt buộc")
    private LocalDate startDate;

    @NotNull(message = "Ngày kết thúc là bắt buộc")
    private LocalDate endDate;

    private String coupon = "";

    @Size(max = 3, message = "Tối đa 3 nhãn")
    private List<@NotBlank String> tags = new ArrayList<>();

    // Chỉ để minh họa mass assignment risk.
    private boolean approved;

    public EventForm() {}

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }

    public LocalDate getStartDate() { return startDate; }
    public void setStartDate(LocalDate startDate) {
        this.startDate = startDate;
    }

    public LocalDate getEndDate() { return endDate; }
    public void setEndDate(LocalDate endDate) {
        this.endDate = endDate;
    }

    public String getCoupon() { return coupon; }
    public void setCoupon(String coupon) { this.coupon = coupon; }

    public List<String> getTags() { return tags; }
    public void setTags(List<String> tags) { this.tags = tags; }

    public boolean isApproved() { return approved; }
    public void setApproved(boolean approved) {
        this.approved = approved;
    }
}
~~~

Class này có no-args constructor và getters/setters để property binding dễ hiểu. `@Valid` sẽ kiểm tra các field constraints sau binding. `approved` chỉ dùng làm test rằng request `approved=true` bị chặn bởi `allowedFields`; trong ứng dụng thật nên bỏ property đó khỏi public input DTO.

### 6.5. Hai editor dưới dạng file Java

~~~java
// src/main/java/com/example/localeditor/StrictLocalDateEditor.java
package com.example.localeditor;

import java.beans.PropertyEditorSupport;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;

public final class StrictLocalDateEditor extends PropertyEditorSupport {
    private final DateTimeFormatter formatter;

    public StrictLocalDateEditor(String pattern) {
        this.formatter = DateTimeFormatter.ofPattern(pattern)
                .withResolverStyle(ResolverStyle.STRICT);
    }

    @Override
    public void setAsText(String text) {
        if (text == null || text.isBlank()) {
            setValue(null);
            return;
        }
        setValue(LocalDate.parse(text.strip(), formatter));
    }

    @Override
    public String getAsText() {
        LocalDate value = (LocalDate) getValue();
        return value == null ? "" : value.format(formatter);
    }
}
~~~

~~~java
// src/main/java/com/example/localeditor/CouponCodeEditor.java
package com.example.localeditor;

import java.beans.PropertyEditorSupport;
import java.util.Locale;

public final class CouponCodeEditor extends PropertyEditorSupport {

    @Override
    public void setAsText(String text) {
        setValue(text == null
                ? ""
                : text.strip().toUpperCase(Locale.ROOT));
    }

    @Override
    public String getAsText() {
        Object value = getValue();
        return value == null ? "" : value.toString();
    }
}
~~~

Các file này có thể compile riêng khi Spring dependencies được Maven giải quyết cho application. Không tái sử dụng instance `CouponCodeEditor` hoặc `StrictLocalDateEditor` giữa requests.

### 6.6. Controller đăng ký editor local

~~~java
// src/main/java/com/example/localeditor/EventController.java
package com.example.localeditor;

import jakarta.validation.Valid;
import org.springframework.beans.propertyeditors.StringTrimmerEditor;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/events")
public class EventController {

    @InitBinder("eventForm")
    void configureBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "title", "startDate", "endDate", "coupon", "tags[*]");
        binder.setAutoGrowCollectionLimit(6);

        // Theo type: mọi String property trong binder.
        binder.registerCustomEditor(
                String.class, new StringTrimmerEditor(true));

        // Theo property path: riêng coupon.
        binder.registerCustomEditor(
                String.class, "coupon", new CouponCodeEditor());

        binder.registerCustomEditor(
                LocalDate.class, "startDate",
                new StrictLocalDateEditor("dd/MM/uuuu"));
        binder.registerCustomEditor(
                LocalDate.class, "endDate",
                new StrictLocalDateEditor("uuuu-MM-dd"));
    }

    @PostMapping(consumes =
            MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Mono<ResponseEntity<Map<String, Object>>> create(
            @Valid @ModelAttribute("eventForm") EventForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            List<String> fields = errors.getFieldErrors().stream()
                    .map(FieldError::getField)
                    .distinct()
                    .sorted()
                    .toList();

            return Mono.just(ResponseEntity.badRequest()
                    .body(Map.of("invalidFields", fields)));
        }

        Map<String, Object> body = Map.of(
                "title", form.getTitle(),
                "startDate", form.getStartDate().toString(),
                "endDate", form.getEndDate().toString(),
                "coupon", form.getCoupon() == null
                        ? "" : form.getCoupon(),
                "tags", form.getTags(),
                "approved", form.isApproved());

        return Mono.just(ResponseEntity.ok(body));
    }

    @PostMapping(path = "/strict", consumes =
            MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Mono<String> createStrict(
            @Valid @ModelAttribute("eventForm") EventForm form) {
        return Mono.just("accepted:" + form.getTitle());
    }
}
~~~

**Tác động của `@InitBinder("eventForm")`**:
1. Spring WebFlux tạo binder cho model attribute có object name `eventForm` và gọi `configureBinder`.
2. `setAllowedFields` cho phép property binding chỉ ở năm nhóm fields; `approved` bị suppress dù client gửi.
3. `StringTrimmerEditor(true)` áp dụng cho String properties thông thường; `CouponCodeEditor` có path riêng nên làm uppercase coupon.
4. Hai `StrictLocalDateEditor` dùng đúng từng format thay vì một quy tắc chung cho mọi LocalDate.
5. Spring bind form/query parameters, sau đó `@Valid` yêu cầu Bean Validation.
6. `BindingResult` ngay sau model attribute cho phép handler trả lỗi gọn và an toàn. Endpoint `/events/strict` không có `BindingResult`, nên form invalid thường ném `WebExchangeBindException` và nhận HTTP 400.

`Mono.just(...)` là kiểu trả về của WebFlux handler; không phải lời khẳng định init binder chạy bất đồng bộ. Hook `@InitBinder` chỉ đăng ký editor cho binder hiện tại.

### 6.7. Controller thứ hai để chứng minh local scope

~~~java
// src/main/java/com/example/localeditor/RawEventController.java
package com.example.localeditor;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class RawEventController {

    @PostMapping(path = "/raw-events", consumes =
            MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Map<String, String> raw(
            @ModelAttribute("eventForm") EventForm form) {
        return Map.of("title", form.getTitle());
    }
}
~~~

Nó có cùng `@ModelAttribute("eventForm")` nhưng **không thuộc `EventController`**, nên không nhận local `@InitBinder` của controller kia. Với request `title="  Java Workshop  "`, text giữ khoảng trắng đầu/cuối khi không có global editor can thiệp. `@Valid` không có, nên hai ngày thiếu giá trị không gây Bean Validation error trong endpoint này.

### 6.8. Chạy bằng curl

~~~bash
mvn spring-boot:run
~~~

Ở terminal khác:

~~~bash
curl -i -X POST http://localhost:8080/events \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "title=  Java Workshop  " \
  --data-urlencode "startDate=25/12/2026" \
  --data-urlencode "endDate=2026-12-31" \
  --data-urlencode "coupon=  vip10  " \
  --data-urlencode "tags[0]=spring" \
  --data-urlencode "approved=true"
~~~

Kết quả JSON dự kiến, không cam kết thứ tự key:

~~~json
{
  "title": "Java Workshop",
  "startDate": "2026-12-25",
  "endDate": "2026-12-31",
  "coupon": "VIP10",
  "tags": ["spring"],
  "approved": false
}
~~~

Dấu `\` để nối dòng trong ví dụ phù hợp shell Linux/macOS/Git Bash. Trên PowerShell cần dùng cú pháp nối dòng tương ứng hoặc lệnh `curl.exe` một dòng.

## 7. Kiểm thử đăng ký editor

### 7.1. HTTP integration tests với WebTestClient

~~~java
// src/test/java/com/example/localeditor/EventControllerTest.java
package com.example.localeditor;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@AutoConfigureWebTestClient
@SpringBootTest
class EventControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void fieldAndTypeEditorsWorkTogether() {
        client.post()
                .uri("/events")
                .body(BodyInserters.fromFormData(
                        "title", "  Java Workshop  ")
                        .with("startDate", "25/12/2026")
                        .with("endDate", "2026-12-31")
                        .with("coupon", "  vip10  ")
                        .with("tags[0]", "spring")
                        .with("approved", "true"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.title").isEqualTo("Java Workshop")
                .jsonPath("$.startDate").isEqualTo("2026-12-25")
                .jsonPath("$.endDate").isEqualTo("2026-12-31")
                .jsonPath("$.coupon").isEqualTo("VIP10")
                .jsonPath("$.tags[0]").isEqualTo("spring")
                .jsonPath("$.approved").isEqualTo(false);
    }

    @Test
    void invalidDateIsBindingError() {
        client.post()
                .uri("/events")
                .body(BodyInserters.fromFormData(
                        "title", "Java Workshop")
                        .with("startDate", "31/02/2026")
                        .with("endDate", "2026-12-31"))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.invalidFields[0]")
                .isEqualTo("startDate");
    }

    @Test
    void blankTitleIsValidationError() {
        client.post()
                .uri("/events")
                .body(BodyInserters.fromFormData("title", "   ")
                        .with("startDate", "25/12/2026")
                        .with("endDate", "2026-12-31"))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.invalidFields[0]")
                .isEqualTo("title");
    }

    @Test
    void localEditorDoesNotLeakToOtherController() {
        client.post()
                .uri("/raw-events")
                .body(BodyInserters.fromFormData(
                        "title", "  Java Workshop  "))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.title")
                .isEqualTo("  Java Workshop  ");
    }

    @Test
    void strictHandlerReturns400ForInvalidForm() {
        client.post()
                .uri("/events/strict")
                .body(BodyInserters.fromFormData("title", " ")
                        .with("startDate", "25/12/2026")
                        .with("endDate", "2026-12-31"))
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

Bộ test kiểm tra:
- Khác biệt giữa editor type-wide và field-specific.
- Ngày không tồn tại gây error đúng field.
- Chuỗi toàn khoảng trắng bị editor chuyển thành null rồi bị `@NotBlank` phát hiện.
- Editor local không lan ra controller khác dù model attribute trùng tên.
- Endpoint không có `BindingResult` trả HTTP 400 khi Bean Validation thất bại.

### 7.2. Unit tests trực tiếp với WebDataBinder

~~~java
// src/test/java/com/example/localeditor/EventBinderTest.java
package com.example.localeditor;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.web.bind.WebDataBinder;

import java.time.LocalDate;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class EventBinderTest {

    private WebDataBinder configured(EventForm form) {
        WebDataBinder binder = new WebDataBinder(form, "eventForm");
        new EventController().configureBinder(binder);
        return binder;
    }

    @Test
    void typeAndPathSpecificConversion() {
        EventForm form = new EventForm();
        WebDataBinder binder = configured(form);

        binder.bind(new MutablePropertyValues(Map.of(
                "title", "  Java Workshop  ",
                "startDate", "25/12/2026",
                "endDate", "2026-12-31",
                "coupon", "  vip10  ",
                "approved", "true"
        )));

        assertFalse(binder.getBindingResult().hasErrors());
        assertEquals("Java Workshop", form.getTitle());
        assertEquals(LocalDate.of(2026, 12, 25),
                form.getStartDate());
        assertEquals(LocalDate.of(2026, 12, 31),
                form.getEndDate());
        assertEquals("VIP10", form.getCoupon());
        assertFalse(form.isApproved());
        assertArrayEquals(new String[]{"approved"},
                binder.getBindingResult().getSuppressedFields());
    }

    @Test
    void twoDatePathsHaveDifferentPatterns() {
        EventForm form = new EventForm();
        WebDataBinder binder = configured(form);

        binder.bind(new MutablePropertyValues(Map.of(
                "title", "Java",
                "startDate", "2026-12-25",
                "endDate", "25/12/2026"
        )));

        assertNotNull(binder.getBindingResult()
                .getFieldError("startDate"));
        assertNotNull(binder.getBindingResult()
                .getFieldError("endDate"));
    }

    @Test
    void bindingDoesNotAutomaticallyValidateAnnotations() {
        EventForm form = new EventForm();
        WebDataBinder binder = configured(form);

        binder.bind(new MutablePropertyValues(Map.of(
                "title", "    ",
                "startDate", "25/12/2026",
                "endDate", "2026-12-31"
        )));

        assertNull(form.getTitle());
        assertFalse(binder.getBindingResult().hasErrors());
        // Test không cấu hình Bean Validation provider và không gọi validate().
    }
}
~~~

Lệnh chạy:

~~~bash
mvn test
~~~

**Kết quả dự kiến:** 8 test PASS (5 test HTTP-level, 3 test binder). Đây là dự đoán theo API và cấu hình đã nêu, **không phải log runtime đã thực thi**. Nếu muốn chỉ chạy `EventBinderTest`:

~~~bash
mvn -Dtest=EventBinderTest test
~~~

Đặc biệt, test cuối cho thấy **editor chỉ thực hiện conversion**; `@NotBlank` chưa chạy vì binder được khởi tạo thủ công mà không gắn validator và không gọi `validate()`.

## 8. BindingResult và thông báo lỗi

Khi editor parse text, có ba tình huống khác nhau:

~~~text
startDate=31/02/2026
  -> DateTimeParseException
  -> BindingResult: lỗi chuyển kiểu, thường typeMismatch

title="   "
  -> StringTrimmerEditor(true) -> null
  -> @NotBlank (nếu validation chạy) -> lỗi NotBlank

approved=true
  -> Không thuộc setAllowedFields
  -> getSuppressedFields() chứa "approved"
  -> Không nhất thiết có FieldError
~~~

`FieldError#getField()` cho tên property như `startDate`; `getCode()` có thể là `typeMismatch` hoặc tên constraint; `getDefaultMessage()` là thông báo có thể phụ thuộc locale. **Không trả thẳng `getRejectedValue()` ra API** nếu form chứa token hoặc dữ liệu cá nhân.

Với WebFlux, object-only `@Valid @ModelAttribute` không có `BindingResult` ngay sau thường tạo `WebExchangeBindException` và 400. Nếu handler có direct method constraints như `@RequestParam @Min(1)`, Spring Framework 6.1+ có thể xử lý theo method validation và tạo `HandlerMethodValidationException`. Không gán tất cả lỗi 400 vào một nhánh exception duy nhất.

Nếu parse lỗi nhưng editor tự ném exception làm app dừng không qua binder, kiểm tra loại exception từ `setAsText`: một exception parse như `IllegalArgumentException` hoặc `DateTimeParseException` là tín hiệu thông thường để binding infrastructure ghi conversion error. Đừng tự nuốt lỗi và gán một ngày giả, vì như vậy form có thể được coi là hợp lệ sai.

## 9. Collection, nested path và requiredType

Với form có `List<Item> items`:

~~~text
items[0].quantity=2
items[1].quantity=5
~~~

Spring `PropertyEditorRegistry` mô tả cách đăng ký editor cho mọi index của nested property bằng canonical path:

~~~java
binder.registerCustomEditor(
        Integer.class,
        "items.quantity",
        new QuantityEditor());
~~~

`QuantityEditor` ở đây là **tên minh họa**, cần có implementation trước khi compile. Không nhất thiết đăng ký riêng `items[0].quantity`, `items[1].quantity`. Path dùng cho lookup có cơ chế bỏ index để tìm editor cho property tương ứng.

Ví dụ DTO minh họa:

~~~java
public class Item {
    private Integer quantity;

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

Một custom editor cho `Integer.class` nếu cần parse số lượng phải xử lý chính xác định dạng, phạm vi và conversion errors. Với `List<Item>`, cấu trúc target, constructor của item, setters và auto-grow cần phù hợp. `registerCustomEditor` **không tự sinh mọi object lồng nhau** nếu Spring không thể tạo một element.

Đặc biệt, editor cho **toàn collection** và editor cho **mỗi element** có ngữ nghĩa khác. Theo API, `requiredType` quyết định editor được dùng cho collection hay elements ở một path; không đặt cả hai với cùng property path và hy vọng pipeline tự gọi tuần tự.

## 10. Bảo mật và phạm vi ảnh hưởng

### 10.1. Editor không phải whitelist

`CouponCodeEditor` chuẩn hóa mã coupon, nhưng không có quyền quyết định client được sửa field nào. Nếu form có `approved`, `roles`, `account.ownerId` hoặc `paymentStatus`, tránh expose chúng trong input DTO. Ở mức binder:

~~~java
binder.setAllowedFields(
        "title", "startDate", "endDate", "coupon", "tags[*]");
~~~

Chỉ các property paths được cho phép mới được property-bind. Các fields bị chặn xuất hiện qua `BindingResult#getSuppressedFields()`; chúng không tự động là constraint violations.

Khuyến nghị:
1. Dùng input DTO nhỏ và riêng cho web.
2. Chọn whitelist `allowedFields` khi phải property-bind một object có nhiều setters.
3. Kiểm soát index/độ sâu collection, kích thước HTTP body.
4. Validate kiểu và format sau khi bind.
5. Kiểm tra authorization/ownership trong service, không dựa vào tên field do client gửi.

### 10.2. JSON @RequestBody đi đường khác

~~~http
POST /api/events HTTP/1.1
Content-Type: application/json

{"startDate":"25/12/2026","coupon":"vip10"}
~~~

Với `@RequestBody` JSON, Jackson/`HttpMessageReader` deserialize dữ liệu thay vì dùng form property-name binder như `@ModelAttribute`. **`registerCustomEditor` không phải cấu hình Jackson deserializer**, và `setAllowedFields` không lọc JSON properties giống form. Nếu JSON cần format ngày hoặc uppercase coupon, cấu hình JSON DTO/Jackson hoặc mapping service riêng.

### 10.3. Local không đồng nghĩa thread-local

Local `@InitBinder` nghĩa là **scope theo controller/model attribute**, không phải một editor global hay một field được giữ riêng cho mỗi thread bởi ứng dụng. Controller có thể là singleton; editor state nên được tạo lại cho từng binder, không lưu vào field dùng chung. Với WebFlux event loop, không block trong editor.

### 10.4. Đừng quên constructor binding

Spring Framework 6.1+ có constructor binding cho model attributes. `allowedFields` chủ yếu điều khiển **property binding**; nó không tự biến mọi constructor parameter thành các trường bị chặn. Với record/immutable DTO, hãy kiểm tra đường constructor, names, conversion và chính sách nhận input riêng. Một editor cần được test trên đúng binder mechanism dự kiến, thay vì giả định property binding test cũng chứng minh hành vi constructor binding.

## 11. Khi nào dùng Formatter hoặc Converter?

| Lựa chọn | Điểm mạnh | Khi phù hợp |
| --- | --- | --- |
| `PropertyEditor` qua `registerCustomEditor` | Local theo type/path, hỗ trợ JavaBeans | Legacy editor, một form có quy tắc đặc thù |
| `Converter<S,T>` | API type-safe, thường stateless | Chuyển kiểu chung qua `ConversionService` |
| `Formatter<T>` | Parse/print và có `Locale` | Ngày, số, tiền tệ và biểu diễn UI |
| `@DateTimeFormat` | Cấu hình ngắn tại field Java Time | Format ngày/giờ thông dụng |
| Jackson deserializer | Kiểm soát JSON input | `@RequestBody`, API JSON |

Với MVC, có thể đăng ký global formatter qua `WebMvcConfigurer#addFormatters`. Với WebFlux, dùng `WebFluxConfigurer#addFormatters`. Khi chỉ muốn một field cụ thể dùng parser, overload `registerCustomEditor(type,path,editor)` khá trực quan.

`PropertyEditor` có state và thiếu đối số `Locale` trong `setAsText`; `Formatter<T>` nhận `Locale` ở `parse`/`print`, dễ dùng cho i18n. Không thiết kế mặc định rằng converter, formatter và editor cùng chạy nối tiếp: conversion service chọn đường phù hợp với cấu hình và editor đã đăng ký.

## 12. Các lỗi phổ biến

| Triệu chứng | Nguyên nhân hay gặp | Cách khắc phục |
| --- | --- | --- |
| `registerCustomEditor` không chạy | `@InitBinder` không khớp model object name | So `@InitBinder("eventForm")` với `@ModelAttribute("eventForm")` |
| Editor ngày cho `startDate` không chạy | `propertyPath` bị thêm tiền tố `eventForm.` | Dùng path tương đối `startDate` |
| `endDate` dùng nhầm format của `startDate` | Chỉ đăng ký theo type `LocalDate.class` | Dùng overload có path |
| Editor String chung làm mất khoảng trắng quan trọng | `StringTrimmerEditor` type-wide quá rộng | Giới hạn field hoặc không trim loại dữ liệu đó |
| Ngày sai vẫn được chấp nhận | Parser không strict | Dùng `ResolverStyle.STRICT`, test 31/02 |
| `CustomDateEditor` không xử lý `LocalDate` | Nhầm `java.util.Date` với Java Time | Chọn editor đúng type |
| Giá trị bị rò giữa requests | Shared mutable editor/`SimpleDateFormat` | Khởi tạo editor mới per binder |
| Conversion lỗi nhưng chưa thấy constraint code | Editor ném type mismatch trước validation | Kiểm tra `BindingResult#getFieldErrors()` |
| `@NotBlank` không chạy | Chỉ bind mà chưa gọi validator | Dùng `@Valid` hoặc cấu hình và gọi `binder.validate()` |
| JSON không đi qua editor | Jackson deserialize `@RequestBody` | Dùng JSON deserializer/DTO đúng chỗ |
| Client sửa được `approved` | Thiếu allowlist/DTO riêng | `setAllowedFields` + authorization |
| List index cao gây lỗi/tốn tài nguyên | Auto-grow và giới hạn input | `setAutoGrowCollectionLimit`, body limits và field count limits |
| Controller khác cũng bị áp editor | `@ControllerAdvice`/global converter quá rộng | Thu hẹp scope và test controller khác |
| Editor có blocking I/O | Lạm dụng conversion làm nghiệp vụ | Chuyển sang reactive service |
| Một property không áp dụng hai editors như kỳ vọng | Chỉ một editor trên path; lookup ưu tiên path-specific | Gộp normalization nếu cần và test path |
| `getAsText()` không thay JSON output | JSON serialization không dùng JavaBeans editor | Cấu hình Jackson riêng |

## 13. Bài tập tự luyện

1. Viết `PhoneNumberEditor` cho field `contact.phone`, chỉ chuẩn hóa ký tự phân cách; dùng Bean Validation cho điều kiện đúng/sai.
2. Tạo ba field `LocalDate` cùng type nhưng khác định dạng; đăng ký editor type-wide và editor field-specific rồi viết test chứng minh ưu tiên.
3. Dùng form `List<Item>`, gửi `items[0].quantity` và `items[1].quantity`, đăng ký editor bằng path `items.quantity`.
4. Thay `StrictLocalDateEditor` bằng `@DateTimeFormat(pattern="dd/MM/uuuu")`, so sánh code và phạm vi.
5. Chuyển editor chung vào `@ControllerAdvice(assignableTypes=...)` rồi test controller nằm trong/ngoài phạm vi.
6. Gửi JSON `startDate=25/12/2026` và tìm hiểu vì sao binder editor không áp dụng; cấu hình Jackson phù hợp.
7. Thử `approved=true`, `tags[99999]` và thiếu `startDate`, phân biệt suppressed, conversion, auto-grow và validation.
8. Viết test chạy nhiều request cùng lúc; xác minh không chia sẻ một `PropertyEditorSupport` instance stateful.
9. Thêm constraint “`endDate` không trước `startDate`” bằng Spring `Validator` hoặc custom Jakarta constraint, **không** thêm vào editor parse ngày.

## 14. Checklist và tài liệu tham khảo

- [ ] Dùng `registerCustomEditor(type,editor)` khi cả type có cùng quy tắc, overload có `propertyPath` khi cần riêng field.
- [ ] Tên `@InitBinder` khớp `@ModelAttribute`, path tương đối với target bean.
- [ ] Khởi tạo editor stateful mới mỗi binder; không chia sẻ `SimpleDateFormat` mutable.
- [ ] Phân biệt parse/typeMismatch với Bean Validation/constraint errors.
- [ ] Đặt `BindingResult` ngay sau non-reactive `@ModelAttribute` khi cần xử lý lỗi trong controller.
- [ ] Dùng DTO input nhỏ, allowlist và kiểm tra authorization riêng.
- [ ] Test form WebFlux bằng `WebTestClient`, binder bằng `WebDataBinder`, không dùng `MockMvc` cho WebFlux.
- [ ] Không dùng editor để kỳ vọng thay đổi Jackson JSON serialization.
- [ ] Với conversion dùng chung và locale, ưu tiên `Converter`/`Formatter`/`ConversionService`.

**Tài liệu chính thức:**
- Spring Framework 6.2, `@InitBinder` trong MVC: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework 6.2, `@InitBinder` trong WebFlux: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-initbinder.html
- Spring Framework 6.2, PropertyEditor và Data Binding: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beans-beans.html
- Spring Framework 6.2, PropertyEditorRegistry Javadoc: https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/beans/PropertyEditorRegistry.html
- Spring Framework 6.2, DataBinder Javadoc: https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 6.2, WebFlux model attribute: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/modelattrib-method-args.html
- Spring Boot 3.5 testing: https://docs.spring.io/spring-boot/3.5/reference/testing/index.html
