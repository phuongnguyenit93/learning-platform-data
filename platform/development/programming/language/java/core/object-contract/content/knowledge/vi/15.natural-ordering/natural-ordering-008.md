# Không dùng phép trừ dễ tràn số để cài đặt `compareTo()`

## 1. Vấn đề: phép trừ không luôn cho biết đúng thứ tự

Khi cài đặt `Comparable<T>.compareTo(T other)`, một cách viết rất dễ gặp là lấy hai trường số trừ cho nhau:

```java
@Override
public int compareTo(Item other) {
    return this.priority - other.priority; // Nguy hiểm nếu int bị tràn.
}
```

Đây chỉ là đoạn mã minh họa bên trong một lớp `Item` giả định có trường `int priority`, **không phải chương trình độc lập**. Nó có vẻ hợp lý: hiệu âm khi giá trị bên trái nhỏ hơn, hiệu bằng 0 khi bằng nhau, hiệu dương khi lớn hơn. Nhưng trong Java, `int` và `long` là các kiểu số nguyên có **giới hạn**. Kết quả toán học của phép trừ có thể vượt phạm vi lưu trữ; khi đó kết quả số nguyên Java bị tràn và có thể **đảo dấu**.

Thí dụ với `int`:

```text
Integer.MAX_VALUE =  2147483647
Integer.MIN_VALUE = -2147483648

Theo toán học: 2147483647 - (-1) = 2147483648, một số dương.
Trong int Java: 2147483647 - (-1) = -2147483648 (tràn số).
```

Như vậy, dù `2147483647 > -1`, phép trừ `2147483647 - (-1)` lại cho kết quả **âm**, khiến `compareTo()` sai về mặt thứ tự. Lỗi này khó phát hiện khi chỉ thử các số nhỏ như 1, 2, 3.

**Cách viết đúng là dùng `Integer.compare(a, b)` cho `int`, `Long.compare(a, b)` cho `long`, hoặc `Comparator.comparingInt`/`comparingLong` khi tạo comparator.** Các API đó so sánh trực tiếp thứ tự của hai giá trị thay vì phụ thuộc phép trừ có khả năng tràn.

## 2. Hợp đồng của `compareTo()`: quan trọng là dấu, không phải độ lớn

Với một lớp `T implements Comparable<T>`, `a.compareTo(b)` phải có ý nghĩa:

| Kết quả | Cách hiểu |
| --- | --- |
| Nhỏ hơn 0 | `a` đứng **trước** `b` trong thứ tự tự nhiên. |
| Bằng 0 | `a` và `b` được coi là **tương đương về thứ tự**. |
| Lớn hơn 0 | `a` đứng **sau** `b`. |

Không có yêu cầu kết quả phải chính xác là `-1`, `0`, `1`: chỉ **dấu** mới là hợp đồng quan trọng. Ví dụ, một triển khai `String.compareTo` có thể trả một số âm hoặc dương có độ lớn khác 1.

Các quy tắc đặc biệt cần bảo đảm:

1. **Phản đối xứng về dấu:** `sign(a.compareTo(b)) == -sign(b.compareTo(a))`. Hai chiều không thể cùng âm hoặc cùng dương.
2. **Bắc cầu:** nếu `a > b` và `b > c` theo `compareTo`, thì `a > c`. Tương tự đối với quan hệ nhỏ hơn.
3. **Tương đương nhất quán:** khi `a.compareTo(b) == 0`, `a` và `b` phải so với mọi đối tượng thứ ba theo cùng dấu.
4. **Không thay đổi khi dữ liệu so sánh giữ nguyên:** phép so sánh nên ổn định theo trạng thái dùng để xác định thứ tự.

Với một đối tượng `x`, `x.compareTo(null)` thông thường ném `NullPointerException` theo hợp đồng `Comparable`; bản thân comparator có thể được cấu hình chính sách xử lý `null`, ví dụ `Comparator.nullsFirst` hoặc `nullsLast`.

`compareTo` có kết quả 0 không **bắt buộc** đồng nghĩa với `equals == true`, nhưng **nên nhất quán với `equals`** khi dùng lớp làm kiểu giá trị hoặc khóa trong collection có thứ tự. Ví dụ nổi tiếng là `BigDecimal`: `new BigDecimal("1.0").compareTo(new BigDecimal("1.00")) == 0`, nhưng `equals` trả `false` vì khác scale. Phải xác định rõ điều này khi dùng `TreeSet`/`TreeMap`.

Nếu phép trừ gây sai dấu, ngay quy tắc đầu tiên đã có thể bị phá vỡ; sau đó thuật toán sắp xếp và cây cân bằng có thể hoạt động không đúng kỳ vọng.

## 3. Tràn `int` có thể phá cả phản đối xứng và bắc cầu

### 3.1. Cả hai chiều đều âm

Đặt `a = Integer.MAX_VALUE`, `b = -1`. Khi dùng hiệu `a - b`:

```text
a - b = 2147483647 - (-1)
      = -2147483648  (tràn int, dấu âm)

b - a = -1 - 2147483647
      = -2147483648  (không tràn, vẫn âm)
```

Cả `a.compareTo(b)` lẫn `b.compareTo(a)` đều có dấu âm. Điều này **vi phạm hợp đồng phản đối xứng về dấu**: không thể đồng thời khẳng định `a < b` và `b < a`.

Một sai lầm khác là lấy `Math.abs(a - b)` để so độ chênh lệch. `Math.abs(Integer.MIN_VALUE)` vẫn trả về `Integer.MIN_VALUE` vì `2147483648` không biểu diễn được bằng `int` dương. Dùng `Math.abs` không khắc phục vấn đề này.

### 3.2. Một bộ ba tạo thứ tự vòng

Chọn:

```text
a = Integer.MIN_VALUE = -2147483648
b = 0
c = Integer.MAX_VALUE =  2147483647
```

Với comparator sai `(x, y) -> x - y`:

```text
a - b = -2147483648 < 0, nên comparator nói a < b.
b - c = -2147483647 < 0, nên comparator nói b < c.
a - c = 1 > 0 do tràn int, nên comparator lại nói a > c.
```

Ta có `a < b`, `b < c`, nhưng `a > c`: **vi phạm tính bắc cầu**. Vì vậy, đây không đơn thuần là lỗi thứ tự của một cặp giá trị. Nó có thể khiến toàn bộ quan hệ thứ tự không còn hợp lệ.

Một thuật toán sắp xếp dựa vào comparator hợp lệ có thể cho thứ tự sai, và một số đường chạy của thư viện sắp xếp Java có thể phát hiện vi phạm hợp đồng và ném `IllegalArgumentException` với thông báo về hợp đồng comparator. Không được giả định rằng Java luôn phát hiện lỗi hoặc luôn ném ngoại lệ: hành vi tùy dữ liệu và đường đi thuật toán.

## 4. Cách an toàn với từng kiểu số

Java có các phương thức so sánh số nguyên theo **dấu thứ tự**:

```java
Integer.compare(aInt, bInt);
Long.compare(aLong, bLong);
Short.compare(aShort, bShort);
Byte.compare(aByte, bByte);
```

Các dòng trên là **lời gọi minh họa** với các biến đã tồn tại, không phải một chương trình độc lập. Phương thức trả số âm/0/dương theo giá trị thực của kiểu, không bị tràn do lấy hiệu.

Cài đặt `compareTo` theo kiểu điển hình:

```java
record Rank(int priority) implements Comparable<Rank> {
    @Override
    public int compareTo(Rank other) {
        return Integer.compare(priority, other.priority);
    }
}
```

Đối với `long`:

```java
record Sequence(long id) implements Comparable<Sequence> {
    @Override
    public int compareTo(Sequence other) {
        return Long.compare(id, other.id);
    }
}
```

Hai đoạn `record` là các khai báo kiểu độc lập có thể đặt ở top-level một tệp Java 17 (hoặc làm kiểu lồng hợp lệ); `record` tạo sẵn `equals/hashCode` dựa trên component và ở đây `compareTo` dùng đúng component đó.

Có thể viết phép so sánh phân nhánh thủ công:

```java
return a < b ? -1 : (a > b ? 1 : 0);
```

Nó cũng an toàn trước tràn số khi `a` và `b` cùng kiểu số nguyên có thứ tự. Tuy nhiên, `Integer.compare` hoặc `Long.compare` giúp biểu đạt ý định ngắn gọn và ít sai hơn.

### Nếu số không dấu hoặc dấu phẩy động?

- Với `int`/`long` đại diện **giá trị không dấu** theo các bit, dùng `Integer.compareUnsigned` hoặc `Long.compareUnsigned`. `Integer.compare`/ `Long.compare` coi số là **có dấu**. Chỉ chọn unsigned khi đây là yêu cầu dữ liệu thực tế.
- Với `float`/`double`, dùng `Float.compare` hoặc `Double.compare` khi cần thứ tự toàn phần theo quy tắc của wrapper, bao gồm `NaN` và phân biệt `-0.0` với `+0.0`. Không dùng phép trừ rồi ép sang `int`, vì còn có sai số, vô cực, NaN và kết quả ép kiểu không biểu đạt đúng quan hệ so sánh.
- Với `BigInteger`/`BigDecimal`, dùng `a.compareTo(b)` của chính kiểu đó; không cố chuyển sang `int`/`long` hoặc ép kết quả hiệu thành `int`.

## 5. Ví dụ Java 17: nhìn thấy tràn số và kết quả đúng

Tạo tệp `CompareOverflowDemo.java`:

```java
public class CompareOverflowDemo {
    static int wrong(int a, int b) {
        return a - b;
    }

    static int safe(int a, int b) {
        return Integer.compare(a, b);
    }

    static long wrongLong(long a, long b) {
        return a - b;
    }

    public static void main(String[] args) {
        int high = Integer.MAX_VALUE;
        int low = -1;

        System.out.println("high > low: " + (high > low));
        System.out.println("wrong(high, low): " + wrong(high, low));
        System.out.println("wrong(low, high): " + wrong(low, high));
        System.out.println("safe(high, low): " + safe(high, low));
        System.out.println("safe(low, high): " + safe(low, high));

        int min = Integer.MIN_VALUE;
        int mid = 0;
        int max = Integer.MAX_VALUE;

        System.out.println("bad min < mid: " + (wrong(min, mid) < 0));
        System.out.println("bad mid < max: " + (wrong(mid, max) < 0));
        System.out.println("bad min > max: " + (wrong(min, max) > 0));
        System.out.println("safe min < max: " + (safe(min, max) < 0));

        long big = Long.MAX_VALUE;
        System.out.println("wrong long sign: " + (wrongLong(big, -1L) < 0));
        System.out.println("safe long sign: " + (Long.compare(big, -1L) > 0));

        long gap = 4_294_967_296L;
        System.out.println("cast diff zero: " + ((int) (gap - 0L) == 0));
        System.out.println("compare long gap: " + (Long.compare(gap, 0L) > 0));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac CompareOverflowDemo.java
java CompareOverflowDemo
```

Stdout chính xác:

```text
high > low: true
wrong(high, low): -2147483648
wrong(low, high): -2147483648
safe(high, low): 1
safe(low, high): -1
bad min < mid: true
bad mid < max: true
bad min > max: true
safe min < max: true
wrong long sign: true
safe long sign: true
cast diff zero: true
compare long gap: true
```

Phân tích:

- Hai phép `wrong(high, low)` và `wrong(low, high)` đều âm, cho thấy **cùng một cặp nhưng hai chiều trái hợp đồng**.
- Bộ ba `min, mid, max` tạo thứ tự vòng với `wrong`: `min < mid < max` nhưng comparator kết luận `min > max`.
- Với `long`, `Long.MAX_VALUE - (-1L)` cũng tràn thành `Long.MIN_VALUE`; đừng nghĩ đổi `int` sang `long` là sửa tận gốc.
- Ép `(int)(longA - longB)` đặc biệt nguy hiểm: hai giá trị `long` khác nhau đúng `2^32` có hiệu khi ép sang `int` bằng **0**, khiến comparator sai ngay cả về việc coi hai giá trị là bằng thứ tự. `Long.compare` xử lý chính xác.

Nếu cần trình bày sai lệch giữa hai số mà không bị tràn, đó là **bài toán tính chênh lệch**, khác với bài toán **xác định thứ tự**. Khi thật sự cần hiệu chính xác vượt phạm vi kiểu, có thể dùng `Math.subtractExact` để phát hiện overflow hoặc `BigInteger` để biểu diễn số lớn, nhưng các cách này không phải lựa chọn cần thiết chỉ để viết `compareTo`.

## 6. So sánh nhiều trường: thứ tự khóa chính, khóa phụ

Một lớp thường có nhiều trường xác định thứ tự, chẳng hạn sắp xếp nhân viên theo `level` tăng dần, rồi `employeeId` tăng dần. Tuyệt đối không viết:

```java
// Sai: cả hai trường số đều có nguy cơ tràn; đây là đoạn minh họa.
int byLevel = this.level - other.level;
if (byLevel != 0) return byLevel;
return (int) (this.employeeId - other.employeeId);
```

Ở nhánh `employeeId`, ngoài overflow của `long` còn có lỗi ép xuống `int`. Nên thực hiện **so sánh theo dấu** cho từng trường và chỉ chuyển sang khóa phụ khi kết quả khóa trước là 0:

```java
@Override
public int compareTo(Employee other) {
    int byLevel = Integer.compare(this.level, other.level);
    if (byLevel != 0) {
        return byLevel;
    }
    return Long.compare(this.employeeId, other.employeeId);
}
```

Đoạn mã chỉ là phần thân phương thức minh họa cho `Employee` có hai trường tương ứng. Đối với nhiều trường kiểu chuỗi, sử dụng `String.compareTo` và xác định riêng chính sách `null` nếu dữ liệu có thể vắng.

Một công thức thay thế dùng `Comparator` có thể dễ đọc hơn:

```java
Comparator<Employee> ORDER =
        Comparator.comparingInt(Employee::level)
                  .thenComparingLong(Employee::employeeId);
```

`Comparator.comparingInt` và `thenComparingLong` dùng so sánh primitive an toàn. Các lệnh này là đoạn minh họa với lớp `Employee` có accessor `level()` và `employeeId()`. Không nên tạo comparator bằng `(a, b) -> a.level() - b.level()` chỉ để ngắn dòng.

### So sánh giảm dần không cần nhân với `-1`

Một thói quen khác là đảo thứ tự bằng `-ascendingCompare(a, b)`. Hợp đồng `Comparable` chỉ yêu cầu giá trị âm/0/dương, **không bảo đảm** kết quả của mọi `compareTo` chỉ thuộc `-1, 0, 1`. Nếu một comparator hợp lệ trả `Integer.MIN_VALUE`, lấy dấu âm của kết quả đó vẫn bằng `Integer.MIN_VALUE` do tràn.

Để đảo thứ tự, dùng `comparator.reversed()` hoặc so sánh **đảo đối số** bằng API an toàn, ví dụ `Integer.compare(b, a)`, thay vì nhân hoặc đổi dấu một kết quả comparator bất kỳ.

## 7. Ví dụ hoàn chỉnh Java 17: thứ tự tự nhiên nhiều trường

Tạo tệp `EmployeeOrderDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class EmployeeOrderDemo {
    record Employee(int level, long employeeId, String name)
            implements Comparable<Employee> {

        @Override
        public int compareTo(Employee other) {
            int byLevel = Integer.compare(level, other.level);
            if (byLevel != 0) {
                return byLevel;
            }

            int byId = Long.compare(employeeId, other.employeeId);
            if (byId != 0) {
                return byId;
            }

            return name.compareTo(other.name);
        }
    }

    public static void main(String[] args) {
        Employee high = new Employee(Integer.MAX_VALUE, 10L, "H");
        Employee low = new Employee(Integer.MIN_VALUE, 11L, "L");
        Employee lowSecond = new Employee(Integer.MIN_VALUE, 12L, "S");

        System.out.println("high > low: " + (high.compareTo(low) > 0));
        System.out.println("low < high: " + (low.compareTo(high) < 0));
        System.out.println("low < lowSecond: " + (low.compareTo(lowSecond) < 0));

        List<Employee> employees =
                new ArrayList<>(List.of(high, lowSecond, low));
        employees.sort(Comparator.naturalOrder());

        System.out.println("first: " + employees.get(0).name());
        System.out.println("second: " + employees.get(1).name());
        System.out.println("third: " + employees.get(2).name());

        Comparator<Employee> byFields =
                Comparator.comparingInt(Employee::level)
                          .thenComparingLong(Employee::employeeId)
                          .thenComparing(Employee::name);

        System.out.println("same ordering: "
                + (Integer.signum(high.compareTo(low))
                   == Integer.signum(byFields.compare(high, low))));

        Comparator<Employee> descending = byFields.reversed();
        System.out.println("reversed high first: "
                + (descending.compare(high, low) < 0));
    }
}
```

Biên dịch/chạy:

```bash
javac EmployeeOrderDemo.java
java EmployeeOrderDemo
```

Stdout:

```text
high > low: true
low < high: true
low < lowSecond: true
first: L
second: S
third: H
same ordering: true
reversed high first: true
```

Giải thích: `level` được xét trước `employeeId`, sau đó mới xét `name`. Hai nhân viên cùng `Integer.MIN_VALUE` được xếp theo `employeeId` 11 trước 12; nhân viên `Integer.MAX_VALUE` xếp sau. Bộ `Comparator` tạo bằng các hàm so sánh trường biểu diễn đúng cùng thứ tự, còn `reversed()` dùng khi cần giảm dần.

Ở đây record `Employee` sinh sẵn `equals/hashCode` dựa trên cả ba component; `compareTo` cũng xét cả ba component, nên với dữ liệu `name` không null, ví dụ duy trì tính nhất quán tự nhiên giữa thứ tự và bình đẳng. Nếu cố tình chỉ so sánh `level` mà bỏ `employeeId/name`, hai record khác nhau có thể có `compareTo == 0`, điều này cần được quyết định rõ theo nghiệp vụ.

## 8. Những lỗi sửa sai tưởng đúng nhưng vẫn nguy hiểm

| Cách viết | Vấn đề | Thay thế |
| --- | --- | --- |
| `return a - b;` với `int` | Tràn, trả sai dấu, phá hợp đồng. | `Integer.compare(a, b)`. |
| `return (int) (aLong - bLong);` | Có thể tràn `long` và mất bit khi ép `int`. | `Long.compare(aLong, bLong)`. |
| `return Math.abs(a - b);` | Mất dấu thứ tự và `abs(MIN_VALUE)` vẫn âm. | Dùng API compare trực tiếp. |
| `return (a - b) > 0 ? 1 : ...;` | Kiểm tra **sau phép trừ** vẫn chịu overflow. | `a < b ? -1 : a > b ? 1 : 0`, hoặc API compare. |
| `return -other.compareTo(this);` | Đổi dấu `Integer.MIN_VALUE` có thể tràn nếu comparator trả giá trị đó. | `Comparator.reversed()` hoặc so sánh đối số đảo đúng cách. |
| So sánh khóa phụ bằng phép trừ sau khi khóa chính bằng nhau | Cùng lỗi overflow ở nhánh ít gặp. | `thenComparingInt`, `thenComparingLong`, hoặc `Long.compare`. |
| Chỉ kiểm tra số nhỏ và dương | Không bắt lỗi ở biên miền số, dấu khác nhau. | Kiểm tra `MIN_VALUE`, `MAX_VALUE`, âm, 0, dương. |

Ngoài overflow, một `compareTo` có thể sai hợp đồng vì dùng dữ liệu thay đổi theo thời gian, quy tắc xử lý `null` thiếu nhất quán, cài đặt không đối xứng ở các nhánh lớp con, hoặc so sánh theo một trường không ổn định khi đã đưa đối tượng vào `TreeSet`/`TreeMap`. Đừng xem việc thay dấu trừ bằng `Integer.compare` là đủ nếu các phần còn lại của chính sách thứ tự vẫn mâu thuẫn.

### Lưu ý với `TreeSet` và `TreeMap`

Các collection có thứ tự như `TreeSet` và `TreeMap` dựa vào `compareTo` hoặc `Comparator` để tìm kiếm và xác định hai khóa tương đương về thứ tự. Nếu comparator trả `0` cho hai khóa khác nhau do ép kiểu làm mất bit, collection có thể coi chúng là cùng vị trí khóa dù `equals` trả `false`. Nếu comparator sai bắc cầu, cấu trúc cây có thể không còn bảo đảm các thao tác `contains`/`get`/`remove` như mong đợi.

Không nên thay đổi các trường tham gia `compareTo`/`Comparator` trong khi đối tượng đang được dùng làm khóa `TreeMap` hoặc phần tử `TreeSet`, vì collection không tự xây dựng lại thứ tự khi trạng thái khóa đổi.

Với những kiểu mà `compareTo == 0` khác `equals == true` theo thiết kế (ví dụ `BigDecimal`), cần hiểu `TreeSet` sử dụng **tương đương về thứ tự** để xác định một phần tử đã có mặt. Đây là một chủ đề riêng nhưng liên quan trực tiếp đến việc chọn khóa so sánh và viết comparator không lỗi.

## 9. Cách kiểm thử một cài đặt `compareTo`

Thay vì chỉ gọi `sort` rồi nhìn danh sách, hãy kiểm tra **hợp đồng** của phép so sánh trên các mẫu đã chọn.

### Mẫu biên bắt buộc

Với trường `int`, nên có:

```text
Integer.MIN_VALUE
Integer.MIN_VALUE + 1
-1
0
1
Integer.MAX_VALUE - 1
Integer.MAX_VALUE
```

Với `long`, dùng tương tự `Long.MIN_VALUE` và `Long.MAX_VALUE`, cùng một cặp cách nhau `2^32` để bắt lỗi ép xuống `int`.

### Kiểm tra từng cặp hai chiều

Đối với mọi cặp mẫu `a` và `b`, cần xác nhận:

```text
sign(a.compareTo(b)) == -sign(b.compareTo(a))
```

Dùng `Integer.signum(result)` để lấy dấu `-1`, `0`, hoặc `1` **sau khi comparator trả kết quả**; không có phép trừ ở đây. Với phép so sánh thứ tự từ giá trị gốc, có thể đối chiếu dấu với `Integer.compare` hoặc `Long.compare`.

Nên thử ít nhất những cặp sau: `MIN` với `MAX`; `MAX` với `-1`; `MIN` với `1`; hai giá trị bằng nhau; hai giá trị sát nhau; và cặp `long` rất xa nhau.

### Kiểm tra bộ ba có thứ tự

Với bộ ba `a`, `b`, `c` và một comparator dự kiến tăng dần:

```text
Nếu compare(a,b) < 0 và compare(b,c) < 0
thì compare(a,c) phải < 0.
```

Tương tự cho chiều lớn hơn. Khi comparator có thể trả `0`, cần kiểm tra thêm rằng quan hệ tương đương theo `compare == 0` là bắc cầu và các đối tượng tương đương có cùng dấu khi so sánh với một đối tượng thứ ba. Một bộ kiểm thử tự động có thể duyệt tất cả cặp và bộ ba có thứ tự trên tập dữ liệu biên nhỏ.

Thử nghiệm hữu hạn giúp **tìm** sai lệch nhưng không chứng minh tuyệt đối mọi giá trị có thể có. Cách cài đặt dựa trên `Integer.compare`/`Long.compare` và chain nhất quán vẫn có nền tảng đáng tin cậy hơn thử nghiệm ngẫu nhiên của `a - b`.

### Checklist trước khi sử dụng

1. Tất cả trường số đều dùng phương thức `compare` phù hợp, không dùng phép trừ để quyết định dấu?
2. Mọi khóa phụ cũng sử dụng phép so sánh an toàn và chỉ chạy khi khóa trước bằng nhau?
3. Có ép kết quả `long` xuống `int`, dùng `Math.abs`, hoặc đảo dấu một giá trị comparator bất kỳ?
4. Các giá trị biên âm/dương, cực tiểu/cực đại được bao phủ?
5. Có kiểm tra hai hướng từng cặp và một số bộ ba, đặc biệt những bộ ba nằm gần biên?
6. `compareTo == 0` có phù hợp với ý nghĩa bằng nhau theo nghiệp vụ và với `equals` hay đã được ghi rõ lý do khác biệt?
7. Các trường tham gia thứ tự có ổn định khi đối tượng đã được lưu trong `TreeMap`/`TreeSet`?

## 10. Câu hỏi tự luyện

1. Vì sao `Integer.MAX_VALUE - (-1)` làm comparator dùng phép trừ trả dấu sai?
2. Nếu cả `a - b` và `b - a` cùng âm trong `int`, điều kiện nào của `compareTo` bị vi phạm?
3. Cho `a = Integer.MIN_VALUE`, `b = 0`, `c = Integer.MAX_VALUE`. Bộ ba này bộc lộ lỗi bắc cầu nào với `(x, y) -> x - y`?
4. Vì sao chỉ đổi kiểu `int` thành `long` không khắc phục hoàn toàn tràn số?
5. Vì sao `(int)(leftLong - rightLong)` còn nguy hiểm hơn việc so sánh `long` bằng phép trừ?
6. Với đối tượng có `level`, `id`, `name`, cách triển khai sắp xếp tăng dần theo cả ba trường là gì?
7. Khi cần thứ tự giảm dần, vì sao `comparator.reversed()` đáng tin cậy hơn phủ định trực tiếp một kết quả comparator tùy ý?
8. Một comparator trả `0` cho hai đối tượng có ID khác nhau có thể ảnh hưởng gì đến `TreeSet`?
9. Khi nào nên dùng `Integer.compareUnsigned` thay cho `Integer.compare`?

**Ghi nhớ:** `compareTo()` và `Comparator.compare()` cần trả **đúng dấu của quan hệ thứ tự**, không cần trả hiệu hai số. Phép trừ `a - b` trên `int`/`long` có thể overflow và phá cả phản đối xứng lẫn bắc cầu. Hãy dùng `Integer.compare`, `Long.compare`, và các phương thức xây dựng `Comparator` tương ứng cho mọi trường, kể cả khóa phụ.