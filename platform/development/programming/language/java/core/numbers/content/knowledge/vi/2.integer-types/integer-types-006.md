# Phân biệt ký tự chữ số (`char`) với giá trị số trong Java

Trong Java, **ký tự trông giống một chữ số** và **giá trị số của chữ số đó** là hai thứ khác nhau. Đây là điểm quan trọng khi xử lý dữ liệu nhập, chuyển đổi chuỗi thành số, tính toán và kiểm tra ký tự.

## 1. `'7'`, `7` và `"7"` khác nhau thế nào?

| Cách viết | Kiểu Java | Ý nghĩa |
| --- | --- | --- |
| `'7'` | `char` | Một ký tự chữ số, có giá trị đơn vị mã UTF-16 là **55** (U+0037) |
| `7` | `int` | Số nguyên có giá trị **7**, dùng trực tiếp để tính toán |
| `"7"` | `String` | Chuỗi chứa một ký tự `7`, phải chuyển đổi khi muốn dùng như số |
| `'0'` | `char` | Ký tự `0`, đơn vị mã UTF-16 bằng **48** (U+0030) |

`char` là kiểu nguyên thủy biểu diễn **một đơn vị mã UTF-16 không dấu 16 bit** (0–65.535). Vì vậy Java cho phép đưa `char` vào biểu thức số học, nhưng số thu được từ chuyển kiểu trực tiếp là **mã của ký tự**, không đương nhiên là chữ số mà con người nhìn thấy. Với các ký tự ASCII, `'0'` đến `'9'` lần lượt có mã thập phân 48 đến 57.

Ví dụ, hai khai báo sau đều hợp lệ nhưng khác nghĩa:

```java
char character = '7'; // Ký tự '7': mã UTF-16 là 55.
int number = 7;       // Giá trị số nguyên thực sự là 7.

int codeUnit = character; // Widening conversion: codeUnit == 55.
int digit = character - '0'; // Hiệu hai mã ký tự: 55 - 48 == 7.
```

Đoạn trên là mã minh họa để đặt trong một phương thức Java. **`(int) character` hoặc `int codeUnit = character` không có nghĩa là phân tích ký tự thành số 7.** Phép trừ `'0'` mới thực hiện ánh xạ từ ký tự ASCII sang giá trị chữ số.

## 2. Vì sao phép trừ `'0'` hoạt động?

Các chữ số ASCII được xếp **liên tiếp** trong bảng mã:

| Ký tự | Mã thập phân | Biểu thức | Giá trị số |
| --- | ---: | --- | ---: |
| `'0'` | 48 | `'0' - '0'` | 0 |
| `'1'` | 49 | `'1' - '0'` | 1 |
| `'7'` | 55 | `'7' - '0'` | 7 |
| `'9'` | 57 | `'9' - '0'` | 9 |

Trong Java, khi dùng toán tử số học như `+` hoặc `-`, toán hạng kiểu `char` được **nâng kiểu số học lên `int`**. Do đó, `'7' - '0'` có kiểu kết quả `int` và giá trị 7.

**Chỉ dùng phép trừ này khi đã biết ký tự nằm trong khoảng ASCII `'0'..'9'`.** Với chữ cái, dấu câu hoặc chữ số thuộc hệ chữ khác, hiệu mã ký tự không phải cách chuyển đổi chữ số tổng quát.

```java
static int asciiDigit(char c) {
    if (c < '0' || c > '9') {
        throw new IllegalArgumentException("Not an ASCII digit: " + c);
    }
    return c - '0';
}
```

Hàm này là một phương thức cần đặt bên trong lớp Java. Nếu truyền `'7'`, kết quả là `7`. Nếu truyền `'A'` hoặc chữ số Ả Rập `'٧'`, hàm chủ động báo lỗi vì ký tự không thuộc tập chữ số ASCII đã cho phép.

## 3. `char` trong tính toán và khi in ra

Hãy phân biệt **in ký tự**, **in giá trị mã** và **thực hiện phép tính**:

```java
char c = '7';

System.out.println(c);              // 7 (in dạng ký tự)
System.out.println((int) c);        // 55 (giá trị mã UTF-16)
System.out.println(c + 1);          // 56 (phép cộng số nguyên)
System.out.println((char) (c + 1)); // 8 (ép kết quả 56 về ký tự)
System.out.println(c - '0');        // 7 (giá trị chữ số)
System.out.println("7" + 1);        // 71 (nối chuỗi)
```

Đây là các câu lệnh minh họa đặt trong `main`. Với `println(c)`, Java chọn overload nhận `char` và hiển thị hình dạng ký tự. Với `println(c + 1)`, biểu thức đã được tính thành `int`, nên in ra `56`. Khi có `String` ở toán tử `+`, Java có thể thực hiện **nối chuỗi**: `"7" + 1` tạo chuỗi `"71"`, không phải số 8.

Hai tình huống dễ nhầm:

- `'7' + '2'` là phép cộng hai mã: `55 + 50 = 105`, **không** phải số 9 hay số 72.
- `(char) 7` tạo ký tự điều khiển U+0007, **không** tạo ký tự `'7'`. Ngược lại, `(char) ('0' + 7)` tạo `'7'` vì nằm trong dải chữ số ASCII.

## 4. Chương trình Java 17+ chạy độc lập

Lưu nội dung sau vào **`DigitVsCharDemo.java`**:

```java
public class DigitVsCharDemo {
    static int asciiDigit(char c) {
        if (c < '0' || c > '9') {
            throw new IllegalArgumentException("Not an ASCII digit: " + c);
        }
        return c - '0';
    }

    public static void main(String[] args) {
        char symbol = '7';
        int rawCodeUnit = symbol;
        int digit = asciiDigit(symbol);

        System.out.println("char=" + symbol);
        System.out.println("UTF-16 code unit=" + rawCodeUnit);
        System.out.println("decimal digit=" + digit);
        System.out.println("add 1=" + (symbol + 1));
        System.out.println("next char=" + (char) (symbol + 1));
        System.out.println("text concat=" + ("7" + 1));
        System.out.println("Unicode decimal digit=" + Character.digit('\u0667', 10));
        System.out.println("hex A=" + Character.digit('A', 16));
        System.out.println("digit 7 -> char=" + Character.forDigit(7, 10));
        System.out.println("two digits=" + (asciiDigit('4') * 10 + asciiDigit('2')));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 DigitVsCharDemo.java
java DigitVsCharDemo
```

Kết quả chuẩn trên stdout:

```text
char=7
UTF-16 code unit=55
decimal digit=7
add 1=56
next char=8
text concat=71
Unicode decimal digit=7
hex A=10
digit 7 -> char=7
two digits=42
```

Dòng cuối cho thấy cách ghép **giá trị số** của hai ký tự `'4'` và `'2'` thành số `42`: chữ số hàng chục nhân 10 rồi cộng chữ số hàng đơn vị. Đây là số học trên `int`, không phải ghép ký tự.

## 5. Khi dữ liệu có chữ số Unicode

Không phải mọi ký tự được hiển thị là chữ số `7` đều có cùng mã với `'7'`. Chẳng hạn:

- `'7'`: chữ số ASCII, mã U+0037.
- `'٧'`: chữ số Arabic-Indic seven, mã U+0667.
- `'７'`: chữ số fullwidth seven, mã U+FF17.

Cả ba có thể biểu thị **chữ số thập phân 7**, nhưng `c - '0'` chỉ đúng cho trường hợp ASCII. Nếu xử lý chữ số Unicode, dùng API `Character` có quy tắc rõ ràng:

```java
char ascii = '7';
char arabicIndic = '٧';
char letter = 'A';

System.out.println(Character.isDigit(ascii));            // true
System.out.println(Character.isDigit(arabicIndic));      // true
System.out.println(Character.digit(arabicIndic, 10));    // 7
System.out.println(Character.digit(letter, 10));         // -1
System.out.println(Character.digit(letter, 16));         // 10
```

Đoạn này đặt trong `main`. `Character.digit(c, radix)` trả giá trị chữ số theo **cơ số** chỉ định hoặc `-1` nếu không hợp lệ. Ví dụ chữ `A` có giá trị 10 trong hệ cơ số 16 nhưng không phải chữ số hợp lệ ở cơ số 10. Các radix được hỗ trợ từ `Character.MIN_RADIX` (2) đến `Character.MAX_RADIX` (36).

Dùng kết hợp kiểm tra và chuyển đổi khi nhận đúng **một ký tự chữ số thập phân**:

```java
static int decimalDigit(char c) {
    int value = Character.digit(c, 10);
    if (!Character.isDigit(c) || value < 0) {
        throw new IllegalArgumentException("Not a decimal digit");
    }
    return value;
}
```

Đây là phương thức đặt bên trong lớp Java. `Character.isDigit(c)` kiểm tra tính chất chữ số thập phân theo Unicode; `Character.digit(c, 10)` lấy giá trị cần dùng để tính toán. Phép `c - '0'` chỉ kiểm tra quan hệ giữa mã, nên không thay thế được cặp API này khi đầu vào cho phép nhiều hệ chữ.

**Giới hạn của `char`:** Một số ký tự Unicode nằm ngoài Basic Multilingual Plane (BMP), cần **hai đơn vị mã UTF-16** (cặp surrogate). `charAt(index)` chỉ lấy một đơn vị mã; lúc này dùng `String.codePointAt(index)` và overload `Character.digit(int codePoint, int radix)` / `Character.isDigit(int codePoint)`.

```java
String s = "𝟠"; // MATHEMATICAL DOUBLE-STRUCK DIGIT EIGHT (U+1D7E0).
System.out.println(s.length());                       // 2: hai đơn vị UTF-16.
System.out.println(Character.digit(s.charAt(0), 10)); // -1: chỉ một surrogate.
System.out.println(Character.digit(s.codePointAt(0), 10)); // 8.
```

Ví dụ này đặt trong `main`; việc duyệt cả chuỗi theo code point nên tăng chỉ số bằng `Character.charCount(codePoint)` hoặc sử dụng `String.codePoints()`, thay vì mặc định mỗi `char` là một ký tự Unicode hoàn chỉnh.

## 6. Chuyển đổi theo chiều ngược: số thành ký tự chữ số

Khi đã có **giá trị số** từ 0 đến 9 và cần ký tự ASCII:

```java
int n = 7;
char c1 = (char) ('0' + n);             // '7', với điều kiện 0 <= n <= 9.
char c2 = Character.forDigit(n, 10);    // '7'.
String text = Integer.toString(n);     // "7" (String).
```

`Character.forDigit(digit, radix)` còn dùng được cho chữ số của các hệ cơ số khác (ví dụ `Character.forDigit(10, 16)` trả về `'a'`). API trả ký tự NUL `'\0'` khi đối số chữ số/cơ số không hợp lệ, vì vậy cần kiểm tra điều kiện đầu vào khi tránh kết quả không mong muốn. Không dùng `(char) ('0' + n)` cho `n = 12`: kết quả là `'<'`, **không** phải chuỗi `"12"`. Với số có nhiều chữ số, dùng `Integer.toString(n)` hoặc `String.valueOf(n)`.

## 7. Một ký tự chữ số khác với một chuỗi nhiều chữ số

- Với **một ký tự ASCII** `'7'`, sau kiểm tra phạm vi, dùng `c - '0'`.
- Với **một code point chữ số Unicode**, dùng `Character.digit(codePoint, 10)` và xử lý trường hợp `-1`.
- Với **một chuỗi biểu diễn số nguyên**, ví dụ `"2048"`, dùng `Integer.parseInt(text)` hoặc kiểu số phù hợp. Chuỗi có thể chứa dấu và nhiều chữ số; `char` riêng lẻ không đại diện cho toàn bộ số nguyên đó.

Ví dụ:

```java
String input = "2048";
int parsed = Integer.parseInt(input);
System.out.println(parsed + 2); // 2050
```

Đặt trong `main`. `Integer.parseInt` ném `NumberFormatException` khi chuỗi không có cú pháp số nguyên hợp lệ hoặc giá trị vượt phạm vi `int`. Đầu vào `null` cũng không chuyển đổi được. Nếu cần dữ liệu lớn hơn giới hạn `int`, cân nhắc `Long.parseLong` hoặc `BigInteger`.

Lưu ý riêng về `Character.getNumericValue`: API này có phạm vi **giá trị số Unicode rộng hơn chữ số thập phân**, chẳng hạn có thể trả 10 với `'A'` hoặc giá trị của ký tự số La Mã. Không dùng riêng `getNumericValue` để quyết định một ký tự có phải chữ số thập phân hay không; hãy chọn `Character.isDigit` / `Character.digit(..., 10)` theo yêu cầu đầu vào.

## 8. Các lỗi thường gặp và cách tránh

| Viết nhầm | Vấn đề | Cách làm đúng |
| --- | --- | --- |
| `int n = '7';` rồi kỳ vọng `n == 7` | `n` thật ra bằng 55 | Kiểm tra rồi dùng `'7' - '0'` hoặc `Character.digit('7', 10)` |
| `char c = (char) 7;` để lấy `'7'` | 7 là mã của ký tự điều khiển, không phải mã của chữ số | `(char) ('0' + 7)` sau kiểm tra phạm vi |
| `'7' + '2'` để cộng 7 và 2 | Java cộng **mã ký tự** thành 105 | `('7' - '0') + ('2' - '0')` thành 9 |
| `c - '0'` trên mọi ký tự Unicode | Chỉ đúng cho dải ASCII `'0'..'9'` | Dùng `Character.digit` khi cho phép Unicode |
| `Character.getNumericValue(c) >= 0` nghĩa là chữ số thập phân | Một số chữ cái/ký hiệu số cũng có numeric value | Dùng `Character.isDigit(c)` và cơ số 10 |
| `s.charAt(0)` để đọc mọi Unicode digit | Ký tự ngoài BMP có thể gồm hai `char` | Dùng code point và overload nhận `int` |
| Dùng `"7" + 1` để tính `8` | Nối chuỗi cho ra `"71"` | Chuyển sang số trước khi cộng |

**Tự kiểm tra:**

1. `(int) '5'` bằng bao nhiêu? **53**, vì là mã của `'5'`.
2. `'5' - '0'` bằng bao nhiêu? **5**, vì đã chuẩn hóa theo mã chữ số ASCII `'0'`.
3. `'9' + 1` có in thành ký tự `':'` không? **Không**, biểu thức có kiểu `int` và giá trị **58**; phải ép sang `char` mới thành `':'`.
4. Muốn đọc chữ số `'٧'` từ đầu vào Unicode? **`Character.digit('٧', 10)`** trả `7`.
5. Muốn đổi số nguyên `27` thành văn bản? **`Integer.toString(27)`** trả chuỗi `"27"`, không thể chứa cả hai chữ số trong một `char`.

Điểm cần nhớ khi làm bài về **kiểu số nguyên**: `char` tham gia được vào phép toán số học vì lưu đơn vị mã 16 bit, nhưng **ý nghĩa chữ số** là một bước diễn giải riêng. Với ASCII, hiệu so với `'0'` là cách đơn giản; với Unicode, nên dùng `Character`; với chuỗi nhiều chữ số, nên dùng API phân tích số nguyên.
