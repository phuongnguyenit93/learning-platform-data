# Tạo khoảng số bằng range và rangeClosed

Khi cần đánh số thứ tự cho danh sách, duyệt các vị trí trong mảng, sinh mã kiểm thử hoặc tính toán trên một dãy số liên tiếp, ta thường viết vòng lặp `for`. **Java Stream API** cung cấp cách khai báo khoảng số trực tiếp bằng **`range`** và **`rangeClosed`**. Hai phương thức này giúp biểu diễn chính xác tập giá trị cần xử lý, sau đó kết hợp với `filter`, `map`, `reduce`, `collect` hoặc các phép toán kết thúc khác.

Bài học thuộc chương **Dãy số và Stream vô hạn** của module **JAVA_STREAM_API**, tập trung vào cách tạo **dãy hữu hạn** bằng `IntStream` và `LongStream`. Khác với `Stream.iterate` hoặc `Stream.generate` có thể tạo dãy không kết thúc, `range` và `rangeClosed` xác định hai đầu khoảng ngay khi xây dựng nguồn. Mục tiêu là hiểu ranh giới bao gồm/không bao gồm, dùng đúng kiểu dữ liệu, tránh lỗi lệch một đơn vị (*off-by-one*) và vận dụng đặc tính lazy, giới hạn tài nguyên của Stream.

## 1. Vì sao cần một nguồn Stream dạng khoảng số?

Hãy xem yêu cầu đơn giản: lấy các số nguyên từ 1 đến 5, tính tổng và tạo tên cho năm bước xử lý.

Với vòng lặp, ta trực tiếp điều khiển biến đếm:

~~~java
int sum = 0;
for (int number = 1; number <= 5; number++) {
    sum += number;
}
System.out.println(sum); // 15
~~~

Với Stream, phần **tạo dãy** tách khỏi phần **xử lý dãy**:

~~~java
import java.util.stream.IntStream;

int sum = IntStream.rangeClosed(1, 5).sum();
System.out.println(sum); // 15
~~~

`IntStream.rangeClosed(1, 5)` mô tả dãy `1, 2, 3, 4, 5`; `sum()` yêu cầu kết quả tổng. Nếu chỉ muốn từ 1 đến 4 thì dùng `IntStream.range(1, 5)`. Đây chính là khác biệt quan trọng nhất giữa hai API.

## 2. range và rangeClosed khác nhau thế nào?

Hai phương thức là các **static factory method** trên `IntStream` và `LongStream`:

~~~java
IntStream.range(int startInclusive, int endExclusive)
IntStream.rangeClosed(int startInclusive, int endInclusive)

LongStream.range(long startInclusive, long endExclusive)
LongStream.rangeClosed(long startInclusive, long endInclusive)
~~~

Tên tham số nói rõ ranh giới:

- `startInclusive`: **bao gồm** điểm bắt đầu.
- `endExclusive`: **không bao gồm** điểm kết thúc.
- `endInclusive`: **bao gồm** điểm kết thúc.

Dùng ký hiệu toán học, với `a <= b`:

- `range(a, b)` tương ứng **`[a, b)`** — đóng bên trái, mở bên phải.
- `rangeClosed(a, b)` tương ứng **`[a, b]`** — đóng ở cả hai đầu.

| Lời gọi | Giá trị được tạo | Số phần tử |
|---|---|---|
| `IntStream.range(2, 6)` | `2, 3, 4, 5` | 4 |
| `IntStream.rangeClosed(2, 6)` | `2, 3, 4, 5, 6` | 5 |
| `IntStream.range(5, 5)` | Không có | 0 |
| `IntStream.rangeClosed(5, 5)` | `5` | 1 |
| `IntStream.range(6, 5)` | Không có | 0 |
| `IntStream.rangeClosed(6, 5)` | Không có | 0 |
| `IntStream.range(-2, 2)` | `-2, -1, 0, 1` | 4 |

Số phần tử với khoảng hợp lệ được xác định bằng:

- `range(start, end)`: `end - start` phần tử khi `start < end`, ngược lại 0.
- `rangeClosed(start, end)`: `end - start + 1` phần tử khi `start <= end`, ngược lại 0.

Các công thức trên mang ý nghĩa **toán học**. Nếu tự tính bằng kiểu `int` hoặc `long` trong chương trình, phép trừ/cộng có thể bị tràn số với ranh giới cực lớn. Khi chỉ cần số phần tử, dùng `count()`; khi tự làm phép tính, phải chọn kiểu số và kiểm soát tràn số phù hợp.

### Hình dung bằng trục số

~~~text
range(2, 6)
    2 --- 3 --- 4 --- 5 --- (6)
    ^                         ^
  lấy 2                    bỏ 6

rangeClosed(2, 6)
    2 --- 3 --- 4 --- 5 --- 6
    ^                         ^
  lấy 2                     lấy 6
~~~

Mẹo nhớ: **`range` loại điểm cuối; `rangeClosed` giữ điểm cuối**. Chữ *Closed* trong toán học gắn với khoảng đóng và ranh giới được bao gồm.

## 3. Ví dụ Java hoàn chỉnh: tạo dãy, tổng hợp và đánh số

Đoạn code sau chạy trên **Java 8 trở lên**; các ví dụ đều dùng Stream API cơ bản mà không yêu cầu `Stream.toList()` của JDK mới.

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class RangeOverviewDemo {
    public static void main(String[] args) {
        // 2, 3, 4, 5: điểm cuối 6 bị loại.
        List<Integer> halfOpen = IntStream.range(2, 6)
            .boxed()
            .collect(Collectors.toList());

        // 2, 3, 4, 5, 6: điểm cuối 6 được giữ.
        List<Integer> closed = IntStream.rangeClosed(2, 6)
            .boxed()
            .collect(Collectors.toList());

        // Dãy 1..10 có tổng bằng 55.
        int sum = IntStream.rangeClosed(1, 10).sum();

        // Chuyển chỉ số 0..size-1 thành tên có số thứ tự 1..size.
        List<String> names = Arrays.asList("An", "Bình", "Chi");
        List<String> numbered = IntStream.range(0, names.size())
            .mapToObj(index -> (index + 1) + ". " + names.get(index))
            .collect(Collectors.toList());

        System.out.println(halfOpen);
        System.out.println(closed);
        System.out.println(sum);
        System.out.println(numbered);
    }
}
~~~

Kết quả:

~~~text
[2, 3, 4, 5]
[2, 3, 4, 5, 6]
55
[1. An, 2. Bình, 3. Chi]
~~~

Có ba thao tác đáng chú ý:

1. `IntStream.range(...)` và `rangeClosed(...)` trả về **`IntStream`**, tức luồng giá trị nguyên thủy `int`.
2. `boxed()` biến các phần tử `int` thành `Integer` để có thể dùng collector tạo `List<Integer>`.
3. `mapToObj(...)` biến mỗi giá trị `int` thành một đối tượng (ở đây là `String`), rồi `collect` tạo ra `List<String>`.

Trong Java 16+, có thể thay `collect(Collectors.toList())` bằng `toList()` nếu muốn nhận danh sách không thể sửa. Hợp đồng của `Collectors.toList()` không bảo đảm cụ thể khả năng sửa đổi của danh sách trả về; hãy chọn collector phù hợp nếu ứng dụng cần một collection có tính chất xác định.

## 4. Khoảng số là Stream nguyên thủy, không phải Stream<Integer>

Java có ba họ Stream nguyên thủy: `IntStream`, `LongStream` và `DoubleStream`. Tuy nhiên, **chỉ `IntStream` và `LongStream` cung cấp `range`, `rangeClosed`**. Không có `DoubleStream.range(...)` trong API chuẩn.

| Đầu vào | Loại Stream trả về | Ví dụ |
|---|---|---|
| `IntStream.range(0, 3)` | `IntStream` | `0, 1, 2` |
| `IntStream.rangeClosed(0, 3)` | `IntStream` | `0, 1, 2, 3` |
| `LongStream.range(0L, 3L)` | `LongStream` | `0L, 1L, 2L` |
| `LongStream.rangeClosed(0L, 3L)` | `LongStream` | `0L, 1L, 2L, 3L` |

Nhờ luồng nguyên thủy, các phép tính số học thường tránh chi phí **boxing/unboxing** giữa `int` và `Integer`. Ta có thể dùng trực tiếp:

~~~java
import java.util.stream.IntStream;

long quantity = IntStream.range(0, 100).count();     // 100
int maximum = IntStream.rangeClosed(1, 5)
    .max()
    .orElseThrow(IllegalStateException::new);        // 5
double average = IntStream.rangeClosed(1, 5)
    .average()
    .orElseThrow(IllegalStateException::new);        // 3.0
~~~

`count()` trả về `long`, trong khi `sum()` của `IntStream` trả về `int` và `sum()` của `LongStream` trả về `long`. `average()` trả về `OptionalDouble` vì dãy có thể rỗng; `max()`, `min()` trả về kiểu `OptionalInt` hoặc `OptionalLong` tương ứng.

### Chuyển kiểu khi cần đối tượng

Không thể gán trực tiếp một `IntStream` cho biến `Stream<Integer>`:

~~~java
// Không hợp lệ vì IntStream khác Stream<Integer>:
// Stream<Integer> values = IntStream.range(1, 4);
~~~

Thay bằng `boxed()` hoặc `mapToObj(...)`:

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<Integer> numbers = IntStream.range(1, 4)
    .boxed()
    .collect(Collectors.toList()); // [1, 2, 3]

List<String> labels = IntStream.rangeClosed(1, 3)
    .mapToObj(number -> "Bước " + number)
    .collect(Collectors.toList()); // [Bước 1, Bước 2, Bước 3]
~~~

Với `LongStream`, cũng có `boxed()` và `mapToObj(...)`. Hãy giữ luồng nguyên thủy càng lâu càng phù hợp khi mục tiêu chính là tính toán số, và chỉ chuyển sang đối tượng khi cần tạo kiểu dữ liệu phong phú hơn.

## 5. Trường hợp thường gặp: chỉ số bắt đầu từ 0

Trong Java, các vị trí hợp lệ của một mảng hoặc `List` có `n` phần tử là **`0` đến `n - 1`**. Do đó `range(0, n)` là lựa chọn tự nhiên:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;

List<String> colors = Arrays.asList("đỏ", "xanh", "vàng");

IntStream.range(0, colors.size())
    .forEach(index ->
        System.out.println(index + ": " + colors.get(index))
    );
~~~

Kết quả:

~~~text
0: đỏ
1: xanh
2: vàng
~~~

Trong trường hợp này, `range(0, colors.size())` cho đúng 3 chỉ số: 0, 1 và 2. Nếu viết `rangeClosed(0, colors.size())`, Stream còn phát ra chỉ số **3**, dẫn đến `IndexOutOfBoundsException` khi gọi `colors.get(3)`.

Với danh sách rỗng, `range(0, 0)` tạo dãy rỗng một cách tự nhiên, không cần xử lý riêng. Nếu chỉ cần duyệt **giá trị** mà không cần chỉ số, viết `colors.stream()` thường đơn giản hơn. Ngoài ra, việc gọi `get(index)` liên tiếp phù hợp nhất với cấu trúc hỗ trợ truy cập chỉ số hiệu quả như `ArrayList` hoặc mảng; dùng cùng cách này với `LinkedList` có thể tạo chi phí duyệt lớn.

### Biến vị trí thành phần tử có cấu trúc

Ví dụ tạo các bản ghi hiển thị với cả vị trí và giá trị:

~~~java
List<String> descriptions = IntStream.range(0, colors.size())
    .mapToObj(index -> "Mục " + (index + 1) + ": " + colors.get(index))
    .collect(java.util.stream.Collectors.toList());
~~~

`mapToObj` nhận một hàm từ `int` sang một đối tượng `R`. Đây là ví dụ điển hình của cách **nguồn khoảng số** kết hợp với **Function** trong pipeline.

## 6. Khi nào dùng rangeClosed?

`rangeClosed` phù hợp khi nghiệp vụ nêu rõ **cả ngày/giá trị đầu và cuối đều được tính**:

- Dãy các số tự nhiên từ 1 đến 10.
- Các vòng thử từ lần 1 đến lần `n`.
- Các ngày trong tháng nếu biểu diễn bằng số ngày từ 1 đến ngày cuối cùng.
- Các bậc mức từ mức thấp nhất đến mức cao nhất, kể cả hai đầu.

Ví dụ cộng từ 1 đến `n`:

~~~java
int n = 10;
int result = IntStream.rangeClosed(1, n).sum();
System.out.println(result); // 55
~~~

Với `n = 0`, `rangeClosed(1, 0)` rỗng và `sum()` trả 0. Nếu nghiệp vụ cho phép `n` âm, cần xác định rõ chính sách xử lý; trả 0 theo mặc định của dãy rỗng có thể che giấu đầu vào sai.

Ví dụ biểu diễn số ngày trong một tháng đã biết:

~~~java
import java.time.YearMonth;
import java.util.stream.IntStream;

YearMonth month = YearMonth.of(2024, 2);

IntStream.rangeClosed(1, month.lengthOfMonth())
    .mapToObj(month::atDay)
    .forEach(System.out::println);
~~~

Trong năm nhuận 2024, tháng 2 có 29 ngày nên pipeline phát các ngày từ `2024-02-01` đến `2024-02-29`. `month::atDay` chuyển mỗi số ngày hợp lệ thành `LocalDate`. Ở đây `rangeClosed` diễn đạt quy tắc *bao gồm ngày cuối cùng* rõ hơn so với việc cộng 1 vào giới hạn của `range`.

## 7. Dùng LongStream.range và rangeClosed cho khoảng lớn

Nếu đầu vào là `long` hoặc vượt khả năng biểu diễn của `int`, dùng `LongStream`:

~~~java
import java.util.stream.LongStream;

long from = 3_000_000_000L;
long toInclusive = 3_000_000_003L;

LongStream.rangeClosed(from, toInclusive)
    .forEach(System.out::println);
~~~

Kết quả:

~~~text
3000000000
3000000001
3000000002
3000000003
~~~

`IntStream` chỉ tạo giá trị kiểu `int`, có miền từ `Integer.MIN_VALUE` đến `Integer.MAX_VALUE`. `LongStream` hỗ trợ giá trị `long` rộng hơn, nhưng cũng **hữu hạn**, không phải số nguyên có độ chính xác tùy ý.

Đừng nhầm kiểu phần tử với kiểu kết quả tổng hợp:

~~~java
// Tổng từ 1 đến 100000 là 5_000_050_000, vượt Integer.MAX_VALUE.
long safeSum = IntStream.rangeClosed(1, 100_000)
    .asLongStream()
    .sum(); // 5000050000
~~~

Nếu gọi `IntStream.rangeClosed(1, 100_000).sum()`, tổng trả về là `int` và có thể **tràn số**. `asLongStream()` chuyển các phần tử sang `long` trước khi cộng, nhưng `long` cũng có giới hạn: tổng quá lớn vẫn có thể tràn. Với yêu cầu độ chính xác vượt `long`, có thể cân nhắc `BigInteger` hoặc công thức số học được kiểm tra điều kiện.

## 8. Lazy evaluation: khoảng có thể lớn mà không tạo sẵn mảng

Gọi `IntStream.range(1, 1_000_000)` **không tạo sẵn một `List` chứa gần một triệu đối tượng**. Khoảng số được biểu diễn như **nguồn** để Stream lấy phần tử khi pipeline xử lý.

~~~java
import java.util.stream.IntStream;

IntStream numbers = IntStream.rangeClosed(1, 1_000_000)
    .filter(number -> number % 17 == 0);

// Tới đây mới mô tả nguồn và điều kiện, chưa duyệt hết các số.

int first = numbers.findFirst()
    .orElse(-1);

System.out.println(first); // 17
~~~

`findFirst()` là phép toán kết thúc có khả năng **dừng sớm**. Vì nguồn có thứ tự tăng dần và phần tử đầu tiên chia hết cho 17 là 17, pipeline này không cần duyệt tất cả một triệu số.

~~~mermaid
flowchart LR
    A["IntStream.rangeClosed(1, 1_000_000)"] --> B["filter(n % 17 == 0)"]
    B --> C["findFirst()"]
    C --> D["OptionalInt: 17"]
~~~

Hai điểm cần phân biệt:

1. **Tạo khoảng bằng range/rangeClosed** chỉ thiết lập nguồn; bản thân nó chưa phải một terminal operation.
2. **Thu thập thành `List`, `toArray()` hoặc dùng `forEach`** có thể yêu cầu duyệt một lượng lớn phần tử, tiêu tốn bộ nhớ hoặc thời gian. Lazy không khiến kết quả lớn trở nên miễn phí.

Ví dụ `LongStream.range(0L, 1_000_000_000_000L).limit(3).toArray()` chỉ yêu cầu ba phần tử đầu tiên. Nếu bỏ `limit(3)`, thao tác thu toàn bộ nghìn tỷ giá trị thành mảng là không thực tế và sẽ vượt giới hạn kích thước mảng Java.

### range là hữu hạn; iterate/generate có thể vô hạn

`range` và `rangeClosed` luôn mô tả khoảng số hữu hạn theo ranh giới đã cho. Ngược lại:

~~~java
import java.util.stream.IntStream;

// Dãy giảm vô hạn theo lý thuyết, lấy 5 phần tử đầu.
IntStream.iterate(10, n -> n - 2)
    .limit(5)
    .forEach(System.out::println); // 10, 8, 6, 4, 2
~~~

`IntStream.iterate(seed, operator)` (Java 8+) không có giới hạn dừng trong cách gọi này; pipeline cần `limit` hoặc một phép toán kết thúc có thể hoàn thành theo logic tương ứng. Với mã chạy đủ lâu, phép cộng/trừ trên `int` trong `iterate` cũng có thể bị tràn và tuần hoàn giá trị. Khi **biết rõ hai đầu, bước tăng là 1**, `range` hoặc `rangeClosed` truyền đạt mục đích rõ và dễ kiểm soát hơn.

## 9. Những lỗi off-by-one và tràn số thường gặp

### 9.1. Dùng rangeClosed cho kích thước collection

~~~java
List<String> names = java.util.Arrays.asList("An", "Bình");

// Sai: 0, 1, 2; chỉ số 2 không hợp lệ cho danh sách 2 phần tử.
// IntStream.rangeClosed(0, names.size()).forEach(i -> names.get(i));

// Đúng: 0, 1.
IntStream.range(0, names.size()).forEach(i -> names.get(i));
~~~

Nếu muốn hiển thị số thứ tự từ 1, hãy dùng `index + 1` khi trình bày thay vì tạo thêm phần tử không hợp lệ.

### 9.2. Lấy thiếu giá trị cuối của khoảng nghiệp vụ

~~~java
// Sai yêu cầu "từ 1 đến 10, kể cả 10".
long nineNumbers = IntStream.range(1, 10).count(); // 9

// Đúng yêu cầu.
long tenNumbers = IntStream.rangeClosed(1, 10).count(); // 10
~~~

Một mẹo thiết kế: dùng `range(0, size)` khi nói về **chỉ số**, dùng `rangeClosed(1, lastNumber)` khi nói về **các số từ 1 đến số cuối**.

### 9.3. Cộng 1 để giả lập rangeClosed

~~~java
int end = Integer.MAX_VALUE;

// Nguy hiểm: end + 1 tràn int thành Integer.MIN_VALUE.
// IntStream.range(1, end + 1);

IntStream correct = IntStream.rangeClosed(1, end);
System.out.println(correct.limit(3).boxed()
    .collect(java.util.stream.Collectors.toList())); // [1, 2, 3]
~~~

`rangeClosed` không yêu cầu người gọi tự cộng 1 vào ranh giới trên, nên xử lý được trường hợp `endInclusive` bằng `Integer.MAX_VALUE`. Tương tự, `LongStream.rangeClosed(..., Long.MAX_VALUE)` là cách mô tả đúng về mặt ranh giới; nhưng vẫn phải cân nhắc việc phép toán kết thúc có hoàn thành hay có tràn số khi tổng hợp không.

### 9.4. Tưởng khoảng tự giảm khi start lớn hơn end

~~~java
long empty = IntStream.rangeClosed(5, 1).count(); // 0
~~~

`rangeClosed(5, 1)` **không tạo** `5, 4, 3, 2, 1`. Hai phương thức này có bước tăng cố định là 1 và trả Stream rỗng khi ranh giới ngược thứ tự. Với dãy giảm có độ dài biết trước, ta có thể ánh xạ một khoảng tăng:

~~~java
IntStream.rangeClosed(0, 4)
    .map(index -> 5 - index)
    .forEach(System.out::println); // 5, 4, 3, 2, 1
~~~

Công thức `5 - index` an toàn cho ví dụ nhỏ này. Với giới hạn cực trị, cần tính toán bằng kiểu số phù hợp để tránh tràn trong biểu thức ánh xạ.

### 9.5. Tạo range rất lớn rồi ép thu toàn bộ

~~~java
// Rủi ro tốn bộ nhớ và thời gian:
// int[] all = IntStream.range(0, Integer.MAX_VALUE).toArray();

// Khi chỉ cần vài phần tử:
int[] prefix = IntStream.range(0, Integer.MAX_VALUE)
    .limit(5)
    .toArray(); // [0, 1, 2, 3, 4]
~~~

Ranh giới đúng **chưa đủ**: cần xác định terminal operation và kích thước kết quả. `count()`, `sum()`, `findFirst()`, `limit()` và `toArray()` có nhu cầu tài nguyên khác nhau.

## 10. Kết hợp range với các phép toán Stream

Khoảng số chỉ là **nguồn dữ liệu**. Ta có thể lắp tiếp các phép toán trung gian và kết thúc để xử lý bài toán thực tế.

| Bài toán | Pipeline gợi ý | Kết quả |
|---|---|---|
| Đếm số phần tử từ 0 đến 99 | `IntStream.range(0, 100).count()` | `100L` |
| Tổng các số chẵn từ 2 đến 10 | `IntStream.rangeClosed(1, 10).filter(n -> n % 2 == 0).sum()` | `30` |
| Bình phương từ 1 đến 4 | `IntStream.rangeClosed(1, 4).map(n -> n * n)` rồi thu kết quả | `1, 4, 9, 16` |
| Kiểm tra trong dãy 1..20 có bội số của 7 không | `IntStream.rangeClosed(1, 20).anyMatch(n -> n % 7 == 0)` | `true` |
| Lấy 3 số đầu của khoảng lớn | `LongStream.range(0L, 1_000_000_000L).limit(3)` | `0, 1, 2` |
| Tạo nhãn các phiên bản | `IntStream.rangeClosed(1, 3).mapToObj(i -> "v" + i)` | `v1, v2, v3` |

Ví dụ tổng hợp các số chẵn:

~~~java
int sumOfEvens = IntStream.rangeClosed(1, 10)
    .filter(number -> number % 2 == 0)
    .sum();

System.out.println(sumOfEvens); // 30
~~~

Ví dụ sinh các nhãn:

~~~java
List<String> versions = IntStream.rangeClosed(1, 3)
    .mapToObj(i -> "v" + i)
    .collect(java.util.stream.Collectors.toList());

System.out.println(versions); // [v1, v2, v3]
~~~

Khi xử lý bằng `parallel()`, nguồn khoảng số thường thuận lợi cho phân chia công việc vì biết giới hạn. Dù vậy, **parallel Stream không mặc nhiên nhanh hơn**: việc phân chia, kết hợp, giữ thứ tự và chi phí tác vụ quyết định hiệu quả. Hãy tránh tác dụng phụ trên trạng thái dùng chung và chỉ bật song song khi có lý do thực tế, được đo kiểm trên khối lượng công việc phù hợp.

## 11. Bài tập vận dụng: đánh số các ngày làm việc giả định

Một ứng dụng hiển thị danh sách năm ngày làm việc từ thứ Hai đến thứ Sáu, đánh số từ 1 đến 5. Yêu cầu:

1. Tạo Stream chứa vị trí 0 đến 4 bằng `range`.
2. Dùng `mapToObj` lấy tên ngày tương ứng và gắn số thứ tự từ 1.
3. Tạo `List<String>` và in danh sách.
4. Viết lại phép tạo số thứ tự bằng `rangeClosed(1, 5)`.
5. Giải thích vì sao `range(0, names.size())` an toàn khi `names` rỗng.

**Lời giải tham khảo (Java 8+):**

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class RangePractice {
    public static void main(String[] args) {
        List<String> weekdays = Arrays.asList(
            "Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu"
        );

        List<String> fromIndexes = IntStream.range(0, weekdays.size())
            .mapToObj(i -> (i + 1) + ". " + weekdays.get(i))
            .collect(Collectors.toList());

        List<String> fromOrdinal = IntStream.rangeClosed(1, weekdays.size())
            .mapToObj(number -> number + ". " + weekdays.get(number - 1))
            .collect(Collectors.toList());

        System.out.println(fromIndexes);
        System.out.println(fromIndexes.equals(fromOrdinal)); // true
    }
}
~~~

Kết quả:

~~~text
[1. Thứ Hai, 2. Thứ Ba, 3. Thứ Tư, 4. Thứ Năm, 5. Thứ Sáu]
true
~~~

Ở cách thứ nhất, biến `i` là **chỉ số bắt đầu từ 0**, nên khi hiển thị cộng thêm 1. Ở cách thứ hai, `number` đã là **số thứ tự bắt đầu từ 1**, nên khi truy cập List cần trừ 1. Khi `weekdays` rỗng, cả `range(0, 0)` và `rangeClosed(1, 0)` đều trả Stream rỗng, nên không có truy cập chỉ số ngoài phạm vi.

**Tự kiểm tra:**

- `IntStream.range(3, 3)` có bao nhiêu phần tử? — **0**.
- `IntStream.rangeClosed(3, 3)` có bao nhiêu phần tử? — **1**, là số 3.
- `IntStream.rangeClosed(3, 1)` có phát 3, 2, 1 không? — **Không**, Stream rỗng.
- `IntStream.range(0, 10).count()` trả kiểu gì? — **`long`**, giá trị `10L`.
- `rangeClosed(1, Integer.MAX_VALUE)` có cần cộng thêm 1 vào ranh giới không? — **Không**, và không nên làm vậy.
- `IntStream.range(1, 100).mapToObj(i -> "ID-" + i)` trả loại Stream nào? — **`Stream<String>`**.

## 12. Ghi nhớ trước khi chuyển sang các dãy khác

**`IntStream.range(start, end)`** và **`LongStream.range(start, end)`** bao gồm `start`, loại `end`. **`rangeClosed(start, end)`** bao gồm cả hai. Cả hai tạo **dãy số nguyên liên tiếp, hữu hạn, tăng từng đơn vị**, và tạo một nguồn Stream chứ không yêu cầu lưu sẵn mọi giá trị trong bộ nhớ.

Khi thiết kế pipeline, hãy trả lời bốn câu hỏi: **đầu cuối có được tính không**, **kiểu số là `int` hay `long`**, **kết quả có thể lớn đến đâu**, và **terminal operation cần bao nhiêu thời gian/bộ nhớ**. Từ nguồn khoảng số, bạn có thể áp dụng `filter`, `map`, `reduce`, `collect`, grouping hoặc các phép tính số; khi cần dãy vô hạn, bước nhảy tùy ý hay quy tắc sinh phần tử khác, hãy tiếp tục tìm hiểu `iterate` và `generate` cùng giới hạn dừng phù hợp.
