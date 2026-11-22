# Ghép chuỗi bằng `joining` với dấu phân cách, tiền tố và hậu tố

> **Chương:** Collector nhiều tầng và tổng hợp  
> **Module:** `JAVA_STREAM_API` — học xử lý dữ liệu khai báo bằng Java Stream API qua pipeline lazy, `filter`, `map`, `reduce` và `collect`; thực hành grouping, collector tùy chỉnh, `Spliterator`, xử lý song song và Stream Gatherers, đồng thời nhận diện giới hạn về trạng thái, tài nguyên và hiệu năng.

Trong các ứng dụng quản lý đơn hàng, báo cáo hoặc hiển thị giao diện, chúng ta thường cần biến một tập phần tử thành **một chuỗi duy nhất**: danh sách mã sản phẩm ngăn bởi dấu phẩy, nhãn đặt trong dấu ngoặc vuông, hoặc tên sản phẩm được ghép theo từng danh mục. Nếu tự nối chuỗi trong vòng lặp, người viết phải xử lý phần tử đầu, phần tử cuối, dấu phân cách và trường hợp danh sách rỗng. Java Stream API cung cấp `Collectors.joining` để diễn đạt những quy tắc này trực tiếp.

Sau bài học, bạn có thể:

- Sử dụng đúng ba overload `joining()`, `joining(delimiter)`, `joining(delimiter, prefix, suffix)`.
- Kết hợp `map`, `filter`, `distinct`, `sorted` với `joining`, và phân biệt kết quả trên Stream rỗng.
- Ghép dữ liệu **theo nhóm** bằng `groupingBy`, `mapping`, `filtering` và các downstream collector.
- Hiểu giới hạn của việc ghép chuỗi khi dữ liệu có `null`, chứa ký tự phân cách, nguồn vô hạn hoặc cần giữ thứ tự trong xử lý song song.

## 1. `Collectors.joining` là gì?

`Collectors.joining` là một **collector** nhận các phần tử kiểu `CharSequence` (ví dụ `String`) và tạo ra một `String`. Nó chỉ mô tả cách tích lũy dữ liệu; quá trình duyệt Stream xảy ra khi gọi phép toán kết thúc `collect`.

```java
import java.util.List;
import java.util.stream.Collectors;

List<String> languages = List.of("Java", "Kotlin", "Scala");

String result = languages.stream()
        .collect(Collectors.joining(", "));

System.out.println(result); // Java, Kotlin, Scala
```

Sơ đồ xử lý:

```text
List<String>
   │
   ▼
 stream()
   │
   ├── "Java"
   ├── "Kotlin"
   └── "Scala"
   │
   ▼
 collect(Collectors.joining(", "))
   │
   ▼
 "Java, Kotlin, Scala"
```

Trong ví dụ, `", "` là **dấu phân cách** (*delimiter*). Collector đặt dấu phân cách **giữa** hai phần tử liền kề, không tự thêm dấu này ở đầu hoặc cuối.

**Điểm cần nhớ:** `joining` khác với `map`. `map` chuyển đổi từng phần tử nhưng vẫn tạo Stream; `collect(joining(...))` **kết thúc** pipeline và gom tất cả phần tử thành một chuỗi.

## 2. Ba overload của `Collectors.joining`

Java cung cấp ba phương thức với cấu trúc khái quát như sau:

```java
// Không chèn dấu phân cách.
Collectors.joining()

// Chèn delimiter giữa các phần tử.
Collectors.joining(CharSequence delimiter)

// Thêm prefix trước toàn bộ kết quả và suffix sau toàn bộ kết quả.
Collectors.joining(
        CharSequence delimiter,
        CharSequence prefix,
        CharSequence suffix
)
```

Chúng trả một `Collector<CharSequence, ?, String>`. `prefix` và `suffix` **bao quanh toàn bộ chuỗi đã ghép**, không được lặp lại trước và sau từng phần tử.

| Phép gọi | Stream gồm `"A", "B", "C"` | Ý nghĩa |
| --- | --- | --- |
| `joining()` | `ABC` | Ghép liền các chuỗi. |
| `joining(", ")` | `A, B, C` | Thêm dấu phẩy và khoảng trắng giữa các phần tử. |
| `joining(" / ", "[", "]")` | `[A / B / C]` | Dấu phân cách, tiền tố và hậu tố. |
| `joining("\n", "", "")` | Mỗi giá trị trên một dòng | Ký tự xuống dòng là delimiter. |

### 2.1. Ghép liền với `joining()`

```java
String code = List.of("VN", "-", "2026", "-", "001").stream()
        .collect(Collectors.joining());

System.out.println(code); // VN-2026-001
```

Không có delimiter không có nghĩa là các phần tử phải cùng độ dài; collector chỉ nối nội dung theo thứ tự phần tử mà pipeline cung cấp.

### 2.2. Chọn dấu phân cách bằng `joining(delimiter)`

```java
List<String> tags = List.of("stream", "collector", "java");

String csvLike = tags.stream()
        .collect(Collectors.joining(","));
// stream,collector,java

String pathPart = tags.stream()
        .collect(Collectors.joining("/"));
// stream/collector/java
```

Ví dụ trên chỉ tạo chuỗi có dấu phân cách; nó **chưa phải** cách mã hóa CSV hay đường dẫn URL an toàn. Nếu dữ liệu chứa dấu phẩy, dấu gạch hoặc ký tự đặc biệt, ứng dụng phải tự áp dụng quy tắc escaping/encoding theo định dạng đích.

### 2.3. Bao toàn bộ kết quả bằng tiền tố và hậu tố

```java
String display = List.of("Java", "SQL", "Docker").stream()
        .collect(Collectors.joining(" | ", "Kỹ năng: [", "]"));

System.out.println(display);
// Kỹ năng: [Java | SQL | Docker]
```

Ở đây:

- `delimiter = " | "`: nằm **giữa** các giá trị.
- `prefix = "Kỹ năng: ["`: đặt **một lần ở đầu**.
- `suffix = "]"`: đặt **một lần ở cuối**.

Không cần tự kiểm tra phần tử đầu và phần tử cuối để quyết định có thêm dấu `|` hay không.

## 3. Ví dụ hoàn chỉnh: tạo mô tả đơn hàng và ghép theo danh mục

Chương trình Java 17+ dưới đây dùng cùng một nguồn để minh họa `filter`, `map`, `distinct`, `sorted`, `joining`, cũng như composition với `groupingBy` và `mapping`.

Lưu vào tệp `JoiningCollectorsDemo.java`:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class JoiningCollectorsDemo {
    record Item(
            String sku,
            String category,
            String name,
            int quantity,
            boolean active
    ) {}

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("BK-01", "BOOK", "Java Stream", 2, true),
                new Item("PN-01", "PEN", "Bút xanh", 4, true),
                new Item("BK-02", "BOOK", "Java Core", 1, true),
                new Item("BK-01", "BOOK", "Java Stream", 3, true),
                new Item("BG-01", "BAG", "Túi vải", 1, false)
        );

        // Ghép các tên đang bán, không lặp và sắp xếp theo tên.
        String uniqueNames = items.stream()
                .filter(Item::active)
                .map(Item::name)
                .distinct()
                .sorted()
                .collect(Collectors.joining(" | ", "[", "]"));

        // Ghép mã kèm số lượng: mỗi Item trở thành một chuỗi.
        String orderLines = items.stream()
                .filter(Item::active)
                .map(item -> item.sku() + " x" + item.quantity())
                .collect(Collectors.joining("; ", "Giỏ hàng: ", "."));

        // Với mỗi danh mục, nối tất cả tên sản phẩm đang bán.
        // TreeMap sắp xếp các khóa BOOK, PEN.
        Map<String, String> namesByCategory = items.stream()
                .filter(Item::active)
                .collect(Collectors.groupingBy(
                        Item::category,
                        TreeMap::new,
                        Collectors.mapping(
                                Item::name,
                                Collectors.joining(" / ", "<", ">")
                        )
                ));

        // Bộ lọc không giữ lại phần tử nào.
        String empty = items.stream()
                .filter(item -> item.quantity() > 100)
                .map(Item::name)
                .collect(Collectors.joining(", ", "[", "]"));

        System.out.println("Tên: " + uniqueNames);
        System.out.println(orderLines);
        System.out.println("Theo danh mục: " + namesByCategory);
        System.out.println("Không có: " + empty);
    }
}
```

Kết quả:

```text
Tên: [Bút xanh | Java Core | Java Stream]
Giỏ hàng: BK-01 x2; PN-01 x4; BK-02 x1; BK-01 x3.
Theo danh mục: {BOOK=<Java Stream / Java Core / Java Stream>, PEN=<Bút xanh>}
Không có: []
```

Phân tích những điểm quan trọng:

1. `filter(Item::active)` giới hạn tập đầu vào **trước** khi nối chuỗi.
2. `map(Item::name)` tạo `Stream<String>`, phù hợp với `Collectors.joining`. Nếu giữ `Stream<Item>` mà đưa thẳng vào `joining` sẽ không phù hợp kiểu đầu vào.
3. `distinct()` loại tên lặp; `sorted()` sắp xếp trước khi `joining`, nên kết quả có thứ tự xác định theo thứ tự tự nhiên của `String`.
4. `map(item -> item.sku() + " x" + item.quantity())` tạo **mỗi dòng biểu diễn bằng một chuỗi**, rồi `joining` thêm `"; "` giữa các dòng.
5. `groupingBy` phân nhóm theo danh mục; `mapping(Item::name, joining(...))` tiếp tục biến từng nhóm thành **một chuỗi**. `TreeMap::new` chỉ sắp xếp **khóa danh mục**, không tự sắp xếp tên nằm trong từng nhóm.
6. Khi kết quả sau `filter` rỗng, dạng ba đối số vẫn trả `"[]"` vì tiền tố và hậu tố vẫn được áp dụng.

## 4. Stream rỗng: dấu phân cách, tiền tố và hậu tố có xuất hiện không?

Đây là điểm thường gây nhầm lẫn. Hãy so sánh:

```java
import java.util.stream.Collectors;
import java.util.stream.Stream;

String a = Stream.<String>empty()
        .collect(Collectors.joining());
String b = Stream.<String>empty()
        .collect(Collectors.joining(", "));
String c = Stream.<String>empty()
        .collect(Collectors.joining(", ", "[", "]"));
String d = Stream.<String>empty()
        .collect(Collectors.joining(", ", "Danh sách: ", "."));

System.out.println(a.isEmpty()); // true
System.out.println(b.isEmpty()); // true
System.out.println(c);         // []
System.out.println(d);         // Danh sách: .
```

| Dạng collector | Kết quả khi Stream rỗng |
| --- | --- |
| `joining()` | Chuỗi rỗng `""` |
| `joining(", ")` | Chuỗi rỗng `""` |
| `joining(", ", "[", "]")` | `"[]"` |
| `joining(";", "(", ")")` | `"()"` |

**Không có phần tử nào** nghĩa là không có dấu phân cách cần chèn. Tuy nhiên, `prefix` và `suffix` là quy tắc định dạng **toàn bộ kết quả**, nên chúng vẫn xuất hiện.

### Khi muốn hiển thị thông báo thay vì `[]`

Nếu đang có một `List` đầu vào được sử dụng trực tiếp và chưa lọc, có thể kiểm tra `isEmpty()` trước khi gọi Stream. Nhưng nếu pipeline có `filter`, danh sách nguồn không rỗng **không bảo đảm** có phần tử sau lọc.

Trên Java 12+, có thể dùng `Collectors.teeing` để tính **số phần tử** và **chuỗi đã nối** trong cùng một lần duyệt, rồi quyết định đầu ra:

```java
String message = List.of("Java", "Kotlin").stream()
        .filter(word -> word.startsWith("Z"))
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.joining(", ", "[", "]"),
                (count, joined) -> count == 0
                        ? "(không có kết quả)"
                        : joined
        ));

System.out.println(message); // (không có kết quả)
```

Không nên chỉ kiểm tra `joined.equals("[]")` để suy ra nguồn rỗng: một phần tử là chuỗi rỗng `""` cũng có thể tạo kết quả `"[]"` khi dùng tiền tố `"["` và hậu tố `"]"`. Số phần tử phản ánh tình trạng rỗng chính xác hơn nội dung chuỗi kết quả.

## 5. Cần chuyển dữ liệu không phải `String` trước khi `joining`

`Collectors.joining` làm việc với `CharSequence` — không tự biết cách trình bày một `Product`, `Order`, `Integer` hoặc `BigDecimal` theo yêu cầu nghiệp vụ. Vì vậy, hãy chuyển phần tử thành chuỗi **trước** bước collect.

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.stream.Collectors;

record PriceTag(String sku, BigDecimal price) {}

List<PriceTag> prices = List.of(
        new PriceTag("BK-01", new BigDecimal("120.00")),
        new PriceTag("PN-01", new BigDecimal("30.50"))
);

String labels = prices.stream()
        .map(p -> p.sku() + "=" + p.price().toPlainString())
        .collect(Collectors.joining("; ", "{", "}"));

System.out.println(labels);
// {BK-01=120.00; PN-01=30.50}
```

`toPlainString()` giúp trình bày `BigDecimal` ở dạng thập phân không dùng ký pháp số mũ. Đây vẫn chỉ là định dạng chuỗi; nếu báo cáo tiền cần dấu phân nhóm, đơn vị tiền tệ hoặc quy tắc vùng miền thì nên dùng formatter với `Locale` thích hợp **trước** khi joining.

Với một primitive stream như `IntStream`, hãy dùng `mapToObj`:

```java
String numbers = java.util.stream.IntStream.of(3, 5, 8)
        .mapToObj(Integer::toString)
        .collect(Collectors.joining(" + ", "(", ")"));

System.out.println(numbers); // (3 + 5 + 8)
```

Ngược lại, `IntStream.sum()` là lựa chọn đúng nếu bài toán cần **kết quả số 16**, chứ không phải chuỗi biểu thức `"(3 + 5 + 8)"`.

## 6. Kết hợp `joining` với các thao tác trung gian

`joining` thường nằm ở cuối pipeline sau khi đã chọn lọc và chuẩn hóa dữ liệu:

```java
String tags = List.of(" java ", "stream", "JAVA", "", "collector")
        .stream()
        .map(String::trim)
        .filter(s -> !s.isBlank())
        .map(s -> s.toLowerCase(java.util.Locale.ROOT))
        .distinct()
        .sorted()
        .collect(Collectors.joining(", ", "#", ""));

System.out.println(tags); // #collector, java, stream
```

Ý nghĩa từng bước:

| Bước | Vai trò trước khi ghép |
| --- | --- |
| `map(String::trim)` | Loại khoảng trắng ở hai đầu từng nhãn. |
| `filter(s -> !s.isBlank())` | Loại nhãn rỗng hoặc chỉ có khoảng trắng. |
| `map(...toLowerCase(Locale.ROOT))` | Chuẩn hóa chữ hoa/thường theo quy tắc không phụ thuộc locale mặc định. |
| `distinct()` | Loại nhãn trùng sau chuẩn hóa. |
| `sorted()` | Xác định thứ tự xuất hiện trong chuỗi kết quả. |
| `joining(", ", "#", "")` | Nối bằng dấu phẩy, thêm tiền tố `#` cho **toàn bộ** chuỗi. |

**Điểm dễ nhầm:** `joining(", ", "#", "")` không biến từng nhãn thành hashtag. Nếu cần `#java, #stream`, hãy viết `map(s -> "#" + s)` **trước** `joining(", ")`.

```java
String hashtags = List.of("java", "stream").stream()
        .map(s -> "#" + s)
        .collect(Collectors.joining(", "));

System.out.println(hashtags); // #java, #stream
```

Sự phân biệt này rất quan trọng giữa **định dạng từng phần tử** (`map`) và **định dạng cả tập kết quả** (`joining` có prefix/suffix).

## 7. Ghép chuỗi theo nhóm với `groupingBy` và `mapping`

Khi yêu cầu không còn là một chuỗi duy nhất mà là **một chuỗi cho mỗi nhóm**, ta có thể dùng collector nhiều tầng:

```java
Collectors.groupingBy(
        classifier,
        Collectors.mapping(valueMapper, Collectors.joining(delimiter))
)
```

Đầu ra có dạng `Map<K, String>`:

```text
Stream<Item>
     │
     ▼
 groupingBy(Item::category)
     │
     ├── BOOK ──► mapping(Item::name) ──► joining(", ") ──► "Java Stream, Java Core"
     └── PEN  ──► mapping(Item::name) ──► joining(", ") ──► "Bút xanh"
     │
     ▼
 Map<String, String>
```

Ví dụ khi có `items` và `Item` như chương trình ở mục 3:

```java
Map<String, String> descriptions = items.stream()
        .filter(Item::active)
        .collect(Collectors.groupingBy(
                Item::category,
                TreeMap::new,
                Collectors.mapping(
                        Item::name,
                        Collectors.joining(", ", "[", "]")
                )
        ));

System.out.println(descriptions);
// {BOOK=[Java Stream, Java Core, Java Stream], PEN=[Bút xanh]}
```

Trong ví dụ này, nếu viết `.map(Item::name)` **trước** `groupingBy(Item::category)` thì đã mất thông tin `category` và không thể phân nhóm theo thuộc tính đó nữa. `Collectors.mapping` cho phép **giữ `Item` ở bước phân nhóm**, rồi mới chuyển từng phần tử trong mỗi nhóm thành `String` để nối.

### `Collectors.filtering` nằm trước hay sau `groupingBy`?

Từ Java 9, `Collectors.filtering` dùng như downstream collector để lọc **bên trong từng nhóm**:

```java
Map<String, String> allCategories = items.stream()
        .collect(Collectors.groupingBy(
                Item::category,
                TreeMap::new,
                Collectors.filtering(
                        Item::active,
                        Collectors.mapping(
                                Item::name,
                                Collectors.joining(", ", "[", "]")
                        )
                )
        ));

System.out.println(allCategories);
// {BAG=[], BOOK=[Java Stream, Java Core, Java Stream], PEN=[Bút xanh]}
```

Ở đây, nhóm `BAG` **vẫn tồn tại** vì có một `Item` thuộc nhóm `BAG`, nhưng downstream `filtering` loại phần tử đó, nên `joining` trong nhóm rỗng trả `[]`.

Ngược lại, khi viết `items.stream().filter(Item::active).collect(groupingBy(...))`, phần tử `BAG` bị loại **trước khi phân nhóm**, vì vậy khóa `BAG` không xuất hiện. Đây là khác biệt ngữ nghĩa đáng chú ý khi cần báo cáo cả các nhóm không có phần tử đạt điều kiện.

## 8. `collectingAndThen`: xử lý kết quả đã ghép

`Collectors.collectingAndThen(downstream, finisher)` cho phép áp dụng **một phép biến đổi cuối cùng** sau khi downstream collector đã hoàn thành.

Ví dụ, chuẩn hóa khoảng trắng của toàn bộ kết quả:

```java
String summary = List.of("Java", "Stream").stream()
        .collect(Collectors.collectingAndThen(
                Collectors.joining(", ", "Danh sách: ", "  "),
                String::strip
        ));

System.out.println(summary); // Danh sách: Java, Stream
```

Lưu ý `collectingAndThen` không cần thiết nếu chỉ muốn thêm prefix/suffix; ba đối số của `joining` đã xử lý việc đó. Hãy dùng `collectingAndThen` khi cần **hậu xử lý riêng** như gói kết quả vào một đối tượng khác, chuẩn hóa định dạng chung hoặc áp dụng một quy tắc không có sẵn trong `joining`.

Nếu chỉ muốn đặt văn bản khác khi không có phần tử, nên sử dụng `teeing` với `counting` như mục 4, hoặc có sẵn thông tin số phần tử trước khi thu thập. Nội dung chuỗi sau khi ghép không phải lúc nào cũng đủ để suy ra số phần tử.

## 9. `null`, ký tự phân cách và an toàn dữ liệu

### `null` trong Stream

Nếu nguồn có phần tử `null`, implementation dựa trên `StringBuilder`/`StringJoiner` có thể biểu diễn nó bằng chuỗi chữ **`"null"`** trong kết quả thay vì loại phần tử. Tốt hơn là định nghĩa rõ chính sách hiển thị.

```java
import java.util.Arrays;
import java.util.Objects;
import java.util.stream.Collectors;

List<String> names = Arrays.asList("An", null, "Bình");

String withoutNull = names.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.joining(" | "));
// An | Bình

String withPlaceholder = names.stream()
        .map(name -> name == null ? "(chưa có tên)" : name)
        .collect(Collectors.joining(" | "));
// An | (chưa có tên) | Bình
```

`List.of(...)` không cho phép phần tử `null`; vì vậy ví dụ trên dùng `Arrays.asList(...)`. Nếu mapper gọi `item.name()` trên một **đối tượng item null**, lỗi có thể xuất hiện **trước khi** joining; cần lọc `Objects::nonNull` ở đúng vị trí.

### `joining` không tự escape nội dung

Giả sử dữ liệu có tên `"Java, nâng cao"`:

```java
String output = List.of("Java, nâng cao", "Stream").stream()
        .collect(Collectors.joining(", "));

System.out.println(output); // Java, nâng cao, Stream
```

Từ chuỗi kết quả không thể biết dấu phẩy thứ nhất là **nội dung tên**, còn dấu phẩy thứ hai là **dấu phân cách**. Vì vậy:

- Không dùng `joining(",")` như một trình ghi CSV hoàn chỉnh khi giá trị có thể chứa dấu phẩy, dấu nháy hoặc xuống dòng; phải áp dụng quy tắc quoting/escaping của CSV.
- Không tạo JSON hoặc câu lệnh SQL bằng nối chuỗi thủ công rồi coi chúng là an toàn. Hãy dùng thư viện serialize JSON hoặc tham số hóa SQL.
- Với dữ liệu dùng trong HTML/URL, áp dụng escaping/encoding theo **ngữ cảnh đích** thay vì kỳ vọng `joining` xử lý giúp.

Ba tham số `delimiter`, `prefix`, `suffix` là **quy tắc trình bày**, không phải cơ chế xác thực hay làm sạch dữ liệu.

## 10. Thứ tự phần tử và Stream song song

`joining` phụ thuộc vào thứ tự khi chuỗi kết quả phải đọc theo trình tự. Trên nguồn có encounter order như `List`, pipeline tuần tự giữ thứ tự đó nếu không có bước làm thay đổi hoặc bỏ bảo đảm thứ tự:

```java
String ordered = List.of("C", "A", "B").stream()
        .collect(Collectors.joining("-"));
// C-A-B

String sorted = List.of("C", "A", "B").stream()
        .sorted()
        .collect(Collectors.joining("-"));
// A-B-C
```

Không nên suy rằng `Collectors.joining` sẽ tự sắp xếp phần tử. Nếu nguồn là tập không có encounter order (ví dụ một số trường hợp dùng `HashSet`), kết quả không có một thứ tự nghiệp vụ được bảo đảm; thêm `sorted` khi cần đầu ra ổn định.

### Khi dùng `parallelStream()`

```java
String joined = List.of("Java", "Kotlin", "Scala")
        .parallelStream()
        .collect(Collectors.joining(" | "));

System.out.println(joined); // Java | Kotlin | Scala
```

`Collectors.joining` có thể được sử dụng trên parallel stream. Với một nguồn có thứ tự như `List` và pipeline không bỏ encounter order, kết quả phải tuân theo thứ tự đó. Việc tích lũy có thể diễn ra ở nhiều vùng trung gian rồi được gộp lại theo hợp đồng collector.

Tuy nhiên, song song **không mặc nhiên nhanh hơn**: chia dữ liệu, tạo các chuỗi trung gian và hợp nhất có chi phí. Với các tập nhỏ hoặc kết quả chuỗi cần giữ thứ tự, xử lý tuần tự thường dễ hiểu và có thể hiệu quả hơn. Nếu một bước như `unordered()` cho phép bỏ encounter order, không được dựa vào thứ tự ghép để xác định kết quả.

## 11. Bộ nhớ, độ dài kết quả và lựa chọn công cụ

Với `n` chuỗi đầu vào, `joining` phải đọc các phần tử để có kết quả cuối cùng; kết quả chứa toàn bộ nội dung đã nối và các ký tự phân cách, tiền tố, hậu tố. **Bộ nhớ tối thiểu cho chuỗi kết quả tăng theo tổng số ký tự**, không thể coi là `O(1)` bất kể dữ liệu lớn đến đâu.

Nếu danh sách dài hàng triệu phần tử, tạo một chuỗi duy nhất có thể tốn nhiều bộ nhớ, thậm chí chạm giới hạn kích thước mảng/chuỗi của JVM. Có thể cân nhắc phân trang, ghi theo lô hoặc streaming ra `Writer` khi yêu cầu không bắt buộc vật hóa cả chuỗi trong RAM.

`joining` cũng cần nguồn hữu hạn để hoàn tất:

```java
String firstFive = java.util.stream.Stream
        .iterate(1, n -> n + 1)
        .limit(5)
        .map(String::valueOf)
        .collect(Collectors.joining(", "));

System.out.println(firstFive); // 1, 2, 3, 4, 5
```

Một Stream vô hạn mà không giới hạn số phần tử sẽ không hoàn tất `collect(joining(...))`. Với các Stream gắn tài nguyên I/O, cần đóng tài nguyên đúng cách; gọi `collect` không thay thế `try-with-resources`.

### So với `String.join`, `StringJoiner` và `reduce`

| Cách làm | Phù hợp khi | Lưu ý |
| --- | --- | --- |
| `Collectors.joining(...)` | Đã có pipeline Stream, đặc biệt khi ghép sau `filter`/`map` hoặc làm downstream collector. | Là terminal reduction; phải có dữ liệu kiểu `CharSequence`. |
| `String.join(delimiter, elements)` | Đã có sẵn `Iterable<? extends CharSequence>` hoặc các tham số `CharSequence`; không cần pipeline. | Không có overload riêng cho prefix/suffix. |
| `StringJoiner` | Tích lũy từng chuỗi thủ công với delimiter/prefix/suffix. | Phải tự gọi `add` cho từng phần tử; `joining` sử dụng cơ chế tích lũy tương tự bên trong. |
| `reduce` với phép cộng chuỗi | Thích hợp để học reduction đơn giản. | Nối chuỗi bất biến lặp đi lặp lại có thể tạo nhiều đối tượng trung gian, không phải lựa chọn ưu tiên cho bài toán ghép nhiều chuỗi. |

Ví dụ không cần Stream:

```java
String direct = String.join(", ", List.of("A", "B", "C"));
// A, B, C

java.util.StringJoiner joiner =
        new java.util.StringJoiner(", ", "[", "]");
joiner.add("A");
joiner.add("B");
System.out.println(joiner); // [A, B]
```

Khi đã có Stream với nhiều bước biến đổi, `collect(Collectors.joining(...))` thường tự nhiên hơn việc đưa các phần tử ra ngoài pipeline rồi dùng vòng lặp ghép thủ công.

## 12. Lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Gọi `joining` trực tiếp trên `Stream<Item>` | Không phù hợp kiểu `CharSequence`; có thể không biên dịch. | `map(Item::name)` hoặc định dạng từng `Item` thành chuỗi trước. |
| Nghĩ prefix/suffix lặp lại trên từng phần tử | Đầu ra không đúng định dạng mong muốn. | Dùng `map` để tạo tiền tố/hậu tố cho mỗi phần tử; dùng `joining(..., prefix, suffix)` cho cả kết quả. |
| Mong chuỗi rỗng trên Stream rỗng khi có prefix/suffix | Thực tế vẫn thu được `prefix + suffix`. | Chọn quy tắc hiển thị và kiểm tra count nếu cần phân biệt. |
| Dùng `joining(",")` để ghi CSV thực sự | Dữ liệu có dấu phẩy/dấu nháy không được escape. | Dùng bộ mã hóa CSV hoặc quy tắc escaping phù hợp. |
| Không loại hoặc thay thế `null` có chủ đích | Chuỗi kết quả có thể chứa chữ `null` ngoài ý muốn. | `filter(Objects::nonNull)` hoặc `map` sang placeholder. |
| Nhầm `groupingBy` và `mapping` | Mất khóa phân nhóm khi `map` quá sớm. | Phân nhóm trên đối tượng, sau đó `mapping` bên trong downstream collector. |
| Đòi hỏi thứ tự xác định từ nguồn unordered | Chuỗi nối có thứ tự khó dự đoán. | Dùng nguồn có encounter order hoặc `sorted()` trước collect. |
| Coi `parallelStream()` luôn tăng tốc | Chi phí chia/gộp lớn hơn lợi ích. | Đo hiệu năng; ưu tiên tuần tự nếu dữ liệu nhỏ. |
| Ghép dữ liệu vô hạn hoặc quá lớn vào một chuỗi | Không kết thúc hoặc tiêu thụ bộ nhớ cao. | Dùng `limit`, xử lý theo lô hoặc xuất tuần tự ra đích. |
| Dùng lại cùng Stream sau `collect` | Stream đã bị tiêu thụ, có thể ném `IllegalStateException`. | Tạo Stream mới từ nguồn có thể duyệt lại. |

## 13. Tự luyện tập

**Bài 1 — Ba overload.** Cho `List.of("x", "y", "z")`. Hãy dự đoán ba kết quả sau:

```java
List<String> values = List.of("x", "y", "z");

String a = values.stream().collect(Collectors.joining());
String b = values.stream().collect(Collectors.joining("-"));
String c = values.stream().collect(Collectors.joining("-", "<", ">"));
```

**Đáp án:** `a = "xyz"`, `b = "x-y-z"`, `c = "<x-y-z>"`.

**Bài 2 — Nguồn rỗng.** Giá trị của `Stream.<String>empty().collect(Collectors.joining("; ", "(", ")"))` là gì?

**Đáp án:** `"()"`. Không có delimiter nào được chèn vì không có phần tử, nhưng prefix và suffix vẫn được giữ.

**Bài 3 — Tiền tố cho từng phần tử.** Cần biến `["java", "stream"]` thành `"#java, #stream"`. Có nên dùng `joining(", ", "#", "")` không?

**Đáp án:** Không. Dùng `.map(s -> "#" + s).collect(Collectors.joining(", "))`; prefix của `joining` chỉ thêm một lần ở đầu toàn bộ chuỗi.

**Bài 4 — Ghép theo nhóm.** Với `Stream<Item>`, làm thế nào tạo `Map<String, String>` theo `category`, mỗi giá trị là tên các `Item` cách nhau dấu `"; "`?

```java
Map<String, String> result = items.stream()
        .collect(Collectors.groupingBy(
                Item::category,
                Collectors.mapping(Item::name, Collectors.joining("; "))
        ));
```

**Bài 5 — Filter ở hai vị trí.** Vì sao `items.stream().filter(Item::active).collect(groupingBy(...))` có thể tạo ít khóa hơn `items.stream().collect(groupingBy(..., filtering(Item::active, ...)))`?

**Đáp án:** Lọc **trước** grouping loại cả phần tử tạo nhóm; nhóm không có phần tử đạt điều kiện có thể biến mất. Lọc **bên trong downstream** vẫn tạo nhóm cho các khóa có phần tử đầu vào, nhưng kết quả joined của nhóm không có phần tử đạt điều kiện có thể là chuỗi rỗng hoặc chỉ prefix/suffix.

**Bài 6 — Thứ tự.** Nếu cần cùng một chuỗi kết quả bất kể thứ tự ban đầu của danh sách, nên thêm bước nào?

**Đáp án:** Sắp xếp theo comparator xác định bằng `sorted()` hoặc `sorted(comparator)` **trước** `joining`. Nếu có nhiều bản ghi có giá trị so sánh bằng nhau mà thứ tự giữa chúng quan trọng, cần thêm tiêu chí phụ rõ ràng.

## Ghi nhớ

- `Collectors.joining()` nối liền các `CharSequence`; `joining(delimiter)` chèn dấu phân cách **giữa** các phần tử; `joining(delimiter, prefix, suffix)` thêm tiền tố/hậu tố **một lần cho toàn bộ kết quả**.
- Với Stream rỗng, hai dạng đầu trả `""`; dạng có prefix/suffix trả `prefix + suffix` (chẳng hạn `"[]"`).
- Khi nguồn không phải `CharSequence`, hãy `map` hoặc `mapToObj` sang chuỗi trước; `joining` không tự định dạng đối tượng theo nghiệp vụ.
- Có thể kết hợp `groupingBy(..., mapping(..., joining(...)))` để tạo một chuỗi cho mỗi nhóm; `filtering` ở downstream khác với `filter` trước grouping về việc giữ nhóm rỗng.
- `joining` không tự escape dữ liệu cho CSV/JSON/HTML, không tự sắp xếp, và cần xét bộ nhớ, thứ tự, tài nguyên cùng giới hạn khi dùng Stream vô hạn hoặc song song.
