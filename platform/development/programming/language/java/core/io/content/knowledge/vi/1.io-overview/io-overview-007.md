# Kiến thức tiên quyết và trình tự học Java I/O

> Phạm vi: Java Core I/O. Bài này xác định những kiến thức cần có, lý do chúng quan trọng và lộ trình học từ thao tác tệp đơn giản đến thiết kế luồng dữ liệu an toàn. Đây là bản đồ học tập; các API nâng cao được giới thiệu đúng vị trí, không cần thành thạo trước khi bắt đầu.

## 1. Đích đến của việc học I/O

**Input/Output (I/O)** là việc chương trình nhận dữ liệu từ hoặc gửi dữ liệu đến một nguồn/đích bên ngoài bộ nhớ đang xử lý: bàn phím, tệp, bộ đệm, kết nối mạng hoặc một luồng khác. Trong Java, cần phân biệt dữ liệu **byte** với **ký tự**, thao tác **đọc/ghi** với vòng đời **tài nguyên**, và cách xử lý dữ liệu nhỏ với dữ liệu lớn.

Sau lộ trình này, người học cần có khả năng:

- Chọn đúng API để đọc/ghi tệp văn bản UTF-8 và dữ liệu nhị phân.
- Giải thích được sự khác nhau giữa `InputStream`/`OutputStream`, `Reader`/`Writer`, `Path`/`Files`, và `Channel`/`Buffer`.
- Sử dụng `try-with-resources` để đóng tài nguyên; xử lý `IOException` có chủ đích.
- Xử lý tệp lớn theo từng phần thay vì mặc định tải toàn bộ vào RAM.
- Nhận biết rủi ro về đường dẫn, mã hóa, dữ liệu không đáng tin, ghi dở và việc nhiều luồng cùng truy cập.
- Tự xác minh kết quả đọc/ghi bằng ví dụ chạy được và bài kiểm tra cho trường hợp lỗi.

## 2. Kiến thức tiên quyết: cần biết gì trước?

| Nền tảng | Mức cần nắm | Liên hệ trực tiếp với I/O |
| --- | --- | --- |
| Cú pháp Java cơ bản | Khai báo biến, toán tử, `if`, `for`, `while`, gọi phương thức | Đọc lặp từng dòng/từng khối byte, dừng khi hết dữ liệu |
| Kiểu dữ liệu và mảng | `byte`, `char`, `int`, `String`, `byte[]`, chỉ số mảng | Bộ đệm byte; phân biệt ký tự Unicode với byte mã hóa |
| Lớp và đối tượng | `new`, constructor, interface, kế thừa, gọi phương thức | Các trừu tượng luồng, reader, writer và lớp bọc như `BufferedReader` |
| Ngoại lệ | `try`, `catch`, `finally`, `throws`, checked exception | Đọc/ghi có thể thất bại do tệp không tồn tại, mất quyền, thiết bị hoặc đường truyền |
| Tài nguyên và phạm vi biến | `AutoCloseable` ở mức sử dụng, `try-with-resources` | Đóng file handle/stream kể cả khi có lỗi |
| Collections ở mức căn bản | `List`, duyệt phần tử; biết giới hạn bộ nhớ | Lưu các dòng nhỏ khi cần, cân nhắc xử lý tuần tự cho dữ liệu lớn |
| Công cụ JDK | Chạy `java -version`, `javac`, `java`, xem đường dẫn làm việc | Biên dịch, chạy và quan sát tệp thật trên hệ điều hành |

**Nên củng cố trước nếu chưa nắm:** vòng lặp `while` với điều kiện trả về `null` hoặc `-1`; ý nghĩa của `throws IOException`; cách đối chiếu tên tệp nguồn với `public class`; và phân biệt `String` bất biến với mảng byte có thể thay đổi.

**Chưa bắt buộc ở điểm xuất phát:** lập trình đa luồng, socket, serialization, selector, memory-mapped file, hay framework web. Chúng trở nên hữu ích ở các chặng sau khi đã đọc/ghi cơ bản chắc chắn.

## 3. Những khái niệm gốc cần hiểu ngay

### 3.1 Byte, ký tự và charset

- **Byte** là đơn vị dữ liệu nhị phân (8 bit); ảnh, tệp nén và dữ liệu giao thức phải được xem là byte, không tự giải mã thành `String`.
- **Ký tự** là dữ liệu văn bản đã được giải mã. `String` chứa chuỗi ký tự Java (UTF-16 code units); một ký tự Unicode ngoài BMP có thể chiếm hai `char`.
- **Charset** quyết định cách biến văn bản thành byte và ngược lại. Nên chọn rõ `StandardCharsets.UTF_8` khi định dạng tệp hoặc giao thức yêu cầu UTF-8; không giả định máy nào cũng có cùng charset mặc định.
- Các ký tự xuống dòng có thể dùng `\n`, `\r\n` hoặc `\r`. `BufferedReader.readLine()` bỏ ký tự kết thúc dòng; nếu phải giữ nguyên byte hoặc line ending, không dùng cách đọc đó để tái tạo nguyên trạng.

Ví dụ tư duy: văn bản `"é"` và `"😀"` có độ dài `String.length()` lần lượt là 1 và 2 UTF-16 code units, nhưng khi mã hóa UTF-8 có lần lượt 2 và 4 byte. Vì vậy **số ký tự, số `char` và số byte không tương đương**.

### 3.2 Nguồn/đích dữ liệu và lớp API

| Cần giải quyết | Nhóm API nên nhận diện |
| --- | --- |
| Đọc/ghi byte | `InputStream`, `OutputStream` (`java.io`) |
| Đọc/ghi ký tự | `Reader`, `Writer`; `BufferedReader`, `BufferedWriter` |
| Thao tác tệp, thư mục, đường dẫn | `Path`, `Files` (`java.nio.file`) |
| I/O với bộ đệm, vị trí và kênh | `ByteBuffer`, `FileChannel` (`java.nio`) |
| Socket và multiplexing ở tầng nâng cao | `SocketChannel`, `Selector` khi yêu cầu bài toán phù hợp |

`java.io.InputStream` là luồng byte; **không phải** `java.util.stream.Stream<T>` dùng cho thao tác dữ liệu theo phong cách functional. `Path` mô tả đường dẫn; `Files` cung cấp thao tác lên hệ thống tệp. Một `Path` tự nó không mở hay đóng tệp.

### 3.3 Vòng đời tài nguyên và lỗi

Đường đọc thường có ba bước: **mở nguồn → đọc và xử lý → đóng tài nguyên**. Dùng `try-with-resources` cho đối tượng triển khai `AutoCloseable`: Java gọi `close()` khi ra khỏi khối, kể cả khi đọc ném ngoại lệ. Đóng thành công vẫn không đảm bảo mọi lỗi nghiệp vụ đã được xử lý; ví dụ, ghi một tệp đích quan trọng cần thêm chiến lược ghi tạm rồi thay thế theo yêu cầu hệ thống tệp.

`IOException` là checked exception phổ biến; gọi API cần bắt hoặc khai báo `throws`. Phải phân biệt lỗi đọc thất bại với tín hiệu **hết dữ liệu**: `InputStream.read()` trả `-1` khi EOF, còn `BufferedReader.readLine()` trả `null` khi EOF. Không dùng `available()` làm điều kiện đọc hết một stream.

## 4. Trình tự học đề xuất

Đi theo thứ tự dưới đây; mỗi chặng có một năng lực cần đạt trước khi chuyển sang chặng tiếp theo. Không cần học mọi lớp cùng lúc.

### Chặng 0 — Chuẩn bị môi trường và Java nền tảng

**Học:** kiểm tra JDK 17+, biên dịch/chạy một file `.java`, hiểu working directory, đường dẫn tương đối và tuyệt đối; ôn ngoại lệ, vòng lặp, `String`, `byte[]` và `try-with-resources`.

**Thực hành:** một chương trình nhận chuỗi, in ra console; cố tình truyền tên tệp không tồn tại ở bài thử kế tiếp và quan sát thông tin `IOException`.

**Đạt khi:** giải thích được vì sao đường dẫn tương đối phụ thuộc thư mục làm việc và vì sao `try-with-resources` khác việc chỉ gọi `close()` cuối luồng chạy bình thường.

### Chặng 1 — File và Path trước khi học nhiều loại stream

**Học:** `Path.of(...)`, `resolve(...)`, `normalize()`, `Files.exists(...)`, `Files.isRegularFile(...)`, `Files.createDirectories(...)`, `Files.readString(...)`, `Files.writeString(...)`, `Files.copy(...)`, `Files.move(...)`, `Files.deleteIfExists(...)`.

**Thực hành:** tạo thư mục riêng cho bài tập, ghi một tệp UTF-8, đọc lại và so sánh nội dung, sao chép sang tên khác rồi dọn tệp. Dùng `resolve` để nối đường dẫn thay cho tự chèn dấu `/` hoặc `\`.

**Đạt khi:** chọn được API đọc/ghi văn bản **nhỏ** và biết một lần kiểm tra `Files.exists` trước đó không bảo đảm thao tác kế tiếp sẽ thành công: tệp có thể đổi giữa hai thao tác.

### Chặng 2 — Byte streams và character streams

**Học:** `InputStream`/`OutputStream`, `Reader`/`Writer`, `InputStreamReader`/`OutputStreamWriter`, `BufferedInputStream`/`BufferedOutputStream`, `BufferedReader`/`BufferedWriter`.

**Thực hành:** sao chép ảnh theo từng khối byte bằng `InputStream.transferTo(OutputStream)` hoặc vòng lặp `read(byte[])`/`write(...)`; đọc văn bản từng dòng bằng `BufferedReader`; so sánh với đọc toàn bộ chuỗi qua `Files.readString`.

**Đạt khi:** biết chọn byte cho dữ liệu nhị phân, character cho văn bản, nêu rõ charset tại ranh giới chuyển byte ↔ text, và hiểu buffering giảm số lần gọi I/O trong nhiều tình huống.

### Chặng 3 — Quản lý bộ nhớ, lỗi và độ tin cậy

**Học:** xử lý dữ liệu lớn theo luồng; `try-with-resources`; flush và close; ngoại lệ khi mở/đọc/ghi; tệp không tồn tại, quyền truy cập, đường dẫn sai, dữ liệu chưa hoàn chỉnh.

**Thực hành:** xử lý tệp log lớn theo từng dòng mà không gọi `Files.readAllLines` hoặc `Files.readAllBytes`; giả lập lỗi bằng cách trỏ tới tệp không tồn tại; kiểm tra tài nguyên được đóng.

**Đạt khi:** giải thích được `flush()` đẩy dữ liệu từ lớp đệm xuống tầng dưới nhưng không tự đảm bảo dữ liệu đã được lưu bền vững trên thiết bị; `close()` giải phóng tài nguyên và có thể phát sinh lỗi.

### Chặng 4 — File tree và metadata

**Học:** `Files.list(...)`, `Files.walk(...)`, `Files.walkFileTree(...)`, `BasicFileAttributes`, symbolic link; phân biệt lọc tên tệp với đọc nội dung tệp.

**Thực hành:** liệt kê tệp theo hậu tố và tính tổng kích thước trong một thư mục bài tập; dùng `try-with-resources` với stream trả về bởi `Files.list`/`Files.walk`.

**Đạt khi:** biết giới hạn phạm vi quét, xử lý lỗi quyền truy cập và tránh vô tình đi theo symlink ngoài thư mục dự kiến.

### Chặng 5 — NIO buffers và channels

**Học:** `ByteBuffer` với `position`, `limit`, `capacity`, `flip()`, `clear()`; `FileChannel` để đọc/ghi theo vị trí; phân biệt blocking I/O thường gặp với non-blocking I/O trong các trường hợp kênh hỗ trợ.

**Thực hành:** đọc tệp nhị phân bằng `FileChannel` và `ByteBuffer`; ghi hoặc đọc một vùng xác định của tệp; so sánh với stream ở chặng 2.

**Đạt khi:** giải thích được vì sao phải `flip()` trước khi đọc dữ liệu vừa ghi vào buffer, và không mặc định mọi `Channel` đều non-blocking.

### Chặng 6 — Áp dụng theo loại dữ liệu và độ phức tạp

**Học theo nhu cầu:** `DataInputStream`/`DataOutputStream` cho primitive theo định dạng xác định; `ObjectInputStream`/`ObjectOutputStream` ở mức nhận biết rủi ro, không coi Java serialization là định dạng trao đổi mặc định; socket I/O, selector và asynchronous channel chỉ khi bài toán cần.

**Thực hành:** viết một định dạng bản ghi nhị phân nhỏ có mô tả thứ tự trường, phiên bản và charset; kiểm thử đọc lại. Với dữ liệu trao đổi hệ thống, cân nhắc định dạng có schema/ràng buộc rõ thay vì deserialization Java từ nguồn không đáng tin.

**Đạt khi:** đưa ra lý do kỹ thuật cho API đã chọn theo kiểu dữ liệu, kích thước, nhu cầu hiệu năng, độ tin cậy và khả năng bảo trì.

## 5. Ví dụ Java 17 hoàn chỉnh: ghi và đọc UTF-8 an toàn

Ví dụ dưới đây minh họa **chặng 1–3**: tạo tệp tạm, ghi UTF-8, đọc từng dòng, đóng reader tự động và xóa tệp trong `finally`. Tên tệp tạm được hệ thống tạo, nên chương trình không phụ thuộc thư mục chạy.

Lưu tệp với tên **`IoRoadmapDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class IoRoadmapDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("io-roadmap-", ".txt");

        try {
            Files.writeString(file, "Xin chào\nJava I/O\n", StandardCharsets.UTF_8);

            try (BufferedReader reader =
                    Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                String line;
                int lineNumber = 0;
                while ((line = reader.readLine()) != null) {
                    System.out.println(++lineNumber + ": " + line);
                }
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+ (lưu mã nguồn ở UTF-8):

```bash
javac -encoding UTF-8 IoRoadmapDemo.java
java IoRoadmapDemo
```

Kết quả stdout chính xác trong lần chạy thành công:

```text
1: Xin chào
2: Java I/O
```

**Vì sao chương trình đúng:** `Files.writeString` chuyển văn bản thành byte UTF-8; `Files.newBufferedReader` chuyển byte UTF-8 trở lại thành dòng ký tự; `readLine()` trả `null` sau dòng cuối; `try-with-resources` đóng reader; `finally` cố gắng xóa tệp tạm kể cả khi đọc có lỗi. `main throws IOException` cho phép lỗi I/O đi ra cho người chạy thấy thay vì nuốt mất lỗi. Trong ứng dụng thực tế, chọn chính sách log/thông báo/khôi phục phù hợp.

**Giới hạn của ví dụ:** đây là tệp nhỏ và ứng dụng một luồng; nó chưa minh họa sao chép nhị phân, xử lý dữ liệu nhiều GB, concurrent writers hay ghi tệp quan trọng theo kiểu atomic replacement.

## 6. Chọn công cụ theo tình huống

| Tình huống | Lựa chọn khởi đầu | Cảnh báo quan trọng |
| --- | --- | --- |
| Đọc/ghi tệp văn bản nhỏ | `Files.readString` / `Files.writeString` với charset | Nội dung lớn có thể tiêu tốn nhiều RAM |
| Đọc văn bản theo từng dòng | `Files.newBufferedReader` hoặc `Files.lines` | Đóng reader/stream; nhớ line ending không được giữ nguyên |
| Sao chép tệp thông thường | `Files.copy` | Chọn chính sách tệp đích có sẵn, xử lý lỗi; không giả định thao tác luôn atomic |
| Sao chép byte giữa hai nguồn/đích | `InputStream` + `OutputStream`, `transferTo` | Đóng cả hai resource; không chuyển nhị phân thành text |
| Duyệt nhiều tệp trong thư mục | `Files.walk` hoặc `walkFileTree` | Giới hạn độ sâu/quyền/symlink; đóng stream |
| Truy cập ngẫu nhiên vùng byte | `FileChannel` và `ByteBuffer` | Hiểu `position`/`limit` và kết quả `read`/`write` có thể từng phần |
| Nhiều kết nối mạng cùng lúc | NIO selector / asynchronous API khi đo đạc chứng minh cần | Nhiều trạng thái và lỗi hơn; không dùng chỉ vì tên “NIO” |

## 7. Thứ tự thực hành và tiêu chí tự kiểm tra

1. **Bài tập văn bản:** ghi tệp `notes.txt` UTF-8 gồm chữ tiếng Việt và emoji; đọc lại; tự kiểm chứng byte và ký tự có độ dài khác nhau.
2. **Bài tập nhị phân:** sao chép ảnh/tệp ZIP bằng byte stream; so kích thước và nội dung byte giữa hai tệp, không dùng `Reader`.
3. **Bài tập file lớn:** đếm số dòng bằng `BufferedReader` hoặc `Files.lines` với tài nguyên được đóng; giải thích lý do không dùng `readAllLines` cho tệp lớn.
4. **Bài tập lỗi:** thử đường dẫn sai và đường dẫn không có quyền truy cập (nếu môi trường cho phép); phân biệt thông báo cho người dùng với log chẩn đoán; bảo đảm không bỏ qua ngoại lệ.
5. **Bài tập tổ chức:** duyệt thư mục con, liệt kê tên/kích thước, xử lý các mục bị xóa trong khi đang duyệt.
6. **Bài tập NIO:** đọc file bằng `FileChannel` và buffer, ghi chú trạng thái buffer trước và sau `flip()`; đối chiếu với API stream đã biết.

Có thể dùng các câu hỏi sau làm checkpoint:

- Vì sao không mở ảnh bằng `BufferedReader` để sao chép?
- `read()` trả `-1` khác gì so với ngoại lệ?
- `readLine()` trả `null` trong trường hợp nào? Nó có giữ `\r\n` không?
- Khi nào `Files.readString` tiện lợi, và khi nào nên đọc từng dòng/từng khối?
- `try-with-resources` đóng những gì, còn `Path` có cần đóng không?
- Vì sao gọi `Files.exists(path)` rồi mới ghi vẫn có thể gặp lỗi?
- Khi sử dụng `Files.lines` hoặc `Files.walk`, trách nhiệm đóng tài nguyên thuộc về ai?
- Trong một ví dụ ByteBuffer ghi rồi đọc, `flip()` thay đổi trạng thái gì?

Nếu còn lúng túng với hai câu đầu liên quan đến **byte/text** và **EOF/ngoại lệ**, nên củng cố chặng 1–2 trước khi học channel hoặc selector.

## 8. Lỗi phổ biến cần tránh xuyên suốt lộ trình

- **Dùng charset ngầm định:** có thể cho kết quả khác trên các môi trường hoặc làm hỏng dữ liệu; ghi rõ UTF-8 tại ranh giới chuyển đổi khi định dạng yêu cầu.
- **Dùng `readAllBytes`/`readAllLines` cho mọi tệp:** dữ liệu lớn có thể gây áp lực heap; ưu tiên đọc theo khối/dòng nếu không cần giữ toàn bộ.
- **Quên đóng tài nguyên:** gây rò rỉ file descriptor hoặc giữ khóa tài nguyên; dùng `try-with-resources` theo vòng đời thật.
- **Không kiểm tra số byte thực đọc:** `read(byte[])` có thể đọc ít hơn độ dài mảng, ngay cả trước EOF; chỉ xử lý số byte phương thức thực trả về.
- **Giả định một lần ghi luôn hoàn tất mọi byte với NIO channel:** kiểm tra giá trị trả về của `write` và lặp nếu giao thức/thao tác yêu cầu ghi đủ.
- **Nuốt `IOException`:** làm mất nguyên nhân và khiến đầu ra tưởng đã thành công; báo lỗi đúng tầng, có thông tin ngữ cảnh và giữ nguyên cause khi bọc ngoại lệ.
- **Đưa đường dẫn từ người dùng vào thao tác nhạy cảm mà không kiểm soát:** chuẩn hóa, xác định thư mục gốc cho phép, xét symlink và kiểm soát quyền truy cập; `normalize()` chỉ xử lý cú pháp, không tự ngăn path traversal.
- **Coi `flush` hoặc `close` là đồng nghĩa ghi bền vững tuyệt đối:** yêu cầu độ bền cao cần xem đặc tính filesystem, đồng bộ dữ liệu và chiến lược thay thế/khôi phục.
- **Học selector/async quá sớm:** làm mờ lỗi cơ bản về charset, EOF và cleanup; chỉ tiến lên khi các bài tập nền tảng ổn định.

## 9. Khi nào sẵn sàng học chủ đề I/O kế tiếp?

Bạn có thể tiến từ phần tổng quan sang các bài chuyên sâu khi tự viết được chương trình Java 17 đọc/ghi UTF-8, sao chép tệp nhị phân mà không làm biến đổi dữ liệu, xử lý EOF chính xác và đóng tài nguyên dù có ngoại lệ. Từ nền tảng đó, học `Path`/`Files` → luồng byte/ký tự và buffering → xử lý dữ liệu lớn/lỗi → duyệt file tree → `ByteBuffer`/`Channel` → networking/serialization/async theo yêu cầu bài toán sẽ giúp mỗi API mới gắn với một vấn đề cụ thể.