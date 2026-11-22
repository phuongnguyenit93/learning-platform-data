# Math.nextUp và giới hạn sai số theo độ chính xác

## 1. Số dấu phẩy động là một tập rời rạc

Giữa hai số thực khác nhau luôn còn vô số số thực. Nhưng kiểu `float` và `double` chỉ biểu diễn được một tập hữu hạn các giá trị. Vì thế, tại một giá trị đã biểu diễn được, có thể hỏi: **giá trị biểu diễn được liền kề ở phía lớn hơn là gì?**

`Math.nextUp` trả lời câu hỏi đó. Nó không cộng một số thập phân nhỏ cố định, không thêm một chữ số chính xác và không sửa sai số đã tích lũy trong phép tính.

Hiểu các giá trị liền kề giúp kiểm tra ranh giới số học và hình dung giới hạn biểu diễn: một thay đổi quá nhỏ có thể bị làm tròn về chính giá trị cũ.

API có từ Java 6 và tiếp tục hữu ích trên Java hiện đại. Ví dụ trong bài dùng Java 17+.

## 2. Hợp đồng của nextUp

Hai overload:

```java
public static double nextUp(double value)
public static float nextUp(float value)
```

Đây là chữ ký để đối chiếu, không phải chương trình độc lập.

Với số hữu hạn, `nextUp` đi một bước trong tập giá trị biểu diễn được theo hướng **dương vô cực**. Ví dụ:

```java
Math.nextUp(1.0);   // double liền kề lớn hơn 1.0
Math.nextUp(1.0f);  // float liền kề lớn hơn 1.0f
Math.nextUp(-1.0);  // lớn hơn -1.0, tức gần zero hơn
```

“Up” nói về thứ tự số, không nói về trị tuyệt đối. Với số âm, kết quả thường có độ lớn nhỏ hơn.

Không cần tự tính một epsilon rồi cộng vào để tìm hàng xóm. Hợp đồng xem [Math.nextUp](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html#nextUp(double)).

## 3. Các giá trị đặc biệt

| Đầu vào double | Kết quả nextUp |
| --- | --- |
| `+0.0` hoặc `-0.0` | `Double.MIN_VALUE`, số dương khác zero nhỏ nhất |
| `-Double.MIN_VALUE` | `-0.0` |
| `Double.MAX_VALUE` | Dương vô cực |
| Dương vô cực | Vẫn dương vô cực |
| Âm vô cực | `-Double.MAX_VALUE` |
| NaN | NaN |

Với overload `float`, các trường hợp tương ứng dùng `Float.MIN_VALUE` và `Float.MAX_VALUE`.

Hai hệ quả:

- Không viết vòng lặp dựa trên giả định `nextUp(x)` luôn khác `x`: ở dương vô cực, nó không tiến nữa.
- Không dùng phép so sánh thông thường để khẳng định kết quả NaN “lớn hơn” đầu vào; NaN có quy tắc riêng.

Zero có dấu cần được nhận biết khi quan sát bit hoặc dạng hex, dù `+0.0 == -0.0` là `true`. Một số phép toán vẫn phân biệt hai giá trị này.

## 4. Khoảng cách phụ thuộc độ lớn và kiểu số

Trong miền số chuẩn dương của `double`, các giá trị trong khoảng `[2^e, 2^(e+1))` có khoảng cách `2^(e-52)` tới hàng xóm hữu hạn kế tiếp. Với `float`, công thức tương ứng là `2^(e-23)`.

Lý do: phần định trị của số chuẩn có 53 bit chính xác với `double` và 24 bit với `float`, tính cả bit đầu ngầm định.

| Vị trí | Khoảng cách phía trên |
| --- | --- |
| Gần `1.0` với double | `2^-52` |
| Gần `1.0f` với float | `2^-23` |
| Gần `2.0` với double | `2^-51` |
| Trong miền dưới chuẩn double | Bước cố định `2^-1074` |

Dải số lớn hơn không giữ được cùng khoảng cách tuyệt đối nhỏ như gần zero. Vì vậy, một hằng nhỏ có thể thay đổi được giá trị nhỏ nhưng không đủ để thay đổi một giá trị rất lớn sau làm tròn.

Công thức khoảng số chuẩn không được áp dụng mù quáng cho NaN, vô cực hoặc bước từ số hữu hạn lớn nhất sang vô cực. Các loại `float`/`double` và hành vi làm tròn được quy định trong [JLS về số dấu phẩy động](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.2.3).

## 5. ULP là thước đo cục bộ, không phải một epsilon chung

ULP là viết tắt của “unit in the last place”, một đơn vị theo độ phân giải của biểu diễn ở bậc độ lớn đang xét. `Math.ulp(x)` cung cấp kích thước ULP theo hợp đồng của phương thức.

Gần `1.0`:

```text
Math.ulp(1.0) = 2^-52
```

Nhưng không suy ra rằng:

```text
Math.nextUp(x) - x luôn bằng Math.ulp(x)
```

Tại ranh giới lũy thừa 2, bước ở hai phía có thể khác nhau:

```text
1.0 - nextDown(1.0) = 2^-53
nextUp(1.0) - 1.0   = 2^-52
```

Với `x = -1.0`, hướng tăng đi về zero nên:

```text
nextUp(-1.0) - (-1.0) = 2^-53
Math.ulp(-1.0)         = 2^-52
```

`Math.ulp` có cùng kết quả cho `x` và `-x`; nó không phải phép đo mọi khoảng cách có hướng quanh `x`. Nếu cần đúng khoảng cách phía trên/phía dưới, tính từ hàng xóm phù hợp và xử lý các giá trị đặc biệt.

Thuật ngữ “machine epsilon” thường dùng cho khoảng cách từ 1 tới số lớn hơn kế tiếp, tức `2^-52` ở `double`. Trong phân tích sai số, “unit roundoff” với làm tròn gần nhất thường là `2^-53`. Cần nêu định nghĩa đang dùng thay vì dùng từ epsilon cho mọi ngưỡng.

Xem [Math.ulp](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html#ulp(double)).

## 6. Từ bước biểu diễn tới sai số: điều gì được bảo đảm?

Giả sử một giá trị thực nằm giữa hai giá trị dấu phẩy động hữu hạn liền kề. Nếu một bước tính được **làm tròn đúng về giá trị gần nhất**, sai số của riêng bước làm tròn đó không vượt quá nửa khoảng cách giữa hai giá trị kẹp nó; trường hợp ở chính giữa cần quy tắc xử lý hòa.

Điều này không có nghĩa:

- Mọi kết quả của mọi phương thức `Math` đều có cùng giới hạn 0,5 ULP.
- Tổng sai số của một chuỗi phép tính vẫn luôn dưới 0,5 ULP.
- Dữ liệu đầu vào đã chính xác về mặt toán học.
- Tăng kết quả bằng một lần `nextUp` làm nó đúng hơn.

Hợp đồng độ chính xác của từng hàm phải được đọc riêng. Một số hàm toán học cho phép giới hạn lớn hơn một bước làm tròn đúng; phân tích toàn thuật toán còn phải xét truyền sai số, mất chữ số khi trừ các số gần nhau và điều kiện của bài toán.

Ví dụ, một kết quả có thể đang cao hơn giá trị thực; gọi `nextUp` chỉ làm nó cao thêm. Hàng xóm biểu diễn được là thông tin về lưới số, không phải thông tin về hướng sai số của phép tính trước.

### Một thay đổi nhỏ có thể không làm giá trị tăng

Ở `1.0`, nửa bước phía trên là `2^-53`. Theo làm tròn gần nhất, hòa về chữ số chẵn:

```java
double halfStep = Math.ulp(1.0) / 2.0;
boolean unchanged = (1.0 + halfStep == 1.0);  // true
```

Đây là đoạn minh họa ở trong một phương thức. `nextUp(1.0)` thì trả đúng hàng xóm phía trên, thay vì tạo một giá trị ở giữa rồi bị làm tròn lại.

## 7. Ví dụ Java 17+: quan sát bằng dạng hex

Tệp `NextUpDemo.java`:

```java
public final class NextUpDemo {
    public static void main(String[] args) {
        show("nextUp(1.0)", Math.nextUp(1.0));
        show("nextUp(-1.0)", Math.nextUp(-1.0));
        show("nextUp(+0.0)", Math.nextUp(0.0));
        show("nextUp(-0.0)", Math.nextUp(-0.0));
        show("nextUp(-MIN_VALUE)", Math.nextUp(-Double.MIN_VALUE));
        show("nextUp(MAX_VALUE)", Math.nextUp(Double.MAX_VALUE));
        show("nextUp(+Infinity)", Math.nextUp(Double.POSITIVE_INFINITY));
        show("nextUp(-Infinity)", Math.nextUp(Double.NEGATIVE_INFINITY));
        show("nextUp(NaN)", Math.nextUp(Double.NaN));

        show("gap above 1.0", Math.nextUp(1.0) - 1.0);
        show("gap below 1.0", 1.0 - Math.nextDown(1.0));
        show("ulp(1.0)", Math.ulp(1.0));
        show("gap above -1.0", Math.nextUp(-1.0) + 1.0);
        show("ulp(-1.0)", Math.ulp(-1.0));
        show("float gap above 1.0",
                (double) (Math.nextUp(1.0f) - 1.0f));

        double halfStep = Math.ulp(1.0) / 2.0;
        System.out.println("1.0 + halfStep == 1.0: "
                + (1.0 + halfStep == 1.0));
        System.out.println("nextUp(1.0) > 1.0: " + (Math.nextUp(1.0) > 1.0));
    }

    private static void show(String label, double value) {
        System.out.println(label + " = " + Double.toHexString(value));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 NextUpDemo.java
java NextUpDemo
```

Stdout:

```text
nextUp(1.0) = 0x1.0000000000001p0
nextUp(-1.0) = -0x1.fffffffffffffp-1
nextUp(+0.0) = 0x0.0000000000001p-1022
nextUp(-0.0) = 0x0.0000000000001p-1022
nextUp(-MIN_VALUE) = -0x0.0p0
nextUp(MAX_VALUE) = Infinity
nextUp(+Infinity) = Infinity
nextUp(-Infinity) = -0x1.fffffffffffffp1023
nextUp(NaN) = NaN
gap above 1.0 = 0x1.0p-52
gap below 1.0 = 0x1.0p-53
ulp(1.0) = 0x1.0p-52
gap above -1.0 = 0x1.0p-53
ulp(-1.0) = 0x1.0p-52
float gap above 1.0 = 0x1.0p-23
1.0 + halfStep == 1.0: true
nextUp(1.0) > 1.0: true
```

Dạng hex dùng `p` cho số mũ cơ số 2: `0x1.0p-52` là `1 × 2^-52`. Nó giúp nhìn bước nhị phân rõ hơn chuỗi thập phân dài.

Các dòng zero, NaN và vô cực cho thấy cần tách riêng những miền đó. Dòng `float gap` dùng `1.0f` để chọn overload `float`; chuyển kết quả khoảng cách sang `double` sau phép trừ chỉ để dùng cùng hàm in, không thay phép tính thành độ chính xác `double`.

## 8. Ứng dụng phù hợp

### Kiểm thử ranh giới

Nếu một hàm có nhánh `x <= threshold`, hãy thử:

```java
double below = Math.nextDown(threshold);
double at = threshold;
double above = Math.nextUp(threshold);
```

Đoạn mã giả định `threshold` là một `double` hữu hạn trong miền ứng dụng. Ba giá trị giúp thử đúng ngưỡng và hai hàng xóm gần nhất, thay vì chọn tùy ý `threshold ± 0.000001`.

Điều này chỉ kiểm tra lưới biểu diễn quanh ngưỡng. Nếu yêu cầu nghiệp vụ có sai số đo lường hoặc quy tắc làm tròn thập phân riêng, cần thêm các ca theo yêu cầu đó.

### Tìm đầu mút biểu diễn được

Với một ngưỡng hữu hạn `a`, `nextUp(a)` là ứng viên nhỏ nhất trong định dạng đó có giá trị lớn hơn `a`. Nó hữu ích khi thuật toán cần đầu mút mở/đóng theo tập số biểu diễn được.

Tuy nhiên, nếu `a` là số hữu hạn lớn nhất thì đầu mút kế tiếp là vô cực. Và `nextUp(f(x))` không tự là một cận trên đúng cho giá trị thực của một biểu thức bất kỳ nếu chưa có phân tích sai số đủ chặt.

### Quan sát độ phân giải

So sánh bước gần `1.0`, `2.0` và một số lớn giúp hiểu vì sao cộng một gia số nhỏ có thể không còn tác dụng. Đây là công cụ để kiểm chứng giả thuyết số học, không phải thay thế bằng chứng về độ chính xác của cả thuật toán.

## 9. Chọn ngưỡng so sánh theo vấn đề

Một ngưỡng tuyệt đối cố định có thể phù hợp với sai số có đơn vị đo rõ ràng. Một ngưỡng tương đối có thể phù hợp khi độ lớn biến đổi rộng. Một giới hạn ULP có thể hữu ích khi kiểm thử một thuật toán số đã có hợp đồng theo ULP.

Không có một ngưỡng đúng chung cho mọi phép so sánh `double`. Cần xác định:

- Đầu vào có thể chứa NaN/vô cực không?
- Giá trị gần zero có cần ngưỡng tuyệt đối không?
- Sai số cho phép đến từ đo lường, làm tròn hay phân tích thuật toán?
- Kết quả dùng cho nhánh nghiệp vụ, kiểm thử thư viện hay quan hệ thứ tự?
- Loại `float` hay `double` thực sự được sử dụng?

Không thay mọi phép `==` bằng “chênh dưới một ULP” chỉ vì đã biết `nextUp`. Chẳng hạn hai giá trị đo khác nhau về nghiệp vụ có thể nằm gần nhau trên lưới, còn một bất biến đại số trong thuật toán lại cần kiểm chứng khác.

## 10. Lỗi thường gặp và bài tập

| Lỗi suy luận | Sửa bằng |
| --- | --- |
| nextUp làm trị tuyệt đối tăng | Nhớ hướng là dương vô cực, gồm cả miền âm |
| Một epsilon cố định luôn tới đúng hàng xóm | Dùng nextUp/nextDown cho hàng xóm; bước thay đổi theo miền số |
| nextUp(x) - x luôn bằng ulp(x) | Xem bước có hướng, dấu và ranh giới lũy thừa 2 |
| Một ULP luôn là mức sai số chấp nhận được | Đọc hợp đồng và yêu cầu của phép tính |
| Cộng nửa ULP chắc chắn làm x tăng | Xét làm tròn và quy tắc hòa |
| Duyệt nextUp luôn kết thúc hữu hạn theo điều kiện tự đặt | Tính đến NaN, vô cực và miền giá trị được phép |

Tự thực hành:

1. Thay `1.0` bằng `2.0`; dự đoán bước phía trên và phía dưới rồi chạy kiểm chứng.
2. So sánh `Math.nextUp(1.0f)` với `Math.nextUp((double) 1.0f)`; giải thích vì sao hai overload cho hàng xóm khác nhau.
3. Thử hai giá trị kề ranh giới `Double.MIN_NORMAL`; đối chiếu bước ở miền chuẩn thấp nhất với miền dưới chuẩn.
4. Nêu vì sao gọi `nextUp` sau một hàm toán học không tự bảo đảm tạo cận trên đúng cho giá trị toán học.
5. Thiết kế ba ca thử cho một nhánh so sánh ngưỡng bằng `nextDown`, giá trị ngưỡng và `nextUp`.
