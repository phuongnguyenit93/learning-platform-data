# `StringReader`, `StringWriter` và các luồng mảng `char` trong Java I/O

## 1. Vì sao cần luồng ký tự trong bộ nhớ?

Không phải tác vụ I/O nào cũng cần mở tệp hoặc kết nối mạng. Đôi khi chương trình đã có dữ liệu dạng `String` hay `char[]` nhưng muốn truyền nó vào một API làm việc với `Reader`; hoặc muốn thu kết quả từ một API nhận `Writer` mà không ghi ra đĩa. Java có bốn lớp tiện dụng trong `java.io`:

| Lớp | Hướng thao tác | Nguồn/đích | Trường hợp phù hợp |
| --- | --- | --- | --- |
| `StringReader` | Đọc | Một `String` đã có | Cho parser/API cần `Reader` đọc từ chuỗi |
| `StringWriter` | Ghi | Bộ đệm ký tự tăng kích thước được | Thu văn bản mà API xuất qua `Writer` |
| `CharArrayReader` | Đọc | Một mảng `char[]`, có thể giới hạn đoạn | Cho API cần `Reader` đọc dữ liệu trong mảng |
| `CharArrayWriter` | Ghi | Mảng `char[]` nội bộ tăng kích thước được | Ghi dữ liệu ký tự và lấy mảng hoặc ghi tiếp sang `Writer` khác |

Tất cả hoạt động ở tầng **ký tự UTF-16 của Java**. Không có bước đọc byte từ đĩa, giải mã charset hay encode sang UTF-8 khi bạn chỉ chuyển giữa `String`, `char[]` và những lớp này.

Ví dụ quan hệ kiểu:

```text
String ──> StringReader ──> Reader ──> parser / BufferedReader
char[] ──> CharArrayReader ──> Reader ──> parser

formatter / parser ──> Writer ──> StringWriter ──> String
formatter / parser ──> Writer ──> CharArrayWriter ──> char[]
```

Dấu mũi tên trong hai dòng ghi thể hiện **dữ liệu đi vào writer rồi được lấy lại**; cấu trúc `Writer` là API để ghi, còn `toString()`/`toCharArray()` lấy kết quả.

## 2. Hiểu đúng `Reader` và `Writer` trước khi ghép lớp

`Reader` và `Writer` là các abstraction cho dữ liệu ký tự:

- `Reader.read()` trả về một `int` chứa **một đơn vị mã UTF-16** từ `0` đến `65535`, hoặc `-1` khi hết dữ liệu. Điều này khác `InputStream.read()`, chỉ trả giá trị byte `0..255` hoặc `-1`.
- `Reader.read(char[])` hay `read(char[], offset, length)` trả về **số lượng đơn vị mã `char`** được đọc, hoặc `-1` nếu EOF với yêu cầu đọc có độ dài dương. Giá trị `0` có thể xuất hiện khi yêu cầu độ dài bằng 0.
- `Writer.write(int)` ghi phần 16 bit thấp của đối số như một `char`; `write(char[])`, `write(String)` và `append(...)` ghi một hay nhiều ký tự.
- `flush()` yêu cầu đẩy dữ liệu đang chờ qua các lớp bọc; `close()` kết thúc vòng đời của một reader/writer theo hợp đồng từng lớp.

**`char` không đồng nghĩa một Unicode code point.** Một ký tự Unicode nằm ngoài vùng BMP (như nhiều emoji) được biểu diễn bằng **hai `char`** (surrogate pair). Vì vậy số lần `Reader.read()` có thể lớn hơn số code point mà người dùng coi là ký tự.

Chọn API theo nguồn dữ liệu: có sẵn `String` thì `StringReader`; có sẵn `char[]` thì `CharArrayReader`. Nếu một thư viện đã nhận trực tiếp `String` và không yêu cầu luồng, tạo `Reader` chỉ để bọc chuỗi thường không mang lại lợi ích.

## 3. `StringReader`: cho một `String` trở thành `Reader`

Tạo bằng `new StringReader(text)`, trong đó `text` là một `String`. `StringReader` đọc tuần tự các đơn vị mã UTF-16, có các thao tác `read()`, `read(char[])`, `skip(...)`, `mark(...)`, `reset()` và `close()`.

Ví dụ độc lập **`StringReaderDemo.java`**:

```java
import java.io.IOException;
import java.io.StringReader;

public class StringReaderDemo {
    public static void main(String[] args) throws IOException {
        try (StringReader reader = new StringReader("AβC")) {
            System.out.println((char) reader.read());

            reader.mark(10);
            System.out.println((char) reader.read());

            reader.reset();
            System.out.println((char) reader.read());
            System.out.println((char) reader.read());
            System.out.println(reader.read());
        }
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 StringReaderDemo.java
java StringReaderDemo
```

Đầu ra:

```text
A
β
β
C
-1
```

Giải thích:

1. Lần đầu đọc `A`, reader chuyển con trỏ đến trước `β`.
2. `mark(10)` đánh dấu vị trí hiện tại (trước `β`). Tham số là `readAheadLimit` theo API, không làm mảng tự tăng kích thước.
3. `read()` lấy `β`; `reset()` quay lại vị trí đánh dấu, nên lần đọc tiếp theo vẫn nhận `β`.
4. Tiếp theo là `C`, rồi `-1` báo hết chuỗi.
5. `StringReader` hỗ trợ `markSupported() == true`. Sau `close()`, các thao tác đọc thường ném `IOException`; không tiếp tục dùng một reader đã đóng.

Nếu cần đọc theo **dòng**, bọc thêm `BufferedReader`:

```java
BufferedReader lines = new BufferedReader(new StringReader(text));
String firstLine = lines.readLine();
```

Đoạn này **chỉ minh họa**, cần có biến `text`, import `java.io.BufferedReader`, xử lý `IOException` và đóng reader khi xong. `readLine()` loại bỏ dấu kết thúc dòng ở kết quả; nó khác `read()` lấy từng đơn vị mã.

## 4. `StringWriter`: thu nội dung được ghi thành `String`

`StringWriter` cung cấp một `Writer` với bộ đệm `StringBuffer` ở bên trong. Những thao tác quan trọng:

| Phương thức | Chức năng |
| --- | --- |
| `write(String)`, `write(char[])`, `write(int)` | Ghi văn bản/đơn vị mã vào bộ đệm |
| `append(CharSequence)` | Nối nội dung theo giao diện `Appendable`; trả về writer để tiếp tục nối |
| `toString()` | Lấy `String` biểu diễn nội dung hiện tại |
| `getBuffer()` | Trả về `StringBuffer` **nội bộ**, có thể sửa trực tiếp |
| `flush()`, `close()` | Không có tác dụng với chính `StringWriter`; nội dung vẫn lấy được sau khi đóng |

Ví dụ độc lập **`StringWriterDemo.java`**:

```java
import java.io.StringWriter;

public class StringWriterDemo {
    public static void main(String[] args) {
        StringWriter writer = new StringWriter();
        writer.write("Xin ");
        writer.append("chào");
        writer.write('!');

        System.out.println(writer.toString());
        System.out.println("length=" + writer.getBuffer().length());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 StringWriterDemo.java
java StringWriterDemo
```

Đầu ra:

```text
Xin chào!
length=9
```

`getBuffer()` cho quyền truy cập trực tiếp bộ đệm có thể thay đổi; chỉ dùng khi thật sự cần thao tác với `StringBuffer`. Đa số trường hợp nên lấy kết quả qua `toString()`. `StringWriter(int initialSize)` cho phép đặt dung lượng ban đầu; đây là **capacity**, không phải giới hạn cứng về số ký tự sẽ ghi.

`StringWriter` phù hợp khi thư viện chỉ nhận `Writer`, ví dụ renderer mẫu, formatter, serializer văn bản hoặc công cụ kiểm thử muốn thu output để so sánh. Nếu chỉ nối vài đoạn chuỗi trong mã ứng dụng và không cần API `Writer`, `StringBuilder` thường trực tiếp và đơn giản hơn.

## 5. `CharArrayReader`: đọc một mảng hoặc một đoạn mảng

`CharArrayReader` nhận `char[]` có sẵn:

- `new CharArrayReader(buffer)`: đọc toàn bộ mảng.
- `new CharArrayReader(buffer, offset, length)`: đọc **một đoạn** bắt đầu tại `offset` với tối đa `length` phần tử, không cần tạo chuỗi trung gian.
- Hỗ trợ `read()`, `read(char[], offset, length)`, `skip(...)`, `mark(...)` và `reset()`.

Ví dụ độc lập **`CharArrayReaderDemo.java`**:

```java
import java.io.CharArrayReader;
import java.io.IOException;

public class CharArrayReaderDemo {
    public static void main(String[] args) throws IOException {
        char[] source = "xABCDEy".toCharArray();

        try (CharArrayReader reader = new CharArrayReader(source, 1, 5)) {
            char[] block = new char[3];

            int first = reader.read(block, 0, block.length);
            System.out.println("chunk=" + new String(block, 0, first));

            reader.mark(10);
            System.out.println("next=" + (char) reader.read());

            reader.reset();
            System.out.println("again=" + (char) reader.read());
            System.out.println("last=" + (char) reader.read());
            System.out.println("EOF=" + reader.read());
        }
    }
}
```

Chạy:

```bash
javac CharArrayReaderDemo.java
java CharArrayReaderDemo
```

Đầu ra:

```text
chunk=ABC
next=D
again=D
last=E
EOF=-1
```

Reader này chỉ thấy đoạn `ABCDE`: ký tự `x` và `y` nằm ngoài phạm vi đã chọn. `read(char[], ...)` trả **số `char` thực đọc**, vì vậy dùng `new String(block, 0, first)`; không mặc định toàn bộ mảng đích đều vừa được điền dữ liệu mới.

**Điểm cần lưu ý về mảng:** `CharArrayReader` sử dụng mảng được truyền vào; không cần tạo bản sao độc lập theo hợp đồng constructor. Nếu mã khác sửa các phần tử mảng nguồn khi reader đang hoạt động, dữ liệu đọc có thể thay đổi theo. Không chia sẻ mảng có thể bị sửa đồng thời khi không có cơ chế phối hợp.

## 6. `CharArrayWriter`: ghi vào mảng `char` có thể tăng dung lượng

`CharArrayWriter` bắt đầu bằng bộ đệm ký tự nội bộ và tự tăng khi cần. Khác với `CharArrayReader` (nhận mảng có sẵn để đọc), `CharArrayWriter` sở hữu vùng nhớ để **nhận dữ liệu ghi vào**.

API chính:

| Phương thức | Kết quả |
| --- | --- |
| `write(...)` hoặc `append(...)` | Thêm ký tự vào bộ đệm |
| `toCharArray()` | Lấy **bản sao** `char[]` của nội dung hiện tại |
| `toString()` | Lấy bản `String` của nội dung |
| `size()` | Số đơn vị mã `char` hiện có |
| `writeTo(Writer other)` | Ghi nội dung hiện tại sang một writer khác |
| `reset()` | Đặt độ dài logic về 0 để tái sử dụng bộ đệm |
| `close()` | Không có tác dụng; lớp này vẫn có thể sử dụng sau khi đóng |

Chương trình độc lập **`CharArrayWriterDemo.java`**:

```java
import java.io.CharArrayWriter;
import java.io.IOException;
import java.io.StringWriter;

public class CharArrayWriterDemo {
    public static void main(String[] args) throws IOException {
        StringWriter destination = new StringWriter();

        try (CharArrayWriter writer = new CharArrayWriter(2)) {
            writer.write("Java");

            char[] snapshot = writer.toCharArray();
            writer.writeTo(destination);

            writer.reset();
            writer.write("IO");

            System.out.println("snapshot=" + new String(snapshot));
            System.out.println("destination=" + destination);
            System.out.println("reused=" + writer);
            System.out.println("size=" + writer.size());
        }
    }
}
```

Chạy:

```bash
javac CharArrayWriterDemo.java
java CharArrayWriterDemo
```

Đầu ra:

```text
snapshot=Java
destination=Java
reused=IO
size=2
```

`new CharArrayWriter(2)` chỉ cấp **capacity ban đầu bằng 2**, nên vẫn ghi được `Java` (4 ký tự). `toCharArray()` trả bản sao: sau `reset()` và ghi `IO`, biến `snapshot` vẫn chứa `Java`. `writeTo(destination)` chuyển nội dung tại thời điểm gọi, vì thế `destination` giữ `Java`.

`reset()` giúp tái sử dụng vùng nhớ trong các lượt xử lý lặp lại, nhưng bộ nhớ đã được cấp vẫn có thể được giữ lại. Khi làm việc với văn bản cực lớn, đừng giữ một writer có capacity lớn mãi nếu ứng dụng không cần tái sử dụng nó.

## 7. Ví dụ tích hợp: `StringReader` → `BufferedReader` → `BufferedWriter` → `StringWriter`

Đây là tình huống thường gặp khi một API phải xử lý từng dòng văn bản nhưng ta muốn tất cả hoạt động trong RAM. Ví dụ chuẩn hóa một văn bản gồm hai dòng, đánh số và chuyển thành chữ hoa.

Tạo tệp **`InMemoryTextPipeline.java`**:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.StringReader;
import java.io.StringWriter;
import java.util.Locale;

public class InMemoryTextPipeline {
    public static void main(String[] args) throws IOException {
        String source = "  táo  \n  chuối \n";
        StringWriter destination = new StringWriter();

        try (BufferedReader input =
                     new BufferedReader(new StringReader(source));
             BufferedWriter output =
                     new BufferedWriter(destination)) {

            String line;
            int lineNumber = 1;

            while ((line = input.readLine()) != null) {
                String normalized = line.strip().toUpperCase(Locale.ROOT);
                output.write(lineNumber + ":" + normalized);
                output.write('\n');
                lineNumber++;
            }
        }

        System.out.print(destination.toString());
    }
}
```

Chạy với Java 17+:

```bash
javac -encoding UTF-8 InMemoryTextPipeline.java
java InMemoryTextPipeline
```

Đầu ra:

```text
1:TÁO
2:CHUỐI
```

Dòng dữ liệu đi qua các tầng như sau:

1. `StringReader(source)` chuyển chuỗi có sẵn thành `Reader`; không tạo file và không diễn ra encode/decode UTF-8.
2. `BufferedReader` cho phép đọc theo dòng bằng `readLine()`; dấu xuống dòng không nằm trong kết quả `line`.
3. `strip()` bỏ khoảng trắng ở đầu/cuối mỗi dòng; `toUpperCase(Locale.ROOT)` biến `táo`, `chuối` thành `TÁO`, `CHUỐI` theo quy tắc Unicode, không dựa vào locale mặc định.
4. `BufferedWriter` nhận chuỗi đã xử lý, ghép `\n` **tường minh** để kết quả không phụ thuộc ký tự xuống dòng của hệ điều hành.
5. Khi rời `try-with-resources`, writer ngoài cùng được đóng và flush, nên `StringWriter destination` chứa toàn bộ kết quả. Đóng chính `StringWriter` không làm mất kết quả được lưu trong RAM.

Ví dụ này cũng phù hợp với **unit test**: một hàm xử lý `Reader` → `Writer` có thể kiểm thử chỉ với `StringReader` và `StringWriter`, không cần tạo tệp tạm hay kết nối mạng.

## 8. Cẩn thận với Unicode: `char` khác code point

Vì tất cả những reader/writer này dùng đơn vị mã UTF-16, một emoji thường cần hai `char`. Ví dụ độc lập **`CharUnitsDemo.java`**:

```java
import java.io.IOException;
import java.io.StringReader;

public class CharUnitsDemo {
    public static void main(String[] args) throws IOException {
        String text = "A😀B";

        System.out.println("length=" + text.length());
        System.out.println("codePoints="
                + text.codePointCount(0, text.length()));

        int units = 0;
        try (StringReader reader = new StringReader(text)) {
            while (reader.read() != -1) {
                units++;
            }
        }
        System.out.println("reader units=" + units);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 CharUnitsDemo.java
java CharUnitsDemo
```

Đầu ra:

```text
length=4
codePoints=3
reader units=4
```

`A` và `B` mỗi chữ dùng một đơn vị mã. Emoji `😀` được biểu diễn bởi một **cặp surrogate**, nên tổng `String.length()` và số lần đọc `StringReader.read()` là 4, còn số code point là 3.

**Hệ quả khi xử lý:** Nếu cần thao tác theo Unicode code point, hãy kết hợp đúng surrogate pair (ví dụ qua `String.codePoints()` hoặc `Character.toCodePoint(...)`), thay vì cho rằng mỗi lần `read()` là một ký tự độc lập mà người dùng nhìn thấy. Cắt `char[]` giữa cặp surrogate có thể tạo văn bản không hợp lệ khi chuyển sang byte theo charset.

## 9. Có nên thêm `BufferedReader` hoặc `BufferedWriter` không?

Đối với nguồn và đích đã ở trong bộ nhớ:

- `StringReader` đọc từ một chuỗi hiện hữu, `CharArrayReader` đọc trực tiếp từ mảng. Chúng không chịu chi phí gọi hệ điều hành để đọc đĩa/mạng.
- `StringWriter` và `CharArrayWriter` ghi vào bộ đệm RAM. Không bắt buộc phải bọc `BufferedWriter` chỉ vì muốn “tăng tốc”.
- `BufferedReader` vẫn hữu ích khi cần `readLine()`, vì phương thức này không tồn tại trên `StringReader` hay `CharArrayReader`.
- `BufferedWriter` hữu ích khi muốn API `newLine()` hoặc khi tái sử dụng cùng thuật toán cho writer khác, nhưng lớp đệm bổ sung có thể chưa đẩy nội dung xuống writer bên dưới cho đến `flush()` hoặc `close()`.

Chọn wrapper theo **giao diện thuật toán cần dùng**, tránh đệm lặp lại vì thói quen. Nếu nguồn bên dưới là file/socket, buffer đôi khi quan trọng để giảm lượt I/O vật lý; điều đó không tự động áp dụng cho mọi tác vụ trong RAM.

Một thiết kế linh hoạt là hàm nhận `Reader` và `Writer`:

```java
static void copyCharacters(Reader source, Writer destination)
        throws IOException {
    char[] buffer = new char[1024];
    int count;

    while ((count = source.read(buffer)) != -1) {
        destination.write(buffer, 0, count);
    }
}
```

Đây là **đoạn mã minh họa**, cần import `java.io.Reader`, `java.io.Writer` và `java.io.IOException`, đưa vào trong một class thích hợp. Nó hoạt động với `StringReader`, `CharArrayReader`, `FileReader` hoặc bất kỳ `Reader` tuân hợp đồng; tương tự đối với đích `Writer`. Bản thân hàm không đóng source/destination vì caller thường là bên quyết định vòng đời.

## 10. Vòng đời tài nguyên, sao chép và dung lượng bộ nhớ

Mặc dù các lớp hoạt động trong RAM, chúng vẫn có hành vi `close()` riêng:

| Lớp | Sau `close()` |
| --- | --- |
| `StringReader` | Không tiếp tục đọc; thao tác có thể gây `IOException` |
| `CharArrayReader` | Không tiếp tục đọc; thao tác có thể gây `IOException` |
| `StringWriter` | `close()` không có tác dụng; nội dung vẫn có thể truy xuất và writer có thể tiếp tục dùng |
| `CharArrayWriter` | `close()` không có tác dụng; bộ đệm còn đó, vẫn dùng được |

Chính vì vậy việc đọc tiếp từ reader sau khi đóng không phải cách truy xuất lại nguồn. Nếu cần lượt đọc khác, có thể tạo `StringReader` mới từ `String` gốc, hoặc một `CharArrayReader` mới từ mảng còn hợp lệ.

So sánh các cách lưu dữ liệu:

- `String` bất biến, phù hợp để giữ kết quả không cần sửa; `StringReader` dùng nó như nguồn.
- `char[]` thay đổi được, phù hợp khi muốn quản lý vùng nhớ và đoạn dữ liệu; `CharArrayReader` làm việc trên mảng nguồn nên tránh sửa mảng trong lúc đang đọc.
- `StringWriter` dùng `StringBuffer` nội bộ, có thể chuyển kết quả thành `String`. `getBuffer()` cho phép tác động vào bộ đệm nên cần kiểm soát nơi truy cập.
- `CharArrayWriter.toCharArray()` trả **bản sao**, còn `reset()` xóa độ dài logic mà thường giữ capacity.
- Kết quả `toString()` hoặc `toCharArray()` có thể yêu cầu cấp phát bộ nhớ bổ sung. Với nội dung rất lớn, quá nhiều bản sao cùng tồn tại làm tăng áp lực heap.

Nếu dữ liệu đầu vào thực sự là **byte**, chọn `ByteArrayInputStream` hoặc giải mã bằng `InputStreamReader(..., charset)` theo đúng nhu cầu. Không ép từng byte thành `char` để “đổi sang luồng ký tự”: việc đó không phải chuyển mã Unicode. Tương tự, khi cần tạo byte, dùng `OutputStreamWriter(..., charset)`/`String.getBytes(charset)` thay vì xem `char[]` như một mảng byte.

## 11. Lỗi phổ biến và checklist chọn lớp

| Nhầm lẫn | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `StringReader` là `InputStream` | Nó là `Reader` và làm việc trên `char` | Chỉ dùng API yêu cầu `Reader` |
| `StringWriter` ghi vào tệp | Nó ghi vào bộ đệm RAM | Dùng `Files.newBufferedWriter` hoặc writer dựa trên file để ghi tệp |
| `CharArrayReader` tự copy mảng nguồn | Reader làm việc với mảng được truyền vào | Không sửa/chia sẻ mảng đầu vào không kiểm soát |
| `read()` đọc một Unicode code point | `Reader.read()` đọc một đơn vị mã UTF-16 | Xử lý surrogate pair khi cần code point |
| `read(char[])` luôn điền đầy mảng | Có thể đọc ít hơn độ dài yêu cầu | Dùng đúng `count` được trả về |
| `CharArrayWriter.toCharArray()` trả mảng nội bộ | API trả bản sao nội dung | Dùng `reset()` để tái sử dụng, đừng mong sửa snapshot sẽ đổi writer |
| Tưởng `reset()` của mọi reader đều về đầu | `reset()` về vị trí `mark` nếu đã đánh dấu | Xác định rõ vị trí mark và kiểm tra `markSupported()` |
| Đọc `StringWriter` bọc bởi `BufferedWriter` quá sớm | Dữ liệu có thể còn trong buffer ngoài | `flush()` hoặc đóng BufferedWriter trước khi lấy kết quả |
| Thêm charset vào `StringReader` | Reader đã làm việc trên ký tự | Chỉ định charset ở ranh giới byte ↔ ký tự khi thực sự có byte |
| Dùng `StringWriter` cho dữ liệu khổng lồ không giới hạn | Bộ đệm có thể chiếm nhiều heap | Xem xét streaming, giới hạn đầu vào và tránh bản sao lớn |

**Tự luyện:** Viết hàm `normalize(Reader input, Writer output)` đọc từng dòng rồi thêm số thứ tự. Thử hai cách truyền dữ liệu: `StringReader`/`StringWriter` và `CharArrayReader`/`CharArrayWriter`. Khi chạy cùng nội dung, so sánh hai chuỗi đầu ra bằng `equals`. Sau đó thử chuỗi chứa emoji để giải thích vì sao `String.length()` và số code point có thể khác nhau.

**Ghi nhớ:** `StringReader`/`CharArrayReader` biến văn bản sẵn có trong RAM thành **nguồn `Reader`**; `StringWriter`/`CharArrayWriter` biến API **`Writer`** thành **đích trong RAM**. Chúng làm việc với đơn vị mã `char`, không tự chuyển byte theo charset. Chọn lớp theo dạng dữ liệu sẵn có, quản lý đúng vòng đời và kiểm soát các bản sao khi tài liệu lớn.