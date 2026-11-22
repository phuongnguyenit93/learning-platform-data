# Tại sao giá trị đơn vị sai làm kết quả `reduce()` song song sai?

Trong Java Stream, `reduce()` kết hợp nhiều phần tử thành một kết quả: tính tổng, tích, min/max, kết hợp chuỗi hoặc xây dựng một giá trị tổng hợp. Với phép rút gọn **song song**, Java có thể chia nguồn thành nhiều phần, rút gọn mỗi phần rồi kết hợp những kết quả trung gian. Vì thế **giá trị đơn vị** (*identity*) phải là phần tử trung hòa của phép kết hợp, chứ không phải “giá trị bắt đầu tiện tay”.

Một phép `reduce` có thể trông đúng khi chạy tuần tự nhưng cho kết quả khác khi chạy song song nếu chọn identity sai. Đây không phải lỗi ngẫu nhiên của JVM: code đã vi phạm hợp đồng cần thiết để Java được quyền phân chia và kết hợp các nhóm phần tử.

## 1. `reduce()` làm gì?

Bản hai đối số của `Stream<T>` có dạng:

```java
T reduce(T identity, BinaryOperator<T> accumulator)
```

Đây là chữ ký API rút gọn, không phải chương trình Java độc lập.

- `identity` là giá trị đơn vị đối với phép toán được dùng để kết hợp.
- `accumulator` nhận hai giá trị kiểu `T` và trả về một giá trị kiểu `T`.
- Kết quả là `T`; với stream rỗng, kết quả là chính `identity`.
- Toán tử phải có tính **kết hợp** (*associativity*), không can thiệp nguồn và không phụ thuộc trạng thái bên ngoài có thể thay đổi.

Ví dụ cộng số nguyên:

```java
int total = List.of(1, 2, 3, 4)
        .stream()
        .reduce(0, Integer::sum);
// total == 10
```

Đây là đoạn minh họa bên trong một phương thức, cần `import java.util.List;`. Giá trị đơn vị của phép cộng là `0` vì `0 + x == x` và `x + 0 == x`.

Các identity quen thuộc:

| Phép kết hợp | Identity đúng | Vì sao |
| --- | --- | --- |
| Cộng số nguyên hoặc số thực | `0` hoặc `0.0` tương ứng | `0 + x = x = x + 0` |
| Nhân số | `1` | `1 * x = x = x * 1` |
| Nối `String` bằng `concat` | `""` | Chuỗi rỗng không thêm ký tự |
| `Math.min` trên `int` | `Integer.MAX_VALUE` | `min(MAX_VALUE, x) = x` |
| `Math.max` trên `int` | `Integer.MIN_VALUE` | `max(MIN_VALUE, x) = x` |
| AND boolean | `true` | `true && x = x` |
| OR boolean | `false` | `false || x = x` |

Với `min/max`, nếu cần phân biệt **nguồn rỗng** với kết quả có giá trị thật bằng cực trị của kiểu, ưu tiên `stream.min(...)`, `IntStream.min()`, `IntStream.max()` hoặc dạng `reduce` không có identity trả `Optional`.

## 2. Giá trị đơn vị là luật toán học, không phải “giá trị khởi tạo”

Cho phép toán `⊕` và phần tử đơn vị `e`, hai điều kiện phải đúng với mọi giá trị `x` thuộc miền cần xử lý:

```text
e ⊕ x = x       (identity bên trái)
x ⊕ e = x       (identity bên phải)
```

Đồng thời, phép toán cần có tính kết hợp:

```text
(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
```

**Identity sai** nghĩa là một nhóm phần tử được rút gọn có thể bị cộng thêm, nhân thêm hoặc gắn thêm một giá trị không mong muốn. Trong sequential stream, thường chỉ thấy identity xuất hiện một lần lúc khởi đầu quá trình tính. Trong parallel stream, mỗi nhóm con có thể bắt đầu từ cùng identity. Khi kết quả các nhóm được ghép lại, giá trị sai bị **lặp nhiều lần**.

Ví dụ chọn identity `10` cho phép cộng:

```java
int wrongSequential = List.of(1, 2, 3, 4)
        .stream()
        .reduce(10, Integer::sum);
// wrongSequential == 20, không phải tổng 10.
```

Ở đây ngay cả tuần tự cũng sai nếu nghiệp vụ yêu cầu tổng `10`. Nhưng một số chương trình thực sự **muốn cộng thêm 10 phí cố định**, nên `20` có thể trông đúng trong trường hợp tuần tự. Cái bẫy nằm ở việc nhầm “thêm 10 đúng một lần” với “identity của phép cộng”.

Nếu chia nhóm `[1, 2]` và `[3, 4]` rồi rút gọn từng nhóm với `10`:

```text
Nhóm trái:   reduce(10, +) trên [1, 2] = 10 + 1 + 2 = 13
Nhóm phải:   reduce(10, +) trên [3, 4] = 10 + 3 + 4 = 17
Ghép:        13 + 17 = 30

Nếu không chia nhóm:
             10 + 1 + 2 + 3 + 4 = 20

Tổng thật:    1 + 2 + 3 + 4 = 10
Tổng + phí:  10 + 10 = 20
```

**Parallel stream không hứa hẹn luôn chia chính xác hai nhóm.** Số nhóm và cách ghép là chi tiết thực thi nên đừng dựa vào một số cụ thể của phép reduce sai khi chạy `.parallel()`. Điểm có thể kiểm chứng ở đây là: nếu identity không trung hòa, hai cách nhóm hợp lệ có thể cho **kết quả khác nhau**, khiến phép rút gọn vi phạm hợp đồng parallel reduction.

## 3. Ví dụ Java 17+ chạy đầy đủ, kết quả xác định

Tạo tệp `ReduceIdentityDemo.java`:

```java
import java.util.List;
import java.util.stream.IntStream;

public class ReduceIdentityDemo {
    public static void main(String[] args) {
        List<Integer> values = List.of(1, 2, 3, 4);

        int correctSequential = values.stream()
                .reduce(0, Integer::sum);
        int correctParallel = values.parallelStream()
                .reduce(0, Integer::sum);

        int wrongSequential = values.stream()
                .reduce(10, Integer::sum);

        // Mô phỏng hai nhánh hợp lệ, cho kết quả sai một cách xác định.
        int left = List.of(1, 2).stream()
                .reduce(10, Integer::sum);
        int right = List.of(3, 4).stream()
                .reduce(10, Integer::sum);
        int combined = Integer.sum(left, right);

        int sumPlusOneFee = 10 + values.parallelStream()
                .reduce(0, Integer::sum);

        int product = IntStream.of(2, 3, 4)
                .parallel()
                .reduce(1, (a, b) -> a * b);

        String letters = List.of("A", "B", "C")
                .parallelStream()
                .reduce("", String::concat);

        System.out.println("correctSequential = " + correctSequential);
        System.out.println("correctParallel = " + correctParallel);
        System.out.println("wrongSequential = " + wrongSequential);
        System.out.println("left = " + left);
        System.out.println("right = " + right);
        System.out.println("combined = " + combined);
        System.out.println("sumPlusOneFee = " + sumPlusOneFee);
        System.out.println("product = " + product);
        System.out.println("letters = " + letters);
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac ReduceIdentityDemo.java
java ReduceIdentityDemo
```

Stdout chính xác:

```text
correctSequential = 10
correctParallel = 10
wrongSequential = 20
left = 13
right = 17
combined = 30
sumPlusOneFee = 20
product = 24
letters = ABC
```

Điểm quan trọng của ví dụ: phép rút gọn **đúng** dùng identity `0`, nên tổng bằng `10` dù thực thi tuần tự hay song song. Nếu cần thêm một khoản `10` đúng một lần, hãy **cộng sau khi rút gọn**: `10 + stream.reduce(0, Integer::sum)`.

Chương trình cố tình **không in `values.parallelStream().reduce(10, Integer::sum)`** với một kết quả kỳ vọng cố định. Phép tính này vi phạm điều kiện identity; kết quả của nó có thể phụ thuộc cách JVM phân chia và ghép tác vụ. Hai nhóm tường minh trong chương trình chỉ dùng để chứng minh nguyên nhân, nên các giá trị `13`, `17` và `30` hoàn toàn xác định.

## 4. Vì sao phép rút gọn song song cần identity cho từng nhánh?

Mô hình khái niệm của một parallel reduction:

```text
                     [1, 2, 3, 4]
                          |
                   Chia thành nhóm
                      /       \
                   [1,2]     [3,4]
                    |           |
              reduce(e, op)  reduce(e, op)
                    |           |
                  left        right
                      \       /
                   combine(op)
                          |
                        result
```

Đây chỉ là sơ đồ minh họa. Java có thể chia nhiều nhóm, dùng các ngưỡng phân chia khác nhau và ghép theo nhiều cách. Nếu `e` là identity thực sự, kết quả không bị thay đổi do chèn `e` vào bất kỳ nhánh nào. Nếu `e` không trung hòa, mỗi nhánh có thể đưa thêm sai lệch.

Với phép cộng chuẩn:

```text
left  = 0 + 1 + 2 = 3
right = 0 + 3 + 4 = 7
result = 3 + 7 = 10
```

Với `e = 10`, mỗi nhánh mang thêm `10`, dẫn tới kết quả phụ thuộc số nhánh. Vì vậy một phép reduce đúng phải cho kết quả phù hợp với việc chia và ghép dữ liệu, không được dựa vào cách chạy của một lần thử.

## 5. Chọn đúng identity chưa đủ: accumulator cũng phải kết hợp được

Điều kiện tiếp theo là phép toán phải **associative**. Cộng số nguyên trong phạm vi không có vấn đề ngữ nghĩa do thay nhóm, còn phép trừ không có tính kết hợp:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Dùng `reduce(0, (a, b) -> a - b)` để “cộng dồn trừ” không phải phép reduction hợp lệ cho parallel stream: `0 - x != x`, nên cả identity cũng sai, và phép trừ cũng không associative. Sequential stream có thể cho một kết quả tùy thứ tự duyệt, nhưng parallel stream được phép thay đổi cách nhóm.

Nếu muốn tính `initialAmount - sum(deductions)`, hãy tách biểu thức:

```java
int initialAmount = 100;
int remaining = initialAmount
        - List.of(10, 20, 5).parallelStream()
                .reduce(0, Integer::sum);
// remaining == 65
```

Đoạn minh họa cần `import java.util.List;`. Phép reduce chỉ thực hiện phép cộng có identity `0`; phép trừ áp dụng **một lần** sau khi thu được tổng.

### Lưu ý đặc biệt với `double`

Phép cộng số thực trên máy tính có thể không hoàn toàn associative do làm tròn theo IEEE 754:

```text
(a + b) + c  có thể khác  a + (b + c)
```

Ví dụ với những giá trị chênh nhau rất lớn, các lịch ghép khác nhau có thể tạo ra kết quả `double` hơi khác nhau. Đây là vấn đề **độ chính xác số học**, khác với lỗi chọn identity `10` thay vì `0`. Khi cần độ chính xác thập phân theo nghiệp vụ, cân nhắc `BigDecimal` và quy tắc rounding; khi kiểm thử phép tính song song trên `double`, không mặc định so sánh bit-by-bit nếu thuật toán không bảo đảm thứ tự cộng.

## 6. Hợp đồng `reduce(identity, accumulator)` cần thỏa

Đối với dạng `T reduce(T identity, BinaryOperator<T> accumulator)`, một thiết kế đúng phải đáp ứng:

1. **Identity:** với mọi `t`, `accumulator(identity, t)` phải cho `t`; đối với phép kết hợp hợp lệ giữa các phần, identity cũng phải trung hòa khi ghép ở cả hai phía.
2. **Associativity:** `accumulator(accumulator(a, b), c)` bằng `accumulator(a, accumulator(b, c))` theo ngữ nghĩa mong muốn.
3. **Stateless:** lambda không dựa vào trạng thái có thể thay đổi bên ngoài; lần gọi với cùng tham số cho cùng kết quả logic.
4. **Non-interfering:** không sửa dữ liệu nguồn đang được stream tiêu thụ.
5. **An toàn khi song song:** nếu dùng mutable state ở bên ngoài, phải hiểu rõ vấn đề race; tốt nhất thiết kế reducer trả giá trị mới hoặc dùng primitive reduction/collector đúng hợp đồng.

**Phân biệt identity với seed:** trong một thuật toán tuần tự viết tay, bạn có thể khởi tạo accumulator bằng một giá trị bất kỳ rồi cập nhật lần lượt, ví dụ `sum = 10`. Nhưng `reduce` với chế độ song song diễn giải tham số `identity` theo hợp đồng phần tử đơn vị. Không thể dùng “seed” tùy ý rồi mong Java chỉ áp dụng đúng một lần.

## 7. Dạng reduce ba đối số: thêm yêu cầu tương thích

Dạng tổng quát:

```java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner
)
```

Đây là chữ ký API rút gọn, không phải chương trình độc lập.

Dạng này dùng khi phần tử nguồn thuộc kiểu `T`, nhưng kết quả tổng hợp thuộc kiểu `U`. Chẳng hạn stream chứa bản ghi `Sale` nhưng kết quả là `long`.

```java
record Sale(String sku, int units) {}

List<Sale> sales = List.of(
        new Sale("A", 2),
        new Sale("B", 3),
        new Sale("C", 4)
);

long totalUnits = sales.parallelStream().reduce(
        0L,
        (sum, sale) -> sum + sale.units(),
        Long::sum
);
// totalUnits == 9
```

Đây là đoạn minh họa đặt trong một class và một phương thức, cần `import java.util.List;`. `Sale` là record Java 16+ (hợp lệ với Java 17).

Trong dạng ba đối số:

- `identity` phải là phần tử đơn vị của **combiner**.
- `combiner` phải có tính kết hợp.
- `accumulator` và `combiner` phải **tương thích** theo quy tắc:

```text
combiner(u, accumulator(identity, t)) == accumulator(u, t)
```

với các `u` và `t` hợp lệ (trong đó `u` là một kết quả trung gian kiểu `U`, `t` là phần tử nguồn kiểu `T`).

Với ví dụ trên: `combiner` là phép cộng `long`; `identity=0L`; `accumulator(sum, sale)=sum+sale.units()`. Do đó:

```text
combiner(u, accumulator(0L, sale)) = u + (0 + units)
                                    = u + units
                                    = accumulator(u, sale)
```

Nếu đưa `100L` làm identity để cộng thêm phí cố định, mỗi nhóm có thể cộng thêm `100` trước khi `Long::sum` ghép nhóm. Cách đúng là:

```java
long withFixedFee = 100L + sales.parallelStream()
        .reduce(0L, (sum, sale) -> sum + sale.units(), Long::sum);
// 109
```

Phí được áp dụng **một lần sau reduction**, dù stream chia bao nhiêu nhóm.

## 8. Identity sai có thể “trông đúng” ở tuần tự vì sao?

Hãy phân biệt hai yêu cầu:

**Yêu cầu A — tính tổng các phần tử:** `[1,2,3,4]` phải trả `10`.

```java
int total = values.stream().reduce(0, Integer::sum);
```

**Yêu cầu B — tính tổng và cộng phí cố định 10:** phải trả `20`.

```java
int withFee = 10 + values.stream().reduce(0, Integer::sum);
```

Nếu viết `values.stream().reduce(10, Integer::sum)`, kết quả **tình cờ khớp** yêu cầu B khi thực thi theo một chuỗi tuần tự từ identity `10`. Nhưng với parallel stream, việc áp identity vào nhiều nhánh làm phí xuất hiện nhiều lần.

Lỗi này có thể khó phát hiện khi bộ kiểm thử chỉ kiểm tra sequential stream, hoặc khi đầu vào quá nhỏ khiến song song chưa thực sự chia công việc. **Không có bảo đảm một phép reduce sai identity sẽ luôn lộ lỗi trong mọi lần chạy song song**. Phải kiểm tra hợp đồng identity/associativity, không chỉ quan sát một lần chạy.

## 9. Reduce không có identity: khi nào hữu ích?

`Stream<T>` còn có dạng:

```java
Optional<T> reduce(BinaryOperator<T> accumulator)
```

Vì không có identity, API này trả **`Optional<T>`**: stream rỗng tạo `Optional.empty()`, còn stream có phần tử trả kết quả reduction nếu toán tử hợp lệ.

```java
Optional<Integer> maximum = List.of(4, 1, 9)
        .parallelStream()
        .reduce(Integer::max);
// Optional[9]

Optional<Integer> empty = List.<Integer>of()
        .stream()
        .reduce(Integer::max);
// Optional.empty()
```

Đây là đoạn minh họa trong phương thức, cần `import java.util.List;` và `java.util.Optional;`.

Không có identity làm rõ rằng không thể có max/min của tập rỗng theo cùng ngữ nghĩa với một giá trị thực. Tuy nhiên, **toán tử vẫn phải associative** khi muốn reduction song song đáng tin cậy. Bỏ identity không chữa được một accumulator sai như phép trừ.

Với các stream nguyên thủy, Java có sẵn `IntStream.sum()`, `LongStream.sum()`, `IntStream.min()`, `IntStream.max()`, `DoubleStream.average()` và các API tương ứng. Những API này thường dễ đọc hơn tự viết reduce cho thao tác thống kê phổ biến.

## 10. Đừng dùng mutable identity dùng chung trong reduce

Một lỗi khác thường xuất hiện khi biến identity thành đối tượng mutable:

```java
// Ví dụ sai thiết kế, KHÔNG dùng trong parallel stream:
StringBuilder sb = new StringBuilder();
StringBuilder result = List.of("A", "B", "C")
        .parallelStream()
        .reduce(
                sb,
                (builder, part) -> builder.append(part),
                (left, right) -> left.append(right)
        );
```

Đây là đoạn minh họa cần `import java.util.List;`. `StringBuilder` mutable và có thể bị chia sẻ trong reduction. Các accumulator/combiner trên sửa trực tiếp object được truyền vào. Việc tái sử dụng cùng identity object, đặc biệt giữa các nhánh song song, phá giả định trung hòa và độc lập; có thể gây race, lặp dữ liệu hoặc kết quả bất thường.

Nếu cần nối chuỗi:

```java
String combined = List.of("A", "B", "C")
        .parallelStream()
        .collect(java.util.stream.Collectors.joining());
// "ABC"
```

Hoặc dùng `reduce("", String::concat)` khi dữ liệu nhỏ và dễ hiểu. Khi cần tích lũy mutable state, `collect` thường đúng hơn vì có **supplier tạo container mới** cho từng nhánh, accumulator cập nhật container ấy và combiner gộp các container. Dù chọn cách nào cũng phải tuân thủ hợp đồng API và không chia sẻ mutable state không an toàn.

## 11. Cách kiểm thử identity và phép kết hợp

Khi tự viết reducer, bạn có thể kiểm tra các luật bằng những ví dụ đại diện cho miền dữ liệu. Với phép cộng:

```java
int e = 0;
int a = 3, b = 5, c = 7;

boolean leftIdentity = Integer.sum(e, a) == a;
boolean rightIdentity = Integer.sum(a, e) == a;
boolean associative =
        Integer.sum(Integer.sum(a, b), c)
        == Integer.sum(a, Integer.sum(b, c));

System.out.println(leftIdentity);
System.out.println(rightIdentity);
System.out.println(associative);
```

Đây là đoạn minh họa đặt trong phương thức. Ba dòng kết quả đều là `true`.

Nhưng việc thử vài dữ liệu **không phải chứng minh toán học cho mọi giá trị**, đặc biệt với kiểu dữ liệu phức tạp, overflow, `double`, comparator hoặc aggregator tự định nghĩa. Khi thiết kế một reducer mới, hãy viết rõ phép toán, identity và chứng minh hoặc lập luận vì sao chúng hợp lệ trên miền dữ liệu thực tế.

Một kiểm thử thực dụng:

1. Trả kết quả đúng cho **stream rỗng**, stream một phần tử và nhiều phần tử.
2. So sánh sequential với parallel trên các bộ dữ liệu đủ lớn và nhiều mẫu phân bố.
3. Thử chia list thành nhiều nhóm thủ công; reduce từng nhóm rồi combine và so với reduce toàn bộ.
4. Thử những trường hợp có số âm, số 0, dữ liệu lặp, giá trị biên hoặc giá trị đặc biệt nếu ứng dụng cần.
5. Nếu có kết quả khác nhau, tìm nguyên nhân từ identity, associativity, stateful side effect hoặc độ chính xác số học; đừng “sửa” bằng cách ép stream về sequential mà bỏ qua hợp đồng.

## 12. Lỗi thường gặp và cách sửa

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| `reduce(10, Integer::sum)` để cộng phí 10 một lần | Identity `10` không trung hòa; mỗi nhánh có thể đưa thêm 10 | `10 + stream.reduce(0, Integer::sum)` |
| `reduce(0, (a,b) -> a*b)` để nhân | `0` không phải identity của nhân; làm tích thành 0 | `reduce(1, (a,b) -> a*b)` |
| `reduce(0, (a,b) -> a-b)` trên parallel stream | Trừ không associative; identity cũng không đúng ở phía trái | Tính tổng cần trừ rồi trừ một lần bên ngoài |
| Dùng `new StringBuilder()` làm identity, rồi `append` vào chính nó | Mutable identity có thể bị chia sẻ giữa nhánh; vi phạm hợp đồng | Dùng `Collectors.joining()` hoặc `collect` đúng cách |
| Bắt chước sequential loop `total = 100` bằng identity `100` trong parallel reduce | Nhầm seed với identity | `100 + parallelReduceWithIdentityZero` |
| Chỉ so sánh một lần sequential/parallel | Một lịch chia nhánh có thể che lỗi | Kiểm tra luật identity và associativity bằng ví dụ/chứng minh |
| Cho rằng output phải luôn cùng bit với phép cộng `double` tuần tự | Làm tròn số thực có thể thay đổi khi đổi nhóm | Chọn độ chính xác và phép tổng hợp phù hợp |

## Tự kiểm tra

**Câu 1.** Identity của `Integer::sum` là gì? Vì sao?

**Đáp án:** `0`, vì cộng với `0` ở hai phía không thay đổi giá trị.

**Câu 2.** `List.of(1,2,3).stream().reduce(5, Integer::sum)` trả gì? Có được dùng làm reduce song song nếu ý nghĩa là “cộng phí 5 một lần” không?

**Đáp án:** Tuần tự trả `11`. Không nên dùng làm reduction song song theo ý nghĩa ấy vì identity `5` không trung hòa; hãy viết `5 + stream.reduce(0, Integer::sum)`.

**Câu 3.** Với hai nhóm `[1,2]` và `[3,4]`, giảm mỗi nhóm bằng `reduce(10, Integer::sum)` rồi cộng kết quả nhận gì?

**Đáp án:** `13 + 17 = 30`, khác `20` của reduction tuần tự với seed `10`.

**Câu 4.** Có thể dùng `reduce(0, (a,b) -> a-b)` trên parallel stream để trừ dần không?

**Đáp án:** Không: phép trừ không kết hợp và `0 - x != x`. Hãy mô tả phép toán bằng những reduction có hợp đồng hợp lệ.

**Câu 5.** Trong dạng ba đối số, ngoài identity của combiner, còn cần luật gì?

**Đáp án:** `combiner(u, accumulator(identity, t)) == accumulator(u,t)`; thêm tính kết hợp của combiner và tính stateless/non-interfering của các hàm.

**Câu 6.** Vì sao một phép reduce sai đôi khi vẫn cho “đúng” khi chạy parallel với bộ dữ liệu nhỏ?

**Đáp án:** JVM có thể không thực sự chia thành nhiều nhóm hoặc lịch xử lý tình cờ không làm lỗi lộ ra. Kết quả quan sát được không thay thế việc kiểm chứng hợp đồng.

## Ghi nhớ

- **Identity là phần tử trung hòa** của phép toán, không phải giá trị khởi tạo tùy ý.
- **Parallel reduce có thể áp identity vào nhiều nhóm**, nên identity sai làm các nhóm mang thêm sai lệch.
- **Accumulator/combiner phải associative** và không phụ thuộc trạng thái chia sẻ có thể thay đổi.
- Khi cần cộng một khoản **đúng một lần**, hãy giảm bằng identity đúng rồi cộng khoản đó **sau reduction**.
- Với reduce ba đối số, phải giữ cả **identity của combiner** lẫn **tính tương thích** giữa accumulator và combiner.
- Kiểm tra kết quả bằng nhiều cách chia nhóm; đừng dựa vào một lịch thực thi song song cụ thể.
