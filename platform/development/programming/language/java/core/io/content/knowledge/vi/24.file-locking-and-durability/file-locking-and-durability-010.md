# Giới hạn nhất quán trên network file system trong Java NIO

## 1. Vấn đề: hai tiến trình cùng nhìn một tệp qua mạng có thấy cùng dữ liệu không?

Một **network file system** cho phép nhiều máy truy cập tệp được lưu ở máy chủ hoặc một dịch vụ lưu trữ chung. Ví dụ quen thuộc là **NFS** trên Linux/Unix, **SMB/CIFS** trong môi trường chia sẻ tệp và những file share được mount vào máy ứng dụng.

Giả sử:

~~~text
          Máy A                                  Máy B
     Java writer                            Java reader
       FileChannel                            Files.read...
           |                                       |
    OS page/attribute cache                 OS page/attribute cache
           |                                       |
           +-------------- Network ----------------+
                                |
                          File server
                                |
                         Backing storage
~~~

Máy A ghi `balance=900` và gọi `channel.force(true)`, rồi máy B đọc cùng đường dẫn được mount. Ta cần phân biệt **ba câu hỏi độc lập**:

1. **Visibility (khả năng nhìn thấy):** máy B sẽ thấy ngay phiên bản mới, hay còn thấy bản cũ trong cache?
2. **Durability (tính bền vững):** thay đổi đã được lưu đủ bền để tồn tại sau crash của client, server hoặc hệ thống lưu trữ chưa?
3. **Concurrency/atomicity (đồng thời/nguyên tử):** nếu A và B cùng ghi, có bảo đảm không bị mất cập nhật, bản ghi nửa mới nửa cũ hoặc trình tự khóa sai không?

**Không có một phương thức Java NIO nào tự giải quyết đầy đủ cả ba câu hỏi trên cho mọi network file system.** API Java phụ thuộc vào file-system provider, OS, client cache, giao thức mạng, cấu hình mount và máy chủ lưu trữ.

Bài này tập trung vào giới hạn nhất quán của các thao tác `Files.*`, `FileChannel`, `FileLock`, `MappedByteBuffer` và các mode đồng bộ khi tệp nằm trên hệ thống file qua mạng. Những nhận xét riêng cho NFS không mặc nhiên áp dụng giống hệt cho SMB, hệ thống file phân tán có coherence mạnh hoặc dịch vụ object storage.

## 2. Ba mức nhất quán dễ bị nhầm lẫn

### 2.1. Visibility: có thể đọc lại bản cũ do cache

Ứng dụng Java trên máy B có thể đọc dữ liệu từ page cache hoặc metadata cache của OS. Thời điểm làm mới cache phụ thuộc giao thức và cấu hình. Một phép `Files.readAllBytes(path)` **không mang ý nghĩa đặc biệt “bắt server trả bản mới nhất từ mọi client”**.

Ví dụ thời gian:

~~~text
t0  A và B cùng nhìn version=1
t1  B cache bản version=1
t2  A ghi version=2 và đóng file
t3  B đọc lại nhưng cache chưa được làm mới -> có thể thấy version=1
t4  B mở lại / cache được xác thực hoặc hết hạn -> có thể thấy version=2

Thời điểm, hành vi cụ thể ở t3/t4 phụ thuộc filesystem,
giao thức, mount options và cách chương trình mở/đọc tệp.
~~~

Nếu ứng dụng yêu cầu rằng mọi client đều thấy một lần ghi đã hoàn tất ngay lập tức, nó cần một **hợp đồng nhất quán cụ thể** từ hệ thống lưu trữ. Không được suy luận điều đó chỉ từ tên đường dẫn giống nhau.

### 2.2. Durability: dữ liệu nhìn thấy mới chưa chắc đã bền

Một lời gọi `write(...)` có thể đã làm dữ liệu xuất hiện trong cache của writer, trong khi chưa có bằng chứng dữ liệu đã được lưu an toàn trên thiết bị hoặc được máy chủ cam kết ở mức cần thiết. Gọi `force` có ý nghĩa đối với file cục bộ, nhưng **đặc tả Java 17 không đưa ra bảo đảm tương tự cho file trên thiết bị không cục bộ**.

Ngay cả khi server trả lời đã nhận dữ liệu, tính bền vững trước sự cố điện, thiết bị, replica hoặc nhiều failure domain còn phụ thuộc chính sách của server/storage.

### 2.3. Atomicity và ordering: nhất quán tệp không phải giao dịch

Ghi tuần tự hai trường:

~~~java
// Đoạn minh họa, channel đã mở để ghi.
channel.write(header);
channel.write(body);
~~~

không có nghĩa mọi reader ở máy khác sẽ luôn quan sát cả `header` và `body` như một thay đổi nguyên tử. Mỗi lời gọi có thể ghi một phần, hai lời gọi có thể xen với thao tác của writer khác nếu không được phối hợp.

**Một thao tác I/O thành công, cache coherence, atomic rename, mutual exclusion và durability là những thuộc tính khác nhau.** Ứng dụng cần xác định riêng từng yêu cầu.

## 3. NFS thường cung cấp close-to-open, không phải coherent cache tuyệt đối

Với nhiều cách triển khai NFS phổ biến, mô hình **close-to-open (CTO)** được sử dụng:

1. Client A mở tệp và cập nhật nội dung.
2. A đóng tệp; client NFS có cơ hội đẩy các thay đổi đang chờ lên server.
3. Client B **mở tệp sau đó**; client B có cơ hội xác thực thuộc tính/tình trạng tệp ở server và làm mới dữ liệu cache cần thiết.
4. B đọc bản mới, **nếu** hệ thống tuân theo chính sách CTO trong điều kiện và cấu hình đó.

~~~text
Client A: open -> write -> close
                                    Client B: open -> read -> close
                 ^ ranh giới close-to-open giúp tăng khả năng nhìn thấy
~~~

**CTO không có nghĩa** mọi lượt `read` trên một handle đã mở từ lâu lập tức thấy từng byte A vừa ghi. B cũng không được bảo đảm đọc một snapshot nguyên tử của toàn bộ chuỗi cập nhật A đang thực hiện.

Các điểm cần đặc biệt lưu ý:

- NFS có thể cache **data** và **metadata/attributes** riêng; hai loại cache có lịch làm mới khác nhau.
- Tùy phiên bản giao thức, client kernel và mount options, kết quả quan sát có thể khác.
- Mount option `nocto` trên một số NFS client có thể tắt một phần hành vi close-to-open.
- Mount option `noac` trên Linux NFS nhằm giảm cache thuộc tính, **không có nghĩa toàn bộ data cache đã bị tắt** và cũng không xóa hết race.
- Hệ thống file phân tán khác có thể cung cấp coherence mạnh hơn NFS thông thường; hãy đọc tài liệu của đúng sản phẩm.

**Kết luận thực hành:** Khi cần chuyển giao dữ liệu hoàn chỉnh từ A sang B, thường nên thiết kế ranh giới **“writer hoàn tất → đóng/commit → thông báo phiên bản mới → reader mở/kiểm tra lại”** theo giao thức đã kiểm nghiệm. Nhưng đây vẫn là một **quy trình ứng dụng**, không phải lời hứa tuyệt đối từ Java cho mọi NFS/SMB.

## 4. Metadata cache gây ra những nhầm lẫn gì?

Các thao tác như:

- `Files.exists(path)`
- `Files.size(path)`
- `Files.getLastModifiedTime(path)`
- `Files.readAttributes(path, BasicFileAttributes.class)`
- duyệt thư mục bằng `Files.list(...)` hoặc `DirectoryStream`

có thể phụ thuộc những thông tin file/directory do OS hoặc server cung cấp, và thông tin đó có thể đã bị cache trên client.

Ví dụ máy A đổi tên `ready.tmp` thành `ready.dat`, trong lúc máy B vẫn có cache danh sách thư mục. Máy B **có thể** chưa nhìn thấy entry mới ngay tại thời điểm ứng dụng mong đợi. Việc quan sát entry mới còn chịu ảnh hưởng của các quy tắc rename và invalidation cụ thể.

Một mẫu sai:

~~~java
// Minh họa logic chưa an toàn trước thay đổi đồng thời:
if (Files.exists(path)) {
    long size = Files.size(path);
    byte[] bytes = Files.readAllBytes(path);
    // Không có bảo đảm size và bytes cùng một thời điểm/snapshot.
}
~~~

Từ thời điểm `exists` tới `size` rồi `readAllBytes`, file có thể bị thay đổi, xóa hoặc thay thế. Đây là **TOCTOU (time-of-check to time-of-use)**; nó vẫn có thể xảy ra trên filesystem cục bộ, và cache/mạng làm mô hình quan sát phức tạp hơn.

**Không lấy timestamp hoặc size làm version tuyệt đối.** Độ phân giải thời gian, đồng hồ client/server, cache và chuỗi thay đổi có cùng kích thước làm cách kiểm tra này có thể bỏ sót cập nhật. Nếu cần phát hiện chính xác phiên bản, lưu **version/counter, checksum hoặc manifest** được quản lý rõ ràng.

## 5. `FileChannel.force(...)`: bảo đảm cục bộ không tự mở rộng sang mạng

Java 17 định nghĩa:

~~~java
// Mã minh họa; channel là FileChannel đã mở.
channel.force(false); // Yêu cầu ghi bền các thay đổi nội dung.
channel.force(true);  // Yêu cầu ghi bền nội dung và metadata.
~~~

Theo đặc tả `FileChannel.force(boolean metaData)`:

- Nếu file trên **local storage device**, khi `force` trả về, những cập nhật thuộc hợp đồng đã được ghi xuống thiết bị.
- Nếu file **không nằm trên thiết bị cục bộ**, **không có bảo đảm tương tự**.
- `metaData=false` yêu cầu đồng bộ nội dung; `metaData=true` bao gồm cả metadata cần thiết.
- Khi cập nhật được thực hiện qua **memory-mapped buffer**, `FileChannel.force(...)` **không được bảo đảm** tự force các dirty page do mapped buffer sửa. Cần dùng `MappedByteBuffer.force()` cho nội dung mapping.

Điều này **không có nghĩa** gọi `force` trên NFS/SMB chắc chắn vô ích. Nó có thể dẫn tới yêu cầu ghi/sync phù hợp trên OS và server. Điều không được phép khẳng định là: **“Java đã bảo đảm dữ liệu sống qua mọi crash của mạng/server vì `force(true)` trả về.”**

### `RandomAccessFile` và các mode đồng bộ

| API/Mode | Ý nghĩa trên Java | Giới hạn với file qua mạng |
|---|---|---|
| `RandomAccessFile(..., "rw")` | Đọc/ghi, không bắt buộc đồng bộ trên từng lần ghi | Không có checkpoint durability per-write được hứa |
| `RandomAccessFile(..., "rwd")` | Đồng bộ phần **content** khi cập nhật | Java không đưa ra bảo đảm tương tự local storage trên network device |
| `RandomAccessFile(..., "rws")` | Đồng bộ **content và metadata** khi cập nhật | Vẫn chịu giới hạn trên remote storage |
| `FileChannel.force(false/true)` | Chủ động yêu cầu content / content+metadata được ghi xuống thiết bị | Không phải chứng cứ về replica/quorum hoặc server crash recovery |
| `MappedByteBuffer.force()` | Yêu cầu đồng bộ thay đổi trong vùng đã map | Bảo đảm sau return được đặc tả cho local storage, không tự mở rộng sang remote |

**SYNC/DSYNC** trong `StandardOpenOption` cũng biểu đạt yêu cầu cập nhật đồng bộ tương ứng nhưng không nên được xem là giải pháp bỏ qua giới hạn giao thức/máy chủ mạng. Một file provider có thể không hỗ trợ một số tuỳ chọn hoặc thực hiện chúng theo cơ chế của nó.

### Vì sao đọc lại ngay sau force không chứng minh durability?

Sau khi `write` và `force`, một phép đọc trên cùng client có thể trả dữ liệu từ cache đã chứa phiên bản mới, **kể cả khi server/storage chưa đáp ứng mức bền vững mà ứng dụng cần**.

Muốn kiểm chứng cần thử nghiệm đúng hệ thống NFS/SMB, phiên bản server, mount options và failure model. Việc mô phỏng crash, mất mạng, failover và đọc từ client khác là quan trọng. Ngay cả test thành công cũng chỉ chứng minh hành vi trong cấu hình/điều kiện đã thử, không thành một bảo đảm API Java tổng quát.

## 6. `FileLock`: điều phối quyền ghi, nhưng cần kiểm tra hỗ trợ NFS

Java cung cấp `FileChannel.lock(...)`, `tryLock(...)` và đối tượng `java.nio.channels.FileLock`.

~~~java
// Đoạn minh họa: FileChannel mở với quyền ghi phù hợp.
try (FileLock lock = channel.lock()) {
    // Vùng code cần bảo vệ bởi cùng một quy ước lock.
    updateSharedFile();
    channel.force(true);
} // lock.close()/release() giải phóng khóa.
~~~

Một số điều quan trọng từ đặc tả:

1. **Lock có phạm vi theo file/byte range**, ví dụ `channel.lock(0, 128, false)` yêu cầu khóa **exclusive** trên vùng 128 byte.
2. `lock(position, size, true)` yêu cầu **shared lock**, nhưng hệ thống không hỗ trợ shared lock có thể chuyển thành exclusive. Hãy kiểm tra `FileLock.isShared()` nếu semantics này quan trọng.
3. File lock có tính chất thuộc **JVM**, không được thiết kế để điều phối các thread bên trong cùng JVM. Với các thread, dùng cơ chế đồng bộ Java thích hợp, chẳng hạn `synchronized` hay `ReentrantLock`.
4. Một số nền tảng dùng **advisory lock**: tiến trình không tuân theo giao thức lock vẫn có thể truy cập file. Nền tảng khác có cơ chế mandatory; không giả định giống nhau.
5. Trên network filesystem, việc hỗ trợ lock phụ thuộc phiên bản giao thức, server, client, mount/configuration và kiểu vùng khóa. Java cảnh báo một số NFS không hỗ trợ lock cho vùng map trừ khi canh theo page size hoặc có giới hạn offset/độ dài.
6. Việc đóng channel trên một số hệ điều hành có thể khiến các khóa liên quan tới file trong JVM được giải phóng ngoài dự kiến. Nên dùng **một channel chuyên quản lý khóa trên một file** trong luồng công việc.

Vì vậy **“đã lấy được FileLock” chưa tự chứng minh tính nhất quán toàn cluster**. Cần chứng minh các client tương tác qua cùng một hệ thống khóa, không có client bỏ qua lock, lock không bị mất khi network partition/failover, và ứng dụng xử lý trường hợp không thể gia hạn hoặc xác nhận ownership.

### Ví dụ: tránh mất cập nhật khi hai writer cùng sửa số dư

Hai writer cùng làm quy trình sai:

~~~text
A đọc balance = 1000
B đọc balance = 1000
A tính 1000 - 100 = 900, ghi 900
B tính 1000 - 200 = 800, ghi 800
Kết quả cuối có thể = 800; cập nhật của A bị mất.
~~~

Muốn serialize, cả A và B cần tuân thủ:

~~~text
acquire lock
    -> mở/đọc phiên bản đang có theo quy trình cache coherence đã kiểm nghiệm
    -> xác minh version / điều kiện cập nhật
    -> ghi phiên bản mới
    -> yêu cầu đồng bộ theo chính sách durability
release lock
~~~

Ngay cả có lock, nếu B đọc **bản cache cũ** hoặc server mất lock khi failover, kết quả vẫn có thể sai. Dùng **version number + compare-and-swap logic** ở tầng ứng dụng hoặc hệ lưu trữ phù hợp khi yêu cầu nghiêm ngặt. Một chương trình tự kiểm tra version rồi ghi trên file thường cũng có thể gặp race nếu hai thao tác không được bảo vệ bởi cơ chế coordination đáng tin cậy.

### `tryLock()` và lỗi khi lock không sẵn sàng

- `channel.tryLock()` thường trả về `null` nếu không lấy được khóa ngay vì một tiến trình khác đang giữ khóa tương ứng.
- Nếu trong cùng JVM đã có lock chồng lấn, có thể gặp `OverlappingFileLockException` thay vì `null`.
- Một lời gọi lock có thể thất bại do `IOException` hoặc do provider/OS không hỗ trợ hành vi được yêu cầu.
- Đừng spin vô hạn gọi `tryLock()` mà không có backoff/timeout theo thiết kế. Trên NFS, phản hồi chậm hoặc lỗi mạng cần được xử lý riêng.

## 7. Atomic rename không đồng nghĩa data durability hoặc snapshot xuyên client

Một cách publish file thường dùng:

1. Ghi nội dung hoàn chỉnh vào file tạm **trong cùng thư mục**.
2. Flush/sync tệp tạm theo khả năng nền tảng.
3. Đổi tên file tạm thành tên mà reader dùng.
4. Reader chỉ xử lý file được công bố.

Trong Java có thể yêu cầu:

~~~java
// Đoạn minh họa; temp và target đã được chuẩn bị hợp lệ.
Files.move(temp, target, StandardCopyOption.ATOMIC_MOVE);
~~~

**Những giới hạn quan trọng:**

- `ATOMIC_MOVE` yêu cầu move là thao tác **nguyên tử theo filesystem**. Nếu không hỗ trợ, Java ném `AtomicMoveNotSupportedException`. Thường cần nguồn và đích trên cùng FileStore/provider; không chắc chắn khi đổi qua mount khác.
- Nếu đích đã tồn tại, việc thay thế hay báo lỗi khi dùng `ATOMIC_MOVE` là **implementation-specific** theo Java; không giả định kiểu replace luôn thành công.
- Một rename được thực hiện nguyên tử trên server **không tự đảm bảo** mọi client đã hủy cache ngay lập tức hoặc đọc được cùng một snapshot của nhiều file.
- `ATOMIC_MOVE` cũng **không tự bảo đảm durability** của nội dung tệp tạm, metadata hoặc directory entry sau server crash.
- Nếu không dùng `ATOMIC_MOVE`, giữa kiểm tra tồn tại và thao tác move có thể có race; việc move có thể không nguyên tử với các thao tác filesystem khác.

Đừng dùng cách sai:

~~~java
// Minh họa điều cần tránh khi dữ liệu chưa được phối hợp.
Files.writeString(target, largeDocument); // Reader có thể bắt gặp trạng thái đang ghi.
~~~

Cách publish qua file tạm và rename thường tốt hơn cho **reader chỉ cần toàn bộ bản hoàn tất**, nhưng vẫn cần xác định semantics của đúng shared filesystem và quy tắc reader re-open/verify.

### Manifest và checksum cho dữ liệu nhiều file

Nếu một “phiên bản dữ liệu” gồm `data-1.bin`, `data-2.bin` và `metadata.json`, việc đổi tên từng file không tạo transaction xuyên ba file. Một thiết kế thường dùng:

- Ghi các file phiên bản mới dưới **tên không trùng, bất biến**.
- Force/sync theo khả năng hệ lưu trữ và kiểm tra checksum.
- Khi tất cả sẵn sàng, publish **manifest** trỏ tới tên/version của các file mới.
- Reader đọc manifest, xác minh version/checksum, và chỉ dùng các file khớp phiên bản.
- Nếu checksum hoặc version không khớp, reader **retry theo chính sách có giới hạn**, không âm thầm coi nội dung là mới.

Mô hình này cải thiện khả năng **phát hiện phiên bản hỗn hợp**. Nó vẫn không xóa bỏ yêu cầu lưu bền manifest hay giả định cache consistency của hệ thống.

## 8. Chương trình Java 17+ chạy được: minh họa lock, ghi và force trên file cục bộ

Chương trình dưới đây dùng **một file tạm cục bộ**, có thể chạy ổn định không cần mount NFS. Nó minh họa API Java và trạng thái mà một reader **trên cùng môi trường kiểm thử** có thể xác nhận. Kết quả **không chứng minh** NFS có cùng visibility hoặc durability.

Lưu tệp **`NetworkFileConsistencyDemo.java`**:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class NetworkFileConsistencyDemo {

    private static void writeAll(FileChannel channel, ByteBuffer data)
            throws IOException {
        while (data.hasRemaining()) {
            int n = channel.write(data);
            if (n == 0) {
                throw new IOException("No write progress");
            }
        }
    }

    private static void readExactly(FileChannel channel, ByteBuffer dst)
            throws IOException {
        while (dst.hasRemaining()) {
            int n = channel.read(dst);
            if (n < 0) {
                throw new EOFException("Incomplete record");
            }
            if (n == 0) {
                throw new IOException("No read progress");
            }
        }
    }

    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("fs-consistency-");
        Path file = dir.resolve("record.bin");

        try {
            try (FileChannel writer = FileChannel.open(file,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE);
                 FileLock lock = writer.lock()) {

                ByteBuffer record = ByteBuffer.allocate(16);
                record.putLong(1L);    // version
                record.putLong(900L);  // balance
                record.flip();

                writeAll(writer, record);
                writer.force(true); // Trên local file có bảo đảm Java phù hợp.
                System.out.println("writer: version=1, balance=900");
            }

            // Mở lại sau khi writer đã hoàn tất và đóng channel.
            try (FileChannel reader = FileChannel.open(
                    file, StandardOpenOption.READ)) {
                ByteBuffer record = ByteBuffer.allocate(16);
                readExactly(reader, record);
                record.flip();

                System.out.println("reader: version="
                        + record.getLong() + ", balance="
                        + record.getLong());
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac NetworkFileConsistencyDemo.java
java NetworkFileConsistencyDemo
~~~

**Stdout mong đợi khi filesystem cục bộ cho phép thao tác:**

~~~text
writer: version=1, balance=900
reader: version=1, balance=900
~~~

**Diễn giải:**

1. `ByteBuffer.allocate(16)` có đủ chỗ cho hai số `long`, mỗi số 8 byte. `putLong` ghi dưới dạng nhị phân big-endian mặc định.
2. Writer lấy `FileLock`, ghi đến khi `ByteBuffer` hết remaining, rồi gọi `force(true)` trước khi đóng.
3. Sau khi writer và lock đã đóng, reader mở file, đọc đúng 16 byte và giải mã version/balance.
4. Nếu chạy trên NFS/SMB, stdout **có thể** giống ví dụ, nhưng điều đó không phải thử nghiệm crash/replication/coherence. Các lời gọi lock, force, close và read phải được kiểm chứng trên cấu hình storage cụ thể.

**Lưu ý:** trên một số hệ điều hành, xóa file ngay khi mapping/handle còn mở có thể thất bại; chương trình dùng `try-with-resources` để đóng lock và channel trước khi dọn file. Nếu filesystem có lỗi I/O/permission, chương trình ném ngoại lệ và không tạo đủ stdout.

### Kiểm thử visibility trên hai client thật

Để thử riêng vấn đề NFS, cần **hai máy hoặc hai mount/client thực sự** trỏ đến cùng shared filesystem. Chạy một chương trình writer trên A và reader trên B theo cùng một kịch bản đã ghi thời gian. Nên thu thập:

- NFS/SMB version, server OS và file-system type, mount options và cache policy.
- Thứ tự open → write → force → close ở A; open → read ở B.
- Checksum/version do mỗi bên nhìn thấy, thời điểm nhìn thấy mới và mọi lỗi I/O.
- Kết quả khi B giữ handle mở liên tục so với đóng rồi mở lại.
- Hành vi sau network partition, reconnect, server restart hoặc failover có kiểm soát.

Một lượt kiểm thử luôn thành công cũng **không đủ để suy ra bảo đảm tất cả client luôn thấy ngay lập tức**, nhưng nó là bằng chứng vận hành cho môi trường được thử.

## 9. Network partition, failover và lock bị mất

Khi kết nối bị gián đoạn, client có thể tiếp tục có dữ liệu cũ trong cache. File server hoặc dịch vụ lưu trữ có thể khôi phục phiên, lease hoặc lock theo cách phụ thuộc giao thức. Đặc biệt, không nên suy ra:

- Nếu JVM từng giữ `FileLock` hợp lệ thì sau mọi sự cố mạng server vẫn chắc chắn tôn trọng khóa cũ.
- Nếu server failover thành công thì tất cả dữ liệu gần nhất của mỗi client đã đạt cùng mức durability.
- Nếu thao tác ghi timeout thì “chắc chắn chưa thực hiện”: server có thể đã nhận và áp dụng thay đổi nhưng phản hồi bị mất.
- Nếu retry một thao tác ghi số dư thì sẽ không bị trừ tiền hai lần. Retry có thể tạo lỗi business logic khi thao tác không idempotent.

Nếu dữ liệu rất quan trọng, cần thiết kế **idempotency key**, version/fencing token, bước xác thực lại ownership và quy tắc phục hồi sau lỗi mạng. Các yêu cầu này đôi khi phù hợp hơn với cơ sở dữ liệu/transaction store có hợp đồng nhất quán rõ, thay vì dùng file share làm kho trạng thái đồng thời.

### “Exactly once” không tự đến từ FileChannel

Thử tưởng tượng ứng dụng ghi bản ghi giao dịch rồi mất kết nối trước khi nhận xác nhận. Nó không thể chỉ dựa vào exception của Java để biết server **đã commit hay chưa**. Quy trình đúng thường dùng ID giao dịch ổn định và kiểm tra trạng thái server/manifest trước khi retry; file I/O thô không tự cung cấp exactly-once.

## 10. Sự khác nhau giữa NFS, SMB và các hệ file phân tán khác

**Không đồng nhất các hệ thống sau:**

| Loại hệ thống | Cần xác minh điều gì? |
|---|---|
| NFS (các phiên bản khác nhau) | Close-to-open, attribute/data caching, session/lock behavior, mount options, server commit semantics |
| SMB/CIFS | Oplock/lease, cache invalidation, share modes, durability và failover semantics của phiên bản triển khai |
| Cluster/distributed file system có coherence mạnh | Hợp đồng consistency, cross-client serialization, metadata transactions, failure behavior |
| Object storage được mount như filesystem | Provider/FUSE semantics: rename, locking, append, list consistency, sync/force có thể khác POSIX |
| Filesystem cục bộ | Vẫn cần xét atomicity, lock và durability, nhưng bảo đảm Java cho local force được xác định rõ hơn |

Không nên dùng những mẹo như luôn tắt cache hoặc mở lại file liên tục như một “giải pháp tổng quát”: chúng có thể rất tốn network I/O và vẫn không giải quyết được transaction hoặc partition. Chọn theo contract đã công bố của hệ lưu trữ.

## 11. Những lỗi phổ biến

| Ngộ nhận | Thực tế |
|---|---|
| “A ghi xong thì B lập tức đọc được bản mới” | Cache/client coherence có thể gây độ trễ; cần xác minh filesystem cụ thể. |
| “`Files.size()` luôn là độ dài mới nhất từ server” | Metadata cache và race có thể khiến kết quả không còn đúng tại lúc dùng. |
| “`force(true)` là durable trên mọi network drive” | Java chỉ đưa ra bảo đảm local storage; remote storage không được hứa tương tự. |
| “`rws/rwd` sẽ thay thế distributed transaction” | Chỉ là yêu cầu đồng bộ I/O, không cung cấp transaction/isolation. |
| “`FileLock` luôn khóa bắt buộc trên mọi máy” | Có thể advisory, phụ thuộc triển khai và hỗ trợ server/client. |
| “Lấy FileLock là đủ, bất kể cache stale” | Cần phối hợp cache coherence, mở/đọc đúng phiên bản và xác minh ownership. |
| “Close-to-open có nghĩa mọi read qua handle cũ đều mới” | CTO chủ yếu liên quan ranh giới close/open và chính sách cache cụ thể. |
| “`ATOMIC_MOVE` chắc chắn hỗ trợ và bền vững trên mọi mount” | Có thể không hỗ trợ; atomic namespace không đồng nghĩa durability và cache visibility. |
| “Timestamp và size là version chắc chắn” | Có thể trùng, bị cache, khác độ phân giải hoặc thay đổi giữa kiểm tra và sử dụng. |
| “Một lần đọc đúng từ client B đã chứng minh crash safety” | Đó chỉ là bằng chứng visibility ở một thời điểm, không phải thử nghiệm crash/durability. |
| “Ghi nhiều file có thể commit đồng thời chỉ bằng rename” | Rename từng file không tạo transaction xuyên file. |
| “Network timeout chắc chắn ghi thất bại” | Có thể server đã xử lý và chỉ mất phản hồi; cần idempotency/verification. |

## 12. Checklist thiết kế ứng dụng dùng shared file

1. **Xác định consistency contract:** ứng dụng chấp nhận eventual/close-to-open hay thực sự cần linearizable read/write?
2. **Xác định durability contract:** server xác nhận đến cache, ổ lưu trữ hay replica/quorum? Nếu mất server có phục hồi không?
3. **Xác định owner/writer policy:** một writer duy nhất hay nhiều writer cạnh tranh? File locks có hoạt động xuyên toàn bộ client không?
4. **Quản lý version:** dùng version ID/checksum/manifest cho dữ liệu quan trọng; reader phát hiện stale/incomplete data.
5. **Publish an toàn:** cân nhắc file tạm + atomic move khi được hỗ trợ, cùng quy tắc force/directory durability của nền tảng.
6. **Xử lý lỗi có thể đã commit:** retry có giới hạn và idempotent; không tự suy ra trạng thái từ timeout.
7. **Thử nghiệm môi trường thật:** hai client riêng, mount options xác thực, fault injection/network partition/server restart khi có điều kiện.
8. **Cân nhắc công nghệ khác:** nếu cần transaction mạnh cho nhiều writer, một database hoặc coordination service có contract rõ thường dễ đảm bảo hơn raw shared file.

### Câu hỏi tự kiểm tra

1. A ghi file rồi gọi `FileChannel.force(true)` trên NFS. Theo Java 17, có thể khẳng định dữ liệu tồn tại sau mọi server crash không? **Không.** Bảo đảm local force không áp dụng tổng quát cho remote storage.
2. B giữ file mở lâu và đọc lại sau A cập nhật. Có chắc thấy bản mới nhờ CTO? **Không chắc.** Cần xét chính sách cache, close/open và filesystem.
3. `Files.exists()` trả `true` rồi ứng dụng mở file. File có chắc còn nguyên? **Không.** Có race giữa kiểm tra và dùng.
4. Có `FileLock` thì mọi tiến trình trên mọi nền tảng đều không thể sửa file? **Không.** Lock có thể advisory và hỗ trợ khác nhau.
5. `Files.move(temp,target,ATOMIC_MOVE)` có nghĩa nội dung bền vững sau mất điện? **Không.** Atomic move và durability là hai thuộc tính độc lập.
6. `force()` của `MappedByteBuffer` có thể được thay tổng quát bằng `FileChannel.force(true)`? **Không**, đặc tả FileChannel không bảo đảm force dirty mapped pages.
7. Nếu giao dịch gửi tới server báo timeout, có chắc chưa ghi? **Không.** Có thể chỉ mất phản hồi; cần kiểm tra version/ID trước khi retry.
8. Cần đảm bảo reader không dùng dữ liệu nhiều file bị trộn phiên bản. Một hướng thiết kế? **Versioned immutable files + manifest + checksum + publish theo protocol đã kiểm nghiệm.**
9. `noac` trên Linux NFS có đồng nghĩa tắt toàn bộ data cache và mọi race? **Không.**
10. Khi nào nên cân nhắc database/coordination service? **Khi cần transaction, ordering và isolation mạnh với nhiều writer hoặc nhiều failure domain.**

## 13. Tài liệu chính thức

- [Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): `force(boolean)`, `lock(...)`, đọc/ghi, phạm vi bảo đảm local/remote.
- [Java SE 17 — FileLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileLock.html): tính hệ thống, advisory/mandatory, shared/exclusive, đặc thù network filesystem.
- [Java SE 17 — RandomAccessFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/RandomAccessFile.html): `"rw"`, `"rwd"`, `"rws"` và đồng bộ trên thiết bị cục bộ.
- [Java SE 17 — MappedByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html): `force()` và giới hạn file trên non-local storage.
- [Java SE 17 — Files.move](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#move(java.nio.file.Path,java.nio.file.Path,java.nio.file.CopyOption...)): `ATOMIC_MOVE`, trường hợp không hỗ trợ và tính chất phụ thuộc provider.
- [Linux man-pages — nfs(5), Data and Metadata Coherence](https://man7.org/linux/man-pages/man5/nfs.5.html): cache, close-to-open, attribute cache và các mount options cụ thể của Linux NFS.
