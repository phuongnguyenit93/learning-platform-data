# `Collectors.groupingBy()` theo một thuộc tính trong Java

## 1. Bài toán và mục tiêu học tập

Giả sử ứng dụng có danh sách sản phẩm, mỗi sản phẩm chứa tên, danh mục và giá. Ta cần tập hợp những sản phẩm **cùng danh mục** lại với nhau, chẳng hạn các cuốn sách thuộc nhóm `Books`, đồ ăn thuộc `Food`, thiết bị thuộc `Gadgets`.

Với Stream, giải pháp trực tiếp là `Collectors.groupingBy(classifier)`:

```java
Map<String, List<Product>> byCategory = products.stream()
        .collect(Collectors.groupingBy(Product::category));
```

Đọc từ trái sang phải:

1. `products.stream()` tạo một luồng phần tử `Product`.
2. `Product::category` là **classifier**, tức hàm xác định khóa nhóm cho mỗi phần tử.
3. `Collectors.groupingBy(...)` tạo một collector có nhiệm vụ gom các phần tử có cùng khóa.
4. `collect(...)` là **terminal operation**, thực thi pipeline và tạo `Map` kết quả.
5. Mỗi khóa của `Map` là một danh mục; giá trị tương ứng mặc định là `List<Product>` gồm các sản phẩm được phân vào nhóm đó.

Khác với `filter` chỉ giữ một tập con, `groupingBy` **phân loại toàn bộ** phần tử vào các nhóm (miễn classifier trả về khóa hợp lệ). Một phần tử được xếp vào một khóa do classifier xác định; các phần tử có khóa bằng nhau theo `equals` sẽ cùng nhóm.

Sau bài học, bạn sẽ biết cách chọn thuộc tính nhóm, đọc đúng kiểu `Map<K,List<T>>`, dùng các overload và downstream collector, xử lý dữ liệu rỗng hoặc khóa null, bảo đảm thứ tự khi cần, và kiểm thử kết quả thay vì dựa vào thứ tự in ngẫu nhiên của `HashMap`.

## 2. Cơ chế: classifier quyết định khóa của từng nhóm

Hãy xem dữ liệu:

| Tên | Danh mục | Giá |
| --- | --- | ---: |
| Java | Books | 120 |
| Mouse | Gadgets | 80 |
| Tea | Food | 40 |
| Algorithms | Books | 200 |
| Keyboard | Gadgets | 150 |
| Coffee | Food | 60 |
| Spring | Books | 180 |

Khi classifier là `Product::category`, kết quả về mặt logic là:

```text
Stream<Product>
  Java       → Books  ┐
  Mouse      → Gadgets├→ Map<Category, List<Product>>
  Tea        → Food   │
  Algorithms → Books  │
  Keyboard   → Gadgets│
  Coffee     → Food   │
  Spring     → Books  ┘

Books   → [Java, Algorithms, Spring]
Food    → [Tea, Coffee]
Gadgets → [Mouse, Keyboard]
```

Đó là biểu diễn theo nhóm; không phải bảo đảm các khóa Map sẽ được duyệt và in theo thứ tự `Books`, `Food`, `Gadgets` nếu bạn chỉ dùng overload `groupingBy(classifier)` mặc định. Nếu muốn **thứ tự khóa xác định**, có thể cung cấp `TreeMap::new` làm map factory như phần sau.

### Kiểu của classifier

Giả sử khai báo:

```java
record Product(String name, String category, int price) {}
```

`Product::category` có thể dùng như `Function<Product, String>`:

```java
Function<Product, String> classifier = Product::category;
```

- `T = Product`: kiểu của phần tử Stream.
- `K = String`: kiểu khóa do classifier trả về.
- Giá trị mặc định mỗi khóa là một `List<Product>`.

Với `Stream<Employee>`, classifier có thể là `Employee::department`, `Employee::city` hoặc một lambda tạo khóa theo quy tắc nghiệp vụ. Điều kiện cốt lõi: **mọi phần tử cùng nhóm phải tạo khóa bằng nhau theo logic so sánh của `Map`**. Đối với `String`, `"Books"` và `"books"` là hai khóa khác nhau. Muốn không phân biệt chữ hoa/thường, hãy chuẩn hóa trước khi nhóm.

## 3. Các overload quan trọng của `groupingBy`

Trong `java.util.stream.Collectors` có ba overload thường dùng:

```java
// 1. Nhóm theo classifier, giá trị là List<T>.
groupingBy(classifier)

// 2. Nhóm theo classifier rồi tổng hợp riêng từng nhóm.
groupingBy(classifier, downstream)

// 3. Nhóm và chọn Map cụ thể, kèm downstream.
groupingBy(classifier, mapFactory, downstream)
```

Ý nghĩa kiểu tổng quát:

| Cách gọi | Kiểu kết quả thường gặp | Mục đích |
| --- | --- | --- |
| `groupingBy(Product::category)` | `Map<String, List<Product>>` | Gom nguyên bản ghi theo danh mục |
| `groupingBy(Product::category, counting())` | `Map<String, Long>` | Đếm số bản ghi trong mỗi nhóm |
| `groupingBy(Product::category, mapping(Product::name, toList()))` | `Map<String, List<String>>` | Chỉ giữ tên trong từng nhóm |
| `groupingBy(Product::category, summingInt(Product::price))` | `Map<String, Integer>` | Tổng giá trị một thuộc tính của nhóm |
| `groupingBy(Product::category, TreeMap::new, toList())` | `TreeMap<String, List<Product>>` hoặc `Map<String,List<Product>>` tùy khai báo biến | Dùng map có khóa sắp xếp |

`downstream` là một `Collector` dùng **bên trong mỗi nhóm**, không phải là thao tác `map` áp dụng cho toàn bộ Stream trước khi nhóm. Phân biệt:

```java
// Giữ nguyên Product trong mỗi nhóm:
products.stream()
        .collect(Collectors.groupingBy(Product::category));

// Mỗi nhóm chỉ giữ tên:
products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                Collectors.mapping(Product::name, Collectors.toList())));
```

Ở ví dụ thứ hai, classifier vẫn được gọi trên **Product gốc**, rồi từng Product trong nhóm mới được downstream chuyển thành tên.

## 4. Ví dụ Java 17+ hoàn chỉnh

Tạo file `GroupingByAttributeDemo.java`. Chương trình sử dụng dữ liệu cố định, tránh phụ thuộc giờ hệ thống, thứ tự duyệt `HashMap` hay thư viện ngoài JDK. Nó minh họa nhóm thành `List`, biến đổi giá trị từng nhóm, đếm, tính tổng, trung bình và xử lý danh mục trống.

```java
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class GroupingByAttributeDemo {
    record Product(String name, String category, int price) {}

    static List<Product> sample() {
        return List.of(
                new Product("Java", "Books", 120),
                new Product("Mouse", "Gadgets", 80),
                new Product("Tea", "Food", 40),
                new Product("Algorithms", "Books", 200),
                new Product("Keyboard", "Gadgets", 150),
                new Product("Coffee", "Food", 60),
                new Product("Spring", "Books", 180));
    }

    static Map<String, List<Product>> groupProducts(
            List<Product> products) {
        return products.stream()
                .collect(Collectors.groupingBy(
                        Product::category,
                        TreeMap::new,
                        Collectors.toList()));
    }

    static Map<String, List<String>> groupNames(
            List<Product> products) {
        return products.stream()
                .collect(Collectors.groupingBy(
                        Product::category,
                        TreeMap::new,
                        Collectors.mapping(
                                Product::name, Collectors.toList())));
    }

    static Map<String, Long> countByCategory(
            List<Product> products) {
        return products.stream()
                .collect(Collectors.groupingBy(
                        Product::category,
                        TreeMap::new,
                        Collectors.counting()));
    }

    static Map<String, Integer> totalPrices(
            List<Product> products) {
        return products.stream()
                .collect(Collectors.groupingBy(
                        Product::category,
                        TreeMap::new,
                        Collectors.summingInt(Product::price)));
    }

    static Map<String, Double> averagePrices(
            List<Product> products) {
        return products.stream()
                .collect(Collectors.groupingBy(
                        Product::category,
                        TreeMap::new,
                        Collectors.averagingInt(Product::price)));
    }

    static void check(Object expected, Object actual, String label) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    label + ": expected=" + expected
                            + ", actual=" + actual);
        }
    }

    static void runTests() {
        List<Product> products = sample();
        Map<String, List<String>> names = groupNames(products);

        check(List.of("Java", "Algorithms", "Spring"),
                names.get("Books"), "book names");
        check(List.of("Tea", "Coffee"),
                names.get("Food"), "food names");
        check(List.of("Mouse", "Keyboard"),
                names.get("Gadgets"), "gadget names");

        check(Map.of("Books", 3L, "Food", 2L, "Gadgets", 2L),
                countByCategory(products), "category counts");
        check(Map.of("Books", 500, "Food", 100, "Gadgets", 230),
                totalPrices(products), "category price totals");

        check(true, Math.abs(
                averagePrices(products).get("Books") - 500.0 / 3)
                < 1e-9, "books average");

        check(7, products.size(), "source list unchanged");
        check(Map.of(), groupProducts(List.of()), "empty input");

        // Đưa khóa null về một nhãn tường minh.
        List<Product> unknown = List.of(
                new Product("Mystery", null, 10));
        Map<String, Long> normalized = unknown.stream()
                .collect(Collectors.groupingBy(
                        p -> p.category() == null
                                ? "UNKNOWN" : p.category(),
                        Collectors.counting()));
        check(Map.of("UNKNOWN", 1L),
                normalized, "unknown category");

        // Classifier trả null trực tiếp bị groupingBy từ chối.
        boolean nullKeyRejected = false;
        try {
            unknown.stream()
                    .collect(Collectors.groupingBy(
                            Product::category));
        } catch (NullPointerException expected) {
            nullKeyRejected = true;
        }
        check(true, nullKeyRejected, "null classifier key");
    }

    public static void main(String[] args) {
        runTests();
        System.out.println("tests=PASS");

        List<Product> products = sample();
        Map<String, List<String>> names = groupNames(products);

        for (Map.Entry<String, List<String>> entry
                : names.entrySet()) {
            System.out.println(entry.getKey()
                    + "=" + entry.getValue());
        }

        System.out.println("counts=" + countByCategory(products));
        System.out.println("totals=" + totalPrices(products));
        System.out.println("booksAverage="
                + String.format(Locale.ROOT, "%.1f",
                        averagePrices(products).get("Books")));

        List<Product> unknown = List.of(
                new Product("Mystery", null, 10));
        long unknownCount = unknown.stream()
                .collect(Collectors.groupingBy(
                        p -> p.category() == null
                                ? "UNKNOWN" : p.category(),
                        Collectors.counting()))
                .get("UNKNOWN");
        System.out.println("unknown=" + unknownCount);

        boolean nullKeyRejected = false;
        try {
            Stream.of(new Product("Mystery", null, 10))
                    .collect(Collectors.groupingBy(
                            Product::category));
        } catch (NullPointerException expected) {
            nullKeyRejected = true;
        }
        System.out.println("nullKeyRejected=" + nullKeyRejected);
    }
}
```

Chạy bằng JDK 17 hoặc mới hơn:

```bash
javac GroupingByAttributeDemo.java
java GroupingByAttributeDemo
```

Stdout dự kiến, theo đúng thứ tự:

```text
tests=PASS
Books=[Java, Algorithms, Spring]
Food=[Tea, Coffee]
Gadgets=[Mouse, Keyboard]
counts={Books=3, Food=2, Gadgets=2}
totals={Books=500, Food=100, Gadgets=230}
booksAverage=166.7
unknown=1
nullKeyRejected=true
```

### Vì sao kết quả có thứ tự xác định?

Trong ví dụ, ta truyền `TreeMap::new` vào overload ba tham số. `TreeMap<String,...>` dùng thứ tự tự nhiên của `String`, nên các khóa xuất hiện theo thứ tự `Books`, `Food`, `Gadgets` khi duyệt `entrySet()` và khi in bản đồ. Bên trong mỗi nhóm, `Collectors.toList()` duy trì encounter order của Stream có thứ tự trong pipeline tuần tự nêu trên, nên các tên xuất hiện theo thứ tự đầu vào trong từng danh mục.

Tuy nhiên, `Collectors.groupingBy` mặc định **không cam kết kiểu `Map` cụ thể**, cũng không cam kết các khóa xuất hiện theo thứ tự nào. Đừng dùng một kết quả in của `HashMap` tình cờ “đúng” để làm test. Nếu bài toán cần thứ tự **theo lần xuất hiện đầu tiên**, có thể chọn `LinkedHashMap::new`; nếu muốn sắp xếp theo khóa, dùng `TreeMap::new`.

### Kiểm tra được những gì?

`runTests()` xác minh số sản phẩm mỗi nhóm, thứ tự các tên trong từng nhóm, tổng giá, trung bình của nhóm Books, nguồn đầu vào không thay đổi, Stream rỗng và chính sách xử lý khóa `null`. Lệnh `check` ném `AssertionError` nếu có sai lệch; không cần bật `-ea`.

Kết quả trung bình nhóm Books là `(120 + 200 + 180) / 3 = 500 / 3`, tức khoảng `166.666...`. `String.format(Locale.ROOT, "%.1f", ...)` làm tròn thành `166.7` và giữ dấu chấm thập phân ổn định theo locale. `Collectors.averagingInt` trả `Double`, không phải `Integer`.

## 5. `mapping`: chỉ thu thập thuộc tính cần thiết của từng nhóm

Từ `Map<String, List<Product>>`, đôi khi phía hiển thị chỉ cần tên, không cần giá và bản ghi đầy đủ. `Collectors.mapping` là downstream phù hợp:

```java
Map<String, List<String>> namesByCategory =
        products.stream().collect(
                Collectors.groupingBy(
                        Product::category,
                        Collectors.mapping(
                                Product::name,
                                Collectors.toList())));
```

Ý nghĩa:

- `Product::category` quyết định **nhóm**.
- `Product::name` quyết định **giá trị đưa vào nhóm**.
- `Collectors.toList()` thu thập các tên cùng nhóm thành danh sách.

So với `products.stream().map(Product::name)` trước rồi mới nhóm, cách dùng downstream vẫn giữ được đối tượng `Product` ở thời điểm classifier xác định danh mục. Nếu chuyển thành `String` quá sớm, bạn có thể mất trường `category` và không còn đủ dữ liệu để phân nhóm.

Nếu muốn một **tập tên không trùng**, thay `toList()` bằng `toSet()`:

```java
Map<String, java.util.Set<String>> uniqueNames =
        products.stream().collect(
                Collectors.groupingBy(
                        Product::category,
                        Collectors.mapping(
                                Product::name,
                                Collectors.toSet())));
```

`toSet()` không bảo đảm thứ tự duyệt phần tử; yêu cầu thứ tự hoặc comparator phải được thể hiện qua collector phù hợp, chẳng hạn `toCollection(TreeSet::new)` nếu kiểu có thứ tự tự nhiên hoặc comparator đúng.

## 6. `counting`, `summingInt`, `averagingInt` và các downstream khác

Nhóm theo một thuộc tính không có nghĩa kết quả bắt buộc là `List<T>`. `groupingBy` có thể dùng nhiều downstream để tạo các dạng thống kê khác nhau.

### Đếm số phần tử mỗi nhóm

```java
Map<String, Long> counts = products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                Collectors.counting()));
```

Giá trị thuộc kiểu `Long`, không phải `Integer`, bởi `Collectors.counting()` tạo kết quả `Long`.

### Tổng một thuộc tính số

```java
Map<String, Integer> priceTotals = products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                Collectors.summingInt(Product::price)));
```

Ở ví dụ, tổng thuộc tính `price` trên từng nhóm là Books=500, Food=100, Gadgets=230. Lưu ý dùng `summingInt` có thể tràn số nguyên nếu dữ liệu đủ lớn; chọn `summingLong` hoặc một chính sách số học phù hợp khi cần.

### Trung bình một thuộc tính số

```java
Map<String, Double> averages = products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                Collectors.averagingInt(Product::price)));
```

Mỗi nhóm có `Double` là giá trị trung bình. Việc dùng trung bình dấu phẩy động có thể cần chính sách độ chính xác/làm tròn riêng trong nghiệp vụ tiền tệ. Không dùng `double` như một biểu diễn tiền chính xác tuyệt đối nếu có yêu cầu tài chính nghiêm ngặt.

### Tổng hợp nhiều thống kê trên một nhóm

Khi cần số lượng và tổng trong **một lần nhóm**, có thể dùng `Collectors.summarizingInt(...)`:

```java
Map<String, java.util.IntSummaryStatistics> statistics =
        products.stream().collect(
                Collectors.groupingBy(
                        Product::category,
                        Collectors.summarizingInt(Product::price)));
```

Mỗi `IntSummaryStatistics` cung cấp `getCount()`, `getSum()`, `getMin()`, `getMax()`, `getAverage()`. Kết quả `getSum()` là `long`, nhưng vẫn phải suy nghĩ về giới hạn kiểu và ý nghĩa của phép cộng khi xử lý thực tế.

**Lựa chọn phụ thuộc đầu ra nghiệp vụ**: nếu cần danh sách sản phẩm thì dùng `toList`; nếu cần báo cáo tổng hợp thì nên thu thống kê trực tiếp, tránh giữ một danh sách lớn chỉ để đếm sau đó.

## 7. Chọn đúng `Map` và hiểu thứ tự

Overload đơn giản:

```java
Map<String, List<Product>> grouped = products.stream()
        .collect(Collectors.groupingBy(Product::category));
```

Không cam kết kết quả là `HashMap`, `TreeMap`, `LinkedHashMap` hoặc bất kỳ triển khai cụ thể nào. API không quy định thứ tự khóa. Nếu ứng dụng cần dựa vào thứ tự, hãy tạo nó **tường minh**:

### Khóa có thứ tự từ điển

```java
Map<String, List<Product>> alphabetical = products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                java.util.TreeMap::new,
                Collectors.toList()));
```

`TreeMap` yêu cầu khóa có thể so sánh hoặc được cung cấp comparator; `String` có thứ tự tự nhiên.

### Giữ thứ tự xuất hiện đầu tiên của khóa

```java
Map<String, List<Product>> firstSeen = products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                java.util.LinkedHashMap::new,
                Collectors.toList()));
```

Với Stream tuần tự, có encounter order và classifier nhất quán, `LinkedHashMap` phản ánh thứ tự thêm các khóa vào map. Nếu bật song song hoặc dùng nguồn unordered, không nên giả định thứ tự chèn khóa tương đương thứ tự ban đầu trong mọi trường hợp. Nếu thứ tự là hợp đồng nghiêm ngặt, hãy kiểm thử cấu hình nguồn và collector thực tế hoặc sắp xếp rõ ràng ở bước cuối.

### Tính chỉnh sửa của Map và List

Collector `groupingBy` không cam kết một kiểu Map cụ thể, khả năng chỉnh sửa, khả năng tuần tự hóa hay thread-safety của Map/List kết quả ở mọi overload. Nếu muốn kết quả không cho chỉnh sửa, có thể lựa chọn cấu trúc dữ liệu và tạo bản sao theo chính sách hợp đồng, ví dụ:

```java
Map<String, List<Product>> grouped = products.stream()
        .collect(Collectors.groupingBy(Product::category));

Map<String, List<Product>> snapshot = grouped.entrySet().stream()
        .collect(Collectors.toUnmodifiableMap(
                Map.Entry::getKey,
                entry -> List.copyOf(entry.getValue())));
```

Đoạn này minh họa và cần `Product`, `products`, `Map`, `List`, `Collectors` được khai báo/import tương ứng. `Map` và `List` tạo bởi `copyOf`/`toUnmodifiableMap` không chấp nhận phần tử/khóa `null` theo hợp đồng. Nếu cần giữ thứ tự khóa, `toUnmodifiableMap` không hứa thứ tự duyệt; phải chọn thiết kế khác có chính sách thứ tự và bất biến phù hợp.

## 8. Xử lý khóa `null`, khác biệt chữ hoa/thường và khóa nhiều dạng

### `groupingBy` không chấp nhận classifier trả về `null`

Lỗi dễ gặp:

```java
Map<String, List<Product>> grouped = products.stream()
        .collect(Collectors.groupingBy(Product::category));
```

Nếu có `Product` có `category() == null`, `Collectors.groupingBy` sẽ ném `NullPointerException` khi classifier trả về khóa `null`. Điều này đúng ngay cả nếu kiểu `Map` khác có thể chấp nhận khóa null: **collector này yêu cầu khóa phân nhóm khác null**.

Các phương án xử lý tùy hợp đồng:

- Nếu category bắt buộc, kiểm tra/validate sớm và ném lỗi có ngữ cảnh rõ ràng.
- Nếu category có thể thiếu và phải được nhóm chung, dùng một nhãn thay thế như `"UNKNOWN"`.
- Nếu cần phân biệt category thực sự có tên `"UNKNOWN"` với category chưa xác định, dùng **kiểu khóa riêng** (record hoặc enum đại diện trạng thái), thay vì ghép tùy tiện hai trường hợp vào một chuỗi.

Ví dụ dùng nhãn thay thế:

```java
Map<String, Long> counts = products.stream()
        .collect(Collectors.groupingBy(
                p -> p.category() == null
                        ? "UNKNOWN" : p.category(),
                Collectors.counting()));
```

Đây là **chính sách dữ liệu** được chọn có chủ đích; không dùng `filter(Objects::nonNull)` để âm thầm bỏ cả sản phẩm nếu bài toán thực tế cần thống kê lỗi hoặc sản phẩm chưa có danh mục.

### Chuẩn hóa khóa trước khi nhóm

Nếu dữ liệu có `"Books"`, `"books"` và `" BOOKS "`, classifier mặc định xem đó là các khóa khác nhau. Có thể chuẩn hóa:

```java
Map<String, List<Product>> grouped = products.stream()
        .collect(Collectors.groupingBy(
                p -> p.category().strip()
                        .toLowerCase(java.util.Locale.ROOT)));
```

Đoạn trên giả định `category()` khác null; khi dữ liệu có thể null, phải xử lý theo hợp đồng trước khi gọi `strip()`. `Locale.ROOT` tránh phụ thuộc locale mặc định của máy. Việc chuẩn hóa có thể hữu ích cho mã danh mục nhưng không phải lúc nào cũng phù hợp với các chuỗi hiển thị tên riêng hoặc ngôn ngữ khác nhau.

### Phân biệt khóa với giá trị trong nhóm

Classifier là hàm `T -> K`. Nếu muốn nhóm theo thuộc tính tính toán như khoảng giá, bạn cũng có thể dùng classifier tạo nhãn:

```java
Map<String, List<Product>> byPriceLevel = products.stream()
        .collect(Collectors.groupingBy(
                p -> p.price() >= 150 ? "HIGH" : "STANDARD"));
```

Đó vẫn là nhóm **theo một thuộc tính suy ra**. Đừng nhầm việc này với `partitioningBy(Predicate)`, vốn luôn cho hai khóa Boolean `true` và `false` (kể cả khi một bên không có phần tử, giá trị downstream tương ứng được cung cấp). `groupingBy` chỉ tạo các khóa thực sự xuất hiện trong dữ liệu đầu vào; trên Stream rỗng, kết quả là Map rỗng.

## 9. `groupingBy` so với `toMap`, `partitioningBy` và `groupingByConcurrent`

| Công cụ | Phù hợp khi | Khác biệt |
| --- | --- | --- |
| `groupingBy(classifier)` | Nhiều phần tử có cùng khóa, cần nhóm lại | Tạo các nhóm, không coi khóa trùng là lỗi |
| `toMap(keyMapper, valueMapper)` | Mỗi khóa mong đợi một giá trị, hoặc có chiến lược merge rõ | Khóa trùng có thể ném `IllegalStateException` nếu không có merge function |
| `partitioningBy(predicate)` | Chỉ hai nhóm đúng/sai | Map khóa `Boolean`, có cả hai nhóm |
| `groupingByConcurrent(classifier)` | Grouping đồng thời theo nhu cầu cụ thể | Tạo concurrent map; đặc tính thứ tự và downstream khác nhóm tuần tự |

Dùng `groupingByConcurrent` không mặc định làm mọi phép tính nhanh hơn; cần đánh giá dữ liệu, nguồn, chi phí classifier/downstream, độ tranh chấp khóa và yêu cầu thứ tự. Nó là collector **concurrent** và **unordered**; không thích hợp nếu ứng dụng đòi duy trì chính xác encounter order của danh sách trong từng nhóm.

Các thao tác nhóm thường phải giữ dữ liệu/trạng thái trung gian cho mỗi khóa. Với hàng triệu phần tử hoặc một danh mục rất lớn, `groupingBy(..., toList())` có thể tiêu tốn nhiều bộ nhớ. Nếu chỉ cần đếm hoặc tổng, dùng downstream `counting`/`summingInt` và không giữ toàn bộ phần tử trong mỗi nhóm.

## 10. Bài tập kiểm thử đúng hành vi

Một số bất biến và ca kiểm thử quan trọng:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Danh sách rỗng | `groupingBy` trả `Map` rỗng, không có khóa ảo |
| Một danh mục duy nhất | Có đúng một khóa, danh sách chứa đủ phần tử |
| Nhiều danh mục xen kẽ | Phân nhóm đúng, không mất phần tử |
| Khóa giống nhau | Những phần tử cùng category ở cùng nhóm |
| Khác hoa/thường | Chuẩn hóa hoặc phân biệt theo đúng quy tắc được công bố |
| Khóa `null` | Có validation hoặc nhãn/kiểu khóa thay thế; không bỏ lỗi im lặng |
| Thứ tự khóa | Nếu cần, chọn `TreeMap`/`LinkedHashMap` có lý do |
| Thứ tự phần tử mỗi nhóm | Kiểm thử encounter order khi nguồn và collector bảo đảm |
| Downstream tổng hợp | Kiểm tra loại kết quả `Long`, `Integer`, `Double` và giá trị |
| Dữ liệu đầu vào | Không có mutation ngoài ý muốn |

Đối với ví dụ ở phần 4, có thể kiểm tra bất biến:

```java
long totalGrouped = groupProducts(sample()).values().stream()
        .mapToLong(List::size)
        .sum();

// totalGrouped == sample().size() == 7
```

Đoạn kiểm tra này phù hợp khi không có phần tử/khóa không hợp lệ làm phép nhóm thất bại và mọi phần tử được phân vào đúng một nhóm. Chỉ đối chiếu tổng là chưa đủ: hai sản phẩm đặt nhầm nhóm vẫn có thể cho tổng 7; phải kiểm tra khóa và thành viên của nhóm như `runTests()`.

### Mở rộng: nhóm theo loại với kiểm thử bất biến

Để tránh nhập nhằng do chuỗi danh mục do người dùng nhập, có thể thay `String category` bằng một `enum Category` và xác định hành vi với nhãn không nhận dạng được tại tầng parse. `groupingBy(Product::category)` lúc này trả `Map<Category, List<Product>>`, vẫn có cùng cơ chế. Khi danh mục thực sự là tập giá trị đóng, `EnumMap` có thể là map factory phù hợp; cần khai báo supplier đúng kiểu và bảo đảm không có khóa null.

## 11. Các lỗi phổ biến

**Lỗi 1 — nghĩ `groupingBy` trả một `List` duy nhất.** Kết quả mặc định là `Map<K, List<T>>`. Truy cập một nhóm bằng `grouped.get(key)`; khi khóa không tồn tại, `Map.get()` thường trả `null`, không phải một danh sách rỗng. Có thể dùng `getOrDefault(key, List.of())` để tránh null khi chỉ muốn đọc.

**Lỗi 2 — giả định thứ tự khóa của Map mặc định.** Việc hiển thị có vẻ ổn trên một môi trường không tạo ra hợp đồng sắp xếp. Chọn map factory hoặc sort khi cần thứ tự.

**Lỗi 3 — classifier trả null.** `groupingBy` không chấp nhận khóa null. Validation/normalize phải có trước khi nhóm; `TreeMap` cũng không cho phép khóa null với thứ tự tự nhiên.

**Lỗi 4 — xem khóa khác nhau chỉ vì cách viết.** `"Books"` và `"books"` khác nhau; chuẩn hóa có chủ đích, có test Unicode/locale nếu dữ liệu đa ngôn ngữ.

**Lỗi 5 — dùng `mapping` ở sai vị trí.** Nếu `map(Product::name)` trước khi xác định category, bạn không còn category trên phần tử nguồn. `mapping` downstream giúp phân nhóm trên Product trước, rồi chỉ giữ tên.

**Lỗi 6 — đoán kiểu của kết quả downstream.** `counting()` trả `Long`; `averagingInt()` trả `Double`. Đừng gán nhầm `Map<String,Integer>` cho `counting()` hoặc tự ép kiểu không an toàn.

**Lỗi 7 — dùng `toMap` cho khóa không duy nhất.** `toMap(Product::category, Product::name)` mặc định sẽ gặp lỗi khi hai sản phẩm cùng danh mục. `groupingBy` được thiết kế cho trường hợp khóa lặp; nếu cần map một giá trị/khóa thì phải thiết kế merge rule.

**Lỗi 8 — dùng `parallelStream` và thay đổi cấu trúc chung bên ngoài.** Tránh side effect lên một `HashMap`/`ArrayList` chung trong lambda. Collector đã có cơ chế tích lũy/kết hợp; hãy dùng API collector chuẩn và kiểm tra yêu cầu thứ tự/concurrency.

**Lỗi 9 — quên chi phí bộ nhớ.** `groupingBy(..., toList())` giữ phần tử trong danh sách theo nhóm. Với dữ liệu lớn và chỉ cần thống kê, hãy chọn downstream aggregation thích hợp hoặc kiến trúc xử lý theo lô.

**Lỗi 10 — nhầm Map chứa kết quả với dữ liệu nguồn.** `collect` tạo cấu trúc kết quả; nó không tự xóa hoặc sửa sản phẩm trong `List` nguồn. Nếu `Product` là object mutable và bạn sửa nó về sau, các danh sách nhóm vẫn có thể tham chiếu cùng object; dùng record bất biến hoặc snapshot nếu cần cô lập dữ liệu.

## 12. Bài tập thực hành

1. Với `List<Product>` mẫu, dùng `groupingBy(Product::category)` rồi kiểm tra đủ ba khóa và tổng số phần tử nhóm bằng 7. Tránh so sánh thứ tự in Map.
2. Dùng `groupingBy(Product::category, counting())` để tìm số sản phẩm mỗi nhóm. Tại sao kiểu giá trị là `Long`?
3. Dùng downstream `mapping(Product::name, toSet())` để lấy tên không trùng. Nêu tác động đến thứ tự phần tử.
4. Dùng `groupingBy(Product::category, summingInt(Product::price))` để tính tổng giá, xác minh Books=500, Food=100, Gadgets=230.
5. Biến thể dữ liệu có `"Books"`, `"books"`, `" Books "`. Thiết kế classifier chuẩn hóa về một khóa và viết test.
6. Bổ sung `Product` có `category=null`. Viết test kiểm tra lỗi của `groupingBy(Product::category)` rồi sửa classifier để đưa vào nhóm `"UNKNOWN"` hoặc một kiểu khóa tường minh.
7. Cho Stream rỗng; so sánh kết quả `groupingBy` và `partitioningBy` theo số khóa.
8. Thử `TreeMap::new` và `LinkedHashMap::new` trong overload ba tham số, giải thích khác nhau giữa thứ tự theo tên và thứ tự gặp khóa.
9. Thử nhóm các sản phẩm thành Map theo nhãn giá `HIGH`/`STANDARD`. So sánh với `partitioningBy(p -> p.price() >= 150)`.
10. Chọn downstream `summarizingInt(Product::price)` và lấy số bản ghi, tổng, giá nhỏ nhất/lớn nhất, trung bình trong mỗi nhóm; kiểm tra logic với bảng dữ liệu mẫu.

## 13. Tổng kết

`Collectors.groupingBy()` phân loại các phần tử `Stream<T>` theo một **classifier `T → K`**:

- Overload đơn giản tạo `Map<K,List<T>>`, nơi mỗi khóa đại diện một nhóm.
- Overload có downstream cho phép tạo `Map<K,D>`, ví dụ số lượng, tổng, trung bình hoặc danh sách thuộc tính đã biến đổi.
- Overload có map factory cho phép chọn `TreeMap`, `LinkedHashMap` hay cấu trúc Map phù hợp khi cần chính sách thứ tự cụ thể.
- Classifier phải trả khóa **khác null**. Muốn xử lý danh mục thiếu hoặc khác cách viết, phải thiết kế validation và chuẩn hóa rõ ràng.
- Đừng dựa vào thứ tự Map mặc định hoặc dùng `toMap` khi khóa có thể trùng. Hãy kiểm thử cả phân nhóm, thành viên, kiểu kết quả và bất biến số lượng.

Khi chọn đúng classifier, downstream và loại Map, bạn sẽ biến được một luồng bản ghi thành các nhóm dễ tra cứu, tổng hợp và hiển thị mà không cần tự viết nhiều vòng lặp quản lý danh sách theo khóa.
