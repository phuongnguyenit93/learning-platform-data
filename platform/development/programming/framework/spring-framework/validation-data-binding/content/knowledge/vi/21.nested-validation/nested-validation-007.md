# Optional, unwrapping và kiểm tra giá trị được chứa trong Spring Bean Validation

## 1. Bài toán: kiểm tra đối tượng bọc hay giá trị bên trong?

Trong Java 17+, `Optional<T>` biểu diễn một giá trị **có thể có hoặc không có**. Với Jakarta Bean Validation (thường dùng cùng Spring Framework), ba câu hỏi sau khác nhau:

1. Biến chứa `Optional` có khác `null` không?
2. `Optional` có giá trị bên trong không?
3. Nếu có giá trị, giá trị ấy có hợp lệ, và nếu là Java bean thì các thuộc tính lồng nhau có được kiểm tra không?

Ví dụ `Optional.empty()` là **một đối tượng `Optional` không null nhưng không chứa giá trị**; điều này khác với biến `Optional<String> nickname = null`. Cũng cần phân biệt `Optional.of("   ")`: có phần tử kiểu `String` nhưng nội dung toàn khoảng trắng.

Jakarta Validation cung cấp **value extractor** cho `Optional`, `OptionalInt`, `OptionalLong` và `OptionalDouble`. Nhờ extractor, constraint có thể áp dụng cho **phần tử được bọc**, dù phần tử không phải là một field JavaBean độc lập. Tuy nhiên **không phải mọi constraint đặt trực tiếp lên wrapper đều tự chuyển sang phần tử**.

Trong Spring, `LocalValidatorFactoryBean` thường kết nối Spring với Bean Validation provider (chẳng hạn Hibernate Validator). Các quy tắc dưới đây được thực thi khi một lượt kiểm tra thực sự diễn ra: `jakarta.validation.Validator.validate(bean)`, `@Valid`/`@Validated` tại điểm vào MVC được hỗ trợ, hoặc phương thức Spring validation tương ứng. Annotation đứng một mình không khiến dữ liệu tự được kiểm tra.

**Ý cần nhớ:** *Constraint trên wrapper, constraint trên type argument và cascade `@Valid` là ba việc khác nhau.*

## 2. `Optional` và khái niệm giá trị vắng mặt

| Dữ liệu Java | Wrapper có tồn tại? | Có phần tử? | Phần tử quan sát được qua extractor |
| --- | --- | --- | --- |
| `Optional.of("Alice")` | Có | Có | `"Alice"` |
| `Optional.of("   ")` | Có | Có | `"   "` |
| `Optional.empty()` | Có | Không | `null` theo contract built-in extractor |
| `Optional.ofNullable(null)` | Có | Không | `null` |
| `Optional<String> value = null` | Không | Không thể gọi `isPresent()` | Không gọi extractor cho container null |
| `OptionalInt.of(3)` | Có | Có | `Integer.valueOf(3)` |
| `OptionalInt.empty()` | Có | Không | `null` |

Jakarta Validation yêu cầu extractor của `Optional<T>` đưa giá trị chứa ra `ValueReceiver.value(null, originalValue.orElse(null))`. Tên node là `null` nghĩa là trong `ConstraintViolation.propertyPath` thường không thêm node dành riêng cho lớp `Optional`: nếu `Optional<@NotBlank String> nickname` sai, path thường là `nickname`, không phải `nickname.value`.

**Hệ quả tinh tế:** `Optional<@NotNull String>` có thể đánh dấu `Optional.empty()` là vi phạm, vì extractor đưa ra `null` cho phần tử vắng mặt. Trong khi đó, `@NotNull Optional<String>` kiểm tra chính *đối tượng wrapper*; `Optional.empty()` vẫn là một đối tượng khác null và được chấp nhận.

## 3. Constraint trên wrapper so với constraint trên giá trị bên trong

### Kiểm tra đối tượng `Optional`

```java
@NotNull
private Optional<String> nickname;
```

`@NotNull` nằm trước kiểu field và kiểm tra wrapper. Nó chặn `nickname == null` nhưng **không yêu cầu** `nickname.isPresent()` trả `true`.

### Kiểm tra phần tử được bọc

```java
private Optional<@NotBlank String> nickname;
```

`@NotBlank` nằm bên trong dấu ngoặc generic, ngay trên **`String`**. Nó yêu cầu chuỗi không null, không rỗng và không chỉ có khoảng trắng. Với `Optional.empty()`, extractor cung cấp `null` nên ràng buộc `@NotBlank` thất bại.

### Yêu cầu đồng thời wrapper không null và nội dung hợp lệ

```java
@NotNull
private Optional<@NotBlank String> nickname;
```

Hai vị trí annotation tạo hai rule độc lập: `@NotNull` trên wrapper, `@NotBlank` trên String được lấy ra. Vì `Optional` nên được khởi tạo là `Optional.empty()` thay vì `null`, nhiều ứng dụng chỉ cần chọn một quy ước khởi tạo và kiểm thử đúng luồng binding.

### Ví dụ nhầm vị trí annotation

```java
@NotBlank
private Optional<String> nickname; // Sai cách đặt để kiểm tra String
```

Bộ extractor chuẩn của **`Optional<T>` không được đánh dấu `@UnwrapByDefault`**. Khi không yêu cầu unwrap tường minh, constraint đặt trên wrapper được phân giải cho kiểu `Optional`. `@NotBlank` chuẩn có validator cho `CharSequence`, không có validator chuẩn cho `Optional`, nên provider thường ném `UnexpectedTypeException` (ví dụ Hibernate Validator có thông báo HV000030).

**Cách sửa ưu tiên:** dùng `Optional<@NotBlank String>`. Nhìn ngay ở khai báo sẽ hiểu constraint dành cho phần tử bên trong; không cần chỉnh provider hoặc ghi custom validator nếu chỉ dùng `Optional` chuẩn.

## 4. Bảng chân trị: null, empty, chuỗi trắng và chuỗi hợp lệ

Xét ba khai báo khác nhau:

- A: `@NotNull Optional<String> value`
- B: `Optional<@NotNull String> value`
- C: `Optional<@NotBlank String> value`

| Giá trị wrapper | A: wrapper không null | B: phần tử không null | C: phần tử không blank |
| --- | --- | --- | --- |
| `Optional.of("ok")` | Đạt | Đạt | Đạt |
| `Optional.of("  ")` | Đạt | Đạt | **Lỗi** |
| `Optional.of("")` | Đạt | Đạt | **Lỗi** |
| `Optional.empty()` | Đạt | **Lỗi** | **Lỗi** |
| `null` | **Lỗi** | Không kiểm tra phần tử | Không kiểm tra phần tử |

Với wrapper `null`, built-in extractor không được gọi; nếu muốn lỗi rõ ràng cho wrapper, hãy thêm constraint ở **wrapper**. Ngược lại, nếu một field là *thật sự tùy chọn*, thì **không nên** gắn `@NotNull` hoặc `@NotBlank` lên phần tử trừ khi nghiệp vụ muốn coi `Optional.empty()` là lỗi.

Ví dụ field tùy chọn, nhưng nếu có thì chỉ được dài tối đa 30 ký tự:

```java
private Optional<@Size(max = 30) String> displayName =
        Optional.empty();
```

`@Size` cho phép `null`, nên `Optional.empty()` **đạt**, `Optional.of("")` cũng đạt theo ràng buộc max-only; `Optional.of("...")` quá 30 ký tự bị lỗi. Đây là thiết kế “không nhập thì được bỏ qua; nhập thì giới hạn độ dài”.

Nếu nghiệp vụ muốn *không được gửi chuỗi trắng nhưng vẫn cho phép vắng mặt*, có thể dùng custom constraint cho `String` với `null` được chấp nhận và chuỗi blank bị từ chối, hoặc chuẩn hóa input trước rồi áp dụng các rule rõ ràng. `@NotBlank` vốn từ chối null, nên không diễn đạt trực tiếp rule “empty optional được phép nhưng blank string không được phép”.

## 5. Cascade `@Valid`: kiểm tra Java bean nằm trong `Optional`

Giả sử có:

```java
public class Address {
    @NotBlank
    private String city;
}
```

Khi DTO có field:

```java
private Optional<@Valid Address> deliveryAddress;
```

`@Valid` đặt tại type argument thông báo rằng **nếu có `Address`**, Bean Validation sẽ đi tiếp vào object đó và kiểm tra `Address.city`. Ví dụ:

- `Optional.of(new Address("Hanoi"))`: constraint `city` đạt.
- `Optional.of(new Address(""))`: cascade phát hiện `city` vi phạm.
- `Optional.empty()`: phần tử được extractor báo là null; **cascade bỏ qua null**, nên không có lỗi riêng từ `@Valid`.
- `deliveryAddress == null`: không có phần tử để cascade; muốn yêu cầu wrapper tồn tại, thêm `@NotNull` ngoài wrapper.

Nếu mục tiêu là **phải có địa chỉ và địa chỉ hợp lệ**, dùng:

```java
@NotNull
private Optional<@NotNull @Valid Address> deliveryAddress;
```

Constraint ngoài buộc wrapper khác null; `@NotNull` bên trong buộc phần tử phải hiện diện; `@Valid` duyệt vào các thuộc tính của `Address`. Trong thực tế, với field bắt buộc luôn có một giá trị, một field `@NotNull @Valid Address deliveryAddress` (không dùng Optional) thường dễ bind và dễ đọc hơn.

**Không đặt `@Valid` đồng thời lên wrapper và type argument** của cùng container. Đặc tả khuyến nghị chỉ chọn một chỗ để tránh kiểm tra cascade trùng lặp; với generic container, đặt ở type argument làm ý đồ dễ thấy hơn.

`@Valid` là **marker cascade, không phải constraint bắt buộc**. Nó không thay thế `@NotNull` và không tự chạy nếu không có một lượt Bean Validation thực sự.

## 6. Cơ chế value extractor bên dưới

Jakarta Validation 2.0+ (namespace `jakarta.validation.*` trên Spring Framework 6+/Boot 3+) hỗ trợ **container element constraints** thông qua `ValueExtractor<T>`.

Ví dụ triển khai đúng ý nghĩa của built-in extractor dành cho `Optional`:

```java
import java.util.Optional;

import jakarta.validation.valueextraction.ExtractedValue;
import jakarta.validation.valueextraction.ValueExtractor;

public final class OptionalExtractorExample
        implements ValueExtractor<Optional<@ExtractedValue ?>> {

    @Override
    public void extractValues(
            Optional<?> originalValue, ValueReceiver receiver) {
        receiver.value(null, originalValue.orElse(null));
    }
}
```

Đây là **mã mô phỏng cách extractor hoạt động**. **Không đăng ký lại extractor này trong ứng dụng bình thường**, vì Jakarta Validation provider đã cung cấp extractor chuẩn cho `Optional` và đăng ký trùng có thể tạo xung đột.

Ý nghĩa hai tham số của `receiver.value(...)`:

1. **`nodeName` = null**: không tạo thêm node container element vào property path. Với wrapper một giá trị, lỗi trên phần tử thường gắn vào tên property của wrapper.
2. **`element = originalValue.orElse(null)`**: đưa giá trị đã mở wrapper cho constraint/cascade xử lý; `Optional.empty()` trở thành `null`.

Bên trong provider, extractor được chọn theo kiểu container và vị trí type argument chứa constraint. Đối với container lồng nhau, provider gọi nhiều extractor theo thứ tự cần thiết:

```text
OrderForm
  |
  +-- List<Optional<@NotBlank String>> codes
          |
          +-- List extractor: lấy phần tử [0], [1], ...
                       |
                       +-- Optional extractor: lấy String hoặc null
                                     |
                                     +-- @NotBlank kiểm tra String
```

Đó là lý do `List<Optional<@NotBlank String>>` có thể kiểm tra phần tử hai tầng mà không viết vòng lặp thủ công. Một wrapper tùy biến không có extractor thường cần triển khai `ValueExtractor` của riêng nó.

## 7. `@UnwrapByDefault`, implicit unwrapping và explicit unwrapping

**Unwrapping** là việc yêu cầu Bean Validation áp dụng constraint trên **phần tử được bọc**, thay vì trực tiếp trên chính đối tượng wrapper. Có ba trường hợp cần phân biệt:

| Trường hợp | Cơ chế | Ví dụ |
| --- | --- | --- |
| Constraint đặt ngay trên type argument | Extractor được chọn do vị trí annotation | `Optional<@NotBlank String>` |
| Constraint đặt trên wrapper có extractor gắn `@UnwrapByDefault` | **Implicit unwrapping** | `@Min(1) OptionalInt count` |
| Constraint đặt trên wrapper và dùng payload `Unwrapping.Unwrap` | **Explicit unwrapping** | `@NotBlank(payload = Unwrapping.Unwrap.class) Optional<String> code` |

Đặc tả yêu cầu extractor tích hợp cho `OptionalInt`, `OptionalLong` và `OptionalDouble` có `@UnwrapByDefault`. Vì thế:

```java
@Min(1)
private OptionalInt count;
```

`@Min` không chạy trên class `OptionalInt`, mà được provider áp vào kiểu `Integer` được extractor lấy ra. `OptionalInt.of(0)` không đạt, `OptionalInt.of(2)` đạt. **`OptionalInt.empty()` được extractor báo là null, trong khi `@Min` coi null là hợp lệ**, nên `empty()` không bị `@Min` từ chối.

Với `OptionalDouble`, chọn constraint hỗ trợ kiểu `Double` như `@Positive`; đừng dựa vào việc `@Min` được hỗ trợ cho `double` ở mọi provider (đặc tả không bắt buộc hỗ trợ floating point cho `@Min`/`@Max`).

### Explicit unwrap bằng payload

Khi muốn giữ annotation trên wrapper generic vì lý do tương thích cấu trúc, có thể dùng:

```java
@NotBlank(payload = Unwrapping.Unwrap.class)
private Optional<String> code;
```

Với extractor `Optional` chuẩn, `Unwrapping.Unwrap` yêu cầu xử lý giá trị String bên trong. Đây là API Jakarta (`jakarta.validation.valueextraction.Unwrapping`), không phải Java `Optional.orElse(...)` hay `jakarta.validation.Validator.unwrap(Class)`.

**Ưu tiên:** khi viết code mới, `Optional<@NotBlank String>` rõ nghĩa hơn, không cần payload. Explicit unwrap hữu ích khi muốn chỉ định mục tiêu kiểm tra của một constraint đã đặt ở declaration level.

### Ngăn unwrap bằng `Unwrapping.Skip`

Nếu extractor được đánh dấu `@UnwrapByDefault`, có thể buộc constraint kiểm tra **wrapper** bằng:

```java
@NotNull(payload = Unwrapping.Skip.class)
private OptionalInt count;
```

Điều này chỉ kiểm tra biến `count` có khác `null` hay không. `OptionalInt.empty()` là một wrapper khác null nên **đạt**. Trong khi đó, **`@NotNull OptionalInt count`** (không có Skip) sẽ **unwrap ngầm**, làm `OptionalInt.empty()` trở thành `null` để `@NotNull` đánh giá và báo lỗi.

**Không dùng đồng thời** `Unwrapping.Unwrap` và `Unwrapping.Skip` cho cùng constraint: đó là cấu hình mâu thuẫn, có thể gây `ConstraintDeclarationException`.

## 8. Giá trị vắng mặt với `OptionalInt`, `OptionalLong`, `OptionalDouble`

Ba lớp chuyên biệt không có generic type argument:

```java
@Min(1)
private OptionalInt seats;

@Positive
private OptionalLong bytes;

@Positive
private OptionalDouble ratio;
```

Extractor của chúng gắn `@ExtractedValue(type = Integer.class)`, `Long.class` và `Double.class` tương ứng, đồng thời `@UnwrapByDefault`. Vì vậy các constraint declaration-level theo kiểu số có thể chạy trên phần tử.

| Dữ liệu | Constraint | Kết quả |
| --- | --- | --- |
| `OptionalInt.of(0)` | `@Min(1)` | Vi phạm |
| `OptionalInt.of(3)` | `@Min(1)` | Đạt |
| `OptionalInt.empty()` | `@Min(1)` | Đạt do phần tử null |
| `OptionalInt.empty()` | `@NotNull` | Vi phạm sau implicit unwrap |
| `OptionalInt.empty()` | `@NotNull(payload=Unwrapping.Skip.class)` | Đạt vì wrapper khác null |
| `OptionalLong.of(-1)` | `@Positive` | Vi phạm |
| `OptionalDouble.of(0.5)` | `@Positive` | Đạt |

Dùng `OptionalDouble` không có nghĩa đã giải quyết rủi ro chính xác số thực; với tiền tệ hay quy tắc giá trị thập phân có độ chính xác cao, nên chọn `BigDecimal` và thiết kế nullable/optional cho rõ ràng.

## 9. Ví dụ chạy được: Java 17 + Spring Boot + Bean Validation

Ví dụ sau chứng minh các quy tắc bằng **một chương trình hoàn chỉnh**: kiểm tra wrapper, phần tử, cascade và OptionalInt; đồng thời minh họa explicit unwrap và sai vị trí `@NotBlank`. Sử dụng Spring Boot 3.5.8 (bản đã phát hành) để cố định version trong ví dụ học tập, Maven và JDK 17+.

Cấu trúc:

```text
optional-validation-demo/
├── pom.xml
└── src/main/java/demo/OptionalValidationDemo.java
```

### File `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.8</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>optional-validation-demo</artifactId>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### File `src/main/java/demo/OptionalValidationDemo.java`

```java
package demo;

import java.util.Comparator;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.UnexpectedTypeException;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.Valid;
import jakarta.validation.valueextraction.Unwrapping;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OptionalValidationDemo {

    public static void main(String[] args) {
        SpringApplication.run(OptionalValidationDemo.class, args);
    }

    @Bean
    ApplicationRunner demonstrate(jakarta.validation.Validator validator) {
        return args -> {
            Profile good = new Profile(
                    Optional.empty(),
                    Optional.of("Mai"),
                    Optional.of(new Address("Ha Noi")),
                    OptionalInt.of(2));
            print("Good", validator.validate(good));

            Profile absent = new Profile(
                    Optional.empty(),
                    Optional.empty(),
                    Optional.empty(),
                    OptionalInt.empty());
            print("Absent", validator.validate(absent));

            Profile invalid = new Profile(
                    Optional.empty(),
                    Optional.of("   "),
                    Optional.of(new Address("")),
                    OptionalInt.of(0));
            print("Invalid", validator.validate(invalid));

            Profile nullWrapper = new Profile(
                    null,
                    Optional.of("Mai"),
                    Optional.empty(),
                    OptionalInt.of(2));
            print("Null wrapper", validator.validate(nullWrapper));

            print("OptionalInt required",
                    validator.validate(
                            new PrimitiveRequired(OptionalInt.empty())));

            print("Explicit unwrap",
                    validator.validate(
                            new ExplicitUnwrap(Optional.of(" "))));

            try {
                validator.validate(new IncorrectPlacement());
            } catch (UnexpectedTypeException ex) {
                System.out.println("Wrong placement: "
                        + ex.getClass().getSimpleName());
            }
        };
    }

    static void print(
            String title,
            Set<? extends ConstraintViolation<?>> violations) {

        String paths = violations.stream()
                .map(v -> v.getPropertyPath().toString())
                .sorted()
                .collect(Collectors.joining(", "));
        System.out.println(title + ": " + violations.size()
                + (paths.isEmpty() ? "" : " [" + paths + "]"));
    }

    public static final class Profile {
        @NotNull
        private final Optional<String> wrapper;

        private final Optional<@NotBlank String> nickname;

        private final Optional<@Valid Address> address;

        @Min(1)
        private final OptionalInt seats;

        public Profile(Optional<String> wrapper,
                       Optional<String> nickname,
                       Optional<Address> address,
                       OptionalInt seats) {
            this.wrapper = wrapper;
            this.nickname = nickname;
            this.address = address;
            this.seats = seats;
        }
    }

    public static final class Address {
        @NotBlank
        private final String city;

        public Address(String city) {
            this.city = city;
        }
    }

    public static final class PrimitiveRequired {
        // OptionalInt được unwrap ngầm vì @UnwrapByDefault.
        @NotNull
        private final OptionalInt count;

        public PrimitiveRequired(OptionalInt count) {
            this.count = count;
        }
    }

    public static final class ExplicitUnwrap {
        @NotBlank(payload = Unwrapping.Unwrap.class)
        private final Optional<String> code;

        public ExplicitUnwrap(Optional<String> code) {
            this.code = code;
        }
    }

    public static final class IncorrectPlacement {
        // Không có @UnwrapByDefault trên Optional<T>.
        @NotBlank
        private final Optional<String> code = Optional.of("ok");
    }
}
```

Có thể bỏ import `Comparator` vì chương trình chỉ dùng `sorted()` trên stream; Java cho phép import không sử dụng, nhưng trong code review có thể xóa import đó. Các field `private final` được provider đọc theo field-access của Bean Validation; không bắt buộc khai báo getter cho mỗi field để dùng field constraints.

Biên dịch và chạy tại thư mục chứa `pom.xml`:

```bash
mvn spring-boot:run
```

Bỏ qua các log khởi động Spring Boot; các dòng `System.out.println` do chương trình tạo ra:

```text
Good: 0
Absent: 1 [nickname]
Invalid: 3 [address.city, nickname, seats]
Null wrapper: 1 [wrapper]
OptionalInt required: 1 [count]
Explicit unwrap: 1 [code]
Wrong placement: UnexpectedTypeException
```

**Phân tích từng kết quả:**

1. **Good: 0** — `wrapper = Optional.empty()` vẫn khác null nên đạt `@NotNull` đặt trên wrapper; `nickname` có String hợp lệ; `address.city` hợp lệ; `seats = 2` đạt `@Min(1)`.
2. **Absent: 1 [nickname]** — optional wrapper còn tồn tại, nhưng `Optional<@NotBlank String>` có phần tử null nên thất bại. `address = Optional.empty()` không tạo vi phạm cascade, `seats = OptionalInt.empty()` đạt `@Min` vì giá trị được unwrap thành null.
3. **Invalid: 3** — nickname là chuỗi trắng, địa chỉ được cascade có `city = ""`, số ghế 0 không đạt `@Min(1)`. Các path được sắp xếp để kết quả hiển thị ổn định.
4. **Null wrapper: 1** — `@NotNull` trên đối tượng `Optional<String> wrapper` từ chối null, không cần unwrap.
5. **OptionalInt required: 1** — `@NotNull OptionalInt count` unwrap ngầm, OptionalInt.empty() được đưa ra dưới dạng null và bị từ chối.
6. **Explicit unwrap: 1** — `Unwrapping.Unwrap` buộc `@NotBlank` đánh giá String bên trong Optional; chuỗi trắng không hợp lệ.
7. **Wrong placement** — thiếu explicit unwrap hoặc type-use annotation, `@NotBlank` bị áp vào kiểu `Optional<String>` và provider không tìm thấy validator thích hợp.

Ví dụ cố ý đặt một annotation sai kiểu ở class riêng để minh họa `UnexpectedTypeException`. Trong ứng dụng production, **sửa `IncorrectPlacement` thành `Optional<@NotBlank String>` hoặc dùng explicit unwrap phù hợp**; không giữ class sai chỉ để bắt exception ở runtime.

## 10. `@NotNull` và `@Valid` trong dữ liệu lồng nhiều tầng

Container element constraints có thể kết hợp với nhau:

```java
private List<Optional<@NotBlank String>> aliases;

private Map<@NotBlank String,
            Optional<@NotNull @Valid Address>> addressByCode;
```

Cần import `java.util.List` và `Map`. Trong khai báo đầu:

1. `List` extractor lấy từng phần tử Optional.
2. `Optional` extractor lấy String hoặc null.
3. `@NotBlank` đánh giá String.

Trong khai báo sau:

1. Map key extractor áp `@NotBlank` lên từng key String.
2. Map value extractor lấy Optional ở từng entry.
3. Optional extractor lấy Address hoặc null.
4. `@NotNull` buộc mỗi Optional chứa Address, và `@Valid` cascade vào Address.

Lưu ý: với `List<Optional<@NotBlank String>>`, bản thân List có thể là null hoặc rỗng mà không nhất thiết vi phạm; muốn yêu cầu List có phần tử, thêm `@NotEmpty`/`@NotNull` trên **List**. Nếu muốn mỗi Optional wrapper trong List không được null, đặt `@NotNull` trên **type argument Optional**:

```java
@NotEmpty
private List<@NotNull Optional<@NotBlank String>> aliases;
```

Không đặt `@NotBlank` trên `List` hay trên `Optional` mà thiếu unwrap. Annotation phải được đặt tại đúng **đối tượng cần kiểm tra**, và provider phải có extractor cho các lớp container trung gian.

## 11. Tự tạo `ValueExtractor` cho wrapper riêng

Giả sử ứng dụng có một kiểu bọc như `Box<T>`:

```java
public record Box<T>(T value) {}
```

Nếu dùng `Box<@NotBlank String>` mà provider không biết cách trích `T`, Bean Validation không thể tiếp cận giá trị. Ta có thể tạo extractor:

```java
import jakarta.validation.valueextraction.ExtractedValue;
import jakarta.validation.valueextraction.ValueExtractor;

public final class BoxValueExtractor
        implements ValueExtractor<Box<@ExtractedValue ?>> {

    @Override
    public void extractValues(
            Box<?> container, ValueReceiver receiver) {
        receiver.value(null, container.value());
    }
}
```

Hai đoạn code **minh họa từng file độc lập**; nếu lưu thành Java source, đặt `Box.java` và `BoxValueExtractor.java` trong cùng package. `@ExtractedValue` chỉ rõ **type argument duy nhất** được extract; đối với generic wrapper thông thường, phải dùng unbounded wildcard `?` tại nơi đánh dấu. Không gắn `@ExtractedValue` vào nhiều type arguments trong một extractor.

Đăng ký trong Spring qua `LocalValidatorFactoryBean` trước khi bootstrap provider, ví dụ với cấu hình Spring Framework/Boot đã hiểu rõ bean validator của ứng dụng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class ValidationConfig {
    @Bean
    LocalValidatorFactoryBean validator() {
        LocalValidatorFactoryBean factory =
                new LocalValidatorFactoryBean();
        factory.setConfigurationInitializer(
                configuration -> configuration.addValueExtractor(
                        new BoxValueExtractor()));
        return factory;
    }
}
```

Đây là **lớp cấu hình minh họa, không phải chương trình có `main`**; cần bảo đảm `Box`/`BoxValueExtractor` nằm trong package/import phù hợp và chỉ có một cấu hình validator được chọn cho luồng MVC/service thực tế. `setConfigurationInitializer(...)` là API của Spring `LocalValidatorFactoryBean` để tùy chỉnh `jakarta.validation.Configuration<?>` trước khi provider xây dựng factory.

Có thể đăng ký extractor theo cơ chế `META-INF/services/jakarta.validation.valueextraction.ValueExtractor`, `validation.xml` hoặc bằng API `Configuration.addValueExtractor(...)` theo mức ưu tiên của Jakarta Validation. Một extractor chỉ nên được đăng ký một cách có chủ đích; việc trùng extractor cho cùng cặp type/type-argument hoặc nhiều extractor cùng phù hợp có thể sinh lỗi khai báo/giải quyết extractor.

**Khi nào dùng `@UnwrapByDefault` ở extractor riêng?** Chỉ khi muốn constraint đặt ở **declaration level trên chính Box** được tự động chuyển vào giá trị T. Nếu không gắn, người dùng vẫn có thể viết `Box<@NotBlank String>` với constraint trên type argument. Gắn `@UnwrapByDefault` cần được cân nhắc vì có thể khiến `@NotNull Box<T>` kiểm tra phần tử thay vì kiểm tra wrapper, tạo khác biệt rất khó nhận ra.

## 12. Tìm đúng loại exception

| Lỗi | Ý nghĩa điển hình | Hướng xử lý |
| --- | --- | --- |
| `UnexpectedTypeException` | Không có `ConstraintValidator` phù hợp cho kiểu bị kiểm tra | Đổi vị trí annotation/type hoặc yêu cầu unwrap rõ ràng |
| `ConstraintDeclarationException` | Khai báo/cách giải quyết constraint hoặc extractor không hợp lệ | Kiểm tra type argument, cấu hình unwrap, sự mơ hồ |
| `ValueExtractorDefinitionException` | Implementation extractor không đúng định nghĩa | Kiểm tra `@ExtractedValue` và generic wildcard |
| `ValueExtractorDeclarationException` | Cấu hình/đăng ký extractor bất hợp lệ, ví dụ nhiều extractor trùng | Kiểm tra đăng ký service/XML/API |
| `ConstraintViolation` | Đã tìm đúng validator nhưng giá trị không đạt rule | Sửa dữ liệu hoặc contract nghiệp vụ |
| `MethodArgumentNotValidException` (Spring MVC) | MVC validate DTO và có binding/validation errors | Đọc `BindingResult` và trả lỗi phù hợp |

Ví dụ sai thường gặp:

```java
@NotBlank
Optional<String> code;
```

Nếu provider không unwrap ngầm Optional generic, `@NotBlank` nhắm tới `Optional` nên phát sinh `UnexpectedTypeException`. Sửa:

```java
Optional<@NotBlank String> code;
```

Khi một custom extractor cho `Box` thiếu hoặc hai extractor cùng phù hợp, lỗi thường nằm ở **khâu tìm extractor**, không nhất thiết là `UnexpectedTypeException`. Đọc chính xác exception class, property path và stack trace; không quy mọi lỗi chung là “giá trị null”.

## 13. Spring MVC: binding Optional và Bean Validation là hai bước khác nhau

Trong Spring MVC, `@RequestParam Optional<String> keyword` là một cơ chế **binding tham số tùy chọn**. Nó không đồng nghĩa tự chạy `@NotBlank` trên String bên trong ở mọi cấu hình. Bean Validation cần một điểm kích hoạt như `@Valid`/`@Validated` trong luồng MVC hỗ trợ, hoặc một lượt validate tường minh.

Ví dụ DTO dùng type-use constraints:

```java
public class SearchFilter {
    @NotNull
    private Optional<@Size(max = 40) String> keyword =
            Optional.empty();

    private Optional<@Positive Integer> minPrice =
            Optional.empty();
}
```

Đây là class minh họa. Nó cần binding/deserialization tạo đúng kiểu `Optional`, sau đó có entry point thực thi Bean Validation. Với JSON `@RequestBody`, Jackson cần hỗ trợ `Optional` (ví dụ module `jackson-datatype-jdk8` và cấu hình object mapper phù hợp); **Jackson chỉ chuyển JSON sang DTO, còn Bean Validation chạy sau khi được framework yêu cầu**. Không xem `Optional.empty()`, JSON thiếu field và JSON `null` là ba giá trị giống nhau trong mọi ObjectMapper: hành vi phụ thuộc cấu hình deserialization và constructor/setter được dùng.

Controller minh họa:

```java
@PostMapping("/search")
public ResponseEntity<?> search(
        @Valid @RequestBody SearchFilter filter,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest()
                .body(errors.getFieldErrors().stream()
                        .map(e -> e.getField() + ": "
                                + e.getDefaultMessage())
                        .toList());
    }

    return ResponseEntity.ok().build();
}
```

Đây là **phương thức controller minh họa**, cần import Spring MVC/HTTP, `jakarta.validation.Valid` và đặt trong controller thực tế. `BindingResult` phải nằm ngay sau tham số được validate ở những chữ ký hỗ trợ. Provider phải có extractor tương ứng; Spring `LocalValidatorFactoryBean` thông thường không cần bạn tự đăng ký extractor cho `Optional`.

**Lưu ý thiết kế:** Java `Optional` chủ yếu được dùng rõ ràng ở **API trả về** để mô tả có/không có kết quả. Với DTO cần bind từ JSON/form, field `Optional` không luôn là lựa chọn đơn giản nhất; có thể dùng field nullable cùng constraint rõ ràng và chuyển sang `Optional` ở service boundary. Chọn theo hợp đồng dữ liệu và hành vi Jackson/conversion thực tế.

## 14. Groups, cascaded validation và null semantics

Group vẫn được áp dụng khi constraint nằm trong generic container:

```java
public interface OnCreate {}

public class CreateProfile {
    private Optional<@NotBlank(groups = OnCreate.class) String> name;
}
```

Gọi `validator.validate(profile, OnCreate.class)` sẽ kiểm tra `@NotBlank` của nhóm `OnCreate` trên String được extractor lấy ra. Nếu chỉ gọi `validator.validate(profile)` (nhóm mặc định), constraint thuộc nhóm khác có thể không được đánh giá. Cần bảo đảm field `name` không null hoặc thêm constraint trên wrapper nếu ứng dụng muốn bắt lỗi trường hợp đó.

Đối với `Optional<@Valid Address>`, cascade sẽ áp dụng group đang dùng theo quy tắc Bean Validation. Nếu cần chuyển nhóm ở boundary container, Jakarta hỗ trợ `@ConvertGroup` trên phần tử cascade theo các hạn chế của đặc tả. Không tự suy rằng `@Valid` khiến mọi nhóm constraint của Address đều chạy.

**Null policy đáng ghi thành test:**

- Bắt buộc wrapper? `@NotNull Optional<T>`.
- Bắt buộc có phần tử? `Optional<@NotNull T>` (nếu extractor cho loại container đưa absent thành null).
- Phần tử tùy chọn nhưng nếu có thì giới hạn độ dài? `Optional<@Size(max=40) String>`.
- Bắt buộc có phần tử không trắng? `Optional<@NotBlank String>`.
- Chỉ kiểm tra bean khi có? `Optional<@Valid Address>`.
- Vừa yêu cầu có bean vừa cascade? `Optional<@NotNull @Valid Address>`, kết hợp `@NotNull` ngoài wrapper khi cần.

Đặt rule ở đúng vị trí giúp mô hình biểu thị rõ *missing*, *null*, *empty String* và *invalid nested object*.

## 15. Kiểm thử những ca dễ sai

1. `Optional.empty()` với `Optional<@NotNull String>` → có violation.
2. `Optional.empty()` với `Optional<@Size(max=10) String>` → không có violation do `@Size` chấp nhận null.
3. `Optional.of(" ")` với `Optional<@NotBlank String>` → có violation.
4. `null` wrapper với `@NotNull Optional<String>` → có violation.
5. `Optional.empty()` với `Optional<@Valid Address>` → không có cascade violation.
6. `Optional.of(Address(city=""))` với `Optional<@Valid Address>` → có violation trên `city`.
7. `OptionalInt.empty()` với `@Min(1)` → thường không có violation theo chuẩn, vì số được extract thành null.
8. `OptionalInt.empty()` với `@NotNull` → violation do implicit unwrap.
9. `OptionalInt.empty()` với `@NotNull(payload=Unwrapping.Skip.class)` → không violation nếu wrapper khác null.
10. `@NotBlank Optional<String>` không có explicit unwrap → cần phát hiện `UnexpectedTypeException` và sửa khai báo.
11. `List<Optional<@NotBlank String>>` → test phần tử thứ hai là `Optional.of("")`; kiểm tra path có thể bao gồm index.
12. Custom `Box<T>` → test có/không có extractor và việc cấu hình `@UnwrapByDefault` có thay ngữ nghĩa `@NotNull` không.
13. MVC JSON → test cả request thiếu trường, `null`, chuỗi trống, chuỗi trắng và chuỗi hợp lệ.
14. Method/DTO validation → test đúng qua Spring-managed entry point hoặc gọi `jakarta.validation.Validator` trực tiếp; đừng nghĩ annotation sẽ tự chạy chỉ vì object đã được tạo.

**Để test ổn định**, kiểm tra tập property path/constraint type thay vì vị trí đầu tiên trong `Set<ConstraintViolation<?>>`, vì thứ tự không được bảo đảm. Một số provider cung cấp path chi tiết hơn cho list/map với node như `<list element>`, `<map key>`, `<map value>`; test nên bám vào contract cần bảo đảm và provider bạn sử dụng.

## 16. Những lỗi thiết kế thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Sửa như thế nào |
| --- | --- | --- |
| `@NotBlank Optional<String>` gây HV000030 | Constraint nhắm vào wrapper không được unwrap mặc định | Chuyển thành `Optional<@NotBlank String>` |
| `@NotNull Optional<String>` không phát hiện `Optional.empty()` | `@NotNull` chỉ kiểm tra wrapper | Nếu bắt buộc có phần tử, dùng `Optional<@NotNull String>` |
| `Optional<@Valid Address>` không báo lỗi khi rỗng | Cascade không coi null là vi phạm | Thêm `@NotNull` vào type argument |
| `Optional<@Size(max=10) String>` không báo lỗi khi absent | `@Size` xem null là hợp lệ | Kết hợp `@NotNull` bên trong nếu phải hiện diện |
| `@Min(1) OptionalInt` cho phép empty | Implicit unwrap được null và `@Min` cho qua null | Thêm `@NotNull` với ngữ nghĩa unwrap nếu cần bắt buộc |
| Dùng `Unwrapping.Skip` mà tưởng nó buộc có nội dung | Skip buộc rule áp vào wrapper | Dùng `@NotNull`/constraint trên phần tử tùy ý định |
| Custom Box không được kiểm tra | Chưa có/đăng ký sai `ValueExtractor` | Khai báo `ValueExtractor<Box<@ExtractedValue ?>>` và đăng ký một lần |
| Trùng extractor hoặc extractor không hợp lệ | Lỗi cấu hình ValueExtractor | Rà service loader, `validation.xml`, API registration |
| Spring MVC không báo lỗi | Chưa kích hoạt validation hoặc DTO chưa bind như mong đợi | Kiểm tra `@Valid`, validator bean, Jackson JDK8 module, test thực tế |
| `Optional` field là null sau deserialize | Cấu hình setter/constructor/deserializer không khởi tạo như dự tính | Chuẩn hóa input, thiết kế DTO rõ contract, test absent/null |
| Cascade bị kiểm tra hai lần | Gắn `@Valid` vừa wrapper vừa type argument | Chỉ dùng một vị trí cascade đúng ý đồ |
| API và database dùng ngữ nghĩa missing khác nhau | Trộn “vắng mặt”, “null” và “xóa field” | Xác định rõ PATCH/PUT và chính sách update |

Không sửa lỗi về vị trí annotation bằng cách bắt mọi `ValidationException` rồi bỏ qua; làm vậy có thể biến lỗi lập trình thành dữ liệu không được kiểm tra.

## 17. Câu hỏi tự kiểm tra

**1. `Optional.empty()` có bị `@NotNull Optional<String>` từ chối không?**  
Không, vì wrapper khác null. Nếu muốn bắt buộc phần tử, dùng constraint trên type argument.

**2. `Optional<@NotNull String>` có từ chối `Optional.empty()` không?**  
Có. Built-in extractor chuyển sự vắng mặt thành phần tử `null`; `@NotNull` trên phần tử không đạt.

**3. `@NotBlank Optional<String>` và `Optional<@NotBlank String>` có tương đương không?**  
Không. Khai báo đầu nhắm đến wrapper và không được unwrap ngầm theo extractor generic chuẩn; khai báo sau nhắm đến String.

**4. `@Min(1) OptionalInt.of(0)` kiểm tra trên kiểu nào?**  
Giá trị được trích ra dưới dạng `Integer` nhờ `@UnwrapByDefault` trên extractor `OptionalInt`.

**5. `@Min(1) OptionalInt.empty()` có từ chối empty không?**  
Không theo quy tắc chuẩn, vì phần tử được extractor báo null và `@Min` chấp nhận null. Dùng thêm `@NotNull` với ngữ nghĩa unwrap để bắt buộc có số.

**6. `Optional<@Valid Address>` có yêu cầu có địa chỉ không?**  
Không. `@Valid` chỉ cascade khi có đối tượng. `@NotNull` tại type argument mới buộc phần tử hiện diện.

**7. Khi nào cần tự viết `ValueExtractor`?**  
Khi dùng container riêng như `Box<T>` mà provider chưa có extractor tương ứng cho type argument cần validate.

**8. `Unwrapping.Unwrap` có giống `validator.unwrap(...)` không?**  
Không. `Unwrapping.Unwrap` là payload điều khiển áp dụng constraint lên phần tử; `Validator.unwrap(Class)` là API truy cập chức năng/đối tượng cụ thể của provider.

**9. Có phải mọi JSON field `Optional` luôn được Jackson xử lý cùng cách?**  
Không. Cần xem Jackson JDK 8 module và cấu hình deserializer; Bean Validation là một bước riêng sau khi DTO được tạo.

**Ghi nhớ:** *Đặt constraint đúng vị trí cần kiểm tra; hiểu extractor làm gì với Optional.empty(); chỉ dùng implicit unwrap khi extractor khai báo cho phép; dùng @Valid để cascade, dùng constraint để yêu cầu tồn tại.*

## Tài liệu tham khảo chính thức

- Jakarta Validation 3.1 specification — Container element constraints / implicit unwrapping / value extractors: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Jakarta Validation API — ValueExtractor: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/valueextraction/ValueExtractor.html
- Jakarta Validation API — Unwrapping: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/valueextraction/Unwrapping.html
- Jakarta Validation API — UnwrapByDefault: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/valueextraction/UnwrapByDefault.html
- Hibernate Validator documentation — Container element constraints and value extraction: https://hibernate.org/validator/documentation/
- Spring Framework Reference — Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework API — LocalValidatorFactoryBean: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html
- Spring Framework Reference — MVC validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
