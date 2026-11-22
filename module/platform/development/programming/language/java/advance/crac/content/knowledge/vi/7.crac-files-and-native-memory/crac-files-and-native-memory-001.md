# Đóng và mở lại InputStream, OutputStream và FileChannel

Trong ứng dụng Java, InputStream, OutputStream và FileChannel là những API thường dùng để đọc hoặc ghi dữ liệu. Khi ứng dụng hỗ trợ CRaC, các object này cần được xem xét theo vòng đời của tài nguyên mà chúng đại diện. Một stream hoặc channel đang mở có thể giữ file descriptor hay trạng thái I/O do hệ điều hành quản lý. Việc object Java vẫn còn trong heap sau restore không bảo đảm handle bên dưới vẫn hợp lệ.

Một cách xử lý phổ biến là đưa I/O về trạng thái an toàn trước checkpoint: dừng thao tác đang chạy, ghi hết dữ liệu cần ghi, lưu thông tin cần thiết để tiếp tục, rồi đóng stream hoặc channel. Sau restore, ứng dụng mở lại tài nguyên và khôi phục vị trí hoặc trạng thái đọc ghi theo thiết kế của mình.

Không phải mọi InputStream hay OutputStream đều có thể đóng rồi mở lại giống nhau. Cách phục hồi phụ thuộc nguồn dữ liệu, chế độ mở file, trạng thái buffer, vị trí đọc ghi và giao thức của hệ thống bên ngoài.

## 1. Vì sao cần đóng và mở lại tài nguyên I/O?

Một object stream hoặc channel thường là lớp Java đại diện cho tài nguyên bên dưới:

- FileInputStream và FileOutputStream thường sử dụng file descriptor để thao tác với file.
- BufferedInputStream và BufferedOutputStream giữ thêm dữ liệu đệm trong heap, đồng thời bọc một stream khác.
- FileChannel cung cấp thao tác đọc ghi theo vị trí và có thể giữ khóa file.
- Stream mạng có thể đại diện cho socket kết nối tới một peer ở xa.

Checkpoint lưu trạng thái tiến trình Java theo cơ chế của CRaC runtime. Trong khoảng thời gian tiến trình tạm dừng, file có thể bị thay đổi, một dịch vụ từ xa có thể đóng socket, quyền truy cập có thể thay đổi hoặc một handle có thể không được hỗ trợ khôi phục trong môi trường đang dùng.

Vì vậy, không nên suy luận rằng một trường Java khác null đồng nghĩa tài nguyên vẫn sử dụng được. Ví dụ:

~~~java
if (inputStream != null) {
    int value = inputStream.read();
}
~~~

Điều kiện trên chỉ kiểm tra tham chiếu Java. Nó không chứng minh file descriptor, socket hoặc trạng thái ở peer vẫn hợp lệ sau restore.

Đối với file, ứng dụng thường có thể mở lại bằng đường dẫn và chế độ truy cập. Đối với stream mạng, mở lại thường cần thực hiện lại giao thức kết nối, xác thực, subscription hoặc khôi phục offset. Một stream tổng quát không cung cấp khả năng phục hồi vị trí đọc ghi một cách tự động.

## 2. Nguyên tắc chung trước checkpoint và sau restore

Trước checkpoint, thành phần quản lý I/O cần phối hợp với tầng sử dụng để không có thread tiếp tục đọc hoặc ghi trong lúc handle bị đóng. Một quy trình thường gồm:

1. Ngừng nhận công việc mới có thể sử dụng stream hoặc channel.
2. Chờ thao tác đang chạy hoàn tất hoặc hủy theo quy tắc của ứng dụng.
3. Flush dữ liệu ghi đang nằm trong buffer.
4. Ghi nhận vị trí hoặc checkpoint logic cần thiết để tiếp tục.
5. Đóng stream/channel và giải phóng tham chiếu tới handle cũ.

Sau restore:

1. Đọc lại cấu hình, đường dẫn và quyền truy cập hiện tại.
2. Mở một stream/channel mới với đúng chế độ đọc hoặc ghi.
3. Khôi phục vị trí đọc ghi nếu nguồn dữ liệu hỗ trợ và ứng dụng có lưu vị trí đó.
4. Kiểm tra trạng thái file hoặc dịch vụ bên ngoài trước khi tiếp tục.
5. Chỉ cho phép công việc mới sau khi tài nguyên đã sẵn sàng.

CRaC API cung cấp Resource để ứng dụng tham gia vào hai giai đoạn này. Thành phần sở hữu tài nguyên có thể triển khai beforeCheckpoint để chuẩn bị và afterRestore để mở lại. Việc đóng và mở lại phải được thực hiện theo hướng dẫn của CRaC runtime và thư viện đang dùng; một số thư viện đã có tích hợp CRaC riêng.

## 3. Đóng và mở lại InputStream

### InputStream không có API vị trí tổng quát

InputStream cung cấp các thao tác đọc byte, nhưng không có phương thức chung để truy vấn vị trí hiện tại hoặc đặt lại vị trí tùy ý. Điều này có nghĩa ứng dụng không thể chỉ đóng một InputStream bất kỳ rồi mở lại và mặc định tiếp tục đúng byte đang đọc.

Với file, ứng dụng có thể chọn một trong các cách:

- Đọc lại từ đầu nếu dữ liệu nhỏ hoặc có thể xử lý lại an toàn.
- Theo dõi số byte logic đã tiêu thụ và mở lại file rồi bỏ qua đúng số byte cần thiết, nếu file ổn định và nguồn hỗ trợ cách tiếp cận đó.
- Dùng FileChannel để quản lý vị trí đọc rõ ràng.
- Dùng một định dạng record có offset hoặc checkpoint nghiệp vụ để tiếp tục tại ranh giới record.

Không dùng InputStream.available() để xác định vị trí đọc. available() chỉ ước lượng số byte có thể đọc mà không bị chặn; nó không trả về tổng kích thước file hay offset hiện tại.

### Mark và reset không phải cơ chế checkpoint bền vững

Một số InputStream hỗ trợ mark/reset. mark() đánh dấu vị trí có thể quay lại trong giới hạn do stream quy định; reset() quay về dấu đó nếu stream vẫn hỗ trợ và trạng thái chưa bị mất.

Không nên xem mark/reset là cách lưu vị trí để phục hồi sau khi đóng và mở lại stream:

- Mark thường chỉ có ý nghĩa trong cùng instance stream.
- Sau close, instance cũ không còn dùng để đọc tiếp.
- Stream có thể không hỗ trợ mark.
- Với BufferedInputStream, giới hạn read-ahead và trạng thái buffer ảnh hưởng tới việc reset.
- Với socket hoặc stream từ xa, peer có thể đã thay đổi trạng thái hoặc không cho phép phát lại dữ liệu.

Nếu cần tiếp tục sau restore, hãy lưu offset hoặc checkpoint logic ở một nơi phù hợp và xác minh nguồn dữ liệu vẫn tương ứng với offset đó.

### BufferedInputStream và vị trí logic

BufferedInputStream có thể đọc trước một vùng dữ liệu từ stream bên dưới rồi giữ trong buffer. Vì vậy, vị trí vật lý của file descriptor có thể đã tiến xa hơn vị trí mà ứng dụng thực sự tiêu thụ.

Ví dụ, ứng dụng mới xử lý 100 byte nhưng BufferedInputStream có thể đã đọc trước 8 KB từ file. Nếu lấy vị trí của file channel bên dưới và mở lại từ vị trí đó, ứng dụng có thể bỏ qua phần byte còn nằm trong buffer mà chưa được xử lý.

Muốn tiếp tục chính xác, cần lưu vị trí logic mà ứng dụng đã xử lý, thường là số byte đã tiêu thụ hoặc offset của record cuối cùng đã hoàn thành. Không lấy vị trí read-ahead của lớp buffer làm vị trí nghiệp vụ.

### Ví dụ: mở lại file input theo offset đã xử lý

Ví dụ dưới đây minh họa một file văn bản/nhị phân có thể đọc lại từ một offset byte đã được ứng dụng ghi nhận. Lớp quản lý lưu offset logic và tạo stream mới sau restore.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ResumableFileInput {
    private final Path path;
    private InputStream input;
    private long nextOffset;

    public ResumableFileInput(Path path) throws IOException {
        this.path = path;
        this.nextOffset = 0;
        openAtSavedOffset();
    }

    public synchronized int read() throws IOException {
        int value = input.read();
        if (value >= 0) {
            nextOffset++;
        }
        return value;
    }

    public synchronized void closeForCheckpoint() throws IOException {
        if (input != null) {
            input.close();
            input = null;
        }
    }

    public synchronized void reopenAfterRestore() throws IOException {
        openAtSavedOffset();
    }

    private void openAtSavedOffset() throws IOException {
        InputStream reopened = Files.newInputStream(path);
        try {
            long skipped = 0;
            while (skipped < nextOffset) {
                long count = reopened.skip(nextOffset - skipped);
                if (count == 0) {
                    if (reopened.read() < 0) {
                        throw new IOException(
                                "File ended before the saved offset");
                    }
                    count = 1;
                }
                skipped += count;
            }
            input = reopened;
        } catch (IOException | RuntimeException error) {
            reopened.close();
            throw error;
        }
    }
}
~~~

Đây là ví dụ minh họa cho nguồn file có thể mở lại và không bị thay đổi ngoài dự kiến. Trong ứng dụng thật:

- nextOffset phải đại diện cho byte mà nghiệp vụ đã xử lý thành công, không phải byte mà buffer đã đọc trước.
- Cần bảo đảm file vẫn là cùng một nội dung hoặc cùng phiên bản. Nếu file bị thay thế hay sửa trong thời gian checkpoint, offset cũ có thể trỏ tới dữ liệu khác.
- Nếu xử lý theo dòng hoặc record, nên lưu offset tại ranh giới record đã hoàn tất để tránh xử lý thiếu hoặc lặp một phần record.
- Với file lớn, bỏ qua từ đầu tới offset có thể tốn thời gian. FileChannel cho phép đặt position trực tiếp.

## 4. Đóng và mở lại OutputStream

### Flush trước khi close

OutputStream có thể được bọc bởi BufferedOutputStream hoặc một lớp buffer khác. Dữ liệu ứng dụng đã ghi có thể vẫn nằm trong buffer Java mà chưa được chuyển tới stream bên dưới.

Trước khi checkpoint:

- Ngừng thread ghi mới.
- Chờ thao tác ghi hiện tại hoàn tất.
- Gọi flush() để đẩy dữ liệu trong buffer xuống stream bên dưới.
- Nếu cần bảo đảm dữ liệu file được đồng bộ tới thiết bị lưu trữ, dùng cơ chế phù hợp như FileChannel.force hoặc API tương ứng của hệ thống.
- Đóng stream để giải phóng tài nguyên bên dưới.

flush() không đồng nghĩa mọi dữ liệu đã được ghi bền vững xuống thiết bị lưu trữ. Nó thường chỉ đẩy dữ liệu từ buffer của Java tới tầng tiếp theo. Độ bền cuối cùng còn phụ thuộc hệ điều hành, filesystem và thiết bị.

### Chọn đúng chế độ mở lại

Khi tạo OutputStream mới, chế độ mở file quyết định dữ liệu cũ có bị ghi đè hay không.

| Cách mở | Hành vi | Trường hợp sử dụng |
|---|---|---|
| Files.newOutputStream(path) với mặc định | Tạo mới hoặc truncate file hiện có | Ghi lại toàn bộ file từ đầu khi đó là chủ đích |
| Files.newOutputStream(path, CREATE, WRITE, APPEND) | Ghi nối vào cuối file | Log hoặc dữ liệu append-only |
| FileOutputStream(path, true) | Mở ở chế độ append | Ghi nối vào file |
| FileChannel với WRITE và CREATE | Mở để ghi, không tự truncate chỉ vì mở | Tiếp tục ghi theo position do ứng dụng quản lý |

Một lỗi phổ biến là mở lại file output bằng chế độ mặc định sau restore. Nếu file đã tồn tại, thao tác này có thể truncate nội dung trước checkpoint. Hãy chọn rõ CREATE, WRITE, APPEND hoặc TRUNCATE_EXISTING theo mục tiêu của ứng dụng.

### OutputStream không cung cấp vị trí ghi tổng quát

OutputStream không có API position. Với file append-only, mở lại bằng chế độ append giúp ghi tiếp vào cuối file mà không cần biết offset hiện tại. Với file cần ghi tại một vị trí cụ thể, FileChannel phù hợp hơn vì cung cấp position().

Nếu ứng dụng ghi record vào file, nên xác định ranh giới record và cách xử lý khi checkpoint xảy ra sau khi một phần record đã được ghi. Có thể dùng record framing, checksum, commit marker hoặc ghi file tạm rồi atomic move để giảm nguy cơ dữ liệu dở dang. Việc gửi lại record sau restore cần có idempotency hoặc cơ chế phát hiện trùng.

### Ví dụ: mở lại OutputStream ở chế độ append

~~~java
import java.io.BufferedOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class AppendFileOutput {
    private final Path path;
    private OutputStream output;

    public AppendFileOutput(Path path) throws IOException {
        this.path = path;
        open();
    }

    public synchronized void writeRecord(byte[] record)
            throws IOException {
        output.write(record);
        output.write('\n');
    }

    public synchronized void beforeCheckpoint() throws IOException {
        if (output != null) {
            output.flush();
            output.close();
            output = null;
        }
    }

    public synchronized void afterRestore() throws IOException {
        open();
    }

    private void open() throws IOException {
        OutputStream file = Files.newOutputStream(
                path,
                StandardOpenOption.CREATE,
                StandardOpenOption.WRITE,
                StandardOpenOption.APPEND);
        output = new BufferedOutputStream(file);
    }
}
~~~

Chế độ APPEND phù hợp với ví dụ ghi nối. Nó không giải quyết việc một record có thể chỉ được ghi một phần trước khi tiến trình checkpoint hoặc gặp lỗi. Ứng dụng cần định dạng record có thể phát hiện phần ghi chưa hoàn chỉnh và có quy tắc xử lý khi gửi lại.

Không nên đóng OutputStream trong khi thread khác đang ghi. Các phương thức đồng bộ hóa ở ví dụ chỉ bảo vệ những lời gọi đi qua cùng instance; ứng dụng vẫn cần điều phối các thread và dừng nhận công việc mới trước khi callback đóng stream.

## 5. Đóng và mở lại FileChannel

### FileChannel có vị trí đọc ghi rõ ràng

FileChannel cung cấp các thao tác đọc ghi trên file và hỗ trợ position():

- position() trả về vị trí hiện tại của channel.
- position(long) đặt vị trí hiện tại.
- size() trả về kích thước file.
- truncate(long) cắt file về kích thước chỉ định.
- force(boolean) yêu cầu đồng bộ các cập nhật của file tới thiết bị lưu trữ theo cam kết của hệ thống.
- close() đóng channel và giải phóng tài nguyên liên quan.

Sau khi close(), channel không thể được dùng để tiếp tục đọc hoặc ghi. Sau restore, ứng dụng cần mở một FileChannel mới rồi thiết lập lại position nếu muốn tiếp tục từ offset đã lưu.

### Lưu vị trí và mở lại channel

Một quy trình điển hình:

1. Dừng các thao tác đang đọc hoặc ghi.
2. Lưu channel.position() vào trạng thái của Resource.
3. Nếu có ghi dữ liệu, gọi force(true) khi yêu cầu độ bền dữ liệu cần thiết.
4. Đóng channel.
5. Sau restore, mở channel mới với các StandardOpenOption phù hợp.
6. Đặt position của channel mới về offset đã lưu.

Không dùng TRUNCATE_EXISTING nếu mục tiêu là tiếp tục file cũ. Chỉ dùng tùy chọn này khi muốn xóa nội dung cũ và ghi lại từ đầu.

### Ví dụ: Resource quản lý FileChannel

Ví dụ sau quản lý một channel đọc/ghi. Channel được đóng trước checkpoint; sau restore, channel mới được mở và đặt lại vị trí đã lưu.

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CheckpointFileChannel implements Resource {
    private final Path path;
    private FileChannel channel;
    private long savedPosition;

    public CheckpointFileChannel(Path path) throws IOException {
        this.path = path;
        this.savedPosition = 0;
        open();
        Core.getGlobalContext().register(this);
    }

    public synchronized int read(ByteBuffer destination)
            throws IOException {
        return channel.read(destination);
    }

    public synchronized int write(ByteBuffer source)
            throws IOException {
        return channel.write(source);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        if (channel != null && channel.isOpen()) {
            savedPosition = channel.position();
            channel.force(true);
            channel.close();
            channel = null;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        open();
        channel.position(savedPosition);
    }

    private void open() throws IOException {
        channel = FileChannel.open(
                path,
                StandardOpenOption.CREATE,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE);
    }
}
~~~

Trong ví dụ:

- Resource đăng ký chính instance sở hữu channel với global context.
- beforeCheckpoint lưu vị trí hiện tại, yêu cầu đồng bộ dữ liệu file rồi đóng channel.
- afterRestore mở channel mới và khôi phục position.
- CREATE, READ và WRITE cho phép tạo file nếu chưa tồn tại và mở file hiện có để đọc ghi. Không có TRUNCATE_EXISTING nên nội dung cũ không bị xóa chỉ vì mở lại.

force(true) được dùng ở đây để minh họa yêu cầu đồng bộ nội dung và metadata file. Ứng dụng chỉ nên trả chi phí đồng bộ này khi yêu cầu độ bền dữ liệu cần thiết; force có thể ảnh hưởng hiệu năng và vẫn chịu giới hạn của filesystem, thiết bị và nền tảng.

Ví dụ giả định chỉ có một luồng hoặc một bộ điều phối sử dụng channel tại một thời điểm. Nếu nhiều thread cùng đọc/ghi, phải dừng và drain chúng trước callback; chỉ synchronized trên các method của wrapper không bảo vệ những tham chiếu channel bị chia sẻ ở nơi khác.

## 6. Vị trí FileChannel không phải lúc nào cũng là vị trí nghiệp vụ

FileChannel.position() hữu ích khi ứng dụng trực tiếp đọc hoặc ghi qua channel. Tuy nhiên, vị trí này có thể không đại diện cho tiến độ nghiệp vụ nếu:

- Một lớp buffer đã đọc trước dữ liệu nhưng ứng dụng chưa xử lý.
- Ứng dụng ghi dữ liệu vào buffer riêng trước khi gửi xuống channel.
- Một record được ghi thành nhiều phần và checkpoint xảy ra giữa chừng.
- Nhiều thread cùng thao tác trên channel.
- Một tiến trình khác cũng sửa file trong khoảng thời gian checkpoint.

Ví dụ, channel đã đọc tới byte 4096 nhưng parser mới xử lý xong record kết thúc ở byte 3000. Nếu restore tại position 4096, phần dữ liệu từ byte 3000 đến 4095 có thể bị bỏ qua. Cần lưu offset của record đã xử lý thành công, hoặc bảo đảm buffer được tiêu thụ hoàn toàn trước khi lưu vị trí.

Tương tự với ghi dữ liệu: position là vị trí I/O, không phải bằng chứng rằng toàn bộ record đã được commit về mặt nghiệp vụ. Nếu record có thể ghi dở, cần định dạng cho phép phát hiện và khôi phục phần chưa hoàn chỉnh.

## 7. File lock và bộ nhớ ánh xạ

### FileLock

FileChannel có thể tạo FileLock để khóa một vùng file. File lock gắn với channel và tài nguyên hệ điều hành. Khi channel đóng, lock liên quan được giải phóng. Không giữ một object FileLock trong heap rồi giả định khóa vẫn còn hiệu lực sau restore.

Nếu cần tiếp tục thao tác độc quyền:

- Đóng channel và nhả lock trước checkpoint theo quy tắc của ứng dụng.
- Sau restore, mở channel mới.
- Yêu cầu khóa lại.
- Kiểm tra việc giành khóa có thành công hay không trước khi sửa file.

Một tiến trình khác có thể đã lấy khóa trong thời gian ứng dụng tạm dừng. Việc khôi phục object Java cũ không khôi phục quyền sở hữu khóa ở hệ điều hành.

### MappedByteBuffer

FileChannel.map() tạo vùng nhớ ánh xạ file thông qua MappedByteBuffer. Vùng ánh xạ có vòng đời và hành vi phụ thuộc JVM, hệ điều hành và cách triển khai checkpoint. Đóng FileChannel không nên được xem là bằng chứng rằng mọi vùng ánh xạ đã được giải phóng hoặc có thể được tạo lại an toàn.

Nếu ứng dụng sử dụng memory-mapped file, cần kiểm tra hỗ trợ của đúng CRaC runtime và nền tảng triển khai. Khi không có bảo đảm rõ ràng, nên thiết kế để kết thúc thao tác với vùng ánh xạ trước checkpoint và tạo mapping mới sau restore bằng channel mới. Cũng cần bảo đảm không có thread tiếp tục truy cập ByteBuffer cũ.

## 8. Những trường hợp không thể chỉ đóng rồi mở lại

### Stream từ socket hoặc dịch vụ từ xa

Đóng một stream mạng thường đóng kết nối hiện tại. Mở socket mới không có nghĩa phiên giao thức cũ được khôi phục. Ứng dụng có thể cần:

- Kết nối lại tới host hiện tại.
- Thực hiện lại TLS handshake và xác thực.
- Đăng ký lại subscription.
- Đọc offset hoặc sequence number đã xác nhận.
- Dùng acknowledgement, idempotency hoặc deduplication để xử lý message có thể được gửi lại.

Không nên lưu một InputStream hoặc OutputStream socket rồi dùng lại sau restore mà không xác minh kết nối.

### Stream từ tài nguyên một lần

Một số nguồn chỉ cho đọc một lần hoặc không hỗ trợ seek, ví dụ pipe, luồng dữ liệu trực tiếp hoặc response body của một request. Sau khi đóng, không có cách mở lại cùng byte tiếp theo nếu phía nguồn không cung cấp cơ chế resume.

Trong trường hợp đó, ứng dụng phải thiết kế checkpoint ở tầng giao thức hoặc tầng nghiệp vụ. Ví dụ, lưu message offset đã xác nhận, cursor có thể tái tạo hoặc token resume do dịch vụ cung cấp.

### ByteArrayInputStream và stream thuần trong heap

ByteArrayInputStream đọc từ một mảng byte trong heap và không giữ file descriptor. Nếu mảng byte và trạng thái đọc đều nằm trong heap, chúng thường được khôi phục cùng tiến trình. Không cần đóng/mở lại chỉ vì đó là InputStream.

Tương tự, cần phân biệt wrapper và nguồn bên dưới. BufferedInputStream bọc FileInputStream vẫn phụ thuộc file; wrapper bọc ByteArrayInputStream lại có vòng đời khác. Hãy xác định tài nguyên thực sự được sở hữu trước khi đăng ký Resource.

## 9. Đưa vòng đời I/O vào CRaC Resource

Một thành phần sở hữu stream hoặc channel có thể triển khai org.crac.Resource:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class MyIoResource implements Resource {
    public MyIoResource() {
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        // Dừng I/O, flush và đóng handle do thành phần sở hữu.
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        // Mở lại handle và khôi phục offset/trạng thái cần thiết.
    }
}
~~~

Đoạn mã chỉ minh họa cấu trúc callback. Logic thực tế phải xử lý đồng bộ với thread sử dụng I/O, lỗi mở lại và trạng thái tài nguyên chưa được tạo. Không đăng ký một Resource phụ nếu framework hoặc thư viện đã đăng ký Resource để quản lý cùng stream/channel.

Khi ứng dụng có nhiều file, có thể có một Resource cho mỗi thành phần sở hữu file hoặc một Resource quản lý tập tài nguyên có cùng vòng đời. Cần giữ ranh giới sở hữu rõ ràng để tránh hai callback cùng đóng một handle.

## 10. Những lỗi thường gặp

**Chỉ kiểm tra stream khác null rồi tiếp tục đọc.**

Tham chiếu còn tồn tại không chứng minh handle bên dưới hợp lệ. Sau restore, cần mở lại hoặc xác minh tài nguyên theo cơ chế hỗ trợ.

**Dùng available() làm offset.**

available() không trả về vị trí hiện tại. Hãy theo dõi offset logic hoặc dùng FileChannel khi cần truy cập theo vị trí.

**Dùng mark/reset để tiếp tục sau khi mở lại.**

Mark gắn với instance stream cũ và không phải checkpoint có thể phục hồi sau close. Lưu offset hoặc trạng thái nghiệp vụ độc lập.

**Quên flush trước khi đóng OutputStream.**

Dữ liệu còn trong buffer có thể chưa được chuyển xuống stream bên dưới. Dừng ghi, flush và đóng theo đúng thứ tự.

**Mở lại file output với chế độ mặc định.**

Chế độ mặc định có thể truncate file hiện tại. Chọn APPEND hoặc FileChannel với position phù hợp.

**Khôi phục position nhưng bỏ qua buffer.**

Vị trí vật lý của channel có thể khác vị trí logic ứng dụng đã xử lý. Lưu offset tại ranh giới dữ liệu đã hoàn tất.

**Giữ FileLock cũ qua restore.**

Channel đóng sẽ giải phóng lock. Mở channel mới và yêu cầu khóa lại trước khi sửa file.

**Đóng handle khi thread khác vẫn đang I/O.**

Thao tác đang chạy có thể lỗi hoặc ghi dữ liệu không hoàn chỉnh. Dừng nhận công việc mới và drain các thao tác hiện tại trước callback.

## 11. Checklist thiết kế và kiểm thử

Khi đưa I/O vào ứng dụng hỗ trợ CRaC, hãy xác định:

- Nguồn dữ liệu là file, bộ nhớ, socket hay dịch vụ từ xa?
- Stream/channel nào thực sự sở hữu tài nguyên bên dưới?
- Ai chịu trách nhiệm dừng thread và đóng handle?
- Có buffer đọc trước hoặc buffer ghi chưa flush không?
- Offset cần lưu là vị trí vật lý hay tiến độ nghiệp vụ?
- Sau restore, file có thể bị thay đổi bởi tiến trình khác không?
- Mở lại file cần READ, WRITE, CREATE, APPEND hay truncate?
- Có FileLock hoặc mapping cần tạo lại không?
- Nếu mở lại thất bại, ứng dụng có được phép nhận traffic không?
- Nếu một phần record đã ghi hoặc xử lý trước checkpoint, cách phát hiện và xử lý lặp là gì?

Nên kiểm thử trên đúng JDK/CRaC runtime, hệ điều hành và filesystem dự kiến triển khai. Bao gồm checkpoint khi file đang đọc, khi output buffer có dữ liệu, sau khi file hoặc dịch vụ bên ngoài thay đổi, và khi thao tác mở lại thất bại. Kiểm thử nhiều chu kỳ để phát hiện handle bị rò rỉ, stream mở trùng hoặc offset bị sai.

## 12. Kết luận

Đóng và mở lại InputStream, OutputStream và FileChannel là một phần của việc quản lý vòng đời I/O khi ứng dụng sử dụng CRaC. Trước checkpoint, ứng dụng cần dừng thao tác đang chạy, flush dữ liệu ghi, lưu tiến độ cần thiết và đóng handle phù hợp. Sau restore, ứng dụng tạo stream hoặc channel mới, chọn đúng chế độ mở và khôi phục offset dựa trên trạng thái nghiệp vụ.

InputStream và OutputStream không cung cấp API vị trí tổng quát; FileChannel có position rõ ràng nhưng vị trí I/O vẫn có thể khác tiến độ nghiệp vụ khi có buffer hoặc nhiều thread. Thiết kế an toàn cần hiểu nguồn dữ liệu, quyền sở hữu handle, chế độ mở file, buffer và khả năng resume của hệ thống bên ngoài.
