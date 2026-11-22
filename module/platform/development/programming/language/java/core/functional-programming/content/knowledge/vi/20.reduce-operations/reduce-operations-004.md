# Tính kết hợp của phép toán và vì sao phép trừ thường không phù hợp với reduce() trong Java

## 1. Đặt vấn đề: reduce không chỉ là viết gọn một vòng lặp

`reduce()` là **thao tác kết thúc** (*terminal operation*) trong Java Stream API: nó kết hợp nhiều phần tử thành một giá trị tổng hợp, ví dụ tổng số, tích số, giá trị lớn nhất hoặc chuỗi được ghép. Ý tưởng nghe giống “duyệt các phần tử rồi cập nhật biến kết quả”, nhưng hợp đồng của `Stream.reduce` còn quan trọng hơn: phép kết hợp phải **có tính kết hợp** (*associativity*) để Java có thể nhóm các phép tính theo những cách khác nhau, đặc biệt trong parallel stream, mà vẫn cho kết quả đúng.

So sánh hai phép toán quen thuộc:

~~~text
Phép cộng:   (10 + 3) + 2 = 10 + (3 + 2) = 15
Phép trừ:    (10 - 3) - 2 = 5
             10 - (3 - 2) = 9
~~~

Phép cộng thỏa tính kết hợp trên các số nguyên theo nghĩa số học phù hợp. Phép trừ **không thỏa**: chỉ cần đổi cách đặt dấu ngoặc đã đổi kết quả từ `5` thành `9`.

Đó là nguyên nhân `(a, b) -> a - b` thường **không phù hợp** để làm phép kết hợp của `reduce()`. Code có thể **biên dịch và đôi khi cho kết quả mong đợi trong stream tuần tự**, nhưng không đáp ứng những điều kiện cần cho việc gộp từng phần kết quả một cách đáng tin khi Java chia công việc thành các nhóm.

**Thông điệp chính:** Muốn dùng `reduce()` đúng, hãy kiểm tra cả **phép kết hợp** lẫn **giá trị đồng nhất** (*identity*), không chỉ kiểm tra kiểu của lambda và một vài đầu vào thử nghiệm.

## 2. Tính kết hợp (associativity) là gì?

Một phép toán hai ngôi `⊕` có tính kết hợp nếu với mọi giá trị `a`, `b`, `c` hợp lệ:

~~~text
(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
~~~

Điều này có nghĩa ta được **thay đổi cách nhóm** các phần tử nhưng vẫn giữ nguyên thứ tự các phần tử và không đổi kết quả.

Ví dụ:

~~~text
Cộng:        (2 + 3) + 4 = 2 + (3 + 4) = 9
Nhân:        (2 × 3) × 4 = 2 × (3 × 4) = 24
Nối chuỗi:   ("a" + "b") + "c" = "a" + ("b" + "c") = "abc"
Trừ:         (10 - 3) - 2 = 5 ≠ 9 = 10 - (3 - 2)
Chia:        (24 / 4) / 2 = 3 ≠ 12 = 24 / (4 / 2)
~~~

**Tính kết hợp không giống tính giao hoán.**

- *Kết hợp*: `(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)` — cho phép đổi **dấu ngoặc**.
- *Giao hoán*: `a ⊕ b = b ⊕ a` — cho phép đổi **thứ tự hai phần tử**.

Ví dụ, **nối chuỗi có tính kết hợp nhưng không có tính giao hoán**: `"a" + "b"` khác `"b" + "a"`. Vì vậy không được khẳng định `reduce()` luôn cần phép toán giao hoán. Với nguồn stream có **encounter order** và phép giảm có tính kết hợp, Java vẫn có thể giữ thứ tự phần tử logic khi gộp chuỗi; nếu chủ động làm cho phép toán trở nên unordered hoặc phụ thuộc side effect thì phải xét hợp đồng từng API.

### 2.1. Đặc điểm của phép trừ

Phép trừ cho thấy rõ ràng:

~~~text
a - (b - c) = a - b + c
(a - b) - c = a - b - c
~~~

Hai biểu thức khác nhau ở dấu của `c`. Trừ vài trường hợp đặc biệt, không thể coi chúng tương đương.

Ví dụ với `a = 10`, `b = 3`, `c = 2`:

~~~text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
~~~

Một bộ kiểm thử chỉ dùng số `0` hoặc những trường hợp trùng hợp đặc biệt có thể không phát hiện vấn đề. Để kiểm tra tính kết hợp, luôn thử ít nhất **ba phần tử** và hai cách nhóm khác nhau.

## 3. Hai biến thể reduce phổ biến và điều kiện của chúng

Với `Stream<T>`, Java có các overload:

~~~java
T reduce(T identity, BinaryOperator<T> accumulator);

Optional<T> reduce(BinaryOperator<T> accumulator);
~~~

Đây là **chữ ký rút gọn từ Stream API**, không phải mã khai báo interface để chạy riêng.

### 3.1. `reduce(identity, accumulator)`

Ví dụ:

~~~java
int sum = List.of(1, 2, 3, 4).stream()
        .reduce(0, Integer::sum);
~~~

Kết quả là `10`. `Integer::sum` mô tả phép cộng hai `Integer` và là một `BinaryOperator<Integer>` tương thích; `0` là identity thích hợp cho phép cộng.

Hợp đồng cần nhớ:

1. **`accumulator` phải kết hợp được**: có tính kết hợp.
2. **`identity` phải là phần tử đồng nhất** của phép toán: `accumulator(identity, x) = x` và, với một phép giảm đúng kiểu, `accumulator(x, identity) = x`.
3. Lambda sử dụng trong stream reduction phải phù hợp với yêu cầu **non-interfering** và **stateless** (không sửa nguồn, không phụ thuộc trạng thái ngoài thay đổi theo thứ tự gọi).

API có thể chia nguồn thành nhiều nhóm, giảm từng nhóm rồi gộp kết quả. Nếu `identity` và `accumulator` đáp ứng hợp đồng, cách nhóm khác nhau vẫn hợp lý.

### 3.2. `reduce(accumulator)` không truyền identity

~~~java
Optional<Integer> sum = List.of(1, 2, 3, 4).stream()
        .reduce(Integer::sum);
~~~

Kết quả là `Optional.of(10)`. Với stream **rỗng**, overload này trả `Optional.empty()` vì không có phần tử ban đầu để sử dụng làm kết quả.

Với stream rỗng, `reduce(0, Integer::sum)` trả trực tiếp `0`; còn `reduce(Integer::sum)` trả Optional rỗng. **Bỏ identity không làm yêu cầu tính kết hợp biến mất**. Trong overload không identity, `accumulator` vẫn phải là một phép toán kết hợp được.

### 3.3. So sánh ngắn

| Thuộc tính | `reduce(identity, accumulator)` | `reduce(accumulator)` |
|---|---|---|
| Đối số | Giá trị khởi đầu và phép kết hợp | Chỉ phép kết hợp |
| Kiểu kết quả | `T` | `Optional<T>` |
| Stream rỗng | Trả `identity` | Trả `Optional.empty()` |
| Yêu cầu về phép toán | Kết hợp, identity đúng | Kết hợp |
| Cách dùng tiêu biểu | Tính tổng bắt đầu từ `0`, tích từ `1` | Tìm min/max khi không muốn giá trị mặc định |
| Có sửa được lỗi không kết hợp của phép trừ? | Không | Không |

**Đừng nhầm:** bỏ `identity` có thể khiến kết quả tuần tự trông giống biểu thức trừ truyền thống từ phần tử đầu tiên, nhưng không biến phép trừ thành associative operation.

## 4. Vì sao identity bằng 0 không sửa được phép trừ?

Một **identity** `e` phải thỏa **cả hai phía**:

~~~text
e ⊕ x = x
x ⊕ e = x
~~~

Với phép cộng, `0` thỏa:

~~~text
0 + x = x
x + 0 = x
~~~

Với phép nhân, `1` thỏa:

~~~text
1 × x = x
x × 1 = x
~~~

Nhưng với phép trừ:

~~~text
0 - 5 = -5    (không bằng 5)
5 - 0 = 5
~~~

`0` chỉ là **đồng nhất bên phải** đối với phép trừ, **không** là đồng nhất bên trái. Vì thế:

~~~java
int value = List.of(10, 3, 2).stream()
        .reduce(0, (a, b) -> a - b);
~~~

Trên pipeline tuần tự như đoạn minh họa, các bước tương ứng với `((0 - 10) - 3) - 2`, cho kết quả `-15`. Nếu người viết chỉ mong `(10 - 3) - 2 = 5` thì ngay cả cách đặt identity `0` đã làm kết quả khác kỳ vọng.

Dù không truyền identity:

~~~java
int value = List.of(10, 3, 2).stream()
        .reduce((a, b) -> a - b)
        .orElseThrow();
~~~

Pipeline tuần tự thực hiện như phép trừ từ phần tử đầu tiên nên có thể cho `5`, nhưng về **hợp đồng reduce**, accumulator vẫn không có tính kết hợp. Khi tách nhóm, cách gộp trung gian có thể cho kết quả khác.

## 5. Ví dụ Java 17 hoàn chỉnh: phép cộng ổn, phép trừ đổi khi nhóm

Lưu thành **`AssociativityDemo.java`**:

~~~java
import java.util.List;
import java.util.stream.IntStream;

public class AssociativityDemo {
    public static void main(String[] args) {
        int leftSubtract = (10 - 3) - 2;
        int rightSubtract = 10 - (3 - 2);

        int leftAdd = (10 + 3) + 2;
        int rightAdd = 10 + (3 + 2);

        List<Integer> values = List.of(10, 3, 2);
        int sum = values.stream().reduce(0, Integer::sum);
        int subtractWithIdentity = values.stream()
                .reduce(0, (a, b) -> a - b);
        int subtractWithoutIdentity = values.stream()
                .reduce((a, b) -> a - b)
                .orElseThrow();
        int parallelAddition = IntStream.rangeClosed(1, 10)
                .parallel()
                .reduce(0, Integer::sum);

        System.out.println("subtractLeft=" + leftSubtract);
        System.out.println("subtractRight=" + rightSubtract);
        System.out.println("addLeft=" + leftAdd);
        System.out.println("addRight=" + rightAdd);
        System.out.println("sum=" + sum);
        System.out.println("subtractIdentity=" + subtractWithIdentity);
        System.out.println("subtractNoIdentity=" + subtractWithoutIdentity);
        System.out.println("parallelAddition=" + parallelAddition);
    }
}
~~~

Lệnh chạy (JDK 17+):

~~~bash
javac AssociativityDemo.java
java AssociativityDemo
~~~

Stdout dự kiến:

~~~text
subtractLeft=5
subtractRight=9
addLeft=15
addRight=15
sum=15
subtractIdentity=-15
subtractNoIdentity=5
parallelAddition=55
~~~

**Phân tích:**

- Hai dòng đầu minh họa phép trừ **không kết hợp**: đổi dấu ngoặc, đổi kết quả.
- Phép cộng cho `15` theo cả hai cách nhóm vì trong phạm vi giá trị minh họa, phép cộng đúng tính kết hợp.
- `reduce(0, Integer::sum)` dùng identity đúng và phép cộng kết hợp nên ra `15`.
- `reduce(0, (a,b) -> a-b)` là **mẫu không nên áp dụng cho phép giảm tổng quát**; kết quả tuần tự `-15` không phải hiệu `10-3-2`.
- `reduce((a,b)->a-b)` cho `5` ở pipeline tuần tự minh họa nhưng **vẫn vi phạm yêu cầu associativity** của phép giảm.
- `IntStream.rangeClosed(1,10).parallel().reduce(0,Integer::sum)` trả `55` vì phép cộng `int` cùng identity `0` thỏa hợp đồng giảm; không dựa vào thứ tự xử lý từng thread.

Chương trình này **cố ý** chạy các phép trừ trên stream tuần tự để cho ra đầu ra dễ kiểm chứng, không hề khẳng định dùng phép trừ với `reduce()` là thiết kế đúng cho mọi trường hợp.

## 6. Parallel reduce có thể nhóm lại phép toán như thế nào?

Điểm cốt lõi của parallel reduction là các phần tử có thể được chia thành **nhóm con**. Mỗi nhóm tạo một kết quả tạm, rồi các kết quả tạm được gộp. Với phép toán có tính kết hợp và identity đúng, việc nhóm lại không đổi kết quả logic.

Xét bốn giá trị `1, 2, 3, 4` và identity `0`.

**Một cách tính tuần tự:**

~~~text
(((0 - 1) - 2) - 3) - 4 = -10
~~~

**Một cách chia nhóm thành hai phần:**

~~~text
Nhóm trái:  (0 - 1) - 2 = -3
Nhóm phải: (0 - 3) - 4 = -7
Gộp nhóm:  -3 - (-7) = 4
~~~

Kết quả `-10` và `4` khác nhau. Đó là một **mô hình nhóm phép tính hợp lệ về mặt cách chia công việc** nhưng **không hợp lệ về nghĩa nghiệp vụ** khi ta kỳ vọng phép trừ trái-sang-phải. Vì Java không cam kết một thứ tự nhóm cụ thể cho một accumulator vi phạm hợp đồng, không nên khẳng định một lệnh `parallel().reduce(0,(a,b)->a-b)` sẽ luôn trả `4` hay luôn trả `-10`. Kết quả có thể phụ thuộc nguồn, cách phân mảnh, JDK và cách thực thi.

Với **phép cộng**:

~~~text
Tuần tự:  (((0 + 1) + 2) + 3) + 4 = 10
Chia nhóm: (0 + 1 + 2) + (0 + 3 + 4) = 10
~~~

Hai cách nhóm vẫn cho `10`.

### 6.1. Ví dụ Java kiểm chứng một cách nhóm trừ khác

Lưu thành **`RegroupingDemo.java`**:

~~~java
import java.util.List;

public class RegroupingDemo {
    public static void main(String[] args) {
        List<Integer> values = List.of(1, 2, 3, 4);

        int sequential = values.stream()
                .reduce(0, (a, b) -> a - b);

        int leftChunk = List.of(1, 2).stream()
                .reduce(0, (a, b) -> a - b);
        int rightChunk = List.of(3, 4).stream()
                .reduce(0, (a, b) -> a - b);
        int regrouped = leftChunk - rightChunk;

        System.out.println("sequential=" + sequential);
        System.out.println("leftChunk=" + leftChunk);
        System.out.println("rightChunk=" + rightChunk);
        System.out.println("regrouped=" + regrouped);
        System.out.println("same=" + (sequential == regrouped));
        System.out.println("zeroMinusFive=" + (0 - 5));
        System.out.println("fiveMinusZero=" + (5 - 0));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac RegroupingDemo.java
java RegroupingDemo
~~~

Stdout:

~~~text
sequential=-10
leftChunk=-3
rightChunk=-7
regrouped=4
same=false
zeroMinusFive=-5
fiveMinusZero=5
~~~

Chương trình **không dựa vào lịch chạy parallel hay fork/join của JVM** để ép một đáp án cụ thể. Nó tự chia dữ liệu thành hai đoạn, thực hiện đúng phép trừ đã chọn rồi gộp thủ công; nhờ đó mọi dòng stdout đều có thể kiểm chứng.

**Suy luận:** Với một phép toán mà chỉ đổi cách nhóm đã thay kết quả, ta không thể xem nó là phép giảm an toàn theo hợp đồng Stream. Không phải parallel stream “tính sai”; chính accumulator không thỏa ràng buộc của `reduce()`.

## 7. Overload ba tham số: accumulator và combiner phải phối hợp nhất quán

`Stream<T>` còn có overload cho trường hợp kiểu kết quả `U` **khác** kiểu phần tử `T`:

~~~java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner);
~~~

Ví dụ cần tổng **độ dài chuỗi** từ `Stream<String>` và trả một `Integer`:

~~~java
int totalLength = List.of("java", "fp", "stream")
        .parallelStream()
        .reduce(
                0,
                (sum, word) -> sum + word.length(),
                Integer::sum
        );
~~~

Kết quả là `12`. Ở đây:

- `identity = 0`: phần tử đồng nhất của **combiner**.
- `accumulator`: nhận tổng hiện tại kiểu `Integer` và một `String` để cập nhật tổng độ dài.
- `combiner = Integer::sum`: gộp hai tổng cục bộ khi parallel stream chia công việc.
- `combiner` có tính kết hợp, `0` là identity phù hợp và `accumulator` nhất quán với `combiner`.

Một điều kiện quan trọng của hợp đồng ba tham số là tính **tương thích**:

~~~text
combiner(u, accumulator(identity, t)) == accumulator(u, t)
~~~

Trong ví dụ: `u + (0 + length(t)) = u + length(t)`, nên điều kiện được thỏa.

### 7.1. Sai lầm: dùng combiner là phép trừ

~~~java
// SAI về hợp đồng reduce, dù cú pháp có thể biên dịch:
int result = words.parallelStream().reduce(
        0,
        (sum, word) -> sum + word.length(),
        (left, right) -> left - right
);
~~~

`combiner` trừ hai tổng từng nhóm. Khi so với phiên bản tuần tự (không cần gộp nhóm), kết quả có thể khác; identity `0` cũng không phải phần tử đồng nhất hai phía của phép trừ. Giải pháp đúng là `Integer::sum` nếu mục tiêu là **cộng số lượng**.

### 7.2. Không được dùng reduce để thay thế collector mutable sai hợp đồng

Tránh kiểu:

~~~java
// KHÔNG KHUYẾN NGHỊ: mutate StringBuilder qua reduce.
StringBuilder all = words.parallelStream().reduce(
        new StringBuilder(),
        (builder, word) -> builder.append(word),
        (left, right) -> left.append(right)
);
~~~

Vấn đề: identity mutable có thể được chia sẻ và biến đổi giữa các nhánh; accumulator/combiner không còn diễn đạt phép giảm với identity bất biến và an toàn. Với phép ghép chuỗi, dùng `Collectors.joining()`. Với thu thập vào danh sách, dùng `toList()` hoặc `collect(Collectors.toList())` khi phù hợp. **`collect` được thiết kế cho quá trình gom kết quả mutable**, trong khi `reduce` nên biểu diễn việc kết hợp các giá trị theo hợp đồng của nó.

## 8. Chương trình Java 17 hoàn chỉnh: giữ phép cộng bên trong, trừ sau

Đây là mẫu thiết kế **đúng về bản chất nghiệp vụ** khi bạn muốn tính “ngân sách ban đầu trừ tổng chi phí”.

Giả sử có các chi phí `12, 25, 8`, và ngân sách `100`:

~~~text
Tổng chi phí: 12 + 25 + 8 = 45
Còn lại: 100 - 45 = 55
~~~

**Không** giảm trực tiếp bằng phép trừ `reduce(100,(a,b)->a-b)`. `100` không phải identity cho phép trừ, và phép toán không kết hợp. Hãy tính tổng chi phí bằng phép cộng, rồi thực hiện **một phép trừ sau khi giảm**.

Lưu file **`SafeReductionDemo.java`**:

~~~java
import java.util.List;
import java.util.stream.Stream;

public class SafeReductionDemo {
    record Stats(long total, long count) {
        Stats combine(Stats other) {
            return new Stats(total + other.total, count + other.count);
        }
    }

    public static void main(String[] args) {
        List<String> words = List.of("java", "fp", "stream");

        Stats stats = words.parallelStream()
                .map(s -> new Stats(s.length(), 1))
                .reduce(new Stats(0, 0), Stats::combine);

        int letters = words.parallelStream().reduce(
                0,
                (sum, word) -> sum + word.length(),
                Integer::sum
        );

        int budget = 100;
        int remaining = budget - letters;
        double average = (double) stats.total() / stats.count();

        System.out.println("stats=" +
                stats.total() + "," + stats.count());
        System.out.println("average=" + average);
        System.out.println("letters=" + letters);
        System.out.println("remaining=" + remaining);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SafeReductionDemo.java
java SafeReductionDemo
~~~

Stdout:

~~~text
stats=12,3
average=4.0
letters=12
remaining=88
~~~

**Giải thích:**

1. `Stats` là một record bất biến chứa tổng độ dài và số lượng phần tử. `combine` cộng từng trường tương ứng.
2. `new Stats(0, 0)` là identity đúng; phép gộp `Stats::combine` có tính kết hợp theo phép cộng của các trường (trong miền số minh họa không xảy ra tràn).
3. `words.parallelStream().map(...).reduce(...)` cho phép nhóm các đối tượng `Stats` theo nhiều cách nhưng vẫn thu được `total=12` và `count=3`.
4. Overload ba đối số tính tổng độ dài trực tiếp từ `String` sang `Integer`, với `Integer::sum` là combiner đúng.
5. `remaining = budget - letters` là **một phép trừ sau khi đã có tổng**. Đây là nơi phép trừ thực sự phản ánh công thức nghiệp vụ.
6. `average` được tính từ hai giá trị đã giảm. Với dữ liệu rỗng, `stats.count()` bằng `0`, vì vậy ứng dụng thực tế phải kiểm tra số lượng trước khi chia. Ví dụ dùng danh sách có ba phần tử nên kết quả `4.0` hợp lệ.

Record và `Stream.toList()` là các API/tính năng ổn định trong Java 17. Mẫu code này không tạo state mutable dùng chung giữa các nhánh parallel.

## 9. Nếu nghiệp vụ thực sự muốn trừ liên tiếp theo thứ tự thì sao?

Có bài toán cần chính xác phép tính:

~~~text
Bắt đầu với 100
Trừ lần lượt 10, 20, 5
Kết quả: 65
~~~

Nếu **thứ tự cập nhật là một phần của yêu cầu**, một vòng lặp tường minh giúp diễn tả ý định:

~~~java
int balance = 100;
for (int charge : new int[] {10, 20, 5}) {
    balance -= charge;
}
System.out.println(balance); // 65
~~~

Đây là **đoạn minh họa** bên trong một phương thức, không có `main` riêng. Cách viết này rõ ràng: `balance` được cập nhật tuần tự đúng ba lần. Nếu yêu cầu chỉ là “ngân sách trừ tổng chi phí”, có thể tính `100 - IntStream.of(10,20,5).sum()`; khi đó giảm theo phép **cộng** và trừ đúng một lần ở cuối.

Trên một stream có thứ tự và thực thi tuần tự, `reduce((a,b)->a-b)` thường quan sát được hành vi fold trái. **Tuy nhiên**, vì phép trừ không thỏa hợp đồng accumulator kết hợp được, không nên coi đó là một *reduction* hợp lệ để tối ưu song song hoặc làm nền cho code cần bảo đảm lâu dài. Một vòng lặp tường minh hoặc mô hình hóa lại bài toán bằng phép cộng dễ giải thích và kiểm thử hơn.

### 9.1. Không nhầm phép trừ với cộng số âm

Phép tính:

~~~text
100 - 10 - 20 - 5 = 100 + (-10) + (-20) + (-5) = 65
~~~

Trong trường hợp dữ liệu có nghĩa “các khoản cần trừ”, bạn có thể chuyển từng khoản thành **giá trị có dấu** rồi cộng:

~~~java
int balance = 100 + java.util.stream.IntStream.of(10, 20, 5)
        .map(charge -> -charge)
        .sum();
~~~

Dạng này dùng **`sum`** trên số có dấu, không phải dùng **phép trừ** làm phép kết hợp. Tuy nhiên, cần chú ý `-Integer.MIN_VALUE` vẫn là `Integer.MIN_VALUE` do tràn `int`; trong bài toán tài chính có miền số lớn, hãy kiểm soát tràn và cân nhắc `long` hoặc `BigDecimal` phù hợp.

## 10. Tính kết hợp không phải lúc nào cũng hiển nhiên trong Java

### 10.1. Số nguyên và tràn số

Phép cộng `int` của Java có tính kết hợp theo mô hình **tràn số 32-bit dạng modulo**: các cách nhóm không đổi bit-pattern của tổng cuối trong phép cộng `int` thuần túy, nhưng kết quả vẫn có thể **sai nghĩa nghiệp vụ** khi tổng vượt phạm vi `int`.

Ví dụ:

~~~java
int unexpected = java.util.stream.IntStream.of(
        Integer.MAX_VALUE, 1
).sum();
// Kết quả tràn thành Integer.MIN_VALUE.
~~~

Đây là đoạn minh họa; nếu cần phát hiện tràn, cân nhắc `Math.addExact` trong phép cộng. Song **`Math.addExact` có thể ném ngoại lệ tại các điểm nhóm khác nhau** nếu xuất hiện tổng trung gian vượt miền biểu diễn, dù tổng toán học cuối có thể nằm trong miền; khi thiết kế reduction song song cần quy định cách xử lý overflow. Nếu tổng rất lớn, chuyển sang `long` hoặc `BigInteger` và kiểm soát miền giá trị.

### 10.2. Số thực floating-point không hoàn toàn kết hợp

Ngay cả phép cộng `double` **không có tính kết hợp chính xác** vì làm tròn theo IEEE 754:

~~~text
(a + b) + c có thể khác a + (b + c)
~~~

Một ví dụ thường gặp: `a=1e16`, `b=-1e16`, `c=1`:

~~~java
double left = (1e16 + -1e16) + 1.0;   // 1.0
double right = 1e16 + (-1e16 + 1.0); // 0.0
~~~

Vì `-1e16 + 1.0` được làm tròn về `-1e16`, nên kết quả cuối khác nhau. Do đó parallel reduction trên `double` có thể thay đổi những bit thấp của kết quả do thứ tự nhóm. Nếu ứng dụng yêu cầu kết quả ổn định tuyệt đối hoặc chính xác tiền tệ, cần chọn phương pháp số học và kiểu dữ liệu thích hợp. Với số tiền thập phân, thường nên dùng `BigDecimal` hoặc đơn vị nguyên nhỏ nhất có giới hạn rõ.

### 10.3. Phép nối chuỗi có tính kết hợp nhưng không giao hoán

~~~java
String joined = List.of("a", "b", "c").parallelStream()
        .reduce("", String::concat);
~~~

Kết quả logic trên stream có thứ tự là `"abc"`. Vì `("a"+"b")+"c" = "a"+("b"+"c")`, việc nhóm các đoạn nối không đổi chuỗi cuối nếu **giữ nguyên thứ tự phần tử**. Nhưng `"ab" != "ba"`, nên phép nối không giao hoán.

Trên lượng dữ liệu lớn, nối từng chuỗi bằng `String::concat` có thể tốn chi phí cấp phát; `Collectors.joining()` thường là API phù hợp hơn để nối nhiều chuỗi. **Tính đúng về đại số không tự động bảo đảm hiệu năng tốt.**

### 10.4. Max/min và identity

`Integer::max` hoặc `Integer::min` là các phép toán kết hợp. Nhưng identity phải được chọn đúng:

~~~java
int maximum = List.of(-10, -5, -7).stream()
        .reduce(Integer.MIN_VALUE, Integer::max); // -5
~~~

Chọn identity bằng `0` trong một bài toán mọi số âm sẽ làm kết quả tối đa bị sai: `max(0,-10,-5,-7)=0` dù `0` không xuất hiện. Khi không có một identity hợp lý cho miền dữ liệu, dùng overload `reduce(BinaryOperator)` trả `Optional<T>` hoặc `max()`/`min()` chuẩn của Stream.

## 11. Mẫu đúng: tránh sửa object mutable trong reduce

Một lỗi khó phát hiện là dùng `reduce` để tích lũy vào **cùng một object mutable**:

~~~java
// Ví dụ KHÔNG NÊN dùng trong parallel Stream:
List<Integer> result = numbers.parallelStream()
        .reduce(
                new ArrayList<>(),
                (list, n) -> {
                    list.add(n);
                    return list;
                },
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        );
~~~

Ngoài vấn đề type inference/generic khi viết trong ngữ cảnh thực tế, đoạn code này có thể **sai hợp đồng reduction** vì identity mutable có thể bị thay đổi và được chia sẻ giữa các tác vụ, gây lặp phần tử hoặc race condition. Nó chỉ là ví dụ cảnh báo, không khuyến nghị sao chép chạy.

Nếu mục tiêu thu thập các phần tử vào collection, dùng:

~~~java
List<Integer> result = numbers.stream().toList();
~~~

Hoặc khi cần một `ArrayList` có thể sửa sau đó:

~~~java
List<Integer> result = numbers.stream()
        .collect(java.util.stream.Collectors.toCollection(ArrayList::new));
~~~

Các đoạn cần khai báo `numbers` và imports thích hợp. `collect` có semantics phù hợp để gom kết quả mutable và có thể phối hợp các container trung gian đúng hợp đồng collector. `reduce` phù hợp hơn với các phép kết hợp **giá trị** hoặc các accumulator bất biến.

## 12. Checklist thiết kế phép giảm có thể song song hóa

Trước khi viết `reduce`, hãy đặt các câu hỏi:

1. **Giá trị đầu ra cần là gì?** Tổng, tích, max/min, một object thống kê, hay hiệu số theo thứ tự?
2. **Phép toán hai ngôi là gì?** Cộng, nhân, max, nối chuỗi hay một hàm nghiệp vụ?
3. **Có kết hợp được không?** Thử `(a ⊕ b) ⊕ c` và `a ⊕ (b ⊕ c)` với ba giá trị bất kỳ và dữ liệu biên.
4. **Identity thật sự trung tính ở cả hai phía không?** `0` với cộng, `1` với nhân; `0` **không** là identity hai phía của phép trừ.
5. **Nếu dùng overload ba đối số, accumulator và combiner có tương thích không?** Kiểm tra quy tắc `combiner(u, accumulator(identity, t)) == accumulator(u, t)`.
6. **Có đang mutate một object được dùng làm identity không?** Nếu có, cân nhắc `collect` hoặc accumulator bất biến.
7. **Có phụ thuộc thứ tự gọi, số lần gọi, side effect hoặc trạng thái bên ngoài không?** Giảm tổng quát không nên phụ thuộc vào những điều đó.
8. **Có trường hợp stream rỗng không?** Chọn identity đúng hoặc xử lý `Optional.empty()`.
9. **Có vấn đề overflow, floating-point precision hoặc miền giá trị không?** Chọn kiểu và chiến lược số học phù hợp.
10. **Có cần giữ encounter order không?** Với phép toán không giao hoán như nối chuỗi, thứ tự nguồn phải được hiểu rõ.
11. **Dữ liệu có số lượng lớn hoặc chạy `parallel()` không?** Phải bảo đảm phép kết hợp đúng trước khi cân nhắc hiệu năng.
12. **Có phép toán chuyên biệt sẵn không?** `IntStream.sum()`, `max()`, `min()`, `Collectors.joining()` thường rõ ràng hơn accumulator tự viết.

Đặc biệt, **đừng xem việc Java biên dịch được một lambda là bằng chứng phép toán phù hợp với reduction**. Compiler chỉ xác nhận kiểu của `BinaryOperator`/`BiFunction`, không chứng minh tính kết hợp hay identity đúng.

## 13. Các lỗi phổ biến và cách sửa

| Sai lầm | Vì sao có vấn đề? | Thay bằng gì? |
|---|---|---|
| `reduce(0, (a,b)->a-b)` để tính “hiệu liên tiếp” | Identity không đúng và phép trừ không kết hợp | Vòng lặp rõ thứ tự hoặc `initial - sum(charges)` |
| `parallel().reduce((a,b)->a-b)` | Nhóm lại kết quả đổi | Chuyển mô hình về phép cộng hoặc giảm tuần tự theo thuật toán khác |
| Cho rằng bỏ identity sẽ sửa phép trừ | `reduce(BinaryOperator)` vẫn cần kết hợp | Đừng dùng phép trừ làm accumulator chung |
| Chọn `0` cho `reduce(max)` trên tập toàn số âm | `0` làm sai kết quả tối đa | `Integer.MIN_VALUE` hoặc `max()` trả Optional |
| Chỉ kiểm tra một ví dụ hai phần tử | Không phát hiện thay đổi dấu ngoặc | Dùng ba phần tử và hai cách nhóm |
| Dùng `StringBuilder.append` trong `reduce` với identity mutable | Có thể làm hỏng việc gộp song song | `Collectors.joining()` |
| Dùng phép cộng `double` rồi đòi kết quả bit-for-bit bất biến | Floating point có rounding | Kỹ thuật cộng có kiểm soát/kiểu dữ liệu chính xác hơn |
| Trộn accumulator cộng với combiner trừ | Không tương thích trong overload ba đối số | Dùng combiner cộng |
| Tưởng associative nghĩa là commutative | Nối chuỗi associative nhưng không commutative | Phân biệt đổi dấu ngoặc và đổi thứ tự |
| Kỳ vọng `parallel()` luôn nhanh hơn | Phân mảnh, phối hợp và kết hợp có chi phí | Đo hiệu năng; ưu tiên correctness |
| Sửa mutable external state trong accumulator | Non-interference/stateless bị vi phạm | Kết hợp giá trị bất biến hoặc `collect` |
| Không xử lý stream rỗng | Kết quả có thể là identity hoặc `Optional.empty()` | Kiểm tra yêu cầu nghiệp vụ về dữ liệu rỗng |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Phát biểu chính xác của tính kết hợp là gì? Nó khác tính giao hoán thế nào?

**Câu 2.** Với ba số `10,3,2`, tính `(10-3)-2` và `10-(3-2)`. Điều này cho biết gì về phép trừ?

**Câu 3.** Vì sao `0` là identity của phép cộng nhưng không phải identity hai phía của phép trừ?

**Câu 4.** `Stream.of(10,3,2).reduce(0, (a,b)->a-b)` trong pipeline tuần tự minh họa cho kết quả nào? Có nên dùng trong parallel reduction không?

**Câu 5.** `Stream.of(10,3,2).reduce((a,b)->a-b)` có hợp đồng associativity đúng chưa khi đã bỏ identity?

**Câu 6.** Vì sao phép nối chuỗi có thể dùng với `reduce` dù `"ab" != "ba"`?

**Câu 7.** Trong overload `reduce(identity, accumulator, combiner)`, tại sao combiner cần tương thích accumulator?

**Câu 8.** Muốn tính `budget - tổng chi phí`, nên giảm theo phép toán nào?

**Câu 9.** Stream rỗng cho kết quả gì với `reduce(0,Integer::sum)` và `reduce(Integer::sum)`?

**Câu 10.** Vì sao phép cộng `double` có thể khác nhau ở phần thấp của kết quả khi thay đổi cách nhóm?

**Đáp án:**

1. Associativity là `(a⊕b)⊕c = a⊕(b⊕c)`; commutativity là `a⊕b = b⊕a`.
2. Lần lượt `5` và `9`; phép trừ không kết hợp.
3. `0+x=x` và `x+0=x`, nhưng `0-x=-x` khác `x` khi `x≠0`.
4. `-15` trong ví dụ tuần tự; không dùng như một associative accumulator để giảm song song.
5. Chưa; điều kiện tính kết hợp vẫn bắt buộc.
6. Nối chuỗi giữ thứ tự các phần tử nhưng có thể đổi cách nhóm; nó associative, không commutative.
7. Để gộp các phần tính riêng cho ra cùng kết quả logic như tích lũy tuần tự.
8. Cộng các chi phí bằng `sum/reduce(Integer::sum)` rồi trừ tổng khỏi budget.
9. Lần lượt `0` và `Optional.empty()`.
10. Do IEEE 754 làm tròn sau mỗi phép cộng; thay dấu ngoặc có thể thay kết quả trung gian và kết quả cuối.

## 15. Nguồn tham khảo chính thức

- [Java SE 17 API — Stream.reduce](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): hợp đồng `reduce`, yêu cầu tính kết hợp, identity và overload có combiner.
- [Java SE 17 API — IntStream.reduce](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html): biến thể reduction primitive `int`.
- [Java SE 17 API — BinaryOperator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/BinaryOperator.html): kiểu hàm hai tham số cùng kiểu đầu ra.
- [Java SE 17 API — Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html): các collector như `joining` và `toCollection` khi cần tích lũy mutable.
- [Java SE 17 API — Stream package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html): đặc tính giảm, tính độc lập của callback và lưu ý với parallel stream.

**Ghi nhớ:** Phép toán đưa vào `reduce` phải **có tính kết hợp**; overload có identity còn yêu cầu **identity phù hợp**. Phép trừ `a-b` thường **không kết hợp** và `0` không phải identity hai phía, nên những lời gọi reduce dùng phép trừ không phù hợp để gộp tùy ý hoặc chạy song song. Nếu bài toán là **giá trị ban đầu trừ tổng các khoản**, hãy **cộng các khoản trước rồi trừ một lần sau**; nếu bài toán yêu cầu cập nhật tuần tự từng bước, hãy dùng vòng lặp mô tả rõ thứ tự.