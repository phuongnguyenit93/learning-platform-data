# appendCodePoint và dữ liệu ngoài BMP trong StringBuilder

Khi dựng chuỗi Java từ dữ liệu Unicode, không phải mọi “ký tự” đều vừa trong một `char`. Một code point ngoài **Basic Multilingual Plane (BMP)**, chẳng hạn emoji 😊 (`U+1F60A`), cần **hai code unit UTF-16**. Nếu ép code point đó về `char` rồi gọi `StringBuilder.append(char)`, dữ liệu bị cắt mất. `StringBuilder.appendCodePoint(int)` là API dành cho việc thêm **một code point Unicode** vào bộ dựng chuỗi, sử dụng một hoặc hai code unit UTF-16 theo giá trị code point.

Mục tiêu của bài là hiểu cơ chế, biết khi nào dùng `appendCodePoint` thay cho `append`, phân biệt dữ liệu ngoài BMP với surrogate pair, kiểm tra giá trị đầu vào, và tránh nhầm code point với cụm ký tự hiển thị (*grapheme cluster*).

## 1. BMP, code point, `char` và UTF-16

Một **Unicode code point** là giá trị số được ký hiệu `U+XXXX`, thuộc khoảng `U+0000` đến `U+10FFFF`. Java thường biểu diễn giá trị code point bằng `int`. `char` trong Java chỉ chứa **một đơn vị mã UTF-16 16 bit**, nên không thể chứa trực tiếp mọi code point Unicode.

Unicode chia không gian code point thành các *plane*. **BMP**, hay Plane 0, bao phủ `U+0000`–`U+FFFF`. Những plane còn lại chứa các code point lớn hơn `U+FFFF`, gọi là **supplementary code points**. Một số emoji, chữ lịch sử, ký hiệu âm nhạc và ký tự toán học thuộc các plane bổ sung.

Với UTF-16:

- Một code point thuộc BMP **không ở vùng surrogate** (`U+D800`–`U+DFFF`) được biểu diễn bằng **một code unit**.
- Một code point ngoài BMP (`U+10000`–`U+10FFFF`) được biểu diễn bằng **hai code unit**: một *high surrogate* (`0xD800`–`0xDBFF`) và một *low surrogate* (`0xDC00`–`0xDFFF`).
- Vùng surrogate là phần đặc biệt dành cho mã hóa UTF-16. Một giá trị như `U+D800` không phải **Unicode scalar value** hợp lệ để biểu diễn độc lập thành một ký tự văn bản Unicode hoàn chỉnh.

Ví dụ:

| Code point | Biểu diễn | Code unit UTF-16 | Ghi chú |
|---|---|---:|---|
| `U+0041` | `A` | 1 | Chữ Latin thuộc BMP |
| `U+00E9` | `é` | 1 | Ký tự dựng sẵn thuộc BMP |
| `U+1F60A` | 😊 | 2 | Emoji ngoài BMP: `D83D DE0A` |
| `U+1F1FB` | Regional indicator V | 2 | Một nửa của cờ 🇻🇳 |
| `U+1F1F3` | Regional indicator N | 2 | Một nửa còn lại của cờ 🇻🇳 |

Một flag emoji 🇻🇳 có **hai code point ngoài BMP**, tổng cộng **bốn code unit UTF-16**, nhưng thường được hiển thị thành **một grapheme cluster**. Như vậy: **số code unit ≠ số code point ≠ số ký tự người dùng cảm nhận**.

## 2. `StringBuilder.appendCodePoint(int)` thực hiện gì?

Chữ ký phương thức:

```java
StringBuilder appendCodePoint(int codePoint)
```

Đây là chữ ký API minh họa; `StringBuilder` có phương thức thực trả về chính builder để hỗ trợ gọi nối chuỗi kiểu `builder.appendCodePoint(cp).append("...")`.

Với giá trị code point trong phạm vi hợp lệ của API:

1. Nếu thuộc BMP (bao gồm cả mã surrogate đơn lẻ ở cấp độ API), phương thức thêm **một code unit `char`**.
2. Nếu là code point ngoài BMP, phương thức chuyển thành **cặp surrogate UTF-16** và thêm **hai code unit theo đúng thứ tự**.
3. Builder tăng độ dài theo **số code unit** đã thêm. Nội dung của builder thay đổi; phương thức trả về tham chiếu đến **cùng builder**.
4. Nếu giá trị ngoài khoảng code point Unicode do Java chấp nhận, chẳng hạn `-1` hay `0x110000`, phương thức ném `IllegalArgumentException`.

Do đó, với builder ban đầu rỗng:

```java
StringBuilder builder = new StringBuilder();
builder.appendCodePoint(0x41);       // A: thêm 1 char
builder.appendCodePoint(0x1F60A);    // 😊: thêm 2 char
```

Sau hai lời gọi, `builder.length() == 3` nhưng `builder.codePointCount(0, builder.length()) == 2`. Độ dài mà `StringBuilder.length()` trả về là số **code unit UTF-16**, không phải số code point.

`appendCodePoint` **không chuẩn hóa Unicode**, không kiểm tra ranh giới grapheme cluster và không chuyển chữ hoa/thường. Chức năng của nó là thêm *một giá trị code point* theo quy tắc UTF-16.

## 3. Ví dụ đầy đủ: thêm code point ngoài BMP

Lưu thành **`AppendCodePointDemo.java`**:

```java
public class AppendCodePointDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder();
        builder.append('A')
                .appendCodePoint(0x1F60A)
                .append('B');

        System.out.println("UTF-16 units: " + builder.length());
        System.out.println("Code points: "
                + builder.codePointCount(0, builder.length()));

        System.out.printf("charAt(1): U+%04X%n",
                (int) builder.charAt(1));
        System.out.printf("charAt(2): U+%04X%n",
                (int) builder.charAt(2));
        System.out.printf("codePointAt(1): U+%X%n",
                builder.codePointAt(1));

        System.out.println("valid surrogate pair: "
                + Character.isSurrogatePair(
                        builder.charAt(1), builder.charAt(2)));

        String expected = "A\uD83D\uDE0AB";
        System.out.println("content matches: "
                + builder.toString().equals(expected));
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac AppendCodePointDemo.java
java AppendCodePointDemo
```

**Stdout:**

```text
UTF-16 units: 4
Code points: 3
charAt(1): U+D83D
charAt(2): U+DE0A
codePointAt(1): U+1F60A
valid surrogate pair: true
content matches: true
```

Giải thích:

- `A` chiếm một code unit, emoji chiếm hai, `B` chiếm một: tổng `length() == 4`.
- `codePointCount(...)` nhận diện cặp surrogate hợp lệ và đếm emoji như **một code point**, nên tổng số code point là 3.
- `charAt(1)` và `charAt(2)` lần lượt cho hai nửa UTF-16 `D83D` và `DE0A`. Cả hai **không** phải hai emoji riêng.
- `codePointAt(1)` đọc code point bắt đầu ở offset UTF-16 `1`, trả `U+1F60A`.
- `toString()` tạo kết quả chuỗi chứa đúng các code unit đã thêm. So với literal được viết bằng cặp surrogate `"\uD83D\uDE0A"`, nội dung bằng nhau theo `String.equals()`.

**Đừng nhầm chỉ số:** tham số `index` của `codePointAt(index)` cũng là **offset code unit UTF-16**. Nó không phải “chỉ số code point thứ index”. Nếu cần dịch theo code point, xem `offsetByCodePoints(...)` ở phần sau.

## 4. Phân biệt `append(int)`, `append(char)` và `appendCodePoint(int)`

Ba phương thức có **ý nghĩa khác nhau**. Khi một biến `int` đang chứa code point, đây là lỗi rất thường gặp:

```java
int smile = 0x1F60A;

new StringBuilder().append(smile);          // thêm chữ số "128522"
new StringBuilder().append((char) smile);   // mất phần giá trị cao của int
new StringBuilder().appendCodePoint(smile); // thêm UTF-16 của emoji 😊
```

Đây là đoạn mã minh họa. `append(int)` chuyển số nguyên thành **văn bản thập phân**. `append((char) smile)` thực hiện ép kiểu thu hẹp, giữ lại 16 bit thấp và không thể biểu diễn trọn code point `U+1F60A`. `appendCodePoint(smile)` mới giữ đúng code point ngoài BMP.

Ví dụ chạy được **`AppendOverloadsDemo.java`**:

```java
public class AppendOverloadsDemo {
    public static void main(String[] args) {
        int smile = 0x1F60A;

        StringBuilder asNumber = new StringBuilder().append(smile);
        StringBuilder asChar = new StringBuilder().append((char) smile);
        StringBuilder asCodePoint = new StringBuilder()
                .appendCodePoint(smile);

        System.out.println("append(int): " + asNumber);
        System.out.println("append(char) units: " + asChar.length());
        System.out.printf("append(char) value: U+%04X%n",
                (int) asChar.charAt(0));
        System.out.println("appendCodePoint units: "
                + asCodePoint.length());
        System.out.printf("appendCodePoint value: U+%X%n",
                asCodePoint.codePointAt(0));
        System.out.println("correct smile: "
                + asCodePoint.toString().equals("\uD83D\uDE0A"));
    }
}
```

```bash
javac AppendOverloadsDemo.java
java AppendOverloadsDemo
```

**Stdout:**

```text
append(int): 128522
append(char) units: 1
append(char) value: U+F60A
appendCodePoint units: 2
appendCodePoint value: U+1F60A
correct smile: true
```

Sự sai khác là **mất dữ liệu**, không chỉ khác cách hiển thị. Sau khi ép `(char) smile`, giá trị `U+1F60A` đã trở thành `U+F60A` và không thể tự khôi phục bằng `append`.

Nếu đã có một **`String` hoàn chỉnh và hợp lệ** chứa emoji, `builder.append(string)` cũng giữ nguyên toàn bộ code unit của nó. `appendCodePoint` hữu ích nhất khi **đầu vào là một giá trị `int` biểu diễn code point**, chẳng hạn kết quả duyệt `codePoints()` hoặc dữ liệu mã Unicode.

## 5. Kiểm tra giá trị đầu vào và surrogate đơn lẻ

`Character.isValidCodePoint(int)` kiểm tra giá trị số có nằm trong dải `U+0000` đến `U+10FFFF` hay không. Tuy nhiên, **dải này chứa cả mã surrogate `U+D800`–`U+DFFF`**, nên kết quả `true` của `isValidCodePoint` **chưa đủ** để kết luận đầu vào là một *Unicode scalar value* có thể đứng độc lập trong văn bản hợp lệ.

Phân biệt:

- **Code point nằm trong dải hợp lệ của Java:** `0 <= cp <= 0x10FFFF`. `Character.isValidCodePoint(cp)` kiểm tra điều này.
- **Unicode scalar value:** code point hợp lệ **không thuộc vùng surrogate** `0xD800..0xDFFF`.
- **Code point được gán ký tự (*assigned*):** còn là một khái niệm khác; không phải mọi scalar value đều đã có ký tự được gán trong phiên bản Unicode của JDK.
- **Grapheme cluster hợp lệ cho UI:** phải xét quy tắc phân đoạn Unicode, có thể gồm nhiều scalar value.

`appendCodePoint` nhận cả giá trị surrogate nằm trong dải code point Java, và sẽ thêm một `char` surrogate đứng lẻ nếu bạn truyền `0xD800`. Về mặt cấu trúc `StringBuilder` có thể chứa code unit đó, nhưng đây **không phải** cách tạo văn bản Unicode scalar sequence hợp lệ. Khi dữ liệu đến từ hệ thống ngoài, hãy xác thực theo mục tiêu sử dụng.

Ví dụ **`SafeCodePointDemo.java`**:

```java
public class SafeCodePointDemo {
    private static boolean isScalarValue(int codePoint) {
        return Character.isValidCodePoint(codePoint)
                && !(codePoint >= 0xD800 && codePoint <= 0xDFFF);
    }

    private static void appendScalar(StringBuilder builder, int codePoint) {
        if (!isScalarValue(codePoint)) {
            throw new IllegalArgumentException(
                    "Not a Unicode scalar value");
        }
        builder.appendCodePoint(codePoint);
    }

    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder();

        appendScalar(builder, 0x41);
        appendScalar(builder, 0x1F60A);

        System.out.println("units: " + builder.length());
        System.out.println("points: "
                + builder.codePointCount(0, builder.length()));

        System.out.println("surrogate in numeric range: "
                + Character.isValidCodePoint(0xD800));
        System.out.println("surrogate accepted as scalar: "
                + isScalarValue(0xD800));

        try {
            appendScalar(builder, 0xD800);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected lone surrogate");
        }

        try {
            builder.appendCodePoint(0x110000);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected out-of-range value");
        }

        System.out.println("builder unchanged: "
                + builder.toString().equals("A\uD83D\uDE0A"));
    }
}
```

```bash
javac SafeCodePointDemo.java
java SafeCodePointDemo
```

**Stdout:**

```text
units: 3
points: 2
surrogate in numeric range: true
surrogate accepted as scalar: false
rejected lone surrogate
rejected out-of-range value
builder unchanged: true
```

`appendScalar` là **hàm bao ngoài tự định nghĩa** nhằm áp dụng hợp đồng đầu vào chặt hơn `appendCodePoint`. Java không tự áp dụng chính sách “không nhận surrogate code point” cho mọi trường hợp xây chuỗi. Nếu cần xử lý dữ liệu có surrogate lẻ, phải quyết định riêng: từ chối, thay bằng ký tự thay thế `U+FFFD`, hay giữ nguyên code unit để phục vụ một mục đích kỹ thuật cụ thể.

**Lưu ý:** `Character.isValidCodePoint` cũng không kiểm tra điều kiện “ký tự đã được gán”, không xác nhận tính hợp lệ của một grapheme cluster hay nội dung văn bản theo ngôn ngữ cụ thể.

## 6. Tạo chuỗi từ mảng code point hoặc luồng `codePoints()`

Một trường hợp sử dụng thường gặp là nhận dữ liệu dưới dạng các số nguyên Unicode rồi dựng văn bản. Khi danh sách đầu vào là các *scalar values* đã được kiểm tra, có thể append từng giá trị:

```java
int[] codePoints = {0x41, 0x1F60A, 0x42};
StringBuilder builder = new StringBuilder();
for (int cp : codePoints) {
    builder.appendCodePoint(cp);
}
String text = builder.toString();
```

Đây là đoạn mã minh họa; kết quả `text` là `"A😊B"` và có `length() == 4`. Nếu cần constructor thay vì builder, `new String(int[] codePoints, int offset, int count)` cũng nhận dữ liệu code point và mã hóa sang UTF-16 theo API. Builder có lợi khi dữ liệu đến từng phần hoặc cần phối hợp nhiều loại phần tử.

Với `String.codePoints()`, mỗi giá trị luồng là một `int` đại diện code point theo quy tắc Java. Có thể dựng lại chuỗi bằng `appendCodePoint`. Nhưng lưu ý: khi nguồn chứa **surrogate đứng lẻ**, `codePoints()` vẫn có thể trả giá trị code unit lẻ đó như một phần tử. Tái dựng giữ lại dữ liệu nguồn không đồng nghĩa nguồn là chuỗi Unicode scalar sequence hoàn chỉnh.

**Ví dụ chạy được `CodePointRoundTripDemo.java`:**

```java
public class CodePointRoundTripDemo {
    public static void main(String[] args) {
        String original = "A\uD83D\uDE0AB";

        StringBuilder rebuilt = new StringBuilder();
        original.codePoints().forEach(rebuilt::appendCodePoint);

        System.out.println("same content: "
                + original.contentEquals(rebuilt));
        System.out.println("UTF-16 units: " + rebuilt.length());
        System.out.println("code points: "
                + rebuilt.codePointCount(0, rebuilt.length()));

        int index = rebuilt.offsetByCodePoints(1, 1);
        System.out.println("after emoji offset: " + index);
        System.out.printf("code point at 1: U+%X%n",
                rebuilt.codePointAt(1));
    }
}
```

```bash
javac CodePointRoundTripDemo.java
java CodePointRoundTripDemo
```

**Stdout:**

```text
same content: true
UTF-16 units: 4
code points: 3
after emoji offset: 3
code point at 1: U+1F60A
```

Trong ví dụ, `offsetByCodePoints(1, 1)` bắt đầu tại offset UTF-16 `1` (ngay trước emoji), đi qua một code point và trả offset `3` (ngay sau cặp surrogate). Nếu viết `substring(1, 2)` sẽ cắt đôi emoji, trong khi `substring(1, 3)` lấy trọn.

Cảnh báo về reference trong Java: việc method reference `rebuilt::appendCodePoint` dùng với `IntConsumer` là hợp lệ; mặc dù phương thức trả về `StringBuilder`, kết quả trả về bị bỏ qua bởi chức năng consumer.

## 7. Xây nhiều code point vẫn có thể chỉ tạo một grapheme cluster

`appendCodePoint` xử lý **một code point tại một thời điểm**, không tạo hoặc phân đoạn “một ký tự hiển thị” theo ý nghĩa UI. Một số tổ hợp quan trọng:

- Chữ `e` (`U+0065`) và dấu sắc kết hợp (`U+0301`) là **hai code point**, nhưng thường được nhóm thành **một extended grapheme cluster**.
- Cờ 🇻🇳 gồm hai **regional indicator** `U+1F1FB` và `U+1F1F3`, tổng cộng hai code point, bốn code unit UTF-16, nhưng **một cluster** theo quy tắc phân đoạn.
- Emoji gia đình 👨‍👩‍👧‍👦 gồm bốn emoji người và ba ký tự nối `U+200D` (*Zero Width Joiner*), tổng cộng bảy code point, 11 code unit UTF-16, thường là một grapheme cluster.

Có thể tạo các tổ hợp này bằng nhiều lời gọi `appendCodePoint(...)` liên tiếp. Phương thức không tự ghép bảy code point thành một code point; nó chỉ mã hóa từng giá trị và nối các code unit.

Ví dụ **`GraphemeBuilderDemo.java`**:

```java
import java.util.regex.Pattern;

public class GraphemeBuilderDemo {
    private static final Pattern GRAPHEME = Pattern.compile("\\X");

    private static void show(String name, StringBuilder builder) {
        long clusters = GRAPHEME.matcher(builder).results().count();
        System.out.println(name
                + ": units=" + builder.length()
                + ", points=" + builder.codePointCount(0, builder.length())
                + ", clusters=" + clusters);
    }

    public static void main(String[] args) {
        StringBuilder accented = new StringBuilder();
        accented.appendCodePoint(0x65).appendCodePoint(0x301);

        StringBuilder flag = new StringBuilder();
        flag.appendCodePoint(0x1F1FB).appendCodePoint(0x1F1F3);

        StringBuilder family = new StringBuilder();
        int[] codePoints = {
                0x1F468, 0x200D, 0x1F469, 0x200D,
                0x1F467, 0x200D, 0x1F466
        };
        for (int cp : codePoints) {
            family.appendCodePoint(cp);
        }

        show("accented", accented);
        show("flag", flag);
        show("family", family);
    }
}
```

```bash
javac GraphemeBuilderDemo.java
java GraphemeBuilderDemo
```

**Stdout (Java 17+):**

```text
accented: units=2, points=2, clusters=1
flag: units=4, points=2, clusters=1
family: units=11, points=7, clusters=1
```

Java regex `\X` hỗ trợ phân đoạn **Unicode extended grapheme cluster**. Trong Java string literal phải viết `"\\X"` để regex nhận được `\X`. Kết quả phân đoạn có thể chịu ảnh hưởng bởi phiên bản dữ liệu Unicode trong JDK, nhất là với emoji mới; còn số code unit và code point của các ví dụ trên không phụ thuộc font.

Ngay cả một cluster cũng không nhất thiết thành **một glyph duy nhất**, vì font và nền tảng hiển thị quyết định việc ghép hình. Khi thiết kế cắt chuỗi theo “ký tự người dùng nhìn thấy”, dùng ranh giới grapheme cluster của thư viện phù hợp, không dùng `appendCodePoint` hay `length()` làm phép đếm ký tự hiển thị.

## 8. Tránh phá surrogate pair khi sửa `StringBuilder`

`StringBuilder` là **mutable**: có thể thêm, xóa, thay thế hoặc đảo nội dung. Tuy nhiên, nhiều API chỉnh sửa của builder vẫn làm việc theo **chỉ số code unit UTF-16**, nên có thể tạo ra surrogate lẻ nếu thao tác giữa một cặp.

Xét builder chứa `"A😊B"` với code unit ở offset:

```text
Offset: 0      1        2       3
        A   high-D83D low-DE0A   B
Ranh giới UTF-16: 0 | 1 | 2 | 3 | 4
```

- `builder.delete(1, 3)` xóa đủ hai code unit emoji, giữ `"AB"`.
- `builder.delete(1, 2)` chỉ xóa high surrogate, để lại low surrogate đứng lẻ.
- `builder.setCharAt(1, 'X')` thay high surrogate bằng `X`, cũng để lại low surrogate đứng lẻ.
- `builder.insert(2, "...")` có thể chèn giữa high và low surrogate; hãy tránh đặt điểm chèn ở đó nếu dữ liệu cần hợp lệ.

**Ví dụ `BuilderBoundaryDemo.java`:**

```java
public class BuilderBoundaryDemo {
    public static void main(String[] args) {
        StringBuilder safe = new StringBuilder("A\uD83D\uDE0AB");
        safe.delete(1, 3);
        System.out.println("safe result: " + safe);

        StringBuilder broken = new StringBuilder("A\uD83D\uDE0AB");
        broken.delete(1, 2);

        System.out.println("broken units: " + broken.length());
        System.out.println("lone low surrogate: "
                + Character.isLowSurrogate(broken.charAt(1)));

        StringBuilder original = new StringBuilder("A\uD83D\uDE0AB");
        int end = original.offsetByCodePoints(1, 1);
        original.delete(1, end);
        System.out.println("code point deletion: " + original);
    }
}
```

```bash
javac BuilderBoundaryDemo.java
java BuilderBoundaryDemo
```

**Stdout:**

```text
safe result: AB
broken units: 3
lone low surrogate: true
code point deletion: AB
```

`offsetByCodePoints(1, 1)` đưa vị trí từ offset 1 qua trọn một code point, nên end = 3 trong ví dụ. Đây là lựa chọn tốt hơn cho các thao tác cắt **theo code point**, nhưng vẫn có thể cắt giữa chữ cơ sở và dấu kết hợp. Nếu cần giữ **grapheme cluster**, hãy xác định ranh giới grapheme trước khi thao tác.

**Về `reverse()`:** `StringBuilder.reverse()` có xử lý riêng để giữ thứ tự đúng bên trong các surrogate pair hợp lệ, nhưng nó không có nghĩa phép đảo luôn giữ nguyên các grapheme cluster có nhiều code point (như e + dấu, emoji kết hợp). Không dùng `reverse()` như một bộ đảo “ký tự người dùng nhìn thấy” cho mọi hệ chữ.

## 9. Giới hạn độ dài, capacity và xử lý đầu vào

Vì builder lưu dữ liệu theo UTF-16 ở mức API:

- `length()` và `capacity()` đo bằng **số code unit `char`**, không đo bằng số code point, grapheme cluster hay byte khi xuất UTF-8.
- `appendCodePoint(0x1F60A)` tăng `length()` thêm **2**, không phải 1.
- `ensureCapacity(n)` yêu cầu builder chuẩn bị capacity tối thiểu theo đơn vị **code unit UTF-16**; không làm tăng `length()` và không tự thêm nội dung.
- Nếu cần giới hạn “tối đa N code point”, không thể chỉ kiểm tra `builder.length() <= N`. Với văn bản ngoài BMP, `length` có thể lớn hơn số code point.
- Nếu giới hạn byte cho giao thức hoặc tệp, hãy mã hóa theo charset mục tiêu (ví dụ UTF-8) rồi đo số byte. Số byte khác cả code unit, code point và grapheme.

Đầu vào từ nguồn ngoài có thể là số âm, vượt `U+10FFFF`, surrogate đơn lẻ hoặc code point chưa được gán trong phiên bản Unicode đang dùng. Chính sách nhận dữ liệu phải do **hợp đồng của ứng dụng** xác định. Bài học này dùng `appendScalar` để loại surrogate đơn lẻ, nhưng một trình xử lý dữ liệu UTF-16 thô có thể cần chính sách khác nhằm bảo toàn thông tin.

### Lựa chọn API theo dạng dữ liệu

| Đầu vào hiện có | API phù hợp | Chú ý |
|---|---|---|
| Một code point dưới dạng `int` | `appendCodePoint(cp)` | Nên xác thực scalar value nếu xây Unicode text hợp lệ |
| Một code unit UTF-16 dưới dạng `char` | `append(ch)` | Có thể là một nửa cặp surrogate |
| Một chuỗi `String` đã hoàn chỉnh | `append(text)` | Giữ nguyên dãy code unit của chuỗi |
| Mảng `char[]` UTF-16 | `append(chars)` | Chịu trách nhiệm bảo vệ cặp surrogate nếu nguồn có thể không hợp lệ |
| Mảng code point `int[]` | Lặp `appendCodePoint(cp)`, hoặc constructor `String(int[],...)` | Đừng ép mảng `int[]` thẳng thành `char[]` |
| Luồng `String.codePoints()` | Lặp appendCodePoint hoặc `new String(codePoints, ...)` | Nguồn có thể có surrogate lẻ, cần chính sách hợp lệ hóa |
| Cần thao tác theo ký tự hiển thị | Phân đoạn grapheme trước | Một cluster có thể chứa nhiều code point |

Đối với builder được dùng trong nhiều luồng, cần chú ý thêm `StringBuilder` **không đồng bộ hóa**; đồng bộ truy cập hoặc chọn cấu trúc phù hợp nếu thực sự chia sẻ mutable builder. Điều này độc lập với đặc tính Unicode của `appendCodePoint`.

## 10. Lỗi thường gặp và cách tránh

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| `builder.append(0x1F60A)` để thêm emoji | Thêm chuỗi chữ số `"128522"` | `appendCodePoint(0x1F60A)` |
| `builder.append((char) 0x1F60A)` | Chỉ giữ 16 bit thấp, mất code point ngoài BMP | Giữ `int` và dùng `appendCodePoint` |
| Cho rằng `appendCodePoint` luôn tăng length 1 | Đếm sai độ dài khi có supplementary code points | Với ngoài BMP, tăng 2 code unit |
| Cho rằng `Character.isValidCodePoint` là kiểm tra scalar value | Surrogate `U+D800` vẫn được coi là giá trị nằm trong khoảng code point | Loại riêng `0xD800..0xDFFF` nếu dữ liệu cần scalar |
| Chỉ kiểm tra `cp >= 0` | Giá trị `cp > 0x10FFFF` gây `IllegalArgumentException` | Xác thực giới hạn trên và surrogate theo chính sách |
| Truy cập `charAt(i)` như một code point | Có thể chỉ lấy high hoặc low surrogate | Dùng `codePointAt(i)` và `offsetByCodePoints(...)` |
| Xóa `delete(i, i+1)` để xóa emoji | Có thể chỉ xóa một nửa surrogate | Tính ranh giới code point/grapheme phù hợp |
| Coi hai code point cờ là hai ký tự người dùng nhìn thấy | Flag có thể là một grapheme cluster | Phân đoạn grapheme bằng quy tắc Unicode |
| Nghĩ `appendCodePoint` tự chuẩn hóa NFC | Dãy code point vẫn được nối nguyên vẹn | Dùng `Normalizer` riêng khi yêu cầu |
| Giới hạn nội dung bằng `capacity` hoặc chỉ dựa `length` để đếm code point | Đếm sai đơn vị | Định nghĩa rõ UTF-16 units, code points, clusters hay bytes |
| Nghĩ builder chứa surrogate lẻ sẽ luôn ném lỗi ngay | `StringBuilder` cho phép dãy code unit không tạo Unicode scalar text hợp lệ | Kiểm tra/giữ nguyên/thay thế theo hợp đồng đầu vào |

## 11. Tự kiểm tra

Dự đoán kết quả của chương trình **`AppendCodePointSelfCheck.java`** trước khi chạy:

```java
public class AppendCodePointSelfCheck {
    public static void main(String[] args) {
        int cp = 0x1F60A;

        StringBuilder a = new StringBuilder();
        a.appendCodePoint(cp);
        a.appendCodePoint(0x41);

        System.out.println(a.length());
        System.out.println(a.codePointCount(0, a.length()));
        System.out.println(Character.isSupplementaryCodePoint(cp));
        System.out.println(a.codePointAt(0) == cp);

        StringBuilder b = new StringBuilder();
        b.append(cp);
        System.out.println(b.toString());

        StringBuilder c = new StringBuilder();
        c.append((char) cp);
        System.out.println(c.length());
        System.out.println(c.codePointAt(0) == cp);
    }
}
```

```bash
javac AppendCodePointSelfCheck.java
java AppendCodePointSelfCheck
```

**Stdout:**

```text
3
2
true
true
128522
1
false
```

Giải thích: `a` chứa emoji (hai code unit, một code point) và chữ `A` (một code unit, một code point). `b.append(cp)` chọn overload số nguyên và chuyển thành chữ số. `c.append((char) cp)` cắt mất phần cao của `int` nên giá trị đọc lại không thể bằng `U+1F60A`.

**Ba câu hỏi khi quyết định API:**

1. Giá trị đang cầm là **một `char` UTF-16**, **một `int` code point**, hay **một chuỗi hoàn chỉnh**?
2. Giá trị có nằm ngoài BMP hoặc là surrogate đơn lẻ không, và hợp đồng của ứng dụng có yêu cầu Unicode scalar sequence hợp lệ không?
3. Bài toán muốn đếm/giới hạn/xóa theo **code unit**, **code point**, **grapheme cluster**, hay số **byte mã hóa**?

Khi dữ liệu đầu vào là code point hợp lệ và mục tiêu là tạo chuỗi Unicode, `StringBuilder.appendCodePoint(int)` giúp mã hóa đúng các giá trị ngoài BMP thành surrogate pair. Phần còn lại của tính đúng đắn nằm ở việc kiểm tra đầu vào, chọn ranh giới thao tác và định nghĩa chính xác “ký tự” theo yêu cầu.
