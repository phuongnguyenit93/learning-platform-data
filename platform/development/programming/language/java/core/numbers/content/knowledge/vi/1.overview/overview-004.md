# Phạm vi giá trị khác độ chính xác như thế nào trong Java?

Hai khái niệm trả lời **hai câu hỏi khác nhau**:

- **Phạm vi giá trị (range):** Kiểu dữ liệu có thể biểu diễn các giá trị nhỏ nhất, lớn nhất nào? Một phép tính có vượt khỏi miền biểu diễn hay không?
- **Độ chính xác (precision):** Trong phạm vi đó, kiểu dữ liệu phân biệt được các giá trị sát nhau đến mức nào? Có bao nhiêu chữ số có nghĩa được giữ lại khi lưu và tính toán?

Một kiểu có phạm vi rất rộng vẫn có thể có độ chính xác hữu hạn. Đặc biệt, `double` biểu diễn được các số lớn hơn `int` rất nhiều, nhưng **không biểu diễn chính xác mọi số nguyên hoặc mọi số thập phân** trong phạm vi ấy.

## 1. Đối với số nguyên: giới hạn miền giá trị, biểu diễn chính xác trong miền

Các kiểu số nguyên nguyên thủy của Java sử dụng số bit cố định:

| Kiểu | Số bit | Phạm vi giá trị |
| --- | ---: | --- |
| `byte` | 8 | -128 đến 127 |
| `short` | 16 | -32.768 đến 32.767 |
| `int` | 32 | -2.147.483.648 đến 2.147.483.647 |
| `long` | 64 | -9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 |

- Mỗi giá trị **nguyên** nằm trong phạm vi của kiểu đều được lưu chính xác: `int` biểu diễn được `1_000_000` và `1_000_001` thành hai giá trị khác nhau.
- Giới hạn ở đây là **phạm vi**, không phải hiện tượng làm tròn một giá trị còn nằm trong miền. Kiểu `int` không chứa được một số nguyên lớn hơn `Integer.MAX_VALUE`.
- Phép cộng, trừ, nhân số nguyên nguyên thủy có thể **tràn số (overflow)**: kết quả tính theo các bit của kiểu và có thể đổi dấu. Java không tự động mở rộng từ `int` sang `long` để giữ kết quả; muốn tính với `long`, hãy chuyển toán hạng trước khi phép tính diễn ra.
- Dùng `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact` hoặc `Math.toIntExact` để phát hiện các trường hợp tràn số phù hợp. Với số nguyên vượt 64 bit, cân nhắc `BigInteger`.

**Ví dụ:** `Integer.MAX_VALUE + 1` cho `-2_147_483_648` do tràn `int`. Đây không phải lỗi làm tròn vì thiếu chữ số thập phân: kết quả toán học đã vượt phạm vi `int`.

> `char` cũng chứa 16 bit không dấu (từ `'\u0000'` đến `'\uffff'`), nhưng là một **đơn vị mã UTF-16** và không nên coi là kiểu số nguyên dùng cho tính toán thông thường.

## 2. Đối với số thực: phạm vi rộng nhưng độ chính xác hữu hạn

`float` (32 bit) và `double` (64 bit) sử dụng biểu diễn dấu phẩy động nhị phân theo IEEE 754. Số bit được phân bổ cho **dấu**, **số mũ** và **phần trị (significand)**:

- **Số mũ** giúp biểu diễn các giá trị có độ lớn rất khác nhau; đây là một lý do phạm vi của số thực rộng.
- **Phần trị** chứa hữu hạn bit nên chỉ biểu diễn được một tập giá trị rời rạc. Những số nằm giữa hai giá trị biểu diễn được thường phải **làm tròn** sang một trong hai.
- Khoảng cách giữa hai số thực biểu diễn được kề nhau (thường gọi là **ULP**, *unit in the last place*) **thay đổi theo độ lớn**. Gần giá trị lớn, khoảng cách lớn hơn; gần 0, khoảng cách thường nhỏ hơn. Ở vùng số *subnormal*, độ chính xác tương đối giảm.

| Thuộc tính | `float` | `double` |
| --- | --- | --- |
| Số bit toàn bộ | 32 | 64 |
| Số bit phần trị hiệu dụng của số chuẩn hóa | 24 | 53 |
| Độ chính xác thập phân thường dùng để ước lượng | khoảng 7 chữ số có nghĩa | khoảng 15–16 chữ số có nghĩa |
| Trị tuyệt đối hữu hạn lớn nhất | khoảng `3.4028235E38` | khoảng `1.7976931348623157E308` |
| Số dương khác 0 nhỏ nhất (*subnormal*) | khoảng `1.4E-45` | khoảng `4.9E-324` |
| Mọi số nguyên liên tiếp đều chính xác đến | `2^24 = 16_777_216` | `2^53 = 9_007_199_254_740_992` |

Các mốc `2^24` và `2^53` nói rằng **mọi số nguyên trong đoạn tương ứng đều biểu diễn chính xác**; chúng không có nghĩa mọi số nguyên lớn hơn đều sai. Chẳng hạn, các số chẵn đủ gần `2^24` vẫn có thể được lưu chính xác bằng `float`, nhưng số nguyên liền kề ở giữa có thể không.

**Phân biệt “chữ số có nghĩa” và “chữ số sau dấu phẩy”:** Với `double`, độ chính xác xấp xỉ 15–16 **chữ số có nghĩa cho cả số**, không phải luôn có 15–16 chữ số *sau dấu phẩy*. Số `1_000_000_000_000_000` dùng nhiều chữ số có nghĩa hơn số `1.0`; khoảng cách tới số `double` kế tiếp phụ thuộc bậc độ lớn.

Lưu ý về các hằng Java:

- `Float.MAX_VALUE` / `Double.MAX_VALUE`: số **dương hữu hạn lớn nhất**; số âm hữu hạn nhỏ nhất theo thứ tự số học là `-Float.MAX_VALUE` / `-Double.MAX_VALUE`.
- `Float.MIN_VALUE` / `Double.MIN_VALUE`: số **dương khác 0 nhỏ nhất**, **không** phải số âm nhỏ nhất. `MIN_NORMAL` là số dương *chuẩn hóa* nhỏ nhất.
- `Float.POSITIVE_INFINITY`, `Double.NEGATIVE_INFINITY` và `NaN` là các giá trị đặc biệt. Chúng không phải số hữu hạn nằm giữa `-MAX_VALUE` và `MAX_VALUE`.

### Vì sao một `double` rất lớn lại có thể “bỏ qua” `+1`?

`double` chứa 53 bit độ chính xác phần trị, nhưng phải biểu diễn cả những số có bậc độ lớn đến khoảng `10^308`. Gần `1.0E16`, hai số `double` kề nhau cách nhau **2**; vì thế `1.0E16 + 1` được làm tròn trở lại `1.0E16`. Trong khi đó, gần `1.0`, `Math.ulp(1.0)` chỉ khoảng `2.22E-16`.

Đây là **mất độ phân giải**, không phải tràn phạm vi. Cả `1.0E16` và `1.0E16 + 1` đều rất nhỏ so với `Double.MAX_VALUE`, nhưng `double` không giữ được hai giá trị ấy như hai số phân biệt.

### Vì sao `0.1 + 0.2` không bằng chính xác `0.3`?

Phần lớn phân số thập phân, gồm `0.1`, không có biểu diễn nhị phân hữu hạn. Ngay từ khi lưu literal `0.1` hoặc `0.2` vào `double`, giá trị thực tế đã là một số nhị phân gần đúng. Sau phép cộng, kết quả được làm tròn thêm nên phép so sánh bằng chính xác:

`0.1 + 0.2 == 0.3`

trả về `false`. **Phạm vi số thực không phải vấn đề ở đây**: cả ba số đều rất nhỏ và nằm trong miền biểu diễn. Vấn đề là **độ chính xác biểu diễn và làm tròn**.

## 3. Chạy thử: quan sát range, overflow, precision và decimal

Tạo tệp `RangePrecisionDemo.java` (Java 17 trở lên):

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class RangePrecisionDemo {
    public static void main(String[] args) {
        System.out.println("byte: " + Byte.MIN_VALUE + " .. " + Byte.MAX_VALUE);
        System.out.println("int: " + Integer.MIN_VALUE + " .. " + Integer.MAX_VALUE);
        System.out.println("int overflow: " + (Integer.MAX_VALUE + 1));
        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException e) {
            System.out.println("addExact: overflow detected");
        }

        float f = 16_777_216f;
        System.out.println("float keeps +1? " + (f + 1 == f));
        double d = 1e16;
        System.out.println("double keeps +1? " + (d + 1 == d));
        System.out.println("0.1 + 0.2 == 0.3? " + (0.1 + 0.2 == 0.3));
        System.out.println("ulp(1.0): " + Math.ulp(1.0));
        System.out.println("double infinity: " + Double.isInfinite(1e308 * 10));

        BigDecimal a = new BigDecimal("0.1");
        BigDecimal b = new BigDecimal("0.2");
        System.out.println("BigDecimal sum: " + a.add(b));
        BigDecimal x = new BigDecimal("123.4500");
        System.out.println("precision=" + x.precision() + ", scale=" + x.scale());
        BigDecimal thirds = BigDecimal.ONE.divide(
            new BigDecimal("3"), new MathContext(5, RoundingMode.HALF_UP));
        System.out.println("1 / 3 (5 digits): " + thirds);
    }
}
```

Biên dịch và chạy:

```bash
javac RangePrecisionDemo.java
java RangePrecisionDemo
```

Đầu ra đã kiểm tra với JDK 21 (chương trình chỉ dùng API có từ Java 17):

```text
byte: -128 .. 127
int: -2147483648 .. 2147483647
int overflow: -2147483648
addExact: overflow detected
float keeps +1? true
double keeps +1? true
0.1 + 0.2 == 0.3? false
ulp(1.0): 2.220446049250313E-16
double infinity: true
BigDecimal sum: 0.3
precision=7, scale=4
1 / 3 (5 digits): 0.33333
```

Cách đọc kết quả:

1. `int overflow`: vượt **phạm vi**; `Math.addExact` phát hiện bằng ngoại lệ thay vì cho kết quả quấn vòng.
2. `float keeps +1? true`: `16_777_216f + 1` được làm tròn về `16_777_216f`; `float` chưa vượt phạm vi, nhưng không giữ được bước tăng bằng 1.
3. `double keeps +1? true`: điều tương tự xảy ra với `double` ở độ lớn `10^16`.
4. `0.1 + 0.2 == 0.3? false`: phép tính thập phân nhìn đơn giản nhưng các toán hạng ở dạng nhị phân gần đúng.
5. `Math.ulp(1.0)` đo khoảng cách tới số `double` kề tiếp ở gần `1.0`.
6. `double infinity: true`: phép nhân vượt số hữu hạn lớn nhất dẫn đến `+Infinity`; đây là **overflow số thực**, khác với làm tròn mất `+1`.
7. `BigDecimal` tính tổng số thập phân đầu vào chính xác. Nhưng phép chia `1 / 3` không có khai triển thập phân hữu hạn, vì vậy phải chủ động chọn độ chính xác và quy tắc làm tròn.

## 4. Precision, scale và rounding của BigDecimal có giống float/double không?

`BigDecimal` lưu một **số nguyên không chia tỷ lệ** cùng với `scale` (số chữ số thập phân theo cách biểu diễn cơ số 10). Nó không chịu độ chính xác nhị phân cố định 24/53 bit như `float` và `double`:

- `new BigDecimal("123.4500").precision()` = `7`: có bảy chữ số trong số nguyên không chia tỷ lệ `1234500`.
- `new BigDecimal("123.4500").scale()` = `4`: có bốn vị trí sau dấu phẩy theo biểu diễn đang giữ.
- `precision` **khác** `scale`. Một giá trị có thể có scale lớn mà không có nhiều chữ số có nghĩa, hoặc ngược lại.
- Không truyền `MathContext` thì phép cộng/trừ/nhân `BigDecimal` thường cho kết quả thập phân chính xác, với giới hạn thực tế về bộ nhớ và độ lớn scale. Chia một số cho một số khác mà có phần thập phân vô hạn, như `1 / 3`, cần chỉ rõ `MathContext` hoặc scale và `RoundingMode`; nếu dùng `divide` đòi hỏi kết quả chính xác mà không thể kết thúc, Java ném `ArithmeticException`.
- Khi cần làm tròn để hiển thị tiền có hai chữ số sau dấu phẩy, có thể dùng `amount.setScale(2, RoundingMode.HALF_UP)` (chỉ là một chính sách làm tròn; quy định nghiệp vụ có thể yêu cầu cách khác).
- `new BigDecimal("0.1")` giữ đúng số thập phân `0.1`. `new BigDecimal(0.1)` lại nhận **giá trị double nhị phân gần đúng**; vì vậy nên khởi tạo từ `String` hoặc một dạng nhập thập phân tin cậy. `BigDecimal.valueOf(0.1)` sử dụng biểu diễn chuỗi của `double`, nhưng không thể khôi phục thông tin đã mất nếu dữ liệu bị làm tròn từ trước.

`BigDecimal.equals` còn xét cả scale: `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` là `false`, trong khi `compareTo` cho kết quả `0` vì hai giá trị bằng nhau về mặt số học. Đây là vấn đề **ngữ nghĩa biểu diễn và so sánh**, không phải khác phạm vi.

`BigInteger` giải quyết bài toán **phạm vi số nguyên** khi `long` không đủ; `BigDecimal` giải quyết bài toán **biểu diễn thập phân và kiểm soát làm tròn**. Cả hai vẫn chịu giới hạn tài nguyên thực tế.

## 5. Chọn kiểu dữ liệu đúng theo yêu cầu

| Nhu cầu | Gợi ý | Lý do |
| --- | --- | --- |
| Đếm, chỉ số, số lượng nằm trong miền `int` | `int` | Mọi số nguyên hợp lệ đều chính xác, chi phí gọn |
| Số nguyên lớn hơn miền `int` nhưng vừa `long` | `long` | Mở rộng phạm vi; nhớ tính bằng toán hạng `long` trước khi tràn |
| Số nguyên lớn hơn cả `long` | `BigInteger` | Không có giới hạn cố định 64 bit |
| Đo lường, mô phỏng, tính toán khoa học chấp nhận sai số | Thường là `double` | Phạm vi rộng và độ chính xác nhị phân cao hơn `float` |
| Tối ưu bộ nhớ cho dữ liệu thực lớn khi sai số chấp nhận được | `float` sau khi đánh giá sai số | 32 bit nhưng độ chính xác thấp hơn `double` |
| Tiền tệ, thuế, giá và quy tắc làm tròn thập phân | `BigDecimal`, với scale/rounding được quy định | Tránh sai lệch do biểu diễn nhị phân của `0.1`, `0.2` |
| Lưu tiền ở đơn vị nhỏ nhất, ví dụ số xu, khi miền giá trị cho phép | `long` hoặc `int` | Số nguyên chính xác; phải quy định đơn vị và xử lý chuyển đổi |

Khi xử lý `double`/`float`, tránh so sánh `==` nếu ý định là “gần bằng về mặt toán học” sau tính toán. Có thể dùng sai số tuyệt đối và/hoặc tương đối theo miền giá trị; ngưỡng sai số phải xuất phát từ yêu cầu bài toán. `Math.ulp(value)` hữu ích khi muốn hiểu độ phân giải của biểu diễn tại một giá trị nhất định. Ngoại lệ: so sánh chính xác vẫn hợp lệ khi đó là đúng ngữ nghĩa mong muốn (ví dụ kiểm tra một giá trị đã được gán trực tiếp hoặc kiểm tra cờ trạng thái đặc biệt).

## 6. Các nhầm lẫn thường gặp

1. **“`double` có phạm vi lớn hơn `long` nên lưu chính xác mọi `long`.”** Sai: từ `2^53 + 1` trở đi, không phải mọi số nguyên kề nhau đều phân biệt được bằng `double`. Ép một `long` lớn sang `double` có thể làm mất chữ số dù không overflow.
2. **“`double` chính xác đến 16 chữ số thập phân sau dấu phẩy.”** Sai: thường nói đến khoảng 15–16 **chữ số có nghĩa**, và độ phân giải phụ thuộc độ lớn.
3. **“`Double.MIN_VALUE` là số âm nhất.”** Sai: nó là số dương khác 0 nhỏ nhất; số âm hữu hạn thấp nhất là `-Double.MAX_VALUE`.
4. **“Tính `0.1 + 0.2` sai do vượt phạm vi.”** Sai: đó là sai số biểu diễn/làm tròn trong miền; tràn số thực mới có thể tạo `Infinity`.
5. **“Ép kiểu sau phép tính sẽ tránh overflow.”** Sai: `long result = (long) (Integer.MAX_VALUE + 1);` vẫn overflow ở phép cộng `int` trước khi ép. Cần `(long) Integer.MAX_VALUE + 1` hoặc `1L`.
6. **“Thêm nhiều chữ số vào literal `double` sẽ làm nó chính xác tùy ý.”** Sai: một `double` chỉ giữ số bit phần trị cố định; cú pháp literal không mở rộng precision.
7. **“`BigDecimal` luôn chia chính xác và không cần làm tròn.”** Sai đối với thương thập phân vô hạn, chẳng hạn `1 / 3`.
8. **“`1 / 3` ra `0` vì `int` thiếu precision.”** Cần phân biệt: Java dùng **phép chia số nguyên** khi cả hai toán hạng là số nguyên, nên phần dư bị bỏ theo quy tắc phép toán. Viết `1.0 / 3` để thực hiện phép chia số thực, nhưng kết quả vẫn là xấp xỉ nhị phân.

## 7. Tự kiểm tra

- Nếu muốn lưu mọi số nguyên từ `0` đến `1_000_000_000` một cách chính xác, `int` có đủ **phạm vi** không? **Có**, và các giá trị hợp lệ đều biểu diễn chính xác.
- `double` có thể lưu giá trị khoảng `10^100` không? **Có**, vì nằm trong phạm vi hữu hạn; nhưng không có nghĩa giữ chính xác mọi chữ số của giá trị đó.
- Vì sao `16_777_216f + 1 == 16_777_216f`? **Vì độ phân giải của `float` ở vùng đó không còn phân biệt bước tăng 1**, dù chưa vượt phạm vi.
- Khi cần tính `0.1 + 0.2` chính xác bằng thập phân trong nghiệp vụ tiền, nên dùng gì? **`BigDecimal` khởi tạo từ chuỗi thập phân**, cùng chính sách làm tròn rõ ràng khi cần.

**Ghi nhớ:** *Phạm vi* nói về **giá trị xa đến đâu**; *độ chính xác* nói về **các giá trị gần nhau phân biệt được đến mức nào**. Với số nguyên Java, mọi giá trị trong miền đều chính xác; với số dấu phẩy động, miền có thể cực rộng nhưng độ phân giải hữu hạn và thay đổi theo độ lớn.
