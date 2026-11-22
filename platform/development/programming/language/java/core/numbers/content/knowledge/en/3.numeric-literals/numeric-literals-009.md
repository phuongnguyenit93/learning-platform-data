# Literal, biểu thức hằng và khác biệt với phân tích `String` trong Java

Khi viết `int n = 42;`, Java đọc `42` trực tiếp như một **literal trong mã nguồn**. Khi viết `int n = Integer.parseInt("42");`, Java nhận một **chuỗi ký tự** rồi thực hiện **phân tích cú pháp lúc chương trình chạy**. Còn `int n = 40 + 2;` là một **biểu thức hằng** mà trình biên dịch có thể đánh giá. Cả ba có thể cho giá trị 42, nhưng cú pháp hợp lệ, thời điểm kiểm tra lỗi, quy tắc ép kiểu và khả năng tràn số khác nhau.

Bài này phân biệt ba cơ chế trong Java 17+ để đọc đúng literal ở các cơ số, hiểu constant expression, và chuyển dữ liệu văn bản thành số an toàn.

## 1. Ba cơ chế, ba thời điểm xử lý

| Cơ chế | Ví dụ | Được xử lý khi nào? | Điểm cần nhớ |
| --- | --- | --- | --- |
| **Literal** trong mã nguồn | `0x2A`, `42L`, `1.5e2` | Trình biên dịch phân tích cú pháp mã nguồn | Tiền tố/hậu tố là cú pháp ngôn ngữ, không phải ký tự lưu trong giá trị |
| **Biểu thức hằng lúc biên dịch** (*constant expression*) | `20 + 22`, `3 * (4 + 2)` | Giá trị được xác định theo quy tắc JLS lúc biên dịch | Chỉ một tập toán tử, literal và biến hằng hợp lệ; lời gọi phương thức thông thường không thuộc tập này |
| **Phân tích `String` thành số** | `Integer.parseInt("42")` | Lúc chạy (runtime) | Phương thức nhận chuỗi, radix và quy tắc parser riêng; đầu vào sai có thể ném `NumberFormatException` |

Một số ví dụ cùng kết quả:

```java
int fromLiteral = 42;
int fromExpression = 40 + 2;
int fromText = Integer.parseInt("42");
```

Dòng thứ nhất và thứ hai có thể được kiểm tra và xác định mà không cần dữ liệu runtime. Dòng thứ ba **cần gọi phương thức** ngay cả khi đối số là chuỗi literal. `"42"` là literal kiểu `String`, **không phải** literal số nguyên.

> **Cách phân biệt nhanh:** dấu ngoặc kép tạo `String`; tiền tố `0x`, `0b`, hậu tố `L`/`F` và dấu gạch dưới trong numeric literal tuân theo luật của mã nguồn. Không nên giả định rằng parser cho `String` sẽ chấp nhận tất cả cú pháp literal.

## 2. Literal số nguyên: cơ số, dấu, kiểu và giới hạn

### 2.1. Các cách viết cùng một giá trị

```java
int decimal = 42;       // Cơ số 10
int binary  = 0b101010; // Cơ số 2
int octal   = 052;      // Cơ số 8
int hex     = 0x2A;     // Cơ số 16
```

Bốn biến đều có giá trị toán học **42**. Cơ số chỉ ảnh hưởng **cách viết trong mã nguồn**. Sau khi biên dịch, toán tử cộng/trừ/so sánh làm việc trên giá trị và kiểu, không mang theo “cơ số gốc”. Muốn hiển thị lại ở cơ số khác, dùng `Integer.toBinaryString`, `Integer.toOctalString`, `Integer.toHexString` hoặc `Integer.toString(value, radix)`.

| Cách viết literal | Cơ số | Giá trị thập phân | Ghi chú |
| --- | ---: | ---: | --- |
| `10` | 10 | 10 | Dạng thông thường |
| `0b1010` hoặc `0B1010` | 2 | 10 | Chỉ chữ số `0` và `1` |
| `012` | 8 | 10 | Bắt đầu bằng `0`; rất dễ nhầm với số thập phân |
| `0xA` hoặc `0XA` | 16 | 10 | Các chữ số `0-9` và `a-f`/`A-F` |
| `10L` | 10 | 10 | Literal kiểu `long` |

**Bẫy số 0 đứng đầu:** trong mã Java, `010` là **số bát phân 8**, còn chuỗi `"010"` không mang cơ số cố định; parser quyết định ý nghĩa của chuỗi (xem phần 4). Literal `08` hoặc `09` là lỗi biên dịch, vì 8 và 9 không thuộc cơ số 8.

### 2.2. Literal `int` và `long`

Literal nguyên thập phân không có hậu tố `L` dùng kiểu `int`, nếu nằm trong miền cho phép (ngoại lệ cú pháp đặc biệt cho `-2147483648`). Hậu tố `L` hoặc `l` cho kiểu `long`; nên viết `L` để không nhầm chữ `l` với số `1`.

```java
int count = 2_000_000;
long largeCount = 3_000_000_000L;

// long invalid = 3_000_000_000; // Lỗi biên dịch: literal thập phân vượt int.
// long alsoValid = 3_000_000_000L;
```

Với số nguyên, viết `-42` là **toán tử dấu âm** đặt trước literal `42`, chứ dấu âm không phải ký tự bên trong numeric literal. Java có quy tắc riêng để viết giá trị tối thiểu:

```java
int minInt = -2147483648;
long minLong = -9223372036854775808L;
```

Trong ngữ cảnh đó, literal thập phân dương có độ lớn bằng `2^31` (hoặc `2^63` với `L`) chỉ hợp lệ làm toán hạng của unary minus theo quy tắc ngôn ngữ. Không thể dùng cùng chuỗi chữ số thập phân không dấu ấy như một giá trị dương kiểu tương ứng.

Với literal hệ 16, 8 và 2, Java cũng cho phép mẫu bit toàn 1 như `0xFFFF_FFFF` làm một `int` có giá trị **−1**. Đừng suy luận rằng một literal chỉ có chữ số hex dương nhất định cho số nguyên có dấu dương: **độ rộng và dấu** của kiểu quyết định cách diễn giải.

### 2.3. Dấu gạch dưới giúp đọc số nhưng không thuộc giá trị

Java cho phép dấu `_` **giữa các chữ số** trong numeric literal:

```java
int population = 1_234_567;
long flags = 0b1111_0000L;
double amount = 1_234.50;
```

Chúng không làm thay đổi giá trị. Dấu gạch dưới **không được** đặt đầu/cuối literal, ngay cạnh dấu chấm thập phân, trước/sau hậu tố kiểu, hoặc ở những vị trí khiến nó không nằm giữa chữ số hợp lệ. Chẳng hạn `1_.0`, `1._0`, `42_L`, `_42` (lúc này được đọc như tên định danh) và `42_` không phải cách viết numeric literal hợp lệ theo ý muốn.

**`"1_234"` là dữ liệu văn bản khác:** dấu gạch dưới có thật trong chuỗi và `Integer.parseInt("1_234")` sẽ ném `NumberFormatException`. Parser không tự hiểu quy tắc trình bày numeric literal của trình biên dịch.

## 3. Literal dấu phẩy động và ảnh hưởng của biểu diễn

`double` là kiểu mặc định cho literal có dấu chấm hoặc số mũ thập phân; hậu tố `f`/`F` chọn `float`; `d`/`D` có thể ghi rõ `double`:

```java
double a = 1.5;
double b = 15e-1;
double c = 1.5D;
float d = 1.5f;
double e = 0x1.8p1; // Literal floating-point hệ 16: 1.5 * 2^1 = 3.0.
```

Literal floating-point hệ 16 bắt đầu bằng `0x` và dùng số mũ `p`/`P` theo lũy thừa của **2**, ví dụ `0x1.8p1` bằng 3.0. Ký hiệu này hữu ích khi cần mô tả chính xác các bit/chữ số nhị phân; số mũ `e` dành cho literal floating-point thập phân.

`0.1` trong mã là literal `double` nhưng giá trị toán học 1/10 không có biểu diễn hữu hạn ở binary64; giá trị lưu là số nhị phân gần nhất. Việc biểu thức `0.1 + 0.2` có kết quả in ra `0.30000000000000004` là vấn đề **biểu diễn chấm động**, khác với vấn đề parser chấp nhận cú pháp chuỗi nào.

Không có numeric literal Java tương ứng trực tiếp với ký hiệu `NaN` hoặc `Infinity`; dùng `Double.NaN` và `Double.POSITIVE_INFINITY`. Ngược lại, `Double.parseDouble("NaN")` hoặc `Double.parseDouble("Infinity")` có thể phân tích các chuỗi đặc biệt đó. Bởi vậy, tập văn bản parser chấp nhận không hoàn toàn trùng tập numeric literal của ngôn ngữ.

Nếu cần phép tính thập phân chính xác theo văn bản đầu vào, cân nhắc `BigDecimal` từ chuỗi: `new BigDecimal("0.1")` giữ đúng 0.1 thập phân; `new BigDecimal(0.1)` nhận xấp xỉ đã nằm trong `double` và có thể tạo số thập phân dài ngoài ý muốn.

## 4. Phân tích `String`: radix, tiền tố, dấu và ngoại lệ

### 4.1. `parseInt` dùng cơ số 10 theo mặc định

```java
int a = Integer.parseInt("42");      // 42
int b = Integer.parseInt("+42");     // 42
int c = Integer.parseInt("-42");     // -42
int d = Integer.parseInt("010");     // 10, không phải octal.
int e = Integer.parseInt("FF", 16);  // 255
int f = Integer.parseInt("1010", 2); // 10
```

`Integer.parseInt(String)` phân tích **cơ số 10**; `Integer.parseInt(String, int radix)` dùng cơ số chỉ định trong khoảng `Character.MIN_RADIX` (2) đến `Character.MAX_RADIX` (36). Cơ số 16 chấp nhận ký tự chữ số hex mà không yêu cầu `0x`. Với cơ số lớn hơn 10, chữ cái biểu diễn các chữ số có giá trị từ 10 trở lên.

**Các trường hợp dễ nhầm:**

| Đầu vào và API | Kết quả |
| --- | --- |
| `Integer.parseInt("010")` | 10 (decimal) |
| `Integer.parseInt("010", 8)` | 8 (octal) |
| `Integer.parseInt("FF", 16)` | 255 |
| `Integer.parseInt("0xFF")` | `NumberFormatException` |
| `Integer.parseInt("0xFF", 16)` | `NumberFormatException` do tiền tố `0x` không hợp lệ với `parseInt` |
| `Integer.parseInt("1_000")` | `NumberFormatException` |
| `Integer.parseInt(" 42 ")` | `NumberFormatException` vì có khoảng trắng |
| `Integer.parseInt("2147483648")` | `NumberFormatException` vì vượt miền `int` |
| `Long.parseLong("2147483648")` | 2147483648 dưới dạng `long` |

Dấu `+`/`-` là hợp lệ ở đầu chuỗi theo quy tắc parser. Không được lặng lẽ bỏ qua `NumberFormatException`: đó thường là tín hiệu đầu vào không đúng định dạng hoặc vượt giới hạn cho phép.

### 4.2. `Integer.decode` hỗ trợ tiền tố radix, nhưng cần ý thức về số 0 đầu

`Integer.decode(String)` nhận dạng các tiền tố `0x`/`0X`/`#` là hệ 16, số `0` đứng đầu là hệ 8, còn lại là hệ 10. Nó có thể nhận dấu ở **trước** tiền tố. Dạng tương tự tồn tại ở `Long.decode`.

```java
Integer.parseInt("010");    // 10
Integer.decode("010");      // 8
Integer.decode("0xFF");     // 255
Integer.decode("#FF");      // 255
Integer.decode("-0xA");     // -10
```

**Không dùng `decode` bừa bãi cho mã số từ người dùng** nếu định dạng nghiệp vụ luôn là thập phân, vì chuỗi `"010"` có thể chỉ là mã hoặc số 10 mà lại bị hiểu thành octal 8. Hãy quyết định radix của dữ liệu bằng **hợp đồng đầu vào**, không dựa vào sự tiện lợi của parser.

### 4.3. Các parser khác có hợp đồng khác

- `Long.parseLong(String)`/`Long.parseLong(String, radix)`: giống hướng xử lý của `Integer.parseInt`, nhưng miền `long` lớn hơn; không tự nhận `0x` khi dùng `parseLong`.
- `Integer.parseUnsignedInt(String)`: phân tích số nguyên **không dấu 32 bit** trong miền 0 đến 4.294.967.295 nhưng trả về mẫu bit kiểu `int`. Dùng `Integer.toUnsignedLong` hoặc `Integer.toUnsignedString` để thao tác/hiển thị theo nghĩa không dấu; Java vẫn không có primitive `unsigned int` riêng.
- `Double.parseDouble(String)` và `Float.parseFloat(String)`: cho cú pháp dấu phẩy động, số mũ, các dạng hex floating-point, và một số chuỗi đặc biệt như `NaN`/`Infinity`. Chúng không áp dụng dấu gạch dưới dùng riêng cho numeric literal trong mã nguồn.
- `new BigInteger(String, radix)`: phân tích số nguyên độ lớn tùy ý trong radix chỉ định; `new BigDecimal(String)`: phân tích số thập phân chính xác theo cú pháp `BigDecimal`. Không tự động cho rằng chúng hiểu mọi tiền tố Java literal hoặc mọi ký tự phân nhóm địa phương.

Với dữ liệu nhập từ người dùng, `parseInt` không loại bỏ khoảng trắng; có thể dùng `strip()` một cách **chủ động** khi hợp đồng cho phép. `Double.parseDouble` xử lý một số khoảng trắng theo quy tắc riêng của nó, nên không nên dựa vào hành vi whitespace giống nhau giữa tất cả parser. Quy định rõ có cho phép khoảng trắng, dấu `+` và chữ số ngoài ASCII hay không; đối với nguồn cần chuẩn hóa chặt (API, mã định danh), có thể kiểm tra cú pháp trước khi parse.

### 4.4. Cơ số khi chuyển số thành chuỗi

```java
int number = 255;
String hex = Integer.toString(number, 16);  // "ff"
String binary = Integer.toBinaryString(number); // "11111111"
int restored = Integer.parseInt(hex, 16);   // 255
```

`Integer.toHexString`/`toBinaryString` có hành vi dựa trên biểu diễn bit đối với số âm; ví dụ `Integer.toHexString(-1)` tạo `"ffffffff"`. Chuỗi đó có ý nghĩa là 4.294.967.295 nếu diễn giải số **không dấu 32 bit**, nên `Integer.parseInt("ffffffff", 16)` ném `NumberFormatException` vì vượt `Integer.MAX_VALUE`. Để khôi phục bit theo nghĩa không dấu, dùng `Integer.parseUnsignedInt("ffffffff", 16)` hoặc logic tương ứng với yêu cầu.

## 5. Biểu thức hằng lúc biên dịch là gì?

**Compile-time constant expression** là biểu thức mà Java Language Specification cho phép xác định giá trị trong lúc biên dịch, dựa trên literal, một số toán tử và **constant variable**. Không phải biểu thức nào có kết quả luôn giống nhau cũng là constant expression theo định nghĩa ngôn ngữ.

Ví dụ:

```java
int a = 2 * (3 + 4);             // Constant expression: 14.
String label = "Java " + "17";  // Ghép chuỗi constant expression.

final int base = 10;
int b = base + 4;                // base là constant variable, b = 14.

int c = Integer.parseInt("14"); // Gọi phương thức tại runtime: không phải constant expression.
int d = Math.abs(-14);          // Gọi phương thức: không phải constant expression.
```

Một **constant variable** là biến `final` kiểu primitive hoặc `String` và được khởi tạo bằng constant expression. Biến `final` không đương nhiên là constant variable:

```java
final int fixed = 20;                    // Constant variable.
final int parsed = Integer.parseInt("20"); // final nhưng không phải constant variable.
final Integer boxed = 20;               // Wrapper Integer không là constant variable.
```

Dù lập trình viên nhìn thấy `Integer.parseInt("20")` luôn trả 20 trong trường hợp này, **lời gọi phương thức không được phép** trong compile-time constant expression theo quy tắc của Java. “Compiler có thể tối ưu code” cũng không đồng nghĩa với “ngôn ngữ coi biểu thức đó là hằng lúc biên dịch”.

### 5.1. Thu hẹp kiểu đối với biểu thức hằng

Java cho phép một số phép chuyển từ constant expression kiểu `int` sang `byte`, `short` hoặc `char` **không cần cast**, nếu giá trị xác định tại biên dịch nằm trong miền đích:

```java
byte total = 100 + 20; // Hợp lệ: hằng 120 vừa byte.
char letter = 65;      // Hợp lệ: giá trị 65 vừa char.

final int offset = 20;
byte alsoFine = 100 + offset; // Hợp lệ: constant variable.

int runtimeOffset = 20;
// byte notAllowed = 100 + runtimeOffset; // Lỗi biên dịch: biểu thức int không hằng.
// byte tooBig = 100 + 30;               // Lỗi biên dịch: 130 không vừa byte.
```

Dạng thường gặp gây thắc mắc:

```java
byte x = 10;
byte y = 20;
// byte z = x + y; // Lỗi: phép cộng số nguyên promote các toán hạng byte lên int.
int z = x + y;     // Hợp lệ.
```

Việc hai biến `byte` chứa giá trị nhỏ **không khiến phép `x + y` có kiểu `byte`**. Trình biên dịch kiểm tra **kiểu của biểu thức** và quy tắc chuyển đổi, không chỉ kiểm tra giá trị có vẻ nhỏ tại thời điểm đọc mã.

### 5.2. Hằng ở `case` và annotation

Với dạng `switch` theo số nguyên (Java 17), nhãn `case` phải là constant expression phù hợp:

```java
final int code = 10;
int input = 11;
switch (input) {
    case code + 1 -> System.out.println("matched"); // Hợp lệ.
    default -> System.out.println("other");
}

// case Integer.parseInt("11") -> ... // Không hợp lệ: method call không là constant expression.
```

Nhiều phần tử của annotation cũng yêu cầu giá trị dạng compile-time constant (hoặc loại biểu thức đặc biệt phù hợp với kiểu phần tử annotation). Khi cần API runtime thay vì hằng trong source, hãy chuyển logic sang chỗ phù hợp; không thể biến `parseInt` thành constant expression chỉ bằng cách đánh dấu kết quả `final`.

### 5.3. Tràn số xảy ra cả trong biểu thức hằng

Java không tự mở rộng `int` sang `long` vì biến đích là `long`. Một constant expression nguyên tính toán với kiểu `int` có thể tràn, rồi **kết quả đã tràn** mới được gán:

```java
long wrong = 1_000_000 * 3_000;   // -1294967296: nhân int tràn.
long correct = 1_000_000L * 3_000; // 3000000000: nhân long.
```

Vì biểu thức có kiểu `int`, trình biên dịch có thể tính trước kết quả theo quy tắc phép toán `int`, bao gồm tràn; việc biên dịch thành công **không bảo đảm kết quả toán học mong muốn**. `Math.multiplyExact` có thể phát hiện overflow ở phép tính runtime; nếu tích cần kiểu `long`, hãy bảo đảm ít nhất một toán hạng `long` từ **trước phép nhân**.

## 6. Vì sao parser lúc chạy và constant expression cần xử lý lỗi khác nhau?

Các lỗi thuộc hai nhóm khác nhau:

| Tình huống | Giai đoạn/phản ứng | Cách xử lý |
| --- | --- | --- |
| `int x = 0b102;` | Không biên dịch: chữ số không thuộc cơ số 2 | Sửa literal trong mã nguồn |
| `int x = 08;` | Không biên dịch: literal bát phân sai | Dùng `8` nếu muốn thập phân |
| `long x = 3000000000;` | Không biên dịch: literal thập phân không `L` vượt `int` | Thêm `L` |
| `byte b = 130;` | Không biên dịch: constant expression không vừa kiểu | Đổi kiểu/cận trên hoặc xử lý dữ liệu |
| `Integer.parseInt("0xFF")` | Runtime `NumberFormatException` | Đặt radix với chuỗi không có tiền tố, hoặc dùng `decode` có chủ đích |
| `Integer.parseInt("2147483648")` | Runtime `NumberFormatException` do overflow | Dùng `Long.parseLong` nếu miền nghiệp vụ cho phép |
| `Integer.parseInt(userInput)` với chuỗi sai | Runtime `NumberFormatException` | Validate theo hợp đồng, catch ở ranh giới nhập |
| `new BigDecimal("0.1")` | Runtime tạo số thập phân chính xác | Chọn số chữ số/scale và chính sách làm tròn khi cần |

Không thể “bắt” lỗi cú pháp literal trong `try/catch`, vì chương trình còn chưa biên dịch thành công. Ngược lại, phân tích `String` là thao tác runtime nên phải kiểm tra nguồn đầu vào, đặc biệt ở API, CLI, tệp dữ liệu và form nhập liệu.

### 6.1. Parse input có kiểm soát

```java
static int parseNonNegativeCount(String input) {
    if (input == null || !input.matches("[0-9]+")) {
        throw new IllegalArgumentException("Count must contain decimal digits");
    }
    int count = Integer.parseInt(input); // Có thể ném NumberFormatException khi vượt int.
    return count;
}
```

Ví dụ minh họa trên **chủ động giới hạn chữ số ASCII 0–9, không có dấu, không có whitespace**. Regex chấp nhận `"0007"` như số 7; nghiệp vụ có thể cho phép hoặc cấm số 0 đầu. Nếu cần hỗ trợ mọi chữ số Unicode hoặc dấu cộng/trừ, thay đổi kiểm tra theo hợp đồng. Một regex đúng về hình thức **không bảo đảm số nằm trong miền `int`**; vẫn cần xử lý `NumberFormatException` khi overflow.

Không nên tự “làm sạch” tùy tiện bằng cách xóa tất cả dấu `_`, dấu phẩy, dấu chấm hay khoảng trắng: `"1,234"` có thể là số phân nhóm hàng nghìn ở locale này nhưng là dấu thập phân ở locale khác. Đối với số nhập theo locale, dùng định dạng/parsing theo `NumberFormat` và xác định rõ quy tắc locale; đối với giao thức máy, thường nên dùng dạng số chuẩn và radix tường minh.

## 7. Ví dụ Java 17+ chạy độc lập

Lưu tệp dưới tên `LiteralConstantParsingDemo.java`:

```java
import java.math.BigDecimal;

public class LiteralConstantParsingDemo {
    public static void main(String[] args) {
        int binary = 0b101010;
        int octal = 052;
        int hex = 0x2A;
        System.out.println("Three radices: " + binary + ", " + octal + ", " + hex);

        final int base = 10;
        byte folded = 100 + base;
        System.out.println("Constant expression to byte: " + folded);

        System.out.println("Literal 010: " + 010);
        System.out.println("parseInt 010: " + Integer.parseInt("010"));
        System.out.println("decode 010: " + Integer.decode("010"));
        System.out.println("parseInt FF radix 16: " + Integer.parseInt("FF", 16));
        System.out.println("decode 0xFF: " + Integer.decode("0xFF"));

        long wrong = 1_000_000 * 3_000;
        long correct = 1_000_000L * 3_000;
        System.out.println("Overflow before long: " + wrong);
        System.out.println("Long multiplication: " + correct);

        System.out.println("Hex float: " + 0x1.8p1);
        System.out.println("Exact decimal sum: "
                + new BigDecimal("0.1").add(new BigDecimal("0.2")));

        try {
            Integer.parseInt("1_000");
        } catch (NumberFormatException ex) {
            System.out.println("Underscore in parsed String: invalid");
        }

        try {
            Integer.parseInt("2147483648");
        } catch (NumberFormatException ex) {
            System.out.println("Beyond int: invalid");
        }

        System.out.println("Long parser: " + Long.parseLong("2147483648"));
    }
}
```

Chạy trong thư mục chứa tệp với JDK 17 trở lên:

```bash
javac LiteralConstantParsingDemo.java
java LiteralConstantParsingDemo
```

Kết quả:

```text
Three radices: 42, 42, 42
Constant expression to byte: 110
Literal 010: 8
parseInt 010: 10
decode 010: 8
parseInt FF radix 16: 255
decode 0xFF: 255
Overflow before long: -1294967296
Long multiplication: 3000000000
Hex float: 3.0
Exact decimal sum: 0.3
Underscore in parsed String: invalid
Beyond int: invalid
Long parser: 2147483648
```

Ở đây, giá trị 42 từ ba radix literal giống nhau, còn chuỗi `"010"` có thể được hiểu là 10 hoặc 8 tùy parser. `byte folded` hợp lệ nhờ compile-time constant expression. Phép nhân `int` cho kết quả đã tràn khi gán vào `long`; có `L` thì biểu thức dùng `long` ngay từ đầu. Hai ngoại lệ `NumberFormatException` được bắt vì chúng là lỗi **runtime parsing**.

## 8. Checklist khi đọc và viết số trong Java

1. **Số được viết trong mã hay đến từ dữ liệu ngoài?** Nếu nằm trong mã Java, dùng quy tắc literal. Nếu nhận chuỗi, dùng parser có hợp đồng rõ.
2. **Radix có rõ ràng không?** Literal `0b`/`0x` hoặc số 0 đầu có ý nghĩa trong source; `parseInt` mặc định decimal, `decode` có tiền tố và octal. Chọn parser theo định dạng dữ liệu.
3. **Cú pháp có phụ thuộc biên dịch?** Dấu `_`, hậu tố `L`/`F`, literal hex float là một phần ngữ pháp mã nguồn; chuỗi parser chấp nhận theo luật riêng.
4. **Đây có thật là compile-time constant expression?** Literal và phép toán cho phép có thể là hằng; lời gọi `parseInt` không phải hằng dù argument là `"42"`. `final` chỉ là một điều kiện cần cho constant variable.
5. **Miền giá trị và kiểu phép toán có phù hợp?** Dùng `L` khi số literal thập phân lớn hoặc phép toán cần `long`; đừng gán sau khi biểu thức `int` tràn.
6. **Đầu vào runtime sai sẽ được xử lý ở đâu?** Quy định dấu, whitespace, radix, nhóm chữ số, locale và cách báo lỗi. Bắt `NumberFormatException` tại ranh giới nhận dữ liệu; không che giấu lỗi bằng giá trị mặc định không được thiết kế.
7. **Có cần decimal chính xác hay số nguyên vượt `long` không?** Dùng `BigDecimal(String)`/`BigInteger` theo hợp đồng dữ liệu thay vì cố gắng ép mọi thứ qua `double` hoặc `int`.

### Câu hỏi tự kiểm tra

- Tại sao `010` trong Java có giá trị 8 nhưng `Integer.parseInt("010")` có giá trị 10? `Integer.decode("010")` cho giá trị nào?
- Tại sao `byte b = 100 + 20;` biên dịch, nhưng `int x = 20; byte b = 100 + x;` lại không?
- Tại sao `final int x = Integer.parseInt("5");` chưa khiến `x` là constant variable theo định nghĩa Java?
- Vì sao `long total = 1_000_000 * 3_000;` cho giá trị khác `long total = 1_000_000L * 3_000;`?
- `"0xFF"` hợp lệ với `Integer.parseInt(..., 16)` hay `Integer.decode(...)`? Đối với API chỉ nhận số thập phân, chọn cách nào để không hiểu nhầm chuỗi `"010"`?
- Vì sao một chuỗi số nhập hợp lệ về **cú pháp** vẫn có thể ném `NumberFormatException`?

**Nguyên tắc áp dụng:** literal thuộc cú pháp Java tại compile time; constant expression là khái niệm hẹp hơn “phép tính luôn cho kết quả như nhau”; parsing `String` là hợp đồng runtime với quy tắc radix, cú pháp và kiểm tra miền riêng. Giữ ba cơ chế tách bạch sẽ tránh lỗi về cơ số, ép kiểu, tràn số và dữ liệu nhập.