# `ByteArrayOutputStream.toString(Charset)` — Giải mã dữ liệu byte bằng bảng mã tường minh

**Chủ đề:** Charset trong I/O — Java 10 trở lên.

`ByteArrayOutputStream.toString(Charset)` chuyển **các byte hiện có trong bộ đệm của `ByteArrayOutputStream`** thành một đối tượng `String` bằng cách **giải mã theo `Charset` được chỉ định**. Overload nhận `Charset` xuất hiện từ **Java 10** và vẫn còn được hỗ trợ trong Java hiện đại. Ưu điểm lớn nhất là người đọc mã nhìn thấy ngay bảng mã được sử dụng, không phải đoán theo môi trường máy chạy.

Bài học tập trung vào kiểu dữ liệu, quy trình mã hóa/giải mã, trường hợp byte không hợp lệ, so sánh các overload, vòng đời bộ đệm, kết hợp `OutputStreamWriter` và cách tránh lỗi khi dữ liệu đến thành nhiều phần. Có **năm chương trình Java độc lập**, được kiểm tra biên dịch với `javac --release 10` và chạy với stdout cụ thể.

## 1. API, kiểu dữ liệu và hợp đồng

Khai báo phương thức:

~~~java
public String toString(Charset charset)
~~~

- **Lớp:** `java.io.ByteArrayOutputStream`, một `OutputStream` lưu dữ liệu dạng **byte** trong bộ nhớ.
- **Tham số:** `java.nio.charset.Charset`, ví dụ `StandardCharsets.UTF_8` hoặc `StandardCharsets.ISO_8859_1`.
- **Kết quả:** `java.lang.String` chứa các ký tự thu được khi giải mã **toàn bộ các byte hiện có** của stream.
- **Khi `charset == null`:** ném `NullPointerException`.
- **Khi byte đầu vào sai định dạng hoặc chứa chuỗi byte không thể ánh xạ:** phương thức **dùng chuỗi ký tự thay thế mặc định của Charset** thay vì bắt caller tự xử lý ngoại lệ giải mã. Nếu muốn từ chối byte không hợp lệ hoặc kiểm soát cách thay thế, dùng `CharsetDecoder`.
- **Không có checked `UnsupportedEncodingException` trên overload này:** đối tượng `Charset` đã được cung cấp trực tiếp thay vì truyền một tên bảng mã dạng `String`.
- **Không tự thay đổi bộ đệm:** gọi `toString(Charset)` không xóa byte, không reset, không đóng stream, và không ghi/biến đổi lại bytes đang có.
- **Không phải API lấy bytes:** muốn bytes gốc, dùng `size()` và `toByteArray()`; `toString(Charset)` trả **text đã giải mã**.

Ví dụ ngắn trong một phương thức:

~~~java
ByteArrayOutputStream output = new ByteArrayOutputStream();
output.write("Java".getBytes(StandardCharsets.UTF_8));

String text = output.toString(StandardCharsets.UTF_8);
System.out.println(text); // Java
~~~

Đoạn trên cần import `ByteArrayOutputStream` và `StandardCharsets`; thuộc một phương thức có xử lý `IOException` nếu cần. Vì chữ `"Java"` chỉ chứa ASCII, nhiều bảng mã cũng có thể giải ra cùng ký tự; hãy dùng dữ liệu Unicode khi cần kiểm tra **đúng Charset**.

### Dòng dữ liệu là chuyển đổi **byte sang ký tự**

~~~text
String (ký tự Unicode)
   | getBytes(StandardCharsets.UTF_8) — MÃ HÓA
   v
byte[] (UTF-8)
   | ByteArrayOutputStream.write(byte[])
   v
ByteArrayOutputStream [các byte chưa được giải mã]
   | toString(StandardCharsets.UTF_8) — GIẢI MÃ
   v
String (ký tự Unicode)
~~~

`write(byte[])` chỉ chép **các byte** vào stream. Nó không đọc ngữ nghĩa văn bản và **không biết bytes thuộc UTF-8 hay ISO-8859-1**. Bảng mã chỉ có ý nghĩa khi một bước chuyển giữa byte và ký tự được thực hiện.

**Quy tắc cơ bản:** bảng mã khi **giải mã** phải tương thích với bảng mã đã dùng để **mã hóa**. Nếu dữ liệu ban đầu là UTF-8, dùng `toString(StandardCharsets.UTF_8)`; đổi sang bảng mã khác không “tự sửa” bytes mà chỉ diễn giải chúng theo quy tắc khác.

## 2. Hiểu đúng `size()`, `String.length()` và code point

Với văn bản Unicode, ba đại lượng không nhất thiết bằng nhau:

| Đại lượng | API thường dùng | Đơn vị đếm | Ví dụ văn bản `Aé🚀` |
| --- | --- | --- | --- |
| Số byte UTF-8 | `output.size()` hoặc `getBytes(UTF_8).length` | Byte | **7** |
| Độ dài Java String | `text.length()` | Đơn vị `char` UTF-16 | **4** |
| Số Unicode code point | `text.codePointCount(0, text.length())` | Code point | **3** |

Giải thích cho `Aé🚀`:

- `A` có 1 byte trong UTF-8 và 1 `char` UTF-16.
- `é` (U+00E9) có 2 byte UTF-8 và 1 `char` UTF-16.
- `🚀` (U+1F680) có 4 byte UTF-8 và chiếm **2 `char` UTF-16** (một surrogate pair).
- Tổng: 1 + 2 + 4 = **7 bytes**, 1 + 1 + 2 = **4 đơn vị `char`**, **3 code point**.

Vì vậy, **không** dùng `output.size()` để khẳng định số ký tự văn bản, và **không** dùng `String.length()` để dự đoán số byte lưu file hoặc gửi mạng. Với một charset khác, độ dài byte có thể khác dù chuỗi `String` vẫn giống hệt.

## 3. Chương trình chạy được 1 — Giải mã UTF-8 và trả về String độc lập

Lưu **`ExplicitCharsetDemo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class ExplicitCharsetDemo {
    public static void main(String[] args) throws IOException {
        String original = "A\u00E9\uD83D\uDE80";
        byte[] encoded = original.getBytes(StandardCharsets.UTF_8);

        ByteArrayOutputStream out = new ByteArrayOutputStream();
        out.write(encoded);

        String decoded = out.toString(StandardCharsets.UTF_8);
        System.out.println("equal=" + original.equals(decoded));
        System.out.println("bytes=" + out.size());
        System.out.println("chars=" + decoded.length());
        System.out.println("codepoints=" +
                decoded.codePointCount(0, decoded.length()));
        System.out.println("same-as-new-String=" +
                decoded.equals(new String(
                        out.toByteArray(), StandardCharsets.UTF_8)));

        out.write(33);
        System.out.println("snapshot-still-equal=" + decoded.equals(original));
        System.out.println("updated-suffix=" +
                out.toString(StandardCharsets.UTF_8).endsWith("!"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 10 ExplicitCharsetDemo.java
java ExplicitCharsetDemo
~~~

**Stdout chính xác:**

~~~text
equal=true
bytes=7
chars=4
codepoints=3
same-as-new-String=true
snapshot-still-equal=true
updated-suffix=true
~~~

Điều chương trình chứng minh:

1. Dùng `getBytes(UTF_8)` để mã hóa và `toString(UTF_8)` để giải mã thu lại cùng nội dung. Việc dùng ký tự `é` và emoji đảm bảo thử nghiệm không chỉ là ASCII.
2. `size()` đếm bytes (7), trong khi độ dài `String` là 4 `char` và có 3 code point.
3. `new String(out.toByteArray(), StandardCharsets.UTF_8)` cho **nội dung** giống `out.toString(StandardCharsets.UTF_8)` khi giải mã cùng bytes theo cùng charset. Phương án `toByteArray` tạo bản sao byte[] trung gian, không cần thiết nếu mục tiêu duy nhất là tạo String.
4. `decoded` là `String` đã trả về tại thời điểm giải mã. Khi `out.write(33)` thêm byte `!`, `decoded` **không tự thay đổi**, còn lần `toString(UTF_8)` tiếp theo quan sát bytes mới.
5. `toString(Charset)` không có tác dụng reset stream; nội dung byte cũ vẫn tồn tại cho tới khi gọi `reset()` hoặc ngừng sử dụng instance.

**Lưu ý về cú pháp Unicode:** trong tệp nguồn, `\u00E9` và cặp `\uD83D\uDE80` được Java hiểu thành `é` và emoji. Việc dùng escape trong ví dụ giúp file nguồn dễ chạy ở nhiều môi trường console và vẫn cho cùng kết quả xác nhận.

## 4. So sánh bốn cách chuyển bytes sang văn bản

| Cách viết | Charset dùng để giải mã | Xử lý lỗi tên charset | Khi nên dùng |
| --- | --- | --- | --- |
| `out.toString(StandardCharsets.UTF_8)` | UTF-8 chỉ định tường minh | Không cần tra tên; không có checked `UnsupportedEncodingException` | **Ưu tiên** khi đã có `ByteArrayOutputStream`, Java 10+ |
| `out.toString()` | Charset mặc định của runtime | Không nhận tham số | Chỉ khi định dạng dữ liệu **cố ý** phụ thuộc charset mặc định |
| `out.toString("UTF-8")` | Charset được tìm theo tên `String` | Khai báo `throws UnsupportedEncodingException` | Tương thích code/API sử dụng tên bảng mã; thường kém rõ hơn object `Charset` |
| `new String(out.toByteArray(), StandardCharsets.UTF_8)` | UTF-8 chỉ định tường minh | Không có checked `UnsupportedEncodingException` | Khi cũng cần xử lý/cất riêng byte[] hoặc không dùng overload của BAOS |

### Vì sao nên tránh dựa vào `toString()` không tham số?

`toString()` dùng charset mặc định của môi trường chạy. Một số phiên bản và cấu hình JVM có quy tắc mặc định khác nhau; Java hiện đại thường mặc định UTF-8 nhưng ứng dụng vẫn có thể có những ngữ cảnh/cấu hình đặc biệt. Mã giao tiếp với HTTP, file, database, API hoặc protocol thường phải tuân theo **charset của dữ liệu**, chứ không phải đoán theo charset của máy.

Ví dụ, bytes vốn mã hóa ISO-8859-1 nhưng được đọc theo UTF-8 có thể tạo ký tự thay thế hoặc nội dung sai. Vì vậy trong mã cần tái lập kết quả và không phụ thuộc môi trường, nên chỉ định `StandardCharsets.UTF_8` hoặc Charset do protocol/metadata quy định.

### `toString(String)` và `toString(Charset)` không giống nhau về chữ ký

~~~java
String a = out.toString(StandardCharsets.UTF_8);
String b = out.toString("UTF-8");
~~~

Đây là hai dòng minh họa khi `out` là BAOS, đặt trong phương thức xử lý được checked exception của overload thứ hai. Nội dung `a` và `b` **giống nhau** nếu dùng đúng cùng charset và bytes. Nhưng overload nhận chuỗi tên bảng mã có thể phải xử lý `UnsupportedEncodingException`; overload nhận object `Charset` thì không có checked exception đó.

Trong Java 10+, dùng hằng `StandardCharsets.UTF_8` làm rõ hợp đồng và tránh lỗi chính tả của tên bảng mã. Nếu charset đến từ cấu hình động, hãy xác nhận/validate tên và hỗ trợ theo cơ chế `Charset` thích hợp, thay vì giả định mọi tên do người dùng nhập đều hợp lệ.

**Lưu ý overload và null:** `out.toString((Charset) null)` ném `NullPointerException`. Với code có overload nhận cả `String` và `Charset`, truyền literal `null` không kèm ép kiểu có thể gây **lời gọi mơ hồ lúc biên dịch**; không dùng `null` để biểu diễn “dùng charset mặc định”. Hãy chủ động gọi `toString()` nếu đúng là muốn default, hoặc chọn `Charset` cụ thể.

## 5. Chương trình chạy được 2 — Dùng sai Charset và so sánh overload

Lưu **`CharsetChoiceDemo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.UnsupportedEncodingException;
import java.nio.charset.StandardCharsets;

public class CharsetChoiceDemo {
    public static void main(String[] args) throws Exception {
        String original = "caf\u00E9";
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        out.write(original.getBytes(StandardCharsets.ISO_8859_1));

        String correct = out.toString(StandardCharsets.ISO_8859_1);
        String wrong = out.toString(StandardCharsets.UTF_8);

        System.out.println("correct=" + correct.equals(original));
        System.out.println("wrong-equal=" + wrong.equals(original));
        System.out.println("wrong-has-replacement=" +
                wrong.contains("\uFFFD"));
        System.out.println("named-equivalent=" +
                correct.equals(out.toString("ISO-8859-1")));

        try {
            out.toString("NOT-A-REAL-CHARSET");
        } catch (UnsupportedEncodingException expected) {
            System.out.println("invalid-name=UnsupportedEncodingException");
        }

        try {
            out.toString((java.nio.charset.Charset) null);
        } catch (NullPointerException expected) {
            System.out.println("null-charset=NullPointerException");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 10 CharsetChoiceDemo.java
java CharsetChoiceDemo
~~~

**Stdout chính xác:**

~~~text
correct=true
wrong-equal=false
wrong-has-replacement=true
named-equivalent=true
invalid-name=UnsupportedEncodingException
null-charset=NullPointerException
~~~

Điểm quan trọng:

- `"café"` mã hóa ISO-8859-1 sử dụng **một byte cho `é`**. Byte đó nếu diễn giải theo UTF-8 thì không tạo ra cùng chuỗi, ở ví dụ sẽ có ký tự thay thế U+FFFD.
- `correct` và `out.toString("ISO-8859-1")` có nội dung giống nhau vì cả hai giải mã theo một charset.
- Tên charset không được hỗ trợ ở overload `toString(String)` dẫn tới `UnsupportedEncodingException`, còn `(Charset) null` bị từ chối với `NullPointerException`.
- Phương thức **không tự phát hiện dữ liệu ban đầu thuộc charset nào**. Chọn sai charset vẫn có thể trả về một `String` — nhưng là chuỗi sai nội dung.

Trong ứng dụng, nếu nhận bytes từ một hệ thống bên ngoài, cách chọn charset phải lấy từ hợp đồng API, HTTP `Content-Type` có charset (khi phù hợp), cấu hình file, hoặc định dạng chuẩn của dữ liệu. Không nên “thử nhiều charset và chọn chuỗi có vẻ đọc được” như một cam kết xử lý chính xác.

## 6. Byte không hợp lệ: `toString(Charset)` thay thế, không báo lỗi nghiêm ngặt

Javadoc nêu rõ `ByteArrayOutputStream.toString(Charset)` **luôn thay các chuỗi byte không hợp lệ hoặc không ánh xạ được bằng chuỗi thay thế mặc định của Charset**. Với UTF-8, trường hợp thường thấy là ký tự thay thế Unicode **U+FFFD**, hiển thị như `�`.

Điều này hữu ích khi cần hiển thị văn bản tối đa có thể giải mã, nhưng **không** đủ nếu ứng dụng cần đảm bảo input chính xác 100%, chẳng hạn xác minh định dạng file, dữ liệu cần ký số hoặc protocol phải từ chối mọi byte UTF-8 sai.

Ví dụ bytes:

~~~text
41 C3 28 42
 A ?? (  B
~~~

- `0x41` là `A` trong UTF-8.
- `0xC3` yêu cầu byte tiếp theo phù hợp với chuỗi UTF-8 nhiều byte.
- `0x28` là `(`, không phải continuation byte thích hợp của `0xC3`.
- Khi giải mã bằng phương thức có chế độ thay thế, chuỗi ví dụ trở thành `A�(B`; xuất hiện **một U+FFFD trong trường hợp cụ thể này**.

### Khi cần kiểm soát lỗi byte, dùng `CharsetDecoder`

`CharsetDecoder` cho phép tùy chỉnh xử lý `CodingErrorAction.REPORT`, `REPLACE` và `IGNORE` đối với malformed/unmappable input. Khi cấu hình `REPORT`, việc giải mã dữ liệu sai có thể ném `CharacterCodingException` (với ví dụ dưới, `MalformedInputException`).

Cách làm rõ sự khác biệt:

~~~java
String permissive = out.toString(StandardCharsets.UTF_8);

String strict = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .decode(ByteBuffer.wrap(out.toByteArray()))
        .toString();
~~~

Đây là **đoạn minh họa trong method**; `out` là BAOS, cần import `ByteBuffer`, `CodingErrorAction`, `StandardCharsets` và xử lý `CharacterCodingException`. Ở nhánh strict, kết quả chỉ được trả nếu bytes hợp lệ theo các quy tắc decoder.

**Đừng nhầm sự thay thế với validation thành công:** từ việc `out.toString(UTF_8)` không ném exception **không thể kết luận** bytes là UTF-8 hợp lệ. Nó có thể đã chèn ký tự thay thế và làm mất khả năng phục hồi nội dung gốc.

## 7. Chương trình chạy được 3 — So sánh thay thế và từ chối byte sai

Lưu **`MalformedInputDemo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class MalformedInputDemo {
    public static void main(String[] args) throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        out.write(new byte[] {65, (byte) 0xC3, 40, 66});

        String replacement = out.toString(StandardCharsets.UTF_8);
        System.out.println("replacement-expected=" +
                replacement.equals("A\uFFFD(B"));
        System.out.println("replacement-count=" +
                replacement.codePoints()
                        .filter(cp -> cp == 0xFFFD)
                        .count());

        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(out.toByteArray()));
        } catch (CharacterCodingException expected) {
            System.out.println("strict-error=" +
                    expected.getClass().getSimpleName());
        }
    }
}
~~~

Lệnh:

~~~bash
javac --release 10 MalformedInputDemo.java
java MalformedInputDemo
~~~

Stdout:

~~~text
replacement-expected=true
replacement-count=1
strict-error=MalformedInputException
~~~

Ở đây, `toString(UTF_8)` trả chuỗi có một U+FFFD đúng như dự đoán. `CharsetDecoder` ở chế độ `REPORT` ném `MalformedInputException` để caller xác định input sai, thay vì âm thầm sử dụng nội dung đã thay ký tự.

Trong dự án, nên quyết định rõ một trong hai chính sách:

1. **Hiển thị/phục hồi tối đa:** chấp nhận replacement, nhưng hiểu rằng nội dung đã có thể mất thông tin.
2. **Kiểm tra nghiêm ngặt:** từ chối malformed/unmappable input, báo lỗi với thông tin hữu ích và không sử dụng dữ liệu như thể hoàn toàn hợp lệ.

Không nên dùng `String.contains("\uFFFD")` như cơ chế validation chắc chắn: ký tự U+FFFD có thể đã xuất hiện **hợp lệ trong dữ liệu gốc**. Khi cần biết decoder có gặp byte sai hay không, hãy dùng chế độ `REPORT` và xử lý exception.

## 8. `ByteArrayOutputStream` có thể ghi tiếp, `reset` và `close`

`ByteArrayOutputStream` là stream trong bộ nhớ. Nó không phải socket hay file stream cần flush/close để đảm bảo những byte đã ghi xuất hiện trong bộ đệm nội bộ. Các phương thức quan trọng:

- `write(...)`: thêm byte vào phần dữ liệu đang có.
- `size()`: trả số byte hiện đang có.
- `toString(Charset)`: giải mã bytes hiện có và trả một `String` mới về **nội dung**; không tự tiêu thụ bytes.
- `toByteArray()`: trả **một bản sao byte[] mới** của nội dung hiện có, không phải reference trực tiếp tới bộ đệm nội bộ.
- `reset()`: đặt số byte hợp lệ về 0, cho phép tái sử dụng buffer đã cấp phát; String đã tạo từ lần giải mã trước không bị sửa.
- `flush()`: với chính `ByteArrayOutputStream`, không cần dùng để làm bytes xuất hiện trong bộ nhớ; byte đã ghi có thể đọc được ngay.
- `close()`: theo hợp đồng lớp này, **không có tác dụng**. Kể cả sau khi đóng, các thao tác của BAOS vẫn có thể được gọi mà không gây `IOException` chỉ vì nó đã close.

Không khái quát hành vi `close()` vô tác dụng cho mọi `OutputStream`. Với file/socket output, đóng stream thường giải phóng tài nguyên và ngăn tiếp tục sử dụng. Đó là đặc điểm riêng của BAOS.

### String trả về là ảnh chụp nội dung ký tự, không phải live view

~~~java
ByteArrayOutputStream out = new ByteArrayOutputStream();
out.write("A".getBytes(StandardCharsets.UTF_8));

String first = out.toString(StandardCharsets.UTF_8);
out.write("B".getBytes(StandardCharsets.UTF_8));

System.out.println(first);                           // A
System.out.println(out.toString(StandardCharsets.UTF_8)); // AB
~~~

Đây là đoạn minh họa trong method, cần import tương ứng. `first` là một `String` immutable đã được tạo; nó không thay đổi khi BAOS nhận thêm byte. Mỗi lần muốn nhìn thấy dữ liệu mới, gọi giải mã lại **sau khi bytes mới đã được ghi đủ**.

## 9. Chương trình chạy được 4 — Snapshot, reset, flush và close

Lưu **`BufferLifecycleDemo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

public class BufferLifecycleDemo {
    public static void main(String[] args) throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        out.write("one".getBytes(StandardCharsets.UTF_8));
        String first = out.toString(StandardCharsets.UTF_8);

        out.write("two".getBytes(StandardCharsets.UTF_8));
        System.out.println("first=" + first);
        System.out.println("current=" + out.toString(StandardCharsets.UTF_8));

        out.reset();
        System.out.println("after-reset-size=" + out.size());
        System.out.println("after-reset-text-empty=" +
                out.toString(StandardCharsets.UTF_8).isEmpty());

        out.write("new".getBytes(StandardCharsets.UTF_8));
        out.flush();
        out.close();
        out.write('!');
        System.out.println("after-close=" + out.toString(StandardCharsets.UTF_8));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 10 BufferLifecycleDemo.java
java BufferLifecycleDemo
~~~

**Stdout chính xác:**

~~~text
first=one
current=onetwo
after-reset-size=0
after-reset-text-empty=true
after-close=new!
~~~

Điều cần nhớ:

- `first` vẫn bằng `"one"` dù BAOS đã nhận thêm bytes.
- `reset()` làm dữ liệu đang có của BAOS trở về rỗng, không thay đổi `first`.
- `flush`/`close` trên BAOS trong ví dụ không ngăn việc ghi tiếp; riêng BAOS có hợp đồng này.
- `write('!')` viết byte có giá trị 33, phù hợp vì `!` là một ký tự ASCII. Với một ký tự Unicode bất kỳ, **không** dùng `write(int)` một lần rồi mong nó tự mã hóa UTF-8; hãy mã hóa bằng `String.getBytes(Charset)` hoặc `OutputStreamWriter`.

## 10. Khi bytes đến từ `OutputStreamWriter`, cần flush writer đúng thời điểm

Nhiều chương trình không tự có `byte[]`, mà dùng một `Writer` để ghi ký tự vào `ByteArrayOutputStream`:

~~~java
ByteArrayOutputStream bytes = new ByteArrayOutputStream();
Writer writer = new OutputStreamWriter(bytes, StandardCharsets.UTF_8);

writer.write("Xin chào");
// Cần writer.flush() hoặc writer.close() trước khi coi bytes là hoàn chỉnh.
writer.flush();

String result = bytes.toString(StandardCharsets.UTF_8);
~~~

Đây là đoạn minh họa trong method, cần import `Writer`, `OutputStreamWriter`, `ByteArrayOutputStream` và `StandardCharsets`. `OutputStreamWriter` mã hóa ký tự thành bytes và có thể giữ kết quả trong bộ đệm nội bộ. Nếu còn một `BufferedWriter` bọc phía ngoài, còn thêm một tầng buffering nữa.

**Vì vậy:** `BAOS.toString(Charset)` chỉ giải mã những bytes **thực sự đã đến BAOS**. Nó **không tự gọi `flush()` trên writer bên trên** và không biết writer đang giữ phần dữ liệu nào. Nếu decode trước khi writer flush, kết quả có thể rỗng hoặc thiếu đoạn cuối.

Quy trình an toàn khi kết thúc một thông điệp:

~~~text
Writer.write(text)
     |
     | flush() tại ranh giới cần thấy output
     v
ByteArrayOutputStream đã có đủ bytes
     |
     | toString(cùng Charset)
     v
String
~~~

Nếu chính phương thức sở hữu writer và sắp kết thúc, `try-with-resources` có thể đóng writer (đóng writer flush theo hợp đồng). BAOS vẫn có thể giải mã bytes sau khi writer đóng vì `BAOS.close()` không có tác dụng. Nếu writer là tài nguyên do caller sở hữu, **không tự ý đóng**; flush theo giao thức mà caller quy định.

### Lưu ý khi dữ liệu được chia thành nhiều chunk

Với UTF-8, một ký tự Unicode có thể cần 2, 3 hoặc 4 bytes. Nếu mới nhận **một phần** bytes rồi gọi `toString(UTF_8)`, phương thức sẽ giải mã theo số bytes hiện có và có thể chèn ký tự thay thế cho chuỗi chưa hoàn chỉnh.

Ví dụ ký tự `€` (U+20AC) có các byte UTF-8:

~~~text
E2 82 AC
~~~

Nếu BAOS chỉ đang có `E2`, `toString(UTF_8)` không thể biết hai byte tiếp theo sẽ đến sau; nó giải mã **toàn bộ buffer hiện tại** và có thể tạo `�`. Khi ghi tiếp `82 AC` rồi giải mã lại **toàn bộ ba bytes**, kết quả là `€`. String từ lần giải mã chưa đủ bytes không tự được sửa.

**Không dùng `toString(Charset)` như một decoder giữ trạng thái giữa các chunk.** Nếu giao thức thực sự cần chuyển bytes thành ký tự **trong lúc streaming**, hãy dùng `CharsetDecoder` với `ByteBuffer`/`CharBuffer` và cơ chế giữ byte chưa hoàn chỉnh phù hợp, hoặc `InputStreamReader`/`BufferedReader` cho luồng text. Nếu chỉ cần nội dung sau khi nhận xong, chờ đủ thông điệp rồi `toString(Charset)`.

## 11. Chương trình chạy được 5 — Flush và byte UTF-8 chưa hoàn chỉnh

Lưu **`ChunkedEncodingDemo.java`**:

~~~java
import java.io.BufferedWriter;
import java.io.ByteArrayOutputStream;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;

public class ChunkedEncodingDemo {
    public static void main(String[] args) throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        BufferedWriter writer = new BufferedWriter(
                new OutputStreamWriter(out, StandardCharsets.UTF_8), 128);

        writer.write("A\u00E9\uD83D\uDE80");
        System.out.println("before-flush-size=" + out.size());

        writer.flush();
        System.out.println("after-flush-size=" + out.size());
        System.out.println("flush-decoded=" +
                out.toString(StandardCharsets.UTF_8)
                        .equals("A\u00E9\uD83D\uDE80"));
        writer.close();

        ByteArrayOutputStream parts = new ByteArrayOutputStream();
        parts.write(0xE2);
        String partial = parts.toString(StandardCharsets.UTF_8);
        System.out.println("partial-replacement=" +
                partial.contains("\uFFFD"));

        parts.write(new byte[] {(byte) 0x82, (byte) 0xAC});
        System.out.println("completed-euro=" +
                parts.toString(StandardCharsets.UTF_8).equals("\u20AC"));
        System.out.println("saved-partial-unchanged=" +
                partial.contains("\uFFFD"));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 10 ChunkedEncodingDemo.java
java ChunkedEncodingDemo
~~~

**Stdout chính xác:**

~~~text
before-flush-size=0
after-flush-size=7
flush-decoded=true
partial-replacement=true
completed-euro=true
saved-partial-unchanged=true
~~~

Phân tích:

1. Trong thử nghiệm cụ thể, buffer 128 ký tự giữ nội dung `"Aé🚀"` nên BAOS chưa có bytes trước `flush`. **Không suy ra rằng writer luôn giữ mọi dữ liệu cho tới flush**: khi buffer đầy, writer có thể ghi xuống trước.
2. Sau `writer.flush()`, BAOS có 7 bytes mã hóa UTF-8 và giải mã lại chính xác.
3. Lúc chỉ có `E2`, kết quả chứa U+FFFD vì chuỗi UTF-8 chưa đủ.
4. Khi thêm `82 AC`, cả ba bytes cùng tồn tại và giải mã ra `€`.
5. `partial` vẫn chứa ký tự thay thế của **lần giải mã trước**, không cập nhật theo lần ghi thêm.

Trong hệ thống nhận byte từ socket/HTTP, **ranh giới chunk mạng không nhất thiết là ranh giới ký tự Unicode**. Phải biết khi nào payload đã đủ hoặc dùng decoder streaming đúng cách, tránh giải mã riêng từng chunk rồi nối String theo phương pháp làm mất ký tự.

## 12. Áp dụng vào API và luồng dữ liệu thực tế

### Mẫu tạo chuỗi từ writer được sở hữu trong cùng phương thức

Nếu một phương thức chủ động tạo `OutputStreamWriter` để ghi văn bản rồi cần kết quả dưới dạng `String`:

~~~java
static String render(String value) throws IOException {
    ByteArrayOutputStream bytes = new ByteArrayOutputStream();

    try (Writer writer =
                 new OutputStreamWriter(bytes, StandardCharsets.UTF_8)) {
        writer.write(value);
    }

    return bytes.toString(StandardCharsets.UTF_8);
}
~~~

Đây là **phương thức minh họa**, cần import `IOException`, `ByteArrayOutputStream`, `Writer`, `OutputStreamWriter` và `StandardCharsets`. Sau `try-with-resources`, writer đã được đóng theo hợp đồng và các bytes đã được chuyển tới BAOS. Vì BAOS có thể đọc sau khi close, `toString(UTF_8)` lấy được nội dung cuối.

Trong trường hợp **chỉ muốn tạo String từ String**, không cần vòng chuyển mã vòng quanh như thế; ví dụ này dùng để minh họa luồng mã hóa trong API chỉ cho phép ghi vào `OutputStream`.

### Kết quả là dữ liệu nhị phân thì không dùng `toString(Charset)`

Nếu BAOS chứa một file ZIP, PNG, PDF, dữ liệu nén hoặc dữ liệu mã hóa, **đừng tự động gọi `toString(UTF_8)`**. Những bytes đó không có hợp đồng là văn bản UTF-8 nên có thể bị thay thế và mất dữ liệu khi biến thành String.

Giữ dưới dạng byte[]:

~~~java
byte[] content = output.toByteArray();
~~~

Đây là đoạn trong phương thức khi `output` là BAOS. `toByteArray()` trả bytes copy để có thể ghi file hoặc gửi bằng API nhận binary. Chỉ giải mã text khi dữ liệu được xác định là text và biết Charset.

### API trả text: mô tả Charset rõ ràng

Một phương thức tốt nên ghi rõ nguồn dữ liệu, Charset và chính sách với byte lỗi. Ví dụ:

- “Đọc payload theo UTF-8; malformed input bị từ chối” → cần decoder cấu hình `REPORT` hoặc parser có contract tương ứng, **không chỉ** `toString(UTF_8)`.
- “Hiển thị tối đa nội dung, thay byte không hợp lệ” → `toString(UTF_8)` có hành vi replacement phù hợp, nhưng caller phải chấp nhận khả năng mất thông tin.
- “Mã hóa lại để lưu file” → dùng cùng Charset khi encode/decode; cân nhắc newline, normalization và format của tệp.

Không nên nhầm **charset** với **phông chữ hiển thị**. Chuỗi `String` đã giải mã đúng có thể vẫn hiển thị khác nhau theo font/console, nhưng đó không nhất thiết là lỗi decode.

## 13. Bảng lỗi phổ biến và cách xử lý

| Lỗi / ngộ nhận | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Gọi `out.toString()` khi bytes theo UTF-8 nhưng runtime có charset khác | Có thể ra ký tự sai | Dùng `out.toString(StandardCharsets.UTF_8)` |
| Dùng `toString(ISO_8859_1)` cho bytes vốn mã hóa UTF-8 | Chuỗi bị diễn giải sai, có thể thành văn bản lỗi | Dùng đúng Charset nguồn |
| Tưởng `toString(Charset)` sẽ ném khi UTF-8 sai | Có thể âm thầm chèn replacement | Dùng `CharsetDecoder` với `CodingErrorAction.REPORT` nếu cần strict |
| Tưởng `toString(Charset)` phát hiện Charset của dữ liệu | Không có cơ chế auto-detect được bảo đảm | Charset phải đến từ hợp đồng/metadata |
| Gọi decode khi `OutputStreamWriter` chưa flush | BAOS có thể chưa chứa đủ bytes | Flush/close writer theo ownership và ranh giới dữ liệu |
| Giải mã riêng từng chunk UTF-8 và nối text | Ký tự đa byte cắt giữa chunks có thể trở thành `�` | Đợi đủ bytes hoặc dùng decoder streaming |
| Tưởng `out.size()` là số ký tự | Sai với UTF-8 và surrogate pair | Phân biệt byte, UTF-16 `char` và code point |
| Tưởng `toString(Charset)` làm rỗng buffer | Lần đọc sau vẫn có dữ liệu cũ | `reset()` nếu muốn bỏ byte hiện có |
| Tưởng String vừa giải mã là live view của buffer | String cũ không tự cập nhật khi BAOS ghi thêm | Gọi decode lại nếu muốn nội dung mới |
| Tưởng `close` của BAOS ngăn `write` tiếp | BAOS có hợp đồng đặc biệt: `close` không tác dụng | Không áp dụng suy luận này cho FileOutputStream/SocketOutputStream |
| Dùng tên bảng mã dạng String mà không xử lý checked exception | `toString(String)` có `UnsupportedEncodingException` | Ưu tiên object `StandardCharsets.UTF_8` |
| Truyền `(Charset) null` | `NullPointerException` | Cung cấp Charset hợp lệ |
| Biến dữ liệu nhị phân tùy ý thành String | Replacement làm mất dữ liệu, không còn đảm bảo roundtrip | Giữ binary dưới dạng `byte[]` |
| So sánh output console và kết luận Charset sai | Font/terminal cũng có thể ảnh hưởng biểu diễn | Kiểm tra bằng `String.equals`, bytes hoặc code point |
| Dựa vào replacement để xác nhận input hợp lệ | Có thể mất dữ liệu mà không phát sinh exception | Giải mã strict với `CharsetDecoder` khi cần kiểm soát |

## 14. Checklist kiểm thử cho dự án

Khi review một lời gọi `ByteArrayOutputStream.toString(charset)`, hãy kiểm tra:

1. **Dữ liệu có thực sự là text không?** Nếu là binary, không dùng decode.
2. **Nguồn byte dùng charset nào?** Có khai báo trong protocol/file metadata không? Có trùng Charset được dùng giải mã không?
3. **Mã nguồn có dùng hằng `StandardCharsets`?** Tránh tên charset dạng chuỗi hoặc phụ thuộc charset mặc định nếu không cần.
4. **Đầu vào có Unicode ngoài ASCII?** Test ký tự có dấu và code point ngoài BMP, không chỉ `"hello"`.
5. **Có trường hợp byte malformed hoặc incomplete không?** Chọn replacement hay strict rejection cho đúng domain.
6. **BAOS nhận dữ liệu từ Writer chưa flush không?** Đặt điểm flush/close phù hợp.
7. **Có giải mã trước khi nhận đủ payload không?** Với UTF-8, chuỗi nhiều byte có thể bị cắt theo chunk.
8. **Có nhầm đơn vị đếm không?** Kiểm tra số byte và số ký tự bằng phép đo khác nhau.
9. **Cần dữ liệu mới sau khi `write` hoặc `reset`?** String trước đó là snapshot, không tự cập nhật.
10. **Đích tương tác có yêu cầu độ tin cậy không?** `BAOS.toString(Charset)` không xác nhận bytes đã truyền mạng hay được ghi bền vững; nó chỉ decode nội dung trong memory.
11. **Có mã hóa cùng Charset khi roundtrip không?** Với charset không biểu diễn mọi ký tự, `String.getBytes(Charset)` cũng có thể thay thế ký tự không ánh xạ được; chọn Charset phù hợp hoặc encoder strict khi yêu cầu toàn vẹn.
12. **Test có phụ thuộc charset mặc định của máy không?** Nếu cần kết quả lặp lại, chỉ định Charset ở cả chiều encode/decode.

Đối với unit test Java, nên so sánh nội dung bằng `assertEquals(expected, actual)` hoặc `String.equals`, không dựa vào việc in emoji có hiển thị chính xác trên mọi terminal. Với byte không hợp lệ, test strict decoder bằng ngoại lệ cụ thể/nhóm `CharacterCodingException`.

## 15. Câu hỏi tự kiểm tra

1. `ByteArrayOutputStream.toString(StandardCharsets.UTF_8)` nhận byte[] hay String làm tham số? Nó trả về kiểu nào?
2. Phương thức này được giới thiệu ở Java mấy và hiện có còn được hỗ trợ không?
3. Nếu ghi bytes ISO-8859-1 rồi gọi `toString(UTF_8)`, có luôn nhận đúng text không?
4. Nếu payload `Aé🚀` được mã hóa UTF-8, số byte, số `char` và số code point lần lượt là bao nhiêu?
5. `out.toString(StandardCharsets.UTF_8)` có reset hoặc đóng `out` không?
6. Sau khi tạo `String first = out.toString(UTF_8)`, nếu ghi thêm bytes, `first` có tự cập nhật không?
7. Khi UTF-8 chứa byte không hợp lệ, `toString(UTF_8)` có buộc ném `MalformedInputException` không? Muốn từ chối nghiêm ngặt thì dùng gì?
8. `out.toString("UTF-8")` khác `out.toString(StandardCharsets.UTF_8)` về loại tham số/checked exception như thế nào?
9. Tại sao cần `writer.flush()` trước `out.toString(UTF_8)` nếu dữ liệu đang nằm trong `BufferedWriter`?
10. Vì sao không nên giải mã từng TCP chunk UTF-8 độc lập rồi nối các String?
11. `ByteArrayOutputStream.close()` có cấm tiếp tục `write` không?
12. Khi stream chứa PDF/PNG dưới dạng bytes, nên dùng `toString(UTF_8)` hay `toByteArray()`?

**Đáp án:**

1. Nhận một `Charset`, không nhận byte[]/String; trả về `String`.
2. Java 10; vẫn là API hiện hành.
3. Không. Phải giải mã theo charset đã mã hóa hoặc theo hợp đồng dữ liệu.
4. 7 bytes, 4 đơn vị `char` UTF-16, 3 code point.
5. Không; nó chỉ giải mã bytes hiện có.
6. Không; String là kết quả đã được tạo, không phải view sống.
7. Không; overload này dùng replacement. Dùng `CharsetDecoder` cấu hình `CodingErrorAction.REPORT` khi muốn từ chối.
8. Bản nhận tên `String` khai báo `UnsupportedEncodingException`; bản nhận `Charset` không có checked exception đó.
9. Vì writer có thể giữ bytes trong buffer chưa chuyển xuống BAOS; decode quá sớm sẽ thấy nội dung thiếu.
10. Một ký tự UTF-8 có thể bị cắt giữa các chunk; giải mã từng phần có thể chèn U+FFFD không phục hồi được.
11. Không; close của riêng BAOS là no-op theo hợp đồng.
12. `toByteArray()` để giữ đúng bytes của dữ liệu nhị phân.

## 16. Tài liệu Java chính thức đang áp dụng

- **Oracle Javadoc — `ByteArrayOutputStream` (Java SE 10), mốc giới thiệu `toString(Charset)`:** https://docs.oracle.com/javase/10/docs/api/java/io/ByteArrayOutputStream.html
- **Oracle Javadoc — `ByteArrayOutputStream` (Java SE 26), phương thức và replacement policy:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/ByteArrayOutputStream.html
- **Oracle Javadoc — `StandardCharsets`:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/StandardCharsets.html
- **Oracle Javadoc — `CharsetDecoder` và `CodingErrorAction`:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetDecoder.html
- **Oracle Javadoc — `String`, constructor nhận `byte[]` và `Charset`:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html
- **Oracle Javadoc — `OutputStreamWriter`:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/OutputStreamWriter.html
- **Oracle Javadoc — `BufferedWriter`:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/BufferedWriter.html

**Ghi nhớ:** `ByteArrayOutputStream.toString(Charset)` của Java 10+ **giải mã các byte đang có theo Charset tường minh**, tạo một `String` mới về nội dung, **không đổi hoặc xóa bytes trong stream**. Chỉ định đúng Charset, đợi dữ liệu ghi hoàn chỉnh, hiểu chính sách **thay thế byte không hợp lệ**, và phân biệt byte với ký tự. Khi cần kiểm tra nghiêm ngặt dữ liệu đầu vào, dùng `CharsetDecoder` thay vì cho rằng `toString(Charset)` luôn phát hiện lỗi.