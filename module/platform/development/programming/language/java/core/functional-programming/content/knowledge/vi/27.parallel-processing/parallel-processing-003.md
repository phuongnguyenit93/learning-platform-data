# Chia nguồn, xử lý từng phần và gộp kết quả trong Java Parallel Stream

## 1. Tư duy chia để trị trong Stream song song

Một pipeline xử lý song song có thể chia nguồn thành các **phần việc** (*partitions/tasks*), xử lý mỗi phần rồi kết hợp các **kết quả cục bộ** để tạo ra kết quả cuối. Đây là tư tưởng *divide and conquer*, nhưng ứng dụng không cần tự tạo một luồng Java cho từng phần tử.

Mô hình khái niệm:

```text
                         Nguồn [1,2,3,4,5,6,7,8]
                                     |
                                chia nguồn
                          /                       \
               [1,2,3,4]                         [5,6,7,8]
                 /    \                             /    \
              [1,2] [3,4]                       [5,6] [7,8]
                |     |                           |     |
             subtotal subtotal                 subtotal subtotal
                \     /                           \     /
               kết hợp                           kết hợp
                  \                                /
                   -------- gộp cuối -------------
                               |
                             kết quả
```

Khi các phần là phép cộng, tổng là `36`. Điều quan trọng không phải mỗi phần được phân công cho *thread nào*, mà là phép biến đổi và cách gộp phải **giữ nguyên ý nghĩa kết quả** dù framework phân chia thành nhiều phần khác nhau.

Trong Java, hai cách đơn giản để yêu cầu pipeline song song:

```java
numbers.parallelStream()
       .mapToInt(Integer::intValue)
       .sum();
```

hoặc:

```java
numbers.stream()
       .parallel()
       .mapToInt(Integer::intValue)
       .sum();
```

Đây là những biểu thức minh họa trong phương thức có biến `numbers: List<Integer>`, import `List`. Cả hai thiết lập chế độ parallel cho pipeline, nhưng **không buộc framework sử dụng số lượng thread cố định hoặc một cách chia cố định**.

Parallel stream hướng đến giải quyết bài toán xử lý dữ liệu, không phải một cách tự động biến mọi thuật toán tuần tự thành nhanh và đúng trong môi trường nhiều luồng.

## 2. Từ nguồn đến kết quả: bốn giai đoạn

Có thể hiểu một phép tổng hợp song song qua bốn bước:

1. **Phân rã nguồn:** framework nhận một nguồn có khả năng duyệt/chia (thường thông qua `Spliterator`) và tạo các công việc con khi thích hợp.
2. **Xử lý từng phần:** mỗi tác vụ thực thi phần pipeline tương ứng (ví dụ `filter`, `map`, `mapToInt`) trên các phần tử được giao.
3. **Tích lũy cục bộ:** mỗi phần có thể tạo một subtotal (`reduce`) hoặc một container tạm (`collect`), tùy thuật toán.
4. **Kết hợp:** các subtotal/container cục bộ được gộp thành kết quả chung theo quy tắc combiner phù hợp.

Lưu ý: đây là **mô hình tư duy**, không phải cam kết rằng mọi terminal operation đều phải thực hiện đúng bốn bước với số tác vụ, số container và thứ tự cố định. Tối ưu hóa, kích thước nguồn, thao tác có trạng thái, phép kết thúc sớm hoặc cấu trúc collector có thể làm quá trình thực thi khác nhau.

Ví dụ `stream.parallel().count()` có thể dùng đặc trưng kích thước nguồn để tính kết quả mà không xử lý từng phần tử. Do đó không dùng side effect trong `peek`/`map` để kiểm đếm “đã chạy bao nhiêu task”.

## 3. Spliterator: cơ chế phân chia nguồn

`java.util.Spliterator<T>` kết hợp khả năng **duyệt phần tử** và **tách phần việc**. Một số phương thức cần biết:

| API | Ý nghĩa |
| --- | --- |
| `tryAdvance(Consumer<? super T>)` | Nếu còn phần tử thì xử lý một phần tử |
| `forEachRemaining(Consumer<? super T>)` | Duyệt các phần tử còn lại |
| `trySplit()` | Cố tách một phần để xử lý độc lập; có thể trả `null` |
| `estimateSize()` | Ước lượng số phần tử còn lại |
| `characteristics()` | Trả tập cờ đặc tính, ví dụ `ORDERED`, `SIZED`, `SUBSIZED` |

Thông thường Stream lấy spliterator từ `Collection`, mảng hoặc nguồn được cung cấp. Những nguồn dễ tách và đã biết kích thước (như `ArrayList`, mảng, dãy số) thường thuận lợi hơn nguồn tuần tự không thể chia hiệu quả.

**`trySplit()` không có hợp đồng luôn chia thành hai nửa bằng nhau.** Nhiều implementation trả phần *prefix* khi có encounter order và để lại phần *remainder*, nhưng độ lớn từng phần, số lần chia và điều kiện trả `null` do spliterator quyết định.

Phân biệt:

- `ORDERED`: có thứ tự gặp phần tử cần được tôn trọng ở những operation yêu cầu.
- `SIZED`: biết chính xác số phần tử còn lại theo hợp đồng nguồn.
- `SUBSIZED`: các spliterator sau khi tách cũng có thuộc tính `SIZED`.
- `SORTED` hoặc `DISTINCT`: đặc tính giá trị/nguồn mà một số operation có thể tận dụng.

Những cờ này **không phải nút bật song song**, mà cung cấp thông tin để framework quyết định cách xử lý và tối ưu.

## 4. Ví dụ chia nguồn bằng trySplit() và xem hai phần

Một ví dụ trực quan đặt trong phương thức:

```java
List<Integer> values = IntStream.rangeClosed(1, 8).boxed().toList();
Spliterator<Integer> remainder = values.spliterator();
Spliterator<Integer> prefix = remainder.trySplit();

List<Integer> firstPart = StreamSupport.stream(prefix, false).toList();
List<Integer> secondPart = StreamSupport.stream(remainder, false).toList();
```

Đoạn minh họa cần import `java.util.*`, `java.util.stream.*`. Với nguồn List cụ thể này trong môi trường Java 17 kiểm thử, `prefix` là `[1, 2, 3, 4]`, `remainder` là `[5, 6, 7, 8]`.

**Đây là kết quả quan sát của ví dụ, không phải quy tắc mọi `Spliterator` đều phải chia 4/4.** Khi gọi `trySplit()` trên nguồn quá nhỏ hoặc loại nguồn khác, kết quả có thể là `null`. Mã sản xuất dùng `trySplit` trực tiếp phải kiểm tra null; ví dụ đầy đủ biết trước nguồn List có 8 phần tử và đã được kiểm thử trên JDK 17.

Để thực thi một phần từ spliterator bằng Stream API, có thể dùng `StreamSupport.stream(part, false)`. Lệnh này **tiêu thụ spliterator** được cung cấp; không sử dụng lại đối tượng ấy sau khi đã được duyệt.

Thông thường bạn **không cần gọi `trySplit` thủ công**: `parallelStream()` kết hợp Stream framework với spliterator nguồn để quyết định phân chia.

## 5. Fork/Join và số lượng tác vụ không cố định

Stream song song trong Java thông thường được triển khai bằng các cơ chế của **Fork/Join** (thường liên quan `ForkJoinPool.commonPool()`). Một công việc có thể tách thành những công việc nhỏ hơn (*fork*), và kết quả được kết hợp khi hoàn tất (*join*).

Nhưng khi viết:

```java
int total = IntStream.rangeClosed(1, 100).parallel().sum();
```

điều ta có thể dựa vào là **ngữ nghĩa phép tổng hợp** với dữ liệu nhỏ này, chứ không phải “100 phần tử chạy trên 100 threads”. Framework có thể không tạo tác vụ cho từng phần tử, và tác vụ cũng không nhất thiết chạy đồng thời.

Tính song song phụ thuộc khả năng chia nguồn, số lượng và độ nặng của thao tác, số core/tài nguyên, chi phí tạo/ghép công việc và các ràng buộc về thứ tự. Cũng có thể một pipeline khai báo parallel nhưng lợi ích không đáng kể vì nguồn nhỏ hoặc một công đoạn phải chờ nhau.

**Không đoán thứ tự xuất log hoặc số thread** từ một lần chạy: scheduler và môi trường có thể thay đổi. Tránh đặt hành động nghiệp vụ phụ thuộc vào thread name, thứ tự task kết thúc hay số lần gọi combiner.

## 6. Gộp giá trị bằng reduce(identity, accumulator, combiner)

Phương thức gộp ba tham số của `Stream<T>` có chữ ký khái niệm:

```java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner);
```

Đây là chữ ký API để đọc generic, không phải một lớp Java độc lập.

Ý nghĩa:

- **`identity`**: giá trị đơn vị hoặc trạng thái khởi đầu phù hợp cho mỗi phần xử lý. Với phép cộng: `0`.
- **`accumulator`**: tiếp nhận subtotal kiểu `U` và một phần tử kiểu `T`, tạo subtotal mới kiểu `U`.
- **`combiner`**: gộp hai subtotal `U` từ những phần khác nhau.

Ví dụ với `List<Integer>`:

```java
long sum = numbers.parallelStream()
        .reduce(0L,
                (subtotal, number) -> subtotal + number,
                Long::sum);
```

Các lệnh minh họa cần biến `numbers: List<Integer>`. `identity` có kiểu `Long` qua boxing, accumulator chuyển phần tử `Integer` thành subtotal `Long` bằng phép cộng, combiner cộng hai subtotal `Long`.

Nếu các phần nguồn có tổng `10` và `26`, combiner `Long::sum` cho `36`. Với dữ liệu `[1,2,3,4,5,6,7,8]`, chương trình kiểm thử trả `36`.

Về mặt hợp đồng, phép giảm song song yêu cầu các hàm gộp **kết hợp được** (*associative*), identity đúng, và `combiner` **tương thích** với `accumulator`. Không phải cứ thêm đối số combiner là mọi lambda đều xử lý song song an toàn.

## 7. Vì sao tính kết hợp (associativity) là điều kiện quyết định?

Phép toán `op` kết hợp khi:

```text
op(op(a,b),c) == op(a,op(b,c))
```

Cộng số nguyên trong miền không tràn thường phù hợp; `max`, `min`, phép kết hợp tập hợp hoặc nối list theo đúng thứ tự cũng thường có thể xây dựng để kết hợp.

**Phép trừ không kết hợp:**

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Vì kết quả khác nhau, dùng kiểu `reduce(0,(a,b)->a-b)` rồi trông đợi kết quả y hệt trên mọi cách chia công việc là sai thiết kế.

Thực tế parallel reduction có thể nhóm các phần theo một cây gộp khác với xử lý từ trái sang phải. Ngay cả khi một lần chạy in ra kết quả “đúng”, điều đó không chứng minh reducer an toàn về ngữ nghĩa.

**Tính kết hợp khác với tính giao hoán** (*commutativity*). Phép nối chuỗi có thể kết hợp nhưng không giao hoán: `"A"+"B"` khác `"B"+"A"`. Nếu đầu ra cần encounter order, phải chọn API/collector có hợp đồng giữ thứ tự phù hợp; không suy diễn phép ghép chuỗi an toàn với mọi unordered hoặc concurrent collector.

**Số thực `double`:** phép cộng số thực có làm tròn, nên không kết hợp chính xác theo biểu diễn; parallel sum có thể cho chênh lệch chữ số thấp do thứ tự nhóm. Nếu cần tiền tệ/số chính xác, xem xét `BigDecimal`, kiểu số chính xác và thuật toán phù hợp.

## 8. Identity và quy tắc tương thích accumulator/combiner

`identity` không đơn thuần là “giá trị tùy thích để bắt đầu”. Với phép cộng, `0` là identity vì `0 + x = x`. Với phép nhân, `1` là identity vì `1 * x = x`.

Đoạn **sai về ngữ nghĩa**:

```java
int wrong = IntStream.of(1, 2, 3)
        .parallel()
        .reduce(10, Integer::sum);
```

Câu lệnh biên dịch được nếu nằm trong phương thức có import `IntStream`; nhưng `10` **không phải identity cho phép cộng**, vì `10 + x != x`. Các phần nguồn có thể bắt đầu từ identity riêng và gộp lại, vì thế kết quả có thể khác trực giác “tổng một lần cộng 10”. Đúng khi tính tổng là `reduce(0, Integer::sum)` hoặc `sum()`.

Với overload ba tham số, Javadoc còn yêu cầu **compatibility** giữa accumulator và combiner, theo dạng:

```text
combiner(u, accumulator(identity, t)) == accumulator(u, t)
```

trên dữ liệu hợp lệ theo hợp đồng; điều này cho phép gộp kết quả mỗi phần mà không thay đổi phép tính chung.

Ví dụ hợp lệ: `identity=0L`, `accumulator=(subtotal,n)->subtotal+n`, `combiner=Long::sum`. Tất cả mô tả cùng một phép cộng.

Ví dụ sai: accumulator cộng điểm nhưng combiner lại **nhân** hai subtotal; kết quả không tương thích và phụ thuộc số lượng phần được chia. Không có exception tự động báo “combiner sai ngữ nghĩa”; code có thể chạy nhưng ra dữ liệu sai.

## 9. reduce() khác collect() ở đâu?

`reduce` thích hợp khi kết quả là một **giá trị** có phép kết hợp phù hợp, ví dụ tổng, tích, min/max, `BigInteger`, một summary type bất biến được thiết kế tốt.

`collect` thích hợp khi kết quả là **container có thể thay đổi** trong quá trình tích lũy, ví dụ `List`, `Set`, `Map`, `StringBuilder`, các bộ thống kê có hàm tích lũy.

| Chủ đề | reduce() | collect() |
| --- | --- | --- |
| Kết quả thường gặp | Giá trị tổng hợp, subtotal mới | Container được bổ sung phần tử |
| Tích lũy | Trả về giá trị U mới | Thường mutate **container cục bộ** |
| Gộp phần | `combiner(U,U) -> U` | Kết hợp các container cục bộ |
| Mẫu điển hình | `reduce(0,Integer::sum)` | `collect(Collectors.toList())`, `groupingBy` |
| Cạm bẫy | Identity/associativity sai | Mutable state dùng chung hoặc combiner sai |

**Không dùng `reduce` với identity là một `ArrayList` mutable rồi mutate nó ngay trong accumulator**. Identity của reduction có thể được chia sẻ ở nhiều nhánh tính toán; thao tác đó vi phạm mô hình reduce không can thiệp và có thể dẫn đến race, mất hoặc nhân đôi dữ liệu.

Muốn tạo danh sách trong parallel stream, hãy dùng `toList()` hoặc một `Collector` được thiết kế đúng.

## 10. Collector: supplier, accumulator, combiner, finisher

Một `Collector<T,A,R>` mô tả cách biến phần tử kiểu `T` thành kết quả `R` thông qua container tích lũy kiểu `A`:

- **supplier**: tạo container rỗng mới cho phần được xử lý.
- **accumulator**: thêm một phần tử `T` vào container `A` của phần đó.
- **combiner**: gộp **hai container `A`** thành một; quan trọng khi có nhiều phần cục bộ.
- **finisher** (nếu có): chuyển trạng thái tạm `A` thành kết quả `R`.
- **characteristics**: khai báo đặc tính như `CONCURRENT`, `UNORDERED`, `IDENTITY_FINISH`, nếu thực sự đúng theo hợp đồng.

Đồ hình đơn giản:

```text
Nhánh 1: supplier() -> [] -> accumulate("A") -> ["A"]
                               accumulate("B") -> ["A","B"]

Nhánh 2: supplier() -> [] -> accumulate("C") -> ["C"]
                               accumulate("D") -> ["C","D"]

combiner(["A","B"], ["C","D"]) -> ["A","B","C","D"]
finisher(...) (nếu có) -> kết quả mong muốn
```

Đây là **mô tả khái niệm**, không phải lời hứa framework sẽ chia đúng hai phần hoặc gọi combiner chỉ một lần.

Điểm mấu chốt của collector thông thường là **mỗi container cục bộ thuộc một luồng tích lũy riêng**, vì vậy bên trong accumulator có thể thêm phần tử vào `ArrayList` riêng mà không phải để nhiều task đồng thời sửa cùng một list.

## 11. Viết custom Collector cho List

Đoạn phương thức minh họa (dùng trong lớp với import `java.util.*`, `java.util.stream.*`):

```java
static Collector<String, ArrayList<String>, ArrayList<String>> listCollector() {
    return Collector.of(
            ArrayList::new,
            ArrayList::add,
            (left, right) -> {
                left.addAll(right);
                return left;
            });
}
```

Ở đây `ArrayList::new` là **supplier**, `ArrayList::add` là **accumulator**, lambda gộp hai list là **combiner**.

Mặc dù `ArrayList` không thread-safe cho việc ghi đồng thời vào **cùng một instance**, collector này có thể dùng đúng trong parallel stream vì framework quản lý các container cục bộ và kết hợp theo hợp đồng của collector **không concurrent**. Nó **không** chia sẻ một đối tượng `ArrayList` đã tạo từ trước cho mọi nhánh.

```java
List<String> words = List.of("A", "B", "C", "D");
List<String> output = words.parallelStream().collect(listCollector());
```

Khi collector không khai báo `UNORDERED` và đầu vào có encounter order, kết quả của phép thu thập giữ thứ tự theo hợp đồng. Trong ví dụ Java 17 đã thử, `output = [A, B, C, D]`.

Không nên “tối ưu” supplier thành `() -> sharedList` với `sharedList` là biến dùng chung; làm như vậy phá mô hình tích lũy cục bộ và tạo rủi ro race.

## 12. Custom Collector có finisher: ghép chuỗi CSV

Nếu container tạm là `StringBuilder` nhưng giá trị cuối muốn nhận là `String`, dùng `Collector.of` có finisher:

```java
static Collector<String, StringBuilder, String> csvCollector() {
    return Collector.of(
            StringBuilder::new,
            (builder, value) -> {
                if (builder.length() > 0) builder.append(",");
                builder.append(value);
            },
            (left, right) -> {
                if (left.length() > 0 && right.length() > 0) {
                    left.append(",");
                }
                left.append(right);
                return left;
            },
            StringBuilder::toString);
}
```

Đây là một phương thức nằm trong ví dụ Java hoàn chỉnh ở mục 14.

Cần hiểu hai dấu phẩy:

- **accumulator** chỉ thêm dấu phẩy khi container hiện tại đã có dữ liệu;
- **combiner** chỉ thêm dấu phẩy khi **cả hai** phần đều không rỗng, rồi nối phần phải vào phần trái.

Với `["A","B","C","D"]`, kết quả là `A,B,C,D` theo encounter order. Phần gộp được thiết kế để việc chia thành 1, 2 hay nhiều nhánh không tự tạo dấu phẩy thừa, miễn là framework giữ thứ tự của các phần theo hợp đồng collector có thứ tự.

`StringBuilder` **không thread-safe** khi hai thread đồng thời sửa cùng instance. Nhưng điều đó không cấm dùng nó làm **container cục bộ** trong collector không concurrent. Nếu bạn cố đánh dấu `CONCURRENT` không đúng, lập luận an toàn này không còn hiệu lực.

## 13. Ví dụ Java 17 chạy độc lập: Spliterator và reduce/collect

Tạo tệp `ParallelSplitReduceDemo.java` với toàn bộ nội dung:

```java
import java.util.*;
import java.util.stream.*;

public class ParallelSplitReduceDemo {
    public static void main(String[] args) {
        List<Integer> data = IntStream.rangeClosed(1, 8).boxed().toList();

        Spliterator<Integer> remainder = data.spliterator();
        Spliterator<Integer> prefix = remainder.trySplit();
        List<Integer> left = StreamSupport.stream(prefix, false).toList();
        List<Integer> right = StreamSupport.stream(remainder, false).toList();
        System.out.println("prefix=" + left);
        System.out.println("remainder=" + right);
        System.out.println("covered=" + (left.size() + right.size()));

        int sequential = data.stream().mapToInt(Integer::intValue).sum();
        int parallel = data.parallelStream().mapToInt(Integer::intValue).sum();
        System.out.println("sequentialSum=" + sequential);
        System.out.println("parallelSum=" + parallel);

        long parallelThreeArg = data.parallelStream()
                .reduce(0L, (subtotal, n) -> subtotal + n, Long::sum);
        System.out.println("parallelThreeArg=" + parallelThreeArg);

        int sumSquares = data.parallelStream()
                .map(n -> n * n)
                .reduce(0, Integer::sum);
        System.out.println("sumSquares=" + sumSquares);

        Map<String, Integer> grouped = data.parallelStream()
                .collect(Collectors.groupingBy(
                        n -> n % 2 == 0 ? "even" : "odd",
                        TreeMap::new, Collectors.summingInt(Integer::intValue)));
        System.out.println("grouped=" + grouped);

        IntSummaryStatistics stats = data.parallelStream()
                .collect(Collectors.summarizingInt(Integer::intValue));
        System.out.println("stats=" + stats.getCount()
                + "/" + stats.getSum()
                + "/" + stats.getMin()
                + "/" + stats.getMax());

        List<Integer> transformed = data.parallelStream()
                .map(n -> n * 10).toList();
        System.out.println("orderedResult=" + transformed);

        List<Integer> observed = Collections.synchronizedList(new ArrayList<>());
        data.parallelStream().forEachOrdered(observed::add);
        System.out.println("orderedAction=" + observed);

        System.out.println("associative=" +
                ((10 - 3) - 2) + "/" + (10 - (3 - 2)));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 ParallelSplitReduceDemo.java
java ParallelSplitReduceDemo
```

Đầu ra đã kiểm chứng trong môi trường Java 17:

```text
prefix=[1, 2, 3, 4]
remainder=[5, 6, 7, 8]
covered=8
sequentialSum=36
parallelSum=36
parallelThreeArg=36
sumSquares=204
grouped={even=20, odd=16}
stats=8/36/1/8
orderedResult=[10, 20, 30, 40, 50, 60, 70, 80]
orderedAction=[1, 2, 3, 4, 5, 6, 7, 8]
associative=5/9
```

Giải thích:

1. `Spliterator.trySplit()` trong ví dụ cho prefix và remainder, tổng số phần tử là `8`. Kích thước chia **không phải lời hứa cho mọi nguồn**.
2. `sequentialSum` và `parallelSum` cùng bằng `36`, đúng với dữ liệu nhỏ và phép cộng nguyên không tràn.
3. `parallelThreeArg=36` xác nhận reduction ba tham số với `identity=0L`, accumulator cộng vào long, combiner `Long::sum`.
4. `sumSquares=204` xác nhận xử lý từng phần `n*n` rồi gộp bằng tổng.
5. `grouped={even=20, odd=16}` là **tổng** các giá trị chẵn/lẻ, không phải số lượng các phần tử.
6. `stats=8/36/1/8` tương ứng `count/sum/min/max`.
7. `orderedResult` và `orderedAction` minh họa trường hợp API yêu cầu encounter order được bảo toàn. Điều đó **không có nghĩa các lambda map luôn chạy tuần tự theo thứ tự**.
8. `associative=5/9` minh họa phép trừ không kết hợp, không phải đầu ra không ổn định được đo từ một parallel reduction.

Chương trình chỉ dùng thư viện chuẩn, không cần tạo file dữ liệu hay truy cập mạng.

## 14. Ví dụ Java 17 chạy độc lập: custom Collector và gộp container

Tạo tệp `ParallelCollectorDemo.java`:

```java
import java.util.*;
import java.util.stream.*;

public class ParallelCollectorDemo {
    static Collector<String, ArrayList<String>, ArrayList<String>> listCollector() {
        return Collector.of(
                ArrayList::new,
                ArrayList::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });
    }

    static Collector<String, StringBuilder, String> csvCollector() {
        return Collector.of(
                StringBuilder::new,
                (builder, value) -> {
                    if (builder.length() > 0) builder.append(",");
                    builder.append(value);
                },
                (left, right) -> {
                    if (left.length() > 0 && right.length() > 0) {
                        left.append(",");
                    }
                    left.append(right);
                    return left;
                },
                StringBuilder::toString);
    }

    public static void main(String[] args) {
        List<String> words = List.of("A", "B", "C", "D");
        List<String> result = words.parallelStream().collect(listCollector());
        System.out.println("list=" + result);
        System.out.println("csv=" + words.parallelStream().collect(csvCollector()));

        Map<String, Long> counts = words.parallelStream()
                .collect(Collectors.groupingBy(
                        s -> (s.equals("A") || s.equals("C")) ? "odd" : "even",
                        TreeMap::new, Collectors.counting()));
        System.out.println("counts=" + counts);

        Set<String> unique = Stream.of("A", "B", "A", "C")
                .parallel()
                .collect(Collectors.toCollection(TreeSet::new));
        System.out.println("sortedSet=" + unique);

        int all = IntStream.rangeClosed(1, 100)
                .parallel().sum();
        System.out.println("sum100=" + all);
    }
}
```

Lệnh kiểm thử:

```bash
javac --release 17 -encoding UTF-8 ParallelCollectorDemo.java
java ParallelCollectorDemo
```

Đầu ra:

```text
list=[A, B, C, D]
csv=A,B,C,D
counts={even=2, odd=2}
sortedSet=[A, B, C]
sum100=5050
```

Các điểm quan trọng:

- `listCollector` dùng **supplier/accumulator/combiner** với `ArrayList` cục bộ.
- `csvCollector` thêm **finisher** để trả `String`, tránh lộ `StringBuilder` mutable ra caller.
- `groupingBy(..., TreeMap::new, counting())` minh họa nhóm theo khóa, gộp và tạo Map có khóa sắp xếp. `even=2`, `odd=2` là **số lượng phần tử** ở nhóm.
- `Collectors.toCollection(TreeSet::new)` tạo tập hợp có khóa sắp xếp, kết quả `[A, B, C]`.
- `IntStream.rangeClosed(1,100).parallel().sum()` trả `5050`; tác dụng của `parallel` là cách tính chứ không làm thay đổi tổng toán học trong miền int hợp lệ.

Không nên cố đếm số lần gọi supplier/combiner bằng side effect để coi đó là cấu trúc phân chia mặc định. Số lần gọi phụ thuộc kích thước, môi trường và chiến lược thực thi.

## 15. Thu thập kết quả với collector chuẩn

Trước khi tự viết collector, hãy kiểm tra thư viện chuẩn:

| Nhu cầu | API thường phù hợp |
| --- | --- |
| Tổng số nguyên | `mapToInt(...).sum()`, `Collectors.summingInt(...)` |
| Đếm phần tử | `count()`, `Collectors.counting()` |
| Gom thành danh sách | `toList()`, `Collectors.toList()` |
| Gom thành tập | `Collectors.toSet()`, `toCollection(TreeSet::new)` |
| Gom theo khóa | `Collectors.groupingBy(...)` |
| Gộp thành Map với khóa trùng | `Collectors.toMap(key,value,merge)` |
| Gom theo nhiều nhóm và thống kê | `groupingBy(..., downstreamCollector)` |
| Collector thực sự concurrent | Một số `toConcurrentMap`, `groupingByConcurrent` |

Nếu chỉ cần một kết quả thống kê, collector chuẩn thường ngắn hơn và ít rủi ro hơn custom collector. `groupingBy` không phải mặc định concurrent; parallel stream có thể tạo map cục bộ rồi gộp. `groupingByConcurrent` có hợp đồng khác và có thể là `UNORDERED`, vì vậy phải xét yêu cầu thứ tự.

**Không nhầm “Map có thể dùng từ nhiều thread sau khi tạo” với “collector cho phép nhiều thread cùng cập nhật một container trong lúc collect”**. Collector `CONCURRENT` có ràng buộc riêng; một mapFactory trả `ConcurrentHashMap` không tự làm collector bất kỳ trở thành concurrent đúng nghĩa.

## 16. Thứ tự gặp phần tử: song song không đồng nghĩa hỗn loạn

Nguồn `List` có encounter order. Khi gọi:

```java
List<Integer> result = numbers.parallelStream()
        .map(n -> n * 10)
        .toList();
```

`result` giữ thứ tự gặp phần tử tương ứng của nguồn cho pipeline ordered này; với `numbers = [1,2,3]` thì kết quả là `[10,20,30]`.

Nhưng **thứ tự đánh giá bên trong** `map` có thể khác thứ tự nguồn; `toList()` thu dữ liệu theo thứ tự được yêu cầu. Vì vậy không viết:

```text
List<Integer> audit = new ArrayList<>();
numbers.parallelStream().map(n -> {
    audit.add(n);
    return n * 10;
}).toList();
```

Đây là **phản ví dụ sai về thiết kế**: ghi đồng thời vào `ArrayList` dùng chung có thể gây race; ngoài ra side effect trong stage `map` không nên được dùng làm nghiệp vụ bắt buộc.

Khi thật sự muốn **thao tác terminal** theo encounter order, `forEachOrdered` có hợp đồng phù hợp:

```java
List<Integer> observed = Collections.synchronizedList(new ArrayList<>());
numbers.parallelStream().forEachOrdered(observed::add);
```

Đoạn minh họa nằm trong phương thức có import `List`, `Collections`, `ArrayList`. `forEachOrdered` áp đặt thứ tự action theo encounter order với ordered stream, nhưng có thể giảm lợi ích song song. Dùng `forEach` khi **không cần thứ tự**; không tự giả định thứ tự gọi action.

## 17. Stateful operations và giới hạn tốc độ

Không phải pipeline nào cũng phân chia/gộp hiệu quả. Những thao tác cần quan sát nhiều phần tử hoặc tôn trọng thứ tự có thể tạo rào cản:

- `sorted()`: sắp xếp thường cần giữ/đánh giá nhiều phần tử.
- `distinct()`: có thể cần tập trạng thái các phần tử đã thấy; ordered parallel có thể tốn thêm chi phí.
- `limit()`, `skip()`: với ordered parallel, việc xác định chính xác tiền tố cần giữ/bỏ có thể tốn kém.
- `takeWhile()`, `dropWhile()`: với ordered source, phải xác định đúng ranh giới tiền tố.
- `findFirst()): phải trả phần tử đầu tiên theo encounter order, có thể cần phối hợp giữa các nhánh.
- `findAny()`: khi thứ tự không cần thiết, có thể linh hoạt hơn.

Không có quy tắc “`parallel()` luôn nhanh gấp số core”. Tốc độ phụ thuộc lượng dữ liệu, chi phí xử lý từng phần tử, khả năng chia nguồn, mức độ phối hợp, độ trễ bộ nhớ, chi phí combine và môi trường chạy.

**Một số trường hợp chạy song song chậm hơn:** dữ liệu quá nhỏ; mỗi phần tử chỉ thực hiện phép cộng đơn giản; nguồn khó chia; cần `sorted` rồi `findFirst`; hoặc combiner/collector phải copy nhiều dữ liệu.

Chỉ nên kết luận hiệu năng sau khi **benchmark hợp lý** (ví dụ JMH, warm-up, dữ liệu đại diện), không lấy `System.currentTimeMillis()` của một lần chạy nhỏ làm bằng chứng.

## 18. Nguồn có thứ tự và nguồn unordered

Đôi khi có thể bỏ ràng buộc thứ tự bằng `unordered()` nếu bài toán **không cần thứ tự**. Điều này có thể giúp một số pipeline parallel dễ tối ưu hơn. Tuy nhiên `unordered()` chỉ **loại bỏ ràng buộc encounter order**, không bảo đảm xáo trộn phần tử.

Nếu kết quả phải giữ thứ tự sự kiện, chọn bản ghi đầu tiên hoặc dựng chuỗi theo đúng thứ tự, không tùy tiện gọi `unordered()`.

Với collector có đặc tính `UNORDERED`, kết quả có thể không bảo toàn encounter order dù nguồn là `List`. Ngược lại, một collector không `UNORDERED` và được viết đúng có thể gộp các phần theo cách cho ra thứ tự danh sách đúng, như ví dụ `listCollector`.

**Tính xác định của kết quả** và **thứ tự side effects** là hai việc khác nhau: kết quả `toList()` có thể đúng thứ tự dù các thread đã chạy `map` theo thứ tự khác.

## 19. Vì sao shared mutable accumulator là lỗi nghiêm trọng?

Một sai lầm phổ biến là tạo một biến mutable ở ngoài rồi cho nhiều phần xử lý cùng sửa:

```text
List<Integer> result = new ArrayList<>();
numbers.parallelStream().forEach(result::add);
```

Đây là **đoạn cảnh báo**, không phải mã được khuyến nghị. `ArrayList` không an toàn khi nhiều thread ghi đồng thời; kết quả có thể thiếu phần tử, hỏng trạng thái nội bộ hoặc có lỗi khó lặp lại.

Phương án đơn giản:

```java
List<Integer> result = numbers.parallelStream().toList();
```

Đây là lệnh trong phương thức có `numbers: List<Integer>`. Framework chịu trách nhiệm thu kết quả; bạn không chia sẻ một `ArrayList` mutable bên ngoài.

Ngay cả nếu dùng `Collections.synchronizedList` để tránh race, việc khóa chung có thể trở thành nút cổ chai, và **thứ tự thêm phần tử qua `forEach` vẫn không phải thứ tự nguồn**. Dùng `collect` đúng nghĩa thường thích hợp hơn.

Đặc biệt **không dùng một `ArrayList` làm identity cho `reduce` rồi `acc.add(x)`**: reduction không phải API thay thế `collect` cho container mutable.

## 20. Tính đúng đắn khi có ngoại lệ hoặc dữ liệu không thuần

Một lambda được truyền cho parallel stream nên:

- **Non-interfering**: không sửa nguồn dữ liệu trong khi stream đang xử lý.
- **Stateless**: không dựa vào trạng thái mutable chia sẻ khiến kết quả phụ thuộc thứ tự hoặc lịch chạy.
- **Thread-safe khi cần thiết**: nếu thật sự dùng state, phải biết cách phối hợp; ưu tiên tránh state.
- **Có hợp đồng lỗi rõ**: nếu một nhánh ném exception, terminal operation có thể thất bại; không được giả định các nhánh khác đều đã hoàn tất hoặc mọi side effect đã rollback.

Ví dụ các thao tác như gửi email, ghi cơ sở dữ liệu hay trừ tiền **không nên được giấu trong `map` hoặc `peek` của pipeline** để hy vọng “mỗi phần tử chạy đúng một lần”. Parallel stream không cung cấp transaction hay exactly-once đối với hệ thống ngoài.

Nếu nghiệp vụ phải thực thi một hành động trên mỗi bản ghi, hãy thiết kế **bước thực thi tường minh** với kiểm soát lỗi, retry/idempotency và dữ liệu trạng thái, thay vì để việc tối ưu hóa pipeline quyết định hành động nào được gọi.

## 21. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `parallel()` luôn dùng một thread trên mỗi phần tử | Framework chia theo nguồn/tài nguyên/chi phí | Không phụ thuộc số luồng hay kích thước task |
| `trySplit()` luôn chia đôi và luôn khác null | Contract cho phép các chiến lược chia khác nhau | Kiểm tra null, không hardcode phần 50/50 |
| `reduce(10,Integer::sum)` là cộng thêm 10 một lần | 10 không phải identity của cộng | Dùng identity=0 cho tổng |
| Phép trừ là reducer phù hợp cho parallel | Không có tính kết hợp | Chọn phép gộp có tính kết hợp |
| Accumulator cộng nhưng combiner nhân | Không tương thích phép tính | Dùng combiner phù hợp accumulator |
| Dùng `reduce` với `ArrayList` mutable | Identity có thể chia sẻ và bị mutate | Dùng `collect` với supplier cấp container mới |
| Collector supplier trả một list dùng chung | Các task có thể sửa cùng list | Supplier tạo **instance mới** mỗi lần gọi |
| `parallelStream().toList()` luôn lộn xộn thứ tự | Ordered result vẫn có thể giữ encounter order | Phân biệt thứ tự kết quả và lịch chạy |
| `forEach` và `forEachOrdered` giống nhau | `forEachOrdered` có ràng buộc thứ tự | Chọn đúng theo yêu cầu |
| Mọi `collect` trên parallel đều cập nhật Map đồng thời | Collector không concurrent có thể dùng map cục bộ | Kiểm tra characteristics `CONCURRENT` |
| Cứ bật parallel là nhanh hơn | Có chi phí chia/ghép/đồng bộ | Benchmark theo dữ liệu thật |
| Merge function có side effect vẫn an toàn vì gọi trong collector | Lịch gọi và cách nhóm có thể thay đổi | Viết hàm gộp thuần, đúng hợp đồng |

## 22. Bài tập thực hành và đáp án

**Bài 1 — Chia nguồn.** Một `Spliterator` có `ORDERED`, `SIZED`, `SUBSIZED` và 100 phần tử. Có thể khẳng định `trySplit()` luôn tạo hai phần 50/50 không?

Đáp án: **Không**. Các characteristics nói về thứ tự/kích thước, không buộc thuật toán chia đúng một nửa. `trySplit()` thậm chí có thể trả `null` nếu không thể chia.

**Bài 2 — Gộp subtotal.** Nguồn `[1,2,3,4,5,6,7,8]` chia thành hai phần `[1,2,3,4]` và `[5,6,7,8]`. Các subtotal và kết quả cuối là gì?

Đáp án: subtotal `10` và `26`; combiner cộng cho `36`. Các cách chia khác cũng phải cho `36` trong bài toán cộng nguyên nhỏ này.

**Bài 3 — Identity.** Vì sao `IntStream.of(1,2,3).parallel().reduce(5,Integer::sum)` không phải cách tính tổng rồi cộng 5 đúng nghĩa?

Đáp án: `5` không là identity của phép cộng. Ở các nhánh riêng có thể có identity `5` riêng, nên kết quả không phải “5 + tổng” theo ý định. Dùng `reduce(0,Integer::sum)` rồi cộng 5 vào kết quả cuối, hoặc thiết kế reduction khác đúng hợp đồng.

**Bài 4 — Associativity.** `(10-3)-2` và `10-(3-2)` cho các giá trị nào? Có nên dùng phép trừ làm combiner tổng quát không?

Đáp án: `5` và `9`. Vì không bằng nhau nên phép trừ không kết hợp; không nên dùng làm phép gộp phụ thuộc cách nhóm.

**Bài 5 — Mutable container.** Muốn thu các chuỗi từ parallel stream thành List. Vì sao `reduce(new ArrayList<>(), (list,s)->{list.add(s);return list;}, ...)` rủi ro?

Đáp án: mutate một identity mutable trong reduce vi phạm yêu cầu reduction không can thiệp; identity có thể bị dùng ở nhiều nhánh. Chọn `collect(Collectors.toList())`, `toList()` hoặc `Collector.of(ArrayList::new, ...)`.

**Bài 6 — Collector.** Nêu chức năng của ba thành phần `supplier`, `accumulator`, `combiner` khi thu thành List.

Đáp án: supplier tạo List rỗng **mới** cho phần việc; accumulator thêm phần tử vào list cục bộ; combiner nối hai list thành kết quả chung. Không trả một list dùng chung từ supplier.

**Bài 7 — Finisher.** Trong collector tạo CSV, vì sao cần `StringBuilder::toString`?

Đáp án: `StringBuilder` là container tạm để nối hiệu quả, còn giá trị cuối cần trả là `String`. Finisher thực hiện chuyển đổi này.

**Bài 8 — Ordered.** `numbers.parallelStream().map(...).toList()` có thể cho danh sách đúng encounter order dù các lambda chạy khác thứ tự không?

Đáp án: **Có**, với nguồn ordered và pipeline còn ràng buộc thứ tự. Thứ tự đánh giá nội bộ và thứ tự kết quả là hai việc khác nhau.

**Bài 9 — Lựa chọn API.** Nguồn lớn cần tính số lượng theo loại trong nhiều phần. Dùng gì?

Đáp án: `groupingBy(key, counting())` có thể xử lý parallel bằng cơ chế tích lũy/gộp; cân nhắc `groupingByConcurrent` nếu không cần encounter order và thực sự phù hợp. Đo hiệu năng trước khi kết luận tốt hơn.

**Bài 10 — Đúng hay sai?** “Nếu tôi dùng `parallelStream` và `forEachOrdered`, mọi side effect đều được bảo đảm transaction và exactly-once.”

Đáp án: **Sai**. `forEachOrdered` áp đặt thứ tự action trong một traversal có thứ tự, không có transaction, rollback hay idempotency giữa các lần retry.

## 23. Checklist khi thiết kế pipeline song song

1. **Nguồn có chia tốt không?** Biết kích thước, có `Spliterator` hiệu quả, hay là một luồng I/O tuần tự khó chia?
2. **Hàm xử lý từng phần có thuần và độc lập không?** Không sửa nguồn, không phụ thuộc mutable state dùng chung.
3. **Phép gộp có tính kết hợp không?** Xác minh bằng nhiều cách nhóm, không chỉ bằng một bộ test.
4. **Identity có đúng không?** Kiểm tra phần tử đơn vị; với reduce ba tham số, cả compatibility accumulator/combiner.
5. **Dùng reduce hay collect?** Giá trị tổng hợp thường dùng reduce; container mutable dùng collect.
6. **Supplier có tạo container mới?** Đừng dùng shared list/singleton mutable.
7. **Cần thứ tự không?** Encounter order, `forEachOrdered`, `UNORDERED` ảnh hưởng đúng đắn và hiệu năng.
8. **Có stateful stage không?** `sorted`, `distinct`, `limit`, `takeWhile` có thể tốn thêm chi phí phối hợp.
9. **Có tràn hoặc sai số không?** Tổng int/long có thể overflow; double có vấn đề làm tròn theo cách nhóm.
10. **Lỗi và side effects được quản lý thế nào?** Parallel stream không tự tạo exactly-once hay transaction.
11. **Tốc độ có thực sự tốt hơn?** Benchmark với dữ liệu đại diện, không đo một lần rồi suy diễn.
12. **Stream có được tái sử dụng không?** Một pipeline chỉ tiêu thụ một lần; tạo stream mới cho lượt xử lý khác.

## 24. Tổng kết

- **Chia nguồn** thường được hỗ trợ bởi `Spliterator`; `trySplit` là mô hình để hiểu phân rã, không cam kết chia đôi 50/50.
- **Xử lý từng phần** cho phép nhiều tác vụ tính dữ liệu cục bộ; lịch thread và số lượng công việc do implementation quyết định.
- **Gộp kết quả** phải dùng phép toán có **identity đúng**, **tính kết hợp** và **combiner tương thích** với accumulator.
- **`reduce`** phù hợp kết quả kiểu giá trị; **`collect`** phù hợp container mutable với supplier/accumulator/combiner/finisher.
- **Không chia sẻ container mutable** giữa các task, không dùng `reduce` để mutate `ArrayList` identity.
- **Parallel không tự loại ràng buộc encounter order**; kết quả ordered có thể đúng thứ tự dù các task hoàn tất khác nhau.
- **Thứ tự, hiệu năng, lỗi, tràn số và side effects** vẫn phải được xem xét như một phần của thiết kế.

Tài liệu chuẩn: [Java 17 Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html), [Spliterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html), [Collector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collector.html), [Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html), [Stream package summary — Reduction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html#Reduction).
