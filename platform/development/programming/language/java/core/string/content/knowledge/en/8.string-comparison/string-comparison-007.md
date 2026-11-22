# `String.contentEquals()`: so sánh nội dung với `StringBuilder` và `CharSequence`

## 1. Bài toán và ý tưởng chính

Trong Java, `String` lưu một chuỗi ký tự bất biến (*immutable*). Trong khi đó, `StringBuilder`, `StringBuffer` và nhiều kiểu khác triển khai `CharSequence` có thể cung cấp một dãy ký tự mà không phải là đối tượng `String`. Đôi khi cần hỏi: **“Dãy ký tự hiện tại của đối tượng này có giống chính xác nội dung của một `String` không?”** Đây là trường hợp sử dụng `String.contentEquals(...)`.

Ví dụ, một bộ phân tích dữ liệu đã ghép tên trường vào `StringBuilder`, và cần so với từ khóa `"status"`. Nếu gọi `"status".equals(builder)` thì kết quả là `false`, dù các ký tự trùng nhau, vì `String.equals(Object)` chỉ coi một đối tượng khác là bằng khi đối tượng đó cũng là `String` với cùng nội dung. `"status".contentEquals(builder)` mới kiểm tra trực tiếp dãy ký tự bên trong builder.

~~~java
String expected = "status";
StringBuilder actual = new StringBuilder("status");

System.out.println(expected.equals(actual));        // false
System.out.println(expected.contentEquals(actual)); // true
System.out.println(expected.equals(actual.toString())); // true
~~~

Cả hai cách cuối đều đúng về nội dung. `contentEquals(builder)` tránh việc người gọi phải tạo một `String` trung gian qua `builder.toString()`; hiệu quả thực tế phụ thuộc loại đối tượng, bản JDK, tối ưu của JVM và hoàn cảnh sử dụng.

## 2. Hai overload của `String.contentEquals()`

Lớp `java.lang.String` cung cấp:

~~~java
public boolean contentEquals(StringBuffer sb)
public boolean contentEquals(CharSequence cs)
~~~

Đây là **chữ ký API**, không phải một chương trình Java hoàn chỉnh.

- **`contentEquals(StringBuffer)`:** so nội dung `String` với `StringBuffer`. `StringBuffer` là lớp mutable có đồng bộ hóa trên các thao tác của nó; overload dành riêng cho `StringBuffer` đồng bộ hóa việc quan sát bộ đệm khi so sánh.
- **`contentEquals(CharSequence)`:** so nội dung `String` với bất kỳ đối tượng triển khai `CharSequence`, chẳng hạn `StringBuilder`, `StringBuffer`, `String`, `CharBuffer` hoặc một implementation tự viết.

`StringBuilder` **không** có overload riêng; nó được chấp nhận vì `StringBuilder implements CharSequence`. Hai overload có cùng ý nghĩa kết quả: `true` khi nội dung dãy ký tự tương ứng giống chính xác; `false` nếu khác.

`CharSequence` là một interface đọc dãy `char`, với các thao tác như `length()`, `charAt(int)`, `subSequence(...)`. Interface **không bắt buộc đối tượng bất biến**. Vì vậy kết quả `contentEquals()` phản ánh nội dung tại thời điểm được quan sát trong phép gọi, chứ không phải một cam kết đối tượng sẽ giữ nguyên trong tương lai.

~~~java
CharSequence text = new StringBuilder("Java");
StringBuffer buffer = new StringBuffer("Java");

System.out.println("Java".contentEquals(text));   // true: overload CharSequence
System.out.println("Java".contentEquals(buffer)); // true: overload StringBuffer
System.out.println("Java".contentEquals("Java")); // true: String cũng là CharSequence
~~~

Khi biến có kiểu khai báo là `CharSequence`, trình biên dịch chọn overload `contentEquals(CharSequence)`, dù đối tượng runtime có thể là `StringBuffer`. Điều quan trọng là **ngữ nghĩa so nội dung**, không phải việc buộc người gọi ép kiểu sang overload khác.

## 3. `equals()`, `contentEquals()` và `==` khác gì?

| Biểu thức | Điều kiện trả `true` | Trường hợp dùng |
|---|---|---|
| `a == b` | Cùng tham chiếu đối tượng (với kiểu tham chiếu) | Kiểm tra identity, không dùng mặc định để so văn bản |
| `a.equals(b)` khi `a` là `String` | `b` cũng là `String` có cùng dãy ký tự UTF-16 | So sánh hai String |
| `a.contentEquals(cs)` | `cs` cung cấp cùng dãy ký tự hiện tại, kể cả khi là StringBuilder | So một String với CharSequence |
| `a.equals(cs.toString())` | Kết quả `toString()` là String có nội dung bằng `a` | Hợp lý khi đã cần bản String vì mục đích khác |
| `a.equalsIgnoreCase(b)` | Hai String bằng nhau theo quy tắc bỏ qua hoa/thường của Java | So văn bản không phân biệt hoa/thường; không có phiên bản CharSequence trực tiếp |

Ví dụ với hai đối tượng `String` khác nhau:

~~~java
String a = new String("abc");
String b = new String("abc");
System.out.println(a == b);              // false
System.out.println(a.equals(b));         // true
System.out.println(a.contentEquals(b));  // true
~~~

Nếu hai đầu đều là `String`, `equals()` thường là lựa chọn rõ nhất. Khi vế kia là `StringBuilder` hoặc một `CharSequence` được xây dựng trong quá trình xử lý, `contentEquals()` diễn đạt đúng nhu cầu mà không cần chủ động chuyển về String.

**Lưu ý quan trọng:** `StringBuilder` không override `Object.equals()` để so nội dung; `new StringBuilder("abc").equals(new StringBuilder("abc"))` là `false` vì đó là hai đối tượng khác nhau. Nếu muốn so **hai** `StringBuilder`, trong Java 17 có thể dùng `builder1.compareTo(builder2) == 0` vì `StringBuilder` triển khai `Comparable<StringBuilder>`; hoặc so thông qua một `String` với `contentEquals()`. Không suy ra rằng mọi loại `CharSequence` đều có `equals()` dựa vào nội dung: interface không quy định điều đó.

## 4. So sánh `StringBuilder` khi nội dung thay đổi

`StringBuilder` mutable: các lệnh `append()`, `insert()`, `delete()`, `replace()`, `setCharAt()`, `setLength()` có thể thay dãy ký tự. Lần so sánh sau có thể trả kết quả khác lần trước:

~~~java
String expected = "abc";
StringBuilder builder = new StringBuilder("abc");

System.out.println(expected.contentEquals(builder)); // true
builder.append('d');
System.out.println(expected.contentEquals(builder)); // false
builder.deleteCharAt(3);
System.out.println(expected.contentEquals(builder)); // true
~~~

Trong quá trình parse hoặc xây dựng thông điệp, hãy so sau khi đã có nội dung cần kiểm tra. Nếu cần một **snapshot ổn định** để lưu, truyền sang luồng khác hoặc tái sử dụng lâu dài, lấy `String snapshot = builder.toString();` tại điểm kiểm soát phù hợp rồi so bằng `equals()`; không giả định `CharSequence` mutable sẽ giữ nguyên nội dung.

### So sánh toàn bộ, không phải tiền tố hay chuỗi con

`contentEquals()` kiểm tra **toàn bộ dãy ký tự**. Nó không giống `contains()`, `startsWith()` hay so khớp một đoạn:

~~~java
StringBuilder full = new StringBuilder("status=OK");
System.out.println("status".contentEquals(full)); // false
System.out.println("status=OK".contentEquals(full)); // true
System.out.println("status=OK".startsWith("status")); // true
~~~

Nếu mục đích chỉ tìm một từ khóa trong chuỗi dài, hãy dùng `contains()`, `indexOf()` hoặc bộ parser thay vì `contentEquals()`.

## 5. So sánh với kiểu khai báo `CharSequence`

Một API nhận `CharSequence` giúp chấp nhận nhiều nguồn dữ liệu mà không ép caller chuyển hết sang `String`:

~~~java
static boolean isReady(CharSequence candidate) {
    return "READY".contentEquals(candidate);
}
~~~

Có thể gọi:

~~~java
System.out.println(isReady("READY"));                     // true
System.out.println(isReady(new StringBuilder("READY")));  // true
System.out.println(isReady(new StringBuffer("READY")));   // true
System.out.println(isReady(new StringBuilder("ready")));  // false
~~~

Hai khối trên là **đoạn minh họa**: hãy đặt phương thức `isReady` trong class, và những câu lệnh `System.out.println` trong một phương thức chạy, như chương trình tổng hợp bên dưới.

Interface `CharSequence` có các implementation khác nhau:

- `String`: nội dung bất biến.
- `StringBuilder`: mutable, tối ưu cho xây dựng chuỗi trong một luồng.
- `StringBuffer`: mutable, các phương thức của buffer có đồng bộ hóa.
- `java.nio.CharBuffer`: cung cấp một vùng ký tự theo `position` và `limit`; nội dung có thể phụ thuộc trạng thái và vùng nhìn thấy hiện tại.
- Các implementation tự viết: có thể có cơ chế tạo hoặc đọc nội dung riêng; không giả định `toString()`, `equals()` và `charAt()` có tính chất vượt quá hợp đồng mà API đó công bố.

Ví dụ với một `CharBuffer` được tạo để nhìn đúng bốn ký tự:

~~~java
import java.nio.CharBuffer;

CharBuffer buffer = CharBuffer.wrap("Java");
System.out.println("Java".contentEquals(buffer));  // true
buffer.position(1);
System.out.println("Java".contentEquals(buffer));  // false: phần còn lại là "ava"
System.out.println("ava".contentEquals(buffer));   // true
~~~

`CharBuffer` coi các ký tự từ `position` đến trước `limit` là phần tử còn lại của buffer. Thay `position` có thể thay dãy ký tự mà các phương thức `CharSequence` bộc lộ; do đó không nên xem mọi `CharSequence` là một String cố định.

## 6. Null, chữ hoa/thường, Unicode và khoảng trắng

### 6.1. Null

`"abc".contentEquals((CharSequence) null)` ném `NullPointerException`. Vế String nhận cũng không được null; `String s = null; s.contentEquals(...)` ném `NullPointerException`.

Nếu null là giá trị hợp lệ trong mô hình dữ liệu, kiểm tra trước:

~~~java
static boolean sameText(String expected, CharSequence actual) {
    return expected != null && actual != null
            && expected.contentEquals(actual);
}
~~~

Đây là quy ước **null không khớp**, kể cả khi cả hai null. Nếu nghiệp vụ cần null bằng null, xác định quy tắc đó tường minh; chẳng hạn chỉ với String/String có thể dùng `Objects.equals()`. Đừng giả định `contentEquals(null)` trả `false`.

### 6.2. Chữ hoa/thường và khoảng trắng

`contentEquals()` so chính xác dãy code unit: không bỏ dấu cách, không `trim`/`strip`, không chuyển hoa/thường.

~~~java
System.out.println("Java".contentEquals(new StringBuilder("java")));   // false
System.out.println("Java".contentEquals(new StringBuilder(" Java")));  // false
System.out.println("Java".contentEquals(new StringBuilder("Java")));   // true
~~~

Nếu cần so không phân biệt case hoặc bỏ khoảng trắng, phải làm rõ quy tắc chuẩn hóa đầu vào:

~~~java
import java.util.Locale;

StringBuilder candidate = new StringBuilder(" java ");
String normalized = candidate.toString().strip().toUpperCase(Locale.ROOT);
System.out.println("JAVA".equals(normalized)); // true
~~~

`Locale.ROOT` phù hợp nhiều mã máy không phụ thuộc ngôn ngữ, nhưng **không** thay thế quy tắc so sánh từ ngữ tự nhiên của mọi locale. Chuẩn hóa cần được quyết định theo yêu cầu thực tế; không thêm tự động vào `contentEquals()`.

### 6.3. Unicode: so theo UTF-16, không tự chuẩn hóa

Cả `String` và `CharSequence` bộc lộ một dãy `char` (UTF-16 code unit). Khi dùng `contentEquals()`, hai dãy phải giống nhau chính xác. Hai biểu diễn Unicode nhìn giống nhau có thể khác:

~~~java
import java.text.Normalizer;

String composed = "\u00E9";       // é: một code point
StringBuilder decomposed = new StringBuilder("e\u0301"); // e + dấu sắc

System.out.println(composed.contentEquals(decomposed)); // false
String normalized = Normalizer.normalize(
        decomposed.toString(), Normalizer.Form.NFC);
System.out.println(composed.equals(normalized)); // true
~~~

Emoji ngoài BMP có thể dùng **hai `char`**, nhưng nếu hai dãy code unit hoàn toàn giống nhau thì `contentEquals()` vẫn trả true:

~~~java
System.out.println("🚀".length());                             // 2
System.out.println("🚀".contentEquals(new StringBuilder("🚀"))); // true
~~~

Nếu cần so ngôn ngữ tự nhiên (ví dụ quy tắc sắp xếp tên tiếng Việt, bỏ dấu, case folding), phải chọn thuật toán/locale phù hợp; `contentEquals()` chỉ so nội dung chính xác. Nó cũng **không** thay cho so sánh mật khẩu hoặc secret với yêu cầu thời gian hằng số, vì API không cam kết đặc tính chống timing side-channel.

## 7. Đồng bộ và an toàn luồng

`String` bất biến và an toàn để nhiều luồng đọc nội dung của nó. `StringBuilder` mutable và **không có đồng bộ hóa nội bộ**, nên không được sửa nó đồng thời với lời gọi `contentEquals()` ở luồng khác nếu không có biện pháp phối hợp. Đọc `length()` và từng `charAt()` trên một đối tượng đang bị sửa có thể quan sát trạng thái không nhất quán; kết quả khó dự đoán, không có bảo đảm một snapshot nguyên tử.

`StringBuffer` sử dụng đồng bộ hóa cho các thao tác của nó. Overload `String.contentEquals(StringBuffer)` đồng bộ trên đối tượng buffer trong khi thực hiện so sánh, nên có thể quan sát dãy ký tự nhất quán đối với các thay đổi cũng tuân theo khóa đó. Tuy vậy, dữ liệu **vẫn có thể thay đổi trước hoặc sau lời gọi**. Không nhầm an toàn của một phép so với một chuỗi giao dịch nhiều thao tác.

Ví dụ một đoạn có nhiều bước:

~~~java
// Đoạn minh họa, không phải giao dịch nguyên tử:
StringBuffer shared = new StringBuffer("READY");
if ("READY".contentEquals(shared)) {
    // Luồng khác vẫn có thể sửa shared ngay sau khi if được đánh giá.
    // Không được suy ra shared luôn bằng "READY" trong phần thân này.
}
~~~

Nếu cần kiểm tra và sử dụng nội dung như một giao dịch, đồng bộ một đoạn bao quanh **cả bước kiểm tra lẫn bước sử dụng** bằng cùng khóa mà mọi writer tuân theo, hoặc chuyển dữ liệu sang snapshot bất biến ở ranh giới phù hợp.

~~~java
StringBuilder builder = new StringBuilder("READY");
// Sau khi đã kết thúc tất cả thao tác ghi trên builder:
String snapshot = builder.toString();
System.out.println("READY".equals(snapshot)); // true
~~~

Nếu nhiều luồng cùng truy cập `StringBuilder`, bước tạo snapshot cũng phải được đồng bộ đúng cách; bản thân `toString()` không tự sửa tình trạng ghi song song.

## 8. Hiệu năng: khi nào tránh `toString()`?

Khi đã có một `StringBuilder` và chỉ cần **một phép so toàn bộ nội dung**, `expected.contentEquals(builder)` có thể tránh một bước tạo String rõ ràng trong code. Việc tạo `String` từ builder bằng `toString()` có thể phát sinh cấp phát hoặc sao chép dữ liệu, tùy JVM/JDK; nhưng **không** thể từ đó khẳng định `contentEquals()` luôn không cấp phát hoặc luôn nhanh hơn.

So sánh:

~~~java
String expected = "GET";

// Cách 1: so trực tiếp dãy ký tự.
boolean direct = expected.contentEquals(builder);

// Cách 2: tạo String trung gian rồi so.
boolean converted = expected.equals(builder.toString());
~~~

Trong ví dụ này `builder` được giả định đã tồn tại và chứa văn bản cần kiểm tra. Đây **chỉ là hai cách viết để thảo luận**, không phải file Java độc lập.

Quy tắc chọn thực tế:

- Nếu chỉ cần **đúng một hoặc vài phép so** với một `StringBuilder` đã có, ưu tiên `contentEquals()` vì diễn đạt trực tiếp và không bắt buộc gọi `toString()`.
- Nếu cần lưu/đưa văn bản sang API nhận `String` hay tái sử dụng snapshot nhiều lần, `String snapshot = builder.toString();` có thể hợp lý và rõ ràng hơn.
- Nếu cần so **hai String**, sử dụng `equals()`; không chuyển chúng sang builder chỉ để gọi `contentEquals()`.
- Với đoạn nhạy hiệu năng, đo dữ liệu thực tế bằng profiler hoặc JMH; tránh benchmark vòng lặp đơn giản vì JIT/escape analysis có thể loại bỏ hoặc thay đổi chi phí một cách bất ngờ.

Không sử dụng `contentEquals()` như cách thay thế đồng loạt `equals()`. Nền tảng của nó là **khả năng so trực tiếp String với CharSequence khác String**.

## 9. Chương trình hoàn chỉnh chạy trên Java 17

Đặt toàn bộ đoạn dưới vào file UTF-8 tên **`ContentEqualsDemo.java`**. Chương trình minh họa overload, thay đổi nội dung, kiểm tra toàn chuỗi, CharSequence và một ví dụ chuẩn hóa Unicode.

~~~java
import java.nio.CharBuffer;
import java.text.Normalizer;
import java.util.Locale;

public class ContentEqualsDemo {
    private static boolean isReady(CharSequence value) {
        return value != null && "READY".contentEquals(value);
    }

    public static void main(String[] args) {
        String expected = "Java";
        StringBuilder builder = new StringBuilder("Java");

        System.out.println("equalsBuilder=" + expected.equals(builder));
        System.out.println("contentBuilder=" + expected.contentEquals(builder));
        System.out.println("equalsString=" + expected.equals(builder.toString()));

        builder.append('!');
        System.out.println("afterAppend=" + expected.contentEquals(builder));
        builder.deleteCharAt(4);
        System.out.println("afterDelete=" + expected.contentEquals(builder));

        CharSequence sequence = new StringBuilder("Java");
        StringBuffer buffer = new StringBuffer("Java");
        System.out.println("asSequence=" + expected.contentEquals(sequence));
        System.out.println("asBuffer=" + expected.contentEquals(buffer));

        CharBuffer charBuffer = CharBuffer.wrap("Java");
        System.out.println("charBufferFull=" + expected.contentEquals(charBuffer));
        charBuffer.position(1);
        System.out.println("charBufferSuffix=" + "ava".contentEquals(charBuffer));

        System.out.println("ready=" + isReady(new StringBuilder("READY")));
        System.out.println("nullReady=" + isReady(null));
        System.out.println("caseSensitive=" +
                "Java".contentEquals(new StringBuilder("java")));

        String normalized = new StringBuilder(" java ").toString()
                .strip().toUpperCase(Locale.ROOT);
        System.out.println("normalized=" + "JAVA".equals(normalized));

        String composed = "\u00E9";
        StringBuilder decomposed = new StringBuilder("e\u0301");
        System.out.println("unicodeDirect=" +
                composed.contentEquals(decomposed));
        System.out.println("unicodeNFC=" +
                composed.equals(Normalizer.normalize(
                        decomposed.toString(), Normalizer.Form.NFC)));
    }
}
~~~

Biên dịch bằng JDK 17+ với mã nguồn UTF-8 và chạy:

~~~bash
javac -encoding UTF-8 ContentEqualsDemo.java
java ContentEqualsDemo
~~~

Kết quả stdout chính xác:

~~~text
equalsBuilder=false
contentBuilder=true
equalsString=true
afterAppend=false
afterDelete=true
asSequence=true
asBuffer=true
charBufferFull=true
charBufferSuffix=true
ready=true
nullReady=false
caseSensitive=false
normalized=true
unicodeDirect=false
unicodeNFC=true
~~~

Giải thích quan trọng: `equalsBuilder=false` vì `String.equals(Object)` không coi `StringBuilder` là String. `contentBuilder=true` vì dãy ký tự trùng. Append một `!` làm độ dài khác, nên so thất bại; xóa nó thì bằng lại. `CharBuffer` trả dãy từ vị trí hiện tại tới giới hạn; khi chuyển vị trí sang 1, phần nội dung còn lại là `"ava"`. Chuẩn hóa Unicode NFC cho biểu diễn `e + dấu sắc` về biểu diễn tương đương với `é`.

## 10. Những lỗi phổ biến

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| `"abc".equals(new StringBuilder("abc"))` | Luôn false với StringBuilder | `"abc".contentEquals(builder)` |
| `a == b` để kiểm tra văn bản | So identity, không so nội dung | `equals()` hoặc `contentEquals()` phù hợp |
| Gọi `contentEquals(null)` | `NullPointerException` | Null-check trước |
| Coi kết quả so builder là vĩnh viễn | Builder có thể bị sửa sau đó | So tại điểm dùng hoặc tạo snapshot |
| Sửa builder cùng lúc so ở thread khác | Race, trạng thái không ổn định | Phối hợp đồng bộ hoặc snapshot an toàn |
| Mong bỏ qua hoa/thường/space | `contentEquals()` so chính xác | Chuẩn hóa có chủ đích rồi so |
| Mong Unicode nhìn giống sẽ bằng nhau | Hai dãy code point/code unit có thể khác | Chuẩn hóa phù hợp khi nghiệp vụ yêu cầu |
| Mong `contentEquals()` tìm chuỗi con | Nó kiểm tra cả dãy | `contains()`/`indexOf()` hoặc parser |
| Gọi `toString()` trong mọi phép so chỉ vì muốn dùng `equals()` | Có thể tạo bước chuyển đổi không cần thiết | Dùng `contentEquals()` trực tiếp khi chỉ cần so |
| Tin rằng `contentEquals()` luôn nhanh hơn | Tối ưu phụ thuộc trường hợp và JVM | Benchmark/profiler trên tải thật |

## 11. Ghi nhớ khi lựa chọn API

1. **Hai đối tượng là `String`:** `equals()` cho so nội dung chính xác; `equalsIgnoreCase()` nếu yêu cầu so bỏ qua hoa/thường và đã cân nhắc locale/ngữ nghĩa.
2. **Một `String`, một `StringBuilder`/`StringBuffer`/`CharSequence`:** `String.contentEquals()` cho so trực tiếp toàn bộ dãy.
3. **Cần một snapshot bất biến từ builder:** chuyển bằng `toString()` ở thời điểm kiểm soát phù hợp rồi so `equals()`; với dữ liệu dùng chung nhiều luồng, bảo đảm không ghi đồng thời thiếu đồng bộ.
4. **Cần tìm một đoạn:** sử dụng `contains()`, `indexOf()`, `startsWith()` hoặc regex tùy nhu cầu.
5. **Có dữ liệu null hoặc Unicode phức tạp:** đặt quy tắc null, case, khoảng trắng và normalization rõ ràng trước khi gọi API.

`contentEquals()` hữu ích chính vì **so trực tiếp nội dung hiện tại của một `CharSequence` với một `String`**, kể cả khi hai đối tượng thuộc các kiểu khác nhau. Nó không tự chuẩn hóa văn bản, không thay thế bảo đảm an toàn luồng và không biến `equals()` thành thừa.