# Tìm kiếm theo tiền tố và hậu tố với `startsWith`, `startsWith(prefix, offset)` và `endsWith` trong Java

Khi cần xác định một `String` có bắt đầu hoặc kết thúc bằng một chuỗi ký tự cho trước hay không, Java cung cấp ba cách dùng trực tiếp: `startsWith(String prefix)`, `startsWith(String prefix, int toffset)` và `endsWith(String suffix)`. Cả ba phương thức trả về kiểu `boolean` và **so sánh nội dung ký tự theo vị trí xác định**, không thay đổi chuỗi nguồn.

Điểm dễ nhầm nhất nằm ở overload có `toffset`: nó kiểm tra tiền tố **bắt đầu chính xác tại chỉ số `toffset` trong chuỗi nguồn**, chứ không đi tìm tiền tố ở một vị trí tùy ý từ `toffset` trở về sau.

## 1. Ý nghĩa của ba phương thức

| Phương thức | Kiểm tra điều gì? | Ví dụ |
| --- | --- | --- |
| `text.startsWith(prefix)` | `prefix` có xuất hiện ngay tại **đầu** `text` (chỉ số 0) không? | `"banana".startsWith("ban")` → `true` |
| `text.startsWith(prefix, toffset)` | `prefix` có khớp **ngay tại vị trí `toffset`** trong `text` không? | `"banana".startsWith("ana", 1)` → `true` |
| `text.endsWith(suffix)` | `suffix` có xuất hiện ngay tại **cuối** `text` không? | `"banana".endsWith("ana")` → `true` |

Chữ ký công khai trong lớp `java.lang.String`:

```java
public boolean startsWith(String prefix)
public boolean startsWith(String prefix, int toffset)
public boolean endsWith(String suffix)
```

Đây là chữ ký phương thức để tham khảo, không phải một chương trình chạy độc lập.

Cả ba đều kiểm tra **một chuỗi con liên tiếp**. Chuỗi có thể dài hơn tiền tố/hậu tố. Ví dụ, `"Spring Boot"` bắt đầu bằng `"Spring"` dù sau đó còn ký tự; `"file.txt"` kết thúc bằng `".txt"` dù trước hậu tố còn tên tệp.

## 2. `startsWith(String prefix)`: kiểm tra ngay tại đầu chuỗi

Ví dụ cơ bản:

```java
String text = "Java Core";

System.out.println(text.startsWith("Java"));   // true
System.out.println(text.startsWith("Ja"));     // true
System.out.println(text.startsWith("Core"));   // false
System.out.println(text.startsWith("Java Core")); // true
System.out.println(text.startsWith("Java Core!")); // false
```

Các lệnh trên là đoạn minh họa đặt trong một phương thức Java.

Một tiền tố có thể bằng toàn bộ nội dung chuỗi: `text.startsWith(text)` trả về `true`. Ngược lại, tiền tố dài hơn chuỗi nguồn không thể khớp. Phương thức không bỏ qua khoảng trắng, không tự chuyển hoa/thường, cũng không tự cắt bỏ ký tự xuống dòng.

Tệp chạy được `StartsWithBasics.java`:

```java
public class StartsWithBasics {
    public static void main(String[] args) {
        String text = "banana";

        System.out.println("ban: " + text.startsWith("ban"));
        System.out.println("ana at start: " + text.startsWith("ana"));
        System.out.println("whole: " + text.startsWith("banana"));
        System.out.println("longer: " + text.startsWith("bananas"));
        System.out.println("uppercase: " + text.startsWith("Ban"));
        System.out.println("suffix ana: " + text.endsWith("ana"));
        System.out.println("suffix ban: " + text.endsWith("ban"));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 StartsWithBasics.java
java StartsWithBasics
```

Kết quả:

```text
ban: true
ana at start: false
whole: true
longer: false
uppercase: false
suffix ana: true
suffix ban: false
```

Ở đây `"ana"` thực sự có trong `"banana"`, nhưng `startsWith("ana")` vẫn là `false` vì `"ana"` không nằm tại **đầu chuỗi**. Nếu mục tiêu là kiểm tra có xuất hiện **ở bất kỳ đâu**, dùng `contains(...)` hoặc `indexOf(...)` cho mục đích tìm kiếm khác.

## 3. `startsWith(String prefix, int toffset)`: kiểm tra ở một biên cụ thể

Overload hai tham số có cú pháp:

```java
boolean matched = text.startsWith(prefix, toffset);
```

`toffset` là **chỉ số UTF-16 code unit trong `text`**, đánh dấu vị trí ký tự đầu tiên phải được so khớp với `prefix`. Nếu tiền tố có độ dài `m`, phương thức cần khớp đúng `m` code unit liên tiếp bắt đầu từ chỉ số `toffset`.

Ví dụ, trong `"banana"`:

```text
Chuỗi:       b a n a n a
Chỉ số:      0 1 2 3 4 5
             | | | | | |
"ana" tại 1:  a n a
"ana" tại 3:      a n a
```

Vì thế:

- `"banana".startsWith("ana", 0)` → `false`; đầu chuỗi là `"ban"`.
- `"banana".startsWith("ana", 1)` → `true`; từ vị trí 1 là `"ana..."`.
- `"banana".startsWith("ana", 2)` → `false`; từ vị trí 2 là `"nan..."`.
- `"banana".startsWith("ana", 3)` → `true`; ba ký tự cuối là `"ana"`.

Tệp `StartsWithOffsetDemo.java`:

```java
public class StartsWithOffsetDemo {
    public static void main(String[] args) {
        String text = "banana";

        for (int offset = 0; offset <= text.length(); offset++) {
            System.out.printf("offset %d: %b%n",
                    offset, text.startsWith("ana", offset));
        }

        System.out.println("offset -1: " + text.startsWith("ana", -1));
        System.out.println("offset 7: " + text.startsWith("ana", 7));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 StartsWithOffsetDemo.java
java StartsWithOffsetDemo
```

Đầu ra:

```text
offset 0: false
offset 1: true
offset 2: false
offset 3: true
offset 4: false
offset 5: false
offset 6: false
offset -1: false
offset 7: false
```

Nếu `toffset` âm, vượt quá độ dài chuỗi, hoặc không còn đủ ký tự để chứa toàn bộ `prefix`, kết quả là `false` (với `prefix` không phải `null`). Đây là **kết quả so khớp không thành công**, chứ không phải lời gọi luôn ném `IndexOutOfBoundsException` khi `toffset` nằm ngoài phạm vi. Riêng tiền tố rỗng có quy tắc biên hợp lệ được giải thích ở phần sau.

### Điều rất dễ nhầm: offset không phải vị trí bắt đầu tìm kiếm

Ví dụ:

```java
String text = "abaXaba";

System.out.println(text.startsWith("aba", 1)); // false
System.out.println(text.indexOf("aba", 1));     // 4
```

`startsWith("aba", 1)` chỉ kiểm tra ba ký tự ở **chính vị trí 1** (`"baX"`), nên trả `false`. `indexOf("aba", 1)` tìm **từ chỉ số 1 trở đi** và trả về vị trí 4 khi tìm thấy. Không thể thay thế hai phương thức này cho nhau.

Nếu cần so khớp một nhãn đứng sau phần đầu cố định, `startsWith(prefix, offset)` rất phù hợp:

```java
String line = "2026-10-22 ERROR: connection lost";

System.out.println(line.startsWith("ERROR:", 11)); // true
System.out.println(line.startsWith("ERROR:", 10)); // false
```

Với dữ liệu trên, ký tự `E` đầu tiên của `ERROR:` nằm tại chỉ số 11. Tuy nhiên, khi dữ liệu phần đầu có độ dài biến đổi, đừng tự đoán một offset cố định: hãy tìm mốc phù hợp bằng `indexOf` hoặc phân tích cấu trúc dữ liệu trước.

## 4. `endsWith(String suffix)`: kiểm tra phần kết thúc

`endsWith(suffix)` trả về `true` nếu các code unit cuối của chuỗi nguồn bằng toàn bộ `suffix`. Phương thức không nhận tham số offset vì vị trí được xác định từ **cuối chuỗi nguồn**.

```java
String file = "report.csv";

System.out.println(file.endsWith(".csv"));  // true
System.out.println(file.endsWith("csv"));   // true
System.out.println(file.endsWith(".txt"));  // false
System.out.println(file.endsWith("report.csv")); // true
System.out.println(file.endsWith("REPORT.CSV")); // false
```

Hậu tố có thể bằng toàn bộ chuỗi. Nếu hậu tố dài hơn chuỗi, kết quả là `false`. Việc kiểm tra không tự nhận biết khái niệm đuôi tệp, URL hay loại MIME; nó chỉ so sánh ký tự.

Về quan hệ ngữ nghĩa, với một `suffix` không `null`, có thể hiểu phép kiểm tra:

```java
text.endsWith(suffix)
```

tương đương về kết quả với:

```java
text.startsWith(suffix, text.length() - suffix.length())
```

Nếu hậu tố dài hơn chuỗi, hiệu `text.length() - suffix.length()` âm và việc kiểm tra bắt đầu ở offset âm thất bại. Đây là cách nhìn để hiểu vị trí kiểm tra, **không phải yêu cầu bạn phải viết lại `endsWith`** trong code ứng dụng.

## 5. Prefix và suffix rỗng: những trường hợp biên

Chuỗi rỗng `""` là tiền tố và hậu tố hợp lệ của **mọi `String`**.

```java
String text = "Java";
String empty = "";

System.out.println(text.startsWith(empty)); // true
System.out.println(text.endsWith(empty));   // true
System.out.println(empty.startsWith(empty)); // true
System.out.println(empty.endsWith(empty));  // true
```

Với overload có offset, tiền tố rỗng khớp tại **mọi vị trí biên hợp lệ từ 0 đến `text.length()`**, bao gồm biên cuối:

| Lời gọi với `text = "Java"` (độ dài 4) | Kết quả | Giải thích |
| --- | --- | --- |
| `text.startsWith("", 0)` | `true` | Tiền tố rỗng tại biên đầu |
| `text.startsWith("", 2)` | `true` | Tiền tố rỗng tại biên giữa |
| `text.startsWith("", 4)` | `true` | Tiền tố rỗng tại biên cuối |
| `text.startsWith("", -1)` | `false` | Offset âm không hợp lệ |
| `text.startsWith("", 5)` | `false` | Offset lớn hơn độ dài |
| `text.startsWith("J", 4)` | `false` | Không còn code unit cho tiền tố không rỗng |

Điều này tương tự khoảng rỗng `[k, k)` ở một biên hợp lệ: vì không cần so khớp ký tự nào nên kết quả là `true`. Đừng tự động đồng nhất `startsWith("") == true` với việc chuỗi có chứa dữ liệu; ngay cả chuỗi nguồn rỗng cũng trả về `true`.

Tệp `EmptyPrefixSuffix.java` giúp kiểm tra đầy đủ:

```java
public class EmptyPrefixSuffix {
    public static void main(String[] args) {
        String text = "Java";

        System.out.println("empty prefix: " + text.startsWith(""));
        System.out.println("empty suffix: " + text.endsWith(""));
        System.out.println("at length: "
                + text.startsWith("", text.length()));
        System.out.println("after length: "
                + text.startsWith("", text.length() + 1));
        System.out.println("nonempty at length: "
                + text.startsWith("a", text.length()));
        System.out.println("empty source: "
                + "".startsWith(""));
    }
}
```

Biên dịch:

```bash
javac -encoding UTF-8 EmptyPrefixSuffix.java
java EmptyPrefixSuffix
```

Đầu ra:

```text
empty prefix: true
empty suffix: true
at length: true
after length: false
nonempty at length: false
empty source: true
```

Nếu muốn một prefix/suffix **bắt buộc phải có nội dung**, hãy xác thực điều kiện `!prefix.isEmpty()` hoặc `!suffix.isEmpty()` trước khi kiểm tra. Hành vi mặc định của API là cố ý và nhất quán.

## 6. So sánh có phân biệt hoa/thường và không tự chuẩn hóa Unicode

Ba phương thức đều so sánh **chính xác dãy UTF-16 code unit**. Chúng không tự:

- bỏ qua phân biệt chữ hoa/chữ thường;
- xóa khoảng trắng đầu/cuối;
- xử lý biến thể Unicode tương đương theo chuẩn hóa;
- thực thi biểu thức chính quy (regex), wildcard `*` hoặc `?`;
- dịch nghĩa văn bản theo ngôn ngữ tự nhiên.

Ví dụ:

```java
String name = "Readme.md";

System.out.println(name.startsWith("read")); // false
System.out.println(name.endsWith(".MD"));    // false
System.out.println(name.endsWith(".md"));    // true
```

Nếu nghiệp vụ **đối với dữ liệu ASCII** muốn so sánh không phân biệt hoa/thường, có thể chuyển đổi các phía theo cùng quy tắc, chẳng hạn `toLowerCase(Locale.ROOT)`. Tuy nhiên, xử lý Unicode đầy đủ có thể phức tạp hơn vì ánh xạ chữ hoa/thường đôi khi thay đổi số code point; việc chuẩn hóa hai chuỗi cần được thiết kế và kiểm thử theo dữ liệu thực tế.

Khi chỉ cần so khớp một vùng cố định mà không phân biệt hoa/thường, `regionMatches(true, ...)` là API khác đáng cân nhắc:

```java
String text = "Java Core";
String prefix = "java";
boolean result = text.regionMatches(
        true, 0, prefix, 0, prefix.length()
);
System.out.println(result); // true
```

Ở đây `true` bật chế độ ignore case của `regionMatches`; đây **không phải** overload của `startsWith`. Đoạn minh họa cần đặt trong một phương thức và biến `text` đã được khai báo như trên.

Với Unicode, hai chuỗi có thể hiển thị giống nhau nhưng khác dãy code point. Ví dụ `"\u00E9"` (é tiền tổ hợp) và `"e\u0301"` (e cộng dấu kết hợp) không tự động bằng nhau trong `startsWith` hoặc `endsWith` nếu chưa chuẩn hóa. Cần phân biệt vấn đề này với quy tắc so sánh tiền tố/hậu tố.

## 7. Vị trí trong `startsWith(prefix, toffset)` là UTF-16, không phải code point

Trong Java, `String.length()`, `charAt()` và tham số `toffset` dùng **chỉ số UTF-16 code unit**. Một Unicode code point ngoài BMP (ví dụ emoji 😀, `U+1F600`) chiếm hai code unit (surrogate pair). Vì vậy, vị trí code point và vị trí UTF-16 có thể không trùng nhau.

Tệp `UnicodeOffsetPrefix.java`:

```java
public class UnicodeOffsetPrefix {
    public static void main(String[] args) {
        String smile = new String(Character.toChars(0x1F600));
        String text = "A" + smile + "B";

        System.out.println("length=" + text.length());
        System.out.println("smile at 1=" + text.startsWith(smile, 1));
        System.out.println("smile at 2=" + text.startsWith(smile, 2));
        System.out.println("B at 2=" + text.startsWith("B", 2));
        System.out.println("B at 3=" + text.startsWith("B", 3));
        System.out.println("ends with B=" + text.endsWith("B"));

        int indexAfterTwoCodePoints = text.offsetByCodePoints(0, 2);
        System.out.println("B at code point boundary="
                + text.startsWith("B", indexAfterTwoCodePoints));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 UnicodeOffsetPrefix.java
java UnicodeOffsetPrefix
```

Kết quả:

```text
length=4
smile at 1=true
smile at 2=false
B at 2=false
B at 3=true
ends with B=true
B at code point boundary=true
```

`text` chứa ba code point (`A`, emoji, `B`) nhưng có bốn UTF-16 code unit. `B` nằm ở chỉ số UTF-16 **3**, không phải **2**. Nếu bắt đầu từ **vị trí code point**, hãy chuyển thành chỉ số UTF-16 với `offsetByCodePoints(...)`.

Các phương thức prefix/suffix chỉ thực hiện so khớp code unit; chúng không kiểm chứng ranh giới grapheme cluster và cũng không từ chối một chuỗi chứa surrogate đứng lẻ. Với dữ liệu văn bản quốc tế, phải định nghĩa đúng đơn vị chỉ số trước khi gọi overload có offset.

## 8. Ví dụ ứng dụng: kiểm tra nhãn đầu dòng và phần mở rộng tệp

Bài toán: đọc một số chuỗi đầu vào và phân loại theo nhãn `INFO:`, `ERROR:`, hoặc kiểm tra tên tệp có hậu tố `.csv`. Các so sánh này phù hợp vì nhãn nằm **ở đầu** và đuôi tệp nằm **ở cuối**.

Tệp `PrefixSuffixUseCase.java`:

```java
public class PrefixSuffixUseCase {
    static String logLevel(String line) {
        if (line.startsWith("ERROR:")) {
            return "error";
        }
        if (line.startsWith("INFO:")) {
            return "info";
        }
        return "other";
    }

    static boolean isCsv(String fileName) {
        return fileName.endsWith(".csv");
    }

    public static void main(String[] args) {
        System.out.println(logLevel("ERROR: disk full"));
        System.out.println(logLevel("INFO: started"));
        System.out.println(logLevel(" WARN: pending"));

        System.out.println(isCsv("report.csv"));
        System.out.println(isCsv("report.csv.bak"));
        System.out.println(isCsv("REPORT.CSV"));

        String message = "2026-10-22 ERROR: disk full";
        System.out.println(message.startsWith("ERROR:", 11));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 PrefixSuffixUseCase.java
java PrefixSuffixUseCase
```

Kết quả:

```text
error
info
other
true
false
false
true
```

Các tình huống cần hiểu:

- `" WARN: pending"` có dấu cách ở đầu nên không khớp bất kỳ nhãn nào bắt đầu tại chỉ số 0; ứng dụng muốn bỏ qua khoảng trắng cần xử lý riêng.
- `"report.csv.bak"` chứa `".csv"` ở giữa, nhưng không **kết thúc** bằng `".csv"`; `endsWith(".csv")` trả `false`.
- `"REPORT.CSV"` không kết thúc bằng `".csv"` theo so sánh phân biệt hoa/thường.
- Trong `message`, chuỗi `ERROR:` bắt đầu ở chỉ số 11, nên overload `startsWith("ERROR:", 11)` kiểm tra thành công.

Kiểm tra `endsWith(".csv")` chỉ nhận diện hậu tố ký tự; nó **không xác minh nội dung tệp thực sự là CSV**, không bảo đảm an toàn đường dẫn và không thay thế xác thực định dạng dữ liệu.

## 9. So sánh với `contains`, `indexOf`, `matches` và `regionMatches`

Khi chọn API, hãy bắt đầu bằng ý nghĩa câu hỏi:

| Câu hỏi của ứng dụng | API phù hợp |
| --- | --- |
| Có bắt đầu bằng tiền tố tại chỉ số 0 không? | `startsWith(prefix)` |
| Có đúng tiền tố tại chỉ số UTF-16 xác định không? | `startsWith(prefix, toffset)` |
| Có kết thúc bằng hậu tố không? | `endsWith(suffix)` |
| Một chuỗi ký tự xuất hiện **ở bất kỳ đâu** không? | `contains(fragment)` |
| Chuỗi xuất hiện **đầu tiên ở đâu**, tùy chọn bắt đầu tìm từ vị trí nào? | `indexOf(fragment)` hoặc `indexOf(fragment, fromIndex)` |
| Toàn bộ chuỗi có khớp một **regex** không? | `matches(regex)` |
| Hai vùng ký tự có bằng nhau, có tùy chọn bỏ qua hoa/thường không? | `regionMatches(...)` |

Ví dụ:

```java
String text = "banana";

System.out.println(text.startsWith("ana"));    // false
System.out.println(text.startsWith("ana", 1)); // true
System.out.println(text.contains("ana"));      // true
System.out.println(text.indexOf("ana"));       // 1
System.out.println(text.endsWith("ana"));      // true
```

Không nên dùng `matches(".*prefix.*")` chỉ để hỏi một chuỗi có bắt đầu bằng nội dung cố định hay không. `startsWith` rõ mục đích hơn và không biến ký tự trong tiền tố thành cú pháp regex.

## 10. Giá trị `null` và an toàn khi sử dụng

Các phương thức này không xem `null` là tiền tố hoặc hậu tố rỗng. Nếu truyền tham số `null` cho `startsWith` hoặc `endsWith`, lời gọi sẽ ném `NullPointerException`. Nếu chính biến chuỗi nguồn là `null`, gọi phương thức trên nó cũng gây `NullPointerException`.

Ví dụ xử lý tham chiếu có thể là `null`:

```java
static boolean hasErrorPrefix(String line) {
    return line != null && line.startsWith("ERROR:");
}

static boolean hasCsvSuffix(String fileName) {
    return fileName != null && fileName.endsWith(".csv");
}
```

Hai phương thức trên là ví dụ minh họa cần đặt bên trong một lớp Java. Toán tử `&&` thực hiện đánh giá ngắn mạch, nên chỉ gọi API chuỗi khi tham chiếu nguồn không `null`.

Nếu `prefix` hoặc `suffix` đến từ dữ liệu đầu vào và có thể là `null`, hãy xử lý chúng theo quy định nghiệp vụ (từ chối, yêu cầu không rỗng hoặc dùng một giá trị mặc định có chủ đích), thay vì ngầm coi `null` bằng `""`.

## 11. Lỗi phổ biến và cách tránh

**1. Tưởng `startsWith(prefix, offset)` tìm vị trí đầu tiên sau offset.** Phương thức chỉ kiểm tra **đúng tại offset**; cần tìm từ offset trở đi thì dùng `indexOf(prefix, offset)`.

**2. Nghĩ offset nằm ngoài chuỗi luôn ném ngoại lệ.** Với tiền tố không `null`, `startsWith(prefix, offset)` trả `false` nếu offset âm hoặc vượt phạm vi có thể so khớp, kể cả trường hợp không đủ ký tự còn lại.

**3. Bỏ quên tiền tố/hậu tố rỗng.** `startsWith("")` và `endsWith("")` luôn `true`; `startsWith("", offset)` chỉ `true` khi offset nằm trong khoảng từ 0 đến `length()`. Kiểm tra thêm `isEmpty()` nếu yêu cầu nghiệp vụ cần chuỗi con không rỗng.

**4. Tưởng các phương thức bỏ qua hoa/thường, khoảng trắng hoặc normalization.** Cả ba so khớp nội dung thực của `String`; mọi tiền xử lý cần được thiết kế riêng.

**5. Nhầm offset là số Unicode code point.** Java dùng chỉ số UTF-16; với emoji và ký tự bổ sung, chỉ số có thể khác vị trí code point.

**6. Dùng `endsWith(".txt")` như bằng chứng chắc chắn về kiểu nội dung.** Hậu tố chỉ phản ánh tên chuỗi, không xác thực file hay định dạng dữ liệu.

**7. Truyền `null` và mong kết quả `false`.** Cần tự kiểm tra đầu vào nếu có thể `null`.

**8. Dùng `contains` để thay thế kiểm tra chính xác đầu/cuối.** `contains` có thể đúng dù phần cần tìm nằm giữa chuỗi; điều kiện phân loại sẽ sai nếu nghiệp vụ yêu cầu tiền tố hoặc hậu tố.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Với `String s = "banana";`, ba lệnh sau trả về gì?

```java
s.startsWith("ana")
s.startsWith("ana", 1)
s.startsWith("ana", 2)
```

**Đáp án:** lần lượt là `false`, `true`, `false`. `"ana"` không ở đầu chuỗi, nhưng xuất hiện đúng tại chỉ số 1 và không xuất hiện tại chỉ số 2.

**Câu 2.** Vì sao `"abc".startsWith("", 3)` là `true` nhưng `"abc".startsWith("", 4)` là `false`?

**Đáp án:** tiền tố rỗng khớp tại biên hợp lệ từ 0 đến `length()` (bằng 3), còn chỉ số 4 vượt biên cuối.

**Câu 3.** `"archive.tar.gz".endsWith(".tar")` cho kết quả gì?

**Đáp án:** `false`, bởi toàn bộ chuỗi kết thúc bằng `".gz"`. `".tar"` chỉ xuất hiện trước hậu tố cuối cùng.

**Câu 4.** Nếu cần tìm `"ERROR:"` ở bất cứ vị trí nào từ offset 5 trở về sau, nên dùng API nào?

**Đáp án:** `indexOf("ERROR:", 5)`, rồi kiểm tra kết quả có khác `-1` không. `startsWith("ERROR:", 5)` chỉ kiểm tra chính xác tại vị trí 5.

**Câu 5.** `startsWith` và `endsWith` có hiểu `.` hoặc `*` là ký tự đại diện regex không?

**Đáp án:** Không. Các tham số là dãy ký tự thông thường; muốn dùng biểu thức chính quy, phải chọn API phù hợp với regex và xử lý cú pháp riêng.

**Ghi nhớ:** `startsWith(prefix)` kiểm tra **đầu chuỗi**, `startsWith(prefix, toffset)` kiểm tra **đúng tại offset** theo UTF-16, và `endsWith(suffix)` kiểm tra **cuối chuỗi**. Cả ba phân biệt hoa/thường, xử lý tiền tố/hậu tố rỗng theo quy tắc biên, và không tự tìm kiếm tùy ý bên trong chuỗi.
