# Mẫu tích lũy tổng, đếm và tìm giá trị lớn nhất trong Java

> **Java core — language-basics / Vòng lặp**  
> **Môi trường:** JDK 17+, chương trình một file, không dùng thư viện bên ngoài.  
> **Mục tiêu:** Dùng một vòng lặp để tính tổng, đếm phần tử/đếm theo điều kiện và tìm giá trị lớn nhất; chọn giá trị khởi tạo chính xác, xử lý mảng rỗng và tránh tràn tổng kiểu `int`.

## 1. Mẫu tích lũy (*accumulator*) là gì?

Khi duyệt một dãy số, ta có thể giữ các biến **trạng thái tóm tắt**. Mỗi lượt xử lý một phần tử và cập nhật trạng thái:

~~~java
int[] numbers = {3, -2, 7, 0, -5};
long sum = 0;
int count = 0;

for (int number : numbers) {
    sum += number;
    count++;
}

System.out.println(sum);   // 3
System.out.println(count); // 5
~~~

- **Tổng**: khởi tạo `sum = 0`, cập nhật bằng `sum += number`.
- **Đếm**: khởi tạo `count = 0`, tăng đúng một lần cho mỗi phần tử được tính.
- **Giá trị lớn nhất**: sau khi gặp phần tử đầu tiên, giữ `max` bằng phần tử lớn nhất đã thấy; mỗi lượt so sánh rồi cập nhật nếu cần.

Cả ba phép tính có thể được thực hiện trong **cùng một lần duyệt**, không nhất thiết tạo ba vòng lặp. Với `n` phần tử, thời gian là **O(n)** và bộ nhớ phụ cho các bộ tích lũy là **O(1)**.

## 2. Khởi tạo và cập nhật: tổng, đếm, đếm có điều kiện

Tổng của dãy rỗng được định nghĩa là `0`. Đếm phần tử của dãy rỗng cũng là `0`. Ta có thể đếm thêm các phần tử thỏa điều kiện:

~~~java
int[] numbers = {3, -2, 7, 0, -5};
long sum = 0;
int count = 0;
int positiveCount = 0;

for (int number : numbers) {
    sum += number;
    count++;

    if (number > 0) {
        positiveCount++;
    }
}
// sum = 3; count = 5; positiveCount = 2.
~~~

Ở đây `0` **không** được tính là số dương vì điều kiện là `number > 0`. Nếu yêu cầu đếm số không âm, thay bằng `number >= 0` và cập nhật cả bảng test.

Không nhầm `count` (tổng số phần tử) với `positiveCount` (số phần tử thỏa điều kiện). Nếu chỉ cộng số dương, điều kiện lọc phải bao quanh **cả phép cộng lẫn phép đếm cùng miền**, thay vì dùng tổng tất cả chia cho số lượng số dương.

## 3. Tìm `max` đúng cả khi toàn số âm hoặc mảng rỗng

Một lỗi phổ biến là khởi tạo `max = 0` rồi chỉ cập nhật nếu phần tử lớn hơn:

~~~java
// SAI với dãy {-8, -3, -12}:
// int max = 0;
// for (int x : numbers) {
//     if (x > max) max = x;
// }
// Kết quả sai là 0; lớn nhất thực sự là -3.
~~~

Có hai cách an toàn:

1. Nếu biết mảng **không rỗng**, đặt `max = numbers[0]` và bắt đầu duyệt từ phần tử thứ hai.
2. Nếu mảng **có thể rỗng**, dùng cờ `hasAny` để ghi nhận đã thấy phần tử nào, rồi xuất kết quả tùy chọn (`OptionalInt`).

~~~java
int max = 0;
boolean hasAny = false;

for (int number : numbers) {
    if (!hasAny || number > max) {
        max = number;
        hasAny = true;
    }
}

java.util.OptionalInt maximum =
        hasAny ? java.util.OptionalInt.of(max)
               : java.util.OptionalInt.empty();
~~~

Trong cách thứ hai, giá trị ban đầu `max = 0` **không được coi là kết quả** khi chưa gặp phần tử: lượt đầu sẽ gán `max = number` bất kể âm hay dương. Với mảng rỗng, `maximum.isPresent()` là false. Không tự kết luận max của mảng rỗng bằng 0 vì 0 không phải phần tử của mảng.

## 4. Bảng diễn tiến và bất biến vòng lặp

Với dãy `{3, -2, 7, 0, -5}`, sau mỗi lượt, trạng thái biến đổi như sau:

| Phần tử vừa xử lý | `sum` | `count` | `positiveCount` | `max` |
| ---: | ---: | ---: | ---: | ---: |
| Chưa xử lý | 0 | 0 | 0 | Chưa có |
| 3 | 3 | 1 | 1 | 3 |
| -2 | 1 | 2 | 1 | 3 |
| 7 | 8 | 3 | 2 | 7 |
| 0 | 8 | 4 | 2 | 7 |
| -5 | 3 | 5 | 2 | 7 |

**Bất biến vòng lặp** sau `k` phần tử là: `sum` bằng tổng `k` phần tử đầu; `count = k`; `positiveCount` bằng số phần tử dương trong `k` phần tử; nếu `k > 0` thì `max` bằng phần tử lớn nhất trong đoạn đã duyệt.

Lập luận: trạng thái ban đầu đúng với `k = 0`; mỗi lượt cập nhật tổng, các bộ đếm và max theo phần tử mới nên vẫn đúng với `k + 1`. Khi duyệt hết `n` phần tử, các biến mô tả chính xác toàn bộ dãy.

Việc viết bất biến giúp phát hiện lỗi đặt `count++` sai chỗ, bỏ qua phần tử đầu, hoặc cập nhật `max` bằng điều kiện ngược `number < max`.

## 5. Trung bình, kiểu dữ liệu và tràn số

Sau khi có tổng và số lượng, có thể tính trung bình:

~~~java
double average = count == 0
        ? Double.NaN
        : (double) sum / count;
~~~

Phải kiểm tra `count == 0` vì trung bình của dãy rỗng **không xác định**. Trong ví dụ runnable bên dưới, ta in `"N/A"` thay cho trung bình rỗng. Ép kiểu `(double) sum` **trước phép chia** để tránh phép chia nguyên làm mất phần thập phân.

**Dùng `long` cho tổng số nguyên `int`:**

~~~java
int large = Integer.MAX_VALUE;
int wrong = large + large;       // Tràn int: -2.
long correct = (long) large + large; // 4_294_967_294.
~~~

Nếu dùng `long sum = 0; sum += number;` với từng `int` thì phép cộng được thực hiện dưới kiểu `long`, tránh tràn `int` trước khi cộng. Nhưng `long` **không bảo đảm vô hạn**: nếu cộng rất nhiều số trong luồng dữ liệu lớn, vẫn có thể tràn `long`; khi cần phát hiện tràn có thể dùng `Math.addExact` hoặc `BigInteger` tùy bài toán.

Khi mảng chứa số âm, trung bình vẫn có thể âm. Không lấy số lượng số dương làm mẫu số nếu tổng đang tính trên **toàn bộ** phần tử.

## 6. Chọn vòng lặp và kiểm tra trường hợp biên

| Trường hợp | Kết quả cần kiểm tra |
| --- | --- |
| Mảng rỗng `{}` | Tổng 0, đếm 0, không có max, trung bình `N/A` |
| Chỉ số âm `{-8, -3, -12}` | Max `-3`, không phải 0 |
| Có số 0 | 0 được đếm là phần tử, nhưng không phải số dương |
| Một phần tử | Tổng và max bằng chính phần tử; đếm 1 |
| Hai `Integer.MAX_VALUE` | Tổng `4_294_967_294` bằng `long` |
| Mảng null | Không thể duyệt bằng for-each; phải kiểm tra null theo hợp đồng |

Dùng `for (int x : numbers)` khi chỉ cần **giá trị** mỗi phần tử. Dùng `for (int i = 0; i < numbers.length; i++)` nếu cần chỉ số hoặc bắt đầu từ vị trí 1 sau khi gán max bằng phần tử đầu.

Với đầu vào null, có thể chủ động báo lỗi bằng `IllegalArgumentException` thay vì để vòng lặp gây `NullPointerException` không rõ mục đích; ví dụ runnable lựa chọn báo lỗi tường minh.

## 7. Chương trình Java 17+ chạy độc lập

Tạo file **LoopAccumulatorDemo.java**:

~~~java
import java.util.Locale;
import java.util.OptionalInt;

public final class LoopAccumulatorDemo {
    private record Summary(
            long sum, int count, int positiveCount, OptionalInt max) {}

    private static Summary analyze(int[] values) {
        if (values == null) {
            throw new IllegalArgumentException("values must not be null");
        }

        long sum = 0L;
        int count = 0;
        int positiveCount = 0;
        int max = 0;
        boolean hasAny = false;

        for (int number : values) {
            sum += number;
            count++;

            if (number > 0) {
                positiveCount++;
            }
            if (!hasAny || number > max) {
                max = number;
                hasAny = true;
            }
        }

        return new Summary(sum, count, positiveCount,
                hasAny ? OptionalInt.of(max) : OptionalInt.empty());
    }

    private static void show(String label, int[] values) {
        Summary result = analyze(values);

        String maxText = result.max().isPresent()
                ? String.valueOf(result.max().getAsInt()) : "NONE";
        String averageText = result.count() == 0
                ? "N/A"
                : String.format(Locale.ROOT, "%.2f",
                        (double) result.sum() / result.count());

        System.out.println(label
                + ":sum=" + result.sum()
                + ",count=" + result.count()
                + ",positive=" + result.positiveCount()
                + ",max=" + maxText
                + ",average=" + averageText);
    }

    public static void main(String[] args) {
        show("mixed", new int[] {3, -2, 7, 0, -5});
        show("negative", new int[] {-8, -3, -12});
        show("empty", new int[] {});
        show("zeros", new int[] {0, 0});
        show("min", new int[] {Integer.MIN_VALUE});
        show("large", new int[] {
                Integer.MAX_VALUE, Integer.MAX_VALUE
        });

        try {
            analyze(null);
        } catch (IllegalArgumentException ex) {
            System.out.println("nullInput=IllegalArgumentException");
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 LoopAccumulatorDemo.java
java LoopAccumulatorDemo
~~~

**Expected stdout chính xác:**

~~~text
mixed:sum=3,count=5,positive=2,max=7,average=0.60
negative:sum=-23,count=3,positive=0,max=-3,average=-7.67
empty:sum=0,count=0,positive=0,max=NONE,average=N/A
zeros:sum=0,count=2,positive=0,max=0,average=0.00
min:sum=-2147483648,count=1,positive=0,max=-2147483648,average=-2147483648.00
large:sum=4294967294,count=2,positive=2,max=2147483647,average=2147483647.00
nullInput=IllegalArgumentException
~~~

Bốn kết quả quan trọng: `negative` phát hiện khởi tạo max sai; `empty` minh họa không có giá trị lớn nhất; `large` chứng minh tổng vượt miền `int` vẫn được giữ trong `long`; và `mixed` thể hiện tổng, các bộ đếm và max được tính từ **cùng một lượt duyệt**.

## 8. Lỗi thường gặp và bài tập

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Khởi tạo `max = 0` rồi dùng luôn làm giá trị lớn nhất | Sai với toàn số âm hoặc mảng rỗng | Khởi tạo từ phần tử đầu hợp lệ hoặc dùng `hasAny` |
| Dùng `int sum` cho tổng lớn | Có thể tràn số | Dùng `long` và tránh tràn trước khi ép kiểu |
| `count++` chỉ chạy khi số dương | Đếm sai tổng phần tử | Tách `count` và `positiveCount` |
| Tính trung bình `sum / count` bằng số nguyên | Mất phần lẻ, sai với dãy rỗng | Kiểm tra count, ép kiểu trước phép chia |
| Truy cập `numbers[0]` khi mảng rỗng | `ArrayIndexOutOfBoundsException` | Kiểm tra rỗng hoặc dùng cờ lần đầu |
| Nhầm `> 0` với `>= 0` | Đếm khác ở phần tử 0 | Bám đúng định nghĩa số dương/không âm |

**Bài 1.** Tự tính `sum`, `count`, `positiveCount`, `max` cho dãy `{4, -1, 0, 10}`, sau đó kiểm chứng bằng chương trình.

**Bài 2.** Thay điều kiện đếm số dương thành đếm số chẵn; chú ý cách xử lý số âm chẵn và số 0.

**Bài 3.** Sửa mẫu để chỉ lấy tổng và max của **các phần tử dương**. Nếu không có số dương thì trả kết quả gì để không nhầm với max=0?

**Bài 4.** Viết biến thể sử dụng `for (int i = 1; i < values.length; i++)` với `max = values[0]`, đồng thời xử lý đầu vào rỗng trước.

**Bài 5.** Dùng dãy `{Integer.MAX_VALUE, Integer.MAX_VALUE}` để so sánh tổng lưu vào `int` và `long`; giải thích tại sao chỉ ép kiểu **sau khi** đã cộng theo `int` là quá muộn.

### Ghi nhớ

**Tích lũy tổng bắt đầu từ 0, đếm bắt đầu từ 0, còn max cần phần tử đầu tiên thực sự tồn tại.** Mỗi lượt duyệt cập nhật đúng các bộ tích lũy và giữ bất biến. Với mảng rỗng, không có max; với toàn số âm, max vẫn âm. Sử dụng `long` cho tổng `int` có thể lớn và kiểm tra `count == 0` trước khi tính trung bình.
