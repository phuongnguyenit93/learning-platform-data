# `RoundingMode.UNNECESSARY`: yêu cầu kết quả không cần làm tròn trong Java

## 1. Vì sao cần chế độ “không cho phép làm tròn”?

Khi làm việc với `BigDecimal`, lập trình viên thường chỉ định **scale** (số chữ số sau dấu thập phân) hoặc **precision** (số chữ số có nghĩa). Nếu kết quả chính xác có nhiều chữ số hơn mức được yêu cầu, phép tính cần loại bỏ hoặc thay đổi chữ số. Khi đó, một chế độ như `HALF_UP` hoặc `HALF_EVEN` sẽ quyết định cách làm tròn.

**`RoundingMode.UNNECESSARY` có ý nghĩa khác:** tuyên bố rằng thao tác **phải thực hiện được mà không thay đổi giá trị toán học**. Nếu không thể thỏa ràng buộc scale/precision mà vẫn giữ nguyên giá trị, `BigDecimal` ném `ArithmeticException` thay vì âm thầm làm tròn.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal exact = new BigDecimal("12.3400");
BigDecimal a = exact.setScale(2, RoundingMode.UNNECESSARY); // 12.34
BigDecimal b = exact.setScale(5, RoundingMode.UNNECESSARY); // 12.34000

// Khi chạy sẽ ném ArithmeticException vì phải bỏ chữ số 5:
BigDecimal c = new BigDecimal("12.345")
        .setScale(2, RoundingMode.UNNECESSARY);
~~~

Các dòng trên là **đoạn mã minh họa**, đặt vào phương thức hoặc chương trình thích hợp. Bản chạy độc lập có ở phần 6.

Điểm cốt lõi: `UNNECESSARY` **không có nghĩa là bỏ qua bước xử lý, không có nghĩa là giữ nguyên chuỗi đầu vào và cũng không tự bảo đảm phép toán luôn thành công**. Nó là một **điều kiện kiểm tra tính chính xác** của phép toán dưới ràng buộc đã yêu cầu. `BigDecimal` vẫn có thể thay đổi cách biểu diễn, thêm hoặc bớt các số 0 tận cùng, miễn giá trị không đổi.

## 2. Nền tảng: giá trị, scale và precision của `BigDecimal`

`BigDecimal` lưu một **unscaled value** là số nguyên, kết hợp với một **scale** nguyên:

~~~text
giá trị = unscaledValue × 10^(-scale)
~~~

Ví dụ:

| `BigDecimal` tạo từ chuỗi | Unscaled value | Scale | Precision |
| --- | ---: | ---: | ---: |
| `"12.34"` | 1234 | 2 | 4 |
| `"12.3400"` | 123400 | 4 | 6 |
| `"0.00120"` | 120 | 5 | 3 |
| `"1200"` | 1200 | 0 | 4 |

**Scale** là vị trí dấu thập phân theo biểu diễn hiện tại; scale có thể âm (ví dụ scale = -2 biểu thị bội số của 100). **Precision** là số chữ số thập phân của unscaled value khi bỏ dấu; nó không đồng nghĩa với số chữ số sau dấu thập phân.

`new BigDecimal("12.3400")` và `new BigDecimal("12.34")` có **giá trị số học bằng nhau**, nhưng scale/precision ban đầu khác nhau. Vì vậy:

- `compareTo()` cho kết quả 0 khi hai `BigDecimal` có cùng giá trị toán học.
- `equals()` còn xét scale nên hai đối tượng trên **không bằng nhau theo `equals`**.
- `setScale(2, UNNECESSARY)` có thể biến `12.3400` thành `12.34` vì chỉ loại bỏ các chữ số 0 không ảnh hưởng giá trị.

Ví dụ `setScale(5, UNNECESSARY)` lại thêm số 0 để tạo `12.34000`, vẫn là một phép chuyển đổi **chính xác**. Do đó “không cần làm tròn” khác với “không được thay đổi cách hiển thị”.

## 3. `setScale(..., RoundingMode.UNNECESSARY)`: kiểm tra biểu diễn chính xác ở scale mong muốn

Phương thức:

~~~java
BigDecimal result = value.setScale(targetScale, RoundingMode.UNNECESSARY);
~~~

yêu cầu biểu diễn giá trị bằng đúng `targetScale`. Có ba tình huống:

1. **Tăng scale:** thêm chữ số 0 ở phần thập phân để giữ nguyên giá trị, nên có thể thực hiện chính xác.
2. **Giảm scale nhưng chỉ bỏ số 0 tận cùng:** vẫn chính xác, thành công.
3. **Giảm scale và phải bỏ chữ số khác 0:** không thể giữ nguyên giá trị; ném `ArithmeticException`.

| Giá trị đầu vào | Yêu cầu | Kết quả |
| --- | --- | --- |
| `12.34` | `setScale(4, UNNECESSARY)` | `12.3400` |
| `12.3400` | `setScale(2, UNNECESSARY)` | `12.34` |
| `12.345` | `setScale(2, UNNECESSARY)` | `ArithmeticException` |
| `1000` | `setScale(-2, UNNECESSARY)` | `1.0E+3` (scale = -2) |
| `1250` | `setScale(-2, UNNECESSARY)` | `ArithmeticException` |

Ở hai hàng cuối, scale = -2 yêu cầu giá trị là bội số chính xác của **100**: `1000` chia hết cho 100, còn `1250` thì không. Dạng chuỗi `1.0E+3` chỉ là cách `BigDecimal.toString()` biểu diễn `1000` có scale -2.

Cùng phép chuyển `12.345` xuống 2 chữ số, các chế độ làm tròn khác có thể tạo `12.35` hoặc `12.34`, tùy quy tắc; `UNNECESSARY` chọn **báo lỗi** để người gọi không nhầm kết quả đã bị sửa.

### 3.1. Ứng dụng: xác minh dữ liệu có đúng số chữ số thập phân được phép

Giả sử một hệ thống chỉ nhận tiền có tối đa hai chữ số sau dấu chấm, nhưng phải bảo toàn giá trị khách hàng nhập:

~~~java
public static BigDecimal requireTwoDecimalPlaces(String input) {
    return new BigDecimal(input)
            .setScale(2, RoundingMode.UNNECESSARY);
}
~~~

Đây là phương thức cần đặt trong một class đã import `java.math.BigDecimal` và `java.math.RoundingMode`.

- `"19"` → `19.00`.
- `"19.2"` → `19.20`.
- `"19.2000"` → `19.20`: các số 0 dư không đổi giá trị.
- `"19.201"` → `ArithmeticException`: không thể biểu diễn chính xác ở scale 2.

Đó là kiểm tra **khả năng biểu diễn chính xác ở scale 2**, không phải kiểm tra **chuỗi gốc có đúng hai chữ số**. Nếu yêu cầu dữ liệu là đúng hai chữ số được nhập, phải xác minh định dạng chuỗi riêng. Ngoài ra, chính sách tiền tệ thực tế có thể còn cần ràng buộc số âm, miền giá trị, currency và các quy tắc nghiệp vụ.

## 4. `MathContext` và precision: làm tròn theo số chữ số có nghĩa

`MathContext` gồm precision và rounding mode. Ví dụ:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

MathContext exactThreeDigits =
        new MathContext(3, RoundingMode.UNNECESSARY);

BigDecimal x = new BigDecimal("123.00").round(exactThreeDigits);
// x = 123: bỏ 2 chữ số 0 tận cùng nhưng không đổi giá trị.

// Ném ArithmeticException: không thể biểu diễn chính xác
// giá trị 123.40 bằng tối đa 3 chữ số có nghĩa.
BigDecimal y = new BigDecimal("123.40").round(exactThreeDigits);
~~~

`MathContext(3, UNNECESSARY)` yêu cầu kết quả vừa có **tối đa 3 chữ số có nghĩa** vừa **không mất giá trị**. Nó không yêu cầu “giữ đúng 3 chữ số sau dấu thập phân”. Chẳng hạn, `123.00` giảm được xuống `123` mà vẫn đúng, còn `123.40` cần bốn chữ số có nghĩa để giữ chính xác giá trị `123.4`.

Một số phép tính như `add`, `subtract`, `multiply`, `divide` có overload nhận `MathContext`. Khi cần thu kết quả về precision đã cho, chúng thực hiện kiểm tra tương tự. Với `UNNECESSARY`, nếu kết quả chính xác cần nhiều chữ số có nghĩa hơn và không thể giảm bằng cách bỏ các số 0 không ảnh hưởng giá trị, thao tác sẽ thất bại.

### 4.1. Precision = 0 là trường hợp đặc biệt

~~~java
MathContext unlimited =
        new MathContext(0, RoundingMode.UNNECESSARY);
~~~

Trong `MathContext`, **precision = 0 nghĩa là không giới hạn độ chính xác**. Khi đó chế độ rounding không tác động đến việc giới hạn số chữ số có nghĩa, vì không có giới hạn nào được đặt ra. Tuy nhiên, điều này **không khiến phép chia có phần thập phân vô hạn tự trở nên biểu diễn được**: `1 / 3` vẫn không có kết quả `BigDecimal` chính xác với hữu hạn chữ số.

`MathContext.UNLIMITED` là hằng có precision 0 và rounding mode `HALF_UP`; trong các phép toán không cần giới hạn precision, rounding mode của nó không tạo ra khác biệt. Đừng hiểu `MathContext.UNLIMITED` là vô hiệu hóa mọi lỗi số học (ví dụ chia cho 0 và phép chia không kết thúc vẫn lỗi).

## 5. Phép chia: nơi `UNNECESSARY` thường tạo lỗi khó hiểu

### 5.1. Phân biệt ba overload của `divide`

| Cách gọi | Ràng buộc kết quả | Điều gì xảy ra nếu không thể chính xác? |
| --- | --- | --- |
| `a.divide(b)` | Kết quả chính xác với biểu diễn thập phân hữu hạn | `ArithmeticException` khi phép chia không kết thúc, ví dụ `1/3` |
| `a.divide(b, scale, UNNECESSARY)` | Kết quả đúng scale đã chỉ định, không làm tròn | `ArithmeticException` nếu chữ số cần bỏ khác 0 |
| `a.divide(b, mathContextWithUNNECESSARY)` | Kết quả đúng giới hạn precision, không làm tròn | `ArithmeticException` nếu phải làm tròn hoặc kết quả không biểu diễn chính xác được ở precision đó |

Một overload khác, `a.divide(b, RoundingMode.UNNECESSARY)`, dùng **scale của `a`** làm scale kết quả, dễ gây bất ngờ. Ví dụ `new BigDecimal("10").divide(new BigDecimal("4"), RoundingMode.UNNECESSARY)` sẽ lỗi vì scale của `10` là 0, dù giá trị chia chính xác `2.5` có thể được lưu bằng `BigDecimal`. Nếu muốn kết quả scale 1, phải gọi overload có tham số scale tường minh.

### 5.2. “Chia chính xác” khác “chia chính xác ở scale/precision được yêu cầu”

~~~java
BigDecimal ten = new BigDecimal("10");
BigDecimal four = new BigDecimal("4");

// Chính xác ở scale 1:
BigDecimal ok = ten.divide(four, 1, RoundingMode.UNNECESSARY);
// ok = 2.5

// Không thể chính xác ở scale 0:
BigDecimal fail = ten.divide(four, 0, RoundingMode.UNNECESSARY);
// ArithmeticException
~~~

`10 ÷ 4 = 2.5` là giá trị **hoàn toàn biểu diễn được bằng số thập phân hữu hạn**, nhưng không phải bằng scale 0. Đây là lỗi do **ràng buộc biểu diễn**, không phải do phép chia “vốn không chính xác”.

Với precision thì tương tự:

~~~java
MathContext p3 = new MathContext(3, RoundingMode.UNNECESSARY);

BigDecimal ok = BigDecimal.ONE.divide(new BigDecimal("8"), p3);
// 0.125 có 3 chữ số có nghĩa: thành công.

BigDecimal fail = BigDecimal.ONE.divide(new BigDecimal("32"), p3);
// 0.03125 có 4 chữ số có nghĩa: ArithmeticException.
~~~

### 5.3. Phép chia có thập phân vô hạn

`1 / 3 = 0.3333...` không thể ghi chính xác bằng một `BigDecimal` có hữu hạn chữ số thập phân:

~~~java
BigDecimal a = BigDecimal.ONE;
BigDecimal b = new BigDecimal("3");

// Cả hai đều không thể trả về BigDecimal chính xác:
a.divide(b);
a.divide(b, new MathContext(20, RoundingMode.UNNECESSARY));
~~~

Trong hai dòng trên, lỗi phát sinh tại phép chia được thực thi đầu tiên; để kiểm tra dòng thứ hai riêng, đặt các dòng trong những khối `try/catch` độc lập.

Một phân số tối giản `n/d` có biểu diễn thập phân hữu hạn khi **mẫu d chỉ có các thừa số nguyên tố 2 và 5**. Ví dụ `1/8 = 0.125`, `1/20 = 0.05` hữu hạn; `1/3`, `1/6` không hữu hạn. Tiêu chí này áp dụng sau khi rút gọn phân số, với mẫu là số nguyên dương.

Nếu yêu cầu nghiệp vụ **cho phép làm tròn**, hãy chọn một scale hoặc precision và chế độ làm tròn có chủ đích, ví dụ:

~~~java
BigDecimal oneThird = BigDecimal.ONE.divide(
        new BigDecimal("3"), 2, RoundingMode.HALF_UP);
// oneThird = 0.33, là giá trị xấp xỉ.
~~~

Nếu nghiệp vụ **cấm làm tròn**, giữ `UNNECESSARY` và xử lý lỗi như tín hiệu dữ liệu hoặc kỳ vọng phép toán chưa đáp ứng điều kiện, thay vì tự đổi sang `HALF_UP`.

## 6. Chương trình Java 17+ có thể biên dịch và chạy

Tạo tệp **UnnecessaryDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class UnnecessaryDemo {
    private static void attempt(String label, Runnable calculation) {
        try {
            calculation.run();
        } catch (ArithmeticException ex) {
            System.out.println(label + " -> ArithmeticException");
        }
    }

    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("12.3400");

        System.out.println("scale down exact: "
                + amount.setScale(2, RoundingMode.UNNECESSARY));
        System.out.println("scale up exact: "
                + amount.setScale(5, RoundingMode.UNNECESSARY));

        attempt("scale down inexact", () ->
                System.out.println(new BigDecimal("12.345")
                        .setScale(2, RoundingMode.UNNECESSARY)));

        System.out.println("divide exact scale: "
                + new BigDecimal("10").divide(
                        new BigDecimal("4"), 1, RoundingMode.UNNECESSARY));

        attempt("divide inexact scale", () ->
                System.out.println(new BigDecimal("10").divide(
                        new BigDecimal("4"), 0, RoundingMode.UNNECESSARY)));

        MathContext precision3 =
                new MathContext(3, RoundingMode.UNNECESSARY);
        System.out.println("precision exact: "
                + new BigDecimal("123.00").round(precision3));

        attempt("precision inexact", () ->
                System.out.println(new BigDecimal("123.40")
                        .round(precision3)));

        System.out.println("exact division: "
                + BigDecimal.ONE.divide(new BigDecimal("8")));

        attempt("nonterminating division", () ->
                System.out.println(BigDecimal.ONE.divide(
                        new BigDecimal("3"), precision3)));

        System.out.println("exact precision division: "
                + BigDecimal.ONE.divide(new BigDecimal("8"), precision3));

        attempt("precision division", () ->
                System.out.println(BigDecimal.ONE.divide(
                        new BigDecimal("32"), precision3)));

        MathContext unlimited =
                new MathContext(0, RoundingMode.UNNECESSARY);
        System.out.println("unlimited division: "
                + BigDecimal.ONE.divide(new BigDecimal("32"), unlimited));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac UnnecessaryDemo.java
java UnnecessaryDemo
~~~

Đầu ra:

~~~text
scale down exact: 12.34
scale up exact: 12.34000
scale down inexact -> ArithmeticException
divide exact scale: 2.5
divide inexact scale -> ArithmeticException
precision exact: 123
precision inexact -> ArithmeticException
exact division: 0.125
nonterminating division -> ArithmeticException
exact precision division: 0.125
precision division -> ArithmeticException
unlimited division: 0.03125
~~~

Trong chương trình, `attempt` bắt `ArithmeticException` nhằm cho phép các trường hợp khác tiếp tục chạy sau một phép tính cố ý sai ràng buộc. Ứng dụng thực tế nên có chính sách xử lý lỗi phù hợp, tránh che lỗi hoặc trả một giá trị thay thế tùy tiện.

## 7. Dùng `UNNECESSARY` ở đâu?

### 7.1. Kiểm tra dữ liệu trước khi lưu

Nếu cơ sở dữ liệu sử dụng `DECIMAL(12, 2)` và nghiệp vụ yêu cầu không làm mất phần lẻ, có thể dùng:

~~~java
BigDecimal normalized =
        input.setScale(2, RoundingMode.UNNECESSARY);
~~~

Sau đó **vẫn phải kiểm tra giới hạn độ lớn/số chữ số nguyên** để phù hợp precision của cột và các quy tắc nghiệp vụ khác. `setScale(2, UNNECESSARY)` chỉ chứng minh rằng giá trị có thể được biểu diễn đúng ở scale 2; nó không chứng minh giá trị vừa vào mọi cột hoặc nằm trong miền hợp lệ.

### 7.2. Phân phối số lượng nguyên

Nếu chia một tổng đơn vị nguyên thành các phần và bắt buộc không còn phần dư, có thể dùng `divide(..., 0, UNNECESSARY)` để yêu cầu thương nguyên chính xác. Ví dụ `10 / 2` thành công ở scale 0, còn `10 / 4` báo lỗi vì thương 2.5 không nguyên. Nếu muốn kiểm tra tính chia hết của **số nguyên**, `BigInteger.divideAndRemainder` hoặc phép chia và phần dư nguyên có thể diễn đạt ý định rõ ràng hơn.

### 7.3. Kiểm tra bất biến trong tính toán

Trong một chuỗi phép tính mà phần nghiệp vụ xác nhận **không được mất chữ số**, `UNNECESSARY` biến giả định “chắc chắn chia/chuẩn hóa chính xác được” thành điều kiện được kiểm tra ở runtime. Điều này đặc biệt hữu ích ở **ranh giới dữ liệu**: trước khi lưu, gửi API hoặc chuyển sang scale chuẩn.

Tuy nhiên, `UNNECESSARY` không loại bỏ sai số đã phát sinh từ nguồn dữ liệu trước đó. Ví dụ, `new BigDecimal(0.1)` mang chính xác giá trị nhị phân của literal `double` 0.1 sau khi đã làm tròn theo IEEE 754, không mang chính xác số thập phân 0.1 kỳ vọng. Khi cần dữ liệu thập phân đúng theo văn bản, ưu tiên `new BigDecimal("0.1")` hoặc một nguồn thập phân có kiểm soát. Nếu thật sự bắt đầu bằng `double`, `BigDecimal.valueOf(0.1)` dùng biểu diễn thập phân chuẩn của giá trị double và thường phù hợp hơn constructor nhận double, nhưng không phục hồi số thập phân gốc chưa biết.

## 8. Các ngoại lệ và hiểu lầm cần tránh

| Hiểu lầm | Điều đúng |
| --- | --- |
| `UNNECESSARY` nghĩa là “đừng làm gì” | API vẫn đổi scale/precision khi đổi được mà không mất giá trị |
| Có `UNNECESSARY` thì kết quả phải thành công | Nó ném `ArithmeticException` nếu cần làm tròn |
| `setScale(2, UNNECESSARY)` bắt chuỗi nhập phải có đúng 2 chữ số sau dấu chấm | Nó kiểm tra **giá trị** có thể biểu diễn chính xác ở scale 2 |
| Precision = 2 tương đương scale = 2 | Precision đếm chữ số có nghĩa; scale chỉ vị trí dấu thập phân |
| Mọi phép chia hữu hạn đều thành công ở bất kỳ scale nào | `10/4` hữu hạn nhưng không biểu diễn chính xác ở scale 0 |
| `MathContext(0, UNNECESSARY)` khiến `1/3` biểu diễn chính xác | Precision không giới hạn vẫn không tạo được một số thập phân hữu hạn bằng `1/3` |
| `BigDecimal.divide(BigDecimal, UNNECESSARY)` không đặt scale | Overload này dùng **scale của số bị chia** |
| `UNNECESSARY` tự kiểm tra miền giá trị, định dạng hoặc tính hợp lệ nghiệp vụ | Nó chỉ kiểm tra **nhu cầu làm tròn** trong thao tác đang gọi |

Lưu ý thêm: **không phải mọi `ArithmeticException` đều do `UNNECESSARY`**. Chia cho số 0 cũng ném `ArithmeticException`; vì vậy khi ghi log và phản hồi lỗi nghiệp vụ cần phân biệt dữ liệu đầu vào, phép toán được gọi và ràng buộc mong muốn, thay vì mặc định mọi lỗi đều mang nghĩa “cần làm tròn”.

## 9. Tự kiểm tra kiến thức

1. `new BigDecimal("5.000").setScale(0, UNNECESSARY)` có thành công không? **Có**, kết quả `5` vì chỉ bỏ số 0 dư.
2. `new BigDecimal("5.001").setScale(2, UNNECESSARY)` có thành công không? **Không**, vì `5.001` không thể giữ nguyên khi chỉ còn 2 chữ số sau dấu chấm.
3. `new BigDecimal("1").divide(new BigDecimal("8"), 2, UNNECESSARY)` thế nào? **Ném `ArithmeticException`**, vì `0.125` không thể chính xác ở scale 2.
4. Cùng phép chia đó với `scale = 3` thì sao? **Thành công**, kết quả `0.125`.
5. `new BigDecimal("123.00").round(new MathContext(3, UNNECESSARY))` thế nào? **Thành công**, kết quả `123` vì có thể bỏ các số 0 dư mà vẫn bảo toàn giá trị.
6. Khi nào nên dùng `HALF_EVEN` hoặc `HALF_UP`? **Khi nghiệp vụ chủ động cho phép làm tròn** và đã chỉ rõ quy tắc. Khi yêu cầu tuyệt đối không đổi giá trị, dùng `UNNECESSARY` để phát hiện vi phạm.

**Ghi nhớ:** `RoundingMode.UNNECESSARY` là cách diễn đạt yêu cầu **“kết quả ở scale/precision này phải chính xác, nếu không hãy báo lỗi”**. Muốn dùng đúng, trước tiên xác định mình đang giới hạn **scale** hay **precision**, sau đó dự kiến và xử lý `ArithmeticException` khi ràng buộc không thể được đáp ứng.