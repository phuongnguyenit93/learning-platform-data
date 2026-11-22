# Đồng bộ dữ liệu xuống thiết bị và giới hạn bảo đảm của hạ tầng

Trong chương **Độ bền dữ liệu** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, ta tìm hiểu điều gì thật sự xảy ra giữa thời điểm ứng dụng Java gọi hàm ghi dữ liệu và thời điểm dữ liệu có thể được phục hồi sau sự cố. Một lời gọi `write()` thành công, một transaction đã `COMMIT`, hay một bản sao đã nhận dữ liệu đều có ý nghĩa khác nhau. Để thiết kế tầng persistence đáng tin cậy, cần hiểu **các tầng bộ đệm**, **cơ chế đồng bộ xuống thiết bị**, **ranh giới cam kết của cơ sở dữ liệu** và **những sự cố vượt quá bảo đảm của một thiết bị**.

Mục tiêu của bài là trả lời được bốn câu hỏi thực hành: *Dữ liệu đang nằm ở đâu khi hàm ghi trả về? Động tác nào yêu cầu hệ điều hành lưu bền dữ liệu? Database xác nhận commit dựa trên điều kiện nào? Nếu thiết bị, máy chủ hay cả vùng triển khai gặp sự cố thì còn gì để phục hồi?*

## 1. Độ bền dữ liệu là một cam kết có phạm vi

Trong ACID, **Durability (tính bền vững)** có nghĩa: khi cơ sở dữ liệu xác nhận một giao dịch đã commit thành công, các thay đổi của giao dịch đó phải tồn tại qua **những loại sự cố mà hệ thống và cấu hình cam kết chịu được**.

Điều này **không** đồng nghĩa với việc mỗi câu lệnh `write()` đã ghi xuống đĩa, mọi bản sao đều có dữ liệu mới nhất, hoặc dữ liệu không thể mất trong bất kỳ thảm họa nào.

Ví dụ: khách hàng thanh toán thành công và API trả “Đơn hàng đã được ghi nhận”. Sau đó tiến trình database bị dừng đột ngột. Nếu hệ thống đã xác nhận commit theo chế độ lưu bền phù hợp, bản ghi đơn hàng phải được khôi phục khi database chạy lại. Nhưng nếu toàn bộ hệ thống lưu trữ bị phá hủy và không có bản sao hoặc backup, một thiết bị riêng lẻ không thể bảo đảm sự tồn tại của dữ liệu.

Cần phân biệt các khái niệm:

| Khái niệm | Điều được bảo đảm hoặc yêu cầu | Điều **chưa** thể kết luận |
| --- | --- | --- |
| **Ghi vào buffer của ứng dụng** | Byte đã được sao chép vào bộ đệm do ứng dụng/thư viện quản lý. | Hệ điều hành hoặc thiết bị đã thấy dữ liệu. |
| **Lệnh ghi trả thành công** | Một số byte đã được chuyển cho tầng I/O kế tiếp theo hợp đồng API. | Byte đã được lưu bền trên thiết bị. |
| **`flush()` của stream có bộ đệm** | Yêu cầu đẩy dữ liệu đang đệm đến stream bên dưới. | Cache của hệ điều hành hay thiết bị đã được đồng bộ bền vững. |
| **`fsync`/`fdatasync` hoặc cơ chế tương đương** | Yêu cầu hệ điều hành đồng bộ các thay đổi của tệp xuống tầng lưu trữ theo hợp đồng nền tảng. | Thiết bị có thật sự tôn trọng lệnh, dữ liệu có còn nguyên nếu mất cả thiết bị. |
| **Database `COMMIT` thành công ở chế độ đồng bộ** | Database xác nhận theo chính sách WAL/log và đồng bộ đã cấu hình. | Mọi replica, bản backup hoặc ứng dụng bên ngoài đều đã cập nhật. |
| **Đồng bộ tới bản sao/backup** | Thêm một hoặc nhiều bản dữ liệu được giữ ở nơi khác theo chính sách cụ thể. | Không bao giờ có mất mát do xóa nhầm, hỏng dữ liệu logic hay sự cố chung. |

Vì vậy, bất kỳ câu khẳng định “dữ liệu đã an toàn” nào cũng cần đi kèm **mô hình sự cố** và **điều kiện xác nhận thành công**.

## 2. Một byte đi qua những tầng nào trước khi được lưu?

Khi Java ghi một tệp hoặc gửi câu SQL tới database, dữ liệu thường đi qua nhiều lớp. Sơ đồ đơn giản hóa cho I/O tệp cục bộ:

```text
Ứng dụng Java
    │
    ▼
Buffer trong ứng dụng/thư viện (nếu có)
    │  flush() của buffer
    ▼
System call ghi (write/pwrite hoặc cơ chế tương đương)
    │
    ▼
Page cache của hệ điều hành ──────► Có thể ghi xuống nền về sau
    │
    │  fsync / fdatasync / FileChannel.force(...)
    ▼
Hệ thống tệp và lớp block I/O
    │
    ▼
Cache của bộ điều khiển / thiết bị lưu trữ
    │  flush / FUA / cơ chế bảo vệ mất điện, nếu được hỗ trợ
    ▼
Môi trường lưu trữ không mất dữ liệu khi mất điện
    (flash NAND, đĩa từ hoặc cơ chế bền vững tương đương)
```

Từng lớp có thể **xác nhận đã nhận dữ liệu** trước khi lớp bên dưới ghi bền vững. Ví dụ, một lời gọi ghi tệp trên hệ điều hành thông dụng có thể trả về ngay sau khi dữ liệu vào **page cache RAM**. Việc ghi vật lý sẽ diễn ra sau theo chính sách của kernel.

Một số tầng cần hiểu:

- **Buffer của Java:** `BufferedOutputStream`, `BufferedWriter` và các thư viện có thể giữ dữ liệu trong bộ nhớ tiến trình. Nếu tiến trình chết trước khi đẩy buffer, dữ liệu có thể chưa đến hệ điều hành.
- **Page cache của hệ điều hành:** tăng hiệu năng đọc/ghi bằng RAM. Khi máy chủ mất điện hoặc kernel bị lỗi, phần dữ liệu chỉ còn trong RAM có thể biến mất.
- **Filesystem:** quản lý các khối dữ liệu và metadata như tên tệp, kích thước, vị trí khối; có thể dùng journal hoặc copy-on-write để giữ cấu trúc nhất quán.
- **Cache của thiết bị:** SSD, HDD hoặc bộ điều khiển RAID có thể dùng bộ đệm ghi; hành vi khi mất nguồn tùy phần cứng, firmware và việc thiết bị có hỗ trợ bảo vệ mất điện.
- **Ổ lưu trữ từ xa:** network filesystem, SAN, ổ block trên cloud hoặc lưu trữ phân tán thêm các bước truyền và xác nhận. Ý nghĩa “ghi xong” phụ thuộc hợp đồng của dịch vụ và cấu hình, không thể suy ra từ mã nguồn Java.

Các cơ chế này phục vụ hiệu năng, nhưng cũng tạo nên **khoảng thời gian dữ liệu đã được ứng dụng nhìn nhận là ghi xong mà vẫn chưa sống sót qua một số sự cố**.

## 3. `flush()`, `close()`, `fsync()` và `force()` khác nhau ra sao?

Đây là nguồn gây nhầm lẫn thường gặp nhất khi tự triển khai lưu trữ hoặc xử lý tệp trong Java.

### 3.1. `flush()` chỉ đẩy buffer ở tầng mà nó quản lý

Ví dụ:

```java
try (var writer = java.nio.file.Files.newBufferedWriter(path)) {
    writer.write("order=123,status=PAID");
    writer.flush();
}
```

`writer.flush()` yêu cầu các ký tự đang nằm trong buffer của `writer` được chuyển tới stream bên dưới. Nó **không phải** yêu cầu đồng bộ bộ nhớ đệm hệ điều hành xuống thiết bị bền vững. `close()` thường làm các bước flush/đóng tài nguyên của stream, nhưng một lần đóng tệp bình thường **không đồng nghĩa** với `fsync`.

Tương tự, `Files.writeString(...)` hoặc `Files.write(...)` thành công cho thấy thao tác ghi đã thực hiện theo hợp đồng API, **không mặc định là hợp đồng chống mất điện**.

### 3.2. `fsync` và `fdatasync` là yêu cầu đồng bộ ở tầng hệ điều hành

Trên các hệ điều hành kiểu POSIX:

- **`fsync(fd)`:** yêu cầu đồng bộ nội dung tệp và metadata liên quan theo hợp đồng hệ điều hành.
- **`fdatasync(fd)`:** tập trung vào nội dung và những metadata cần thiết để truy xuất đúng nội dung (ví dụ kích thước tệp khi mở rộng), có thể bỏ qua một số metadata khác.

Cả hai là các lời gọi có thể tốn thời gian vì phải đợi những thao tác I/O cần thiết. Chúng vẫn phụ thuộc filesystem, driver, phần cứng hoặc dịch vụ lưu trữ **thực hiện đúng** yêu cầu.

Việc đồng bộ **một tệp** chưa chắc đồng bộ **mục nhập thư mục** chứa tên tệp đó. Với thao tác tạo tệp mới hoặc đổi tên, tính bền vững của đường dẫn có thể cần đồng bộ thư mục cha; khả năng thực hiện và ngữ nghĩa khác nhau theo nền tảng.

### 3.3. Java cung cấp `FileChannel.force(...)` và `FileDescriptor.sync()`

Java NIO có thể yêu cầu đồng bộ tệp bằng `FileChannel.force(boolean metaData)`:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class DurableFileWriter {
    public static void appendRecord(Path file, String record) throws IOException {
        byte[] bytes = (record + "\n").getBytes(StandardCharsets.UTF_8);

        try (FileChannel channel = FileChannel.open(
                file,
                StandardOpenOption.CREATE,
                StandardOpenOption.WRITE,
                StandardOpenOption.APPEND)) {

            ByteBuffer buffer = ByteBuffer.wrap(bytes);
            while (buffer.hasRemaining()) {
                channel.write(buffer); // Không giả định một lần write ghi hết buffer.
            }

            channel.force(true); // Yêu cầu lưu dữ liệu và metadata của tệp.
        }
    }
}
```

Ý nghĩa của `force(...)` theo hợp đồng Java phụ thuộc loại thiết bị: với tệp nằm trên **thiết bị lưu trữ cục bộ**, lời gọi yêu cầu đồng bộ các thay đổi của tệp xuống thiết bị; trên một số hệ thống tệp không cục bộ, mức bảo đảm có thể khác. Tham số `true` yêu cầu cả dữ liệu lẫn metadata; `false` chỉ bắt buộc dữ liệu tệp theo phạm vi hợp đồng API.

Điểm quan trọng là **đợi `force(...)` hoàn tất trước khi xác nhận thao tác cần độ bền đã thành công**. Nếu nó ném ngoại lệ, không thể báo đã lưu bền vững.

Tuy vậy, ví dụ trên **chưa phải một hệ thống log giao dịch hoàn chỉnh**:

1. Nếu nhiều tiến trình ghi đồng thời, cần thiết kế cơ chế phối hợp/khóa phù hợp; không mặc định mỗi bản ghi ứng dụng được ghi nguyên tử.
2. Một bản ghi có thể bị ghi dở khi tiến trình hoặc máy chủ lỗi trước khi đồng bộ. Khi đọc lại, cần nhận biết bản ghi hoàn chỉnh (ví dụ bằng length, checksum, sequence number).
3. Nếu tệp **mới được tạo**, sự tồn tại bền vững của tên tệp còn phụ thuộc đồng bộ mục nhập thư mục và ngữ nghĩa hệ thống tệp.
4. Lưu nhiều tệp liên quan nhất quán với nhau cần một giao thức transaction hoặc journal, không phải chỉ gọi `force(true)` cho từng tệp.

Java còn có `FileDescriptor.sync()` ở các API I/O liên quan. Chọn cơ chế phù hợp với lớp I/O mà ứng dụng đang dùng; tránh gọi nhầm `flush()` của đối tượng Java rồi cho rằng đã đồng bộ xuống thiết bị.

### 3.4. Bảng đối chiếu nhanh

| Lời gọi/thao tác | Tác dụng chính | Có đủ để tự khẳng định chống mất điện? |
| --- | --- | --- |
| `BufferedOutputStream.flush()` | Đẩy buffer Java xuống stream bên dưới. | **Không**. |
| `OutputStream.close()` | Đóng stream và thường đẩy buffer liên quan. | **Không mặc định**. |
| `Files.write(...)` | Ghi nội dung theo API tệp và trả khi thao tác hoàn tất. | **Không mặc định**. |
| `FileChannel.force(false)` | Yêu cầu đồng bộ dữ liệu tệp theo hợp đồng API. | Có thể bảo vệ phần dữ liệu trong phạm vi thiết bị/hệ thống tệp; **không bao quát mọi metadata và đường dẫn**. |
| `FileChannel.force(true)` | Yêu cầu đồng bộ dữ liệu và metadata của tệp. | **Mạnh hơn**, vẫn phụ thuộc hạ tầng và có thể cần đồng bộ thư mục. |
| `COMMIT` của DB | Hoàn tất giao dịch theo cấu hình DB. | Phụ thuộc WAL/log, chế độ đồng bộ, replication và điều kiện xác nhận. |

## 4. Khi sửa hoặc thay tệp: có đúng dữ liệu chưa đủ, còn phải đúng tên tệp

Nhiều ứng dụng lưu cấu hình hoặc snapshot bằng quy trình “ghi tệp tạm rồi đổi tên”. Cách này có thể tránh để người đọc nhìn thấy một tệp đang được ghi dở, nhưng **atomic rename** và **durable rename** là hai khái niệm khác nhau.

Trên hệ thống tệp có hỗ trợ, một chiến lược thường gặp là:

```text
1. Tạo tệp tạm trong cùng filesystem với tệp đích
2. Ghi đầy đủ nội dung mới
3. fsync / FileChannel.force(true) tệp tạm
4. Đổi tên tệp tạm thành tệp đích bằng cơ chế atomic move
5. Đồng bộ thư mục cha theo cơ chế nền tảng (khi cần và được hỗ trợ)
6. Chỉ khi chính sách độ bền đã đạt mới xác nhận thành công
```

Vì sao cần nhiều bước?

- **Bỏ bước 3:** tên tệp mới có thể trỏ tới nội dung chưa được lưu bền vững.
- **Bỏ bước 4 hoặc dùng cách thay tệp không nguyên tử:** người đọc có thể thấy tệp bị cắt cụt hoặc nội dung đang viết.
- **Bỏ bước 5:** sau sự cố, thay đổi tên/mục nhập thư mục có thể không được bảo đảm tồn tại, dù nội dung tệp mới đã được đồng bộ.

Trong Java, `Files.move(source, target, StandardCopyOption.ATOMIC_MOVE)` yêu cầu một thao tác di chuyển nguyên tử **nếu filesystem hỗ trợ** và có thể ném `AtomicMoveNotSupportedException`. Ngữ nghĩa thay thế một đích đã tồn tại khi dùng `ATOMIC_MOVE` phụ thuộc implementation; cần có đường xử lý rõ ràng theo hệ điều hành, không mặc định mọi hệ thống cho phép cùng một tổ hợp tùy chọn.

**Không có một đoạn mã Java thuần, ngắn và di động tuyệt đối** có thể cam kết toàn bộ chuỗi tệp tạm → rename → đồng bộ thư mục trên mọi filesystem. Với dữ liệu nghiệp vụ nhiều bước, dùng database hoặc một thư viện lưu trữ đã xử lý giao thức khôi phục thường an toàn và dễ kiểm chứng hơn.

## 5. Database dùng WAL để xác nhận commit như thế nào?

Một database giao dịch thường không bắt buộc phải ghi ngay **mọi trang dữ liệu** xuống thiết bị trước khi trả `COMMIT`. Làm như vậy có thể khiến commit rất chậm. Thay vào đó, nhiều DBMS dùng **write-ahead logging (WAL)** hoặc một cơ chế log phục hồi tương đương.

Ý tưởng trọng tâm:

1. Trước khi xác nhận commit, database chuẩn bị **log đủ thông tin** để phục hồi những thay đổi của transaction.
2. Database đồng bộ log đến mốc phù hợp theo **chính sách độ bền** đang bật.
3. Database trả commit thành công.
4. Các trang dữ liệu có thể được ghi ra thiết bị **sau đó**; khi gặp sự cố, quá trình recovery dùng log để khôi phục trạng thái hợp lệ.

```text
Transaction cập nhật đơn hàng
            │
            ▼
Thay đổi trong bộ nhớ / buffer của database
            │
            ▼
Ghi record của giao dịch vào WAL / redo log
            │
            ▼
Đồng bộ WAL đến mốc commit theo cấu hình
            │
            ▼
       Trả COMMIT thành công
            │
            ▼
Trang dữ liệu được ghi xuống thiết bị theo lịch riêng
            │
            ▼
Nếu có sự cố: recovery đọc log để tái tạo trạng thái đã commit
```

**Write-ahead** có nghĩa là thông tin log cần thiết cho việc phục hồi phải được lưu bền vững trước khi những thay đổi tương ứng của trang dữ liệu được xem là đã lưu an toàn. Tính đúng đắn của cơ chế phụ thuộc thứ tự ghi, checkpoint, cách quản lý trang và xử lý trường hợp ghi dở (*torn write*).

Ví dụ một transaction đã commit, log commit bền vững nhưng trang `orders` còn trong RAM lúc máy chủ sập: khi khởi động lại, database có thể dùng redo log để phục hồi thay đổi. Ngược lại, nếu chính log commit vẫn chỉ nằm trong bộ đệm dễ mất, việc trang dữ liệu thỉnh thoảng được ghi ra không đủ để hứa rằng một transaction vừa được xác nhận sẽ luôn được phục hồi đúng.

### WAL không giống journal của filesystem

Filesystem journaling chủ yếu bảo vệ cấu trúc và tính nhất quán của **filesystem** sau sự cố, tùy chế độ; nó không tự hiểu ranh giới nghiệp vụ như “trừ tiền rồi cộng tiền”. WAL của database mô tả đủ thông tin để engine phục hồi các transaction theo quy tắc của nó.

Do đó, câu “ổ đĩa dùng journaling filesystem” không thay thế được yêu cầu **database WAL + đúng chính sách flush + recovery**.

### Group commit để tránh đồng bộ riêng từng giao dịch

Một lần đồng bộ xuống thiết bị có thể tốn nhiều thời gian. **Group commit** gộp log của nhiều giao dịch, rồi thực hiện một hoặc một số lần đồng bộ chung trước khi xác nhận các giao dịch đủ điều kiện.

Ví dụ:

```text
WAL buffer: [T101 commit][T102 commit][T103 commit]
                         │
                         ▼
                   Đồng bộ log
                         │
                         ▼
              ACK T101, T102, T103
```

Nhờ vậy, thông lượng có thể cao hơn so với mỗi transaction đều có một lần flush vật lý riêng. Chi phí có thể đổi thành một phần độ trễ chờ nhóm và phụ thuộc workload, thiết bị và triển khai của DBMS. Ứng dụng **không nên tự thêm `sleep()` vào giao dịch** để giả lập group commit; đó là cơ chế do database quản lý.

## 6. Các điểm cấu hình ảnh hưởng đến lời hứa commit

Thông số cụ thể khác nhau giữa các sản phẩm. Mục tiêu khi đọc cấu hình là xác định: **khi database trả “commit thành công”, log đã được đồng bộ tới đâu, và theo chính sách nào?**

### PostgreSQL

PostgreSQL dùng WAL và có các cấu hình liên quan:

- **`fsync`:** điều khiển việc PostgreSQL yêu cầu hệ điều hành đồng bộ các bản ghi liên quan xuống lưu trữ bền vững. Tắt nó làm mất các bảo đảm quan trọng và có thể dẫn tới hỏng dữ liệu sau sự cố; không coi đó là cách tối ưu mặc định cho production.
- **`synchronous_commit`:** quyết định mức chờ khi xác nhận transaction commit. Với cơ chế cục bộ và chế độ thông thường, database chờ WAL commit được flush cục bộ; nếu cấu hình các replica đồng bộ, những chế độ chờ khác còn liên quan việc replica nhận, ghi hoặc áp dụng log. Giá trị `off` có thể trả thành công trước khi WAL commit được flush và **cho phép mất một số transaction vừa được báo thành công** sau sự cố.
- **`full_page_writes`:** ghi bổ sung thông tin trang để hỗ trợ khôi phục trước rủi ro ghi trang không hoàn chỉnh; không phải tùy chọn chỉ để giảm dung lượng log khi chưa đánh giá hệ thống lưu trữ.

Không nên hiểu “bật `synchronous_commit`” đồng nghĩa có replica đồng bộ: **đợi flush cục bộ** và **đợi một replica khác** là hai mức bảo đảm khác nhau. Cấu hình replication và chính sách xác nhận phải được xem cùng nhau.

### MySQL/InnoDB

Với MySQL/InnoDB, những cấu hình thường cần đánh giá gồm:

- **`innodb_flush_log_at_trx_commit`:** chi phối thời điểm InnoDB ghi và flush redo log theo transaction. Chế độ `1` được dùng để yêu cầu ghi/flush mỗi lần commit theo cơ chế của engine; các chế độ giảm tần suất flush có thể cải thiện hiệu năng nhưng tăng khoảng thời gian mất transaction khi hệ điều hành hoặc máy mất nguồn.
- **`sync_binlog`:** điều khiển việc đồng bộ binary log. Nếu hệ thống dùng binary log cho replication hoặc phục hồi theo thời điểm, cần xem tính bền vững của **cả redo log lẫn binary log** và cách database phối hợp chúng.

Không suy diễn kết quả vận hành chỉ từ một tham số. Cần xét phiên bản MySQL, cấu hình redo/binlog, môi trường chạy, đặc tính filesystem và cách xác nhận trong topology replication thực tế.

### Vì sao tối ưu bằng cách tắt flush có rủi ro?

Giả sử database trả commit thành công ngay khi WAL mới ở RAM. Trong khoảng thời gian sau ACK mà trước flush xuống thiết bị, tiến trình có thể còn ghi tiếp nhưng máy chủ đột ngột mất điện. Sau khi khởi động lại, các transaction đã trả thành công trong khoảng đó **có thể không còn**. Đây là lựa chọn **mức độ bền vững đánh đổi thông lượng/độ trễ**, cần có yêu cầu RPO rõ ràng và được chấp thuận ở cấp thiết kế.

Không thể dùng câu “chúng tôi có backup” để mặc nhiên chấp nhận mất commit: backup có thể cách đó nhiều phút/giờ và **không làm một transaction đã xác nhận trở nên bền vững tại thời điểm xác nhận**.

## 7. Giới hạn của hạ tầng: thiết bị có thể không giữ đúng lời hứa

Ngay cả khi ứng dụng gọi `fsync` thành công, phạm vi bảo đảm vẫn phụ thuộc vào các tầng phía dưới. Các hệ thống lưu trữ khác nhau có khả năng chịu sự cố rất khác nhau.

| Tầng hoặc thành phần | Điểm cần xác minh | Rủi ro nếu giả định sai |
| --- | --- | --- |
| **Ổ HDD/SSD** | Thiết bị có tôn trọng flush, cache flush/FUA, bảo vệ khi mất điện hay không? | Ghi còn trong cache mất điện bị mất; firmware lỗi gây mất/hỏng dữ liệu. |
| **SSD flash** | Có cơ chế power-loss protection phù hợp cho dữ liệu và metadata ánh xạ FTL hay không? | Mất điện đúng lúc cập nhật ánh xạ/ghi flash có thể gây mất hoặc hỏng dữ liệu. |
| **Bộ điều khiển RAID** | Cache write-back có được bảo vệ bởi pin/tụ điện? Flush có được chuyển xuống tầng phù hợp? | Controller báo ghi xong dù dữ liệu vẫn ở cache dễ mất. |
| **Filesystem** | Chế độ journaling/COW, thứ tự ghi, hỗ trợ sync và atomic rename? | Nội dung hoặc tên tệp chưa được lưu bền vững theo cách ứng dụng nghĩ. |
| **Máy ảo/container** | Ổ là volume bền vững hay lớp lưu trữ tạm? Host có truyền đúng các lệnh flush không? | Xóa/recreate instance làm mất dữ liệu, hoặc cơ chế sync bị suy yếu. |
| **Network filesystem/SAN** | Server có commit dữ liệu thật lên ổ bền vững trước khi ACK? Giao thức và mount option bảo đảm gì? | Client nhận ACK trước khi máy chủ từ xa lưu bền vững. |
| **Cloud block storage** | Hợp đồng durability, vùng lỗi, snapshot, replication và flush của nhà cung cấp? | Nhầm mức bảo vệ trước mất máy/ổ với bảo vệ trước mất vùng hoặc xóa nhầm. |

**Power-loss protection (PLP)** trên một SSD hoặc bộ điều khiển thường giúp giữ lại dữ liệu đang ở bộ đệm khi mất nguồn đột ngột, nhưng phải xem nhà sản xuất bảo đảm phần nào: dữ liệu đã được ACK, metadata ánh xạ, phạm vi bảo vệ và độ tin cậy qua vòng đời thiết bị.

**UPS** có thể giúp máy chủ hoạt động đủ lâu để dừng an toàn khi mất điện lưới, nhưng không bảo vệ được mọi kịch bản: nguồn bị rút trong thiết bị, hỏng controller, kernel panic, lỗi firmware, thiên tai hoặc mất nguyên hệ thống lưu trữ. UPS và SSD có PLP là các **lớp giảm rủi ro**, không thay thế quy trình backup và phục hồi.

**RAID không phải backup.** RAID có thể tăng khả năng chịu lỗi đĩa và tính sẵn sàng theo cấu hình, nhưng có thể sao chép cả thao tác xóa nhầm hoặc dữ liệu bị mã hóa độc hại. Một vùng lưu trữ chung có thể hỏng đồng thời hoặc bị xóa bởi cùng một quyền quản trị.

## 8. Phân biệt loại sự cố để hiểu bảo đảm thật sự

Một câu trả lời đúng về durability phải gắn với **loại lỗi** đang xét:

| Sự cố | Nếu dữ liệu chỉ ở buffer dễ mất | Nếu WAL được lưu bền và hệ thống lưu trữ làm đúng hợp đồng | Cần bổ sung gì? |
| --- | --- | --- | --- |
| **Tiến trình Java chết** | Buffer Java chưa flush có thể mất. | Dữ liệu đã đồng bộ xuống tệp hoặc DB commit theo chính sách thường còn. | Định dạng log có thể phục hồi bản ghi dở, kiểm soát tài nguyên. |
| **Database process crash** | Transaction chưa commit có thể bị rollback; WAL chưa flush có thể mất. | Recovery có thể khôi phục các transaction đã commit theo chính sách. | WAL, checkpoint, kiểm thử recovery. |
| **Kernel panic / reboot đột ngột** | Page cache chưa đồng bộ có thể mất. | WAL/tệp đã sync có cơ hội được phục hồi theo bảo đảm tầng dưới. | Kiểm tra chế độ flush và filesystem. |
| **Mất điện toàn máy** | Cache RAM/controller không bền có thể mất. | Thiết bị tôn trọng flush và có cơ chế bảo vệ phù hợp mới giữ được lời hứa. | PLP, UPS, kiểm thử phù hợp, lưu trữ đáng tin cậy. |
| **Hỏng một thiết bị lưu trữ** | Có thể mất toàn bộ dữ liệu trên thiết bị. | WAL/tệp cũng mất nếu chỉ có trên thiết bị bị hỏng. | Redundancy, replica, backup ở nơi khác. |
| **Mất toàn bộ site/region** | Mất dữ liệu ở site đó. | Sync cục bộ không thể cứu dữ liệu đã mất cùng site. | Bản sao/backup độc lập về miền lỗi. |
| **Xóa nhầm hoặc migration sai** | Thay đổi sai có thể đã được sync hoàn toàn. | Durability còn khiến lỗi logic được lưu bền. | Backup phục hồi theo thời điểm, kiểm soát thao tác và audit. |

Một hệ thống có thể đạt durability trước **process crash** mà không đạt trước **mất điện**, hoặc chịu lỗi **một máy chủ** mà không chịu lỗi **cả vùng triển khai**. Khi chọn kiến trúc persistence, hãy ghi rõ mong muốn chịu được loại sự cố nào.

## 9. Đồng bộ trên một máy khác với replication và backup

Khi một database commit thành công ở nút chính, có thể tồn tại nhiều mốc:

```text
Nút chính ghi WAL
       │
       ├─ WAL được flush cục bộ
       │
       ├─ Replica nhận bản ghi log qua mạng
       │
       ├─ Replica ghi log vào tầng lưu trữ của nó
       │
       ├─ Replica đồng bộ log bền vững
       │
       └─ Replica replay/apply thay đổi cho truy vấn
```

Các mốc **nhận**, **ghi**, **flush** và **apply** không đồng nghĩa nhau. Chính sách xác nhận commit đồng bộ có thể yêu cầu một hoặc nhiều mốc tại một hoặc nhiều replica, tùy cơ sở dữ liệu và cấu hình.

### Replication bất đồng bộ

Ở chế độ **asynchronous replication**, nút chính có thể xác nhận commit **trước khi** replica nhận bản ghi mới. Nếu nút chính mất vĩnh viễn ngay sau commit và hệ thống nâng replica chưa bắt kịp lên làm chính, một số giao dịch đã ACK có thể **không xuất hiện** trên nút mới.

Đó là **mất dữ liệu khi failover**, dù giao dịch ở nút chính từng được xác nhận đúng theo độ bền *cục bộ*. Muốn đánh giá rủi ro, phải quan sát **replication lag** và khả năng truy cập lại dữ liệu từ nút chính.

### Replication đồng bộ

Ở chế độ **synchronous replication**, có thể yêu cầu ít nhất một replica xác nhận đã nhận/ghi bền log tới mốc nhất định trước khi nút chính báo commit. Cách này giảm rủi ro mất commit khi hỏng một nút, nhưng có chi phí mạng, thời gian chờ, và có thể ảnh hưởng khả năng ghi nếu các replica bắt buộc không đáp ứng.

**Đồng bộ không luôn có nghĩa replica đã áp dụng xong dữ liệu cho truy vấn.** Nếu ứng dụng đọc ngay trên replica, cần hiểu mức chờ nào được cấu hình và sự khác biệt giữa dữ liệu **đã lưu bền** với dữ liệu **đã nhìn thấy qua truy vấn**.

### Backup và phục hồi theo thời điểm

Replication giúp tăng tính sẵn sàng; **backup** cung cấp khả năng khôi phục sau xóa nhầm, hỏng logic, mã hóa độc hại hoặc mất nhiều bản sao cùng lúc. Một chiến lược thường gồm:

- Backup nền (*base/full backup*) có tính nhất quán theo công cụ DBMS.
- Chuỗi WAL/binlog hoặc log liên tục đủ để **point-in-time recovery (PITR)** đến thời điểm mong muốn.
- Bảo vệ backup bằng phân quyền riêng, mã hóa, chính sách giữ bản và nơi lưu trữ độc lập.
- **Thử restore định kỳ**, kiểm tra dữ liệu và thời gian khôi phục; việc job “backup succeeded” không đủ chứng minh có thể khôi phục.

### RPO và RTO phải được định lượng

- **RPO (Recovery Point Objective):** mức mất dữ liệu tối đa chấp nhận được, thường diễn đạt bằng khoảng thời gian. Ví dụ RPO 5 phút có nghĩa tổ chức đặt mục tiêu không mất quá khoảng 5 phút thay đổi trong kịch bản đã định.
- **RTO (Recovery Time Objective):** thời gian tối đa mục tiêu để đưa dịch vụ trở lại sau sự cố.

Hai chỉ số khác nhau: một bản backup cách đây một giờ có thể khôi phục rất nhanh nhưng vẫn không đáp ứng RPO 5 phút; một replica bắt kịp gần tức thời có thể giữ RPO tốt nhưng quy trình failover thủ công kéo dài có thể khiến RTO không đạt.

## 10. Ranh giới commit đối với ứng dụng Java

Với JDBC, `Connection.commit()` là lời gọi yêu cầu database kết thúc transaction theo hợp đồng server và các cấu hình độ bền hiện hành. **Việc `PreparedStatement.executeUpdate()` trả 1 chưa có nghĩa giao dịch đã commit**.

Ví dụ đơn giản:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderWriter {
    private final DataSource dataSource;

    public OrderWriter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void createOrder(String requestId, long orderId) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                try (PreparedStatement statement = connection.prepareStatement(
                        "INSERT INTO orders (id, request_id, status) " +
                        "VALUES (?, ?, 'PENDING')")) {
                    statement.setLong(1, orderId);
                    statement.setString(2, requestId);
                    if (statement.executeUpdate() != 1) {
                        throw new SQLException("Khong ghi duoc don hang");
                    }
                }

                connection.commit(); // Chỉ sau khi trả thành công mới phản hồi OK.
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }
}
```

Ví dụ giả định có bảng `orders` và ràng buộc **UNIQUE** trên `request_id`. Đây là minh họa ranh giới giao dịch; chương trình thật cần kiểm tra quyền ghi, validate dữ liệu, xử lý kiểu lỗi và chính sách idempotency.

### Lỗi khó nhất: không biết commit đã thành công chưa

Xét thứ tự:

```text
Ứng dụng gửi COMMIT
        │
Database ghi WAL và hoàn tất commit
        │
Kết nối mạng đứt trước khi ứng dụng nhận ACK
        │
Ứng dụng nhận lỗi I/O hoặc timeout
```

Ở đây database **có thể đã commit** dù client nhận ngoại lệ. Nếu ứng dụng tự động gửi lại yêu cầu tạo đơn hàng như một giao dịch mới, nó có thể tạo **đơn trùng**, thu tiền hai lần hoặc giảm tồn kho hai lần.

Cách giải quyết là **gắn định danh yêu cầu bền vững** như `request_id` cho một ý định nghiệp vụ và dùng ràng buộc duy nhất ở DB. Khi gặp kết quả commit không rõ, ứng dụng phải đối soát trên nguồn dữ liệu có tính nhất quán phù hợp (thường là primary hoặc đường đọc đảm bảo không trễ), xác nhận request đã có kết quả hay chưa rồi mới quyết định thử lại.

Lưu ý:

1. `rollback()` sau một lỗi commit không chứng minh transaction đã chưa commit. Kết nối có thể đã mất hoặc database đã hoàn tất.
2. Retry trong trường hợp **serialization failure/deadlock** khác với retry sau **mất ACK commit**. Loại đầu thường được xác định đã rollback; loại sau có thể cần truy vấn đối soát.
3. Nếu phát sự kiện sau commit bằng một lời gọi mạng riêng, có khoảng trống “đã commit nhưng chưa gửi sự kiện”. Mẫu **transactional outbox** giúp lưu sự kiện chờ gửi cùng transaction; worker gửi lại và consumer cần idempotent.
4. Việc “server trả 200 OK” cũng không tự bảo đảm một dịch vụ **bên ngoài** đã xử lý xong; mỗi hệ thống có ranh giới độ bền và xác nhận riêng.

## 11. Thiết kế độ bền khác nhau cho từng loại dữ liệu

Không phải mọi dữ liệu đều cần cùng một mức đồng bộ. Điều quan trọng là **xác định điều gì được phép mất** và **không được quảng bá cam kết mạnh hơn cấu hình đã chọn**.

| Loại dữ liệu | Hướng thiết kế thường gặp | Lý do |
| --- | --- | --- |
| Đơn hàng/nhật ký chuyển tiền | DB transaction, WAL flush phù hợp, idempotency, backup/PITR | Không thể âm thầm mất giao dịch đã xác nhận. |
| Bản ghi audit quan trọng | Ghi có thứ tự, định danh riêng, lưu trữ hạn chế sửa/xóa, sao lưu độc lập | Cần truy vết và khôi phục bằng chứng. |
| Session người dùng | Có thể dùng store phân tán, TTL, replication theo RPO đã chấp nhận | Có thể ưu tiên khả năng phục vụ, tùy ứng dụng. |
| Cache tính toán lại được | Có thể chấp nhận mất khi process/máy chủ sập | Dữ liệu gốc vẫn có thể phục hồi để dựng lại cache. |
| Metrics tạm thời | Batch hoặc buffer với giới hạn mất mẫu rõ ràng | Giảm chi phí mỗi lần đồng bộ; ưu tiên throughput. |
| File upload | Tệp/đối tượng lưu trữ có checksum, xác nhận hoàn tất, backup/versioning theo chính sách | Tránh xác nhận upload khi dữ liệu chưa bền vững hoặc chưa kiểm toàn vẹn. |

Ví dụ hệ thống giỏ hàng có thể chấp nhận mất lần thay đổi gần nhất trong một số tình huống nếu sản phẩm đã quyết định rõ. Nhưng hệ thống thanh toán không nên dùng mặc định cùng chính sách độ bền chỉ vì nó giúp giảm độ trễ.

Khi lập tài liệu kiến trúc, nên ghi:

- **Sự kiện xác nhận:** lúc nào API được phép báo thành công?
- **Failure model:** hệ thống phải chịu process crash, host loss, mất một ổ đĩa hay mất cả site?
- **RPO/RTO:** số liệu mục tiêu nào phải đáp ứng?
- **Lưu trữ:** WAL/flush, replica, backup và kiểm thử recovery đang cấu hình thế nào?
- **Giới hạn:** loại dữ liệu nào có thể mất, các thao tác nào có kết quả không rõ và cần đối soát?

## 12. Hiệu năng: đồng bộ bền vững thường có chi phí

Một lần đồng bộ xuống thiết bị có thể buộc đường ghi phải đợi hoàn tất nhiều tầng I/O. Khi workload có nhiều transaction nhỏ, chi phí này đôi khi chi phối **độ trễ ở phần đuôi (p95/p99)** và thông lượng.

Các hướng tối ưu hợp lý:

1. **Dùng transaction ngắn và ranh giới hợp lý.** Không giữ transaction mở trong lúc chờ API bên ngoài, nhập liệu hoặc thao tác mạng dài.
2. **Để database thực hiện group commit và tối ưu WAL.** Không tự vô hiệu hóa sync chỉ vì đo thấy độ trễ giảm.
3. **Đo thực tế:** latency commit, thời gian chờ flush WAL, số lượng flush, throughput, áp lực I/O, thời gian chờ khóa và replication lag.
4. **Sử dụng thiết bị phù hợp** với workload, có khả năng flush và bảo vệ mất điện được kiểm chứng, thay vì chỉ nhìn tốc độ ghi tuần tự trong quảng cáo.
5. **Batch dữ liệu được phép mất** theo quyết định sản phẩm. Cần nêu rõ bao nhiêu dữ liệu có thể mất nếu máy chủ sập trước flush.
6. **Tách dữ liệu bền vững khỏi cache:** không buộc mỗi metric/log không quan trọng phải chờ như một transaction tiền tệ.

Một phép đo hợp lý phải gồm cả **thông lượng, latency, error rate và khả năng phục hồi sau sự cố**. Hệ thống ghi nhanh hơn nhưng thất lạc các transaction vừa được xác nhận có thể đã đánh đổi sai yêu cầu nghiệp vụ.

### Đừng nhầm commit latency với tốc độ của mỗi trang dữ liệu

WAL cho phép database đồng bộ một luồng log tuần tự trước khi từng trang dữ liệu được đẩy xuống đĩa. Vì vậy, tăng cache hoặc thay đổi lịch checkpoint có thể giúp hiệu năng, nhưng mức độ an toàn vẫn phụ thuộc liệu các **bản ghi log bắt buộc** đã được lưu bền đúng thứ tự trước khi xác nhận commit hay chưa.

## 13. Kiểm thử durability bằng sự cố có kiểm soát

Khả năng phục hồi cần được **kiểm chứng**, không chỉ suy luận từ cấu hình hoặc việc ứng dụng chạy thành công trên máy phát triển.

### 13.1. Kịch bản process crash

1. Gửi yêu cầu có `request_id` duy nhất; đợi API báo commit thành công.
2. Dừng tiến trình database đột ngột trong môi trường kiểm thử chuyên dụng, theo phương pháp phù hợp và an toàn.
3. Khởi động lại; chờ cơ chế recovery hoàn tất.
4. Kiểm tra bản ghi đã xác nhận còn đúng, các transaction chưa commit không xuất hiện như đã commit, và bất biến dữ liệu vẫn được giữ.

Đây là kiểm thử hữu ích cho recovery và WAL, nhưng **chưa mô phỏng đầy đủ mất điện của máy chủ hoặc bộ điều khiển lưu trữ**.

### 13.2. Kịch bản mất kết nối lúc commit

Cho ứng dụng mất kết nối ngay quanh thời điểm `COMMIT`. Có thể mô phỏng bằng lớp giao tiếp/thiết bị mạng thử nghiệm thay vì làm gián đoạn môi trường thật. Kiểm chứng:

- Ứng dụng nhận diện trạng thái **không rõ kết quả**.
- Không tạo lại nghiệp vụ khi đã có `request_id` được commit.
- Nếu chưa có kết quả được ghi nhận, cơ chế thử lại có thể hoàn tất đúng **một** lần.
- Hệ thống ghi log/metrics đủ để đối soát sự cố.

### 13.3. Kịch bản mất thiết bị và khôi phục từ backup

Kiểm tra restore vào **môi trường tách biệt**, ví dụ dựng một instance mới từ backup và log liên quan. Xác minh dữ liệu quan trọng bằng truy vấn nghiệp vụ hoặc checksum phù hợp, rồi đo **RPO/RTO thực tế**.

Kiểm thử mất điện thực sự, fault injection ở tầng block storage hoặc thao tác phá hủy thiết bị chỉ nên thực hiện trên môi trường kiểm thử được kiểm soát, có khả năng phục hồi. Không dùng kết quả từ một lần `kill` tiến trình để tuyên bố hạ tầng chắc chắn chịu được mất điện.

### 13.4. Các chỉ số cần quan sát

| Chỉ số | Giúp trả lời câu hỏi gì? |
| --- | --- |
| Commit latency p50/p95/p99 | Việc đợi đồng bộ có gây chậm cho nghiệp vụ hay không? |
| WAL/redo flush time và số lượt flush | Tầng lưu trữ có đang là nút nghẽn không? |
| I/O error, filesystem error, SMART/health signals | Có dấu hiệu thiết bị hoặc hạ tầng đang gặp rủi ro không? |
| Replication lag và trạng thái replica | Bản sao đang cách primary bao xa và có đáp ứng chính sách failover? |
| Thời điểm backup thành công gần nhất | Có bản backup mới đến đâu? |
| Restore test gần nhất và thời gian hoàn tất | Bản backup có **khôi phục được** trong mục tiêu RTO không? |
| Số lần client gặp commit không rõ kết quả | Có cần cải thiện đối soát/idempotency hay kết nối không? |

## 14. Những ngộ nhận cần tránh

| Nhận định dễ gặp | Cách hiểu đúng |
| --- | --- |
| “Gọi `flush()` là dữ liệu đã nằm trên đĩa.” | `flush()` thường chỉ đẩy buffer ở tầng thư viện, không thay `fsync`. |
| “Đóng tệp là chắc chắn chống mất điện.” | `close()` không mặc định đồng nghĩa đồng bộ bền vững ở mọi hệ thống. |
| “`fsync` thành công nên không thể mất dữ liệu trong mọi thảm họa.” | Hợp đồng còn phụ thuộc filesystem, thiết bị và failure model; mất toàn bộ thiết bị cần bản sao/backup. |
| “WAL phải ghi hết trang dữ liệu ra đĩa trước khi commit.” | WAL cho phép commit sau khi log cần thiết được lưu bền theo chính sách, còn trang dữ liệu có thể ghi sau. |
| “Filesystem có journal nên DB không cần WAL.” | Journal của filesystem và log phục hồi transaction giải quyết hai phạm vi khác nhau. |
| “RAID hoặc replica chính là backup.” | Chúng thường sao chép cả lỗi logic/xóa nhầm; backup cần độc lập và restore được. |
| “Replication đồng bộ tức là truy vấn replica thấy ngay mọi thay đổi.” | Đã nhận/flush log không nhất thiết có nghĩa đã replay và sẵn sàng cho mọi truy vấn. |
| “`executeUpdate() == 1` nghĩa là đơn hàng đã commit.” | Lệnh UPDATE/INSERT có thể vẫn nằm trong transaction chưa commit. |
| “Client thấy timeout khi commit tức là DB rollback.” | Commit có thể đã thành công nhưng ACK bị mất; cần đối soát theo định danh. |
| “Backup job chạy xanh nghĩa là dữ liệu cứu được.” | Phải thử restore và xác nhận RPO/RTO trong điều kiện dự kiến. |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Java gọi `BufferedWriter.flush()` rồi trả HTTP 200. Máy chủ mất điện ngay sau đó. Ứng dụng có thể khẳng định nội dung tệp đã bền vững không?

**Không.** `flush()` đẩy buffer Java xuống tầng bên dưới; có thể dữ liệu vẫn nằm trong page cache dễ mất. Cần cơ chế đồng bộ phù hợp, cùng bảo đảm của filesystem/thiết bị và xử lý metadata nếu tạo hoặc đổi tên tệp.

**Câu 2.** Vì sao database có thể trả commit thành công dù trang dữ liệu tương ứng chưa được ghi ra tệp chính?

Vì **WAL/redo log** đã lưu đủ thông tin phục hồi và đã được đồng bộ tới mốc commit theo chính sách. Khi khởi động lại, database dùng log để phục hồi trang dữ liệu còn thiếu.

**Câu 3.** Nút chính xác nhận commit rồi mất vĩnh viễn; replica bất đồng bộ không có giao dịch vừa xác nhận. Có mâu thuẫn với việc nút chính đã lưu bền cục bộ không?

**Không.** Độ bền trên **một thiết bị/nút** và bảo đảm **không mất dữ liệu sau failover** là hai phạm vi khác nhau. Replication bất đồng bộ có thể có lag; muốn cam kết mạnh hơn phải thiết kế topology và chính sách ACK phù hợp.

**Câu 4.** Nếu một ứng dụng đã gọi `FileChannel.force(true)` trên tệp tạm trước khi `Files.move(..., ATOMIC_MOVE)`, đã chắc chắn tên tệp mới tồn tại sau mọi lỗi chưa?

**Chưa.** Việc đồng bộ nội dung/metadata của **tệp** không mặc nhiên đồng bộ **mục nhập thư mục** sau rename. Cần xét khả năng và ngữ nghĩa đồng bộ thư mục của hệ điều hành/filesystem, cùng giới hạn lưu trữ.

**Câu 5.** Khi `Connection.commit()` ném lỗi vì kết nối đứt, vì sao không được gửi lại nghiệp vụ thanh toán ngay?

Vì database có thể đã commit và chỉ mất phản hồi. Gửi lại không có idempotency có thể tạo thao tác trùng. Cần tra cứu giao dịch qua `request_id` và xử lý kết quả không rõ theo một quy trình có thể phục hồi.

**Câu 6.** Tại sao có hai replica vẫn chưa đủ để bảo vệ trước lỗi xóa nhầm hàng loạt?

Vì thao tác xóa hợp lệ với hệ quản trị có thể được **sao chép** sang các replica. Backup độc lập, có thời điểm khôi phục phù hợp, cùng thử nghiệm restore mới giúp khôi phục trạng thái trước khi xóa.

## Kết luận

Lời gọi ghi, đồng bộ bộ đệm, đồng bộ thiết bị và commit thành công nằm ở **những ranh giới bảo đảm khác nhau**. Ở tầng tệp, cần hiểu `flush()`, `FileChannel.force(...)`, metadata thư mục và hành vi thực sự của filesystem/thiết bị. Ở tầng database, cần hiểu WAL, thứ tự flush, chế độ xác nhận commit và quy trình crash recovery. Ở cấp hệ thống, cần bổ sung replication, backup/PITR, RPO/RTO và khả năng đối soát kết quả commit không rõ.

Khi thiết kế ranh giới persistence cho Java, hãy bắt đầu từ **loại sự cố cần chịu được** và **dữ liệu được phép mất**, rồi chọn cơ chế đồng bộ, phần cứng và chính sách xác nhận có thể đo lường và kiểm thử. Không có một lệnh `flush` hoặc một ổ đĩa riêng lẻ nào thay thế được thiết kế độ bền từ ứng dụng tới hạ tầng và quy trình phục hồi.
