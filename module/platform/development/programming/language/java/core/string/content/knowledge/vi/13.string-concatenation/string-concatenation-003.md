# Phân biệt ký tự cộng số với nối chuỗi trong Java

Trong Java, toán tử `+` có **hai vai trò**: thực hiện phép cộng số học hoặc nối chuỗi (`String concatenation`). Vì `char` lưu một đơn vị mã ký tự 16 bit có giá trị số, biểu thức `'A' + 1` **không** có nghĩa là ghép chữ `A` với chữ số `1`: Java nâng `char` thành `int` rồi cộng, nhận `66`. Ngược lại, `"A" + 1` có một toán hạng là `String` nên tạo chuỗi `"A1"`.

Sự khác biệt này rất quan trọng khi in log, xây dựng chuỗi, xử lý ký tự chữ số, dịch chuyển ký tự và đọc biểu thức có nhiều toán tử `+`. Chỉ cần thay dấu nháy đơn bằng nháy kép, thêm chuỗi rỗng hoặc đặt ngoặc khác vị trí, **kiểu kết quả và giá trị có thể đổi**.

## 1. Phân biệt `char`, `String` và `int`

| Biểu thức | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `'A'` | `char` | Một UTF-16 code unit tương ứng với ký tự `A` (giá trị `U+0041`, thập phân 65) |
| `"A"` | `String` | Một đối tượng chuỗi có nội dung là chữ `A` |
| `1` | `int` | Giá trị số nguyên một |
| `'1'` | `char` | Ký tự số `1` (giá trị `U+0031`, thập phân 49) |
| `"1"` | `String` | Chuỗi gồm ký tự `1` |

**Nháy đơn `'...'` không giống nháy kép `"..."`.**

- `'A'` là một giá trị nguyên thủy `char`, có thể tham gia phép toán số học.
- `"A"` là `String`, khiến toán tử `+` ở biểu thức nhị phân trở thành phép nối chuỗi.
- `'1'` mang giá trị mã ký tự của chữ số, **không phải số nguyên 1**.
- `"1"` là một chuỗi. Muốn đổi nội dung chuỗi chữ số thành số, có thể dùng `Integer.parseInt("1")` và xử lý lỗi đầu vào khi cần.

Với các ký tự quen thuộc trong bảng ASCII (cũng nằm trong Unicode), `'A'` có giá trị mã 65; `'B'` có giá trị mã 66; `'0'` có giá trị mã 48; `'1'` có giá trị mã 49.

## 2. Quy tắc của toán tử `+`

### Khi cộng các toán hạng số, `char` được nâng thành `int`

Nếu cả hai toán hạng là kiểu số nguyên thủy phù hợp với phép cộng số học, Java sử dụng **binary numeric promotion**. Với `char`, `byte` và `short`, giá trị được nâng thành ít nhất `int` trước khi tính toán.

Ví dụ:

```java
int a = 'A' + 1;    // 65 + 1 = 66
int b = 'A' + 'B';  // 65 + 66 = 131
int c = 1 + '2';   // 1 + 50 = 51
```

Kết quả biểu thức `'A' + 1` là một `int`, không phải `char`. Java **không tự chuyển mã 66 thành ký tự `B`** chỉ vì toán hạng đầu là `char`.

### Khi một toán hạng là `String`, `+` nối chuỗi

Nếu ít nhất một toán hạng của phép `+` nhị phân là `String`, Java thực hiện **nối chuỗi**. Toán hạng còn lại được chuyển thành biểu diễn văn bản phù hợp:

```java
String a = "A" + 1;   // "A1"
String b = 'A' + "1"; // "A1"
String c = "A" + 'B'; // "AB"
String d = "" + 42;   // "42"
```

Trong các ví dụ trên, toán hạng `char` được biểu diễn như **ký tự** khi tham gia phép nối với `String`: `'A' + "1"` cho `"A1"` chứ không cho `"651"`.

Hai kiểu hoạt động của `+` là **khác nhau về ngữ nghĩa**, không phải cùng một phép cộng rồi Java tự chọn cách in kết quả.

## 3. Ví dụ hoàn chỉnh: cùng chữ A nhưng kết quả khác hẳn

Tạo tệp `CharPlusDemo.java`:

```java
public class CharPlusDemo {
    public static void main(String[] args) {
        System.out.println('A');
        System.out.println('A' + 1);
        System.out.println("A" + 1);
        System.out.println('A' + "1");
        System.out.println('A' + 'B');
        System.out.println("" + 'A' + 'B');
        System.out.println(String.valueOf('A' + 1));
        System.out.println(String.valueOf((char) ('A' + 1)));
    }
}
```

Biên dịch và chạy trên Java 17 trở lên:

```bash
javac -encoding UTF-8 CharPlusDemo.java
java CharPlusDemo
```

Kết quả chính xác:

```text
A
66
A1
A1
131
AB
66
B
```

Từng dòng minh họa một quy tắc:

1. `println('A')` gọi overload có đối số `char` nên in ký tự `A`.
2. `'A' + 1` là phép cộng số: 65 + 1 = 66; `println` nhận kết quả số nguyên và in `66`.
3. `"A" + 1` có `String` nên nối thành `A1`.
4. `'A' + "1"` cũng có `String` nên nối thành `A1`.
5. `'A' + 'B'` là phép cộng số nguyên 65 + 66 = 131.
6. `"" + 'A' + 'B'` bắt đầu bằng nối chuỗi và tiếp tục nối hai ký tự thành `AB`.
7. `String.valueOf('A' + 1)` nhận giá trị `int` 66 nên trả chuỗi `"66"`.
8. `(char) ('A' + 1)` ép số 66 về kiểu `char`, tương ứng ký tự `B`; `String.valueOf(char)` trả `"B"`.

**Ghi nhớ:** chỉ nhìn thấy chữ `A` trong mã nguồn chưa đủ để biết chương trình sẽ in `A` hay `65`. Cần xác định **kiểu của cả biểu thức** được truyền cho `println`.

## 4. Thứ tự kết hợp từ trái sang phải và vai trò của dấu ngoặc

Thứ tự nhóm quyết định phép cộng mã ký tự xảy ra **trước hay sau** khi biểu thức trở thành `String`:

```java
System.out.println('A' + 1 + "!");      // 66!
System.out.println("!" + 'A' + 1);      // !A1
System.out.println("value=" + ('A' + 'B')); // value=131
```

Dùng ngoặc khi muốn tính mã số trước. Bài **Thứ tự kết hợp trái–phải của + với số và chuỗi** giải thích riêng tính kết hợp, độ ưu tiên và thứ tự đánh giá biểu thức; ở đây trọng tâm là **kiểu `int` của phép cộng `char`**.

## 5. Ký tự chữ số không phải giá trị số tương ứng

Một lỗi thường gặp là dùng `'5' + 2` khi muốn tính `5 + 2`. `'5'` lưu mã ký tự `U+0035` (thập phân 53), nên `'5' + 2` trả `55`, không phải `7`.

Tệp `DigitCharDemo.java`:

```java
public class DigitCharDemo {
    public static void main(String[] args) {
        char digitChar = '5';

        System.out.println("digitChar=" + digitChar);
        System.out.println("codeUnit=" + (int) digitChar);
        System.out.println("charPlusTwo=" + (digitChar + 2));
        System.out.println("numericValue=" + (digitChar - '0'));
        System.out.println("numericPlusTwo=" + (digitChar - '0' + 2));
        System.out.println("Character.digit=" + Character.digit(digitChar, 10));
        System.out.println("String.parse=" +
                Integer.parseInt(String.valueOf(digitChar)));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 DigitCharDemo.java
java DigitCharDemo
```

Đầu ra:

```text
digitChar=5
codeUnit=53
charPlusTwo=55
numericValue=5
numericPlusTwo=7
Character.digit=5
String.parse=5
```

**Vì sao `digitChar - '0'` cho 5?** Các ký tự chữ số ASCII `'0'` đến `'9'` có mã liên tiếp từ 48 đến 57, nên `'5' - '0'` là 53 − 48 = 5. Đây là công thức hữu ích **nếu bạn đã xác nhận ký tự thuộc `'0'..'9'`**.

`Character.digit(digitChar, 10)` là một lựa chọn rõ ràng hơn khi xử lý một ký tự chữ số được Java nhận diện theo cơ số 10; nó trả `-1` khi ký tự không hợp lệ ở cơ số đó. `Integer.parseInt(...)` phù hợp khi dữ liệu đầu vào là cả một chuỗi chữ số, có thể nhiều ký tự, và cần bắt lỗi định dạng.

Không nên tự động áp dụng `c - '0'` cho mọi ký tự Unicode giống chữ số: không phải các chữ số thuộc mọi hệ chữ viết đều có vị trí mã gần `'0'` ASCII.

## 6. Biến số `char` khi cộng và phép gán về `char`

`char` là kiểu nguyên thủy **16 bit không dấu** dùng để biểu diễn UTF-16 code unit. Khi cộng với một số nguyên, kết quả thông thường là `int`. Do đó, với một **biến** `char`:

```java
char c = 'A';
int number = c + 1;            // 66
char next = (char) (c + 1);    // 'B'
// char wrong = c + 1;         // Lỗi biên dịch: int không tự thu hẹp thành char
```

Đây là đoạn minh họa đặt trong một phương thức.

Tuy nhiên, Java có **ngoại lệ cho biểu thức hằng tại thời điểm biên dịch**. Một biểu thức hằng kiểu `int` có giá trị nằm trong dải `char` có thể được gán trực tiếp cho biến `char`:

```java
char fromConstant = 'A' + 1; // Hợp lệ: hằng số nguyên 66 nằm trong dải char

char letter = 'A';
// char fromVariable = letter + 1; // Không hợp lệ: kết quả là int
char fromCast = (char) (letter + 1); // Hợp lệ
```

Vì vậy, khẳng định “`char` cộng `int` **luôn** không gán được vào `char`” là chưa chính xác: phép cộng **vẫn có kiểu `int`**, nhưng quy tắc gán cho phép **thu hẹp ngầm một biểu thức hằng số nguyên nằm trong giới hạn `char`**. Còn `letter + 1` có chứa biến nên không phải biểu thức hằng theo quy tắc ấy.

### `+=` và `++` hoạt động như thế nào?

Với phép gán kết hợp, Java cho phép chuyển kết quả phép toán về kiểu của biến bên trái theo quy tắc riêng:

```java
char c = 'A';
c += 1; // B
c++;    // C
```

Điều này **không làm cho biểu thức `c + 1` có kiểu `char`**. Nó chỉ có nghĩa rằng trong phép gán kết hợp `c += 1`, Java thực hiện phép toán và chuyển kết quả về kiểu của `c` theo ngữ nghĩa của `+=`. Cần cẩn thận với giá trị lớn: phép chuyển về `char` có thể giữ lại 16 bit thấp của giá trị số, không bảo đảm tạo ra ký tự Unicode đúng ý định.

Tệp `CharArithmeticAssignment.java`:

```java
public class CharArithmeticAssignment {
    public static void main(String[] args) {
        char fromConstant = 'A' + 1;
        char fromVariable = 'A';
        int beforeCast = fromVariable + 1;
        char fromCast = (char) beforeCast;

        fromVariable += 1;
        fromVariable++;

        System.out.println("constant=" + fromConstant);
        System.out.println("intResult=" + beforeCast);
        System.out.println("cast=" + fromCast);
        System.out.println("compound=" + fromVariable);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CharArithmeticAssignment.java
java CharArithmeticAssignment
```

Kết quả:

```text
constant=B
intResult=66
cast=B
compound=C
```

Sử dụng phép cộng mã ký tự để dịch chữ **không phải** phương pháp xử lý văn bản tự nhiên tổng quát: bảng mã Unicode chứa nhiều khoảng không liên tiếp, nhiều chữ có dấu hoặc dạng ký tự bổ sung. Ngay cả việc dùng `c++` cho các ký tự ASCII cũng nên được giới hạn ở bài toán kỹ thuật có kiểm tra đầu vào và giới hạn.

## 7. Khi truyền vào `print` hoặc `println`, kiểu đối số quyết định cách in

Lớp `PrintStream` có nhiều overload, bao gồm `println(char)`, `println(int)` và `println(String)`. Java chọn phương thức tương ứng với **kiểu biểu thức** ở thời điểm biên dịch.

| Câu lệnh | Kiểu biểu thức đối số | Nội dung được in |
| --- | --- | --- |
| `System.out.println('A');` | `char` | `A` |
| `System.out.println((int) 'A');` | `int` | `65` |
| `System.out.println('A' + 1);` | `int` | `66` |
| `System.out.println((char) ('A' + 1));` | `char` | `B` |
| `System.out.println("A" + 1);` | `String` | `A1` |
| `System.out.println('A' + "1");` | `String` | `A1` |

Điều này giải thích tại sao cùng `'A'` có lúc in thành chữ `A`, lúc thành `65` hoặc thành số `66`.

Nếu bạn cần thể hiện **mã số** của một `char`, hãy ép sang `int` một cách tường minh: `(int) c`. Nếu cần thể hiện **ký tự sau khi tính toán**, cần quyết định xem phép chuyển số về `char` có thực sự hợp lệ cho bài toán hay không.

## 8. Ghép ký tự thành chuỗi: lựa chọn rõ ràng hơn

Khi muốn nối hai ký tự mà không cộng mã của chúng, có một số cách diễn đạt rõ ý định:

### Dùng một `String` làm toán hạng

```java
char first = 'J';
char second = 'a';

String joined = "" + first + second; // "Ja"
```

Cách này đơn giản và không cần chuyển các `char` thành số. Tuy nhiên, với mã dài hoặc nhiều vòng lặp, có thể chọn công cụ ghép chuỗi chuyên dụng hơn để làm rõ ý định.

### Dùng `StringBuilder`

```java
StringBuilder builder = new StringBuilder();
builder.append('J');
builder.append('a');
String joined = builder.toString(); // "Ja"
```

`StringBuilder.append(char)` thêm **ký tự được biểu diễn bởi code unit**, không cộng giá trị số. Đây là lựa chọn thường phù hợp khi xây dựng chuỗi theo nhiều bước hoặc trong vòng lặp. Không nên dựa vào việc Java thực thi một biểu thức nối chuỗi cụ thể bằng lớp nào bên trong; JDK có thể chọn chiến lược tối ưu khác nhau.

### Dùng `String.valueOf(char)`

```java
char letter = 'A';
String text = String.valueOf(letter); // "A"
```

Cần phân biệt `String.valueOf(letter)` (đối số là `char`) với `String.valueOf(letter + 1)` (đối số đã là `int`). Cách rõ ràng nhất để tạo văn bản từ một ký tự là truyền **chính ký tự** hoặc một mảng ký tự vào API tương ứng, không cộng mã số trừ khi bài toán thực sự yêu cầu.

## 9. `char` chỉ là một UTF-16 code unit, không phải mọi ký tự Unicode hoàn chỉnh

Trong các ví dụ trên, `'A'` và `'5'` đều là ký tự thuộc BMP nên chúng vừa bằng một `char` vừa bằng một Unicode code point. Nhưng không phải mọi ký tự Unicode đều được chứa trong một `char`. Ví dụ emoji 😀 (`U+1F600`) cần **một surrogate pair gồm hai `char`** trong UTF-16.

Vì thế:

- `char` tham gia phép cộng bằng giá trị **code unit**, không tự động là một Unicode code point hoàn chỉnh.
- Không thể lấy một Unicode code point ngoài BMP chỉ bằng cách lấy một `char` trong surrogate pair rồi cộng số.
- Nếu cần xử lý mã Unicode như một đơn vị, dùng `int` để lưu code point; các API như `String.codePointAt(...)` và `Character.toChars(int)` hỗ trợ làm việc với code point.

Tệp `CodePointVsChar.java`:

```java
public class CodePointVsChar {
    public static void main(String[] args) {
        String emoji = new String(Character.toChars(0x1F600));

        System.out.println("length=" + emoji.length());
        System.out.printf("firstUnit=U+%04X%n", (int) emoji.charAt(0));
        System.out.printf("codePoint=U+%X%n", emoji.codePointAt(0));
        System.out.println("concat=" + ("X" + emoji));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CodePointVsChar.java
java CodePointVsChar
```

Kết quả (console cần hỗ trợ hiển thị emoji để nhìn đúng dòng cuối):

```text
length=2
firstUnit=U+D83D
codePoint=U+1F600
concat=X😀
```

Khi nối `"X" + emoji`, Java nối toàn bộ nội dung `String`. Khi làm phép toán với `emoji.charAt(0)`, bạn chỉ đang thao tác với **một nửa của surrogate pair**, không phải toàn bộ emoji.

## 10. Các lỗi phổ biến và cách tránh

- `'1' + 2` cho `51`, vì `'1'` mang mã 49 chứ không phải số 1.
- `'A' + 'B'` cho `131` (`int`), trong khi `"" + 'A' + 'B'` cho `"AB"`.
- `String.valueOf('A' + 1)` nhận `int` và cho `"66"`; dùng `String.valueOf((char) ('A' + 1))` để tạo `"B"` khi phép chuyển có nghĩa.
- `char next = c + 1` không biên dịch nếu `c` là biến; ngoại lệ thu hẹp ngầm chỉ áp dụng cho **biểu thức hằng** `int` hợp lệ.
- Một `char` có thể chỉ là một nửa surrogate pair; không áp dụng mẹo cộng trừ ASCII cho Unicode tổng quát.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Đoạn sau in gì?

```java
System.out.println('A' + 2);
System.out.println("A" + 2);
System.out.println('A' + "2");
```

**Đáp án:** `67`, `A2`, `A2`. Chỉ dòng đầu là phép cộng mã ký tự với số nguyên.

**Câu 2.** Vì sao `'1' + '2'` không phải số 3 và cũng không phải chuỗi `"12"`?

**Đáp án:** Cả hai toán hạng là `char`, nên được nâng thành `int` và cộng các mã `49 + 50 = 99`. Muốn tính 1 + 2 phải chuyển chữ số thành số; muốn ghép thành `"12"` cần dùng `String`.

**Câu 3.** `"result=" + 'A' + 1` khác gì `"result=" + ('A' + 1)`?

**Đáp án:** Biểu thức đầu in `result=A1` vì nối chuỗi ngay từ `"result="`. Biểu thức sau in `result=66` vì phép cộng trong ngoặc được thực hiện trước khi nối.

**Câu 4.** `char c = 'A' + 1;` có hợp lệ không? Còn `char c = 'A'; char d = c + 1;` thì sao?

**Đáp án:** Trường hợp đầu hợp lệ vì `'A' + 1` là **biểu thức hằng `int`** có giá trị 66 nằm trong dải `char`. Trường hợp sau không hợp lệ vì `c + 1` phụ thuộc biến, kết quả kiểu `int` không được tự chuyển về `char` trong phép gán thông thường.

**Câu 5.** Khi muốn tạo chuỗi `"Hi"` từ `char a = 'H'; char b = 'i';`, viết thế nào?

**Đáp án:** Có thể viết `String result = "" + a + b;` hoặc `new StringBuilder().append(a).append(b).toString()`. Không dùng `a + b` vì đó là phép cộng số.

**Ghi nhớ:** `char + số` hoặc `char + char` là **phép cộng số** sau khi nâng kiểu thành `int`; `String + giá trị` là **nối chuỗi**. Muốn tính số, kiểm tra kiểu của toán hạng; muốn ghép ký tự, tạo một phép nối `String` rõ ràng; và khi có nhiều dấu `+`, hãy dùng ngoặc để biểu đạt đúng ý định.
