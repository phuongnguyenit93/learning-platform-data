# Đọc và ghi char[], String và từng phần dữ liệu trong luồng ký tự Java

## 1. Mục tiêu và bức tranh chung

Trong Java I/O, **luồng ký tự** (`Reader` và `Writer`) cho phép ứng dụng đọc, ghi nội dung văn bản theo các đơn vị `char` của Java. Khi dữ liệu có thể dài, đến chậm hoặc được chia thành nhiều phần, ta thường dùng **mảng `char[]` làm bộ đệm** thay vì đọc toàn bộ văn bản thành một `String`.

Bài này giải quyết các câu hỏi thực tế:

- `Reader.read(char[])` đọc bao nhiêu ký tự trong một lần? Tại sao không được giả định mảng luôn đầy?
- `char[]`, `String` và `StringBuilder` có vai trò khác nhau ra sao khi lưu, xử lý và ghi dữ liệu?
- `off` và `len` trong `read`/`write` có nghĩa gì? Làm thế nào tránh lẫn vị trí bắt đầu với vị trí kết thúc?
- Làm thế nào sao chép từng phần văn bản mà không thêm ký tự cũ, mất dữ liệu hay phá vỡ nội dung?
- Khi nào cần quan tâm đến Unicode, charset, bộ đệm và việc đóng luồng?

Một đường đi điển hình:

~~~text
Nguồn văn bản (tệp hoặc chuỗi)
          │
          ▼
      Reader
          │ read(char[], off, len)
          ▼
   char[] dùng lại nhiều lần
          │ write(char[], 0, count)
          ▼
      Writer
          │
          ▼
Đích văn bản (tệp hoặc vùng nhớ)
~~~

`Reader` và `Writer` thao tác trên **ký tự Java**; nếu đầu vào hoặc đầu ra thực sự là tệp hay kết nối mạng, byte sẽ được giải mã/mã hóa qua một charset tại ranh giới I/O. `char[]` chỉ là vùng nhớ trung gian. Việc đọc theo từng phần giúp sử dụng bộ nhớ có giới hạn, độc lập với độ dài tài liệu.

## 2. Ba cách biểu diễn văn bản: char[], String và luồng ký tự

| Thành phần | Vai trò | Điểm cần nhớ |
| --- | --- | --- |
| `char` | Một đơn vị mã UTF-16 16 bit | Không luôn biểu diễn trọn một ký tự Unicode theo nghĩa code point |
| `char[]` | Mảng ký tự có thể sửa, có độ dài cố định | Có thể tái sử dụng làm bộ đệm; các vị trí cũ không tự biến mất |
| `String` | Chuỗi văn bản bất biến | Thích hợp cho đoạn văn bản đã thu được hoặc tham số cần truyền |
| `StringBuilder` | Bộ tích lũy ký tự trong bộ nhớ, có thể thay đổi | Phù hợp khi cần nối nhiều đoạn thành một chuỗi cuối cùng |
| `Reader` | Giao diện lớp trừu tượng để nhận ký tự theo thứ tự | `read` có thể trả về ít hơn lượng yêu cầu; `-1` nghĩa là hết dữ liệu |
| `Writer` | Giao diện lớp trừu tượng để đưa ký tự ra đích | `write` không trả về số ký tự đã ghi; có thể ném `IOException` |

Ví dụ, biểu thức `new char[1024]` tạo mảng chứa 1024 đơn vị `char`. Mỗi lượt đọc có thể chỉ ghi đè phần đầu của mảng. Nếu một lần chỉ đọc được 7 đơn vị, **chỉ 7 phần tử đầu là dữ liệu mới của lượt đó** khi dùng `read(buffer)`.

`String` không thể thay đổi tại chỗ. Nếu cần biến phần dữ liệu mới đọc thành chuỗi, dùng `new String(buffer, 0, count)`; chuỗi này chứa **đúng `count` phần tử**. Tránh `new String(buffer)` khi chỉ một phần mảng hợp lệ, vì chuỗi khi đó có thể chứa ký tự tồn dư hoặc giá trị `\u0000` chưa được ghi.

Khi cần xử lý dữ liệu lớn, không nhất thiết tạo `String` ở mỗi lần đọc: có thể chuyển thẳng `char[]` từ `Reader` sang `Writer`, hoặc xử lý phần dữ liệu hợp lệ rồi ghi. Việc liên tục nối `result += chunk` có thể tạo nhiều đối tượng `String` trung gian.

## 3. Hợp đồng đọc: Reader.read() và Reader.read(char[])

### 3.1. Đọc một đơn vị char

`Reader.read()` trả về một `int`:

- Giá trị không âm biểu diễn một đơn vị ký tự đã đọc (0–65535).
- `-1` biểu diễn **kết thúc luồng** (EOF).
- Lỗi I/O thường được báo bằng `IOException`.

Dùng `int` thay vì `char` để giữ được dấu hiệu `-1`:

~~~java
int codeUnit;
while ((codeUnit = reader.read()) != -1) {
    char ch = (char) codeUnit;
    // Xử lý ch.
}
~~~

Đây là đoạn minh họa: `reader` là một `Reader` đã mở và phải được đóng đúng quyền sở hữu. Cách đọc từng đơn vị dễ hiểu nhưng thường không tối ưu cho luồng lớn so với đọc vào mảng.

### 3.2. Đọc vào mảng

`read(char[] cbuf)` có thể đọc **tối đa** `cbuf.length` ký tự; giá trị trả về là số phần tử thực sự được lấp bằng dữ liệu mới, hoặc `-1` nếu luồng đã kết thúc. Đối với độ dài yêu cầu dương, hợp đồng của `Reader` sẽ chờ cho đến khi có dữ liệu, EOF hoặc lỗi, nhưng **không hứa đọc đủ toàn bộ độ dài yêu cầu**.

~~~java
char[] buffer = new char[4096];
int count;
while ((count = reader.read(buffer)) != -1) {
    writer.write(buffer, 0, count);
}
~~~

Với đoạn minh họa này, `reader` và `writer` là các đối tượng đã được tạo bên ngoài. Dòng `writer.write(buffer, 0, count)` là yếu tố then chốt: **ghi đúng phần dữ liệu vừa đọc**.

Các giá trị `count` có thể thay đổi:

~~~text
Bộ đệm dài 4; nguồn "ABCDEFGHIJ"

Lượt 1: count=4, dữ liệu mới ABCD
Lượt 2: count=4, dữ liệu mới EFGH
Lượt 3: count=2, dữ liệu mới IJ; hai ô còn lại vẫn có thể giữ GH
Lượt 4: count=-1, EOF
~~~

Nếu lượt 3 gọi `writer.write(buffer)`, hai phần tử cũ có thể bị ghi thêm thành `IJGH`. Nếu gọi `new String(buffer)` rồi nối vào kết quả, lỗi tương tự xuất hiện.

### 3.3. Trường hợp mảng rỗng

`read(new char[0])` yêu cầu đọc 0 phần tử và có thể trả về `0` ngay, kể cả chưa đến EOF. Vì thế, **không dùng bộ đệm độ dài 0** trong vòng lặp đọc thông thường. Với bộ đệm dương, vẫn nên viết thuật toán dựa trên số ký tự thực sự trả về thay vì suy đoán từ kích thước buffer hoặc dung lượng tệp.

Đọc luồng ký tự có thể chặn thread khi dữ liệu chưa sẵn sàng. Không dùng `reader.ready() == false` để kết luận đã EOF: `ready()` chỉ cho biết lượt đọc kế tiếp có thể tiến hành mà không chặn theo hợp đồng của lớp, không có nghĩa đã đọc hết dữ liệu.

## 4. Vùng đọc: read(char[] buffer, int off, int len)

Dạng ba tham số cho phép ghi vào **một đoạn** của mảng đích:

~~~java
int count = reader.read(buffer, off, len);
~~~

- `buffer` là mảng nhận dữ liệu.
- `off` là chỉ số **bắt đầu** trong mảng (tính từ 0).
- `len` là **số ký tự tối đa muốn đọc**, không phải chỉ số kết thúc.
- Giá trị trả về `count` là số ký tự thực tế, hoặc `-1` ở EOF khi yêu cầu có độ dài dương.

Điều kiện hợp lệ: `off >= 0`, `len >= 0` và `off + len <= buffer.length` về mặt toán học. Để tránh tràn số khi tự kiểm tra, có thể đánh giá bằng `off <= buffer.length` rồi `len <= buffer.length - off`.

Ví dụ độc lập minh họa vị trí điền dữ liệu:

~~~java
import java.io.StringReader;
import java.util.Arrays;

public class ReadSliceDemo {
    public static void main(String[] args) throws Exception {
        char[] destination = {'_', '_', '_', '_', '_'};

        try (StringReader reader = new StringReader("ABC")) {
            int count = reader.read(destination, 1, 3);
            System.out.println("count=" + count);
            System.out.println(Arrays.toString(destination));
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ReadSliceDemo.java
java ReadSliceDemo
~~~

Kết quả:

~~~text
count=3
[_, A, B, C, _]
~~~

Có hai điều phải chú ý: dữ liệu chỉ được đặt từ chỉ số 1 đến 3; hai phần tử ngoài đoạn đọc không bị thay đổi. Nếu `count` bằng 2, đoạn mới hợp lệ chỉ là `destination[1]` và `destination[2]`. Khi ghi tiếp, dùng `writer.write(destination, 1, count)`, **không** dùng `writer.write(destination, 1, 3)` theo độ dài đã yêu cầu.

Đọc với `off` và `len` hữu ích khi mảng chứa nhiều vùng, khi ghép thêm vào phần đang có, hoặc khi giao thức xử lý chỉ cho phép ghi vào một đoạn nhất định. Trong ví dụ sao chép toàn bộ luồng, `read(buffer)` ngắn gọn hơn.

## 5. Ghi char[], String và từng đoạn

### 5.1. Writer.write(char[])

`writer.write(charArray)` ghi **toàn bộ mảng**, từ chỉ số 0 đến `charArray.length - 1`. Phương thức này phù hợp khi mọi phần tử đều có ý nghĩa.

`writer.write(charArray, off, len)` chỉ ghi `len` phần tử bắt đầu tại `off`. Đây là cách đúng khi mảng chỉ chứa `count` ký tự hợp lệ từ một lần đọc.

~~~java
char[] chars = {'J', 'a', 'v', 'a', '!', '?'};

writer.write(chars, 0, 5); // Ghi "Java!"
writer.write(chars, 2, 3); // Ghi "va!"
~~~

Đoạn này mang tính minh họa với `writer` đã được cung cấp. `write` trả về `void`; nếu thao tác không thành công, nó có thể báo lỗi thay vì trả số ký tự đã ghi. Không giả định `write` tự thêm dấu kết thúc dòng; nếu cần xuống dòng, phải ghi `"\n"`, `System.lineSeparator()` hoặc sử dụng phương thức dòng phù hợp với mục đích.

### 5.2. Writer.write(String)

`writer.write(text)` ghi toàn bộ `String`. `writer.write(text, off, len)` ghi đúng đoạn bắt đầu tại chỉ số `off` với độ dài `len`, cũng tính theo **đơn vị UTF-16**.

Ví dụ:

~~~java
writer.write("abcdef", 2, 3); // "cde", không phải "c"
~~~

Bởi tham số cuối là **độ dài**, không phải chỉ số kết thúc. So sánh `String.substring(beginIndex, endIndex)`: tham số cuối của `substring` là chỉ số loại trừ, nên `"abcdef".substring(2, 3)` chỉ tạo `"c"`. Nhầm hai hợp đồng này có thể khiến mất hoặc ghi thừa ký tự.

### 5.3. Append khác write ở cặp chỉ số

`writer.append("abcdef", 2, 5)` sử dụng `start` và `end` (end loại trừ), do hợp đồng `Appendable`; kết quả là `"cde"`. Ngược lại, `writer.write("abcdef", 2, 5)` yêu cầu **5** đơn vị tính từ chỉ số 2, vượt quá chuỗi dài 6 và không hợp lệ.

| Lời gọi | Cách hiểu tham số | Phần được lấy |
| --- | --- | --- |
| `write("abcdef", 2, 3)` | off=2, len=3 | `cde` |
| `append("abcdef", 2, 3)` | start=2, end=3 | `c` |
| `"abcdef".substring(2, 3)` | begin=2, end=3 | `c` |
| `write(new char[]{'a','b','c'}, 1, 2)` | off=1, len=2 | `bc` |

**Không dùng chung một biến tên `end` cho tham số `len` nếu chưa chuyển đổi**; chọn tên `offset`, `length` hoặc `start`, `endExclusive` để làm rõ ý nghĩa.

### 5.4. Ví dụ runnable về cách ghi đoạn

~~~java
import java.io.StringWriter;

public class WriteSliceDemo {
    public static void main(String[] args) throws Exception {
        try (StringWriter writer = new StringWriter()) {
            writer.write("abcdef", 1, 3);           // bcd
            writer.write(new char[]{'1','2','3','4'}, 1, 2); // 23
            writer.append("XYZ", 1, 3);             // YZ
            System.out.println(writer.toString());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 WriteSliceDemo.java
java WriteSliceDemo
~~~

Kết quả:

~~~text
bcd23YZ
~~~

`StringWriter` ghi vào bộ đệm ký tự trong RAM, nên ví dụ chạy mà không cần mở tệp. `StringWriter.close()` không có tác động làm mất nội dung tích lũy; với `FileWriter` hoặc một `Writer` gắn với tệp/socket, việc đóng tài nguyên cần thiết hơn nhiều.

## 6. Sao chép từng phần và tái sử dụng buffer

Kỹ thuật nền tảng khi xử lý văn bản lớn là một vòng lặp:

1. Tạo một mảng ký tự **có độ dài dương**, cố định.
2. Đọc vào mảng; nhận `count`.
3. Nếu `count == -1` thì dừng vì đã EOF.
4. Xử lý hoặc ghi **đúng `count` ký tự**; không đụng vào phần còn lại.
5. Lặp lại cho đến hết dữ liệu, rồi đóng tài nguyên theo trách nhiệm.

Một ví dụ đầy đủ có thể quan sát số phần tử mỗi lần đọc:

~~~java
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;
import java.io.Writer;

public class CharChunkDemo {
    public static void main(String[] args) throws Exception {
        try (Reader reader = new StringReader("abcdefg");
             Writer writer = new StringWriter()) {

            char[] buffer = new char[3];
            int count;

            while ((count = reader.read(buffer)) != -1) {
                System.out.println("read=" + count
                        + " segment=" + new String(buffer, 0, count));
                writer.write(buffer, 0, count);
            }

            System.out.println("result=" + writer);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CharChunkDemo.java
java CharChunkDemo
~~~

Kết quả chính xác:

~~~text
read=3 segment=abc
read=3 segment=def
read=1 segment=g
result=abcdefg
~~~

Trong lượt cuối, mảng vật lý có thể đang chứa `g` cùng ký tự còn lại từ lượt trước, nhưng `new String(buffer, 0, 1)` và `write(buffer, 0, 1)` chỉ dùng `g`. Vì `StringReader` đọc từ bộ nhớ đã có sẵn, đây là ví dụ có phân đoạn dễ dự đoán; với luồng tệp hoặc mạng thực, số ký tự mỗi lần đọc có thể khác giữa các lượt và môi trường.

Không cần xóa mảng bằng `Arrays.fill(buffer, '\0')` sau mỗi lần đọc để bảo đảm đúng dữ liệu, miễn là thuật toán luôn tuân thủ `count` và không sử dụng vùng cũ. Tùy loại dữ liệu nhạy cảm, việc xóa sau sử dụng có thể là yêu cầu riêng, nhưng không thay thế quy tắc đọc/ghi theo độ dài hợp lệ.

### 6.1. Nếu cần tích lũy thành String

Khi thật sự phải thu toàn bộ nội dung để xử lý trong bộ nhớ:

~~~java
StringBuilder result = new StringBuilder();
char[] buffer = new char[1024];
int count;

while ((count = reader.read(buffer)) != -1) {
    result.append(buffer, 0, count);
}

String text = result.toString();
~~~

Đây là đoạn minh họa dùng `Reader reader` đã có sẵn. `StringBuilder.append(char[], off, len)` cũng dùng `off` và `len`. Khả năng tiếp nhận toàn bộ dữ liệu phụ thuộc bộ nhớ heap. Với tệp lớn, cách chuyển thẳng từ Reader sang Writer hoặc xử lý trực tiếp từng khối thường phù hợp hơn.

Để nhận chuỗi từ một nguồn nhỏ đã biết, `StringWriter` cũng là một lựa chọn lưu trong bộ nhớ. Một số API tiện ích như `Reader.transferTo(Writer)` (Java 10+) có thể tự chuyển toàn bộ dữ liệu và trả về số `char` đã chuyển; nó **không tự đóng** Reader và Writer, nên vẫn cần quản lý vòng đời bên ngoài.

## 7. Ví dụ Java 17: đọc và ghi tệp văn bản theo từng khối char[]

Ví dụ sau tạo thư mục tạm, ghi văn bản UTF-8 làm dữ liệu nguồn, sau đó sao chép bằng `BufferedReader` và `BufferedWriter` trong từng lần đọc. Đích được đọc lại để xác minh nội dung; mọi luồng tự mở đều được đóng qua `try-with-resources`.

Lưu vào tệp **CopyTextChunksDemo.java**:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class CopyTextChunksDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("char-chunks-");
        Path source = directory.resolve("source.txt");
        Path target = directory.resolve("target.txt");
        String text = "Chào Java!\nDòng 2";

        try {
            Files.writeString(source, text, StandardCharsets.UTF_8);

            long copiedUnits = 0;
            try (BufferedReader reader =
                         Files.newBufferedReader(source, StandardCharsets.UTF_8);
                 BufferedWriter writer =
                         Files.newBufferedWriter(target, StandardCharsets.UTF_8)) {

                char[] buffer = new char[4];
                int count;
                while ((count = reader.read(buffer)) != -1) {
                    writer.write(buffer, 0, count);
                    copiedUnits += count;
                }
            }

            String copied = Files.readString(target, StandardCharsets.UTF_8);
            System.out.println("UTF-16 units: " + copiedUnits);
            System.out.println("Equal content: " + text.equals(copied));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CopyTextChunksDemo.java
java CopyTextChunksDemo
~~~

Kết quả:

~~~text
UTF-16 units: 17
Equal content: true
~~~

Lý do kết quả là `17`: `"Chào Java!"` có 10 đơn vị UTF-16, dấu xuống dòng `\n` có 1, `"Dòng 2"` có 6. Giá trị `copiedUnits` ghi lại **số đơn vị `char`**, không phải số byte UTF-8 trên đĩa. Ký tự có dấu trong văn bản có thể chiếm nhiều byte UTF-8 dù ở đây mỗi ký tự dùng một đơn vị UTF-16.

Giải thích cách chương trình giữ dữ liệu đúng:

- `newBufferedReader` giải mã các byte UTF-8 từ tệp thành luồng ký tự; `newBufferedWriter` mã hóa ký tự trở lại UTF-8.
- `char[4]` là bộ đệm nhỏ có chủ đích để minh họa quá trình chia khối. Trong chương trình thực, có thể chọn bộ đệm lớn hơn và đo hiệu năng bằng dữ liệu thực.
- `writer.write(buffer, 0, count)` ghi đúng đoạn vừa đọc, kể cả lần cuối chưa đầy mảng.
- Sau khi ra khỏi `try-with-resources`, writer đã được đóng và phần bộ đệm của nó đã được chuyển xuống luồng bên dưới; lúc đó mới mở tệp đích để đọc kiểm tra.
- `finally` dọn các tệp/thư mục thử nghiệm. Với ứng dụng có yêu cầu chẩn đoán lỗi cao, nên xử lý riêng ngoại lệ dọn dẹp để không che ngoại lệ xảy ra trước đó.

Vì đây là sao chép **văn bản**, việc giải mã rồi mã hóa lại là có chủ đích. Nếu cần bảo toàn nguyên vẹn từng byte của tệp bất kỳ, nên dùng byte stream hoặc `Files.copy`; đừng tùy tiện dùng `Reader`/`Writer` cho dữ liệu nhị phân.

## 8. Dữ liệu đến theo nhiều phần: điều gì được bảo đảm?

Giả sử giao thức gửi chuỗi `"HELLO"` nhưng nguồn chỉ sẵn có `"HE"` tại thời điểm đọc. `read(buffer)` có thể trả 2; lần sau trả 3. **Một lượt đọc không nhất thiết tương ứng một thông điệp, một dòng hoặc một đoạn người gửi đã ghi.**

Vì vậy, các cấu trúc như “đọc một lần cho đủ 100 ký tự” hoặc “một lần đọc là một bản ghi” là không an toàn nếu không có quy tắc xác định ranh giới. Thường có ba chiến lược:

1. **Đọc cho đến EOF** khi toàn bộ nguồn đại diện cho một nội dung. Dùng vòng lặp `read` như các ví dụ trên.
2. **Đọc đủ một độ dài được chỉ định** khi dữ liệu có phần đầu cung cấp độ dài hoặc hợp đồng yêu cầu chính xác N đơn vị. Lặp và cộng số đã đọc, xử lý EOF sớm như lỗi thiếu dữ liệu theo hợp đồng.
3. **Đọc theo dấu phân cách** khi dữ liệu được tổ chức thành dòng hoặc bản ghi có delimiter. `BufferedReader.readLine()` là API cho dòng văn bản, nhưng nó bỏ dấu kết thúc dòng khỏi kết quả.

Ví dụ đoạn mã minh họa cho yêu cầu đọc đúng `required` đơn vị `char`:

~~~java
char[] data = new char[required];
int offset = 0;

while (offset < required) {
    int count = reader.read(data, offset, required - offset);
    if (count == -1) {
        throw new java.io.EOFException("Văn bản kết thúc trước độ dài yêu cầu");
    }
    offset += count;
}
~~~

Giả định `required` là số không âm đã được kiểm tra và `reader` hợp lệ. Đoạn mã chưa phải một chương trình Java độc lập. Một nguồn đặc biệt có thể trả `0` lặp lại dù yêu cầu có độ dài dương; nếu làm việc với triển khai `Reader` không chuẩn hoặc luồng có giao ước riêng, cần thiết kế cơ chế tiến triển/tránh vòng lặp vô hạn. Với những Reader tuân thủ hợp đồng chuẩn, thao tác đọc độ dài dương thông thường sẽ chờ có dữ liệu, EOF hoặc lỗi.

**Không chọn `available()` để quyết định đọc đủ bao nhiêu ký tự**: đây là phương thức của `InputStream` (byte stream), không phải công cụ xác định độ dài dữ liệu cuối cùng. Tương tự, `ready()` của Reader không phải dấu hiệu EOF.

### 8.1. Không lẫn “một lần ghi” với “một lần nhận”

Phía ghi có thể gọi `writer.write("HELLO")` một lần nhưng phía đọc vẫn nhận dữ liệu làm nhiều phần. Điều này đặc biệt đúng với các giao thức truyền dữ liệu liên tục và lớp đệm trung gian. Nếu ranh giới thông điệp quan trọng, giao thức phải mã hóa ranh giới bằng độ dài, dấu phân cách có quy tắc escaping, hoặc cấu trúc bản ghi thích hợp.

## 9. Unicode: một char không luôn là một ký tự người dùng nhìn thấy

Java `char` là **một đơn vị mã UTF-16**. Hầu hết ký tự thông dụng như `A` hay `à` được biểu diễn bằng một đơn vị `char`; nhiều ký tự ngoài Basic Multilingual Plane, ví dụ một số emoji, cần **cặp surrogate** gồm hai đơn vị `char`.

Ví dụ:

~~~java
public class UnicodeUnitsDemo {
    public static void main(String[] args) {
        String text = "A😀B";
        System.out.println("UTF-16 units: " + text.length());
        System.out.println("Code points: " + text.codePointCount(0, text.length()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 UnicodeUnitsDemo.java
java UnicodeUnitsDemo
~~~

Kết quả:

~~~text
UTF-16 units: 4
Code points: 3
~~~

Chuỗi gồm ba code point (`A`, emoji, `B`) nhưng bốn đơn vị `char`. **Một lần `read(char[])` có thể chia dữ liệu ở ranh giới giữa hai đơn vị surrogate**; khi sao chép không biến đổi toàn bộ dữ liệu theo thứ tự, việc chuyển tuần tự qua Reader/Writer thích hợp sẽ giữ nguyên chuỗi đơn vị mã, nhưng nếu xử lý độc lập từng khối bằng cách đảo, cắt, lọc hoặc giải mã lại, cần giữ trạng thái giữa các khối để không tách cặp surrogate thành phần rời rạc.

Đừng hiểu `count` của `read` hoặc `Writer.write` là số “ký tự nhìn thấy” hay số code point. Muốn đếm hoặc thao tác theo code point trên `String`, có thể dùng `codePoints()` hoặc `Character.codePointAt` theo đúng ngữ cảnh. Ngay cả code point cũng không luôn bằng một ký tự hiển thị hoàn chỉnh: dấu kết hợp có thể đi với chữ cái trước đó.

### 9.1. Charset nằm ở ranh giới đọc/ghi byte

`StringReader` và `StringWriter` chỉ xử lý ký tự trong RAM; chúng không chọn UTF-8 hay UTF-16 cho tệp. Với tệp, nên nêu charset rõ ràng bằng những API như:

~~~java
try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    // Đọc các đơn vị char đã được giải mã từ byte UTF-8.
}
~~~

Với dữ liệu đã có sẵn dưới dạng byte, `InputStreamReader(input, UTF_8)` làm cầu nối byte → ký tự; `OutputStreamWriter(output, UTF_8)` làm cầu nối ký tự → byte. Khi charset nguồn và đích khác nhau, văn bản có thể được chuyển mã một cách có chủ đích. Nếu charset đọc sai, `char[]` có thể chứa văn bản đã lỗi trước cả khi logic ghi bắt đầu.

### 9.2. Nếu phải xử lý đoạn một cách độc lập

Một thuật toán như “mỗi khối 4 char đem đảo ngược rồi ghi ngay” có thể phá cặp surrogate hoặc dấu kết hợp khi nằm sát ranh giới. Giải pháp tùy mục đích: xử lý theo code point, giữ lại phần chưa hoàn chỉnh cho khối kế, hoặc dùng bộ xử lý văn bản theo quy tắc Unicode phù hợp. **Ranh giới buffer là chi tiết truyền dữ liệu, không tự nhiên là ranh giới ngữ nghĩa của văn bản**.

## 10. Đọc dòng, giữ dấu xuống dòng và xử lý khối

`BufferedReader.readLine()` trả về một `String` cho một dòng và **loại bỏ dấu xuống dòng** (`\n`, `\r`, hoặc `\r\n`) ở cuối. Nó tiện khi xử lý các dòng log, CSV đơn giản hoặc dữ liệu mà kết thúc dòng không cần giữ nguyên.

Nhưng trong một công cụ **sao chép văn bản chính xác**, nếu đọc từng dòng rồi ghi `writer.write(line)`, mọi dấu xuống dòng bị mất. Nếu ghi thêm `writer.newLine()`, dấu xuống dòng cũng có thể bị chuẩn hóa theo nền tảng, khác với nguồn ban đầu. Khi cần giữ đúng nội dung ký tự, sao chép bằng `read(char[])` và `write(char[], off, count)` như trên.

Ví dụ đầu vào:

~~~text
alpha\r\nbeta\n
~~~

Nếu chuỗi ký hiệu trên biểu diễn dữ liệu chứa `\r\n` sau `alpha` và `\n` sau `beta`, cách đọc/ghi từng khối char sẽ giữ nguyên chuỗi ký tự xuống dòng. Đọc bằng `readLine()` rồi gọi `newLine()` có thể thay đổi biểu diễn. Nếu mục tiêu là **chuẩn hóa** xuống dòng, đó lại là xử lý có chủ đích, nên ghi rõ trong hợp đồng chương trình.

## 11. Buffering, flush và close khi ghi dữ liệu từng phần

`BufferedReader` giảm số lần lấy dữ liệu từ nguồn bên dưới nhờ bộ đệm ký tự; `BufferedWriter` gom các lần ghi nhỏ trước khi đẩy tiếp xuống tầng bên dưới. Khi đã có `BufferedReader` hoặc `BufferedWriter`, dùng thêm một mảng `char[]` trong ứng dụng vẫn hợp lệ: mảng này có thể giúp thao tác theo khối và kiểm soát phần dữ liệu hợp lệ.

**`writer.write(...)` thành công không đồng nghĩa với dữ liệu đã nằm bền vững trên ổ đĩa.** Nếu writer có bộ đệm, dữ liệu có thể đang chờ trong bộ nhớ.

- `flush()` đẩy nội dung đang giữ trong bộ đệm writer xuống tầng tiếp theo theo hợp đồng của lớp; không bảo đảm dữ liệu đã được đồng bộ bền vững xuống thiết bị vật lý.
- `close()` kết thúc quyền sử dụng tài nguyên; với `BufferedWriter`, đóng cũng chuyển phần dữ liệu còn đệm xuống writer bên dưới rồi đóng nó.
- `try-with-resources` giúp gọi `close()` trên cả đường thành công lẫn ngoại lệ; nếu thân `try` và `close()` đều lỗi, lỗi đóng có thể được gắn dưới dạng suppressed exception.
- Với `StringWriter`, dữ liệu ở RAM và `close()` không ảnh hưởng đến nội dung, nhưng kiểu sở hữu vẫn nên được thể hiện nhất quán.

Nếu một hàm **nhận** `Writer` của bên gọi, thường không nên tự đóng nó trừ khi hợp đồng giao quyền sở hữu rõ ràng. Đóng wrapper như `BufferedWriter` thường đóng cả writer bên dưới; điều này đặc biệt quan trọng khi bên gọi tiếp tục dùng tài nguyên sau khi hàm hoàn thành.

## 12. Các lỗi phổ biến khi xử lý từng phần

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `writer.write(buffer)` sau mỗi `read(buffer)` | Lượt cuối có thể đọc ít hơn độ dài mảng; ghi thừa phần cũ | `writer.write(buffer, 0, count)` |
| `new String(buffer)` ở mọi lượt | Lấy cả phần mảng chưa chứa dữ liệu mới | `new String(buffer, 0, count)` |
| Dùng `len` làm chỉ số kết thúc cho `write(String, off, len)` | API yêu cầu độ dài, không phải end index | Tính `len = endExclusive - start` |
| Tưởng `read(buffer)` chắc chắn điền đầy mảng | Reader có thể trả về số dương nhỏ hơn yêu cầu | Lặp cho đến EOF hoặc đủ độ dài giao thức |
| Chỉ cần `ready() == false` là kết thúc | “Chưa sẵn sàng” không đồng nghĩa EOF | Dựa vào `read() == -1` |
| Nối nhiều khối qua `result += chunk` | Tạo nhiều String trung gian, gây tốn bộ nhớ | Dùng `StringBuilder` hoặc ghi trực tiếp |
| Ghi theo `readLine()` rồi quên xuống dòng | `readLine` loại bỏ dấu kết thúc dòng | Dùng char[] để bảo toàn hoặc ghi dòng có chủ đích |
| Xử lý mỗi `char` như một code point hoàn chỉnh | Emoji và ký tự ngoài BMP có cặp surrogate | Áp dụng thao tác Unicode có lưu trạng thái |
| Dùng charset mặc định khi chạy ở nhiều hệ | Văn bản có dấu có thể giải mã/mã hóa khác nhau | Chỉ định `StandardCharsets.UTF_8` hoặc charset của định dạng |
| Không đóng `BufferedReader`/`BufferedWriter` | Có thể rò rỉ tài nguyên hoặc mất dữ liệu đang đệm | Dùng `try-with-resources` theo quyền sở hữu |
| Giữ toàn bộ văn bản rất lớn trong một `String` | Tốn RAM và có thể vượt giới hạn mảng/heap | Xử lý trực tiếp từng phần |

### Checklist khi tự viết một vòng lặp đọc/ghi

Hãy tự trả lời trước khi chạy:

1. Mảng có kích thước lớn hơn 0 không?
2. Có kiểm tra kết quả `-1` để kết thúc hay không?
3. Có chỉ dùng đoạn `[offset, offset + count)` vừa đọc hay không?
4. Nếu cần đọc đúng N đơn vị, có xử lý EOF sớm không?
5. Nếu cần giữ nguyên văn bản, có tránh thao tác phá vỡ dấu xuống dòng và Unicode không?
6. Nếu nguồn là byte/tệp, charset có được xác định không?
7. Reader/Writer do ai mở và ai có trách nhiệm đóng?
8. Có phân biệt số đơn vị UTF-16, số code point và số byte khi báo cáo kết quả không?

## 13. Bài tập tự kiểm tra

**Bài tập 1 — Buffer chưa đầy.** Cho `char[] buffer = new char[5]`. Lượt đọc cuối trả về `2`. Nếu ghi cả mảng, điều gì xảy ra? **Đáp án:** chỉ hai phần tử đầu là dữ liệu mới, ba phần tử cuối có thể chứa dữ liệu cũ hoặc ký tự mặc định. Chỉ ghi `write(buffer, 0, 2)`.

**Bài tập 2 — off/len.** Với `String text = "ABCDEFGHIJ"`, lời gọi `writer.write(text, 3, 4)` ghi gì? **Đáp án:** `"DEFG"`; `off=3` là vị trí `D`, `len=4` là độ dài đoạn. Nếu dùng `append(text, 3, 4)` thì chỉ ghi `"D"`.

**Bài tập 3 — EOF bất ngờ.** Giao thức yêu cầu đọc đúng 10 ký tự nhưng Reader kết thúc sau 7. Có nên coi 7 là đủ? **Đáp án:** không, nếu hợp đồng đòi chính xác 10; cần báo lỗi thiếu dữ liệu. Nếu mục tiêu chỉ là “đọc hết những gì có”, 7 ký tự trước EOF có thể là kết quả hợp lệ.

**Bài tập 4 — Unicode.** `"A😀B".length()` bằng bao nhiêu, và tại sao? **Đáp án:** 4 đơn vị UTF-16; emoji chiếm hai đơn vị. Nếu muốn số code point thì dùng `codePointCount(0, text.length())`, kết quả 3.

**Bài tập 5 — Giữ nguyên xuống dòng.** Vì sao `readLine` → `write(line)` không phải thuật toán sao chép nguyên vẹn? **Đáp án:** `readLine` bỏ các ký tự kết thúc dòng, nên luồng ghi không nhận được những ký tự đó; việc tự thêm `newLine` có thể thay đổi kiểu xuống dòng.

**Thực hành mở rộng:** sửa `CharChunkDemo` để buffer dài 2 và nguồn là một chuỗi có dấu/emoji; quan sát từng lượt đọc mà không giả định ranh giới khối là ranh giới code point. Tiếp tục sửa `CopyTextChunksDemo` để xử lý văn bản có cả `\r\n` và `\n`, rồi so sánh `text.equals(copied)`. Cuối cùng thử thay vòng lặp sao chép bằng `reader.transferTo(writer)`, vẫn dùng `try-with-resources` cho hai tài nguyên.

## Tóm tắt kiến thức cốt lõi

- `read(char[])` nhận tối đa kích thước mảng và trả về **số đơn vị ký tự thực sự đọc**, hoặc `-1` khi EOF. Không có cam kết mỗi lần đọc đầy mảng.
- `read(char[], off, len)`, `write(char[], off, len)` và `write(String, off, len)` dùng **offset và độ dài**; `append(CharSequence, start, end)` và `substring(begin, end)` dùng **chỉ số kết thúc loại trừ**.
- Tái sử dụng `char[]` với `write(buffer, 0, count)` là cách căn bản để xử lý văn bản dài theo từng phần mà không vô tình thêm ký tự cũ.
- `String` thích hợp cho dữ liệu đã tích lũy; `StringBuilder` để nối khối trong RAM; khi có thể, truyền trực tiếp từ Reader sang Writer để tránh giữ toàn bộ nội dung.
- `char`/`count` đo **đơn vị UTF-16**; các ký tự Unicode có thể trải qua nhiều `char`, và ranh giới buffer không phải ranh giới văn bản.
- Charset, dấu xuống dòng, bộ đệm, `flush` và `close` quyết định tính đúng đắn khi dữ liệu đi giữa bộ nhớ và hệ thống tệp.

### Tài liệu API tham khảo

- [Reader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Reader.html)
- [Writer — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Writer.html)
- [BufferedReader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html)
- [BufferedWriter — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedWriter.html)
- [Files — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [StringBuilder — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html)
