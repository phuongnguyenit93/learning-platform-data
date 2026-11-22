# `Math.addExact`, `subtractExact` và `multiplyExact`: phát hiện tràn số nguyên trong Java

Trong Java, phép cộng `+`, trừ `-` và nhân `*` trên `int`/`long` **không tự báo lỗi khi kết quả vượt phạm vi**. Kết quả sẽ bị tràn theo biểu diễn số nguyên có độ rộng cố định. Điều này nguy hiểm khi tính tổng tiền theo đơn vị nhỏ nhất, số lượng tồn kho, kích thước bộ nhớ, bộ đếm, số điểm hoặc giới hạn giao dịch.

`java.lang.Math` cung cấp ba phương thức **kiểm tra tràn** (*exact arithmetic*):

- `Math.addExact(a, b)`: tính `a + b` và báo lỗi nếu kết quả không biểu diễn được bằng kiểu trả về.
- `Math.subtractExact(a, b)`: tính `a - b`, có kiểm tra tràn.
- `Math.multiplyExact(a, b)`: tính `a * b`, có kiểm tra tràn.

Khi tràn, cả ba đều **ném `ArithmeticException`**, thay vì trả giá trị đã quay vòng. Chúng không tự mở rộng kiểu của phép toán và không tạo số nguyên có độ dài vô hạn.

## 1. Tại sao cần phép toán có kiểm tra tràn?

`int` có 32 bit có dấu, biểu diễn từ `-2_147_483_648` đến `2_147_483_647`. `long` có 64 bit có dấu, từ `-9_223_372_036_854_775_808L` đến `9_223_372_036_854_775_807L`.

Ví dụ phép toán thường:

```java
int a = Integer.MAX_VALUE;
int unchecked = a + 1; // -2147483648: đã tràn int
```

`Integer.MAX_VALUE` là 2.147.483.647, nên cộng 1 về mặt toán học phải ra 2.147.483.648, không chứa vừa `int`. `+` không báo lỗi; kết quả `int` thành giá trị âm nhỏ nhất.

Dùng phép toán có kiểm tra:

```java
int a = Integer.MAX_VALUE;
int checked = Math.addExact(a, 1); // ArithmeticException lúc chạy
```

Nếu kết quả nằm trong miền của kiểu trả về, `addExact` trả **chính kết quả số học**. Nếu nằm ngoài miền, method ném exception; không có giá trị trả về thành công.

| Phép tính | Toán tử thông thường trên `int` | `Math.*Exact` trên `int` |
| --- | --- | --- |
| `40 + 2` | 42 | 42 |
| `Integer.MAX_VALUE + 1` | -2147483648 (tràn) | `ArithmeticException` |
| `Integer.MIN_VALUE - 1` | 2147483647 (tràn) | `ArithmeticException` |
| `100_000 * 100_000` | 1410065408 (tràn) | `ArithmeticException` |

**Giới hạn của việc kiểm tra:** các method phát hiện tràn **ở phép toán do chính method thực hiện**, không có khả năng suy ngược lỗi đã xảy ra trước khi chúng được gọi.

## 2. Cú pháp, overload và kiểu kết quả

Ba method là `static` trong `java.lang.Math`, nên có thể gọi bằng `Math.addExact(...)` mà không cần `import`.

| Phép toán | Chữ ký thường dùng | Kiểu trả về |
| --- | --- | --- |
| Cộng chính xác | `Math.addExact(int x, int y)` | `int` |
| Cộng chính xác | `Math.addExact(long x, long y)` | `long` |
| Trừ chính xác | `Math.subtractExact(int x, int y)` | `int` |
| Trừ chính xác | `Math.subtractExact(long x, long y)` | `long` |
| Nhân chính xác | `Math.multiplyExact(int x, int y)` | `int` |
| Nhân chính xác | `Math.multiplyExact(long x, long y)` | `long` |
| Nhân chính xác | `Math.multiplyExact(long x, int y)` | `long` |

Overload `multiplyExact(long, int)` có trong Java hiện đại (bao gồm Java 17). Khi `int` được truyền cho tham số `long`, Java có thể tự mở rộng kiểu như lời gọi method thông thường.

Ví dụ:

```java
int sum = Math.addExact(15, 27);        // 42, overload int
long sumLong = Math.addExact(15L, 27);  // 42L, overload long
int product = Math.multiplyExact(6, 7); // 42
long big = Math.multiplyExact(100_000L, 100_000); // 10000000000L
```

Lưu ý quan trọng: **kiểu của biến nhận kết quả không quyết định overload được chọn**.

```java
// Vẫn gọi multiplyExact(int, int), nên phép nhân tràn sẽ ném exception:
long wrong = Math.multiplyExact(100_000, 100_000);

// Chọn phép nhân có kết quả long ngay tại lời gọi:
long correct = Math.multiplyExact(100_000L, 100_000);
```

Đây là đoạn minh họa: dòng `wrong` biên dịch được nhưng ném exception lúc chạy nếu được thực thi. Chữ `L` hoặc ép kiểu phải xuất hiện **ở đối số trước khi gọi**; gán kết quả vào `long` sau lời gọi không cứu được phép tính `int`.

## 3. `Math.addExact`: cộng và phát hiện vượt biên

`addExact(x, y)` trả `x + y` khi kết quả nằm trong miền `int`/`long` được chọn; nếu không thì ném `ArithmeticException`.

### Ví dụ bình thường và sát biên

```java
int score = Math.addExact(80, 20); // 100
int max = Math.addExact(Integer.MAX_VALUE - 1, 1); // Integer.MAX_VALUE
int min = Math.addExact(Integer.MIN_VALUE, 0); // Integer.MIN_VALUE
```

Ở đây chạm chính xác giá trị lớn nhất/nhỏ nhất là **hợp lệ**. Method chỉ báo lỗi khi phép tính vượt phạm vi.

### Vượt biên dương và âm

```java
// ArithmeticException: 2147483647 + 1 nằm ngoài int
Math.addExact(Integer.MAX_VALUE, 1);

// ArithmeticException: -2147483648 + (-1) nằm ngoài int
Math.addExact(Integer.MIN_VALUE, -1);
```

Hai câu lệnh là đoạn **minh họa ném exception**, không phải ví dụ để chạy mà không có xử lý lỗi.

Nếu yêu cầu là **tính được kết quả lớn hơn miền int**, hãy chọn overload `long` ngay từ đầu:

```java
long expanded = Math.addExact((long) Integer.MAX_VALUE, 1);
// 2147483648L
```

Nhưng `long` vẫn có giới hạn. `Math.addExact(Long.MAX_VALUE, 1L)` cũng ném `ArithmeticException`.

## 4. `Math.subtractExact`: trừ hai số và trường hợp biên

`subtractExact(x, y)` kiểm tra kết quả toán học của `x - y`. Phép trừ có thể tràn ở cả hai chiều:

```java
int remaining = Math.subtractExact(100, 35); // 65
int min = Math.subtractExact(Integer.MIN_VALUE + 1, 1); // MIN_VALUE
```

Các trường hợp này ném `ArithmeticException`:

```java
// Tràn âm: MIN_VALUE - 1 < MIN_VALUE
Math.subtractExact(Integer.MIN_VALUE, 1);

// Tràn dương: MAX_VALUE - (-1) > MAX_VALUE
Math.subtractExact(Integer.MAX_VALUE, -1);
```

Dấu của toán hạng thứ hai dễ làm người học nhầm: **trừ số âm tương đương cộng số dương về mặt toán học**, nên `MAX_VALUE - (-1)` vượt trần `int`.

Với `long`:

```java
long safe = Math.subtractExact((long) Integer.MIN_VALUE, 1L);
// -2147483649L, hợp lệ vì vẫn nằm trong long
```

`Math.subtractExact(Long.MIN_VALUE, 1L)` ném `ArithmeticException`. Kiểm tra biên luôn tương ứng kiểu đã chọn, không phải phạm vi `int` một cách cố định.

## 5. `Math.multiplyExact`: nhân và phát hiện tràn

Phép nhân có thể vượt phạm vi ngay cả khi từng toán hạng riêng lẻ nhỏ hơn giới hạn. Ví dụ `100_000` vẫn là `int` hợp lệ, nhưng tích `100_000 * 100_000 = 10_000_000_000` vượt `int`.

```java
int normal = Math.multiplyExact(6, 7); // 42
int square = Math.multiplyExact(46_340, 46_340); // 2147395600

// Ném ArithmeticException:
Math.multiplyExact(100_000, 100_000);
```

`46_340 * 46_340 = 2_147_395_600` vẫn nằm trong miền `int`, vì vậy method trả kết quả bình thường. `46_341 * 46_341 = 2_147_488_281` vượt `Integer.MAX_VALUE` nên `Math.multiplyExact(46_341, 46_341)` ném exception.

### Tích âm và cặp giá trị đặc biệt

Với `int`, `Integer.MIN_VALUE * (-1)` không chứa vừa kiểu `int`: kết quả toán học là `2_147_483_648`.

```java
// Ném ArithmeticException:
Math.multiplyExact(Integer.MIN_VALUE, -1);
```

Tương tự, `Math.multiplyExact(Long.MIN_VALUE, -1L)` ném exception vì kết quả dương vượt `Long.MAX_VALUE`.

Các trường hợp có `0` luôn cho tích `0` và không tràn, bất kể toán hạng còn lại nằm đâu trong miền kiểu tương ứng:

```java
int zero = Math.multiplyExact(Integer.MAX_VALUE, 0); // 0
```

### Chọn `long` và hiểu đúng mục tiêu

```java
long largeProduct = Math.multiplyExact(100_000L, 100_000);
// 10000000000
```

Chỉ nâng lên `long` khi miền giá trị dự kiến thực sự phù hợp với `long`. Nếu tích có thể vượt 64 bit, cân nhắc `BigInteger`; không có overload `Math.multiplyExact(BigInteger, BigInteger)`.

## 6. Lỗi tinh vi: phép toán đã tràn trước khi đến `Exact`

Giả sử viết:

```java
int alreadyOverflowed = Integer.MAX_VALUE + 1; // -2147483648
int undetected = Math.addExact(alreadyOverflowed, 0);
// -2147483648: không có overflow mới trong phép addExact này
```

`Math.addExact` nhận đầu vào thực tế là `-2147483648` và `0`; bản thân phép cộng đó hợp lệ. Method không biết giá trị âm là kết quả của một phép tính bị tràn trước đó.

Một trường hợp sai khác:

```java
long wrong = Math.addExact(Integer.MAX_VALUE + 1, 0L);
// (-2147483648) + 0L -> -2147483648L: không báo lỗi
```

Phép `Integer.MAX_VALUE + 1` được đánh giá bằng `int` **trước** khi chuyển thành đối số `long`, nên đã tràn. Cách đúng:

```java
long correct = Math.addExact((long) Integer.MAX_VALUE + 1, 0L);
// 2147483648L
```

Hoặc ngắn hơn `Math.addExact((long) Integer.MAX_VALUE, 1L)`.

Tương tự, **không bọc một biểu thức đã cộng/nhân thông thường vào phương thức `Exact` rồi kỳ vọng nó kiểm tra toàn bộ chuỗi tính toán**:

```java
int a = 2_000_000_000;
int b = 2_000_000_000;
int result = Math.addExact(a + b, 0); // a + b đã tràn!
```

Nếu cần kiểm tra ngay phép cộng của `a` và `b`, phải viết `Math.addExact(a, b)`. Nếu cần nhiều bước đều được kiểm tra, dùng method tương ứng **ở từng bước**.

## 7. Xử lý `ArithmeticException` và thiết kế nghiệp vụ

### Bắt lỗi tại ranh giới phù hợp

`ArithmeticException` là *unchecked exception* (thuộc `RuntimeException`); Java không bắt buộc khai báo `throws` hay `catch`. Tuy nhiên với phép tính quan trọng, ứng dụng nên xác định cách xử lý:

```java
try {
    int updated = Math.addExact(Integer.MAX_VALUE, 1);
    System.out.println(updated);
} catch (ArithmeticException ex) {
    System.out.println("overflow detected");
}
```

Kết quả là một dòng `overflow detected`. Không nên dựa vào **chuỗi thông báo chi tiết của exception** để quyết định nghiệp vụ; chỉ nên dựa vào kiểu lỗi và bối cảnh.

Nếu lỗi tràn là dữ liệu đầu vào không hợp lệ, tầng nghiệp vụ có thể chuyển nó thành thông báo phù hợp hoặc từ chối yêu cầu. Nếu lỗi biểu thị vi phạm bất biến nội bộ, có thể để lỗi lan tới cơ chế xử lý tập trung và ghi log đúng mức độ.

### Đừng biến lỗi tràn thành giá trị hợp lệ giả

Những cách xử lý như `catch (ArithmeticException ex) { return 0; }` rất nguy hiểm nếu `0` cũng là kết quả hợp lệ: ta sẽ không còn phân biệt “không có gì” với “tính toán vượt miền”.

Chọn rõ chính sách khi tràn:

| Chính sách | Cách thực hiện | Khi nào phù hợp |
| --- | --- | --- |
| Từ chối phép tính | Gọi method `Exact`, chuyển lỗi tại biên nhập dữ liệu | Miền dữ liệu có giới hạn nghiêm ngặt |
| Tăng miền biểu diễn | Chọn phép toán `long` ngay trước khi tính | Đầu vào `int` nhưng kết quả có thể vượt `int` |
| Dùng số nguyên không giới hạn độ rộng cố định | `BigInteger` và các method `add`, `subtract`, `multiply` | Độ lớn có thể vượt cả `long` |
| Bão hòa ở giá trị biên (*saturating*) | Tự xây dựng chính sách với xử lý rõ ràng | Chỉ khi đặc tả nghiệp vụ yêu cầu clamp ở min/max |
| Cho phép quay vòng (*wraparound*) | Toán tử số nguyên thường | Chỉ khi mục đích là số học modulo/bit pattern |

Ba method `Exact` không tự thực hiện *clamping*, không trả `Optional`, và không hỗ trợ phép toán trên số thực `float`/`double` theo cùng bộ API.

## 8. So sánh `Exact` với `long` và `BigInteger`

Ba chiến lược giải quyết **ba nhu cầu khác nhau**:

- **`Math.*Exact`:** giữ kiểu `int`/`long`, nhưng phát hiện khi kết quả vượt giới hạn của chính kiểu đó.
- **`long`:** cho miền biểu diễn lớn hơn `int`; vẫn có thể tràn và vẫn cần `Math.*Exact` nếu muốn phát hiện tràn `long`.
- **`BigInteger`:** biểu diễn số nguyên độ lớn tùy ý trong giới hạn bộ nhớ; method cộng, trừ, nhân không bị giới hạn 32/64 bit. `BigInteger` bất biến, nên phép toán trả object mới.

Ví dụ:

```java
long product = Math.multiplyExact(100_000L, 100_000); // 10000000000L

java.math.BigInteger huge = java.math.BigInteger.valueOf(Long.MAX_VALUE)
        .multiply(java.math.BigInteger.TWO); // hơn miền long
```

`BigInteger.TWO` có trong Java hiện đại, gồm Java 17. Trong một hệ thống thanh toán thực tế, cần chọn cả **đơn vị đo, kiểu số và chính sách làm tròn**; `Math.*Exact` bảo vệ khỏi một loại lỗi tràn số nguyên nhưng không xác minh mọi quy tắc nghiệp vụ.

Cần phân biệt `Math.toIntExact(long)`: method này kiểm tra **chuyển một giá trị `long` về `int`**, không thực hiện phép cộng/trừ/nhân. Nó hữu ích sau khi chọn tính bằng `long` và muốn từ chối kết quả không vừa `int`.

## 9. Chương trình Java 17+ chạy được: kiểm chứng từng phép toán

Tạo file **`ExactArithmeticDemo.java`**:

```java
public class ExactArithmeticDemo {
    public static void main(String[] args) {
        System.out.println("add=" + Math.addExact(20, 22));
        System.out.println("subtract=" + Math.subtractExact(70, 28));
        System.out.println("multiply=" + Math.multiplyExact(6, 7));
        System.out.println("addMax=" + Math.addExact(Integer.MAX_VALUE - 1, 1));
        System.out.println("subtractMin=" + Math.subtractExact(Integer.MIN_VALUE + 1, 1));
        System.out.println("square=" + Math.multiplyExact(46_340, 46_340));

        System.out.println("uncheckedAdd=" + (Integer.MAX_VALUE + 1));
        System.out.println("uncheckedMultiply=" + (100_000 * 100_000));

        try {
            Math.addExact(Integer.MAX_VALUE, 1);
            System.out.println("checkedAdd=not-detected");
        } catch (ArithmeticException ex) {
            System.out.println("checkedAdd=detected");
        }

        try {
            Math.subtractExact(Integer.MIN_VALUE, 1);
            System.out.println("checkedSubtract=not-detected");
        } catch (ArithmeticException ex) {
            System.out.println("checkedSubtract=detected");
        }

        try {
            Math.multiplyExact(100_000, 100_000);
            System.out.println("checkedMultiply=not-detected");
        } catch (ArithmeticException ex) {
            System.out.println("checkedMultiply=detected");
        }

        long longAdd = Math.addExact((long) Integer.MAX_VALUE, 1L);
        long longMultiply = Math.multiplyExact(100_000L, 100_000);
        System.out.println("longAdd=" + longAdd);
        System.out.println("longMultiply=" + longMultiply);

        int wrapped = Integer.MAX_VALUE + 1;
        System.out.println("priorOverflow=" + Math.addExact(wrapped, 0));

        try {
            Math.multiplyExact(Long.MIN_VALUE, -1L);
            System.out.println("longOverflow=not-detected");
        } catch (ArithmeticException ex) {
            System.out.println("longOverflow=detected");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac ExactArithmeticDemo.java
java ExactArithmeticDemo
```

**Kết quả chuẩn** (chương trình chủ động bắt exception nên vẫn chạy đến hết):

```text
add=42
subtract=42
multiply=42
addMax=2147483647
subtractMin=-2147483648
square=2147395600
uncheckedAdd=-2147483648
uncheckedMultiply=1410065408
checkedAdd=detected
checkedSubtract=detected
checkedMultiply=detected
longAdd=2147483648
longMultiply=10000000000
priorOverflow=-2147483648
longOverflow=detected
```

Các dòng `checked*=detected` là kết quả từ khối `catch`, không phải thông báo tùy tiện của JVM. Dòng `priorOverflow` xác nhận sự khác biệt quan trọng: nếu đã tràn trước khi gọi `addExact` thì lần gọi kiểm tra sau đó không thể phát hiện lỗi cũ.

## 10. Tình huống áp dụng thực tế

### Cập nhật số lượng có kiểm soát

Nếu một kho đang có `stock` đơn vị và nhập thêm `received`, sử dụng:

```java
int newStock = Math.addExact(stock, received);
```

Đoạn này nằm trong ngữ cảnh đã khai báo biến `stock`, `received`; chưa phải chương trình độc lập. Khi tràn `int`, method ném `ArithmeticException`. Nếu logic nghiệp vụ không cho số lượng âm, cần **kiểm tra thêm ràng buộc `newStock >= 0`**; `addExact` không tự kiểm tra ràng buộc này.

### Tính tổng giá theo đơn vị nguyên

Nếu `unitPrice` và `quantity` có kiểu `int`, nhưng tích dự kiến có thể vượt `int`:

```java
long total = Math.multiplyExact((long) unitPrice, quantity);
```

Đây là phép nhân kiểm tra tràn **long**, vì một đối số đã được mở rộng trước khi gọi. Nếu miền kết quả còn lớn hơn `long`, hãy chọn mô hình số phù hợp (ví dụ `BigInteger`) từ đầu.

### Chuỗi phép tính nhiều bước

Ví dụ tính `(price * quantity) - discount` trong miền `long`:

```java
long subtotal = Math.multiplyExact(price, quantity);
long total = Math.subtractExact(subtotal, discount);
```

Ở đây giả định cả ba tham số `price`, `quantity`, `discount` đã được khai báo với kiểu `long`; đoạn code minh họa nằm trong method hiện có. Từng phép tính phải được kiểm tra riêng. Nếu `subtotal` vượt miền, exception xuất hiện ngay ở bước nhân.

**Kiểm tra tràn không thay thế kiểm tra miền nghiệp vụ**: số lượng không âm, giới hạn đơn hàng, phân quyền, tính nhất quán của dữ liệu hoặc quy tắc tiền tệ vẫn cần kiểm tra độc lập.

## 11. Những lỗi phổ biến và checklist

| Hiểu nhầm | Thực tế |
| --- | --- |
| “`long result = Math.addExact(intA, intB);` sẽ cộng theo `long`.” | Nếu hai đối số là `int`, overload `int` được chọn; có thể ném exception trước khi gán vào `long`. |
| “Bọc phép toán đã tính bên trong `addExact` sẽ phát hiện tràn trước đó.” | Không; hãy gọi phép kiểm tra đúng tại bước cần tính. |
| “`multiplyExact` luôn trả `long`.” | `int, int` trả `int`; overload `long` trả `long`. |
| “Có exception nghĩa là JVM dừng tức thì.” | Exception có thể được bắt/được xử lý; nếu không được xử lý, chương trình sẽ thoát theo quy tắc exception. |
| “Tràn chỉ xảy ra lúc cộng số dương.” | Tràn có thể ở cộng, trừ, nhân; với số dương lẫn số âm và ở biên âm/dương. |
| “`Math.addExact` kiểm tra số âm có hợp lệ nghiệp vụ không.” | Không; nó chỉ kiểm tra kết quả toán học có nằm trong phạm vi kiểu hay không. |
| “Chuyển sang `long` là không thể tràn.” | `long` vẫn giới hạn ở 64 bit; có overload `Exact` cho `long`. |
| “`Math.multiplyExact` xử lý `double` và `float`.” | Bộ overload ở đây dành cho số nguyên `int`/`long`, không phải số thực. |
| “Có thể dùng `Math.multiplyExact` trực tiếp với `BigInteger`.” | Không; dùng method `multiply` của `BigInteger`. |

Khi kiểm tra code, hãy trả lời theo trình tự:

1. **Kiểu toán hạng là gì?** Nhìn đối số thực tế, không chỉ biến đích. Nếu cần phép tính `long`, bảo đảm một hoặc các đối số phù hợp đã mang kiểu `long` trước khi tính.
2. **Phép tính nào cần được bảo vệ?** Thay `a + b` bằng `Math.addExact(a, b)` tại đúng bước; tương tự với trừ/nhân.
3. **Kết quả nào nằm ở biên?** Chạm `MAX_VALUE` hoặc `MIN_VALUE` vẫn hợp lệ; vượt biên thì ném `ArithmeticException`.
4. **Nếu exception xảy ra, ai xử lý?** Chọn chính sách nghiệp vụ rõ ràng; không âm thầm dùng giá trị giả có thể bị nhầm là hợp lệ.
5. **Nếu miền biểu diễn không đủ?** Dùng `long` hoặc `BigInteger` tùy nhu cầu, đồng thời tiếp tục kiểm tra quy tắc nghiệp vụ.

**Ghi nhớ:** `Math.addExact`, `Math.subtractExact` và `Math.multiplyExact` cho phép tính số nguyên **có kiểm tra tràn tại chính phép toán đó**. Chúng giúp phát hiện lỗi vốn dễ bị che giấu bởi kết quả quay vòng, nhưng muốn an toàn phải chọn đúng overload, bảo vệ mọi bước trung gian và xử lý `ArithmeticException` theo mục đích của chương trình.