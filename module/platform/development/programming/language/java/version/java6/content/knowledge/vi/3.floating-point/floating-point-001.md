# Math.copySign và bảo toàn dấu của giá trị

`Math.copySign(magnitude, sign)` tạo một số thực lấy **độ lớn từ đối số thứ nhất** và **dấu từ đối số thứ hai**. Nó hữu ích khi một phép tính tạo ra độ lớn mới nhưng thuật toán cần giữ dấu của một giá trị khác, kể cả dấu âm của `-0.0`.

Hai overload `double` và `float` có từ Java 6 và vẫn được dùng trong JDK hiện hành. Bài thực hành trên JDK hiện đại, tập trung vào hợp đồng của thao tác thay dấu.

## 1. Hiểu đúng vai trò hai đối số

Chữ ký:

```java
public static double copySign(double magnitude, double sign)
public static float copySign(float magnitude, float sign)
```

Cách đọc:

```text
độ lớn của magnitude + dấu của sign -> kết quả mới
```

Ví dụ:

| Lời gọi | Kết quả | Giải thích |
| --- | --- | --- |
| `Math.copySign(3.5, -2.0)` | `-3.5` | Lấy độ lớn 3.5 và dấu âm |
| `Math.copySign(-3.5, 2.0)` | `3.5` | Dấu ban đầu của đối số thứ nhất bị thay |
| `Math.copySign(3.5, -0.0)` | `-3.5` | Dấu âm của số không vẫn có ý nghĩa |
| `Math.copySign(0.0, -1.0)` | `-0.0` | Độ lớn không đổi, dấu âm được giữ |

Tên tham số `sign` không có nghĩa đối số thứ hai phải bằng `1` hoặc `-1`. Độ lớn của nó không được dùng để nhân vào kết quả.

Phương thức trả một giá trị mới; nó không sửa biến đã được truyền vào. Xem [Math.copySign(double,double)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html#copySign(double,double)).

## 2. Vì sao signed zero cần được nhắc đến?

Số thực Java có hai số không: `+0.0` và `-0.0`. Chúng bằng nhau khi so sánh số học bằng `==`, và `-0.0 < 0.0` là `false`. Nhưng dấu vẫn được giữ trong biểu diễn và có thể ảnh hưởng phép tính sau đó.

Ví dụ:

```java
1.0 / +0.0  // Infinity
1.0 / -0.0  // -Infinity
```

Các dòng trên là minh họa biểu thức. Với phép chia số thực này, Java trả vô cực có dấu; không ném `ArithmeticException` như phép chia số nguyên cho không.

Do đó, cách hỏi “giá trị có nhỏ hơn không không?” khác với “bit dấu của nó có âm không?”. `copySign` thực hiện bài toán thứ hai khi nhận nguồn dấu.

Tài liệu [Double: signed zero và phép so sánh](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Double.html) mô tả sự khác biệt này.

## 3. Chương trình hoàn chỉnh: nhìn kết quả và bit

Tạo tệp `CopySignDemo.java`:

```java
public class CopySignDemo {
    public static void main(String[] args) {
        show("positive-to-negative", 3.5, -2.0);
        show("negative-to-positive", -3.5, 2.0);
        show("positive-zero-sign", 3.5, +0.0);
        show("negative-zero-sign", 3.5, -0.0);
        show("zero-magnitude", +0.0, -1.0);
        show("infinite-magnitude", Double.POSITIVE_INFINITY, -1.0);
        show("infinite-sign", 2.0, Double.NEGATIVE_INFINITY);

        double negativeZero = Math.copySign(0.0, -1.0);
        System.out.println("zero.equal=" + (negativeZero == 0.0));
        System.out.println("zero.less=" + (negativeZero < 0.0));
        System.out.println("zero.reciprocal=" + (1.0 / negativeZero));
        System.out.println("naive.zero-sign=" + (Math.abs(3.5) * Math.signum(-0.0)));
        System.out.println("float.result=" + Math.copySign(2.5f, -0.0f));
        System.out.println("nan.magnitude=" + Double.isNaN(Math.copySign(Double.NaN, -1.0)));
        double negativeNaN = Double.longBitsToDouble(0xFFF8000000000000L);
        System.out.println("strict.nan-sign=" + StrictMath.copySign(7.0, negativeNaN));
    }

    private static void show(String label, double magnitude, double sign) {
        double result = Math.copySign(magnitude, sign);
        System.out.println(label + "=" + result + ", bits="
                + String.format("%016X", Double.doubleToRawLongBits(result)));
    }
}
```

`show` in giá trị và biểu diễn bit `double` dạng hex. Với `-0.0`, chữ số đầu `8` ở dãy `8000000000000000` giúp nhìn thấy bit dấu được đặt, dù phép so sánh `==` coi hai số không là bằng nhau.

Mã dùng `doubleToRawLongBits` để quan sát biểu diễn số thực. Đây là phép đổi cách nhìn các bit, không phải ép kiểu số học `(long) result`. Xem [Double.doubleToRawLongBits](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Double.html#doubleToRawLongBits(double)).

### Biên dịch và chạy

Lưu tệp UTF-8 không BOM. Mở terminal tại thư mục chứa tệp, dùng JDK 17 trở lên có `javac` và `java` trong `PATH`:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -d out CopySignDemo.java
java -cp out CopySignDemo
```

Stdout đã kiểm chứng trên Microsoft OpenJDK 21.0.9:

```text
positive-to-negative=-3.5, bits=C00C000000000000
negative-to-positive=3.5, bits=400C000000000000
positive-zero-sign=3.5, bits=400C000000000000
negative-zero-sign=-3.5, bits=C00C000000000000
zero-magnitude=-0.0, bits=8000000000000000
infinite-magnitude=-Infinity, bits=FFF0000000000000
infinite-sign=-2.0, bits=C000000000000000
zero.equal=true
zero.less=false
zero.reciprocal=-Infinity
naive.zero-sign=-0.0
float.result=-2.5
nan.magnitude=true
strict.nan-sign=7.0
```

## 4. Đọc các nhóm kết quả

### 4.1. Dấu ban đầu của magnitude không quyết định dấu kết quả

Hai lời gọi đầu đưa ra `-3.5` và `3.5`. Độ lớn vẫn là 3.5; dấu được lấy lại từ đối số thứ hai.

Vì thế, “bảo toàn dấu” trong một thuật toán thường nghĩa là giữ dấu của **giá trị nguồn được chọn**. Không nên hiểu rằng `copySign` luôn giữ dấu đang có của đối số thứ nhất.

### 4.2. Nguồn dấu bằng không vẫn được sử dụng

`positive-zero-sign` và `negative-zero-sign` có cùng độ lớn nhưng dấu khác nhau. Đây là trường hợp một nhánh `sign < 0.0` không phân biệt được.

`zero-magnitude` cho thấy phương thức còn tạo được số không có dấu khi chính độ lớn bằng không.

### 4.3. Vô cực có hai vai trò khác nhau

Nếu độ lớn là vô cực, kết quả vẫn có độ lớn vô cực và dấu mới, như `infinite-magnitude=-Infinity`.

Nếu nguồn dấu là vô cực, chỉ dấu của nó được sử dụng. `Math.copySign(2.0, Double.NEGATIVE_INFINITY)` trả `-2.0`, không trở thành vô cực.

## 5. Vì sao các biểu thức tự viết dễ sai?

### Dùng nhánh so sánh với không

Đoạn minh họa:

```java
double result = sign < 0.0 ? -Math.abs(magnitude) : Math.abs(magnitude);
```

Khi `sign=-0.0`, điều kiện là `false`, nên ví dụ với độ lớn 3.5 trả `+3.5`. `copySign` cần trả `-3.5`.

### Nhân với signum

Đoạn minh họa:

```java
double result = Math.abs(magnitude) * Math.signum(sign);
```

`Math.signum(-0.0)` trả `-0.0`. Kết quả trong chương trình là `-0.0`, làm mất độ lớn 3.5 ban đầu. Khi kết hợp với vô cực, các phép nhân còn có thể sinh NaN theo quy tắc số thực.

Như vậy, `signum` là phép lấy giá trị dấu theo hợp đồng riêng; nó không thay cho thao tác ghép độ lớn với dấu.

### Nhân trực tiếp với nguồn dấu

```java
double result = Math.abs(magnitude) * sign;
```

Cách này thay cả độ lớn. Với `magnitude=3.5`, `sign=-2.0`, kết quả là `-7.0` chứ không phải `-3.5`.

Sử dụng `copySign` vừa biểu đạt đúng ý định, vừa tránh phải tự tái hiện các trường hợp biên bằng nhiều nhánh.

## 6. NaN: phân biệt đối số độ lớn và đối số dấu

### NaN làm độ lớn

```java
Math.copySign(Double.NaN, -1.0)
```

vẫn cho kết quả NaN. Thay dấu không biến một kết quả không phải số thành một số hữu hạn hợp lệ. Chương trình dùng `Double.isNaN` để kiểm tra; không dùng `result == Double.NaN`.

Không lấy ví dụ này làm cam kết rằng mọi mẫu payload NaN phải được bảo toàn theo cùng một cách trên mọi nền tảng.

### NaN làm nguồn dấu

Đây là chỗ `Math.copySign` và `StrictMath.copySign` có hợp đồng khác nhau:

| Phương thức | Khi đối số sign là NaN |
| --- | --- |
| `Math.copySign` | Không bắt buộc xem mọi NaN là dấu dương; cách triển khai được phép xử lý khác nhau |
| `StrictMath.copySign` | Luôn xem nguồn dấu NaN như dương |

Vì vậy, chương trình không in một kết quả dấu cố định cho `Math.copySign(7.0, negativeNaN)`. Nó kiểm chứng `StrictMath.copySign` và nhận `7.0`, đúng với hợp đồng.

Xem [ghi chú NaN của Math.copySign](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html#copySign(double,double)) và [StrictMath.copySign](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StrictMath.html#copySign(double,double)).

Trong ứng dụng, nếu NaN không có ý nghĩa làm nguồn dấu, hãy phát hiện và xử lý theo quy tắc dữ liệu trước khi gọi. Việc chọn `StrictMath` không thay thế quyết định nghiệp vụ xem đầu vào NaN có hợp lệ hay không.

## 7. Áp dụng: đổi độ lớn nhưng giữ dấu gốc

Giả sử một thuật toán đã tính được độ lớn điều chỉnh `adjustedMagnitude`, và muốn giữ dấu của `original`:

```java
double adjusted = Math.copySign(adjustedMagnitude, original);
```

Đây là đoạn minh họa khi hai biến đã tồn tại. Nó giữ dấu nguồn, kể cả `original=-0.0`. Điều kiện cần xác định riêng là: thuật toán có cho phép zero, vô cực hoặc NaN không?

Một ví dụ dữ liệu hữu hạn:

```java
double original = -8.0;
double adjustedMagnitude = 2.5;
double adjusted = Math.copySign(adjustedMagnitude, original);
// adjusted là -2.5
```

Nếu bài toán chỉ cần biến số thành không âm, `Math.abs` đã thể hiện đúng mục đích. Dùng `copySign` khi dấu thực sự đến từ một nguồn khác hoặc cần giữ quy tắc dấu nguồn rõ ràng.

### Chọn float hoặc double có chủ đích

```java
float small = Math.copySign(2.5f, -0.0f);
double wide = Math.copySign(2.5, -0.0);
```

Hai literal có hậu tố `f` giúp chọn overload `float`; literal thập phân không có hậu tố mặc định là `double`. Trong chương trình, `float.result=-2.5` minh họa overload thứ nhất.

Không chuyển sang `float` chỉ để đổi dấu nếu phần còn lại của thuật toán cần độ chính xác `double`.

## 8. Lỗi thường gặp

| Nhầm lẫn | Hệ quả |
| --- | --- |
| Đảo thứ tự hai đối số | Lấy sai độ lớn và sai nguồn dấu |
| Cho rằng magnitude âm thì kết quả phải âm | Bỏ qua việc dấu được thay bằng đối số thứ hai |
| Dùng `sign < 0` để phân biệt mọi dấu | Mất trường hợp `-0.0` |
| Nhân với nguồn dấu bất kỳ | Thay cả độ lớn |
| Dùng `==` để kiểm tra NaN | Không nhận đúng NaN |
| Cố định kết quả dấu Math khi nguồn là NaN | Phụ thuộc giả định vượt hợp đồng |
| Gọi phương thức mà không dùng kết quả | Biến đầu vào không tự được cập nhật |

## 9. Tự kiểm tra

1. Dự đoán `Math.copySign(-4.0, +0.0)` rồi kiểm chứng.
2. Vì sao `Math.copySign(4.0, -0.0)` khác biểu thức dùng `sign < 0.0`?
3. Vì sao nguồn dấu `Double.NEGATIVE_INFINITY` không làm độ lớn 2.0 trở thành vô cực?
4. Tại sao cần phân biệt NaN ở đối số thứ nhất với NaN ở đối số thứ hai?
5. Nếu muốn giữ dấu của một kết quả gốc sau khi đổi độ lớn, biến nào phải đứng ở đối số thứ hai?

Hãy đọc lời gọi thành một câu rõ ràng: **lấy độ lớn của giá trị thứ nhất, gắn dấu của giá trị thứ hai**. Với số thực, câu này còn bao gồm signed zero và các điều kiện đặc biệt của API.
