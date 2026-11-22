# Giới hạn đọc song song và thứ tự ghép kết quả với Java IO/NIO.2

Khi một tệp lớn cần được đọc và xử lý theo từng khối, ta có thể phân chia công việc cho nhiều luồng: khối đầu tiên đọc từ offset 0, khối tiếp theo từ offset `chunkSize`, v.v. Tuy nhiên, **đọc hoặc xử lý song song** không đồng nghĩa với **kết quả đến theo thứ tự gốc**. Khối ở cuối file có thể hoàn thành trước khối đầu; nếu ghi ngay theo thứ tự hoàn thành, dữ liệu đầu ra sẽ bị đảo chỗ.

Ngoài tính đúng đắn, đọc song song không giới hạn dễ sinh hàng nghìn tác vụ, nhiều buffer chứa dữ liệu và quá nhiều lời gọi IO cùng lúc. Thiết kế tốt phải đồng thời bảo đảm:

1. **Đúng phạm vi đọc:** mỗi khối đọc một khoảng byte xác định, không chồng lấp, không bỏ sót.
2. **Giới hạn tài nguyên:** giới hạn số tác vụ thực thi, số tác vụ đã gửi nhưng chưa tiêu thụ kết quả, lượng dữ liệu đệm và số file/channel mở.
3. **Ghép theo thứ tự:** kết quả được đưa vào đầu ra đúng chỉ số khối/offset, bất kể luồng nào xong trước.
4. **Xử lý lỗi và kết thúc:** lỗi đọc được truyền về phía điều phối; tài nguyên và tác vụ còn lại được dừng, không tiếp tục công bố một file đầu ra chưa hoàn chỉnh.

Bài này tập trung vào cơ chế Java 17+ dùng `FileChannel`, `ExecutorService`, `Future` và hàng đợi kết quả có giới hạn. Các nguyên tắc tương tự áp dụng cho việc tính checksum theo khối, giải mã/biến đổi khối độc lập hoặc ghép những phần đã xử lý.

## 1. Ba thứ tự khác nhau

Giả sử file có 4 khối:

```text
Tệp theo offset:
[0: AAAA] [1: BBBB] [2: CCCC] [3: DDDD]
```

Nếu hai worker cùng hoạt động, lịch chạy có thể là:

```text
Lệnh submit:        0 → 1 → 2 → 3
Lệnh hoàn thành:    1 → 0 → 3 → 2
Thứ tự phải ghi:    0 → 1 → 2 → 3
Kết quả đúng:       AAAABBBBCCCCDDDD
```

- **Submit order:** thứ tự gửi công việc vào executor; hoàn toàn không cam kết thứ tự hoàn thành.
- **Completion order:** thứ tự các tác vụ thực sự xong; phụ thuộc scheduler, tốc độ thiết bị, cache và thời lượng xử lý.
- **Output order:** thứ tự nghiệp vụ cần giữ; với ghép file thường là thứ tự offset tăng dần.

`Future.get()` chờ tác vụ cụ thể hoàn thành. Nếu lưu các future theo thứ tự khối rồi lần lượt `get()` và ghi, đầu ra có thể đúng thứ tự. Nếu dùng `ExecutorCompletionService.take()`, kết quả sẽ đến theo thứ tự hoàn thành, cần một cơ chế sắp/xếp lại trước khi ghép.

**Một sai lầm phổ biến:** `ExecutorService.submit` nhiều lần rồi cho mỗi tác vụ tự ghi vào cùng `OutputStream` bằng `out.write(data)`. Thứ tự ghi lúc đó do lịch chạy quyết định; ngay cả khi từng `write` không bị chen byte, các khối vẫn có thể đảo thứ tự.

## 2. Phân chia file theo vị trí byte

Với file kích thước `fileSize` byte và độ lớn khối `chunkSize > 0`, số khối là:

\[
\text{chunkCount}=\left\lceil\frac{\text{fileSize}}{\text{chunkSize}}\right\rceil.
\]

Khối `i` (bắt đầu từ 0) có:

- `offset = i * chunkSize` (dùng `long` cho vị trí file lớn).
- `length = min(chunkSize, fileSize - offset)`.
- Phạm vi byte là `[offset, offset + length)`, tức chứa đầu, không chứa cuối.

Ví dụ: file 15 byte, `chunkSize = 4` → bốn khối ở các offset 0, 4, 8, 12; độ dài lần lượt 4, 4, 4, 3. File rỗng có 0 khối; không tạo công việc đọc ngoài EOF.

Với `FileChannel.read(ByteBuffer dst, long position)`, `position` là vị trí byte **tuyệt đối**. Đây là API phù hợp để nhiều worker đọc các vùng riêng của cùng một channel mà không phải cạnh tranh trên vị trí đọc tuần tự của channel. Mỗi worker phải dùng **ByteBuffer riêng**, không chia sẻ `position/limit` của một buffer giữa các luồng.

Cần lưu ý:

- Một lời gọi `read` **không bảo đảm lấp đầy buffer**. Luôn lặp cho tới khi đủ byte của khối, gặp EOF, hoặc lỗi.
- `FileChannel.size()` và offset đầu vào phải khớp với **một file ổn định** trong lúc xử lý. Nếu bên khác truncate, append hoặc ghi đè file đang đọc, phép chia khối dựa trên kích thước ban đầu không còn là snapshot nhất quán.
- `FileChannel` có API an toàn để dùng giữa nhiều luồng theo hợp đồng của channel, nhưng việc gọi read song song **không bảo đảm tăng thông lượng**: provider, filesystem, cache, ổ HDD/SSD và tải I/O có thể giới hạn hoặc tuần tự hóa các thao tác.

Không nên chia byte tùy ý rồi gọi `new String(bytes, UTF_8)` cho **từng khối** nếu cần giữ nguyên ký tự: một code point UTF-8 có thể bị cắt giữa hai khối. Đọc/ghép byte trước khi giải mã, hoặc tự thiết kế cách chia tại ranh giới ký tự/dòng và decoder có trạng thái. Ví dụ bên dưới ghép **byte nguyên vẹn**; không biến đổi từng khối như văn bản.

## 3. Hai loại giới hạn song song khác nhau

`Executors.newFixedThreadPool(3)` giới hạn khoảng 3 tác vụ chạy đồng thời, nhưng **không tự giới hạn số lượng đã submit**: executor fixed pool sử dụng hàng đợi công việc có thể tăng rất lớn. Nếu chương trình tạo `Future` cho từng khối của file nhiều terabyte, bộ nhớ vẫn có thể tăng theo số lượng tác vụ dù chỉ có 3 worker đang chạy.

Cần tách hai tham số:

| Giới hạn | Mục đích | Ví dụ |
| --- | --- | --- |
| `WORKERS` | Số worker thực thi task cùng lúc, ảnh hưởng CPU, IOPS và mức cạnh tranh đọc | `2` |
| `MAX_IN_FLIGHT` | Số task đã submit nhưng chưa được lấy/ghi kết quả; giới hạn task queue, future và buffer chờ | `2` |
| `CHUNK_BYTES` | Kích thước bộ nhớ dữ liệu cho mỗi khối; ảnh hưởng số syscall và memory pressure | `4` trong demo, thường lớn hơn trong thực tế |

Với cách ghép byte có giới hạn, lượng byte của các khối đã submit mà còn chờ tiêu thụ xấp xỉ **`MAX_IN_FLIGHT × CHUNK_BYTES`** ở trạng thái xấu nhất, cộng buffer của `OutputStream`, cấu trúc task, buffer hệ thống và các thành phần xử lý khác. Đây là ước lượng theo ứng dụng, không phải giới hạn RSS chính xác của JVM.

Nếu mỗi task tạo thêm kết quả kích thước khác (ví dụ giải nén hoặc tạo nhiều đối tượng), phải ràng buộc **kích thước kết quả** nữa: giới hạn số tác vụ chưa chắc giới hạn tổng bộ nhớ nếu một tác vụ có thể tạo hàng gigabyte.

Cơ chế cấp việc hợp lý là **cửa sổ trượt**: chỉ submit khi số task chưa tiêu thụ nhỏ hơn `MAX_IN_FLIGHT`; nhận một kết quả theo thứ tự, ghi nó xuống output, bỏ dữ liệu của khối đó, rồi mới cấp chỗ cho một task mới. Khi đầu ra chậm, tốc độ đọc bị kéo xuống theo (*backpressure*), thay vì tích lũy vô hạn.

## 4. Ví dụ Java 17+ chạy được: đọc đồng thời, ghi theo offset

Chương trình dưới đây tạo file nguồn nhỏ để stdout xác định, sau đó copy qua nhiều lần đọc có vị trí tuyệt đối. Phương thức `copyOrdered` có thể dùng cùng mẫu cho file lớn; không cần giữ toàn bộ nội dung file trong RAM.

Tạo file `OrderedParallelRead.java`:

```java
import java.io.EOFException;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Deque;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class OrderedParallelRead {
    private static final int CHUNK_BYTES = 4;
    private static final int WORKERS = 2;
    private static final int MAX_IN_FLIGHT = 2;

    private record Block(long index, byte[] bytes) { }

    private static Block readBlock(
            FileChannel channel, long index, long offset, int length)
            throws IOException {
        ByteBuffer buffer = ByteBuffer.allocate(length);

        while (buffer.hasRemaining()) {
            long position = offset + buffer.position();
            int n = channel.read(buffer, position);
            if (n < 0) {
                throw new EOFException("File changed or ended early");
            }
            if (n == 0) {
                throw new IOException("No progress reading a file block");
            }
        }
        return new Block(index, buffer.array());
    }

    private static long copyOrdered(Path source, Path destination)
            throws Exception {
        // Tạo stream output bằng CREATE_NEW để không ghi đè file có sẵn.
        try (FileChannel channel =
                     FileChannel.open(source, StandardOpenOption.READ);
             OutputStream out = Files.newOutputStream(
                     destination, StandardOpenOption.CREATE_NEW,
                     StandardOpenOption.WRITE)) {

            ExecutorService executor =
                    Executors.newFixedThreadPool(WORKERS);
            Deque<Future<Block>> inFlight = new ArrayDeque<>();

            long fileSize = channel.size();
            long nextOffset = 0;
            long nextIndex = 0;
            long expectedIndex = 0;

            try {
                while (nextOffset < fileSize || !inFlight.isEmpty()) {

                    // Chỉ gửi thêm tác vụ khi cửa sổ còn chỗ.
                    while (nextOffset < fileSize
                            && inFlight.size() < MAX_IN_FLIGHT) {
                        final long offset = nextOffset;
                        final long index = nextIndex++;
                        final int length = (int) Math.min(
                                (long) CHUNK_BYTES, fileSize - nextOffset);

                        inFlight.addLast(executor.submit(
                                () -> readBlock(
                                        channel, index, offset, length)));
                        nextOffset += length;
                    }

                    // Future đầu hàng đợi là khối có index nhỏ nhất
                    // chưa được ghi. Chờ nó dù khối sau đã chạy xong.
                    Future<Block> oldest = inFlight.removeFirst();
                    Block block;
                    try {
                        block = oldest.get();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw e;
                    }

                    if (block.index() != expectedIndex) {
                        throw new IOException("Unexpected block order");
                    }
                    out.write(block.bytes());
                    expectedIndex++;
                }

                return expectedIndex;
            } finally {
                // Hủy phần chưa dùng nếu có lỗi; đóng pool khi hoàn tất.
                for (Future<Block> future : inFlight) {
                    future.cancel(true);
                }
                executor.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("ordered-read-");
        Path input = dir.resolve("source.bin");
        Path output = dir.resolve("copy.bin");

        Files.writeString(input, "ABCDEFGHIJKLMNO",
                StandardCharsets.UTF_8);

        long blocks = copyOrdered(input, output);

        System.out.println("blocks=" + blocks);
        System.out.println("output="
                + Files.readString(output, StandardCharsets.UTF_8));
        System.out.println("equal=" + Arrays.equals(
                Files.readAllBytes(input),
                Files.readAllBytes(output)));
    }
}
```

Biên dịch/chạy ở thư mục chứa file bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 OrderedParallelRead.java
java OrderedParallelRead
```

Stdout xác định:

```text
blocks=4
output=ABCDEFGHIJKLMNO
equal=true
```

**Vì sao kết quả đúng dù task hoàn thành đảo thứ tự?**

1. Task số 0 đọc 4 byte từ offset 0; số 1 đọc từ offset 4; tiếp theo là 8 và 12 (độ dài cuối chỉ 3 byte).
2. Mỗi `readBlock` tạo `ByteBuffer` riêng, lặp positional read cho tới khi đủ `length`, sau đó trả `Block(index, bytes)`.
3. `inFlight` lưu future **theo thứ tự submit**, cũng là thứ tự offset; chỉ có tối đa 2 future chưa tiêu thụ.
4. Consumer lấy `removeFirst().get()` và chỉ ghi khối có index đúng `expectedIndex`. Nếu khối 1 xong sớm hơn khối 0, nó nằm chờ; không được viết trước khối 0.
5. Dữ liệu từng khối được ghi xong trước khi mở chỗ nhận công việc tiếp theo; `OutputStream` chỉ có **một thread** viết, tránh tranh chấp vị trí output.
6. Dòng `Arrays.equals` chỉ dùng để chứng minh cho **fixture 15 byte**; với file lớn nên xác nhận bằng checksum dạng streaming, không dùng `Files.readAllBytes` cho cả file.

**Lưu ý về quản lý lỗi:** Ví dụ hủy các future còn trong cửa sổ và gọi `shutdownNow()` khi thoát. `cancel(true)` hoặc `shutdownNow()` chỉ yêu cầu ngắt, không bảo đảm task hoặc I/O đang chặn dừng tức thì. Trong hệ thống có yêu cầu dừng sạch, hãy đợi pool kết thúc bằng `awaitTermination` có timeout, xử lý cờ interrupted và bảo đảm không đóng tài nguyên mà task còn sử dụng. Trên thất bại, file output đã tạo có thể chỉ chứa phần đầu; không công bố file đó như thành phẩm.

Trong demo, hai tham số `CHUNK_BYTES=4` và `MAX_IN_FLIGHT=2` được cố ý chọn nhỏ để nhìn thấy số khối. Với dữ liệu lớn cần đo đạc trước khi chọn kích thước thực tế.

## 5. Vì sao không submit toàn bộ khối cùng lúc?

Một phương án dễ viết nhưng kém khả năng mở rộng:

```java
// Mã minh họa, không phải chương trình độc lập.
List<Future<byte[]>> futures = new ArrayList<>();
for (long offset = 0; offset < size; offset += chunkSize) {
    final long start = offset;
    futures.add(pool.submit(() -> readAt(start)));
}
for (Future<byte[]> f : futures) {
    output.write(f.get());
}
```

Cách này có thể **giữ đúng thứ tự output** vì duyệt future theo thứ tự, nhưng toàn bộ task và future đều được tạo ngay. Nếu không có giới hạn submit, hàng đợi của fixed thread pool, tham chiếu tới các `Future` và kết quả hoàn tất đang chờ có thể tăng theo kích thước file.

Các lỗi khác thường đi kèm: dùng `int` cho offset file lớn rồi overflow; `byte[] data = Files.readAllBytes(bigPath)` vô tình nạp cả file; tăng số luồng rất cao và làm thiết bị IO tranh chấp; ghi nhiều khối vào một `OutputStream` từ nhiều worker mà không có đánh số/điều phối.

Cửa sổ trượt trong ví dụ có thể làm tác vụ sau chờ vì tác vụ đầu tiên chậm (**head-of-line blocking**). Đây là lựa chọn đánh đổi để đầu ra giữ đúng thứ tự và bộ nhớ bị chặn bởi số khối tối đa. Nếu xử lý từng khối có thời gian rất lệch nhau, có thể cân nhắc kích thước khối đồng đều hơn, tách bước xử lý khỏi bước đọc, hoặc cơ chế cấp tín chỉ hợp lý.

## 6. Khi dùng CompletionService và bộ đệm sắp lại

`ExecutorCompletionService` hữu ích nếu muốn biết **task nào xong trước**, ví dụ phục vụ metric, chạy downstream độc lập hoặc giảm thời gian nhàn rỗi. Nhưng `take()` không trả theo chỉ số khối.

Mô hình ghép đúng khi nhận theo thứ tự hoàn thành:

```text
workers → completed Block(index, bytes)
                   ↓
        pendingByIndex (map)
                   ↓
nextExpected=0 → xuất khối 0 nếu sẵn có → tăng nextExpected
                   ↓
        tiếp tục xuất các khối liên tiếp đã có
```

Giữ `Map<Long, Block> pendingByIndex`, thêm kết quả theo `index`, chỉ ghi khi đã có `nextExpected`. Sau khi ghi, lấy các block nối tiếp đang chờ.

**Bẫy về giới hạn tài nguyên:** Nếu cứ nhận một completion rồi submit thêm một task mới, nhưng khối đầu đang chậm, `pendingByIndex` có thể phình ra vô hạn: tất cả các khối sau đã xong nhưng không khối nào được xuất. Phải giới hạn **tổng số task đã gửi nhưng chưa được ghi theo thứ tự** (bao gồm cả đang chạy, queued và đã hoàn thành trong reorder buffer). Chỉ hoàn lại một “slot” sau khi kết quả thực sự được tiêu thụ/ghi xong, không chỉ sau khi một task kết thúc.

Nếu mỗi khối được **ghi vào vị trí offset riêng** bằng `FileChannel.write(buffer, position)`, bước ghép tuần tự về mặt vật lý có thể không cần thiết. Tuy nhiên khi đó phải bảo đảm khoảng ghi không chồng lấp, xử lý partial write, kích thước file đích, lỗi giữa chừng và xác nhận hoàn tất toàn bộ trước khi công bố file. Với định dạng nén/mã hóa có header chung hoặc biến đổi làm thay đổi độ dài mỗi khối, offset đầu ra không còn đơn giản bằng offset đầu vào.

## 7. Đọc theo dòng, ký tự và bản ghi: đừng lấy byte chunk làm ranh giới dữ liệu

Chia tệp byte thành những đoạn `64 KiB` có thể cắt đôi một ký tự UTF-8, một dòng CSV, một bản ghi có độ dài thay đổi hoặc một thông điệp trong log. Nếu worker giải mã độc lập từng đoạn, bạn có thể gặp ký tự thay thế, bản ghi bị chia đôi hoặc kết quả ghép không đúng về ngữ nghĩa.

Các hướng xử lý:

- **Cần bảo toàn file nhị phân:** đọc và ghép đúng byte theo offset; không giải mã từng khối. Đây là yêu cầu/thiết kế của ví dụ.
- **Cần xử lý từng dòng:** dùng một reader tuần tự chịu trách nhiệm phân tách dòng hoàn chỉnh rồi gửi **batch các dòng/bản ghi** cho worker. Đánh số batch, giới hạn queue/in-flight và phát kết quả theo batch index; tránh dùng một `BufferedReader` chung cho nhiều luồng gọi `readLine` không điều phối.
- **Cần chia file text tại offset:** đọc thêm một phần biên để tìm dấu kết thúc bản ghi hợp lệ, quy định rõ ai sở hữu byte của record nằm ở ranh giới; decoder UTF-8 phải xử lý byte multi-byte ở biên. Đừng tự cộng byte mù quáng và bỏ mất dữ liệu trùng.
- **Cần streaming từng record qua mạng:** phải xét backpressure, timeout, retry và semantic ordering của giao thức; “song song nội bộ” không tự có nghĩa là response luôn đúng thứ tự.
- **Cần parallel Stream:** `Files.lines(path)` trả `Stream<String>` và phải được đóng; `parallel()` không thay thế chính sách giới hạn bộ nhớ/IO của bài toán. `forEach` không giữ encounter order, còn `forEachOrdered` có bảo đảm thứ tự phần tử nhưng có thể hạn chế concurrency và không tự bảo đảm bounded buffering cho pipeline tùy biến.

Ngay cả khi dữ liệu là text, đôi khi tách “đọc tuần tự + xử lý CPU song song + ghép có thứ tự” đơn giản và hiệu quả hơn “nhiều luồng cùng seek/read text file”.

## 8. Xử lý lỗi, hủy tác vụ và xuất file nguyên tử

Với file quan trọng, đầu ra cần có một vòng đời rõ ràng:

1. Đọc metadata input đã được phê duyệt; nếu có thể, sử dụng snapshot/file bất biến trong thời gian xử lý. Không để tác vụ khác ghi/truncate cùng file.
2. Tạo **file tạm trong cùng filesystem/thư mục phù hợp**, không ghi trực tiếp vào tên đích được công bố.
3. Chỉ có một coordinator quản lý submit và output order. Mọi worker trả kết quả hoặc lỗi; không âm thầm nuốt exception.
4. Khi `Future.get()` ném `ExecutionException`, nguyên nhân gốc nằm ở `getCause()`. Dừng cấp việc, hủy tác vụ đang chờ và đưa hệ thống vào trạng thái lỗi. Với `InterruptedException`, phục hồi interrupt flag rồi thoát.
5. Chỉ khi tất cả block đã xử lý, `OutputStream` đóng thành công và các bước kiểm tra (ví dụ kích thước/checksum) đạt yêu cầu, mới công bố file tạm bằng move/rename. Nếu cần nguyên tử, kiểm tra hỗ trợ `Files.move(..., ATOMIC_MOVE)`; nền tảng có thể ném `AtomicMoveNotSupportedException`.
6. Nếu có lỗi, xóa file tạm chưa hoàn chỉnh theo chính sách; ghi log offset/index và nguyên nhân nhưng tránh lộ dữ liệu nhạy cảm. Có thể cân nhắc retry **tác vụ chỉ đọc idempotent** với số lần giới hạn khi input bất biến; không retry bừa bãi khi đang ghi side effect.

Ví dụ hoàn chỉnh ở mục 4 cố ý chưa xây protocol công bố file, checksum streaming hay retry. Nó minh họa cơ chế giới hạn và thứ tự; khi dùng trong hệ thống cần lưu trữ bền vững, phải thêm vòng đời output nói trên.

Một chi tiết quan trọng: nếu worker làm biến đổi không idempotent (ví dụ đếm/tăng trạng thái chung, gửi thông báo), retry sẽ có nguy cơ áp dụng tác dụng phụ hai lần. Phải tách phần tính toán thuần của khối khỏi phần commit có thứ tự, hoặc dùng cơ chế idempotency.

## 9. Chọn số luồng và kích thước khối theo đo đạc

Không có con số `WORKERS=8` hoặc `CHUNK_BYTES=1MiB` đúng cho mọi hệ thống.

- Với **HDD**, đọc tuần tự thường tốt hơn nhiều truy cập ngẫu nhiên; đọc song song cùng một ổ có thể tăng seek và làm chậm.
- Với **SSD/NVMe**, vài yêu cầu đọc đồng thời có thể cải thiện throughput, nhưng khi cache đã nóng hoặc giới hạn khác xuất hiện, thêm luồng không giúp.
- Nếu mỗi khối có **xử lý CPU nặng** độc lập, tách pool đọc IO khỏi pool CPU hoặc cân bằng tổng số worker theo profile. Nút thắt có thể là CPU, memory allocation/GC hoặc output disk thay vì input disk.
- Với **nhiều file khác nhau**, đọc song song theo file có thể cho lợi ích và cấu trúc đơn giản hơn so với chia một file thành vô số khối.
- Nếu output là một luồng tuần tự chậm, nó có thể là giới hạn tốc độ tổng thể; tăng số reader chỉ khiến kết quả chờ lâu hơn.
- Dùng `long` cho size/offset; giới hạn mỗi buffer byte[] ở cỡ vừa đủ (`int`), kiểm tra phép nhân/cộng khi tính offset của hàng tỉ block.

Các chỉ số cần đo là throughput (MiB/s), tổng thời gian, p95/p99 latency mỗi block, số task in-flight, tổng byte đang chờ, CPU, GC, số lượng context switch, mức sử dụng thiết bị IO và thời gian coordinator chờ khối đầu. Benchmark với file có kích thước đủ lớn, cache lạnh/nóng rõ ràng, dữ liệu thực tế và cùng điều kiện thử nghiệm. Đừng suy ra “nhiều worker hơn thì luôn nhanh hơn” chỉ từ ví dụ nhỏ.

Tùy nhu cầu, `AsynchronousFileChannel` có thể cung cấp API hoàn thành IO bất đồng bộ, nhưng callback/future vẫn có thể hoàn thành sai thứ tự offset và vẫn phải áp dụng giới hạn in-flight, reorder buffer, xử lý lỗi và close. Nó không xóa bỏ các yêu cầu trên.

## 10. Lỗi thường gặp và hướng sửa

| Triệu chứng | Nguyên nhân khả dĩ | Khắc phục |
| --- | --- | --- |
| Output chứa các khối đúng nhưng bị đảo | Ghi theo completion order hoặc worker cùng ghi `OutputStream` | Đánh số khối và ghép theo offset/sequence; dùng một writer |
| Vùng byte bị lặp hoặc mất | Tính offset/length sai, block cuối không đủ, dùng shared channel position không điều phối | Xác định khoảng `[offset, offset+length)`, đọc đủ byte với positional read |
| Chỉ có 2 worker nhưng heap vẫn tăng | Submit toàn bộ hàng triệu task/future hoặc lưu mọi kết quả | Dùng bounded in-flight window và ghi/giải phóng từng khối |
| File text bị lỗi ký tự ở biên | Giải mã UTF-8 theo chunk byte không căn chỉnh | Decode có trạng thái hoặc tách record trước khi xử lý |
| `Future.get()` treo lâu ở khối đầu | Khối đầu chậm hoặc blocked; head-of-line | Đặt timeout/cancellation policy, theo dõi metric, cân nhắc chiến lược scheduling |
| Kết quả thiếu cuối file | Chỉ đọc một lần rồi tưởng buffer đã đầy, hoặc dùng `int` tràn | Lặp đọc, xử lý EOF và dùng `long` offset |
| Copy đúng với file nhỏ nhưng sai khi nguồn thay đổi | File bị truncate/ghi đè khi đang đọc | Dùng input bất biến/snapshot, kiểm tra lỗi/validation |
| Output file bị bỏ dở khi một task thất bại | Ghi trực tiếp vào file công bố và không cleanup | Ghi temp, commit sau thành công, xử lý fail và cleanup |
| Thêm luồng khiến đọc chậm hơn | IO contention, seek, cache pressure hoặc output là bottleneck | Đo trên thiết bị thật; thử tuần tự và thay đổi worker/chunk có kiểm soát |

## 11. Câu hỏi tự kiểm tra

1. File 10 byte, chunk size 4. Có bao nhiêu khối và độ dài từng khối? **3 khối**, lần lượt 4, 4, 2; offset 0, 4, 8.
2. Fixed thread pool 4 luồng có tự ngăn 1 triệu task được submit không? **Không.** Cần giới hạn in-flight/queue ngoài số luồng.
3. Task số 3 hoàn thành trước task số 2. Có thể nối byte của số 3 vào `OutputStream` ngay không? **Không**, nếu phải khôi phục thứ tự file và chưa có block 2.
4. Vì sao `channel.read(buffer, position)` phải chạy trong vòng lặp? **Một lần đọc có thể trả ít byte hơn yêu cầu.**
5. `CompletionService.take()` có tự trả kết quả theo thứ tự submit không? **Không**, nó trả tác vụ đã hoàn thành; cần đánh số và reorder nếu muốn ghép đúng.
6. Tăng số worker từ 2 lên 32 có chắc tăng throughput file lớn không? **Không.** Giới hạn có thể nằm ở thiết bị IO, cache, CPU, RAM/GC hoặc writer.
7. File văn bản UTF-8 có thể giải mã riêng từng block tùy ý không? **Không**, cần giữ trạng thái giải mã hoặc chia theo ranh giới record/ký tự hợp lệ.

**Tài liệu API chính thức:** Java SE 17 `java.nio.channels.FileChannel` (positional `read`/`write`), `java.nio.ByteBuffer`, `java.util.concurrent.ExecutorService`, `Future`, `ExecutorCompletionService`, `java.nio.file.Files` và `StandardOpenOption`.