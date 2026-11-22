# Giá trị trả về và đơn vị số lượng ký tự đã chuyển của `Reader.transferTo` (Java 10+)

## 1. Quy tắc cốt lõi

`java.io.Reader.transferTo(Writer out)` được bổ sung trong **Java 10**, vẫn là API tiêu chuẩn và hữu ích trong Java hiện đại. Phương thức đọc các **ký tự còn lại** từ `Reader` hiện tại, viết chúng sang `Writer` được cung cấp theo đúng thứ tự đọc, rồi **trả về số ký tự thực sự đã chuyển**.

~~~java
public long transferTo(Writer out) throws IOException
~~~

Đây là **chữ ký API của lớp `Reader`**, không phải phương thức bạn cần tự định nghĩa.

Điểm quan trọng nhất của bài:

- Giá trị trả về có **kiểu `long`**, không phải `int`, `void` hay `String`.
- Đơn vị đếm là **`char` của Java, tức các đơn vị mã UTF-16 (*UTF-16 code units*)** khi làm việc với văn bản Unicode theo mô hình `Reader`/`Writer`.
- **Không phải số byte**, **không nhất thiết là số Unicode code point**, và **không phải số ký tự người dùng nhìn thấy (*grapheme clusters*)**.
- Đếm lượng **thực sự còn lại tại vị trí đọc hiện tại**, không tự động đếm lại phần dữ liệu `Reader` đã tiêu thụ trước đó.
- Khi thành công, `Reader` đang ở **cuối luồng (EOF)**. Gọi `transferTo` thêm lần nữa trên Reader vẫn mở nhưng đã ở EOF sẽ trả về **`0L`**.
- Phương thức **không tự đóng** `Reader` hay `Writer`.
- Nếu phát sinh lỗi I/O, phương thức **ném `IOException`**, không trả một giá trị `long` đặc biệt để báo lỗi.

Nếu tổng số ký tự chuyển vượt quá `Long.MAX_VALUE`, hợp đồng API quy định trả về **`Long.MAX_VALUE`** (bão hòa ở giới hạn kiểu `long`). Đây là trường hợp cực lớn và hiếm trong thực tế, nhưng cho thấy giá trị trả về được thiết kế cho dữ liệu có thể lớn hơn khả năng đếm của `int`.

## 2. Ví dụ đơn giản: giá trị trả về bằng 7

~~~java
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;

// Đoạn mã đặt trong một phương thức throws IOException:
try (Reader source = new StringReader("Java 10");
     StringWriter destination = new StringWriter()) {

    long count = source.transferTo(destination);

    System.out.println(count);                  // 7
    System.out.println(destination.toString()); // Java 10
}
~~~

Vì `"Java 10"` gồm bảy đơn vị `char` Java, `count` nhận `7L`. Trong một trường hợp đơn giản như vậy, bạn có thể thấy:

~~~java
"Java 10".length() == 7 // true
~~~

Nhưng **không được suy luận rằng `transferTo` luôn bằng độ dài của chuỗi nguồn ban đầu**. Điều đó chỉ đúng khi Reader bắt đầu tại đầu văn bản, còn đủ mọi ký tự và chuyển thành công toàn bộ.

### `var` có suy luận đúng `long` không?

Có. Trong Java 10 trở lên:

~~~java
var count = source.transferTo(destination); // Kiểu tĩnh: long
~~~

`var` chỉ thay kiểu khai báo cục bộ bằng suy luận từ lời gọi; không đổi kiểu trả về của API. Khi cần truyền qua tham số hoặc lưu giá trị lớn, hãy giữ kiểu `long`:

~~~java
long transferred = source.transferTo(destination);
~~~

Không viết:

~~~java
// int count = source.transferTo(destination);
// Lỗi biên dịch: không tự thu hẹp long sang int.
~~~

Ép kiểu `(int)` chỉ hợp lý nếu đã chủ động kiểm tra phạm vi; không nên ép kiểu một cách tùy tiện vì có thể mất thông tin khi số lượng ký tự lớn.

## 3. `Reader` chuyển **`char`**, không chuyển byte

Java tách riêng hai loại API nhập/xuất:

| API | Luồng đầu vào → đầu ra | Đơn vị đếm của `transferTo` |
| --- | --- | --- |
| `Reader.transferTo(Writer)` | Luồng **ký tự** → luồng **ký tự** | Số đơn vị `char` đã chuyển; trả về `long` |
| `InputStream.transferTo(OutputStream)` | Luồng **byte** → luồng **byte** | Số **byte** đã chuyển; trả về `long` |

Hai phương thức cùng tên `transferTo` nhưng **khác đơn vị thống kê**. `InputStream.transferTo` là API luồng byte, còn bài này tập trung vào `Reader.transferTo`.

Ví dụ, chuỗi `"é"` dạng một mã Unicode U+00E9 thường có:

- `String.length() == 1` (một đơn vị UTF-16).
- `String.codePointCount(0, 1) == 1` (một code point).
- Khi mã hóa **UTF-8**, `getBytes(StandardCharsets.UTF_8).length == 2` (hai byte).

Nếu đưa `"é"` qua `StringReader.transferTo(StringWriter)`, giá trị trả về là **`1`**, không phải `2`. Phương thức không nhìn vào số byte của biểu diễn UTF-8 để tính kết quả.

### Khi chuyển file văn bản thì sao?

~~~java
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;

// Đoạn mã minh họa trong phương thức throws IOException:
try (Reader reader = Files.newBufferedReader(
             Paths.get("input.txt"), StandardCharsets.UTF_8);
     Writer writer = Files.newBufferedWriter(
             Paths.get("output.txt"), StandardCharsets.UTF_8)) {

    long chars = reader.transferTo(writer);
    System.out.println("Transferred UTF-16 units: " + chars);
}
~~~

Đây là **đoạn minh họa thao tác file**: `input.txt` phải tồn tại tại thư mục chạy chương trình và `output.txt` sẽ được tạo hoặc ghi đè theo hành vi mặc định của `Files.newBufferedWriter`.

- `Files.newBufferedReader(..., UTF_8)` **giải mã byte** từ file thành các `char` Java.
- `transferTo` đếm `char` đi qua giao diện `Reader`/`Writer`.
- `Files.newBufferedWriter(..., UTF_8)` **mã hóa lại ký tự** thành byte để lưu vào file.

Vì bước giải mã/mã hóa là chuyện riêng, không thể lấy `chars` làm số byte của file đầu ra. Nếu cần **dung lượng file**, hãy kiểm tra bằng API file tương ứng, chẳng hạn `Files.size(path)` sau khi dữ liệu đã được ghi xong, thay vì sử dụng kết quả `Reader.transferTo`.

## 4. Unicode: một code point có thể chiếm **hai `char`**

Đây là lỗi đếm thường gặp nhất. `String` Java sử dụng mô hình UTF-16; một ký tự Unicode ngoài *Basic Multilingual Plane* (BMP), chẳng hạn ký hiệu mặt cười 🙂 (U+1F642), được biểu diễn bằng **cặp surrogate gồm hai đơn vị `char`**.

Ví dụ tạo văn bản chứa một ký tự bổ sung mà không phụ thuộc bộ mã hóa file nguồn Java:

~~~java
String face = new String(Character.toChars(0x1F642));
String text = "A" + face + "B";
~~~

Văn bản hiển thị gồm:

1. `A` — một `char`.
2. 🙂 — **hai `char`** tạo thành một Unicode code point.
3. `B` — một `char`.

Vì thế:

~~~java
System.out.println(text.length()); // 4
System.out.println(
        text.codePointCount(0, text.length())); // 3
System.out.println(
        text.getBytes(java.nio.charset.StandardCharsets.UTF_8).length); // 6
~~~

Khi chuyển bằng `Reader.transferTo`:

~~~java
try (Reader source = new StringReader(text);
     StringWriter destination = new StringWriter()) {

    long copied = source.transferTo(destination);
    System.out.println(copied);                       // 4
    System.out.println(text.equals(destination.toString())); // true
}
~~~

**`copied == 4`**, vì Reader đếm bốn đơn vị UTF-16, không đếm ba code point hay sáu byte UTF-8.

### Ba khái niệm khác nhau

| Đại lượng | Phép đo | Giá trị cho `"A" + 🙂 + "B"` |
| --- | --- | --- |
| **UTF-16 code units** | `text.length()` | `4` |
| **Unicode code points** | `text.codePointCount(0, text.length())` | `3` |
| **Byte UTF-8** | `text.getBytes(StandardCharsets.UTF_8).length` | `6` |
| **Số `char` do Reader chuyển** | `source.transferTo(writer)` | `4` |

Một **grapheme cluster** (ký tự hiển thị với người dùng) còn là khái niệm khác. Ví dụ một chữ cái kết hợp dấu thanh có thể gồm nhiều code point dù mắt người thấy một ký tự. `Reader.transferTo` **không thực hiện phân đoạn grapheme** và cũng không làm chuẩn hóa Unicode trước khi đếm.

**Quy tắc kiểm thử đúng:** so sánh giá trị trả về với số `char` trong dữ liệu đã đọc, không dùng số emoji hoặc số ký tự hiển thị trên màn hình.

## 5. Giá trị trả về chỉ tính phần **còn lại** của `Reader`

`transferTo` bắt đầu tại **vị trí hiện tại** của Reader. Nếu Reader đã được đọc, bỏ qua hoặc tiêu thụ một phần trước đó, phương thức không quay về đầu.

~~~java
try (Reader source = new StringReader("XYZ");
     StringWriter destination = new StringWriter()) {

    int first = source.read(); // Đọc và tiêu thụ 'X'.

    long remaining = source.transferTo(destination);

    System.out.println((char) first); // X
    System.out.println(remaining);    // 2
    System.out.println(destination);  // YZ
}
~~~

Đây là ví dụ `StringReader`, trong đó nguồn ban đầu có ba `char` nhưng chỉ còn `Y` và `Z` khi gọi `transferTo`. Kết quả đúng là **`2L`**, không phải `3L`.

Các thao tác có thể ảnh hưởng vị trí đọc:

- `read()` hoặc `read(char[])` tiêu thụ dữ liệu.
- `skip(n)` có thể bỏ qua một số ký tự.
- Các thao tác đặc thù như `BufferedReader.readLine()` có thể đã tiêu thụ cả ký tự kết thúc dòng.
- `mark/reset`, khi Reader hỗ trợ và được dùng hợp lệ, có thể đặt lại vị trí đọc.

Không nên chỉ biết dung lượng ban đầu rồi tính số lượng còn lại bằng phép trừ tùy ý khi không hiểu vị trí nguồn. **Giá trị trả về của `transferTo` chính là lượng chuyển thực tế trong lần gọi đó**, nếu phương thức hoàn tất bình thường.

## 6. Giá trị `0L` khi nguồn trống hoặc đã ở EOF

Hai tình huống bình thường trả về `0`:

### Nguồn đã rỗng từ đầu

~~~java
try (Reader source = new StringReader("");
     Writer target = new StringWriter()) {

    long count = source.transferTo(target);
    System.out.println(count); // 0
}
~~~

### Nguồn đã được đọc đến hết bởi lần `transferTo` trước

~~~java
try (Reader source = new StringReader("AB");
     StringWriter target = new StringWriter()) {

    long first = source.transferTo(target); // 2
    long second = source.transferTo(new StringWriter()); // 0

    System.out.println(first);  // 2
    System.out.println(second); // 0
}
~~~

`0` **không phải mã lỗi**, mà là số đơn vị `char` đã chuyển thành công khi không còn ký tự nào để đọc.

**Phân biệt:** `Reader.read()` trả về `-1` khi gặp EOF; `Reader.transferTo` trả về **`0`** nếu không có gì để chuyển. Không viết `if (count == -1)` để nhận biết EOF cho `transferTo`.

Nếu `Reader` bị đóng không đúng thời điểm hoặc gặp lỗi đọc/ghi, thay vì luôn trả `0`, nó có thể **ném `IOException`**. Không được coi `0` là lời hứa “file không tồn tại” hay “Reader đang lỗi”.

## 7. Không được đếm cả dữ liệu đã có sẵn trong `Writer`

Một `Writer` có thể đã chứa văn bản trước khi nhận dữ liệu mới. `transferTo` chỉ trả về **số ký tự lấy từ Reader để chuyển trong lần gọi này**, không trả tổng chiều dài đầu ra sau khi ghi.

~~~java
try (Reader source = new StringReader("XYZ");
     StringWriter target = new StringWriter()) {

    target.write("prefix:");
    source.read(); // Tiêu thụ 'X'.

    long transferred = source.transferTo(target);

    System.out.println(transferred);     // 2
    System.out.println(target.toString()); // prefix:YZ
    System.out.println(target.toString().length()); // 9
}
~~~

Phân tích:

- `"prefix:"` gồm **7 `char`** đã có sẵn trước.
- Phần còn lại của Reader là `"YZ"`, gồm **2 `char`**.
- Writer sau cùng chứa `"prefix:YZ"`, có **9 `char`**.
- `transferTo` vẫn trả **`2L`**, không phải `9L`.

Đây là lý do không được định nghĩa API như “trả về độ dài của Writer” hoặc “trả về số ký tự tổng cộng từ khi Writer được tạo”. Nếu `Writer` ghi vào thiết bị, mạng, bộ đệm, hoặc có cơ chế biến đổi đầu ra, việc lấy độ dài dữ liệu đã giữ lại còn có thể **không khả thi**. Giá trị của `transferTo` phản ánh lần chuyển, không phải kích thước cuối cùng của một thiết bị lưu trữ.

## 8. Ký tự xuống dòng và ký tự điều khiển vẫn được tính

`Reader.transferTo` **không tách dữ liệu thành các dòng** và **không tự bỏ ký tự xuống dòng**. Nó chuyển các đơn vị `char` mà Reader cung cấp.

Với chuỗi chứa CRLF:

~~~java
String lines = "A\r\nB"; // A, CR, LF, B.

try (Reader source = new StringReader(lines);
     StringWriter target = new StringWriter()) {

    long count = source.transferTo(target);
    System.out.println(count); // 4
}
~~~

`"\r"` (carriage return) là một `char`, `"\n"` (line feed) là một `char`; hai ký tự này tạo một cặp CRLF nên tổng **hai `char`**. Thêm `A` và `B` được **4 `char`**.

Ví dụ khác:

| Chuỗi Reader cung cấp | Số `char` | Ghi chú |
| --- | --- | --- |
| `"A\nB"` | `3` | LF = 1 `char` |
| `"A\r\nB"` | `4` | CR và LF là hai `char` |
| `"\t"` | `1` | Tab là một `char` |
| `""` | `0` | Rỗng |
| `"A" + 🙂 + "B"` | `4` | Emoji bổ sung dùng hai UTF-16 code units |

Nếu một `Reader` đặc thù đã biến đổi/loại bỏ dấu xuống dòng khi cung cấp dữ liệu, `transferTo` đếm **các `char` thực sự Reader trả về**. Nó không hứa phục dựng byte gốc hoặc hình thức xuống dòng ban đầu của một file.

## 9. Chương trình Java hoàn chỉnh và output kiểm chứng

Lưu tệp **`ReaderTransferCountDemo.java`**:

~~~java
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;

public class ReaderTransferCountDemo {

    public static void main(String[] args) throws IOException {

        // 1. Chuỗi ASCII cơ bản: 7 char.
        String ascii = "Java 10";

        try (Reader source = new StringReader(ascii);
             StringWriter target = new StringWriter()) {

            long copied = source.transferTo(target);

            System.out.println("asciiCount=" + copied);
            System.out.println(
                    "asciiSame=" + ascii.equals(target.toString()));

            // Reader đã hết dữ liệu sau lần chuyển đầu.
            System.out.println(
                    "asciiSecond=" + source.transferTo(new StringWriter()));
        }

        // 2. Một Unicode code point có thể chiếm hai char UTF-16.
        String emojiText = "A"
                + new String(Character.toChars(0x1F642))
                + "B";

        try (Reader source = new StringReader(emojiText);
             StringWriter target = new StringWriter()) {

            long copied = source.transferTo(target);

            System.out.println("unicodeTransferred=" + copied);
            System.out.println("utf16Length=" + emojiText.length());
            System.out.println("codePoints="
                    + emojiText.codePointCount(0, emojiText.length()));
            System.out.println("utf8Bytes="
                    + emojiText.getBytes(StandardCharsets.UTF_8).length);
            System.out.println(
                    "unicodeSame=" + emojiText.equals(target.toString()));
        }

        // 3. Reader đã được tiêu thụ một phần,
        // Writer đã có sẵn dữ liệu.
        try (Reader source = new StringReader("XYZ");
             StringWriter target = new StringWriter()) {

            int first = source.read();
            target.write("prefix:");
            long rest = source.transferTo(target);

            System.out.println("first=" + (char) first);
            System.out.println("remainingCount=" + rest);
            System.out.println("target=" + target.toString());

            System.out.println(
                    "lastCount=" + source.transferTo(new StringWriter()));
        }

        // 4. CRLF gồm hai char.
        try (Reader source = new StringReader("A\r\nB");
             StringWriter target = new StringWriter()) {

            System.out.println(
                    "lineBreakCount=" + source.transferTo(target));
            System.out.println(
                    "lineBreakUtf16=" + target.toString().length());
        }

        // 5. Reader rỗng trả 0, không phải -1.
        try (Reader source = new StringReader("")) {
            System.out.println(
                    "emptyCount=" + source.transferTo(new StringWriter()));
        }

        // 6. Writer null là đối số không hợp lệ.
        try (Reader source = new StringReader("X")) {
            try {
                source.transferTo(null);
            } catch (NullPointerException ex) {
                System.out.println("nullWriter=NPE");
            }
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**; phương thức `Reader.transferTo` đã có từ Java 10 và ví dụ không dùng tính năng mới không cần thiết:

~~~bash
javac ReaderTransferCountDemo.java
java ReaderTransferCountDemo
~~~

**Kết quả `stdout` được kiểm thử trên JDK 24:**

~~~text
asciiCount=7
asciiSame=true
asciiSecond=0
unicodeTransferred=4
utf16Length=4
codePoints=3
utf8Bytes=6
unicodeSame=true
first=X
remainingCount=2
target=prefix:YZ
lastCount=0
lineBreakCount=4
lineBreakUtf16=4
emptyCount=0
nullWriter=NPE
~~~

Giải thích các dòng chính:

1. `asciiCount=7`: chuỗi ASCII có bảy `char`.
2. `asciiSecond=0`: Reader đã ở EOF sau lần chuyển thành công đầu tiên.
3. `unicodeTransferred=4`, `codePoints=3`, `utf8Bytes=6`: cùng một văn bản nhưng có ba cách đo **khác đơn vị**.
4. `remainingCount=2` dù Writer chứa `prefix:YZ` (chín `char`): đã đọc trước `X`, và tiền tố có sẵn không được cộng vào kết quả `transferTo`.
5. `lineBreakCount=4`: CRLF được tính hai đơn vị.
6. `emptyCount=0`: Reader trống có kết quả bình thường là không chuyển ký tự nào.
7. `nullWriter=NPE`: Writer không được `null`.

Với các trường hợp trên, output được thiết kế xác định và không phụ thuộc việc console có hiển thị được biểu tượng Unicode bổ sung hay không, vì chương trình in **số lượng** thay vì in trực tiếp emoji.

## 10. Trường hợp đặc biệt: kiểu `long` và bão hòa ở `Long.MAX_VALUE`

`Reader.transferTo` trả về `long` để biểu diễn lượng dữ liệu lớn hơn `Integer.MAX_VALUE` (2.147.483.647). Không có lý do phải ép kết quả xuống `int` chỉ vì các ví dụ nhỏ trả về số một chữ số.

Theo Javadoc hiện hành, nếu **tổng số ký tự đã chuyển** lớn hơn `Long.MAX_VALUE`, phương thức trả về **`Long.MAX_VALUE`**. Đây là cơ chế bão hòa (*saturation*) của **giá trị trả về**, không có nghĩa Reader chỉ được phép chuyển nhiều nhất `Long.MAX_VALUE` đơn vị hoặc tự cắt luồng tại đó.

~~~java
long charsTransferred = reader.transferTo(writer);
~~~

Đoạn trên minh họa trong một phương thức có `reader`/`writer` hợp lệ, đã được khai báo, và có thể ném `IOException`. Với dữ liệu thông thường, `charsTransferred` là số `char` đã chuyển chính xác. Đối với lượng dữ liệu vượt phạm vi biểu diễn của `long`, chỉ nhận được giá trị đã bão hòa theo hợp đồng.

**Không dùng `int` làm bộ đếm tùy ý cho các tập dữ liệu văn bản lớn.** Nếu một API khác nhận `int`, hãy xem có cần kiểm tra phạm vi trước khi chuyển đổi:

~~~java
if (charsTransferred > Integer.MAX_VALUE) {
    throw new IllegalStateException("Too many characters for int");
}
int safeCount = (int) charsTransferred;
~~~

Lỗi ví dụ thường gặp:

~~~java
// int count = reader.transferTo(writer); // Lỗi biên dịch
// var count = reader.transferTo(writer); // Đúng: long
~~~

## 11. Lỗi I/O: không có giá trị trả về khi chưa hoàn tất

Nếu thao tác đọc `Reader` hoặc viết `Writer` thất bại, `transferTo` có thể ném **`IOException`**. Trong trường hợp đó, lời gọi **không trả về thành công** `long` để bạn lấy “đếm bao nhiêu ký tự đã ghi được”.

~~~java
try (Reader source = ...; Writer target = ...) {
    long chars = source.transferTo(target);
    // Chỉ tới đây khi transferTo hoàn tất bình thường.
} catch (IOException ex) {
    // Ghi log/đánh giá trạng thái lỗi theo hợp đồng ứng dụng.
}
~~~

Đoạn trên là **pseudocode Java** minh họa xử lý, vì dấu `...` phải được thay bằng cách tạo Reader/Writer thực tế trước khi biên dịch.

Điều cần hiểu:

- I/O có thể thất bại **sau khi một phần dữ liệu đã được đọc hoặc viết**.
- Reader có thể **chưa ở EOF**, một hoặc cả hai luồng có thể ở trạng thái không còn nhất quán cho việc tiếp tục.
- **Không được giả định đầu ra vẫn rỗng** khi gặp lỗi.
- Javadoc khuyến nghị **đóng sớm cả hai luồng** nếu gặp lỗi I/O. `try-with-resources` giúp bảo đảm việc đóng khi thoát khối.
- Không hứa chắc việc gọi lại `transferTo` sẽ tiếp tục chính xác ở vị trí lỗi đã dừng; cách xử lý phụ thuộc nguồn, đích và khả năng khôi phục của hệ thống.

Đối số `out` phải khác `null`; truyền `null` gây **`NullPointerException`**, không phải một giá trị đếm đặc biệt.

**Không nhầm `IOException` với số `-1`:** ở một số phương thức đọc đơn ký tự, `-1` báo EOF; `transferTo` được thiết kế để chuyển đến cuối và trả số lượng thành công, hoặc ném ngoại lệ nếu thất bại.

## 12. Phương thức không tự `close` hoặc `flush`

Javadoc quy định `Reader.transferTo` **không đóng** `Reader` và **không đóng** `Writer`. Đồng thời không nên dựa vào việc nó tự `flush` dữ liệu còn nằm trong bộ đệm của Writer đích.

Ví dụ thực hành tốt:

~~~java
try (Reader reader = java.nio.file.Files.newBufferedReader(
             java.nio.file.Paths.get("input.txt"),
             java.nio.charset.StandardCharsets.UTF_8);
     Writer writer = java.nio.file.Files.newBufferedWriter(
             java.nio.file.Paths.get("output.txt"),
             java.nio.charset.StandardCharsets.UTF_8)) {

    long chars = reader.transferTo(writer);
    System.out.println("chars=" + chars);
}
// Kết thúc try-with-resources: tài nguyên được đóng tự động.
// Writer có thể đẩy dữ liệu đệm trong quá trình close theo hợp đồng của nó.
~~~

Khi `transferTo` **trả về** `chars`, điều đó không nhất thiết chứng minh rằng **toàn bộ byte đã được ghi bền vững ra đĩa**. Tầng mã hóa, buffering, hệ thống file và việc đóng/flush hoạt động theo các hợp đồng khác nhau.

Nếu ứng dụng cần xác nhận byte đã lưu, kích thước file hoặc ghi bền vững, phải xét **API của Writer/FileChannel và hệ thống lưu trữ**; chỉ số `char` không thay thế được những kiểm tra đó.

### Có nên gọi `flush()`?

Tùy Writer. Với BufferedWriter, hãy đóng bằng try-with-resources hoặc flush có chủ đích khi cần đẩy nội dung đã ghi. Nhưng đừng đưa quy tắc “Reader.transferTo luôn flush” vào chương trình — API không cam kết điều đó.

### Có nên dùng `StringWriter` với dữ liệu cực lớn?

`StringWriter` giữ nội dung trong bộ nhớ, phù hợp ví dụ và chuỗi nhỏ. Nếu đọc một luồng văn bản rất lớn từ file hay mạng, việc thu toàn bộ kết quả vào `StringWriter` có thể dùng nhiều bộ nhớ. Chuyển sang `BufferedWriter` hoặc một đích streaming thích hợp nếu mục tiêu là sao chép luồng, không cần giữ toàn bộ chuỗi trong RAM.

## 13. `transferTo` và việc đếm ký tự theo nhu cầu nghiệp vụ

Giá trị `long` của `Reader.transferTo` rất phù hợp cho:

- Thống kê bao nhiêu đơn vị `char` đã chuyển giữa các thành phần xử lý văn bản.
- Ghi số lượng hoạt động của một thao tác chuyển luồng ký tự khi đã hoàn tất thành công.
- Đối chiếu với số `char` còn lại của một `StringReader`/`CharArrayReader` biết rõ vị trí và dữ liệu.
- Đếm ký tự **sau quá trình giải mã** từ byte thành `char` qua `InputStreamReader`.

Nó **không đủ**, nếu nghiệp vụ muốn biết:

- **Số byte** đã đọc hoặc đã ghi trong một charset cụ thể.
- **Số Unicode code point** của văn bản.
- **Số grapheme cluster** người dùng nhìn thấy trên màn hình.
- **Số dòng** văn bản hoặc số từ.
- **Dung lượng đĩa** của file sau khi lưu.
- **Số ký tự còn lại trước khi chuyển** nếu chưa thực sự thực hiện thao tác chuyển.

Trong các trường hợp này, dùng công cụ đo đúng loại: `InputStream.transferTo` cho byte, `String.codePointCount` cho code point khi đã có chuỗi, hoặc các thuật toán Unicode/line-count riêng cho grapheme và dòng.

Nếu muốn vừa chuyển sang `StringWriter` vừa thống kê code point của **kết quả nhỏ**, bạn có thể thực hiện sau:

~~~java
String content = destination.toString();
int codePoints = content.codePointCount(0, content.length());
~~~

Với lượng dữ liệu lớn, đừng chuyển mọi thứ vào `StringWriter` chỉ để tính code point nếu không cần thiết; khi đó, hãy thiết kế bộ đếm luồng có xử lý cặp surrogate đúng quy tắc.

## 14. Sai lầm phổ biến và cách sửa

| Sai lầm | Vì sao sai | Cách hiểu/sửa |
| --- | --- | --- |
| “`Reader.transferTo` trả về số byte.” | Reader/Writer là API ký tự. | Đếm `char`; muốn byte dùng luồng byte/charset phù hợp. |
| “Trả về `int` giống `Reader.read()`.” | Chữ ký trả về `long`. | Khai báo `long` hoặc dùng `var`. |
| “Một emoji luôn được tính 1.” | Unicode bổ sung thường cần hai UTF-16 code units. | So sánh `String.length()` với `codePointCount`. |
| “`transferTo` đếm toàn bộ dữ liệu Reader đã từng có.” | Nó bắt đầu tại vị trí hiện tại. | Phần đã đọc trước không tính lại. |
| “Độ dài Writer sau khi ghi bằng return value.” | Writer có thể đã chứa nội dung trước đó. | Return value chỉ đếm phần được chuyển trong lần gọi. |
| “EOF trả `-1`.” | `-1` là tín hiệu của `read()`. | `transferTo` hết dữ liệu trả `0L` khi bình thường. |
| “Gặp IOException vẫn có một `long` số ký tự đã ghi dở.” | Phương thức ném ngoại lệ, không trả count thành công. | Xử lý trạng thái có thể bị ghi dở và đóng tài nguyên. |
| “`transferTo` tự đóng Reader và Writer.” | Javadoc nói rõ không đóng. | Dùng try-with-resources. |
| “Giá trị đếm nghĩa là dữ liệu đã ghi bền vững xuống đĩa.” | Buffering/encoding/lưu trữ khác với đếm ký tự. | Quản lý flush/close và xác nhận I/O nếu cần. |
| “Kết quả luôn bằng `String.length()` của toàn nguồn.” | Reader có thể đã đọc một phần hoặc bị biến đổi. | Chỉ so sánh với phần thực tế còn lại đã chuyển. |

## 15. Câu hỏi tự kiểm tra

### Bài 1 — nguồn đã đọc một ký tự

~~~java
try (Reader reader = new StringReader("ABC");
     StringWriter writer = new StringWriter()) {

    reader.read(); // Tiêu thụ A
    long chars = reader.transferTo(writer);
    System.out.println(chars);
    System.out.println(writer);
}
~~~

**Đáp án:** In `2` và `BC`. Kết quả không phải `3` vì `A` đã được đọc trước lời gọi `transferTo`.

### Bài 2 — UTF-16 so với code point

~~~java
String text = "X" + new String(Character.toChars(0x1F642)) + "Y";

try (Reader reader = new StringReader(text);
     Writer writer = new StringWriter()) {
    System.out.println(reader.transferTo(writer));
}
~~~

**Đáp án:** In `4`, do `X` và `Y` mỗi ký tự dùng một `char`, còn code point U+1F642 dùng hai `char`.

### Bài 3 — Writer đã chứa tiền tố

~~~java
try (Reader reader = new StringReader("HI");
     StringWriter writer = new StringWriter()) {

    writer.write("PRE-");
    System.out.println(reader.transferTo(writer));
    System.out.println(writer.toString().length());
}
~~~

**Đáp án:** In `2` và `6`. Chỉ có `HI` là nội dung được chuyển trong lần gọi, còn `PRE-` đã có trước.

### Bài 4 — gọi lặp sau EOF

~~~java
try (Reader reader = new StringReader("ok")) {
    System.out.println(reader.transferTo(new StringWriter()));
    System.out.println(reader.transferTo(new StringWriter()));
}
~~~

**Đáp án:** In `2` rồi `0`. Lần thứ nhất đã đọc đến EOF, lần sau không còn đơn vị `char` để chuyển.

### Bài 5 — hai overload `transferTo` khác nhau ở đơn vị nào?

**Đáp án:** `InputStream.transferTo(OutputStream)` đếm **byte**, còn `Reader.transferTo(Writer)` đếm **đơn vị `char`/UTF-16**. Dù cùng kiểu trả về `long`, không được so sánh trực tiếp hai số như thể cùng đơn vị khi văn bản có Unicode và charset nhiều byte.

### Bài 6 — khi chuyển phát sinh IOException ở giữa?

**Đáp án:** Không có giá trị `long` trả về bình thường. Một phần dữ liệu có thể đã ghi, Reader có thể chưa ở EOF và hai stream cần được đóng/xử lý theo tình huống. Không tự suy đoán rằng đầu ra rỗng hoặc có thể resume an toàn.

## 16. Tổng kết và tài liệu tham khảo

- `Reader.transferTo(Writer)` có từ **Java 10**, vẫn hoạt động và phù hợp trong Java hiện đại.
- Giá trị trả về là **`long` số ký tự đã chuyển thành công**, đơn vị là **Java `char` (UTF-16 code units)** chứ không phải byte/code point/grapheme.
- Kết quả chỉ tính **phần Reader còn lại ở vị trí hiện tại**, không cộng nội dung Writer đã có sẵn.
- Chuyển đến EOF thành công; Reader rỗng hoặc đã ở EOF trả **`0L`**.
- Khi tổng lượng chuyển vượt `Long.MAX_VALUE`, giá trị trả về **bão hòa** ở `Long.MAX_VALUE`.
- `IOException` báo lỗi đọc/ghi có thể xảy ra sau khi một phần dữ liệu đã chuyển; `NullPointerException` khi Writer là null.
- Phương thức **không tự đóng tài nguyên** và không phải hợp đồng xác nhận dữ liệu đã được flush hay lưu bền vững.

**Tài liệu chính thức:**

- [Java SE 26 — `Reader.transferTo(Writer)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/Reader.html#transferTo(java.io.Writer)) — kiểu `long`, số ký tự chuyển, EOF, bão hòa `Long.MAX_VALUE`, ngoại lệ và trách nhiệm đóng stream.
- [Java SE 26 — `String`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html) — mô hình UTF-16, `String.length()` và `codePointCount`.
- [Java SE 26 — `InputStream.transferTo(OutputStream)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/InputStream.html#transferTo(java.io.OutputStream)) — phương thức cùng tên nhưng **đếm byte**.
