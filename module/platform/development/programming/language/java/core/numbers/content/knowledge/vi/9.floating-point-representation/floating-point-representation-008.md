# Số 0 dương, số 0 âm, vô cực và NaN trong Java

Trong Java, `float` và `double` không chỉ biểu diễn các số thực hữu hạn thông thường. Theo cơ chế dấu phẩy động nhị phân IEEE 754, chúng còn biểu diễn được **hai số 0 có dấu** (`+0.0`, `-0.0`), **vô cực dương/âm** (`+Infinity`, `-Infinity`) và **NaN** (*Not a Number*).

Các giá trị này không phải ngoại lệ Java và cũng không nhất thiết báo lỗi khi xuất hiện. Ví dụ:

```java
double positiveZero = 0.0;
double negativeZero = -0.0;
System.out.println(positiveZero == negativeZero); // true

System.out.println(1.0 / positiveZero); // Infinity
System.out.println(1.0 / negativeZero); // -Infinity
System.out.println(0.0 / 0.0);          // NaN
```

Ba phép chia dấu phẩy động trên **không ném `ArithmeticException`**. Nếu chương trình xử lý số đo, mô phỏng, thống kê, sắp xếp, lưu dữ liệu hoặc gửi JSON mà không xét tới giá trị đặc biệt, kết quả có thể sai âm thầm.

Bài học thuộc phần **Biểu diễn dấu phẩy động** của **Java core – numbers**, giúp giải thích biểu diễn và phép toán của các giá trị này, phân biệt `==` với `Double.compare`/`Double.equals`, và đưa ra cách kiểm tra dữ liệu thực tế.

## 1. Vì sao một kiểu số có nhiều “giá trị đặc biệt”?

`float` (32 bit) và `double` (64 bit) sử dụng định dạng dấu phẩy động nhị phân. Với giá trị hữu hạn, cách biểu diễn có thành phần dấu, số mũ và phần trị. Một số tổ hợp bit được dành riêng cho **zero**, **infinity** và **NaN**.

| Đặc điểm | `float` | `double` |
| --- | --- | --- |
| Tổng số bit | 32 | 64 |
| Bit dấu | 1 | 1 |
| Bit số mũ | 8 | 11 |
| Bit phần trị lưu trữ | 23 | 52 |
| Độ chính xác phần trị với bit ẩn | 24 bit | 53 bit |
| Hai dạng số 0 | `+0.0f`, `-0.0f` | `+0.0d`, `-0.0d` |
| Vô cực | `Float.POSITIVE_INFINITY`, `Float.NEGATIVE_INFINITY` | `Double.POSITIVE_INFINITY`, `Double.NEGATIVE_INFINITY` |
| NaN | `Float.NaN` | `Double.NaN` |

Khi một số hữu hạn bị tràn về độ lớn của định dạng dấu phẩy động, kết quả theo phép toán thông thường có thể trở thành vô cực. Khi một phép toán không có kết quả số thực có nghĩa trong quy tắc IEEE 754, nó có thể tạo NaN. Khi kết quả quá nhỏ, nó có thể thành số rất nhỏ, **subnormal**, hoặc thành số 0 có dấu tùy độ lớn và cách làm tròn.

Không nên nhầm với số nguyên Java: `int`/`long` **không có** `NaN`, `Infinity` hoặc hai số 0 khác dấu. Tràn số nguyên và chia nguyên cho 0 tuân theo quy tắc khác.

## 2. Số 0 dương (+0.0) và số 0 âm (-0.0)

Trong toán học thông thường, 0 không có hai giá trị khác nhau. Ở IEEE 754, `+0.0` và `-0.0` có **hai mã bit riêng**:

```text
double +0.0 = 0x0000000000000000
double -0.0 = 0x8000000000000000

float  +0.0 = 0x00000000
float  -0.0 = 0x80000000
```

Khác biệt nằm ở bit dấu. Vì phần trị và số mũ đều biểu diễn zero, hai giá trị cùng được xem là bằng 0 trong phép so sánh số học `==`, nhưng **dấu của zero vẫn có thể ảnh hưởng phép toán tiếp theo**.

```java
double plusZero = 0.0;
double minusZero = -0.0;

System.out.println(plusZero == minusZero); // true
System.out.println(plusZero < minusZero);  // false
System.out.println(minusZero < plusZero);  // false
```

Với toán tử so sánh số học, `+0.0` và `-0.0` có cùng vị trí trên trục số. Nhưng Java vẫn giữ được dấu, cho phép nhận biết qua phép chia hoặc bit biểu diễn.

### 2.1. Hai phép chia cho zero cho kết quả khác dấu

```java
double plus = 1.0 / +0.0;  // Infinity
double minus = 1.0 / -0.0; // -Infinity
```

Dấu của kết quả tuân theo dấu toán hạng trong phép chia dấu phẩy động. Tương tự:

```java
double negativeOverPositive = -1.0 / +0.0; // -Infinity
double negativeOverNegative = -1.0 / -0.0; // Infinity
```

Do vậy một kiểm tra `value == 0.0` **không phân biệt được dấu** nhưng cả hai zero có thể dẫn tới hành vi khác ở phép toán sau.

### 2.2. Nhận biết zero âm

Một cách minh họa là đọc bit bằng `Double.doubleToRawLongBits`:

```java
double z = -0.0;
boolean negativeZero =
        z == 0.0 && Double.doubleToRawLongBits(z) < 0;
// true vì bit dấu ở bit cao nhất.
```

Nếu cần kiểm tra cả `float`, có thể dùng `Float.floatToRawIntBits`. So sánh `1.0 / z` với `Double.NEGATIVE_INFINITY` cũng phân biệt được zero âm, nhưng dùng bit trực tiếp thường thể hiện ý định rõ hơn khi thật sự phải kiểm tra dấu zero.

Không lấy `-0.0 == 0.0` làm bằng chứng rằng mã bit giống nhau. Đừng cho rằng chuyển qua một định dạng văn bản hoặc xử lý dữ liệu trung gian luôn bảo toàn dấu zero: cần kiểm chứng hợp đồng thư viện và giao thức.

### 2.3. Math.abs, signum, copySign, min/max

Một số API phân biệt hoặc giữ dấu zero:

```java
Math.abs(-0.0);            // +0.0
Math.signum(-0.0);         // -0.0
Math.copySign(1.0, -0.0);  // -1.0
Math.min(+0.0, -0.0);      // -0.0
Math.max(+0.0, -0.0);      // +0.0
```

`Math.min` và `Math.max` có quy tắc riêng với signed zero: `-0.0` được coi là nhỏ hơn `+0.0` khi chọn kết quả. Đây là lý do những hàm này **không hoàn toàn tương đương** với một biểu thức điều kiện tự viết chỉ dùng `<` hoặc `>` nếu cần bảo toàn dấu zero.

**Lưu ý:** giá trị `Math.signum(-0.0)` in ra là `-0.0`, không phải `-1.0`; `signum` trả lại zero có dấu đối với đầu vào zero.

## 3. Vô cực dương và vô cực âm

Java định nghĩa các hằng:

```java
double positive = Double.POSITIVE_INFINITY;
double negative = Double.NEGATIVE_INFINITY;
float positiveFloat = Float.POSITIVE_INFINITY;
float negativeFloat = Float.NEGATIVE_INFINITY;
```

Vô cực có thể xuất hiện từ việc chia một số hữu hạn khác 0 cho zero hoặc từ phép tính thực có kết quả quá lớn để biểu diễn:

```java
double a = 1.0 / 0.0;               // Infinity
double b = -1.0 / 0.0;              // -Infinity
double c = Double.MAX_VALUE * 2.0; // Infinity
```

Các giá trị vô cực không phải là “số lớn nhất có thể biểu diễn”. `Double.MAX_VALUE` là **số hữu hạn dương lớn nhất**, còn `Double.POSITIVE_INFINITY` là một giá trị đặc biệt lớn hơn mọi giá trị hữu hạn trong các phép so sánh thông thường.

```java
Double.MAX_VALUE < Double.POSITIVE_INFINITY; // true
Double.NEGATIVE_INFINITY < -Double.MAX_VALUE; // true
```

Một số phép toán với vô cực:

| Biểu thức | Kết quả | Ý nghĩa |
| --- | --- | --- |
| `1.0 / 0.0` | `Infinity` | Số dương hữu hạn chia cho zero dương |
| `-1.0 / 0.0` | `-Infinity` | Số âm hữu hạn chia cho zero dương |
| `Double.MAX_VALUE * 2.0` | `Infinity` | Tràn miền giá trị hữu hạn |
| `1.0 / Double.POSITIVE_INFINITY` | `+0.0` | Kết quả tiến về zero dương |
| `-1.0 / Double.POSITIVE_INFINITY` | `-0.0` | Kết quả tiến về zero âm |
| `Double.POSITIVE_INFINITY + 10.0` | `Infinity` | Vô cực cộng số hữu hạn |
| `Double.POSITIVE_INFINITY + Double.NEGATIVE_INFINITY` | `NaN` | Hai vô cực khác dấu cộng nhau |
| `Double.POSITIVE_INFINITY / Double.POSITIVE_INFINITY` | `NaN` | Dạng không xác định theo phép toán IEEE 754 |

Các biểu thức đó không tự tạo `ArithmeticException` chỉ vì xuất hiện `Infinity` hoặc `NaN`.

### 3.1. So sánh với vô cực

`Infinity` so sánh có thứ tự với các số hữu hạn:

```java
double x = Double.POSITIVE_INFINITY;

x > 1e300;                           // true
x == Double.POSITIVE_INFINITY;       // true
Double.NEGATIVE_INFINITY < -1e300;   // true
```

Tuy nhiên, đừng dùng vô cực như một giá trị mặc định “không có dữ liệu” trừ khi đặc tả API đã xác định rõ. Một phép tổng hợp, trung bình hoặc chuẩn hóa có thể vô tình truyền vô cực vào kết quả cuối.

## 4. NaN: giá trị biểu thị phép toán không có kết quả số thực xác định

`NaN` viết tắt của *Not a Number*. Nó là giá trị dấu phẩy động đặc biệt, có thể sinh ra bởi những phép toán như:

```java
double a = 0.0 / 0.0;           // NaN
double b = Math.sqrt(-1.0);     // NaN
double c = Double.POSITIVE_INFINITY
        - Double.POSITIVE_INFINITY; // NaN
double d = Double.NaN;
```

Không nên hiểu `NaN` chỉ là “lỗi cú pháp” hoặc một exception. Một khi NaN tham gia phép toán dấu phẩy động, kết quả của nhiều phép số học khác tiếp tục là NaN:

```java
double unknown = Double.NaN;
double result = unknown + 100.0; // NaN
```

Vì vậy, NaN có thể lan theo dòng xử lý dữ liệu. Nếu chương trình lưu nó như một phép đo hợp lệ, các phép thống kê hoặc mô hình dựa trên kết quả có thể trở nên khó kiểm soát.

### 4.1. Tại sao NaN != NaN?

Theo quy tắc so sánh số học của Java:

```java
double x = Double.NaN;

System.out.println(x == x); // false
System.out.println(x != x); // true
System.out.println(x < 1.0);  // false
System.out.println(x > 1.0);  // false
System.out.println(x <= 1.0); // false
System.out.println(x >= 1.0); // false
```

Mọi phép so sánh thứ tự với NaN bằng `<`, `>`, `<=`, `>=` đều trả `false`. `==` với NaN cũng trả `false`, kể cả khi so một biến với chính nó; `!=` trả `true`.

Bởi vậy, biểu thức `x != x` có thể phát hiện NaN về mặt kỹ thuật, nhưng **nên dùng `Double.isNaN(x)` hoặc `Float.isNaN(x)`** cho rõ ý định và tránh làm người đọc hiểu nhầm.

### 4.2. NaN làm hỏng kiểm tra khoảng

Giả sử hệ thống chấp nhận nhiệt độ trong khoảng từ -50 đến 150:

```java
static boolean badValidation(double temperature) {
    return !(temperature < -50.0 || temperature > 150.0);
}
```

Với `temperature = Double.NaN`, cả hai biểu thức `<` và `>` đều là `false`; phép phủ định khiến hàm **trả `true`** dù NaN không phải nhiệt độ hợp lệ.

Cách kiểm tra đúng khi chỉ chấp nhận giá trị hữu hạn:

```java
static boolean validTemperature(double value) {
    return Double.isFinite(value)
            && value >= -50.0
            && value <= 150.0;
}
```

Hàm kiểm tra này loại trừ cả `NaN`, `+Infinity` và `-Infinity`; sau đó mới kiểm tra khoảng. Nếu miền dữ liệu cho phép vô cực hoặc NaN có ý nghĩa riêng, phải thiết kế một nhánh xử lý tường minh, không vô tình coi chúng là số đo bình thường.

## 5. Các API kiểm tra NaN, vô cực và tính hữu hạn

Java có các phương thức kiểm tra tường minh:

| Phương thức | Trả `true` khi nào? |
| --- | --- |
| `Double.isNaN(value)` | Giá trị là NaN |
| `Double.isInfinite(value)` | Giá trị là vô cực dương hoặc âm |
| `Double.isFinite(value)` | Giá trị không phải NaN và không phải vô cực |
| `Float.isNaN(value)` | Giá trị `float` là NaN |
| `Float.isInfinite(value)` | Giá trị `float` là vô cực |
| `Float.isFinite(value)` | Giá trị `float` hữu hạn |

Ví dụ:

```java
Double.isFinite(0.0);                 // true
Double.isFinite(-0.0);                // true
Double.isFinite(Double.NaN);         // false
Double.isFinite(Double.POSITIVE_INFINITY); // false

Double.isInfinite(-1.0 / 0.0);       // true
Double.isNaN(0.0 / 0.0);             // true
```

**Signed zero vẫn là giá trị hữu hạn.** Nếu ứng dụng có yêu cầu riêng “không được có zero âm”, chỉ kiểm tra `isFinite` là chưa đủ; phải phát hiện bit dấu zero hoặc chuẩn hóa có chủ đích.

Trong lớp nhận dữ liệu/API, quy tắc đơn giản và hữu ích là **kiểm tra `isFinite` trước khi tính toán** khi ngữ nghĩa đầu vào là một số đo hữu hạn.

## 6. Toán tử ==, Double.compare và Double.equals không giống nhau

Đây là một trong những bẫy dễ gây lỗi nhất.

### 6.1. Toán tử == trên double

```java
+0.0 == -0.0;             // true
Double.NaN == Double.NaN; // false
```

`==` áp dụng so sánh số học của dấu phẩy động, không so bit và không định nghĩa thứ tự tổng quát cho NaN.

### 6.2. Double.compare cung cấp thứ tự dùng để sắp xếp

`Double.compare(a, b)` định nghĩa cách so sánh có thứ tự phù hợp cho các trường hợp đặc biệt. Trong đó:

- `Double.compare(-0.0, +0.0) < 0`: zero âm được xếp trước zero dương.
- `Double.compare(Double.NaN, Double.NaN) == 0`: hai giá trị NaN được xem là bằng nhau trong trật tự so sánh này.
- NaN được xem là **lớn hơn** `Double.POSITIVE_INFINITY` theo thứ tự của `Double.compare`, không có nghĩa NaN là một đại lượng số học lớn hơn vô cực.

```java
Double.compare(-0.0, +0.0); // Giá trị âm (cụ thể -1).
Double.compare(Double.NaN, Double.NaN); // 0
Double.compare(Double.NaN, Double.POSITIVE_INFINITY); // Dương.
```

`Float.compare` có cách xử lý tương ứng cho `float`. Các API sắp xếp/hộp wrapper có thể sử dụng cách so sánh này để có trật tự xác định cho dữ liệu chứa NaN và signed zero.

### 6.3. Double.equals so nội dung theo quy tắc wrapper

```java
Double.valueOf(-0.0).equals(Double.valueOf(+0.0)); // false
Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN)); // true
```

Điều này có thể gây ngạc nhiên:

| So sánh | Kết quả |
| --- | --- |
| `+0.0 == -0.0` | `true` |
| `Double.valueOf(+0.0).equals(Double.valueOf(-0.0))` | `false` |
| `Double.compare(-0.0, +0.0) < 0` | `true` |
| `Double.NaN == Double.NaN` | `false` |
| `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` | `true` |
| `Double.compare(Double.NaN, Double.NaN) == 0` | `true` |

Wrapper `Double.equals` dùng quy tắc dựa trên `Double.doubleToLongBits`: **phân biệt zero có dấu và chuẩn hóa các NaN cho so sánh bằng nhau**. Vì `equals` và `hashCode` của wrapper phải nhất quán, một `HashSet<Double>` có thể coi `+0.0` và `-0.0` là hai phần tử khác nhau, trong khi `==` giữa hai primitive zero trả true.

**Cách chọn:** sử dụng `==` khi thật sự muốn so sánh số học; `isNaN` để phát hiện NaN; `Double.compare` khi muốn thứ tự sắp xếp xác định; `equals` khi làm việc theo hợp đồng đối tượng của wrapper. Không coi các phép so sánh này là thay thế cho **so gần đúng theo sai số nghiệp vụ**.

## 7. Các phép toán hay tạo giá trị đặc biệt

| Biểu thức `double` | Kết quả | Bẫy thường gặp |
| --- | --- | --- |
| `1.0 / +0.0` | `Infinity` | Không có exception |
| `1.0 / -0.0` | `-Infinity` | Dấu zero ảnh hưởng dấu vô cực |
| `-1.0 / -0.0` | `Infinity` | Hai dấu âm triệt tiêu |
| `0.0 / 0.0` | `NaN` | Không phải 0 |
| `Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY` | `NaN` | Dạng không xác định |
| `0.0 * Double.POSITIVE_INFINITY` | `NaN` | Không phải 0 |
| `Double.MAX_VALUE * 2.0` | `Infinity` | Tràn dấu phẩy động |
| `-1.0 / Double.POSITIVE_INFINITY` | `-0.0` | Underflow về zero có dấu |
| `Math.sqrt(-1.0)` | `NaN` | Đầu vào ngoài miền thực |
| `Double.NaN + 3.0` | `NaN` | NaN lan truyền |

### 7.1. So sánh với chia nguyên cho zero

```java
int denominator = 0;
// int q = 1 / denominator; // Nếu chạy: ArithmeticException.

double floating = 1.0 / denominator; // Infinity, không exception.
```

Ở dòng `double floating`, vì có toán hạng `1.0` kiểu `double`, Java nâng `denominator` sang `double` rồi thực hiện phép chia dấu phẩy động. Vì thế **một thay đổi nhỏ về kiểu toán hạng có thể thay đổi cả cơ chế lỗi**.

### 7.2. Phần dư trên số thực

Java hỗ trợ toán tử `%` cho `float`/`double`, nhưng nó không trùng với toàn bộ quy tắc exception của `%` số nguyên:

```java
double r = 1.0 % 0.0; // NaN
```

Trong khi `int r = 1 % 0;` nếu được đánh giá sẽ ném `ArithmeticException`, phép phần dư dấu phẩy động với số chia zero trả NaN. Không áp dụng máy móc suy luận từ phép `%` nguyên sang phép `%` thực.

## 8. Dấu của zero khi làm tròn, in ra và chuyển kiểu

### 8.1. In ra và chuyển sang String

```java
System.out.println(+0.0); // 0.0
System.out.println(-0.0); // -0.0
System.out.println(Double.POSITIVE_INFINITY); // Infinity
System.out.println(Double.NaN); // NaN
```

Cách in này là biểu diễn dạng chuỗi thông thường của Java. Nó giúp quan sát, nhưng **không chứng minh giao thức trao đổi khác** (ví dụ JSON hay database) sẽ giữ nguyên chuỗi hoặc giá trị.

### 8.2. Chuyển từ double sang int/long

Khi thu hẹp `double`/`float` sang số nguyên Java, phần thập phân bị bỏ theo quy tắc chuyển kiểu và các giá trị đặc biệt có xử lý riêng:

- `(int) Double.NaN` là `0`.
- `(int) Double.POSITIVE_INFINITY` là `Integer.MAX_VALUE`.
- `(int) Double.NEGATIVE_INFINITY` là `Integer.MIN_VALUE`.
- `(int) -0.0` là `0`, không còn bit dấu zero.

```java
int fromNaN = (int) Double.NaN; // 0
int fromInfinity = (int) Double.POSITIVE_INFINITY; // 2147483647
int fromNegativeZero = (int) -0.0; // 0
```

Những phép cast này **không tự báo lỗi**. Nếu đầu vào của ứng dụng không được phép là NaN/vô cực, kiểm tra `Double.isFinite` trước khi cast; sau đó kiểm tra miền `int`/`long` và yêu cầu làm tròn riêng. Đặc biệt, phép cast đưa NaN thành 0 có thể che mất dữ liệu lỗi và khiến hệ thống xem một giá trị không hợp lệ như giá trị hợp lệ.

### 8.3. Negative zero có thể xuất hiện sau khi kết quả rất nhỏ

```java
double x = -Double.MIN_VALUE;
double y = x / 2.0;
System.out.println(y); // -0.0
```

`Double.MIN_VALUE` là **số double dương nhỏ nhất khác 0**, không phải số âm thấp nhất như `Integer.MIN_VALUE`. Lấy âm của nó rồi chia đôi khiến độ lớn nhỏ hơn mức subnormal nhỏ nhất có thể biểu diễn; kết quả tròn về zero âm.

Điều này thể hiện vì sao signed zero không chỉ do lập trình viên viết `-0.0` trực tiếp; nó có thể được tạo ra bởi phép toán số thực hợp lệ.

## 9. Truyền dữ liệu và chuẩn hóa: không âm thầm chấp nhận NaN hoặc Infinity

### 9.1. Dữ liệu nhập có thể chứa chuỗi đặc biệt

Một số hàm Java cho phép chuyển chuỗi đặc biệt thành giá trị `double`:

```java
Double.parseDouble("NaN");       // NaN
Double.parseDouble("Infinity");  // Infinity
Double.parseDouble("-Infinity"); // -Infinity
```

Nếu API đầu vào kỳ vọng “số hữu hạn”, chỉ gọi `Double.parseDouble` chưa đủ. Sau parse phải kiểm tra `Double.isFinite` và các ràng buộc miền.

Ví dụ:

```java
static double parseFinite(String text) {
    double value = Double.parseDouble(text);
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Finite number required");
    }
    return value;
}
```

Hàm này vẫn có thể nhận `-0.0`, vì nó là giá trị hữu hạn. Nếu ứng dụng cần cấm hoặc chuẩn hóa zero âm, xử lý như một **chính sách bổ sung**. Ngoài ra, `parseDouble` có thể ném `NumberFormatException` khi chuỗi không theo cú pháp số mà nó chấp nhận.

### 9.2. JSON tiêu chuẩn và API

Trong JSON chuẩn, ký hiệu trần `NaN`, `Infinity` và `-Infinity` **không phải các literal number hợp lệ**. Phản ứng của từng thư viện Java khi serialize giá trị đặc biệt có thể khác nhau: từ chối, thay bằng `null`, mã hóa thành chuỗi, hoặc sử dụng một định dạng mở rộng ngoài JSON chuẩn. **Không giả định** chúng tự truyền đi như number hợp lệ.

Nếu NaN/vô cực là trạng thái nghiệp vụ cần bảo toàn, nên thiết kế schema rõ ràng, ví dụ một trường `status` đi cùng giá trị tùy chọn, thay vì lén đưa các chuỗi đặc biệt vào một number field. Nếu chỉ chấp nhận số đo hữu hạn, validate trước khi serialize.

### 9.3. BigDecimal không hỗ trợ NaN và Infinity

`BigDecimal` biểu diễn số thập phân hữu hạn; nó không có giá trị NaN/vô cực tương ứng:

```java
// BigDecimal.valueOf(Double.NaN) hoặc
// BigDecimal.valueOf(Double.POSITIVE_INFINITY)
// ném NumberFormatException.
```

Không nên chuyển đổi dữ liệu `double` sang `BigDecimal` rồi kỳ vọng mọi giá trị đặc biệt được bảo toàn; kiểm tra hữu hạn trước. Nếu cần tiền hoặc số thập phân chính xác, ưu tiên tạo `BigDecimal` từ **chuỗi thập phân gốc** và áp dụng validation/rounding nghiệp vụ.

## 10. Khi nào cần giữ hoặc loại bỏ dấu zero?

Tùy ứng dụng:

- Với phép đo, mô phỏng và thuật toán IEEE 754, dấu zero có thể mang ý nghĩa của **hướng tiếp cận 0** hoặc dấu của kết quả rất nhỏ. Tự chuẩn hóa `-0.0` thành `+0.0` có thể thay đổi kết quả phép chia kế tiếp.
- Với giao diện người dùng hoặc báo cáo, `-0.0` có thể gây khó hiểu khi nó chỉ là kết quả làm tròn một giá trị âm rất gần 0. Có thể chọn hiển thị `0.0`, nhưng cần tách **cách hiển thị** khỏi dữ liệu gốc.
- Với khóa dữ liệu và so sánh đối tượng, `Double.equals` phân biệt `-0.0`/`+0.0`, nên một `Set<Double>` hoặc khóa hash có thể coi chúng khác nhau. Nếu nghiệp vụ muốn chúng cùng một khóa, hãy chuẩn hóa rõ ràng **trước khi tạo khóa**.
- Với phép thống kê, nên quyết định chính sách với NaN: loại mẫu, đánh dấu dữ liệu thiếu hoặc dừng xử lý. Không cho rằng tổng/trung bình tự bỏ qua NaN.

Ví dụ hàm chuẩn hóa zero khi và chỉ khi hợp đồng miền chấp nhận việc mất dấu:

```java
static double normalizeZero(double value) {
    return value == 0.0 ? 0.0 : value;
}
```

Hàm giữ NaN và vô cực nguyên trạng; nếu mục tiêu còn bao gồm loại bỏ chúng, phải kết hợp `Double.isFinite`. Nó cố ý biến `-0.0` thành `+0.0`. **Không áp dụng mặc định** cho một thuật toán số cần giữ hướng dấu.

## 11. Chương trình Java 17+ chạy độc lập

Lưu file **`FloatingSpecialValuesDemo.java`**. Chương trình dùng `println` thay vì định dạng phụ thuộc locale, và tách rõ zero có dấu, vô cực, NaN, so sánh wrapper, kiểm tra dữ liệu, cast và underflow thành zero âm.

```java
public class FloatingSpecialValuesDemo {
    static boolean validTemperature(double value) {
        return Double.isFinite(value)
                && value >= -50.0
                && value <= 150.0;
    }

    public static void main(String[] args) {
        double positiveZero = 0.0;
        double negativeZero = -0.0;

        System.out.println("zero-equal=" + (positiveZero == negativeZero));
        System.out.println("positive-zero-bits=" +
                Long.toHexString(Double.doubleToRawLongBits(positiveZero)));
        System.out.println("negative-zero-bits=" +
                Long.toHexString(Double.doubleToRawLongBits(negativeZero)));
        System.out.println("positive-reciprocal=" + (1.0 / positiveZero));
        System.out.println("negative-reciprocal=" + (1.0 / negativeZero));
        System.out.println("min-zero=" + Math.min(positiveZero, negativeZero));
        System.out.println("max-zero=" + Math.max(positiveZero, negativeZero));
        System.out.println("signum-negative-zero=" + Math.signum(negativeZero));

        double infinity = 1.0 / positiveZero;
        double nan = 0.0 / 0.0;
        System.out.println("infinity=" + infinity);
        System.out.println("opposite-infinities=" +
                (infinity + Double.NEGATIVE_INFINITY));
        System.out.println("zero-over-zero=" + nan);
        System.out.println("nan-equal-self=" + (nan == nan));
        System.out.println("nan-is-nan=" + Double.isNaN(nan));
        System.out.println("infinity-is-finite=" + Double.isFinite(infinity));
        System.out.println("negative-zero-is-finite=" +
                Double.isFinite(negativeZero));

        System.out.println("compare-zero=" +
                Double.compare(negativeZero, positiveZero));
        System.out.println("boxed-zero-equal=" +
                Double.valueOf(negativeZero).equals(Double.valueOf(positiveZero)));
        System.out.println("boxed-nan-equal=" +
                Double.valueOf(nan).equals(Double.valueOf(Double.NaN)));

        System.out.println("nan-temperature-valid=" + validTemperature(nan));
        System.out.println("normal-temperature-valid=" +
                validTemperature(25.0));
        System.out.println("cast-nan=" + (int) nan);
        System.out.println("cast-infinity=" + (int) infinity);

        double tinyNegative = -Double.MIN_VALUE;
        System.out.println("tiny-negative-half=" + (tinyNegative / 2.0));
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```bash
javac FloatingSpecialValuesDemo.java
java FloatingSpecialValuesDemo
```

Stdout dự kiến:

```text
zero-equal=true
positive-zero-bits=0
negative-zero-bits=8000000000000000
positive-reciprocal=Infinity
negative-reciprocal=-Infinity
min-zero=-0.0
max-zero=0.0
signum-negative-zero=-0.0
infinity=Infinity
opposite-infinities=NaN
zero-over-zero=NaN
nan-equal-self=false
nan-is-nan=true
infinity-is-finite=false
negative-zero-is-finite=true
compare-zero=-1
boxed-zero-equal=false
boxed-nan-equal=true
nan-temperature-valid=false
normal-temperature-valid=true
cast-nan=0
cast-infinity=2147483647
tiny-negative-half=-0.0
```

Đọc kết quả theo từng nhóm:

1. **Hai zero bằng nhau qua `==` nhưng khác bit.** Phép chia cho chúng cho hai vô cực khác dấu; `Math.min` và `Math.max` giữ quy tắc chọn zero có dấu.
2. **Vô cực và NaN không phải exception.** Cộng hai vô cực trái dấu ra NaN; NaN không bằng chính nó qua `==`.
3. **Đổi API so sánh đổi semantics.** `Double.compare(-0.0,+0.0)` âm; boxed `Double.equals` phân biệt hai zero nhưng xem hai NaN bằng nhau.
4. **Kiểm tra dữ liệu phải tường minh.** `Double.isFinite` loại bỏ NaN/vô cực, trong khi cast NaN về `int` trả 0 và có thể che giấu dữ liệu không hợp lệ.
5. **Số âm rất nhỏ có thể thành zero âm.** Dòng cuối không phải giá trị 0 âm được viết trực tiếp mà là kết quả underflow.

## 12. Kiểm thử và lỗi thường gặp

| Giả định sai | Vì sao nguy hiểm? | Cách kiểm tra/phòng tránh |
| --- | --- | --- |
| “Zero chỉ có một biểu diễn.” | `+0.0` và `-0.0` khác bit và cho phép chia khác dấu | Dùng bit, `Double.compare` hoặc chính sách chuẩn hóa rõ ràng khi cần |
| “`x == 0.0` nhận biết zero âm.” | Cả `+0.0` và `-0.0` đều bằng 0.0 | Dùng `Double.doubleToRawLongBits` nếu cần dấu zero |
| “Chia số thực cho 0 sẽ ném ArithmeticException.” | Có thể nhận vô cực hoặc NaN | Validate đầu vào và kết quả hữu hạn |
| “NaN có thể kiểm tra bằng `x == Double.NaN`.” | `NaN == NaN` luôn false | Dùng `Double.isNaN(x)` |
| “Nếu `x` không nhỏ hơn hoặc lớn hơn giới hạn thì x hợp lệ.” | So sánh thứ tự với NaN đều false | Kiểm tra `Double.isFinite` và điều kiện miền |
| “`Double.equals` giống `==`.” | `equals` phân biệt signed zero nhưng coi NaN bằng nhau | Chọn API theo nghĩa cần dùng |
| “Vô cực chỉ là số hữu hạn rất lớn.” | Vô cực là giá trị đặc biệt | `Double.isInfinite` và `Double.isFinite` |
| “`Double.MAX_VALUE` là infinity.” | Đây là số hữu hạn dương lớn nhất | Dùng `Double.POSITIVE_INFINITY` khi thực sự cần vô cực |
| “Cast NaN sang int phải ném lỗi.” | Cast cho kết quả 0 | Kiểm tra tính hữu hạn và miền trước cast |
| “JSON nào cũng lưu NaN/Infinity như number.” | JSON chuẩn không cho các literal đó | Thiết kế schema/serializer có xác thực |
| “`Double.MIN_VALUE` là số âm nhỏ nhất.” | Nó là số dương khác 0 nhỏ nhất | Phân biệt với `-Double.MAX_VALUE` hoặc `Double.NEGATIVE_INFINITY` |
| “Mọi zero có dấu có thể tự do gộp lại.” | Một số phép toán số học cần giữ dấu zero | Chuẩn hóa chỉ khi nghiệp vụ cho phép |

Các bộ test nên bao gồm `+0.0`, `-0.0`, `Double.MIN_VALUE`, `-Double.MIN_VALUE`, `Double.MAX_VALUE`, cả hai vô cực, NaN và các giá trị hữu hạn âm/dương. Khi thử API so sánh, hãy kiểm chứng cả `==`, `Double.compare` và `Double.equals` vì kết quả không giống nhau ở zero có dấu và NaN.

## 13. Bài tập vận dụng

**Bài 1 – Dự đoán kết quả.** Không chạy Java, tính `1.0 / +0.0`, `1.0 / -0.0`, `0.0 / 0.0`, `Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY`. Phép nào ném exception, phép nào trả giá trị đặc biệt?

**Bài 2 – So sánh.** Cho `a = +0.0`, `b = -0.0`, `c = Double.NaN`. Lập bảng cho `a == b`, `Double.compare(a,b)`, `Double.valueOf(a).equals(Double.valueOf(b))`, `c == c`, `Double.isNaN(c)`. Giải thích mục đích của từng phép.

**Bài 3 – Validation.** Viết phương thức nhận chuỗi nhiệt độ và chỉ cho phép các giá trị hữu hạn trong `[-50,150]`. Thử `"25.5"`, `"NaN"`, `"Infinity"`, `"-Infinity"`, `"abc"`, `"-0.0"`. Chỉ rõ quy tắc ngoại lệ của parser và chính sách riêng với zero âm.

**Bài 4 – Bucket và key.** Một ứng dụng dùng `HashSet<Double>` để loại trùng kết quả đo. Dự đoán có bao nhiêu phần tử khi thêm `+0.0`, `-0.0`, `Double.NaN` hai lần. Vì sao `HashSet` không áp dụng trực tiếp `==` của primitive?

**Bài 5 – Dòng tính toán.** Phân tích đầu vào khiến một phép tính trả vô cực rồi dẫn tới NaN ở bước sau. Thiết kế cách quan sát và báo lỗi để người dùng không nhìn thấy NaN như một kết quả hợp lệ.

**Bài 6 – Underflow.** Tính `-Double.MIN_VALUE / 2.0`. Vì sao kết quả in ra là `-0.0` chứ không phải một số âm khác 0? Phép `1.0 / result` sẽ có giá trị gì?

**Bài 7 – JSON.** Đề xuất cấu trúc phản hồi API cho phép có giá trị đo hữu hạn hoặc trạng thái không tính được mà vẫn hợp lệ JSON chuẩn. Vì sao mã hóa trực tiếp number `NaN` không phải một hợp đồng an toàn?

## 14. Checklist dùng số thực an toàn

- Hiểu `float`/`double` có **hai zero có dấu, hai vô cực và NaN**, khác với kiểu nguyên.
- Nếu miền dữ liệu yêu cầu số hữu hạn, kiểm tra **`Float.isFinite`/`Double.isFinite`** trước phép tính quan trọng, trước khi cast và trước khi serialize.
- Dùng **`isNaN`** để phát hiện NaN; không dùng `== Double.NaN`.
- Phân biệt `==`, `Double.compare` và `Double.equals` đối với signed zero và NaN.
- Không mặc định mọi phép chia cho 0 đều ném exception; phụ thuộc vào **kiểu toán hạng**.
- Không lạm dụng cast `double → int/long` làm validation: NaN có thể thành 0, vô cực bị chặn về biên.
- Nếu cần bảo toàn dấu zero, không tự chuẩn hóa; nếu cần gộp hai zero trong khóa dữ liệu, hãy chuẩn hóa có chủ ý.
- Kiểm tra serializer/API vì **JSON chuẩn không cho NaN và Infinity dưới dạng number**.
- Với tiền và số thập phân cần chính xác, chọn kiểu và chính sách làm tròn theo nghiệp vụ, không coi NaN/vô cực như những giá trị `BigDecimal` thông thường.

**Kết luận:** `+0.0`, `-0.0`, vô cực và NaN là những **giá trị có hành vi được định nghĩa** trong dấu phẩy động Java, không phải tất cả đều là exception. Tính đúng đắn phụ thuộc vào việc hiểu quy tắc tính toán, lựa chọn phép so sánh phù hợp và xác thực rõ những giá trị được phép đi qua hệ thống.
