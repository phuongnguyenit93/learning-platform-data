# StringBuilder.reverse(): Bảo toàn surrogate pair nhưng không bảo toàn cụm ký tự

## 1. Ý chính cần nhớ

`StringBuilder.reverse()` đảo thứ tự nội dung **ngay trong builder hiện tại** và trả về chính builder đó. Theo hợp đồng Java, phương thức **giữ nguyên thứ tự high surrogate – low surrogate trong một surrogate pair UTF-16 hợp lệ** khi đảo. Nhờ vậy, emoji hay ký tự bổ sung Unicode được biểu diễn bởi một cặp surrogate không tự biến thành hai surrogate sai thứ tự chỉ do `reverse()`.

Nhưng bảo toàn **surrogate pair** hoàn toàn khác với bảo toàn **grapheme cluster** — cụm ký tự người đọc thường cảm nhận như một ký tự. Nhiều grapheme cluster có hai hoặc nhiều Unicode code point, ví dụ chữ có dấu kết hợp, emoji có ký tự nối ZWJ, ký hiệu với variation selector, hay cờ biểu diễn bằng hai regional indicator.

Hai trường hợp quan trọng:

~~~text
"A😀B"  -> reverse() -> "B😀A"
Emoji U+1F600 vẫn gồm đúng high surrogate U+D83D và low surrogate U+DE00.

"a" + U+0301 + "b"
Code point ban đầu: U+0061 U+0301 U+0062
Sau reverse():     U+0062 U+0301 U+0061
Dấu sắc có thể gắn sang chữ b thay vì chữ a.
~~~

**Kết luận:** `reverse()` thích hợp khi muốn dùng **hợp đồng đảo UTF-16 của Java**; không tự động thích hợp khi bài toán yêu cầu đảo theo **ký tự hiển thị** và giữ nguyên emoji phức tạp hay tổ hợp dấu.

## 2. UTF-16 code unit, Unicode code point và grapheme cluster

Trước khi đọc mã nguồn, hãy tách rõ ba đơn vị:

| Đơn vị | Định nghĩa | Java API điển hình |
| --- | --- | --- |
| UTF-16 code unit | Một đơn vị rộng 16 bit, chính là `char` của Java | `length()`, `charAt(i)` |
| Unicode code point | Một giá trị Unicode, ví dụ `U+0041` hoặc `U+1F600` | `codePointAt(i)`, `codePoints()`, `appendCodePoint(cp)` |
| Extended grapheme cluster | Một nhóm code point được các quy tắc Unicode nhận diện như một đơn vị ký tự trong văn bản | Cần thuật toán phân đoạn grapheme phù hợp UAX #29 |

Trong UTF-16, Unicode code point thuộc các mặt phẳng bổ sung (`U+10000..U+10FFFF`) cần **hai** code unit:

- High surrogate trong `U+D800..U+DBFF`.
- Low surrogate trong `U+DC00..U+DFFF`.
- Cặp phải có thứ tự **high trước, low sau**.

Ví dụ:

~~~java
int smile = 0x1F600;
char[] pair = Character.toChars(smile);
System.out.printf("U+%04X U+%04X%n", (int) pair[0], (int) pair[1]);
// U+D83D U+DE00
~~~

`StringBuilder("😀").length()` bằng `2` (hai code unit), trong khi `codePointCount(0, length())` bằng `1`. Đây vẫn thường là **một** grapheme cluster.

Một ví dụ khác: chữ `á` có thể là `U+00E1`, hoặc là `U+0061 U+0301` (chữ `a` cộng dấu sắc kết hợp). Cách thứ hai có **hai code point** nhưng vẫn thường hiển thị thành một cụm ký tự. Vì thế đảo theo code point cũng chưa chắc là đảo theo grapheme cluster.

## 3. Hợp đồng chính xác của StringBuilder.reverse()

Chữ ký:

~~~java
public StringBuilder reverse()
~~~

Phương thức thay nội dung hiện tại bằng dãy đảo và **trả về `this`**, do đó có thể nối lời gọi:

~~~java
StringBuilder sb = new StringBuilder("abc");
StringBuilder returned = sb.reverse();

System.out.println(sb);             // cba
System.out.println(returned == sb); // true
~~~

`returned == sb` là phép so sánh **identity của hai tham chiếu builder**, dùng ở đây để cho thấy `reverse()` không trả một builder mới.

Các bảo đảm và giới hạn:

1. **Surrogate pair hợp lệ được coi như một đơn vị khi đảo**. Thứ tự high–low trong mỗi pair được giữ đúng.
2. Những code unit không thuộc pair hợp lệ được đảo theo cơ chế của phương thức.
3. Phương thức không phân đoạn **extended grapheme cluster** theo UAX #29.
4. Những surrogate **lẻ** đứng riêng có thể **hình thành một pair hợp lệ** sau khi đảo nếu trước đó chúng nằm theo thứ tự low–high. Đây là hành vi được đặc tả, không phải một bước sửa dữ liệu Unicode tổng quát.
5. Dãy `String` lấy bằng `toString()` trước khi sửa builder giữ nguyên nội dung vì `String` bất biến.

Điều quan trọng là **hợp đồng kết quả**, không phải giả định về thuật toán nội bộ hay backing array của một bản OpenJDK cụ thể.

### Ví dụ đơn giản

~~~java
StringBuilder sb = new StringBuilder("A");
sb.appendCodePoint(0x1F600).append('B');

String original = sb.toString();
sb.reverse();

System.out.printf("U+%X%n", sb.codePointAt(1)); // U+1F600
System.out.println(original.codePointCount(0, original.length())); // 3
~~~

Sau `reverse()`, builder biểu diễn `B`, emoji `U+1F600`, `A`. Nếu nhìn ở mức UTF-16 code unit:

~~~text
Trước: [0041] [D83D] [DE00] [0042]
                high    low
Sau:   [0042] [D83D] [DE00] [0041]
                high    low
~~~

Cặp surrogate của emoji **không trở thành** `[DE00][D83D]`. Nếu tự viết vòng lặp đảo từng `char`, bạn có nguy cơ tạo ra thứ tự low–high sai đó.

## 4. Dấu kết hợp: ví dụ rõ nhất của grapheme bị tách

Xét dãy Unicode:

~~~text
U+0061 U+0301 U+0062
    a   dấu sắc   b
~~~

Bộ dựng chữ thường hiển thị `a + U+0301` thành một chữ `á` có dấu. Nhưng `StringBuilder.reverse()` chỉ giữ quy tắc surrogate, không có hợp đồng giữ chữ và dấu kết hợp thành một cluster:

~~~java
String input = "a\u0301b";
String reversed = new StringBuilder(input).reverse().toString();
~~~

`input` là dãy code point `U+0061 U+0301 U+0062`; `reversed` là `U+0062 U+0301 U+0061`. Dấu sắc đã chuyển sang ngay sau `b`, nên cách hiển thị có thể thành `b́a`.

Nếu mục tiêu là **đảo hai grapheme cluster** `[a + dấu sắc]` và `[b]`, thứ tự mong muốn sẽ là:

~~~text
[b] [a + U+0301]
Code point: U+0062 U+0061 U+0301
~~~

Khác biệt này cho thấy việc đảo **code point** riêng lẻ cũng chưa đủ; cần biết **ranh giới cluster** để giữ nguyên cấu trúc bên trong từng cluster.

### Chuẩn hóa NFC có giải quyết không?

`java.text.Normalizer` với `NFC` có thể kết hợp `a + dấu sắc` thành một code point dựng sẵn `U+00E1`. Nhờ vậy **riêng ví dụ này** có thể trở nên dễ đảo hơn. Tuy nhiên NFC không biến mọi emoji ZWJ, variation selector hay cluster khác thành một code point. **Normalization** và **grapheme segmentation** là hai bài toán riêng; NFC không biến `reverse()` thành thuật toán đảo cluster đúng cho mọi Unicode text.

## 5. Emoji nối bằng ZWJ: surrogate không hỏng, emoji vẫn có thể thay đổi

Emoji **woman technologist** có thể được mã hóa thành dãy:

~~~text
U+1F469  WOMAN
U+200D   ZERO WIDTH JOINER (ZWJ)
U+1F4BB  PERSONAL COMPUTER
~~~

Hai code point hai đầu là supplementary, nên từng code point được lưu bằng **surrogate pair**. Trên nền tảng hỗ trợ, ba code point có thể hiển thị như một emoji kết hợp.

~~~java
String womanTechnologist = new StringBuilder()
        .appendCodePoint(0x1F469)
        .appendCodePoint(0x200D)
        .appendCodePoint(0x1F4BB)
        .toString();

String reversed = new StringBuilder(womanTechnologist)
        .reverse()
        .toString();
~~~

Sau đảo, dãy là:

~~~text
U+1F4BB U+200D U+1F469
~~~

Các surrogate pair bên trong U+1F469 và U+1F4BB vẫn hợp lệ, nhưng **thứ tự các thành phần của cụm emoji bị thay đổi**. Màn hình có thể hiển thị cụm khác hoặc hiển thị tách rời, phụ thuộc bộ dựng chữ và font. `reverse()` **không** coi toàn bộ cụm emoji ZWJ là một phần tử cần giữ nguyên.

## 6. Variation selector và cờ

**Variation selector:** Cụm `U+2764 U+FE0F` chứa ký hiệu trái tim cùng VARIATION SELECTOR-16. Sau đảo:

~~~text
Trước: U+2764 U+FE0F
Sau:   U+FE0F U+2764
~~~

Selector đứng trước base, thay vì theo sau, nên dạng hiển thị có thể thay đổi. `U+FE0F` không phải surrogate pair và không được giữ kèm base bởi hợp đồng `reverse()`.

**Cờ bằng regional indicators:** Ví dụ cờ Việt Nam có hai code point theo thứ tự:

~~~text
Trước: U+1F1FB U+1F1F3
Sau:   U+1F1F3 U+1F1FB
~~~

Mỗi regional indicator supplementary vẫn được mã hóa UTF-16 đúng, nhưng cặp **không còn cùng thứ tự**. Do vậy ý nghĩa biểu tượng và cách hiển thị không được bảo toàn.

Các hiện tượng tương tự có thể liên quan đến emoji modifier, dấu kết hợp đa tầng hoặc cấu trúc chữ của một số hệ viết. Bộ kiểm thử chỉ dùng ASCII hoặc một emoji đơn code point thường không bắt được lỗi ở mức cluster.

## 7. Surrogate lẻ: trường hợp đặc biệt phải hiểu

Java `String` và `StringBuilder` có thể chứa một `char` surrogate đứng riêng. Ví dụ chuỗi cố ý chứa hai code unit theo thứ tự **low trước, high sau**:

~~~java
char low = '\uDE00';
char high = '\uD83D';
String malformed = new String(new char[] {low, high});

String after = new StringBuilder(malformed).reverse().toString();
~~~

Trước đảo:

~~~text
U+DE00 U+D83D  // low rồi high: không tạo một pair hợp lệ
~~~

Sau đảo:

~~~text
U+D83D U+DE00  // high rồi low: pair hợp lệ, code point U+1F600
~~~

Điều này chứng minh một chi tiết thú vị: `reverse()` có thể biến hai surrogate trước đó **không ghép cặp** thành **một pair hợp lệ**. Phép đảo không được đảm bảo là một phép hoán vị giữ nguyên mọi phân nhóm code point trên dữ liệu UTF-16 hỏng.

Hệ quả là không nên khẳng định gọi `reverse()` **hai lần** luôn khôi phục chính xác dãy code unit ban đầu trong mọi dữ liệu có surrogate lẻ. Khi pair đã hình thành ở lượt đảo đầu, lượt đảo thứ hai có thể giữ cặp đó theo quy tắc bảo toàn surrogate pair, chứ không khôi phục cấu trúc sai cũ.

Nếu dữ liệu phải tuân thủ Unicode scalar values, hãy kiểm tra/loại/thay surrogate lẻ bằng chính sách rõ ràng. `reverse()` không phải API sửa chữa UTF-16 bị hỏng.

## 8. Chương trình Java 17+ đầy đủ và kết quả đã kiểm chứng

Chương trình dưới đây in code point và code unit dạng `U+XXXX` để kiểm tra khách quan, không phụ thuộc vào font hoặc khả năng console hiển thị emoji.

Lưu tệp **`ReverseUnicodeDemo.java`**:

~~~java
import java.util.stream.Collectors;

public class ReverseUnicodeDemo {
    private static String cps(String s) {
        return s.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    private static String units(String s) {
        StringBuilder result = new StringBuilder();
        for (int i = 0; i < s.length(); i++) {
            if (i > 0) result.append(' ');
            result.append(String.format("U+%04X", (int) s.charAt(i)));
        }
        return result.toString();
    }

    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("A")
                .appendCodePoint(0x1F600)
                .append('B');
        String original = builder.toString();
        StringBuilder returned = builder.reverse();
        System.out.println("sameBuilder=" + (returned == builder));
        System.out.println("original=" + cps(original));
        System.out.println("reversed=" + cps(builder.toString()));
        System.out.println("reversedUnits=" + units(builder.toString()));
        System.out.println("originalStill=" + cps(original));

        String accent = "a\u0301b";
        System.out.println("accentBefore=" + cps(accent));
        System.out.println("accentAfter=" + cps(new StringBuilder(accent).reverse().toString()));

        String womanTechnologist = new StringBuilder()
                .appendCodePoint(0x1F469)
                .appendCodePoint(0x200D)
                .appendCodePoint(0x1F4BB).toString();
        System.out.println("zwjBefore=" + cps(womanTechnologist));
        System.out.println("zwjAfter=" + cps(new StringBuilder(womanTechnologist).reverse().toString()));

        String heart = "\u2764\uFE0F";
        System.out.println("heartAfter=" + cps(new StringBuilder(heart).reverse().toString()));

        String flag = new StringBuilder()
                .appendCodePoint(0x1F1FB)
                .appendCodePoint(0x1F1F3).toString();
        System.out.println("flagBefore=" + cps(flag));
        System.out.println("flagAfter=" + cps(new StringBuilder(flag).reverse().toString()));

        String malformed = new String(new char[]{'\uDE00', '\uD83D'});
        System.out.println("malformedUnits=" + units(malformed));
        System.out.println("malformedReversed=" + cps(
                new StringBuilder(malformed).reverse().toString()));
    }
}
~~~

Lệnh biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 ReverseUnicodeDemo.java
java ReverseUnicodeDemo
~~~

`stdout` đã xác nhận trực tiếp bằng trình biên dịch/JVM:

~~~text
sameBuilder=true
original=U+0041 U+1F600 U+0042
reversed=U+0042 U+1F600 U+0041
reversedUnits=U+0042 U+D83D U+DE00 U+0041
originalStill=U+0041 U+1F600 U+0042
accentBefore=U+0061 U+0301 U+0062
accentAfter=U+0062 U+0301 U+0061
zwjBefore=U+1F469 U+200D U+1F4BB
zwjAfter=U+1F4BB U+200D U+1F469
heartAfter=U+FE0F U+2764
flagBefore=U+1F1FB U+1F1F3
flagAfter=U+1F1F3 U+1F1FB
malformedUnits=U+DE00 U+D83D
malformedReversed=U+1F600
~~~

**Đọc kết quả:**

- `sameBuilder=true`: `reverse` sửa tại chỗ và trả `this`.
- `reversedUnits`: surrogate pair của emoji vẫn là `D83D DE00`, không đảo thành `DE00 D83D`.
- `originalStill`: biến `String` đã tạo trước đó vẫn giữ nội dung ban đầu.
- `accentAfter`: dấu kết hợp đã chuyển vị trí giữa các chữ.
- `zwjAfter`: thứ tự trong emoji ZWJ sequence bị đảo.
- `heartAfter` và `flagAfter`: variation selector và regional indicators bị đảo thứ tự.
- `malformedReversed`: hai surrogate lẻ đã trở thành một supplementary code point hợp lệ.

Như vậy, kiểm tra đầy đủ cần xem **code point** và đôi khi cả **UTF-16 code unit**, không chỉ so sánh ảnh hiển thị.

## 9. Tự đảo theo code point có giải quyết được không?

Một giải pháp tốt hơn **đảo `char` ngây thơ** khi muốn xử lý Unicode code point là đọc `String.codePoints()` rồi `appendCodePoint()` ngược thứ tự:

~~~java
static String reverseCodePoints(String input) {
    int[] points = input.codePoints().toArray();
    StringBuilder result = new StringBuilder(input.length());

    for (int i = points.length - 1; i >= 0; i--) {
        result.appendCodePoint(points[i]);
    }
    return result.toString();
}
~~~

Đây là một **phương thức minh họa** cần đặt trong một class Java; đầu vào giả định không null.

Nó giữ nguyên từng supplementary code point hợp lệ, nhưng vẫn **đảo riêng** dấu kết hợp, ZWJ, variation selector và từng regional indicator. `reverseCodePoints` **không** là thuật toán đảo theo grapheme cluster.

Với dữ liệu UTF-16 không hợp lệ, `String.codePoints()` cũng có thể trả surrogate lẻ như một giá trị `int` riêng; `appendCodePoint` không tự áp dụng chính sách loại bỏ toàn bộ surrogate lẻ. Nếu cần Unicode scalar values chuẩn, xác thực đầu vào riêng.

Với yêu cầu đơn giản không cần grapheme-aware, hãy dùng `new StringBuilder(input).reverse().toString()` thay vì tự viết logic đảo `charAt` dễ làm hỏng surrogate.

## 10. Muốn đảo theo cụm ký tự phải làm gì?

Nếu đặc tả yêu cầu đảo **các ký tự theo cách người đọc nhận thức**, phải **phân đoạn extended grapheme cluster trước, đảo thứ tự các cluster sau**, và **không thay thứ tự các code point bên trong cluster**.

Ví dụ logic:

~~~text
Input:
[a U+0301] [b] [woman U+200D laptop]

Grapheme segmentation:
cluster 1 = a + dấu sắc
cluster 2 = b
cluster 3 = emoji woman-ZWJ-laptop

Reverse cluster order:
[woman U+200D laptop] [b] [a U+0301]
~~~

Ở mức thiết kế, thuật toán gồm:

1. Chọn một bộ phân đoạn grapheme phù hợp phiên bản Unicode và ngôn ngữ/dữ liệu thực tế.
2. Lấy các khoảng `[start,end)` theo **chỉ số UTF-16** hoặc các chuỗi con đại diện cho từng cluster.
3. Đảo **thứ tự các khoảng**, giữ nguyên dãy code unit trong mỗi khoảng.
4. Ghép các khoảng bằng `StringBuilder.append` rồi trả `toString()`.
5. Kiểm thử với chữ+dấu, emoji ZWJ, flags, variation selector và dữ liệu đa ngôn ngữ.

Trong Java, `java.text.BreakIterator.getCharacterInstance(...)` có chức năng xác định ranh giới ký tự, nhưng khả năng hỗ trợ **extended grapheme clusters phức tạp**, nhất là emoji và quy tắc Unicode mới, cần được xác minh theo **phiên bản JDK**. Với yêu cầu tuân thủ UAX #29 nghiêm ngặt, có thể cân nhắc công cụ phân đoạn Unicode chuyên dụng như ICU4J theo phiên bản phù hợp; không giả định mọi công cụ “character boundary” đều xử lý mọi emoji như nhau.

**Quan trọng:** đảo theo grapheme cluster cũng chưa chắc tương đương *đảo hình ảnh trên màn hình*. Văn bản có hướng RTL/LTR, thuật toán hai chiều Unicode (bidi) và contextual shaping cần sự hỗ trợ của hệ thống dàn chữ. Để hiển thị văn bản theo hướng đọc thích hợp, thường nên điều chỉnh layout/text direction, không phải `reverse()` chuỗi logic.

## 11. Những lỗi thường gặp

1. **Nghĩ `char` là ký tự Unicode hoàn chỉnh.** Một supplementary code point có hai `char`.
2. **Viết vòng lặp đảo từng `charAt` từ cuối đến đầu.** Có thể tách surrogate pair hợp lệ thành thứ tự low–high sai.
3. **Cho rằng bảo toàn surrogate pair là giữ mọi emoji.** Nhiều emoji gồm nhiều code point.
4. **Cho rằng `reverse()` giữ nguyên dấu kết hợp.** `a + U+0301` có thể thành dấu phía sau chữ khác.
5. **Cho rằng `String.codePoints()` là grapheme segmentation.** Một cluster có thể gồm nhiều code point.
6. **Cho rằng NFC khiến mọi cụm ký tự thành một code point.** Nhiều emoji ZWJ/variation selector vẫn nhiều code point.
7. **Đoán kết quả bằng mắt trên console.** Font và rendering có thể khác nhau; nên in `U+XXXX` khi QA.
8. **Bỏ qua surrogate lẻ.** `reverse()` có thể tạo cặp mới từ đầu vào sai cấu trúc; không bảo đảm đảo hai lần trả nguyên dãy sai ban đầu.
9. **Cho rằng `reverse()` tạo builder mới.** Nó sửa chính builder nhận lời gọi; chụp `String` trước khi sửa nếu cần giá trị gốc.
10. **Dùng `reverse()` để sửa hướng hiển thị RTL.** Logical order, bidi và grapheme order là các khái niệm khác nhau.
11. **Bỏ qua việc đánh giá bộ phân đoạn theo JDK.** Tài liệu/triển khai Unicode thay đổi theo phiên bản; cần test thực tế với dữ liệu của ứng dụng.

## 12. Bài tập tự kiểm tra

**Câu 1.** `reverse()` có làm surrogate pair của `U+1F600` thành low–high không?

**Đáp án:** không. Pair hợp lệ vẫn giữ high–low.

**Câu 2.** Dãy `U+0061 U+0301 U+0062` thành gì sau `reverse()`?

**Đáp án:** `U+0062 U+0301 U+0061`; dấu sắc thay đổi vị trí so với chữ `a`.

**Câu 3.** `U+1F469 U+200D U+1F4BB` sau `reverse()` có được bảo đảm vẫn là cùng một emoji hợp nhất không?

**Đáp án:** không. Kết quả đảo thứ tự thành `U+1F4BB U+200D U+1F469`.

**Câu 4.** Vì sao đảo ngược theo code point vẫn không đủ để đảo theo “ký tự nhìn thấy”?

**Đáp án:** một grapheme cluster có thể chứa nhiều code point. Đảo từng code point phá cấu trúc cụm.

**Câu 5.** Có nên dùng `new StringBuilder(text).reverse().toString()` cho ứng dụng cần giữ nguyên dấu tiếng Việt kết hợp và emoji phức tạp?

**Đáp án:** không thể mặc định. Phải phân đoạn và đảo theo grapheme cluster theo yêu cầu ứng dụng.

**Câu 6.** Dữ liệu low surrogate rồi high surrogate có thể trở thành gì sau reverse?

**Đáp án:** một pair high–low hợp lệ; do đó không được xem reverse là phép biến đổi luôn có thể đảo ngược trên dữ liệu UTF-16 sai.

**Câu 7.** Nếu cần đổi hướng hiển thị một đoạn tiếng Ả Rập, có nên đảo nội dung `String` không?

**Đáp án:** thông thường không. Dùng cơ chế bố trí/Unicode bidi đúng thay vì sửa logical order bằng `reverse()`.

## 13. Nguồn tham khảo chuẩn

- [Java SE 17 — StringBuilder.reverse()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html#reverse()): hợp đồng đảo, bảo toàn surrogate pair và khả năng tạo pair từ hai surrogate lẻ.
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): UTF-16, high/low surrogate, `toChars`, `charCount` và code point.
- [Java SE 17 — String.codePoints()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#codePoints()): cách đọc dãy code point và các trường hợp surrogate lẻ.
- [Unicode Standard Annex #29 — Unicode Text Segmentation](https://www.unicode.org/reports/tr29/): quy tắc phân đoạn extended grapheme cluster.
- [Unicode Technical Standard #51 — Unicode Emoji](https://www.unicode.org/reports/tr51/): emoji ZWJ sequences, variation selector, emoji modifier và regional indicator.

**Ghi nhớ:** `StringBuilder.reverse()` giữ đúng cấu trúc **surrogate pair UTF-16 hợp lệ**, nhưng không biết ranh giới **grapheme cluster**. Muốn đảo “ký tự người dùng nhìn thấy”, hãy phân đoạn cluster theo quy tắc Unicode phù hợp rồi đảo **nguyên từng cluster**.