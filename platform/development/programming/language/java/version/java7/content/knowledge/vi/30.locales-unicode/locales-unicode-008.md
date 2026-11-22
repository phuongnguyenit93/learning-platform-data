# Java 7 — Locale và Unicode: Nhận diện script và duyệt văn bản theo code point

## 1. Mục tiêu bài học và phạm vi

Java lưu `String` bằng một chuỗi **UTF-16 code units**; trong khi thao tác Unicode thường cần làm việc với **code points** và phân loại **script** (hệ chữ viết). Vì vậy, việc lặp `charAt(i)` trên từng ký tự `char` có thể phân tích sai những ký tự ngoài Basic Multilingual Plane, ví dụ emoji. Bài học giải quyết đúng đề bài **“Nhận diện script và duyệt văn bản theo code point”**, thuộc chủ đề **“Locale và Unicode”**.

Các API lõi đã có từ Java 7, chẳng hạn `Character.UnicodeScript` và `Character.codePointAt`, vẫn hữu dụng trên Java 17+. Bài dùng thêm các API hiện đại `String.codePoints()`, Java Stream `toList()`, `Locale.forLanguageTag`, `Normalizer`, Unicode-aware regular expressions theo Java 17; không dạy các cách xử lý mã hóa lỗi thời.

Kết quả mong đợi:
1. Phân biệt UTF-16 `char`, Unicode code point, Unicode scalar value, grapheme cluster và glyph hiển thị.
2. Duyệt `String` tiến/lùi đúng bằng `codePointAt`/`codePointBefore` cùng `Character.charCount`.
3. Dùng `String.codePoints()` và biết khác `String.chars()`.
4. Phân loại code point theo `Character.UnicodeScript.of(cp)`.
5. Hiểu `COMMON`, `INHERITED`, `UNKNOWN` và những giới hạn của script property.
6. Dùng `UnicodeScript.forName` cho tên/ISO 15924 aliases khi được hỗ trợ.
7. Phân biệt script của code point với `Locale.getScript()` và `UnicodeBlock`.
8. Không lẫn code points với ký tự người dùng nhìn thấy; biết `\X` và các yêu cầu grapheme segmentation.
9. Dùng `String.offsetByCodePoints`, `String.codePointCount`, `Character.toChars` và `StringBuilder.appendCodePoint`.
10. Phát hiện UTF-16 **unpaired surrogate** và không xem nó là một scalar value hợp lệ.
11. Nhận biết normalization, combining marks và locale-sensitive case mapping.
12. Đánh giá rủi ro mixed-script/visual spoofing mà không đưa ra tuyên bố bảo mật quá mức.
13. Áp dụng Java 17 APIs còn được hỗ trợ, chạy được 18 ví dụ độc lập, với output đã xác minh.

## 2. Năm tầng khác nhau của văn bản Unicode

```text
Raw bytes (UTF-8, UTF-16BE, ...)
        |
 Decode using correct Charset
        |
Java String: UTF-16 code units (char)
        |
Code-point iteration: int from String.codePoints()
        |
Unicode properties: Script, Category, Normalization
        |
Grapheme segmentation / text layout
        |
Glyphs rendered by font and shaping engine
```

Không được đánh đồng những tầng này:

| Khái niệm | Mô tả | Ví dụ |
| --- | --- | --- |
| Byte | Đơn vị trong encoding/storage | UTF-8 có số bytes biến đổi |
| `char` / UTF-16 code unit | Số không dấu 16 bit trong Java | Emoji supplementary dùng hai `char` |
| Code point | Giá trị U+0000..U+10FFFF trong Unicode coding space | `U+1F600` |
| Unicode scalar value | Code point **ngoại trừ** vùng surrogate U+D800..U+DFFF | U+1F600 là scalar, U+D83D không phải |
| Grapheme cluster | Một đơn vị ký tự nhìn/biên tập theo Unicode segmentation | `e` + combining acute accent |
| Glyph | Hình hiển thị do font/shaping quyết định | Một cluster có thể có nhiều glyph hoặc một ligature |

**Bài học trực tiếp xử lý code point và script**, không tự nhận giải quyết mọi vấn đề grapheme segmentation hay rendering.

### 2.1. Vì sao `String.length()` không phải số “ký tự Unicode”?

`String.length()` đếm **UTF-16 code units**. Emoji ở `U+1F600` được mã hóa thành hai `char` (high và low surrogate), vì code point lớn hơn U+FFFF. Với chuỗi `"A"` + U+1F600 + `"漢"`: `length()==4` nhưng có **3 code points**.

### 2.2. `char` vẫn có ích khi nào?

Khi cần xử lý giao thức/định dạng dựa trên UTF-16 units, thao tác với `char[]`, hoặc chỉ chấp nhận ASCII/BMP đã được validate, `char` có thể là lựa chọn phù hợp. Sai lầm nằm ở việc coi **mọi `char` đều là một Unicode character hoàn chỉnh**.

## 3. UTF-16: surrogate pair là gì?

Code points trong BMP (U+0000..U+FFFF, trừ các mã surrogate) thường chiếm **một `char`**. Những scalar values từ U+10000 đến U+10FFFF chiếm **hai `char`**:

- High surrogate: U+D800..U+DBFF.
- Low surrogate: U+DC00..U+DFFF.
- Một high đứng trước một low tạo ra **một supplementary code point**.

Ví dụ `U+1F600` trong Java:

```java
String emoji = "\uD83D\uDE00";
System.out.println(emoji.length());                  // 2 UTF-16 units
System.out.println(emoji.codePoints().count());      // 1 code point
System.out.println(emoji.codePointAt(0)==0x1F600);   // true
```

Đây là **mảnh Java**, chưa có class `main` độc lập. Escape sequences `\uD83D\uDE00` biểu diễn surrogate pair trong Java source. Java compiler xử lý Unicode escapes sớm; trong examples này cặp surrogate tạo đúng string có một supplementary code point.

### 3.1. Code point là `int`, không phải `char`

Java trả code point qua `int` để biểu diễn đầy đủ U+0000..U+10FFFF. Không cast `int cp` sang `char` để lưu emoji; cast sẽ chỉ giữ 16 bit thấp, mất thông tin.

### 3.2. Không tự cộng index bằng 1

Một vòng lặp code point cần tăng index `i` bằng `Character.charCount(cp)` (1 hoặc 2 cho các code points được biểu diễn qua UTF-16 bình thường), không phải luôn `i++`.

## 4. Character.UnicodeScript: nhận diện hệ chữ viết của code point

`Character.UnicodeScript` là một `enum` chứa các tên scripts theo dữ liệu Unicode trong JDK. Dùng:

```java
Character.UnicodeScript script =
    Character.UnicodeScript.of(0x0416);
System.out.println(script);  // CYRILLIC
```

Đây là mảnh minh họa. Phương thức `of(int codePoint)` có thể ném `IllegalArgumentException` khi input nằm ngoài giới hạn code-point value.

Ví dụ phân loại phổ biến:

| Code point | Mô tả | `UnicodeScript.of` |
| --- | --- | --- |
| U+0041 | Latin capital A | `LATIN` |
| U+0416 | Cyrillic capital Zhe | `CYRILLIC` |
| U+6F22 | CJK Unified Ideograph | `HAN` |
| U+0915 | Devanagari letter Ka | `DEVANAGARI` |
| U+0628 | Arabic letter Beh | `ARABIC` |
| U+1F600 | Grinning face emoji | `COMMON` |
| U+0301 | Combining acute accent | `INHERITED` |
| U+0035 | Digit 5 | `COMMON` |

**Không suy** từ `LATIN` rằng văn bản là tiếng Anh, từ `HAN` rằng văn bản là tiếng Trung hay từ `ARABIC` rằng mọi ký tự đều thuộc tiếng Ả Rập. **Script là thuộc tính của code point; language là thuộc tính/ngữ cảnh khác.**

## 5. Chương trình 1 — ScriptPropertyDemo.java

```java
import java.util.Locale;

public final class ScriptPropertyDemo {
 public static void main(String[] args) {
   int[] cps={
       'A',0x0416,0x6F22,0x0915,0x0628,
       0x1F600,0x0301,'5'
   };
   for(int cp:cps) {
     System.out.println(String.format(
         Locale.ROOT,"U+%04X=%s",cp,
         Character.UnicodeScript.of(cp)));
   }
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ScriptPropertyDemo.java
java ScriptPropertyDemo
```

**Stdout đã kiểm thử:**

```text
U+0041=LATIN
U+0416=CYRILLIC
U+6F22=HAN
U+0915=DEVANAGARI
U+0628=ARABIC
U+1F600=COMMON
U+0301=INHERITED
U+0035=COMMON
```

`String.format(Locale.ROOT,...)` cố định locale khi format đầu ra demo; nó không thay đổi `UnicodeScript.of`. Các scripts có thể có tên enum/độ bao phủ dữ liệu khác nhau khi JDK nâng phiên bản Unicode; hãy test với JDK đích, không hardcode giả định Unicode database luôn bất biến.

## 6. COMMON, INHERITED và UNKNOWN không có nghĩa “bị lỗi”

Ba giá trị này cần hiểu chính xác:

- **`COMMON`**: các code points không gắn riêng với một hệ chữ viết, ví dụ nhiều chữ số, dấu câu và emoji.
- **`INHERITED`**: các code points như combining marks, có script phụ thuộc vào ngữ cảnh surrounding text.
- **`UNKNOWN`**: code points chưa được gán script trong Unicode version của JDK hoặc không có script được xác định, ví dụ một code point unassigned.

Đừng bỏ qua các marks `INHERITED` khi chuẩn hóa văn bản; chúng có thể ảnh hưởng việc hiển thị, so khớp, diacritic và security. Cũng đừng tự gán mọi `COMMON` cho script của ký tự bên trái: Unicode có **Script_Extensions** và quy tắc segmentation phức tạp hơn.

### 6.1. Script_Extensions khác Script

`UnicodeScript.of(cp)` trả property **Script** cơ bản, không phải đầy đủ tập giá trị `Script_Extensions` của mỗi ký tự. Một dấu câu hoặc mark có thể hợp lệ trong nhiều ngữ cảnh script. Muốn xây bộ phân tích mixed-script/identifier theo Unicode TR39 cần thuật toán hoàn chỉnh, không thể chỉ dùng một `EnumSet` và `of`.

## 7. Duyệt tiến từng code point bằng codePointAt

Pattern chuẩn cho `String`:

```java
for (int i=0; i<text.length();) {
    int cp=text.codePointAt(i);
    // Process this Unicode code point.
    i+=Character.charCount(cp);
}
```

Đây là **mảnh minh họa** dùng biến `String text`. `i` luôn tính bằng **UTF-16 offset**. `cp` là một `int` code point. Với surrogate pair hợp lệ, `charCount(cp)==2`, nhảy qua cả high/low surrogate.

### 7.1. Dùng String.codePointAt hay Character.codePointAt?

Có nhiều overload:
- `String.codePointAt(int index)`.
- `Character.codePointAt(CharSequence seq,int index)`.
- `Character.codePointAt(char[] a,int index)` và overload giới hạn index.

Với `String`, instance method ngắn gọn. Với API nhận một `CharSequence` bất kỳ, `Character.codePointAt(sequence,index)` có thể phù hợp. Chú ý `CharSequence` mutable: nếu thay đổi song song khi đang duyệt, logic có thể sai. Dùng immutable `String` hoặc snapshot nếu cần.

## 8. Chương trình 2 — ForwardCodePointDemo.java

```java
import java.util.Locale;

public final class ForwardCodePointDemo {
 public static void main(String[] args) {
   String s="A\uD83D\uDE00\u6F22";

   System.out.println("utf16Length="+s.length());
   System.out.println("codePointCount="+
       s.codePointCount(0,s.length()));

   for(int index=0;index<s.length();) {
     int cp=s.codePointAt(index);
     System.out.println("index="+index+" cp="+
         String.format(Locale.ROOT,"U+%04X",cp));
     index+=Character.charCount(cp);
   }
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ForwardCodePointDemo.java
java ForwardCodePointDemo
```

**Stdout đã kiểm thử:**

```text
utf16Length=4
codePointCount=3
index=0 cp=U+0041
index=1 cp=U+1F600
index=3 cp=U+6F22
```

**Giải thích:** index 1 là vị trí high surrogate của emoji. `codePointAt(1)` ghép cặp và trả `0x1F600`; `Character.charCount` trả 2 nên index mới là 3, bỏ qua low surrogate ở index 2. Chữ Hán cuối cùng dùng một UTF-16 code unit.

## 9. Duyệt ngược bằng codePointBefore

Nếu cần quét chuỗi từ phải sang trái theo code points:

```java
for(int i=text.length();i>0;) {
    int cp=text.codePointBefore(i);
    i-=Character.charCount(cp);
    // Process cp; i points to its UTF-16 starting position.
}
```

Đây là **mảnh minh họa**, cần biến `String text`. `codePointBefore(i)` đọc code point **ngay trước** index `i`. Index bắt đầu từ `length()`, trừ đi số UTF-16 units của code point được đọc.

**Đừng** làm `i--` đơn lẻ rồi xử lý `charAt(i)`, vì bạn sẽ tách một surrogate pair thành hai phần không hợp lệ.

## 10. Chương trình 3 — BackwardCodePointDemo.java

```java
import java.util.Locale;

public final class BackwardCodePointDemo {
 public static void main(String[] args) {
   String s="A\uD83D\uDCA1\u4E2D";

   for(int index=s.length();index>0;) {
     int cp=s.codePointBefore(index);
     index-=Character.charCount(cp);
     System.out.println("index="+index+" cp="+
         String.format(Locale.ROOT,"U+%04X",cp));
   }
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 BackwardCodePointDemo.java
java BackwardCodePointDemo
```

**Stdout đã kiểm thử:**

```text
index=3 cp=U+4E2D
index=1 cp=U+1F4A1
index=0 cp=U+0041
```

`U+1F4A1` là supplementary code point cần hai units. Khi quay lại từ index 3, codePointBefore ghép đúng cặp ở offsets 1 và 2 rồi giảm index đi 2.

## 11. String.chars() khác String.codePoints()

Java có hai streams dễ nhầm:

| API | Dữ liệu trả về | Surrogate pair |
| --- | --- | --- |
| `String.chars()` | `IntStream` của **UTF-16 char values** | Hai ints tương ứng high và low |
| `String.codePoints()` | `IntStream` của **Unicode code points** | Một int cho một cặp hợp lệ |
| `String.length()` | Số UTF-16 code units | Tính 2 |
| `String.codePointCount(0,length())` | Số code points trong khoảng UTF-16 | Tính 1 cho cặp hợp lệ |

**Cực kỳ quan trọng:** `String.codePoints()` không bảo đảm đầu vào là UTF-16 well-formed. Nếu có surrogate không ghép được, stream phát ra giá trị surrogate code unit (int) thay vì ném lỗi. Phần tiếp theo xử lý giới hạn này.

### 11.1. Khi nào dùng stream?

`s.codePoints().forEach(cp -> {...})` rất tiện cho thống kê/property checks hoặc transform stateless. Khi cần giữ **UTF-16 offsets để substring**, manual loop hay `offsetByCodePoints` phù hợp hơn. Không mặc định stream nhanh hơn; chọn theo readability, allocation và benchmark thực tế.

## 12. Chương trình 4 — CharsVsCodePointsDemo.java

```java
import java.util.Arrays;

public final class CharsVsCodePointsDemo {
 public static void main(String[] args) {
   String s="A\uD83D\uDE00\u0301";

   System.out.println("charUnits="+s.chars().count());
   System.out.println("logicalCodePoints="+
       s.codePoints().count());
   System.out.println("utf16Units="+
       Arrays.toString(s.chars().toArray()));
   System.out.println("codePoints="+
       Arrays.toString(s.codePoints().toArray()));
   System.out.println("scriptsByCodePoint="+
       s.codePoints()
        .mapToObj(cp->Character.UnicodeScript.of(cp).name())
        .toList());
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 CharsVsCodePointsDemo.java
java CharsVsCodePointsDemo
```

**Stdout đã kiểm thử:**

```text
charUnits=4
logicalCodePoints=3
utf16Units=[65, 55357, 56832, 769]
codePoints=[65, 128512, 769]
scriptsByCodePoint=[LATIN, COMMON, INHERITED]
```

`55357` và `56832` là hai surrogate code units của emoji; `128512` là code point hoàn chỉnh. `769` (U+0301) là combining acute accent, `INHERITED`.

## 13. Unpaired surrogate: giới hạn không thể bỏ qua

`String` Java có thể chứa một high surrogate đứng lẻ hoặc low surrogate đứng lẻ. Đây là **UTF-16 không well-formed** cho một chuỗi Unicode scalar values. Java `String.codePoints()` vẫn có quy tắc trả về một int đại diện surrogate code unit đó, không tự sửa thành `U+FFFD`.

Phân biệt kỹ:

- `Character.isValidCodePoint(0xD83D)` trả **true**, vì giá trị U+D83D nằm trong Unicode code point range U+0000..U+10FFFF.
- Tuy nhiên U+D83D là **surrogate**, không phải **Unicode scalar value**.
- Một token code point có giá trị surrogate **không được** dùng làm một scalar độc lập.
- `String.codePoints()` có thể phát ra 0xD83D cho input ill-formed.
- Trên văn bản phải là well-formed UTF-16, cần kiểm **unpaired surrogate**, không chỉ `isValidCodePoint`.

### 13.1. Kiểm tra scalar values của String

```java
boolean allScalars=text.codePoints()
    .allMatch(cp -> cp < 0xD800 || cp > 0xDFFF);
```

Đây là **mảnh minh họa** với `String text`. Vì int từ String.codePoints() luôn nằm trong phạm vi UTF-16/codepoint, loại mã surrogate là đủ để kiểm không có surrogate đứng lẻ; các surrogate đã ghép thành supplementary code point không nằm trong vùng D800..DFFF.

Lưu ý `Normalizer`/encoding errors có thể thay thế hoặc xử lý input khác nhau, nên nếu policy cần **từ chối** malformed text, validate ở đúng boundary, tránh thay thế silent rồi đánh mất nguyên nhân.

## 14. Chương trình 5 — SurrogateValidationDemo.java

```java
public final class SurrogateValidationDemo {
 public static void main(String[] args) {
   String unpaired="\uD83D";
   String paired="\uD83D\uDE00";

   System.out.println("unpairedLength="+unpaired.length());
   System.out.println("unpairedCodePoints="+
       unpaired.codePoints().count());
   System.out.println("unpairedStreamHasSurrogate="+
       unpaired.codePoints().anyMatch(
           cp->cp>=0xD800 && cp<=0xDFFF));
   System.out.println("isValidCodePointSurrogateValue="+
       Character.isValidCodePoint(0xD83D));

   System.out.println("pairedUtf16Length="+
       paired.length());
   System.out.println("pairedCodePoints="+
       paired.codePoints().count());
   System.out.println("pairedAllUnicodeScalars="+
       paired.codePoints().allMatch(
           cp->cp<0xD800 || cp>0xDFFF));
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 SurrogateValidationDemo.java
java SurrogateValidationDemo
```

**Stdout đã kiểm thử:**

```text
unpairedLength=1
unpairedCodePoints=1
unpairedStreamHasSurrogate=true
isValidCodePointSurrogateValue=true
pairedUtf16Length=2
pairedCodePoints=1
pairedAllUnicodeScalars=true
```

**Điểm bất ngờ có chủ ý:** `Character.isValidCodePoint` kiểm **code point range**, không kiểm **scalar value**. Nếu bảo mật/serialization yêu cầu text well-formed, cần validation khác.

## 15. Code-point offsets so với UTF-16 offsets

`String.substring(start,end)`, `charAt(index)` và `String.length()` sử dụng **UTF-16 offsets**. Để đi đến code point thứ N, dùng:

- `String.offsetByCodePoints(index,offset)`.
- `String.codePointCount(beginIndex,endIndex)`.

Không làm `substring(0,n)` nếu `n` là **số code points**, vì có thể cắt đôi một surrogate pair.

```text
String: A + U+1F600 + B
UTF-16 indices:
  A:   [0]
  emoji high: [1]
  emoji low:  [2]
  B:   [3]
  end: [4]

Code-point indices: 0=A, 1=emoji, 2=B, end=3
offsetByCodePoints(0,2) => UTF-16 index 3
```

## 16. Chương trình 6 — OffsetByCodePointsDemo.java

```java
public final class OffsetByCodePointsDemo {
 public static void main(String[] args) {
   String s="A\uD83D\uDE00B";
   int afterSecond=s.offsetByCodePoints(0,2);

   System.out.println("lengthUtf16="+s.length());
   System.out.println("codePointCount="+
       s.codePointCount(0,s.length()));
   System.out.println("afterTwoCodePointsIndex="+
       afterSecond);
   System.out.println("firstTwoUtf16Length="+
       s.substring(0,afterSecond).length());
   System.out.println("codePointAtSecondIsEmoji="+
       (s.codePointAt(1)==0x1F600));
   System.out.println("lastCodePointStartsAt="+
       s.offsetByCodePoints(s.length(),-1));
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 OffsetByCodePointsDemo.java
java OffsetByCodePointsDemo
```

**Stdout đã kiểm thử:**

```text
lengthUtf16=4
codePointCount=3
afterTwoCodePointsIndex=3
firstTwoUtf16Length=3
codePointAtSecondIsEmoji=true
lastCodePointStartsAt=3
```

`substring(0,3)` giữ A + emoji thành **3 UTF-16 units = 2 code points**. Với thao tác cắt chuỗi theo số ký tự người dùng hiển thị, offsetByCodePoints vẫn có thể chưa đủ nếu grapheme cluster chứa nhiều code points.

## 17. UnicodeScript.forName: đọc tên hoặc alias

`Character.UnicodeScript.forName(String)` có thể trả enum value tương ứng với tên script hoặc một alias Unicode/ISO 15924 được triển khai, ví dụ `Latn`, `Cyrl`, `Hani`.

Không tự tin rằng **mọi** chuỗi đầu vào là tên script hợp lệ:
- Alias không tồn tại có thể ném `IllegalArgumentException`.
- Phải validate/handle khi dữ liệu đến từ config/user.
- Không dùng `UnicodeScript.valueOf("Latn")` để tra ISO aliases; `valueOf` dùng enum constant name, còn `forName` có quy tắc aliases.
- Khi lưu config cross-platform, dùng canonical identifiers và kiểm trên JDK được hỗ trợ.

## 18. Chương trình 7 — ScriptAliasDemo.java

```java
public final class ScriptAliasDemo {
 public static void main(String[] args) {
   System.out.println("Latn="+
       Character.UnicodeScript.forName("Latn"));
   System.out.println("Latin="+
       Character.UnicodeScript.forName("LATIN"));
   System.out.println("Hani="+
       Character.UnicodeScript.forName("Hani"));
   System.out.println("Cyrl="+
       Character.UnicodeScript.forName("Cyrl"));

   boolean invalid=false;
   try {
     Character.UnicodeScript.forName("NotAScript");
   }catch(IllegalArgumentException ex){
     invalid=true;
   }
   System.out.println("invalidAliasRejected="+invalid);
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ScriptAliasDemo.java
java ScriptAliasDemo
```

**Stdout đã kiểm thử:**

```text
Latn=LATIN
Latin=LATIN
Hani=HAN
Cyrl=CYRILLIC
invalidAliasRejected=true
```

## 19. UnicodeScript khác Locale.getScript()

Một `Locale` mô tả các convention liên quan **ngôn ngữ, vùng và script subtag**. Ví dụ BCP 47:
- `en-Latn-US`: English với script subtag Latn.
- `sr-Cyrl-RS`: Serbian với script subtag Cyrl.
- `ja-JP`: không có explicit script subtag, `Locale.getScript()` có thể là chuỗi trống.

`Character.UnicodeScript.of('A')` lại nhìn **thuộc tính của ký tự cụ thể**; nó **không nhận Locale**.

Cần phân biệt:

| Câu hỏi | API |
| --- | --- |
| Code point này thuộc script nào theo Unicode database? | `UnicodeScript.of(cp)` |
| Locale được khai báo dùng script subtag nào? | `locale.getScript()` |
| Văn bản là tiếng gì? | Không có câu trả lời từ riêng hai API trên |
| Cần quy tắc viết hoa/thường cho ngôn ngữ? | `toLowerCase(locale)`/`toUpperCase(locale)` với locale phù hợp |
| Cần tokenization/word-break thực tế? | Phụ thuộc segmentation/language rules, không chỉ script |

### 19.1. Một script có thể dùng cho nhiều ngôn ngữ

Latin script được dùng bởi nhiều ngôn ngữ, không chỉ English. Han characters xuất hiện trong nhiều hệ chữ viết/ngữ cảnh của Đông Á. Script detection là **một tín hiệu**, không phải language identification.

## 20. Chương trình 8 — ScriptVsLocaleDemo.java

```java
import java.util.Locale;

public final class ScriptVsLocaleDemo {
 public static void main(String[] args) {
   Locale en=Locale.forLanguageTag("en-Latn-US");
   Locale sr=Locale.forLanguageTag("sr-Cyrl-RS");
   Locale ja=Locale.forLanguageTag("ja-JP");

   System.out.println("localeEnglishScript="+
       en.getScript());
   System.out.println("localeSerbianScript="+
       sr.getScript());
   System.out.println("localeJapaneseScriptBlank="+
       ja.getScript().isEmpty());
   System.out.println("characterAScript="+
       Character.UnicodeScript.of('A'));
   System.out.println("characterCyrillicScript="+
       Character.UnicodeScript.of(0x0416));
   System.out.println(
       "localeScriptIsMetadataNotDetection=true");
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ScriptVsLocaleDemo.java
java ScriptVsLocaleDemo
```

**Stdout đã kiểm thử:**

```text
localeEnglishScript=Latn
localeSerbianScript=Cyrl
localeJapaneseScriptBlank=true
characterAScript=LATIN
characterCyrillicScript=CYRILLIC
localeScriptIsMetadataNotDetection=true
```

**Không được** suy rằng `locale.getScript().isEmpty()` nghĩa script UNKNOWN: nó chỉ nói Locale **không khai báo script subtag**.

## 21. Combining marks và Unicode normalization

Hai String **trông giống** nhau có thể có số code points khác nhau:

- `"\u00E9"` là U+00E9 (precomposed Latin small e with acute).
- `"e\u0301"` là U+0065 + U+0301 (Latin e + combining acute accent).

Chúng thường có hình thức tương tự khi render, nhưng:
- Composed: 1 code point.
- Decomposed: 2 code points.
- U+0065 có `UnicodeScript.LATIN`.
- U+0301 có `UnicodeScript.INHERITED`.
- Java String `equals` không mặc nhiên coi hai chuỗi có canonical equivalence là bằng nhau.

`java.text.Normalizer` cung cấp `NFC`, `NFD`, `NFKC`, `NFKD`. Khi cần canonical equivalence, hãy chọn policy normalize nhất quán ở system boundaries, ví dụ NFC cho nhiều use cases. **Không** chọn compatibility normalization/NFKC cho dữ liệu nhạy cảm một cách tùy tiện: nó có thể thay đổi biểu diễn/ý nghĩa theo các quy tắc rộng hơn.

### 21.1. Script của combining mark không thể đoán chỉ từ visual

Vì combining mark được phân loại `INHERITED`, một kiểm tra "chỉ Latin letters" bằng cách đòi **tất cả** code points đều `LATIN` sẽ từ chối nhiều chuỗi Latin dùng dấu hợp lệ. Ngược lại, tự bỏ qua mọi marks cũng có thể tạo lỗ hổng confusable/spoofing nếu không có policy đầy đủ.

## 22. Chương trình 9 — CombiningNormalizationDemo.java

```java
import java.text.Normalizer;

public final class CombiningNormalizationDemo {
 public static void main(String[] args) {
   String decomposed="e\u0301";
   String composed="\u00E9";

   System.out.println("decomposedCodePoints="+
       decomposed.codePoints().count());
   System.out.println("composedCodePoints="+
       composed.codePoints().count());
   System.out.println("decomposedScripts="+
       decomposed.codePoints()
           .mapToObj(cp->
               Character.UnicodeScript.of(cp).name())
           .toList());
   System.out.println("nfcEqualsComposed="+
       Normalizer.normalize(
           decomposed,Normalizer.Form.NFC)
           .equals(composed));
   System.out.println("nfdEqualsDecomposed="+
       Normalizer.normalize(
           composed,Normalizer.Form.NFD)
           .equals(decomposed));
   System.out.println("markTypeNonSpacing="+
       (Character.getType(0x0301)==
           Character.NON_SPACING_MARK));
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 CombiningNormalizationDemo.java
java CombiningNormalizationDemo
```

**Stdout đã kiểm thử:**

```text
decomposedCodePoints=2
composedCodePoints=1
decomposedScripts=[LATIN, INHERITED]
nfcEqualsComposed=true
nfdEqualsDecomposed=true
markTypeNonSpacing=true
```

Cách đọc chuẩn xác: NFC/NFD mang lại kết quả tương đương cho cặp ví dụ này. Không suy mọi visual confusables đều là canonical equivalents; nhiều ký tự trông giống nhau vẫn **khác code points, scripts và normalization result**.

## 23. Code point không đồng nghĩa grapheme cluster

Grapheme cluster cố gắng mô tả một đơn vị ký tự người dùng thường coi là một khối khi di chuyển cursor, xóa/backspace hoặc hiển thị:

- `e` + U+0301: 2 code points nhưng thường 1 grapheme cluster.
- Emoji có skin-tone modifier/variation selector có thể chứa nhiều code points.
- Emoji ZWJ sequences, regional-indicator flags có thể gồm nhiều code points.
- Text shaping có thể còn liên quan tới ligatures, font và context.

Java 17 `java.util.regex.Pattern` hỗ trợ `\X` cho Unicode extended grapheme cluster matching. Dùng `Matcher` để đếm clusters trong ví dụ, nhưng **Unicode segmentation implementation và phiên bản dữ liệu** có thể thay đổi giữa JDKs. Nếu ứng dụng cần đầy đủ thuật toán Unicode UAX #29 mới nhất, đặc biệt emoji sequences và text editing, hãy kiểm phiên bản JDK/Unicode và cân nhắc thư viện chuyên dụng như ICU4J (khi được phép).

### 23.1. Nhu cầu nào dùng code point, nhu cầu nào dùng grapheme?

| Yêu cầu | Đơn vị |
| --- | --- |
| Đọc UnicodeScript hoặc Character category | Code point |
| Tính số UTF-16 units theo Java indexing | `char` / UTF-16 offset |
| Xử lý mỗi Unicode scalar trong analyzer | Code point + validation |
| Đếm/cắt theo ký tự người dùng nhìn thấy | Grapheme cluster |
| Render, line-break, font fallback | Text layout/shaping engine |
| Byte limit cho network/database | Encoded byte length theo Charset |

Không viết validation “username tối đa 20 ký tự” dựa hoàn toàn `String.length()` mà không làm rõ đơn vị. Cũng không tự khẳng định codePointCount đúng với ý nghĩa "20 chữ người dùng" trong mọi script.

## 24. Chương trình 10 — GraphemeClusterDemo.java

```java
import java.util.regex.*;

public final class GraphemeClusterDemo {
 public static void main(String[] args) {
   String s="e\u0301X";
   Matcher m=Pattern.compile("\\X").matcher(s);
   int graphemes=0;
   while(m.find())graphemes++;

   System.out.println("utf16Units="+s.length());
   System.out.println("codePoints="+
       s.codePoints().count());
   System.out.println("graphemeClusters="+graphemes);
   System.out.println(
       "codePointsNotUserCharacters=true");
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 GraphemeClusterDemo.java
java GraphemeClusterDemo
```

**Stdout đã kiểm thử:**

```text
utf16Units=3
codePoints=3
graphemeClusters=2
codePointsNotUserCharacters=true
```

Dù `s.length()==3` và `codePoints().count()==3`, regex `\X` nhóm `e` + combining acute thành **một** cluster, còn `X` là cluster thứ hai. Điều này không mâu thuẫn với việc U+0301 có script `INHERITED`.

## 25. Mixed-script: một tín hiệu cảnh báo, không phải giải pháp security hoàn chỉnh

Một số chữ **nhìn tương tự nhau** nhưng ở scripts khác:
- Latin `a`: U+0061, `LATIN`.
- Cyrillic small a: U+0430, `CYRILLIC`.

Ví dụ một username/trade name trộn Latin và Cyrillic có thể trông giống từ toàn Latin. Một heuristic đơn giản là duyệt code points và thu thập scripts khác `COMMON`/`INHERITED`/`UNKNOWN`. Nếu có hơn một script, có thể yêu cầu review/tăng mức validation.

Nhưng **giới hạn rất lớn**:
- Nhiều identifier hợp lệ dùng nhiều scripts.
- Có confusables **trong cùng script**.
- `COMMON`/`INHERITED` vẫn có thể tham gia trick với joiners/marks.
- Unicode `Script_Extensions` và `TR39` quy định các mô hình restriction/confusability phức tạp hơn.
- Chỉ kiểm script không phát hiện mọi spoofing, directionality/bidi hay normalization issues.
- Tránh dùng heuristic để kết luận “người dùng độc hại” hoặc tự động loại mọi tên đa script.

Muốn bảo vệ domain names/identifiers thật, áp dụng một **identifier policy** rõ, chuẩn phù hợp (UTS #39, IDNA theo ứng dụng) và thư viện/implementation được kiểm thử, không xem `UnicodeScript.of` là validator hoàn chỉnh.

## 26. Chương trình 11 — MixedScriptPolicyDemo.java

```java
import java.util.*;

public final class MixedScriptPolicyDemo {
 static boolean mixed(String s) {
   Set<Character.UnicodeScript> scripts=
       EnumSet.noneOf(Character.UnicodeScript.class);

   s.codePoints().forEach(cp->{
     Character.UnicodeScript sc=
         Character.UnicodeScript.of(cp);
     if(sc!=Character.UnicodeScript.COMMON
         &&sc!=Character.UnicodeScript.INHERITED
         &&sc!=Character.UnicodeScript.UNKNOWN)
       scripts.add(sc);
   });
   return scripts.size()>1;
 }

 public static void main(String[] args) {
   System.out.println("asciiOnlySingleScript="+
       (!mixed("paypal")));
   System.out.println(
       "lookalikeLatinCyrillicMixed="+
       mixed("p\u0430ypal"));
   System.out.println(
       "mixedNotCompleteSpoofDetection=true");
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 MixedScriptPolicyDemo.java
java MixedScriptPolicyDemo
```

**Stdout đã kiểm thử:**

```text
asciiOnlySingleScript=true
lookalikeLatinCyrillicMixed=true
mixedNotCompleteSpoofDetection=true
```

`"p\u0430ypal"` có Cyrillic U+0430 ở vị trí chữ a đầu tiên. **Kết quả chỉ là tín hiệu** hỗn hợp scripts, không phải verdict về quyền truy cập hay độ an toàn của toàn chuỗi. Ví dụ cố ý dùng `EnumSet` để không phải lưu raw user identifier trong logs.

## 27. Locale-sensitive case mapping có thể đổi số code points

Việc viết hoa/thường không luôn one-to-one:
- Một ký tự có thể tạo hai code points sau full case mapping.
- Kết quả có thể phụ thuộc `Locale`.
- `Character.toLowerCase(int)` là simple code point mapping, không thay thế đầy đủ `String.toLowerCase(Locale)` trong mọi trường hợp.

Ví dụ U+0130 (LATIN CAPITAL LETTER I WITH DOT ABOVE):
- `toLowerCase(Locale.ROOT)` có thể tạo `i` + U+0307.
- `toLowerCase(Locale.forLanguageTag("tr-TR"))` tạo `i`.

### 27.1. Tại sao liên quan script?

Sau case mapping, số code points/marks có thể thay đổi. Nếu chỉ phân tích script trước/ sau theo một quy tắc thiếu normalization/context, kết quả validation/search có thể lệch. Cần chọn thứ tự xử lý Unicode và locale-sensitive case mapping nhất quán.

## 28. Chương trình 12 — LocaleCaseMappingDemo.java

```java
import java.util.Locale;

public final class LocaleCaseMappingDemo {
 public static void main(String[] args) {
   String upperDottedI="\u0130";
   String root=upperDottedI.toLowerCase(
       Locale.ROOT);
   String turkish=upperDottedI.toLowerCase(
       Locale.forLanguageTag("tr-TR"));

   System.out.println("sourceCodePoints="+
       upperDottedI.codePoints().count());
   System.out.println("rootLowerCodePoints="+
       root.codePoints().count());
   System.out.println("turkishLowerCodePoints="+
       turkish.codePoints().count());
   System.out.println("rootHasCombiningDot="+
       root.codePoints().anyMatch(cp->cp==0x0307));
   System.out.println("turkishIsAsciiI="+
       turkish.equals("i"));
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 LocaleCaseMappingDemo.java
java LocaleCaseMappingDemo
```

**Stdout đã kiểm thử:**

```text
sourceCodePoints=1
rootLowerCodePoints=2
turkishLowerCodePoints=1
rootHasCombiningDot=true
turkishIsAsciiI=true
```

Ví dụ chỉ minh họa sự khác biệt theo locale, **không** kết luận toàn bộ Unicode case folding có thể thực hiện đúng bằng một call `toLowerCase`. Các use cases so khớp không phân biệt hoa/thường cho security/identifiers cần policy chặt chẽ hơn.

## 29. UnicodeScript khác UnicodeBlock

`Character.UnicodeBlock.of(cp)` nói code point thuộc **khối vị trí mã Unicode** nào, ví dụ `BASIC_LATIN`, `COMBINING_DIACRITICAL_MARKS`, `EMOTICONS`.

`Character.UnicodeScript.of(cp)` nói **hệ chữ viết** theo Script property. Đây là hai thuộc tính khác nhau:

```text
U+0041:
    UnicodeBlock = BASIC_LATIN
    UnicodeScript = LATIN

U+0301:
    UnicodeBlock = COMBINING_DIACRITICAL_MARKS
    UnicodeScript = INHERITED

U+1F600:
    UnicodeBlock = EMOTICONS
    UnicodeScript = COMMON
```

**Không** dùng `UnicodeBlock` như thay thế trực tiếp `UnicodeScript` để phân loại language/script. Một block có thể liên quan tới multiple scripts, và script có thể được phân bố trên nhiều blocks.

## 30. Chương trình 13 — BlockVsScriptDemo.java

```java
public final class BlockVsScriptDemo {
 public static void main(String[] args) {
   System.out.println("latinBlock="+
       Character.UnicodeBlock.of('A'));
   System.out.println("latinScript="+
       Character.UnicodeScript.of('A'));
   System.out.println("combiningBlock="+
       Character.UnicodeBlock.of(0x0301));
   System.out.println("combiningScript="+
       Character.UnicodeScript.of(0x0301));
   System.out.println("emojiBlock="+
       Character.UnicodeBlock.of(0x1F600));
   System.out.println("emojiScript="+
       Character.UnicodeScript.of(0x1F600));
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 BlockVsScriptDemo.java
java BlockVsScriptDemo
```

**Stdout đã kiểm thử:**

```text
latinBlock=BASIC_LATIN
latinScript=LATIN
combiningBlock=COMBINING_DIACRITICAL_MARKS
combiningScript=INHERITED
emojiBlock=EMOTICONS
emojiScript=COMMON
```

## 31. UNKNOWN và code point ngoài miền hợp lệ

`UnicodeScript.of(cp)` yêu cầu `cp` trong phạm vi code point U+0000..U+10FFFF. Nếu `cp` âm hoặc lớn hơn U+10FFFF, method ném `IllegalArgumentException`.

Một code point **unassigned** như U+0378 trong dữ liệu Unicode mà Java 17 dùng có `Character.getType(cp)==Character.UNASSIGNED` và `UnicodeScript.of(cp)==UNKNOWN`.

Cẩn thận:
- `UNKNOWN` khác `IllegalArgumentException`.
- Một code point hợp lệ về **giá trị số** chưa chắc đã được Unicode gán ký tự.
- Vùng surrogate U+D800..U+DFFF nằm trong code point range nhưng không phải Unicode scalar values.
- Không kết luận text “bị lỗi” chỉ vì có UNKNOWN, đặc biệt với các JDK hỗ trợ Unicode versions khác nhau; cần policy cụ thể.

## 32. Chương trình 14 — UnknownScriptDemo.java

```java
public final class UnknownScriptDemo {
 public static void main(String[] args) {
   int unassigned=0x0378;

   System.out.println("unassignedCharacter="+
       (Character.getType(unassigned)==
           Character.UNASSIGNED));
   System.out.println("unassignedScript="+
       Character.UnicodeScript.of(unassigned));

   boolean negativeRejected=false;
   boolean tooLargeRejected=false;
   try {
     Character.UnicodeScript.of(-1);
   }catch(IllegalArgumentException e){
     negativeRejected=true;
   }
   try {
     Character.UnicodeScript.of(0x110000);
   }catch(IllegalArgumentException e){
     tooLargeRejected=true;
   }

   System.out.println("negativeRejected="+
       negativeRejected);
   System.out.println("tooLargeRejected="+
       tooLargeRejected);
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 UnknownScriptDemo.java
java UnknownScriptDemo
```

**Stdout đã kiểm thử:**

```text
unassignedCharacter=true
unassignedScript=UNKNOWN
negativeRejected=true
tooLargeRejected=true
```

Đừng dùng `Character.UnicodeScript.of` với giá trị integer chưa kiểm phạm vi khi dữ liệu bên ngoài có thể chứa số tùy ý. Với text từ `String.codePoints()`, values nằm trong phạm vi nhưng có thể còn unpaired surrogates như đã giải thích.

## 33. Thống kê số code points theo script

Khi cần tìm phân bố scripts trong văn bản, có thể dùng `String.codePoints()` cộng `EnumMap<UnicodeScript,Integer>`:

```text
"Hi "  -> Latin 2, Common 1
U+0416 -> Cyrillic 1
U+6F22 -> Han 1
U+1F600 -> Common 1

Total 6 code points
LATIN 2, CYRILLIC 1, HAN 1, COMMON 2
```

Một map thống kê cho phép báo cáo hoặc policy checks, nhưng **không tự phát hiện ngôn ngữ hoặc độ an toàn của identifier**. Unicode scripts có thể chia sẻ marks/punctuation, và một token nhiều scripts có thể là hợp lệ.

## 34. Chương trình 15 — ScriptCountsDemo.java

```java
import java.util.*;

public final class ScriptCountsDemo {
 public static void main(String[] args) {
   String s="Hi \u0416\u6F22\uD83D\uDE00";
   Map<Character.UnicodeScript,Integer> count=
       new EnumMap<>(Character.UnicodeScript.class);

   s.codePoints().forEach(cp->
       count.merge(
           Character.UnicodeScript.of(cp),1,
           Integer::sum));

   System.out.println("codePoints="+
       s.codePoints().count());
   System.out.println("LATIN="+count.getOrDefault(
       Character.UnicodeScript.LATIN,0));
   System.out.println("CYRILLIC="+count.getOrDefault(
       Character.UnicodeScript.CYRILLIC,0));
   System.out.println("HAN="+count.getOrDefault(
       Character.UnicodeScript.HAN,0));
   System.out.println("COMMON="+count.getOrDefault(
       Character.UnicodeScript.COMMON,0));
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ScriptCountsDemo.java
java ScriptCountsDemo
```

**Stdout đã kiểm thử:**

```text
codePoints=6
LATIN=2
CYRILLIC=1
HAN=1
COMMON=2
```

`EnumMap` phù hợp vì keys là enum. Ở production, nếu thống kê texts lớn cần cân nhắc giới hạn input length, memory, lazy streams và privacy; không log raw identifiers chứa thông tin cá nhân.

## 35. Dựng String từ code points an toàn

Khi đã có một `int` scalar value và muốn thêm vào String:

- `Character.toChars(cp)` trả `char[]` gồm 1 hoặc 2 units.
- `StringBuilder.appendCodePoint(cp)` thêm đúng UTF-16 representation.
- `Character.charCount(cp)` cho biết số code units.
- `Character.isSupplementaryCodePoint(cp)` giúp xác định supplementary code point.

**Không** viết `(char)cp` cho U+1F600; nó sẽ cắt bỏ phần high bits. Khi input là một integer external, validate range và **surrogate scalar exclusion** trước khi chèn nếu hệ thống yêu cầu well-formed Unicode text.

## 36. Chương trình 16 — AppendCodePointDemo.java

```java
public final class AppendCodePointDemo {
 public static void main(String[] args) {
   int emoji=0x1F600;
   char[] units=Character.toChars(emoji);
   StringBuilder sb=new StringBuilder();
   sb.appendCodePoint('A').appendCodePoint(emoji);

   System.out.println("emojiUtf16Units="+
       units.length);
   System.out.println("builderLengthUtf16="+
       sb.length());
   System.out.println("builderCodePoints="+
       sb.codePoints().count());
   System.out.println("lastCodePointCorrect="+
       (sb.codePointBefore(sb.length())==emoji));
   System.out.println("isSupplementary="+
       Character.isSupplementaryCodePoint(emoji));
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 AppendCodePointDemo.java
java AppendCodePointDemo
```

**Stdout đã kiểm thử:**

```text
emojiUtf16Units=2
builderLengthUtf16=3
builderCodePoints=2
lastCodePointCorrect=true
isSupplementary=true
```

**Điểm cần nhớ:** StringBuilder có một `char` cho A và hai `char` cho emoji; code point count là hai.

## 37. Regex script properties khi cần lọc văn bản

Java 17 `java.util.regex.Pattern` hỗ trợ các thuộc tính script trong regex như:
- `\p{sc=Latin}` — thuộc Unicode Script Latin.
- `\p{IsHan}` — Unicode script Han.
- `\X` — extended grapheme cluster matching (khác script property).

Lưu ý Java String cần **escape dấu gạch chéo**: regex `\p{sc=Latin}+` viết trong Java source là `"\\p{sc=Latin}+"`.

**Không** coi regex script match là bộ kiểm tra tiếng Anh, tiếng Trung hay detector chống homograph hoàn chỉnh. Nếu policy yêu cầu Unicode Script_Extensions, identifier restriction levels và confusables, `Pattern` script property đơn giản chưa đủ.

## 38. Chương trình 17 — RegexScriptPropertyDemo.java

```java
import java.util.regex.Pattern;

public final class RegexScriptPropertyDemo {
 public static void main(String[] args) {
   Pattern latin=Pattern.compile(
       "\\p{sc=Latin}+");
   Pattern han=Pattern.compile(
       "\\p{IsHan}+");

   System.out.println("latinWord="+
       latin.matcher("Java").matches());
   System.out.println("latinRejectsCyrillic="+
       (!latin.matcher("\u0416").matches()));
   System.out.println("hanCharacter="+
       han.matcher("\u6F22").matches());
   System.out.println(
       "regexScriptIsNotLanguage=true");
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 RegexScriptPropertyDemo.java
java RegexScriptPropertyDemo
```

**Stdout đã kiểm thử:**

```text
latinWord=true
latinRejectsCyrillic=true
hanCharacter=true
regexScriptIsNotLanguage=true
```

Regex `\p{sc=Latin}+` match toàn bộ chuỗi `Java` nhưng không match ký tự Cyrillic U+0416; `\p{IsHan}+` match một code point Han. Pattern matches chạy toàn chuỗi theo `Matcher.matches()`.

## 39. Sai lầm khi phân loại script bằng charAt

Với chuỗi chỉ chứa supplementary emoji U+1F600:
- `length() == 2`.
- `charAt(0)` là high surrogate, `charAt(1)` là low surrogate.
- `UnicodeScript.of(s.charAt(0))` nhìn giá trị 16-bit surrogate, có thể trả `UNKNOWN`.
- `UnicodeScript.of(s.codePointAt(0))` nhìn đúng U+1F600 và trả `COMMON`.

Như vậy **lặp char rồi gọi UnicodeScript.of(char)** có thể tạo báo cáo giả “UNKNOWN script” cho emoji, trong khi code point hợp lệ là COMMON.

## 40. Chương trình 18 — CharLoopPitfallDemo.java

```java
public final class CharLoopPitfallDemo {
 public static void main(String[] args) {
   String s="\uD83D\uDE00";

   System.out.println("charLoopIterations="+
       s.length());
   System.out.println("codePointLoopIterations="+
       s.codePoints().count());
   System.out.println("firstCharIsHighSurrogate="+
       Character.isHighSurrogate(s.charAt(0)));
   System.out.println("secondCharIsLowSurrogate="+
       Character.isLowSurrogate(s.charAt(1)));
   System.out.println("wholeCodePointScript="+
       Character.UnicodeScript.of(
           s.codePointAt(0)));
   System.out.println("firstCharScript="+
       Character.UnicodeScript.of(
           s.charAt(0)));
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 CharLoopPitfallDemo.java
java CharLoopPitfallDemo
```

**Stdout đã kiểm thử:**

```text
charLoopIterations=2
codePointLoopIterations=1
firstCharIsHighSurrogate=true
secondCharIsLowSurrogate=true
wholeCodePointScript=COMMON
firstCharScript=UNKNOWN
```

Đây là lỗi cốt lõi cần tránh trong đề bài: **UnicodeScript phải nhận full code point từ code-point iteration**, không phải arbitrary UTF-16 code unit.

## 41. Quy trình xử lý Unicode string theo mục đích

Trước khi viết code kiểm tra văn bản, trả lời lần lượt:

1. Input bytes được decode bằng Charset nào? Đã xử lý lỗi decoding chưa?
2. `String` có thể chứa unpaired surrogate không? Nếu không được phép, validate.
3. Có cần canonical normalization hay giữ nguyên raw input?
4. Cần phân tích **script của code points** hay **Locale metadata**?
5. `COMMON`/`INHERITED` được xử lý theo policy nào?
6. Có cần Script_Extensions, grapheme boundaries, BiDi hoặc confusables?
7. Kết quả dùng để **thống kê**, **hiển thị**, **search**, hay **security enforcement**?
8. Có cần giữ UTF-16 offsets để highlight/cắt chuỗi?
9. Có rủi ro user-input gây excessive CPU/memory không?
10. Bộ quy tắc Unicode/JDK version có cần đồng nhất giữa services không?

### 41.1. Một pipeline phân tích gợi ý

```text
Input bytes
    |
Decode with explicit Charset, reject/replace malformed per policy
    |
Java String
    |
Validate well-formed UTF-16 if required
    |
Normalize consistently if required (NFC/NFD and policy)
    |
String.codePoints()
    |
Character.UnicodeScript.of(cp), Character.getType(cp)
    |
Apply script-specific analysis or collect statistics
    |
If UI editing/visual length needed: grapheme segmentation separately
```

**Đừng** âm thầm normalize hoặc lowercase trước khi xác định business/storage/security policy. Ví dụ mật khẩu, source code hoặc legal text có thể cần giữ nguyên bytes/characters theo chuẩn riêng.

## 42. UTF-16 offsets, byte offsets và grapheme boundaries

Đây là điểm dễ gây lỗi khi xây editor, search/highlight hoặc API:

| Đơn vị offset | Dùng ở đâu | Cảnh báo |
| --- | --- | --- |
| UTF-16 unit offset | `String.charAt`, `substring`, regex match indices | Có thể nằm giữa surrogate pair |
| Code-point offset | `offsetByCodePoints`, semantic Unicode processing | Có thể nằm giữa grapheme cluster |
| Grapheme-cluster offset | Cursor/backspace/visible character positions | Cần Unicode segmentation |
| Byte offset | Database/network/file byte sequences | Phụ thuộc encoding, không bằng UTF-16 offset |

Một hệ thống có backend Java, frontend JavaScript và service Python cần thỏa thuận **đơn vị offset** trước khi truyền vị trí giữa các hệ thống. Java String và JavaScript String chủ yếu dùng UTF-16 indexing; Python `str` thường indexing theo Unicode code points nhưng vẫn không phải grapheme clusters. Không giả định cùng số “ký tự” giữa các platform.

### 42.1. Search/highlight ví dụ

Nếu dùng một regex `Matcher.start()` trên Java String, index thường là **UTF-16 offsets**. Để tính số code points trước một match:

```java
int codePointsBeforeMatch=
    text.codePointCount(0, matcher.start());
```

Đây là **mảnh minh họa** cần `String text` và `Matcher matcher` đang có match. Không dùng `matcher.start()` như “số ký tự Unicode” nếu văn bản có supplementary code points.

## 43. Unicode data version và khả năng di động

`Character.UnicodeScript` dùng dữ liệu Unicode được tích hợp theo từng JDK version. Một code point mới được Unicode bổ sung sau version mà JDK cũ biết có thể được phân loại khác khi nâng JDK.

Những điều nên làm:
- Chạy tests trên **Java runtime thực tế** dùng ở production.
- Nếu business/security policy phụ thuộc scripts chính xác, định nghĩa version/compatibility và review khi nâng JDK.
- Không hardcode một danh sách “mọi scripts đã tồn tại” từ một bài học cũ.
- `UNKNOWN` trên JDK cũ không có nghĩa code point sẽ vĩnh viễn UNKNOWN.
- `Locale` script subtags, regex Unicode properties và `Character` data có thể dùng các nguồn/phiên bản cập nhật riêng; cần kiểm tiêu chuẩn deployment.
- Nếu cần bộ dữ liệu Unicode cập nhật độc lập với JDK, chọn thư viện chuyên dụng có phiên bản rõ.

Để bảo đảm kết quả giống nhau giữa JVMs, nên **kiểm thử các code points yêu cầu**, thay vì suy code point property từ tên language.

## 44. Performance và quản lý tài nguyên

`String.codePoints()` thuận tiện và thường đủ cho phân tích script. Với cực nhiều văn bản, hiệu năng phụ thuộc:
- Số code points.
- Memory allocations của `Stream`/boxing/lambda capture.
- Normalization và regex complexity.
- Input length và nguồn dữ liệu không tin cậy.
- Việc có cần giữ offsets hay không.
- Unicode property lookups và caching.

Một manual loop `codePointAt(i);i+=charCount(cp)` có thể tiện và ít overhead khi cần offsets; nhưng không tự khẳng định nó nhanh hơn streams trong mọi trường hợp. Benchmark với JMH nếu performance là yêu cầu quan trọng.

### 44.1. CodePointCount và offsets trong chuỗi dài

`codePointCount(begin,end)` có thể cần quét phạm vi để đếm các surrogate pairs. Không gọi lặp đi lặp lại trong loop theo cách tạo thuật toán O(n²) nếu có thể xử lý một lần.

### 44.2. Bộ nhớ và giới hạn đầu vào

Nếu dữ liệu từ người dùng có thể rất dài, hãy giới hạn bytes/codepoints/graphemes theo đúng nghiệp vụ và bảo vệ memory. Không map toàn bộ text thành nhiều boxed `Character` objects khi có thể dùng `IntStream` primitive hoặc loop đơn giản.

## 45. Các lỗi lập trình thường gặp

1. Nghĩ `char` của Java là một Unicode scalar value hoàn chỉnh.
2. Dùng `String.length()` làm số code points.
3. Dùng `s.chars()` để nhận diện script của emoji.
4. Dùng `UnicodeScript.of(s.charAt(i))` trên string có supplementary symbols.
5. Tăng `i++` thay vì `i+=Character.charCount(cp)`.
6. Duyệt ngược bằng từng char mà quên surrogate pair.
7. Dùng `substring(0,n)` với n là số code points.
8. Nghĩ `codePointAt` luôn trả một scalar value ngay cả khi input có lone surrogate.
9. Nghĩ `Character.isValidCodePoint` từ chối surrogate values.
10. Không validate unpaired surrogates khi encoding/storage yêu cầu well-formed text.
11. Cast `int codePoint` sang `char` để lưu emoji.
12. Dùng `UnicodeScript.of` để suy language duy nhất.
13. Từ `UnicodeScript.LATIN` kết luận text tiếng Anh.
14. Từ `UnicodeScript.HAN` kết luận text tiếng Trung.
15. Dùng `Locale.getScript()` như automatic content script detector.
16. Coi Locale không có script subtag là unknown Unicode Script.
17. Dùng `UnicodeBlock` thay `UnicodeScript`.
18. Bỏ qua hoàn toàn `COMMON`/`INHERITED` trong identifier security.
19. Coi mọi mixed-script identifier là độc hại.
20. Tin script detection đầy đủ để ngăn confusables/homograph.
21. Quên Script_Extensions và Unicode TR39 khi có security requirements.
22. Nghĩ combining mark là một grapheme riêng trong mọi trường hợp.
23. Dùng codePointCount làm length theo grapheme cluster.
24. Dùng regex `\X` nhưng không kiểm Unicode version/emoji behavior.
25. Dùng `String.toLowerCase()` không truyền Locale khi xử lý locale-specific data.
26. Giả định case conversion một code point ra một code point.
27. Giả định text nhìn giống nhau luôn có cùng `String.equals`.
28. Chọn NFKC/NFKD tùy tiện khi dữ liệu cần giữ nguyên bản.
29. Dùng UnicodeScript.forName với unvalidated input mà không bắt `IllegalArgumentException`.
30. Dùng `valueOf("Latn")` rồi mong hiểu ISO script alias.
31. Gọi `UnicodeScript.of(-1)` hay ngoài U+10FFFF mà không kiểm lỗi.
32. Dùng `UNKNOWN` làm dấu hiệu duy nhất của malformed input.
33. Dùng code point integer U+D83D như một scalar value hợp lệ.
34. Đánh đồng UTF-8 byte length với Java UTF-16 String length.
35. Dùng regex Matcher.start làm code-point offset trực tiếp.
36. Không quy định đơn vị offset khi frontend/backend trao đổi positions.
37. Không test surrogate pair, combining mark, mixed scripts, lone surrogate.
38. Giả định Unicode property data giống nhau trên mọi JDK.
39. Ghi raw suspicious usernames vào logs mà không redaction policy.
40. Tự triển khai script confusable/security validation bằng một EnumSet đơn giản.
41. Coi script detection là font availability/rendering guarantee.
42. Không giới hạn kích thước input Unicode trước một pipeline tốn kém.
43. Không xử lý null/empty input ở application boundary.
44. Dùng Unicode normalization để thay thế authentication và canonical identifier policy.
45. Tự khẳng định API Java 7 có String.codePoints() dù method được thêm vào Java 8; bài này sử dụng Java 17 hiện hành.

## 46. Bài tập tự kiểm tra kèm đáp án

**1.** `String.length()` đếm gì? **UTF-16 code units**.

**2.** `String.codePoints().count()` đếm gì? **Code points theo cách Java duyệt UTF-16, gồm lone surrogate units nếu có**.

**3.** Emoji U+1F600 cần bao nhiêu `char` trong UTF-16? **2**.

**4.** Emoji U+1F600 là bao nhiêu code points? **1**.

**5.** Một combining mark có thể được phân loại script gì? **INHERITED**.

**6.** ASCII `'A'` có script gì? **LATIN**.

**7.** Cyrillic U+0416 có script gì? **CYRILLIC**.

**8.** Han U+6F22 có script gì? **HAN**.

**9.** Emoji U+1F600 có script gì? **COMMON**.

**10.** UnicodeScript.of('5') cho kết quả? **COMMON**.

**11.** Loop code points tăng index bằng gì? **Character.charCount(cp)**.

**12.** Duyệt ngược dùng method nào? **codePointBefore(index)**.

**13.** `chars()` khác `codePoints()`? **Duyệt UTF-16 units thay vì ghép surrogate pairs**.

**14.** `s.codePointAt(i)` trả kiểu Java gì? **int**.

**15.** `String.offsetByCodePoints(0,n)` trả gì? **UTF-16 index sau n code points, nếu hợp lệ**.

**16.** `substring` nhận UTF-16 hay code-point offsets? **UTF-16**.

**17.** U+D83D đứng một mình có phải Unicode scalar value không? **Không**.

**18.** `Character.isValidCodePoint(0xD83D)` trả? **true, chỉ kiểm numerical range**.

**19.** `String.codePoints()` có ném lỗi vì lone surrogate không? **Không, có thể emit surrogate code unit as int**.

**20.** Cách đơn giản kiểm lone surrogate qua stream? **Reject values trong U+D800..U+DFFF**.

**21.** `UnicodeScript.forName("Latn")` trả? **LATIN**.

**22.** `UnicodeScript.forName("Hani")` trả? **HAN**.

**23.** Alias không hợp lệ gây exception nào? **IllegalArgumentException**.

**24.** Locale `"en-Latn-US"` có `getScript`? **Latn**.

**25.** Locale không có explicit script subtag có script property Unknown không? **Không; nó chỉ thiếu metadata**.

**26.** `UnicodeScript.of` có xác định ngôn ngữ tự nhiên không? **Không**.

**27.** `UnicodeBlock` và `UnicodeScript` có giống nhau? **Không**.

**28.** `e\u0301` có bao nhiêu code points? **2**.

**29.** `\u00E9` có bao nhiêu code points? **1**.

**30.** NFC của `e\u0301` có thể trùng `\u00E9` không? **Có, theo ví dụ kiểm thử**.

**31.** Một grapheme cluster có thể gồm nhiều code points không? **Có**.

**32.** Java regex `\X` dùng làm gì? **Match một extended grapheme cluster**.

**33.** Mixed-script detector có bắt được mọi spoofing không? **Không**.

**34.** Nhận diện script không cần Script_Extensions cho mọi use case? **Đúng với thống kê đơn giản; không đủ cho các chính sách phức tạp**.

**35.** `toLowerCase(Locale.ROOT)` luôn giữ nguyên số code points? **Không**.

**36.** Script `INHERITED` thường xuất hiện ở đâu? **Combining marks và một số ký tự dùng theo context**.

**37.** `UNKNOWN` có nghĩa code point ngoài miền không? **Không; value nằm trong miền nhưng chưa gán script**.

**38.** `UnicodeScript.of(0x110000)`? **Ném IllegalArgumentException**.

**39.** `StringBuilder.appendCodePoint(0x1F600)` thêm bao nhiêu UTF-16 units? **2**.

**40.** `(char)0x1F600` có tạo một emoji đúng không? **Không, làm mất thông tin**.

**41.** `\p{sc=Latin}` trong Java String literal viết sao? **"\\p{sc=Latin}"**.

**42.** `Matcher.start()` với Java String dùng offset nào? **UTF-16**.

**43.** Có thể dùng script để quyết định font render luôn thành công? **Không**.

**44.** Có thể suy Python/Java/JavaScript indexing luôn cùng đơn vị không? **Không**.

**45.** Để hỗ trợ JDK nâng Unicode version cần gì? **Kiểm thử scripts/code points và policy compatibility**.

**46.** Khi xử lý văn bản Việt Nam có dấu nên chú ý gì? **Combining mark, normalization, code points và grapheme boundaries**.

**47.** Khi làm UI giới hạn “20 ký tự” cần định nghĩa gì? **Đơn vị là UTF-16, code points, graphemes hay bytes**.

**48.** Code-point iteration có tự làm sanitizer bảo mật không? **Không**.

## 47. Checklist cho code review Java 17+

- [ ] Input đã được decode bằng Charset đúng và có lỗi decoding policy.
- [ ] Đã phân biệt `char` vs Unicode code point.
- [ ] Dùng `String.codePoints()` hoặc `codePointAt` với `charCount` đúng.
- [ ] Không tự cắt surrogate pair qua substring với index code-point.
- [ ] Nếu cần UTF-16 offset, dùng `offsetByCodePoints`.
- [ ] Nếu cần duyệt ngược, dùng `codePointBefore`.
- [ ] Bảo đảm các supplementary characters được test.
- [ ] Nếu yêu cầu well-formed Unicode, từ chối lone surrogates.
- [ ] Không chỉ dùng `isValidCodePoint` để validate scalar.
- [ ] Không cast int code point thành char để tạo text.
- [ ] Dùng `UnicodeScript.of(cp)` trên **full code point**.
- [ ] Có cách xử lý `COMMON`, `INHERITED` và `UNKNOWN` đúng với use case.
- [ ] Không đánh đồng Unicode script với Locale script/language.
- [ ] Không dùng UnicodeBlock làm script detector.
- [ ] Không coi mixed-script heuristic là chống spoofing đầy đủ.
- [ ] Nếu security identifier, áp dụng policy TR39/IDNA đúng theo domain.
- [ ] Nhớ Script_Extensions khi language/script policy đòi chính xác hơn.
- [ ] Có normalization policy nhất quán nếu so khớp text tương đương.
- [ ] Case mapping dùng Locale phù hợp và kiểm expansion.
- [ ] Nếu UI needs user-perceived characters, dùng grapheme segmentation.
- [ ] Có tests cho combining marks và ZWJ/emoji nếu ứng dụng có UI.
- [ ] Không mặc định regex \X luôn đồng nhất Unicode version mọi JDK.
- [ ] Không nhầm UTF-16 offsets với bytes/code-points/graphemes.
- [ ] Có tests với invalid UnicodeScript aliases và code point out-of-range.
- [ ] Đã cân nhắc JDK Unicode data version khi nâng runtime.
- [ ] Không in dữ liệu người dùng nhạy cảm vào diagnostics.
- [ ] Đã benchmark trước khi tối ưu stream/loop.
- [ ] Code examples dùng Java SE 17+ API hiện hành, không private internals.

## 48. Tài liệu Java SE 17 và tiêu chuẩn liên quan

- [`Character` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): `codePointAt`, `codePointBefore`, `charCount`, `toChars`, `isValidCodePoint`, `isSupplementaryCodePoint`, Unicode categories.
- [`Character.UnicodeScript` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.UnicodeScript.html): `of(int)`, `forName(String)`, `COMMON`, `INHERITED`, `UNKNOWN`.
- [`Character.UnicodeBlock` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.UnicodeBlock.html): Unicode blocks khác script.
- [`String` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `length`, `charAt`, `codePointAt`, `codePointBefore`, `codePointCount`, `offsetByCodePoints`, `chars`, `codePoints`.
- [`StringBuilder` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html): `appendCodePoint`, code-point methods.
- [`Locale` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): `forLanguageTag`, `getScript`, locale-sensitive text.
- [`Normalizer` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): NFC/NFD/NFKC/NFKD.
- [`Pattern` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html): `\p{sc=...}`, `\p{Is...}`, `\X`.
- [`IntStream` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html): primitive stream từ `String.codePoints`.
- [Unicode Standard Annex #29](https://unicode.org/reports/tr29/): grapheme/word/sentence boundaries.
- [Unicode Technical Standard #39](https://unicode.org/reports/tr39/): identifier security, confusables và mixed scripts.
- [Unicode Standard Annex #15](https://unicode.org/reports/tr15/): Unicode normalization.
- [Unicode Script Property](https://www.unicode.org/reports/tr24/): Script và Script_Extensions.

**Tổng kết:** `Character.UnicodeScript.of(cp)` xác định **script property của một code point**, không phải ngôn ngữ hay font. Trong Java, duyệt text theo **Unicode code points** bằng `String.codePoints()` hoặc `codePointAt + Character.charCount`; không lặp `char` rồi giả định một `char` là một ký tự hoàn chỉnh. Hãy chú ý `COMMON`/`INHERITED`/`UNKNOWN`, surrogate đứng lẻ, normalization và sự khác biệt giữa script, Locale và grapheme cluster. Các API này hiện vẫn dùng tốt trên Java 17+, nhưng không tự cung cấp language detection, text rendering hay chống Unicode spoofing hoàn chỉnh.