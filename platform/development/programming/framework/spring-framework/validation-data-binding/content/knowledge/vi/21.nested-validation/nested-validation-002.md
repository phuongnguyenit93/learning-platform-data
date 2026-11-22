# Kiểm tra lan truyền qua `List`, mảng và `Map` trong Jakarta Bean Validation

## 1. Vì sao cần kiểm tra lan truyền?

Một request thường không chỉ chứa các trường đơn giản như `name` hay `quantity`. Nó có thể chứa **danh sách đối tượng**, **mảng**, **Map ánh xạ khóa đến đối tượng**, hoặc **cấu trúc lồng nhiều tầng**. Ví dụ đơn đặt hàng có một `List<OrderLine>`, trong đó mỗi dòng phải có mã sản phẩm và số lượng hợp lệ.

Nếu đặt `@NotBlank` và `@Min` trên `OrderLine` rồi chỉ validate đối tượng cha, các quy tắc trên đối tượng con **không nhất thiết tự chạy**. Jakarta Bean Validation dùng annotation **`@Valid`** (`jakarta.validation.Valid`) để đánh dấu những quan hệ phải được đi sâu (*cascaded validation*).

Mục tiêu bài học là phân biệt ba việc khác nhau:

1. Kiểm tra **bản thân container** (danh sách có null/rỗng không?): `@NotNull`, `@NotEmpty`, `@Size`.
2. Kiểm tra **giá trị phần tử** (phần tử có null, chuỗi có rỗng...?): annotation trực tiếp trên **type argument** như `List<@NotNull Item>` hoặc `Map<@NotBlank String, ...>`.
3. Kiểm tra **các ràng buộc bên trong object phần tử**: `List<@Valid Item>`, mảng được đánh dấu `@Valid`, hoặc `Map<K, @Valid Item>`.

Ba mục đích này có thể phối hợp nhưng không thay thế nhau. `@Valid` tự nó **không phải** constraint kiểm tra `null`, độ dài, kích thước hay tính hợp lệ của từng ký tự.

Ví dụ minh họa xuyên suốt:

```java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public class OrderLine {
    @NotBlank
    private String sku;

    @Min(1)
    private int quantity;

    // Constructor/getter/setter tùy mô hình dữ liệu và cách binding
}
```

Đây là đoạn khai báo model để giải thích; chương trình Java 17 chạy độc lập nằm ở mục 6.

## 2. Nguyên tắc `@Valid`: đi từ cha xuống con

Xét object cha:

```java
import jakarta.validation.Valid;
import java.util.List;

public class Order {
    private List<@Valid OrderLine> lines;
}
```

Khi Jakarta provider thực thi `validator.validate(order)`, nó kiểm tra các constraint của `Order`, sau đó đi theo các quan hệ `@Valid` tới từng `OrderLine` thực tế và tiếp tục kiểm tra `@NotBlank`, `@Min` của chúng.

Luồng suy nghĩ:

```text
validator.validate(order)
          |
          v
      Order.lines
          |
          v
  List<@Valid OrderLine>
          |
          +--> OrderLine[0] --> sku / quantity
          |
          +--> OrderLine[1] --> sku / quantity
          |
          +--> ...
```

Các điểm cần hiểu:

- **Mỗi phần tử không null** được lấy ra từ container được đánh dấu cascade sẽ được kiểm tra theo constraints của kiểu thực tế (kể cả subclass phù hợp).
- `@Valid` có thể tiếp tục đi sâu qua object khác chứa quan hệ `@Valid` — đó là validation của **đồ thị đối tượng**, không chỉ một mức.
- **Tham chiếu null được bỏ qua khi cascade.** Nếu phần tử bắt buộc tồn tại, cần thêm `@NotNull`.
- Jakarta provider phải tránh lặp vô hạn trong đồ thị có chu trình tham chiếu. Điều này không đồng nghĩa mọi lần kiểm tra cùng object ở những nhánh khác nhau đều được gộp thành một kết quả duy nhất.
- Không bắt buộc phải có Spring MVC mới dùng được cơ chế này: đây là phần của **Jakarta Validation provider**. Spring thường gọi thông qua adapter khi xử lý request.

Từ Jakarta Bean Validation 2.0 trở đi, có thể đặt `@Valid` trực tiếp **trên type argument** của container, chẳng hạn `List<@Valid OrderLine>`. Đây là cách viết dễ đọc và rõ ràng cho code mới.

## 3. Cascade qua `List` và các `Iterable`

### 3.1. Danh sách object

Để kiểm tra các constraint bên trong từng dòng:

```java
private List<@Valid OrderLine> lines;
```

Để vừa từ chối danh sách null/rỗng, vừa từ chối phần tử null và kiểm tra object phần tử:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.List;

@NotEmpty
private List<@NotNull @Valid OrderLine> lines;
```

Các annotation có vị trí và ý nghĩa riêng:

| Khai báo | Điều kiện kiểm tra |
| --- | --- |
| `@NotNull List<OrderLine>` | Container không null, nhưng có thể rỗng |
| `@NotEmpty List<OrderLine>` | Container không null và có ít nhất một phần tử |
| `@Size(min=1,max=10) List<OrderLine>` | Kích thước container nằm trong khoảng |
| `List<@NotNull OrderLine>` | Mỗi phần tử không được null |
| `List<@Valid OrderLine>` | Cascade vào constraints trên từng object phần tử không null |
| `@NotEmpty List<@NotNull @Valid OrderLine>` | Kết hợp cả ba yêu cầu |

Phân tích một số input:

- `lines = null`: `@NotEmpty` vi phạm; `@Valid` không thể đi sâu vào một tham chiếu null.
- `lines = []`: `@NotEmpty` vi phạm; không có phần tử để cascade.
- `lines = [null]`: container **không rỗng**; `@NotNull` ở type argument vi phạm, còn `@Valid` bỏ qua phần tử null.
- `lines = [OrderLine(sku="",quantity=0)]`: `@NotNull` ở phần tử đạt; cascade qua `@Valid` và tìm hai constraint vi phạm trên `OrderLine`.
- `lines = [OrderLine(sku="A1",quantity=2)]`: mọi kiểm tra trên đạt.

### 3.2. Constraint trên phần tử không cần `@Valid` nếu chỉ kiểm tra chính giá trị

Ví dụ:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import java.util.List;

private List<@NotBlank @Email String> emails;
```

`@NotBlank` và `@Email` là **container-element constraints** đặt trực tiếp trên `String`. Provider xử lý chúng bằng **value extractor** cho container được hỗ trợ. Chúng **không cần `@Valid`** vì đang kiểm tra chính phần tử `String`, không cascade vào các thuộc tính bên trong một bean khác.

Ngược lại, chỉ khai báo:

```java
private List<OrderLine> lines;
```

sẽ **không tự đi sâu** kiểm tra `@NotBlank` và `@Min` trong `OrderLine` khi bạn chỉ gọi `validator.validate(order)`.

### 3.3. `List`, `Set`, `Iterable` và vị trí lỗi

Các container hỗ trợ phổ biến gồm `List`, `Set` và các implementation `Iterable`. Provider có thể ghi **index** cho phần tử trong `List`, nhưng với `Set` hoặc `Iterable` không bảo đảm thứ tự/index, đường dẫn lỗi có thể không có index ổn định.

Do đó khi thiết kế API:

- Dùng `ConstraintViolation.getPropertyPath()` để đọc path.
- Dùng `Path.Node.isInIterable()`, `getIndex()` và `getKey()` để lấy metadata tương ứng nếu cần.
- Không giả định chuỗi từ `path.toString()` luôn giống hệt giữa mọi provider/phiên bản.
- Nếu muốn giao diện giữ lỗi theo một dòng ổn định trong danh sách đang được sắp xếp/xóa, có thể dùng **định danh nghiệp vụ** của dòng kết hợp với path, thay vì coi index là ID vĩnh viễn.

## 4. Cascade qua mảng (`T[]`)

Mảng object cũng được hỗ trợ trong kiểm tra đồ thị đối tượng. Cách viết rõ ràng và thông dụng:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

public class WarehouseBatch {

    @NotNull
    @Valid
    private OrderLine[] lines;
}
```

Đặt `@Valid` trên field mảng kiểu đối tượng cho phép provider đi vào **từng `OrderLine` của mảng**. Với ví dụ `lines = new OrderLine[] { new OrderLine("", 0) }`, nếu validate `WarehouseBatch`, provider sẽ phát hiện các lỗi về `sku` và `quantity` trong phần tử đầu.

Phân biệt:

- `@NotNull` trên **mảng** chỉ buộc bản thân mảng khác `null`; nó không bắt mọi slot đều chứa object.
- `@Valid` đi vào các object phần tử **không null**, nhưng không tự báo lỗi với slot null.
- Một mảng rỗng vẫn thỏa `@NotNull`; muốn mảng phải có phần tử, dùng `@NotEmpty` hoặc `@Size(min = 1)`.
- Với dữ liệu form/API mà null element không được phép, cần ràng buộc phần tử theo cú pháp type-use/khả năng provider hoặc quy tắc bổ sung được kiểm thử; đừng nhầm `@NotNull` đặt trên field mảng với `@NotNull` của từng phần tử.
- Mảng primitive như `int[]` không chứa object bean để cascade vào các field; thông thường các ràng buộc giá trị phần tử thuộc loại khác, không phải `@Valid` vào một bean.

Về truyền dữ liệu trong JSON: khi Jackson chuyển mảng JSON thành `OrderLine[]`, validation xảy ra **sau bước deserialize**. Nếu JSON có phần tử sai cấu trúc khiến deserialize thất bại, đó chưa chắc là `ConstraintViolation`. Nếu object phần tử tạo thành công nhưng vi phạm `@NotBlank`, `@Min`, lỗi xuất hiện ở bước Bean Validation.

**Nên chọn mảng hay `List`?** Trong DTO mới, `List<@NotNull @Valid OrderLine>` thường dễ diễn đạt constraint cho phần tử và thao tác với collection. Mảng vẫn hợp lệ khi hợp đồng Java/JSON cần mảng hoặc dùng API legacy. Chọn theo kiểu dữ liệu và hợp đồng, không vì một định kiến rằng mảng không cascade được.

## 5. Cascade qua `Map`: kiểm tra khóa và giá trị

`Map<K,V>` có hai vị trí type argument khác nhau, vì thế cần đặt annotation đúng nơi.

### 5.1. Kiểm tra giá trị trong Map

```java
import jakarta.validation.Valid;
import java.util.Map;

private Map<String, @Valid OrderLine> linesByCode;
```

Khi validate bean cha, provider đi qua **các value** của map và kiểm tra constraints bên trong từng `OrderLine`. Map có key `"paper"` và value `OrderLine("", 0)` sẽ phát sinh các vi phạm của object value ấy.

Muốn value khác null và phải là bean hợp lệ:

```java
private Map<String, @NotNull @Valid OrderLine> linesByCode;
```

Với map chứa `"paper" -> null`, `@Valid` bỏ qua null; `@NotNull` gắn trên value mới là phần kiểm tra bắt buộc.

### 5.2. Kiểm tra khóa Map

Jakarta Validation cũng có **built-in value extractor cho Map key**, vì vậy có thể đặt constraint hoặc `@Valid` lên **key type**:

```java
import jakarta.validation.constraints.NotBlank;
import java.util.Map;

private Map<@NotBlank String, @Valid OrderLine> linesByCode;
```

Khi key là `" "` hoặc `""`, `@NotBlank` trên key phát hiện vi phạm. Khi value có constraint vi phạm, `@Valid` trên value phát hiện riêng.

Nếu key là một bean có fields:

```java
private Map<@Valid ProductKey, @Valid OrderLine> linesByKey;
```

thì cả **object key** và **object value** được cascade; `ProductKey` cần có constraint của riêng nó. Với Java Map dùng key mutable, hãy rất thận trọng nếu hash/equality phụ thuộc vào field có thể thay đổi sau khi đưa vào map; vấn đề này thuộc thiết kế collection, không được Bean Validation giải quyết.

### 5.3. Đối chiếu từng cấu hình

| Khai báo | Kiểm tra |
| --- | --- |
| `@NotEmpty Map<String,OrderLine>` | Map không null và không rỗng; không tự cascade các value |
| `Map<@NotBlank String,OrderLine>` | Giá trị chuỗi của từng key |
| `Map<String,@NotNull OrderLine>` | Từng value không null |
| `Map<String,@Valid OrderLine>` | Constraints trong bean của từng value |
| `Map<@Valid ProductKey,@Valid OrderLine>` | Constraints trong cả bean key và value |
| `@NotEmpty Map<@NotBlank String,@NotNull @Valid OrderLine>` | Map không rỗng, key không trống, value tồn tại và hợp lệ |

**Chi tiết tương thích với code cũ:** trước Bean Validation 2.0, bạn có thể thấy `@Valid` đặt ở **field Map**:

```java
@Valid
private Map<String, OrderLine> linesByCode;
```

Cách legacy này cascade vào **value** của Map, không tự cascade key. Với code mới, đặt `@Valid` tại type argument (`Map<@Valid Key, @Valid Value>`) để thể hiện rõ chiều cần đi sâu. Không đặt `@Valid` đồng thời trên container và chính type argument của nó chỉ vì nghĩ “càng nhiều càng tốt”: đặc tả khuyến cáo tránh cấu hình trùng cascade.

### 5.4. Đọc path của một vi phạm Map

Giả sử key là `"paper"`, value là `OrderLine(quantity=0)`. Đường dẫn lỗi có thể được provider biểu diễn gần như:

```text
linesByCode[paper].quantity
```

Với constraint áp trên **chính key** như `@NotBlank`, có thể có node container element tên `<map key>`; với constraint trên **chính value**, có thể có node `<map value>`. Cách `toString()` biểu diễn node cụ thể khác nhau theo provider, nên đừng parse chuỗi này như định dạng giao thức bắt buộc.

Đặc tả cung cấp các trường structured trên path node:

```java
for (jakarta.validation.Path.Node node : violation.getPropertyPath()) {
    if (node.isInIterable()) {
        Integer index = node.getIndex(); // Có giá trị cho List/array khi khả dụng
        Object key = node.getKey();      // Có giá trị cho Map khi khả dụng
    }
}
```

Đây là đoạn minh họa bên trong vòng lặp qua `ConstraintViolation<?> violation`; không phải chương trình Java độc lập. `index` hoặc `key` có thể null tùy node và loại container.

## 6. Ví dụ Java 17 chạy độc lập: List, mảng, Map và Map lồng List

Ví dụ dùng Hibernate Validator 8 (Jakarta Validation provider). Nó cố tình tạo lỗi khác nhau ở bốn cấu trúc để quan sát **phạm vi cascade**. Để stdout không phụ thuộc thứ tự của `Set<ConstraintViolation<?>>`, chương trình chỉ in tên annotation constraint vi phạm sau khi sắp xếp.

Tạo dự án Gradle:

```text
cascade-containers/
├── settings.gradle
├── build.gradle
└── src/main/java/ContainerCascadeDemo.java
```

**`settings.gradle`**:

```groovy
rootProject.name = 'cascade-containers'
```

**`build.gradle`**:

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
    mainClass = 'ContainerCascadeDemo'
}
```

Trong Spring Boot 3+, có thể dùng `spring-boot-starter-validation` và để BOM của Boot quản lý phiên bản thay vì cố định provider như dự án độc lập này. `expressly` cung cấp Jakarta Expression Language implementation cho message interpolation.

**`src/main/java/ContainerCascadeDemo.java`**:

```java
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public class ContainerCascadeDemo {

    public static final class Item {
        @NotBlank
        private final String code;

        @Min(1)
        private final int quantity;

        public Item(String code, int quantity) {
            this.code = code;
            this.quantity = quantity;
        }
    }

    public static final class ListCase {
        @NotEmpty
        private final List<@NotNull @Valid Item> items;

        public ListCase(List<Item> items) {
            this.items = items;
        }
    }

    public static final class ArrayCase {
        @NotNull
        @Valid
        private final Item[] items;

        public ArrayCase(Item[] items) {
            this.items = items;
        }
    }

    public static final class MapCase {
        @NotEmpty
        private final Map<@NotBlank String, @NotNull @Valid Item> items;

        public MapCase(Map<String, Item> items) {
            this.items = items;
        }
    }

    public static final class NestedCase {
        private final Map<String, List<@Valid Item>> groups;

        public NestedCase(Map<String, List<Item>> groups) {
            this.groups = groups;
        }
    }

    private static String violationNames(
            Set<? extends ConstraintViolation<?>> violations) {
        return violations.stream()
                .map(v -> v.getConstraintDescriptor()
                        .getAnnotation()
                        .annotationType()
                        .getSimpleName())
                .sorted()
                .collect(Collectors.joining(","));
    }

    private static void show(String label, Object bean, Validator validator) {
        Set<ConstraintViolation<Object>> violations =
                validator.validate(bean);

        System.out.printf("%s: %d [%s]%n",
                label, violations.size(), violationNames(violations));
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            // Một phần tử có code trống, một phần tử null.
            show("List",
                    new ListCase(Arrays.asList(new Item(" ", 2), null)),
                    validator);

            // Mảng: không có lỗi code nhưng quantity=0 vi phạm @Min.
            show("Array",
                    new ArrayCase(new Item[]{new Item("A1", 0)}),
                    validator);

            // Map: key trống, một value có code trống, một value null.
            Map<String, Item> values = new LinkedHashMap<>();
            values.put(" ", new Item(" ", 2));
            values.put("missing", null);
            show("Map", new MapCase(values), validator);

            // Map lồng List: cascade qua cả hai lớp container.
            Map<String, List<Item>> groups = new LinkedHashMap<>();
            groups.put("holiday", List.of(new Item(" ", 2)));
            show("Nested", new NestedCase(groups), validator);
        }
    }
}
```

Chạy trong thư mục dự án bằng Java 17+:

```bash
gradle run --quiet
```

Nếu dùng Gradle Wrapper: Linux/macOS `./gradlew run --quiet`; Windows `gradlew.bat run --quiet`.

**Standard output dự kiến**:

```text
List: 2 [NotBlank,NotNull]
Array: 1 [Min]
Map: 3 [NotBlank,NotBlank,NotNull]
Nested: 1 [NotBlank]
```

Phân tích kết quả:

1. **List:** `ListCase.items` không rỗng nên `@NotEmpty` đạt. `Item(" ", 2)` bị `@NotBlank` qua `@Valid`; slot null bị `@NotNull` trên type argument, dù `@Valid` không đi vào null.
2. **Array:** `Item[]` không null; annotation `@Valid` trên field mảng đi vào phần tử, `quantity=0` vi phạm `@Min(1)`.
3. **Map:** key `" "` vi phạm `@NotBlank` ở key type. Value tại key đó là `Item(" ",2)` và vi phạm `@NotBlank` ở field `code`. Value tại key `"missing"` là null, vi phạm `@NotNull` ở value type. Tổng **3** violations.
4. **Nested:** `Map<String, List<@Valid Item>>` đi qua value extractor của Map rồi của List để tới `Item`; code trống vi phạm `@NotBlank`.

`ValidatorFactory` được đóng bằng try-with-resources; đây là chương trình Java độc lập, không có Spring ApplicationContext. Provider có thể ghi log khởi động ra stderr tùy cấu hình; phần trên mô tả **standard output của chương trình**.

Để xem đường dẫn từng lỗi thay vì chỉ tên constraint, thay thân hàm `show` bằng cách duyệt:

```java
violations.stream()
        .map(v -> v.getPropertyPath() + " -> " + v.getMessage())
        .sorted()
        .forEach(System.out::println);
```

Đây là đoạn thay thế **bên trong** hàm `show` đã có, không phải tệp chạy độc lập. Output đường dẫn có index/key, nhưng chuỗi path cuối cùng phụ thuộc provider và vị trí constraint.

## 7. Cascade nhiều tầng: `Map<String, List<@Valid Item>>`

Trong hệ thống lớn, dữ liệu có thể chứa nhiều lớp container:

```java
private Map<String, List<@Valid OrderLine>> linesByWarehouse;
```

Cách đọc từ trái sang phải:

1. `linesByWarehouse` là một Map có key `String`.
2. Mỗi value là một `List<OrderLine>`.
3. `@Valid` nằm trên type argument của List nên từng `OrderLine` được cascade.
4. Khi object `OrderLine` có `@Valid` sang object khác, validation tiếp tục đi sâu.

Muốn kiểm soát container, có thể bổ sung các constraint ở mỗi mức:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

@NotEmpty
private Map<
        @NotBlank String,
        @NotEmpty List<@NotNull @Valid OrderLine>
        > linesByWarehouse;
```

Khai báo trên mang các ý nghĩa:

- Map phải có ít nhất một entry.
- Key không được trống.
- Mỗi value List không được null/rỗng (`@NotEmpty`).
- Mỗi phần tử của List không được null (`@NotNull`) và được cascade (`@Valid`).

Các ràng buộc trực tiếp trên type argument như `@NotEmpty List<...>` hoạt động nhờ **value extractors**. Đặc tả Jakarta định nghĩa value extractors cho những container Java phổ biến; Hibernate Validator 8 hỗ trợ thêm một số loại đặc thù. Với một container tự viết, có thể phải đăng ký `ValueExtractor` phù hợp. Nếu không có extractor hợp lệ hoặc xảy ra mơ hồ, provider có thể báo `ConstraintDeclarationException`/`ValidationException` khi chạy; không nên giả định mọi generic wrapper tùy ý đều có cascade tự động.

### `Map` chứa object có `List` lồng bên trong

Một tình huống khác:

```java
public class Shipment {
    @NotEmpty
    private Map<String, @Valid Warehouse> warehouses;
}

public class Warehouse {
    @NotEmpty
    private List<@Valid OrderLine> lines;
}
```

Đây là các đoạn minh họa type/field cần bổ sung import, constructor và các phần khác trước khi chạy. Khi validate `Shipment`, provider vào từng `Warehouse` qua `@Valid`, rồi vào từng `OrderLine` qua `@Valid` tiếp theo. Nếu thiếu `@Valid` ở cấp `Warehouse`, đường cascade sẽ dừng tại đó dù cấp dưới khai báo đầy đủ constraint.

Đặc tả yêu cầu provider tránh vòng lặp vô hạn trong đồ thị có quan hệ hai chiều, ví dụ `OrderLine` tham chiếu ngược về `Shipment`. Dù vậy, nên thiết kế quan hệ validation rõ ràng để tránh kiểm tra không cần thiết hoặc nhiều lỗi khó hiểu.

## 8. Groups và chuyển nhóm khi cascade

Jakarta Validation có **groups** để chọn bộ constraint. Mặc định, `validator.validate(object)` dùng nhóm `jakarta.validation.groups.Default`.

Nếu `OrderLine` có constraint chỉ thuộc `PublishChecks` và validator đang chạy nhóm `Default`, constraint đó không tự chạy chỉ vì có `@Valid` từ cha. Cơ chế cascade đi tiếp với nhóm validation đang áp dụng, trừ khi có cấu hình **group conversion**:

```java
import jakarta.validation.Valid;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.groups.Default;

private List<
        @Valid
        @ConvertGroup(from = Default.class, to = PublishChecks.class)
        OrderLine
        > lines;
```

Đây là **một ví dụ khai báo nâng cao**, giả định `PublishChecks` đã được định nghĩa, không phải chương trình độc lập. `@ConvertGroup` trên quan hệ cascade chuyển nhóm `Default` thành `PublishChecks` khi đi vào từng phần tử. Chỉ dùng khi các bước tạo/sửa/publish thực sự có các quy tắc khác nhau; cấu hình groups quá phức tạp có thể làm mất các kiểm tra mong đợi.

Các lỗi liên quan groups thường xuất phát từ việc constraints chỉ được đặt vào nhóm `Default` hoặc nhóm riêng, nhưng luồng gọi validation không truyền nhóm đúng. Khi thấy “có `@Valid` mà không có lỗi”, nên kiểm tra **groups** bên cạnh việc kiểm tra vị trí annotation và provider.

## 9. Tích hợp với Spring MVC/Spring Boot

Trong Spring Framework 6+/Spring Boot 3+, dùng các annotation của Jakarta (`jakarta.validation.Valid`, `jakarta.validation.constraints.*`). Spring Web MVC có thể sử dụng adapter Jakarta để chạy validation khi binding request thành command object.

Ví dụ DTO Java 17 dùng `record`:

```java
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public record LineInput(
        @NotBlank String sku,
        @Min(1) int quantity
) {}

public record OrderInput(
        @NotEmpty List<@NotNull @Valid LineInput> lines
) {}
```

Đây là **các định nghĩa kiểu minh họa**; trong code Java thực tế hãy đặt từng public record vào tệp cùng tên hoặc bỏ `public` để dùng cùng package. Với `record`, Jackson/Spring Boot cần cấu hình hỗ trợ record theo phiên bản đang dùng (Spring Boot 3+ thường có).

Controller minh họa:

```java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    @PostMapping("/orders")
    public ResponseEntity<String> create(@Valid @RequestBody OrderInput input) {
        return ResponseEntity.ok("accepted");
    }
}
```

Controller yêu cầu `@Valid` trên **object cha `OrderInput`**; từ đây Jakarta provider nhìn thấy `List<@NotNull @Valid LineInput>` và đi sâu từng phần tử. Nếu request gửi:

```json
{
  "lines": [
    {"sku": "A1", "quantity": 2},
    {"sku": "", "quantity": 0}
  ]
}
```

sau khi deserialize thành công, phần tử thứ hai vi phạm cả `@NotBlank` và `@Min`. Với cấu hình mặc định, Spring MVC thường trả HTTP 400 cho lỗi object validation nếu không được controller/exception handler xử lý riêng; loại exception hay được gặp là `MethodArgumentNotValidException` đối với validation của command object.

Điểm quan trọng về **request container trực tiếp**: chữ ký controller như `@Valid @RequestBody List<LineInput> lines` có ngữ nghĩa validation khác so với một command object `OrderInput` được đánh dấu `@Valid`. Theo tài liệu Spring MVC, đường object validation tự động của `@RequestBody` tập trung vào **command object, không phải container Map/Collection trực tiếp**; method validation có quy tắc riêng. Để hành vi dễ hiểu và kiểm thử, có thể dùng wrapper DTO như `OrderInput`, hoặc cấu hình phương pháp validation cụ thể cho endpoint nhận container trực tiếp.

Nếu muốn tự xử lý lỗi trong controller, với mô hình phù hợp có thể đặt `BindingResult` **ngay sau** tham số có `@Valid`:

```java
@PostMapping("/orders")
public ResponseEntity<?> create(
        @Valid @RequestBody OrderInput input,
        org.springframework.validation.BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body(errors.getFieldErrors()
                .stream()
                .map(e -> e.getField() + ": " + e.getCode())
                .toList());
    }
    return ResponseEntity.ok("accepted");
}
```

Đây là **đoạn method minh họa** cần các import `@PostMapping`, `@RequestBody`, `@Valid`, `ResponseEntity` và class/DTO tương ứng. Không nên trả nguyên rejected value hoặc dữ liệu riêng tư trong response lỗi.

Spring MVC cũng phân biệt **binding/deserialization errors**, **object validation** và **method validation** (có thể liên quan `HandlerMethodValidationException` ở các phiên bản hiện đại). JSON không parse được có thể bị chặn **trước khi** các constraint trên List/Map được kiểm tra. Hãy test từng nhánh nếu API cần báo lỗi ổn định.

## 10. Kiểm thử và lỗi phổ biến

### Ma trận test tối thiểu

| Đầu vào | Khai báo liên quan | Kỳ vọng |
| --- | --- | --- |
| `null` ở field list | `@NotEmpty List<...>` | Vi phạm container |
| `[]` | `@NotEmpty List<...>` | Vi phạm container |
| `[null]` | `List<@NotNull @Valid Item>` | Vi phạm `@NotNull` của phần tử |
| `[Item(code="",quantity=0)]` | `List<@Valid Item>` | Vi phạm constraints bên trong `Item` |
| `new Item[]{Item("A",0)}` | `@Valid Item[]` | Vi phạm `@Min` trong phần tử |
| `Map` có key `""` | `Map<@NotBlank String,...>` | Vi phạm key |
| `Map` có value `null` | `Map<K,@NotNull @Valid Item>` | Vi phạm `@NotNull` của value |
| `Map` có value `Item("",2)` | `Map<K,@Valid Item>` | Vi phạm `@NotBlank` của bean value |
| `Map<K,List<Item>>` thiếu mọi `@Valid` | Không có annotation cascade trên item | Không tự chạy constraint bên trong `Item` |
| `Map<K,List<@Valid Item>>` | Cascade trên nested type argument | Kiểm tra từng `Item` trong từng List |
| Chu trình cha → con → cha | Có `@Valid` ở các quan hệ | Provider phải tránh vòng lặp vô hạn |

Khi kiểm thử, kiểm tra **số lượng lỗi, loại constraint, field path** và phân biệt lỗi trên **container** với lỗi trên **phần tử**. Không phụ thuộc thứ tự của `Set<ConstraintViolation<?>>`. Với Spring MVC, nên có test HTTP gửi request hợp lệ, request có phần tử lỗi và request JSON sai cú pháp.

### Những lỗi nên tránh

1. **Chỉ viết `List<Item>` rồi mong `Item` được validate.** Cần `@Valid` tại đúng quan hệ.
2. **Dùng `@Valid` để cấm null.** Cascade bỏ qua null; thêm `@NotNull` đúng vị trí.
3. **Nghĩ `@NotEmpty` kiểm tra từng object con.** Nó chỉ kiểm tra container có null/rỗng không.
4. **Đặt `@NotNull` trên List rồi nghĩ từng phần tử phải khác null.** Đặt `List<@NotNull Item>` nếu muốn kiểm tra phần tử.
5. **Đánh đồng Map key và Map value.** `Map<@NotBlank String, @Valid Item>` có hai rule khác phía.
6. **Dùng kiểu legacy `@Valid Map<K,V>` và mong key cũng được cascade.** Đặt `@Valid` trên key type khi key là bean cần kiểm tra.
7. **Thiếu `@Valid` ở một mắt xích trong nhiều tầng bean.** Cascade có thể dừng ở tầng đó.
8. **Đặt `@Valid` ở cả container và element mà không có chủ đích.** Có thể tạo cấu hình trùng; ưu tiên type argument rõ ràng cho generic containers.
9. **Dùng `getPropertyPath().toString()` như chuẩn giao thức cố định.** Xem từng node và metadata `index/key`, test với provider thực tế.
10. **Nhầm việc Spring MVC gọi validation với Jakarta API thuần Java.** Cần Jakarta provider và Spring integration đúng; JSON conversion diễn ra trước validation.
11. **Bỏ qua groups.** Constraint thuộc nhóm khác có thể không chạy dù quan hệ cascade có `@Valid`.
12. **Mong mọi generic container tự được hỗ trợ.** Custom container có thể cần `ValueExtractor`.
13. **Trả nguyên dữ liệu sai cho client/log.** Violation chứa path, message và đôi khi invalid value nhạy cảm.
14. **Không test phần tử null và container rỗng.** Đây là ranh giới quan trọng nhất của `@Valid` và `@NotNull`/`@NotEmpty`.

### Tự kiểm tra kiến thức

1. Vì sao `@NotEmpty List<@Valid Item>` không chặn `[null]`? **List có một phần tử nên không rỗng; `@Valid` bỏ qua phần tử null.** Muốn chặn, thêm `@NotNull` trên type argument.
2. Muốn kiểm tra đối tượng key trong Map, đặt `@Valid` ở đâu? **Trên type argument của key**, ví dụ `Map<@Valid ProductKey, ...>`.
3. Vì sao `List<@NotBlank String>` không cần `@Valid`? **Constraint áp trực tiếp lên phần tử String**, không đi sâu vào một object bean khác.
4. Với `Map<String,List<@Valid Item>>`, provider đi qua mấy lớp container để tới Item? **Map value rồi List element**; nó dùng value extractor tương ứng.
5. Nếu `@Valid` có mặt nhưng một constraint riêng không chạy, cần kiểm tra gì? **Kiểu và vị trí annotation, provider, giá trị null, validation groups, đường gọi validation và các quan hệ cascade trung gian.**
6. Nếu controller nhận trực tiếp `List<Item>` từ JSON, có thể mặc định hành vi giống DTO wrapper với `@Valid` không? **Không nên mặc định**; cần kiểm tra quy tắc validation của Spring MVC và cấu hình endpoint thực tế.

## 11. Tài liệu tham khảo

- [Jakarta Bean Validation 3.0 — Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): mục Object graph validation, container-element constraints và value extractors.
- [Hibernate Validator 8.0 — Reference Guide](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/): kiểm tra List/Map, cascaded validation of containers, nested container elements, property paths.
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): provider Jakarta và Spring `LocalValidatorFactoryBean`.
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): object validation, `@Valid`/`@Validated`, method validation và lỗi MVC.
- [Jakarta Validation 3.0 — `@Valid` Javadoc](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Valid.html): cách đánh dấu quan hệ cascade.

**Ghi nhớ:** muốn kiểm tra constraint của đối tượng **bên trong** List, mảng hay Map, phải khai báo `@Valid` đúng vị trí. Muốn kiểm tra **container hoặc giá trị phần tử** thì dùng `@NotEmpty`, `@NotNull`, `@Size`, `@NotBlank`... ở cấp thích hợp. Với Map, hãy xét **key và value** độc lập và nhớ xử lý các container lồng nhau.
