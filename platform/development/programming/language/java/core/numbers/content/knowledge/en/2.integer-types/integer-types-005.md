# `char` là số nguyên không dấu biểu diễn đơn vị mã UTF-16

## 1. Vì sao `char` thuộc nhóm kiểu số nguyên?

Trong Java, `char` là một **kiểu nguyên thủy (*primitive*) 16 bit không dấu**, có miền giá trị nguyên **0 đến 65.535** (tương ứng `0x0000` đến `0xFFFF`). Đặc tả ngôn ngữ xếp `char` vào nhóm *integral types* cùng `byte`, `short`, `int` và `long`. `Character.SIZE` bằng `16`, `Character.MIN_VALUE` bằng `'\u0000'` (giá trị nguyên 0), còn `Character.MAX_VALUE` bằng `'\uFFFF'` (giá trị nguyên 65.535).

Tuy nhiên, mục đích chính của `char` **không phải lưu một số đếm**. Mỗi giá trị `char` được hiểu là **một đơn vị mã (*code unit*) UTF-16**. Nó có thể biểu diễn ký tự thường gặp như `'A'`, `'7'`, `'中'` hoặc một phần của cặp thay thế (*surrogate pair*). Đặc điểm “số nguyên không dấu” giải thích cách Java lưu, so sánh và thực hiện phép toán với kiểu này; đặc điểm “đơn vị mã UTF-16” giải thích **nó biểu diễn phần nào của văn bản Unicode**.

Ba khái niệm phải phân biệt:

- **Giá trị số của `char`:** một số nguyên từ 0 đến 65.535.
- **Đơn vị mã UTF-16:** một phần tử 16 bit của chuỗi UTF-16; chính là thứ `char` biểu diễn.
- **Ký tự Unicode theo mã điểm (*code point*):** một giá trị Unicode từ `U+0000` đến `U+10FFFF`, trừ khoảng surrogate không phải *Unicode scalar value*. Nhiều mã điểm cần **hai** đơn vị mã UTF-16, nên không thể chứa trọn trong một `char`.

Chẳng hạn, `'A'` vừa là một `char` mang giá trị nguyên 65, vừa là một đơn vị mã UTF-16 biểu diễn mã điểm `U+0041`. Trong khi đó, biểu tượng 😀 (`U+1F600`) cần **hai** giá trị `char`: `0xD83D` và `0xDE00`. Do đó, khẳng định “một `char` luôn là một ký tự Unicode hoàn chỉnh” là **sai**.

## 2. Miền giá trị và hành vi số học

### 2.1. Không dấu khác gì `byte`, `short`?

`byte` và `short` là các số nguyên **có dấu** 8 và 16 bit, có thể nhận giá trị âm. `char` cũng có 16 bit nhưng **không dấu**:

| Kiểu | Số bit | Giá trị nhỏ nhất | Giá trị lớn nhất | Mục đích chính |
|---|---:|---:|---:|---|
| `byte` | 8 | −128 | 127 | Số nguyên nhỏ, dữ liệu byte |
| `short` | 16 | −32.768 | 32.767 | Số nguyên có dấu 16 bit |
| `char` | 16 | 0 | 65.535 | Đơn vị mã UTF-16 |
| `int` | 32 | −2.147.483.648 | 2.147.483.647 | Số nguyên thông thường |

Điều này có nghĩa `char` **không tự biểu diễn số âm**. Không thể gán biến `char` từ giá trị `-1` bằng phép gán thu hẹp ngầm định. Khi ép kiểu `(char) -1`, kết quả có giá trị số `65535` (giữ 16 bit thấp), không phải một `char` âm. Việc ép kiểu như vậy là chuyển đổi số học, không tạo ra một ký tự văn bản hợp lệ theo nhu cầu sử dụng.

### 2.2. `char` tham gia phép toán số như thế nào?

Trong đa số phép toán số học, Java thực hiện *binary numeric promotion*, chuyển `char` thành `int` trước khi tính:

~~~java
char letter = 'A';
int code = letter;           // widening conversion: 65
int nextCode = letter + 1;   // phép cộng có kiểu int: 66
char next = (char) (letter + 1); // ép lại char: 'B'
~~~

Đoạn trên là **minh họa** (không phải chương trình chạy độc lập). Chú ý `char next = letter + 1;` **không biên dịch** nếu `letter` là biến `char`: biểu thức `letter + 1` có kiểu `int` và phải chuyển đổi thu hẹp một cách tường minh. Đừng suy từ việc `char` là kiểu số nguyên rằng mọi kết quả phép cộng vẫn có kiểu `char`.

Một biểu thức hằng có thể là ngoại lệ của quy tắc gán: `char capitalA = 65;` hoặc `char capitalA = '\u0041';` đều hợp lệ vì giá trị hằng nằm trong miền của `char`. Nhưng `int number = 65; char letter = number;` không hợp lệ nếu không ép kiểu, dù giá trị lúc chạy vẫn là 65.

Khi so sánh `char` bằng `<`, `>`, `==`, Java so sánh **giá trị số/đơn vị mã**, không thực hiện quy tắc sắp xếp từ điển của một ngôn ngữ. Ví dụ, `'A' < 'a'` là `true` vì 65 nhỏ hơn 97; điều đó không có nghĩa đây là cách sắp xếp tên người, văn bản tiếng Việt hoặc chuỗi theo `Locale`. Với sắp xếp ngôn ngữ tự nhiên, xem `Collator` thay cho phép so sánh từng `char`.

### 2.3. Ví dụ độc lập: nhìn thấy giá trị số

Tạo tệp `CharIntegralDemo.java`:

~~~java
public class CharIntegralDemo {
    public static void main(String[] args) {
        char letter = 'A';
        char digit = '7';
        char han = '\u4E2D'; // U+4E2D: chữ 中
        char max = Character.MAX_VALUE;

        System.out.println("bits=" + Character.SIZE);
        System.out.println("range=" + (int) Character.MIN_VALUE
                + ".." + (int) max);
        System.out.println("A=" + (int) letter);
        System.out.println("Han=" + (int) han);
        System.out.println("digitValue=" + (digit - '0'));
        System.out.println("A+1=" + (letter + 1));
        System.out.println("next=" + (char) (letter + 1));
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac CharIntegralDemo.java
java CharIntegralDemo
~~~

Đầu ra chính xác:

~~~text
bits=16
range=0..65535
A=65
Han=20013
digitValue=7
A+1=66
next=B
~~~

Giải thích:

1. `Character.SIZE` cho biết kích thước logic 16 bit của `char`; không có nghĩa mỗi ký tự trong file luôn chiếm đúng hai byte. Mã hóa văn bản trên đĩa có thể là UTF-8 hoặc mã hóa khác.
2. `'A'` có giá trị nguyên 65; `'\u4E2D'` có giá trị nguyên 20.013.
3. `'7'` có giá trị mã 55, **không phải** số nguyên 7. Phép `'7' - '0'` cho 7 vì chữ số ASCII liên tiếp; kỹ thuật này chỉ nên dùng khi đầu vào chắc chắn là `'0'` đến `'9'`.
4. `letter + 1` có kiểu `int` nên in `66`; ép về `char` mới in `B`.

## 3. UTF-16: đơn vị mã, mã điểm và cặp surrogate

### 3.1. Unicode code point không đồng nhất với `char`

Unicode gán **mã điểm (*code point*)** cho các thành phần văn bản; cách mã hóa **UTF-16** dùng một hoặc hai đơn vị mã 16 bit cho mỗi *Unicode scalar value*.

- Trong **BMP** (*Basic Multilingual Plane*, `U+0000`–`U+FFFF`), các mã điểm **ngoài vùng surrogate** được biểu diễn bằng **một** đơn vị mã, tương ứng một `char`. Ví dụ: `U+0041` (`A`), `U+00E9` (`é`), `U+4E2D` (`中`).
- Các mã điểm thuộc **supplementary planes**, từ `U+10000` đến `U+10FFFF`, cần **hai** đơn vị mã UTF-16: một *high surrogate* và một *low surrogate*. Ví dụ: 😀 `U+1F600` = `D83D DE00`.
- Vùng `U+D800`–`U+DFFF` được dành riêng cho surrogate. Đây là các giá trị **hợp lệ của kiểu `char`**, nhưng bản thân mỗi giá trị **không phải một Unicode scalar value độc lập**.

| Phạm vi đơn vị mã | Vai trò |
|---|---|
| `0000`–`D7FF` | Một mã điểm BMP ngoài surrogate |
| `D800`–`DBFF` | **High surrogate**: nửa đầu của cặp |
| `DC00`–`DFFF` | **Low surrogate**: nửa sau của cặp |
| `E000`–`FFFF` | Một mã điểm BMP ngoài surrogate |

Chữ “đơn vị mã” mô tả cấu trúc biểu diễn. Một phần tử `char` giữ mã `0xD83D` hoàn toàn hợp lệ về mặt kiểu Java, nhưng không đại diện riêng lẻ cho biểu tượng 😀. Muốn làm việc với mã điểm `U+1F600`, nên dùng `int`.

### 3.2. Cơ chế ghép hai đơn vị mã

Đối với mã điểm `U` từ `0x10000` đến `0x10FFFF`, đặt `U' = U - 0x10000`:

- High surrogate = `0xD800 + (U' >>> 10)`.
- Low surrogate = `0xDC00 + (U' & 0x3FF)`.

Với `U+1F600`, `U' = 0xF600`, high surrogate `0xD83D` và low surrogate `0xDE00`. Thực tế, dùng API `Character.toChars(codePoint)` để tạo cặp và `Character.toCodePoint(high, low)` để khôi phục mã điểm; không nên tự viết công thức trừ khi đang xây dựng thư viện mã hóa.

Java cung cấp `Character.isHighSurrogate(char)`, `Character.isLowSurrogate(char)`, `Character.isSurrogatePair(char, char)`, `Character.isSupplementaryCodePoint(int)` và `Character.charCount(int)` để kiểm tra và thao tác đúng.

### 3.3. Vì sao một ký tự biểu tượng làm `String.length()` tăng 2?

Trong Java, `String.length()` trả về **số đơn vị mã UTF-16**, không phải số mã điểm và càng không bảo đảm bằng số ký tự hiển thị. `String.charAt(index)` lấy **một** đơn vị mã; `String.codePointAt(index)` lấy mã điểm bắt đầu ở chỉ số UTF-16 tương ứng và ghép cặp surrogate hợp lệ khi có thể.

Ví dụ độc lập, tạo tệp `Utf16PairDemo.java`:

~~~java
public class Utf16PairDemo {
    public static void main(String[] args) {
        String smile = new String(Character.toChars(0x1F600));
        String text = "A" + smile + "Z";

        System.out.println("units=" + text.length());
        System.out.println("points="
                + text.codePointCount(0, text.length()));
        System.out.printf("pair=%04X %04X%n",
                (int) text.charAt(1), (int) text.charAt(2));
        System.out.printf("pointAt1=U+%X%n", text.codePointAt(1));
        System.out.println("validPair=" + Character.isSurrogatePair(
                text.charAt(1), text.charAt(2)));
        System.out.println("pointUnits="
                + Character.charCount(text.codePointAt(1)));
        System.out.println("sameSmile="
                + smile.equals(text.substring(1, 3)));
    }
}
~~~

~~~bash
javac Utf16PairDemo.java
java Utf16PairDemo
~~~

Đầu ra chính xác:

~~~text
units=4
points=3
pair=D83D DE00
pointAt1=U+1F600
validPair=true
pointUnits=2
sameSmile=true
~~~

Chuỗi có ba mã điểm `A`, 😀, `Z` nhưng bốn đơn vị mã: `0041 D83D DE00 005A`. Chỉ số `1` và `2` cùng thuộc **một** mã điểm 😀. `text.substring(1, 3)` lấy đủ hai đơn vị mã, còn `substring(1, 2)` chỉ lấy high surrogate và tạo chuỗi không chứa biểu tượng hoàn chỉnh.

Đặc biệt, `charAt(2)` trả **low surrogate**, trong khi `codePointAt(2)`, do bắt đầu ngay ở low surrogate mà không nhìn ngược để ghép với high surrogate trước đó, trả giá trị low surrogate như một `int`. Vì vậy, phải truyền **chỉ số bắt đầu của mã điểm** khi sử dụng `codePointAt`.

## 4. Duyệt chuỗi đúng khi có ký tự ngoài BMP

Vòng lặp phổ biến sau đọc từng **đơn vị mã**:

~~~java
for (int i = 0; i < text.length(); i++) {
    char unit = text.charAt(i);
    // Chỉ thích hợp khi chủ đích là xử lý UTF-16 code unit.
}
~~~

Đây là **đoạn mã minh họa**, giả sử biến `text` đã được khai báo. Nếu mục đích là xử lý từng **mã điểm Unicode**, tăng chỉ số bằng `Character.charCount(codePoint)`:

~~~java
for (int i = 0; i < text.length();) {
    int codePoint = text.codePointAt(i);
    // Xử lý codePoint dưới dạng int.
    i += Character.charCount(codePoint);
}
~~~

Đây cũng là **đoạn minh họa**. Với dữ liệu chuỗi thông thường, có thể dùng `text.codePoints()` để nhận `IntStream`, song cần hiểu quy tắc đối với surrogate lẻ được giải thích ở phần tiếp theo.

### Ví dụ độc lập: lặp theo code point

Tạo tệp `CodePointIterationDemo.java`:

~~~java
public class CodePointIterationDemo {
    public static void main(String[] args) {
        String text = "A"
                + new String(Character.toChars(0x1F642))
                + "\u00E9";

        System.out.println("units=" + text.length());
        System.out.println("points=" + text.codePoints().count());

        for (int i = 0; i < text.length();) {
            int cp = text.codePointAt(i);
            System.out.printf("index=%d codePoint=U+%X%n", i, cp);
            i += Character.charCount(cp);
        }
    }
}
~~~

~~~bash
javac CodePointIterationDemo.java
java CodePointIterationDemo
~~~

Đầu ra chính xác:

~~~text
units=4
points=3
index=0 codePoint=U+41
index=1 codePoint=U+1F642
index=3 codePoint=U+E9
~~~

`U+1F642` là mã điểm ngoài BMP nên chiếm hai đơn vị mã ở chỉ số UTF-16 `1` và `2`; `é` (dạng đơn mã điểm `U+00E9`) bắt đầu ở chỉ số `3`. Nếu cần di chuyển theo mã điểm thay vì tự tính số đơn vị mã, Java còn cung cấp `String.offsetByCodePoints`.

Không được lấy `text.length()` làm số “ký tự con người nhìn thấy”, chẳng hạn để kiểm tra tên hiển thị tối đa 20 ký tự: `length()` đếm đơn vị mã UTF-16, `codePointCount` đếm mã điểm, còn **grapheme cluster** mới gần với một ký tự cảm nhận của người dùng.

## 5. Một code point chưa chắc là một ký tự hiển thị

Ngay cả khi đã chuyển từ `char` sang mã điểm, vấn đề đếm ký tự văn bản vẫn chưa kết thúc:

- Chữ `é` có thể là **một mã điểm** `U+00E9`, hoặc hai mã điểm `U+0065` (`e`) và `U+0301` (dấu sắc kết hợp).
- Một số biểu tượng emoji được tạo từ nhiều mã điểm kết hợp với dấu nối `U+200D` (*zero-width joiner*), biến thể hoặc thành phần khác, nhưng hiển thị như một biểu tượng.
- Văn bản tiếng Việt và các ngôn ngữ khác có thể có dấu tổ hợp, quy tắc biên ký tự và cách sắp xếp phụ thuộc ngôn ngữ.

Do đó:

| Câu hỏi | Khái niệm/API thích hợp |
|---|---|
| Có bao nhiêu đơn vị UTF-16? | `String.length()` |
| Lấy đơn vị mã tại chỉ số UTF-16? | `String.charAt(index)` |
| Mã điểm bắt đầu ở vị trí UTF-16 này là gì? | `String.codePointAt(index)` |
| Có bao nhiêu mã điểm theo cách đếm UTF-16? | `String.codePointCount(0, length)` |
| Duyệt mã điểm | `String.codePoints()` hoặc `codePointAt` + `Character.charCount` |
| Đếm phần tử văn bản hiển thị, tách theo cụm tự vị? | Thuật toán phân đoạn *extended grapheme cluster* phù hợp chuẩn Unicode và phiên bản dữ liệu áp dụng |
| So sánh/sắp xếp chuỗi theo ngôn ngữ? | Quy tắc `Collator`/`Locale`, không dựa trên thứ tự mã số `char` |

Chuẩn hóa Unicode, ví dụ NFC/NFD qua `java.text.Normalizer`, có thể cần thiết để xử lý chuỗi tương đương ở mức biểu diễn. Tuy nhiên, **chuẩn hóa** và **phân đoạn grapheme** là hai thao tác khác nhau: chuẩn hóa không làm cho phép đếm `char` đột nhiên trở thành phép đếm ký tự hiển thị.

## 6. Unicode escape, char literal và dữ liệu từ bên ngoài

### 6.1. Viết literal `char`

Một literal `char` dùng **dấu nháy đơn** và đúng một đơn vị mã UTF-16, ví dụ `'A'`, `'7'`, `'\n'`, `'\u4E2D'`. Literal chuỗi dùng dấu nháy kép, ví dụ `"A"`, `"ABC"`. Biểu tượng ngoài BMP như 😀 không thể nằm trong một literal `char` độc lập vì cần hai đơn vị mã; hãy dùng `String` và `Character.toChars(0x1F600)` khi cần xây chuỗi bằng mã điểm.

Các escape quen thuộc như `'\n'`, `'\t'`, `'\\'` và `'\''` đều là literal `char` hợp lệ. Lưu ý Java xử lý **Unicode escape `\uXXXX` ở giai đoạn rất sớm**, trước khi phân tích token. Vì thế cách viết trực tiếp escape Unicode của ký tự xuống dòng `U+000A` trong source Java có thể làm dòng nguồn bị tách bất ngờ; khi cần ký tự xuống dòng, dùng `'\n'` thay cho escape Unicode của nó.

Một `char` chỉ là giá trị đơn vị mã, không nói toàn bộ văn bản sẽ được lưu trên file bằng UTF-16. Khi ghi file, gửi mạng hoặc chuyển chuỗi thành `byte[]`, hãy chọn charset rõ ràng, chẳng hạn `StandardCharsets.UTF_8`. Không lấy một `char` rồi cho rằng cast sang `byte` luôn giữ được ký tự; cast có thể mất các bit cao và hoàn toàn không phải phép mã hóa UTF-8.

### 6.2. Có thể tồn tại surrogate đứng lẻ

Java `String` có thể chứa một high surrogate hoặc low surrogate **không ghép cặp**. Đây là chuỗi có đơn vị mã UTF-16 nhưng **không phải một chuỗi Unicode scalar value hợp lệ đầy đủ**. Trong trường hợp đó:

- `String.length()` vẫn đếm đơn vị mã, kể cả surrogate lẻ.
- `String.codePointAt` và `String.codePoints()` ghép **cặp hợp lệ**; với surrogate không ghép cặp, chúng có thể trả chính giá trị surrogate dưới dạng `int`.
- `Character.isValidCodePoint(int)` chỉ kiểm tra số có nằm trong miền code point `U+0000`–`U+10FFFF`; không có nghĩa đã loại trừ giá trị surrogate. Kiểm tra *Unicode scalar value* cần loại trừ khoảng `U+D800`–`U+DFFF`.
- Khi trao đổi dữ liệu giữa hệ thống hoặc xuất ra charset khác, cần một chính sách xử lý đầu vào không hợp lệ thay vì ngầm định mọi `String` đều chỉ chứa mã điểm hợp lệ.

Ví dụ độc lập, tạo tệp `UnpairedSurrogateDemo.java`:

~~~java
public class UnpairedSurrogateDemo {
    public static void main(String[] args) {
        char high = (char) 0xD83D;
        String broken = String.valueOf(high);
        int cp = broken.codePointAt(0);

        System.out.println("units=" + broken.length());
        System.out.printf("returned=U+%X%n", cp);
        System.out.println("high=" + Character.isHighSurrogate(high));
        System.out.println("validCodePoint="
                + Character.isValidCodePoint(cp));
        System.out.println("scalar=" + isScalarValue(cp));
    }

    private static boolean isScalarValue(int cp) {
        return cp >= 0 && cp <= 0x10FFFF
                && !(cp >= 0xD800 && cp <= 0xDFFF);
    }
}
~~~

~~~bash
javac UnpairedSurrogateDemo.java
java UnpairedSurrogateDemo
~~~

Đầu ra chính xác:

~~~text
units=1
returned=U+D83D
high=true
validCodePoint=true
scalar=false
~~~

Ví dụ cho thấy sự khác nhau giữa **miền mã điểm mà API chấp nhận** và **một mã điểm scalar hợp lệ để biểu diễn Unicode**. Hãy dùng kiểu `int` cho mã điểm và kiểm tra cặp surrogate khi nguồn dữ liệu có thể bị hỏng.

## 7. Nên dùng `char` khi nào, và khi nào không?

**Dùng `char`** khi chương trình thật sự cần xử lý **một đơn vị mã UTF-16**, tương tác với `charAt`, bộ đệm `char[]`, API ký tự tương ứng hoặc các ký hiệu ASCII đơn giản trong một giao thức đã giới hạn ký tự. Ví dụ, kiểm tra dấu phân cách `','` hay `':'` là một tình huống hợp lý.

**Dùng `int` cho mã điểm** khi bài toán cần duyệt, phân loại hoặc biến đổi văn bản Unicode vượt BMP; kết hợp `codePointAt`/`codePoints` với các phương thức `Character` nhận tham số `int`, chẳng hạn `Character.isLetter(int codePoint)`. Một số phép xử lý Unicode có API overload nhận `char` nhưng sẽ bỏ lỡ ký tự ngoài BMP: khi cần phủ toàn Unicode, chọn overload `int`.

**Dùng `String` cho văn bản** như tên người, chuỗi nội dung, email, mã định danh hoặc một biểu tượng bất kỳ. `String` có thể chứa nhiều đơn vị mã và vẫn cần thao tác đúng theo yêu cầu: duyệt code point, chuẩn hóa, phân đoạn grapheme, so sánh theo locale.

**Dùng `int`, `long`, `BigInteger` cho đại lượng số nguyên** thông thường thay vì tận dụng `char` chỉ vì nó không dấu. `char` có tính chất số học, nhưng tên kiểu và API của nó diễn đạt ý nghĩa **đơn vị mã văn bản**, không phải số lượng phi âm tổng quát.

### Bốn lỗi phổ biến

1. **“`char` chứa được mọi ký tự Unicode vì có 16 bit.”** Không đúng: Unicode có mã điểm ngoài BMP cần hai đơn vị UTF-16.
2. **“`String.length()` là số ký tự người dùng nhìn thấy.”** Không đúng: đó là số đơn vị mã UTF-16; số code point hoặc grapheme cluster có thể khác.
3. **“`charAt(i)` luôn trả một ký tự đầy đủ.”** Không đúng: nó có thể trả high/low surrogate. Khi duyệt mã điểm, hãy tăng `i` theo `Character.charCount(cp)`.
4. **“`char` là số không dấu nên dùng thay cho `unsigned short` ở mọi bài toán.”** Không phù hợp: kiểu `char` gắn với code unit; nếu xử lý trường số không dấu 16 bit của giao thức, thường giải mã sang `int` để tính toán và thể hiện rõ miền 0..65535.

## 8. Tự kiểm tra kiến thức

1. `char` có bao nhiêu bit, và miền số nguyên của nó là gì?
2. Vì sao `char letter = 'A'; int n = letter + 1;` hợp lệ nhưng `char next = letter + 1;` lại không?
3. Vì sao `"A😀Z".length()` bằng `4`, nhưng số Unicode code point trong chuỗi là `3`?
4. `String.charAt` khác `String.codePointAt` ở đâu? Vì sao mã điểm nên được giữ trong `int`?
5. Một chuỗi có high surrogate đứng lẻ có thể tồn tại trong Java không? `Character.isValidCodePoint` có bảo đảm không còn surrogate lẻ không?
6. Khi người dùng giới hạn độ dài tên hiển thị theo ký tự cảm nhận, nên đếm UTF-16 code unit, code point hay grapheme cluster?

**Đáp án gợi ý:** (1) 16 bit, 0–65.535; (2) phép cộng được nâng sang `int`, thu hẹp cần explicit cast; (3) emoji nằm ngoài BMP chiếm 2 code unit; (4) `charAt` đọc một code unit, `codePointAt` ghép surrogate hợp lệ để đọc code point, `int` chứa được trên `U+FFFF`; (5) có thể có surrogate lẻ, `isValidCodePoint` kiểm tra miền số nên chưa đủ để loại surrogate; (6) chọn phép phân đoạn grapheme cluster phù hợp Unicode và yêu cầu sản phẩm.

**Ghi nhớ:** `char` **là một số nguyên không dấu 16 bit về cơ chế của Java**, đồng thời **là một đơn vị mã UTF-16 về ý nghĩa văn bản**. Với Unicode hiện đại, một mã điểm có thể cần hai `char` và một ký tự hiển thị có thể cần nhiều mã điểm.