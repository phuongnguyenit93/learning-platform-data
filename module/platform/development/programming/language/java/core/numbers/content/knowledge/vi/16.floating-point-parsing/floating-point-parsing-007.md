# Vì sao `new BigDecimal(double)` khác `new BigDecimal(String)` trong Java

Khi viết `new BigDecimal(0.1)`, Java **không** nhận trực tiếp số thập phân “một phần mười” chính xác. Literal `0.1` được trình biên dịch xử lý thành một giá trị `double` nhị phân trước, và constructor nhận `double` sẽ chuyển **chính xác giá trị nhị phân đã lưu đó** sang biểu diễn thập phân của `BigDecimal`. Trong khi đó, `new BigDecimal("0.1")` đọc trực tiếp chuỗi thập phân, nên biểu diễn **chính xác 0.1 thập phân**.

Đây không chỉ là khác biệt về cách in: hai đối tượng có thể **khác giá trị toán học**, khác `scale` và dẫn tới kết quả khác khi `equals`, `compareTo`, cộng, trừ hoặc làm tròn.

Bài này thuộc nhóm **Phân tích số thực** của Java Core. Ta sẽ tách rõ ba cách tạo `BigDecimal` — từ `double`, từ `String` và từ `BigDecimal.valueOf(double)` — rồi xem tác động khi parse dữ liệu, làm tròn, tính toán tiền tệ và xử lý đầu vào thực tế.

## 1. Ví dụ mấu chốt: cùng thấy “0.1” nhưng số được lưu khác nhau

~~~java
double d = 0.1;

BigDecimal fromDouble = new BigDecimal(d);
BigDecimal fromString = new BigDecimal("0.1");
BigDecimal fromValueOf = BigDecimal.valueOf(d);

System.out.println(fromDouble);
// 0.1000000000000000055511151231257827021181583404541015625
System.out.println(fromString);
// 0.1
System.out.println(fromValueOf);
// 0.1
~~~

Giải thích chính xác từng bước:

1. Source literal `0.1` được chuyển thành một mẫu bit `double` IEEE 754 binary64. Phân số `1/10` không có biểu diễn hữu hạn trong cơ số 2; mẫu bit `double` chứa **số gần 0.1**, không phải 0.1 toán học chính xác.
2. `new BigDecimal(d)` tạo một số thập phân **đúng bằng giá trị binary64 đã làm tròn** đang nằm trong `d`. Nó không đoán “ý định” ban đầu là 0.1.
3. `new BigDecimal("0.1")` phân tích các chữ số thập phân trong chuỗi `"0.1"`; giá trị bằng chính xác `1/10`.
4. `BigDecimal.valueOf(d)` dùng biểu diễn thập phân qua `Double.toString(d)` rồi tạo `BigDecimal` tương ứng. Với `d = 0.1`, chuỗi đó là `"0.1"`, nên kết quả giống constructor nhận chuỗi ở trường hợp này.

Về số học: giá trị của `new BigDecimal(0.1)` **lớn hơn** `new BigDecimal("0.1")` một lượng xấp xỉ `5.55 × 10^-18`. Dạng `Double.toString(0.1)` chỉ nhằm cho phép đọc lại đúng giá trị `double` nhị phân; nó **không** khẳng định mẫu bit lưu tương ứng đúng chính xác 0.1 thập phân.

Một `double` là giá trị số; `String` là các chữ số do người dùng, file hoặc API truyền vào. Chúng chứa những mức thông tin khác nhau nên constructor có kết quả khác.

## 2. Cơ sở: thập phân và nhị phân biểu diễn phân số khác nhau

Một số thập phân như `0.5` = `1/2` được biểu diễn hữu hạn trong cả cơ số 10 lẫn cơ số 2. Nhưng `0.1` = `1/10` = `1/(2 × 5)` có mẫu số chứa thừa số 5, vì thế biểu diễn nhị phân của nó là một chuỗi vô hạn cần cắt/làm tròn ở binary64.

Kiểu `double` thường giữ khoảng 15–17 chữ số thập phân có nghĩa, với **53 bit precision ở phần trị**. Điều đó đủ cho nhiều ứng dụng khoa học, đồ họa và tính toán, nhưng không làm mọi phân số thập phân trở nên chính xác.

| Giá trị/biểu thức | Kết quả cần hiểu |
| --- | --- |
| `double d = 0.5` | Có thể lưu chính xác `1/2` trong binary64 |
| `double d = 0.1` | Lưu số nhị phân gần 0.1 |
| `System.out.println(0.1)` | In `0.1` — dạng decimal ngắn có khả năng round-trip, không in toàn bộ giá trị toán học của bit |
| `new BigDecimal(0.1)` | Giữ nguyên giá trị của bit `double` và hiện ra chuỗi dài |
| `new BigDecimal("0.1")` | Giữ đúng giá trị thập phân do chuỗi mô tả |
| `BigDecimal.valueOf(0.1)` | Dựa trên `Double.toString(0.1)` nên tạo `BigDecimal` bằng 0.1 trong trường hợp này |

Trong biểu diễn lưu trữ, `BigDecimal` gồm **unscaled integer** (số nguyên tùy ý độ dài) và **scale** (số chữ số thập phân theo lũy thừa mười): giá trị bằng `unscaledValue × 10^(-scale)`. Ví dụ `new BigDecimal("0.1")` có unscaled value bằng 1 và scale bằng 1.

`BigDecimal` **không bị giới hạn bởi 53 bit precision như `double`**, nhưng vẫn cần chính sách scale/precision/rounding khi phép toán tạo kết quả dài hoặc vô hạn, đặc biệt là phép chia.

## 3. Ba cách tạo BigDecimal: hợp đồng không giống nhau

### Cách A — constructor nhận `double`

~~~java
BigDecimal exactStoredDouble = new BigDecimal(0.1);
~~~

Hợp đồng: biểu diễn **chính xác số thực đã lưu trong đối số `double`** dưới dạng thập phân. Constructor này có ích khi bạn cố ý cần điều tra giá trị binary64, lưu lại chính xác nội dung số học đang có hoặc xử lý chuyển đổi bit/số thực theo yêu cầu cụ thể.

Nó thường **không** phù hợp khi bạn muốn tạo giá tiền `0.10` từ literal `0.1`. Vấn đề không phải constructor hoạt động sai: nó làm đúng việc chuyển một số `double` hiện hữu sang `BigDecimal` **mà không làm tròn về ý định thập phân**.

### Cách B — constructor nhận `String`

~~~java
BigDecimal exactDecimal = new BigDecimal("0.1");
BigDecimal amount = new BigDecimal("19.99");
BigDecimal measured = new BigDecimal("1.2300");
~~~

Hợp đồng: parse văn bản hợp lệ thành **số thập phân chính xác** và ghi nhận scale theo biểu diễn chuỗi. Ví dụ `"1.2300"` có scale bằng 4, còn `"1.23"` có scale bằng 2, dù chúng bằng nhau về giá trị thập phân.

Nếu dữ liệu đã đến từ JSON/CSV/form người dùng dưới dạng chuỗi decimal đáng tin cậy, **tránh chuyển chuỗi sang `double` trước rồi mới tạo `BigDecimal`**:

~~~java
String input = "19.99";
BigDecimal correct = new BigDecimal(input);

// Không nên dùng nếu cần giữ đúng decimal từ input:
BigDecimal potentiallyDifferent =
        new BigDecimal(Double.parseDouble(input));
~~~

Cách thứ hai đã đi qua một số binary64 xấp xỉ trước khi constructor nhận `double` được gọi. Lúc này `BigDecimal` chỉ có thể giữ chính xác **giá trị sau bước xấp xỉ**, không biết người dùng định nhập số thập phân nào.

### Cách C — factory `BigDecimal.valueOf(double)`

~~~java
double d = 0.1;
BigDecimal commonConversion = BigDecimal.valueOf(d);
~~~

Hợp đồng: dùng dạng chuỗi canonical của `Double.toString(d)` để tạo `BigDecimal`. Với `d = 0.1`, nó tạo số `0.1`; nhờ đó giảm nhiều chữ số “đuôi” không mong đợi khi đổi một giá trị `double` hiện hữu sang decimal.

**Nhưng `valueOf` không tự sửa mọi sai số đã tích lũy:**

~~~java
double sum = 0.1 + 0.2;             // 0.30000000000000004
BigDecimal fromSum = BigDecimal.valueOf(sum);
// fromSum là 0.30000000000000004, không phải 0.3
~~~

`Double.toString(sum)` chính là `"0.30000000000000004"`, vì đó là dạng cần thiết để round-trip mẫu bit của tổng. Factory không thể suy ra phép tính ban đầu “đáng lẽ bằng 0.3”.

**Khuyến nghị theo ý định:** Dữ liệu decimal chính xác mới nên bắt đầu bằng `String`/`char[]` phù hợp hoặc nguồn `BigDecimal`. Khi đã có `double` và cần chuyển sang `BigDecimal` bằng dạng decimal ngắn tương ứng, `BigDecimal.valueOf` thường thuận tiện hơn constructor nhận `double`. Khi cần chính xác giá trị binary64 hiện tại, constructor nhận `double` mới là lựa chọn chủ đích.

## 4. Vì sao `equals` và `compareTo` có thể đưa ra kết quả khác?

Với `0.1`:

~~~java
BigDecimal a = new BigDecimal(0.1);
BigDecimal b = new BigDecimal("0.1");

boolean sameByEquals = a.equals(b);      // false
int numericOrder = a.compareTo(b);       // > 0
~~~

`a` thật sự **lớn hơn b về giá trị**, vì `double 0.1` được làm tròn hơi lớn hơn `1/10`. Do đó cả `equals` lẫn `compareTo == 0` đều không xem chúng bằng nhau.

Một vấn đề **khác** là scale:

~~~java
BigDecimal x = new BigDecimal("1.0");
BigDecimal y = new BigDecimal("1.00");

boolean equalObjects = x.equals(y);    // false: scale 1 khác scale 2
boolean equalValues = x.compareTo(y) == 0; // true: giá trị toán học bằng nhau
~~~

- `BigDecimal.equals` xem hai số bằng nhau khi **giá trị và scale** thích hợp khớp nhau. Đây là object equality quan trọng với `HashMap`/`HashSet`.
- `BigDecimal.compareTo` so sánh **giá trị số** và xem `1.0` và `1.00` bằng nhau.
- `stripTrailingZeros` có thể chuẩn hóa một phần biểu diễn decimal (`new BigDecimal("1.00").stripTrailingZeros()` in `1`), nhưng việc thay đổi scale không sửa được sự khác nhau thực về giá trị giữa `new BigDecimal(0.1)` và `new BigDecimal("0.1")`.

Nếu dùng `BigDecimal` làm khóa, hãy quyết định hợp đồng **scale có ý nghĩa hay không**. `HashSet<BigDecimal>` dựa trên `equals`, còn `TreeSet<BigDecimal>` dùng `compareTo` mặc định; hai tập có thể xử lý `1.0` và `1.00` khác nhau. Đây không phải lỗi của constructor mà là kết hợp giữa *giá trị* và *đại diện decimal*.

## 5. Làm tròn: sai khác khi khởi tạo có thể thành sai khác nghiệp vụ

Ví dụ kinh điển là `1.005` làm tròn đến hai chữ số thập phân theo `RoundingMode.HALF_UP`:

~~~java
BigDecimal a = new BigDecimal(1.005);
BigDecimal b = new BigDecimal("1.005");
BigDecimal c = BigDecimal.valueOf(1.005);

System.out.println(a.setScale(2, RoundingMode.HALF_UP)); // 1.00
System.out.println(b.setScale(2, RoundingMode.HALF_UP)); // 1.01
System.out.println(c.setScale(2, RoundingMode.HALF_UP)); // 1.01
~~~

Vì giá trị binary64 của literal `1.005` **hơi nhỏ hơn 1.005 thập phân**, constructor nhận `double` giữ đúng giá trị hơi nhỏ đó, nên làm tròn HALF_UP tới hai chữ số cho `1.00`. Với constructor nhận chuỗi, giá trị đúng ở điểm giữa `1.005` nên HALF_UP cho `1.01`.

Đây là lý do cùng một UI hiển thị `1.005` nhưng thuật toán tính giá/thuế có thể cho ra kết quả khác khi đi qua `double`. **Số chữ số hiển thị không chứng minh được tính chính xác hoặc chính sách làm tròn.**

Các phương thức `setScale` trả về **`BigDecimal` mới**, vì `BigDecimal` là immutable. Bạn phải dùng kết quả trả về, thay vì nghĩ rằng gọi phương thức sẽ thay đổi object cũ.

`RoundingMode.HALF_UP` chỉ là một chính sách. Các nghiệp vụ khác có thể yêu cầu `HALF_EVEN`, `DOWN`, `UP` hoặc cách xử lý đặc biệt; hãy định nghĩa rõ ở cấp nghiệp vụ.

## 6. Chương trình Java 17+ hoàn chỉnh để đối chiếu

Lưu tệp `BigDecimalConstructionDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class BigDecimalConstructionDemo {
    public static void main(String[] args) {
        double d = 0.1;
        BigDecimal fromDouble = new BigDecimal(d);
        BigDecimal fromString = new BigDecimal("0.1");
        BigDecimal fromValueOf = BigDecimal.valueOf(d);

        System.out.println("double d = " + d);
        System.out.println("new BigDecimal(d) = " + fromDouble);
        System.out.println("new BigDecimal(\"0.1\") = " + fromString);
        System.out.println("BigDecimal.valueOf(d) = " + fromValueOf);
        System.out.println("double constructor equals string = "
                + fromDouble.equals(fromString));
        System.out.println("valueOf equals string = "
                + fromValueOf.equals(fromString));
        System.out.println("double constructor compareTo string = "
                + fromDouble.compareTo(fromString));
        System.out.println("double constructor scale = " + fromDouble.scale());
        System.out.println("string constructor scale = " + fromString.scale());

        System.out.println("sum as double = " + (0.1 + 0.2));
        System.out.println("valueOf(double sum) = "
                + BigDecimal.valueOf(0.1 + 0.2));
        System.out.println("decimal string sum = "
                + new BigDecimal("0.1").add(new BigDecimal("0.2")));

        System.out.println("new BigDecimal(1.005) rounded = "
                + new BigDecimal(1.005)
                .setScale(2, RoundingMode.HALF_UP));
        System.out.println("new BigDecimal(\"1.005\") rounded = "
                + new BigDecimal("1.005")
                .setScale(2, RoundingMode.HALF_UP));
        System.out.println("BigDecimal.valueOf(1.005) rounded = "
                + BigDecimal.valueOf(1.005)
                .setScale(2, RoundingMode.HALF_UP));

        System.out.println("equals 1.0 and 1.00 = "
                + new BigDecimal("1.0")
                .equals(new BigDecimal("1.00")));
        System.out.println("compareTo 1.0 and 1.00 = "
                + new BigDecimal("1.0")
                .compareTo(new BigDecimal("1.00")));
        System.out.println("stripTrailingZeros 1.00 = "
                + new BigDecimal("1.00").stripTrailingZeros());

        System.out.println("BigDecimal.valueOf(-0.0) = "
                + BigDecimal.valueOf(-0.0));
        System.out.println("new BigDecimal(\"-0.0\") = "
                + new BigDecimal("-0.0"));

        try {
            new BigDecimal(Double.NaN);
        } catch (NumberFormatException ex) {
            System.out.println("NaN constructor = NumberFormatException");
        }
        try {
            BigDecimal.valueOf(Double.POSITIVE_INFINITY);
        } catch (NumberFormatException ex) {
            System.out.println("Infinity valueOf = NumberFormatException");
        }
        try {
            new BigDecimal("0.1").divide(new BigDecimal("3"));
        } catch (ArithmeticException ex) {
            System.out.println("0.1 / 3 exact = ArithmeticException");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BigDecimalConstructionDemo.java
java BigDecimalConstructionDemo
~~~

Stdout chính xác của chương trình:

~~~text
double d = 0.1
new BigDecimal(d) = 0.1000000000000000055511151231257827021181583404541015625
new BigDecimal("0.1") = 0.1
BigDecimal.valueOf(d) = 0.1
double constructor equals string = false
valueOf equals string = true
double constructor compareTo string = 1
double constructor scale = 55
string constructor scale = 1
sum as double = 0.30000000000000004
valueOf(double sum) = 0.30000000000000004
decimal string sum = 0.3
new BigDecimal(1.005) rounded = 1.00
new BigDecimal("1.005") rounded = 1.01
BigDecimal.valueOf(1.005) rounded = 1.01
equals 1.0 and 1.00 = false
compareTo 1.0 and 1.00 = 0
stripTrailingZeros 1.00 = 1
BigDecimal.valueOf(-0.0) = 0.0
new BigDecimal("-0.0") = 0.0
NaN constructor = NumberFormatException
Infinity valueOf = NumberFormatException
0.1 / 3 exact = ArithmeticException
~~~

Một số ý nghĩa nổi bật từ kết quả:

- `fromDouble.scale() == 55` trong khi `fromString.scale() == 1`; đó là hai biểu diễn decimal khác hẳn nhau.
- `BigDecimal.valueOf(0.1)` và `new BigDecimal("0.1")` bằng nhau trong ví dụ, **nhưng đừng mở rộng thành kết luận `valueOf(double)` luôn khôi phục decimal mong muốn của mọi phép tính**.
- `0.1 + 0.2` trên `double` thành `0.30000000000000004` trước khi chuyển sang `BigDecimal`; không có constructor nào tự suy ngược ý định phép cộng decimal.
- Hai phép làm tròn `1.005` trả kết quả khác nhau vì dữ liệu đầu vào đã khác nhau.
- `BigDecimal` không hỗ trợ các giá trị NaN và infinity như `double`. Chuyển NaN hoặc vô cực qua `BigDecimal` không tạo một số hợp lệ, mà phát sinh `NumberFormatException` trong ví dụ.
- `BigDecimal` biểu diễn số **không giữ dấu âm riêng cho giá trị 0**: `"-0.0"` khi parse cho ra giá trị 0 với scale 1, in `0.0`.

## 7. `valueOf(double)` không phải “thuốc chữa” sai số số học

Xét hai quy trình:

~~~java
double computed = 0.1 + 0.2;
BigDecimal convertedLater = BigDecimal.valueOf(computed);

BigDecimal computedAsDecimal = new BigDecimal("0.1")
        .add(new BigDecimal("0.2"));
~~~

Kết quả `convertedLater` là `0.30000000000000004`, còn `computedAsDecimal` là `0.3` chính xác. Không thể lấy kết quả của phép cộng đã làm tròn trong binary64 rồi giả định factory biết chính xác hai số thập phân ban đầu.

Cách làm tốt cho dữ liệu decimal có hợp đồng tính toán chặt chẽ:

1. Nhận số thập phân dưới dạng chuỗi gốc hoặc `BigDecimal` ngay tại lớp input; nếu là chuỗi, xác thực định dạng trước khi tạo object.
2. Tiến hành tính toán bằng các phép `add`, `subtract`, `multiply`, `divide` của `BigDecimal`, không chuyển qua `double` giữa chừng.
3. Chỉ định precision/scale và `RoundingMode` ở đúng điểm nghiệp vụ cần lượng tử hóa.
4. Xuất bằng `toPlainString`, `toString`, formatter hoặc serialize theo hợp đồng bên nhận; không phụ thuộc số chữ số ngẫu nhiên của `double`.

Nếu nguồn **chỉ cung cấp `double`**, bạn không thể biết chắc giá trị decimal con người dự định từ bit đã lưu. `BigDecimal.valueOf(d)` thường là chuyển đổi hợp lý dựa trên chuỗi round-trip của `double`; `new BigDecimal(d)` là lựa chọn khi muốn giữ giá trị nhị phân hiện có chính xác tuyệt đối. Phải ghi rõ chính sách thay vì che giấu nguồn gốc dữ liệu.

## 8. Những điều cần lưu ý khi parse String thành BigDecimal

`new BigDecimal(String)` đòi chuỗi có cú pháp số thập phân hợp lệ, không phải bất kỳ chuỗi hiển thị số nào. Ví dụ:

~~~java
BigDecimal ok = new BigDecimal("-12.3400");
BigDecimal scientific = new BigDecimal("1.25E+3");

// new BigDecimal("12,34"); // NumberFormatException
// new BigDecimal("1_000"); // NumberFormatException
// new BigDecimal("");      // NumberFormatException
~~~

Trong mã Java, `1_000` là literal nguyên hợp lệ; trong văn bản runtime đưa vào constructor `BigDecimal(String)`, dấu gạch dưới **không** là ký tự số hợp lệ. Chuỗi chứa dấu phân cách hàng nghìn hoặc thập phân tùy ngôn ngữ cần được xử lý theo **hợp đồng locale** riêng trước khi gọi parser, không tự ý xóa mọi dấu phẩy.

Khác với `double`, `BigDecimal` có thể biểu diễn thập phân rất lớn hoặc rất nhỏ với độ dài tùy ý (trong giới hạn tài nguyên và giới hạn scale/precision nội tại). Tuy vậy constructor vẫn có thể ném `NumberFormatException` khi dữ liệu sai cú pháp hoặc vượt giới hạn cấu trúc có thể xử lý.

Nên xác thực input, bắt ngoại lệ ở ranh giới giao tiếp và đưa ra thông báo nghiệp vụ phù hợp, thay vì nuốt lỗi rồi thay bằng 0. Với dữ liệu chứa thông tin nhạy cảm, không log nguyên văn toàn bộ chuỗi nếu không cần thiết.

## 9. Tính toán BigDecimal vẫn phải thiết kế precision và rounding

`BigDecimal` giúp phép cộng/trừ/nhân decimal hữu hạn diễn ra chính xác nếu không giới hạn precision một cách chủ đích; **nó không làm mọi phép chia có kết quả decimal hữu hạn**.

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

// one.divide(three); // ArithmeticException: khai triển thập phân vô hạn
BigDecimal approx = one.divide(three, 4, RoundingMode.HALF_UP);
// approx là 0.3333
~~~

Nếu bạn dùng `MathContext`, phép toán có thể được làm tròn theo precision yêu cầu:

~~~java
java.math.MathContext context =
        new java.math.MathContext(4, RoundingMode.HALF_EVEN);
BigDecimal roundedByPrecision =
        new BigDecimal("123.456").round(context);
// 123.5 (4 chữ số có nghĩa)
~~~

**Phân biệt:**

- `setScale(2, ...)` chủ yếu điều chỉnh số chữ số theo scale, thường liên quan chữ số sau dấu thập phân.
- `MathContext(4, ...)` quy định **4 chữ số có nghĩa**, không phải bốn chữ số sau dấu thập phân.
- `round`/`setScale` trả đối tượng mới; `BigDecimal` là immutable.
- `RoundingMode.UNNECESSARY` yêu cầu không được làm tròn; nếu số liệu cần làm tròn thì có thể ném `ArithmeticException`. Đây là một cách phát hiện phép làm tròn ngoài dự kiến.

Đối với tiền tệ, ngoài cách tạo `BigDecimal` từ chuỗi, bạn còn phải định nghĩa thời điểm làm tròn (mỗi dòng hay sau tổng), scale, rounding mode, loại tiền và quy tắc đối soát. Constructor đúng là **điều kiện cần**, không phải bảo đảm toàn bộ hệ thống tính tiền chính xác.

## 10. Số nguyên và constructor không bị vấn đề thập phân này giống double

Nếu nguồn thật sự là số nguyên chính xác trong `int` hoặc `long`, có thể tạo `BigDecimal` trực tiếp:

~~~java
BigDecimal units = BigDecimal.valueOf(42L);
BigDecimal alsoUnits = new BigDecimal("42");
~~~

Vì `long` biểu diễn mọi số nguyên trong miền của nó một cách chính xác, `BigDecimal.valueOf(long)` là lựa chọn thẳng và ít gây bất ngờ. `BigDecimal.valueOf(long)` và `BigDecimal.valueOf(double)` là **hai overload khác nhau**, không nên đánh đồng cơ chế của chúng.

Với số nguyên lớn vượt `long`, `BigInteger` và constructor `BigDecimal(BigInteger)` giúp giữ giá trị chính xác:

~~~java
java.math.BigInteger huge =
        new java.math.BigInteger("9223372036854775808");
BigDecimal exactHuge = new BigDecimal(huge);
~~~

Không nên ép `BigInteger` sang `double` rồi tạo `BigDecimal`, vì phép chuyển có thể mất bit độ chính xác hoặc tràn thành vô cực.

## 11. Những sai lầm phổ biến

1. **“`new BigDecimal(0.1)` chính xác hơn `new BigDecimal("0.1")` nên luôn tốt hơn.”** Nó chính xác **đối với số `double` đã làm tròn**, không chính xác theo ý định decimal `1/10`.
2. **“In `double` ra `0.1` nghĩa là bên trong lưu đúng 0.1.”** `Double.toString` tạo chuỗi ngắn có khả năng round-trip; nó không hiển thị tất cả chữ số decimal của giá trị bit đã lưu.
3. **“`BigDecimal.valueOf` luôn xóa sai số tính toán.”** Nó chỉ dùng `Double.toString` của **giá trị đang có**; `0.1 + 0.2` vẫn là `0.30000000000000004`.
4. **“Hai BigDecimal in gần giống nhau thì `equals` đúng.”** Phải xét cả giá trị lẫn scale; `1.0` và `1.00` không bằng nhau theo `equals` nhưng `compareTo == 0`.
5. **“`setScale(2)` làm tròn âm thầm mà không cần policy.”** Nếu phải bỏ chữ số và không chỉ định rounding mode, phép tính có thể ném `ArithmeticException`. Dùng `setScale(2, mode)` với chính sách rõ.
6. **“Đưa NaN/Infinity vào BigDecimal cũng được vì đều là số.”** `BigDecimal` không biểu diễn NaN hoặc vô cực; conversion phát sinh lỗi.
7. **“Tạo BigDecimal từ `double` rồi xử lý tiền là đủ.”** Nếu input đã qua phép tính binary64, decimal gốc có thể không phục hồi được. Hãy giữ dữ liệu decimal ngay từ nguồn.
8. **“Làm tròn ở bước hiển thị là đã làm tròn số tiền thực sự.”** Formatter chỉ xuất chuỗi. Cần lượng tử hóa giá trị nghiệp vụ và lưu kết quả theo chính sách.
9. **“Cứ dùng epsilon để làm BigDecimal.equals gần đúng.”** `BigDecimal` được dùng để mô hình hóa số decimal và scale cụ thể; nếu nghiệp vụ cần so sánh gần đúng thì phải định nghĩa quy tắc riêng, không phá hợp đồng equality/hash.
10. **“Chuỗi người dùng giống số là constructor luôn chấp nhận.”** Định dạng nhóm số, locale, ký tự không hợp lệ hoặc thiếu giá trị vẫn cần validation và xử lý `NumberFormatException`.

## 12. Hướng dẫn lựa chọn nhanh

| Nguồn dữ liệu / mục đích | Cách ưu tiên | Vì sao? |
| --- | --- | --- |
| Chuỗi decimal gốc `"0.10"` | `new BigDecimal("0.10")` | Giữ đúng giá trị và scale được nhập |
| Literal decimal cho tính tiền trong source | `new BigDecimal("19.99")` | Không đi qua binary64 |
| Đã có `double` và muốn decimal ngắn theo round-trip | `BigDecimal.valueOf(double)` | Dựa trên `Double.toString` |
| Đã có `double` và cần chính xác decimal tương ứng mẫu bit | `new BigDecimal(double)` | Giữ chính xác giá trị binary64 |
| Số nguyên `long` chính xác | `BigDecimal.valueOf(long)` | Không có sai số phân số của binary64 |
| Số nguyên rất lớn `BigInteger` | `new BigDecimal(bigInteger)` | Giữ số nguyên ngoài miền long |
| Thập phân cần làm tròn đến 2 chữ số | `setScale(2, RoundingMode.…)` | Quy định rõ phép lượng tử hóa |
| So sánh hai BigDecimal theo giá trị số | `compareTo(...) == 0` | Không phụ thuộc scale |
| So sánh BigDecimal theo object representation | `equals(...)` | Tính cả scale |
| Đầu vào NaN/Infinity | Xử lý trước khi tạo BigDecimal | Kiểu decimal này không biểu diễn chúng |

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `new BigDecimal(0.1)` in ra nhiều chữ số hơn `new BigDecimal("0.1")`?

**Đáp án:** Literal `0.1` đã bị làm tròn thành giá trị `double` nhị phân; constructor nhận `double` biểu diễn chính xác giá trị xấp xỉ đó dưới dạng decimal. Constructor nhận `String` biểu diễn trực tiếp số decimal chính xác.

**Câu 2.** `BigDecimal.valueOf(0.1)` có bằng `new BigDecimal("0.1")` không? Có phải `BigDecimal.valueOf(0.1 + 0.2)` cũng bằng `new BigDecimal("0.3")` không?

**Đáp án:** Ở trường hợp đầu có. Trường hợp sau không: phép cộng `double` cho `0.30000000000000004`, và factory giữ dạng chuỗi round-trip của kết quả ấy.

**Câu 3.** Tại sao `new BigDecimal(1.005).setScale(2, HALF_UP)` khác kết quả constructor nhận chuỗi?

**Đáp án:** Giá trị binary64 được lưu nhỏ hơn 1.005 thập phân, nên constructor nhận `double` làm tròn ra `1.00`; constructor nhận `"1.005"` giữ đúng điểm giữa thập phân và HALF_UP cho `1.01`.

**Câu 4.** `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` trả gì? `compareTo` có trả 0 không?

**Đáp án:** `equals` trả false vì scale khác; `compareTo` trả 0 vì giá trị decimal bằng nhau.

**Câu 5.** Vì sao chuyển JSON decimal `"19.99"` sang `double` trước khi tạo `BigDecimal` là rủi ro?

**Đáp án:** Việc parse thành `double` có thể làm mất sự chính xác thập phân và thông tin scale gốc. Nếu cần decimal chính xác, parse trực tiếp dữ liệu chuỗi thành `BigDecimal`.

**Câu 6.** Có nên dùng `new BigDecimal(Double.NaN)` hoặc kỳ vọng `BigDecimal.ONE.divide(new BigDecimal("3"))` trả số thập phân vô hạn không?

**Đáp án:** Không. `BigDecimal` không hỗ trợ NaN nên constructor đó ném `NumberFormatException`; phép chia có kết quả thập phân vô hạn mà không có chính sách làm tròn ném `ArithmeticException`.

## Tài liệu tham khảo

- [Java SE 21 — BigDecimal: constructor(double), constructor(String), valueOf, scale, rounding](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html).
- [Java SE 21 — Double.toString và IEEE 754](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html).
- [Java SE 21 — MathContext](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/MathContext.html) và [RoundingMode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html).
- [Java Language Specification `4.2.3 — Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.2.3).
