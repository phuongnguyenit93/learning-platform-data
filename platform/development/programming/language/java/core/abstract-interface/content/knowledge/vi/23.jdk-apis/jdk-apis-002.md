# InputStream, Reader và các lớp con cụ thể trong Java

Java cung cấp hai họ API chính để đọc dữ liệu: `InputStream` đọc **byte**, còn `Reader` đọc **ký tự**. Chọn đúng họ API giúp xử lý tệp nhị phân, văn bản có dấu, dữ liệu lớn và tài nguyên hệ thống một cách chính xác.

## 1. Phân biệt byte stream và character stream

| Tiêu chí | `InputStream` | `Reader` |
|---|---|---|
| Đơn vị đọc | Byte, giá trị trả về nằm trong khoảng 0–255 khi đọc một byte đơn | Đơn vị mã UTF-16 (`char`), giá trị trả về nằm trong khoảng 0–65535 khi đọc một ký tự đơn |
| Mục đích thường gặp | Ảnh, PDF, âm thanh, tệp nén, dữ liệu nhị phân, hoặc byte chưa giải mã | Văn bản cần giải mã thành ký tự |
| Phương thức đọc cơ bản | `int read()`, `int read(byte[] b)` | `int read()`, `int read(char[] cbuf)` |
| Báo hết dữ liệu | `-1` | `-1` |
| Lớp chuyển đổi quan trọng | `InputStreamReader` biến byte thành ký tự bằng một charset | `OutputStreamWriter` là lớp ghi ở chiều ngược lại, chuyển ký tự thành byte |

Java `char` là một đơn vị mã UTF-16, không phải lúc nào cũng tương đương một ký tự Unicode hoàn chỉnh. Một số ký tự ngoài Basic Multilingual Plane được biểu diễn bằng một cặp surrogate. Với xử lý văn bản thông thường, hãy dùng `Reader` và các API chuỗi; đừng tự giả định rằng số byte, số `char` và số ký tự người dùng nhìn thấy luôn bằng nhau.

**Quy tắc chọn nhanh:** dùng `InputStream` khi cần byte nguyên bản; dùng `Reader` khi cần văn bản đã giải mã. Không chuyển dữ liệu nhị phân qua `Reader`, vì quá trình giải mã có thể làm thay đổi ý nghĩa của byte.

## 2. Những lớp InputStream thường gặp

Các lớp trong JDK có vai trò khác nhau:

- **`FileInputStream`** đọc byte từ một tệp. Phù hợp khi cần truy cập byte trực tiếp; nếu mục tiêu là văn bản, hãy kết hợp với `InputStreamReader` hoặc dùng API `Files`.
- **`ByteArrayInputStream`** đọc từ một mảng byte trong bộ nhớ. Hữu ích cho ví dụ, kiểm thử và xử lý dữ liệu đã có sẵn.
- **`BufferedInputStream`** thêm bộ đệm để giảm số lần truy cập nguồn dữ liệu khi đọc từng phần nhỏ.
- **`DataInputStream`** đọc các kiểu dữ liệu nhị phân nguyên thủy như `int`, `long`, `boolean` theo định dạng mà chương trình đã thống nhất. Nó không tự biến byte thành văn bản và không phải định dạng lưu trữ có schema.
- **`ObjectInputStream`** đọc đối tượng đã được tuần tự hóa bằng Java Serialization. Chỉ dùng dữ liệu đáng tin cậy hoặc có bộ lọc phù hợp; không xem dữ liệu serialization tùy ý là an toàn.
- **`PipedInputStream`** nhận byte từ một `PipedOutputStream`, thường dùng khi hai luồng thực thi cần trao đổi dữ liệu.
- **`SequenceInputStream`** đọc tuần tự từ nhiều nguồn `InputStream` như thể chúng được nối lại.

Ví dụ đọc byte từ bộ nhớ:

```java
byte[] data = {10, 20, 30};

try (InputStream input = new ByteArrayInputStream(data)) {
    int value;
    while ((value = input.read()) != -1) {
        System.out.println(value);
    }
}
```

Output:

```text
10
20
30
```

`read()` trả về `int` thay vì `byte` để có thể biểu diễn mọi giá trị byte không dấu từ 0 đến 255 và dành `-1` cho EOF (end of stream). Nếu ép ngay kết quả thành `byte`, giá trị lớn hơn 127 có thể trở thành số âm.

## 3. Những lớp Reader thường gặp

- **`InputStreamReader`** là cầu nối giữa byte stream và character stream. Nó giải mã byte bằng charset được chỉ định.
- **`FileReader`** đọc ký tự từ tệp. Với mã mới, nên chỉ định charset tường minh bằng constructor có charset (Java 11+) hoặc dùng `Files.newBufferedReader(path, charset)`.
- **`BufferedReader`** thêm bộ đệm và cung cấp `readLine()`, thuận tiện khi xử lý văn bản theo từng dòng.
- **`StringReader`** đọc văn bản từ một đối tượng `String`, hữu ích khi kiểm thử parser mà không cần tạo tệp.
- **`CharArrayReader`** đọc từ mảng `char`.
- **`PushbackReader`** cho phép đẩy một số ký tự vừa đọc trở lại luồng, thường hữu ích khi viết parser cần nhìn trước một ký tự.

Ví dụ đọc từng dòng từ chuỗi:

```java
String text = "alpha\nbeta\n";

try (BufferedReader reader = new BufferedReader(new StringReader(text))) {
    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
```

Output:

```text
alpha
beta
```

`readLine()` bỏ dấu kết thúc dòng khỏi giá trị trả về. Nó trả về `null` khi đã hết dữ liệu và không còn dòng nào để đọc; vì vậy vòng lặp đúng thường có dạng `while ((line = reader.readLine()) != null)`.

## 4. Charset: bước quan trọng khi đọc văn bản

Tệp văn bản lưu byte theo một encoding cụ thể, ví dụ UTF-8. `Reader` làm việc với ký tự, nên cần giải mã byte bằng charset phù hợp. Nếu dùng charset khác với charset đã dùng để ghi, văn bản có thể thành ký tự lỗi hoặc mojibake.

Nên chỉ định charset rõ ràng:

```java
Path path = Path.of("message.txt");

try (BufferedReader reader =
         Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
```

Đoạn này cần các import `java.io.BufferedReader`, `java.nio.charset.StandardCharsets`, `java.nio.file.Files` và `java.nio.file.Path`.

Một cách khác khi nguồn đã là `InputStream`:

```java
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(inputStream, StandardCharsets.UTF_8))) {
    // Đọc văn bản từ reader
}
```

Trong ví dụ thứ hai, `inputStream` phải là một biến `InputStream` đang mở và được quản lý đúng cách. `InputStreamReader` thực hiện giải mã; `BufferedReader` thêm bộ đệm và tiện ích đọc theo dòng.

Không nên dựa vào charset mặc định của máy để đọc dữ liệu có định dạng đã biết. Khi đọc tệp do một hệ thống khác tạo ra, charset là một phần của giao thức dữ liệu và cần được thống nhất rõ ràng.

## 5. Đọc theo khối và dùng buffering

Đọc từng byte hoặc từng ký tự một có thể gây nhiều lời gọi phương thức. Với dữ liệu lớn, thường nên đọc theo mảng hoặc dùng lớp buffered.

```java
try (InputStream input = new BufferedInputStream(
        Files.newInputStream(Path.of("image.bin")))) {
    byte[] buffer = new byte[8192];
    int count;

    while ((count = input.read(buffer)) != -1) {
        // Xử lý buffer[0] đến buffer[count - 1].
        // Không xử lý toàn bộ mảng nếu count nhỏ hơn buffer.length.
    }
}
```

`count` là số byte hợp lệ trong lần đọc hiện tại. Lần cuối có thể đọc ít hơn kích thước mảng. Các byte phía sau `count - 1` có thể còn dữ liệu cũ từ lần đọc trước, nên chỉ xử lý phần vừa được báo là đã đọc.

Đối với văn bản, hãy dùng bộ đệm ở tầng phù hợp, ví dụ `BufferedReader`. Nó có thể giảm thao tác I/O và cung cấp `readLine()`. Không cần bọc thêm nhiều lớp buffering một cách máy móc; chọn cấu trúc đơn giản phù hợp với nguồn và cách đọc.

Một số phương thức tiện dụng có từ Java 9:

- `InputStream.readAllBytes()` đọc toàn bộ phần còn lại thành mảng byte.
- `InputStream.readNBytes(n)` đọc tối đa số byte yêu cầu.
- `InputStream.transferTo(out)` chuyển byte sang một `OutputStream`.
- `Reader.transferTo(writer)` chuyển ký tự sang một `Writer`.

Các phương thức đọc toàn bộ chỉ nên dùng khi kích thước dữ liệu phù hợp với bộ nhớ. Với tệp lớn hoặc luồng không có giới hạn rõ ràng, đọc theo khối thường an toàn hơn.

## 6. Quản lý tài nguyên bằng try-with-resources

Luồng có thể giữ file descriptor, socket hoặc tài nguyên hệ thống khác. Đóng luồng khi dùng xong là một phần của việc xử lý đúng.

```java
try (InputStream input = Files.newInputStream(Path.of("data.bin"))) {
    // Đọc dữ liệu
}
```

Khi rời khỏi khối `try`, Java tự gọi `close()`, kể cả khi phát sinh ngoại lệ. `Reader` cũng triển khai `Closeable`/ `AutoCloseable` và dùng được theo cách tương tự.

Đóng wrapper thường đóng luôn luồng bên dưới. Chẳng hạn đóng `BufferedReader` sẽ đóng `InputStreamReader` và `InputStream` mà nó bao bọc. Vì vậy, tránh đóng đi đóng lại các lớp lồng nhau không cần thiết; hãy xác định rõ nơi sở hữu và chịu trách nhiệm đóng tài nguyên.

Không nên nuốt ngoại lệ I/O rồi giả vờ dữ liệu đã đọc thành công. Tùy ứng dụng, hãy xử lý hoặc truyền tiếp `IOException` để caller có thể phản ứng với lỗi tệp, quyền truy cập hoặc kết nối.

## 7. Ví dụ Java 17+ chạy hoàn chỉnh

Chương trình dưới đây dùng cùng một nội dung UTF-8 để cho thấy `InputStream` đếm byte, còn `Reader` giải mã thành văn bản. Lưu tệp với tên `StreamReaderDemo.java`.

```java
import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;

public class StreamReaderDemo {
    public static void main(String[] args) throws Exception {
        String text = "Xin chào\nJava 17\n";
        byte[] encoded = text.getBytes(StandardCharsets.UTF_8);

        int totalBytes = 0;
        try (InputStream input = new ByteArrayInputStream(encoded)) {
            byte[] buffer = new byte[4];
            int count;
            while ((count = input.read(buffer)) != -1) {
                totalBytes += count;
            }
        }
        System.out.println("UTF-8 bytes: " + totalBytes);

        try (Reader decoded = new InputStreamReader(
                    new ByteArrayInputStream(encoded),
                    StandardCharsets.UTF_8);
             BufferedReader reader = new BufferedReader(decoded)) {
            String line;
            while ((line = reader.readLine()) != null) {
                System.out.println("Line: " + line);
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac StreamReaderDemo.java
java StreamReaderDemo
```

Stdout chính xác:

```text
UTF-8 bytes: 18
Line: Xin chào
Line: Java 17
```

Giải thích:

1. `getBytes(StandardCharsets.UTF_8)` mã hóa chuỗi thành byte UTF-8.
2. Vòng lặp `InputStream.read(buffer)` cộng số byte thực sự đọc được, không cộng kích thước toàn bộ mảng mỗi lần.
3. `InputStreamReader` giải mã cùng mảng byte bằng đúng UTF-8.
4. `BufferedReader.readLine()` trả về từng dòng mà không giữ ký tự xuống dòng.
5. `try-with-resources` tự đóng các luồng. Trong khối thứ hai, đóng `BufferedReader` cũng đóng `Reader` mà nó bao bọc.

Chuỗi mẫu có chữ `à`, được mã hóa UTF-8 thành hai byte; vì thế số byte UTF-8 không nhất thiết bằng số ký tự trong văn bản.

## 8. Lỗi thường gặp

- **Dùng `InputStream` như thể nó đọc văn bản:** byte không tự động là ký tự. Hãy giải mã bằng `InputStreamReader` với charset đúng.
- **Không chỉ định charset:** kết quả có thể phụ thuộc môi trường hoặc không khớp định dạng của tệp. Dùng UTF-8 khi đó là encoding của dữ liệu.
- **Giả định một lần `read(byte[])` sẽ lấp đầy mảng:** một lần đọc có thể trả về ít byte hơn mong đợi. Luôn dùng giá trị trả về để xác định phần hợp lệ.
- **Quên EOF:** `read()` trả về `-1` khi hết dữ liệu; không kiểm tra EOF có thể gây vòng lặp sai hoặc lặp vô hạn.
- **Xem `available()` là kích thước còn lại của tệp:** phương thức này chỉ ước lượng số byte có thể đọc hoặc bỏ qua mà không bị chặn; không dùng nó để cấp phát mảng chứa toàn bộ dữ liệu.
- **Không đóng luồng:** tài nguyên có thể bị giữ lại lâu hơn cần thiết. Dùng try-with-resources.
- **Đọc toàn bộ tệp lớn vào bộ nhớ:** `readAllBytes()` và các cách tương tự có thể tiêu tốn nhiều bộ nhớ. Ưu tiên đọc theo khối với dữ liệu lớn.
- **Dùng `readLine()` rồi mong nhận lại dấu xuống dòng:** phương thức loại bỏ dấu kết thúc dòng. Nếu định dạng yêu cầu giữ nguyên byte hoặc newline, xử lý ở tầng byte hoặc dùng API phù hợp.
- **Tin cậy dữ liệu Java Serialization không rõ nguồn:** `ObjectInputStream` có thể khởi tạo đối tượng khi đọc. Không deserialize dữ liệu không đáng tin cậy nếu không có biện pháp bảo vệ phù hợp.

## 9. Checklist lựa chọn API

- Cần byte chính xác của ảnh, PDF, tệp nén hoặc dữ liệu nhị phân: `InputStream`.
- Cần đọc ký tự từ byte theo UTF-8: `InputStreamReader` với charset tường minh.
- Cần đọc văn bản theo dòng: bọc `Reader` bằng `BufferedReader`.
- Cần đọc từ tệp văn bản: cân nhắc `Files.newBufferedReader(path, charset)`.
- Cần đọc từ chuỗi trong bộ nhớ: `StringReader`.
- Cần đọc từ mảng byte trong bộ nhớ: `ByteArrayInputStream`.
- Cần xử lý dữ liệu lớn: đọc theo khối, chỉ dùng số byte hoặc ký tự thực sự được trả về, và đóng tài nguyên bằng try-with-resources.

Điểm cốt lõi là xác định dữ liệu đang ở dạng byte hay văn bản, chọn đúng lớp chuyển đổi, khai báo charset khi giải mã và quản lý vòng đời luồng một cách rõ ràng.