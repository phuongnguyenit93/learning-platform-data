# Reduce, collect và lựa chọn phép tổng hợp

Trong Java 27, **Stream API** cho phép xây dựng các pipeline xử lý dữ liệu theo hướng khai báo: lọc, biến đổi, nhóm và tổng hợp. Khi cần chuyển nhiều phần tử thành một kết quả, hai nhóm công cụ phổ biến là `reduce(...)` và `collect(...)`. Chúng đều là **terminal operations**, nhưng cách tích lũy và mục đích thiết kế khác nhau:

- **`reduce`** kết hợp các giá trị thành một kết quả bằng phép toán có tính kết hợp, ví dụ cộng tổng, nhân tích hoặc tính tổng `BigDecimal`.
- **`collect`** dùng một bộ tích lũy có cấu trúc, thường là container có thể thay đổi trong quá trình xử lý, để tạo danh sách, tập hợp, map, bảng thống kê hay kết quả nhóm.
- **Các terminal operation chuyên dụng** như `count()`, `sum()`, `min()`, `max()` và `average()` diễn đạt trực tiếp những phép tổng hợp phổ biến.

Mục tiêu của bài là chọn được phép tổng hợp phù hợp với dữ liệu, xử lý đúng trường hợp stream rỗng, tránh lỗi với `parallelStream()`, và tận dụng các `Collector` có sẵn của Java 27 thay vì tự viết vòng lặp hoặc shared mutable state không cần thiết.

## 1. Vị trí của reduce và collect trong một Stream pipeline

Một pipeline thường có ba phần:

```text
Nguồn dữ liệu -> Intermediate operations -> Terminal operation
  List/array       filter/map/sorted          reduce/collect/sum/count
```

Ví dụ:

```java
import java.util.List;

var prices = List.of(10, 20, 30, 40);

int sum = prices.stream()
    .filter(price -> price >= 20)
    .mapToInt(Integer::intValue)
    .sum();

System.out.println(sum); // 90
```

`filter` tạo ra một bước trung gian có tính **lazy**; dữ liệu chỉ được xử lý khi `sum()` bắt đầu chạy. Sau một terminal operation, cùng một đối tượng `Stream` không được sử dụng lại để tính tiếp:

```java
var stream = prices.stream();

long count = stream.count();
// stream.reduce(0, Integer::sum); // Không được dùng lại stream đã tiêu thụ

int total = prices.stream().mapToInt(Integer::intValue).sum();
```

Muốn tính nhiều kết quả riêng, hãy tạo stream mới từ nguồn dữ liệu (hoặc dùng `Collectors.teeing` khi hai phép tổng hợp có thể gộp trong một lần thu thập).

## 2. reduce: gộp các phần tử thành một giá trị

`Stream<T>` cung cấp ba overload chính của `reduce`:

| Overload | Kết quả | Trường hợp phù hợp |
|---|---|---|
| `reduce(BinaryOperator<T>)` | `Optional<T>` | Không muốn tự chọn giá trị đồng nhất; cần xử lý stream rỗng |
| `reduce(T identity, BinaryOperator<T>)` | `T` | Các phần tử và kết quả cùng kiểu, có identity hợp lệ |
| `reduce(U identity, BiFunction<U,T,U>, BinaryOperator<U>)` | `U` | Tích lũy thành kiểu kết quả khác với kiểu phần tử |

Trong hai biểu diễn rút gọn của bảng, Java cho phép wildcard như `? super T`; hãy xem Javadoc khi cần chữ ký generic đầy đủ.

### 2.1. reduce có identity

```java
var numbers = List.of(2, 3, 5);

int total = numbers.stream()
    .reduce(0, Integer::sum);

int product = numbers.stream()
    .reduce(1, (a, b) -> a * b);

System.out.println(total);   // 10
System.out.println(product); // 30
```

`0` là identity cho phép cộng, còn `1` là identity cho phép nhân:

```text
0 + x == x
1 * x == x
```

Với stream rỗng, overload này trả về identity:

```java
int total = java.util.stream.Stream.<Integer>empty()
    .reduce(0, Integer::sum);

System.out.println(total); // 0
```

Không phải lúc nào một giá trị mặc định cũng có ý nghĩa nghiệp vụ. Ví dụ, dùng `0` làm “điểm cao nhất” có thể sai nếu dữ liệu cho phép điểm âm. Khi không có identity tự nhiên, hãy chọn overload trả về `Optional`.

### 2.2. reduce không có identity: Optional

```java
var scores = List.of(72, 95, 84);

var best = scores.stream().reduce(Integer::max);

best.ifPresent(score ->
    System.out.println("Điểm cao nhất: " + score)
);
```

Kết quả là `Optional<Integer>` vì stream có thể không chứa phần tử nào:

```java
var none = java.util.stream.Stream.<Integer>empty()
    .reduce(Integer::max);

System.out.println(none.isEmpty()); // true
```

Nên xử lý rõ trường hợp rỗng bằng `orElse`, `orElseThrow`, `ifPresent` hoặc logic nghiệp vụ thích hợp; không gọi `get()` một cách vô điều kiện.

Đối với bài toán cực trị, `stream.max(comparator)` hoặc `stream.min(comparator)` thường thể hiện ý định tốt hơn `reduce` với `Math.max` tự viết:

```java
var longest = List.of("A", "Java", "Streams").stream()
    .max(java.util.Comparator.comparingInt(String::length));

System.out.println(longest.orElse("")); // Streams
```

### 2.3. reduce ba tham số: kết quả khác kiểu nguồn

Giả sử nguồn chứa `String` nhưng kết quả là tổng chiều dài kiểu `long`:

```java
var words = List.of("Java", "Stream", "API");

long totalLength = words.stream().reduce(
    0L,
    (sum, word) -> sum + word.length(),
    Long::sum
);

System.out.println(totalLength); // 13
```

Ba đối số lần lượt là:

1. **Identity**: `0L`, giá trị bắt đầu và giá trị trung hòa khi ghép các kết quả từng phần.
2. **Accumulator**: `(sum, word) -> sum + word.length()`, gộp một phần tử nguồn vào giá trị kết quả.
3. **Combiner**: `Long::sum`, kết hợp hai kết quả trung gian, đặc biệt quan trọng khi xử lý parallel.

Với bài toán này, cách viết chuyên dụng thường rõ hơn và tránh boxing của `Long` trong reduce tổng quát:

```java
long totalLength = words.stream()
    .mapToLong(String::length)
    .sum();
```

Dùng overload ba tham số khi bạn cần cấu trúc gộp khác kiểu và không có terminal operation chuyên dụng dễ hiểu hơn.

## 3. Hợp đồng để reduce cho kết quả đúng

Để việc gộp có thể được chia nhỏ rồi kết hợp lại, hàm tích lũy cần tuân thủ những quy tắc quan trọng.

### 3.1. Phép kết hợp phải có tính associative

Với một toán tử `op`, tính kết hợp là:

```text
(a op b) op c == a op (b op c)
```

Phép cộng số nguyên (nếu chỉ xét phép toán Java với cùng kiểu số) và phép nối chuỗi là các ví dụ có tính kết hợp. Phép trừ không có tính kết hợp:

```text
(10 - 4) - 2 = 4
10 - (4 - 2) = 8
```

Ví dụ không nên dùng:

```java
// Không phù hợp cho phép reduce song song:
// Kết quả phụ thuộc vào cách nhóm các phần tử.
var result = List.of(10, 4, 2).parallelStream()
    .reduce(0, (a, b) -> a - b);
```

Không dựa vào một kết quả quan sát được của ví dụ trên; các phép chia nhóm có thể khiến giá trị thay đổi. Nếu nghiệp vụ cần phép trừ theo đúng thứ tự, hãy biểu diễn nó bằng phép xử lý có thứ tự rõ ràng thay vì giả định `parallel reduce` sẽ đi theo một thứ tự cố định.

### 3.2. Identity phải thực sự trung hòa

Với overload hai tham số, `identity` phải là giá trị trung hòa của accumulator:

```java
int correct = List.of(1, 2, 3).stream()
    .reduce(0, Integer::sum); // 6
```

Nếu dùng `100` làm identity cho phép cộng, mỗi phân đoạn parallel có thể bắt đầu với giá trị `100`; điều đó không tương đương phép cộng bình thường. Một identity không đúng có thể cho ra kết quả phụ thuộc vào cách thực thi.

Ở overload ba tham số, combiner cũng phải associative và tương thích với accumulator. Cụ thể, kết hợp một giá trị đã tích lũy với phần kết quả bắt đầu từ identity phải cho cùng kết quả như tích lũy trực tiếp phần tử đó.

### 3.3. Hàm tích lũy phải stateless và non-interfering

Không sửa nguồn stream hoặc thay đổi một biến bên ngoài được nhiều task cùng chia sẻ:

```java
// KHÔNG NÊN: shared mutable state dễ gây data race.
int[] total = {0};

List.of(1, 2, 3, 4).parallelStream()
    .forEach(n -> total[0] += n);
```

Cách đúng là đưa phép gộp vào terminal operation:

```java
int total = List.of(1, 2, 3, 4).parallelStream()
    .mapToInt(Integer::intValue)
    .sum();
```

Các lambda cung cấp cho `reduce` nên chỉ tính giá trị kết quả từ tham số, không thực hiện cập nhật trạng thái bên ngoài. Điều này giảm rủi ro khi chuyển giữa sequential và parallel.

### 3.4. Số thực và tính kết hợp

Cần phân biệt tính kết hợp toán học với phép cộng dấu phẩy động theo IEEE 754: do làm tròn, `double` có thể cho kết quả khác khi thay đổi thứ tự hoặc cách nhóm phép cộng.

```java
var numbers = List.of(1e16, 1.0, -1e16);

double sum = numbers.stream()
    .mapToDouble(Double::doubleValue)
    .sum();
```

Kết quả có thể chịu ảnh hưởng của sai số và chiến lược cộng số dấu phẩy động; đừng dùng một tổng `double` để biểu diễn tiền tệ cần độ chính xác thập phân. Với số tiền, dùng `BigDecimal` và quy tắc scale/làm tròn của miền nghiệp vụ.

## 4. collect: tích lũy vào cấu trúc kết quả

`collect` là thao tác *mutable reduction*: nó tích lũy các phần tử vào một **container** (ví dụ `ArrayList`, `HashMap`, `StringBuilder`) rồi trả về kết quả. Có hai cách gọi:

```java
<R> R collect(
    Supplier<R> supplier,
    BiConsumer<R, ? super T> accumulator,
    BiConsumer<R, R> combiner
);

<R, A> R collect(Collector<? super T, A, R> collector);
```

Trong ví dụ chữ ký trên, `T` là kiểu phần tử của `Stream<T>`; đây là các chữ ký rút gọn để giải thích, không phải khai báo phương thức độc lập có thể dán vào class.

### 4.1. collect ba tham số

```java
import java.util.ArrayList;
import java.util.List;

List<String> names = List.of("Lan", "An", "Binh").stream()
    .collect(
        ArrayList::new,
        ArrayList::add,
        ArrayList::addAll
    );

System.out.println(names); // [Lan, An, Binh]
```

Ý nghĩa:

- `supplier` tạo một container rỗng.
- `accumulator` thêm từng phần tử vào container.
- `combiner` nối nội dung từ hai container trung gian.

Khi chạy song song, Stream có thể tạo nhiều container riêng rồi ghép chúng lại. Vì vậy, `ArrayList` vẫn có thể được dùng làm container của phép `collect` parallel nếu các hàm tuân thủ hợp đồng; điều này **không** có nghĩa là có thể cập nhật một `ArrayList` toàn cục từ nhiều luồng mà không đồng bộ.

Trong phần lớn ứng dụng, hãy ưu tiên collector định nghĩa sẵn:

```java
var names = List.of("Lan", "An", "Binh").stream()
    .collect(java.util.stream.Collectors.toCollection(ArrayList::new));
```

### 4.2. Vì sao không dùng reduce để tạo List?

Đây là ví dụ **sai hướng tiếp cận**, đặc biệt nguy hiểm khi dùng stream song song:

```java
// Tránh: accumulator sửa trực tiếp identity/container của reduce.
var wrong = java.util.stream.Stream.of("A", "B", "C").reduce(
    new ArrayList<String>(),
    (list, value) -> {
        list.add(value);
        return list;
    },
    (left, right) -> {
        left.addAll(right);
        return left;
    }
);
```

Ở overload `reduce`, identity được dùng như giá trị đồng nhất cho mỗi phần tích lũy, không phải một container riêng do `supplier` tạo. Mutate `ArrayList` trong accumulator vi phạm các giả định về identity, associativity và tính stateless, khiến kết quả không được bảo đảm.

Cách đúng:

```java
var correct = java.util.stream.Stream.of("A", "B", "C")
    .collect(java.util.stream.Collectors.toCollection(ArrayList::new));
```

Quy tắc đơn giản: **tính ra một giá trị mới** thì cân nhắc `reduce`; **xây hoặc cập nhật cấu trúc kết quả** thì cân nhắc `collect`.

## 5. Lựa chọn List, Set và kết quả không thể sửa đổi

Các cách gom phần tử phổ biến trông giống nhau nhưng hợp đồng trả về khác nhau:

| Cách viết | Kết quả | Tính sửa đổi và thứ tự |
|---|---|---|
| `stream.toList()` | `List<T>` | Unmodifiable, giữ encounter order nếu stream có order |
| `stream.collect(Collectors.toList())` | `List<T>` | Không bảo đảm kiểu triển khai hay tính sửa đổi |
| `stream.collect(Collectors.toUnmodifiableList())` | `List<T>` | Unmodifiable, từ chối phần tử `null` |
| `stream.collect(Collectors.toCollection(ArrayList::new))` | `ArrayList<T>` | Có thể sửa, giữ thứ tự phần tử với nguồn có encounter order |
| `stream.collect(Collectors.toSet())` | `Set<T>` | Không bảo đảm kiểu triển khai, thứ tự hay tính sửa đổi |

Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

var source = List.of("A", "B", "A");

var ordered = source.stream().toList();
var distinct = source.stream().collect(Collectors.toSet());
var mutable = source.stream()
    .collect(Collectors.toCollection(ArrayList::new));

System.out.println(ordered);       // [A, B, A]
System.out.println(distinct.size()); // 2
mutable.add("C");                  // Hợp lệ
// ordered.add("C");               // UnsupportedOperationException
```

Nếu nghiệp vụ cần danh sách không thể sửa đổi, `Stream.toList()` thường diễn đạt ý định rõ nhất. Nếu yêu cầu một implementation cụ thể hoặc khả năng cập nhật, chọn `toCollection` với supplier phù hợp.

Không suy luận rằng `Collectors.toList()` luôn trả về `ArrayList` có thể sửa; Javadoc không cam kết như vậy. Khi dùng `Collectors.toSet()`, không giả định kết quả sẽ duyệt theo đúng thứ tự input.

## 6. toMap: gom dữ liệu theo khóa và xử lý trùng khóa

`Collectors.toMap` thích hợp khi mỗi phần tử ánh xạ thành một cặp key–value:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Product(String code, String name) {}

var products = List.of(
    new Product("P-1", "Bút"),
    new Product("P-2", "Sổ")
);

Map<String, Product> byCode = products.stream()
    .collect(Collectors.toMap(Product::code, product -> product));

System.out.println(byCode.get("P-1").name()); // Bút
```

### 6.1. Trùng khóa không được giải quyết tự động

Overload hai tham số của `toMap(keyMapper, valueMapper)` ném `IllegalStateException` nếu hai phần tử sinh cùng một khóa theo quy tắc `equals` của khóa.

```java
var names = List.of("an", "AN");

// Cùng key sau khi lower-case, nên collector hai tham số thất bại.
// names.stream().collect(Collectors.toMap(
//     name -> name.toLowerCase(java.util.Locale.ROOT),
//     name -> name
// ));
```

Khi trùng khóa là tình huống hợp lệ, cung cấp **merge function**:

```java
Map<String, String> merged = names.stream().collect(
    Collectors.toMap(
        name -> name.toLowerCase(java.util.Locale.ROOT),
        name -> name,
        (first, second) -> first
    )
);
```

Hàm `(first, second) -> first` giữ giá trị đầu tiên khi merge. Nếu cần kết quả không phụ thuộc thứ tự gộp, ưu tiên một phép merge có tính associative và không dựa vào “phần tử đến trước” trừ khi encounter order là một phần được bảo đảm của quy trình.

Dạng bốn tham số cung cấp `mapFactory`:

```java
var countsByName = List.of("B", "A", "B").stream()
    .collect(Collectors.toMap(
        java.util.function.Function.identity(),
        ignored -> 1,
        Integer::sum,
        java.util.TreeMap::new
    ));

System.out.println(countsByName); // {A=1, B=2}
```

Dùng `TreeMap::new` khi muốn thứ tự khóa theo so sánh tự nhiên; dùng `LinkedHashMap::new` khi muốn một map có encounter order phù hợp với nguồn và thao tác. `toMap` mặc định không cam kết loại `Map` được tạo, kể cả khi triển khai JDK thường dùng `HashMap`.

Lưu ý, tránh thiết kế mapper tạo khóa hoặc giá trị `null` nếu collector tương ứng không hỗ trợ; hãy chuẩn hóa và kiểm tra dữ liệu đầu vào một cách rõ ràng.

## 7. groupingBy: nhóm rồi tổng hợp từng nhóm

`groupingBy(classifier)` tạo một map từ khóa nhóm đến danh sách các phần tử:

```java
import java.util.List;
import java.util.stream.Collectors;

record Event(String category, int quantity) {}

var events = List.of(
    new Event("BOOK", 2),
    new Event("PEN", 3),
    new Event("BOOK", 1)
);

var byCategory = events.stream()
    .collect(Collectors.groupingBy(Event::category));

System.out.println(byCategory.get("BOOK").size()); // 2
```

Nhưng nếu chỉ muốn thống kê thay vì giữ mọi phần tử, hãy dùng **downstream collector**:

```java
var countByCategory = events.stream().collect(
    Collectors.groupingBy(
        Event::category,
        Collectors.counting()
    )
);

var quantityByCategory = events.stream().collect(
    Collectors.groupingBy(
        Event::category,
        Collectors.summingInt(Event::quantity)
    )
);

System.out.println(countByCategory.get("BOOK"));    // 2 (Long)
System.out.println(quantityByCategory.get("BOOK")); // 3 (Integer)
```

`groupingBy` với downstream giúp thực hiện nhiều kiểu tổng hợp mà không phải tạo `Map<K,List<V>>` trung gian rồi duyệt lần nữa.

### 7.1. Kết hợp mapping với groupingBy

```java
var quantitiesAsStrings = events.stream().collect(
    Collectors.groupingBy(
        Event::category,
        Collectors.mapping(
            event -> Integer.toString(event.quantity()),
            Collectors.joining(", ")
        )
    )
);

System.out.println(quantitiesAsStrings.get("BOOK")); // 2, 1
```

`mapping` biến đổi phần tử chỉ **bên trong từng nhóm** trước khi downstream nhận dữ liệu. Nó tiện khi bạn muốn nhóm theo thuộc tính của phần tử ban đầu nhưng gom một thuộc tính khác.

### 7.2. Tái sử dụng reduce làm downstream

`Collectors.reducing` cho phép đặt một phép giảm giá trị trong `groupingBy`:

```java
import java.math.BigDecimal;

record Item(String category, BigDecimal amount) {}

var items = List.of(
    new Item("BOOK", new BigDecimal("12.50")),
    new Item("PEN", new BigDecimal("4.00")),
    new Item("BOOK", new BigDecimal("7.50"))
);

var amountByCategory = items.stream().collect(
    Collectors.groupingBy(
        Item::category,
        Collectors.reducing(
            BigDecimal.ZERO,
            Item::amount,
            BigDecimal::add
        )
    )
);

System.out.println(amountByCategory.get("BOOK")); // 20.00
```

Overload `reducing(identity, mapper, op)` nhận phần tử `Item`, biến thành `BigDecimal`, rồi kết hợp bằng phép cộng. Đây là ví dụ quan trọng cho việc phối hợp giữa **reduction** và **collector**: `Collectors.reducing` được thiết kế đặc biệt hữu ích khi dùng downstream của `groupingBy` hoặc `partitioningBy`.

Một `groupingBy` mặc định không cam kết loại map, tính sửa đổi, an toàn đa luồng hoặc thứ tự duyệt khóa. Nếu muốn đầu ra có thứ tự khóa ổn định, dùng overload có `mapFactory` như `TreeMap::new`.

## 8. partitioningBy, filtering và điểm khác biệt về nhóm rỗng

Nếu chỉ phân dữ liệu theo điều kiện đúng/sai, dùng `Collectors.partitioningBy`:

```java
var numbers = List.of(1, 2, 3, 4, 5);

var partitions = numbers.stream().collect(
    Collectors.partitioningBy(n -> n % 2 == 0)
);

System.out.println(partitions.get(true));  // [2, 4]
System.out.println(partitions.get(false)); // [1, 3, 5]
```

Kết quả là `Map<Boolean,List<T>>`, có cả khóa `true` lẫn `false` kể cả khi một phía rỗng. Với downstream `counting()`, bạn có thể đếm số phần tử thỏa/không thỏa điều kiện:

```java
var counts = numbers.stream().collect(
    Collectors.partitioningBy(n -> n % 2 == 0, Collectors.counting())
);
// true -> 2L; false -> 3L
```

### filter trước khi nhóm khác với filtering ở downstream

```java
record User(String team, boolean active) {}

var users = List.of(
    new User("backend", false),
    new User("frontend", true)
);

var filteredFirst = users.stream()
    .filter(User::active)
    .collect(Collectors.groupingBy(User::team, Collectors.counting()));

var retainedGroups = users.stream()
    .collect(Collectors.groupingBy(
        User::team,
        Collectors.filtering(User::active, Collectors.counting())
    ));
```

- `filteredFirst` **không có** khóa `backend`, vì phần tử nhóm này đã bị loại trước khi phân nhóm.
- `retainedGroups` có khóa `backend` với giá trị `0L`, vì nhóm được xác định trước, sau đó mới lọc các phần tử đưa vào downstream.

Chọn cách nào dựa trên câu hỏi nghiệp vụ: chỉ quan tâm nhóm có dữ liệu hợp lệ, hay cần báo cáo cả nhóm có giá trị thống kê bằng 0.

## 9. Các phép tổng hợp chuyên dụng

Không phải phép tính nào cũng cần gọi `reduce` hoặc tự xây `Collector`. Những API có sẵn thường ngắn gọn, rõ ràng và có tối ưu dành cho mục đích riêng.

| Mục tiêu | API thường phù hợp | Kiểu kết quả |
|---|---|---|
| Đếm phần tử trong stream | `stream.count()` | `long` |
| Tính tổng primitive int | `mapToInt(...).sum()` | `int` |
| Tính tổng primitive long | `mapToLong(...).sum()` | `long` |
| Tính tổng primitive double | `mapToDouble(...).sum()` | `double` |
| Trung bình số primitive | `mapToInt(...).average()` | `OptionalDouble` |
| Min/max phần tử | `stream.min/max(comparator)` | `Optional<T>` |
| Thống kê tổng hợp int | `Collectors.summarizingInt(mapper)` | `IntSummaryStatistics` |
| Thống kê tổng hợp long | `Collectors.summarizingLong(mapper)` | `LongSummaryStatistics` |
| Ghép chuỗi | `Collectors.joining(delimiter)` | `String` |
| Đếm bên trong mỗi nhóm | `groupingBy(..., counting())` | `Map<K,Long>` |

Ví dụ gom count, min, max, sum và average về một đối tượng:

```java
var statistics = List.of(5, 10, 15, 20).stream()
    .collect(java.util.stream.Collectors.summarizingInt(
        Integer::intValue
    ));

System.out.println(statistics.getCount());   // 4
System.out.println(statistics.getSum());     // 50
System.out.println(statistics.getMin());     // 5
System.out.println(statistics.getMax());     // 20
System.out.println(statistics.getAverage()); // 12.5
```

Với stream rỗng, `average()` trên primitive stream trả `OptionalDouble.empty()`, còn `count()` trả 0. Các giá trị `min()`/`max()` không có phần tử trả Optional rỗng. Hãy chọn hành vi phù hợp với hợp đồng nghiệp vụ, đừng tự thay `Optional` rỗng bằng `0` khi `0` có ý nghĩa khác.

Chú ý tới overflow nếu cộng rất nhiều số nguyên: `IntStream.sum()` trả về `int`; nếu tổng có thể vượt giới hạn `int`, cân nhắc `mapToLong(...).sum()`, `Math.addExact`, hoặc `BigInteger` tùy yêu cầu. Với tiền tệ, `BigDecimal` thường phù hợp hơn `double` vì độ chính xác thập phân.

## 10. teeing: tính hai kết quả trong một lần collect

`Collectors.teeing(downstream1, downstream2, merger)` kết hợp **hai collector** trên cùng luồng đầu vào, sau đó hợp nhất hai kết quả thành một kết quả cuối. API này đã ổn định từ Java 12 và còn được hỗ trợ trong Java 27.

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.stream.Collectors;

record Payment(BigDecimal amount) {}
record PaymentSummary(long count, BigDecimal total) {}

var payments = List.of(
    new Payment(new BigDecimal("10.50")),
    new Payment(new BigDecimal("19.50"))
);

var summary = payments.stream().collect(
    Collectors.teeing(
        Collectors.counting(),
        Collectors.reducing(
            BigDecimal.ZERO,
            Payment::amount,
            BigDecimal::add
        ),
        PaymentSummary::new
    )
);

System.out.println(summary.count()); // 2
System.out.println(summary.total()); // 30.00
```

Collector đầu đếm phần tử; collector thứ hai tính tổng tiền; hàm `PaymentSummary::new` kết hợp hai kết quả thành một record.

`teeing` tiện khi chỉ cần **hai** kết quả thống kê trong một pipeline. Nó không tự biến các phép tích lũy thành thao tác miễn phí hay luôn nhanh hơn hai lần duyệt một collection nhỏ. Với báo cáo có nhiều chỉ tiêu, hãy cân nhắc `summarizingInt`, collector tổng hợp chuyên biệt hoặc một đối tượng accumulator được thiết kế đúng hợp đồng.

## 11. Ví dụ hoàn chỉnh: báo cáo doanh thu theo danh mục

Tạo file `SalesReductionDemo.java` và dùng JDK 27 để biên dịch. Chương trình này minh họa ba phép tổng hợp có ý nghĩa khác nhau: `reduce` tính tổng doanh thu, `groupingBy` kết hợp downstream `reducing` để tính doanh thu theo danh mục, và `teeing` để tạo bảng tóm tắt.

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class SalesReductionDemo {

    record Sale(String orderId, String category, long units,
                BigDecimal unitPrice) {
        Sale {
            Objects.requireNonNull(orderId, "orderId");
            Objects.requireNonNull(category, "category");
            Objects.requireNonNull(unitPrice, "unitPrice");
            if (orderId.isBlank() || category.isBlank()
                    || units <= 0 || unitPrice.signum() < 0) {
                throw new IllegalArgumentException("Dữ liệu bán hàng không hợp lệ");
            }
        }

        BigDecimal revenue() {
            return unitPrice.multiply(BigDecimal.valueOf(units));
        }
    }

    record Overview(long count, BigDecimal totalRevenue) {}

    public static void main(String[] args) {
        var sales = List.of(
            new Sale("O-101", "BOOK", 2, new BigDecimal("12.50")),
            new Sale("O-102", "PEN", 3, new BigDecimal("3.20")),
            new Sale("O-103", "BOOK", 1, new BigDecimal("8.00")),
            new Sale("O-104", "PEN", 2, new BigDecimal("1.50"))
        );

        // (1) Reduce tạo ra một giá trị tổng.
        BigDecimal totalRevenue = sales.stream()
            .map(Sale::revenue)
            .reduce(BigDecimal.ZERO, BigDecimal::add);

        // (2) GroupingBy và downstream reducing tạo tổng theo nhóm.
        var revenueByCategory = sales.stream().collect(
            Collectors.groupingBy(
                Sale::category,
                TreeMap::new,
                Collectors.reducing(
                    BigDecimal.ZERO,
                    Sale::revenue,
                    BigDecimal::add
                )
            )
        );

        // (3) Mỗi nhóm cộng số lượng bằng summingLong.
        var unitsByCategory = sales.stream().collect(
            Collectors.groupingBy(
                Sale::category,
                TreeMap::new,
                Collectors.summingLong(Sale::units)
            )
        );

        // (4) Hai chỉ tiêu đầu ra trong một lần collect.
        var overview = sales.stream().collect(
            Collectors.teeing(
                Collectors.counting(),
                Collectors.reducing(
                    BigDecimal.ZERO,
                    Sale::revenue,
                    BigDecimal::add
                ),
                Overview::new
            )
        );

        // (5) Ghép mã đơn hàng với thứ tự rõ ràng.
        String orderIds = sales.stream()
            .map(Sale::orderId)
            .distinct()
            .sorted()
            .collect(Collectors.joining(", "));

        System.out.println("Tổng doanh thu: " + totalRevenue);
        System.out.println("Doanh thu theo danh mục: " + revenueByCategory);
        System.out.println("Số lượng theo danh mục: " + unitsByCategory);
        System.out.println("Số dòng dữ liệu: " + overview.count());
        System.out.println("Tổng trong overview: " + overview.totalRevenue());
        System.out.println("Mã đơn: " + orderIds);
    }
}
```

Chạy:

```shell
javac SalesReductionDemo.java
java SalesReductionDemo
```

Kết quả:

```text
Tổng doanh thu: 45.60
Doanh thu theo danh mục: {BOOK=33.00, PEN=12.60}
Số lượng theo danh mục: {BOOK=3, PEN=5}
Số dòng dữ liệu: 4
Tổng trong overview: 45.60
Mã đơn: O-101, O-102, O-103, O-104
```

Ở ví dụ này, `TreeMap::new` cung cấp thứ tự khóa tự nhiên cho kết quả theo danh mục, nên dạng hiển thị map ổn định theo khóa. Trong một báo cáo thật, không nên dựa vào `Map.toString()` như định dạng trao đổi dữ liệu; hãy ánh xạ kết quả sang DTO/JSON hoặc định dạng xuất có hợp đồng rõ ràng.

`BigDecimal` được dùng để tính doanh thu, còn `summingLong` chỉ tính số lượng nguyên. Với tiền tệ, ứng dụng vẫn cần chính sách đơn vị tiền, scale và làm tròn nhất quán với yêu cầu miền nghiệp vụ.

## 12. Thu thập dữ liệu song song: khi nào phù hợp?

Một phép `reduce` đúng hợp đồng với identity, accumulator và combiner có thể được thực thi song song. Tuy nhiên, **khả năng parallelizable không đồng nghĩa với việc nên dùng parallel stream cho mọi tập dữ liệu**.

```java
var numbers = java.util.stream.LongStream.rangeClosed(1, 1_000_000);

long total = numbers.parallel().sum();
```

Ở đây, `LongStream.sum()` là phép tổng hợp chuyên dụng. Khi dùng `collect`, thư viện có thể tạo nhiều container trung gian, tích lũy độc lập, rồi ghép kết quả. Một collector không thread-safe như `Collectors.toList()` vẫn có thể hoạt động đúng với parallel stream vì các container trung gian được quản lý theo hợp đồng Stream, không đồng nghĩa từng container được chia sẻ cho các task cùng cập nhật.

### groupingByConcurrent có thể giúp khi không cần thứ tự

```java
var values = List.of("java", "kotlin", "java", "scala");

var counts = values.parallelStream().collect(
    Collectors.groupingByConcurrent(
        java.util.function.Function.identity(),
        Collectors.counting()
    )
);
```

`groupingByConcurrent` cho phép một chiến lược gom nhóm concurrent và là collector không bảo đảm encounter order của các phần tử trong từng nhóm. Nó có thể hữu ích khi không cần thứ tự, dữ liệu lớn và chi phí gom nhóm đủ cao; đừng mặc định nó nhanh hơn `groupingBy` trong mọi tình huống.

Trước khi dùng parallel, hãy kiểm tra:

- Phép kết hợp phải associative và identity đúng.
- Lambda phải stateless và non-interfering.
- Không dùng shared `ArrayList`, `HashMap` hoặc bộ đếm mutable không đồng bộ làm side effect.
- Có yêu cầu giữ encounter order không? `groupingByConcurrent` và collector có đặc tính `UNORDERED` có thể không phù hợp.
- Nguồn dữ liệu và collector có phù hợp với chi phí chia task/ghép kết quả không?
- Phép toán có cần độ chính xác floating point phụ thuộc thứ tự, hoặc có side effect hay I/O không?

Đối với workload nhỏ hoặc các thao tác chủ yếu chờ I/O, stream tuần tự thường đơn giản hơn. Chỉ tối ưu theo kết quả đo thực tế trong môi trường ứng dụng.

## 13. Các sai lầm thường gặp

| Sai lầm | Vấn đề | Cách xử lý |
|---|---|---|
| Dùng `reduce` để mutate một `ArrayList` identity | Vi phạm hợp đồng reduction, đặc biệt trong parallel | Dùng `collect(toCollection(...))` |
| Chọn identity không trung hòa | Kết quả sai hoặc phụ thuộc cách chia nhóm | Kiểm tra identity của phép toán |
| Dùng phép trừ trong parallel reduce | Không associative | Dùng quy trình có thứ tự hoặc đổi mô hình phép tính |
| Dùng `double` cho tiền | Sai số dấu phẩy động | Dùng `BigDecimal` với chính sách làm tròn |
| Dùng `toMap` khi key có thể trùng, không có merge | `IllegalStateException` | Cung cấp merge function hoặc dùng `groupingBy` |
| Dùng `groupingBy` để lấy danh sách khi chỉ cần số đếm | Lưu container trung gian không cần thiết | Dùng downstream `counting()` |
| Giả định `Collectors.toList()` luôn mutable | Không có bảo đảm API | Dùng `toCollection(ArrayList::new)` |
| Tưởng `Stream.toList()` mutable | `UnsupportedOperationException` | Tạo collection sửa được khi cần |
| Dùng `Collectors.toSet()` rồi dựa vào thứ tự phần tử | Set không có cam kết encounter order | Chọn `toCollection(LinkedHashSet::new)` nếu cần |
| Dùng `forEach` để đếm cộng dồn trong biến chia sẻ | Data race và phụ thuộc thứ tự | Dùng `count`, `sum`, `reduce` hoặc `collect` |
| Dùng một Stream cho nhiều terminal operations | Stream đã được tiêu thụ | Lấy stream mới từ nguồn |
| Gộp theo thuộc tính có thể null mà không xác thực | Dễ gặp lỗi hoặc nhóm không đúng ý nghĩa | Chuẩn hóa và kiểm tra dữ liệu trước khi collect |

Một vấn đề khác là **trùng nghĩa tính toán**: việc gọi `groupingBy` rồi mới `map`/reduce trên từng danh sách có thể thừa container và vòng duyệt so với `groupingBy(classifier, downstream)`. Hãy ưu tiên khai báo trực tiếp kết quả mong muốn.

## 14. Checklist chọn phép tổng hợp

Khi đứng trước một yêu cầu xử lý dữ liệu, có thể ra quyết định theo các câu hỏi sau:

1. **Chỉ cần một số đếm, tổng, min, max hoặc trung bình?** Ưu tiên terminal operation chuyên dụng; dùng primitive stream khi phù hợp.
2. **Cần một giá trị duy nhất dựa trên phép kết hợp associative, có identity?** Dùng `reduce(identity, operator)`.
3. **Cần một giá trị nhưng stream có thể rỗng và không có identity hợp lệ?** Dùng `reduce(operator)`, `min()` hoặc `max()` trả `Optional`.
4. **Cần biến đổi kiểu phần tử thành kiểu kết quả khi gộp?** Cân nhắc `mapToInt/mapToLong + sum`, rồi mới `reduce` ba tham số khi thật sự cần.
5. **Cần List, Set, Map hoặc mutable container?** Chọn `collect` và collector thích hợp.
6. **Cần một giá trị cho mỗi nhóm?** Dùng `groupingBy(classifier, downstream)`, thay vì tự tạo map các danh sách trung gian.
7. **Cần đúng hai nhóm true/false?** Dùng `partitioningBy`.
8. **Cần hai kết quả khác nhau từ cùng nguồn?** Cân nhắc `teeing` nếu kết hợp được trong một lần collect.
9. **Cần xử lý song song?** Kiểm tra associativity, statelessness, ordering, nguồn dữ liệu và đo hiệu năng.
10. **Có ràng buộc thứ tự hoặc tính sửa đổi của kết quả?** Chọn collector/factory có hợp đồng đáp ứng yêu cầu, không dựa vào implementation ngầm định.

Điểm quan trọng nhất: **không chọn `reduce` hay `collect` chỉ vì cú pháp ngắn hơn**. Hãy chọn dựa trên **bản chất kết quả**, **hợp đồng toán học** và **trường hợp biên của dữ liệu**.

## 15. Bài tập thực hành

### Bài 1 — Tổng số lượng

Cho danh sách `List<Integer>` chứa `[2, 5, 3, 4]`. Hãy tính tổng bằng `reduce`, sau đó viết lại bằng primitive stream. Giải thích cách nào dễ đọc hơn khi chỉ tính tổng số nguyên.

### Bài 2 — Tìm giá trị lớn nhất

Cho một danh sách điểm số có thể rỗng, hãy tìm điểm lớn nhất bằng `reduce(BinaryOperator)` rồi trả về `Optional<Integer>`. Không dùng một số đặc biệt như `-1` để giả định điểm cao nhất của dữ liệu rỗng.

### Bài 3 — Đếm theo nhóm

Cho danh sách trạng thái `["NEW", "PAID", "NEW", "FAILED", "PAID", "NEW"]`, hãy sử dụng `groupingBy` và `counting` để tạo `Map<String,Long>`.

### Bài 4 — Ghép chuỗi

Cho danh sách mã `["B-02", "A-01", "C-03"]`, hãy tạo chuỗi `"A-01, B-02, C-03"` bằng `sorted()` và `Collectors.joining(", ")`. Vì sao dùng `reduce("", String::concat)` kém rõ ràng hơn trong yêu cầu này?

### Bài 5 — Trùng khóa

Cho `List<String>` có `["a", "A", "b"]`, xây map từ chuỗi dạng chữ hoa sang số lần xuất hiện bằng `toMap` với merge function và `TreeMap::new`. Dự đoán kết quả.

### Bài 6 — Group có số đếm bằng 0

Cho danh sách nhân sự theo nhóm, trong đó một nhóm có toàn nhân sự inactive. Hãy so sánh kết quả khi dùng `filter` trước `groupingBy` và `Collectors.filtering` ở downstream. Xác định cách tạo bảng báo cáo vẫn giữ nhóm có số lượng active bằng 0.

### Đáp án gợi ý

```java
import java.util.List;
import java.util.Locale;
import java.util.TreeMap;
import java.util.stream.Collectors;

var numbers = List.of(2, 5, 3, 4);

int viaReduce = numbers.stream().reduce(0, Integer::sum);
int viaPrimitive = numbers.stream().mapToInt(Integer::intValue).sum();
// viaReduce == viaPrimitive == 14

var maximum = numbers.stream().reduce(Integer::max);
// Optional<Integer> chứa 5

var states = List.of("NEW", "PAID", "NEW", "FAILED", "PAID", "NEW");
var stateCounts = states.stream().collect(
    Collectors.groupingBy(
        java.util.function.Function.identity(),
        Collectors.counting()
    )
);
// NEW=3, PAID=2, FAILED=1 (thứ tự map không được bảo đảm)

var ids = List.of("B-02", "A-01", "C-03");
var joined = ids.stream().sorted().collect(Collectors.joining(", "));
// "A-01, B-02, C-03"

var labels = List.of("a", "A", "b");
var countsByUppercase = labels.stream().collect(
    Collectors.toMap(
        value -> value.toUpperCase(Locale.ROOT),
        ignored -> 1,
        Integer::sum,
        TreeMap::new
    )
);
// {A=2, B=1}
```

**Gợi ý bài 6:** Đưa `Collectors.filtering(Employee::active, Collectors.counting())` vào downstream của `groupingBy(Employee::team, ...)` nếu muốn nhóm có toàn nhân sự inactive vẫn xuất hiện với giá trị 0.

## 16. Tóm tắt

`reduce` và `collect` cùng tạo kết quả cuối của Stream nhưng có trách nhiệm khác nhau:

- `reduce` là lựa chọn tự nhiên cho phép gộp **giá trị** bằng toán tử associative với identity phù hợp.
- `collect` thích hợp cho phép tích lũy **cấu trúc**, bao gồm collection, map, kết quả nhóm và các thống kê phức tạp.
- `groupingBy(..., downstream)`, `partitioningBy`, `toMap`, `teeing` giúp mô hình hóa nhiều yêu cầu tổng hợp mà không phải dùng mutable state bên ngoài.
- `sum`, `count`, `average`, `min`, `max` và primitive streams thường là công cụ rõ ràng nhất cho thống kê cơ bản.
- Khi chạy song song, hợp đồng associativity, identity, non-interference và đặc tính thứ tự quyết định tính đúng đắn; đo hiệu năng thay vì tự giả định parallel luôn nhanh.

## Tài liệu tham khảo

- [Java SE 27 API — Stream](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html): các overload `reduce`, `collect`, `toList`, `count` và yêu cầu đối với stream pipeline.
- [Java SE 27 API — Collectors](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Collectors.html): `toMap`, `groupingBy`, `reducing`, `counting`, `teeing`, `mapping`, `filtering`, `partitioningBy`.
- [Java SE 27 API — java.util.stream package](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/package-summary.html): reduction, mutable reduction, associativity, parallel processing và non-interference.
- [Java SE 27 API — Collector](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Collector.html): đặc tính `CONCURRENT`, `UNORDERED`, `IDENTITY_FINISH` và hợp đồng tích lũy.
- [Java SE 27 API — IntStream](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/IntStream.html): `sum`, `average`, `summaryStatistics` và primitive reduction.
- [Java SE 27 API — BigDecimal](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/math/BigDecimal.html): cộng, nhân và biểu diễn số thập phân chính xác cho yêu cầu nghiệp vụ.
