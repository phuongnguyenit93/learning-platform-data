# Các khoảng origin, bound và quy tắc cận trên loại trừ khi tạo số ngẫu nhiên trong Java

## 1. Hiểu đúng khoảng [origin, bound)

Trong các API sinh số ngẫu nhiên có tham số `origin` và `bound` của Java, quy tắc trọng tâm là:

**`origin` được lấy (inclusive), còn `bound` bị loại trừ (exclusive).**

Ký hiệu toán học: **[origin, bound)**, tương đương điều kiện:

~~~text
origin <= result < bound
~~~

Với **số nguyên**, tập giá trị có thể trả về hữu hạn và liệt kê được. Ví dụ:

| Lệnh Java 17 | Khoảng chính xác | Các giá trị `int` có thể có |
|---|---|---|
| `rng.nextInt(0, 5)` | [0, 5) | 0, 1, 2, 3, 4 |
| `rng.nextInt(1, 7)` | [1, 7) | 1, 2, 3, 4, 5, 6 |
| `rng.nextInt(-3, 4)` | [-3, 4) | -3, -2, -1, 0, 1, 2, 3 |
| `rng.nextInt(7, 8)` | [7, 8) | chỉ 7 |
| `rng.nextInt(-5, 0)` | [-5, 0) | -5, -4, -3, -2, -1 |
| `rng.nextInt(5, 5)` | khoảng rỗng | ném `IllegalArgumentException` |

Với [0, 5), số 5 **không thể** được sinh bởi đúng lời gọi này. Với [-3, 4), số -3 **có thể** xuất hiện và số 4 **không thể** xuất hiện. Quy tắc vẫn giữ nguyên khi origin âm, dương hoặc bằng 0.

Khi biểu diễn bằng số học trên tập số nguyên, số phần tử của khoảng [origin, bound) là `bound - origin`, **được hiểu theo toán học**. Nếu tính hiệu này bằng phép trừ `int` trong Java, phép toán có thể overflow; không nên lấy công thức rồi mặc định kiểu `int` luôn chứa được kết quả.

### Vì sao chọn cận trên loại trừ?

Khoảng nửa mở giúp tính kích thước và ghép đoạn rõ ràng. Nếu [a, b) và [b, c) được ghép, chúng không trùng giá trị b và bao phủ [a, c). Phân đoạn dãy bằng chỉ số cũng dùng quy tắc này: một mảng độ dài n có chỉ số [0, n), nên `nextInt(n)` phù hợp để chọn một chỉ số hợp lệ khi **n > 0**.

Đừng nhầm chữ “bound” với “giá trị lớn nhất có thể trả về”. Trong `nextInt(origin, bound)`, nếu khoảng không rỗng, số nguyên lớn nhất có thể trả về là **bound - 1**, trừ khi đây chỉ là cách nói toán học để diễn giải; trong code vẫn phải chú ý overflow khi thao tác số cực trị.

## 2. Các API phổ biến trong Java 17+

Java 17 có interface `java.util.random.RandomGenerator`, cung cấp cách gọi nhất quán trên các generator khác nhau. Một `java.util.Random` có thể dùng qua interface này:

~~~java
import java.util.Random;
import java.util.random.RandomGenerator;

RandomGenerator rng = new Random(2026L);
int roll = rng.nextInt(1, 7); // 1..6
~~~

Đoạn trên là **minh họa đặt bên trong phương thức**, không có `main`; ví dụ chương trình hoàn chỉnh nằm ở phần 5.

| API | Khoảng trả về | Ràng buộc chính |
|---|---|---|
| `rng.nextInt()` | Một giá trị `int` bất kỳ | Không có cận origin/bound |
| `rng.nextInt(bound)` | [0, bound) | `bound > 0` |
| `rng.nextInt(origin, bound)` | [origin, bound) | `origin < bound` |
| `rng.nextLong(origin, bound)` | [origin, bound) trên kiểu `long` | `origin < bound` |
| `rng.nextDouble()` | [0.0, 1.0) | Giá trị dấu phẩy động |
| `rng.nextDouble(origin, bound)` | [origin, bound) trên kiểu `double` | Hai cận hữu hạn và `origin < bound` |
| `rng.nextFloat(origin, bound)` | [origin, bound) trên kiểu `float` | Hai cận hữu hạn và `origin < bound` |
| `random.ints(size, origin, bound)` | Stream gồm `size` số `int` thuộc [origin, bound) | `size >= 0` và `origin < bound` |
| `random.longs(size, origin, bound)` | Stream `long` có cùng quy tắc nửa mở | Cận hợp lệ, size không âm |
| `random.doubles(size, origin, bound)` | Stream `double` có cùng quy tắc nửa mở | Cận hữu hạn, size không âm |

Các dòng `rng` giả định `rng` thuộc interface `RandomGenerator`. `Random` có phương thức `nextInt(int bound)` và triển khai interface `RandomGenerator` ở Java 17; vì vậy các overload `nextInt(origin, bound)`, `nextLong(origin, bound)` có thể được gọi qua interface. `ThreadLocalRandom.current()` và `SplittableRandom` cũng có các overload bounded phù hợp.

Ví dụ chọn cách sử dụng:

~~~java
int dice = java.util.concurrent.ThreadLocalRandom.current().nextInt(1, 7);
long idPart = java.util.concurrent.ThreadLocalRandom.current()
        .nextLong(1_000L, 10_000L);
~~~

Đây là đoạn minh họa trong một phương thức: `dice` thuộc [1, 7), `idPart` thuộc [1000, 10000). Đây **không phải** cách tạo mã bí mật; các generator thông thường được thiết kế cho tác vụ giả ngẫu nhiên, không mặc định an toàn trước đối thủ.

Khi yêu cầu phải giữ một hạt giống (`seed`) có thể tái hiện test, `new Random(seed)` là lựa chọn dễ hiểu. `ThreadLocalRandom.current()` phù hợp khi nhiều luồng cần tạo số ngẫu nhiên, nhưng không có API đặt seed trực tiếp theo cách dùng thông thường. `SplittableRandom` hỗ trợ chia nhánh generator cho các tác vụ tính toán; các generator có thể tạo chuỗi khác nhau dù đầu vào seed giống nhau.

## 3. nextInt(bound) khác nextInt(origin, bound) thế nào?

Với `nextInt(bound)`, **origin ngầm định là 0**. `nextInt(6)` sinh một số trong {0, 1, 2, 3, 4, 5}. Để mô phỏng xúc xắc từ 1 đến 6:

~~~java
int diceA = rng.nextInt(6) + 1; // 1..6, bound phải dương
int diceB = rng.nextInt(1, 7); // 1..6, trực tiếp nêu khoảng
~~~

Hai công thức có cùng tập giá trị có thể trả về, nhưng không được kỳ vọng cùng kết quả khi gọi liên tiếp vì mỗi lời gọi tiêu thụ trạng thái generator.

Nếu muốn số nguyên trong [-5, 5), **không thể** truyền bound âm vào `nextInt(bound)` rồi chờ nhận giá trị âm:

~~~java
int signed = rng.nextInt(-5, 5); // -5..4
// rng.nextInt(-5);             // IllegalArgumentException
~~~

Với origin khác 0, đặc biệt có số âm hoặc sát cực trị của kiểu số, ưu tiên overload hai cận để bộc lộ rõ ý nghĩa. Không chuyển khoảng bằng `rng.nextInt(bound - origin) + origin` một cách máy móc: nếu phép trừ int overflow, kích thước khoảng tính ra sai và lời gọi có thể thất bại hoặc hành vi khác yêu cầu.

## 4. Đầu vào không hợp lệ và những trường hợp biên

Các overload bị ràng buộc bởi **khoảng có ít nhất một giá trị hợp lệ**:

- `nextInt(bound)` cần `bound > 0`. `bound = 0` hay âm đều sai; `nextInt(0)` không có giá trị hợp lệ.
- `nextInt(origin, bound)` và `nextLong(origin, bound)` cần `origin < bound`. Khoảng [7, 7) rỗng; [8, 7) ngược cận. Hai trường hợp đều ném `IllegalArgumentException`.
- Với `nextDouble(origin, bound)` và `nextFloat(origin, bound)`, hai cận phải hữu hạn, không phải NaN/Infinity, và thỏa origin < bound.
- `size` trong các overload tạo stream hữu hạn phải không âm. `size = 0` tạo stream rỗng, không phải lỗi nếu hai cận hợp lệ.

**Một phần tử trong khoảng số nguyên** không giống khoảng rỗng. [7, 8) luôn trả 7; [7, 7) không trả giá trị nào và bị từ chối. Đây là test tốt cho lỗi nhầm inclusive/exclusive.

Nếu API của bạn nhận `origin` và `bound` từ người dùng, hãy xác thực sớm và trả lỗi dễ hiểu: đầu vào cần đúng kiểu, khoảng không rỗng, miền giá trị không vi phạm quy tắc nghiệp vụ. Sau xác thực, vẫn để API chuẩn thực hiện sinh số ngẫu nhiên thay vì tự thay đổi cận không có cơ sở.

## 5. Chương trình Java 17+ có kiểm chứng giới hạn

Lưu thành **`OriginBoundDemo.java`**. Chương trình không in ra các số ngẫu nhiên cụ thể, vì giá trị được rút là không cố định theo ý nghĩa của ví dụ; thay vào đó nó **kiểm tra bất biến và in kết quả ổn định**. Kiểm tra này chứng minh phạm vi của các giá trị *đã lấy mẫu*, không chứng minh xác suất đồng đều của toàn bộ generator.

~~~java
import java.util.Random;
import java.util.random.RandomGenerator;

public class OriginBoundDemo {
    private static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("Range invariant violated");
        }
    }

    private static void expectInvalid(Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected IllegalArgumentException");
        } catch (IllegalArgumentException expected) {
            // Đúng hợp đồng: tham số khoảng không hợp lệ.
        }
    }

    // Hỗ trợ toàn bộ miền int, kể cả upper = Integer.MAX_VALUE.
    private static int nextIntInclusive(RandomGenerator rng, int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min must not exceed max");
        }
        long upperExclusive = (long) max + 1L;
        long sampled = rng.nextLong((long) min, upperExclusive);
        return Math.toIntExact(sampled);
    }

    public static void main(String[] args) {
        RandomGenerator rng = new Random(2026L);

        for (int i = 0; i < 10_000; i++) {
            int x = rng.nextInt(-3, 4);
            long y = rng.nextLong(-20L, 21L);
            double z = rng.nextDouble(-0.5, 2.5);

            check(x >= -3 && x < 4);
            check(y >= -20L && y < 21L);
            check(z >= -0.5 && z < 2.5);
        }
        System.out.println("Half-open ranges: PASS");

        check(rng.nextInt(7, 8) == 7);
        check(rng.nextInt(Integer.MAX_VALUE - 1,
                          Integer.MAX_VALUE) == Integer.MAX_VALUE - 1);
        check(nextIntInclusive(rng, Integer.MAX_VALUE,
                                   Integer.MAX_VALUE) == Integer.MAX_VALUE);
        check(nextIntInclusive(rng, Integer.MIN_VALUE,
                                   Integer.MIN_VALUE) == Integer.MIN_VALUE);
        System.out.println("Boundary cases: PASS");

        expectInvalid(() -> rng.nextInt(0));
        expectInvalid(() -> rng.nextInt(5, 5));
        expectInvalid(() -> rng.nextInt(6, 5));
        expectInvalid(() -> rng.nextDouble(Double.NaN, 1.0));
        expectInvalid(() -> nextIntInclusive(rng, 9, 8));
        System.out.println("Invalid arguments: PASS");

        check(rng.ints(100, -3, 4)
                 .allMatch(value -> value >= -3 && value < 4));
        System.out.println("Bounded stream: PASS");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac OriginBoundDemo.java
java OriginBoundDemo
~~~

Stdout:

~~~text
Half-open ranges: PASS
Boundary cases: PASS
Invalid arguments: PASS
Bounded stream: PASS
~~~

Trong `nextIntInclusive`, hàm có quy tắc **cả hai cận đều được lấy**: [min, max]. Vì tham số `max` là `int`, phép cộng `(long) max + 1L` an toàn trong `long`, kể cả khi max bằng `Integer.MAX_VALUE`. Số ngẫu nhiên được tạo ở dạng `long` trong [min, max + 1), rồi chuyển chính xác về `int` bằng `Math.toIntExact`; vì kết quả không vượt giới hạn `int` theo tiền điều kiện, chuyển đổi thành công. Đây là phiên bản tổng quát cho khoảng nguyên đóng kiểu int, không phải công thức để xử lý mọi khoảng kiểu long.

## 6. Đổi [min, max] sang [origin, bound) mà không bị off-by-one

Bài toán kinh điển: “lấy ngẫu nhiên từ 1 đến 6 **bao gồm cả 6**”. Đây là **[1, 6]**, trong khi API hai cận nhận **[origin, bound)**. Ta viết:

~~~java
int roll = rng.nextInt(1, 7); // [1, 7) tương đương [1, 6]
~~~

Nhiều lỗi xuất phát từ việc truyền thẳng `max`:

~~~java
int wrong = rng.nextInt(1, 6); // CHỈ 1..5, không thể bằng 6
~~~

Với số nguyên và max không phải giá trị cực đại, quy tắc chuyển là:

~~~text
[minimum, maximum]  =>  [minimum, maximum + 1)
~~~

Nhưng **phép `maximum + 1` phải biểu diễn được trong kiểu dữ liệu**. Nếu `maximum = Integer.MAX_VALUE`, biểu thức `maximum + 1` trong `int` overflow thành `Integer.MIN_VALUE`. Tương tự, `rng.nextInt(Integer.MAX_VALUE + 1)` thành `nextInt(Integer.MIN_VALUE)` và ném lỗi. Dùng `Math.addExact(maximum, 1)` nếu muốn **phát hiện** overflow; hoặc chọn thuật toán mở rộng sang `long` như `nextIntInclusive` trong ví dụ khi thật sự cần bao gồm `Integer.MAX_VALUE`.

Không nên áp dụng công thức đổi miền số nguyên cho `double` một cách mù quáng: “max + 1.0” thêm cả một khoảng thực rộng một đơn vị, không có nghĩa là cho phép chính xác một giá trị max. Miền float/double có tính chất biểu diễn khác miền int/long; hãy xác định rõ hợp đồng có thực sự cần nhận bound hay không, thường chỉ cần [origin, bound) theo API.

### Trường hợp số nguyên sát cực trị

Các lời gọi sau là hợp lệ:

~~~java
int lastBelowMax = rng.nextInt(
        Integer.MAX_VALUE - 1, Integer.MAX_VALUE);
// Giá trị duy nhất: Integer.MAX_VALUE - 1

long maxAsLong = rng.nextLong(
        (long) Integer.MAX_VALUE, (long) Integer.MAX_VALUE + 1L);
// Giá trị duy nhất: 2147483647L
~~~

Tập giá trị của `nextInt(Integer.MIN_VALUE, Integer.MAX_VALUE)` bao trùm phần lớn miền int nhưng vẫn **loại trừ chính Integer.MAX_VALUE**. Cần toàn bộ miền `int` có thể dùng `nextInt()` không có cận, hoặc dùng cách xây dựng khoảng đóng đã kiểm soát theo `long` khi có min/max do nghiệp vụ cung cấp.

Với chính kiểu `long`, `Long.MAX_VALUE + 1L` overflow. Không thể dùng mẹo chuyển sang `long` lớn hơn như với int; nếu nghiệp vụ đòi khoảng đóng kết thúc ở `Long.MAX_VALUE`, phải thiết kế riêng bằng cách khác (ví dụ thuật toán chọn mẫu phù hợp với toàn miền hoặc số nguyên lớn hơn), không tự tăng bound trong kiểu long.

## 7. Số thực double: cùng dấu ngoặc khoảng, khác đặc tính biểu diễn

`nextDouble(origin, bound)` tạo giá trị dấu phẩy động trong khoảng **[origin, bound)**. Ví dụ:

~~~java
double fraction = rng.nextDouble(0.0, 1.0);
double temperature = rng.nextDouble(-10.0, 35.0);
~~~

`fraction` có thể bằng 0.0 nhưng không thể bằng 1.0 theo contract; `temperature` có thể sát 35.0 nhưng phải nhỏ hơn 35.0. **Không có bảo đảm** từng điểm trong khoảng thực đều có thể xuất hiện: `double` chỉ biểu diễn tập hữu hạn các số theo IEEE 754; đây không phải lấy ngẫu nhiên trên continuum thực lý tưởng.

Nếu cần chọn ngẫu nhiên số thập phân có bước cố định, chẳng hạn giá tiền cách nhau 0.01, hãy sinh **đơn vị nguyên nhỏ nhất** trong miền đã xác định, rồi chuyển sang biểu diễn thập phân. Đừng lấy `nextDouble`, nhân 100 và làm tròn một cách không phân tích: phân phối trên tập giá trị rời rạc có thể bị lệch ở biên hoặc chịu ảnh hưởng của precision và rounding.

**Vì sao không tự mở rộng bằng `Math.random()` một cách tùy tiện?**

~~~java
double raw = Math.random();            // [0.0, 1.0)
double shifted = -2.0 + raw * 5.0;    // Ý định: [-2.0, 3.0)
~~~

Đây là đoạn mô tả phép biến đổi; các số thực dấu phẩy động được làm tròn khi nhân/cộng. Trong những tình huống biên, phép tính thủ công có thể tạo vấn đề do làm tròn đến bound hoặc hiệu `bound - origin` bị overflow thành Infinity. Khi đã có API `rng.nextDouble(origin, bound)`, ưu tiên dùng nó để diễn đạt trực tiếp chính sách [origin, bound) và kiểm tra hợp lệ của tham số. Bản thân số học dấu phẩy động trong các miền cực đoan vẫn cần kiểm thử.

`Math.random()` trả về giá trị trong [0.0, 1.0); nó không có tham số origin/bound và không phải API phù hợp để sinh token bí mật. Với số thực rất gần nhau, cần hiểu độ phân giải và khả năng biểu diễn; sự khác biệt giữa hai cận phải được diễn giải trên kiểu `double`, không phải trên số thập phân lý tưởng.

## 8. Số lượng giá trị và xác suất ở miền nguyên

Nếu bộ sinh phân phối gần đồng đều trên một khoảng nguyên gồm n giá trị thì xác suất của mỗi giá trị là gần `1/n` (mức độ và bảo đảm chính xác tùy bộ sinh). Với [1, 7), n = 6, mô phỏng xúc xắc cân bằng theo kỳ vọng có mỗi mặt xác suất khoảng 1/6. Đây là lý do cần tránh dùng phép chia dư đơn giản:

~~~java
int wrong = Math.abs(rng.nextInt()) % 6; // Không nên làm thế
int correct = rng.nextInt(6);            // 0..5
~~~

Hai rủi ro ở công thức `wrong`:

1. `Math.abs(Integer.MIN_VALUE) == Integer.MIN_VALUE` vì trị tuyệt đối dương không biểu diễn được trong `int`. Vì vậy kết quả có thể âm.
2. Ép tất cả giá trị ngẫu nhiên vào miền nhỏ bằng phép `%` theo cách không có loại bỏ mẫu (`rejection sampling`) có thể tạo **modulo bias** vì số phần tử trong miền nguồn không chia hết cho độ rộng miền đích.

Hãy dùng bounded API chuẩn để tạo mẫu từ một tập giá trị số nguyên; nó được thiết kế để xử lý giới hạn và giảm thiên lệch phân phối theo hợp đồng generator. Đừng tự viết lại thuật toán sinh số có cận nếu chưa có nhu cầu được chứng minh và kiểm thử thống kê thích hợp.

### Không đánh giá tính đồng đều bằng một vài mẫu

Nếu chạy 10.000 lần và chỉ thấy các giá trị trong [origin, bound), ta mới kiểm chứng **phạm vi của mẫu đã quan sát**. Việc không thấy bound trong một số lượt không chứng minh đầy đủ thuật toán. Tương tự, một bộ mẫu nhỏ có tần suất không bằng nhau không đủ để kết luận generator sai. Khi kiểm thử logic sản phẩm, nên kiểm tra invariant bất biến; khi đánh giá xác suất, cần phương pháp thống kê phù hợp.

## 9. Streams dùng cùng quy tắc khoảng nửa mở

Các API Java như `Random.ints`, `Random.longs`, `Random.doubles` cho phép tạo stream số ngẫu nhiên có giới hạn:

~~~java
import java.util.Random;

Random random = new Random(2026L);
long validCount = random.ints(500, 10, 20)
        .filter(x -> x >= 10 && x < 20)
        .count();

System.out.println(validCount); // 500
~~~

Đây là đoạn nằm trong thân một phương thức (với import tương ứng). Các phần tử đều trong **[10, 20)**, nên số 20 không được sinh. Cần lưu ý `ints(500, 10, 20)` có tham số **streamSize trước, origin và bound sau**; không nhầm với `nextInt(origin, bound)` chỉ có hai cận. `ints(origin, bound)` không có streamSize sinh stream về lý thuyết không giới hạn, nên dùng `limit` hoặc một phép toán kết thúc có điều kiện và kiểm soát tài nguyên.

Stream được tiêu thụ một lần. Với test có seed cố định, tránh giả định các thao tác ở thứ tự khác nhau hoặc generator khác nhau cho ra cùng dãy. Mỗi lời gọi sinh số làm thay đổi trạng thái của generator có trạng thái; không so sánh cứng một mẫu ngẫu nhiên với mẫu được lấy **sau** nó.

## 10. Áp dụng vào các tình huống thực tế

### Chọn chỉ số mảng/list

~~~java
if (!items.isEmpty()) {
    int index = rng.nextInt(items.size()); // [0, size)
    var selected = items.get(index);
}
~~~

Đây là đoạn minh họa đặt trong phương thức có biến `items` là một `List`. `items.size() > 0` là điều kiện cần: list rỗng dẫn tới `nextInt(0)` ném lỗi. Cận trên loại trừ tương thích trực tiếp với vị trí cuối là `size - 1`.

### Sinh số trong khoảng có cả số âm

~~~java
int adjustment = rng.nextInt(-10, 11); // [-10, 10]
~~~

Vì cần bao gồm +10, bound truyền vào là 11. Không nên suy ra `rng.nextInt(-10, 10)` sẽ bao gồm +10.

### Sinh mã số hoặc số phiên ngắn

~~~java
int fourDigits = rng.nextInt(1000, 10_000); // 1000..9999
~~~

Đây chỉ là số giả ngẫu nhiên bốn chữ số, **không** tự bảo đảm duy nhất, không bảo đảm tính khó đoán, không thay thế sequence hoặc cơ chế cấp ID. Nếu cần token phiên đăng nhập, mã xác thực, key hoặc bí mật bảo mật, cần nguồn ngẫu nhiên an toàn mật mã như `SecureRandom` và thiết kế bảo mật phù hợp. Tính đúng của khoảng [origin, bound) chỉ là một phần rất nhỏ của vấn đề đó.

### Lấy số của một enum

~~~java
enum TrafficColor { RED, YELLOW, GREEN }

TrafficColor[] values = TrafficColor.values();
TrafficColor randomColor = values[rng.nextInt(values.length)];
~~~

Các đoạn trong phần 10 là minh họa đặt trong thân class/phương thức phù hợp; enum khai báo ở cấp class, còn thao tác truy cập mảng ở bên trong phương thức. Nếu enum rỗng (không có hằng), phải xử lý riêng trước `nextInt(0)`.

## 11. Kiểm thử thiết kế khoảng đúng hơn

Cần kiểm tra cả **tính đúng của yêu cầu miền** và **hành vi code**:

1. **Ranh giới đơn giản:** [0, 1) chỉ trả 0; [7, 8) chỉ trả 7. Những trường hợp một phần tử giúp bắt nhầm cận rất nhanh.
2. **Origin âm:** [-3, 4) bảo đảm `x >= -3 && x < 4`. Chạy nhiều lần chỉ là kiểm chứng mẫu, không chứng minh thống kê.
3. **Đầu vào lỗi:** `bound <= 0` với overload một cận; `origin >= bound` với overload hai cận; NaN/Infinity với floating bounds.
4. **Cực trị int:** [`Integer.MAX_VALUE - 1`, `Integer.MAX_VALUE`) chỉ có `Integer.MAX_VALUE - 1`. Với khoảng đóng [MAX, MAX], hàm hỗ trợ inclusive trả MAX; công thức cộng `1` kiểu int bị overflow.
5. **Chuyển đổi từ yêu cầu “đến và bao gồm”:** ví dụ xúc xắc [1, 6] phải chuyển thành [1, 7), không phải [1, 6).
6. **Mảng rỗng:** không gọi `nextInt(size)` khi size bằng 0; đặt tiền điều kiện hoặc xử lý nhánh rỗng.
7. **Stream:** kiểm tra đúng thứ tự tham số `(size, origin, bound)`; kích thước stream đầu ra và mọi giá trị thuộc khoảng.
8. **Khả năng tái hiện:** dùng seed cố định trong test cho luồng gọi được kiểm soát, nhưng không đánh đồng seed giống nhau giữa mọi lớp generator hoặc mọi chiến lược phân luồng.
9. **Phân phối và bảo mật:** kiểm thử bất biến không thay thế kiểm định ngẫu nhiên; `Random`/`ThreadLocalRandom` không mặc định là nguồn sinh token an toàn.
10. **Số thực:** kiểm tra hữu hạn và `origin <= x < bound`; không ép kiểm thử phải quan sát cả hai đầu mút vì một đầu mút bị loại, còn đầu mút được phép chưa chắc được lấy trong mẫu hữu hạn.

Một ví dụ nhỏ kiểm tra ngoại lệ theo tiền điều kiện, có thể đặt trong unit test:

~~~java
RandomGenerator rng = new Random(1L);
try {
    rng.nextInt(5, 5);
    throw new AssertionError("Expected IllegalArgumentException");
} catch (IllegalArgumentException expected) {
    // PASS: [5, 5) không có phần tử.
}
~~~

Ở đoạn này cần import `java.util.Random` và `java.util.random.RandomGenerator` và đặt mã trong phương thức. Không dựa vào `assert` của Java khi test chưa bật `-ea`; dùng test framework hoặc kiểm tra luôn thực thi như ví dụ.

## 12. Lỗi phổ biến cần tránh

| Sai lầm | Vì sao sai | Cách làm đúng |
|---|---|---|
| `nextInt(1, 6)` để lấy xúc xắc 1..6 | Số 6 là bound bị loại | `nextInt(1, 7)` |
| `nextInt(0)` để chọn phần tử list rỗng | Không có chỉ số hợp lệ | Xử lý list rỗng trước |
| `nextInt(-5)` để lấy số âm | Overload một cận yêu cầu bound dương | `nextInt(-5, 0)` |
| `nextInt(min, max + 1)` khi max = INT_MAX | Overflow trong phép cộng kiểu int | Dùng `long` có kiểm soát, hoặc thuật toán tổng quát |
| `nextInt(max - min) + min` cho miền lớn | Hiệu `int` có thể overflow | Dùng overload `nextInt(min, max)` |
| Dùng `Math.abs(nextInt()) % n` | Có thể âm, có modulo bias | Dùng `nextInt(n)` |
| Đo `nextDouble` bằng số chữ số thập phân hiển thị | Số thực dấu phẩy động có precision riêng | Kiểm tra bằng bất đẳng thức trên giá trị |
| Tạo token bảo mật bằng `Random` | Generator không dành cho trường hợp đối thủ dự đoán | Dùng `SecureRandom` với quy trình an toàn |
| Dùng vài mẫu để kết luận bound được/không được lấy | Ngẫu nhiên không bảo đảm quan sát mọi khả năng | Dựa vào contract và test biên |
| Viết thuật toán riêng vì muốn cận đóng | Dễ lỗi off-by-one và overflow | Chuyển miền có kiểm soát hoặc helper đã kiểm thử |

## 13. Bài tập và đáp án

**Bài 1.** Viết `nextInt(origin, bound)` cho các yêu cầu: từ 4 đến 9 (bao gồm 9); từ -7 đến -1 (bao gồm -1); từ 0 đến 0 (chỉ một giá trị).

**Bài 2.** Dự đoán kết quả/phạm vi: `nextInt(10, 11)`, `nextInt(-2, 2)`, `nextInt(3, 3)`, `nextInt(10, 9)`.

**Bài 3.** Tại sao `rng.nextInt(1, Integer.MAX_VALUE + 1)` không thể dùng để bao gồm `Integer.MAX_VALUE`? Viết phương án tránh overflow.

**Bài 4.** Vì sao `rng.nextInt(-10, 10)` không tạo giá trị 10, nhưng có thể tạo -10? Hãy phát biểu bất biến kiểm tra mọi kết quả.

**Bài 5.** Một mảng có n = 12 phần tử. Cách chọn ngẫu nhiên một chỉ số hợp lệ và cách xử lý n = 0 là gì?

**Đáp án:**

1. `nextInt(4, 10)`, `nextInt(-7, 0)`, `nextInt(0, 1)`.
2. Chỉ trả 10; từ -2 đến 1; hai lời gọi cuối ném `IllegalArgumentException`.
3. `Integer.MAX_VALUE + 1` overflow kiểu int; có thể dùng helper `nextIntInclusive` của phần 5 với max kiểu int rồi tính upper bằng long.
4. Khoảng là [-10, 10): `value >= -10 && value < 10`.
5. Nếu n > 0, `rng.nextInt(n)` trả chỉ số [0, n); nếu n = 0, xử lý riêng thay vì gọi `nextInt(0)`.

## Tài liệu Java SE 17

- `RandomGenerator` (các overload `nextInt`, `nextLong`, `nextDouble`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html
- `Random`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html
- `ThreadLocalRandom`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html
- `SplittableRandom`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SplittableRandom.html
- `Math.random()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#random()

**Ghi nhớ:** khi đọc tham số `origin` và `bound`, luôn diễn giải theo **`origin <= value < bound`**. Nếu yêu cầu thực tế là [min, max] bao gồm max, chỉ chuyển thành [min, max + 1) sau khi xác minh phép cộng có thể biểu diễn an toàn trong kiểu số đang dùng.