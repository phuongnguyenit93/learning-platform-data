# @AssertTrue và @AssertFalse

> **Bối cảnh:** Hai ràng buộc boolean chuẩn của Jakarta Bean Validation trong Java và Spring Framework. Bài học tập trung vào ý nghĩa `true`/`false`/`null`, lựa chọn `boolean` hay `Boolean`, kết hợp `@NotNull` khi bắt buộc gửi dữ liệu, kiểm tra điều kiện suy ra từ nhiều trường, và cách Spring MVC kích hoạt validation. Ví dụ chạy độc lập với Java 17+ và Jakarta Validation provider từ Spring Boot 3.3.x.

## 1. Định nghĩa và mục đích

`@AssertTrue` và `@AssertFalse` thuộc `jakarta.validation.constraints`. Chúng dùng để khẳng định rằng **giá trị boolean của một phần tử có trạng thái mong muốn**.

- `@AssertTrue`: giá trị hợp lệ khi là `true`; `false` vi phạm.
- `@AssertFalse`: giá trị hợp lệ khi là `false`; `true` vi phạm.
- **Cả hai đều coi `null` là hợp lệ**, theo Jakarta Bean Validation. Nếu yêu cầu một giá trị phải được cung cấp, cần bổ sung `@NotNull` trên `Boolean`.
- **Kiểu được hỗ trợ theo chuẩn:** primitive `boolean` và wrapper `java.lang.Boolean`. Không áp hai annotation này trực tiếp lên `String`, `Integer`, `List` hay những đối tượng không phải boolean.

Đó là *ràng buộc trên giá trị*, không phải phép so sánh Java tự chạy khi gọi setter/constructor. Có annotation trên field mới là bước khai báo; chỉ khi Bean Validation được kích hoạt (ví dụ `Validator.validate(bean)`, `@Valid` trong Spring MVC), provider mới đánh giá constraint.

### Bảng hành vi nền tảng

| Giá trị thực tế | `@AssertTrue` | `@AssertFalse` | `@NotNull` |
| --- | --- | --- | --- |
| `Boolean.TRUE` | Hợp lệ | Vi phạm | Hợp lệ |
| `Boolean.FALSE` | Vi phạm | Hợp lệ | Hợp lệ |
| `null` (`Boolean`) | **Hợp lệ** | **Hợp lệ** | Vi phạm |
| `true` (primitive `boolean`) | Hợp lệ | Vi phạm | Không có null |
| `false` (primitive `boolean`) | Vi phạm | Hợp lệ | Không có null |

**Không nhầm `@AssertFalse` với “bắt buộc client xác nhận không”.** Nó cho phép `null`, nghĩa là nếu nghiệp vụ cần một câu trả lời rõ ràng `false`, nên dùng `@NotNull @AssertFalse Boolean field`. Tương tự, `@AssertTrue` đơn lẻ chưa bảo đảm người dùng đã gửi `true` nếu trường là `Boolean` và giá trị thiếu thành `null`.

## 2. Chọn `boolean` hay `Boolean`

### 2.1. Primitive `boolean`: chỉ có hai trạng thái

```java
import jakarta.validation.constraints.AssertTrue;

public class Settings {
    @AssertTrue
    private boolean enabled;
}
```

Primitive có hai giá trị `true` hoặc `false`; một field `boolean` chưa gán được khởi tạo mặc định là `false`. Vì vậy:

- `enabled = true` qua `@AssertTrue`.
- `enabled = false` trượt `@AssertTrue`.
- Không biểu diễn được tình trạng “chưa gửi/chưa chọn” bằng null.
- Nếu một lớp được tạo bằng constructor không truyền field hoặc một binder gán giá trị mặc định, việc thiếu giá trị và gửi `false` **có thể trở nên không phân biệt được**. Hành vi HTTP còn phụ thuộc mapper, setter, constructor và cấu hình binding.

`@NotNull` trên primitive `boolean` không hữu ích: primitive vốn không thể null. Đừng dùng `@NotNull` để giải quyết việc phân biệt “thiếu” với `false` khi kiểu dữ liệu đã là primitive.

### 2.2. Wrapper `Boolean`: ba trạng thái, có thể yêu cầu người dùng trả lời rõ ràng

```java
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotNull;

public class TermsInput {
    @NotNull
    @AssertTrue
    private Boolean acceptedTerms;
}
```

Đây là DTO minh họa, chưa có constructor/getter/setter. Với `Boolean`, code có thể phân biệt:

1. `null`: chưa được cung cấp hoặc không xác định → `@NotNull` bắt lỗi.
2. `false`: có trả lời nhưng chưa đồng ý → `@AssertTrue` bắt lỗi.
3. `true`: có trả lời và đồng ý → cả hai qua.

Nếu chỉ dùng `@AssertTrue Boolean acceptedTerms` mà bỏ `@NotNull`, giá trị null **vẫn qua**. Với `@AssertFalse` cũng tương tự:

```java
@NotNull
@AssertFalse
private Boolean disabledByPolicy;
```

Kết hợp này yêu cầu giá trị được cung cấp **và phải là `false`**. Dùng cho cờ nghiệp vụ mà API thật sự muốn bắt buộc trả lời “không”, chứ không chỉ cho một trường có mặc định false trong UI.

### 2.3. Một sai lầm với API JSON

Với một DTO chứa `Boolean agreed` và Spring/Jackson cấu hình thông thường, request sau có các ý nghĩa khác nhau:

```json
{"agreed": true}
```

```json
{"agreed": false}
```

```json
{"agreed": null}
```

```json
{}
```

Trong trường hợp mapper tạo DTO và để `agreed = null` khi property thiếu, ba trường hợp sau (false/null/thiếu) không đồng nghĩa:

- `false`: `@AssertTrue` báo vi phạm; `@NotNull` qua.
- `null`: `@AssertTrue` qua; `@NotNull` báo vi phạm.
- Thiếu property: nếu mapper để null, tương tự null; nhưng constructor/record hoặc cấu hình Jackson nghiêm ngặt có thể xử lý thiếu field trước validation.

**Đừng giả định mọi trường thiếu luôn thành null hoặc mọi giá trị sai kiểu luôn đi đến Bean Validation.** Một số lỗi JSON có thể được Jackson từ chối khi deserialize, trước khi Bean Validation chạy. Với contract API, nên gửi JSON boolean literal `true`/`false`, không dựa vào việc mapper có cho phép coercion từ chuỗi `"true"` hay số `1`.

## 3. Ví dụ Java 17+ chạy được: cả hai constraint và xử lý null

Ví dụ dưới đây dùng một `ValidatorFactory`, kiểm tra giá trị `Boolean`, so sánh trường hợp yêu cầu bắt buộc, rồi xác minh một thuộc tính tính toán từ hai trường số. Để đầu ra ổn định, chương trình chỉ in đường dẫn field và tên annotation sau khi sắp xếp, không dùng message theo locale.

Cấu trúc:

```text
boolean-constraints/
├── pom.xml
└── src/main/java/demo/BooleanConstraintsDemo.java
```

**`pom.xml`**: dùng starter validation của Spring Boot để cung cấp Jakarta Validation API và Hibernate Validator. Chương trình chạy như Java `main`, **không khởi động ứng dụng Spring**.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>boolean-constraints</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/demo/BooleanConstraintsDemo.java`**:

```java
package demo;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.AssertFalse;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotNull;

import java.util.List;

public class BooleanConstraintsDemo {

    static final class Flags {
        @AssertTrue
        private final Boolean active;

        @AssertFalse
        private final Boolean archived;

        Flags(Boolean active, Boolean archived) {
            this.active = active;
            this.archived = archived;
        }
    }

    static final class RequiredConsent {
        @NotNull
        @AssertTrue
        private final Boolean accepted;

        RequiredConsent(Boolean accepted) {
            this.accepted = accepted;
        }
    }

    static final class Range {
        private final int from;
        private final int to;

        Range(int from, int to) {
            this.from = from;
            this.to = to;
        }

        // Getter boolean có thể biểu diễn điều kiện giữa hai field.
        @AssertTrue
        public boolean isOrdered() {
            return from <= to;
        }
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            inspect(validator, "flags.null",
                    new Flags(null, null));
            inspect(validator, "flags.wrong",
                    new Flags(false, true));
            inspect(validator, "flags.correct",
                    new Flags(true, false));

            inspect(validator, "consent.null",
                    new RequiredConsent(null));
            inspect(validator, "consent.false",
                    new RequiredConsent(false));
            inspect(validator, "consent.true",
                    new RequiredConsent(true));

            inspect(validator, "range.invalid",
                    new Range(10, 5));
            inspect(validator, "range.valid",
                    new Range(5, 10));
        }
    }

    private static void inspect(
            Validator validator, String name, Object input) {
        List<String> violations = validator
                .validate(input)
                .stream()
                .map(v -> v.getPropertyPath()
                        + ":"
                        + v.getConstraintDescriptor()
                                .getAnnotation()
                                .annotationType()
                                .getSimpleName())
                .sorted()
                .toList();

        System.out.println(name + " -> " + violations);
    }
}
```

Chạy từ thư mục chứa `pom.xml` với Java 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.BooleanConstraintsDemo
```

**Các dòng do chương trình in ra** (bỏ qua log phụ của Maven hoặc provider nếu có):

```text
flags.null -> []
flags.wrong -> [active:AssertTrue, archived:AssertFalse]
flags.correct -> []
consent.null -> [accepted:NotNull]
consent.false -> [accepted:AssertTrue]
consent.true -> []
range.invalid -> [ordered:AssertTrue]
range.valid -> []
```

Phân tích:

- `Flags(null, null)` hợp lệ vì hai annotation đều cho phép null.
- `Flags(false, true)` có hai vi phạm: `active` phải true và `archived` phải false.
- `Flags(true, false)` đáp ứng cả hai constraint.
- `RequiredConsent(null)` vi phạm **`@NotNull`**, nhưng không vi phạm `@AssertTrue`.
- `RequiredConsent(false)` vi phạm **`@AssertTrue`**, nhưng không vi phạm `@NotNull`.
- `RequiredConsent(true)` hợp lệ.
- `Range(10, 5)` có getter `isOrdered()` trả false nên vi phạm `@AssertTrue` trên thuộc tính `ordered`.
- `Range(5, 10)` trả true nên hợp lệ.

Ở `Range`, `isOrdered()` là **JavaBeans-style getter** không có tham số, trả về primitive boolean. Bean Validation gọi getter để kiểm tra property constraint. Ví dụ dùng cách này để diễn giải một quy tắc đơn giản liên quan hai trường; nó không biến `@AssertTrue` thành annotation đặt trực tiếp lên class.

`ValidatorFactory` được tạo một lần và đóng bằng `try-with-resources`. `Validator` có thể tái sử dụng qua nhiều lần `validate(...)`, không có phương thức `close()` riêng. Các violations được sắp xếp nên không phụ thuộc thứ tự duyệt `Set`.

## 4. Đặt annotation trên field, getter và biểu thức suy ra

### 4.1. Field validation: kiểm tra dữ liệu có sẵn

```java
import jakarta.validation.constraints.AssertFalse;
import jakarta.validation.constraints.AssertTrue;

public class UserPreferences {
    @AssertTrue
    private Boolean visible;

    @AssertFalse
    private Boolean blocked;
}
```

Đây là đoạn DTO minh họa chưa có constructor/getter/setter. Provider kiểm tra giá trị field tương ứng. Có thể annotate field `private`; Jakarta Validation provider hợp lệ vẫn đọc constraint metadata của field trong quá trình validation.

### 4.2. Getter validation: kiểm tra một thuộc tính tính toán

Một điều kiện liên quan nhiều field đôi khi biểu diễn gọn thành getter boolean:

```java
import jakarta.validation.constraints.AssertTrue;
import java.time.LocalDate;

public class TravelDates {
    private LocalDate departure;
    private LocalDate returnDate;

    @AssertTrue(message = "returnDate must not precede departure")
    public boolean isChronological() {
        return departure == null
                || returnDate == null
                || !returnDate.isBefore(departure);
    }
}
```

Đây là đoạn minh họa thuộc tính tính toán `chronological`. Getter trả true khi một trong hai ngày chưa có hoặc ngày về không trước ngày đi; muốn bắt buộc có hai ngày, đặt **`@NotNull` riêng trên từng field**. Không nên nhồi kiểm tra null và tính hợp lệ liên trường vào cùng một biểu thức khó hiểu khi muốn báo lỗi cụ thể.

Khi `isChronological()` trả false, vi phạm có `propertyPath` thông thường là `chronological`. Nếu API cần gắn lỗi trực tiếp vào `returnDate`, cân nhắc viết **custom class-level constraint** với `ConstraintValidatorContext` để tạo path có ý nghĩa hơn.

**Chú ý một tác dụng phụ:** Getter công khai `isChronological()` có thể được Jackson nhận là JSON property khi serialize một JavaBean. Trong REST DTO, nếu chỉ dùng getter cho validation mà không muốn trả trường đó ra JSON, có thể dùng `@JsonIgnore` phù hợp hoặc tách DTO/validation logic. Hãy kiểm tra cấu hình Jackson thực tế; `@AssertTrue` không phải annotation điều khiển JSON.

### 4.3. Đừng annotate cả field lẫn getter cho cùng một quy tắc mà không có chủ đích

```java
@AssertTrue
private Boolean accepted;

@AssertTrue
public Boolean getAccepted() {
    return accepted;
}
```

Nếu cả hai constraint được phát hiện, cùng một dữ liệu có thể bị **kiểm tra hai lần**, tạo nhiều violation không mong muốn. Nên chọn field access hoặc property access nhất quán cho một thuộc tính. Với property validation, đặt annotation trên **getter**, không đặt trên setter và tưởng rằng Bean Validation sẽ tự chạy mỗi lần setter được gọi.

Một phương thức bất kỳ như `boolean checkBusinessRule()` không mặc nhiên là JavaBeans getter. Muốn dùng Bean Validation property constraint, định nghĩa getter `isXxx()`/`getXxx()` phù hợp; nếu kiểm tra toàn object phức tạp, cân nhắc class-level constraint.

## 5. Khi dùng với Spring MVC và Spring Boot

### 5.1. Bean Validation phải được kích hoạt

Trong Spring Boot 3.x, dùng `spring-boot-starter-validation` để có API Jakarta Validation và provider. Với Spring MVC, khai báo `@Valid` hoặc `@Validated` ở điểm bind thích hợp. Luồng phổ biến của request JSON:

```text
HTTP JSON body (true / false / null / thiếu field)
        │
        ▼
Jackson deserialize
        │
        ▼
DTO với boolean hoặc Boolean
        │
        ▼
@Valid @RequestBody → Jakarta Validation
        │
        ├── hợp lệ: controller xử lý
        │
        └── vi phạm: lỗi validation / BindingResult / exception
```

Ví dụ **các đoạn code để thêm vào dự án Spring Boot Web MVC**, không phải file Java độc lập:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotNull;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

public record AcceptTermsRequest(
        @NotNull @AssertTrue Boolean acceptedTerms) {
}

@RestController
public class TermsController {
    @PostMapping("/terms/accept")
    public ResponseEntity<Void> accept(
            @Valid @RequestBody AcceptTermsRequest request) {
        // Chỉ chạy sau validation thông thường thành công.
        return ResponseEntity.noContent().build();
    }
}
```

Trong ứng dụng có Jakarta Validation được cấu hình:

| Body request | Kết quả theo constraint của record |
| --- | --- |
| `{"acceptedTerms": true}` | Hợp lệ |
| `{"acceptedTerms": false}` | `@AssertTrue` vi phạm |
| `{"acceptedTerms": null}` | `@NotNull` vi phạm |
| `{}` | Nếu Jackson tạo record với giá trị null cho thành phần thiếu, `@NotNull` vi phạm; cấu hình strict constructor binding có thể từ chối body sớm hơn |
| Body JSON sai cú pháp | Có thể bị JSON message converter từ chối **trước** Bean Validation |

Trong cấu hình Spring MVC thông thường, lỗi `@Valid @RequestBody` được framework xử lý thành HTTP 400 nếu không có `BindingResult` phù hợp. Dạng JSON mô tả lỗi phụ thuộc `@ControllerAdvice`/error handling của ứng dụng. Không được giả định chỉ có một exception hoặc response schema cho mọi trường hợp binding và constraint violation.

Nếu chuyển sang `@ModelAttribute`/HTML form, checkbox HTML **không được chọn thường không gửi tham số**. Spring data binding có xử lý đặc biệt đối với checkbox/field marker trong một số cấu hình, nên kết quả cuối cùng (`false` hay `null`) phải được kiểm thử đúng cách bind của form. Không thể lấy hành vi HTML form rồi áp nguyên cho `@RequestBody` JSON.

### 5.2. Validation không đồng nghĩa xác thực nghiệp vụ và bảo mật

`@AssertTrue Boolean acceptedTerms` chỉ khẳng định giá trị DTO tại thời điểm kiểm tra là true (nếu không null). Nó **không chứng minh** người dùng thực sự đọc điều khoản, không ghi lại consent audit, không xác định phiên bản điều khoản và không bảo đảm lời xác nhận xuất phát từ một người dùng đã được xác thực.

Một quy trình chấp thuận điều khoản thực tế có thể cần:

- `@NotNull @AssertTrue` để kiểm tra dữ liệu request.
- Xác định user đã đăng nhập từ context bảo mật.
- Ghi thời điểm, phiên bản điều khoản, hành động consent và thông tin kiểm toán theo chính sách hệ thống.
- Tránh chỉ tin một cờ `acceptedTerms=true` do client tự khai báo để thay thế bằng chứng nghiệp vụ.

Tương tự, `@AssertFalse` trên cờ `banned` trong request **không** chứng minh tài khoản không bị cấm; đó phải là trạng thái do phía server kiểm soát. Không dùng giá trị client cung cấp làm quyết định authorization.

## 6. Những gì các annotation không làm

### Không thay thế `@NotNull`

Theo đặc tả, null thỏa `@AssertTrue` và `@AssertFalse`. Nếu câu hỏi nghiệp vụ là “đã trả lời rõ ràng chưa?”, bắt buộc dùng `Boolean` và `@NotNull` (hoặc cơ chế tương đương) để phân biệt trạng thái chưa trả lời.

### Không thay thế các constraint chuỗi

Muốn `"YES"`, `"NO"` hoặc chuỗi `"true"` không rỗng thì đó là dữ liệu kiểu chuỗi; có thể dùng `@NotBlank`, `@Pattern`, enum, converter hoặc custom validator theo hợp đồng dữ liệu. Đừng annotate `String` bằng `@AssertTrue`; kiểu này không được hỗ trợ theo chuẩn và có thể gây `UnexpectedTypeException` khi validate.

### Không có tác dụng chuẩn hóa đầu vào

Hai annotation không tự biến `"true"` thành `true`, không bỏ khoảng trắng, không sửa case và không ép client gửi đúng literal JSON. Mọi bước parse/coercion xảy ra trước validation theo converter/Jackson được cấu hình.

### Không tự động chạy trên mọi đối tượng

Gọi `new TermsInput()` không chạy Bean Validation. Cần gọi `jakarta.validation.Validator#validate()` hoặc tích hợp có trigger (`@Valid` ở boundary, method validation, v.v.). Annotation `@Valid` dùng để kích hoạt tại những vị trí framework hỗ trợ hoặc biểu thị cascade; nó không khiến constructor Java thuần tự có hiệu ứng kiểm tra.

### Không giới hạn kết quả theo thứ tự cố định

`Validator#validate()` trả `Set<ConstraintViolation<T>>`; thứ tự violations không nên được sử dụng làm contract ổn định. Thông báo vi phạm có thể được dịch theo locale. Khi viết test, ưu tiên so sánh `propertyPath` và loại constraint, hoặc sort trước khi in.

## 7. Lỗi thường gặp và hướng xử lý

| Lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Chỉ dùng `@AssertTrue Boolean agreed` để bắt buộc user đồng ý | `null` vẫn hợp lệ | Dùng `@NotNull @AssertTrue Boolean agreed` |
| Chỉ dùng `@AssertFalse Boolean rejected` để bắt buộc user trả lời “không” | `null` vẫn hợp lệ | Dùng `@NotNull @AssertFalse Boolean rejected` |
| Dùng primitive `boolean` để phân biệt thiếu với `false` | Primitive không biểu diễn được null | Dùng `Boolean` và quy định cách xử lý thiếu field |
| Đặt `@NotNull` trên primitive `boolean` | Không cung cấp bảo đảm bổ sung về tính hiện diện | Sử dụng wrapper khi cần phân biệt null |
| Dùng `@AssertTrue` cho `String` hoặc `int` | Không có validator chuẩn phù hợp, có thể `UnexpectedTypeException` | Chuyển kiểu có chủ đích hoặc dùng constraint đúng kiểu |
| Nghĩ `@AssertFalse` nghĩa là “không truyền field” | `false` và `null` đều hợp lệ nhưng khác ý nghĩa | Viết rõ API contract và thêm `@NotNull` nếu bắt buộc trả lời |
| Đặt annotation vào setter hoặc một hàm bất kỳ và mong property validation chạy | Ràng buộc có thể không được thực thi như mong muốn | Annotate field/getter hợp lệ; dùng method validation nếu mục tiêu là tham số/return của method |
| Đặt cùng constraint trên field và getter | Có thể tạo lỗi trùng lặp | Chọn một kiểu truy cập nhất quán |
| Tưởng getter kiểm tra nhiều field sẽ tự tạo lỗi đúng từng field | `propertyPath` thường là tên getter suy ra | Dùng class-level custom constraint nếu cần path chi tiết |
| Dùng một getter `isValid()` chỉ để validate nhưng không xem JSON response | Jackson có thể serialize getter thành property ngoài ý muốn | Thiết kế DTO rõ ràng hoặc dùng `@JsonIgnore` phù hợp |
| Không thêm dependency validation implementation | Annotation có thể hiện diện nhưng validation không được thực thi | Thêm provider, như `spring-boot-starter-validation` trong Boot 3 |
| Dùng import `javax.validation.*` trong Spring Boot 3 | Khác hệ namespace Jakarta | Dùng `jakarta.validation.*` và provider tương thích |
| Dùng `@AssertTrue` thay kiểm tra phân quyền trên server | Client có thể gửi `true` tùy ý | Kiểm tra lại trạng thái, identity và rule nghiệp vụ phía server |
| So sánh nguyên văn message trong test | Dễ bị ảnh hưởng locale/provider | Assert constraint type/path hoặc các mã lỗi chuẩn hóa |

### Ranh giới với ràng buộc tích hợp trong cơ sở dữ liệu

`@AssertTrue` và `@AssertFalse` là quy tắc Bean Validation ở **điểm mà validation được kích hoạt**. Chúng không đảm bảo tự sinh constraint database trong mọi ORM/DDL configuration; không nên dựa vào chúng để bảo vệ một cột booleans trước các đường ghi khác không chạy validation. Nếu dữ liệu phải có invariant ở database, cần quy tắc phù hợp với schema và nghiệp vụ (ví dụ `NOT NULL` hay CHECK constraint khi DB hỗ trợ).

## 8. Bài tập tự kiểm tra

Trước khi xem đáp án, dự đoán `validate(bean)` có trả lỗi hay không.

**Tình huống A:** `@AssertTrue Boolean verified`, giá trị null. **Đáp án:** không có vi phạm từ `@AssertTrue` vì null hợp lệ.

**Tình huống B:** `@NotNull @AssertTrue Boolean verified`, giá trị null. **Đáp án:** `@NotNull` vi phạm; `@AssertTrue` vẫn coi null hợp lệ.

**Tình huống C:** `@AssertFalse Boolean archived`, giá trị true. **Đáp án:** vi phạm `@AssertFalse`.

**Tình huống D:** `@AssertFalse boolean archived`, field chưa được gán trong một object mới. **Đáp án:** giá trị mặc định của primitive field là false, nên riêng `@AssertFalse` không báo lỗi.

**Tình huống E:** `@AssertTrue boolean isEligible()` là một getter property trả false. **Đáp án:** có vi phạm khi Bean Validation kiểm tra bean và nhận diện getter property. `propertyPath` thường là `eligible`.

**Tình huống F:** `@AssertTrue String confirmation` chứa chuỗi `"true"`. **Đáp án:** kiểu `String` không được hỗ trợ theo Jakarta Validation chuẩn; lỗi cấu hình constraint/`UnexpectedTypeException` có thể xuất hiện trong quá trình validation, không phải một kiểm tra boolean thành công.

## 9. Checklist áp dụng

- [ ] Đã xác định rõ **mong đợi true hay false** trong nghiệp vụ?
- [ ] Đã chọn đúng `boolean` hoặc `Boolean` tùy việc có cần phân biệt “chưa trả lời”?
- [ ] Nếu field `Boolean` bắt buộc, đã ghép `@NotNull` bên cạnh `@AssertTrue`/`@AssertFalse`?
- [ ] Đã kiểm thử đủ ba trường hợp `true`, `false` và `null`?
- [ ] Với request HTTP, đã kiểm thử riêng property thiếu, null, false và sai kiểu JSON?
- [ ] Nếu dùng method/getter, đã tuân thủ quy tắc JavaBeans và tránh annotate trùng field + getter?
- [ ] Nếu getter suy ra từ nhiều trường, đã xác định cách báo lỗi và kiểm thử các trường hợp null?
- [ ] Đã có Bean Validation provider và trigger thực thi (`@Valid`/`@Validated`/`Validator.validate`)?
- [ ] Có tránh dùng cờ do client tự gửi làm bằng chứng authorization/consent ở phía server?
- [ ] Test có kiểm tra property path/constraint type, tránh phụ thuộc thông điệp và thứ tự của `Set`?

**Ghi nhớ:** `@AssertTrue` yêu cầu giá trị **true**; `@AssertFalse` yêu cầu **false**; cả hai đều chấp nhận **null** trên `Boolean`. Khi cần một câu trả lời bắt buộc, ghép `@NotNull`; khi ràng buộc phụ thuộc nhiều field, có thể biểu diễn bằng getter boolean nhưng phải cân nhắc đường dẫn lỗi, trách nhiệm validation và ảnh hưởng tới JSON.

### Tài liệu tham khảo

- [Jakarta Bean Validation 3.0 — `@AssertTrue` Javadoc](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/AssertTrue.html)
- [Jakarta Bean Validation 3.0 — `@AssertFalse` Javadoc](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/AssertFalse.html)
- [Jakarta Bean Validation Specification 3.0, `8.3–8.4](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Hibernate Validator 8 Reference Guide — Constraint declarations](https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/)
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring MVC — Method Argument Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
