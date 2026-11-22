# BigDecimal.setScale() và việc trả về đối tượng mới

## 1. Mục tiêu bài học

Trong Java, `BigDecimal` biểu diễn số thập phân với độ chính xác tùy ý, thường được dùng cho tiền tệ, thuế, tỷ lệ và các phép tính cần kiểm soát chữ số thập phân. `setScale()` đặt **scale** của giá trị kết quả; nó **không sửa đối tượng `BigDecimal` ban đầu** vì lớp này bất biến (*immutable*). Phải sử dụng giá trị trả về nếu cần kết quả đã đổi scale.

```java
BigDecimal price = new BigDecimal("12.345");
price.setScale(2, RoundingMode.HALF_UP); // Bỏ qua kết quả!
System.out.println(price);              // 12.345

BigDecimal rounded = price.setScale(2, RoundingMode.HALF_UP);
System.out.println(rounded); // 12.35
System.out.println(price);   // 12.345
```

Các đoạn minh họa rời trong bài giả định đã `import java.math.BigDecimal;` và `import java.math.RoundingMode;`. Ví dụ đầy đủ có thể biên dịch nằm ở phần 5.

## 2. Scale khác gì precision?

`BigDecimal` biểu diễn giá trị bằng **unscaled value** (số nguyên) và **scale** theo công thức:

```text
giá trị = unscaledValue × 10^(-scale)
```

Ví dụ, `new BigDecimal("123.4500")` có `unscaledValue() = 1234500`, `scale() = 4` và `precision() = 7`. Scale cho biết vị trí dấu thập phân; precision là tổng số chữ số có nghĩa trong biểu diễn. Sau `setScale(2)`, kết quả `123.45` có unscaled value `12345` và scale `2`, còn trị số toán học giữ nguyên.

`new BigDecimal("2.5")` có scale 1, trong khi `new BigDecimal("2.500")` có scale 3. Cùng trị số nhưng khác biểu diễn. `setScale(2)` yêu cầu **hai vị trí sau dấu phẩy**, không phải hai chữ số có nghĩa; để giới hạn chữ số có nghĩa, tìm hiểu `MathContext` và các phép toán áp dụng nó.

Scale còn có thể âm: `new BigDecimal("1234").setScale(-2, RoundingMode.HALF_UP)` biểu diễn giá trị `1200` ở scale -2 và có thể in `1.2E+3`. Scale âm tương ứng làm tròn đến hàng chục, hàng trăm hoặc lớn hơn.

## 3. Ba overload và quy tắc thay đổi scale

| API | Ý nghĩa |
| --- | --- |
| `setScale(int newScale)` | Chỉ cho phép thay đổi scale **chính xác**; nếu phải bỏ chữ số khác 0 thì ném `ArithmeticException`. |
| `setScale(int newScale, RoundingMode roundingMode)` | Cho phép làm tròn khi cần theo chế độ được chọn. |
| `setScale(int newScale, int roundingMode)` | Overload dùng hằng số `int` cũ, đã deprecated; nên dùng `RoundingMode`. |

**Tăng scale** bổ sung chữ số 0 mà không đổi giá trị số học:

```java
BigDecimal x = new BigDecimal("7.2");
System.out.println(x.setScale(3)); // 7.200
System.out.println(x);             // 7.2
```

**Giảm scale** phải xét phần bị loại:

```java
new BigDecimal("7.2300").setScale(2);                    // 7.23, chính xác
new BigDecimal("7.235").setScale(2, RoundingMode.HALF_UP); // 7.24
new BigDecimal("7.235").setScale(2);                    // ArithmeticException
```

Phát biểu “`setScale(2)` luôn làm tròn” là sai: overload một tham số không có chế độ làm tròn mặc định. Nhưng “giảm scale luôn lỗi” cũng sai: giảm từ `7.2300` xuống `7.23` không mất chữ số có giá trị khác 0 nên vẫn chính xác.

Nếu dùng `RoundingMode.UNNECESSARY`, phương thức chủ động ném `ArithmeticException` mỗi khi yêu cầu phải làm tròn. Cách này hữu ích khi kiểm tra dữ liệu đầu vào phải đã đúng scale.

## 4. Hiểu và lựa chọn RoundingMode

Ví dụ số dương `2.345` về scale 2:

| Chế độ | Kết quả | Quy tắc |
| --- | --- | --- |
| `HALF_UP` | `2.35` | Đúng giữa hai mức thì đi xa 0. |
| `HALF_EVEN` | `2.34` | Đúng giữa thì chọn chữ số cuối giữ lại là chẵn; `2.355` thành `2.36`. |
| `DOWN` | `2.34` | Cắt phần bị bỏ, hướng về 0. |
| `UP` | `2.35` | Khi có phần bị bỏ khác 0, đi xa 0. |
| `CEILING` | `2.35` | Làm tròn về dương vô cực. |
| `FLOOR` | `2.34` | Làm tròn về âm vô cực. |
| `UNNECESSARY` | Exception | Không chấp nhận mất độ chính xác. |

Số âm cho thấy `CEILING` và `FLOOR` khác `UP` và `DOWN`:

```java
BigDecimal negative = new BigDecimal("-2.345");
System.out.println(negative.setScale(2, RoundingMode.CEILING)); // -2.34
System.out.println(negative.setScale(2, RoundingMode.FLOOR));   // -2.35
System.out.println(negative.setScale(2, RoundingMode.HALF_UP)); // -2.35
```

`HALF_EVEN` có thể giảm thiên lệch tổng thể khi nhiều kết quả rơi đúng giữa hai mức. Nhưng yêu cầu nghiệp vụ, quy định tài chính hoặc quy tắc tiền tệ mới là căn cứ để chọn chế độ; không có `RoundingMode` nào là đúng cho mọi hệ thống.

## 5. Chương trình Java 17+ hoàn chỉnh

Lưu vào tệp `BigDecimalSetScaleDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class BigDecimalSetScaleDemo {
    public static void main(String[] args) {
        BigDecimal original = new BigDecimal("12.345");
        BigDecimal rounded = original.setScale(2, RoundingMode.HALF_UP);
        System.out.println("original = " + original);
        System.out.println("rounded = " + rounded);

        BigDecimal amount = new BigDecimal("2.5");
        BigDecimal expanded = amount.setScale(3);
        System.out.println("expanded = " + expanded);
        System.out.println("amount unchanged = " + amount);

        BigDecimal exact = new BigDecimal("12.340").setScale(2);
        System.out.println("exact = " + exact);

        BigDecimal tie = new BigDecimal("2.345");
        System.out.println("HALF_UP = " + tie.setScale(2, RoundingMode.HALF_UP));
        System.out.println("HALF_EVEN = " + tie.setScale(2, RoundingMode.HALF_EVEN));

        BigDecimal sameScale = new BigDecimal("1.20");
        BigDecimal result = sameScale.setScale(2);
        System.out.println("same value = " + sameScale.equals(result));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac BigDecimalSetScaleDemo.java
java BigDecimalSetScaleDemo
```

Kết quả chuẩn:

```text
original = 12.345
rounded = 12.35
expanded = 2.500
amount unchanged = 2.5
exact = 12.34
HALF_UP = 2.35
HALF_EVEN = 2.34
same value = true
```

Giải thích: `rounded` nhận kết quả được làm tròn, nhưng `original` giữ nguyên. `expanded` có thêm hai số 0 vì scale tăng từ 1 lên 3. `exact` chỉ loại chữ số 0 nên không cần rounding mode. `tie` minh họa khác biệt giữa hai chính sách làm tròn khi nằm đúng giữa. Trường hợp `sameScale` so sánh bằng giá trị và scale, không kiểm tra sự khác biệt tham chiếu.

## 6. “Trả về đối tượng mới” phải hiểu đúng

Về mặt ngữ nghĩa, `setScale()` trả về một `BigDecimal` có scale mới được yêu cầu mà **không thay đổi trạng thái của đối tượng gốc**:

```java
BigDecimal a = new BigDecimal("10.555");
BigDecimal b = a.setScale(2, RoundingMode.HALF_UP);
// a: 10.555, scale = 3
// b: 10.56, scale = 2
```

Tuy nhiên, không được suy ra JVM **luôn cấp phát instance vật lý khác**. Khi scale đã bằng scale yêu cầu, hoặc nhờ khả năng tái sử dụng/cache, một triển khai có thể trả lại chính tham chiếu trước đó. Không được viết phép kiểm tra `a != a.setScale(a.scale())` với kỳ vọng luôn đúng. Hợp đồng API là **giá trị kết quả + tính bất biến**, không phải danh tính tham chiếu mới ở mọi lời gọi.

Cần phân biệt các cách dùng sau:

- `amount.setScale(2, mode);`: kết quả bị bỏ; `amount` không đổi.
- `amount = amount.setScale(2, mode);`: gán biến địa phương sang tham chiếu kết quả; đối tượng gốc vẫn không đổi.
- `return amount.setScale(2, mode);`: trả kết quả đã chuẩn hóa cho caller.
- Với biến `final BigDecimal amount`, có thể tạo `BigDecimal rounded = amount.setScale(...)`, nhưng không được gán lại `amount`.

Đối tượng `BigDecimal` bất biến nên chia sẻ chính đối tượng giữa các luồng là an toàn về mặt trạng thái nội tại. Nếu nhiều luồng cùng đọc và gán lại **một biến/field dùng chung** chứa tham chiếu `BigDecimal`, vẫn cần đồng bộ hoặc cấu trúc dữ liệu luồng an toàn phù hợp; tính bất biến không tự động biến nhiều phép cập nhật tham chiếu thành một thao tác nguyên tử.

## 7. Ảnh hưởng đến equals(), compareTo() và collection

`setScale()` có thể làm thay đổi kết quả `equals()` dù giá trị số học giữ nguyên:

```java
BigDecimal x = new BigDecimal("2.0");
BigDecimal y = x.setScale(2); // 2.00

System.out.println(x.equals(y));    // false
System.out.println(x.compareTo(y)); // 0
System.out.println(x.scale());      // 1
System.out.println(y.scale());      // 2
```

`equals()` của `BigDecimal` xét cả giá trị biểu diễn và scale; `compareTo()` so sánh theo trị số toán học. Do đó, với mục tiêu “hai số có bằng nhau về số học không?”, thường dùng `compareTo(...) == 0`. Còn `HashSet<BigDecimal>` và khóa `HashMap<BigDecimal, ...>` dùng `equals()/hashCode()`: `2.0` và `2.00` có thể là hai khóa khác nhau. Nếu nghiệp vụ yêu cầu khóa chuẩn hóa, hãy áp dụng một chiến lược scale thống nhất **trước khi lưu/truy vấn**.

`stripTrailingZeros()` cũng trả về một `BigDecimal` và có thể biến đổi scale; nó không thay thế `setScale(n, mode)` khi yêu cầu số chữ số thập phân cố định. Cũng cần nhớ định dạng hiển thị chuỗi (ví dụ tiền tệ theo locale) là một trách nhiệm riêng: không suy ra hợp đồng hiển thị chỉ từ `BigDecimal.toString()`.

## 8. Tình huống thực tế: làm tròn số tiền

Giả sử nghiệp vụ yêu cầu làm tròn số tiền phải trả về hai chữ số sau dấu phẩy theo `HALF_UP`. Chương trình độc lập sau thể hiện cách viết hàm trả về kết quả, giữ nguyên đầu vào:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class MoneyExample {
    static BigDecimal toTwoDecimals(BigDecimal amount) {
        return amount.setScale(2, RoundingMode.HALF_UP);
    }

    public static void main(String[] args) {
        BigDecimal raw = new BigDecimal("19.995");
        BigDecimal payable = toTwoDecimals(raw);
        System.out.println("raw = " + raw);
        System.out.println("payable = " + payable);
    }
}
```

Lưu thành `MoneyExample.java`, chạy `javac MoneyExample.java` rồi `java MoneyExample`:

```text
raw = 19.995
payable = 20.00
```

Hàm `toTwoDecimals` chuẩn hóa dữ liệu tại ranh giới nghiệp vụ. Cần quyết định **làm tròn ở thời điểm nào**: từng dòng hóa đơn, sau khi cộng tổng, trước/sau khi tính thuế... Làm tròn sớm ở mọi bước có thể làm tổng cuối khác so với làm tròn một lần. Việc chọn scale 2 trong ví dụ chỉ là quy ước giả định, không đúng cho mọi loại tiền và quy định.

Nếu cần kiểm tra giá trị đầu vào đã đúng scale mà không được làm tròn:

```java
BigDecimal valid = new BigDecimal("10.00");
BigDecimal invalid = new BigDecimal("10.001");
System.out.println(valid.setScale(2, RoundingMode.UNNECESSARY)); // 10.00
// invalid.setScale(2, RoundingMode.UNNECESSARY) ném ArithmeticException.
```

## 9. Những lỗi thường gặp

1. **Không giữ giá trị trả về:** gọi `x.setScale(2, mode)` rồi tiếp tục dùng `x`. Cách sửa: gán cho biến kết quả, gán lại biến nếu được phép, hoặc return.
2. **Tin rằng overload một tham số luôn làm tròn:** `new BigDecimal("1.235").setScale(2)` ném `ArithmeticException`. Nếu có thể mất chữ số, chọn `RoundingMode` theo nghiệp vụ.
3. **Tin rằng giảm scale luôn lỗi:** `new BigDecimal("1.2300").setScale(2)` hợp lệ vì chính xác.
4. **Khởi tạo sai từ `double`:** `new BigDecimal(0.1)` giữ chính xác giá trị nhị phân của `double` (vốn không bằng chính xác 0.1 thập phân). Nên tạo bằng `new BigDecimal("0.1")` hoặc `BigDecimal.valueOf(0.1)` trong tình huống phù hợp.
5. **Nhầm scale và precision:** `setScale(2)` định vị dấu thập phân chứ không giới hạn hai chữ số có nghĩa; dùng `MathContext` khi bài toán yêu cầu precision.
6. **So sánh sai:** `==` xét tham chiếu; `equals()` xét thêm scale; `compareTo()` xét giá trị số học.
7. **Đợi chia rồi mới gọi `setScale()`:** `BigDecimal.ONE.divide(new BigDecimal("3"))` có thể ném `ArithmeticException` vì phần thập phân vô hạn; `setScale()` không cứu được phép chia đã lỗi. Dùng overload `divide(divisor, scale, roundingMode)` khi muốn chia có làm tròn.
8. **Nhầm các phương thức bất biến:** `add()`, `subtract()`, `multiply()`, `divide()` và `setScale()` đều trả giá trị; phải dùng kết quả khi cần.
9. **Tùy tiện làm tròn nhiều lần:** kết quả tổng có thể đổi nếu làm tròn trung gian. Viết kiểm thử cho các ngưỡng như `1.005`, `-1.005`, `2.345` và quy tắc nghiệp vụ đã chọn.

## 10. Câu hỏi tự kiểm tra

- `new BigDecimal("5.200").setScale(1)` có lỗi không? **Không**: trả `5.2` vì chỉ bỏ số 0.
- `new BigDecimal("5.201").setScale(1)` có lỗi không? **Có**: `ArithmeticException` do phải bỏ chữ số có giá trị khác 0.
- Sau `BigDecimal x = new BigDecimal("1.234"); x.setScale(2, RoundingMode.DOWN);`, `x` có giá trị gì? Vẫn **`1.234`**, vì kết quả `1.23` không được giữ.
- `new BigDecimal("8").setScale(2).toString()` trả gì? **`"8.00"`**.
- Tại sao `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` sai? Vì hai đối tượng khác scale, dù `compareTo()` trả 0.
- Vì sao không khẳng định `setScale()` luôn tạo instance mới? Vì API cam kết tính bất biến và kết quả chứ không cam kết danh tính tham chiếu luôn khác nhau.

**Ghi nhớ:** `setScale()` trả về giá trị có scale được yêu cầu; nó không sửa `BigDecimal` ban đầu. Chọn quy tắc làm tròn tường minh, luôn sử dụng kết quả và phân biệt scale với trị số toán học.
