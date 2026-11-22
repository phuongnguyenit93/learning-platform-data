# @Null và @NotNull trong Jakarta Bean Validation và Spring Framework

## 1. Bài toán: “không có giá trị” khác với “giá trị rỗng”

Trong ứng dụng Spring, hai annotation `@Null` và `@NotNull` thuộc nhóm **ràng buộc chuẩn (built-in constraints)** của Jakarta Bean Validation. Chúng được dùng khi hợp đồng dữ liệu cần xác định một trường **phải vắng giá trị ở mức Java `null`**, hay **bắt buộc có tham chiếu khác `null`**.

Ví dụ với API quản lý đơn hàng:

- Khi **tạo** đơn hàng, client không được tự quyết định ID do hệ thống phát sinh: `id` cần là `null` trước khi server gán ID.
- Khi **cập nhật** đơn hàng, ID phải có để xác định tài nguyên: `id` cần khác `null`.
- Trường `name` phải có giá trị; nếu yêu cầu “phải chứa nội dung thực”, chỉ `@NotNull` là chưa đủ.

Hai quy tắc trông đơn giản nhưng ảnh hưởng trực tiếp đến thiết kế DTO, validation groups, conversion/binding, cách xử lý chuỗi rỗng, trường không có trong JSON và thời điểm kiểm tra dữ liệu.

## 2. Định nghĩa chính xác

Jakarta Validation khai báo:

```java
import jakarta.validation.constraints.Null;
import jakarta.validation.constraints.NotNull;

public class Example {
    @Null
    private Long id;

    @NotNull
    private String name;
}
```

- **`@Null`:** phần tử được chú thích **phải bằng `null`**.
- **`@NotNull`:** phần tử được chú thích **phải khác `null`**.
- Cả hai **chấp nhận mọi loại tham chiếu có thể nhận `null`**, ví dụ `String`, `Long`, `LocalDate`, enum, object, `List` và các giá trị trong container.
- Cả hai không kiểm tra nội dung, độ dài, số dương, tính đúng định dạng hay sự tồn tại trong database.
- Đây là annotation thuộc **`jakarta.validation.constraints`**; trong dự án Spring Framework 6 / Spring Boot 3, không dùng nhầm `javax.validation.constraints` của hệ trước.

Bảng chân trị của từng annotation:

| Giá trị Java | `@Null` | `@NotNull` | Nhận xét |
| --- | --- | --- | --- |
| `null` | Đạt | Vi phạm | Trường hợp phân biệt trực tiếp |
| `""` (chuỗi rỗng) | Vi phạm | Đạt | Chuỗi rỗng là một object khác null |
| `"   "` | Vi phạm | Đạt | Khoảng trắng không bị `@NotNull` cấm |
| `"hello"` | Vi phạm | Đạt | Nội dung không quan trọng với hai constraint này |
| `0`, `false` | Vi phạm nếu được boxing thành object | Đạt | Số 0/boolean false vẫn là giá trị |
| `List.of()` (collection rỗng) | Vi phạm | Đạt | Collection rỗng khác `null` |
| `new Object()` | Vi phạm | Đạt | Object có tồn tại |

**Điểm dễ nhầm:** ở thời điểm validation, `@NotNull` không quan tâm người dùng có gõ dữ liệu “hợp lý” hay không; nó chỉ quan tâm giá trị đang được validate có bằng `null` hay không. Do đó `@NotNull String name` vẫn chấp nhận `name=""` và `name="  "`.

### 2.1. Annotation đặt ở đâu?

Trong Jakarta Validation 3.x, `@Null` và `@NotNull` có thể áp dụng tại field, method/getter, parameter, constructor, annotation type và `TYPE_USE`. Thông thường:

```java
class CustomerForm {
    @NotNull
    private String email;                    // Field-level

    @NotNull
    public String getPhone() { return phone; } // Getter-level

    private String phone;
}
```

Ví dụ trên chỉ minh họa vị trí, không phải class hoàn chỉnh để bind vào MVC. Trong một bean thật, chọn **một vị trí khai báo nhất quán** cho mỗi constraint; đặt annotation giống hệt trên cả field và getter có thể khiến cùng một ý định được kiểm tra qua hai metadata constraint khác nhau.

Với `TYPE_USE`, có thể kiểm tra từng phần tử:

```java
class Shipment {
    @NotNull
    private List<@NotNull String> trackingCodes;
}
```

Ở đây `@NotNull` trên `trackingCodes` yêu cầu chính danh sách không được null; `List<@NotNull String>` yêu cầu mỗi phần tử trong danh sách khác null khi Bean Validation duyệt các phần tử của container được hỗ trợ. Danh sách vẫn được phép **rỗng**; để bắt buộc ít nhất một phần tử, dùng thêm `@NotEmpty` hoặc `@Size(min=1)`.

### 2.2. Không đặt `@Null` lên primitive nếu muốn kiểm tra null

Kiểu primitive `int`, `long`, `boolean` không thể chứa `null`. Vì vậy:

```java
@NotNull
private int age;
```

Annotation này không giúp phát hiện trường hợp người dùng **không truyền tuổi** sau khi binding đã hoàn tất: giá trị `age` có thể được khởi tạo mặc định thành `0`, và `0` không phải null. Nếu muốn biểu diễn “chưa cung cấp”, nên dùng wrapper:

```java
@NotNull
private Integer age;
```

Nếu gắn `@Null` lên primitive, một giá trị primitive thực tế luôn khác null; constraint sẽ không đạt khi được kiểm tra. Trong khi đó, Bean Validation **không thay thế bước binding**: thiếu field, giá trị sai kiểu và mặc định primitive còn tùy cơ chế tạo/bind object.

## 3. So sánh với @NotEmpty, @NotBlank và kiểm tra nội dung

Để xác định ràng buộc đúng, cần phân biệt **null**, **empty**, **blank** và **invalid format**.

| Constraint | `null` | `""` | `"  "` | `"abc"` | Dùng cho |
| --- | --- | --- | --- | --- | --- |
| `@Null` | Đạt | Không đạt | Không đạt | Không đạt | Bắt buộc vắng giá trị |
| `@NotNull` | Không đạt | Đạt | Đạt | Đạt | Bắt buộc khác null |
| `@NotEmpty` | Không đạt | Không đạt | Đạt | Đạt | Chuỗi, collection, map hoặc array không được rỗng |
| `@NotBlank` | Không đạt | Không đạt | Không đạt | Đạt | `CharSequence` phải có ký tự không phải khoảng trắng |

Trong bảng, `@NotEmpty` và `@NotBlank` được xét với giá trị `String`; không áp dụng tùy tiện `@NotBlank` lên `Integer` hoặc `List`.

Ví dụ:

```java
class RegisterRequest {
    @NotNull
    private Long departmentId; // Có ID; chưa biết ID đó có tồn tại trong DB hay không.

    @NotBlank
    private String username;   // Không null, rỗng hoặc toàn khoảng trắng.

    @NotEmpty
    private List<String> roles; // Có ít nhất một phần tử; nội dung phần tử kiểm tra riêng.
}
```

`@NotBlank` là lựa chọn phù hợp hơn `@NotNull` cho tên bắt buộc có nội dung. Với collection có phần tử bắt buộc không null, kết hợp `@NotEmpty List<@NotNull String>`. Với số cần lớn hơn 0, có thể kết hợp `@NotNull` với `@Positive` hoặc `@Min(1)`. Với email, cần yêu cầu không rỗng một cách tường minh ngoài `@Email` theo hợp đồng ứng dụng; không suy ra `@Email` tự cấm `null`.

**Không nên viết `@Null @NotNull` cho cùng một trường trong cùng validation group**: không có giá trị nào có thể đồng thời bằng null và khác null. Chỉ dùng cả hai khi chúng phục vụ những **nhóm khác nhau** hoặc các điều kiện nghiệp vụ được mô hình hóa rõ ràng.

## 4. Validation groups: cùng một field, yêu cầu khác nhau khi tạo và cập nhật

Một trường hợp rất phổ biến là ID server cấp:

```java
import jakarta.validation.constraints.Null;
import jakarta.validation.constraints.NotNull;

interface Create {}
interface Update {}

class OrderCommand {
    @Null(groups = Create.class)
    @NotNull(groups = Update.class)
    private Long id;

    // Getter/setter hoặc constructor binding được định nghĩa trong code thực tế.
}
```

- Khi tạo: `validator.validate(command, Create.class)` yêu cầu `id == null`.
- Khi cập nhật: `validator.validate(command, Update.class)` yêu cầu `id != null`.
- Nếu gọi `validator.validate(command)` không truyền group, mặc định chạy nhóm `Default`. **Hai constraint trên không chạy trong `Default`** vì chỉ khai báo cho `Create` hoặc `Update`.
- `@Valid` của Jakarta không có thuộc tính group; để chọn nhóm trong Spring MVC, dùng `@Validated(Create.class)` hoặc `@Validated(Update.class)` của Spring ở vị trí hỗ trợ.

Ví dụ controller MVC (mã tích hợp, không phải chương trình Java standalone):

```java
@PostMapping("/orders")
ResponseEntity<?> create(
        @Validated(Create.class) @RequestBody OrderCommand command,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body("Invalid order");
    }
    // Phân quyền, áp dụng quy tắc nghiệp vụ rồi cấp ID tại service.
    return ResponseEntity.ok().build();
}

@PutMapping("/orders/{id}")
ResponseEntity<?> update(
        @PathVariable Long id,
        @Validated(Update.class) @RequestBody OrderCommand command,
        BindingResult errors) {
    if (errors.hasErrors() || !id.equals(command.getId())) {
        return ResponseEntity.badRequest().body("Invalid order");
    }
    return ResponseEntity.ok().build();
}
```

Cần import những kiểu Spring MVC, `@Validated`, `BindingResult`, `OrderCommand` và `ResponseEntity`, đồng thời định nghĩa getter/binding tương ứng cho DTO. Đường dẫn và kiểm tra ID ở đây minh họa quy tắc nghiệp vụ; mã production cần giải quyết cả phân quyền, tài nguyên không tồn tại, race condition và trạng thái database.

**Lưu ý về độ tin cậy:** `@Null(groups=Create.class)` đảm bảo ID *sau khi bind* đang null, **không tự chứng minh client đã không gửi field**. Trong JSON, “field vắng mặt” và `"id": null` thường cùng thành một giá trị Java `null`; cả hai vượt qua `@Null`. Khi yêu cầu nghiêm ngặt cấm client gửi trường, phải dùng DTO riêng không có property đó, kiểm soát JSON mapping, hoặc kiểm tra cấu trúc input ở tầng phù hợp.

**Giữ ID khỏi mass assignment:** đừng dựa vào `@Null` thay cho cấu hình trường client được phép ghi; dùng DTO theo action, kiểm soát property binder/mapper và gán ID phía server. Dữ liệu hợp lệ về nullability chưa chắc hợp lệ về phân quyền.

## 5. Ví dụ Java 17+ chạy độc lập: @Null, @NotNull và groups

Ví dụ sử dụng **Jakarta Validation 3.x** và Hibernate Validator 8 làm provider. Chương trình minh họa: ID phải null khi tạo, phải khác null khi cập nhật; tên và danh sách phải khác null trong nhóm mặc định; địa chỉ con chỉ được kiểm tra khi cascade `@Valid` chạy.

### 5.1. Cấu hình Maven

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>null-constraints-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.1.Final</version>
        </dependency>
    </dependencies>
</project>
```

`hibernate-validator` mang theo Jakarta Validation API và dependency transitive cần thiết. Để ví dụ chạy từ command line mà không bắt buộc cài thư viện Jakarta Expression Language, chương trình dùng `ParameterMessageInterpolator` của Hibernate Validator. Thành phần này là chi tiết provider, không phải giao diện chuẩn; ứng dụng sử dụng mẫu message có biểu thức EL cần cấu hình hỗ trợ EL phù hợp.

### 5.2. Mã nguồn `NullConstraintsDemo.java`

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Null;
import jakarta.validation.constraints.NotNull;

import org.hibernate.validator.HibernateValidator;
import org.hibernate.validator.messageinterpolation.ParameterMessageInterpolator;

import java.util.List;
import java.util.Set;

public class NullConstraintsDemo {

    public interface Create {}
    public interface Update {}

    public static final class Address {
        @NotNull
        private final String city;

        public Address(String city) {
            this.city = city;
        }
    }

    public static final class OrderCommand {
        @Null(groups = Create.class)
        @NotNull(groups = Update.class)
        private final Long id;

        @NotNull
        private final String name;

        @NotNull
        private final List<String> tags;

        @Valid
        private final Address address;

        public OrderCommand(Long id, String name, List<String> tags, Address address) {
            this.id = id;
            this.name = name;
            this.tags = tags;
            this.address = address;
        }

        public Long getId() {
            return id;
        }
    }

    private static void print(
            String label, Set<? extends ConstraintViolation<?>> violations) {
        List<String> paths = violations.stream()
                .map(v -> v.getPropertyPath().toString())
                .sorted()
                .toList();
        System.out.println(label + " -> " + paths.size() + " " + paths);
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory = Validation
                .byProvider(HibernateValidator.class)
                .configure()
                .messageInterpolator(new ParameterMessageInterpolator())
                .buildValidatorFactory()) {

            Validator validator = factory.getValidator();

            // id=null thỏa Create; name="" và tags=[] đều khác null.
            OrderCommand draft = new OrderCommand(
                    null, "", List.of(), new Address(null));

            // Đối tượng có id nhưng ba constraint thuộc Default vi phạm.
            OrderCommand saved = new OrderCommand(
                    7L, null, null, new Address(null));

            print("draft Default", validator.validate(draft));
            print("draft Create", validator.validate(draft, Create.class));
            print("draft Update", validator.validate(draft, Update.class));

            print("saved Default", validator.validate(saved));
            print("saved Create", validator.validate(saved, Create.class));
            print("saved Update", validator.validate(saved, Update.class));

            print("draft.name", validator.validateProperty(draft, "name"));
            print("draft.address", validator.validateProperty(draft, "address"));

            print("candidate.name=null", validator.validateValue(
                    OrderCommand.class, "name", null));
            print("candidate.id=7 Create", validator.validateValue(
                    OrderCommand.class, "id", 7L, Create.class));
            print("candidate.id=null Update", validator.validateValue(
                    OrderCommand.class, "id", null, Update.class));

            System.out.println("savedId=" + saved.getId());
        }
    }
}
```

### 5.3. Biên dịch và chạy

JDK 17+ và Maven, chạy từ thư mục có hai tệp trên.

Bash (Linux/macOS):

```bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
CP="$(cat classpath.txt)"
javac -encoding UTF-8 -cp "$CP" NullConstraintsDemo.java
java -cp ".:$CP" NullConstraintsDemo
```

PowerShell (Windows):

```powershell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
$cp = (Get-Content -Raw classpath.txt).Trim()
javac -encoding UTF-8 -cp $cp NullConstraintsDemo.java
java -cp ".;$cp" NullConstraintsDemo
```

Stdout kỳ vọng (bỏ qua log/cảnh báo của provider hoặc Maven nếu môi trường in ra):

```text
draft Default -> 1 [address.city]
draft Create -> 0 []
draft Update -> 1 [id]
saved Default -> 3 [address.city, name, tags]
saved Create -> 1 [id]
saved Update -> 0 []
draft.name -> 0 []
draft.address -> 0 []
candidate.name=null -> 1 [name]
candidate.id=7 Create -> 1 [id]
candidate.id=null Update -> 1 [id]
savedId=7
```

Giải thích:

- `draft Default` chỉ vi phạm `address.city`: `name=""` và `tags=[]` vẫn thỏa `@NotNull`. `@Valid` trên `address` cho phép đi vào kiểm tra `@NotNull` của `city`.
- `draft Create` đạt do ID null và chỉ có constraint `@Null(groups=Create.class)` được chọn; nhóm `Default` không tự động chạy kèm.
- `draft Update` vi phạm vì ID null; yêu cầu `@NotNull(groups=Update.class)`.
- `saved Default` vi phạm ở `name`, `tags` và `address.city`, nhưng không kiểm tra hai constraint ID vì chúng không thuộc nhóm `Default`.
- `saved Create` vi phạm vì ID đã có giá trị; `saved Update` đạt vì ID khác null.
- `validateProperty(draft, "address")` không đi theo cascade `@Valid`, nên trả 0 khi property `address` không có constraint trực tiếp.
- `validateValue` thử ứng viên mà không sửa instance; ba lời gọi minh họa null/khác-null trong nhóm tương ứng.
- `getPropertyPath()` được sắp xếp trước khi in để stdout không phụ thuộc thứ tự lặp của `Set<ConstraintViolation<?>>`.

**Phạm vi ví dụ:** đây là Bean Validation thuần Java. `OrderCommand` ở đây immutable nhằm minh họa kiểm tra object đã tạo; không mặc nhiên là DTO bind được từ mọi request MVC. Khi dùng ở Spring MVC, cần cấu hình constructor binding/deserialization phù hợp hoặc xây DTO có setter/builder tùy yêu cầu.

## 6. Tích hợp với Spring Framework: khi nào constraint được thực thi?

Gắn annotation trên field **không đủ để mọi lần gán giá trị đều tự động ném lỗi**. Spring phải có cơ chế kích hoạt validation.

### 6.1. Spring MVC với form và JSON

Đối với form `@ModelAttribute` hoặc body `@RequestBody`:

```java
@PostMapping("/customers")
public ResponseEntity<?> create(
        @Valid @RequestBody CustomerRequest request,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest()
                .body(errors.getFieldErrors().stream()
                        .map(e -> e.getField() + ": " + e.getCode())
                        .toList());
    }

    return ResponseEntity.ok().build();
}
```

Đoạn trên là mã bên trong controller, dùng các import `jakarta.validation.Valid` và Spring MVC phù hợp. `CustomerRequest` là DTO phải có các property/annotation mong muốn; đối tượng cần được JSON deserializer tạo thành công trước khi Bean Validation có thể đánh giá constraint.

- `@Valid` kích hoạt validation đối tượng với nhóm mặc định.
- `@Validated(Create.class)` từ Spring giúp chọn nhóm khi cần kiểm tra những constraint dành riêng thao tác Create.
- `BindingResult` đứng ngay sau tham số tương ứng để controller nhận lỗi trong những trường hợp Spring hỗ trợ; tùy chữ ký và loại validation, lỗi có thể phát sinh dạng `MethodArgumentNotValidException` hoặc `HandlerMethodValidationException`. Không giả định một exception duy nhất cho mọi trường hợp.
- Với `@RequestBody`, JSON sai cú pháp hoặc kiểu chuyển đổi sai có thể bị từ chối **trước Bean Validation**, và không nhất thiết đi qua cùng `BindingResult` như violation `@NotNull`.

Trong một ứng dụng Spring Boot phù hợp, sử dụng starter validation để có API + provider (ví dụ Hibernate Validator). Nếu classpath thiếu provider hoặc không đăng ký validator cho MVC, annotation có thể không được đánh giá như kỳ vọng.

### 6.2. Phân biệt “bắt buộc có property trong request” và “khác null sau binding”

Hai loại yêu cầu **không tương đương**:

1. **`@NotNull` trên thuộc tính Java:** kiểm tra giá trị cuối cùng khác null khi Bean Validation chạy.
2. **Yêu cầu client phải gửi field trong wire format:** kiểm tra sự hiện diện của key/parameter trong HTTP request.

Ví dụ JSON:

```json
{}
```

và:

```json
{"name": null}
```

Với DTO có `String name` và deserializer mặc định không áp dụng thêm điều kiện hiện diện, cả hai trường hợp thường tạo `name == null`; `@NotNull` sẽ từ chối cả hai. Nếu cần **phân biệt** thiếu field với explicit null (ví dụ JSON Merge Patch), cần mô hình input hỗ trợ trạng thái hiện diện hoặc cơ chế mapping riêng.

Ngược lại, JSON:

```json
{"name": ""}
```

thường tạo giá trị Java `""`; `@NotNull` cho phép, còn `@NotBlank` từ chối. Ở form binding, `StringTrimmerEditor`, custom converter hoặc cấu hình binder có thể đổi chuỗi rỗng/blank thành null; kết quả `@NotNull` sau đó sẽ khác so với khi chưa trim. Đó là tác động của bước **conversion/normalization** đi trước validation, không phải bản thân annotation.

### 6.3. Method parameters và response validation

Bean Validation cũng hỗ trợ parameter/return value constraints:

```java
// Phương thức minh họa hợp đồng; cần được đi qua validation interceptor
// hoặc cơ chế method validation của framework.
public String find(@NotNull Long id) {
    return "order-" + id;
}
```

Việc annotation `@NotNull` trên tham số **không tự đảm bảo** mọi lời gọi Java nội bộ sẽ được kiểm tra; nó cần `ExecutableValidator` hoặc tích hợp method validation thích hợp. Spring MVC bản mới có hỗ trợ method validation đối với tham số controller; Spring service có thể cần `@Validated`/proxy hoặc cấu hình khác tùy stack và cách gọi.

Với request HTTP, `@RequestParam(required=true)` là quy tắc **ràng buộc tham số hiện diện** ở tầng MVC; đây không phải cách thay thế tổng quát cho `@NotNull` trên bean field. Đừng dùng `@Null` để cấm người dùng gửi một tham số; nếu policy là “field không có trong payload”, dùng DTO, bộ lọc field hoặc kiểm tra payload hiện diện.

### 6.4. Trong service và kiểm tra thủ công

Có thể inject trực tiếp `jakarta.validation.Validator`:

```java
@Service
public class CustomerValidationService {
    private final jakarta.validation.Validator validator;

    public CustomerValidationService(
            jakarta.validation.Validator validator) {
        this.validator = validator;
    }

    public void check(CustomerRequest request) {
        var violations = validator.validate(request);
        if (!violations.isEmpty()) {
            throw new IllegalArgumentException("Invalid customer");
        }
    }
}
```

Đây là đoạn tích hợp; `CustomerRequest` và `@Service` cần được định nghĩa/import đúng. Với ứng dụng sản xuất, hãy chuyển `ConstraintViolation` sang thông báo/mã lỗi thống nhất, không trả nguyên giá trị vi phạm nếu chứa dữ liệu nhạy cảm.

Hai giao diện dễ nhầm: `jakarta.validation.Validator` có `validate(object)` trả `Set<ConstraintViolation<T>>`; `org.springframework.validation.Validator` có `supports(...)` và `validate(object, Errors)`. `LocalValidatorFactoryBean` của Spring là cầu nối cho tích hợp Bean Validation.

## 7. Đối tượng lồng nhau và collection: nullability ở từng cấp

Xét:

```java
class Invoice {
    @NotNull
    @Valid
    private BillingAddress address;

    @NotNull
    private List<@NotNull String> tags;
}

class BillingAddress {
    @NotNull
    private String city;
}
```

Có ba điều kiện khác nhau:

1. `address != null` nhờ `@NotNull`; `@Valid` cho phép kiểm tra `address.city` khi `address` tồn tại.
2. `tags != null` nhờ `@NotNull` đặt trên collection.
3. Từng phần tử của `tags` phải khác null nhờ `List<@NotNull String>`, nhưng `tags=[]` **vẫn hợp lệ**.

Không lẫn lộn `@NotNull` với `@Valid`: `@Valid` chỉ kích hoạt cascade và tự nó không đòi thuộc tính khác null. Nếu một quan hệ tùy chọn được để `null` thì việc cascade bỏ qua đối tượng không tồn tại là hợp lý; nếu quan hệ bắt buộc, dùng `@NotNull @Valid` cùng nhau.

Khi validate từng field:

```java
validator.validate(invoice);                     // Xét graph nếu @Valid.
validator.validateProperty(invoice, "address");  // Không cascade vào address.city.
```

`validateValue(Invoice.class, "address", ...)` cũng không cascade. Để kết luận toàn object hợp lệ, dùng `validate` với các nhóm phù hợp.

## 8. Groups, thông báo lỗi và kiểm thử đúng kỳ vọng

### 8.1. Thuộc tính của constraint

`@Null` và `@NotNull` đều có ba thuộc tính chuẩn:

- `message`: mẫu thông báo (mặc định các message key được provider dịch qua `ValidationMessages.properties`/bundle hỗ trợ).
- `groups`: nhóm áp dụng; để trống nghĩa là thuộc nhóm `Default`.
- `payload`: metadata mở rộng; bản thân payload không tự làm thay đổi điều kiện null/khác-null.

```java
@NotNull(
    message = "{order.customer.required}",
    groups = Create.class
)
private Long customerId;
```

Đây là một field minh họa trong bean có `Create` group. Khi dùng message key, cần bundle chứa nội dung tương ứng. `ConstraintViolation#getMessage()` có thể phụ thuộc locale và provider; kiểm thử ổn định nên so theo property path, template hoặc metadata constraint khi cần.

### 8.2. Kiểm thử nên bao phủ những gì?

| Đầu vào / thao tác | Kỳ vọng |
| --- | --- |
| `@Null Long id` với `id=null` | Đạt |
| `@Null Long id` với `id=0L` | Vi phạm |
| `@NotNull String name` với `name=null` | Vi phạm |
| `@NotNull String name` với `name=""` | Đạt |
| `@NotNull String name` với `name="   "` | Đạt |
| `@NotEmpty String name` với `name=""` | Vi phạm |
| `@NotBlank String name` với `name="   "` | Vi phạm |
| `@NotNull List<String> tags` với `tags=[]` | Đạt |
| `List<@NotNull String>` với phần tử null | Vi phạm ở phần tử đó |
| `@Null(groups=Create.class)` gọi nhóm Update | Không áp dụng constraint Create |
| `@NotNull(groups=Update.class)` gọi nhóm Create | Không áp dụng constraint Update |
| `@NotNull @Valid Address address` với `address=null` | Vi phạm `@NotNull` |
| `@Valid Address address` với `address=null` | Bỏ qua cascade; không vi phạm chỉ vì null |

Viết test cho cả **bean hợp lệ**, **bean sai ràng buộc**, **đúng nhóm** và **mức HTTP**. Trong Spring MVC, nên kiểm tra JSON/form được deserializer và binder tạo ra object như thế nào trước khi assert thông báo `@NotNull`.

### 8.3. Trường hợp cần nhiều hơn @Null/@NotNull

Nếu nghiệp vụ yêu cầu:

- Tên bắt buộc có chữ: `@NotBlank`.
- Danh sách có ít nhất một phần tử: `@NotEmpty` hoặc `@Size(min=1)`.
- Giá trị số nằm trong khoảng: `@Min`, `@Max`, `@Positive`/`@Negative` kết hợp nullability khi cần.
- Chuỗi phù hợp regex: `@Pattern` và constraint khác kiểm tra rỗng/null phù hợp.
- Ngày tương lai: `@Future` hoặc `@FutureOrPresent` cùng `@NotNull` nếu bắt buộc nhập.
- Mã ID phải tồn tại trong cơ sở dữ liệu: kiểm tra ở service/repository hoặc custom validator có chính sách phù hợp; `@NotNull` chỉ biết ID có khác null.

Không dùng `@NotNull` thay cho một quy tắc nghiệp vụ phức tạp rồi kỳ vọng provider tự hiểu ý định.

## 9. Lỗi phổ biến và cách khắc phục

| Lỗi | Nguyên nhân thực tế | Khắc phục |
| --- | --- | --- |
| `@NotNull` không bắt chuỗi rỗng | `"" != null` | Dùng `@NotBlank` hoặc `@NotEmpty` phù hợp |
| `@NotNull` trên `int` không phát hiện thiếu input | Primitive không thể null, giá trị mặc định có thể là 0 | Dùng `Integer`, phân biệt binding lỗi và constraint |
| `@Null` dùng để cấm client gửi field nhưng `"id":null` vẫn qua | Annotation kiểm tra giá trị sau bind, không kiểm tra key tồn tại | Dùng DTO riêng/kiểm tra cấu trúc payload |
| `@Null` và `@NotNull` cùng một group trên một field | Hai điều kiện mâu thuẫn | Dùng groups Create/Update khác nhau hoặc DTO riêng |
| `@NotNull List<String>` vẫn chấp nhận danh sách rỗng | Nullability khác kích thước collection | Dùng `@NotEmpty` nếu cần danh sách có phần tử |
| `@NotNull` đặt trên `Optional<T>` nhưng `Optional.empty()` vẫn đạt | Object `Optional` khác null | Validate nội dung theo cách biểu diễn phù hợp; không dùng Optional field khi không cần |
| Có annotation nhưng API vẫn nhận dữ liệu không hợp lệ | Không kích hoạt Bean Validation hoặc thiếu provider | Cấu hình provider và `@Valid`/`@Validated` đúng vị trí |
| Lỗi JSON sai kiểu bị hiểu là lỗi `@NotNull` | Deserialization xảy ra trước validation | Xử lý lỗi `HttpMessageConverter`/Jackson và validation riêng |
| Chỉ dùng `@Valid` trên nested field rồi kỳ vọng null bị cấm | Cascade không đồng nghĩa `@NotNull` | Kết hợp `@NotNull @Valid` nếu bắt buộc |
| Gọi validator với nhóm Create nhưng field ở Default không chạy | Chỉ nhóm được chọn (và quy tắc liên quan) được xét | Chọn group chính xác, sequence/kế thừa nếu cần |
| Lấy `getMessage()` làm khóa logic lâu dài | Message có thể dịch theo locale | Dùng mã constraint/message template/field để phân loại |
| Dùng `@NotNull` để kiểm tra quyền cập nhật ID | Nullability không thể xác nhận quyền truy cập | Kiểm tra quyền và quyền sở hữu tại service |
| Đặt annotation ở field và getter rồi thấy nhiều lỗi | Metadata constraint bị khai báo lặp | Chọn một chiến lược đặt constraint nhất quán |
| Dùng package `javax.validation` trên Spring 6 | Khác namespace Jakarta | Dùng `jakarta.validation` và provider tương ứng |

## 10. Quy trình chọn annotation khi thiết kế DTO

Khi định nghĩa field, xác định theo thứ tự:

1. **Giá trị bắt buộc vắng mặt trong thao tác này?** Dùng `@Null` nếu cần kiểm tra null sau binding; để **cấm gửi property**, thiết kế input contract/DTO phù hợp.
2. **Giá trị bắt buộc phải có?** Dùng `@NotNull` với reference type; nếu là chuỗi cần nội dung, cân nhắc `@NotBlank`.
3. **Collection có thể rỗng không?** Nếu không, dùng `@NotEmpty` hoặc `@Size(min=1)`.
4. **Quan hệ nested có bắt buộc và cần kiểm tra sâu không?** Dùng `@NotNull @Valid` nếu cả hai yêu cầu.
5. **Create và Update có nullability trái ngược?** Chọn DTO theo action hoặc validation groups có policy rõ ràng, đừng gắn hai constraint mâu thuẫn cùng nhóm.
6. **Dữ liệu đến từ HTTP/JSON?** Kiểm tra mapping, thiếu field, explicit null, rỗng và trạng thái sau normalization trước khi kết luận constraint hoạt động đúng.
7. **Có quy tắc bảo mật hay nghiệp vụ?** Áp dụng độc lập ở tầng phù hợp; Bean Validation là một phần kiểm tra tính hợp lệ, không phải cơ chế phân quyền.

**Ghi nhớ:** `@Null` buộc giá trị Java phải là `null`; `@NotNull` buộc giá trị Java phải khác `null`. Chúng không kiểm tra nội dung chuỗi, không phát hiện chính xác việc client có gửi key, không thay bước conversion/binding và không thay quy tắc nghiệp vụ. Chọn annotation theo hợp đồng dữ liệu thật sự, kết hợp constraint khác và group phù hợp trước khi đưa vào Spring controller.

### Tài liệu tham khảo

- Jakarta Validation API 3.1 — `@Null`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraints/Null.html
- Jakarta Validation API 3.1 — `@NotNull`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraints/NotNull.html
- Jakarta Bean Validation 3.0 specification — built-in constraints và groups: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Hibernate Validator 8 Reference Guide: https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/
- Spring Framework — Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring MVC — Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring MVC — Validation configuration: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html
