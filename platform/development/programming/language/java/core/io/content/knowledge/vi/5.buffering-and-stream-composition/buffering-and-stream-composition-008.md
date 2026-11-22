# Mark, reset, markSupported và readlimit trong Java I/O

> **Bối cảnh:** Java Core I/O → **Bộ đệm và ghép luồng**. Bài này tập trung vào cơ chế **đánh dấu vị trí đọc, đọc thử và quay lại**, cách wrapper bổ sung khả năng này, sự khác nhau giữa giới hạn đọc trước theo **byte** và theo **ký tự**, cùng những giới hạn không được bỏ qua khi viết parser. Các ví dụ độc lập biên dịch được với Java 17; các API cốt lõi được trình bày đã có từ những phiên bản Java trước đó.

## 1. Tại sao phải đánh dấu rồi đọc lại?

Giả sử parser đang nhận một luồng byte, cần nhìn vài byte đầu để đoán định dạng, sau đó cho bộ xử lý chính đọc lại **từ đúng điểm vừa đánh dấu**:

1. Đặt điểm nhớ bằng `mark(readlimit)`.
2. Đọc thử một đoạn với `read(...)`.
3. Quyết định xử lý dựa trên đoạn vừa xem.
4. Nếu cần đọc lại đoạn đó, gọi `reset()` để di chuyển **vị trí đọc của chính stream đó** về điểm đánh dấu.

Đây là kiểu **lookahead**: đọc trước mà chưa coi đoạn dữ liệu đó đã bị tiêu thụ vĩnh viễn. Một số input stream chỉ đọc tuần tự, không có seek hoặc khả năng đọc lại; vì vậy **không phải mọi stream đều hỗ trợ mark/reset**. Bộ đệm có thể giữ những byte đã đọc để phát lại mà không cần quay vị trí của tệp/socket gốc.

Hãy phân biệt ngay ba việc:

- **`mark`** chỉ ghi nhớ vị trí; không trả một đối tượng bookmark, không nhân bản stream, không đọc dữ liệu.
- **`reset`** đưa vị trí về **mark gần nhất còn hợp lệ**, không mặc định về đầu stream hoặc đầu file.
- **`markSupported`** cho biết **implementation của chính stream đang dùng** có hỗ trợ giao thức mark/reset không; kiểu biến `InputStream` hay `Reader` không đủ để kết luận.

## 2. Bốn thành phần của hợp đồng API

### 2.1. `InputStream.mark(int readlimit)`

Đặt vị trí ghi nhớ trong byte-input stream. Tham số `readlimit` là **số byte tối đa được đề nghị bảo toàn để có thể reset** kể từ mark. Ví dụ `mark(8)` có nghĩa code sau đó dự định đọc trước nhiều nhất 8 byte và vẫn cần phát lại chúng.

- Phương thức này có kiểu trả về `void` và **không khai báo `throws IOException`** trong `InputStream`.
- Implementation mặc định của lớp `InputStream` cho `mark(int)` **không làm gì**. Phải kiểm tra subclass/wrapper mới biết mark có hiệu lực.
- Có thể mark nhiều lần; **mark mới thay mark trước**. Không có stack lưu nhiều vị trí để reset ngược qua nhiều mark.
- **`readlimit` không phải số lần được phép gọi `read`** và cũng không phải giới hạn tốc độ đọc. Nó là giới hạn về **khoảng dữ liệu cần có khả năng đọc lại**.
- Khi đã đọc **vượt readlimit**, implementation **không có nghĩa vụ** giữ dữ liệu để reset. Reset có thể thất bại; một số stream vẫn reset được do đặc điểm lưu trữ riêng. Đừng viết code phụ thuộc vào việc mark chắc chắn mất hiệu lực ngay ở byte thứ `readlimit + 1`.
- Đặt readlimit rất lớn có thể khiến wrapper giữ/mở rộng buffer tương ứng, tạo áp lực bộ nhớ; không thể xem đó là cơ chế rewind vô hạn.

### 2.2. `InputStream.reset()`

Đặt vị trí đọc trở về mark gần nhất (nếu còn hợp lệ). Các byte đã đọc kể từ mark có thể được phát lại theo thứ tự cũ. `reset()` khai báo `throws IOException`.

Các trường hợp cần xử lý: stream không hỗ trợ reset, chưa mark, mark bị vô hiệu, stream đã đóng hoặc lỗi I/O khác. Tùy loại stream, gọi `reset` khi chưa mark có thể trở về trạng thái mặc định riêng (như đầu nguồn bộ nhớ), nhưng **không được giả định mọi stream như vậy**.

**Reset không tạo dữ liệu mới** và cũng không đảm bảo nguồn gốc chưa thay đổi nếu có code khác thao tác với cùng tài nguyên bên dưới. Trong một pipeline đọc bình thường, chỉ thao tác thông qua **cùng một wrapper đang mark và reset**.

### 2.3. `InputStream.markSupported()`

Trả `boolean`. Hợp đồng của `InputStream` nói hỗ trợ mark/reset là thuộc tính ổn định của từng instance. Phương thức mặc định trả `false`; những subclass/wrapper phù hợp có thể trả `true`.

~~~java
// Fragment: in là một InputStream đang mở.
if (in.markSupported()) {
    in.mark(16);
    // Chỉ đọc trước trong phạm vi đã thiết kế.
    in.reset();
} else {
    // Chọn buffering, pushback, hoặc cách xử lý khác.
}
~~~

Đây là **fragment minh họa**: `in` do code xung quanh cung cấp. Trong chương trình thật vẫn cần bắt hoặc khai báo `IOException` khi `reset()`, ngay cả khi `markSupported()` là `true`: hỗ trợ không có nghĩa mọi mark đều còn hợp lệ.

### 2.4. `readlimit` là hạn mức gì?

Trong `InputStream.mark(n)`, đơn vị `n` là **byte được đọc kể từ mark**; đối với `Reader.mark(n)`, tham số được gọi là **`readAheadLimit`**, đơn vị là **ký tự theo `Reader` (UTF-16 code unit trong Java)**.

Không được coi hai tham số là số grapheme (ký tự người dùng thấy) hoặc số Unicode code point. Một emoji ngoài BMP có thể chiếm **2 code unit UTF-16**, trong khi khi encode UTF-8 sẽ chiếm **4 byte**. Khi làm parser văn bản, hãy tính read-ahead ở tầng wrapper mà parser thao tác.

**Điểm then chốt:** readlimit là phần giới hạn về độ dài dữ liệu có thể replay, không phải hạn mức **tổng số byte của stream**, không phải giới hạn `available()`, và không tự biến đọc thành non-blocking.

## 3. Những implementation thường gặp hỗ trợ hay không hỗ trợ?

| Stream/Reader | `markSupported()` thường trả | Điều cần biết |
| --- | --- | --- |
| `InputStream` mặc định | `false` | `mark` mặc định không làm gì; `reset` mặc định báo lỗi. |
| `FileInputStream` | `false` | File descriptor có vị trí, nhưng lớp stream này không cung cấp mark/reset; file seek là API khác. |
| `ByteArrayInputStream` | `true` | Nguồn đã nằm trong bộ nhớ; có thể reset về mark ngay cả khi đã đọc vượt tham số readlimit. |
| `BufferedInputStream` | `true` | Buffer có thể lưu lại byte đã đọc; readlimit quyết định mức đọc trước dự định giữ. |
| `FilterInputStream` | Phụ thuộc stream bọc bên trong | Lớp cơ sở chuyển tiếp các thao tác; subclass có thể đổi hành vi. |
| `DataInputStream` | Phụ thuộc stream bọc bên trong | Một số method đọc nhiều byte; mark trên đúng wrapper và giữ giới hạn theo số byte. |
| `PushbackInputStream` | `false` | Có `unread` để đẩy lại byte trong buffer riêng, nhưng không hỗ trợ mark/reset. |
| `InputStreamReader` | `false` | Decoder chuyển byte → ký tự; nếu cần đọc lại ký tự, thường bọc bên ngoài bằng `BufferedReader`. |
| `BufferedReader` | `true` | `mark(int readAheadLimit)` theo **số code unit/char**, có khả năng đọc lại sau reset. |
| `StringReader` và `CharArrayReader` | `true` | Dữ liệu nguồn ký tự ở bộ nhớ, có khả năng reset theo cơ chế riêng. |
| `PushbackReader` | `false` | Dùng `unread` thay cho mark/reset. |

Bảng thể hiện hành vi API chuẩn của những lớp phổ biến, không thay thế việc đọc tài liệu subclass cụ thể hoặc gọi `markSupported()` khi đầu vào là một stream bất kỳ do bên thứ ba cung cấp.

### 3.1. Wrapper thay đổi điều gì?

~~~text
FileInputStream [markSupported = false]
          |
          v
BufferedInputStream [markSupported = true]
          |
          v
Parser nhận BufferedInputStream, không đọc trực tiếp FileInputStream
~~~

`BufferedInputStream` giữ các byte đã đọc trong buffer khi cần. Vì vậy, dù `FileInputStream` không hỗ trợ mark, wrapper có thể tự hỗ trợ mà **không đòi nguồn gốc phải có khả năng quay lại**.

Tránh giữ cả hai biến rồi đọc xen kẽ:

~~~java
// Fragment sai về thiết kế: source và buffered cùng chia một nguồn dữ liệu.
InputStream source = /* nguồn từ caller */;
BufferedInputStream buffered = new BufferedInputStream(source);
buffered.mark(8);
int peek = buffered.read();
int next = source.read(); // Không đọc trực tiếp source sau khi đã bọc!
// buffered.reset() không thể khôi phục một cách đúng đắn hai con trỏ đọc.
~~~

Bộ đệm có thể đã kéo thêm byte từ `source` trước thời điểm caller đọc trực tiếp. Quy tắc đúng: tạo wrapper một lần và chuyển wrapper đó cho toàn bộ code tiêu thụ nguồn. `close()` wrapper thường đóng cả nguồn bên trong; quản lý ownership để tránh đóng sớm hoặc đóng lặp do cấu trúc vòng đời rối.

## 4. Ví dụ chạy được: đọc thử rồi phát lại byte

Tạo tệp **`MarkByteDemo.java`**:

~~~java
import java.io.BufferedInputStream;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class MarkByteDemo {
    public static void main(String[] args) throws IOException {
        byte[] data = "ABCDE".getBytes(StandardCharsets.US_ASCII);

        // bufferSize = 2 để thấy mark/reset hoạt động dù buffer nhỏ.
        try (InputStream in = new BufferedInputStream(
                new ByteArrayInputStream(data), 2)) {

            System.out.println("supported=" + in.markSupported());
            System.out.println("first=" + (char) in.read()); // A

            in.mark(3); // Đánh dấu trước B, dự định nhìn tối đa 3 byte.
            System.out.println("peek=" + (char) in.read()
                    + "" + (char) in.read());             // BC

            in.reset(); // Quay về trước B.
            System.out.println("replay=" + (char) in.read()
                    + "" + (char) in.read());             // BC
        }
    }
}
~~~

Chạy bằng Java 17 (mã cũng dùng API Java cũ):

~~~bash
javac MarkByteDemo.java
java MarkByteDemo
~~~

Stdout:

~~~text
supported=true
first=A
peek=BC
replay=BC
~~~

**Giải thích từng bước:** Con trỏ ban đầu trước `A`. Sau `read()` đầu, con trỏ đứng trước `B`. `mark(3)` lưu vị trí này; hai lần đọc cho `B` và `C`. `reset()` đưa con trỏ logic về `B`, nên hai lần đọc tiếp phát lại `BC`. Không có byte mới được thêm vào nguồn. Kích thước buffer khởi tạo **2** không ngăn việc mark với `readlimit=3`: wrapper có thể giữ/mở rộng phần dữ liệu thích hợp khi cần.

Biểu thức `"peek=" + (char)in.read() + "" + (char)in.read()` cố ý bắt đầu bằng **String**, vì cộng trực tiếp hai giá trị `char` có thể tạo phép cộng số nguyên thay vì ghép chuỗi. Đặc biệt nếu tệp chứa byte UTF-8 nhiều byte/ký tự, ép `(char) in.read()` từng byte **không phải decoder văn bản đúng**. Demo sử dụng ASCII để minh họa vị trí byte, không dùng thủ thuật đó làm parser Unicode.

## 5. Ví dụ phản ví dụ: `readlimit` không phải quy tắc hủy mark ngay lập tức

Tạo **`MemoryMarkDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.IOException;

public class MemoryMarkDemo {
    public static void main(String[] args) throws IOException {
        byte[] values = {10, 20, 30, 40};

        try (ByteArrayInputStream in = new ByteArrayInputStream(values)) {
            System.out.println("supported=" + in.markSupported());

            in.mark(1); // Yêu cầu đọc trước 1 byte.
            System.out.println(in.read()); // 10
            System.out.println(in.read()); // 20
            System.out.println(in.read()); // 30

            in.reset(); // Vẫn hoạt động với ByteArrayInputStream.
            System.out.println("afterReset=" + in.read()); // 10
        }
    }
}
~~~

~~~bash
javac MemoryMarkDemo.java
java MemoryMarkDemo
~~~

Stdout:

~~~text
supported=true
10
20
30
afterReset=10
~~~

Đã đọc **3 byte sau `mark(1)`**, nhưng `ByteArrayInputStream` vẫn nhớ vị trí vì toàn bộ dữ liệu có sẵn trong bộ nhớ và implementation này không dùng `readlimit` để xóa mark. Hợp đồng chung chỉ nói stream **không bắt buộc** nhớ đủ khi vượt giới hạn. Vì vậy:

- **Không** viết unit test chung kiểu “đọc `readlimit + 1` byte thì `reset` bắt buộc ném `IOException`”.
- **Không** suy ra `readlimit` là lượng bộ nhớ dùng bởi mọi implementation.
- Nếu parser **phải** đọc lại N byte, chọn implementation có contract phù hợp, đặt readlimit bao phủ phần đọc trước và xử lý `IOException` khi cần.

Với `BufferedInputStream`, mark có thể bị vô hiệu nếu dữ liệu cần giữ vượt giới hạn và buffer phải bỏ vùng cũ. Việc thất bại ở thao tác cụ thể nào tùy trạng thái buffer và hợp đồng API; đừng xây logic nghiệp vụ dựa trên thời điểm nội bộ giải phóng bộ đệm.

## 6. Cách `BufferedInputStream` sử dụng buffer khi mark

Không có mark, `BufferedInputStream` được phép tiêu thụ dữ liệu từ nguồn thành từng khối và bỏ những byte đã phục vụ, giúp giảm số lời gọi I/O xuống nguồn. Khi có mark:

1. `mark(readlimit)` lưu **vị trí logic** hiện tại trong bộ đệm.
2. Đọc tiếp có thể lấy byte từ buffer, refill từ nguồn hoặc di chuyển phần dữ liệu đang cần giữ.
3. Khi còn cần reset, wrapper bảo toàn vùng từ mark tới vị trí đọc; một buffer nhỏ có thể được mở rộng để đáp ứng readlimit trong trường hợp cần.
4. Khi việc duy trì mark không còn nằm trong giới hạn, wrapper được phép bỏ mark/vùng cũ để hoạt động hiệu quả.
5. `reset` hợp lệ chỉ di chuyển vị trí đọc logic trong dữ liệu giữ lại; không nhất thiết đổi vị trí thật của file/socket bên dưới.

Điều này giải thích vì sao một mark với readlimit lớn trên luồng dữ liệu dài có thể làm tăng bộ nhớ. **`new BufferedInputStream(source, 8192)` không hề có nghĩa toàn bộ lookahead bị giới hạn tuyệt đối ở 8192 byte**, đồng thời `mark(1_000_000)` cũng **không đảm bảo** chính xác 1 MB sẽ được cấp phát ngay khi mark. Các cấu trúc nội bộ là chi tiết implementation; điều nên thiết kế là **N byte thực sự có thể cần replay**.

Nếu chỉ muốn xem 4 hoặc 8 byte header, truyền readlimit hợp lý thay vì `Integer.MAX_VALUE`. Nếu phải random access trên file lớn, cân nhắc `FileChannel.position(...)` hoặc `RandomAccessFile.seek(...)`, hoặc parser lưu header theo cấu trúc riêng: mark/reset không phải cơ chế tìm kiếm dữ liệu tùy ý.

## 7. `BufferedReader.mark(readAheadLimit)`: đơn vị là ký tự

`Reader` xử lý dữ liệu đã giải mã thành ký tự, nên phương thức `mark(int readAheadLimit)` tính giới hạn theo **char/UTF-16 code unit** mà `Reader` phát ra. Khác với `InputStream.mark`, khai báo của `Reader.mark` có thể **ném `IOException`**. `BufferedReader` hỗ trợ mark/reset và có thể mở rộng buffer để giữ phần read-ahead.

Tạo tệp **`MarkReaderDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class MarkReaderDemo {
    public static void main(String[] args) throws IOException {
        // Chuỗi có A + emoji supplementary U+1F642 + B.
        try (BufferedReader reader =
                new BufferedReader(new StringReader("A\uD83D\uDE42B"))) {
            System.out.println("supported=" + reader.markSupported());

            reader.mark(3); // 3 UTF-16 code unit, không phải 3 glyph.
            System.out.println("first=" + (char) reader.read()); // A

            char high = (char) reader.read();
            char low = (char) reader.read();
            System.out.println("high=" + Character.isHighSurrogate(high));
            System.out.println("low=" + Character.isLowSurrogate(low));

            reader.reset();
            System.out.println("replay=" + (char) reader.read());
        }
    }
}
~~~

~~~bash
javac MarkReaderDemo.java
java MarkReaderDemo
~~~

Stdout:

~~~text
supported=true
first=A
high=true
low=true
replay=A
~~~

Một code point emoji ngoài BMP dùng **hai** `char`. Khi `BufferedReader` đọc 3 lần `read()` trong ví dụ, đã tiêu thụ 3 code unit (A + high surrogate + low surrogate), dù người dùng nhìn thấy hai ký tự. `readAheadLimit=3` được chọn đúng cho số `char` cần replay.

Nếu nguồn là byte từ mạng/tệp, cấu trúc thường là:

~~~java
// Fragment: source là InputStream do caller cung cấp.
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(source, StandardCharsets.UTF_8))) {
    if (reader.markSupported()) {
        reader.mark(64); // 64 đơn vị char ở tầng reader.
        // Đọc ký tự...
        reader.reset();
    }
}
~~~

Fragment cần import `java.io.BufferedReader`, `java.io.InputStreamReader`, `java.nio.charset.StandardCharsets` và nằm trong method xử lý `IOException`. Hãy mark **trên BufferedReader**, vì `InputStreamReader` thường không hỗ trợ mark. Đừng reset stream byte bên dưới khi `InputStreamReader` đã đọc trước byte để giải mã; trạng thái decoder và buffer có thể không còn đồng bộ.

### 7.1. `BufferedReader.mark(0)` và điều kiện đầu vào

`BufferedReader.mark(readAheadLimit)` có thể ném `IllegalArgumentException` nếu `readAheadLimit` âm. `0` hợp lệ về đối số nhưng **không nên dùng làm cam kết phát lại một ký tự**: nếu cần đọc trước N ký tự, hãy đặt giới hạn đủ N và xử lý lỗi khi reset. Với `BufferedInputStream.mark(readlimit)`, hợp đồng chung không cho phép suy luận giống hệt về cách xử lý các giá trị bất thường; gọi theo dữ liệu hợp lệ đã tính rõ.

Đừng nhầm bộ đệm char trong `BufferedReader` với buffer byte trong `BufferedInputStream`: cùng là caching nhưng nằm ở **hai tầng khác nhau**. Khi ghép lớp, trách nhiệm cấp limit thuộc tầng mà parser đọc.

## 8. Mark sau khi `readLine` hoặc `skip`: còn tính không?

**Có thể có.** Mark/reset phụ thuộc lượng dữ liệu đã đọc sau mark và implementation, không chỉ số lần gọi `read()`.

- `BufferedReader.readLine()` đọc ký tự tới hết dòng và thường tiêu thụ dấu kết thúc dòng; `readAheadLimit` phải tính cả phần ký tự được **tiêu thụ**, kể cả ký tự newline vốn không có trong `String` kết quả. Kết thúc dòng Windows `\r\n` có hai code unit.
- `skip(n)` cũng di chuyển vị trí đọc; theo hợp đồng cụ thể, thao tác skip có thể tiêu thụ dữ liệu cần được giữ để reset. Không giả định “skip không tính”.
- `InputStream.read(byte[])` có thể đọc ít hơn số byte yêu cầu; lượng được **đọc thật** mới quan trọng. Với `DataInputStream.readInt()`, một số nguyên được diễn giải từ **4 byte**, không phải 1 “ký tự”; readlimit thuộc byte layer.
- `InputStream.readAllBytes()` hoặc `transferTo(...)` có thể tiêu thụ cả phần dữ liệu còn lại; đặt mark với readlimit nhỏ trước một thao tác tiêu thụ không giới hạn có thể làm reset không còn khả dụng.

Đối với parser nhận dạng header, hãy đọc **số byte cố định** có giới hạn rõ, không dựa vào `available()`: `available()` chỉ ước lượng số byte có thể đọc/skip mà không blocking, **không phải độ dài toàn bộ stream**.

## 9. Mẫu lookahead an toàn theo chiều xử lý

### 9.1. Byte header hữu hạn

~~~java
// Fragment bên trong method có thể ném IOException.
// source là InputStream chưa bị tiêu thụ bên ngoài wrapper.
try (BufferedInputStream in = new BufferedInputStream(source)) {
    if (!in.markSupported()) {
        throw new IllegalStateException("Missing mark/reset");
    }

    in.mark(4);
    int b1 = in.read();
    int b2 = in.read();
    // b1/b2 có thể bằng -1; kiểm tra EOF trước khi so header.
    boolean gzip = b1 == 0x1F && b2 == 0x8B;
    in.reset();

    if (gzip) {
        // Truyền 'in' cho tầng xử lý gzip phù hợp.
    } else {
        // Truyền 'in' cho tầng xử lý định dạng khác.
    }
}
~~~

Đây là **fragment**, không phải chương trình độc lập. Giới hạn 4 byte đủ cho hai lần đọc thử; nếu muốn nhận dạng thêm nhiều định dạng, tính lại N và số byte thực đọc. Việc parser thực thi đúng còn cần xử lý EOF, các bộ đọc hợp lệ và ownership của stream được truyền. Nếu `reset()` lỗi, **không được bỏ qua rồi tiếp tục coi con trỏ chưa bị thay đổi**.

### 9.2. Chỉ cần đọc lại một số byte: `PushbackInputStream`

`PushbackInputStream` có thể `unread(byte)` hoặc `unread(byte[],...)` để đẩy lại byte vào pushback buffer. Nó thích hợp khi bạn đã đọc một prefix nhỏ và muốn trả đúng prefix đó cho consumer, nhưng `markSupported()` vẫn là **false**.

~~~java
// Fragment: source là InputStream; try-with-resources quản lý tài nguyên.
try (PushbackInputStream in = new PushbackInputStream(source, 2)) {
    int first = in.read();
    if (first != -1) {
        in.unread(first); // Lần read kế tiếp sẽ trả cùng byte.
    }
    // Xử lý tiếp với 'in', không đổi sang 'source'.
}
~~~

Fragment cần import `java.io.PushbackInputStream`, khai báo/bắt `IOException`, và không được `unread(-1)` khi EOF. Độ lớn pushback buffer phải đủ dữ liệu trả lại; nếu quá sức chứa, `unread` ném `IOException`. Pushback không tương đương mark/reset nhiều lượt: nó đặt dữ liệu cụ thể về trước vị trí đọc, không đưa con trỏ về một bookmark được lưu.

### 9.3. Cần seek tùy ý trên file

- `RandomAccessFile.seek(long)` hoặc `FileChannel.position(long)` cho phép đặt vị trí trên **file/channel** hỗ trợ random access; đây là cơ chế khác với `InputStream.mark/reset`.
- Một file có thể được mở lại và bỏ qua phần đầu để đọc lại, nhưng không hiệu quả cho tệp lớn và không chắc phản ánh cùng snapshot nếu file bị thay đổi.
- Socket stream thường không thể seek; nếu cần đọc lại, dùng buffering, pushback hoặc tự lưu lượng header hữu hạn. Nếu phải rewind dữ liệu không giới hạn, cần thiết kế spool ra bộ nhớ/tệp tạm có giới hạn và phương án cleanup.

## 10. Các kiểu lỗi và xử lý hợp lý

| Tình huống | Kết quả có thể gặp | Cách xử lý |
| --- | --- | --- |
| `markSupported() == false` | `mark` có thể bị bỏ qua, `reset` ném `IOException` | Dùng wrapper hỗ trợ, pushback hoặc cấu trúc dữ liệu khác. |
| Gọi `reset` trước `mark` | Tùy implementation: lỗi hoặc trạng thái mặc định riêng | Mark trước khi đọc thử, không dựa vào mặc định. |
| Đọc vượt `readlimit` | Mark có thể bị vô hiệu; một số implementation vẫn cho reset | Chọn limit đủ cho lookahead; không coi giới hạn là điểm hủy tuyệt đối. |
| Mark/Reset sau `close()` | Lỗi I/O hoặc mark không có tác dụng tùy hợp đồng class | Giữ stream mở trong toàn bộ giao dịch đọc thử và đọc chính. |
| `BufferedReader.mark(-1)` | `IllegalArgumentException` | Kiểm tra số ký tự cần đọc trước, không dùng số âm. |
| Nhiều lần `mark` | Mark gần nhất thay mark trước | Chỉ thiết kế một mốc hiện hành hoặc tự lưu dữ liệu cho nested backtracking. |
| Mark trên một wrapper nhưng đọc source trực tiếp | Cursor logic và dữ liệu buffer mất đồng bộ | Chỉ để một consumer dùng wrapper đã chọn. |
| Đọc UTF-8 raw byte rồi cắt giữa sequence | Ký tự lỗi nếu decode từng đoạn | Decode bằng Reader có trạng thái; mark ở tầng ký tự khi parser làm việc với text. |
| `readLine` bỏ newline khỏi kết quả | Đếm limit thiếu ký tự `\n` hay `\r\n` đã tiêu thụ | Dành readAheadLimit theo code unit thực đọc, gồm dấu dòng. |
| `mark(Integer.MAX_VALUE)` cho mọi nguồn | Wrapper có thể giữ buffer rất lớn | Giới hạn protocol rõ ràng, chặn input không tin cậy và chọn chiến lược seek/spool phù hợp. |

**Nguyên tắc bắt lỗi:** `markSupported()` chỉ xác nhận capability của loại stream; nó **không loại bỏ** ngoại lệ khi `reset()`, `read()` hay đóng stream. Trong parser, thất bại rewind thường khiến bạn **không còn ở vị trí dự định**; chuyển sang luồng xử lý bình thường mà không sửa con trỏ là bug.

## 11. Phân biệt mark/reset với các API dễ nhầm

| Cơ chế | Điểm giống | Khác biệt cốt lõi |
| --- | --- | --- |
| `mark` + `reset` | Đọc thử và quay về mốc | Mốc logic gần nhất, replay có điều kiện theo stream và readlimit. |
| `PushbackInputStream.unread` | Cung cấp lại byte đã tiêu thụ | Caller chủ động đẩy **byte cụ thể** vào buffer, giới hạn bởi pushback capacity. |
| `FileChannel.position` / `RandomAccessFile.seek` | Có thể đọc lại từ vị trí trước | Dựa vào nguồn có random access, không bị giới hạn bởi readlimit kiểu stream. |
| `BufferedInputStream` | Caching byte làm giảm I/O tới nguồn | Buffering không đồng nghĩa vô hạn rewind; mark có điều kiện riêng. |
| `BufferedReader` | Caching dữ liệu text đã decode | Mark theo char code unit, không theo số byte của encoding. |
| `available()` | Hỏi về dữ liệu sẵn ngay | Không trả vị trí, không đặt mark, không báo chiều dài đầy đủ. |
| `skip(long)` | Di chuyển vị trí đọc tới trước | Không đặt bookmark; số thực skip có thể nhỏ hơn yêu cầu. |
| `InputStream.transferTo` | Đưa byte sang output | Tiêu thụ stream, không có cam kết reset sau đó. |

## 12. Câu hỏi tự kiểm tra

1. `FileInputStream` trả `markSupported() == false`. Bọc bằng `BufferedInputStream` có thể làm mark/reset hoạt động không? Vì sao?
2. Bạn mark với `readlimit = 5`, đọc 7 byte rồi reset thành công ở `ByteArrayInputStream`. Điều này có vi phạm contract không?
3. `reset()` di chuyển về đầu tệp hay vị trí gọi `mark` gần nhất?
4. Parser dùng `BufferedReader` và đọc emoji ngoài BMP sau mark. Một emoji thường tiêu thụ bao nhiêu đơn vị `char`?
5. Vì sao `readAheadLimit=10` không luôn đủ để `readLine()` lấy chuỗi kết quả dài 10 ký tự?
6. Nếu người khác đọc trực tiếp `FileInputStream` trong lúc bạn mark trên `BufferedInputStream` của nó, điều gì có thể sai?
7. Khi cần trả lại đúng 2 byte header nhưng source không hỗ trợ mark, còn những lựa chọn nào?
8. Có thể dựa vào việc đọc byte thứ `readlimit + 1` để khẳng định mọi `reset` sẽ ném lỗi không?

**Gợi ý đáp án:**

1. **Có**; wrapper giữ byte đã đọc để phát lại mà không đòi nguồn file tự seek.
2. **Không**; readlimit là ngưỡng mà sau đó stream không còn bắt buộc giữ mark, không phải lệnh bắt buộc xóa mark.
3. Trở về mark gần nhất còn hợp lệ, không tự động về đầu.
4. Thường **hai** UTF-16 code unit (`char`), dù là một code point.
5. `readLine()` còn có thể tiêu thụ `\n` hoặc `\r\n` mà không trả trong chuỗi kết quả.
6. Hai tầng không còn chia sẻ vị trí logic nhất quán; buffer có thể đã đọc trước dữ liệu của source.
7. `BufferedInputStream` + mark/reset, `PushbackInputStream` + `unread`, hoặc lưu prefix riêng rồi phối hợp reader.
8. **Không**; mark có thể còn sử dụng được tùy implementation và trạng thái.

## 13. Tài liệu API chuẩn

- [`InputStream` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStream.html): `mark(int)`, `reset()`, `markSupported()` và giới hạn contract của `readlimit`.
- [`BufferedInputStream` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/BufferedInputStream.html): buffering, mark vị trí logic, điều kiện làm mất mark.
- [`ByteArrayInputStream` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ByteArrayInputStream.html): stream trong bộ nhớ, mark/reset luôn được hỗ trợ.
- [`BufferedReader` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/BufferedReader.html): `mark(int readAheadLimit)` và tính chất mark theo ký tự.
- [`Reader` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Reader.html): contract chung của reader, `mark` và `reset`.
- [`PushbackInputStream` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/PushbackInputStream.html): `unread` và `markSupported() == false`.

**Ghi nhớ:** kiểm tra `markSupported()` trên **đúng đối tượng** đang được đọc; `mark(N)` trước khi lookahead, đảm bảo N tính theo đúng đơn vị và đủ cho đoạn cần phát lại; `reset()` có thể ném `IOException`; không đọc xen kẽ bên dưới wrapper và không dùng mark/reset làm random access không giới hạn.