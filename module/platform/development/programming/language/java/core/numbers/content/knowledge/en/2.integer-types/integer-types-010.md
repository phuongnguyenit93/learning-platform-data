# Giới hạn của kiểu cố định so với số nguyên toán học trong Java

## 1. Vấn đề cốt lõi: cùng gọi là “số nguyên” nhưng khác miền giá trị

Trong toán học, tập số nguyên `ℤ = {…, -2, -1, 0, 1, 2, …}` **không có số lớn nhất hoặc nhỏ nhất**. Nếu `a` và `b` là số nguyên, thì `a + b`, `a - b` và `a × b` vẫn là số nguyên toán học; kết quả có thể lớn tùy ý.

Trong Java, `byte`, `short`, `int` và `long` là các **kiểu số nguyên có độ rộng cố định**. Mỗi kiểu chỉ biểu diễn được một tập hữu hạn các giá trị. Phép tính bằng các kiểu này có thể cho kết quả vượt khỏi miền biểu diễn, dù kết quả toán học hoàn toàn hợp lệ.

Ví dụ:

- Toán học: `2_147_483_647 + 1 = 2_147_483_648`.
- Java với `int`: `Integer.MAX_VALUE + 1` có kết quả `-2_147_483_648` do **tràn số nguyên** (*integer overflow*).
- Java với `long`: `(long) Integer.MAX_VALUE + 1` cho đúng kết quả toán học `2_147_483_648`, vì giá trị này còn nằm trong miền `long`.

Đây là giới hạn của **kiểu dữ liệu được chọn và phép toán đang thực hiện**, không có nghĩa phép cộng nguyên trong toán học có điểm kết thúc.

## 2. Miền biểu diễn của từng kiểu nguyên thủy

Java định nghĩa độ rộng giá trị và miền của các kiểu số nguyên, độc lập với cách máy tính cụ thể sắp xếp bộ nhớ:

| Kiểu | Độ rộng | Miền giá trị | Ghi chú |
| --- | ---: | --- | --- |
| `byte` | 8 bit | `-128` đến `127` | Có dấu. |
| `short` | 16 bit | `-32_768` đến `32_767` | Có dấu. |
| `int` | 32 bit | `-2_147_483_648` đến `2_147_483_647` | Kiểu nguyên mặc định của nhiều biểu thức. |
| `long` | 64 bit | `-9_223_372_036_854_775_808` đến `9_223_372_036_854_775_807` | Có dấu; hậu tố literal `L`. |
| `char` | 16 bit | `0` đến `65_535` (`\u0000` đến `\uffff`) | Không dấu, biểu diễn một đơn vị mã UTF-16; thuộc nhóm *integral* trong đặc tả Java. |

Với kiểu số nguyên có dấu độ rộng `w` bit, các giá trị nằm trong khoảng:

```text
MIN = -2^(w - 1)
MAX =  2^(w - 1) - 1
```

Ví dụ `int` có `w = 32`, nên `MIN = -2^31` và `MAX = 2^31 - 1`. Phần âm có nhiều hơn phần dương **một giá trị** vì số `0` chiếm một vị trí ở phía không âm.

**Lưu ý phân loại:** `char` là kiểu *integral* nhưng không phải kiểu số nguyên có dấu. `boolean` hoàn toàn không phải kiểu số. Trong bài này, các quy tắc tràn số tập trung vào `byte`, `short`, `int` và `long`, đồng thời nhắc đến `char` khi cần hiểu chuyển kiểu.

Các hằng `Byte.MIN_VALUE`, `Short.MAX_VALUE`, `Integer.MIN_VALUE`, `Long.MAX_VALUE` giúp truy cập giới hạn của từng kiểu mà không phải tự gõ các số dài.

## 3. Tại sao phép toán Java có thể “quay vòng” giá trị?

Hãy hình dung mỗi độ rộng `w` chỉ có `2^w` mẫu bit có thể biểu diễn. Đối với `int` 32 bit, phép cộng, trừ, nhân thông thường giữ lại kết quả theo modulo `2^32`; mẫu bit cuối cùng được diễn giải thành một giá trị có dấu theo biểu diễn bù hai (*two's complement*).

Với kết quả toán học `r`, có thể hình dung phép tính `int` như sau:

1. Chọn phần dư không âm `u = r mod 2^32`, nằm trong `0 .. 2^32 - 1`.
2. Nếu `u <= 2^31 - 1` thì giá trị `int` là `u`.
3. Nếu `u >= 2^31` thì giá trị `int` là `u - 2^32`.

Bởi vậy:

```text
2147483647 + 1 = 2147483648    (kết quả toán học)
2147483648 mod 4294967296
    = 2147483648                 (mẫu bit 0x80000000)
Đọc dưới dạng int có dấu:
2147483648 - 4294967296
    = -2147483648
```

Dòng code sau **hợp lệ** và cho kết quả âm:

```java
int max = Integer.MAX_VALUE;
int wrapped = max + 1;
System.out.println(wrapped); // -2147483648
```

Java quy định hành vi tràn số trong các phép toán `int`/`long` thông thường; chương trình **không tự ném ngoại lệ** khi cộng, trừ hay nhân bị tràn. Đây là hành vi xác định theo ngôn ngữ, không phải kết quả ngẫu nhiên hoặc *undefined behavior*.

Tính chất “quay vòng” tương tự xảy ra tại giới hạn nhỏ nhất: `Integer.MIN_VALUE - 1` cho `Integer.MAX_VALUE`. Với toán hạng `long`, mô hình tương ứng dùng modulo `2^64`.

### Tràn số không chỉ xuất hiện khi cộng

```java
int a = 50_000;
int b = 50_000;
int wrong = a * b; // -1794967296; kết quả toán học là 2500000000.
```

Lấy `2_500_000_000 - 4_294_967_296 = -1_794_967_296`. Kết quả sai về *ý nghĩa toán học* nếu bạn mong phép nhân giữ nguyên độ chính xác, nhưng vẫn đúng với ngữ nghĩa phép nhân `int` cố định.

Một giới hạn ít thấy hơn là số nhỏ nhất không có số đối nằm trong cùng kiểu:

```java
int min = Integer.MIN_VALUE;
System.out.println(-min);          // -2147483648 (vẫn tràn)
System.out.println(Math.abs(min)); // -2147483648
```

Về toán học, đối của `-2_147_483_648` là `+2_147_483_648`, nhưng `int` không chứa được giá trị dương đó. Vì thế, không được mặc định rằng `Math.abs(x) >= 0` với **mọi** `int`/`long`; trường hợp `MIN_VALUE` là ngoại lệ.

## 4. Kiểu của biểu thức quyết định nơi phép tính diễn ra

Một biến nhận có kiểu rộng hơn **không thể khôi phục** kết quả đã tràn trong biểu thức hẹp.

```java
int x = 50_000;
int y = 50_000;

long tooLate = x * y;          // -1794967296: tính bằng int trước, rồi đổi sang long.
long correct = (long) x * y;   // 2500000000: một toán hạng là long từ trước khi nhân.
long alsoCorrect = x * 50_000L; // 2500000000: literal long.
```

Quy tắc cần nhớ:

- Với nhiều toán tử số nhị phân như `+`, `-`, `*`, `/`, `%`, Java áp dụng *binary numeric promotion*: nếu một toán hạng là `long` (và không có `float`/`double` tham gia) thì tính bằng `long`; nếu không, các toán hạng nguyên hẹp hơn được nâng lên `int`.
- Các phép cộng/nhân trên `byte`, `short`, `char` thông thường cho biểu thức kiểu `int`. Chẳng hạn, `byte r = (byte) (a + b)` cần cast nếu muốn lưu kết quả vào `byte` mà biểu thức không thỏa ngoại lệ gán hằng số khi biên dịch.
- Chuyển đổi **sau phép tính** chỉ đổi kiểu cho kết quả đã tính; muốn nới miền tính toán, chuyển kiểu **một toán hạng trước phép tính**.
- Nếu chính kết quả toán học vượt cả giới hạn `long`, nâng lên `long` vẫn không giải quyết được; cần biểu diễn số nguyên với độ chính xác tùy ý.

### Literal số nguyên cũng có kiểu và giới hạn

```java
long ok = 3_000_000_000L; // Hậu tố L tạo literal long.
// long error = 3_000_000_000; // Lỗi biên dịch: literal thập phân vượt miền int.
```

Ngoài ra, `2147483648` không phải một literal `int` dương hợp lệ trong các ngữ cảnh thông thường; Java có quy tắc cú pháp đặc biệt cho literal xuất hiện ngay sau toán tử một ngôi `-` để viết `-2147483648`. Để dễ đọc và tránh nhầm lẫn trong code thực tế, ưu tiên `Integer.MIN_VALUE`/`Integer.MAX_VALUE` hoặc dùng literal có hậu tố `L` khi cần giá trị lớn.

## 5. Tràn số, chia số nguyên và ép kiểu hẹp là ba việc khác nhau

### 5.1. Phép chia nguyên làm tròn về 0

Khi cả hai toán hạng là số nguyên, phép chia `/` thực hiện chia nguyên và bỏ phần lẻ, **làm tròn về 0**, không cho ra số thực:

```java
System.out.println(7 / 2);   // 3
System.out.println(-7 / 2);  // -3
System.out.println(7 % 2);   // 1
System.out.println(-7 % 2);  // -1
```

Kết quả `7 / 2 = 3` ở đây là do ngữ nghĩa chia nguyên, **không phải** tràn số.

Chia nguyên cho 0 gây `ArithmeticException`. Đặc biệt, `Integer.MIN_VALUE / -1` trả về `Integer.MIN_VALUE`: thương toán học vượt miền `int`, nhưng đặc tả Java quy định trường hợp này **không ném ngoại lệ**. `Long.MIN_VALUE / -1L` tương tự. Khi bài toán cần phát hiện tất cả tràn số, đừng bỏ sót phép chia đặc biệt này.

### 5.2. Ép kiểu hẹp có thể làm mất bit

Chuyển `long` sang `int` có thể bỏ các bit cao, làm thay đổi giá trị:

```java
long large = 2_147_483_648L;
int narrowed = (int) large; // -2147483648
```

Ở đây không có phép cộng bị tràn; **chính chuyển đổi hẹp** làm mất khả năng biểu diễn giá trị ban đầu. Chuyển đổi `int` sang `byte`/`short`/`char` cũng có thể làm mất thông tin.

Ngược lại, nâng từ `int` sang `long` giữ nguyên chính xác mọi giá trị `int` vì toàn bộ miền `int` nằm trong miền `long`. Nhưng nâng lên `float` hoặc `double` là chuyện khác: kiểu dấu phẩy động có thể làm tròn một số nguyên lớn, dù độ lớn của số vẫn nằm trong miền biểu diễn.

### 5.3. Đừng nhầm với vấn đề của floating-point

Đối với `float`/`double`, giới hạn biểu diễn còn liên quan tới số mũ, độ chính xác và `Infinity`/`NaN`. Phép cộng nguyên tràn làm “quay vòng” theo độ rộng cố định; phép toán dấu phẩy động không dùng cùng quy tắc đó. Khi bài toán đòi hỏi đếm chính xác hay tính số nguyên lớn, không nên mặc nhiên đổi sang `double` như cách chữa tràn số.

## 6. Ba chiến lược xử lý theo yêu cầu thực tế

### Chiến lược A — Chọn kiểu nguyên thủy đủ rộng và nâng trước khi tính

Nếu đã chứng minh được kết quả nằm trong miền `long`, dùng `long` cho biểu thức:

```java
int totalUsers = 1_500_000;
int bytesPerUser = 4_096;
long totalBytes = (long) totalUsers * bytesPerUser;
```

Kết quả là `6_144_000_000`, vượt `int` nhưng nằm trong `long`. Cast ở vế phải trước phép nhân là điều quan trọng. Với dữ liệu ngoài dự tính, vẫn phải kiểm tra miền tổng thể nếu kết quả có khả năng vượt `long`.

### Chiến lược B — Dùng phép toán có kiểm tra tràn

Trong Java, lớp `Math` có các phương thức phát hiện tràn cho phép toán phù hợp: `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`, `Math.negateExact`, `Math.incrementExact`, `Math.decrementExact`, cùng `Math.toIntExact` để chuyển `long` xuống `int` có kiểm tra. Những phương thức này ném `ArithmeticException` khi phép toán được kiểm tra không biểu diễn được kết quả.

```java
int oldBalance = Integer.MAX_VALUE;
try {
    int updated = Math.addExact(oldBalance, 1);
    System.out.println(updated);
} catch (ArithmeticException ex) {
    System.out.println("Giá trị int không đủ chứa kết quả");
}
```

Cách này phù hợp nếu **tràn số là lỗi nghiệp vụ**: chẳng hạn số lượng, giới hạn bộ đếm, chỉ số hoặc dữ liệu bắt buộc nằm trong kiểu đã chọn.

Phép `Math.floorDiv` phục vụ quy tắc làm tròn phép chia, **không phải** một cơ chế kiểm tra tất cả các trường hợp tràn. Nếu dùng trực tiếp phép chia và cần tính chính xác, phải xử lý riêng `MIN_VALUE / -1` và phép chia cho 0.

### Chiến lược C — Dùng `BigInteger` khi không biết trước giới hạn

`java.math.BigInteger` lưu số nguyên có độ chính xác tùy ý (*arbitrary precision*). Nó **không phải** kiểu nguyên thủy, có kích thước lưu trữ tăng theo độ lớn và chịu giới hạn bộ nhớ/tài nguyên thực tế, nhưng không bị giới hạn 32 hoặc 64 bit như `int`/`long`.

```java
import java.math.BigInteger;

BigInteger a = BigInteger.valueOf(Long.MAX_VALUE);
BigInteger b = a.add(BigInteger.ONE);
System.out.println(b); // 9223372036854775808
```

`BigInteger` là bất biến (*immutable*): `a.add(...)` trả về một đối tượng kết quả mới, không sửa `a`. Dùng `add`, `subtract`, `multiply`, `divide`, `remainder`, `compareTo` thay cho các toán tử số thông thường.

**Rất quan trọng:** hãy chuyển sang `BigInteger` **trước khi** biểu thức nguyên thủy bị tràn:

```java
long a = Long.MAX_VALUE;
BigInteger correct = BigInteger.valueOf(a).add(BigInteger.ONE);

// Sai mục đích nếu muốn giữ kết quả toán học:
// BigInteger tooLate = BigInteger.valueOf(a + 1); // a + 1 đã tràn long.
```

Tạo số nguyên lớn vượt miền `long` từ chuỗi thập phân bằng `new BigInteger("123456789012345678901234567890")`. Khi quay lại kiểu nguyên thủy, `intValueExact()` và `longValueExact()` giúp phát hiện giá trị vượt miền; `intValue()` và `longValue()` có thể làm mất dữ liệu.

| Nhu cầu | Lựa chọn | Lý do |
| --- | --- | --- |
| Giá trị nhỏ, miền chắc chắn hữu hạn | `int` | Đơn giản, phép toán trực tiếp, hiệu quả. |
| Kết quả có thể vượt `int`, vẫn nằm trong `long` | `long` và nâng trước phép toán | Giữ tính chính xác trong miền 64 bit. |
| Tràn số phải bị phát hiện | Các phương thức `Math.*Exact` hoặc kiểm tra miền chuyên biệt | Báo lỗi thay vì giữ kết quả quay vòng. |
| Số nguyên vượt 64 bit hoặc độ lớn đầu vào không xác định | `BigInteger` | Độ chính xác tùy ý trong giới hạn tài nguyên. |
| Giao thức/thuật toán cố ý dùng phép toán modulo `2^w` | Phép toán nguyên thủy với thiết kế rõ ràng | Kết quả quay vòng có thể là hành vi mong muốn. |

Không có một kiểu đúng cho mọi tình huống: phải xác định **miền dữ liệu đầu vào**, **giới hạn kết quả**, **yêu cầu phát hiện lỗi** và **chi phí tính toán** trước khi lựa chọn.

## 7. Ví dụ hoàn chỉnh Java 17+ có thể chạy

Tạo file **`FixedWidthVsMathInteger.java`**:

```java
import java.math.BigInteger;

public class FixedWidthVsMathInteger {
    public static void main(String[] args) {
        int max = Integer.MAX_VALUE;
        System.out.println("int max = " + max);
        System.out.println("max + 1 as int = " + (max + 1));
        System.out.println("max + 1 as long = " + ((long) max + 1));

        int x = 50_000;
        int y = 50_000;
        long afterOverflow = x * y;
        long beforeOperation = (long) x * y;
        System.out.println("int multiplication then long = " + afterOverflow);
        System.out.println("long multiplication = " + beforeOperation);

        try {
            Math.addExact(max, 1);
        } catch (ArithmeticException ex) {
            System.out.println("Math.addExact detected overflow");
        }

        long large = 2_147_483_648L;
        System.out.println("narrowing long to int = " + (int) large);

        BigInteger beyondLong = BigInteger.valueOf(Long.MAX_VALUE)
                .add(BigInteger.ONE);
        System.out.println("BigInteger beyond long = " + beyondLong);
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp:

```bash
javac FixedWidthVsMathInteger.java
java FixedWidthVsMathInteger
```

Kết quả chuẩn:

```text
int max = 2147483647
max + 1 as int = -2147483648
max + 1 as long = 2147483648
int multiplication then long = -1794967296
long multiplication = 2500000000
Math.addExact detected overflow
narrowing long to int = -2147483648
BigInteger beyond long = 9223372036854775808
```

Đọc ví dụ theo trình tự: `int` quay vòng tại giới hạn; `long` cho phép giữ kết quả khi nâng toán hạng trước phép tính; `Math.addExact` phát hiện tràn; cast hẹp có thể mất dữ liệu; `BigInteger` biểu diễn giá trị vượt cả `long`.

## 8. Các lỗi thường gặp khi so sánh với toán học

1. **Cho rằng “kết quả số nguyên luôn chính xác”.** Điều đó chỉ đúng khi kết quả nằm trong miền kiểu đang tính và không có chuyển kiểu gây mất dữ liệu.
2. **Gán kết quả vào `long` sau phép nhân `int`.** Biểu thức vẫn tính bằng `int`. Hãy chuyển một toán hạng sang `long` từ trước.
3. **Dùng `Math.abs(Integer.MIN_VALUE)` để chắc chắn có số dương.** Biểu thức trả lại giá trị âm nhỏ nhất do không có số đối dương trong `int`.
4. **Tin rằng Java sẽ tự cảnh báo/ném lỗi khi phép cộng số nguyên tràn.** Các toán tử số nguyên thông thường không tự kiểm tra tràn; hãy chọn API `*Exact` nếu cần.
5. **Xem `BigInteger.valueOf(x + y)` như một phép cộng chính xác tùy ý.** Nếu `x + y` thực hiện bằng kiểu nguyên thủy, có thể tràn trước khi vào `BigInteger`.
6. **Dùng `double` để thay số nguyên lớn cần chính xác tuyệt đối.** `double` có số chữ số chính xác hữu hạn nên có thể không phân biệt được các số nguyên lớn liên tiếp.
7. **Xem ép kiểu hẹp và tràn phép toán là cùng một thao tác.** Cả hai có thể thay đổi giá trị, nhưng nguyên nhân và vị trí phát sinh khác nhau; cần kiểm tra riêng.
8. **Giả định mọi phép chia đều giữ lại một số nguyên toán học.** Phép chia nguyên làm tròn về 0; phép chia cho 0 ném ngoại lệ; `MIN_VALUE / -1` là trường hợp đặc biệt vượt miền.

## 9. Cách suy nghĩ khi thiết kế chương trình

Với mỗi phép tính số nguyên, hãy tự hỏi:

- **Phép tính toán học là gì?** Tính được cận trên/cận dưới từ miền đầu vào không?
- **Java thực hiện phép tính ở kiểu nào?** `int`, `long`, hay `BigInteger`? Việc nâng kiểu xảy ra trước hay sau?
- **Kết quả có thể vượt miền không?** Nếu có, ứng dụng cần *báo lỗi*, *đổi sang kiểu rộng hơn*, *dùng độ chính xác tùy ý*, hay *cố ý chấp nhận modulo*?
- **Có bước chuyển kiểu hẹp hay chuyển định dạng nào không?** Chuyển `long` thành `int`, `BigInteger` về kiểu nguyên thủy hoặc chuyển qua số thực cần quy tắc riêng.

**Kết luận:** Số nguyên toán học không bị chặn bởi độ dài biểu diễn; `int` và `long` trong Java có miền hữu hạn. Hãy phân biệt *kết quả toán học* với *giá trị có thể lưu trong kiểu Java*, chọn kiểu trước khi tính, và chủ động kiểm soát tràn số nếu kết quả chính xác là yêu cầu của bài toán.

**Tài liệu đặc tả:** [Java Language Specification §4.2 (Primitive Types and Values)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.2), [§5.1.3 (Narrowing Primitive Conversion)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.3), [§15.17–15.18 (Multiplicative and Additive Operators)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.17), và [Java SE 21 BigInteger API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigInteger.html).
