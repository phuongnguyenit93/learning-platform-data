# Kiểm thử constraint riêng, nhóm và kiểm tra lan truyền trong Jakarta Bean Validation

## 1. Ba cơ chế phải được kiểm thử độc lập

Trong Spring Framework, Bean Validation thường được tích hợp qua `LocalValidatorFactoryBean`, còn Hibernate Validator là một provider phổ biến của Jakarta Validation. Khi một object được kiểm tra, ba câu hỏi cần tách bạch là:

1. **Constraint riêng (custom constraint):** Quy tắc do ứng dụng tự định nghĩa có trả đúng kết quả với giá trị hợp lệ, sai định dạng, rỗng và `null` không?
2. **Nhóm kiểm tra (validation groups):** Khi gọi validate với nhóm `Draft` hoặc `Publish`, chỉ những constraint thuộc nhóm tương ứng có được chạy không? Nhóm mặc định `Default` hoạt động ra sao?
3. **Kiểm tra lan truyền (cascaded validation):** Ràng buộc trên object lồng nhau hoặc phần tử collection có được kiểm tra qua `@Valid` không? Nếu cần đổi nhóm khi đi từ object cha sang object con thì `@ConvertGroup` có hoạt động đúng không?

Đây là ba lớp trách nhiệm **khác nhau**. Một custom validator tự viết chính xác vẫn có thể không chạy khi nhóm không khớp. Một trường con có annotations hợp lệ vẫn có thể bị bỏ qua nếu thiếu `@Valid`. Ngược lại, một `@GroupSequence` có thể chủ động bỏ qua nhóm phía sau khi nhóm phía trước đã vi phạm.

Bài học sử dụng **Java 17, Jakarta Validation 3.0, Hibernate Validator 8 và JUnit 5**, kèm chương trình Maven chạy độc lập. Không cần Spring Boot, HTTP server hay database để thử logic Bean Validation. Phần cuối giải thích cách tích hợp cùng Spring MVC `@Valid` và `@Validated`.

## 2. Những API và annotation chính

| Thành phần | Vai trò | Điểm quan sát trong test |
| --- | --- | --- |
| `jakarta.validation.Constraint` | Đánh dấu một annotation là Bean Validation constraint | Có `validatedBy` trỏ đúng validator |
| `ConstraintValidator<A,T>` | Chứa logic của custom constraint | `initialize(...)`, `isValid(value, context)` |
| `Validator#validate(bean, groups...)` | Kiểm tra object và graph với các nhóm được chọn | Danh sách `ConstraintViolation` |
| `Validator#validateProperty(...)` | Kiểm tra trực tiếp property của object | **Không cascade** vào object lồng |
| `Validator#validateValue(...)` | Kiểm tra giá trị giả định của một property mà không cần instance | Dùng để unit test một constraint |
| `ConstraintViolation#getPropertyPath()` | Đường dẫn tới trường lỗi | `sku`, `recipient.email` |
| `ConstraintViolation#getConstraintDescriptor()` | Metadata constraint gây lỗi | Xác định chính xác `ValidSku.class` |
| `@Valid` | Kích hoạt cascaded validation | Lỗi trong object con/collection element |
| `groups = ...` | Đặt constraint vào một hoặc nhiều groups | Default, Draft, Publish, Contact |
| `@GroupSequence` | Ép thứ tự đánh giá các nhóm | Nhóm phía sau không chạy nếu nhóm trước lỗi |
| `@ConvertGroup` | Chuyển nhóm cho **cạnh cascade** | Publish trên cha → Contact trên con |
| `ValidationMessages.properties` | Tra message template của constraint | `getMessageTemplate()` và `getMessage()` |

Mặc định, `validator.validate(bean)` dùng nhóm `jakarta.validation.groups.Default`. Nếu chỉ gọi `validator.validate(bean, Publish.class)`, **không phải tất cả constraint mặc định đều tự chạy theo**; điều đó chỉ xảy ra nếu quan hệ kế thừa nhóm hoặc group sequence yêu cầu.

## 3. Thiết kế bài toán minh họa

Một phiếu hàng hóa `Item` có các quy tắc:

- `id` luôn cần có ở nhóm **Default**.
- `title` phải có ở nhóm **Draft** khi soạn nháp.
- `sku` phải có và đúng mẫu như `AB-123` ở nhóm **Publish**.
- `stock` phải dương ở nhóm **Publish**.
- `recipient` cần tồn tại ở nhóm **Publish**.
- Bên trong `recipient`, `name` phải có và `email` đúng định dạng, nhưng các constraint thuộc nhóm riêng **Contact**.
- Một cascade từ `Item.recipient` được cấu hình `@ConvertGroup(from=Publish.class,to=Contact.class)` để khi xuất bản phiếu hàng hóa, các điều kiện liên hệ cũng được kiểm tra.
- Nhóm trình tự `Ready` thực hiện **Draft rồi Publish**, dừng lại sau Draft nếu có lỗi.

Ta dùng đầu vào cố tình sai:

```text
id        = ""
title     = ""
sku       = "bad-9"
stock     = 0
recipient = { name: "", email: "not-email" }
```

Nếu kiểm tra từng nhóm độc lập, kết quả phải khác nhau:

| Nhóm gọi validate | Những field gây lỗi |
| --- | --- |
| Không truyền group (Default) | `id` |
| `Draft` | `title` |
| `Publish` | `sku`, `stock`, `recipient.name`, `recipient.email` |
| `Ready` (Draft → Publish) | Chỉ `title` vì Draft thất bại |
| `Ready` sau khi sửa title | Những lỗi Publish nếu vẫn tồn tại |

Test phải đối chiếu **tập đường dẫn** hoặc mã constraint có cấu trúc, không dựa vào thứ tự bất kỳ của `Set<ConstraintViolation<?>>`.

## 4. Tạo custom constraint đúng quy ước

Để kiểm tra SKU, ta định nghĩa annotation `@ValidSku`.

Các thành phần bắt buộc của một Bean Validation constraint annotation thông dụng:

```java
@Documented
@Constraint(validatedBy = SkuValidator.class)
@Target({
    ElementType.FIELD,
    ElementType.PARAMETER,
    ElementType.ANNOTATION_TYPE,
    ElementType.TYPE_USE
})
@Retention(RetentionPolicy.RUNTIME)
public @interface ValidSku {

    String message() default "{demo.sku.invalid}";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
```

Đây là **đoạn rút từ chương trình đầy đủ ở mục 9**. Khi viết annotation top-level public, file phải có tên `ValidSku.java`; trong chương trình mẫu, nó được khai báo là annotation nested trong `ValidationLab.java` để có ít file hơn.

Giải thích:

- `@Constraint(validatedBy=SkuValidator.class)` liên kết annotation với implementation.
- `@Retention(RUNTIME)` cho phép provider đọc annotation bằng reflection khi validate.
- `@Target(...)` giới hạn những vị trí được phép áp dụng.
- `message()` là message template; dùng một key dễ bản địa hóa.
- `groups()` là danh sách nhóm. **Mặc định bắt buộc là mảng rỗng**; khi sử dụng annotation mà không chỉ định nhóm, nó thuộc nhóm `Default`.
- `payload()` mang metadata mở rộng; không dùng để quyết định authentication/authorization.

### 4.1. ConstraintValidator: null thường được coi là hợp lệ

Implementation:

```java
public static final class SkuValidator
        implements ConstraintValidator<ValidSku, String> {

    private static final Pattern PATTERN =
        Pattern.compile("[A-Z]{2}-[0-9]{3}");

    @Override
    public boolean isValid(
            String value,
            ConstraintValidatorContext context) {

        return value == null || PATTERN.matcher(value).matches();
    }
}
```

**Vì sao `null` được coi là hợp lệ?** Một custom constraint kiểm tra định dạng thường nên chỉ trả lời “nếu có SKU, SKU có đúng mẫu không?”. Việc SKU có bắt buộc hay không nên được kiểm tra độc lập bằng `@NotNull` hoặc `@NotBlank`. Thiết kế này giúp tái sử dụng constraint cho trường optional.

Với `@NotBlank` kết hợp `@ValidSku` trên cùng field:

- `sku=null`: `@NotBlank` vi phạm, `@ValidSku` chấp nhận `null`.
- `sku=""`: `@NotBlank` vi phạm; `@ValidSku` cũng có thể vi phạm vì chuỗi rỗng không đúng regex. Có thể nhận **hai violations**, và test cần quyết định đó có phải thiết kế mong muốn.
- `sku="bad-9"`: không blank, nhưng sai pattern → chỉ `@ValidSku` vi phạm.
- `sku="AB-123"`: cả hai đều hợp lệ.

Nếu muốn đúng một lỗi cho chuỗi rỗng, có thể thiết kế custom constraint bỏ qua blank rồi giao cho `@NotBlank`, nhưng đó là thay đổi contract của constraint; phải ghi rõ trong test. Ví dụ chính giữ regex đơn giản và dùng input sai không rỗng để kiểm chứng riêng `ValidSku`.

### 4.2. initialize() và state/thread safety

`ConstraintValidator#initialize(annotation)` là hook tùy chọn để đọc các attribute của annotation, ví dụ một `@ValidSku(prefix="AB")` trong một thiết kế khác. Với regex cố định ở đây không cần override `initialize()`.

Provider có thể cache và tái sử dụng validator instances. Đừng lưu request-specific value, principal hoặc `ConstraintValidatorContext` vào instance fields rồi sử dụng lại xuyên request. `Pattern` bất biến dùng chung là phù hợp; `Matcher` tạo theo từng lời gọi và không chia sẻ giữa threads.

### 4.3. Viết custom violation ở field con

Với một class-level constraint kiểm tra nhiều fields, bạn có thể tạo custom field path:

```java
context.disableDefaultConstraintViolation();
context.buildConstraintViolationWithTemplate(
        "{demo.range.invalid}")
    .addPropertyNode("endDate")
    .addConstraintViolation();
```

Đây là **fragment minh họa** nằm trong `ConstraintValidator#isValid` của class-level constraint, không phải phần của chương trình chạy. Khi bỏ default violation, phải tạo violation mới nếu validation thất bại. Không ghép dữ liệu người dùng vào EL/message template không kiểm soát.

## 5. Validation groups: chọn đúng subset constraint

Nhóm Jakarta Bean Validation được biểu diễn bằng interface:

```java
public interface Draft {}
public interface Publish {}
public interface Contact {}
```

Đây là fragment minh họa; trong ví dụ chạy, các interface thuộc `ValidationLab.Groups`.

Khi khai báo:

```java
@NotBlank
private String id;

@NotBlank(groups = Draft.class)
private String title;

@ValidSku(groups = Publish.class)
private String sku;
```

Ta có:

- `@NotBlank` trên `id` thuộc `Default` vì không ghi `groups`.
- `@NotBlank(groups=Draft.class)` trên `title` thuộc Draft.
- `@ValidSku(groups=Publish.class)` trên `sku` thuộc Publish.

Gọi:

```java
validator.validate(item);
validator.validate(item, Draft.class);
validator.validate(item, Publish.class);
validator.validate(
    item, Default.class, Draft.class, Publish.class);
```

Bốn lệnh có ngữ nghĩa khác nhau. Khi truyền nhiều nhóm trong một lần validate, **không có thứ tự đánh giá mặc định** giữa các nhóm đó. Đừng dùng thứ tự thêm nhóm vào varargs để xây workflow “trước–sau”; hãy dùng `@GroupSequence`.

### 5.1. Kế thừa nhóm

Nếu viết:

```java
public interface Publish extends Draft {}
```

thì Publish có thể kế thừa các constraint của Draft theo quy tắc group inheritance. Trong project demo, ba nhóm độc lập để test dễ phân biệt. **Không** suy luận rằng Publish luôn tự chứa Draft nếu bạn không khai báo quan hệ đó.

### 5.2. Default không tự chạy khi chọn group khác

Một lỗi thiết kế phổ biến:

```java
validator.validate(item, Publish.class);
```

rồi kỳ vọng mọi `@NotBlank` không ghi groups đều được kiểm tra. Mặc định chúng nằm trong `Default`, không tự có mặt ở Publish. Nếu một rule phải chạy ở cả hai, hãy khai báo:

```java
@NotBlank(groups = {Default.class, Publish.class})
private String id;
```

hoặc dùng sequence/kế thừa nhóm theo thiết kế. Cần test cả hai cách để tránh bỏ qua constraint “luôn bắt buộc”.

### 5.3. Validation groups không phải roles/quyền truy cập

Tên `AdminChecks` không tự bảo đảm caller là admin. Groups chỉ chọn **tập constraint cần thực thi**; authorization trên resource và field phải nằm ở Spring Security/service/domain boundary. Dù validate với `AdminChecks` thành công, user không được quyền thay role chỉ vì DTO hợp lệ.

## 6. Group sequence: có thứ tự và short-circuit

Một sequence:

```java
@GroupSequence({Draft.class, Publish.class})
public interface Ready {}
```

Khi gọi:

```java
validator.validate(item, Ready.class);
```

provider phải:

1. Chạy tất cả constraints thuộc Draft.
2. Nếu Draft có **bất kỳ** violation nào, **không chạy Publish** trong lượt sequence đó.
3. Nếu Draft đạt, chạy Publish.

**Không có thứ tự ổn định giữa các constraints cùng một group.** Sequence chỉ đảm bảo thứ tự **giữa các group**, không phải giữa các field/validator trong group.

Với item có title rỗng và SKU sai, `Ready` chỉ báo `title`; điều đó không có nghĩa SKU đã được xác nhận hợp lệ. Sau khi sửa title, gọi validate lại sẽ cho các lỗi Publish còn lại.

### 6.1. Những lỗi về group sequence

- Không khai báo chu kỳ group sequence. Circular dependency có thể gây `GroupDefinitionException`.
- Interface định nghĩa sequence không nên đồng thời kế thừa group interface khác.
- Không gắn constraint trực tiếp vào marker interface đóng vai trò sequence rồi giả định chúng chạy như group thông thường.
- Khi re-define default sequence trực tiếp trên class, thường phải đưa **chính class đó** vào sequence theo quy tắc Jakarta; group sequence thay `Default` chỉ có phạm vi cục bộ class, không tự lan nguyên sequence xuống mọi object con.
- Nếu muốn kiểm tra mọi lỗi đồng thời, đừng dùng sequence vì short-circuit là chủ ý.

### 6.2. Kiểm thử đúng bản chất short-circuit

Test không chỉ đếm lỗi; phải xác nhận **Publish không xuất hiện** khi Draft đã lỗi:

```java
Set<ConstraintViolation<Item>> violations =
    validator.validate(item, Ready.class);

assertEquals(Set.of("title"), paths(violations));
```

Đây là fragment JUnit, cần helper `paths(...)` và model thuộc chương trình ở mục 9. Với một `title` hợp lệ, test lại và xác nhận lỗi Publish lúc đó xuất hiện.

## 7. Cascaded validation: @Valid không phải constraint

Một object cha chứa object con:

```java
public class Item {
    @Valid
    private Recipient recipient;
}

public class Recipient {
    @NotBlank
    private String name;
}
```

Đây là fragment minh họa, không phải file độc lập. Khi validate Item với nhóm phù hợp, `@Valid` cho phép provider **đi vào Recipient** và kiểm tra constraints tại đó.

Điều quan trọng:

- Không có `@Valid`: kiểm tra Item **không tự dò toàn bộ object graph**.
- `@Valid` tự nó **không phải constraint** và không tạo violation “cascaded” riêng.
- Nếu recipient bằng `null`, cascade **bỏ qua**; phải có `@NotNull` trên reference nếu object con bắt buộc tồn tại.
- Nếu recipient có dữ liệu, các constraint của nó phải thuộc **nhóm đang được truyền** hoặc nhóm được chuyển đổi.
- Object graph có vòng tham chiếu có cơ chế chống loop vô hạn theo Bean Validation spec; đừng viết validator tự đi vòng object graph theo recursion không kiểm soát.
- Trên collection, có thể dùng `List<@Valid Recipient>` để validate từng phần tử (container element cascading); đừng đặt `@Valid` đồng thời trên container và type argument chỉ để “cho chắc” vì có nguy cơ xử lý trùng.

### 7.1. Không có @Valid thì test phải chứng minh không cascade

Một wrapper:

```java
public static final class WithoutCascade {
    private final Recipient recipient;

    public WithoutCascade(Recipient recipient) {
        this.recipient = recipient;
    }
}
```

Nếu chỉ đặt một Recipient sai vào bên trong, `validator.validate(wrapper, Contact.class)` không phát hiện field của Recipient vì field chưa đánh dấu `@Valid`.

Đây không phải lỗi của provider; đó là contract của cascaded validation. Test cả hai trường hợp **có** và **không có** `@Valid` để tránh nhầm việc thiếu `@Valid` với việc validator “bị lỗi”.

### 7.2. @Valid và thiếu object con

Một field:

```java
@NotNull(groups = Publish.class)
@Valid
private Recipient recipient;
```

khi `recipient == null` và validate Publish chỉ tạo violation từ `@NotNull`. Không có lỗi `recipient.name` hoặc `recipient.email` vì không có đối tượng con để đi vào.

Nếu property là optional theo nghiệp vụ, chỉ có `@Valid` là hợp lý; nếu bắt buộc, cần `@NotNull` với group thích hợp.

### 7.3. Cascaded validation qua collection

Ví dụ:

```java
public class ContactBatch {
    private List<@Valid Recipient> contacts;
}
```

Với Hibernate Validator 8/Jakarta Validation 3, một `List` có thể dùng value extractor chuẩn để kiểm tra từng Recipient ở các phần tử. Property path có thể thể hiện index như `contacts[0].email`.

Khi test collection, **không phụ thuộc thứ tự Set violations**. Chỉ assert field paths hoặc container element nodes có cấu trúc và kiểm tra một phần tử được cố ý tạo lỗi.

## 8. Chuyển nhóm khi cascade bằng @ConvertGroup

Giả sử Item được kiểm tra ở nhóm `Publish`, trong khi Recipient định nghĩa ràng buộc ở nhóm `Contact`. Nếu chỉ dùng `@Valid`, nhóm Publish mặc định truyền xuống Recipient, nên `@NotBlank(groups=Contact.class)` có thể không chạy.

Khai báo:

```java
@NotNull(groups = Publish.class)
@Valid
@ConvertGroup(from = Publish.class, to = Contact.class)
private Recipient recipient;
```

Khi validate Item với Publish, provider đi qua cạnh `recipient`, chuyển nhóm **Publish → Contact**, rồi kiểm tra Recipient theo nhóm Contact. Không phải đổi nhóm cho mọi property của Item: `sku` và `stock` vẫn được kiểm tra theo Publish.

Quy tắc cần nhớ:

- `@ConvertGroup` chỉ hợp lệ ở vị trí có cascade `@Valid`; nếu không, provider có thể báo `ConstraintDeclarationException`.
- `from` phải là một group thông thường, **không phải một group sequence**.
- Không được khai báo hai rule conversion với cùng `from` ở một element.
- Conversion **không đệ quy theo chuỗi**: A→B và B→C trên cùng cạnh không khiến A tự đi hết tới C.
- Group sequence được **mở rộng** trước khi áp dụng conversion trên cạnh cascade; vì thế sequence Ready chứa Publish vẫn có thể kích hoạt Publish→Contact khi đánh giá bước Publish.
- Với một reference null, không có nested validation; conversion không tạo object con.

### 8.1. Test chứng minh chuyển nhóm đã xảy ra

Nếu validate Publish và thấy violations từ `recipient.email` và `recipient.name`, đó là dấu hiệu nhóm Contact được áp dụng lên Recipient. Để khẳng định nguyên nhân, cần biết Recipient constraints chỉ thuộc Contact, không thuộc Publish/Default.

Một test mạnh hơn chỉ đếm tổng lỗi là so sánh **tập đường dẫn**:

```text
recipient.email
recipient.name
sku
stock
```

Khi không có `@ConvertGroup` hoặc khi truyền nhóm không phù hợp, tập violations có thể khác. Đừng chọn assert quá rộng như `hasErrors() == true` vì một lỗi `sku` có thể che việc Recipient hoàn toàn không được kiểm tra.

## 9. Project Java 17 chạy độc lập

Ví dụ hoàn chỉnh sử dụng một file model/constraint, một file JUnit test, một bundle messages và Maven. Các class trong file `ValidationLab.java` được khai báo nested để người học có thể chạy mà không phải tạo nhiều file Java tách rời.

### 9.1. Cấu trúc dự án

```text
constraint-groups-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/ValidationLab.java
    │   └── resources/ValidationMessages.properties
    └── test/
        └── java/demo/ValidationLabTest.java
```

### 9.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>demo</groupId>
  <artifactId>constraint-groups-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.hibernate.validator</groupId>
      <artifactId>hibernate-validator</artifactId>
      <version>8.0.2.Final</version>
    </dependency>
    <dependency>
      <groupId>org.glassfish</groupId>
      <artifactId>jakarta.el</artifactId>
      <version>4.0.2</version>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.12.2</version>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.2</version>
      </plugin>
    </plugins>
  </build>
</project>
```

Hibernate Validator 8 là provider cho Jakarta Bean Validation 3.0; Jakarta EL support là dependency cần thiết cho một số message interpolation scenarios. Các tests không cần Spring Boot starter vì chúng kiểm tra **Jakarta Validator** trực tiếp.

### 9.3. ValidationMessages.properties

```properties
demo.sku.invalid=Mã SKU phải có dạng AB-123 (hai chữ cái in hoa và ba chữ số)
```

Provider nội suy khóa `{demo.sku.invalid}` thành thông báo. Để test ổn định giữa các locale, bộ JUnit chủ yếu assert annotation type và field path, không so sánh câu dịch của built-in constraints.

### 9.4. ValidationLab.java

```java
package demo;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

import jakarta.validation.Constraint;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Payload;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.GroupSequence;

public class ValidationLab {

    private ValidationLab() {
    }

    public static final class Groups {
        private Groups() {
        }

        public interface Draft {}
        public interface Publish {}
        public interface Contact {}

        @GroupSequence({Draft.class, Publish.class})
        public interface Ready {}
    }

    @Documented
    @Constraint(validatedBy = SkuValidator.class)
    @Target({
        ElementType.FIELD,
        ElementType.PARAMETER,
        ElementType.ANNOTATION_TYPE,
        ElementType.TYPE_USE
    })
    @Retention(RetentionPolicy.RUNTIME)
    public @interface ValidSku {
        String message() default "{demo.sku.invalid}";
        Class<?>[] groups() default {};
        Class<? extends Payload>[] payload() default {};
    }

    public static final class SkuValidator
            implements ConstraintValidator<ValidSku, String> {

        private static final Pattern SKU =
            Pattern.compile("[A-Z]{2}-[0-9]{3}");

        @Override
        public boolean isValid(
                String value,
                ConstraintValidatorContext context) {

            // Null được giao cho @NotNull/@NotBlank.
            return value == null || SKU.matcher(value).matches();
        }
    }

    public static final class Recipient {

        @NotBlank(groups = Groups.Contact.class)
        private final String name;

        @NotBlank(groups = Groups.Contact.class)
        @Email(groups = Groups.Contact.class)
        private final String email;

        public Recipient(String name, String email) {
            this.name = name;
            this.email = email;
        }

        public String getName() {
            return name;
        }

        public String getEmail() {
            return email;
        }
    }

    public static final class Item {

        // Không ghi groups => nhóm Default.
        @NotBlank
        private final String id;

        @NotBlank(groups = Groups.Draft.class)
        private final String title;

        @NotBlank(groups = Groups.Publish.class)
        @ValidSku(groups = Groups.Publish.class)
        private final String sku;

        @Positive(groups = Groups.Publish.class)
        private final int stock;

        @NotNull(groups = Groups.Publish.class)
        @Valid
        @ConvertGroup(
            from = Groups.Publish.class,
            to = Groups.Contact.class
        )
        private final Recipient recipient;

        public Item(
                String id,
                String title,
                String sku,
                int stock,
                Recipient recipient) {

            this.id = id;
            this.title = title;
            this.sku = sku;
            this.stock = stock;
            this.recipient = recipient;
        }

        public String getId() {
            return id;
        }

        public String getTitle() {
            return title;
        }

        public String getSku() {
            return sku;
        }

        public int getStock() {
            return stock;
        }

        public Recipient getRecipient() {
            return recipient;
        }
    }

    // KHÔNG có @Valid: Bean Validation không tự đi vào recipient.
    public static final class WithoutCascade {
        private final Recipient recipient;

        public WithoutCascade(Recipient recipient) {
            this.recipient = recipient;
        }

        public Recipient getRecipient() {
            return recipient;
        }
    }

    // TYPE_USE @Valid: provider đi vào từng phần tử List.
    public static final class ContactBatch {
        private final List<@Valid Recipient> contacts;

        public ContactBatch(List<Recipient> contacts) {
            this.contacts = contacts;
        }

        public List<Recipient> getContacts() {
            return contacts;
        }
    }

    public static Item invalidItem() {
        return new Item(
            "", "", "bad-9", 0,
            new Recipient("", "not-email"));
    }

    public static Item validItem() {
        return new Item(
            "ITEM-1", "Laptop", "AB-123", 5,
            new Recipient("Lan", "lan@example.test"));
    }

    private static String describe(
            Set<? extends ConstraintViolation<?>> violations) {

        return violations.stream()
            .map(v -> v.getPropertyPath()
                + ":"
                + v.getConstraintDescriptor()
                    .getAnnotation()
                    .annotationType()
                    .getSimpleName())
            .sorted()
            .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                 Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();
            Item bad = invalidItem();

            System.out.println("DEFAULT="
                + describe(validator.validate(bad)));
            System.out.println("DRAFT="
                + describe(validator.validate(
                    bad, Groups.Draft.class)));
            System.out.println("PUBLISH="
                + describe(validator.validate(
                    bad, Groups.Publish.class)));
            System.out.println("READY="
                + describe(validator.validate(
                    bad, Groups.Ready.class)));

            Item titleFixed = new Item(
                "", "Laptop", "bad-9", 0,
                new Recipient("", "not-email"));

            System.out.println("READY_AFTER_TITLE="
                + describe(validator.validate(
                    titleFixed, Groups.Ready.class)));
            System.out.println("ALL_VALID="
                + validator.validate(
                    validItem(), Groups.Ready.class).isEmpty());
        }
    }
}
```

### 9.5. Tại sao mô hình này dễ kiểm thử?

- Các fields là `final` nên không phát sinh tác dụng phụ do binding khi chỉ đang validate.
- `@ValidSku` chỉ thuộc nhóm Publish; `@NotBlank` của id thuộc Default; hai vai trò dễ phân biệt.
- Recipient constraints chỉ thuộc nhóm Contact, do đó xuất hiện trong Publish là bằng chứng của `@ConvertGroup`.
- `@NotNull(groups=Publish.class)` trên reference và `@Valid` giải quyết **hai trường hợp khác nhau**: con có tồn tại và con có hợp lệ không.
- `Groups.Ready` là sequence từ Draft tới Publish, không phải một tập groups không thứ tự.
- `describe(...)` dùng annotation type và property path, sort trước khi in. Không dựa vào localized message hoặc thứ tự elements của Set.
- `ValidatorFactory` được tạo một lần cho CLI và đóng khi kết thúc. Trong ứng dụng dài hạn, thường tái sử dụng một `ValidatorFactory`/Spring-managed validator thay vì tạo lại mỗi HTTP request.

### 9.6. Lệnh chạy

Cần Java 17+, Maven 3.x. Trong thư mục chứa `pom.xml`:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java \
  -Dexec.mainClass=demo.ValidationLab
```

Dự kiến chương trình in các dòng sau; bỏ qua logging riêng của Maven hoặc Hibernate Validator:

```text
DEFAULT=id:NotBlank
DRAFT=title:NotBlank
PUBLISH=recipient.email:Email,recipient.name:NotBlank,sku:ValidSku,stock:Positive
READY=title:NotBlank
READY_AFTER_TITLE=recipient.email:Email,recipient.name:NotBlank,sku:ValidSku,stock:Positive
ALL_VALID=true
```

Giải thích từng dòng:

1. **DEFAULT:** chỉ kiểm tra `@NotBlank` trên id; những ràng buộc đánh dấu Draft/Publish/Contact không tự xuất hiện.
2. **DRAFT:** chỉ tiêu đề rỗng tạo vi phạm `NotBlank`.
3. **PUBLISH:** SKU sai pattern, stock bằng 0, Recipient có name rỗng và email sai; nhóm Contact được kích hoạt **qua conversion Publish→Contact**.
4. **READY:** vì Draft đã fail, bước Publish bị bỏ qua; không có thông báo sai SKU trong lượt này.
5. **READY_AFTER_TITLE:** Draft đạt nên Publish chạy và tạo bốn violations còn lại.
6. **ALL_VALID:** item chuẩn đáp ứng cả Draft và Publish (kể cả Contact cascade), do đó không có violations.

Output được suy ra từ rules trong mã và bundle; hãy chạy local để xác nhận trên đúng phiên bản dependency, đặc biệt nếu bạn sửa models/groups/constraints.

## 10. JUnit 5: test riêng từng tính chất

Lưu file `src/test/java/demo/ValidationLabTest.java`. Test dùng một `ValidatorFactory` cho cả class test, nhưng tạo object mới theo từng case. Các helper không dựa vào iteration order của `Set`.

### 10.1. ValidationLabTest.java

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.groups.Default;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

class ValidationLabTest {

    private static ValidatorFactory factory;
    private static Validator validator;

    @BeforeAll
    static void openFactory() {
        factory = Validation.buildDefaultValidatorFactory();
        validator = factory.getValidator();
    }

    @AfterAll
    static void closeFactory() {
        factory.close();
    }

    private static Set<String> paths(
            Set<? extends ConstraintViolation<?>> errors) {

        return errors.stream()
            .map(v -> v.getPropertyPath().toString())
            .collect(Collectors.toSet());
    }

    @Test
    void customConstraintAcceptsProperSkuAndRejectsBadSku() {
        var good = validator.validateValue(
            ValidationLab.Item.class,
            "sku", "AB-123",
            ValidationLab.Groups.Publish.class);

        assertTrue(good.isEmpty());

        var bad = validator.validateValue(
            ValidationLab.Item.class,
            "sku", "bad-9",
            ValidationLab.Groups.Publish.class);

        assertEquals(1, bad.size());
        var violation = bad.iterator().next();

        assertEquals("sku", violation.getPropertyPath().toString());
        assertEquals(
            ValidationLab.ValidSku.class,
            violation.getConstraintDescriptor()
                .getAnnotation().annotationType());
        assertEquals(
            "{demo.sku.invalid}",
            violation.getMessageTemplate());
    }

    @Test
    void nullSkuIsRejectedByNotBlankNotFormatRule() {
        var errors = validator.validateValue(
            ValidationLab.Item.class,
            "sku", null,
            ValidationLab.Groups.Publish.class);

        assertEquals(1, errors.size());
        assertEquals(
            "NotBlank",
            errors.iterator().next()
                .getConstraintDescriptor()
                .getAnnotation().annotationType().getSimpleName());
    }

    @Test
    void defaultGroupRunsOnlyDefaultRules() {
        var errors = validator.validate(
            ValidationLab.invalidItem());

        assertEquals(Set.of("id"), paths(errors));
    }

    @Test
    void draftGroupDoesNotSilentlyRunDefaultOrPublish() {
        var errors = validator.validate(
            ValidationLab.invalidItem(),
            ValidationLab.Groups.Draft.class);

        assertEquals(Set.of("title"), paths(errors));
    }

    @Test
    void publishGroupAlsoCascadesIntoContactGroup() {
        var errors = validator.validate(
            ValidationLab.invalidItem(),
            ValidationLab.Groups.Publish.class);

        assertEquals(
            Set.of(
                "sku", "stock",
                "recipient.name", "recipient.email"
            ),
            paths(errors));
    }

    @Test
    void sequenceStopsWhenDraftFails() {
        var errors = validator.validate(
            ValidationLab.invalidItem(),
            ValidationLab.Groups.Ready.class);

        assertEquals(Set.of("title"), paths(errors));
    }

    @Test
    void sequenceRunsPublishAfterDraftPasses() {
        var item = new ValidationLab.Item(
            "", "Laptop", "bad-9", 0,
            new ValidationLab.Recipient("", "not-email"));

        var errors = validator.validate(
            item, ValidationLab.Groups.Ready.class);

        assertEquals(
            Set.of(
                "sku", "stock",
                "recipient.name", "recipient.email"
            ),
            paths(errors));
    }

    @Test
    void withoutValidNestedErrorsDoNotPropagate() {
        var contact = new ValidationLab.Recipient(
            "", "not-email");
        var holder = new ValidationLab.WithoutCascade(contact);

        assertTrue(validator.validate(
            holder, ValidationLab.Groups.Contact.class).isEmpty());

        // Kiểm tra trực tiếp Contact thì các lỗi xuất hiện.
        assertEquals(
            Set.of("name", "email"),
            paths(validator.validate(
                contact, ValidationLab.Groups.Contact.class)));
    }

    @Test
    void nullRecipientNeedsExplicitNotNullRule() {
        var item = new ValidationLab.Item(
            "ITEM-2", "Valid", "AB-123", 1, null);

        var errors = validator.validate(
            item, ValidationLab.Groups.Publish.class);

        assertEquals(Set.of("recipient"), paths(errors));
        assertEquals(
            "NotNull",
            errors.iterator().next()
                .getConstraintDescriptor()
                .getAnnotation().annotationType().getSimpleName());
    }

    @Test
    void validatePropertyDoesNotCascadeToChild() {
        var item = ValidationLab.invalidItem();

        assertTrue(validator.validateProperty(
            item, "recipient",
            ValidationLab.Groups.Publish.class).isEmpty());

        // validate toàn graph thì @Valid + @ConvertGroup có tác dụng.
        assertFalse(validator.validate(
            item, ValidationLab.Groups.Publish.class).isEmpty());
    }

    @Test
    void containerElementValidCascadesIntoListElements() {
        var batch = new ValidationLab.ContactBatch(
            List.of(new ValidationLab.Recipient(
                "", "not-email")));

        var errors = validator.validate(
            batch, ValidationLab.Groups.Contact.class);

        assertEquals(2, errors.size());
        assertTrue(errors.stream().allMatch(v ->
            v.getPropertyPath().toString()
                .contains("contacts[0]")));
    }

    @Test
    void validItemCanPassAllRequestedGroups() {
        var errors = validator.validate(
            ValidationLab.validItem(),
            Default.class,
            ValidationLab.Groups.Draft.class,
            ValidationLab.Groups.Publish.class);

        assertTrue(errors.isEmpty());
    }
}
```

Bộ test gồm **12 phương thức JUnit**, tập trung vào logic thực tế thay vì kiểm tra một boolean quá chung chung.

### 10.2. Chạy kiểm thử

```bash
mvn -q test
```

Nếu tất cả assertions thành công, Maven trả **exit code 0**. Vì có cờ `-q`, không kỳ vọng stdout nhất định. Báo cáo chi tiết nằm trong `target/surefire-reports/`, ví dụ file XML cho `demo.ValidationLabTest`.

**Đã định nghĩa assertions và expected output từ logic của chương trình, nhưng chưa thực thi compiler/JUnit trong tài liệu này.** Khi áp dụng trong project thật, hãy chạy Maven test trên đúng Java/dependency versions; nếu thay đổi cấu trúc group hoặc messages, cập nhật tests theo contract mới.

### 10.3. Đọc kết quả theo lớp trách nhiệm

| Test | Điều được chứng minh |
| --- | --- |
| `customConstraintAcceptsProperSkuAndRejectsBadSku` | Validator riêng chạy, metadata xác định đúng annotation |
| `nullSkuIsRejectedByNotBlankNotFormatRule` | Null handling tách khỏi format validation |
| `defaultGroupRunsOnlyDefaultRules` | Không truyền group dùng Default |
| `draftGroupDoesNotSilentlyRunDefaultOrPublish` | Draft không tự bao gồm Default/Publish |
| `publishGroupAlsoCascadesIntoContactGroup` | Publish kiểm tra nhóm cha và chuyển qua Contact |
| `sequenceStopsWhenDraftFails` | Group sequence short-circuit |
| `sequenceRunsPublishAfterDraftPasses` | Nhóm sau được chạy khi nhóm đầu đạt |
| `withoutValidNestedErrorsDoNotPropagate` | Thiếu @Valid không tự cascade |
| `nullRecipientNeedsExplicitNotNullRule` | Null được phát hiện bằng @NotNull, không phải @Valid |
| `validatePropertyDoesNotCascadeToChild` | validateProperty không đi sâu vào object con |
| `containerElementValidCascadesIntoListElements` | @Valid ở type argument List dẫn đến nested violations |
| `validItemCanPassAllRequestedGroups` | Trường hợp hợp lệ chạy cả nhiều nhóm thành công |

## 11. Nâng chất lượng tests: kiểm tra nguyên nhân, không chỉ số lỗi

Chỉ viết:

```java
assertFalse(validator.validate(item).isEmpty());
```

thường quá yếu. Nó không nói liệu `@ValidSku` đã chạy hay không; item có thể fail vì `@NotBlank` trên field khác.

Một test tốt nên đối chiếu:

- **Đường dẫn**: `sku`, `recipient.email`, `contacts[0].email`.
- **Loại constraint**: `getConstraintDescriptor().getAnnotation().annotationType()`.
- **Message template**: ví dụ `{demo.sku.invalid}` khi muốn kiểm tra custom annotation đang trỏ đúng bundle key.
- **Group đang được yêu cầu**: Default, Draft, Publish, Ready, Contact.
- **Thiếu hay có @Valid** trên reference/container element.
- **Sự khác biệt** giữa lỗi ở nhóm trước và nhóm sau trong sequence.
- **Không có tác dụng phụ**: validator không được thay object hoặc ghi DB chỉ vì việc kiểm tra hợp lệ.

Khi nhiều violations cùng field, `Set<String> paths` có thể làm mất thông tin về số lỗi/loại annotation. Trong test cần phân biệt hai constraint cùng field, hãy so sánh tập cặp `field + annotation type` hoặc các `ConstraintDescriptor` và đếm số lượng rõ ràng.

### 11.1. Test @NotBlank kết hợp @ValidSku

Một SKU `""` có thể vi phạm cả `@NotBlank` lẫn `@ValidSku`. Nếu API chỉ muốn trả một lỗi cho field, đó là **chiến lược error aggregation** ở tầng presentation hoặc thay đổi thiết kế constraint; Bean Validation không tự cam kết chỉ một violation trên mỗi property.

Một test có thể xác nhận cả hai hoặc dùng một custom constraint chấp nhận blank/null và giao việc “bắt buộc” cho `@NotBlank`. Đừng viết `assertEquals(1, errors.size())` cho chuỗi rỗng khi chính model có hai constraints cùng fail mà không có rule loại trừ.

### 11.2. Test metadata của custom constraint

Dùng:

```java
ConstraintDescriptor<?> descriptor =
    violation.getConstraintDescriptor();

Class<?> annotationType =
    descriptor.getAnnotation().annotationType();

Set<Class<?>> groups = descriptor.getGroups();
```

Đây là fragment; `violation` đã có. Bạn có thể assert `annotationType == ValidSku.class` và `groups` chứa `Publish.class`. Việc test descriptor giúp phát hiện lỗi gắn annotation vào sai property hoặc cấu hình groups sai, ngay cả khi thông báo hiển thị vẫn giống nhau.

### 11.3. Test localization nên tách riêng

`ConstraintViolation#getMessageTemplate()` là chuỗi descriptor ban đầu, còn `getMessage()` đã nội suy theo locale/provider. Nếu mục tiêu là kiểm thử logic constraint, hãy so sánh template/annotation type hơn là một câu tiếng Việt cố định.

Nếu mục tiêu là i18n, tạo resource bundles riêng `ValidationMessages_vi.properties` và `ValidationMessages_en.properties`, chọn locale theo cấu hình provider phù hợp, rồi test message ở đúng locale. **Không thay `Locale.setDefault(...)` toàn JVM theo từng test chạy song song** nếu điều đó tạo race giữa tests.

## 12. Liên hệ Spring MVC: @Valid, @Validated và groups

Trong Spring MVC 6.2, khi Jakarta Bean Validation có trên classpath, `LocalValidatorFactoryBean` thường được đăng ký làm validator mặc định.

### 12.1. @Valid dùng nhóm Default trong trường hợp phổ biến

Fragment controller:

```java
@PostMapping("/inventory/drafts")
public ResponseEntity<?> draft(
        @Valid @RequestBody ItemInput input) {
    return ResponseEntity.ok().build();
}
```

Đây là đoạn tích hợp, cần `ItemInput` DTO và imports. Thông thường `@Valid` trên một argument object kích hoạt Bean Validation với group mặc định. Nếu DTO chỉ khai báo constraints trong nhóm Draft/Publish mà không có constraint Default, chỉ `@Valid` có thể **không thực thi** những rules đó.

### 12.2. @Validated chọn nhóm cụ thể

```java
@PostMapping("/inventory/publish")
public ResponseEntity<?> publish(
        @Validated(Groups.Publish.class)
        @RequestBody ItemInput input) {
    return ResponseEntity.ok().build();
}
```

Đây là fragment dùng `Groups.Publish` và `ItemInput` thuộc thiết kế ứng dụng. `@Validated(...)` là annotation của Spring có hỗ trợ nhóm; với controller argument, nó thường chọn nhóm được yêu cầu cho object-level validation. Nếu muốn Draft rồi Publish theo sequence, chọn `@Validated(Groups.Ready.class)` khi mô hình groups đã phù hợp.

**Chú ý:** `@Validated` ở **cấp class controller** có thể kích hoạt Spring AOP method validation thay vì built-in Spring MVC 6.1+ method validation, dẫn đến đường exception khác. Đừng đồng nhất group selection ở tham số với việc gắn `@Validated` lên toàn controller.

### 12.3. Lỗi MVC khác lỗi Jakarta Validator thuần

| Bối cảnh | Dạng lỗi thông dụng |
| --- | --- |
| `Validator#validate(bean)` thuần | Trả về `Set<ConstraintViolation<T>>`, không tự ném khi có violation |
| `@Valid @RequestBody DTO` ở MVC, không có BindingResult liền sau | `MethodArgumentNotValidException` trong đường object-argument validation |
| Direct method constraints trong MVC 6.1+ | `HandlerMethodValidationException` trong đường method validation |
| `@Valid @ModelAttribute` với `BindingResult` liền kề | Controller nhận lỗi để tự xử lý |
| `@Validated` service method qua Spring AOP | Có thể là `ConstraintViolationException` hoặc `MethodValidationException` tùy cấu hình |

Method validation có thể **bao trùm** nested `@Valid` của các arguments khi phương thức còn khai báo direct constraints. Không viết test chỉ bắt một exception type rồi khẳng định tất cả đường controller validation đều dùng loại đó.

### 12.4. Cascading là trách nhiệm của mô hình

Nếu input có nested object:

```java
public class ItemInput {
    @Valid
    @ConvertGroup(
        from = Groups.Publish.class,
        to = Groups.Contact.class)
    private RecipientInput recipient;
}
```

với `RecipientInput` có constraints thuộc Contact, validation từ Publish có thể đi vào recipient. Chỉ khai báo `RecipientInput` mà quên `@Valid` sẽ không khiến provider tự duyệt con.

Đây là fragment cho Spring MVC DTO, không phải lớp của chương trình độc lập ở mục 9. Với nested list, sử dụng `List<@Valid RecipientInput>` và thiết kế group conversion ở đúng vị trí cascade.

## 13. Kiểm thử ở ba tầng và khi nào dùng tầng nào

| Tầng test | Công cụ | Trọng tâm | Không tự chứng minh |
| --- | --- | --- | --- |
| Unit custom constraint logic | `SkuValidator#isValid(...)` hoặc `Validator#validateValue(...)` | Regex, null, boundary values | Groups/cascade/MVC đầy đủ nếu chỉ gọi isValid trực tiếp |
| Jakarta Bean Validation integration | `Validator#validate(...)` + JUnit 5 | Groups, sequence, cascade, conversion, metadata | Spring MVC argument resolver, HTTP status, @InitBinder, serialization |
| Spring MVC integration | `MockMvc` / Spring Boot Test | `@Validated(groups)`, error mapping, HTTP 400, binding/JSON, controller-specific behavior | Toàn bộ security/business side effects nếu chưa đưa vào test setup |

Một unit test gọi thẳng:

```java
new ValidationLab.SkuValidator()
    .isValid("bad-9", null);
```

có thể kiểm tra phần regex vì implementation hiện tại không dùng context, nhưng nó **bỏ qua** toàn bộ annotation metadata, message interpolation, group selection và provider bootstrap. Vì vậy test provider-level bằng `validator.validateValue(...)` hoặc `validate(...)` mới chứng minh constraint được đăng ký/thi hành đúng trong hệ sinh thái Jakarta.

Nếu controller bind input JSON qua Jackson, cần test JSON deserialize riêng; `@Valid` không thay thế validation của HTTP payload shape hoặc error handling của converter. Nếu form dùng `@ModelAttribute`, cần test cả `WebDataBinder`/`@InitBinder` và `BindingResult`.

## 14. Tình huống biên nên thêm vào bộ kiểm thử

### 14.1. Giá trị null, blank và sai pattern

| Input SKU | `@NotBlank` | `@ValidSku` trong ví dụ | Kết quả khi cùng thuộc Publish |
| --- | --- | --- | --- |
| `null` | Vi phạm | Hợp lệ | 1 violation |
| `""` | Vi phạm | Vi phạm | Có thể có 2 violations |
| `"  "` | Vi phạm | Vi phạm | Có thể có 2 violations |
| `"AB-12"` | Hợp lệ | Vi phạm | 1 violation |
| `"ab-123"` | Hợp lệ | Vi phạm | 1 violation |
| `"AB-123"` | Hợp lệ | Hợp lệ | 0 violations |

Regex là một rule biểu diễn riêng của bài lab. Trong hệ thống thật, cần quyết định case-insensitive hay normalization trước validation, tránh tự `toUpperCase()` mọi string khi domain không cho phép.

### 14.2. Group inheritance và duplicate validations

Nếu một constraint thuộc nhiều groups, provider không nhất thiết thực thi lặp nhiều lần trong một lượt validation khi cùng constraint được yêu cầu qua nhiều groups. Đừng dùng số lần gọi `isValid()` làm business contract nếu không có lý do đặc biệt. Groups chọn subset rules, không dùng để tạo side effects hoặc trigger email.

Nếu có một group kế thừa nhiều nhóm, thứ tự xử lý các constraint trong groups không có sequence vẫn không được định nghĩa. Dùng `@GroupSequence` khi thứ tự là yêu cầu nghiệp vụ thực sự.

### 14.3. Nested null và empty collection

- Reference null: `@Valid` không tạo nested violations; dùng `@NotNull` nếu cần.
- Collection null: `@Valid` không tự coi nó là “phải có”; có thể dùng `@NotNull`.
- Collection rỗng: không có phần tử để cascade; nếu cần ít nhất một phần tử thì dùng `@NotEmpty` hoặc `@Size(min=1)` trên collection với nhóm thích hợp.
- Collection có một phần tử null: cascade bỏ qua phần tử null; nếu null element là sai, có thể dùng `List<@NotNull @Valid Recipient>` với constraints đúng groups.
- Map: có thể cần kiểm tra key/value khác nhau; Jakarta Validation có container element constraints cho generic type arguments và value extractors.
- Cycle trong graph: provider có quy tắc tránh endless recursion, nhưng bạn vẫn cần test cấu trúc phức tạp và thời gian thực thi.

### 14.4. @ConvertGroup và graph khác nhau

Group conversion áp dụng ở **cạnh cascade được khai báo**, không tự đổi nhóm ở root và mọi object cùng kiểu trên toàn graph. Hai fields trỏ tới cùng một Recipient có thể có group conversion khác nhau cho từng association, tùy policy.

Nếu dùng `@ConvertGroup(from=Publish.class,to=Contact.class)` nhưng validate `Draft.class`, rule conversion này **không khớp**; nhóm Draft được lan truyền theo mặc định nếu `@Valid` đang áp dụng. Vì Recipient chỉ có Contact constraints, có thể không tạo violation — điều này là đúng, không phải lỗi provider.

### 14.5. Class-level constraint và cross-field rule

Nếu custom constraint cần so sánh hai fields, đặt nó lên TYPE và triển khai `ConstraintValidator<CustomAnnotation, Item>`. Khi vi phạm, có thể tạo property node để field path chỉ tới thuộc tính phù hợp. Với một validator chỉ kiểm tra SKU, FIELD constraint như trong demo đơn giản hơn.

Đừng dùng một custom validator để truy cập database tùy tiện trong từng `isValid()` vì nó làm tăng chi phí, khó bảo đảm transaction/caching và có thể biến validation thành một nguồn side effects. Quy tắc tồn kho, ownership hoặc quyền thay đổi trạng thái nên được kiểm tra ở domain/service/authorization layer thích hợp.

## 15. Các lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân điển hình | Cách xử lý |
| --- | --- | --- |
| `@ValidSku` không bao giờ chạy | Annotation không có `@Constraint`, retention sai, provider không được bootstrap hoặc group không được chọn | Kiểm tra annotation metadata, `validateValue` và groups |
| `UnexpectedTypeException` | Không có `ConstraintValidator` cho kiểu đích của annotation | Khai báo implementation phù hợp kiểu field |
| `ConstraintDefinitionException` | Annotation constraint thiếu `message/groups/payload` hoặc định nghĩa sai | Theo contract Jakarta Bean Validation |
| Không tìm thấy custom error message | Thiếu `ValidationMessages.properties` hoặc key sai | Kiểm tra resource root/classpath và `getMessageTemplate()` |
| `validator.validate(bean)` bỏ qua Publish | Publish không phải nhóm Default | Gọi `validate(bean, Publish.class)` hoặc dùng sequence đúng |
| `@Valid` trên Recipient nhưng không có lỗi | Nested constraints thuộc Contact còn nhóm đang truyền là Publish | Dùng `@ConvertGroup` nếu policy yêu cầu |
| @ConvertGroup không có hiệu lực | Không gắn cùng `@Valid`, sai nhóm from hoặc đặt ở edge khác | Kiểm tra annotation placement và group conversion rules |
| `ConstraintDeclarationException` | @ConvertGroup thiếu @Valid, trùng from hoặc from là sequence | Sửa declaration theo spec |
| `Ready` chỉ báo title, không báo SKU | Group sequence dừng ở Draft khi Draft fail | Sửa title rồi validate lại hoặc dùng nhiều groups không sequence khi cần tất cả lỗi |
| Test dựa vào thứ tự Set bị flaky | `Set<ConstraintViolation>` không có thứ tự ổn định | So sánh set paths hoặc sort trước |
| Test trùng field làm mất một lỗi | Chỉ so sánh `Set<String> paths` | So thêm annotation type và count |
| `@Valid` không báo Recipient null | Cascade bỏ qua null | Thêm `@NotNull` trên reference |
| Test custom validator đơn lẻ pass nhưng Jakarta provider fail | Unit isValid bỏ qua metadata/bootstrapping | Viết thêm provider-level test |
| Spring MVC chỉ chạy Default | Dùng @Valid thay vì @Validated(Publish.class) | Chọn group ở argument phù hợp |
| Controller có exception khác dự tính | Whole-method validation hoặc AOP @Validated ở class level | Kiểm tra Spring MVC 6.1+ validation path |
| Validation đạt nhưng user không có quyền sửa | Groups không phải authorization | Kiểm tra principal/resource/tenant ở service |
| Validator thay đổi state trong isValid | Custom constraint có side effects | Giữ validation pure, để update trong nghiệp vụ |

## 16. Checklist kiểm thử và review

1. Custom constraint có đúng `@Constraint`, runtime retention, target, `message/groups/payload`?
2. ConstraintValidator hỗ trợ đúng kiểu property và có contract rõ cho null/blank?
3. Đã test giá trị đúng, sai format, null, blank và boundary cases?
4. Đã assert annotation type hoặc message template, không chỉ `hasViolations()`?
5. Đã test `Default`, từng custom group, và multi-group behavior?
6. Khi cần thứ tự, đã dùng `@GroupSequence` và test stop-on-failure?
7. Đã test group sequence sau khi sửa lỗi nhóm đầu?
8. Nested object có `@Valid` ở đúng field/getter/type argument?
9. Đã test một nested object sai **không có @Valid** để chứng minh không tự cascade?
10. Với group conversion, đã test từ nhóm cha sang nhóm con bằng paths cụ thể?
11. Đã test `null` reference và `@NotNull` riêng?
12. Với collection, đã test phần tử invalid, null và empty khi business contract cần?
13. Đã phân biệt `validate` với `validateProperty` và `validateValue`?
14. Assertions có tránh thứ tự của Set và thông báo localized dễ thay đổi không?
15. ValidatorFactory được quản lý và đóng đúng trong test; test có cô lập mutable state?
16. Với MVC, đã test `@Valid` vs `@Validated(groups)` và HTTP status/exception path?
17. Groups có bị hiểu nhầm thành quyền Admin/User không? Có authorization độc lập không?
18. Có regression tests khi thêm field mới, đổi tên group hoặc chuyển sang nested DTO khác?

## 17. Tóm tắt

**Constraint riêng** gồm một annotation khai báo hợp lệ và `ConstraintValidator` cài quy tắc. Test cả giá trị hợp lệ/sai/null cùng metadata để chứng minh provider thật sự thực thi custom constraint.

**Validation groups** chọn tập constraints: không truyền groups thì là `Default`; `@GroupSequence` điều khiển thứ tự và dừng nhóm sau khi nhóm trước vi phạm. Không được nhầm groups với roles hay một cơ chế phân quyền.

**Cascaded validation** chỉ đi vào object con/collection elements khi có `@Valid` phù hợp; reference null bị bỏ qua trừ khi có constraint như `@NotNull`. Nếu object con dùng nhóm khác, `@ConvertGroup` chuyển nhóm ở đúng cạnh cascade. Một bộ JUnit 5 tốt phải kiểm tra riêng từng cơ chế rồi kiểm tra sự kết hợp, đặc biệt qua **property paths, constraint annotation types và group sequence short-circuit**.

## Tài liệu tham khảo chính thức

- Jakarta Bean Validation 3.0 specification — Constraint definitions: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Bean Validation 3.0 — Validation groups, sequences and group conversion (cùng specification, các mục 5.4–5.5): https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Hibernate Validator 8 Reference Guide — Custom constraints, mục 6; Grouping constraints, mục 5: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Jakarta Validation API — `ConstraintValidator`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraintvalidator
- Jakarta Validation API — `Validator`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/validator
- Jakarta Validation API — `GroupSequence`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/groupsequence
- Jakarta Validation API — `ConvertGroup`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/groups/convertgroup
- Spring Framework 6.2 — Bean Validation integration: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2 — MVC validation rules for @Valid and @Validated: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 — Web MVC validator configuration: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html
- JUnit 5 User Guide — Lifecycle and assertions: https://junit.org/junit5/docs/current/user-guide/