# Math.pow, Math.sqrt, Math.cbrt và cách chọn phép tính phù hợp trong Java

Trong Java Core, ba phương thức **`Math.pow`**, **`Math.sqrt`** và **`Math.cbrt`** có vẻ gần nhau vì đều liên quan đến lũy thừa hoặc khai căn. Tuy nhiên, chúng **không hoàn toàn thay thế cho nhau**. Sự khác nhau nằm ở **ngữ nghĩa toán học**, **miền giá trị hợp lệ**, **hành vi với số âm và zero có dấu**, **giới hạn `double`**, **độ chính xác** và khả năng chọn một thuật toán chuyên dụng tốt hơn.

Ví dụ:

```java
double square = Math.pow(3.0, 2.0); // 9.0
double root2 = Math.sqrt(9.0);      // 3.0
double root3 = Math.cbrt(-8.0);     // -2.0

double surprise = Math.pow(-8.0, 1.0 / 3.0);
// surprise là NaN, không phải -2.0.
```

Đoạn mã trên là **mảnh ví dụ** có thể đặt trong một phương thức. Với căn bậc ba âm, `Math.cbrt` biết rõ đó là **căn thực bậc ba**; `Math.pow` chỉ nhìn thấy cơ số âm và một số mũ `double` không nguyên.

Bài học thuộc nhóm **Math và StrictMath**: hiểu cách API được thiết kế và chọn đúng công cụ trước khi tối ưu hiệu năng hoặc sửa những sai số dấu phẩy động.

## 1. Tổng quan API và giá trị trả về

| Phép tính | Phương thức | Kiểu nhận/trả | Ý nghĩa |
| --- | --- | --- | --- |
| Lũy thừa bất kỳ | `Math.pow(double a, double b)` | Hai `double` → `double` | Tính `a^b` theo quy tắc dấu phẩy động |
| Căn bậc hai | `Math.sqrt(double a)` | `double` → `double` | Căn bậc hai thực không âm của `a` |
| Căn bậc ba | `Math.cbrt(double a)` | `double` → `double` | Căn bậc ba thực, kể cả `a` âm |
| Khoảng cách hai chiều | `Math.hypot(double x, double y)` | Hai `double` → `double` | Tính `sqrt(x*x+y*y)` theo cách tránh overflow/underflow trung gian |
| Các hàm tương ứng | `StrictMath.pow/sqrt/cbrt` | Cũng là `double` | Có hợp đồng về khả năng tái lập kết quả theo quy định `StrictMath` |

Tất cả đều là **phương thức static** của lớp `java.lang.Math` hoặc `java.lang.StrictMath`; không cần import riêng nếu gọi bằng tên lớp. Với ba hàm đầu, **không có overload trả `int` hoặc `long`** cho kết quả lũy thừa hoặc căn. Ví dụ:

```java
double answer = Math.sqrt(25);   // 5.0, dù đối số viết bằng literal int.
double power = Math.pow(2, 10);  // 1024.0, không phải kiểu long.
```

Hai lời gọi này nhận literal `int` và tự **widen** thành `double` trước khi gọi hàm. Đừng dựa vào cách viết `Math.pow(2, 10)` để suy ra kết quả là số nguyên chính xác tùy ý: kiểu trả về luôn là `double`.

## 2. `Math.pow(base, exponent)`: phép lũy thừa tổng quát

`Math.pow(a,b)` biểu diễn phép `a` mũ `b`, trong đó cả cơ số và số mũ là `double`. Với các trường hợp thông dụng:

```java
double a = Math.pow(2.0, 10.0);  // 1024.0
double b = Math.pow(10.0, -2.0); // 0.01 (xấp xỉ nhị phân)
double c = Math.pow(9.0, 0.5);   // 3.0 với ví dụ này
double d = Math.pow(-2.0, 3.0);  // -8.0
double e = Math.pow(-2.0, 4.0);  // 16.0
```

Các dòng ở trên là mảnh mã dùng trong phương thức. Điểm đáng chú ý là số mũ được **truyền và xử lý như `double`**, chứ không phải “số nguyên tổng quát”: `Math.pow` không hứa rằng mọi phép lũy thừa số nguyên sẽ tạo ra một số nguyên **chính xác**.

Với số mũ nguyên và cơ số nguyên nhỏ, kết quả có thể được biểu diễn chính xác; với số rất lớn, số mũ không nguyên hoặc kết quả gần biên của `double`, phép tính sẽ chịu quy tắc làm tròn và giới hạn của dấu phẩy động.

**Không dùng dấu `^` làm toán tử lũy thừa trong Java.** `2 ^ 3` là phép **XOR theo bit** trên hai số nguyên và cho kết quả 1, không phải 8. Muốn mũ 3, dùng `Math.pow(2,3)`, nhân liên tiếp khi phù hợp hoặc một hàm lũy thừa số nguyên được thiết kế riêng.

## 3. `Math.sqrt(x)`: căn bậc hai và miền xác định

`Math.sqrt(x)` tìm **căn bậc hai không âm** của `x` khi `x` hữu hạn và không âm.

```java
double a = Math.sqrt(9.0);    // 3.0
double b = Math.sqrt(2.0);    // Số double gần căn 2.
double c = Math.sqrt(0.0);    // +0.0
double d = Math.sqrt(-4.0);   // NaN.
```

Với số âm khác zero, **không tồn tại căn bậc hai thực**, do đó `Math.sqrt(-4.0)` trả **`Double.NaN`**. Java không tự chuyển sang miền **số phức** và cũng không tự ném `ArithmeticException`. Nếu ứng dụng cần căn bậc hai phức, phải dùng thư viện số phức và kiểu dữ liệu có thể chứa phần thực/ảo.

`Math.sqrt` có hợp đồng **correctly rounded**: kết quả là số `double` gần nhất với căn toán học chính xác theo quy tắc làm tròn được quy định. Đây là một điểm mạnh của hàm chuyên dụng; không nên giả định `Math.pow(x,0.5)` luôn có toàn bộ cùng hợp đồng độ chính xác và mọi trường hợp biên.

Chú ý zero có dấu:

```java
double negZero = -0.0;
double root = Math.sqrt(negZero);    // -0.0
boolean sameBits = Double.doubleToRawLongBits(root)
        == Double.doubleToRawLongBits(negZero); // true
```

Theo IEEE 754, `-0.0` và `+0.0` có mẫu bit khác nhau mặc dù `-0.0 == +0.0` là `true`. `Math.sqrt(-0.0)` **giữ nguyên âm zero**, không trả NaN như khi đầu vào là `-4.0`.

## 4. `Math.cbrt(x)`: căn bậc ba thực, kể cả số âm

`Math.cbrt(x)` tính **căn bậc ba thực** của `x`. Khác căn bậc hai, một số âm hữu hạn vẫn có căn bậc ba thực:

```java
double a = Math.cbrt(27.0);  // 3.0
double b = Math.cbrt(-8.0);  // -2.0
double c = Math.cbrt(0.0);   // +0.0
double d = Math.cbrt(-0.0);  // -0.0
```

Ví dụ `(-2)^3 = -8`, nên căn bậc ba thực của `-8` là `-2`. `Math.cbrt` cũng **giữ dấu của zero** và có hành vi với Infinity/NaN theo quy tắc API. Nó có hợp đồng độ chính xác **trong vòng 1 ULP** với yêu cầu liên quan về tính đơn điệu gần đúng, khác với phát biểu `Math.sqrt` được làm tròn đúng.

Chính vì có miền âm, hàm chuyên biệt `cbrt` thường là lựa chọn đúng hơn `pow(x, 1.0/3.0)` để tìm căn bậc ba thực, kể cả khi `x` dương: nó thể hiện chính xác **ý định toán học** và được thiết kế cho phép toán ấy.

## 5. Vì sao `Math.pow(-8.0, 1.0 / 3.0)` là NaN?

Trong toán học thực, căn bậc ba của -8 là -2. Nhưng ở Java:

```java
double exponent = 1.0 / 3.0;
double viaPow = Math.pow(-8.0, exponent); // NaN.
double viaCbrt = Math.cbrt(-8.0);        // -2.0.
```

Nguyên nhân gồm hai ý:

1. `1.0 / 3.0` là một số `double` **xấp xỉ 1/3**, không phải phân số chính xác với tử số/mẫu số tách biệt.
2. Với **cơ số âm hữu hạn** và **số mũ hữu hạn không nguyên**, `Math.pow` theo định nghĩa `double` của Java trả **NaN**. Nó không suy luận rằng một số mũ gần `1/3` có nghĩa “lấy căn bậc ba thực rồi giữ dấu”.

Nếu chỉ thay cách viết thành `Math.pow(-8.0, 0.3333333333333333)`, kết quả vẫn là NaN vì số mũ đó không phải số nguyên. Đây là sai **lựa chọn API**, không phải sai số nhỏ do in thập phân.

Không nên tự sửa bằng `Math.abs(x)` rồi luôn gắn lại dấu âm cho **mọi** số mũ thực: quy tắc đúng còn phụ thuộc bản chất toán học của số mũ (ví dụ phân số có tử/mẫu chẵn/lẻ), miền giá trị và khả năng biểu diễn. Nếu muốn căn bậc ba thực thì `Math.cbrt` chính là API phù hợp.

## 6. Tính bình phương, lập phương và lựa chọn `pow` hay nhân trực tiếp

Với các mũ cố định nhỏ, phép nhân tường minh dễ đọc và có thể tránh chi phí gọi một phép lũy thừa tổng quát:

```java
double x = 2.5;
double square = x * x;
double cube = x * x * x;
double generic = Math.pow(x, 7.0);
```

Tuy nhiên, **đừng mặc định phép nhân trực tiếp và `Math.pow(x,2.0)` cho mẫu bit giống nhau ở mọi input**. Chúng có thể có các quy tắc đặc biệt hoặc sai khác làm tròn/thuật toán; trong các bài toán yêu cầu kết quả bit-for-bit hay một tiêu chuẩn số học cụ thể, hãy kiểm thử trên miền dữ liệu thực tế.

Về hiệu năng, không nên suy luận “`x*x` luôn nhanh hơn” hay “`Math.pow` luôn được CPU tối ưu” mà không đo. JVM có thể tối ưu mã khác nhau theo môi trường; khi hiệu năng quan trọng, benchmark với JMH và dữ liệu đại diện.

**Quan trọng hơn:** với **số nguyên**, dùng `int * int` vẫn có thể tràn. Chuyển qua `Math.pow` không phải giải pháp chính xác; kết quả `double` chỉ hữu hạn độ chính xác.

## 7. Chọn `pow` cho mũ số nguyên có thể làm mất độ chính xác

`double` có 53 bit significand hiệu dụng, nên **không biểu diễn chính xác mọi số nguyên lớn hơn `2^53`**. Ví dụ:

```java
double n = Math.pow(2.0, 53.0);     // 9007199254740992.0
boolean lost = (n + 1.0 == n);     // true.
```

Số toán học `2^53 + 1` không có biểu diễn `double` chính xác. Khi `n + 1.0`, kết quả làm tròn về chính `n`. Do đó **không nên** dùng `(long) Math.pow(base, exponent)` như giải pháp luôn chính xác cho lũy thừa số nguyên:

- Nếu phép lũy thừa tạo ra số nguyên không lưu chính xác trong `double`, ép về `long` **không thể khôi phục bit đã mất**.
- Nếu kết quả `double` vượt miền `long`, phép chuyển từ số thực sang số nguyên theo quy tắc Java không giống phép tính nguyên chính xác; với Infinity và giá trị rất lớn, kết quả chuyển kiểu có thể bị bão hòa.
- Nếu số mũ âm, giá trị lũy thừa thường không phải số nguyên, nên ép kiểu dễ **cắt phần thập phân**.
- Nếu cơ số âm với số mũ thực không nguyên, phép `pow` có thể trả NaN.

Dùng `Math.pow` khi dữ liệu và đầu ra có ngữ nghĩa **dấu phẩy động**. Khi cần số nguyên tuyệt đối chính xác, hãy chọn phép toán nguyên với kiểm tra tràn hoặc `BigInteger.pow`.

## 8. Lũy thừa số nguyên chính xác: `Math.multiplyExact` và `BigInteger.pow`

Một phương pháp cho `long` là dùng **exponentiation by squaring** (bình phương liên tiếp), kiểm tra tràn ở mỗi phép nhân:

```java
static long powExact(long base, int exponent) {
    if (exponent < 0) {
        throw new IllegalArgumentException("negative exponent");
    }
    long result = 1L;
    long factor = base;
    int remaining = exponent;
    while (remaining > 0) {
        if ((remaining & 1) != 0) {
            result = Math.multiplyExact(result, factor);
        }
        remaining >>>= 1;
        if (remaining > 0) {
            factor = Math.multiplyExact(factor, factor);
        }
    }
    return result;
}
```

Đây là **phương thức nằm trong lớp Java**, cũng xuất hiện trong chương trình hoàn chỉnh bên dưới. Thuật toán chạy trong `O(log exponent)` phép bình phương/nhân, không phải nhân một cách tuyến tính theo số mũ. `Math.multiplyExact` ném `ArithmeticException` khi tích nằm ngoài miền `long`.

```java
long valid = powExact(3L, 10); // 59049.
// powExact(2L, 63) ném ArithmeticException vì 2^63 > Long.MAX_VALUE.
```

Lưu ý phương thức chủ động **không hỗ trợ số mũ âm** vì kết quả có thể là phân số. Việc thêm `if (remaining > 0)` trước phép bình phương tiếp theo tránh một phép nhân không còn cần thiết khi thuật toán đã xử lý bit cao nhất; điều này quan trọng với API kiểm tra tràn vì phép trung gian vô ích cũng có thể gây exception.

Nếu đầu ra cần vượt quá `long`, dùng:

```java
java.math.BigInteger a = java.math.BigInteger.valueOf(2);
java.math.BigInteger result = a.pow(100); // Số nguyên 2^100 chính xác.
```

`BigInteger.pow(int exponent)` hỗ trợ số mũ **không âm**, trả giá trị nguyên chính xác trong giới hạn tài nguyên; nó không dùng `double` trung gian. Số mũ âm không phải kết quả `BigInteger` nói chung.

## 9. `sqrt` cho việc kiểm tra số chính phương

Với một `int` hoặc `long`, gọi `Math.sqrt(n)` trả `double`. Nếu mục đích là **hiển thị căn bậc hai xấp xỉ**, cách này rất hợp lý.

Nếu mục đích là kiểm tra **`n` có phải số chính phương chính xác không**, cần cẩn thận:

```java
long n = 81L;
long root = (long) Math.sqrt(n); // 9 với ví dụ này.
boolean square = (root * root == n); // true với n=81.
```

Với `long` rất lớn, vấn đề phức tạp hơn. Một `long` dương có thể không biểu diễn chính xác bằng `double`, phép ép căn sang `long` có thể cần hiệu chỉnh, và `root*root` có thể **tràn** nếu chưa kiểm tra giới hạn. Nếu thực sự cần kiểm tra chính phương cho dữ liệu ở mọi biên `long`, hãy dùng thuật toán căn nguyên có kiểm soát hoặc phép chia an toàn để so sánh.

Với Java có API `Math.sqrt`, **không mặc định** `(long)Math.sqrt(n)` là kết quả căn nguyên chính xác trên mọi `long`. Nếu nghiệp vụ là số nguyên và không chấp nhận sai một đơn vị, hãy định nghĩa rõ quy trình kiểm tra và test các biên gần `Long.MAX_VALUE`.

## 10. `Math.sqrt` và `Math.pow(x,0.5)` khác nhau ở ý định

Về ý nghĩa toán học, với `x >= 0`, `x^0.5` là căn bậc hai. Tuy nhiên, trong Java:

```java
double a = Math.sqrt(9.0);     // 3.0.
double b = Math.pow(9.0, 0.5); // 3.0 trong ví dụ này.
```

Hai cách không nhất thiết có cùng **bảo đảm sai số hay quy tắc các giá trị đặc biệt** cho mọi tổ hợp. `sqrt` được thiết kế cho một phép toán cụ thể và có bảo đảm correctly rounded, nên là lựa chọn mặc định khi bạn thật sự muốn **căn bậc hai**.

Với `Math.pow(x,0.5)`, bạn đang đi qua một hàm lũy thừa tổng quát. Mỗi hàm có tập quy tắc riêng đối với `-0.0`, NaN, Infinity, số mũ đặc biệt, và độ chính xác; cần dựa vào **contract của hàm được gọi**, không dùng biến đổi đại số vô điều kiện để đoán mọi output.

Đối với `x < 0`, cả căn bậc hai thực và `pow` với số mũ `0.5` đều không cho một số thực hữu hạn; Java trả NaN theo trường hợp tương ứng, chứ không tự tạo số phức.

## 11. Trường hợp biên: số âm, zero, Infinity, NaN

| Đầu vào/phép tính | Kết quả minh họa | Giải thích |
| --- | --- | --- |
| `Math.sqrt(-4.0)` | `NaN` | Không có căn bậc hai thực của -4 |
| `Math.sqrt(-0.0)` | `-0.0` | Giữ dấu zero |
| `Math.cbrt(-8.0)` | `-2.0` | Căn bậc ba thực tồn tại |
| `Math.cbrt(-0.0)` | `-0.0` | Giữ dấu zero |
| `Math.pow(-2.0, 3.0)` | `-8.0` | Mũ nguyên lẻ |
| `Math.pow(-2.0, 4.0)` | `16.0` | Mũ nguyên chẵn |
| `Math.pow(-8.0, 1.0/3.0)` | `NaN` | Cơ số âm, mũ hữu hạn không nguyên |
| `Math.pow(Double.NaN, 0.0)` | `1.0` | Quy tắc đặc biệt của `pow`: số mũ 0 |
| `Math.sqrt(Double.POSITIVE_INFINITY)` | `+Infinity` | Căn vô cực dương |
| `Math.cbrt(Double.POSITIVE_INFINITY)` | `+Infinity` | Căn bậc ba vô cực dương |
| `Math.pow(1e200, 2)` | `+Infinity` | Kết quả toán học vượt dải hữu hạn `double` |
| `Math.pow(1e-200, 2)` | `+0.0` | Kết quả quá nhỏ, underflow về zero |

**Lưu ý:** `NaN` không bằng chính nó dưới phép `==`. Để nhận biết NaN, dùng `Double.isNaN(value)` hoặc `Double.isFinite(value)` khi bạn muốn bảo đảm kết quả hữu hạn. Muốn phân biệt `+0.0` và `-0.0` chính xác từng bit, dùng `Double.doubleToRawLongBits` thay vì `==`.

Trong một số nghiệp vụ, đầu vào âm cho `sqrt` cần được **từ chối tường minh** trước khi gọi hàm, thay vì âm thầm tạo NaN rồi truyền qua các bước sau:

```java
static double positiveRoot(double x) {
    if (!Double.isFinite(x) || x < 0.0) {
        throw new IllegalArgumentException("root input must be finite and >= 0");
    }
    return Math.sqrt(x);
}
```

Đây là **phương thức minh họa**, không phải API mặc định của JDK. Việc `x < 0.0` vẫn chấp nhận `-0.0` vì so sánh đó là false; nếu nghiệp vụ cần cấm âm zero, hãy kiểm tra bit dấu riêng. Định nghĩa domain theo yêu cầu ứng dụng, không suy rằng Java sẽ ném exception thay bạn.

## 12. Overflow, underflow và vì sao `Math.hypot` có thể thích hợp hơn `sqrt(x*x+y*y)`

Một công thức toán học phổ biến để tính độ dài vector hai chiều là:

```text
length = sqrt(x^2 + y^2)
```

Nhưng trong `double`:

```java
double x = 1.0e200;
double y = 1.0e200;

double naive = Math.sqrt(x * x + y * y);
double robust = Math.hypot(x, y);
```

Ở công thức `naive`, phép nhân `x*x` đã vượt phạm vi hữu hạn `double` (vì `1e400` quá lớn), nên kết quả trung gian là Infinity. `sqrt(Infinity)` vẫn Infinity, mặc dù độ dài vector toán học khoảng `1.414e200` và **vẫn nằm trong dải double**.

`Math.hypot(x,y)` được thiết kế để giảm nguy cơ **overflow/underflow trung gian** trong bài toán tính độ dài. Trường hợp này nó trả kết quả hữu hạn. Tương tự, với dữ liệu rất nhỏ, phép tính bình phương trực tiếp có thể underflow về 0, trong khi `hypot` có cách tính ổn định hơn.

Do đó, **lựa chọn đúng không phải lúc nào cũng là pow hoặc sqrt**: đôi khi một API chuyên dụng như `Math.hypot` là phù hợp hơn cả chuỗi `Math.sqrt(Math.pow(x,2)+Math.pow(y,2))`.

## 13. Đừng tạo phép nhân số nguyên lớn chỉ vì căn trả double

Đối với `int`, phép nhân có thể tràn **trước** khi kết quả được truyền sang `Math.sqrt`:

```java
int x = 50_000;
int y = x * x;  // -1794967296: overflow int.
double wrong = Math.sqrt(y); // NaN vì y âm.
```

Trong ví dụ, `50_000^2 = 2_500_000_000` vượt `Integer.MAX_VALUE`. Các bit thấp còn lại được Java diễn giải thành một số `int` âm. Khi đưa số âm đó vào `Math.sqrt`, kết quả NaN; nguyên nhân **đầu tiên** là phép nhân nguyên bị tràn, không phải `sqrt` “sai”.

Nếu cần tính bình phương trước dưới dạng `long`:

```java
int x = 50_000;
long exactSquare = (long) x * x;  // 2_500_000_000L.
double root = Math.sqrt(exactSquare); // 50000.0 trong ví dụ.
```

Dấu `(long)` phải có **trước phép nhân**, không phải `(long)(x*x)`; cast sau khi tràn không thể khôi phục kết quả. Nếu phạm vi có thể vượt `long`, dùng `BigInteger` hoặc kiểm tra phạm vi tường minh.

## 14. `Math` hay `StrictMath`?

Cả `Math` và `StrictMath` đều có các phép tính `pow`, `sqrt`, `cbrt` và nhiều phép toán khác. Chúng cung cấp API gần như tương đương về mục đích, nhưng **hợp đồng cài đặt và khả năng tái lập bit** có những điểm khác biệt:

- **`Math`** có thể được triển khai tối ưu theo nền tảng, miễn đáp ứng yêu cầu về độ chính xác và ngữ nghĩa của API.
- **`StrictMath`** hướng tới kết quả tái lập theo cách tính được chuẩn hóa cho nhiều hàm, với các quy định nghiêm ngặt hơn về thuật toán tham chiếu. Một số hàm như `sqrt` có bảo đảm làm tròn chính xác.
- Hai lớp **có thể trả cùng kết quả cho nhiều input**, như `Math.sqrt(9.0)` và `StrictMath.sqrt(9.0)`, nhưng không nên phát biểu mọi lời gọi luôn giống nhau tới từng bit nếu đặc tả không đòi hỏi.

```java
double a = StrictMath.pow(2.0, 10.0); // 1024.0.
double b = StrictMath.sqrt(9.0);      // 3.0.
double c = StrictMath.cbrt(27.0);     // 3.0.
```

Trong ứng dụng thường ngày, `Math` là lựa chọn trực tiếp. Nếu một hệ thống yêu cầu **tính tái lập numerical results qua nhiều môi trường**, cần xem kỹ yêu cầu so sánh bit, JVM và hợp đồng `StrictMath` của từng phép toán; dùng đúng kiểu, thứ tự tính và bộ test tham chiếu. Chỉ thay tên lớp không làm mọi phép tính khác trong ứng dụng tự trở nên deterministic.

Với Java 17, các biểu thức dấu phẩy động có các ràng buộc nhất quán từ nền tảng ngôn ngữ, nhưng điều đó không loại bỏ các sai số làm tròn, những trường hợp đặc biệt hoặc sự khác nhau giữa các thuật toán tính gần đúng.

## 15. Kiểm tra `double` trước và sau khi tính

Một API tính khoảng cách, căn hoặc lũy thừa cho người dùng có thể cần chính sách đầu vào như:

- Cho phép âm hay không? `cbrt` nhận số âm hữu hạn; `sqrt` không có căn thực cho số âm khác zero.
- Cho phép NaN/Infinity hay không? `Double.isFinite` kiểm tra số hữu hạn.
- Có chấp nhận kết quả Infinity nếu phép toán overflow hay không? Nếu không, kiểm tra **đầu ra** sau khi gọi.
- Có chấp nhận underflow thành zero hay không? Với số rất nhỏ, kết quả khác 0 về toán học vẫn có thể thành 0 trong `double`.
- Kết quả có cần chính xác từng đơn vị nguyên hoặc decimal không? Nếu có, tránh lạm dụng `double`/`Math.pow`.
- Có yêu cầu dấu zero hay không? `-0.0` và `+0.0` so sánh `==` nhưng khác bit.
- Có đòi hỏi số thực dương do **nghiệp vụ** không, ngay cả khi toán học cho giá trị âm hợp lệ?

Một ví dụ bảo vệ kết quả:

```java
static double finiteSquareRoot(double value) {
    if (!Double.isFinite(value) || value < 0.0) {
        throw new IllegalArgumentException("invalid square root input");
    }
    double result = Math.sqrt(value);
    if (!Double.isFinite(result)) {
        throw new ArithmeticException("non-finite result");
    }
    return result;
}
```

Đây là phương thức dùng trong lớp ứng dụng, không phải phương thức có sẵn trong `Math`. Hãy chọn loại ngoại lệ và thông báo theo contract API thực tế; không nhất thiết mọi hệ thống phải cấm Infinity hay NaN.

## 16. Chương trình Java 17+ hoàn chỉnh

Lưu mã sau với tên **`PowerRootDemo.java`**:

```java
public class PowerRootDemo {
    static long powExact(long base, int exponent) {
        if (exponent < 0) {
            throw new IllegalArgumentException("negative exponent");
        }
        long result = 1L;
        long factor = base;
        int remaining = exponent;
        while (remaining > 0) {
            if ((remaining & 1) != 0) {
                result = Math.multiplyExact(result, factor);
            }
            remaining >>>= 1;
            if (remaining > 0) {
                factor = Math.multiplyExact(factor, factor);
            }
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println("pow2_10=" + Math.pow(2.0, 10.0));
        System.out.println("pow9_half=" + Math.pow(9.0, 0.5));
        System.out.println("sqrt9=" + Math.sqrt(9.0));
        System.out.println("cbrt27=" + Math.cbrt(27.0));
        System.out.println("cbrtNegative=" + Math.cbrt(-8.0));
        System.out.println("powNegativeOdd=" + Math.pow(-2.0, 3.0));
        System.out.println("powNegativeEven=" + Math.pow(-2.0, 4.0));
        System.out.println("powNegativeFractionNaN="
                + Double.isNaN(Math.pow(-8.0, 1.0 / 3.0)));
        System.out.println("sqrtNegativeNaN="
                + Double.isNaN(Math.sqrt(-4.0)));
        System.out.println("sqrtMinusZeroBits="
                + (Double.doubleToRawLongBits(Math.sqrt(-0.0))
                == Double.doubleToRawLongBits(-0.0)));
        System.out.println("cbrtMinusZeroBits="
                + (Double.doubleToRawLongBits(Math.cbrt(-0.0))
                == Double.doubleToRawLongBits(-0.0)));
        System.out.println("powNaNExponentZero="
                + Math.pow(Double.NaN, 0.0));
        System.out.println("powOverflowInfinite="
                + Double.isInfinite(Math.pow(1.0e200, 2.0)));
        System.out.println("powUnderflowZero="
                + (Math.pow(1.0e-200, 2.0) == 0.0));
        System.out.println("sqrtInfinity="
                + Math.sqrt(Double.POSITIVE_INFINITY));
        System.out.println("cbrtInfinity="
                + Math.cbrt(Double.POSITIVE_INFINITY));
        System.out.println("sqrtMinPositive="
                + (Math.sqrt(Double.MIN_VALUE) > 0.0));
        System.out.println("cbrtMinPositive="
                + (Math.cbrt(Double.MIN_VALUE) > 0.0));

        double large = 1.0e200;
        System.out.println("naiveHypotInfinite="
                + Double.isInfinite(Math.sqrt(large * large + large * large)));
        System.out.println("hypotFinite="
                + Double.isFinite(Math.hypot(large, large)));

        int x = 50_000;
        System.out.println("intMultiplyOverflow=" + (x * x));
        System.out.println("powExact3_10=" + powExact(3L, 10));
        try {
            System.out.println("powExact2_63=" + powExact(2L, 63));
        } catch (ArithmeticException ex) {
            System.out.println("powExact2_63=ArithmeticException");
        }
        System.out.println("pow2_53PlusOneLost="
                + (Math.pow(2.0, 53.0) + 1.0 == Math.pow(2.0, 53.0)));
        System.out.println("strictSqrt9=" + StrictMath.sqrt(9.0));
        System.out.println("strictCbrt27=" + StrictMath.cbrt(27.0));
    }
}
```

Biên dịch/chạy tại thư mục chứa tệp:

```bash
javac --release 17 -encoding UTF-8 PowerRootDemo.java
java PowerRootDemo
```

Stdout chính xác:

```text
pow2_10=1024.0
pow9_half=3.0
sqrt9=3.0
cbrt27=3.0
cbrtNegative=-2.0
powNegativeOdd=-8.0
powNegativeEven=16.0
powNegativeFractionNaN=true
sqrtNegativeNaN=true
sqrtMinusZeroBits=true
cbrtMinusZeroBits=true
powNaNExponentZero=1.0
powOverflowInfinite=true
powUnderflowZero=true
sqrtInfinity=Infinity
cbrtInfinity=Infinity
sqrtMinPositive=true
cbrtMinPositive=true
naiveHypotInfinite=true
hypotFinite=true
intMultiplyOverflow=-1794967296
powExact3_10=59049
powExact2_63=ArithmeticException
pow2_53PlusOneLost=true
strictSqrt9=3.0
strictCbrt27=3.0
```

Một số điểm nổi bật từ chương trình:

1. `pow2_10=1024.0` chứng minh kết quả của `Math.pow` là **`double`**, dù phép toán tương ứng là lũy thừa số nguyên.
2. `sqrt9`, `cbrt27` minh họa hai căn chuyên dụng; `cbrtNegative=-2.0` nhưng `powNegativeFractionNaN=true` phân biệt ngữ nghĩa căn thực âm.
3. `sqrtNegativeNaN=true` và hai dòng `...MinusZeroBits=true` cho thấy **âm khác zero** không giống **âm zero**.
4. `powNaNExponentZero=1.0` nhắc rằng `pow` có các quy tắc đặc biệt; không thể suy hết bằng quy tắc toán học thực đơn giản.
5. `powOverflowInfinite` và `powUnderflowZero` minh họa giới hạn biểu diễn `double`.
6. `naiveHypotInfinite=true` nhưng `hypotFinite=true` giải thích vì sao nên dùng `Math.hypot` để tính độ dài vector lớn.
7. `intMultiplyOverflow=-1794967296` cho thấy phép nhân `int` có thể tràn; `powExact3_10=59049` và `powExact2_63=ArithmeticException` minh họa phép lũy thừa nguyên **có kiểm tra phạm vi**.
8. `pow2_53PlusOneLost=true` chứng tỏ miền `double` không biểu diễn chính xác mọi số nguyên lớn.
9. Hai dòng `strictSqrt9`, `strictCbrt27` minh họa cú pháp `StrictMath`.

Bằng việc dùng các phương thức `Double.isNaN`/`Double.isInfinite`, chương trình tránh giả định mọi kết quả đều là số hữu hạn thông thường.

## 17. Bảng quyết định: nên dùng phương thức nào?

| Yêu cầu thực tế | Chọn | Lý do |
| --- | --- | --- |
| Tính `a^b` với `double` và mũ bất kỳ trong miền hợp lệ | `Math.pow(a,b)` | Cú pháp tổng quát cho dấu phẩy động |
| Tính căn bậc hai của `x >= 0` | `Math.sqrt(x)` | Hàm chuyên dụng với bảo đảm correctly rounded |
| Tính căn bậc ba thực, kể cả `x < 0` | `Math.cbrt(x)` | Hỗ trợ cơ số âm theo ngữ nghĩa căn bậc ba |
| Tính `x*x` hoặc `x*x*x` trên `double` | Nhân tường minh khi phù hợp | Rõ mũ nhỏ; kiểm chứng sai số/hiệu năng nếu quan trọng |
| Tính độ dài `sqrt(x*x+y*y)` với `double` có độ lớn cực đoan | `Math.hypot(x,y)` | Tránh overflow/underflow trung gian không cần thiết |
| Tính `3^10` dưới dạng `long` và báo lỗi nếu vượt `long` | Nhân có `Math.multiplyExact` | Không chuyển qua `double` làm mất đơn vị |
| Tính `2^100` thành số nguyên chính xác | `BigInteger.pow(100)` | Số nguyên lớn tùy ý, không giới hạn ở 64 bit |
| Cần tái lập `pow`/`cbrt` theo contract `StrictMath` | `StrictMath` và QA tương ứng | Lựa chọn ngữ nghĩa kết quả tái lập |
| Cần căn số âm trong miền số phức | Thư viện số phức | `Math.sqrt` chỉ trả `double`, không biểu diễn số phức |
| Cần kiểm tra số nguyên có phải chính phương chính xác | Thuật toán nguyên có kiểm tra biên | `double` có thể làm tròn dữ liệu `long` lớn |

Một lựa chọn đúng không chỉ cho ra “con số gần mong muốn”, mà còn phải phù hợp **miền đầu vào, kiểu kết quả, chính sách sai số và trường hợp lỗi**.

## 18. Lỗi phổ biến khi dùng `pow`, `sqrt`, `cbrt`

| Lỗi/nhầm lẫn | Hậu quả | Cách đúng |
| --- | --- | --- |
| Viết `2 ^ 3` để lấy 2 mũ 3 | Java dùng XOR theo bit → 1 | Dùng `Math.pow(2,3)` hoặc nhân phù hợp |
| Tính căn bậc ba âm bằng `Math.pow(x,1.0/3.0)` | Có thể trả NaN | Dùng `Math.cbrt(x)` |
| Dùng `Math.sqrt(-4)` rồi mong exception | Hàm trả NaN, không ném `ArithmeticException` | Kiểm tra domain hoặc `Double.isNaN` |
| Giả định `sqrt(-0.0)` là NaN | Kết quả giữ `-0.0` | Kiểm tra signed zero khi có yêu cầu |
| Dùng `(long)Math.pow(large, n)` để có số nguyên chính xác | Sai số biểu diễn, overflow/saturation khi chuyển | Dùng `BigInteger.pow` hoặc `multiplyExact` |
| Viết `Math.sqrt(x*x+y*y)` với số rất lớn | Bình phương trung gian thành Infinity | Dùng `Math.hypot` |
| Cast kết quả sau khi `int * int` tràn | Không cứu được kết quả đã sai | Widen trước khi nhân hoặc `Math.multiplyExact` |
| Nghĩ `Math.pow` luôn giữ nguyên từng bit so với nhân trực tiếp | Đường tính/rounding có thể khác | Chọn phép toán có ngữ nghĩa rõ và QA biên |
| Nghĩ `Math.sqrt` luôn trả số nguyên khi input chính phương lớn | Kết quả là `double` | Dùng thuật toán số nguyên khi cần exact |
| Dùng `== Double.NaN` để phát hiện lỗi | NaN không bằng bất kỳ số nào, kể cả chính nó | `Double.isNaN` hoặc `Double.isFinite` |
| Nghĩ mọi `Math` và `StrictMath` đều bit-exact như nhau trên mọi input | Contract về tái lập khác nhau theo hàm | Dựa vào API contract và test mục tiêu |
| Tối ưu trước bằng các mẹo biến đổi đại số | Có thể đổi sai số, zero, Infinity, NaN | Kiểm thử cả miền đặc biệt và yêu cầu chính xác |

## 19. Câu hỏi tự kiểm tra

1. **`Math.pow(2,10)` trả về kiểu nào?** `double`, giá trị `1024.0`. Java nâng các đối số `int` thành `double`.
2. **Có thể dùng `^` để lũy thừa trong Java không?** Không. `^` là XOR.
3. **`Math.sqrt(9)` và `Math.pow(9,0.5)` đều cho 3.0 trong ví dụ, vậy chúng tương đương trong mọi trường hợp không?** Không nên giả định đồng nhất toàn bộ contract về rounding và trường hợp biên.
4. **`Math.sqrt(-4.0)` cho gì?** `NaN`, không phải exception.
5. **Vì sao `Math.cbrt(-8.0)` hợp lệ?** Vì căn bậc ba thực của số âm tồn tại; kết quả là `-2.0`.
6. **Vì sao `Math.pow(-8.0,1.0/3.0)` không trả `-2.0`?** Số mũ `double` hữu hạn nhưng không nguyên; với cơ số âm, `Math.pow` trả NaN theo đặc tả.
7. **`Math.sqrt(-0.0)` có mất bit dấu không?** Không; kết quả vẫn là `-0.0`.
8. **Tính `sqrt(x*x+y*y)` với `x=y=1e200` nên dùng gì?** `Math.hypot(x,y)`, vì bình phương riêng lẻ sẽ overflow.
9. **Dùng `Math.pow(2.0,53)+1.0` có giữ được đơn vị `+1` không?** Không; ở `2^53`, ULP đã là 2.
10. **Nếu muốn lũy thừa số nguyên không chấp nhận tràn, nên dùng gì?** `Math.multiplyExact` trong thuật toán nhân nguyên hoặc `BigInteger.pow`.
11. **`Math.sqrt` và `Math.cbrt` đều xử lý NaN như số thường không?** Không; phải kiểm tra giá trị đặc biệt theo contract dấu phẩy động.
12. **Nên chọn `Math` hay `StrictMath` khi cần tái lập bit?** Xem hợp đồng của từng hàm và kiểm chứng theo môi trường; `StrictMath` hướng tới kết quả tái lập chặt chẽ hơn cho nhiều hàm.

**Ghi nhớ:** `Math.pow` là **lũy thừa `double` tổng quát**, `Math.sqrt` là **căn bậc hai chuyên dụng** và `Math.cbrt` là **căn bậc ba thực kể cả với số âm**. Chọn chúng theo **bản chất bài toán**, không chỉ theo biến đổi đại số. Khi tính độ dài vector dùng `Math.hypot` để hạn chế tràn trung gian; khi tính lũy thừa **số nguyên chính xác**, dùng phép nhân có kiểm tra hoặc `BigInteger.pow`, không đặt niềm tin sai vào `double`.
