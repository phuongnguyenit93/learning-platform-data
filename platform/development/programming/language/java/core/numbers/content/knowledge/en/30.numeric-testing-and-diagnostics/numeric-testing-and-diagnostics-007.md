# Đối chiếu mọi `RoundingMode` tại trường hợp đúng giữa trong Java

## 1. Bài toán: cùng một số ở “đúng giữa”, vì sao kết quả khác nhau?

Khi số thập phân cần giảm số chữ số sau dấu phẩy hoặc giảm số chữ số có nghĩa, **làm tròn** là quyết định phải thực hiện rõ ràng. Một tình huống dễ nhầm nhất là khi giá trị nằm **đúng giữa hai kết quả biểu diễn được** tại độ chính xác đang yêu cầu.

Chẳng hạn, yêu cầu làm tròn `2.5` thành số nguyên:

- Kết quả gần nhất có thể là `2` hoặc `3`.
- Khoảng cách từ `2.5` đến `2` bằng khoảng cách đến `3`, đều là `0.5`.
- Chế độ làm tròn (*rounding mode*) quyết định phải chọn `2`, `3` hay từ chối phép tính.

Với `-2.5`, hai kết quả nguyên lân cận là `-3` và `-2`; việc “làm tròn lên” có thể gây hiểu lầm nếu không phân biệt **về phía +∞**, **về phía −∞**, **về phía 0** và **ra xa 0**.

Trong Java 17+, các chế độ được định nghĩa bằng enum `java.math.RoundingMode` và thường dùng với `BigDecimal.setScale(...)`, `BigDecimal.divide(...)` hoặc `MathContext`.

**Mục tiêu:** đối chiếu **tất cả tám** giá trị `RoundingMode` ở điểm đúng giữa cho cả số dương và số âm; hiểu quy tắc với trường hợp không đúng giữa; biết khi nào `UNNECESSARY` hợp lệ; tạo bộ test có kết quả xác định và tránh lỗi do đầu vào `double`.

## 2. Định nghĩa “đúng giữa” phải gắn với độ chính xác đích

Một số **đúng giữa** (*exact halfway/tie*) là số có cùng khoảng cách tới hai kết quả lân cận có thể biểu diễn ở **scale hoặc precision được chọn**.

Ví dụ với `setScale(0, mode)`, đích là các số nguyên:

| Số gốc | Hai số nguyên lân cận | Có đúng giữa? |
| --- | --- | --- |
| `2.5` | `2` và `3` | Có |
| `-2.5` | `-3` và `-2` | Có |
| `3.5` | `3` và `4` | Có |
| `2.5000` | `2` và `3` | Có, các số 0 cuối không đổi giá trị |
| `2.5001` | `2` và `3` | Không, gần `3` hơn |
| `2.4999` | `2` và `3` | Không, gần `2` hơn |

Với `setScale(1, mode)`, các bước giữa các kết quả hợp lệ có kích thước `0.1`. Lúc này `2.25` ở đúng giữa `2.2` và `2.3`; `2.35` ở đúng giữa `2.3` và `2.4`. Nhưng `2.5` đã có một chữ số thập phân, nên **không cần làm tròn** ở scale 1.

Do đó không thể nói “giá trị có đuôi `.5` là tie” mà thiếu **scale đích**. Với phép làm tròn theo `MathContext`, tie còn phụ thuộc **số chữ số có nghĩa** được yêu cầu, không đơn giản là số vị trí sau dấu phẩy.

Dùng chuỗi thập phân để tạo giá trị test:

```java
BigDecimal value = new BigDecimal("2.5000");
BigDecimal rounded = value.setScale(0, RoundingMode.HALF_EVEN);
// rounded là 2
```

Cách này giữ **chính xác** giá trị thập phân mong muốn. Tránh viết `new BigDecimal(2.675)` cho testcase thập phân “đúng giữa”, vì số `double` đầu vào có thể chỉ là giá trị nhị phân *gần* số thập phân đã gõ.

## 3. Tám `RoundingMode`: chính xác ý nghĩa từng chế độ

`RoundingMode` gồm tám giá trị: `UP`, `DOWN`, `CEILING`, `FLOOR`, `HALF_UP`, `HALF_DOWN`, `HALF_EVEN`, `UNNECESSARY`.

| Chế độ | Quy tắc chính | Với tie dương `+2.5` tới scale 0 | Với tie âm `-2.5` tới scale 0 |
| --- | --- | ---: | ---: |
| `UP` | Nếu phải bỏ phần khác 0, làm tròn **ra xa 0** | `3` | `-3` |
| `DOWN` | Nếu phải bỏ phần khác 0, làm tròn **về 0** | `2` | `-2` |
| `CEILING` | Làm tròn **về +∞** | `3` | `-2` |
| `FLOOR` | Làm tròn **về −∞** | `2` | `-3` |
| `HALF_UP` | Chọn gần nhất; **nếu tie**, chọn **ra xa 0** | `3` | `-3` |
| `HALF_DOWN` | Chọn gần nhất; **nếu tie**, chọn **về 0** | `2` | `-2` |
| `HALF_EVEN` | Chọn gần nhất; **nếu tie**, chọn kết quả có chữ số cuối giữ lại **chẵn** | `2` | `-2` |
| `UNNECESSARY` | **Cấm mọi trường hợp phải làm tròn** | Lỗi | Lỗi |

Đây là **bảng đối chiếu tại tie**; không nên suy ra `UP` và `HALF_UP` giống nhau cho mọi số, hoặc `DOWN` và `HALF_DOWN` giống nhau cho mọi số. Chúng chỉ có thể cho cùng kết quả ở một số trường hợp.

### 3.1. `UP` khác “làm tròn lên theo trục số”

`UP` nghĩa là **ra xa số 0** khi phải bỏ phần khác 0:

```java
new BigDecimal("2.1").setScale(0, RoundingMode.UP);   // 3
new BigDecimal("-2.1").setScale(0, RoundingMode.UP);  // -3
```

Với số âm, kết quả `-3` lại **nhỏ hơn** `-2.1` theo trục số. Vì vậy đừng dịch đơn giản `UP` thành “chọn số lớn hơn”.

`DOWN` nghĩa là **về 0**:

```java
new BigDecimal("2.9").setScale(0, RoundingMode.DOWN);   // 2
new BigDecimal("-2.9").setScale(0, RoundingMode.DOWN);  // -2
```

Đây không phải `Math.floor` với số âm; `FLOOR` của `-2.9` là `-3`, còn `DOWN` là `-2`.

### 3.2. `CEILING` và `FLOOR` phụ thuộc hướng trên trục số

- `CEILING`: số biểu diễn được **nhỏ nhất không nhỏ hơn** số gốc.
- `FLOOR`: số biểu diễn được **lớn nhất không lớn hơn** số gốc.

Ở scale 0:

```java
new BigDecimal("2.5").setScale(0, RoundingMode.CEILING);   // 3
new BigDecimal("-2.5").setScale(0, RoundingMode.CEILING);  // -2

new BigDecimal("2.5").setScale(0, RoundingMode.FLOOR);     // 2
new BigDecimal("-2.5").setScale(0, RoundingMode.FLOOR);    // -3
```

Với số dương, `CEILING` thường giống `UP` khi cần bỏ chữ số và `FLOOR` giống `DOWN`. Với số âm thì ngược lại. Quy tắc này áp dụng không chỉ tại tie mà với mọi phần cần bỏ khác 0.

### 3.3. Ba chế độ `HALF_*`: chọn gần nhất rồi xử lý tie

Cả `HALF_UP`, `HALF_DOWN` và `HALF_EVEN` đều **ưu tiên kết quả gần số gốc nhất**. Chúng chỉ khác nhau khi khoảng cách đến hai kết quả lân cận **bằng nhau tuyệt đối**:

- `HALF_UP`: tie → ra xa 0.
- `HALF_DOWN`: tie → về 0.
- `HALF_EVEN`: tie → chữ số cuối cùng **được giữ lại** là chẵn.

`HALF_EVEN` còn được gọi là *round half to even* hoặc *banker's rounding* trong một số tài liệu. Tên gọi không có nghĩa mọi giao dịch ngân hàng đều bắt buộc dùng nó; quy tắc nghiệp vụ, hợp đồng hoặc pháp luật mới xác định chế độ.

Chẳng hạn tại scale 0:

- `2.5` → `2` với `HALF_EVEN`, vì `2` chẵn và `3` lẻ.
- `3.5` → `4` với `HALF_EVEN`, vì `4` chẵn và `3` lẻ.
- `-2.5` → `-2` với `HALF_EVEN`, vì chữ số đơn vị `2` chẵn.
- `-3.5` → `-4` với `HALF_EVEN`, vì chữ số đơn vị `4` chẵn.

Chú ý `HALF_EVEN` **không phải luôn làm tròn xuống**: kết quả với `3.5` là `4`.

### 3.4. `UNNECESSARY`: một hợp đồng không được mất thông tin

`RoundingMode.UNNECESSARY` yêu cầu phép toán chính xác **không cần làm tròn**. Nếu số không thể biểu diễn ở scale/precision yêu cầu mà không bỏ phần có giá trị, API ném `ArithmeticException`.

```java
new BigDecimal("2.00").setScale(0, RoundingMode.UNNECESSARY);
// 2 — hợp lệ: chỉ bỏ các số 0 không có giá trị.

new BigDecimal("2.50").setScale(0, RoundingMode.UNNECESSARY);
// ArithmeticException — cần bỏ phần 0.5 có giá trị.
```

`UNNECESSARY` không có ý nghĩa “làm tròn theo mặc định”; đó là **yêu cầu cấm làm tròn**. Hữu ích khi cần validation dữ liệu, đơn vị tiền nhỏ nhất, hoặc yêu cầu kết quả chính xác tuyệt đối. Thay nó bằng `DOWN` để tránh exception sẽ **thay đổi hợp đồng**.

## 4. Ma trận kết quả đầy đủ tại `±2.5` và `±3.5`

Các giá trị đầu vào đều là chuỗi `BigDecimal` chính xác; mục tiêu là `scale = 0`.

| `RoundingMode` | `+2.5` | `-2.5` | `+3.5` | `-3.5` |
| --- | ---: | ---: | ---: | ---: |
| `UP` | `3` | `-3` | `4` | `-4` |
| `DOWN` | `2` | `-2` | `3` | `-3` |
| `CEILING` | `3` | `-2` | `4` | `-3` |
| `FLOOR` | `2` | `-3` | `3` | `-4` |
| `HALF_UP` | `3` | `-3` | `4` | `-4` |
| `HALF_DOWN` | `2` | `-2` | `3` | `-3` |
| `HALF_EVEN` | `2` | `-2` | `4` | `-4` |
| `UNNECESSARY` | **lỗi** | **lỗi** | **lỗi** | **lỗi** |

Hai cột `2.5` kiểm tra dấu; hai cột `3.5` kiểm tra **parity của HALF_EVEN**. Nếu chỉ test `2.5`, một implementation sai “HALF_EVEN luôn lấy số nhỏ hơn về độ lớn” có thể không lộ lỗi.

Một điểm khác: `HALF_UP` ở đúng giữa âm `-2.5` cho `-3`, không phải `-2`. “UP” trong tên `HALF_UP` là **ra xa 0 khi tie**, không phải *ceiling*.

## 5. Test đúng giữa tại một chữ số sau dấu phẩy

Đối với `setScale(1, mode)`:

| Giá trị | Kết quả lân cận | `HALF_UP` | `HALF_DOWN` | `HALF_EVEN` |
| --- | --- | --- | --- | --- |
| `2.25` | `2.2` hoặc `2.3` | `2.3` | `2.2` | `2.2` |
| `2.35` | `2.3` hoặc `2.4` | `2.4` | `2.3` | `2.4` |
| `-2.25` | `-2.2` hoặc `-2.3` | `-2.3` | `-2.2` | `-2.2` |
| `-2.35` | `-2.3` hoặc `-2.4` | `-2.4` | `-2.3` | `-2.4` |

Với `2.25`, chữ số cuối giữ lại ở hai ứng viên là `2` và `3`; `HALF_EVEN` lấy `2.2`. Với `2.35`, chữ số cuối là `3` và `4`; kết quả là `2.4`. Không phải lấy **toàn bộ số nguyên** hay “chữ số trước dấu phẩy” để xét tính chẵn khi làm tròn scale 1.

Tương tự cho số âm: tính chẵn/lẻ của chữ số cuối không phụ thuộc dấu. Kết quả được chọn vẫn theo **hai ứng viên gần giá trị gốc nhất**, không tùy tiện bỏ dấu âm.

### Điểm sát tie nhưng không đúng giữa

Chỉ sai khác một chữ số nhỏ là có thể làm các `HALF_*` không còn khác nhau:

| Giá trị tới scale 0 | `HALF_UP` | `HALF_DOWN` | `HALF_EVEN` | Giải thích |
| --- | --- | --- | --- | --- |
| `2.4999` | `2` | `2` | `2` | Gần `2` hơn |
| `2.5000` | `3` | `2` | `2` | Tie thực sự |
| `2.5001` | `3` | `3` | `3` | Gần `3` hơn |
| `-2.4999` | `-2` | `-2` | `-2` | Gần `-2` hơn |
| `-2.5000` | `-3` | `-2` | `-2` | Tie thực sự |
| `-2.5001` | `-3` | `-3` | `-3` | Gần `-3` hơn |

`HALF_DOWN` **không phải lúc nào cũng hướng về 0**; nó chỉ chọn hướng đó khi đúng giữa. Ví dụ `2.5001` với `HALF_DOWN` ra `3`, còn `DOWN` ra `2`.

Đó là lý do bộ test cần cả tie, dưới tie và trên tie, không chỉ một trường hợp `.5`.

## 6. Kiểm chứng chương trình Java 17+ hoàn chỉnh

Lưu nội dung sau thành file **`RoundingMidpointDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class RoundingMidpointDemo {

    // Trả văn bản ERROR khi làm tròn là điều bị cấm.
    static String roundOrReject(
            String input, int scale, RoundingMode mode) {
        try {
            return new BigDecimal(input)
                    .setScale(scale, mode)
                    .toPlainString();
        } catch (ArithmeticException ex) {
            return "ERROR";
        }
    }

    public static void main(String[] args) {
        System.out.println(
                "Mode: +2.5, -2.5, +3.5, -3.5 (scale=0)");

        for (RoundingMode mode : RoundingMode.values()) {
            System.out.println(mode + ": "
                    + roundOrReject("2.5", 0, mode) + ", "
                    + roundOrReject("-2.5", 0, mode) + ", "
                    + roundOrReject("3.5", 0, mode) + ", "
                    + roundOrReject("-3.5", 0, mode));
        }

        System.out.println("HALF_EVEN 2.25 => "
                + roundOrReject("2.25", 1, RoundingMode.HALF_EVEN));
        System.out.println("HALF_EVEN 2.35 => "
                + roundOrReject("2.35", 1, RoundingMode.HALF_EVEN));
        System.out.println("HALF_EVEN -2.25 => "
                + roundOrReject("-2.25", 1, RoundingMode.HALF_EVEN));
        System.out.println("HALF_EVEN -2.35 => "
                + roundOrReject("-2.35", 1, RoundingMode.HALF_EVEN));

        System.out.println("HALF_DOWN 2.5001 => "
                + roundOrReject("2.5001", 0, RoundingMode.HALF_DOWN));
        System.out.println("HALF_UP 2.4999 => "
                + roundOrReject("2.4999", 0, RoundingMode.HALF_UP));

        System.out.println("UNNECESSARY 2.00 => "
                + roundOrReject("2.00", 0, RoundingMode.UNNECESSARY));
        System.out.println("UNNECESSARY 2.50 => "
                + roundOrReject("2.50", 0, RoundingMode.UNNECESSARY));

        System.out.println("String 2.675 => "
                + new BigDecimal("2.675")
                        .setScale(2, RoundingMode.HALF_EVEN));

        System.out.println("Double 2.675 => "
                + new BigDecimal(2.675)
                        .setScale(2, RoundingMode.HALF_EVEN));

        System.out.println("precision2 9.95 => "
                + new BigDecimal("9.95")
                        .round(new MathContext(
                                2, RoundingMode.HALF_UP))
                        .toPlainString());
    }
}
```

Biên dịch và thực thi:

```bash
javac RoundingMidpointDemo.java
java RoundingMidpointDemo
```

Stdout xác định trên Java 17+:

```text
Mode: +2.5, -2.5, +3.5, -3.5 (scale=0)
UP: 3, -3, 4, -4
DOWN: 2, -2, 3, -3
CEILING: 3, -2, 4, -3
FLOOR: 2, -3, 3, -4
HALF_UP: 3, -3, 4, -4
HALF_DOWN: 2, -2, 3, -3
HALF_EVEN: 2, -2, 4, -4
UNNECESSARY: ERROR, ERROR, ERROR, ERROR
HALF_EVEN 2.25 => 2.2
HALF_EVEN 2.35 => 2.4
HALF_EVEN -2.25 => -2.2
HALF_EVEN -2.35 => -2.4
HALF_DOWN 2.5001 => 3
HALF_UP 2.4999 => 2
UNNECESSARY 2.00 => 2
UNNECESSARY 2.50 => ERROR
String 2.675 => 2.68
Double 2.675 => 2.67
precision2 9.95 => 10
```

Phần `roundOrReject(...)` chỉ in `ERROR` cho **mục đích học và đối chiếu**. Trong ứng dụng sản xuất, nếu `UNNECESSARY` báo lỗi, bạn cần xử lý đúng loại ngoại lệ hoặc trả thông báo validation rõ ràng; không âm thầm thay kết quả bằng 0, không nuốt ngoại lệ rồi tiếp tục tính tiền.

Bộ vòng lặp qua `RoundingMode.values()` giúp **không vô ý bỏ sót chế độ thứ tám**. Việc in cả hai dấu và hai parity (`2.5`, `3.5`) giúp phát hiện nhiều loại lỗi trong implementation custom hơn là một ví dụ duy nhất.

## 7. Vì sao dùng `new BigDecimal(2.675)` có thể khiến test midpoint sai?

Nhiều số thập phân không biểu diễn chính xác bằng nhị phân hữu hạn. Literal Java `2.675` có kiểu `double` và được lưu dưới dạng một giá trị nhị phân rất gần `2.675` nhưng **không bằng chính xác** số thập phân ấy.

Vì vậy:

```java
BigDecimal decimalExact = new BigDecimal("2.675");
BigDecimal fromDouble  = new BigDecimal(2.675);

System.out.println(
        decimalExact.setScale(2, RoundingMode.HALF_EVEN)); // 2.68
System.out.println(
        fromDouble.setScale(2, RoundingMode.HALF_EVEN));   // 2.67
```

`decimalExact` nằm đúng giữa `2.67` và `2.68`; chữ số cuối `8` chẵn nên `HALF_EVEN` ra `2.68`. Còn `fromDouble` thể hiện **giá trị nhị phân chính xác đã được lưu từ literal**, hơi nhỏ hơn `2.675`, nên gần `2.67` hơn và ra `2.67`. Kết quả này không chứng minh `HALF_EVEN` hoạt động không nhất quán; **đầu vào đã khác nhau**.

Nếu bắt buộc bắt đầu từ một `double`, `BigDecimal.valueOf(2.675)` sử dụng biểu diễn thập phân từ `Double.toString` và thường hữu ích hơn `new BigDecimal(double)` cho chuyển đổi thông thường. Tuy nhiên, `valueOf` cũng không thể phục hồi giá trị thập phân gốc nếu bạn đã tính toán xấp xỉ bằng `double` trước đó. Với các testcase tie thập phân, ưu tiên tạo từ **chuỗi** hoặc `BigDecimal.valueOf(long, scale)` khi có giá trị nguyên đã định.

### Cách dựng dữ liệu kiểm thử chuẩn

```java
// Hai cách chính xác cho 2.675:
BigDecimal a = new BigDecimal("2.675");
BigDecimal b = BigDecimal.valueOf(2675L, 3);

System.out.println(a.compareTo(b) == 0); // true
```

Với các ca đúng giữa cần độ chính xác decimal, không dùng phép toán `double` trung gian để tạo expected value. Đừng dùng `Math.round(double)` như một oracle tổng quát để kiểm tra tám `RoundingMode`: nó có quy tắc riêng và chịu biểu diễn dấu phẩy động.

## 8. Phân biệt `setScale` với `MathContext`: hai loại bài toán làm tròn

### 8.1. `setScale`: số chữ số sau dấu phẩy

`setScale(targetScale, mode)` làm tròn theo **scale đích**:

```java
BigDecimal value = new BigDecimal("123.45");

BigDecimal fixed = value.setScale(1, RoundingMode.HALF_UP);
// fixed = 123.5
```

Khi dùng scale 0, giá trị kết quả là số nguyên; khi dùng scale 2, kết quả có hai vị trí thập phân (có thể thêm các số 0 cuối). Giá trị BigDecimal có thể có **scale âm**, nên đây không phải chỉ là tùy chọn định dạng; nó quyết định đơn vị lượng tử hóa thập phân.

### 8.2. `MathContext`: tổng số chữ số có nghĩa

`new MathContext(precision, mode)` dùng cho **precision** (số chữ số có nghĩa), không phải số chữ số sau dấu phẩy:

```java
BigDecimal input = new BigDecimal("9.95");
BigDecimal rounded = input.round(
        new MathContext(2, RoundingMode.HALF_UP));

// Kết quả giá trị số là 10, có 2 chữ số có nghĩa.
System.out.println(rounded.toPlainString()); // 10
```

Điểm đúng giữa trong bài toán precision còn phụ thuộc độ lớn đầu vào và vị trí chữ số bị bỏ. Nếu bạn cần tiền có đúng hai chữ số sau dấu phẩy, không nên thay `setScale(2, mode)` bằng `round(new MathContext(2, mode))`.

### 8.3. Làm tròn ở bước trung gian khác làm tròn một lần ở cuối

```java
BigDecimal a = new BigDecimal("0.005");
BigDecimal b = new BigDecimal("0.005");
BigDecimal c = new BigDecimal("0.005");

BigDecimal roundTotal = a.add(b).add(c)
        .setScale(2, RoundingMode.HALF_UP); // 0.02

BigDecimal roundEach = a.setScale(2, RoundingMode.HALF_UP)
        .add(b.setScale(2, RoundingMode.HALF_UP))
        .add(c.setScale(2, RoundingMode.HALF_UP)); // 0.03
```

Cùng mode nhưng **khác ranh giới làm tròn** nên tổng khác. Đây là quyết định nghiệp vụ (làm tròn từng dòng hay toàn hóa đơn), không phải lựa chọn tùy hứng để giảm chi phí tính toán.

## 9. Ma trận kiểm thử khuyến nghị cho mọi `RoundingMode`

Một testcase ở `2.5` là chưa đủ. Nên thiết kế **ma trận theo trục**, đặc biệt nếu đang kiểm chứng hàm rounding tự viết hoặc tích hợp với DB/API.

| Nhóm test | Giá trị mẫu | Điều cần xác minh |
| --- | --- | --- |
| Tie nguyên dương | `2.5`, `3.5` tới scale 0 | Chọn parity ở `HALF_EVEN`, away/toward |
| Tie nguyên âm | `-2.5`, `-3.5` tới scale 0 | Phân biệt `UP` và `CEILING`; `DOWN` và `FLOOR` |
| Tie scale 1 | `2.25`, `2.35`, `-2.25`, `-2.35` | Chữ số giữ lại chẵn/lẻ |
| Ngay dưới tie | `2.4999`, `-2.4999` | `HALF_*` chọn ứng viên gần nhất |
| Ngay trên tie | `2.5001`, `-2.5001` | Không coi sai là tie |
| Không cần rounding | `2.00` tới scale 0 | Mọi mode cho `2`; `UNNECESSARY` thành công |
| Buộc rounding | `2.50` tới scale 0 | `UNNECESSARY` phải ném ngoại lệ |
| Giá trị 0 | `0`, `0.000`, `-0.000` | Không tạo kết quả sai khác; chú ý BigDecimal không bảo toàn dấu âm của 0 |
| Giá trị lớn/nhỏ | `999.95`, `0.00005` theo scale thích hợp | Carry sang hàng chữ số mới, miền scale |
| Precision hữu hạn | `9.95` với precision 2 | Phân biệt `MathContext` với scale |
| Dữ liệu từ `double` | `2.675` literal và `"2.675"` | Không nhầm sai số đầu vào với bug rounding |
| Phân số từ phép chia | `1/3`, `1/8` | Cần mode/context phù hợp; `UNNECESSARY` nếu không chính xác |
| Dữ liệu số âm | `-0.1`, `-9.9` | Hướng +∞, −∞ và 0 đúng |

### 9.1. Kiểm tra trường hợp không cần làm tròn

Nếu số đã nằm chính xác trên “lưới” của scale đích, mọi chế độ phải giữ nguyên **giá trị số**:

```java
BigDecimal input = new BigDecimal("5.000");

for (RoundingMode mode : RoundingMode.values()) {
    BigDecimal result = input.setScale(0, mode);
    if (result.compareTo(new BigDecimal("5")) != 0) {
        throw new AssertionError("Sai khi không cần làm tròn: " + mode);
    }
}
```

Với `BigDecimal`, `equals` còn kiểm tra scale nên `new BigDecimal("5.000")` không `equals(new BigDecimal("5"))`, dù về số học bằng nhau. Hãy chọn phép so sánh theo hợp đồng testcase.

### 9.2. Một số bất biến hữu ích cho property-based testing

Nếu `x` là giá trị hữu hạn kiểu `BigDecimal`, `r = x.setScale(scale, mode)` thành công và không có vấn đề về miền/tài nguyên:

- **Cố định scale:** `r.scale() == scale`.
- **Idempotence ở cùng scale:** `r.setScale(scale, mode).equals(r)`; sau lần đầu, không còn phần chữ số cần bỏ.
- **Không dùng `UP`/`DOWN` sai hướng:** `UP` không cho độ lớn tuyệt đối thấp hơn giá trị gốc khi cần bỏ chữ số; `DOWN` không cho độ lớn tuyệt đối cao hơn giá trị gốc.
- **Không dùng `CEILING`/`FLOOR` sai thứ tự:** `CEILING` không trả số nhỏ hơn `x`; `FLOOR` không trả số lớn hơn `x`.
- **Nếu không cần rounding:** mọi mode, kể cả `UNNECESSARY`, cho cùng giá trị số.
- **Trong nhóm `HALF_*`:** nếu đầu vào không đúng giữa, ba mode phải chọn cùng ứng viên gần nhất (khi cần làm tròn).
- **Nếu phải bỏ chữ số có giá trị:** `UNNECESSARY` phải ném `ArithmeticException`.

Các bất biến không thay thế **expected value** cụ thể cho tất cả trường hợp tie. Phải kết hợp oracle (bảng kết quả ở mục 4/5), kiểm tra ngoại lệ và test giá trị dương/âm.

### 9.3. Kiểm tra ngoại lệ chính xác

Không nên viết test:

```java
// Không tốt: vô tình nuốt mọi lỗi và coi là thành công.
try {
    computation();
} catch (Exception ignored) {
}
```

Nếu quy tắc yêu cầu `UNNECESSARY` ném `ArithmeticException`, hãy kiểm tra **đúng kiểu ngoại lệ**. Trong JUnit 5, có thể dùng `assertThrows(ArithmeticException.class, ...)`; nếu chỉ dùng Java core, dùng một cờ và `try/catch(ArithmeticException)` rõ ràng, rồi ném `AssertionError` khi ngoại lệ không xuất hiện.

Test “không ném ngoại lệ” với `2.00` cũng quan trọng như test “phải ném” với `2.50`.

## 10. Ví dụ kiểm thử không dùng thư viện ngoài

Bạn có thể đưa phương thức này vào một lớp thử nghiệm Java, dùng trực tiếp API chuẩn:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

static void expectRounded(
        String input, int scale,
        RoundingMode mode, String expected) {

    BigDecimal actual = new BigDecimal(input).setScale(scale, mode);

    // So cả toPlainString để kiểm tra scale/trình bày của ví dụ.
    if (!actual.toPlainString().equals(expected)) {
        throw new AssertionError(
                input + " với " + mode + " => "
                + actual.toPlainString() + ", kỳ vọng " + expected);
    }
}

static void expectRoundingRejected(
        String input, int scale) {

    try {
        new BigDecimal(input)
                .setScale(scale, RoundingMode.UNNECESSARY);
    } catch (ArithmeticException expected) {
        return;
    }
    throw new AssertionError(
            "Phải từ chối rounding cho " + input);
}
```

Đây là **hai phương thức nhúng**, không phải file Java độc lập. Ví dụ lời gọi trong một hàm test:

```java
expectRounded("2.5", 0, RoundingMode.HALF_UP, "3");
expectRounded("-2.5", 0, RoundingMode.HALF_UP, "-3");
expectRounded("3.5", 0, RoundingMode.HALF_EVEN, "4");
expectRounded("2.25", 1, RoundingMode.HALF_EVEN, "2.2");
expectRounded("2.35", 1, RoundingMode.HALF_EVEN, "2.4");
expectRounded("-2.5", 0, RoundingMode.CEILING, "-2");
expectRounded("-2.5", 0, RoundingMode.FLOOR, "-3");
expectRounded("2.00", 0, RoundingMode.UNNECESSARY, "2");
expectRoundingRejected("2.50", 0);
```

Khuyến nghị tiếp theo là triển khai **data-driven test** để kiểm tra ma trận tám mode cho nhiều đầu vào, thay vì viết từng điều kiện `if` cho mỗi mode. Đừng tính expected bằng cùng hàm production đang test rồi so với chính nó; như vậy không phát hiện lỗi thuật toán.

## 11. Ứng dụng thực tế: tiền, thuế, kiểm thử liên hệ thống

Các API như `BigDecimal.divide(scale, mode)`, `setScale`, `round(MathContext)` đều có thể làm tròn nhưng **thời điểm** và **mục đích** khác nhau.

Với dữ liệu tiền tệ, một chính sách có thể nói: “Lưu số tiền theo hai chữ số thập phân, từ chối đầu vào không biểu diễn chính xác ở scale 2.” Đây là lý do hợp lệ để dùng `setScale(2, UNNECESSARY)` ở ranh giới lưu. Chính sách khác cho phép tính thuế ở precision cao rồi làm tròn `HALF_UP` khi kết toán; đó lại là một lựa chọn khác. Không có mode mặc định “đúng cho mọi tiền tệ”.

Với tích hợp CSDL `DECIMAL(p,s)`, serializer JSON, phần mềm kế toán hoặc hệ thống khác, kiểm thử không chỉ `BigDecimal` trong JVM mà cả quá trình:

1. Đọc chuỗi đầu vào thành số thập phân chính xác.
2. Áp dụng quy tắc rounding, scale hoặc precision tại ranh giới xác định.
3. Ghi qua JDBC/ORM hoặc xuất JSON theo định dạng đã công bố.
4. Đọc lại và so sánh cả **giá trị số** lẫn **scale/trình bày**, nếu hợp đồng yêu cầu.
5. Kiểm thử những tie dương/âm và chính sách xử lý overflow/exception ở cả hai phía.

Một database/driver có thể có quy tắc làm tròn riêng. Đừng để việc ép kiểu ở DB âm thầm thay thế quyết định trong tầng nghiệp vụ; làm rõ trách nhiệm từng hệ thống và dùng integration test cho các giá trị đúng giữa.

Nếu giao thức trao đổi bắt buộc giữ nguyên “`2.50`” thay vì “`2.5`”, hãy phân biệt giá trị số với biểu diễn chuỗi và scale. `BigDecimal.toPlainString()` giữ scale hiện có, còn `stripTrailingZeros()` có thể làm mất những số 0 cuối có ý nghĩa đối với định dạng/hợp đồng.

## 12. Những nhầm lẫn phổ biến

| Nhầm lẫn | Hậu quả | Quy tắc sửa |
| --- | --- | --- |
| “`UP` nghĩa là trục số tăng” | Làm tròn số âm sai | `UP` là **ra xa 0** |
| “`DOWN` luôn giống `FLOOR`” | Sai cho số âm | `DOWN` về 0; `FLOOR` về −∞ |
| “`CEILING` luôn tăng độ lớn” | Sai với số âm | `CEILING` về +∞ |
| “`HALF_UP` là làm tròn lên mọi phần dư” | Sai khi dưới tie | Chọn gần nhất; tie mới ra xa 0 |
| “`HALF_DOWN` luôn làm tròn xuống” | Sai khi trên tie | Chọn gần nhất; tie mới về 0 |
| “`HALF_EVEN` luôn xuống” | `3.5` thành `3` sai | Tie chọn chữ số **giữ lại** chẵn |
| “HALF_EVEN xét chữ số ngay trước dấu phẩy” | Sai khi scale > 0 hoặc âm | Xét chữ số cuối của **kết quả đích** |
| “`UNNECESSARY` là mode không làm gì” | Nuốt lỗi đáng phải ném | Chỉ hợp lệ khi không phải rounding |
| Chỉ test `+2.5`, bỏ `-2.5` | Không thấy lỗi hướng với số âm | Test cả hai dấu |
| Chỉ test `2.5`, bỏ `3.5` | Không thấy lỗi chẵn/lẻ | Test cả parity |
| Test với `new BigDecimal(2.675)` | Dữ liệu không phải tie thập phân | Tạo bằng chuỗi, dùng giá trị exact |
| Nhầm `MathContext(2)` với `setScale(2)` | Khác phạm vi precision | Dùng đúng API theo hợp đồng |
| Làm tròn mỗi dòng thay vì cuối tổng | Có thể đổi tổng tiền | Giữ ranh giới rounding được quy định |
| Dùng integer `BigDecimal.ROUND_*` cũ | API khó đọc, bị deprecated | Dùng enum `RoundingMode` |
| So `equals` khi chỉ cần bằng nhau về số | Sai với `2.0` và `2.00` | Dùng `compareTo` nếu scale không quan trọng |

## 13. Bài tập và hướng giải

**Bài 1.** Điền kết quả `setScale(0, ...)` cho `+7.5` và `-7.5` với đủ tám mode. Sau đó giải thích vì sao `HALF_EVEN` chọn `8` và `-8`.

*Gợi ý:* các ứng viên là `7`, `8`, `-7`, `-8`; tại tie, kết quả có chữ số cuối chẵn là ±8. `UNNECESSARY` báo lỗi.

**Bài 2.** Với đầu vào `-2.4999`, `-2.5000`, `-2.5001`, so kết quả `HALF_UP`, `HALF_DOWN`, `HALF_EVEN`, `UP`, `DOWN`, `CEILING`, `FLOOR`. Hai giá trị ngoài điểm giữa có giống nhau giữa các `HALF_*` không?

*Gợi ý:* `HALF_*` cùng ra `-2` ở `-2.4999`, khác nhau ở `-2.5000`, cùng ra `-3` ở `-2.5001`. Các mode hướng (UP/DOWN/CEILING/FLOOR) không phụ thuộc điều kiện tie.

**Bài 3.** Hệ thống chỉ lưu tối đa hai chữ số thập phân chính xác, không được tự làm tròn. `1.2300`, `1.234` và `1.200` sẽ được xử lý ra sao với `setScale(2, UNNECESSARY)`?

*Gợi ý:* `1.2300` → `1.23`; `1.234` bị từ chối; `1.200` → `1.20`. Các số 0 cuối có thể loại bỏ chính xác, nhưng chữ số khác 0 phải giữ nguyên.

**Bài 4.** Tại sao `new BigDecimal("2.675")` và `new BigDecimal(2.675)` có thể cho kết quả `HALF_EVEN` khác nhau tại scale 2? Cách tạo đầu vào nào nên được dùng cho bài kiểm thử midpoint thập phân?

*Gợi ý:* thứ nhất là decimal exact; thứ hai chứa giá trị nhị phân thực của `double`, không phải đúng `2.675`. Tạo từ chuỗi hoặc nguyên với scale.

**Bài 5.** Một kết quả `9.95` được làm tròn bằng `new MathContext(2, HALF_UP)`. Nó có nghĩa giữ hai chữ số sau dấu phẩy hay hai chữ số có nghĩa? Vì sao kết quả bằng `10`?

*Gợi ý:* precision 2 là **hai chữ số có nghĩa**, không phải scale 2. Phần cần làm tròn đẩy chữ số cuối lên và tạo carry.

**Bài 6.** Thiết kế bảng test cho các chế độ `RoundingMode` trên hai chiều **dấu** và **parity**, thêm ít nhất ba ca biên không đúng giữa. Làm thế nào để test `UNNECESSARY` cả đường thành công lẫn thất bại?

*Gợi ý:* dùng ma trận mục 4, 5 và các số `2.4999`, `2.5001`, `-2.4999`; test đúng kiểu `ArithmeticException`.

## 14. Kết luận thực hành

Để kiểm thử rounding đúng, **luôn bắt đầu bằng hợp đồng về scale/precision và thời điểm làm tròn**. Xây dựng một ma trận với **cả số dương lẫn số âm**, **chữ số cuối chẵn và lẻ**, **đúng giữa, dưới giữa, trên giữa**, cùng trường hợp **không cần làm tròn** và trường hợp `UNNECESSARY` phải từ chối.

Dùng `BigDecimal` từ chuỗi để tạo midpoint thập phân chính xác; không dùng `double` rồi coi kết quả xấp xỉ là một tie thực sự. `UP`, `DOWN`, `CEILING` và `FLOOR` là quy tắc **hướng**; `HALF_UP`, `HALF_DOWN` và `HALF_EVEN` là quy tắc **chọn gần nhất + xử lý tie**; `UNNECESSARY` là quy tắc **không được làm tròn**.

Tài liệu chuẩn Java SE 17:
- [`RoundingMode`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): mô tả từng chế độ, sơ đồ trường hợp dương và âm.
- [`BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): `setScale`, `divide`, `round`, precision/scale và xử lý `ArithmeticException`.
- [`MathContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html): precision và rounding mode cho phép tính.
