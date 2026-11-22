# Định nghĩa lại `Default` group cho một lớp trong Jakarta Bean Validation

## 1. Tại sao cần thay đổi nhóm `Default`?

Trong ứng dụng Java/Spring, một bean thường có nhiều loại quy tắc:

- **Cơ bản:** tên không rỗng, số lượng phải dương, trường bắt buộc phải có.
- **Nhất quán:** các trường phải tương thích với nhau hoặc một trạng thái nội bộ phải được xác nhận.
- **Phê duyệt:** chỉ được chấp nhận khi điều kiện cuối cùng đã đạt.

Nếu chạy mọi constraint cùng lúc, người dùng có thể nhận lỗi của bước phê duyệt ngay cả khi mã hoặc số lượng đầu vào chưa hợp lệ. Jakarta Bean Validation cho phép sắp xếp các **validation groups** và dừng trước nhóm sau khi nhóm trước thất bại.

Có hai cách dùng `@GroupSequence`:

1. Đặt trên **interface** tạo một nhóm gồm nhiều nhóm con theo thứ tự; caller yêu cầu tường minh bằng `validator.validate(bean, MySequence.class)`.
2. Đặt trên **class được kiểm tra** để **định nghĩa lại `Default` group chỉ cho class đó**. Khi caller gọi `validator.validate(bean)` như thường lệ, sequence mới tự được áp dụng.

Bài này tập trung vào cách thứ hai: **class-level default group sequence redefinition**.

Ví dụ nhu cầu: khi kiểm tra hóa đơn (`Invoice`), hệ thống luôn muốn chạy *Basic → Consistency → Approval*, kể cả khi caller chỉ yêu cầu nhóm mặc định. Bạn không muốn mọi service/controller phải nhớ tên `CompleteInvoiceChecks`.

**Mục tiêu học tập:** biết khai báo `@GroupSequence` trên class; hiểu lý do bắt buộc chứa **chính class**, không phải `Default.class`; nắm quy tắc dừng theo nhóm; hiểu phạm vi cục bộ và hành vi `@Valid` cascade; kiểm tra Java 17 và tích hợp Spring MVC.

## 2. Ôn tập nhóm `Default` và nhóm đặt tên

### 2.1. `Default` là gì?

`jakarta.validation.groups.Default` là marker interface của nhóm mặc định. Một constraint không ghi `groups` sẽ thuộc `Default`:

```java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

@NotBlank
private String code;

@Min(1)
private int quantity;
```

Đây là hai khai báo field minh họa, chưa phải class tự chạy. Theo mặc định:

```java
validator.validate(invoice);
validator.validate(invoice, jakarta.validation.groups.Default.class);
```

hai lệnh đều yêu cầu nhóm `Default`. Nếu class `Invoice` có định nghĩa lại `Default`, **cả hai cách gọi** đều chịu hiệu lực của sequence đã khai báo.

### 2.2. Nhóm riêng

Nhóm thường là các interface marker:

```java
interface ConsistencyChecks {}
interface ApprovalChecks {}
```

Constraint gắn vào nhóm riêng:

```java
import jakarta.validation.constraints.AssertTrue;

@AssertTrue(groups = ConsistencyChecks.class)
private boolean consistent;
```

Khi class chưa định nghĩa lại `Default`, gọi `validate(bean)` thường **không** chạy constraint thuộc riêng `ConsistencyChecks`.

### 2.3. Truyền nhiều groups không tự tạo thứ tự

```java
validator.validate(invoice,
        ConsistencyChecks.class,
        ApprovalChecks.class);
```

Điều này yêu cầu hai nhóm nhưng **không bảo đảm** nhóm `ConsistencyChecks` sẽ chạy xong trước `ApprovalChecks` chỉ vì xuất hiện trước trong danh sách tham số. Nếu thứ tự là quy tắc nghiệp vụ thì cần `@GroupSequence`.

| Cơ chế | Thứ tự kiểm tra | Dừng trước nhóm sau? |
| --- | --- | --- |
| `validate(bean)` không có sequence | Chỉ nhóm `Default` | Không có tầng kế tiếp |
| `validate(bean, A.class, B.class)` | Không cam kết thứ tự chỉ từ danh sách tham số | Không do thứ tự tham số |
| `@GroupSequence({A.class, B.class})` trên interface và yêu cầu interface đó | Có: A rồi B | Có, nếu A có violation |
| `@GroupSequence({Bean.class, A.class})` trên class và yêu cầu `Default` | Có: nhóm class rồi A | Có, nếu nhóm class có violation |

**Lưu ý:** không có thứ tự cam kết **giữa các constraint bên trong cùng một group**. Chỉ thứ tự giữa các tầng do sequence tạo mới được đảm bảo.

## 3. Khai báo `@GroupSequence` trên class

### 3.1. Cú pháp chuẩn

```java
import jakarta.validation.GroupSequence;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

interface ConsistencyChecks {}
interface ApprovalChecks {}

@GroupSequence({
    Invoice.class,
    ConsistencyChecks.class,
    ApprovalChecks.class
})
class Invoice {

    @NotBlank
    String code;

    @Min(1)
    int quantity;

    @AssertTrue(groups = ConsistencyChecks.class)
    boolean consistent;

    @AssertTrue(groups = ApprovalChecks.class)
    boolean reviewed;
}
```

Đây là một lớp minh họa, chưa có constructor và cơ chế chạy. Ví dụ Java 17 chạy độc lập được cung cấp ở mục 6.

`@GroupSequence` trên chính class `Invoice` có ý nghĩa: **khi kiểm tra nhóm `Default` đối với Invoice, thay nhóm Default đó bằng chuỗi nhóm được khai báo**.

```text
validator.validate(invoice)
            |
            v
    Yêu cầu nhóm Default
            |
            v
@GroupSequence trên Invoice
            |
            v
[1] Invoice.class
    @NotBlank code
    @Min quantity
            |
        Có lỗi?
        /    \
      Có     Không
      |        |
   Dừng        v
       [2] ConsistencyChecks
           @AssertTrue consistent
                   |
               Có lỗi?
               /    \
             Có     Không
             |        |
           Dừng       v
              [3] ApprovalChecks
                  @AssertTrue reviewed
                      |
                      v
                   Hoàn tất
```

Mục tiêu không phải “chạy mọi constraint tối đa một lần” mà là **tăng dần độ sâu kiểm tra khi trạng thái nền tảng đã hợp lệ**.

### 3.2. Vì sao phải đặt `Invoice.class` vào sequence?

Đặc tả Jakarta Validation có quy tắc *implicit grouping*: constraints thuộc `Default` và được khai báo trên class `A` cũng **ngầm thuộc nhóm `A`**.

Bởi vậy trong ví dụ trên, `Invoice.class` đại diện cho các ràng buộc Default được khai báo trên lớp: `@NotBlank code` và `@Min quantity`. Đây là cách bảo toàn các constraint cơ bản khi định nghĩa lại Default.

Nếu redefinition nằm trên một class `A`, sequence **bắt buộc chứa `A.class`**. Nếu không, provider có thể ném `jakarta.validation.GroupDefinitionException` khi validate hoặc lấy metadata. Điều kiện này áp dụng cả khi class không có nhiều constraint.

**ĐÚNG:**

```java
@GroupSequence({Invoice.class, ConsistencyChecks.class})
class Invoice {
    // Những khai báo constraint/field của Invoice
}
```

**SAI — thiếu chính class:**

```java
@GroupSequence({ConsistencyChecks.class, ApprovalChecks.class})
class Invoice {
    // Sequence không có Invoice.class
}
```

### 3.3. Không đưa `Default.class` vào class-level sequence

Một lỗi khá phổ biến:

```java
import jakarta.validation.groups.Default;

@GroupSequence({Default.class, ConsistencyChecks.class})
class Invoice {
    // Không hợp lệ khi đặt sequence lên chính Invoice
}
```

Bạn đang **định nghĩa lại Default** nhưng lại tự đưa `Default` vào định nghĩa thay thế, dẫn đến phụ thuộc vòng. Đây không phải cách giữ lại các constraint mặc định. Hãy dùng `Invoice.class`, không dùng `Default.class`.

So sánh: `@GroupSequence({Default.class, OtherChecks.class})` có thể **hợp lệ khi đặt trên một interface sequence độc lập**, nhưng không được dùng để định nghĩa lại Default trên class theo cách đó. Phân biệt hai ngữ cảnh là điều quan trọng nhất của chủ đề này.

### 3.4. Điều gì xảy ra khi sequence lỗi?

Nếu tầng trước có **một hoặc nhiều violations**, các nhóm phía sau trong sequence **không được kiểm tra**. Tuy nhiên mọi constraint thuộc tầng đang chạy vẫn có thể sinh lỗi.

Ví dụ `code=""`, `quantity=0`, `consistent=false`, `reviewed=false`:

- Tầng `Invoice.class` có **hai** violations: `@NotBlank` và `@Min`.
- `ConsistencyChecks` và `ApprovalChecks` không được chạy.
- Không thể nói “sequence dừng ngay ở constraint đầu tiên” nếu chưa bật một chế độ riêng của provider.

Với `code="INV-1"`, `quantity=1`, `consistent=false`: tầng cơ bản đạt, consistency sai, nên approval bị bỏ qua.

## 4. Khác gì với `@GroupSequence` trên interface?

Một interface sequence tạo **một nhóm tổng hợp gọi khi cần**:

```java
import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

interface DetailedChecks {}

@GroupSequence({
    Default.class,
    DetailedChecks.class
})
interface FullValidation {}
```

Khi gọi:

```java
validator.validate(bean, FullValidation.class);
```

provider thực hiện Default rồi tới DetailedChecks nếu Default đạt. Nhưng nếu chỉ gọi `validator.validate(bean)` và class **không** có redefinition, interface `FullValidation` không tự được chọn.

Ở class-level redefinition:

```java
@GroupSequence({Invoice.class, ConsistencyChecks.class})
class Invoice {
    // Các field/constraint của lớp
}
```

thì chính lời gọi `validator.validate(invoice)` đã kích hoạt sequence.

| Khía cạnh | Interface-level | Class-level |
| --- | --- | --- |
| Đặt annotation trên | Interface | Bean class |
| Khi nào sequence chạy | Caller yêu cầu interface group | Khi `Default` được kiểm tra trên class |
| Có thể khai báo `Default.class` | Có, nếu không gây vòng group | Không dùng trong sequence thay thế Default của chính class |
| Phải chứa chính bean class | Không theo quy tắc class redefinition | Có |
| Mức độ ảnh hưởng | Theo use case gọi sequence | Mọi luồng yêu cầu Default đối với class |
| Phù hợp | Nhiều mức kiểm tra được chọn tại caller | Default của class luôn cần thứ tự riêng |

Khi ứng dụng dùng chung DTO ở nhiều use case, cần cân nhắc: định nghĩa lại Default làm thay đổi hành vi của **tất cả** caller kiểm tra Default trên class đó. Nếu có luồng chỉ muốn kiểm tra trường cơ bản, interface sequence và nhóm riêng có thể dễ quản lý hơn.

## 5. Sequence chạy theo nhóm, không phải theo lỗi

### 5.1. Một group có thể cho nhiều lỗi

Dù `Invoice.class` đứng đầu, nó vẫn chứa nhiều constraint. Với code trống và quantity bằng 0, bạn có thể nhận đồng thời hai violations trong tầng đầu. Chỉ **các tầng sau** bị bỏ qua.

Không được giả định thứ tự của `Set<ConstraintViolation<?>>` do Jakarta Validator trả về. Nếu đưa lỗi vào response hoặc unit test, hãy sắp xếp theo field/code/message khi cần kết quả ổn định.

### 5.2. Tránh side effect trong `ConstraintValidator`

Nhiều nhóm nghĩa là có thể có nhiều bước đánh giá, và provider được phép tối ưu cách thực thi. Một constraint có mặt trong nhiều nhóm của sequence không nên bị dùng như công cụ chạy side effect nhiều lần.

Hãy viết `ConstraintValidator` theo hướng không sửa dữ liệu, không gửi email và không tự động ghi DB. Validation có thể chạy nhiều lần từ controller, service hoặc batch job.

### 5.3. Không nhầm với Hibernate Validator fail-fast

Hibernate Validator có chế độ **fail-fast** riêng để dừng sau khi phát hiện một constraint violation, nhưng không cam kết lỗi nào trong cùng nhóm sẽ được phát hiện trước. `@GroupSequence` là cơ chế **chuẩn Jakarta** bảo đảm thứ tự nhóm, còn fail-fast là tính năng **theo provider**. Chúng giải quyết hai vấn đề khác nhau.

## 6. Java 17 chạy độc lập: ba tầng Default redefinition

Chương trình dùng Hibernate Validator 8 làm Jakarta provider, với bốn trường hợp đầu vào. Mỗi nhóm có thông điệp cố định để dễ quan sát. Những thông điệp được **sắp xếp** trước khi in nhằm tránh phụ thuộc thứ tự của `Set`.

### 6.1. Cấu trúc và dependency

```text
default-sequence-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/DefaultSequenceDemo.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'default-sequence-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.hibernate.validator:hibernate-validator:8.0.6.Final'
    implementation 'org.glassfish.expressly:expressly:5.0.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'DefaultSequenceDemo'
}
```

`hibernate-validator` là provider Jakarta Bean Validation 3.0; `expressly` cung cấp Jakarta EL implementation để phục vụ message interpolation. Với Spring Boot, nên dùng `spring-boot-starter-validation` và BOM của Boot để quản lý phiên bản thay vì tự phối các phiên bản.

### 6.2. `DefaultSequenceDemo.java`

```java
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.GroupSequence;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public class DefaultSequenceDemo {

    interface ConsistencyChecks {}
    interface ApprovalChecks {}

    @GroupSequence({
        Invoice.class,
        ConsistencyChecks.class,
        ApprovalChecks.class
    })
    public static final class Invoice {

        @NotBlank(message = "code.required")
        private final String code;

        @Min(value = 1, message = "quantity.min")
        private final int quantity;

        @AssertTrue(
            groups = ConsistencyChecks.class,
            message = "consistency.failed"
        )
        private final boolean consistent;

        @AssertTrue(
            groups = ApprovalChecks.class,
            message = "approval.failed"
        )
        private final boolean approved;

        public Invoice(
                String code, int quantity,
                boolean consistent, boolean approved) {
            this.code = code;
            this.quantity = quantity;
            this.consistent = consistent;
            this.approved = approved;
        }
    }

    private static String messages(
            Set<ConstraintViolation<Invoice>> violations) {
        if (violations.isEmpty()) {
            return "PASS";
        }

        return violations.stream()
                .map(ConstraintViolation::getMessage)
                .sorted()
                .collect(Collectors.joining(","));
    }

    private static void check(
            String label, Invoice bean, Validator validator) {
        Set<ConstraintViolation<Invoice>> violations =
                validator.validate(bean);

        System.out.println(label + ": " + messages(violations));
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            check("basic",
                    new Invoice("", 0, false, false),
                    validator);

            check("consistency",
                    new Invoice("INV-1", 1, false, false),
                    validator);

            check("approval",
                    new Invoice("INV-1", 1, true, false),
                    validator);

            check("valid",
                    new Invoice("INV-1", 1, true, true),
                    validator);
        }
    }
}
```

Lưu tệp theo đúng tên class, rồi chạy với JDK 17 và Gradle:

```bash
gradle run --quiet
```

Nếu dự án có Gradle Wrapper, trên Linux/macOS chạy `./gradlew run --quiet`; trên Windows chạy `gradlew.bat run --quiet`.

**Standard output mong đợi:**

```text
basic: code.required,quantity.min
consistency: consistency.failed
approval: approval.failed
valid: PASS
```

Diễn giải:

- **basic:** Hai default constraints `@NotBlank` và `@Min` cùng sai. Không có lỗi của consistency/approval vì sequence dừng sau nhóm `Invoice`.
- **consistency:** Mã và số lượng hợp lệ; `consistent=false` nên `ConsistencyChecks` có lỗi, bỏ qua `ApprovalChecks`.
- **approval:** Hai tầng đầu đạt; `approved=false` vi phạm nhóm cuối.
- **valid:** Toàn bộ các nhóm đạt; tập `ConstraintViolation<Invoice>` rỗng.

Ví dụ đánh annotation trên **field**, nên Hibernate Validator có thể kiểm tra field private trực tiếp. Các nhóm được khai báo dạng interface lồng bên trong class chứa chương trình; `Invoice` là nested static class. Mã không cần Spring context hay HTTP server.

### 6.3. Kiểm tra một nhóm riêng không đồng nghĩa kiểm tra Default sequence

Gọi:

```java
validator.validate(invoice, ConsistencyChecks.class);
```

chỉ yêu cầu `ConsistencyChecks`. Nó **không tự chèn** tầng Default phía trước. Nếu bạn muốn kiểm tra Default sequence của `Invoice`, hãy gọi `validator.validate(invoice)` hoặc yêu cầu `Default.class`.

Khi test nhóm cụ thể, hãy nêu rõ group truyền vào. Đừng đoán rằng mọi lệnh `validate` trên một class có redefinition đều chạy cùng một sequence.

## 7. Phạm vi **cục bộ**: không truyền toàn bộ sequence của cha sang child

Đây là điểm dễ nhầm khi Spring MVC validate form có nhiều bean lồng nhau.

```java
import jakarta.validation.GroupSequence;
import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;

interface ExtraChecks {}

@GroupSequence({Order.class, ExtraChecks.class})
class Order {

    @NotBlank
    String orderCode;

    @Valid
    Customer customer;

    @AssertTrue(groups = ExtraChecks.class)
    boolean ready;
}

class Customer {

    @NotBlank
    String displayName;
}
```

Đoạn code này minh họa model, chưa có constructor/các hàm bổ trợ.

Khi gọi `validator.validate(order)`:

1. Default của `Order` được thay bằng `Order.class`, rồi `ExtraChecks.class` nếu cần.
2. Cascade qua `@Valid` sang `Customer` **không truyền nguyên** sequence của Order (`Order.class`, `ExtraChecks.class`).
3. `Customer` nhận **Default group**, hoặc dùng default redefinition **của chính Customer** nếu Customer có một class-level `@GroupSequence` riêng.
4. Nếu `Order.orderCode` không hợp lệ, ExtraChecks của Order bị bỏ qua; điều này **không nhất thiết loại bỏ lỗi Default của Customer**, vì kiểm tra Default đã được chuyển qua quan hệ `@Valid`.

Đặc tả gọi đây là **default group sequence overriding is local to the class**. Hiểu quy tắc này giúp giải thích tại sao đôi khi bạn thấy lỗi ở child dù một nhóm nâng cao trên parent đã bị chặn.

### Nếu muốn đổi nhóm khi cascade: `@ConvertGroup`

Jakarta cung cấp group conversion cho một quan hệ có `@Valid`:

```java
import jakarta.validation.Valid;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.groups.Default;

class Checkout {

    @Valid
    @ConvertGroup(
        from = Default.class,
        to = ShippingChecks.class
    )
    Address shippingAddress;
}
```

Đây là snippet minh họa; `Address` và interface `ShippingChecks` phải được định nghĩa thêm. Khi một lời gọi cascade truyền `Default` qua quan hệ này, group được đổi thành `ShippingChecks`.

Cần nhớ:

- `@ConvertGroup` chỉ hợp lệ ở vị trí **có cascade `@Valid`**.
- Group conversion thay đổi group truyền sang child, không thay thế Default ở root.
- Không áp dụng conversion theo chuỗi nhiều lần tại cùng một cạnh.
- Không có hai conversion cùng giá trị `from` trên một điểm cascade.
- `from` không được chỉ tới một group sequence; group sequence được mở rộng trước khi kiểm tra quy tắc conversion.
- Child chỉ cần nhận Default của nó và có class redefinition riêng thì **không nhất thiết cần group conversion**.

## 8. Áp dụng trong Spring MVC và Spring Boot

Spring Framework 6+/Spring Boot 3+ dùng Jakarta namespace, thường kết nối Bean Validation provider qua `LocalValidatorFactoryBean`.

DTO minh họa:

```java
import jakarta.validation.GroupSequence;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;

interface InvoiceRules {}

@GroupSequence({CreateInvoiceRequest.class, InvoiceRules.class})
public class CreateInvoiceRequest {

    @NotBlank
    public String code;

    @AssertTrue(groups = InvoiceRules.class)
    public boolean policyAccepted;

    public CreateInvoiceRequest() {}
}
```

Đặt DTO vào file `CreateInvoiceRequest.java`, có cơ chế binding phù hợp với Jackson/Spring. Trong ứng dụng API thực tế nên thiết kế DTO bất biến hay có setter một cách nhất quán, không vì ví dụ này mà công khai field nhạy cảm.

Controller minh họa:

```java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InvoiceController {

    @PostMapping("/invoices")
    public ResponseEntity<String> create(
            @Valid @RequestBody CreateInvoiceRequest request) {
        return ResponseEntity.ok("accepted");
    }
}
```

Khi JSON được deserialize thành object thành công và Jakarta validator đã được cấu hình:

- `@Valid` kích hoạt validation của request object.
- Vì class `CreateInvoiceRequest` đã định nghĩa lại Default, `code` được kiểm tra trước.
- Nếu `code` trống, nhóm `InvoiceRules` không được chạy.
- Nếu code hợp lệ nhưng `policyAccepted=false`, nhóm `InvoiceRules` có lỗi.
- Spring MVC thường chuyển lỗi object validation thành HTTP 400 nếu controller không xử lý `BindingResult` hoặc exception handler riêng.

Một cách nhận lỗi trực tiếp trong controller là đặt `BindingResult` **ngay sau** tham số `@Valid` tương ứng trong chữ ký method. Không nên nhầm lỗi JSON không parse được với lỗi Jakarta constraint: Jackson có thể thất bại trước khi Bean Validation chạy.

### `@Valid` và `@Validated`

Trong ngữ cảnh MVC phù hợp, `@Valid` thường yêu cầu nhóm Default. Spring `@Validated(OtherChecks.class)` có thể chủ động yêu cầu nhóm khác. Nếu chỉ yêu cầu một nhóm khác Default, **không mặc nhiên dùng redefined Default sequence** trên class.

Hãy test cấu hình group của controller, đặc biệt khi cùng DTO được dùng ở nhiều endpoint. Class-level redefinition thay đổi **hành vi mặc định của tất cả những nơi yêu cầu Default**, không chỉ controller đã tạo class.

## 9. Phần mở rộng động của Hibernate Validator

`@GroupSequence` trên class định nghĩa **sequence tĩnh**. Nếu nghiệp vụ yêu cầu sequence thay đổi dựa trên **trạng thái instance**, Hibernate Validator cung cấp phần mở rộng:

- `org.hibernate.validator.group.GroupSequenceProvider`.
- `org.hibernate.validator.spi.group.DefaultGroupSequenceProvider<T>`.

Ví dụ mô tả ý tưởng: với `Submission`, nếu `submitted == false`, sequence là `{Submission.class}`; nếu `submitted == true`, sequence là `{Submission.class, SubmittedChecks.class}`.

Một provider động có phương thức:

```java
@Override
public List<Class<?>> getValidationGroups(Submission value) {
    List<Class<?>> groups = new ArrayList<>();
    groups.add(Submission.class);

    if (value != null && value.isSubmitted()) {
        groups.add(SubmittedChecks.class);
    }

    return groups;
}
```

Đây là snippet **bên trong** implementation `DefaultGroupSequenceProvider<Submission>` đã được khai báo; cần import `java.util.List` và `java.util.ArrayList` cùng định nghĩa `Submission`, `SubmittedChecks`. Đăng ký provider bằng `@GroupSequenceProvider(MySequenceProvider.class)` trên class, không phải annotation chuẩn Jakarta.

Các lưu ý:

1. Sequence trả về **vẫn phải chứa chính bean class**.
2. Provider có thể được gọi khi instance null (chẳng hạn một số tình huống metadata/validateValue), nên cần xử lý null.
3. Implementation cần constructor public không tham số và an toàn đa luồng.
4. Không kết hợp static `@GroupSequence` class-level với dynamic `@GroupSequenceProvider` trên cùng class.
5. Đây là **phụ thuộc Hibernate Validator**, không portable sang mọi Jakarta provider.

Chỉ dùng dynamic sequence khi có lý do rõ ràng; đôi khi một DTO khác hoặc các groups được caller chọn tường minh sẽ đơn giản hơn.

## 10. Lỗi phổ biến và cách kiểm thử

### Lỗi thường gặp

1. **Dùng `Default.class` trong `@GroupSequence` đặt trên chính class.** Đây là self-reference; dùng `YourBean.class`.
2. **Bỏ `YourBean.class` khỏi sequence.** Class redefinition bắt buộc chứa class đó; nếu không sẽ có `GroupDefinitionException`.
3. **Cho rằng `validate(bean, A.class, B.class)` đảm bảo A trước B.** Phải dùng sequence để có thứ tự.
4. **Nghĩ sequence trả duy nhất một violation.** Một nhóm đang chạy có thể có nhiều lỗi; dừng giữa các groups.
5. **Nghĩ parent sequence tự truyền sang child `@Valid`.** Redefinition có phạm vi cục bộ.
6. **Nhầm interface sequence với class sequence.** Interface chỉ chạy khi được yêu cầu; class thay đổi Default.
7. **Quên groups trên constraint nâng cao.** Nếu không khai báo `groups = BusinessChecks.class`, constraint có thể nằm ở Default và chạy quá sớm.
8. **Đặt groups nhưng không kiểm thử nhánh short-circuit.** Có thể trả những lỗi không mong muốn hoặc bỏ sót nhóm.
9. **Tạo vòng phụ thuộc group sequence/group inheritance.** Khi đánh giá nhóm có thể có `GroupDefinitionException`.
10. **Cho rằng `@GroupSequence` xử lý JSON/type conversion.** Nó chỉ xử lý thứ tự validation, không chuyển đổi request.
11. **Bật Hibernate fail-fast rồi mong lỗi đầu luôn thuộc field mong muốn.** Thứ tự constraint trong group không được bảo đảm.
12. **Tạo provider động không thread-safe.** `DefaultGroupSequenceProvider` có thể được dùng đồng thời.
13. **Dùng `@ConvertGroup` mà thiếu `@Valid`.** Không có cạnh cascade hợp lệ; có thể báo lỗi cấu hình.
14. **Đưa toàn bộ entity graph vào sequence phức tạp.** Nên validate DTO/use case có giới hạn rõ, tránh kiểm tra quá rộng và truy cập JPA lazy ngoài ý muốn.

### Ma trận kiểm thử

| Trường hợp | Kỳ vọng |
| --- | --- |
| Default constraints lỗi, nhóm nâng cao cũng lỗi | Chỉ lỗi nhóm Default hosted trên class |
| Default đạt, `ConsistencyChecks` lỗi | Chỉ lỗi Consistency |
| Default và Consistency đạt, Approval lỗi | Chỉ lỗi Approval |
| Cả ba tầng đạt | Tập violations rỗng |
| Yêu cầu riêng `ConsistencyChecks.class` | Không tự chạy Default sequence |
| Sequence class thiếu chính class | `GroupDefinitionException` |
| Class sequence chứa `Default.class` | Cấu hình không hợp lệ |
| Parent Default redefined có child `@Valid` | Child dùng Default của mình, không sao chép nguyên parent sequence |
| Child có default redefinition riêng | Child áp dụng sequence của nó khi Default được yêu cầu |
| Interface-level sequence được gọi tường minh | Groups chạy theo thứ tự interface sequence |
| JSON sai cú pháp | Lỗi deserialize, không phải thứ tự constraints |

### Tự kiểm tra

1. **Vì sao `@GroupSequence({Invoice.class, Checks.class})` hợp lệ?** Vì `Invoice.class` đại diện những constraints Default hosted trên Invoice, và class bắt buộc có mặt trong sequence.
2. **Vì sao không thay bằng `Default.class`?** Vì đang định nghĩa lại Default, sẽ dẫn tới vòng định nghĩa.
3. **Code trống và quantity sai có thể báo hai lỗi không?** Có, vì cùng thuộc tầng đầu; dừng nhóm sau chứ không dừng ngay lỗi đầu.
4. **Khi caller chỉ gọi `validate(invoice, ApprovalChecks.class)`, có chạy tầng cơ bản không?** Không mặc nhiên.
5. **Child nhận toàn bộ nhóm của parent qua `@Valid` không?** Không đối với class-level Default redefinition; child nhận Default hoặc group chuyển đổi thích hợp.
6. **Khi nào chọn interface-level sequence?** Khi nhiều use case cần mức validation khác nhau do caller lựa chọn, không muốn thay đổi Default của bean.
7. **Khi nào dùng Hibernate `@GroupSequenceProvider`?** Khi cần thay đổi default sequence theo state instance và chấp nhận phụ thuộc provider.

## 11. Tài liệu tham khảo

- [Jakarta Bean Validation 3.0 — Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): mục *Group sequence*, *Redefining the Default group for a class*, *Validation routine*, *Group conversion*.
- [Jakarta Validation 3.0 — `@GroupSequence`](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/GroupSequence.html): hợp đồng thứ tự groups.
- [Jakarta Validation 3.0 — `Default`](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/groups/Default.html): marker group mặc định.
- [Hibernate Validator 8 — Reference Guide](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/): `@GroupSequence`, default group redefinition, group conversion, dynamic sequence.
- [Hibernate Validator 8 — `DefaultGroupSequenceProvider`](https://docs.hibernate.org/validator/8.0/api/org/hibernate/validator/spi/group/DefaultGroupSequenceProvider.html): SPI sequence động.
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): tích hợp Jakarta provider qua `LocalValidatorFactoryBean`.
- [Spring Framework — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): `@Valid`, `@Validated`, `BindingResult`, xử lý lỗi.

**Ghi nhớ:** khi đặt `@GroupSequence` trên một class, bạn định nghĩa lại **Default của chính class đó**. Sequence phải chứa **class**, không chứa `Default.class` để thay thế class. Nhóm sau chỉ chạy khi nhóm trước không có lỗi, và sequence của parent **không tự được truyền nguyên** tới bean con khi cascade.
