# Kiểm thử tràn, hụt số và các giá trị biên

## 1. Vì sao cần thử ngoài những con số “bình thường”?

Một hàm số học có thể cho kết quả hợp lý với `3.0` và `4.0`, nhưng thất bại khi đầu vào rất lớn, rất nhỏ, bằng zero hoặc không hữu hạn. Với `float`/`double`, các trường hợp đó thường tạo **giá trị đặc biệt**, không tự ném ngoại lệ.

Ví dụ, một phép nhân tràn có thể trả vô cực; kết quả rất nhỏ có thể đi vào miền dưới chuẩn hoặc bị làm tròn về zero. Nếu chỉ kiểm tra “không có exception”, một bài kiểm thử có thể bỏ qua sự cố quan trọng.

Cần kiểm chứng hai lớp:

1. Hành vi của phép toán theo quy tắc Java.
2. Hành vi mà hàm ứng dụng phải cung cấp khi gặp kết quả đó: chấp nhận, báo lỗi, đổi cách tính hay từ chối đầu vào.

Bài dùng Java 17+ và các quy tắc số dấu phẩy động còn áp dụng trên Java hiện đại.

## 2. Phân loại đúng trước khi kiểm thử

| Hiện tượng | Dấu hiệu | Không nên nhầm với |
| --- | --- | --- |
| Tràn số dấu phẩy động | Kết quả ngoài miền hữu hạn và được làm tròn thành vô cực | Mọi phép cộng vào MAX_VALUE đều tạo vô cực |
| Kết quả dưới chuẩn | Giá trị khác zero nhỏ hơn MIN_NORMAL về độ lớn | Tự động là một kết quả sai |
| Hụt về zero | Kết quả thực khác zero nhưng quá nhỏ, sau làm tròn trở thành zero | Tích có đầu vào zero hợp lệ |
| NaN | Phép toán không cho một giá trị số theo quy tắc tương ứng | Một số rất lớn hoặc một loại vô cực |
| Mất độ chính xác | Kết quả có thể hữu hạn nhưng mất thông tin cần giữ | Chỉ xảy ra khi tràn/hụt |

Ví dụ:

```java
Double.MAX_VALUE * 2.0;     // +Infinity
Double.MIN_NORMAL / 2.0;    // số dưới chuẩn, vẫn khác zero và biểu diễn chính xác
Double.MIN_VALUE / 2.0;     // +0.0 sau làm tròn
0.0 / 0.0;                 // NaN
```

Đây là các biểu thức minh họa, chưa phải chương trình độc lập.

Việc một kết quả rơi vào miền dưới chuẩn không tự chứng minh đã mất dữ liệu. Chẳng hạn `Double.MIN_NORMAL / 2.0` là lũy thừa của 2 còn biểu diễn được chính xác. Thuật ngữ underflow trong phân tích IEEE 754 còn liên quan độ nhỏ và tính không chính xác; trong kiểm thử Java nên nêu rõ đang kiểm “dưới chuẩn”, “làm tròn về zero” hay một yêu cầu sai số cụ thể.

## 3. Các mốc để thiết kế dữ liệu thử

| Mốc double | Ý nghĩa |
| --- | --- |
| `Double.MAX_VALUE` | Số dương hữu hạn lớn nhất |
| `-Double.MAX_VALUE` | Số âm hữu hạn có độ lớn lớn nhất |
| `Double.MIN_NORMAL` | Số dương chuẩn nhỏ nhất, `2^-1022` |
| `Double.MIN_VALUE` | Số dương khác zero nhỏ nhất, `2^-1074` |
| `+0.0`, `-0.0` | Hai zero có dấu |
| `Double.POSITIVE_INFINITY`, `NEGATIVE_INFINITY` | Hai vô cực |
| `Double.NaN` | Không phải một giá trị số |

`MIN_VALUE` không phải số âm nhỏ nhất. Khi đổi sang `float`, phải dùng các hằng của `Float`; dải biểu diễn và độ chính xác khác với `double`.

Tạo hàng xóm của một mốc bằng `Math.nextDown`/`Math.nextUp`, thay vì trừ/cộng một epsilon tùy ý. Ví dụ `Math.nextDown(Double.MIN_NORMAL)` là giá trị dưới chuẩn lớn nhất phía dương, nằm ngay dưới miền chuẩn.

Các hằng và quy tắc giá trị theo [Double](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Double.html) và [JLS về float/double](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.2.3).

## 4. Chọn phép kiểm phù hợp với loại kết quả

### Vô cực và NaN

Dùng `Double.isFinite`, `Double.isInfinite` hoặc `Double.isNaN` theo ý định. Nếu dấu vô cực quan trọng, so với hằng vô cực đúng dấu.

Không viết:

```java
result == Double.NaN
```

để phát hiện NaN. Biểu thức đó là `false` kể cả khi `result` là NaN.

`Double.isFinite(result)` loại cả NaN lẫn vô cực, nhưng không phát hiện mọi mất độ chính xác hoặc mọi lần hụt về zero. Zero và số dưới chuẩn đều là hữu hạn.

### Zero có dấu

`+0.0 == -0.0` là `true`, nhưng dấu có thể ảnh hưởng phép toán tiếp theo:

```java
1.0 / 0.0;    // +Infinity
1.0 / -0.0;   // -Infinity
```

Khi kiểm thử cần phân biệt dấu, dùng biểu diễn bit hoặc một phép kiểm phù hợp. Ví dụ chương trình bên dưới dùng `Double.doubleToRawLongBits`.

Không lấy `result == 0.0` làm bằng chứng tự động rằng đã hụt số: một công thức có thể cho zero chính xác theo toán học. Phải hiểu đầu vào và kết quả mong đợi.

### Giá trị hữu hạn gần đúng

Nếu hợp đồng là gần đúng, chọn ngưỡng tuyệt đối, tương đối hoặc ULP theo bài toán. Không đặt một epsilon cố định cho mọi miền độ lớn.

Nếu ca thử được thiết kế bằng các lũy thừa 2 biểu diễn chính xác, có thể dùng so sánh chính xác theo giá trị mong đợi. Không cần thêm dung sai để che đi một ca mà kết quả đã biết chính xác.

## 5. Kiểm thử cả trung gian, không chỉ kết quả toán học cuối

Công thức:

```java
Math.sqrt(x * x + y * y)
```

có thể tràn ở các phép bình phương dù chuẩn Euclid cuối cùng vẫn hữu hạn. Với `x = y = 1e200`, các bình phương vượt miền `double`; lấy căn sau đó không phục hồi được dữ liệu đã thành vô cực.

Chiều ngược lại, `x = y = 1e-200` có thể làm các bình phương hụt về zero, dù chuẩn cuối vẫn khác zero.

`Math.hypot(x, y)` được thiết kế tính chuẩn mà tránh tràn/hụt trung gian theo hợp đồng của hàm. Điều đó không có nghĩa nó luôn trả hữu hạn với mọi đầu vào: chuẩn thực sự quá lớn vẫn có thể không biểu diễn hữu hạn được.

Một bài kiểm thử tốt cần ca mà:

- Công thức trực tiếp gặp lỗi miền trung gian.
- Công thức phù hợp hơn tránh được lỗi trung gian.
- Kết quả cuối thực sự vượt miền, để không hứa rằng thuật toán tránh được mọi tràn.

Xem [Math.hypot](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html#hypot(double,double)).

## 6. Chuyển kiểu cũng là một biên số học

Một kết quả `double` hữu hạn có thể không còn hữu hạn khi thu hẹp về `float`:

```java
float tooLarge = (float) Double.MAX_VALUE; // +Infinity
float tooSmall = (float) Double.MIN_VALUE; // +0.0f
```

Vì vậy, thử cả điểm chuyển kiểu, lưu trữ hoặc giao tiếp với thư viện khác. Không chỉ kiểm thử kiểu của biểu thức trung gian.

Đặc biệt, kiểm tra hậu tố literal:

```java
float f = 1.0f;
double d = 1.0;
```

Nếu mục tiêu kiểm thử overload `float` mà truyền một literal `double`, phép thử đang nhắm sai định dạng.

Thu hẹp số dấu phẩy động có thể làm tròn, tràn hoặc hụt; không tự ném exception chỉ vì mất độ lớn/độ chính xác. Quy tắc theo [JLS về narrowing conversion](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.3).

## 7. Chương trình kiểm chứng Java 17+ với 18 ca

Tệp `FloatingBoundaryChecks.java`:

```java
public final class FloatingBoundaryChecks {
    private static int passed;

    public static void main(String[] args) {
        double positiveOverflow = Double.MAX_VALUE * 2.0;
        double negativeOverflow = -Double.MAX_VALUE * 2.0;
        check("positive overflow", positiveOverflow == Double.POSITIVE_INFINITY);
        check("negative overflow", negativeOverflow == Double.NEGATIVE_INFINITY);

        double subnormal = Double.MIN_NORMAL / 2.0;
        check("exact subnormal", subnormal == 0x0.8p-1022);
        check("below normal boundary",
                Math.nextDown(Double.MIN_NORMAL) > 0.0
                && Math.nextDown(Double.MIN_NORMAL) < Double.MIN_NORMAL);

        check("positive underflow to zero",
                Double.doubleToRawLongBits(Double.MIN_VALUE / 2.0) == 0L);
        check("negative underflow to zero",
                Double.doubleToRawLongBits(-Double.MIN_VALUE / 2.0)
                        == Double.doubleToRawLongBits(-0.0));
        check("signed zero division",
                1.0 / -0.0 == Double.NEGATIVE_INFINITY);

        check("zero divided by zero is NaN", Double.isNaN(0.0 / 0.0));
        check("infinity times zero is NaN",
                Double.isNaN(Double.POSITIVE_INFINITY * 0.0));
        check("negative square root is NaN", Double.isNaN(Math.sqrt(-1.0)));
        check("finite tiny value", Double.isFinite(Double.MIN_VALUE));

        check("narrowing overflow",
                (float) Double.MAX_VALUE == Float.POSITIVE_INFINITY);
        check("narrowing underflow", (float) Double.MIN_VALUE == 0.0f);

        double large = 1e200;
        check("naive norm overflows",
                Double.isInfinite(Math.sqrt(large * large + large * large)));
        check("hypot avoids intermediate overflow",
                Double.isFinite(Math.hypot(large, large)));
        check("tiny naive norm vanishes",
                Math.sqrt(1e-200 * 1e-200 + 1e-200 * 1e-200) == 0.0);
        check("hypot preserves tiny norm",
                Math.hypot(1e-200, 1e-200) > 0.0);

        double base = 1e16;
        check("finite does not mean exact", (base + 1.0) - base == 0.0);

        System.out.println("PASS " + passed + " checks");
    }

    private static void check(String name, boolean condition) {
        if (!condition) {
            throw new AssertionError(name);
        }
        passed++;
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 FloatingBoundaryChecks.java
java FloatingBoundaryChecks
```

Stdout:

```text
PASS 18 checks
```

Nếu một điều kiện sai, chương trình ném `AssertionError` kèm tên ca. Hàm `check` tự kiểm tra điều kiện, nên không phụ thuộc cờ `-ea` của câu lệnh `assert`.

### Vì sao chọn các điều kiện này?

- Hai ca đầu thử tràn cả hai dấu.
- Ca `exact subnormal` phân biệt kết quả dưới chuẩn chính xác với dữ liệu bị mất.
- Hàng xóm dưới `MIN_NORMAL` kiểm tra sát ranh giới.
- Hai ca làm tròn về zero xác nhận cả dấu dương/âm.
- Ba phép toán NaN được kiểm bằng `isNaN`, không so bằng.
- Hai phép ép kiểu cho thấy biên kiểu số là một nơi phát sinh mất miền biểu diễn.
- Các ca chuẩn Euclid đối chiếu công thức trực tiếp với `hypot` ở cả độ lớn rất lớn và rất nhỏ.
- Ca cuối cho thấy kết quả hữu hạn không đồng nghĩa phép tính giữ được mọi gia số: trong miền của `1e16`, cộng `1.0` bị làm tròn về giá trị cũ trước khi trừ lại.

Phép kiểm `hypot` trong ví dụ chứng minh không bị lỗi trung gian ở hai ca đã chọn. Nó chưa kiểm đầy đủ giới hạn sai số ULP của hàm trên toàn miền; đó là một mục tiêu kiểm thử khác.

## 8. Quy định phản ứng của hàm ứng dụng

Một hàm nghiệp vụ cần nói rõ loại kết quả nào được phép. Ví dụ, nếu hợp đồng yêu cầu tích hữu hạn và không chấp nhận tích của hai số khác zero bị làm tròn về zero, có thể dùng kiểm tra sau:

```java
static double multiplyChecked(double left, double right) {
    if (!Double.isFinite(left) || !Double.isFinite(right)) {
        throw new IllegalArgumentException("inputs must be finite");
    }

    double result = left * right;
    if (!Double.isFinite(result)) {
        throw new ArithmeticException("non-finite product");
    }
    if (left != 0.0 && right != 0.0 && result == 0.0) {
        throw new ArithmeticException("nonzero product rounded to zero");
    }
    return result;
}
```

Đây là phương thức minh họa để đặt trong một lớp. Các ngoại lệ là do **chính hàm kiểm tra này ném**, không phải phép nhân `double` mặc định tự báo lỗi.

Giới hạn của hợp đồng đó:

- Cho phép zero nếu một đầu vào vốn bằng zero.
- Cho phép số dưới chuẩn khác zero.
- Không phát hiện mọi mất chính xác hoặc mọi kết quả dưới chuẩn có làm tròn.
- Không chứng minh tích hữu hạn là đủ chính xác cho nghiệp vụ.

Đừng đặt tên hoặc mô tả nó là “phép nhân double chính xác tuyệt đối”. Nếu yêu cầu khác — chẳng hạn cấm mọi kết quả dưới chuẩn — phải nêu rõ và kiểm thử theo yêu cầu đó, không lẫn với hành vi Java chuẩn.

## 9. Mở rộng bộ kiểm thử theo cấu trúc, không chỉ thêm số ngẫu nhiên

Một ma trận hữu ích cho mỗi hàm số học:

| Nhóm | Ca nên có |
| --- | --- |
| Bình thường | Số có kết quả biết trước trong miền ổn định |
| Dấu | Dương, âm, hai đầu vào khác dấu nếu phù hợp |
| Biên trên | Gần MAX_VALUE, bước kế tiếp và trường hợp kết quả thực vượt miền |
| Biên dưới | MIN_NORMAL, hàng xóm dưới nó, MIN_VALUE |
| Zero | Cả hai dấu nếu dấu ảnh hưởng hợp đồng |
| Không hữu hạn | NaN và hai vô cực, hoặc ca xác nhận hàm từ chối chúng |
| Chuyển kiểu | Thu hẹp xuống float hoặc chuyển sang kiểu lưu trữ thực tế |
| Công thức trung gian | Kết quả cuối hợp lệ nhưng trung gian tràn/hụt |
| Sai số | Ca nhạy cảm với làm tròn, mất chữ số hoặc tích lũy |

Kiểm thử sinh dữ liệu có thể bổ sung độ phủ, nhưng nên chủ động đưa các mẫu biên vào. Chọn số ngẫu nhiên trong một khoảng thông thường khó đi trúng MIN_VALUE, các hàng xóm của MIN_NORMAL hoặc zero có dấu.

Với các tính chất như “đổi tỷ lệ rồi đổi ngược sẽ trở lại ban đầu”, phải ràng buộc miền: tính chất có thể sai nếu bước trung gian tràn, hụt hoặc làm tròn. Không dùng một tính chất chỉ đúng trên số thực làm giả định kiểm thử vô điều kiện cho `double`.

Nếu cần một giá trị tham chiếu độ chính xác cao, xác định đang so với phép toán trên dữ liệu thập phân người dùng nhập hay trên chính các giá trị nhị phân của đầu vào. Hai mục tiêu có thể khác nhau; đừng dùng một công thức có cùng lỗi làm nguồn kết quả mong đợi.

## 10. Những kết luận cần tránh

| Kết quả quan sát | Chưa chứng minh |
| --- | --- |
| Không có exception | Không tràn/hụt hoặc không NaN |
| isFinite trả true | Không mất dữ liệu số |
| Kết quả là subnormal | Phép tính đã sai hoặc cần tự thay bằng zero |
| Một ca gần zero đạt | Mọi ca gần zero có cùng sai số tương đối |
| Hàm ổn với double | Ổn sau khi ép sang float |
| 18 ca trong ví dụ đều đạt | Thuật toán của một ứng dụng bất kỳ đã đủ độ chính xác |

Tự thực hành:

1. Bổ sung ca `Math.hypot(Double.MAX_VALUE, Double.MAX_VALUE)`; giải thích vì sao kết quả cuối có thể là vô cực dù hàm tránh lỗi trung gian.
2. Thử `Double.MAX_VALUE + 1.0`; chỉ ra vai trò của làm tròn thay vì dự đoán cứ cộng thêm là tràn.
3. Tạo ca dưới chuẩn khác zero chính xác và ca làm tròn về zero; viết hai phép kiểm riêng.
4. Kiểm thử `multiplyChecked` với đầu vào zero, NaN, hai số lớn và hai số rất nhỏ.
5. Với một hàm ứng dụng thật, xác định rõ nó chấp nhận hay từ chối NaN, vô cực, zero và số dưới chuẩn.
