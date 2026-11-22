# Thực hành thống kê mảng và tách thành phương thức trong Java

## 1. Mục tiêu và yêu cầu bài thực hành

Với một mảng số nguyên `int[]`, hãy xây dựng chương trình Java 17+ thống kê:

1. **Độ dài mảng**: tổng số phần tử.
2. **Số lượng số dương, số âm và số 0**: số dương thỏa `x > 0`, số âm thỏa `x < 0`, còn số 0 là `x == 0`.
3. **Tổng các phần tử**: dùng kiểu `long` để tránh tràn `int` ở những trường hợp cộng nhiều số nguyên.
4. **Giá trị nhỏ nhất (`min`) và lớn nhất (`max`)** khi mảng không rỗng.
5. **Trung bình cộng** khi mảng có ít nhất một phần tử; dùng phép chia số thực để không mất phần thập phân.

Yêu cầu chất lượng: **không dồn toàn bộ logic vào `main`**. Hãy tách phần tính toán, tổng hợp và trình bày thành các phương thức có tên rõ ràng. Phương thức thống kê không được sửa các phần tử của mảng đầu vào.

Với đầu vào mẫu:

```text
[8, -3, 0, 7, -2, 8]
```

kết quả mong đợi là:

| Chỉ tiêu | Giá trị | Lý do |
| --- | ---: | --- |
| Độ dài | 6 | Có sáu phần tử |
| Số dương | 3 | `8, 7, 8` |
| Số âm | 2 | `-3, -2` |
| Số 0 | 1 | Một số `0` |
| Tổng | 18 | `8 - 3 + 0 + 7 - 2 + 8 = 18` |
| Nhỏ nhất | -3 | Số nhỏ nhất trong toàn bộ mảng |
| Lớn nhất | 8 | Số lớn nhất trong toàn bộ mảng |
| Trung bình | 3.00 | `18 / 6 = 3.0` |

Lưu ý: **tổng, min, max và trung bình ở đây áp dụng cho toàn bộ mảng**, không chỉ các số dương. Bộ đếm dương/âm/0 là những thống kê bổ sung. Phải phân biệt rõ điều đó khi đọc yêu cầu để không tính ra giá trị sai.

## 2. Chia bài toán thành những phương thức nhỏ

Thay vì viết một `main` dài với nhiều vòng lặp, có thể thiết kế các phương thức độc lập:

| Phương thức | Đầu vào | Kết quả / trách nhiệm |
| --- | --- | --- |
| `sum(int[] values)` | Mảng số nguyên | Tổng dưới dạng `long` |
| `countPositive(int[] values)` | Mảng số nguyên | Số phần tử `> 0` |
| `countNegative(int[] values)` | Mảng số nguyên | Số phần tử `< 0` |
| `findMin(int[] values)` | Mảng số nguyên | `OptionalInt`: giá trị nhỏ nhất, hoặc rỗng |
| `findMax(int[] values)` | Mảng số nguyên | `OptionalInt`: giá trị lớn nhất, hoặc rỗng |
| `average(long sum, int count)` | Tổng và số lượng | `OptionalDouble`: trung bình, hoặc rỗng nếu không có phần tử |
| `analyze(int[] values)` | Mảng số nguyên | Ghép các kết quả trên thành một đối tượng `Stats` |
| `printReport(String title, int[] values)` | Tiêu đề và mảng | In kết quả rõ ràng, không tự tính lại công thức trong code in |
| `main(String[] args)` | Điểm vào ứng dụng | Chuẩn bị dữ liệu, gọi các phương thức, kiểm tra kết quả |

Cách phân chia này dựa trên **một trách nhiệm chính cho mỗi phương thức**:

- Các hàm `sum`, `countPositive`, `countNegative`, `findMin`, `findMax` tập trung vào phép tính, không in màn hình.
- `analyze` là nơi **phối hợp** các phép tính và xác nhận tiền điều kiện của đầu vào.
- `printReport` chỉ quyết định **cách hiển thị** các thống kê đã được tính.
- `main` giữ vai trò tổ chức tình huống chạy, thay vì chứa toàn bộ thuật toán.

Khi một bước hoạt động sai, biết chính xác phương thức nào cần kiểm tra. Các phương thức chỉ tính toán và trả về giá trị còn có thể được **kiểm thử riêng** mà không cần đọc văn bản in trên console.

### Hợp đồng (contract) của phương thức

Trước khi viết Java, xác định rõ:

- **Tiền điều kiện:** đầu vào `values` phải khác `null`. Mảng rỗng `new int[0]` **được phép**.
- **Hậu điều kiện:** `sum` là tổng mọi phần tử; `countPositive + countNegative + countZero == values.length`.
- **Không tác dụng phụ:** các phép tính không sửa `values[i]`, không in ra màn hình, không phụ thuộc biến toàn cục có thể thay đổi.
- **Đầu vào rỗng:** tổng và các bộ đếm bằng `0`; `min`, `max` và `average` **không có giá trị**, không được tự gán `0` làm kết quả cực trị/trung bình.
- **Đầu vào `null`:** phương thức tổng hợp `analyze` từ chối rõ ràng bằng `Objects.requireNonNull`, thay vì coi `null` như mảng rỗng.

Các helper nội bộ trong bài được gọi từ `analyze` sau bước kiểm tra `null`; nếu tái sử dụng chúng thành API công khai, cần xác định và thực thi tiền điều kiện riêng cho từng helper.

## 3. Mã giả trước khi triển khai

Đây là mô tả thuật toán; **không phải mã Java để biên dịch**.

```text
FUNCTION SUM(values):
    total ← 0 (dùng số nguyên 64-bit)
    FOR EACH x IN values:
        total ← total + x
    RETURN total

FUNCTION COUNT_POSITIVE(values):
    count ← 0
    FOR EACH x IN values:
        IF x > 0:
            count ← count + 1
    RETURN count

FUNCTION COUNT_NEGATIVE(values):
    count ← 0
    FOR EACH x IN values:
        IF x < 0:
            count ← count + 1
    RETURN count

FUNCTION MIN(values):
    IF values rỗng: RETURN không có giá trị
    result ← values[0]
    FOR EACH phần tử còn lại x:
        IF x < result: result ← x
    RETURN result

FUNCTION MAX(values):
    IF values rỗng: RETURN không có giá trị
    result ← values[0]
    FOR EACH phần tử còn lại x:
        IF x > result: result ← x
    RETURN result

FUNCTION AVERAGE(total, count):
    IF count = 0: RETURN không có giá trị
    RETURN (số thực) total / count

FUNCTION ANALYZE(values):
    IF values = null: báo lỗi đầu vào
    positives ← COUNT_POSITIVE(values)
    negatives ← COUNT_NEGATIVE(values)
    zeros ← LENGTH(values) - positives - negatives
    total ← SUM(values)
    minimum ← MIN(values)
    maximum ← MAX(values)
    mean ← AVERAGE(total, LENGTH(values))
    RETURN tất cả kết quả thống kê
```

**Vì sao đếm số 0 bằng phép trừ được?** Mỗi số nguyên thuộc đúng một trong ba nhóm `> 0`, `< 0`, `== 0`. Ba nhóm không chồng lấn và bao phủ toàn bộ mảng; do đó `zeros = length - positives - negatives` đúng.

**Vì sao `min` và `max` cần xử lý mảng rỗng?** Không thể truy cập `values[0]` khi `values.length == 0`. Cũng không thể nói giá trị nhỏ nhất của một mảng rỗng bằng `0`: `0` có thể là dữ liệu hợp lệ, nhưng mảng rỗng không có phần tử nào cả.

## 4. Dự đoán bằng bảng theo dõi

Với `[8, -3, 0, 7, -2, 8]`, có thể theo dõi bộ đếm và tổng trong một lượt **chạy tay theo từng phần tử** như sau:

| Bước | Phần tử `x` | Dương | Âm | Bằng 0 | Tổng sau bước |
| --- | ---: | ---: | ---: | ---: | ---: |
| Khởi tạo | — | 0 | 0 | 0 | 0 |
| 1 | 8 | 1 | 0 | 0 | 8 |
| 2 | -3 | 1 | 1 | 0 | 5 |
| 3 | 0 | 1 | 1 | 1 | 5 |
| 4 | 7 | 2 | 1 | 1 | 12 |
| 5 | -2 | 2 | 2 | 1 | 10 |
| 6 | 8 | 3 | 2 | 1 | 18 |

Bảng mô tả **trạng thái tổng hợp giả lập sau mỗi phần tử**, hữu ích để kiểm tra logic; chương trình tách hàm ở phần sau thực hiện các phép tính bằng **những lượt duyệt độc lập** và cuối cùng thu được cùng kết quả.

Khi tính `min` và `max`, bắt đầu từ phần tử đầu tiên `8`. Sau khi gặp `-3`, `min = -3`; không có phần tử nào nhỏ hơn, nên kết quả cuối là `-3`. `max` luôn là `8` với mảng này. Kết quả trung bình: `18 / 6 = 3.0`.

Một bảng như vậy giúp kiểm tra bước **đầu tiên** khiến tổng hoặc bộ đếm khác dự đoán. Khi thực hành, có thể đặt breakpoint trong từng phương thức và so sánh kết quả thực tế với bảng.

## 5. Java 17+: chương trình hoàn chỉnh được tách thành phương thức

Tạo đúng một tệp **`ArrayStatisticsPractice.java`**:

```java
import java.util.Arrays;
import java.util.Locale;
import java.util.Objects;
import java.util.OptionalDouble;
import java.util.OptionalInt;

public class ArrayStatisticsPractice {
    record Stats(
            int length,
            int positive,
            int negative,
            int zero,
            long sum,
            OptionalInt min,
            OptionalInt max,
            OptionalDouble average) {}

    static long sum(int[] values) {
        long total = 0L;
        for (int value : values) {
            total += value;
        }
        return total;
    }

    static int countPositive(int[] values) {
        int count = 0;
        for (int value : values) {
            if (value > 0) {
                count++;
            }
        }
        return count;
    }

    static int countNegative(int[] values) {
        int count = 0;
        for (int value : values) {
            if (value < 0) {
                count++;
            }
        }
        return count;
    }

    static OptionalInt findMin(int[] values) {
        if (values.length == 0) {
            return OptionalInt.empty();
        }
        int result = values[0];
        for (int i = 1; i < values.length; i++) {
            if (values[i] < result) {
                result = values[i];
            }
        }
        return OptionalInt.of(result);
    }

    static OptionalInt findMax(int[] values) {
        if (values.length == 0) {
            return OptionalInt.empty();
        }
        int result = values[0];
        for (int i = 1; i < values.length; i++) {
            if (values[i] > result) {
                result = values[i];
            }
        }
        return OptionalInt.of(result);
    }

    static OptionalDouble average(long total, int count) {
        if (count == 0) {
            return OptionalDouble.empty();
        }
        return OptionalDouble.of((double) total / count);
    }

    static Stats analyze(int[] values) {
        Objects.requireNonNull(values, "values");

        int positive = countPositive(values);
        int negative = countNegative(values);
        int zero = values.length - positive - negative;
        long total = sum(values);

        return new Stats(
                values.length,
                positive,
                negative,
                zero,
                total,
                findMin(values),
                findMax(values),
                average(total, values.length));
    }

    static void printReport(String title, int[] values) {
        Stats stats = analyze(values);
        System.out.println(title);
        System.out.println("array=" + Arrays.toString(values));
        System.out.println("length=" + stats.length());
        System.out.println("positive=" + stats.positive());
        System.out.println("negative=" + stats.negative());
        System.out.println("zero=" + stats.zero());
        System.out.println("sum=" + stats.sum());

        System.out.println("min=" + (stats.min().isPresent()
                ? stats.min().getAsInt() : "N/A"));
        System.out.println("max=" + (stats.max().isPresent()
                ? stats.max().getAsInt() : "N/A"));

        if (stats.average().isPresent()) {
            System.out.printf(Locale.US, "average=%.2f%n",
                    stats.average().getAsDouble());
        } else {
            System.out.println("average=N/A");
        }
    }

    static void check(String label, boolean condition) {
        if (!condition) {
            throw new AssertionError(label);
        }
        System.out.println("test " + label + ": PASS");
    }

    public static void main(String[] args) {
        int[] sample = {8, -3, 0, 7, -2, 8};
        int[] empty = {};
        int[] negatives = {-5, -1, -5};
        int[] large = {Integer.MAX_VALUE, Integer.MAX_VALUE};

        printReport("Case A", sample);
        printReport("Case B", empty);
        printReport("Case C", negatives);
        printReport("Case D", large);

        Stats a = analyze(sample);
        Stats b = analyze(empty);
        Stats d = analyze(large);

        check("sample", a.length() == 6
                && a.positive() == 3 && a.negative() == 2
                && a.zero() == 1 && a.sum() == 18L
                && a.min().orElseThrow() == -3
                && a.max().orElseThrow() == 8);

        check("empty", b.length() == 0 && b.sum() == 0
                && b.min().isEmpty() && b.max().isEmpty()
                && b.average().isEmpty());

        check("large sum", d.sum() == 4294967294L);
    }
}
```

Chương trình không cần thư viện bên ngoài. Dùng **JDK 17 trở lên** và mở terminal tại thư mục chứa `ArrayStatisticsPractice.java`:

```bash
javac -encoding UTF-8 ArrayStatisticsPractice.java
java ArrayStatisticsPractice
```

Lệnh `javac` thành công không in thông báo. **Stdout chính xác** của `java`:

```text
Case A
array=[8, -3, 0, 7, -2, 8]
length=6
positive=3
negative=2
zero=1
sum=18
min=-3
max=8
average=3.00
Case B
array=[]
length=0
positive=0
negative=0
zero=0
sum=0
min=N/A
max=N/A
average=N/A
Case C
array=[-5, -1, -5]
length=3
positive=0
negative=3
zero=0
sum=-11
min=-5
max=-1
average=-3.67
Case D
array=[2147483647, 2147483647]
length=2
positive=2
negative=0
zero=0
sum=4294967294
min=2147483647
max=2147483647
average=2147483647.00
test sample: PASS
test empty: PASS
test large sum: PASS
```

### Giải thích bốn bộ dữ liệu

- **Case A**: đủ số dương, âm, số 0; trung bình của toàn mảng là `3.00`.
- **Case B**: mảng rỗng; bộ đếm và tổng bằng 0, còn `min`, `max` và `average` là `N/A`, tránh truy cập `values[0]` hoặc chia 0.
- **Case C**: chỉ có số âm; `max = -1` (không phải 0) và trung bình `-11 / 3` được in thành `-3.67`.
- **Case D**: hai giá trị `Integer.MAX_VALUE`. Tổng toán học bằng `4294967294` vượt phạm vi `int`, nhưng `long sum` giữ được kết quả chính xác trong trường hợp này.

Ba phép kiểm tra cuối dùng phương thức `check`: nếu điều kiện sai thì ném `AssertionError`, thay vì luôn in `PASS` dù thuật toán sai. Không phải test framework đầy đủ, nhưng đủ để thực hành cách kiểm tra đầu ra theo kỳ vọng.

## 6. Tại sao dùng `OptionalInt` và `OptionalDouble`?

Một sai lầm phổ biến là để `min = 0`, `max = 0` khi mảng rỗng rồi in ra như thể đó là thống kê hợp lệ.

Ví dụ đối với mảng `{-5, -1, -5}`, `max` thật sự là `-1`, **không phải 0**. Nếu khởi tạo `max = 0` và chỉ cập nhật khi phần tử lớn hơn `max`, thuật toán sẽ giữ kết quả sai là `0`.

Trong chương trình này:

- `OptionalInt.of(value)` biểu diễn **có một giá trị `int`**.
- `OptionalInt.empty()` biểu diễn **không tồn tại giá trị** để trả về.
- `OptionalDouble` có ý nghĩa tương tự cho trung bình số thực.

Phần in kết quả chỉ gọi `getAsInt()` sau khi `isPresent()` là `true`; chỉ gọi `getAsDouble()` khi `average` có giá trị. Nếu truy cập `getAsInt()` trên `OptionalInt.empty()`, Java ném `NoSuchElementException`.

`OptionalInt`/`OptionalDouble` phù hợp để **thể hiện một kết quả có thể vắng mặt**; đây không phải cách duy nhất. Với bài nhỏ, cũng có thể dùng điều kiện `values.length == 0` trước khi tính hoặc in min/max. Quan trọng nhất là **đừng lẫn “không có kết quả” với kết quả bằng 0**.

## 7. `record Stats`: gom kết quả mà không dồn logic tính toán

Java 17 hỗ trợ **`record`**, thuận tiện để biểu diễn một nhóm dữ liệu trả về cùng nhau:

```java
record Stats(int length, int positive, int negative) {}
```

Đây chỉ là **minh họa cú pháp**, còn chương trình đầy đủ đã định nghĩa một `Stats` với tám trường. Record tự cung cấp constructor, các phương thức truy cập tên như `length()`, `positive()` và các thành phần phù hợp khác.

Tách bước trả kết quả thành `Stats` giúp tránh dùng biến toàn cục hoặc những tham số truyền đi truyền lại chỉ để cập nhật kết quả. Vì phương thức `analyze` trả một giá trị tổng hợp, nhiều nơi khác nhau có thể sử dụng thống kê theo nhu cầu (in báo cáo, kiểm thử, lưu dữ liệu...) mà không phải chạy lại từng phương thức thủ công.

**Không nhầm record với bất biến tuyệt đối của mọi tham chiếu.** Record giữ trạng thái các thành phần dưới dạng field `final`, nhưng nếu chứa một đối tượng có thể sửa được thì đối tượng đó vẫn có thể thay đổi. Ở đây `Stats` giữ kiểu nguyên thủy và các đối tượng `OptionalInt`/`OptionalDouble` bất biến, nên không có mảng đầu vào nào được đặt vào bản ghi để bị chỉnh sửa qua kết quả.

## 8. Kiểm thử từng phương thức và trường hợp biên

Tách phương thức có ích nhất khi mỗi phương thức có **hợp đồng và ca kiểm tra** riêng:

| Phương thức | Ca kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| `sum` | `[8, -3, 0, 7, -2, 8]` | `18L` |
| `sum` | `[]` | `0L` |
| `sum` | `[Integer.MAX_VALUE, Integer.MAX_VALUE]` | `4294967294L` |
| `countPositive` | `[-1, 0, 4, 4]` | `2` |
| `countNegative` | `[-1, 0, 4, 4]` | `1` |
| `findMin` | `[-5, -1, -5]` | `OptionalInt.of(-5)` |
| `findMax` | `[-5, -1, -5]` | `OptionalInt.of(-1)` |
| `findMin` / `findMax` | `[]` | Cả hai rỗng |
| `average` | `(18L, 6)` | `OptionalDouble.of(3.0)` |
| `average` | `(0L, 0)` | `OptionalDouble.empty()` |

Các ca này là **kỳ vọng kiểm thử**, không phải thêm đoạn mã chạy độc lập. Có thể tự viết các lệnh `check(...)` hoặc dùng JUnit trong dự án có cấu hình thư viện kiểm thử.

Đặc biệt nên kiểm tra:

1. **Mảng rỗng** để tránh truy cập chỉ số 0 và chia cho 0.
2. **Chỉ số âm** và **chỉ số 0** để xác định điều kiện `> 0`, `< 0`, `== 0` rõ ràng.
3. **Mảng chỉ chứa số âm** để phát hiện cách khởi tạo max sai.
4. **Mảng nhiều phần tử bằng nhau** để kiểm tra cập nhật min/max.
5. **Tổng vượt phạm vi `int`** để xác nhận dùng `long`.
6. **`null`** để xác nhận hợp đồng đầu vào được thực thi nhất quán.
7. **Mảng một phần tử**: min và max phải đều là phần tử đó; average đúng bằng giá trị ấy.
8. **Không thay đổi đầu vào**: so sánh mảng trước và sau khi gọi `analyze` nếu cần kiểm chứng tính không tác dụng phụ.

Một phép kiểm thử không nên chỉ khẳng định `sum` đúng rồi cho rằng các hàm đếm hoặc tìm cực trị cũng chắc chắn đúng; mỗi trách nhiệm cần ít nhất một ca kiểm tra phù hợp.

## 9. Những lỗi thường gặp khi tách phương thức

### Lỗi 1: Tính trung bình bằng chia nguyên

```java
long sum = 14;
int count = 3;
double wrong = sum / count;         // 4.0: chia nguyên trước
double right = (double) sum / count; // khoảng 4.6667
```

Đây là đoạn minh họa bên trong một phương thức. Việc gán sang `double` **sau** khi chia nguyên không phục hồi phần lẻ đã mất. Dùng phép ép hoặc một toán hạng dạng số thực trước khi chia.

### Lỗi 2: Dùng `int` cho tổng có thể lớn

```java
int wrongSum = Integer.MAX_VALUE + Integer.MAX_VALUE;
// wrongSum == -2 do tràn int.
```

Biểu thức cộng hai giá trị `int` được tính bằng `int`, nên có thể tràn **trước khi gán**, kể cả nếu biến đích là `long`. Trong chương trình hoàn chỉnh, `total` được khai báo `long`, nên khi dùng `total += value`, phép cộng có ngữ cảnh phù hợp với kiểu `long`.

### Lỗi 3: Đếm luôn số 0 vào nhóm dương/âm

```java
if (value >= 0) {
    positive++;
}
```

Đoạn minh họa trên **sai** nếu yêu cầu “dương” nghĩa là `> 0`. Số `0` phải thuộc nhóm riêng. Một bất biến hữu ích để tự kiểm tra là `positive + negative + zero == length`.

### Lỗi 4: Hàm vừa tính vừa in vừa thay đổi dữ liệu

Ví dụ một `sum` mà vừa cộng, vừa sửa `values[i]`, vừa in kết quả sẽ khó tái sử dụng và khó test. Với bài này, helper tính toán **chỉ trả kết quả**. Tầng `printReport` chịu trách nhiệm xuất console; `main` chọn tình huống và kiểm tra.

### Lỗi 5: Dồn nhiều việc không liên quan vào một phương thức

Nếu `main` chứa tất cả các vòng lặp, định dạng số, xử lý mảng rỗng và kiểm thử, khi cần thay cách in bảng phải đọc lại cả thuật toán. Tách theo **trách nhiệm** tốt hơn tách chỉ để mỗi hàm có vài dòng.

### Lỗi 6: Tạo quá nhiều lượt duyệt mà không nhận ra đánh đổi

Thiết kế ở mục 5 dùng nhiều lượt duyệt: mỗi hàm như `sum`, `countPositive`, `countNegative`, `findMin`, `findMax` xử lý một phần mảng hoặc toàn mảng. Với một mảng độ dài `n`, tổng số phép duyệt vẫn tỷ lệ với `n` do số hàm là hằng số: **thời gian O(n)**, bộ nhớ bổ sung cho phần tính toán **O(1)**. Phần `Arrays.toString` tạo chuỗi để hiển thị nên có thêm chi phí bộ nhớ theo kích thước mảng.

Nếu ứng dụng cần hiệu năng hơn trên mảng cực lớn, có thể gom các phép cập nhật vào một vòng lặp duy nhất nhưng vẫn giữ phương thức `analyze` tách riêng khỏi `printReport` và `main`. Không nên tối ưu hóa quá sớm nếu đánh đổi làm bài học khó hiểu, nhưng cũng không nên hiểu “tách phương thức” đồng nghĩa với “bắt buộc duyệt dữ liệu nhiều lần”.

## 10. Bài tập mở rộng có định hướng

Sau khi chạy đúng chương trình:

1. Bổ sung `countEven(int[] values)` đếm số chẵn bằng `value % 2 == 0`, bao gồm `0` và số âm chẵn. Thêm trường tương ứng vào `Stats` và một ca kiểm thử.
2. Bổ sung tổng **chỉ các số dương** bằng helper độc lập `sumPositive`; đừng nhầm với tổng toàn bộ mảng hiện tại.
3. Viết thêm `findFirstIndexOfMax` trả chỉ số xuất hiện **đầu tiên** của giá trị lớn nhất; quy định hành vi cho mảng rỗng.
4. Thử phiên bản `analyze` chỉ duyệt mảng **một lần**, rồi so sánh kết quả với phiên bản nhiều helper trên cùng bộ test.
5. Viết một bộ kiểm thử gồm ít nhất mảng rỗng, một phần tử, toàn âm, toàn dương, lặp giá trị, số 0 và tổng vượt `int`.

Các yêu cầu mở rộng là bài luyện tập thêm, không làm thay đổi kết quả chạy chính của chương trình ở mục 5.

**Ghi nhớ:** Thống kê mảng không chỉ là viết vòng lặp, mà còn là xác định đúng nghĩa từng chỉ tiêu, xử lý trường hợp biên và chia trách nhiệm rõ ràng. Các phương thức nhỏ, không tác dụng phụ và có đầu ra xác định sẽ giúp Java code **dễ đọc, dễ gỡ lỗi, dễ kiểm thử và dễ tái sử dụng**.