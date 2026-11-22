# Xử lý phần tử null và đối tượng con null khi kiểm tra lồng nhau

> **Module:** Spring Framework – validation-data-binding  
> **Chủ đề cha:** Kiểm tra lồng nhau  
> **Phạm vi:** Jakarta Validation/Bean Validation và Spring MVC; phân biệt đối tượng con `null`, container `null`, phần tử `null`, container rỗng, `@Valid` và các constraint kiểm tra tính bắt buộc.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao `@Valid` **không tự cấm** một object con nhận giá trị `null`.
2. Dùng `@NotNull @Valid` để vừa yêu cầu sự tồn tại của object con, vừa kiểm tra constraint **bên trong** object đó.
3. Phân biệt bốn trạng thái: **container null**, **container rỗng**, **element null**, **element không null nhưng dữ liệu bên trong sai**.
4. Viết đúng `List<@NotNull @Valid Child>`, `List<@NotBlank String>`, `Map<@NotBlank String, @NotNull @Valid Child>`.
5. Hiểu `@NotNull`, `@NotEmpty`, `@Size`, `@NotBlank` và `@Valid` có trách nhiệm khác nhau.
6. Đọc `ConstraintViolation#getPropertyPath()` trong kiểm tra lồng nhau và tránh suy luận sai về tên đường dẫn ở collection/map.
7. Kích hoạt validation trong Spring MVC và phân biệt lỗi deserialize/binding với lỗi constraint.
8. Kiểm thử nhiều trường hợp null bằng chương trình Java 17+ có kết quả xác định, không phụ thuộc thời gian hay thứ tự duyệt `Set`.

## 2. Nguyên tắc gốc: `@Valid` là cascade, không phải non-null

`jakarta.validation.Valid` là chỉ thị **kiểm tra sâu** (cascaded validation). Khi Jakarta Validation provider đang validate đối tượng cha và gặp một association được gắn `@Valid`:

- Nếu association trỏ đến **object khác null**, provider đi tiếp và đánh giá các constraint trên object con.
- Nếu association là **null**, provider **bỏ qua bước cascade** tới object con, không tự tạo lỗi vì `@Valid`.
- Nếu association chứa một container như `List` hoặc `Map`, provider có thể cascade tới các **phần tử con hiện hữu**, trong khi tham chiếu null không phải bean để duyệt.
- Provider theo dõi đường duyệt object graph để tránh vòng lặp vô hạn do association tham chiếu qua lại.

Đây là quy tắc của đặc tả Jakarta Validation, không phải “mẹo” riêng của Spring hay Hibernate Validator.

~~~text
validate(Order)
    |
    +-- customer: @Valid
    |       |
    |       +-- customer != null --> validate(Customer)
    |       |
    |       +-- customer == null --> bỏ qua cascade, không tự báo lỗi
    |
    +-- delivery: @NotNull @Valid
            |
            +-- delivery == null --> @NotNull báo vi phạm
            |                      @Valid vẫn không cascade
            |
            +-- delivery != null --> @NotNull đạt
                                   @Valid kiểm tra Delivery.*
~~~

Điểm then chốt: **Có mặt** và **hợp lệ bên trong** là hai yêu cầu độc lập.

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

class Purchase {
    @Valid
    private Customer optionalCustomer;

    @NotNull
    @Valid
    private Address requiredDeliveryAddress;
}
~~~

Đoạn trên là **mảnh DTO minh họa**, không phải class độc lập có `main`.

- `optionalCustomer == null`: không có lỗi từ `@Valid`; nếu khác null thì các constraint của `Customer` được xét.
- `requiredDeliveryAddress == null`: có lỗi từ `@NotNull`. `@Valid` không gọi validator cho object null.
- `requiredDeliveryAddress != null`: `@NotNull` đạt; các constraint bên trong `Address` vẫn có thể thất bại.

Nếu cần object con **không được phép vắng mặt**, thường phải khai báo **cả `@NotNull` lẫn `@Valid`**. Chỉ `@NotNull` không tự kiểm tra các field bên trong; chỉ `@Valid` không bắt buộc object phải tồn tại.

## 3. Bảng trạng thái cần ghi nhớ

Giả sử class `Address` có:

~~~java
import jakarta.validation.constraints.NotBlank;

public record Address(@NotBlank String city) {}
~~~

Và object cha có field `@Valid Address address`.

| `address` | Kết quả với chỉ `@Valid` | Lý do |
| --- | --- | --- |
| `null` | Không có violation | Không có bean con để cascade |
| `new Address("Ha Noi")` | Không có violation | Cascade có chạy; `city` hợp lệ |
| `new Address("")` | Một violation ở `city` | `@NotBlank` thất bại |
| `new Address(null)` | Một violation ở `city` | `@NotBlank` không cho null |

Nếu cha đổi thành `@NotNull @Valid Address address`, chỉ trường hợp `address == null` đổi thành **một violation ở `address`**. Với object con tồn tại, kết quả bên trong vẫn được kiểm tra nhờ `@Valid`.

Đặc biệt, `@NotBlank` từ chối `null`, chuỗi rỗng và chuỗi chỉ gồm whitespace. Không nên diễn giải rằng “mọi constraint đều bỏ qua null”: nhiều constraint chỉ kiểm tra giá trị khi nó hiện diện (ví dụ `@Size`, `@Pattern`, `@Positive`), nhưng `@NotNull`, `@NotEmpty`, `@NotBlank` được thiết kế để kiểm tra sự thiếu/rỗng của dữ liệu.

## 4. Container null, container rỗng và phần tử null

Với một danh sách địa chỉ, có **ba tầng** khác nhau:

~~~text
Order
  |
  +-- stops: List<Address>           [tham chiếu danh sách]
        |
        +-- stops[0]: Address         [phần tử 0]
        |     |
        |     +-- city: String        [field trong phần tử 0]
        |
        +-- stops[1]: Address         [phần tử 1]
              |
              +-- city: String
~~~

Tại mỗi tầng có thể xuất hiện một giá trị null khác nhau.

### 4.1. Danh sách `null`

~~~java
@NotNull
private List<@Valid Address> stops;
~~~

Nếu `stops == null`, `@NotNull` báo lỗi ở **property `stops`**; không có phần tử để cascade. Nếu thiếu `@NotNull`, `@Valid` trên từng type argument không tự biến danh sách null thành lỗi.

### 4.2. Danh sách rỗng

~~~java
@NotNull
private List<@Valid Address> stops;
~~~

Nếu `stops = List.of()`, `@NotNull` **đạt**, vì danh sách tồn tại. `@Valid` không có phần tử nào để kiểm tra và không tạo lỗi. Nếu nghiệp vụ yêu cầu **ít nhất một phần tử**, dùng `@NotEmpty` hoặc `@Size(min = 1)` cho chính danh sách.

### 4.3. Phần tử null

~~~java
@NotNull
private List<@Valid Address> stops;
~~~

Nếu `stops = [null, Address("Ha Noi")]`, phần tử null được **bỏ qua khi cascade**; riêng `@Valid` ở type argument không yêu cầu phần tử tồn tại. Để loại bỏ các phần tử null:

~~~java
@NotNull
private List<@NotNull @Valid Address> stops;
~~~

Khi đó:

- `@NotNull` **bên ngoài**: danh sách phải khác null.
- `@NotNull` **bên trong dấu `<...>`**: **từng phần tử** phải khác null.
- `@Valid` **bên trong dấu `<...>`**: phần tử khác null được cascade để kiểm tra field của `Address`.

Đây là mẫu quan trọng nhất của bài.

### 4.4. Phần tử khác null nhưng field null

~~~java
List<Address> stops = java.util.Arrays.asList(
        new Address(null),
        new Address("Da Nang"));
~~~

`@NotNull` trên phần tử **không** bắt lỗi của phần tử đầu, vì `new Address(null)` **là một đối tượng Address khác null**. Lỗi `city == null` chỉ xuất hiện khi có `@Valid` cascade tới `Address.city` và kiểm tra `@NotBlank`.

Tóm tắt theo từng tầng:

| Trạng thái | `@NotNull List<@Valid Address>` | `@NotNull List<@NotNull @Valid Address>` | `@NotEmpty List<@NotNull @Valid Address>` |
| --- | --- | --- | --- |
| Danh sách `null` | Lỗi ở list | Lỗi ở list | Lỗi ở list |
| Danh sách `[]` | Hợp lệ | Hợp lệ | Lỗi: rỗng |
| `[null]` | Không lỗi do cascade | Lỗi tại element | Lỗi tại element; list không rỗng |
| `[Address("")]` | Lỗi field `city` | Lỗi field `city` | Lỗi field `city` |
| `[Address("Hue")]` | Hợp lệ | Hợp lệ | Hợp lệ |

Bảng này chỉ tính **các annotation được nêu**. Nếu thêm quy tắc khác trên phần tử hoặc class, tổng số violation có thể tăng.

## 5. Phân biệt các constraint về null và kích thước

| Constraint | Null | Empty | Ý nghĩa |
| --- | --- | --- | --- |
| `@NotNull` trên list | Không hợp lệ | Hợp lệ | Danh sách phải tồn tại |
| `@NotEmpty` trên list | Không hợp lệ | Không hợp lệ | Danh sách phải có ít nhất một phần tử |
| `@Size(min = 1)` trên list | **Hợp lệ** | Không hợp lệ | Kiểm tra kích thước khi list hiện hữu |
| `@NotNull` trên string | Không hợp lệ | Chuỗi rỗng hợp lệ | Chỉ cấm null |
| `@NotEmpty` trên string | Không hợp lệ | Không hợp lệ | Cấm null và chuỗi dài 0; `" "` vẫn được |
| `@NotBlank` trên string | Không hợp lệ | Không hợp lệ | Cấm null, chuỗi rỗng và chỉ có khoảng trắng |
| `@Valid` trên association | Bỏ qua cascade nếu null | Không áp dụng trực tiếp khái niệm empty | Chỉ thị đi sâu khi object tồn tại |

Một vài mẫu DTO hữu ích:

~~~java
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public class ShipmentRequest {
    @NotNull
    @Valid
    private Address destination;

    @NotEmpty
    private List<@NotNull @Valid Address> stops;

    @NotNull
    @Size(min = 2, max = 5)
    private List<@NotBlank String> labels;
}
~~~

Đây là **mảnh DTO**; các class/import được đặt trong ví dụ minh họa.

- `destination`: đối tượng giao hàng bắt buộc, các field con phải hợp lệ.
- `stops`: list bắt buộc **không rỗng**, và mọi element là object khác null, có field hợp lệ. `@NotEmpty` đã cấm null của **list**, nên không bắt buộc thêm `@NotNull` ngoài list nếu chỉ muốn kiểm tra sự có mặt/không rỗng.
- `labels`: list phải tồn tại, chứa từ 2 đến 5 phần tử; mỗi phần tử là chuỗi khác null, không rỗng/blank. Không phải `@Size(min=2)` sẽ tự cấm list null, vì constraint này cho null hợp lệ.

Đừng vô tình gắn cả `@NotNull` và `@NotEmpty` lên cùng list chỉ để “chắc ăn”. Khi list null, cả hai có thể báo lỗi, dẫn đến thông báo trùng ý. Chọn constraint biểu diễn điều kiện nghiệp vụ rõ nhất.

## 6. Constraint trên type argument (container element constraints)

Từ Bean Validation 2.0 / Jakarta Validation, constraint có thể khai báo ngay tại type argument:

~~~java
List<@NotNull Address> addresses;
List<@NotBlank String> names;
List<@NotNull @Valid Address> mandatoryAddresses;
Map<@NotBlank String, @NotNull @Valid Address> addressByCode;
~~~

Đây là **khai báo kiểu minh họa**, không phải một chương trình độc lập. Nó thể hiện rõ mục tiêu:

- `List<@NotNull Address>`: mỗi phần tử không được null, **không tự validate field của Address**.
- `List<@NotBlank String>`: mỗi tên khác null và có ký tự không phải khoảng trắng; không cần `@Valid` vì `String` không phải bean lồng nhau cần cascade.
- `List<@NotNull @Valid Address>`: vừa cấm null element vừa đi sâu kiểm tra object con.
- `Map<@NotBlank String, @NotNull @Valid Address>`: key phải là chuỗi hợp lệ; value không null; value tồn tại thì cascade kiểm tra Address.

Đặt annotation **đúng tầng**:

~~~java
@NotEmpty                     // trên container
List<@NotNull @Valid Address> stops;
//    ^^^^^^^ ^^^^^^
//    trên element: bắt buộc + cascade
~~~

Khai báo ở type argument biểu đạt chính xác hơn `@Valid List<Address>` kiểu cũ, đặc biệt đối với container lồng nhau. Hibernate Validator khuyến nghị đặt `@Valid` trên type argument cho các collection/map hiện đại.

### 6.1. Danh sách nhiều tầng

~~~java
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public class RoutePlan {
    @NotEmpty
    private List<@NotEmpty List<@NotNull @Valid Address>> routes;
}
~~~

Tầng ngoài phải tồn tại và có route; **mỗi list route** phải tồn tại và không rỗng; **mỗi Address** trong route phải khác null và hợp lệ. Các type-use annotation này yêu cầu provider hỗ trợ value extraction cho những container tương ứng; `List` tiêu chuẩn được Hibernate Validator hỗ trợ.

Vì `@NotEmpty` trên một list nhận null là vi phạm, việc đặt nó lên **element list** bảo vệ cả trường hợp một route con là null. Nếu chỉ dùng `@Size(min=1)` trên route con thì null có thể lọt qua (trừ khi thêm `@NotNull`).

### 6.2. `Map`: null key và null value là hai trường hợp khác nhau

~~~java
import java.util.Map;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public class Directory {
    @NotEmpty
    private Map<@NotBlank String,
                @NotNull @Valid Address> addresses;
}
~~~

Cần đọc rõ:

- `@NotEmpty` ngoài `Map`: map không được null/rỗng.
- `@NotBlank String`: từng key không được null, rỗng hay toàn dấu cách.
- `@NotNull @Valid Address`: từng value không được null và phải có các property hợp lệ.
- Key null hoặc value null **khác** map null.
- Một key hợp lệ không chứng minh value hợp lệ, và ngược lại.

Nếu viết `Map<String, @Valid Address>`, một value null được bỏ qua khi cascade; thêm `@NotNull` trên type argument value khi cần loại bỏ nó.

### 6.3. Array, Iterable và custom container

`@Valid` cũng dùng cho các association dạng array và `Iterable` theo khả năng của provider; các container chuẩn có sẵn `ValueExtractor` để tìm element và vị trí. Với container tự tạo như `Box<T>`, provider có thể cần `ValueExtractor` chuyên biệt, nếu không metadata element constraint có thể không được thực thi như dự kiến hoặc gây lỗi cấu hình. Kiểm tra tài liệu provider trước khi tùy tiện gắn type-use constraints lên mọi generic class.

Với container mang ý nghĩa optional như `Optional<T>`, phải phân biệt:
- **Biến Optional là null** (không có wrapper).
- **`Optional.empty()`** (wrapper tồn tại nhưng không có giá trị).
- **`Optional.of(value)`** (wrapper có giá trị).

`Optional.empty()` không đồng nghĩa về mặt Java với biến wrapper null, và việc constraint trên element được trích xuất như thế nào phụ thuộc value extractor theo đặc tả/provider. Đừng mặc định `@Valid` trên một `Optional` sẽ bắt buộc phải có element; hãy khai báo và test quy tắc bắt buộc theo đúng mô hình dữ liệu.

## 7. Chương trình Java 17+ kiểm chứng bằng Hibernate Validator

Phần này là **bài thực hành chạy được**, minh họa bảy trường hợp: con optional null, con required null, phần tử null, property con blank, collection null, collection rỗng và dữ liệu hợp lệ.

### 7.1. Tạo Maven project

Cấu trúc:

~~~text
null-cascade-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── nullcascade/
                    └── NullCascadeDemo.java
~~~

Tệp `pom.xml`: dự án Java 17, Hibernate Validator 8.x (implementation Jakarta Validation 3.0), Jakarta EL để nội suy message mặc định.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>null-cascade-demo</artifactId>
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
        <dependency>
            <groupId>org.glassfish</groupId>
            <artifactId>jakarta.el</artifactId>
            <version>4.0.2</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Trong Spring Boot thực tế, nên dùng dependency management/BOM của Boot cho version thay vì sao chép các version cố định này.

### 7.2. Class có `main`

Lưu đúng đường dẫn `src/main/java/example/nullcascade/NullCascadeDemo.java`:

~~~java
package example.nullcascade;

import java.util.Arrays;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public final class NullCascadeDemo {

    public record Address(
            @NotBlank String city) {}

    public record OptionalContact(
            @Valid Address contact) {}

    public record Order(
            @NotNull @Valid Address shipping,
            @NotNull List<@NotNull @Valid Address> stops,
            @NotEmpty List<@NotBlank String> labels) {}

    private static int errors(Validator validator, Object object) {
        return validator.validate(object).size();
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            OptionalContact optionalNull =
                    new OptionalContact(null);

            Order requiredNull = new Order(
                    null,
                    List.of(new Address("Da Nang")),
                    List.of("fast"));

            Order invalidElements = new Order(
                    new Address(""),
                    Arrays.asList(null, new Address(" ")),
                    Arrays.asList("fast", null, ""));

            Order nullCollections = new Order(
                    new Address("Ha Noi"),
                    null,
                    null);

            Order emptyCollections = new Order(
                    new Address("Ha Noi"),
                    List.of(),
                    List.of());

            Order valid = new Order(
                    new Address("Ha Noi"),
                    List.of(new Address("Hue")),
                    List.of("fast"));

            System.out.println(
                    "optional-null=" + errors(validator, optionalNull));
            System.out.println(
                    "required-null=" + errors(validator, requiredNull));
            System.out.println(
                    "invalid-elements=" + errors(validator, invalidElements));
            System.out.println(
                    "null-collections=" + errors(validator, nullCollections));
            System.out.println(
                    "empty-collections=" + errors(validator, emptyCollections));
            System.out.println(
                    "valid=" + errors(validator, valid));

            try {
                validator.validate((Order) null);
            } catch (IllegalArgumentException exception) {
                System.out.println(
                        "null-root=" + exception.getClass().getSimpleName());
            }
        }
    }
}
~~~

Chạy trong thư mục `null-cascade-demo`:

~~~bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=example.nullcascade.NullCascadeDemo
~~~

**Stdout do chính chương trình in** (không tính log của Maven hoặc provider):

~~~text
optional-null=0
required-null=1
invalid-elements=5
null-collections=2
empty-collections=1
valid=0
null-root=IllegalArgumentException
~~~

### 7.3. Giải thích từng kết quả

| Trường hợp | Tổng violation | Nguồn lỗi |
| --- | ---: | --- |
| `optionalNull` | 0 | `@Valid` bỏ qua `contact == null` |
| `requiredNull` | 1 | `shipping == null` vi phạm `@NotNull`; cascade không chạy |
| `invalidElements` | 5 | `shipping.city` blank (1); phần tử `stops` null (1); `stops` có child với `city` blank (1); `labels` có một phần tử null (1) và một chuỗi rỗng (1) |
| `nullCollections` | 2 | `stops == null` vi phạm `@NotNull`; `labels == null` vi phạm `@NotEmpty` |
| `emptyCollections` | 1 | `stops=[]` hợp lệ với riêng `@NotNull`; `labels=[]` vi phạm `@NotEmpty` |
| `valid` | 0 | Tất cả object/container/element phù hợp |
| `validator.validate(null)` | Exception | **Root object** null không phải cùng trường hợp với **association** null được bỏ qua khi cascade |

Chương trình chỉ in **số lượng violation**, không duyệt thứ tự từ `Set<ConstraintViolation<?>>`; số lượng dự đoán được và không phụ thuộc locale của thông báo lỗi.

**Điểm Java quan trọng:** `List.of(null)` không cho phép phần tử null và sẽ ném `NullPointerException` **khi tạo list**, trước cả khi Bean Validation chạy. Trong ví dụ, `Arrays.asList(...)` được dùng để cố ý tạo list có phần tử null. Nếu một test thất bại ngay tại `List.of(null)`, đó không phải do `@NotNull` của Jakarta Validation.

### 7.4. Chạy bằng `javac/java` thuần được không?

Cần phân biệt:
- `NullCascadeDemo.java` là một class Java 17 có `main` đầy đủ nhưng **phụ thuộc thư viện Jakarta Validation/Hibernate Validator**. `javac NullCascadeDemo.java` từ thư mục trống không có classpath sẽ báo thiếu các package `jakarta.validation`.
- Maven ở trên cấp classpath và chạy ví dụ được. Nếu tự tải các JAR phụ thuộc, cũng có thể biên dịch bằng `javac -cp ...` và chạy bằng `java -cp ...` với **đầy đủ transitive dependencies**; không nên ghi một classpath giả hoặc thiếu thư viện rồi tuyên bố có thể chạy.

Bên dưới là ví dụ Java 17 thuần xác nhận thêm sự khác biệt giữa null object, null list và null element; nhưng nó **không thực thi Jakarta Validation**:

~~~java
import java.util.Arrays;
import java.util.List;

public class NullStructureCheck {
    public static void main(String[] args) {
        List<String> noList = null;
        List<String> emptyList = List.of();
        List<String> withNull = Arrays.asList(null, "ok");

        System.out.println(noList == null);
        System.out.println(emptyList.isEmpty());
        System.out.println(withNull.get(0) == null);
        System.out.println(withNull.size());
    }
}
~~~

Lưu `NullStructureCheck.java` rồi chạy:

~~~bash
javac NullStructureCheck.java
java NullStructureCheck
~~~

Stdout chính xác:

~~~text
true
true
true
2
~~~

Đây là kiểm tra cấu trúc dữ liệu Java, không phải một phép thay thế `Validator.validate(...)`.

## 8. Đường dẫn vi phạm của object và container

`ConstraintViolation#getPropertyPath()` cho biết vị trí lỗi trong object graph. Khi validate một `Order` có `Address shipping`, đường dẫn thường có dạng:

~~~text
shipping                (field shipping bị @NotNull)
shipping.city           (field city của object shipping)
stops[0].<list element> (constraint trên element null, cách hiển thị tùy provider)
stops[1].city           (field city của object tại index 1)
labels[2].<list element>
~~~

Đây là **minh họa định dạng đường dẫn**, không phải stdout cam kết từ chương trình mục 7. Với list/map container-element constraints, tên node nội bộ và cách render chuỗi có thể khác theo provider và phiên bản. Đặc tả cung cấp mô hình `Path` có node, index, key, container class, type argument index để mô tả cấu trúc; không nên viết parser chỉ phụ thuộc một chuỗi ví dụ.

Khi cần trả về lỗi API ổn định:
- Lấy đường dẫn từ `getPropertyPath()`, hiểu các node và index/key khi cần.
- Xây mã lỗi như `REQUIRED_ADDRESS`, `INVALID_CITY`, `NULL_LIST_ELEMENT` từ quy ước của ứng dụng.
- Không chuyển toàn bộ `getInvalidValue()` vào logs hoặc response, vì value có thể chứa dữ liệu nhạy cảm.
- Nếu xuất thông báo quốc tế hóa, message text có thể thay đổi theo locale/provider.

Ví dụ đơn giản để in đường dẫn một cách **ổn định về thứ tự**, đặt trong một project có `Validator` và bean:

~~~java
validator.validate(bean).stream()
        .map(v -> v.getPropertyPath() + " -> " + v.getMessage())
        .sorted()
        .forEach(System.out::println);
~~~

Đây là fragment minh họa, không phải class độc lập. `sorted()` chỉ giúp thứ tự in; không làm cho văn bản `Path` trở thành định dạng API cố định.

## 9. Tích hợp vào Spring MVC / Spring Boot

Trong Spring Boot 3+ (Spring Framework 6+), dùng **`jakarta.validation.*`**, không phải namespace `javax.validation.*` của các phiên bản cũ. Một ứng dụng MVC thông thường cần:

~~~xml
<!-- Các dependency trong dự án Boot có parent/BOM quản lý phiên bản -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Đây chỉ là dependency fragment, không phải `pom.xml` hoàn chỉnh. `starter-validation` thêm provider thường dùng để Spring thực thi các Jakarta constraints.

### 9.1. Ví dụ controller và DTO Java 17+

Trong dự án Spring Boot 3.x có các starter trên, lưu tệp `src/main/java/example/nullweb/NullWebApplication.java`:

~~~java
package example.nullweb;

import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class NullWebApplication {

    public static void main(String[] args) {
        SpringApplication.run(NullWebApplication.class, args);
    }

    public record AddressRequest(
            @NotBlank String city) {}

    public record OrderRequest(
            @NotNull @Valid AddressRequest shipping,
            @NotEmpty List<@NotNull @Valid AddressRequest> stops) {}

    @RestController
    public static class OrdersController {

        @PostMapping("/orders")
        public Map<String, String> create(
                @Valid @RequestBody OrderRequest request) {
            return Map.of(
                    "status", "accepted",
                    "shippingCity", request.shipping().city());
        }
    }
}
~~~

Chạy dự án (khi có wrapper Maven tương ứng):

~~~bash
./mvnw spring-boot:run
~~~

Hoặc dùng `./gradlew bootRun` nếu dự án dùng Gradle wrapper. Các lệnh không thể chạy từ một thư mục chỉ chứa file Java và XML fragment; phải có project Boot được cấu hình đúng.

Gửi request hợp lệ:

~~~bash
curl -i -X POST http://localhost:8080/orders \
  -H "Content-Type: application/json" \
  -d '{"shipping":{"city":"Ha Noi"},"stops":[{"city":"Hue"}]}'
~~~

Trong môi trường Boot tiêu chuẩn, request này có thể trả HTTP **200** và JSON có hai thuộc tính `status`, `shippingCity`. Thứ tự key JSON không được cam kết.

Request với object con null và element null:

~~~bash
curl -i -X POST http://localhost:8080/orders \
  -H "Content-Type: application/json" \
  -d '{"shipping":null,"stops":[null,{"city":""}]}'
~~~

Sau khi Jackson tạo DTO, **ba** constraint có thể thất bại:
1. `shipping == null` vi phạm `@NotNull` trên child.
2. Element đầu tiên của `stops` là null, vi phạm `@NotNull` **ở type argument**.
3. Element thứ hai là object nhưng `city == ""` vi phạm `@NotBlank` sau khi `@Valid` cascade.

`@NotEmpty` trên `stops` **đạt** vì danh sách có hai phần tử, dù có phần tử null.

Request với danh sách rỗng:

~~~bash
curl -i -X POST http://localhost:8080/orders \
  -H "Content-Type: application/json" \
  -d '{"shipping":{"city":"Ha Noi"},"stops":[]}'
~~~

Danh sách tồn tại nhưng rỗng, vi phạm `@NotEmpty` trên container, không phải vi phạm `@NotNull` trên phần tử.

Trong cấu hình MVC thông thường, validation failure của `@Valid @RequestBody` làm Spring trả lỗi HTTP **400**, thường qua `MethodArgumentNotValidException`; payload lỗi cụ thể tùy `@ControllerAdvice`, Problem Details và cấu hình server. **Không** giả định API lúc nào cũng trả một JSON lỗi duy nhất hay một thứ tự field errors nhất định.

### 9.2. Thiếu field khác với field null ở JSON như thế nào?

Hai request:

~~~json
{"shipping":null,"stops":[]}
~~~

và:

~~~json
{"stops":[]}
~~~

thường đều tạo ra `shipping == null` cho một record component/reference field trong ví dụ, **nếu không có cấu hình Jackson đặc biệt** về missing properties, required constructor parameters, default value hay null handling. Validation `@NotNull` sau đó từ chối cả hai.

Nhưng không được đánh đồng trong mọi ứng dụng:
- Jackson có thể được cấu hình để **báo lỗi deserialize** ngay khi property bị thiếu hoặc null.
- Kiểu nguyên thủy Java (`int`, `boolean`) có ngữ nghĩa giá trị mặc định khác object wrapper; cần chọn kiểu dữ liệu đúng cho “bắt buộc”.
- Với PATCH, field **không gửi** và field **gửi giá trị null để xóa** có thể mang ý nghĩa nghiệp vụ khác nhau; hai trường hợp này không thể phân biệt chỉ bằng `@NotNull` trên DTO thông thường.
- Dữ liệu từ HTML form và query parameter đi qua `WebDataBinder`/`ConversionService`, không nhất thiết đi cùng đường xử lý Jackson.

### 9.3. Binding rồi mới validation

~~~text
HTTP JSON
    |
    v
Jackson deserialize
    |
    +-- JSON sai cú pháp hoặc kiểu không chuyển được -> lỗi đọc request
    |
    v
OrderRequest Java (có thể chứa null)
    |
    v
@Valid / Jakarta Validator
    |
    +-- kiểm tra shipping @NotNull và cascade @Valid
    +-- kiểm tra stops @NotEmpty
    +-- kiểm tra @NotNull và @Valid trên từng stops element
    |
    v
Nếu không lỗi -> controller chạy
Nếu có lỗi   -> Spring xử lý validation errors
~~~

Lỗi do JSON sai kiểu (ví dụ `"stops":"not-an-array"`) thường xảy ra **trước** Bean Validation. Vì vậy không thể kỳ vọng mọi dữ liệu hỏng đều tạo `ConstraintViolation`.

## 10. `@Valid` ở cha, ở container và ở type argument

Ba hình thức khác nhau:

~~~java
@Valid
private Address customer;

@Valid
private List<Address> contacts;

private List<@Valid Address> preferredContacts;
~~~

Trong Bean Validation hiện đại:
- Trường thứ nhất cascade từ object cha tới `Address`.
- Trường thứ hai là **cách viết ở container level** được các provider hỗ trợ để cascade tới các phần tử collection; cách viết này có tính lịch sử và ít chính xác hơn khi container nhiều tầng.
- Trường thứ ba khai báo rõ cascade trên **type argument**; đây là lựa chọn ưu tiên cho collection/map mới, nhất là khi kết hợp `@NotNull` trên phần tử.

**Cấm null phải ở đúng tầng**:

~~~java
@NotNull                   // bắt buộc có list
private List<@Valid Address> contacts;

private List<@NotNull @Valid Address> contacts2;
//           ^^^^^^^ bắt buộc có từng element, không cấm list null

@NotNull
private List<@NotNull @Valid Address> contacts3;
// ^^^^^^^ cấm list null
//               ^^^^^^^ cấm element null
~~~

Khi yêu cầu list không rỗng, dùng `@NotEmpty` trên list; khi yêu cầu mỗi element phải tồn tại, dùng `@NotNull` trên type argument. Không thể thay thế một trong hai bằng `@Valid`.

## 11. Nhóm kiểm tra và cascade vào object con

Validation groups quyết định những constraint nào chạy. Nếu một constraint được khai báo chỉ trong group riêng, gọi validator với group khác sẽ không tự đánh giá nó.

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.groups.Default;

interface OnSubmit {}

class ShippingInfo {
    @NotNull(groups = OnSubmit.class)
    private String trackingCode;
}

class Dispatch {
    @Valid
    private ShippingInfo shipping;
}
~~~

Đây là **fragment minh họa**.

- Validate `Dispatch` với `Default`: sẽ cascade tới object con nếu khác null, nhưng constraint `trackingCode` thuộc `OnSubmit` nên không tự chạy.
- Validate `Dispatch` với `OnSubmit`: cascade theo group hiện tại, `trackingCode` được kiểm tra.
- Nếu `shipping == null`: cascade được bỏ qua **ở cả hai group**.
- Muốn bắt buộc `shipping` theo `OnSubmit`: khai báo `@NotNull(groups=OnSubmit.class)` ngay trên association.
- Muốn chuyển từ group cha sang group khác trên bean con: dùng `@ConvertGroup` kết hợp `@Valid` theo Jakarta Validation.

Trong Spring, `@Validated(OnSubmit.class)` tại endpoint có thể chọn group; `@Valid` vẫn là annotation tiêu chuẩn để cascade. Nếu một field có `@NotNull` không khai báo `groups` thì constraint thuộc `Default` và sẽ không tự chạy khi chỉ chọn group độc lập `OnSubmit` (trừ khi đã thiết kế inheritance/sequence phù hợp).

**Bài học:** Khi tưởng rằng “`@NotNull` không hoạt động”, ngoài chuyện annotation được đặt đúng tầng hay chưa, phải kiểm tra **group đang chạy** và có thực sự kích hoạt validation không.

## 12. Vì sao constraint trên object con có thể không được chạy?

Các nguyên nhân phổ biến:

1. **Association null:** `@Valid` bỏ qua. Nếu cấm null, thêm `@NotNull` tại association.
2. **Không có `@Valid`:** provider chỉ kiểm tra constraint khai báo trên object cha; nó không tự quét toàn bộ mọi bean con.
3. **Group không phù hợp:** constraint con thuộc group khác nên không được chọn.
4. **Object đã được kiểm tra trong đường duyệt của một chu trình:** provider tránh lặp vô hạn; đây là cơ chế an toàn của đặc tả.
5. **Container tùy chỉnh thiếu `ValueExtractor`:** không trích xuất được element đúng cách.
6. **Spring chưa kích hoạt validation:** thiếu `@Valid`/`@Validated` ở điểm tích hợp, hoặc thiếu provider dependency.
7. **Dữ liệu chưa thành DTO:** JSON deserialize/binding đã lỗi trước validation.
8. **Đặt annotation sai tầng:** `@NotNull List<@Valid Child>` chỉ cấm list null, không cấm element null.

Đặc biệt, đừng suy ra rằng nếu constraint con không chạy thì “Hibernate Validator bị hỏng”; hãy truy nguyên từng bước của object graph.

## 13. Lỗi NullPointerException khác constraint violation

Tạo list bằng `List.of(null)` gây lỗi Java ngay lúc tạo, còn tạo list có null bằng `Arrays.asList(...)` để test validation là hợp lệ. Tương tự:

~~~java
Order order = new Order(null, null, null);
String city = order.shipping().city(); // NullPointerException
~~~

Đoạn trên là **fragment minh họa**, với `Order` là record ở mục 7. Lỗi `NullPointerException` xảy ra do gọi method trên reference null; không phải phản hồi của `Validator.validate(order)`. Validation **không tự sửa** object và không làm mọi tham chiếu an toàn; nó phát hiện violations khi được gọi. Ở controller MVC, tránh truy cập field bắt buộc trước bước validation hoặc trước khi đã xử lý lỗi.

Lưu ý khác: một custom `ConstraintValidator` không kiểm tra null có thể ném `NullPointerException` trong `isValid`. Khi viết custom validator, hãy định nghĩa rõ null được phép hay không (thường để constraint định dạng cho null hợp lệ rồi dùng `@NotNull` riêng); không dựa vào tác dụng phụ exception để báo lỗi dữ liệu.

## 14. Testing checklist cho các trường hợp null

Với model `Order` (shipping required, stops list required, mỗi Address trong stops required, labels nonempty), bộ test nên bao gồm:

| Input | Mong đợi |
| --- | --- |
| `shipping == null` | Lỗi trên shipping do `@NotNull` |
| `shipping.city == null` | Lỗi tại city của child sau cascade |
| `shipping.city == " "` | Lỗi `@NotBlank` của child |
| `stops == null` | Lỗi container do `@NotNull` |
| `stops == []` | Hợp lệ đối với `@NotNull`, vì không cấm rỗng |
| `stops == [null]` | Lỗi phần tử do `@NotNull` ở type argument |
| `stops == [Address("")]` | Lỗi child.city do `@Valid` |
| `labels == null` | Lỗi `@NotEmpty` |
| `labels == []` | Lỗi `@NotEmpty` |
| `labels == [null]` | Lỗi phần tử `@NotBlank` |
| `labels == [" "]` | Lỗi phần tử `@NotBlank` |
| Đủ object hợp lệ | Không có violation |
| Root object truyền thẳng vào `Validator.validate(null)` | `IllegalArgumentException`, khác với một property con null |

Ngoài ra, test dữ liệu HTTP:
- Field bị thiếu so với được gửi tường minh `null` khi có chính sách deserialize đặc biệt.
- Sai kiểu JSON và lỗi không thể bind.
- DTO lồng nhau theo nhiều tầng và cả `Map` key/value.
- Validation group không phải `Default`.
- Mã HTTP và cấu trúc lỗi của `@ControllerAdvice` nếu API có hợp đồng riêng.

Không kiểm thử bằng cách so sánh thứ tự duyệt `Set<ConstraintViolation>`; tập hợp không cam kết thứ tự. Với JSON response cũng không nên so sánh vị trí key/field error nếu API không bảo đảm.

## 15. Bài tập tự luyện

**Câu 1.** Field `@Valid Address address` có `address == null`. Nó có tạo violation không?

**Đáp:** Không. `@Valid` bỏ qua tham chiếu null. Nếu bắt buộc có address, dùng `@NotNull @Valid Address address`.

**Câu 2.** `@NotNull List<@Valid Address> stops` có `stops=[null]`. Đạt không?

**Đáp:** Với các annotation đã nêu, đạt: list không null, phần tử null bị bỏ qua khi cascade. Thêm `@NotNull` vào **type argument** để bắt lỗi element null.

**Câu 3.** `@NotEmpty List<@NotNull @Valid Address> stops` có list rỗng. Lỗi nào xuất hiện?

**Đáp:** Vi phạm `@NotEmpty` trên list. Không có phần tử để kiểm tra `@NotNull` hoặc cascade.

**Câu 4.** `List<@NotNull Address>` chứa `Address(null)`, còn `Address.city` có `@NotBlank`. Có bắt lỗi city không?

**Đáp:** Không, nếu không có `@Valid` trong chuỗi cascade. `@NotNull` trên element chỉ kiểm tra đối tượng element có null hay không; `Address(null)` khác null. Thêm `@Valid` để đi sâu vào city.

**Câu 5.** Phân biệt ba khai báo: `@NotNull List<Address>`, `List<@NotNull Address>`, `@NotEmpty List<@NotNull Address>`.

**Đáp:** Khai báo thứ nhất cấm list null; thứ hai cấm từng element null khi list tồn tại; thứ ba cấm list null/rỗng **và** cấm element null.

**Câu 6.** Vì sao `List.of(null)` không dùng được để kiểm thử Bean Validation trên phần tử null?

**Đáp:** Java ném `NullPointerException` khi tạo immutable list bằng `List.of`; kiểm tra Jakarta Validation còn chưa diễn ra. Dùng `Arrays.asList(null, ...)` hoặc list có thể thêm null.

**Câu 7.** Tại sao một `Map<@NotBlank String, @Valid Address>` có key null có thể bị lỗi dù value không null?

**Đáp:** Vì `@NotBlank` nằm trên **key** và từ chối null. Nhưng nếu value là null, `@Valid` trên value sẽ bỏ qua; muốn cấm value null cần `@NotNull` trên type argument value.

**Câu 8.** Một DTO có `@NotNull(groups=Create.class) @Valid Child child`. Endpoint chỉ chọn `Update.class`. `child == null` chắc chắn lỗi không?

**Đáp:** Không, nếu hai group độc lập: `@NotNull` thuộc Create không chạy ở Update, còn `@Valid` bỏ qua null. Cần chọn đúng group hoặc khai báo constraint cho Update.

**Câu 9.** Client gửi JSON với `"stops":"abc"` thay vì array. Đây là lỗi null element?

**Đáp:** Không. Đó là vấn đề deserialize/type mismatch trước khi Jakarta Validation kiểm tra container elements.

**Câu 10.** Tại sao object cha vẫn có thể nhận lỗi ở địa chỉ con dù bản thân field cha không có constraint `@NotNull`?

**Đáp:** Vì `@Valid` cascade tới object con **khác null**. Khi child tồn tại, các constraint của child được kiểm tra và có thể thất bại; việc child không bắt buộc không có nghĩa nếu child xuất hiện thì dữ liệu bên trong được phép sai.

## 16. Tổng kết

- `@Valid` có nghĩa **cascade kiểm tra khi object tồn tại**. Nó **không tự cấm null**.
- `@NotNull @Valid Child` kết hợp **bắt buộc child** và **kiểm tra nội dung child**.
- Container null, container rỗng và element null là ba trường hợp **khác nhau**.
- `@NotNull List<@NotNull @Valid Child>`: cấm list null, cấm element null và cascade child hợp lệ. Thêm `@NotEmpty` trên list khi còn phải cấm list rỗng.
- `@Size(min=1)` cho list null hợp lệ; `@NotEmpty` thì không. `@NotBlank` thích hợp cho chuỗi không được null/rỗng/blank.
- Với `Map`, cần đặt constraint đúng vị trí **key** hoặc **value**.
- Phân biệt lỗi Bean Validation với lỗi Java `NullPointerException`, lỗi JSON deserialize và lỗi business validation.
- Trong Spring MVC, chỉ khi validation được kích hoạt bởi `@Valid`/`@Validated` và có provider phù hợp thì các annotation mới được đánh giá.
- Hãy kiểm thử riêng các trường hợp null, empty, blank, group và object nhiều tầng; không phụ thuộc thứ tự của violations.

### Nguồn kỹ thuật chính thức

- Jakarta Validation 3.0 Specification – Object graph validation, null references are ignored: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Validation API – `@Valid`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/valid
- Jakarta Validation API – `@NotNull`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/notnull
- Jakarta Validation API – `@NotEmpty`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/notempty
- Hibernate Validator 8 Reference Guide – Cascaded validation và container element constraints: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Spring Framework – Validation và Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring MVC – Validation of request data: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
