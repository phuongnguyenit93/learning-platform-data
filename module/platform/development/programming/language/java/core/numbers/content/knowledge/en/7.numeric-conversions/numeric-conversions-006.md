# Chuyển NaN, vô cực và số ngoài phạm vi sang kiểu nguyên trong Java

Trong Java, ép kiểu từ số dấu phẩy động (`float`, `double`) sang số nguyên (`byte`, `short`, `int`, `long`; và cả `char`) là **narrowing primitive conversion**. Đây không đơn thuần là “bỏ phần thập phân”: với **`NaN`**, **`+Infinity`**, **`-Infinity`** hoặc giá trị hữu hạn nằm ngoài miền kiểu đích, Java có các quy tắc chuyển đổi xác định.

Ba điều cần ghi nhớ ngay:

1. **Giá trị hữu hạn trong phạm vi:** bỏ phần phân số **hướng về 0**; ví dụ `(int) 3.9 == 3` và `(int) -3.9 == -3`.
2. **Chuyển trực tiếp `float`/`double` sang `int` hoặc `long`:** `NaN` thành `0`; giá trị quá lớn hoặc `+Infinity` thành `MAX_VALUE`; giá trị quá âm hoặc `-Infinity` thành `MIN_VALUE`.
3. **Chuyển sang `byte`, `short`, `char`:** Java **trước hết chuyển sang `int`**, sau đó thu hẹp `int` về kiểu nhỏ bằng cách bỏ các bit cao. Vì thế `(byte) Double.POSITIVE_INFINITY` thành **`-1`**, không phải `Byte.MAX_VALUE`.

Các chuyển đổi nguyên thủy này **không tự ném ngoại lệ do tràn miền**. Nếu chương trình cần từ chối dữ liệu không hữu hạn, vượt miền hoặc có phần lẻ, phải **kiểm tra rõ ràng trước khi cast**.

## 1. Nguồn và đích: chuyển kiểu nào đang được nói đến?

Bài này chỉ xét **giá trị kiểu `float` hoặc `double` khi chuyển sang kiểu nguyên**:

| Kiểu đích | Miền giá trị |
| --- | --- |
| `byte` | -128 đến 127 |
| `short` | -32.768 đến 32.767 |
| `int` | -2.147.483.648 đến 2.147.483.647 |
| `long` | -9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 |
| `char` | 0 đến 65.535 (đơn vị mã UTF-16, không dấu) |

`char` được đưa vào để hiểu đúng quy tắc chuyển kiểu của Java, nhưng không nên dùng `char` để lưu số lượng hoặc tính toán số nguyên thông thường.

`NaN` (*Not a Number*) và vô cực (`+Infinity`, `-Infinity`) là các giá trị đặc biệt của `float`/`double`, **không phải giá trị nguyên**. `NaN` có thể xuất hiện từ `0.0 / 0.0`, `+Infinity` có thể đến từ `1.0 / 0.0` hoặc overflow dấu phẩy động, `-Infinity` có thể đến từ `-1.0 / 0.0`. Ngoài ra, `Double.MAX_VALUE` tuy là **số hữu hạn** vẫn lớn hơn rất nhiều so với `Long.MAX_VALUE`.

Không nên đánh đồng ba tình huống:

- **Phần lẻ trong miền:** có thể cắt về 0 mà không chạm biên, ví dụ `7.8 → 7`.
- **Ngoài miền:** có thể nhận giá trị giới hạn `MAX_VALUE`/`MIN_VALUE` khi chuyển trực tiếp thành `int`/`long`.
- **`NaN` hoặc vô cực:** là giá trị đặc biệt và được xử lý theo quy tắc riêng; bản thân không chứa một số nguyên hữu hạn cần chuyển.

## 2. Quy tắc chính xác theo Java: chuyển sang `int` hoặc `long`

Theo quy tắc thu hẹp từ dấu phẩy động sang số nguyên của Java, khi kiểu đích là `int` hoặc `long`, có thể hình dung thành ba bước:

1. Nếu nguồn là **`NaN`**, kết quả là **`0`** thuộc kiểu đích.
2. Nếu nguồn là **số hữu hạn khác NaN** và phần nguyên sau khi cắt về 0 nằm trong phạm vi, kết quả là phần nguyên đó.
3. Nếu độ lớn vượt miền (kể cả **`+Infinity`/`-Infinity`**), kết quả **bị chặn tại biên đích**: lớn quá → `MAX_VALUE`, âm quá → `MIN_VALUE`.

Bước 2 sử dụng **truncation toward zero**, không phải làm tròn đến số nguyên gần nhất:

| Biểu thức | Kết quả |
| --- | ---: |
| `(int) 3.9` | `3` |
| `(int) -3.9` | `-3` |
| `(int) 0.99` | `0` |
| `(int) -0.99` | `0` |
| `(int) -0.0` | `0` |
| `(int) Double.NaN` | `0` |
| `(int) Double.POSITIVE_INFINITY` | `2147483647` |
| `(int) Double.NEGATIVE_INFINITY` | `-2147483648` |
| `(int) 1e100` | `2147483647` |
| `(long) -1e100` | `-9223372036854775808` |

**Điểm quan trọng:** `(int) Double.POSITIVE_INFINITY` cho `Integer.MAX_VALUE`, nhưng điều này **không có nghĩa** vô cực là một số nguyên lớn có thể lưu chính xác. Java chỉ quy định một kết quả cast. Dữ liệu ban đầu đã không thể biểu diễn trong `int`.

Tương tự, `(int) 1e100` và `(int) Double.POSITIVE_INFINITY` có thể cùng ra `Integer.MAX_VALUE`. Nhìn giá trị `int` cuối cùng **không thể biết** nó đến từ số hợp lệ, từ số lớn bị chặn hay từ vô cực; vì vậy không nên chỉ dựa vào kết quả sau cast để xác nhận dữ liệu.

Các phép cast này **khác hẳn** việc thu hẹp `long` sang `int`. Với `long → int`, Java bỏ các bit cao nên `(int) 3_000_000_000L` bằng `-1294967296`. Với `double → int`, giá trị nguồn `3_000_000_000.0` lại thành **`2147483647`** do quy tắc chuyển từ dấu phẩy động.

## 3. Vì sao `byte` và `short` xử lý khác `int`?

Với đích là `byte`, `short` hoặc `char`, Java áp dụng quy trình **hai giai đoạn**:

1. Thu hẹp `float`/`double` sang **`int`**, theo quy tắc `NaN → 0`, cắt về 0, chặn biên `int` nếu ngoài miền.
2. Thu hẹp giá trị `int` trung gian sang `byte`, `short` hay `char` bằng cách **giữ lại các bit thấp** phù hợp với kiểu đích.

Đối với số có dấu `byte`/`short`, mẫu bit được diễn giải theo bù hai; với `char` là giá trị không dấu 16 bit. Bước thứ hai **không phải clamp về giới hạn `byte`/`short`**.

Ví dụ chuyển `+Infinity` sang `byte`:

```text
+Infinity
  → chuyển double sang int: Integer.MAX_VALUE = 2147483647 (0x7FFFFFFF)
  → chuyển int sang byte: giữ 8 bit thấp = 0xFF
  → byte có dấu: -1
```

Vì thế:

| Biểu thức | Giá trị cuối |
| --- | ---: |
| `(byte) Double.NaN` | `0` |
| `(short) Double.NaN` | `0` |
| `(byte) Double.POSITIVE_INFINITY` | `-1` |
| `(byte) Double.NEGATIVE_INFINITY` | `0` |
| `(short) Double.POSITIVE_INFINITY` | `-1` |
| `(short) Double.NEGATIVE_INFINITY` | `0` |
| `(byte) 130.9` | `-126` |
| `(byte) 1e100` | `-1` |
| `(char) Double.POSITIVE_INFINITY` | ký tự có mã `65535` |

Ví dụ `(byte) 130.9`: bước 1 cắt `130.9` thành `int 130` (vẫn trong miền `int`), bước 2 giữ 8 bit thấp của `130` là `0x82`, diễn giải dạng `byte` có dấu thành **-126**. Đây là hai quy tắc liên tiếp, **không phải** làm tròn `130.9` xuống -126 theo số học.

**Không suy luận** rằng ép từ `double` sang `byte` luôn “saturate tại ±128”. Kết quả tùy **bit của `int` trung gian**; với `+Infinity`, kết quả `byte` âm là hoàn toàn hợp lệ theo đặc tả Java.

## 4. Chuyển NaN: tại sao ra 0 mà không báo lỗi?

`Double.NaN` và `Float.NaN` đại diện cho trạng thái *Not a Number*. Với phép narrowing floating-point → integral, Java quy định `NaN` thành 0 ở bước chuyển sang `int` hoặc `long`. Nếu đích là `byte`, `short` hay `char`, `int 0` trung gian cũng cho kết quả 0.

```java
int a = (int) Double.NaN;     // 0
long b = (long) Float.NaN;    // 0L
byte c = (byte) Double.NaN;   // 0
```

Điểm nguy hiểm là **0 có thể đồng thời là dữ liệu nghiệp vụ hợp lệ**. Nếu hệ thống nhận một giá trị đo không hợp lệ là `NaN` rồi cast thẳng sang `int`, kết quả `0` có thể bị hiểu sai thành “không có số lượng”, “nhiệt độ bằng 0” hoặc một mã trạng thái hợp lệ.

Đừng dùng `value == Double.NaN` để phát hiện NaN: `NaN` không bằng chính nó trong phép so sánh dấu phẩy động. Dùng `Double.isNaN(value)` hoặc `Float.isNaN(value)`.

`Double.isFinite(value)`/`Float.isFinite(value)` thuận tiện hơn nếu **mọi giá trị đặc biệt** (NaN và cả ±Infinity) đều phải bị từ chối.

## 5. Vô cực: quy tắc ép kiểu khác phép chia cho 0

`Double.POSITIVE_INFINITY` và `Double.NEGATIVE_INFINITY` là các giá trị hợp lệ của kiểu `double` theo ngữ nghĩa IEEE 754. Phép chia `1.0 / 0.0` trả `+Infinity`, khác với phép chia số nguyên `1 / 0`, vốn ném `ArithmeticException` khi thực hiện.

```java
double positive = Double.POSITIVE_INFINITY;
double negative = Double.NEGATIVE_INFINITY;

int max = (int) positive;  // Integer.MAX_VALUE
int min = (int) negative;  // Integer.MIN_VALUE

long longMax = (long) positive; // Long.MAX_VALUE
long longMin = (long) negative; // Long.MIN_VALUE
```

Trong phép cast primitive này Java không ném `ArithmeticException`. Thay vào đó, giá trị vô cực **bị chặn** ở biên của `int`/`long` trước khi có thể tiếp tục thu hẹp sang kiểu nhỏ.

Tuy nhiên, có sự khác biệt giữa **giá trị nguồn trước cast** và **giá trị được chọn sau cast**. Một chương trình cần giữ ý nghĩa “nguồn bị lỗi/vô cực” phải kiểm tra nguồn **trước khi chuyển kiểu**; sau cast, thông tin rằng nó từng là vô cực đã biến mất.

## 6. Số hữu hạn ngoài miền vẫn bị chặn: không cần NaN hay Infinity

Một `double` có thể hữu hạn và lớn hơn `Integer.MAX_VALUE` nhiều lần. Ví dụ `1e100` là hữu hạn, nhưng tích cực lớn hơn cả `Long.MAX_VALUE`:

```java
double big = 1e100;

int toInt = (int) big;   // 2147483647
long toLong = (long) big; // 9223372036854775807
```

Số âm ngoài miền cũng bị chặn ở biên âm:

```java
double small = -1e100;

int toInt = (int) small;   // -2147483648
long toLong = (long) small; // -9223372036854775808
```

Với giá trị chỉ hơi ngoài miền `int`:

```java
double d = 2_147_483_648.0; // Integer.MAX_VALUE + 1, biểu diễn chính xác bằng double
int converted = (int) d;    // 2147483647, không phải -2147483648
```

Điều này khác với cast `(int) 2_147_483_648L` từ `long`: cast `long → int` cắt bit, cho `-2147483648`. Với cast từ `double`, Java **chặn ở `Integer.MAX_VALUE`**. Phân biệt **kiểu nguồn** rất quan trọng trước khi dự đoán kết quả.

## 7. Chương trình Java 17+ chạy độc lập

Tạo tệp `FloatToIntegerDemo.java`:

```java
public class FloatToIntegerDemo {
    static int checkedInt(double v) {
        if (!Double.isFinite(v)
                || v < Integer.MIN_VALUE
                || v > Integer.MAX_VALUE
                || v != Math.rint(v)) {
            throw new IllegalArgumentException("not an in-range integer");
        }
        return (int) v;
    }

    public static void main(String[] args) {
        System.out.println("3.9 -> int: " + (int) 3.9);
        System.out.println("-3.9 -> int: " + (int) -3.9);
        System.out.println("-0.0 -> int: " + (int) -0.0);
        System.out.println("NaN -> int: " + (int) Double.NaN);
        System.out.println("+Infinity -> int: " + (int) Double.POSITIVE_INFINITY);
        System.out.println("-Infinity -> int: " + (int) Double.NEGATIVE_INFINITY);
        System.out.println("1e100 -> int: " + (int) 1e100);
        System.out.println("-1e100 -> long: " + (long) -1e100);
        System.out.println("+Infinity -> long: " + (long) Double.POSITIVE_INFINITY);
        System.out.println("+Infinity -> byte: " + (byte) Double.POSITIVE_INFINITY);
        System.out.println("-Infinity -> byte: " + (byte) Double.NEGATIVE_INFINITY);
        System.out.println("NaN -> short: " + (short) Double.NaN);
        System.out.println("130.9 -> byte: " + (byte) 130.9);
        System.out.println("1e100 -> byte: " + (byte) 1e100);
        System.out.println("1e100 -> char code: " + (int) (char) 1e100);
        System.out.println("NaN finite? " + Double.isFinite(Double.NaN));

        System.out.println("checkedInt(7.0): " + checkedInt(7.0));
        try {
            checkedInt(7.5);
        } catch (IllegalArgumentException ex) {
            System.out.println("checkedInt(7.5): rejected");
        }
        try {
            checkedInt(Double.POSITIVE_INFINITY);
        } catch (IllegalArgumentException ex) {
            System.out.println("checkedInt(Infinity): rejected");
        }
        try {
            new java.math.BigDecimal("2147483648").intValueExact();
        } catch (ArithmeticException ex) {
            System.out.println("BigDecimal out of range: rejected");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac FloatToIntegerDemo.java
java FloatToIntegerDemo
```

Kết quả stdout (các giá trị đã được kiểm chứng trên JDK):

```text
3.9 -> int: 3
-3.9 -> int: -3
-0.0 -> int: 0
NaN -> int: 0
+Infinity -> int: 2147483647
-Infinity -> int: -2147483648
1e100 -> int: 2147483647
-1e100 -> long: -9223372036854775808
+Infinity -> long: 9223372036854775807
+Infinity -> byte: -1
-Infinity -> byte: 0
NaN -> short: 0
130.9 -> byte: -126
1e100 -> byte: -1
1e100 -> char code: 65535
NaN finite? false
checkedInt(7.0): 7
checkedInt(7.5): rejected
checkedInt(Infinity): rejected
BigDecimal out of range: rejected
```

Trong ví dụ này:

- Các dòng `3.9`, `-3.9` và `-0.0` chứng minh phép chuyển sang `int` **cắt về 0**, bao gồm cả việc mất dấu của `-0.0`.
- Các dòng `NaN`, `Infinity` và `1e100` chứng minh **0 hoặc chặn biên** khi đích trực tiếp là `int`/`long`.
- Các dòng `byte` và `char` chứng minh **giai đoạn chuyển qua `int` rồi bỏ bit cao**.
- Hàm `checkedInt` minh họa **phát hiện dữ liệu ngoài miền, không hữu hạn hoặc không nguyên** thay vì âm thầm làm mất thông tin.
- `BigDecimal.intValueExact()` minh họa một API ném ngoại lệ khi số thập phân chính xác không thể chuyển thành số nguyên đích mà vẫn giữ giá trị.

## 8. Chuyển đổi có kiểm tra: từ chối mất dữ liệu thay vì chấp nhận cast

Nếu nghiệp vụ cần chuyển một phép đo `double` sang `int` và **chỉ chấp nhận số nguyên hữu hạn nằm trong miền**, hãy kiểm tra đủ ba điều kiện **trước khi cast**:

1. **Hữu hạn:** `Double.isFinite(v)` để loại `NaN` và ±Infinity.
2. **Nằm trong phạm vi:** `Integer.MIN_VALUE <= v && v <= Integer.MAX_VALUE` (các giới hạn này đều biểu diễn chính xác bằng `double`).
3. **Không có phần lẻ:** `v == Math.rint(v)`. `Math.rint` trả giá trị `double` nguyên gần nhất theo quy tắc làm tròn của nó; dùng **để so sánh xem `v` đã nguyên chưa**, không dùng kết quả rint để âm thầm thay đổi dữ liệu.

Hàm `checkedInt` trong chương trình đầy đủ thực hiện cả ba kiểm tra. Với nguồn `NaN`, điều kiện `Double.isFinite` đặc biệt quan trọng: các so sánh kiểu `v < min`, `v > max` hoặc `v != ...` cần được hiểu đúng với NaN. Mã kiểm tra thường nên có nhánh `isFinite` rõ ràng để tránh vô tình chấp nhận NaN.

Nếu yêu cầu **cho phép cắt phần lẻ** (ví dụ từ 7.9 thành 7), bỏ điều kiện `Math.rint`, nhưng vẫn kiểm tra `isFinite` và miền **trước** phép cast. Nếu yêu cầu **làm tròn** theo chính sách (nearest, floor, ceiling), áp dụng quy tắc làm tròn được chọn rồi **kiểm tra miền của kết quả** trước khi chuyển.

### Kiểm tra riêng cho `long`: biên dương cần lưu ý

Kiểm tra một `double` để cast an toàn sang `long` phức tạp hơn nhìn qua, vì **`Long.MAX_VALUE` không được biểu diễn chính xác bằng `double`**. Khi chuyển `Long.MAX_VALUE` sang `double`, giá trị được làm tròn thành **`2^63`**, là số nằm **ngoài miền `long`**. Vì vậy biểu thức:

```java
// KHÔNG phải phép kiểm tra đầy đủ đối với double:
if (v <= Long.MAX_VALUE) {
    // Có thể chấp nhận cả v == 2^63 do Long.MAX_VALUE bị làm tròn lên.
}
```

không đủ nghiêm ngặt cho biên dương. Với nguồn `double`, có thể kiểm tra miền bằng hai ngưỡng biểu diễn chính xác là **`-2^63`** (được phép) và **`+2^63`** (phải từ chối):

```java
static long checkedLong(double v) {
    if (!Double.isFinite(v)
            || v < -0x1.0p63   // v nhỏ hơn Long.MIN_VALUE
            || v >= 0x1.0p63   // v lớn hơn hoặc bằng 2^63
            || v != Math.rint(v)) {
        throw new IllegalArgumentException("not an in-range integer");
    }
    return (long) v;
}
```

Đây là **đoạn phương thức minh họa**, cần đặt trong một class khi dùng thực tế. Các literal hexa dấu phẩy động `0x1.0p63` biểu diễn chính xác `2^63` dưới dạng `double`. Vì vậy `checkedLong` chấp nhận `-2^63`, nhưng từ chối `+2^63`. Điều kiện `Math.rint` từ chối giá trị có phần lẻ biểu diễn được.

Cần biết thêm: nguồn `double` đã **có độ chính xác hữu hạn**. Ngay cả khi giá trị sau kiểm tra là một số nguyên, không thể suy ra mọi chữ số của một số nguyên đầu vào rất lớn ban đầu còn nguyên; một phép chuyển `long → double` trước đó có thể đã làm tròn. **Kiểm tra sau cùng không phục hồi thông tin đã mất trước khi chuyển.**

### Khi đầu vào là dữ liệu thập phân chính xác

Nếu nhập từ JSON/chuỗi thập phân và cần phân biệt số có phần lẻ, vượt miền, hoặc yêu cầu giữ chính xác, cân nhắc **`BigDecimal` từ chuỗi**:

```java
int valid = new java.math.BigDecimal("2147483647.0").intValueExact();
// 2147483647

// new java.math.BigDecimal("2147483648").intValueExact();
// ArithmeticException: vượt miền int.

// new java.math.BigDecimal("7.5").intValueExact();
// ArithmeticException: có phần lẻ.
```

`BigDecimal.intValueExact()` và `longValueExact()` kiểm tra khả năng chuyển **không mất giá trị**. Nhưng `BigDecimal` từ chuỗi thập phân hữu hạn **không đại diện trực tiếp cho NaN hoặc vô cực**; dữ liệu đặc biệt phải được xử lý theo quy tắc xác thực đầu vào. Tạo `BigDecimal` từ một `double` đã bị làm tròn cũng không thể khôi phục chữ số nguyên ban đầu bị mất.

## 9. Phân biệt cast, `Math.round` và `Math.toIntExact`

| Cách chuyển | Hành vi chủ yếu | Có báo lỗi do không vừa phạm vi? |
| --- | --- | --- |
| `(int) someDouble` | Cắt phần lẻ về 0; NaN → 0; quá miền → biên `int` | Không |
| `(long) someDouble` | Tương tự, dùng miền `long` | Không |
| `(byte) someDouble` | Qua `int` rồi bỏ bit cao xuống 8 bit | Không |
| `Math.round(double)` | Làm tròn về số nguyên gần nhất theo quy tắc của API; trả `long` | Không; NaN/±Infinity được xử lý đặc biệt |
| `Math.round(float)` | Làm tròn về số nguyên gần nhất theo quy tắc của API; trả `int` | Không; NaN/±Infinity được xử lý đặc biệt |
| `Math.toIntExact(long)` | Chuyển `long` sang `int` và kiểm tra miền | **Có**: `ArithmeticException` nếu vượt miền |
| `BigDecimal.intValueExact()` | Chuyển giá trị thập phân chính xác sang `int`, kiểm tra phần lẻ/miền | **Có**: `ArithmeticException` nếu không chính xác |

`Math.round` là **phép làm tròn**, không đồng nghĩa với cast cắt về 0: `(int) 3.9 == 3`, nhưng `Math.round(3.9) == 4L`. Với NaN, `Math.round` trả 0; với ±Infinity, trả biên nguyên của kiểu kết quả. Phải chọn API theo **chính sách làm tròn** mong muốn.

`Math.toIntExact` **không có overload nhận `double`**. Viết `Math.toIntExact((long) value)` có thể đã **chặn giá trị ở miền `long` hoặc cắt phần lẻ trước khi kiểm tra**. Điều này không thay thế bước xác thực nguồn `double`.

Khi giải bài toán tiền tệ, mã giao dịch, phân trang, số lượng hoặc số đo có giới hạn, nên xác định rõ liệu giá trị `NaN`/Infinity có thể xuất hiện hay không, có cho phép phần lẻ hay không, miền hợp lệ là gì và chính sách làm tròn nào được phép. Cast đơn giản chỉ phù hợp khi đã chấp nhận ngữ nghĩa mất dữ liệu của Java.

## 10. Những nhầm lẫn thường gặp

1. **“Cast `double` sang `int` sẽ quấn vòng như cast `long` sang `int`.”** Sai. `double → int` chặn biên khi vượt miền, còn `long → int` bỏ bit cao.
2. **“`NaN` luôn ném lỗi khi cast thành số nguyên.”** Sai: narrowing primitive chuyển NaN thành 0.
3. **“`+Infinity` chuyển sang `byte` bằng `127`.”** Sai: bước `double → int` cho `Integer.MAX_VALUE`, sau đó `int → byte` cho `-1`.
4. **“`(int) -3.9` bằng -4.”** Sai: cắt về 0 nên bằng -3; đó không phải `Math.floor`.
5. **“Vượt phạm vi cast sẽ tự báo `ArithmeticException`.”** Sai: primitive cast dùng quy tắc chuyển đổi, không tự ném lỗi do vượt miền.
6. **“Kiểm tra `v <= Long.MAX_VALUE` bằng `double` là đủ.”** Sai ở biên dương vì `Long.MAX_VALUE` được làm tròn thành `2^63` khi so với `double`.
7. **“Chỉ cần kiểm tra `v < min || v > max` để bắt mọi giá trị xấu.”** Sai: NaN có so sánh đặc biệt; hãy xác thực hữu hạn rõ ràng.
8. **“Sau cast không thấy Infinity thì dữ liệu đã hợp lệ.”** Sai: nhiều nguồn rất khác nhau cùng tạo ra `MAX_VALUE`, `MIN_VALUE` hoặc 0.
9. **“`Math.round` và cast đều bỏ phần thập phân về 0.”** Sai: `Math.round` thực hiện làm tròn.
10. **“`BigDecimal.valueOf(double)` tự phục hồi chữ số đã mất.”** Sai: việc chuyển đổi một số nguyên lớn qua `double` có thể làm tròn trước đó; thông tin bị mất không thể lấy lại.

## 11. Tự kiểm tra

- `(int) Double.NaN` bằng gì? **0**.
- `(long) Double.NEGATIVE_INFINITY` bằng gì? **Long.MIN_VALUE**.
- `(byte) Double.POSITIVE_INFINITY` bằng gì? **-1**, vì chuyển qua `int` rồi giữ 8 bit thấp.
- `(int) -8.99` bằng gì? **-8**, do cắt phần lẻ về 0.
- `(int) 3_000_000_000.0` bằng gì? **Integer.MAX_VALUE**, không phải kết quả cast từ `long`.
- `Math.toIntExact((long) Double.NaN)` có phát hiện NaN không? **Không**: cast sang `long` đã cho 0 trước khi `toIntExact` nhận được đối số.
- Muốn chấp nhận *chỉ* các giá trị nguyên hữu hạn trong miền `int`, cần làm gì? **Kiểm tra `Double.isFinite`, min/max và không có phần lẻ trước khi cast**, hoặc dùng giải pháp thập phân chính xác phù hợp nguồn dữ liệu.

**Ghi nhớ:** chuyển `float`/`double` sang `int`/`long` là **cắt về 0, NaN → 0, vượt miền/±Infinity → biên**. Chuyển sang `byte`/`short`/`char` còn có **bước thu hẹp từ `int`**, nên kết quả có thể âm hoặc bất ngờ. Nếu dữ liệu phải chính xác và hợp lệ, **xác thực trước khi chuyển**, thay vì kiểm tra giá trị đã mất thông tin sau cast.
