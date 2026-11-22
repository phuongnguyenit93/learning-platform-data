# IntStream.range và IntStream.rangeClosed trong Java

## 1. Mục tiêu và điểm khác biệt cần nhớ

Trong Java Stream API, `java.util.stream.IntStream` là một luồng các giá trị `int` nguyên thủy (*primitive int stream*). Hai phương thức tạo nguồn rất phổ biến là:

~~~java
IntStream.range(startInclusive, endExclusive);
IntStream.rangeClosed(startInclusive, endInclusive);
~~~

Cả hai đều là **static factory methods** có từ **Java 8** và vẫn được sử dụng trong Java hiện đại. Chúng tạo các giá trị nguyên liên tiếp, tăng từng bước **1**, không yêu cầu bạn tạo mảng hoặc `List<Integer>` trước.

Điểm khác biệt là **cận cuối**:

- `IntStream.range(a, b)` tạo các giá trị từ **a đến trước b**: khoảng nửa mở `[a, b)`.
- `IntStream.rangeClosed(a, b)` tạo các giá trị từ **a đến hết b**: khoảng đóng `[a, b]`.

Ví dụ:

~~~java
// Mảnh mã minh họa, đã import java.util.stream.IntStream.
IntStream.range(2, 6);       // 2, 3, 4, 5
IntStream.rangeClosed(2, 6); // 2, 3, 4, 5, 6
~~~

Các biểu thức trên tạo nguồn Stream; để **xem kết quả**, cần gọi một thao tác kết thúc như `toArray()`, `boxed().toList()`, `count()`, `sum()` hoặc `forEach(...)`.

Có thể hiểu đơn giản:

~~~text
range(2, 6)         [2, 3, 4, 5]       bỏ 6
rangeClosed(2, 6)   [2, 3, 4, 5, 6]    có 6
range(4, 4)         []                rỗng
rangeClosed(4, 4)   [4]               một phần tử
~~~

**Quy tắc chọn nhanh:** duyệt **chỉ số từ 0 đến size - 1** thì ưu tiên `range(0, size)`; duyệt **các số từ m đến n có cả n** thì ưu tiên `rangeClosed(m, n)`. Không biến `endExclusive` và `endInclusive` thành hai khái niệm mơ hồ bằng cách gọi cả hai là “end”.

## 2. Chữ ký API và kiểu kết quả

Hai chữ ký trong `IntStream`:

~~~java
public static IntStream range(int startInclusive, int endExclusive);
public static IntStream rangeClosed(int startInclusive, int endInclusive);
~~~

Đây là chữ ký API dùng để giải thích, không phải phương thức bạn tự thêm vào class.

| Thuộc tính | `range(a, b)` | `rangeClosed(a, b)` |
| --- | --- | --- |
| Cận đầu | Bao gồm `a` | Bao gồm `a` |
| Cận cuối | Loại trừ `b` | Bao gồm `b` |
| Các bước tăng | 1 | 1 |
| `a < b` | `a, a+1, ..., b-1` | `a, a+1, ..., b` |
| `a == b` | Rỗng | Một phần tử `a` |
| `a > b` | Rỗng | Rỗng |
| Kiểu phần tử | Primitive `int` | Primitive `int` |
| Kiểu trả về | `IntStream` | `IntStream` |
| Có thể gọi `sum`, `average`, `count` | Có | Có |
| Có dùng cho số âm | Có | Có |

Truyền hai đối số `int` có nghĩa ta phải xác định rõ phạm vi biểu diễn được bằng kiểu `int`. Bản thân số lượng phần tử của một khoảng rất rộng có thể lớn hơn `Integer.MAX_VALUE`, nên terminal `count()` trả **`long`**, không phải `int`.

### Các phương thức này là nguồn, không phải terminal

~~~java
IntStream numbers = IntStream.range(1, 5);
~~~

Dòng trên tạo một `IntStream`. Chưa có một `List` được trả về. Ta có thể gắn thêm các thao tác trung gian rồi gọi terminal:

~~~java
int sum = IntStream.range(1, 5)
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .sum(); // 4 + 16 = 20
~~~

Tại đây `range` là **nguồn**, `filter` và `map` là **trung gian**, `sum` là **kết thúc**. Phân biệt ba phần giúp tránh việc tưởng nguồn Range tự tạo sẵn mọi phần tử trong một collection.

## 3. Ví dụ chạy đầy đủ 1: cận đóng, cận mở và khoảng rỗng

Tạo tệp **IntRangeBasicsDemo.java**:

~~~java
import java.util.stream.IntStream;

public class IntRangeBasicsDemo {

    public static void main(String[] args) {
        System.out.println("exclusive=" +
                IntStream.range(2, 6).boxed().toList());

        System.out.println("inclusive=" +
                IntStream.rangeClosed(2, 6).boxed().toList());

        System.out.println("same-exclusive=" +
                IntStream.range(4, 4).count());

        System.out.println("same-inclusive=" +
                IntStream.rangeClosed(4, 4).boxed().toList());

        System.out.println("reversed=" +
                IntStream.rangeClosed(5, 2).count());

        System.out.println("negative=" +
                IntStream.range(-2, 2).boxed().toList());
    }
}
~~~

Biên dịch/chạy trên JDK 17+:

~~~bash
javac IntRangeBasicsDemo.java
java IntRangeBasicsDemo
~~~

**Stdout chính xác:**

~~~text
exclusive=[2, 3, 4, 5]
inclusive=[2, 3, 4, 5, 6]
same-exclusive=0
same-inclusive=[4]
reversed=0
negative=[-2, -1, 0, 1]
~~~

Phân tích:

1. `range(2,6)`: lấy 2, 3, 4, 5; không lấy 6.
2. `rangeClosed(2,6)`: thêm 6 vì cận cuối được bao gồm.
3. `range(4,4)`: không có giá trị nào vì khoảng nửa mở có độ dài 0.
4. `rangeClosed(4,4)`: vẫn có một giá trị 4.
5. `rangeClosed(5,2)`: cận đầu lớn hơn cận cuối, kết quả rỗng; không tự tạo dãy giảm.
6. `range(-2,2)`: hỗ trợ số âm, rồi -1, 0, 1; không gồm 2.
7. `boxed()` chuyển `IntStream` sang `Stream<Integer>`; `toList()` từ Java 16 tạo danh sách unmodifiable. Các factory `range` và `rangeClosed` vẫn chỉ cần Java 8.

Nếu cần hỗ trợ Java 8 thuần, thay phần in danh sách bằng `IntStream.range(...).boxed().collect(Collectors.toList())` (với import tương ứng) hoặc `Arrays.toString(IntStream.range(...).toArray())`. Không ghi nhầm rằng `Stream.toList()` đã có trong JDK 8.

## 4. Vì sao Java dùng khoảng nửa mở `[start,end)`?

Phần lớn cấu trúc chỉ số trong Java dùng quy ước **start inclusive / end exclusive**. Ví dụ:

- Chỉ số hợp lệ của danh sách có `size` phần tử: `0` đến `size - 1`.
- `List.subList(fromIndex, toIndex)`: `fromIndex` bao gồm, `toIndex` loại trừ.
- Vòng lặp `for (int i = 0; i < size; i++)`: điều kiện `i < size`.
- `IntStream.range(0, size)`: có các chỉ số đúng cùng phạm vi.

Đây là ba cách nói tương đương về ranh giới chỉ số: số phần tử được duyệt chính xác là `size` nếu `size >= 0`.

Ví dụ một list có 4 phần tử:

~~~text
Giá trị: [A, B, C, D]
Chỉ số:    0  1  2  3
size = 4
range(0, 4) -> 0, 1, 2, 3
~~~

**Lỗi off-by-one** thường phát sinh khi viết nhầm:

~~~java
// CỐ Ý minh họa lời gọi có thể lỗi IndexOutOfBoundsException:
IntStream.rangeClosed(0, items.size())
        .mapToObj(items::get)
        .toList();
~~~

Vì cận cuối được bao gồm, `rangeClosed(0,items.size())` đưa cả chỉ số `size` vào pipeline; `items.get(size)` không hợp lệ khi list có phần tử. Với list rỗng, `rangeClosed(0,0)` còn tạo một chỉ số 0 dù list không có phần tử nào.

**Sửa đúng**:

~~~java
// Mảnh mã minh họa, items là List<T>:
IntStream.range(0, items.size())
        .mapToObj(items::get)
        .toList();
~~~

Nếu chỉ muốn duyệt phần tử mà **không cần index**, `items.stream()` hoặc enhanced `for` thường rõ và có thể hiệu quả hơn. Không dùng `range(0,size)` chỉ để mô phỏng một vòng lặp vô nghĩa.

## 5. Trường hợp sử dụng nổi bật: làm việc với index

`IntStream.range` hữu ích khi **chỉ số là một phần của bài toán**: in số thứ tự, chọn phần tử theo vị trí, ghép hai danh sách tương ứng, tìm index đầu tiên thỏa điều kiện hoặc tạo bảng hai chiều.

Ví dụ:

~~~java
List<String> labels = List.of("red", "blue", "green");

List<String> indexed = IntStream.range(0, labels.size())
        .mapToObj(i -> i + ":" + labels.get(i))
        .toList();
// [0:red, 1:blue, 2:green]
~~~

Đây là mảnh mã minh họa cho JDK 17+.

Tại sao `mapToObj`?

- `IntStream.map(IntUnaryOperator)` phải trả giá trị `int`.
- `mapToObj(IntFunction<R>)` chuyển từng chỉ số `int` thành một **object** như `String`, record hoặc domain object.
- `boxed()` chỉ bọc `int` thành `Integer`; nếu muốn `"0:red"` thì `mapToObj` diễn đạt mục tiêu trực tiếp hơn.

### Đừng mất đi lợi ích khi không cần chỉ số

~~~java
List<String> uppercase = labels.stream()
        .map(String::toUpperCase)
        .toList();
~~~

Khi không cần `i`, dùng `labels.stream()` thường đơn giản hơn tạo dãy `0..size-1` rồi gọi `get(i)`.

### Chi phí của truy cập theo index

Với `ArrayList`, `get(i)` thường có chi phí O(1). Với `LinkedList`, `get(i)` có thể phải đi qua nhiều node; pattern `IntStream.range(0,list.size()).mapToObj(list::get)` có thể dẫn đến tổng chi phí O(n²) cho list lớn. Khi không cần index, ưu tiên `list.stream()` hoặc enhanced `for`. Nếu phải xử lý index trên linked structure, cân nhắc iterator có đếm chỉ số hoặc cấu trúc dữ liệu phù hợp.

## 6. Ví dụ chạy đầy đủ 2: ghép tên với chỉ số và tìm vị trí

Tạo tệp **IntRangeIndexDemo.java**:

~~~java
import java.util.List;
import java.util.stream.IntStream;

public class IntRangeIndexDemo {

    public static void main(String[] args) {
        List<String> labels =
                List.of("red", "blue", "green", "cyan");

        List<String> indexed = IntStream.range(0, labels.size())
                .mapToObj(i -> i + ":" + labels.get(i))
                .toList();

        int firstLongIndex = IntStream.range(0, labels.size())
                .filter(i -> labels.get(i).length() >= 5)
                .findFirst()
                .orElse(-1);

        long emptyCount =
                IntStream.range(0, List.<String>of().size()).count();

        System.out.println("indexed=" + indexed);
        System.out.println("first-long=" + firstLongIndex);
        System.out.println("empty-count=" + emptyCount);
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac IntRangeIndexDemo.java
java IntRangeIndexDemo
~~~

**Stdout chính xác:**

~~~text
indexed=[0:red, 1:blue, 2:green, 3:cyan]
first-long=2
empty-count=0
~~~

Giải thích:

- Chỉ số hợp lệ của list 4 phần tử là 0..3. `range(0,4)` tạo chính xác các vị trí đó.
- `"green"` dài 5 ký tự và nằm ở index 2; hai chuỗi trước có độ dài 3 và 4. `findFirst()` tìm index đầu tiên đạt điều kiện.
- `OptionalInt.orElse(-1)` được dùng như một **sentinel đã có chủ đích**: -1 nghĩa là không tìm thấy. Nếu muốn biểu diễn sự vắng mặt minh bạch hơn, trả `OptionalInt`.
- Với list rỗng, `range(0,0)` rỗng nên `count()` bằng 0; không truy cập bất kỳ chỉ số nào.

### Ghép hai danh sách cùng vị trí

Khi có hai list cùng kích thước:

~~~java
// Mảnh mã minh họa:
List<String> names = List.of("An", "Binh");
List<Integer> scores = List.of(8, 9);

List<String> rows = IntStream.range(0, names.size())
        .mapToObj(i -> names.get(i) + "=" + scores.get(i))
        .toList();
// [An=8, Binh=9]
~~~

Trước khi dùng cách này trong ứng dụng, **xác minh hai list có cùng size**. Nếu `scores` ngắn hơn, code sẽ ném `IndexOutOfBoundsException` khi truy cập vị trí thiếu. Nếu dữ liệu được ghép theo ID thực sự chứ không phải theo vị trí, dùng map theo key; đừng “zip bằng index” nếu không có hợp đồng đảm bảo alignment.

## 7. Chọn `rangeClosed` cho bài toán số tự nhiên gồm cả cận trên

Rất nhiều yêu cầu diễn đạt kiểu **“từ 1 đến N”** với N được bao gồm: tính tổng dãy, tính số lần, thử điều kiện trên mọi giá trị trong khoảng, tạo bảng phép tính.

~~~java
int sum = IntStream.rangeClosed(1, 5).sum();
// 1 + 2 + 3 + 4 + 5 = 15
~~~

Nếu dùng `IntStream.range(1,5)`, kết quả sẽ là `1+2+3+4=10`, thiếu giá trị 5.

Có thể dùng `range(1, N+1)` để mô phỏng việc bao gồm N nhưng **dễ off-by-one và có rủi ro overflow nếu N là Integer.MAX_VALUE**. Khi ý định là **bao gồm cận cuối**, `rangeClosed(1,N)` rõ ràng và an toàn hơn về biểu thức ranh giới.

### Không cộng 1 một cách máy móc

~~~java
// Không nên làm khi end có thể là Integer.MAX_VALUE:
IntStream.range(start, end + 1);
~~~

Trong Java, `int` overflow theo số học 32-bit. Nếu `end == Integer.MAX_VALUE`, thì `end + 1` trở thành `Integer.MIN_VALUE` và dãy kết quả có thể rỗng hoặc sai so với mục đích. Dùng `rangeClosed(start,end)` cho khoảng đóng; API xử lý đúng cận cuối tối đa.

### Kiểm tra cận khi nghiệp vụ có yêu cầu riêng

`rangeClosed(1,0)` là stream rỗng; Java **không ném IllegalArgumentException** vì cận đầu lớn hơn cận cuối. Nếu một API nghiệp vụ yêu cầu `n >= 1`, tự validate trước:

~~~java
// Mảnh mã minh họa:
if (n < 1) {
    throw new IllegalArgumentException("n must be positive");
}
int sum = IntStream.rangeClosed(1, n).sum();
~~~

Hãy phân biệt hành vi hợp lệ của thư viện (khoảng rỗng) với ràng buộc do **bài toán của bạn** yêu cầu.

## 8. Ví dụ chạy đầy đủ 3: terminal `sum`, `count`, `average`

Tạo tệp **IntRangeAggregationDemo.java**:

~~~java
import java.util.stream.IntStream;

public class IntRangeAggregationDemo {

    public static void main(String[] args) {
        int inclusiveSum =
                IntStream.rangeClosed(1, 100).sum();

        int exclusiveSum =
                IntStream.range(1, 100).sum();

        long count =
                IntStream.rangeClosed(1, 100).count();

        double average =
                IntStream.rangeClosed(1, 100)
                        .average().orElse(-1.0);

        int evenSquares =
                IntStream.range(0, 10)
                        .filter(n -> n % 2 == 0)
                        .map(n -> n * n)
                        .sum();

        System.out.println("inclusive-sum=" + inclusiveSum);
        System.out.println("exclusive-sum=" + exclusiveSum);
        System.out.println("count=" + count);
        System.out.println("average=" + average);
        System.out.println("even-squares=" + evenSquares);
    }
}
~~~

Lệnh:

~~~bash
javac IntRangeAggregationDemo.java
java IntRangeAggregationDemo
~~~

**Stdout chính xác:**

~~~text
inclusive-sum=5050
exclusive-sum=4950
count=100
average=50.5
even-squares=120
~~~

Phân tích:

- Từ 1 đến 100 bao gồm cả 100, tổng bằng `100 * 101 / 2 = 5050`.
- `range(1,100)` chỉ tới 99 nên tổng `99 * 100 / 2 = 4950`.
- `count()` là terminal trả `long`: có 100 giá trị trong `rangeClosed(1,100)`.
- `average()` trả `OptionalDouble`, vì stream có thể rỗng. Khi có 100 giá trị, trung bình là `50.5`. Với stream rỗng, `orElse(-1.0)` là giá trị fallback của ví dụ, không phải một công thức tổng quát.
- Các số chẵn từ 0 tới trước 10 là 0, 2, 4, 6, 8; bình phương rồi cộng `0+4+16+36+64=120`.

### Vì sao mỗi phép dùng một `IntStream` mới?

Stream là **one-shot**. Sau terminal như `sum()` hoặc `count()`, không được gọi một terminal khác trên cùng đối tượng Stream:

~~~java
// CỐ Ý minh họa lỗi runtime:
IntStream stream = IntStream.range(1, 10);
int sum = stream.sum();
long count = stream.count(); // IllegalStateException
~~~

Muốn lấy nhiều phép thống kê trong một lượt, dùng `summaryStatistics()`; hoặc tạo nguồn Range mới như chương trình đầy đủ trên. Range là nguồn dễ tái tạo, nên việc gọi factory nhiều lần thường rõ ràng.

## 9. `IntSummaryStatistics`: nhiều kết quả từ một terminal

`IntStream.summaryStatistics()` là một **terminal operation** trả `IntSummaryStatistics`, chứa tổng, số lượng, min, max và trung bình. Khi cần đồng thời các phép này, nó dễ đọc hơn việc cố tái sử dụng một Stream đã kết thúc.

~~~java
// Mảnh mã minh họa:
java.util.IntSummaryStatistics stats =
        IntStream.rangeClosed(1, 4).summaryStatistics();

System.out.println(stats.getCount());   // 4
System.out.println(stats.getSum());     // 10
System.out.println(stats.getMin());     // 1
System.out.println(stats.getMax());     // 4
System.out.println(stats.getAverage()); // 2.5
~~~

Nó cũng là lựa chọn phù hợp cho stream dữ liệu `int` không phải dãy liên tiếp. Với stream rỗng, xem kỹ contract của `getMin()`, `getMax()` và `getAverage()` thay vì tự suy rằng kết quả phản ánh một giá trị thực trong nguồn.

### `reduce` có cần thiết không?

Ví dụ tích từ 1 đến 5:

~~~java
int product = IntStream.rangeClosed(1, 5)
        .reduce(1, (a, b) -> a * b);
// 120
~~~

`1` là identity của phép nhân. Nhưng kiểu `int` có thể overflow rất nhanh khi tính tích; đừng dùng `reduce` chỉ vì có sẵn nếu yêu cầu cần số nguyên lớn hoặc phát hiện tràn. Với những phép đơn giản như tổng, `sum()` rõ ràng hơn `reduce(0,Integer::sum)`.

## 10. Ranh giới của `int`: overflow và số lượng phần tử

Đây là điểm nâng cao nhưng quan trọng. Vì `range` và `rangeClosed` nhận **`int`**, người đọc dễ nhầm rằng số phần tử của stream không thể vượt `Integer.MAX_VALUE`. Điều đó không đúng: khoảng từ `Integer.MIN_VALUE` đến `Integer.MAX_VALUE` chứa **4.294.967.296** giá trị nguyên khác nhau, lớn hơn giới hạn `int` dương.

`IntStream.count()` trả `long`, nên có thể biểu diễn số lượng lớn đó. Tuy nhiên:

- `sum()` trả **`int`**, có thể overflow ngay cả khi mỗi phần tử là `int` hợp lệ.
- `average()` trả `OptionalDouble`; cần cân nhắc độ chính xác floating-point với dữ liệu lớn.
- `rangeClosed(Integer.MAX_VALUE-2,Integer.MAX_VALUE)` phải tạo đúng ba giá trị cuối, không được viết vòng `for` ngây thơ khiến `i++` overflow và chạy sai.
- Nếu cần miền giá trị `long` thực sự, dùng `LongStream.range` hoặc `LongStream.rangeClosed`, không ép giới hạn miền về int.
- Không tự gán số lượng phần tử vào `int` nếu độ rộng miền có thể vượt phạm vi của int.

### Vì sao vòng `for (i <= MAX_VALUE)` có thể nguy hiểm?

~~~java
// CỐ Ý KHÔNG CHẠY:
// Khi i đạt Integer.MAX_VALUE, i++ overflow thành Integer.MIN_VALUE.
for (int i = Integer.MAX_VALUE - 2;
        i <= Integer.MAX_VALUE; i++) {
    System.out.println(i);
}
~~~

Điều kiện `i <= Integer.MAX_VALUE` luôn đúng cho mọi giá trị `int`, nên vòng lặp không kết thúc chỉ vì đã đạt `MAX_VALUE`. `IntStream.rangeClosed` diễn đạt phạm vi đóng mà không cần bạn tự tăng chỉ số quá cận tối đa.

### Tính tổng an toàn hơn với `long`

Nếu tổng số học có thể vượt `int`, chuyển sang `long` **trước** terminal sum:

~~~java
long total = IntStream.rangeClosed(1, 65_536)
        .asLongStream()
        .sum();
~~~

`IntStream.asLongStream()` chuyển mỗi phần tử `int` sang `long`; `LongStream.sum()` trả `long`. Với miền đủ lớn, ngay cả tổng `long` cũng có thể overflow; khi bài toán đòi hỏi tính đúng cho số rất lớn, cân nhắc `BigInteger`, giới hạn đầu vào hoặc thuật toán có kiểm tra tràn.

## 11. Ví dụ chạy đầy đủ 4: khoảng sát `Integer.MAX_VALUE` và tổng an toàn

Tạo tệp **IntRangeBoundaryDemo.java**:

~~~java
import java.util.stream.IntStream;

public class IntRangeBoundaryDemo {

    public static void main(String[] args) {
        int max = Integer.MAX_VALUE;

        System.out.println("max-tail=" +
                IntStream.rangeClosed(max - 2, max)
                        .boxed().toList());

        System.out.println("one-max=" +
                IntStream.rangeClosed(max, max).count());

        System.out.println("full-count=" +
                IntStream.rangeClosed(
                        Integer.MIN_VALUE, Integer.MAX_VALUE)
                        .count());

        System.out.println("int-sum=" +
                IntStream.rangeClosed(1, 65_536).sum());

        System.out.println("long-sum=" +
                IntStream.rangeClosed(1, 65_536)
                        .asLongStream().sum());
    }
}
~~~

Chạy trên JDK 17+:

~~~bash
javac IntRangeBoundaryDemo.java
java IntRangeBoundaryDemo
~~~

**Stdout chính xác:**

~~~text
max-tail=[2147483645, 2147483646, 2147483647]
one-max=1
full-count=4294967296
int-sum=-2147450880
long-sum=2147516416
~~~

Giải thích:

- `max-tail` gồm ba giá trị int cuối cùng, không wrap thành số âm.
- `rangeClosed(MAX,MAX)` gồm đúng một phần tử.
- Độ rộng miền int đầy đủ là `2^32 = 4.294.967.296`; `count()` trả `long`. Trên các JDK hiện đại, thao tác đếm có thể tận dụng metadata kích thước của nguồn thay vì phải materialize bốn tỉ phần tử.
- Tổng toán học `1+...+65536 = 2.147.516.416`, vượt `Integer.MAX_VALUE = 2.147.483.647`.
- `IntStream.sum()` dùng kết quả `int` theo số học tràn của Java, nên in `-2147450880`.
- `asLongStream().sum()` giữ được kết quả toán học trên miền này.

**Không lấy output `int-sum` làm bằng chứng thuật toán sai**: API đang trả int theo đúng contract. Sai lầm là người gọi chọn kiểu kết quả không đủ lớn cho yêu cầu. Với phép tính tài chính hoặc kiểm soát số lượng quan trọng, xác định giới hạn đầu vào và kiểu số phù hợp trước khi chọn terminal.

## 12. Kiểu primitive và chuyển đổi sang object stream

`IntStream` chuyên cho số nguyên primitive, có terminal như `sum`, `average`, `min`, `max`, `summaryStatistics`; điều này tránh boxing từng số nếu bạn chỉ cần phép toán số.

### Khi nào dùng `boxed()`?

~~~java
List<Integer> indexes =
        IntStream.range(0, 4).boxed().toList();
// [0, 1, 2, 3]
~~~

`boxed()` trả `Stream<Integer>` để có thể dùng collector hoặc tạo `List<Integer>`. Boxing có chi phí object/representation trong một số workload; không chuyển `IntStream` sang object stream chỉ để tính tổng rồi lại unbox.

### Khi nào dùng `mapToObj`?

~~~java
List<String> labels = IntStream.range(0, 3)
        .mapToObj(i -> "item-" + i)
        .toList();
// [item-0, item-1, item-2]
~~~

`mapToObj` chuyển int thành object bạn định nghĩa, ví dụ String hoặc một record.

### Khi nào dùng `asLongStream()`?

~~~java
long total = IntStream.rangeClosed(1, 100)
        .asLongStream()
        .sum();
~~~

Tránh overflow của tổng `int` với dữ liệu trong giới hạn `long`. Nó khác với `boxed()`, vì `asLongStream` vẫn là **primitive stream**, chỉ chuyển phần tử sang kiểu `long`.

### Khi nào chọn `LongStream.range` ngay từ đầu?

Nếu đầu vào là `long start`, `long end` hoặc giá trị có thể vượt giới hạn int:

~~~java
// Mảnh mã minh họa:
java.util.stream.LongStream.range(
        3_000_000_000L, 3_000_000_003L);
// 3000000000, 3000000001, 3000000002
~~~

Không ép `long` xuống `int` trước khi tạo range, vì sẽ làm mất miền giá trị. Với miền cực rộng, việc duyệt toàn bộ phần tử vẫn có thể tốn thời gian rất lớn; chọn stream không làm cho độ phức tạp thuật toán tự biến mất.

## 13. Tính lazy, short-circuit và vì sao không phải mọi phần tử đều được xử lý

Một `IntStream.range` là nguồn của pipeline. Các phép trung gian như `filter`, `map`, `peek`, `limit` xây đường xử lý; các terminal như `sum`, `count`, `findFirst`, `anyMatch` yêu cầu đánh giá.

Ví dụ:

~~~java
// Mảnh mã minh họa:
IntStream prepared = IntStream.range(0, 10)
        .filter(i -> i % 3 == 0)
        .map(i -> i * 2);
~~~

Đến đây thông thường chưa đánh giá toàn bộ từng phần tử; nguồn và pipeline đã được dựng. Khi dùng:

~~~java
int first = prepared.findFirst().orElse(-1); // 0
~~~

nó có thể dừng ngay khi tìm được phần tử đầu tiên đi qua pipeline.

### Cảnh giác với `peek`

~~~java
// Mảnh mã minh họa, không dùng cho audit bắt buộc:
long count = IntStream.range(0, 1_000)
        .peek(System.out::println)
        .count();
~~~

`count()` có thể dùng đặc tính `SIZED` của nguồn và pipeline để xác định kết quả mà không cần duyệt mỗi phần tử. Vì vậy **không cam kết** `peek` được gọi 1.000 lần. Đây là hành vi tối ưu hợp lệ của Stream API. Việc gọi một terminal không đồng nghĩa mọi lambda trung gian chắc chắn chạy cho mọi phần tử.

Nếu phải đảm bảo một thao tác xảy ra với mọi số, dùng cấu trúc xử lý tường minh (`for` hoặc `forEach` thích hợp, với chính sách lỗi/thứ tự rõ ràng) thay vì đặt side effect bắt buộc trong `peek`.

### Range lớn không có nghĩa cần tạo mảng khổng lồ

`IntStream.range(0,1_000_000)` không tự cấp phát mảng một triệu số như `toArray()`. Tuy nhiên, nếu bạn gọi `toArray()`, `boxed().toList()` hoặc một terminal phải giữ toàn bộ phần tử, thì bộ nhớ vẫn tăng theo kích thước kết quả. Tối ưu hóa từ Stream là mô hình xử lý, **không phải phép miễn trừ chi phí bộ nhớ**.

## 14. Ví dụ chạy đầy đủ 5: short-circuit trên range

Tạo file **IntRangeShortCircuitDemo.java**:

~~~java
import java.util.stream.IntStream;

public class IntRangeShortCircuitDemo {

    public static void main(String[] args) {
        System.out.println("prepare");

        IntStream source = IntStream.range(1, 10)
                .filter(n -> {
                    System.out.println("test=" + n);
                    return n % 4 == 0;
                })
                .map(n -> {
                    System.out.println("map=" + n);
                    return n * 10;
                });

        System.out.println("before-terminal");
        int first = source.findFirst().orElse(-1);
        System.out.println("first=" + first);
    }
}
~~~

Chạy JDK 17+:

~~~bash
javac IntRangeShortCircuitDemo.java
java IntRangeShortCircuitDemo
~~~

Stdout:

~~~text
prepare
before-terminal
test=1
test=2
test=3
test=4
map=4
first=40
~~~

Vì đây là stream tuần tự có encounter order, `findFirst()` yêu cầu phần tử đầu tiên thỏa filter. `1,2,3` bị loại, `4` đi qua mapper thành `40` rồi terminal kết thúc. `5..9` không bị xử lý trong ví dụ này.

Đây là một ví dụ để **hiểu cơ chế**, không phải lời khuyên dùng `System.out.println` bên trong pipeline production. Nếu bật `parallel()`, thứ tự đánh giá và log side effect có thể thay đổi; không khẳng định stdout giữ nguyên.

## 15. `range` so với `rangeClosed` khi tạo lưới hai chiều

Đôi khi cần tạo mọi cặp hàng/cột, ví dụ bảng có `rows` hàng và `columns` cột, đánh số từ 0.

Với hai kích thước không âm, dùng hai khoảng nửa mở:

~~~java
// Mảnh mã minh họa:
List<String> cells = IntStream.range(0, rows)
        .boxed()
        .flatMap(r -> IntStream.range(0, columns)
                .mapToObj(c -> "(" + r + "," + c + ")"))
        .toList();
~~~

Ở đây:

- Range bên ngoài tạo các chỉ số hàng từ 0 đến `rows-1`.
- Range bên trong tạo các chỉ số cột từ 0 đến `columns-1` cho từng hàng.
- `flatMap` trải các dòng thành một `Stream<String>` chứa mọi cặp (r,c).
- Nếu `rows==0` hoặc `columns==0`, kết quả rỗng, đúng với bảng không có ô.
- Nếu dữ liệu quá lớn, tạo `List` của toàn bộ các cặp có thể tốn bộ nhớ; có thể xử lý từng hàng bằng vòng lặp khi không cần materialize.

### Ví dụ chạy đầy đủ 6: lưới 2 × 3

Tạo file **IntRangeGridDemo.java**:

~~~java
import java.util.List;
import java.util.stream.IntStream;

public class IntRangeGridDemo {

    public static void main(String[] args) {
        int rows = 2;
        int columns = 3;

        List<String> cells = IntStream.range(0, rows)
                .boxed()
                .flatMap(r -> IntStream.range(0, columns)
                        .mapToObj(c -> "(" + r + "," + c + ")"))
                .toList();

        System.out.println("cells=" + cells);
        System.out.println("size=" + cells.size());

        long emptyGrid = IntStream.range(0, 0)
                .boxed()
                .flatMap(r -> IntStream.range(0, 3).boxed())
                .count();

        System.out.println("empty-grid=" + emptyGrid);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac IntRangeGridDemo.java
java IntRangeGridDemo
~~~

Stdout:

~~~text
cells=[(0,0), (0,1), (0,2), (1,0), (1,1), (1,2)]
size=6
empty-grid=0
~~~

Đối với grid có kích thước lớn, công thức `rows * columns` với `int` có thể overflow trước khi so với size; hãy chuyển sang `long` trước khi nhân nếu cần kiểm tra giới hạn: `(long) rows * columns`. Cần phân biệt **mô hình nguồn** (các index) với **việc lưu kết quả** (List cặp) để tránh cấp phát khổng lồ ngoài ý muốn.

## 16. Parallel stream: thứ tự và tính đúng đắn

`IntStream.range` và `rangeClosed` tạo dãy có thứ tự tự nhiên tăng dần, rất tiện để chia công việc độc lập khi cần xử lý song song. Nhưng **`parallel()` không tự tăng tốc mọi bài toán**.

Ví dụ tổng hợp thuần:

~~~java
long total = IntStream.rangeClosed(1, 1_000)
        .parallel()
        .asLongStream()
        .sum(); // 500500
~~~

Terminal `sum()` phù hợp cho phép gộp có identity và tính kết hợp; với miền này kết quả không phụ thuộc thứ tự chạy worker.

### Encounter order không đồng nghĩa thứ tự thực thi callback

`range` có encounter order. `boxed().toList()` trên pipeline có thứ tự thường trả list theo thứ tự đó, kể cả khi pipeline được xử lý song song. Nhưng:

~~~java
IntStream.range(0, 5)
        .parallel()
        .forEach(System.out::println);
~~~

không có stdout thứ tự cố định. Nếu thực sự cần in theo thứ tự gặp phần tử, `forEachOrdered` hỗ trợ điều đó (đổi lại có thể giảm lợi ích parallel).

Không dựa vào `peek`, `map` có side effect hoặc một `ArrayList` bị sửa từ nhiều thread để bảo đảm việc xử lý đúng thứ tự. Nếu bài toán có phụ thuộc giữa lần lặp trước/sau, vòng `for` tuần tự hoặc một thiết kế state machine rõ ràng có thể đúng và dễ bảo trì hơn.

### Ví dụ chạy đầy đủ 7: kết quả song song nhưng có thứ tự

Tạo file **IntRangeParallelDemo.java**:

~~~java
import java.util.List;
import java.util.stream.IntStream;

public class IntRangeParallelDemo {

    public static void main(String[] args) {
        long sum = IntStream.rangeClosed(1, 1_000)
                .parallel()
                .asLongStream()
                .sum();

        List<Integer> squares = IntStream.range(1, 6)
                .parallel()
                .map(n -> n * n)
                .boxed()
                .toList();

        System.out.println("sum=" + sum);
        System.out.println("squares=" + squares);
    }
}
~~~

Biên dịch/chạy JDK 17+:

~~~bash
javac IntRangeParallelDemo.java
java IntRangeParallelDemo
~~~

**Stdout chính xác:**

~~~text
sum=500500
squares=[1, 4, 9, 16, 25]
~~~

Đoạn trên chỉ dùng tính toán thuần, không có mutation dùng chung. `toList()` bảo toàn encounter order của nguồn có thứ tự; thứ tự **thực thi** các task song song không cần được dự đoán để xác định thứ tự **kết quả**.

Nếu mục tiêu chỉ là tổng 1..1000, một công thức số học đơn giản có thể nhanh hơn; ví dụ không nhằm chứng minh `parallel()` là lựa chọn hiệu năng tốt hơn. Hãy đo workload thật bằng một công cụ benchmark như JMH trước khi tối ưu.

## 17. `range` chỉ tăng từng bước 1: nếu cần bước nhảy khác thì sao?

`IntStream.range(a,b)` và `rangeClosed(a,b)` luôn tạo các số nguyên **liên tiếp tăng 1**. Chúng không có đối số `step`.

Để lấy số chẵn, có thể lọc:

~~~java
IntStream.range(0, 10)
        .filter(n -> n % 2 == 0)
        .toArray(); // [0, 2, 4, 6, 8]
~~~

Hoặc ánh xạ một range chỉ số:

~~~java
IntStream.range(0, 5)
        .map(i -> 2 * i)
        .toArray(); // [0, 2, 4, 6, 8]
~~~

Phương án `map(i -> 2*i)` thuận tiện khi số bước đã biết. Chú ý overflow khi phép nhân vượt giới hạn int.

`IntStream.iterate(seed, operator)` có từ Java 8 cho dãy sinh theo hàm chuyển tiếp, và overload có điều kiện dừng `iterate(seed, hasNext, next)` từ Java 9. Dùng `iterate` khi thật sự cần cấp số cộng/cơ chế sinh khác, nhưng phải xem xét điểm dừng, overflow và khả năng stream vô hạn.

~~~java
// Mảnh mã minh họa JDK 17+:
IntStream.iterate(0, i -> i < 10, i -> i + 2)
        .toArray(); // [0, 2, 4, 6, 8]
~~~

**Không dùng `rangeClosed(10,0)` để tạo dãy giảm**. Cận đầu lớn hơn cận cuối cho stream rỗng. Nếu cần đếm ngược, dùng dãy chỉ số rồi chuyển đổi, ví dụ:

~~~java
IntStream.rangeClosed(1, 5)
        .map(i -> 6 - i)
        .toArray(); // [5, 4, 3, 2, 1]
~~~

Cách chuyển đổi phải xét giới hạn phép tính và contract nếu miền rất lớn.

## 18. So sánh với vòng `for`: chọn API theo mục tiêu

Đôi khi `IntStream.range` thay thế vòng `for` có chỉ số:

~~~java
for (int i = 0; i < list.size(); i++) {
    process(i, list.get(i));
}
~~~

và:

~~~java
IntStream.range(0, list.size())
        .forEach(i -> process(i, list.get(i)));
~~~

Hai đoạn là mảnh mã minh họa, cần có `list` và `process`.

**Chọn Stream** khi các chỉ số dùng để tạo một pipeline dữ liệu rõ ràng, chẳng hạn `mapToObj`, `filter`, `findFirst`, `count`, `sum`. **Chọn vòng lặp** nếu:

- Cần `break`, `continue`, `return` khỏi method chứa vòng lặp.
- Cần xử lý checked exception theo từng phần tử bằng `try/catch`.
- Công việc chứa nhiều state transition, rollback hoặc checkpoint.
- Mỗi phần tử phải sinh side effect theo thứ tự với quy tắc lỗi nghiêm ngặt.
- Cần điều chỉnh biến chỉ số không đơn giản là tăng 1 hoặc thay đổi phạm vi trong quá trình duyệt.

Đừng cho rằng `forEach` của Stream luôn đồng nghĩa với `for` cổ điển; đặc biệt với parallel, thứ tự và thread thực thi khác. Trái lại, một pipeline `range(0,n).map(...).sum()` có thể cực kỳ ngắn và rõ hơn vòng lặp có accumulator.

## 19. Kích thước, chi phí bộ nhớ và hiệu năng

Bản thân dãy range là một nguồn được mô tả bằng cận; nó không nhất thiết tạo một mảng chứa toàn bộ các số. Nhưng:

~~~java
int[] all = IntStream.range(0, 1_000_000).toArray();
~~~

đòi một mảng một triệu số; và:

~~~java
List<Integer> boxed = IntStream.range(0, 1_000_000)
        .boxed()
        .toList();
~~~

đòi một danh sách nhiều đối tượng/wrapper `Integer` tương ứng. Cần cân nhắc bộ nhớ trước khi materialize dãy lớn.

Một pipeline terminal như `sum`, `count`, `average`, `anyMatch` thường không cần lưu tất cả phần tử cùng lúc. Nhưng có thao tác stateful như `sorted` hoặc `distinct` có thể tiêu tốn thêm bộ nhớ; không quy mọi Stream thành O(1) bộ nhớ.

### `count()` có thể tối ưu

Nguồn `range` biết số phần tử theo miền, nên `count()` có thể tính số lượng rất nhanh trong các trường hợp phù hợp mà không tạo từng số. Điều này cũng giải thích vì sao **side effects trong `peek` không được dùng làm công việc bắt buộc** nếu terminal không cần thực thi chúng.

### `IntStream` so với `Stream<Integer>`

Trong workload tính số, `IntStream` giúp giảm boxing/unboxing và cung cấp sẵn `sum`, `average`, `summaryStatistics`. Nhưng không tự kết luận một Stream luôn nhanh hơn vòng lặp `for`. Hiệu năng còn phụ thuộc JDK, JIT, data size, kiểu phép biến đổi, bộ nhớ, parallel overhead và cách benchmark.

### Khi nào cần đo?

Nếu một đoạn code nằm trên đường nóng (*hot path*) hoặc xử lý hàng triệu phần tử, dùng JMH và dữ liệu đại diện để kiểm tra. Không rút ra kết luận chung từ một lần `System.nanoTime()` quanh hai đoạn nhỏ vì warm-up/JIT/GC dễ làm số đo sai.

## 20. Lỗi thường gặp và cách tránh

| Lỗi/ngộ nhận | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `range(1,5)` có cả 5 | Cận cuối exclusive | Dùng `rangeClosed(1,5)` |
| `rangeClosed(0,list.size())` là mọi index hợp lệ | Bao gồm cả `size`, vượt chỉ số cuối | Dùng `range(0,list.size())` |
| `range(a,a)` có một phần tử | Khoảng nửa mở rỗng | Dùng `rangeClosed(a,a)` nếu muốn một số |
| `range(a,b)` với a > b tự đếm ngược | Hai factory chỉ tạo dãy tăng | Dùng phép biến đổi hoặc `iterate` có điều kiện đúng |
| `rangeClosed(1,n)` luôn báo lỗi khi n không dương | Cận đảo cho dãy rỗng, không là validation nghiệp vụ | Validate n riêng |
| `range(start,end+1)` luôn tương đương `rangeClosed` | `end+1` có thể overflow | Dùng `rangeClosed` trực tiếp |
| `sum()` luôn tính được tổng số học lớn | `IntStream.sum` trả int | `asLongStream().sum()` hoặc kiểu lớn hơn |
| `count()` trả int | API trả long | Dùng `long` |
| Dùng cùng một Stream cho `sum` rồi `count` | Stream one-shot | Tạo nguồn mới hoặc `summaryStatistics` |
| `peek` luôn chạy một lần mỗi số | Terminal có thể tối ưu, short-circuit | Không để side effect bắt buộc ở `peek` |
| `range(0,linkedList.size()).mapToObj(linkedList::get)` luôn nhanh | `get(i)` có thể O(n) | Dùng iterator/stream phần tử |
| `boxed()` giữ primitive int | Chuyển thành `Stream<Integer>` | Chỉ boxing khi cần object |
| `mapToObj` giống `map` | Một bên trả object stream, bên kia int stream | Chọn theo kiểu output |
| Parallel `forEach` luôn theo thứ tự tăng | Không có cam kết thứ tự thực thi | `forEachOrdered` hoặc tuần tự |
| `IntStream.range` tạo sẵn toàn bộ list | Stream source không đồng nghĩa materialization | Chỉ tạo list/array nếu cần |
| Java 8 có `Stream.toList()` | Được bổ sung ở Java 16 | Nếu target Java 8, dùng `collect(Collectors.toList())` |

## 21. Bài tập thực hành

**Bài 1 — Đọc cận:** Dự đoán `range(3,7)`, `rangeClosed(3,7)`, `range(5,5)`, `rangeClosed(5,5)`, `rangeClosed(7,3)`. Kiểm chứng bằng `toArray()` và `Arrays.toString`.

**Bài 2 — Index list:** Với `List.of("a","bb","ccc")`, tạo `List<String>` có dạng `0:a,1:bb,2:ccc` bằng `range(0,size)`. Sau đó dùng `filter` và `findFirst` để tìm index đầu tiên của chuỗi dài ít nhất 2.

**Bài 3 — Sửa off-by-one:** Cho đoạn `rangeClosed(0,list.size()).mapToObj(list::get)`; giải thích lỗi trên list ba phần tử và list rỗng. Viết phiên bản dùng `range` đúng.

**Bài 4 — Tổng và trung bình:** Tính tổng, count và average của 1..N bằng `rangeClosed`. Nêu kiểu kết quả của từng terminal. Kiểm tra N=0, N=1, N=100. Khi nào nên dùng `summaryStatistics()`?

**Bài 5 — Overflow:** Tính tổng 1..65536 bằng `IntStream.sum()` và `asLongStream().sum()`. Giải thích vì sao hai kết quả khác, và khi nào `long` cũng không đủ.

**Bài 6 — Cận lớn:** Kiểm tra `rangeClosed(Integer.MAX_VALUE-2,Integer.MAX_VALUE)`, `rangeClosed(MAX,MAX)` và `rangeClosed(MIN,MAX).count()`. Không dùng `for (int i=start; i<=MAX; i++)` vì nguy cơ overflow khiến vòng không kết thúc.

**Bài 7 — Bước nhảy 2:** Tạo dãy 0,2,4,6,8 bằng (a) `range` + `filter`, (b) `range` + `map`, và (c) `iterate` có điều kiện dừng ở Java 9+. So sánh độ rõ ràng, thứ tự, rủi ro overflow.

**Bài 8 — Grid:** Dùng hai `range(0,n)` với `flatMap` tạo các tọa độ bảng 3×2. Giải thích số phần tử, thứ tự và trường hợp kích thước một chiều bằng 0.

**Bài 9 — Parallel:** So sánh `parallel().map(...).boxed().toList()` với `parallel().forEach(System.out::println)`. Vì sao kết quả danh sách có thứ tự còn thứ tự in lại không được cam kết? Thử `forEachOrdered`.

**Bài 10 — Chọn cấu trúc:** Viết cùng một thuật toán tìm lỗi đầu tiên trong một list bằng vòng `for` và bằng `IntStream.range(0,size).filter(...).findFirst()`. So sánh độ dễ đọc khi cần thêm số dòng, checked exception hoặc nhiều bước rollback.

**Bài 11 — Không phụ thuộc peek:** Tạo `IntStream.range(0,100).peek(log).count()` và đọc đặc tả vì sao logging không phải side effect được bảo đảm. Thiết kế phiên bản xử lý bắt buộc cho từng chỉ số bằng vòng lặp hoặc cơ chế action terminal thích hợp.

## 22. Checklist khi dùng range trong sản phẩm

- Bạn muốn cận cuối **bao gồm** hay **loại trừ**? API đang phản ánh đúng yêu cầu chưa?
- Với index list, có dùng `range(0,size)` và xử lý list rỗng không?
- Có đang dùng `end + 1` gây overflow khi end có thể là `Integer.MAX_VALUE` không?
- Nếu `start>end` trả stream rỗng, nghiệp vụ có cần báo lỗi riêng không?
- Có cần primitive `IntStream` hay đã boxing sang `Integer` mà không cần thiết?
- Nếu cần object đầu ra, nên dùng `mapToObj` hay `boxed`?
- Tổng có thể vượt `int` không? Đã dùng `long` hoặc kiểu lớn hơn khi cần chưa?
- `count()` và công thức kích thước có dùng kiểu `long` khi miền rộng không?
- Có vô tình dùng lại stream sau terminal hay dùng `peek` cho side effect bắt buộc không?
- Nguồn có thứ tự; terminal/callback trong parallel có đang giả định sai thứ tự thực thi không?
- Với `List` không hỗ trợ random access hiệu quả, có đang dùng `get(i)` trong range gây O(n²) không?
- Materialization qua `toArray()`/`boxed().toList()` có phù hợp giới hạn bộ nhớ không?
- API và cú pháp đang sử dụng có phù hợp JDK mục tiêu không? `range`/`rangeClosed` từ Java 8, `toList()` từ Java 16.

## 23. Tóm tắt

`IntStream.range(startInclusive,endExclusive)` tạo dãy `int` **không có cận cuối**, còn `IntStream.rangeClosed(startInclusive,endInclusive)` **có cận cuối**. Cả hai có từ Java 8 và phù hợp cho việc tạo nguồn số nguyên theo bước tăng 1 trong Java hiện đại.

`range(0,size)` là lựa chọn tự nhiên cho **index hợp lệ**; `rangeClosed(1,n)` phù hợp cho bài toán “từ 1 đến n có cả n”. Chú ý khoảng rỗng, cận `Integer.MAX_VALUE`, tổng `int` có thể overflow, `count()` trả `long`, stream chỉ dùng một lần và nguồn không đồng nghĩa dữ liệu đã được materialize.

Cuối cùng, hãy kết hợp range với terminal phù hợp và giữ các lambda không gây can thiệp nguồn; dùng vòng lặp khi control flow và side effects cần được biểu diễn tường minh. Hiểu cận, kiểu số và thời điểm đánh giá sẽ giúp tránh phần lớn lỗi off-by-one và hành vi khó dự đoán.
