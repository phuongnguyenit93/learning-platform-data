# Tính bắc cầu của quan hệ thứ tự trong Java

## 1. Tính bắc cầu nghĩa là gì?

Khi các đối tượng có **thứ tự tự nhiên** thông qua `Comparable<T>.compareTo(T)`, thứ tự phải có quy tắc nhất quán. Một trong những yêu cầu quan trọng nhất là **tính bắc cầu (transitivity)**:

> Nếu `a` đứng sau `b` và `b` đứng sau `c`, thì `a` cũng phải đứng sau `c`.

Với kết quả `compareTo`, điều đó được diễn đạt bằng dấu:

~~~text
a.compareTo(b) > 0
b.compareTo(c) > 0
----------------
a.compareTo(c) > 0
~~~

Tương tự, nếu `a.compareTo(b) < 0` và `b.compareTo(c) < 0` thì `a.compareTo(c) < 0`. Ở đây **số âm** nghĩa là đứng trước, **0** nghĩa là tương đương theo thứ tự và **số dương** nghĩa là đứng sau; Java không yêu cầu kết quả đúng bằng `-1` hoặc `1`.

Ví dụ, nếu ba điểm số có quan hệ `70 < 80 < 90`, chương trình không được có một quy tắc so sánh làm `90 < 70`. Nếu điều đó xảy ra, không thể sắp ba giá trị vào một trật tự tuyến tính nhất quán.

Tính bắc cầu cần được bảo đảm cho **mọi bộ ba đối tượng hợp lệ**, không chỉ trong một vài bộ dữ liệu kiểm thử. Nó quan trọng với việc sắp xếp, tìm kiếm nhị phân và các tập/bản đồ có thứ tự như `TreeSet`, `TreeMap`.

## 2. Hợp đồng của compareTo còn yêu cầu những gì?

Để định nghĩa một thứ tự tự nhiên đúng, chỉ kiểm tra riêng bắc cầu chưa đủ. Theo hợp đồng `Comparable`, cần xét thêm các quy tắc sau.

| Yêu cầu | Diễn giải | Ví dụ |
| --- | --- | --- |
| Đổi chiều so sánh | `sgn(x.compareTo(y)) == -sgn(y.compareTo(x))` | Nếu x đứng sau y thì y đứng trước x |
| Bắc cầu | Nếu `x > y` và `y > z` thì `x > z` | 90 > 80 > 70 ⇒ 90 > 70 |
| Đối tượng tương đương theo thứ tự | Nếu `x.compareTo(y) == 0` thì với mọi z, `sgn(x.compareTo(z)) == sgn(y.compareTo(z))` | Hai giá trị ngang hạng phải có cùng quan hệ trước/sau với mọi giá trị khác |
| Phù hợp với `equals` | Nên có `x.compareTo(y) == 0` khi và chỉ khi `x.equals(y)` | Các collection theo thứ tự xử lý việc trùng khóa theo `compareTo` |

Ký hiệu `sgn` chỉ **dấu** của một số nguyên: âm thành `-1`, bằng không thành `0`, dương thành `1`. Điều kiện đổi chiều ngụ ý `x.compareTo(x)` phải bằng `0`.

Việc **nhất quán với `equals`** được khuyến nghị mạnh mẽ nhưng không bắt buộc trong mọi lớp `Comparable`. Ví dụ nổi tiếng là `BigDecimal`: `new BigDecimal("4.0").compareTo(new BigDecimal("4.00")) == 0`, trong khi `equals` trả `false` vì biểu diễn scale khác nhau. Điều này không vi phạm tính bắc cầu; nó cho thấy **tương đương theo thứ tự** và **bình đẳng theo `equals`** là hai quan hệ có thể khác nhau.

Điều kiện “bằng 0 thì cùng quan hệ với mọi z” đặc biệt quan trọng: nếu một đối tượng được coi là bằng hạng với đối tượng thứ hai nhưng lại đứng khác phía so với đối tượng thứ ba, thuật toán sắp xếp sẽ nhận các kết quả mâu thuẫn.

## 3. Xây dựng thứ tự tự nhiên đúng bằng các khóa so sánh

Giả sử một kết quả thi có hai thuộc tính:

- `score`: điểm, tăng dần.
- `candidate`: tên, dùng để phân xử khi cùng điểm theo thứ tự từ điển.

Một thứ tự rõ ràng là **so điểm trước; nếu điểm bằng nhau mới so tên**. Đây là cách so sánh theo thứ tự từ điển của cặp khóa `(score, candidate)`. Khi mỗi thành phần dùng một quan hệ thứ tự nhất quán, phép so theo thứ tự ưu tiên cố định cũng giữ tính bắc cầu.

Một số quy tắc hữu ích:

1. Chọn các trường định nghĩa thứ tự và **thứ tự ưu tiên của các trường** ngay từ đầu.
2. Dùng `Integer.compare`, `Long.compare`, `String.compareTo` hoặc `Comparator.comparing(...).thenComparing(...)` thay vì tự tính dấu bằng phép trừ dễ tràn số.
3. Nếu khóa chính khác nhau, trả về kết quả của khóa chính ngay; chỉ xét khóa phụ khi khóa chính bằng nhau.
4. Đảm bảo các trường tham gia so sánh có trạng thái ổn định khi đối tượng đang nằm trong `TreeSet` hoặc làm khóa của `TreeMap`.
5. Xác định rõ `null` hợp lệ hay không. Nếu một trường có thể `null`, hãy dùng quy tắc `nullsFirst` hoặc `nullsLast` nhất quán, hoặc xác thực không được `null` khi tạo.

## 4. Ví dụ Java 17 chạy được

Chương trình gồm một lớp `ExamResult` có thứ tự tự nhiên bắc cầu, một comparator mang tính vòng tròn để minh họa vi phạm, và một phép so sai dùng phép trừ có nguy cơ tràn `int`.

Lưu vào tệp **TransitiveOrderDemo.java**:

~~~java
import java.util.Comparator;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class TransitiveOrderDemo {
    static final class ExamResult implements Comparable<ExamResult> {
        private final int score;
        private final String candidate;

        ExamResult(int score, String candidate) {
            this.score = score;
            this.candidate = Objects.requireNonNull(candidate, "candidate");
        }

        @Override
        public int compareTo(ExamResult other) {
            int byScore = Integer.compare(score, other.score);
            if (byScore != 0) {
                return byScore;
            }
            return candidate.compareTo(other.candidate);
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof ExamResult that
                            && score == that.score
                            && candidate.equals(that.candidate));
        }

        @Override
        public int hashCode() {
            return Objects.hash(score, candidate);
        }

        @Override
        public String toString() {
            return candidate + ":" + score;
        }
    }

    enum Move { ROCK, PAPER, SCISSORS }

    static final Comparator<Move> CYCLIC = (left, right) -> {
        if (left == right) {
            return 0;
        }
        boolean leftWins =
                (left == Move.ROCK && right == Move.SCISSORS)
                || (left == Move.SCISSORS && right == Move.PAPER)
                || (left == Move.PAPER && right == Move.ROCK);
        return leftWins ? 1 : -1;
    };

    public static void main(String[] args) {
        ExamResult a = new ExamResult(70, "An");
        ExamResult b = new ExamResult(80, "Binh");
        ExamResult c = new ExamResult(90, "Chi");

        System.out.println("a < b: " + (a.compareTo(b) < 0));
        System.out.println("b < c: " + (b.compareTo(c) < 0));
        System.out.println("a < c: " + (a.compareTo(c) < 0));

        ExamResult tiedA = new ExamResult(80, "An");
        System.out.println("tie by name: "
                + (tiedA.compareTo(b) < 0));
        System.out.println("zero agrees with equals: "
                + (b.compareTo(new ExamResult(80, "Binh")) == 0
                        && b.equals(new ExamResult(80, "Binh"))));

        Set<ExamResult> results = new TreeSet<>();
        results.add(c);
        results.add(a);
        results.add(b);
        results.add(new ExamResult(80, "Binh"));
        System.out.println("TreeSet: " + results);

        System.out.println("rock > scissors: "
                + (CYCLIC.compare(Move.ROCK, Move.SCISSORS) > 0));
        System.out.println("scissors > paper: "
                + (CYCLIC.compare(Move.SCISSORS, Move.PAPER) > 0));
        System.out.println("rock > paper: "
                + (CYCLIC.compare(Move.ROCK, Move.PAPER) > 0));

        int high = Integer.MAX_VALUE;
        int middle = 0;
        int low = -1;
        System.out.println("subtract high > middle: "
                + (high - middle > 0));
        System.out.println("subtract middle > low: "
                + (middle - low > 0));
        System.out.println("subtract high > low: "
                + (high - low > 0));
        System.out.println("Integer.compare high > low: "
                + (Integer.compare(high, low) > 0));
    }
}
~~~

Biên dịch/chạy trên JDK 17 trở lên:

~~~bash
javac TransitiveOrderDemo.java
java TransitiveOrderDemo
~~~

Kết quả chuẩn:

~~~text
a < b: true
b < c: true
a < c: true
tie by name: true
zero agrees with equals: true
TreeSet: [An:70, Binh:80, Chi:90]
rock > scissors: true
scissors > paper: true
rock > paper: false
subtract high > middle: true
subtract middle > low: true
subtract high > low: false
Integer.compare high > low: true
~~~

### Giải thích

- Ba `ExamResult` có điểm `70 < 80 < 90`, do đó `a < b`, `b < c` và `a < c` đều đúng. Kết quả tuân quy tắc bắc cầu.
- Khi điểm đều là `80`, chương trình dùng tên làm khóa thứ cấp. Tên `"An"` đứng trước `"Binh"`, nên phép phân xử không mâu thuẫn với quan hệ theo điểm.
- `TreeSet` sử dụng `compareTo` để sắp xếp và xác định tính trùng nhau theo thứ tự. Bản sao `ExamResult(80, "Binh")` không tạo thêm một phần tử mới; kết quả duyệt được hiển thị tăng dần.
- `ExamResult` là `final`, các trường tham gia so sánh là `final`; `equals` và `hashCode` dùng chính cặp `(score, candidate)`, nên các hợp đồng nhất quán với nhau.
- `CYCLIC` coi ROCK đứng sau SCISSORS, SCISSORS đứng sau PAPER, nhưng PAPER đứng sau ROCK. Nó thể hiện logic trò chơi kéo–búa–bao, **không phải một quan hệ thứ tự tuyến tính**. Hai so sánh đầu là `true` nhưng kết luận bắc cầu là `false`.
- Phép trừ `high - low` làm tràn `int` vì `Integer.MAX_VALUE - (-1)` vượt giới hạn số nguyên. Kết quả dấu bị đảo, tạo bộ ba `high > middle > low` nhưng phép trừ lại báo `high` không lớn hơn `low`. `Integer.compare` xử lý trường hợp này đúng.

Ví dụ cố ý **không đưa comparator vòng tròn vào `TreeSet`**: nếu vi phạm hợp đồng, những kết quả sắp xếp/tìm kiếm sẽ không còn đáng tin. Việc không thấy lỗi hoặc ngoại lệ trong một lần chạy không chứng minh comparator hợp lệ.

## 5. Vì sao quy tắc “kéo–búa–bao” không thể là thứ tự tự nhiên?

Quan hệ “thắng” trong kéo–búa–bao có vòng:

~~~text
ROCK > SCISSORS
SCISSORS > PAPER
PAPER > ROCK
~~~

Nếu cố hiểu dấu `>` là “đứng sau theo thứ tự tự nhiên”, từ hai dòng đầu bắt buộc suy ra `ROCK > PAPER`. Nhưng dòng cuối khẳng định `PAPER > ROCK`. Vì vậy quan hệ này **không bắc cầu** và không thể sử dụng làm thứ tự tự nhiên đúng hợp đồng.

Một quan hệ nghiệp vụ có thể hợp lý mà **không phải quan hệ thứ tự**. Nếu muốn biểu diễn “đối thủ nào thắng”, nên dùng một phương thức như `beats(other)` trả `boolean` hoặc một kiểu kết quả chiến thắng riêng. Chỉ tạo `Comparator` khi thật sự có một thứ tự nhất quán mà thuật toán sắp xếp có thể dùng.

Nếu muốn hiển thị ba lựa chọn theo một thứ tự cố định, có thể sắp bằng mã/thứ bậc được xác định trước (ví dụ ROCK, PAPER, SCISSORS). Thứ tự hiển thị đó khác với quan hệ ai thắng ai.

## 6. Tác động khi vi phạm tính bắc cầu

### 6.1. Sắp xếp

`Arrays.sort`, `List.sort` và `Collections.sort` dựa vào comparator hoặc `compareTo` biểu thị thứ tự nhất quán. Một comparator không bắc cầu có thể khiến kết quả khó dự đoán hoặc làm thuật toán sắp xếp phát hiện vi phạm và ném `IllegalArgumentException` trong một số trường hợp. **Không nên trông chờ JVM luôn ném ngoại lệ**: có khi dữ liệu nhỏ vẫn được sắp và trông có vẻ đúng, nhưng không có bảo đảm về trật tự hợp lệ đối với comparator sai.

### 6.2. TreeSet và TreeMap

`TreeSet` và `TreeMap` dùng quan hệ thứ tự để tổ chức, tìm kiếm và xác định các khóa được coi là tương đương. Vi phạm hợp đồng có thể làm `contains`, `get`, `remove` hoặc việc duyệt theo thứ tự đưa ra kết quả không phù hợp kỳ vọng. Các collection này giả định rằng kết quả so sánh đủ ổn định và nhất quán để tìm được một vị trí trong cây.

Đặc biệt, `TreeSet`/ `TreeMap` xem **`compare(a, b) == 0`** hoặc **`a.compareTo(b) == 0`** là quan hệ tương đương khi xác định phần tử/khóa trùng nhau. Nếu quan hệ này không phù hợp với `equals`, collection vẫn có thể hoạt động theo quy tắc so sánh nhưng vi phạm kỳ vọng của hợp đồng `Set`/`Map` tổng quát. Vì vậy, nên bảo đảm sự phù hợp với `equals` hoặc ghi rõ chủ ý khác biệt.

### 6.3. Tìm kiếm nhị phân

Thuật toán tìm kiếm nhị phân cần dãy được sắp đúng theo cùng quy tắc so sánh được dùng khi tìm. Một comparator không bắc cầu khiến việc chia đôi phạm vi tìm kiếm mất cơ sở: không thể tin rằng những phần tử ở phía trái hoặc phải đều có quan hệ nhất quán với khóa đích.

Không thể sửa một quan hệ sai bằng cách đảo dấu tùy tiện hoặc lặp lại phép so sánh nhiều lần. Cần sửa **định nghĩa thứ tự**.

## 7. Những cách viết compareTo dễ mắc lỗi

### 7.1. Trừ trực tiếp hai giá trị nguyên

~~~java
@Override
public int compareTo(Score other) {
    return score - other.score; // Có thể tràn int
}
~~~

Đây là **đoạn minh họa lỗi trong lớp Score giả định**, không phải chương trình độc lập. Nếu hiệu số tràn `int`, dấu kết quả có thể sai, kéo theo vi phạm quy tắc đổi chiều hoặc bắc cầu. Thay bằng:

~~~java
@Override
public int compareTo(Score other) {
    return Integer.compare(score, other.score);
}
~~~

Với `long` cũng nên dùng `Long.compare` thay vì ép hiệu số về `int`. Không viết comparator chỉ trả `0` khi hai số có cùng dấu vì cách đó làm các giá trị khác nhau có thể bị coi là ngang hạng và không tương thích với chính sách bình đẳng đã chọn.

### 7.2. So bằng dữ liệu thay đổi theo thời gian

Một phương thức `compareTo` đọc đồng hồ, gọi dịch vụ ngoài hoặc dựa trên trường được sửa trong lúc phần tử đã nằm trong `TreeSet` có thể trả kết quả khác nhau cho cùng cặp đối tượng. Đây là vấn đề về **tính nhất quán qua các lần so sánh**, có thể làm hỏng giả định tìm kiếm của cây dù công thức bắc cầu trông đúng trong từng thời điểm.

Hãy ưu tiên khóa xếp hạng ổn định. Nếu thứ tự cần thay đổi, xóa mục khỏi collection khi vẫn còn nhận diện được bằng trạng thái cũ, cập nhật dữ liệu, rồi chèn lại theo trạng thái mới; trong ứng dụng nhiều luồng cần phối hợp đồng bộ cho toàn thao tác.

### 7.3. Đảo thứ tự ưu tiên trường theo điều kiện khác nhau

Ví dụ, lúc so `a` với `b` thì ưu tiên điểm, lúc so `b` với `c` lại ưu tiên tên vì một cờ nghiệp vụ tùy đối tượng. Nếu việc chọn trường ưu tiên phụ thuộc **vào cặp đang so**, thay vì một thứ tự ưu tiên toàn cục nhất quán, có thể xuất hiện vòng `a < b < c < a`.

Giải pháp thường là chọn một tuple khóa cố định, chẳng hạn `(priority, createdAt, id)`, rồi so theo thứ tự từ trái sang phải. Việc thêm khóa `id` cuối cùng cũng có thể dùng để phá hòa khi cần **thứ tự toàn phần có tính xác định**, nhưng cần xác định rõ khóa nào là một phần của bình đẳng theo thứ tự.

### 7.4. Quên chính sách null

Theo `Comparable`, `compareTo(null)` thông thường ném `NullPointerException`, ngay cả khi `equals(null)` trả `false`. Nếu một **trường bên trong** có thể `null`, phải chọn cách xử lý tường minh trong comparator, ví dụ:

~~~java
Comparator<String> nullableNames =
        Comparator.nullsLast(String::compareTo);
~~~

Đây là **đoạn khai báo comparator**, không phải chương trình độc lập. Nó xếp `null` sau chuỗi không `null`. Dùng chính sách này nhất quán trong toàn bộ quy tắc sắp xếp; đừng ngẫu nhiên coi `null` nhỏ hơn trong một nhánh và lớn hơn trong nhánh khác.

## 8. Kiểm tra tính bắc cầu khi viết hoặc sửa một lớp Comparable

Một bộ kiểm thử nhỏ cần đối chiếu cả trường hợp thông thường lẫn các ranh giới:

1. **Đổi chiều:** với các cặp `a, b`, dấu của `a.compareTo(b)` phải đối nghịch dấu của `b.compareTo(a)`. Kiểm tra cả `a.compareTo(a) == 0`.
2. **Bắc cầu tăng và giảm:** với mọi bộ ba mẫu có `a < b < c`, kiểm tra `a < c`; và với `a > b > c`, kiểm tra `a > c`.
3. **Trường hợp ngang hạng:** nếu `a.compareTo(b) == 0`, hai đối tượng phải có cùng dấu so sánh với mọi `c` mẫu.
4. **Nhiều khóa:** tạo những cặp cùng khóa chính nhưng khác khóa phụ, và những cặp khác khóa chính. Bảo đảm phép phá hòa hoạt động theo thứ tự ưu tiên cố định.
5. **Giá trị biên:** số âm, `Integer.MIN_VALUE`, `Integer.MAX_VALUE`, chuỗi rỗng, `null` nếu thuộc tính cho phép.
6. **Sự nhất quán với equals:** kiểm tra `compareTo == 0` có phù hợp `equals` theo thiết kế không. Nếu chủ ý khác, viết rõ lý do và tác động tới `TreeSet`/`TreeMap`.
7. **Tính ổn định:** cùng các đối tượng không đổi phải cho dấu kết quả giống nhau qua nhiều lần so sánh.

Một hàm hỗ trợ kiểm tra có thể được viết trong lớp kiểm thử:

~~~java
static <T extends Comparable<? super T>> boolean transitiveLess(
        T a, T b, T c) {
    return !(a.compareTo(b) < 0 && b.compareTo(c) < 0)
            || a.compareTo(c) < 0;
}
~~~

Đây là **phương thức minh họa kiểm thử**, không phải chương trình độc lập. Nếu tiền đề `a < b` và `b < c` không đồng thời đúng, kiểm tra suy diễn này trả `true` vì không có vi phạm cho bộ ba đó. Để kiểm chứng đủ mạnh, cần tạo nhiều bộ ba bao gồm cả tiền đề đúng và đảo chiều. Kiểm thử theo tính chất (property-based testing) có thể hỗ trợ tạo dữ liệu ngẫu nhiên và giá trị biên, nhưng không thay thế việc thiết kế đúng quan hệ thứ tự từ đầu.

**Ghi nhớ:** Trong Java, một quan hệ thứ tự dùng bởi `Comparable` hoặc `Comparator` phải **bắc cầu**: nếu `a > b` và `b > c` thì `a > c`. Hãy chọn các khóa so sánh có thứ tự ưu tiên ổn định, dùng các hàm `compare` tránh tràn số và không đưa quan hệ có vòng vào các thuật toán sắp xếp hoặc collection theo thứ tự.