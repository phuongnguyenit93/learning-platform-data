# Quy tắc đảo dấu khi đổi vị trí hai đối tượng trong thứ tự tự nhiên của Java

## 1. Phát biểu quy tắc: đổi vị trí thì đổi **dấu** kết quả so sánh

Trong Java, một lớp triển khai `Comparable<T>` để định nghĩa **thứ tự tự nhiên** (*natural ordering*) giữa những đối tượng có thể so sánh với nhau. Phương thức cốt lõi là:

```java
public int compareTo(T other)
```

Giá trị trả về là một số `int` có ý nghĩa qua **dấu**, không phải độ lớn tuyệt đối:

| `a.compareTo(b)` | Diễn giải |
| --- | --- |
| Nhỏ hơn `0` | `a` đứng trước `b` trong thứ tự tự nhiên |
| Bằng `0` | Hai đối tượng **tương đương theo thứ tự** (*compare-equivalent*) |
| Lớn hơn `0` | `a` đứng sau `b` trong thứ tự tự nhiên |

Một quy tắc bắt buộc của hợp đồng `Comparable` là **đảo dấu khi đổi vị trí hai đối tượng**:

```text
sgn(a.compareTo(b)) == -sgn(b.compareTo(a))
```

Trong đó `sgn(n)` bằng `-1` nếu `n < 0`, `0` nếu `n == 0`, `1` nếu `n > 0`. Trong Java dùng `Integer.signum(n)` để lấy dấu một cách rõ ràng.

Ví dụ, nếu `a.compareTo(b)` là số âm thì `b.compareTo(a)` phải là số dương; nếu một chiều trả về `0` thì chiều còn lại **cũng phải trả về `0`**. Quy tắc này có thể gọi là **tính phản đối xứng theo dấu** (*sign antisymmetry*), khác với khái niệm phản đối xứng của quan hệ `≤` trong toán học và khác với tính đối xứng của `equals()`.

**Điểm hay bị nhầm:** hợp đồng yêu cầu *đổi dấu*, **không bắt buộc đổi đúng trị số**. Nếu `a.compareTo(b) == -8`, chiều ngược lại được phép trả về `1`, `7` hoặc bất kỳ số dương nào khác; nó không nhất thiết phải bằng `8`.

Trong các ví dụ và công thức ở đây, `a` và `b` là những đối tượng khác `null` thuộc miền so sánh mà kiểu dữ liệu đã công bố. Nếu lớp không hỗ trợ so sánh với một loại đối tượng khác, cách xử lý ngoại lệ cũng phải tương thích với hợp đồng của `Comparable`. Một đối tượng `null` không phải giá trị hợp lệ của thứ tự tự nhiên thông thường; lời gọi `someObject.compareTo(null)` theo hợp đồng phải ném `NullPointerException`.

## 2. Vì sao quy tắc này quan trọng?

Giả sử hai điểm số: `low = 5` và `high = 10`. Ta kỳ vọng:

```text
low.compareTo(high)  < 0
high.compareTo(low)  > 0
```

Nếu **cả hai** đều trả về giá trị âm, thuật toán sắp xếp sẽ nhận được thông tin mâu thuẫn: `low` đứng trước `high`, nhưng `high` cũng đứng trước `low`. Kết quả có thể là thứ tự không nhất quán, tìm kiếm sai kỳ vọng hoặc lỗi từ các thuật toán sắp xếp khi hợp đồng `Comparator/Comparable` bị vi phạm.

Điều này ảnh hưởng trực tiếp đến:

- `Collections.sort`, `List.sort` và `Arrays.sort` khi dùng thứ tự tự nhiên;
- `TreeSet` và `TreeMap`, vì cây cân bằng cần kết quả so sánh nhất quán để xác định vị trí khóa/phần tử;
- Các thuật toán tìm kiếm nhị phân hoặc quy tắc chọn phần tử nhỏ nhất/lớn nhất dựa trên thứ tự;
- Bất kỳ phép so sánh nào được triển khai lại ở cả hai hướng.

Một bộ so sánh đúng phải giữ đồng thời ba nhóm quy tắc: **đảo dấu**, **bắc cầu**, và **nhất quán của kết quả so sánh bằng 0 với các đối tượng thứ ba** (giải thích tại mục 5). Chỉ chứng minh được quy tắc đảo dấu chưa đủ để đảm bảo toàn bộ hợp đồng.

## 3. Cách triển khai an toàn: `Integer.compare`, `Long.compare`, `Comparator.comparing`

Với trường số nguyên, cách thông dụng và an toàn nhất là dùng phương thức so sánh chuẩn:

```java
@Override
public int compareTo(Score other) {
    Objects.requireNonNull(other, "other");
    return Integer.compare(this.points, other.points);
}
```

Đây là **phương thức nằm trong lớp `Score` có trường `int points`**, chưa phải chương trình Java độc lập. `Integer.compare` so sánh dựa trên thứ tự số nguyên đúng nghĩa và trả về `-1`, `0` hoặc `1`. Nó không gặp lỗi tràn do tự lấy hiệu.

Nếu so sánh nhiều trường, ví dụ xếp hạng theo điểm tăng dần, sau đó theo mã học viên, có thể dùng bộ so sánh có thứ tự ưu tiên rõ ràng:

```java
record Student(int points, String id) implements Comparable<Student> {
    @Override
    public int compareTo(Student other) {
        Objects.requireNonNull(other, "other");
        int byPoints = Integer.compare(points, other.points);
        if (byPoints != 0) return byPoints;
        return id.compareTo(other.id);
    }
}
```

Đây là **khai báo record minh họa**, có thể đặt độc lập trong tệp thích hợp nếu bổ sung import `java.util.Objects`. Với `id` là chuỗi không null và không thay đổi, so sánh theo điểm trước, rồi theo `id` giúp tạo thứ tự từ điển: mọi trường hợp đối tượng có điểm bằng nhau đều được phân định nhất quán theo mã. `String.compareTo` có thể trả về số có độ lớn lớn hơn 1, nhưng dấu vẫn có đúng ý nghĩa.

Trong API chuyên dùng cho `Comparator`, cũng có thể viết:

```java
Comparator<Student> byPointsThenId =
        Comparator.comparingInt(Student::points)
                  .thenComparing(Student::id);
```

Đây là một biểu thức tạo `Comparator` cho `Student`, cần `import java.util.Comparator`. `Comparator` có quy tắc đảo dấu tương ứng đối với `compare(a,b)` và `compare(b,a)`, dù không cần thay đổi thứ tự tự nhiên mặc định của lớp.

Nếu sắp xếp giảm dần, ưu tiên `Comparator.reversed()` hoặc đổi **thứ tự đối số của phương thức compare chuẩn** thay vì tự đảo dấu một số nguyên tùy ý:

```java
int descending = Integer.compare(other.points, this.points);
```

Đoạn này nằm trong ngữ cảnh có hai giá trị `points`. Việc viết `-someCompareResult` chỉ luôn an toàn khi biết chắc kết quả không thể bằng `Integer.MIN_VALUE`. Với một phương thức `compareTo` tùy ý có quyền trả về số âm đó, phủ định có thể tràn số nguyên và **không đổi dấu**.

## 4. Ví dụ sai: dùng phép trừ để cài đặt `compareTo()`

Một lỗi thường gặp là:

```java
@Override
public int compareTo(BrokenScore other) {
    return points - other.points; // Không an toàn khi int tràn!
}
```

Đây là **phương thức trong lớp `BrokenScore`** của chương trình hoàn chỉnh ở mục 6. Khi hiệu toán học vượt giới hạn của `int`, phép trừ Java bị tràn theo số nguyên 32 bit và kết quả có thể sai dấu.

Hãy xét hai đối tượng có giá trị `0` và `Integer.MIN_VALUE`, tức `-2147483648`:

- Về mặt toán học, `0 > -2147483648` nên so `0` với số nhỏ nhất phải cho **dấu dương**.
- Nhưng phép tính `0 - Integer.MIN_VALUE` trên `int` tràn và cho `-2147483648`, tức **dấu âm**.
- Chiều ngược lại, `Integer.MIN_VALUE - 0` cũng bằng `-2147483648`, **vẫn dấu âm**.
- Như vậy `sgn(a.compareTo(b)) == -sgn(b.compareTo(a))` bị vi phạm: cùng một cặp lại cho hai số âm ở cả hai hướng.

Một lựa chọn chính xác là thay biểu thức trừ bằng `Integer.compare(points, other.points)`. Với `long` dùng `Long.compare`; với `double` và `float`, dùng `Double.compare`/`Float.compare` để có quy tắc chuẩn cho `NaN`, vô cực và `-0.0` thay vì tự viết biểu thức trừ hoặc chuỗi điều kiện đơn giản. So sánh số thực cần hiểu thứ tự do API định nghĩa, vì nó có thể khác phép toán `<`, `>` thông thường ở các giá trị đặc biệt.

Một lỗi khác là viết:

```java
return points > other.points ? 1 : -1;
```

Dòng này trả về `-1` kể cả khi hai điểm bằng nhau, làm mất trường hợp `0`. Nếu dùng cùng hai giá trị bằng nhau ở cả hai chiều, cả hai kết quả là `-1` nên quy tắc đảo dấu cũng sai. Khi thực hiện so sánh nhiều trường, luôn xử lý trường hợp bằng nhau rồi mới xét khóa so sánh tiếp theo.

## 5. Quy tắc đảo dấu nằm trong một hợp đồng lớn hơn

Đảo dấu là điều kiện bắt buộc nhưng chưa đủ để có thứ tự hợp lệ. Cần bảo đảm **tính bắc cầu** (`a > b` và `b > c` thì `a > c`) và **tính nhất quán của nhóm tương đương** (khi `a.compareTo(b) == 0`, hai giá trị phải có cùng dấu khi so với mọi `c` hợp lệ). Một comparator có thể đối dấu đúng theo từng cặp nhưng vẫn tạo vòng `a < b < c < a`.

Khác với `equals` (hai chiều cho cùng boolean), `compareTo` dùng **hai dấu ngược nhau** khi đổi vị trí, ngoại trừ trường hợp cùng trả `0`. Java khuyến nghị `compareTo == 0` nhất quán với `equals`, nhưng đây là yêu cầu thiết kế bổ sung, không phải nội dung của quy tắc đảo dấu. Ví dụ `BigDecimal("2.0")` và `BigDecimal("2.00")` cùng vị trí thứ tự nhưng khác `equals`; điều này tự nó không vi phạm quy tắc đảo dấu.

Để phép so sánh đáng tin cậy qua nhiều lượt, giữ các trường dùng xác định thứ tự ổn định khi đối tượng nằm trong `TreeSet`/`TreeMap`. Phần này định vị các quy tắc liên quan; bài về **bắc cầu**, **giá trị thứ ba** và **equals** phân tích riêng phản ví dụ cùng phép kiểm thử.

## 6. Chương trình Java 17+ hoàn chỉnh để kiểm chứng

Lưu toàn bộ tệp dưới tên **`CompareSignDemo.java`**. Chương trình dùng `record Score` để triển khai `Comparable<Score>` an toàn bằng `Integer.compare`, dùng `BrokenScore` cố ý minh họa phép trừ tràn, và kiểm thử mọi cặp trong một tập giá trị biên.

```java
import java.util.*;

public class CompareSignDemo {
    record Score(int points) implements Comparable<Score> {
        @Override
        public int compareTo(Score other) {
            Objects.requireNonNull(other, "other");
            return Integer.compare(points, other.points);
        }
    }

    static final class BrokenScore implements Comparable<BrokenScore> {
        private final int points;

        BrokenScore(int points) {
            this.points = points;
        }

        @Override
        public int compareTo(BrokenScore other) {
            return points - other.points; // Lỗi cố ý: overflow.
        }
    }

    static void checkSignRule(Score[] scores) {
        for (Score left : scores) {
            for (Score right : scores) {
                int lr = Integer.signum(left.compareTo(right));
                int rl = Integer.signum(right.compareTo(left));

                if (lr != -rl) {
                    throw new AssertionError("sign rule broken");
                }
            }
        }
    }

    public static void main(String[] args) {
        Score low = new Score(Integer.MIN_VALUE);
        Score zero = new Score(0);
        Score equal = new Score(0);

        System.out.println("low vs zero = " + low.compareTo(zero));
        System.out.println("zero vs low = " + zero.compareTo(low));
        System.out.println("zero vs equal = " + zero.compareTo(equal));

        checkSignRule(new Score[] {
                low, new Score(-7), zero,
                new Score(17), new Score(Integer.MAX_VALUE)
        });
        System.out.println("correct sign rule = PASS");

        BrokenScore badZero = new BrokenScore(0);
        BrokenScore badLow = new BrokenScore(Integer.MIN_VALUE);
        int brokenForward = badZero.compareTo(badLow);
        int brokenReverse = badLow.compareTo(badZero);

        System.out.println("broken zero vs min = " + brokenForward);
        System.out.println("broken min vs zero = " + brokenReverse);
        System.out.println("broken sign rule = "
                + (Integer.signum(brokenForward)
                        == -Integer.signum(brokenReverse)));

        TreeSet<Score> set = new TreeSet<>();
        set.add(new Score(4));
        set.add(new Score(-2));
        set.add(new Score(4));
        System.out.println("sorted set = " + set);
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```bash
javac CompareSignDemo.java
java CompareSignDemo
```

Kết quả chính xác của chương trình:

```text
low vs zero = -1
zero vs low = 1
zero vs equal = 0
correct sign rule = PASS
broken zero vs min = -2147483648
broken min vs zero = -2147483648
broken sign rule = false
sorted set = [Score[points=-2], Score[points=4]]
```

Giải thích:

1. `low.compareTo(zero)` trả `-1` vì `Integer.MIN_VALUE < 0`; đảo thứ tự thành `zero.compareTo(low)` trả `1`. Hai dấu đối nhau.
2. `zero.compareTo(equal)` trả `0` vì cùng điểm số. Đảo thứ tự vẫn cho `0`.
3. `checkSignRule` duyệt **toàn bộ 25 cặp** trong 5 giá trị, bao gồm cặp có cùng tham chiếu, cùng giá trị, âm/dương, và các biên `Integer.MIN_VALUE` / `Integer.MAX_VALUE`. Nếu có cặp sai quy tắc, hàm ném `AssertionError`; vì không có lỗi nên in `PASS`.
4. `BrokenScore` dùng phép trừ. `0 - Integer.MIN_VALUE` bị tràn thành `-2147483648`, trong khi chiều ngược lại cũng cho cùng số âm. Do đó `broken sign rule = false`. Đây là ví dụ có kết quả xác định, không phụ thuộc ngẫu nhiên.
5. `TreeSet` chứa các `Score` theo thứ tự tăng dần. Hai đối tượng có `points == 4` được `compareTo` đánh giá bằng 0, nên cây chỉ giữ một phần tử tương đương theo thứ tự. `record` sinh `toString` hiển thị dạng `Score[points=...]`.

**Lưu ý khi kiểm thử:** Đừng viết khẳng định `left.compareTo(right) == -right.compareTo(left)` cho một implementation tổng quát, vì việc phủ định `Integer.MIN_VALUE` bị tràn và hợp đồng chỉ quy định dấu. Cách đúng là so `Integer.signum(left.compareTo(right))` với `-Integer.signum(right.compareTo(left))`. `Integer.signum` chỉ cho giá trị trong {-1, 0, 1} nên phủ định an toàn.

## 7. Những lỗi phổ biến khi viết và sử dụng `compareTo()`

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| `return this.x - other.x;` với `int` | Tràn số nguyên làm sai dấu, có thể vi phạm đảo dấu | `Integer.compare(this.x, other.x)` |
| Dùng `-compareResult` với kết quả có thể bằng `Integer.MIN_VALUE` | Không đổi được dấu vì tràn | Dùng `Integer.signum` để kiểm tra; đổi thứ tự tham số `compare` hoặc `Comparator.reversed` để đảo thứ tự |
| Chỉ trả `1` hoặc `-1`, không có trường hợp `0` | Hai giá trị bằng nhau vẫn bị đặt trước nhau ở cả hai chiều | Xử lý trường hợp bằng nhau; dùng API compare chuẩn |
| Giả sử kết quả chỉ là `-1`, `0`, `1` | Sai với các bộ so sánh hợp lệ trả `-8`, `42`,... | Chỉ kiểm tra dấu: `< 0`, `== 0`, `> 0` |
| `compareTo` phụ thuộc dữ liệu thay đổi khi đã đưa vào `TreeSet` | Vị trí lưu trong cây không còn phù hợp thứ tự mới | Dùng khóa bất biến hoặc xóa và thêm lại |
| Dùng cùng kiểu dữ liệu nhưng tiêu chí so sánh không bắc cầu | Thuật toán sắp xếp nhận thứ tự mâu thuẫn | Kiểm thử cả bộ ba và đặt tiêu chí từ điển nhất quán |
| `compareTo` trả `0` cho hai đối tượng mà `equals` coi là khác | `TreeSet/TreeMap` có thể gộp chúng theo thứ tự | Cố gắng nhất quán với `equals` hoặc ghi rõ ngoại lệ |
| Không xử lý `null` hoặc kiểu không thể so sánh | Có thể ném ngoại lệ sai loại hoặc hành vi khó đoán | Theo hợp đồng `Comparable`: `NullPointerException` khi so với null; loại không tương thích có thể gây `ClassCastException` |

## 8. Bài tự kiểm tra và quy trình rà soát

**Tình huống A.** `a.compareTo(b)` trả `-12`. Chiều đảo `b.compareTo(a)` có bắt buộc trả `12` không?

Không. Nó chỉ phải **dương**, ví dụ `1` hoặc `12`, miễn là toàn bộ các quy tắc còn lại của thứ tự cũng được tuân thủ.

**Tình huống B.** Với `a = 0` và `b = Integer.MIN_VALUE`, code `return a - b;` cho kết quả nào?

Kết quả `int` bị tràn thành `Integer.MIN_VALUE` (âm), dù 0 lớn hơn giá trị nhỏ nhất. Chiều ngược lại cũng âm, trực tiếp vi phạm quy tắc đảo dấu.

**Tình huống C.** Nếu `a.compareTo(b) == 0` và `b.compareTo(c) > 0`, điều kiện nhất quán với giá trị 0 suy ra điều gì?

`a.compareTo(c)` cũng phải có **dấu dương**. Hai phần tử tương đương theo thứ tự phải so sánh với bên thứ ba theo cùng cách. Nếu kết quả lại âm hoặc bằng 0, implementation vi phạm hợp đồng.

**Tình huống D.** Nếu `a.compareTo(b) == 0` nhưng `a.equals(b)` là `false`, có tự động làm sai quy tắc đảo dấu không?

Không. Quy tắc đảo dấu vẫn có thể được giữ. Nhưng thứ tự đó **không nhất quán với `equals`**, điều thường gây bất ngờ ở `TreeSet` và `TreeMap`.

Khi review một implementation `compareTo`, hãy làm lần lượt: xác định tất cả trường và thứ tự ưu tiên khi so; dùng `Integer.compare`/`Long.compare` hoặc API có hợp đồng rõ; kiểm tra trường hợp 0; kiểm thử **hai chiều cho mọi cặp**; kiểm thử **bắc cầu với bộ ba**; kiểm thử các giá trị biên và tình huống dữ liệu có thể thay đổi; cuối cùng xác nhận quan hệ giữa `compareTo == 0` và `equals` có đúng với thiết kế khóa/tập hay không.

**Ghi nhớ:** `Comparable.compareTo` trả về một **dấu thứ tự**, không phải khoảng cách giữa hai giá trị. Đổi vị trí đối tượng phải đổi dấu kết quả; dùng phép so sánh chuẩn và kiểm tra toàn bộ hợp đồng để giữ thứ tự tự nhiên nhất quán.