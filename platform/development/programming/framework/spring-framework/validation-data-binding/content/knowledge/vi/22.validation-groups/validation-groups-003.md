# Truyền nhóm vào Validator hoặc @Validated trong Spring Framework

## 1. Mục tiêu: chọn đúng bộ quy tắc cần kiểm tra theo ngữ cảnh

Một DTO có thể phục vụ nhiều luồng nghiệp vụ: tạo mới (`Create`), cập nhật (`Update`), gửi duyệt (`Submit`). Cùng một trường dữ liệu nhưng yêu cầu không phải lúc nào cũng giống nhau:

- Khi **tạo**, `id` do server sinh nên phải bằng `null`.
- Khi **cập nhật**, `id` cần khác `null`.
- Tên hàng hóa (`name`) luôn bắt buộc; trong nhiều thiết kế nó thuộc nhóm mặc định `Default`.
- Số lượng (`quantity`) phải dương khi tạo hoặc cập nhật.

**Validation groups** của Jakarta Bean Validation cho phép khai báo tập constraint theo ngữ cảnh và **truyền nhóm khi thực hiện validation**, thay vì sao chép toàn bộ constraint hay viết nhiều nhánh `if` trong validator.

Bài này tập trung vào **hai con đường truyền nhóm**:

1. **Gọi `jakarta.validation.Validator` bằng code:** `validator.validate(bean, Create.class)`, `validateProperty(...)` hoặc `validateValue(...)`.
2. **Để Spring kích hoạt validation:** `@Validated(Create.class)` trên tham số MVC hoặc trong cấu hình method validation, theo đúng điểm áp dụng.

Điểm then chốt: **`@Valid` của Jakarta không có thuộc tính để chọn group**, còn **`@Validated` của Spring cho phép chỉ định group**. Tuy nhiên vị trí đặt `@Validated` (tham số controller hay kiểu service) quyết định *cơ chế nào* sẽ thực thi; không phải mọi annotation `@Validated` đều hoạt động giống nhau.

## 2. Định nghĩa nhóm và đặt constraint vào nhóm

Một group thường là **interface marker rỗng**. Không cần cài đặt method:

```java
public interface Create {}
public interface Update {}
```

Đây là hai interface minh họa; trong mã chạy độc lập ở phần 5 chúng được khai báo là interface lồng trong một class.

Khai báo constraint:

```java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;

public class ProductForm {

    @NotBlank
    private String name;

    @Null(groups = Create.class)
    @NotNull(groups = Update.class)
    private Long id;

    @Min(value = 1, groups = {Create.class, Update.class})
    private int quantity;
}
```

Ý nghĩa:

- `@NotBlank` không ghi `groups` ⇒ thuộc **`jakarta.validation.groups.Default`**.
- `@Null(groups=Create.class)` chỉ thuộc nhóm `Create`.
- `@NotNull(groups=Update.class)` chỉ thuộc nhóm `Update`.
- `@Min(..., groups={Create.class,Update.class})` thuộc cả hai nhóm.
- Đặt `@Null` và `@NotNull` cùng property **không mâu thuẫn** trong trường hợp này vì chúng thuộc hai nhóm được dùng trong **những thao tác khác nhau**. Nhưng nếu validate đồng thời `Create` và `Update` trên cùng đối tượng, `id` không thể thỏa cả hai điều kiện.

> Hãy coi `groups` trên annotation là **quy tắc được đăng ký cho nhóm nào**, còn đối số `groups` khi gọi `Validator` hay `@Validated` là **nhóm nào được yêu cầu thực thi**.

### 2.1. Group mặc định không tự chạy kèm nhóm khác

Nếu constraint không khai báo `groups`, nó nằm trong nhóm `Default`. Khi không truyền nhóm vào API, Bean Validation tự chọn `Default`.

```java
validator.validate(form);                          // Default
validator.validate(form, Default.class);           // Default tường minh
validator.validate(form, Create.class);            // Create
validator.validate(form, Update.class);            // Update
validator.validate(form, Default.class, Create.class);
```

Khi truyền **chỉ** `Create.class`, các constraint chỉ thuộc `Default` **không tự động chạy kèm**, trừ khi có **group inheritance, group sequence, group conversion** hoặc metadata liên quan tạo ra tác động đó. Đây là sai sót phổ biến: một form trả về tập violation rỗng khi `Create` được chọn dù `name` rỗng, vì `name` chỉ có `@NotBlank` ở `Default`.

Có ba hướng thiết kế nếu muốn kiểm tra `name` trong Create:

1. Gán constraint cho cả hai nhóm: `@NotBlank(groups={Default.class,Create.class})`.
2. Khi gọi thủ công, truyền `Default.class, Create.class`.
3. Thiết kế kế thừa/sequence nhóm rõ ràng khi có ý nghĩa dài hạn.

Không dùng group tùy ý mà không biết constraint nào được bao phủ.

## 3. Truyền nhóm trực tiếp qua jakarta.validation.Validator

Giao diện chuẩn `jakarta.validation.Validator` nhận varargs `Class<?>... groups`. Ba method thường dùng:

| API | Đầu vào | Phạm vi |
| --- | --- | --- |
| `validate(T object, Class<?>... groups)` | Bean đang có + nhóm | Tất cả constraint trong phạm vi object graph phù hợp, có cascade `@Valid` |
| `validateProperty(T object, String propertyName, Class<?>... groups)` | Bean + tên property + nhóm | Constraint tại **một property hiện có**, không cascade |
| `validateValue(Class<T> beanType, String propertyName, Object value, Class<?>... groups)` | Lớp bean + tên property + candidate + nhóm | Constraint của **một property trên giá trị giả định**, không cần instance, không cascade |

Các method này trả về `Set<ConstraintViolation<T>>`. Tập rỗng nghĩa là **các constraint được chọn trong phạm vi gọi hiện tại** không phát hiện vi phạm; không chứng minh mọi rule của ứng dụng đã được kiểm tra.

### 3.1. Ví dụ truyền một hoặc nhiều group

```java
Set<ConstraintViolation<ProductForm>> createErrors =
        validator.validate(form, Create.class);

Set<ConstraintViolation<ProductForm>> updateErrors =
        validator.validate(form, Update.class);

Set<ConstraintViolation<ProductForm>> combinedErrors =
        validator.validate(form, Default.class, Create.class);
```

Cả ba lệnh trên dùng **cùng một object**, khác ở danh sách group. **Không có thứ tự thực thi được đảm bảo** chỉ vì ta truyền `Default.class` trước `Create.class`. Muốn đánh giá theo thứ tự và dừng khi nhóm trước lỗi, dùng `@GroupSequence` (mục 7).

**Chú ý:** truyền đồng thời `Create` và `Update` cho ví dụ có `@Null` và `@NotNull` trên cùng ID sẽ không hữu ích: với mọi ID, ít nhất một trong hai nhóm không thỏa. Group thể hiện *tình huống* chứ không nhất thiết là các bộ rule nên gộp bừa bãi.

### 3.2. validateProperty và validateValue vẫn chọn nhóm

Khi chỉ cần kiểm tra ID ở một bước UI:

```java
validator.validateProperty(form, "id", Create.class);

validator.validateValue(
        ProductForm.class, "id", 123L, Create.class);
```

Lệnh đầu kiểm tra **giá trị ID đang nằm trong `form`**. Lệnh thứ hai kiểm tra `123L` theo constraint của `id` trong nhóm `Create`, **không cần tạo ProductForm mới** và **không thay đổi `form`**.

Giới hạn của hai API field-level:

- Không thực thi các constraint class-level/cross-field chỉ vì chúng liên quan đến property.
- Không cascade vào bean con qua `@Valid`.
- Với `validateValue`, giá trị phải phù hợp với kiểu constraint; không phải công cụ convert chuỗi HTTP.
- Không dùng kết quả field-level đơn lẻ để khẳng định cả DTO hợp lệ.
- `propertyName` phải là property hợp lệ; tên không đúng hoặc tham số null không hợp lệ có thể tạo exception, không phải luôn trả một tập lỗi rỗng.

Đối với bước chấp nhận request cuối cùng, ưu tiên kiểm tra toàn object bằng `validate(bean, groups...)` hoặc cơ chế Spring tương đương.

### 3.3. Phân biệt jakarta.validation.Validator và Spring Validator

Hai giao diện có tên giống nhau nhưng method khác nhau:

```text
jakarta.validation.Validator
    validate(bean, Class<?>... groups)
    validateProperty(bean, "field", Class<?>... groups)
    validateValue(Bean.class, "field", candidate, Class<?>... groups)

org.springframework.validation.Validator
    supports(Class<?> clazz)
    validate(Object target, Errors errors)

org.springframework.validation.SmartValidator
    validate(Object target, Errors errors, Object... validationHints)
```

`org.springframework.validation.SmartValidator` kế thừa giao diện Spring Validator và cho phép truyền **validation hints**; với một `LocalValidatorFactoryBean` tích hợp Jakarta Bean Validation, những hint là `Class<?>` có thể đóng vai trò group.

Ví dụ tích hợp với Spring (không phải chương trình chạy độc lập):

```java
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.SmartValidator;

SmartValidator springValidator = /* bean do Spring cấu hình */;
ProductForm form = /* bean đã bind */;
var errors = new BeanPropertyBindingResult(form, "form");

// Hint Create.class chuyển thành nhóm validation qua adapter Jakarta.
springValidator.validate(form, errors, Create.class);

boolean hasErrors = errors.hasErrors();
```

Đây là đoạn minh họa API sử dụng trong class/method đã có biến thực. Nếu muốn dùng `Set<ConstraintViolation>` trực tiếp và chọn group một cách rõ ràng, inject `jakarta.validation.Validator`. Nếu đang xử lý binding và `BindingResult` trong MVC, Spring validator/adapter có ích vì nó ánh xạ lỗi về `FieldError`/`ObjectError`.

## 4. @Valid và @Validated: cùng kích hoạt validation nhưng khác khả năng chọn group

### 4.1. @Valid thuộc Jakarta

`@Valid` có import:

```java
import jakarta.validation.Valid;
```

Dùng trên tham số object của controller:

```java
@PostMapping("/products")
public ResponseEntity<?> create(@Valid @RequestBody ProductForm form) {
    return ResponseEntity.ok().build();
}
```

Khi được Spring MVC xử lý với Bean Validation provider thích hợp, `@Valid` trên một command object yêu cầu validation mặc định (`Default`). `@Valid` bản thân **không có `value()` để truyền `Create.class`**. Nó cũng được dùng trên property/type argument để **cascade** vào object con khi Bean Validation kiểm tra toàn bean.

### 4.2. @Validated thuộc Spring

`@Validated` có import:

```java
import org.springframework.validation.annotation.Validated;
```

Để chọn group `Create` cho một DTO trong Spring MVC:

```java
@PostMapping("/products")
public ResponseEntity<?> create(
        @Validated(Create.class) @RequestBody ProductForm form) {
    return ResponseEntity.ok().build();
}
```

`@Validated(Create.class)` yêu cầu các constraint thuộc `Create` theo cơ chế argument validation phù hợp của MVC. Khác biệt quan trọng: nó **không mặc nhiên thêm `Default`** vào nhóm Create. Muốn cả hai, có thể viết:

```java
@Validated({Default.class, Create.class})
@RequestBody ProductForm form
```

Đó là khai báo hợp lệ ở vị trí **tham số method**; ví dụ này chỉ là hai dòng trong chữ ký, không phải mã standalone.

### 4.3. Bảng so sánh

| Vấn đề | `@Valid` | `@Validated` |
| --- | --- | --- |
| Package | `jakarta.validation.Valid` | `org.springframework.validation.annotation.Validated` |
| Chỉ định group bằng thuộc tính | Không | Có: `value = {Group.class,...}` |
| Dùng trên tham số command object của Spring MVC | Có | Có |
| Thường dùng nhóm | `Default` khi gọi mặc định, hoặc nhóm hiện hành khi cascade | Nhóm được khai báo, nếu bỏ trống thì ngữ cảnh mặc định |
| Cascade trên property/type argument | Có, chuyên dùng cho cascade | Không thay thế `@Valid` trong object graph |
| Kích hoạt method validation qua AOP ở Spring service | Không phải điểm kích hoạt Spring AOP tương đương | Có thể là điểm kích hoạt trên class, nếu hạ tầng AOP/method validation được bật |
| Là một constraint như `@NotBlank` không? | Không | Không |

**Không ghi `@Validated` lên field con và tưởng nó sẽ tự cascade.** Khi muốn đi sâu vào nested bean, vẫn cần `@Valid`. Muốn đổi group khi cascade, dùng quy tắc group propagation hoặc `@ConvertGroup` (mục 8).

## 5. Ví dụ Java 17+ chạy độc lập: quan sát Default, Create và Update

Bài thực hành dưới đây sử dụng **Jakarta Bean Validation 3.x + Hibernate Validator 8.x**. Không cần khởi động Spring để hiểu cách truyền nhóm vào `Validator`; điều này giúp so sánh kết quả ổn định trước khi tích hợp với Spring MVC.

### 5.1. pom.xml

Tạo tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>groups-validated-demo</artifactId>
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

`hibernate-validator` là **provider** thực thi Jakarta Bean Validation và kéo theo các dependency cần thiết. Ví dụ CLI chọn `ParameterMessageInterpolator` của Hibernate Validator để không yêu cầu cấu hình Jakarta Expression Language (EL) riêng. Đây là chi tiết **provider-specific**; ứng dụng dùng message template có biểu thức EL phải bổ sung cấu hình tương thích.

### 5.2. GroupPassingDemo.java

Tạo một tệp cùng tên class `GroupPassingDemo.java` ở thư mục chứa `pom.xml`:

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;
import jakarta.validation.groups.Default;

import org.hibernate.validator.HibernateValidator;
import org.hibernate.validator.messageinterpolation.ParameterMessageInterpolator;

import java.util.List;
import java.util.Set;

public class GroupPassingDemo {

    public interface Create {}
    public interface Update {}

    public static final class ProductForm {
        @NotBlank
        private final String name;

        @Null(groups = Create.class)
        @NotNull(groups = Update.class)
        private final Long id;

        @Min(value = 1, groups = {Create.class, Update.class})
        private final int quantity;

        public ProductForm(String name, Long id, int quantity) {
            this.name = name;
            this.id = id;
            this.quantity = quantity;
        }

        public Long getId() {
            return id;
        }
    }

    private static void show(
            String label, Set<? extends ConstraintViolation<?>> violations) {
        List<String> paths = violations.stream()
                .map(v -> v.getPropertyPath().toString())
                .sorted()
                .toList();
        System.out.println(label + " -> " + paths);
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory = Validation
                .byProvider(HibernateValidator.class)
                .configure()
                .messageInterpolator(new ParameterMessageInterpolator())
                .buildValidatorFactory()) {

            Validator validator = factory.getValidator();

            ProductForm form = new ProductForm("", 7L, 0);

            show("Default", validator.validate(form));
            show("Create", validator.validate(form, Create.class));
            show("Update", validator.validate(form, Update.class));
            show("Default+Create",
                    validator.validate(form, Default.class, Create.class));
            show("property id / Create",
                    validator.validateProperty(form, "id", Create.class));
            show("candidate id=null / Update",
                    validator.validateValue(
                            ProductForm.class, "id", null, Update.class));
            show("candidate quantity=2 / Create",
                    validator.validateValue(
                            ProductForm.class, "quantity", 2, Create.class));

            ProductForm fresh = new ProductForm("Ready", null, 2);
            show("fresh / Create",
                    validator.validate(fresh, Create.class));
            show("fresh / Update",
                    validator.validate(fresh, Update.class));

            System.out.println("originalId=" + form.getId());
        }
    }
}
```

### 5.3. Biên dịch và chạy

Cần **JDK 17+** và **Maven**. Chạy trong thư mục có `pom.xml` và `GroupPassingDemo.java`.

Linux/macOS (Bash):

```bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
CP="$(cat classpath.txt)"
javac -encoding UTF-8 -cp "$CP" GroupPassingDemo.java
java -cp ".:$CP" GroupPassingDemo
```

Windows (PowerShell):

```powershell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
$cp = (Get-Content -Raw classpath.txt).Trim()
javac -encoding UTF-8 -cp $cp GroupPassingDemo.java
java -cp ".;$cp" GroupPassingDemo
```

**Stdout kỳ vọng** (không tính log/cảnh báo của Maven hoặc provider):

```text
Default -> [name]
Create -> [id, quantity]
Update -> [quantity]
Default+Create -> [id, name, quantity]
property id / Create -> [id]
candidate id=null / Update -> [id]
candidate quantity=2 / Create -> []
fresh / Create -> []
fresh / Update -> [id]
originalId=7
```

Phân tích kỹ từng dòng:

1. `Default -> [name]`: `@NotBlank name` nằm trong `Default`; `name=""` làm nó vi phạm. Hai constraint ID và `@Min` không thuộc `Default` nên không chạy.
2. `Create -> [id, quantity]`: `id=7L` vi phạm `@Null(groups=Create.class)`; `quantity=0` vi phạm `@Min(1,groups=Create.class)`. `name` rỗng **không bị phát hiện trong call này** vì constraint `@NotBlank` chỉ thuộc Default.
3. `Update -> [quantity]`: ID đã khác null nên `@NotNull(groups=Update.class)` đạt; quantity vẫn vi phạm.
4. `Default+Create -> [id, name, quantity]`: cả hai nhóm được yêu cầu, nên ba rule được áp dụng.
5. `property id / Create -> [id]`: chỉ property ID theo nhóm Create, không kiểm tra tên hoặc số lượng.
6. `candidate id=null / Update -> [id]`: `validateValue` xét một giá trị giả định; `@NotNull` của Update thất bại.
7. `candidate quantity=2 / Create -> []`: số 2 thỏa min 1.
8. `fresh / Create -> []`: `id=null` và `quantity=2` thỏa nhóm Create. Dù form mới có tên hợp lệ, điều đó không khiến Default tự chạy.
9. `fresh / Update -> [id]`: ID null vi phạm yêu cầu Update.
10. `originalId=7`: mọi lệnh validate chỉ kiểm tra, không tự sửa đối tượng.

Hàm `show` sắp xếp `getPropertyPath()` để không phụ thuộc thứ tự lặp của `Set<ConstraintViolation<?>>`. Nếu nhiều constraint cùng vi phạm trên một property, path có thể lặp; số phần tử của tập violation không luôn bằng số field lỗi.

**Lưu ý phạm vi:** mã này **chạy độc lập** với provider Hibernate Validator 8. Những đoạn Spring ở phần tiếp theo là **mã tích hợp**, cần được đặt trong dự án Spring Boot/Spring MVC với các dependency, import và cấu hình thích hợp; chúng không thuộc tệp `GroupPassingDemo.java`.

## 6. Truyền group trong Spring MVC bằng @Validated trên tham số

Khi dữ liệu từ HTTP JSON hoặc form được bind thành DTO, có thể chọn nhóm trong controller.

### 6.1. DTO minh họa cho create/update

Trong dự án Spring Boot 3.x (Jakarta namespace):

```java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;

public class ProductRequest {
    public interface Create {}
    public interface Update {}

    @NotBlank(groups = {Create.class, Update.class})
    private String name;

    @Null(groups = Create.class)
    @NotNull(groups = Update.class)
    private Long id;

    @Min(value = 1, groups = {Create.class, Update.class})
    private int quantity;

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public int getQuantity() { return quantity; }
    public void setQuantity(int quantity) { this.quantity = quantity; }
}
```

Trong ví dụ này, `@NotBlank` khai báo cả hai nhóm để bảo đảm tên được kiểm tra ở cả create và update; vì vậy không còn bẫy Default ở mục 5. Sử dụng nhóm lồng trong DTO chỉ để ví dụ ngắn; dự án thật có thể đặt marker interfaces ở package riêng để dùng thống nhất ở controller/service.

### 6.2. Controller chọn nhóm tương ứng

```java
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/products")
public class ProductController {

    @PostMapping
    public ResponseEntity<?> create(
            @Validated(ProductRequest.Create.class)
            @RequestBody ProductRequest input,
            BindingResult errors) {
        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(errors.getFieldErrors().stream()
                            .map(e -> e.getField() + ":" + e.getCode())
                            .toList());
        }
        // Service áp dụng phân quyền, kiểm tra nghiệp vụ và tạo ID.
        return ResponseEntity.ok("Accepted create");
    }

    @PutMapping("/{id}")
    public ResponseEntity<?> update(
            @PathVariable Long id,
            @Validated(ProductRequest.Update.class)
            @RequestBody ProductRequest input,
            BindingResult errors) {
        if (errors.hasErrors() || !id.equals(input.getId())) {
            return ResponseEntity.badRequest().body("Invalid update");
        }
        // Service xác nhận quyền sửa, trạng thái và dữ liệu persistence.
        return ResponseEntity.ok("Accepted update");
    }
}
```

Ở chữ ký trên:

- `@Validated(ProductRequest.Create.class)` truyền **một group** cho validation của DTO khi POST.
- `@Validated(ProductRequest.Update.class)` truyền group khác khi PUT.
- `BindingResult` đứng ngay sau tham số DTO tương ứng để Spring MVC có chỗ đưa lỗi khi validation tham số hoạt động theo đường này.
- `@RequestBody` phụ trách deserialize JSON trước khi constraint validation; JSON sai cú pháp/không tạo được object có thể phát sinh exception khác trước lúc vào controller.
- So sánh path ID và body ID chỉ minh họa một rule nhất quán; production cần xử lý body null, quyền truy cập, không tồn tại và xung đột trạng thái.

Nếu chỉ dùng `@Valid` trên `ProductRequest` mà tất cả constraint đều khai báo nhóm Create/Update, **Default không có những constraint đó**; POST/PUT có thể bỏ qua rule quan trọng. Chọn `@Validated` đúng nhóm mới phản ánh hợp đồng của từng thao tác.

### 6.3. Hai con đường validation trong Spring MVC

Spring MVC hiện đại hỗ trợ:

1. **Validation từng command object**: `@ModelAttribute`, `@RequestBody` hoặc `@RequestPart` với `@Valid`/`@Validated` trong điều kiện phù hợp; lỗi có thể đi qua `BindingResult` nếu handler khai báo đúng, hoặc thành `MethodArgumentNotValidException`.
2. **Method validation**: khi constraint được khai báo trực tiếp trên tham số method hoặc return value, hoặc chữ ký khác buộc method validation; có thể phát sinh `HandlerMethodValidationException`. Method validation có thể bao gồm constraint của các object lồng nhau thông qua `@Valid`.

Không nên khẳng định tất cả trường hợp đều chỉ gây một loại exception. Việc xử lý lỗi phụ thuộc chữ ký handler, Spring version, có `BindingResult` sát tham số lỗi hay không, và việc có method parameter constraint hay không.

**Điểm riêng từ Spring Framework 6.1+:** Spring MVC có cơ chế **built-in method validation** cho controller. Nếu controller đặt `@Validated` ở **mức class**, việc method validation có thể đi qua AOP proxy thay vì đường built-in. Hướng dẫn Spring khuyến nghị **bỏ `@Validated` ở mức class của controller** khi muốn tận dụng built-in method validation, nhưng vẫn có thể dùng `@Validated(Group.class)` **trên tham số command object** để chọn nhóm. Hai vị trí này có vai trò khác nhau, không nên đánh đồng.

## 7. Group inheritance và @GroupSequence khi cần nhiều nhóm

### 7.1. Nhiều groups không có thứ tự mặc định

```java
validator.validate(form, Default.class, Create.class);
```

Câu lệnh yêu cầu kiểm tra các constraint thuộc cả `Default` và `Create`. Nó **không** có nghĩa “Default chạy trước; nếu lỗi thì dừng”. Thứ tự đánh giá các group trong một lời gọi không dùng sequence **không được bảo đảm**.

Nếu application cần chạy nhóm rẻ trước, nhóm nặng sau, sử dụng `@GroupSequence`:

```java
import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

interface ExpensiveChecks {}

@GroupSequence({Default.class, ExpensiveChecks.class})
interface FullChecks {}
```

Đây là các interface minh họa. Khi `validator.validate(form, FullChecks.class)`:

1. `Default` được đánh giá trước;
2. Nếu Default có violation, nhóm sau **không được kiểm tra**;
3. Chỉ khi Default đạt mới đánh giá `ExpensiveChecks`.

Các constraint liên quan đến `ExpensiveChecks` phải được khai báo `groups=ExpensiveChecks.class`. Không trộn nhóm có thứ tự với lời gọi `validate(form, Default.class, ExpensiveChecks.class)` rồi kỳ vọng hành vi ngắt sớm. Với **định nghĩa lại Default group sequence trên một class**, có quy tắc khai báo riêng (phải đưa chính class đó vào sequence); đừng thay thế máy móc `Default.class` trong annotation class-level.

**Một số provider có cấu hình fail-fast** nhưng đó không phải cách thay thế portable cho `@GroupSequence`. Fail-fast có ngữ nghĩa và thứ tự chọn violation riêng; không dùng nó để chứng minh thứ tự nghiệp vụ.

### 7.2. Kế thừa nhóm

Có thể cho nhóm con kế thừa marker interface khác:

```java
interface BaseChecks {}
interface StrictChecks extends BaseChecks {}
```

Khi yêu cầu `StrictChecks`, các constraint khai báo thuộc `BaseChecks` cũng nằm trong phạm vi kiểm tra theo quy tắc kế thừa group. Tuy nhiên, **không có thứ tự** giữa các constraint chỉ vì interface kế thừa. Cần sequence riêng khi thứ tự và điều kiện dừng là yêu cầu bắt buộc.

Mô hình group quá phức tạp làm API khó bảo trì. Với Create/Update có cấu trúc field khác biệt đáng kể, cân nhắc DTO riêng thay vì chồng nhiều interface/sequence.

## 8. Cascade @Valid và @ConvertGroup: nhóm được truyền đi đâu?

Giả sử `OrderRequest` chứa `Customer`. Validator sẽ không tự kiểm tra constraint bên trong `Customer` chỉ vì field khác null; cần `@Valid` để bật cascade trên trường liên quan.

```java
class Customer {
    @NotBlank(groups = Create.class)
    String displayName;
}

class OrderRequest {
    @Valid
    Customer customer;
}
```

Khi gọi `validator.validate(order, Create.class)`, nhóm `Create` sẽ được **truyền theo tuyến cascade** cho `Customer` theo quy tắc của Jakarta Bean Validation; do đó `displayName` được kiểm tra khi khách hàng tồn tại. `@Valid` không tự cấm `customer == null`; nếu bắt buộc tồn tại, thêm `@NotNull` ở mức property theo nhóm mong muốn.

Đôi lúc root bean ở nhóm `Default` nhưng bean con cần kiểm tra nhóm `Create`. `@ConvertGroup` có thể thay nhóm khi cascade:

```java
import jakarta.validation.Valid;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.groups.Default;

class OrderRequest {
    @Valid
    @ConvertGroup(from = Default.class, to = Create.class)
    Customer customer;
}
```

Đây là ví dụ mô tả tuyến cascade, cần định nghĩa `Customer` và `Create` ở project. Khi validate `OrderRequest` với `Default`, nhóm `Default` được chuyển thành `Create` khi đi vào `customer`. `@ConvertGroup` **không chạy** nếu không có điểm cascade hợp lệ qua `@Valid` và không tự làm thay đổi những constraint ở container/root bean. Với `validateProperty`/`validateValue`, không có cascaded validation, nên không thể suy ra hiệu ứng group conversion trên toàn object graph.

### 8.1. Container và phần tử

Một số constraint gắn vào container, một số gắn vào phần tử:

```java
@NotEmpty(groups = Create.class)
List<@NotBlank(groups = Create.class) String> codes;
```

Khi validator chạy nhóm `Create`, nó kiểm tra cả container không rỗng và từng mã không blank. Nếu chỉ chạy `Default` và không có cấu hình khác, hai constraint Create này không được yêu cầu. Không cần `@Valid` chỉ để áp dụng `@NotBlank` lên phần tử `String`: đó là container-element constraint, không phải cascade tới bean con.

## 9. @Validated tại service: cơ chế method validation khác với validate DTO thủ công

Ngoài controller, `@Validated` còn đóng vai trò điểm kích hoạt **Spring method validation**. Ví dụ service với tham số được ràng buộc bằng annotation:

```java
import jakarta.validation.constraints.NotBlank;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class CodeService {
    public void reserve(@NotBlank String code) {
        // Service logic...
    }
}
```

Khi hạ tầng method validation được cấu hình (ví dụ `MethodValidationPostProcessor`/auto-configuration phù hợp), một lời gọi `reserve("")` đi **qua Spring proxy** sẽ được kiểm tra và có thể bị chặn trước khi chạy body. `@Validated` đặt trên class đóng vai trò điểm kích hoạt AOP; **không phải cứ có annotation mà mọi lời gọi Java nội bộ đều được kiểm tra**.

### 9.1. Chọn nhóm cho method validation ở service

Ví dụ service dành riêng cho thao tác Create:

```java
@Service
@Validated(Create.class)
public class CreateCodeService {
    public void reserve(
            @NotBlank(groups = Create.class) String code) {
        // Nếu proxy method validation hoạt động, code blank sẽ vi phạm.
    }
}
```

`@Validated(Create.class)` tại class thể hiện nhóm dùng cho method validation theo cơ chế Spring AOP tương ứng. Nếu method có annotation `@Validated` để ghi đè nhóm, cần kiểm tra phiên bản/cấu hình method validation và quy tắc phương thức; không suy diễn hoạt động từ vị trí annotation mà Spring không xử lý trong stack cụ thể.

Điều kiện thực tế:

- Có Bean Validation provider tương thích trên classpath.
- Hạ tầng method validation của Spring được bật (có thể do Boot tự cấu hình).
- Service là bean do Spring quản lý và lời gọi đi **qua proxy/interceptor** phù hợp.
- Phương thức cần được proxy intercept (ví dụ public method); self-invocation như `this.reserve("")` trong cùng instance có thể **bỏ qua proxy**.
- Constraint phải thuộc đúng group được yêu cầu.

Không dùng method validation proxy để thay kiểm tra quyền, integrity của transaction, trạng thái database hoặc chính sách nghiệp vụ.

### 9.2. Phân biệt ba vị trí @Validated

| Vị trí | Mục đích chính |
| --- | --- |
| `@Validated(Create.class)` trên DTO parameter trong Spring MVC | Chọn nhóm khi validate command object đang bind |
| `@Validated` trên Spring service class | Đánh dấu kiểu cho proxy-based method validation khi hạ tầng phù hợp |
| `@Validated` ở mức Spring MVC controller class | Có thể kích hoạt method validation qua AOP; với Spring MVC 6.1+ không nên dùng nếu muốn cơ chế built-in method validation |
| `@Valid` trên property hoặc type argument trong DTO | Bật cascade vào bean con, không chọn group |

**Đừng áp dụng một cách máy móc** `@Validated(Create.class)` ở lớp controller với ý nghĩ mọi `@RequestBody`/`@ModelAttribute` ở tất cả handler tự được validate Create theo cùng đường chuẩn. Vị trí đặt trên tham số tương ứng là cách rõ ràng hơn khi cần điều khiển nhóm validation của payload.

## 10. Phân biệt validation lỗi với binding/serialization lỗi

Trong Spring MVC, luồng xử lý thường gồm:

1. **Deserialize/bind:** JSON, form hoặc query parameter được chuyển thành đối tượng Java.
2. **Validate:** Bean Validation kiểm tra các constraint thuộc nhóm đã chọn, kể cả nhóm truyền từ `@Validated` hoặc controller adapter.
3. **Xử lý nghiệp vụ:** service kiểm tra điều kiện không thể biểu đạt chỉ bằng annotation, quyền truy cập, database uniqueness.
4. **Trả lỗi phù hợp:** controller/exception handler chuyển lỗi thành contract HTTP, không để thông tin nhạy cảm lộ ra.

Ví dụ nếu JSON gửi `{"quantity":"abc"}` mà DTO định nghĩa `int quantity`, Jackson/binder có thể báo lỗi chuyển kiểu **trước khi `@Min` có cơ hội chạy**. Validation group không tự biến dữ liệu sai kiểu thành Java value phù hợp.

Ngược lại, JSON gửi `{"quantity":0}` cho DTO Create sẽ tạo `int` và có thể vi phạm `@Min(1)` thuộc Create. Khi dùng DTO với `int`, thiếu field có thể dẫn đến giá trị mặc định 0 hoặc bị cơ chế deserialization riêng chặn; nếu cần phân biệt “không nhập” với 0, dùng `Integer` và `@NotNull` trong group thích hợp.

### 10.1. BindingResult và mã lỗi

Trong handler dùng `@Validated(Create.class) @RequestBody ProductRequest input, BindingResult errors`, `errors` gắn với tham số đầu vào ngay trước nó. Có thể duyệt `errors.getFieldErrors()` để lấy field/code, và `errors.getGlobalErrors()` để lấy rule cấp đối tượng. Nếu chữ ký method thay đổi theo hướng cần method validation trực tiếp, cách nhận lỗi cũng có thể thay đổi.

Tránh trả `ConstraintViolation.getInvalidValue()`, mật khẩu, token hay dữ liệu riêng tư trực tiếp cho client. Nên dùng thông báo địa phương hóa và mã lỗi ổn định theo API contract. Đừng dùng `getMessage()` đã dịch làm định danh logic lâu dài.

### 10.2. @Valid không đồng nghĩa method validation

`@Valid` là tín hiệu cascade hoặc validation một object đầu vào trong ngữ cảnh Spring MVC, không phải một annotation constraint như `@NotNull`. Riêng `@Valid` trên method parameter không tự tạo executable method validation; khi có constraint trực tiếp như `@NotNull` hay `@Min` trên tham số, method validation có thể được yêu cầu. Trong Spring Framework 6.1+, đường xử lý có thể là built-in method validation của MVC, khác AOP `@Validated` trên service/controller class.

## 11. Bảng chọn API theo tình huống

| Tình huống | Cách chọn nhóm | Vì sao |
| --- | --- | --- |
| Service cần kiểm tra toàn DTO theo Create | `jakartaValidator.validate(dto, Create.class)` | Rõ ràng, trả `ConstraintViolation` |
| Kiểm tra field hiện có theo Update | `validateProperty(dto, "id", Update.class)` | Chỉ một property, không cascade |
| Kiểm tra ID dự kiến trước khi gán | `validateValue(Dto.class, "id", candidate, Update.class)` | Không cần instance, không mutate |
| MVC POST body cần nhóm Create | `@Validated(Create.class) @RequestBody Dto dto` | Spring chọn nhóm khi validate argument |
| MVC PUT body cần nhóm Update | `@Validated(Update.class) @RequestBody Dto dto` | Cùng kiểu DTO, tập rule khác |
| MVC muốn cả Default và Create | `@Validated({Default.class, Create.class})` | Yêu cầu hai group tường minh |
| Service cần kiểm tra tham số method | `@Validated` trên bean + constraint ở method parameter | Proxy-based method validation khi được cấu hình |
| Constraint trên bean con | `@Valid` ở field/type argument | Cho phép cascade xuống object graph |
| Bean con cần nhóm khác với cha | `@Valid` + `@ConvertGroup` | Chuyển nhóm tại điểm cascade |
| Muốn nhóm B chỉ chạy nếu nhóm A đạt | `@GroupSequence` | Có thứ tự và điều kiện dừng |
| Chỉ kiểm tra ràng buộc trên field độc lập | `validateValue`/`validateProperty` | Tiện cho UI, nhưng không kết luận toàn bean |

## 12. Lỗi phổ biến và hướng sửa

| Hiện tượng | Nguyên nhân | Giải pháp |
| --- | --- | --- |
| `@Validated(Create.class)` bỏ qua `@NotBlank` không có groups | `@NotBlank` thuộc Default, Create không bao gồm mặc định | Khai báo nhóm hoặc truyền cả Default |
| `@Valid` không kiểm tra ràng buộc trong Create | `@Valid` không chọn group, thường dùng Default | Dùng `@Validated(Create.class)` ở tham số phù hợp |
| Truyền `Create.class,Update.class` rồi có lỗi ID bất kể giá trị | Hai nhóm chứa `@Null`/`@NotNull` trái ngược | Chọn ngữ cảnh duy nhất hoặc thiết kế constraint khác |
| Gọi `validate(form, Default.class, Create.class)` mà tưởng có thứ tự | Varargs nhóm không xác định thứ tự thực thi | Dùng `@GroupSequence` |
| Validation trả rỗng nhưng object có field sai | Chỉ có field/group đã chọn được kiểm tra | Xác minh groups và phạm vi, validate toàn object cuối |
| `validateValue` không bắt rule giữa hai field | Không có bean đầy đủ, không xét class-level | Dùng `validate(dto, ...)` |
| `validateProperty` không báo lỗi nested | Không cascade qua `@Valid` | Validate root bean hoặc bean con |
| Import `org.springframework.validation.Validator` mà gọi `validate(dto,Create.class)` | API Spring Validator khác Jakarta Validator | Import `jakarta.validation.Validator` |
| Dùng `@Validated` trên nested field mong cascade | `@Validated` không thay thế `@Valid` trong graph | Dùng `@Valid` và `@ConvertGroup` khi cần |
| Service `@Validated` nhưng gọi method nội bộ không được chặn | Self-invocation bỏ qua AOP proxy | Gọi qua bean/proxy hoặc refactor boundary |
| Thêm `@Validated` trên controller class và gặp xử lý lỗi khác | Có thể chuyển sang AOP method validation thay vì MVC built-in | Chọn đúng vị trí annotation, đặc biệt Spring 6.1+ |
| Không có lỗi nào dù DTO có annotation | Thiếu provider hoặc validation không được kích hoạt | Cấu hình `LocalValidatorFactoryBean`/starter phù hợp |
| JSON sai kiểu bị coi là group không chạy | Lỗi xảy ra trước Bean Validation | Xử lý deserialization/binding riêng |
| Constraint group trên root đúng nhưng bean con không được kiểm tra | Thiếu cascade `@Valid` hoặc group conversion không đúng | Cấu hình tuyến cascade và kiểm thử |
| Chọn Create cho PATCH nhưng muốn giữ field không gửi | Không có phân biệt hiện diện/giá trị null | Mô hình PATCH riêng, không dùng nhóm thay deserialization policy |
| Tin rằng group validation bảo đảm quyền ghi field | Groups là rule tính hợp lệ, không phải phân quyền | Kiểm tra authorization và mass-assignment ở service/binder |

### 12.1. Kiểm thử tối thiểu

1. `validate(dto)` không truyền nhóm và `validate(dto, Default.class)` cho kết quả tương đương khi metadata không có sequence/redefinition đặc biệt.
2. Create/Update khác nhau tại ID null/non-null, và rule chung được kiểm tra đúng ở từng nhóm.
3. `@Validated(Create.class)` trên `@RequestBody` thực sự chạy Create trong một request MVC hợp lệ.
4. HTTP body malformed bị phân biệt với constraint violation; assert trạng thái và error contract.
5. `BindingResult` ngay sau model parameter thu được lỗi ở các đường validation hỗ trợ.
6. Service method validation được kích hoạt qua proxy, self-invocation không bị dùng làm bằng chứng.
7. Group inheritance/sequence được kiểm tra bằng test chứng minh điều kiện dừng, không dựa vào thứ tự `Set`.
8. Constraint trên bean con chạy khi có `@Valid` và nhóm được truyền/chuyển đúng.
9. Giới hạn dữ liệu: nested list, DTO rất lớn, input không tin cậy và truy cập database.
10. Khi nâng cấp Spring/Validation provider, chạy integration test về exception type và nhóm, đặc biệt ở controller method validation.

## 13. Quy tắc ghi nhớ

- **Group được gán cho constraint tại `groups={...}`; group được chọn lúc thực thi bằng đối số `Validator` hoặc `@Validated`.**
- **Không truyền group ⇒ `Default`. Truyền Create ⇒ chỉ các rule thuộc Create và rule mở rộng theo metadata group, không tự thêm Default.**
- **`@Valid` không có thuộc tính truyền group; `@Validated` có.** `@Valid` vẫn cần khi muốn cascade vào object con.
- **`jakarta.validation.Validator` và `org.springframework.validation.Validator` khác API.** Cái đầu trả violation set và nhận group varargs; cái sau thao tác với `Errors`. `SmartValidator` là adapter thích hợp cho hints.
- **Spring MVC argument validation và Spring AOP method validation là hai cơ chế khác nhau.** Đặt `@Validated` đúng vị trí.
- **Nhiều nhóm không mặc định có thứ tự hoặc fail-fast;** dùng `@GroupSequence` khi nghiệp vụ yêu cầu.
- **Không lấy group làm cơ chế phân quyền hoặc thay thế DTO theo thao tác** nếu Create/Update khác nhau lớn về field được phép nhận.
- Sau bước kiểm tra sớm bằng `validateProperty`/`validateValue`, vẫn kiểm tra **trạng thái cuối của toàn bean** khi quyết định lưu/gửi dữ liệu quan trọng.

### Tài liệu đối chiếu

- Jakarta Validation 3.0 — `Validator`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Validator.html
- Jakarta Bean Validation specification — groups, group inheritance, group sequence: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Validation — `Default`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/groups/default
- Spring Framework — Java Bean Validation và `LocalValidatorFactoryBean`: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework — Spring MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — MVC validation configuration: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html
- Spring Framework — `@Validated` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/annotation/Validated.html
