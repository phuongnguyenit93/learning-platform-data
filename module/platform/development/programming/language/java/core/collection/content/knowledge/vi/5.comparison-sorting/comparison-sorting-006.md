# Tránh tràn số khi viết phép so sánh bằng phép trừ

Khi viết `Comparable.compareTo` hoặc `Comparator.compare`, một cách làm dễ nghĩ tới là lấy giá trị thứ nhất trừ giá trị thứ hai:

```java
return first - second;
```

Lập luận có vẻ hợp lý: nếu thứ nhất nhỏ hơn thì hiệu âm, bằng nhau thì hiệu bằng không, lớn hơn thì hiệu dương. Lập luận đó đúng với phép toán trên các số nguyên không bị giới hạn độ lớn. Tuy nhiên, `int` và `long` của Java có phạm vi hữu hạn; phép trừ có thể **tràn số (overflow)** và trả về dấu sai.

Một comparator chỉ sai ở giá trị biên vẫn có thể làm hỏng kết quả sắp xếp, tìm kiếm hoặc nhận diện khóa trong collection.

Bài này tập trung vào cách nhận diện và sửa lỗi đó. Các chương trình hoàn chỉnh sử dụng API Java 17, đã được biên dịch với `--release 17` và chạy để đối chiếu stdout. Những đoạn rút gọn khác minh họa biểu thức hoặc thân phương thức, không phải tệp chạy độc lập.

Sau bài học, bạn có thể:

- Giải thích vì sao phép trừ không phải cách so sánh an toàn trên toàn miền `int` hoặc `long`.
- Phân biệt lỗi tràn phép toán với lỗi ép kiểu thu hẹp.
- Dùng `Integer.compare`, `Long.compare` và các hàm tạo comparator đúng kiểu.
- Đảo chiều hoặc kết hợp tiêu chí mà không thao tác sai trên dấu.
- Kiểm tra hợp đồng comparator với dữ liệu biên.

## 1. So sánh cần dấu, không cần khoảng cách

Với `compare(first, second)`:

| Kết quả | Ý nghĩa |
| --- | --- |
| Âm | `first` đứng trước `second` |
| Bằng không | Hai giá trị ngang hàng theo quy tắc so sánh |
| Dương | `first` đứng sau `second` |

Kết quả không có nhiệm vụ mô tả “hai số cách nhau bao xa”. Vì vậy, việc tính cả hiệu thường tạo thêm rủi ro mà không cung cấp thông tin cần thiết.

Ví dụ, để so `Integer.MIN_VALUE` với `Integer.MAX_VALUE`, ta chỉ cần biết giá trị thứ nhất nhỏ hơn. Không cần đưa khoảng cách toán học giữa hai số vào một biến `int`.

Một comparator hợp lệ cũng không bắt buộc luôn trả về đúng `-1`, `0` hoặc `1`. Bên sử dụng phải kiểm tra dấu:

```java
if (order.compare(first, second) < 0) {
    // first đứng trước second.
}
```

Việc xử lý dấu đúng là nền tảng cho cả cài đặt comparator lẫn cách sử dụng kết quả của nó.

## 2. Phạm vi hữu hạn làm phép trừ đổi dấu

Hai kiểu số nguyên thường gặp:

| Kiểu | Phạm vi |
| --- | --- |
| `int` | `-2_147_483_648` đến `2_147_483_647` |
| `long` | `-9_223_372_036_854_775_808` đến `9_223_372_036_854_775_807` |

Xét:

```text
first  = 2_147_483_647
second = -1
```

Theo toán học:

```text
first - second = 2_147_483_648
```

Giá trị đó lớn hơn `Integer.MAX_VALUE`. Khi thực hiện bằng phép trừ `int` thông thường, kết quả tràn thành:

```text
-2_147_483_648
```

Một số dương đã thành số âm. Comparator dùng hiệu sẽ kết luận `first` đứng trước `second`, trái với quan hệ số cần có.

### Java không tự báo ngoại lệ cho phép trừ int hoặc long bị tràn

Với phép toán số nguyên thông thường, Java giữ kết quả theo số bit của kiểu; những bit cao vượt phạm vi không được giữ lại. Kết quả được diễn giải lại theo kiểu số nguyên có dấu.

Điều này có thể tạo ra kết quả hợp lệ về mặt kiểu dữ liệu nhưng sai với mục đích so sánh.

Không nên chờ `ArithmeticException` từ phép trừ thông thường để nhận diện lỗi. Các hàm có kiểm tra tràn như `Math.subtractExact` có hợp đồng khác, được bàn ở phần sau.

### Chiều ngược lại cũng có thể sai

```text
Integer.MIN_VALUE - 1
```

có giá trị toán học nhỏ hơn giới hạn dưới của `int`, nhưng kết quả `int` trở thành `Integer.MAX_VALUE`, một số dương.

Vì vậy, không có quy tắc “tràn chỉ làm số lớn thành số nhỏ” đủ dùng để cứu comparator. Cần tránh phép toán có thể tràn ngay từ thiết kế.

## 3. Một comparator sai có thể vi phạm cả hợp đồng thứ tự

Lỗi không chỉ là sắp nhầm hai phần tử. Nó có thể khiến quy tắc không còn biểu diễn một thứ tự nhất quán.

Giả sử comparator là:

```java
Comparator<Integer> unsafe = (first, second) -> first - second;
```

Chọn ba giá trị:

```text
a = Integer.MIN_VALUE
b = 0
c = Integer.MAX_VALUE
```

Theo comparator dùng phép trừ:

- `a - b` âm, nên nó nói `a < b`.
- `b - c` âm, nên nó nói `b < c`.
- `a - c` tràn thành `1`, nên nó lại nói `a > c`.

Quy tắc đã vi phạm **tính bắc cầu**: nếu `a < b` và `b < c`, thì phải có `a < c`.

Nó còn có thể vi phạm quy tắc đổi chiều phải đổi dấu. Ví dụ, `Integer.MIN_VALUE - 0` và `0 - Integer.MIN_VALUE` đều cho kết quả `Integer.MIN_VALUE`, tức đều âm.

### Tác động đến collection

| Nơi sử dụng | Rủi ro khi quy tắc so sánh sai |
| --- | --- |
| Sắp xếp `List` hoặc mảng đối tượng | Thứ tự sai; thuật toán có thể phát hiện vi phạm hợp đồng và báo lỗi |
| `TreeSet` | Phần tử được tổ chức hoặc nhận diện theo quan hệ không đúng |
| Khóa của `TreeMap` | Tìm và cập nhật khóa dựa trên quy tắc sai |
| `PriorityQueue` | Phần tử được lấy theo ưu tiên không đúng với yêu cầu |
| Tìm kiếm nhị phân trên dữ liệu đã sắp | Kết quả không đáng tin nếu điều kiện thứ tự không còn được bảo đảm |

Không phải mọi lần dùng comparator sai đều ném ngoại lệ. Việc một danh sách nhỏ “vẫn sắp đúng” không chứng minh quy tắc hợp lệ trên toàn miền dữ liệu.

Bài không đưa ra một stdout cố định cho việc sắp xếp bằng comparator sai. Khi hợp đồng bị vi phạm, không nên dùng một kết quả tình cờ của thuật toán làm hành vi cần dựa vào.

## 4. Chương trình kiểm chứng lỗi int và cách sửa

Tạo tệp **`SubtractionOrderDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class SubtractionOrderDemo {
    public static void main(String[] args) {
        int left = Integer.MAX_VALUE;
        int right = -1;
        int wrapped = left - right;
        long exactForIntOperands = (long) left - right;

        System.out.println("exact int-operand difference = " + exactForIntOperands);
        System.out.println("wrapped int difference = " + wrapped);
        System.out.println("subtraction says left < right = " + (wrapped < 0));
        System.out.println("Integer.compare says left > right = "
                + (Integer.compare(left, right) > 0));

        Comparator<Integer> unsafe = (first, second) -> first - second;
        int first = Integer.MIN_VALUE;
        int middle = 0;
        int last = Integer.MAX_VALUE;

        System.out.println("unsafe first < middle = "
                + (unsafe.compare(first, middle) < 0));
        System.out.println("unsafe middle < last = "
                + (unsafe.compare(middle, last) < 0));
        System.out.println("unsafe first < last = "
                + (unsafe.compare(first, last) < 0));

        List<Integer> values = new ArrayList<>(
                List.of(Integer.MAX_VALUE, 0, Integer.MIN_VALUE, -1));
        values.sort(Integer::compare);
        System.out.println("safe sorted = " + values);
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 SubtractionOrderDemo.java
java -Dfile.encoding=UTF-8 SubtractionOrderDemo
```

Stdout:

```text
exact int-operand difference = 2147483648
wrapped int difference = -2147483648
subtraction says left < right = true
Integer.compare says left > right = true
unsafe first < middle = true
unsafe middle < last = true
unsafe first < last = false
safe sorted = [-2147483648, -1, 0, 2147483647]
```

### Đọc kết quả

1. `exactForIntOperands` chuyển một toán hạng sang `long` **trước** phép trừ, đủ để chứa hiệu của hai giá trị `int` bất kỳ.
2. `wrapped` được tính bằng `int`, nên tràn và có dấu âm.
3. Comparator dùng phép trừ không giữ được tính bắc cầu ở bộ ba đã chọn.
4. `Integer.compare` xác định đúng quan hệ mà không cần tính hiệu.
5. Danh sách cuối được sắp bằng comparator an toàn, nên thứ tự tăng dần khớp giá trị số.

Việc dùng `long` để hiển thị hiệu chính xác trong ví dụ chỉ là công cụ minh họa. Khi cần so sánh hai `int`, cách trực tiếp vẫn là `Integer.compare`.

## 5. Cách sửa chính: so sánh theo đúng kiểu

### Với int

Thay:

```java
return this.priority - other.priority;
```

bằng:

```java
return Integer.compare(this.priority, other.priority);
```

Hoặc với một comparator:

```java
Comparator<Integer> order = Integer::compare;
```

### Với long

Không dùng:

```java
return (int) (this.sequence - other.sequence);
```

Hãy dùng:

```java
return Long.compare(this.sequence, other.sequence);
```

`Long.compare` trả về một `int` biểu diễn quan hệ, dù các toán hạng có kiểu `long`. Nó không cố nhét khoảng cách giữa hai số `long` vào một số `int`.

### Nếu tự viết bằng phép quan hệ

Với hai biến nguyên thủy có miền giá trị phù hợp, biểu thức minh họa sau cũng không tính hiệu:

```java
return first < second ? -1 : (first > second ? 1 : 0);
```

Các hàm chuẩn thường dễ đọc và ít cơ hội viết sai hơn. Chúng còn thể hiện rõ kiểu dữ liệu cần so sánh.

### Bảng lựa chọn

| Dữ liệu cần so | Lựa chọn nên dùng |
| --- | --- |
| `int` | `Integer.compare(first, second)` |
| `long` | `Long.compare(first, second)` |
| Trường `int` của đối tượng | `Comparator.comparingInt(...)` |
| Trường `long` của đối tượng | `Comparator.comparingLong(...)` |
| Thứ tự ngược của một comparator | `order.reversed()` |
| Nhiều tiêu chí | `thenComparing...` hoặc so từng tiêu chí, chỉ chuyển tiếp khi bằng không |

Với các kiểu số có hợp đồng riêng như `BigInteger` hoặc `BigDecimal`, hãy dùng phép so sánh của chính kiểu thay vì lấy hiệu rồi chuyển kết quả sang `int`.

## 6. Các cách sửa nửa chừng vẫn có lỗi

### 6.1. Ép sang long sau khi trừ là quá muộn

```java
long difference = (long) (first - second);
```

Nếu `first` và `second` là `int`, biểu thức trong ngoặc đã được tính bằng `int`. Phép ép kiểu chỉ chuyển **kết quả đã tràn** thành `long`.

Thậm chí viết:

```java
long difference = first - second;
```

cũng không làm phép trừ tự chuyển thành `long`. Kiểu của biến nhận không thay đổi kiểu toán hạng đã dùng để tính biểu thức.

Nếu thực sự cần hiệu toán học của hai `int`:

```java
long difference = (long) first - second;
```

việc mở rộng xảy ra trước phép toán, nên hiệu nằm trong phạm vi `long`.

### 6.2. Tính hiệu bằng long rồi ép lại int làm mất bảo đảm

Cách này vẫn nguy hiểm:

```java
return (int) ((long) first - second);
```

Phần hiệu có thể đúng trong `long`, nhưng phép ép trở lại `int` làm mất các bit cao. Một hiệu dương ngoài miền `int` có thể trở thành số âm.

Mục đích của comparator không cần hiệu đó. Dùng `Integer.compare` bỏ hẳn bước tính hiệu và thu hẹp không cần thiết.

### 6.3. Hiệu long ép xuống int có thể thành bằng không

Hai giá trị `long`:

```text
0
4_294_967_296
```

khác nhau đúng `2^32`. Hiệu nằm trong miền `long`, nhưng ép hiệu đó xuống `int` có thể cho `0`.

Khi một comparator trả `0` sai:

- Sắp xếp sẽ coi chúng ngang hàng.
- Một cấu trúc như `TreeSet` có thể coi chúng là cùng phần tử.
- `TreeMap` có thể coi chúng là cùng khóa theo quy tắc comparator.

Đây là lỗi **thu hẹp kiểu**, ngay cả khi phép trừ `long` trước đó chưa tràn.

### 6.4. Đổi int thành long không giải quyết toàn bộ miền long

Hiệu của hai số `int` luôn nằm trong phạm vi `long`, nhưng hiệu của hai số `long` bất kỳ có thể vượt phạm vi `long`.

Nếu hai toán hạng vốn là `long`, không có phép “ép sang `long`” nào giúp tăng phạm vi. Hãy dùng `Long.compare`.

### 6.5. Chuyển qua double có thể làm hai số khác nhau thành giống nhau

`double` có phạm vi lớn nhưng không biểu diễn chính xác mọi số nguyên `long`.

Ví dụ, hai số nguyên liên tiếp tại `2^53` và `2^53 + 1` không còn được phân biệt sau phép chuyển sang `double` trong ví dụ dưới đây. So kết quả đã mất thông tin có thể trả về `0`.

Vì vậy:

- Tràn số không phải rủi ro duy nhất.
- “Kiểu số có miền lớn hơn” không đồng nghĩa “giữ nguyên độ chính xác cần thiết”.
- Nếu dữ liệu là `long`, hãy so chúng như `long`.

## 7. Chương trình kiểm chứng lỗi ép kiểu và long

Tạo tệp **`NumericConversionDemo.java`**:

```java
public class NumericConversionDemo {
    public static void main(String[] args) {
        int intLeft = Integer.MAX_VALUE;
        int intRight = -1;

        long castAfter = (long) (intLeft - intRight);
        long castBefore = (long) intLeft - intRight;
        int narrowedAgain = (int) castBefore;

        System.out.println("cast after subtraction = " + castAfter);
        System.out.println("cast before subtraction = " + castBefore);
        System.out.println("narrowed again = " + narrowedAgain);

        long zero = 0L;
        long distant = 1L << 32;
        System.out.println("narrowed long difference = "
                + (int) (zero - distant));
        System.out.println("Long.compare distinct values = "
                + Long.compare(zero, distant));

        long largest = Long.MAX_VALUE;
        long negative = -1L;
        System.out.println("overflowed long difference = " + (largest - negative));
        System.out.println("Long.compare correct direction = "
                + Long.compare(largest, negative));

        long first = 1L << 53;
        long next = first + 1;
        System.out.println("compare after double conversion = "
                + Double.compare((double) first, (double) next));
        System.out.println("compare exact long values = " + Long.compare(first, next));

        try {
            Math.subtractExact(intLeft, intRight);
        } catch (ArithmeticException exception) {
            System.out.println("subtractExact = "
                    + exception.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 NumericConversionDemo.java
java -Dfile.encoding=UTF-8 NumericConversionDemo
```

Stdout:

```text
cast after subtraction = -2147483648
cast before subtraction = 2147483648
narrowed again = -2147483648
narrowed long difference = 0
Long.compare distinct values = -1
overflowed long difference = -9223372036854775808
Long.compare correct direction = 1
compare after double conversion = 0
compare exact long values = -1
subtractExact = ArithmeticException
```

### Mỗi nhóm kết quả nói điều gì?

| Nhóm | Bằng chứng |
| --- | --- |
| Ép sau phép toán | Kết quả tràn của `int` được giữ nguyên khi chuyển thành `long` |
| Ép trước phép toán | Hiệu của hai `int` được tính chính xác bằng `long` |
| Ép trở lại `int` | Thông tin bị mất, dấu có thể sai |
| Hiệu hai `long` ép xuống `int` | Hai số khác nhau có thể cho kết quả `0` |
| Tràn `long` | Phép trừ của hai `long` hợp lệ vẫn có thể đổi dấu |
| Chuyển sang `double` | Hai giá trị `long` khác nhau có thể bị làm thành cùng giá trị |
| `subtractExact` | Tràn số được báo bằng ngoại lệ, không biến thành một quan hệ so sánh hợp lệ |

Các lỗi khác nhau cần được gọi tên đúng. Một giá trị thu hẹp thành `0` không nhất thiết do phép trừ đã tràn; phần tính hiệu có thể đúng và phép ép mới là chỗ phá hỏng dữ liệu.

## 8. Vì sao subtractExact, abs hoặc signum không tự cứu phép trừ?

### Math.subtractExact kiểm tra phép tính, không cung cấp thứ tự đầy đủ

`Math.subtractExact(first, second)` ném `ArithmeticException` nếu hiệu vượt phạm vi.

Điều đó hữu ích khi nghiệp vụ thật sự cần một **hiệu có thể biểu diễn chính xác** và muốn từ chối phép tính không hợp lệ. Tuy nhiên, một comparator cần so được hai số hợp lệ ở hai đầu phạm vi, dù khoảng cách giữa chúng quá lớn để lưu cùng kiểu.

Thay `first - second` bằng `Math.subtractExact(first, second)` sẽ biến sai dấu âm thầm thành lỗi lúc chạy; nó chưa thay thế được `Integer.compare` hoặc `Long.compare`.

### signum sau một phép trừ đã tràn vẫn đọc dấu sai

Cách sau vẫn lỗi:

```java
return Integer.signum(first - second);
```

`signum` chỉ đọc dấu của **kết quả đang có**. Nếu kết quả trừ đã tràn và sai dấu, chuẩn hóa nó thành `-1` hoặc `1` không phục hồi ý nghĩa ban đầu.

Trong bài, `Integer.signum` chỉ được dùng để kiểm tra hoặc hiển thị dấu của một kết quả; nó không được dùng như cách sửa phép trừ bị tràn.

### abs làm mất hướng và còn có giới hạn riêng

`Math.abs(first - second)` không thể là comparator tăng dần, vì giá trị tuyệt đối làm mất thông tin ai lớn hơn ai.

Ngoài ra, số đối dương của `Integer.MIN_VALUE` không biểu diễn được bằng `int`; thao tác trị tuyệt đối với giá trị đó có giới hạn tương ứng. Cần hiểu hợp đồng hàm số, không ghép chúng để đoán dấu.

## 9. Đảo chiều đúng cách

Một comparator hợp lệ có thể trả về bất kỳ giá trị âm hoặc dương nào. Vì vậy, cách viết:

```java
return -order.compare(first, second);
```

không phải lựa chọn an toàn cho một comparator tùy ý.

Nếu kết quả gốc là `Integer.MIN_VALUE`, phép lấy số đối vẫn cho `Integer.MIN_VALUE`, nên dấu không đảo.

### Các cách phù hợp

- Với `Integer.compare` hoặc `Long.compare`, đổi thứ tự hai đối số để đổi chiều.
- Với một đối tượng `Comparator`, dùng `reversed()`.
- Khi kết hợp nhiều tiêu chí, xác định đảo toàn bộ thứ tự hay chỉ đảo một tiêu chí.

Ví dụ quy tắc:

```java
Comparator<Job> ascending = Comparator.comparingInt(Job::priority)
        .thenComparingLong(Job::sequence)
        .thenComparing(Job::id);
```

thì:

- `ascending.reversed()` đảo toàn bộ chuỗi tiêu chí.
- Đảo comparator của `priority` trước rồi mới `thenComparing...` chỉ đảo tiêu chí ưu tiên đó.

Đổi vị trí gọi `reversed()` có thể thay đổi ý nghĩa thứ tự, dù cả hai cách đều không bị tràn.

## 10. So sánh nhiều tiêu chí mà không cộng hoặc trừ kết quả

Cách viết nhiều trường bằng một phép tính gộp thường gây lỗi:

```java
return first.priority - second.priority
        + (int) (first.sequence - second.sequence);
```

Nó có nhiều vấn đề:

1. Mỗi phép trừ có thể tràn hoặc bị thu hẹp sai.
2. Tiêu chí sau có thể lấn át tiêu chí trước.
3. Hai hiệu có thể triệt tiêu nhau và trả về `0` dù dữ liệu khác nhau.
4. Quy tắc không còn thể hiện rõ tiêu chí nào được ưu tiên.

### Cách so từng bước

Trong một thân phương thức so sánh, cách tổ chức hợp lý là:

```java
int result = Integer.compare(first.priority(), second.priority());
if (result != 0) {
    return result;
}

return Long.compare(first.sequence(), second.sequence());
```

Tiêu chí thứ hai chỉ được dùng khi tiêu chí thứ nhất ngang hàng. Nếu cần thêm tiêu chí, tiếp tục theo đúng quy tắc đó.

### Dùng các hàm tạo comparator theo kiểu

`comparingInt` và `comparingLong` giúp diễn đạt cùng ý nghĩa bằng một chuỗi:

```java
Comparator<Job> order = Comparator.comparingInt(Job::priority)
        .thenComparingLong(Job::sequence)
        .thenComparing(Job::id);
```

Trong ví dụ, `id` là một tiêu chí phụ xác định thứ tự giữa những công việc có cùng `priority` và `sequence`. Không được coi “so bằng không” chỉ là chuyện trình bày; nếu quy tắc được dùng trong tập hợp duy nhất hoặc làm khóa, nó ảnh hưởng tới cách nhận diện phần tử.

Ví dụ giả định công việc và `id` đều không `null`. Nếu dữ liệu cho phép thiếu giá trị, cần có chính sách riêng và đặt nó rõ ở comparator phù hợp.

## 11. Chương trình hoàn chỉnh: comparator an toàn và đảo chiều

Tạo tệp **`SafeJobOrderDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class SafeJobOrderDemo {
    public record Job(String id, int priority, long sequence) {
    }

    public static void main(String[] args) {
        List<Job> input = List.of(
                new Job("A", Integer.MAX_VALUE, 0),
                new Job("B", Integer.MIN_VALUE, Long.MAX_VALUE),
                new Job("C", 0, Long.MAX_VALUE),
                new Job("D", 0, Long.MIN_VALUE),
                new Job("E", 0, Long.MIN_VALUE));

        Comparator<Job> ascending = Comparator.comparingInt(Job::priority)
                .thenComparingLong(Job::sequence)
                .thenComparing(Job::id);

        List<Job> jobs = new ArrayList<>(input);
        jobs.sort(ascending);
        System.out.println("ascending ids = " + ids(jobs));

        jobs.sort(ascending.reversed());
        System.out.println("reverse all ids = " + ids(jobs));

        Comparator<Job> priorityDescending = Comparator
                .comparingInt(Job::priority).reversed()
                .thenComparingLong(Job::sequence)
                .thenComparing(Job::id);

        jobs.sort(priorityDescending);
        System.out.println("reverse priority only ids = " + ids(jobs));

        Comparator<Integer> arbitraryMagnitude = (left, right) -> {
            if (left < right) {
                return Integer.MIN_VALUE;
            }
            if (left > right) {
                return Integer.MAX_VALUE;
            }
            return 0;
        };

        int wrongReverse = -arbitraryMagnitude.compare(1, 2);
        int safeReverse = arbitraryMagnitude.reversed().compare(1, 2);
        System.out.println("negated result sign = " + Integer.signum(wrongReverse));
        System.out.println("reversed comparator sign = " + Integer.signum(safeReverse));
    }

    private static List<String> ids(List<Job> jobs) {
        return jobs.stream().map(Job::id).toList();
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 SafeJobOrderDemo.java
java -Dfile.encoding=UTF-8 SafeJobOrderDemo
```

Stdout:

```text
ascending ids = [B, D, E, C, A]
reverse all ids = [A, C, E, D, B]
reverse priority only ids = [A, D, E, C, B]
negated result sign = -1
reversed comparator sign = 1
```

### Theo dõi thứ tự công việc

- **Tăng dần:** `B` có priority nhỏ nhất; `A` lớn nhất. Các công việc priority bằng `0` được xét tiếp theo sequence rồi id.
- **Đảo toàn bộ:** cả priority, sequence và id đều bị đảo thứ tự.
- **Chỉ đảo priority:** priority giảm dần, nhưng các công việc cùng priority vẫn theo sequence tăng dần rồi id tăng dần.

Tên `priority` không tự quy định số lớn hơn hay nhỏ hơn phải được xử lý trước. Chương trình chọn rõ chiều tăng hoặc giảm; trong hệ thống thực tế, cần thống nhất ý nghĩa với yêu cầu nghiệp vụ.

### Vì sao comparator có độ lớn kết quả tùy ý vẫn hợp lệ?

`arbitraryMagnitude` trả về:

- `Integer.MIN_VALUE` khi nhỏ hơn.
- `Integer.MAX_VALUE` khi lớn hơn.
- `0` khi bằng nhau.

Dù độ lớn không đối xứng, dấu vẫn mô tả đúng thứ tự số. Hợp đồng yêu cầu quan hệ giữa các dấu, không yêu cầu hai kết quả là số đối chính xác của nhau.

Phép âm trực tiếp không đảo được `Integer.MIN_VALUE`, còn `reversed()` cho chiều đúng. Ví dụ này cho thấy không nên dựa vào giả định ngầm rằng comparator bên ngoài luôn trả về `-1` hoặc `1`.

## 12. Khi nào phép trừ không tràn?

Không nên kết luận rằng mọi phép trừ đều sai. Nó chỉ không an toàn như một cách so sánh tổng quát nếu không có bảo đảm về miền giá trị.

Nếu hai điểm số luôn thuộc `1..100`, hiệu nằm trong `-99..99`, có thể biểu diễn được bằng `int`.

Tuy nhiên, dùng phép trừ vẫn đặt ra nghĩa vụ chứng minh và giữ bất biến:

- Miền giá trị được kiểm tra ở đâu?
- Có đường nhập dữ liệu nào bỏ qua kiểm tra không?
- Yêu cầu có thể đổi sang số âm hoặc một phạm vi lớn hơn không?
- Cùng phương thức có được dùng lại cho kiểu dữ liệu khác không?
- Tiêu chí mới có làm biểu thức tính gộp vượt phạm vi không?

Nếu mục đích chỉ là so sánh, `Integer.compare` thường rõ ràng hơn và không phụ thuộc việc miền dữ liệu sau này được mở rộng.

### Phân biệt số có dấu với cách diễn giải không dấu

`Integer.compare` và `Long.compare` so theo giá trị có dấu. Nếu một miền nghiệp vụ thực sự diễn giải mẫu bit như số không dấu, Java có các thao tác như `compareUnsigned`.

Đây là lựa chọn về **ngữ nghĩa dữ liệu**, không phải cách chữa tùy tiện cho comparator bị tràn. Không đổi sang so không dấu chỉ vì thấy một giá trị âm, vì có thể làm sai hoàn toàn thứ tự mà nghiệp vụ muốn.

## 13. Kiểm tra hợp đồng bằng dữ liệu biên

Các kiểm tra hữu ích gồm:

1. **Tự so:** `compare(x, x) == 0`.
2. **Đổi chiều:** dấu của `compare(x, y)` phải là số đối của dấu `compare(y, x)`.
3. **Bắc cầu:** nếu `x > y` và `y > z` thì `x > z`.
4. **Nhóm ngang hàng:** nếu `compare(x, y) == 0`, quan hệ của `x` và `y` với một `z` phải nhất quán.

Tập mẫu cần có số âm, số dương, `0`, giá trị bằng nhau và các đầu phạm vi.

### Chương trình hoàn chỉnh

Tạo tệp **`BoundaryContractDemo.java`**:

```java
import java.util.Comparator;

public class BoundaryContractDemo {
    public static void main(String[] args) {
        int[] samples = {
                Integer.MIN_VALUE, Integer.MIN_VALUE + 1, -1, 0,
                1, Integer.MAX_VALUE - 1, Integer.MAX_VALUE
        };

        Comparator<Integer> unsafe = (left, right) -> left - right;
        Comparator<Integer> safe = Integer::compare;

        System.out.println("subtraction passes samples = "
                + obeysContract(unsafe, samples));
        System.out.println("Integer.compare passes samples = "
                + obeysContract(safe, samples));
    }

    private static boolean obeysContract(
            Comparator<Integer> order, int[] samples) {
        for (int first : samples) {
            if (order.compare(first, first) != 0) {
                return false;
            }

            for (int second : samples) {
                int firstSecond = Integer.signum(order.compare(first, second));
                int secondFirst = Integer.signum(order.compare(second, first));

                if (firstSecond != -secondFirst) {
                    return false;
                }

                for (int third : samples) {
                    int firstThird = Integer.signum(order.compare(first, third));
                    int secondThird = Integer.signum(order.compare(second, third));

                    if (firstSecond > 0 && secondThird > 0 && firstThird <= 0) {
                        return false;
                    }

                    if (firstSecond == 0 && firstThird != secondThird) {
                        return false;
                    }
                }
            }
        }
        return true;
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 BoundaryContractDemo.java
java -Dfile.encoding=UTF-8 BoundaryContractDemo
```

Stdout:

```text
subtraction passes samples = false
Integer.compare passes samples = true
```

### Giới hạn của kiểm chứng này

Chương trình kiểm tra các cặp và bộ ba trong một tập mẫu hữu hạn, dừng khi thấy vi phạm.

- Kết quả `false` là bằng chứng có lỗi trên ít nhất một trường hợp đã kiểm tra.
- Kết quả `true` chỉ chứng minh những mẫu đã chọn vượt qua điều kiện trong chương trình.
- Nó không thay thế việc lập luận rằng quy tắc đúng cho toàn bộ miền dữ liệu.
- Nó chưa kiểm tra các chính sách ngoài mục tiêu như xử lý `null`, thay đổi đối tượng sau khi thêm vào cây hoặc tính nhất quán với `equals`.

Với comparator so số nguyên chuẩn, lập luận dựa trên việc so quan hệ trực tiếp và không tính hiệu là phần quan trọng bên cạnh kiểm tra thực thi.

Khi chuyển bài học vào kiểm thử dự án, có thể dùng cùng các nhóm tình huống để xây dựng kiểm tra phù hợp. Không cần đưa comparator sai vào hệ thống chỉ để “xem khi nào thuật toán báo lỗi”.

## 14. Danh sách tự rà soát khi viết compareTo hoặc Comparator

| Câu hỏi | Dấu hiệu cần sửa |
| --- | --- |
| Có dùng `a - b` để trả kết quả? | Cần chứng minh miền giá trị hoặc đổi sang hàm compare đúng kiểu |
| Có ép hiệu `long` về `int`? | Có thể sai dấu hoặc trả `0` sai |
| Có mở rộng sau phép trừ? | Tràn có thể đã xảy ra trước khi ép kiểu |
| Có chuyển `long` sang `double` để so? | Có nguy cơ mất độ chính xác |
| Có dùng `signum` trên hiệu? | Chuẩn hóa một dấu sai không sửa được phép trừ |
| Có lấy số đối của kết quả comparator tùy ý? | `Integer.MIN_VALUE` không đảo dấu được bằng phép âm |
| Có cộng các kết quả tiêu chí? | Tiêu chí có thể lấn át hoặc triệt tiêu nhau |
| Có dữ liệu ở đầu phạm vi trong kiểm tra? | Nếu chưa, ví dụ nhỏ có thể đang che lỗi |
| Có dùng thứ tự cho cấu trúc duy nhất? | Cần kiểm tra ý nghĩa của `compare == 0` |

Mục tiêu của việc rà soát là để quy tắc so sánh mô tả đúng quan hệ nghiệp vụ, không chỉ vượt qua một lần sắp xếp tình cờ.

## 15. Thực hành

### Bài 1: bắt lỗi bằng một cặp số

Viết ra giá trị toán học và giá trị `int` thực tế của:

```text
Integer.MAX_VALUE - (-1)
Integer.MIN_VALUE - 1
0 - Integer.MIN_VALUE
```

Với mỗi biểu thức, xác định dấu đó có mô tả đúng quan hệ giữa hai toán hạng không. Kiểm tra lại bằng `Integer.compare`.

### Bài 2: phân biệt tràn với thu hẹp

Chọn:

```text
first  = 0L
second = 1L << 32
```

So sánh kết quả của:

- Hiệu `long` ban đầu.
- Hiệu sau khi ép về `int`.
- `Long.compare(first, second)`.

Giải thích tại sao hai giá trị khác nhau có thể bị comparator sai coi là ngang hàng mà không có tràn ở bước trừ `long`.

### Bài 3: sửa thứ tự công việc

Từ `SafeJobOrderDemo`, tạo yêu cầu mới:

1. Priority tăng dần.
2. Nếu priority bằng nhau, sequence giảm dần.
3. Nếu vẫn bằng nhau, id tăng dần.

Không trừ hai giá trị và không lấy số đối của kết quả tùy ý. Với dữ liệu sẵn có, thứ tự id cần là:

```text
[B, C, D, E, A]
```

Giải thích vị trí gọi `reversed()` để chỉ đảo sequence, không đảo các tiêu chí khác.

### Bài 4: mở rộng kiểm tra long

Viết một bộ kiểm tra tương tự `BoundaryContractDemo` cho `long`, dùng các giá trị:

```text
Long.MIN_VALUE, -1L, 0L, 1L, Long.MAX_VALUE
```

Thêm hai giá trị cách nhau đúng `2^32`. Đối chiếu comparator ép hiệu về `int` với `Long.compare`, rồi xác định trường hợp nào trả về `0` sai.

Tiêu chí hoàn thành là mô tả được nguyên nhân lỗi, chỉ ra dữ liệu tái hiện và sửa bằng một quy tắc giữ đúng dấu trên miền giá trị cần hỗ trợ.
