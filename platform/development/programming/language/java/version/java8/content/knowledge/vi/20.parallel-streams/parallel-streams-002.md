# Chia nguồn, xử lý và gộp kết quả trong Java Parallel Stream

> **Chủ đề:** Java 8 — Stream song song. Bài học trình bày các hợp đồng `Stream`, `Spliterator`, `reduce` và `collect` vẫn được dùng trong Java hiện đại; không dựa vào chi tiết triển khai hoặc kỹ thuật đã lỗi thời.

## 1. Bức tranh tổng thể: split → process → combine

Với Stream tuần tự (**sequential**), các phần tử thường được duyệt qua một pipeline bằng một luồng thực thi. Với Stream song song (**parallel**), Java có thể **chia nguồn dữ liệu thành các phần**, xử lý các phần đó bằng nhiều tác vụ và **gộp kết quả từng phần** để tạo đầu ra cuối.

~~~text
                 Nguồn ordered: [1,2,3,4,5,6,7,8]
                               |
                         Chia nguồn
                    (Spliterator.trySplit)
                        /            \
                phần A                phần B
               [1,2,3,4]            [5,6,7,8]
                  |                     |
              xử lý A                xử lý B
                  |                     |
             tổng A = 10             tổng B = 26
                  \                     /
                   \---- gộp: 10 + 26--/
                               |
                         kết quả = 36
~~~

Sơ đồ trên là **mô hình minh họa**, không phải lịch chia việc được Java cam kết. JVM có thể chia thành nhiều phần khác nhau, kích thước không bằng nhau, tác vụ thực hiện trên các thread khác nhau hoặc một số phần được xử lý trong cùng thread. Phương pháp chia cụ thể là chi tiết thực thi, **không nên viết logic dựa vào “luôn có 2/4/8 nhánh”**.

Ba trách nhiệm cần phân biệt:

1. **Chia nguồn (split):** tạo những phần dữ liệu có thể được duyệt độc lập, thông qua cơ chế `Spliterator`.
2. **Xử lý (process):** áp dụng các bước pipeline như `filter`, `map`, `mapToInt` hoặc cập nhật container kết quả cục bộ.
3. **Gộp (combine/merge):** kết hợp kết quả các phần theo phép reduction/collector phù hợp, đồng thời tôn trọng encounter order nếu hợp đồng yêu cầu.

Ví dụ:

~~~java
int sum = IntStream.rangeClosed(1, 8)
        .parallel()
        .sum();  // 36
~~~

`parallel()` đánh dấu pipeline chạy ở chế độ parallel. `sum()` là terminal operation thực hiện phép tính; vì cộng số nguyên là phép kết hợp phù hợp (với miền giá trị xét trong ví dụ), các phần có thể tính tổng riêng rồi cộng lại.

**Parallel không đồng nghĩa nhanh hơn**. Chia việc, lên lịch, gộp kết quả, duy trì thứ tự và contention đều có chi phí. Trước tiên cần đảm bảo **đúng kết quả và đúng hợp đồng**, sau đó mới đo hiệu năng.

## 2. Bật parallel ở đâu và pipeline được thực thi khi nào?

Những cách tạo parallel stream phổ biến:

~~~java
list.parallelStream();            // Collection có API này từ Java 8.
list.stream().parallel();         // Chuyển chế độ của stream pipeline.
IntStream.range(0, 100).parallel();
~~~

Ba dòng là **biểu thức minh họa**, chưa có terminal operation và giả định `list` là một collection.

- Stream **lazy**: `map`, `filter`, `parallel` thường chỉ thiết lập pipeline; xử lý thực tế bắt đầu khi có terminal operation như `sum`, `collect`, `reduce` hoặc `forEach`.
- `parallel()` và `sequential()` đặt **chế độ của cả pipeline**, không tạo “một bước chạy parallel, bước sau chạy sequential” theo cách ghép stage thông thường; lựa chọn chế độ gần nhất quyết định lúc pipeline được thực thi.
- `isParallel()` cho biết chế độ đã đặt; **không** chứng minh rằng JVM đã sử dụng nhiều CPU trong một lần tính.
- Một đối tượng Stream **chỉ sử dụng được cho một quá trình tiêu thụ**. Không gọi hai terminal operation trên cùng Stream; cần tạo stream mới từ nguồn.
- `parallel()` không tự phân bổ một thread cho mỗi phần tử, không biến phép tính thành asynchronous API và không cam kết số thread hoặc thứ tự chạy.

Ví dụ đầy đủ về cùng một logic:

~~~java
int sequential = IntStream.rangeClosed(1, 8)
        .map(n -> n * n)
        .sum();

int parallel = IntStream.rangeClosed(1, 8)
        .parallel()
        .map(n -> n * n)
        .sum();

// Cả hai đều bằng 204.
~~~

Kết quả là tổng các bình phương từ 1 đến 8, không phải kết quả khác khi bật parallel. Việc xử lý phần tử `n` diễn ra ở thread nào và theo thứ tự thời gian nào **không ảnh hưởng kết quả**, vì `map` thuần và `sum` có phép gộp phù hợp.

## 3. Chia nguồn: Spliterator hoạt động như thế nào?

### 3.1. Spliterator là gì?

`java.util.Spliterator<T>` là giao diện hỗ trợ **duyệt phần tử** và **tách dữ liệu thành các phần con**. Nó cung cấp nguồn dữ liệu cho Stream, đặc biệt hữu ích khi Stream chạy song song.

Các phương thức quan trọng:

| Phương thức | Ý nghĩa |
| --- | --- |
| `tryAdvance(action)` | Thử duyệt phần tử kế tiếp, trả `true` nếu có; ngược lại `false`. |
| `forEachRemaining(action)` | Duyệt hết phần tử còn lại của Spliterator. |
| `trySplit()` | Nếu có thể tách, trả Spliterator mới bao phủ **một phần** dữ liệu; phần đó không còn do Spliterator gốc bao phủ. Trả `null` khi không tách được. |
| `estimateSize()` | Ước lượng số phần tử còn lại; có thể không chính xác nếu nguồn không có kích thước xác định. |
| `characteristics()` | Các cờ mô tả những hợp đồng của nguồn, ví dụ `ORDERED`, `SIZED`, `SUBSIZED`. |
| `getExactSizeIfKnown()` | Trả kích thước chính xác khi nguồn có `SIZED`; nếu không, trả `-1`. |

Với Spliterator **`ORDERED`**, `trySplit()` thành công phải tách ra **một prefix** (đoạn đầu) trong encounter order, còn phần tiếp tục được duyệt từ Spliterator gốc là phần còn lại. Điều đó giúp những phép reduction/collector yêu cầu thứ tự có thể ghép kết quả đúng.

**Không có cam kết chia đôi chính xác**. `trySplit()` có thể trả `null` hoặc tạo các phần lệch nhau vì cấu trúc nguồn, chi phí chia hoặc điều kiện runtime. Một Spliterator có thể tách được không có nghĩa mọi lần chia đều hiệu quả.

### 3.2. Đặc tính của nguồn ảnh hưởng khả năng chia

| Spliterator characteristic | Ý nghĩa cho stream song song |
| --- | --- |
| `ORDERED` | Có encounter order. Phép tính phụ thuộc thứ tự phải tôn trọng nó. |
| `SIZED` | Biết chính xác số phần tử còn lại theo điều kiện hợp đồng; framework có thêm thông tin để phân chia. |
| `SUBSIZED` | Các Spliterator con sinh ra sau khi tách cũng là `SIZED` và `SUBSIZED`; thuận tiện cho việc chia và phân bổ. |
| `IMMUTABLE` hoặc `CONCURRENT` (của Spliterator) | Mô tả cách dữ liệu nguồn có thể thay đổi; **không** đồng nghĩa accumulator của collector an toàn đa luồng. |
| `DISTINCT` / `SORTED` | Có thể hỗ trợ tối ưu một số bước pipeline vì nguồn đã có tính chất tương ứng. |

**Phân biệt:** `Spliterator.CONCURRENT` nói về nguồn; `Collector.Characteristics.CONCURRENT` nói về phép tích lũy. Chúng là hai hợp đồng **khác nhau**, không thể thay thế.

Ví dụ, nguồn backed by array hoặc `ArrayList` thường thuận lợi hơn khi phân hoạch so với nguồn mà muốn chia phải duyệt qua nhiều phần tử hoặc đọc từ một I/O source. Nhưng hiệu năng thực tế còn phụ thuộc kích thước dữ liệu, pipeline và workload, không chỉ tên collection.

### 3.3. Ví dụ tách thủ công để hiểu nguyên tắc

~~~java
List<Integer> numbers = Arrays.asList(1, 2, 3, 4, 5, 6, 7, 8);

Spliterator<Integer> remaining = numbers.spliterator();
Spliterator<Integer> prefix = remaining.trySplit();

List<Integer> reconstructed = new ArrayList<>();
if (prefix != null) {
    prefix.forEachRemaining(reconstructed::add);
}
remaining.forEachRemaining(reconstructed::add);

System.out.println(reconstructed);
// [1, 2, 3, 4, 5, 6, 7, 8]
~~~

Đây là **đoạn minh họa**, giả định đã import `Arrays`, `List`, `Spliterator`, `ArrayList`. Bởi nguồn là `List` có `ORDERED`, khi tách thành prefix + remainder rồi duyệt lần lượt, ta tái lập encounter order ban đầu. Ngay cả khi `trySplit()` trả `null`, mã vẫn đọc toàn bộ nguồn thông qua `remaining`.

**Lưu ý an toàn:** Không cho hai thread cùng thao tác trực tiếp lên **chính một đối tượng Spliterator** mà không có bảo đảm đồng bộ. Khi tách thành công, mỗi Spliterator con nên được giao cho tác vụ riêng để duyệt; hành vi khi cùng một Spliterator bị tách và duyệt đồng thời không được xác định. Chương trình ví dụ chỉ tách/duyệt **tuần tự** nhằm minh họa hợp đồng, không giả lập scheduler của parallel stream.

## 4. Xử lý: các tác vụ thực hiện một pipeline, không phải mỗi stage một thread

Xét pipeline:

~~~java
long count = numbers.parallelStream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * 10)
        .count();
~~~

Đoạn minh họa giả định `numbers` là `List<Integer>`. Về **ý nghĩa**, pipeline lọc số chẵn, nhân 10 rồi đếm phần tử. Nhưng không được mặc định rằng phép `map` luôn được gọi: Java được phép **bỏ qua các thao tác không ảnh hưởng kết quả** trong một số pipeline đã tối ưu. Vì vậy, mọi lambda cần **stateless**, **non-interfering** và không dựa vào side effect bắt buộc.

### 4.1. Stateless và non-interfering

**Stateless:** kết quả của `map`, `filter` hoặc các callback không phụ thuộc biến đếm chia sẻ, lịch thread hay trạng thái mutable thay đổi giữa các phần tử.

**Non-interfering:** không chỉnh sửa nguồn dữ liệu không hỗ trợ concurrent modification khi pipeline đang duyệt; việc sửa nguồn có thể làm kết quả không xác định hoặc gây lỗi.

Ví dụ tốt:

~~~java
List<Integer> squares = numbers.parallelStream()
        .map(n -> n * n)
        .collect(Collectors.toList());
~~~

Ví dụ sai khi nguồn là `ArrayList` chia sẻ:

~~~java
List<Integer> result = new ArrayList<>();

numbers.parallelStream()
        .forEach(n -> result.add(n * n)); // KHÔNG AN TOÀN
~~~

Hai đoạn là **minh họa**. `ArrayList.add` không hỗ trợ nhiều thread sửa cùng một List. `collect(Collectors.toList())` thích hợp vì framework quản lý các container tích lũy riêng rồi gộp; **không cần** cho nhiều thread cùng gọi `add` trên một danh sách dùng chung.

Thay `ArrayList` bằng `Collections.synchronizedList` có thể tránh race ở những thao tác cụ thể, nhưng thêm contention và **không bảo đảm encounter order** của `forEach`. Đừng dùng “đã synchronized” làm lý do để bỏ qua mô hình reduction của Stream.

### 4.2. Thứ tự xử lý không giống thứ tự kết quả

Với nguồn ordered như `List.stream()`, `collect(Collectors.toList())` có nghĩa kết quả giữ encounter order mặc dù tác vụ xử lý có thể chạy ở thứ tự thời gian khác nhau. Chẳng hạn:

~~~java
List<Integer> result = Arrays.asList(1, 2, 3, 4)
        .parallelStream()
        .map(n -> n * 10)
        .collect(Collectors.toList());

// result có giá trị [10, 20, 30, 40].
~~~

Nhưng `parallelStream().forEach(System.out::println)` **không cam kết thứ tự in**. `forEachOrdered` bảo đảm thứ tự *action* theo encounter order khi stream ordered, song có thể làm giảm cơ hội tối ưu parallel và không có nghĩa mọi callback upstream cũng chạy theo thứ tự đó.

## 5. Gộp kết quả: reduction phải thỏa identity và associativity

Chia được nguồn **chưa đủ**. Muốn có kết quả đúng khi gộp các phần, phép tổng hợp phải phù hợp với việc phân nhóm theo nhiều cách.

### 5.1. Associativity — tính kết hợp

Phép `op` có tính kết hợp nếu:

~~~text
(a op b) op c == a op (b op c)
~~~

Ví dụ cộng:

~~~text
(1 + 2) + (3 + 4) = 10
1 + (2 + (3 + 4)) = 10
~~~

Vì thế Java có thể tính tổng các phần độc lập và cộng kết quả. Ngược lại, **phép trừ không kết hợp**:

~~~text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
~~~

Không viết reduction song song mà người lập trình kỳ vọng một chuỗi phép trừ trái sang phải:

~~~java
// Không phù hợp để dựa vào kết quả nhất quán giữa các cách phân nhóm:
int wrong = numbers.parallelStream()
        .reduce(0, (a, b) -> a - b);
~~~

Đoạn trên là **minh họa về sai lầm thiết kế**, không phải ví dụ có stdout cố định. `reduce` có quyền kết hợp các phần theo cây thay vì theo thứ tự tính tuần tự; phép trừ khiến đáp án phụ thuộc cách nhóm.

**Chú ý phép tính dấu phẩy động:** cộng `double` và `float` **không có tính kết hợp tuyệt đối theo toán học trên máy tính** do làm tròn. Parallel reduction có thể cho sai khác nhỏ so với sequential. Với số tiền hoặc phép tính cần độ chính xác chặt, cần chọn biểu diễn, thuật toán và chính sách sai số phù hợp; không mặc định bit-for-bit giống nhau.

### 5.2. Identity — phần tử đơn vị

Với `reduce(identity, accumulator, combiner)`, identity phải trung hòa phép kết hợp. Với phép cộng là `0`, với phép nhân là `1`.

~~~java
int total = numbers.parallelStream()
        .reduce(0, Integer::sum, Integer::sum);
~~~

Ở ví dụ này, `accumulator` và `combiner` đều là `Integer::sum`; kết quả giống nhau cho mọi cách phân nhóm hợp lệ. Dạng ba tham số đặc biệt hữu ích khi kiểu tích lũy khác kiểu phần tử đầu vào.

Không đặt identity “khởi tạo số dư 100” rồi cộng từng nhánh nếu **100 chỉ được cộng đúng một lần**: trong phép reduction song song, identity có thể được dùng làm điểm bắt đầu cho **nhiều phần**, dẫn tới cộng 100 nhiều lần. Nếu cần cộng khoản cố định một lần, hãy tính kết quả tổng trước rồi cộng khoản đó **sau** terminal reduction.

### 5.3. Tính tương thích accumulator và combiner

Với `Stream<T>`, overload:

~~~java
<U> U reduce(U identity,
             BiFunction<U, ? super T, U> accumulator,
             BinaryOperator<U> combiner)
~~~

là **chữ ký API minh họa**. Ngoài identity và associativity, `combiner` phải tương thích với `accumulator`. Điều đó nghĩa là tích lũy một phần tử vào `u` phải tương đương với gộp `u` cùng kết quả tích lũy phần tử đó từ identity:

~~~text
combiner(u, accumulator(identity, t))
    tương đương accumulator(u, t)
~~~

Ví dụ đúng, tổng độ dài chuỗi:

~~~java
int totalLength = Stream.of("An", "Binh", "Chi")
        .parallel()
        .reduce(0,
                (length, word) -> length + word.length(),
                Integer::sum);

// totalLength = 2 + 4 + 3 = 9.
~~~

Không dùng combiner `(a, b) -> a - b` hoặc bỏ qua `b`; sequential có thể vẫn ra kết quả có vẻ đúng vì có trường hợp không cần combiner, nhưng parallel sẽ lộ sai sót.

## 6. Mutable reduction: collect và combiner của Collector

`collect` thường được dùng để gom thành `List`, `Set`, `Map` hoặc một cấu trúc thống kê. Với `Collector<T, A, R>`:

| Thành phần | Trách nhiệm | Ví dụ List |
| --- | --- | --- |
| `supplier()` | Tạo container tích lũy rỗng, độc lập | `ArrayList::new` |
| `accumulator()` | Thêm một phần tử vào container | `List::add` |
| `combiner()` | Gộp hai container trung gian | `left.addAll(right); return left;` |
| `finisher()` | Chuyển container thành kết quả cuối (nếu cần) | `Function.identity()` |
| `characteristics()` | Nêu các hợp đồng như `IDENTITY_FINISH`, `UNORDERED`, `CONCURRENT` | Tùy collector |

### 6.1. Vì sao một ArrayList thông thường vẫn dùng được trong parallel collect?

~~~java
List<String> words = Stream.of("a", "b", "c")
        .parallel()
        .collect(Collectors.toList());
~~~

Kết quả là `[a, b, c]` do Stream có encounter order. Điều này **không có nghĩa** mọi thread cùng sửa một `ArrayList`. Với một collector không khai báo concurrent reduction, implementation có thể đưa mỗi phần việc vào một container riêng, rồi dùng combiner ghép các container. Cách tổ chức nội bộ chính xác do framework quyết định.

Đặc tính **`Collector.Characteristics.CONCURRENT`** mới là lời hứa rằng accumulator an toàn khi nhiều thread cùng tích lũy vào **một container**. Concurrent reduction chỉ có thể áp dụng khi Stream chạy parallel, collector là CONCURRENT và **nguồn unordered hoặc collector UNORDERED**. Không tự gắn `CONCURRENT` vào custom collector sử dụng `ArrayList.add` trên container chung.

### 6.2. Ví dụ custom Collector giữ encounter order

~~~java
Collector<Integer, List<Integer>, List<Integer>> myListCollector =
        Collector.of(
                ArrayList::new,
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });

List<Integer> result = numbers.parallelStream()
        .collect(myListCollector);
~~~

Đoạn này là **mã minh họa**, giả định `numbers` là `List<Integer>` đã import `Collector`, `ArrayList`, `List`. Với nguồn ordered, collector không khai báo `UNORDERED`, và combiner ghép `left` trước `right`; kết quả List bảo toàn encounter order. Factory `Collector.of(supplier, accumulator, combiner)` tự gắn đặc tính `IDENTITY_FINISH` vì container chính là kết quả cuối.

**Không viết combiner làm mất nửa dữ liệu:**

~~~java
// SAI: không thêm phần tử từ right.
(left, right) -> left
~~~

Đây là lambda minh họa, không phải cả một chương trình. Lỗi có thể khó lộ nếu chỉ chạy sequential hoặc trên dữ liệu nhỏ, nhưng khi chia nguồn thành nhiều nhánh thì kết quả bị thiếu.

### 6.3. Overload collect ba tham số

Ngoài `collect(Collector)`, Stream còn có:

~~~java
List<Integer> copied = numbers.parallelStream()
        .collect(ArrayList::new,
                List::add,
                List::addAll);
~~~

Ba đối số lần lượt là **supplier**, **accumulator** và **combiner** theo dạng `BiConsumer`. Đây là **mã minh họa** với `numbers` kiểu `List<Integer>`, nhập thêm `java.util.ArrayList` và `java.util.List`. Khác với `Collector.of`, combiner trong overload này **không trả container**; nó cập nhật container bên trái.

Tách thành phần có thể giúp ta hiểu:

~~~text
Tác vụ A: new ArrayList -> add(1),add(2) -> [1,2]
Tác vụ B: new ArrayList -> add(3),add(4) -> [3,4]
Combiner: listA.addAll(listB) -> [1,2,3,4]
~~~

Đây vẫn là ví dụ **minh họa kế hoạch phân việc**; số container, thời điểm gọi combiner và lịch thread không được cố định.

### 6.4. groupingBy, toMap và chi phí gộp

Gộp hai container danh sách đơn giản hơn nhiều so với gộp nhiều Map nhóm lớn, vì các khóa trùng nhau cần được giải quyết. Với `Collectors.groupingBy(key)`, parallel collect có thể tốn chi phí merge Map đáng kể. `groupingByConcurrent(key)` cho concurrent reduction khi điều kiện cho phép và chấp nhận **không duy trì thứ tự các phần tử trong từng nhóm**.

Không chọn `groupingByConcurrent` chỉ vì thấy chữ concurrent: nếu nghiệp vụ cần thứ tự phần tử trong mỗi nhóm, phải dùng collector giữ được encounter order và đánh giá chi phí của cách gộp.

## 7. Chương trình chạy được: minh họa split, process và combine

Lưu thành tệp **ParallelSplitProcessMergeDemo.java**. Chương trình sử dụng API Java 8, có kết quả có thể dự đoán dù runtime thay đổi cách chia các tác vụ.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Spliterator;
import java.util.stream.Collector;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ParallelSplitProcessMergeDemo {
    public static void main(String[] args) {
        List<Integer> numbers = IntStream.rangeClosed(1, 8)
                .boxed()
                .collect(Collectors.toList());

        // Split thủ công để quan sát hợp đồng ORDERED.
        Spliterator<Integer> remaining = numbers.spliterator();
        Spliterator<Integer> prefix = remaining.trySplit();
        List<Integer> reconstructed = new ArrayList<>();
        if (prefix != null) {
            prefix.forEachRemaining(reconstructed::add);
        }
        remaining.forEachRemaining(reconstructed::add);
        System.out.println("manual rejoin = " + reconstructed);

        // Parallel reduction bằng phép cộng có tính kết hợp.
        int total = numbers.parallelStream()
                .reduce(0, Integer::sum);
        System.out.println("sum = " + total);

        // Process (map) rồi gộp tổng qua specialized stream.
        int sumSquares = numbers.parallelStream()
                .mapToInt(n -> n * n)
                .sum();
        System.out.println("sumSquares = " + sumSquares);

        // Giữ encounter order của nguồn List.
        List<Integer> tens = numbers.parallelStream()
                .map(n -> n * 10)
                .collect(Collectors.toList());
        System.out.println("tens = " + tens);

        // Collector tùy biến: tích lũy và gộp các List cục bộ.
        Collector<Integer, List<Integer>, List<Integer>> myCollector =
                Collector.of(
                        ArrayList::new,
                        List::add,
                        (left, right) -> {
                            left.addAll(right);
                            return left;
                        });

        List<Integer> collected = numbers.parallelStream()
                .collect(myCollector);
        System.out.println("custom list = " + collected);

        // Gộp các số đếm: mỗi số rơi vào một nhánh.
        Map<Boolean, Long> counts = numbers.parallelStream()
                .collect(Collectors.partitioningBy(
                        n -> n % 2 == 0,
                        Collectors.counting()));
        System.out.println("even = " + counts.get(true)
                + ", odd = " + counts.get(false));
    }
}
~~~

Biên dịch bằng JDK 17+ với mức API và ngôn ngữ Java 8:

~~~bash
javac --release 8 ParallelSplitProcessMergeDemo.java
java ParallelSplitProcessMergeDemo
~~~

**Stdout chính xác:**

~~~text
manual rejoin = [1, 2, 3, 4, 5, 6, 7, 8]
sum = 36
sumSquares = 204
tens = [10, 20, 30, 40, 50, 60, 70, 80]
custom list = [1, 2, 3, 4, 5, 6, 7, 8]
even = 4, odd = 4
~~~

### Vì sao output không phụ thuộc lịch xử lý?

- `manual rejoin` tách một Spliterator ordered; phần tách được là prefix. Chương trình ghép prefix rồi phần còn lại nên giữ nguyên thứ tự. Nếu không tách được, danh sách vẫn được tái tạo đầy đủ.
- `sum` và `sumSquares` sử dụng phép cộng số nguyên với các giá trị nhỏ, không có tràn số; kết quả không phụ thuộc cách chia nhánh.
- `tens` giữ encounter order vì nguồn là ordered List, phép `map` không thay đổi thứ tự và `Collectors.toList` thu thập theo encounter order.
- `custom list` có combiner giữ thứ tự trái → phải và không khai báo `UNORDERED`.
- `partitioningBy` tạo cả hai nhánh `true` và `false`; đếm bốn số chẵn và bốn số lẻ. Chương trình truy cập theo khóa, không in toàn bộ Map theo thứ tự không được cam kết.
- Chương trình không in tên thread hoặc thứ tự sự kiện bên trong `forEach`, vì những thứ đó không có stdout cố định.

## 8. Encounter order và những phép tính cản trở song song

Một Stream có thể là **ordered** hoặc **unordered**, tùy nguồn và thao tác pipeline. `List` và array tạo nguồn có encounter order; `HashSet` không bảo đảm một encounter order có ý nghĩa nghiệp vụ. `sorted()` áp đặt thứ tự sắp xếp; `unordered()` cho phép bỏ ràng buộc thứ tự nếu bài toán không cần.

| Thao tác | Điều cần nhớ khi chạy parallel |
| --- | --- |
| `map`, `filter` | Thường phù hợp với phân hoạch nếu callback thuần, stateless và non-interfering. |
| `sum`, `count` | Có thể tổng hợp từ các phần; tránh dựa vào side effect trong lambda upstream. |
| `reduce` | Combiner phải có identity/associativity/compatibility đúng. |
| `collect(toList())` | Với ordered stream, kết quả giữ encounter order dù xử lý phân nhánh. |
| `distinct()` | Với ordered stream, phải giữ bản sao đầu tiên theo encounter order; có thể cần đồng bộ/buffering tốn kém. |
| `sorted()` | Phải thu thập/sắp xếp trên phạm vi đầu ra thích hợp, có thể tốn bộ nhớ và xử lý lại. |
| `limit(n)`, `skip(n)` | Với ordered parallel stream, phải xác định phần tử đúng vị trí, có thể làm giảm hiệu quả chia việc. |
| `findFirst()` | Phải tôn trọng encounter order khi có; có thể giới hạn tối ưu song song. |
| `findAny()` | Được phép chọn phần tử bất kỳ, vì vậy kết quả có thể không ổn định trên parallel stream. |
| `forEach()` | Không cam kết thứ tự thực hiện action. |
| `forEachOrdered()` | Thực hiện action theo encounter order trên ordered stream; có thể đánh đổi hiệu năng. |

**Không tự ý thêm `unordered()`** nếu kết quả đòi giữ thứ tự đầu vào, ví dụ dựng giao diện, xuất dữ liệu tuần tự hoặc chọn “bản ghi xuất hiện đầu tiên”. Ngược lại, nếu chỉ cần tập hợp duy nhất không thứ tự, bỏ ràng buộc ordering có thể giúp framework tối ưu trong một số trường hợp.

### 8.1. Một lỗi hiểu sai thường gặp về forEachOrdered

~~~java
numbers.parallelStream()
        .map(n -> expensiveTransform(n))
        .forEachOrdered(System.out::println);
~~~

Đây là **mã minh họa**, giả định có `expensiveTransform` thuần. `forEachOrdered` bảo đảm **thứ tự action in** với nguồn ordered; không có nghĩa các lần gọi `expensiveTransform` đều xảy ra theo thứ tự đó hoặc trên một thread duy nhất.

### 8.2. Tránh phỏng đoán theo Map/Set

Khi collect về `Set` hoặc `Map` không có cam kết ordering, không dựa vào `toString()` của kết quả để suy luận lịch gộp. Hãy kiểm thử nội dung bằng các phép toán tập hợp hoặc theo khóa thay vì kiểm tra thứ tự in vô tình quan sát được.

## 9. Những sai lầm thực tế

### Lỗi 1 — Cho rằng parallel luôn tốt hơn sequential

Với dữ liệu ít, callback rẻ, nguồn khó tách hoặc combiner tốn kém, overhead của fork/join, cấp phát container và đồng bộ có thể lớn hơn lợi ích. Hãy bắt đầu từ pipeline rõ nghĩa rồi benchmark với dữ liệu đại diện.

### Lỗi 2 — Chia nguồn không cân bằng rồi kỳ vọng mở rộng tuyến tính

`Spliterator.trySplit()` có thể tách không đều hoặc không tách được. Một tác vụ nhận phần lớn dữ liệu sẽ thành nút nghẽn. Khi tự cung cấp nguồn Stream/Spliterator, chi phí `trySplit()` và độ cân bằng của các phần là yếu tố quan trọng.

### Lỗi 3 — Dùng accumulator có shared mutable state

~~~java
List<Integer> output = new ArrayList<>();
numbers.parallelStream().forEach(output::add); // SAI
~~~

Không để nhiều thread cùng ghi một `ArrayList` bên ngoài pipeline. Thay bằng `collect(Collectors.toList())`, `toArray()` hoặc một reduction đúng hợp đồng.

### Lỗi 4 — Combiner bỏ dữ liệu hoặc gộp sai thứ tự

~~~java
// SAI: bỏ hết kết quả từ right.
(left, right) -> left
~~~

Hoặc ghép `right` trước `left` khi yêu cầu duy trì encounter order cũng có thể làm danh sách đầu ra sai. Trong parallel stream, combiner không phải callback “hiếm khi dùng”; nó là phần thiết yếu của phép gộp.

### Lỗi 5 — Phép gộp không kết hợp

`reduce(0, (a,b) -> a-b)` không phù hợp với parallel reduction dựa trên phép trừ. Dùng phép tổng hợp kết hợp được hoặc chuyển sang thuật toán cần tính tuần tự có chủ đích.

### Lỗi 6 — Identity có giá trị không trung hòa

~~~java
// SAI nếu mục tiêu là tổng các số + 100 đúng một lần:
int x = numbers.parallelStream().reduce(100, Integer::sum);
// Sửa: total = numbers.parallelStream().reduce(0, Integer::sum) + 100;
~~~

Identity có thể được áp dụng ở nhiều nhánh. Nó phải là phần tử đơn vị thực sự của phép kết hợp.

### Lỗi 7 — Kết luận số thread bằng số phần tử

Parallelism không phải mô hình “một phần tử = một thread”, cũng không cam kết độ lớn common pool hay lịch worker cụ thể. Các implementation JDK thường sử dụng cơ chế fork/join (thường `ForkJoinPool.commonPool()`) cho parallel stream, nhưng không nên viết ứng dụng phụ thuộc tên hoặc số worker của một lần chạy.

### Lỗi 8 — Dùng blocking I/O trong common parallel stream không tính tài nguyên

Parallel stream thuận tiện cho công việc CPU-bound có thể chia độc lập, không phải công cụ mặc định cho hàng nghìn kết nối chờ network/DB. Các tác vụ blocking có thể giữ worker và tác động đến công việc khác dùng chung pool. Với I/O, cân nhắc API đồng thời hoặc giới hạn concurrency phù hợp; nếu có yêu cầu cụ thể về executor/pool, chọn cơ chế điều phối phù hợp thay vì dựa vào hành vi thread không được cam kết của Stream.

### Lỗi 9 — Sửa nguồn khi đang duyệt

Không `add`/`remove` trên nguồn `ArrayList` trong lúc pipeline xử lý từ nguồn đó. Điều này vi phạm non-interference và có thể gây `ConcurrentModificationException` hoặc kết quả bất thường. Khóa hoặc snapshot nguồn theo thiết kế ứng dụng nếu cần thay đổi dữ liệu đồng thời.

### Lỗi 10 — Giả định mọi phép gộp cho kết quả bit-for-bit giống nhau

Tổng `double` có thể sai khác do thứ tự làm tròn; `Map`/`Set` không có ordering mặc định; `findAny` có thể trả giá trị khác nhau. Kiểm thử theo **hợp đồng kết quả**, không theo chi tiết tình cờ của lần chạy.

### Lỗi 11 — Tạo side effect trong map/peek và trông chờ chắc chắn được gọi

Stream được phép bỏ những thao tác không ảnh hưởng terminal result khi có thể chứng minh điều đó. `peek` phù hợp hỗ trợ debug hơn là thực hiện nghiệp vụ bắt buộc. Nếu cần ghi dữ liệu ngoài, không dùng callback upstream như một cơ chế đảm bảo side effect đúng một lần.

### Lỗi 12 — Cho rằng chạy collect xong thì kết quả luôn thread-safe

Một collector có thể xử lý song song đúng nhờ nhiều container cục bộ, nhưng List/Map **trả về** không nhất thiết an toàn để nhiều thread sửa đồng thời sau đó. Thread safety của quá trình reduction và thread safety của object cuối là hai vấn đề khác nhau.

## 10. Khi nào nên dùng parallel stream?

Phù hợp hơn khi:

1. **Nguồn đủ lớn và tách hiệu quả**, chẳng hạn mảng, `ArrayList`, `IntStream.range(...)`.
2. **Mỗi phần tử xử lý tương đối đáng kể**, độc lập và CPU-bound.
3. **Không có tác dụng phụ chia sẻ**, callback stateless, non-interfering.
4. **Terminal reduction/collector có phép gộp hợp lệ** và chi phí combine hợp lý.
5. **Yêu cầu ordering không quá tốn kém** hoặc không cần ordering.
6. **Môi trường có tài nguyên CPU phù hợp**, không bị cạnh tranh nặng với các workload khác.

Cần cân nhắc hoặc tránh khi:

- Nguồn quá nhỏ, pipeline rất rẻ.
- Tác vụ phụ thuộc dữ liệu phần tử trước, cần tuần tự.
- Có nhiều I/O blocking, locking hay chỉnh sửa state chia sẻ.
- Cần toàn bộ output theo một thứ tự nghiêm ngặt với các phép stateful tốn kém.
- Combiner trên cấu trúc lớn tốn chi phí gần bằng hoặc lớn hơn công việc chính.

**Cách đánh giá hợp lý:** xác nhận kết quả đúng với sequential/parallel, kiểm thử dữ liệu rỗng và biên, chạy benchmark có warm-up và đại diện cho khối lượng production. Có thể dùng JMH để đo cẩn thận. Không kết luận tăng tốc từ một lần đo `System.currentTimeMillis()`, cũng không giả định số core tăng gấp đôi thì thời gian giảm một nửa.

## 11. Bài tập thực hành và đáp án

**Bài 1.** Tại sao `IntStream.rangeClosed(1, 100).parallel().sum()` có thể cho kết quả đúng mà không biết số phần được chia?

**Đáp án:** Vì phép cộng có identity `0` và kết hợp được; các nhóm được tính tổng rồi gộp bằng phép cộng. Kết quả là `5050` dù cấu trúc cây chia/gộp khác nhau.

**Bài 2.** `trySplit()` trên Spliterator `ORDERED` trả về gì? Nó có chắc chia đôi bằng nhau không?

**Đáp án:** Nếu tách thành công, Spliterator mới bao phủ một **prefix** phần tử; đối tượng gốc giữ phần còn lại. Không có bảo đảm chia đôi chính xác và có thể trả `null`.

**Bài 3.** Vì sao `parallelStream().forEach(sharedArrayList::add)` không an toàn trong khi `parallelStream().collect(toList())` là cách gom hợp lệ?

**Đáp án:** `forEach` trên List chung gây cập nhật đồng thời không đồng bộ; `collect` quản lý tích lũy và kết hợp theo hợp đồng Collector, không yêu cầu caller tự chia sẻ một List mutable.

**Bài 4.** Với nguồn ordered `[1,2,3,4]`, `parallelStream().map(n -> n*2).collect(toList())` trả gì?

**Đáp án:** `[2,4,6,8]`. Thứ tự callback xử lý có thể khác, nhưng kết quả của phép collect phải phù hợp encounter order.

**Bài 5.** Một collector có accumulator `List::add` trên `ArrayList` và combiner `(left,right) -> left`. Tại sao sai?

**Đáp án:** Khi parallel có nhiều container, combiner làm mất toàn bộ phần tử của `right`; không thỏa hợp đồng reduction.

**Bài 6.** Tại sao `reduce(100,Integer::sum)` không phải cách chắc chắn thêm 100 đúng một lần vào tổng?

**Đáp án:** `100` không là identity cho phép cộng và có thể được dùng khởi tạo nhiều phần. Phải dùng `reduce(0,Integer::sum) + 100`.

**Bài 7.** Khi nào `groupingByConcurrent` hữu ích và phải đánh đổi điều gì?

**Đáp án:** Khi cần gom theo khóa và phép tích lũy đồng thời có thể giảm chi phí merge Map; nhưng collector concurrent/unordered không cam kết giữ encounter order của các phần tử trong từng nhóm.

**Bài 8.** Có nên đánh giá hiệu năng parallel bằng việc in tên thread cho từng phần tử?

**Đáp án:** Không. In console tạo side effect, đồng bộ và thay đổi chi phí workload; tên/số thread không thể hiện tốc độ thực và không phải hợp đồng. Hãy kiểm tra kết quả và benchmark với workload đại diện.

## 12. Tóm tắt cần nhớ

- **Chia nguồn:** `Spliterator.trySplit()` có thể chia nguồn thành các phần; không cam kết số lượng phần hay kích thước cân bằng. Với nguồn `ORDERED`, phần tách được là prefix.
- **Xử lý:** các pipeline operation chạy trên những phần dữ liệu bằng các tác vụ do framework quản lý; callback nên **stateless** và **non-interfering**.
- **Gộp:** `reduce` và `collect` cần đúng **identity**, **associativity** và **combiner compatibility**; không thể suy luận từ việc chạy đúng trên sequential.
- **Ordering:** xử lý thực tế có thể không theo thứ tự thời gian ban đầu nhưng đầu ra của các phép có hợp đồng giữ encounter order vẫn phải giữ. Không suy ra thứ tự `forEach` hay thứ tự Map/Set không bảo đảm.
- **Mutable collection:** dùng `collect` thay vì cùng sửa một container ngoài trong `forEach`; không gắn `CONCURRENT` cho accumulator không thread-safe.
- **Hiệu năng:** parallel không tự động nhanh hơn. Chọn nguồn dễ split, phép xử lý độc lập và gộp rẻ; đo với dữ liệu thật.
- Các cơ chế `parallel()`, `Spliterator`, `reduce`, `collect` này đều có từ **Java 8** và vẫn áp dụng ở Java hiện hành.

### Tài liệu chính thức

- [Oracle Java SE 8 — package java.util.stream: parallelism, reduction và ordering](https://docs.oracle.com/javase/8/docs/api/java/util/stream/package-summary.html)
- [Oracle Java SE 25 — java.util.stream: parallelism, reduction, concurrency, ordering](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html)
- [Oracle Java SE 25 — Spliterator: trySplit, SIZED và SUBSIZED](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Spliterator.html)
- [Oracle Java SE 25 — Stream: reduce, collect, forEachOrdered](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html)
- [Oracle Java SE 25 — Collector: supplier, accumulator, combiner và finisher](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collector.html)
