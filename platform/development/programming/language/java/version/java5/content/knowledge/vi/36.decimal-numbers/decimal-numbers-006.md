# UNNECESSARY và trường hợp phát sinh ArithmeticException

## 1. UNNECESSARY thể hiện một điều kiện bắt buộc

Khi xử lý số thập phân, đôi khi yêu cầu không phải “hãy chọn số gần nhất”, mà là **“chỉ chấp nhận nếu kết quả biểu diễn chính xác được; nếu phải làm tròn thì báo lỗi”**.

`RoundingMode.UNNECESSARY` thể hiện điều kiện đó. Nó không chọn một giá trị xấp xỉ, cũng không âm thầm bỏ các chữ số dư.

Ví dụ, hệ thống yêu cầu một giá trị có thể biểu diễn chính xác với hai chữ số sau dấu thập phân:

- `18.2500` chuyển được thành `18.25` mà không thay đổi giá trị.
- `18.25` đã đáp ứng yêu cầu.
- `18.251` không thể chuyển về hai chữ số sau dấu thập phân mà vẫn giữ nguyên giá trị.

Trường hợp cuối phát sinh `ArithmeticException` khi gọi `setScale(2, RoundingMode.UNNECESSARY)`. Định nghĩa chính thức của chế độ này nằm trong [Java API: RoundingMode.UNNECESSARY](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/RoundingMode.html#UNNECESSARY).

Điểm cần giữ trong đầu: **thay đổi biểu diễn không đồng nghĩa với thay đổi giá trị số học**. Bỏ các số 0 ở cuối hoặc thêm số 0 có thể hoàn toàn chính xác.

## 2. Quan hệ giữa vị trí biểu diễn và tính chính xác

Một chế độ làm tròn luôn đi cùng một giới hạn do phép toán quy định. Hai giới hạn thường gặp là:

| Giới hạn | API thường dùng | Ý nghĩa |
|---|---|---|
| Scale | `setScale(scale, mode)` | Quy định vị trí thập phân; scale dương là số chữ số sau dấu thập phân |
| Precision | `round(MathContext)`, phép toán nhận `MathContext` | Giới hạn tổng số chữ số có nghĩa |

`UNNECESSARY` không tự quyết định một trong hai giới hạn này. Cần đọc toàn bộ lời gọi để biết điều kiện chính xác đang được áp dụng ở đâu.

Ví dụ, `123.45` biểu diễn chính xác được với scale 2 nhưng không thể biểu diễn chính xác bằng tổng cộng bốn chữ số có nghĩa. Do đó:

```java
BigDecimal value = new BigDecimal("123.45");

value.setScale(2, RoundingMode.UNNECESSARY); // Thành công.
value.round(new MathContext(4, RoundingMode.UNNECESSARY)); // ArithmeticException.
```

Đây là đoạn mã minh họa nằm trong một phương thức; cần import `java.math.BigDecimal`, `java.math.MathContext` và `java.math.RoundingMode`. Dòng cuối cố ý gây lỗi nên nếu chạy trực tiếp mà không bắt ngoại lệ, chương trình sẽ dừng tại đó.

## 3. Khi nào setScale thành công, khi nào báo lỗi?

### 3.1. Giảm scale nhưng chỉ bỏ số 0

```java
BigDecimal source = new BigDecimal("18.2500");
BigDecimal normalized = source.setScale(2, RoundingMode.UNNECESSARY);

System.out.println(normalized.toPlainString()); // 18.25
System.out.println(source.toPlainString());     // 18.2500
```

Phần bị bỏ là `00`, nên giá trị được giữ nguyên. `BigDecimal` bất biến: `source` không bị sửa. Phải sử dụng đối tượng được trả về nếu muốn lưu biểu diễn mới.

Không nên kiểm tra đơn giản `source.scale() > 2` rồi kết luận đầu vào không hợp lệ. Điều đó sẽ từ chối cả `18.2500`, trong khi giá trị này biểu diễn chính xác được với scale 2.

Nếu yêu cầu là kiểm soát **cách người dùng viết dữ liệu**, chẳng hạn cấm nhập quá hai chữ số sau dấu chấm kể cả số 0, cần kiểm tra cú pháp/văn bản đầu vào riêng. `UNNECESSARY` kiểm tra khả năng biểu diễn chính xác của giá trị.

### 3.2. Giảm scale và phải bỏ phần khác 0

```java
new BigDecimal("18.2501").setScale(2, RoundingMode.UNNECESSARY);
```

Biểu thức này phát sinh `ArithmeticException`: không có giá trị nào ở scale 2 bằng chính xác `18.2501`.

Điều này cũng đúng với số âm. `-18.2501` không thể được giữ nguyên giá trị ở scale 2. `UNNECESSARY` không có quy tắc phân xử theo dấu như các chế độ làm tròn theo hướng.

Cũng không có ngưỡng “phần dư quá nhỏ nên bỏ qua”. Nếu phần bị loại bỏ khác 0, dù rất nhỏ, điều kiện chính xác vẫn bị vi phạm:

```java
new BigDecimal("18.2500000001")
        .setScale(2, RoundingMode.UNNECESSARY); // ArithmeticException.
```

### 3.3. Tăng scale

Chuyển `18.25` sang scale 4 cho `18.2500`. Không phải thay đổi giá trị, nên `UNNECESSARY` chấp nhận.

```java
BigDecimal expanded = new BigDecimal("18.25")
        .setScale(4, RoundingMode.UNNECESSARY);
System.out.println(expanded.toPlainString()); // 18.2500
```

Trong các ví dụ có scale thông thường này, thêm số 0 là chính xác. Điều đó không có nghĩa mọi scale cực lớn tùy ý đều có thể được xử lý mà không gặp giới hạn tài nguyên hoặc phạm vi biểu diễn của API.

### 3.4. Scale âm cũng tuân theo điều kiện chính xác

Scale `-1` đặt vị trí biểu diễn ở hàng chục:

- `120` chuyển được về scale `-1`: giá trị vẫn là `120`.
- `121` không chuyển chính xác được về scale `-1`, nên phát sinh ngoại lệ.

```java
BigDecimal exactTens = new BigDecimal("120")
        .setScale(-1, RoundingMode.UNNECESSARY);
System.out.println(exactTens.toPlainString()); // 120
```

Dạng chuỗi thông thường của kết quả có thể dùng số mũ; `toPlainString()` giúp nhìn rõ giá trị khi học và đối chiếu.

Các hợp đồng thao tác scale và các ngoại lệ tương ứng được mô tả trong [Java API: BigDecimal.setScale](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigDecimal.html#setScale(int,java.math.RoundingMode)).

## 4. MathContext với UNNECESSARY

`MathContext` kết hợp precision và chế độ làm tròn. Chẳng hạn:

```java
MathContext exactThreeDigits =
        new MathContext(3, RoundingMode.UNNECESSARY);
```

Context này yêu cầu kết quả của phép toán nhận nó phải biểu diễn chính xác được với tối đa ba chữ số có nghĩa. Nó không có nghĩa là ba chữ số sau dấu thập phân.

### 4.1. Xét kết quả toán học, không chỉ đếm ký tự đầu vào

Ví dụ:

| Giá trị hoặc phép toán | Precision yêu cầu | Kết quả |
|---|---:|---|
| `12.300` được `round` | 3 | `12.3`, chính xác |
| `12.301` được `round` | 3 | `ArithmeticException` |
| `1.23 + 0.01` | 3 | `1.24`, chính xác |
| `95 + 6` | 2 | `ArithmeticException`, vì tổng chính xác là `101` |
| `9.99 × 9` | 3 | `ArithmeticException`, vì tích chính xác là `89.91` |

Ở hàng cộng `95 + 6`, mỗi toán hạng đều có không quá hai chữ số có nghĩa nhưng kết quả cần ba chữ số. Điều kiện được kiểm tra trên kết quả của phép toán.

Ngược lại, `12.300` có thể giảm số chữ số được lưu xuống còn ba mà không đổi giá trị. Không được chỉ so sánh `value.precision()` với precision yêu cầu rồi kết luận luôn phải mất thông tin.

Các constructor nhận `MathContext` cũng có thể phát sinh ngoại lệ khi chuỗi đầu vào biểu diễn một giá trị không thể giữ chính xác trong precision đã yêu cầu:

```java
new BigDecimal("12.34", new MathContext(3, RoundingMode.UNNECESSARY));
// ArithmeticException: giá trị 12.34 cần bốn chữ số có nghĩa.
```

### 4.2. Precision bằng 0 có ý nghĩa riêng

Precision `0` biểu thị không giới hạn precision theo cách của `MathContext`; lúc đó chế độ làm tròn không tham gia giới hạn chữ số. Nó không buộc số có 0 chữ số, cũng không có khả năng lưu một khai triển vô hạn tuần hoàn.

Ví dụ, `1 / 8` có kết quả thập phân hữu hạn `0.125`, còn `1 / 3` không có biểu diễn thập phân hữu hạn chính xác. Phép chia chính xác `1 / 3` vẫn phát sinh `ArithmeticException` với context có precision 0.

Context chỉ áp dụng khi được truyền vào đúng constructor/phương thức; nó không được gắn ngầm vào mọi phép toán sau đó. Chi tiết cấu hình nằm trong [Java API: MathContext](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/MathContext.html).

## 5. Phép chia: ba tình huống cần tách biệt

### 5.1. Có kết quả hữu hạn nhưng scale yêu cầu không đủ

`1 / 8 = 0.125` là kết quả hữu hạn. Tuy nhiên:

```java
BigDecimal.ONE.divide(new BigDecimal("8"), 2, RoundingMode.UNNECESSARY);
// ArithmeticException.

BigDecimal.ONE.divide(new BigDecimal("8"), 3, RoundingMode.UNNECESSARY);
// 0.125.
```

Ngoại lệ ở dòng đầu không có nghĩa phép chia là vô hạn tuần hoàn. Nó chỉ cho biết kết quả không thể được biểu diễn chính xác tại scale 2 đã yêu cầu.

Với overload chỉ truyền `divisor` và `RoundingMode`, scale kết quả là scale của số bị chia:

```java
BigDecimal.ONE.divide(new BigDecimal("8"), RoundingMode.UNNECESSARY);
// ArithmeticException, vì BigDecimal.ONE có scale 0.

new BigDecimal("1.000").divide(
        new BigDecimal("8"), RoundingMode.UNNECESSARY);
// 0.125, vì số bị chia có scale 3.
```

Nếu yêu cầu là một số chữ số thập phân xác định, truyền scale rõ ràng sẽ giúp hợp đồng dễ đọc và ổn định khi biểu diễn toán hạng thay đổi.

### 5.2. Kết quả không có khai triển thập phân hữu hạn

`1 / 3` không thể biểu diễn chính xác bằng một `BigDecimal` hữu hạn. Vì thế các cách sau đều không trả về giá trị xấp xỉ:

```java
BigDecimal.ONE.divide(new BigDecimal("3"));

BigDecimal.ONE.divide(
        new BigDecimal("3"), 20, RoundingMode.UNNECESSARY);

BigDecimal.ONE.divide(
        new BigDecimal("3"), new MathContext(20, RoundingMode.UNNECESSARY));
```

Mỗi biểu thức đều phát sinh `ArithmeticException`. Dòng đầu không truyền `UNNECESSARY` nhưng vẫn yêu cầu kết quả chia chính xác.

Tăng scale hoặc precision từ 20 lên một con số hữu hạn lớn hơn không biến `1/3` thành số thập phân hữu hạn chính xác. Nếu ứng dụng cho phép xấp xỉ, cần một chính sách làm tròn được xác định rõ. Nếu ứng dụng phải giữ phân số chính xác, cần mô hình phù hợp với tử số/mẫu số thay vì mong một `BigDecimal` hữu hạn chứa được mọi phân số.

### 5.3. Chia cho 0

Chia cho 0 cũng gây `ArithmeticException`, kể cả khi chọn một chế độ cho phép xấp xỉ như `HALF_UP`.

Vì vậy, nhìn thấy kiểu ngoại lệ này chưa đủ để kết luận rằng `UNNECESSARY` đã bị vi phạm. Cần xem phép toán và dữ liệu đã dẫn đến lỗi.

Không thay chế độ làm tròn để “chữa” một số chia bằng 0. Đây là nguyên nhân khác hoàn toàn.

## 6. Chương trình chạy đầy đủ

Lưu thành `UnnecessaryDemo.java`. Mỗi trường hợp được chạy riêng để một ngoại lệ không ngăn các trường hợp sau tiếp tục.

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;
import java.util.function.Supplier;

public class UnnecessaryDemo {
    private static final RoundingMode EXACT = RoundingMode.UNNECESSARY;

    private static void check(String label, Supplier<BigDecimal> operation) {
        try {
            BigDecimal result = operation.get();
            System.out.println(label + " -> " + result.toPlainString());
        } catch (ArithmeticException exception) {
            System.out.println(label + " -> ArithmeticException");
        }
    }

    public static void main(String[] args) {
        MathContext three = new MathContext(3, EXACT);
        MathContext unlimited = new MathContext(0, EXACT);

        check("drop zeros",
                () -> new BigDecimal("18.2500").setScale(2, EXACT));
        check("drop nonzero",
                () -> new BigDecimal("18.2501").setScale(2, EXACT));
        check("negative nonzero",
                () -> new BigDecimal("-18.2501").setScale(2, EXACT));
        check("add zeros",
                () -> new BigDecimal("18.25").setScale(4, EXACT));
        check("exact tens",
                () -> new BigDecimal("120").setScale(-1, EXACT));
        check("inexact tens",
                () -> new BigDecimal("121").setScale(-1, EXACT));

        check("precision exact",
                () -> new BigDecimal("12.300").round(three));
        check("precision inexact",
                () -> new BigDecimal("12.301").round(three));
        check("addition exact",
                () -> new BigDecimal("1.23").add(new BigDecimal("0.01"), three));
        check("addition inexact",
                () -> new BigDecimal("95").add(new BigDecimal("6"),
                        new MathContext(2, EXACT)));
        check("multiplication inexact",
                () -> new BigDecimal("9.99").multiply(new BigDecimal("9"), three));
        check("constructor inexact",
                () -> new BigDecimal("12.34", three));

        check("1/8 scale 2",
                () -> BigDecimal.ONE.divide(new BigDecimal("8"), 2, EXACT));
        check("1/8 scale 3",
                () -> BigDecimal.ONE.divide(new BigDecimal("8"), 3, EXACT));
        check("1/8 implicit scale 0",
                () -> BigDecimal.ONE.divide(new BigDecimal("8"), EXACT));
        check("1.000/8 implicit scale 3",
                () -> new BigDecimal("1.000").divide(new BigDecimal("8"), EXACT));
        check("1/3 exact divide",
                () -> BigDecimal.ONE.divide(new BigDecimal("3")));
        check("1/8 unlimited",
                () -> BigDecimal.ONE.divide(new BigDecimal("8"), unlimited));
        check("1/3 unlimited",
                () -> BigDecimal.ONE.divide(new BigDecimal("3"), unlimited));
        check("divide by zero with HALF_UP",
                () -> BigDecimal.ONE.divide(BigDecimal.ZERO, 2,
                        RoundingMode.HALF_UP));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 UnnecessaryDemo.java
java UnnecessaryDemo
```

Stdout:

```text
drop zeros -> 18.25
drop nonzero -> ArithmeticException
negative nonzero -> ArithmeticException
add zeros -> 18.2500
exact tens -> 120
inexact tens -> ArithmeticException
precision exact -> 12.3
precision inexact -> ArithmeticException
addition exact -> 1.24
addition inexact -> ArithmeticException
multiplication inexact -> ArithmeticException
constructor inexact -> ArithmeticException
1/8 scale 2 -> ArithmeticException
1/8 scale 3 -> 0.125
1/8 implicit scale 0 -> ArithmeticException
1.000/8 implicit scale 3 -> 0.125
1/3 exact divide -> ArithmeticException
1/8 unlimited -> 0.125
1/3 unlimited -> ArithmeticException
divide by zero with HALF_UP -> ArithmeticException
```

Chương trình chủ động in tên kiểu ngoại lệ thay vì nội dung `getMessage()`. Không dùng chuỗi thông báo chi tiết của JDK làm hợp đồng nghiệp vụ hoặc điều kiện rẽ nhánh.

## 7. Dùng UNNECESSARY để bảo vệ một ranh giới dữ liệu

Giả sử một hàm chỉ chấp nhận giá trị có thể lưu chính xác với hai chữ số sau dấu thập phân. Có thể đưa việc chuẩn hóa vào một hàm nhỏ:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public final class DecimalInput {
    private DecimalInput() {
    }

    public static BigDecimal requireScaleTwo(BigDecimal value) {
        Objects.requireNonNull(value, "value");

        try {
            return value.setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException exception) {
            throw new IllegalArgumentException(
                    "Gia tri phai bieu dien chinh xac duoc voi scale 2",
                    exception);
        }
    }
}
```

Đây là một lớp hoàn chỉnh lưu được thành `DecimalInput.java`, nhưng không có `main` để tự chạy. Ví dụ sử dụng trong một phương thức khác:

```java
BigDecimal accepted = DecimalInput.requireScaleTwo(new BigDecimal("3.4000"));
// accepted có biểu diễn 3.40.

DecimalInput.requireScaleTwo(new BigDecimal("3.4001"));
// IllegalArgumentException; nguyên nhân được giữ lại là ArithmeticException.
```

Hàm bắt ngoại lệ trong phạm vi hẹp của đúng `setScale`, rồi chuyển thành lỗi đầu vào có ngữ nghĩa rõ hơn. Nó không bao trùm một chuỗi gồm parse, chia, ghi dữ liệu và nhiều phép tính khác trong cùng một khối `try`.

Lựa chọn trả lỗi, ném ngoại lệ hay trả một kiểu kết quả phụ thuộc giao diện ứng dụng. Điều cốt yếu là giữ nguyên hợp đồng: đầu vào không đáp ứng không được tự động làm tròn thành một giá trị khác.

Nếu muốn kiểm tra dữ liệu có quá hai chữ số sau dấu chấm **về mặt cú pháp**, cần một quy tắc khác. Hàm trên chấp nhận `3.4000` đúng theo mục tiêu giữ nguyên giá trị.

## 8. Phân biệt các nguyên nhân lỗi

| Tình huống | Kiểu lỗi thường liên quan | Cách hiểu |
|---|---|---|
| Cần bỏ phần khác 0 trong `setScale` với `UNNECESSARY` | `ArithmeticException` | Vi phạm yêu cầu chính xác ở scale đã chọn |
| Kết quả không vừa precision với `UNNECESSARY` | `ArithmeticException` | Vi phạm yêu cầu chính xác ở precision đã chọn |
| Chia chính xác ra khai triển vô hạn tuần hoàn | `ArithmeticException` | Không có biểu diễn thập phân hữu hạn chính xác |
| Chia cho 0 | `ArithmeticException` | Phép chia không hợp lệ |
| `new BigDecimal("abc")` | `NumberFormatException` | Văn bản không phải số thập phân hợp lệ |
| `new MathContext(-1, mode)` | `IllegalArgumentException` | Cấu hình precision không hợp lệ |
| Truyền `null` vào tham số bắt buộc | `NullPointerException` | Thiếu đối tượng đầu vào |
| `longValueExact()` với phần lẻ hoặc vượt miền `long` | `ArithmeticException` | Chuyển kiểu không chính xác hoặc vượt phạm vi |

Bảng nhằm phân biệt những trường hợp thường gặp, không phải danh sách mọi ngoại lệ có thể có của toàn bộ `BigDecimal`. Ví dụ, phạm vi scale bị vượt trong một số phép toán cũng có thể gây `ArithmeticException`.

`longValueExact()` và `intValueExact()` không nhận `RoundingMode`; chúng có hợp đồng chuyển đổi chính xác riêng. Đừng suy ra mọi phương thức phát sinh `ArithmeticException` đều đang dùng `UNNECESSARY`.

Một trình tự tìm nguyên nhân thực tế:

1. Xác định đúng phương thức phát sinh lỗi từ stack trace.
2. Kiểm tra số chia có bằng 0 nếu đang chia.
3. Xem overload nhận scale, `MathContext` hay không nhận cấu hình làm tròn.
4. Ghi nhận giá trị, scale, precision của các toán hạng liên quan.
5. Đối chiếu kết quả chính xác với giới hạn được yêu cầu.
6. Sửa dữ liệu hoặc hợp đồng tính toán theo yêu cầu; không đổi chế độ chỉ để ngoại lệ biến mất.

## 9. Những hiểu nhầm dễ dẫn đến mất dữ liệu

### “UNNECESSARY nghĩa là không quan tâm đến phần thập phân”

Sai. `DOWN` có thể cắt phần dư theo hướng về 0; `UNNECESSARY` từ chối nếu phải thay đổi giá trị. Hai lựa chọn có mục đích khác nhau.

### “Bắt lỗi rồi dùng HALF_UP là an toàn”

Cách làm này chỉ đúng nếu yêu cầu đã cho phép xấp xỉ và quy định rõ chính sách dự phòng. Nếu hàm đã cam kết giữ chính xác, tự đổi mode khi thất bại làm hỏng cam kết đó.

### “Không có ngoại lệ chứng minh dữ liệu ban đầu luôn chính xác”

Một phép `setScale` thành công chỉ xác nhận giá trị `BigDecimal` **hiện tại** biểu diễn được ở scale yêu cầu. Nó không xác minh rằng dữ liệu đã được tính, đọc hoặc chuyển đổi đúng trước đó.

Nếu một bước trước đã làm tròn `3.456` thành `3.46`, kiểm tra `3.46` bằng `UNNECESSARY` ở scale 2 sẽ thành công. Phần thông tin mất trước đó không thể được khôi phục hoặc phát hiện chỉ bằng bước kiểm tra này.

Để kiểm soát số thập phân từ văn bản, tạo `BigDecimal` trực tiếp từ chuỗi hợp lệ trước khi kiểm tra. Nếu đầu vào đi qua `double`, phép kiểm tra sẽ xét giá trị sau chuyển đổi, không phải ý định thập phân ban đầu của người nhập.

### “Phải bắt ArithmeticException ở mọi dòng”

Không cần biến mọi phép toán thành một `try/catch` riêng trong mã ứng dụng. Chọn vị trí xử lý theo ranh giới trách nhiệm: nơi tiếp nhận đầu vào, nơi thực hiện một phép tính có hợp đồng cụ thể, hoặc nơi chuyển lỗi thành phản hồi cho bên gọi. Chỉ bắt khi có cách phản hồi phù hợp; nếu không, giữ nguyên lỗi để tầng có trách nhiệm xử lý.

## 10. Thực hành dự đoán trước khi chạy

1. `new BigDecimal("-6.7000").setScale(1, UNNECESSARY)` có thành công không?
2. `new BigDecimal("6.7001").setScale(1, UNNECESSARY)` có thành công không?
3. `new BigDecimal("1000").round(new MathContext(1, UNNECESSARY))` có cần thay đổi giá trị không?
4. Vì sao `1 / 8` có thể thất bại ở scale 2 dù kết quả không tuần hoàn?
5. Vì sao tăng precision cho `1 / 3` lên một triệu vẫn không đáp ứng yêu cầu giữ chính xác bằng một `BigDecimal` hữu hạn?
6. Một hàm đã làm tròn `4.567` thành `4.57`. Sau đó `setScale(2, UNNECESSARY)` thành công. Có thể kết luận quá trình chưa mất thông tin không?

Trong các câu trên, `UNNECESSARY` viết tắt cho `RoundingMode.UNNECESSARY`.

Đáp án:

1. Thành công, kết quả `-6.7`; chỉ bỏ số 0.
2. Phát sinh `ArithmeticException`; phải bỏ phần khác 0.
3. Không cần đổi giá trị. Kết quả có thể biểu diễn với một chữ số có nghĩa và scale âm; `toPlainString()` vẫn cho `1000`.
4. `0.125` cần ba vị trí sau dấu thập phân để biểu diễn chính xác.
5. Khai triển có vô hạn chữ số; mọi precision hữu hạn đều cần xấp xỉ.
6. Không. Điều kiện chỉ kiểm tra giá trị hiện tại, không kiểm toán các phép tính trước đó.
