# CharSequence.chars() với đơn vị UTF-16 trong Java

**Chủ đề cha:** Chuỗi và Base64. **Trọng tâm bài học:** Hiểu chính xác kết quả của `CharSequence.chars()`: một `IntStream` có thứ tự, mỗi phần tử là giá trị số nguyên **không dấu mở rộng từ một `char` UTF-16**, **không phải** một code point Unicode hoàn chỉnh, một byte UTF-8 hay một ký tự người dùng nhìn thấy. Từ đó chọn đúng `chars()`, `codePoints()`, `codePointAt()`, `offsetByCodePoints()`, xử lý surrogate pairs, cắt chuỗi an toàn và phân biệt số code unit, code point, byte và grapheme.

**Phiên bản:** `CharSequence.chars()` và `CharSequence.codePoints()` có từ **Java 8**, vẫn được hỗ trợ trong Java SE hiện hành. Những ví dụ hoàn chỉnh dưới đây dùng **Java 17+** và chỉ dựa vào standard library. Những tính năng mới hơn như `Stream.toList()` (Java 16+) được ghi rõ khi xuất hiện. Bài tránh API lỗi thời và tập trung vào hợp đồng Java vẫn áp dụng.

> **Điểm quan trọng nhất:** `"A😀ế".chars()` tạo **4 giá trị int**: `0x0041`, `0xD83D`, `0xDE00`, `0x1EBF`. `codePoints()` tạo **3 giá trị int**: `0x41`, `0x1F600`, `0x1EBF`. Cả hai đều không đếm chính xác "ký tự người dùng nhìn thấy" trong mọi ngôn ngữ/emoji. Khi chuẩn bị dữ liệu đưa vào Base64, phải mã hóa `String` thành **byte theo charset cụ thể**, thường là `UTF-8`, không lấy các phần tử `chars()` làm byte.

## 1. Phân biệt bốn lớp biểu diễn văn bản

Khi xử lý text, "độ dài chuỗi" có thể có **ít nhất bốn nghĩa**:

| Đơn vị | Mô tả | Java API thường dùng |
| --- | --- | --- |
| **UTF-16 code unit** | Một giá trị 16-bit tương ứng với một `char` | `CharSequence.length()`, `charAt(i)`, `chars()` |
| **Unicode code point** | Giá trị số thường biểu diễn một điểm mã Unicode; một supplementary code point dùng hai code units UTF-16 | `codePoints()`, `codePointCount(...)`, `codePointAt(...)` |
| **Byte theo charset** | Chuỗi byte sau khi **mã hóa**, ví dụ UTF-8 | `getBytes(StandardCharsets.UTF_8)`, `CharsetEncoder` |
| **Grapheme cluster** | Nhóm code point được người dùng thường cảm nhận như một ký tự, ví dụ ký tự có dấu kết hợp hoặc emoji ZWJ | Unicode text segmentation/`BreakIterator` với kiểm chứng theo Unicode/JDK, hoặc thư viện Unicode chuyên dụng |

**Không có phép đồng nhất phổ quát:** một code point có thể cần **hai** UTF-16 units; một ký tự nhìn thấy có thể gồm **nhiều** code points; mỗi code point có thể cần **một đến bốn byte UTF-8** khi dữ liệu hợp lệ.

Ví dụ:

- `"A"`: một UTF-16 unit, một code point, một byte UTF-8.
- `"ế"`: một UTF-16 unit, một code point và ba byte UTF-8 ở dạng Unicode đã tổ hợp này.
- `"😀"`: **hai** UTF-16 units, một Unicode code point và bốn byte UTF-8.
- `"e\u0301"` (ký tự e + dấu sắc kết hợp): **hai** UTF-16 units, **hai** code points và một cụm chữ nhìn thấy trong cách hiển thị thông thường; không giống `"é"` ở dạng dữ liệu thô.
- `"👩🏽‍💻"`: **bảy** UTF-16 units, **bốn** code points và thường **một** emoji sequence hiển thị, tùy font/rendering.

Bởi vậy, yêu cầu nghiệp vụ phải ghi rõ đang đếm **UTF-16 units**, **code points**, **bytes** hay **grapheme clusters**. Chỉ nói "đếm ký tự" rất dễ dẫn đến bug.

## 2. CharSequence là một chuỗi các `char` 16-bit

`java.lang.CharSequence` là interface biểu diễn một chuỗi các giá trị `char` có thể đọc. Các implementation quen thuộc gồm `String`, `StringBuilder`, `StringBuffer` và `CharBuffer`. Những phương thức cơ bản:

```java
int length();
char charAt(int index);
CharSequence subSequence(int start, int end);
String toString();
```

Đây là **chữ ký interface minh họa**, không phải một chương trình Java độc lập. Từ Java 8, interface có thêm hai phương thức mặc định quan trọng:

```java
IntStream chars();
IntStream codePoints();
```

`chars()` là stream các **`char` values được mở rộng thành `int`**; `codePoints()` là stream theo **code points** sau khi kết hợp các surrogate pairs hợp lệ.

### 2.1. Tại sao `char` của Java không tương đương một Unicode character?

`char` chứa đúng **16 bit**, trong khi Unicode hiện nay có các code points ngoài vùng Basic Multilingual Plane (BMP), tức lớn hơn `U+FFFF`. Để biểu diễn các code points từ `U+10000` đến `U+10FFFF` trong UTF-16, Java cần **hai `char`**, tạo thành một **surrogate pair**.

- **High surrogate:** `U+D800–U+DBFF`.
- **Low surrogate:** `U+DC00–U+DFFF`.
- Một cặp high ngay sau là low hợp lệ đại diện cho một supplementary code point.
- Một high hoặc low đứng lẻ là **unpaired surrogate**, tạo chuỗi UTF-16 không hợp lệ về mặt biểu diễn Unicode scalar values, nhưng các Java `String` vẫn có thể chứa các code unit như thế.

**Không phân loại mọi giá trị int từ `chars()` là Unicode scalar value.** Với emoji, stream phát hai code unit `D83D` và `DE00` riêng biệt — từng giá trị đó nằm trong vùng surrogate và không biểu diễn hai ký tự riêng.

### 2.2. `String.length()` tính gì?

`String.length()` trả **số UTF-16 code units**. Vì `String` triển khai `CharSequence`, điều này tương ứng số phần tử của `String.chars()`:

```java
String text = "A\uD83D\uDE00\u1EBF";

int units = text.length();            // 4
long unitsFromStream = text.chars().count(); // 4
```

Đây là **đoạn bên trong phương thức**. Trong chuỗi Java có `\uD83D\uDE00` (emoji 😀) và `\u1EBF` (chữ ế). Ký hiệu Java Unicode escape trong code nhằm làm ví dụ không phụ thuộc encoding của tệp nguồn hoặc terminal.

**Lưu ý:** `length()` là cách trực tiếp và rẻ hơn để lấy số code units của `String`. Không cần tạo stream chỉ để tính `chars().count()` khi chỉ cần `length()`.

## 3. Hợp đồng chính xác của `CharSequence.chars()`

Javadoc hiện hành mô tả `chars()` như sau:

- Trả một `IntStream` tuần tự, có thứ tự, theo các `char` trong sequence.
- Mỗi `char` được **zero-extend** thành `int`, nên giá trị nằm trong khoảng `0x0000–0xFFFF`.
- Mọi code unit trong vùng surrogate được đưa ra **nguyên vẹn**; phương thức **không ghép** high/low surrogate thành code point.
- Stream liên kết với sequence khi **terminal operation** bắt đầu (late-binding đối với mutable sequence).
- **Sửa sequence trong lúc terminal operation đang duyệt** sẽ dẫn đến kết quả **không được xác định** theo contract; phải tránh.

### 3.1. Zero-extension khác sign-extension thế nào?

`char` của Java là kiểu **16-bit không dấu**. Đưa `char` vào `int` sẽ tạo một giá trị không âm trong 0..65535; code unit `0xD83D` trở thành số nguyên `55357`, không bị âm như cách sign-extend từ `short` signed.

```java
char high = '\uD83D';

int fromChar = high;             // 55357, hay 0xD83D
int fromStream = "\uD83D".chars().findFirst().orElseThrow();
// fromStream == 55357
```

Đây là đoạn trong phương thức (sử dụng `OptionalInt.orElseThrow()` có trong Java 17+). Một giá trị `char` surrogate ở đây **không** phải emoji đầy đủ; chỉ là nửa đầu của một cặp.

### 3.2. Stream có thứ tự nhưng không phải kiểu `Stream<Character>`

`CharSequence.chars()` trả `IntStream`, tức **primitive stream of int**, giúp tránh boxing cho phần lớn thao tác.

```java
String ascii = "ABC";

int first = ascii.chars().findFirst().orElseThrow(); // 65
long count = ascii.chars().count();                 // 3
int sum = ascii.chars().sum();                      // 198
```

Đây là đoạn trong phương thức. Tổng 198 là 65+66+67, **không phải** tổng code points có giá trị nghiệp vụ đặc biệt.

Nếu cần tạo `List<Integer>`, có thể gọi `boxed()` rồi `toList()` (Java 16+):

```java
List<Integer> units = ascii.chars().boxed().toList();
```

Đây là đoạn trong phương thức, import `java.util.List`. Không box toàn bộ stream nếu chỉ cần `count`, `filter` hay `sum`; boxing gây overhead.

### 3.3. `chars()` và `charAt` tương ứng nhau theo chỉ số code unit

Với chuỗi ổn định:

```java
String input = "Hi";

int c0 = input.charAt(0);
int viaStream = input.chars().findFirst().orElseThrow();
// c0 == viaStream == 72
```

Đây là đoạn trong phương thức. Tương ứng này giữ với mỗi chỉ số UTF-16. Nhưng **một emoji ngoài BMP chiếm hai chỉ số**; `charAt(0)` của một emoji không phải code point Unicode đầy đủ.

## 4. Java 17+ runnable: `chars()` so với `codePoints()`

Tạo file **`Utf16CharStreamDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.util.stream.Collectors;

public class Utf16CharStreamDemo {
    public static void main(String[] args) {
        // A, emoji U+1F600, chữ ế U+1EBF.
        String text = "A\uD83D\uDE00\u1EBF";

        System.out.println("UTF-16 units: " + text.length());
        System.out.println("chars count: " + text.chars().count());
        System.out.println("codePoints count: "
                + text.codePoints().count());
        System.out.println("UTF-8 bytes: "
                + text.getBytes(StandardCharsets.UTF_8).length);

        String units = text.chars()
                .mapToObj(unit ->
                        String.format("%04X", unit))
                .collect(Collectors.joining(" "));

        String points = text.codePoints()
                .mapToObj(point ->
                        String.format("%X", point))
                .collect(Collectors.joining(" "));

        System.out.println("chars hex: " + units);
        System.out.println("codePoints hex: " + points);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 Utf16CharStreamDemo.java
java Utf16CharStreamDemo
```

**Stdout xác định:**

```text
UTF-16 units: 4
chars count: 4
codePoints count: 3
UTF-8 bytes: 8
chars hex: 0041 D83D DE00 1EBF
codePoints hex: 41 1F600 1EBF
```

**Giải thích theo từng giá trị:**

1. `0x0041` là code unit của chữ Latin `A`.
2. `0xD83D` và `0xDE00` là high/low surrogate của `U+1F600`, được `chars()` phát **tách rời**.
3. `0x1EBF` là chữ `ế` đã tổ hợp, thuộc BMP nên cần một code unit.
4. `codePoints()` ghép `D83D DE00` thành `1F600`, do đó chỉ có ba phần tử.
5. Dữ liệu UTF-8 tương ứng có 1+4+3 = 8 bytes.
6. `String.format("%X",...)` in chữ số hex; giá trị nằm trong int nên không có vấn đề sign.
7. Output in mã hex thay vì hiển thị emoji trực tiếp, giúp kết quả nhất quán giữa các terminal/font.

**Không dùng `chars().count()` để xác định có bao nhiêu emoji hay user-perceived characters trong input.** Nó chỉ biết số code units.

## 5. `codePoints()` làm gì khác?

`CharSequence.codePoints()` cũng trả `IntStream` có thứ tự, nhưng xử lý UTF-16 như sau:

- Hai code units **high surrogate + low surrogate liên tiếp** được ghép thành **một** supplementary code point bằng quy tắc tương đương `Character.toCodePoint(high, low)`.
- Code units BMP bình thường được zero-extend thành int.
- **Unpaired surrogates** được phát thành **một giá trị int nằm trong vùng surrogate**. Phương thức **không tự từ chối** hoặc thay thế dữ liệu không hợp lệ.
- Như `chars()`, stream có late binding đối với mutable sequence và không được sửa sequence trong khi terminal operation chạy.

### 5.1. Không được hiểu codePoints là "luôn hợp lệ Unicode"

Đoạn dữ liệu:

```java
String invalid = "X\uD83DY\uDE00Z";
```

có một high surrogate đứng trước `Y` và một low surrogate đứng trước `Z`, **không ghép thành pair**. `invalid.codePoints()` vẫn sẽ trả cả `0xD83D` và `0xDE00` như hai giá trị int riêng.

Vì vậy:

- `codePoints()` hợp với logic cần **đi từng code point** của một sequence.
- Nhưng nếu ứng dụng cần **chuỗi Unicode well-formed**, phải **kiểm tra surrogate lẻ**.
- `Character.isValidCodePoint(int)` chỉ kiểm tra trong phạm vi giá trị code point từ 0 đến `U+10FFFF`; **không tự loại mọi giá trị vùng surrogate**. Đây là bẫy dễ bỏ sót khi xác thực dữ liệu.
- Unicode **scalar value** không bao gồm surrogate range `U+D800..U+DFFF`.

### 5.2. Khi nào dùng `chars()`?

`chars()` là lựa chọn đúng khi bài toán thực sự nói về **UTF-16 units**:

- Đếm đơn vị mà `String.length()` biểu thị.
- Kiểm tra từng `char` theo hợp đồng của parser/định dạng Java dùng code unit.
- Tìm/số hóa các code unit, bao gồm phát hiện surrogate high/low.
- Tính kích thước theo giới hạn **UTF-16 code units** của một ô, buffer hoặc giao thức đã quy định rõ.
- Phân tích chính xác cấu trúc UTF-16 để nhận diện surrogate pairs và lỗi surrogate lẻ.

Ngược lại, nếu cần xét **chữ cái Unicode ngoài BMP**, phân loại qua `Character.isLetter(int)` hoặc xử lý một mã điểm hoàn chỉnh, `codePoints()` thường phù hợp hơn.

### 5.3. Khi nào không nên chọn cả hai?

Nếu yêu cầu là **đếm, cắt hoặc đảo ký tự mà người dùng nhìn thấy**, `chars()` và `codePoints()` đều có thể không đủ do combining marks, emoji ZWJ, modifiers, regional indicators và những quy tắc grapheme phức tạp. Dùng Unicode grapheme segmentation phù hợp với ứng dụng và kiểm chứng với phiên bản Unicode/locale cần hỗ trợ.

Nếu yêu cầu là **giới hạn byte UTF-8**, sử dụng charset encoding và đếm byte thật; cả hai primitive streams không trực tiếp đo byte.

## 6. Surrogate pair và các API Character liên quan

Một supplementary code point `cp >= 0x10000` (và `cp <= 0x10FFFF`) cần hai UTF-16 units.

Các API có thể dùng:

| Phương thức | Mục đích |
| --- | --- |
| `Character.isHighSurrogate(char)` | Kiểm tra code unit ở vùng high surrogate |
| `Character.isLowSurrogate(char)` | Kiểm tra code unit ở vùng low surrogate |
| `Character.isSurrogate(char)` | Có thuộc cả hai vùng surrogate không |
| `Character.isSurrogatePair(high, low)` | Hai units có ghép thành pair hợp lệ không |
| `Character.toCodePoint(high, low)` | Ghép pair thành code point; **không tự validate pair** |
| `Character.toChars(int)` | Chuyển code point hợp lệ sang một hoặc hai `char` |
| `Character.charCount(int)` | Trả số units cần cho code point (thường 1/2); **không tự validate input** |
| `Character.isSupplementaryCodePoint(int)` | Kiểm tra vùng supplementary |
| `Character.codePointAt(CharSequence,index)` | Lấy code point bắt đầu ở **UTF-16 index** |
| `Character.codePointBefore(CharSequence,index)` | Lấy code point trước **UTF-16 index** |

### 6.1. Code point là int, code unit là char

`int` đủ chứa `U+1F600` (số `128512`), `char` chỉ có 16 bit và **không** chứa nguyên giá trị 128512. Đừng viết:

```java
char emoji = (char) 0x1F600; // Sai về ý nghĩa: mất bit cao.
```

Đây là **phản ví dụ**, không dùng để lưu emoji. Dùng:

```java
int emoji = 0x1F600;
String text = new String(Character.toChars(emoji));
```

Hai dòng trên là đoạn trong phương thức; `text` là chuỗi hai UTF-16 code units nhưng một Unicode code point.

### 6.2. Không gọi `Character.toCodePoint` khi chưa kiểm tra

Nếu input không phải một cặp high/low đúng thứ tự, `Character.toCodePoint(high, low)` không bảo đảm kết quả có ý nghĩa; dùng `Character.isSurrogatePair` hoặc các hàm `codePointAt` vốn đã triển khai logic kết hợp.

### 6.3. Các API theo code point vẫn sử dụng UTF-16 index

`String.codePointAt(index)` nhận **index tính theo UTF-16 code units**, không phải vị trí code point. Với `"A😀B"`:

- `charAt(0)`: `A`.
- `charAt(1)`: high surrogate của emoji.
- `charAt(2)`: low surrogate.
- `charAt(3)`: `B`.
- `codePointAt(1)`: `U+1F600`.
- `codePointAt(2)`: low surrogate `0xDE00` đứng lẻ từ điểm nhìn của vị trí bắt đầu 2; vì không có high surrogate ngay tại 2 nên **không** cho ra lại U+1F600.
- `offsetByCodePoints(0,2)`: trả **3**, tức vị trí UTF-16 ngay sau hai code points đầu là A và emoji.

**Quy tắc:** Nếu code đang đếm theo code points nhưng truy cập substring/charAt theo index, phải chuyển vị trí bằng `offsetByCodePoints`.

## 7. Java 17+: Đếm code points và tránh cắt đôi surrogate

Tạo file **`CodePointIndexDemo.java`**:

```java
import java.util.stream.Collectors;

public class CodePointIndexDemo {
    public static void main(String[] args) {
        String s = "A\uD83D\uDE00B";

        System.out.println("Length: " + s.length());
        System.out.println("PointCount: "
                + s.codePointCount(0, s.length()));
        System.out.println("CharAt1 high: "
                + Character.isHighSurrogate(s.charAt(1)));
        System.out.println("CharAt2 low: "
                + Character.isLowSurrogate(s.charAt(2)));
        System.out.println("Pair: "
                + Character.isSurrogatePair(
                        s.charAt(1), s.charAt(2)));
        System.out.println("At1: "
                + String.format("%X", s.codePointAt(1)));

        int end = s.offsetByCodePoints(0, 2);
        System.out.println("Offset +2: " + end);

        String safe = s.substring(0, end);
        System.out.println("Substring by points: "
                + safe.codePoints()
                        .mapToObj(cp -> String.format("%X", cp))
                        .collect(Collectors.joining(" ")));

        String broken = s.substring(0, 2);
        System.out.println("Index 2 half-pair: "
                + Character.isSurrogate(
                        broken.charAt(broken.length() - 1)));
    }
}
```

Chạy:

```bash
javac --release 17 CodePointIndexDemo.java
java CodePointIndexDemo
```

**Stdout:**

```text
Length: 4
PointCount: 3
CharAt1 high: true
CharAt2 low: true
Pair: true
At1: 1F600
Offset +2: 3
Substring by points: 41 1F600
Index 2 half-pair: true
```

Phân tích:

1. `String.substring(0,2)` **không** có nghĩa lấy hai code points; nó lấy **hai UTF-16 units**. Với chuỗi này, kết quả gồm `A` và **một high surrogate lẻ**.
2. `offsetByCodePoints(0,2)` trả 3, đủ để `substring(0,3)` chứa A và emoji **nguyên vẹn**.
3. `codePointCount(0,length)` với dữ liệu well-formed đếm ba code points; không cần tạo stream khi chỉ muốn count trên `String`.
4. Trong ứng dụng thực, vị trí index có thể đến từ cursor, API editor hoặc column trong protocol: phải biết index đó đo **code units** hay **grapheme clusters**. Không tự cộng 1 để đi qua supplementary code point.

## 8. Unpaired surrogate: `codePoints()` không tự chữa dữ liệu hỏng

Một Java `String` có thể chứa UTF-16 không well-formed, ví dụ khi data nhập qua một bước cắt/truncate sai hoặc API trả một high surrogate đứng lẻ. `chars()` và `codePoints()` chỉ báo lại nội dung theo contract, không tự sửa nó.

### 8.1. Java 17+ runnable: Phát hiện surrogate lẻ

Tạo file **`UnpairedSurrogateDemo.java`**:

```java
import java.util.stream.Collectors;

public class UnpairedSurrogateDemo {
    static boolean hasUnpairedSurrogate(String value) {
        return value.codePoints()
                .anyMatch(cp -> cp >= 0xD800 && cp <= 0xDFFF);
    }

    public static void main(String[] args) {
        // X + high surrogate + Y + low surrogate + Z.
        String malformed = "X\uD83DY\uDE00Z";

        System.out.println("Malformed units: "
                + malformed.length());
        System.out.println("Malformed points: "
                + malformed.codePoints().count());
        System.out.println("Malformed char hex: "
                + malformed.chars()
                        .mapToObj(unit -> String.format(
                                "%04X", unit))
                        .collect(Collectors.joining(" ")));
        System.out.println("Malformed point hex: "
                + malformed.codePoints()
                        .mapToObj(point -> String.format(
                                "%X", point))
                        .collect(Collectors.joining(" ")));
        System.out.println("Has unpaired: "
                + hasUnpairedSurrogate(malformed));

        String deseret = "\uD801\uDC00"; // U+10400.
        System.out.println("Deseret code point letter: "
                + Character.isLetter(deseret.codePointAt(0)));
        System.out.println("Deseret char letter: "
                + Character.isLetter(deseret.charAt(0)));
    }
}
```

Chạy:

```bash
javac --release 17 UnpairedSurrogateDemo.java
java UnpairedSurrogateDemo
```

**Stdout:**

```text
Malformed units: 5
Malformed points: 5
Malformed char hex: 0058 D83D 0059 DE00 005A
Malformed point hex: 58 D83D 59 DE00 5A
Has unpaired: true
Deseret code point letter: true
Deseret char letter: false
```

**Tại sao code này quan trọng:**

- `malformed` có **hai surrogate lẻ**, không có cặp high-low liên tiếp. Vì vậy `codePoints()` vẫn trả năm giá trị, không nhất thiết giảm số phần tử so với `chars()`.
- Bộ kiểm tra nhận diện **những code point values trong vùng surrogate** sau khi đã kết hợp tất cả pairs hợp lệ, nên chúng là các surrogate lẻ.
- Ký tự U+10400 thuộc **Deseret alphabet** và được `Character.isLetter(int)` nhận diện là chữ cái. `charAt(0)` chỉ là high surrogate, nên `Character.isLetter(char)` trả false. Điều này chứng minh việc phân loại Unicode bằng từng code unit có thể sai.
- Không kết luận “mọi code point đều sẽ biến thành một chữ cái hay emoji”. Code point có thể là dấu kết hợp, control, space, ZWJ và nhiều loại khác.

### 8.2. `Character.isValidCodePoint` không đủ để validate scalar value

`Character.isValidCodePoint` kiểm tra liệu số nằm trong khoảng Unicode code point, nhưng vùng surrogate vẫn nằm trong khoảng này. Do đó nên kiểm tra thêm:

```java
static boolean isUnicodeScalarValue(int cp) {
    return Character.isValidCodePoint(cp)
            && !(cp >= 0xD800 && cp <= 0xDFFF);
}
```

Đây là **method bên trong class**. Nếu dùng trên một stream codePoints từ String, các surrogate lẻ sẽ bị phát hiện. Đừng loại bỏ chúng âm thầm trong một giao thức cần roundtrip nguyên vẹn; hãy đưa ra chính sách rõ: từ chối input, thay `U+FFFD` hoặc báo lỗi có vị trí.

## 9. Cắt chuỗi theo code point không giống cắt theo code unit

Với API `substring(start,end)`:

- `start`/`end` là **UTF-16 indices**.
- Nếu đặt ranh giới ở giữa high/low surrogate, phần bên trái/phải có thể chứa unpaired surrogate.
- `String.offsetByCodePoints(index, n)` hỗ trợ chuyển n code points thành số units cần tiến.
- `String.codePointCount(start,end)` đếm code points trong một **vùng code units**; unpaired surrogates được tính riêng.
- `Character.charCount(cp)` cho biết một point cần bao nhiêu units, nhưng **không phân nhóm grapheme**.

### 9.1. Ví dụ cắt hai code points

```java
String s = "A\uD83D\uDE00B";

int end = s.offsetByCodePoints(0, 2);
String twoPoints = s.substring(0, end);
// twoPoints chứa A và emoji, end = 3.
```

Đây là đoạn trong phương thức.

**Cảnh báo:** `twoPoints` có hai code points nhưng có thể vẫn không bằng hai ký tự người dùng thấy nếu có combining marks/emoji ZWJ. `offsetByCodePoints` giải quyết vấn đề **cắt đôi surrogate**, không tự giải quyết **grapheme clusters**.

### 9.2. Cắt theo giới hạn UTF-16 units

Một số hệ thống chỉ định giới hạn lưu trữ theo số UTF-16 units. Khi phải chia thành các phần không quá `maxUnits` nhưng vẫn bảo toàn surrogate pair, có thể điều chỉnh ranh giới **nếu nó nằm giữa high và low**.

Ví dụ:

```java
int end = Math.min(start + maxUnits, text.length());

if (end < text.length()
        && Character.isHighSurrogate(text.charAt(end - 1))
        && Character.isLowSurrogate(text.charAt(end))) {
    end--; // Lùi một unit để không cắt giữa pair.
}
```

Đây là **đoạn trong một phương thức**, có biến `start`/`maxUnits` hợp lệ và bảo đảm `end > start`. Nếu `maxUnits == 1` mà vị trí hiện tại là high surrogate, không thể chứa nguyên pair trong một part có capacity một unit; phải báo không thể phân chia theo ràng buộc đó hoặc thay đổi thiết kế. Với cap từ 2 trở lên, có thể phân mảnh chính xác mà không cắt pair.

### 9.3. Không chuẩn hóa đầu vào khi mục tiêu là roundtrip byte-for-byte

Nếu yêu cầu lưu/ghép lại đúng chuỗi UTF-16 gốc, **không** tự gọi `Normalizer.normalize`, `trim`, `strip` hoặc thay unsupported char. Những phép đó có thể thay nội dung/dài ngắn và vi phạm đối chiếu nguyên văn. Khi cần normalize cho so sánh hoặc tìm kiếm, dùng một **giá trị dẫn xuất riêng**, giữ bản gốc nếu yêu cầu lưu trữ chính xác.

## 10. Java 17+ runnable: Chia đoạn UTF-16 mà không xé surrogate pair

Tạo file **`Utf16SafeChunksDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

public class Utf16SafeChunksDemo {
    static List<String> splitWithoutBreakingPairs(
            String value, int maxUnits) {
        if (maxUnits < 2) {
            throw new IllegalArgumentException(
                    "maxUnits must be at least 2");
        }

        List<String> parts = new ArrayList<>();

        for (int start = 0; start < value.length();) {
            int end = Math.min(start + maxUnits, value.length());

            if (end < value.length()
                    && Character.isHighSurrogate(
                            value.charAt(end - 1))
                    && Character.isLowSurrogate(
                            value.charAt(end))) {
                end--;
            }

            if (end <= start) {
                throw new IllegalStateException(
                        "cannot make progress");
            }

            parts.add(value.substring(start, end));
            start = end;
        }
        return parts;
    }

    static String hexPoints(String value) {
        return value.codePoints()
                .mapToObj(cp -> String.format("%X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String original = "A\uD83D\uDE00B";
        List<String> parts =
                splitWithoutBreakingPairs(original, 2);

        System.out.println("Part count: " + parts.size());

        for (int i = 0; i < parts.size(); i++) {
            System.out.println("Part " + i + ": "
                    + hexPoints(parts.get(i)));
        }

        String restored = String.join("", parts);
        System.out.println("Exact roundtrip: "
                + original.equals(restored));
        System.out.println("Sizes fit: "
                + parts.stream().allMatch(
                        p -> p.length() <= 2));
    }
}
```

Chạy:

```bash
javac --release 17 Utf16SafeChunksDemo.java
java Utf16SafeChunksDemo
```

**Stdout:**

```text
Part count: 3
Part 0: 41
Part 1: 1F600
Part 2: 42
Exact roundtrip: true
Sizes fit: true
```

Giải thích:

1. Chuỗi gốc có bốn units: A, high, low, B.
2. Nếu cắt mỗi hai units một cách máy móc, phần đầu kết thúc ở **high surrogate**. Hàm nhận diện ranh giới này và **lùi về một unit**.
3. Ba đoạn chứa A, emoji, B; emoji có hai units nên vừa maxUnits=2.
4. Ghép bằng `String.join("", parts)` tái tạo nguyên văn chuỗi gốc, không thêm separator.
5. Code này **không bảo vệ grapheme clusters** như dấu kết hợp hoặc emoji ZWJ; chỉ bảo vệ cặp surrogate.
6. Nếu chuỗi gốc đã có surrogate lẻ, hàm không tự sửa nó. Muốn yêu cầu **UTF-16 well-formed** thì validate trước.
7. Nếu input rỗng, trả list rỗng và ghép lại vẫn đúng. Nếu đầu vào null, phương thức sẽ ném NullPointerException; ứng dụng có thể xác thực rõ trước khi gọi.

## 11. UTF-16 vs UTF-8: Tại sao Base64 không bắt đầu bằng `chars()`?

Trong nhóm học *Chuỗi và Base64*, phải phân biệt hai tầng:

1. **Text / String:** Dữ liệu ký tự bên trong Java biểu diễn qua UTF-16 code units.
2. **Bytes:** Dữ liệu xuất ra file, HTTP, network và đầu vào cho Base64 phải được **encode theo charset cụ thể**, ví dụ UTF-8.

**Base64 là mã hóa byte thành ký tự ASCII**, không phải phép biến mỗi Unicode character thành một Base64 character. Vì vậy quy trình chuẩn:

```text
String (UTF-16 model in Java)
    |
    | getBytes(StandardCharsets.UTF_8)
    v
byte[] UTF-8
    |
    | Base64.getEncoder().encodeToString(bytes)
    v
ASCII Base64 text
```

Giải mã làm theo chiều ngược:

```text
Base64 text
    |
    | Base64.getDecoder().decode(base64)
    v
UTF-8 bytes
    |
    | new String(bytes, StandardCharsets.UTF_8)
    v
String
```

**Không** viết:

```java
byte[] wrong = text.chars()
        .mapToObj(v -> (byte) v)
        .collect(...);
```

Đây là **phản ví dụ dạng pseudocode**, chưa có collector có kiểu phù hợp, và logic cắt bỏ bits cao là sai. Ép từng UTF-16 unit sang byte không tạo UTF-8. Với emoji `D83D DE00`, nếu cast thành byte, bạn sẽ mất thông tin và không thể roundtrip.

### 11.1. Byte count khác code unit count

`"A😀ế"` ở dạng code points đã tổ hợp có:

- UTF-16 units: **4**.
- Unicode code points: **3**.
- UTF-8 bytes: **8**.
- Base64 output length: **12 ASCII characters** (8 bytes được Base64 encode với padding).

Không suy luận giới hạn byte database hoặc HTTP payload từ `String.length()` nếu protocol ghi rõ **UTF-8 bytes**.

### 11.2. Unpaired surrogate khi encode

Java `String` có thể chứa surrogate lẻ, nhưng UTF-8 chuẩn không thể biểu diễn surrogate code point như một Unicode scalar value hợp lệ. Các encoder thường có **replacement policy** cho input malformed; chúng có thể thay dữ liệu hỏng thay vì roundtrip chính xác.

Nếu ứng dụng yêu cầu an toàn dữ liệu, dùng `CharsetEncoder` với `CodingErrorAction.REPORT` để **phát hiện malformed/unmappable input** và xử lý theo policy, hoặc kiểm tra surrogate lẻ trước khi encode. Không tin rằng `String.getBytes(UTF_8)` luôn bảo toàn code units malformed.

## 12. Java 17+ runnable: UTF-8 và Base64 với emoji

Tạo file **`Utf8Base64RoundTripDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class Utf8Base64RoundTripDemo {
    public static void main(String[] args) {
        String text = "A\uD83D\uDE00\u1EBF";
        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);

        String hex = IntStream.range(0, utf8.length)
                .mapToObj(i -> String.format(
                        "%02X", utf8[i] & 0xFF))
                .collect(Collectors.joining(" "));

        String base64 =
                Base64.getEncoder().encodeToString(utf8);
        byte[] decoded =
                Base64.getDecoder().decode(base64);
        String restored =
                new String(decoded, StandardCharsets.UTF_8);

        System.out.println("UTF-8 hex: " + hex);
        System.out.println("Base64: " + base64);
        System.out.println("Round trip: "
                + text.equals(restored));
        System.out.println("UTF-16 units: " + text.length());
        System.out.println("UTF-8 byte count: " + utf8.length);
    }
}
```

Chạy:

```bash
javac --release 17 Utf8Base64RoundTripDemo.java
java Utf8Base64RoundTripDemo
```

**Stdout:**

```text
UTF-8 hex: 41 F0 9F 98 80 E1 BA BF
Base64: QfCfmIDhur8=
Round trip: true
UTF-16 units: 4
UTF-8 byte count: 8
```

**Điểm cần hiểu:**

- Byte `0x41` là A.
- Dãy `F0 9F 98 80` mã hóa emoji `U+1F600` theo UTF-8.
- Dãy `E1 BA BF` mã hóa chữ `ế` đã tổ hợp `U+1EBF`.
- Base64 của **tám byte thực** được kiểm tra bằng roundtrip.
- Toán tử `& 0xFF` dùng khi chuyển Java `byte` signed thành số 0..255 để in hex, khác với `char` vốn không dấu 16-bit.
- Chuỗi Base64 có thể được chứa trong Java `String`, nhưng nó là **representation ASCII của bytes**, không phải representation gốc của văn bản Unicode.
- Nếu charset encode/decode không khớp, các ký tự ngoài ASCII có thể bị lỗi dù Base64 encoder/decoder tự hoạt động chính xác.

## 13. Combining marks: Code point chưa chắc là một chữ người dùng thấy

Unicode cho phép cùng một nội dung nhìn giống nhau được biểu diễn bằng nhiều sequence khác nhau.

Ví dụ:

```java
String composed = "\u00E9";   // é đã tổ hợp, 1 code point.
String decomposed = "e\u0301"; // e + combining acute, 2 code points.
```

Hai chuỗi thường hiển thị gần như giống nhau, nhưng:

- `composed.equals(decomposed)` là **false**, vì các UTF-16 units khác nhau.
- `composed.length() == 1`, `decomposed.length() == 2`.
- `composed.codePoints().count() == 1`, `decomposed.codePoints().count() == 2`.
- `Normalizer.normalize(..., Normalizer.Form.NFC)` có thể chuyển chúng về dạng chuẩn để so sánh theo một chính sách Unicode normalization.
- Việc normalize thay đổi dữ liệu nên không dùng khi yêu cầu lưu/khôi phục nguyên văn.

### 13.1. Grapheme cluster còn phức tạp hơn dấu kết hợp

Emoji `👩🏽‍💻` gồm:

- `U+1F469` — woman.
- `U+1F3FD` — skin tone modifier.
- `U+200D` — zero-width joiner.
- `U+1F4BB` — laptop.

Có bốn code points và bảy UTF-16 units, nhưng thường render như một **emoji sequence duy nhất**. Tách sau bất kỳ code point nào cũng có thể làm ý nghĩa hiển thị thay đổi.

Nếu ứng dụng có cursor, backspace, cắt tên hiển thị theo "ký tự", input method hoặc text editor, hãy nghiên cứu **extended grapheme clusters** theo Unicode UAX #29. Trong Java, `java.text.BreakIterator` hỗ trợ phân đoạn text, nhưng mức hỗ trợ các emoji ZWJ sequences cụ thể có thể phụ thuộc JDK/Unicode version; muốn tuân thủ quy tắc hiện đại cho đầy đủ trường hợp, cần kiểm thử dữ liệu thực hoặc dùng thư viện Unicode cập nhật tương ứng (chẳng hạn ICU4J nếu ứng dụng chấp nhận dependency).

**Không** lấy `codePoints().count()` làm số "ký tự người dùng nhìn thấy" khi UI có emoji phức hợp.

### 13.2. Normalize không phải transliterate

`Normalizer.normalize(text, Form.NFC)` **không** đồng nghĩa bỏ dấu tiếng Việt hay chuyển mọi ký tự thành ASCII. Nó giải quyết canonical/compatibility normalization theo form được chọn; hành vi tìm kiếm "không dấu" cần thiết kế khác, cẩn thận ngôn ngữ và nghiệp vụ. Với dữ liệu định danh, password, chữ ký số hoặc hash, normalization có thể thay bytes và vì vậy cần một policy đã được thống nhất trước.

## 14. Java 17+ runnable: Normalization và emoji sequence

Tạo file **`UnicodeNormalizationDemo.java`**:

```java
import java.text.Normalizer;

public class UnicodeNormalizationDemo {
    public static void main(String[] args) {
        String precomposed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("Raw equals: "
                + precomposed.equals(decomposed));
        System.out.println("Normalized equals: "
                + Normalizer.normalize(
                        precomposed, Normalizer.Form.NFC)
                        .equals(Normalizer.normalize(
                                decomposed, Normalizer.Form.NFC)));

        System.out.println("Precomposed units/points: "
                + precomposed.length() + "/"
                + precomposed.codePoints().count());
        System.out.println("Decomposed units/points: "
                + decomposed.length() + "/"
                + decomposed.codePoints().count());

        // Woman + skin tone + ZWJ + laptop.
        String emoji = "\uD83D\uDC69\uD83C\uDFFD"
                + "\u200D\uD83D\uDCBB";

        System.out.println("Emoji units/points: "
                + emoji.length() + "/"
                + emoji.codePoints().count());
    }
}
```

Chạy:

```bash
javac --release 17 UnicodeNormalizationDemo.java
java UnicodeNormalizationDemo
```

**Stdout:**

```text
Raw equals: false
Normalized equals: true
Precomposed units/points: 1/1
Decomposed units/points: 2/2
Emoji units/points: 7/4
```

**Vì sao đáng chú ý:** Một pipeline thống kê dùng `chars().count()` hoặc `codePoints().count()` để giới hạn tên người dùng có thể đối xử khác nhau với hai chuỗi nhìn giống nhau; một trình soạn thảo dùng substring theo codepoint cũng có thể tách emoji ZWJ thành các thành phần không mong muốn. Phải xác định **đơn vị đo và chính sách normalization** theo nghiệp vụ trước khi chọn API.

## 15. StringBuilder và CharSequence mutable: Late binding, không sửa khi đang duyệt

`CharSequence.chars()` và `codePoints()` không buộc phải chụp snapshot nội dung ngay lúc gọi. Theo Javadoc, stream **liên kết khi terminal operation bắt đầu**. Với `StringBuilder` (mutable), điều này có nghĩa có thể thấy dữ liệu thêm **trước** khi terminal operation bắt đầu.

Ví dụ:

```java
StringBuilder builder = new StringBuilder("AB");

IntStream pending = builder.chars(); // Chưa duyệt.
builder.append("C");

long size = pending.count(); // Có thể thấy nội dung ABC.
```

Đây là đoạn trong phương thức; `IntStream` import từ `java.util.stream.IntStream`. Theo contract về late binding, việc append **trước terminal operation** là khác với việc thay đổi **trong khi đang duyệt**.

### 15.1. Sửa trong terminal operation: Không có kết quả được đảm bảo

Đừng làm:

```java
StringBuilder builder = new StringBuilder("ABC");

builder.chars().forEach(c -> builder.append('!'));
```

Đây là **phản ví dụ nguy hiểm**, không chạy: callback sửa chính sequence đang bị duyệt. Javadoc ghi kết quả không được xác định. Nó có thể gây số phần tử tăng, vòng lặp bất thường hoặc hành vi khác theo implementation; không thể dựa vào một output mong muốn.

### 15.2. Chụp snapshot cho dữ liệu mutable

Khi muốn xử lý một giá trị ổn định:

```java
String snapshot = builder.toString();

long count = snapshot.codePoints().count();
```

Đây là đoạn trong phương thức. `String` là bất biến, nên những thay đổi về sau của builder không làm snapshot đổi theo.

**Lưu ý concurrency:** Nếu thread khác đang sửa `StringBuilder` **đồng thời với việc gọi `toString()`**, quá trình tạo snapshot vẫn cần bảo vệ theo cơ chế đồng bộ/ownership; `StringBuilder` không thread-safe. `StringBuffer` có các phương thức synchronized nhưng vẫn phải hiểu compound operations và cách lấy snapshot đúng với ứng dụng.

### 15.3. Không reuse một stream

`IntStream` là pipeline dùng **một lần** khi đã gọi terminal operation. Không viết:

```java
IntStream stream = text.chars();
long n = stream.count();
int sum = stream.sum(); // IllegalStateException: stream đã dùng.
```

Đây là phản ví dụ; `text` được khai báo ở scope ngoài. Khi cần nhiều phép thống kê, tạo stream mới hoặc dùng mảng/snapshot đã materialize. `chars()` rẻ đối với nhiều use case, nhưng không nên lặp qua text lớn rất nhiều lần khi một lượt duyệt có thể tính các chỉ số.

## 16. Java 17+: Late binding và snapshot

Tạo file **`MutableCharSequenceDemo.java`**:

```java
import java.util.stream.IntStream;
import java.util.stream.Collectors;

public class MutableCharSequenceDemo {
    public static void main(String[] args) {
        CharSequence mutable = new StringBuilder("AB");

        IntStream pending = mutable.chars();
        ((StringBuilder) mutable).append("C");

        String observed = pending
                .mapToObj(codeUnit ->
                        Character.toString((char) codeUnit))
                .collect(Collectors.joining());

        System.out.println("Pending sees: " + observed);

        String snapshot = mutable.toString();
        ((StringBuilder) mutable).append("D");

        System.out.println("Snapshot: " + snapshot);
        System.out.println("Current: " + mutable);
    }
}
```

Chạy:

```bash
javac --release 17 MutableCharSequenceDemo.java
java MutableCharSequenceDemo
```

**Stdout:**

```text
Pending sees: ABC
Snapshot: ABC
Current: ABCD
```

Diễn giải:

1. `pending` được tạo khi builder còn `AB`, nhưng terminal operation chạy **sau** append `C`.
2. Chuỗi `observed` thu được là `ABC` vì stream late-binding.
3. `snapshot` là `String` bất biến đại diện cho `ABC`; builder sau đó thay đổi thành `ABCD`, snapshot vẫn giữ nguyên.
4. Demo thực hiện tất cả thay đổi **tuần tự trước hoặc sau khi terminal operation**, không cố gây concurrent modification không xác định.
5. Nếu cần dữ liệu text nhất quán giữa nhiều thread, dùng đồng bộ/ownership hoặc copy được thực hiện tại một thời điểm hợp lệ; đừng dựa vào việc `chars()` tự lock sequence.

## 17. Phân loại Unicode: `Character` nhận `int` hay `char`?

Các phương thức `Character` có overload nhận `char` hoặc `int`. Với text có supplementary letters, overload `int` làm việc với **code point đầy đủ**:

```java
String letter = "\uD801\uDC00"; // U+10400.

boolean byCodePoint =
        Character.isLetter(letter.codePointAt(0)); // true

boolean byCodeUnit =
        Character.isLetter(letter.charAt(0)); // false
```

Đây là đoạn trong phương thức. `Character.isLetter(char)` chỉ thấy high surrogate; nó không nhìn đủ hai code units để suy ra chữ cái ngoài BMP.

**Khuyến nghị cho Unicode classification:**

```java
long letters = text.codePoints()
        .filter(Character::isLetter)
        .count();
```

Đây là đoạn trong phương thức; `text` là `String`. `Character.isLetter(int)` nhận code point, có thể phân loại supplementary letter tốt hơn.

**Nhưng cũng phải hiểu giới hạn:**

- Dấu kết hợp có thể không được `Character.isLetter` phân loại là một letter độc lập.
- `isLetter` không có nghĩa một grapheme, một từ hoặc một tên người hợp lệ.
- Các quy tắc case mapping của cả chuỗi (ví dụ chuyển một ký tự thành nhiều ký tự tùy locale/case mapping) không được bảo đảm đầy đủ khi chỉ gọi `Character.toUpperCase(int)` cho từng code point.
- Với biến đổi chuỗi người dùng theo ngôn ngữ, cân nhắc `String.toUpperCase(Locale.ROOT)` hoặc locale thích hợp và policy normalization/collation; không tự dựng đầy đủ Unicode case folding từ `chars().map(Character::toUpperCase)`.

### 17.1. Không filter từng surrogate như ký tự riêng

Một đoạn:

```java
String s = "\uD83D\uDE00";
s.chars()
        .filter(c -> !Character.isSurrogate((char) c));
```

là **phản ví dụ** nếu mục tiêu là giữ emoji. Cả hai code units của emoji đều thuộc surrogate range nên phép filter này **loại bỏ toàn emoji**, trong khi `s.codePoints()` có một phần tử `0x1F600`.

Khi muốn **xác thực** thay vì xóa dữ liệu, kiểm tra malformed surrogate và thông báo lỗi; không lọc vô điều kiện các code units vì có thể phá hủy những cặp hợp lệ.

### 17.2. `codePoints()` không thay thế normalization, grapheme hoặc tokenizer

Tách mã điểm là bước đúng để xử lý Unicode code points, nhưng nếu cần:
- tách **từ** theo ngôn ngữ,
- phân biệt dấu phụ,
- phân đoạn **emoji clusters**,
- kiểm tra độ rộng hiển thị trên terminal,
- so sánh văn bản có canonical equivalence,

thì vẫn phải dùng API/phương pháp phù hợp riêng. `codePoints().count()` không tự biết font, locale, grapheme segmentation hay collation.

## 18. Kiểm tra và cắt theo UTF-16 trong hệ thống có giới hạn lưu trữ

Khi một API hoặc sheet cell giới hạn số **UTF-16 units**, Java có thể dùng:

```java
static int utf16Units(String value) {
    return value.length();
}
```

Đây là method trong class. Nếu app cần chia payload thành các mảnh và muốn **mỗi mảnh không chứa nửa surrogate pair hợp lệ**, dùng thuật toán điều chỉnh ranh giới đã minh họa. Không làm thay đổi dấu tiếng Việt, emoji, khoảng trắng hoặc newline khi mục tiêu là exact reconstruction.

### 18.1. Giá trị `char` và JavaScript đều thường dùng UTF-16 units

Java `String.length()` và JavaScript string `length` đều dựa trên UTF-16 code units đối với các chuỗi thông thường. Nhưng khi giao thức kết nối Java với hệ thống khác, hãy xác nhận rõ cách hệ thống đó **đếm capacity**: một vài API coi Unicode code point, vài API coi UTF-8 bytes và một số dùng UTF-16 units.

Đừng áp quy tắc code unit của Java cho mọi cơ sở dữ liệu hay Google Sheet mà không kiểm tra tài liệu giới hạn thực tế. Khi có giới hạn theo bytes, đo `getBytes(UTF_8).length`; khi giới hạn theo grapheme, phải phân đoạn grapheme.

### 18.2. Newline và combining marks vẫn là code units

`'\n'` thường một code unit; `"\r\n"` hai code units. Dấu tổ hợp Unicode là code point riêng và thường một code unit đối với combining mark trong BMP. Vì vậy cùng một đoạn text hiển thị giống nhau có thể khác độ dài do newline convention, Unicode normalization hay style emoji.

Nếu ghép nhiều mảnh để so sánh nguyên văn, **không tự thêm separator** giữa các mảnh. Kiểm tra `String.join("", parts).equals(original)` để xác nhận không mất ký tự/code unit.

## 19. Unicode code point và thứ tự so sánh

`String.compareTo` và một phép so sánh tuần tự trên từng `char` thường xét các **UTF-16 units**. Với supplementary code point, thứ tự code unit có thể khác thứ tự **giá trị số code point** đối với một số ký tự BMP.

Ví dụ `U+10000` biểu diễn high surrogate `D800`, và BMP `U+E000` có giá trị code unit E000. So `D800 < E000` theo UTF-16 units, nhưng `U+10000 > U+E000` khi so numeric code points. Nếu nghiệp vụ yêu cầu Unicode code point order hay collation theo ngôn ngữ, không suy luận từ `String.compareTo` rằng nó có cùng thứ tự.

**Khi nào cần quan tâm?** Sort tên người theo locale, tìm kiếm không phân biệt hoa/thường, indexing văn bản nhiều ngôn ngữ và lexical protocol có định nghĩa rõ. Với collation, dùng `Collator` theo locale và kiểm thử Unicode version, không viết một comparator ngây thơ lấy `chars().sum()`.

### 19.1. Normalization trong so sánh

Hai chuỗi nhìn giống nhau có thể có code units khác nhau. Nếu nghiệp vụ yêu cầu canonical equivalence, có thể normalize trước khi so sánh. Nhưng **không phải mọi biến đổi Unicode đều là canonical equivalence**: case folding, compatibility decomposition, dấu tiếng Việt và phân biệt ngôn ngữ có chính sách riêng.

Trong dữ liệu an ninh, identifiers và chữ ký điện tử, thay đổi normalization **sau khi ký hoặc hash** sẽ thay bytes; policy phải được chốt từ đầu và áp dụng nhất quán.

## 20. Bảng lỗi phổ biến và cách sửa

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| `chars().count()` để đếm "ký tự hiển thị" | Đếm UTF-16 units, emoji có thể cần hai units | Dùng grapheme segmentation nếu yêu cầu UI |
| `chars().count()` để đếm Unicode points | Cặp surrogate được tính thành hai | Dùng `codePoints().count()` hoặc `codePointCount` |
| `codePoints().count()` để đếm graphemes | ZWJ/combining marks có nhiều code points | Dùng Unicode grapheme segmentation |
| `String.length()` để giới hạn UTF-8 bytes | Bytes khác units | Dùng `getBytes(UTF_8).length`/encoder |
| `(byte) value` từ `chars()` rồi Base64 | Cắt bỏ bits cao, không phải UTF-8 | Encode text sang bytes trước |
| `charAt(i)` để lấy emoji | Chỉ trả một UTF-16 unit | Dùng `codePointAt(index)` và offset |
| `substring(0,n)` để lấy n code points | n đang là UTF-16 index | Dùng `offsetByCodePoints` |
| `codePointAt(i+1)` để bước một code point | Bước có thể rơi giữa cặp | Dùng `Character.charCount(cp)`/`offsetByCodePoints` |
| `Character.isLetter(char)` cho ký tự supplementary | char chứa một nửa pair | Dùng overload `isLetter(int)` |
| Filter loại surrogate từ `chars` | Xóa cả emoji hợp lệ | Xác thực pair, không lọc tùy tiện |
| Tin `codePoints()` luôn xuất valid scalar values | Unpaired surrogate vẫn xuất hiện | Kiểm tra range `D800..DFFF` |
| `isValidCodePoint(cp)` để loại surrogate lẻ | Range check này không đồng nghĩa scalar check | Loại thêm surrogate range |
| Dùng `Normalizer` cho exact roundtrip | Có thể đổi code units | Lưu bản gốc; normalize bản dẫn xuất |
| Sửa `StringBuilder` khi terminal operation duyệt | Contract không xác định | Lấy snapshot ổn định |
| Tạo `IntStream` rồi dùng hai terminal operations | Stream đã được consume | Tạo stream mới hoặc materialize |
| Giả định UTF-16 code unit luôn là một glyph | Font/grapheme phức tạp | Tách logic rendering khỏi encoding |
| Tin mã UTF-8 luôn từ 1 byte/code point | Ngoài ASCII có 2-4 bytes | Encode và đo bytes |
| Dùng `chars().parallel()` cho parser trạng thái | Index/state theo sequence và side effects khó an toàn | Ưu tiên ordered/sequential, không mutate |
| Đếm emoji ZWJ bằng `codePoints().count()` | Một emoji sequence có nhiều points | Sử dụng grapheme rules |
| Tính hash/an ninh bằng code units rồi coi tương đương Unicode canonically | Khác representation | Quy định normalization/canonicalization |
| Nhầm Java Unicode escapes với bytes nguồn | Escape là cú pháp mã nguồn Java, không phải encoding payload | Mã hóa text rõ bằng charset |

## 21. Checklist kiểm thử cho `CharSequence.chars()`

Kiểm thử nên có ít nhất các trường hợp sau:

- [ ] Chuỗi rỗng: `length == chars.count == codePoints.count == 0`.
- [ ] ASCII thuần: từng code unit trùng từng code point, nhưng không suy ra quy luật cho Unicode nói chung.
- [ ] Chữ Việt BMP đã tổ hợp: `é` hoặc `ế` thường một code unit/code point.
- [ ] Supplementary emoji: `"😀"` có hai UTF-16 units và một code point.
- [ ] Chuỗi pha trộn ASCII + emoji + tiếng Việt: các chỉ số và byte count khác nhau đúng.
- [ ] High surrogate lẻ: `codePoints()` giữ mã surrogate, không biến thành emoji.
- [ ] Low surrogate lẻ: vẫn là một int trong surrogate range.
- [ ] High và low đứng liền nhau: `codePoints()` ghép thành một supplementary code point.
- [ ] `Character.isLetter(int)` cho chữ supplementary và `isLetter(char)` trên high surrogate cho kết quả khác.
- [ ] `String.offsetByCodePoints` trả chỉ số **UTF-16**, không phải số code points.
- [ ] Cắt một cặp surrogate tại boundary bằng substring không bảo đảm text well-formed.
- [ ] Cắt an toàn theo giới hạn UTF-16 units, roundtrip chính xác, không chèn separator.
- [ ] Trường hợp maxUnits quá nhỏ để chứa pair: có policy từ chối hoặc thiết kế khác.
- [ ] Combining mark: composed/decomposed có thể khác code point count.
- [ ] Emoji ZWJ: code point count không là grapheme count.
- [ ] Encode UTF-8 rồi Base64 và decode roundtrip với chuỗi well-formed.
- [ ] Invalid UTF-16 khi encode phải có policy REPORT/REPLACE nhất quán.
- [ ] `StringBuilder` thay đổi trước terminal operation có thể được thấy; thay đổi trong terminal operation là sai contract.
- [ ] Stream không tái sử dụng cho hai terminal operations.
- [ ] Không lấy `chars().sum()` làm checksum/bản mã Unicode hay thứ tự collation mà không có đặc tả.
- [ ] Lưu code unit count và byte count riêng nếu một hệ thống có cả hai giới hạn.
- [ ] Khi dùng Unicode version/BreakIterator khác nhau, kiểm thử các emoji/grapheme thực tế của UI.

### 21.1. Tại sao không chỉ kiểm thử một emoji?

Một phép thử chỉ với `U+1F600` xác minh surrogate pair nhưng **không** xác minh combining marks, ZWJ, variation selectors, skin-tone modifiers hoặc regional indicator flags. Một phép thử chỉ với tiếng Việt BMP có thể tình cờ khiến `length == codePoints.count` rồi làm người học kết luận sai rằng hai API luôn giống nhau.

Kết hợp các test có **nhiều loại input** và mong đợi rõ số units/points/bytes. Tránh test dựa vào cách terminal render emoji vì font/OS có thể khác; so số hex/codepoint là ổn định hơn.

## 22. Java 17+: Bộ kiểm thử hợp đồng

Tạo file **`CharSequenceBoundaryChecks.java`**. Đây là một chương trình kiểm thử **không phụ thuộc flag `-ea`**, vì mọi bất biến dùng `check` ném `AssertionError` nếu sai:

```java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;

public class CharSequenceBoundaryChecks {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static boolean hasUnpaired(String s) {
        return s.codePoints()
                .anyMatch(cp -> cp >= 0xD800 && cp <= 0xDFFF);
    }

    public static void main(String[] args) {
        String text = "A\uD83D\uDE00\u1EBF";

        check(text.length() == 4, "UTF-16 length");
        check(text.chars().count() == 4, "chars count");
        check(text.codePoints().count() == 3, "point count");
        check(text.getBytes(StandardCharsets.UTF_8).length == 8,
                "UTF-8 bytes");
        System.out.println("Units versus points: PASS");

        int[] units = text.chars().toArray();
        int[] points = text.codePoints().toArray();

        check(units[1] == 0xD83D, "high surrogate");
        check(units[2] == 0xDE00, "low surrogate");
        check(points[1] == 0x1F600, "supplementary point");
        System.out.println("Surrogate pairing: PASS");

        String indexed = "A\uD83D\uDE00B";
        int safeEnd = indexed.offsetByCodePoints(0, 2);

        check(safeEnd == 3, "offset");
        check(indexed.substring(0, safeEnd)
                .codePoints().count() == 2, "safe substring");
        check(Character.isHighSurrogate(
                indexed.substring(0, 2).charAt(1)),
                "broken half-pair not detected");
        System.out.println("Code-point offset: PASS");

        check(hasUnpaired("X\uD83DY"), "high alone");
        check(hasUnpaired("X\uDE00Y"), "low alone");
        check(!hasUnpaired("\uD83D\uDE00"), "valid pair");
        System.out.println("Malformed UTF-16: PASS");

        String composed = "\u00E9";
        String decomposed = "e\u0301";

        check(!composed.equals(decomposed), "raw distinct");
        check(Normalizer.normalize(
                    composed, Normalizer.Form.NFC)
                .equals(Normalizer.normalize(
                    decomposed, Normalizer.Form.NFC)),
                "normalized equivalent");
        System.out.println("Normalization: PASS");

        String letter = "\uD801\uDC00";
        check(Character.isLetter(letter.codePointAt(0)),
                "supplementary letter");
        check(!Character.isLetter(letter.charAt(0)),
                "char overload should see high surrogate");
        System.out.println("Character overload: PASS");

        System.out.println("All checks: PASS");
    }
}
```

Chạy:

```bash
javac --release 17 CharSequenceBoundaryChecks.java
java CharSequenceBoundaryChecks
```

**Stdout:**

```text
Units versus points: PASS
Surrogate pairing: PASS
Code-point offset: PASS
Malformed UTF-16: PASS
Normalization: PASS
Character overload: PASS
All checks: PASS
```

Bộ test này xác nhận **hợp đồng nền của `chars()`**, cách ghép surrogate, index theo UTF-16 units, phát hiện dữ liệu không well-formed và Unicode normalization/case classification. Nó không xác nhận **grapheme segmentation** cho mọi Unicode version — đó là một bài toán khác, cần bộ dữ liệu kiểm thử thực tế và nguồn quy tắc tương ứng.

## 23. Câu hỏi ôn tập

1. `CharSequence.chars()` trả `Stream<Character>`, `IntStream` hay `Stream<String>`?
2. Mỗi phần tử `chars()` là một UTF-16 unit hay một Unicode code point?
3. Tại sao `chars()` zero-extend từ `char` sang `int`?
4. `"😀".chars().count()` và `"😀".codePoints().count()` khác nhau thế nào?
5. `String.length()` có phải số ký tự người dùng nhìn thấy không?
6. Khi `codePoints()` gặp high surrogate đứng lẻ, nó tự từ chối input hay phát giá trị riêng?
7. `Character.isValidCodePoint(0xD800)` có thể dùng một mình để loại surrogate lẻ không?
8. `String.codePointAt(index)` nhận index code point hay UTF-16?
9. Nếu lấy `substring(0,2)` từ `"A😀B"`, phần cuối là gì?
10. Muốn lấy hai code points đầu `"A😀B"` an toàn, nên dùng API nào?
11. Vì sao `Character.isLetter(char)` có thể bỏ sót supplementary letters?
12. `chars().count()` có bằng `getBytes(UTF_8).length` không?
13. Muốn tạo Base64 từ String Unicode, nên làm bước nào trước?
14. Một grapheme cluster có thể gồm nhiều code points không?
15. `"é"` và `"e\u0301"` có bằng nhau theo `String.equals` không? Có thể normalize để so sánh không?
16. Khi lấy stream từ `StringBuilder`, thay đổi builder **trước** terminal operation có thể xuất hiện trong stream không?
17. Có thể sửa `StringBuilder` từ callback `chars().forEach` đang duyệt nó không?
18. `LongAdder` có liên quan đến `CharSequence.chars()` không, hay là bài toán concurrency khác?
19. Nếu giới hạn là 30.000 UTF-16 units, nên dùng code point count hay `length()`?
20. Vì sao cần kiểm tra high+low surrogate khi chia chunk theo giới hạn code units?
21. `StringBuilder.appendCodePoint` có giải quyết việc tính grapheme không?
22. Khi kiểm tra tên hiển thị hoặc password, nên xác định rõ những đơn vị và chính sách nào?

**Gợi ý đáp án:** (1) `IntStream`. (2) UTF-16 code unit. (3) `char` là không dấu 16-bit, nên mở rộng int không âm. (4) Hai units, một code point. (5) Không. (6) Phát một giá trị surrogate riêng, không tự từ chối. (7) Không; phải kiểm tra thêm surrogate range. (8) UTF-16 units. (9) High surrogate lẻ sau A. (10) `offsetByCodePoints(0,2)` rồi `substring`. (11) Chỉ nhìn một nửa pair. (12) Không; encoding bytes theo charset. (13) `getBytes(StandardCharsets.UTF_8)` rồi Base64 encode. (14) Có, như dấu kết hợp và emoji ZWJ. (15) Raw false; NFC có thể cho cùng chuỗi chuẩn. (16) Có do late binding. (17) Không, contract không xác định. (18) Không liên quan trực tiếp; LongAdder dành cho thống kê concurrency. (19) `String.length()` và tránh cắt đôi surrogate. (20) Để bảo toàn một supplementary code point. (21) Không; chỉ bổ sung code point vào StringBuilder. (22) Units/points/bytes/graphemes, charset, normalization, Unicode version, locale và ranh giới input.

**Kết luận:** `CharSequence.chars()` là công cụ duyệt **các UTF-16 code units** được mở rộng thành int, không phải công cụ tổng quát để "duyệt mọi ký tự Unicode". Nếu cần một supplementary Unicode code point nguyên vẹn, dùng `codePoints()` hoặc `codePointAt`/`offsetByCodePoints`; nếu cần các ký tự người dùng nhìn thấy, xem xét **grapheme segmentation**; nếu cần Base64 hoặc giới hạn truyền tải, chuyển `String` sang **bytes theo charset rõ ràng** trước. Luôn xử lý cẩn thận surrogate pairs, dữ liệu malformed và mutable CharSequence đang được duyệt. Chọn đúng đơn vị sẽ tránh lỗi cắt emoji, đếm sai độ dài, phân loại sai Unicode hoặc làm hỏng dữ liệu khi encode.

## Tài liệu tham khảo Java chính thức, vẫn còn áp dụng

- `CharSequence`: hợp đồng `chars()`, `codePoints()`, late binding và unpaired surrogates — https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/CharSequence.html
- `String`: `length`, `charAt`, `codePointAt`, `codePointCount`, `offsetByCodePoints`, `substring` — https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html
- `Character`: UTF-16 representation, surrogate pairs, `toCodePoint`, `toChars`, `isLetter(int)` — https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Character.html
- `StringBuilder`: mutable text, `appendCodePoint`, code-point access — https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/StringBuilder.html
- `StandardCharsets` và `CharsetEncoder`: UTF-8, malformed input và error policy — https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/StandardCharsets.html và https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetEncoder.html
- `Base64`: encode/decode byte arrays và Base64 ASCII representation — https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Base64.html
- `Normalizer`: Unicode normalization — https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html
- `BreakIterator`: text boundary analysis tùy ngôn ngữ/Unicode version — https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/BreakIterator.html
- `IntStream`: primitive stream/terminal operations — https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/IntStream.html
