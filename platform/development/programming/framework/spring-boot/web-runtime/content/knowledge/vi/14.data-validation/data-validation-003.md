# Ràng buộc tham số đường dẫn, query parameter và đối tượng lồng nhau trong Spring Boot

## 1. Bài toán và mục tiêu

Một API Spring Boot không chỉ cần đọc được tham số HTTP; nó còn phải kiểm tra xem dữ liệu đó có hợp lệ trước khi gọi business service hay không. Ba dạng đầu vào thường cùng xuất hiện trong một endpoint là:

- **Tham số đường dẫn** (`@PathVariable`): ví dụ ID danh mục trong `/categories/7/items`.
- **Query parameters** (`@RequestParam`): ví dụ `?page=2&sort=price`.
- **Đối tượng lồng nhau** được tạo từ query/form qua `@ModelAttribute` hoặc từ JSON qua `@RequestBody`: ví dụ `range.min=10`, `range.max=100`, `tags[0].name=eco`.

Ví dụ request:

~~~text
GET /api/categories/7/items?page=2&sort=price&range.min=10&range.max=100&tags[0].name=eco
~~~

Hợp đồng mong muốn:
- `categoryId` phải là số nguyên dương.
- `page` phải nằm trong khoảng 1–50.
- `sort` chỉ nhận `name` hoặc `price`.
- `range.min` và `range.max` không được thiếu, không âm, và min không lớn hơn max.
- Mỗi `tags[i].name` không được rỗng; tối đa ba tag.
- Input không hợp lệ phải bị từ chối trước khi chạy xử lý nghiệp vụ.
- Dữ liệu không được phép ghi vào DTO/domain object không được bind tùy ý.

Trong Spring MVC 6.1+ (Spring Boot 3.2+), **ràng buộc trên method parameters** và **validation của một object argument** có các đường xử lý và exception tương ứng. Nếu không phân biệt chúng, `@RestControllerAdvice` rất dễ chỉ bắt được một nửa lỗi.

Bài học sử dụng **Spring Boot 3.5.x, Java 17+, Spring Framework 6.2.x, Jakarta Bean Validation**. Ví dụ chính chạy trên Servlet MVC; cuối bài chỉ rõ điểm tương tự và khác biệt trong Spring WebFlux.

## 2. Bốn giai đoạn: route, chuyển kiểu, binding, validation

Trước khi một controller được gọi, Spring MVC trải qua các bước:

~~~text
HTTP request
   |
DispatcherServlet / HandlerMapping
   |  URL pattern có khớp /categories/{categoryId}/items?
   v
HandlerMethodArgumentResolver
   | @PathVariable, @RequestParam, @ModelAttribute, @RequestBody
   v
Type conversion / data binding / JSON deserialization
   |  "7" -> long 7; "2" -> int 2; "range.min" -> BigDecimal
   v
Jakarta Bean Validation / method validation nếu có
   |  @Positive, @Min, @Max, @Pattern, @Valid, @NotNull...
   v
Controller được gọi nếu đầu vào hợp lệ
   v
Service -> HTTP response
~~~

**Điểm cần nhớ:** binding và validation không phải một việc.

- **Routing:** URL có khớp mapping không. Không có handler phù hợp thường là 404.
- **Conversion:** biến dữ liệu dạng chuỗi thành `long`, `int`, enum, `BigDecimal`, `LocalDate`... Ví dụ `page=abc` không thể convert thành `int`.
- **Binding:** gắn nhiều dữ liệu vào object, kể cả nested properties và indexed collections.
- **Validation:** chỉ sau khi có giá trị phù hợp mới xét `@Min(1)`, `@NotBlank`, `@AssertTrue`, ràng buộc liên quan nhiều field.

Vì thế `/categories/abc/items` và `/categories/-3/items` đều có thể dẫn đến HTTP 400 nhưng nguyên nhân khác: trường hợp đầu là type conversion của path variable; trường hợp sau là Bean Validation `@Positive` nếu được bật.

## 3. Dependency bắt buộc để dùng Jakarta Bean Validation

Trong Spring Boot 3.x, starter web tự cung cấp Spring MVC nhưng **không nên giả định** nó luôn có đầy đủ Bean Validation provider. Để dùng `@NotBlank`, `@Min`, `@Valid`, hãy thêm:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Starter này thông thường đưa Hibernate Validator và Jakarta Validation API phù hợp vào classpath. Spring Boot tích hợp validator vào MVC khi có Bean Validation provider.

Imports điển hình:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
~~~

**Sai lầm dễ gặp:** import `javax.validation.*` từ tài liệu Spring Boot 2.x vào dự án Boot 3.x. Boot 3 dùng namespace **`jakarta.validation.*`**.

Không coi `@Valid` tự nó là một constraint. Nó kích hoạt việc kiểm tra các constraints của object được đánh dấu và có thể kích hoạt cascade validation; nếu DTO không có ràng buộc hoặc provider chưa được cấu hình thì annotation không làm input tự trở nên hợp lệ.

## 4. Ràng buộc tham số đường dẫn bằng @PathVariable

Ví dụ:

~~~java
@GetMapping("/categories/{categoryId}/items")
ResponseEntity<?> items(
        @PathVariable("categoryId") @Positive long categoryId) {
    // Dùng categoryId đã được convert và validate.
    return ResponseEntity.ok().build();
}
~~~

Đây là fragment trong một controller và cần các imports; ví dụ đầy đủ được trình bày ở mục 10.

Giải thích:
- `{categoryId}` là URI template variable.
- `@PathVariable("categoryId")` gắn chuỗi từ route vào tham số Java.
- Spring chuyển `"7"` thành `long 7`.
- `@Positive` yêu cầu số lớn hơn 0.
- Khi conversion/validation thất bại, Spring MVC thường trả 400 trước khi vào controller, trừ khi application đã tùy chỉnh xử lý lỗi.

### 4.1. Những trạng thái cần phân biệt

| Request | Route có khớp mẫu? | Kết quả thường gặp |
|---|---|---|
| `/categories/7/items` | Có | `categoryId=7`, kiểm tra `@Positive` đạt |
| `/categories/0/items` | Có | Type conversion đạt, `@Positive` thất bại: 400 |
| `/categories/-4/items` | Thường có | Type conversion đạt, `@Positive` thất bại: 400 |
| `/categories/abc/items` | Có | Không đổi `abc` thành `long`: thường 400 |
| `/categories/items` | Không khớp mẫu có ID | Thường 404, không phải lỗi `@Positive` |
| `/categories/7/items/extra` | Không khớp mapping đã khai báo | Thường 404 |

Lưu ý: route constraints như `/categories/{categoryId:[0-9]+}/items` có thể **chặn giá trị sai từ bước routing** và dẫn đến 404 thay vì Bean Validation 400. Hai cách thiết kế tạo ra hợp đồng HTTP khác nhau: route regex quyết định handler matching, còn `@Positive` là validation của argument đã match.

### 4.2. @Pattern và UUID path variables

Nếu ID là chuỗi có định dạng, có thể dùng:

~~~java
@GetMapping("/orders/{orderCode}")
String order(@PathVariable @Pattern(
        regexp = "[A-Z]{3}-[0-9]{4}") String orderCode) {
    return orderCode;
}
~~~

Đây là fragment của controller. `@Pattern` kiểm **giá trị sau khi binding**, không phải thay thế route matcher. Với kiểu `UUID`, Spring có converter riêng; chuỗi UUID sai format thường bị từ chối trong conversion trước validation.

Không dùng `@NotBlank` cho số `long`; chọn constraint tương thích với kiểu dữ liệu. `@Positive`/`@Min` dành cho số; `@Pattern` dành cho `CharSequence`.

## 5. Ràng buộc query parameter bằng @RequestParam

Spring MVC dùng `@RequestParam` để đọc query parameters và, với Servlet, các form parameters khi phù hợp.

~~~java
@GetMapping("/search")
Map<String, Object> search(
        @RequestParam(name = "page", defaultValue = "1")
        @Min(1) @Max(50) int page,

        @RequestParam(name = "sort", defaultValue = "name")
        @Pattern(regexp = "name|price") String sort) {

    return Map.of("page", page, "sort", sort);
}
~~~

Đây là fragment, cần imports của `Map`, `@GetMapping`, `@RequestParam`, constraints. Lưu ý:
- Query không có `page` hoặc có giá trị rỗng theo cơ chế default của `@RequestParam`: `defaultValue="1"` được sử dụng.
- `page=2`: được convert thành int và đạt `@Min`/`@Max`.
- `page=0`: convert được nhưng không đạt `@Min(1)`.
- `page=xyz`: conversion thất bại, không phải lỗi `@Min`.
- `sort=price`: hợp lệ.
- `sort=random`: không đạt `@Pattern`.

### 5.1. required, defaultValue và null

| Cách khai báo | Khi query key thiếu | Lưu ý |
|---|---|---|
| `@RequestParam String q` | Thường 400 vì required=true mặc định | Không đồng nghĩa q không phải blank |
| `@RequestParam(required=false) String q` | Có thể null | `@Size` thường cho phép null; nếu cần có giá trị hãy thêm constraint |
| `@RequestParam(defaultValue="1") int page` | Nhận giá trị mặc định 1 | `defaultValue` ngầm làm required=false |
| `@RequestParam Optional<String> q` | `Optional.empty()` | Constraint trực tiếp lên container/element cần chọn đúng target |
| `@RequestParam List<String> tags` | Có thể nhận repeated params | Cần ràng buộc kích thước/phần tử nếu nghiệp vụ yêu cầu |

Để bắt buộc query phải có nội dung có nghĩa, `required=true` **chỉ** đảm bảo tồn tại theo contract request parameter; nó không cấm `q=` hoặc chuỗi chỉ có khoảng trắng. Với `String`, thêm `@NotBlank` nếu không cho phép blank.

### 5.2. Lặp query key và collection element constraints

Ví dụ:

~~~java
@GetMapping("/tags")
List<String> tags(
        @RequestParam(name = "tag")
        @Size(max = 3) List<@NotBlank String> tags) {
    return tags;
}
~~~

Đây là fragment biểu diễn các loại constraint:
- `@Size(max=3)` kiểm **số phần tử**.
- `List<@NotBlank String>` kiểm **từng string** khi container element validation được thực hiện.
- Một client có thể gửi `?tag=eco&tag=new`.
- `@NotBlank` không áp dụng lên kiểu `List` trực tiếp vì constraint này dành cho chuỗi.

Cần kiểm thử khi sử dụng collection constraints trực tiếp trên method parameter vì đó là method validation; không suy ra một danh sách rỗng/không có query sẽ luôn được xem giống nhau.

## 6. @ModelAttribute: nhiều query fields thành một đối tượng lồng nhau

Khi có hàng chục query/form parameters, viết một `@RequestParam` cho từng field trở nên dài và khó quản lý. Spring MVC có thể tạo object qua `@ModelAttribute`:

~~~java
@GetMapping("/catalog")
ResponseEntity<?> catalog(
        @Valid @ModelAttribute("criteria") SearchCriteria criteria) {
    return ResponseEntity.ok(criteria);
}
~~~

Đây là fragment; class `SearchCriteria` được định nghĩa sau.

Request:

~~~text
GET /catalog?range.min=10&range.max=100&tags[0].name=eco&tags[1].name=organic
~~~

Binder nhận từng path:
- `range.min` → `criteria.range.min`;
- `range.max` → `criteria.range.max`;
- `tags[0].name` → phần tử thứ nhất trong danh sách `tags`;
- `tags[1].name` → phần tử thứ hai.

Trong Spring MVC, `@ModelAttribute` có thể tạo model object qua constructor hoặc dùng JavaBean property binding. Binder có thể tự tăng kích thước collection khi gặp indexed property; tính năng này có giới hạn và cần kiểm soát để tránh tiêu tốn tài nguyên.

### 6.1. Ràng buộc ở lớp cha và lớp con

Mẫu DTO mutable:

~~~java
class SearchCriteria {
    @Valid
    @NotNull
    private PriceRange range = new PriceRange();

    @Size(max = 3)
    private List<@Valid TagFilter> tags = new ArrayList<>();

    // Các getters/setters được định nghĩa trong class thực tế.
}

class PriceRange {
    @NotNull @DecimalMin("0")
    private BigDecimal min;

    @NotNull @DecimalMin("0")
    private BigDecimal max;
}

class TagFilter {
    @NotBlank
    private String name;
}
~~~

Đây là fragment, cần imports và getters/setters, chưa phải source độc lập. Quan hệ validation:

1. `@Valid` trên argument `SearchCriteria` yêu cầu validate object đầu vào.
2. `@Valid` trên field `range` yêu cầu **đi sâu** vào `PriceRange`.
3. `@NotNull` trên `range` bảo đảm child object không null; chỉ `@Valid` thì nếu child null, không tự báo lỗi.
4. `@NotNull` và `@DecimalMin` kiểm mỗi giá trị tiền tệ.
5. `List<@Valid TagFilter>` yêu cầu validate từng phần tử list; `@NotBlank` kiểm `name`.
6. `@Size(max=3)` kiểm số tag, không kiểm từng tag.
7. Spring chuyển chuỗi thập phân sang `BigDecimal` trước khi Jakarta Bean Validation kiểm giá trị.

**Nếu thiếu `@Valid` đúng chỗ, ràng buộc bên trong object lồng nhau có thể bị bỏ qua.** Chỉ đặt `@NotNull` ở parent không đủ để kiểm tra `range.min`, `range.max`.

### 6.2. Nested path và collection indexes có thể gây lỗi gì?

| Input | Nguyên nhân |
|---|---|
| `range.min=abc` | Không chuyển được `abc` sang BigDecimal |
| `range.min=-1` | Chuyển kiểu được; vi phạm `@DecimalMin("0")` |
| `range.min` không có | Có thể còn null; vi phạm `@NotNull` |
| `tags[0].name=` | Tag được tạo nhưng `@NotBlank` thất bại |
| `tags[0].name=eco&tags[1].name=new` | Hai phần tử hợp lệ nếu constraints khác đều đạt |
| `tags[3].name=extra` với size tối đa 3 | Có thể tạo 4 phần tử rồi vi phạm `@Size(max=3)` |
| `tags[999999].name=boom` | Có thể vượt giới hạn auto-grow và làm binding lỗi |

Đừng mở rộng `autoGrowCollectionLimit` vô hạn chỉ để nhận index lớn. Đặt giới hạn ở binder và áp dụng giới hạn kích thước collection/payload tại cửa vào phù hợp. Chỉ ràng buộc `@Size` **sau** binding không thay thế việc giới hạn chi phí cấp phát khi tạo object.

## 7. Cross-field validation: min phải nhỏ hơn hoặc bằng max

Các ràng buộc trên từng field không phát hiện được `min=100, max=10` nếu cả hai đều không âm. Đó là **ràng buộc liên thuộc**.

Cách gọn cho ví dụ JavaBean:

~~~java
@AssertTrue(message = "min phải nhỏ hơn hoặc bằng max")
public boolean isOrderValid() {
    return min == null || max == null || min.compareTo(max) <= 0;
}
~~~

Đây là method đặt trong `PriceRange` có hai field `BigDecimal min, max`. JavaBean convention nhận nó như một boolean property `orderValid`; Bean Validation kiểm `@AssertTrue`. Khi field null, method trả true để nhường lỗi “field bắt buộc” cho `@NotNull` thay vì sinh lỗi trùng.

Trong dự án lớn, ràng buộc nhiều field nên được mô tả bằng **class-level custom constraint** với `ConstraintValidator` để gắn error vào path phù hợp, tái sử dụng giữa nhiều DTO, hỗ trợ i18n và unit test tách biệt.

Không nên tự kiểm min/max trong mỗi controller sau khi đã cho phép service chạy. Validation nên được đặt ở lớp hợp đồng đầu vào hoặc lớp nghiệp vụ theo yêu cầu.

## 8. Method validation: một khác biệt quan trọng từ Spring Framework 6.1

Spring MVC có hai cấp validation phổ biến:

### 8.1. Validation của một argument object

Ví dụ:

~~~java
@PostMapping("/products")
ResponseEntity<?> create(
        @Valid @RequestBody CreateProductRequest input) {
    // ...
    return ResponseEntity.ok().build();
}
~~~

Nếu chỉ cần validation object `CreateProductRequest` và không có constraint trực tiếp khác buộc method validation, Spring MVC có thể ném `MethodArgumentNotValidException` khi DTO không hợp lệ.

### 8.2. Validation của toàn bộ handler method

Ví dụ:

~~~java
@GetMapping("/categories/{id}")
String get(
        @PathVariable @Positive long id,
        @RequestParam @Min(1) int page) {
    return "ok";
}
~~~

`@Positive` và `@Min` đặt trực tiếp trên method parameters yêu cầu **method validation**. Spring MVC 6.1+ hỗ trợ method validation tích hợp sẵn và thường ném `HandlerMethodValidationException` khi input không hợp lệ.

Khi một handler đồng thời có:
- `@Positive` trên `@PathVariable`;
- `@Min` trên `@RequestParam`;
- `@Valid` trên `@ModelAttribute` hoặc `@RequestBody`;

thì method validation có thể bao gồm cả nested validation của object và **thay thế** đường validation riêng từng argument. Vì vậy `@RestControllerAdvice` nên xử lý cả `HandlerMethodValidationException` và `MethodArgumentNotValidException` tùy chữ ký handler.

> `@Valid` **không** phải constraint trực tiếp. Một mình nó không tự buộc method validation; `@Min`, `@NotBlank`, `@NotNull` đặt trực tiếp lên parameter mới là ví dụ của constraint kích hoạt cơ chế ấy.

### 8.3. Không dùng @Validated ở cấp controller một cách máy móc

Trong Spring Framework 6.1+, annotation `@Validated` ở **class level** của controller có thể khiến method validation chạy qua AOP proxy thay vì support tích hợp của MVC. Exception và semantics có thể khác với `HandlerMethodValidationException`.

Nếu muốn dùng cơ chế method validation tích hợp của Spring MVC, tài liệu Framework khuyến nghị bỏ `@Validated` khỏi class controller. Không sao chép hướng dẫn Spring Boot 2.x “thêm @Validated trên controller để validate query params” mà không xét phiên bản mới.

Spring Boot cần Bean Validation provider phù hợp; chỉ dùng annotations mà thiếu dependency validation không đủ để đảm bảo checks thực thi.

## 9. BindingResult và cách thiết kế response lỗi

### 9.1. BindingResult phải nằm ngay sau object tương ứng

Trong controller form:

~~~java
@PostMapping("/filter")
ResponseEntity<?> filter(
        @Valid @ModelAttribute("criteria") SearchCriteria criteria,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body(errors.getFieldErrors()
                .stream().map(error -> error.getField()).toList());
    }
    return ResponseEntity.ok().build();
}
~~~

Đây là fragment, không phải method của ví dụ đầy đủ bên dưới. `BindingResult` phải đứng **ngay sau** object mà nó mô tả. Khi có ràng buộc trên những tham số method khác, controller chỉ được gọi nếu mọi lỗi đều có argument `Errors` liền sau tương ứng; nếu có lỗi ở những parameter không có local Errors, `HandlerMethodValidationException` vẫn được ném.

Với `@RequestBody` body JSON sai cú pháp, không có object để validate; `BindingResult` **không** chữa được `HttpMessageNotReadableException`.

### 9.2. Các lỗi có thể xuất hiện

| Nhóm lỗi | Ví dụ | Exception Spring MVC thường gặp |
|---|---|---|
| Không convert path/query | `categoryId=abc`, `page=xyz` | `MethodArgumentTypeMismatchException` và nhánh conversion errors |
| Thiếu query bắt buộc | Thiếu `q` khi `required=true` | `MissingServletRequestParameterException` |
| Object binding / validation | `@Valid @ModelAttribute` vi phạm constraint | `MethodArgumentNotValidException` khi validation riêng object được áp dụng |
| Method-level validation | `@Positive` trên path, `@Min` trên query | `HandlerMethodValidationException` |
| JSON không đọc được | Body sai JSON hoặc không deserialize được | `HttpMessageNotReadableException` |
| Sai `Content-Type` | Endpoint chỉ nhận JSON, gửi text/plain | `HttpMediaTypeNotSupportedException` |
| Không có route matching | Thiếu segment category ID | Thường 404, không đi qua validation |

Default behavior phần lớn lỗi input có thể trả **400 Bad Request**; media type thường trả **415**. Cấu hình custom exception handler, security, routing và phiên bản framework có thể thay mã phản hồi; kiểm thử API contract thay vì đóng đinh error body mặc định.

### 9.3. Error details an toàn

Nên trả error code nhất quán như `validation_failed`, danh sách field/path và message an toàn. Khi cần hỗ trợ client i18n, Spring có `MessageSource` và message codes của Bean Validation. Không trả stack trace, toàn bộ entity hoặc request body nhạy cảm.

Một `@RestControllerAdvice` có thể:
- Xử lý `MethodArgumentNotValidException` bằng `getBindingResult()`.
- Xử lý `HandlerMethodValidationException` bằng danh sách `ParameterValidationResult`.
- Để framework xử lý lỗi type conversion/404/415, hoặc định nghĩa handler riêng khi API có yêu cầu.

Ví dụ hoàn chỉnh ở mục 10 sử dụng hai nhánh exception validation, giữ nguyên mặc định framework cho các lỗi còn lại.

## 10. Ví dụ ứng dụng Spring Boot 3.5 và Java 17+ chạy được

Chúng ta tạo ứng dụng MVC có:
- GET: path variable + query parameters + nested `@ModelAttribute`.
- POST: path variable + nested JSON `@RequestBody`.
- Cả hai đều áp dụng method validation cho path variable; object được validate đệ quy.
- Query binder chỉ cho phép những property paths cần thiết.
- Tự động trả 400 với input sai, thông qua Spring MVC và handler validation.

### 10.1. pom.xml

Tạo thư mục Maven project, file `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>nested-validation-demo</artifactId>
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

Với Java 17+ và Maven, dự án dùng `spring-boot-starter-web` nên chạy Spring MVC trên Servlet container mặc định (thường Tomcat). Không thêm starter WebFlux ở ví dụ này.

### 10.2. Java source đầy đủ

Tạo `src/main/java/example/validation/NestedValidationApplication.java`:

~~~java
package example.validation;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@SpringBootApplication
public class NestedValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(NestedValidationApplication.class, args);
    }
}

@RestController
@RequestMapping("/api")
class CatalogController {

    @InitBinder("criteria")
    void limitFields(WebDataBinder binder) {
        binder.setAllowedFields("range.min", "range.max", "tags[*].name");
        binder.setAutoGrowCollectionLimit(8);
    }

    @GetMapping("/categories/{categoryId}/items")
    Map<String, Object> browse(
            @PathVariable("categoryId") @Positive long categoryId,
            @RequestParam(name = "page", defaultValue = "1")
            @Min(1) @Max(50) int page,
            @RequestParam(name = "sort", defaultValue = "name")
            @Pattern(regexp = "name|price") String sort,
            @Valid @ModelAttribute("criteria") SearchCriteria criteria) {

        return Map.of(
                "categoryId", categoryId,
                "page", page,
                "sort", sort,
                "min", criteria.getRange().getMin(),
                "max", criteria.getRange().getMax(),
                "tags", criteria.getTags().stream()
                        .map(TagChoice::getName).toList());
    }

    @PostMapping(
            path = "/categories/{categoryId}/items/search",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<Map<String, Object>> searchJson(
            @PathVariable("categoryId") @Positive long categoryId,
            @Valid @RequestBody JsonSearch input) {

        return ResponseEntity.ok(Map.of(
                "categoryId", categoryId,
                "min", input.range().min(),
                "max", input.range().max(),
                "tags", input.tags().stream()
                        .map(JsonTag::name).toList()));
    }
}

@RestControllerAdvice
class InputValidationAdvice {

    @ExceptionHandler(HandlerMethodValidationException.class)
    ResponseEntity<Map<String, Object>> onMethodValidation(
            HandlerMethodValidationException exception) {

        List<String> messages = exception.getAllValidationResults()
                .stream()
                .flatMap(result -> result.getResolvableErrors().stream())
                .map(error -> String.valueOf(error.getDefaultMessage()))
                .toList();

        return ResponseEntity.status(exception.getStatusCode())
                .body(Map.of(
                        "error", "validation_failed",
                        "details", messages));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<Map<String, Object>> onObjectValidation(
            MethodArgumentNotValidException exception) {

        List<String> messages = exception.getBindingResult()
                .getAllErrors()
                .stream()
                .map(error -> String.valueOf(error.getDefaultMessage()))
                .toList();

        return ResponseEntity.badRequest()
                .body(Map.of(
                        "error", "validation_failed",
                        "details", messages));
    }
}

class SearchCriteria {

    @Valid
    @NotNull
    private PriceBounds range = new PriceBounds();

    @Size(max = 3)
    private List<@Valid TagChoice> tags = new ArrayList<>();

    public SearchCriteria() {}

    public PriceBounds getRange() { return range; }
    public void setRange(PriceBounds range) { this.range = range; }

    public List<TagChoice> getTags() { return tags; }
    public void setTags(List<TagChoice> tags) { this.tags = tags; }
}

class PriceBounds {

    @NotNull
    @DecimalMin("0")
    private BigDecimal min;

    @NotNull
    @DecimalMin("0")
    private BigDecimal max;

    public PriceBounds() {}

    public BigDecimal getMin() { return min; }
    public void setMin(BigDecimal min) { this.min = min; }

    public BigDecimal getMax() { return max; }
    public void setMax(BigDecimal max) { this.max = max; }

    @AssertTrue(message = "min phải nhỏ hơn hoặc bằng max")
    public boolean isOrderValid() {
        return min == null || max == null || min.compareTo(max) <= 0;
    }
}

class TagChoice {

    @NotBlank
    private String name;

    public TagChoice() {}

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
}

record JsonSearch(
        @Valid @NotNull JsonPrice range,
        @NotNull @Size(max = 3) List<@Valid JsonTag> tags) {}

record JsonPrice(
        @NotNull @DecimalMin("0") BigDecimal min,
        @NotNull @DecimalMin("0") BigDecimal max) {

    @AssertTrue(message = "min phải nhỏ hơn hoặc bằng max")
    public boolean isOrderValid() {
        return min == null || max == null || min.compareTo(max) <= 0;
    }
}

record JsonTag(@NotBlank String name) {}
~~~

Lưu ý về mã:
- File có đúng một `public class` khớp tên tệp; DTO, controller và advice còn lại là package-private.
- `@Valid` nằm ở method argument và nested types; `@Positive`, `@Min`, `@Max`, `@Pattern` nằm trực tiếp trên parameters.
- `@InitBinder("criteria")` chỉ giới hạn property binding cho model attribute `criteria`, không áp dụng cho Jackson deserialization của `@RequestBody`.
- `tags[*].name` là allowedFields wildcard phù hợp các indexed property paths `tags[0].name`, `tags[1].name`...
- `setAutoGrowCollectionLimit(8)` chặn collection index quá lớn ở binder; `@Size(max=3)` tiếp tục kiểm giới hạn nghiệp vụ chặt hơn.
- Class controller **không** khai báo `@Validated` ở type level, vì muốn dùng method validation tích hợp Spring MVC 6.1+.
- `@RestControllerAdvice` minh họa hai exception validation chính; lỗi JSON sai cú pháp, type mismatch, route không khớp và media type sai vẫn được Spring MVC xử lý theo mặc định.
- Import `org.springframework.validation.annotation.Validated` ở bản minh họa không được sử dụng và có thể bỏ đi; không làm thay đổi chức năng.

Đây là ứng dụng minh họa, không truy cập database. Khi đầu vào hợp lệ, endpoint trả một `Map` mô tả giá trị đã bind để dễ kiểm chứng.

### 10.3. Khởi động

Tại thư mục Maven project:

~~~bash
mvn spring-boot:run
~~~

Giả định cổng 8080 đang rảnh, không có proxy hoặc security starter bổ sung. Bản build này tự tải dependencies cần thiết nếu Maven repository truy cập được.

## 11. Chạy thử bằng curl: cùng một request, nhiều lớp kiểm tra

### 11.1. GET với query + nested model attributes hợp lệ

~~~bash
curl -i -G "http://localhost:8080/api/categories/7/items" \
  --data-urlencode "page=2" \
  --data-urlencode "sort=price" \
  --data-urlencode "range.min=10" \
  --data-urlencode "range.max=100" \
  --data-urlencode "tags[0].name=eco"
~~~

Kết quả có ý nghĩa:

~~~json
{"categoryId":7,"page":2,"sort":"price","min":10,"max":100,"tags":["eco"]}
~~~

HTTP status dự kiến **200 OK**. JSON property order không có ý nghĩa hợp đồng; đừng viết test phụ thuộc vào thứ tự các key của `Map`.

### 11.2. POST JSON có đối tượng lồng nhau

~~~bash
curl -i -X POST \
  "http://localhost:8080/api/categories/7/items/search" \
  -H "Content-Type: application/json" \
  -d '{"range":{"min":10,"max":100},"tags":[{"name":"eco"}]}'
~~~

Kết quả có ý nghĩa:

~~~json
{"categoryId":7,"min":10,"max":100,"tags":["eco"]}
~~~

HTTP status dự kiến **200 OK**. Spring MVC dùng Jackson HTTP message converter để tạo `JsonSearch` record, sau đó validation đi vào `JsonPrice` và `JsonTag` nhờ `@Valid`.

### 11.3. Path variable không hợp lệ

~~~bash
curl -i -G "http://localhost:8080/api/categories/0/items" \
  --data-urlencode "range.min=10" \
  --data-urlencode "range.max=100"
~~~

Mã dự kiến **400**, bởi `categoryId=0` vi phạm `@Positive`. Lỗi xuất hiện trên method parameter, nên thường đi qua `HandlerMethodValidationException` trong Spring MVC 6.2.

~~~bash
curl -i -G "http://localhost:8080/api/categories/abc/items" \
  --data-urlencode "range.min=10" \
  --data-urlencode "range.max=100"
~~~

Mã cũng thường là **400**, nhưng ở lần này `abc` không convert được sang `long`. Không gọi đây là lỗi `@Positive`.

### 11.4. Query parameter không hợp lệ

~~~bash
# page vượt giới hạn
curl -i -G "http://localhost:8080/api/categories/7/items" \
  --data-urlencode "page=80" \
  --data-urlencode "range.min=10" \
  --data-urlencode "range.max=100"

# sort không thuộc các giá trị cho phép
curl -i -G "http://localhost:8080/api/categories/7/items" \
  --data-urlencode "sort=unknown" \
  --data-urlencode "range.min=10" \
  --data-urlencode "range.max=100"
~~~

Cả hai đều dự kiến **400** nếu chưa có custom error mapping.

### 11.5. Nested object không hợp lệ

~~~bash
# Ràng buộc liên thuộc: min > max
curl -i -G "http://localhost:8080/api/categories/7/items" \
  --data-urlencode "range.min=100" \
  --data-urlencode "range.max=10"

# Tag có name rỗng
curl -i -G "http://localhost:8080/api/categories/7/items" \
  --data-urlencode "range.min=10" \
  --data-urlencode "range.max=100" \
  --data-urlencode "tags[0].name="
~~~

Kết quả dự kiến **400** nếu nested validation được kích hoạt đúng. Với `range.min=100` và `range.max=10`, hai field riêng lẻ đạt `@DecimalMin("0")`, nhưng `@AssertTrue` trên `isOrderValid()` không đạt.

### 11.6. Dữ liệu vượt quy mô binder

Nếu client gửi index `tags[999999].name`, binder có thể không tăng collection lên kích thước đó do `setAutoGrowCollectionLimit(8)`. Trường hợp này có thể phát sinh binding/invalid-property exception trước cả `@Size(max=3)`. Kết quả chi tiết phụ thuộc cách binder và exception handler xử lý; đây là phần cần integration test nếu API chịu dữ liệu không tin cậy.

Không nên dùng request có hàng triệu phần tử để thử trên production. Hãy dùng môi trường test riêng và áp dụng rate limits, request-size limits và các biện pháp bảo vệ tài nguyên ở edge/server.

## 12. Test tự động bằng MockMvc

Tạo file `src/test/java/example/validation/NestedValidationApplicationTests.java`:

~~~java
package example.validation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class NestedValidationApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void acceptsValidPathQueryAndNestedModel() throws Exception {
        mvc.perform(get("/api/categories/7/items")
                .param("page", "2")
                .param("sort", "price")
                .param("range.min", "10")
                .param("range.max", "100")
                .param("tags[0].name", "eco"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.categoryId").value(7))
                .andExpect(jsonPath("$.page").value(2))
                .andExpect(jsonPath("$.tags[0]").value("eco"));
    }

    @Test
    void rejectsInvalidPathConstraint() throws Exception {
        mvc.perform(get("/api/categories/0/items")
                .param("range.min", "10")
                .param("range.max", "100"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsPageOutsideRange() throws Exception {
        mvc.perform(get("/api/categories/7/items")
                .param("page", "99")
                .param("range.min", "10")
                .param("range.max", "100"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsNestedCrossFieldRule() throws Exception {
        mvc.perform(get("/api/categories/7/items")
                .param("range.min", "100")
                .param("range.max", "10"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsBlankNestedTagName() throws Exception {
        mvc.perform(get("/api/categories/7/items")
                .param("range.min", "10")
                .param("range.max", "100")
                .param("tags[0].name", ""))
                .andExpect(status().isBadRequest());
    }

    @Test
    void acceptsNestedJson() throws Exception {
        mvc.perform(post("/api/categories/7/items/search")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"range":{"min":10,"max":100},
                     "tags":[{"name":"eco"}]}
                    """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.tags[0]").value("eco"));
    }

    @Test
    void rejectsInvalidNestedJson() throws Exception {
        mvc.perform(post("/api/categories/7/items/search")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"range":{"min":100,"max":10},
                     "tags":[{"name":"eco"}]}
                    """))
                .andExpect(status().isBadRequest());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Những test trên kiểm **HTTP contract** và validation thật trong Spring MVC test context. Không khẳng định nguyên văn order của `details` JSON vì thứ tự lỗi có thể khác theo validator và handler signature. Trong trường hợp controller có direct parameter constraints, `HandlerMethodValidationException` là nhánh cần kiểm; khi chỉ có object `@Valid`, `MethodArgumentNotValidException` có thể là nhánh được gọi.

MockMvc không thay thế mọi integration test với Tomcat nhúng. Nếu cần kiểm các giới hạn kích thước URI, proxy, query encoding hoặc security filters ngoài test slice, chạy full application trên cổng ngẫu nhiên và gửi request qua HTTP thực.

## 13. Validation groups: tạo và cập nhật có thể có luật khác nhau

Một DTO dùng cho hai nghiệp vụ có thể cần các tập constraints khác nhau:

- Tạo mới: `name` bắt buộc, ID chưa có.
- Cập nhật: ID bắt buộc, một số field cho phép trống.
- Tìm kiếm: khoảng giá tùy chọn, giới hạn số tag khác request tạo mới.

Jakarta Bean Validation hỗ trợ **validation groups** và Spring `@Validated(SomeGroup.class)`. Ví dụ minh họa:

~~~java
interface CreateGroup {}
interface UpdateGroup {}

record ProductInput(
        @NotBlank(groups = CreateGroup.class)
        String name,

        @NotNull(groups = UpdateGroup.class)
        Long id) {}
~~~

Đây là fragment DTO và marker interfaces. Khi khai báo `@Validated(CreateGroup.class) @RequestBody ProductInput input`, validator kiểm constraints thuộc group đó. Khác với `@Valid`, `@Validated` còn hỗ trợ Spring validation hints/groups. Tuy nhiên:
- Constraints thuộc group `Default` không mặc nhiên được chạy khi chọn một group khác, trừ khi định nghĩa hoặc sequence phù hợp.
- Cascade validation sang nested objects cũng có thể cần cấu hình groups/`@ConvertGroup` khi group policy phức tạp.
- Đừng dùng một DTO quá rộng rồi kỳ vọng groups tự bảo vệ over-posting; request DTO riêng thường dễ hiểu và an toàn hơn.

Khi có method validation và group validation cùng lúc, kiểm tra behavior theo đúng Spring Framework version và exception handlers đang dùng; không suy luận chỉ từ annotation trên một field.

## 14. Đối tượng lồng nhau trong JSON khác gì nested query parameters?

Có hai đường xử lý khác nhau:

| Đặc điểm | Nested `@ModelAttribute` | Nested `@RequestBody` |
|---|---|---|
| Dữ liệu đầu vào | Query/form và các nguồn binder hỗ trợ | Body JSON/XML khi converter hỗ trợ |
| Đường tới nested field | `range.min=10`, `tags[0].name=eco` | `{"range":{"min":10},"tags":[{"name":"eco"}]}` |
| Thành phần tạo object | `WebDataBinder`, constructor/property binding | Jackson hoặc `HttpMessageConverter` tương ứng |
| Cách giới hạn writable fields | DTO và `@InitBinder.setAllowedFields` cho property binding | JSON DTO, Jackson config, deserializer policies |
| Lỗi chuyển kiểu | Binder/type mismatch | Parser/deserializer exception |
| Cascade validation | `@Valid` trên nested fields/elements | `@Valid` trên nested fields/elements |
| Collection index | Binder có auto-grow limit | JSON parser tạo list từ mảng; có request/body size limits riêng |
| Lỗi do body rỗng | Không phụ thuộc JSON body | `@RequestBody` mặc định required=true |
| Media type | Phù hợp form/query semantics | `Content-Type: application/json` cho JSON |

Một đoạn JSON không tự được bind bởi `@ModelAttribute` nếu client gửi `application/json`; và `@RequestBody` không tự ghép query parameters vào DTO JSON. Cùng một nested validation DTO concept nhưng đường tạo object và lỗi conversion khác nhau.

## 15. Bảo mật dữ liệu đầu vào và giới hạn tài nguyên

### 15.1. Mass assignment và nested paths

Nếu bind thẳng entity domain bằng `@ModelAttribute`, client có thể gửi `user.role=ADMIN`, `order.ownerId=...`, `account.balance=999999` khi setter tương ứng có mặt. Đây là **mass assignment/over-posting**, không phải bug của Bean Validation.

Các biện pháp:
1. Request DTO chỉ chứa những field được phép sửa.
2. Với mutable property binding, `@InitBinder` và `setAllowedFields` giới hạn đường property có thể bind.
3. Không bind trực tiếp JPA entity từ database bằng request parameters.
4. Xác thực quyền cập nhật field ở service/domain layer; validation không thay thế authorization.
5. Với JSON `@RequestBody`, cũng cần DTO/deserialization policy và mapping an toàn sang entity. JSON không miễn nhiễm mass assignment.
6. Giới hạn nested collection depth/index, request size và số parameter để giảm nguy cơ resource exhaustion.

Trong ví dụ, binder chỉ cho phép:
- `range.min`;
- `range.max`;
- `tags[*].name`.

Không có đường `ownerId` hay `admin` trong DTO. Nhưng `allowedFields` trên property binding **không** phải bộ lọc JSON của Jackson; không dùng nó thay request-body DTO.

### 15.2. Validation không thay database/business rules

`@Positive` kiểm một ID lớn hơn 0, nhưng không chứng minh bản ghi có thật hoặc caller có quyền xem. `@Pattern` kiểm format code, không xác thực code tồn tại. `@DecimalMin` kiểm số không âm, không kiểm quota, số dư hay giá hiện hành.

Flow đúng:
1. Xác thực và phân quyền (theo hợp đồng security).
2. Bind/convert input.
3. Validate cú pháp, cấu trúc, độ dài và quan hệ field.
4. Business service kiểm trạng thái, quyền sở hữu, tồn tại tài nguyên và quy tắc giao dịch.
5. Chọn mã HTTP theo hợp đồng API: 400 do input không hợp lệ, 404 nếu tài nguyên vắng mặt, 403 nếu thiếu quyền, 409 khi xung đột trạng thái, v.v.

Không mặc định `@Valid` đã bảo đảm an toàn dữ liệu.

## 16. Spring WebFlux: cùng khái niệm, runtime và lỗi khác

Spring WebFlux cũng hỗ trợ `@PathVariable`, `@RequestParam`, `@ModelAttribute`, `@RequestBody`, `@Valid` và method validation. Nhưng:
- `@RequestBody` đọc qua reactive `HttpMessageReader`/codec, có thể nhận `Mono<T>`.
- `@ModelAttribute` dùng binder reactive-aware để xử lý form/query và nested object paths.
- Nếu validation riêng một argument object thất bại, WebFlux thường ném `WebExchangeBindException`.
- Method-level constraints như `@Positive` trên path hoặc `@Min` trên query có thể dẫn đến `HandlerMethodValidationException`.
- `@Valid` một mình vẫn không phải constraint trực tiếp, cơ chế lựa chọn method validation tương tự về mặt ý tưởng.
- Không gọi `block()` trong event loop chỉ để “đọc DTO” trước khi validate.

Fragment minh họa WebFlux (không nằm trong project MVC mục 10):

~~~java
@PostMapping(path = "/reactive/search",
        consumes = MediaType.APPLICATION_JSON_VALUE)
Mono<ResponseEntity<String>> reactiveSearch(
        @Valid @RequestBody Mono<JsonSearch> input) {
    return input.map(value ->
            ResponseEntity.ok("tags=" + value.tags().size()));
}
~~~

Đây là fragment yêu cầu các imports WebFlux và DTO `JsonSearch` thích hợp. Việc validate reactive body wrapper và trả lỗi qua publisher khác với nhận một DTO đồng bộ trong MVC. Nếu cần xử lý invalid body riêng, dùng WebFlux `@ExceptionHandler` hoặc các operator phù hợp, không tái sử dụng Servlet `BindingResult` assumptions cho `Mono<DTO>`.

Đừng kết luận ứng dụng đang chạy WebFlux chỉ vì có `WebClient` trên classpath. Khi cả starter-web và starter-webflux cùng tồn tại, Spring Boot thường ưu tiên MVC server; cần xác định web application type thực tế.

## 17. Các lỗi thường gặp

1. **Thiếu `spring-boot-starter-validation` nhưng tin `@Min` sẽ chạy.** Kiểm dependency provider.
2. **Thêm `@Valid` chỉ ở top-level DTO, quên nested `@Valid`.** Child constraints có thể không được kiểm.
3. **Dùng `@NotBlank` trên kiểu số.** Constraint không tương thích; dùng `@Positive`, `@Min`.
4. **Xem `page=abc` là vi phạm `@Min`.** Đó là lỗi conversion.
5. **Dùng route regex để thay mọi validation và không xét 404/400.** Hai tầng trả kết quả khác nhau.
6. **Chỉ bắt `MethodArgumentNotValidException`.** Có thể bỏ sót `HandlerMethodValidationException` khi method có constraints trực tiếp.
7. **Đặt `@Validated` trên controller theo hướng dẫn cũ mà không xét Spring 6.1+.** Có thể dùng AOP validation với exception khác.
8. **Đặt `BindingResult` không ngay sau object.** Không nhận lỗi local đúng tham số.
9. **Cho rằng `@Size(max=3)` ngăn binder cấp phát collection rất lớn.** Đây là hai lớp giới hạn khác nhau.
10. **Gửi nested JSON nhưng dùng `@ModelAttribute`.** Sai đường đọc dữ liệu, nên dùng `@RequestBody`.
11. **Dùng `@RequestBody` nhưng mong tự nhận `range.min` từ query.** Không tự ghép nguồn.
12. **Chỉ kiểm @NotNull range mà không cascade vào PriceBounds.** Không kiểm min/max.
13. **Không kiểm quan hệ giữa min và max.** Từng field đúng vẫn có thể tạo khoảng giá sai.
14. **Bind thẳng domain entity vào object lồng nhau.** Nguy cơ mass assignment và sai authorization.
15. **Coi 400 có cùng exception/error body trong mọi trường hợp.** Conversion, missing, method validation và JSON parse có paths khác nhau.
16. **Dùng test slice không tải validation config hoặc advice thật rồi kết luận production hành xử tương đương.** Kiểm đúng context.
17. **Không test path/query URL encoding.** `curl --data-urlencode` giúp tránh lỗi với brackets/dấu cách trong tham số.
18. **Bỏ qua null trong container elements.** `List<@Valid TagChoice>` không mặc nhiên cấm null elements; nếu cần thì kết hợp `List<@NotNull @Valid TagChoice>`.
19. **Dùng `@Min` với BigDecimal cho giá không âm nhưng bỏ qua độ chính xác.** Nên cân nhắc `@Digits`, `@DecimalMin` và ràng buộc scale/rounding theo nghiệp vụ.
20. **Kiểm dữ liệu ở controller rồi để service khác bỏ qua kiểm tra nghiệp vụ.** Validation HTTP và domain invariants có vai trò bổ trợ, không thay thế nhau.

## 18. Checklist kiểm tra trước khi merge

- [ ] Endpoint xác định rõ path variables, query parameters, model attributes và JSON body.
- [ ] Các ID có constraint hợp kiểu (`@Positive`/`@Min`/`@Pattern`) và có phương án khi không tìm được resource.
- [ ] Query keys có `required`/`defaultValue`/nullability rõ ràng.
- [ ] Các số, enum, date có conversion/format phù hợp và test input sai kiểu.
- [ ] Các DTO lồng nhau có `@Valid` ở đúng cha/field/element.
- [ ] Field bắt buộc dùng `@NotNull`/`@NotBlank` phù hợp; không nhầm với `@Valid`.
- [ ] Collections có `@Size` và binder có giới hạn auto-grow khi dùng indexed model attributes.
- [ ] Các quan hệ giữa field đã được kiểm bằng `@AssertTrue` hoặc custom class-level constraint.
- [ ] Bean Validation provider đã được thêm vào dependencies.
- [ ] Không đặt class-level `@Validated` trên MVC controller nếu muốn method validation tích hợp và không có lý do AOP.
- [ ] Error handler bao phủ `HandlerMethodValidationException` và `MethodArgumentNotValidException` khi cần, cùng lỗi type conversion/JSON parse theo contract.
- [ ] Request DTO được giới hạn trường; nested property binding dùng allowedFields nếu là mutable form object.
- [ ] Response lỗi không tiết lộ stack trace, token hoặc dữ liệu nhạy cảm.
- [ ] Đã test trường hợp 200, 400 (constraints, nested, conversion), 404 và 415 khi liên quan.
- [ ] Đã test đúng MVC/WebFlux runtime thay vì trộn lẫn exception paths.
- [ ] Business layer còn kiểm quyền và invariants không thể suy từ Bean Validation.

## 19. Kết luận

Ràng buộc dữ liệu trong Spring Boot cần nhìn từ **toàn bộ đường đi của request**. `@PathVariable` và `@RequestParam` bind từng giá trị rồi có thể kiểm constraints trực tiếp ở cấp handler method; `@ModelAttribute` và `@RequestBody` tạo DTO qua binder hoặc message converter, sau đó kiểm cấu trúc đệ quy bằng `@Valid` trên các nhánh nested. Từ Spring MVC 6.1+, ràng buộc trực tiếp trên method parameters có thể kích hoạt `HandlerMethodValidationException`, khác đường `MethodArgumentNotValidException` của validation một object. Bảo vệ API bằng DTO hẹp, constraints đúng kiểu, giới hạn binder, error contract nhất quán, kiểm thử request thực và validation bổ sung ở domain/service.

## Tài liệu chính thức

- Spring Framework 6.2 — MVC Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 — MVC @ModelAttribute: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.2 — MVC @RequestParam: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestparam.html
- Spring Framework 6.2 — MVC @PathVariable: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/pathvariable.html
- Spring Framework 6.2 — MVC @InitBinder: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework 6.2 — Spring Data Binding: https://docs.spring.io/spring-framework/reference/6.2/core/validation/data-binding.html
- Spring Framework 6.2 — WebFlux Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html
- Spring Boot 3.5 — Bean Validation: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
