# Miền xác định, NaN, vô cực và độ chính xác được Javadoc quy định: `Math` và `StrictMath`

Khi gọi `Math.sqrt`, `Math.log`, `Math.pow`, `Math.hypot` hay `StrictMath.exp`, không đủ để biết công thức toán học. Một chương trình Java còn phải biết **đầu vào nào hợp lệ, điều gì xảy ra với các giá trị đặc biệt IEEE 754, giới hạn sai số của kết quả, và tính tái lập mà API thực sự cam kết**.

Một ví dụ ngắn:

```java
System.out.println(Math.sqrt(-1.0)); // NaN
System.out.println(Math.log(0.0));   // -Infinity
System.out.println(Math.pow(Double.NaN, 0.0)); // 1.0
```

Cả ba kết quả trên đều có ý nghĩa theo **hợp đồng của từng phương thức**, không thể suy luận bằng một quy tắc chung “đầu vào bất thường thì luôn ném exception” hoặc “có NaN ở đâu thì kết quả chắc chắn NaN”.

Bài học dùng **Java 17+**, tập trung vào cách **đọc và áp dụng Javadoc**. Khi triển khai với phiên bản Java khác, kiểm tra đúng tài liệu của phiên bản đang chạy. Nguồn chuẩn để tra cứu:

- [Javadoc Java 17 — java.lang.Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html)
- [Javadoc Java 17 — java.lang.StrictMath](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StrictMath.html)

## 1. “Miền xác định” trong toán học và trong `double`

Toán học thực cho hàm \(\sqrt{x}\) miền \(x\geq 0\), hàm \(\ln(x)\) miền \(x>0\), và \(\arcsin(x)\) miền \(-1\leq x\leq1\). Nhưng giá trị `double` có thêm:

- `Double.NaN`: kết quả không phải số theo ngữ nghĩa IEEE 754.
- `Double.POSITIVE_INFINITY` và `Double.NEGATIVE_INFINITY`: vô cực có dấu.
- `+0.0` và `-0.0`: zero có bit dấu khác nhau, dù `+0.0 == -0.0` là `true`.
- Giá trị **subnormal** rất gần 0; overflow hoặc underflow có thể làm kết quả thành vô cực hoặc zero.

**Miền thực thông thường** chỉ là bước đầu để đọc tài liệu. Javadoc còn mô tả **special cases**: khi nhận NaN, vô cực, zero có dấu, số ngoài miền, hoặc các kết hợp đặc biệt giữa hai/ba tham số, phương thức cụ thể phải trả gì.

Ví dụ, với `sqrt`:

```java
double a = Math.sqrt(4.0); // 2.0
double b = Math.sqrt(-1.0); // NaN
double c = Math.sqrt(-0.0); // -0.0
```

`sqrt(-0.0)` **không** được coi như căn bậc hai của một số âm không hợp lệ: Javadoc ghi rõ phải trả **zero với cùng dấu**. Ngược lại `sqrt(-1.0)` trả NaN.

Không đồng nhất “NaN” với “exception”. Trong tính toán dấu phẩy động, nhiều phương thức thông báo trạng thái qua chính **giá trị trả về**.

## 2. Vì sao không thể dùng một bảng quy tắc NaN chung cho mọi hàm?

Một số hàm lan truyền NaN theo cách thông thường, nhưng **special cases có thể ưu tiên hơn**:

| Biểu thức Java | Kết quả | Hợp đồng cần nhận biết |
| --- | --- | --- |
| `Math.sqrt(-1.0)` | `NaN` | Căn bậc hai của số âm thực không có kết quả thực |
| `Math.sqrt(-0.0)` | `-0.0` | Giữ dấu zero |
| `Math.log(+0.0)` | `-Infinity` | Zero là ranh giới của logarit |
| `Math.log(-0.0)` | `-Infinity` | Cả hai zero cho âm vô cực |
| `Math.log(-1.0)` | `NaN` | Đầu vào âm ngoài miền |
| `Math.exp(Double.NEGATIVE_INFINITY)` | `+0.0` | Giới hạn của \(e^x\) khi \(x\to-\infty\) |
| `Math.pow(Double.NaN, 0.0)` | `1.0` | Mũ bằng zero được quy định ưu tiên |
| `Math.pow(-2.0, 0.5)` | `NaN` | Cơ số âm với số mũ hữu hạn không nguyên |
| `Math.hypot(Double.POSITIVE_INFINITY, Double.NaN)` | `Infinity` | Đối số vô cực có ưu tiên theo Javadoc |
| `Math.fma(Double.POSITIVE_INFINITY, 0.0, 1.0)` | `NaN` | Tích vô cực nhân zero là trường hợp đặc biệt |
| `Math.min(-0.0, +0.0)` | `-0.0` | Âm zero nhỏ hơn dương zero theo contract của `min` |
| `Math.max(-0.0, +0.0)` | `+0.0` | Dương zero lớn hơn âm zero theo contract của `max` |

Điểm tinh tế: **`Math.pow(Double.NaN, 0.0)` trả 1.0**, dù đối số đầu là NaN. **`Math.hypot(Infinity, NaN)` trả vô cực**, dù có NaN. Việc khẳng định “bất kỳ tham số NaN nào cũng bắt buộc cho NaN” sẽ sai.

Cũng không nên tưởng `Math.min`/`Math.max` sử dụng y hệt toán tử `<`/`>` trong mọi trường hợp. Chúng có quy tắc tường minh cho signed zero và NaN.

## 3. Bảng miền xác định và các trường hợp biên tiêu biểu

| Phương thức | Miền số thực hữu hạn thông thường | Đầu vào ở biên/ngoài miền |
| --- | --- | --- |
| `sqrt(x)` | \(x\geq0\) | `x<0` → NaN; `-0.0` → -0.0; `+Infinity` → +Infinity |
| `cbrt(x)` | Mọi x thực | Số âm cho căn bậc ba âm; `-0.0` → -0.0; ±Infinity giữ dấu |
| `log(x)` | \(x>0\) | ±0.0 → -Infinity; x âm → NaN; +Infinity → +Infinity |
| `log10(x)` | \(x>0\) | ±0.0 → -Infinity; x âm → NaN |
| `log1p(x)` | \(x>-1\) | `-1.0` → -Infinity; x nhỏ hơn -1 → NaN; ±0.0 giữ dấu |
| `exp(x)` | Mọi x thực | -Infinity → +0.0; +Infinity → +Infinity; có thể overflow/underflow |
| `expm1(x)` | Mọi x thực | -Infinity → -1.0; ±0.0 giữ dấu; có thể overflow |
| `asin(x)`, `acos(x)` | \(-1\leq x\leq1\) | `abs(x)>1` → NaN |
| `sin(x)`, `cos(x)`, `tan(x)` | Mọi x thực | NaN hoặc ±Infinity → NaN; `sin`/`tan` giữ dấu zero |
| `pow(a,b)` | Phụ thuộc cả a và b | `a<0`, b hữu hạn không nguyên → NaN; các quy tắc zero, NaN, vô cực chi tiết |
| `hypot(x,y)` | Mọi x,y thực hữu hạn | Có Infinity → +Infinity kể cả tham số khác NaN |
| `fma(a,b,c)` | Phép \(a\times b+c\) dấu phẩy động | Infinity × zero → NaN; có NaN → NaN |
| `min(a,b)` / `max(a,b)` cho `double` | Mọi giá trị hữu hạn | Nếu một tham số NaN → NaN; phân biệt -0.0 và +0.0 |

Bảng là bản đồ để tra cứu, **không thay thế danh sách special cases đầy đủ của từng Javadoc**. Đặc biệt `pow` có nhiều trường hợp tổ hợp số mũ 0, ±Infinity, cơ số ±0.0 và số mũ nguyên chẵn/lẻ; khi tính một tình huống biên phải đọc đúng mục `pow`.

**Hàm không ném exception** trong một ví dụ không chứng minh toàn bộ API không thể ném exception trong mọi bối cảnh. Chẳng hạn thao tác primitive nguyên như `Math.addExact` ném `ArithmeticException` khi tràn, nhưng `Math.sqrt(-1.0)` lại trả NaN. Mỗi phương thức có hợp đồng riêng.

## 4. `NaN`, ±Infinity và các phép kiểm tra đúng

Dùng API phân loại giá trị dấu phẩy động:

```java
double x = Math.log(-1.0);

System.out.println(Double.isNaN(x));      // true
System.out.println(Double.isInfinite(x)); // false
System.out.println(Double.isFinite(x));   // false
```

`Double.isFinite(x)` chỉ trả `true` cho các giá trị hữu hạn, bao gồm `+0.0`, `-0.0` và cả số subnormal. `Float` có `Float.isNaN`, `Float.isInfinite` và `Float.isFinite` tương ứng.

**Không kiểm tra NaN bằng `x == Double.NaN`.** Bởi theo so sánh dấu phẩy động, NaN không bằng chính nó:

```java
double x = Double.NaN;
System.out.println(x == Double.NaN); // false
System.out.println(Double.isNaN(x));  // true
```

Khi chương trình yêu cầu **kết quả hữu hạn**, có thể xác thực sau phép tính:

```java
static double requireFinite(double result) {
    if (!Double.isFinite(result)) {
        throw new ArithmeticException("Result is not finite");
    }
    return result;
}
```

Đây là method minh họa đặt trong class. Exception trong helper **do người lập trình chủ động ném**; không phải `Math` tự ném exception tương tự khi gặp giá trị bất thường. Kiểm tra `isFinite` vẫn **không phát hiện mất chữ số do làm tròn**, cũng không ngăn kết quả underflow về zero.

## 5. `+0.0` và `-0.0`: bằng nhau nhưng không thể thay thế tùy ý

Các kiểu `float` và `double` có bit dấu riêng cho zero. Toán tử số học `==` coi hai zero bằng nhau:

```java
System.out.println(+0.0 == -0.0); // true
```

Nhưng Javadoc quy định nhiều hàm phải xét dấu:

- `Math.sqrt(-0.0)` → `-0.0`.
- `Math.cbrt(-0.0)` → `-0.0`.
- `Math.sin(-0.0)` và `Math.tan(-0.0)` → `-0.0`.
- `Math.expm1(-0.0)` và `Math.log1p(-0.0)` → `-0.0`.
- `Math.log(-0.0)` → `-Infinity`.
- `Math.exp(-0.0)` → `1.0`.
- `Math.min(+0.0,-0.0)` → `-0.0`; `Math.max(+0.0,-0.0)` → `+0.0`.

Để phân biệt bit:

```java
long a = Double.doubleToRawLongBits(+0.0); // 0x0000000000000000
long b = Double.doubleToRawLongBits(-0.0); // 0x8000000000000000
boolean sameBits = a == b; // false
```

`Double.compare(+0.0, -0.0)` cũng phân biệt signed zero, khác với `==`. Khi dữ liệu chạy qua thuật toán có phép chia hoặc giới hạn một phía, giữ/chuẩn hóa dấu zero có thể ảnh hưởng kết quả. Ứng dụng bình thường không cần phân biệt dấu zero vẫn nên **chuẩn hóa có chủ đích**, không vì thấy `==` là true mà nghĩ bit và các phép toán sau đều giống nhau.

## 6. ULP là gì? “Sai số trong 1 ulp” có nghĩa gì?

`ulp` là viết tắt của *unit in the last place*. Với một vùng giá trị của `double`, khoảng cách giữa các số thực biểu diễn được **thay đổi theo độ lớn của số**. Gần `1.0`, khoảng cách giữa `1.0` và số `double` lớn hơn gần nhất là:

```java
System.out.println(Math.ulp(1.0));       // 2.220446049250313E-16
System.out.println(Math.nextUp(1.0));    // 1.0000000000000002
```

Javadoc `Math` dùng ULP để định nghĩa **giới hạn sai số so với kết quả toán học chính xác**, chứ không phải số chữ số decimal cố định. Với cách nói “sai số tối đa 1 ulp”, giới hạn được đo trên **lưới số thực nhị phân ở độ lớn của kết quả**, không phải “sai số không quá 1 đơn vị số thực” hoặc “chính xác một chữ số cuối”.

Một cách hình dung:

```text
... 1.0000000000000000
... 1.0000000000000002   (số double tiếp theo)
... 1.0000000000000004
       ^ khoảng cách gần 1.0 khoảng 2.22 × 10^-16
```

Gần số rất lớn, ULP lớn hơn; gần zero, khoảng cách của số subnormal cực nhỏ. Độ chính xác tương đối và sai số tuyệt đối phải được phân tích trong miền dữ liệu thực tế.

### `Math.ulp` không đo sai số thực tế của một lời gọi

`Math.ulp(result)` trả quy mô một bước biểu diễn quanh `result`; nó **không tự biết giá trị toán học chính xác** để tính `abs(result - exact)`.

Do đó:

```java
double value = Math.exp(1.0);
double spacing = Math.ulp(value);
```

`spacing` là một kích thước ULP quanh số đã nhận, **không phải báo cáo** rằng `Math.exp(1.0)` thực sự sai đúng `spacing`.

Muốn đánh giá sai số của một hàm bằng kiểm thử chuẩn, cần kết quả tham chiếu có precision cao hơn hoặc phương pháp đối chiếu đáng tin; không thể suy ra error chỉ từ một lần gọi `Math.ulp`.

## 7. “Correctly rounded”, giới hạn 0,5/1/2 ulp và semi-monotonic

Javadoc phân biệt các cấp bảo đảm:

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Correctly rounded** | Chọn kết quả dấu phẩy động đúng theo quy tắc làm tròn được chỉ định từ kết quả toán học chính xác |
| **Trong 0,5 ulp** | Mức sai số rất chặt; phương thức đúng như vậy được xem là trả số biểu diễn gần kết quả thực nhất (với quy tắc tie phù hợp) |
| **Trong 1 ulp** | Sai lệch giới hạn theo khoảng cách lưới số; **không** nhất thiết luôn là kết quả làm tròn gần nhất trong mọi trường hợp |
| **Trong 2 ulp** | Giới hạn lỏng hơn 1 ulp, áp dụng cho một số hàm được Javadoc chỉ rõ |
| **Semi-monotonic** | Trên vùng hàm toán học tăng (hoặc giảm), xấp xỉ dấu phẩy động không được đảo hướng tăng (hoặc giảm), theo yêu cầu từng hàm |

`Math.sqrt` được Javadoc Java 17 mô tả là **correctly rounded positive square root**: đây là một cam kết cụ thể. Trong khi đó, các hàm như `Math.sin`, `Math.log` và `Math.exp` có quy định **within 1 ulp** và **semi-monotonic**, không có lời hứa mọi kết quả được làm tròn đúng đến bit gần nhất.

Cần nhớ:

1. **Đọc con số ULP trên đúng mục phương thức**, đừng áp dụng “1 ulp cho toàn bộ `Math`”.
2. **Semi-monotonic không có nghĩa hàm luôn tăng trên toàn bộ trục số.** `sin(x)` tự nhiên có đoạn tăng, đoạn giảm; ràng buộc nói về việc xấp xỉ giữ chiều trên các đoạn mà hàm toán học có tính đơn điệu.
3. **Trong 1 ulp không đồng nghĩa cùng bit trên mọi JVM.** Hai implementation có thể cho kết quả khác nhau nhưng đều nằm trong giới hạn Javadoc.
4. **Bảo đảm về độ chính xác không thay cho bảo đảm miền giá trị.** Một hàm có đặc tả ULP vẫn có special cases NaN/Infinity/signed zero.

### Ví dụ các mức theo từng phương thức

Theo Javadoc Java 17:

| `Math` method | Cam kết liên quan |
| --- | --- |
| `sqrt(double)` | Correctly rounded |
| `sin(double)`, `cos(double)`, `tan(double)` | Trong **1 ulp**, semi-monotonic |
| `exp(double)`, `log(double)`, `log10(double)` | Trong **1 ulp**, semi-monotonic |
| `expm1(double)`, `log1p(double)` | Trong **1 ulp**, semi-monotonic |
| `pow(double,double)` | Trong **1 ulp**, semi-monotonic |
| `hypot(double,double)` | Trong **1 ulp**; semi-monotonic theo một biến khi biến kia cố định |
| `atan2(double,double)` | Trong **2 ulp**, semi-monotonic |
| `sinh(double)`, `cosh(double)`, `tanh(double)` | Trong **2,5 ulp** theo Javadoc |
| `fma(double,double,double)` | Tính tích rồi cộng như có precision/range vô hạn, **làm tròn một lần theo nearest-even** |

Không suy luận sai rằng hàm có “2,5 ulp” chắc chắn luôn sai nhiều hơn một hàm “1 ulp”. Đó là **giới hạn tối đa được API cho phép**, không phải độ lớn sai số thực tế trong mọi lần gọi.

### Tại sao `fma` khác `a * b + c`?

```java
double combined = Math.fma(a, b, c);
double separate = a * b + c;
```

`Math.fma` làm tròn **một lần** sau khi tính chính xác toán học \(a\times b+c\), trong khi biểu thức thông thường có bước làm tròn tích rồi làm tròn tổng. Hai kết quả có thể khác vài bit ở trường hợp nhạy cảm. Điều này là **contract**, không phải do CPU nào “tình cờ tính tốt hơn”.

`Math.fma(Double.POSITIVE_INFINITY, 0.0, 1.0)` trả NaN theo special case cho vô cực nhân zero, không ném exception.

## 8. `Math` khác `StrictMath` ở đâu?

**Cả hai đều** cung cấp nhiều phương thức toán học dấu phẩy động và các giá trị đặc biệt theo hợp đồng Java. Nhưng tính **tái lập kết quả bit-for-bit** không giống nhau:

- `Math` cho phép implementation khác nhau của **một số hàm** trên nền tảng/JVM khác nhau, miễn **đáp ứng accuracy và các ràng buộc Javadoc**. Điều này mở đường cho intrinsic, hướng dẫn CPU hoặc thư viện native nhanh hơn.
- `StrictMath` yêu cầu một số hàm toán học có hành vi tương thích các thuật toán được công bố trong **fdlibm 5.3**; mục tiêu chính là **tính tái lập** giữa các nền tảng, không phải lời hứa “luôn chính xác hơn `Math`”.
- Từ Java 17 (JEP 306), biểu thức dấu phẩy động Java đã trở lại ngữ nghĩa *always-strict*. Điều đó **không xóa khác biệt giữa hợp đồng `Math` và `StrictMath`**.

Javadoc Java 17 `StrictMath` nêu cụ thể các hàm phải theo fdlibm, bao gồm `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `exp`, `log`, `log10`, `cbrt`, `atan2`, `pow`, `sinh`, `cosh`, `tanh`, `hypot`, `expm1` và `log1p`.

**Không khái quát rằng mọi method trong `StrictMath` đều chạy fdlibm**; các phương thức khác có đặc tả riêng. Tên `StrictMath` cũng **không bảo đảm mọi phép gọi chạy chậm hơn hoặc chính xác hơn `Math`**.

Ví dụ một yêu cầu thực tiễn:

```java
double fastOrPlatform = Math.exp(1.0);
double specReproducible = StrictMath.exp(1.0);
```

Hai giá trị có thể giống nhau trong môi trường hiện tại, nhưng **không được dùng một test `Math.exp(x) == StrictMath.exp(x)` cho mọi x và mọi JVM như một đảm bảo**. Nếu quy trình cần tái lập bit trong hàm thuộc nhóm fdlibm, cân nhắc `StrictMath`, đồng thời cố định phiên bản Java, dữ liệu đầu vào và môi trường khi cần.

## 9. Phương thức số nguyên: độ chính xác và overflow có hợp đồng khác

Chủ đề `Math`/`StrictMath` không chỉ có `double`. Một số API số nguyên như `Math.addExact`, `Math.multiplyExact` và `Math.toIntExact` **ném `ArithmeticException` khi tràn**.

Ngược lại, phép `Math.abs(int)` có trường hợp đặc biệt:

```java
int minimum = Integer.MIN_VALUE;
System.out.println(Math.abs(minimum)); // -2147483648
```

Bởi miền `int` là `[-2^31, 2^31-1]`, giá trị tuyệt đối toán học của `Integer.MIN_VALUE` không biểu diễn được dưới dạng `int`. `Math.abs(minimum)` theo hợp đồng cũ trả lại chính số âm đó. **Đừng diễn giải tên `abs` là bảo đảm kết quả không âm với mọi `int`**.

Nếu cần phát hiện điều này:

```java
try {
    int exact = Math.absExact(Integer.MIN_VALUE);
} catch (ArithmeticException ex) {
    System.out.println("abs overflow detected");
}
```

`Math.absExact` (có trong Java 17) ném exception khi giá trị tuyệt đối không thể chứa vừa kiểu nguyên. Đây là **cơ chế lỗi khác** so với các giá trị NaN/Infinity của nhiều hàm `double`.

Tóm lại, phải xem **kiểu tham số, overload và hợp đồng cụ thể** trước khi suy luận miền và cách báo lỗi.

## 10. Xây dựng xác thực đầu vào/đầu ra theo hợp đồng ứng dụng

Javadoc cho biết **Java sẽ trả gì**, không tự quyết định giá trị đó có được ứng dụng cho phép hay không.

Ví dụ ứng dụng yêu cầu căn bậc hai của số hữu hạn không âm, kết quả cũng phải hữu hạn:

```java
static double checkedSqrt(double x) {
    if (!Double.isFinite(x) || x < 0.0) {
        throw new IllegalArgumentException("Expected finite nonnegative x");
    }
    double answer = Math.sqrt(x);
    if (!Double.isFinite(answer)) {
        throw new ArithmeticException("Non-finite square root");
    }
    return answer;
}
```

Đây là method minh họa đặt trong class. Vì `-0.0 < 0.0` là false, helper **chấp nhận -0.0**, và `Math.sqrt(-0.0)` sẽ trả **-0.0**. Nếu contract cần loại trừ hoặc chuẩn hóa âm zero, phải thêm quy tắc cụ thể; điều kiện `x < 0.0` chưa đủ.

Với logarit tự nhiên:

```java
static double checkedLog(double x) {
    if (!Double.isFinite(x) || x <= 0.0) {
        throw new IllegalArgumentException("Expected finite positive x");
    }
    double answer = Math.log(x);
    if (!Double.isFinite(answer)) {
        throw new ArithmeticException("Non-finite logarithm");
    }
    return answer;
}
```

Ở đây `x <= 0.0` sẽ **từ chối cả +0.0 và -0.0**. Cặp kiểm tra `Double.isFinite` và miền dương giúp loại NaN/Infinity một cách rõ ràng, thay vì chờ chúng lan truyền qua công thức.

### Khi cần chấp nhận giá trị IEEE 754

Các hệ thống nghiên cứu hoặc mô phỏng có thể chủ ý giữ `NaN`/Infinity như trạng thái tính toán. Khi đó không nên dùng helper cấm mọi giá trị không hữu hạn; thay vào đó cần một cách xử lý có tài liệu:

```java
double result = Math.log(input);
if (Double.isNaN(result)) {
    // Đường xử lý NaN đã được thiết kế
} else if (Double.isInfinite(result)) {
    // Đường xử lý vô cực
} else {
    // Kết quả hữu hạn
}
```

Đây là đoạn minh họa bên trong method có biến `input`. Không âm thầm chuyển NaN thành zero để “làm chương trình chạy tiếp”: zero cũng là một giá trị toán học hợp lệ, nên cách đó che mất lỗi dữ liệu.

## 11. Chương trình Java 17+ độc lập và đầu ra đáng kiểm chứng

Lưu thành **`MathJavadocContractDemo.java`**:

```java
import java.util.Locale;

public class MathJavadocContractDemo {
    static double checkedLog(double x) {
        if (!Double.isFinite(x) || x <= 0.0) {
            throw new IllegalArgumentException("Expected finite positive x");
        }
        return Math.log(x);
    }

    public static void main(String[] args) {
        System.out.println("sqrtNegative=" + Math.sqrt(-1.0));
        System.out.println("sqrtNegativeZero=" + Math.sqrt(-0.0));
        System.out.println("cbrtNegativeZero=" + Math.cbrt(-0.0));
        System.out.println("logZero=" + Math.log(0.0));
        System.out.println("logNegativeZero=" + Math.log(-0.0));
        System.out.println("logNegative=" + Math.log(-1.0));
        System.out.println("log1pMinusOne=" + Math.log1p(-1.0));
        System.out.println("expm1MinusZero=" + Math.expm1(-0.0));

        System.out.println("powNanZero=" + Math.pow(Double.NaN, 0.0));
        System.out.println("powNegativeFraction=" + Math.pow(-2.0, 0.5));
        System.out.println("hypotInfAndNan=" +
                Math.hypot(Double.POSITIVE_INFINITY, Double.NaN));
        System.out.println("fmaInfinityTimesZero=" +
                Math.fma(Double.POSITIVE_INFINITY, 0.0, 1.0));

        System.out.println("minSignedZero=" + Math.min(+0.0, -0.0));
        System.out.println("maxSignedZero=" + Math.max(+0.0, -0.0));
        System.out.println("zeroNumericEqual=" + (+0.0 == -0.0));
        System.out.println("zeroSameBits=" +
                (Double.doubleToRawLongBits(+0.0) ==
                 Double.doubleToRawLongBits(-0.0)));

        System.out.println("ulpOne=" + Math.ulp(1.0));
        System.out.println("nextUpOne=" + Math.nextUp(1.0));

        double outOfDomain = Math.log(-1.0);
        System.out.println("nanDetected=" + Double.isNaN(outOfDomain));
        System.out.println("nanFinite=" + Double.isFinite(outOfDomain));
        System.out.println("nanEqualsSelf=" +
                (Double.NaN == Double.NaN));

        System.out.println("expOverflow=" + Math.exp(800.0));
        System.out.println("expUnderflow=" + Math.exp(-800.0));
        System.out.println("overflowIsInfinite=" +
                Double.isInfinite(Math.exp(800.0)));

        System.out.println("mathExpSixDigits=" +
                String.format(Locale.ROOT, "%.6f", Math.exp(1.0)));
        System.out.println("strictExpSixDigits=" +
                String.format(Locale.ROOT, "%.6f", StrictMath.exp(1.0)));

        System.out.println("absMinimum=" + Math.abs(Integer.MIN_VALUE));
        try {
            Math.absExact(Integer.MIN_VALUE);
            System.out.println("absExact=notDetected");
        } catch (ArithmeticException ex) {
            System.out.println("absExact=detected");
        }

        try {
            checkedLog(0.0);
            System.out.println("checkedLogZero=notDetected");
        } catch (IllegalArgumentException ex) {
            System.out.println("checkedLogZero=detected");
        }
        System.out.println("checkedLogOne=" + checkedLog(1.0));
    }
}
```

Biên dịch và chạy:

```bash
javac MathJavadocContractDemo.java
java MathJavadocContractDemo
```

**Đầu ra với các giá trị được chọn**:

```text
sqrtNegative=NaN
sqrtNegativeZero=-0.0
cbrtNegativeZero=-0.0
logZero=-Infinity
logNegativeZero=-Infinity
logNegative=NaN
log1pMinusOne=-Infinity
expm1MinusZero=-0.0
powNanZero=1.0
powNegativeFraction=NaN
hypotInfAndNan=Infinity
fmaInfinityTimesZero=NaN
minSignedZero=-0.0
maxSignedZero=0.0
zeroNumericEqual=true
zeroSameBits=false
ulpOne=2.220446049250313E-16
nextUpOne=1.0000000000000002
nanDetected=true
nanFinite=false
nanEqualsSelf=false
expOverflow=Infinity
expUnderflow=0.0
overflowIsInfinite=true
mathExpSixDigits=2.718282
strictExpSixDigits=2.718282
absMinimum=-2147483648
absExact=detected
checkedLogZero=detected
checkedLogOne=0.0
```

Các test tập trung vào **special cases mà Javadoc xác định rõ**. Hai dòng định dạng `Math.exp(1)` và `StrictMath.exp(1)` chỉ kiểm tra dạng hiển thị sáu chữ số decimal, **không tuyên bố mọi bit hai giá trị đều phải khớp**. Dùng số nhỏ, zero và giá trị đặc biệt giúp xây dựng test ổn định hơn so với kiểm tra chính xác toàn bộ chữ số của một phép tính siêu việt trên mọi JVM.

## 12. Thiết kế test đúng theo Javadoc thay vì hard-code kết quả máy hiện tại

Một bộ kiểm thử nên tách ba loại:

**(A) Special cases với kết quả xác định:** kiểm tra `Double.isNaN(Math.sqrt(-1.0))`, `Math.pow(Double.NaN, 0.0) == 1.0`, hoặc bit âm zero sau `Math.sqrt(-0.0)`. Với NaN, không dùng `== Double.NaN`.

**(B) Miền đầu vào và giá trị đầu ra:** kiểm tra ứng dụng có từ chối log của số không dương, hoặc phát hiện overflow thành vô cực không. Các quy tắc này thuộc **business contract**, bổ sung cho Javadoc.

**(C) Sai số của kết quả hữu hạn:** nếu phương thức chỉ hứa “within 1 ulp” thay vì cùng bit, đừng lưu một chuỗi thập phân quá dài từ máy hiện tại làm expected duy nhất cho mọi hệ thống. So sánh với tham chiếu chính xác đủ cao và dùng mức sai số phù hợp đặc tả, đồng thời xét subnormal, vô cực, NaN, signed zero. Một công thức kiểu `abs(actual - expected) <= Math.ulp(actual)` chỉ là **minh họa thô**, chưa chắc đo đúng ulp của kết quả thực, không xử lý các giá trị đặc biệt và **không thay thế quy trình kiểm chứng chuẩn**.

Ví dụ một test về đặc điểm hướng tăng ở miền log dương có thể kiểm tra nhiều điểm mẫu. Nhưng vài điểm mẫu **không chứng minh hoàn toàn** semi-monotonic cho mọi `double`. Muốn kiểm thử sâu phải biết chính xác hợp đồng Javadoc, bộ tham chiếu, dải đầu vào và công cụ đánh giá số học.

Nếu hệ thống đòi kết quả bit-for-bit để tái lập, cân nhắc dùng `StrictMath` với các hàm có ràng buộc fdlibm và viết rõ chính sách phiên bản/đầu vào, thay vì vô tình dựa vào một implementation cụ thể của `Math`.

## 13. Hiểu lầm phổ biến và checklist

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| “Hàm `Math` nhận số ngoài miền sẽ ném `ArithmeticException`.” | Nhiều hàm số thực trả `NaN` hoặc Infinity, theo từng special case. |
| “Bất kỳ đầu vào NaN nào cũng bắt buộc cho NaN.” | Sai với trường hợp như `Math.pow(NaN,0.0)`, và `hypot(Infinity,NaN)`. |
| “`sqrt(-0.0)` phải cho NaN vì số âm.” | Sai: -0.0 được giữ dấu theo hợp đồng căn bậc hai. |
| “`Math.min(+0.0,-0.0)` có thể tùy ý chọn một zero.” | Javadoc quy định chọn -0.0; `max` chọn +0.0. |
| “1 ulp là sai số không quá 1.0.” | Sai: ulp là bước của lưới số thực nhị phân tại độ lớn kết quả. |
| “Trong 1 ulp nghĩa là kết quả đã correctly rounded.” | Không nhất thiết; có thể chọn một giá trị kề thay vì gần nhất. |
| “`Math.sqrt`, `Math.exp` và `Math.atan2` cùng một cam kết sai số.” | Không: phải đọc từng mục Javadoc. |
| “Semi-monotonic nghĩa là hàm `sin` tăng mãi.” | Sai: đó là ràng buộc bảo toàn hướng trên vùng mà hàm toán học đơn điệu. |
| “`StrictMath` luôn nhiều chữ số chính xác hơn `Math`.” | Không có bảo đảm như vậy; trọng tâm là tái lập theo thuật toán được chỉ định. |
| “Java 17 always-strict khiến `Math` và `StrictMath` giống nhau.” | Sai: ngữ nghĩa biểu thức không xóa sự khác nhau ở đặc tả các method thư viện. |
| “`Math.abs(int)` luôn không âm.” | Sai với `Integer.MIN_VALUE`; có thể dùng `absExact` để phát hiện tràn. |
| “`Double.isFinite` đủ chứng minh kết quả không sai số.” | Sai: nó chỉ loại NaN/Infinity, không kiểm tra làm tròn hay underflow. |

Checklist thực hành:

1. **Mở đúng Javadoc của phiên bản Java đang dùng**, tìm đúng overload theo kiểu tham số.
2. **Đọc công thức và miền thực** nhưng không dừng ở đó.
3. **Đọc trọn mục “Special Cases”**: NaN, Infinity, signed zero, tham số ở biên, thứ tự ưu tiên giữa các trường hợp.
4. **Đọc dòng cam kết sai số** của từng method: correctly rounded, 1 ulp, 2 ulp, 2,5 ulp và semi-monotonic nếu có.
5. **Phân biệt `Math` và `StrictMath` theo yêu cầu tái lập**, không theo suy đoán tên class.
6. **Xác định business contract** có cho phép kết quả NaN/vô cực, zero có dấu và underflow không.
7. **Kiểm thử trường hợp biên riêng khỏi kiểm thử độ chính xác**; không dùng một so sánh `==` duy nhất cho mọi số thực.
8. **Khi cần độ chính xác hoặc tái lập nghiêm ngặt**, dùng dữ liệu tham chiếu và tiêu chí sai số phù hợp, không lấy kết quả máy hiện tại làm chân lý cho mọi nền tảng.

**Kết luận:** Hợp đồng `Math`/`StrictMath` không chỉ là công thức. Nó bao gồm **miền xác định, special cases, độ chính xác đo theo ULP, tính đơn điệu xấp xỉ và mức tái lập**. Lập trình Java đúng đòi hỏi đọc **Javadoc của từng phương thức**, xác thực giá trị theo mục đích ứng dụng và kiểm thử đúng điều API thực sự cam kết.