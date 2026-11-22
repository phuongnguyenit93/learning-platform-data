# Math.getExponent và số mũ không thiên lệch

## 1. Số mũ nhị phân cho biết bậc độ lớn

Một số dấu phẩy động nhị phân chuẩn có thể được mô tả bằng dấu, phần định trị và lũy thừa của 2:

```text
x = dấu × m × 2^e
với 1 <= m < 2
```

Ví dụ:

```text
6.5  = 1.625 × 2^2
0.75 = 1.5   × 2^-1
8.0  = 1.0   × 2^3
```

`Math.getExponent` giúp lấy số mũ nhị phân trong biểu diễn `float` hoặc `double`, với quy tắc riêng cho số dưới chuẩn, zero, vô cực và NaN.

Phương thức có từ Java 6 và vẫn dùng được trên Java hiện đại. Nó hữu ích khi cần khảo sát bậc độ lớn nhị phân, chuẩn hóa dữ liệu số hoặc lựa chọn nhánh tính toán theo miền số. Nó không làm số dấu phẩy động trở thành số thập phân chính xác.

## 2. Hai overload, cùng trả về int

```java
public static int getExponent(float value)
public static int getExponent(double value)
```

Đây là chữ ký để đối chiếu, không phải chương trình độc lập.

Ví dụ với số chuẩn:

```java
Math.getExponent(6.5);    // 2, overload double
Math.getExponent(-6.5);   // 2
Math.getExponent(0.75);   // -1
Math.getExponent(8.0f);   // 3, overload float
```

Dấu của một số hữu hạn không làm đổi số mũ của độ lớn: `6.5` và `-6.5` có cùng kết quả `2`.

Số mũ âm không có nghĩa số đầu vào âm. Chẳng hạn `0.75` là số dương nhỏ hơn 1, nên ở dạng chuẩn hóa nhị phân nó có số mũ `-1`.

Kết quả là số nguyên nhị phân liên quan biểu diễn của **giá trị đang được lưu**, không phải số chữ số thập phân và không phải phần số mũ trong một chuỗi định dạng khoa học thập phân. Hợp đồng xem [Math.getExponent](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html#getExponent(double)).

## 3. “Không thiên lệch” nghĩa là gì?

Trường số mũ trong định dạng IEEE 754 không lưu trực tiếp một số nguyên âm/dương như `-1` hoặc `2`. Với số chuẩn, nó lưu một giá trị đã cộng **độ lệch (bias)**.

| Kiểu | Số bit trường mũ | Bias | Dải số mũ của số chuẩn hữu hạn |
| --- | --- | --- | --- |
| `float` | 8 | 127 | -126 đến 127 |
| `double` | 11 | 1023 | -1022 đến 1023 |

Với số chuẩn:

```text
e = E - bias
E: giá trị nguyên không dấu của trường mũ
e: số mũ sau khi bỏ độ lệch
```

Ví dụ với `double`:

- `6.5` có trường mũ `E = 1025`, nên `e = 1025 - 1023 = 2`.
- `0.75` có `E = 1022`, nên `e = -1`.
- `8.0` có `E = 1026`, nên `e = 3`.

Tên “không thiên lệch” ở đây nói về bỏ bias của biểu diễn số, không nói về sai số thống kê hay làm tròn không thiên lệch.

Với `double` chuẩn, nếu phần bit phân số được xem là số nguyên `F`, biểu thức giá trị là:

```text
(-1)^s × (1 + F / 2^52) × 2^(E - 1023)
```

Không cần tự tách bit cho mỗi lần dùng: `Math.getExponent` diễn đạt trực tiếp ý định và xử lý các loại giá trị theo hợp đồng.

## 4. Zero, số dưới chuẩn, NaN và vô cực

Không được dùng công thức của số chuẩn cho mọi mẫu bit. Các giá trị trường mũ ở hai đầu được dành cho những loại đặc biệt.

| Loại đầu vào | Kết quả với double | Kết quả với float |
| --- | --- | --- |
| Số chuẩn hữu hạn | -1022 đến 1023 | -126 đến 127 |
| `+0.0`, `-0.0` | -1023 | -127 |
| Số dưới chuẩn khác 0 | -1023 | -127 |
| NaN | 1024 | 128 |
| Vô cực dương/âm | 1024 | 128 |

Có thể ghi theo các hằng:

```text
zero hoặc subnormal -> MIN_EXPONENT - 1
NaN hoặc infinity   -> MAX_EXPONENT + 1
```

Các giá trị như `-1023` và `1024` là kết quả được API quy định; chúng không biến zero hay NaN thành số chuẩn có lũy thừa tương ứng.

Đặc biệt:

- `getExponent(x) == 1024` không phân biệt NaN với vô cực đối với `double`.
- `getExponent(x) == -1023` không phân biệt zero với số dưới chuẩn.
- Kết quả không giữ thông tin dấu của zero hoặc vô cực.

Muốn phân loại, kết hợp `Double.isFinite`, `Double.isNaN`, `Double.isInfinite` và phép kiểm tra zero theo câu hỏi cụ thể. Quy tắc biểu diễn và các loại giá trị theo [JLS về số dấu phẩy động](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.2.3).

## 5. Điểm quan trọng: số dưới chuẩn không trả số mũ chuẩn hóa thực sự

Một số dưới chuẩn (subnormal) cho phép biểu diễn các giá trị rất nhỏ bên dưới miền chuẩn, bằng cách không dùng bit `1` đầu ngầm định của phần định trị.

Ví dụ:

```text
Double.MIN_NORMAL = 2^-1022
Double.MIN_VALUE  = 2^-1074
```

Nhưng:

```java
Math.getExponent(Double.MIN_NORMAL);  // -1022
Math.getExponent(Double.MIN_VALUE);   // -1023, không phải -1074
```

Tất cả số dưới chuẩn `double` đều trả `-1023`, dù độ lớn của chúng khác nhau.

Trong biểu diễn số dưới chuẩn, giá trị có thể mô tả là:

```text
(-1)^s × (F / 2^52) × 2^-1022
```

Không có phần `1 +` như số chuẩn. Vì vậy, cách hiểu đơn giản “lấy trường mũ rồi có ngay dạng 1.x × 2^e” không còn đúng.

`Double.MIN_VALUE` là số dương khác zero nhỏ nhất, không phải số âm có giá trị nhỏ nhất. Tương tự, cần phân biệt `Float.MIN_VALUE` với `Float.MIN_NORMAL`. Xem [các hằng Double](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Double.html) và [các hằng Float](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Float.html).

## 6. Quan hệ với logarit cơ số 2

Với **số chuẩn hữu hạn khác zero**:

```text
2^e <= |x| < 2^(e+1)
e = floor(log2(|x|)) theo toán học
```

Ví dụ, `6.5` thuộc khoảng `[4, 8)` nên có số mũ `2`; `8.0` thuộc khoảng `[8, 16)` nên có số mũ `3`.

Điều này không có nghĩa nên thay `getExponent` bằng:

```java
(int) (Math.log(Math.abs(x)) / Math.log(2.0))
```

Đó là đoạn mã minh họa một cách suy luận không tương đương:

- Ép `double` sang `int` cắt về phía zero, khác `floor` đối với giá trị âm.
- Các phép logarit có làm tròn, có thể gây vấn đề khi phân loại sát ranh giới lũy thừa.
- Zero, số dưới chuẩn, NaN và vô cực có hợp đồng khác với `getExponent`.

Ngay cả khi bổ sung `Math.floor`, vẫn chưa biến cách tính logarit thành một phương thức tương đương trên toàn miền.

Nếu mục tiêu là đọc số mũ của biểu diễn, dùng API đúng mục tiêu. Nếu muốn số mũ chuẩn hóa theo độ lớn cho mọi số hữu hạn khác zero, phải xử lý riêng miền dưới chuẩn và nêu rõ hợp đồng của hàm tự viết.

## 7. Ví dụ Java 17+: các miền số và ranh giới

Tệp `ExponentDemo.java`:

```java
public final class ExponentDemo {
    public static void main(String[] args) {
        show("6.5", 6.5);
        show("-6.5", -6.5);
        show("0.75", 0.75);
        show("8.0", 8.0);
        show("nextDown(8.0)", Math.nextDown(8.0));
        show("MIN_NORMAL", Double.MIN_NORMAL);
        show("MIN_VALUE", Double.MIN_VALUE);
        show("+0.0", 0.0);
        show("-0.0", -0.0);
        show("MAX_VALUE", Double.MAX_VALUE);
        show("+Infinity", Double.POSITIVE_INFINITY);
        show("NaN", Double.NaN);

        System.out.println("float MIN_VALUE="
                + Math.getExponent(Float.MIN_VALUE));
        System.out.println("widened float MIN_VALUE="
                + Math.getExponent((double) Float.MIN_VALUE));
        System.out.println("normalized 6.5="
                + Math.scalb(6.5, -Math.getExponent(6.5)));
        System.out.println("magnitudeExponent(MIN_VALUE)="
                + magnitudeExponent(Double.MIN_VALUE));
    }

    private static void show(String label, double value) {
        System.out.println(label + " -> " + Math.getExponent(value));
    }

    private static int magnitudeExponent(double value) {
        if (!Double.isFinite(value) || value == 0.0) {
            throw new IllegalArgumentException("requires finite nonzero value");
        }
        int exponent = Math.getExponent(value);
        if (exponent == Double.MIN_EXPONENT - 1) {
            return Math.getExponent(Math.scalb(value, 52)) - 52;
        }
        return exponent;
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ExponentDemo.java
java ExponentDemo
```

Stdout:

```text
6.5 -> 2
-6.5 -> 2
0.75 -> -1
8.0 -> 3
nextDown(8.0) -> 2
MIN_NORMAL -> -1022
MIN_VALUE -> -1023
+0.0 -> -1023
-0.0 -> -1023
MAX_VALUE -> 1023
+Infinity -> 1024
NaN -> 1024
float MIN_VALUE=-127
widened float MIN_VALUE=-149
normalized 6.5=1.625
magnitudeExponent(MIN_VALUE)=-1074
```

`Math.nextDown(8.0)` tạo giá trị `double` biểu diễn được ngay bên dưới 8. Nó vẫn thuộc khoảng `[4, 8)`, nên kết quả là `2`, còn đúng `8.0` cho `3`.

Ví dụ chỉ in nhãn và kết quả liên quan để tập trung vào hợp đồng số mũ, không phụ thuộc định dạng toàn bộ chữ số thập phân của các giá trị cực nhỏ.

### Vì sao chuyển float sang double có thể đổi kết quả?

`Float.MIN_VALUE` có giá trị `2^-149`. Nó là số dưới chuẩn khi biểu diễn bằng `float`, nên overload `float` trả `-127`.

Khi chuyển chính xác sang `double`, giá trị số vẫn là `2^-149`, nhưng nó nằm trong miền chuẩn của `double`. Vì vậy overload `double` trả `-149`.

Đây là khác biệt do định dạng đầu vào của API, không phải chuyển kiểu làm thay đổi giá trị của `Float.MIN_VALUE` trong trường hợp này. Chú ý kiểu biến và hậu tố `f` của literal khi kiểm chứng overload.

## 8. Chuẩn hóa và hàm bổ sung trong ví dụ

Với số chuẩn như `6.5`, có thể dùng số mũ để đổi tỷ lệ theo lũy thừa 2:

```java
int exponent = Math.getExponent(6.5);
double significand = Math.scalb(6.5, -exponent);  // 1.625
```

`Math.scalb(x, n)` thực hiện đổi tỷ lệ theo `2^n` theo hợp đồng riêng. Trong trường hợp này kết quả nằm trong `[1, 2)`.

Không áp dụng đoạn chuẩn hóa đó một cách máy móc cho zero, NaN, vô cực hoặc số dưới chuẩn: kết quả `getExponent` của các miền này có ý nghĩa đặc biệt.

Hàm `magnitudeExponent` trong chương trình có hợp đồng **khác** `Math.getExponent`: nó trả số mũ `e` sao cho `2^e <= |x| < 2^(e+1)` với mọi `double` hữu hạn khác zero, kể cả số dưới chuẩn.

Cách xử lý miền dưới chuẩn:

1. Loại zero và giá trị không hữu hạn.
2. Với số dưới chuẩn, dùng `Math.scalb(value, 52)` để đưa giá trị vào miền chuẩn.
3. Lấy số mũ của giá trị đã đổi tỷ lệ rồi trừ `52`.

Vì số dưới chuẩn dương nhỏ nhất là `2^-1074`, nhân với `2^52` đưa nó tới `2^-1022`, là số chuẩn nhỏ nhất. Các số dưới chuẩn khác cũng đi vào miền chuẩn mà không cần tính trực tiếp một `double` bằng `2^1074`.

Đây là một ứng dụng có chủ đích, không phải “sửa lỗi” cho API: `Math.getExponent` đã trả đúng hợp đồng của nó. Khi đưa hàm bổ sung vào thư viện số học, cần giữ và kiểm thử hợp đồng riêng, gồm chính sách cho zero/NaN/vô cực.

## 9. Cách sử dụng và lỗi thường gặp

| Tình huống | Cách hiểu đúng |
| --- | --- |
| Cần bậc độ lớn của số chuẩn | Số mũ cho biết khoảng lũy thừa 2 chứa độ lớn |
| Hai số âm/dương có cùng độ lớn | Chúng có cùng kết quả getExponent |
| Cần số mũ theo cơ số 10 | getExponent không giải quyết trực tiếp câu hỏi này |
| Gặp kết quả MIN_EXPONENT - 1 | Phân loại zero hoặc subnormal trước khi chuẩn hóa |
| Gặp MAX_EXPONENT + 1 | Kiểm tra NaN/vô cực, không coi là số chuẩn lớn hơn |
| Cần phát hiện mọi mất độ chính xác | Số mũ không đủ; còn phụ thuộc định trị và các phép toán |
| Thấy kết quả khác sau chuyển kiểu | Kiểm tra giá trị có đổi miền chuẩn/dưới chuẩn và overload có đổi không |

Không dùng riêng `getExponent` để khẳng định hai số gần bằng nhau: rất nhiều giá trị có chung một số mũ. Cũng không dùng nó để chứng minh một phép tính sắp tới không tràn hoặc không hụt nếu chưa phân tích đầy đủ các toán hạng và thao tác.

## 10. Tự thực hành

1. Dự đoán kết quả cho `1.0`, `2.0`, `4.0` và các số nằm ngay dưới chúng bằng `Math.nextDown`.
2. So sánh `Double.MIN_NORMAL` với `Math.nextDown(Double.MIN_NORMAL)`; chỉ ra ranh giới chuẩn/dưới chuẩn.
3. Giải thích vì sao `Math.getExponent(0.0)` không thể được diễn giải như logarit toán học của zero.
4. Kiểm tra `Float.MIN_VALUE` trước và sau khi chuyển thành `double`; phân biệt giá trị số với dạng biểu diễn.
5. Nêu hợp đồng khác nhau giữa `Math.getExponent` và `magnitudeExponent` trong ví dụ.
