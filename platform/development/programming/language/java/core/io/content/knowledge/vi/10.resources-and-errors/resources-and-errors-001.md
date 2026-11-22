# IOException và các lỗi thường gặp khi mở, đọc hoặc ghi trong Java I/O

## 1. Mục tiêu: hiểu lỗi I/O xảy ra ở đâu và xử lý đúng

Một chương trình Java đọc tệp tưởng như chỉ gồm ba bước: mở, đọc, đóng. Thực tế, mỗi bước có thể thất bại độc lập vì dữ liệu I/O nằm ngoài quyền kiểm soát hoàn toàn của JVM: tệp bị di chuyển, quyền truy cập thay đổi, thiết bị hết dung lượng, kết nối bị cắt, đường dẫn trỏ tới thư mục thay vì tệp, hoặc thao tác đóng phát hiện dữ liệu chưa thể ghi.

`IOException` là ngoại lệ kiểm tra (*checked exception*) nền tảng của `java.io` và nhiều API `java.nio.file`, báo rằng một thao tác nhập/xuất đã thất bại hoặc bị gián đoạn theo hợp đồng của API. Bài này giúp phân biệt:

- **Lỗi mở**: không thể có được một luồng/kênh hoặc tạo tệp theo yêu cầu.
- **Lỗi đọc**: tài nguyên đã mở, nhưng không thể lấy dữ liệu tiếp hoặc dữ liệu không phù hợp với hợp đồng đọc.
- **Lỗi ghi**: không thể đưa dữ liệu tới đích, có thể sau khi một phần đã được ghi.
- **Lỗi flush/close**: kết thúc thao tác có thể thất bại; không được coi “đã gọi write” đồng nghĩa dữ liệu đã lưu an toàn.
- **Phản ứng của chương trình**: ghi nhận nguyên nhân, dọn tài nguyên, quyết định có thử lại, kiểm tra hậu điều kiện và tránh làm hỏng dữ liệu.

Một chuỗi xử lý thường có dạng:

~~~text
Path / nguồn I/O
    |
    v
OPEN  --IOException--> phân loại lỗi mở (không tồn tại, quyền, trùng tên...)
    |
    v
READ / WRITE --IOException--> biết đã xử lý được một phần hay chưa?
    |
    v
FLUSH / CLOSE --IOException--> không được đánh mất lỗi chính
    |
    v
Đánh giá hậu điều kiện / ghi log / báo lỗi cho người dùng
~~~

Không phải mọi lỗi xảy ra cạnh thao tác I/O đều là `IOException`. Ví dụ, `NullPointerException` khi truyền tham số null, `IllegalArgumentException` khi cấu hình không hợp lệ, và `SecurityException` do chính sách truy cập có thể là ngoại lệ runtime. Không bắt `IOException` rồi cho rằng đã xử lý được mọi lỗi của chương trình.

## 2. Phân cấp ngoại lệ cần biết

`IOException` kế thừa `Exception`, nên là **checked exception**: phương thức phát sinh thường phải được xử lý bằng `try/catch` hoặc khai báo `throws`. Một số lớp thường gặp:

| Loại | Khi nào hay gặp | Ghi chú |
| --- | --- | --- |
| `IOException` | Lỗi I/O không có kiểu con cụ thể hoặc cần trừu tượng hóa | Không nên suy diễn nguyên nhân chỉ từ thông điệp |
| `FileNotFoundException` | Mở tệp qua `FileInputStream`/`FileOutputStream` thất bại | Có thể do không tồn tại **hoặc** nguyên nhân khác như quyền, đường dẫn không hợp lệ theo ngữ cảnh |
| `NoSuchFileException` | `java.nio.file.Files` không tìm thấy tệp/thành phần cần thiết | Là kiểu con của `FileSystemException` |
| `AccessDeniedException` | Từ chối truy cập ở tầng hệ thống tệp | Là kiểu con của `FileSystemException`; môi trường có thể báo kiểu khác |
| `FileAlreadyExistsException` | Cố tạo tệp đã tồn tại trong thao tác không cho phép ghi đè | Thường liên quan `CREATE_NEW` hoặc `Files.createFile` |
| `FileSystemException` | Lỗi hệ thống tệp có thông tin tệp, tệp khác, lý do tùy môi trường | Phù hợp khi chẩn đoán lỗi NIO |
| `EOFException` | API yêu cầu một lượng dữ liệu bắt buộc, nhưng kết thúc quá sớm | Khác với EOF bình thường là `read() == -1` |
| `UTFDataFormatException` | Lỗi dữ liệu UTF theo định dạng mà API cụ thể mong đợi | Hay gặp khi `DataInput.readUTF()` gặp dữ liệu modified UTF-8 không hợp lệ |
| `CharacterCodingException` | Lỗi mã hóa/giải mã ký tự theo chính sách báo lỗi | Có thể có các lớp con như `MalformedInputException` |
| `SocketException` | Lỗi socket trong quá trình giao tiếp mạng | Phụ thuộc ngữ cảnh và trạng thái kết nối |
| `InterruptedIOException` | I/O bị gián đoạn theo hợp đồng một số API | Không đánh đồng mọi gián đoạn thread với ngoại lệ này |

Các lớp nói trên không thay thế việc đọc hợp đồng của phương thức gọi. Với cùng một tình huống “tệp không tồn tại”, `Files.newInputStream(path)` thường ném `NoSuchFileException`, còn `new FileInputStream(file)` thường ném `FileNotFoundException`. Loại cụ thể và thông điệp có thể khác giữa provider hệ thống tệp, OS và API.

### 2.1. `throws IOException` hay `catch IOException`?

Phương thức ở tầng thấp thường **khai báo `throws IOException`** để tầng gọi biết có thể thất bại:

~~~java
static byte[] load(Path path) throws IOException {
    return Files.readAllBytes(path);
}
~~~

Đây là đoạn phương thức minh họa; cần import `java.nio.file.Files`, `java.nio.file.Path` và `java.io.IOException`; nó không phải chương trình độc lập. Dù ngắn, đây vẫn là một quyết định về API: caller phải xử lý lỗi, không âm thầm trả byte[] rỗng khi việc đọc thất bại.

Ở tầng điều phối ứng dụng, nên **bắt nơi có đủ thông tin để quyết định**: thử lại, trả lỗi HTTP, hiển thị thông báo, hoặc ngừng xử lý. Không cần thêm catch ở mọi lớp chỉ để in stack trace rồi ném lại.

### 2.2. Một lỗi thường không có “mã lỗi” bất biến xuyên nền tảng

Không nên viết logic nghiệp vụ bằng cách tìm chuỗi `"Permission denied"` hay `"The system cannot find the file specified"` trong `getMessage()`. Thông điệp phụ thuộc hệ điều hành, provider, ngôn ngữ và phiên bản.

Nếu API trả kiểu con ổn định như `NoSuchFileException` hoặc `FileAlreadyExistsException`, hãy bắt theo kiểu cụ thể. Nếu chỉ nhận `IOException` tổng quát, giữ nguyên `cause` và log đầy đủ ngữ cảnh để chẩn đoán thay vì đoán từ thông điệp.

## 3. Lỗi trong giai đoạn mở tài nguyên

### 3.1. Đường dẫn không tồn tại hoặc sai thành phần

Với NIO:

~~~java
try (InputStream in = Files.newInputStream(path)) {
    // Đọc tệp...
} catch (NoSuchFileException e) {
    // Không tìm thấy tệp hoặc thành phần cần thiết.
}
~~~

Đây là đoạn minh họa, với `Path path` đã có và các import `java.io.InputStream`, `java.nio.file.Files`, `java.nio.file.NoSuchFileException`. Một đường dẫn chưa tồn tại không phải lúc nào cũng là lỗi: khi **ghi để tạo tệp mới**, chương trình có thể chủ động dùng `CREATE` hoặc `CREATE_NEW`. Điều quan trọng là phân biệt **mở để đọc** với **mở để ghi/tạo**.

Không dùng `Files.exists(path)` rồi coi đó là bảo đảm tệp sẽ còn tồn tại lúc `open`. Giữa hai thao tác, tiến trình khác có thể xóa hoặc di chuyển tệp. Đây là vấn đề **time-of-check to time-of-use (TOCTOU)**. Hãy xử lý ngoại lệ của thao tác thực sự mở tài nguyên, thay vì chỉ dựa vào lần kiểm tra trước đó.

### 3.2. Truy cập bị từ chối

`AccessDeniedException` có thể xuất hiện khi người dùng chạy chương trình không có quyền cần thiết, thư mục không cho truy cập, hoặc chính sách filesystem từ chối thao tác. Tuy nhiên, quyền thực tế còn phụ thuộc ACL, quyền sở hữu, sandbox, file lock và provider.

Cách xử lý tốt thường là báo đường dẫn liên quan và yêu cầu quyền hợp lệ; **không** tự động đổi quyền của hàng loạt tệp hoặc chạy chương trình với đặc quyền cao hơn chỉ vì thao tác thất bại. Trong môi trường server, log nội bộ có thể chứa đường dẫn chi tiết, còn thông báo cho người dùng nên tránh tiết lộ cấu trúc thư mục nhạy cảm.

### 3.3. Tệp đã tồn tại và lựa chọn ghi đè

`Files.createFile(path)` và `Files.newOutputStream(path, StandardOpenOption.CREATE_NEW)` yêu cầu tạo đối tượng mới; nếu đã tồn tại, thường nhận `FileAlreadyExistsException`.

~~~java
try (OutputStream out = Files.newOutputStream(
        path, StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE)) {
    out.write(data);
} catch (FileAlreadyExistsException e) {
    // Không ghi đè dữ liệu đang có.
}
~~~

Đoạn minh họa sử dụng `Path path` và `byte[] data` có sẵn, cùng import từ `java.io`, `java.nio.file`. Với ứng dụng cần bảo vệ tệp hiện có, `CREATE_NEW` tốt hơn mô hình “kiểm tra `exists` rồi tự mở” vì điều kiện không tồn tại và thao tác tạo được yêu cầu thực hiện nguyên tử theo hợp đồng của API đối với provider hỗ trợ.

Ngược lại, khi dùng `Files.newOutputStream(path)` **không truyền option**, mặc định thường tương đương tạo nếu cần và cắt ngắn tệp nếu tồn tại. Đây có thể là hành vi phá dữ liệu nếu người lập trình nhầm với “mở để nối thêm”.

### 3.4. Tệp là thư mục, đường dẫn vô hiệu và các vấn đề filesystem

Nguồn lỗi mở không chỉ là thiếu tệp:

- Đích mong đợi tệp thường nhưng lại là thư mục.
- Thành phần thư mục cha chưa tồn tại.
- Đường dẫn quá dài hoặc bị provider không hỗ trợ.
- Tệp bị khóa hoặc đang được ứng dụng khác sử dụng theo cách không tương thích.
- Ổ đĩa ngoài bị ngắt kết nối hay filesystem chuyển sang trạng thái chỉ đọc.

Loại ngoại lệ cụ thể không nhất thiết giống nhau trên mọi OS. Thay vì viết nhiều điều kiện phỏng đoán cho mọi trường hợp, xử lý nguyên nhân hữu ích theo kiểu khi có thể và để `IOException` còn lại đi theo đường báo lỗi đầy đủ.

## 4. Ví dụ Java 17: phân biệt tệp không tồn tại và tệp đã có

Lưu thành tệp **OpenFileFailuresDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public class OpenFileFailuresDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("io-errors-demo-");
        Path file = directory.resolve("data.txt");

        try {
            try {
                Files.readString(file, StandardCharsets.UTF_8);
            } catch (NoSuchFileException e) {
                System.out.println("Missing file: true");
            }

            Files.createFile(file);
            try {
                Files.createFile(file);
            } catch (FileAlreadyExistsException e) {
                System.out.println("Already exists: true");
            }

            Files.writeString(file, "Java I/O", StandardCharsets.UTF_8);
            System.out.println("Content: " +
                    Files.readString(file, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 OpenFileFailuresDemo.java
java OpenFileFailuresDemo
~~~

Kết quả trên filesystem thông thường hỗ trợ các thao tác nêu trên:

~~~text
Missing file: true
Already exists: true
Content: Java I/O
~~~

Chương trình tự tạo thư mục tạm mới, nên tên cụ thể của thư mục không ảnh hưởng output. Lần đọc đầu mở một tệp chưa từng được tạo trong thư mục đó, minh họa `NoSuchFileException`. Lần tạo thứ hai dùng `Files.createFile` trên tệp đã tồn tại, minh họa `FileAlreadyExistsException`. Sau cùng, chương trình ghi rồi đọc nội dung bình thường.

`finally` dọn tài nguyên thử nghiệm. Nếu quá trình xóa thất bại, nó cũng có thể ném `IOException`; ví dụ nhỏ này chấp nhận để caller thấy lỗi dọn dẹp. Trong hệ thống sản xuất, cần quản lý ngoại lệ dọn dẹp để không làm mất dấu nguyên nhân chính, như phần `try-with-resources` phía dưới.

## 5. Lỗi khi đọc: EOF bình thường khác IOException

### 5.1. EOF không phải lỗi trong vòng lặp đọc hết

Với `InputStream.read()`, giá trị `-1` biểu diễn **hết dữ liệu** (EOF). Giá trị `0..255` là byte hợp lệ. Một vòng lặp:

~~~java
int value;
while ((value = input.read()) != -1) {
    // Xử lý value.
}
~~~

Đây là đoạn minh họa với `InputStream input` đã mở. EOF bình thường không yêu cầu ném `EOFException`: nó là điều kiện kết thúc hợp lệ khi mục tiêu là “đọc cho tới hết”.

Với `read(byte[])`, hàm trả số byte thực tế hoặc `-1` khi hết dữ liệu. **Đừng xem một lần đọc ngắn hơn buffer là lỗi**: luồng tệp, socket và wrapper có thể trả ít byte hơn yêu cầu dù vẫn còn dữ liệu. Luôn dựa vào `count` để xử lý phần hợp lệ.

### 5.2. EOFException: dữ liệu bắt buộc bị thiếu

Trường hợp khác là giao thức cần đọc **đúng N byte**, ví dụ 4 byte đầu biểu diễn số nguyên. `DataInputStream.readInt()` cần đủ bốn byte; nếu nguồn chỉ có hai byte rồi EOF, phương thức sẽ ném `EOFException`.

~~~java
try (DataInputStream in = new DataInputStream(
        new ByteArrayInputStream(new byte[] {0x01, 0x02}))) {
    int number = in.readInt(); // Thiếu hai byte: EOFException.
}
~~~

Đoạn minh họa cần import `java.io.DataInputStream` và `ByteArrayInputStream`, cùng xử lý `IOException`. Đây không phải lỗi của `read() == -1` theo nghĩa thông thường: **hợp đồng đọc đủ dữ liệu bắt buộc không được đáp ứng**.

`InputStream.readNBytes(n)` có thể trả mảng ngắn hơn `n` nếu EOF sớm; `readNBytes(byte[], off, len)` trả số byte thực sự đọc. Nếu nghiệp vụ đòi chính xác N byte, caller phải kiểm tra số lượng và tự ném `EOFException` hoặc thông báo lỗi thiếu dữ liệu. Không nên tự suy ra mọi API “read N” đều ném cùng loại ngoại lệ.

### 5.3. IOException giữa chừng không phải EOF

Một nguồn có thể đọc thành công vài byte rồi thất bại vì kết nối bị cắt hoặc thiết bị lỗi. Ví dụ:

~~~text
Lượt 1: read(buffer) → 100 byte hợp lệ
Lượt 2: read(buffer) → 72 byte hợp lệ
Lượt 3: read(buffer) → IOException
~~~

Nếu chương trình bắt ngoại lệ và coi như đã EOF, nó sẽ giữ một dữ liệu **bị cắt cụt** mà không báo lỗi. Đây là lỗi logic nguy hiểm khi đọc ảnh, file cấu hình, bản ghi giao dịch hoặc gói dữ liệu có định dạng.

Một chiến lược đúng:

- Đọc đến `-1` nếu hợp đồng cho phép dữ liệu có độ dài không biết trước.
- Nếu cần kiểm tra kích thước, checksum hoặc dấu kết thúc, so sánh chúng **sau khi đọc thành công**.
- Khi đọc ném `IOException`, giữ trạng thái kết quả là **thất bại**, không “thành công với ít dữ liệu”.
- Chỉ sử dụng prefix dữ liệu đã đọc nếu nghiệp vụ định nghĩa rõ kết quả một phần có giá trị và cung cấp cờ/trạng thái tương ứng.

### 5.4. read() có thể chặn

Với nguồn sống như socket, `read()` có thể chờ dữ liệu. Việc chưa trả byte không phải `IOException`, và một số API có cơ chế timeout riêng. Đừng dùng `available() == 0` để quyết định EOF: đó là số byte có thể đọc ngay theo hợp đồng lớp, **không** nhất thiết là toàn bộ nội dung còn lại. Với I/O không chặn, giá trị 0 còn có thể nghĩa là tạm thời chưa có dữ liệu, khác với `-1` là kết thúc.

## 6. Ví dụ Java 17: lỗi trong quá trình đọc sau khi đã có dữ liệu

Để kiểm tra logic mà không phụ thuộc vào thiết bị thật, có thể dùng một `InputStream` tự tạo luôn đọc được hai byte rồi cố ý ném `IOException`. Demo chứng minh lỗi không bị coi như EOF.

Lưu thành **ReadFailureDemo.java**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;

public class ReadFailureDemo {
    static class FailingInput extends InputStream {
        private int position;

        @Override
        public int read() throws IOException {
            if (position == 0) {
                position++;
                return 'O';
            }
            if (position == 1) {
                position++;
                return 'K';
            }
            throw new IOException("Simulated read failure");
        }
    }

    public static void main(String[] args) {
        try (InputStream input = new FailingInput();
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {

            int next;
            while ((next = input.read()) != -1) {
                output.write(next);
            }
            System.out.println("Read completed");
        } catch (IOException e) {
            System.out.println("Read failed: " + e.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReadFailureDemo.java
java ReadFailureDemo
~~~

Kết quả:

~~~text
Read failed: Simulated read failure
~~~

Hai byte `O` và `K` đã được đọc trước khi lỗi, nhưng chương trình không in `Read completed` vì vòng lặp chưa kết thúc bằng EOF. Trong ứng dụng thật, chính sách có thể trả một đối tượng kết quả mang trạng thái `PARTIAL_FAILURE`, hoặc hủy toàn bộ việc xử lý để tránh trình bày dữ liệu chưa hoàn chỉnh như thành công.

**Lưu ý:** Đây là `InputStream` mô phỏng lỗi được thiết kế cho kiểm thử, không phải một cách gây lỗi hệ điều hành. Nó cũng chỉ ghi một byte mỗi lần để demo dễ kiểm chứng; khi đọc lượng lớn, thường nên dùng mảng buffer.

## 7. Lỗi khi ghi: dữ liệu có thể đã được ghi một phần

### 7.1. write không trả số byte đã ghi

`OutputStream.write(byte[], off, len)` theo API trả về `void`. Khi hoàn tất thành công, nó được kỳ vọng ghi đúng đoạn được yêu cầu theo hợp đồng; khi thất bại, nó có thể ném `IOException`. Nếu lỗi xảy ra sau một phần dữ liệu, **API tổng quát không trả về thông số đáng tin cậy “đã ghi được bao nhiêu byte”**.

Vì vậy, không nên:

~~~java
try {
    output.write(payload);
} catch (IOException e) {
    output.write(payload); // Sai: có thể ghi trùng một phần đã thành công.
}
~~~

Đây là đoạn minh họa **cách làm không an toàn**, với `output` và `payload` đã có. Nếu lần thứ nhất đã đẩy được một số byte rồi lỗi, ghi lại toàn bộ sẽ có nguy cơ trùng dữ liệu. Trên mạng, ngay cả việc client có thấy IOException không cũng chưa đủ kết luận server đã hay chưa nhận thông điệp.

Thử lại cần dựa vào **đặc tính thao tác và giao thức**:

- **Idempotent**: lặp lại yêu cầu nhiều lần vẫn cho hiệu quả cuối tương đương. Ví dụ thay thế nội dung tệp tạm hoàn chỉnh rồi đổi tên theo giao thức xác định, khi được thiết kế đúng.
- **Không idempotent**: mỗi lần ghi là một sự kiện mới hoặc append có thể nhân đôi dữ liệu. Không tự thử lại toàn bộ.
- **Có xác nhận**: giao thức có mã yêu cầu, vị trí/offset, checksum hoặc xác nhận để đối chiếu trạng thái và khôi phục an toàn.

### 7.2. Thiết bị hết dung lượng, tệp chỉ đọc, kết nối đóng

Các nguyên nhân phổ biến:

- Filesystem hết dung lượng hoặc vượt quota.
- Không còn quyền ghi tại thời điểm thao tác.
- Ổ đĩa/thiết bị bị tháo, tệp trở nên không khả dụng.
- Đích là socket đã bị đóng hoặc kết nối mạng lỗi.
- Tên đường dẫn mới không hợp lệ hoặc cấu trúc thư mục không tồn tại.
- Luồng/kênh đã đóng trước đó (tùy API có thể ném `IOException` hoặc ngoại lệ khác).

Một ví dụ dễ nhầm là `Files.writeString(path, text)`: lệnh gọi thành công cho biết API đã hoàn tất thao tác ghi theo hợp đồng, **không nhất thiết** là dữ liệu đã được đồng bộ tới bộ lưu trữ bền vững vật lý. Nếu bài toán yêu cầu tính bền vững khi mất điện, cần thảo luận mức độ đồng bộ và hợp đồng filesystem riêng.

### 7.3. Ghi đè hay append là quyết định nghiệp vụ

Một thao tác ghi cần được thiết kế rõ ràng: tạo mới duy nhất, thay thế toàn bộ hay nối thêm:

~~~java
Files.writeString(path, "hello", StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
~~~

Đoạn minh họa có `Path path` và import NIO cần thiết. Với lựa chọn trên, tồn tại sẵn thường gây `FileAlreadyExistsException`. Nếu muốn nối thêm:

~~~java
Files.writeString(path, "append", StandardCharsets.UTF_8,
        StandardOpenOption.CREATE, StandardOpenOption.APPEND);
~~~

Đây cũng là đoạn minh họa, không độc lập. `APPEND` không tự thêm dấu xuống dòng và không làm mỗi lần ghi trở thành một giao dịch nguyên tử đối với mọi filesystem. Nếu logic yêu cầu “mỗi bản ghi nguyên vẹn hoặc không có”, cần giải pháp phù hợp hơn là đơn thuần gọi append.

## 8. Buffered I/O: flush() và close() cũng có thể báo lỗi

`BufferedWriter` và `BufferedOutputStream` thường giữ dữ liệu trong bộ nhớ trước khi chuyển tới đích bên dưới. Vì thế:

1. Một lời gọi `write` có thể chỉ ghi vào buffer của ứng dụng và thành công.
2. `flush()` yêu cầu chuyển phần dữ liệu đang đệm xuống luồng bên dưới; ở bước này mới có thể xuất hiện `IOException`.
3. `close()` có thể flush/đóng tài nguyên và báo lỗi.
4. Không đồng nhất `flush()` với bảo đảm dữ liệu **bền vững trên ổ đĩa**. Việc đồng bộ vật lý, nếu cần, liên quan API và filesystem như `FileChannel.force(...)`, cũng không tạo bảo đảm tuyệt đối cho mọi ngữ cảnh phần cứng.

Ví dụ:

~~~java
try (BufferedWriter writer =
        Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("Tài liệu quan trọng");
} // writer.close() được gọi ở đây và có thể ném IOException.
~~~

Đoạn minh họa với `Path path` đã có. Nếu `writer.write(...)` thành công nhưng close thất bại, không được ghi nhận toàn bộ thao tác là thành công chắc chắn; cần xử lý lỗi từ cả lúc viết và lúc đóng.

### 8.1. Đừng tự close trong try-with-resources

Không cần:

~~~java
try (OutputStream out = Files.newOutputStream(path)) {
    out.write(payload);
    out.close(); // Thừa; làm code khó quản lý vòng đời.
}
~~~

Đây là đoạn minh họa. `try-with-resources` tự động gọi close cuối phạm vi, kể cả khi thân `try` ném ngoại lệ. Gọi sớm có thể không phù hợp nếu còn sử dụng stream sau đó và có thể khiến xử lý lỗi khó theo dõi.

## 9. try-with-resources: bảo toàn lỗi chính và suppressed exceptions

Cú pháp `try-with-resources` ưu tiên cho tài nguyên triển khai `AutoCloseable`, trong đó `InputStream`, `OutputStream`, `Reader` và `Writer` thường áp dụng được.

~~~java
try (InputStream input = Files.newInputStream(source);
     OutputStream output = Files.newOutputStream(target)) {
    input.transferTo(output);
}
~~~

Đây là đoạn minh họa với `Path source` và `Path target`. Các tài nguyên được đóng **theo thứ tự ngược với thứ tự khai báo**: `output` rồi `input`.

Giả sử:

- Trong thân `try` xảy ra lỗi đọc `IOException("read failed")`.
- Khi đóng output, lại xảy ra lỗi `IOException("close failed")`.

Nếu dùng `try-with-resources`, ngoại lệ từ thân `try` là lỗi chính, còn lỗi đóng được gắn vào danh sách **suppressed exceptions** thông qua `Throwable.getSuppressed()`. Điều này giúp chẩn đoán cả hai nguyên nhân mà không đánh mất lỗi đầu tiên.

### 9.1. Ví dụ Java 17 tự tạo lỗi khi đóng

Lưu **SuppressedExceptionDemo.java**:

~~~java
import java.io.IOException;

public class SuppressedExceptionDemo {
    static class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        try (FailingResource resource = new FailingResource()) {
            throw new IOException("read failed");
        } catch (IOException e) {
            System.out.println("Primary: " + e.getMessage());
            System.out.println("Suppressed count: " +
                    e.getSuppressed().length);
            for (Throwable problem : e.getSuppressed()) {
                System.out.println("Suppressed: " + problem.getMessage());
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 SuppressedExceptionDemo.java
java SuppressedExceptionDemo
~~~

Kết quả:

~~~text
Primary: read failed
Suppressed count: 1
Suppressed: close failed
~~~

Đây là phép mô phỏng có kiểm soát, không phụ thuộc lỗi thiết bị thật. Nó chứng minh một ngoại lệ khi `close()` vẫn được giữ trong thông tin chẩn đoán ngay cả khi thân `try` đã thất bại trước đó.

Nếu **thân `try` hoàn tất bình thường** nhưng `close()` ném ngoại lệ, lỗi đóng trở thành ngoại lệ chính. Khi mở nhiều tài nguyên, có thể xuất hiện nhiều suppressed exception. Khi xử lý và log, nên giữ stack trace/cause đầy đủ thay vì chỉ lưu `getMessage()`.

### 9.2. Tại sao không nên viết finally với close một cách bất cẩn?

Mẫu cũ:

~~~java
InputStream in = null;
try {
    in = Files.newInputStream(path);
    // Đọc...
} finally {
    if (in != null) {
        in.close();
    }
}
~~~

Đoạn minh họa này có thể làm lỗi từ `close()` trong `finally` **che khuất** lỗi gốc trong thân `try`. Việc xử lý thủ công để giữ nguyên cả hai ngoại lệ rất dễ thiếu sót. Với Java hiện đại, ưu tiên `try-with-resources` khi có thể. Nếu buộc phải dùng `finally`, cần chủ động bảo toàn exception chính, suppressed, và bảo đảm mọi tài nguyên đều có cơ hội được đóng.

## 10. Thiết kế catch: khi nào bắt cụ thể, khi nào ném tiếp?

### 10.1. Bắt kiểu cụ thể trước kiểu tổng quát

Ví dụ API cần phân biệt ba tình huống:

~~~java
try {
    Files.readString(path, StandardCharsets.UTF_8);
} catch (NoSuchFileException e) {
    // Thiếu tệp: có thể báo mã lỗi "not found".
} catch (AccessDeniedException e) {
    // Không có quyền: báo "permission denied".
} catch (IOException e) {
    // Những lỗi I/O khác.
}
~~~

Đây là đoạn minh họa với `Path path` đã khai báo và import Java NIO. Hai lớp đầu đều là kiểu con của `IOException`, nên phải bắt trước. Nếu đặt `catch(IOException)` lên đầu, các catch bên dưới trở thành không thể tới và Java sẽ từ chối biên dịch.

Mỗi catch cần **hành động phù hợp**; không bắt nhiều kiểu chỉ để in cùng một thông báo rồi lặng lẽ cho chương trình tiếp tục như thể không có lỗi.

### 10.2. Ném tiếp nhưng bổ sung ngữ cảnh

Một lớp xử lý tệp biết tên tài nguyên hoặc thao tác đang làm có thể bổ sung ngữ cảnh:

~~~java
static byte[] readDocument(Path path) throws IOException {
    try {
        return Files.readAllBytes(path);
    } catch (IOException e) {
        throw new IOException("Failed to read document: " + path, e);
    }
}
~~~

Đây là đoạn phương thức minh họa; chưa phải chương trình độc lập. Cú pháp constructor `new IOException(message, cause)` giữ lại ngoại lệ gốc thông qua `getCause()`. Lưu ý: nếu tầng trên cần phân biệt `NoSuchFileException` bằng `catch`, bọc mọi lỗi thành `IOException` tổng quát sẽ làm mất **kiểu cụ thể ở tầng ngoài**. Vì vậy chỉ bọc khi muốn thay đổi ranh giới trừu tượng, hoặc dùng chiến lược giữ nguyên loại ngoại lệ khi cần.

Đừng bọc rồi vứt nguyên nhân:

~~~java
catch (IOException e) {
    throw new RuntimeException("Failed"); // Thiếu e làm cause.
}
~~~

Đây là ví dụ không nên làm: thông tin stack trace gốc khó truy tìm hơn. Nếu API buộc dùng unchecked exception, nên dùng `new UncheckedIOException("...", e)` cho `IOException` hoặc một exception miền nghiệp vụ có `cause`.

### 10.3. Kiểm tra log và thông báo

Log hữu ích nên chứa **thao tác**, **đường dẫn/đích đã được xử lý an toàn**, **loại ngoại lệ**, **stack trace/cause** và khi cần **số byte đã xử lý**. Tránh ghi lại toàn bộ nội dung dữ liệu nhạy cảm chỉ để chẩn đoán.

Ví dụ thông báo cho người dùng: “Không thể lưu tệp báo cáo. Hãy kiểm tra dung lượng và quyền thư mục.” Còn trong log có thể giữ `IOException` đầy đủ. Không cần tiết lộ đường dẫn hệ thống nội bộ cho người dùng cuối nếu môi trường có yêu cầu bảo mật.

## 11. Thử lại (retry) có phù hợp không?

Retry chỉ phù hợp khi lỗi có tính **tạm thời** và thao tác có thể lặp an toàn. Bảng gợi ý:

| Tình huống | Retry tự động? | Lý do |
| --- | --- | --- |
| `NoSuchFileException` vì người dùng chọn sai tên tệp | Thường không | Cần sửa đầu vào hoặc kiểm tra nguồn |
| `AccessDeniedException` do quyền cố định | Thường không | Lặp lại không tạo quyền mới |
| `FileAlreadyExistsException` khi `CREATE_NEW` | Không nên ghi đè tự động | Vi phạm mục tiêu bảo vệ tệp hiện hữu |
| Mất kết nối mạng tạm thời trước khi truyền gì | Có thể, tùy giao thức | Cần xác minh trạng thái và điều kiện thử lại |
| Ghi append thất bại giữa chừng | Không retry toàn bộ nếu chưa có giao thức chống trùng | Có thể chèn dữ liệu lặp |
| Đọc tệp không đổi từ đầu sau lỗi tạm thời | Có thể, nếu nguồn/phiên bản được kiểm soát | Không được giả định tệp vẫn giữ nội dung cũ |
| Không đủ dung lượng ổ đĩa | Thường không ngay lập tức | Cần giải phóng dung lượng hoặc đổi đích |

Nếu thử lại, nên:

1. Giới hạn số lần và thời gian tổng.
2. Có khoảng chờ phù hợp; với dịch vụ phân tán có thể dùng exponential backoff và jitter.
3. Xác định **điều kiện an toàn/idempotence**.
4. Ghi nhận nguyên nhân của lần thất bại và kết quả cuối.
5. Không retry khi đã bị hủy/cần dừng, và không dùng retry để che sai định dạng hoặc thiếu quyền.

Ví dụ nếu ghi tệp bằng một tệp tạm rồi thay thế đích, mỗi lần thử cần tạo tệp tạm mới hoặc xử lý chính xác trạng thái tệp tạm cũ. Nếu gửi dữ liệu cho server, cần mã yêu cầu idempotency hoặc xác nhận theo giao thức để tránh nhân đôi tác vụ.

## 12. Ghi tệp an toàn hơn khi lỗi xuất hiện giữa chừng

Trực tiếp ghi đè tệp đích có rủi ro: nếu tiến trình lỗi sau khi tệp đã bị cắt ngắn mà trước khi hoàn tất, dữ liệu cũ đã mất, dữ liệu mới chưa đầy đủ.

Một chiến lược thường dùng cho **một tệp**:

1. Tạo **tệp tạm riêng** trong cùng thư mục/ filesystem với đích.
2. Ghi toàn bộ nội dung mới vào tệp tạm; đóng tài nguyên và kiểm tra hậu điều kiện.
3. Chỉ khi quá trình ghi/đóng hoàn tất, thử **di chuyển tệp tạm sang đích**.
4. Khi cần cam kết đổi tên nguyên tử, yêu cầu `StandardCopyOption.ATOMIC_MOVE` và xử lý `AtomicMoveNotSupportedException` thay vì lặng lẽ hạ cấp khi hợp đồng nghiệp vụ không cho phép.
5. Nếu cần cam kết bền vững khi mất điện, xem xét `FileChannel.force`, đồng bộ dữ liệu/metadata và đặc tính hệ thống tệp; **atomic rename không đồng nghĩa với fsync hoặc transaction toàn hệ thống**.
6. Nếu bất kỳ bước nào lỗi, báo kết quả thất bại và dọn tệp tạm theo chiến lược bảo toàn thông tin lỗi.

Ví dụ minh họa phần chuyển tệp:

~~~java
Files.move(temp, target,
        StandardCopyOption.ATOMIC_MOVE,
        StandardCopyOption.REPLACE_EXISTING);
~~~

Đây là đoạn minh họa với `Path temp`, `Path target`. `ATOMIC_MOVE` chỉ có thể dùng khi provider hỗ trợ, và tác động khi đích tồn tại mang sắc thái phụ thuộc provider theo hợp đồng API. Đừng tự suy ra rằng câu lệnh bảo đảm mọi nội dung và metadata được ghi bền vững khi sự cố nguồn điện xảy ra.

Đây là **mô hình thiết kế** chứ không phải thay thế cơ chế transaction của cơ sở dữ liệu hay bảo đảm cập nhật nhiều tệp nguyên tử cùng lúc. Chọn mức độ an toàn tương ứng tính quan trọng của dữ liệu.

## 13. Ví dụ Java 17: sao chép bằng try-with-resources và kiểm tra kết quả

Lưu thành **SafeCopyDemo.java**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class SafeCopyDemo {
    public static void main(String[] args) throws IOException {
        Path folder = Files.createTempDirectory("safe-copy-");
        Path source = folder.resolve("source.bin");
        Path target = folder.resolve("target.bin");

        try {
            byte[] original = "Java IO 17".getBytes(
                    StandardCharsets.US_ASCII);
            Files.write(source, original);

            long copied;
            try (InputStream in = Files.newInputStream(source);
                 OutputStream out = Files.newOutputStream(target)) {
                copied = in.transferTo(out);
            }

            byte[] result = Files.readAllBytes(target);
            System.out.println("Copied bytes: " + copied);
            System.out.println("Matches: " +
                    Arrays.equals(original, result));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
            Files.deleteIfExists(folder);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 SafeCopyDemo.java
java SafeCopyDemo
~~~

Kết quả:

~~~text
Copied bytes: 10
Matches: true
~~~

Điểm quan trọng:

- `transferTo` trả số byte đã chuyển và không tự đóng luồng; `try-with-resources` đóng `out` rồi `in`.
- Sau khi đóng thành công, chương trình đọc đích và so sánh byte thực tế, tránh tin rằng “đã gọi write” tương đương “đã hoàn thành toàn bộ nội dung” khi có lỗi.
- Ví dụ không tạo lỗi I/O cố ý; nếu filesystem không cho tạo/xóa/ghi trong thư mục tạm, ngoại lệ sẽ được ném ra thay vì bị nuốt.
- Hàm `finally` ở ví dụ chỉ dọn tệp tạm. Với hệ thống sản xuất, nếu cleanup cũng có thể thất bại khi lỗi chính đã tồn tại, nên thiết kế báo cáo riêng hoặc ghép suppressed exception để bảo toàn nguyên nhân đầu tiên.
- Đây là thao tác sao chép demo; nó **không** bảo đảm ghi file đích theo chiến lược thay thế nguyên tử. Với nội dung nghiệp vụ quan trọng, áp dụng quy trình tệp tạm và di chuyển phù hợp.

## 14. FileInputStream/FileOutputStream và Files/NIO: khác nhau khi báo lỗi

Các API Java truyền thống và NIO có thể biểu đạt lỗi theo kiểu khác nhau:

~~~java
new FileInputStream("missing.txt");   // Thường FileNotFoundException.
Files.newInputStream(Path.of("missing.txt")); // Thường NoSuchFileException.
~~~

Đây là đoạn minh họa, không phải chương trình độc lập. Tên tệp ví dụ được giả định không tồn tại; trong thực tế điều kiện môi trường quyết định kết quả. Cần import tương ứng.

`FileNotFoundException` không nhất thiết chỉ mang nghĩa tệp thiếu; nó cũng có thể được dùng khi không mở được vì quyền hoặc các nguyên nhân tương tự. Khi muốn phân biệt lý do ở hệ thống tệp, các lớp NIO như `NoSuchFileException`, `AccessDeniedException`, `FileAlreadyExistsException` và `FileSystemException` thường giúp xử lý rõ hơn, nhưng không được giả định mọi provider luôn báo đúng cùng kiểu.

Khi chuyển mã cũ sang NIO, hãy kiểm tra lại các `catch`: nếu chỉ bắt `FileNotFoundException`, có thể bỏ sót `NoSuchFileException`. Nếu dùng `catch(IOException)` ở tầng hợp lý, vẫn xử lý được phần lớn lỗi checked I/O.

## 15. IOException với văn bản: lỗi charset không giống thiếu tệp

Đọc tệp văn bản có ít nhất **hai bước logic**: lấy byte từ nguồn và **giải mã** byte theo charset. Nếu nguồn chứa byte không hợp lệ với charset và API/decoder đang ở chế độ báo lỗi, có thể phát sinh `MalformedInputException` (kiểu con của `CharacterCodingException` và `IOException`).

Ví dụ:

~~~java
String text = Files.readString(path, StandardCharsets.UTF_8);
~~~

Đây là đoạn minh họa với `Path path`. Nếu tệp có dữ liệu không hợp lệ theo UTF-8, cách đọc này có thể ném ngoại lệ giải mã. Không nên bắt mọi `IOException` rồi báo “Không tìm thấy tệp”; tệp có thể tồn tại và đọc byte được, nhưng văn bản không hợp lệ.

Sự khác biệt:

- **NoSuchFileException**: tài nguyên không tìm thấy theo thao tác hệ thống tệp.
- **AccessDeniedException**: quyền truy cập không đủ.
- **MalformedInputException**: chuỗi byte không hợp lệ theo charset, khi dùng giải mã báo lỗi.
- **EOFException**: không đủ dữ liệu cho một trường bắt buộc theo hợp đồng đọc định dạng.

Khi dùng `InputStreamReader` hoặc `CharsetDecoder`, hành vi dữ liệu sai còn phụ thuộc `CodingErrorAction.REPORT`, `REPLACE` hoặc `IGNORE`. Nếu cần phân biệt lỗi dữ liệu, hãy chọn chính sách `REPORT` phù hợp; nếu dùng chế độ thay thế, cần biết dữ liệu có thể được sửa thành `�` thay vì ném lỗi.

Không dùng `new String(bytes)` với charset mặc định khi nguồn quy định UTF-8: lỗi đọc “ký tự lạ” đôi khi là lỗi chọn charset, không phải lỗi thiếu tệp hoặc I/O thiết bị.

## 16. IOException trong hệ thống mạng và luồng được bọc

`IOException` cũng có thể phát sinh từ socket, stream nén, stream giải mã, wrapper buffering hoặc nguồn I/O khác. Với TCP, các thông điệp như “connection reset” hoặc “broken pipe” có thể xuất hiện tùy OS và thời điểm. Không nên dựa trên một chuỗi thông báo cố định để suy ra server đã thực sự xử lý bao nhiêu dữ liệu.

Một số quy tắc:

- `read() == -1` trên socket stream biểu diễn kết thúc đầu vào theo hợp đồng; `IOException` là thất bại, không phải kết thúc bình thường.
- Kết nối có thể bị đóng giữa lúc ghi; kết quả trên phía nhận còn cần giao thức xác nhận.
- `flush()` chỉ đẩy dữ liệu trong các lớp đệm mà nó quản lý, không đồng nghĩa phía bên kia đã xử lý giao dịch.
- Nếu có timeout ở API, hãy xử lý timeout theo **trạng thái nghiệp vụ**, không mặc định retry mù.
- Khi bọc luồng (`BufferedInputStream`, `GZIPInputStream`, `InputStreamReader`), thông thường đóng wrapper sẽ đóng nguồn bên dưới. Xác định quyền sở hữu trước khi dùng `try-with-resources`.

Đối với luồng nén, dữ liệu không hoàn chỉnh có thể được phát hiện sau khi đọc khá xa hoặc khi kết thúc, tùy định dạng/checksum. Vì vậy cần để luồng báo lỗi qua hết vòng đời và không xem một phần đầu giải nén được là bằng chứng toàn bộ dữ liệu hợp lệ.

## 17. Thiết kế API để không mất thông tin lỗi

Một phương thức đọc tệp thường trả kết quả theo một trong hai cách rõ ràng:

**Cách A — checked exception:**

~~~java
byte[] load(Path source) throws IOException
~~~

Caller bắt hoặc truyền tiếp `IOException`. Đây là chữ ký minh họa, không phải phương thức đầy đủ.

**Cách B — kết quả tường minh:** đối tượng kết quả có thể chứa trạng thái thành công/thất bại và metadata cần thiết, phù hợp khi xử lý hàng loạt nhiều tệp mà không muốn một lỗi dừng toàn bộ batch. Dù dùng kiểu nào, đừng trả mảng rỗng hoặc chuỗi rỗng để biểu diễn cả “tệp rỗng hợp lệ” lẫn “đọc thất bại”.

Ví dụ cách làm cần tránh:

~~~java
static String readOrEmpty(Path path) {
    try {
        return Files.readString(path);
    } catch (IOException e) {
        return ""; // Không phân biệt tệp rỗng thật với đọc lỗi.
    }
}
~~~

Đây là đoạn phương thức minh họa **anti-pattern**. Nó biến lỗi hạ tầng thành dữ liệu nghiệp vụ giả, làm việc debug và kiểm tra kết quả khó hơn.

Khi bắt `IOException` chỉ để đổi sang exception miền nghiệp vụ, hãy giữ `cause`. Nếu caller cần biết loại lỗi cụ thể, bổ sung mã lỗi có cấu trúc hoặc để ngoại lệ gốc đi xuyên tầng phù hợp.

## 18. Checklist kiểm tra lỗi I/O

Trước khi đánh dấu một thao tác hoàn tất, hãy tự kiểm tra:

1. **Nguồn/đích nào?** Tệp, mạng, bộ nhớ hay wrapper? Có biết quyền sở hữu tài nguyên không?
2. **Thao tác nào thất bại?** Open, read, write, flush hay close? Có ghi lại giai đoạn và ngữ cảnh không?
3. **Kiểu ngoại lệ là gì?** NoSuchFile, AccessDenied, AlreadyExists, EOFException, CharacterCodingException hay IOException tổng quát?
4. **Đã xử lý được một phần dữ liệu?** Một phần đó có được phép dùng hay phải bỏ?
5. **Có dọn tài nguyên?** `try-with-resources` đã bảo toàn ngoại lệ đóng như suppressed chưa?
6. **Có nhận nhầm EOF thành lỗi hoặc ngược lại?** `-1` là kết thúc bình thường của vòng lặp đọc hết; `EOFException` khác.
7. **Có vô tình ghi đè dữ liệu cũ?** Chế độ mở và option đã được chỉ định rõ?
8. **Có kiểm tra hậu điều kiện?** Kích thước, checksum, nội dung, giao thức xác nhận hoặc trạng thái tệp đích khi phù hợp?
9. **Retry có an toàn?** Có giới hạn thử lại, cơ chế idempotency hoặc quyết định dựa trên trạng thái?
10. **Log có ích và an toàn?** Có ngữ cảnh, stack trace/cause nhưng không tiết lộ dữ liệu nhạy cảm?
11. **Có quy tắc về bền vững?** Nếu cần chống mất điện, đã xem xét fsync/force và giới hạn bảo đảm của hệ thống tệp?
12. **Có kiểm thử tình huống lỗi?** Thiếu tệp, tệp trùng, đọc ngắn, EOF sớm, lỗi đọc sau một phần dữ liệu, lỗi close và lỗi charset.

## 19. Lỗi phổ biến cần tránh

| Lỗi của người lập trình | Hệ quả | Hướng sửa |
| --- | --- | --- |
| Bắt `IOException` rồi trả `""` hoặc byte[] rỗng | Che lỗi bằng kết quả trông hợp lệ | Ném tiếp hoặc trả trạng thái lỗi riêng |
| `catch(IOException)` chỉ `printStackTrace()` rồi tiếp tục như thành công | Trạng thái chương trình sai | Tầng xử lý phải quyết định phục hồi hoặc kết thúc |
| Xem `read() == -1` là ngoại lệ | Bắt lỗi không cần thiết | Dùng -1 làm EOF bình thường |
| Xem `IOException` giữa chừng là EOF bình thường | Chấp nhận dữ liệu bị cắt | Báo trạng thái thất bại và không giả định payload đủ |
| Tin rằng `read(buffer)` luôn đầy | Đọc thiếu hoặc xử lý dữ liệu cũ | Dùng giá trị `count` |
| Dùng `available() == 0` để kết thúc | Dừng sớm với luồng sống | Đọc cho tới -1 hoặc theo giao thức |
| Tin rằng write thành công là đã fsync ổ đĩa | Đánh giá sai tính bền vững | Xác định rõ mức bảo đảm cần thiết |
| Retry toàn bộ thao tác append sau IOException | Có thể ghi trùng một phần | Chỉ retry khi có cơ chế an toàn |
| `finally` gọi close làm che lỗi chính | Mất nguyên nhân ban đầu | Ưu tiên `try-with-resources` |
| Chỉ log `e.getMessage()` | Thiếu stack trace/cause/suppressed | Giữ thông tin exception đầy đủ |
| Bắt `FileNotFoundException` cho mọi API NIO | Bỏ sót các loại lỗi NIO khác | Bắt lớp con cụ thể đúng API hoặc IOException |
| Dùng `Files.exists` để “bảo đảm” mở thành công | TOCTOU khiến điều kiện thay đổi | Xử lý ngoại lệ khi mở thực sự |
| Dùng `CREATE_NEW` nhưng tự ghi đè nếu đã có | Mất mục tiêu bảo vệ dữ liệu | Quyết định rõ chính sách conflict |
| Dùng sai charset rồi báo “file hỏng” không kiểm tra | Nhầm lỗi dữ liệu/mã hóa | Chọn charset đúng, kiểm tra chính sách decoder |
| Che ngoại lệ cleanup hoàn toàn | Không phát hiện lỗi dọn dẹp có ảnh hưởng | Giữ lỗi phụ bằng suppressed hoặc log có ngữ cảnh |

## 20. Bài tập tự kiểm tra

**Bài 1 — EOF hay lỗi?** Một vòng lặp `InputStream.read()` đọc được 10 byte rồi trả -1. Có cần ném `EOFException` không?

**Đáp án:** không, nếu mục tiêu là đọc hết luồng. EOF là điều kiện dừng hợp lệ. Nếu giao thức bắt buộc 20 byte, phải báo lỗi thiếu dữ liệu vì dữ liệu chưa đủ.

**Bài 2 — Tệp không tồn tại.** Hai phương thức `new FileInputStream(path)` và `Files.newInputStream(path)` có bắt buộc ném cùng một kiểu con không?

**Đáp án:** không. API cũ thường ném `FileNotFoundException`; NIO thường ném `NoSuchFileException`. Chọn catch theo API thực tế và vẫn có đường xử lý `IOException` tổng quát.

**Bài 3 — Sau khi write lỗi, có được tự ghi lại toàn bộ payload?**

**Đáp án:** không mặc định. Một phần payload có thể đã được gửi hoặc lưu, và ghi lại từ đầu có thể gây trùng. Cần giao thức idempotent/offset/ack hoặc quy trình thay thế an toàn.

**Bài 4 — Hai lỗi cùng lúc.** Trong `try-with-resources`, thân ném `IOException("read failed")` và close ném `IOException("close failed")`. Ngoại lệ chính là gì?

**Đáp án:** `read failed` là lỗi chính; `close failed` nằm trong `getSuppressed()`, như ví dụ `SuppressedExceptionDemo`.

**Bài 5 — Đọc UTF-8.** Tệp tồn tại và có quyền đọc, nhưng byte bên trong không tạo thành văn bản UTF-8 hợp lệ. Vì sao vẫn nhận `IOException`?

**Đáp án:** lỗi phát sinh ở bước **giải mã ký tự**, ví dụ `MalformedInputException` với chính sách REPORT, chứ không nhất thiết ở bước mở file. Không báo sai thành “tệp không tồn tại”.

**Bài 6 — Ghi thành công có đủ bảo đảm dữ liệu bền vững không?**

**Đáp án:** chưa đủ cho mọi yêu cầu. `write`, `flush`, `close` và đồng bộ dữ liệu vật lý có các hợp đồng khác nhau; nếu hệ thống yêu cầu tính bền vững qua mất điện, cần thiết kế riêng và tìm hiểu bảo đảm của filesystem/thiết bị.

### Bài tập thực hành nâng cao

1. Sửa `OpenFileFailuresDemo` để bắt thêm `IOException` tổng quát và in tên **lớp ngoại lệ** nếu phát sinh, không phân loại bằng chuỗi thông điệp.
2. Thêm `FileAlreadyExistsException` vào một chương trình tạo báo cáo: nếu đích đã có, ứng dụng phải dừng với thông báo rõ ràng, không xóa/ghi đè.
3. Viết một `InputStream` kiểm thử ném IOException ở byte thứ N và xác nhận kết quả được đánh dấu **thất bại**, không phải thành công với payload ngắn.
4. Thêm một tài nguyên thứ hai cũng lỗi khi `close()` vào `SuppressedExceptionDemo`; kiểm tra thứ tự đóng ngược và danh sách suppressed.
5. Thiết kế pseudocode cho “ghi tệp tạm → xác minh → di chuyển sang đích” với nhánh xử lý khi `ATOMIC_MOVE` không hỗ trợ, nhánh cleanup lỗi và quy tắc không làm mất dữ liệu cũ.

## Kết luận

`IOException` không chỉ có nghĩa “không tìm thấy tệp”: nó có thể xuất hiện ở **mở, đọc, ghi, flush hoặc close**, mỗi giai đoạn mang một kiểu rủi ro khác nhau. Một ứng dụng Java I/O đáng tin cậy cần:

- Phân biệt **EOF bình thường** với **thiếu dữ liệu bắt buộc** và **lỗi đọc thật**.
- Bắt lớp con cụ thể khi hữu ích, nhưng giữ đường xử lý `IOException` tổng quát và nguyên nhân gốc.
- Dùng `try-with-resources` để đóng tài nguyên, xem `getSuppressed()` khi có nhiều lỗi.
- Không âm thầm biến thất bại thành kết quả rỗng; không retry ghi mù vì đầu ra có thể đã được ghi một phần.
- Đặt chính sách rõ về ghi đè, append, dữ liệu tạm, hậu điều kiện, độ bền dữ liệu và an toàn khi lỗi.

### Tài liệu Java SE 17

- [IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html)
- [InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html)
- [OutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html)
- [Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [FileSystemException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystemException.html)
- [NoSuchFileException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/NoSuchFileException.html)
- [AccessDeniedException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/AccessDeniedException.html)
- [FileAlreadyExistsException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileAlreadyExistsException.html)
- [Throwable.getSuppressed()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getSuppressed())
- [Java try-with-resources — Oracle Tutorial](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html)
