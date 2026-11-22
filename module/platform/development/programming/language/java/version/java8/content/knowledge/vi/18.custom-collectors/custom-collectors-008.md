# Kiểm thử nhiều cách phân chia, gộp dữ liệu cho Collector tùy biến (Java 8)

Một `Collector` tùy biến có thể chạy **đúng với `stream()` tuần tự nhưng sai khi `parallelStream()` chia dữ liệu thành nhiều phần**. Nguyên nhân thường nằm ở `combiner`: quên gộp một vế, gộp trùng, dùng nhầm trạng thái dùng chung, hoặc kết hợp theo cách phụ thuộc vào vị trí đặt dấu ngoặc. Để đánh giá một `Collector` đúng đắn, cần **chủ động kiểm thử nhiều cách chia dữ liệu và nhiều cây gộp** chứ không chỉ chạy một ví dụ đầu vào.

Bài này thuộc nhóm **Collector tùy biến** của Java 8. Mọi mã đều dùng API hiện vẫn được hỗ trợ; phần quan trọng nhất là một chương trình kiểm thử độc lập, biên dịch được với Java 8, có kết quả dự kiến và phép so sánh với một thuật toán tham chiếu.

## 1. Vì sao kết quả thu thập có thể phụ thuộc cách chia?

Giả sử dữ liệu gốc có thứ tự:

```text
[4, -2, 7, 4, 0, 9, -2]
```

Một collector tính `count`, `sum`, `min`, `max` phải trả về:

```text
count=7, sum=20, min=-2, max=9
```

Nó phải đúng cả khi Stream xử lý lần lượt bảy phần tử lẫn khi dữ liệu được chia thành:

```text
P1 = [ 4, -2 ]
P2 = [ 7,  4, 0 ]
P3 = [ 9, -2 ]
```

Mỗi phần có một trạng thái tích lũy riêng, rồi framework có thể kết hợp các kết quả theo các hình dạng khác nhau:

```text
Cây gộp 1:       combine(combine(P1, P2), P3)

Cây gộp 2:       combine(P1, combine(P2, P3))

Dạng tuần tự:    add(add(add(...), item), item)
```

Nếu collector đúng, **kết quả cuối phải tương đương theo hợp đồng đầu ra** trong các cách phân chia hợp lệ. Với thống kê số nguyên trong bài, các trường kết quả phải bằng nhau chính xác. Với kết quả có thứ tự, có thể cần **giữ nguyên encounter order**; với kết quả không yêu cầu thứ tự, tiêu chuẩn tương đương cần xét đến tính không thứ tự.

### Bốn thành phần Collector cần kiểm thử

| Thành phần | Vai trò | Lỗi thường gặp |
| --- | --- | --- |
| `supplier()` | Cấp trạng thái tích lũy mới `A` | Trả singleton/collection dùng chung, gây ghi đè chéo |
| `accumulator()` | Đưa một phần tử `T` vào trạng thái `A` | Bỏ phần tử, cập nhật sai trường hoặc thay đổi dữ liệu nguồn |
| `combiner()` | Gộp hai trạng thái `A` thành một trạng thái `A` | Mất dữ liệu vế phải, đếm đôi, không giữ đúng quy tắc thứ tự |
| `finisher()` | Đổi `A` thành kết quả `R` | Trả trạng thái chưa hoàn chỉnh, để lộ mutable state hoặc xử lý tập rỗng sai |

Ký hiệu đầy đủ là `Collector<T, A, R>`: `T` là kiểu phần tử nguồn, `A` là kiểu tích lũy nội bộ, `R` là kiểu kết quả cuối. Khi `A` khác `R`, finisher thường đóng vai trò chuyển trạng thái nội bộ sang kết quả an toàn để sử dụng.

## 2. Các tính chất đúng đắn bắt buộc

### 2.1. Identity: gộp với phần rỗng không được đổi kết quả

Nếu `e = supplier.get()` là bộ chứa rỗng và `a` là bộ chứa đã tích lũy, phép gộp `combine(a, e)` phải tương đương với `a` về kết quả cuối. Một collector được thiết kế tốt cũng nên xử lý được vế rỗng bên trái khi cách chia dữ liệu tạo ra phần rỗng.

Ví dụ với bộ thống kê, trạng thái rỗng phải có tác dụng trung hòa:

```text
combine(stats([4,-2]), stats([])) → stats([4,-2])
combine(stats([]), stats([4,-2])) → stats([4,-2])
```

Giá trị identity khác nhau theo bài toán: tổng dùng 0, tích dùng 1, tập hợp dùng tập rỗng. Với `min/max`, nếu chưa có phần tử cần ghi nhận trạng thái **rỗng thật sự**; không lấy `Integer.MAX_VALUE` làm một giá trị dữ liệu giả trong kết quả công khai.

### 2.2. Associativity: đổi cấu trúc cây gộp vẫn tương đương

Với các kết quả phần `a, b, c`, phải kiểm tra:

```text
finish(combine(combine(a, b), c))
    tương đương
finish(combine(a, combine(b, c)))
```

Do `combiner` thường **mutate** một trạng thái rồi trả lại trạng thái đó, mỗi cây gộp trong bài kiểm thử cần dùng **những bộ chứa mới độc lập**. Không được lấy kết quả đã bị mutate ở cây thứ nhất để thử cây thứ hai.

### 2.3. Accumulator và combiner phải nhất quán

Tích lũy toàn bộ dữ liệu:

```text
add(a, x)
add(a, y)
```

phải tương đương với:

```text
left  = add(empty(), x)
right = add(empty(), y)
combine(left, right)
```

Nói cách khác, kết quả thu tuần tự không được khác kết quả thu thành nhiều phần rồi ghép. Chỉ kiểm tra `combine(a,b) == combine(b,a)` là **không đủ**: một số phép thu là **kết hợp (associative) nhưng không giao hoán (commutative)**, chẳng hạn ghép danh sách có thứ tự.

### 2.4. Định nghĩa kết quả tương đương trước khi viết test

- **Tổng, đếm, min/max với số nguyên trong miền không tràn:** kiểm tra chính xác từng trường.
- **Danh sách có thứ tự:** so sánh bằng `List.equals`; đảo các khối dữ liệu sẽ đổi thứ tự, đó có thể là hành vi đúng.
- **Tập hợp không thứ tự:** so sánh bằng `Set.equals` thay vì `toString()` hay thứ tự iterator.
- **`Map`:** so sánh khóa và giá trị bằng `Map.equals`, tránh suy ra thứ tự từ cách in `HashMap`.
- **Số thực dấu phẩy động:** phép cộng không có tính kết hợp toán học chính xác do làm tròn. Xác định tolerance hoặc phép tính tham chiếu phù hợp; nếu nghiệp vụ đòi tổng bất biến tuyệt đối, cần thiết kế kiểu tích lũy hoặc quy tắc số học thích hợp.

Trong test minh họa, `Summary.equals` định nghĩa rõ phép tương đương. Điều này tốt hơn kiểm tra chuỗi in ra, vì định dạng in có thể thay đổi mà dữ liệu vẫn đúng.

## 3. Thiết kế một Collector có combiner rõ ràng

Ta chọn nhiệm vụ dễ xác định tính đúng: thu các số nguyên thành bốn trường **count, sum, min, max**. Thành phần thực thi:

- `Acc` là **trạng thái mutable**, dùng trong quá trình thu.
- `Summary` là **kết quả bất biến** sau `finisher`.
- `Acc.add` tích lũy một phần tử.
- `Acc.combine` cộng count/sum và hợp nhất min/max của hai phần, trả về chính trạng thái bên trái.
- `Acc.finish` chuyển trạng thái tích lũy sang `Summary`; với nguồn rỗng, min và max là `null`, còn count/sum bằng 0.

Đây là mô hình *mutable reduction* hợp lệ nếu framework cấp bộ chứa riêng cho mỗi quá trình tích lũy. `Acc` không cần được biến thành cấu trúc thread-safe chỉ vì gọi `parallelStream()`: collector này **không** khai báo `CONCURRENT` nên việc kết hợp các bộ chứa riêng thuộc trách nhiệm của Stream framework. Nếu ứng dụng tự chia sẻ cùng một `Acc` qua nhiều luồng, đó là bài toán khác và không được collector này bảo đảm.

### Chữ ký factory

```java
// Đoạn minh họa trích từ lớp chạy đầy đủ ở mục 4:
static Collector<Integer, Acc, Summary> collector() {
    return Collector.of(
        Acc::new,      // supplier: trạng thái rỗng mới
        Acc::add,      // accumulator: thêm một số nguyên
        Acc::combine,  // combiner: gộp hai trạng thái
        Acc::finish    // finisher: chốt kết quả
    );
}
```

Không khai báo `IDENTITY_FINISH` vì `Acc` và `Summary` là hai kiểu khác nhau và finisher thực hiện phép biến đổi thật. Không khai báo `CONCURRENT` khi `Acc` không hỗ trợ nhiều luồng cập nhật **cùng một đối tượng** đồng thời. Những đặc tính này là cam kết về ngữ nghĩa, không phải công tắc bật để tăng tốc.

## 4. Chương trình kiểm thử độc lập: nhiều cách chia, hai cây gộp và parallel

Tệp **`CollectorPartitionTest.java`** dưới đây vừa định nghĩa collector tùy biến vừa thực hiện một bộ test có thể chạy trực tiếp.

Nó kiểm tra:

1. **Oracle độc lập:** tính kết quả tham chiếu bằng vòng `for`, không gọi collector đang được thử.
2. **Giá trị mong đợi cụ thể:** bộ mẫu có kết quả `count=7,sum=20,min=-2,max=9`.
3. **Tất cả cách chia thành ba đoạn liên tiếp:** chọn điểm cắt `i, j` với `0 <= i <= j <= n`, bao gồm đoạn rỗng, không chia, và trường hợp chỉ hai đoạn không rỗng.
4. **Cả hai cây gộp:** `(a+b)+c` và `a+(b+c)`, luôn tạo accumulator mới cho mỗi cây.
5. **Chạy tuần tự và song song:** so với oracle, không dựa vào scheduler chọn số phần hoặc thứ tự thực thi cụ thể.
6. **Dữ liệu đảo trộn với seed cố định:** vì phép thống kê này không phụ thuộc thứ tự, kết quả phải ổn định.
7. **Tập dữ liệu 10.000 phần tử:** giúp thử các lần phân chia thực tế của parallel Stream.
8. **Collector dùng làm downstream của `groupingBy`:** kiểm tra việc kết hợp trạng thái riêng trong từng nhóm.

```java
import java.util.*;
import java.util.stream.*;

public class CollectorPartitionTest {
    static final class Summary {
        final long count;
        final long sum;
        final Integer min;
        final Integer max;

        Summary(long count, long sum, Integer min, Integer max) {
            this.count = count;
            this.sum = sum;
            this.min = min;
            this.max = max;
        }

        @Override public boolean equals(Object obj) {
            if (!(obj instanceof Summary)) return false;
            Summary other = (Summary) obj;
            return count == other.count
                && sum == other.sum
                && Objects.equals(min, other.min)
                && Objects.equals(max, other.max);
        }

        @Override public int hashCode() {
            return Objects.hash(count, sum, min, max);
        }

        @Override public String toString() {
            return "count=" + count + ",sum=" + sum
                + ",min=" + min + ",max=" + max;
        }
    }

    static final class Acc {
        long count;
        long sum;
        int min = Integer.MAX_VALUE;
        int max = Integer.MIN_VALUE;

        void add(Integer x) {
            int value = Objects.requireNonNull(x, "input");
            count++;
            sum += value;
            min = Math.min(min, value);
            max = Math.max(max, value);
        }

        Acc combine(Acc right) {
            count += right.count;
            sum += right.sum;
            min = Math.min(min, right.min);
            max = Math.max(max, right.max);
            return this;
        }

        Summary finish() {
            return new Summary(count, sum,
                count == 0 ? null : min,
                count == 0 ? null : max);
        }
    }

    static Collector<Integer, Acc, Summary> collector() {
        return Collector.of(Acc::new, Acc::add,
                            Acc::combine, Acc::finish);
    }

    // Tích lũy đúng một đoạn; mỗi lần gọi tạo trạng thái mới.
    static Acc accumulate(List<Integer> part) {
        Acc a = new Acc();
        part.forEach(a::add);
        return a;
    }

    // Oracle độc lập với Collector và combiner đang được kiểm thử.
    static Summary reference(List<Integer> values) {
        long count = 0, sum = 0;
        Integer min = null, max = null;
        for (Integer x : values) {
            int v = Objects.requireNonNull(x, "input");
            count++;
            sum += v;
            min = min == null ? v : Math.min(min, v);
            max = max == null ? v : Math.max(max, v);
        }
        return new Summary(count, sum, min, max);
    }

    static void require(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static int testAllThreeWaySplits(List<Integer> values) {
        int n = values.size();
        Summary expected = reference(values);
        require(expected.equals(values.stream().collect(collector())),
                "sequential");

        int checks = 0;
        for (int i = 0; i <= n; i++) {
            for (int j = i; j <= n; j++) {
                List<Integer> a = values.subList(0, i);
                List<Integer> b = values.subList(i, j);
                List<Integer> c = values.subList(j, n);

                // Cây 1: (a + b) + c.
                Summary leftTree = accumulate(a)
                    .combine(accumulate(b))
                    .combine(accumulate(c))
                    .finish();

                // Cây 2: a + (b + c). Dùng trạng thái mới!
                Summary rightTree = accumulate(a)
                    .combine(accumulate(b).combine(accumulate(c)))
                    .finish();

                require(expected.equals(leftTree),
                        "left tree i=" + i + " j=" + j);
                require(expected.equals(rightTree),
                        "right tree i=" + i + " j=" + j);
                checks++;
            }
        }
        return checks;
    }

    static final class Row {
        final String category;
        final int points;

        Row(String category, int points) {
            this.category = category;
            this.points = points;
        }
    }

    static Map<String, Summary> group(
            List<Row> rows, boolean parallel) {
        Stream<Row> stream = parallel
            ? rows.parallelStream() : rows.stream();

        return stream.collect(Collectors.groupingBy(
            r -> r.category,
            TreeMap::new,
            Collectors.mapping(r -> r.points, collector())));
    }

    public static void main(String[] args) {
        List<Integer> sample =
            Arrays.asList(4, -2, 7, 4, 0, 9, -2);
        Summary expected = new Summary(7, 20, -2, 9);

        require(expected.equals(reference(sample)),
                "independent reference");
        require(expected.equals(sample.stream().collect(collector())),
                "sample golden");

        int splits = 0;
        splits += testAllThreeWaySplits(
            Collections.<Integer>emptyList());
        splits += testAllThreeWaySplits(
            Collections.singletonList(5));
        splits += testAllThreeWaySplits(
            Arrays.asList(4, 4, -1, 0));
        splits += testAllThreeWaySplits(sample);

        // Supplier không được trả cùng một trạng thái dùng chung.
        Acc freshA = collector().supplier().get();
        Acc freshB = collector().supplier().get();
        require(freshA != freshB,
                "supplier creates independent accumulators");

        // Xáo trộn có seed để tái lập lỗi khi cần.
        Random random = new Random(2026L);
        for (int round = 0; round < 30; round++) {
            List<Integer> shuffled = new ArrayList<>(sample);
            Collections.shuffle(shuffled, random);

            require(expected.equals(
                shuffled.stream().collect(collector())),
                "shuffle sequential " + round);
            require(expected.equals(
                shuffled.parallelStream().collect(collector())),
                "shuffle parallel " + round);
        }

        // Thử bộ dữ liệu lớn để chạy trên nhiều phần thực tế.
        List<Integer> large = IntStream.range(0, 10000)
            .boxed().collect(Collectors.toList());
        Summary largeExpected =
            new Summary(10000, 49995000, 0, 9999);
        require(largeExpected.equals(reference(large)),
                "large reference");

        for (int round = 0; round < 20; round++) {
            require(largeExpected.equals(
                large.parallelStream().collect(collector())),
                "large parallel " + round);
        }

        // Dùng collector tùy biến bên trong groupingBy.
        List<Row> rows = Arrays.asList(
            new Row("West", 1), new Row("East", 2),
            new Row("West", 3), new Row("East", 5));

        Map<String, Summary> expectedGroups = new TreeMap<>();
        expectedGroups.put("East", new Summary(2, 7, 2, 5));
        expectedGroups.put("West", new Summary(2, 4, 1, 3));

        require(expectedGroups.equals(group(rows, false)),
                "group sequential");
        require(expectedGroups.equals(group(rows, true)),
                "group parallel");

        System.out.println("sample=" + expected);
        System.out.println("splitTrees=" + splits);
        System.out.println("large=" + largeExpected);
        System.out.println("grouped=" + expectedGroups);
        System.out.println("PASS");
    }
}
```

Chạy với JDK 8 trở lên:

```bash
javac -encoding UTF-8 CollectorPartitionTest.java
java CollectorPartitionTest
```

Nếu dùng JDK 9+ và muốn chắc chắn mã chỉ gọi API của Java 8, có thể biên dịch bằng `javac --release 8 -encoding UTF-8 CollectorPartitionTest.java`. Tùy JDK mới, trình biên dịch có thể cảnh báo rằng source/target 8 đã cũ; đây là cảnh báo về chế độ biên dịch, không có nghĩa API trong bài đã bị loại bỏ.

**Stdout đã xác minh:**

```text
sample=count=7,sum=20,min=-2,max=9
splitTrees=55
large=count=10000,sum=49995000,min=0,max=9999
grouped={East=count=2,sum=7,min=2,max=5, West=count=2,sum=4,min=1,max=3}
PASS
```

Trong test này, lỗi điều kiện kiểm tra sẽ ném `AssertionError` làm chương trình dừng trước `PASS`. Bởi vậy chỉ nhìn một kết quả thu tuần tự là chưa đủ; `PASS` ở đây chỉ được in sau nhiều nhóm kiểm tra khác nhau.

## 5. Hiểu thật rõ phép thử 55 cách phân chia

Nếu một danh sách có `n` phần tử và ta cho phép ba đoạn liên tiếp có thể rỗng, chọn hai vị trí cắt `0 <= i <= j <= n`. Số bộ `(i, j)` là:

\[
\frac{(n+1)(n+2)}{2}
\]

Trong chương trình:

| Bộ dữ liệu | n | Số cách chia ba đoạn | Những tình huống được bao phủ |
| --- | ---: | ---: | --- |
| Danh sách rỗng | 0 | 1 | Ba bộ chứa rỗng; identity của gộp |
| Danh sách một phần tử | 1 | 3 | Phần tử ở đoạn đầu, giữa hoặc cuối |
| `[4, 4, -1, 0]` | 4 | 15 | Trùng lặp, số âm, zero, đoạn rỗng |
| `[4, -2, 7, 4, 0, 9, -2]` | 7 | 36 | Nhiều điểm cắt và hai cây gộp |
| **Tổng** | | **55** | Mỗi cách chia được kiểm bằng hai cây gộp |

Mỗi lần lặp:

1. `a = values.subList(0, i)`, `b = values.subList(i, j)`, `c = values.subList(j, n)`.
2. Tạo trạng thái riêng cho từng đoạn bằng `accumulate(...)`.
3. Tính lần lượt `(a+b)+c` và `a+(b+c)`.
4. Gọi `finish()` để so sánh **kiểu kết quả công khai** `Summary` với oracle.
5. Báo lỗi gồm `i`, `j` nếu một trong hai cây gộp không đúng.

Nhờ vậy, test chủ động gọi `combiner` ngay cả khi runtime quyết định **không gọi combiner** trong một phép `stream().collect(...)` tuần tự. Đây là trọng tâm kiểm thử collector tùy biến.

### Vì sao cần oracle độc lập?

Nếu dùng:

```java
// Phản ví dụ: không phải oracle độc lập.
Summary expected = data.stream().collect(collectorUnderTest);
Summary actual = data.parallelStream().collect(collectorUnderTest);
```

hai phép gọi có thể cùng sai theo một cách và vẫn bằng nhau. Vì thế bài kiểm thử dùng vòng `for` độc lập để tự tính count/sum/min/max, rồi thêm một **giá trị vàng** (golden result) viết tay cho dữ liệu mẫu. Chúng ta kiểm tra cả quy tắc tích lũy lẫn việc gộp.

### Có phải 55 cách là toàn bộ khả năng chia không?

Không. 55 là **tất cả cách chia thành ba đoạn liên tiếp** của bốn bộ test đang chọn. Với bốn đoạn, năm đoạn hoặc một cây gộp nhiều nhánh, không gian lớn hơn. Tuy nhiên, kiểm tra identity/associativity trên nhiều đoạn và hai cây gộp là một phép thử thực dụng, có tính tái lập cao. Bên cạnh đó, test chạy parallel trên dữ liệu lớn và trên dữ liệu đã xáo trộn để tăng khả năng phát hiện lỗi khác.

Đừng nhầm **“đã thử nhiều lịch thực thi”** với **“đã chứng minh mọi lịch thực thi”**. Nếu collector vi phạm luật về state chia sẻ hoặc đồng thời, cần thêm đánh giá thiết kế và kiểm thử concurrency phù hợp, không thể chỉ dựa vào số lần gọi `parallelStream()`.

## 6. Thí nghiệm phản chứng: combiner sai có thể qua test tuần tự

Một lỗi kinh điển là combiner chỉ trả vế trái, bỏ vế phải:

```java
(left, right) -> left  // SAI: mất toàn bộ phần tử right.
```

Vì pipeline tuần tự thường tích lũy vào một bộ chứa, chương trình có thể xuất đúng khi gọi `stream().collect(...)`, khiến lỗi bị bỏ sót. Ta có thể **buộc gọi combiner** với hai bộ chứa có dữ liệu để kiểm tra.

Tệp độc lập **`BrokenCombinerDemo.java`**:

```java
import java.util.*;
import java.util.stream.*;

public class BrokenCombinerDemo {
    public static void main(String[] args) {
        Collector<Integer, List<Integer>, List<Integer>> wrong =
            Collector.of(
                ArrayList::new,
                List::add,
                (left, right) -> left // LOSES right!
            );

        List<Integer> input = Arrays.asList(1, 2, 3, 4);
        List<Integer> sequential = input.stream().collect(wrong);

        List<Integer> left =
            new ArrayList<>(Arrays.asList(1, 2));
        List<Integer> right =
            new ArrayList<>(Arrays.asList(3, 4));

        List<Integer> manual =
            wrong.combiner().apply(left, right);

        System.out.println("sequential=" + sequential);
        System.out.println("manual=" + manual);
        System.out.println("brokenDetected=" + !manual.equals(input));
    }
}
```

```bash
javac -encoding UTF-8 BrokenCombinerDemo.java
java BrokenCombinerDemo
```

```text
sequential=[1, 2, 3, 4]
manual=[1, 2]
brokenDetected=true
```

Đây là một **ví dụ cố ý sai**, dùng để thấy phương pháp kiểm thử phát hiện lỗi. Kết quả `sequential` đúng không chứng minh `combiner` đúng. Lệnh gộp trực tiếp cho thấy vế phải `[3, 4]` biến mất.

Sửa bằng cách nối dữ liệu hai vế rồi trả trạng thái chứa kết quả:

```java
// Mã minh họa: dùng khi left và right là List<T> riêng biệt.
(left, right) -> {
    left.addAll(right);
    return left;
}
```

Với collector giữ thứ tự, ghép `left` trước `right` là điều quan trọng. Đảo thứ tự hai phần thường làm sai encounter order. Không phải cứ phép gộp có tính kết hợp là nó có tính giao hoán.

## 7. Thiết kế ma trận kiểm thử đủ bao phủ

Một collector mới nên có các nhóm test sau, điều chỉnh theo hợp đồng thực tế:

| Loại test | Đầu vào/phép kiểm | Rủi ro được phát hiện |
| --- | --- | --- |
| **Empty** | Không có phần tử | Sai supplier/finisher, min/max không có giá trị |
| **Singleton** | Một phần tử ở nhiều vị trí đoạn | Sai identity, lỗi khi một đoạn rỗng |
| **Repeated values** | Phần tử trùng, khóa trùng | Vô tình lọc trùng hoặc gộp đếm sai |
| **Negative/zero/boundary** | Giá trị âm, 0, cực trị phù hợp | Sai identity/sentinel, dấu và tổng |
| **Split all cuts** | Cắt ở mọi `i, j` trong giới hạn nhỏ | Bỏ phần hoặc thiếu dữ liệu ở các nhánh |
| **Merge tree** | `(a+b)+c` và `a+(b+c)` | Vi phạm kết hợp |
| **Empty merge both sides** | `combine(a, empty)` và `combine(empty, a)` | Vi phạm identity |
| **Fresh supplier** | Hai lần gọi `supplier.get()` | Dùng chung state mutable |
| **Golden + independent oracle** | Kết quả viết tay/vòng `for` | Test tự xác nhận một thuật toán sai |
| **Sequential vs parallel** | Cùng đầu vào, cùng kết quả mong đợi | Lỗi bị che khi không gọi combiner |
| **Repeated seeded random** | Shuffle có seed, dữ liệu có cấu trúc khác | Lỗi xuất hiện với dạng dữ liệu/partition khác |
| **Nested/grouping usage** | `groupingBy(..., mapping(..., custom))` | Sai kết quả khi collector dùng trong nhóm |
| **Order test** | Dữ liệu có thứ tự rõ và kết quả cần giữ thứ tự | Gộp đảo nhánh, đặc tính UNORDERED sai |
| **Concurrency contract** | Chỉ khi thực sự hỗ trợ `CONCURRENT` | Race khi nhiều luồng cập nhật cùng state |
| **Overflow/precision** | Tổng lớn, số thực, giá trị biên | Sai số hoặc tràn kiểu số |

Với input đến từ API, CSV hoặc cơ sở dữ liệu, thêm test cho null, bản ghi không hợp lệ, ký tự đặc biệt và nguồn có thể thay đổi. Xử lý lỗi đầu vào phải được quy định rõ trong contract của collector: **loại bỏ, báo lỗi hay bảo toàn thông tin lỗi**. Trong ví dụ số nguyên của bài, `null` bị từ chối chủ động bằng `Objects.requireNonNull`, không phải tự động biến thành 0.

## 8. Thứ tự là một phần của hợp đồng kiểm thử

Collector của ví dụ tính count/sum/min/max nên **không phụ thuộc encounter order**. Vì vậy ta có thể shuffle danh sách và vẫn đòi kết quả giống hệt.

Nhưng không được áp test “shuffle thì kết quả phải bằng” cho mọi collector. Ví dụ một collector nối chuỗi theo thứ tự gặp:

```text
Đầu vào:       [An, Binh, Chi]
Kết quả đúng:  An|Binh|Chi

Đầu vào mới:   [Chi, An, Binh]
Kết quả đúng:  Chi|An|Binh
```

Với kết quả có thứ tự, điều cần kiểm là:

```text
sequential(đầu vào X)
    ==
parallel(đầu vào X, nếu hợp đồng đòi giữ encounter order)
    ==
manualMerge(đoạn liên tiếp của X theo đúng thứ tự)
```

Không tự yêu cầu kết quả của **hai đầu vào đã hoán đổi thứ tự** phải bằng nhau. Với `Set` không thứ tự, dùng `Set.equals`; với `Map` thống kê, dùng `Map.equals`. Khi collector khai báo `UNORDERED` một cách hợp lệ, phép tương đương có thể không yêu cầu cùng thứ tự, nhưng vẫn phải giữ đủ nội dung nghiệp vụ.

Nếu viết collector để gom `List<T>` và giữ encounter order, một combiner kiểu `left.addAll(right); return left;` giữ thứ tự phần trước rồi phần sau khi framework đưa các phân đoạn theo đúng hợp đồng. Ngược lại, `right.addAll(left); return right;` có thể cho thứ tự ngược nếu chỉ kiểm tra song song một vài lần sẽ khó phát hiện.

## 9. Parallel Stream và ba đặc tính Collector

Các đặc tính thuộc `Collector.Characteristics` phải phù hợp với triển khai thật:

| Đặc tính | Khi nào hợp lệ? | Sai lầm dễ gặp |
| --- | --- | --- |
| `CONCURRENT` | Accumulator có thể được gọi đồng thời trên **cùng một trạng thái** mà vẫn đúng | Gắn vào `ArrayList`/`HashMap` mutable không đồng bộ |
| `UNORDERED` | Kết quả không có yêu cầu bảo toàn encounter order | Khai báo cho collector nối danh sách/chuỗi theo thứ tự |
| `IDENTITY_FINISH` | Finisher thật sự là identity, có thể bỏ qua; kiểu `A` phù hợp với `R` | Dùng khi finisher tạo object kết quả khác hoặc đóng băng dữ liệu |

Với `CollectorPartitionTest`, collector dùng trạng thái `Acc` mutable, finisher thành `Summary` immutable; không khai báo các đặc tính trên. Đây là cách thận trọng và đúng cho ví dụ học tập. `parallelStream()` vẫn có thể dùng collector không `CONCURRENT` bằng cách tích lũy các trạng thái riêng rồi gộp.

Theo hợp đồng Java Stream, **concurrent reduction** chỉ phù hợp khi luồng chạy song song, collector có `CONCURRENT`, và nguồn không yêu cầu thứ tự hoặc collector có `UNORDERED`. Chỉ thay thành `parallelStream()` không chứng tỏ accumulator nào cũng có thể chạy đồng thời trên một instance.

**Không lấy kết quả `parallelStream()` một lần làm oracle cho tính kết hợp.** Kế hoạch chia phần của runtime tùy nguồn dữ liệu, số luồng và implementation. Test ở mục 4 gọi trực tiếp combiner với các đoạn và cây gộp định trước, giúp tái lập chính xác trường hợp sai. Test song song bổ sung thêm kiểm tra tích hợp với Stream framework.

## 10. Tránh ba dạng test cho cảm giác an toàn giả

### 10.1. Chỉ test tuần tự

```java
// Chưa đủ để xác minh combiner.
Summary result = data.stream().collect(customCollector);
```

Nếu chỉ supplier và accumulator được sử dụng, combiner sai có thể không lộ. Bổ sung test trực tiếp trên hai hoặc ba accumulator đã có phần tử.

### 10.2. Chỉ so parallel với sequential của cùng collector

```java
// Hai đường xử lý cùng lỗi vẫn có thể cho kết quả giống nhau.
Summary x = data.stream().collect(customCollector);
Summary y = data.parallelStream().collect(customCollector);
```

Hãy thêm golden result cho dữ liệu nhỏ và oracle viết bằng cách độc lập như vòng `for` hoặc một phép tổng hợp chuẩn khác có hợp đồng đã biết.

### 10.3. Dùng cùng accumulator mutable cho hai cây gộp

```java
// Mã sai về thiết kế test: a, b có thể đã bị mutate.
Acc first = a.combine(b);
Acc second = a.combine(b); // Không còn kiểm tra trên trạng thái gốc!
```

Cách đúng: tạo lại tất cả bộ chứa bằng supplier/accumulate cho mỗi nhánh test. Nếu cần so sánh trạng thái nội bộ, hãy tạo snapshot độc lập; không sửa dữ liệu test giữa các lần đo.

Một lỗi tương tự xảy ra khi các test chạy song song cùng chia sẻ một `Random`, một `Map` hoặc một bộ chứa mutable mà không quản lý vòng đời. Với test deterministic, tạo seed cố định và dùng bản sao đầu vào riêng; khi cần test concurrency, đưa việc chia sẻ trạng thái thành một kịch bản được thiết kế cụ thể.

## 11. Test số học: tính kết hợp thực tế và giới hạn kiểu số

Bộ ví dụ dùng `long` cho `count` và `sum`, `int` cho min/max. Với bộ dữ liệu được kiểm thử, giá trị nằm trong miền an toàn. Điều này **không tự bảo đảm không tràn** với mọi ứng dụng:

- `long` cũng có giới hạn; tổng rất lớn vẫn có thể tràn. Nếu phải phát hiện tràn, cân nhắc `Math.addExact` và định nghĩa cách hệ thống báo lỗi. Nếu cần miền số lớn không giới hạn bởi long, cân nhắc `BigInteger`.
- Với tiền tệ, tính chính xác theo quy tắc nghiệp vụ thường cần `BigDecimal` hoặc lưu đơn vị nhỏ nhất bằng số nguyên có kiểm tra tràn.
- Với `double`/`float`, do làm tròn, phép cộng có thể tạo kết quả khác nhau tùy thứ tự gộp. Không ép equality bitwise cho mọi phép cộng số thực rồi kết luận combiner sai: hãy xác định tolerance, phương pháp tổng và yêu cầu tái lập kết quả trước.
- `min`/`max` có thể dùng giá trị sentinel trong **trạng thái nội bộ** miễn có cờ/count phân biệt trạng thái rỗng. Trong bài, `count==0` khiến `Summary.min/max` thành null; do đó input thực sự bằng `Integer.MIN_VALUE` hay `Integer.MAX_VALUE` vẫn xử lý đúng.
- Nếu kết quả thống kê còn đi vào `groupingBy`, hãy test riêng từng khóa, không chỉ tổng chung: có thể một nhóm bị gộp nhầm sang nhóm khác trong khi tổng toàn bộ vẫn đúng.

Một số test dùng dữ liệu nhỏ có giá trị kỳ vọng bằng tay (golden), cùng vài test nguồn lớn có giá trị toán học đã biết, mang lại bằng chứng mạnh hơn so với chỉ thử dữ liệu ngẫu nhiên không có oracle.

## 12. Nên kiểm thử Collector tùy biến trong groupingBy như thế nào?

Collector trong ví dụ có thể được dùng làm **downstream** của `groupingBy`:

```java
// Trích từ chương trình mục 4, cần lớp Row và collector().
Map<String, Summary> summaries = rows.stream().collect(
    Collectors.groupingBy(
        r -> r.category,
        TreeMap::new,
        Collectors.mapping(r -> r.points, collector())));
```

Ở đây:

1. `groupingBy` xác định nhóm từ `category`.
2. `mapping` lấy `points` làm dữ liệu đầu vào của collector tùy biến.
3. Với mỗi nhóm, collector tạo và gộp `Acc` riêng.
4. `TreeMap::new` chỉ định thứ tự khóa trong kết quả; các giá trị trong map là `Summary`.

Chương trình đã đối chiếu cả sequential và parallel với hai nhóm cụ thể:

```text
East: [2, 5]  → count=2, sum=7, min=2, max=5
West: [1, 3]  → count=2, sum=4, min=1, max=3
```

Khi ứng dụng có khóa trùng hoặc tập nhóm rỗng, test thêm trường hợp chỉ có một nhóm, nhiều nhóm đan xen, các giá trị bằng nhau ở nhiều nhóm, nhóm có số âm và nguồn rỗng. Không mặc định `groupingBy` tự sinh nhóm có khóa không tồn tại trong nguồn. Cần làm sạch khóa `null` trước khi nhóm theo chính sách nghiệp vụ, vì `groupingBy` có thể ném `NullPointerException` nếu classifier tạo null.

## 13. Mở rộng kiểm thử theo hướng có hệ thống

Với collector phức tạp hơn một bộ thống kê nhỏ, có thể áp dụng:

**A. Bài thử property với dữ liệu ngẫu nhiên có seed.** Tạo danh sách số hợp lệ bằng `Random(2026L)`, luôn lưu seed và input gây lỗi. Đối chiếu kết quả với oracle độc lập. Test ở mục 4 xáo trộn danh sách đã biết; có thể bổ sung độ dài khác nhau và giá trị biên để tăng độ phủ.

**B. Nhiều cây gộp hơn.** Với bốn đoạn A, B, C, D, kiểm:

```text
(((A+B)+C)+D)
((A+B)+(C+D))
(A+(B+(C+D)))
((A+(B+C))+D)
(A+((B+C)+D))
```

Đây là năm cách đặt ngoặc có bảo toàn thứ tự của bốn đoạn. Nếu collector yêu cầu encounter order, luôn giữ A trước B trước C trước D. Với kết quả không phụ thuộc thứ tự như thống kê count/sum/min/max, có thể bổ sung hoán vị các đoạn để thử tính độc lập với thứ tự **nếu** đó thật sự là hợp đồng.

**C. Test cố ý làm sai một thành phần.** Thay combiner bằng phiên bản bỏ vế phải như mục 6 và xác minh bộ test thực sự thất bại. Đây là cách kiểm chứng rằng test không chỉ so sánh hai kết quả cùng được tính từ một implementation sai.

**D. Kiểm thử khả năng tái sử dụng collector.** Có thể dùng cùng một đối tượng `Collector` để thu nhiều Stream khác nhau **nếu supplier cấp trạng thái mới và các hàm không giữ state ngoài**. Tạo nhiều lần `data.stream().collect(collector)`, không tái sử dụng chính đối tượng Stream đã kết thúc.

**E. Test tài nguyên và hiệu năng riêng.** Sau khi đúng về chức năng, đo thời gian/memory ở dữ liệu đại diện, so với collector chuẩn khi phù hợp. Đừng diễn giải số lần gọi combiner của một máy thành cam kết của JDK. Benchmark cần khởi động JVM, dữ liệu đủ lớn và phương pháp đo thích hợp; test đơn vị chỉ nên khẳng định tính đúng.

## 14. Checklist khi collector sai sau khi chia/gộp

| Triệu chứng | Nghi vấn đầu tiên | Cách xác nhận |
| --- | --- | --- |
| Tuần tự đúng, parallel thiếu phần tử | Combiner làm mất phần | Buộc gọi combiner trên hai phần không rỗng |
| Kết quả lớn hơn kỳ vọng | Count/sum bị cộng trùng | Test hai đoạn nhỏ, golden result |
| Kết quả chỉ sai khi có đoạn rỗng | Identity của trạng thái rỗng sai | Test `(empty,a)`, `(a,empty)` và empty toàn bộ |
| Kết quả phụ thuộc cây gộp | Combiner không associative | So `(a+b)+c` với `a+(b+c)` trên state mới |
| Danh sách đảo thứ tự | Combiner ghép phải trước trái | Test nguồn có encounter order và so List |
| Hai lần collect ảnh hưởng nhau | Supplier trả cùng mutable instance | Kiểm tra hai lần `supplier.get()` là các object độc lập |
| Test đôi lúc sai khi parallel | State dùng chung, race hoặc contract sai | Rà soát state ngoài, đặc tính `CONCURRENT`, tạo case tái lập |
| Chỉ một nhóm bị sai trong groupingBy | Nhóm nhầm khóa/gộp kết quả sai | Oracle theo từng khóa và test khóa đan xen |
| Min/max sai ở đầu vào rỗng | Sentinel bị xuất thành dữ liệu thật | Test `Collections.emptyList()` và giá trị cực trị |
| Sai vài chữ số thập phân | Floating point không kết hợp chính xác | Xác định độ chính xác mong muốn, dùng tolerance/kiểu số đúng |

Những phép thử này nhắm đến **luật của Collector**, không phụ thuộc vào cách JVM cụ thể chia workload. Khi gặp lỗi, giảm input xuống tập nhỏ nhất còn tái hiện được, ghi rõ seed, các điểm cắt và dạng cây gộp để sửa trực tiếp điều kiện bị vi phạm.

## 15. Câu hỏi tự kiểm tra

**1. Vì sao chạy `parallelStream().collect(...)` 100 lần vẫn không đủ để chứng minh combiner đúng?**  
Vì runtime không có nghĩa vụ thử mọi cách chia hoặc mọi cây gộp. Cần kiểm thử trực tiếp các trường hợp chia và gộp có kiểm soát, cộng thêm oracle độc lập.

**2. Combiner `(left,right)->left` có thể khiến test tuần tự pass không?**  
Có. Tích lũy tuần tự có thể không phải gọi combiner; ví dụ `BrokenCombinerDemo` chứng minh việc gộp thủ công sẽ làm mất vế phải.

**3. Vì sao mỗi phép thử cây gộp cần accumulator mới?**  
Vì combiner có thể thay đổi bộ chứa mutable. Tái sử dụng state khiến test thứ hai nhận dữ liệu đã bị thay đổi bởi test thứ nhất.

**4. `combine(a, empty)` cần thỏa yêu cầu gì?**  
Kết quả phải tương đương với `a` sau finisher. Đây là điều kiện identity theo hợp đồng Collector.

**5. Có nên yêu cầu `combine(a,b) == combine(b,a)` với collector xây danh sách có thứ tự?**  
Không. Ghép danh sách thường không giao hoán; yêu cầu cần kiểm là kết quả tương đương khi chia/gộp hợp lệ có giữ encounter order.

**6. Khi nào có thể khai báo `CONCURRENT`?**  
Chỉ khi accumulator hoạt động đúng khi nhiều luồng gọi đồng thời trên cùng một bộ chứa, và các điều kiện semantic tương ứng được bảo đảm. Dùng `parallelStream()` không tự biến một accumulator không đồng bộ thành concurrent.

**7. Trong bộ test, 55 biểu thị điều gì?**  
Tổng số cách cắt thành ba đoạn liên tiếp của bốn bộ dữ liệu có độ dài 0, 1, 4 và 7. Mỗi cách được kiểm với cả hai dạng cây gộp.

**8. Vì sao nên giữ golden result ngoài oracle?**  
Vì oracle cũng là code có thể sai. Một ví dụ nhỏ có kết quả xác định bằng tay giúp kiểm tra tính độc lập và đúng đắn của oracle.

## Tài liệu tham khảo chính thức

- [Java SE 8 — Collector](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Collector.html): supplier, accumulator, combiner, finisher, **identity/associativity constraints** và characteristics.
- [Java SE 8 — Stream](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Stream.html): `collect(Collector)`, `collect(supplier,accumulator,combiner)` và parallel Stream.
- [Java SE 8 — Stream package](https://docs.oracle.com/javase/8/docs/api/java/util/stream/package-summary.html): mutable reduction, parallel reduction, side effects và vấn đề associative.
- [Java SE 8 — Collectors](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Collectors.html): `groupingBy`, `mapping` và những collector chuẩn để đối chiếu.

**Điểm cần nhớ:** một collector tùy biến chỉ đáng tin khi đúng ở cả **tích lũy tuần tự**, **gộp các phần độc lập**, **thay đổi cây gộp**, **trường hợp rỗng**, và **tích hợp với parallel Stream**. Hãy viết oracle độc lập, sinh nhiều vị trí cắt, tạo state mới cho mỗi thử nghiệm và so sánh kết quả theo đúng hợp đồng về kiểu, thứ tự và độ chính xác.