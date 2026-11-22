# @ExtractedValue, @UnwrapByDefault và chiến lược unwrapping trong Jakarta Validation

## 1. Mục tiêu và bài toán thực tế

Trong ứng dụng Spring Framework, Bean Validation (Jakarta Validation) thường kiểm tra thuộc tính DTO thông qua `@NotBlank`, `@Min`, `@Valid`, v.v. Nhưng giá trị nghiệp vụ không phải lúc nào cũng nằm trực tiếp trong một `String` hay `int`: nó có thể được bọc trong `OptionalInt`, `List<T>`, `Map<K, V>` hoặc một kiểu tự định nghĩa như `Box<T>`.

Giả sử `Box<String>` giữ mã khách hàng. Có ba điều hoàn toàn khác nhau mà ta có thể muốn xác minh:

- **Bản thân container có tồn tại?** `box != null`: kiểm tra đối tượng `Box`.
- **Giá trị bên trong có hợp lệ?** `box.value()` phải không trống hoặc đúng định dạng: kiểm tra *wrapped value*.
- **Đối tượng bên trong có các thuộc tính hợp lệ?** `Box<Address>` chứa `Address` có các trường được ràng buộc: *cascaded validation*.

Jakarta Validation có cơ chế **value extraction** để lấy giá trị từ container trước khi kiểm tra. Ba thành phần trọng tâm:

1. `@ExtractedValue` đánh dấu **phần tử/kiểu dữ liệu được trích xuất** trong chữ ký `ValueExtractor`.
2. `@UnwrapByDefault` đặt **chính sách mặc định**: constraint đặt trên container sẽ được áp lên giá trị được trích xuất khi extractor phù hợp.
3. `Unwrapping.Unwrap` và `Unwrapping.Skip` là **payload tại nơi khai báo constraint** để yêu cầu mở hộp hoặc giữ nguyên hộp đối với constraint đó.

Sau bài này, bạn sẽ tự viết và đăng ký `ValueExtractor`, chọn đúng mục tiêu validation, phân biệt container-element constraint với unwrapping, đọc được đường dẫn lỗi, và tích hợp cơ chế này vào Spring MVC.

## 2. Tách bạch container, phần tử và unwrapping

Xét những khai báo sau:

```java
@NotNull
private List<@NotBlank String> names;

@Size(min = 2)
private List<String> tags;

private List<@Valid Address> addresses;
```

- `@NotNull` ở ngoài `List` kiểm tra **tham chiếu danh sách** khác `null`. Nó không tự xác minh từng phần tử.
- `List<@NotBlank String>` kiểm tra **từng chuỗi trong danh sách** nhờ built-in extractor cho `List`.
- `@Size(min = 2)` đặt trên `List` kiểm tra **số phần tử của danh sách**. Không được mặc định hiểu thành độ dài của từng `String`.
- `List<@Valid Address>` thực hiện validation đệ quy từng đối tượng `Address` nhờ container value extraction. `@Valid` đánh dấu cascade, không phải constraint với `message` hoặc `payload`.

Khi có custom container:

```java
Box<@NotBlank String> code;
```

`@NotBlank` nằm **trên đối số kiểu** `String`. Provider cần extractor của `Box` để lấy `String` ra. Trường hợp này khác với:

```java
@NotBlank
Box<String> code;
```

Ở ví dụ thứ hai, constraint nằm **trên đối tượng có kiểu `Box`**. Provider phải quyết định kiểm tra `Box` hay mở `Box` để kiểm tra `String`. Chính sách mặc định hoặc payload unwrapping sẽ giải quyết câu hỏi đó.

**Nguyên tắc gốc:** Có `ValueExtractor` chưa đồng nghĩa mọi constraint đặt trên container tự động được áp lên giá trị bên trong. Extractor cho biết *cách lấy giá trị*; chính sách unwrapping quyết định *đặt constraint ở đâu*.

## 3. API nền tảng: `ValueExtractor` và `@ExtractedValue`

Cả hai nằm trong package `jakarta.validation.valueextraction`. Một extractor triển khai:

```java
public interface ValueExtractor<T> {
    void extractValues(T originalValue, ValueReceiver receiver);
}
```

`T` ở đây là **kiểu container**. Bên trong `extractValues()`, extractor gọi các hàm của `ValueReceiver` để chuyển những giá trị cần kiểm tra cho provider. Với container tổng quát:

```java
public record Box<T>(T value) {}

public final class BoxExtractor
        implements ValueExtractor<Box<@ExtractedValue ?>> {

    @Override
    public void extractValues(Box<?> box, ValueReceiver receiver) {
        receiver.value(null, box.value());
    }
}
```

*Đây là hai khai báo minh họa API, chưa phải chương trình độc lập; ví dụ chạy đầy đủ ở mục 6.*

Ý nghĩa quan trọng:

- `Box<@ExtractedValue ?>` xác định **đối số kiểu thứ nhất** là nơi extractor lấy giá trị. Với kiểu generic, `@ExtractedValue` đánh dấu một type argument trong chữ ký extractor, **không** đặt tùy ý trên trường DTO.
- Mỗi định nghĩa extractor phải có **đúng một** vị trí được đánh dấu `@ExtractedValue`. Với container có hai kiểu như `Map<K,V>`, cần extractor riêng cho key và value.
- `receiver.value(null, box.value())` báo một giá trị trích xuất. `null` ở tham số `nodeName` khiến đường dẫn lỗi không có thêm node trung gian (rất hợp với wrapper trong suốt như `Box`/`Optional`).
- `@ExtractedValue(type = SomeClass.class)` dành cho kiểu **không generic**, nơi không có type argument để suy ra kiểu giá trị bên trong. Không dùng tham số `type` trên type argument của container generic.
- Extractor thực hiện **lấy dữ liệu**, không tự gọi `validator.validate()`, không tự tạo `ConstraintViolation` và không thay validator của từng constraint.

### 3.1. Chọn đúng phương thức `ValueReceiver`

| Phương thức | Khi dùng | Dữ liệu ngữ cảnh trong đường dẫn lỗi |
| --- | --- | --- |
| `value(nodeName, value)` | Một giá trị được bọc, ví dụ `Box<T>` | Node tên `nodeName`, hoặc không thêm node khi `null` |
| `iterableValue(nodeName, value)` | Các phần tử không có chỉ số rõ ràng, ví dụ `Set` | Trạng thái nằm trong iterable |
| `indexedValue(nodeName, index, value)` | Phần tử có vị trí, ví dụ `List` | Chỉ số `index` |
| `keyedValue(nodeName, key, value)` | Phần tử có khóa, ví dụ `Map` | Khóa `key` |

Với container nhiều phần tử, **gọi receiver cho từng giá trị**, không gửi cả collection dưới danh nghĩa một phần tử. Ví dụ extractor cho một danh sách tự định nghĩa có thể duyệt:

```java
for (int i = 0; i < values.size(); i++) {
    receiver.indexedValue("<element>", i, values.get(i));
}
```

Đoạn trên là phần thân minh họa, giả sử đã có `values` là `List<?>` và `receiver` hợp lệ. Khi có index/key, hãy bảo toàn chúng để API báo lỗi xác định đúng phần tử. Đừng dùng `receiver.value(null, collection)` nếu mục đích là validate từng phần tử.

## 4. `@UnwrapByDefault` và hai payload chủ động

`@UnwrapByDefault` đặt **trên lớp triển khai `ValueExtractor`**, không đặt lên `Box`, trường DTO hay annotation constraint:

```java
@UnwrapByDefault
public final class BoxExtractor
        implements ValueExtractor<Box<@ExtractedValue ?>> {
    @Override
    public void extractValues(Box<?> box, ValueReceiver receiver) {
        receiver.value(null, box.value());
    }
}
```

Khi provider tìm được một extractor phù hợp và mặc định mở hộp như trên, câu lệnh:

```java
@NotBlank
Box<String> customerCode;
```

sẽ áp `@NotBlank` lên `String` được bọc. Đây là **implicit unwrapping**. Không cần viết `@NotBlank` vào tham số kiểu nữa nếu thiết kế API chủ định kiểm tra wrapped value bằng annotation đặt trên wrapper.

Một constraint riêng lẻ vẫn có thể bỏ qua hoặc bắt buộc mở hộp bằng payload:

```java
@NotBlank(payload = Unwrapping.Unwrap.class)
Box<String> code; // Buộc validate String bên trong.

@NotNull(payload = Unwrapping.Skip.class)
Box<String> holder; // Validate chính tham chiếu Box.
```

Hai payload là `jakarta.validation.valueextraction.Unwrapping.Unwrap` và `Unwrapping.Skip` (các marker kế thừa `Payload`), không phải tùy chọn toàn cục; chúng áp dụng **cho constraint được khai báo cùng payload**.

### 4.1. Bảng quyết định

| Nơi đặt constraint | Cấu hình extractor | Ý nghĩa |
| --- | --- | --- |
| `Box<@NotBlank String> code` | Có extractor phù hợp | Validate phần tử `String`, không phụ thuộc `@UnwrapByDefault` |
| `@NotBlank Box<String> code` | Extractor có `@UnwrapByDefault` | Mặc định validate `String` |
| `@NotBlank Box<String> code` | Extractor không có `@UnwrapByDefault` | Cố validate `Box`; thường gây `UnexpectedTypeException` vì `@NotBlank` không có validator cho `Box` |
| `@NotBlank(payload = Unwrapping.Unwrap.class) Box<String> code` | Extractor không default unwrap nhưng có thể trích xuất `String` | Cưỡng bức kiểm tra phần tử `String` |
| `@NotNull(payload = Unwrapping.Skip.class) Box<String> holder` | Extractor có `@UnwrapByDefault` | Cưỡng bức kiểm tra **tham chiếu container** |
| `@Valid Box<Address> holder` hoặc `Box<@Valid Address> holder` | Có extractor phù hợp để cascade | Đưa đối tượng bên trong vào validation đệ quy; `@Valid` không dùng payload Unwrap/Skip |

Bảng này mô tả trường hợp có đúng một extractor phù hợp cho vị trí cần lấy giá trị. Nếu không có extractor, chọn nhầm extractor, hoặc có nhiều ứng viên ngang nhau, provider có thể báo lỗi cấu hình/thực thi. Không sử dụng `Unwrapping.Unwrap` và `Unwrapping.Skip` cùng lúc trên một constraint.

### 4.2. Trường hợp `@NotNull` dễ hiểu sai

Với extractor **được đánh dấu `@UnwrapByDefault`**:

```java
@NotNull
Box<String> value; // Ý nghĩa mong muốn: wrapped String không null.

@NotNull(payload = Unwrapping.Skip.class)
Box<String> holder; // Ý nghĩa mong muốn: tham chiếu Box không null.
```

Nếu `holder = new Box<>(null)` thì constraint thứ hai **đạt** vì container tồn tại. Nếu yêu cầu *cả container lẫn dữ liệu bên trong* không null, khai báo hai quy tắc rõ ràng tại hai tầng thay vì coi một `@NotNull` là kiểm tra tất cả. Với container `null`, extractor không có đối tượng để mở; quy tắc kiểm tra sự tồn tại của wrapper cần được khai báo riêng khi có ý nghĩa nghiệp vụ.

Một cảnh báo tương tự: `@Min` và `@Size` thường coi **giá trị được trích xuất là `null`** là hợp lệ. Muốn cấm rỗng/thiếu phải thêm `@NotNull`, `@NotBlank` hoặc một constraint thích hợp vào đúng tầng cần kiểm tra.

## 5. Container generic và không generic

### 5.1. Generic: `Box<T>`

`ValueExtractor<Box<@ExtractedValue ?>>` nói rõ tham số kiểu `T` là thứ được trích xuất. Do đó annotation sử dụng được cả hai kiểu khai báo:

```java
Box<@NotBlank String> name;
Box<@Valid Address> address;
```

Trong đó `Address` là một lớp có các constraint trên field/getter. Annotation `@Valid` trong type argument biểu thị cascade. Nếu định nghĩa extractor chỉ xử lý một vị trí type argument, thì provider cần extractor tương ứng cho mỗi vị trí khác mà bạn muốn kiểm tra.

### 5.2. Không generic: `OptionalInt`

Với `OptionalInt` không có `<T>`, nên extractor phải khai báo kiểu nội dung một cách tường minh:

```java
@UnwrapByDefault
public final class ExampleOptionalIntExtractor
        implements ValueExtractor<
                @ExtractedValue(type = Integer.class) OptionalInt> {

    @Override
    public void extractValues(OptionalInt original, ValueReceiver receiver) {
        receiver.value(
                null,
                original.isPresent() ? original.getAsInt() : null
        );
    }
}
```

Đoạn minh họa này giả sử đã import `java.util.OptionalInt` và API validation; **không cần đăng ký lại extractor này** khi dùng Hibernate Validator có built-in `OptionalInt` extractor. `type = Integer.class` cung cấp kiểu giá trị sau unwrapping vì `OptionalInt` không có type argument.

Ví dụ sử dụng built-in extractor:

```java
@Min(5)
private OptionalInt minimum; // Mặc định nhắm tới Integer bên trong.

@NotNull(payload = Unwrapping.Skip.class)
private OptionalInt holder;  // Kiểm tra tham chiếu OptionalInt.
```

`OptionalInt.empty()` và `null` là hai trạng thái khác nhau: đối tượng `OptionalInt` có thể tồn tại nhưng không chứa `int`. Built-in extractor chuyển trường hợp empty thành giá trị trích xuất `null`. Vì `@Min` cho phép giá trị `null`, đừng dùng riêng `@Min` để khẳng định OptionalInt phải có giá trị. Điều kiện "bắt buộc present" phải được thể hiện bằng constraint thích hợp trên giá trị đã unwrap, ví dụ `@NotNull` khi mặc định unwrapping có hiệu lực.

## 6. Ví dụ chạy độc lập với Java 17 và Hibernate Validator

Bài thực hành dùng **hai wrapper generic**:

- `Box<T>`: extractor có `@UnwrapByDefault` để kiểm tra mặc định wrapped value.
- `Parcel<T>`: extractor **không** có `@UnwrapByDefault` để thấy rõ `Unwrapping.Unwrap` cưỡng bức mở hộp.

Dùng Maven và Java 17+, cấu trúc:

```text
value-extraction-demo/
├── pom.xml
└── src/main/java/demo/
    └── ExtractionDemo.java
```

### 6.1. Cấu hình dependency

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>value-extraction-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.5.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish.expressly</groupId>
            <artifactId>expressly</artifactId>
            <version>5.0.0</version>
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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Hibernate Validator mang theo Jakarta Validation API; `expressly` cung cấp Jakarta Expression Language cho nội suy message. Trong ứng dụng Spring Boot, thông thường dùng `spring-boot-starter-validation` và cơ chế dependency management của dự án thay vì sao chép các version trên.

### 6.2. Chương trình `ExtractionDemo.java`

```java
package demo;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import jakarta.validation.valueextraction.ExtractedValue;
import jakarta.validation.valueextraction.UnwrapByDefault;
import jakarta.validation.valueextraction.Unwrapping;
import jakarta.validation.valueextraction.ValueExtractor;

import java.util.TreeSet;

public class ExtractionDemo {

    public record Box<T>(T value) {}
    public record Parcel<T>(T value) {}

    // Box được "mở hộp" mặc định.
    @UnwrapByDefault
    public static final class BoxExtractor
            implements ValueExtractor<Box<@ExtractedValue ?>> {

        @Override
        public void extractValues(Box<?> box, ValueReceiver receiver) {
            receiver.value(null, box.value());
        }
    }

    // Parcel vẫn có extractor, nhưng không tự mở hộp cho
    // constraint được khai báo trên chính Parcel.
    public static final class ParcelExtractor
            implements ValueExtractor<Parcel<@ExtractedValue ?>> {

        @Override
        public void extractValues(Parcel<?> parcel, ValueReceiver receiver) {
            receiver.value(null, parcel.value());
        }
    }

    public static final class Form {

        // Constraint nằm trên Box, nhưng được chuyển đến String.
        @NotBlank(message = "code is blank")
        private final Box<String> code;

        // Buộc kiểm tra Box, bỏ qua @UnwrapByDefault.
        @NotNull(
            message = "container is null",
            payload = Unwrapping.Skip.class
        )
        private final Box<String> carrier;

        // Constraint nằm ngay trên type argument String.
        private final Box<@Size(
            min = 3,
            message = "token too short"
        ) String> token;

        // Parcel không unwrap mặc định; yêu cầu unwrap tại đây.
        @NotBlank(
            message = "pin is blank",
            payload = Unwrapping.Unwrap.class
        )
        private final Parcel<String> pin;

        Form(Box<String> code,
             Box<String> carrier,
             Box<String> token,
             Parcel<String> pin) {
            this.code = code;
            this.carrier = carrier;
            this.token = token;
            this.pin = pin;
        }
    }

    private static void check(
            Validator validator, String label, Form form) {
        TreeSet<String> errors = new TreeSet<>();

        for (ConstraintViolation<Form> violation
                : validator.validate(form)) {
            errors.add(
                violation.getPropertyPath() + ": "
                    + violation.getMessage()
            );
        }

        System.out.println(label + " -> " + errors);
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                 Validation.byDefaultProvider()
                     .configure()
                     .addValueExtractor(new BoxExtractor())
                     .addValueExtractor(new ParcelExtractor())
                     .buildValidatorFactory()) {

            Validator validator = factory.getValidator();

            check(validator, "invalid", new Form(
                new Box<>(""),
                new Box<>(null),
                new Box<>("AB"),
                new Parcel<>("")
            ));

            check(validator, "valid", new Form(
                new Box<>("OK"),
                new Box<>(null),
                new Box<>("GOOD"),
                new Parcel<>("123")
            ));

            check(validator, "missing-wrapper", new Form(
                new Box<>("OK"),
                null,
                new Box<>("GOOD"),
                new Parcel<>("123")
            ));
        }
    }
}
```

Từ thư mục `value-extraction-demo` chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ExtractionDemo
```

**Kết quả mong đợi từ `System.out`** (bỏ qua log độc lập của Maven/provider):

```text
invalid -> [code: code is blank, pin: pin is blank, token: token too short]
valid -> []
missing-wrapper -> [carrier: container is null]
```

Giải mã từng kết quả:

1. Trong `invalid`, `code` bọc chuỗi trống: `@UnwrapByDefault` làm `@NotBlank` tác động lên chuỗi, nên báo `code is blank`.
2. `carrier = new Box<>(null)` vẫn là một container **khác null**. Vì `Unwrapping.Skip`, `@NotNull` kiểm tra `Box` nên không báo lỗi mặc dù giá trị bên trong null.
3. `token` bọc `"AB"` có độ dài 2; `@Size(min = 3)` đặt ở đối số kiểu, nên provider dùng extractor để kiểm tra phần tử và báo `token too short`.
4. `pin` có chuỗi trống. `ParcelExtractor` không có `@UnwrapByDefault`, nhưng `Unwrapping.Unwrap` buộc kiểm tra giá trị, vì vậy báo `pin is blank`.
5. Trường hợp `missing-wrapper` đặt `carrier = null` nên `@NotNull(payload = Skip.class)` vi phạm, trong khi các field khác hợp lệ.

`TreeSet` sắp xếp các chuỗi lỗi để stdout xác định được; thứ tự duyệt tập `ConstraintViolation` mà provider trả về không được đảm bảo. `receiver.value(null, ...)` giữ tên property đơn giản như `code`/`pin`/`token` mà không thêm node wrapper vào đường dẫn.

### 6.3. Biến thể nhỏ để tự đối chiếu

Thử **bỏ `@UnwrapByDefault`** trên `BoxExtractor`, giữ nguyên `@NotBlank Box<String> code`: lúc này `@NotBlank` nhắm đến `Box`; provider chuẩn không có validator `@NotBlank` cho `Box` và thường phát sinh `UnexpectedTypeException`. Để sửa đúng ý đồ "kiểm tra chuỗi", hoặc chuyển annotation thành `Box<@NotBlank String>`, hoặc thêm `payload = Unwrapping.Unwrap.class` vào `@NotBlank`.

Trái lại, bỏ `payload = Unwrapping.Skip.class` khỏi `carrier` khiến `@NotNull` của field đó có thể nhắm đến giá trị String bên trong (vì extractor mặc định unwrap); khi `new Box<>(null)`, kết quả từ ví dụ sẽ thay đổi.

## 7. Đăng ký `ValueExtractor` trong Java và Spring

Chỉ viết lớp implement `ValueExtractor` là chưa đủ. Provider phải **biết extractor đó tồn tại**. Có nhiều con đường:

### 7.1. Đăng ký bằng API chương trình

Ví dụ mục 6 dùng:

```java
ValidatorFactory factory = Validation.byDefaultProvider()
    .configure()
    .addValueExtractor(new BoxExtractor())
    .addValueExtractor(new ParcelExtractor())
    .buildValidatorFactory();
```

Cách này phù hợp khi viết chương trình CLI, thử nghiệm, hoặc tự quản lý `ValidatorFactory`. Mỗi factory cần được đóng khi không dùng nữa. Nếu ứng dụng Spring có nhiều `Validator`, hãy đảm bảo chúng được cấu hình nhất quán thay vì tạo một factory riêng trong controller.

### 7.2. Đăng ký qua Java ServiceLoader

Với thư viện dùng chung hoặc ứng dụng Spring Boot, có thể để provider tìm extractor qua tài nguyên:

```text
src/main/resources/META-INF/services/
    jakarta.validation.valueextraction.ValueExtractor
```

Nội dung file (mỗi dòng một tên lớp có thể được khởi tạo bằng constructor không tham số):

```text
demo.ExtractionDemo$BoxExtractor
demo.ExtractionDemo$ParcelExtractor
```

Hai tên có dấu `$` vì ví dụ mục 6 khai báo extractor là **nested static class**. Nếu trong dự án thật bạn chuyển extractor thành lớp top-level, dùng tên đầy đủ tương ứng (ví dụ `demo.BoxExtractor`). Các lớp cần public và có constructor không tham số truy cập được. Đây là một lựa chọn **thay thế** đăng ký `addValueExtractor(...)` của chương trình minh họa; đừng cấu hình trùng trong cùng một factory nếu không cần.

Hibernate Validator cũng hỗ trợ `META-INF/validation.xml` và `ValidatorContext#addValueExtractor(...)`. Extractor được đăng ký ở mức `ValidatorContext` chỉ có hiệu lực cho `Validator` tương ứng. Khi có cùng container và cùng type parameter ở nhiều nguồn cấu hình, thứ tự ưu tiên thường là: extractor built-in, ServiceLoader, `validation.xml`, `Configuration.addValueExtractor`, rồi `ValidatorContext.addValueExtractor`. Nếu có hai extractor trùng key ở **cùng một mức cấu hình**, có thể bị từ chối vì khai báo mơ hồ.

### 7.3. Sử dụng trong Spring MVC

Ví dụ dưới đây là đoạn mã **lắp vào một ứng dụng Spring Boot đã cấu hình validation**, không phải chương trình độc lập thay thế mục 6. Giả sử `Box` và `BoxExtractor` đã có trên classpath và extractor đã được đăng ký cho provider mà Spring dùng:

```java
// DTO:
public record CreateRequest(
    Box<@NotBlank String> customerCode
) {}

// Controller:
@RestController
@RequestMapping("/requests")
public class RequestController {

    @PostMapping
    public ResponseEntity<Void> submit(
            @Valid @RequestBody CreateRequest request) {
        return ResponseEntity.noContent().build();
    }
}
```

Cần các import Spring MVC, `jakarta.validation.Valid` và `jakarta.validation.constraints.NotBlank`. Dữ liệu JSON tương ứng với `Box` dạng record ở mục 6:

```json
{
  "customerCode": {
    "value": ""
  }
}
```

Khi Spring deserialize DTO và `@Valid` kích hoạt validation, provider nhận thấy container element constraint `@NotBlank` nằm trong `Box<...>`, gọi custom extractor và phát hiện chuỗi rỗng. Với một request body validation thất bại theo luồng MVC thông thường, Spring có thể trả HTTP 400 qua `MethodArgumentNotValidException`. Xử lý method validation hoặc `BindingResult` sẽ có nhánh xử lý khác tùy chữ ký controller.

**Phân tách trách nhiệm:** Spring binding/Jackson tạo dữ liệu DTO, Spring kích hoạt validation, provider Jakarta Validation chọn extractor và constraint, Spring xử lý lỗi nhận về. `@UnwrapByDefault` không thay thế `@Valid`, không can thiệp cách JSON được bind và không tự bật validation cho endpoint.

## 8. Cascaded validation và cấu trúc lồng nhau

`ValueExtractor` còn tham gia cascade. Giả sử:

```java
public class Address {
    @NotBlank
    private String city;
}

// Khai báo trong DTO:
private Box<@Valid Address> shippingAddress;
```

Khi validate DTO, provider lấy `Address` từ `Box` rồi áp các constraint của `Address` nhờ `@Valid`. `@UnwrapByDefault` không phải điều kiện để sử dụng `Box<@Valid Address>`; cái cần là extractor phù hợp và đăng ký đúng.

Với cấu trúc nhiều tầng:

```java
private List<Box<@Valid Address>> addresses;
```

Provider có thể đi theo từng mức: extractor built-in của `List` → extractor tùy chỉnh của `Box` → validation của `Address`. Đường dẫn lỗi có thể mang tên thuộc tính, node container và chỉ số phần tử tùy phương thức `ValueReceiver`. Nếu bạn thay `receiver.value(null, ...)` bằng tên node không null, đường dẫn sẽ thêm thành phần tương ứng.

**Không nhầm cascade với việc mở hộp của constraint:** `@Valid` xác định cần đi sâu vào object graph; `Unwrapping.Unwrap` và `Unwrapping.Skip` điều chỉnh constraint **có payload** đang đặt trên container. Bạn không nên dùng `@Valid(payload = ...)` vì `@Valid` không khai báo thuộc tính `payload`.

## 9. Resolution, hiệu năng và giới hạn

### 9.1. Provider chọn extractor như thế nào?

Việc chọn dựa vào kiểu container, vị trí type argument được đánh dấu và context của validation. Với **container element constraint**, đặc tả dùng kiểu **đã khai báo** để tìm extractor; với **cascaded validation**, kiểu **tại runtime** có vai trò trong resolution. Khi có nhiều extractor cạnh tranh, provider phải xác định extractor đủ cụ thể cho vị trí cần trích xuất. Lựa chọn mơ hồ có thể gây `ConstraintDeclarationException`, tùy tình huống.

Những lỗi thiết kế thường gây sự cố:
- Hai extractor cùng nhận `Box<@ExtractedValue ?>` ở cùng mức đăng ký.
- Không có extractor cho custom container mà vẫn khai báo constraint trên type argument.
- Đánh dấu nhiều hơn một `@ExtractedValue` trong cùng định nghĩa extractor.
- Dùng `@ExtractedValue(type = String.class)` trên type parameter của một container generic.
- Một extractor nhắm tới kiểu `Map<K,V>` nhưng muốn trích cả K và V trong cùng định nghĩa; nên tách hai extractor đúng vị trí.

### 9.2. Một số ràng buộc về dữ liệu và hiệu năng

- Extraction thường được gọi mỗi khi provider cần xét các element/cascade liên quan. Một collection lớn có thể phát sinh nhiều lần validate, vì vậy `extractValues()` nên là hàm lặp đơn giản, không truy vấn DB hoặc tạo side effect.
- Không giả định provider gọi extractor với container `null`. Constraint kiểm tra sự tồn tại của container nên được định nghĩa ở đúng tầng.
- Extractor cho collection phải duyệt phần tử đúng thứ tự/logical set; với `Map`, lấy đúng key/value và truyền key thật cho `keyedValue`.
- Với DTO nhận từ HTTP, cân nhắc kích thước collection đầu vào và giới hạn request ở tầng binding/application; validation không phải bộ thay thế kiểm soát kích thước payload.
- Custom extractors tạo ra cơ chế chung cho mọi constraint có liên quan; thay đổi chính sách `@UnwrapByDefault` sẽ ảnh hưởng nhiều vị trí khai báo, vì vậy cần test hành vi wrapper và wrapped value.

## 10. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| Constraint trên `Box<@NotBlank String>` không chạy hoặc báo thiếu extractor | Extractor chưa đăng ký hoặc chữ ký nhắm sai type argument | Kiểm tra `ValueExtractor<Box<@ExtractedValue ?>>` và đăng ký qua factory/ServiceLoader |
| `@NotBlank Box<String>` gây `UnexpectedTypeException` | Constraint nhắm đến `Box` trong khi validator chỉ hỗ trợ chuỗi | Dùng `Box<@NotBlank String>`, `@UnwrapByDefault` hoặc `Unwrapping.Unwrap` phù hợp |
| `@NotNull Box<String>` không phân biệt rõ null trong/ngoài | Default unwrapping thay đổi đối tượng được kiểm tra | Dùng `Skip` để kiểm tra tham chiếu container, constraint riêng cho phần tử |
| `@Min` trên `OptionalInt.empty()` không báo lỗi | Giá trị được extract là `null` và `@Min` không cấm null | Thêm constraint bắt buộc có giá trị tại đúng tầng |
| Tạo extractor với hai `@ExtractedValue` | Chữ ký extractor không hợp lệ | Mỗi extractor có đúng một vị trí extracted; tách K/V nếu cần |
| Value extractor generic báo sai định nghĩa | Gán `type = ...` ở `@ExtractedValue` thuộc type argument | Bỏ `type` cho generic; dùng `@ExtractedValue(type=...)` chỉ với non-generic |
| Lỗi đường dẫn thiếu index/key | Dùng `receiver.value(...)` thay vì indexed/keyed receiver | Chọn `indexedValue`/`keyedValue` và truyền vị trí/khóa |
| Spring MVC vẫn chấp nhận dữ liệu sai | Chưa kích hoạt validation hoặc extractor không được provider của Spring đăng ký | Kiểm tra starter, `@Valid`/`@Validated`, ServiceLoader và đường đi qua `Validator` |
| Chỉ fail khi thêm `Skip` | Validator của constraint không hỗ trợ kiểu container | Dùng constraint phù hợp để kiểm tra container; `Skip` không tạo validator mới |

Nhận biết một số loại ngoại lệ:
- `ValueExtractorDefinitionException`: **định nghĩa extractor** bất hợp lệ, chẳng hạn không khai báo đúng `@ExtractedValue`.
- `ValueExtractorDeclarationException`: **khai báo/đăng ký extractor** gây xung đột, chẳng hạn trùng extractor cho cùng container/type parameter.
- `ConstraintDeclarationException`: khai báo constraint/container hoặc resolution không hợp lệ.
- `UnexpectedTypeException`: không tìm thấy validator phù hợp với **kiểu thực sự được constraint nhắm tới** (ví dụ `@NotBlank` nhắm vào `Box`).

Đừng xử lý các lỗi cấu hình trên bằng cách bắt ngoại lệ rồi bỏ qua validation. Hãy sửa chữ ký extractor, vị trí annotation và đăng ký trước khi triển khai.

## 11. Chiến lược test nên áp dụng

Khi viết một wrapper dùng chung, test tối thiểu **các trục độc lập**, không chỉ một input hợp lệ:

| Tình huống | Kết quả cần kiểm chứng |
| --- | --- |
| Container có dữ liệu hợp lệ | Không có violation |
| Container có dữ liệu sai | Constraint trên wrapped value phát hiện lỗi |
| Container có giá trị `null` bên trong | Constraint trên phần tử có xử lý null đúng theo hợp đồng |
| Chính tham chiếu container `null` | Constraint kiểm tra wrapper phản hồi đúng |
| Constraint ngoài + `@UnwrapByDefault` | Mặc định mở hộp |
| Constraint ngoài + `Unwrapping.Skip` | Kiểm tra container |
| Constraint ngoài + `Unwrapping.Unwrap` | Buộc kiểm tra phần tử dù extractor không default unwrap |
| Constraint trên type argument | Hoạt động dù không gắn `@UnwrapByDefault` |
| `Box<@Valid Address>` | Cascade đến constraint của `Address` |
| Hai extractor có khả năng trùng nhau | Cấu hình không còn mơ hồ và lỗi được phát hiện sớm |

Trong test, ngoài `getMessage()`, nên kiểm tra `getPropertyPath()` và `getInvalidValue()` của `ConstraintViolation`. Tùy receiver node name, property path có thể khác nhau; test đường dẫn khi nó là một phần hợp đồng API trả lỗi cho client.

## 12. Bài tập củng cố

1. Bỏ `@UnwrapByDefault` khỏi `BoxExtractor` của mục 6, sau đó thay `@NotBlank Box<String> code` bằng `Box<@NotBlank String> code`. Dự đoán `invalid` trước và sau khi chạy.
2. Thêm field `@NotNull Box<String> mandatoryValue` và `@NotNull(payload = Unwrapping.Skip.class) Box<String> mandatoryContainer`. So sánh khi cả hai là `new Box<>(null)` và khi cả hai là `null`.
3. Viết `ValueExtractor` cho một container nhiều phần tử tự định nghĩa, gọi `indexedValue("<item>", index, value)`; thử constraint trên type argument và quan sát property path.
4. Đặt `@Valid` cho một đối tượng trong `Box`, thử dữ liệu hợp lệ và field bên trong rỗng; chứng minh cascade không cần `Unwrapping.Unwrap`.
5. Chuyển đăng ký extractor từ `Configuration.addValueExtractor` sang ServiceLoader, giữ nguyên các case test và kiểm tra provider dùng đúng extractor khi chạy trong Spring.

**Ghi nhớ:** `@ExtractedValue` nói *lấy cái gì*; `ValueReceiver` nói *trả các giá trị đó cho validator theo cấu trúc nào*; `@UnwrapByDefault` nói *mặc định constraint ở wrapper có nên chuyển vào bên trong hay không*; `Unwrapping.Unwrap/Skip` nói *ngoại lệ riêng cho một constraint*.

## 13. Tài liệu tham khảo

- [Jakarta Bean Validation 3.0 specification — Value extraction và implicit unwrapping](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html#valueextractordefinition)
- [Jakarta Validation API — `ExtractedValue`](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/valueextraction/extractedvalue)
- [Jakarta Validation API — `UnwrapByDefault`](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/valueextraction/unwrapbydefault)
- [Jakarta Validation API — `Unwrapping`](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/valueextraction/unwrapping)
- [Hibernate Validator 8 Reference Guide — Value extraction](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/#chapter-valueextraction)
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)