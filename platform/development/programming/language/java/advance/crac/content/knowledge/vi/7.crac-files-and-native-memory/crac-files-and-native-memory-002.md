# Lưu vị trí đọc ghi và kiểm tra nội dung tệp sau restore

Trong CRaC (Coordinated Restore at Checkpoint), tiến trình Java có thể được khôi phục từ một checkpoint image và tiếp tục công việc đang thực hiện. Nếu ứng dụng đọc hoặc ghi tệp, việc khôi phục cần giữ đúng vị trí xử lý và xác nhận dữ liệu trên đĩa vẫn phù hợp với trạng thái đã lưu trong bộ nhớ.

Một offset được lưu trong heap chỉ cho biết ứng dụng đã xử lý đến đâu tại thời điểm checkpoint. Nó không tự bảo đảm rằng tệp bên ngoài vẫn còn nguyên vẹn khi restore. Tệp có thể bị thay thế, rút ngắn, nối thêm hoặc sửa bởi một tiến trình khác trong khoảng thời gian ứng dụng ngừng chạy.

Vì vậy, quy trình cần phối hợp ba việc: đồng bộ dữ liệu đang ghi, lưu vị trí đọc/ghi ở một ranh giới an toàn, rồi mở lại và xác minh tệp trước khi tiếp tục sau restore.

## 1. Vị trí đọc ghi của tệp được biểu diễn như thế nào?

Java cung cấp nhiều API để đọc và ghi tệp. Cách lấy vị trí hiện tại phụ thuộc API đang sử dụng.

| API | Cách lấy vị trí | Đơn vị |
|---|---|---|
| FileChannel | position() | Byte |
| RandomAccessFile | getFilePointer() | Byte |
| InputStream | Không có API vị trí tổng quát | Cần tự theo dõi |
| BufferedReader | Không cung cấp vị trí byte chính xác | Cần tự theo dõi vị trí logic |
| BufferedInputStream | Không cung cấp offset tệp đáng tin cậy trực tiếp | Cần tính cả dữ liệu đã đọc trước vào buffer |

Với FileChannel, position() trả về vị trí byte hiện tại trong tệp. Sau một thao tác đọc hoặc ghi, vị trí thường được cập nhật theo số byte đã xử lý. Có thể đặt lại vị trí bằng position(long newPosition).

~~~java
try (FileChannel channel = FileChannel.open(
        Path.of("data.bin"),
        StandardOpenOption.READ,
        StandardOpenOption.WRITE)) {

    long offset = channel.position();

    channel.position(128);
    // Đọc hoặc ghi bắt đầu từ byte 128.
}
~~~

RandomAccessFile cung cấp getFilePointer() và seek(long position), cũng làm việc theo byte:

~~~java
try (RandomAccessFile file = new RandomAccessFile("data.bin", "rw")) {
    long offset = file.getFilePointer();

    file.seek(128);
    // Đọc hoặc ghi từ byte 128.
}
~~~

Offset là số byte tính từ đầu tệp, không phải số ký tự, số dòng hay số record đã xử lý. Phân biệt này đặc biệt quan trọng khi tệp chứa văn bản UTF-8 hoặc một định dạng có record độ dài thay đổi.

## 2. Vì sao phải lưu vị trí ở ranh giới an toàn?

Giả sử một worker đọc từng record từ tệp. Nếu checkpoint xảy ra giữa lúc xử lý một record, sau restore ứng dụng có thể:

- Đọc lại record đã xử lý và tạo kết quả trùng lặp.
- Bỏ qua phần còn lại của record.
- Tiếp tục từ giữa một ký tự UTF-8.
- Ghi lại một phần record khiến tệp đầu ra không còn đúng định dạng.

Ứng dụng nên chọn một **điểm tiếp tục (resume point)** có ý nghĩa nghiệp vụ, chẳng hạn:

- Byte đầu tiên của record tiếp theo chưa xử lý.
- Byte ngay sau record cuối cùng đã được commit.
- Vị trí bắt đầu của một block dữ liệu có checksum.
- Offset sau khi một batch ghi đã được flush và xác nhận.

Một trạng thái checkpoint có thể lưu:

~~~text
filePath          = /var/lib/myapp/input/events.dat
readOffset        = 1048576
lastRecordId      = 8200
expectedFileSize  = 2097152
expectedDigest    = ...
formatVersion     = 3
~~~

Các trường này là metadata ứng dụng. Chúng được lưu trong heap cùng checkpoint image nếu nằm trong trạng thái đối tượng được checkpoint. Nếu ứng dụng cần phục hồi độc lập với checkpoint image, metadata cũng có thể được lưu trong một manifest riêng với quy tắc ghi nguyên tử và đồng bộ phù hợp.

### Lưu offset sau khi hoàn tất record

Ví dụ một worker đọc record, xử lý và chỉ cập nhật offset sau khi công việc tương ứng đã hoàn tất:

~~~java
while (hasNextRecord()) {
    Record record = readNextRecord();

    process(record);
    commitResult(record);

    // Chỉ cập nhật sau khi record đã được xử lý/commit.
    savedOffset = nextRecordByteOffset();
}
~~~

Trong thực tế, việc đọc, xử lý và commit có thể liên quan đến nhiều hệ thống. Nếu kết quả đã được ghi vào database nhưng offset chưa được lưu, restore có thể xử lý lại record. Nếu offset được lưu trước khi kết quả được commit, restore có thể bỏ qua record chưa hoàn tất.

Cần chọn một quy tắc nhất quán, ví dụ ghi kết quả theo khóa idempotency, commit offset cùng transaction với kết quả, hoặc chấp nhận xử lý lại và khử trùng lặp. Lưu offset đơn thuần không tạo ra bảo đảm exactly-once.

## 3. Offset byte và buffer đọc

Một lỗi thường gặp là lấy vị trí FileChannel sau khi đọc qua BufferedReader hoặc BufferedInputStream rồi xem đó là vị trí logic mà ứng dụng đã xử lý.

Các lớp buffered đọc trước một vùng dữ liệu để giảm số lần truy cập hệ thống. Vì vậy, vị trí của nguồn bên dưới có thể đã đi xa hơn dữ liệu mà ứng dụng thực sự tiêu thụ.

Ví dụ:

~~~text
Nội dung tệp:
|---- record A ----|---- record B ----|---- record C ----|

Ứng dụng đã xử lý:
|---- record A ----|

Buffer có thể đã đọc:
|---- record A ----|---- record B ----|---- record C ----|
                                      ^
                         FileChannel.position() có thể ở đây
~~~

Nếu lưu vị trí channel trong tình huống này, sau restore ứng dụng có thể bắt đầu từ record D và bỏ qua B, C dù chúng chưa được xử lý.

Có ba cách giải quyết phổ biến:

1. Dùng FileChannel và tự quản lý offset logic tại ranh giới record.
2. Dùng một parser có khả năng báo số byte đã tiêu thụ, thay vì lấy vị trí của nguồn đã đọc trước.
3. Nếu cần giữ nguyên buffer, checkpoint cả trạng thái buffer và trạng thái decoder theo một thiết kế rõ ràng; cách này phức tạp hơn và dễ phụ thuộc vào chi tiết triển khai.

Với xử lý theo record, cách thứ nhất thường dễ kiểm soát nhất.

### UTF-8 và ký tự nhiều byte

Trong UTF-8, một ký tự có thể chiếm từ một đến bốn byte. Offset byte không tương đương chỉ số ký tự.

Ví dụ một chuỗi có dấu tiếng Việt có thể dùng nhiều byte cho mỗi ký tự. Nếu lưu offset giữa chuỗi byte của một ký tự, việc giải mã sau restore có thể gặp dữ liệu không hợp lệ hoặc ký tự bị thay thế.

Nên lưu offset tại ranh giới record hoặc ranh giới ký tự đã được xác định. Nếu định dạng dùng dấu xuống dòng làm phân cách, cần tính cả byte của ký tự xuống dòng theo cách tệp được tạo trên nền tảng đó. Với định dạng nhị phân, dùng chiều dài record và header để xác định ranh giới.

Nếu dùng CharsetDecoder, cần phối hợp cả byte còn trong input buffer và trạng thái decoder. Không thể chỉ khôi phục FileChannel.position() rồi giả định decoder đã ở trạng thái ban đầu của một ký tự mới.

## 4. Ghi tệp: flush, force và lưu write offset

Với thao tác ghi, ứng dụng phải đưa dữ liệu còn nằm trong buffer xuống channel trước khi lưu vị trí. Sau đó, nếu cần đảm bảo dữ liệu được đẩy xuống thiết bị lưu trữ, gọi FileChannel.force().

Ba thao tác có ý nghĩa khác nhau:

- flush() của BufferedWriter hoặc OutputStreamWriter đẩy dữ liệu từ buffer của lớp Java xuống stream bên dưới.
- FileChannel.force(true) yêu cầu cập nhật nội dung và metadata của tệp được ghi ra thiết bị lưu trữ theo bảo đảm của hệ thống.
- position() lấy offset hiện tại của channel.

Thứ tự thường dùng khi chuẩn bị checkpoint:

~~~text
Ngừng nhận batch ghi mới
        |
        v
Hoàn tất record đang ghi
        |
        v
Flush writer/buffer
        |
        v
FileChannel.force(true)
        |
        v
Lưu write offset và metadata
        |
        v
Đóng channel nếu chọn chiến lược mở lại sau restore
~~~

Ví dụ:

~~~java
writer.flush();

channel.force(true);

long committedOffset = channel.position();
long committedSize = channel.size();
~~~

Ví dụ này giả định writer và channel cùng sử dụng một channel bên dưới và không có thao tác ghi đồng thời khác. Nếu có nhiều writer hoặc nhiều thread, cần khóa hoặc drain chúng trước khi lấy offset.

force(true) không thay thế flush() của writer. Nếu dữ liệu vẫn nằm trong buffer của BufferedWriter, channel chưa nhận được các byte đó để force.

Nếu ứng dụng ghi bằng FileChannel trực tiếp và không có buffer ở tầng Java, có thể gọi force(true) sau batch ghi. Nếu chỉ cần đồng bộ nội dung mà không yêu cầu đồng bộ metadata, force(false) có thể phù hợp; lựa chọn phụ thuộc yêu cầu độ bền dữ liệu.

### Ghi append và xử lý dữ liệu thừa

Giả sử ứng dụng đang ghi nối tiếp vào file log và đã lưu committedOffset = 4096. Sau restore:

- Nếu kích thước tệp nhỏ hơn 4096, dữ liệu đã commit có thể bị mất hoặc tệp đã bị thay thế. Không được tiếp tục ghi một cách mù quáng.
- Nếu kích thước bằng 4096 và checksum phù hợp, có thể tiếp tục tại offset 4096.
- Nếu kích thước lớn hơn 4096, có dữ liệu xuất hiện sau checkpoint. Cần xác định dữ liệu đó thuộc một lần ghi đã commit, một tiến trình khác hay phần ghi dở.

Chỉ truncate về committedOffset khi ứng dụng sở hữu độc quyền tệp và chính sách dữ liệu xác định phần đuôi là dữ liệu chưa commit. Nếu có writer khác hoặc dữ liệu mới hợp lệ, truncate sẽ làm mất dữ liệu.

~~~java
if (channel.size() < committedOffset) {
    throw new IOException("File is shorter than committed offset");
}

if (channel.size() > committedOffset) {
    // Chỉ thực hiện nếu ứng dụng sở hữu độc quyền file
    // và đã xác định phần đuôi là dữ liệu chưa commit.
    channel.truncate(committedOffset);
}

channel.position(committedOffset);
~~~

Đối với tệp dữ liệu quan trọng, nên ghi theo batch có marker hoặc checksum để nhận biết record cuối đã hoàn tất. Một record bị ghi dở ở cuối tệp không nên được xem là dữ liệu đã commit.

## 5. Kiểm tra nội dung tệp sau restore

Checkpoint image lưu trạng thái tiến trình, còn tệp là tài nguyên bên ngoài. Trong khoảng thời gian từ checkpoint đến restore, tệp có thể bị thay đổi bởi:

- Một tiến trình khác.
- Một job xoay vòng log hoặc thay thế file.
- Một thao tác deploy hoặc đồng bộ dữ liệu.
- Một người dùng chỉnh sửa thủ công.
- Một hệ thống lưu trữ hoặc mount từ xa.

Vì vậy, sau restore cần xác minh tệp trước khi đặt lại vị trí và tiếp tục đọc/ghi.

### Kiểm tra kích thước

Lấy kích thước hiện tại:

~~~java
long currentSize = Files.size(path);
~~~

So sánh với kích thước đã lưu tại checkpoint. Kiểm tra này nhanh nhưng không phát hiện nội dung bị thay đổi mà kích thước không đổi.

### Kiểm tra thời gian sửa đổi và file identity

Có thể đọc thuộc tính:

~~~java
BasicFileAttributes attributes = Files.readAttributes(
    path,
    BasicFileAttributes.class
);

long size = attributes.size();
FileTime modified = attributes.lastModifiedTime();
Object fileKey = attributes.fileKey();
~~~

Các thuộc tính này giúp phát hiện nhiều trường hợp tệp đã bị thay thế hoặc chỉnh sửa. Tuy nhiên:

- lastModifiedTime có thể bị giữ nguyên hoặc độ phân giải thời gian không đủ.
- fileKey có thể không được filesystem cung cấp.
- fileKey không nhất thiết ổn định giữa các lần mount hoặc trên filesystem từ xa.

Do đó, metadata là tín hiệu bổ trợ; không nên dùng một mình để xác nhận nội dung.

### Kiểm tra checksum hoặc hash

Nếu cần xác minh nội dung, có thể tính SHA-256 của tệp tại checkpoint và so sánh sau restore.

~~~java
MessageDigest digest = MessageDigest.getInstance("SHA-256");

try (InputStream input = Files.newInputStream(path)) {
    byte[] buffer = new byte[8192];
    int count;

    while ((count = input.read(buffer)) != -1) {
        digest.update(buffer, 0, count);
    }
}

byte[] fileHash = digest.digest();
~~~

Cần lưu hash ở dạng byte hoặc chuỗi biểu diễn ổn định cùng checkpoint state. Sau restore, tính lại và so sánh bằng MessageDigest.isEqual() khi so sánh mảng byte.

Tính hash toàn bộ tệp có thể tốn thời gian với tệp lớn. Các lựa chọn khác:

- Hash phần dữ liệu đã commit.
- Hash block cuối cùng cùng offset và record ID.
- Dùng checksum theo từng block trong định dạng tệp.
- Kết hợp kích thước, file identity và checksum của vùng quan trọng.

Chọn mức kiểm tra theo giá trị dữ liệu và chi phí khởi động. Không bỏ qua kiểm tra chỉ vì tệp có cùng kích thước.

### Kiểm tra cấu trúc dữ liệu

Hash xác nhận byte có giống nhau hay không, nhưng không thay thế việc kiểm tra tính hợp lệ của định dạng. Sau restore, ứng dụng có thể cần:

- Xác nhận header và version của file.
- Xác nhận offset nằm tại ranh giới record.
- Kiểm tra record cuối đã hoàn chỉnh.
- Kiểm tra checksum của block hoặc record.
- Đối chiếu sequence number hoặc record ID với metadata đã lưu.

Nếu tệp bị thay đổi hợp lệ theo quy trình bên ngoài, ứng dụng cần chính sách reconcile thay vì mặc định coi mọi khác biệt là corruption.

## 6. Resource quản lý file qua checkpoint và restore

Một cách triển khai rõ ràng là tạo một Resource sở hữu FileChannel. Trước checkpoint, resource đồng bộ dữ liệu, lưu offset và metadata rồi đóng channel. Sau restore, resource mở lại tệp, xác minh nội dung và khôi phục vị trí.

Ví dụ dưới đây minh họa trường hợp đọc/ghi một tệp do ứng dụng sở hữu độc quyền. Hàm computeSha256() đại diện cho hàm tính SHA-256 của nội dung tệp.

~~~java
import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CheckpointFileResource implements Resource {
    private final Path path;
    private final boolean writable;

    private FileChannel channel;
    private long savedPosition;
    private long expectedSize;
    private byte[] expectedHash;
    private boolean closedForCheckpoint;

    public CheckpointFileResource(Path path, boolean writable)
            throws IOException {
        this.path = path;
        this.writable = writable;
        openChannel();
        Core.getGlobalContext().register(this);
    }

    private void openChannel() throws IOException {
        if (writable) {
            channel = FileChannel.open(
                path,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE
            );
        } else {
            channel = FileChannel.open(
                path,
                StandardOpenOption.READ
            );
        }
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        // Các writer/buffer bên ngoài phải được drain và flush
        // trước khi lấy position của channel.
        if (writable) {
            channel.force(true);
        }

        savedPosition = channel.position();
        expectedSize = channel.size();
        expectedHash = computeSha256(path);

        channel.close();
        closedForCheckpoint = true;
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        reopenAndValidate();
    }

    public synchronized void reopenAfterAbortedCheckpoint()
            throws Exception {
        if (closedForCheckpoint) {
            reopenAndValidate();
        }
    }

    private void reopenAndValidate() throws Exception {
        FileChannel reopened = null;

        try {
            if (writable) {
                reopened = FileChannel.open(
                    path,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE
                );
            } else {
                reopened = FileChannel.open(
                    path,
                    StandardOpenOption.READ
                );
            }

            if (reopened.size() != expectedSize) {
                throw new IOException("File size changed after checkpoint");
            }

            byte[] actualHash = computeSha256(path);
            if (!MessageDigest.isEqual(expectedHash, actualHash)) {
                throw new IOException("File content changed after checkpoint");
            }

            if (savedPosition < 0 || savedPosition > expectedSize) {
                throw new IOException("Saved file position is invalid");
            }

            reopened.position(savedPosition);
            channel = reopened;
            reopened = null;
            closedForCheckpoint = false;

        } finally {
            if (reopened != null) {
                reopened.close();
            }
        }
    }

    private byte[] computeSha256(Path file) throws Exception {
        // Đọc file theo block và trả về SHA-256.
        // Cần triển khai bằng MessageDigest và Files.newInputStream().
        throw new UnsupportedOperationException("Implement SHA-256");
    }
}
~~~

Đoạn code là khung minh họa, cần bổ sung implementation SHA-256 và chính sách đồng bộ writer. Trong mã thực tế, import MessageDigest và xử lý hash theo block. Nếu tệp lớn, thay hash toàn tệp bằng checksum theo block hoặc vùng dữ liệu cần bảo vệ.

Ví dụ cũng giả định channel là đường đọc/ghi duy nhất. Nếu một BufferedWriter hoặc OutputStreamWriter cùng ghi vào channel, phải flush chúng trước khi callback lấy vị trí và force. Không được để thread khác ghi trong lúc lưu metadata.

### Xử lý checkpoint bị hủy

Nếu beforeCheckpoint() đóng channel nhưng checkpoint sau đó bị hủy, afterRestore() không được gọi cho tiến trình ban đầu. Nếu ứng dụng gọi Core.checkpointRestore() trực tiếp, có thể bắt CheckpointException và gọi reopenAfterAbortedCheckpoint():

~~~java
try {
    Core.checkpointRestore();
} catch (CheckpointException failure) {
    try {
        fileResource.reopenAfterAbortedCheckpoint();
    } catch (Exception reopenFailure) {
        failure.addSuppressed(reopenFailure);
        markApplicationNotReady();
    }

    throw failure;
}
~~~

Nếu việc checkpoint được gửi trực tiếp bằng jcmd từ bên ngoài, luồng gọi API của ứng dụng không có khối catch này. Khi đó, cần chọn chiến lược resource phù hợp với khả năng phục hồi của runtime hoặc xây dựng cơ chế quản trị để ứng dụng tự điều phối checkpoint. Không giả định rằng afterRestore() sẽ chạy khi checkpoint bị hủy.

## 7. Lưu vị trí đọc và khôi phục từ byte offset

Ví dụ sau mô tả một reader dùng FileChannel và lưu offset sau mỗi record. Hàm readNextRecord() được giả định trả về một record hoàn chỉnh cùng offset byte kế tiếp.

~~~java
public final class RecordReader {
    private FileChannel channel;
    private long nextOffset;

    public RecordReader(FileChannel channel, long savedOffset)
            throws IOException {
        this.channel = channel;
        this.nextOffset = savedOffset;
        this.channel.position(savedOffset);
    }

    public void processNext() throws Exception {
        RecordWithOffset item = readNextRecord(channel);

        process(item.record());
        commit(item.record());

        // Cập nhật sau khi record đã được xử lý và commit.
        nextOffset = item.nextByteOffset();
    }

    public long checkpointOffset() {
        return nextOffset;
    }

    public void rebindChannel(FileChannel reopened) throws IOException {
        this.channel = reopened;
        this.channel.position(nextOffset);
    }
}
~~~

RecordWithOffset và readNextRecord() là kiểu và hàm minh họa. Parser thực tế phải xác định offset byte kế tiếp từ dữ liệu đã tiêu thụ, không lấy position của channel sau khi buffer đã đọc trước nhiều record.

Sau restore:

1. Mở lại đúng file.
2. Xác minh file và định dạng.
3. Kiểm tra nextOffset là ranh giới record hợp lệ.
4. Đặt channel.position(nextOffset).
5. Tiếp tục đọc record tiếp theo.

Nếu record đã được xử lý nhưng chưa commit kết quả, ứng dụng cần xử lý lại theo chính sách idempotency. Không đánh dấu offset đã hoàn tất trước khi kết quả được commit.

## 8. Lưu vị trí ghi và tiếp tục append

Với writer, cần lưu vị trí sau record cuối cùng đã được ghi đầy đủ và đồng bộ. Ví dụ:

~~~java
public final class AppendWriter {
    private FileChannel channel;
    private long committedOffset;

    public AppendWriter(FileChannel channel) throws IOException {
        this.channel = channel;
        this.committedOffset = channel.position();
    }

    public void append(byte[] record) throws IOException {
        ByteBuffer buffer = ByteBuffer.wrap(record);

        while (buffer.hasRemaining()) {
            channel.write(buffer);
        }

        channel.force(true);
        committedOffset = channel.position();
    }

    public long checkpointOffset() {
        return committedOffset;
    }

    public void rebindChannel(FileChannel reopened) throws IOException {
        this.channel = reopened;
        this.channel.position(committedOffset);
    }
}
~~~

Sau restore, mở lại tệp, kiểm tra kích thước và nội dung đến committedOffset, sau đó đặt channel về offset đó để tiếp tục ghi.

Nếu dữ liệu sau committedOffset có thể thuộc một tiến trình khác, không truncate tự động. Dùng lock file, lease hoặc cơ chế phối hợp giữa các writer để bảo đảm quyền sở hữu tệp.

Nếu nhiều instance cùng restore từ một checkpoint image và cùng ghi vào một file dùng chung, chúng có thể ghi đè hoặc nối dữ liệu cạnh tranh. Cần tệp riêng cho từng instance hoặc một giao thức đồng bộ ngoài tiến trình.

## 9. Quản lý tệp thay đổi trong khi ứng dụng được checkpoint

Có những tệp được phép thay đổi trong thời gian ứng dụng ngừng chạy. Ví dụ, một log đầu vào tiếp tục được hệ thống khác ghi thêm.

Không phải mọi thay đổi đều là lỗi. Cần định nghĩa chính sách theo vai trò của tệp:

| Loại tệp | Chính sách sau restore |
|---|---|
| Input bất biến | Yêu cầu hash/identity khớp; dừng nếu nội dung thay đổi |
| Input append-only | Xác minh phần đã đọc, sau đó tiếp tục đọc dữ liệu mới từ offset đã lưu |
| Output do ứng dụng sở hữu độc quyền | Xác minh phần đã commit; xử lý phần đuôi theo quy tắc commit |
| Shared output | Dùng lock/lease hoặc cơ chế ghi có điều phối; không tự truncate |
| Log được rotate | Tìm đúng file generation theo ID/inode hoặc manifest; không chỉ dựa vào tên path |

Với input append-only, kích thước hiện tại có thể lớn hơn kích thước checkpoint mà không phải lỗi. Ứng dụng cần xác minh prefix đã xử lý không đổi, sau đó tiếp tục từ savedOffset để đọc phần mới.

Nếu log đã rotate, đường dẫn cũ có thể trỏ tới file mới trong khi dữ liệu cũ được đổi tên. Nên lưu định danh generation hoặc thông tin file identity và dùng manifest của hệ thống log để tìm đúng file.

## 10. Ghi metadata checkpoint an toàn

Nếu offset và checksum nằm trong đối tượng Java được checkpoint, chúng sẽ đi cùng trạng thái heap của tiến trình. Tuy nhiên, có thể cần ghi metadata ra tệp riêng để hỗ trợ phục hồi, kiểm toán hoặc đối chiếu với dữ liệu bên ngoài.

Khi ghi manifest riêng, tránh cập nhật trực tiếp file metadata đang dùng. Một cách phổ biến là:

1. Ghi nội dung mới vào file tạm trong cùng filesystem.
2. Flush và force file tạm.
3. Đổi tên file tạm thành file manifest chính bằng thao tác atomic move nếu filesystem hỗ trợ.
4. Đồng bộ metadata thư mục nếu yêu cầu durability của hệ thống cần đến thao tác này và nền tảng cung cấp cách thực hiện.
5. Chỉ sau khi manifest được commit mới xem offset là checkpoint metadata hợp lệ.

Manifest có thể chứa:

~~~text
version=1
file=/var/lib/myapp/input/events.dat
offset=1048576
size=2097152
sha256=...
lastRecordId=8200
~~~

Khi restore, xác nhận version metadata, file path, offset, size, checksum và record ID. Nếu metadata không hợp lệ, chuyển ứng dụng sang trạng thái lỗi có kiểm soát thay vì đoán offset.

Nếu dùng manifest ngoài heap, cần phối hợp thời điểm commit manifest với thời điểm checkpoint image được tạo. Một manifest mới được ghi nhưng checkpoint thất bại có thể không khớp với trạng thái heap của tiến trình ban đầu. Có thể lưu generation ID hoặc checkpoint attempt ID để nhận biết manifest thuộc lần nào.

## 11. Lỗi thường gặp và cách xử lý

### Offset lớn hơn kích thước tệp

Nguyên nhân có thể là tệp bị truncate, thay thế hoặc metadata được lưu sai.

Cách xử lý: không seek rồi tiếp tục. Kiểm tra file identity, checksum, bản sao dự phòng hoặc nguồn dữ liệu. Chỉ khởi động lại từ đầu khi quy tắc nghiệp vụ cho phép.

### Offset hợp lệ nhưng nội dung đã thay đổi

Kích thước có thể không đổi trong khi byte bên trong bị sửa. So sánh hash hoặc checksum của vùng dữ liệu đã commit. Nếu không khớp, dừng đọc/ghi và xử lý như một phiên bản dữ liệu khác.

### Bỏ qua dữ liệu vì buffer đã đọc trước

Không lưu trực tiếp channel.position() sau khi parser đã đọc qua BufferedReader hoặc buffer lớn. Theo dõi offset logic của record đã commit hoặc khôi phục cả buffer/decoder state.

### Ghi thiếu dữ liệu do chưa flush

Nếu chỉ lưu offset mà chưa flush writer, dữ liệu còn trong buffer có thể không nằm trong tệp. Flush writer, force channel khi cần durability, rồi mới lưu offset đã commit.

### Dữ liệu đuôi bị ghi dở

Nếu lần ghi cuối chưa hoàn tất, restore có thể gặp record thiếu byte hoặc checksum sai. Dùng record length, marker hoặc checksum để nhận diện. Chỉ truncate phần đuôi khi ứng dụng sở hữu độc quyền tệp và biết chính xác offset commit.

### Tệp bị thay thế nhưng giữ nguyên tên

Path chỉ là tên định vị, không phải bằng chứng tệp vẫn là cùng một đối tượng. Kiểm tra file identity khi nền tảng cung cấp và xác minh nội dung bằng hash hoặc checksum.

### Channel đóng trước checkpoint nhưng checkpoint bị hủy

Nếu beforeCheckpoint() đóng channel, tiến trình cũ có thể tiếp tục sau checkpoint failure mà channel vẫn đóng. Với Core.checkpointRestore(), bắt CheckpointException và mở lại channel theo trạng thái đã lưu. Với jcmd bên ngoài, cần quy trình phục hồi phù hợp vì ứng dụng không bắt được exception trong luồng gọi API.

## 12. Quy trình thực hiện

Một quy trình đọc/ghi tệp qua CRaC có thể được tổ chức như sau.

### Trước checkpoint

1. Ngừng nhận công việc mới liên quan đến tệp.
2. Chờ các thao tác đọc/ghi đang chạy hoàn tất tại ranh giới record hoặc batch.
3. Flush writer và buffer.
4. Force dữ liệu nếu yêu cầu durability cần thiết.
5. Lưu offset byte đã commit.
6. Lưu kích thước, file identity, version và checksum phù hợp.
7. Đóng channel nếu chọn chiến lược mở lại sau restore.
8. Đăng ký Resource với CRaC để runtime gọi callback.

### Sau restore

1. Mở lại đúng đường dẫn hoặc tìm đúng file generation.
2. Kiểm tra kích thước và identity.
3. Xác minh checksum hoặc nội dung của vùng đã commit.
4. Xác nhận offset nằm trong giới hạn và ở ranh giới record hợp lệ.
5. Đặt lại channel.position(savedOffset).
6. Khởi tạo lại reader/writer và buffer ở trạng thái nhất quán.
7. Chỉ tiếp tục công việc sau khi mọi kiểm tra thành công.

### Khi kiểm tra thất bại

Không tiếp tục đọc/ghi bằng offset cũ nếu nội dung tệp không còn khớp. Ghi log thông tin file, offset, kích thước, generation và checksum; giữ ứng dụng ở trạng thái chưa sẵn sàng; sau đó chọn chính sách khôi phục như đọc lại từ nguồn, dùng bản sao hợp lệ hoặc yêu cầu vận hành xử lý.

## 13. Nguyên tắc cần ghi nhớ

- FileChannel.position() và RandomAccessFile.getFilePointer() biểu diễn vị trí theo byte.
- Không nhầm offset byte với số ký tự hoặc số record đã xử lý.
- Chọn offset tại ranh giới record hoặc batch đã commit.
- Buffer đọc trước có thể khiến vị trí channel vượt quá vị trí logic của ứng dụng.
- Flush writer trước khi lấy vị trí; dùng force() khi cần đồng bộ dữ liệu xuống storage.
- Lưu cả offset và metadata giúp phát hiện tệp bị thay đổi.
- Sau restore, mở lại tệp và xác minh nội dung trước khi seek và tiếp tục.
- Không truncate phần dữ liệu thừa nếu không sở hữu độc quyền tệp.
- Phân biệt checkpoint bị hủy với restore thành công để phục hồi channel đúng nhánh.
- Với tệp lớn hoặc append-only, xác minh theo block, prefix đã commit hoặc checksum record để giảm chi phí.
- Nếu nhiều instance cùng restore, cần điều phối quyền ghi hoặc dùng file riêng cho từng instance.

Việc lưu vị trí đọc ghi chỉ có ý nghĩa khi nó gắn với dữ liệu đã được xác minh và một ranh giới xử lý nhất quán. Khi ứng dụng flush dữ liệu, lưu offset đã commit, xác minh tệp sau restore và chỉ tiếp tục khi các điều kiện phù hợp, chu kỳ CRaC có thể tiếp tục công việc trên tệp mà không bỏ sót hoặc ghi trùng dữ liệu một cách âm thầm.
