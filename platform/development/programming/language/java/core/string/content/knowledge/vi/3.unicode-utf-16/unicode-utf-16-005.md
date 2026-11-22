# Java String có thể chứa surrogate không ghép cặp

Trong Java, `String` lưu một **dãy đơn vị mã UTF-16 (UTF-16 code units)**. Mỗi đơn vị mã tương ứng một `char` 16 bit. Java **không bắt buộc** mọi `String` đều biểu diễn một chuỗi ký tự Unicode hợp lệ: một chuỗi vẫn có thể chứa **high surrogate** hoặc **low surrogate** đứng riêng lẻ, không ghép đúng cặp. Tình trạng này gọi là *unpaired surrogate* hoặc *unpaired surrogate code unit*.

Đây là điểm quan trọng khi cắt chuỗi, duyệt chuỗi, tính độ dài, so sánh và chuyển mã sang UTF-8. Một `String` có thể hoàn toàn hợp lệ về **kiểu Java**, nhưng chứa một dãy UTF-16 **không well-formed** (*ill-formed UTF-16*).

## 1. Phân biệt `char`, UTF-16 code unit, code point và Unicode scalar value

- **`char` trong Java:** giá trị nguyên không dấu 16 bit, từ `0x0000` đến `0xFFFF`. `String.length()` đếm số đơn vị mã `char` này, không đếm số ký tự hiển thị.
- **Unicode code point:** vị trí trong không gian mã `U+0000` đến `U+10FFFF`. Java thường biểu diễn code point bằng `int`.
- **Unicode scalar value:** code point **không thuộc** dải surrogate `U+D800`–`U+DFFF`; đây là những giá trị có thể mã hóa thành một ký tự Unicode riêng trong UTF-8.
- **UTF-16:** scalar value ở BMP không thuộc vùng surrogate dùng một đơn vị mã; scalar value từ `U+10000` đến `U+10FFFF` dùng **hai đơn vị mã**, lần lượt là high surrogate và low surrogate.

Các khoảng surrogate:

| Nhóm | Khoảng giá trị UTF-16 | Vai trò |
|---|---|---|
| High surrogate (*leading surrogate*) | `U+D800`–`U+DBFF` | Đơn vị mã đầu tiên của cặp |
| Low surrogate (*trailing surrogate*) | `U+DC00`–`U+DFFF` | Đơn vị mã thứ hai của cặp |
| Cặp hợp lệ | High rồi đến Low | Cùng biểu diễn một scalar value ngoài BMP |
| Không ghép cặp | High không theo sau bởi Low; hoặc Low không có High đi ngay trước | Không tạo được một scalar value từ đơn vị mã đó |

Ví dụ emoji 😀 có code point `U+1F600`. Trong UTF-16, nó dùng hai `char`: `U+D83D` (*high*) và `U+DE00` (*low*). Vì thế, một `String` chỉ chứa emoji này có `length() == 2`, nhưng `codePointCount(0, length()) == 1`.

Công thức UTF-16 khi mã hóa code point ngoài BMP (chỉ để hiểu cơ chế):

```text
x    = codePoint - 0x10000
high = 0xD800 + (x >>> 10)
low  = 0xDC00 + (x & 0x3FF)
```

Các code unit surrogate **không đại diện cho ký tự độc lập**. High `U+D83D` đứng một mình không phải là emoji 😀. Không nên nhầm mã surrogate `U+D83D` với code point emoji `U+1F600`.

## 2. Vì sao Java vẫn cho phép một `String` chứa surrogate lẻ?

API `String` hoạt động dựa trên chuỗi đơn vị mã UTF-16, và một số thao tác nhận/trả về các đơn vị mã đó mà không bắt buộc kiểm tra tính well-formed của cả chuỗi. Một `char` có thể có giá trị nằm trong khoảng surrogate; Java không cấm đưa `char` đó vào `String`.

Có ít nhất ba cách làm xuất hiện surrogate không ghép cặp:

### Tạo trực tiếp từ một `char`

```java
char high = (char) 0xD83D;
char low = (char) 0xDE00;

String onlyHigh = String.valueOf(high);
String onlyLow = new String(new char[] {low});
```

Mỗi chuỗi trên dài một đơn vị mã, nhưng không tạo thành cặp surrogate hoàn chỉnh.

### Cắt giữa một cặp đúng

```java
String emoji = new String(Character.toChars(0x1F600)); // Hai UTF-16 code units
String firstHalf = emoji.substring(0, 1);              // High surrogate đứng riêng
String secondHalf = emoji.substring(1, 2);             // Low surrogate đứng riêng
String restored = firstHalf + secondHalf;               // Cặp được ghép lại đúng thứ tự
```

Cả `substring` lẫn `charAt` dùng **chỉ số đơn vị mã**. Chúng không bảo đảm ranh giới trùng với ranh giới code point. `firstHalf` và `secondHalf` đều là `String` có thể được tạo và lưu bình thường, dù mỗi chuỗi là UTF-16 không well-formed. Khi ghép đúng thứ tự, `restored` lại chứa cặp hợp lệ.

### Thêm đơn vị mã bằng `StringBuilder` hoặc nhận dữ liệu đã có sẵn

```java
StringBuilder builder = new StringBuilder();
builder.append((char) 0xD83D);
builder.append('X');
String malformed = builder.toString();
```

Trong `malformed`, high surrogate đi trước `X`, không có low surrogate tương ứng. Dữ liệu cắt từ hệ thống khác hoặc các API thao tác theo `char` cũng có thể mang tình trạng này. Không phải việc tạo thành công đối tượng `String` là đã xác nhận Unicode well-formed.

Lưu ý: sau khi cắt hoặc ghép chuỗi, cùng một đơn vị mã có thể chuyển từ trạng thái lẻ sang hợp lệ hoặc ngược lại tùy **hai đơn vị mã liền kề**, vì điều kiện ghép cặp phụ thuộc vào thứ tự.

## 3. Các API đếm và duyệt chuỗi có hành vi gì?

| API | Đơn vị và hành vi | Điều cần nhớ |
|---|---|---|
| `length()` | Số UTF-16 code units | Một code point ngoài BMP thường chiếm 2 |
| `charAt(i)` | Lấy một code unit ở chỉ số `i` | Có thể trả về một nửa cặp |
| `substring(begin, end)` | Cắt theo chỉ số code unit | Có thể tách đôi cặp |
| `chars()` | Stream các giá trị `char` mở rộng thành `int` | Không ghép surrogate pair |
| `codePointAt(i)` | Ghép High+Low khi có cặp hợp lệ tại vị trí đó; nếu không, trả về giá trị của một code unit | Có thể trả về giá trị thuộc dải surrogate |
| `codePoints()` | Ghép các cặp hợp lệ thành một `int`; với đơn vị mã không ghép cặp, phát ra chính giá trị code unit đó | **Không** phải phép kiểm tra Unicode well-formed |
| `codePointCount(begin, end)` | Đếm cặp hợp lệ là một, code unit không ghép cặp là một | Kết quả vẫn được trả về khi chuỗi ill-formed |
| `offsetByCodePoints(index, delta)` | Di chuyển theo cách Java nhận diện code point trong chuỗi UTF-16 | Hữu ích để tránh cắt cặp hợp lệ nhưng không sửa dữ liệu đã hỏng |

Một điểm dễ nhầm: `Character.isValidCodePoint(0xD83D)` trả về `true` vì giá trị nằm trong khoảng `0x0000`–`0x10FFFF` được API này chấp nhận. Tuy nhiên `U+D83D` **không phải Unicode scalar value** vì nó thuộc vùng surrogate. Do đó, **chỉ kiểm tra `isValidCodePoint` chưa đủ** để xác nhận có thể mã hóa như một ký tự Unicode độc lập.

Có thể kiểm tra một giá trị `int` là scalar value bằng điều kiện:

```java
static boolean isUnicodeScalarValue(int cp) {
    return Character.isValidCodePoint(cp)
            && !(cp >= 0xD800 && cp <= 0xDFFF);
}
```

Điều kiện đó áp dụng cho **một code point dạng `int`**. Với một `String`, phải duyệt và kiểm tra sự ghép cặp của các đơn vị mã UTF-16.

## 4. Kiểm tra một `String` có well-formed UTF-16 hay không

Quy tắc kiểm tra từ trái sang phải:

1. Gặp **high surrogate**, phải có ký tự kế tiếp và ký tự đó phải là **low surrogate**; tiêu thụ cả hai.
2. Gặp **low surrogate** mà chưa đi cùng high ngay trước nó, chuỗi **không hợp lệ**.
3. Gặp `char` không thuộc hai nhóm trên thì đi tiếp bình thường.
4. Hết chuỗi mà không có lỗi thì dãy UTF-16 well-formed; chuỗi rỗng cũng hợp lệ.

Với `n = s.length()`, thuật toán chạy `O(n)` và sử dụng `O(1)` bộ nhớ bổ sung.

### Ví dụ Java 17+ chạy độc lập

Lưu toàn bộ chương trình vào **`UnpairedSurrogateDemo.java`**:

```java
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.StringJoiner;

public class UnpairedSurrogateDemo {
    public static boolean isWellFormedUtf16(String s) {
        for (int i = 0; i < s.length(); i++) {
            char ch = s.charAt(i);

            if (Character.isHighSurrogate(ch)) {
                if (i + 1 == s.length()
                        || !Character.isLowSurrogate(s.charAt(i + 1))) {
                    return false;
                }
                i++; // Đã xử lý cả high và low surrogate
            } else if (Character.isLowSurrogate(ch)) {
                return false; // Low surrogate đứng riêng
            }
        }
        return true;
    }

    private static String units(String s) {
        StringJoiner result = new StringJoiner(" ");
        for (int i = 0; i < s.length(); i++) {
            result.add(String.format("U+%04X", (int) s.charAt(i)));
        }
        return result.toString();
    }

    private static String codePointValues(String s) {
        StringJoiner result = new StringJoiner(" ");
        s.codePoints().forEach(cp ->
                result.add(String.format("U+%04X", cp)));
        return result.toString();
    }

    private static String utf8EncodingStatus(String s) {
        CharsetEncoder encoder = StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        try {
            encoder.encode(CharBuffer.wrap(s));
            return "OK";
        } catch (CharacterCodingException ex) {
            return "malformed input";
        }
    }

    public static void main(String[] args) {
        String emoji = new String(Character.toChars(0x1F600));
        String high = emoji.substring(0, 1);
        String low = emoji.substring(1, 2);
        String restored = high + low;
        String mixed = "A" + high + "B";

        System.out.println("emoji.length(): " + emoji.length());
        System.out.println("emoji.codePointCount(): "
                + emoji.codePointCount(0, emoji.length()));
        System.out.println("emoji units: " + units(emoji));
        System.out.println("high units: " + units(high));
        System.out.println("low units: " + units(low));
        System.out.println("high codePoints: " + codePointValues(high));
        System.out.println("emoji well-formed: " + isWellFormedUtf16(emoji));
        System.out.println("high well-formed: " + isWellFormedUtf16(high));
        System.out.println("low well-formed: " + isWellFormedUtf16(low));
        System.out.println("restored well-formed: " + isWellFormedUtf16(restored));
        System.out.println("mixed well-formed: " + isWellFormedUtf16(mixed));
        System.out.println("UTF-8 emoji: " + utf8EncodingStatus(emoji));
        System.out.println("UTF-8 high: " + utf8EncodingStatus(high));
        System.out.println("high isValidCodePoint: "
                + Character.isValidCodePoint(high.charAt(0)));
        System.out.println("high isSurrogate: "
                + Character.isSurrogate(high.charAt(0)));
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac -encoding UTF-8 UnpairedSurrogateDemo.java
java UnpairedSurrogateDemo
```

Kết quả:

```text
emoji.length(): 2
emoji.codePointCount(): 1
emoji units: U+D83D U+DE00
high units: U+D83D
low units: U+DE00
high codePoints: U+D83D
emoji well-formed: true
high well-formed: false
low well-formed: false
restored well-formed: true
mixed well-formed: false
UTF-8 emoji: OK
UTF-8 high: malformed input
high isValidCodePoint: true
high isSurrogate: true
```

**Đọc kết quả:** `high.codePoints()` vẫn tạo được một phần tử số nguyên `0xD83D`; điều đó **không xác nhận chuỗi well-formed**. Bộ mã hóa UTF-8 ở chế độ `REPORT` từ chối surrogate lẻ vì nó không biểu diễn một Unicode scalar value. Khi `high` và `low` được ghép đúng thứ tự, cùng hai code unit lại tạo một cặp hợp lệ.

Hàm `isWellFormedUtf16` kiểm tra tính hợp lệ của **chuỗi đơn vị mã**, chứ không kiểm tra dữ liệu có ý nghĩa ngôn ngữ hoặc có hiển thị được dưới font hiện tại hay không.

## 5. Hậu quả khi mã hóa sang UTF-8 hoặc trao đổi dữ liệu

UTF-8 mã hóa các Unicode scalar value. Một surrogate đứng riêng lẻ trong `String` không có biểu diễn UTF-8 hợp lệ như một ký tự độc lập. Khi chuyển đổi, kết quả phụ thuộc **API và chính sách xử lý dữ liệu lỗi**:

- **Chính sách `REPORT`:** bộ mã hóa báo lỗi `MalformedInputException` (một loại `CharacterCodingException`), như chương trình trên. Đây là lựa chọn phù hợp khi cần phát hiện dữ liệu không hợp lệ.
- **Chính sách `REPLACE`:** bộ mã hóa thay phần không hợp lệ bằng các byte thay thế được cấu hình; lúc đó dữ liệu sau chuyển đổi không còn giữ nguyên surrogate lẻ. Byte thay thế của encoder không nên tự giả định luôn là một ký tự Unicode cố định.
- **Các hàm tiện ích như `getBytes(StandardCharsets.UTF_8)`:** có thể thay thế dữ liệu lỗi thay vì báo lỗi; không dùng kết quả thành công của hàm này làm bằng chứng rằng chuỗi ban đầu well-formed.

Ở chiều ngược lại, khi **giải mã** byte UTF-8 lỗi, bộ giải mã có thể *report* hoặc thay bằng ký tự `U+FFFD` (*replacement character*) tùy API/chính sách. **U+FFFD là một scalar value hợp lệ**, khác hoàn toàn với high surrogate/low surrogate đứng riêng. Không được gọi surrogate lẻ chính là U+FFFD.

Quá trình tuần tự hóa sang JSON, XML, giao tiếp API hay lưu trữ cũng cần xét hợp đồng của thư viện nhận dữ liệu. Một số thư viện có thể từ chối, thay thế, hoặc biểu diễn escape theo quy tắc riêng; không giả định mọi hệ thống sẽ tự xử lý giống nhau. Nếu hệ thống yêu cầu Unicode well-formed, hãy kiểm tra hoặc đặt chính sách xử lý lỗi rõ ràng **trước ranh giới truyền dữ liệu**.

### Có nên tự động thay surrogate lẻ?

Tùy yêu cầu nghiệp vụ:

- **Từ chối** dữ liệu không well-formed: phù hợp nếu giữ nguyên nghĩa và tính nhất quán dữ liệu quan trọng.
- **Thay mỗi đơn vị mã không ghép cặp bằng U+FFFD:** phù hợp khi cần tiếp tục hiển thị và chấp nhận mất thông tin; phải làm đúng từng cặp/đơn vị mã.
- **Giữ nguyên** dãy code unit để điều tra hoặc xử lý nội bộ: chỉ nên làm khi các bước kế tiếp hiểu rõ đặc tính UTF-16 không well-formed.

Không sửa bằng cách xóa *mọi* `char` thuộc dải surrogate: làm vậy sẽ xóa cả **cặp hợp lệ** và phá hỏng mọi ký tự ngoài BMP. Cũng không nên nối tùy ý surrogate lẻ với bất kỳ surrogate nào ở xa: một cặp hợp lệ phải là **high ngay trước low**.

## 6. Cắt chuỗi an toàn theo ranh giới code point

Nếu chuỗi đầu vào đã well-formed và cần cắt một số code point đầu tiên, `offsetByCodePoints` giúp tìm chỉ số UTF-16 đúng ranh giới cặp:

```java
String text = "A" + new String(Character.toChars(0x1F600)) + "B";
int end = text.offsetByCodePoints(0, 2);
String prefix = text.substring(0, end); // Chứa A và emoji 😀
System.out.println(prefix.codePointCount(0, prefix.length())); // 2
```

Nếu thay bằng `text.substring(0, 2)`, kết quả gồm `A` và **high surrogate của emoji**, thiếu low surrogate: đây là chuỗi ill-formed. Một phép cắt theo số code point cũng **không tự sửa** chuỗi đầu vào vốn đã có surrogate lẻ.

Ngoài ra, *code point không đồng nhất với ký tự người dùng nhìn thấy* (*grapheme cluster*). Ví dụ chữ cái kèm dấu kết hợp hoặc một emoji được ghép từ nhiều code point có thể cần xử lý phân đoạn văn bản cấp cao hơn. `offsetByCodePoints` giải quyết **ranh giới UTF-16 surrogate pair**, chưa giải quyết toàn bộ quy tắc phân đoạn grapheme.

## 7. Những nhầm lẫn phổ biến

| Khẳng định/giả định | Vì sao sai | Cách nghĩ đúng |
|---|---|---|
| “`String` luôn chứa Unicode hợp lệ.” | `String` vẫn chứa được surrogate lẻ. | Khi cần tính hợp lệ Unicode, kiểm tra UTF-16 well-formed riêng. |
| “`char` luôn là một ký tự hiển thị.” | Nó chỉ là một code unit 16 bit. | Ký tự ngoài BMP có hai `char`; grapheme có thể có nhiều code point. |
| “`length()` đếm số code point.” | `length()` đếm UTF-16 code units. | Dùng `codePointCount` cho cách đếm của API Java; lưu ý surrogate lẻ vẫn được đếm. |
| “`codePoints()` chỉ phát Unicode scalar value.” | Stream này có thể phát giá trị surrogate lẻ. | Kiểm tra well-formed UTF-16 hoặc loại dải `D800`–`DFFF` khi xét scalar value. |
| “`Character.isValidCodePoint` là đủ để xác thực.” | Nó trả về `true` cho số trong dải surrogate. | Loại trừ `U+D800`–`U+DFFF` khi kiểm tra một scalar value. |
| “Cắt `substring` luôn ở giữa các ký tự đầy đủ.” | Ranh giới được tính theo code unit. | Cân nhắc `offsetByCodePoints` nếu mục tiêu là code point. |
| “Emoji biến thành `?`/`�` chỉ là vấn đề font.” | Có thể đã xảy ra thay thế dữ liệu trong lúc chuyển mã lỗi. | Phân biệt code unit gốc, byte được mã hóa, decoder và font. |
| “Xóa mọi surrogate là sửa dữ liệu.” | Xóa cả các cặp hợp lệ. | Duyệt từng cặp, xử lý riêng surrogate **không ghép cặp**. |

## 8. Tình huống luyện tập

Cho một chuỗi được tạo như sau:

```java
String face = new String(Character.toChars(0x1F600));
String a = face.substring(0, 1);
String b = face.substring(1, 2);
String c = "x" + a + b + "y";
String d = a + "x" + b;
```

1. `a.length()`, `b.length()` và `face.length()` lần lượt là bao nhiêu?
2. Các chuỗi `face`, `a`, `b`, `c` và `d` có well-formed UTF-16 không?
3. `c.codePointCount(0, c.length())` có giá trị bao nhiêu?
4. Nếu mã hóa `d` sang UTF-8 bằng một `CharsetEncoder` với `CodingErrorAction.REPORT`, thao tác có thành công không?

**Đáp án:** (1) `1`, `1`, `2`. (2) `face` và `c` well-formed; `a`, `b` và `d` không well-formed vì chứa surrogate lẻ. (3) `3` code point: `x`, emoji, `y`. (4) Không; high và low bị ngăn bởi `x` nên không tạo cặp, và encoder báo malformed input.

**Ghi nhớ:** Kiểu `String` của Java chứa một chuỗi UTF-16 code units; sự tồn tại của chuỗi **không đảm bảo** chuỗi đó là UTF-16 well-formed. Một cặp surrogate hợp lệ cần đúng thứ tự **high + low liền kề**. Khi cắt hoặc duyệt, biết API đang xử lý `char` hay code point; khi chuyển sang UTF-8 hay giao tiếp với hệ thống khác, xác định rõ chính sách **báo lỗi, thay thế hoặc từ chối** surrogate không ghép cặp.
