# Các phương thức `*ValueExact` của BigDecimal: kiểm tra phần lẻ và giới hạn kiểu đích

Khi chuyển `BigDecimal` sang `byte`, `short`, `int`, `long` hoặc `BigInteger`, cần quyết định rõ có **cho phép mất thông tin** hay không. Nhóm phương thức `byteValueExact()`, `shortValueExact()`, `intValueExact()`, `longValueExact()` và `toBigIntegerExact()` dành cho trường hợp yêu cầu **kết quả là số nguyên chính xác**.

**Quy tắc cốt lõi:** phép chuyển đổi `*Exact` chỉ thành công nếu giá trị `BigDecimal` không có **phần lẻ khác 0**; đối với các kiểu nguyên có độ rộng cố định, giá trị còn phải **nằm trong phạm vi biểu diễn của kiểu đích**. Nếu không đạt điều kiện, phương thức ném `ArithmeticException` thay vì tự cắt phần lẻ, làm tròn hoặc tràn số âm thầm.

```java
new BigDecimal("42.000").intValueExact(); // 42: chính xác
new BigDecimal("42.100").intValueExact(); // ArithmeticException: phần lẻ
new BigDecimal("2147483648").intValueExact(); // ArithmeticException: vượt int
```

Đoạn trên minh họa các biểu thức riêng lẻ; hai dòng cuối ném ngoại lệ nếu được thực thi mà không có xử lý.

## 1. Hai điều kiện độc lập: số nguyên về giá trị và vừa phạm vi

`BigDecimal` dùng biểu diễn `unscaledValue × 10^(-scale)`. `scale > 0` thường có nghĩa là có vị trí dành cho chữ số thập phân, **nhưng không chứng minh số có phần lẻ khác 0**.

Ví dụ:

| Giá trị `BigDecimal` | Scale | Là số nguyên về giá trị? | `intValueExact()` |
|---|---:|---|---|
| `"42"` | 0 | Có | `42` |
| `"42.000"` | 3 | Có: các chữ số sau dấu đều bằng 0 | `42` |
| `"42.100"` | 3 | Không: phần lẻ 0.100 | Ném `ArithmeticException` |
| `"-2.75"` | 2 | Không | Ném `ArithmeticException` |
| `"0.000"` | 3 | Có, bằng 0 | `0` |
| `"1E+3"` | -3 | Có, bằng 1000 | `1000` |
| `"2147483647"` | 0 | Có, vừa `int` | `2147483647` |
| `"2147483648"` | 0 | Có, nhưng vượt `int` | Ném `ArithmeticException` |

Lưu ý: phép chuyển chính xác kiểm tra **phần lẻ theo giá trị**, không đơn giản đòi `scale() == 0`. Vì thế `42.000` hợp lệ và `1E+3` cũng hợp lệ.

Hai điều kiện cần xét theo thứ tự logic:

1. **Tính nguyên:** có tồn tại giá trị nguyên bằng chính xác `BigDecimal` đầu vào không? `42.000` có, `42.100` không.
2. **Phạm vi:** số nguyên đó có thể được biểu diễn đúng trong `byte`, `short`, `int` hoặc `long` hay không? `2147483648` là số nguyên nhưng không thuộc `int`.

Không cần đoán ngoại lệ phát sinh vì lý do nào từ thông báo lỗi: API cam kết `ArithmeticException` khi không chuyển được chính xác, còn nội dung message có thể khác theo phiên bản triển khai. Nếu ứng dụng cần thông báo nghiệp vụ riêng cho “có phần lẻ” và “quá giới hạn”, hãy kiểm tra riêng từng điều kiện trước hoặc giải thích rõ chính sách sau khi bắt ngoại lệ.

## 2. Các phương thức chuyển đổi chính xác

| Phương thức | Kiểu trả về | Phạm vi kiểu đích | Điều kiện để thành công |
|---|---|---|---|
| `byteValueExact()` | `byte` | -128 đến 127 | Giá trị nguyên, trong phạm vi `byte` |
| `shortValueExact()` | `short` | -32768 đến 32767 | Giá trị nguyên, trong phạm vi `short` |
| `intValueExact()` | `int` | -2147483648 đến 2147483647 | Giá trị nguyên, trong phạm vi `int` |
| `longValueExact()` | `long` | -9223372036854775808 đến 9223372036854775807 | Giá trị nguyên, trong phạm vi `long` |
| `toBigIntegerExact()` | `BigInteger` | Không có giới hạn bit cố định | Giá trị nguyên; còn phụ thuộc giới hạn tài nguyên thực tế |

Những phương thức trên **không có tham số `RoundingMode`**: nếu giá trị không chuyển được chính xác, bạn phải xử lý lỗi hoặc chủ động làm tròn trước bằng một bước riêng đã được quy định.

### Ví dụ với `byte` và `short`

```java
new BigDecimal("127.00").byteValueExact(); // 127
new BigDecimal("128").byteValueExact();    // ArithmeticException
new BigDecimal("-128").byteValueExact();   // -128
new BigDecimal("-129").byteValueExact();   // ArithmeticException

new BigDecimal("32767").shortValueExact(); // 32767
new BigDecimal("32768").shortValueExact(); // ArithmeticException
```

`"127.00"` không bị từ chối chỉ vì scale là 2; giá trị vẫn chính xác bằng số nguyên 127. `"128"` bị từ chối vì `byte` tối đa là 127, dù hoàn toàn không có phần lẻ.

### Ví dụ với `int` và `long`

```java
new BigDecimal("2147483647").intValueExact(); // 2147483647
new BigDecimal("2147483648").intValueExact(); // ArithmeticException

new BigDecimal("9223372036854775807").longValueExact(); // Long.MAX_VALUE
new BigDecimal("9223372036854775808").longValueExact(); // ArithmeticException
```

Ở giới hạn âm cũng tương tự: giá trị nhỏ hơn `Integer.MIN_VALUE` hoặc `Long.MIN_VALUE` không thể chuyển chính xác sang kiểu tương ứng.

### Trường hợp `toBigIntegerExact()`

`BigInteger` có độ chính xác số nguyên tùy ý nên **không gặp giới hạn 8/16/32/64 bit**. Tuy nhiên, nó vẫn không thể giữ phần thập phân:

```java
new BigDecimal("999999999999999999999.000").toBigIntegerExact();
// Trả về BigInteger có giá trị 999999999999999999999

new BigDecimal("999999999999999999999.001").toBigIntegerExact();
// ArithmeticException: có phần lẻ khác 0
```

Có thể dùng `toBigIntegerExact()` khi cần chuyển một giá trị thập phân sang số nguyên lớn mà vẫn bảo toàn **toàn bộ giá trị**.

## 3. Khác biệt với các phương thức chuyển đổi thông thường

Nhóm **không có hậu tố `Exact`** có thể trả về giá trị mà không báo lỗi khi mất thông tin:

- `byteValue()`, `shortValue()`, `intValue()`, `longValue()` trả phần nguyên theo hướng về 0; nếu số vượt phạm vi kiểu đích, các bit thấp của phần nguyên được giữ theo độ rộng tương ứng, làm giá trị có thể đổi dấu hoặc không còn bằng số ban đầu.
- `toBigInteger()` loại phần lẻ theo hướng về 0, không kiểm tra xem phần lẻ có bị mất hay không.
- `floatValue()` và `doubleValue()` chuyển sang số thực nhị phân, có thể mất chữ số chính xác, cho kết quả vô cùng khi quá lớn hoặc về 0 khi quá nhỏ. **Không có phương thức `floatValueExact()` hoặc `doubleValueExact()` tương ứng trong `BigDecimal`.**

Ví dụ:

| Giá trị đầu vào | Gọi thông thường | Kết quả | Gọi `Exact` |
|---|---|---|---|
| `"42.1"` | `intValue()` | `42` | `intValueExact()` ném ngoại lệ |
| `"-2.75"` | `intValue()` | `-2` | `intValueExact()` ném ngoại lệ |
| `"2147483648"` | `intValue()` | `-2147483648` | `intValueExact()` ném ngoại lệ |
| `"128"` | `byteValue()` | `-128` | `byteValueExact()` ném ngoại lệ |
| `"1.99"` | `toBigInteger()` | `1` | `toBigIntegerExact()` ném ngoại lệ |
| `"-1.99"` | `toBigInteger()` | `-1` | `toBigIntegerExact()` ném ngoại lệ |

Ở ví dụ `2147483648`, `intValue()` trả `-2147483648` vì chỉ lấy 32 bit thấp của phần nguyên, được diễn giải theo kiểu `int` có dấu. Đây **không phải** một phép làm tròn hợp lệ theo nghiệp vụ và không phải cách kiểm tra số có vừa kiểu dữ liệu.

**Hệ quả:** dùng `intValue()` để chuyển giá tiền, mã định danh, số lượng, dữ liệu kế toán hoặc trường cần tính toàn vẹn có thể âm thầm bỏ chữ số hoặc tạo giá trị sai. Nếu yêu cầu là “chỉ chấp nhận số nguyên trong phạm vi”, `intValueExact()` là lựa chọn trực tiếp.

## 4. Ví dụ Java 17+ chạy độc lập và stdout có kiểm chứng

Tạo tệp `BigDecimalExactConversionDemo.java`:

```java
import java.math.BigDecimal;
import java.util.function.Supplier;

public class BigDecimalExactConversionDemo {
    private static void check(String label, Supplier<?> conversion) {
        try {
            System.out.println(label + " -> " + conversion.get());
        } catch (ArithmeticException ex) {
            System.out.println(label + " -> ArithmeticException");
        }
    }

    public static void main(String[] args) {
        check("42.000 int",
                () -> new BigDecimal("42.000").intValueExact());
        check("42.100 int",
                () -> new BigDecimal("42.100").intValueExact());
        check("-2.75 int",
                () -> new BigDecimal("-2.75").intValueExact());

        check("2147483647 int",
                () -> new BigDecimal("2147483647").intValueExact());
        check("2147483648 int",
                () -> new BigDecimal("2147483648").intValueExact());

        check("127.00 byte",
                () -> new BigDecimal("127.00").byteValueExact());
        check("128 byte",
                () -> new BigDecimal("128").byteValueExact());
        check("32767 short",
                () -> new BigDecimal("32767").shortValueExact());
        check("32768 short",
                () -> new BigDecimal("32768").shortValueExact());

        check("long max",
                () -> new BigDecimal("9223372036854775807").longValueExact());
        check("long overflow",
                () -> new BigDecimal("9223372036854775808").longValueExact());

        check("big integer",
                () -> new BigDecimal("999999999999999999999.000")
                        .toBigIntegerExact());
        check("big fraction",
                () -> new BigDecimal("999999999999999999999.001")
                        .toBigIntegerExact());

        System.out.println("42.1 intValue = "
                + new BigDecimal("42.1").intValue());
        System.out.println("2147483648 intValue = "
                + new BigDecimal("2147483648").intValue());
        System.out.println("128 byteValue = "
                + new BigDecimal("128").byteValue());
        System.out.println("zero scale=3 -> int = "
                + new BigDecimal("0.000").intValueExact());
        System.out.println("scientific -> int = "
                + new BigDecimal("1E+3").intValueExact());
    }
}
```

Biên dịch và chạy (Java 17 trở lên):

```bash
javac BigDecimalExactConversionDemo.java
java BigDecimalExactConversionDemo
```

Kết quả stdout:

```text
42.000 int -> 42
42.100 int -> ArithmeticException
-2.75 int -> ArithmeticException
2147483647 int -> 2147483647
2147483648 int -> ArithmeticException
127.00 byte -> 127
128 byte -> ArithmeticException
32767 short -> 32767
32768 short -> ArithmeticException
long max -> 9223372036854775807
long overflow -> ArithmeticException
big integer -> 999999999999999999999
big fraction -> ArithmeticException
42.1 intValue = 42
2147483648 intValue = -2147483648
128 byteValue = -128
zero scale=3 -> int = 0
scientific -> int = 1000
```

Hàm `check` bắt `ArithmeticException` để minh họa từng trường hợp thất bại mà không dừng toàn bộ chương trình. Nó cố ý in **tên loại ngoại lệ** thay vì `ex.getMessage()`, vì câu chữ thông báo không phải hợp đồng ổn định cần phụ thuộc.

Quan sát hai kết luận từ chương trình: `42.000` và `1E+3` chuyển chính xác dù scale lần lượt là 3 và -3; ngược lại `2147483648` không thể chuyển đúng sang `int`, dù là một số nguyên thuần túy.

## 5. Khi nào nên làm tròn trước rồi mới chuyển?

`*ValueExact` **không tự áp dụng chính sách làm tròn**. Nếu nghiệp vụ cho phép làm tròn, hãy tách quyết định làm tròn thành bước hiển thị rõ trong mã, rồi chuyển chính xác:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal quantity = new BigDecimal("12.7");

int rounded = quantity
        .setScale(0, RoundingMode.HALF_UP)
        .intValueExact(); // 13

int truncated = quantity
        .setScale(0, RoundingMode.DOWN)
        .intValueExact(); // 12
```

Đây là **đoạn mã minh họa** để đặt trong phương thức Java thích hợp, không phải một lớp Java có `main` độc lập. `setScale(0, ...) ` làm rõ chính sách xử lý phần thập phân. `intValueExact()` sau đó vẫn **kiểm tra phạm vi `int`**: làm tròn trước không bảo đảm một số quá lớn trở nên vừa kiểu.

Các chế độ làm tròn có ý nghĩa khác nhau; ví dụ `HALF_UP` làm tròn tới số nguyên gần nhất và chọn tăng độ lớn tại điểm giữa, `DOWN` bỏ phần lẻ theo hướng về 0. Việc chọn chế độ nào phải theo hợp đồng nghiệp vụ, không phải sở thích của lập trình viên.

Nếu nghiệp vụ **không cho phép mất bất kỳ phần lẻ nào**, gọi thẳng `intValueExact()` là đúng; đừng làm tròn trước để “lách” kiểm tra tính chính xác.

## 6. Dùng trong nhập liệu, API và xử lý lỗi

Một ví dụ điển hình: nhận số lượng từ chuỗi JSON, CSV hoặc database dưới dạng `BigDecimal`, rồi chuyển sang `int`. Nếu hệ thống yêu cầu số lượng phải là số nguyên không âm và không vượt số lượng tối đa, hãy làm các bước riêng:

1. **Xác thực miền nghiệp vụ:** số lượng phải không âm hoặc phải dương, phải đáp ứng giới hạn nghiệp vụ. `intValueExact()` chỉ kiểm tra tính nguyên và giới hạn kỹ thuật, **không** kiểm tra “phải dương”, “không được bằng 0” hay “tối đa 100 sản phẩm”.
2. **Chuyển chính xác:** dùng `intValueExact()`, `longValueExact()`, v.v. để loại phần lẻ không hợp lệ và tràn kiểu.
3. **Ánh xạ lỗi:** bắt `ArithmeticException` tại ranh giới phù hợp để tạo lỗi nhập liệu rõ ràng, thay vì để ứng dụng xử lý sai dữ liệu.

Ví dụ hàm có thể đặt trong lớp xử lý yêu cầu:

```java
static int parseQuantity(BigDecimal raw) {
    if (raw == null) {
        throw new IllegalArgumentException("Quantity is required");
    }
    final int quantity;
    try {
        quantity = raw.intValueExact();
    } catch (ArithmeticException ex) {
        throw new IllegalArgumentException(
                "Quantity must be a 32-bit integer", ex);
    }
    if (quantity < 0 || quantity > 100) {
        throw new IllegalArgumentException(
                "Quantity must be between 0 and 100");
    }
    return quantity;
}
```

Đoạn hàm trên dành cho một lớp Java thích hợp (hoặc đưa vào ví dụ có `main`) và không tự chạy riêng như một tệp. Nó phân biệt **lỗi chuyển đổi** (giá trị thập phân hoặc vượt `int`) với **lỗi quy tắc miền** (dù là số nguyên nhưng ngoài 0–100). Tránh chỉ viết `int x = raw.intValue()` vì có thể âm thầm thay đổi giá trị mà không phát hiện.

Nếu cần giữ số nguyên rất lớn mà vẫn từ chối phần lẻ, hãy dùng `toBigIntegerExact()` thay vì ép về `long` hoặc `int`.

## 7. Phân biệt chính xác số học với biểu diễn dữ liệu

Một số ngộ nhận phổ biến:

- **`scale() > 0` không có nghĩa phép chuyển `Exact` sẽ thất bại.** `"5.000"` là số nguyên về giá trị.
- **`scale() == 0` không bảo đảm phép chuyển `Exact` thành công.** `"999999999999999999999"` lớn hơn phạm vi `long` dù không có phần lẻ.
- **`precision()` không thay thế phép kiểm tra phạm vi.** Precision cho biết số chữ số có nghĩa, còn giá trị âm/dương, scale và giới hạn đích vẫn cần xét. Gọi đúng phương thức `*Exact` là cách ngắn gọn để API thực thi ràng buộc.
- **Phần lẻ khác 0 cũng bao gồm giá trị rất nhỏ.** `"0.0000001"` không thể chuyển thành 0 bằng `intValueExact()`, dù `intValue()` cho 0.
- **`-0.000` vẫn bằng số nguyên 0.** Giá trị số học bằng 0, nên chuyển chính xác thành 0, bất kể cách viết ban đầu.
- **`BigDecimal` bất biến.** Các phương thức chuyển đổi trả về giá trị kiểu đích; chúng không chỉnh scale hay làm tròn chính đối tượng `BigDecimal`.

Ngoài ra, `BigDecimal` có thể được tạo từ `double`. `new BigDecimal(0.1)` thể hiện chính xác giá trị nhị phân xấp xỉ của `double`, khác với giá trị thập phân mong muốn `0.1`. Khi dữ liệu đầu vào vốn là thập phân, nên ưu tiên `new BigDecimal("0.1")` hoặc nguồn decimal phù hợp; không trộn vấn đề **nguồn số có chính xác hay không** với vấn đề **chuyển sang kiểu nguyên có chính xác hay không**.

## 8. Cách chọn nhanh phương thức

| Yêu cầu | Cách làm |
|---|---|
| Chỉ chấp nhận số nguyên vừa `byte` | `byteValueExact()` |
| Chỉ chấp nhận số nguyên vừa `short` | `shortValueExact()` |
| Chỉ chấp nhận số nguyên vừa `int` | `intValueExact()` |
| Chỉ chấp nhận số nguyên vừa `long` | `longValueExact()` |
| Chấp nhận số nguyên vượt 64 bit, từ chối phần lẻ | `toBigIntegerExact()` |
| Cho phép làm tròn theo chính sách rõ ràng | `setScale(0, roundingMode)` rồi `*ValueExact()` |
| Chủ đích cắt phần lẻ và chấp nhận kết quả có thể mất thông tin | `intValue()`, `longValue()`, `toBigInteger()` tương ứng; ghi rõ ý nghĩa và rủi ro |
| Cần số thực `double` / `float` | Dùng `doubleValue()` / `floatValue()`, chấp nhận khả năng mất độ chính xác hoặc kiểm tra riêng điều kiện ứng dụng |

## 9. Tự kiểm tra

**Câu 1.** `new BigDecimal("7.000").intValueExact()` có ném lỗi không?  
**Đáp án:** Không; kết quả là 7 vì phần lẻ bằng 0, dù scale bằng 3.

**Câu 2.** `new BigDecimal("7.001").intValueExact()` trả gì?  
**Đáp án:** Ném `ArithmeticException` vì có phần lẻ khác 0.

**Câu 3.** `new BigDecimal("128").byteValueExact()` so với `byteValue()` thế nào?  
**Đáp án:** `byteValueExact()` ném `ArithmeticException` do 128 vượt `byte`; `byteValue()` trả -128 do chỉ giữ 8 bit thấp.

**Câu 4.** `new BigDecimal("2147483648").toBigIntegerExact()` có thành công không?  
**Đáp án:** Có; `BigInteger` không bị giới hạn bởi 32 bit. `intValueExact()` trên cùng giá trị sẽ ném ngoại lệ.

**Câu 5.** Khi nào `new BigDecimal("12.7").setScale(0, RoundingMode.HALF_UP).intValueExact()` là lựa chọn đúng?  
**Đáp án:** Khi quy tắc nghiệp vụ **cho phép và yêu cầu** làm tròn tới đơn vị theo `HALF_UP`; kết quả là 13. Nếu yêu cầu là nhập số nguyên nguyên trạng, phải từ chối `12.7` bằng `intValueExact()`.

**Câu 6.** `new BigDecimal("1E+3").intValueExact()` trả gì?  
**Đáp án:** 1000. Scale âm không cản trở chuyển đổi chính xác nếu giá trị số học là số nguyên và nằm trong phạm vi.

**Ghi nhớ:** `*ValueExact` là hàng rào chống mất dữ liệu âm thầm khi chuyển `BigDecimal` sang **số nguyên**: phải **không có phần lẻ** và **vừa phạm vi kiểu đích** (ngoại trừ `BigInteger` không có giới hạn bit cố định). Đừng nhầm việc cắt số, làm tròn và chuyển đổi chính xác là cùng một thao tác.
