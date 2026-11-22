# MockMvc cho lỗi binding, validation và hợp đồng phản hồi trong Spring MVC

## 1. Mục tiêu: kiểm thử đúng nguyên nhân lỗi, không chỉ HTTP 400

Một API Spring MVC có thể trả **400 Bad Request** cho nhiều yêu cầu rất khác nhau:

```http
GET /api/count
```

Thiếu tham số query bắt buộc.

```http
GET /api/count?count=abc
```

Có query nhưng String không chuyển thành `Integer`.

```http
GET /api/page?page=0
```

Chuyển kiểu thành công nhưng vi phạm `@Min(1)` đặt trực tiếp trên handler parameter.

```http
POST /api/items
Content-Type: application/json

{"name":" ","quantity":0,"delivery":{"city":""}}
```

JSON giải mã được, nhưng các field vi phạm Jakarta Bean Validation.

```http
POST /api/items
Content-Type: application/json

{"name":"Book","quantity":{"unexpected":1},"delivery":{"city":"Hue"}}
```

JSON đúng cú pháp nhưng **không chuyển được** object thành `Integer quantity`; đây là lỗi decode/conversion của JSON, chưa phải lỗi `@Min`.

```http
POST /api/form
Content-Type: application/x-www-form-urlencoded

name=Book&quantity=abc
```

`@ModelAttribute` có thể chứa một `FieldError` do **binding failure**, chứ không phải một constraint violation.

Nếu chỉ viết:

```java
mvc.perform(post("/api/items").content(invalidJson))
   .andExpect(status().isBadRequest());
```

test sẽ pass ngay cả khi API vô tình đổi từ `CONSTRAINT_VIOLATION` thành `BODY_UNREADABLE`, trả stack trace ra client, bỏ mất field code, hoặc thay định dạng lỗi mà frontend phụ thuộc. **HTTP status chỉ là một phần của hợp đồng phản hồi.**

Bài này tập trung vào **kiểm thử** qua Spring Test `MockMvc`:
1. Kích hoạt chính xác các nhánh **argument presence**, **type conversion**, **data binding**, **Bean Validation**, **handler method validation**.
2. Phân biệt `MethodArgumentNotValidException` với `HandlerMethodValidationException` và `HttpMessageNotReadableException`.
3. Thiết kế một JSON error contract ổn định gồm `code`, `issues[]` và category theo field.
4. Dùng `ResponseEntityExceptionHandler` để tập trung chuẩn hóa lỗi.
5. Dùng `MockMvc` xác minh status, content type, cấu trúc, mã lỗi, field paths, thứ tự, nội dung bị cấm và response thành công.
6. Tránh các test fragile dựa vào message nội bộ của Spring hay thứ tự ngẫu nhiên của constraint violations.
7. Hiểu phạm vi của `@WebMvcTest`, `@SpringBootTest`, `MockMvcBuilders.standaloneSetup` và trường hợp cần real server test.

**Ngữ cảnh:** Spring Framework 6.2.x, Spring Boot 3.5.6, Java 17+, Jakarta Validation 3.x, Spring MVC Servlet stack. Các API/annotation có thể thay đổi giữa Spring 5, 6 và 7; không sao chép nguyên imports hoặc exception routing sang WebFlux.

## 2. Bảng phân loại cần thuộc trước khi viết test

| Request/hợp đồng | Lỗi ở giai đoạn | Exception thường gặp ở Spring MVC | Mã API đề xuất |
| --- | --- | --- | --- |
| Thiếu `@RequestParam(required=true)` | Argument resolution | `MissingServletRequestParameterException` | `MISSING_PARAMETER` |
| `count=abc` cho `Integer` | Type conversion | `MethodArgumentTypeMismatchException` | `TYPE_MISMATCH` |
| JSON body trống khi `@RequestBody(required=true)` | Message reading | `HttpMessageNotReadableException` | `BODY_UNREADABLE` |
| JSON malformed, ví dụ thiếu dấu `}` | JSON parser | `HttpMessageNotReadableException` | `BODY_UNREADABLE` |
| JSON field là object, Java field là Integer | Jackson deserialization | `HttpMessageNotReadableException` | `BODY_UNREADABLE` |
| `@Valid @RequestBody` DTO có `@NotBlank` sai | Bean Validation cho argument | `MethodArgumentNotValidException` | `VALIDATION_ERROR` |
| `@Valid @ModelAttribute` form có `quantity=abc` | DataBinder | `FieldError.isBindingFailure()==true`, có thể trong `MethodArgumentNotValidException` | `BINDING_ERROR` |
| `@Valid @ModelAttribute` form có `name=""` | Bean Validation trên binder target | `FieldError.isBindingFailure()==false` | `VALIDATION_ERROR` |
| `@Min(1)` trực tiếp trên `@RequestParam` | MVC method validation (6.1+) | `HandlerMethodValidationException` | `METHOD_VALIDATION_ERROR` |
| Constraint trên giá trị trả về của handler | MVC method validation (6.1+) | `HandlerMethodValidationException`, status thường 500 | `SERVER_CONTRACT_VIOLATION` |

**Lưu ý:** Đây là các tình huống thông thường khi có Bean Validation provider và Spring MVC 6.1+. Kết quả còn phụ thuộc chữ ký handler, `BindingResult`, class-level `@Validated`, conversion service, custom argument resolver, exception advice và cấu hình ứng dụng. Vì vậy bản thân **integration tests** là nguồn xác nhận hợp đồng thật của project.

### 2.1. Binding error không đồng nghĩa constraint error

Với form:

```java
public class ItemForm {
    @NotBlank String name;
    @NotNull @Min(1) Integer quantity;
}
```

Request `quantity=abc`:
- `"abc"` không convert được thành `Integer`.
- Spring binder ghi lỗi `typeMismatch` (với `FieldError.isBindingFailure()==true`).
- Có thể còn Bean Validation lỗi `@NotNull` nếu giá trị sau binding là null, tùy cách binder/validator xử lý field đã lỗi; **không đoán số lượng FieldErrors tuyệt đối**.
- Test nên assert **có** binding error phù hợp, không ràng buộc mọi trường hợp chỉ được phép có đúng một lỗi.

Request `quantity=0`:
- Conversion thành công.
- `@Min(1)` phát hiện giá trị không hợp lệ.
- Trường hợp này là **constraint violation**, không phải conversion error.

### 2.2. Một exception class có thể chứa nhiều loại lỗi

`MethodArgumentNotValidException` không phải lúc nào cũng có nghĩa chỉ Jakarta constraint: với `@ModelAttribute`, `BindingResult` có thể chứa **type mismatch** hoặc những lỗi bind khác.

Vì vậy khi chuyển lỗi thành JSON, hãy phân loại **mỗi `FieldError`** bằng `isBindingFailure()`, không chỉ phân loại theo class exception.

### 2.3. Argument validation khác handler method validation

Spring MVC 6.1+ phân biệt:
- `@Valid @RequestBody ItemRequest` không có direct constraint trên method parameter khác: thường là **argument validation**, ném `MethodArgumentNotValidException` khi không có `Errors/BindingResult` ngay sau.
- `@RequestParam("page") @Min(1) int page`: có **direct method constraint**, dùng built-in handler method validation, có thể ném `HandlerMethodValidationException`.
- Nếu handler vừa có direct `@Min` vừa có `@Valid` cho một DTO, method validation có thể bao phủ cả cascading DTO constraints.

Do đó một advice ổn định cần hỗ trợ **cả hai exception types**. Đừng đặt class-level `@Validated` lên controller chỉ để kích hoạt `@Min`: Spring Framework lưu ý class-level `@Validated` có thể đổi sang proxy-based AOP method validation, khác cơ chế MVC 6.1+.

## 3. Xác định hợp đồng phản hồi trước khi test

Ta sử dụng một response minh họa, **không phải định dạng bắt buộc của Spring**:

```json
{
  "code": "VALIDATION_ERROR",
  "issues": [
    {
      "field": "name",
      "code": "NotBlank",
      "category": "constraint"
    },
    {
      "field": "quantity",
      "code": "Min",
      "category": "constraint"
    }
  ]
}
```

Trong đó:
- `code`: category chính của request, là một **machine-readable string** ổn định.
- `issues[]`: danh sách lỗi có cấu trúc để frontend xác định field và lý do.
- `field`: property path hoặc tên tham số do API định nghĩa.
- `issues[].code`: mã lỗi ổn định trong project, ví dụ `NotBlank`, `Min`, `typeMismatch`, `required`, `invalid`.
- `category`: `presence`, `binding` hoặc `constraint`.
- Danh sách `issues` được **sort theo field rồi code** và loại duplicates để test không lệ thuộc thứ tự provider.

Ví dụ lỗi thiếu query:

```json
{
  "code": "MISSING_PARAMETER",
  "issues": [
    {
      "field": "count",
      "code": "required",
      "category": "presence"
    }
  ]
}
```

Ví dụ JSON decoder không đọc được body:

```json
{
  "code": "BODY_UNREADABLE",
  "issues": []
}
```

Ví dụ lỗi binding của form:

```json
{
  "code": "BINDING_ERROR",
  "issues": [
    {
      "field": "quantity",
      "code": "typeMismatch",
      "category": "binding"
    }
  ]
}
```

Trong sản phẩm thật có thể chọn **RFC 9457 Problem Details** (`ProblemDetail`), thêm `type`, `title`, `status`, `detail`, `instance` và extension code. Dù chọn schema nào, hãy test **schema được công bố**, không sao chép một Spring exception text có thể thay theo version hoặc locale.

### 3.1. Đừng để `message` hiển thị là API code

Một câu tiếng Anh như `"must be greater than or equal to 1"` là **display text**; người dùng locale vi có thể nhận câu khác. Không nên test rằng message mặc định Hibernate Validator luôn khớp từng ký tự nếu hợp đồng chỉ cam kết **field + code + status**.

Thay vào đó:
- Assert `code="Min"` ổn định trong ranh giới project.
- Nếu ứng dụng chủ động định nghĩa localized message contract, tạo resource bundles và test locale một cách riêng biệt.
- Không biến raw message của `ex.getMessage()` thành mã lỗi.

### 3.2. Không trả dữ liệu nhạy cảm

`FieldError.getRejectedValue()` có thể chứa password, token, email hoặc request text. `HttpMessageNotReadableException` có thể chứa Jackson path/implementation details. Không đưa các giá trị này, stack trace, method signature hoặc exception Java class names vào JSON public.

Bài kiểm thử bảo mật phải xác minh raw rejected value không bị phản chiếu trong response (ngoài trường hợp dữ liệu đó là một message được business contract cho phép hiển thị).

## 4. MockMvc làm được gì và không làm được gì?

`MockMvc` tạo request/response giả đi qua Spring MVC infrastructure:
- Handler mapping và argument resolution.
- `HttpMessageConverter` (ví dụ Jackson JSON).
- ConversionService/WebDataBinder cho query/form.
- Bean Validation, `@ControllerAdvice` và exception resolvers.
- Response serialization, status/headers/content type.

`MockMvc` **không bắt buộc mở cổng TCP**; với `@SpringBootTest(webEnvironment=MOCK)` và `@AutoConfigureMockMvc`, nó thường dùng mock Servlet environment.

Nó **không thay thế** test real servlet container cho:
- Networking/proxy, TLS, HTTP/2.
- Các giới hạn request/body do container áp dụng.
- Real error-page dispatch, compression/transfer encoding.
- Deployment-specific security/network filters không có trong test context.

Đừng nói “MockMvc là end-to-end qua mạng”. Đây là **integration test ở tầng MVC**, đủ tin cậy để kiểm tra binder, validation và handler advice nếu cấu hình context đúng.

### 4.1. Ba kiểu thiết lập phổ biến

| Cách | Khởi tạo | Phù hợp |
| --- | --- | --- |
| `@WebMvcTest(MyController.class)` | MVC slice, MockMvc auto-configured | Test controller/advice mà không kéo toàn bộ repository/business beans |
| `@SpringBootTest + @AutoConfigureMockMvc` | ApplicationContext gần ứng dụng thực, không mở TCP mặc định | Test tương tác giữa MVC config, validators, converters, advices |
| `MockMvcBuilders.standaloneSetup(...)` | Setup controller trực tiếp, phải cấu hình dependencies/resolvers thủ công | Unit-ish MVC tests cần kiểm soát rất hẹp |

Đối với lỗi binding và validation, **whole-context test có thể đáng giá** để chứng minh thực tế starter validation, Jackson và exception advice đã được đăng ký. Dự án bên dưới chọn cách này để giảm nguy cơ giả lập thiếu MVC components.

### 4.2. Khi `@WebMvcTest` có thể cho kết quả giả

Một `@WebMvcTest` không quét mọi `@Service`/`@Repository` như full application. Nếu controller phụ thuộc service, dùng `@MockitoBean` hoặc cấu hình test bean phù hợp. Đảm bảo advice/converters liên quan có mặt. Một web slice có thể vô tình **không** sử dụng global `WebMvcConfigurer` hoặc custom bean mà production đang dùng.

Ngược lại, `@SpringBootTest` tốn thời gian hơn; dùng hợp lý thay vì mở full context cho mọi trường hợp unit validation nhỏ.

## 5. Cách tổ chức một test tốt: Arrange → Act → Assert

Ví dụ:

```java
@Test
void missingRequiredParameterReturnsStableErrorContract()
        throws Exception {

    mvc.perform(get("/api/count"))
            .andExpect(status().isBadRequest())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.code")
                    .value("MISSING_PARAMETER"))
            .andExpect(jsonPath("$.issues[0].field")
                    .value("count"))
            .andExpect(jsonPath("$.issues[0].code")
                    .value("required"));
}
```

Ý nghĩa:
- **Arrange:** route và input xác định (cố ý không có `count`).
- **Act:** request đi qua MockMvc.
- **Assert:** HTTP status, content type, machine code và field path.

Đây là snippet; class và imports đầy đủ ở phần dự án. Trong response contract, đừng assert toàn bộ JSON serialization bằng một chuỗi vì JSON object key ordering không được bảo đảm. Dùng `jsonPath` hoặc `content().json(...)` theo ngữ nghĩa cấu trúc.

### 5.1. `andExpect` hay `andDo(print())`?

`andExpect(...)` là assertion xác thực hợp đồng. `andDo(print())` chỉ hỗ trợ debug request/response, không làm test “pass đúng hơn”. Khi phải debug:
- Dùng `andDo(print())` tạm thời trong môi trường phù hợp.
- Không log raw request body có secrets lên CI public logs.
- Sau khi sửa lỗi, giữ assertions biểu đạt yêu cầu thực.

### 5.2. `andReturn()` hữu ích khi cần kiểm tra sâu

`MvcResult result = mvc.perform(...).andReturn();` cho phép lấy `MockHttpServletResponse` và `getResolvedException()`. Có thể assert **exception type** để bảo đảm một request đi qua đúng nhánh MVC:

```java
mvc.perform(get("/api/count").param("count", "abc"))
        .andExpect(result ->
                assertInstanceOf(
                        MethodArgumentTypeMismatchException.class,
                        result.getResolvedException()));
```

Đoạn minh họa cần imports và test context đầy đủ. **Không dùng exception type làm toàn bộ response contract**: client HTTP không nhận một Java exception class. Khi cần chứng minh cả hai, assert error envelope và resolved exception trong cùng test hoặc các test riêng.

## 6. Dự án mẫu Java 17 + Spring Boot 3.5.6

Dự án dùng một API quản lý mặt hàng với:
1. Query `count` cho missing/type mismatch.
2. Query `page` gắn `@Min(1)` cho MVC method validation.
3. JSON `CreateItemRequest` gắn `@Valid` và nested `Delivery`.
4. Form `ItemForm` nhận setter-bound data, có đường xử lý **local BindingResult** và đường **unhandled** đi qua advice.
5. Error envelope thống nhất `ApiError`.
6. `ApiExceptionHandler` kế thừa `ResponseEntityExceptionHandler`.
7. Bộ MockMvc tests kiểm tra từng nhánh và contract.

Spring Boot **3.5.6** là một phiên bản cố định cho ví dụ, **không ngụ ý bản mới nhất**. Không dùng Spring Boot 4 imports trong dự án này. Cần JDK 17+ và Maven tải được các dependencies.

### 6.1. Cấu trúc thư mục

```text
mockmvc-contract-demo/
├── pom.xml
├── src/main/java/demo/contract/
│   ├── ContractApplication.java
│   ├── CreateItemRequest.java
│   ├── ItemForm.java
│   ├── ApiError.java
│   ├── ItemController.java
│   └── ApiExceptionHandler.java
└── src/test/java/demo/contract/
    ├── QueryAndMethodValidationTest.java
    ├── JsonValidationContractTest.java
    ├── FormBindingContractTest.java
    └── ResponseContractSecurityTest.java
```

### 6.2. `pom.xml`

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
    <artifactId>mockmvc-contract-demo</artifactId>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

- `spring-boot-starter-web` cung cấp Spring MVC Servlet + Jackson converter và Tomcat cho chạy server.
- `spring-boot-starter-validation` cung cấp Jakarta Validation provider trong cấu hình thông thường; **không có nó** thì chỉ đặt `@NotBlank` không bảo đảm có validation như kỳ vọng.
- `spring-boot-starter-test` có JUnit Jupiter, Spring Test MockMvc, Hamcrest/AssertJ liên quan.
- Không cần database, không cần credentials và không tạo testcontainers.

### 6.3. `ContractApplication.java`

```java
package demo.contract;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContractApplication {
    public static void main(String[] args) {
        SpringApplication.run(ContractApplication.class, args);
    }
}
```

### 6.4. `CreateItemRequest.java`

```java
package demo.contract;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateItemRequest(

        @NotBlank(message = "name.required")
        @Size(max = 12, message = "name.tooLong")
        String name,

        @NotNull(message = "quantity.required")
        @Min(value = 1, message = "quantity.tooSmall")
        Integer quantity,

        @NotNull(message = "delivery.required")
        @Valid
        Delivery delivery) {

    public record Delivery(
            @NotBlank(message = "delivery.city.required")
            String city) {
    }
}
```

**Vì sao dùng `Integer` chứ không phải `int`?** JSON không gửi `quantity` hoặc gửi `null` sẽ thành `null` (trong cấu hình Jackson thông thường), và `@NotNull` có thể phân biệt với `quantity=0`. `@Min` tự nó thường cho phép null, nên không thay thế `@NotNull`.

`@NotBlank` từ chối null, rỗng và chuỗi chỉ có khoảng trắng. `@Size(max=12)` từ chối tên quá dài nhưng không tự xử lý khoảng trắng trống như `@NotBlank`. Hai constraint có thể cùng được khai báo trên một field; không dựa vào thứ tự collection của các violations.

`@NotNull @Valid Delivery` giúp phân biệt:
- Thiếu toàn bộ nested object `delivery` → `NotNull` ở path `delivery`.
- Object có `city=""` → `NotBlank` ở path `delivery.city`.

### 6.5. `ItemForm.java`

```java
package demo.contract;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class ItemForm {

    @NotBlank(message = "name.required")
    private String name;

    @NotNull(message = "quantity.required")
    @Min(value = 1, message = "quantity.tooSmall")
    private Integer quantity;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
```

Mutable JavaBean này là request DTO nhỏ cho form. Nó không có field quyền/owner/id; các trường hợp nhạy cảm như `approved`, `role`, `ownerId` không được phép thuộc input DTO công khai.

### 6.6. `ApiError.java` — định nghĩa một schema có thể kiểm thử

```java
package demo.contract;

import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;

import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.stream.Stream;

public record ApiError(String code, List<Issue> issues) {

    public record Issue(
            String field,
            String code,
            String category) {
    }

    public static ApiError simple(String code) {
        return new ApiError(code, List.of());
    }

    public static ApiError one(
            String code,
            String field,
            String issueCode,
            String category) {
        return new ApiError(code,
                List.of(new Issue(field, issueCode, category)));
    }

    public static ApiError fromBindingResult(BindingResult result) {

        Stream<Issue> fieldIssues = result.getFieldErrors().stream()
                .map(error -> new Issue(
                        error.getField(),
                        error.isBindingFailure()
                                ? "typeMismatch"
                                : Objects.requireNonNullElse(
                                        error.getCode(), "invalid"),
                        error.isBindingFailure()
                                ? "binding"
                                : "constraint"));

        Stream<Issue> globalIssues = result.getGlobalErrors().stream()
                .map(error -> new Issue(
                        "_object",
                        Objects.requireNonNullElse(
                                error.getCode(), "invalid"),
                        "constraint"));

        List<Issue> issues = Stream.concat(fieldIssues, globalIssues)
                .distinct()
                .sorted(Comparator.comparing(Issue::field)
                        .thenComparing(Issue::code)
                        .thenComparing(Issue::category))
                .toList();

        boolean hasBindingFailure = result.getFieldErrors()
                .stream()
                .anyMatch(FieldError::isBindingFailure);

        String responseCode = hasBindingFailure
                ? "BINDING_ERROR"
                : "VALIDATION_ERROR";

        return new ApiError(responseCode, issues);
    }
}
```

Đây là **toàn bộ implementation** của error schema demo:
- `record` khiến response data immutable ở mức record references.
- `issues` được sắp xếp ổn định theo field/code/category.
- `FieldError.isBindingFailure()` phân biệt bind/type errors với constraint validation.
- Các `ObjectError` cấp object được gán field logic `_object` để không bị mất.
- Không đưa `getRejectedValue()`, exception message, stack trace hay internal Java type vào payload.
- Nếu nhiều lỗi cùng field, các issue có code khác nhau vẫn được giữ; chỉ duplicates hoàn toàn giống nhau bị loại.

**Không hiểu sai:** `FieldError.getCode()` phụ thuộc vào annotation/validator được áp dụng. Trong demo dùng Jakarta constraints `@NotBlank`, `@Min`, `@NotNull`, `@Size`; các mã thông dụng tương ứng là `NotBlank`, `Min`, `NotNull`, `Size`. Nếu dự án có custom MessageCodesResolver hoặc custom Spring Validator, hãy định nghĩa mapping machine codes phù hợp thay vì coi mọi `getCode()` là public contract vĩnh viễn.

### 6.7. `ItemController.java` — các nhánh lỗi cần kiểm thử

```java
package demo.contract;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api")
public class ItemController {

    // Không gắn @Validated ở class level:
    // dùng MVC built-in method validation từ Spring 6.1+.

    @GetMapping("/count")
    public Map<String, Integer> count(
            @RequestParam("count") Integer count) {
        return Map.of("count", count);
    }

    @GetMapping("/page")
    public Map<String, Integer> page(
            @RequestParam("page") @Min(1) int page) {
        return Map.of("page", page);
    }

    @PostMapping(path = "/items",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Map<String, Object>> create(
            @Valid @RequestBody CreateItemRequest request) {

        Map<String, Object> body = Map.of(
                "name", request.name(),
                "quantity", request.quantity(),
                "city", request.delivery().city());

        return ResponseEntity.status(HttpStatus.CREATED).body(body);
    }

    @InitBinder("itemForm")
    void restrictForm(WebDataBinder binder) {
        binder.setAllowedFields("name", "quantity");
    }

    @PostMapping(path = "/form-local",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> formLocal(
            @Valid @ModelAttribute("itemForm") ItemForm form,
            BindingResult errors) {

        // Suppressed fields không nhất thiết là FieldError.
        if (errors.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest()
                    .body(ApiError.simple("UNEXPECTED_FIELD"));
        }

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(ApiError.fromBindingResult(errors));
        }

        return ResponseEntity.ok(Map.of(
                "name", form.getName(),
                "quantity", form.getQuantity()));
    }

    @PostMapping(path = "/form-unhandled",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Map<String, Object> formUnhandled(
            @Valid @ModelAttribute("itemForm") ItemForm form) {

        // Không có BindingResult ngay sau DTO:
        // MVC có thể ném MethodArgumentNotValidException.
        return Map.of(
                "name", form.getName(),
                "quantity", form.getQuantity());
    }

    @NotNull
    @GetMapping("/server-contract")
    public String brokenReturnContract() {
        // Endpoint cố tình sai hậu điều kiện, CHỈ DÙNG CHO TEST.
        return null;
    }
}
```

**Vì sao có hai endpoint form gần giống nhau?**
- `form-local()` đặt `BindingResult` **ngay sau** `@ModelAttribute`. Controller có thể đọc và phản hồi error locally.
- `form-unhandled()` không có `BindingResult`; Spring thường ném `MethodArgumentNotValidException` để global advice xử lý.

Không sử dụng `@RequestBody` để chứng minh `setAllowedFields` chặn Jackson: JSON deserialization có pipeline khác. `@InitBinder("itemForm")` giới hạn setter/property binding cho form. Trong project production, vẫn phải kiểm tra authorization và dùng DTO đầu vào riêng.

**Vì sao có endpoint trả null?** Nó là một fixture cố ý vi phạm `@NotNull` trên return value, dùng để kiểm tra HTTP **500** chứ không phải chuyển mọi constraint error thành 400. **Không triển khai endpoint này trong sản phẩm thực**.

### 6.8. `ApiExceptionHandler.java` — trả hợp đồng lỗi thống nhất

```java
package demo.contract;

import org.springframework.beans.TypeMismatchException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

@RestControllerAdvice
public class ApiExceptionHandler extends ResponseEntityExceptionHandler {

    private ResponseEntity<Object> reply(
            HttpHeaders headers,
            HttpStatusCode status,
            ApiError error) {

        return new ResponseEntity<>(error, headers, status);
    }

    @Override
    protected ResponseEntity<Object> handleMissingServletRequestParameter(
            MissingServletRequestParameterException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return reply(headers, status, ApiError.one(
                "MISSING_PARAMETER",
                ex.getParameterName(), "required", "presence"));
    }

    @Override
    protected ResponseEntity<Object> handleTypeMismatch(
            TypeMismatchException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        if (status.is5xxServerError()) {
            // Ví dụ conversion config không được hỗ trợ ở phía server.
            return reply(headers, status,
                    ApiError.simple("SERVER_CONVERSION_ERROR"));
        }

        String field =
                ex instanceof MethodArgumentTypeMismatchException mismatch
                        ? mismatch.getName()
                        : "parameter";

        return reply(headers, status, ApiError.one(
                "TYPE_MISMATCH",
                field, "typeMismatch", "binding"));
    }

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        // Không echo raw body, Jackson exception text hay stack trace.
        return reply(headers, status,
                ApiError.simple("BODY_UNREADABLE"));
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return reply(headers, status,
                ApiError.fromBindingResult(ex.getBindingResult()));
    }

    @Override
    protected ResponseEntity<Object> handleHandlerMethodValidationException(
            HandlerMethodValidationException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        if (ex.isForReturnValue()) {
            // Trả lỗi hợp đồng của server, không công bố dữ liệu return.
            return reply(headers, status,
                    ApiError.simple("SERVER_CONTRACT_VIOLATION"));
        }

        List<ApiError.Issue> issues = new ArrayList<>();

        for (var parameterResult : ex.getAllValidationResults()) {
            var parameter = parameterResult.getMethodParameter();
            var query = parameter.getParameterAnnotation(
                    RequestParam.class);

            String field = "arg" + parameter.getParameterIndex();

            if (query != null) {
                if (!query.value().isBlank()) {
                    field = query.value();
                } else if (!query.name().isBlank()) {
                    field = query.name();
                }
            }

            for (var error : parameterResult.getResolvableErrors()) {
                // Duy trì detail cho nested DTO nếu MVC đưa FieldError.
                if (error instanceof FieldError fieldError) {
                    issues.add(new ApiError.Issue(
                            field + "." + fieldError.getField(),
                            fieldError.getCode() == null
                                    ? "invalid"
                                    : fieldError.getCode(),
                            fieldError.isBindingFailure()
                                    ? "binding"
                                    : "constraint"));
                } else {
                    issues.add(new ApiError.Issue(
                            field, "invalid", "constraint"));
                }
            }
        }

        List<ApiError.Issue> ordered = issues.stream()
                .distinct()
                .sorted(Comparator.comparing(ApiError.Issue::field)
                        .thenComparing(ApiError.Issue::code)
                        .thenComparing(ApiError.Issue::category))
                .toList();

        return reply(headers, status,
                new ApiError("METHOD_VALIDATION_ERROR", ordered));
    }
}
```

**Các quyết định có chủ đích trong handler:**
- Kế thừa `ResponseEntityExceptionHandler` và **override protected methods** thay vì khai báo thêm `@ExceptionHandler` trùng mapping của superclass.
- Giữ nguyên `HttpStatusCode status` do Spring cung cấp; không đổi return-value violation 500 thành 400.
- Giữ `HttpHeaders` do Spring chuyển vào; không tự tạo headers trống trong mỗi handler.
- `handleMethodArgumentNotValid` phân loại dựa trên `BindingResult` thực, không coi mọi FieldError là Jakarta constraint.
- `handleHandlerMethodValidationException` dùng `getAllValidationResults()` để lấy parameter-specific results, không parse exception text.
- Vì handler method có thể kiểm tra nhiều arguments, kết quả được sắp xếp ổn định.
- Với direct `@Min` trên `page`, demo chọn issue code `invalid` chung; nếu API cần mã cụ thể như `Min` cho method validation, cần mapping có kiểm thử dựa trên metadata `MessageSourceResolvable`/ConstraintViolation/visitor phù hợp.

**Giới hạn của demo:** `@RequestParam` được nhận diện theo annotation và lấy tên explicit `value/name`; với `@RequestHeader`, `@PathVariable`, `@ModelAttribute` phức tạp, cần mở rộng mapping parameter name và nested paths theo handler contract. Không coi `arg0` là tên field nên hiển thị cho người dùng trong API production. `getAllValidationResults()` là API Spring MVC method validation, không áp dụng cho mọi AOP `ConstraintViolationException` ở service.

### 6.9. Tính nhất quán của response

Với code trên, những lỗi phát hiện bởi:
- Argument resolver cho query.
- Jackson message converter cho JSON.
- WebDataBinder cho form.
- Jakarta validator trên DTO.
- MVC method validation.

đều đi qua một dạng:

```json
{
  "code": "SOME_STABLE_CODE",
  "issues": []
}
```

Không có `timestamp`, `trace` hoặc `exception` trong JSON demo. Nếu API production dùng `ProblemDetail`, hãy thay schema tập trung và cập nhật contract tests cho client, không thay rải rác trong từng controller.

## 7. MockMvc: kiểm thử thiếu/sai kiểu/query và method validation

### 7.1. `QueryAndMethodValidationTest.java`

```java
package demo.contract;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.bind.MissingServletRequestParameterException;

import static org.hamcrest.Matchers.aMapWithSize;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class QueryAndMethodValidationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validCountReturnsSuccess() throws Exception {
        mvc.perform(get("/api/count").param("count", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.count").value(2));
    }

    @Test
    void missingCountHasOwnCodeAndField() throws Exception {
        mvc.perform(get("/api/count"))
                .andExpect(status().isBadRequest())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.code")
                        .value("MISSING_PARAMETER"))
                .andExpect(jsonPath("$.issues[0].field")
                        .value("count"))
                .andExpect(jsonPath("$.issues[0].code")
                        .value("required"))
                .andExpect(jsonPath("$.issues[0].category")
                        .value("presence"))
                .andExpect(result -> assertInstanceOf(
                        MissingServletRequestParameterException.class,
                        result.getResolvedException()));
    }

    @Test
    void invalidCountIsTypeMismatchNotMissing() throws Exception {
        mvc.perform(get("/api/count").param("count", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("TYPE_MISMATCH"))
                .andExpect(jsonPath("$.issues[0].field")
                        .value("count"))
                .andExpect(jsonPath("$.issues[0].code")
                        .value("typeMismatch"))
                .andExpect(result -> assertInstanceOf(
                        MethodArgumentTypeMismatchException.class,
                        result.getResolvedException()));
    }

    @Test
    void zeroIsAllowedWhenOnlyConversionIsRequired() throws Exception {
        mvc.perform(get("/api/count").param("count", "0"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.count").value(0));
    }

    @Test
    void validPagePassesDirectMin() throws Exception {
        mvc.perform(get("/api/page").param("page", "1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.page").value(1));
    }

    @Test
    void zeroPageTriggersMvcMethodValidation() throws Exception {
        mvc.perform(get("/api/page").param("page", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("METHOD_VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[0].field")
                        .value("page"))
                .andExpect(jsonPath("$.issues[0].code")
                        .value("invalid"))
                .andExpect(jsonPath("$.issues[0].category")
                        .value("constraint"))
                .andExpect(result -> assertInstanceOf(
                        HandlerMethodValidationException.class,
                        result.getResolvedException()));
    }

    @Test
    void wrongTypeIsRejectedBeforeMinConstraint() throws Exception {
        mvc.perform(get("/api/page").param("page", "not-an-int"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("TYPE_MISMATCH"));
    }

    @Test
    void returnValueConstraintFailureStaysServerError()
            throws Exception {

        mvc.perform(get("/api/server-contract"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code")
                        .value("SERVER_CONTRACT_VIOLATION"))
                .andExpect(jsonPath("$.issues", hasSize(0)))
                .andExpect(result -> assertInstanceOf(
                        HandlerMethodValidationException.class,
                        result.getResolvedException()));
    }
}
```

Đây là lớp kiểm tra **argument presence**, **type mismatch**, **handler method validation** và **return-value contract violation**. Việc assert resolved exception giúp bắt regression khi một thay đổi signature khiến request đi sang nhánh framework khác, còn `jsonPath` kiểm tra API contract client thực sự nhìn thấy.

**Sắc thái:** Request `count=` (tham số có mặt nhưng rỗng) có thể đi vào nhánh *missing after conversion* với wrapper `Integer`. Nếu thêm test đó, kiểm tra `MissingServletRequestParameterException.isMissingAfterConversion()` trong phiên bản cụ thể; đừng khẳng định mọi chuỗi rỗng luôn là `MethodArgumentTypeMismatchException`.

## 8. MockMvc: JSON decoder và Bean Validation

### 8.1. `JsonValidationContractTest.java`

```java
package demo.contract;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.MethodArgumentNotValidException;

import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class JsonValidationContractTest {

    @Autowired
    MockMvc mvc;

    private static final String VALID = """
            {
              "name":"Book",
              "quantity":2,
              "delivery":{"city":"Hue"}
            }
            """;

    @Test
    void validJsonCreatesItem() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(VALID))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.name").value("Book"))
                .andExpect(jsonPath("$.quantity").value(2))
                .andExpect(jsonPath("$.city").value("Hue"));
    }

    @Test
    void missingBodyIsNotAConstraintViolation() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(""))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BODY_UNREADABLE"))
                .andExpect(jsonPath("$.issues", hasSize(0)))
                .andExpect(result -> assertInstanceOf(
                        HttpMessageNotReadableException.class,
                        result.getResolvedException()));
    }

    @Test
    void malformedJsonIsUnreadable() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BODY_UNREADABLE"));
    }

    @Test
    void jsonFieldWrongJavaTypeIsUnreadable() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "name":"Book",
                              "quantity":{"unexpected":true},
                              "delivery":{"city":"Hue"}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BODY_UNREADABLE"));
    }

    @Test
    void blankNameHasNotBlankViolation() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "name":"  ",
                              "quantity":2,
                              "delivery":{"city":"Hue"}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[0].field")
                        .value("name"))
                .andExpect(jsonPath("$.issues[0].code")
                        .value("NotBlank"))
                .andExpect(jsonPath("$.issues[0].category")
                        .value("constraint"))
                .andExpect(result -> assertInstanceOf(
                        MethodArgumentNotValidException.class,
                        result.getResolvedException()));
    }

    @Test
    void missingQuantityTriggersNotNull() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "name":"Book",
                              "delivery":{"city":"Hue"}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[0].field")
                        .value("quantity"))
                .andExpect(jsonPath("$.issues[0].code")
                        .value("NotNull"));
    }

    @Test
    void zeroQuantityTriggersMinNotTypeMismatch() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "name":"Book",
                              "quantity":0,
                              "delivery":{"city":"Hue"}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[0].code").value("Min"))
                .andExpect(jsonPath("$.issues[0].field")
                        .value("quantity"));
    }

    @Test
    void missingDeliveryHasOwnNotNullPath() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {"name":"Book","quantity":2}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issues[0].field")
                        .value("delivery"))
                .andExpect(jsonPath("$.issues[0].code")
                        .value("NotNull"));
    }

    @Test
    void nestedCityHasNestedFieldPath() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "name":"Book",
                              "quantity":2,
                              "delivery":{"city":""}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issues[0].field")
                        .value("delivery.city"))
                .andExpect(jsonPath("$.issues[0].code")
                        .value("NotBlank"));
    }

    @Test
    void tooLongNameTriggersSize() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "name":"VeryLongProductName",
                              "quantity":2,
                              "delivery":{"city":"Hue"}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issues[0].field")
                        .value("name"))
                .andExpect(jsonPath("$.issues[0].code")
                        .value("Size"));
    }

    @Test
    void multipleViolationsAreReturnedAsStableFieldList()
            throws Exception {

        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "name":"",
                              "quantity":0,
                              "delivery":{"city":""}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[*].field",
                        hasItem("name")))
                .andExpect(jsonPath("$.issues[*].field",
                        hasItem("quantity")))
                .andExpect(jsonPath("$.issues[*].field",
                        hasItem("delivery.city")));
    }

    @Test
    void validJsonStillUsesSameSuccessContract() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(VALID))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.name").value("Book"));
    }
}
```

Các test cố tình phân biệt:
- **Body rỗng / JSON malformed / wrong Java type** → `BODY_UNREADABLE`.
- **DTO đã tạo được nhưng vi phạm constraint** → `VALIDATION_ERROR`.
- **Nested cascade**: path `delivery.city`.
- **Có nhiều violations**: kiểm tra sự hiện diện của từng field thay vì trói test vào thứ tự tùy ý của provider.

Ở test nhiều lỗi, `issues[]` được sắp xếp ở `ApiError.fromBindingResult`, nên có thể bổ sung assertion thứ tự nếu order là một contract được công bố. Tuy nhiên frontend nên căn cứ vào **field/code**, không suy luận ý nghĩa nghiệp vụ từ vị trí phần tử trong array.

## 9. MockMvc: BindingResult cục bộ và global exception advice

### 9.1. `FormBindingContractTest.java`

```java
package demo.contract;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.MethodArgumentNotValidException;

import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FormBindingContractTest {

    @Autowired
    MockMvc mvc;

    private org.springframework.test.web.servlet.request
            .MockHttpServletRequestBuilder form(String path) {

        return post(path)
                .contentType(MediaType.APPLICATION_FORM_URLENCODED);
    }

    @Test
    void localFormBindingSucceeds() throws Exception {
        mvc.perform(form("/api/form-local")
                        .param("name", "Book")
                        .param("quantity", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("Book"))
                .andExpect(jsonPath("$.quantity").value(2));
    }

    @Test
    void localFormWrongTypeIsBindingFailure() throws Exception {
        mvc.perform(form("/api/form-local")
                        .param("name", "Book")
                        .param("quantity", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BINDING_ERROR"))
                .andExpect(jsonPath("$.issues[*].field",
                        hasItem("quantity")))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("typeMismatch")))
                .andExpect(jsonPath("$.issues[*].category",
                        hasItem("binding")));
    }

    @Test
    void localFormConstraintViolationIsDifferent() throws Exception {
        mvc.perform(form("/api/form-local")
                        .param("name", "")
                        .param("quantity", "2"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[0].field")
                        .value("name"))
                .andExpect(jsonPath("$.issues[0].code")
                        .value("NotBlank"))
                .andExpect(jsonPath("$.issues[0].category")
                        .value("constraint"));
    }

    @Test
    void localFormMinConstraintIsNotBindingError() throws Exception {
        mvc.perform(form("/api/form-local")
                        .param("name", "Book")
                        .param("quantity", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[0].code")
                        .value("Min"));
    }

    @Test
    void localFormMissingQuantityIsNotNullViolation() throws Exception {
        mvc.perform(form("/api/form-local")
                        .param("name", "Book"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[0].field")
                        .value("quantity"))
                .andExpect(jsonPath("$.issues[0].code")
                        .value("NotNull"));
    }

    @Test
    void localFormCanContainBindingAndConstraintIssues() throws Exception {
        mvc.perform(form("/api/form-local")
                        .param("name", "")
                        .param("quantity", "not-a-number"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BINDING_ERROR"))
                .andExpect(jsonPath("$.issues[*].field",
                        hasItem("name")))
                .andExpect(jsonPath("$.issues[*].field",
                        hasItem("quantity")))
                .andExpect(jsonPath("$.issues[*].category",
                        hasItem("binding")))
                .andExpect(jsonPath("$.issues[*].category",
                        hasItem("constraint")));
    }

    @Test
    void localFormRejectsSuppressedFieldsEvenIfKnownFieldsValid()
            throws Exception {

        mvc.perform(form("/api/form-local")
                        .param("name", "Book")
                        .param("quantity", "2")
                        .param("role", "admin"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNEXPECTED_FIELD"))
                .andExpect(jsonPath("$.issues", hasSize(0)));
    }

    @Test
    void globalAdviceHandlesUnhandledFormBindingError()
            throws Exception {

        mvc.perform(form("/api/form-unhandled")
                        .param("name", "Book")
                        .param("quantity", "not-a-number"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BINDING_ERROR"))
                .andExpect(jsonPath("$.issues[*].field",
                        hasItem("quantity")))
                .andExpect(result -> assertInstanceOf(
                        MethodArgumentNotValidException.class,
                        result.getResolvedException()));
    }

    @Test
    void globalAdviceHandlesUnhandledFormConstraint() throws Exception {
        mvc.perform(form("/api/form-unhandled")
                        .param("name", "")
                        .param("quantity", "2"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("NotBlank")));
    }

    @Test
    void globalAdviceKeepsBindingAndConstraintDetails()
            throws Exception {

        mvc.perform(form("/api/form-unhandled")
                        .param("name", "")
                        .param("quantity", "not-a-number"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BINDING_ERROR"))
                .andExpect(jsonPath("$.issues[*].category",
                        hasItem("binding")))
                .andExpect(jsonPath("$.issues[*].category",
                        hasItem("constraint")));
    }

    @Test
    void validUnhandledFormStillSucceeds() throws Exception {
        mvc.perform(form("/api/form-unhandled")
                        .param("name", "Book")
                        .param("quantity", "5"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.quantity").value(5));
    }
}
```

**Điểm then chốt của test form:**
- `@ModelAttribute` dùng setter/property binding; String `"abc"` không convert thành `Integer`.
- `BindingResult` ngay sau DTO cho phép handler xử lý lỗi local.
- Nếu không có `BindingResult`, `MethodArgumentNotValidException` có thể chứa **binding failure** lẫn **constraint violation**.
- `hasErrors()` không đủ để nhận biết mọi suppressed field do allowlist; ví dụ kiểm tra `getSuppressedFields()` riêng.
- Một request có thể có lỗi trên **nhiều field và nhiều category**, vì thế response giữ từng issue thay vì chỉ một String.
- Test client contract nên xác nhận các mã ổn định; exception internals chỉ dùng để debug hoặc assert routing của framework.

## 10. MockMvc: hợp đồng phản hồi và bảo mật

### 10.1. `ResponseContractSecurityTest.java`

```java
package demo.contract;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.aMapWithSize;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ResponseContractSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void errorEnvelopeHasOnlyStableTopLevelFields() throws Exception {
        mvc.perform(get("/api/count"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$", aMapWithSize(2)))
                .andExpect(jsonPath("$.code")
                        .value("MISSING_PARAMETER"))
                .andExpect(jsonPath("$.issues", hasSize(1)))
                .andExpect(jsonPath("$.timestamp").doesNotExist())
                .andExpect(jsonPath("$.trace").doesNotExist())
                .andExpect(jsonPath("$.exception").doesNotExist());
    }

    @Test
    void everyErrorIsSerializedAsJson() throws Exception {
        mvc.perform(get("/api/count").param("count", "wrong"))
                .andExpect(status().isBadRequest())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON));
    }

    @Test
    void untrustedInputIsNotEchoedInTypeError() throws Exception {
        String raw = "SENSITIVE_REQUEST_PAYLOAD_938472";

        String body = mvc.perform(get("/api/count")
                        .param("count", raw))
                .andExpect(status().isBadRequest())
                .andReturn().getResponse().getContentAsString();

        assertFalse(body.contains(raw));
        assertFalse(body.contains("MethodArgumentTypeMismatchException"));
    }

    @Test
    void unreadableJsonDoesNotLeakRawParserMessage()
            throws Exception {

        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$", aMapWithSize(2)))
                .andExpect(jsonPath("$.code")
                        .value("BODY_UNREADABLE"))
                .andExpect(jsonPath("$.issues", hasSize(0)));
    }

    @Test
    void serverReturnViolationIsNotMisclassifiedAsClient400()
            throws Exception {

        mvc.perform(get("/api/server-contract"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code")
                        .value("SERVER_CONTRACT_VIOLATION"))
                .andExpect(jsonPath("$.issues", hasSize(0)));
    }
}
```

Test bảo mật không phải chứng nhận toàn bộ hệ thống “an toàn tuyệt đối”. Nó xác nhận vài tính chất hữu ích của **error contract do chúng ta kiểm soát**:
- Không echo request field value `raw` ra JSON.
- Không leak Java exception class names vào body.
- Error envelope luôn có `code` và `issues`.
- Method return constraint violation vẫn là lỗi server.
- Jackson parse error trả schema đơn giản, không đẩy stack trace.

Trong production còn cần kiểm thử authentication/authorization, content negotiation, CORS, headers, rate limiting và logging policies riêng.

## 11. Chạy test và diễn giải kết quả

Với bốn lớp test vừa định nghĩa, có **nhiều phương thức `@Test`** bao phủ success, missing, wrong type, validation, nested field paths, response envelope, bảo mật và 500 server contract. Kết quả “tests pass” chỉ được xác nhận **sau khi chạy Maven trên môi trường của bạn**; đây là bản mã mẫu đã được giải thích, không tuyên bố đã chạy build trong lúc soạn bài.

Trong thư mục `mockmvc-contract-demo`:

```bash
mvn test
```

Chạy từng test class để khoanh vùng:

```bash
mvn -Dtest=QueryAndMethodValidationTest test
mvn -Dtest=JsonValidationContractTest test
mvn -Dtest=FormBindingContractTest test
mvn -Dtest=ResponseContractSecurityTest test
```

Chạy ứng dụng:

```bash
mvn spring-boot:run
```

Các lệnh dùng JDK 17+ và Maven tải được dependencies. Không cố định stdout của Maven/Spring Boot; test report chuẩn trong `target/surefire-reports` sẽ cho biết số case và failures nếu có.

### 11.1. Khi một assertion fail, đọc theo tầng

| Test fail | Nên kiểm tra |
| --- | --- |
| HTTP status sai | Handler mapping, controller return, exception type, advice có được đăng ký |
| `$.code` sai | Đường argument resolution/converter/validator, handler override mapping |
| `issues[*].field` sai | Object name, nested path, method parameter name, `@ModelAttribute` |
| `issues[*].category` sai | `FieldError.isBindingFailure()`, mapping issues |
| `@Min` direct trả exception khác | Spring MVC version, class-level `@Validated`, method validation config |
| Test form chỉ ra thiếu code `typeMismatch` | DataBinder conversion, errorCode mapping, DTO type |
| JSON malformed trả 500 | Custom exception handler/mapper có lỗi, logging, serialization |
| Status đúng nhưng response không có JSON | Advice trả body null; message converter không được nạp |
| Một web slice test pass còn full-context test fail | Bean registration, filters, security, custom config, validation provider |
| Form valid bị reject do field không được allow | `@InitBinder` allowed fields, suppressed fields và property names |

### 11.2. `MockMvc` không được phép ép failure thành “200 OK”

Một anti-pattern:

```java
mvc.perform(post("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .content(invalidJson))
   .andExpect(status().isOk());
```

Nếu input vi phạm contract và server được thiết kế trả 400, chỉnh test thành 200 để pass không giải quyết nguyên nhân. Thay đổi status/error semantics phải là quyết định **API contract** có lý do, không phải sửa test qua loa.

## 12. Thử API bằng curl

### 12.1. Query missing

```bash
curl -i 'http://localhost:8080/api/count'
```

Kỳ vọng HTTP 400 với body tương tự:

```json
{
  "code": "MISSING_PARAMETER",
  "issues": [
    {"field":"count","code":"required","category":"presence"}
  ]
}
```

### 12.2. Query wrong type

```bash
curl -i 'http://localhost:8080/api/count?count=abc'
```

Kỳ vọng HTTP 400:

```json
{
  "code": "TYPE_MISMATCH",
  "issues": [
    {"field":"count","code":"typeMismatch","category":"binding"}
  ]
}
```

### 12.3. Direct `@Min`

```bash
curl -i 'http://localhost:8080/api/page?page=0'
```

Kỳ vọng HTTP 400:

```json
{
  "code": "METHOD_VALIDATION_ERROR",
  "issues": [
    {"field":"page","code":"invalid","category":"constraint"}
  ]
}
```

### 12.4. JSON valid

```bash
curl -i -X POST \
  'http://localhost:8080/api/items' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Book","quantity":2,"delivery":{"city":"Hue"}}'
```

Kỳ vọng HTTP 201 và body:

```json
{"name":"Book","quantity":2,"city":"Hue"}
```

### 12.5. JSON có đúng kiểu nhưng sai constraint

```bash
curl -i -X POST \
  'http://localhost:8080/api/items' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Book","quantity":0,"delivery":{"city":"Hue"}}'
```

Kỳ vọng HTTP 400, error category `VALIDATION_ERROR` và issue `quantity/Min/constraint`.

### 12.6. JSON không decode được

```bash
curl -i -X POST \
  'http://localhost:8080/api/items' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Book","quantity":{"oops":1},"delivery":{"city":"Hue"}}'
```

Kỳ vọng HTTP 400, code `BODY_UNREADABLE`, không có issue `Min` vì value không được decode thành `Integer`.

### 12.7. Form sai kiểu

```bash
curl -i -X POST \
  'http://localhost:8080/api/form-local' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'name=Book' \
  --data-urlencode 'quantity=abc'
```

Kỳ vọng HTTP 400, error category `BINDING_ERROR`, issue `quantity/typeMismatch/binding`.

### 12.8. Form bị chặn field lạ

```bash
curl -i -X POST \
  'http://localhost:8080/api/form-local' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'name=Book' \
  --data-urlencode 'quantity=2' \
  --data-urlencode 'role=admin'
```

Kỳ vọng HTTP 400, code `UNEXPECTED_FIELD`, issues rỗng. Đây là policy riêng của demo: không silently ignore các property paths bị suppressed.

## 13. Tránh flaky tests: các assertion nên và không nên viết

### 13.1. Không dựa vào thứ tự validation provider

Một field có thể vi phạm `@NotBlank` và `@Size`, các constraints có thể được thực thi/danh sách trả về không theo thứ tự cố định.

Không nên:

```java
.andExpect(jsonPath("$.issues[0].code").value("NotBlank"))
.andExpect(jsonPath("$.issues[1].code").value("Size"))
```

nếu API **không** công bố sort order. Trong demo, `ApiError` **chủ động sort** issues theo field và code, nên thứ tự có thể được xem như contract; tuy nhiên khi test một request có nhiều lỗi, dùng Hamcrest `hasItem` để nêu mục đích tốt hơn:

```java
.andExpect(jsonPath("$.issues[*].code",
        hasItem("NotBlank")))
.andExpect(jsonPath("$.issues[*].code",
        hasItem("Size")));
```

Đây là snippet, cần imports `hasItem` và `jsonPath`. Nếu policy sort được công bố, viết thêm test riêng cho sorting, không buộc tất cả tests vào chi tiết serialization.

### 13.2. Không assert text mặc định của provider

Không nên cố định toàn bộ text:

```text
must be greater than or equal to 1
```

vì locale và Hibernate Validator message interpolation có thể thay đổi. Nếu ứng dụng chủ động định nghĩa bản dịch và cam kết câu hiển thị, hãy test **message bundles của ứng dụng**, không dựa trên provider default text.

### 13.3. Tránh so sánh JSON nguyên chuỗi

JSON object key ordering không phải hợp đồng mặc định. Cách sau dễ fragile:

```java
assertEquals(
  "{\"code\":\"MISSING_PARAMETER\",\"issues\":[]}",
  responseText);
```

Dùng `jsonPath` hoặc `content().json(expectedJson)` với chế độ matching phù hợp. Nếu schema có quyền thêm optional fields, xác định rõ nên strict hay lenient; ví dụ `aMapWithSize(2)` trong demo **cố ý** khóa top-level keys để phát hiện schema drift.

### 13.4. Không assert Spring exception raw message

String từ `MethodArgumentTypeMismatchException#getMessage()` có thể chứa tên argument, Java class và thông tin nội bộ. Dùng exception **type** khi cần debug đường đi, machine code **của API** cho hợp đồng và HTTP status cho semantics. Không viết test dựa vào substring tiếng Anh của Spring exception để suy ra field.

### 13.5. Dữ liệu giả nhưng có tính phát hiện lỗi

Dùng input khác nhau để phát hiện bug:
- Missing: không thêm `param` hoặc để body trống.
- Wrong type: `quantity=abc`.
- Vi phạm constraint: `quantity=0`.
- Valid: `quantity=2`.
- Nested invalid: `delivery.city=""`.
- Suppressed: `role=admin`.

Nếu cả “wrong type” và “violation” đều dùng `quantity=0`, test có thể không bao giờ chạy conversion failure branch.

## 14. Kiểm tra chi tiết exception path bằng `getResolvedException()`

Khi debugging, code:

```java
MvcResult result = mvc.perform(
        get("/api/count").param("count", "abc"))
        .andReturn();

Exception ex = result.getResolvedException();
assertInstanceOf(MethodArgumentTypeMismatchException.class, ex);
```

có ích để xác nhận Spring MVC đã nhận request, chuyển kiểu thất bại và có exception được resolver xử lý. Tuy nhiên:
- Nếu controller tự xử lý bằng `BindingResult`, có thể **không có resolved exception** dù response 400.
- Nếu một custom advice bắt lỗi và không đi qua resolver tương tự, exception path có thể khác.
- `getResolvedException()` không thay contract test của body.
- Khi dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)` và gọi qua HTTP thật, không có `MvcResult.getResolvedException()` ở client.

Đừng dùng resolved exception là dấu hiệu duy nhất rằng một HTTP error đã được chuẩn hóa đúng.

## 15. Test controller đã không xử lý request lỗi như request thành công

Trong API thật, kiểm thử status/message vẫn chưa đủ để bảo đảm **không ghi database** khi binding/validation thất bại. Nếu controller có service:

```java
@RestController
public class CreateController {

    private final ItemService service;

    public CreateController(ItemService service) {
        this.service = service;
    }

    @PostMapping("/items")
    public ResponseEntity<?> create(
            @Valid @RequestBody CreateItemRequest request) {

        service.create(request);
        return ResponseEntity.status(201).build();
    }
}
```

Đây là **fragment kiến trúc**, cần định nghĩa `ItemService` và imports; không phải một file khác trong project chạy ở phần 6.

Trong `@WebMvcTest`, có thể dùng `@MockitoBean ItemService service`, gửi JSON invalid rồi:

```java
verifyNoInteractions(service);
```

nhằm chứng minh việc validate chặn request **trước khi** ghi business data. Với `BindingResult` cục bộ, controller vẫn được gọi, nên code phải chủ động return khi có errors; MockMvc test không chỉ assert response mà cần xác minh service không được invoke nếu đó là security/data-integrity requirement.

Khi test authorization hoặc transaction rollback, bổ sung service/repository integration tests; MockMvc response test một mình không chứng minh DB không đổi.

## 16. Test Security filters, CORS và authentication ảnh hưởng thế nào?

Nếu Spring Security nằm trên classpath, `MockMvc` của Boot có thể tự cấu hình security filters. Khi đó unauthenticated request có thể nhận **401/403 trước khi controller binding/validation chạy**. Đây là hành vi chính xác của hệ thống nhưng làm test “mong chờ 400” fail nếu setup không cấp quyền phù hợp.

Các lựa chọn:
- Với test mục tiêu **binding/validation**, tạo authenticated principal hợp lệ (`spring-security-test`, `@WithMockUser` hoặc request postprocessor) để request thực sự tới controller.
- Test 401/403 ở suite security riêng.
- Không tắt hết security chỉ để test pass nếu cấu hình production yêu cầu bảo vệ.
- `@WebMvcTest` có thể scan security filters; kiểm tra slice config có đúng bean cần thiết.

Project demo **không có Spring Security dependency**, vì vậy tests chỉ tập trung vào MVC validation contract.

## 17. Spring MVC `ProblemDetail` và hợp đồng lỗi mở rộng

Spring Framework hỗ trợ RFC 9457 `ProblemDetail`. Một API có thể chọn:

```json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "Some fields are invalid",
  "code": "VALIDATION_ERROR",
  "issues": [
    {"field":"quantity","code":"Min","category":"constraint"}
  ]
}
```

Đây là **schema thiết kế minh họa**, không phải JSON Spring tự tạo trong mọi cấu hình.

Ưu điểm:
- Trường `status`/`title`/`type`/`detail` theo RFC 9457.
- Có thể thêm extension `code`/`issues` cho frontend.
- Có chiến lược localization qua `MessageSource`.
- Có thể giữ consistent error handling giữa controllers.

Khi chuyển từ `ApiError` custom sang `ProblemDetail`, test cần:
1. HTTP status phù hợp `ProblemDetail.status`.
2. `Content-Type: application/problem+json` khi đó là contract.
3. Machine code và issues đúng.
4. Không lộ internal details.
5. Cách xử lý lỗi 500 khác 400 vẫn nhất quán.

Không làm thay đổi schema lớn trong một code review mà không cập nhật OpenAPI/client tests và versioning policy.

## 18. Kiểm tra tính nhất quán của nhiều endpoint

Một hợp đồng lỗi tốt không chỉ đúng ở một controller:

| Endpoint | Request sai | HTTP | `code` |
| --- | --- | --- | --- |
| `GET /api/count` | thiếu count | 400 | `MISSING_PARAMETER` |
| `GET /api/count` | count=abc | 400 | `TYPE_MISMATCH` |
| `GET /api/page` | page=0 | 400 | `METHOD_VALIDATION_ERROR` |
| `POST /api/items` | malformed JSON | 400 | `BODY_UNREADABLE` |
| `POST /api/items` | quantity=0 | 400 | `VALIDATION_ERROR` |
| `POST /api/form-local` | quantity=abc | 400 | `BINDING_ERROR` |
| `POST /api/form-local` | role=admin | 400 | `UNEXPECTED_FIELD` |
| `POST /api/form-unhandled` | name="" | 400 | `VALIDATION_ERROR` |
| `GET /api/server-contract` | return null | 500 | `SERVER_CONTRACT_VIOLATION` |

Các hàng là **kỳ vọng của code demo**. Khi ứng dụng có custom message converters/advice hoặc thay MVC version, MockMvc regression tests sẽ phát hiện khác biệt.

### 18.1. Contract drift khó thấy

Một refactor có thể thay:

```java
public String create(@Valid @RequestBody CreateItemRequest dto)
```

thành:

```java
public String create(
        @RequestParam @Min(1) int amount,
        @Valid @RequestBody CreateItemRequest dto)
```

Việc thêm direct method constraint `@Min` có thể thay exception path sang `HandlerMethodValidationException`. Nếu advice chỉ bắt `MethodArgumentNotValidException`, API có thể đột nhiên trả JSON lỗi khác.

Chính vì vậy suite phải có tests cho **cả validation modes** và giữ error schema consistency khi controller signatures thay đổi.

## 19. Những lỗi test phổ biến

| Sai lầm | Hậu quả | Sửa như thế nào |
| --- | --- | --- |
| Chỉ assert `400` | Không phát hiện sai category, thiếu field hoặc leak dữ liệu | Assert `code`, `issues`, content type |
| Test `@Min` với `"abc"` | Conversion fail trước, không test constraint | Dùng `"0"` cho Min, `"abc"` cho conversion |
| Coi mọi `MethodArgumentNotValidException` là Bean Validation | Bỏ qua type mismatch ở form | Dùng `FieldError.isBindingFailure()` |
| Chỉ test `@Valid` DTO, không test direct method constraint | Bỏ sót `HandlerMethodValidationException` | Test riêng `@RequestParam @Min` |
| Chỉ test direct `@Min`, không test nested DTO | Bỏ sót `@Valid` cascade, property paths | Test `delivery.city` |
| Quên `BindingResult` ngay sau `@ModelAttribute` | Không bắt local errors như kỳ vọng | Đặt đúng vị trí hoặc dùng global advice |
| Có `BindingResult` nhưng không check `getSuppressedFields()` | Extra field có thể bị ignore trong khi API cần reject | Test suppression riêng |
| Dùng `@RequestBody` để test setter allowlist | Jackson deserialize khác DataBinder | Dùng `@ModelAttribute` form/query |
| `@WebMvcTest` thiếu advice/validator | Response khác production | Import/mock/configure required beans |
| `MockMvcBuilders.standaloneSetup` thiếu resolver | Test pass/sai vì hạ tầng không giống production | Dùng web slice hoặc config đầy đủ |
| Dựa vào thứ tự `ConstraintViolation` | Flaky tests | Dùng hasItem hoặc sort contract |
| Assert raw exception text | Fail sau upgrade/provider/locale | Assert machine codes |
| Dùng HTTP 400 cho return-value constraint | Đổ lỗi server cho client | Giữ status 500 |
| Echo `getRejectedValue()` | Lộ PII/secrets | Giới hạn response, test không leak |
| Test chỉ error case, bỏ happy path | Không biết converter/serialization hợp lệ | Test 200/201 cùng dữ liệu chuẩn |
| Chỉ test happy path, bỏ malformed JSON | Không kiểm tra bad input | Phủ cả body missing, malformed, wrong type |
| Bật security rồi mong anonymous 400 | 401/403 có thể chặn trước validation | Setup auth hợp lệ, test security riêng |
| Sửa assertions để suite pass mà không hiểu exception | Che regression | Phân tích từng tầng và quyết định API contract |

## 20. Checklist review trước khi merge

1. Test dùng đúng dependency `spring-boot-starter-test`, provider Jakarta Validation.
2. Test annotation phù hợp Spring Boot major version và Java 17.
3. Request dùng đúng HTTP method, route, Content-Type và parameters.
4. Test thiếu `@RequestParam` không bị nhầm với converter failure.
5. Test `count=abc` được xem là type mismatch, không phải `@Min`.
6. Test `page=0` có direct `@Min` và xác nhận MVC method-validation branch.
7. Test `@Valid @RequestBody` JSON malformed khác constraint errors.
8. Test JSON thiếu field với `@NotNull` và field path chính xác.
9. Test `@Valid` cascade vào nested object và nested error path.
10. Test local `BindingResult` đứng ngay sau model attribute.
11. Test form `quantity=abc` bằng `FieldError.isBindingFailure()`.
12. Test request vừa có binding error vừa có constraint error; response giữ cả hai.
13. Test suppressed extra fields nếu API yêu cầu reject.
14. Test global exception advice override đúng chữ ký Spring version.
15. Test response code/issue schema, status và content type.
16. Test các machine-readable codes không lệ thuộc locale.
17. Test sorting/deduplication nếu được quy định là contract.
18. Test không leak raw rejected values, internal exception names/stack trace.
19. Test return-value constraint giữ 500.
20. Test success cases 200/201, JSON body và field mapping.
21. Test nhiều request endpoints để nhận ra schema drift.
22. Với Spring Security, setup authenticated requests đúng mức.
23. Nếu có service write, xác minh invalid request không gọi service và không làm đổi data.
24. Nếu error schema thay đổi, cập nhật OpenAPI, SDK/client và migration policy.
25. Kiểm thử real server riêng cho những vấn đề network/container mà MockMvc không mô phỏng.

## 21. Bài tập tự luyện

1. Thêm `GET /api/optional` với `@RequestParam(required=false) Integer count`. Test missing, empty, invalid text; giải thích khác biệt.
2. Đổi `CreateItemRequest.quantity` từ `Integer` thành `int`. Gửi JSON thiếu field; quan sát sự khác biệt giữa 0 và null.
3. Viết một test JSON chứa hai constraint failures trên cùng field; assert bằng `hasItem` thay vì index cố định.
4. Chuyển `ApiError` sang `ProblemDetail` và assert `Content-Type: application/problem+json`.
5. Thêm `@Size(min=3)` trên `name` và kiểm thử giới hạn biên bằng `@ParameterizedTest`.
6. Viết test form `quantity=abc&name=` và so sánh `getFieldErrors()` với `isBindingFailure()` cho từng field.
7. Thêm converter `String→CurrencyCode` bằng `WebMvcConfigurer#addFormatters`; test request sai conversion và code `TYPE_MISMATCH`.
8. Thêm một direct `@Min` lên handler nhận `@Valid @RequestBody`, rồi kiểm tra exception routing có thay đổi không.
9. Đặt class-level `@Validated` lên controller trong một test configuration riêng, quan sát AOP method-validation path và tránh áp giả định cũ.
10. Thêm endpoint `@RequestHeader("X-Correlation-Id")` required; tạo mã `MISSING_HEADER` và MockMvc test missing header.
11. Thêm multipart form có missing file part và file 0 byte; giải thích vì sao presence khác content validation.
12. Thêm business error `ITEM_ALREADY_EXISTS` được mapping sang 409; giữ schema `code/issues` thống nhất mà không gọi nó là Jakarta violation.
13. Viết test với `Accept-Language: vi` và `en` nếu có localized display message; khẳng định machine `code` không đổi.
14. Thêm service được inject vào controller và dùng `@MockitoBean` + `verifyNoInteractions` để bảo đảm invalid request không persist.
15. Thay một vài field names trong DTO và xem tests contract có bắt lỗi API backward compatibility.
16. Thêm test status 415 khi gửi `text/plain` vào endpoint chỉ consumes `application/json`; đảm bảo không gán nhầm là `BODY_UNREADABLE`.
17. Thêm test status 405 cho HTTP method sai; không gọi các lỗi routing này là validation.
18. Viết test strict JSON contract có đúng `code` và `issues`, không có `trace`.
19. Thêm test high-volume negative inputs, nhưng giới hạn request size và không dùng raw PII trong test logs.
20. Dùng Testcontainers/database sandbox để kiểm chứng invalid forms không tạo record; giữ test này riêng với MockMvc response contract nếu phù hợp.

**Kết luận:** `MockMvc` giúp xác nhận cả **đường đi qua Spring MVC** lẫn **hợp đồng phản hồi thực tế**. Để kiểm thử mạnh, hãy gửi dữ liệu phân biệt rõ **thiếu**, **không chuyển kiểu được**, **vi phạm constraint**, **binding form**, **method validation** và **lỗi server**; sau đó assert HTTP status, `Content-Type`, `code`, `issues`, field path, tính ổn định và không rò rỉ thông tin. Đây là cách phát hiện regression khi thay controller signature, converter, validator hoặc global exception handler.

## 22. Tài liệu chính thức

- [Spring Framework 6.2 — Validation cho MVC Handler Methods](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — Error Responses, RFC 9457](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework 6.2 — ResponseEntityExceptionHandler API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
- [Spring Framework 6.2 — HandlerMethodValidationException API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html)
- [Spring Framework 6.2 — BindingResult API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework 6.2 — FieldError API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring Framework 6.2 — ModelAttribute Methods](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — RequestBody Methods](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — MockMvc setup](https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework/server-setup-options.html)
- [Spring Framework 6.2 — MockMvc performing requests](https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework/performing-requests.html)
- [Spring Boot 3.5 — Testing Spring Boot applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Jakarta Validation 3.0 — Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)