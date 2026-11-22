# Hành vi trước, sau `close()` và hợp đồng tài nguyên của byte stream (Java 11+)

## 1. Vấn đề cốt lõi: luồng dữ liệu và vòng đời tài nguyên là hai thứ khác nhau

Trong Java, `InputStream` cung cấp các byte để đọc; `OutputStream` nhận byte để ghi. Nhiều stream nắm giữ tài nguyên hữu hạn như file descriptor, socket hoặc bộ đệm. Gọi `close()` là hành động **kết thúc quyền sử dụng tài nguyên theo hợp đồng của stream**, không đơn thuần là báo “đã đọc hết dữ liệu”.

Ví dụ: một tệp đã đọc tới cuối có thể vẫn đang mở; ngược lại, một stream có thể bị đóng trước khi đọc hết. Hai tình huống này khác nhau về trạng thái tài nguyên và kết quả thao tác tiếp theo.

Bốn câu hỏi phải trả lời khi sử dụng stream:

1. **Trước khi `close()`**, `read()`, `write()` và `flush()` được phép làm gì?
2. **Sau khi `close()`**, API cụ thể có cho phép tiếp tục thao tác không, và lỗi nào có thể xảy ra?
3. **Ai sở hữu stream** và chịu trách nhiệm gọi `close()` đúng thời điểm?
4. **Nếu xử lý hoặc đóng stream thất bại**, dữ liệu và ngoại lệ được quản lý ra sao?

Từ Java 11 đến các bản Java hiện hành, `try-with-resources`, `InputStream`, `OutputStream`, `Closeable` và `AutoCloseable` vẫn là các khái niệm trọng tâm. Đặc biệt, Java 11 có hai factory hữu ích để kiểm thử hợp đồng đóng: `InputStream.nullInputStream()` và `OutputStream.nullOutputStream()`.

## 2. Phân biệt OPEN, EOF, CLOSED và lỗi I/O

Hãy xem trạng thái logic sau (không phải state machine chính thức được mọi provider triển khai giống nhau):

~~~text
Đã tạo stream
      |
      v
  OPEN / USABLE --------- read() trả -1 ---------> EOF đã quan sát
      |                                               |
      |  read/write/flush khi hợp đồng cho phép        |  vẫn có thể chưa close
      |                                               |
      +-------------------- close() -------------------+
                               |
                               v
                           CLOSED
                    tài nguyên cần được giải phóng
~~~

**Điểm phân biệt quan trọng:**

- `read()` của `InputStream` trả về **một giá trị từ 0 đến 255**, hoặc **-1** khi đạt kết thúc luồng (EOF). `-1` không phải một byte dữ liệu và **không đồng nghĩa tự động đóng stream**.
- `readAllBytes()` đọc các byte còn lại cho đến EOF, nhưng **không có hợp đồng tự gọi `close()`** trên stream; tài nguyên vẫn do bên sở hữu quản lý.
- `available()` chỉ ước lượng số byte có thể đọc hoặc bỏ qua mà không block; **không phải cách xác định kích thước tệp hoặc kiểm tra chắc chắn đã EOF**.
- `close()` có thể được gọi ngay cả khi chưa đọc đủ dữ liệu hoặc khi còn bộ đệm ghi. Điều đó thường kết thúc khả năng dùng stream và giải phóng tài nguyên liên quan.
- `IOException` khi đang đọc/ghi là lỗi thao tác, **khác** với EOF; kết quả có thể chỉ xử lý một phần dữ liệu. Đừng biến lỗi I/O thành “đã hết dữ liệu” bằng cách trả về `-1` giả.

Các stream mạng, tệp, bộ nhớ, stream đã bọc qua filter hoặc stream do thư viện tạo có hành vi chi tiết khác nhau. Vì vậy không thể viết một quy tắc tuyệt đối kiểu “mọi phương thức đều ném `IOException` sau `close()`”. Phải xem hợp đồng **của lớp stream cụ thể**.

## 3. Hợp đồng từ `AutoCloseable`, `Closeable` đến stream cụ thể

### `AutoCloseable`: giao thức được tự đóng bởi `try-with-resources`

`AutoCloseable` định nghĩa `close() throws Exception`. Khi một resource nằm trong `try (...)`, Java tự gọi `close()` khi thoát khối, **kể cả khi thân `try` ném ngoại lệ**. Bất cứ tài nguyên nào triển khai `AutoCloseable` đều có thể tham gia cơ chế này.

Tuy nhiên, `AutoCloseable` **không bắt buộc `close()` phải idempotent**: gọi nhiều lần có thể có tác dụng phụ. Người viết resource tùy biến được khuyến khích làm `close()` an toàn khi gọi lại nhưng không thể dựa vào lời hứa này cho mọi triển khai.

### `Closeable`: hợp đồng hẹp hơn, phù hợp I/O

`java.io.Closeable` kế thừa `AutoCloseable`, có phương thức `close() throws IOException`. Hợp đồng `Closeable` quy định **nếu stream đã đóng thì gọi `close()` lại không có tác dụng**. Nhưng điều này không phải giấy phép gọi `read()` hoặc `write()` sau khi đóng: khả năng dùng tiếp phụ thuộc chính API.

Các lớp `InputStream` và `OutputStream` triển khai `Closeable`. Bản thân các lớp nền có phương thức `close()` mặc định không làm gì; lớp con nào thực sự giữ tài nguyên phải định nghĩa hành vi cần thiết. Vì vậy:

- Không được suy ra “`close()` không làm gì” chỉ vì biến có kiểu `InputStream`/`OutputStream`.
- Không được suy ra “`close()` luôn làm mọi thao tác sau đó lỗi” chỉ vì biến có kiểu `Closeable`.
- Khi làm việc qua interface, **thiết kế theo vòng đời sử dụng một lần**: hoàn tất công việc, đóng, rồi ngừng dùng biến đó. Ngoại lệ đặc biệt của từng lớp chỉ nên khai thác khi có lý do rõ ràng.

### `close()` có thể ném ngoại lệ

Với stream có tài nguyên thực, `close()` có thể ném `IOException`. Một số thao tác giải phóng có thể đã hoàn tất trước khi ngoại lệ được báo; **không mặc định stream vẫn mở hoặc chưa ghi dữ liệu**. Cần coi kết quả là không chắc chắn theo hợp đồng và xử lý ở ranh giới nghiệp vụ.

Một resource tự viết nên cố gắng giải phóng tài nguyên và đánh dấu đã đóng ngay cả khi `close()` thất bại. Đừng bỏ qua lỗi `close()` có thể chứa thông tin về ghi dữ liệu chưa hoàn tất.

## 4. Hành vi cụ thể trước và sau `close()`

| Lớp/loại stream | Trước `close()` | Sau `close()` | Điều phải nhớ |
| --- | --- | --- | --- |
| `FileInputStream` hoặc input file qua `Files.newInputStream` | Đọc byte từ file, có thể đến EOF | Đọc tiếp thường ném `IOException` | EOF không tự giải phóng file handle |
| `FileOutputStream` hoặc output file qua `Files.newOutputStream` | Ghi byte vào file | Ghi tiếp thường ném `IOException` | Đóng xong không “mở lại” cùng object |
| `BufferedInputStream` | Đọc qua bộ đệm trên stream nguồn | Đọc sau khi đã đóng thường lỗi | Đóng wrapper thường đóng nguồn bên dưới |
| `BufferedOutputStream` | Có thể đang giữ byte chờ ghi xuống stream đích | Không được tiếp tục ghi qua wrapper đã đóng | `close()` kế thừa cơ chế flush + đóng downstream |
| `ByteArrayInputStream` | Đọc từ mảng byte trong bộ nhớ | **Vẫn đọc được**; `close()` không có tác dụng | Ngoại lệ được tài liệu API của lớp này nêu rõ |
| `ByteArrayOutputStream` | Ghi vào bộ đệm byte trong bộ nhớ | **Vẫn ghi/đọc buffer được**; `close()` không có tác dụng | Không dùng ngoại lệ này để suy ra mọi output stream giống nhau |
| `InputStream.nullInputStream()` (Java 11+) | `read()` trả `-1` vì không có dữ liệu | `read()` ném `IOException` | EOF khi còn mở khác với trạng thái đã đóng |
| `OutputStream.nullOutputStream()` (Java 11+) | Nhận và bỏ qua byte | `write(...)` ném `IOException` | Stream discard vẫn có vòng đời rõ ràng |
| Resource từ thư viện/provider | Theo API provider | Theo API provider | Đọc tài liệu và quy ước ownership trước khi sử dụng |

Các câu trong bảng về file và wrapper là **cách sử dụng thực tế cần tuân theo**; những triển khai tùy biến có thể quy định chi tiết khác. Cụm “thường ném” tránh biến một hành vi của các stream tệp tiêu chuẩn thành phát biểu sai cho *mọi* `InputStream`/`OutputStream`.

### Ngoại lệ đặc biệt ở stream bộ nhớ

Theo API chính thức:

~~~java
ByteArrayInputStream in = new ByteArrayInputStream(new byte[] {65});
in.close();
System.out.println(in.read()); // 65: close không ảnh hưởng.

ByteArrayOutputStream out = new ByteArrayOutputStream();
out.close();
out.write(66);
System.out.println(out.toString("UTF-8")); // B
~~~

Đây là **đoạn mã minh họa** (cần import `java.io.*;`, và một phương thức có khai báo/ xử lý `IOException`). Khi dùng các lớp bộ nhớ này, `close()` không có tác dụng; vẫn không nên lạm dụng thao tác sau close nếu code cần dễ thay thế sang stream file/network sau này.

### Hai factory `null...Stream()` của Java 11

~~~java
InputStream empty = InputStream.nullInputStream();
System.out.println(empty.read()); // -1: EOF khi chưa close.
empty.close();
// empty.read() -> IOException.

OutputStream sink = OutputStream.nullOutputStream();
sink.write(65); // Byte bị bỏ đi.
sink.close();
// sink.write(66) -> IOException.
~~~

Đây cũng là **mã minh họa**; các dòng có chú thích lỗi không được gọi nếu chưa có `try/catch` hoặc `throws`. `nullInputStream()` và `nullOutputStream()` vẫn hữu ích trong kiểm thử, khi muốn một nguồn rỗng hoặc một đích nhận rồi bỏ byte, mà không cần file tạm.

## 5. Ví dụ hoàn chỉnh Java 11+: EOF, close, bộ nhớ, null stream và file

Tạo tệp **ByteStreamCloseDemo.java**:

~~~java
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

public class ByteStreamCloseDemo {
    public static void main(String[] args) throws IOException {
        byte[] abc = "ABC".getBytes(StandardCharsets.UTF_8);
        try (InputStream in = new ByteArrayInputStream(abc)) {
            System.out.println("firstByte=" + in.read());
            System.out.println("remaining=" +
                    new String(in.readAllBytes(), StandardCharsets.UTF_8));
            System.out.println("eof=" + in.read());
        }
        ByteArrayInputStream memIn = new ByteArrayInputStream(abc);
        memIn.close();
        System.out.println("memoryInputAfterClose=" + memIn.read());

        ByteArrayOutputStream memOut = new ByteArrayOutputStream();
        memOut.write('A');
        memOut.close();
        memOut.write('B');
        System.out.println("memoryOutputAfterClose=" +
                memOut.toString(StandardCharsets.UTF_8));

        try (InputStream empty = InputStream.nullInputStream()) {
            System.out.println("nullInputEOF=" + empty.read());
        }
        InputStream closedEmpty = InputStream.nullInputStream();
        closedEmpty.close();
        boolean closedNullInputThrows = false;
        try {
            closedEmpty.read();
        } catch (IOException expected) {
            closedNullInputThrows = true;
        }
        System.out.println("closedNullInputThrows=" + closedNullInputThrows);

        OutputStream closedSink = OutputStream.nullOutputStream();
        closedSink.write(65);
        closedSink.close();
        boolean closedNullOutputThrows = false;
        try {
            closedSink.write(66);
        } catch (IOException expected) {
            closedNullOutputThrows = true;
        }
        System.out.println("closedNullOutputThrows=" + closedNullOutputThrows);

        Path temp = Files.createTempFile("byte-stream-close-", ".dat");
        try {
            try (OutputStream out =
                    new BufferedOutputStream(Files.newOutputStream(temp))) {
                out.write(abc);
            }
            try (InputStream fileInput = Files.newInputStream(temp)) {
                System.out.println("fileContents=" +
                        new String(fileInput.readAllBytes(),
                                StandardCharsets.UTF_8));
            }

            InputStream closedFile = Files.newInputStream(temp);
            closedFile.close();
            boolean closedFileThrows = false;
            try {
                closedFile.read();
            } catch (IOException expected) {
                closedFileThrows = true;
            }
            System.out.println("closedFileThrows=" + closedFileThrows);
        } finally {
            Files.deleteIfExists(temp);
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 11 trở lên** (nếu dùng JDK mới, `--release 11` giúp kiểm tra cú pháp và API Java 11):

~~~bash
javac --release 11 ByteStreamCloseDemo.java
java ByteStreamCloseDemo
~~~

Kết quả **stdout chính xác** trên JDK đầy đủ có quyền tạo/xóa tệp tạm:

~~~text
firstByte=65
remaining=BC
eof=-1
memoryInputAfterClose=65
memoryOutputAfterClose=AB
nullInputEOF=-1
closedNullInputThrows=true
closedNullOutputThrows=true
fileContents=ABC
closedFileThrows=true
~~~

**Phân tích từng nhóm kết quả:**

1. `firstByte=65` vì byte đầu của chuỗi UTF-8 `"ABC"` là mã ASCII `A` (65). `readAllBytes()` trả về `BC` còn lại; `read()` tiếp theo trả `-1`. Dù đã EOF, `try-with-resources` vẫn gọi `close()` khi ra khỏi khối.
2. `memoryInputAfterClose=65` và `memoryOutputAfterClose=AB` là hành vi **được đặc tả riêng** cho `ByteArrayInputStream`/`ByteArrayOutputStream`: `close()` không có tác dụng trên các lớp này.
3. `nullInputEOF=-1` xảy ra khi `nullInputStream` **vẫn mở**. Sau khi đóng, `read()` ném `IOException` nên biến `closedNullInputThrows` là `true`.
4. `nullOutputStream` bỏ qua byte trước khi đóng nhưng ném `IOException` khi được yêu cầu `write(66)` sau khi đóng; do đó `closedNullOutputThrows=true`.
5. `Files.createTempFile` tạo tệp riêng cho lần chạy; `BufferedOutputStream` nhận ba byte `ABC` và **`close()` của wrapper** làm chúng được chuyển đến tệp rồi đóng stream bên dưới theo hợp đồng filter. Phần đọc file sau đó in `fileContents=ABC`.
6. Stream tệp từ `Files.newInputStream(temp)` sau `close()` từ chối đọc; `closedFileThrows=true`. Khối `finally` chỉ dọn tệp tạm mà ví dụ đã tạo. Nếu một thao tác I/O lỗi trước đó, chương trình vẫn phải xử lý/đưa ra ngoại lệ.

Ví dụ chạy độc lập, không cần thư viện ngoài JDK và chỉ tạo tệp trong thư mục tạm của môi trường. Kết quả đã được đối chiếu thực thi trên JDK hiện đại bằng `javac --release 11`.

## 6. `flush()` khác `close()` như thế nào?

Trên một `OutputStream` có bộ đệm:

- `write(bytes)` có thể mới đưa dữ liệu vào **bộ đệm trong Java**, chưa chuyển toàn bộ xuống stream đích.
- `flush()` yêu cầu chuyển dữ liệu còn đệm đến đích theo hợp đồng của output stream; **không đóng stream**.
- `close()` kết thúc việc sử dụng stream, giải phóng tài nguyên; các wrapper như `FilterOutputStream` thực hiện `flush` rồi gọi `close()` của stream bên dưới.
- **`flush()` và `close()` không đồng nghĩa “dữ liệu đã chắc chắn nằm an toàn trên thiết bị lưu trữ vật lý”**. Với file, `flush()` có thể mới chuyển dữ liệu tới hệ điều hành; độ bền lưu trữ cần cơ chế riêng, chẳng hạn `FileChannel.force(...)` và thiết kế an toàn khi xảy ra sự cố.

Ví dụ mô tả thứ tự mong muốn:

~~~java
try (OutputStream out =
        new BufferedOutputStream(Files.newOutputStream(path))) {
    out.write(payload);
    out.flush(); // Khi cần cho bên nhận nhìn thấy dữ liệu trước khi đóng.
    // Có thể write(...) tiếp trong khối này.
} // Gọi close() tự động; không dùng 'out' sau khi ra khỏi khối.
~~~

Đây là **đoạn minh họa**, không phải chương trình độc lập (`path`/`payload` do caller cung cấp). Trong nhiều trường hợp chỉ cần ghi xong rồi đóng; không nhất thiết gọi `flush()` thủ công trước `close()` của `BufferedOutputStream`.

**Không suy diễn** rằng mọi `OutputStream` đều buộc phải flush dữ liệu theo cùng cách: `OutputStream.flush()` của lớp nền mặc định không làm gì; mỗi lớp con/wrapper quyết định hành vi cụ thể. Ngay cả khi đã gọi `flush()`, vẫn cần `close()` để giải phóng resource.

## 7. Quy tắc ownership: ai mở stream thì ai chịu trách nhiệm đóng?

Không có quy tắc máy móc “hàm nào gọi `read()` thì hàm đó phải `close()`”. **Hợp đồng sở hữu (ownership contract)** quyết định việc đóng:

| Tình huống | Ai nên đóng? | Vì sao |
| --- | --- | --- |
| Phương thức tự gọi `Files.newInputStream(path)` | Chính phương thức, bằng `try-with-resources` | Phương thức đã tạo resource và quyết định vòng đời |
| Phương thức nhận `InputStream` của caller để đọc | Thường caller, **nếu hợp đồng API không chuyển ownership** | Đóng trong hàm có thể phá luồng xử lý của caller |
| Phương thức nhận `OutputStream` để ghi dữ liệu | Thường caller; có thể `flush()` nếu hợp đồng yêu cầu | Caller có thể cần ghi thêm dữ liệu khác |
| Phương thức bọc stream được nó sở hữu bằng `BufferedOutputStream` | Đóng wrapper ngoài cùng | Wrapper thường đóng stream bên trong |
| Framework cung cấp response/body stream | Theo hợp đồng framework | Tự đóng sớm có thể cắt response |
| `System.in`, `System.out` được chia sẻ | Thông thường **không đóng từ tiện ích dùng nhờ** | Có thể làm mất I/O cho phần còn lại của ứng dụng |
| `ByteArrayOutputStream` do chính hàm tạo | Có thể không cần close vì không sở hữu OS handle | Lớp này định nghĩa close không có tác dụng |

### Trường hợp caller cho mượn stream

Ví dụ một hàm chỉ **mượn** `InputStream` và `OutputStream` để sao chép:

~~~java
static long copyBorrowed(InputStream src, OutputStream dst)
        throws IOException {
    // Không đóng src/dst: caller vẫn sở hữu cả hai.
    return src.transferTo(dst);
}
~~~

`InputStream.transferTo(OutputStream)` (có từ Java 9, dùng tốt trong Java 11+) đọc và chuyển byte sang đích; **không tự đóng cả input lẫn output**. Nó có thể block, có thể hoàn tất một phần rồi ném `IOException`. Caller phải đóng hai resource theo chính sách của mình.

Một cách dùng có ownership rõ ràng:

~~~java
try (InputStream src = Files.newInputStream(sourcePath);
     OutputStream dst = Files.newOutputStream(targetPath)) {
    copyBorrowed(src, dst);
}
~~~

Hai đoạn trên là **mã minh họa không độc lập**; `sourcePath` và `targetPath` cần được tạo/cấu hình, và việc ghi tệp đích phải xem xét chính sách overwrite. Khi cả hai stream được khai báo trong `try-with-resources`, Java đóng **`dst` rồi `src`** theo thứ tự ngược lúc khai báo.

### Đóng wrapper và stream bên dưới

Với `BufferedOutputStream`, `DataOutputStream` hoặc nhiều filter stream, đóng wrapper thường **lan truyền `close()`** xuống stream được bọc. Vì thế, mẫu thường dùng là **đóng wrapper ngoài cùng**, tránh đóng nguồn trước khi wrapper kịp flush.

~~~java
try (OutputStream out =
        new BufferedOutputStream(Files.newOutputStream(path))) {
    out.write(data);
}
~~~

Nếu stream dưới là tài nguyên dùng chung hoặc **caller chỉ cho mượn**, không được tùy tiện bọc rồi đóng một wrapper có thể đóng luôn stream gốc. Hãy quy định rõ: “hàm này **sở hữu và đóng** stream” hoặc “hàm này **chỉ mượn, không đóng** stream”, rồi chọn thiết kế wrapper phù hợp. Không chỉ dựa vào tên lớp wrapper; phải đọc hợp đồng `close()` của nó.

## 8. `try-with-resources`: đóng đúng thời điểm, đúng thứ tự

Với stream do phương thức mở, mẫu phổ biến và an toàn là:

~~~java
try (InputStream in = Files.newInputStream(path)) {
    byte[] data = in.readAllBytes();
    // Xử lý data.
} // Dù khối try thành công hay ném lỗi, close() vẫn được gọi.
~~~

Đây là **mã minh họa**, cần có `path` và xử lý `IOException`; với file quá lớn không nên dùng `readAllBytes()` để nạp toàn bộ vào bộ nhớ. Ưu điểm của `try-with-resources`:

1. Resource được đóng **khi rời scope**, kể cả khi có `return` hoặc exception.
2. Nhiều resource được đóng theo **thứ tự ngược** với thứ tự khai báo.
3. Ngoại lệ từ thân `try` được giữ làm **ngoại lệ chính**, và ngoại lệ từ `close()` trở thành **suppressed exception**, tránh làm mất nguyên nhân gốc.
4. Nếu thân `try` hoàn tất bình thường nhưng `close()` ném lỗi, lỗi đóng **không bị bỏ qua**: nó thoát ra ngoài theo cơ chế của Java.

Lưu ý: `try-with-resources` đảm bảo Java **gọi** `close()`, không thể bảo đảm mọi phần cứng/network/provider sẽ đóng thành công hay ghi dữ liệu đầy đủ. Cần quan sát ngoại lệ và phục hồi theo nghiệp vụ.

### Ví dụ thứ hai: ngoại lệ chính và thứ tự đóng

Tạo tệp **ResourceContractDemo.java**:

~~~java
import java.io.IOException;

public class ResourceContractDemo {
    static class FailingClose implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }
    public static void main(String[] args) throws Exception {
        try (FailingClose resource = new FailingClose()) {
            throw new IllegalStateException("work failed");
        } catch (IllegalStateException e) {
            System.out.println("primary=" + e.getMessage());
            System.out.println("suppressed=" + e.getSuppressed().length);
            System.out.println("suppressedMessage=" +
                    e.getSuppressed()[0].getMessage());
        }

        try (AutoCloseable first = () -> System.out.println("close first");
             AutoCloseable second = () -> System.out.println("close second")) {
            System.out.println("body");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 11 ResourceContractDemo.java
java ResourceContractDemo
~~~

**stdout chính xác:**

~~~text
primary=work failed
suppressed=1
suppressedMessage=close failed
body
close second
close first
~~~

Trong phần đầu, `IllegalStateException("work failed")` từ thân khối là ngoại lệ chính; `IOException("close failed")` từ tài nguyên được giữ trong `e.getSuppressed()`. Phần sau chứng minh Java đóng `second` trước `first`.

**Giới hạn của ví dụ:** `FailingClose` chỉ dùng để mô phỏng lỗi đóng; nó không quản lý tài nguyên hệ điều hành thực tế. Với một resource tự viết trong ứng dụng, nên giải phóng tài nguyên và cập nhật trạng thái nội bộ ngay cả khi xảy ra lỗi lúc đóng, theo hướng dẫn của `AutoCloseable`.

## 9. Xử lý lỗi, đóng sớm và dùng lại object

### Đọc/ghi thất bại giữa chừng

Một hoạt động đọc hoặc ghi byte có thể xử lý **một phần** rồi báo `IOException`. Ví dụ `transferTo` có thể đã sao chép một phần dữ liệu sang đích; `write` có thể đã ghi một phần nội dung. Không cho rằng dữ liệu đích chưa hề thay đổi. Khi cần ghi tệp theo giao dịch, hãy thiết kế lưu tạm, kiểm chứng, thay thế theo cơ chế phù hợp của hệ thống tệp và xử lý cleanup; `close()` không tự biến thao tác ghi thành transaction.

Mẫu bắt lỗi:

~~~java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(destination)) {
    in.transferTo(out);
} catch (IOException e) {
    // Ghi log có kiểm soát, báo lỗi cho caller, xử lý dữ liệu đích có thể dở dang.
    throw e;
}
~~~

Đoạn này là **mã minh họa**, cần `source` và `destination`. Lỗi phát sinh trong thân hoặc khi đóng đều có thể đi ra `catch`. Khi điều tra sự cố, xem `getSuppressed()` nếu có; không chỉ đọc duy nhất thông báo của ngoại lệ chính.

### Không đóng stream đang được luồng khác sử dụng

Khi một thread đóng stream trong lúc thread khác đang `read()` hoặc `write()`, hành vi giữa các triển khai có thể khác nhau: thao tác đang chạy có thể thất bại hoặc kết thúc theo cơ chế provider. Không viết thuật toán phụ thuộc vào một hành vi không được hợp đồng bảo đảm. Nếu chia sẻ stream, cần quản lý ownership, đồng bộ hóa và thời điểm hủy I/O rõ ràng.

### Không mở lại một stream đã đóng

Với resource tệp/socket tiêu chuẩn, object đã đóng không có cơ chế `reopen()` chung. Nếu cần đọc tệp lại từ đầu, **mở một stream mới** bằng `Files.newInputStream(path)` hoặc API phù hợp. Với `ByteArrayInputStream`, `reset()` có thể di chuyển vị trí đọc theo hợp đồng riêng của nó, nhưng đó **không phải** cơ chế mở lại một file stream đã đóng.

### Có cần gọi `close()` hai lần?

Với `Closeable`, gọi lại `close()` khi đã đóng không có tác dụng theo hợp đồng. Tuy nhiên, đừng viết mã phụ thuộc vào việc nhiều thành phần cùng tự đóng một resource; điều đó làm mờ ownership và che giấu lỗi thiết kế. Với tài nguyên chỉ triển khai `AutoCloseable` mà không phải `Closeable`, idempotence **không bắt buộc**. Mẫu mặc định nên là **một nơi sở hữu, một scope đóng**.

## 10. Những ngộ nhận dễ gặp

| Ngộ nhận | Sự thật cần nhớ |
| --- | --- |
| “`read() == -1` nghĩa là stream đã close.” | EOF là hết dữ liệu đọc; vẫn cần `close()` nếu resource yêu cầu |
| “`readAllBytes()` tự đóng stream.” | Nó đọc các byte còn lại, không tự nhận quyền đóng stream |
| “Mọi stream sau close đều ném `IOException`.” | Sai với `ByteArrayInputStream`/`ByteArrayOutputStream` |
| “Vì `ByteArrayOutputStream` vẫn ghi sau close, `FileOutputStream` cũng thế.” | Không; hành vi phụ thuộc lớp cụ thể và tài nguyên thực |
| “`flush()` là đủ để giải phóng file handle.” | Không; flush không thay thế close |
| “Đóng là bảo đảm dữ liệu đã xuống ổ đĩa vật lý.” | Không; còn phụ thuộc provider, OS và yêu cầu độ bền |
| “Hàm nào được truyền stream cũng nên đóng luôn.” | Sai với borrowed stream; cần quy định ownership |
| “Đóng wrapper không ảnh hưởng stream gốc.” | Nhiều filter/wrapper đóng luôn delegate bên dưới |
| “`try-with-resources` làm mất ngoại lệ trong thân nếu close lỗi.” | Ngoại lệ thân thường giữ vai trò chính; close lỗi được suppressed |
| “`AutoCloseable` bảo đảm close lặp lại vô hại.” | `AutoCloseable` không bắt buộc idempotent; `Closeable` có yêu cầu khác |
| “`available() == 0` nghĩa là EOF và có thể close.” | `available` chỉ là ước lượng byte đọc không block; không xác nhận EOF |
| “`transferTo` tự đóng cả hai luồng.” | `InputStream.transferTo` không tự đóng input hoặc output |
| “Không thấy ngoại lệ là dữ liệu đã được ghi nguyên vẹn.” | Có thể cần xác thực nội dung và kiểm soát tình huống ghi một phần |

## 11. Checklist khi review code thao tác byte stream

Khi đọc một đoạn Java dùng `InputStream` hoặc `OutputStream`, kiểm tra lần lượt:

1. **Nguồn stream ở đâu?** Do hàm tự mở, caller truyền vào, hay framework sở hữu?
2. **Hợp đồng đóng là gì?** Hàm nhận ownership hay chỉ mượn? Nếu có wrapper, wrapper có đóng delegate không?
3. **Đã dùng `try-with-resources` cho resource mình sở hữu chưa?** Scope có đủ nhỏ và không có escape ngoài ý muốn không?
4. **Có nhầm EOF với close không?** `-1` là dấu hiệu dữ liệu đọc kết thúc, không phải chứng minh tài nguyên đã giải phóng.
5. **Sau close có còn code đọc/ghi không?** Nếu có, đó là lỗi vòng đời trừ khi API lớp cụ thể nói rõ khác và ta cố ý sử dụng.
6. **Nếu output có buffer, có thời điểm flush hợp lý không?** Có cần hiển thị dữ liệu trước khi đóng không? Đừng nhầm flush với durability.
7. **Đã xét lỗi trong cả thân xử lý và lúc close chưa?** Xem cả suppressed exceptions khi cần.
8. **Đã xét dữ liệu dở dang chưa?** Nếu copy/write thất bại, liệu cần hủy, xóa phần tạm hoặc báo trạng thái không?
9. **Có dùng API tải toàn bộ dữ liệu vào RAM không?** `readAllBytes()` chỉ phù hợp khi kích thước có giới hạn/chấp nhận được.
10. **Có giữ nguyên stream dùng chung không?** Tránh đóng `System.in`, `System.out` hoặc stream do caller/framework quản lý nếu chưa được giao quyền.
11. **Có dựa vào đặc tính riêng của ByteArray/null stream ở nơi cần thay implementation không?** Hãy viết code theo hợp đồng chung khi mục tiêu là thay thế implementation.
12. **Có kiểm thử đường đi lỗi?** Test EOF, gọi sau close, close lỗi, thứ tự đóng, và behavior khi stream chỉ đọc/ghi được một phần.

**Ghi nhớ:** `EOF` cho biết trạng thái **dữ liệu**, còn `close()` quyết định vòng đời **tài nguyên**. `try-with-resources` giúp đóng đúng scope, nhưng cần làm rõ **ownership**; còn hành vi đọc/ghi sau close phải dựa vào **lớp stream cụ thể**, vì có những trường hợp được phép tiếp tục thao tác như `ByteArrayInputStream` và `ByteArrayOutputStream`.

## Tài liệu chuẩn còn áp dụng

- [Oracle Java SE 25 — `InputStream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/InputStream.html): `read()`, `readAllBytes()`, `transferTo()`, `nullInputStream()` và `close()`.
- [Oracle Java SE 25 — `OutputStream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/OutputStream.html): `write`, `flush`, `close`, `nullOutputStream()`.
- [Oracle Java SE 25 — `Closeable`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Closeable.html): hợp đồng đóng lặp lại và `IOException`.
- [Oracle Java SE 25 — `AutoCloseable`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/AutoCloseable.html): dùng trong `try-with-resources`, idempotence và lỗi close.
- [Oracle Java SE 25 — `ByteArrayInputStream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/ByteArrayInputStream.html): `close()` không có tác dụng.
- [Oracle Java SE 25 — `ByteArrayOutputStream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/ByteArrayOutputStream.html): vẫn dùng được sau `close()`.
- [Oracle Java SE 25 — `FilterOutputStream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/FilterOutputStream.html): `flush` và đóng stream bên dưới.
- [Oracle Java Tutorials — The try-with-resources Statement](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html): cơ chế đóng theo scope và suppressed exceptions.

Bài học chỉ sử dụng những khái niệm, hợp đồng và API hiện vẫn được hỗ trợ trong Java 11+; các hành vi khác biệt sau `close()` được nêu theo tài liệu lớp cụ thể để tránh suy luận từ kỹ thuật cũ hoặc một implementation riêng.