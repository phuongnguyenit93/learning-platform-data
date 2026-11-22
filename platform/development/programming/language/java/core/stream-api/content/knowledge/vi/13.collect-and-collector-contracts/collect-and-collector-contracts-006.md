# Hợp đồng đơn vị, kết hợp và tính tương đương của Collector

Trong Java Stream API, `collect(Collector)` là thao tác kết thúc (*terminal operation*) dùng để **tích lũy các phần tử của Stream thành một kết quả**. Có thể thu thập thành `List`, `Set`, `Map`, thống kê, chuỗi hoặc một đối tượng tổng hợp tự thiết kế. Tuy nhiên, một `Collector` tùy chỉnh chỉ đúng khi tuân thủ **hợp đồng đơn vị (identity)**, **hợp đồng kết hợp (associativity)** và **tính tương đương (equivalence)**. Ba khái niệm này đặc biệt quan trọng khi Stream được xử lý song song, vì runtime được quyền chia dữ liệu thành các phần rồi kết hợp kết quả từng phần.

Bài thuộc chương **Cơ chế collect và Collector** của module **JAVA_STREAM_API**. Mục tiêu là hiểu sâu các hợp đồng cần có trước khi tự viết collector, sử dụng `groupingBy` với downstream collector hoặc đánh giá kết quả trên parallel stream. Kiến thức này nối với pipeline lazy, `filter`, `map`, `reduce`, `collect`, `Spliterator` và những giới hạn của thuật toán khi có trạng thái, tài nguyên và yêu cầu hiệu năng.

## 1. Collector gồm những bộ phận nào?

Giao diện tổng quát là `java.util.stream.Collector<T, A, R>`, với:

- **`T`**: kiểu phần tử đầu vào của Stream.
- **`A`**: kiểu *bộ tích lũy trung gian* (*mutable accumulation type*).
- **`R`**: kiểu kết quả trả về sau khi thu thập xong.

Một collector mô tả năm thành phần:

| Thành phần | Kiểu hàm | Trách nhiệm |
|---|---|---|
| `supplier()` | `Supplier<A>` | Tạo một bộ tích lũy mới ở trạng thái rỗng |
| `accumulator()` | `BiConsumer<A, T>` | Đưa một phần tử đầu vào vào bộ tích lũy |
| `combiner()` | `BinaryOperator<A>` | Gộp hai bộ tích lũy trung gian |
| `finisher()` | `Function<A, R>` | Chuyển bộ tích lũy thành kết quả |
| `characteristics()` | `Set<Characteristics>` | Công bố tính chất như `UNORDERED`, `CONCURRENT`, `IDENTITY_FINISH` |

Ví dụ, collector tạo danh sách có thể:

1. Tạo `ArrayList` rỗng bằng supplier.
2. Thêm từng phần tử vào danh sách của một nhánh bằng accumulator.
3. Ghép danh sách từ các nhánh bằng combiner.
4. Trả chính danh sách tích lũy làm kết quả (không cần biến đổi thêm).

Với Stream tuần tự, bạn có thể chỉ quan sát thấy một bộ tích lũy và không thấy combiner được gọi. Trên parallel stream, thư viện có quyền tạo nhiều bộ tích lũy, phân chia phần tử rồi gộp lại. **Collector hợp lệ phải cho kết quả tương đương giữa các cách phân hoạch đúng hợp đồng**, không phụ thuộc vào việc một ví dụ nhỏ có gọi combiner hay không.

```text
                     Stream<T>
                         |
                     chia phần
                /         |         \
           supplier   supplier    supplier
                |         |         |
          accumulator accumulator accumulator
                |         |         |
                A1        A2        A3
                \         /         |
                 combiner           |
                     \             /
                       combiner
                          |
                          A
                          |
                       finisher
                          |
                          R
```

Sơ đồ diễn tả **một cách thực thi có thể xảy ra**, không bắt buộc trình tự hoặc số lần gọi của mọi implementation. Với collector có đặc tính `CONCURRENT`, thư viện thậm chí có thể cho nhiều worker tích lũy đồng thời vào cùng một container khi đủ điều kiện.

## 2. Hợp đồng đơn vị: gộp với container rỗng không làm đổi ý nghĩa

Giả sử `a` là một bộ tích lũy hợp lệ đã chứa một số phần tử và `e = supplier.get()` là **một bộ tích lũy mới ở trạng thái rỗng**. Hợp đồng đơn vị yêu cầu:

```text
combiner(a, e)  ≈  a
```

Dấu `≈` biểu thị **tương đương về kết quả**, không bắt buộc phải là cùng một tham chiếu đối tượng. Combiner có thể sửa `a` rồi trả nó, hoặc tạo một bộ tích lũy khác, miễn kết quả cuối vẫn mang cùng ý nghĩa.

Ví dụ với danh sách:

```java
List<String> left = new ArrayList<>(Arrays.asList("A", "B"));
List<String> empty = new ArrayList<>();

left.addAll(empty);
System.out.println(left); // [A, B]
```

Thao tác ghép danh sách rỗng không làm thay đổi các phần tử. Một collector có supplier tạo danh sách rỗng và combiner ghép danh sách như vậy có **phần tử đơn vị đúng**.

### 2.1. Identity của Collector khác identity của Stream.reduce

Trong `stream.reduce(0, Integer::sum)`, `0` là **giá trị khởi đầu của phép cộng**. Trong `Collector`, “đơn vị” thường là **trạng thái tích lũy rỗng do supplier tạo ra**:

| Phép tổng hợp | Đơn vị phù hợp |
|---|---|
| `reduce(0, Integer::sum)` | Số `0` |
| Collector ghép `List` | Danh sách rỗng `[]` |
| Collector ghép `Set` | Tập hợp rỗng |
| Collector nối chuỗi | Bộ đệm chuỗi rỗng |
| Collector đếm và cộng số | Trạng thái `count = 0`, `sum = 0` |

Không được hiểu rằng supplier **luôn** trả `null` hoặc **luôn** trả số `0`. Nó phải trả một container mới hợp lệ, có trạng thái được combiner xem là đơn vị.

### 2.2. Ví dụ vi phạm hợp đồng đơn vị

```java
// SAI: combiner thêm -1 kể cả khi nhánh bên phải rỗng.
Collector<Integer, List<Integer>, List<Integer>> wrong =
        Collector.of(
                ArrayList::new,
                (list, number) -> list.add(number),
                (left, right) -> {
                    left.addAll(right);
                    left.add(-1);
                    return left;
                });
```

Nếu `left = [10, 20]` và `right = []` thì combiner trả `[10, 20, -1]`, không còn tương đương với `[10, 20]`. Collector này có thể tạo kết quả khác tùy cách Stream bị chia, kể cả khi dữ liệu đầu vào giống nhau.

Hợp đồng đơn vị nhấn mạnh **kết quả sau khi gộp**, không chỉ việc supplier tạo thành công một đối tượng.

## 3. Hợp đồng kết hợp: chia dữ liệu theo cách khác vẫn ra kết quả tương đương

Hợp đồng kết hợp (*associativity*) mạnh hơn việc “combiner có thể ghép hai container”. Nó đòi hỏi **đưa các phần tử vào một container liên tục** và **chia ra nhiều container rồi gộp** phải cho kết quả cuối tương đương.

Giả sử Stream chứa hai phần tử `t1`, `t2` theo thứ tự gặp:

**Cách A — tích lũy liên tiếp**

```text
a = supplier()
accumulator(a, t1)
accumulator(a, t2)
resultA = finisher(a)
```

**Cách B — chia thành hai nhánh và kết hợp**

```text
left  = supplier()
right = supplier()
accumulator(left,  t1)
accumulator(right, t2)
merged  = combiner(left, right)
resultB = finisher(merged)
```

Yêu cầu:

```text
resultA  ≈  resultB
```

Một phép gộp hợp lệ phải tiếp tục giữ tính chất này nếu dữ liệu được chia thành ba, bốn hoặc nhiều phần, với các phép gộp được nhóm khác nhau. Đối với collector **có thứ tự**, việc ghép cần bảo toàn thứ tự tương đối của các phân đoạn theo encounter order.

### 3.1. Ví dụ đúng: nối danh sách theo thứ tự

```java
Collector<Integer, List<Integer>, List<Integer>> toOrderedList =
        Collector.of(
                ArrayList::new,
                (list, value) -> list.add(value),
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });

List<Integer> collected = Stream.of(1, 2, 3, 4)
        .parallel()
        .collect(toOrderedList);

System.out.println(collected); // [1, 2, 3, 4]
```

Với nguồn có encounter order và collector không công bố `UNORDERED`, kết quả phải giữ thứ tự từ nguồn. Phép nối danh sách theo hướng **trái rồi phải** là kết hợp nhóm về mặt nội dung:

```text
([1] ++ [2]) ++ [3,4] = [1,2,3,4]
[1] ++ ([2] ++ [3,4]) = [1,2,3,4]
```

Ở đây `++` là phép nối danh sách. Nó **không giao hoán**: `[1] ++ [2]` khác `[2] ++ [1]`. Collector có thứ tự **không cần phép gộp giao hoán**; chỉ cần kết quả nhất quán với encounter order bất kể cách chia nhóm.

### 3.2. Ví dụ sai: combiner đánh mất một nhánh

```java
Collector<Integer, List<Integer>, List<Integer>> dropRight =
        Collector.of(
                ArrayList::new,
                (list, value) -> list.add(value),
                (left, right) -> left); // SAI: bỏ toàn bộ phần tử của right.
```

Tích lũy tuần tự `1` rồi `2` cho `[1, 2]`, nhưng nếu một nhánh chứa `[1]` và nhánh khác chứa `[2]` thì `combiner([1], [2])` chỉ còn `[1]`. Vì thế **không thỏa hợp đồng kết hợp**, dù kiểm thử trên một Stream tuần tự nhỏ có thể tình cờ thành công.

### 3.3. Sai lầm hay gặp: gộp trung bình của các nhóm bằng cách lấy trung bình tiếp

Giả sử muốn tính trung bình các số `[10, 20, 30]`. Nếu chia thành `[10]` và `[20, 30]` thì trung bình từng nhóm là `10` và `25`. Lấy tiếp trung bình của hai số này:

```text
(10 + 25) / 2 = 17.5    // SAI, vì hai nhóm có kích thước khác nhau.
(10 + 20 + 30) / 3 = 20 // ĐÚNG.
```

Không thể gộp hai **giá trị trung bình đơn lẻ** thành trung bình chung nếu thiếu **số lượng phần tử của mỗi nhóm**. Thiết kế đúng cần lưu tổng và số lượng:

```text
left:  sum = 10, count = 1
right: sum = 50, count = 2
merge: sum = 60, count = 3
finish: 60 / 3 = 20
```

Đây là lý do `A` (trạng thái tích lũy trung gian) có thể khác `R` (kết quả cuối). `Collector` được phép giữ thêm thông tin cần thiết để các nhánh được kết hợp chính xác.

## 4. Tính tương đương: kết quả phải giống nhau ở mức nào?

Hai cách thực thi không nhất thiết tạo ra **cùng đối tượng trong bộ nhớ**. Điều được yêu cầu là chúng cho kết quả **tương đương theo ý nghĩa của collector**. Tính tương đương được đánh giá trên kết quả sau bước hoàn tất, tức `finisher`, chứ không phải so địa chỉ của hai container.

Với collector **không công bố `UNORDERED`**, hai kết quả cuối thường được xem là tương đương theo `equals` trong hợp đồng của Collector, vì thứ tự phần tử có thể mang ý nghĩa nghiệp vụ. Ví dụ:

```java
List<Integer> a = Arrays.asList(1, 2, 3);
List<Integer> b = Arrays.asList(1, 2, 3);
List<Integer> c = Arrays.asList(3, 2, 1);

System.out.println(a.equals(b)); // true
System.out.println(a.equals(c)); // false: List.equals xét thứ tự.
```

Với collector có đặc tính `UNORDERED`, khái niệm tương đương được **nới lỏng đối với khác biệt chỉ do thứ tự**: thứ tự gặp phần tử không đóng góp vào kết quả nghiệp vụ. Ví dụ, tập hợp các mã sản phẩm được xem là cùng kết quả nếu chứa cùng phần tử, dù thứ tự duyệt của tập hợp khác nhau.

| Collector/đầu ra | Kết quả 1 | Kết quả 2 | Tương đương? |
|---|---|---|---|
| Collector tạo `List` có thứ tự | `[A, B]` | `[A, B]` | Có |
| Collector tạo `List` có thứ tự | `[A, B]` | `[B, A]` | Không |
| Collector thực sự `UNORDERED`, kết quả là tập hợp | `{A, B}` | `{B, A}` | Có, vì cùng phần tử |
| Bất kỳ collector phù hợp | Tổng bằng `100` | Tổng bằng `90` | Không |
| Bất kỳ collector phù hợp | Ba phần tử hợp lệ | Bị mất một phần tử | Không |

**Không được dùng `UNORDERED` để hợp thức hóa việc mất dữ liệu hoặc kết quả tính toán sai.** Khác biệt thứ tự là ngoại lệ được cho phép; khác biệt về số phần tử, tổng hoặc thành phần kết quả vẫn là vi phạm.

### 4.1. UNORDERED không có nghĩa “sắp xếp ngẫu nhiên”

`Characteristics.UNORDERED` có nghĩa collector **không cam kết bảo toàn encounter order**. Nó không yêu cầu đảo thứ tự, xáo trộn dữ liệu hay làm kết quả thay đổi giữa các lần chạy.

Nếu viết collector để tạo một danh sách có mục tiêu giữ vị trí, ví dụ báo cáo giao dịch hoặc kết quả phân trang, **không công bố `UNORDERED`** chỉ để hi vọng tăng tốc. Chỉ công bố khi thứ tự thực sự không làm thay đổi ý nghĩa của kết quả.

## 5. Ví dụ hoàn chỉnh Java 8: Collector tính trung bình theo hợp đồng

Ví dụ sau thiết kế collector tính trung bình tiền đơn bằng một bộ tích lũy chứa **tổng** và **số lượng**, rồi áp dụng trên Stream tuần tự, song song, nguồn rỗng và từng nhóm. Số tiền dùng `long` theo đơn vị nhỏ nhất; kết quả trung bình trả `OptionalDouble` để phân biệt nguồn rỗng. Đây là ví dụ minh họa về hợp đồng, giả định dữ liệu đủ nhỏ để không tràn `long` và sai số `double` được chấp nhận.

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.OptionalDouble;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class CollectorContractsDemo {
    static final class Sale {
        private final String category;
        private final long amountCents;

        Sale(String category, long amountCents) {
            this.category = category;
            this.amountCents = amountCents;
        }

        String getCategory() {
            return category;
        }

        long getAmountCents() {
            return amountCents;
        }
    }

    static final class SumCount {
        private long sum;
        private long count;

        void add(Sale sale) {
            sum += sale.getAmountCents();
            count++;
        }

        SumCount combine(SumCount other) {
            sum += other.sum;
            count += other.count;
            return this;
        }

        OptionalDouble finish() {
            return count == 0
                    ? OptionalDouble.empty()
                    : OptionalDouble.of((double) sum / count);
        }
    }

    public static void main(String[] args) {
        Collector<Sale, SumCount, OptionalDouble> averageCollector =
                Collector.of(
                        SumCount::new,    // supplier
                        SumCount::add,    // accumulator
                        SumCount::combine,// combiner
                        SumCount::finish  // finisher
                );

        List<Sale> sales = Arrays.asList(
                new Sale("Sách", 10),
                new Sale("Sách", 20),
                new Sale("Sách", 30),
                new Sale("Phụ kiện", 40)
        );

        OptionalDouble sequential = sales.stream()
                .collect(averageCollector);
        OptionalDouble parallel = sales.parallelStream()
                .collect(averageCollector);
        OptionalDouble empty = Collections.<Sale>emptyList()
                .stream()
                .collect(averageCollector);

        System.out.println(sequential.orElse(-1)); // 25.0
        System.out.println(parallel.orElse(-1));   // 25.0
        System.out.println(empty.isPresent());    // false

        Map<String, OptionalDouble> byCategory = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::getCategory,
                        averageCollector));

        System.out.println(byCategory.get("Sách").orElse(-1));
        // 20.0
        System.out.println(byCategory.get("Phụ kiện").orElse(-1));
        // 40.0
    }
}
```

**Vì sao collector này tuân hợp đồng?**

- **Đơn vị:** `new SumCount()` có `sum = 0` và `count = 0`; `combine(a, empty)` giữ nguyên cặp giá trị của `a`.
- **Kết hợp:** gộp các cặp bằng cách **cộng tổng với tổng, số lượng với số lượng**. Nếu không tràn `long`, tổng và số lượng cuối cùng không phụ thuộc cách nhóm các phép gộp.
- **Tương đương:** `finish` lấy `sum / count` khi có dữ liệu, hoặc trả `OptionalDouble.empty()` khi rỗng; trong dữ liệu ví dụ, các cách phân chia cho cùng kết quả số học.
- **Phân tách trạng thái:** các bộ `SumCount` khác nhau được tạo bằng supplier; collector **không khai báo `CONCURRENT`**, nên runtime xử lý chúng theo quy tắc cô lập container và kết hợp an toàn.
- **Kiểu trạng thái và kết quả khác nhau:** `A = SumCount`, `R = OptionalDouble`; không khai báo `IDENTITY_FINISH`.

Ở đây `SumCount` có thể thay đổi bên trong quá trình thu thập, nhưng không bị lộ cho caller, và mỗi phần tích lũy thuộc về quá trình collect. Khi cần tính số tiền với độ chính xác thập phân cao, hãy cân nhắc `BigDecimal` và chính sách làm tròn tại finisher thay cho `double`.

## 6. Đối chiếu hợp đồng bằng cách tự chia đầu vào

Để kiểm tra một collector, có thể tạo hai lối tích lũy tương đương: **một nhánh** và **nhiều nhánh kết hợp**. Đoạn độc lập dưới đây minh họa với collector danh sách hợp lệ; yêu cầu import `java.util.ArrayList`, `java.util.Arrays`, `java.util.List` và `java.util.stream.Collector`.

```java
Collector<Integer, List<Integer>, List<Integer>> collector =
        Collector.of(
                ArrayList::new,
                (list, number) -> list.add(number),
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });

// Tích lũy liên tục ba phần tử.
List<Integer> onePass = collector.supplier().get();
collector.accumulator().accept(onePass, 1);
collector.accumulator().accept(onePass, 2);
collector.accumulator().accept(onePass, 3);

// Tách thành hai nhánh: [1, 2] và [3].
List<Integer> left = collector.supplier().get();
List<Integer> right = collector.supplier().get();
collector.accumulator().accept(left, 1);
collector.accumulator().accept(left, 2);
collector.accumulator().accept(right, 3);
List<Integer> combined = collector.combiner().apply(left, right);

System.out.println(onePass.equals(combined)); // true
// Cả hai đều chứa [1, 2, 3].

// Gộp với container mới rỗng: hợp đồng đơn vị.
List<Integer> withEmpty =
        collector.combiner().apply(combined, collector.supplier().get());
System.out.println(withEmpty.equals(onePass)); // true
```

Đây là một phép kiểm tra **đại diện**, không chứng minh hợp đồng với mọi dữ liệu và mọi cách phân chia. Để kiểm tra kỹ hơn, nên thử cả nguồn rỗng, một phần tử, nhiều vị trí tách, nhiều cách ghép ba hoặc nhiều nhánh, các phần tử trùng nhau và nguồn có thứ tự.

Nếu collector không có `IDENTITY_FINISH`, phải so sánh **kết quả sau `finisher`** khi kiểm chứng tính tương đương. Đừng chỉ so `A.equals(...)` nếu trạng thái trung gian là một đối tượng không triển khai `equals` theo ý nghĩa kết quả.

## 7. Characteristics có thể thay đổi cách runtime thực hiện collect

`Collector.Characteristics` mô tả các tính chất mà implementation có thể dựa vào để tối ưu. Công bố đặc tính **không đúng thực tế** có thể làm chương trình sai trên parallel stream dù thử tuần tự vẫn chạy.

### 7.1. IDENTITY_FINISH: A chính là R

`IDENTITY_FINISH` nói rằng finisher thực chất là phép đồng nhất, có thể được bỏ qua: kiểu trạng thái tích lũy `A` có thể dùng trực tiếp như kết quả `R`.

```java
Collector<String, List<String>, List<String>> listCollector =
        Collector.of(
                ArrayList::new,
                (list, value) -> list.add(value),
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });
// Overload 3 thành phần này có đặc tính IDENTITY_FINISH.
```

Ví dụ trung bình ở phần 5 **không được** công bố `IDENTITY_FINISH` vì `SumCount` không phải `OptionalDouble`. Nếu khai báo sai, implementation có thể bỏ qua finisher và cố trả trạng thái trung gian như kết quả cuối, dẫn đến lỗi kiểu hoặc kết quả không đúng.

### 7.2. UNORDERED: kết quả không phụ thuộc encounter order

`UNORDERED` phù hợp khi ý nghĩa kết quả không dựa vào thứ tự, chẳng hạn thu thập các khóa vào một tập hợp. Nó có thể cho phép thư viện bỏ bớt ràng buộc thứ tự khi giảm song song.

```java
java.util.Set<String> unique = Stream.of("B", "A", "B")
        .parallel()
        .collect(Collectors.toSet());
// Nội dung tập hợp: {"A", "B"}, không cam kết thứ tự duyệt.
```

`Collectors.toSet()` là collector không có thứ tự (*unordered collector*). Ngược lại, collector tạo danh sách để giữ thứ tự giao dịch **không nên** được đánh dấu `UNORDERED`.

### 7.3. CONCURRENT: cho phép tích lũy đồng thời vào cùng container

`CONCURRENT` có nghĩa accumulator **được phép gọi đồng thời** bởi nhiều luồng trên cùng một container. Đây là cam kết về an toàn đồng thời mà collector phải thực sự đáp ứng.

Không phải cứ gọi `parallelStream()` thì collector cần `CONCURRENT`. Nếu collector **không concurrent**, framework vẫn có thể chia thành các container riêng, mỗi container được một nhánh xử lý, rồi hợp nhất bằng combiner. Cơ chế đó không yêu cầu mỗi `ArrayList` hay `SumCount` phải là đối tượng thread-safe.

Thông thường framework chỉ thực hiện một **concurrent reduction** trực tiếp vào container dùng chung khi collector có `CONCURRENT` **và** Stream không có encounter order, **hoặc** collector còn có `UNORDERED`. Do đó, hai đặc tính này không thể thêm tùy tiện chỉ để “bật chạy song song”.

| Characteristics | Cho phép gì? | Rủi ro nếu công bố sai |
|---|---|---|
| `IDENTITY_FINISH` | Bỏ qua phép chuyển đổi trạng thái thành kết quả | Trả sai kiểu hoặc bỏ mất bước finisher bắt buộc |
| `UNORDERED` | Không giữ thứ tự gặp phần tử trong kết quả | Kết quả dạng danh sách/báo cáo bị đổi thứ tự |
| `CONCURRENT` | Nhiều worker có thể dùng cùng accumulator container đồng thời | Race condition, mất dữ liệu hoặc hỏng cấu trúc |

**Ví dụ sai:** khai báo `CONCURRENT` cho collector sử dụng một `ArrayList` thường mà không đồng bộ hóa hoặc không có cấu trúc dữ liệu concurrent. Khi runtime được phép cùng gọi `list.add(...)` từ nhiều worker, `ArrayList` không bảo đảm an toàn luồng.

## 8. Những ràng buộc khác của vòng đời tích lũy

Ngoài ba hợp đồng chính, cách runtime quản lý container cũng quan trọng:

1. `supplier` phải cung cấp các bộ tích lũy mới, hợp lệ, có thể dùng độc lập. Không dùng một biến `static` giữ danh sách chung để mọi lần `supplier.get()` trả lại cùng đối tượng.
2. `accumulator` cần diễn đạt cách thêm phần tử vào trạng thái, không thay đổi nguồn dữ liệu, không phụ thuộc luồng cụ thể và không tự ý sửa các container của nhánh khác.
3. `combiner` phải ghép cả hai trạng thái theo đúng ngữ nghĩa và trả một trạng thái dùng được tiếp. Với mẫu mutable phổ biến, sửa container bên trái và trả nó là hợp lệ nếu không làm mất thông tin.
4. Nếu combiner hoặc finisher **không trả lại chính container được truyền vào**, collector implementation không được tiếp tục sử dụng container đã bị thay thế theo các quy tắc vòng đời. Đừng xây logic trông chờ một container cũ được gọi tích lũy trở lại.
5. Một container đã được chuyển cho combiner hoặc finisher không được đưa trở lại accumulator; vì thế việc đếm số lần gọi `accumulator` qua tác dụng phụ toàn cục không phải thước đo đáng tin của cách framework phân chia việc.

Các quy tắc này giúp việc tích lũy bằng **trạng thái mutable cục bộ** vẫn an toàn trong parallel stream. Chúng không cấp phép cho accumulator hoặc combiner sửa tùy ý mọi đối tượng mutable bên ngoài pipeline.

## 9. Collector và reduce: giống nhau ở phép kết hợp, khác nhau ở trạng thái

`reduce` và `collect` đều là phép rút gọn, nhưng khác về cách quản lý trạng thái:

| Tiêu chí | `reduce` | `collect(Collector)` |
|---|---|---|
| Phép tích lũy | Thường trả một giá trị mới hoặc giá trị có sẵn theo phép toán | Có thể sửa container trung gian `A` |
| Đối tượng tích lũy | Thường cùng kiểu với kết quả hoặc có phiên bản ba tham số cho khác kiểu | `A` có thể khác `R` |
| Tổ chức song song | Phải có phép accumulator/combiner hợp lệ, tính kết hợp | Supplier tạo container riêng, accumulator và combiner cùng tuân hợp đồng |
| Ví dụ phù hợp | Tính tổng, tích, min/max theo phép kết hợp thuần | List, Map, nhóm, thống kê nhiều đại lượng, collector tùy chỉnh |
| Điều cần tránh | Tác dụng phụ hoặc shared mutable identity | Supplier dùng lại chung container, combiner mất dữ liệu, Characteristics khai báo sai |

Ví dụ, nối chuỗi lớn bằng `Collectors.joining()` thường phù hợp hơn `reduce(String::concat)` nếu cần giảm chi phí tạo chuỗi trung gian. Tính tổng số nguyên bằng `IntStream.sum()` lại rõ nghĩa hơn cả hai khi chỉ cần một phép cộng.

**Lưu ý:** tính kết hợp nhóm trong toán học không đảm bảo kết quả dấu phẩy động **giống hệt theo bit** giữa mọi cách gộp, vì phép cộng `double` có sai số làm tròn. Với số tiền hoặc thống kê yêu cầu độ chính xác cao, hãy chọn kiểu số, thuật toán cộng và chính sách làm tròn tương ứng, thay vì coi việc Collector hợp đồng đúng là bảo đảm chính xác tuyệt đối.

## 10. Phân biệt lỗi contract và lỗi nghiệp vụ

| Hiện tượng | Nguyên nhân thường gặp | Hướng khắc phục |
|---|---|---|
| Chạy tuần tự đủ phần tử, song song bị mất vài phần tử | Combiner bỏ một nhánh hoặc supplier chia sẻ mutable container | Gộp đầy đủ hai nhánh; supplier tạo trạng thái độc lập |
| Cùng nguồn nhưng tổng/đếm sai tùy cách chia | Accumulator không tương thích với combiner hoặc dữ liệu tràn số | Thiết kế trạng thái có thể gộp, kiểm soát miền số |
| Trung bình song song sai khi nhóm có kích thước khác nhau | Gộp trung bình từng nhánh mà không giữ count | Gộp cặp (sum, count), chia ở finisher |
| Danh sách kết quả đổi thứ tự dù nghiệp vụ cần thứ tự | Đánh dấu `UNORDERED` không đúng | Giữ ràng buộc encounter order, ghép trái rồi phải |
| Kết quả bị `ClassCastException` hoặc mất bước chuyển kiểu | Đánh dấu `IDENTITY_FINISH` khi `A` khác `R` | Chỉ công bố khi finisher thực sự là identity |
| `ArrayList` bị hỏng khi thu thập đồng thời | Đánh dấu `CONCURRENT` cho container không an toàn | Bỏ characteristic hoặc dùng thiết kế concurrent thực sự |
| Nguồn rỗng trả một giá trị không hợp lý | Supplier không tạo trạng thái đơn vị hoặc finisher sai chính sách rỗng | Thiết kế rõ kết quả rỗng và kiểm tra identity |
| Kết quả khác nhau chỉ vì thứ tự duyệt `Set` | Nghiệp vụ đã phụ thuộc vào thứ tự không có bảo đảm | Sắp xếp rõ ràng hoặc thiết kế kết quả không phụ thuộc thứ tự |

## 11. Bài tập tự kiểm tra có đáp án

### Bài 1. Phần tử đơn vị của collector cộng số

Một collector dùng trạng thái `SumCount(sum, count)`, accumulator tăng `sum` và `count`. Supplier nên trả trạng thái nào?

**Đáp án:** `sum = 0` và `count = 0`. Gộp một trạng thái có dữ liệu với trạng thái này giữ nguyên cả tổng lẫn số lượng.

### Bài 2. Lỗi trong combiner

```java
(left, right) -> {
    left.addAll(right);
    left.add("END");
    return left;
}
```

**Câu hỏi:** Nếu `right` rỗng, hợp đồng nào bị vi phạm?

**Đáp án:** **Đơn vị** vì `combiner(left, empty)` làm xuất hiện thêm `"END"`. Ngoài ra, việc thêm phần tử theo mỗi lần combine còn khiến kết quả phụ thuộc số lần gộp, vi phạm hợp đồng kết hợp.

### Bài 3. Tính kết hợp nhưng không giao hoán

Nối `[A]` với `[B]` cho `[A, B]`, trong khi đảo hai nhánh cho `[B, A]`. Có thể dùng phép nối danh sách để làm combiner cho một collector có thứ tự không?

**Đáp án:** **Có**. Phép nối danh sách kết hợp nhóm nhưng không giao hoán. Collector có thứ tự phải ghép các phân đoạn theo encounter order, không yêu cầu tùy ý đảo nhánh.

### Bài 4. Characteristics cho collector tính trung bình

Một collector có `A = SumCount` và `R = OptionalDouble`, dùng finisher để chia `sum / count`. Có được khai báo `IDENTITY_FINISH` không?

**Đáp án:** **Không**, vì trạng thái trung gian và kết quả khác kiểu, đồng thời phải chạy finisher.

### Bài 5. Trung bình sau khi chia nhóm

Nhánh A chứa `[10]`, nhánh B chứa `[20, 30]`. Gộp trung bình các nhánh bằng cách lấy trung bình của `10` và `25` có đúng không?

**Đáp án:** **Sai**, kết quả `17.5`. Cần gộp `(sum=10, count=1)` và `(sum=50, count=2)` thành `(sum=60, count=3)`; kết quả đúng là `20`.

### Bài 6. Parallel có bắt buộc CONCURRENT không?

Collector dùng `ArrayList` riêng trên mỗi phân đoạn, combiner ghép danh sách bằng `addAll`. Có cần công bố `CONCURRENT` để dùng `parallelStream().collect(...)` không?

**Đáp án:** **Không**. Framework có thể tích lũy trên các container độc lập, rồi kết hợp. Chỉ công bố `CONCURRENT` khi thiết kế thực sự cho phép nhiều worker cùng cập nhật một container an toàn.

## 12. Checklist khi tự thiết kế Collector

Trước khi đưa collector vào ứng dụng, hãy tự kiểm tra:

1. **Đơn vị:** trạng thái do `supplier` tạo ra có thực sự “rỗng” và gộp vào một kết quả đã tích lũy không làm thay đổi ý nghĩa của nó?
2. **Kết hợp:** mọi cách chia đầu vào hợp lệ, tích lũy rồi gộp có dẫn đến cùng kết quả sau finisher không? Combiner có giữ đủ số phần tử, tổng, count và thứ tự cần thiết không?
3. **Tương đương:** tiêu chí so sánh kết quả đã rõ chưa? Nếu công bố `UNORDERED`, việc khác thứ tự có thật sự không quan trọng với nghiệp vụ không?
4. **Kiểu và đặc tính:** `A` khác `R` thì finisher có bắt buộc không? `IDENTITY_FINISH` và `CONCURRENT` có thật sự được bảo đảm không?
5. **Tài nguyên và trạng thái:** supplier có tạo bộ tích lũy độc lập, các hàm có tránh sửa nguồn và biến chia sẻ, dữ liệu số có thể tràn hoặc mất độ chính xác không?

Hãy bắt đầu với collector có sẵn như `Collectors.toList`, `toSet`, `groupingBy`, `summingLong` hoặc `summarizingLong` nếu chúng đáp ứng yêu cầu. Khi phải tự xây collector, **đơn vị, kết hợp và tương đương** chính là tiêu chuẩn để chương trình giữ đúng kết quả dù cách chia việc và thực thi của Stream thay đổi.
