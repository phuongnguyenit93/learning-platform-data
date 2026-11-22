# StrictMath.absExact và lựa chọn hợp đồng toán học trong Java 15+

## 1. Mục tiêu: giá trị tuyệt đối phải có hợp đồng rõ ràng

Khi lấy trị tuyệt đối của số nguyên, ta thường mong kết quả không âm: `|-7| = 7`, `|0| = 0`. Tuy nhiên, các kiểu nguyên có dấu `int` và `long` của Java có **một giá trị âm nhiều hơn số giá trị dương**. Vì vậy, trị tuyệt đối của số âm nhỏ nhất **không thể biểu diễn** bằng cùng kiểu dữ liệu.

Từ **Java 15**, `StrictMath.absExact(int)` và `StrictMath.absExact(long)` giải quyết tình huống này bằng hợp đồng: **trả về trị tuyệt đối đúng nếu còn nằm trong miền biểu diễn; nếu vượt miền, ném `ArithmeticException`**. Hai phương thức vẫn tồn tại trong Java hiện hành.

Đây là một quyết định về **hợp đồng tính toán**: khi giá trị không thể biểu diễn đúng, ứng dụng cần phát hiện lỗi, đổi sang kiểu rộng hơn, hay chấp nhận hành vi số nguyên có dấu của phép toán thông thường? Tên lớp `StrictMath` không tự động quyết định đáp án; chính lựa chọn phương thức và kiểu dữ liệu mới quyết định.

Bài học tập trung vào `StrictMath.absExact`, đối chiếu `Math.abs`/`Math.absExact`, cách xử lý biên `MIN_VALUE`, và cách chọn một chính sách phù hợp cho phép toán thực tế.

## 2. API và hành vi chính xác

Hai overload (phương thức cùng tên, khác kiểu tham số) được cung cấp trong `java.lang.StrictMath`:

```java
public static int absExact(int a)
public static long absExact(long a)
```

`StrictMath` thuộc `java.lang` nên có thể gọi trực tiếp dưới dạng `StrictMath.absExact(value)` mà không cần `import`. Phương thức **trả đúng cùng kiểu** với đối số:

- `StrictMath.absExact(7)` → `int` mang giá trị `7`.
- `StrictMath.absExact(-7)` → `int` mang giá trị `7`.
- `StrictMath.absExact(0)` → `int` mang giá trị `0`.
- `StrictMath.absExact(-7L)` → `long` mang giá trị `7L`.
- `StrictMath.absExact(Integer.MIN_VALUE)` → **ném `ArithmeticException`**.
- `StrictMath.absExact(Long.MIN_VALUE)` → **ném `ArithmeticException`**.

Không có overload `absExact(float)` hoặc `absExact(double)`. Đây là API kiểm tra khả năng biểu diễn trị tuyệt đối của **số nguyên `int`/`long`**, không phải lời hứa về độ chính xác thập phân của số thực.

### Vì sao chính xác một giá trị đặc biệt bị lỗi?

Java dùng số nguyên có dấu dạng bù hai (*two's complement*):

| Kiểu | Giá trị nhỏ nhất | Giá trị lớn nhất | Trị tuyệt đối của MIN_VALUE |
|---|---:|---:|---:|
| `int` (32 bit) | −2.147.483.648 | 2.147.483.647 | **2.147.483.648**: lớn hơn `Integer.MAX_VALUE` |
| `long` (64 bit) | −9.223.372.036.854.775.808 | 9.223.372.036.854.775.807 | **9.223.372.036.854.775.808**: lớn hơn `Long.MAX_VALUE` |

Ví dụ, `Integer.MIN_VALUE == -2147483648`, nhưng `2147483648` không thể biểu diễn bằng `int`. Cùng một lý do áp dụng cho `Long.MIN_VALUE`.

**Điểm cần nhớ:** `absExact` không làm miền số nguyên lớn thêm; nó chỉ **không cho phép phép tính trả về một kết quả sai mà không thông báo**.

## 3. So sánh `abs` và `absExact`

Đặt `x = Integer.MIN_VALUE`. Hai lệnh nhìn giống nhau nhưng có hợp đồng rất khác:

```java
int ordinary = Math.abs(x);             // -2147483648
int checked  = StrictMath.absExact(x);  // ném ArithmeticException
```

Đoạn trên **chỉ là minh họa** và không chạy độc lập vì chưa khai báo `x`; lệnh thứ hai sẽ phát sinh ngoại lệ khi được thực thi.

| Lựa chọn | Kiểu hỗ trợ | Khi gặp `MIN_VALUE` của `int`/`long` | Hợp đồng |
|---|---|---|---|
| `Math.abs(int/long)` | `int`, `long` | Trả về chính giá trị âm `MIN_VALUE` | Trị tuyệt đối với hành vi tràn số nguyên không báo lỗi |
| `StrictMath.abs(int/long)` | `int`, `long` | Cũng trả về chính giá trị âm `MIN_VALUE` | Cùng kết quả ở trường hợp biên này |
| `Math.absExact(int/long)` | `int`, `long` | Ném `ArithmeticException` | Trị tuyệt đối có kiểm tra tràn |
| **`StrictMath.absExact(int/long)`** | **`int`, `long`** | **Ném `ArithmeticException`** | **Cùng hợp đồng chính xác như `Math.absExact`** |
| Đổi `int` thành `long` trước khi `abs` | Giá trị gốc là `int` | Biểu diễn được 2.147.483.648 trong `long` | Giữ nguyên kết quả toán học khi miền rộng hơn đủ chứa |
| `BigInteger.abs()` | `BigInteger` | Biểu diễn được trị tuyệt đối của cả `Long.MIN_VALUE` | Số nguyên độ chính xác tùy ý |

Với các giá trị **khác** `MIN_VALUE`, `abs` và `absExact` trên cùng kiểu nguyên trả **cùng trị tuyệt đối không âm**. Do đó, test chỉ dùng `-10`, `0`, `10` chưa phát hiện được khác biệt hợp đồng.

### Vì sao `Math.abs(MIN_VALUE)` vẫn trả số âm?

Phép đổi dấu của `Integer.MIN_VALUE` theo số học `int` không biểu diễn được giá trị dương tương ứng; kết quả bị tràn và quay về `Integer.MIN_VALUE`. `Math.abs(int)` và `StrictMath.abs(int)` được đặc tả trả về giá trị âm đó trong trường hợp biên, không ném ngoại lệ. `absExact` chủ động từ chối trường hợp này.

Do đó, một giả định như `Math.abs(x) >= 0` **không đúng cho mọi `int`**. Nguy cơ có thể lan sang chỉ số mảng, phép modulo, độ lớn khoản chênh lệch hoặc kiểm tra giới hạn dữ liệu.

## 4. `StrictMath` hay `Math`: chính xác khác với tính tái lập

Nhiều người hiểu tên `StrictMath` thành “mọi phép tính chính xác hơn `Math`”. Cách hiểu đó không đúng.

- **Đối với `absExact(int/long)`**, `Math.absExact` và `StrictMath.absExact` có **cùng hợp đồng về kết quả và ngoại lệ**. Bạn có thể chọn `Math.absExact` cho code số nguyên phổ thông hoặc `StrictMath.absExact` nếu đang dùng nhất quán API `StrictMath`; cả hai đều phát hiện trường hợp `MIN_VALUE`.
- **Đối với một số hàm số thực phức tạp** như `sin`, `cos`, `log`, `pow`, đặc tả `StrictMath` ràng buộc kết quả theo thuật toán tham chiếu `fdlibm` để hỗ trợ tính tái lập. `Math` cho phép một số hiện thực tối ưu hóa có thể khác ở vài bit cuối nhưng vẫn đáp ứng giới hạn sai số được quy định.
- **`absExact` không phải phép toán số thực**, vì vậy không có lý do chọn nó chỉ để mong độ chính xác dấu phẩy động tốt hơn hoặc một thuật toán `fdlibm`.

Hãy tách hai câu hỏi:

1. **Số nguyên có được phép tràn hay phải báo lỗi?** → lựa chọn `abs` hay `absExact`, miền `int`/`long` hay `BigInteger`.
2. **Hàm số thực có yêu cầu tính tái lập bit-for-bit theo đặc tả riêng không?** → khi thực sự tính `sin`, `log`, `pow`, hãy xét hợp đồng của `StrictMath`/`Math` cho chính hàm đó.

Không nên viện dẫn đặc tính của `StrictMath.sin` để khẳng định `StrictMath.absExact` khác `Math.absExact` về tính đúng đắn số nguyên.

## 5. Ví dụ Java hoàn chỉnh: kiểm tra cả biên và phép tính trung gian

Chương trình sau biên dịch/chạy được với **Java 17+**; các API đang dùng đã có từ Java 15 hoặc sớm hơn. Lưu đúng tên **`AbsExactDemo.java`**:

```java
import java.math.BigInteger;

public class AbsExactDemo {
    private static String absInt(int value) {
        try {
            return Integer.toString(StrictMath.absExact(value));
        } catch (ArithmeticException exception) {
            return "OVERFLOW";
        }
    }

    private static String absLong(long value) {
        try {
            return Long.toString(StrictMath.absExact(value));
        } catch (ArithmeticException exception) {
            return "OVERFLOW";
        }
    }

    public static void main(String[] args) {
        System.out.println("int -7=" + absInt(-7));
        System.out.println("int 0=" + absInt(0));
        System.out.println("int MIN=" + absInt(Integer.MIN_VALUE));
        System.out.println("long MIN=" + absLong(Long.MIN_VALUE));
        System.out.println("Math.abs(int MIN)=" + Math.abs(Integer.MIN_VALUE));
        System.out.println("widen int MIN=" + StrictMath.absExact((long) Integer.MIN_VALUE));
        System.out.println("BigInteger abs(long MIN)="
                + BigInteger.valueOf(Long.MIN_VALUE).abs());
        System.out.println("StrictMath vs Math="
                + (StrictMath.absExact(-11L) == Math.absExact(-11L)));

        int left = Integer.MIN_VALUE;
        int right = Integer.MAX_VALUE;
        System.out.println("int-pair distance="
                + Math.absExact((long) left - right));

        long wrapped = Long.MAX_VALUE - Long.MIN_VALUE;
        System.out.println("wrapped-before-abs=" + Math.absExact(wrapped));
        BigInteger exactDistance = BigInteger.valueOf(Long.MAX_VALUE)
                .subtract(BigInteger.valueOf(Long.MIN_VALUE)).abs();
        System.out.println("full-long distance=" + exactDistance);
    }
}
```

Chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 AbsExactDemo.java
java AbsExactDemo
```

**Stdout chính xác:**

```text
int -7=7
int 0=0
int MIN=OVERFLOW
long MIN=OVERFLOW
Math.abs(int MIN)=-2147483648
widen int MIN=2147483648
BigInteger abs(long MIN)=9223372036854775808
StrictMath vs Math=true
int-pair distance=4294967295
wrapped-before-abs=1
full-long distance=18446744073709551615
```

Phân tích kết quả:

- `absInt` và `absLong` bắt ngoại lệ chỉ để **minh họa một chính sách thông báo lỗi**: trả chữ `OVERFLOW`. Trong ứng dụng thật cần quyết định trả lỗi nghiệp vụ, ghi nhận lỗi đầu vào hay xử lý bằng kiểu rộng hơn.
- `Math.abs(Integer.MIN_VALUE)` trả lại số âm, đúng theo API `abs`; `StrictMath.absExact` chủ động ném ngoại lệ.
- Ép `int` sang `long` **trước** khi lấy trị tuyệt đối giúp nhận kết quả `2147483648`.
- `BigInteger.valueOf(Long.MIN_VALUE).abs()` cho kết quả đúng `9223372036854775808`, lớn hơn `Long.MAX_VALUE`.
- `int-pair distance` ra `4294967295` vì hai đầu mút `int` được trừ trong miền `long`.
- `wrapped-before-abs=1` là **bẫy quan trọng**: `Long.MAX_VALUE - Long.MIN_VALUE` đã tràn thành `-1L` **trước khi** `absExact` được gọi. `absExact(-1L)` hợp lệ nên trả `1`; nó không thể phát hiện một phép tính trước đó đã tràn.
- `full-long distance` dùng `BigInteger` từ **trước bước trừ**, nên cho đúng khoảng cách `18446744073709551615`.

**Không rút ra kết luận sai từ output** `StrictMath vs Math=true`: dòng đó chỉ kiểm tra một đầu vào. Kết luận hai API có cùng hợp đồng `absExact` dựa vào tài liệu chuẩn, không dựa vào một mẫu thử.

## 6. Lựa chọn theo hợp đồng nghiệp vụ

| Nhu cầu/giả định hợp lệ | Cách chọn | Điều cần đảm bảo |
|---|---|---|
| Kết quả `int` hoặc `long` **bắt buộc** biểu diễn đúng, tràn phải báo lỗi | `StrictMath.absExact(value)` hoặc `Math.absExact(value)` | Xử lý `ArithmeticException` ở ranh giới thích hợp; kiểm thử `MIN_VALUE` |
| Giá trị gốc là `int` bất kỳ, muốn trị tuyệt đối không âm đầy đủ | `StrictMath.absExact((long) value)` | Ép kiểu **trước** phép tính; kết quả là `long` |
| Giá trị gốc là `long` bất kỳ, muốn trị tuyệt đối không âm đầy đủ | `BigInteger.valueOf(value).abs()` | Kết quả `BigInteger`, có thể lớn hơn `Long.MAX_VALUE` |
| Hệ thống chấp nhận rõ hành vi số nguyên của `abs` tại `MIN_VALUE` | `Math.abs(value)` hoặc `StrictMath.abs(value)` | Không giả định đầu ra luôn không âm; chính sách này phải được đặc tả rõ |
| Muốn trả `MAX_VALUE` khi vượt miền (*saturating*) | Kiểm tra `MIN_VALUE` tường minh rồi chọn `MAX_VALUE`; nếu không, gọi `abs` | Đây là **chính sách do ứng dụng tự định nghĩa**, không phải hành vi của `absExact` |
| Cần độ lớn của kết quả phép trừ/cộng/nhân mà trung gian có thể tràn | Dùng kiểu đủ rộng, `BigInteger`, hoặc phép `addExact`/`subtractExact`/`multiplyExact` thích hợp | **Kiểm tra từ phép tính trung gian**, không trông chờ `absExact` sửa lỗi đã xảy ra |

Ví dụ chính sách bão hòa (đặt bên trong một lớp Java) nếu nghiệp vụ **thật sự quy định** rằng giá trị vượt miền được kẹp về `Integer.MAX_VALUE`:

```java
static int saturatingAbs(int value) {
    return value == Integer.MIN_VALUE
            ? Integer.MAX_VALUE
            : Math.abs(value);
}
```

Hàm này **không trả trị tuyệt đối toán học đúng** cho `Integer.MIN_VALUE`: nó chọn `2147483647` theo hợp đồng bão hòa. Đừng dùng nó trong báo cáo tài chính/đo lường nếu yêu cầu giá trị chính xác. Nếu đầu vào `MIN_VALUE` là dữ liệu không hợp lệ theo miền nghiệp vụ, hãy từ chối rõ ràng thay vì âm thầm kẹp số.

## 7. Bẫy chuyển kiểu và phép tính trung gian

### 7.1. Ép kiểu quá muộn

```java
int value = Integer.MIN_VALUE;
long wrong = Math.abs(value);           // -2147483648, sau đó mới chuyển sang long
long correct = Math.abs((long) value);  // 2147483648
```

Cách viết `(long) Math.abs(value)` cũng **sai về thời điểm ép kiểu**: `Math.abs(int)` đã tạo giá trị âm sai trước, sau đó mới được đưa sang `long`. Hãy **ép kiểu đầu vào trước khi gọi hàm**.

Khi cần hợp đồng báo lỗi trên kiểu rộng, `Math.absExact((long) value)` hoặc `StrictMath.absExact((long) value)` đều hợp lệ và không tràn với bất kỳ giá trị `int` nào.

### 7.2. Phép trừ tràn trước khi lấy trị tuyệt đối

```java
int a = Integer.MIN_VALUE;
int b = Integer.MAX_VALUE;

long wrong = Math.absExact((long) (a - b));
long correct = Math.absExact((long) a - b);
```

Ở `wrong`, `a - b` diễn ra ở kiểu `int`, đã tràn trước lúc ép `long`. Kết quả tràn cụ thể là `1`; `absExact(1L)` không có lý do ném ngoại lệ. Ở `correct`, toán hạng `a` chuyển sang `long` trước khi trừ, nên thu được `-4294967295L`, trị tuyệt đối là `4294967295L`.

Với **hai giá trị `long` bất kỳ**, ngay cả phép trừ `long` cũng có thể tràn. Tùy hợp đồng:

- Muốn **phát hiện** tràn trong từng bước nhưng vẫn giới hạn kết quả ở `long`:

```java
long difference = Math.subtractExact(aLong, bLong);
long magnitude = Math.absExact(difference);
```

Đây là đoạn **minh họa nằm trong phương thức có hai biến `long aLong, bLong`**. `subtractExact` phát hiện tràn khi trừ; `absExact` phát hiện nếu kết quả trừ đúng bằng `Long.MIN_VALUE`.

- Muốn **tính được kết quả toán học**, ngay cả khi khoảng cách lớn hơn `Long.MAX_VALUE`:

```java
BigInteger distance = BigInteger.valueOf(aLong)
        .subtract(BigInteger.valueOf(bLong))
        .abs();
```

Đoạn trên cần `import java.math.BigInteger;` và cũng giả định đã có hai biến `long aLong, bLong`. Hãy chuyển sang `BigInteger` **trước khi trừ**, không lấy giá trị `long` đã tràn rồi mới chuyển.

### 7.3. Đổi `BigInteger` trở lại kiểu nguyên cần kiểm tra

`BigInteger.valueOf(Long.MIN_VALUE).abs()` không thể chứa trong `long`. Khi buộc phải chuyển sang `long`, `longValueExact()` sẽ ném `ArithmeticException` nếu ngoài miền; `longValue()` có thể làm mất thông tin. Giữ `BigInteger` hoặc chọn xử lý lỗi chuyển kiểu có chủ đích.

## 8. `absExact` không dành cho số thực

Java cung cấp `Math.abs(float/double)` và `StrictMath.abs(float/double)`, nhưng **không** cung cấp `absExact(float/double)`.

Một số trường hợp số thực phải được xử lý theo hợp đồng riêng:

- `Math.abs(-0.0d)` cho `+0.0d` (dấu âm của zero được loại).
- `Math.abs(Double.NaN)` vẫn là NaN; `Math.abs(Double.NEGATIVE_INFINITY)` cho dương vô cực.
- Với ràng buộc “chỉ chấp nhận số hữu hạn”, cần kiểm tra `Double.isFinite(value)`; lấy trị tuyệt đối **không tự xác thực** điều kiện này.
- Với phép toán tiền/tỷ lệ cần biểu diễn thập phân kiểm soát, `BigDecimal` và chính sách scale/rounding thích hợp hơn việc cho rằng `StrictMath` sẽ làm `double` thành số thập phân chính xác.

Đừng nhầm **“exact” là kiểm tra overflow số nguyên** với **“reproducible” là hợp đồng của một số hàm floating-point**. Hai vấn đề khác nhau.

## 9. Kiểm thử biên và cách xử lý ngoại lệ

Với một hàm dùng `StrictMath.absExact`, bộ trường hợp tối thiểu nên bao gồm:

| Đầu vào | Kỳ vọng |
|---|---|
| `0` | `0` |
| `1` và `-1` | `1` |
| `Integer.MAX_VALUE` | `2147483647` |
| `Integer.MIN_VALUE + 1` | `2147483647` |
| **`Integer.MIN_VALUE`** | **`ArithmeticException`** |
| `Long.MAX_VALUE` | `9223372036854775807L` |
| **`Long.MIN_VALUE`** | **`ArithmeticException`** |

Trong kiểm thử JUnit hiện hành, có thể dùng `assertThrows(ArithmeticException.class, () -> StrictMath.absExact(Integer.MIN_VALUE))`; đoạn này là minh họa trong một test có `import static org.junit.jupiter.api.Assertions.assertThrows;`, không phải chương trình Java độc lập. Bộ test cần kiểm tra cả **kiểu trả về** `int`/`long` và **ngữ nghĩa khi tràn**, không chỉ các trường hợp thông thường.

Ở tầng nghiệp vụ, nếu `absExact` ném ngoại lệ thì **đừng tùy tiện bắt rồi trả 0, -1 hoặc `MAX_VALUE`**: những giá trị đó có thể bị hiểu nhầm là kết quả hợp lệ. Cách xử lý nên dựa trên hợp đồng đã chọn, ví dụ phản hồi lỗi đầu vào có ngữ cảnh, sử dụng kiểu rộng hơn, hoặc trả đối tượng kết quả biểu diễn rõ trường hợp không thể tính.

Cũng không nên dùng `absExact` như kiểm tra duy nhất cho cả một biểu thức phức tạp. Nó chỉ xét **đối số nhận vào tại thời điểm gọi**. Những bước tính có thể tràn trước đó cần được thiết kế/kiểm tra riêng.

## 10. Quy trình ra quyết định ngắn

1. **Xác định miền giá trị đầu vào**: có thể nhận `Integer.MIN_VALUE`/`Long.MIN_VALUE` không? Các phép trừ trước khi lấy `abs` có thể mở rộng miền hay tràn không?
2. **Xác định hợp đồng kết quả**: phải tuyệt đối không âm và chính xác, phải báo lỗi khi không chứa được, hay được phép kẹp về một giới hạn do nghiệp vụ quy định?
3. **Chọn kiểu trước khi tính**: `int` có thể mở lên `long`; trường hợp toàn miền `long` có thể cần `BigInteger`. Ép kiểu **trước** phép toán.
4. **Chọn phương thức**: `StrictMath.absExact`/`Math.absExact` để phát hiện overflow của trị tuyệt đối ở kiểu nguyên; `abs` khi hiểu rõ quy tắc `MIN_VALUE`; `BigInteger.abs` khi cần kết quả ngoài miền.
5. **Kiểm thử đúng biên**: `MIN_VALUE`, `MIN_VALUE + 1`, `MAX_VALUE`, `0`, dấu âm/dương và các phép trừ có khả năng tràn.

**Kết luận kỹ thuật:** `StrictMath.absExact` bổ sung một lựa chọn hợp đồng có kiểm tra tràn từ Java 15 và vẫn có ý nghĩa trong Java hiện hành. Giá trị thực tế của nó nằm ở **việc ném lỗi khi không thể biểu diễn trị tuyệt đối số nguyên**; không phải ở việc tự mở rộng miền kiểu dữ liệu hay cải thiện độ chính xác của phép toán đã tràn.

**Tài liệu chính thức:** [Oracle Java SE 26 — StrictMath](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/StrictMath.html), [Oracle Java SE 26 — Math](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Math.html), [Oracle Java SE 26 — BigInteger](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigInteger.html), [JLS — Integer Types and Values §4.2.1](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.2.1).
