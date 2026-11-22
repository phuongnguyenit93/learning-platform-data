# Thay đổi biến bên ngoài làm kết quả phụ thuộc thứ tự trong Java Stream

## 1. Vấn đề: pipeline nhìn như hàm nhưng lại phụ thuộc trạng thái bên ngoài

Java Stream khuyến khích viết các bước xử lý dữ liệu bằng những hàm nhỏ, rõ mục đích:

```java
List<String> result = words.stream()
        .filter(word -> !word.isBlank())
        .map(String::strip)
        .toList();
```

Nếu `words` là danh sách `String` không chứa `null`, kết quả của mỗi phép biến đổi chỉ phụ thuộc vào giá trị phần tử được truyền vào. Đây là phong cách **stateless** (*không lưu trạng thái giữa các phần tử*) và **non-interfering** (*không can thiệp vào nguồn dữ liệu đang được duyệt*).

Tuy nhiên, một lỗi thường gặp là dùng biến **nằm ngoài lambda** để đếm, đánh số, ghi kết quả trung gian hoặc ra quyết định:

```java
AtomicInteger number = new AtomicInteger();

List<String> numbered = words.stream()
        .map(word -> number.incrementAndGet() + ":" + word)
        .toList();
```

Đoạn này có thể in ra thứ tự mong muốn trong một thử nghiệm tuần tự. Nhưng kết quả của từng phần tử không còn là hàm thuần `word -> result`: nó phụ thuộc **phần tử nào gọi `incrementAndGet()` trước**. Chuyển vị trí `sorted`, bật `parallel`, thay terminal operation hoặc cấu trúc nguồn có thể làm những giá trị gắn với từng phần tử khác đi.

`AtomicInteger` giúp các thao tác tăng biến đếm **atomic**, chứ không biến thứ tự thực thi của các phần tử thành một hợp đồng ổn định. Việc “không mất số đếm” hoàn toàn khác với việc “phần tử nào nhận số thứ tự nào”.

Bài này giúp bạn:

1. Nhận diện lambda có trạng thái ngoài (*stateful lambda*) và tác dụng phụ (*side effect*).
2. Phân biệt **encounter order**, **execution order** và **result order** trong Stream.
3. Hiểu vì sao `sorted`, `filter`, `limit`, `count`, `parallelStream`, `forEach` có thể làm lộ lỗi thiết kế.
4. Không nhầm “biến phải effectively final” với “trạng thái được tham chiếu là bất biến”.
5. Sửa theo hướng phép biến đổi thuần, đánh số bằng chỉ số ổn định, dùng `map`/`reduce`/`collect` hoặc vòng lặp có chủ đích.
6. Kiểm thử hành vi và giới hạn của những giả định về thứ tự.

## 2. Hai điều kiện quan trọng: stateless và non-interfering

Theo hợp đồng Stream, hầu hết hàm hành vi truyền vào pipeline (`Predicate`, `Function`, `Consumer`, `Comparator`, v.v.) nên **không can thiệp vào nguồn** và **không phụ thuộc trạng thái thay đổi trong quá trình xử lý**.

### Stateless: kết quả không phụ thuộc lịch sử xử lý

Một lambda stateless:

```java
n -> n * n
```

Cho cùng một giá trị `n`, phép biến đổi cho cùng một kết quả, không cần biết phần tử nào đã chạy trước đó.

Một lambda stateful:

```java
n -> n + counter.incrementAndGet()
```

Kết quả phụ thuộc `counter` đã tăng bao nhiêu lần, tức phụ thuộc các lần gọi trước và thứ tự tác vụ.

### Non-interfering: không chỉnh sửa nguồn khi pipeline đang duyệt

Ví dụ sai:

```java
// Không nên: sửa chính danh sách đang được Stream duyệt.
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3));
numbers.stream().forEach(n -> numbers.add(n * 10));
```

Đây là đoạn minh họa lỗi thiết kế. Với nguồn không hỗ trợ sửa đồng thời như `ArrayList`, sửa nguồn khi pipeline còn chạy có thể dẫn đến `ConcurrentModificationException`, kết quả không đoán được hoặc các hậu quả khác. Không thể coi việc chạy không ném lỗi trong một thử nghiệm là bảo đảm an toàn.

**Khác biệt:** lambda có trạng thái ngoài không nhất thiết sửa nguồn; nó vẫn có thể vi phạm yêu cầu stateless dù chỉ chỉnh một bộ đếm ngoài. Việc sửa một collection kết quả chia sẻ từ `parallelStream` lại thêm nguy cơ race condition. Cần phân tích riêng cả trạng thái, thứ tự và thread safety.

## 3. Vì sao Java cho phép lambda thay đổi object ngoài nhưng không cho tăng biến local?

Trong Java, một biến local được lambda *capture* phải là `final` hoặc **effectively final**: biến đó không được gán lại sau khi khởi tạo.

Ví dụ không biên dịch:

```java
int counter = 0;

// Sai: local variable counter không effectively final.
// words.forEach(word -> counter++);
```

Nhưng mã sau có thể biên dịch:

```java
int[] counter = {0};
words.forEach(word -> counter[0]++);
```

hoặc:

```java
AtomicInteger counter = new AtomicInteger();
words.forEach(word -> counter.incrementAndGet());
```

Lý do: tham chiếu `counter` không bị gán lại, nên đáp ứng yêu cầu capture. Tuy nhiên, **nội dung mảng** hoặc **trạng thái của `AtomicInteger`** vẫn có thể thay đổi. Compiler chỉ kiểm soát việc capture biến local, không tự chứng minh lambda là stateless hay an toàn khi chạy song song.

Không dùng mảng một phần tử hoặc `AtomicInteger` chỉ để “lách” effectively final nếu mục tiêu thật sự là tích lũy dữ liệu trong Stream. Hãy hỏi: có thể dùng `count`, `sum`, `reduce`, `collect` hoặc một vòng lặp rõ ràng thay thế không?

## 4. Ba loại thứ tự không giống nhau

Cần phân biệt:

| Khái niệm | Ý nghĩa | Điều thường dễ nhầm |
| --- | --- | --- |
| **Encounter order** | Thứ tự các phần tử theo nguồn và các thao tác giữ thứ tự | Không phải mọi nguồn đều có: `HashSet` không bảo đảm thứ tự |
| **Execution order** | Thứ tự và thread mà callback `map`/`filter`/`forEach` thực sự được gọi | Không đồng nghĩa encounter order, nhất là khi `parallel()` |
| **Result order** | Thứ tự phần tử thu được trong kết quả, nếu có | `toList()` có thể giữ encounter order dù callback chạy đồng thời |

Với `List.of("pear", "apple", "plum")`, nguồn có encounter order `pear`, `apple`, `plum`.

Một pipeline thuần:

```java
List<String> sorted = words.parallelStream()
        .map(String::toUpperCase)
        .sorted()
        .toList();
```

tạo danh sách theo thứ tự đã sắp xếp. Chạy song song có thể chia việc tính toán, nhưng `toList()` giữ encounter order của pipeline có thứ tự. Người viết code **không cần dựa** vào lambda của phần tử nào chạy trước.

Ngược lại:

```java
AtomicInteger next = new AtomicInteger();
List<String> tagged = words.parallelStream()
        .map(word -> next.incrementAndGet() + ":" + word)
        .toList();
```

mỗi phần tử được gắn một số theo thứ tự **thực thi** của `incrementAndGet`, không phải chắc chắn theo encounter order. Mảng kết quả vẫn có thể được thu thập theo thứ tự nguồn, nhưng số được gắn vào mỗi `word` có thể khác giữa các lần chạy. Đừng đưa một mẫu output cụ thể của ví dụ song song này vào hợp đồng.

**Điểm cần nhớ:** giữ thứ tự của danh sách kết quả không chứng minh phép gán số theo thứ tự. Bạn có thể nhận `[2:pear, 1:apple, 3:plum]` trong một cách phân lịch, dù ba phần tử trong danh sách vẫn nằm ở vị trí `pear`, `apple`, `plum`.

## 5. `sorted` cho thấy thứ tự của tác dụng phụ quan trọng thế nào

Xét hai phương án đánh số trong pipeline **tuần tự**.

### Đánh số trước, rồi sắp xếp theo từ

```java
AtomicInteger next = new AtomicInteger();

List<String> result = Stream.of("pear", "apple", "plum")
        .map(word -> new Tagged(next.incrementAndGet(), word))
        .sorted(Comparator.comparing(Tagged::word))
        .map(tag -> tag.sequence() + ":" + tag.word())
        .toList();

// [2:apple, 1:pear, 3:plum]
```

Ở đây `Tagged` là record `record Tagged(int sequence, String word) {}` được khai báo trong chương trình đầy đủ ở phần 8. `map` đánh số theo thứ tự đầu vào `pear`, `apple`, `plum`; `sorted` sau đó chuyển vị trí của các `Tagged` mà **không thay lại số đã gán**.

### Sắp xếp trước, rồi đánh số

```java
AtomicInteger next = new AtomicInteger();

List<String> result = Stream.of("pear", "apple", "plum")
        .sorted()
        .map(word -> next.incrementAndGet() + ":" + word)
        .toList();

// [1:apple, 2:pear, 3:plum]
```

Hai pipeline có cùng ba từ và cùng thao tác `sorted`, `map`, `toList`, nhưng **thứ tự giữa `sorted` và `map` khác**. Khi `map` tạo số từ một counter ngoài, số này gắn với vị trí tác vụ chạy, không phải thuộc tính độc lập của từ.

Vấn đề không phải `sorted` “làm mất dữ liệu”; vấn đề là trạng thái ngoài đã đưa một phụ thuộc vào thứ tự thực thi vào phép biến đổi. Nếu yêu cầu nghiệp vụ là số thứ tự sau khi sắp xếp, có thể tách rõ: tạo **danh sách đã sắp xếp**, rồi đánh số qua chỉ số. Nếu yêu cầu là số dòng đầu vào, đừng dùng counter trong `map`: hãy gắn chỉ số gốc từ nguồn có khả năng truy cập theo chỉ số.

## 6. `filter`, `limit`, `findFirst` và `count` làm lộ giả định sai

Một lambda có tác dụng phụ đôi khi được viết vì người lập trình nghĩ nó sẽ chạy **đúng một lần trên mọi phần tử**. Hợp đồng Stream không cho phép dùng điều đó làm cơ sở cho logic nghiệp vụ trong tất cả các pipeline.

### Lọc trước và sau đánh số khác nhau

```java
// Minh họa khi words là List<String> có thứ tự, không chứa null.
AtomicInteger counter = new AtomicInteger();

List<String> labels = words.stream()
        .filter(s -> s.length() >= 5)
        .map(s -> counter.incrementAndGet() + ":" + s)
        .toList();
```

Chỉ các phần tử qua `filter` mới nhận số. Nếu đặt `map` trước `filter`, việc đếm có thể xảy ra cả với các phần tử sau đó bị loại. Đổi thứ tự các thao tác để “tối ưu” có thể làm hỏng nhãn được đánh số.

### Dừng sớm

`limit`, `findFirst`, `anyMatch` và các terminal operation có khả năng dừng sớm có thể khiến **không phải mọi phần tử** được xét. Đừng kỳ vọng một side effect trong lambda luôn chạy đủ số lần bằng kích thước nguồn. Ví dụ `Stream.iterate(...)` có thể là dãy vô hạn nhưng dùng `limit` chỉ lấy một phần.

### `count()` có thể bỏ qua callback không cần thiết

Một trường hợp đặc biệt quan trọng:

```java
List<String> source = List.of("a", "b", "c");
AtomicInteger calls = new AtomicInteger();

long count = source.stream()
        .map(s -> {
            calls.incrementAndGet();
            return s.toUpperCase();
        })
        .count();
```

Với nguồn đã biết kích thước như `List` và pipeline không đổi số phần tử, JDK có thể tính `count()` **mà không duyệt qua từng `map`**. Không được viết test hay nghiệp vụ yêu cầu `calls == 3`. Giá trị `count` là 3; side effect của `map` **không được bảo đảm** được thực thi.

Điều này cho thấy một lambda biến đổi không nên vừa làm việc chính vừa bắt buộc ghi log, gọi API ngoài hoặc cập nhật biến trạng thái để dữ liệu được coi là hợp lệ. Khi mục đích thực sự là tác dụng phụ, cần thiết kế bước tiêu thụ riêng và hiểu rõ giới hạn thứ tự; khi mục đích là tổng hợp, nên dùng terminal operation tương ứng.

## 7. `forEach`, `forEachOrdered` và `AtomicInteger` không giải quyết mọi vấn đề

### `forEach` không cam kết thứ tự khi chạy song song

```java
List<String> words = List.of("pear", "apple", "plum");
words.parallelStream().forEach(System.out::println);
```

Các từ có thể được in theo những thứ tự khác nhau; `forEach` không bảo đảm giữ encounter order đối với parallel Stream.

### `forEachOrdered` giữ encounter order cho hành động terminal

```java
words.parallelStream().forEachOrdered(System.out::println);
```

Với nguồn có thứ tự như `List`, hành động terminal được thực thi theo encounter order. Tuy nhiên:

- Điều này **không bảo đảm** các lambda `map` hoặc `filter` trước đó chạy theo thứ tự tương ứng.
- Nếu trong `map` đã gắn số bằng `AtomicInteger`, `forEachOrdered` không thể sửa số gán sai trước khi in.
- Việc buộc giữ thứ tự có thể giảm cơ hội song song hóa có lợi; dùng nó khi thứ tự thực sự là yêu cầu.

### Atomicity khác determinism

`AtomicInteger.incrementAndGet()` đảm bảo mỗi thao tác tăng là atomic và các lời gọi có thứ tự tuyến tính hóa cho biến đó. Nhưng **phần tử nào đến lượt gọi trước** vẫn tùy cách lên lịch. Nếu cần chỉ số gắn với đúng vị trí dữ liệu, hãy lấy từ nguồn, không suy ra từ thứ tự các thread gọi biến đếm.

Sử dụng `Collections.synchronizedList`, `CopyOnWriteArrayList` hoặc `ConcurrentLinkedQueue` làm nơi thêm phần tử có thể giải quyết một phần **an toàn bộ nhớ/cập nhật**, nhưng không đồng nghĩa phần tử xuất hiện trong thứ tự mong muốn. Ngoài ra, một phần pipeline có thể không duyệt hết hoặc được tối ưu. Khi chỉ cần thu thập, dùng `toList`, `toSet`, `collect` với collector phù hợp là rõ ràng hơn.

## 8. Ví dụ Java 17 hoàn chỉnh: đối chiếu cách phụ thuộc thứ tự và cách sửa

Tạo file **`ExternalStateStreamDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class ExternalStateStreamDemo {
    record Tagged(int sequence, String word) {}

    static void check(Object expected, Object actual, String label) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    label + ": expected=" + expected
                            + ", actual=" + actual);
        }
    }

    static List<Integer> runningTotals(List<Integer> values) {
        // Bài toán phụ thuộc phần tử trước: vòng lặp là lựa chọn rõ ràng.
        List<Integer> output = new ArrayList<>();
        int running = 0;
        for (int value : values) {
            running += value;
            output.add(running);
        }
        return List.copyOf(output);
    }

    public static void main(String[] args) {
        List<String> words = List.of("pear", "apple", "plum");

        // Cách phụ thuộc thứ tự: chỉ minh họa pipeline tuần tự.
        AtomicInteger sequentialCounter = new AtomicInteger();
        List<String> sequential = words.stream()
                .map(w -> sequentialCounter.incrementAndGet() + ":" + w)
                .toList();

        // Đánh số trước sorted: số gắn với thứ tự đầu vào.
        AtomicInteger beforeSortCounter = new AtomicInteger();
        List<String> numberedBeforeSort = words.stream()
                .map(w -> new Tagged(
                        beforeSortCounter.incrementAndGet(), w))
                .sorted(Comparator.comparing(Tagged::word))
                .map(t -> t.sequence() + ":" + t.word())
                .toList();

        // Sorted trước đánh số: số gắn với thứ tự đã sắp xếp.
        AtomicInteger afterSortCounter = new AtomicInteger();
        List<String> sortedBeforeNumber = words.stream()
                .sorted()
                .map(w -> afterSortCounter.incrementAndGet() + ":" + w)
                .toList();

        // Cách đúng khi cần số thứ tự cố định của dữ liệu đầu vào.
        List<String> indexed = IntStream.range(0, words.size())
                .mapToObj(i -> (i + 1) + ":" + words.get(i))
                .toList();

        // Từng index tự mang định danh, nên parallel không đổi gắn nhãn.
        List<String> parallelIndexed = IntStream.range(0, words.size())
                .parallel()
                .mapToObj(i -> (i + 1) + ":" + words.get(i))
                .toList();

        // Phép biến đổi thuần, không có trạng thái ngoài.
        List<String> pure = words.stream()
                .map(s -> s.toUpperCase(Locale.ROOT))
                .sorted()
                .toList();

        // Khi thực sự cần tổng cộng: dùng terminal reduction.
        List<Integer> amounts = List.of(2, 3, 5);
        int sum = amounts.stream().mapToInt(Integer::intValue).sum();

        // Khi thực sự cần tổng lũy kế theo vị trí: vòng lặp có chủ đích.
        List<Integer> prefix = runningTotals(amounts);

        check(List.of("1:pear", "2:apple", "3:plum"),
                sequential, "sequential stateful example");
        check(List.of("2:apple", "1:pear", "3:plum"),
                numberedBeforeSort, "number before sorted");
        check(List.of("1:apple", "2:pear", "3:plum"),
                sortedBeforeNumber, "sort before numbering");
        check(List.of("1:pear", "2:apple", "3:plum"),
                indexed, "source index");
        check(indexed, parallelIndexed, "parallel stable index");
        check(List.of("APPLE", "PEAR", "PLUM"),
                pure, "pure mapping");
        check(10, sum, "sum");
        check(List.of(2, 5, 10), prefix, "running totals");
        check(List.of("pear", "apple", "plum"),
                words, "source unchanged");

        System.out.println("sequential=" + sequential);
        System.out.println("beforeSort=" + numberedBeforeSort);
        System.out.println("afterSort=" + sortedBeforeNumber);
        System.out.println("indexed=" + indexed);
        System.out.println("parallelIndexed=" + parallelIndexed);
        System.out.println("pure=" + pure);
        System.out.println("runningTotals=" + prefix);
        System.out.println("sum=" + sum);
        System.out.println("tests=PASS");
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac ExternalStateStreamDemo.java
java ExternalStateStreamDemo
```

Stdout dự kiến:

```text
sequential=[1:pear, 2:apple, 3:plum]
beforeSort=[2:apple, 1:pear, 3:plum]
afterSort=[1:apple, 2:pear, 3:plum]
indexed=[1:pear, 2:apple, 3:plum]
parallelIndexed=[1:pear, 2:apple, 3:plum]
pure=[APPLE, PEAR, PLUM]
runningTotals=[2, 5, 10]
sum=10
tests=PASS
```

Chương trình cố ý **không** đưa ví dụ `parallelStream().map(w -> counter.incrementAndGet() + ":" + w)` vào stdout bắt buộc, vì ánh xạ số–từ của nó không ổn định. Thay vào đó, `parallelIndexed` minh họa phương án thiết kế đúng: `IntStream.range` sinh chỉ số theo vị trí nguồn, `mapToObj` xây nhãn chỉ từ chỉ số và giá trị ở vị trí đó, không cần bộ đếm ngoài.

### Phân tích các dòng quan trọng

1. `sequential` cho kết quả theo thứ tự List trong ví dụ tuần tự, nhưng đây là **hành vi của pipeline cụ thể**, không phải giấy phép đưa stateful lambda vào mọi pipeline.
2. `beforeSort` cho `2:apple` vì `apple` là phần tử thứ hai được gắn nhãn trước khi `sorted` sắp xếp.
3. `afterSort` cho `1:apple` vì phần tử được sắp xếp **trước** khi gọi counter.
4. `indexed` lấy chỉ số từ nguồn, nên `pear` luôn gắn `1`, `apple` luôn gắn `2`, `plum` luôn gắn `3`.
5. `parallelIndexed` bằng `indexed` vì kết quả từng chỉ số là một phép tính độc lập. `toList` giữ thứ tự của IntStream có encounter order ngay cả khi đánh giá song song.
6. `pure` là pipeline không trạng thái ngoài, dễ bảo trì và an toàn khi đổi cách thực thi trong điều kiện nguồn không bị sửa.
7. `sum` biểu diễn **một giá trị tổng**, còn `runningTotals` biểu diễn **dãy các tổng tiền tố**. Đó là hai yêu cầu khác nhau: tổng tiền tố phụ thuộc thứ tự và trạng thái, nên vòng lặp tuần tự là lựa chọn đơn giản, chính xác.
8. `check` ném `AssertionError` nếu kết quả khác dự kiến, nên không cần bật `java -ea`.

## 9. Những cách thiết kế thay thế tốt hơn

### 9.1. Nếu cần biến đổi từng phần tử: dùng hàm thuần

Thay vì:

```java
AtomicInteger counter = new AtomicInteger();
List<String> labels = words.stream()
        .map(w -> counter.incrementAndGet() + ":" + w)
        .toList();
```

hãy xác định **nhãn có thật sự cần index không**. Nếu không, dùng:

```java
List<String> labels = words.stream()
        .map(String::strip)
        .map(s -> s.toUpperCase(Locale.ROOT))
        .toList();
```

Kết quả của từng phần tử chỉ phụ thuộc dữ liệu phần tử, không phụ thuộc một biến bị thao tác trước đó. Đoạn này giả sử `words` gồm chuỗi không null và đã import `List`, `Locale`.

### 9.2. Nếu cần số thứ tự của List: dùng index từ nguồn

```java
List<String> labels = IntStream.range(0, words.size())
        .mapToObj(i -> (i + 1) + ":" + words.get(i))
        .toList();
```

Điều này phù hợp khi `words` là List có khả năng truy cập theo chỉ số hiệu quả (như `ArrayList` hoặc `List.of`), được giữ ổn định trong quá trình duyệt. Với `LinkedList`, `get(i)` có thể tốn O(n), khiến toàn bộ thuật toán O(n²). Khi đó, một vòng lặp dùng iterator hoặc `ListIterator` cùng bộ đếm cục bộ rõ ràng thường phù hợp hơn.

Nếu cần đánh số **sau khi sắp xếp**, tạo List đã sắp xếp trước:

```java
List<String> sorted = words.stream().sorted().toList();

List<String> numbered = IntStream.range(0, sorted.size())
        .mapToObj(i -> (i + 1) + ":" + sorted.get(i))
        .toList();
```

Ở đây trình tự “sắp xếp rồi đánh số” là yêu cầu được thể hiện rõ, không phải kết quả tình cờ của thứ tự gọi lambda.

### 9.3. Nếu cần tổng hợp: dùng reduction/collector

Sai hoặc khó bảo trì:

```java
int[] total = {0};
numbers.stream().forEach(n -> total[0] += n);
```

Đúng với yêu cầu tổng số:

```java
int sum = numbers.stream()
        .mapToInt(Integer::intValue)
        .sum();
```

Để đếm số phần tử:

```java
long count = numbers.stream().count();
```

Để nhóm và đếm theo khóa:

```java
Map<String, Long> counts = words.stream()
        .collect(Collectors.groupingBy(
                s -> s.substring(0, 1),
                Collectors.counting()));
```

Đoạn cuối giả định các chuỗi không rỗng, `words` không chứa null và đã import `Map`, `Collectors`. Nếu có giá trị rỗng, phải định nghĩa cách xử lý trước `substring`. `Collectors.groupingBy` từ chối classifier trả null. Với tổng, `reduce` hoặc `collect` đã xác định cách framework chia/gộp trạng thái; không cần biến global được cập nhật ngoài phạm vi collector.

### 9.4. Nếu cần trạng thái tuần tự thật: dùng vòng lặp

Một số phép tính **vốn phụ thuộc thứ tự** như tổng tiền tố, bộ phân tích trạng thái, nhận biết chuyển trạng thái giữa các phần tử liền nhau, quy tắc dừng sớm nhiều nhánh. Không cần cưỡng ép chúng vào Stream bằng `AtomicInteger` hoặc mảng một phần tử.

```java
List<Integer> totals = new ArrayList<>();
int running = 0;

for (int amount : amounts) {
    running += amount;
    totals.add(running);
}
```

Đoạn trên là minh họa với `amounts` đã tồn tại. Nó thể hiện tuần tự rõ ràng: `running` là trạng thái cục bộ của **một** lần xử lý, không bị chia sẻ giữa các thread, và mỗi bước cập nhật được mô tả tường minh.

Lưu ý: biến cục bộ của vòng lặp **vẫn là trạng thái**, không phải “thuần hàm”. Điểm khác là trạng thái này có chủ đích, phạm vi ngắn và luồng điều khiển rõ ràng. Không có quy tắc bắt buộc mọi tác vụ phải viết bằng Stream.

## 10. Side effect nào có thể chấp nhận?

Không phải mọi side effect đều bị Java cấm. `forEach` được thiết kế như một terminal operation cho hành động trên mỗi phần tử; việc ghi log, gọi I/O hoặc gửi thông điệp có thể là mục tiêu thật của pipeline. Tuy nhiên, cần hiểu rõ:

- **Thứ tự**: `forEach` trên parallel Stream không bảo đảm encounter order; `forEachOrdered` có thể giữ thứ tự hành động của nguồn có thứ tự.
- **Thread safety**: hành động có thể chạy trên nhiều thread; tài nguyên bên ngoài phải được thiết kế cho cập nhật đồng thời nếu cần.
- **Thất bại từng phần**: ghi file, gửi mạng hoặc DB có thể thất bại sau khi một số phần tử đã hoàn thành; Stream không tự cung cấp transaction/retry/idempotency.
- **Dừng sớm và tối ưu**: không coi tác dụng phụ trong intermediate operation như `map` hoặc `peek` là bước bắt buộc cho mọi phần tử.
- **Thiết kế kết quả**: nếu mục tiêu là thu thập List/Map/tổng, dùng terminal collector thay vì xây `List`/Map dùng chung từ lambda.

Ví dụ, khi ứng dụng cần ghi tất cả sự kiện theo thứ tự và tác vụ I/O cần tuần tự, một vòng lặp `for` với xử lý ngoại lệ rõ ràng có thể dễ kiểm soát hơn `parallelStream().forEach(...)`. Còn nếu mục tiêu chỉ là biến dữ liệu thành List, dùng `.map(...).toList()`.

### `peek` không phải hệ thống ghi nhận sự kiện tin cậy

```java
long count = words.stream()
        .peek(System.out::println)
        .count();
```

Lời gọi `peek` có thể không được thực thi với mọi phần tử nếu terminal operation xác định kết quả bằng tối ưu hóa, ví dụ khi kích thước nguồn đã biết. `peek` được dùng chủ yếu để quan sát/debug, không nên là nơi duy nhất đảm nhận side effect nghiệp vụ bắt buộc.

## 11. `reduce` và `collect` không cho phép mutate biến global tùy tiện

### `reduce` là phép gộp giá trị

```java
int sum = numbers.stream().reduce(0, Integer::sum);
```

Một reduction đúng phải đáp ứng identity trung hòa và phép kết hợp phù hợp với việc phân nhóm, nhất là khi song song. Không nên viết:

```java
AtomicInteger external = new AtomicInteger();

int result = numbers.parallelStream()
        .reduce(0, (a, b) -> {
            external.addAndGet(b);
            return a + b;
        });
```

Đoạn phản ví dụ có trạng thái ngoài; việc cộng vào `external` không thuộc kết quả của phép reduction và có thể phụ thuộc cách framework gọi operator. Điều quan trọng là kết quả `result`, không phải side effect có thể bị thay đổi bởi cách phân chia/gộp.

### `collect` quản lý container bên trong

Với mutable accumulation, nên dùng collector:

```java
List<String> result = words.parallelStream()
        .collect(Collectors.toList());
```

Collector chuẩn có cơ chế tạo/gộp container khi cần. Đừng thay bằng:

```java
List<String> shared = new ArrayList<>();
words.parallelStream().forEach(shared::add); // Không an toàn.
```

Việc dùng `Collections.synchronizedList` có thể bảo vệ thao tác thêm, nhưng **không tự bảo đảm thứ tự xuất hiện** tương đương nguồn. Nếu điều bạn muốn là một danh sách theo encounter order, collector là giải pháp biểu đạt đúng hơn.

### `CONCURRENT` không đồng nghĩa “muốn dùng song song”

Khi viết collector tùy chỉnh, đánh dấu `CONCURRENT` chỉ khi accumulator thực sự hỗ trợ nhiều thread cập nhật **cùng một container** an toàn. Một collector không có `CONCURRENT` vẫn có thể thu thập Stream song song bằng những container riêng biệt và combiner phù hợp. Không nên gắn `CONCURRENT` lên một `ArrayList` hoặc bộ đếm mutable thường để “tăng tốc”.

## 12. Những quan niệm sai phổ biến

| Quan niệm sai | Sự thật |
| --- | --- |
| “Biến local capture phải effectively final nên mọi lambda đều thuần” | Tham chiếu không bị gán lại nhưng object/mảng vẫn có thể bị sửa |
| “Dùng `AtomicInteger` là an toàn rồi” | Atomic đảm bảo cập nhật biến, không đảm bảo gắn chỉ số đúng encounter order |
| “Stream từ `List` có thứ tự thì mọi lambda chạy theo thứ tự” | Encounter order không đồng nghĩa execution order khi parallel |
| “`toList()` giữ thứ tự thì nhãn từ counter cũng đúng thứ tự” | `toList` giữ vị trí kết quả, không sửa các giá trị đã được gán sai |
| “`forEachOrdered` sửa được nhãn gán ở `map`” | Nó chỉ áp đặt thứ tự cho hành động terminal |
| “`peek` hoặc `map` chắc chắn chạy trên mọi phần tử” | Một số terminal có thể dừng sớm hoặc bỏ qua callback không ảnh hưởng kết quả |
| “`synchronizedList` giải quyết thứ tự” | Nó hỗ trợ đồng bộ thao tác, không cam kết thứ tự gọi của các thread |
| “Luôn phải dùng Stream thay vòng lặp” | Vòng lặp tuần tự rất phù hợp với bài toán có trạng thái theo thứ tự |
| “Ghi vào biến ngoài chỉ để log thì không ảnh hưởng” | Side effect có thể làm chương trình phụ thuộc số lần gọi, thứ tự và thất bại I/O |

## 13. Kiểm thử để phát hiện phụ thuộc thứ tự

Một bộ test tốt cần đặt câu hỏi **hàm có tạo đúng giá trị từ phần tử, hay kết quả phụ thuộc vào lịch sử gọi lambda?**

### So sánh tuần tự và song song

Với phép biến đổi thuần:

```java
List<String> sequential = words.stream()
        .map(String::toUpperCase)
        .toList();

List<String> parallel = words.parallelStream()
        .map(String::toUpperCase)
        .toList();
```

Trong ví dụ `words` là List có thứ tự, String không null. Hai kết quả phải bằng nhau vì mỗi phần tử biến đổi độc lập và `toList` giữ encounter order. Đây là phép kiểm thử **giá trị kết quả**, không phải test số lần callback chạy.

Với counter ngoài, không viết test mong một mapping cụ thể từ `parallelStream`: một lần chạy ra đúng vẫn có thể chỉ là cách lên lịch trùng may mắn. Đừng dùng `Thread.sleep` để cố ép lịch trình vì nó khiến test chậm và không đáng tin cậy; cần **sửa thiết kế**.

### Kiểm tra tính đúng ở nhiều vị trí thao tác

Nếu pipeline có `filter`, `sorted`, `limit`, hãy viết test cho:

1. Dữ liệu rỗng và chỉ có một phần tử.
2. Dữ liệu có trùng lặp hoặc nhiều giá trị cùng thứ tự so sánh.
3. Chuyển vị trí bước được phép thay đổi theo yêu cầu, xác định có làm đổi nhãn không.
4. Kết quả tuần tự và song song (chỉ khi nghiệp vụ cho phép song song).
5. Source không bị sửa trong lúc duyệt.
6. Thứ tự và gắn index khi input có encounter order.
7. Kích thước dữ liệu nhỏ/lớn, không chỉ một ca ba phần tử.

Test thứ tự không có nghĩa mọi callback phải gọi lần lượt; hãy test **output và các invariant được công bố**, ví dụ `indexed.get(i)` luôn bắt đầu bằng `(i+1) + ":"` và vẫn trỏ đúng phần tử `words.get(i)`.

### Các bất biến có thể kiểm tra

Đối với `List<String> indexed` được tạo từ `IntStream.range(0, words.size())`:

```text
indexed.size() == words.size()
indexed[i] == (i + 1) + ":" + words[i]
```

Hai bất biến này đúng với nguồn ổn định và pipeline thuần trong ví dụ. Chúng không dựa vào thread, số lần callback hay lịch sử của một biến đếm. Test như vậy diễn đạt rõ hợp đồng hơn kiểm tra `AtomicInteger.get() == n`.

## 14. Các lỗi thiết kế cần tránh

**Lỗi 1: dùng biến ngoài để đánh số trong `map` rồi bật parallel.** Có thể gắn số cho sai phần tử dù mọi số vẫn khác nhau. Dùng index nguồn hoặc tách bước đánh số tuần tự rõ ràng.

**Lỗi 2: thay `map` bằng `peek` chỉ để cập nhật biến.** `peek` là intermediate operation có thể bị bỏ qua do tối ưu; không phải giải pháp cho side effect cần thiết.

**Lỗi 3: sửa `ArrayList` nguồn từ `forEach`.** Vi phạm non-interference; có nguy cơ lỗi hoặc kết quả không đoán được.

**Lỗi 4: ghi trực tiếp vào một `ArrayList` ngoài từ `parallelStream().forEach`.** Có race condition. Dùng `.toList()` hoặc collector.

**Lỗi 5: dùng `AtomicInteger` để “sửa” thứ tự nhưng không thay thuật toán.** Atomic xử lý truy cập đồng thời, không xử lý thứ tự logic của dữ liệu.

**Lỗi 6: dựa vào thứ tự in log để suy ra thứ tự phần tử.** `System.out.println` ở nhiều thread là quan sát side effect, không là định nghĩa encounter order.

**Lỗi 7: dùng `forEachOrdered` khi side effect đã xảy ra ở bước trước.** Nó không đảo ngược cách gắn nhãn đã thực hiện trong `map`.

**Lỗi 8: để một biến static bên ngoài lưu trạng thái qua nhiều lần gọi.** Lần xử lý thứ hai có thể nhận số tiếp theo của lần thứ nhất; test chạy độc lập hoặc chạy theo thứ tự khác sẽ cho kết quả khác.

**Lỗi 9: quên `limit`/short-circuit khiến chỉ một phần dữ liệu được xét.** Không đặt việc quan trọng phải xảy ra với mọi đầu vào trong một lambda trung gian nếu terminal có thể dừng sớm.

**Lỗi 10: dùng phép reduction có side effect thay vì giá trị thuần.** Các toán tử gộp phải thỏa hợp đồng kết hợp/identity; cập nhật biến global không thay thế accumulator đúng.

**Lỗi 11: nghĩ thứ tự luôn được xác định.** `HashSet.stream()` và các nguồn unordered không có encounter order như List. Nếu cần thứ tự, tạo thứ tự bằng sort/comparator phù hợp hoặc chọn nguồn thích hợp.

**Lỗi 12: chuyển mọi logic tuần tự sang Stream để giảm số dòng.** Với prefix sums, parser trạng thái hoặc quy trình cần điều kiện `break` phức tạp, vòng lặp có thể rõ ràng hơn và ít lỗi hơn.

## 15. Quy trình chọn giải pháp

Khi gặp code Stream có biến bên ngoài bị sửa, hãy hỏi lần lượt:

1. **Đây có phải phép biến đổi độc lập từng phần tử?** Nếu có, viết `map` thuần và để kết quả truyền qua pipeline, không dùng biến ngoài.
2. **Có thực sự cần số thứ tự?** Nếu có, số đó thuộc *chỉ số của nguồn*, *vị trí sau lọc*, hay *vị trí sau sắp xếp*? Xác định đúng trước khi viết.
3. **Có chỉ cần một giá trị tổng hợp?** Dùng `count`, `sum`, `reduce`, `collect`.
4. **Có cần dãy kết quả phụ thuộc phần tử trước?** Vòng lặp tuần tự hoặc thuật toán scan chuyên biệt thường rõ hơn.
5. **Có tác dụng phụ ngoài hệ thống không?** Xem lại thứ tự, retry/idempotency, transaction, lỗi từng phần và thread safety.
6. **Chạy song song có ý nghĩa thật không?** Đừng bật `parallel()` chỉ để tăng tốc khi logic đang phụ thuộc trạng thái chia sẻ.
7. **Kiểm thử đang xác nhận điều gì?** Hãy xác nhận kết quả và các invariant, không chỉ một lịch trình thực thi tình cờ.

## 16. Bài tập thực hành

1. Cho `List.of("B", "A", "C")`. Dùng `AtomicInteger` để đánh số trước `sorted`, dự đoán kết quả; sau đó `sorted` trước khi đánh số và so sánh. Viết lời giải thích về vị trí thực hiện stateful operation.
2. Thay cách đánh số bằng `IntStream.range`, tạo hai phiên bản: giữ thứ tự gốc và đánh số sau sắp xếp. Test đúng vị trí/giá trị và chạy lại với `parallel()` ở phiên bản index thuần.
3. Giải thích vì sao `AtomicInteger.incrementAndGet()` không thể hứa rằng phần tử đầu tiên của List nhận số 1 trong `parallelStream`.
4. Cho pipeline `source.stream().map(x -> { counter.incrementAndGet(); return x; }).count()`. Phân tích vì sao counter không phải thước đo đáng tin cậy về số phần tử đã xử lý.
5. Tạo chương trình tính tổng tiền tố của `List.of(3, 1, 4, 2)`. Kết quả mong đợi `[3, 4, 8, 10]`. Giải thích vì sao một vòng lặp có `running` cục bộ là thiết kế hợp lý.
6. Từ danh sách nhân viên, dùng `Collectors.groupingBy(Employee::department, counting())` để đếm người mỗi phòng, không cập nhật `HashMap` ngoài lambda. Kiểm thử số lượng mỗi nhóm.
7. Viết ví dụ `parallelStream().forEach` in chuỗi và `forEachOrdered` in chuỗi; mô tả điều được cam kết và điều không được cam kết, không dùng output may rủi làm khẳng định tuyệt đối.
8. Refactor đoạn `parallelStream().forEach(sharedList::add)` thành terminal collector. Kiểm thử nội dung List thay vì kiểm thử thứ tự gọi `add`.
9. Viết một ca test minh họa `sorted` sau `map` không thể đổi lại nhãn đã gắn. So sánh với cách `sorted().toList()` rồi đánh số qua index.
10. Đối với thao tác ghi log/DB của từng phần tử, đề xuất chính sách thứ tự, timeout, retry và cách xử lý khi một phần tử thất bại. Giải thích vì sao `.map` với side effect và một terminal `count()` không phải phương án đảm bảo xử lý.

## 17. Kết luận

**Thay đổi biến bên ngoài trong lambda có thể làm kết quả phụ thuộc thứ tự thực thi, số lần gọi callback và trạng thái từ lần xử lý trước.** Một `Stream` có encounter order không có nghĩa mọi callback luôn chạy theo thứ tự đó, nhất là khi song song. `AtomicInteger` giúp thao tác cập nhật an toàn ở mức biến, **không bảo đảm phần tử nào nhận nhãn nào**.

Để viết Stream đúng và dễ bảo trì:

- Ưu tiên các hàm **stateless, non-interfering** trong `map`, `filter` và những thao tác trung gian.
- Dùng **index thực của nguồn** khi yêu cầu đánh số có vị trí ổn định.
- Dùng **terminal operation** (`count`, `sum`, `reduce`, `collect`) cho tổng hợp thay vì biến global.
- Dùng vòng lặp rõ ràng nếu quy trình thực sự phụ thuộc trạng thái tuần tự.
- Dùng `forEachOrdered` chỉ khi cần thứ tự hành động terminal, không coi nó là cách sửa các side effect từ giai đoạn trước.
- Test **giá trị cuối và các invariant nghiệp vụ**, không dùng một lịch trình thread hoặc số lần lambda được gọi làm bằng chứng đúng đắn.

Nhờ tách rõ *dữ liệu* khỏi *trạng thái thay đổi ngoài pipeline*, chương trình giữ được tính dễ hiểu, dễ kiểm thử và dễ chuyển từ xử lý tuần tự sang song song khi phù hợp.
