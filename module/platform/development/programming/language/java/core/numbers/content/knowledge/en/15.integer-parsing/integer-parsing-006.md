# Vì sao `Integer.parseInt` không xử lý tiền tố `0x` hay dấu gạch dưới như trình biên dịch Java?

Các ký hiệu `0x`, `0b`, `_` giữa chữ số hoặc hậu tố `L` là một phần **cú pháp literal số trong mã nguồn Java**. Chúng được trình biên dịch xử lý khi đọc chương trình. Ngược lại, `Integer.parseInt(String)` là API chạy **lúc runtime**, nhận một chuỗi và chuyển nó thành giá trị `int` theo **quy tắc cú pháp riêng**. Phương thức này **không phải một trình biên dịch Java thu nhỏ**.

```java
int sourceLiteral = 0x2A;                         // 42: Java compiler hiểu 0x.
int sourceUnderscore = 1_000;                     // 1000: Java compiler hiểu _.
int parsedHex = Integer.parseInt("2A", 16);       // 42: radix được truyền riêng.

// Integer.parseInt("0x2A", 16); // NumberFormatException.
// Integer.parseInt("1_000");    // NumberFormatException.
```

**Ý chính:** Những ký tự nằm trong một `String` là **dữ liệu**, không được Java tự quét lại như token của ngôn ngữ. Nếu input dạng `"0x2A"`, bạn phải chọn API hiểu tiền tố ấy, chẳng hạn `Integer.decode`, hoặc tự xác thực và bỏ tiền tố trước khi gọi `parseInt`. Nếu input chứa underscore, phải định nghĩa **quy tắc hợp lệ** rồi chuẩn hóa; không phải mọi cách bỏ underscore đều đúng với cú pháp literal.

## 1. Hai giai đoạn xử lý hoàn toàn khác nhau

### 1.1. Literal trong source: được xử lý trước khi chương trình chạy

Khi Java compiler đọc mã:

```java
int decimal = 42;
int hex = 0x2A;
int binary = 0b101010;
int octal = 052;
int separated = 1_000_000;
```

Nó phân tích **token literal** theo cú pháp ngôn ngữ Java. Các cách viết có thể tạo cùng giá trị số học, nhưng compiler nhận ra cấu trúc: cơ số từ tiền tố hoặc chữ số đầu, vị trí underscore hợp lệ, hậu tố `L`/`l` của kiểu `long`, và miền giá trị. Sau biên dịch, chương trình làm việc với các **giá trị số**, không phải giữ nguyên cú pháp văn bản `0x...` trong biến `int`.

Ví dụ `0x2A` là một **integer literal** hệ 16, `0b101010` là literal hệ 2, `052` là literal hệ 8 vì số 0 đứng đầu, còn `42` là literal thập phân. `1_000_000` dùng dấu gạch dưới để người đọc thấy nhóm chữ số, nhưng dấu này không có giá trị số học.

Không có chuyện một biến `int` tự ghi nhớ rằng nó được khai báo bằng thập phân hay hexadecimal. Cách **hiển thị** kết quả lại là quyết định khác, ví dụ `Integer.toString(value)` hay `Integer.toHexString(value)`.

### 1.2. `String` lúc runtime: được parser xử lý theo hợp đồng của parser

```java
String text = "0x2A";
String other = "1_000";

// Đặt trong dấu ngoặc kép: đây là nội dung String, không phải integer literal.
```

Compiler chỉ nhận ra đây là các **string literal**. Nó tạo giá trị chuỗi, **không phân tích nội dung bên trong thành token số Java**. Khi `Integer.parseInt(text)` được gọi, JVM đã ở runtime; phương thức kiểm tra ký tự theo cú pháp parser của nó.

Đây là khác biệt nền tảng: cùng chuỗi ký tự nhìn thấy được có thể mang hai ý nghĩa theo hai ngữ cảnh **token của source code** và **dữ liệu chuỗi**.

| Dòng mã / input | Ai xử lý? | Kết quả |
| --- | --- | --- |
| `int x = 0x2A;` | Java compiler | `x == 42` |
| `Integer.parseInt("2A", 16)` | `parseInt` tại runtime | Trả `42` |
| `Integer.parseInt("0x2A", 16)` | `parseInt` tại runtime | Ném `NumberFormatException` |
| `int x = 1_000;` | Java compiler | `x == 1000` |
| `Integer.parseInt("1_000")` | `parseInt` tại runtime | Ném `NumberFormatException` |
| `int x = 010;` | Java compiler | `x == 8` vì literal bát phân |
| `Integer.parseInt("010")` | `parseInt` tại runtime | Trả `10` vì mặc định radix 10 |

Đừng đánh đồng **khác biệt cú pháp** với **khác biệt giá trị**. `0x2A` và `42` tạo cùng `int`; `parseInt` chỉ không chấp nhận toàn bộ cách viết literal như input.

## 2. Hợp đồng thực tế của `Integer.parseInt`

Trong Java SE 17, các overload cốt lõi gồm:

```java
int a = Integer.parseInt("42");      // Mặc định radix = 10.
int b = Integer.parseInt("2A", 16);   // Hex digits, radix = 16.
int c = Integer.parseInt("101010", 2); // Binary digits, radix = 2.
int d = Integer.parseInt("-2A", 16);  // -42, dấu trừ được phép.
```

`Integer.parseInt(String s, int radix)` nhận:

1. Một dấu ASCII `+` hoặc `-` **ở đầu**, tùy chọn.
2. Theo sau là ít nhất một chữ số hợp lệ với `radix`.
3. Không có các ký tự trang trí như `_`, `0x`, `0b`, hậu tố `L`, khoảng trắng chưa chuẩn hóa.
4. Giá trị số sau dấu phải nằm trong miền `int` có dấu, từ `Integer.MIN_VALUE` đến `Integer.MAX_VALUE`.
5. `radix` trong khoảng `Character.MIN_RADIX` (2) đến `Character.MAX_RADIX` (36).

Một ký tự chữ số được xác định theo `Character.digit(character, radix)`; ngoài `0..9` và các chữ cái tương ứng, Java có thể chấp nhận một số ký tự chữ số Unicode được API `Character` nhận diện. Nếu định dạng đầu vào của ứng dụng **chỉ cho ASCII**, bạn phải đặt ràng buộc riêng; không mặc nhiên coi parser là bộ kiểm tra ASCII.

### Phương thức không đoán cơ số từ chuỗi

```java
System.out.println(Integer.parseInt("010"));     // 10.
System.out.println(Integer.parseInt("010", 10)); // 10.
System.out.println(Integer.parseInt("010", 8));  // 8.
```

Tham số `radix` giải quyết **cơ số**, không phải **tiền tố**. Ví dụ radix 16 nghĩa là ký tự `A` có giá trị 10, chứ không có nghĩa chuỗi được phép bắt đầu bằng `0x`.

```java
System.out.println(Integer.parseInt("FF", 16)); // 255.

// Integer.parseInt("0xFF", 16); // NumberFormatException vì chữ 'x'.
// Integer.parseInt("0b101", 2); // NumberFormatException vì chữ 'b'.
```

Trong `"0xFF"`, ký tự `0` có thể là chữ số hệ 16, nhưng ký tự `x` không phải chữ số hợp lệ của radix 16. Parser không có quy tắc “xem hai ký tự đầu là prefix rồi bỏ qua”.

### Dấu âm và dấu dương là ngoại lệ được parser nhận biết

```java
System.out.println(Integer.parseInt("-42"));     // -42.
System.out.println(Integer.parseInt("+42"));     // 42.
System.out.println(Integer.parseInt("-2A", 16)); // -42.
```

Việc chấp nhận dấu đầu **không đồng nghĩa** parser chấp nhận toàn bộ cú pháp unary expression Java. `Integer.parseInt("2+3")` không tính biểu thức; `Integer.parseInt("--42")` không hợp lệ; `Integer.parseInt("-0x2A",16)` cũng không hợp lệ do tiền tố `0x` vẫn còn.

### Lỗi được phát hiện lúc runtime

Dữ liệu sai cú pháp hoặc vượt miền làm `parseInt` ném `NumberFormatException`, một lớp con của `IllegalArgumentException`:

```java
// Tất cả đều có lỗi:
Integer.parseInt("1_000");
Integer.parseInt("0x2A");
Integer.parseInt("3.14");
Integer.parseInt("42L");
Integer.parseInt("2147483648");
Integer.parseInt(" 42");
```

Đây là **những lời gọi độc lập được cố ý minh họa lỗi**, không phải đoạn chương trình chạy liên tiếp an toàn. Nếu muốn chương trình tiếp tục, bắt exception ở ranh giới input và báo lỗi có ngữ cảnh.

## 3. Cú pháp dấu gạch dưới trong numeric literal của compiler

Kể từ Java 7, một hoặc nhiều dấu `_` được cho phép **giữa các chữ số** của một literal số với các giới hạn do grammar quy định. Chúng giúp nhìn các nhóm chữ số dễ hơn, không làm đổi giá trị.

```java
int million = 1_000_000;
int flags = 0b1010_0101;
int color = 0xCA_FE;
long big = 9_223_372_036_854_775_807L;
```

Các ví dụ trên đều là **source code Java hợp lệ**. Compiler biết `_` là ký hiệu phân nhóm nên bỏ qua nó khi xác định giá trị.

Tuy nhiên, không phải chuỗi có underscore ở đâu cũng là literal hợp lệ:

```java
// int a = _1000;  // Không phải integer literal hợp lệ; có thể được hiểu như tên.
// int b = 1000_;  // Không hợp lệ: underscore ở cuối chữ số.
// int c = 0x_FF;  // Không hợp lệ: ngay sau prefix, trước chữ số đầu.
// int d = 0b_101; // Không hợp lệ: ngay sau prefix.
// long e = 100_L; // Không hợp lệ: underscore ngay trước hậu tố L.
```

Lưu ý `100__0` **là literal hợp lệ**: Java cho phép nhiều underscore liên tiếp **nằm giữa hai chữ số**. Vì vậy một validator chỉ cho đúng **một** underscore giữa hai nhóm chữ số là một **định dạng input tùy chỉnh**, không hoàn toàn bằng toàn bộ grammar literal Java.

`Integer.parseInt("1_000")` không dùng grammar literal, nên nó sẽ ném `NumberFormatException` ngay cả khi `int n = 1_000;` biên dịch thành công.

### Vì sao không nên cứ `replace("_", "")` vô điều kiện?

```java
String input = "1_000";
int n = Integer.parseInt(input.replace("_", "")); // 1000.
```

Đoạn này **có thể đúng nếu nghiệp vụ đã quy định underscore chỉ được xuất hiện giữa các chữ số hợp lệ**. Nhưng thao tác thay thế mù quáng cũng biến:

```text
_100 -> 100
100_ -> 100
1__0 -> 10
```

Hai ví dụ đầu **không phải cách viết literal số hợp lệ**; ví dụ thứ ba có thể hợp lệ trong source Java nhưng có thể vi phạm **chính sách input hẹp hơn** của ứng dụng. Nếu chỉ dùng `replace` thì tất cả đều được nhận mà không phân biệt cú pháp ban đầu.

**Nguyên tắc:** trước khi chuẩn hóa, **xác thực toàn bộ chuỗi** với một quy tắc rõ ràng. Sau đó mới bỏ underscore và gọi `parseInt`. Không dùng `replace` như bước “sửa lỗi” im lặng để nhận input chưa được kiểm tra.

## 4. Phân biệt tiền tố `0x`, `0b` và số 0 đầu

Trong Java source:

| Literal | Cơ số | Giá trị thập phân |
| --- | ---: | ---: |
| `42` | 10 | 42 |
| `0x2A` | 16 | 42 |
| `0X2a` | 16 | 42 |
| `0b101010` | 2 | 42 |
| `0B101010` | 2 | 42 |
| `052` | 8 | 42 |
| `010` | 8 | 8 |
| `000` | 8 | 0 |

Compiler xác định loại literal từ **cú pháp token nguồn**. `Integer.parseInt` thì nhận **radix** truyền vào và các chữ số tương ứng, không suy cơ số theo token source.

```java
System.out.println(Integer.parseInt("052"));    // 52.
System.out.println(Integer.parseInt("052", 8)); // 42.
System.out.println(Integer.parseInt("0b101010", 2)); // Ném NumberFormatException.
```

Dòng cuối là minh họa chủ động một trường hợp ném exception; khi chạy chương trình thật, không gọi trực tiếp nếu muốn các dòng sau vẫn thực thi.

### Bẫy `010` và `09`

```java
int octalTen = 012;           // 10 decimal.
int octalEight = 010;         // 8 decimal.
int parsed = Integer.parseInt("010"); // 10 decimal.
```

Trong source Java, `09` là literal **không hợp lệ**, vì `9` không phải chữ số bát phân sau tiền tố `0`. Nhưng `Integer.parseInt("09")` trả **9** vì parser mặc định dùng thập phân.

Đây là lý do **không nên mặc định coi chuỗi do người dùng nhập có cùng quy tắc số 0 đầu với mã nguồn Java**. Nhiều hệ thống nhập mã bưu điện, số hóa đơn, chuỗi phiên bản hoặc số điện thoại; có những dữ liệu không nên được parse thành số ngay từ đầu vì số 0 đầu có thể mang ý nghĩa định danh.

## 5. Khi nào nên dùng `Integer.decode`?

Nếu input của ứng dụng **cố ý hỗ trợ một số dạng tiền tố**, JDK có `Integer.decode(String)`:

```java
System.out.println(Integer.decode("42"));    // 42.
System.out.println(Integer.decode("0x2A"));  // 42.
System.out.println(Integer.decode("0X2A"));  // 42.
System.out.println(Integer.decode("#2A"));   // 42.
System.out.println(Integer.decode("052"));   // 42.
System.out.println(Integer.decode("-0x2A")); // -42.
```

`decode` hỗ trợ:
- Không có tiền tố: thập phân.
- `0x` hoặc `0X` hoặc `#`: hệ 16.
- `0` đầu một chuỗi nhiều chữ số: hệ 8.
- Dấu `+` hoặc `-` đầu chuỗi, nếu có.

Nhưng `Integer.decode` **không phải trình phân tích tất cả numeric literals Java**:

```java
// Integer.decode("0b101010"); // NumberFormatException.
// Integer.decode("1_000");    // NumberFormatException.
// Integer.decode("42L");      // NumberFormatException.
// Integer.decode("09");       // NumberFormatException (09 bị hiểu octal).
```

**Đặc biệt:** `decode("09")` bị hiểu là octal và thất bại, khác `parseInt("09")` là 9. Nếu dữ liệu do người dùng nhập thường có số 0 đầu nhưng phải hiểu **hệ 10**, không dùng `decode` như lựa chọn mặc định.

### `decode` và dấu âm trong hệ 16

```java
System.out.println(Integer.decode("-0x2A")); // -42.
```

`decode` hiểu dấu âm trước prefix. `parseInt("-2A",16)` cũng hiểu dấu âm nhưng **không** nhận prefix `0x`. Nếu bạn đã chuẩn hóa input bằng cách tách prefix, hãy giữ dấu ở vị trí hợp lệ.

### API liên quan tới kiểu lớn

- `Long.parseLong(text, radix)` và `Long.decode(text)` tương ứng dành cho `long`.
- `Byte.decode(text)` và `Short.decode(text)` có hỗ trợ cú pháp prefix tương tự, nhưng miền giá trị hẹp hơn.
- `new BigInteger(text, radix)` cho phép số nguyên nhiều chữ số hơn `long`, nhưng input radix vẫn cần xử lý tiền tố theo hợp đồng của constructor.
- `Integer.parseUnsignedInt(text, radix)` dành cho giá trị **không dấu 32 bit** theo diễn giải `int` không dấu, không tự nhận `0x` hoặc `_`.

Hãy chọn API theo **miền giá trị và định dạng đầu vào**, không chỉ theo tên phương thức.

## 6. Bẫy nâng cao: literal hexadecimal và giới hạn `int` có dấu

Một khác biệt khác không giải quyết chỉ bằng việc bỏ `0x` và underscore: **quy tắc về số nguyên không dấu trong cú pháp literal hệ 16 và parser số nguyên có dấu**.

```java
int allBitsSet = 0xFFFF_FFFF; // Hợp lệ; giá trị int là -1.
System.out.println(allBitsSet); // -1.
```

`0xFFFF_FFFF` viết dưới dạng literal hệ 16 biểu diễn mẫu bit 32 bit toàn `1`. Giá trị `int` có dấu tương ứng là **−1**.

Nếu dùng parser `int` có dấu:

```java
// Integer.parseInt("FFFFFFFF", 16); // NumberFormatException:
// 4294967295 > Integer.MAX_VALUE.
```

`Integer.parseInt` không mặc định xem chuỗi như mẫu bit không dấu 32 bit. Nếu dữ liệu của bạn **định nghĩa hex là biểu diễn unsigned 32-bit**, dùng:

```java
int bits = Integer.parseUnsignedInt("FFFFFFFF", 16);
System.out.println(bits);                          // -1 (xem như signed int).
System.out.println(Integer.toUnsignedString(bits)); // 4294967295.
```

`parseUnsignedInt` trả về kiểu `int` do Java không có kiểu `uint` primitive, nhưng có thể diễn giải bit theo unsigned khi dùng `Integer.toUnsignedString`, `Integer.compareUnsigned`, `Integer.divideUnsigned`...

**Đừng đánh đồng ba ý nghĩa khác nhau:**
1. Số nguyên signed có giá trị trong `[-2^31, 2^31-1]`.
2. Mẫu bit 32 bit, có thể được in theo hệ 16.
3. Giá trị unsigned 32 bit trong `[0, 2^32-1]`.

`parseInt` xử lý trường hợp 1; `parseUnsignedInt` hỗ trợ trường hợp 3 và trả lại cùng mẫu bit trong `int`. Compiler xử lý literal số có quy tắc riêng cho trường hợp 2. `Integer.decode("0xFFFFFFFF")` cũng không phải giải pháp cho ý định unsigned 32 bit; nó dùng giới hạn có dấu.

### Không lẫn dấu trừ với literal âm

Trong ngữ pháp Java, một dấu `-` trước numeric literal về bản chất là **toán tử unary minus**, ngoại trừ cách compiler quy định riêng cho giá trị min của kiểu nguyên. `-0x2A` trong source có nghĩa lấy âm của literal 42. `Integer.parseInt("-2A",16)` thì coi dấu âm là một phần cú pháp string đầu vào. Hai đường dẫn có thể cho cùng giá trị nhưng không dùng cùng cơ chế.

Nếu cần parse các biểu thức như `"-0x2A"`, `"1 + 2"`, `"(0b101) << 3"`, bạn đang thiết kế **ngôn ngữ/biểu thức đầu vào** chứ không chỉ parse một số nguyên. Không đưa toàn bộ input không tin cậy vào trình chạy mã Java.

## 7. Kiểm tra lỗi đầu vào: cú pháp, radix và overflow

`Integer.parseInt` thường ném `NumberFormatException` nếu:

- Chuỗi rỗng, không có chữ số sau dấu, hoặc chữ số không hợp lệ với radix.
- Gặp tiền tố `0x`/`0b` hay underscore không được hợp đồng `parseInt` hỗ trợ.
- Gặp khoảng trắng trước/sau hoặc ký tự thừa không được xử lý trước.
- Giá trị ngoài miền `int` có dấu.
- Radix ngoài `2..36`.

```java
// Các lời gọi dưới đây cố ý minh họa lỗi:
Integer.parseInt("");
Integer.parseInt(" 42 ");
Integer.parseInt("12.0");
Integer.parseInt("42L");
Integer.parseInt("999999999999999");
Integer.parseInt("2", 2);
Integer.parseInt("10", 1);
```

Đoạn trên **không phải ví dụ runnable liên tục** vì lệnh đầu đã ném exception. Ví dụ hoàn chỉnh ở phần 11 trình bày helper chuyển kết quả thất bại thành chữ `INVALID` để chương trình vẫn chạy hết.

### Vì sao `trim` không giải quyết mọi khác biệt?

`Integer.parseInt(" 42 ")` thất bại, trong khi `Integer.parseInt(" 42 ".trim())` trả 42. Đây là **chính sách chuẩn hóa khoảng trắng** do ứng dụng chọn. Nhưng `trim` không chuyển `0x` thành chữ số hợp lệ, không xóa underscore và không bỏ hậu tố literal; nó chỉ xử lý một nhóm ký tự khoảng trắng theo định nghĩa của `String.trim`. `String.strip()` có hành vi Unicode whitespace khác `trim()`.

Nếu dữ liệu cần khớp chính xác với một chuẩn trao đổi, không nên “tự sửa” các chuỗi không hợp lệ mà không thông báo. Một số giao thức yêu cầu từ chối khoảng trắng để tránh vấn đề diễn giải không nhất quán giữa các hệ thống.

### Số 0 đầu có thể mang ý nghĩa của dữ liệu, không phải cú pháp số

Chuỗi `"00042"` đôi khi là một **định danh**. Nếu parse thành `42`, bạn mất ba số 0 đầu. Nếu cần lưu mã dạng này, giữ `String`, kiểm tra độ dài và tập ký tự theo quy tắc mã thay vì dùng `parseInt`.

## 8. Khi ứng dụng muốn cho nhập hex có underscore: xác thực rồi chuẩn hóa

Nếu hợp đồng của hệ thống định nghĩa **chuỗi số hex có prefix `0x` hoặc `0X`**, có thể kèm dấu và underscore phân cách **theo một quy tắc chủ động**, hãy xây parser riêng trước khi gọi `Integer.parseInt`.

Ví dụ bên dưới cố tình chỉ chấp nhận **một hoặc nhiều chữ số hex theo ASCII** với **không quá một underscore giữa hai nhóm chữ số**. Đây là **chính sách input hẹp hơn** grammar Java (Java có thể cho nhiều underscore liên tiếp giữa chữ số).

```java
static int parseHexInput(String input) {
    if (input == null ||
            !input.matches("[+-]?0[xX][0-9a-fA-F]+(?:_[0-9a-fA-F]+)*")) {
        throw new NumberFormatException("Invalid hex input");
    }
    boolean hasSign = input.startsWith("-") || input.startsWith("+");
    String sign = input.startsWith("-") ? "-" : "";
    String digits = input.substring(hasSign ? 3 : 2).replace("_", "");
    return Integer.parseInt(sign + digits, 16);
}
```

Ví dụ:

```java
System.out.println(parseHexInput("0x2A"));  // 42.
System.out.println(parseHexInput("+0x2_A")); // 42.
System.out.println(parseHexInput("-0x2A")); // -42.
// parseHexInput("0x_2A");    // NumberFormatException.
// parseHexInput("0x2__A");   // NumberFormatException theo policy này.
// parseHexInput("0xFFFFFFFF"); // NumberFormatException do vượt miền signed int.
```

**Quan trọng:** phương thức ví dụ không cố mô phỏng hết compiler Java. Nó diễn đạt một **định dạng nhập số hex có dấu, có underscore hạn chế và kết quả signed int**. Nếu cần hỗ trợ hex theo mẫu bit unsigned 32 bit, phải dùng `parseUnsignedInt` và thiết kế lại chính sách dấu; không thể chỉ thay tên phương thức.

Nếu ứng dụng chỉ cần hex đơn giản không underscore, `Integer.decode` đủ tiện và dễ đọc hơn. Nếu chỉ cần các chữ số hex **không có prefix**, `Integer.parseInt(text,16)` trực tiếp là phù hợp nhất.

### Nên dùng regex nào?

Validator có thể chấp nhận:
- Chữ số theo radix và ASCII/Unicode tùy hợp đồng.
- Có hay không prefix, dấu và underscore.
- Có hay không khoảng trắng.
- Miền số signed hay unsigned.

**Không nên cố dùng một regex khổng lồ để bao quát toàn bộ Java numeric literal** nếu nghiệp vụ chỉ cần một kiểu input cụ thể. Càng hỗ trợ nhiều cú pháp, khả năng mơ hồ càng tăng (ví dụ `010` có nên là octal hay decimal?).

## 9. Phân biệt compile-time error và runtime exception

Với mã nguồn Java:

```java
int valid = 0x2A;
int formatted = 1_000;

// int invalid = 0x_2A; // Sai vị trí underscore: lỗi biên dịch.
// int invalidOctal = 09; // Sai digit octal: lỗi biên dịch.
```

Sai cú pháp literal được phát hiện ở **compile time**. Nhưng biểu thức:

```java
String incoming = "0x_2A";
int parsed = Integer.parseInt(incoming, 16);
```

vẫn **biên dịch thành công**, vì compiler chỉ kiểm tra rằng `incoming` là `String` và có overload phù hợp cho `parseInt`. Khi chạy đến lời gọi, parser thấy input không hợp lệ và ném `NumberFormatException`.

Ngay cả input trong một string literal **cố định** như `Integer.parseInt("0x2A",16)` cũng không bị trình biên dịch báo lỗi cú pháp số: nó là lời gọi method hợp lệ về kiểu và sẽ thất bại **lúc chạy**.

Điều này có ý nghĩa khi xử lý dữ liệu từ file CSV/JSON, biến môi trường, giao diện người dùng, request API hoặc command-line arguments. Bạn phải kiểm tra và quản lý lỗi runtime ở **ranh giới tin cậy**, không dựa vào việc mã đã biên dịch.

## 10. Lựa chọn API theo yêu cầu đầu vào

| Input hợp đồng | Ví dụ | API hoặc chiến lược phù hợp |
| --- | --- | --- |
| Chữ số thập phân signed đơn giản | `"123"`, `"-42"` | `Integer.parseInt(text)` |
| Chữ số của radix xác định, **không prefix** | `"2A"` với radix 16 | `Integer.parseInt(text,16)` |
| Tiền tố hex, số 0 đầu kiểu octal theo quy tắc decode | `"0x2A"`, `"052"` | `Integer.decode(text)` |
| Hex có prefix và underscore, signed int | `"0x2_A"` | Validator + bỏ ký tự format + `parseInt` |
| Binary có `0b` prefix | `"0b101010"` | Nhận diện/bỏ prefix có kiểm tra + `parseInt(digits,2)` |
| Số nguyên `long` với miền rộng hơn | `"4294967296"` | `Long.parseLong` hoặc `Long.decode` khi đúng format |
| Số nguyên rất lớn | `"1234567890123456789012345"` | `BigInteger` với radix và normalization rõ |
| Hex như mẫu bit unsigned 32-bit | `"FFFFFFFF"` | `Integer.parseUnsignedInt(...,16)` |
| Các mã giữ số 0 đầu, không thực hiện số học | `"00042"` | Giữ `String`, validate schema |
| Toàn bộ biểu thức số Java có toán tử | `"1 + 0x2A"` | Parser biểu thức chuyên dụng, không dùng `parseInt` |
| Dữ liệu có thể sai hoặc bị tấn công | Input bất kỳ | Validate định dạng, radix, miền; bắt lỗi ở ranh giới |

Một lựa chọn sai hay gặp là **dùng `decode` cho mọi dữ liệu số** chỉ vì nó hiểu `0x`. Nếu input có `"010"` và doanh nghiệp hiểu là mười, `decode` sẽ trả tám. Hãy quyết định **chính sách số 0 đầu** trước khi chọn API.

## 11. Chương trình Java 17+ chạy độc lập

Lưu thành `ParseVsLiteralDemo.java`:

```java
public class ParseVsLiteralDemo {
    static String parse(String text, int radix) {
        try {
            return Integer.toString(Integer.parseInt(text, radix));
        } catch (NumberFormatException ex) {
            return "INVALID";
        }
    }

    static String decode(String text) {
        try {
            return Integer.toString(Integer.decode(text));
        } catch (NumberFormatException ex) {
            return "INVALID";
        }
    }

    public static void main(String[] args) {
        int hex = 0x2A;
        int binary = 0b101010;
        int separated = 1_000_000;
        int octal = 010;
        System.out.println("Literals: " + hex + ", " + binary
                + ", " + separated + ", " + octal);

        System.out.println("parseInt(2A,16): " + parse("2A", 16));
        System.out.println("parseInt(0x2A,16): " + parse("0x2A", 16));
        System.out.println("decode(0x2A): " + decode("0x2A"));

        System.out.println("parseInt(101010,2): " + parse("101010", 2));
        System.out.println("parseInt(0b101010,2): "
                + parse("0b101010", 2));

        System.out.println("parseInt(1_000): " + parse("1_000", 10));
        System.out.println("parseInt(1_000 after removing underscore): "
                + parse("1_000".replace("_", ""), 10));

        System.out.println("parseInt(010): " + parse("010", 10));
        System.out.println("decode(010): " + decode("010"));
        System.out.println("parseInt(09): " + parse("09", 10));
        System.out.println("decode(09): " + decode("09"));

        System.out.println("parseInt(-2A,16): " + parse("-2A", 16));
        System.out.println("decode(-0x2A): " + decode("-0x2A"));
        System.out.println("parseInt(42L): " + parse("42L", 10));
        System.out.println("parseInt(space42): " + parse(" 42", 10));
        System.out.println("parseInt(2147483648): "
                + parse("2147483648", 10));

        int bits = Integer.parseUnsignedInt("FFFFFFFF", 16);
        System.out.println("unsigned bits: " + bits);
        System.out.println("unsigned decimal: "
                + Integer.toUnsignedString(bits));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 ParseVsLiteralDemo.java
java ParseVsLiteralDemo
```

Stdout:

```text
Literals: 42, 42, 1000000, 8
parseInt(2A,16): 42
parseInt(0x2A,16): INVALID
decode(0x2A): 42
parseInt(101010,2): 42
parseInt(0b101010,2): INVALID
parseInt(1_000): INVALID
parseInt(1_000 after removing underscore): 1000
parseInt(010): 10
decode(010): 8
parseInt(09): 9
decode(09): INVALID
parseInt(-2A,16): -42
decode(-0x2A): -42
parseInt(42L): INVALID
parseInt(space42): INVALID
parseInt(2147483648): INVALID
unsigned bits: -1
unsigned decimal: 4294967295
```

Tất cả dòng `INVALID` được tạo bởi helper **cố ý bắt `NumberFormatException`**, không phải một cách diễn đạt cú pháp của `parseInt`. Trong ứng dụng thực tế, lỗi cần chứa ngữ cảnh field/line/input policy và được xử lý phù hợp, thay vì âm thầm biến dữ liệu hỏng thành một số hợp lệ.

Đoạn ví dụ cho thấy đồng thời:
- Compiler nhận `0x`, `0b` và underscore trong numeric literal.
- `parseInt` cần **digits không prefix** và radix tường minh.
- `decode` hiểu một số prefix nhưng có chính sách octal riêng.
- `parseUnsignedInt` diễn giải toàn bộ 32 bit khi input không dấu vượt `Integer.MAX_VALUE`.

## 12. Kiểm thử parser đầu vào theo hợp đồng

Khi xây API nhập số, đừng chỉ kiểm thử các số nhỏ hợp lệ. Tối thiểu cần:

| Nhóm | Ví dụ | Câu hỏi cần trả lời |
| --- | --- | --- |
| Decimal bình thường | `"42"`, `"-42"`, `"+42"` | Có hỗ trợ dấu không? |
| Tiền tố hex | `"0x2A"`, `"0X2A"`, `"#2A"` | Parser nào nhận? |
| Binary có prefix | `"0b1010"` | Có tự bỏ `0b` không? |
| Số 0 đầu | `"010"`, `"09"`, `"00042"` | Hệ 8, 10 hay là định danh? |
| Underscore hợp lệ | `"1_000"`, `"0xCA_FE"` | Có cho phân cách nhóm không? |
| Underscore ở biên | `"_100"`, `"100_"`, `"0x_FF"` | Có bị từ chối không? |
| Underscore lặp | `"1__0"` | Java literal cho phép giữa digits; input policy có cho không? |
| Hậu tố `L` | `"42L"` | Có cần bỏ suffix không, kiểu đích là gì? |
| Khoảng trắng | `" 42 "`, tab, newline | Trim, strip hay từ chối? |
| Vượt giới hạn | `"2147483648"`, `"-2147483649"` | Signed overflow được báo ra sao? |
| Unsigned 32-bit | `"FFFFFFFF"` | Có cần giữ mẫu bit và in không dấu? |
| Radix không hợp lệ | `1`, `37` | Parser có ném `NumberFormatException` không? |
| Chuỗi rỗng/không có chữ số | `""`, `"-"`, `"0x"` | Có thông báo lỗi dễ hiểu không? |
| Ký tự ngoài ASCII | Unicode digits, dấu trừ kiểu typography | Có policy rõ không? |

Nếu xây parser tự định nghĩa, luôn test **tính nhất quán giữa validate và parse**: một chuỗi đã qua validator không được bị diễn giải thành một cơ số hay giá trị khác dự kiến; một input không hợp lệ phải được từ chối thay vì “sửa cho chạy”.

### Nên xử lý dữ liệu không tin cậy ra sao?

Một luồng xử lý minh bạch là:

1. Ghi rõ **schema** của input: signed/unsigned, radix, prefix, dấu, underscore, khoảng trắng, độ dài và miền số.
2. Kiểm tra null, rỗng và giới hạn độ dài trước khi xử lý chuỗi quá lớn.
3. Kiểm tra cú pháp toàn bộ chuỗi, không chỉ kiểm tra “có chứa một chữ số”.
4. Chuẩn hóa **chỉ những ký hiệu được cho phép**, chẳng hạn prefix và underscore hợp lệ.
5. Gọi parser cho radix và miền giá trị đúng.
6. Bắt `NumberFormatException` tại ranh giới và báo lỗi theo schema; không bắt mọi exception rồi trả 0.
7. Kiểm thử các số sát `Integer.MIN_VALUE`/`Integer.MAX_VALUE`, trường hợp unsigned và input biên.

Giới hạn độ dài phù hợp đặc biệt quan trọng nếu parser nhận chuỗi cực dài từ request hoặc tập dữ liệu lớn. Trong mọi trường hợp, không dùng runtime evaluation của mã Java do người dùng cung cấp để “được cùng cú pháp literal”.

## 13. Các nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế | Cách tránh |
| --- | --- | --- |
| “`parseInt` đọc được bất kỳ literal `int` Java nào” | Parser có grammar khác compiler | Viết chính xác input format và chọn API |
| “`radix=16` sẽ tự hiểu `0x`” | `x` không phải digit radix 16 | Bỏ prefix có xác thực hoặc dùng `decode` |
| “`parseInt("010")` giống literal `010`” | Parser decimal cho 10; literal octal cho 8 | Cố định radix/leading-zero policy |
| “`decode` luôn tốt hơn `parseInt`” | `decode("010") == 8`, `decode("09")` lỗi | Chỉ dùng nếu cần chính sách prefix/oct |
| “Compiler cho underscore thì parser cũng nhận” | `parseInt("1_000")` lỗi | Validate + chuẩn hóa có chủ đích |
| “Bỏ hết underscore luôn đúng” | Có thể nhận chuỗi không hợp lệ như `_100` | Validator chạy trước replace |
| “`parseInt("42L")` hiểu hậu tố long” | Hậu tố `L` là cú pháp nguồn | Chọn `Long.parseLong("42")` nếu cần `long` |
| “Không parse được hex 32 bit nghĩa là literal sai” | `0xFFFFFFFF` có thể là literal int mẫu bit hợp lệ | Phân biệt signed parser và unsigned pattern |
| “`String` chứa mã số được compiler phân tích như token Java” | String chỉ là dữ liệu | Runtime parser riêng, không đánh giá mã |
| “Mọi ký tự chữ số phải là ASCII” | `Character.digit` có hỗ trợ Unicode trong nhiều trường hợp | Đặt policy ASCII riêng nếu schema yêu cầu |
| “`trim` đủ để parse mọi dạng số” | Không xử lý prefix/underscore/suffix | Parse theo định dạng đã định nghĩa |
| “Thất bại `parseInt` là lỗi biên dịch” | `NumberFormatException` xảy ra runtime | Bắt/lan truyền lỗi ở ranh giới |
| “Tự viết regex có thể dễ dàng mô phỏng toàn bộ numeric literal Java” | Grammar có trường hợp biên và ngữ nghĩa width/suffix phức tạp | Chỉ nhận cú pháp thực sự cần dùng |

## 14. Câu hỏi tự kiểm tra

1. Vì sao `int x = 0x2A;` biên dịch nhưng `Integer.parseInt("0x2A",16)` ném exception? `Integer.parseInt("2A",16)` khác gì?
2. Với `0b101010` và `"0b101010"`, token nguồn và nội dung String được xử lý bởi thành phần nào?
3. `Integer.parseInt("010")`, `Integer.parseInt("010",8)` và literal `010` có giá trị bao nhiêu?
4. Vì sao literal `09` lỗi biên dịch nhưng `Integer.parseInt("09")` trả 9?
5. `Integer.decode("09")` trả gì? Có nên dùng `decode` khi input thường bắt đầu bằng 0 nhưng phải là decimal?
6. Vì sao `Integer.parseInt("1_000")` thất bại? Nếu bỏ underscore, phải kiểm tra những vị trí nào trước?
7. Literal `1__0` có hợp lệ với Java không? Một API input có bắt buộc phải chấp nhận nó không?
8. `Integer.parseInt("-2A",16)` và `Integer.decode("-0x2A")` cùng trả giá trị nào? API nào chấp nhận prefix?
9. Vì sao `int x = 0xFFFF_FFFF;` hợp lệ và là −1, còn `Integer.parseInt("FFFFFFFF",16)` lỗi? `parseUnsignedInt` giải quyết trường hợp nào?
10. Khi nào cần giữ `"00042"` dưới dạng `String` thay vì chuyển sang số?
11. Nếu nhận chuỗi `"42L"` từ file, đó là một numeric literal Java hay đơn thuần một giá trị văn bản? Hợp đồng input nên quyết định điều gì?
12. Nêu sự khác biệt giữa compile-time syntax error trong literal và runtime `NumberFormatException` khi parse.
13. Nếu cần parser theo **toàn bộ** cú pháp biểu thức Java, `Integer.parseInt` có đủ không? Tại sao không nên chạy trực tiếp source code của user?

## 15. Tài liệu chính thức

- [Java Language Specification `3.10.1 — Integer Literals (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.1): grammar literal thập phân, hexadecimal, octal, binary, underscore và hậu tố `L`.
- [Java SE 17 — `Integer.parseInt`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#parseInt(java.lang.String,int)): yêu cầu radix, dấu, chữ số hợp lệ, miền signed.
- [Java SE 17 — `Integer.decode`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#decode(java.lang.String)): nhận tiền tố `0x`/`0X`/`#`, số 0 đầu octal, dấu.
- [Java SE 17 — `Integer.parseUnsignedInt`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#parseUnsignedInt(java.lang.String,int)): phân tích biểu diễn số nguyên không dấu 32 bit.
- [Java SE 17 — `Character.digit`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html#digit(char,int)): cách xác định chữ số tương thích với radix.

**Ghi nhớ:** Compiler Java xử lý `0x`, `0b`, số 0 đầu, underscore và suffix như **cú pháp của numeric literal trong source**. `Integer.parseInt` xử lý **dữ liệu String ở runtime**: dấu đầu tùy chọn, chữ số theo radix, không tự hiểu prefix/underscore/suffix. Dùng `Integer.decode` nếu thật sự muốn prefix hex/octal, dùng `parseUnsignedInt` cho mẫu 32-bit không dấu, hoặc xây validator + normalization có chủ đích. Điều quan trọng là **định nghĩa rõ schema của input**, không kỳ vọng parser hoạt động như compiler.