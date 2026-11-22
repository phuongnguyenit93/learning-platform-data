# ArithmeticException khi không thể đáp ứng yêu cầu chính xác trong BigDecimal

## 1. Vấn đề cần hiểu

`BigDecimal` biểu diễn số thập phân bằng một số nguyên không chia tỷ lệ (`unscaledValue`) và một `scale`:

```text
giá trị = unscaledValue × 10^(-scale)
1.230  = 1230 × 10^(-3)
```

Nhờ đó, các số như `0.1`, `12.34` có thể được biểu diễn chính xác theo hệ thập phân nếu khởi tạo từ chuỗi thích hợp. Tuy nhiên, **không phải thương của hai số thập phân hữu hạn cũng có biểu diễn thập phân hữu hạn**. Chẳng hạn, `1 / 3 = 0.3333...` có vô hạn chữ số.

Nếu chương trình yêu cầu kết quả **chính xác tuyệt đối** trong khi biểu diễn hữu hạn không đáp ứng được, hoặc cấm mọi làm tròn dù thao tác cần làm tròn, `BigDecimal` ném `ArithmeticException`. Đây là tín hiệu rằng *điều kiện chính xác đã yêu cầu không thể được đáp ứng*, không có nghĩa kiểu `BigDecimal` luôn thiếu chính xác.

Ba tình huống thường gặp:

- Gọi `divide(BigDecimal)` cho thương thập phân vô hạn, chẳng hạn `1 / 3`.
- Dùng `RoundingMode.UNNECESSARY` với `setScale`, `divide` hay `round` trong trường hợp muốn có kết quả thì phải loại bỏ chữ số có giá trị.
- Dùng `MathContext` có giới hạn chữ số đáng kể (`precision`) và chế độ `UNNECESSARY` khi kết quả không thể giữ nguyên ở giới hạn ấy.

**Phạm vi:** Bài tập trung vào ngoại lệ do yêu cầu chính xác/làm tròn trong các phép toán `BigDecimal`. Chia cho 0 cũng ném `ArithmeticException`, nhưng là nguyên nhân độc lập cần phân biệt khi chẩn đoán.

## 2. Chính xác, scale, precision và rounding là bốn ý khác nhau

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Giá trị số | Đại lượng toán học được biểu diễn | `1.230` và `1.23` cùng giá trị |
| `scale` | Số chữ số ở bên phải dấu thập phân đối với giá trị scale không âm | `1.230` có scale 3 |
| `precision` | Số chữ số của `unscaledValue` (không đếm dấu); tính cả số 0 cuối nếu còn trong biểu diễn | `1.230` có precision 4 |
| `RoundingMode` | Quy tắc khi phải bỏ chữ số có giá trị để đáp ứng scale/precision | `HALF_UP`, `HALF_EVEN`, `DOWN`, `UNNECESSARY` |

Ví dụ, `new BigDecimal("1.230").setScale(2, RoundingMode.UNNECESSARY)` thành `1.23` **không gây lỗi**: chỉ bỏ một chữ số 0 và giá trị không đổi. Ngược lại, `new BigDecimal("1.234").setScale(2, RoundingMode.UNNECESSARY)` phải bỏ chữ số 4 có giá trị, nên ném `ArithmeticException`.

`UNNECESSARY` không phải là chế độ “làm tròn tốt nhất”; nó là **điều kiện kiểm tra** rằng phép biến đổi *không cần* làm tròn. Dùng nó khi việc mất bất kỳ chữ số có giá trị nào phải bị phát hiện và xử lý.

`MathContext.UNLIMITED` có `precision = 0`, nghĩa là không áp dụng giới hạn chữ số đáng kể. Nó **không** khiến `1 / 3` có một chuỗi chữ số thập phân hữu hạn. Vì vậy, chia thương vô hạn với ngữ cảnh không giới hạn vẫn có thể ném ngoại lệ.

## 3. Chẩn đoán lỗi chia chính xác từ bản chất thương

`divide(divisor)` chỉ thành công khi thương có biểu diễn thập phân hữu hạn. Sau khi rút gọn phân số, mẫu số chỉ được chứa thừa số 2 và 5; vì vậy `1/8`, `3/6` thành công, còn `1/3`, `1/6` ném `ArithmeticException`. Bài *divide chính xác và số thập phân vô hạn tuần hoàn* đã chứng minh tiêu chí này.

Khi **xử lý ngoại lệ**, trước hết kiểm tra `divisor.signum() == 0` để tách lỗi đầu vào. Nếu số chia khác 0, kiểm tra overload có yêu cầu thương exact không, hay một `RoundingMode.UNNECESSARY` hoặc `MathContext` đang từ chối bỏ chữ số có giá trị. **Đừng** bắt chung các trường hợp rồi tự động chọn `HALF_UP`: điều đó làm thay đổi hợp đồng chính xác.

## 4. Các overload dễ bị nhầm của divide

```java
BigDecimal a = new BigDecimal("1");
BigDecimal b = new BigDecimal("3");

// Yêu cầu thương chính xác: ném ArithmeticException.
a.divide(b);

// Quy định 2 chữ số sau dấu thập phân và chế độ làm tròn.
a.divide(b, 2, RoundingMode.HALF_UP); // 0.33

// Quy định tối đa 5 chữ số đáng kể cho kết quả.
a.divide(b, new MathContext(5, RoundingMode.HALF_EVEN)); // 0.33333

// Cấm làm tròn trong kết quả có scale 2: ném ArithmeticException.
a.divide(b, 2, RoundingMode.UNNECESSARY);
```

Các dòng này là **minh họa độc lập về API**, không phải một chương trình chạy tuần tự: nếu thực thi dòng `divide(b)` chưa bắt ngoại lệ, các dòng sau sẽ không chạy.

Điểm cần nhớ:

1. `divide(divisor)` yêu cầu chính xác và không tự chọn số chữ số hay chính sách làm tròn.
2. `divide(divisor, scale, roundingMode)` kiểm soát **số chữ số sau dấu thập phân**. Ví dụ scale 2 tạo số dạng `0.33`.
3. `divide(divisor, mathContext)` kiểm soát **chữ số đáng kể**, khác với số chữ số thập phân. Ví dụ precision 5 cho `0.33333`, còn `12345 / 1` ở precision 5 vẫn có năm chữ số trước dấu thập phân.
4. `divide(divisor, roundingMode)` là một overload khác: **scale của kết quả bằng scale của số bị chia**. Nó không mặc định là hai chữ số thập phân. Vì sự khác biệt này, trong code nghiệp vụ hãy ưu tiên overload khai báo tường minh scale hoặc `MathContext`.

Ngay cả khi chọn `UNNECESSARY`, phép chia vẫn có thể thành công nếu thương chính xác phù hợp scale/precision yêu cầu. Ví dụ `new BigDecimal("1").divide(new BigDecimal("8"), 3, RoundingMode.UNNECESSARY)` trả `0.125`; với scale 2 thì ném ngoại lệ.

## 5. Ví dụ Java 17+ chạy được và kết quả chính xác

Lưu tệp `BigDecimalExactnessDemo.java`:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class BigDecimalExactnessDemo {
    private static void attempt(String label, Runnable operation) {
        try {
            operation.run();
        } catch (ArithmeticException e) {
            System.out.println(label + ": " + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        BigDecimal one = new BigDecimal("1");
        BigDecimal three = new BigDecimal("3");

        System.out.println("1 / 8 exact = "
                + one.divide(new BigDecimal("8")));

        attempt("1 / 3 exact", () ->
                System.out.println(one.divide(three)));

        System.out.println("1 / 3 scale=2 = "
                + one.divide(three, 2, RoundingMode.HALF_UP));

        System.out.println("1 / 3 precision=5 = "
                + one.divide(three, new MathContext(5, RoundingMode.HALF_EVEN)));

        System.out.println("Drop trailing zero = "
                + new BigDecimal("1.230")
                        .setScale(2, RoundingMode.UNNECESSARY));

        attempt("Drop nonzero digit", () ->
                System.out.println(new BigDecimal("1.234")
                        .setScale(2, RoundingMode.UNNECESSARY)));

        attempt("Precision=2 without rounding", () ->
                System.out.println(new BigDecimal("12.345")
                        .round(new MathContext(2, RoundingMode.UNNECESSARY))));

        attempt("Division by zero", () ->
                System.out.println(one.divide(BigDecimal.ZERO)));
    }
}
```

Chạy:

```bash
javac BigDecimalExactnessDemo.java
java BigDecimalExactnessDemo
```

Stdout:

```text
1 / 8 exact = 0.125
1 / 3 exact: ArithmeticException
1 / 3 scale=2 = 0.33
1 / 3 precision=5 = 0.33333
Drop trailing zero = 1.23
Drop nonzero digit: ArithmeticException
Precision=2 without rounding: ArithmeticException
Division by zero: ArithmeticException
```

Ví dụ cố ý chỉ in **loại ngoại lệ**: thông điệp chi tiết của `ArithmeticException` có thể thay đổi giữa API hoặc bản JDK, và không nên dùng thông điệp ấy làm giao kèo logic. Trong ứng dụng thật, không nên bắt tất cả `ArithmeticException` rồi thay bằng một kết quả mặc định: nó có thể che khuất lỗi chia cho 0 hay vi phạm invariant.

## 6. Vì sao MathContext với UNNECESSARY cũng gây lỗi?

`MathContext` là cặp gồm `precision` và `roundingMode`. Ví dụ:

```java
BigDecimal x = new BigDecimal("1.234");
MathContext strict = new MathContext(3, RoundingMode.UNNECESSARY);

// Cần đổi 1.234 thành số chỉ có 3 chữ số đáng kể.
// Vì chữ số 4 cuối có giá trị, round(strict) ném ArithmeticException.
x.round(strict);
```

Ngược lại, `new BigDecimal("1.230").round(new MathContext(3, RoundingMode.UNNECESSARY))` có thể cho `1.23` vì chỉ bỏ số 0 cuối mà không đổi giá trị.

Giới hạn precision không chỉ tác động đến `round`: một số overload của `add`, `subtract`, `multiply`, `divide`, `pow` nhận `MathContext` và cũng có thể yêu cầu làm tròn. Chẳng hạn `new BigDecimal("1.23").multiply(new BigDecimal("2"), new MathContext(2, RoundingMode.UNNECESSARY))` muốn giữ `2.46` ở hai chữ số đáng kể: không thể, nên ném ngoại lệ.

Nếu phép tính phải chính xác, cân nhắc giữ nguyên giá trị trung gian không giới hạn precision và chỉ áp dụng quy tắc biểu diễn ở **ranh giới đã thống nhất**. Đừng tự động tăng precision tùy ý rồi nghĩ ngoại lệ đã được giải quyết: thương `1 / 3` vẫn không bao giờ có biểu diễn thập phân hữu hạn chính xác.

## 7. Chọn giải pháp theo yêu cầu nghiệp vụ

**Trường hợp A — cần kết quả làm tròn hợp lệ.** Xác định scale hoặc precision cần dùng, rồi chọn `RoundingMode` theo quy tắc nghiệp vụ:

```java
BigDecimal ratio = new BigDecimal("1")
        .divide(new BigDecimal("3"), 4, RoundingMode.HALF_UP);
// 0.3333
```

**Trường hợp B — không chấp nhận mất bất kỳ chữ số có giá trị nào.** Dùng phép tính exact hoặc `UNNECESSARY` như một assertion có chủ ý; chuyển trường hợp không đáp ứng thành thông báo lỗi nghiệp vụ có ngữ cảnh:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class ExactMoney {
    public static BigDecimal requireTwoDecimals(BigDecimal value) {
        try {
            return value.setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException cause) {
            throw new IllegalArgumentException(
                    "Amount cannot be represented exactly with two decimals", cause);
        }
    }
}
```

Đoạn mã là class tiện ích có thể biên dịch, không có `main` nên không tự chạy. Với `12.340`, nó trả `12.34`; với `12.345`, nó ném `IllegalArgumentException` và giữ nguyên nguyên nhân `ArithmeticException` để hỗ trợ truy vết. Chỉ áp dụng ràng buộc hai chữ số nếu đó thực sự là hợp đồng dữ liệu của hệ thống.

**Trường hợp C — chia tiền hoặc đơn vị không chia đều.** Làm tròn thương từng phần có thể làm tổng phân bổ khác tổng gốc. Phải quy định cách xử lý phần dư, chẳng hạn phân bổ cho phần tử cuối:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class AllocationDemo {
    public static void main(String[] args) {
        BigDecimal total = new BigDecimal("10.00");
        BigDecimal count = new BigDecimal("3");
        BigDecimal first = total.divide(count, 2, RoundingMode.DOWN);
        BigDecimal second = first;
        BigDecimal last = total.subtract(first).subtract(second);

        System.out.println(first + ", " + second + ", " + last);
        System.out.println(first.add(second).add(last));
    }
}
```

Chạy `javac AllocationDemo.java` rồi `java AllocationDemo`, stdout là:

```text
3.33, 3.33, 3.34
10.00
```

Ví dụ này chỉ minh họa cách bảo toàn tổng; thứ tự chia phần dư, đồng tiền, đơn vị nhỏ nhất, quy định thuế và yêu cầu kiểm toán phải được xác định riêng. `RoundingMode.DOWN` được dùng để dễ theo dõi phân bổ số dương ở đây, không phải một chế độ phổ quát cho mọi giao dịch.

## 8. Cách chẩn đoán khi thấy ArithmeticException

1. **Xác định phép toán gây lỗi**: `divide`, `setScale`, `round`, hay overload dùng `MathContext`. Đọc stack trace và giá trị các toán hạng, thay vì chỉ bắt và nuốt ngoại lệ.
2. **Kiểm tra mẫu số**: nếu bằng 0 thì xử lý điều kiện đầu vào; quy tắc làm tròn không khắc phục chia cho 0.
3. **Kiểm tra yêu cầu exact**: `divide(divisor)` với thương thập phân vô hạn sẽ thất bại; hãy quyết định có cho phép làm tròn hay từ chối phép chia.
4. **Kiểm tra `UNNECESSARY`**: muốn rút bớt scale/precision có đang phải bỏ chữ số có giá trị không? Nếu có, đó là vi phạm đúng nghĩa của chính sách exact.
5. **Xác định precision khác scale**: `MathContext(2, ...)` là hai chữ số đáng kể, không phải hai số sau dấu phẩy; `setScale(2, ...)` mới kiểm soát hai chữ số sau dấu thập phân.
6. **Đối chiếu hợp đồng nghiệp vụ**: phép tính gần đúng có hợp lệ không, dùng kiểu làm tròn nào, làm tròn một lần hay nhiều lần, và phải phân bổ phần dư như thế nào?
7. **Ghi test cho ca biên**: thương kết thúc (`1/8`), thương vô hạn (`1/3`), bỏ zero (`1.230 → 1.23`), bỏ nonzero (`1.234 → 1.23`), và mẫu số bằng 0.

Không nên “sửa nhanh” bằng `double`: số nhị phân dấu phẩy động có thể đưa thêm sai số biểu diễn. Cũng không nên làm tròn kín đáo trong utility dùng chung khi người gọi chưa chấp thuận chính sách làm tròn.

## 9. Lỗi phổ biến và cách tránh

| Sai lầm | Hệ quả | Thay bằng |
| --- | --- | --- |
| Tưởng `BigDecimal` khiến `1/3` exact trở thành số thập phân hữu hạn | `divide` ném ngoại lệ | Chấp nhận làm tròn có chủ đích hoặc từ chối nghiệp vụ |
| Dùng `divide(divisor, RoundingMode.HALF_UP)` và ngỡ rằng kết quả có hai chữ số sau dấu thập phân | Scale kết quả phụ thuộc số bị chia | Dùng `divide(divisor, 2, RoundingMode.HALF_UP)` nếu cần scale 2 |
| Nhầm `MathContext(2, ...)` với `setScale(2, ...)` | Precision áp lên chữ số đáng kể, scale áp lên phần thập phân | Chọn tham số đúng ý nghĩa |
| Dùng `UNNECESSARY` như cách tránh tính toán chính sách làm tròn | Ngoại lệ khi cần làm tròn thật | Chọn chính sách nghiệp vụ hoặc xác nhận exact có chủ đích |
| Dùng `new BigDecimal(0.1)` để nhập decimal chính xác | Sao chép giá trị nhị phân của literal `double` | Dùng `new BigDecimal("0.1")` hoặc `BigDecimal.valueOf(0.1)` khi nhận `double` |
| Làm tròn nhiều bước mà không kiểm tra tổng | Sai lệch tích lũy, mất phần dư | Xác định điểm làm tròn và quy tắc phân bổ phần dư |
| Bắt `ArithmeticException` rồi trả `BigDecimal.ZERO` | Che lỗi chia cho 0/làm tròn không hợp lệ | Gắn ngữ cảnh, báo lỗi hoặc xử lý theo chính sách rõ ràng |

Lưu ý: `BigDecimal.valueOf(0.1)` dùng biểu diễn chuỗi thập phân của giá trị `double` đầu vào nên thông thường cho `0.1`, nhưng không thể phục hồi độ chính xác đã mất trước đó trong quá trình tính toán bằng `double`.

## 10. Tự kiểm tra

- Vì sao `new BigDecimal("1").divide(new BigDecimal("40"))` thành công, còn chia cho `30` lại thất bại? **Vì** `1/40 = 0.025` là hữu hạn (mẫu chỉ có 2 và 5), còn `1/30` có thừa số 3 ở mẫu sau rút gọn.
- `new BigDecimal("1.200").setScale(2, RoundingMode.UNNECESSARY)` có lỗi không? **Không**; kết quả `1.20` giữ nguyên giá trị.
- `new BigDecimal("1.201").setScale(2, RoundingMode.UNNECESSARY)` có lỗi không? **Có**; cần bỏ chữ số 1 có giá trị.
- Có phải tăng `MathContext` lên 100 chữ số là cách thực hiện chính xác `1/3`? **Không**; precision 100 vẫn chỉ là một xấp xỉ nếu cho phép rounding, còn exact vẫn không thể biểu diễn hữu hạn.
- Khi nào `UNNECESSARY` là lựa chọn hợp lý? **Khi yêu cầu chính xác là invariant đã được xác định**, ví dụ giá trị gửi tới trường lưu trữ có scale cố định và không cho phép mất chữ số có giá trị.

## 11. Ghi nhớ

`ArithmeticException` trong các thao tác exact của `BigDecimal` bảo vệ hợp đồng chính xác: nó xuất hiện khi phép toán không thể tạo kết quả thập phân hữu hạn chính xác, hoặc khi các giới hạn scale/precision buộc phải làm tròn nhưng `RoundingMode.UNNECESSARY` cấm điều đó. Hãy phân biệt **scale** với **precision**, chọn overload của `divide` tường minh, xác định chính sách làm tròn từ yêu cầu nghiệp vụ, và chỉ xem việc bắt ngoại lệ là bước xử lý có chủ đích sau khi đã hiểu nguyên nhân.
