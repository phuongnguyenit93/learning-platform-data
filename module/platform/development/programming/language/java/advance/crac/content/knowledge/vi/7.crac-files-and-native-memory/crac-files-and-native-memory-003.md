# Bộ đệm ghi, thao tác flush và nguy cơ mất hoặc lặp dữ liệu

Ứng dụng Java thường không ghi dữ liệu xuống đích ngay tại thời điểm gọi write(). Dữ liệu có thể đi qua nhiều lớp bộ đệm: buffer trong đối tượng Java, buffer của thư viện, bộ đệm của hệ điều hành, bộ đệm của thiết bị lưu trữ hoặc hàng đợi gửi dữ liệu của socket. Buffering giúp giảm số lần I/O và tăng throughput, nhưng khi dùng CRaC cần trả lời chính xác: tại thời điểm checkpoint, dữ liệu đang nằm ở lớp nào và đã được xác nhận ở đâu?

Nếu checkpoint được tạo khi vẫn còn dữ liệu chưa flush, dữ liệu đó có thể nằm trong trạng thái bộ nhớ được lưu lại. Sau restore, ứng dụng có thể tiếp tục ghi phần dữ liệu đang chờ. Nhưng nếu thao tác ghi đã đến hệ thống bên ngoài mà trạng thái tiến trình chưa ghi nhận thao tác hoàn tất, restore có thể thực hiện lại thao tác đó và tạo dữ liệu trùng. Ngược lại, nếu ứng dụng đánh dấu dữ liệu đã xử lý trước khi dữ liệu thực sự được ghi bền vững, restore có thể bỏ qua phần dữ liệu chưa được lưu và gây mất dữ liệu.

Vì vậy, cần hiểu chính xác ý nghĩa của flush(), phân biệt flush với ghi bền vững (*durability*), xác định owner của buffer và chọn một điểm checkpoint mà trạng thái trong bộ nhớ nhất quán với trạng thái ở hệ thống bên ngoài.

## 1. Vì sao ứng dụng dùng bộ đệm ghi?

Ghi từng byte hoặc từng record nhỏ trực tiếp xuống đích thường tạo nhiều lời gọi I/O. Mỗi lời gọi có chi phí chuyển đổi giữa user space và kernel, đồng bộ, syscall hoặc giao tiếp mạng. Buffering gom nhiều lần ghi nhỏ thành một lần ghi lớn hơn.

Ví dụ, một ứng dụng ghi 100.000 log record. Nếu mỗi record được ghi riêng, ứng dụng có thể thực hiện rất nhiều thao tác I/O nhỏ. Nếu gom các record vào buffer rồi ghi theo lô, số lần gọi I/O có thể giảm đáng kể.

Các lớp buffering thường gặp:

- BufferedOutputStream giữ byte trong bộ đệm Java trước khi ghi xuống stream bên dưới.
- BufferedWriter giữ ký tự trong bộ đệm, sau đó chuyển chúng qua encoder và stream bên dưới.
- BufferedReader chủ yếu buffer dữ liệu đọc; nó không phải bộ đệm ghi nhưng vẫn là trạng thái I/O cần xem xét khi checkpoint.
- ByteBuffer có thể giữ dữ liệu trong heap hoặc vùng nhớ direct/native khi làm việc với NIO.
- Thư viện logging, database driver, HTTP client và message producer có thể có buffer hoặc hàng đợi riêng.
- Hệ điều hành có page cache và các hàng đợi I/O trước khi dữ liệu đến thiết bị lưu trữ.
- Socket có send buffer ở phía kernel; giao thức ứng dụng phía nhận còn có thể buffer thêm.

Một lời gọi write() thành công vì thế không nhất thiết có nghĩa dữ liệu đã đến đích cuối cùng. Nó có thể chỉ có nghĩa dữ liệu đã được chép vào buffer của lớp hiện tại.

## 2. Đường đi của dữ liệu khi ghi

Với một file, đường đi khái quát có thể như sau:

```text
Mã nghiệp vụ
    |
    | write(record)
    v
Buffer trong Java (BufferedWriter / BufferedOutputStream)
    |
    | flush()
    v
Stream / encoder / FileChannel
    |
    | write xuống hệ điều hành
    v
Page cache của hệ điều hành
    |
    | force / sync và cơ chế filesystem
    v
Thiết bị lưu trữ
```

Với network, đường đi có dạng khác:

```text
Mã nghiệp vụ
    |
    v
Buffer của client / producer
    |
    | flush hoặc gửi request
    v
Socket send buffer của hệ điều hành
    |
    | TCP truyền dữ liệu
    v
Socket receive buffer ở phía đích
    |
    v
Ứng dụng phía nhận xử lý và xác nhận
```

Hai sơ đồ chỉ ra rằng có nhiều ranh giới khác nhau. Dữ liệu được đẩy khỏi buffer Java chưa chắc đã được ghi bền vững trên đĩa; dữ liệu được đưa vào socket chưa chắc đã được ứng dụng phía nhận xử lý hoặc commit.

## 3. write(), flush() và close() khác nhau thế nào?

### 3.1. write()

write() đưa dữ liệu vào stream hoặc channel. Với stream có buffering, dữ liệu có thể chỉ được chép vào buffer trong bộ nhớ. Với một số API, lời gọi có thể ghi trực tiếp xuống lớp thấp hơn, nhưng vẫn còn các lớp buffering tiếp theo.

Không nên suy luận rằng write() trả về thành công đồng nghĩa với dữ liệu đã bền vững. Hãy đọc hợp đồng của API cụ thể và xác định nó xác nhận ở tầng nào.

### 3.2. flush()

flush() yêu cầu lớp đang buffer đẩy dữ liệu đang chờ xuống stream hoặc đích bên dưới theo hợp đồng của API. Với BufferedOutputStream, thao tác này ghi byte còn trong buffer vào stream bên dưới rồi gọi flush() trên stream đó. Với BufferedWriter, thao tác này đẩy ký tự đang buffer qua writer bên dưới.

Điều quan trọng là flush() thường chỉ đảm bảo dữ liệu đã đi qua các buffer thuộc lớp Java đang gọi và được chuyển cho lớp thấp hơn. Nó không tự động bảo đảm dữ liệu đã được ghi bền vững trên thiết bị lưu trữ, cũng không bảo đảm ứng dụng từ xa đã xử lý dữ liệu.

### 3.3. close()

close() thường hoàn tất việc sử dụng stream, flush phần dữ liệu còn lại theo hợp đồng của stream rồi giải phóng tài nguyên. Sau khi đóng, stream thường không thể tiếp tục ghi.

Đóng stream có thể là hành động phù hợp trước checkpoint nếu tài nguyên cần được mở lại sau restore. Tuy nhiên, đóng một writer không thay thế việc kiểm tra durability. Nếu cần dữ liệu file bền vững, hãy flush rồi dùng API force/sync phù hợp trước khi đóng.

## 4. Flush không đồng nghĩa với durability

Đây là phân biệt quan trọng nhất khi xử lý dữ liệu file.

Với BufferedOutputStream hoặc BufferedWriter, gọi flush() đẩy dữ liệu còn trong buffer Java xuống stream bên dưới. Nếu đích là file, stream bên dưới thường chuyển dữ liệu cho hệ điều hành. Hệ điều hành có thể giữ dữ liệu trong page cache trước khi ghi xuống thiết bị.

Muốn yêu cầu dữ liệu file được đẩy xuống thiết bị lưu trữ, có thể cần gọi FileChannel.force(...) hoặc FileDescriptor.sync() sau khi flush. Các API này yêu cầu hệ điều hành đồng bộ dữ liệu đã sửa đổi theo hợp đồng của chúng. Mức bảo đảm cuối cùng vẫn phụ thuộc filesystem, thiết bị và cấu hình lưu trữ.

| Thao tác | Ý nghĩa điển hình | Điều không nên suy diễn |
|---|---|---|
| write() | Đưa dữ liệu vào stream hoặc channel | Dữ liệu đã ra khỏi mọi buffer |
| flush() | Đẩy dữ liệu đang chờ ở buffer của lớp hiện tại xuống lớp dưới | Dữ liệu đã bền vững trên thiết bị hoặc đã được ứng dụng từ xa xử lý |
| FileChannel.force(false) | Yêu cầu đồng bộ nội dung file đã sửa đổi với thiết bị lưu trữ theo hợp đồng API | Mọi metadata liên quan đều đã được đồng bộ |
| FileChannel.force(true) | Yêu cầu đồng bộ nội dung và metadata file đã sửa đổi | Có thể thay thế mọi giao thức commit của ứng dụng |
| FileDescriptor.sync() | Yêu cầu đồng bộ dữ liệu và thuộc tính file đã sửa đổi xuống thiết bị | Giao dịch nghiệp vụ hoặc dữ liệu ở hệ thống khác đã commit |
| ACK của ứng dụng từ xa | Phía nhận xác nhận theo giao thức ứng dụng | ACK luôn có nghĩa dữ liệu đã được lưu bền vững; cần đọc hợp đồng của phía nhận |

Ví dụ ghi file bằng BufferedOutputStream:

```java
import java.io.BufferedOutputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

Path path = Path.of("events.log");

try (FileOutputStream file = new FileOutputStream(path.toFile(), true);
     BufferedOutputStream out = new BufferedOutputStream(file)) {

    byte[] record = "order-created".getBytes(StandardCharsets.UTF_8);
    out.write(record);
    out.write('\n');

    // Đẩy dữ liệu khỏi buffer của BufferedOutputStream.
    out.flush();

    // Yêu cầu đồng bộ dữ liệu/thuộc tính file đã sửa đổi.
    file.getFD().sync();
}
```

Trong ví dụ, flush() chuyển byte đang buffer xuống FileOutputStream. sync() yêu cầu đồng bộ file. Nếu bỏ sync(), dữ liệu có thể vẫn còn trong page cache của hệ điều hành sau khi flush() trả về. sync() có chi phí I/O và có thể làm giảm throughput, vì vậy ứng dụng cần chọn ranh giới durability phù hợp thay vì gọi sau mọi byte.

Với NIO, có thể dùng FileChannel.force(true) sau khi ghi. Nếu writer được bọc trên một channel, cần bảo đảm writer đã flush trước khi gọi force() để byte còn trong buffer ký tự hoặc byte được chuyển xuống channel.

## 5. Flush trên network có ý nghĩa gì?

Với socket, flush() thường đẩy dữ liệu khỏi buffer của stream Java xuống socket hoặc lớp network bên dưới. Dữ liệu vẫn có thể nằm trong send buffer của kernel, đang được TCP truyền, hoặc đã đến máy đích nhưng chưa được ứng dụng phía nhận đọc.

TCP acknowledgement xác nhận việc nhận dữ liệu ở tầng TCP theo cơ chế của giao thức. Nó không nhất thiết xác nhận rằng ứng dụng phía nhận đã xử lý record, ghi database hoặc commit giao dịch.

Nếu yêu cầu là “message đã được hệ thống nhận và xử lý”, ứng dụng cần một ACK ở tầng giao thức nghiệp vụ. ACK nên mang ý nghĩa rõ ràng, ví dụ message ID đã được lưu bền vững hoặc transaction đã commit. Chỉ sau khi nhận ACK đúng hợp đồng, producer mới nên đánh dấu message đã hoàn tất.

Với message broker hoặc client bất đồng bộ, phương thức flush() có thể có nghĩa khác nhau giữa thư viện. Có client dùng nó để chờ các request gửi đang chờ hoàn tất; có client chỉ đẩy buffer nội bộ ra network. Hãy kiểm tra tài liệu của đúng client và cấu hình broker. Không áp dụng ý nghĩa của OutputStream.flush() cho mọi phương thức cùng tên.

## 6. Bộ đệm ghi ảnh hưởng đến checkpoint như thế nào?

CRaC lưu trạng thái tiến trình tại một điểm checkpoint. Buffer nằm trong heap Java có thể là một phần trạng thái bộ nhớ được lưu. Sau restore, ứng dụng có thể tiếp tục với dữ liệu vẫn đang chờ trong buffer, tùy tài nguyên và cách runtime hỗ trợ.

Điều này có thể hữu ích khi buffer chứa dữ liệu hợp lệ chưa cần gửi ngay. Nhưng nó cũng tạo rủi ro nếu tiến trình chuẩn bị checkpoint đã thực hiện một phần side effect bên ngoài mà chưa cập nhật trạng thái tương ứng trong bộ nhớ.

Ví dụ, ứng dụng có một BufferedWriter và một biến lastWrittenSequence:

```text
Buffer Java:       [record 101, record 102]
File bên ngoài:    đã có đến record 100
lastWrittenSequence = 100
```

Nếu checkpoint lưu buffer đang chờ, restore có thể ghi tiếp record 101 và 102. Đây có thể là hành vi đúng nếu file vẫn ở đúng vị trí và chưa có lần ghi nào khác. Nhưng nếu một phần dữ liệu đã được ghi xuống file mà trạng thái buffer hoặc vị trí ghi trong tiến trình không phản ánh chính xác kết quả bên ngoài, restore có thể ghi lặp hoặc tạo file không nhất quán.

Với nhiều loại tài nguyên, trạng thái bên ngoài không nằm hoàn toàn trong heap. File descriptor, socket, page cache và native buffer có quy tắc riêng. Không nên giả định rằng snapshot heap đồng nghĩa với việc mọi buffer ở kernel hoặc thiết bị cũng được snapshot theo cùng cách. Phải làm theo hướng dẫn của JDK CRaC, thư viện và nền tảng đang dùng.

## 7. Hai lỗi đối nghịch: mất dữ liệu và lặp dữ liệu

### 7.1. Mất dữ liệu

Mất dữ liệu có thể xảy ra khi ứng dụng ghi nhận tiến độ trong bộ nhớ trước khi dữ liệu thực sự được chuyển đến hoặc lưu bền vững ở đích.

Ví dụ:

1. Ứng dụng nhận record 205.
2. Ứng dụng tăng lastProcessedSequence lên 205.
3. Dữ liệu vẫn còn trong buffer Java, chưa flush.
4. Checkpoint được tạo và lưu lastProcessedSequence = 205.
5. Sau restore, ứng dụng tiếp tục từ record 206.
6. Record 205 chưa được ghi ra đích và không được gửi lại.

Trạng thái tiến độ đã đi trước dữ liệu thực tế. Đây là nguyên nhân tạo mất dữ liệu.

### 7.2. Lặp dữ liệu

Lặp dữ liệu xảy ra khi side effect bên ngoài đã thành công nhưng checkpoint lưu trạng thái tiến trình trước khi ghi nhận thành công đó.

Ví dụ:

1. Ứng dụng gửi record 205 đến hệ thống đích.
2. Hệ thống đích đã ghi record 205 thành công.
3. Ứng dụng chưa cập nhật lastProcessedSequence hoặc chưa lưu ACK vào trạng thái bền vững.
4. Checkpoint được tạo với trạng thái cũ.
5. Sau restore, ứng dụng gửi lại record 205.
6. Hệ thống đích nhận một thao tác trùng nếu không có cơ chế chống lặp.

Đây là vấn đề phổ biến khi một tiến trình phải phối hợp trạng thái trong bộ nhớ với side effect bên ngoài. Checkpoint không tự tạo giao dịch nguyên tử giữa heap Java và database, file hoặc broker.

### 7.3. Bảng so sánh

| Trình tự | Trạng thái được checkpoint | Kết quả có thể xảy ra |
|---|---|---|
| Đánh dấu hoàn tất trước khi dữ liệu được lưu | Tiến độ đã tăng, dữ liệu chưa được ghi | Mất dữ liệu |
| Dữ liệu bên ngoài đã ghi, tiến độ chưa được cập nhật | Đích đã có dữ liệu, tiến trình nghĩ chưa hoàn tất | Lặp dữ liệu khi restore gửi lại |
| Buffer còn dữ liệu và được giữ trong checkpoint | Dữ liệu đang chờ được snapshot cùng tiến trình | Có thể tiếp tục ghi; cần bảo đảm đích và vị trí ghi nhất quán |
| Buffer được flush và trạng thái được xác nhận trước checkpoint | Buffer rỗng, tiến độ phản ánh kết quả đã xác nhận | Dễ khôi phục nhất nếu tài nguyên được mở lại đúng cách |

## 8. Thiết kế điểm nhất quán trước checkpoint

Trước khi checkpoint, ứng dụng nên đi đến một trạng thái mà dữ liệu đang chờ, tiến độ xử lý và side effect bên ngoài có thể đối chiếu được.

Một quy trình quiesce cho luồng ghi có thể gồm:

1. Ngừng nhận công việc mới từ HTTP, queue hoặc scheduler.
2. Chờ các thao tác ghi đang chạy hoàn tất hoặc đưa về trạng thái có thể retry.
3. Chặn producer mới đưa dữ liệu vào buffer.
4. Flush buffer theo hợp đồng của stream/client.
5. Chờ ACK hoặc kết quả commit ở tầng ứng dụng nếu đích hỗ trợ.
6. Ghi tiến độ xử lý bền vững theo cùng quy tắc nhất quán.
7. Gọi force() hoặc sync() nếu yêu cầu durability của file cần điều đó.
8. Đóng hoặc chuẩn bị tạo lại tài nguyên I/O theo hướng dẫn CRaC.
9. Chỉ cho phép checkpoint sau khi tất cả owner báo đã sẵn sàng.

Không phải ứng dụng nào cũng cần force file hoặc chờ ACK của broker ở mọi checkpoint. Quy trình phải dựa trên yêu cầu dữ liệu: log có thể chấp nhận mất một lượng nhỏ dữ liệu; sổ cái tài chính hoặc event quan trọng có thể yêu cầu durability mạnh hơn. Điều quan trọng là xác định rõ mức bảo đảm và đặt checkpoint ở ranh giới phù hợp.

Nếu một thao tác flush hoặc commit thất bại, callback chuẩn bị checkpoint cần báo lỗi để quy trình checkpoint không tiếp tục như thể dữ liệu đã an toàn. Cần có log và metric cho lỗi này. Không được nuốt exception rồi để tiến trình checkpoint với trạng thái không rõ ràng.

## 9. CRaC Resource quản lý buffer và stream

CRaC API cung cấp org.crac.Resource với hai callback chính:

- beforeCheckpoint(...): chuẩn bị tài nguyên trước khi trạng thái tiến trình được lưu. Với tài nguyên ghi, owner có thể ngừng ghi mới, flush, force/sync nếu cần và đóng stream.
- afterRestore(...): tạo lại hoặc xác minh tài nguyên sau khi tiến trình được khôi phục. Với file, owner có thể mở lại file và khôi phục vị trí ghi theo thiết kế. Với network, owner thường tạo kết nối mới.

Ví dụ dưới đây minh họa một owner quản lý file append. Để đơn giản, lớp giả định một coordinator đã ngừng các producer và chờ các lời gọi ghi hoàn tất trước khi CRaC gọi beforeCheckpoint(...).

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.io.BufferedWriter;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.nio.channels.Channels;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.locks.ReentrantLock;

public final class CheckpointAwareFileWriter implements Resource {
    private final Path path;
    private final ReentrantLock lock = new ReentrantLock();
    private FileChannel channel;
    private BufferedWriter writer;

    public CheckpointAwareFileWriter(Path path) throws IOException {
        this.path = path;
        open();
        Core.getGlobalContext().register(this);
    }

    private void open() throws IOException {
        channel = FileChannel.open(path,
                StandardOpenOption.CREATE,
                StandardOpenOption.WRITE,
                StandardOpenOption.APPEND);
        writer = new BufferedWriter(new OutputStreamWriter(
                Channels.newOutputStream(channel), StandardCharsets.UTF_8));
    }

    public void writeRecord(String record) throws IOException {
        lock.lock();
        try {
            writer.write(record);
            writer.newLine();
        } finally {
            lock.unlock();
        }
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        lock.lock();
        try {
            if (writer != null) {
                writer.flush();
                channel.force(true);
                writer.close();
                writer = null;
                channel = null;
            }
        } finally {
            lock.unlock();
        }
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        lock.lock();
        try {
            open();
        } finally {
            lock.unlock();
        }
    }
}
```

Trong ví dụ, writer.flush() đẩy dữ liệu khỏi buffer ký tự xuống channel; channel.force(true) yêu cầu đồng bộ nội dung và metadata file đã sửa đổi; sau đó writer được đóng. Khi restore, file được mở lại ở chế độ append. Việc mở lại tránh phụ thuộc vào trạng thái stream cũ.

Đây là ví dụ khung, không phải một lớp ghi file hoàn chỉnh cho mọi ứng dụng. Trong hệ thống thực tế, cần bổ sung:

- Một cơ chế quiesce thực sự để ngăn producer gọi writeRecord() sau khi chuẩn bị checkpoint bắt đầu. Lock trong ví dụ chỉ tuần tự hóa các lời gọi đang chạy; nó không tự ngăn lời gọi mới sau khi callback trả về.
- Xử lý exception khi flush, force, close hoặc open thất bại. Nếu flush/force lỗi, không được đánh dấu dữ liệu là đã bền vững.
- Chính sách lưu vị trí hoặc sequence đã ghi để phát hiện record trùng và tiếp tục đúng điểm.
- Xác minh đường dẫn, mount và quyền file sau restore.
- Quy tắc nếu nhiều tiến trình restore cùng ghi file: dùng file riêng theo instance hoặc một cơ chế đồng bộ/append được thiết kế rõ ràng. Không để nhiều replica ghi chung một file chỉ vì chúng cùng bắt đầu từ một checkpoint.
- Cách xử lý nếu checkpoint thất bại sau khi callback đã flush và đóng writer. Ứng dụng cần có quy trình tiếp tục phục vụ hoặc khởi tạo lại tài nguyên theo lifecycle mà runtime hỗ trợ.

Nếu file có record nghiệp vụ quan trọng, nên dùng định dạng record có sequence hoặc ID duy nhất, có thể kiểm tra tính toàn vẹn và loại bỏ thao tác lặp khi khôi phục.

## 10. Ngăn ghi trùng bằng idempotency và sequence

Không phải lúc nào cũng có thể tạo một giao dịch nguyên tử giữa trạng thái tiến trình và hệ thống bên ngoài. Một cách thực tế là thiết kế thao tác ghi có thể thực hiện lại mà không tạo thêm tác dụng phụ.

### 10.1. Idempotency key

Mỗi thao tác có một ID ổn định. Khi hệ thống nhận lại cùng ID, nó nhận biết thao tác đã được xử lý và không áp dụng side effect lần thứ hai.

Ví dụ, một event có eventId ổn định. Database lưu event ID đã xử lý trong cùng giao dịch với thay đổi nghiệp vụ. Nếu tiến trình restore gửi lại event, database phát hiện ID đã tồn tại và trả kết quả phù hợp.

Idempotency cần được thực thi ở phía hệ thống đích hoặc trong một transaction có tính nhất quán. Chỉ lưu ID trong một biến heap rồi checkpoint không đủ vì biến đó có thể lệch với kết quả bên ngoài.

### 10.2. Sequence number và offset

Với luồng record có thứ tự, dùng sequence hoặc offset bền vững. Ứng dụng chỉ đánh dấu offset hoàn tất sau khi đích đã xác nhận thao tác theo hợp đồng. Khi restore, đọc offset đã commit từ nguồn bền vững và tiếp tục theo quy tắc của hệ thống.

Với nhiều consumer, việc cấp phát partition hoặc lease phải do broker hoặc coordinator quản lý. Không nên sao chép một offset trong heap rồi để nhiều tiến trình cùng tiếp tục từ cùng vị trí mà không có cơ chế phân chia công việc.

### 10.3. Transactional outbox hoặc giao dịch phù hợp

Khi cập nhật database và phát event cần nhất quán, có thể dùng transactional outbox: ghi thay đổi nghiệp vụ và bản ghi outbox trong cùng transaction database; một publisher đọc outbox và gửi event với ID ổn định. Publisher có thể gửi lại khi không chắc ACK đã đến, còn consumer xử lý idempotent.

Mô hình này không loại bỏ mọi khả năng lặp ở network, nhưng nó giúp kiểm soát lặp bằng ID và trạng thái bền vững. Tương tự, nếu hệ thống đích hỗ trợ transaction hoặc exactly-once semantics, cần hiểu rõ phạm vi và điều kiện của cơ chế đó trước khi dựa vào nó.

## 11. Buffer trong các loại tài nguyên khác nhau

### 11.1. File và writer

Với file, phân biệt buffer Java, page cache và thiết bị lưu trữ. Trước checkpoint, writer cần được quiesce; flush buffer; force/sync nếu yêu cầu durability; rồi đóng và mở lại sau restore khi phù hợp. Nếu file được nhiều tiến trình sử dụng, cần có quy tắc append, locking hoặc file riêng.

### 11.2. Logging framework

Logging framework có thể có async appender và queue riêng. Gọi flush() trên một stream không nhất thiết drain queue của logging framework. Cần dùng API shutdown/flush của đúng appender hoặc logger, chờ worker ghi log hoàn tất, và xác minh các lỗi ghi. Với log có thể chấp nhận mất một phần dữ liệu, mức durability có thể khác dữ liệu nghiệp vụ.

### 11.3. Message producer

Producer bất đồng bộ thường buffer message trước khi gửi. flush() có thể đợi các send đang chờ hoàn tất, nhưng ý nghĩa chính xác phụ thuộc client. Hãy chờ kết quả gửi hoặc ACK theo hợp đồng của broker trước khi checkpoint, và lưu offset/progress bền vững theo cách tránh mất hoặc gửi trùng. Sau restore, tạo lại producer nếu client hoặc socket cũ không được hỗ trợ.

### 11.4. HTTP client và socket

HTTP client có thể buffer request body, gộp request hoặc gửi bất đồng bộ. Chỉ gọi flush() không chứng minh server đã commit. Với request cần xác nhận, chờ response/ACK ở tầng ứng dụng. Trước checkpoint, hoàn tất hoặc hủy request đang chạy theo chính sách rõ ràng; sau restore, tạo client hoặc connection mới nếu cần.

### 11.5. Direct buffer và native memory

ByteBuffer.allocateDirect() dùng vùng nhớ direct thay vì mảng byte heap thông thường. Native library có thể duy trì buffer và con trỏ riêng. Những vùng nhớ này cần được xem xét theo hỗ trợ của JVM, CRaC và thư viện native. Không giả định mọi trạng thái native đều có lifecycle giống một đối tượng Java bình thường.

Với MappedByteBuffer, phương thức force() yêu cầu ghi các thay đổi của vùng nhớ ánh xạ xuống thiết bị lưu trữ theo hợp đồng API. Ứng dụng cần xác minh mapping, file và vị trí sau restore; không dựa vào việc một mapping cũ luôn hợp lệ trong môi trường mới.

## 12. Chính sách flush: khi nào và ở mức nào?

Flush thường xuyên làm giảm lượng dữ liệu có thể mất khi tiến trình gặp sự cố, nhưng có thể giảm throughput đáng kể. Flush quá thưa tăng hiệu năng ghi theo lô nhưng kéo dài khoảng thời gian dữ liệu còn nằm trong buffer.

Chọn chính sách theo loại dữ liệu:

| Loại dữ liệu | Chính sách thường cân nhắc | Lý do |
|---|---|---|
| Log chẩn đoán thông thường | Buffer theo lô hoặc theo thời gian; drain trước checkpoint | Cân bằng throughput và khả năng mất một lượng log nhỏ |
| Audit log quan trọng | Flush và durability theo ranh giới nghiệp vụ | Cần giảm nguy cơ mất sự kiện đã xác nhận |
| Giao dịch tài chính | Transaction bền vững và xác nhận commit | Không thể chỉ dựa vào buffer trong heap |
| File export có thể tạo lại | Flush theo lô, checkpoint tại ranh giới record | Có thể tái tạo khi thất bại nếu có nguồn dữ liệu gốc |
| Message producer | Chờ ACK hoặc completion theo hợp đồng client | Tránh đánh dấu hoàn tất khi broker chưa xác nhận |
| HTTP request có side effect | Chờ response nghiệp vụ và dùng idempotency key | Tránh gửi lại thao tác không rõ kết quả |

Một ứng dụng có thể flush theo số byte, số record, thời gian hoặc ranh giới transaction. Nhưng khi chuẩn bị checkpoint, chính sách cần có một thao tác drain/flush tường minh để bảo đảm dữ liệu không còn ở trạng thái không xác định.

## 13. Xử lý lỗi trong quá trình flush và checkpoint

Flush hoặc force có thể thất bại do disk full, I/O error, file descriptor đóng, quyền truy cập thay đổi hoặc thiết bị lưu trữ gặp sự cố. Với network, send hoặc ACK có thể timeout trong khi phía nhận đã xử lý một phần hoặc toàn bộ dữ liệu.

Khi kết quả không rõ ràng, không nên tự động kết luận rằng thao tác thất bại hoàn toàn. Ví dụ, timeout khi gửi request có thể xảy ra sau khi server đã commit nhưng response bị mất. Retry khi đó có thể tạo lặp nếu không có idempotency.

Một chính sách xử lý nên phân biệt:

- **Thất bại chắc chắn trước khi gửi:** Có thể retry vì đích chưa nhận dữ liệu, nếu API bảo đảm điều đó.
- **Thất bại trong khi gửi hoặc chờ ACK:** Kết quả có thể không xác định; tra cứu bằng operation ID hoặc retry idempotent.
- **Đích đã xác nhận, nhưng chưa ghi tiến độ:** Có nguy cơ gửi lại sau restore; cần deduplicate.
- **Tiến độ đã ghi nhưng dữ liệu chưa bền vững:** Có nguy cơ mất dữ liệu; chỉ cập nhật tiến độ sau điểm xác nhận phù hợp.
- **Flush/force thất bại trước checkpoint:** Không đánh dấu resource đã sẵn sàng; chặn checkpoint hoặc đưa ứng dụng về trạng thái phục hồi được.

Log lỗi nên có resource ID, operation ID, sequence, đích ghi và trạng thái xác nhận. Tránh ghi payload nhạy cảm vào log chỉ để debug lỗi I/O.

## 14. Quy trình chuẩn bị buffer trước checkpoint

Một quy trình tổng quát cho ứng dụng có nhiều luồng ghi:

```text
Yêu cầu chuẩn bị checkpoint
          |
          v
Ngừng nhận công việc mới
          |
          v
Drain request / message / job đang chạy
          |
          v
Chặn producer ghi thêm vào buffer
          |
          v
Flush từng buffer theo owner
          |
          v
Chờ ACK / commit ở tầng ứng dụng nếu cần
          |
          v
Force / sync file nếu yêu cầu durability
          |
          v
Đóng hoặc chuẩn bị lại tài nguyên I/O
          |
          v
Xác nhận trạng thái nhất quán
          |
          v
Cho phép checkpoint
```

Khi restore:

```text
Restore tiến trình
       |
       v
Tạo lại file handle / client / connection
       |
       v
Đọc lại cấu hình và tiến độ bền vững
       |
       v
Kiểm tra buffer rỗng hoặc trạng thái buffer hợp lệ
       |
       v
Khởi động producer / consumer / worker
       |
       v
Readiness thành công
```

Không nhất thiết mọi resource phải được đóng. Một số thư viện có tích hợp CRaC và quy trình riêng; hãy tuân thủ đúng hợp đồng của chúng. Điểm quan trọng là owner phải xác nhận buffer và side effect đã ở trạng thái có thể khôi phục.

## 15. Kiểm thử mất và lặp dữ liệu

Một bài kiểm thử checkpoint/restore nên kiểm tra cả kết quả ghi lẫn trạng thái tiến độ. Chỉ xác nhận tiến trình restore được là chưa đủ.

Một kịch bản thử đơn giản:

1. Tạo một nguồn phát record có ID tăng dần, ví dụ 1 đến 10.000.
2. Ghi record vào đích và lưu ID đã xác nhận theo cơ chế bền vững.
3. Yêu cầu ứng dụng quiesce và tạo checkpoint ở một ranh giới xác định.
4. Restore tiến trình từ ảnh.
5. Tiếp tục gửi phần record còn lại.
6. Đọc dữ liệu ở đích và kiểm tra ID bị thiếu, ID trùng, thứ tự và checksum.
7. Lặp lại với checkpoint xảy ra trong lúc buffer có dữ liệu, lúc đang chờ ACK và sau khi đích đã ghi nhưng trước khi tiến trình cập nhật progress.

Các trường hợp lỗi cần thử:

- Tạo lỗi I/O khi flush hoặc force.
- Làm gián đoạn kết nối sau khi server nhận request nhưng trước khi client nhận ACK.
- Làm database hoặc broker tạm thời không sẵn sàng sau restore.
- Dừng một tiến trình giữa lúc xử lý batch.
- Khôi phục nhiều instance từ cùng ảnh nếu hệ thống có mô hình multi-restore.
- Làm cho hai instance cùng nhận một record để kiểm tra idempotency và cơ chế phân chia công việc.

Các chỉ số nên thu thập gồm số record đã tạo, số record được xác nhận, số record thực tế ở đích, số ID trùng, số ID thiếu, số lần retry, thời gian flush/force và thời gian phục hồi resource.

## 16. Những sai lầm thường gặp

**Cho rằng flush() đồng nghĩa với ghi xuống đĩa.** Flush của stream Java thường đẩy dữ liệu xuống lớp bên dưới; với file, cần xem xét page cache và API force/sync nếu yêu cầu durability.

**Cho rằng flush socket đồng nghĩa server đã xử lý.** Dữ liệu có thể mới được đưa vào send buffer hoặc TCP. Hãy chờ ACK ở tầng ứng dụng nếu cần xác nhận xử lý.

**Checkpoint khi producer vẫn đang ghi.** Buffer có thể thay đổi trong lúc chuẩn bị checkpoint và trạng thái tiến độ khó nhất quán. Hãy ngừng producer, drain và phối hợp owner.

**Đánh dấu progress trước khi đích xác nhận.** Sau restore, ứng dụng có thể bỏ qua dữ liệu chưa được ghi. Chỉ cập nhật tiến độ theo điểm xác nhận bền vững đã định nghĩa.

**Gửi lại mà không có idempotency.** Nếu đích đã xử lý nhưng ACK bị mất, retry có thể tạo side effect trùng. Dùng operation ID ổn định và deduplication.

**Cho rằng buffer Java là toàn bộ trạng thái I/O.** Native buffer, kernel buffer, page cache và trạng thái dịch vụ ngoài có lifecycle riêng. Kiểm tra tất cả lớp liên quan.

**Nuốt lỗi trong callback.** Nếu flush hoặc force thất bại mà callback vẫn báo thành công, checkpoint có thể chứa trạng thái không nhất quán. Hãy truyền lỗi và chặn checkpoint theo chính sách.

**Gọi flush sau mỗi lần ghi mà không cân nhắc hiệu năng.** Điều này có thể làm giảm throughput. Chọn ranh giới flush theo loại dữ liệu và yêu cầu durability.

**Dùng chung file append cho nhiều tiến trình restore.** Nhiều tiến trình có thể ghi trùng hoặc tranh chấp offset. Dùng file riêng, khóa liên tiến trình hoặc hệ thống ghi tập trung được thiết kế cho concurrent writer.

## 17. Checklist cho buffer và thao tác ghi khi dùng CRaC

- [ ] Đã liệt kê buffer trong Java, thư viện, direct/native memory và hệ điều hành chưa?
- [ ] Đã xác định owner cho từng buffer, stream, channel và producer chưa?
- [ ] Đã biết write() và flush() của API cụ thể xác nhận ở tầng nào chưa?
- [ ] Đã phân biệt flush với force/sync và ACK ứng dụng chưa?
- [ ] Producer có được ngừng nhận dữ liệu mới trước checkpoint không?
- [ ] Các thao tác ghi đang chạy có được drain hoặc hoàn tất không?
- [ ] Buffer có được flush bởi đúng owner trước checkpoint không?
- [ ] Dữ liệu quan trọng có được force/sync hoặc commit theo yêu cầu durability không?
- [ ] Tiến độ xử lý chỉ được cập nhật sau điểm xác nhận phù hợp không?
- [ ] Thao tác ghi có ID hoặc sequence để phát hiện lặp không?
- [ ] Stream, channel và client được tạo lại hoặc xác minh sau restore chưa?
- [ ] Đã kiểm thử lỗi I/O, ACK timeout, mất dữ liệu và gửi lặp chưa?
- [ ] Readiness có chờ tài nguyên ghi và dependency thiết yếu phục hồi không?

## Kết luận

Bộ đệm ghi giúp Java giảm chi phí I/O nhưng tạo ra nhiều tầng trạng thái cần phối hợp khi checkpoint. write() có thể chỉ đưa dữ liệu vào buffer; flush() đẩy dữ liệu xuống lớp bên dưới; force hoặc sync yêu cầu đồng bộ file; còn ACK ở tầng ứng dụng mới có thể xác nhận hệ thống đích đã xử lý theo hợp đồng của nó. Các thao tác này không thể thay thế cho nhau.

Để tránh mất hoặc lặp dữ liệu, hãy xác định owner của từng buffer, ngừng producer và drain công việc trước checkpoint, flush và xác nhận theo yêu cầu, rồi lưu tiến độ ở một ranh giới nhất quán. Sau restore, tạo lại tài nguyên phù hợp, đọc tiến độ bền vững và dùng ID, sequence hoặc idempotency để xử lý trường hợp kết quả bên ngoài không rõ ràng. Khi dữ liệu trong bộ nhớ và trạng thái ở đích được phối hợp có chủ đích, CRaC có thể rút ngắn thời gian khởi động mà vẫn giữ được tính đúng đắn của luồng ghi.

