# Phân biệt @NotNull, @NotEmpty và @NotBlank

> **Phạm vi:** Ba ràng buộc chuẩn của Jakarta Bean Validation trong ứng dụng Java/Spring Framework. Bài học tập trung vào ý nghĩa của `null`, chuỗi rỗng, chuỗi toàn khoảng trắng, collection/map/array; cách chọn annotation đúng kiểu dữ liệu; và cách kết hợp validation trong Spring MVC. Ví dụ thực thi dùng Java 17, Jakarta Validation qua Hibernate Validator (Spring Boot 3.3.x).

## 1. Mục đích của ba ràng buộc

Cả ba annotation đều thuộc package `jakarta.validation.constraints` trong Jakarta Bean Validation (ở các dự án cũ dùng `javax.validation.constraints`). Chúng biểu đạt **ba mức yêu cầu khác nhau** đối với một giá trị:

- **`@NotNull`:** đối tượng tham chiếu phải **khác `null`**. Không kiểm tra nội dung, số phần tử hay khoảng trắng.
- **`@NotEmpty`:** giá trị phải **khác `null` và có độ dài/kích thước lớn hơn 0**. Hỗ trợ `CharSequence`, `Collection`, `Map` và array; không coi chuỗi chỉ có khoảng trắng là rỗng.
- **`@NotBlank`:** giá trị kiểu **`CharSequence` khác `null` và chứa ít nhất một ký tự không phải khoảng trắng**. Dùng cho văn bản yêu cầu có nội dung có nghĩa, chẳng hạn tên hiển thị hoặc ghi chú bắt buộc.

Tất cả là **constraint kiểm tra giá trị**. Chúng không tự cắt khoảng trắng, không đổi `null` thành chuỗi rỗng, không tự tạo phần tử cho collection và không thay đổi object đã nhận. Kết quả chỉ xuất hiện khi ứng dụng/framework **thực sự kích hoạt validation**.

| Annotation | Điều kiện hợp lệ | Các kiểu dữ liệu hỗ trợ theo chuẩn | `null` có hợp lệ? | Chuỗi `""` có hợp lệ? | Chuỗi `"   "` có hợp lệ? |
| --- | --- | --- | --- | --- | --- |
| `@NotNull` | Giá trị khác `null` | Mọi kiểu tham chiếu; về mặt cú pháp có thể áp lên primitive nhưng không hữu ích để kiểm tra null | Không | Có | Có |
| `@NotEmpty` | Không null và length/size ≥ 1 | `CharSequence`, `Collection`, `Map`, array | Không | Không | **Có** |
| `@NotBlank` | Không null và có ≥ 1 ký tự không phải whitespace | `CharSequence`, ví dụ `String`, `StringBuilder` | Không | Không | **Không** |

Trong bảng, `"   "` gồm ba dấu cách thông thường U+0020. Với những ký tự Unicode đặc biệt trông như khoảng trắng, kết quả có thể phụ thuộc định nghĩa whitespace của provider/JDK; phải kiểm thử đúng bộ ký tự mà hệ thống chấp nhận. Không suy rằng mọi ký tự nhìn trống đều được nhận diện giống U+0020.

### 1.1. `@NotNull`: chỉ kiểm tra sự hiện diện của một tham chiếu

```java
import jakarta.validation.constraints.NotNull;

public class OrderInput {
    @NotNull
    private Long customerId;

    @NotNull
    private String comment;
}
```

Đoạn code trên là **minh họa DTO**, chưa có constructor/getter/setter và không tự thực thi. `customerId = null` vi phạm; `customerId = 0L` vẫn thỏa `@NotNull` vì muốn kiểm tra số dương cần thêm `@Positive` hoặc `@Min(1)`. Với `comment`, cả `""` lẫn `"   "` đều **thỏa** `@NotNull`.

Không dùng primitive `int` nếu muốn phân biệt “không truyền số” với “số 0”: primitive luôn có giá trị mặc định khi là field, và một ràng buộc `@NotNull` không thể phát hiện việc thiếu dữ liệu sau khi đã chuyển thành `int`. Hãy dùng `Integer`/`Long` và kết hợp constraint về miền giá trị.

### 1.2. `@NotEmpty`: kiểm tra kích thước, không kiểm tra ý nghĩa nội dung

```java
import jakarta.validation.constraints.NotEmpty;
import java.util.List;
import java.util.Map;

public class BasketInput {
    @NotEmpty
    private String promotionCode;

    @NotEmpty
    private List<String> productIds;

    @NotEmpty
    private Map<String, String> attributes;

    @NotEmpty
    private byte[] attachment;
}
```

Với `@NotEmpty`:

- `String`: dựa trên `CharSequence.length()`. `""` không hợp lệ, `" "` hợp lệ vì length bằng 1.
- `List`, `Set` và các `Collection` khác: dựa trên `size()`. `List.of()` không hợp lệ, `List.of("")` hợp lệ về **kích thước**.
- `Map`: dựa trên số entry. Map có một key/value rỗng vẫn có `size() = 1`.
- **Array**: dựa trên `length`. `new String[0]` không hợp lệ; `new String[]{null}` có một phần tử nên thỏa **constraint đặt trên mảng**, dù phần tử bên trong là null.

**`@NotEmpty` không kiểm tra từng phần tử.** Muốn danh sách có ít nhất một phần tử và từng phần tử đều là text có nội dung, cần thêm constraint ở *type argument* (xem phần 5). Không dùng `@NotEmpty` trên `Long`, `BigDecimal` hoặc một bean không có khái niệm length/size: các kiểu đó không được hỗ trợ và provider có thể báo `UnexpectedTypeException` khi validation được thực thi.

### 1.3. `@NotBlank`: kiểm tra văn bản có nội dung, không tự chuẩn hóa chuỗi

```java
import jakarta.validation.constraints.NotBlank;

public class ProfileInput {
    @NotBlank
    private String displayName;
}
```

`@NotBlank` từ chối cả `null`, `""` và chuỗi chỉ gồm whitespace. Nó chấp nhận `" A "` vì có ký tự `A` không phải khoảng trắng, **nhưng không tự biến** `" A "` thành `"A"`. Muốn lưu tên đã bỏ khoảng trắng đầu/cuối, ứng dụng phải xử lý chuẩn hóa riêng và thống nhất thời điểm trước hoặc sau validation.

`@NotBlank` **không phải** ràng buộc dành cho `List`/`Map`/array hoặc số. Nếu gắn lên danh sách, việc không có validator phù hợp có thể dẫn đến lỗi cấu hình runtime thay vì một `ConstraintViolation` thông thường.

## 2. Ma trận hành vi dễ nhầm nhất

### 2.1. So sánh trực tiếp trên cùng kiểu `String`

| Giá trị `String` | `@NotNull` | `@NotEmpty` | `@NotBlank` | Vì sao? |
| --- | --- | --- | --- | --- |
| `null` | ❌ | ❌ | ❌ | Cả ba yêu cầu không null |
| `""` (dài 0) | ✅ | ❌ | ❌ | Đã có object nhưng không có ký tự |
| `"   "` (3 dấu cách) | ✅ | ✅ | ❌ | Chuỗi có độ dài 3 nhưng không có ký tự nội dung |
| `"\t\n"` (tab và xuống dòng) | ✅ | ✅ | ❌ | Có ký tự nhưng đều là whitespace thông thường |
| `"a"` | ✅ | ✅ | ✅ | Có một ký tự nội dung |
| `" a "` | ✅ | ✅ | ✅ | Có chữ `a`, dù bao quanh bằng khoảng trắng |
| `"0"` | ✅ | ✅ | ✅ | Chữ số `0` là nội dung hợp lệ; không kiểm tra tính số học |

**Mức nghiêm ngặt trên chuỗi thông thường** có thể hiểu là: `@NotBlank` → `@NotEmpty` → `@NotNull` (từ yêu cầu mạnh hơn đến yếu hơn). Tuy nhiên, không được coi ba annotation là thay thế được cho nhau vì **miền kiểu hỗ trợ khác nhau**.

### 2.2. Với collection, map và array

| Giá trị | `@NotNull` | `@NotEmpty` | `@NotBlank` |
| --- | --- | --- | --- |
| `List<String> = null` | ❌ | ❌ | Không hỗ trợ trên List |
| `List.of()` | ✅ | ❌ | Không hỗ trợ |
| `List.of("")` | ✅ | ✅ | Không hỗ trợ |
| `Map.of()` | ✅ | ❌ | Không hỗ trợ |
| `Map.of("k", "")` | ✅ | ✅ | Không hỗ trợ |
| `new int[0]` | ✅ | ❌ | Không hỗ trợ |
| `new int[]{0}` | ✅ | ✅ | Không hỗ trợ |

`@NotEmpty` đảm bảo **có phần tử/entry**, không đảm bảo phần tử khác null, string không trắng, số dương hay bean con hợp lệ. Đó là công việc của constraint đặt trên phần tử hoặc validation lồng nhau.

## 3. Ví dụ Java 17 chạy được và output chính xác

Ví dụ sau cố ý đặt ba constraint trên **ba field cùng chứa một giá trị `String`** để quan sát sự khác nhau mà không phụ thuộc vào text thông báo lỗi theo locale. Sau đó kiểm tra một danh sách bằng cả `@NotEmpty` và constraint trên phần tử.

Cấu trúc dự án:

```text
constraint-comparison/
├── pom.xml
└── src/main/java/demo/StandardConstraintsDemo.java
```

**`pom.xml`** — dùng `spring-boot-starter-validation` để cung cấp Jakarta Validation API và Hibernate Validator; chương trình chỉ sử dụng Jakarta Validation, không khởi động Spring:

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
    <artifactId>constraint-comparison</artifactId>
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

**`src/main/java/demo/StandardConstraintsDemo.java`**:

```java
package demo;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import java.util.List;

public class StandardConstraintsDemo {

    static final class TextFields {
        @NotNull
        private final String presence;

        @NotEmpty
        private final String nonEmpty;

        @NotBlank
        private final String meaningful;

        TextFields(String value) {
            this.presence = value;
            this.nonEmpty = value;
            this.meaningful = value;
        }
    }

    static final class NameList {
        @NotEmpty
        private final List<@NotBlank String> names;

        NameList(List<String> names) {
            this.names = names;
        }
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            checkText(validator, "null", null);
            checkText(validator, "empty", "");
            checkText(validator, "spaces", "   ");
            checkText(validator, "value", "Hoa");

            checkList(validator, "null", null);
            checkList(validator, "empty", List.of());
            checkList(validator, "blankElement", List.of(" "));
            checkList(validator, "valid", List.of("Hoa"));
        }
    }

    private static void checkText(
            Validator validator, String label, String value) {
        List<String> invalidFields = validator
                .validate(new TextFields(value))
                .stream()
                .map(v -> v.getPropertyPath().toString())
                .sorted()
                .toList();

        System.out.println("text." + label + " -> " + invalidFields);
    }

    private static void checkList(
            Validator validator, String label, List<String> names) {
        int count = validator.validate(new NameList(names)).size();
        System.out.println("list." + label + " -> count=" + count);
    }
}
```

Chạy bằng JDK 17+ và Maven tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.StandardConstraintsDemo
```

**Các dòng do chương trình in ra** (không tính log phụ nếu môi trường Maven/provider phát sinh):

```text
text.null -> [meaningful, nonEmpty, presence]
text.empty -> [meaningful, nonEmpty]
text.spaces -> [meaningful]
text.value -> []
list.null -> count=1
list.empty -> count=1
list.blankElement -> count=1
list.valid -> count=0
```

Giải thích kết quả:

1. Với `null`, cả ba field vi phạm vì cả ba constraint từ chối null.
2. Với `""`, `presence` hợp lệ theo `@NotNull`; `nonEmpty` và `meaningful` vi phạm.
3. Với `"   "`, `@NotEmpty` coi chuỗi có length 3 nên hợp lệ; `@NotBlank` vẫn từ chối.
4. Với `"Hoa"`, cả ba hợp lệ.
5. Với `List.of()`, constraint `@NotEmpty` ở collection vi phạm.
6. Với `List.of(" ")`, collection không rỗng nhưng **phần tử** vi phạm `@NotBlank`.
7. Với `List.of("Hoa")`, collection và phần tử đều hợp lệ.

Ví dụ sắp xếp tên field để tránh phụ thuộc vào thứ tự của `Set<ConstraintViolation<?>>`; cũng không in `getMessage()` vì nội dung thông báo có thể bị quốc tế hóa. Số lượng vi phạm trong ví dụ được kiểm soát vì từng tình huống chỉ có những ràng buộc đã khai báo, không dựa trên thứ tự xử lý của provider.

## 4. Chọn annotation theo loại dữ liệu và yêu cầu nghiệp vụ

Đừng chọn theo tên annotation nghe “nghiêm ngặt hơn”; hãy trả lời **kiểu dữ liệu là gì, điều kiện bất hợp lệ là gì?**

| Nhu cầu | Khai báo gợi ý | Vì sao |
| --- | --- | --- |
| ID dạng `Long` bắt buộc có mặt | `@NotNull Long customerId` | Số không có khái niệm “empty”; muốn dương thêm `@Positive` |
| Tên người dùng phải có chữ, không được toàn dấu cách | `@NotBlank String username` | Từ chối null, rỗng và toàn whitespace |
| Mã token phải có ít nhất một ký tự, khoảng trắng có thể là dữ liệu hợp lệ theo contract | `@NotEmpty String token` | Kiểm tra độ dài mà không bác bỏ whitespace |
| Danh sách sản phẩm phải có phần tử | `@NotEmpty List<Product> products` | Kiểm tra collection size |
| Danh sách nhãn phải có phần tử và không có nhãn trắng | `@NotEmpty List<@NotBlank String> labels` | Kết hợp constraint container và phần tử |
| Map tùy chọn nhưng nếu gửi phải có entry | Xử lý quy tắc có điều kiện riêng; `@NotEmpty` từ chối cả null và map rỗng | Chỉ dùng `@NotEmpty` nếu **bắt buộc có map và entry** |
| Giá trị tiền phải được cung cấp và dương | `@NotNull @Positive BigDecimal amount` | Không dùng `@NotEmpty` trên `BigDecimal` |
| Chuỗi không rỗng và tối đa 50 ký tự | `@NotEmpty @Size(max=50) String code` | Một constraint về hiện diện/độ dài tối thiểu, một về giới hạn tối đa |

**Ghi chú về `null` và constraint khác:** `@Size(min=1)` không thay thế hoàn toàn `@NotEmpty`: `@Size` thường coi `null` là hợp lệ theo đặc tả. Nếu dùng `@Size` một mình, giá trị null có thể vượt qua validation. Ghép `@NotNull`/`@NotEmpty` khi cần bắt buộc có dữ liệu.

## 5. Kết hợp với constraint trên phần tử và bean lồng nhau

### 5.1. Collection có dữ liệu và từng phần tử có dữ liệu

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import java.util.List;

public class CampaignRequest {
    @NotEmpty
    private List<@NotBlank String> tags;

    // Constructor/getter/setter tương ứng với cách binding.
}
```

Các tầng có ý nghĩa **khác nhau**:

- `@NotEmpty` trước `List` kiểm tra tham chiếu list khác null và list có ít nhất một phần tử.
- `@NotBlank` trong `List<@NotBlank String>` kiểm tra từng chuỗi phần tử. Một phần tử null, empty hoặc blank gây lỗi dù list không rỗng.
- Container element validation được hỗ trợ trong Jakarta Bean Validation 2.0+, phù hợp cho các collection/map với type argument có constraint.
- `List.of("")` có một phần tử nên qua phần collection nhưng trượt ở phần tử.
- `@NotBlank List<String>` đặt trên toàn list là **sai kiểu constraint**.

Nếu phần tử là một DTO con, cần phân biệt constraint trên tham chiếu với kiểm tra sâu vào bean:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.List;

public class OrderRequest {
    @NotEmpty
    private List<@NotNull @Valid OrderLine> lines;

    // OrderLine chứa các constraint trên field của chính nó.
}
```

Ở đây `@NotEmpty` bắt list có phần tử; `@NotNull` ngăn phần tử null; `@Valid` yêu cầu kiểm tra các constraint bên trong đối tượng `OrderLine`. `@Valid` **không tự động** làm list không rỗng. Đoạn code này là ví dụ cấu trúc, cần định nghĩa `OrderLine` để biên dịch trong dự án thực tế.

### 5.2. `@NotBlank` thường đủ, không nhất thiết cần thêm `@NotNull`

```java
@NotNull
@NotBlank
private String title;
```

Đặt đồng thời như trên thường **dư thừa về logic** bởi `@NotBlank` đã từ chối null. Nó còn có thể tạo **hai violation cho cùng giá trị null**, tùy validation groups và cấu hình. Với form chỉ muốn một thông báo “tiêu đề bắt buộc”, `@NotBlank` là lựa chọn rõ ràng hơn.

Tương tự, `@NotEmpty` đã bao gồm “not null”, nên `@NotNull @NotEmpty` thường không cần nếu cùng nhóm validation và cùng ý nghĩa. Có thể cố ý tách để đặt thông báo hoặc nhóm khác nhau, nhưng phải kiểm soát hành vi hiển thị nhiều lỗi.

### 5.3. `@NotBlank` không thay thế kiểm tra định dạng

Tên đăng nhập `"a"` thỏa `@NotBlank` nhưng có thể quá ngắn; email `"not-an-email"` cũng thỏa `@NotBlank`. Ghép constraint đúng nhu cầu:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class AccountInput {
    @NotBlank
    @Size(min = 3, max = 32)
    private String username;

    @NotBlank
    @Email
    private String email;
}
```

- `@NotBlank` kiểm tra có nội dung, kể cả yêu cầu không chỉ gồm dấu cách.
- `@Size` kiểm tra length/size, không bảo đảm văn bản có nghĩa hay bỏ khoảng trắng.
- `@Email` kiểm tra hình thức email trong phạm vi contract của validator; tự nó không thay thế việc bắt buộc trường (nhất là khi giá trị null).
- Nếu nghiệp vụ cần loại bỏ khoảng trắng hoặc chuẩn hóa Unicode, hãy có bước xử lý riêng và viết test thể hiện rõ giá trị **trước/sau** chuẩn hóa.

## 6. Khi dùng với Spring MVC / Spring Boot

### 6.1. Đường đi validation

Spring MVC có thể kích hoạt Jakarta Validation thông qua `@Valid` hoặc `@Validated` trên argument được bind. Với Spring Boot 3.x, thêm dependency `spring-boot-starter-validation` (provider tương thích với `jakarta.validation`) để có validator. Trong ví dụ REST thông thường:

```text
HTTP JSON body
     │
     ▼
Jackson deserialize → CreateUserRequest
     │
     ▼
@Valid / Spring MVC validation
     │
     ├── valid ───────► controller logic
     │
     └── invalid ─────► BindingResult / validation exception / HTTP 400
```

**`@NotNull`, `@NotEmpty` và `@NotBlank` không tự chạy khi gọi constructor**, và chỉ thêm annotation lên field không đồng nghĩa tất cả controller đều sẽ validate. Phải có điểm kích hoạt phù hợp: `@Valid`, `@Validated` hoặc gọi `jakarta.validation.Validator#validate(...)`.

### 6.2. DTO và controller minh họa

Đây là **đoạn code để thêm vào một ứng dụng Spring Boot 3 có Web MVC và starter-validation**, không phải file Java độc lập:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

public record CreateUserRequest(
    @NotNull Long departmentId,
    @NotBlank String displayName,
    @NotEmpty List<@NotBlank String> roles
) {}

@RestController
public class UserController {
    @PostMapping("/users")
    public ResponseEntity<Void> create(
            @Valid @RequestBody CreateUserRequest input) {
        // Ở ứng dụng thực, xử lý nghiệp vụ sau khi dữ liệu hợp lệ.
        return ResponseEntity.noContent().build();
    }
}
```

Với cấu hình Spring MVC thông thường, request có body:

```json
{
  "departmentId": 3,
  "displayName": "   ",
  "roles": ["ADMIN"]
}
```

sẽ có vi phạm `@NotBlank` cho `displayName`. Body có `"roles": []` vi phạm `@NotEmpty`; có `"roles": [""]` vi phạm ràng buộc phần tử `@NotBlank`, dù list không rỗng. Khi không có `BindingResult` xử lý tại controller, Spring MVC thường trả HTTP 400 cho lỗi validation của request body, nhưng **cấu trúc JSON lỗi cụ thể** phụ thuộc `@ControllerAdvice` và cấu hình ứng dụng.

**Phân biệt lỗi binding với lỗi validation:** Nếu JSON sai cú pháp hoặc field numeric không thể deserialize, Jackson/message converter có thể thất bại *trước khi* Bean Validation chạy. Không nhất thiết nhận được violation `@NotNull`/`@NotBlank` cho trường không parse được. Khi dùng `@ModelAttribute` thay cho `@RequestBody`, dữ liệu form/query đi qua data binding và cách ghi lỗi vào `BindingResult` có thể khác.

### 6.3. Giá trị thiếu, null và chuỗi rỗng ở HTTP boundary

Giả sử client gửi các body hợp lệ về cú pháp:

```json
{}
```

```json
{"displayName": null}
```

```json
{"displayName": ""}
```

```json
{"displayName": "   "}
```

Khi DTO có field tham chiếu `String displayName` và mapper đặt field thiếu thành null, kết quả theo Bean Validation với `@NotBlank` đều **không hợp lệ**; nhưng các trường hợp này khác về nguồn gốc và logging. Cấu hình Jackson, constructor/record binding, giá trị mặc định hoặc custom deserializer có thể thay đổi việc thiếu property được xử lý ra sao **trước** validation. Đừng tự suy rằng HTTP thiếu trường luôn biến thành null trong mọi DTO.

Với Spring data binding cho form, có thể tồn tại cấu hình như `StringTrimmerEditor` chuyển chuỗi toàn khoảng trắng thành null trước khi ràng buộc kiểm tra. Vì thế, khi debug, xác định rõ giá trị **thực tế vào Bean Validation** rồi mới kết luận annotation nào đã cho qua hay bắt lỗi.

## 7. Lỗi hay gặp và cách tránh

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `@NotNull` để bắt người dùng nhập nội dung | `""` và `"   "` vẫn hợp lệ | Chọn `@NotBlank` cho text có ý nghĩa |
| Dùng `@NotEmpty` cho tên người dùng | Chuỗi chỉ chứa dấu cách vẫn hợp lệ | Dùng `@NotBlank` |
| Dùng `@NotBlank` cho `List`, `Map`, array, `Integer` | Kiểu không được hỗ trợ, có thể lỗi validator | Dùng `@NotEmpty` cho container, `@NotNull` cho tham chiếu/số |
| Dùng `@NotEmpty List<String>` và tưởng các phần tử đều hợp lệ | List chứa `""` hoặc `null` có thể vẫn qua | Thêm `List<@NotBlank String>` hoặc constraint phần tử phù hợp |
| Dùng `@Size(min=1)` và nghĩ null bị chặn | `@Size` bỏ qua null theo đặc tả | Kết hợp `@NotNull` hoặc dùng `@NotEmpty` |
| Gắn `@NotNull @NotBlank` để “chắc ăn” | Trùng ý nghĩa và có thể hai lỗi cho null | `@NotBlank` thường đủ |
| Dùng `@NotBlank` và nghĩ giá trị đã được trim | Dữ liệu vẫn còn khoảng trắng đầu/cuối | Chuẩn hóa có chủ đích, test trước/sau |
| Dùng primitive `int` với `@NotNull` | Primitive không thể null | Dùng `Integer` để phân biệt thiếu giá trị |
| Thiếu dependency implementation Bean Validation | Annotation có thể tồn tại nhưng validation không chạy như kỳ vọng | Dùng provider tương thích, như `spring-boot-starter-validation` |
| Dùng `javax.validation` với Spring Boot 3/Jakarta | Không khớp hệ API đang dùng | Chuyển sang `jakarta.validation` và dependencies tương thích |
| Không có `@Valid`/`@Validated` hay gọi validator | Không có trigger kiểm tra dữ liệu | Bật validation tại boundary và kiểm thử nó |
| Assert nguyên văn thông báo tiếng Anh | Dễ thất bại khi locale/provider đổi | Assert field/path/constraint type và mã lỗi ổn định |
| Giả định mọi ký tự Unicode nhìn trống đều là whitespace như nhau | Quy tắc Unicode có thể khác giữa runtime/provider | Test ký tự cụ thể và quy định chuẩn hóa input rõ ràng |

### 7.1. Unicode whitespace và ký tự đặc biệt

`@NotBlank` được đặc tả cho `CharSequence` phải có ít nhất một ký tự không phải whitespace. Không nên kết luận rằng *mọi ký tự được Unicode phân loại là khoảng trống* sẽ bị mọi provider xử lý giống hệt nhau; các ký tự như no-break space, zero-width space hoặc dấu cách hẹp có thể khác các dấu cách thông thường. Đừng âm thầm sửa đầu vào bằng `trim()` hoặc `strip()` mà không kiểm thử ảnh hưởng tới contract.

Nếu hệ thống xử lý dữ liệu đa ngôn ngữ hoặc username có quy tắc phức tạp, hãy xác định chính sách hợp lệ (normalization, giới hạn độ dài theo Unicode code point, ký tự được phép) riêng ngoài ba annotation. Bản thân `@NotBlank` không bảo vệ khỏi toàn bộ trường hợp chuỗi khó nhìn, không đảm bảo nội dung an toàn HTML hay ngăn ký tự điều khiển.

### 7.2. Annotation không tương đương ràng buộc database

`@NotNull` của Bean Validation là quy tắc kiểm tra **ở lớp ứng dụng tại thời điểm validation được kích hoạt**. Dù Hibernate ORM có thể diễn giải metadata validation trong một số chế độ tích hợp, **đừng phụ thuộc** annotation này để thay thế `NOT NULL`, độ dài cột hoặc kiểm tra toàn vẹn dữ liệu của database. Ví dụ, database `NOT NULL` chặn null nhưng không chặn `""` hoặc `"   "`; quy tắc “phải có chữ” phải được kiểm tra ở tầng phù hợp. Nếu có nhiều đường ghi dữ liệu khác nhau, cần biện pháp đảm bảo nhất quán theo yêu cầu hệ thống.

## 8. Checklist kiểm thử và rà soát

Trước khi chọn annotation hoặc kết luận form/API đã kiểm tra đúng, đối chiếu các trường hợp:

- [ ] Với `String`, đã thử `null`, `""`, `"   "`, `"x"` và chuỗi có khoảng trắng đầu/cuối?
- [ ] Với collection, đã thử `null`, collection rỗng, collection có một phần tử rỗng và collection hợp lệ?
- [ ] Nếu các phần tử cũng phải hợp lệ, đã thêm type-use constraints/`@Valid` ở vị trí đúng?
- [ ] Với số, đã dùng `@NotNull` cộng constraint số phù hợp thay cho `@NotEmpty`?
- [ ] Nếu dùng `@Size`/`@Email`/`@Pattern`, đã xét riêng hành vi khi input bằng null?
- [ ] Nếu áp dụng `@NotBlank` trên văn bản Unicode, đã kiểm thử ký tự trắng thực tế và quy tắc chuẩn hóa?
- [ ] Trong Spring Boot 3+, import đúng package `jakarta.validation.*` và có provider?
- [ ] Đã có trigger kiểm tra (`@Valid`/`@Validated`/`Validator.validate`), chứ không chỉ khai báo annotation?
- [ ] Test phản hồi HTTP phân biệt JSON sai cú pháp, binding/type conversion thất bại và constraint violation?
- [ ] Khi kiểm thử, tránh lệ thuộc thứ tự `Set<ConstraintViolation>` hoặc message được dịch theo locale?

**Ghi nhớ:** `@NotNull` hỏi “**có tham chiếu không?**”; `@NotEmpty` hỏi “**có ít nhất một phần tử/ký tự không?**”; `@NotBlank` hỏi “**chuỗi có ít nhất một ký tự không phải khoảng trắng không?**”. Chọn theo **kiểu dữ liệu và ý nghĩa nghiệp vụ**, rồi kiểm thử tại đúng ranh giới kích hoạt Bean Validation của Spring.

### Tài liệu tham khảo chính thức

- [Jakarta Validation 3.0 — @NotNull](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/NotNull.html)
- [Jakarta Validation 3.0 — @NotEmpty](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/NotEmpty.html)
- [Jakarta Validation 3.0 — @NotBlank](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/NotBlank.html)
- [Jakarta Bean Validation 3.0 — Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Hibernate Validator 8 — Reference Guide](https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/)
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
