# Thu thập theo thứ tự sắp xếp bằng TreeSet

Một ứng dụng thường cần thu thập dữ liệu thành tập hợp **vừa không trùng lặp, vừa có thứ tự xác định**: danh sách mã sản phẩm theo thứ tự chữ cái, các mốc giá tăng dần, hoặc bảng xếp hạng theo nhiều tiêu chí. Trong **Java Stream API**, cách diễn đạt rõ ràng cho nhu cầu này là dùng `collect(Collectors.toCollection(TreeSet::new))`.

`TreeSet` là một `NavigableSet` dựa trên cấu trúc cây có thứ tự. Khi thu thập các phần tử vào `TreeSet`, Java sử dụng **thứ tự tự nhiên (`Comparable`)** hoặc một **`Comparator`** được cung cấp để sắp xếp các phần tử. Đặc biệt, cách so sánh này còn quyết định **phần tử nào được xem là trùng**.

Bài học thuộc chương **Thu thập thành Collection** của module **JAVA_STREAM_API**. Sau bài, bạn sẽ biết cách thu thập Stream vào `TreeSet`, tự định nghĩa thứ tự, phân biệt `TreeSet` với `sorted()`, `distinct()` và `Collectors.toSet()`, cũng như nhận diện các rủi ro về `Comparator`, `null`, dữ liệu thay đổi, parallel Stream, tài nguyên và hiệu năng. Kiến thức này là nền tảng khi làm việc với collector tùy chỉnh, grouping, `Spliterator` và Stream Gatherers.

## 1. Bài toán thực tế: cần vừa sắp xếp, vừa loại trùng

Giả sử một hệ thống nhận các mã công nghệ do người dùng lựa chọn:

~~~text
java, kotlin, java, go, stream, kotlin
~~~

Yêu cầu đầu ra là **mỗi mã chỉ xuất hiện một lần** và được **sắp xếp tăng dần**. Ta có thể viết:

~~~java
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class TreeSetOverview {
    public static void main(String[] args) {
        List<String> technologies = List.of(
            "java", "kotlin", "java", "go", "stream", "kotlin"
        );

        TreeSet<String> result = technologies.stream()
            .collect(Collectors.toCollection(TreeSet::new));

        System.out.println(result); // [go, java, kotlin, stream]
        System.out.println(technologies.size()); // 6: nguồn giữ nguyên
    }
}
~~~

Trong ví dụ này, `TreeSet` dùng thứ tự tự nhiên của `String` (`String.compareTo`). Hai chuỗi bằng nhau theo cách so sánh đó chỉ được giữ một lần. Danh sách nguồn có 6 phần tử nhưng `TreeSet` kết quả còn 4 phần tử và được duyệt theo thứ tự tăng dần.

`TreeSet` **không phụ thuộc vào thứ tự xuất hiện** của phần tử để sắp xếp. Nếu thêm `"api"` vào cuối nguồn, nó sẽ xuất hiện ở đầu tập kết quả.

> Ví dụ sử dụng `List.of` (Java 9+). Bản thân `TreeSet` và `Collectors.toCollection` có thể dùng từ Java 8; nếu cần Java 8, thay `List.of(...)` bằng `Arrays.asList(...)`.

## 2. TreeSet là kiểu Collection như thế nào?

`java.util.TreeSet<E>` triển khai `NavigableSet<E>`, đồng thời tuân theo hành vi sắp xếp của `SortedSet<E>`. Những tính chất quan trọng:

| Tính chất | Ý nghĩa khi dùng trong Stream |
|---|---|
| Không lưu phần tử trùng theo quy tắc so sánh | Khi `compare(a, b) == 0` hoặc `a.compareTo(b) == 0`, `TreeSet` xem `a` và `b` là cùng một phần tử |
| Các phần tử được sắp xếp | Duyệt tập theo comparator hoặc thứ tự tự nhiên |
| Truy cập phần tử theo khoảng và mốc | Hỗ trợ `first`, `last`, `lower`, `floor`, `ceiling`, `higher` và các tập con |
| Thay đổi được | Có thể gọi `add`, `remove`, `clear` trên `TreeSet` kết quả |
| Không tự đồng bộ | Không dùng cùng một `TreeSet` để cập nhật đồng thời từ nhiều thread nếu chưa có thiết kế đồng bộ phù hợp |
| Chi phí dựa trên cây cân bằng | Các thao tác cơ bản như `add`, `remove`, `contains` có chi phí thời gian bảo đảm ở mức logarit theo kích thước tập |

Một `TreeSet` mới tạo bằng `new TreeSet<>()` dùng **thứ tự tự nhiên**. Vì vậy các phần tử phải **so sánh được với nhau**, thường bằng cách triển khai `Comparable`. Nếu phần tử không có thứ tự tự nhiên phù hợp, hãy cung cấp `Comparator`.

~~~mermaid
flowchart LR
    A["Stream: 7, 3, 7, 5, 3"] --> B["collect(toCollection(TreeSet::new))"]
    B --> C["TreeSet: 3, 5, 7"]
    C --> D["Duyệt theo thứ tự tăng dần"]
~~~

Dòng dữ liệu vẫn tuân theo mô hình Stream: `stream()` tạo nguồn, `filter`/`map` là các bước trung gian lazy nếu có, và `collect(...)` là **terminal operation** tạo kết quả.

## 3. Cơ chế Collectors.toCollection(TreeSet::new)

`Collectors.toCollection` có dạng khái quát:

~~~java
static <T, C extends Collection<T>>
Collector<T, ?, C> toCollection(Supplier<C> collectionFactory)
~~~

Đối số `collectionFactory` là một `Supplier` tạo ra collection đích. Khi truyền `TreeSet::new`, ta yêu cầu collector tạo **`TreeSet` mới** và thêm các phần tử được xử lý vào đó.

~~~java
TreeSet<Integer> numbers = java.util.stream.Stream.of(5, 1, 2, 5, 3)
    .collect(java.util.stream.Collectors.toCollection(TreeSet::new));

System.out.println(numbers); // [1, 2, 3, 5]
~~~

Trong cách hiểu đơn giản khi chạy tuần tự:

1. Collector gọi supplier để có một `TreeSet` rỗng.
2. Mỗi phần tử từ Stream được thêm bằng `add`.
3. `TreeSet` dùng comparator hoặc thứ tự tự nhiên để tìm vị trí và phát hiện trùng.
4. `collect` trả về tập kết quả.

Với parallel Stream, collector có thể tạo nhiều bộ chứa, tích lũy riêng từng nhánh rồi hợp nhất. Không được giả định supplier chỉ được gọi đúng một lần hoặc các lời gọi diễn ra theo một thứ tự thread cố định.

### 3.1. Vì sao không chỉ dùng Collectors.toSet()?

~~~java
List<Integer> source = List.of(5, 2, 5, 1, 3);

java.util.Set<Integer> unspecified = source.stream()
    .collect(java.util.stream.Collectors.toSet());

TreeSet<Integer> ascending = source.stream()
    .collect(java.util.stream.Collectors.toCollection(TreeSet::new));

System.out.println(ascending); // [1, 2, 3, 5]
~~~

`Collectors.toSet()` có nhiệm vụ tạo một `Set`, nhưng **không bảo đảm loại triển khai hay thứ tự duyệt kết quả**. Kể cả khi một lần chạy in ra thứ tự tăng dần, không được dựa vào điều đó.

`Collectors.toCollection(TreeSet::new)` thể hiện yêu cầu rõ ràng hơn: **tạo đúng `TreeSet`** và tuân theo thứ tự của kiểu tập này.

### 3.2. Vì sao không chỉ gọi sorted()?

~~~java
List<Integer> values = List.of(5, 2, 5, 1, 3);

List<Integer> sortedButDuplicated = values.stream()
    .sorted()
    .collect(java.util.stream.Collectors.toList());

TreeSet<Integer> sortedAndUnique = values.stream()
    .collect(java.util.stream.Collectors.toCollection(TreeSet::new));

System.out.println(sortedButDuplicated); // [1, 2, 3, 5, 5]
System.out.println(sortedAndUnique);     // [1, 2, 3, 5]
~~~

`sorted()` **sắp xếp nhưng không loại trùng**; `TreeSet` vừa sắp xếp vừa loại trùng **theo phép so sánh của tập**.

## 4. Thứ tự tự nhiên: Comparable

Với `Integer`, `Long`, `String` và nhiều kiểu chuẩn có `Comparable`, `TreeSet::new` thường dùng được ngay.

~~~java
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

List<Integer> scores = List.of(8, 6, 10, 6, 9, 8);

TreeSet<Integer> orderedScores = scores.stream()
    .collect(Collectors.toCollection(TreeSet::new));

System.out.println(orderedScores); // [6, 8, 9, 10]
System.out.println(orderedScores.first()); // 6
System.out.println(orderedScores.last());  // 10
~~~

**Cần nhớ:** `String.compareTo` so sánh theo thứ tự tự nhiên của chuỗi Java, vốn phân biệt chữ hoa/thường. Nó **không tự động** áp dụng cách xếp chữ cái dành riêng cho tiếng Việt hoặc các quy tắc ngôn ngữ tự nhiên.

Ví dụ, `"Java"` và `"java"` là hai giá trị khác nhau trong `TreeSet<String>` dùng thứ tự tự nhiên. Khi cần chuẩn hóa mã hoặc sắp xếp theo ngôn ngữ, phải xác định rõ quy tắc nghiệp vụ.

### 4.1. Đối tượng không có Comparable thì sao?

~~~java
record Product(String sku, long price) {}

List<Product> products = List.of(
    new Product("SP02", 200L),
    new Product("SP01", 100L)
);

// Không có thứ tự tự nhiên cho Product record.
// products.stream().collect(Collectors.toCollection(TreeSet::new));
~~~

`record` tự sinh `equals` và `hashCode`, **không tự triển khai `Comparable`**. Một `TreeSet` dùng natural ordering có thể ném `ClassCastException` khi thêm các đối tượng không thể so sánh. Cách phù hợp là cung cấp `Comparator<Product>` như mục tiếp theo.

## 5. Chỉ định Comparator khi thu thập

`TreeSet` có constructor nhận `Comparator<? super E>`. Vì `Collectors.toCollection` cần một supplier, hãy dùng lambda để tạo set kèm comparator:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

List<Integer> scores = List.of(8, 6, 10, 6, 9);

TreeSet<Integer> descendingScores = scores.stream()
    .collect(Collectors.toCollection(
        () -> new TreeSet<>(Comparator.reverseOrder())
    ));

System.out.println(descendingScores); // [10, 9, 8, 6]
~~~

Nếu yêu cầu thứ tự tăng dần cho đối tượng có `Comparable`, có thể dùng `Comparator.naturalOrder()`. Nếu muốn giảm dần, `Comparator.reverseOrder()` là lựa chọn ngắn gọn. Nhưng khi kiểu đối tượng không so sánh được tự nhiên, cần comparator mô tả chính xác các trường sắp xếp.

### 5.1. Sắp xếp đối tượng theo một trường

Ví dụ mã đầy đủ chạy trên **Java 17+**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class ProductOrderDemo {
    record Product(String sku, String name, long priceVnd) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
            new Product("SP03", "Bút",  30_000L),
            new Product("SP01", "Sổ",  80_000L),
            new Product("SP02", "Vở",  30_000L)
        );

        Comparator<Product> byPriceThenSku =
            Comparator.comparingLong(Product::priceVnd)
                .thenComparing(Product::sku);

        TreeSet<Product> ordered = products.stream()
            .collect(Collectors.toCollection(
                () -> new TreeSet<>(byPriceThenSku)
            ));

        ordered.forEach(p ->
            System.out.println(p.sku() + ": " + p.priceVnd())
        );
    }
}
~~~

Kết quả:

~~~text
SP02: 30000
SP03: 30000
SP01: 80000
~~~

`comparingLong(Product::priceVnd)` xếp giá **tăng dần**. Khi hai giá bằng nhau, `thenComparing(Product::sku)` dùng mã sản phẩm để phá hòa, nên `SP02` đứng trước `SP03`.

### 5.2. Sắp xếp giảm dần với nhiều tiêu chí

Nếu muốn giá giảm dần, cùng giá thì mã tăng dần:

~~~java
Comparator<Product> byPriceDescThenSku =
    Comparator.comparingLong(Product::priceVnd)
        .reversed()
        .thenComparing(Product::sku);

TreeSet<Product> descending = products.stream()
    .collect(Collectors.toCollection(
        () -> new TreeSet<>(byPriceDescThenSku)
    ));
~~~

Đoạn trên dùng kiểu `Product` và biến `products` từ ví dụ trước đó. `reversed()` chỉ đảo comparator được xây đến thời điểm gọi; `thenComparing(Product::sku)` sau đó tiếp tục sắp mã **tăng dần** khi giá bằng nhau.

**Tránh viết một phép trừ để so sánh số nguyên**, ví dụ `(a, b) -> (int) (a.priceVnd() - b.priceVnd())`. Phép trừ có thể tràn và ép `long` về `int` làm mất thông tin. `Comparator.comparingLong` và `Long.compare` an toàn hơn cho mục đích so sánh.

## 6. TreeSet loại trùng theo compare() == 0, không đơn thuần theo equals()

Đây là điểm quan trọng nhất của bài.

Với `Stream.distinct()`, hai đối tượng được xem là trùng theo `equals()` (và cần tuân thủ hợp đồng `hashCode()`). Với `TreeSet`, hai phần tử được xem là trùng khi **comparator trả 0**, hoặc `compareTo` trả 0 nếu dùng thứ tự tự nhiên.

Ví dụ đối với `BigDecimal`:

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

List<BigDecimal> amounts = List.of(
    new BigDecimal("1.0"),
    new BigDecimal("1.00"),
    new BigDecimal("2.0")
);

System.out.println(amounts.get(0).equals(amounts.get(1)));    // false
System.out.println(amounts.get(0).compareTo(amounts.get(1))); // 0

long byEquals = amounts.stream().distinct().count();

TreeSet<BigDecimal> byOrdering = amounts.stream()
    .collect(Collectors.toCollection(TreeSet::new));

System.out.println(byEquals);        // 3
System.out.println(byOrdering.size()); // 2
~~~

`BigDecimal.equals` còn xét `scale` nên `1.0` và `1.00` khác nhau; `BigDecimal.compareTo` xem chúng có giá trị số bằng nhau. Vì thế `distinct()` giữ cả hai, còn `TreeSet` dùng natural ordering chỉ giữ một đại diện.

### 6.1. Comparator chỉ so sánh giá có thể làm mất bản ghi

Quay lại `Product`:

~~~java
Comparator<Product> onlyPrice =
    Comparator.comparingLong(Product::priceVnd);

TreeSet<Product> byPrice = products.stream()
    .collect(Collectors.toCollection(
        () -> new TreeSet<>(onlyPrice)
    ));

System.out.println(byPrice.size()); // 2, dù nguồn có 3 sản phẩm
~~~

Hai sản phẩm `SP02` và `SP03` cùng giá 30.000 sẽ được coi là **trùng theo comparator**, dù chúng có mã khác nhau. Nếu mục tiêu là **sắp xếp nhưng giữ cả hai sản phẩm**, cần một comparator phân biệt chúng bằng tiêu chí tiếp theo, chẳng hạn `thenComparing(Product::sku)`.

Nếu cần bảo đảm comparator phân biệt tất cả record `Product` có các thành phần khác nhau, có thể thêm cả `name` làm tie-breaker:

~~~java
Comparator<Product> byPriceSkuName =
    Comparator.comparingLong(Product::priceVnd)
        .thenComparing(Product::sku)
        .thenComparing(Product::name);
~~~

Trong ví dụ với các trường khác null, comparator này phân biệt theo cả ba trường của record, phù hợp hơn với `equals` mặc định của record.

### 6.2. Comparator nhất quán với equals nghĩa là gì?

Một comparator **nhất quán với equals** khi `compare(a, b) == 0` tương đương `a.equals(b)` cho các đối tượng liên quan. Đây là tính chất **nên có** nếu muốn `TreeSet` tuân thủ đầy đủ kỳ vọng chung của `Set` về bình đẳng.

Nếu comparator không nhất quán với `equals`, `TreeSet` vẫn có hành vi xác định theo quy tắc sắp xếp, nhưng có thể **không tuân thủ hợp đồng chung của `Set` về equality**. Điều này dễ gây bất ngờ khi kết hợp tập với các API dùng `equals` và `hashCode`.

Hãy chọn comparator theo **mục tiêu nghiệp vụ**:

- Nếu cần tập các **sản phẩm duy nhất** và xếp theo giá: comparator nên có các tie-breaker để phân biệt các sản phẩm khác nhau.
- Nếu cần **các mức giá duy nhất**: nên ánh xạ sang `priceVnd` trước, rồi thu `TreeSet<Long>`.
- Nếu cần **một sản phẩm đại diện cho mỗi mã**, hãy xác định quy tắc chọn đại diện, rồi thu theo mã với cách xử lý trùng minh bạch.

Không nên chọn comparator chỉ theo một trường rồi vô tình loại bỏ dữ liệu ở những trường khác.

### 6.3. Chuỗi không phân biệt chữ hoa/thường

~~~java
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

List<String> languages = List.of("Java", "java", "Kotlin", "kotlin");

TreeSet<String> caseInsensitive = languages.stream()
    .collect(Collectors.toCollection(
        () -> new TreeSet<>(String.CASE_INSENSITIVE_ORDER)
    ));

System.out.println(caseInsensitive); // [Java, Kotlin] trong ví dụ tuần tự
~~~

`String.CASE_INSENSITIVE_ORDER` xem `"Java"` và `"java"` tương đương để sắp xếp và khử trùng. Trong pipeline tuần tự có thứ tự như trên, đại diện được thêm đầu tiên trong nhóm là `"Java"`. Với nguồn unordered hoặc khi cần chọn một bản ghi cụ thể theo chính sách, nên **chuẩn hóa dữ liệu hoặc thiết kế quy tắc chọn đại diện riêng**, thay vì trông chờ vào hình thức chữ hoa/thường được giữ.

Nếu mục tiêu là **mã kỹ thuật thống nhất**, việc `map(value -> value.toLowerCase(Locale.ROOT))` trước khi thu vào `TreeSet` thường rõ nghĩa hơn so với chỉ dùng comparator không phân biệt chữ hoa/thường.

## 7. Chuẩn hóa và lọc dữ liệu trước khi thu thập

Giả sử dữ liệu người dùng có `null`, khoảng trắng và giá trị rỗng. Pipeline nên xác định bước chuẩn hóa trước khi thu thập:

~~~java
import java.util.Arrays;
import java.util.Locale;
import java.util.Objects;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class NormalizedTreeSetDemo {
    public static void main(String[] args) {
        var raw = Arrays.asList(
            " Java ", null, "kotlin", "JAVA", "", " Go "
        );

        TreeSet<String> normalized = raw.stream()
            .filter(Objects::nonNull)
            .map(String::trim)
            .filter(s -> !s.isEmpty())
            .map(s -> s.toLowerCase(Locale.ROOT))
            .collect(Collectors.toCollection(TreeSet::new));

        System.out.println(normalized); // [go, java, kotlin]
    }
}
~~~

Thứ tự bước có lý do:

1. `filter(Objects::nonNull)` loại `null` trước khi gọi `trim`.
2. `map(String::trim)` xóa khoảng trắng đầu/cuối.
3. `filter(s -> !s.isEmpty())` bỏ các giá trị sau chuẩn hóa trở thành rỗng.
4. `toLowerCase(Locale.ROOT)` thống nhất cách ghi mã theo quy tắc kỹ thuật.
5. `collect(toCollection(TreeSet::new))` tạo tập được sắp xếp và không trùng.

`TreeSet` ở đây khử trùng theo **chuỗi đã chuẩn hóa**. Nếu ta thu tập trước khi chuẩn hóa, các chuỗi gốc có thể được xem là khác nhau, và quy tắc yêu cầu sẽ không được đáp ứng.

Lưu ý: ví dụ chỉ đưa ra quy tắc chuẩn hóa mã kỹ thuật. Với họ tên, văn bản tiếng Việt, hoặc từ khóa đa ngôn ngữ, quy tắc collation/Unicode cần được xác định theo ngữ cảnh thay vì mặc định dùng `String.compareTo`.

## 8. Khi nào không nên dùng TreeSet?

Có những nhu cầu trông giống “thu thập có thứ tự” nhưng thực ra cần kiểu Collection khác.

| Nhu cầu thực tế | Cách tiếp cận | Lý do |
|---|---|---|
| Cần tất cả phần tử, kể cả trùng, được sắp xếp | `stream.sorted(comparator).collect(toList())` | `List` giữ các phần tử trùng |
| Cần duy nhất theo `equals`, không quan tâm thứ tự | `collect(toSet())` | Không đòi hỏi cấu trúc cây |
| Cần duy nhất theo `equals`, giữ **thứ tự xuất hiện** | `collect(toCollection(LinkedHashSet::new))` | `LinkedHashSet` dựa trên băm và thứ tự chèn |
| Cần duy nhất theo comparator, luôn duyệt theo thứ tự sắp xếp | `collect(toCollection(() -> new TreeSet<>(comparator)))` | `TreeSet` kết hợp sắp xếp và khử trùng theo comparator |
| Cần giữ bản ghi “tốt nhất” theo khóa nghiệp vụ | Collector vào `Map` với merge function rõ ràng | Có thể điều khiển chính sách chọn đại diện |
| Chỉ cần vài kết quả đầu theo thứ tự tính toán | Xem xét `sorted` + `limit` hoặc thuật toán top-k chuyên dụng | Tránh lưu cả tập nếu không cần |

Ví dụ so sánh trực tiếp:

~~~java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

List<Integer> input = List.of(3, 1, 3, 2);

List<Integer> sortedAll = input.stream()
    .sorted()
    .collect(Collectors.toList());
// [1, 2, 3, 3]

LinkedHashSet<Integer> insertionOrder = input.stream()
    .collect(Collectors.toCollection(LinkedHashSet::new));
// [3, 1, 2]

TreeSet<Integer> naturalOrder = input.stream()
    .collect(Collectors.toCollection(TreeSet::new));
// [1, 2, 3]
~~~

`LinkedHashSet` giữ thứ tự chèn đầu tiên; `TreeSet` duyệt theo thứ tự của comparator. Hai tập có thể cùng số phần tử nhưng khác cách sắp xếp và **khác quy tắc xét trùng** khi kiểu dữ liệu có sự khác biệt giữa `equals` và comparator.

Một phương án khác để vừa sort vừa loại trùng theo `equals` là:

~~~java
LinkedHashSet<Integer> sortedUniqueByEquals = input.stream()
    .sorted()
    .collect(Collectors.toCollection(LinkedHashSet::new));
// [1, 2, 3]
~~~

Cách này phù hợp khi tính bình đẳng phải dựa trên `equals` và thứ tự cần dựa trên `sorted`. Khi comparator không nhất quán với `equals`, kết quả có thể khác cách thu vào `TreeSet`.

## 9. Dùng TreeSet như NavigableSet sau collect

Ưu điểm của `TreeSet` không dừng ở việc in theo thứ tự. Nó còn hỗ trợ tìm giá trị gần một mốc.

~~~java
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

TreeSet<Integer> thresholds = List.of(10, 20, 30, 40).stream()
    .collect(Collectors.toCollection(TreeSet::new));

System.out.println(thresholds.first());      // 10
System.out.println(thresholds.last());       // 40
System.out.println(thresholds.lower(20));    // 10: nhỏ hơn 20
System.out.println(thresholds.floor(20));    // 20: nhỏ hơn hoặc bằng 20
System.out.println(thresholds.ceiling(25));  // 30: lớn hơn hoặc bằng 25
System.out.println(thresholds.higher(30));   // 40: lớn hơn 30
~~~

Bảng các phép điều hướng:

| Phương thức | Ý nghĩa khi dùng thứ tự tăng dần |
|---|---|
| `lower(x)` | Phần tử lớn nhất **nhỏ hơn** `x` |
| `floor(x)` | Phần tử lớn nhất **nhỏ hơn hoặc bằng** `x` |
| `ceiling(x)` | Phần tử nhỏ nhất **lớn hơn hoặc bằng** `x` |
| `higher(x)` | Phần tử nhỏ nhất **lớn hơn** `x` |
| `first()` / `last()` | Phần tử đầu/cuối theo comparator |
| `descendingSet()` | View duyệt theo thứ tự ngược |
| `headSet` / `tailSet` / `subSet` | View đại diện cho các khoảng của tập |

Ví dụ lấy tập con:

~~~java
System.out.println(thresholds.headSet(30));    // [10, 20]
System.out.println(thresholds.tailSet(30));    // [30, 40]
System.out.println(thresholds.subSet(20, 40)); // [20, 30]
System.out.println(thresholds.descendingSet());// [40, 30, 20, 10]
~~~

Trong các overload hai tham số trên, `headSet(to)` và `subSet(from, to)` **loại ranh giới trên**, còn `tailSet(from)` **bao gồm ranh giới dưới**. Các overload khác có thể nhận cờ boolean để chỉ rõ có bao gồm ranh giới hay không.

**Cẩn thận:** nhiều phép lấy tập con hoặc `descendingSet()` trả về **view liên kết với TreeSet gốc**, không phải bản sao độc lập. Nếu sửa view, thay đổi có thể phản ánh lên tập gốc và ngược lại. Nếu muốn một snapshot, cần sao chép các phần tử.

### 9.1. Tập rỗng và null trong kết quả điều hướng

Với `TreeSet` rỗng, `first()` và `last()` ném `NoSuchElementException`. Các phép như `lower`, `floor`, `ceiling` và `higher` có thể trả `null` khi không có phần tử phù hợp, nhưng `null` cũng có thể là phần tử hợp lệ nếu comparator cho phép nó; do đó cần quy tắc dữ liệu phù hợp.

Nếu chỉ muốn xem tập có phần tử hay không:

~~~java
TreeSet<Integer> empty = java.util.stream.Stream.<Integer>empty()
    .collect(Collectors.toCollection(TreeSet::new));

if (!empty.isEmpty()) {
    System.out.println(empty.first());
}
~~~

## 10. Xử lý null và Comparator phù hợp

Với `TreeSet` sử dụng thứ tự tự nhiên, việc thêm `null` thường gây `NullPointerException`. Khi dữ liệu từ nguồn có thể chứa null, cách thường dùng là **lọc bỏ null** trước khi thu:

~~~java
import java.util.Arrays;
import java.util.Objects;
import java.util.TreeSet;
import java.util.stream.Collectors;

TreeSet<String> safe = Arrays.asList("Kotlin", null, "Java")
    .stream()
    .filter(Objects::nonNull)
    .collect(Collectors.toCollection(TreeSet::new));

System.out.println(safe); // [Java, Kotlin]
~~~

Nếu nghiệp vụ **cần giữ null như một phần tử riêng**, bạn có thể dùng comparator hỗ trợ null:

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.TreeSet;
import java.util.stream.Collectors;

Comparator<String> nullableOrder =
    Comparator.nullsFirst(Comparator.naturalOrder());

TreeSet<String> withNull = Arrays.asList("Kotlin", null, "Java")
    .stream()
    .collect(Collectors.toCollection(
        () -> new TreeSet<>(nullableOrder)
    ));

System.out.println(withNull); // [null, Java, Kotlin]
~~~

`Comparator.nullsFirst` đặt null trước các giá trị không null, đồng thời chỉ giữ **một null** vì hai null được comparator xem là bằng nhau. Nếu dùng `nullsLast`, null sẽ đứng cuối.

Việc cho phép null trong tập có thể khiến một số xử lý điều hướng hoặc nghiệp vụ khó phân biệt “không tìm thấy” với “phần tử null”. Trong hệ thống cần mô tả dữ liệu thiếu rõ ràng, cân nhắc chuẩn hóa đầu vào hoặc dùng kiểu trạng thái thay vì giữ null như một giá trị tập.

## 11. Tránh thay đổi trường dùng để so sánh khi đối tượng đã nằm trong TreeSet

Một `TreeSet` dựa vào quan hệ thứ tự của các phần tử để tổ chức cây. Nếu bạn thay đổi các trường dùng trong comparator **sau khi đã thêm đối tượng**, cấu trúc cây có thể không còn phù hợp với thứ tự mới.

Ví dụ thiết kế không an toàn:

~~~java
class MutableScore {
    int score;

    MutableScore(int score) {
        this.score = score;
    }
}

java.util.Comparator<MutableScore> byScore =
    java.util.Comparator.comparingInt(item -> item.score);

TreeSet<MutableScore> ranking = java.util.stream.Stream.of(
        new MutableScore(10),
        new MutableScore(20)
    )
    .collect(java.util.stream.Collectors.toCollection(
        () -> new TreeSet<>(byScore)
    ));

// Không nên thay đổi score của một phần tử đang nằm trong ranking.
// ranking.first().score = 99;
~~~

Khi giá trị khóa so sánh đổi, các thao tác `contains`, `remove`, `first` hoặc việc thêm tiếp phần tử có thể không cho kết quả như mong đợi. Đây là lỗi **mutable key**, tương tự rủi ro thay đổi trường ảnh hưởng `hashCode` khi đối tượng nằm trong `HashSet`.

Cách thực hành an toàn:

- Ưu tiên **record** hoặc đối tượng có trường sắp xếp bất biến.
- Nếu thuộc tính sắp xếp thay đổi, **loại phần tử khỏi tập, cập nhật rồi thêm lại** theo thiết kế phù hợp, hoặc tạo tập mới từ dữ liệu đã cập nhật.
- Comparator nên nhất quán theo thời gian trong lúc một TreeSet đang sử dụng nó; tránh phụ thuộc trạng thái ngoài biến đổi.

## 12. Thu thập song song và yêu cầu về tính đúng đắn

`Collectors.toCollection(TreeSet::new)` không phải collector `CONCURRENT`. Nhưng vẫn có thể dùng trong `parallelStream()` vì framework có thể tạo **nhiều TreeSet độc lập** rồi kết hợp chúng:

~~~java
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

List<Integer> values = List.of(7, 3, 9, 3, 1, 7, 5);

TreeSet<Integer> result = values.parallelStream()
    .collect(Collectors.toCollection(TreeSet::new));

System.out.println(result); // [1, 3, 5, 7, 9]
~~~

Trong ví dụ này, tính đúng đắn dựa vào luật thứ tự tự nhiên của `Integer` và cơ chế collector, không phụ thuộc thứ tự thread hoàn thành. Tuy nhiên, `TreeSet` **không thread-safe** khi nhiều thread tự ý cập nhật cùng một đối tượng tập bên ngoài pipeline.

Đoạn không nên sử dụng:

~~~java
TreeSet<Integer> shared = new TreeSet<>();

// Nguy hiểm: nhiều thread cùng sửa shared.
// values.parallelStream().forEach(shared::add);
~~~

Tương tự, **supplier** trong `toCollection` phải tạo collection mới khi được gọi. Trả về một `TreeSet` dùng chung từ biến ngoài sẽ phá hỏng cơ chế tích lũy độc lập của collector.

### 12.1. Comparator cần thuần và nhất quán

Comparator không nên:

- Dựa trên biến đếm tăng dần, thời gian hiện tại hoặc giá trị ngẫu nhiên.
- Thay đổi kết quả so sánh trong quá trình xây set.
- Có tác dụng phụ làm thay đổi nguồn hay phần tử khi đang được xét.

Nếu cùng hai đối tượng được so sánh lại mà thứ tự thay đổi, cấu trúc cây có thể mất tính nhất quán; với xử lý song song, lỗi có thể càng khó tái hiện.

### 12.2. Không mặc định parallel nhanh hơn

Khi kết hợp TreeSet từ các nhánh, framework có thể phải thêm phần tử của nhánh này vào set nhánh khác, phát sinh chi phí so sánh và cân bằng cây. Với tập nhỏ, xử lý tuần tự thường đơn giản hơn. Với tập lớn, cần đo thời gian, cấp phát bộ nhớ, chi phí comparator và số lượng giá trị duy nhất trên môi trường thật trước khi quyết định.

## 13. Độ phức tạp, bộ nhớ và nguồn vô hạn

`TreeSet` dựa trên cấu trúc cây cân bằng, nên các thao tác cơ bản `add`, `remove` và `contains` có độ phức tạp **O(log k)** đối với `k` phần tử hiện có. Khi thu thập `n` phần tử vào TreeSet có `k` giá trị khác nhau, chi phí thường được nhìn như **O(n log k)**, tùy chi phí comparator. Bộ nhớ giữ lại dữ liệu kết quả tăng theo số phần tử duy nhất.

So sánh định hướng:

| Phương án | Tính chất kết quả | Chi phí đáng lưu ý |
|---|---|---|
| `collect(toSet())` | Không trùng theo `equals/hashCode`; không bảo đảm thứ tự | Thường thuận lợi cho bài toán không cần sắp xếp |
| `sorted().collect(toList())` | Có thứ tự, giữ phần tử trùng | Cần tổ chức việc sắp xếp và giữ toàn bộ phần tử đầu ra |
| `collect(toCollection(TreeSet::new))` | Có thứ tự theo comparator và loại trùng theo so sánh | Chi phí chèn vào cây và lưu các giá trị khác nhau |
| `sorted().collect(toCollection(LinkedHashSet::new))` | Sắp xếp trước, rồi khử trùng theo `equals/hashCode` | Chi phí sắp xếp cùng cơ chế băm và chèn |

Không có phương án nào luôn tối ưu. Nếu chỉ cần **phần tử nhỏ nhất**, `stream.min(comparator)` có thể phù hợp hơn nhiều so với việc thu cả nguồn thành TreeSet chỉ để gọi `first()`. Nếu chỉ cần **một vài phần tử nhỏ nhất**, hãy cân nhắc yêu cầu dữ liệu, độ lớn và thuật toán top-k phù hợp.

### 13.1. Thu toàn bộ một nguồn vô hạn sẽ không kết thúc

~~~java
// Không chạy: nguồn vô hạn, thu toàn bộ vào TreeSet.
// java.util.stream.IntStream.iterate(0, n -> n + 1)
//     .boxed()
//     .collect(Collectors.toCollection(TreeSet::new));
~~~

Khi cần xử lý nguồn không giới hạn, phải có **điều kiện dừng** hoặc **giới hạn hữu hạn** trước terminal operation:

~~~java
TreeSet<Integer> firstFive = java.util.stream.IntStream
    .iterate(0, n -> n + 1)
    .limit(5)
    .boxed()
    .collect(Collectors.toCollection(TreeSet::new));

System.out.println(firstFive); // [0, 1, 2, 3, 4]
~~~

`limit(5)` bảo đảm chỉ lấy năm phần tử từ nguồn `iterate` tuần tự này. Lưu ý `sorted()` hoặc `distinct()` có thể cần trạng thái và tăng chi phí xử lý; đặt giới hạn sai vị trí có thể làm pipeline không kết thúc hoặc thay đổi kết quả.

## 14. Tạo tập kết quả không cho phép sửa

`TreeSet` kết quả từ collector là **mutable**:

~~~java
TreeSet<String> languages = java.util.stream.Stream
    .of("Java", "Go", "Kotlin")
    .collect(Collectors.toCollection(TreeSet::new));

languages.add("Scala"); // Hợp lệ.
~~~

Nếu ứng dụng cần công bố tập để người gọi chỉ đọc, có thể tạo một snapshot và dùng wrapper không cho phép sửa:

~~~java
import java.util.Collections;
import java.util.SortedSet;
import java.util.TreeSet;

SortedSet<String> snapshot =
    Collections.unmodifiableSortedSet(new TreeSet<>(languages));

// snapshot.add("Rust"); // Ném UnsupportedOperationException.
~~~

`new TreeSet<>(languages)` tạo **bản sao hiện tại**; `unmodifiableSortedSet` chặn các thao tác sửa qua wrapper. Nếu chỉ bao một `TreeSet` gốc mà không sao chép, wrapper vẫn là **view** và có thể phản ánh thay đổi từ nơi khác nắm tham chiếu đến set gốc.

Không nhầm điều này với `Collectors.toUnmodifiableSet()`: collector đó tạo set không thể sửa nhưng **không cam kết thứ tự sắp xếp hoặc loại triển khai TreeSet**.

## 15. Bài thực hành: danh mục giá sản phẩm

Một cửa hàng cần lấy **các mức giá bán khác nhau theo thứ tự tăng dần** từ danh sách sản phẩm. Các giá âm là dữ liệu nhập sai nên phải bị loại; đồng thời cần tìm mức giá gần nhất **không nhỏ hơn 50.000 đồng**.

**Yêu cầu:** xây pipeline khai báo dùng `filter`, `mapToLong` hoặc `map`, và `Collectors.toCollection`. Không dùng `forEach(sharedSet::add)`.

Lời giải tham khảo (Java 17+):

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class PriceLevelsPractice {
    record Product(String sku, long priceVnd) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
            new Product("SP01", 70_000L),
            new Product("SP02", 40_000L),
            new Product("SP03", 70_000L),
            new Product("SP04", -1L),
            new Product("SP05", 90_000L)
        );

        TreeSet<Long> priceLevels = products.stream()
            .map(Product::priceVnd)
            .filter(price -> price >= 0L)
            .collect(Collectors.toCollection(TreeSet::new));

        System.out.println(priceLevels);        // [40000, 70000, 90000]
        System.out.println(priceLevels.ceiling(50_000L)); // 70000

        TreeSet<Long> descending = products.stream()
            .map(Product::priceVnd)
            .filter(price -> price >= 0L)
            .collect(Collectors.toCollection(
                () -> new TreeSet<>(Comparator.reverseOrder())
            ));

        System.out.println(descending); // [90000, 70000, 40000]
    }
}
~~~

Trong bài này, `map(Product::priceVnd)` chuyển sản phẩm thành **mức giá**, sau đó `TreeSet<Long>` tự loại các mức giá trùng. Điều này diễn đạt đúng yêu cầu “mức giá khác nhau”. Nếu thu thẳng `Product` vào TreeSet theo giá, các sản phẩm khác nhau có cùng giá sẽ bị gộp, gây mất thông tin sản phẩm.

**Tự kiểm tra:**

1. `Collectors.toSet()` có bảo đảm tạo `TreeSet` không? — **Không**.
2. `stream.sorted().collect(toList())` có loại phần tử trùng không? — **Không**.
3. `TreeSet` dùng gì để xem hai phần tử là trùng? — **Kết quả so sánh bằng 0** của comparator hoặc `compareTo`.
4. Vì sao `new TreeSet<Product>()` có thể lỗi với record `Product` không có comparator? — Record **không mặc định triển khai `Comparable`**.
5. Khi nào cần `thenComparing`? — Khi comparator chính có thể xem các đối tượng khác nhau là đồng hạng nhưng nghiệp vụ phải giữ chúng tách biệt.
6. `TreeSet` dùng natural order có tự chấp nhận `null` không? — **Không nên dựa vào điều đó**; lọc null hoặc dùng comparator hỗ trợ null theo chủ đích.
7. `TreeSet` từ `collect` có thể gọi `add` sau khi thu không? — **Có**, nó là collection mutable.
8. Có nên thay đổi trường dùng để so sánh của phần tử đang nằm trong TreeSet không? — **Không**, vì có thể làm hỏng quan hệ thứ tự của cây.
9. Có thể dùng `parallelStream().collect(toCollection(TreeSet::new))` không? — **Có**, nếu collector và comparator tuân thủ hợp đồng; không suy ra rằng kết quả sẽ chạy nhanh hơn.

## 16. Ghi nhớ khi chọn TreeSet trong Java Stream API

**`collect(Collectors.toCollection(TreeSet::new))`** là cách rõ ràng để thu các phần tử thành một tập **được sắp xếp** và **không trùng theo phép so sánh**. Khi cần thứ tự khác tự nhiên, cung cấp `Comparator` trong supplier: `() -> new TreeSet<>(comparator)`.

Trước khi chọn TreeSet, cần trả lời ba câu hỏi: **dữ liệu có thực sự cần sắp xếp không**, **“trùng” được định nghĩa theo `equals` hay theo comparator**, và **có cần giữ các bản ghi khác nhau nhưng trùng một trường sắp xếp hay không**. Nếu cần giữ tất cả phần tử, hãy dùng `sorted` với `List`; nếu cần thứ tự xuất hiện và equality, cân nhắc `LinkedHashSet`; nếu cần chọn đại diện theo khóa, định nghĩa quy tắc riêng bằng collector.

Cuối cùng, hãy đảm bảo **comparator nhất quán**, **trường so sánh ổn định**, **nguồn dữ liệu có giới hạn phù hợp**, và **không chia sẻ TreeSet mutable thiếu đồng bộ**. Những nguyên tắc này giúp sử dụng Stream API an toàn khi mở rộng sang grouping, collector tùy chỉnh, `Spliterator`, xử lý song song và Stream Gatherers.
