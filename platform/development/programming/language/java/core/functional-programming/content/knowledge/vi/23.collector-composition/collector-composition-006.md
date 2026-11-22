# `reducing()`, `minBy()` và `maxBy()` phía sau collector khác

## 1. Mục tiêu: gom nhóm rồi rút gọn **bên trong từng nhóm**

Trong Java Stream API, một phép xử lý thường có hai cấp:

1. **Collector bên ngoài** quyết định cách phân vùng dữ liệu, chẳng hạn `groupingBy` theo danh mục sản phẩm hoặc `partitioningBy` theo điều kiện giá.
2. **Collector bên trong (downstream collector)** quyết định kết quả của từng nhóm: tổng tiền, phần tử nhỏ nhất, phần tử lớn nhất hoặc một giá trị đã rút gọn.

Các collector `Collectors.reducing(...)`, `Collectors.minBy(...)` và `Collectors.maxBy(...)` đặc biệt hữu ích ở **vị trí downstream** vì chúng không buộc phải tạo một `List` trung gian rồi duyệt lại.

Ví dụ ý tưởng:

```java
Map<String, Integer> revenueByCategory = products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                Collectors.reducing(
                        0,
                        p -> p.price() * p.quantity(),
                        Integer::sum)));
```

`Product::category` chọn nhóm cho từng `Product`. Trong mỗi nhóm, `reducing` biến mỗi sản phẩm thành doanh thu dòng đó (`price × quantity`), rồi cộng các giá trị bắt đầu từ `0`. Kết quả của toàn bộ `collect` là `Map<String, Integer>` — **mỗi khóa chỉ có một tổng**, không phải `Map<String,List<Product>>`.

Tương tự:

```java
Map<String, Optional<Product>> mostExpensive =
        products.stream().collect(Collectors.groupingBy(
                Product::category,
                Collectors.maxBy(Comparator.comparingInt(Product::price))));
```

Giá trị của mỗi nhóm là một `Optional<Product>` chứa sản phẩm có giá lớn nhất theo comparator. Dù `groupingBy` chỉ tạo nhóm từ những khóa thực sự xuất hiện, kiểu downstream `maxBy` vẫn là `Optional<Product>` vì nó cũng phải có kết quả hợp lệ trong trường hợp **không có phần tử** khi được kết hợp với collector bên ngoài khác.

Mục tiêu bài học: hiểu chữ ký và kết quả của ba collector, dùng chúng sau `groupingBy`/`partitioningBy`/`mapping` hoặc `collectingAndThen`, kiểm tra đúng giá trị rỗng và so sánh, tránh các bẫy về kiểu, thứ tự và hiệu năng.

## 2. Phân biệt `Stream.reduce()` và `Collectors.reducing()`

`Stream.reduce(...)` là **terminal operation** trực tiếp trên một Stream. Nó thu được **một** giá trị cho Stream đó:

```java
int sum = java.util.stream.Stream.of(2, 3, 5)
        .reduce(0, Integer::sum); // 10
```

`Collectors.reducing(...)` là **factory tạo Collector**. Nó chưa thực thi dữ liệu; collector này được truyền vào `collect`, hoặc làm downstream cho một collector khác:

```java
int sum = java.util.stream.Stream.of(2, 3, 5)
        .collect(java.util.stream.Collectors.reducing(0, Integer::sum));
// 10
```

Hai ví dụ trả cùng kết quả; với tổng số đơn giản, dùng `reduce` hoặc `IntStream.sum()` thường ngắn gọn và dễ hiểu hơn.

Giá trị đặc biệt của `Collectors.reducing` xuất hiện khi **phối hợp**:

```text
products.stream()
    │
    ▼
groupingBy(Product::category, downstream)
    ├── Books   → reducing(...) → tổng Books
    ├── Food    → reducing(...) → tổng Food
    ├── Office  → reducing(...) → tổng Office
    └── Tech    → reducing(...) → tổng Tech
                  │
                  ▼
             Map<Category, Result>
```

Nếu thực hiện `products.stream().reduce(...)` trực tiếp, bạn chỉ rút gọn toàn bộ Stream thành một giá trị, không tự sinh Map kết quả riêng cho từng danh mục. Với các downstream chuyên dụng như `summingInt`, `counting` hoặc `averagingInt`, bạn có thể chọn API rõ ý nghĩa hơn thay vì luôn dùng `reducing`.

## 3. Ba overload của `Collectors.reducing`

Có ba dạng phổ biến, và chúng **khác nhau cả về đầu vào và kiểu kết quả**.

### 3.1. `reducing(BinaryOperator<T>)` — không có identity

Chữ ký:

```java
static <T> Collector<T, ?, Optional<T>> reducing(
        java.util.function.BinaryOperator<T> op);
```

Collector này gộp các phần tử cùng kiểu `T` bằng phép toán `op`, nhưng vì không có giá trị đầu tiên khi nhóm rỗng, kết quả là `Optional<T>`.

```java
java.util.Optional<Integer> max = java.util.stream.Stream
        .of(2, 7, 4)
        .collect(java.util.stream.Collectors.reducing(Integer::max));

// Optional[7]
```

Nếu nguồn rỗng, kết quả là `Optional.empty()`. Khi ở trong `groupingBy`, kết quả của **mỗi nhóm** có kiểu `Optional<T>`:

```java
Map<String, Optional<Product>> latestByCategory =
        products.stream().collect(Collectors.groupingBy(
                Product::category,
                Collectors.reducing((a, b) ->
                        a.price() >= b.price() ? a : b)));
```

Đoạn này là minh họa, giả sử đã khai báo `Product`, `products`, `Map`, `Optional`, `Collectors`. Khi muốn chọn cực trị, nên dùng `maxBy(comparator)`/`minBy(comparator)` để quy tắc so sánh tường minh hơn. Hàm chọn bên trái khi giá bằng nhau như trên cũng cần xem xét chính sách tie và encounter order trước khi dùng trong xử lý song song.

### 3.2. `reducing(T identity, BinaryOperator<T>)` — cùng kiểu, có giá trị trung hòa

Chữ ký:

```java
static <T> Collector<T, ?, T> reducing(
        T identity,
        java.util.function.BinaryOperator<T> op);
```

`identity` là giá trị trung hòa của `op`, ví dụ `0` đối với cộng hoặc `1` đối với nhân. Với một Stream rỗng, collector trả `identity`, không phải `Optional.empty()`.

```java
int product = java.util.stream.Stream.of(2, 3, 4)
        .collect(java.util.stream.Collectors.reducing(
                1, (a, b) -> a * b));

// 24
```

Nếu downstream nhận `Product` trực tiếp từ `groupingBy`, bạn **không thể** gọi `reducing(0, Integer::sum)` rồi mong Java tự lấy `Product.price()`. Hai tham số dạng này dùng `T = Product` khi chưa biến đổi giá trị. Muốn rút gọn thuộc tính số, dùng overload ba tham số có `mapper` hoặc kết hợp `mapping`:

```java
// mapping biến Product thành Integer trước downstream reducing:
Map<String, Integer> sums = products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                Collectors.mapping(
                        Product::price,
                        Collectors.reducing(0, Integer::sum))));
```

Đây là đoạn minh họa ở bên trong class có import thích hợp. `mapping` trả các giá trị kiểu `Integer` để `reducing(0, Integer::sum)` dùng đúng kiểu.

### 3.3. `reducing(U identity, Function<T,U> mapper, BinaryOperator<U> op)`

Chữ ký:

```java
static <T, U> Collector<T, ?, U> reducing(
        U identity,
        java.util.function.Function<? super T, ? extends U> mapper,
        java.util.function.BinaryOperator<U> op);
```

Đây thường là dạng **thuận tiện nhất khi dùng phía sau `groupingBy`**. Nó gồm ba bước:

1. Dùng `mapper` biến một phần tử `T` thành giá trị `U`.
2. Tích lũy các giá trị `U` bằng `op`.
3. Dùng `identity` khi nhóm không có phần tử và khi khởi tạo rút gọn.

```java
Map<String, Integer> totalPrice = products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                Collectors.reducing(
                        0, Product::price, Integer::sum)));
```

Ở đây nguồn `Product` khác kiểu kết quả `Integer`. Chú ý đây là **ba tham số của `Collectors.reducing`** (`identity`, `mapper`, `op`), **khác** ba tham số của `Stream.reduce` (`identity`, `accumulator`, `combiner`). Chúng không có cùng chữ ký và không nên hoán đổi tên/hành vi.

| Dạng | Nhận phần tử | Kết quả | Khi dùng |
| --- | --- | --- | --- |
| `reducing(op)` | `T` | `Optional<T>` | Gộp không identity, kể cả min/max tự định nghĩa |
| `reducing(identity, op)` | `T` | `T` | Gộp các phần tử cùng kiểu |
| `reducing(identity, mapper, op)` | `T`, chuyển sang `U` | `U` | Tổng hợp thuộc tính khác kiểu nguồn |
| `Stream.reduce(identity, accumulator, combiner)` | `T`, trạng thái `U` | `U` | Terminal reduction trực tiếp trên toàn Stream |

## 4. `Collectors.minBy` và `Collectors.maxBy` là downstream của comparator

Chữ ký:

```java
static <T> Collector<T, ?, Optional<T>> minBy(
        java.util.Comparator<? super T> comparator);

static <T> Collector<T, ?, Optional<T>> maxBy(
        java.util.Comparator<? super T> comparator);
```

Một comparator so sánh hai phần tử `T`. `minBy` chọn phần tử nhỏ nhất; `maxBy` chọn phần tử lớn nhất theo thứ tự comparator quy định.

Với sản phẩm:

```java
Comparator<Product> byPrice =
        Comparator.comparingInt(Product::price);

Map<String, Optional<Product>> cheapest =
        products.stream().collect(Collectors.groupingBy(
                Product::category,
                Collectors.minBy(byPrice)));

Map<String, Optional<Product>> priciest =
        products.stream().collect(Collectors.groupingBy(
                Product::category,
                Collectors.maxBy(byPrice)));
```

- Khóa `Map` là danh mục.
- Giá trị là `Optional<Product>`, **không phải chính `Product`**.
- `minBy`/`maxBy` chọn cực trị **trong từng danh mục**, không phải cực trị toàn Stream.
- Comparator có thể dựa trên giá, ngày, độ ưu tiên, độ dài tên hoặc thuộc tính tổng hợp.
- Trường hợp nhiều phần tử **bằng nhau theo comparator** cần chính sách tie có chủ đích nếu quan tâm chính xác phần tử nào được chọn.

Dùng `Comparator.comparingInt(Product::price)` thay vì `(a, b) -> a.price() - b.price()`. Phép trừ trong comparator có thể tràn số nguyên khi giá trị quá lớn hoặc có số âm, làm sai thứ tự.

### Tie-breaker tạo chính sách chọn xác định

Giả sử hai sản phẩm có cùng giá, và bạn muốn phân định theo tên. Có thể dùng:

```java
Comparator<Product> byPriceThenName =
        Comparator.comparingInt(Product::price)
                  .thenComparing(Product::name);
```

`minBy` sẽ chọn sản phẩm **giá nhỏ hơn**, rồi tên **nhỏ hơn theo thứ tự từ điển** khi đồng giá. `maxBy` sẽ chọn sản phẩm **giá lớn hơn**, rồi tên **lớn hơn theo thứ tự từ điển** khi đồng giá.

Nếu muốn giá cao nhất nhưng tên *nhỏ nhất* khi đồng giá, cần một comparator khác với phần tie-breaker được đảo phù hợp; không nên mặc định `maxBy` luôn chọn tên đầu tiên.

## 5. Downstream bên trong `groupingBy` hoạt động như thế nào?

Xét cú pháp:

```java
Collectors.groupingBy(
        Product::category,
        Collectors.maxBy(byPriceThenName))
```

`groupingBy` làm việc ở lớp ngoài: tạo khóa category và phân phối mỗi Product vào nhóm thích hợp. Collector bên trong chỉ nhận các Product **của nhóm đang xét**.

Kết quả có cấu trúc:

```text
Books → Optional[Product đắt nhất thuộc Books]
Food  → Optional[Product đắt nhất thuộc Food]
Tech  → Optional[Product đắt nhất thuộc Tech]
```

Không có việc `maxBy` tính một sản phẩm đắt nhất toàn cục rồi gắn nó vào mọi khóa. Mỗi nhóm có trạng thái rút gọn của riêng mình.

Nếu bạn viết:

```java
products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                Collectors.toList()));
```

kết quả là `Map<String,List<Product>>`: giữ toàn bộ Product trong các danh sách. Với `maxBy`, `minBy` hoặc `reducing` bên trong, giá trị chỉ cần là một kết quả tổng hợp và không phải giữ toàn bộ phần tử nhóm trong danh sách kết quả.

`groupingBy` là terminal aggregation khi đặt trong `stream.collect(...)`, chứ không phải bước trung gian có thể `map` tiếp trên chính Stream cũ. Nếu muốn biến đổi Map sau khi thu thập, có thể duyệt `entrySet()` bằng Stream mới hoặc đặt downstream `collectingAndThen` như phần 8.

## 6. Ví dụ Java 17 hoàn chỉnh và kết quả kiểm thử

Bài toán thực hành sử dụng `Product` gồm `name`, `category`, `price`, `quantity`. Ta tính:

- Tổng giá niêm yết các sản phẩm trong mỗi danh mục bằng `reducing(0, Product::price, Integer::sum)`.
- Tổng doanh thu (`price × quantity`) theo danh mục bằng `reducing(0, mapper, Integer::sum)`.
- Sản phẩm rẻ nhất và đắt nhất trong mỗi danh mục bằng `minBy`/`maxBy`.
- Sản phẩm đắt nhất theo danh mục bằng `reducing(BinaryOperator.maxBy(...))` để so sánh cách viết.
- Tên sản phẩm rẻ nhất/đắt nhất dùng `collectingAndThen` chuyển `Optional<Product>` thành `String`.
- Sản phẩm đắt nhất trong hai phân vùng giá cao/thấp dùng `partitioningBy`.
- Kết quả Stream rỗng: `groupingBy` trả Map rỗng, còn `partitioningBy` vẫn có hai khóa Boolean và các `Optional.empty()` tương ứng.

Tệp Java 17 độc lập có tên **`DownstreamReducingDemo.java`**:

```java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.TreeMap;
import java.util.function.BinaryOperator;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class DownstreamReducingDemo {
    record Product(String name, String category,
                   int price, int quantity) {}

    static final Comparator<Product> BY_PRICE_THEN_NAME =
            Comparator.comparingInt(Product::price)
                    .thenComparing(Product::name);

    static List<Product> sample() {
        return List.of(
                new Product("Java", "Books", 120, 2),
                new Product("Clean Code", "Books", 150, 1),
                new Product("Tea", "Food", 40, 3),
                new Product("Coffee", "Food", 70, 2),
                new Product("Mouse", "Tech", 90, 1),
                new Product("Keyboard", "Tech", 200, 1),
                new Product("Pen", "Office", 15, 4));
    }

    static Map<String, Integer> sumPrices(Stream<Product> input) {
        return input.collect(Collectors.groupingBy(
                Product::category,
                TreeMap::new,
                Collectors.reducing(
                        0, Product::price, Integer::sum)));
    }

    static Map<String, Integer> revenues(Stream<Product> input) {
        return input.collect(Collectors.groupingBy(
                Product::category,
                TreeMap::new,
                Collectors.reducing(
                        0,
                        p -> p.price() * p.quantity(),
                        Integer::sum)));
    }

    static Map<String, Optional<Product>> cheapest(
            Stream<Product> input) {
        return input.collect(Collectors.groupingBy(
                Product::category,
                TreeMap::new,
                Collectors.minBy(BY_PRICE_THEN_NAME)));
    }

    static Map<String, Optional<Product>> priciest(
            Stream<Product> input) {
        return input.collect(Collectors.groupingBy(
                Product::category,
                TreeMap::new,
                Collectors.maxBy(BY_PRICE_THEN_NAME)));
    }

    static Map<String, Optional<Product>> priciestWithReducing(
            Stream<Product> input) {
        return input.collect(Collectors.groupingBy(
                Product::category,
                TreeMap::new,
                Collectors.reducing(
                        BinaryOperator.maxBy(BY_PRICE_THEN_NAME))));
    }

    static Map<String, String> minimumNames(Stream<Product> input) {
        return input.collect(Collectors.groupingBy(
                Product::category,
                TreeMap::new,
                Collectors.collectingAndThen(
                        Collectors.minBy(BY_PRICE_THEN_NAME),
                        opt -> opt.map(Product::name).orElse("NONE"))));
    }

    static Map<String, String> maximumNames(Stream<Product> input) {
        return input.collect(Collectors.groupingBy(
                Product::category,
                TreeMap::new,
                Collectors.collectingAndThen(
                        Collectors.maxBy(BY_PRICE_THEN_NAME),
                        opt -> opt.map(Product::name).orElse("NONE"))));
    }

    static Map<Boolean, Optional<Product>> pricePartitions(
            Stream<Product> input) {
        return input.collect(Collectors.partitioningBy(
                p -> p.price() >= 100,
                Collectors.maxBy(BY_PRICE_THEN_NAME)));
    }

    static void expect(Object wanted, Object actual, String name) {
        if (!Objects.equals(wanted, actual)) {
            throw new AssertionError(
                    name + ": expected=" + wanted + ", actual=" + actual);
        }
    }

    static void runTests() {
        List<Product> products = sample();
        Map<String, Integer> expectedPrices = Map.of(
                "Books", 270,
                "Food", 110,
                "Office", 15,
                "Tech", 290);
        Map<String, Integer> expectedRevenue = Map.of(
                "Books", 390,
                "Food", 260,
                "Office", 60,
                "Tech", 290);

        expect(expectedPrices,
                sumPrices(products.stream()), "sum prices");
        expect(expectedRevenue,
                revenues(products.stream()), "revenues");
        expect(expectedRevenue,
                revenues(products.parallelStream()),
                "parallel revenues");

        expect(Map.of(
                "Books", "Java",
                "Food", "Tea",
                "Office", "Pen",
                "Tech", "Mouse"),
                minimumNames(products.stream()), "minimum names");

        expect(Map.of(
                "Books", "Clean Code",
                "Food", "Coffee",
                "Office", "Pen",
                "Tech", "Keyboard"),
                maximumNames(products.stream()), "maximum names");

        expect(priciest(products.stream()),
                priciestWithReducing(products.stream()),
                "maxBy equals reducing max");

        Map<String, Optional<Product>> min =
                cheapest(products.stream());
        expect("Java",
                min.get("Books").orElseThrow().name(),
                "minimum Books");

        Map<Boolean, Optional<Product>> partitions =
                pricePartitions(products.stream());
        expect("Keyboard",
                partitions.get(true).orElseThrow().name(),
                "expensive partition maximum");
        expect("Mouse",
                partitions.get(false).orElseThrow().name(),
                "cheap partition maximum");

        expect(Map.of(),
                sumPrices(Stream.<Product>empty()),
                "empty grouping");
        expect(Map.of(),
                cheapest(Stream.<Product>empty()),
                "empty grouping with Optional");
        Map<Boolean, Optional<Product>> emptyPartitions =
                pricePartitions(Stream.<Product>empty());
        expect(true, emptyPartitions.containsKey(true),
                "true partition exists");
        expect(true, emptyPartitions.containsKey(false),
                "false partition exists");
        expect(Optional.empty(), emptyPartitions.get(true),
                "empty true partition");
        expect(Optional.empty(), emptyPartitions.get(false),
                "empty false partition");

        // Mỗi Product vẫn giữ nguyên; các kết quả nhóm chỉ đọc.
        expect(7, products.size(), "input unchanged");
    }

    public static void main(String[] args) {
        runTests();
        List<Product> products = sample();

        System.out.println("sumPrices="
                + sumPrices(products.stream()));
        System.out.println("revenues="
                + revenues(products.stream()));
        System.out.println("minNames="
                + minimumNames(products.stream()));
        System.out.println("maxNames="
                + maximumNames(products.stream()));
        System.out.println("maxViaReducingBooks="
                + priciestWithReducing(products.stream())
                        .get("Books").orElseThrow().name());

        Map<Boolean, Optional<Product>> p =
                pricePartitions(products.stream());
        System.out.println("highPartitionMax="
                + p.get(true).orElseThrow().name());
        System.out.println("lowPartitionMax="
                + p.get(false).orElseThrow().name());

        Map<Boolean, Optional<Product>> empty =
                pricePartitions(Stream.<Product>empty());
        System.out.println("emptyFalse=" + empty.get(false).isEmpty());
        System.out.println("emptyTrue=" + empty.get(true).isEmpty());
        System.out.println("tests=PASS");
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac DownstreamReducingDemo.java
java DownstreamReducingDemo
```

Stdout dự kiến:

```text
sumPrices={Books=270, Food=110, Office=15, Tech=290}
revenues={Books=390, Food=260, Office=60, Tech=290}
minNames={Books=Java, Food=Tea, Office=Pen, Tech=Mouse}
maxNames={Books=Clean Code, Food=Coffee, Office=Pen, Tech=Keyboard}
maxViaReducingBooks=Clean Code
highPartitionMax=Keyboard
lowPartitionMax=Mouse
emptyFalse=true
emptyTrue=true
tests=PASS
```

### Phân tích giá trị

| Danh mục | Sản phẩm | Tổng giá | Doanh thu |
| --- | --- | ---: | ---: |
| Books | Java 120 × 2; Clean Code 150 × 1 | 270 | 390 |
| Food | Tea 40 × 3; Coffee 70 × 2 | 110 | 260 |
| Office | Pen 15 × 4 | 15 | 60 |
| Tech | Mouse 90 × 1; Keyboard 200 × 1 | 290 | 290 |
| **Tổng** | 7 sản phẩm | **685** | **1.000** |

`sumPrices` cộng **giá niêm yết từng dòng**, còn `revenues` cộng **giá nhân số lượng** của từng dòng. Hai kết quả khác nhau theo hợp đồng nghiệp vụ; đừng nhầm `summingInt(Product::price)` với doanh thu.

Trong ví dụ, `TreeMap::new` đảm bảo **thứ tự khóa danh mục** ở output `Map`, và `Comparator.comparingInt(...).thenComparing(...)` quy định lựa chọn khi có giá bằng nhau. Không nên phụ thuộc vào thứ tự duyệt `HashMap` mặc định hoặc chọn kết quả tình cờ ở ca tie.

Chương trình dùng `expect` ném `AssertionError` nếu kết quả khác kỳ vọng, không phụ thuộc tùy chọn `java -ea`. Khi muốn xác minh tính chính xác thật trên môi trường của bạn, hãy dùng đúng JDK 17+ với lệnh `javac`/`java` ở trên.

## 7. `partitioningBy(..., minBy/maxBy)` và trường hợp một nhánh rỗng

Không chỉ `groupingBy` mới nhận downstream. `Collectors.partitioningBy` chia dữ liệu thành **hai nhóm Boolean** theo một predicate:

```java
Map<Boolean, Optional<Product>> byExpensive =
        products.stream().collect(
                Collectors.partitioningBy(
                        p -> p.price() >= 100,
                        Collectors.maxBy(BY_PRICE_THEN_NAME)));
```

Trong ví dụ chính, `true` là nhóm có giá từ 100 trở lên, sản phẩm đắt nhất là `Keyboard` (200); `false` là nhóm giá dưới 100, đắt nhất là `Mouse` (90).

Sự khác biệt quan trọng:

- `groupingBy(classifier, downstream)` **không tạo khóa** của nhóm chưa từng xuất hiện. Với Stream rỗng, Map rỗng.
- `partitioningBy(predicate, downstream)` **có cả hai khóa** `true` và `false`, kể cả khi nhóm tương ứng rỗng. Vì `maxBy` trả `Optional`, nhóm rỗng có giá trị `Optional.empty()`.

Nếu dùng `partitioningBy(predicate, reducing(0, mapper, Integer::sum))`, bên rỗng sẽ có tổng **`0`** (identity), không phải `Optional.empty()`. Sự khác biệt này giúp bạn lựa chọn downstream dựa trên điều muốn diễn đạt: **“không tồn tại cực trị”** hay **“tổng của nhóm rỗng bằng 0”**.

Cũng không nên dùng `map.get(true)` rồi gọi `.get()` trực tiếp trên `Optional` mà không kiểm tra, vì có thể ném `NoSuchElementException` khi nhóm không có phần tử. Dùng `ifPresent`, `orElse`, `orElseGet`, `map`, hoặc `orElseThrow` khi việc vắng mặt được xem là bất thường theo hợp đồng.

## 8. `collectingAndThen` kết hợp với `minBy/maxBy`

Đầu ra `Optional<Product>` là đúng với ngữ nghĩa cực trị, nhưng đôi khi giao diện chỉ cần **tên** sản phẩm có giá nhỏ nhất/lớn nhất. `Collectors.collectingAndThen(downstream, finisher)` cho phép biến đổi **kết quả cuối** của downstream thành một kiểu khác:

```java
Map<String, String> nameOfCheapest =
        products.stream().collect(Collectors.groupingBy(
                Product::category,
                TreeMap::new,
                Collectors.collectingAndThen(
                        Collectors.minBy(BY_PRICE_THEN_NAME),
                        optional -> optional
                                .map(Product::name)
                                .orElse("NONE"))));
```

Sơ đồ:

```text
Product trong một danh mục
          │
          ▼
    minBy(comparator)
          │
          ▼
    Optional<Product>
          │
          ▼
  collectingAndThen:
  opt.map(Product::name).orElse("NONE")
          │
          ▼
        String
```

Trong `groupingBy`, một khóa xuất hiện có ít nhất một phần tử, nên nếu classifier và nguồn hợp lệ thì `minBy` của khóa ấy không rỗng. Nhưng finisher vẫn cần có ngữ nghĩa rõ khi được tái sử dụng với collector khác hoặc được gọi trên nhóm rỗng, như ở `partitioningBy`. Ở đây, `"NONE"` là chính sách hiển thị minh họa; nếu việc thiếu cực trị là lỗi, đừng dùng placeholder che thông tin mà hãy xử lý như một trạng thái nghiệp vụ.

**Lưu ý:** `collectingAndThen` chạy **sau khi downstream kết thúc tích lũy**, không phải với mỗi phần tử nguồn. Nếu mục đích là biến đổi từng phần tử trước hoặc trong lúc thu thập nhóm, hãy dùng `map` của Stream hoặc downstream `Collectors.mapping`.

## 9. `mapping` kết hợp với `reducing`

Có hai cách tương đương về ý nghĩa để cộng thuộc tính giá của mỗi nhóm:

```java
Map<String, Integer> first = products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                Collectors.reducing(0,
                        Product::price, Integer::sum)));
```

Và:

```java
Map<String, Integer> second = products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                Collectors.mapping(
                        Product::price,
                        Collectors.reducing(0, Integer::sum))));
```

Ở cách thứ nhất, `reducing` tích hợp bước `mapper`. Ở cách thứ hai, `mapping` chuyển mỗi `Product` thành `Integer` rồi `reducing` cộng các số. Cả hai giúp làm rõ rằng nhóm được xác định trên **Product** trước khi chọn `price`.

Với tổng đơn giản, phương án này thậm chí ngắn gọn hơn:

```java
Map<String, Integer> sums = products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                Collectors.summingInt(Product::price)));
```

**Hãy ưu tiên collector chuyên dụng** (`counting`, `summingInt`, `summingLong`, `averagingInt`, `summarizingInt`, v.v.) khi nó thể hiện đúng mục đích. Dùng `reducing` cho bài toán thực sự là kết hợp theo một phép toán có identity/mapper/op rõ ràng, hoặc khi cần cấu trúc tổng hợp mà các collector có sẵn chưa diễn tả gọn.

## 10. `minBy`/`maxBy` so với cách nhóm rồi duyệt lại

Cách hai bước:

```java
Map<String, List<Product>> grouped = products.stream()
        .collect(Collectors.groupingBy(Product::category));

Map<String, Optional<Product>> maxByCategory =
        new java.util.HashMap<>();

grouped.forEach((category, list) ->
        maxByCategory.put(
                category,
                list.stream().max(BY_PRICE_THEN_NAME)));
```

Cách này hợp lệ nếu **cần giữ đầy đủ danh sách** vì mục đích khác. Nhưng nếu bài toán chỉ cần phần tử đắt nhất, nó tạo nhiều danh sách nhóm rồi lại quét để tìm cực trị.

Downstream trực tiếp:

```java
Map<String, Optional<Product>> maxByCategory =
        products.stream().collect(
                Collectors.groupingBy(
                        Product::category,
                        Collectors.maxBy(BY_PRICE_THEN_NAME)));
```

thể hiện ý định trong một phép collect và không phải tạo `List<Product>` cho mỗi nhóm ở kết quả. Tuy nhiên, không nên khẳng định mọi tình huống downstream luôn nhanh hơn theo một con số cố định; chi phí phụ thuộc dữ liệu, collector, số khóa và đặc tính song song. Đánh giá tính đúng đắn và bộ nhớ trước, benchmark nếu hiệu năng là yêu cầu thực.

## 11. Quy tắc của phép rút gọn: identity và tính kết hợp

`reducing(identity, mapper, op)` dùng một phép kết hợp `op` trên các giá trị `U`. Để có hành vi hợp lệ khi rút gọn theo nhóm và thực thi song song, `identity` phải là phần tử trung hòa, còn phép kết hợp phải có **tính kết hợp** (*associativity*).

Với phép cộng:

```text
identity = 0
combine(a, b) = a + b

combine(0, x) = x
combine(x, 0) = x
combine(combine(a, b), c) = combine(a, combine(b, c))
```

`Integer::sum` phù hợp về ngữ nghĩa cộng nguyên Java. Tuy nhiên, với giá trị vượt khả năng biểu diễn của `int`, tổng có thể overflow; bài toán tiền/giá lớn cần chọn kiểu và chính sách số học thích hợp, ví dụ `long`, `BigInteger`, `BigDecimal`, hoặc kiểm tra overflow.

**Phản ví dụ:**

```java
// Không tuân thủ hợp đồng rút gọn cho kết quả ổn định:
int result = java.util.stream.Stream.of(10, 3, 2)
        .collect(java.util.stream.Collectors.reducing(
                0, (a, b) -> a - b));
```

Phép trừ không có `0` là identity hai phía (`0 - x` không bằng `x`), đồng thời không kết hợp được. Các nhóm có thể được gộp theo cách khác nhau khi song song, nên kết quả không được bảo đảm giữ ý nghĩa mong muốn.

**Không dùng object mutable chung làm identity rồi sửa trực tiếp trong accumulator** của `reducing`. Nếu cần thêm các phần tử vào `ArrayList`, `HashMap` hoặc container mutable, nên dùng `collect` với supplier tạo container độc lập hoặc collector có sẵn, thay vì dùng `reducing` với tác dụng phụ không an toàn. Trong xử lý song song, yếu tố này đặc biệt quan trọng.

### `minBy` và `maxBy` cũng cần comparator ổn định

Comparator phải phản ánh một quy tắc nhất quán trong khi collector làm việc. Không dùng comparator có trạng thái thay đổi, đọc biến mutable đang bị sửa hoặc sinh số ngẫu nhiên mỗi lần so sánh. Nếu comparator không nhất quán, “nhỏ nhất/lớn nhất” có thể trở thành khái niệm mơ hồ, nhất là khi phân nhóm và rút gọn song song.

Khi giá bằng nhau, hãy chỉ định tie-breaker nếu đầu ra yêu cầu một Product cụ thể. Nếu chỉ cần mức giá cao nhất/thấp nhất mà không quan tâm bản ghi đại diện, có thể rút gọn trực tiếp giá bằng `mapping` + `reducing`, hoặc dùng `summing`/`summarizing`/collector chuyên biệt khi phù hợp.

## 12. Null, nhóm rỗng và Optional

### Không cho `groupingBy` nhận khóa phân loại `null`

`Collectors.groupingBy` không chấp nhận classifier trả `null`:

```java
// Nếu category() == null thì groupingBy gây NullPointerException.
products.stream()
        .collect(Collectors.groupingBy(Product::category));
```

Nếu `category` có thể thiếu, hãy định nghĩa chính sách: từ chối dữ liệu, đưa vào nhóm `"UNKNOWN"` hay dùng kiểu khóa biểu diễn trạng thái riêng. Không có cách nào mà `minBy`/`maxBy` downstream tự sửa khóa `null` ở bước outer grouping.

### `Optional.empty()` khác `null` của Map

`Map<String, Optional<Product>>` có thể có hai tình huống:

- **Không có khóa**: `map.get("Missing")` trả `null` vì danh mục ấy không được tạo bởi `groupingBy`.
- **Có khóa nhưng Optional rỗng**: thường gặp với `partitioningBy` khi nhánh Boolean không có phần tử, hoặc khi bạn áp dụng một downstream có thể cho kết quả rỗng sau khi lọc.

Vì vậy, lời gọi:

```java
Optional<Product> maybe =
        grouped.getOrDefault("Missing", Optional.empty());
```

là cách hợp lệ để xử lý cả khóa không tồn tại và trường hợp Optional rỗng, miễn `grouped` là `Map<String, Optional<Product>>`.

Không viết `grouped.get("Missing").get()` khi chưa xác nhận khóa tồn tại và Optional có giá trị. Với rút gọn không identity, thiết kế API nên thể hiện **khả năng không có kết quả**. Với tổng có identity, chọn một identity hợp lý như 0 và hiểu rõ vì sao tổng nhóm rỗng có giá trị đó.

### Null ở phần tử hoặc kết quả phép mapper

Nếu phần tử của Stream có thể `null`, `Product::category` hoặc comparator truy cập thuộc tính có thể ném `NullPointerException`. Hãy validate, chuyển đổi hoặc lọc có chủ đích trước khi grouping. Nếu việc thiếu phần tử là lỗi cần báo, đừng âm thầm bỏ qua.

`Collectors.minBy`/`maxBy` trả `Optional` của kết quả; Optional không cho phép chứa một giá trị `null`. Tránh để comparator hoặc quy trình nhập dữ liệu dựa vào việc coi `null` là một Product hợp lệ. Với mapper của `reducing`, cũng cần bảo đảm phép toán gộp xử lý rõ kiểu và trạng thái `null`; nếu nghiệp vụ cần ghi nhận lỗi, hãy đưa kết quả thất bại vào mô hình dữ liệu, không làm một phép tổng bị mất phần tử mà không có dấu vết.

## 13. Thứ tự, song song và đặc tính Collector

`groupingBy` mặc định **không cam kết loại Map hay thứ tự khóa**. Trong ví dụ đầy đủ, `TreeMap::new` cố ý bảo đảm thứ tự khóa `Books`, `Food`, `Office`, `Tech` để stdout ổn định. Nếu muốn thứ tự theo lần gặp khóa trong dữ liệu tuần tự, cân nhắc `LinkedHashMap::new`.

`minBy` và `maxBy` không tự sắp xếp toàn bộ mỗi nhóm: chúng tìm phần tử cực trị theo comparator. Khi bạn cần **nhiều phần tử đứng đầu** thay vì chỉ một cực trị, `maxBy` không đủ; dùng collector/thuật toán phù hợp cho top-K.

Khi dùng `parallelStream()`:

- Tránh cập nhật trực tiếp `ArrayList`, `HashMap` hoặc biến đếm dùng chung từ `map`, `filter`, classifier hay comparator.
- Đảm bảo phép rút gọn có identity trung hòa và phép kết hợp hợp lệ.
- Đảm bảo comparator ổn định; tie-breaker giúp kết quả chọn bản ghi không phụ thuộc vào tình cờ của cách gộp.
- Không dựa vào số lần gọi lambda hay thứ tự gọi combiner để suy luận kết quả.
- Kết quả song song không mặc nhiên nhanh hơn; số nhóm ít, nguồn nhỏ và chi phí merge có thể làm overhead lớn hơn lợi ích.

`groupingByConcurrent` có đặc tính concurrent và unordered, dùng khi thực sự cần nhóm đồng thời theo điều kiện phù hợp. Nó có ràng buộc thứ tự khác `groupingBy`; không thay một cách máy móc khi ứng dụng dựa trên encounter order. Downstream `reducing`, `minBy`, `maxBy` có thể được phối hợp với grouping collector theo đúng hợp đồng, nhưng việc chạy concurrent cần xem xét thread safety và hiệu năng thực tế.

## 14. Những sai lầm thường gặp

**Sai 1 — dùng `Stream.reduce` thay cho downstream.** `Stream.reduce(...)` trả một kết quả toàn Stream; `Collectors.reducing(...)` trả một Collector để đặt sau `groupingBy` hay `partitioningBy`. Không dùng hai phương thức như thể chúng có cùng chữ ký.

**Sai 2 — gọi `reducing(0, Integer::sum)` trực tiếp trên nhóm `Product`.** Kiểu phần tử downstream vẫn là `Product` nếu chưa `mapping`. Dùng `reducing(0, Product::price, Integer::sum)` hoặc `mapping(Product::price, reducing(0,Integer::sum))`.

**Sai 3 — quên `Optional` ở `minBy` và `maxBy`.** `Map<K, Optional<Product>>` không thể tự gán cho `Map<K, Product>`. Hãy xử lý khả năng rỗng một cách tường minh hoặc dùng `collectingAndThen`.

**Sai 4 — nhầm thứ tự in Map với thứ tự giá.** `TreeMap` sắp xếp **khóa danh mục**, không sắp xếp sản phẩm theo giá; comparator của min/max mới quyết định cực trị trong từng nhóm.

**Sai 5 — xử lý tie không nhất quán.** `maxBy(comparingInt(Product::price))` không quy định lựa chọn cụ thể giữa hai sản phẩm đồng giá. Nếu cần determinism, thêm tie-breaker rõ ràng.

**Sai 6 — dùng comparator bằng phép trừ.** `(a,b) -> a.price()-b.price()` có nguy cơ overflow; dùng `comparingInt`.

**Sai 7 — dùng identity không trung hòa hoặc op không kết hợp.** Phép rút gọn có thể cho kết quả sai hoặc khác nhau khi song song.

**Sai 8 — dùng `Optional.get()` không kiểm tra.** Một partition rỗng cho `Optional.empty()` và `.get()` ném `NoSuchElementException`.

**Sai 9 — cộng tiền qua kiểu số không đủ rộng.** `price * quantity` có thể tràn `int` **trước khi** được cộng. Nếu dùng `long`, hãy chuyển kiểu trước phép nhân: `(long) p.price() * p.quantity()`, rồi dùng `Long::sum` và identity `0L`.

**Sai 10 — giữ tất cả sản phẩm trong nhóm chỉ để tìm min/max.** Nếu chỉ cần một cực trị/tổng, downstream trực tiếp thường làm code ngắn hơn và tránh giữ List nhóm trong kết quả.

**Sai 11 — hiểu `collectingAndThen` là biến đổi từng phần tử.** Finisher chạy sau khi downstream xong; chuyển từng `Product` sang giá/nhãn thì dùng `mapping` hoặc mapper của `reducing`.

**Sai 12 — không phân biệt nhóm vắng mặt và nhóm rỗng.** `groupingBy` không tạo nhóm cho khóa không xuất hiện; `partitioningBy` tạo cả true và false. Thiết kế code đọc Map dựa trên hợp đồng phù hợp.

## 15. Cách chọn collector theo đầu ra cần thiết

| Yêu cầu | Downstream nên xem xét | Kết quả trong từng nhóm |
| --- | --- | --- |
| Giữ nguyên các phần tử | `toList()` | `List<T>` |
| Chỉ cần số phần tử | `counting()` | `Long` |
| Tổng một thuộc tính `int` | `summingInt(mapper)` | `Integer` |
| Tổng theo phép tùy chọn | `reducing(identity, mapper, op)` | `U` |
| Gộp trực tiếp các `T` không identity | `reducing(op)` | `Optional<T>` |
| Sản phẩm có giá nhỏ nhất | `minBy(comparator)` | `Optional<T>` |
| Sản phẩm có giá lớn nhất | `maxBy(comparator)` | `Optional<T>` |
| Tên của sản phẩm giá lớn nhất | `collectingAndThen(maxBy(...), finisher)` | `String` hoặc kiểu đầu ra khác |
| Chỉ lấy thuộc tính trước khi gộp | `mapping(mapper, downstream)` | Tùy downstream |
| Đếm, min, max, sum, average số | `summarizingInt/Long/Double(mapper)` | Đối tượng thống kê |

Nếu chỉ cần **một** tổng trên toàn Stream, cân nhắc `mapToInt(...).sum()` hoặc `reduce` terminal. Nếu cần **cùng phép tổng trên mỗi nhóm**, dùng `groupingBy` kết hợp downstream collector.

## 16. Bài tập và kiểm thử bổ sung

1. Với danh sách `Product` trong phần 6, viết `groupingBy(Product::category, reducing(0, Product::quantity, Integer::sum))` để tính tổng số lượng từng danh mục. Dự kiến Books=3, Food=5, Office=4, Tech=2; tổng là 14.
2. Viết `groupingBy(..., mapping(Product::price, reducing(0,Integer::sum)))` và chứng minh kết quả bằng cách dùng overload ba tham số `reducing(0,Product::price,Integer::sum)`.
3. Thêm một sản phẩm `new Product("Java Mini", "Books", 120, 1)`. `minBy` với comparator giá-rồi-tên sẽ chọn tên nào? Giải thích chính sách so sánh khi giá bằng nhau.
4. Dùng `partitioningBy(p -> p.price() >= 100, minBy(BY_PRICE_THEN_NAME))`, dự đoán sản phẩm có giá thấp nhất ở hai nhánh. Kiểm thử cả trường hợp nguồn không có sản phẩm giá cao.
5. Thêm danh mục `Toys` chỉ có một phần tử. Xác nhận `minBy` và `maxBy` trả cùng sản phẩm; sau đó kiểm thử Map không có khóa `Toys` khi không có đầu vào thuộc danh mục ấy.
6. Thay `int price` bằng `long price` và chuyển doanh thu sang `long` để tránh tràn nhân `int`. Nêu rõ vị trí chuyển kiểu cần đặt **trước** phép nhân.
7. Viết test cho nguồn rỗng: `groupingBy(maxBy(...))` trả `{}`, còn `partitioningBy(maxBy(...))` có cả `true` và `false` với `Optional.empty()`.
8. Viết comparator có tie-breaker theo tên **tăng dần** trong khi chọn giá **giảm dần**. Kiểm tra hai sản phẩm đồng giá và so sánh kết quả với `maxBy(BY_PRICE_THEN_NAME)`.
9. Thử `revenues(products.parallelStream())` rồi so sánh với tuần tự. Giải thích vì sao cộng `int` trong phạm vi không tràn và không có trạng thái mutable ngoài sẽ cho cùng kết quả.
10. Nếu cần cả số lượng, tổng giá, giá thấp nhất và cao nhất trong cùng nhóm, cân nhắc `summarizingInt(Product::price)` và nêu ưu điểm so với tính bốn Map riêng biệt.

Khi kiểm thử, không chỉ so số lượng nhóm: phải kiểm tra **đúng khóa, đúng cực trị, đúng tổng, đúng tie-breaker và đúng trường hợp rỗng**. Với API dùng `Optional`, hãy kiểm tra rõ khi nào là không có nhóm và khi nào là nhóm không có phần tử phù hợp.

## 17. Tổng kết

`Collectors.reducing`, `Collectors.minBy` và `Collectors.maxBy` là những downstream collector quan trọng khi cần **rút gọn từng nhóm/phân vùng**:

- `reducing(op)` không có identity nên trả `Optional<T>`.
- `reducing(identity, op)` gộp các phần tử cùng kiểu và trả `T`.
- `reducing(identity, mapper, op)` chuyển từng `T` thành `U` rồi gộp, trả `U`.
- `minBy(comparator)` và `maxBy(comparator)` chọn cực trị theo quy tắc so sánh, luôn trả `Optional<T>`.
- `groupingBy` tạo nhóm **chỉ cho các khóa xuất hiện**; `partitioningBy` tạo **cả hai khóa Boolean**, kể cả khi một bên rỗng.
- `mapping` cho phép biến đổi từng phần tử downstream; `collectingAndThen` biến đổi kết quả **sau** khi collector bên trong hoàn thành.

Thiết kế tốt cần quan tâm đến identity trung hòa, tính kết hợp, comparator ổn định, kiểu số, `Optional`, thứ tự Map và chính sách xử lý dữ liệu thiếu. Hãy chọn downstream thể hiện đúng loại kết quả của từng nhóm thay vì mặc định luôn thu thập mọi phần tử vào một `List`.
