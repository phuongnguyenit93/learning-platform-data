# Chọn overload clamp cho số nguyên và số thực

Java 21 bổ sung `Math.clamp()` để giới hạn một giá trị vào khoảng đóng `[min, max]`. Nếu `value` nhỏ hơn `min`, phương thức trả về `min`; nếu lớn hơn `max`, phương thức trả về `max`; nếu nằm trong khoảng, phương thức trả lại giá trị ban đầu.

Điểm cần chú ý khi sử dụng là `Math.clamp()` có bốn overload với kiểu tham số và kiểu trả về khác nhau. Đặc biệt, Java không có overload `(int, int, int)`: ba đối số `int` được xử lý bằng overload `(long, int, int)` và kết quả có kiểu `int`. Với số thực, `float` và `double` có quy tắc riêng cho `NaN` và signed zero.

## 1. Bốn overload của Math.clamp trong Java 21

Các chữ ký được cung cấp trong `java.lang.Math` là:

```java
int    clamp(long value, int min, int max)
long   clamp(long value, long min, long max)
float  clamp(float value, float min, float max)
double clamp(double value, double min, double max)
```

Cả bốn overload đều có từ Java 21. Bảng sau giúp chọn phương thức theo kiểu dữ liệu:

| Overload | Kiểu trả về | Mục đích thường gặp |
|---|---|---|
| `clamp(long, int, int)` | `int` | Giới hạn một giá trị `long` trong khoảng `int`; hữu ích khi chuyển kiểu có bão hòa |
| `clamp(long, long, long)` | `long` | Giới hạn giá trị nguyên 64 bit trong khoảng `long` |
| `clamp(float, float, float)` | `float` | Giữ phép tính và kết quả ở độ chính xác `float` |
| `clamp(double, double, double)` | `double` | Giữ phép tính và kết quả ở độ chính xác `double` |

Không có phương thức `clamp(int, int, int)`, `clamp(int, long, long)` hay overload nhận kết hợp tùy ý giữa `float` và `double`. Java chọn overload dựa trên kiểu tĩnh của các biểu thức tại thời điểm biên dịch, có xét các phép widening primitive conversion hợp lệ.

## 2. Chọn overload cho số nguyên

### Ba đối số int

Khi cả ba đối số là `int`, Java chọn `clamp(long, int, int)`. Đối số đầu tiên được mở rộng từ `int` sang `long`; hai cận vẫn giữ kiểu `int`; kết quả trả về là `int`:

```java
int score = Math.clamp(125, 0, 100);
System.out.println(score); // 100

int temperature = Math.clamp(-8, 0, 50);
System.out.println(temperature); // 0
```

Có thể gán trực tiếp cho biến `int` vì kiểu trả về của overload được chọn là `int`. Không cần ép kiểu kết quả.

### Dùng long với hai cận int để chuyển kiểu có bão hòa

Overload `clamp(long value, int min, int max)` được thiết kế để giá trị đầu vào `long` có thể lớn hơn phạm vi `int`, nhưng kết quả luôn nằm trong hai cận `int`:

```java
long importedValue = 5_000_000_000L;
int safeValue = Math.clamp(importedValue, 0, Integer.MAX_VALUE);

System.out.println(safeValue); // 2147483647
```

Nếu `value` nhỏ hơn `min`, kết quả là `min`; nếu lớn hơn `max`, kết quả là `max`; nếu nằm trong khoảng, giá trị đó chắc chắn biểu diễn được bằng `int`. Đây là phép chuyển kiểu có bão hòa (*saturating conversion*), khác với ép kiểu `int` thông thường có thể làm tràn và đổi dấu.

```java
long value = 3_000_000_000L;

int wrapped = (int) value;
int saturated = Math.clamp(value, Integer.MIN_VALUE, Integer.MAX_VALUE);

System.out.println(wrapped);   // Có thể là số âm do tràn khi ép kiểu
System.out.println(saturated); // 2147483647
```

### Giữ kết quả long

Khi hai cận là `long`, Java chọn overload `clamp(long, long, long)` và trả về `long`:

```java
long fileSize = 8_000_000_000L;
long maxAllowed = 10_000_000_000L;

long acceptedSize = Math.clamp(fileSize, 0L, maxAllowed);
System.out.println(acceptedSize); // 8000000000
```

Hậu tố `L` làm rõ kiểu `long` của literal. Nếu cần giữ giá trị lớn hơn phạm vi `int`, hãy dùng các cận `long` để chọn đúng overload và tránh chuyển kết quả về `int`.

### Bảng chọn overload số nguyên

| Biểu thức gọi | Overload được chọn | Kiểu kết quả |
|---|---|---|
| `Math.clamp(10, 0, 100)` | `clamp(long, int, int)` | `int` |
| `Math.clamp(longValue, 0, 100)` | `clamp(long, int, int)` | `int` |
| `Math.clamp(longValue, 0L, 100L)` | `clamp(long, long, long)` | `long` |
| `Math.clamp(intValue, 0L, 100L)` | `clamp(long, long, long)` | `long` |

Quy tắc thực hành: nếu cận là `int`, overload đầu có thể trả về `int` kể cả khi giá trị đầu vào là `long`. Nếu muốn kết quả `long`, hãy truyền các cận kiểu `long`.

## 3. Chọn overload cho float và double

Khi cả ba đối số có kiểu `float`, Java chọn overload `clamp(float, float, float)` và trả về `float`:

```java
float opacity = Math.clamp(1.25f, 0.0f, 1.0f);
System.out.println(opacity); // 1.0
```

Khi giá trị hoặc một trong các cận có kiểu `double`, overload `clamp(double, double, double)` thường được chọn vì các đối số `float` và kiểu nguyên có thể được mở rộng sang `double`:

```java
double zoom = Math.clamp(1.25, 0.5, 2.0);
System.out.println(zoom); // 1.25

double mixed = Math.clamp(1.25f, 0.0, 1.0);
// Các cận là double nên kết quả là double.
```

Hậu tố literal có ảnh hưởng đến overload resolution:

| Literal | Kiểu |
|---|---|
| `1.0f` | `float` |
| `1.0` | `double` |
| `1` | `int` |
| `1L` | `long` |

Một số trường hợp trộn kiểu thường gặp:

| Kiểu đối số `(value, min, max)` | Overload được chọn | Lưu ý |
|---|---|---|
| `(float, int, int)` | `clamp(float, float, float)` | Hai cận nguyên được mở rộng thành `float` |
| `(double, float, float)` | `clamp(double, double, double)` | Các cận `float` được mở rộng thành `double` |
| `(long, float, float)` | `clamp(float, float, float)` | `long` được chuyển thành `float`, có thể mất độ chính xác |
| `(long, double, double)` | `clamp(double, double, double)` | `long` được chuyển thành `double`; số nguyên lớn hơn khả năng biểu diễn chính xác của double có thể bị làm tròn |

Nếu muốn giữ phép tính ở `float`, hãy dùng nhất quán giá trị và cận kiểu `float`, thường bằng hậu tố `f`. Nếu muốn giữ độ chính xác `double`, dùng `double` cho các biến và cận. Tránh trộn kiểu không chủ ý vì Java có thể chọn overload trả về kiểu rộng hơn và làm thay đổi kiểu kết quả.

Đặc biệt, `long` có thể được mở rộng sang `float`, nhưng phép chuyển đổi này có thể mất độ chính xác vì `float` không biểu diễn chính xác mọi số nguyên lớn. Ví dụ, `16_777_217L` không thể được biểu diễn chính xác dưới dạng `float`:

```java
long measurement = 16_777_217L;

float rounded = Math.clamp(measurement, 0.0f, 20_000_000.0f);
// Overload float được chọn; measurement được chuyển sang float.
System.out.println(rounded); // 1.6777216E7

long exactInteger = Math.clamp(measurement, 0L, 20_000_000L);
// Overload long được chọn; giữ nguyên giá trị nguyên.
System.out.println(exactInteger); // 16777217
```

Nếu dữ liệu có ý nghĩa nguyên, hãy dùng cận nguyên. Đừng dùng cận `float` chỉ để tận dụng một overload nếu điều đó làm mất độ chính xác của giá trị `long`.

## 4. Quy tắc chung và điều kiện hợp lệ của cận

Với overload số nguyên, `min` và `max` xác định khoảng đóng. Nếu `min > max`, phương thức ném `IllegalArgumentException`:

```java
int result = Math.clamp(50, 100, 0); // IllegalArgumentException
```

Với overload `float` và `double`, cận cũng phải hợp lệ:

- `min` hoặc `max` là `NaN`: ném `IllegalArgumentException`.
- `min > max`: ném `IllegalArgumentException`.
- `min` là `+0.0` và `max` là `-0.0`: ném `IllegalArgumentException`.
- Nếu `value` là `NaN` và hai cận hợp lệ: kết quả là `NaN`.

Điểm cuối rất quan trọng: `NaN` ở vị trí giá trị được clamp khác với `NaN` ở vị trí cận. `Math.clamp(Double.NaN, 0.0, 1.0)` trả về `NaN`; `Math.clamp(0.5, Double.NaN, 1.0)` ném `IllegalArgumentException`.

## 5. NaN, vô cực và signed zero

Các giá trị đặc biệt của IEEE 754 cần được hiểu rõ khi clamp số thực.

### NaN

Nếu `value` là `NaN`, phương thức trả `NaN` khi cận hợp lệ. Nó không tự biến `NaN` thành `min` hoặc `max`:

```java
double result = Math.clamp(Double.NaN, 0.0, 1.0);
System.out.println(Double.isNaN(result)); // true
```

Nếu nghiệp vụ yêu cầu `NaN` được thay bằng giá trị mặc định, hãy kiểm tra riêng trước khi gọi `clamp`:

```java
double input = readSensorValue();
double normalized = Double.isNaN(input)
        ? 0.0
        : Math.clamp(input, 0.0, 100.0);
```

### Vô cực

Với cận hợp lệ, giá trị vô cực được đưa về cận gần nhất:

```java
double high = Math.clamp(Double.POSITIVE_INFINITY, 0.0, 10.0);
double low = Math.clamp(Double.NEGATIVE_INFINITY, 0.0, 10.0);

System.out.println(high); // 10.0
System.out.println(low);  // 0.0
```

Nếu cận là vô cực và được sắp xếp hợp lệ, chúng cũng có thể được sử dụng. Ví dụ khoảng `[-Infinity, +Infinity]` không giới hạn các giá trị số thực thông thường.

### Âm zero và dương zero

Khác với toán tử so sánh số học thông thường, `Math.clamp` xem `-0.0` nhỏ hơn `+0.0`. Vì vậy:

```java
double result = Math.clamp(-0.0, +0.0, 1.0);
System.out.println(result); // 0.0
```

Ở đây kết quả là dương zero vì `-0.0` nằm dưới cận `+0.0`. Cặp cận `min = +0.0`, `max = -0.0` bị xem là khoảng không hợp lệ và gây `IllegalArgumentException`, dù toán tử `>` thông thường không phân biệt hai giá trị zero này.

Nếu dấu của zero có ý nghĩa trong tính toán, hãy kiểm tra bằng `Double.doubleToRawLongBits()` hoặc `Float.floatToRawIntBits()` thay vì chỉ in giá trị ra console; cách hiển thị thông thường có thể không thể hiện dấu zero.

## 6. Ứng dụng thực tế

### Giới hạn phần trăm hoặc opacity

```java
static float normalizeOpacity(float requested) {
    return Math.clamp(requested, 0.0f, 1.0f);
}
```

Giá trị opacity được giới hạn trong khoảng 0 đến 1 và giữ kiểu `float` để tương thích với API đồ họa nhận float.

### Giới hạn số lượng kết quả

```java
static int pageSize(int requested) {
    return Math.clamp(requested, 1, 100);
}
```

Ví dụ này dùng overload trả `int`, phù hợp với tham số page size thường được khai báo là `int`.

### Chuyển giá trị nhập từ hệ thống ngoài

```java
static int toBoundedInt(long externalId) {
    return Math.clamp(externalId, 0, Integer.MAX_VALUE);
}
```

Khi tích hợp với thành phần chỉ nhận `int`, overload `(long, int, int)` cho phép chuyển một giá trị `long` về phạm vi `int` bằng bão hòa thay vì để phép ép kiểu làm tràn.

## 7. Không nhầm clamp với kiểm tra dữ liệu đầu vào

`Math.clamp` bảo đảm kết quả nằm trong khoảng khi đầu vào và cận đáp ứng hợp đồng. Nó không thay thế việc xác thực dữ liệu nghiệp vụ.

Ví dụ, nếu điểm thi hợp lệ phải nằm trong `[0, 100]`, clamp sẽ biến `150` thành `100`. Nhưng nếu `150` thể hiện dữ liệu sai cần báo lỗi, clamp có thể che giấu lỗi đó. Hãy quyết định rõ hai chính sách:

- **Normalize/saturate:** dữ liệu ngoài khoảng được đưa về cận gần nhất.
- **Validate/reject:** dữ liệu ngoài khoảng bị từ chối hoặc báo lỗi.

Không dùng clamp để âm thầm sửa các giá trị mà hợp đồng nghiệp vụ yêu cầu phải hợp lệ ngay từ đầu.

Ngoài ra, clamp không ngăn overflow xảy ra trước khi lời gọi được thực hiện. Ví dụ:

```java
long next = Math.clamp(balance + delta, 0L, maximumBalance);
```

Nếu `balance + delta` tràn kiểu `long`, `Math.clamp` chỉ nhận giá trị đã bị tràn và không thể khôi phục giá trị toán học ban đầu. Nếu cần phát hiện overflow, dùng `Math.addExact(balance, delta)` hoặc thuật toán kiểm tra overflow trước khi clamp.

## 8. So sánh với cách dùng Math.min và Math.max

Trước Java 21, một biểu thức thường được dùng để giới hạn giá trị là:

```java
int result = Math.max(min, Math.min(max, value));
```

Với các giá trị nguyên và cận đã được xác thực, biểu thức này có thể tạo kết quả clamp tương tự. Tuy nhiên, `Math.clamp` thể hiện trực tiếp ý định, cung cấp overload chuyển `long` sang `int` có bão hòa và kiểm tra cận `min <= max` bằng exception.

Với số thực, không nên xem biểu thức `Math.max(min, Math.min(max, value))` là thay thế hoàn toàn tương đương cho `Math.clamp`: hợp đồng xử lý cận `NaN`, thứ tự hai zero và khoảng cận không hợp lệ cần được xét riêng. Khi cần đúng semantics của API Java 21, dùng `Math.clamp`.

## 9. Bảng kiểm thử các trường hợp quan trọng

| Lời gọi | Kết quả hoặc hành vi |
|---|---|
| `Math.clamp(5, 0, 10)` | `5`, kiểu trả về `int` |
| `Math.clamp(-5, 0, 10)` | `0` |
| `Math.clamp(15, 0, 10)` | `10` |
| `Math.clamp(5_000_000_000L, 0, 100)` | `100`, kiểu trả về `int` |
| `Math.clamp(5_000_000_000L, 0L, 10_000_000_000L)` | `5_000_000_000L`, kiểu trả về `long` |
| `Math.clamp(1.5f, 0.0f, 1.0f)` | `1.0f` |
| `Math.clamp(1.5, 0.0, 2.0)` | `1.5` |
| `Math.clamp(Double.NaN, 0.0, 1.0)` | `NaN` |
| `Math.clamp(Double.POSITIVE_INFINITY, 0.0, 1.0)` | `1.0` |
| `Math.clamp(0.5, Double.NaN, 1.0)` | `IllegalArgumentException` |
| `Math.clamp(5, 10, 0)` | `IllegalArgumentException` |

## 10. Checklist chọn overload

- [ ] Xác định kiểu tĩnh của `value`, `min` và `max` trước khi gọi.
- [ ] Với ba đối số `int`, nhớ Java chọn `clamp(long, int, int)` và trả `int`.
- [ ] Dùng cận `int` khi cần saturating conversion từ `long` về `int`.
- [ ] Dùng cả ba đối số `long` khi cần giữ kết quả `long`.
- [ ] Dùng hậu tố `f` nhất quán nếu cần overload `float`.
- [ ] Dùng `double` nhất quán nếu cần kết quả `double`.
- [ ] Kiểm tra `min <= max`; riêng số thực còn phải loại `NaN` ở hai cận và cặp `+0.0`/`-0.0` không hợp lệ.
- [ ] Xác định rõ cách xử lý `value` là `NaN` trước khi dùng trong nghiệp vụ.
- [ ] Không dùng clamp để che giấu dữ liệu sai nếu nghiệp vụ yêu cầu từ chối.
- [ ] Kiểm tra overflow ở biểu thức tính `value` trước khi gọi clamp.

## Tài liệu tham khảo

- [Math — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html): bốn overload `clamp`, kiểu trả về, saturating conversion, quy tắc NaN, signed zero và exception khi cận không hợp lệ.
- [StrictMath — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StrictMath.html): các phương thức clamp tương ứng và semantics được đặc tả.
- [Java Language Specification, Java SE 21 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12): quy tắc overload resolution và chuyển đổi kiểu khi gọi phương thức.
