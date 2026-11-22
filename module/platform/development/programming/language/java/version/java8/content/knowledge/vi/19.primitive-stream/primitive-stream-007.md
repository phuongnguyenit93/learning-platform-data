# Range gồm biên hoặc không gồm biên trong Primitive Stream

## 1. Mục tiêu

Khi muốn tạo một dãy số nguyên liên tiếp trong Java Stream, hai phương thức quan trọng là:

- **`IntStream.range(startInclusive, endExclusive)`**: lấy **biên đầu**, **không lấy biên cuối**.
- **`IntStream.rangeClosed(startInclusive, endInclusive)`**: lấy **cả biên đầu và biên cuối**.

`LongStream` có hai phương thức tương ứng cho kiểu `long`. Các API này thuộc `java.util.stream`, xuất hiện từ Java 8 và vẫn được sử dụng trong Java hiện đại. Tên tham số thể hiện rõ ý nghĩa: `inclusive` là **có bao gồm**, `exclusive` là **không bao gồm**.

Ví dụ với `start=2`, `end=6`:

```text
IntStream.range(2, 6)       -> [2, 3, 4, 5]
IntStream.rangeClosed(2, 6) -> [2, 3, 4, 5, 6]
```

Một giá trị `6` ở biên cuối làm khác biệt hoàn toàn về số lượng phần tử. Đây là lỗi **off-by-one** (lệch một đơn vị) rất thường gặp khi duyệt chỉ số mảng, sinh số thứ tự, xử lý khoảng ngày hoặc tính tổng trên đoạn số nguyên.

Bài học tập trung vào **ranh giới của khoảng giá trị** trong primitive stream, điều kiện tạo stream rỗng, cách áp dụng với chỉ số mảng/danh sách, kiểu `int`/`long`, giới hạn số nguyên và các lựa chọn để tránh sai biên.

## 2. Hai API: khoảng nửa mở và khoảng đóng

### 2.1. `range(a, b)` — khoảng nửa mở `[a, b)`

```java
IntStream.range(int startInclusive, int endExclusive);
LongStream.range(long startInclusive, long endExclusive);
```

Đây là **chữ ký minh họa của các static factory method**, không phải chương trình độc lập. Cách hiểu về tập giá trị:

```text
startInclusive <= n < endExclusive
```

Nếu `a < b`, stream chứa `a, a+1, a+2, ..., b-1`. Giá trị `b` **không có** trong kết quả.

Ví dụ:

```java
// Mã minh họa trong hàm có import java.util.stream.IntStream.
IntStream.range(0, 4);   // 0, 1, 2, 3
IntStream.range(-2, 2);  // -2, -1, 0, 1
IntStream.range(5, 5);   // rỗng
IntStream.range(7, 3);   // rỗng
```

Khoảng `[a, b)` rất tự nhiên với mảng và `List` vì chỉ số hợp lệ là `0` đến `size - 1`. Viết `IntStream.range(0, size)` sẽ tạo đúng `size` chỉ số, không bị truy cập vào vị trí `size` ngoài phạm vi.

### 2.2. `rangeClosed(a, b)` — khoảng đóng `[a, b]`

```java
IntStream.rangeClosed(int startInclusive, int endInclusive);
LongStream.rangeClosed(long startInclusive, long endInclusive);
```

Cách hiểu:

```text
startInclusive <= n <= endInclusive
```

Nếu `a <= b`, stream chứa `a, a+1, ..., b`. Giá trị `b` **có mặt** trong kết quả.

Ví dụ:

```java
// Mã minh họa trong hàm có import java.util.stream.IntStream.
IntStream.rangeClosed(1, 4);   // 1, 2, 3, 4
IntStream.rangeClosed(-2, 2);  // -2, -1, 0, 1, 2
IntStream.rangeClosed(5, 5);   // một phần tử: 5
IntStream.rangeClosed(7, 3);   // rỗng
```

Khoảng `[a, b]` phù hợp khi hai đầu mút đều là giá trị hợp lệ thuộc tập dữ liệu, chẳng hạn số thứ tự từ `1` đến `N` hoặc tất cả ngày có số thứ tự `1..31`.

### 2.3. Bảng so sánh nhanh

| Thuộc tính | `range(a, b)` | `rangeClosed(a, b)` |
| --- | --- | --- |
| Ký hiệu toán học | `[a, b)` | `[a, b]` |
| Có chứa `a`? | Có, nếu khoảng không rỗng | Có, nếu khoảng không rỗng |
| Có chứa `b`? | Không | Có, nếu `a <= b` |
| Khi `a < b` | `a` đến `b - 1` | `a` đến `b` |
| Khi `a == b` | Rỗng | Một phần tử `a` |
| Khi `a > b` | Rỗng | Rỗng |
| Độ tăng mặc định | `+1` | `+1` |
| Thứ tự nguồn | Có encounter order tăng dần | Có encounter order tăng dần |
| Ứng dụng điển hình | Chỉ số `0..size-1` | Số từ `1..N` kể cả `N` |

**Không có exception chỉ vì `start >= end`**: các phương thức trả stream rỗng khi không có số nào thỏa mãn biên. Điểm khác biệt là khi `start == end`, `rangeClosed` vẫn có đúng **một** phần tử.

## 3. Ví dụ 1 — tất cả các trường hợp biên cơ bản

Tạo file **RangeBasicsDemo.java**:

```java
import java.util.Arrays;
import java.util.stream.IntStream;

public class RangeBasicsDemo {
    public static void main(String[] args) {
        System.out.println("range=" +
            Arrays.toString(IntStream.range(2, 6).toArray()));

        System.out.println("rangeClosed=" +
            Arrays.toString(IntStream.rangeClosed(2, 6).toArray()));

        System.out.println("rangeEqual=" +
            Arrays.toString(IntStream.range(5, 5).toArray()));

        System.out.println("closedEqual=" +
            Arrays.toString(IntStream.rangeClosed(5, 5).toArray()));

        System.out.println("rangeReverse=" +
            Arrays.toString(IntStream.range(7, 3).toArray()));

        System.out.println("closedReverse=" +
            Arrays.toString(IntStream.rangeClosed(7, 3).toArray()));

        System.out.println("negative=" +
            Arrays.toString(IntStream.range(-2, 2).toArray()));

        System.out.println("rangeCount=" +
            IntStream.range(2, 6).count());

        System.out.println("closedCount=" +
            IntStream.rangeClosed(2, 6).count());
    }
}
```

Chạy trên JDK 17 trở lên; toàn bộ API trong ví dụ cũng có trong Java 8:

```bash
javac RangeBasicsDemo.java
java RangeBasicsDemo
```

Stdout:

```text
range=[2, 3, 4, 5]
rangeClosed=[2, 3, 4, 5, 6]
rangeEqual=[]
closedEqual=[5]
rangeReverse=[]
closedReverse=[]
negative=[-2, -1, 0, 1]
rangeCount=4
closedCount=5
```

Điểm cần chú ý:

1. Cùng hai tham số `(2, 6)` nhưng `range` có `4` phần tử, `rangeClosed` có `5` phần tử.
2. `range(5, 5)` rỗng vì không có số `n` nào thỏa `5 <= n < 5`.
3. `rangeClosed(5, 5)` có `5` vì `5 <= n <= 5` là hợp lệ.
4. `range(7, 3)` và `rangeClosed(7, 3)` đều **rỗng**: API này không tự suy ra rằng bạn muốn đếm lùi.
5. Giá trị âm được xử lý bình thường theo thứ tự tăng dần; `range(-2, 2)` vẫn có biên cuối mở.

Trong ví dụ, `Arrays.toString(...)` chỉ dùng để in giá trị rõ ràng. `toArray()` biến một primitive stream hữu hạn thành mảng `int[]`.

## 4. Điều gì xảy ra khi start hoặc end đặc biệt?

### 4.1. Khi `start == end`

```text
range(4, 4)       -> []
rangeClosed(4, 4) -> [4]
```

Bài toán thực tế: một khoảng số thứ tự từ `startOrder` đến `endOrder`. Nếu hai số bằng nhau và yêu cầu **bao gồm cả hai đầu**, dùng `rangeClosed` sẽ giữ lại đơn hàng đó. Nếu `end` đại diện cho **vị trí đầu tiên sau vùng dữ liệu**, dùng `range` đúng vì một khoảng `[i, i)` không có phần tử.

### 4.2. Khi `start > end`

```text
range(8, 2)       -> []
rangeClosed(8, 2) -> []
```

Cả hai đều trả stream rỗng, **không đếm giảm** và **không ném lỗi chỉ vì biên đảo**. Nếu người dùng nhập biên sai và nghiệp vụ không cho phép khoảng rỗng, phải **validate ở tầng ứng dụng**:

```java
// Đoạn minh họa, không phải chương trình độc lập.
if (start > end) {
    throw new IllegalArgumentException("start must not exceed end");
}
int[] values = IntStream.rangeClosed(start, end).toArray();
```

Biến `start`/`end` và import `IntStream` cần được định nghĩa ở chương trình gọi. Ví dụ chỉ minh họa cách kiểm tra nếu ứng dụng yêu cầu khoảng đóng không được đảo chiều.

### 4.3. Có tự tạo stream vô hạn không?

Không. Với hai biên `int` hoặc `long` cụ thể, `range` và `rangeClosed` mô tả một khoảng **hữu hạn**. Nhưng khoảng có thể rất lớn; dùng `toArray()` trên một khoảng khổng lồ có thể hết bộ nhớ, và duyệt hết có thể mất nhiều thời gian. Hãy kết hợp `limit`, `skip`, `filter`, hoặc xử lý từng phần khi bài toán yêu cầu.

Lưu ý: đây là các **primitive stream** (số kiểu nguyên thủy) nên tránh boxing từng số thành `Integer`/`Long` khi không cần. `IntStream.range(...)` trả `IntStream`, không phải `List<Integer>`.

## 5. Dùng range với chỉ số của mảng và List

Đây là trường hợp thực tế nên ưu tiên **biên cuối không bao gồm**.

Một mảng có độ dài `length = 4` có chỉ số hợp lệ:

```text
0, 1, 2, 3
```

Vì vậy:

```java
IntStream.range(0, array.length)
```

tương đương về tập chỉ số với vòng lặp:

```java
for (int i = 0; i < array.length; i++) {
    // xử lý array[i]
}
```

**Không viết `rangeClosed(0, array.length)` để truy cập mảng**, vì nó còn tạo `array.length` — vị trí không hợp lệ, gây `ArrayIndexOutOfBoundsException` nếu truy cập.

Tương tự, `List.size()` là số phần tử, nhưng chỉ số cuối là `size() - 1`. Viết `IntStream.range(0, list.size())` diễn đạt trực tiếp quy tắc chỉ số Java.

### Ví dụ 2 — đánh số vị trí và tính tổng một đoạn mảng

Tạo file **IndexRangeDemo.java**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class IndexRangeDemo {
    public static void main(String[] args) {
        List<String> tasks = Arrays.asList("read", "test", "deploy");

        List<String> indexed = IntStream.range(0, tasks.size())
            .mapToObj(i -> i + ":" + tasks.get(i))
            .collect(Collectors.toList());

        int[] data = {4, 6, 8, 10};

        int sumFromIndexOne = IntStream.range(1, data.length)
            .map(i -> data[i])
            .sum();

        int inclusiveSum = IntStream.rangeClosed(1, 4)
            .sum();

        int[] evens = IntStream.rangeClosed(1, 8)
            .filter(n -> n % 2 == 0)
            .toArray();

        int[] stepTwo = IntStream.range(0, 4)
            .map(i -> 2 + i * 2)
            .toArray();

        System.out.println("indexed=" + indexed);
        System.out.println("sumFromIndexOne=" + sumFromIndexOne);
        System.out.println("inclusiveSum=" + inclusiveSum);
        System.out.println("evens=" + Arrays.toString(evens));
        System.out.println("stepTwo=" + Arrays.toString(stepTwo));
    }
}
```

```bash
javac IndexRangeDemo.java
java IndexRangeDemo
```

Stdout:

```text
indexed=[0:read, 1:test, 2:deploy]
sumFromIndexOne=24
inclusiveSum=10
evens=[2, 4, 6, 8]
stepTwo=[2, 4, 6, 8]
```

Giải thích:

- `range(0, tasks.size())` tạo `0, 1, 2`; `mapToObj` chuyển mỗi chỉ số thành chuỗi `"i:task"`. `Collectors.toList()` thu thập các chuỗi thành `List<String>`.
- `range(1, data.length)` tạo các chỉ số `1, 2, 3`, nên tổng `data[1] + data[2] + data[3] = 6 + 8 + 10 = 24`. Không động vào `data[4]`.
- `rangeClosed(1, 4).sum()` tính `1 + 2 + 3 + 4 = 10` — chính số `4` ở biên cuối được tính.
- `filter(n -> n % 2 == 0)` lọc số chẵn từ khoảng đóng `1..8`.
- `range(0, 4).map(i -> 2 + i * 2)` chuyển chỉ số thành dãy `2, 4, 6, 8`. Bản thân `range` luôn tăng bước `1`; ở đây `map` tạo dãy giá trị có bước `2`.

**Khi chỉ cần giá trị, không cần index**, thường nên dùng `tasks.stream()` trực tiếp thay vì `range(0, tasks.size()).mapToObj(tasks::get)`. Range hữu ích nhất khi **chỉ số cũng mang ý nghĩa**, hoặc khi làm việc với mảng và dữ liệu vị trí.

Với một `List` có `get(i)` không phải thời gian hằng số (ví dụ `LinkedList`), truy cập theo chỉ số liên tục có thể kém hiệu quả; hãy cân nhắc duyệt phần tử trực tiếp hoặc dùng cấu trúc dữ liệu phù hợp.

## 6. LongStream.range và LongStream.rangeClosed

Hai phương thức bên `LongStream` có **cùng quy tắc biên** nhưng đầu vào và phần tử là `long`:

```java
LongStream.range(10L, 13L)       // 10, 11, 12
LongStream.rangeClosed(10L, 13L) // 10, 11, 12, 13
```

Nên chọn `LongStream` khi giá trị của khoảng hoặc miền giá trị thực tế cần `long`, thay vì ép xuống `int`. Dữ liệu thời gian biểu diễn bằng epoch millisecond, ID dạng `long` hoặc bộ đếm lớn có thể cần miền `long`; tuy vậy, hãy cân nhắc không tự tạo một stream khổng lồ chỉ vì kiểu `long` đủ rộng.

### Ví dụ 3 — khoảng long và biên lớn nhất

Tạo file **LongRangeDemo.java**:

```java
import java.util.Arrays;
import java.util.stream.LongStream;

public class LongRangeDemo {
    public static void main(String[] args) {
        System.out.println("longRange=" +
            Arrays.toString(LongStream.range(10L, 13L).toArray()));

        System.out.println("longClosed=" +
            Arrays.toString(LongStream.rangeClosed(10L, 13L).toArray()));

        System.out.println("nearLongMax=" +
            Arrays.toString(LongStream.rangeClosed(
                Long.MAX_VALUE - 2,
                Long.MAX_VALUE
            ).toArray()));

        System.out.println("longEqual=" +
            Arrays.toString(LongStream.range(
                Long.MAX_VALUE,
                Long.MAX_VALUE
            ).toArray()));
    }
}
```

```bash
javac LongRangeDemo.java
java LongRangeDemo
```

Stdout:

```text
longRange=[10, 11, 12]
longClosed=[10, 11, 12, 13]
nearLongMax=[9223372036854775805, 9223372036854775806, 9223372036854775807]
longEqual=[]
```

**Vì sao ví dụ quan trọng?** `LongStream.rangeClosed(Long.MAX_VALUE - 2, Long.MAX_VALUE)` có thể biểu diễn hợp lệ ba giá trị cuối của kiểu `long`, **bao gồm** `Long.MAX_VALUE`. Nếu cố chuyển thành `LongStream.range(start, end + 1)`, phép cộng `Long.MAX_VALUE + 1` sẽ overflow trước khi `range` nhận tham số.

Cả `IntStream` và `LongStream` đều có các factory method `range` và `rangeClosed`. **`DoubleStream` không có `range(...)` hay `rangeClosed(...)` tương ứng**. Với một dãy giá trị thực có bước cố định, có thể tạo chỉ số bằng `IntStream.range` và chuyển qua `mapToDouble`, nhưng phải lưu ý về sai số chấm động.

## 7. Lỗi quan trọng: thay rangeClosed bằng range(end + 1)

Ở các khoảng nhỏ, ta thường thấy:

```java
// Với các giá trị bình thường, hai dãy sau giống nhau.
IntStream.rangeClosed(1, 5); // 1, 2, 3, 4, 5
IntStream.range(1, 6);       // 1, 2, 3, 4, 5
```

Nhưng **đừng kết luận** công thức tổng quát luôn là:

```java
// Không an toàn khi end == Integer.MAX_VALUE.
IntStream.range(start, end + 1);
```

Vì `int` chỉ chứa các giá trị từ `-2147483648` đến `2147483647`. Với `end = Integer.MAX_VALUE`, phép tính `end + 1` overflow thành `Integer.MIN_VALUE`. Lúc đó `range(start, end + 1)` có thể trở thành **khoảng rỗng** dù phải có dữ liệu.

### Ví dụ 4 — kiểm tra overflow sát biên Integer.MAX_VALUE

Tạo file **BoundaryRangeDemo.java**:

```java
import java.util.Arrays;
import java.util.stream.IntStream;

public class BoundaryRangeDemo {
    public static void main(String[] args) {
        System.out.println("nearIntMaxExclusive=" +
            Arrays.toString(IntStream.range(
                Integer.MAX_VALUE - 2,
                Integer.MAX_VALUE
            ).toArray()));

        System.out.println("nearIntMaxInclusive=" +
            Arrays.toString(IntStream.rangeClosed(
                Integer.MAX_VALUE - 2,
                Integer.MAX_VALUE
            ).toArray()));

        int overflowedEnd = Integer.MAX_VALUE + 1;
        System.out.println("overflowedEnd=" + overflowedEnd);

        System.out.println("wrongRange=" +
            Arrays.toString(IntStream.range(
                Integer.MAX_VALUE - 2,
                overflowedEnd
            ).toArray()));

        System.out.println("parallelOrdered=" +
            Arrays.toString(IntStream.range(1, 6)
                .parallel()
                .toArray()));
    }
}
```

```bash
javac BoundaryRangeDemo.java
java BoundaryRangeDemo
```

Stdout:

```text
nearIntMaxExclusive=[2147483645, 2147483646]
nearIntMaxInclusive=[2147483645, 2147483646, 2147483647]
overflowedEnd=-2147483648
wrongRange=[]
parallelOrdered=[1, 2, 3, 4, 5]
```

Phân tích:

- `range(Integer.MAX_VALUE - 2, Integer.MAX_VALUE)` **không lấy** số `2147483647`.
- `rangeClosed(Integer.MAX_VALUE - 2, Integer.MAX_VALUE)` **có lấy** số `2147483647` và kết thúc đúng.
- `Integer.MAX_VALUE + 1` được tính theo số nguyên 32 bit, kết quả là `Integer.MIN_VALUE` vì overflow. Vậy `range(2147483645, -2147483648)` trống.
- `parallel()` khiến stream có thể xử lý song song, nhưng `toArray()` vẫn trả mảng theo **encounter order** khi nguồn có thứ tự. Đầu ra này không có nghĩa các tác vụ nội bộ chạy tuần tự.

**Quy tắc an toàn:** Khi nghiệp vụ yêu cầu biên cuối **được tính**, gọi `rangeClosed(start, end)` trực tiếp. Không cộng `1` vào `end` một cách máy móc. Với `LongStream`, vấn đề tương tự tồn tại tại `Long.MAX_VALUE`.

Một điểm liên quan: **kiểu số trả về của phép cộng/tổng cũng có giới hạn**. Ví dụ `IntStream.rangeClosed(1, 100000).sum()` trả `int` và tổng toán học vượt miền `int`, nên có thể overflow. Dùng `mapToLong(i -> i).sum()` hoặc kiểu số lớn hơn nếu cần tính tổng lớn. **Giới hạn kết quả của `sum()` không phải lỗi của `rangeClosed`**.

## 8. Thứ tự phần tử và thực thi song song

Cả bốn factory method `IntStream.range`, `IntStream.rangeClosed`, `LongStream.range` và `LongStream.rangeClosed` tạo một **sequential, ordered primitive stream** với giá trị tăng từng bước `1`. Nếu nguồn `range(1, 6)`, encounter order là:

```text
1 -> 2 -> 3 -> 4 -> 5
```

Khi gọi `parallel()`, phép tính có thể được chia ra nhiều nhánh nhưng nguồn vẫn có encounter order. Chọn terminal operation theo yêu cầu:

| Terminal operation | Ý nghĩa về thứ tự |
| --- | --- |
| `toArray()` trên stream có thứ tự | Mảng kết quả theo encounter order. |
| `forEachOrdered(action)` | Thực hiện các hành động theo encounter order, kể cả với stream song song. |
| `forEach(action)` khi stream song song | **Không bảo đảm** thứ tự hành động; không dùng nếu thứ tự xuất ra là yêu cầu. |
| `sum()`, `count()` | Tổng/số lượng; thứ tự duyệt thường không phải điều cần quan sát. |

Ví dụ, với biến `numbers` là một `IntStream` đã khởi tạo mới:

```java
// Đoạn minh họa, không phải chương trình độc lập.
IntStream.range(1, 6)
    .parallel()
    .forEachOrdered(System.out::println);
// In 1, 2, 3, 4, 5 theo từng dòng.
```

Đừng phụ thuộc vào thứ tự của `parallel().forEach(System.out::println)`: kết quả mỗi lần chạy có thể khác nhau. Với tác vụ tính toán nhỏ trên một dải ngắn, `parallel()` còn có overhead phân chia/gộp nên không mặc định nhanh hơn.

## 9. Bước nhảy khác 1, đếm lùi và số thực

`range` và `rangeClosed` **chỉ sinh số nguyên tăng theo bước `1`**; không có tham số `step` trong hai phương thức này.

### Bước 2

Cách đơn giản là dùng range làm **dãy chỉ số**, sau đó map sang giá trị cần sinh:

```java
// Đoạn minh họa, import IntStream trong chương trình thực tế.
int[] evens = IntStream.range(0, 4)
    .map(i -> 2 + i * 2)
    .toArray();
// [2, 4, 6, 8]
```

Hoặc nếu có một khoảng số nguyên sẵn:

```java
// Đoạn minh họa.
int[] evens = IntStream.rangeClosed(1, 8)
    .filter(n -> n % 2 == 0)
    .toArray();
// [2, 4, 6, 8]
```

Cách `filter` vẫn kiểm tra từng số trong khoảng, còn `map` từ dãy chỉ số hữu hạn biểu diễn trực tiếp số lượng phần tử cần tạo. Với `start`, `step`, `count` phụ thuộc dữ liệu đầu vào, phải chú ý overflow trong phép tính `start + i * step`.

### Đếm lùi

`range(5, 1)` không cho `5,4,3,2` mà cho **stream rỗng**. Nếu cần đếm lùi trong phạm vi nhỏ có kiểm soát, có thể biến đổi dãy chỉ số:

```java
// Đoạn minh họa: dãy 5, 4, 3, 2, 1.
int[] descending = IntStream.rangeClosed(1, 5)
    .map(i -> 6 - i)
    .toArray();
```

Trong Java 9+ (vẫn áp dụng hiện nay), còn có `IntStream.iterate(seed, hasNext, next)` hỗ trợ điều kiện dừng và bước giảm theo ý muốn; nếu phải duy trì compatibility đúng Java 8, có thể dùng overload `IntStream.iterate(seed, next).limit(n)` cho trường hợp phù hợp. Dù chọn cách nào, cần kiểm tra bước nhảy, biên và overflow.

### Dãy double

Không có `DoubleStream.range`. Nếu muốn `0.0, 0.5, 1.0, 1.5`, dùng các chỉ số nguyên rồi chuyển kiểu:

### Ví dụ 5 — chuyển range thành giá trị double

Tạo file **DoubleRangeDemo.java**:

```java
import java.util.Arrays;
import java.util.stream.IntStream;

public class DoubleRangeDemo {
    public static void main(String[] args) {
        double[] halves = IntStream.range(0, 4)
            .mapToDouble(i -> i * 0.5)
            .toArray();

        System.out.println("halves=" + Arrays.toString(halves));
    }
}
```

```bash
javac DoubleRangeDemo.java
java DoubleRangeDemo
```

Stdout:

```text
halves=[0.0, 0.5, 1.0, 1.5]
```

Khi dùng bước nhảy thập phân như `0.1`, hãy lưu ý `double` không biểu diễn chính xác mọi giá trị thập phân. Nếu ứng dụng cần chính xác theo đơn vị tiền tệ hoặc decimal, phải chọn kiểu và thuật toán phù hợp.

## 10. Cách quyết định dùng khoảng gồm biên hay không gồm biên

| Yêu cầu nghiệp vụ | Cách viết | Tại sao |
| --- | --- | --- |
| Duyệt chỉ số `0` đến `size - 1` | `IntStream.range(0, size)` | `size` là **số phần tử**, không phải chỉ số cuối. |
| Lặp đúng `n` lần với chỉ số từ `0` | `IntStream.range(0, n)` | Khi `n=0`, kết quả rỗng đúng mong đợi. |
| Số thứ tự từ `1` đến `n`, kể cả `n` | `IntStream.rangeClosed(1, n)` | Biên cuối là giá trị phải được xử lý. |
| Các giá trị nguyên từ `a` đến trước `b` | `IntStream.range(a, b)` | Mô tả khoảng `[a, b)`. |
| Các giá trị nguyên từ `a` đến `b`, kể cả `b` | `IntStream.rangeClosed(a, b)` | Mô tả khoảng `[a, b]`. |
| Giá trị có miền `long` | `LongStream.range/ rangeClosed` | Dùng đúng kiểu số cho biên và phần tử. |
| Bước nhảy tùy chỉnh | `range(...).map(...)` hoặc `iterate(...)` theo điều kiện | Hai factory range luôn tăng bước `1`. |
| Xử lý dữ liệu trực tiếp, không cần vị trí | `list.stream()` | Tránh tạo index không cần thiết. |

Một cách tự hỏi đơn giản: **“Tham số `end` là phần tử cuối cùng mình muốn lấy, hay là vị trí đầu tiên sau vùng cần lấy?”**

- Nếu `end` là **phần tử cuối cùng**, chọn `rangeClosed`.
- Nếu `end` là **điểm dừng ở ngay sau**, chọn `range`.

## 11. Các lỗi phổ biến và cách sửa

### Lỗi 1 — lệch một đơn vị

```java
// Sai nếu cần cả các số 1,2,3,4,5.
IntStream.range(1, 5);        // chỉ 1..4
// Đúng:
IntStream.rangeClosed(1, 5);  // 1..5
```

**Cách sửa:** gọi đúng API theo ý nghĩa của biên cuối, không chỉ theo sự quen tay với vòng lặp `for`.

### Lỗi 2 — truy cập index vượt size

```java
// Sai nếu dùng i để truy cập list.get(i).
IntStream.rangeClosed(0, list.size());
// Đúng:
IntStream.range(0, list.size());
```

Đoạn mã là minh họa, trong ngữ cảnh `list` đã tồn tại. Cần dùng giới hạn **exclusive** khi duyệt chỉ số. Với danh sách rỗng, `range(0, 0)` tự nhiên không có phần tử.

### Lỗi 3 — tưởng range(start, end) tự đếm lùi

`IntStream.range(10, 1)` là rỗng, không phải `10,9,...,2`. Cần tự định nghĩa dãy giảm nếu nghiệp vụ yêu cầu.

### Lỗi 4 — dùng end + 1 không kiểm tra tràn

`IntStream.range(start, end + 1)` có thể sai khi `end = Integer.MAX_VALUE`. Thay bằng `IntStream.rangeClosed(start, end)`. Tương tự với `LongStream.rangeClosed` tại `Long.MAX_VALUE`.

### Lỗi 5 — cộng/tính tổng trong kiểu quá nhỏ

Dãy số sinh ra có thể hoàn toàn đúng nhưng `sum()` kiểu `int` bị tràn. Kiểm tra miền kết quả; nếu cần, `mapToLong(i -> i).sum()` hoặc kiểu rộng hơn. Không nhầm lỗi tính tổng với lỗi biên của range.

### Lỗi 6 — cho rằng range tự xử lý input không hợp lệ

Khoảng đảo biên trả stream rỗng. Nếu ứng dụng phải báo lỗi khi `start > end`, **tự xác thực đầu vào**. Một kết quả rỗng có thể che lỗi cấu hình hoặc lỗi người dùng.

### Lỗi 7 — tạo một dãy khổng lồ rồi toArray

`IntStream.rangeClosed(1, Integer.MAX_VALUE).toArray()` có kích thước tiềm năng rất lớn; không dùng nếu không đủ bộ nhớ. Xây pipeline có giới hạn kích thước thực tế; đừng biến mọi dãy số thành mảng chỉ để xử lý từng phần tử.

### Lỗi 8 — giả định thứ tự của forEach song song

`IntStream.range(1, 6).parallel().forEach(...)` không hứa hành động theo `1,2,3,4,5`. Nếu thứ tự là yêu cầu, dùng `forEachOrdered` hoặc terminal operation bảo toàn encounter order như `toArray`.

### Lỗi 9 — tưởng có DoubleStream.range

Trong Java Stream tiêu chuẩn, `range` và `rangeClosed` được cung cấp cho `IntStream` và `LongStream`, không phải `DoubleStream`. Dùng dãy chỉ số `int/long` rồi chuyển qua `mapToDouble` nếu phù hợp.

### Lỗi 10 — tái sử dụng một Stream đã kết thúc

```java
// Sai về vòng đời Stream: không gọi hai terminal operation trên cùng stream.
IntStream values = IntStream.range(1, 5);
long count = values.count();
// int sum = values.sum(); // Không được dùng lại sau count().
```

Nếu cần kết quả `count` và `sum`, tạo **hai stream mới** từ biên hoặc dùng một terminal operation trả nhiều thống kê, chẳng hạn `summaryStatistics()`. Đây là quy tắc chung của Stream, không riêng `range`.

## 12. Tự kiểm tra kiến thức

**Câu 1.** `IntStream.range(3, 7).toArray()` có những giá trị nào?

**Đáp án:** `[3, 4, 5, 6]`. Biên `7` bị loại.

**Câu 2.** `IntStream.rangeClosed(3, 7).toArray()` khác gì?

**Đáp án:** `[3, 4, 5, 6, 7]`. Biên `7` được tính nên nhiều hơn một phần tử.

**Câu 3.** `range(8, 8)` và `rangeClosed(8, 8)` có giống nhau không?

**Đáp án:** Không. `range(8, 8)` rỗng, còn `rangeClosed(8, 8)` chứa đúng `8`.

**Câu 4.** Với `List` có `size() == 3`, phạm vi chỉ số hợp lệ là gì?

**Đáp án:** `0,1,2`. Dùng `IntStream.range(0, list.size())`.

**Câu 5.** Có nên thay `rangeClosed(10, Integer.MAX_VALUE)` thành `range(10, Integer.MAX_VALUE + 1)`?

**Đáp án:** Không. `Integer.MAX_VALUE + 1` overflow thành số âm, dẫn đến khoảng sai. Gọi `rangeClosed` trực tiếp.

**Câu 6.** `IntStream.range(5, 2)` trả `5,4,3` hay stream rỗng?

**Đáp án:** Stream rỗng. `range` không tự sinh số giảm.

**Câu 7.** `LongStream.rangeClosed(10L, 12L)` cho kết quả nào?

**Đáp án:** `10L, 11L, 12L` — ba giá trị kiểu `long`.

**Câu 8.** `IntStream.range(0, 4).map(i -> 3*i).toArray()` cho kết quả nào?

**Đáp án:** `[0, 3, 6, 9]`. `range` tạo các chỉ số `0..3`, sau đó `map` nhân từng phần tử với `3`.

**Câu 9.** Khi dùng `parallel()`, `range` có mất encounter order không?

**Đáp án:** Không tự mất encounter order; tuy nhiên `forEach` song song không bảo đảm **thứ tự hành động**. `toArray` trên stream ordered hoặc `forEachOrdered` có thể bảo toàn thứ tự theo yêu cầu.

## 13. Tài liệu tham khảo chính thức

- [Oracle Java SE 26 — IntStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/IntStream.html): `range(int,int)` và `rangeClosed(int,int)`, ý nghĩa biên đầu/cuối và primitive terminal operation.
- [Oracle Java SE 26 — LongStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/LongStream.html): hai phương thức tương tự với `long`.
- [Oracle Java SE 26 — DoubleStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/DoubleStream.html): các phương thức hiện có, đối chiếu việc không có `range`.
- [Oracle Java SE 26 — Stream package](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html): nguyên tắc encounter order, terminal operation và parallel pipelines.

**Ghi nhớ:** `range(start, end)` tạo khoảng **`[start, end)`** (không lấy `end`); `rangeClosed(start, end)` tạo khoảng **`[start, end]`** (có lấy `end`). Với index từ `0` đến `size - 1`, dùng `range(0, size)`. Với giá trị số từ `1` đến `n` kể cả `n`, dùng `rangeClosed(1, n)`. Đừng tự cộng `1` vào biên cuối khi có thể gây overflow.