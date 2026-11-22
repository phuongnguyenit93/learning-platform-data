# Luồng dữ liệu, tài nguyên hệ điều hành và vòng đời sử dụng trong Java I/O

## 1. Bức tranh tổng thể: đọc và ghi dữ liệu là một quá trình có tài nguyên

I/O (Input/Output) là cách chương trình trao đổi dữ liệu với bên ngoài: tệp, bàn phím, màn hình, kết nối mạng, bộ nhớ hoặc một nguồn/đích khác. **Input** là dữ liệu đi vào chương trình; **output** là dữ liệu đi ra chương trình. Một thao tác I/O có thể đọc hoặc ghi từng phần, bị chặn trong lúc chờ dữ liệu, hoặc thất bại vì nguyên nhân ngoài chương trình.

Hình dung một lần sao chép tệp:

~~~text
Tệp nguồn trên đĩa
      │   hệ điều hành cho phép mở tệp
      ▼
InputStream  ── đọc từng khối byte ──► byte[] buffer
                                            │
                                            ▼
                                     OutputStream
                                            │
                                            ▼
                                     Tệp đích trên đĩa
~~~

Trong sơ đồ có ba đối tượng cần phân biệt:

1. **Nguồn/đích dữ liệu**: tệp, socket, thiết bị, mảng byte... Đây là nơi dữ liệu đến hoặc đi.
2. **Đối tượng I/O của Java**: chẳng hạn `InputStream`, `OutputStream`, `Reader`, `Writer`; chúng cung cấp phương thức đọc/ghi và quản lý một phần trạng thái.
3. **Tài nguyên ở hệ điều hành**: chẳng hạn file descriptor hoặc handle liên quan đến tệp/socket. Không phải mọi luồng Java đều sử dụng tài nguyên hệ điều hành.

Hai từ “luồng” trong bài cần hiểu đúng ngữ cảnh: **stream I/O** là dòng dữ liệu được đọc/ghi theo thứ tự; nó **không phải thread** (luồng thực thi). Đối tượng stream là một cách truy cập dữ liệu, còn thread là đơn vị thực hiện lệnh.

**Mục tiêu thực hành:** biết ai mở tài nguyên, ai chịu trách nhiệm đóng, đọc/ghi đến đâu là hoàn tất, và điều gì xảy ra nếu thao tác lỗi giữa chừng.

## 2. Stream, Reader/Writer và lớp bao (wrapper)

### 2.1. Byte và ký tự không giống nhau

- `InputStream` và `OutputStream` xử lý **byte**. Phù hợp với dữ liệu nhị phân và sao chép nội dung nguyên trạng, ví dụ ảnh, ZIP, PDF.
- `Reader` và `Writer` xử lý **ký tự** (Java `char` / văn bản đã giải mã). Phù hợp với dữ liệu văn bản nhưng cần chọn bảng mã (charset) đúng lúc chuyển giữa byte và ký tự.
- `InputStreamReader` chuyển byte thành ký tự qua một `Charset`; `OutputStreamWriter` chuyển ký tự thành byte.
- Các API tiện ích như `Files.readString`, `Files.newBufferedReader` và `Files.writeString` cũng cần được dùng với charset rõ ràng khi tính nhất quán quan trọng; UTF-8 là lựa chọn phổ biến.

Ví dụ chuỗi `"á"` có một đơn vị UTF-16 (`String.length() == 1`) nhưng khi mã hóa UTF-8 cần hai byte. Bởi vậy **số ký tự không bằng số byte**. Sao chép tệp nhị phân qua `Reader/Writer` có thể làm thay đổi dữ liệu do quá trình giải mã và mã hóa.

### 2.2. Lớp nền và lớp bao có trách nhiệm khác nhau

~~~text
Ứng dụng
   │
BufferedInputStream      ← gom nhiều lần đọc nhỏ vào bộ đệm
   │
FileInputStream          ← đọc byte từ tệp, thường giữ handle/descriptor
   │
Hệ điều hành / hệ thống tệp
~~~

`BufferedInputStream` chủ yếu bổ sung bộ đệm; `FileInputStream` thực hiện đọc từ tệp. Hai đối tượng có thể dùng chung **một** tài nguyên tệp bên dưới, vì vậy “có hai object” không có nghĩa “đã mở hai tệp”. Khi đóng lớp bao ngoài cùng do mình sở hữu, thao tác đóng thông thường được truyền xuống luồng bên dưới.

Các stream trong bộ nhớ như `ByteArrayInputStream` và `ByteArrayOutputStream` không giữ file descriptor; đóng `ByteArrayOutputStream` không làm nó mất dữ liệu đã tích lũy. Ngược lại, luồng từ `Files.newInputStream(path)` thường liên quan đến tài nguyên tệp cần giải phóng. Không đánh đồng mọi `close()` với một lần gọi hệ điều hành giống nhau.

### 2.3. Bộ đệm và từng phần dữ liệu

`read()` một byte có thể gây nhiều lần gọi I/O hơn đọc một mảng byte; trong thực tế thường dùng bộ đệm, ví dụ `byte[8192]`. Đọc không bắt buộc lấp đầy cả mảng: một lần `read(buffer)` có thể trả về số byte nhỏ hơn `buffer.length`. Khi đọc đến hết luồng, kết quả là `-1`; không được lấy `-1` làm số byte hợp lệ để ghi.

Với độ dài mảng lớn hơn 0, dạng vòng lặp thường dùng là:

~~~java
byte[] buffer = new byte[8192];
int count;
while ((count = in.read(buffer)) != -1) {
    out.write(buffer, 0, count);
}
~~~

Đây là **đoạn mã minh họa**, trong đó `in` và `out` đã được tạo và sẽ được đóng bởi phần bao ngoài. Chỉ ghi đúng `count` byte nhận được. Viết `out.write(buffer)` sẽ có nguy cơ ghi thêm các byte cũ ở phần cuối mảng khi lần đọc cuối trả về ít dữ liệu.

## 3. Hệ điều hành tham gia I/O như thế nào?

Khi một chương trình mở tệp hoặc socket thông qua Java, JVM và thư viện nền tảng thường phối hợp với hệ điều hành để tạo một định danh cho tài nguyên đang mở: **file descriptor** ở các hệ Unix hoặc **handle** ở Windows. Chi tiết ánh xạ phụ thuộc hệ điều hành và loại API; không có quy tắc “một Java object luôn bằng một file descriptor”.

Trong lúc tài nguyên còn mở, hệ điều hành có thể duy trì vị trí đọc/ghi, quyền truy cập, bộ đệm, trạng thái kết nối hoặc khóa liên quan. Đóng tài nguyên làm kết thúc quyền sử dụng của đối tượng đó và yêu cầu giải phóng tài nguyên bên dưới theo hợp đồng API. Việc dữ liệu đã được ghi đến đâu trên thiết bị lưu trữ vật lý là câu chuyện khác (xem mục 8).

Ví dụ hậu quả khi quên đóng liên tục:

- Tiến trình giữ quá nhiều descriptor/handle dẫn đến lỗi kiểu “too many open files” hoặc không mở thêm tệp/socket được.
- Tệp có thể chưa được giải phóng để đổi tên/xóa trên một số hệ điều hành hoặc khi còn khóa, ánh xạ bộ nhớ.
- Dữ liệu vẫn nằm trong bộ đệm chưa được đẩy xuống luồng bên dưới.
- Kết nối mạng tồn tại lâu hơn dự kiến, giữ bộ nhớ và tài nguyên của cả hai đầu.

**Garbage Collector (GC) quản lý bộ nhớ đối tượng Java, không phải cơ chế bảo đảm đóng tài nguyên I/O đúng thời điểm.** Một object không còn được tham chiếu có thể được thu gom sau đó, hoặc rất lâu sau đó. Dù một thư viện có biện pháp dọn dẹp dự phòng, không được dựa vào GC để thay `close()`.

Cần nhớ ba lớp khác nhau:

| Lớp | Ví dụ | Điều phải kiểm soát |
| --- | --- | --- |
| Dữ liệu | byte, ký tự, bản ghi, thông điệp | Đọc/ghi đúng số lượng, đúng charset và thứ tự |
| Đối tượng Java | `InputStream`, `BufferedReader`, `FileChannel` | Trạng thái đang mở, bộ đệm, lỗi, `close()` |
| Tài nguyên bên ngoài | descriptor/handle tệp, socket, khóa | Mở có giới hạn, giải phóng kịp thời, hạn chế tranh chấp |

## 4. Vòng đời tài nguyên: mở → dùng → kết thúc

Một đường đi điển hình:

~~~text
Chưa mở
   │ open/newInputStream/newOutputStream
   ▼
Đang mở
   ├── read/write/flush thành công ──► tiếp tục sử dụng
   ├── hết dữ liệu đầu vào (EOF) ────► vẫn có thể cần close
   └── IOException ─────────────────► vẫn phải close
   │
   ▼
close() / try-with-resources
   │
   ▼
Đã đóng: không tiếp tục I/O trên đối tượng có tài nguyên
~~~

**EOF không đồng nghĩa với đóng tệp.** `read() == -1` chỉ cho biết đã hết dữ liệu của đầu vào theo giao ước đọc; descriptor/handle vẫn cần giải phóng. Tương tự, ghi đủ các byte dự kiến không tự bảo đảm `close()` đã chạy.

Một số điểm dễ bỏ sót:

- **Mở cũng có thể thất bại**: tệp không tồn tại, thiếu quyền, đường dẫn sai, quá nhiều tệp đang mở.
- **Đọc hoặc ghi có thể thất bại giữa chừng**: thiết bị đầy, kết nối bị cắt, quyền truy cập thay đổi. Đích có thể đã nhận một phần dữ liệu.
- **`flush()` và `close()` có thể ném `IOException`**. Đường xử lý lỗi phải tính đến cả lỗi dọn dẹp.
- **Không phải một lần `write` tương đương một giao dịch**. Nếu quá trình sao chép thất bại, tệp đích có thể chứa dữ liệu chưa hoàn chỉnh; nếu cần thay thế tệp an toàn phải thiết kế quy trình ghi tạm và đổi tên phù hợp hệ thống tệp.
- **Đóng nhiều lần**: một số lớp có hành vi dung thứ, nhưng không được giả định mọi triển khai `AutoCloseable` đều bảo đảm `close()` idempotent. Hãy thiết kế mỗi tài nguyên có một chủ sở hữu chịu trách nhiệm đóng.

Trong mô hình luồng, thao tác đọc/ghi còn có thể **chặn** để chờ dữ liệu hoặc thiết bị. Chẳng hạn socket đang mở nhưng phía kia chưa gửi thêm byte; việc chờ không nói lên rằng dữ liệu đã hết. Đặc biệt với mạng, cần xem xét timeout, hủy thao tác và quy tắc đóng riêng của API đó.

## 5. Đóng đúng bằng try-with-resources

`try-with-resources` (có từ Java 7) là cách chuẩn để quản lý đối tượng triển khai `AutoCloseable`, bao gồm nhiều loại trong `java.io`, `java.nio.channels` và các stream I/O khác.

~~~java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(target)) {
    // Đọc và ghi.
} // out.close() chạy trước, rồi in.close(), kể cả khi thân try phát sinh lỗi.
~~~

Đây là đoạn minh họa; các biến `source` và `target` phải là `Path` hợp lệ, và lớp chứa đoạn mã phải xử lý/khai báo `IOException`. Tài nguyên được đóng **theo thứ tự ngược với thứ tự khai báo**. Nếu một bước đóng xảy ra lỗi, Java vẫn cố gắng đóng các tài nguyên còn lại.

Lợi ích so với tự viết `try/finally` là quản lý chính xác ngoại lệ. Nếu thân `try` ném một ngoại lệ và `close()` cũng ném ngoại lệ, ngoại lệ từ thân `try` là ngoại lệ chính; lỗi khi đóng được gắn vào đó dưới dạng **suppressed exception** (truy xuất qua `Throwable.getSuppressed()`). Đừng thay thế nó bằng ngoại lệ dọn dẹp rồi mất nguyên nhân ban đầu.

Ví dụ độc lập minh họa thứ tự đóng:

~~~java
public class CloseOrderDemo {
    static final class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        try (Resource first = new Resource("first");
             Resource second = new Resource("second")) {
            System.out.println("work");
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 CloseOrderDemo.java
java CloseOrderDemo
~~~

Kết quả chính xác:

~~~text
work
close second
close first
~~~

`Closeable` mở rộng `AutoCloseable` và quy định `close()` ném tối đa `IOException`; `AutoCloseable.close()` có thể khai báo `Exception`. Hợp đồng chính xác của mỗi lớp vẫn cần được tôn trọng. Không viết `catch (Exception ignored)` chỉ để giấu lỗi đóng, vì có thể mất tín hiệu rằng dữ liệu chưa được đẩy ra ngoài thành công.

## 6. Ví dụ đầy đủ: sao chép tệp và giải phóng tài nguyên

Ví dụ Java 17+ sau tự tạo tệp đầu vào tạm, đọc từng khối byte, ghi sang tệp đích, tự đóng hai luồng và xóa tệp tạm. Dữ liệu thử là ASCII để số byte dễ kiểm tra. Tên tệp Java phải là **IoLifecycleDemo.java**.

~~~java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class IoLifecycleDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("java-io-");
        Path source = directory.resolve("source.txt");
        Path target = directory.resolve("target.txt");

        try {
            Files.writeString(source, "Java I/O\n", StandardCharsets.UTF_8);
            long total = 0;

            try (InputStream in = new BufferedInputStream(
                         Files.newInputStream(source));
                 OutputStream out = new BufferedOutputStream(
                         Files.newOutputStream(target))) {

                byte[] buffer = new byte[8192];
                int count;

                while ((count = in.read(buffer)) != -1) {
                    out.write(buffer, 0, count);
                    total += count;
                }
            }

            System.out.println("Bytes copied: " + total);
            System.out.println("Content: " +
                    Files.readString(target, StandardCharsets.UTF_8).strip());
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Biên dịch và chạy ở thư mục chứa tệp nguồn:

~~~bash
javac -encoding UTF-8 IoLifecycleDemo.java
java IoLifecycleDemo
~~~

Kết quả:

~~~text
Bytes copied: 9
Content: Java I/O
~~~

Giải thích từng quyết định:

1. `Files.createTempDirectory` tạo thư mục thử nghiệm riêng; `source` và `target` là đường dẫn tệp chứ chưa phải stream đang mở.
2. `Files.writeString` thực hiện trọn một thao tác ghi tiện ích và tự quản lý tài nguyên nội bộ. Chuỗi `"Java I/O\n"` gồm 9 byte UTF-8.
3. `Files.newInputStream` và `Files.newOutputStream` mở các tài nguyên cần được đóng. `BufferedInputStream/BufferedOutputStream` bọc chúng để hạn chế các thao tác I/O nhỏ.
4. Thân `try-with-resources` sao chép đúng số byte mỗi lượt. `total` chỉ tăng sau khi `write` trả về bình thường.
5. Rời khối `try` đóng `out` rồi `in`, kể cả khi `read` hoặc `write` có lỗi. `BufferedOutputStream.close()` đẩy phần dữ liệu đang đệm xuống luồng bên dưới trước khi đóng.
6. Chỉ sau khi khối đóng thành công mới đọc lại tệp đích. Khối `finally` cố gắng xóa các tệp và thư mục thử nghiệm.

Ví dụ ưu tiên sự rõ ràng. Trong phần mềm thực tế, nếu thao tác chính lỗi và việc xóa tệp tạm cũng lỗi, ngoại lệ từ `finally` có thể che lỗi gốc; khi cần giữ cả hai nguyên nhân, hãy thiết kế riêng bước dọn tệp tạm và gắn ngoại lệ dọn dẹp dưới dạng suppressed exception. Đồng thời phải quyết định sẽ giữ lại tệp đích chưa hoàn chỉnh để điều tra hay xóa đi.

Nếu chỉ muốn sao chép tệp thông thường, Java có API tiện ích `Files.copy(source, target, ...)`; ví dụ thủ công ở đây để nhìn thấy vòng đời của **luồng dữ liệu** và **tài nguyên**.

## 7. Văn bản: đưa charset vào đúng ranh giới byte/ký tự

Tệp và socket truyền **byte**; người dùng đọc **chữ**. Bộ giải mã chuyển byte thành ký tự theo charset. Khi charset không khớp, chữ có dấu có thể thành ký tự lỗi; nếu dùng charset mặc định tùy môi trường, kết quả giữa các máy có thể khác nhau.

Đọc văn bản có thể dùng:

~~~java
try (var reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý một dòng; readLine() đã bỏ dấu kết thúc dòng.
    }
}
~~~

Đây là đoạn minh họa trong ngữ cảnh có `Path path` và xử lý `IOException`. `readLine()` trả về `null` tại EOF; khi gặp EOF vẫn cần đóng `reader`. Nếu phải bảo toàn byte gốc, kiểu xuống dòng hoặc mã hóa đầu vào, đừng dùng cách đọc dòng rồi ghi lại theo charset như một phương pháp “sao chép nguyên vẹn”.

`Files.readString(path, UTF_8)` tiện cho tệp văn bản nhỏ, nhưng tải toàn bộ nội dung vào bộ nhớ; với tệp lớn, hãy đọc tuần tự hoặc xử lý theo khối/dòng. Với đầu ra, `Files.newBufferedWriter(path, UTF_8)` cho phép ghi văn bản theo kiểu tuần tự.

Ngoài `Reader/Writer`, các nguồn lười như `Files.lines(path, UTF_8)` và `Files.walk(path)` trả về `Stream` có tài nguyên I/O cần đóng; đặt chúng trong `try-with-resources`. Không suy diễn rằng mọi `java.util.stream.Stream` đều giữ tài nguyên ngoài: stream từ một danh sách trong bộ nhớ thường không cần đóng.

## 8. Flush, close và độ bền dữ liệu là ba việc khác nhau

**`flush()`** yêu cầu bộ đệm của đối tượng ghi đẩy những gì đang giữ xuống đích kế tiếp theo hợp đồng API. Chẳng hạn `BufferedOutputStream.flush()` chuyển dữ liệu còn đệm xuống `OutputStream` bên dưới. Nó không tự cam kết dữ liệu đã nằm bền vững trên ổ đĩa vật lý.

**`close()`** kết thúc việc sử dụng tài nguyên; nhiều output stream sẽ flush trong quá trình đóng rồi giải phóng luồng bên dưới. Sau khi đóng, không tiếp tục ghi lên stream đó. Close thành công vẫn không phải cam kết tuyệt đối rằng dữ liệu đã sống sót qua sự cố mất điện.

**Đồng bộ dữ liệu xuống thiết bị** là yêu cầu mạnh hơn. Với tệp, `FileChannel.force(boolean metaData)` yêu cầu đẩy các cập nhật liên quan đến channel xuống thiết bị lưu trữ theo hợp đồng của API, nhưng bảo đảm thực tế còn phụ thuộc loại thiết bị, hệ điều hành, hệ thống tệp và việc tệp được mở từ đâu. Đây không phải thao tác thay thế cho `close()`, và cũng không làm toàn bộ quá trình thay tệp trở thành giao dịch nguyên tử.

| Thao tác | Mục đích chính | Không nên suy ra |
| --- | --- | --- |
| `write(...)` | Đưa dữ liệu vào đối tượng/đích ghi | Mọi byte đã ghi bền vững trên đĩa |
| `flush()` | Đẩy dữ liệu ở bộ đệm của lớp hiện tại xuống tầng kế | Tệp đã được đóng hoặc đã được fsync |
| `close()` | Kết thúc vòng đời, giải phóng tài nguyên | GC đã chạy hoặc thiết bị không thể mất dữ liệu |
| `FileChannel.force(...)` | Yêu cầu đồng bộ cập nhật tệp liên quan đến channel | Thay thế việc đóng, hoặc đảm bảo một giao dịch đa tệp |

Ví dụ dịch vụ ghi cấu hình quan trọng: có thể cần ghi tệp tạm, flush/đóng đúng cách, yêu cầu đồng bộ thích hợp rồi thay thế tệp đích bằng thao tác di chuyển hỗ trợ tính nguyên tử khi có thể. Chính sách này phụ thuộc yêu cầu độ bền và hệ thống tệp; không áp dụng máy móc cho mọi bản ghi nhỏ.

## 9. Ai sở hữu stream thì người đó quản lý vòng đời

Quy tắc thực hành: **phần nào tạo/mở tài nguyên thường chịu trách nhiệm đóng**, trừ khi hợp đồng API chỉ rõ quyền sở hữu được chuyển cho bên nhận.

- Một hàm tự gọi `Files.newInputStream(path)` thì nên đóng stream trong hàm, thường bằng `try-with-resources`.
- Một hàm nhận `InputStream` từ người gọi thường chỉ sử dụng stream; nó **không tự đóng** nếu hợp đồng không chuyển quyền sở hữu, vì người gọi có thể còn cần dùng.
- Một hàm tạo `BufferedReader` bọc stream do người gọi sở hữu phải cân nhắc: đóng wrapper thường sẽ đóng luôn stream nền. Hãy công bố rõ ai chịu trách nhiệm đóng chuỗi wrapper.
- `System.in`, `System.out` và `System.err` là luồng chuẩn chia sẻ của tiến trình. Đóng chúng trong mã thư viện hoặc bài thực hành có thể làm các phần còn lại không đọc/ghi tiếp được; thông thường không nhận quyền đóng chúng.

Đối với chương trình lớn, hãy biểu diễn rõ trách nhiệm trong tên hàm, tài liệu API và cấu trúc `try-with-resources`. Tránh tình huống hai nơi đều cho rằng bên kia sẽ đóng, hoặc cả hai đều tự đóng tài nguyên chung.

Một số API cấp cao như `Files.readAllBytes` hoặc `Files.readString` tự mở và đóng tài nguyên cần thiết trong lời gọi; người sử dụng chỉ nhận kết quả dữ liệu. API kiểu `Files.newInputStream` hoặc `Files.lines` trao lại một đối tượng sống cần đóng. Sự khác biệt nằm ở **hợp đồng của phương thức**, không nằm ở việc tên có chứa “Files”.

## 10. Lỗi thường gặp và cách phát hiện

| Dấu hiệu / cách viết | Vấn đề | Cách xử lý |
| --- | --- | --- |
| Mở tệp trong vòng lặp, không đóng | Rò rỉ handle/descriptor sau nhiều lần | Dùng `try-with-resources` trong mỗi lần mở |
| Chỉ gọi `close()` trên đường thành công | Ngoại lệ bỏ qua bước giải phóng | Đưa tài nguyên vào `try-with-resources` ngay khi mở |
| Dùng `available() == 0` để suy ra EOF | `available()` chỉ ước lượng số byte có thể đọc không chặn, không xác định hết luồng | Dựa vào giá trị trả về của `read()` |
| Giả định `read(buffer)` điền đầy mảng | Ghi thêm dữ liệu cũ hoặc mất dữ liệu | Dùng đúng `count` do `read` trả về |
| Ghi tệp nhị phân qua `Reader/Writer` | Giải mã/mã hóa làm đổi byte | Dùng byte stream hoặc `Files.copy` |
| Đóng wrapper không thuộc sở hữu | Đóng luôn stream gốc của bên gọi | Quy định rõ quyền sở hữu trong hợp đồng |
| Gọi `flush()` rồi coi như an toàn khi mất điện | Nhầm bộ đệm Java với độ bền vật lý | Chọn chiến lược đồng bộ và ghi tệp an toàn khi cần |
| Nuốt mọi `IOException` ở `close()` | Mất tín hiệu hỏng đường ghi hoặc dọn dẹp | Ghi nhận và xử lý lỗi, bảo toàn ngoại lệ chính |
| Mở `Files.lines`/`Files.walk` nhưng không đóng | Có thể giữ tài nguyên đọc tệp/thư mục | Bọc kết quả trong `try-with-resources` |

Để tìm lỗi tài nguyên trong chương trình thực, hãy theo dõi số descriptor/handle đang mở của tiến trình, thử tải lặp nhiều lần, xem stack trace `IOException`, và kiểm tra mọi nhánh kết thúc sớm, lỗi và hủy. Số lượng handle tăng ổn định theo tải mà không giảm sau khi hoàn thành công việc là một dấu hiệu cần điều tra, chưa đủ để kết luận chính xác chỗ rò rỉ.

## 11. Tự kiểm tra hiểu biết

**Tình huống A.** Một hàm gọi `read(buffer)`, nhận được `3` nhưng lại ghi `buffer.length` byte. Hỏi lỗi là gì? **Giải thích:** chỉ ba phần tử đầu mảng chứa dữ liệu mới của lượt đọc; phần còn lại có thể chứa byte từ lượt trước. Cần `write(buffer, 0, 3)`.

**Tình huống B.** Chương trình đã đọc đến `-1` và thoát vòng lặp nhưng không gọi `close()`. Hỏi tài nguyên đã được giải phóng chưa? **Giải thích:** EOF không kết thúc vòng đời tài nguyên. Dùng `try-with-resources`.

**Tình huống C.** Một thư viện nhận `InputStream` do ứng dụng cung cấp và tự đóng stream ở cuối hàm. Có luôn đúng không? **Giải thích:** không; nếu không có thỏa thuận chuyển quyền sở hữu, thư viện có thể làm hỏng các lần đọc tiếp theo của ứng dụng.

**Tình huống D.** `BufferedOutputStream.flush()` trả về bình thường. Có thể khẳng định dữ liệu sẽ sống sót sau mất điện không? **Giải thích:** không; flush ở tầng Java không tương đương đồng bộ bền vững trên thiết bị.

**Bài tập thực hành:** thử sửa ví dụ sao chép để (1) sao chép chuỗi UTF-8 có dấu và kiểm tra kích thước byte; (2) đặt kiểm tra lỗi giữa chừng và quan sát tệp đích có thể dang dở; (3) thay vòng lặp tự viết bằng `Files.copy` rồi so sánh trách nhiệm đóng tài nguyên của hai cách.

## Ghi nhớ

1. **Stream mô tả dòng byte/ký tự; tài nguyên hệ điều hành là thứ cần được quản lý bên dưới**, và không phải stream nào cũng có descriptor riêng.
2. **Mở, sử dụng, đọc tới EOF và đóng là các mốc khác nhau**. Không để GC quyết định thời điểm giải phóng I/O.
3. **Dùng try-with-resources và xác định chủ sở hữu tài nguyên**. Wrapper có thể đóng luôn luồng nền.
4. **Xử lý đọc/ghi theo từng phần và giữ thông tin lỗi**. Không nhầm số byte đã đọc, bộ đệm đã flush, tài nguyên đã đóng và dữ liệu đã bền vững.
5. **Chọn API theo dữ liệu**: byte stream cho nhị phân, Reader/Writer với charset rõ ràng cho văn bản, các tiện ích `Files` khi không cần tự quản lý vòng lặp.

### Tài liệu API tham khảo

- [InputStream (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html)
- [OutputStream (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html)
- [AutoCloseable (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html)
- [Files (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [FileChannel (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html)
