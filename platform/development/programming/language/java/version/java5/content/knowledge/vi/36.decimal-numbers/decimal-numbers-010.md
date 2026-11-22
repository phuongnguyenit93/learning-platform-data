# setScale so với round

## 1. Hai câu hỏi khác nhau khi làm tròn

Với số `123.456`, yêu cầu “giữ hai chữ số sau dấu thập phân” cho kết quả `123.46`. Yêu cầu “giữ hai chữ số có nghĩa” lại cho giá trị `120`.

Cả hai đều có thể dùng cùng `RoundingMode.HALF_UP`, nhưng **vị trí làm tròn khác nhau**:

- `setScale(2, mode)` chọn vị trí theo dấu thập phân.
- `round(new MathContext(2, mode))` chọn số lượng chữ số có nghĩa.

Con số `2` trong hai lời gọi không biểu thị cùng một đại lượng. Chế độ làm tròn chỉ quyết định chọn giá trị nào khi cần bỏ phần dư; nó không làm hai mục tiêu trở thành tương đương.

Trong `BigDecimal`, cần hiểu ba khái niệm trước khi chọn API:

| Khái niệm | Câu hỏi nó trả lời |
|---|---|
| Giá trị số học | Số này lớn hay nhỏ bao nhiêu? |
| Scale | Dấu thập phân nằm ở đâu so với phần số nguyên được lưu? |
| Precision | Phần số nguyên được lưu có bao nhiêu chữ số? |

Cách nhìn này giúp giải thích cả những tình huống tưởng lạ như kết quả `120` có precision 2, hoặc `7` và `7.00` cùng giá trị nhưng khác `equals`.

## 2. Scale và precision trong BigDecimal

Có thể hình dung biểu diễn của `BigDecimal` bằng công thức:

```text
giá trị = unscaledValue × 10^(-scale)
```

`unscaledValue` là một số nguyên có độ dài tùy ý trong phạm vi tài nguyên thực tế. `scale` là số nguyên có thể dương, bằng 0 hoặc âm. `precision()` đếm số chữ số của trị tuyệt đối phần số nguyên được lưu; số 0 có precision bằng 1.

Một số ví dụ:

| Văn bản tạo số | unscaledValue | scale | precision |
|---|---:|---:|---:|
| `"123.456"` | `123456` | 3 | 6 |
| `"0.00123456"` | `123456` | 8 | 6 |
| `"7"` | `7` | 0 | 1 |
| `"7.000"` | `7000` | 3 | 4 |
| `"0.000"` | `0` | 3 | 1 |

Các số 0 đứng trước chữ số khác 0 trong `0.00123456` không làm precision tăng. Ngược lại, các số 0 cuối được lưu trong `7.000` có tham gia precision của biểu diễn đó.

Do đó, precision không đơn giản là “số chữ số sau dấu thập phân”, cũng không thể suy ra chính xác chỉ từ chuỗi `toPlainString()` nếu kết quả có scale âm.

Định nghĩa biểu diễn và hợp đồng làm tròn được mô tả trong [Java API: BigDecimal](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigDecimal.html).

## 3. setScale: chọn vị trí dựa trên dấu thập phân

### 3.1. Scale dương cố định số chữ số sau dấu thập phân

Khi gọi:

```java
BigDecimal result = new BigDecimal("123.456")
        .setScale(2, RoundingMode.HALF_UP);
```

kết quả là `123.46`, có scale 2 và precision 5.

Đây là đoạn mã minh họa dùng trong một phương thức, sau khi import `BigDecimal` và `RoundingMode`. Chương trình hoàn chỉnh ở phần sau có đầy đủ import, lệnh biên dịch và stdout.

`setScale` không giới hạn phần nguyên cần bao nhiêu chữ số. Vì vậy, `123.46` có tổng cộng năm chữ số nhưng vẫn đáp ứng hoàn toàn yêu cầu scale 2.

### 3.2. Thêm số 0 có thể không làm đổi giá trị

Với `new BigDecimal("7").setScale(2, mode)`, kết quả biểu diễn thành `7.00`.

Giá trị số học vẫn là 7. Chỉ biểu diễn được thay đổi để có scale 2. Trong trường hợp này, chế độ làm tròn không phải phân xử giữa hai giá trị khác nhau.

Giảm scale cũng không nhất thiết làm đổi giá trị: `7.000 → 7.00` chỉ bỏ một số 0.

Tuy nhiên, `7.001 → 7.00` đã thay đổi giá trị. Nếu yêu cầu giữ chính xác, có thể dùng `RoundingMode.UNNECESSARY`; lần chuyển này sẽ gây `ArithmeticException`.

### 3.3. Scale bằng 0 và scale âm

- Scale 0: biểu diễn ở đơn vị nguyên.
- Scale -1: vị trí ở hàng chục.
- Scale -2: vị trí ở hàng trăm.

Ví dụ:

```java
BigDecimal tens = new BigDecimal("149")
        .setScale(-1, RoundingMode.HALF_UP);

System.out.println(tens.toPlainString()); // 150
System.out.println(tens.scale());         // -1
System.out.println(tens.precision());     // 2
```

Biểu diễn của `tens` có thể hiểu là `15 × 10^1`. Chuỗi `150` có ba ký tự số nhưng phần số nguyên được lưu là `15`, nên precision bằng 2.

Đừng viết quy tắc chung “scale luôn là số chữ số sau dấu thập phân” mà bỏ qua trường hợp scale âm. Cách nói đó chỉ thuận tiện khi scale không âm.

### 3.4. Overload không truyền mode đòi hỏi chuyển chính xác

`setScale(2)` không tự chọn `HALF_UP`, `HALF_EVEN` hay một chế độ mặc định cho phép mất thông tin.

Ví dụ:

```java
new BigDecimal("1.2300").setScale(2); // 1.23, chuyển chính xác được.
new BigDecimal("1.234").setScale(2);  // ArithmeticException.
```

Nếu cho phép xấp xỉ, truyền `RoundingMode` rõ ràng. Nếu muốn thể hiện điều kiện giữ chính xác ngay trong lời gọi, dùng `setScale(2, RoundingMode.UNNECESSARY)`.

## 4. round(MathContext): giới hạn số chữ số có nghĩa

### 4.1. Precision dương là giới hạn tối đa

```java
MathContext context = new MathContext(2, RoundingMode.HALF_UP);
BigDecimal result = new BigDecimal("123.456").round(context);
```

Kết quả có giá trị `120`, scale -1 và precision 2. Hai chữ số được giữ là 1 và 2; vị trí bị bỏ bắt đầu từ chữ số 3 ở hàng đơn vị.

Với `0.00123456`, cũng context đó cho `0.0012`. Các số 0 đầu chỉ xác định độ lớn; hai chữ số có nghĩa được giữ vẫn là 1 và 2.

Như vậy, cùng precision 2 có thể cho:

- Một kết quả có scale âm khi số lớn.
- Một kết quả có nhiều chữ số sau dấu thập phân khi số rất nhỏ.

Đó là lý do `round` phù hợp với yêu cầu về số chữ số có nghĩa mà không cố định vị trí dấu thập phân.

### 4.2. round không bảo đảm thêm số 0 cho đủ precision

`new BigDecimal("7").round(new MathContext(2, mode))` vẫn có thể trả biểu diễn `7` với precision 1. Số này đã nằm trong giới hạn hai chữ số có nghĩa.

Với đầu vào `7.000`, precision hiện có là 4; làm tròn về precision 2 cho biểu diễn `7.0`.

Hai kết quả cùng giá trị nhưng cho thấy context không phải công cụ yêu cầu “luôn in đúng hai chữ số”. Nếu mục tiêu là định dạng hiển thị, cần xác định yêu cầu định dạng riêng.

### 4.3. Có thể xảy ra nhớ sang hàng trước

Làm tròn `9.999` với precision 2 và `HALF_UP` cho `10`, scale 0, precision 2.

Làm tròn `999.9` với precision 3 cho giá trị `1000`, nhưng biểu diễn có scale -1 và precision 3, tương ứng `100 × 10^1`.

Đừng chỉ cắt chuỗi sau một số lượng chữ số. Phần bị bỏ có thể khiến chữ số được giữ tăng, rồi lan truyền qua nhiều chữ số 9. API xử lý cả kết quả mang sang vị trí mới này.

### 4.4. Precision bằng 0 không có nghĩa giữ 0 chữ số

`new MathContext(0, mode)` biểu thị không giới hạn precision. Với `round`, nó không làm mất chữ số của giá trị đầu vào.

Ví dụ, `123.456` vẫn là `123.456` khi `round` bằng context đó. Chế độ làm tròn không được dùng để giới hạn chữ số trong trường hợp precision 0.

Precision âm không hợp lệ và làm constructor `MathContext` ném `IllegalArgumentException`.

Khi cần chọn chế độ, truyền cả hai đối số như `new MathContext(2, RoundingMode.HALF_EVEN)`. Constructor chỉ nhận precision sử dụng `HALF_UP`; đừng giả định nó tự dùng một chế độ khác. Xem [Java API: MathContext](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/MathContext.html).

## 5. Bảng so sánh trực tiếp

Với `RoundingMode.HALF_UP`:

| Đầu vào | `setScale(2, mode)` | `round(new MathContext(2, mode))` |
|---|---:|---:|
| `123.456` | `123.46` | `120` |
| `0.00123456` | `0.00` | `0.0012` |
| `9.999` | `10.00` | `10` |
| `7` | `7.00` | `7` |
| `7.000` | `7.00` | `7.0` |
| `0.000` | `0.00` | `0.000` |

Đặc biệt, trường hợp số rất nhỏ cho thấy khác biệt có thể ảnh hưởng lớn đến kết quả: `setScale(2)` có thể đưa một số khác 0 về `0.00`, còn precision 2 vẫn giữ được độ lớn và hai chữ số có nghĩa.

Điều đó không khiến một API đúng hơn API còn lại. Kết quả phù hợp phụ thuộc câu hỏi ban đầu: cố định vị trí thập phân hay giới hạn số chữ số có nghĩa.

| Thuộc tính | `setScale` | `round` |
|---|---|---|
| Đầu vào cấu hình chính | Scale đích | `MathContext` |
| Có thể tăng số 0 cuối | Có, để đạt scale yêu cầu | Không bảo đảm bổ sung cho đủ precision |
| Phần nguyên lớn có bị giảm chữ số không? | Tùy scale; scale 2 không giới hạn số chữ số phần nguyên | Có thể, nếu vượt precision |
| Kết quả có thể có scale âm? | Có, nếu yêu cầu scale âm | Có, khi cần biểu diễn kết quả trong precision |
| Thay đổi đối tượng ban đầu? | Không | Không |
| Có thể ném lỗi vì không cho phép làm tròn? | Có | Có |
| Là công cụ định dạng chuỗi đầy đủ? | Không | Không |

## 6. Chương trình Java chạy đầy đủ

Lưu thành `ScaleVsRoundDemo.java`:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class ScaleVsRoundDemo {
    private static void show(String label, BigDecimal value) {
        System.out.println(label + " = " + value.toPlainString()
                + " | scale=" + value.scale()
                + " | precision=" + value.precision());
    }

    public static void main(String[] args) {
        RoundingMode mode = RoundingMode.HALF_UP;
        MathContext twoDigits = new MathContext(2, mode);

        for (String text : new String[] {
                "123.456", "0.00123456", "9.999", "7", "7.000", "0.000"
        }) {
            BigDecimal value = new BigDecimal(text);
            System.out.println("input " + text);
            show("setScale(2)", value.setScale(2, mode));
            show("round(p=2)", value.round(twoDigits));
        }

        show("tens", new BigDecimal("149").setScale(-1, mode));
        show("carry", new BigDecimal("999.9")
                .round(new MathContext(3, mode)));
        show("unlimited", new BigDecimal("123.456")
                .round(new MathContext(0, mode)));

        BigDecimal original = new BigDecimal("4.4501");
        RoundingMode halfDown = RoundingMode.HALF_DOWN;
        show("direct scale 1", original.setScale(1, halfDown));
        show("precision then scale", original
                .round(new MathContext(3, halfDown))
                .setScale(1, halfDown));

        try {
            new BigDecimal("1.234").setScale(2);
        } catch (ArithmeticException exception) {
            System.out.println("setScale(2) without mode = ArithmeticException");
        }

        BigDecimal sameNumber = new BigDecimal("7").setScale(2, mode);
        System.out.println("7 equals 7.00 = "
                + new BigDecimal("7").equals(sameNumber));
        System.out.println("7 compareTo 7.00 = "
                + new BigDecimal("7").compareTo(sameNumber));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 ScaleVsRoundDemo.java
java ScaleVsRoundDemo
```

Stdout:

```text
input 123.456
setScale(2) = 123.46 | scale=2 | precision=5
round(p=2) = 120 | scale=-1 | precision=2
input 0.00123456
setScale(2) = 0.00 | scale=2 | precision=1
round(p=2) = 0.0012 | scale=4 | precision=2
input 9.999
setScale(2) = 10.00 | scale=2 | precision=4
round(p=2) = 10 | scale=0 | precision=2
input 7
setScale(2) = 7.00 | scale=2 | precision=3
round(p=2) = 7 | scale=0 | precision=1
input 7.000
setScale(2) = 7.00 | scale=2 | precision=3
round(p=2) = 7.0 | scale=1 | precision=2
input 0.000
setScale(2) = 0.00 | scale=2 | precision=1
round(p=2) = 0.000 | scale=3 | precision=1
tens = 150 | scale=-1 | precision=2
carry = 1000 | scale=-1 | precision=3
unlimited = 123.456 | scale=3 | precision=6
direct scale 1 = 4.5 | scale=1 | precision=2
precision then scale = 4.4 | scale=1 | precision=2
setScale(2) without mode = ArithmeticException
7 equals 7.00 = false
7 compareTo 7.00 = 0
```

Chương trình dùng `toPlainString()` để hiển thị kết quả không có số mũ, đồng thời in riêng scale và precision. Cần đọc cả ba thông tin; chuỗi `1000` đơn lẻ không cho biết biểu diễn đang có precision 3 hay 4.

## 7. Vì sao không nên gọi liên tiếp chỉ để “chắc chắn”?

Nếu gọi `round` rồi `setScale`, có thể đang làm tròn hai lần.

Trong chương trình:

```java
BigDecimal original = new BigDecimal("4.4501");
RoundingMode mode = RoundingMode.HALF_DOWN;

BigDecimal direct = original.setScale(1, mode);

BigDecimal throughPrecision = original
        .round(new MathContext(3, mode))
        .setScale(1, mode);
```

Đây là đoạn minh họa trích từ cách tính trong chương trình hoàn chỉnh:

- Trực tiếp về scale 1: `4.4501` gần `4.5` hơn `4.4`, nên nhận `4.5`.
- Qua precision 3: giá trị đầu tiên thành `4.45`.
- Sau đó về scale 1: `4.45` nằm đúng giữa; `HALF_DOWN` chọn về phía 0, nên nhận `4.4`.

Thông tin rằng số gốc vượt điểm giữa đã mất sau bước đầu. Dùng cùng một mode ở cả hai bước không khôi phục được thông tin đó.

Khi một hệ thống yêu cầu cả giới hạn chữ số có nghĩa lẫn scale cố định, cần xác định thứ tự xử lý, mức chính xác trung gian và việc có cho phép thêm một lần xấp xỉ hay không. Nếu bước sau chỉ được phép thay đổi biểu diễn, có thể đặt `UNNECESSARY` cho bước đó để phát hiện trường hợp phải đổi giá trị. Tuy nhiên, điều này không kiểm tra được thông tin đã mất ở bước trước.

## 8. Kết quả mới, giá trị bằng nhau và equals

Cả `setScale` lẫn `round` trả về một `BigDecimal`; chúng không sửa đối tượng tại chỗ.

```java
BigDecimal input = new BigDecimal("5.678");
input.setScale(2, RoundingMode.HALF_UP);
System.out.println(input.toPlainString()); // Vẫn là 5.678.
```

Phải lưu giá trị trả về:

```java
BigDecimal adjusted = input.setScale(2, RoundingMode.HALF_UP);
System.out.println(adjusted.toPlainString()); // 5.68.
```

Về so sánh, `BigDecimal.equals` xét cả giá trị và scale. `compareTo` dùng thứ tự theo giá trị số học:

```java
BigDecimal a = new BigDecimal("7");
BigDecimal b = new BigDecimal("7.00");

System.out.println(a.equals(b));    // false
System.out.println(a.compareTo(b)); // 0
```

Do đó, thêm số 0 bằng `setScale` có thể ảnh hưởng đến kiểm tra `equals` và cách sử dụng làm khóa trong tập hợp/bản đồ, dù giá trị số học không thay đổi.

Không dùng toán tử `==` để kiểm tra hai `BigDecimal` có cùng giá trị. Cũng không dựa vào việc một phương thức có trả lại cùng tham chiếu đối tượng hay không; chọn phép so sánh phù hợp với mục tiêu giá trị hoặc biểu diễn.

## 9. Phân biệt làm tròn, chuẩn hóa và định dạng

Ba mục tiêu này có thể liên quan nhưng không đồng nhất:

1. **Làm tròn giá trị:** chấp nhận chuyển `2.678` thành `2.68`.
2. **Chuẩn hóa biểu diễn:** chuyển `2.6800` thành `2.68` mà không đổi giá trị.
3. **Định dạng cho người đọc:** chọn dấu phân cách, nhóm chữ số, ký hiệu đơn vị hoặc số 0 hiển thị.

`setScale` có thể thực hiện hai mục tiêu đầu tùy đầu vào và mode. `round` kiểm soát số chữ số có nghĩa. Cả hai không tự quyết định toàn bộ quy tắc hiển thị theo ngôn ngữ.

Một chuỗi hiển thị ít chữ số không chứng minh rằng số dùng cho phép tính tiếp theo đã được thay đổi. Ngược lại, gọi `setScale` làm thay đổi giá trị trả về nhưng không sửa biến gốc nếu bỏ qua kết quả.

Cũng đừng xem `stripTrailingZeros()` là từ đồng nghĩa với một trong hai thao tác. Phương thức đó loại bỏ các số 0 cuối khỏi biểu diễn mà giữ nguyên giá trị, có thể tạo scale âm và không bảo đảm scale đích hoặc quy tắc hiển thị cố định.

Ví dụ, `new BigDecimal("1000.00").stripTrailingZeros()` có thể được biểu diễn thành `1E+3`; `toPlainString()` là `1000`, scale là -3. Đây không phải yêu cầu “luôn giữ hai chữ số sau dấu thập phân”.

## 10. Chọn API theo hợp đồng cụ thể

| Yêu cầu | Lựa chọn |
|---|---|
| Kết quả cần scale 2; cho phép xấp xỉ theo quy tắc đã định | `setScale(2, chosenMode)` |
| Kết quả cần scale 2; tuyệt đối không được đổi giá trị | `setScale(2, RoundingMode.UNNECESSARY)` |
| Chỉ giữ tối đa 4 chữ số có nghĩa | `round(new MathContext(4, chosenMode))` |
| Phép nhân phải áp dụng precision ngay trên kết quả phép nhân | `multiply(other, context)` |
| Chỉ cần hiển thị theo ngôn ngữ và mẫu số | Dùng công cụ định dạng; xác định chính sách hiển thị riêng |
| Muốn bỏ các số 0 cuối mà không ấn định scale | Cân nhắc `stripTrailingZeros()` và hệ quả về biểu diễn |

`round(context)` chỉ tác động lên giá trị tại lời gọi đó; nó không gắn context vào đối tượng để mọi phép toán sau tự sử dụng. Nếu phép nhân, cộng hoặc chia cần một `MathContext`, truyền context vào đúng overload của phép toán.

Để kiểm chứng thập phân rõ ràng, các ví dụ dùng constructor nhận chuỗi. Không tạo `BigDecimal` từ một `double` rồi mặc định rằng đó là đúng giá trị thập phân người nhập; khác biệt ở đầu vào sẽ ảnh hưởng kết quả làm tròn, dù chọn đúng phương thức.

## 11. Lỗi thường gặp

- Đọc `round(new MathContext(2))` như “hai số sau dấu thập phân”.
- Mong `round` thêm số 0 để mọi kết quả có đúng một số lượng ký tự cố định.
- Nghĩ `setScale(2)` mặc định được phép làm tròn.
- Đếm precision bằng độ dài chuỗi `toPlainString()`, đặc biệt khi scale âm.
- Bỏ quên đối tượng được trả về vì tưởng phương thức sửa số tại chỗ.
- Tự thêm cả `round` và `setScale` vào nhiều tầng, rồi bất ngờ khi kết quả thay đổi.
- Dùng `equals` cho kiểm tra chỉ cần so sánh giá trị, trong khi scale hai phía khác nhau.
- Chỉ thử số dương cỡ lớn, bỏ qua số nhỏ, số 0 và trường hợp nhớ qua nhiều chữ số 9.

Một nhóm đầu vào kiểm tra hữu ích gồm số có nhiều chữ số phần nguyên, số nhỏ hơn `0.01`, số đã nằm trong giới hạn precision, số có các số 0 cuối và số ngay sát vị trí làm tròn.

## 12. Bài tập tự kiểm tra

Dùng `RoundingMode.HALF_UP` nếu đề không chỉ định chế độ khác.

1. Với `45.678`, dự đoán `setScale(2, mode)` và `round` với precision 2.
2. Với `0.0009876`, so sánh hai cách trên.
3. `new BigDecimal("8").round(new MathContext(4, mode))` có bắt buộc thành `8.000` không?
4. Làm tròn `999.9` về precision 3 tạo giá trị nào, scale nào?
5. Vì sao `new BigDecimal("3.141").setScale(2)` không trả về `3.14`?
6. Hai số `5` và `5.00` nên so bằng gì khi chỉ quan tâm giá trị?

Đáp án:

1. `45.68` và `46`.
2. `0.00` và `0.00099`.
3. Không. Giá trị `8` đã nằm trong giới hạn bốn chữ số có nghĩa.
4. Giá trị `1000`, scale -1, precision 3.
5. Overload không nhận mode yêu cầu chuyển chính xác; đầu vào cần bỏ phần khác 0 nên ném `ArithmeticException`.
6. Dùng `compareTo` và kiểm tra kết quả bằng 0.
