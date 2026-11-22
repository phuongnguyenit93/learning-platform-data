# Container element constraint: kiểm tra phần tử trong List<@NotBlank String> và các container lồng nhau

## 1. Bài toán: kiểm tra danh sách hay kiểm tra từng phần tử?

Một endpoint nhận danh sách nhãn:

```json
{
  "tags": ["java", " ", "spring"]
}
```

Nếu DTO chỉ ghi `@NotEmpty List<String> tags`, danh sách có ba phần tử nên vượt qua ràng buộc không rỗng. Nhưng phần tử thứ hai là chuỗi chỉ chứa dấu cách, không nên được chấp nhận nếu nhãn bắt buộc có nội dung.

Jakarta Bean Validation giải quyết vấn đề bằng **container element constraint**: đặt annotation ngay lên kiểu phần tử, thay vì chỉ đặt trên biến chứa danh sách.

```java
import java.util.List;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;

public record TagRequest(
        @NotEmpty List<@NotBlank String> tags) {
}
```

Hai annotation kiểm tra **hai cấp khác nhau**:

- `@NotEmpty` đặt trên `List`: danh sách không được null hoặc rỗng.
- `@NotBlank` đặt trên đối số kiểu `String`: mỗi phần tử của danh sách phải khác null và chứa ít nhất một ký tự không phải whitespace.
- `List<@NotBlank String>` không có nghĩa "chỉ cần một phần tử hợp lệ"; **mọi phần tử được đưa ra bởi container đều phải thỏa constraint**.
- Nếu toàn bộ danh sách bằng `null` và không có `@NotEmpty` hay `@NotNull` trên container, engine không có phần tử để kiểm tra; constraint phần tử không tự bắt lỗi container vắng mặt.

Đây là một tính năng của **Bean Validation** (Jakarta Validation), được Spring tích hợp vào quá trình binding/validation khi có điểm kích hoạt phù hợp; Java generic tự nó không kiểm tra giá trị runtime.

Sau bài này, người học cần giải thích đúng vị trí annotation, phân biệt kiểm tra container/element/cascade, áp dụng với List/Set/Map/Optional/container lồng nhau, hiểu `ValueExtractor`, và kiểm thử được kết quả qua `Validator` cùng Spring MVC.

## 2. Cú pháp TYPE_USE và vai trò từng annotation

Từ Bean Validation 2.0, constraint chuẩn có thể được đặt tại vị trí **type use** (`ElementType.TYPE_USE`) trong generic type arguments:

```java
List<@NotBlank String> names;
List<@NotNull Integer> counts;
List<@Positive Integer> quantities;
List<@Email String> emails;
List<@Valid Address> addresses;
```

Đây là các fragment minh họa; class `Address` cần được định nghĩa và các annotation cần được import.

Đọc từng dòng chính xác:

- `List<@NotBlank String>`: từ chối `null`, `""` và chuỗi chỉ toàn whitespace trong từng phần tử.
- `List<@NotNull Integer>`: từ chối phần tử null; số âm hay 0 vẫn được phép nếu không có constraint khác.
- `List<@Positive Integer>`: mỗi số khác null phải lớn hơn 0; `@Positive` riêng lẻ **cho phép null**, cần thêm `@NotNull` nếu null không được phép.
- `List<@Email String>`: kiểm tra định dạng email trên phần tử không null; nếu cần email bắt buộc, kết hợp `@NotBlank @Email`.
- `List<@Valid Address>`: duyệt vào từng bean `Address` và kiểm tra constraint **bên trong** bean đó. `@Valid` là chỉ thị cascade, không phải constraint kiểm tra String.

Những khai báo sau có ý nghĩa khác:

```java
@NotEmpty List<String> tags;               // Chỉ kiểm tra List
List<@NotBlank String> tags;               // Chỉ kiểm tra phần tử
@NotEmpty List<@NotBlank String> tags;     // Cả List lẫn phần tử
```

**Đừng viết `@NotBlank List<String> tags`** để yêu cầu các phần tử không trắng. `@NotBlank` được thiết kế cho `CharSequence`; khi áp dụng lên `List`, một Bean Validation provider chuẩn không có `ConstraintValidator` tương thích và có thể ném `UnexpectedTypeException`, thay vì kiểm tra toàn bộ các chuỗi.

Để tránh lẫn với các dạng `@Valid` lồng nhau, nhớ công thức:

```text
@NotEmpty  List<@NotBlank String>
    |         |
    |         +-- constraint chạy trên từng String
    +------------ constraint chạy trên bản thân List

@NotNull   List<@NotNull @Valid Address>
    |                  |       |
    |                  |       +-- đi vào constraint của Address
    |                  +---------- phần tử Address không được null
    +----------------------------- chính List không được null
```

## 3. Hiểu kết quả của List<@NotBlank String>

Giả sử khai báo:

```java
record Form(@NotEmpty List<@NotBlank String> tags) {}
```

Bảng sau phân biệt lỗi của container và phần tử:

| Giá trị `tags` | `@NotEmpty` trên List | `@NotBlank` trên phần tử | Kết luận |
| --- | --- | --- | --- |
| `null` | Sai | Không duyệt được phần tử | Không hợp lệ |
| `[]` | Sai | Không có phần tử | Không hợp lệ |
| `["java"]` | Đúng | Đúng | Hợp lệ |
| `["java", "spring"]` | Đúng | Đều đúng | Hợp lệ |
| `[""]` | Đúng | Sai | Không hợp lệ |
| `[" "]` | Đúng | Sai | Không hợp lệ |
| `[null]` | Đúng | Sai vì `@NotBlank` coi null là không hợp lệ | Không hợp lệ |
| `["ok", " "]` | Đúng | Phần tử thứ hai sai | Không hợp lệ |
| `["ok", null]` | Đúng | Phần tử thứ hai sai | Không hợp lệ |

`@NotBlank` khác `@NotEmpty` khi dùng trên String: `@NotEmpty` chấp nhận chuỗi có một dấu cách, còn `@NotBlank` không. Nếu yêu cầu nội dung không được toàn khoảng trắng, hãy dùng `@NotBlank`.

### 3.1. Khi số phần tử có giới hạn

Nếu cần ít nhất 1 và nhiều nhất 5 nhãn, đồng thời mỗi nhãn từ 2 đến 20 ký tự:

```java
import java.util.List;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

record Tags(
        @Size(min = 1, max = 5)
        List<@NotBlank @Size(min = 2, max = 20) String> values) {
}
```

`@Size(min=1,max=5)` ngoài `List` giới hạn **số phần tử**. `@Size(min=2,max=20)` bên trong giới hạn **độ dài mỗi chuỗi**. `@NotBlank` cũng bắt null và whitespace-only; `@Size` trên String thường xem null hợp lệ, vì vậy không nên bỏ `@NotBlank` khi cần buộc nội dung.

Không có annotation nào trong ví dụ tự xóa khoảng trắng ở đầu/cuối hoặc chuẩn hóa chữ hoa/thường. Chuỗi `" Java "` vẫn có thể hợp lệ nếu đủ điều kiện. Nếu nghiệp vụ muốn trim/normalize, thực hiện theo hợp đồng dữ liệu một cách tường minh và test cả thứ tự **chuẩn hóa trước validation**.

## 4. Cơ chế ValueExtractor phía sau

Khi Bean Validation thấy `List<@NotBlank String>` trên một thuộc tính đang được validate, nó phải lấy **các phần tử** khỏi danh sách. Cơ chế chuẩn gọi là `jakarta.validation.valueextraction.ValueExtractor`.

```text
Validator.validate(request)
        |
        v
TagRequest.tags = List
        |
        +--> @NotEmpty đánh giá danh sách
        |
        +--> Bean Validation xác định type argument có @NotBlank
                   |
                   v
             List ValueExtractor
                   |
             +-----+-----+
             |     |     |
             0     1     2
             |     |     |
            "a"   " "   "b"
             |     |     |
             pass  fail  pass
```

Điểm cốt lõi:

1. Container element constraint là **metadata gắn lên type argument** có `TYPE_USE`, không phải annotation trên một instance `String` riêng lẻ.
2. Provider xác định `ValueExtractor` phù hợp với container; đối với `List`, extractor biết cách lần lượt trả các phần tử và index tương ứng.
3. Engine áp dụng constraint lên **giá trị đã trích xuất**. Với `Map`, extractor cho key và value được phân biệt; với `Optional`, giá trị có thể là null khi Optional rỗng.
4. Lỗi chứa `ConstraintViolation.getPropertyPath()` mô tả đường dẫn từ bean gốc tới phần tử, thường có chỉ số danh sách hoặc key của map.
5. Nếu một container tự tạo (`Box<T>`, `Either<L,R>`...) không có value extractor tương thích, việc gắn type-argument constraint có thể gây lỗi khai báo/không phân giải được extractor. Hệ thống cần cấu hình một `ValueExtractor` thích hợp; **không tự giả định mọi generic class đều được hỗ trợ**.

Bean Validation cung cấp extractors chuẩn cho các container như `Iterable`, `List`, `Map`, `Optional` và các primitive Optional. Do đó trường hợp `List<@NotBlank String>` thông thường **không cần tự viết ValueExtractor**.

### 4.1. Đường dẫn lỗi của phần tử

Với Hibernate Validator, một lỗi ở phần tử thứ hai của danh sách `tags` thường có đường dẫn dạng:

```text
tags[1].<list element>
```

Khi lỗi do constraint bên trong bean của `List<@Valid Address>`, thường thấy đường dẫn như:

```text
addresses[0].city
```

Tên node container, cách Spring ánh xạ path ra field error và thứ tự của tập `ConstraintViolation` có thể phụ thuộc provider/version/integration. Khi test, nên kiểm tra loại constraint và path theo dữ liệu quan trọng; nếu cần giao diện lỗi cố định, chủ động định nghĩa cách chuyển `ConstraintViolation` thành cấu trúc response ổn định.

## 5. Phân biệt element constraint và cascaded validation bằng @Valid

Xét hai trường hợp:

```java
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

record Address(@NotBlank String city) {}

record Form(
        List<@NotBlank String> tags,
        List<@Valid Address> addresses) {
}
```

- `List<@NotBlank String>` đặt **constraint trên giá trị String trực tiếp**; mỗi String được kiểm tra mà **không cần @Valid trên List**.
- `List<@Valid Address>` yêu cầu provider **đi vào bean Address** để kiểm tra `city`. Nếu bỏ `@Valid` trên type argument và chỉ có `@NotBlank` trong class `Address`, việc xác thực `Form` thông thường không đi vào `Address.city`.
- `List<@NotNull @Valid Address>` còn từ chối phần tử `null`. `@Valid` đơn độc không tự coi một phần tử bean null là vi phạm.
- Đánh dấu `@Valid` trên đối tượng cha được Bean Validation provider validate **khác** với annotation trên phần tử container. Điểm bắt đầu từ controller hoặc `Validator.validate(...)` phải tồn tại trước.

### 5.1. Không đặt @Valid trùng một đường

Đối với những container giữ bean cần cascade, có thể gặp cú pháp cũ:

```java
@Valid
List<Address> addresses;
```

Cú pháp hiện đại nêu rõ vị trí element:

```java
List<@Valid Address> addresses;
```

Với cùng một đường đi, **không cần** dùng đồng thời `@Valid List<@Valid Address>`; Jakarta Bean Validation khuyến cáo chọn một cách đánh dấu cascade để không xác thực các phần tử hai lần. Với ràng buộc nội dung String, dùng `List<@NotBlank String>`, không thêm `@Valid` chỉ để khiến `@NotBlank` hoạt động.

### 5.2. @Valid không thay thế @NotNull hay @NotEmpty

Các annotation đáp ứng nhu cầu riêng:

| Yêu cầu | Chỗ đặt |
| --- | --- |
| Danh sách bắt buộc tồn tại | `@NotNull List<...>` |
| Danh sách bắt buộc có phần tử | `@NotEmpty List<...>` |
| Mỗi String không trắng | `List<@NotBlank String>` |
| Mỗi phần tử bean không null | `List<@NotNull @Valid Address>` |
| Mỗi bean con phải được kiểm tra constraint nội bộ | `List<@Valid Address>` |

Một danh sách rỗng có **không phần tử nào vi phạm** `@NotBlank`; muốn danh sách không rỗng, luôn cần constraint trên container.

## 6. Map: ràng buộc key và value khác nhau

Container `Map<K,V>` có hai type argument, cho phép đánh dấu từng nhánh:

```java
import java.util.Map;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

record Contact(@NotBlank String name) {}

record ContactDirectory(
        Map<@NotBlank String, @NotBlank @Email String> emailsByRole,
        Map<@NotBlank String, @NotNull @Valid Contact> contactsByRole) {
}
```

`emailsByRole` có quy tắc:
- Mỗi **key** (vai trò như `"admin"` hay `"support"`) không null, không trắng.
- Mỗi **value** phải là String không null, không trắng và hợp lệ theo `@Email`; `@Email` đứng riêng thường không buộc có nội dung, nên kết hợp `@NotBlank`.
- Map bản thân vẫn có thể null hoặc rỗng nếu không thêm `@NotNull`/`@NotEmpty` trên Map.

`contactsByRole` còn đi vào `Contact.name` của từng bean ở **value**, nhưng vẫn cần `@NotNull` trên value nếu muốn cấm null thay vì cho phép cascade bỏ qua.

Điểm cần nhớ: `Map<@NotBlank String, Contact>` kiểm tra **key**, còn `Map<String, @Valid Contact>` kiểm tra **nội dung bean ở value**. Đừng đặt annotation vào type argument sai khi viết nhiều generic.

## 7. Optional và container lồng nhau

### 7.1. Optional<T>

Ví dụ:

```java
import java.util.Optional;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

record Profile(
        Optional<@NotBlank String> nickname,
        Optional<@Valid Address> deliveryAddress) {
}
```

Extractor của `Optional` lấy giá trị đang chứa, hoặc đưa **null** tới validator nếu `Optional.empty()`:

- `Optional.of("ok")` đạt `@NotBlank`.
- `Optional.of(" ")` vi phạm `@NotBlank`.
- `Optional.empty()` cũng **vi phạm `@NotBlank` trên type argument**, vì giá trị trích xuất là null và `@NotBlank` không cho null. Nếu trường thật sự tùy chọn, chọn constraint chấp nhận null, mô hình khác, hoặc chính sách riêng cho Optional.
- Với `Optional<@Valid Address>`, trường hợp rỗng không có bean để cascade và không tự phát sinh lỗi; nếu có `Address` thì constraint bên trong được kiểm tra.

`@NotNull Optional<...>` chỉ đòi hỏi **đối tượng Optional không null**; `Optional.empty()` vẫn là một instance khác null. Đừng coi `@NotNull` trên Optional như kiểm tra bên trong có giá trị. Đồng thời không nên để bản thân field Optional bằng null nếu code kỳ vọng sử dụng `Optional` an toàn.

### 7.2. List của List

Có thể đặt constraint sâu tới kiểu nằm trong container thứ hai:

```java
import java.util.List;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;

record Matrix(
        @NotEmpty
        List<@NotEmpty List<@NotBlank String>> groups) {
}
```

Ở đây:
- `@NotEmpty` ngoài cùng: phải có ít nhất một nhóm.
- `@NotEmpty` trên `List` bên trong: từng nhóm không được null/rỗng.
- `@NotBlank` trên `String`: mọi chuỗi trong mọi nhóm đều không được trắng.

Ví dụ `groups = [["java"], []]` sẽ bị từ chối vì nhóm thứ hai rỗng. `groups = [["java"], [" "]]` bị từ chối vì chuỗi nhóm thứ hai trắng. `groups = []` bị từ chối vì danh sách nhóm ngoài rỗng.

Các constraint phần tử tiếp tục chạy theo nhóm validation (`Default` hoặc group được chọn) giống constraint trên field bình thường; nếu nhóm không thuộc lượt validate hiện tại, constraint có thể không chạy.

## 8. Ví dụ Java 17+ có thể chạy: Jakarta Validator + Hibernate Validator

Chương trình này chứng minh chính xác các trường hợp:
- một `List<@NotBlank String>` với phần tử whitespace và null;
- một `List<@NotNull @Valid Address>` với bean con sai và phần tử null;
- container rỗng bị `@NotEmpty` từ chối;
- input hợp lệ cho kết quả không có vi phạm.

Cần runtime có **Jakarta Validation API** và **provider** như Hibernate Validator. Chỉ chạy `javac` trên một file không có classpath thì thiếu các dependency. Ví dụ dưới dùng Maven và JDK 17+.

Cấu trúc thư mục:

```text
container-validation-demo/
├── pom.xml
└── src/main/java/example/ContainerConstraintDemo.java
```

### 8.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>container-validation-demo</artifactId>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Trong ứng dụng Spring Boot 3.x thực tế, nên dùng dependency management của Boot và `spring-boot-starter-validation` thay vì áp dụng máy móc phiên bản pin từ ví dụ nhỏ này.

### 8.2. src/main/java/example/ContainerConstraintDemo.java

```java
package example;

import java.util.Arrays;
import java.util.List;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public final class ContainerConstraintDemo {

    public record Address(@NotBlank String city) {}

    public record Registration(
            @NotEmpty List<@NotBlank String> tags,
            @NotEmpty List<@NotNull @Valid Address> addresses) {
    }

    private static long countFor(
            Set<ConstraintViolation<Registration>> errors,
            String fieldPrefix) {

        return errors.stream()
                .filter(e -> e.getPropertyPath()
                        .toString().startsWith(fieldPrefix))
                .count();
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            Registration valid = new Registration(
                    List.of("java", "spring"),
                    List.of(new Address("Ha Noi")));

            Registration invalid = new Registration(
                    Arrays.asList("java", " ", null),
                    Arrays.asList(new Address(""), null));

            Registration empty = new Registration(
                    List.of(),
                    List.of(new Address("Da Nang")));

            System.out.println("valid="
                    + validator.validate(valid).size());

            Set<ConstraintViolation<Registration>> errors =
                    validator.validate(invalid);

            System.out.println("invalid=" + errors.size());
            System.out.println("tags=" + countFor(errors, "tags"));
            System.out.println("addresses=" + countFor(errors, "addresses"));
            System.out.println("emptyTags="
                    + validator.validate(empty).size());
        }
    }
}
```

Tại thư mục `container-validation-demo`, chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.ContainerConstraintDemo
```

Các dòng `System.out.println` dự kiến (log Maven/provider, nếu có, là riêng):

```text
valid=0
invalid=4
tags=2
addresses=2
emptyTags=1
```

Giải thích chính xác:
- `valid=0`: tags đều có chữ, Address có city hợp lệ.
- `invalid=4`: `tags[1]` chỉ có whitespace, `tags[2]` bằng null, `addresses[0].city` rỗng, `addresses[1]` bằng null.
- `tags=2`: cả hai lỗi chuỗi do `List<@NotBlank String>`, không cần thêm `@Valid`.
- `addresses=2`: một lỗi `@NotBlank` từ bean con vì `@Valid`, một lỗi `@NotNull` trên phần tử Address.
- `emptyTags=1`: List rỗng vi phạm `@NotEmpty` trên container, dù không có phần tử để chạy `@NotBlank`.

`Arrays.asList(...)` được dùng có chủ ý ở mẫu invalid vì nó cho phép phần tử null; `List.of(...)` của JDK không cho phép null và sẽ ném `NullPointerException` ngay khi tạo list, khiến bài test không tới bước Bean Validation.

Hàm `countFor` dùng prefix của property path để tránh phụ thuộc chi tiết node nội bộ như `<list element>`; nếu cần xác minh index cụ thể, thêm assertion cho index theo provider dự án đang dùng.

## 9. Unit test JUnit 5 cho các ranh giới quan trọng

Ví dụ này dùng hai `record` public lồng trong `ContainerConstraintDemo` ở mục 8. Tạo file `src/test/java/example/ContainerConstraintTest.java`; cấu hình JUnit Jupiter cho Maven hoặc hệ build đang dùng.

```java
package example;

import java.util.Arrays;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.ConstraintViolation;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ContainerConstraintTest {

    @Test
    void validatesEveryStringAndNestedBean() {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();

            var invalid = new ContainerConstraintDemo.Registration(
                    Arrays.asList("java", " ", null),
                    Arrays.asList(
                            new ContainerConstraintDemo.Address(""),
                            null));

            var violations = validator.validate(invalid);

            assertEquals(4, violations.size());

            Set<String> paths = violations.stream()
                    .map(v -> v.getPropertyPath().toString())
                    .collect(Collectors.toSet());

            assertTrue(paths.stream()
                    .anyMatch(path -> path.startsWith("tags[1]")));
            assertTrue(paths.stream()
                    .anyMatch(path -> path.startsWith("tags[2]")));
            assertTrue(paths.stream()
                    .anyMatch(path -> path.startsWith("addresses[0]")));
            assertTrue(paths.stream()
                    .anyMatch(path -> path.startsWith("addresses[1]")));
        }
    }

    @Test
    void rejectsEmptyListButAcceptsValidItems() {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();

            var empty = new ContainerConstraintDemo.Registration(
                    List.of(),
                    List.of(new ContainerConstraintDemo.Address("Hue")));
            assertEquals(1, validator.validate(empty).size());

            var valid = new ContainerConstraintDemo.Registration(
                    List.of("java", "spring"),
                    List.of(new ContainerConstraintDemo.Address("Hue")));
            assertTrue(validator.validate(valid).isEmpty());
        }
    }
}
```

**Test source bổ sung:** `pom.xml` ở mục 8 chỉ phục vụ chạy `main`; để chạy JUnit 5, thêm dependency `org.junit.jupiter:junit-jupiter` phiên bản phù hợp và cấu hình Maven Surefire tương thích. Trong một dự án Spring Boot, `spring-boot-starter-test` thường cung cấp các thành phần test cần thiết. Phần test trên là file Java thực thi trong classpath đã có JUnit, không phải bài test Maven có thể chạy ngay với `pom.xml` main-only.

Chạy qua test task của build (ví dụ `mvn test` sau khi bổ sung JUnit/Surefire), rồi kiểm tra đường dẫn vi phạm trên phiên bản provider của dự án. Các assertion ở đây kiểm tra hành vi thật thay vì chỉ tìm annotation qua reflection.

## 10. Tích hợp vào Spring MVC: @RequestBody DTO bao bọc List

Đối với API HTTP nhận JSON, hãy dùng một **request DTO** để mô tả rõ constraint trên container và phần tử. Với Spring Boot 3.x, thường cần `spring-boot-starter-web` cùng `spring-boot-starter-validation` và một entrypoint Boot có component scan phù hợp.

### 10.1. DTO và controller

**File `src/main/java/com/example/api/LabelRequest.java`:**

```java
package com.example.api;

import java.util.List;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;

public record LabelRequest(
        @NotEmpty List<@NotBlank String> labels) {
}
```

**File `src/main/java/com/example/api/LabelController.java`:**

```java
package com.example.api;

import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LabelController {

    @PostMapping("/labels")
    public ResponseEntity<Void> create(
            @Valid @RequestBody LabelRequest request) {

        // Chỉ minh họa validate; không lưu dữ liệu.
        return ResponseEntity.noContent().build();
    }
}
```

Hai vị trí đáng chú ý:
1. `@Valid` trên tham số method nói với Spring MVC rằng sau khi Jackson deserialize JSON thành `LabelRequest`, MVC cần áp dụng Bean Validation cho root object này.
2. `List<@NotBlank String>` trong DTO nói với Bean Validation provider kiểm tra **từng label**, khi root được validate. Không cần `@Valid` đặt thêm trên field `labels` chỉ vì các phần tử là String.

Với Bean Validation provider được cấu hình và controller đang sử dụng MVC validation thông thường:

| JSON body | Kết quả |
| --- | --- |
| `{"labels":["java","spring"]}` | 204 No Content |
| `{"labels":[]}` | 400 Bad Request do `@NotEmpty` |
| `{"labels":[""]}` | 400 do `@NotBlank` trên phần tử |
| `{"labels":["java"," "]}` | 400 do nhãn thứ hai whitespace-only |
| `{"labels":["java",null]}` | 400 do `@NotBlank` trên null |
| `{"labels":null}` | 400 do `@NotEmpty` trên List |
| `{}` | Thường 400 vì field labels bị deserialize thành null, rồi `@NotEmpty` thất bại |
| JSON không parse được | Lỗi deserialize (có thể 400) trước Bean Validation |

**Không giả định response JSON lỗi có định dạng chung.** Điều đó phụ thuộc phiên bản Spring Boot, Problem Details, `@ControllerAdvice` và message configuration. Các lỗi Bean Validation của một command object `@Valid @RequestBody` trong MVC thường đi qua `MethodArgumentNotValidException`; lỗi parse JSON có thể đi qua `HttpMessageNotReadableException`.

### 10.2. MockMvc kiểm tra phần tử thực sự bị từ chối

**File `src/test/java/com/example/api/LabelControllerTest.java`:**

```java
package com.example.api;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.MethodArgumentNotValidException;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(LabelController.class)
class LabelControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void acceptsValidLabels() throws Exception {
        mvc.perform(post("/labels")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"labels\":[\"java\",\"spring\"]}"))
                .andExpect(status().isNoContent());
    }

    @Test
    void rejectsBlankElement() throws Exception {
        mvc.perform(post("/labels")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"labels\":[\"java\",\" \"]}"))
                .andExpect(status().isBadRequest())
                .andExpect(result -> {
                    assertTrue(result.getResolvedException()
                            instanceof MethodArgumentNotValidException);

                    var ex = (MethodArgumentNotValidException)
                            result.getResolvedException();

                    assertTrue(ex.getBindingResult().getFieldErrors()
                            .stream()
                            .anyMatch(e -> e.getField()
                                    .startsWith("labels[1]")));
                });
    }

    @Test
    void rejectsEmptyContainer() throws Exception {
        mvc.perform(post("/labels")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"labels\":[]}"))
                .andExpect(status().isBadRequest());
    }
}
```

`@WebMvcTest` cần dependency test phù hợp (thường `spring-boot-starter-test`) và validation provider đang hoạt động trong test context. Test chứng minh cả ràng buộc danh sách lẫn phần tử, tránh chỉ assert annotation có trong source.

### 10.3. Vì sao không viết trực tiếp List<@NotBlank String> @RequestBody?

Ví dụ:

```java
@PostMapping("/labels")
void create(@Valid @RequestBody List<@NotBlank String> labels) {
    // Không thể mặc định suy ra MVC sẽ validate trực tiếp List như command object.
}
```

Đoạn trên là **fragment thảo luận**, không phải hợp đồng endpoint được bảo đảm. Theo cơ chế Spring MVC, `@Valid @RequestBody` với một đối tượng command (DTO) có đường validate bean khác với khi tham số trực tiếp là `Collection`/`Map`. Method validation cũng có điều kiện kích hoạt riêng, đặc biệt trong Spring MVC 6.1+. Nếu cần API nhận JSON array trực tiếp, phải kiểm thử cơ chế validation thực tế hoặc kích hoạt method validation thích hợp; **DTO bao bọc là cách rõ ràng, dễ bảo trì** khi muốn kiểm tra `List<@NotBlank String>`.

## 11. Container element constraints trên method parameter và return value

Bên ngoài DTO, Jakarta Bean Validation cho phép đặt type argument constraints vào:
- field và bean getter;
- tham số method hoặc constructor;
- kiểu giá trị trả về method.

Ví dụ fragment:

```java
import java.util.List;
import jakarta.validation.constraints.NotBlank;

public interface LabelService {
    List<@NotBlank String> normalize(
            List<@NotBlank String> incoming);
}
```

Annotation mô tả ràng buộc **đầu vào và đầu ra** của method. Tuy nhiên nếu method được gọi như Java thuần `new LabelServiceImpl().normalize(...)`, annotation không tự chạy. Cần cơ chế method validation thực sự gọi `ExecutableValidator`; với Spring service bean thường là method validation bằng Spring proxy/AOP khi được cấu hình và gọi từ bên ngoài proxy.

Spring MVC 6.1+ có built-in method validation cho handler method khi xuất hiện constraint trực tiếp trên method parameter/return value. `@Valid` **không phải** một constraint annotation; `@Valid` đơn độc không đồng nghĩa với "mọi method sẽ tự được validate". Các exception có thể khác nhau giữa validation đối tượng request (`MethodArgumentNotValidException`) và method validation (`HandlerMethodValidationException`).

Với return value, Bean Validation có thể chạy sau khi method trả kết quả; thất bại ở output thường phản ánh lỗi server/invariant, không nên mặc nhiên trả cùng mã HTTP 400 như lỗi dữ liệu từ client.

## 12. Validation groups và mối quan hệ với @Validated

Ví dụ constraint chỉ có hiệu lực khi tạo mới:

```java
import java.util.List;
import jakarta.validation.constraints.NotBlank;
import org.springframework.validation.annotation.Validated;

interface CreateGroup {}

record Command(
        List<@NotBlank(groups = CreateGroup.class) String> tags) {
}

// Fragment của controller có cơ chế MVC validation:
void create(@Validated(CreateGroup.class) Command command) {
}
```

Với lượt validate nhóm `CreateGroup`, mỗi String trong `tags` chịu constraint `@NotBlank` của nhóm ấy. Khi chỉ validate nhóm `Default`, constraint chỉ gán cho `CreateGroup` **không tự chạy**. Cơ chế group cho container element giống constraint ở field bình thường; vị trí annotation không tự thay đổi group.

Cần phân biệt:
- `@Valid` (Jakarta): nói provider đi sâu vào bean con/đường cascade, hoặc trong MVC là chỉ dấu validate DTO tại điểm vào.
- `@Validated` (Spring): hỗ trợ chọn validation group tại điểm tích hợp Spring và dùng trong một số cấu hình method validation.
- `@NotBlank`: mới là constraint **thực sự kiểm tra** giá trị String; khi đặt trong `List<...>`, nó áp vào từng phần tử.

Nếu một bean con cần đổi group khi cascade, Bean Validation có `@ConvertGroup` theo đúng đường `@Valid`. Đừng đưa `@ConvertGroup` vào mọi container khi hợp đồng không đòi hỏi chuyển group.

## 13. Những lỗi thường gặp khi viết container element constraint

1. **Đặt `@NotBlank` trên toàn bộ List:** `@NotBlank List<String>` sai kiểu constraint; đặt vào type argument như `List<@NotBlank String>`.
2. **Chỉ dùng `@NotEmpty List<String>`:** danh sách vẫn có thể chứa `""`, `" "` hay `null`; cần ràng buộc phần tử.
3. **Chỉ dùng `List<@NotBlank String>`:** List null hoặc rỗng có thể không báo lỗi; cần `@NotNull`/`@NotEmpty` trên List theo hợp đồng.
4. **Dùng `@Valid` cho String:** `@Valid` không thay cho `@NotBlank`; String không có constraint nội tại nào để cascade tới.
5. **Quên `@Valid` trên bean element:** `List<Address>` không tự kiểm tra `Address.city` khi validate root; dùng `List<@Valid Address>`.
6. **Quên `@NotNull` trên phần tử object:** `@Valid` bỏ qua null bean; dùng `List<@NotNull @Valid Address>` nếu null element không được phép.
7. **Quên khởi động Bean Validation:** annotation trên DTO không chạy khi gọi `new`; cần `Validator.validate` hoặc integration Spring.
8. **Thiếu provider trong classpath:** chỉ có Jakarta Validation API mà không có Hibernate Validator/provider thì không thể kỳ vọng chạy đầy đủ.
9. **Nhầm cấu trúc List với field path:** index có thể xuất hiện cùng node `<list element>`; kiểm tra theo provider/integration đang dùng.
10. **Gắn annotation sai type argument của Map:** key và value là hai vị trí độc lập.
11. **Assume Optional.empty() luôn hợp lệ:** nếu type argument mang `@NotBlank` thì extractor đưa null và có thể vi phạm; `@Valid` xử lý null khác.
12. **Viết `@Valid List<@Valid Address>`:** annotation trùng trên một đường có thể khiến duyệt lặp; chọn một vị trí cascade.
13. **Gắn constraint vào custom generic chưa có extractor:** phải cung cấp `ValueExtractor` tương thích.
14. **Giả định controller nhận List trực tiếp luôn được validate:** kiểm thử Spring MVC method validation và cân nhắc DTO wrapper.
15. **Cho rằng JSON sai kiểu là lỗi @NotBlank:** deserialize/binding có thể thất bại trước Bean Validation.
16. **Tin rằng field đã validate thì mọi tầng đều an toàn:** service, message consumer, batch, repository có các điểm vào khác; cần bảo đảm validation thực sự được kích hoạt.
17. **Dùng cấu trúc lỗi không ổn định:** muốn API response nhất quán, map field/index/code tường minh thay vì hardcode tiếng Anh hay thứ tự của `Set<ConstraintViolation>`.

## 14. Checklist thực hành

1. Xác định container cần **có giá trị** (`@NotNull`), **có phần tử** (`@NotEmpty`), hoặc có giới hạn số phần tử (`@Size`).
2. Đặt constraint đúng **kiểu giá trị trích xuất**, ví dụ `List<@NotBlank String>`, `List<@Positive Integer>`, `Map<@NotBlank String, @Email String>`.
3. Với bean con, dùng `List<@Valid Address>`; thêm `@NotNull` cho element nếu cần. Không lặp `@Valid` trên cùng đường.
4. Với nested containers, đánh dấu từng cấp theo đúng yêu cầu: `List<@NotEmpty List<@NotBlank String>>`.
5. Xem xét `null` ở **ba vị trí**: container null, container rỗng, phần tử null; mỗi trường hợp có constraint khác nhau.
6. Đảm bảo provider hỗ trợ extractor; container chuẩn dùng built-in, custom container cần thiết kế `ValueExtractor`.
7. Test bean-level trực tiếp bằng `Validator.validate` với phần tử hợp lệ, rỗng, whitespace, null và nested bean.
8. Test Spring MVC thực bằng `MockMvc`, kiểm tra HTTP status và field/index vi phạm; nếu nhận JSON, test thêm lỗi deserialize khác với validation.
9. Nếu sử dụng validation groups/method validation, test nhóm áp dụng và lời gọi qua Spring integration/proxy thực sự.
10. Giữ response lỗi ổn định bằng cách phân loại lỗi container, element và nested object, tránh phụ thuộc thông điệp/locale mặc định.

### Tài liệu tham khảo

- [Jakarta Bean Validation 3.0 Specification — Container element constraints và ValueExtractor](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html).
- [Hibernate Validator 8 Reference Guide — Container element constraints](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/).
- [Spring Framework — Validation in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html).
- [Spring Framework — @RequestBody và @Valid](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html).
- [Spring Framework — Bean Validation integration](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html).
