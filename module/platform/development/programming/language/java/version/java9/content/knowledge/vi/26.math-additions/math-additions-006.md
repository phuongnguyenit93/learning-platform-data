# Phân biệt chia làm tròn xuống với chia cắt về không trong Java

## Mục tiêu

Phép chia số nguyên trong Java có một quy tắc quan trọng: kết quả được làm tròn về 0 (truncate toward zero). Quy tắc này khác với phép chia làm tròn xuống âm vô cực (floor division).

Với số dương, hai cách chia thường cho cùng kết quả. Với số âm, kết quả có thể khác nhau. Ví dụ:

- Java integer division: `-13 / 5 == -2`.
- Floor division: `Math.floorDiv(-13, 5) == -3`.

Nếu chương trình tính bucket thời gian, chia tọa độ, phân trang hoặc chỉ số vòng lặp có thể âm, chọn sai phép chia sẽ làm sai kết quả. Java cung cấp `Math.floorDiv` và `Math.floorMod` để biểu diễn rõ phép chia làm tròn xuống và phần dư tương ứng.

## 1. Chia số nguyên mặc định trong Java

Khi cả hai toán hạng của toán tử `/` là kiểu số nguyên (`byte`, `short`, `char`, `int`, `long` sau khi áp dụng binary numeric promotion), Java thực hiện phép chia số nguyên và bỏ phần thập phân bằng cách làm tròn về 0.

Ví dụ:

~~~java
System.out.println(13 / 5);
System.out.println(-13 / 5);
System.out.println(13 / -5);
System.out.println(-13 / -5);
~~~

Kết quả:

~~~text
2
-2
-2
2
~~~

Quy tắc có thể hiểu như sau:

- Phần thập phân bị loại bỏ.
- Kết quả tiến về 0, không tiến về âm vô cực.
- Nếu thương toán học là số nguyên thì không có phần thập phân để loại bỏ.

Vì vậy `-13 / 5` cho `-2`, bởi thương toán học là `-2.6` và giá trị nguyên gần 0 hơn là `-2`.

Đây là hành vi được định nghĩa của Java, không phụ thuộc vào hệ điều hành hay bộ xử lý.

## 2. Floor division là gì?

Floor division lấy số nguyên lớn nhất nhỏ hơn hoặc bằng thương toán học. Nói cách khác, kết quả được làm tròn về âm vô cực.

Trong Java, dùng:

~~~java
Math.floorDiv(int x, int y)
Math.floorDiv(long x, long y)
~~~

Các overload nhận `long` và `int` cũng có sẵn để xử lý toán hạng hỗn hợp mà không cần tự ép kiểu. `Math.floorDiv` và `Math.floorMod` là API hiện hành từ Java 8, vì vậy dùng được trong mã nguồn Java 9 và các phiên bản mới hơn.

Ví dụ:

~~~java
System.out.println(Math.floorDiv(13, 5));
System.out.println(Math.floorDiv(-13, 5));
System.out.println(Math.floorDiv(13, -5));
System.out.println(Math.floorDiv(-13, -5));
~~~

Kết quả:

~~~text
2
-3
-3
2
~~~

Điểm khác biệt thể hiện rõ khi thương toán học là số âm không nguyên:

- `-13 / 5` cắt về 0 thành `-2`.
- `Math.floorDiv(-13, 5)` làm tròn xuống thành `-3`.
- `13 / -5` cắt về 0 thành `-2`.
- `Math.floorDiv(13, -5)` làm tròn xuống thành `-3`.

Nếu thương đã là số nguyên, `/` và `floorDiv` cho cùng kết quả.

## 3. Bảng so sánh các dấu của toán hạng

Bảng dưới đây cho thấy sự khác nhau giữa phép chia số nguyên mặc định và floor division:

| x | y | `x / y` (về 0) | `Math.floorDiv(x, y)` |
|---:|---:|---:|---:|
| 13 | 5 | 2 | 2 |
| -13 | 5 | -2 | -3 |
| 13 | -5 | -2 | -3 |
| -13 | -5 | 2 | 2 |
| 15 | 5 | 3 | 3 |
| -15 | 5 | -3 | -3 |

Có thể ghi nhớ:

- Hai toán hạng cùng dấu: thương không âm; với ví dụ thông thường, hai cách cho cùng kết quả.
- Hai toán hạng trái dấu và phép chia có dư: phép chia mặc định cắt về 0, còn floor division đi xuống thêm một đơn vị.
- Chia hết: hai cách cho cùng kết quả.

Không nên chỉ kiểm thử với số dương. Các lỗi liên quan đến floor division thường chỉ xuất hiện khi tử số hoặc mẫu số âm.

## 4. Phần dư: toán tử % và Math.floorMod

Phép chia có phần dư đi kèm với quy tắc làm tròn của thương.

Toán tử `%` của Java trả về phần dư có dấu giống toán hạng bên trái (số bị chia), trừ trường hợp phần dư bằng 0.

`Math.floorMod(x, y)` trả về phần dư tương ứng với `Math.floorDiv(x, y)`. Phần dư khác 0 có dấu giống toán hạng bên phải (số chia).

Ví dụ:

~~~java
System.out.println(-13 % 5);
System.out.println(Math.floorMod(-13, 5));

System.out.println(13 % -5);
System.out.println(Math.floorMod(13, -5));
~~~

Kết quả:

~~~text
-3
2
3
-2
~~~

Bảng đầy đủ:

| x | y | `x % y` | `Math.floorMod(x, y)` |
|---:|---:|---:|---:|
| 13 | 5 | 3 | 3 |
| -13 | 5 | -3 | 2 |
| 13 | -5 | 3 | -2 |
| -13 | -5 | -3 | -3 |
| 15 | 5 | 0 | 0 |
| -15 | 5 | 0 | 0 |

Hai toán tử `%` và `floorMod` đều trả về 0 khi phép chia hết. Khi có phần dư, dấu của kết quả mới thể hiện khác biệt.

## 5. Mối quan hệ giữa thương và phần dư

Với phép chia nguyên không xảy ra trường hợp tràn thương, có thể biểu diễn:

~~~text
x = (x / y) * y + (x % y)
x = Math.floorDiv(x, y) * y + Math.floorMod(x, y)
~~~

Cả hai cặp thương/phần dư đều tái tạo lại số bị chia, nhưng quy tắc chọn thương khác nhau nên phần dư cũng khác nhau.

Ví dụ với `x = -13`, `y = 5`:

- Chia cắt về 0: `-13 = (-2) * 5 + (-3)`.
- Floor division: `-13 = (-3) * 5 + 2`.

Với `floorMod`, phần dư có dấu giống số chia và độ lớn nhỏ hơn độ lớn của số chia. Đây là đặc điểm hữu ích khi muốn chuẩn hóa chỉ số hoặc vị trí trong một chu kỳ.

Riêng trường hợp đặc biệt `Integer.MIN_VALUE / -1` hoặc `Long.MIN_VALUE / -1`, thương toán học không thể biểu diễn trong kiểu tương ứng. Java giữ hành vi tràn số của phép chia nguyên; không dùng trường hợp này để suy luận về thương toán học không giới hạn.

## 6. Ứng dụng thực tế của floorDiv và floorMod

### Chia thời gian thành các bucket

Khi chia timestamp thành các khoảng thời gian cố định, timestamp có thể âm nếu nằm trước mốc epoch. Muốn mỗi bucket đại diện cho một khoảng nửa mở đúng theo trục thời gian, dùng floor division.

Ví dụ chia giây thành bucket một phút:

~~~java
long epochSecond = -1L;
long minuteBucket = Math.floorDiv(epochSecond, 60L);

System.out.println(minuteBucket);
~~~

Kết quả:

~~~text
-1
~~~

Giây `-1` thuộc phút bucket `-1`, tức khoảng từ giây `-60` đến trước giây `0`. Nếu dùng `epochSecond / 60`, kết quả là 0 do cắt về 0, khiến thời điểm trước epoch bị xếp nhầm vào bucket bắt đầu tại epoch.

### Chỉ số vòng lặp hoặc vị trí tuần hoàn

Khi chuẩn hóa một chỉ số có thể âm vào phạm vi từ 0 đến `size - 1`, dùng `floorMod`:

~~~java
int size = 5;
int index = -1;

int normalized = Math.floorMod(index, size);
System.out.println(normalized);
~~~

Kết quả:

~~~text
4
~~~

Vị trí `-1` được ánh xạ về phần tử cuối cùng. Nếu dùng `index % size`, kết quả là `-1`, không phải chỉ số hợp lệ của mảng hoặc List.

Ví dụ lấy phần tử trong mảng theo chỉ số vòng:

~~~java
String[] days = {"Mon", "Tue", "Wed", "Thu", "Fri"};

int offset = -1;
String day = days[Math.floorMod(offset, days.length)];

System.out.println(day);
~~~

Kết quả:

~~~text
Fri
~~~

Chỉ dùng cách này nếu nghiệp vụ thực sự quy định chỉ số tuần hoàn. Với chỉ số ngoài phạm vi cần báo lỗi, hãy kiểm tra biên thay vì âm thầm chuẩn hóa.

## 7. Phân biệt Math.floor, floorDiv và phép chia số thực

Các API này giải quyết các kiểu dữ liệu và mục đích khác nhau:

- `Math.floor(double)` nhận số thực và trả về giá trị double lớn nhất không vượt quá đầu vào.
- `Math.floorDiv(int, int)` và các overload tương ứng thực hiện phép chia số nguyên theo hướng làm tròn xuống.
- Toán tử `/` với toán hạng số nguyên cắt thương về 0.
- Toán tử `/` với toán hạng floating-point thực hiện phép chia số thực, không tự cắt phần thập phân.

Ví dụ:

~~~java
System.out.println(-13 / 5);
System.out.println(Math.floor(-13.0 / 5.0));
System.out.println(Math.floorDiv(-13, 5));
~~~

Kết quả:

~~~text
-2
-3.0
-3
~~~

Dùng `Math.floorDiv` khi dữ liệu là số nguyên và cần thương nguyên theo floor. Không cần chuyển số nguyên sang double chỉ để gọi Math.floor; việc chuyển đổi có thể mất độ chính xác với các giá trị lớn.

Với `BigDecimal`, hãy chọn `RoundingMode.FLOOR` nếu cần làm tròn về âm vô cực hoặc `RoundingMode.DOWN` nếu cần cắt về 0. Quy tắc làm tròn phải được chọn rõ ràng theo yêu cầu nghiệp vụ và scale mong muốn.

## 8. Chia cho 0 và trường hợp tràn số

### Chia cho 0

Phép chia số nguyên cho 0 phát sinh `ArithmeticException`. Các phương thức `Math.floorDiv` và `Math.floorMod` cũng phát sinh ngoại lệ này khi số chia bằng 0.

~~~java
int quotient = Math.floorDiv(10, 0); // ArithmeticException
~~~

Nếu mẫu số đến từ dữ liệu bên ngoài, hãy kiểm tra hoặc xử lý ngoại lệ theo hợp đồng của phương thức.

### MIN_VALUE chia cho -1

Giá trị dương đối ứng của `Integer.MIN_VALUE` không thể biểu diễn bằng kiểu int. Vì vậy:

~~~java
System.out.println(Integer.MIN_VALUE / -1);
System.out.println(Math.floorDiv(Integer.MIN_VALUE, -1));
System.out.println(Integer.MIN_VALUE % -1);
~~~

Kết quả:

~~~text
-2147483648
-2147483648
0
~~~

Đây là tràn số được quy định cho phép chia số nguyên; phép chia không ném ArithmeticException trong trường hợp này. Cùng quy tắc áp dụng cho `Long.MIN_VALUE` chia cho `-1L`.

Nếu ứng dụng yêu cầu phát hiện mọi trường hợp tràn, cần tự kiểm tra trường hợp biên hoặc dùng kiểu biểu diễn đủ rộng/phù hợp. `Math.floorDiv` không phải phương thức kiểm tra tràn.

## 9. Ví dụ hoàn chỉnh có thể chạy

Tệp `FloorDivisionDemo.java`:

~~~java
public class FloorDivisionDemo {
    public static void main(String[] args) {
        int[][] cases = {
                {13, 5},
                {-13, 5},
                {13, -5},
                {-13, -5}
        };

        for (int[] values : cases) {
            int x = values[0];
            int y = values[1];

            System.out.println(
                    x + " / " + y
                    + " = " + (x / y)
                    + ", floorDiv = " + Math.floorDiv(x, y)
                    + ", % = " + (x % y)
                    + ", floorMod = " + Math.floorMod(x, y)
            );
        }

        long epochSecond = -1L;
        System.out.println("minute bucket: "
                + Math.floorDiv(epochSecond, 60L));

        int normalizedIndex = Math.floorMod(-1, 5);
        System.out.println("normalized index: " + normalizedIndex);

        System.out.println("MIN / -1: "
                + Math.floorDiv(Integer.MIN_VALUE, -1));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 -Xlint:all FloorDivisionDemo.java
java FloorDivisionDemo
~~~

Kết quả chuẩn:

~~~text
13 / 5 = 2, floorDiv = 2, % = 3, floorMod = 3
-13 / 5 = -2, floorDiv = -3, % = -3, floorMod = 2
13 / -5 = -2, floorDiv = -3, % = 3, floorMod = -2
-13 / -5 = 2, floorDiv = 2, % = -3, floorMod = -3
minute bucket: -1
normalized index: 4
MIN / -1: -2147483648
~~~

Ví dụ kiểm tra cả bốn tổ hợp dấu, cặp thương/phần dư, bucket thời gian âm, chỉ số vòng và trường hợp biên của int.

## 10. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng `/` khi cần bucket theo trục thời gian có giá trị âm | `/` cắt về 0, có thể xếp nhầm bucket âm | Dùng `Math.floorDiv` |
| Dùng `%` để chuẩn hóa chỉ số âm | Phần dư có thể âm | Dùng `Math.floorMod` nếu chỉ số thực sự tuần hoàn |
| Nghĩ `floorDiv` chỉ khác `/` khi tử số âm | Mẫu số âm cũng có thể tạo khác biệt khi phép chia có dư | Kiểm thử cả hai dấu của hai toán hạng |
| Dùng `Math.floor(x / y)` với số nguyên lớn | Ép sang double có thể mất độ chính xác | Dùng `Math.floorDiv` trên kiểu số nguyên phù hợp |
| Nghĩ chia MIN_VALUE cho -1 sẽ ném ngoại lệ | Trường hợp này tràn nhưng không ném ArithmeticException | Kiểm tra riêng nếu nghiệp vụ cần phát hiện tràn |
| Quên xử lý số chia bằng 0 | Chia số nguyên và floorDiv/floorMod đều ném ArithmeticException | Kiểm tra đầu vào hoặc xử lý ngoại lệ |
| Dùng floorMod cho chỉ số cần báo lỗi | Chuẩn hóa có thể che giấu dữ liệu ngoài phạm vi | Chỉ dùng khi quy tắc vòng lặp được yêu cầu |

## 11. Checklist lựa chọn

- Cần phép chia số nguyên theo quy tắc Java thông thường: dùng `/`.
- Cần thương làm tròn về âm vô cực: dùng `Math.floorDiv`.
- Cần phần dư tương ứng với floor division: dùng `Math.floorMod`.
- Cần phần dư giữ dấu của số bị chia: dùng `%`.
- Làm việc với timestamp âm hoặc bucket trước epoch: cân nhắc `floorDiv`.
- Chuẩn hóa chỉ số tuần hoàn có thể âm: cân nhắc `floorMod`.
- Kiểm tra mẫu số khác 0 và trường hợp MIN_VALUE chia cho -1.
- Không đổi sang double nếu phép tính cần độ chính xác nguyên.
- Với BigDecimal, chọn rõ RoundingMode theo quy tắc làm tròn cần thiết.

Phân biệt cắt thương về 0 với làm tròn xuống giúp các phép chia có số âm cho kết quả đúng với ý nghĩa toán học và nghiệp vụ. Khi cần floor division, hãy dùng `Math.floorDiv` cùng `Math.floorMod` để thương và phần dư tuân theo cùng một quy tắc.