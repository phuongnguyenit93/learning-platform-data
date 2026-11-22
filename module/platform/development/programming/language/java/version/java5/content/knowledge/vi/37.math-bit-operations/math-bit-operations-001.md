# Math.log10 và căn bậc ba bằng Math.cbrt

## 1. Hai phép toán, hai ý nghĩa

`Math.log10(x)` trả logarit cơ số 10: trả lời câu hỏi “10 cần nâng lên số mũ bao nhiêu để được x?”. Ví dụ `10^3 = 1000`, nên `log10(1000) = 3`.

`Math.cbrt(x)` trả căn bậc ba thực: tìm một số `r` sao cho `r × r × r = x`. Ví dụ `3^3 = 27`, nên `cbrt(27) = 3`; `(-2)^3 = -8`, nên `cbrt(-8) = -2`.

Cả hai là phương thức `static` nhận `double` và trả `double`:

```java
double logarithm = Math.log10(1000.0);
double cubeRoot = Math.cbrt(27.0);
```

`Math` thuộc `java.lang`, nên không cần câu lệnh `import`. Hai API này có từ Java 5 và vẫn áp dụng trong Java hiện nay; ví dụ trong bài có thể biên dịch bằng Java 17 trở lên.

## 2. log10: đọc độ lớn theo bậc mười

Một số mốc toán học:

| x | log10(x) | Giải thích |
| ---: | ---: | --- |
| 0.01 | -2 | `10^-2 = 0.01` |
| 0.1 | -1 | `10^-1 = 0.1` |
| 1 | 0 | `10^0 = 1` |
| 10 | 1 | `10^1 = 10` |
| 1000 | 3 | `10^3 = 1000` |

Với đầu vào dương nhỏ hơn 1, kết quả logarit âm là hợp lệ. Điều bị loại khỏi miền logarit thực là **đầu vào âm**, không phải kết quả âm.

`log10` hữu ích khi phân tích đại lượng trải qua nhiều bậc độ lớn, tạo thang đo logarit hoặc so sánh mức chênh theo lũy thừa 10. Nó không trả về “số chữ số” một cách trực tiếp và không tự làm tròn về số nguyên.

`Math.log(x)` là logarit tự nhiên cơ số e; `Math.log10(x)` là cơ số 10. Công thức đổi cơ số `Math.log(x) / Math.log(10.0)` có ý nghĩa toán học, nhưng gồm nhiều phép tính dấu phẩy động và không được mặc định giống từng bit với `Math.log10(x)`. Khi cần cơ số 10, gọi đúng API diễn đạt ý định.

### Giá trị biên của log10

| Đầu vào | Kết quả |
| --- | --- |
| Dương hữu hạn | Một giá trị logarit hữu hạn |
| `1.0` | `+0.0` |
| `+0.0` hoặc `-0.0` | `Double.NEGATIVE_INFINITY` |
| Số âm, kể cả `Double.NEGATIVE_INFINITY` | `NaN` |
| `Double.POSITIVE_INFINITY` | `Double.POSITIVE_INFINITY` |
| `NaN` | `NaN` |

API trả các giá trị đặc biệt theo quy tắc dấu phẩy động, không ném ngoại lệ vì `log10(0)` hoặc `log10(-10)`. Nếu bài toán chỉ cho phép dữ liệu dương hữu hạn, hãy kiểm tra điều kiện đó trước:

```java
static double positiveFiniteLog10(double x) {
    if (!Double.isFinite(x) || x <= 0.0) {
        throw new IllegalArgumentException("x must be positive and finite");
    }
    return Math.log10(x);
}
```

Đây là phương thức minh họa để đặt trong một lớp. Chỉ kiểm tra `x <= 0` sẽ không loại được `NaN`, vì các phép so sánh thứ tự với `NaN` đều trả `false`.

## 3. cbrt: căn bậc ba thực của cả số âm

Khác căn bậc hai thực, căn bậc ba thực có nghĩa với mọi số thực hữu hạn. `Math.cbrt(-8.0)` trả `-2.0`; không cần tự tách dấu rồi ghép lại.

Một ứng dụng hình học là tìm cạnh của khối lập phương từ thể tích: `edge = Math.cbrt(volume)`. Hàm toán học nhận được số âm, nhưng thể tích vật lý của mô hình thông thường không âm; vì vậy vẫn phải kiểm tra điều kiện của miền ứng dụng.

| Đầu vào cbrt | Kết quả |
| --- | --- |
| Số dương hữu hạn | Căn bậc ba dương |
| Số âm hữu hạn | Căn bậc ba âm |
| `+0.0` | `+0.0` |
| `-0.0` | `-0.0`, giữ dấu |
| `+Infinity` hoặc `-Infinity` | Vô cực cùng dấu |
| `NaN` | `NaN` |

Không thay căn bậc ba bằng `Math.pow(x, 1 / 3)`: `1 / 3` là phép chia hai số nguyên và cho 0, nên ví dụ `Math.pow(27.0, 1 / 3)` trở thành `27^0 = 1`.

Đổi thành `1.0 / 3.0` mới tạo số mũ thực, nhưng vẫn không tương đương với `cbrt` trên toàn miền:

```java
Math.pow(-8.0, 1.0 / 3.0); // NaN
Math.cbrt(-8.0);           // -2.0
```

`pow` với cơ số âm và số mũ hữu hạn không nguyên cho `NaN`; một xấp xỉ `double` của một phần ba không được diễn giải như phân số chính xác để chọn căn thực âm. Hãy dùng `cbrt` khi ý định là lấy căn bậc ba.

## 4. Độ chính xác và cách kiểm chứng

Cả hai hàm tính bằng `double`, không phải số thực có vô hạn chữ số. Hợp đồng API yêu cầu kết quả nằm trong sai số 1 ulp của kết quả chính xác; ulp là đơn vị gắn với khoảng cách giữa các giá trị dấu phẩy động ở độ lớn đang xét, không phải một số chữ số thập phân cố định.

Không mặc định rằng với mọi x, `Math.cbrt(x) * Math.cbrt(x) * Math.cbrt(x) == x`. Bản thân phép nhân kiểm tra cũng được làm tròn và có thể tràn số khi x rất lớn.

Với một dữ liệu thử nhỏ như `x = 2`, có thể xem phần dư `|r^3 - x|` và dùng ngưỡng phù hợp. Ngưỡng `1e-12` trong chương trình bên dưới chỉ dành cho ví dụ đó, không phải ngưỡng đúng cho mọi miền giá trị. Một kiểm tra tổng quát cần xét độ lớn, sai số tuyệt đối/tương đối và các trường hợp vô cực, `NaN` riêng.

`Double.isNaN(result)` là cách kiểm tra `NaN`; biểu thức `result == Double.NaN` không dùng được. `Double.isFinite` hữu ích nếu quy trình chỉ chấp nhận kết quả hữu hạn.

Một số kết quả cuối có thể khác ở bit thấp giữa các triển khai `Math` mà vẫn tuân theo sai số được quy định. Nếu một hệ thống đòi tái lập kết quả theo hợp đồng chặt hơn, hãy xem `StrictMath` và yêu cầu cụ thể; không coi việc in ít chữ số là chứng minh kết quả bên trong giống nhau.

## 5. Chương trình chạy đầy đủ

Lưu thành `Log10CbrtDemo.java`.

```java
public class Log10CbrtDemo {
    public static void main(String[] args) {
        System.out.println("log10(1000) = " + Math.log10(1000.0));
        System.out.println("log10(0.01) = " + Math.log10(0.01));
        System.out.println("log10(1) = " + Math.log10(1.0));
        System.out.println("log10(0) = " + Math.log10(0.0));
        System.out.println("log10(-10) is NaN = "
                + Double.isNaN(Math.log10(-10.0)));
        System.out.println("log10(+infinity) = "
                + Math.log10(Double.POSITIVE_INFINITY));

        System.out.println("cbrt(27) = " + Math.cbrt(27.0));
        System.out.println("cbrt(-8) = " + Math.cbrt(-8.0));
        System.out.println("cbrt(-0.0) = " + Math.cbrt(-0.0));
        System.out.println("cbrt(-infinity) = "
                + Math.cbrt(Double.NEGATIVE_INFINITY));
        System.out.println("pow(-8, 1.0/3.0) is NaN = "
                + Double.isNaN(Math.pow(-8.0, 1.0 / 3.0)));
        System.out.println("1/3 with ints = " + (1 / 3));
        System.out.println("pow(27, 1/3) = " + Math.pow(27.0, 1 / 3));

        double root = Math.cbrt(2.0);
        double residual = Math.abs(root * root * root - 2.0);
        System.out.println("cbrt(2) residual below 1e-12 = "
                + (residual < 1e-12));

        long n = 999_999_999_999_999_999L;
        int estimated = (int) Math.floor(Math.log10(n)) + 1;
        int exact = Long.toString(n).length();
        System.out.println("digit estimate = " + estimated);
        System.out.println("exact digits = " + exact);
    }
}
```

Lệnh biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 Log10CbrtDemo.java
java Log10CbrtDemo
```

Stdout của ví dụ:

```text
log10(1000) = 3.0
log10(0.01) = -2.0
log10(1) = 0.0
log10(0) = -Infinity
log10(-10) is NaN = true
log10(+infinity) = Infinity
cbrt(27) = 3.0
cbrt(-8) = -2.0
cbrt(-0.0) = -0.0
cbrt(-infinity) = -Infinity
pow(-8, 1.0/3.0) is NaN = true
1/3 with ints = 0
pow(27, 1/3) = 1.0
cbrt(2) residual below 1e-12 = true
digit estimate = 19
exact digits = 18
```

Các dòng `digit` được đưa vào để minh họa một lỗi dùng logarit, không phải công thức đếm chữ số được khuyến nghị.

## 6. Vì sao không dùng log10 để đếm chính xác chữ số của long?

Trong toán học, với số nguyên dương n, `floor(log10(n)) + 1` cho số chữ số hệ 10. Nhưng trong Java, lời gọi `Math.log10(n)` chuyển `long` sang `double` trước; số nguyên lớn có thể mất thông tin.

Ví dụ số `999_999_999_999_999_999L` có 18 chữ số. Khi chuyển sang `double`, nó được làm tròn thành giá trị `1e18`; công thức dùng logarit cho 19.

Ngay cả khi đầu vào nhỏ hơn, làm tròn kết quả logarit gần ranh giới lũy thừa 10 cũng là điều phải xét nếu muốn đếm chính xác. Không sửa chung bằng cách cộng một epsilon tùy ý; epsilon có thể làm những đầu vào khác vượt ranh giới.

Nếu yêu cầu đếm chữ số của **long dương**, cách trực tiếp là:

```java
int digits = Long.toString(n).length();
```

Với số 0 hoặc số âm, cần định nghĩa có tính dấu âm không và xử lý theo hợp đồng. Nếu dùng thuật toán chia nguyên để đếm, cũng phải xử lý các trường hợp đó. Đặc biệt, tránh giả định `Math.abs(Long.MIN_VALUE)` là số dương biểu diễn được.

Tương tự, `Math.cbrt(n)` trả xấp xỉ `double`; không chỉ ép kiểu rồi kết luận một số nguyên lớn là lập phương hoàn hảo. Một kiểm tra nguyên chính xác cần xác minh ứng viên bằng phép toán tránh tràn số hoặc kiểu số nguyên lớn phù hợp.

## 7. Tự kiểm tra

1. `Math.log10(0.001)` có ý nghĩa gì về mặt toán học?
2. `Math.log10(-1.0)` ném ngoại lệ hay trả giá trị đặc biệt?
3. Để lấy căn bậc ba của `-125`, nên dùng lời gọi nào?
4. Vì sao `Math.pow(64, 1 / 3)` không cho 4?

Đáp án:

1. Tìm số mũ của 10 tạo ra `0.001`; giá trị toán học là -3.
2. Trả `NaN`.
3. `Math.cbrt(-125.0)`, có giá trị -5.
4. `1 / 3` tính bằng số nguyên thành 0, nên lời gọi tính `64^0`. Dùng `Math.cbrt(64.0)` diễn đạt đúng ý định.

Tham khảo hợp đồng API: [Math.log10](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html#log10(double)) và [Math.cbrt](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html#cbrt(double)) trong Java SE 21.
