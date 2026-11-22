# Phân biệt GroupSequence với thứ tự lỗi trong kết quả Bean Validation

## 1. Hai loại “thứ tự” hoàn toàn khác nhau

Trong Spring Framework sử dụng **Jakarta Bean Validation**, nhóm kiểm tra giúp chia ràng buộc thành các tập có mục đích khác nhau: kiểm tra dữ liệu bắt buộc, kiểm tra hình thức, kiểm tra quy tắc sâu. Khi dùng `@GroupSequence`, developer có thể yêu cầu nhóm trước **đạt hết** rồi mới chuyển sang nhóm tiếp theo.

Tuy nhiên, thứ tự **thực thi nhóm constraint** không đồng nghĩa thứ tự **các phần tử lỗi được trả ra**.

**Quy tắc cần nhớ:**

1. **`@GroupSequence`**: xác định **thứ tự đánh giá giữa các nhóm validation** và cơ chế **dừng trước nhóm phía sau nếu nhóm hiện tại có ít nhất một vi phạm**.
2. **`Validator.validate(...)`**: trả **`Set<ConstraintViolation<T>>`**, tức tập vi phạm; **không có cam kết thứ tự duyệt các lỗi**.
3. Trong **một nhóm**, các constraint cũng không có thứ tự thực thi được chuẩn bảo đảm, trừ khi có một quy tắc khác được xác định trong chuẩn và áp dụng phù hợp. Group sequence không biến các constraint cùng nhóm thành hàng đợi `A → B → C`.
4. Nếu cần **thứ tự lỗi hiển thị ổn định** (cho REST API, form hoặc kiểm thử), ứng dụng phải **sắp xếp** kết quả hoặc định nghĩa quy tắc ưu tiên ở tầng trình bày. `@GroupSequence` không làm việc này.
5. Khi một nhóm trong sequence thất bại, **không có nghĩa chỉ còn một lỗi**. Trong cấu hình validation thông thường, tập có thể chứa **nhiều vi phạm thuộc nhóm đầu tiên bị lỗi**.

Ví dụ mô hình:

~~~text
@GroupSequence({Presence, Shape, Business})
          |
          v
  Presence: bắt buộc nhập?
          |
     +----+----+
     |         |
  có lỗi     không lỗi
     |         |
    DỪNG      v
          Shape: đúng độ dài/ngưỡng?
                |
           +----+----+
           |         |
         có lỗi    không lỗi
           |         |
          DỪNG       v
               Business: quy tắc sâu?
                         |
                      trả kết quả

Kết quả của mỗi lần validate:
      Set<ConstraintViolation<T>>
                |
                | không đảm bảo thứ tự
                v
   sort / map / trình bày cho client
~~~

Một ứng dụng có thể có sequence **đúng** nhưng vẫn trả JSON lỗi với thứ tự **khác** giữa hai lần chạy. Đây không phải lỗi của `@GroupSequence` mà là nhầm lẫn giữa lịch đánh giá và biểu diễn tập kết quả.

## 2. Kiến thức nền: group là gì?

Mỗi constraint Jakarta Bean Validation có thuộc tính `groups`, có thể chỉ rõ constraint thuộc nhóm nào.

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

interface PresenceChecks {}
interface ShapeChecks {}

class UserRequest {

    @NotBlank(groups = PresenceChecks.class)
    @Size(min = 3, max = 12, groups = ShapeChecks.class)
    String username;
}
~~~

Đây là **đoạn minh họa**, chưa phải chương trình độc lập. `@NotBlank` thuộc `PresenceChecks`, còn `@Size` thuộc `ShapeChecks`. Hai nhóm có thể được yêu cầu độc lập.

~~~java
validator.validate(request, PresenceChecks.class);
validator.validate(request, ShapeChecks.class);
~~~

Với `request.username = ""`:

- `PresenceChecks`: `@NotBlank` thất bại.
- `ShapeChecks`: `@Size(min=3)` thất bại.
- Nếu chỉ validate nhóm `PresenceChecks`, nhóm `ShapeChecks` **không tự chạy**.
- Nếu gọi `validator.validate(request)` không truyền group, nhóm mặc định là `jakarta.validation.groups.Default`. Trong ví dụ này các constraint **đều gắn group riêng**, nên không có ràng buộc nào của `UserRequest.username` thuộc `Default` chỉ do các annotation đã nêu.

### Cú pháp và phạm vi nhóm

Nhóm thường là một **marker interface** không có method:

~~~java
public interface PresenceChecks {}
public interface ShapeChecks {}
public interface BusinessChecks {}
~~~

Annotation có thể thuộc nhiều nhóm:

~~~java
@NotNull(groups = {PresenceChecks.class, BusinessChecks.class})
private String reference;
~~~

Một constraint có thể xuất hiện trong nhiều nhóm; khi các nhóm được bao trong sequence, chuẩn tránh đánh giá lại một constraint đã được xử lý ở nhóm trước. Không thiết kế logic nghiệp vụ dựa trên việc cùng một validator chắc chắn được gọi nhiều lần chỉ vì liệt kê group nhiều lần.

**Phân biệt group inheritance** với group sequence: `interface AdvancedChecks extends PresenceChecks {}` tạo quan hệ kế thừa nhóm, nhưng không tự định nghĩa thứ tự “Presence trước, Advanced sau”. Muốn thứ tự và dừng theo giai đoạn, dùng `@GroupSequence` đúng hợp đồng.

## 3. Không có GroupSequence: nhiều nhóm không có thứ tự đánh giá được bảo đảm

Xét lời gọi:

~~~java
validator.validate(request,
    PresenceChecks.class,
    ShapeChecks.class,
    BusinessChecks.class);
~~~

Nhiều người nghĩ Java varargs giữ thứ tự nên provider sẽ chạy lần lượt `Presence → Shape → Business` và dừng khi Presence có lỗi. **Điều này sai.**

Tham số varargs xác định **các nhóm cần kiểm tra**, không định nghĩa trình tự dừng. Theo Jakarta Bean Validation, khi không có `@GroupSequence`, thứ tự đánh giá các constraint/nhóm **không bị ràng buộc**. Các lỗi thuộc nhiều nhóm có thể cùng xuất hiện trong tập kết quả.

Điều này đúng ngay cả khi:

~~~java
validator.validate(request,
    BusinessChecks.class,
    PresenceChecks.class);
~~~

được đổi thứ tự đối số. Sự thay đổi thứ tự đối số **không phải** một cơ chế ưu tiên validation.

So sánh:

| Cách gọi | Nhóm được yêu cầu | Có thứ tự và dừng nhóm sau? |
| --- | --- | --- |
| `validate(bean)` | `Default` | Không, trừ khi nhóm Default của class đã định nghĩa lại sequence. |
| `validate(bean, PresenceChecks.class)` | Chỉ Presence và nhóm inherited phù hợp | Không có giai đoạn sau để dừng. |
| `validate(bean, PresenceChecks.class, ShapeChecks.class)` | Cả hai | **Không bảo đảm** thứ tự/dừng. |
| `validate(bean, OrderedChecks.class)` | Các nhóm trong sequence đã khai báo | **Có**, theo trình tự và quy tắc dừng. |
| `validate(bean, Default.class, BusinessChecks.class)` | Default và Business | Không tạo sequence chỉ bởi vị trí varargs. |

**Muốn có trình tự**, hãy định nghĩa một nhóm sequence được annotate `@GroupSequence` rồi yêu cầu đúng nhóm đó; đừng thay thứ tự annotation ở field hoặc thứ tự tham số varargs.

## 4. GroupSequence thực sự làm gì?

Annotation là `jakarta.validation.GroupSequence`:

~~~java
import jakarta.validation.GroupSequence;

interface PresenceChecks {}
interface ShapeChecks {}
interface BusinessChecks {}

@GroupSequence({
    PresenceChecks.class,
    ShapeChecks.class,
    BusinessChecks.class
})
interface OrderedChecks {}
~~~

Ở đây `OrderedChecks` là **interface đại diện cho một chuỗi nhóm**, không phải một field constraint. Lời gọi:

~~~java
validator.validate(request, OrderedChecks.class);
~~~

có nghĩa:

1. Xét constraint thuộc `PresenceChecks`.
2. Nếu Presence sinh **một hoặc nhiều violation**, trả kết quả của đợt kiểm tra phù hợp và **không chạy `ShapeChecks` lẫn `BusinessChecks`** trong sequence.
3. Nếu Presence đạt, xét `ShapeChecks`.
4. Nếu Shape sinh violation, **không chạy `BusinessChecks`**.
5. Nếu hai nhóm trước đạt, xét `BusinessChecks`.
6. Nếu cả ba đạt thì tập vi phạm của sequence rỗng.

**Không phải dừng ngay khi phát hiện constraint đầu tiên sai trong nhóm.** Với provider ở chế độ thông thường, Presence có hai constraint sai thì bạn có thể nhận cả hai lỗi thuộc Presence. Điều được `@GroupSequence` bảo đảm là **không đánh giá những nhóm sau một nhóm đã không đạt**, chứ không phải “mỗi lần chỉ trả một lỗi”.

Trường hợp provider bật **fail-fast** (đặc thù Hibernate Validator) có thể dừng sau lỗi đầu tiên được phát hiện. Fail-fast và GroupSequence là hai tính năng khác nhau; mục 15 phân biệt cụ thể.

### Điều kiện định nghĩa sequence đúng

- Interface chứa `@GroupSequence` nên là một marker interface **không extends một group khác**.
- Không gắn constraint với `groups = OrderedChecks.class` trên field; hãy gắn constraint vào **group thành phần**. Sequence chỉ **gộp các nhóm và quy định thứ tự**.
- Không tạo sequence vòng tròn trực tiếp/gián tiếp, kể cả qua group inheritance. Khi provider phát hiện chu trình, `GroupDefinitionException` được ném.
- Một group thành phần có thể được tạo từ kế thừa hoặc sequence khác, nhưng thứ tự của toàn bộ cấu trúc vẫn phải nhất quán.
- `@GroupSequence` không phải `@SequenceGenerator` của JPA, cũng không phải chú thích sort kết quả trong Java Collection.

## 5. Tại sao Set<ConstraintViolation<T>> không có thứ tự?

Jakarta Validator định nghĩa chữ ký:

~~~java
<T> Set<ConstraintViolation<T>> validate(
    T object, Class<?>... groups);
~~~

`Set` biểu diễn các phần tử vi phạm, **không hứa thứ tự ổn định** như `List`. Có thể dùng `Set.of(...)`, `HashSet` hoặc implementation provider khác với cách lặp khác nhau; API không yêu cầu provider trả `LinkedHashSet` theo thứ tự phát hiện. Vì thế:

~~~java
for (ConstraintViolation<UserRequest> error : errors) {
    System.out.println(error.getMessage());
}
~~~

không bảo đảm một quy luật “lỗi bắt buộc đứng trước lỗi độ dài”, ngay cả khi một nhóm đã được chạy trước nhóm khác. Nếu lỗi từ một sequence chỉ thuộc nhóm đầu tiên bị lỗi, **các lỗi trong chính nhóm đó vẫn không có thứ tự được chuẩn quy định**.

Đừng viết test:

~~~java
// KHÔNG NÊN: kỳ vọng phần tử đầu tiên là lỗi ưu tiên.
String first = errors.iterator().next().getMessage();
assertEquals("username is required", first);
~~~

đặc biệt khi tập có nhiều hơn một phần tử. Đừng cố “fix” bằng cách chuyển sang `ArrayList<>(errors)` rồi đọc index 0: danh sách này vẫn kế thừa thứ tự tùy ý từ `Set`.

### Cách đúng để in ra ổn định

~~~java
errors.stream()
    .map(v -> v.getPropertyPath() + " -> " + v.getMessage())
    .sorted()
    .forEach(System.out::println);
~~~

Đoạn minh họa này sắp xếp theo **chuỗi kết quả**, phù hợp cho ví dụ ngắn. Trong API sản phẩm, tốt hơn là sắp xếp theo **field/path, mã lỗi và mức ưu tiên đã định nghĩa**, không dựa vào văn bản thông điệp đã dịch.

**Thứ tự lỗi được hiển thị** là một quyết định trình bày; nó không nói constraint nào đã được đánh giá trước trong validator.

## 6. Bốn tình huống cần dự đoán đúng tập lỗi

Giả sử có ba group:

- **Presence:** username khác null/rỗng/trắng, age khác null, code không trắng.
- **Shape:** username dài 3–8 đơn vị UTF-16, age ít nhất 18.
- **Business:** code có định dạng `[A-Z][A-Z0-9]{3,7}`, tức dài 4–8 ký tự ASCII, bắt đầu bằng chữ hoa.

Sequence: `Presence → Shape → Business`.

| Dữ liệu | Presence | Shape | Business | Lỗi nhận khi validate sequence |
| --- | --- | --- | --- | --- |
| `username="", age=null, code="A123"` | **2 lỗi** | Bỏ qua | Bỏ qua | 2 lỗi Presence. |
| `username="Al", age=16, code="A123"` | Đạt | **2 lỗi** | Bỏ qua | 2 lỗi Shape. |
| `username="Alice", age=20, code="bad"` | Đạt | Đạt | **1 lỗi** | 1 lỗi Business. |
| `username="Alice", age=20, code="A123"` | Đạt | Đạt | Đạt | Tập rỗng. |

Nếu dữ liệu `username="Al", age=16, code="bad"` được kiểm tra **cả ba group qua varargs**, có thể nhận **3 lỗi**: hai ở Shape và một ở Business. Nhưng khi kiểm tra **`OrderedChecks.class`**, nhận **2 lỗi Shape**, vì Business bị bỏ qua.

**Phát biểu chính xác:** GroupSequence ảnh hưởng **những lỗi nào được tạo ra** nhờ điều khiển giai đoạn được chạy; nó **không áp một thứ tự sắp xếp** lên các lỗi được tạo.

## 7. Ví dụ chạy được: Java 17 + Hibernate Validator 8

Ví dụ dưới đây kiểm tra đúng sự khác nhau giữa trình tự group và thứ tự lỗi trả ra. Chạy bằng **Java 17**, **Maven**, **Jakarta Bean Validation 3.0 API** và **Hibernate Validator 8.0.6.Final** (provider). Không cần Spring MVC hay web server để quan sát hợp đồng cơ bản.

Cấu trúc thư mục:

~~~text
group-sequence-demo/
├── pom.xml
└── src/
    ├── main/java/demo/GroupSequenceDemo.java
    └── test/java/demo/GroupSequenceDemoTest.java
~~~

### 7.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>group-sequence-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.6.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish.expressly</groupId>
            <artifactId>expressly</artifactId>
            <version>5.0.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`hibernate-validator` cung cấp implementation để chạy Jakarta Validation, còn `expressly` cung cấp EL phục vụ message interpolation trong ứng dụng Java SE standalone. Ở dự án Spring Boot dùng dependency management, thường nên dùng `spring-boot-starter-validation` và để BOM quản lý phiên bản thay vì cố định bộ dependency như ví dụ Maven này.

### 7.2. src/main/java/demo/GroupSequenceDemo.java

~~~java
package demo;

import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.GroupSequence;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public class GroupSequenceDemo {

    public interface PresenceChecks {}
    public interface ShapeChecks {}
    public interface BusinessChecks {}

    @GroupSequence({
        PresenceChecks.class,
        ShapeChecks.class,
        BusinessChecks.class
    })
    public interface OrderedChecks {}

    public static final class Registration {
        @NotBlank(
            groups = PresenceChecks.class,
            message = "username required")
        @Size(
            min = 3, max = 8,
            groups = ShapeChecks.class,
            message = "username length 3..8")
        private final String username;

        @NotNull(
            groups = PresenceChecks.class,
            message = "age required")
        @Min(
            value = 18,
            groups = ShapeChecks.class,
            message = "age must be at least 18")
        private final Integer age;

        @NotBlank(
            groups = PresenceChecks.class,
            message = "code required")
        @Pattern(
            regexp = "[A-Z][A-Z0-9]{3,7}",
            groups = BusinessChecks.class,
            message = "code format invalid")
        private final String code;

        public Registration(
                String username, Integer age, String code) {
            this.username = username;
            this.age = age;
            this.code = code;
        }
    }

    static void show(
            String label,
            Set<? extends ConstraintViolation<?>> errors) {

        System.out.println(label + "=" + errors.size());

        // Chuỗi được sort để stdout không phụ thuộc thứ tự Set.
        errors.stream()
            .map(v -> v.getPropertyPath() + " -> " + v.getMessage())
            .sorted()
            .forEach(System.out::println);
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            show("presence-stop", validator.validate(
                new Registration("", null, "A123"),
                OrderedChecks.class));

            show("shape-stop", validator.validate(
                new Registration("Al", 16, "A123"),
                OrderedChecks.class));

            show("business-stop", validator.validate(
                new Registration("Alice", 20, "bad"),
                OrderedChecks.class));

            show("valid", validator.validate(
                new Registration("Alice", 20, "A123"),
                OrderedChecks.class));

            Registration mixed =
                new Registration("Al", 16, "bad");

            // Ba group được yêu cầu, KHÔNG phải một sequence.
            show("plain-groups", validator.validate(
                mixed,
                PresenceChecks.class,
                ShapeChecks.class,
                BusinessChecks.class));

            // Cùng object nhưng yêu cầu sequence rõ ràng.
            show("ordered-groups", validator.validate(
                mixed, OrderedChecks.class));

            // Không annotation nào trong ví dụ thuộc Default.
            show("default-only", validator.validate(
                new Registration("", null, "bad")));
        }
    }
}
~~~

### 7.3. Chạy và kết quả

Chạy tại thư mục có `pom.xml` (cần JDK 17+, Maven và quyền tải dependency lần đầu):

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.GroupSequenceDemo
~~~

Stdout **do chương trình tạo ra**, không tính log riêng của Maven/Hibernate Validator nếu runtime in thêm:

~~~text
presence-stop=2
age -> age required
username -> username required
shape-stop=2
age -> age must be at least 18
username -> username length 3..8
business-stop=1
code -> code format invalid
valid=0
plain-groups=3
age -> age must be at least 18
code -> code format invalid
username -> username length 3..8
ordered-groups=2
age -> age must be at least 18
username -> username length 3..8
default-only=0
~~~

Giải thích:

1. `presence-stop`: username là `""` và age là null nên hai constraint Presence thất bại. Shape và Business **không được chạy** trong sequence.
2. `shape-stop`: Presence đạt, username `"Al"` dài 2 và age 16 không đạt Shape; Business không chạy. Có **hai lỗi thuộc cùng nhóm**, nhưng thứ tự hai dòng sau `sorted()` do chúng ta quyết định, không phải do GroupSequence.
3. `business-stop`: Presence và Shape đạt, code `"bad"` không khớp pattern; nhận một lỗi Business.
4. `valid`: mọi giai đoạn đạt → 0.
5. `plain-groups`: ba group được yêu cầu cùng nhau, không đặt trong sequence; có hai lỗi Shape và một lỗi Business → 3.
6. `ordered-groups`: cùng object `mixed` nhưng dùng sequence, Shape thất bại nên Business không chạy → 2.
7. `default-only`: mọi constraint trong ví dụ được gán group rõ ràng, không có constraint `Default`. Gọi `validate(bean)` không tự bao gồm `OrderedChecks` nên nhận 0 ngay cả khi nhiều dữ liệu sai theo các group custom. Đây là một **bẫy thiết kế quan trọng**, không phải bằng chứng đối tượng hợp lệ theo mọi quy tắc.

**Đừng bỏ `.sorted()`** rồi vẫn khẳng định thứ tự các dòng trên chính xác: nội dung và số lỗi giữ ý nghĩa, nhưng thứ tự duyệt từng violation chưa được bảo đảm. Với test chuẩn, hãy so sánh số lượng và tập path/message hoặc danh sách đã sort, không đoán thứ tự từ provider.

## 8. Kiểm thử với JUnit 5

Tệp `src/test/java/demo/GroupSequenceDemoTest.java`:

~~~java
package demo;

import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class GroupSequenceDemoTest {

    @Test
    void stopsAfterPresenceAndCanReturnMoreThanOneError() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var value = new GroupSequenceDemo.Registration(
                "", null, "A123");

            var errors = validator.validate(
                value, GroupSequenceDemo.OrderedChecks.class);

            assertEquals(2, errors.size());
            assertEquals(
                Set.of("username", "age"),
                errors.stream()
                    .map(v -> v.getPropertyPath().toString())
                    .collect(Collectors.toSet()));
        }
    }

    @Test
    void laterGroupIsSkippedWhenShapeFails() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var value = new GroupSequenceDemo.Registration(
                "Al", 16, "bad");

            var errors = validator.validate(
                value, GroupSequenceDemo.OrderedChecks.class);

            assertEquals(2, errors.size());
            assertEquals(
                Set.of("username", "age"),
                errors.stream()
                    .map(v -> v.getPropertyPath().toString())
                    .collect(Collectors.toSet()));
        }
    }

    @Test
    void passingEarlierGroupsAllowsBusiness() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var value = new GroupSequenceDemo.Registration(
                "Alice", 20, "bad");

            var errors = validator.validate(
                value, GroupSequenceDemo.OrderedChecks.class);

            assertEquals(1, errors.size());
            assertEquals("code",
                errors.iterator().next()
                    .getPropertyPath().toString());
        }
    }

    @Test
    void unorderedVarargsAndSequenceYieldDifferentSets() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var value = new GroupSequenceDemo.Registration(
                "Al", 16, "bad");

            var unordered = validator.validate(
                value,
                GroupSequenceDemo.PresenceChecks.class,
                GroupSequenceDemo.ShapeChecks.class,
                GroupSequenceDemo.BusinessChecks.class);

            var sequenced = validator.validate(
                value,
                GroupSequenceDemo.OrderedChecks.class);

            assertEquals(3, unordered.size());
            assertEquals(2, sequenced.size());
            assertTrue(unordered.stream()
                .anyMatch(e -> e.getPropertyPath().toString()
                    .equals("code")));
            assertTrue(sequenced.stream()
                .noneMatch(e -> e.getPropertyPath().toString()
                    .equals("code")));
        }
    }

    @Test
    void defaultIsNotTheCustomSequence() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var value = new GroupSequenceDemo.Registration(
                "", null, "bad");

            assertTrue(validator.validate(value).isEmpty());
            assertFalse(validator.validate(
                value,
                GroupSequenceDemo.OrderedChecks.class).isEmpty());
        }
    }

    @Test
    void validValuesPassAllStages() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var value = new GroupSequenceDemo.Registration(
                "Alice", 20, "A123");

            assertTrue(validator.validate(
                value,
                GroupSequenceDemo.OrderedChecks.class).isEmpty());
        }
    }

    @Test
    void normalizeErrorOrderExplicitlyForPresentation() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var value = new GroupSequenceDemo.Registration(
                "", null, "A123");

            var errors = validator.validate(
                value, GroupSequenceDemo.OrderedChecks.class);

            var sortedMessages = errors.stream()
                .map(ConstraintViolation::getMessage)
                .sorted()
                .toList();

            assertEquals(
                java.util.List.of("age required", "username required"),
                sortedMessages);
        }
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Với cấu hình mẫu, kết quả mong đợi: **7 test thành công, 0 thất bại**. Các test quan trọng:

- Không xác nhận “Presence chạy trước” bằng thứ tự phần tử `Set`; xác nhận **Shape/Business không được trả lỗi khi Presence thất bại**.
- Không xác nhận “chỉ có một lỗi” khi một giai đoạn thất bại; kiểm tra **hai lỗi cùng nhóm**.
- Với một object nhất định, so sánh **varargs các group thường** với **group sequence**.
- Khi cần thứ tự output, **chủ động sort** rồi mới so sánh List.

Ví dụ dùng Hibernate Validator mặc định, không bật fail-fast. Trong một cấu hình provider tùy biến có fail-fast hoặc constraint khác, số lỗi có thể thay đổi; hãy chốt điều kiện kiểm thử trong test setup và không suy ra số lỗi ngoài những constraint đã khai báo.

## 9. @GroupSequence trên interface khác @GroupSequence trên class

Có hai cách dùng annotation **cùng tên** nhưng ý nghĩa khác nhau.

### 9.1. Interface sequence: người gọi yêu cầu nhóm đó

~~~java
@GroupSequence({
    jakarta.validation.groups.Default.class,
    ShapeChecks.class,
    BusinessChecks.class
})
public interface CompleteChecks {}
~~~

Khi khai báo trên interface, `CompleteChecks` đại diện một tổ hợp có thứ tự. Muốn nó có hiệu lực, gọi:

~~~java
validator.validate(bean, CompleteChecks.class);
~~~

Nếu chỉ gọi `validator.validate(bean)` thì Jakarta mặc định kiểm tra `Default`, **không tự biết** bạn muốn `CompleteChecks`, trừ khi một class liên quan đã định nghĩa lại default group sequence.

Việc đưa `Default.class` vào **interface sequence** là hợp lệ. Đây là cách kết hợp các ràng buộc thông thường của Default với các nhóm sâu, và vẫn dừng ở nhóm đầu tiên có vi phạm.

### 9.2. Class sequence: định nghĩa lại Default của class đó

Trường hợp muốn mọi lời gọi `validator.validate(invoice)` tự tuân theo thứ tự nhất định:

~~~java
import jakarta.validation.GroupSequence;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

interface InvoiceDeepChecks {}

@GroupSequence({Invoice.class, InvoiceDeepChecks.class})
class Invoice {

    @NotBlank(message = "invoice number required")
    String number;

    @Min(value = 1, groups = InvoiceDeepChecks.class,
         message = "items must be positive")
    int itemCount;
}
~~~

Ở đây **`@GroupSequence` được đặt trên `class Invoice`**. Khi validate `Default` của `Invoice`:

1. Nhóm `Invoice.class`, đại diện cho các constraint mặc định được khai báo trên class, được xét trước. `number` trống → dừng.
2. Chỉ nếu phần mặc định đạt thì mới xét `InvoiceDeepChecks` cho `itemCount`.

**Quy tắc rất quan trọng:** Khi định nghĩa lại Default cho class `Invoice`, sequence **phải chứa `Invoice.class`**, không được thay bằng `Default.class`:

~~~java
// KHÔNG HỢP LỆ khi đặt trực tiếp lên class Invoice:
@GroupSequence({
    jakarta.validation.groups.Default.class,
    InvoiceDeepChecks.class
})
class Invoice { }
~~~

Đây là ví dụ **cố ý sai, không được chép vào dự án runnable**. Nó tạo dependency vòng hoặc thiếu chính class trong default sequence theo quy tắc Jakarta, có thể dẫn tới `GroupDefinitionException` khi provider xử lý metadata/validation.

**Nhớ sự đối lập:**

| Annotation đặt ở | Có thể ghi Default trong sequence? | Nhóm dùng khi validate |
| --- | --- | --- |
| Interface `CompleteChecks` | Có | Gọi `validate(bean, CompleteChecks.class)`. |
| Class `Invoice` để redefine Default | Phải dùng **`Invoice.class`** thay cho `Default.class` | `validate(invoice)` có thể dùng default sequence mới cho class đó. |

### 9.3. Default override là cục bộ, không tự truyền toàn bộ sequence sang bean con

Một class định nghĩa lại Default của chính nó **không làm các object được cascade `@Valid` tự động nhận một nhóm sequence mới giống hệt class cha**. Quy tắc group propagation xác định nhóm truyền theo từng quan hệ; trong những tình huống chuẩn, Default của object cha được propagate dưới dạng `Default` sang bean con. Bean con sẽ áp dụng default-group semantics riêng của nó nếu đã cấu hình.

Nếu cần đổi group khi cascade, Bean Validation có `@ConvertGroup`, nhưng đây là khái niệm khác với sort lỗi. Hãy kiểm thử hành vi thực tế với object graph, đặc biệt khi kết hợp group conversion, sequence và Default override.

## 10. Nhiều constraint trong một nhóm không được @GroupSequence sắp xếp

Ví dụ:

~~~java
interface PresenceChecks {}

class AccountForm {
    @NotBlank(groups = PresenceChecks.class)
    String username;

    @NotBlank(groups = PresenceChecks.class)
    String email;

    @NotNull(groups = PresenceChecks.class)
    Integer age;
}
~~~

Nếu ba field đều thiếu, một lần validate Presence có thể tạo ba violation. `@GroupSequence({PresenceChecks.class, ...})` **không** cho bạn một thứ tự “username trước email trước age”.

Tương tự, viết annotation trên một field theo thứ tự:

~~~java
@NotBlank(groups = PresenceChecks.class)
@Size(min = 3, groups = PresenceChecks.class)
String name;
~~~

**không** có nghĩa `@NotBlank` chắc chắn chạy trước `@Size`. Cả hai cùng thuộc một group và đều có thể thất bại khi `name=""`. Muốn chia thành hai giai đoạn, phải tách chúng vào hai nhóm thật sự khác và định nghĩa sequence, nhưng chỉ nên làm vậy khi nghiệp vụ **cần kiểm tra có điều kiện**, không phải đơn thuần muốn một thông điệp “đứng đầu” trong UI.

### GroupSequence cũng không định nghĩa thứ tự @Valid đi sâu

Nếu object chứa nhiều nested bean có `@Valid`, thứ tự cụ thể provider duyệt các thuộc tính/collection cũng không phải cơ chế ưu tiên lỗi UI. Một sequence xác định **thứ tự group** theo mô hình object graph được chuẩn xử lý, nhưng không biến mọi field và phần tử lồng nhau thành một chuỗi đánh giá có thứ tự cố định.

Đừng dùng side effect trong `ConstraintValidator.isValid(...)` để theo dõi thứ tự hoặc ghi trạng thái phụ thuộc validator khác. Validator nên không có side effect quan trọng; thứ tự thực thi không phải một hợp đồng tuần tự hóa nghiệp vụ.

## 11. Nếu chỉ muốn hiển thị lỗi theo thứ tự ưu tiên, đừng dùng GroupSequence

Giả sử form có ba lỗi: tên không hợp lệ, email không hợp lệ và tuổi không hợp lệ. Yêu cầu chỉ là hiển thị:

1. Tên.
2. Email.
3. Tuổi.

Nếu nghiệp vụ vẫn muốn **hiển thị tất cả ba lỗi trong cùng response**, việc chia chúng thành ba group rồi dùng GroupSequence có thể gây **mất hai lỗi sau** nếu group đầu thất bại. Đây thường là quyết định **sai mục tiêu**.

Thay vì vậy:

~~~java
record ApiError(
    String field,
    String code,
    String message
) {}
~~~

Sau khi validate tất cả nhóm liên quan, ánh xạ các `ConstraintViolation` thành danh sách, rồi sort theo **bảng ưu tiên của giao diện**. Chẳng hạn:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import jakarta.validation.ConstraintViolation;

static <T> List<ApiError> toApiErrors(
        Set<ConstraintViolation<T>> errors) {

    Map<String, Integer> fieldRank = Map.of(
        "username", 0,
        "email", 1,
        "age", 2
    );

    return errors.stream()
        .map(v -> new ApiError(
            v.getPropertyPath().toString(),
            v.getConstraintDescriptor().getAnnotation()
                .annotationType().getSimpleName(),
            v.getMessage()))
        .sorted(Comparator
            .comparingInt(
                (ApiError e) ->
                    fieldRank.getOrDefault(e.field(), 999))
            .thenComparing(ApiError::field)
            .thenComparing(ApiError::code)
            .thenComparing(ApiError::message))
        .toList();
}
~~~

Đây là **đoạn minh họa phép ánh xạ** cần được đặt trong class chứa `ApiError` và imports liên quan, không phải file Java chạy độc lập. Sort theo rank đã xác định, sau đó dùng field/code/message làm các khóa phụ để ổn định thứ tự. Nếu API có nhiều violation cùng một field, vẫn giữ đủ các phần tử.

**Không dựa vào `getMessage()` làm mã lỗi ổn định.** Message có thể thay đổi do locale và message interpolation. Nếu cần công khai contract lỗi lâu dài, hãy định nghĩa mã lỗi nghiệp vụ riêng rồi map từ metadata constraint tương ứng.

Nếu chỉ muốn **một thông điệp trên mỗi field**, có thể thêm chiến lược chọn lỗi ưu tiên: ví dụ `REQUIRED` trước `SIZE` trước `PATTERN`. Đó vẫn là xử lý presentation/response, không phải lý do tự động phải đặt `@GroupSequence`. Những điều kiện đắt hoặc phụ thuộc dữ liệu đã hợp lệ mới là lý do tốt để tách giai đoạn validation.

## 12. Khi nào thực sự nên dùng GroupSequence?

GroupSequence có giá trị khi **một giai đoạn cần đạt trước khi giai đoạn sau có ý nghĩa**:

- **Kiểm tra cơ bản trước kiểm tra sâu:** chỉ chạy consistency/business constraint khi các field bắt buộc và dạng dữ liệu cơ bản đã đạt.
- **Tránh tính toán tốn tài nguyên:** validation của nhóm sau có thể nặng hơn; chỉ muốn đánh giá nó khi đầu vào đã đủ tốt. Tuy nhiên validator thường không nên tự thực hiện I/O hay side effect lớn.
- **Triển khai chính sách theo giai đoạn:** dữ liệu phải đạt `PresenceChecks` rồi `ShapeChecks`, cuối cùng `BusinessChecks`.
- **Định nghĩa lại Default cho bean cụ thể:** muốn `validate(bean)` mặc định đã kiểm tra qua các giai đoạn thích hợp của bean đó.

GroupSequence **không phù hợp** nếu nhu cầu chỉ là:

- Sắp xếp thông điệp lỗi theo thứ tự tên field.
- Ép một lỗi duy nhất hiển thị.
- Thứ tự các dòng JSON ổn định giữa các lần chạy.
- Dự đoán constraint nào trong cùng group chạy trước.
- Bắt tất cả lỗi trên mọi group khi group trước đã có vi phạm.

Muốn hiển thị **mọi lỗi trong một lượt**, hãy xem lại chính sách chạy đồng thời các group (không dùng sequence để short-circuit), sau đó sort kết quả. Muốn thông báo **được chia giai đoạn** theo logic, hãy dùng sequence và giải thích rõ cho người dùng vì sao lỗi của giai đoạn sâu chưa xuất hiện.

## 13. Tương tác với @Valid, collection và nhóm lồng nhau

Khi có `@Valid`, Bean Validation có thể đi vào các object con không null. Các group được yêu cầu và group sequence ảnh hưởng việc kiểm tra các constraint của object graph.

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

class Order {
    @NotNull(groups = PresenceChecks.class)
    @Valid
    Customer customer;
}
~~~

Nếu `customer == null`, `@Valid` không tự tạo bean con; `@NotNull` thuộc `PresenceChecks` tạo vi phạm. Nếu Presence thất bại trong sequence, các giai đoạn sau bị bỏ qua.

Nếu `customer != null`, các ràng buộc của `Customer` có thể được cascade theo group semantics áp dụng. Trên nested bean cũng có thể có `@GroupSequence` hoặc `@ConvertGroup`. Không nên kết luận rằng tất cả constraints của nested bean luôn chạy chỉ vì parent có `@Valid`.

### Ranh giới quan trọng

- `@Valid` là **cascade**, không phải một constraint như `@NotNull`.
- Group sequence đặt trên parent không đơn giản là thứ tự duyệt các phần tử list con.
- `@ConvertGroup(from=..., to=...)` có thể đổi group khi đi vào quan hệ cascade; quy tắc từ `from` áp dụng trên group đã được mở rộng theo sequence. Không đặt tên một sequence vào `from` rồi kỳ vọng nó được xử lý như một group chưa mở rộng.
- Khi hai object con có lỗi trong cùng giai đoạn, Set tổng hợp vẫn không có thứ tự hiển thị được bảo đảm.
- Nếu một class định nghĩa lại Default, định nghĩa lại này là cục bộ; không tự mang toàn bộ chuỗi sang object liên quan.

**Thực hành:** với object graph có nhiều tầng, viết test riêng kiểm tra **những nhóm nào đã được chạy/không chạy**, **số violation** và **path**. Không viết test chỉ nhìn vào thứ tự của `Set` để suy ra traversal.

## 14. GroupSequence khác fail-fast và @ReportAsSingleViolation

Ba tính năng có thể cùng làm **số lỗi ít đi**, nhưng bản chất khác nhau:

| Tính năng | Đang điều khiển điều gì? | Có bảo đảm thứ tự lỗi Set? |
| --- | --- | --- |
| `@GroupSequence` (Jakarta chuẩn) | Thứ tự **nhóm** và dừng **nhóm phía sau** khi nhóm trước có vi phạm. | **Không**. |
| Hibernate Validator **fail-fast** (provider-specific) | Có thể dừng toàn bộ validation sau một vi phạm được phát hiện, không xác định vi phạm nào sẽ là đầu tiên. | **Không**. |
| `@ReportAsSingleViolation` (Jakarta chuẩn) | Với một **composed constraint**, thay các lỗi của constraint thành phần bằng một vi phạm tổng hợp. | **Không**. |
| `Comparator`/sort của ứng dụng | Thứ tự danh sách được **trình bày**, không làm thay đổi constraint nào đã được đánh giá. | **Có thứ tự sau khi sort**, nhưng Set nguyên thủy vẫn không có thứ tự bảo đảm. |

### Ví dụ mô tả

Giả sử nhóm Presence có ba constraint sai:

- Chỉ dùng `@GroupSequence`: có thể nhận đủ ba lỗi của nhóm Presence; Shape và Business không chạy.
- Bật Hibernate Validator fail-fast: có thể nhận chỉ **một lỗi** do provider dừng khi gặp vi phạm đầu tiên (không bảo đảm đó là constraint nào).
- Sử dụng một composed constraint có `@ReportAsSingleViolation`: nhiều thành phần bên trong composite có thể tạo **một lỗi tổng hợp** cho constraint ấy, dù các constraint độc lập khác vẫn có thể tạo lỗi.
- Gọi `.sorted()`: vẫn cùng số lỗi và cùng nhóm được chạy; chỉ thứ tự trình bày đổi.

Đừng dùng fail-fast để “lấy lỗi ưu tiên nhất” nếu không có quy tắc ưu tiên rõ, vì provider không cam kết thứ tự constraint, trừ khi cơ chế cụ thể định nghĩa khác và được dùng đúng. Muốn lỗi ưu tiên, hãy định nghĩa chiến lược xử lý ở ứng dụng.

## 15. Cấu hình sai: GroupDefinitionException và constraint thuộc sai group

### 15.1. Tạo chu trình sequence

Ví dụ cố ý sai:

~~~java
interface Alpha {}
interface Beta {}

@GroupSequence({Alpha.class, Beta.class})
interface AThenB {}

@GroupSequence({AThenB.class, Alpha.class})
interface CyclicChecks {} // Kiểu này tự nó chưa tạo vòng.
~~~

**Lưu ý:** Đoạn code trên có thể không tạo chu trình; nó chỉ minh họa sequence lồng và sự lặp nhóm. Một **chu trình thật** xảy ra khi `A` yêu cầu sequence chứa `B`, trong khi `B` trực tiếp hoặc gián tiếp lại yêu cầu `A`. Để không làm sai hợp đồng bằng một ví dụ Java vừa dài vừa dễ lệch, hãy ghi nhớ tiêu chí thay vì coi đoạn trên là ví dụ ném exception.

Khi provider phát hiện chu trình thật sự trong group sequences/group inheritance, `GroupDefinitionException` là lỗi khai báo/cấu hình của ứng dụng, **không phải lỗi dữ liệu request của người dùng**. Không tự trả nó như “field invalid” qua HTTP 400.

### 15.2. Nhầm interface và class

~~~java
// ĐÚNG nếu khai báo trên interface:
@GroupSequence({
    jakarta.validation.groups.Default.class,
    ShapeChecks.class
})
interface CompleteChecks {}
~~~

~~~java
// ĐÚNG nếu định nghĩa lại Default ngay trên class:
@GroupSequence({
    RequestForm.class,
    ShapeChecks.class
})
class RequestForm {}
~~~

Đoạn thứ hai là **minh họa** class tối giản; trong dự án thật phải có constraint và đối tượng muốn validate. Thay `RequestForm.class` bằng `Default.class` trong annotation của chính class là sai quy tắc, có thể gây `GroupDefinitionException`.

### 15.3. Gán constraint vào sequence thay vì group thành phần

~~~java
// KHÔNG NÊN:
@NotBlank(groups = OrderedChecks.class)
String title;
~~~

Interface đại diện sequence không nên được dùng trực tiếp trong constraint declaration. Hãy gán vào `PresenceChecks.class` hoặc `ShapeChecks.class`. Cách này giúp hợp đồng “giai đoạn nào kiểm tra điều kiện này?” minh bạch.

### 15.4. Nhầm Default với mọi nhóm

~~~java
validator.validate(bean);
~~~

**Không tự gọi** mọi nhóm người dùng đã định nghĩa. Nếu constraint nào chỉ thuộc `BusinessChecks`, nó không mặc nhiên chạy trong `Default`. Muốn business group tham gia, truyền group cụ thể/sequence hoặc định nghĩa lại Default cho đúng class.

## 16. Tích hợp với Spring Framework / Spring Boot

Spring hỗ trợ Bean Validation qua Jakarta Validator và các điểm kích hoạt validation. **`@GroupSequence` là annotation Jakarta**, còn **`@Validated` là annotation Spring** giúp chọn group khi áp dụng validation tại boundary phù hợp.

Với một Spring Boot 3 project đã có parent/BOM quản lý version:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Đây là đoạn dependency cho **project Spring Boot**, không phải một `pom.xml` độc lập hoàn chỉnh.

### 16.1. Chọn group sequence cho DTO controller

~~~java
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.http.ResponseEntity;

@RestController
class RegistrationController {

    @PostMapping("/registrations")
    ResponseEntity<Void> register(
            @Validated(GroupSequenceDemo.OrderedChecks.class)
            @RequestBody
            GroupSequenceDemo.Registration request) {

        // Xử lý nghiệp vụ sau khi validation đã đạt.
        return ResponseEntity.noContent().build();
    }
}
~~~

Đây là **đoạn tích hợp Spring MVC**, không phải ứng dụng chạy độc lập. Trong ứng dụng thực tế cần đặt `Registration` vào DTO hợp lệ với cơ chế deserialization JSON (constructor/record/properties được Jackson hỗ trợ), có Bean Validation provider và các class được Spring phát hiện. Bài tập core ở mục 7 dùng `Registration` immutable cho kiểm thử Validator trực tiếp, chưa thiết kế nó làm DTO production cho Jackson.

`@Validated(OrderedChecks.class)` yêu cầu sequence rõ ràng. Nếu chỉ dùng:

~~~java
@Valid @RequestBody RegistrationRequest request
~~~

thì áp dụng nhóm `Default`, trừ khi class đã định nghĩa lại Default. `@Valid` **không** tự chọn `OrderedChecks.class` chỉ vì interface đó tồn tại.

### 16.2. Phân biệt validation error với thứ tự trả response

Với Spring MVC, khi kiểm tra `@RequestBody` object qua `@Validated`/`@Valid` thất bại, ứng dụng thường nhận `MethodArgumentNotValidException` và `BindingResult`/`FieldError` trong những điều kiện controller tương ứng. Với method validation của Spring MVC 6.1+ có constraint trực tiếp trên method parameter, có thể nhận `HandlerMethodValidationException`. Service method validation qua proxy có thể ném `ConstraintViolationException` hoặc loại exception thích ứng nếu được cấu hình.

**Không ép cast** `FieldError` thành `ConstraintViolation<?>`. Đây là các mô hình lỗi khác nhau. Tương tự, dù thứ tự group chạy đã được cố định, thứ tự phần tử trong `BindingResult.getFieldErrors()` **không nên được dùng làm hợp đồng ưu tiên hiển thị liên phiên bản/hệ thống** nếu ứng dụng cần một thứ tự API ổn định. Hãy map/sort theo field + code/priority rõ ràng.

Một handler minh họa:

~~~java
@ExceptionHandler(MethodArgumentNotValidException.class)
ResponseEntity<List<ApiError>> handle(
        MethodArgumentNotValidException ex) {

    List<ApiError> errors = ex.getBindingResult()
        .getFieldErrors().stream()
        .map(e -> new ApiError(
            e.getField(),
            e.getCode() == null ? "INVALID" : e.getCode(),
            e.getDefaultMessage()))
        .sorted(Comparator
            .comparing(ApiError::field)
            .thenComparing(ApiError::code))
        .toList();

    return ResponseEntity.badRequest().body(errors);
}
~~~

Đây là **đoạn minh họa trong `@RestControllerAdvice`**, cần các imports và record `ApiError` đã nêu ở mục 11; không phải class standalone. Sắp xếp bằng `Comparator` giúp response có trật tự dù nguồn lỗi không định nghĩa trật tự. Trong ứng dụng thực tế, nên xác định nullability của message/code, quy định mã lỗi nghiệp vụ ổn định và tránh xuất dữ liệu nhạy cảm (`rejectedValue`/`invalidValue`) ra client.

### 16.3. @Validated trên service

Với Spring method validation qua `@Validated`/`MethodValidationPostProcessor`, một method có constraint ở tham số/return value được thực thi qua Spring proxy có thể dùng group đã chọn. Tuy nhiên đây là **đường xử lý method validation** khác với việc gọi `Validator.validate(bean, OrderedChecks.class)`. Đừng kỳ vọng gọi trực tiếp `new Service().method()` cũng chạy validation AOP hoặc sequence.

Group sequence quan trọng ở cả hai đường khi **được yêu cầu** đúng cách, nhưng kiểu exception và cách chuyển violation sang response có thể khác. Hãy viết integration test theo pipeline thực sự.

## 17. Cách thiết kế test tránh sai giả định thứ tự

Bài kiểm thử tốt nên tập trung vào **nội dung tập lỗi** và **nhóm bị bỏ qua**, thay vì thứ tự tình cờ của provider.

### Test tốt

~~~java
var errors = validator.validate(
    request, OrderedChecks.class);

assertEquals(2, errors.size());
assertEquals(
    Set.of("username", "age"),
    errors.stream()
        .map(v -> v.getPropertyPath().toString())
        .collect(java.util.stream.Collectors.toSet()));
~~~

Đây là **đoạn minh họa** với `request` mang dữ liệu invalid của Presence và imports/JUnit phù hợp. Nó chứng minh hai trường vi phạm và không phụ thuộc thứ tự.

### Test không bền

~~~java
var errors = validator.validate(
    request, OrderedChecks.class);

// KHÔNG BỀN nếu errors có nhiều phần tử:
assertEquals(
    "username",
    errors.iterator().next().getPropertyPath().toString());
~~~

Test có thể pass ở một provider/JDK nhưng fail ở môi trường khác mà chính sách group sequence không thay đổi.

### Test thứ tự output ở đúng tầng

~~~java
List<String> sortedPaths = errors.stream()
    .map(v -> v.getPropertyPath().toString())
    .sorted()
    .toList();

assertEquals(List.of("age", "username"), sortedPaths);
~~~

Đoạn này kiểm tra **thứ tự sau sort**, không kiểm tra thứ tự Bean Validation chạy constraint.

### Test không nên dựa vào log của custom validator

Bạn có thể tạo custom validator `isValid` ghi log “group A” hoặc “group B” để điều tra, nhưng đừng biến log nội bộ đó thành **hợp đồng thứ tự cho các constraint trong cùng group**. Validator có thể được cache, reused, chạy qua trình duyệt object graph khác nhau; còn provider-specific fail-fast càng khiến thứ tự “lỗi đầu tiên” khó đoán.

Nên giữ ba bộ test riêng:

1. **Validation scope:** group nào được yêu cầu và có bao nhiêu loại lỗi.
2. **Short circuit:** group sau thật sự bị bỏ qua khi group trước fail.
3. **Presentation:** danh sách lỗi được sort theo tiêu chí client yêu cầu.

## 18. Các lỗi thường gặp và cách sửa

| Hiểu sai | Hậu quả | Cách đúng |
| --- | --- | --- |
| Nghĩ `@GroupSequence` sắp xếp `Set<ConstraintViolation>` | API trả lỗi khác thứ tự mong muốn. | Chủ động sort khi map sang List/JSON. |
| Nghĩ sequence chỉ trả **một** vi phạm | Bỏ qua các lỗi cùng giai đoạn. | GroupSequence dừng **các group sau**, không mặc định dừng từng constraint. |
| Truyền `validate(bean, A.class, B.class)` rồi nghĩ là `A → B` | Cả hai nhóm có thể được xét, không có short-circuit. | Định nghĩa `@GroupSequence({A.class,B.class})` và gọi sequence interface. |
| Đổi thứ tự annotation trên field để điều khiển lỗi đầu tiên | Provider không cam kết. | Group thật theo nghiệp vụ hoặc sort lỗi UI. |
| Gắn `groups=Ordered.class` trực tiếp ở constraint | Nhầm sequence interface với group thành phần. | Gắn constraint vào nhóm `Presence`/`Shape`/`Business`. |
| Định nghĩa sequence interface rồi chỉ gọi `validate(bean)` | Chỉ `Default` chạy, sequence không tự kích hoạt. | Truyền sequence hoặc redefine Default có chủ đích. |
| Đặt `@GroupSequence({Default.class, Deep.class})` trên class | Sai quy tắc redefine Default. | Sử dụng `@GroupSequence({MyClass.class, Deep.class})`. |
| Dùng sequence để sắp xếp lỗi form nhưng vẫn muốn thấy mọi lỗi | Các group sau bị bỏ qua khi nhóm trước sai. | Validate tất cả group cần thiết và sort kết quả. |
| Dùng `iterator().next()` làm lỗi ưu tiên | Thứ tự Set không được bảo đảm. | Xử lý đầy đủ, sort/rank rõ ràng. |
| Bật fail-fast và cho rằng nó chạy theo priority field | “Lỗi đầu tiên” không có ưu tiên chuẩn. | Định nghĩa policy priority ở ứng dụng. |
| Giả định bean con nhận nguyên default sequence của parent | Default redefinition là cục bộ; propagation theo group semantics. | Test @Valid/@ConvertGroup và định nghĩa Default tại đúng class. |
| Nghĩ `@Validated({A.class,B.class})` là sequence | Một mảng group không phải `@GroupSequence`. | Dùng `@Validated(Ordered.class)` nếu cần thứ tự. |
| Gộp mọi validation exception thành lỗi input 400 | `GroupDefinitionException` có thể là lỗi metadata server. | Phân loại lỗi cấu hình và lỗi dữ liệu riêng. |
| Trả raw `ConstraintViolation` với `invalidValue` trong JSON | Có thể lộ mật khẩu, dữ liệu cá nhân, cấu trúc nội bộ. | Ánh xạ sang field/code/message an toàn. |
| Chỉ test số lỗi, không test group sau bị chặn | Có thể sai group cấu hình nhưng vẫn ra cùng số lỗi. | Kiểm tra property path/message để xác định stage. |
| Lấy message để xác định code và sort chính | Message phụ thuộc locale. | Dùng mã lỗi nghiệp vụ và comparator rõ ràng. |
| Viết custom validator có side effect vì tin vào thứ tự gọi | Logic dễ sai theo provider/phiên bản. | Validator nên độc lập, chỉ kiểm tra trạng thái. |

## 19. Checklist áp dụng trong dự án thực tế

1. Liệt kê các constraint thuộc nhóm `Default`, `PresenceChecks`, `ShapeChecks` và `BusinessChecks`.
2. Xác định **ràng buộc nào cần đạt trước** khi các ràng buộc sâu hơn được đánh giá.
3. Chọn **sequence interface** nếu caller sẽ yêu cầu tường minh hoặc **Default override trên class** nếu đây là hợp đồng mặc định của bean.
4. Nếu dùng interface sequence, tránh extends group khác và không đặt constraint trực tiếp vào sequence group.
5. Nếu redefine Default trên class, nhớ dùng `@GroupSequence({MyClass.class, ...})`.
6. Không tạo sequence có chu trình, kể cả qua inheritance/nested sequence.
7. Không nhầm varargs nhiều groups với một nhóm sequence.
8. Test khi **Presence thất bại nhiều constraint**: nhận lỗi trong nhóm này, nhóm sau không được đánh giá.
9. Test khi Presence đạt nhưng Shape thất bại: Business bị bỏ qua.
10. Test khi mọi nhóm trước đạt: Business thật sự được chạy.
11. Test khác biệt giữa `validate(bean, A.class,B.class)` và `validate(bean, Ordered.class)`.
12. Tách biệt test Bean Validation trực tiếp và test Spring MVC/`@Validated`/AOP nếu có.
13. Không tin vào thứ tự `Set`; sort theo field, code và thứ tự ưu tiên của UI khi chuyển sang danh sách.
14. Nếu bật fail-fast hoặc composed constraint, test lại **số lỗi và phạm vi** theo cấu hình đó.
15. Kiểm tra cascade `@Valid`, group conversion và Default redefinition khi có object graph lồng nhau.
16. Không xuất `getInvalidValue()`, stack trace hoặc metadata nhạy cảm trong response.
17. Tài liệu hóa cho client: lỗi trả về là **tất cả lỗi** hay **lỗi của giai đoạn đầu tiên chưa đạt**. Đây là khác biệt hành vi API có thể quan trọng.

### Câu hỏi ôn tập

1. `@GroupSequence({Basic.class, Deep.class})` có buộc `Set<ConstraintViolation<?>>` trả Basic lỗi trước Deep lỗi không?
2. Basic có hai ràng buộc sai, Deep có ba ràng buộc sai. Khi chạy sequence (không fail-fast), có thể nhận bao nhiêu lỗi và Deep có được kiểm tra không?
3. Gọi `validator.validate(bean, Basic.class, Deep.class)` có tương đương gọi sequence không?
4. `@GroupSequence` trên interface và trên class khác nhau ở điểm nào?
5. Với class `Invoice` redefine Default, sequence nên chứa `Default.class` hay `Invoice.class`?
6. Một API muốn trả **tất cả lỗi** và xếp tên trước tuổi: nên dùng GroupSequence để sort hay sort sau validation?
7. Có thể dựa vào `violations.iterator().next()` làm lỗi ưu tiên không?
8. Vì sao `@Validated({Basic.class,Deep.class})` không có nghĩa `Basic → Deep`?
9. Hibernate Validator fail-fast và GroupSequence giống nhau ở điểm nào, khác nhau ở điểm nào?
10. Nếu có nested bean `@Valid` và class cha redefine Default, có thể mặc định cả sequence cha được truyền nguyên vẹn sang bean con không?

**Đáp án:** (1) Không, sequence là thứ tự **đánh giá** và dừng nhóm sau, không phải thứ tự Set; (2) có thể nhận 2 lỗi Basic và Deep bị bỏ qua; (3) không, varargs không tạo sequence; (4) interface sequence phải được yêu cầu, class sequence redefine Default cục bộ; (5) `Invoice.class`; (6) validate phạm vi cần thiết rồi sort response; (7) không; (8) mảng các group không có hợp đồng thứ tự; (9) cả hai có thể làm ít lỗi hơn, nhưng GroupSequence dừng giữa các nhóm còn fail-fast dừng khi phát hiện lỗi theo hành vi provider; (10) không, default override có phạm vi và propagation riêng.

## 20. Tài liệu tham khảo chính thức

- Jakarta Bean Validation 3.0 Specification — *Group sequence*, *Redefining the Default group for a class*, *Validation routine*: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Bean Validation 3.0 API — `GroupSequence`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/GroupSequence.html
- Jakarta Bean Validation 3.0 API — `Validator`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Validator.html
- Jakarta Bean Validation 3.0 API — `ConstraintViolation`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ConstraintViolation.html
- Jakarta Bean Validation 3.0 API — `GroupDefinitionException`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/GroupDefinitionException.html
- Hibernate Validator 8.0 — Reference Guide, *Defining group sequences*, *Redefining default group sequence* và *Fail fast*: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Hibernate Validator 8.0 releases, Maven coordinates: https://hibernate.org/validator/releases/8.0/
- Spring Framework — Validation, Data Binding, Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation.html
- Spring Framework — Spring MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
