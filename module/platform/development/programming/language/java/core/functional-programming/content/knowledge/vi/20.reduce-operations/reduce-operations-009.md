# Chọn reduce() hay collect() theo bản chất kết quả trong Java Stream

Trong Java Stream API, **`reduce()`** và **`collect()`** đều là các *terminal operations* dùng để tổng hợp nhiều phần tử thành một kết quả. Tuy nhiên, chúng phục vụ hai kiểu tích lũy khác nhau. Chọn đúng không chỉ giúp mã rõ ràng mà còn ảnh hưởng trực tiếp đến **tính đúng đắn khi xử lý song song**, khả năng tái sử dụng, quản lý bộ nhớ và hiệu năng.

- **`reduce()`** phù hợp với **phép kết hợp giá trị**: từ các phần tử, tính ra tổng, tích, min/max, phép gộp bất biến hoặc một kết quả tổng hợp mới. Mỗi lần áp dụng toán tử thường trả **một giá trị kết quả**, không thay đổi accumulator được truyền vào.
- **`collect()`** phù hợp với **tích lũy vào bộ chứa có thể thay đổi**: xây dựng danh sách, tập hợp, bản đồ, nhóm dữ liệu, chuỗi bằng `StringBuilder`, thống kê tổng hợp hoặc một kết quả được mô tả bởi `Collector`.
- Không có quy tắc tuyệt đối rằng kết quả cuối của `collect` phải mutable hoặc `reduce` chỉ trả primitive. Sự khác biệt nằm ở **cơ chế tích lũy và hợp đồng của toán tử**, không đơn thuần ở tên kiểu kết quả cuối cùng.

Ví dụ ngắn, giả sử `numbers` là `List<Integer>` đã được khai báo:

```java
int sum = numbers.stream().reduce(0, Integer::sum);
List<Integer> copy = numbers.stream().collect(java.util.stream.Collectors.toList());
```

Dòng đầu kết hợp các số bằng phép cộng. Dòng thứ hai thu thập các phần tử thành một container. Hai mục tiêu khác nhau nên chọn terminal khác nhau.

**Mục tiêu bài học:** nắm vững ba overload của `reduce`, các dạng `collect`, quy tắc identity/associativity/combiner, lựa chọn cho danh sách–map–grouping–statistic, bẫy mutable identity, và cách kiểm tra logic trên parallel stream. Các chương trình hoàn chỉnh dùng **Java 17+**.

## 1. Tư duy từ bản chất kết quả, không từ cú pháp

Câu hỏi đầu tiên khi chọn terminal operation là: **Kết quả cần là một giá trị tính toán hay là một cấu trúc được tích lũy?**

| Mục tiêu | Thường chọn | Ví dụ |
| --- | --- | --- |
| Cộng các số | `sum()` hoặc `reduce(0, Integer::sum)` | `IntStream` trả `int` |
| Tìm giá trị lớn nhất/nhỏ nhất | `max()`, `min()`, hoặc `reduce` | Kết quả có thể là `Optional` |
| Gộp các trạng thái bất biến thành một trạng thái mới | `reduce` | Tổng + số lượng trong record bất biến |
| Tạo `List<T>`, `Set<T>` | `toList()` hoặc `collect` | Dữ liệu được đưa vào container |
| Phân nhóm theo khóa | `collect(groupingBy(...))` | `Map<K,List<T>>` |
| Đếm mỗi nhóm | `collect(groupingBy(..., counting()))` | `Map<K,Long>` |
| Nối chuỗi với delimiter | `collect(joining(","))` | Collector dùng tích lũy hiệu quả |
| Thu thập vào `ArrayList` mutable được chỉ định | `collect(toCollection(ArrayList::new))` | Có thể sửa kết quả |
| Tính thống kê nhiều chỉ số trong một lượt | `collect(summarizingInt(...))` | Count/sum/min/max/average |

Không phải cứ `reduce` nhận được cùng kiểu trả về là lựa chọn tốt nhất. Ví dụ nối 10.000 chuỗi bằng `reduce("", String::concat)` có thể phải tạo nhiều chuỗi trung gian vì `String` bất biến; `Collectors.joining` thường phù hợp hơn. Ngược lại, tính tổng chỉ cần một giá trị số nên không cần tự dựng `ArrayList` rồi duyệt lại.

## 2. reduce(): phép rút gọn dựa trên kết hợp giá trị

Với `Stream<T>`, có ba nhóm overload quan trọng.

### 2.1. reduce(BinaryOperator<T>): có thể không có phần tử

```java
Optional<Integer> max = Stream.of(2, 9, 4)
        .reduce(Integer::max);  // Optional chứa 9

Optional<Integer> missing = Stream.<Integer>empty()
        .reduce(Integer::max);  // Optional.empty()
```

Đây là **mảnh mã minh họa** cần import `java.util.Optional` và `java.util.stream.Stream`, được đặt trong phương thức. Khi Stream rỗng và không có identity, API dùng `Optional<T>` để biểu diễn sự vắng mặt. Không gọi `get()` tùy tiện; dùng `orElse` hoặc `orElseThrow` khi phù hợp.

Một toán tử như `Integer::max` là phép kết hợp có tính *associative*; kết quả không phụ thuộc vào cách nhóm các phép tính theo toán học.

### 2.2. reduce(identity, BinaryOperator<T>): luôn có kết quả

```java
int total = Stream.of(2, 9, 4).reduce(0, Integer::sum); // 15
int emptyTotal = Stream.<Integer>empty().reduce(0, Integer::sum); // 0
```

`identity` là **phần tử đơn vị**: gộp nó với một giá trị không làm thay đổi giá trị ấy. Với phép cộng, identity là `0`; với phép nhân, identity là `1`. Nếu Stream rỗng, `reduce(identity, op)` trả chính identity.

Đối với phép ghép chuỗi, `""` là identity của nối chuỗi; với tổng có kiểu `long`, dùng `0L`. Không chọn identity tùy tiện theo “giá trị mặc định” nếu nó phá vỡ phép toán.

### 2.3. reduce(identity, accumulator, combiner): kết quả kiểu khác phần tử

Đây là overload có dạng khái niệm:

```java
<U> U reduce(
    U identity,
    BiFunction<U, ? super T, U> accumulator,
    BinaryOperator<U> combiner
)
```

Đoạn trên là **chữ ký minh họa**, không phải phương thức top-level để chạy độc lập. `T` là kiểu phần tử của Stream; `U` là kiểu kết quả.

- `identity` là giá trị đơn vị của phép gộp kết quả.
- `accumulator` nhận một kết quả trung gian `U` và phần tử `T`, rồi **trả một `U` mới/giá trị kết quả**.
- `combiner` gộp hai kết quả `U` khi pipeline được chia thành nhiều phần, đặc biệt trong xử lý song song.

Ví dụ cộng tổng độ dài các chuỗi:

```java
int lengthSum = Stream.of("aa", "bbb", "c")
        .reduce(
                0,
                (total, word) -> total + word.length(),
                Integer::sum
        ); // 6
```

Giá trị `0` là identity, accumulator thêm độ dài từng từ, combiner cộng hai tổng trung gian. Cả hai phép gộp đều **không sửa một object accumulator dùng chung**. Đây là mẫu hợp lệ với `parallelStream()` nếu các hàm là stateless và non-interfering như ví dụ.

## 3. Hợp đồng của reduce: identity, associative và compatibility

Để một phép `reduce` được chia/gộp đúng, cần đáp ứng các điều kiện nền tảng.

### 3.1. Identity

Với toán tử `op`, identity `e` cần thỏa:

```text
op(e, x) = x
op(x, e) = x
```

Đây là **ký hiệu toán học mô tả hợp đồng**, không phải code Java.

Phép cộng: `e = 0`. Phép nhân: `e = 1`. Đối với một phép toán khác, phải xét thật sự đâu là phần tử đơn vị, không được mặc định dùng số không.

### 3.2. Associativity

Toán tử cần có tính kết hợp:

```text
op(op(a, b), c) = op(a, op(b, c))
```

Phép cộng số nguyên trên các giá trị ví dụ nhỏ là phù hợp. Phép trừ thông thường **không kết hợp**:

```text
(10 - 5) - 2 = 3
10 - (5 - 2) = 7
```

Vì vậy `reduce(0, (a, b) -> a - b)` không phải phép rút gọn đúng để kỳ vọng cùng kết quả khi chuyển từ tuần tự sang song song. Lưu ý phép cộng số nguyên Java có thể tràn theo quy tắc modulo, nên cần kiểm soát miền giá trị nếu nghiệp vụ đòi tổng toán học không tràn.

### 3.3. Compatibility cho reduce ba đối số

Với kết quả kiểu `U`, `combiner` phải nhất quán với cách `accumulator` thêm phần tử. Hợp đồng quan trọng:

```text
combiner(u, accumulator(identity, t)) = accumulator(u, t)
```

Dạng này diễn tả rằng gộp một kết quả `u` với kết quả tính từ một phần tử `t` phải giống trực tiếp thêm `t` vào `u`. Nếu `accumulator` tính tổng nhưng `combiner` lại nhân, kết quả song song có thể sai dù thử tuần tự dường như đúng.

Một số phép toán như cộng `double` có sai số làm tròn theo thứ tự nhóm phép cộng; không nên yêu cầu kết quả bit-by-bit giống nhau trên mọi cách gộp.

**Quy tắc thực hành:** với `reduce`, ưu tiên accumulator và combiner **không có side effect**, không sửa nguồn Stream, không sửa một container mutable chia sẻ, và có identity/associativity đúng.

## 4. Chương trình Java 17: các overload của reduce

Lưu thành **`ReduceEssentialsDemo.java`**:

```java
import java.util.List;
import java.util.Optional;

public class ReduceEssentialsDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(2, 3, 5);

        int sum = numbers.stream().reduce(0, Integer::sum);
        int product = numbers.stream().reduce(1, (a, b) -> a * b);
        Optional<Integer> max = numbers.stream().reduce(Integer::max);

        Optional<Integer> emptyMax = List.<Integer>of()
                .stream()
                .reduce(Integer::max);

        int totalLength = List.of("aa", "bbb", "c")
                .parallelStream()
                .reduce(0,
                        (length, word) -> length + word.length(),
                        Integer::sum);

        System.out.println("sum=" + sum);
        System.out.println("product=" + product);
        System.out.println("max=" + max.orElse(-1));
        System.out.println("emptyMax=" + emptyMax.orElse(-1));
        System.out.println("lengthSum=" + totalLength);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ReduceEssentialsDemo.java
java ReduceEssentialsDemo
```

**Stdout chính xác:**

```text
sum=10
product=30
max=5
emptyMax=-1
lengthSum=6
```

Ở đây các toán tử gộp số nhỏ phù hợp identity và tính kết hợp; do đó chạy `parallelStream` ở phép cộng độ dài vẫn cho kết quả 6. `emptyMax` là `Optional.empty()` và `orElse(-1)` chỉ cung cấp fallback cho ví dụ.

`List.<Integer>of()` tạo danh sách rỗng có kiểu phần tử `Integer` rõ ràng. Không lẫn `max` với phép lấy phần tử cuối: `Integer::max` so sánh giá trị số.

## 5. collect(): tích lũy qua container hoặc Collector

`collect()` cung cấp cơ chế **mutable reduction**: tạo container kết quả, đưa từng phần tử vào container, sau đó kết hợp các container phần việc nếu cần.

Có hai nhóm API chính:

```java
<R> R collect(
    Supplier<R> supplier,
    BiConsumer<R, ? super T> accumulator,
    BiConsumer<R, R> combiner
)

<R, A> R collect(Collector<? super T, A, R> collector)
```

Đây là **chữ ký minh họa** trong `Stream<T>` (đã đơn giản hóa phần generic cho dễ đọc). Với bản ba đối số:

- **supplier** tạo container mới, chẳng hạn `ArrayList::new`.
- **accumulator** nhận container và phần tử, rồi **thay đổi container đó**, chẳng hạn `List::add`.
- **combiner** gộp nội dung hai container để tạo kết quả gộp đúng, chẳng hạn `List::addAll`.

Khác với `reduce` trả giá trị kết hợp, `collect` được thiết kế để xử lý các container **có thể thay đổi trong quá trình tích lũy**. Khi chạy song song, framework có thể tạo nhiều container độc lập và kết hợp chúng. Không cung cấp một `ArrayList` chung đã tạo sẵn từ bên ngoài rồi sửa từ nhiều worker.

Dạng nhận `Collector` còn cho phép mô tả **supplier, accumulator, combiner, finisher** và các đặc tính của collector một cách chuẩn hóa. Một `Collector` có thể trả kết quả cuối **không thể sửa đổi**, mặc dù việc tích lũy bên trong sử dụng trạng thái mutable.

## 6. Các Collector chuẩn thường dùng

Trong `java.util.stream.Collectors`, có nhiều collector phổ biến:

| Collector | Mục tiêu |
| --- | --- |
| `toList()` | Thu thập vào `List<T>`; không bảo đảm cụ thể loại list hoặc khả năng sửa |
| `toSet()` | Thu thập vào `Set<T>`; không bảo đảm thứ tự lặp |
| `toCollection(ArrayList::new)` | Chọn kiểu container kết quả cụ thể |
| `toUnmodifiableList()` | Trả List không thể sửa; không chấp nhận phần tử null |
| `joining(",")` | Nối các phần tử `CharSequence` có phân tách |
| `groupingBy(classifier)` | Nhóm phần tử theo khóa vào Map |
| `groupingBy(classifier, downstream)` | Nhóm rồi tổng hợp từng nhóm |
| `toMap(keyMapper, valueMapper, mergeFunction)` | Tạo map, xử lý khóa trùng theo merge |
| `counting()` | Đếm số phần tử thành `Long` |
| `summingInt(mapper)` | Cộng một thuộc tính kiểu int |
| `summarizingInt(mapper)` | Tổng hợp count, sum, min, max, average |
| `partitioningBy(predicate)` | Phân vùng dữ liệu theo true/false |

**Không nhầm `Stream.toList()` với `Collectors.toList()`.** Từ Java 16, `Stream.toList()` trả danh sách không sửa được qua API. `Collectors.toList()` **không cam kết** khả năng sửa hoặc implementation cụ thể; nếu cần chắc chắn một `ArrayList` mutable, dùng `Collectors.toCollection(ArrayList::new)`.

Ngoài ra `Collectors.toSet()` không hứa thứ tự; nếu cần bảo toàn thứ tự chèn, `Collectors.toCollection(LinkedHashSet::new)` là lựa chọn rõ ràng.

## 7. Chương trình Java 17: collect thành list, set và map

Lưu thành **`CollectContainersDemo.java`**:

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeMap;
import java.util.Map;
import java.util.stream.Collectors;

public class CollectContainersDemo {
    public static void main(String[] args) {
        List<String> words = List.of(
                "java", "stream", "java", "lambda", ""
        );

        List<String> mutable = words.stream()
                .filter(s -> !s.isBlank())
                .collect(Collectors.toCollection(ArrayList::new));
        mutable.add("extra");

        Set<String> unique = words.stream()
                .filter(s -> !s.isBlank())
                .collect(Collectors.toCollection(LinkedHashSet::new));

        Map<Integer, Long> byLength = List.of("a", "bb", "ccc", "dd", "e")
                .stream()
                .collect(Collectors.groupingBy(
                        String::length,
                        TreeMap::new,
                        Collectors.counting()));

        String joined = words.stream()
                .filter(s -> !s.isBlank())
                .collect(Collectors.joining(","));

        System.out.println("mutable=" + mutable);
        System.out.println("unique=" + unique);
        System.out.println("byLength=" + byLength);
        System.out.println("joined=" + joined);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 CollectContainersDemo.java
java CollectContainersDemo
```

**Stdout chính xác:**

```text
mutable=[java, stream, java, lambda, extra]
unique=[java, stream, lambda]
byLength={1=2, 2=2, 3=1}
joined=java,stream,java,lambda
```

`ArrayList` được yêu cầu cụ thể qua supplier nên kết quả có thể `add` thêm phần tử. `LinkedHashSet` loại trùng và giữ thứ tự chèn của những phần tử được duyệt tuần tự. `TreeMap` sắp xếp khóa độ dài tăng dần để hiển thị map có thứ tự xác định. `joining(",")` nối các chuỗi trong encounter order mà không tự viết phép reduce tạo chuỗi trung gian liên tiếp.

## 8. Vì sao mutable identity trong reduce nguy hiểm?

Đây là lỗi rất phổ biến khi mới học `reduce`: người viết muốn gom các phần tử vào `ArrayList` hoặc `StringBuilder`, nên dùng một container mutable làm **identity** rồi sửa nó trong accumulator.

**Ví dụ chống chỉ định — không sử dụng:**

```java
// KHÔNG AN TOÀN, nhất là với parallelStream():
List<String> collected = List.of("A", "B", "C")
        .parallelStream()
        .reduce(
                new ArrayList<String>(),
                (list, text) -> {
                    list.add(text);       // sửa list dùng làm identity
                    return list;
                },
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        );
```

Đoạn trên **biên dịch được** nếu có import `List` và `ArrayList`, nhưng vi phạm hợp đồng giảm giá trị: accumulator thay đổi object được chia sẻ làm identity; khi parallel, cùng đối tượng mutable có thể tham gia nhiều phép giảm và gây race condition hoặc kết quả sai/nhân lặp. Đừng cố sửa bằng vài phép `synchronized` mà vẫn giữ mô hình gộp sai.

**Cách sửa: dùng collect** để framework tạo container riêng cho các phần việc:

```java
List<String> collected = List.of("A", "B", "C")
        .parallelStream()
        .collect(
                ArrayList::new,
                ArrayList::add,
                ArrayList::addAll
        );
```

Đoạn này là mảnh mã độc lập với mảnh trên (nếu đặt cả hai trong một phương thức, đặt tên biến khác nhau). `collect(supplier, accumulator, combiner)` tạo các `ArrayList` mới khi cần, thêm từng giá trị vào container riêng, rồi gộp các phần. Với nguồn List có thứ tự, kết quả giữ encounter order theo hợp đồng phù hợp của Stream; không sử dụng một `ArrayList` ngoài pipeline làm mục tiêu `forEach` song song.

**Chú ý:** một cách sửa khác như `reduce(new ArrayList<>(), (list, x) -> { List copy = new ArrayList(list); copy.add(x); return copy; }, ...)` có thể tránh sửa identity nhưng tạo rất nhiều bản sao. Khi mục tiêu là xây dựng danh sách, `collect` đơn giản và tự nhiên hơn.

## 9. Dùng StringBuilder trong collect thay vì reduce nối chuỗi

Nối chuỗi minh họa được bằng `reduce`:

```java
String joined = Stream.of("A", "B", "C")
        .reduce("", String::concat); // "ABC"
```

Đây là mảnh mã cần `import java.util.stream.Stream;`. Cú pháp đúng nhưng với nhiều chuỗi, mỗi lần nối thường tạo một `String` trung gian vì String bất biến.

Nếu chỉ cần nối chuỗi, thường nên dùng:

```java
String joined = Stream.of("A", "B", "C")
        .collect(java.util.stream.Collectors.joining(",")); // "A,B,C"
```

Nếu cần xây dựng một chuỗi theo cách tùy chỉnh, có thể dùng `collect` ba đối số với `StringBuilder`:

```java
StringBuilder builder = Stream.of("A", "B", "C")
        .collect(
                StringBuilder::new,
                (b, text) -> b.append(text),
                (left, right) -> left.append(right)
        );
String result = builder.toString(); // "ABC"
```

Đây là mảnh mã minh họa, mỗi Stream được tạo mới. Supplier `StringBuilder::new` cung cấp container cho mỗi phần tích lũy; accumulator và combiner có thể sửa container riêng của phần việc. Vì kết quả mong muốn là `String`, `Collectors.joining` thường ngắn gọn và rõ nghĩa hơn.

**Không dùng `reduce(new StringBuilder(), StringBuilder::append, StringBuilder::append)` cho pipeline song song**: identity mutable có thể bị dùng lại ở các nhánh, làm vi phạm yêu cầu về toán tử không side effect và tính đúng đắn của reduction.

## 10. Chương trình Java 17: collect ba đối số và parallel an toàn

Lưu thành **`ParallelCollectDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

public class ParallelCollectDemo {
    public static void main(String[] args) {
        List<String> letters = List.of("A", "B", "C", "D");

        List<String> direct = letters.parallelStream()
                .collect(
                        ArrayList::new,
                        ArrayList::add,
                        ArrayList::addAll
                );

        List<String> viaCollector = letters.parallelStream()
                .collect(Collectors.toCollection(ArrayList::new));

        String joined = letters.parallelStream()
                .collect(Collectors.joining("-"));

        int totalLength = letters.parallelStream()
                .reduce(
                        0,
                        (length, letter) -> length + letter.length(),
                        Integer::sum
                );

        System.out.println("direct=" + direct);
        System.out.println("collector=" + viaCollector);
        System.out.println("joined=" + joined);
        System.out.println("length=" + totalLength);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ParallelCollectDemo.java
java ParallelCollectDemo
```

**Stdout chính xác:**

```text
direct=[A, B, C, D]
collector=[A, B, C, D]
joined=A-B-C-D
length=4
```

Các nguồn ở ví dụ là List có encounter order. Các phép collect tuân thủ hợp đồng thứ tự và có cách kết hợp các phần tích lũy tương thích, nên kết quả giữ thứ tự này dù các bước xử lý có thể chạy trên nhiều thread. `reduce` sử dụng số nguyên bất biến và phép cộng kết hợp được. Không có `ArrayList` chia sẻ từ bên ngoài các terminal operations.

Đừng suy luận rằng parallel stream luôn nhanh hơn; bốn chuỗi quá nhỏ để làm benchmark hiệu năng nghiêm túc. Ví dụ chỉ nhằm chứng minh cách dùng API **đúng về ngữ nghĩa**.

## 11. Collect có thể trả về kết quả bất biến

Một ngộ nhận thường gặp: “collect dùng mutable container nên kết quả cuối cùng luôn mutable”. Điều này sai: một collector có thể dùng container mutable **trong lúc tích lũy**, rồi áp dụng finisher để tạo kiểu kết quả khác, bao gồm một đối tượng bất biến.

Ví dụ:

```java
List<String> immutable = Stream.of("A", "B")
        .collect(java.util.stream.Collectors.toUnmodifiableList());
```

Đoạn minh họa trả về List không hỗ trợ sửa qua API; `immutable.add("C")` sẽ ném `UnsupportedOperationException`. Nó còn không chấp nhận phần tử null. Tương tự, `Stream.toList()` (Java 16+) trả danh sách không sửa được mà không cần gọi `collect`.

Collector `collectingAndThen(downstream, finisher)` có thể chuyển kết quả downstream thành dạng cuối theo ý định, nhưng cần kiểm tra chính xác yêu cầu bất biến và aliasing của object bên trong. Một List không sửa được cấu trúc vẫn có thể chứa các object mutable.

**Quyết định dựa vào cách tích lũy và hợp đồng đầu ra:**
- Cần biến đổi thuần ra một giá trị? Thường `reduce`.
- Cần gom/nhóm vào container? Thường `collect`.
- Cần list bất biến cuối cùng? Chọn `toList`, `toUnmodifiableList` hoặc collector/finisher phù hợp, không nhất thiết dùng `reduce`.

## 12. Cùng một bài toán, hai cách biểu đạt: số liệu bán hàng

Giả sử mỗi bản ghi bán hàng có `category` và `quantity`. Ta muốn:
- Tính tổng số lượng của tất cả các bản ghi.
- Có thống kê số bản ghi, tổng, min, max, trung bình.
- Gom tổng số lượng theo từng danh mục.

**Tổng số lượng** là một giá trị kết hợp, nên dùng `reduce` hoặc `mapToInt(...).sum()`.

**Thống kê và grouping** cần trạng thái tổng hợp và cấu trúc kết quả, nên dùng `collect` với downstream collector.

Lưu thành **`SalesAggregationDemo.java`**:

```java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class SalesAggregationDemo {
    record Sale(String category, int quantity) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("A", 2),
                new Sale("B", 3),
                new Sale("A", 4)
        );

        int totalReduce = sales.stream()
                .map(Sale::quantity)
                .reduce(0, Integer::sum);

        int totalPrimitive = sales.stream()
                .mapToInt(Sale::quantity)
                .sum();

        IntSummaryStatistics stats = sales.stream()
                .collect(Collectors.summarizingInt(Sale::quantity));

        Map<String, Integer> quantityByCategory = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::category,
                        TreeMap::new,
                        Collectors.summingInt(Sale::quantity)
                ));

        String categories = sales.stream()
                .map(Sale::category)
                .distinct()
                .collect(Collectors.joining(","));

        System.out.println("reduceTotal=" + totalReduce);
        System.out.println("primitiveTotal=" + totalPrimitive);
        System.out.println("count=" + stats.getCount());
        System.out.println("min=" + stats.getMin());
        System.out.println("max=" + stats.getMax());
        System.out.println("average=" + stats.getAverage());
        System.out.println("byCategory=" + quantityByCategory);
        System.out.println("categories=" + categories);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 SalesAggregationDemo.java
java SalesAggregationDemo
```

**Stdout chính xác:**

```text
reduceTotal=9
primitiveTotal=9
count=3
min=2
max=4
average=3.0
byCategory={A=6, B=3}
categories=A,B
```

`map(Sale::quantity).reduce(0, Integer::sum)` và `mapToInt(...).sum()` cùng cho kết quả 9; cách dùng primitive stream tránh boxing cho bước tổng. `summarizingInt` là collector thống kê nhiều chỉ số trong một terminal. `groupingBy` kết hợp `summingInt` tạo tổng theo từng category; `TreeMap` làm thứ tự hiển thị khóa xác định. `joining` chỉ có nhiệm vụ nối chuỗi danh mục sau khi loại trùng.

**Lưu ý:** những phép tổng `int` này có thể tràn khi số lượng quá lớn. Nếu tổng có thể vượt miền `int`, hãy dùng `mapToLong`/`summingLong` và chính sách kiểm tra tràn phù hợp, không chỉ đổi tên terminal operation.

## 13. Dùng reduce với record bất biến cho trạng thái tổng hợp

`reduce` không chỉ dùng cho một số nguyên. Một record bất biến có thể biểu diễn kết quả tổng hợp; mỗi bước tạo một giá trị mới và combiner gộp hai kết quả mà không sửa đối tượng chung.

Ví dụ:

```java
record CountSum(long count, long sum) {
    CountSum addValue(int value) {
        return new CountSum(count + 1, sum + value);
    }

    CountSum combine(CountSum other) {
        return new CountSum(count + other.count, sum + other.sum);
    }
}
```

Đây là mảnh khai báo record hợp lệ trong Java 17, đặt ở cấp top-level hoặc nested trong class. Khi dùng trong một phương thức:

```java
CountSum statistics = List.of(2, 3, 5)
        .parallelStream()
        .reduce(
                new CountSum(0L, 0L),
                (result, value) -> result.addValue(value),
                CountSum::combine
        );
// CountSum[count=3, sum=10]
```

Ở đây identity `CountSum(0,0)` là bất biến; accumulator trả record mới với count tăng 1 và sum cộng thêm value; combiner gộp hai record. Thiết kế này **phù hợp về mặt ngữ nghĩa** với `reduce` song song.

Tuy nhiên, nếu dữ liệu rất lớn và thao tác gộp tạo ra object mới quá thường xuyên, collector thống kê có thể giảm số lần cấp phát. **Đúng về ngữ nghĩa không đồng nghĩa tối ưu hiệu năng**. Hãy chọn API theo mục tiêu rồi đo nếu throughput/latency quan trọng.

## 14. Collect và xử lý song song: các quy tắc an toàn

Parallel Stream có thể chia dữ liệu thành phần việc rồi tổng hợp kết quả theo thứ tự tương thích với hợp đồng Stream. Vì vậy:

1. **Không sửa container do bên ngoài cung cấp** từ nhiều callback `forEach`. Ví dụ `List<String> result = new ArrayList<>(); source.parallelStream().forEach(result::add);` không an toàn.
2. **Với `collect` ba đối số**, supplier phải tạo được container độc lập, accumulator cập nhật đúng container được giao, combiner kết hợp hai container đúng ý nghĩa. Tránh giữ một singleton accumulator bên ngoài.
3. **Với Collector có sẵn**, ví dụ `toList`, `groupingBy`, `toCollection`, để Stream framework quản lý containers; không cần tự thêm `synchronized` quanh mọi thao tác.
4. **Không kết luận Collector nào cũng có đặc tính `CONCURRENT`**. Nhiều collector bình thường vẫn dùng được với parallel Stream bằng cách tạo nhiều container và gộp. Collector concurrent có quy tắc riêng về container chia sẻ, unordered và tính an toàn của accumulator.
5. **Giữ encounter order khi nghiệp vụ cần.** Nếu nguồn là List có thứ tự, các collector phù hợp thường duy trì thứ tự kết quả; nếu nguồn unordered, không tự giả định phần tử đầu tiên luôn được giữ.
6. **Phép reduce phải associative và identity đúng.** Với `double`, khác biệt thứ tự gộp có thể tạo khác biệt làm tròn; ứng dụng cần định nghĩa độ sai lệch chấp nhận được.

Số thread và mức tăng tốc không được bảo đảm. Hãy benchmark trên dữ liệu thực với công cụ phù hợp (ví dụ JMH) thay vì cho rằng cứ `parallelStream()` là tốt hơn.

## 15. Những lỗi phổ biến

1. **Dùng `reduce(new ArrayList<>(), ...)` và sửa chính list identity:** sai hợp đồng, nguy hiểm trong parallel.
2. **Cho rằng collect chỉ trả mutable List:** `toUnmodifiableList`, `collectingAndThen` có thể trả kết quả không sửa được.
3. **Cho rằng `Collectors.toList()` luôn là `ArrayList`:** API không bảo đảm implementation hoặc khả năng sửa.
4. **Cho rằng `Stream.toList()` và `Collectors.toList()` là một:** khác nhau về hợp đồng đầu ra.
5. **Dùng phép trừ với reduce song song:** không associative.
6. **Chọn sai identity:** dùng 0 cho phép nhân làm mọi kết quả thành 0.
7. **Combiner sai logic:** accumulator cộng còn combiner nhân; tuần tự có thể tưởng đúng nhưng song song sai.
8. **Giữ accumulator mutable ở field/biến ngoài pipeline:** shared mutable state có thể gây race condition.
9. **Dùng `reduce` nối rất nhiều String:** có thể tạo nhiều String trung gian; `joining` phù hợp hơn.
10. **Dùng `collect` chỉ để tính tổng một số:** thường có `sum` hoặc `reduce` đơn giản hơn.
11. **Dùng `toSet` rồi mong thứ tự giống List nguồn:** Set collector không bảo đảm thứ tự; chọn `LinkedHashSet` hoặc cấu trúc phù hợp.
12. **Lấy kết quả `Optional` bằng `get()` khi reduce không có identity:** Stream rỗng có thể làm `get()` ném lỗi.
13. **Tin rằng tất cả collector đều thread-safe để sửa từ ngoài:** framework quản lý lifecycle/container; không tự do sửa cùng một container từ nhiều thread.
14. **Không kiểm soát null:** `toUnmodifiableList` không chấp nhận null; một số collector và mapper cũng có hạn chế riêng.
15. **Dùng parallel chỉ vì reduce/collect hỗ trợ:** overhead và tính chất dữ liệu quyết định lợi ích thực tế.
16. **Trộn bước giảm bất biến và tác dụng phụ I/O:** khó kiểm thử, khó đảm bảo thứ tự và dễ lỗi khi song song.

## 16. Bảng quyết định cuối cùng

| Đặc điểm yêu cầu | Lựa chọn ưu tiên |
| --- | --- |
| Có phép kết hợp giá trị thuần, associative và identity phù hợp | `reduce` |
| Chỉ muốn tổng/min/max/count từ primitive stream | `sum`/`min`/`max`/`count` |
| Muốn tập/danh sách từ nhiều phần tử | `toList()` hoặc `collect` |
| Cần định rõ container mutable (ArrayList, LinkedHashSet) | `collect(toCollection(...))` |
| Cần nhóm/đếm theo khóa | `collect(groupingBy(...))` |
| Cần tạo Map, xử lý key trùng | `collect(toMap(..., mergeFunction))` |
| Cần nối chuỗi với delimiter | `collect(joining(delimiter))` |
| Cần nhiều thống kê trong một lượt | `collect(summarizingInt(...))` |
| Muốn giảm nhiều phần tử thành record bất biến | `reduce` có accumulator/combiner thuần |
| Đang tích lũy bằng cách sửa object container | `collect` thay vì mutable identity của `reduce` |

**Đường quyết định gọn:** Nếu câu trả lời là “**gộp các giá trị bằng một toán tử thuần**”, hãy xem `reduce`. Nếu câu trả lời là “**tạo hoặc cập nhật một bộ chứa kết quả**”, hãy xem `collect` hoặc terminal chuyên dụng. Khi có API chuyên dụng rõ hơn (như `sum`, `toList`, `joining`, `groupingBy`), ưu tiên cách biểu đạt đó.

## 17. Tự kiểm tra và đáp án

**Câu 1.** `Stream.of(1,2,3).reduce(0, Integer::sum)` trả gì?

**Đáp án:** `6`, vì 0 là identity của phép cộng.

**Câu 2.** `Stream.<Integer>empty().reduce(Integer::max)` trả gì?

**Đáp án:** `Optional.empty()`; không có identity và không có phần tử.

**Câu 3.** Cần tạo `ArrayList<String>` có thể thêm phần tử sau khi thu thập. Dùng `reduce` hay `collect`?

**Đáp án:** `collect(Collectors.toCollection(ArrayList::new))`. Đây là yêu cầu xây dựng container mutable.

**Câu 4.** Vì sao `parallelStream().reduce(new ArrayList<>(), (list,x) -> { list.add(x); return list; }, ...)` không an toàn?

Vì sửa mutable identity phá vỡ hợp đồng reduction và các phần việc song song có thể cùng ảnh hưởng tới object. Dùng `collect` với supplier tạo container mới.

**Câu 5.** `Collectors.toList()` có hứa trả một `ArrayList` mutable không?

**Không.** Nếu cần `ArrayList`, dùng `toCollection(ArrayList::new)`. `Stream.toList()` thì được quy định trả list không sửa được.

**Câu 6.** Tính tổng `quantity` cho từng `category` nên dùng gì?

**Đáp án:** `collect(groupingBy(Sale::category, summingInt(Sale::quantity)))` hoặc biến thể chọn Map cụ thể. Đây là tổng hợp theo nhóm, không chỉ một phép giảm về một số.

**Câu 7.** Toán tử combiner của `reduce(identity, accumulator, combiner)` phải có quan hệ gì với accumulator?

**Đáp án:** Phải gộp được các kết quả `U` đúng ngữ nghĩa, associative, identity đúng và tương thích với việc accumulator thêm một phần tử: `combiner(u, accumulator(identity,t))` tương đương `accumulator(u,t)`.

**Câu 8.** Khi cần nối rất nhiều chuỗi bằng dấu phẩy, `reduce("", String::concat)` hay `Collectors.joining(",")` hợp lý hơn?

**Đáp án:** `Collectors.joining(",")`, vì biểu đạt delimiter trực tiếp và tránh chuỗi trung gian không cần thiết.

**Ghi nhớ:** **`reduce()` dành cho phép kết hợp giá trị đúng luật (identity, associativity, compatibility); `collect()` dành cho tích lũy qua container/collector.** Không dùng container mutable làm identity rồi sửa trong `reduce`. Hãy chọn terminal dựa vào bản chất kết quả và sự an toàn khi chia/gộp, không chỉ vì một cú pháp trông ngắn hơn.
