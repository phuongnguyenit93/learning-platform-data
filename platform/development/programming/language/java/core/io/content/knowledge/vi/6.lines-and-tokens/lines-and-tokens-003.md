# BufferedWriter.newLine và System.lineSeparator trong Java

Khi ghi văn bản nhiều dòng, ta phải phân biệt **nội dung ký tự**, **dấu kết thúc dòng (line separator)** và **bộ đệm ghi**. Hai API Java có liên quan trực tiếp là `BufferedWriter.newLine()` và `System.lineSeparator()`:

- `BufferedWriter.newLine()` **ghi một chuỗi ký tự kết thúc dòng** theo quy ước của nền tảng vào luồng ký tự đang mở.
- `System.lineSeparator()` **trả về một `String`** chứa chuỗi kết thúc dòng theo quy ước của nền tảng; chỉ gọi phương thức này **không ghi gì**.
- Cả hai phù hợp khi muốn tạo file văn bản **theo quy ước xuống dòng của môi trường chạy**. Nếu một định dạng/giao thức bắt buộc đúng `\n` hoặc `\r\n`, phải ghi chính xác chuỗi do chuẩn đó yêu cầu, không chọn tự động theo hệ điều hành.

Bài học nằm trong chủ đề **Dòng và token** của Java I/O: hiểu cách tách các dòng văn bản và không làm sai dữ liệu khi ghi, đọc lại hoặc trao đổi file giữa các hệ điều hành.

## 1. Line separator là gì?

Trong văn bản, một dấu xuống dòng thường được biểu diễn bằng một hoặc nhiều ký tự điều khiển:

| Biểu diễn Java | Tên | Thường gặp |
| --- | --- | --- |
| `"\n"` | LF, Line Feed, mã `U+000A` | Unix/Linux, macOS hiện đại |
| `"\r\n"` | CRLF, Carriage Return + Line Feed | Windows |
| `"\r"` | CR, Carriage Return, mã `U+000D` | Một số định dạng và hệ thống cũ |

Ví dụ hai chuỗi này hiển thị tương tự trên nhiều công cụ, nhưng **khác nhau ở số ký tự và byte**:

```java
String lf = "Một\nHai";      // "Một" + LF + "Hai"
String crlf = "Một\r\nHai";  // "Một" + CRLF + "Hai"
```

Đây là hai khai báo minh họa có thể đặt trong một phương thức Java. Số ký tự điều khiển và byte thực tế phụ thuộc vào cách mã hóa văn bản ra file; chẳng hạn khi mã hóa UTF-8, LF chiếm 1 byte `0A`, còn CRLF chiếm 2 byte `0D 0A`.

**Lưu ý:** “Dòng mới” trong văn bản không phải một đối tượng Java riêng. `BufferedWriter` chỉ ghi ký tự; `BufferedReader` có thể diễn giải các dấu kết thúc dòng khi đọc. Một dòng cuối không kết thúc bằng dấu xuống dòng vẫn là nội dung dòng hợp lệ trong nhiều định dạng văn bản.

## 2. `BufferedWriter.newLine()` làm gì?

`BufferedWriter` là một `Writer` có bộ đệm để giảm số lần ghi xuống luồng bên dưới. Khi gọi:

```java
writer.newLine();
```

`BufferedWriter` ghi chuỗi kết thúc dòng mà nó lấy theo quy ước nền tảng, được Java mô tả qua thuộc tính hệ thống `line.separator`. Điều này **không bảo đảm luôn là một ký tự `'\n'`**: trên Windows thông thường là `"\r\n"`, trên Unix/Linux thông thường là `"\n"`.

Đoạn minh họa:

```java
writer.write("Dòng thứ nhất");
writer.newLine();
writer.write("Dòng thứ hai");
```

Nếu môi trường dùng LF, kết quả về mặt ký tự là `"Dòng thứ nhất\nDòng thứ hai"`. Nếu dùng CRLF, nó là `"Dòng thứ nhất\r\nDòng thứ hai"`. `newLine()` **không tự động thêm khoảng trắng**, **không ghi nội dung của dòng kế tiếp** và **không gọi `flush()`** chỉ vì đã xuống dòng.

### Cú pháp và ngoại lệ

`newLine()` là phương thức thể hiện trong `java.io.BufferedWriter`, trả về `void` và có thể ném `IOException`:

```java
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.Writer;

// Phương thức minh họa; tham số đích là Writer đã được mở.
static void writeTwoLines(Writer destination) throws IOException {
    try (BufferedWriter writer = new BufferedWriter(destination)) {
        writer.write("Alpha");
        writer.newLine();
        writer.write("Beta");
    }
}
```

**Quyền sở hữu luồng:** đóng `BufferedWriter` sẽ đóng `Writer` bên dưới. Phương thức này chỉ nên dùng khi nó **được phép đóng** `destination`. Nếu tầng gọi vẫn cần dùng luồng đã truyền vào, cần thống nhất rõ chủ sở hữu và vòng đời.

### `newLine()` có tự tạo dòng trống không?

Về cơ bản, `newLine()` chỉ ghi **một dấu kết thúc dòng**. Nếu viết:

```java
writer.write("A");
writer.newLine();
writer.newLine();
writer.write("B");
```

sẽ xuất hiện một dòng trống giữa A và B. Ngược lại, nếu gọi `newLine()` sau dòng cuối cùng, file sẽ **kết thúc bằng dấu xuống dòng**. Có cần dấu xuống dòng ở cuối file hay không phụ thuộc quy ước của định dạng, công cụ hoặc dự án.

## 3. `System.lineSeparator()` trả về gì?

`System.lineSeparator()` là phương thức tĩnh của `java.lang.System`, trả về chuỗi dấu xuống dòng phụ thuộc nền tảng:

```java
String separator = System.lineSeparator();

String content = "Alpha" + separator + "Beta";
// Chỉ tạo String, chưa ghi ra file hoặc OutputStream.
```

Có thể kết hợp với `StringBuilder`, `String.join` hoặc một `Writer` bất kỳ:

```java
String content = String.join(
        System.lineSeparator(),
        "Dòng 1", "Dòng 2", "Dòng 3"
);
```

Hoặc:

```java
writer.write("Dòng 1");
writer.write(System.lineSeparator());
writer.write("Dòng 2");
```

Các đoạn minh họa này giả định `writer` đã tồn tại. `System.lineSeparator()` thích hợp khi cần **tạo một giá trị String chứa các dấu xuống dòng theo môi trường**, còn `BufferedWriter.newLine()` ngắn gọn hơn khi đang ghi trực tiếp bằng `BufferedWriter`.

Theo tài liệu Java, giá trị `System.lineSeparator()` dựa trên giá trị ban đầu của thuộc tính `line.separator` và giữ ổn định trong thời gian chạy. **Không sửa `System.setProperty("line.separator", ...)` ở giữa chương trình để cố đổi định dạng file**: đây không phải cách thiết kế định dạng đầu ra đáng tin cậy. Khi cần LF hoặc CRLF cố định, hãy dùng chuỗi tường minh.

## 4. So sánh và lựa chọn

| Tiêu chí | `BufferedWriter.newLine()` | `System.lineSeparator()` |
| --- | --- | --- |
| Loại API | Phương thức của một `BufferedWriter` | Phương thức tĩnh của `System` |
| Kết quả | **Ghi** dấu kết thúc dòng vào writer | **Trả về `String`**, chưa ghi |
| Giá trị trả về | `void` | `String` |
| Ngoại lệ thường gặp | `IOException` khi ghi | Không khai báo `IOException` |
| Khi dùng | Đang ghi dòng qua `BufferedWriter` | Đang ghép `String` hoặc ghi qua API khác |
| Tính phụ thuộc môi trường | Theo line separator của môi trường | Theo line separator của môi trường |
| Khi phải xuất LF hoặc CRLF cố định | Không phải lựa chọn phù hợp | Không phải lựa chọn phù hợp |

Nếu chương trình **ghi nhiều dòng trực tiếp vào file**, `BufferedWriter.newLine()` dễ đọc:

```java
writer.write("Tên: An");
writer.newLine();
writer.write("Tuổi: 20");
```

Nếu chương trình **xây dựng nội dung văn bản trước**, `System.lineSeparator()` tiện lợi:

```java
String report = "Tên: An"
        + System.lineSeparator()
        + "Tuổi: 20";
```

Khi cả hai dùng cùng quy ước nền tảng trong một chương trình Java thông thường, nội dung dấu xuống dòng tương ứng là như nhau. Khác biệt quan trọng là **một API thực hiện ghi**, còn API kia **cung cấp chuỗi ký tự**.

## 5. Chương trình Java 17+ hoàn chỉnh và chạy được

Ví dụ dưới đây ghi ba dòng vào `StringWriter` qua `BufferedWriter`. Sau khi writer được đóng, chương trình kiểm tra chuỗi nhận được có giống cách ghép bằng `System.lineSeparator()` không, xác nhận chính xác ba dòng bằng `BufferedReader.readLine()`, và kiểm tra có thêm dấu xuống dòng ở cuối hay không.

Lưu đúng tên file **`LineSeparatorDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.StringReader;
import java.io.StringWriter;

public class LineSeparatorDemo {

    public static void main(String[] args) throws IOException {
        StringWriter destination = new StringWriter();

        try (BufferedWriter writer = new BufferedWriter(destination)) {
            writer.write("Dòng một");
            writer.newLine();
            writer.write("Dòng hai");
            writer.newLine();
            writer.write("Dòng ba");
        }

        String actual = destination.toString();
        String expected = String.join(
                System.lineSeparator(),
                "Dòng một", "Dòng hai", "Dòng ba"
        );

        System.out.println("Matches platform separator: " +
                actual.equals(expected));
        System.out.println("Logical line count: " +
                countLines(actual));
        System.out.println("Ends with separator: " +
                actual.endsWith(System.lineSeparator()));
    }

    private static int countLines(String text) throws IOException {
        int count = 0;

        try (BufferedReader reader =
                     new BufferedReader(new StringReader(text))) {
            while (reader.readLine() != null) {
                count++;
            }
        }

        return count;
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 LineSeparatorDemo.java
java LineSeparatorDemo
```

**Stdout trên các môi trường thông thường dùng LF hoặc CRLF:**

```text
Matches platform separator: true
Logical line count: 3
Ends with separator: false
```

**Vì sao ra kết quả này?**

1. `writer.newLine()` được gọi **hai lần**, giữa các dòng, nên chuỗi có ba dòng logic.
2. `String.join(System.lineSeparator(), ...)` cũng chèn đúng hai separator tương ứng; so sánh trả `true`.
3. `BufferedReader.readLine()` trả lần lượt `"Dòng một"`, `"Dòng hai"`, `"Dòng ba"`, rồi `null` khi hết dữ liệu. Nó bỏ ký tự kết thúc dòng ra khỏi từng kết quả.
4. Dòng cuối `"Dòng ba"` không được theo sau bởi `newLine()` nên `endsWith(separator)` là `false`.

Ví dụ dùng `StringWriter` để quan sát nội dung mà không cần tạo file thật. `StringWriter` lưu ký tự trong bộ nhớ; đóng `BufferedWriter` sẽ gọi đóng writer dưới, nhưng với `StringWriter`, ta vẫn có thể lấy nội dung đã ghi qua `toString()`.

### Nhìn rõ LF và CRLF khi gỡ lỗi

Không nên dùng mắt để đoán separator vì console hoặc editor có thể hiển thị cả LF và CRLF gần như giống nhau. Với chuỗi văn bản đã có:

```java
String visible = actual
        .replace("\r", "\\r")
        .replace("\n", "\\n");
System.out.println(visible);
```

Đặt đoạn mã vào `main` của ví dụ sau khi tạo `actual`. Với LF, sẽ thấy:

```text
Dòng một\nDòng hai\nDòng ba
```

Với CRLF, sẽ thấy:

```text
Dòng một\r\nDòng hai\r\nDòng ba
```

Đây là **hiển thị minh họa phụ thuộc nền tảng**, không phải hai dòng stdout xuất hiện đồng thời.

## 6. Ghi file UTF-8 theo dòng

`BufferedWriter` xử lý **ký tự và bộ đệm**; charset như UTF-8 được xác định khi nối tới luồng byte của file. Với Java NIO, cách rõ ràng là:

```java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public static void writeReport(Path path) throws IOException {
    try (BufferedWriter writer = Files.newBufferedWriter(
            path, StandardCharsets.UTF_8)) {
        writer.write("Tiêu đề");
        writer.newLine();
        writer.write("Nội dung tiếng Việt");
        writer.newLine();
    }
}
```

Đây là **phương thức minh họa**, phải đặt bên trong một class. `Files.newBufferedWriter(path, StandardCharsets.UTF_8)` tạo buffered writer mã hóa ký tự theo UTF-8, còn `writer.newLine()` chọn ký tự xuống dòng theo môi trường chạy. Hai quyết định **độc lập**:

- **Charset UTF-8** quyết định cách chuyển ký tự Unicode thành byte.
- **Line separator** quyết định chèn LF, CRLF hay chuỗi dấu xuống dòng được quy ước.

Với tùy chọn mặc định, `Files.newBufferedWriter` tạo file nếu chưa có hoặc cắt ngắn nội dung nếu file đã tồn tại. Cần xác định chính sách ghi đè nếu báo cáo cũ phải được lưu lại.

Trong ví dụ này, vì gọi `newLine()` sau dòng `"Nội dung tiếng Việt"`, file **có dấu kết thúc dòng ở cuối**. Điều đó có thể là quy ước mong muốn đối với file dạng dòng; nếu định dạng đầu ra yêu cầu không có dấu xuống dòng sau nội dung cuối, hãy bỏ lần gọi đó.

## 7. Buffer, `flush()` và `close()`

`BufferedWriter` giữ dữ liệu trong bộ đệm; không có bảo đảm rằng mỗi lệnh `write` hoặc `newLine` lập tức tạo thay đổi quan sát được ở file đích.

- `writer.write(...)` ghi ký tự vào writer; nội dung có thể còn nằm trong bộ đệm.
- `writer.newLine()` ghi chuỗi xuống dòng vào writer, **không tự động flush**.
- `writer.flush()` đẩy dữ liệu đang đệm qua các tầng writer bên dưới. Nó **không đồng nghĩa** với bảo đảm dữ liệu đã được ghi bền vững xuống thiết bị lưu trữ.
- `writer.close()` đóng writer, flush phần còn đệm trong quá trình đóng, và giải phóng tài nguyên. `try-with-resources` giúp gọi close kể cả khi có ngoại lệ.

Ví dụ khi cần quan sát dữ liệu trước khi đóng writer:

```java
writer.write("Trạng thái: đang chạy");
writer.newLine();
writer.flush();  // Cần khi bên nhận phải nhìn thấy dữ liệu ngay.
```

Không nên `flush()` sau **mọi** dòng nếu không cần, vì có thể làm giảm lợi ích của buffering. Với file thông thường, đóng đúng bằng `try-with-resources` ở cuối tác vụ thường là đủ.

## 8. Khi nào phải ghi `"\n"` hoặc `"\r\n"` tường minh?

Đây là khác biệt đặc biệt quan trọng khi chương trình Java xuất dữ liệu để hệ thống khác đọc. Không phải định dạng nào cũng sử dụng line separator của máy đang chạy.

**Khi định dạng hoặc protocol yêu cầu một kiểu kết thúc dòng cụ thể**, hãy ghi kiểu đó đúng theo chuẩn:

```java
writer.write("line 1");
writer.write("\n");    // LF cố định, bất kể hệ điều hành.
writer.write("line 2");
```

Hoặc khi giao thức yêu cầu CRLF:

```java
writer.write("Header: value");
writer.write("\r\n");  // CRLF cố định.
```

Các đoạn trên là minh họa cần `writer` đã mở. Ví dụ header HTTP/1.1 ở tầng giao thức có quy tắc CRLF riêng; trong ứng dụng thực tế nên để thư viện HTTP quản lý định dạng thông điệp thay vì tự ghép chuỗi protocol.

Các tình huống điển hình:

| Nhu cầu | Cách chọn dấu xuống dòng |
| --- | --- |
| File ghi chú, báo cáo trên máy người dùng, theo quy ước nền tảng | `writer.newLine()` hoặc `System.lineSeparator()` |
| File được chuẩn hóa LF để dùng cùng trong nhiều môi trường | `"\n"` tường minh hoặc chuẩn hóa output |
| Protocol yêu cầu CRLF | `"\r\n"` tường minh hoặc API protocol chuyên dụng |
| File đầu ra cần giữ nguyên kết thúc dòng của file nguồn | Phải đọc và lưu lại chính xác separator đã có, không đọc theo `readLine()` rồi tự chọn lại |
| Tạo `String` nhiều dòng cho ứng dụng theo nền tảng | `String.join(System.lineSeparator(), lines)` |
| Dữ liệu dạng nhị phân | Dùng luồng byte; `newLine()` không có ý nghĩa |

**Không dùng `System.lineSeparator()` như một cách dự đoán line ending của file bên ngoài.** Một file tạo trên Linux vẫn có thể chứa CRLF, và một file tạo trên Windows vẫn có thể chứa LF. Nguồn dữ liệu, chuẩn định dạng hoặc nội dung file mới quyết định ký tự có mặt trong file đó.

## 9. Đọc lại bằng `BufferedReader.readLine()` và giới hạn

`BufferedReader.readLine()` nhận diện các dòng kết thúc bởi LF, CR hoặc CRLF. Hàm trả chuỗi **không chứa ký tự kết thúc dòng**; `null` biểu thị EOF khi không còn dòng nào.

```java
try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý nội dung từng dòng, không kèm LF hay CRLF.
        System.out.println(line);
    }
}
```

Đoạn minh họa giả định `path` và các import `BufferedReader`, `Files`, `StandardCharsets` tồn tại. Một điểm cần nhớ là **đọc từng dòng làm mất thông tin separator ban đầu**:

```text
Nguồn 1: "A\nB"
Nguồn 2: "A\r\nB"
readLine() trên cả hai: "A", "B"
```

Vì vậy, nếu đọc bằng `readLine()` rồi ghi lại bằng `newLine()`, bạn có thể **chuẩn hóa hoặc thay đổi line ending**, dù chữ hiển thị không đổi. Đối với tác vụ cần giữ nguyên byte, ký tự xuống dòng hỗn hợp hoặc chữ ký/checksum của file, hãy đọc byte/ký tự và bảo toàn đúng dữ liệu gốc, không coi `readLine()` là phương pháp sao chép y nguyên.

Ngoài ra, dòng cuối **không có** dấu kết thúc dòng vẫn được `readLine()` trả về trước EOF, miễn có nội dung.

## 10. So với `PrintWriter.println()`, `System.out.println()` và `%n`

Một số API Java cũng cung cấp thao tác xuống dòng thuận tiện nhưng có hành vi riêng:

| API | Mục đích | Lưu ý |
| --- | --- | --- |
| `BufferedWriter.newLine()` | Ghi line separator vào `BufferedWriter` | Có `IOException`; không tự flush |
| `System.lineSeparator()` | Trả về `String` separator | Không thực hiện I/O |
| `PrintWriter.println(...)` | Ghi giá trị và kết thúc dòng | `PrintWriter` thường lưu cờ lỗi thay vì ném `IOException` trực tiếp; kiểm tra `checkError()` khi cần |
| `System.out.println(...)` | In giá trị/dòng ra chuẩn stdout | Thường theo quy ước môi trường |
| `String.format("A%nB")` | Định dạng chuỗi với dấu xuống dòng theo nền tảng | `%n` là format specifier, khác với `\n` cố định |

`PrintWriter` có các constructor/tùy chọn auto-flush; hành vi tự flush khi `println` phụ thuộc việc auto-flush được bật. **Không suy ra rằng `BufferedWriter.newLine()` có auto-flush như một số `PrintWriter`.**

Nếu cần xử lý `IOException` rõ ràng khi ghi file và muốn biết lúc nào flush, `BufferedWriter` là lựa chọn dễ kiểm soát.

## 11. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách làm phù hợp |
| --- | --- | --- |
| Nghĩ `newLine()` luôn ghi `"\n"` | Kết quả có thể khác giữa Windows và Linux | Dùng `newLine()` khi muốn quy ước nền tảng; dùng literal khi chuẩn bắt buộc |
| Gọi `System.lineSeparator()` một mình rồi chờ file xuống dòng | Không có ký tự nào được ghi | `writer.write(System.lineSeparator())` hoặc `writer.newLine()` |
| Dùng `newLine()` để xuất định dạng yêu cầu CRLF cố định | File có thể sai trên môi trường LF | Ghi chính xác `"\r\n"` hoặc dùng thư viện giao thức |
| Gọi `newLine()` rồi tưởng dữ liệu đã flush | Người đọc khác có thể chưa thấy dòng | `flush()` ở điểm cần đồng bộ; đóng đúng |
| Đọc `readLine()` và ghi lại mà đòi giữ nguyên byte | Mất thông tin CR/LF/CRLF nguyên bản | Đọc/ghi bảo toàn chính xác ký tự hoặc byte |
| Coi UTF-8 quyết định LF/CRLF | Nhầm charset với line ending | Chọn charset và separator độc lập |
| Ghi `newLine()` sau mọi dòng mà không kiểm tra chuẩn | Có thể thêm newline cuối không mong muốn | Xác định chính sách dấu kết thúc dòng cuối |
| Dùng `"\n"` rồi khẳng định file luôn hiển thị đúng mọi ứng dụng | Một số hệ thống cũ/tool đặc thù kỳ vọng quy ước khác | Tuân thủ định dạng hoặc nhu cầu ứng dụng nhận |
| Thêm `flush()` sau từng lệnh không cần thiết | Giảm hiệu quả đệm và tăng I/O | Flush theo điểm đồng bộ có chủ đích |

## 12. Bài tập tự kiểm tra

1. **Trên Windows thông thường**, sau `writer.write("A"); writer.newLine(); writer.write("B");` thì chuỗi ký tự sẽ tương đương dạng nào? **`"A\r\nB"`**, nếu môi trường dùng CRLF.
2. **Trên Linux thông thường**, chuỗi tương đương là gì? **`"A\nB"`**, nếu môi trường dùng LF.
3. **Chỉ gọi `System.lineSeparator()` có ghi ra file không?** **Không**; phương thức trả về `String`.
4. **`newLine()` có tự gọi `flush()` không?** **Không**; gọi `flush()` tại thời điểm cần đẩy dữ liệu đệm, hoặc đóng writer đúng cách.
5. **Một chuẩn yêu cầu LF cố định trên mọi OS: dùng gì?** **Ghi `"\n"` rõ ràng** hoặc API xuất theo đúng chuẩn.
6. **Đọc file có CRLF bằng `readLine()` rồi ghi lại bằng `newLine()` trên Linux có giữ nguyên byte không?** **Không bảo đảm**; các ký tự kết thúc dòng có thể chuyển thành LF.
7. **UTF-8 có làm cho `newLine()` luôn dùng LF không?** **Không**; encoding byte và line ending là hai quyết định riêng.
8. **Muốn file text luôn có newline cuối cùng, đặt `newLine()` ở đâu?** **Sau cả dòng cuối**, theo quy định định dạng của file.

**Quy tắc thực hành:** dùng `BufferedWriter.newLine()` để **ghi xuống dòng theo nền tảng**, dùng `System.lineSeparator()` để **lấy chuỗi xuống dòng theo nền tảng**, và dùng `"\n"` hoặc `"\r\n"` **tường minh** khi đặc tả đầu ra yêu cầu chính xác.