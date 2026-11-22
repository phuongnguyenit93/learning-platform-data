# Nâng kiểu vẫn có thể mất độ chính xác khi chuyển sang float hoặc double trong Java

Trong Java, **nâng kiểu nguyên thủy** (*widening primitive conversion*) không đồng nghĩa với **giữ nguyên giá trị toán học trong mọi trường hợp**. Khi chuyển một số nguyên sang `float` hoặc `double`, kiểu đích có thể có phạm vi giá trị rộng hơn nhưng **không có đủ bit phần trị để biểu diễn chính xác từng số nguyên** trong phạm vi đó.

Hai ví dụ quan trọng:

```java
int integer = 16_777_217;
float approximate = integer;  // Giá trị float thực tế: 16_777_216.0f

long large = 9_007_199_254_740_993L;
double rounded = large;       // Giá trị double thực tế: 9_007_199_254_740_992.0
```

Đây là các mảnh mã hợp lệ bên trong phương thức Java. Không có lỗi biên dịch hoặc `ArithmeticException`: chuyển kiểu được phép, nhưng kết quả **đã bị làm tròn**. Nếu các số biểu diễn số đếm, mã định danh, phiên bản dữ liệu hoặc số tiền ở đơn vị nhỏ nhất, việc mất một đơn vị cũng có thể làm sai nghiệp vụ.

Bài học thuộc phần **Chuyển kiểu** của module **Java core – numbers**, tập trung vào lý do, điều kiện xảy ra, các bẫy khi so sánh và cách bảo toàn dữ liệu khi đổi sang kiểu dấu phẩy động.

## 1. “Nâng kiểu” và “chính xác” là hai thuộc tính khác nhau

Trong Java, chuyển kiểu nguyên thủy được gọi là *widening* nếu nằm trong nhóm chuyển đổi được ngôn ngữ cho phép mở rộng, ví dụ `int → long`, `int → float`, `int → double`, `long → float`, `long → double`, `float → double`. Đa số có thể diễn ra tự động khi gán, truyền tham số hoặc trong biểu thức số học.

Nhưng từ “widening” mô tả **quy tắc chuyển đổi và phạm vi giá trị được hỗ trợ**, không bảo đảm tăng số bit lưu **phần nguyên chính xác**.

| Chuyển đổi | Có giữ chính xác mọi giá trị nguồn? | Giải thích |
| --- | --- | --- |
| `byte → short/int/long` | Có | Số nguyên đích biểu diễn được toàn bộ miền nguồn |
| `short → int/long` | Có | Bảo toàn mọi giá trị |
| `char → int/long` | Có | Mọi giá trị `char` 0–65535 đều biểu diễn được |
| `int → long` | Có | 64 bit nguyên chứa đủ mọi `int` |
| `int → float` | **Không** | `float` chỉ có 24 bit độ chính xác phần trị |
| `int → double` | **Có** | `double` có 53 bit độ chính xác phần trị, đủ cho mọi `int` |
| `long → float` | **Không** | Nhiều `long` phải làm tròn khi vào `float` |
| `long → double` | **Không** | Không đủ 53 bit để biểu diễn mọi số nguyên 64 bit |
| `float → double` | Có, đối với giá trị hữu hạn đã lưu trong `float` | Giá trị nhị phân của `float` được biểu diễn chính xác trong `double`; **không phục hồi** thông tin đã mất trước đó |

Cần phân biệt **độ lớn cực đại** với **độ phân giải**. `float` có thể biểu diễn số có độ lớn vượt xa `Long.MAX_VALUE`, nhưng khi số lớn, các giá trị biểu diễn được cách nhau rất xa. Kiểu có dải giá trị lớn hơn **không nhất thiết** chứa được mọi số nguyên nhỏ hơn ngưỡng lớn nhất ấy.

## 2. Cơ chế: số dấu phẩy động lưu phần trị và số mũ

`float` và `double` trong Java sử dụng biểu diễn dấu phẩy động nhị phân IEEE 754:

- `float`: 32 bit tổng cộng, **24 bit độ chính xác phần trị** (bao gồm bit ẩn ở các số chuẩn hóa).
- `double`: 64 bit tổng cộng, **53 bit độ chính xác phần trị**.
- Phần bit còn lại đảm nhiệm dấu và số mũ; chúng giúp mở rộng **phạm vi độ lớn**, nhưng không làm cho mọi số nguyên trong phạm vi đó đều có biểu diễn chính xác.

Một cách hình dung: khi còn đủ bit phần trị, hai số nguyên liên tiếp như 100 và 101 có thể có hai biểu diễn riêng. Khi tăng tới giá trị lớn, khoảng cách giữa hai số dấu phẩy động liền kề tăng lên 2, 4, 8… đơn vị. Những số nguyên nằm giữa phải được làm tròn đến một giá trị lân cận.

### Mốc 2^24 của float

```text
2^24 = 16_777_216

16_777_216 → float: chính xác
16_777_217 → float: 16_777_216
16_777_218 → float: chính xác
16_777_219 → float: 16_777_220 (làm tròn tới giá trị gần nhất)
```

Ở miền quanh `2^24`, các giá trị `float` liên tiếp cách nhau **2**. `16_777_217` nằm giữa `16_777_216` và `16_777_218`; quy tắc làm tròn đến gần nhất, hòa chọn chữ số cuối chẵn (*round to nearest, ties to even*) chọn `16_777_216` trong trường hợp này.

**Mọi số nguyên từ `-2^24` đến `2^24` đều được biểu diễn chính xác bằng `float`**, nhưng điều đó **không** có nghĩa mọi số nguyên bên ngoài miền đều sai: ví dụ `16_777_218` vẫn biểu diễn chính xác. Mốc này là ngưỡng **bảo đảm liên tục**, không phải ngưỡng “mọi giá trị lớn hơn đều không thể lưu”.

### Mốc 2^53 của double

```text
2^53 = 9_007_199_254_740_992

9_007_199_254_740_992 → double: chính xác
9_007_199_254_740_993 → double: 9_007_199_254_740_992
9_007_199_254_740_994 → double: chính xác
```

Tương tự, mọi số nguyên trong `[-2^53, 2^53]` đều biểu diễn chính xác bằng `double`, nhưng các số nguyên liền kề sau ngưỡng này không còn luôn có biểu diễn riêng. Vì `long` chứa những số nguyên lớn hơn `2^53`, chuyển `long → double` có thể đánh mất chữ số thấp.

Ngưỡng `Number.MAX_SAFE_INTEGER` trong JavaScript là `2^53 - 1`, có liên hệ với khả năng phân biệt liên tiếp của binary64. Điều đó đặc biệt đáng quan tâm nếu dịch vụ Java xuất `long` qua JSON number cho JavaScript.

## 3. Vì sao int → double vẫn chính xác, còn int → float có thể không?

Mọi `int` Java nằm trong miền:

```text
-2_147_483_648 ≤ int ≤ 2_147_483_647
```

Một `double` có 53 bit phần trị, nên biểu diễn được mọi số nguyên 32 bit. Vì vậy:

```java
int source = Integer.MAX_VALUE;
double widened = source;

boolean exact = (long) widened == source; // true
```

Trong ví dụ này có thể cast kết quả về `long` để thấy giá trị nguyên, nhưng chỉ riêng tính chất “mọi `int` đều nằm trong độ chính xác của `double`” đã đủ để kết luận chuyển đổi chính xác.

Với `float`, dù kiểu này có phạm vi độ lớn rất rộng, 24 bit phần trị không đủ chứa mọi `int`. Ví dụ:

```java
int source = 16_777_217;
float widened = source;

int recovered = (int) widened;   // 16_777_216
boolean equal = recovered == source; // false
```

**Thông điệp quan trọng:** số bit tổng cộng của kiểu đích không trực tiếp cho biết số chữ số nguyên được giữ. `double` là 64 bit, `long` cũng 64 bit, nhưng `double` dành bit cho số mũ và dấu nên chỉ có 53 bit độ chính xác phần trị.

## 4. Java làm gì khi một số nguyên không biểu diễn chính xác được?

Việc chuyển `int` hoặc `long` sang `float`/`double` là chuyển đổi được phép và được làm tròn đến giá trị dấu phẩy động biểu diễn được gần nhất theo quy tắc thích hợp của Java. Với các ca đúng giữa hai số lân cận, quy tắc ties to even quyết định kết quả.

```java
int first = 16_777_216;
int second = 16_777_217;

float f1 = first;
float f2 = second;

// Hai số nguyên khác nhau tạo cùng một giá trị float:
boolean collision = f1 == f2; // true
```

Điểm này giải thích vì sao một bộ đếm nguyên **không nên được lưu bằng `float`** chỉ vì `float` có thể chứa số rất lớn. Giá trị đích có thể không thay đổi sau khi cộng 1 ở miền lớn:

```java
float count = 16_777_216f;
count = count + 1f;
// count vẫn là 16_777_216f.
```

Điều này không phải vì phép cộng bị bỏ qua, mà vì kết quả toán học `16_777_217` không biểu diễn chính xác được và bị làm tròn trở lại `16_777_216`.

Các chuyển đổi này không tự phát sinh `ArithmeticException`, và không có cảnh báo bắt buộc từ compiler. Vì vậy cần phân tích đầu vào, chọn kiểu và kiểm thử các giá trị biên thay vì dựa vào việc biên dịch thành công.

## 5. Bẫy khi so sánh: int == float hoặc long == double có thể vẫn true

Một lỗi đặc biệt khó thấy là đem số nguyên gốc so trực tiếp với số thực đã bị làm tròn:

```java
int original = 16_777_217;
float converted = original;

System.out.println(original == converted);         // true
System.out.println(original == (int) converted);   // false
```

Tại sao phép so sánh đầu tiên trả `true`?

Trong biểu thức `original == converted`, Java áp dụng **binary numeric promotion**: toán hạng `int` được chuyển thành `float` để so với `float`. Trong lúc chuyển, `16_777_217` cũng bị làm tròn thành `16_777_216f`. Hai toán hạng lúc so sánh bằng nhau, nhưng **điều đó không chứng minh `float` giữ được số nguyên gốc**.

Tương tự:

```java
long original = 9_007_199_254_740_993L;
double converted = original;

System.out.println(original == converted);        // true
System.out.println(original == (long) converted); // false
```

Không dùng `original == (float) original` hoặc `original == (double) original` làm phép kiểm tra chính xác. Với so sánh hỗn hợp nguyên/dấu phẩy động, chính toán hạng nguyên có thể bị chuyển đổi mất thông tin trước phép so sánh.

### Hai số nguyên khác nhau có thể “bằng nhau” sau chuyển kiểu

```java
long a = 9_007_199_254_740_992L;
long b = 9_007_199_254_740_993L;

boolean integerDifferent = a != b; // true
boolean doubleSame = (double) a == (double) b; // true
```

Nếu một hệ thống chuyển các ID lớn sang `double` rồi dùng chúng làm khóa so sánh, tra cứu hay deduplication, hai định danh khác nhau có thể trở thành một. Hệ quả có thể nặng hơn sai số trong phép đo thông thường.

## 6. Bẫy cast ngược: kiểm tra round-trip cần hiểu quy tắc

Một cách kiểm tra có vẻ hợp lý:

```java
double converted = (double) originalLong;
boolean unchanged = ((long) converted == originalLong);
```

Với `originalLong = 9_007_199_254_740_993L`, phép này trả `false` và phát hiện được mất 1 đơn vị. Tuy nhiên **không nên coi đây là kiểm tra đúng cho mọi `long`**.

Ví dụ:

```java
long originalLong = Long.MAX_VALUE;
double converted = originalLong;

boolean appearsEqual = ((long) converted == originalLong); // true
```

Phân tích:

- `Long.MAX_VALUE` là `9223372036854775807`.
- Giá trị `double` gần nhất khi chuyển có giá trị toán học `9223372036854775808` (`2^63`), **lớn hơn** `Long.MAX_VALUE`.
- Khi chuyển **thu hẹp** từ `double` về `long`, Java cắt phần lẻ và xử lý giá trị nằm ngoài miền theo quy tắc thu hẹp, trong đó giá trị dương quá lớn bị chặn về `Long.MAX_VALUE`.
- Vì thế cast ngược có thể cho lại `Long.MAX_VALUE` dù `double` đã không còn bằng số nguyên gốc!

Phép kiểm tra kiểu `(long) d == original` có thể cho **dương tính giả** tại giới hạn. Bản thân phép cast từ `double` sang `long` không phải một phép chứng minh chính xác.

### Kiểm tra giá trị integer ↔ double bằng biểu diễn chính xác

Trong trường hợp cần biết một `long` cụ thể có chuyển sang `double` **mà không thay đổi giá trị toán học** hay không, có thể so sánh bằng kiểu thập phân chính xác:

```java
import java.math.BigDecimal;

// Phương thức đặt trong một class Java:
static double toDoubleExact(long original) {
    double converted = (double) original;
    BigDecimal fromLong = BigDecimal.valueOf(original);
    BigDecimal exactDoubleValue = new BigDecimal(converted);

    if (fromLong.compareTo(exactDoubleValue) != 0) {
        throw new ArithmeticException("Precision lost converting long to double");
    }
    return converted;
}
```

Ở đây, **`new BigDecimal(converted)` được sử dụng có chủ đích để lấy đúng giá trị nhị phân của `double`**, kể cả khi biểu diễn thập phân dài. Đây là tình huống khác hẳn việc tạo tiền từ `double`; với số tiền, nên tạo `BigDecimal` từ **chuỗi thập phân gốc** thay vì dựa vào một giá trị thực đã bị làm tròn.

`BigDecimal.valueOf(original)` giữ chính xác số nguyên `long`. So sánh hai giá trị thập phân chính xác sẽ phát hiện cả trường hợp `Long.MAX_VALUE` dù cast ngược về `long` cho kết quả có vẻ bằng nhau.

Nếu yêu cầu của ứng dụng là hỗ trợ toàn bộ miền `long` mà không mất thông tin, **không dùng `double` làm kiểu lưu trữ số nguyên đó**. Kiểm tra trên chỉ phù hợp ở nơi có chủ đích cho phép hoặc từ chối từng giá trị cụ thể.

## 7. float → double không phục hồi độ chính xác của đầu vào ban đầu

Đây là một phân biệt quan trọng:

```java
float decimalLike = 0.1f;
double promoted = decimalLike;

System.out.println(promoted); // 0.10000000149011612
```

Bản thân việc chuyển `float → double` **giữ chính xác giá trị nhị phân đã được lưu trong float**. Nhưng literal `0.1f` từ đầu đã không biểu diễn chính xác 1/10 trong hệ nhị phân; `double` chỉ biểu diễn chính xác hơn **giá trị float đã làm tròn**, không biến nó thành 0.1 thập phân toán học.

Tương tự, nếu trước đó một số nguyên đã được lưu qua `float` rồi mới chuyển sang `double`:

```java
int original = 16_777_217;
float intermediate = original;
double later = intermediate;

// later mang giá trị 16_777_216.0; không còn biết số gốc là 16_777_217.
```

Một khi nhiều đầu vào khác nhau đã bị làm tròn thành cùng một giá trị `float`, bước widening tiếp theo **không có thông tin để khôi phục**.

## 8. ULP: khoảng cách giữa các số thực lân cận

`Math.ulp(value)` (*unit in the last place*) cho biết độ lớn một đơn vị ở vị trí bit phần trị thấp nhất quanh một giá trị dấu phẩy động. Nó giúp quan sát **độ phân giải** thay đổi theo độ lớn.

```java
System.out.println(Math.ulp(16_777_216f));          // 2.0
System.out.println(Math.ulp(9_007_199_254_740_992d)); // 2.0
```

Tại những vị trí này, khoảng cách tới số thực biểu diễn kế tiếp về phía lớn hơn là 2 đơn vị. Khi độ lớn tiếp tục tăng, ULP sẽ tăng. Điều đó khiến `float`/`double` vẫn chứa được số lớn nhưng không còn phân biệt được từng đơn vị nhỏ như trước.

Lưu ý ULP là thông tin về độ phân giải, **không tự cung cấp một tiêu chí sai số nghiệp vụ**. Trong bài toán đo lường, sai số cần xét đơn vị và yêu cầu thuật toán. Trong bài toán số đếm hoặc định danh, mất dù chỉ 1 đơn vị có thể không được phép.

## 9. Chương trình Java 17+ chạy độc lập

Tạo file **`WideningPrecisionDemo.java`**. Chương trình kiểm tra những bẫy quan trọng: chuyển `int → float`, `long → double`, so sánh hỗn hợp kiểu, ULP, chuyển `float → double`, cast ngược ở `Long.MAX_VALUE` và hàm chuyển `long` sang `double` có kiểm tra chính xác.

```java
import java.math.BigDecimal;

public class WideningPrecisionDemo {
    static double toDoubleExact(long original) {
        double converted = (double) original;
        BigDecimal fromLong = BigDecimal.valueOf(original);
        BigDecimal exactDoubleValue = new BigDecimal(converted);

        if (fromLong.compareTo(exactDoubleValue) != 0) {
            throw new ArithmeticException("Precision lost");
        }
        return converted;
    }

    public static void main(String[] args) {
        int intSource = 16_777_217;
        float asFloat = intSource;
        System.out.println("int-original=" + intSource);
        System.out.println("float-as-int=" + (int) asFloat);
        System.out.println("int-float-round-trip=" +
                ((int) asFloat == intSource));
        System.out.println("int-equals-float=" + (intSource == asFloat));
        System.out.println("int-to-double-exact=" +
                ((long) (double) Integer.MAX_VALUE == Integer.MAX_VALUE));
        System.out.println("float-ulp-at-2pow24=" +
                Math.ulp(16_777_216f));

        long longSource = 9_007_199_254_740_993L;
        double asDouble = longSource;
        System.out.println("long-original=" + longSource);
        System.out.println("double-as-long=" + (long) asDouble);
        System.out.println("long-double-round-trip=" +
                ((long) asDouble == longSource));
        System.out.println("long-equals-double=" +
                (longSource == asDouble));
        System.out.println("double-ulp-at-2pow53=" +
                Math.ulp(9_007_199_254_740_992d));

        double promotedFloat = 0.1f;
        System.out.println("float-to-double=" + promotedFloat);

        double roundedMax = (double) Long.MAX_VALUE;
        System.out.println("long-max-cast-back-equal=" +
                ((long) roundedMax == Long.MAX_VALUE));
        System.out.println("long-max-double-exact-integer=" +
                new BigDecimal(roundedMax).toBigIntegerExact());

        System.out.println("exact-small-long=" + toDoubleExact(10L));
        try {
            toDoubleExact(longSource);
        } catch (ArithmeticException ex) {
            System.out.println("checked-widening=precision-lost");
        }
    }
}
```

Lệnh thực thi:

```bash
javac WideningPrecisionDemo.java
java WideningPrecisionDemo
```

Kết quả stdout:

```text
int-original=16777217
float-as-int=16777216
int-float-round-trip=false
int-equals-float=true
int-to-double-exact=true
float-ulp-at-2pow24=2.0
long-original=9007199254740993
double-as-long=9007199254740992
long-double-round-trip=false
long-equals-double=true
double-ulp-at-2pow53=2.0
float-to-double=0.10000000149011612
long-max-cast-back-equal=true
long-max-double-exact-integer=9223372036854775808
exact-small-long=10.0
checked-widening=precision-lost
```

Điểm đáng chú ý: hai dòng `int-equals-float=true` và `long-equals-double=true` **không chứng minh phép chuyển đổi chính xác**. Giá trị số nguyên ở vế so sánh cũng được nâng sang kiểu thực và bị làm tròn. Dòng `long-max-cast-back-equal=true` cũng không chứng minh chính xác vì cast thu hẹp từ `double` về `long` có cơ chế chặn tại giới hạn.

## 10. Cách chọn kiểu khi cần bảo toàn số nguyên

| Nhu cầu | Lựa chọn phù hợp | Rủi ro nếu dùng float/double |
| --- | --- | --- |
| Đếm sự kiện, kích thước tệp, tổng số byte | `int`/`long`, hoặc `BigInteger` nếu cần | Mất các đơn vị lẻ ở miền lớn |
| ID số lớn, khóa tra cứu, số tài khoản | Thường `String` nếu là mã; `long`/`BigInteger` nếu cần số học | Hai ID khác nhau có thể trở thành một |
| Số tiền theo cent nguyên | `long` với kiểm soát tràn; hoặc giải pháp decimal theo miền | Không chấp nhận mất 1 cent |
| Số đo thực nghiệm chấp nhận sai số | `double`, đôi khi `float` theo đặc tả | Sai số là đặc tính được tính vào mô hình |
| Tiền hoặc giá trị thập phân chính xác | `BigDecimal` từ dữ liệu thập phân gốc | `double` có sai số nhị phân |
| Phải gửi `long` lớn sang JavaScript | String trong JSON hoặc giao thức hỗ trợ số nguyên chính xác | JavaScript Number (binary64) không phân biệt mọi số nguyên lớn |
| Một API bắt buộc nhận `double` từ `long` | Kiểm tra chính xác hoặc quy định sai số cho phép | Widening xảy ra âm thầm và không exception |

Tránh suy luận rằng một kiểu có **phạm vi biểu diễn lớn** thì luôn tốt hơn để lưu mọi dữ liệu nguyên. Ngữ nghĩa dữ liệu và yêu cầu bảo toàn thông tin phải quyết định thiết kế.

## 11. Những phép chuyển đổi và lời gọi thường gây nhầm

### 11.1. Truyền tham số vào method nhận double

```java
static void record(double idOrMeasurement) {
    // ...
}

long id = 9_007_199_254_740_993L;
record(id); // Java tự chuyển long sang double, có thể mất độ chính xác.
```

Không cần cast tường minh nên lỗi có thể xuất hiện khi refactor chữ ký method hoặc kết nối thư viện. Nếu `id` là định danh cần chính xác, chữ ký nhận `double` là một vấn đề thiết kế, không chỉ là lỗi format dữ liệu.

### 11.2. Toán hạng hỗn hợp trong biểu thức

```java
long count = 9_007_199_254_740_993L;
double average = count / 1.0; // count được nâng sang double trước phép chia.
```

Đầu ra là `double`; sai số chuyển kiểu có thể xuất hiện **trước phép chia**. Đừng cho rằng phép toán có kết quả dạng số thực vẫn giữ đủ từng đơn vị của bộ đếm rất lớn.

### 11.3. Tính nguyên trước rồi mới chuyển sang double

```java
long count = Long.MAX_VALUE;
double result = count + 1L;
```

Trong đoạn này, `count + 1L` thực hiện phép cộng `long` **trước khi chuyển sang `double`**, đã bị tràn thành `Long.MIN_VALUE`. Đó là **hai lớp rủi ro khác nhau**: tràn trong phép tính nguyên và mất chính xác ở bước chuyển sang số thực. Nếu mục đích là số thực lớn, cần chuyển kiểu đúng thời điểm theo yêu cầu tính toán; nếu mục đích là số nguyên chính xác, cân nhắc `BigInteger`.

### 11.4. Tăng double ở miền lớn

```java
double count = 9_007_199_254_740_992d;
count = count + 1.0;
// count vẫn bằng 9_007_199_254_740_992d.
```

Một biến kiểu `double` có thể ngừng thay đổi khi cộng một lượng nhỏ hơn độ phân giải hiện tại. Đây là nguyên nhân khiến `float`/`double` không phù hợp làm bộ đếm nguyên không giới hạn miền.

### 11.5. BigDecimal không tự phục hồi giá trị đã mất

```java
long id = 9_007_199_254_740_993L;
double rounded = id;
BigDecimal fromRounded = BigDecimal.valueOf(rounded);
```

`fromRounded` giữ giá trị tương ứng biểu diễn chuỗi của `double` đã làm tròn, không thể tự khôi phục số nguyên `id`. Nếu cần thập phân chính xác từ số nguyên, tạo **`BigDecimal.valueOf(id)` trước khi chuyển qua `double`**.

## 12. Chiến lược kiểm tra và thử nghiệm

Trong thực tế, không nhất thiết mọi chuyển `long → double` đều sai: nhiều giá trị cụ thể biểu diễn chính xác. Điều quan trọng là biết **hợp đồng của hệ thống**.

- Nếu yêu cầu **mọi đầu vào phải chính xác**, chọn kiểu giữ được toàn bộ miền, như `long` hoặc `BigInteger`, và tránh chuyển qua `float`/`double`.
- Nếu đầu vào bị giới hạn trong một miền an toàn, ghi rõ và kiểm tra giới hạn tại biên. Ví dụ `|n| ≤ 2^24` bảo đảm chính xác khi chuyển nguyên sang `float`; `|n| ≤ 2^53` bảo đảm chính xác khi chuyển nguyên sang `double`. Đối với `Long.MIN_VALUE`, tránh tính `Math.abs(n)` để kiểm tra miền vì `abs` có ca biên riêng.
- Nếu chỉ một số giá trị cụ thể được chấp nhận, có thể thực hiện chuyển kiểu rồi so với biểu diễn **toán học chính xác** như ví dụ `toDoubleExact`.
- Nếu cho phép xấp xỉ, định nghĩa **mức sai số chấp nhận được** và cách so sánh phù hợp; một ngưỡng tuyệt đối dùng cho số nhỏ không nhất thiết có nghĩa với số rất lớn.

Các ca thử nên bao gồm:

| Đầu vào | Chuyển đổi | Điều cần xác nhận |
| --- | --- | --- |
| `16_777_216` | `int → float` | Chính xác tại `2^24` |
| `16_777_217` | `int → float` | Làm tròn xuống `16_777_216` |
| `16_777_218` | `int → float` | Vẫn chính xác dù vượt `2^24` |
| `Integer.MAX_VALUE` | `int → double` | Chính xác |
| `9_007_199_254_740_992L` | `long → double` | Chính xác tại `2^53` |
| `9_007_199_254_740_993L` | `long → double` | Mất 1 đơn vị |
| `Long.MAX_VALUE` | `long → double → long` | Có thể trông đúng do cast bão hòa dù double đã khác |
| `0.1f` | `float → double` | Giữ đúng giá trị float đã xấp xỉ, không thành 0.1 chính xác |
| Hai ID kề nhau quanh `2^53` | So sánh sau khi đổi sang `double` | Phát hiện khả năng va chạm hai ID |

Một bộ test chỉ dùng số nhỏ dễ bỏ qua lỗi vì các chuyển đổi vẫn chính xác ở miền đó. Cần cố ý kiểm thử **ngay hai phía của mốc 2^24 và 2^53** cùng các giá trị giới hạn `int`/`long`.

## 13. Câu hỏi tự luyện

1. Vì sao `int → double` giữ chính xác mọi giá trị, nhưng `long → double` thì không? Giải thích theo số bit phần trị chứ không chỉ theo tổng số bit.
2. Dự đoán `(float) 16_777_217` và `(float) 16_777_218`. Vì sao một số phải làm tròn còn số kia thì không?
3. Với `long a = 9_007_199_254_740_992L` và `long b = a + 1`, vì sao `a != b` nhưng `(double) a == (double) b`?
4. Dự đoán `int i = 16_777_217; float f = i; i == f`. Vì sao `true` không chứng minh việc chuyển `int → float` giữ nguyên giá trị?
5. Giải thích ví dụ `Long.MAX_VALUE` chuyển sang `double` rồi cast ngược lại `long`: tại sao phép so sánh có thể `true` mà vẫn mất thông tin?
6. Viết một hàm nhận `long` và chỉ cho phép trả `double` nếu giá trị toán học không thay đổi; thử `10`, `2^53`, `2^53 + 1` và `Long.MAX_VALUE`.
7. Một DTO có trường ID kiểu `long`, nhưng JavaScript client nhận bằng `Number`. Chọn định dạng truyền tải phù hợp để giữ mọi giá trị ID, kèm ví dụ JSON.
8. Vì sao `double d = 0.1f;` biểu diễn đúng giá trị float đã lưu nhưng không phải 0.1 toán học? Việc đổi sang `BigDecimal` sau đó có thể phục hồi ý định số thập phân gốc không?
9. Một thư viện nhận `double` làm đầu vào cho thống kê, còn nguồn dữ liệu là số đếm `long`. Bạn sẽ chấp nhận sai số, chia nhỏ tính toán hay thay đổi API? Hãy nêu các giả định và test cần có.

## 14. Ghi nhớ

- **Nâng kiểu không bảo đảm giữ chính xác giá trị:** `int → float` và `long → float/double` có thể làm tròn âm thầm.
- **`float` có 24 bit độ chính xác, `double` có 53 bit**, nên mọi số nguyên đến `2^24` hoặc `2^53` về độ lớn tương ứng được giữ đúng, nhưng ngoài ngưỡng đó không phải mọi số nguyên đều biểu diễn được.
- **`int → double` giữ chính xác mọi `int`**, còn `float → double` giữ chính xác **giá trị float hiện có** và không phục hồi dữ liệu đã bị làm tròn.
- **So sánh hỗn hợp kiểu có thể đánh lừa:** `int == float` hoặc `long == double` có thể đúng ngay cả khi đã mất độ chính xác.
- **Cast ngược từ double về long không phải kiểm tra chính xác tổng quát**, đặc biệt tại `Long.MAX_VALUE` do quy tắc chặn khi thu hẹp kiểu.
- Với số đếm, mã định danh, số tiền nguyên và dữ liệu cần chính xác, **giữ kiểu nguyên hoặc kiểu thập phân chính xác thích hợp**; chỉ chuyển sang dấu phẩy động khi bài toán thật sự chấp nhận điều đó.

Nên tách ba câu hỏi khi chọn kiểu: *giá trị có nằm trong phạm vi biểu diễn không*, *giá trị có được biểu diễn chính xác không*, và *quy tắc chuyển/so sánh có bảo toàn điều kiện nghiệp vụ không*. Một phép widening hợp lệ chỉ trả lời câu hỏi thứ nhất.
