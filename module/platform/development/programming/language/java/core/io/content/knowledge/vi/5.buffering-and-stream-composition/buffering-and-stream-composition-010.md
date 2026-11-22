# Tránh trộn nhiều lớp đọc có bộ đệm trên cùng một nguồn trong Java I/O

## Mục tiêu bài học

Trong Java, `BufferedInputStream`, `BufferedReader`, `Scanner` và các bộ chuyển đổi như `InputStreamReader` giúp đọc dữ liệu thuận tiện, hiệu quả hơn. Nhưng nếu tạo **nhiều đối tượng đọc độc lập trên cùng một nguồn** rồi thay phiên đọc, chương trình có thể mất byte, bỏ qua dòng hoặc thấy EOF sớm dù dữ liệu vẫn đang nằm trong bộ đệm của đối tượng khác.

Sau bài học, bạn có thể:

- Giải thích **read-ahead (đọc trước)** và vị trí dữ liệu được giữ trong bộ đệm.
- Phân biệt **ghép nhiều lớp theo một chuỗi duy nhất** (an toàn) với **nhiều đầu đọc cạnh tranh trên cùng nguồn** (dễ sai).
- Quan sát lỗi bằng một chương trình Java 17+ có đầu ra xác định, rồi sửa bằng một điểm đọc duy nhất.
- Tổ chức luồng byte, luồng ký tự, parser nhị phân và tài nguyên `System.in` với quyền sở hữu rõ ràng.

## 1. Vì sao bộ đệm đọc trước nhiều hơn một lời gọi `read()`?

Xét dữ liệu byte trong nguồn:

```text
Nguồn gốc: A B C D E F G H I J K
```

Khi bạn gọi `buffered.read()` chỉ để nhận **một byte**, `BufferedInputStream` có thể đọc trước **một khối** từ nguồn và giữ phần còn lại trong bộ đệm riêng:

```text
                 +------------------------------------+
raw InputStream  | A B C D E F G H | I J K           |
                 +------------------------------------+
                         | đọc trước 8 byte
                         v
buffered buffer  [ A B C D E F G H ]
                     ^
           buffered.read() trả A

raw đang ở vị trí trước I.
B C D E F G H vẫn còn trong bộ đệm của buffered.
```

Sau khi gọi `buffered.read()`, vị trí đọc của nguồn gốc có thể đã tiến đến `I`, **không phải `B`**. Những byte `B..H` không mất: chúng vẫn ở trong `buffered`, và phải được lấy qua **chính đối tượng đó**.

Mức đọc trước thực tế phụ thuộc lớp và cách triển khai; kích thước bộ đệm không bảo đảm rằng mỗi lần đọc luôn lấy đúng bấy nhiêu byte trên mọi nguồn. Điều quan trọng là **một đối tượng có thể đã lấy từ nguồn nhiều hơn lượng dữ liệu nó vừa trả về cho người gọi**.

Bộ đệm của `BufferedReader` hoạt động tương tự ở mức **ký tự**; `InputStreamReader` còn có thể lấy trước nhiều byte để giải mã ký tự từ `InputStream`. `Scanner` cũng có cơ chế đệm/phân tích token riêng.

## 2. Phân biệt hai cách tổ chức rất dễ nhầm

**Đúng: các lớp nằm nối tiếp trong *một pipeline*, chỉ có một đầu đọc ứng dụng.**

```text
InputStream gốc
      |
      v
BufferedInputStream
      |
      v
InputStreamReader (UTF-8)
      |
      v
BufferedReader
      |
      v
Ứng dụng chỉ gọi readLine() trên BufferedReader
```

Mỗi lớp phía ngoài lấy dữ liệu từ lớp ngay dưới nó. Phần đọc trước vẫn đi qua **một đường tiêu thụ duy nhất**. Đây là cách **ghép luồng** hợp lệ, dù có thể không cần thêm mọi tầng đệm trong mọi chương trình.

**Sai: tạo hai đầu đọc cạnh tranh hoặc đọc xen kẽ qua lớp bọc và nguồn gốc.**

```text
                     +--> BufferedInputStream A --> logic 1
InputStream gốc -----+
                     +--> BufferedInputStream B --> logic 2

hoặc

InputStream gốc -----+--> BufferedInputStream --> logic 1
                     +--> đọc trực tiếp raw   --> logic 2
```

Khi A lấy trước byte vào buffer, B không biết byte nào đã nằm trong buffer của A. Cả hai cùng làm thay đổi vị trí đọc chung ở nguồn gốc. Vì vậy, kết quả tùy theo **thứ tự và mức đọc trước của từng bên**; dữ liệu mà ứng dụng mong chờ có thể nằm ở một đối tượng khác.

**Quy tắc cốt lõi:** Có thể bọc **nhiều tầng trên cùng một chuỗi**, nhưng không nên dùng **nhiều đầu đọc độc lập để cạnh tranh trên cùng nguồn** nếu không có cơ chế phân phối dữ liệu được thiết kế riêng.

## 3. Ví dụ Java 17+: đọc xen kẽ làm đổi thứ tự dữ liệu

Ví dụ cố tình tạo một trường hợp đủ nhỏ để nhìn thấy read-ahead. `ByteArrayInputStream` giữ sẵn dãy `ABCDEFGHIJK`; `BufferedInputStream` được tạo với bộ đệm 8 byte. Lưu thành **`MixedBufferedReadDemo.java`**:

```java
import java.io.BufferedInputStream;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class MixedBufferedReadDemo {
    public static void main(String[] args) throws IOException {
        byte[] data = "ABCDEFGHIJK".getBytes(StandardCharsets.US_ASCII);
        ByteArrayInputStream raw = new ByteArrayInputStream(data);

        try (BufferedInputStream buffered = new BufferedInputStream(raw, 8)) {
            System.out.println("buffered first = " + (char) buffered.read());
            System.out.println("raw available = " + raw.available());
            System.out.println("raw next = " + (char) raw.read());
            System.out.println("buffered rest = "
                    + new String(buffered.readAllBytes(),
                                 StandardCharsets.US_ASCII));
        }
    }
}
```

Biên dịch, chạy trên JDK 17+:

```bash
javac MixedBufferedReadDemo.java
java MixedBufferedReadDemo
```

Đầu ra của ví dụ với `ByteArrayInputStream` và bộ đệm 8 byte trên JDK 17:

```text
buffered first = A
raw available = 3
raw next = I
buffered rest = BCDEFGHJK
```

Diễn giải theo từng bước:

1. `buffered.read()` trả `A` nhưng lấy trước tám byte `A..H` vào bộ đệm. Nguồn `raw` chỉ còn `IJK` nên `raw.available()` là `3`.
2. `raw.read()` **bỏ qua góc nhìn của `buffered`** và nhận `I` trực tiếp. Đây là chỗ chương trình vô tình đổi thứ tự xử lý.
3. Khi tiếp tục đọc từ `buffered`, chương trình nhận `B..H` trong bộ đệm, sau đó nhận `JK` còn ở nguồn. Kết quả ghép lại thành `A` + `I` + `BCDEFGHJK`, không còn theo thứ tự `ABCDEFGHIJK` ban đầu.

Các byte không tự biến mất khỏi chương trình demo; chúng bị **phân phối sai thứ tự giữa hai đường đọc**. Trong parser thực tế, việc đọc nhầm vị trí như vậy có thể gây lỗi tiêu đề, thiếu payload hoặc giải mã sai dữ liệu.

Đừng phụ thuộc vào chính xác giá trị `raw.available() == 3` với nguồn khác. Con số này minh họa một trường hợp cụ thể; `available()` không phải tổng độ dài dữ liệu, càng không biết hết byte đang nằm trong buffer của wrapper.

## 4. Cách sửa: mọi thao tác đọc dùng cùng một đối tượng có bộ đệm

Lưu thành **`SingleBufferedReadDemo.java`**:

```java
import java.io.BufferedInputStream;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class SingleBufferedReadDemo {
    public static void main(String[] args) throws IOException {
        byte[] data = "ABCDEFGHIJK".getBytes(StandardCharsets.US_ASCII);

        try (BufferedInputStream in =
                     new BufferedInputStream(new ByteArrayInputStream(data), 8)) {
            System.out.println("first = " + (char) in.read());
            System.out.println("rest = "
                    + new String(in.readAllBytes(), StandardCharsets.US_ASCII));
        }
    }
}
```

Chạy:

```bash
javac SingleBufferedReadDemo.java
java SingleBufferedReadDemo
```

Kết quả:

```text
first = A
rest = BCDEFGHIJK
```

Lúc này, lần đọc đầu tiên có thể vẫn đọc trước `A..H`, nhưng phần còn lại được trả lại **đúng thứ tự** bởi cùng `in`. Bước sửa không đòi hỏi tắt buffering: chỉ cần không chuyển sang đọc trực tiếp nguồn `raw` giữa chừng.

Nếu nhiều phương thức cần cùng nguồn, hãy **truyền cùng đối tượng `BufferedInputStream`** xuống các phương thức đó, hoặc đặt quyền đọc ở một lớp parser rồi cho các thành phần khác tiêu thụ **kết quả đã phân tích**. Tránh mỗi phương thức tự tạo một wrapper mới từ nguồn gốc.

## 5. Trộn byte và ký tự còn nguy hiểm hơn

Ví dụ thiết kế dễ gặp lỗi:

```java
// MINH HỌA SAI: hai lối đọc trên cùng socketInput.
InputStreamReader characters =
        new InputStreamReader(socketInput, java.nio.charset.StandardCharsets.UTF_8);
int firstCharacter = characters.read();
int nextRawByte = socketInput.read();
```

Đây là **đoạn minh họa**, không phải chương trình độc lập; biến `socketInput` đại diện một `InputStream` do chương trình khác cấp.

`InputStreamReader` có thể đọc trước nhiều byte để giải mã UTF-8. Vì vậy, `nextRawByte` không nhất thiết là byte ngay sau ký tự vừa được trả về. Nếu byte đó thuộc ký tự UTF-8 nhiều byte, parser còn có thể tách giữa các byte của cùng một ký tự và gây lỗi.

Tương tự, tạo cả:

```java
BufferedReader lines =
        new BufferedReader(new InputStreamReader(raw, java.nio.charset.StandardCharsets.UTF_8));
Scanner tokens = new Scanner(raw, java.nio.charset.StandardCharsets.UTF_8);
```

là hai bộ đọc độc lập trên cùng `raw` nếu chương trình dùng chúng xen kẽ. Mỗi bên có thể đọc trước hoặc giữ trạng thái phân tích riêng. Lưu ý đoạn này giả định đã có biến `raw` kiểu `InputStream` và các import phù hợp; nó chỉ minh họa lỗi thiết kế.

Các tổ hợp nên tránh khi cùng tranh một nguồn:

- `BufferedReader` và `Scanner` cùng đọc `System.in`.
- `BufferedReader` đọc dòng, rồi đọc tiếp byte trực tiếp từ `InputStream` bên dưới.
- Hai `BufferedReader` khác nhau cùng bọc một `Reader` hoặc cùng bọc một đầu vào thô.
- Một `BufferedInputStream` đọc header nhưng phần body lại dùng `rawInputStream.read()`.
- Đọc một ít dữ liệu bằng wrapper A, sau đó bỏ A và dựng wrapper B trên nguồn gốc nhưng không xử lý byte A đã đọc trước.

Đừng nhầm lỗi này với **khác biệt token/dòng của `Scanner`**: `nextInt()` thường để lại dấu xuống dòng để `nextLine()` đọc; đó là quy tắc phân tách đầu vào **ngay trong một Scanner**, và có cách xử lý riêng. Trộn hai scanner/reader trên cùng nguồn tạo thêm lỗi đọc trước, khó đoán hơn.

## 6. Pipeline ký tự đúng: một `BufferedReader` đọc toàn bộ dòng

Lưu tệp **`SingleTextReaderDemo.java`**:

```java
import java.io.BufferedInputStream;
import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class SingleTextReaderDemo {
    public static void main(String[] args) throws IOException {
        byte[] bytes = "alpha\nbeta\n".getBytes(StandardCharsets.UTF_8);

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                        new BufferedInputStream(
                                new ByteArrayInputStream(bytes)),
                        StandardCharsets.UTF_8))) {
            String line;
            int index = 0;

            while ((line = reader.readLine()) != null) {
                System.out.println("line " + (++index) + ": " + line);
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac SingleTextReaderDemo.java
java SingleTextReaderDemo
```

Đầu ra:

```text
line 1: alpha
line 2: beta
```

Đây là chuỗi **`ByteArrayInputStream → BufferedInputStream → InputStreamReader(UTF-8) → BufferedReader`**. Có nhiều lớp, thậm chí hai tầng hỗ trợ buffering, nhưng chỉ có **một đường đọc** và ứng dụng chỉ sử dụng `reader.readLine()`. Do đó dữ liệu được giải mã và chia dòng nhất quán.

Trong thực tế, `BufferedReader(new InputStreamReader(raw, UTF_8))` thường đã đủ cho việc đọc theo dòng. Chỉ thêm `BufferedInputStream` khi có lý do phù hợp với kiến trúc hoặc hiệu năng. Nếu bọc thêm, hãy tiếp tục dùng **đầu ngoài cùng**.

### `readLine()` tiêu thụ những gì?

`BufferedReader.readLine()` trả dòng **không kèm** ký tự kết thúc dòng (`\n`, `\r` hoặc `\r\n`). Nếu định dạng đòi hỏi giữ nguyên byte ban đầu, đừng vừa đọc bằng `readLine()` vừa cố “lấy lại” dấu xuống dòng bằng một đầu đọc byte độc lập. Thay vào đó, chọn API xử lý byte hoặc parser có khả năng bảo toàn separator ngay từ đầu.

## 7. Parser nhị phân: đọc header và body qua *cùng một luồng*

Một lỗi thường gặp ở giao thức nhị phân là đọc header qua wrapper, sau đó đọc body trên đối tượng thô. Hãy giữ cả hai bước trên một đường đọc. `DataInputStream` cung cấp `readUnsignedShort()`, `readFully(byte[])` và các phương thức cho dữ liệu nhị phân; có thể đặt nó **bên ngoài** `BufferedInputStream`.

Ví dụ packet có hai byte độ dài (big-endian), ba byte chữ `cat`, rồi một byte đánh dấu `X`. Lưu thành **`FramedPacketDemo.java`**:

```java
import java.io.BufferedInputStream;
import java.io.ByteArrayInputStream;
import java.io.DataInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class FramedPacketDemo {
    public static void main(String[] args) throws IOException {
        byte[] packet = {0, 3, 99, 97, 116, 88};

        try (DataInputStream in = new DataInputStream(
                new BufferedInputStream(
                        new ByteArrayInputStream(packet), 4))) {
            int length = in.readUnsignedShort();
            byte[] body = new byte[length];
            in.readFully(body);

            System.out.println("length = " + length);
            System.out.println("body = "
                    + new String(body, StandardCharsets.US_ASCII));
            System.out.println("trailer = " + (char) in.readUnsignedByte());
            System.out.println("eof = " + in.read());
        }
    }
}
```

Chạy:

```bash
javac FramedPacketDemo.java
java FramedPacketDemo
```

Đầu ra:

```text
length = 3
body = cat
trailer = X
eof = -1
```

`DataInputStream` đọc **cả header, body lẫn trailer** từ cùng `in`; việc `BufferedInputStream` lấy trước các byte không gây vấn đề. `readFully` sẽ đọc cho đủ số byte yêu cầu hoặc ném `EOFException` nếu EOF đến sớm, khác với một lần `read(byte[])` vốn có thể trả ít hơn số byte mong muốn.

Khi xử lý dữ liệu bên ngoài không đáng tin cậy, phải **kiểm tra giới hạn của `length` trước khi cấp phát `new byte[length]`**. Trong chương trình này, packet cố định và đủ nhỏ để tập trung vào nguyên tắc dùng chung một đầu đọc.

## 8. Đóng luồng và chuyển quyền sở hữu cũng có thể phá pipeline

Nhiều wrapper I/O trong Java **đóng luôn luồng bên dưới** khi `close()`. Nếu hai thành phần cùng tạo wrapper từ một đối tượng gốc, việc một wrapper đóng có thể khiến thành phần kia không đọc tiếp được.

Ví dụ các thao tác này dễ gây vấn đề:

```java
// MINH HỌA SAI khi raw còn được nơi khác sử dụng:
BufferedReader first = new BufferedReader(
        new InputStreamReader(raw, java.nio.charset.StandardCharsets.UTF_8));
first.close(); // Thường đóng cả InputStreamReader và raw bên dưới.
int next = raw.read(); // Có thể ném IOException nếu raw đã đóng.
```

Đây là đoạn mô tả rủi ro, không phải mã chạy độc lập và không phải mọi `InputStream` đều phản ứng giống nhau sau `close()`. Chẳng hạn `ByteArrayInputStream.close()` không có tác dụng, trong khi nhiều nguồn tệp và socket không thể đọc sau khi đóng. Không dựa vào ngoại lệ của luồng trong bộ nhớ để suy ra hành vi của nguồn thật.

Quy ước thực tế:

1. Một lớp hoặc thành phần **sở hữu** nguồn và quyết định thời điểm đóng.
2. Bọc nguồn **một lần thành chuỗi chính**, truyền lớp ngoài cùng cho code đọc.
3. Nếu phương thức chỉ mượn stream, ghi rõ hợp đồng nó **không tự đóng**; thành phần sở hữu sẽ đóng khi toàn bộ quá trình hoàn tất.
4. Với `System.in` dùng chung trong ứng dụng tương tác, đừng vô tình đóng nó trong một helper hoặc `try-with-resources` của reader tạm thời, khiến những phần sau không nhận được input.

**Ngoại lệ:** Nếu cố ý tạo stream con độc lập hoặc API cấp lại một nguồn mới, mỗi stream có thể có vòng đời riêng. Nguyên tắc ở bài này áp dụng khi **thực sự dùng chung một nguồn dữ liệu có trạng thái đọc**.

## 9. Nếu thật sự cần hai bộ xử lý, phân phối dữ liệu như thế nào?

Đôi khi ứng dụng cần vừa parse vừa log, vừa tính checksum hoặc cho nhiều component quan sát cùng dữ liệu. Cách giải không phải cho các bên tự đua đọc trên một `InputStream`:

- **Một reader, nhiều consumer:** chỉ một thành phần đọc từng khối byte, sau đó chuyển **bản sao hoặc dữ liệu đã phân tích** cho các thành phần khác. Mỗi consumer không động chạm tới vị trí của nguồn.
- **Ghi đồng thời trong pipeline có kiểm soát:** một lớp trung gian có thể chuyển byte qua nhiều đích (ví dụ log và parser), nhưng vẫn giữ **một đường đọc từ nguồn**. Cần xác định cách xử lý lỗi và thứ tự.
- **Nguồn dữ liệu tái mở được:** nếu cần hai lượt đọc hoàn toàn độc lập và nguồn hỗ trợ, mở **hai stream khác nhau từ đầu** (chẳng hạn hai lần gọi `Files.newInputStream(path)`); lúc đó mỗi stream có vị trí riêng. Không áp dụng cách này cho socket/pipe tiêu thụ một lần.
- **Dữ liệu nhỏ lưu trong RAM:** đọc toàn bộ nguồn **một lần** rồi cấp các `ByteArrayInputStream` riêng trên mảng đã lưu. Với nguồn lớn, không dùng giải pháp này vô điều kiện vì tốn bộ nhớ.
- **Dữ liệu dùng chung nhiều thread:** tập trung quyền đọc tại một thành phần rồi phân phối qua queue hoặc cơ chế message. Việc nhiều thread thay nhau gọi `read()` lên các wrapper khác nhau cũng không giải quyết được đọc trước và có thể tạo thêm lỗi đồng bộ.

Nếu một phương thức cần đọc một phần dữ liệu rồi để phương thức tiếp theo đọc tiếp, hãy chuyển **chính wrapper hiện tại** giữa các phương thức, không chỉ chuyển `raw` ban đầu.

## 10. Dấu hiệu nhận biết và cách chẩn đoán lỗi

| Triệu chứng | Câu hỏi cần kiểm tra | Cách sửa |
| --- | --- | --- |
| Đọc trực tiếp nguồn gốc bị nhảy qua vài byte | Có wrapper nào vừa đọc trước trên nguồn đó không? | Đọc phần tiếp theo qua chính wrapper. |
| Một parser thấy EOF bất ngờ | Dữ liệu có nằm trong buffer của parser khác không? | Dùng một parser/reader có quyền sở hữu nguồn. |
| `BufferedReader` bỏ qua dòng “khó hiểu” khi ghép `Scanner` | Có hai đối tượng cùng lấy trước từ `System.in`/socket không? | Chọn một API đầu vào và thống nhất quy tắc parse. |
| Byte đọc được nhưng ký tự UTF-8 bị lỗi | Có đang chuyển qua lại giữa đọc byte và đọc ký tự không? | Đọc và giải mã tập trung bằng một `Reader`/decoder. |
| `raw.available()` rất nhỏ dù còn dữ liệu | Byte đã nằm trong một buffer phía ngoài chưa? | Không dùng `available()` để tính dữ liệu còn lại hoặc EOF. |
| Đọc tiếp thất bại sau khi helper kết thúc | Helper có đóng wrapper, kéo theo đóng nguồn chung không? | Quy định quyền sở hữu và thời điểm `close()`. |

### `mark()` / `reset()` có giải quyết được không?

`BufferedInputStream` có thể hỗ trợ `mark/reset` trong một phạm vi đọc được giữ trong buffer. Tuy nhiên, `reset()` chỉ điều chỉnh **trạng thái của wrapper đó** theo hợp đồng của nó; không đồng bộ vị trí và bộ đệm của các wrapper cạnh tranh khác. Đừng coi `mark/reset` là cách “điều chỉnh” hai bộ đọc độc lập trên cùng một nguồn.

### Có thể chỉ dùng `InputStreamReader` mà không có `BufferedReader` không?

Có. `InputStreamReader` chuyển byte sang ký tự; `BufferedReader` bổ sung bộ đệm ký tự và các thao tác như `readLine()`. Mối nguy không nằm ở việc có bao nhiêu lớp nối tiếp, mà ở việc có **bao nhiêu lối đọc riêng cùng tranh dữ liệu nguồn**. Một `InputStreamReader` cũng có thể đọc trước byte khi giải mã.

## 11. Tự kiểm tra

**Câu 1.** `BufferedInputStream` trả về `A`; có được gọi `raw.read()` để lấy `B` không?

**Trả lời:** Không bảo đảm. Wrapper có thể đã lấy `B` cùng nhiều byte khác vào buffer. Hãy dùng `buffered.read()` để lấy byte kế tiếp theo đúng thứ tự.

**Câu 2.** `InputStream → BufferedInputStream → InputStreamReader → BufferedReader` có bị xem là trộn nhiều đầu đọc không?

**Trả lời:** Không, nếu ứng dụng chỉ đọc ở `BufferedReader` ngoài cùng và các lớp nối tiếp nhau. Đây là **một pipeline**; những đầu đọc *song song* trên cùng nguồn mới là rủi ro.

**Câu 3.** Tại sao hai `Scanner` cùng đọc `System.in` dễ sai?

**Trả lời:** Mỗi scanner có buffer và trạng thái token riêng. Một scanner có thể lấy trước dữ liệu mà scanner kia cần. Hãy dùng một scanner hoặc một reader/parser duy nhất.

**Câu 4.** Parser đọc hai byte độ dài và payload. Header đọc qua `DataInputStream(BufferedInputStream(raw))`, body đọc từ `raw`: có an toàn không?

**Trả lời:** Không. Dữ liệu body có thể nằm sẵn trong buffer của `DataInputStream`/`BufferedInputStream`. Đọc cả header và body qua cùng đối tượng `DataInputStream`.

**Câu 5.** Muốn hai thuật toán phân tích độc lập cùng một file, có thể mở hai `InputStream` từ cùng đường dẫn tệp không?

**Trả lời:** Có, nếu file ổn định và mỗi lời gọi mở tạo một stream riêng, quản lý vòng đời riêng. Đây là **hai nguồn đọc độc lập**, khác với hai wrapper dùng chung **một đối tượng stream**. Nếu file bị thay đổi đồng thời, phải có cách xử lý nhất quán dữ liệu.

## Ghi nhớ

**Một nguồn có trạng thái đọc → một pipeline chính → một đầu đọc ngoài cùng.** Có thể ghép nhiều tầng đệm và giải mã **nối tiếp** theo nhu cầu, nhưng khi đã đọc qua wrapper có bộ đệm thì đừng chuyển sang đọc trên raw stream hoặc wrapper thứ hai cùng bọc raw. Muốn nhiều consumer, hãy phân phối dữ liệu sau một điểm đọc chung hoặc mở các nguồn độc lập khi nguồn hỗ trợ.
