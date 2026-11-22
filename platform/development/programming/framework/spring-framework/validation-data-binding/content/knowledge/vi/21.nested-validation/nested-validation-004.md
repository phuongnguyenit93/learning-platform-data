# Ràng buộc trên khóa và giá trị của Map

> **Bối cảnh:** Jakarta Bean Validation trong Java 17+ và Spring Framework/Spring Boot 3.x, thuộc chủ đề **kiểm tra lồng nhau** (*nested validation*). Trọng tâm là đặt constraint trên từng **khóa** và **giá trị** của `Map<K, V>`, khác với constraint áp lên chính Map, kết hợp `@Valid` để kiểm tra bean bên trong và đọc đúng đường dẫn lỗi.

## 1. Ba tầng validation khác nhau trong một Map

Một `Map<K, V>` có ít nhất ba cấp có thể kiểm tra:

1. **Chính Map:** biến `Map` có null hay không, có bao nhiêu entry, v.v.
2. **Từng khóa K:** key có null, rỗng, sai định dạng hoặc là object không hợp lệ hay không.
3. **Từng giá trị V:** value có null, quá nhỏ, sai định dạng; nếu value là một bean hoặc collection, có cần kiểm tra sâu hơn hay không.

Ba cấp này **không tự động suy ra lẫn nhau**.

```text
OrderRequest
   │
   └── items : Map<K, V>                       ← constraint trên cả Map
          │
          ├── key "PEN-01"                     ← constraint trên type argument K
          └── value Item(name, quantity)      ← constraint trên type argument V
                    │
                    ├── name                   ← constraint trong Item, cần cascade
                    └── quantity               ← constraint trong Item, cần cascade
```

Ví dụ khai báo đầy đủ:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.Map;

public class CartRequest {
    @NotEmpty
    private Map<@NotBlank String, @NotNull @Valid Item> items;
}
```

Đây là **đoạn mã minh họa**; muốn biên dịch cần định nghĩa thêm `Item` và thành phần còn lại của DTO. Ý nghĩa từng vị trí:

- `@NotEmpty` **đặt trên field `items`**: Map phải khác null và có tối thiểu một entry.
- `@NotBlank` **đặt trước `String` ở type argument thứ nhất**: mỗi khóa phải là chuỗi có nội dung (khác null, không rỗng, không toàn whitespace).
- `@NotNull` **đặt trước `Item` ở type argument thứ hai**: mỗi value không được null.
- `@Valid` **đặt trên cùng type argument `Item`**: khi value khác null, tiếp tục kiểm tra những constraint bên trong mỗi object `Item`.

Từ Bean Validation **2.0** trở đi (sang namespace `jakarta.validation` trong Jakarta Validation 3.x), việc đặt annotation tại **type argument** của container như `Map<@NotBlank String, @Valid Item>` là cơ chế chuẩn để kiểm tra từng phần tử của container (*container element constraints*).

## 2. Syntax: annotate đúng vị trí

### 2.1. Constraint trên cả Map

```java
@NotNull
Map<String, Item> items;

@NotEmpty
Map<String, Item> requiredItems;
```

- `@NotNull` chỉ cấm `items == null`; `Map.of()` (rỗng) vẫn hợp lệ.
- `@NotEmpty` cấm cả null và Map rỗng; một entry có key/value không hợp lệ **vẫn làm Map được coi là không rỗng**.
- `@Size(min = 1, max = 20)` giới hạn số entry; theo đặc tả `@Size` cho phép null, nên nếu Map bắt buộc phải hiện diện cần kết hợp với `@NotNull` hoặc dùng `@NotEmpty` cùng `@Size(max=20)`.
- `@NotBlank` **không hỗ trợ** Map: nó dành cho `CharSequence`, không phải container.

### 2.2. Constraint trên khóa (K)

```java
Map<@NotBlank String, Item> itemsBySku;

Map<@NotNull @Pattern(regexp = "[A-Z0-9-]+") String, Item>
        itemsByCode;
```

Ở type argument **đầu tiên** của `Map<K, V>`, `@NotBlank` cấm cả key null/rỗng/toàn dấu cách; `@Pattern` kiểm tra format chuỗi nhưng **tự nó cho phép null**, vì vậy có thể ghép `@NotNull` nếu key bắt buộc khác null. Với ràng buộc trên khóa là DTO/bean, có thể đặt `@Valid` lên type argument K để cascade vào bean-key, miễn có value extractor hỗ trợ.

### 2.3. Constraint trên giá trị (V)

```java
Map<String, @NotNull Integer> scores;
Map<String, @Positive Integer> stockLevels;
Map<String, @NotBlank String> displayLabels;
Map<String, @NotNull @Valid Item> items;
```

Ở type argument **thứ hai**:

- `@NotNull` kiểm tra value không null.
- `@Positive` kiểm tra số phải dương; giá trị null **thỏa riêng `@Positive`**, nên phải thêm `@NotNull` nếu không chấp nhận null.
- `@NotBlank` dành cho value là `CharSequence`.
- `@Valid` làm **cascaded validation** với bean bên trong value; nếu `Item.name` có `@NotBlank` mà thiếu `@Valid` trên value, constraint trong `Item` không tự động chạy chỉ vì Map đã có constraint khác.

**Không viết** `@NotNull Map<String, Item> items` rồi coi điều đó đã cấm mọi value null. `@NotNull` ở ngoài chỉ kiểm tra Map, không kiểm tra từng entry.

### 2.4. Bảng so sánh vị trí khai báo

| Khai báo | Điều được kiểm tra | Không mặc nhiên kiểm tra |
| --- | --- | --- |
| `@NotNull Map<K,V> map` | Chính tham chiếu Map không null | Số entry, key, value |
| `@NotEmpty Map<K,V> map` | Map không null, có ≥1 entry | Nội dung key/value |
| `Map<@NotBlank String,V>` | Mỗi key là text có nội dung | Map rỗng và value |
| `Map<K,@NotNull V>` | Mỗi value khác null | Map rỗng và key |
| `Map<K,@Valid V>` | Constraint bên trong bean value | Value null và Map rỗng, nếu không ghép constraint khác |
| `Map<@Valid KeyBean,@Valid ValueBean>` | Cascade vào object key lẫn value | Map có bắt buộc có entry hay không |
| `@NotEmpty Map<@NotBlank String,@NotNull @Valid V>` | Map không rỗng, key hợp lệ, value không null và valid sâu | Những quy tắc nghiệp vụ không biểu diễn bằng constraint đã khai báo |

## 3. Bên dưới framework: ValueExtractor của Map

Bean Validation không thể lấy từng khóa/giá trị chỉ bằng constraint trên Map. Với *container element constraints*, validation provider sử dụng cơ chế `ValueExtractor`:

```text
Validator.validate(request)
        │
        ▼
Đọc constraint ở field items : Map<K,V>
        │
        ├── @NotEmpty: kiểm tra chính Map
        │
        ├── MapKeyExtractor   → key 1, key 2, ...   → constraint trên K
        │
        └── MapValueExtractor → val 1, val 2, ...   → constraint trên V
                                                          │
                                                          └── @Valid → bean con
```

Theo Jakarta Validation, provider tương thích có các **built-in value extractors** cho khóa và giá trị của `java.util.Map`, nên không cần tự viết extractor khi dùng `Map` thông thường. Value extractor của key dùng tên node dạng `<map key>` và của value dùng `<map value>`. Khi tạo violation path, framework còn có thể ghi nhận khóa entry tại node tương ứng.

Mỗi constraint ở type argument K/V được provider ghép với extractor thích hợp. Nếu dùng **container tùy chỉnh** không có extractor tương ứng, hoặc đăng ký những extractor xung đột, có thể phát sinh lỗi cấu hình kiểu `ConstraintDeclarationException` thay vì một violation của dữ liệu. Chỉ viết `ValueExtractor` riêng khi thật sự cần hỗ trợ container ngoài những kiểu chuẩn và hiểu cơ chế giải quyết extractor.

**Lưu ý:** Built-in Map key/value extraction không biến Map thành database constraint hay một công cụ kiểm tra logic toàn bộ tập entry. Ví dụ tính duy nhất của **giá trị** giữa nhiều entry, quan hệ giữa key và value, hoặc yêu cầu một tập khóa bắt buộc phải xuất hiện thường cần custom constraint hoặc logic nghiệp vụ riêng.

## 4. Ví dụ Java 17+ chạy được: Map, key, value và bean con

Ví dụ dùng Jakarta Bean Validation với Hibernate Validator (được starter của Spring Boot 3.3.5 đưa vào classpath). Chương trình không cần web server và **không tạo Spring ApplicationContext**.

Cấu trúc:

```text
map-validation-demo/
├── pom.xml
└── src/main/java/demo/MapValidationDemo.java
```

**`pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>map-validation-demo</artifactId>
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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/demo/MapValidationDemo.java`:**

```java
package demo;

import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class MapValidationDemo {

    // Bean con: được kiểm tra sâu nếu có @Valid ở value type.
    static final class Item {
        @NotBlank
        private final String name;

        @Positive
        private final int quantity;

        Item(String name, int quantity) {
            this.name = name;
            this.quantity = quantity;
        }
    }

    static final class Catalog {
        @NotEmpty
        private final Map<@NotBlank String, @NotNull @Valid Item> items;

        Catalog(Map<String, Item> items) {
            this.items = items;
        }
    }

    // Container lồng nhau: Map value là List<String>.
    static final class TagGroups {
        @NotEmpty
        private final Map<
                @NotBlank String,
                @NotEmpty List<@NotBlank String>> tags;

        TagGroups(Map<String, List<String>> tags) {
            this.tags = tags;
        }
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            show(validator, "catalog.nullMap", new Catalog(null));
            show(validator, "catalog.emptyMap",
                    new Catalog(Map.of()));
            show(validator, "catalog.invalidKey",
                    new Catalog(Map.of(" ", new Item("Pen", 2))));

            // Map.of() cấm null; dùng LinkedHashMap để test value null.
            Map<String, Item> withNullValue = new LinkedHashMap<>();
            withNullValue.put("PEN-01", null);
            show(validator, "catalog.nullValue",
                    new Catalog(withNullValue));

            show(validator, "catalog.invalidItem",
                    new Catalog(Map.of("PEN-01", new Item(" ", 0))));
            show(validator, "catalog.valid",
                    new Catalog(Map.of("PEN-01", new Item("Pen", 2))));

            show(validator, "tags.emptyList",
                    new TagGroups(Map.of("color", List.of())));
            show(validator, "tags.blankElement",
                    new TagGroups(Map.of("color", List.of(" "))));
            show(validator, "tags.valid",
                    new TagGroups(Map.of("color", List.of("red"))));
        }
    }

    private static void show(Validator validator,
                             String label, Object bean) {
        // In tên constraint thay vì message/path: output không
        // phụ thuộc locale, thứ tự Map hay cách render path của provider.
        List<String> failures = validator.validate(bean).stream()
                .map(v -> v.getConstraintDescriptor()
                        .getAnnotation()
                        .annotationType()
                        .getSimpleName())
                .sorted()
                .toList();

        System.out.println(label + " -> " + failures);
    }
}
```

Chạy ở thư mục chứa `pom.xml` (yêu cầu Maven và Java 17+):

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.MapValidationDemo
```

**Đầu ra của chương trình** (không tính log ngoài chương trình của Maven/provider):

```text
catalog.nullMap -> [NotEmpty]
catalog.emptyMap -> [NotEmpty]
catalog.invalidKey -> [NotBlank]
catalog.nullValue -> [NotNull]
catalog.invalidItem -> [NotBlank, Positive]
catalog.valid -> []
tags.emptyList -> [NotEmpty]
tags.blankElement -> [NotBlank]
tags.valid -> []
```

Giải thích từng ca:

1. `catalog.nullMap`: Map null → chỉ `@NotEmpty` trên field Map báo lỗi; không có entry để kiểm tra key/value.
2. `catalog.emptyMap`: Map có thật nhưng rỗng → vẫn lỗi `@NotEmpty`; không có key/value để kiểm tra.
3. `catalog.invalidKey`: Map có một entry nên `@NotEmpty` qua; key `" "` vi phạm `@NotBlank`; value có dữ liệu hợp lệ.
4. `catalog.nullValue`: Map chứa key hợp lệ với value null. `@NotNull` trên V báo lỗi; `@Valid` bỏ qua việc cascade vào null.
5. `catalog.invalidItem`: key hợp lệ, value không null nhưng bean `Item` chứa `name = " "` và `quantity = 0`; qua `@Valid` sinh hai lỗi `@NotBlank` và `@Positive`.
6. `catalog.valid`: ba tầng đều hợp lệ.
7. `tags.emptyList`: Map không rỗng và key đúng, nhưng List ở value rỗng nên `@NotEmpty` trên type argument V báo lỗi.
8. `tags.blankElement`: value List có một phần tử nên qua `@NotEmpty`, nhưng phần tử `" "` vi phạm `@NotBlank`.
9. `tags.valid`: có key hợp lệ, List có phần tử và từng phần tử hợp lệ.

Đầu ra được tạo bằng cách **sắp xếp tên loại constraint**, không in message hoặc đường dẫn có chứa key: điều này giữ cho ví dụ nhất quán khi provider/locale khác nhau. Khi debug ứng dụng thực, vẫn cần lấy `ConstraintViolation#getPropertyPath()` để định vị chính xác lỗi.

### 4.1. Thử thêm key null

`Map.of(...)` của Java không cho tạo key hoặc value null: Java sẽ ném `NullPointerException` **trước khi** Bean Validation được gọi. Nếu cần kiểm tra trường hợp key null, dùng một loại Map cho phép null như `HashMap`/`LinkedHashMap`:

```java
Map<String, Item> withNullKey = new LinkedHashMap<>();
withNullKey.put(null, new Item("Pen", 2));
show(validator, "catalog.nullKey", new Catalog(withNullKey));
```

Đoạn này là phần minh họa **đặt bên trong `main` khi `validator` đang tồn tại**. Kết quả chương trình tương ứng sẽ là:

```text
catalog.nullKey -> [NotBlank]
```

Vì `@NotBlank` trên key từ chối null. Trường hợp Map implementation nào được dùng và việc có cho key null hay không là đặc tính của Map implementation; **không phải** một giới hạn do Bean Validation tự đặt.

## 5. Map có key là bean: cascade vào khóa và giá trị

Từ Bean Validation 2.0+, `@Valid` có thể đặt tại **cả hai type argument**:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import java.util.Map;

public class Index {
    private Map<
            @NotNull @Valid CategoryKey,
            @NotNull @Valid ProductInfo> entries;
}
```

Đây là ví dụ cấu trúc, cần định nghĩa `CategoryKey` và `ProductInfo` trong dự án thực tế. Ý nghĩa:

- `@Valid` ở K đi vào những ràng buộc của object `CategoryKey`.
- `@Valid` ở V đi vào những ràng buộc của object `ProductInfo`.
- `@NotNull` ở K/V chặn key/value null; `@Valid` tự nó không làm null trở thành không hợp lệ.
- Constraint được áp dụng khi một đối tượng `Index` đi qua Bean Validation, và provider có extractor tương ứng.

**Quan trọng về cách dùng Map object làm key:** Java Map dựa trên `equals()`/`hashCode()` để quản lý khóa; mutable key có thể làm hỏng khả năng tra cứu sau khi đưa vào Map. Bean Validation **không** sửa vấn đề này. Nếu key là object, thiết kế value object bất biến và quy tắc equality/hash phù hợp với nghiệp vụ.

### 5.1. Phân biệt `@Valid Map<K,V>` và `Map<K,@Valid V>`

Trong Jakarta Validation, cách dùng truyền thống:

```java
@Valid
private Map<String, ProductInfo> products;
```

thường làm **cascade vào các value của Map**, chứ không kiểm tra ràng buộc trên từng key. Từ Bean Validation 2.0, cú pháp minh bạch hơn là:

```java
private Map<String, @Valid ProductInfo> products;
```

và nếu cần cả key:

```java
private Map<@Valid CategoryKey, @Valid ProductInfo> products;
```

Đừng đặt `@Valid` **cả trên container và trên type argument tương ứng** chỉ để “chắc chắn”: đặc tả khuyên tránh cách đó vì có thể làm phần tử được kiểm tra lặp lại. Chọn vị trí có chủ đích; trong code mới, ưu tiên annotate đúng type argument cần cascade.

### 5.2. `@Valid` không phải constraint cấm null

So sánh:

```java
Map<String, @Valid ProductInfo> a;
Map<String, @NotNull @Valid ProductInfo> b;
```

Nếu một value null (và Map implementation cho phép), `a` **không báo lỗi do `@Valid`**; `b` vi phạm `@NotNull`. Nếu value không null nhưng có một field bên trong không hợp lệ, cả hai đều có thể phát hiện constraint của `ProductInfo`. Đừng dùng `@Valid` thay cho `@NotNull`/`@NotEmpty`.

## 6. Map lồng collection hoặc Map khác

Khi Map value là container, phải đặt annotation **đúng cấp**:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.List;
import java.util.Map;

public class BatchRequest {
    @NotEmpty
    private Map<
            @NotBlank String,
            @NotEmpty List<@NotNull @Valid LineItem>> linesByStore;
}
```

Đây là đoạn minh họa, yêu cầu lớp `LineItem` có constraint và phần còn lại của DTO. Các quy tắc là:

- Map phải không null và có ít nhất một entry.
- Mỗi key tên cửa hàng phải là text có nội dung.
- Mỗi value List phải không null và có ít nhất một phần tử (do `@NotEmpty` trên List).
- Mỗi phần tử `LineItem` phải khác null (do `@NotNull` trên phần tử List).
- Mỗi `LineItem` không null được kiểm tra sâu (do `@Valid` trên phần tử List).

Thêm một cấp Map:

```java
Map<
    @NotBlank String,
    @NotEmpty Map<@NotBlank String, @Positive Integer>>
    inventoryByWarehouse;
```

Ví dụ kiểm tra key ở Map ngoài (warehouse ID), value Map trong không rỗng, key của Map trong (SKU) không blank, số lượng ở Map trong phải dương. **`@Positive` cho phép value null** theo đặc tả; nếu yêu cầu không null, thêm `@NotNull` cho kiểu `Integer`.

Với container lồng nhiều tầng, provider dùng một chuỗi extractor phù hợp để đi xuống từng phần tử. Không thể chỉ đặt `@Valid` trên đối tượng ngoài cùng rồi mong mọi constraint của mọi cấp được suy ra tự động nếu chưa khai báo chúng ở type arguments.

## 7. Đọc `ConstraintViolation`: lỗi ở khóa khác lỗi ở giá trị

Khi dùng Map, chỉ in `violation.getMessage()` thường không đủ. Thông tin hữu ích bao gồm:

- `getPropertyPath()`: đường từ bean gốc tới field, entry Map và có thể tới field của bean con.
- `getConstraintDescriptor().getAnnotation().annotationType()`: ràng buộc nào bị vi phạm.
- `getInvalidValue()`: giá trị nào bị xem là sai (cẩn trọng với dữ liệu nhạy cảm).
- `Path.Node`: thông tin node, `getKind()`, `isInIterable()`, `getKey()`/`getIndex()`, `getContainerClass()` và `getTypeArgumentIndex()` khi phù hợp.

Với Map có các key như `"PEN-01"`, đường dẫn lỗi được provider biểu diễn theo dạng gần với:

```text
items[PEN-01].<map key>
items[PEN-01].<map value>
items[PEN-01].name
items[PEN-01].quantity
```

**Đây là ví dụ định hướng cách đọc, không phải stdout cam kết cho mọi provider/kiểu constraint.** Các segment node, ký hiệu trong dấu ngoặc và cách hiển thị của `Path.toString()` cần được kiểm tra bằng provider cụ thể. Quan trọng là lỗi **ở key** và **ở value** không phải cùng một vị trí; khi cần API error schema ổn định, nên chuyển từ `Path.Node` sang cấu trúc lỗi ứng dụng thay vì copy nguyên string `toString()` làm hợp đồng dài hạn.

Ví dụ lấy metadata để phân biệt:

```java
for (var violation : validator.validate(request)) {
    String constraint = violation.getConstraintDescriptor()
            .getAnnotation()
            .annotationType()
            .getSimpleName();

    System.out.println(constraint
            + " at " + violation.getPropertyPath());
}
```

Đây là đoạn minh họa đặt bên trong scope có `validator` và `request` phù hợp; output phụ thuộc dữ liệu/provider. Trong ứng dụng thực, có thể duyệt `violation.getPropertyPath()` theo từng `Path.Node` và đọc `Node#getKey()`/`getKind()` để tạo thông báo gắn với field/entry cụ thể.

**Bảo mật:** Map key có thể là email, mã bí mật hay dữ liệu người dùng. Việc đưa toàn bộ key hoặc `getInvalidValue()` vào log/API response có nguy cơ lộ thông tin. Cần lọc/ẩn dữ liệu nhạy cảm trước khi ghi log.

## 8. Kích hoạt validation trong Spring MVC

### 8.1. DTO cho request JSON

Trong Spring Boot 3.x, `spring-boot-starter-validation` cung cấp provider Jakarta Validation. Với Spring Web MVC, `@Valid` trên argument `@RequestBody` thường kích hoạt validation sau khi Jackson deserialize JSON thành DTO.

Các đoạn dưới đây là ví dụ **để thêm vào ứng dụng Spring Boot 3 có web MVC và validation**, không phải một file Java độc lập:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

public record CreateCatalogRequest(
    @NotEmpty Map<
        @NotBlank String,
        @NotNull @Valid CatalogItem> items
) {}

public record CatalogItem(
    @NotBlank String name,
    @Positive int quantity
) {}

@RestController
public class CatalogController {
    @PostMapping("/catalog")
    public ResponseEntity<Void> create(
            @Valid @RequestBody CreateCatalogRequest request) {
        // Xử lý nghiệp vụ khi validation thông thường thành công.
        return ResponseEntity.noContent().build();
    }
}
```

Ví dụ JSON hợp lệ:

```json
{
  "items": {
    "PEN-01": { "name": "Blue pen", "quantity": 2 },
    "BOOK-02": { "name": "Notebook", "quantity": 5 }
  }
}
```

Một số request không hợp lệ và lớp vi phạm dự kiến:

| Request/value sau khi deserialize | Vi phạm |
| --- | --- |
| `"items": {}` | `@NotEmpty` trên Map |
| `"items": {" ": {"name": "Pen", "quantity": 1}}` | `@NotBlank` trên key |
| `"items": {"PEN-01": null}` | `@NotNull` trên value |
| `"items": {"PEN-01": {"name": " ", "quantity": 0}}` | `@NotBlank`, `@Positive` bên trong `CatalogItem` thông qua cascade |
| `"items": {"PEN-01": {"name": "Pen", "quantity": 1}}` | Hợp lệ theo các constraint đã định nghĩa |

Cấu trúc HTTP response khi có lỗi phụ thuộc `@ControllerAdvice`, `BindingResult` và Spring configuration; trong xử lý Spring MVC thông thường, lỗi validation của `@Valid @RequestBody` không được xử lý cục bộ dẫn tới HTTP 400. **Việc JSON không parse được có thể làm message converter lỗi trước khi Bean Validation chạy.**

### 8.2. Đừng nhầm JSON Map với constraint trên khóa

Một JSON object bình thường có **tên property là chuỗi**. Jackson thường chuyển những tên property đó thành key của `Map<String, ...>`; nếu dùng `Map<Integer, ...>` hoặc key là object tùy chỉnh, việc chuyển key có thể yêu cầu key deserializer/cấu hình riêng. Đây là việc của **Jackson**, không phải `@NotNull`/`@Pattern` hay `@Valid`.

JSON object cũng không biểu diễn được key null theo cách thông thường như Java `HashMap`. Vì thế, case key null trong unit test Jakarta Validation không nhất thiết có đường đi trực tiếp tương ứng trong JSON request.

Nếu JSON có **tên key lặp**, Jackson hoặc parser có thể ghi đè entry trước, giữ entry sau hoặc áp dụng chế độ phát hiện trùng. Sau khi đã thành Java Map, một key duy nhất chỉ xuất hiện một lần; Bean Validation không thể “tìm lại” cặp key trùng đã mất. Cần cấu hình parser nếu muốn cấm duplicate JSON field names.

### 8.3. `@Valid` ở HTTP boundary và `@Valid` bên trong Map khác nhau

Hai vị trí đều quan trọng:

- `@Valid @RequestBody CreateCatalogRequest request`: yêu cầu MVC kiểm tra DTO gốc sau khi bind.
- `Map<String, @Valid CatalogItem> items`: yêu cầu provider tiếp tục **cascade** từ DTO sang từng value là `CatalogItem`.

Nếu thiếu `@Valid` ở boundary và không có trigger khác, các constraint trong DTO có thể không được đánh giá. Nếu chỉ có `@Valid` ở boundary nhưng value type không có `@Valid`, những constraint trong `CatalogItem` có thể **không được kiểm tra sâu**, dù constraint trực tiếp trên type argument key/value vẫn có thể được đánh giá.

Tương tự, dùng `@Validated` và method validation có những quy tắc kích hoạt riêng. Phải kiểm thử nơi provider thực sự được gọi thay vì suy rằng đặt annotation là đủ.

## 9. Các trường hợp đặc biệt cần hiểu rõ

### 9.1. `null`, Map rỗng và value null không giống nhau

| Dữ liệu | `@NotEmpty` trên Map | `@NotBlank` trên key | `@NotNull` trên value |
| --- | --- | --- | --- |
| `map == null` | Vi phạm | Không có key để kiểm tra | Không có value để kiểm tra |
| `Map.of()` | Vi phạm | Không có key để kiểm tra | Không có value để kiểm tra |
| Map có key `"ok"`, value null | Hợp lệ theo size | Hợp lệ | Vi phạm |
| Map có key `""`, value hợp lệ | Hợp lệ theo size | Vi phạm | Hợp lệ |
| Map có một entry đúng | Hợp lệ | Hợp lệ | Hợp lệ |

`@NotNull`/`@NotBlank` trên type arguments kiểm tra **các entry hiện hữu**, không tự buộc container phải có entry. Do đó, nếu map không được rỗng, đặt thêm `@NotEmpty` trên Map.

### 9.2. Constraint đặt trên Map không thay cho constraint đặt trên phần tử

```java
@NotEmpty
Map<String, String> labels;
```

Map với `{"a": ""}` đáp ứng `@NotEmpty` vì có một entry. Muốn value có nội dung:

```java
@NotEmpty
Map<@NotBlank String, @NotBlank String> labels;
```

Và nếu chỉ cần value khác null nhưng chấp nhận empty string:

```java
@NotEmpty
Map<String, @NotNull String> labels;
```

Chọn theo contract, không phải “annotation nào trông mạnh nhất”.

### 9.3. `@Valid` xử lý đối tượng con, không kiểm tra một mối quan hệ tổng thể

`@Valid` đi theo đồ thị bean và constraint đã khai báo. Nó **không** tự kiểm tra rằng tổng số lượng hàng bằng ngân sách, key SKU khớp `Item.sku`, mọi value trong Map là duy nhất, hoặc phải có key `"PRIMARY"`. Những quy tắc có tính tổng thể có thể cần:

- Method kiểm tra nghiệp vụ khi service nhận DTO đã validate.
- Custom constraint ở mức class (`@ValidCatalog`) với `ConstraintValidator<CatalogConstraint, CatalogRequest>`.
- Một API/domain model bất biến kiểm soát bất biến từ constructor/factory, và kiểm tra lại khi thay đổi.
- Ràng buộc database phù hợp nếu quy tắc phải được bảo vệ trước nhiều đường ghi.

Không nên cố diễn đạt mọi quy tắc liên-entry bằng `@NotBlank` trên từng key hoặc `@NotNull` trên từng value.

### 9.4. Chú ý hỗ trợ kiểu dữ liệu đúng constraint

- `@NotBlank` áp cho `CharSequence`; không đặt lên Map hay bean.
- `@Positive` áp cho kiểu số phù hợp; không đặt lên `String` rồi mong nó parse số.
- `@NotEmpty` áp cho `CharSequence`, `Collection`, `Map` và array; có thể dùng ở Map field hoặc value kiểu `List`/`Map`.
- `@Valid` là dấu chỉ cascade, không phải constraint cấm null.
- `@Pattern` trên `String`/`CharSequence` theo đặc tả không cấm null; kết hợp `@NotNull` hoặc `@NotBlank` nếu cần.
- Với Java 17/Spring Boot 3.x, import `jakarta.validation.*`. Các dự án Spring Boot 2.x thường dùng `javax.validation.*`; trộn namespace không có nghĩa provider mới sẽ hiểu constraint cũ như mong đợi.

### 9.5. Validation group và nhóm kiểm tra lồng nhau

Container element constraints và cascaded validation tham gia cơ chế validation groups như constraint trên field. Nếu nghiệp vụ có `Create` và `Update` groups khác nhau, việc gọi `validator.validate(dto, Create.class)` hoặc cấu hình `@Validated(Create.class)` ở điểm hỗ trợ sẽ ảnh hưởng constraint nào được đánh giá. Khi cascade sang bean khác, group có thể được lan truyền/chuyển đổi theo quy tắc `@ConvertGroup`. Đừng dùng lỗi thiếu group để kết luận validator không hỗ trợ Map keys/values.

### 9.6. Không dựa vào thứ tự Map hoặc violation Set

`Map` có thể có thứ tự duyệt khác nhau theo implementation; `Validator.validate` trả về `Set<ConstraintViolation<T>>` không có thứ tự thứ nhất bất biến. Với test:

- Sắp xếp violations theo field, loại constraint hoặc business error code.
- So sánh **tập** path/type/codes thay vì phụ thuộc vào thứ tự đầu ra.
- Khi key chứa dữ liệu nhạy cảm, tránh snapshot nguyên key vào log.

## 10. Lỗi thường gặp và hướng sửa

| Hiểu sai hoặc lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Chỉ dùng `@NotEmpty Map<K,V>` và nghĩ mọi entry hợp lệ | Key/value có thể sai hoặc null | Gắn constraint trên K/V |
| Dùng `@NotNull Map<K,V>` để cấm value null | Chỉ cấm chính Map null | `Map<K,@NotNull V>` |
| Gắn `@NotBlank` vào toàn Map | Constraint không hỗ trợ kiểu Map | `@NotBlank` tại key/value `String` |
| Dùng `Map<String,@Valid V>` và tưởng value null bị cấm | `@Valid` bỏ qua null | Thêm `@NotNull` vào V |
| Quên `@Valid` trên value bean | Constraint trong bean value không được cascade | `Map<K,@Valid V>` |
| Chỉ dùng `@Valid` trên Map và tưởng key bean được cascade | Cơ chế truyền thống chủ yếu đi vào values | `Map<@Valid Key,@Valid Value>` khi cần cả hai |
| Gắn `@Valid` cả trên Map và value type | Có thể kiểm tra phần tử lặp hoặc khó hiểu | Đặt `@Valid` tại type argument cần cascade |
| Dùng `Map.of(key, null)` để test validation | Java ném `NullPointerException` trước validator | Dùng `LinkedHashMap` khi cần dữ liệu chứa null |
| Value List có ít nhất một phần tử nhưng phần tử rỗng | `@NotEmpty List` không bắt phần tử rỗng | `List<@NotBlank String>` |
| Bỏ `@NotEmpty` trên Map vì đã kiểm tra keys | Map rỗng không tạo key violation | Thêm `@NotEmpty` trên container |
| Dựa vào `Map` để bắt duplicate key trên JSON | Duplicate có thể bị ghi đè khi parse | Cấu hình JSON duplicate detection |
| Test so sánh chính xác `Path.toString()` trên mọi provider | Dễ phụ thuộc biểu diễn path | Dùng `Path.Node` và business error schema |
| Thiếu Jakarta Validation provider hoặc trigger Spring | Annotation không chạy như mong đợi | Có starter/provider và `@Valid`/`@Validated` đúng chỗ |
| Đặt constraint trên type argument của custom container mà không có extractor | Lỗi metadata/`ConstraintDeclarationException` | Định nghĩa/đăng ký `ValueExtractor` phù hợp |
| Tưởng validation thay thế toàn bộ nghiệp vụ/database | Quy tắc chéo entry hoặc dữ liệu ngoài boundary vẫn có thể sai | Kiểm tra thêm ở service/domain/database |

## 11. Checklist trước khi triển khai

**Mô hình dữ liệu**

- [ ] Map có được phép `null` không? Map rỗng có được chấp nhận không?
- [ ] Mỗi key có cần khác null/không blank/hợp format không?
- [ ] Mỗi value có cần khác null hoặc thỏa một constraint số/chuỗi không?
- [ ] Nếu value là bean, đã đặt `@Valid` trên type argument V?
- [ ] Nếu key là bean, có cần `@Valid` trên type argument K?
- [ ] Nếu V là `List`/`Map` lồng nhau, đã đánh dấu đúng từng cấp?
- [ ] Có quy tắc chéo key/value hoặc giữa nhiều entry cần custom constraint?

**Spring và dữ liệu đầu vào**

- [ ] Có Bean Validation provider tương thích namespace Jakarta và trigger `@Valid`/`@Validated` phù hợp?
- [ ] Có phân biệt lỗi Jackson deserialization với lỗi Bean Validation?
- [ ] Đã kiểm thử JSON Map key thông thường, key blank, value null, bean value invalid?
- [ ] Nếu nghiệp vụ cấm duplicate JSON field, parser đã được cấu hình kiểm tra?
- [ ] Error response có đủ thông tin xác định key/value nhưng không tiết lộ dữ liệu nhạy cảm?

**Kiểm thử**

- [ ] Đã thử Map null, Map rỗng, key không hợp lệ, value null, bean con sai, Map hợp lệ?
- [ ] Đã thử value là collection rỗng và collection có phần tử không hợp lệ?
- [ ] Test không dựa vào thứ tự iteration của Map/Set hoặc message localization?
- [ ] Nếu dùng validation groups, đã test nhóm thực sự được chọn ở boundary?

**Kết luận:** Ràng buộc Map có hai kiểu phạm vi hoàn toàn khác: `@NotEmpty Map<K,V>` kiểm tra **chính container**, còn `Map<@... K,@... V>` kiểm tra **từng khóa/từng giá trị**. `@Valid` đặt ở đúng type argument đưa validation đi sâu vào object con. Phối hợp những tầng này một cách rõ ràng giúp phát hiện đúng dữ liệu sai trong DTO lồng nhau của Spring mà không nhầm lẫn giữa container, entry và bean bên trong.

### Tài liệu tham khảo chính thức

- [Jakarta Bean Validation 3.0 — Section 4, Value Extractor Definition; Section 5.5, Container Element Constraints](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Jakarta Bean Validation 3.0 — `@NotEmpty`](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/NotEmpty.html)
- [Jakarta Bean Validation 3.0 — `@NotNull`](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/NotNull.html)
- [Hibernate Validator 8 — Reference Guide, Container Element Constraints and Cascaded Validation](https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/)
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
