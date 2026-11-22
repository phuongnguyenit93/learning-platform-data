# Tác động của signed zero tới phép chia và hàm toán học trong Java

## 1. Mục tiêu và câu hỏi mở đầu

Java có hai giá trị dấu phẩy động biểu diễn **số không**: `+0.0` (positive zero) và `-0.0` (negative zero). Hai giá trị này **so sánh bằng nhau với toán tử `==`**, nhưng **không thể thay thế nhau trong mọi phép tính**. Dấu của số không có thể quyết định dấu của vô cực khi chia, dấu của kết quả một số hàm toán học, cách sắp xếp bằng `Double.compare` và dữ liệu thô khi tuần tự hóa.

Hãy nhìn hai câu lệnh:

```java
System.out.println(+0.0 == -0.0); // true
System.out.println(1.0 / -0.0);    // -Infinity
```

Không có mâu thuẫn: phép `==` trên primitive so sánh theo quy tắc số học floating point; phép chia xét cả dấu của hai toán hạng. Đây là một chủ đề quan trọng trong **Java Core — Numbers / Phép toán dấu phẩy động**.

Sau bài này, bạn sẽ:

1. Hiểu mẫu bit của `+0.0` và `-0.0` trong `float`/`double`.
2. Dự đoán kết quả `/` khi mẫu số hoặc tử số là signed zero; phân biệt `Infinity`, `-Infinity` và `NaN`.
3. Phân tích tác động của dấu zero đối với `Math.abs`, `Math.signum`, `Math.copySign`, `Math.min`, `Math.max`, `Math.sqrt`, `Math.ceil`, `Math.floor`, `Math.rint`, `Math.atan2` và `Math.pow`.
4. Phân biệt so sánh primitive `==` với `Double.compare`/`Double.equals` và những ảnh hưởng lên collection.
5. Đọc đúng raw bits, kiểm tra sign của zero, bảo toàn dấu khi thật sự cần; không nhầm với epsilon hoặc chuyển kiểu số nguyên.

Các ví dụ **chạy với Java 17+** và không cần thư viện bên ngoài JDK.

## 2. Hai số không trong IEEE 754 binary32/binary64

Kiểu `float` của Java dùng khuôn dạng **binary32** gồm 1 bit dấu, 8 bit mũ và 23 bit fraction. Kiểu `double` dùng **binary64** gồm 1 bit dấu, 11 bit mũ và 52 bit fraction.

Số không ở cả hai khuôn dạng có trường **exponent toàn 0 và fraction toàn 0**; trường sign quyết định đó là `+0.0` hay `-0.0`.

| Giá trị | Kiểu | Mẫu bit hệ hex |
| --- | --- | --- |
| `+0.0f` | `float` | `0x00000000` |
| `-0.0f` | `float` | `0x80000000` |
| `+0.0` | `double` | `0x0000000000000000` |
| `-0.0` | `double` | `0x8000000000000000` |

Giá trị toán học “độ lớn bằng 0” được chia thành hai mẫu bit để giúp phép toán dấu phẩy động lưu lại thông tin dấu hữu ích, nhất là khi một kết quả rất nhỏ **underflow** về zero hoặc khi chia cho zero.

Trong Java, `-0.0` là một biểu thức dùng toán tử âm một ngôi tác động lên literal `0.0`; kết quả là zero âm. `Double.toString(-0.0)` in `-0.0`, còn `Double.toString(+0.0)` in `0.0`. Điều này cho thấy cách in mặc định bảo toàn dấu, dù `==` coi hai giá trị bằng nhau.

### 2.1. Tự kiểm tra các bit

```java
double plus = +0.0;
double minus = -0.0;

System.out.printf("%016X%n", Double.doubleToRawLongBits(plus));
System.out.printf("%016X%n", Double.doubleToRawLongBits(minus));
```

Stdout:

```text
0000000000000000
8000000000000000
```

Đây là **mảnh mã** cần đặt trong một phương thức Java trước khi chạy. `Double.doubleToRawLongBits` trả mẫu 64 bit, khác hoàn toàn cast `(long) minus` — cast số thực sang số nguyên cho `0L`, không cho “raw signed-zero bits”.

Có API tương ứng cho `float`: `Float.floatToRawIntBits`. Nếu đang kiểm tra NaN, cần biết phương thức raw có hợp đồng khác các phương thức `doubleToLongBits`/`floatToIntBits` vốn chuẩn hóa nhiều mẫu NaN. Với **zero**, cả raw và non-raw đều cho mẫu dấu đúng.

## 3. `==` coi +0.0 và -0.0 bằng nhau, nhưng bit khác nhau

```java
double positive = +0.0;
double negative = -0.0;

System.out.println(positive == negative); // true
System.out.println(positive != negative); // false
System.out.println(positive < negative);  // false
System.out.println(positive > negative);  // false
```

Các toán tử so sánh primitive không xếp `-0.0` nhỏ hơn `+0.0`. Tuy nhiên, có ít nhất ba cách hỏi **khác nhau** về số zero:

| Câu hỏi | Biểu thức | Với `-0.0` so với `+0.0` |
| --- | --- | --- |
| Hai giá trị có bằng theo phép `==` số học không? | `a == b` | `true` |
| Hai mã bit IEEE 754 có giống hệt không? | `Double.doubleToRawLongBits(a) == Double.doubleToRawLongBits(b)` | `false` |
| Trong thứ tự đầy đủ dành cho wrapper, số nào nhỏ hơn? | `Double.compare(a, b)` | `-0.0` đứng trước `+0.0` |

**Hệ quả:** nếu ứng dụng chỉ hỏi “giá trị có bằng zero về số học không?”, dùng `value == 0.0` là hợp lý và khớp cho cả hai dấu. Nếu ứng dụng muốn **phân biệt dấu zero**, phép `==` không đủ. Ngược lại, nếu mọi zero phải được coi tương đương ở mức nghiệp vụ, dùng một comparator phân biệt hai dấu có thể không phù hợp.

## 4. Phép chia với zero: dấu của kết quả không thể bỏ qua

Quy tắc dấu của phép chia dấu phẩy động: **cùng dấu thì kết quả dương, khác dấu thì kết quả âm**, ngoại trừ các trường hợp cho NaN. Quy tắc này áp dụng cho zero và infinity theo đặc tả IEEE 754 của Java.

### 4.1. Một số hữu hạn khác 0 chia cho ±0.0

| Biểu thức | Kết quả |
| --- | --- |
| `1.0 / +0.0` | `Infinity` |
| `1.0 / -0.0` | `-Infinity` |
| `-1.0 / +0.0` | `-Infinity` |
| `-1.0 / -0.0` | `Infinity` |

Dù `+0.0 == -0.0` là `true`, **không được** từ đó suy ra `1.0 / +0.0 == 1.0 / -0.0`. Hai vế tương ứng là dương vô cực và âm vô cực.

```java
System.out.println(1.0 / +0.0);
System.out.println(1.0 / -0.0);
System.out.println(-1.0 / +0.0);
System.out.println(-1.0 / -0.0);
```

Stdout:

```text
Infinity
-Infinity
-Infinity
Infinity
```

Đó là **quy tắc cho kiểu `double`**, không phải “chia nguyên”. Nếu cả hai toán hạng là `int`/`long`, chia cho số `0` ném `ArithmeticException` ở runtime khi phép chia được thực hiện.

### 4.2. Zero làm tử số, mẫu số hữu hạn khác 0

| Biểu thức | Kết quả |
| --- | --- |
| `+0.0 / 2.0` | `0.0` |
| `-0.0 / 2.0` | `-0.0` |
| `+0.0 / -2.0` | `-0.0` |
| `-0.0 / -2.0` | `0.0` |

Kết quả vẫn bằng zero về giá trị số học, nhưng **dấu của zero** tuân theo dấu phép chia. Nếu đưa kết quả đó vào một phép chia tiếp theo, dấu có thể thay đổi vô cực:

```java
double tinyResult = +0.0 / -2.0; // -0.0
double reciprocal = 1.0 / tinyResult; // -Infinity
```

Đây là ví dụ cho thấy việc âm thầm thay mọi giá trị zero bằng `+0.0` có thể làm thay đổi hành vi về sau.

### 4.3. Zero chia zero và vô cực

Các quy tắc biên khác cần nhớ:

- `+0.0 / +0.0`, `+0.0 / -0.0`, `-0.0 / +0.0` và `-0.0 / -0.0` đều cho **`NaN`**.
- Số hữu hạn chia cho `+Infinity` hoặc `-Infinity` tạo **signed zero**, dấu theo hai toán hạng nếu không có NaN.
- `Infinity / Infinity` và `-Infinity / Infinity` cho `NaN`.
- Nếu một toán hạng là `NaN`, kết quả phép chia là `NaN`.

Ví dụ:

```java
System.out.println(0.0 / -0.0);                 // NaN
System.out.println(3.0 / Double.NEGATIVE_INFINITY); // -0.0
System.out.println(Double.isNaN(0.0 / 0.0));     // true
```

Dùng `Double.isNaN(result)` hoặc `Double.isInfinite(result)` khi cần **kiểm tra trạng thái**; không kiểm tra NaN bằng `result == Double.NaN` vì NaN không bằng chính nó theo primitive `==`.

### 4.4. Phân biệt `1 / 0` với `1.0 / 0.0`

`1 / 0` là phép chia nguyên cho zero (một biểu thức hằng như vậy có thể là lỗi biên dịch trong các ngữ cảnh constant expression; phép chia nguyên cho zero thực thi tại runtime ném `ArithmeticException`). `1.0 / 0.0` là phép chia dấu phẩy động trả `Infinity`.

Các phép chia dấu phẩy động theo JLS không ném runtime exception chỉ vì chia cho zero, overflow, underflow hay mất thông tin. Tuy nhiên, chương trình **vẫn phải tự quyết định** có chấp nhận `Infinity` hoặc `NaN` làm kết quả nghiệp vụ hay không.

## 5. Số zero sinh ra qua cộng, trừ và nhân

Signed zero không chỉ đến từ literal `-0.0`. Phép nhân một số không với số âm có thể đổi dấu:

```java
System.out.println(-0.0 * 2.0);  // -0.0
System.out.println(-0.0 * -2.0); // 0.0
System.out.println(0.0 * -2.0);  // -0.0
```

Cộng trừ có các quy tắc dấu zero riêng. Ví dụ theo chế độ làm tròn mặc định Java:

```java
System.out.println(-0.0 + +0.0); // 0.0
System.out.println(-0.0 + -0.0); // -0.0
```

Điều này dẫn đến một cảnh báo quan trọng: một phép biến đổi biểu thức mà ta thường cho là hiển nhiên trong **đại số số thực** có thể không bảo toàn **mọi bit kết quả floating-point**. Chẳng hạn thêm `+0.0` vào một biểu thức có thể đổi `-0.0` thành `+0.0`.

**Không suy ra phép cộng số thực luôn kết hợp**: làm tròn, overflow, underflow và signed zero đều có thể tạo khác biệt giữa những biểu thức được nhóm khác nhau. Khi yêu cầu kết quả bit chính xác (reproducible), cần kiểm tra các biểu thức được tối ưu hay biến đổi và tuân thủ ngữ nghĩa Java/JLS.

## 6. `Math.abs`, `Math.signum` và `Math.copySign`

Ba phương thức rất dễ bị nhầm vì tên đều liên quan đến dấu:

| Biểu thức `double` | Kết quả | Ý nghĩa |
| --- | --- | --- |
| `Math.abs(-0.0)` | `0.0` | Trả độ lớn không âm, bỏ dấu âm |
| `Math.signum(-0.0)` | `-0.0` | Giữ signed zero |
| `Math.signum(+0.0)` | `0.0` | Giữ signed zero |
| `Math.copySign(2.5, -0.0)` | `-2.5` | Dùng độ lớn toán hạng đầu, dấu toán hạng thứ hai |
| `Math.copySign(0.0, -1.0)` | `-0.0` | Có thể tạo zero âm |
| `Math.copySign(-0.0, 1.0)` | `0.0` | Có thể tạo zero dương |

### 6.1. `Math.abs`: loại bỏ dấu zero âm

`Math.abs(-0.0)` là `+0.0`. Nếu bạn muốn **chuẩn hóa** mọi zero thành dương để hiển thị hoặc áp dụng quy ước nghiệp vụ, đây là một cách; nhưng nó cũng biến số âm hữu hạn thành dương nên không phù hợp khi phải **chỉ thay đổi zero**.

Nếu chỉ muốn chuẩn hóa hai loại zero:

```java
static double normalizeZero(double value) {
    return value == 0.0 ? 0.0 : value;
}
```

Đây là **mảnh phương thức**, không phải file Java độc lập. Nó giữ các giá trị khác zero, kể cả `NaN` và infinity, nhưng biến `-0.0` thành `+0.0`. Chỉ áp dụng khi **đúng yêu cầu**: chuẩn hóa zero có thể làm đổi dấu của kết quả chia về sau.

### 6.2. `Math.signum`: không làm mất dấu của zero

`Math.signum(-0.0)` trả `-0.0`, không phải `0.0` hay số nguyên `-1`. `Math.signum(+0.0)` trả `+0.0`. Với số hữu hạn khác zero, `signum` trả ±1.0; với NaN, trả NaN.

Nếu bạn đang tìm “giá trị dấu là -1, 0, +1” theo số học nhưng phải phân biệt zero âm, `signum` vẫn trả **floating-point signed zero**. Muốn mã `int` riêng cho zero âm, cần thiết kế quy ước tường minh và kiểm tra raw bits.

### 6.3. `Math.copySign`: sao chép bit dấu một cách có chủ đích

`Math.copySign(magnitude, sign)` dùng **độ lớn của đối số thứ nhất** và **dấu của đối số thứ hai**. Với đầu vào là zero, nó có thể bảo toàn/tạo zero âm. Ví dụ:

```java
double negativeMagnitude = Math.copySign(5.0, -0.0); // -5.0
double negativeZero = Math.copySign(0.0, -3.0);       // -0.0
```

`Math.copySign` không giống `Math.signum`. Với NaN, chi tiết của bit dấu có thể phụ thuộc API/hợp đồng từng phương thức, vì vậy hãy đọc tài liệu `Math`/`StrictMath` của phiên bản đích nếu có yêu cầu xử lý NaN payload/sign cụ thể.

## 7. `Math.min` và `Math.max` phân biệt signed zero

Đây là trường hợp dễ gây bất ngờ: mặc dù `-0.0 == +0.0` là `true`, `Math.min` và `Math.max` trên `double`/`float` **xét zero âm nhỏ hơn zero dương**.

```java
System.out.println(Math.min(-0.0, +0.0)); // -0.0
System.out.println(Math.max(-0.0, +0.0)); // 0.0
```

Dù đổi thứ tự hai đối số, cùng cặp ±0 sẽ vẫn cho `-0.0` với `min` và `+0.0` với `max`. Các overload `int`/`long` không có khái niệm signed zero riêng.

| Phương thức | Với -0.0 và +0.0 | Với một đối số NaN |
| --- | --- | --- |
| `Math.min` (`double`/`float`) | Trả `-0.0` | Trả NaN |
| `Math.max` (`double`/`float`) | Trả `+0.0` | Trả NaN |

Do đó, nếu một thuật toán gom giá trị nhỏ nhất/lớn nhất qua nhiều bước, hãy nghĩ đến **dấu zero trong dữ liệu**, đặc biệt khi sau đó tính nghịch đảo hoặc xuất raw bits.

**Không thay `Math.min(a,b)` một cách máy móc bằng `a < b ? a : b`** khi cần giữ đầy đủ hợp đồng IEEE 754, vì phép so sánh primitive không phân biệt signed zero và có quy tắc khác với NaN. Cũng không nên giả định mọi phép viết min/max tùy biến tương đương API chuẩn.

## 8. `Math.sqrt`, `Math.ceil`, `Math.floor`, `Math.rint` và signed zero

Các phương thức làm việc với số thực có thể nhận/trả zero âm:

| Biểu thức | Kết quả |
| --- | --- |
| `Math.sqrt(-0.0)` | `-0.0` |
| `Math.cbrt(-0.0)` | `-0.0` |
| `Math.ceil(-0.5)` | `-0.0` |
| `Math.floor(-0.0)` | `-0.0` |
| `Math.rint(-0.4)` | `-0.0` |
| `Math.abs(-0.0)` | `+0.0` |

### 8.1. Căn bậc hai của zero âm

`Math.sqrt(-0.0)` trả **`-0.0`**, dù người học đôi khi cho rằng căn bậc hai không thể là số âm. Kết quả zero âm được giữ theo hợp đồng floating point của phương thức, không phải “căn bậc hai của một số âm hữu hạn”.

Phân biệt rõ:

- `Math.sqrt(-0.0)` → `-0.0`.
- `Math.sqrt(-1.0)` → `NaN`.

Cả `+0.0` và `-0.0` đều là zero theo `==`, nhưng phương thức sqrt có thể phân biệt tại mức bit đầu ra.

### 8.2. Làm tròn gần zero từ phía âm

`Math.ceil(-0.5)` trả `-0.0`: trần toán học của `-0.5` là zero, nhưng dấu kết quả là âm theo hợp đồng `ceil`. `Math.rint(-0.4)` cũng có thể trả `-0.0` khi làm tròn về số nguyên gần nhất được biểu diễn ở kiểu `double`.

`Math.floor(-0.0)` bảo toàn `-0.0`. Khi áp dụng `Math.floor(-0.5)` thì kết quả lại là `-1.0`; không đánh đồng `floor` và `ceil`.

**Bẫy chuyển kiểu:** nếu cast `(int) Math.ceil(-0.5)`, giá trị cuối trở thành `0` kiểu `int` và không còn bit dấu zero. Khi cần lưu nguyên bản biểu diễn số thực, không nên chuyển qua kiểu nguyên.

### 8.3. Một số hàm luôn không âm vẫn có thể làm mất dấu

`Math.abs` cố ý trả độ lớn. Các phương thức như `Math.hypot` mô tả độ dài không âm cũng không thích hợp để giữ dấu zero từ một trục đầu vào. Hãy đọc hợp đồng **từng hàm**, không suy từ tên gọi chung “hàm toán học”.

## 9. `Math.atan2`: dấu zero quyết định góc ở đường biên

`Math.atan2(y, x)` trả góc tính bằng radian khi xử lý cặp tọa độ, và có các quy tắc đặc biệt đối với zero có dấu. Trong đó:

- `Math.atan2(+0.0, -1.0)` = `+π`.
- `Math.atan2(-0.0, -1.0)` = `-π`.

Ví dụ:

```java
System.out.println(Math.atan2(+0.0, -1.0));
System.out.println(Math.atan2(-0.0, -1.0));
```

Stdout:

```text
3.141592653589793
-3.141592653589793
```

Điều này có ích khi làm hình học, đồ họa, biểu diễn hướng, miền góc từ `-π` đến `+π`. Cùng tọa độ có `y` **bằng zero theo `==`**, nhưng dấu zero giúp `atan2` lựa chọn **phía của nhánh góc (branch cut)**.

Đừng tự thay `atan2(y,x)` bằng `atan(y/x)` khi cần xử lý góc đầy đủ: cách đó mất thông tin về góc phần tư, có thể sinh vô cực/NaN tại `x = 0`, và không tương đương tại nhiều trường hợp đặc biệt.

### 9.1. Các tình huống tọa độ thường gặp

Với `x > 0`:

- `Math.atan2(+0.0, x)` trả `+0.0`.
- `Math.atan2(-0.0, x)` trả `-0.0`.

Với `x < 0`:

- `Math.atan2(+0.0, x)` trả `+π`.
- `Math.atan2(-0.0, x)` trả `-π`.

Các phép lượng giác khác có hợp đồng riêng (ví dụ `Math.sin(-0.0)` trả `-0.0`), nhưng không nên suy rằng **mọi** hàm đều bảo toàn dấu zero: cần xem Java SE `Math` hoặc `StrictMath` của bản JDK đang hỗ trợ.

## 10. `Math.pow` và dấu zero theo số mũ

Một số trường hợp của `Math.pow` phụ thuộc dấu zero và số mũ, đặc biệt với **số mũ nguyên lẻ hay chẵn**:

| Biểu thức | Kết quả |
| --- | --- |
| `Math.pow(-0.0, 3.0)` | `-0.0` |
| `Math.pow(-0.0, 2.0)` | `+0.0` |
| `Math.pow(-0.0, -3.0)` | `-Infinity` |
| `Math.pow(-0.0, -2.0)` | `Infinity` |

Diễn giải: dấu âm của cơ số zero được giữ với lũy thừa nguyên lẻ (khi kết quả còn zero hoặc vô cực); với số mũ nguyên chẵn kết quả có dấu dương. Điều này giống trực giác quy tắc dấu của phép nhân/chia, nhưng `Math.pow` có nhiều nhánh đặc biệt cho NaN, infinity và các số mũ không nguyên.

Khi cần bảo đảm hành vi tại ranh giới, hãy kiểm tra **giá trị cụ thể và contract**. Không thay `Math.pow` bằng phép nhân thủ công hoặc ngược lại rồi mặc nhiên khẳng định toàn bộ trường hợp biên giữ nguyên mẫu bit.

## 11. `Math.nextUp` và `Math.nextDown` đi qua vùng zero

`Math.nextUp(x)` trả giá trị floating-point **biểu diễn được kế tiếp theo hướng +∞**; `Math.nextDown(x)` trả giá trị kế tiếp theo hướng −∞.

Tại zero:

```java
System.out.println(Math.nextUp(-0.0) == Double.MIN_VALUE);
System.out.println(Math.nextDown(+0.0) == -Double.MIN_VALUE);
```

Stdout:

```text
true
true
```

`Double.MIN_VALUE` là số **dương khác zero nhỏ nhất** của binary64 (subnormal), chứ không phải số âm hữu hạn nhỏ nhất. Hai phép nextUp/nextDown phản ánh thứ tự số biểu diễn được **theo giá trị**: `+0.0` và `-0.0` so sánh bằng số học, nhưng có hai bit patterns riêng.

Đừng nhầm kết quả khi áp dụng nextUp/nextDown với quan hệ `Double.compare` trên các zero; các API này có mục tiêu khác nhau. Nếu muốn so sánh raw bits của hai zero, dùng API bit chứ không đi vòng qua `nextUp`.

## 12. `Double.compare` và `Double.equals` khác `==`

So sánh primitive `==`:

```java
System.out.println(-0.0 == +0.0); // true
```

So sánh theo **thứ tự đầy đủ** của wrapper:

```java
System.out.println(Double.compare(-0.0, +0.0)); // -1
System.out.println(Double.valueOf(-0.0)
        .equals(Double.valueOf(+0.0))); // false
```

`Double.compare` đặt `-0.0` thấp hơn `+0.0`. `Double.equals` dựa trên biểu diễn bit đã canonicalize NaN, nên coi ±0 là **không bằng nhau**. Điều này giúp `Double` có quan hệ bằng/so sánh tương thích với cách dùng trong `HashSet`, `HashMap`, `TreeSet`.

Tương tự, `Float.compare(-0.0f, +0.0f)` trả số âm và `Float.valueOf(-0.0f).equals(Float.valueOf(+0.0f))` là false.

### 12.1. Ảnh hưởng đến collections

```java
java.util.Set<Double> zeros = new java.util.HashSet<>();
zeros.add(+0.0);
zeros.add(-0.0);
System.out.println(zeros.size()); // 2
```

Đây là **mảnh mã**, đặt trong phương thức nếu muốn chạy. Khi thêm vào `HashSet<Double>`, auto-boxing tạo hai giá trị `Double` có ý nghĩa khác nhau theo `equals`. Vì thế tập hợp có **2 phần tử**, dù primitive `+0.0 == -0.0` là true.

Nếu yêu cầu nghiệp vụ gộp hai zero thành một khóa, phải **chuẩn hóa có chủ đích** trước khi đưa vào map/set. Ví dụ:

```java
double value = -0.0;
double normalized = value == 0.0 ? 0.0 : value;
```

Tuy nhiên, nếu giá trị được dùng để tính nghịch đảo, phân tích hình học hoặc giữ raw IEEE bits, việc chuẩn hóa có thể làm mất thông tin cần thiết. **Quyết định lưu hay gộp signed zero phải theo yêu cầu**, không áp dụng máy móc cho mọi hệ thống.

### 12.2. Vì sao so sánh NaN cũng khác?

`Double.compare` còn quy định một thứ tự cho NaN, trong khi phép `==` với NaN luôn false. `Double.equals` coi các NaN đã canonicalize là tương đương. Đây là lý do cần biết bạn đang dùng **phép so sánh toán học primitive**, **thứ tự dành cho collection** hay **kiểm tra mẫu bit**.

## 13. Chương trình Java hoàn chỉnh A: chia cho signed zero

Lưu thành **`SignedZeroDivision.java`**:

```java
public class SignedZeroDivision {
    public static void main(String[] args) {
        double positive = +0.0;
        double negative = -0.0;

        System.out.println(positive == negative);

        System.out.println(1.0 / positive);
        System.out.println(1.0 / negative);
        System.out.println(-1.0 / positive);
        System.out.println(-1.0 / negative);

        System.out.println(negative / 2.0);
        System.out.println(positive / -2.0);
        System.out.println(negative / -2.0);

        System.out.println(positive / negative);
        System.out.println(3.0 / Double.NEGATIVE_INFINITY);
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac --release 17 SignedZeroDivision.java
java SignedZeroDivision
```

**Stdout chính xác:**

```text
true
Infinity
-Infinity
-Infinity
Infinity
-0.0
-0.0
0.0
NaN
-0.0
```

Giải thích từng nhóm:

1. Dòng `true` chỉ nói hai zero bằng theo phép so sánh primitive.
2. Bốn dòng vô cực thể hiện quy tắc **cùng dấu/dị dấu**.
3. Ba dòng kết quả zero thể hiện dấu của thương.
4. `0.0 / -0.0` cho NaN, không có dấu số hữu hạn.
5. `3.0 / -Infinity` cho zero âm theo quy tắc dấu.

Không gán `-Infinity` vào một phép tính nghiệp vụ mà không kiểm tra, vì nó có thể làm thuật toán lan truyền infinity/NaN ở các bước sau.

## 14. Chương trình Java hoàn chỉnh B: signed zero trong Math

Lưu thành **`SignedZeroMath.java`**:

```java
public class SignedZeroMath {
    public static void main(String[] args) {
        System.out.println(Math.min(-0.0, +0.0));
        System.out.println(Math.max(-0.0, +0.0));
        System.out.println(Math.abs(-0.0));
        System.out.println(Math.signum(-0.0));

        System.out.println(Math.copySign(2.5, -0.0));
        System.out.println(Math.copySign(0.0, -1.0));

        System.out.println(Math.sqrt(-0.0));
        System.out.println(Math.ceil(-0.5));
        System.out.println(Math.floor(-0.0));
        System.out.println(Math.rint(-0.4));

        System.out.println(Math.atan2(+0.0, -1.0));
        System.out.println(Math.atan2(-0.0, -1.0));

        System.out.println(Math.pow(-0.0, 3.0));
        System.out.println(Math.pow(-0.0, -3.0));
    }
}
```

Chạy:

```bash
javac --release 17 SignedZeroMath.java
java SignedZeroMath
```

**Stdout chính xác:**

```text
-0.0
0.0
0.0
-0.0
-2.5
-0.0
-0.0
-0.0
-0.0
-0.0
3.141592653589793
-3.141592653589793
-0.0
-Infinity
```

Những trường hợp này đã được chọn vì dấu zero **được quy định bởi hợp đồng API**. Các phương thức khác của `Math` có thể có quy tắc riêng về signed zero, NaN và infinity; luôn tham khảo tài liệu theo đúng phiên bản JDK mà dự án hỗ trợ.

## 15. Chương trình Java hoàn chỉnh C: bit, equality và ordering

Lưu thành **`SignedZeroIdentity.java`**:

```java
import java.util.HashSet;
import java.util.Set;

public class SignedZeroIdentity {
    public static void main(String[] args) {
        double positive = +0.0;
        double negative = -0.0;

        System.out.printf("%016X%n", Double.doubleToRawLongBits(positive));
        System.out.printf("%016X%n", Double.doubleToRawLongBits(negative));

        System.out.println(positive == negative);
        System.out.println(Double.compare(negative, positive));
        System.out.println(Double.valueOf(negative)
                .equals(Double.valueOf(positive)));

        Set<Double> values = new HashSet<>();
        values.add(positive);
        values.add(negative);
        System.out.println(values.size());

        System.out.println(Math.nextUp(negative) == Double.MIN_VALUE);
        System.out.println(Math.nextDown(positive) == -Double.MIN_VALUE);
    }
}
```

Chạy:

```bash
javac --release 17 SignedZeroIdentity.java
java SignedZeroIdentity
```

**Stdout chính xác:**

```text
0000000000000000
8000000000000000
true
-1
false
2
true
true
```

Tại đây có ba câu hỏi khác nhau: `==` xác định tương đương theo số học, raw bits xác định **bit identity**, và wrapper/collection xác định **equivalence/ordering** theo hợp đồng của `Double`.

## 16. Kiểm tra và bảo toàn signed zero trong chương trình thực tế

### 16.1. Chỉ cần biết một giá trị có phải zero không

Dùng:

```java
boolean isZero = value == 0.0;
```

Điều này nhận cả zero dương và zero âm; `NaN` không thỏa. Đây là lựa chọn tốt khi dấu zero **không có ý nghĩa nghiệp vụ**.

### 16.2. Cần biết chính xác zero âm

Dùng raw bits hoặc so sánh phần dấu của zero:

```java
static boolean isNegativeZero(double x) {
    return Double.doubleToRawLongBits(x) == 0x8000000000000000L;
}
```

Phương thức trên đúng với **zero âm**, không coi mọi số âm hoặc NaN có bit sign bằng 1 là zero âm. Nó là một **mảnh phương thức** cần đặt trong class.

Cách kiểm tra khác dựa trên phép chia: `x == 0.0 && 1.0 / x == Double.NEGATIVE_INFINITY`. Tuy nhiên, raw-bits thường rõ mục đích hơn, tránh khiến người đọc nghĩ bạn đang thử phép chia với mẫu số không hợp lệ.

### 16.3. Cần bảo toàn dấu khi truyền dữ liệu

- Dùng `Double.doubleToRawLongBits`/`Double.longBitsToDouble` khi hợp đồng yêu cầu bảo toàn bit của giá trị IEEE 754.
- Nếu lưu thành chuỗi thập phân theo `Double.toString`, `-0.0` sẽ xuất hiện rõ như chuỗi `"-0.0"`. Nhưng hệ thống bên ngoài có thể chuẩn hóa nó khi parse hoặc mapping.
- Khi đi qua kiểu nguyên, định dạng số thập phân cố định, dữ liệu tài chính, cơ sở dữ liệu hay giao thức trao đổi, cần xác minh đầu-cuối liệu dấu zero có được giữ không. **Đừng giả định** mọi định dạng số hỗ trợ signed zero giống IEEE 754.
- Nếu chuẩn hóa về `+0.0` là yêu cầu, thực hiện một lần ở ranh giới hệ thống và ghi rõ quy ước.

### 16.4. Các kiểm thử boundary nên có

| Mục tiêu | Trường hợp kiểm thử |
| --- | --- |
| Chia | `1.0/+0.0`, `1.0/-0.0`, `-1.0/-0.0` |
| Zero/zero | `0.0/0.0`, `-0.0/+0.0` → NaN |
| Zero từ phép khác | `-0.0*2.0`, `-0.0+-0.0`, `-0.0++0.0` |
| Hàm toán học | `Math.min/max` của ±0, `abs`, `signum`, `copySign` |
| Rounding | `Math.ceil(-0.5)`, `Math.rint(-0.4)` |
| Góc | `Math.atan2(±0.0,-1.0)` |
| Bit identity | `doubleToRawLongBits(±0.0)` |
| Collection | Hai `Double` ±0 làm khóa |
| Giá trị đặc biệt | `NaN`, `Infinity`, `Double.MIN_VALUE` |

**Gợi ý:** đừng chỉ so sánh số qua `==` trong unit test cần phân biệt zero âm/dương; hãy đối chiếu raw bits hoặc phép toán phụ thuộc dấu. Với comparator/collections, kiểm tra đúng hợp đồng `equals` và `compareTo`.

## 17. Những ngộ nhận thường gặp

1. **“`+0.0 == -0.0` nên chúng thay thế nhau được.”** Sai. Chia lấy nghịch đảo và một số hàm toán học phân biệt dấu.
2. **“Chia cho zero floating point luôn ném exception.”** Sai; thường trả ±Infinity hoặc NaN. `int`/`long` chia 0 mới ném `ArithmeticException` khi chạy.
3. **“`Math.abs(-0.0)` bảo toàn dấu.”** Sai; trả +0.0.
4. **“`Math.signum(-0.0)` trả -1.0.”** Sai; trả -0.0.
5. **“`Math.min(+0.0,-0.0)` tùy ý trả bất kỳ zero nào.”** Sai; overload số thực quy định kết quả là -0.0.
6. **“`Math.atan2(0.0,-1.0)` không cần biết dấu 0.”** Sai; +0 cho +π, -0 cho -π.
7. **“`Double.equals` dùng chính xác cùng quy tắc `==` primitive.”** Sai; wrapper phân biệt hai zero và xử lý NaN theo hợp đồng riêng.
8. **“`HashSet<Double>` chắc chắn gộp ±0.”** Sai; mặc định có thể lưu cả hai vì `equals` khác nhau.
9. **“Ép `(long) -0.0` giữ bit dấu.”** Sai; cast numeric cho số nguyên 0, mất signed-zero bit.
10. **“`Double.MIN_VALUE` là số âm nhỏ nhất.”** Sai; đó là subnormal dương khác 0 nhỏ nhất.
11. **“Đầu ra `-0.0` là lỗi in số.”** Không; `Double.toString` giữ dấu để thể hiện khác biệt IEEE 754.
12. **“Có thể chuẩn hóa mọi -0.0 thành +0.0 mà không ảnh hưởng chương trình.”** Sai nếu dấu zero có tác động đến các phép tính sau.
13. **“Mọi hàm toán học xử lý signed zero giống nhau.”** Sai; phải tra contract của từng hàm.
14. **“NaN có thể kiểm tra bằng `== Double.NaN`.”** Sai; hãy dùng `Double.isNaN`.

## 18. Bài tập kèm đáp án

### Bài 1 — Hai giá trị bằng nhau nhưng hai kết quả khác dấu

Với `double a=+0.0, b=-0.0;`, hãy tính `a == b`, `1.0 / a` và `1.0 / b`.

**Đáp án:** `true`, `Infinity`, `-Infinity`. `==` không so sánh bit dấu của zero theo nghĩa số học, còn phép chia có quy tắc dấu.

### Bài 2 — Cùng dấu và khác dấu

Tính `-2.0 / +0.0` và `-2.0 / -0.0`.

**Đáp án:** `-Infinity` và `Infinity`. Phép chia hai toán hạng cùng dấu cho dương, khác dấu cho âm.

### Bài 3 — Zero chia zero

`-0.0 / -0.0` cho zero âm, zero dương hay NaN?

**Đáp án:** `NaN`. Zero chia zero không có thương số hữu hạn hoặc vô cực xác định.

### Bài 4 — Ba hàm xử lý dấu

Dự đoán `Math.abs(-0.0)`, `Math.signum(-0.0)` và `Math.copySign(2.5,-0.0)`.

**Đáp án:** `0.0`, `-0.0` và `-2.5`. `abs` bỏ dấu, `signum` giữ zero âm, `copySign` lấy dấu của đối số thứ hai.

### Bài 5 — Min/max signed zero

`Math.min(-0.0,+0.0)` và `Math.max(-0.0,+0.0)` cho gì?

**Đáp án:** `-0.0` và `0.0` theo hợp đồng `Math`.

### Bài 6 — Góc ranh giới

So sánh `Math.atan2(+0.0,-1.0)` và `Math.atan2(-0.0,-1.0)`.

**Đáp án:** `+π` và `-π`. Dấu của tọa độ y biểu thị phía của nhánh góc.

### Bài 7 — Wrapper và nguyên thủy

Tại sao `-0.0 == +0.0` là true nhưng `Double.valueOf(-0.0).equals(Double.valueOf(+0.0))` là false?

**Đáp án:** `==` primitive tuân theo equality floating point; `Double.equals` dựa trên bit-conversion có phân biệt zero âm/dương.

### Bài 8 — Xác định dấu chính xác

Viết điều kiện chỉ đúng với `double x = -0.0`, không đúng với `+0.0` hoặc `-Double.MIN_VALUE`.

**Đáp án:** `Double.doubleToRawLongBits(x) == 0x8000000000000000L`.

### Bài 9 — Căn bậc hai

Tính `Math.sqrt(-0.0)` và `Math.sqrt(-1.0)`.

**Đáp án:** `-0.0` và `NaN`. Zero âm được bảo toàn; số âm hữu hạn khác zero không có căn bậc hai thực trong kết quả `double`.

### Bài 10 — Làm tròn về zero

`Math.ceil(-0.5)`, `Math.floor(-0.5)` và `Math.rint(-0.4)` trả gì?

**Đáp án:** `-0.0`, `-1.0`, `-0.0`. Dấu zero còn được giữ ở kết quả của `ceil`/`rint`.

### Bài 11 — Kiểm thử collections

Thêm `+0.0` và `-0.0` vào `HashSet<Double>` rồi gọi `size()`. Kết quả bao nhiêu?

**Đáp án:** `2`. `Double.equals` phân biệt zero âm/dương, dù primitive `==` coi chúng bằng nhau.

### Bài 12 — Quyết định chuẩn hóa

Một API chỉ cần kiểm tra “khối lượng có bằng zero không” nên phân biệt ±0 hay không? Một API tính `1.0/x` có thể bỏ dấu zero không?

**Đáp án:** câu đầu thường chỉ cần `x == 0.0`, không phân biệt dấu; câu sau **không thể** bỏ dấu nếu muốn giữ chính xác dấu của infinity và hợp đồng IEEE 754. Quyết định phải dựa trên mục đích dữ liệu.

## 19. Checklist hoàn thành

- [ ] Tôi biết chính xác mẫu bit `+0.0` và `-0.0` của `float`/`double`.
- [ ] Tôi giải thích được vì sao primitive `==` trả true, dù phép chia theo dấu cho hai kết quả vô cực khác nhau.
- [ ] Tôi phân biệt kết quả `±0.0`, `±Infinity` và `NaN` trong phép `/`.
- [ ] Tôi biết `Math.abs` bỏ dấu zero âm, trong khi `Math.signum` bảo toàn nó.
- [ ] Tôi biết `Math.copySign` có thể tạo zero âm và `Math.min/max` chọn dấu zero theo hợp đồng.
- [ ] Tôi hiểu `Math.sqrt`, `Math.ceil`, `Math.floor`, `Math.rint` có thể trả signed zero.
- [ ] Tôi giải thích được `Math.atan2(+0.0,-1.0)` khác `Math.atan2(-0.0,-1.0)`.
- [ ] Tôi phân biệt `Double.compare`/`equals` với `==` khi dùng collection.
- [ ] Tôi dùng raw bits để kiểm tra zero âm chính xác mà không lẫn số âm nhỏ hay NaN.
- [ ] Tôi có lý do rõ ràng trước khi **giữ lại** hoặc **chuẩn hóa** signed zero trong dữ liệu.
- [ ] Tôi đã chạy ba ví dụ Java 17+ và kiểm tra các giá trị ở ranh giới.

**Tài liệu chính thức để đối chiếu:**

- [Java SE 17 — Double API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): signed zero, `compare`, `equals`, `doubleToRawLongBits`, `toString`.
- [Java SE 17 — Float API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html): cấu trúc binary32 và các API raw bits.
- [Java SE 17 — Math API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `abs`, `signum`, `copySign`, `min`, `max`, `sqrt`, `ceil`, `floor`, `rint`, `atan2`, `pow`.
- [JLS 17 `15.17 — Multiplicative Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17): ngữ nghĩa nhân/chia số thực, signed zero và infinity.
- [JLS 17 `15.18 — Additive Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.18): cộng/trừ floating-point.
- [JLS 17 `15.21.1 — Numerical Equality](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.21.1): `==` và NaN/zero.

**Kết luận:** signed zero là **thông tin dấu được lưu trong biểu diễn số thực**, không chỉ là cách in. Khi xây dựng thuật toán Java dùng `double`/`float`, đừng suy từ `+0.0 == -0.0` rằng chúng có thể thay thế nhau trong phép chia hoặc mọi hàm toán học. Muốn kết quả đúng, hãy xác định bạn cần **equality theo giá trị**, **raw bit identity**, hay **quy tắc xử lý dấu** của từng phép toán và API.