# Precision bằng 0 không phải scale bằng 0 trong Java BigDecimal

Khi làm việc với số thập phân chính xác bằng `BigDecimal`, hai từ **precision** và **scale** mô tả hai khía cạnh khác nhau. Đặc biệt, **`MathContext` có `precision = 0` nghĩa là không giới hạn số chữ số có nghĩa khi tính toán**, hoàn toàn không có nghĩa kết quả có `scale = 0` (không có chữ số sau dấu thập phân).

## 1. Phân biệt ba đại lượng dễ nhầm

Một `BigDecimal` biểu diễn giá trị bằng công thức:

```text
value = unscaledValue × 10^(-scale)
```

- **`BigDecimal.precision()`**: số chữ số trong hệ số nguyên không gồm dấu (`unscaledValue`), bỏ các số 0 đứng đầu. Số 0 có precision bằng **1**. Chữ số 0 ở cuối hệ số vẫn được tính khi biểu diễn chúng bằng scale tương ứng.
- **`BigDecimal.scale()`**: số mũ âm của 10 trong biểu diễn trên. Với số dạng thông thường, scale dương thường là số chữ số sau dấu thập phân; scale bằng 0 là số nguyên ở biểu diễn hiện tại; scale âm cũng hợp lệ.
- **`MathContext.getPrecision()`**: số chữ số có nghĩa tối đa mà một phép toán có áp dụng `MathContext` sẽ giữ lại khi làm tròn. Riêng giá trị **0** là tín hiệu *unlimited precision*: không áp dụng giới hạn precision. Nó không phải precision thực tế bằng 0 của `BigDecimal`.

Ví dụ:

| Giá trị khởi tạo | `precision()` | `scale()` | Giải thích |
|---|---:|---:|---|
| `new BigDecimal("123.4500")` | 7 | 4 | Hệ số nguyên là `1234500`, có 7 chữ số. |
| `new BigDecimal("0.0012300")` | 5 | 7 | Hệ số `12300` có 5 chữ số, scale là 7. |
| `new BigDecimal("1000")` | 4 | 0 | Giá trị có biểu diễn scale 0, dù precision là 4. |
| `new BigDecimal("1E+3")` | 1 | -3 | Cùng giá trị số học 1000, nhưng biểu diễn khác. |
| `new BigDecimal("0.00")` | 1 | 2 | Giá trị bằng 0 có precision 1, vẫn giữ scale 2. |

**Cần nhớ:** precision mô tả **chữ số có nghĩa**, scale mô tả **vị trí dấu thập phân trong biểu diễn**. Hai đại lượng không phải hai cách gọi của cùng một thông số.

## 2. `MathContext` có precision bằng 0 hoạt động ra sao?

`MathContext` định nghĩa precision và `RoundingMode` cho những phép toán `BigDecimal` nhận đối số context:

```java
MathContext unlimited = MathContext.UNLIMITED;
MathContext alsoUnlimited = new MathContext(0, RoundingMode.DOWN);

System.out.println(unlimited.getPrecision());     // 0
System.out.println(alsoUnlimited.getPrecision());  // 0
```

Hai context trên đều **không làm tròn chỉ vì giới hạn chữ số có nghĩa**, bất kể chế độ làm tròn được cấu hình. `MathContext.UNLIMITED` có `precision = 0` và `RoundingMode.HALF_UP`; chế độ làm tròn này không biến nó thành context giới hạn precision.

Ví dụ, làm tròn bằng context unlimited không thay đổi số nguồn:

```java
BigDecimal x = new BigDecimal("1234.567");
BigDecimal y = x.round(MathContext.UNLIMITED);
// y = 1234.567; y.precision() = 7; y.scale() = 3
```

Nhưng **unlimited không đồng nghĩa mọi phép toán luôn trả về kết quả thành công**:

- Phép cộng, trừ, nhân có thể biểu diễn kết quả thập phân hữu hạn một cách chính xác, tùy giới hạn tài nguyên và phạm vi scale mà `BigDecimal` hỗ trợ.
- Phép chia có kết quả thập phân vô hạn tuần hoàn, như `1 / 3`, không thể được biểu diễn chính xác bằng một `BigDecimal` hữu hạn. Với `MathContext.UNLIMITED` hoặc `new MathContext(0, ...)`, `divide` sẽ ném `ArithmeticException` vì không có precision hữu hạn để làm tròn.
- Phép chia cho 0 vẫn ném ngoại lệ. Unlimited precision không loại bỏ điều kiện lỗi toán học.
- **Không có quy tắc bảo đảm scale giữ nguyên** khi tính toán. Scale của kết quả còn phụ thuộc phép toán, scale toán hạng và biểu diễn chính xác của kết quả.

Ví dụ, `new BigDecimal("1.20").add(new BigDecimal("3.4"), MathContext.UNLIMITED)` cho `4.60` (scale 2), còn phép nhân tương ứng cho `4.080` (scale 3). Context unlimited không đưa hai kết quả về scale 0.

## 3. `setScale(0)` tác động lên điều gì?

`setScale(0, roundingMode)` yêu cầu **kết quả có scale bằng 0**. Nếu phần thập phân khác 0, Java phải áp dụng chế độ làm tròn đã cung cấp:

```java
BigDecimal x = new BigDecimal("1234.567");

BigDecimal a = x.setScale(0, RoundingMode.HALF_UP); // 1235
BigDecimal b = x.setScale(2, RoundingMode.HALF_UP); // 1234.57
```

- `a.scale() == 0`, nhưng `a.precision() == 4`. Scale 0 không làm precision thành 0.
- `b.scale() == 2` vì có đúng hai chữ số sau dấu thập phân trong biểu diễn.
- `x.setScale(0)` (không có `RoundingMode`) chỉ thành công nếu có thể đổi scale **chính xác**, chẳng hạn `1234.000` thành `1234`; với `1234.567` nó ném `ArithmeticException` vì phải làm tròn.
- `RoundingMode.UNNECESSARY` có ý nghĩa “không cho phép mất thông tin”: nếu phép đổi scale đòi làm tròn thì ném ngoại lệ.

`BigDecimal` là bất biến: `setScale`, `round` và các phép số học trả về đối tượng kết quả; chúng không âm thầm sửa giá trị biến nguồn.

## 4. `round(MathContext)` khác `setScale`

Với cùng một số:

| Thao tác | Giá trị kết quả | Precision | Scale | Ràng buộc được áp dụng |
|---|---|---:|---:|---|
| `new BigDecimal("1234.567")` | `1234.567` | 7 | 3 | Biểu diễn ban đầu |
| `x.round(MathContext.UNLIMITED)` | `1234.567` | 7 | 3 | Không giới hạn chữ số có nghĩa |
| `x.round(new MathContext(3, HALF_UP))` | `1.23E+3` | 3 | -1 | 3 chữ số có nghĩa |
| `x.setScale(0, HALF_UP)` | `1235` | 4 | 0 | 0 chữ số sau dấu thập phân |

Trong bảng, `HALF_UP` là `RoundingMode.HALF_UP`.

Quan sát dòng precision 3: `1.23E+3` có giá trị số học là **1230**, khác **1235** của `setScale(0, HALF_UP)`. Làm tròn đến 3 chữ số có nghĩa nghĩa là làm tròn theo hàng chục trong trường hợp này; scale kết quả thậm chí **âm**. Vì thế thay `setScale(0, ...)` bằng `round(new MathContext(0, ...))` là lỗi về bản chất yêu cầu.

Một điểm tinh tế: nếu làm tròn theo precision khiến phần hệ số được chuẩn hóa, kết quả có thể chuyển sang ký pháp khoa học. `toPlainString()` có thể dùng khi cần hiển thị số thường, nhưng chỉ đổi **cách hiển thị**, không làm scale thành 0 hoặc thay quy tắc làm tròn.

## 5. Ví dụ Java 17+ chạy độc lập

Lưu tệp `PrecisionZeroVsScaleZero.java`:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class PrecisionZeroVsScaleZero {
    private static void show(String label, BigDecimal value) {
        System.out.println(label + ": " + value
                + " | precision=" + value.precision()
                + " | scale=" + value.scale());
    }

    public static void main(String[] args) {
        BigDecimal value = new BigDecimal("1234.567");
        MathContext unlimited = new MathContext(0, RoundingMode.DOWN);

        show("source", value);
        show("MathContext(0)", value.round(unlimited));
        show("setScale(0)", value.setScale(0, RoundingMode.HALF_UP));
        show("MathContext(3)",
                value.round(new MathContext(3, RoundingMode.HALF_UP)));

        BigDecimal one = BigDecimal.ONE;
        BigDecimal three = new BigDecimal("3");
        show("zero 0.00", new BigDecimal("0.00"));
        show("zero 0", BigDecimal.ZERO);

        System.out.println("1 / 8 unlimited: "
                + one.divide(new BigDecimal("8"), MathContext.UNLIMITED));

        try {
            System.out.println("1 / 3 unlimited: "
                    + one.divide(three, MathContext.UNLIMITED));
        } catch (ArithmeticException ex) {
            System.out.println("1 / 3 unlimited: ArithmeticException");
        }

        System.out.println("1 / 3 precision=4: "
                + one.divide(three,
                        new MathContext(4, RoundingMode.HALF_UP)));
        System.out.println("1 / 3 scale=2: "
                + one.divide(three, 2, RoundingMode.HALF_UP));
    }
}
```

Biên dịch và chạy:

```bash
javac PrecisionZeroVsScaleZero.java
java PrecisionZeroVsScaleZero
```

Kết quả chuẩn:

```text
source: 1234.567 | precision=7 | scale=3
MathContext(0): 1234.567 | precision=7 | scale=3
setScale(0): 1235 | precision=4 | scale=0
MathContext(3): 1.23E+3 | precision=3 | scale=-1
zero 0.00: 0.00 | precision=1 | scale=2
zero 0: 0 | precision=1 | scale=0
1 / 8 unlimited: 0.125
1 / 3 unlimited: ArithmeticException
1 / 3 precision=4: 0.3333
1 / 3 scale=2: 0.33
```

Trong chương trình, `new MathContext(0, RoundingMode.DOWN)` không cắt `1234.567` xuống một số nguyên; `setScale(0, HALF_UP)` mới thực sự đặt scale về 0. Ngoài ra, precision hữu hạn 4 cho phép `1 / 3` trả `0.3333`, trong khi scale cố định 2 cho `0.33`.

## 6. Chọn công cụ cho từng yêu cầu

| Bài toán thực tế | Cách tiếp cận |
|---|---|
| Cần phép tính chính xác, không chủ động giới hạn chữ số có nghĩa | Dùng phép toán chính xác hoặc `MathContext.UNLIMITED`; chủ động xử lý trường hợp chia vô hạn tuần hoàn. |
| Cần số chữ số có nghĩa hữu hạn cho thuật toán đo lường/tính gần đúng | Dùng `MathContext(p, RoundingMode)` với `p > 0`; thống nhất quy tắc làm tròn trong chuỗi phép tính. |
| Cần đúng 2 chữ số thập phân cho một giá trị tiền tệ hay đầu ra quy định | Dùng `setScale(2, RoundingMode...)` theo quy tắc nghiệp vụ; không dùng precision 2 để thay thế. |
| Cần làm tròn về đơn vị nguyên | Dùng `setScale(0, RoundingMode...)` rồi kiểm tra kết quả. |
| Cần chắc chắn phép toán không được mất chữ số | Dùng chế độ `UNNECESSARY` cho những phép có thể đòi làm tròn và xử lý `ArithmeticException`. |

Ví dụ tiền tệ: `new BigDecimal("12.345").setScale(2, RoundingMode.HALF_UP)` cho `12.35`. Ngược lại, `round(new MathContext(2, RoundingMode.HALF_UP))` cho `12`: đây là **hai chữ số có nghĩa**, không phải hai chữ số sau dấu thập phân.

Khi tạo `BigDecimal` từ số thập phân, ưu tiên constructor chuỗi hoặc `BigDecimal.valueOf(double)` tùy dữ liệu đầu vào. `new BigDecimal(0.1)` giữ giá trị nhị phân thực của `double`, nên có thể mang một dãy chữ số thập phân dài ngoài ý muốn; vấn đề này độc lập với việc precision context có bằng 0 hay không.

## 7. Các bẫy thường gặp

1. **Nhầm `precision = 0` của `MathContext` là “kết quả không có chữ số”.** Quy ước 0 ở context mang nghĩa unlimited; `BigDecimal.precision()` của số 0 vẫn là 1.
2. **Tưởng unlimited precision nghĩa là scale bằng 0.** Scale của `new BigDecimal("1.2300")` là 4 dù phép `round(MathContext.UNLIMITED)` giữ nguyên biểu diễn đó.
3. **Tưởng unlimited precision tự xử lý phép chia vô hạn.** `1 / 3` cần một precision hữu hạn hoặc scale kèm `RoundingMode` khi muốn kết quả xấp xỉ.
4. **Trộn làm tròn theo chữ số có nghĩa với làm tròn theo chữ số thập phân.** `MathContext(3)` khác `setScale(3)`. Phải xuất phát từ đơn vị đo hoặc quy định nghiệp vụ để chọn.
5. **Dùng `equals` để so sánh giá trị số học khi scale khác nhau.** `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` trả `false`, vì `equals` xét cả scale; `compareTo` trả 0 vì giá trị số học bằng nhau.
6. **Giả định scale luôn không âm hoặc luôn được bảo toàn.** Ví dụ `new BigDecimal("1000").stripTrailingZeros()` có thể trở thành `1E+3` với scale -3. `stripTrailingZeros()` chỉ chuẩn hóa biểu diễn; nó không có nghĩa “làm tròn về số nguyên”.
7. **Gọi `setScale` mà quên gán kết quả.** Với kiểu bất biến, phải dùng `result = value.setScale(...)` hoặc sử dụng trực tiếp giá trị trả về.

## 8. Tự kiểm tra

- `new MathContext(0, RoundingMode.HALF_EVEN).getPrecision()` bằng bao nhiêu? **0**, biểu thị unlimited precision.
- `new BigDecimal("7.000").setScale(0, RoundingMode.UNNECESSARY)` có thành công không? **Có**, được `7` vì các chữ số bỏ đi đều bằng 0.
- `new BigDecimal("7.001").setScale(0, RoundingMode.UNNECESSARY)` thế nào? **Ném `ArithmeticException`**, do cần làm tròn.
- `new BigDecimal("0.00").scale()` bằng bao nhiêu? **2**; còn `precision()` là **1**.
- `new BigDecimal("1000").round(new MathContext(2, RoundingMode.HALF_UP))` có scale bằng 0 không? **Không nhất thiết**: kết quả là `1.0E+3`, precision 2, scale -2.

**Quy tắc quyết định:** cần giới hạn *bao nhiêu chữ số có nghĩa* thì dùng `MathContext` với precision dương; cần giới hạn *bao nhiêu chữ số sau dấu thập phân* thì dùng `setScale`. Giá trị precision **0 của `MathContext`** chỉ bỏ giới hạn precision, không đặt scale về 0.
