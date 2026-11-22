# FileChannel: `transferTo`, `transferFrom` và xử lý số byte chuyển thực tế

## 1. Mục tiêu

`FileChannel` thuộc `java.nio.channels`, cho phép đọc/ghi, truy cập vị trí ngẫu nhiên và chuyển dữ liệu giữa channel. Hai phương thức `transferTo` và `transferFrom` đặc biệt hữu ích khi sao chép dữ liệu từ hoặc vào tệp mà không phải tự tổ chức vòng lặp `ByteBuffer` trong đường đi thông thường.

Điểm cần nhớ ngay: **giá trị `count` là số byte yêu cầu chuyển tối đa, không phải cam kết số byte thực sự đã chuyển**. Mỗi lần gọi trả về một giá trị `long` là **số byte đã chuyển thực tế**. Chương trình muốn chuyển đủ dữ liệu phải kiểm tra giá trị này, cập nhật độ lệch rồi gọi tiếp khi phù hợp.

Sau bài học, bạn có thể:

- Chọn chiều chuyển dữ liệu đúng giữa `transferTo` và `transferFrom`.
- Phân biệt tham số `position` với `FileChannel.position()` và vị trí của channel còn lại.
- Viết vòng lặp xử lý kết quả dương nhỏ hơn yêu cầu và kết quả 0.
- Giải thích giới hạn từ hệ điều hành, EOF, channel không chặn và các điều kiện cạnh tranh.
- Kiểm tra số byte, nội dung, đóng tài nguyên và phát hiện sao chép thiếu dữ liệu.

## 2. API và chiều dữ liệu

Hai chữ ký cốt lõi của Java NIO.2:

~~~java
// Phương thức instance của FileChannel:
long transferTo(long position, long count, WritableByteChannel target)
        throws IOException;

long transferFrom(ReadableByteChannel src, long position, long count)
        throws IOException;
~~~

Đây là **chữ ký API**, không phải một chương trình Java độc lập.

| Phương thức được gọi trên | Chiều dữ liệu | `position` thuộc về | Đối tượng channel còn lại |
| --- | --- | --- | --- |
| `sourceFile.transferTo(position, count, target)` | **Từ** tệp nguồn **đến** channel đích | Vị trí bắt đầu **trong tệp nguồn** `sourceFile` | `WritableByteChannel target` nhận dữ liệu |
| `destinationFile.transferFrom(src, position, count)` | **Từ** channel nguồn **vào** tệp đích | Vị trí bắt đầu **trong tệp đích** `destinationFile` | `ReadableByteChannel src` cung cấp dữ liệu |

Ví dụ sơ đồ:

~~~text
transferTo:
[FileChannel nguồn] --(position trong tệp nguồn, count)--> [WritableByteChannel đích]

transferFrom:
[ReadableByteChannel nguồn] --(count)--> [FileChannel đích ở position]
~~~

**Không hoán đổi ý nghĩa `position`:** Với `transferTo`, `position` là offset đọc; với `transferFrom`, `position` là offset ghi. Cả hai offset này dùng đơn vị **byte** tính từ đầu tệp, không phải chỉ số ký tự.

Các tham số `position` và `count` không được âm; giá trị âm gây `IllegalArgumentException`. Ngoài ra các phương thức có thể ném `IOException` khi truyền dữ liệu thất bại, `ClosedChannelException` khi channel cần thiết đã đóng, hoặc các ngoại lệ khác theo loại channel và trạng thái. Đừng chỉ dựa vào một loại exception duy nhất.

### Giá trị trả về có ý nghĩa gì?

~~~java
long actual = sourceFile.transferTo(offset, requested, target);
~~~

`actual` là lượng dữ liệu thực sự chuyển thành công trong **lần gọi đó**:

- `0 < actual < requested`: chỉ chuyển được một phần; có thể còn dữ liệu.
- `actual == requested`: lần gọi đã chuyển đủ đúng lượng yêu cầu.
- `actual == 0`: không có byte nào được chuyển trong lần này. **Không tự động suy ra đã tới EOF**, nhất là khi channel không chặn hoặc triển khai bị giới hạn.
- Kết quả chuyển thành công nằm trong `[0, requested]`; `actual` không phải tổng byte từ các lần gọi trước và không phải vị trí cuối cùng.

Nếu `requested == 0`, kết quả bằng 0 là bình thường. Khi `position` đọc của `transferTo` nằm ở hoặc vượt quá kích thước tệp hiện tại, cũng không còn byte tại vị trí đó để chuyển.

## 3. Vị trí tệp và vị trí channel sau lệnh chuyển

Điều này dễ gây lỗi hơn chính thao tác sao chép.

Với `source.transferTo(fromOffset, count, sink)`:

- `fromOffset` xác định điểm bắt đầu **đọc từ tệp nguồn**, độc lập với vị trí hiện tại của `source`.
- Lời gọi **không thay đổi** `source.position()`.
- Nếu `sink` là một channel có vị trí, chẳng hạn một `FileChannel`, dữ liệu được ghi từ vị trí hiện tại của `sink` và vị trí của `sink` tăng theo lượng dữ liệu ghi.
- Vì thế lần gọi tiếp theo phải truyền `fromOffset + actual` nếu cần nối tiếp vùng nguồn; gọi lại với cùng offset sẽ đọc lặp byte cũ.

Với `destination.transferFrom(src, toOffset, count)`:

- `toOffset` xác định nơi **ghi vào tệp đích**, độc lập với `destination.position()`.
- Lời gọi **không thay đổi** `destination.position()`.
- Nếu `src` có vị trí (ví dụ `FileChannel`), vị trí đọc của `src` thường tiến lên theo số byte đã đọc.
- Vì thế lần tiếp theo phải truyền `toOffset + actual` vào `transferFrom`; còn vị trí đọc của `src` thường đã được cập nhật và không cần tự tăng lần nữa.

| Thao tác | `position` của FileChannel được gọi | Vị trí của channel đối diện |
| --- | --- | --- |
| `fileSource.transferTo(...)` | **Không đổi** | Channel đích có vị trí sẽ tiến lên khi nhận byte |
| `fileDestination.transferFrom(...)` | **Không đổi** | Channel nguồn có vị trí sẽ tiến lên khi cung cấp byte |

**Ví dụ tính vị trí:** `source.transferTo(100, 40, target)` trả về 15. Lần sau muốn tiếp tục vùng nguồn phải gọi `source.transferTo(115, 25, target)`. Tương tự, `destination.transferFrom(src, 100, 40)` trả về 15 thì offset ghi tiếp là 115. Nếu channel đích ghi của `transferTo` đã được sử dụng trước đó, hãy đặt `target.position(...)` theo mục tiêu thật sự trước khi bắt đầu sao chép.

## 4. Tại sao một lần gọi có thể chuyển ít hơn `count`?

Theo hợp đồng API, `transferTo` và `transferFrom` **có thể chuyển ít hơn lượng yêu cầu**. Các lý do điển hình:

1. **Không đủ dữ liệu:** vùng đọc từ tệp chỉ còn vài byte; với `transferFrom`, channel nguồn có thể đã hết dữ liệu (EOF).
2. **Giới hạn của hệ điều hành hoặc bộ cung cấp channel:** một lời gọi chuyển dữ liệu có thể bị giới hạn kích thước, kể cả khi còn rất nhiều byte. Truyền file lớn không được giả định thành công trong một lời gọi.
3. **Channel không chặn:** đầu đọc chưa có dữ liệu hoặc đầu ghi chưa sẵn sàng nhận thêm, nên có thể chuyển ít hoặc trả 0.
4. **Trạng thái tệp thay đổi đồng thời:** tác vụ khác rút ngắn, mở rộng hoặc chỉnh sửa tệp trong lúc chuyển, khiến kích thước dự kiến không còn phản ánh dữ liệu thực.
5. **Lỗi I/O:** channel có thể thất bại và ném exception giữa quá trình; việc chuyển một số byte trước đó không đồng nghĩa thao tác toàn bộ đã thành công.

Một số triển khai có thể tối ưu transfer bằng đường đi của hệ điều hành (thường gọi là **zero-copy**), giảm việc sao chép qua bộ đệm trong user space. Tuy nhiên, **API không cam kết luôn dùng zero-copy hoặc mọi lần đều chuyển đủ `count`**. Hành vi và hiệu năng phụ thuộc source/target, provider, hệ điều hành và môi trường.

## 5. Vòng lặp chuyển đủ số byte với `transferTo`

Với một tệp nguồn ổn định và channel đích ghi đồng bộ, mẫu xử lý cơ bản:

~~~java
long remaining = source.size();
long offset = 0;

while (remaining > 0) {
    long transferred = source.transferTo(offset, remaining, target);

    if (transferred == 0) {
        throw new IOException("Không có tiến triển khi transferTo");
    }

    offset += transferred;
    remaining -= transferred;
}
~~~

Đây là **đoạn minh họa**, sử dụng các biến `source` (`FileChannel`) và `target` (`WritableByteChannel`) đã được mở, cùng `java.io.IOException`.

**Tại sao cập nhật cả hai biến?** `offset` tăng theo số byte vừa đọc để lần gọi sau không sao chép lại đoạn đã chuyển; `remaining` giảm tương ứng để không đọc vượt yêu cầu. Nếu yêu cầu ban đầu bằng `0`, vòng lặp không chạy.

**Tại sao không `while` vô hạn khi nhận 0?** Nếu gọi liên tục khi không có tiến triển, CPU có thể bị tiêu tốn vô ích. Với ví dụ tệp thường và channel ghi đồng bộ, ném `IOException` làm thao tác lỗi được báo rõ ràng. Trong thiết kế không chặn, phải chờ channel sẵn sàng thông qua cơ chế thích hợp rồi thử lại; không dùng vòng lặp quay liên tục.

Nếu muốn chỉ chuyển một vùng `[start, start + length)` của tệp, đặt `offset = start` và `remaining = length`. Trước khi sao chép, kiểm tra `start >= 0`, `length >= 0` và vùng cần thiết có trong dữ liệu thực; tránh phép cộng `start + length` bị tràn `long` bằng cách so sánh với kích thước theo hướng an toàn (ví dụ `length <= size - start` khi `start <= size`).

## 6. Vòng lặp chuyển đủ số byte với `transferFrom`

Đảo chiều API: phương thức được gọi trên **FileChannel đích**, và `position` là offset ghi.

~~~java
long remaining = expectedBytes;
long destinationOffset = 0;

while (remaining > 0) {
    long transferred = destination.transferFrom(
            source, destinationOffset, remaining);

    if (transferred == 0) {
        throw new IOException(
                "Nguồn hết dữ liệu hoặc không sẵn sàng trong transferFrom");
    }

    destinationOffset += transferred;
    remaining -= transferred;
}
~~~

Đây là **đoạn minh họa**, trong đó `destination` là `FileChannel` ghi, `source` là `ReadableByteChannel` mở để đọc, `expectedBytes` đã được xác định, và đã import `IOException`.

Khi `source` là `FileChannel`, `transferFrom` dùng vị trí hiện tại của nguồn và làm vị trí đó tiến lên. Do đó vòng lặp chỉ tự cập nhật `destinationOffset`; nếu tự gọi thêm `source.position(source.position() + transferred)` thì sẽ **bỏ qua dữ liệu**. Khi `source` là network channel, dữ liệu đến từng đợt có thể khiến `transferred` bằng 0 dù kết nối chưa kết thúc.

**Khác biệt với `transferTo`:** việc ghi của `transferFrom` vào một offset có thể mở rộng tệp đích khi offset nằm trong hoặc sát cuối tệp. Nếu `position` lớn hơn kích thước tệp hiện có, API cho phép không chuyển byte nào. Muốn tạo lỗ trống hoặc ghi ngẫu nhiên, hãy dùng chiến lược định vị/ghi phù hợp và kiểm tra hệ thống tệp.

## 7. Ví dụ Java 17+ hoàn chỉnh: chạy cả hai chiều và xác minh nội dung

Chương trình sau tạo tệp nguồn với dữ liệu ASCII có độ dài cố định 11 byte (`Java NIO.2\n`), sao chép theo cả hai hướng, xác minh số byte đã chuyển, trạng thái vị trí và so sánh nội dung. Nó cố tình xử lý trường hợp **mỗi lời gọi chỉ chuyển một phần** bằng vòng lặp.

Lưu dưới tên **`FileChannelTransferDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.channels.FileChannel;

public class FileChannelTransferDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("channel-transfer-");
        Path sourceFile = directory.resolve("source.txt");
        Path toFile = directory.resolve("copy-to.txt");
        Path fromFile = directory.resolve("copy-from.txt");

        try {
            Files.writeString(
                    sourceFile, "Java NIO.2\n", StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW);

            long transferredTo;
            long sourcePositionAfterTo;
            try (FileChannel source = FileChannel.open(
                         sourceFile, StandardOpenOption.READ);
                 FileChannel target = FileChannel.open(
                         toFile, StandardOpenOption.CREATE_NEW,
                         StandardOpenOption.WRITE)) {

                long required = source.size();
                long offset = 0;

                while (offset < required) {
                    long n = source.transferTo(
                            offset, required - offset, target);
                    if (n == 0) {
                        throw new IOException(
                                "transferTo không có tiến triển tại " + offset);
                    }
                    offset += n;
                }

                transferredTo = offset;
                sourcePositionAfterTo = source.position();
            }

            long transferredFrom;
            long destinationPositionAfterFrom;
            try (FileChannel source = FileChannel.open(
                         sourceFile, StandardOpenOption.READ);
                 FileChannel target = FileChannel.open(
                         fromFile, StandardOpenOption.CREATE_NEW,
                         StandardOpenOption.WRITE)) {

                long required = source.size();
                long destinationOffset = 0;

                while (destinationOffset < required) {
                    long n = target.transferFrom(
                            source, destinationOffset,
                            required - destinationOffset);
                    if (n == 0) {
                        throw new IOException(
                                "transferFrom không có tiến triển tại "
                                        + destinationOffset);
                    }
                    destinationOffset += n;
                }

                transferredFrom = destinationOffset;
                destinationPositionAfterFrom = target.position();
            }

            boolean equalCopies = Files.mismatch(sourceFile, toFile) == -1
                    && Files.mismatch(sourceFile, fromFile) == -1;

            System.out.println("Source bytes: " + Files.size(sourceFile));
            System.out.println("transferTo bytes: " + transferredTo);
            System.out.println("transferFrom bytes: " + transferredFrom);
            System.out.println(
                    "Source position after transferTo: "
                            + sourcePositionAfterTo);
            System.out.println(
                    "Destination position after transferFrom: "
                            + destinationPositionAfterFrom);
            System.out.println("Copies match: " + equalCopies);
        } finally {
            Files.deleteIfExists(toFile);
            Files.deleteIfExists(fromFile);
            Files.deleteIfExists(sourceFile);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 FileChannelTransferDemo.java
java FileChannelTransferDemo
~~~

Khi việc chuyển tệp thông thường hoàn tất, **stdout** là:

~~~text
Source bytes: 11
transferTo bytes: 11
transferFrom bytes: 11
Source position after transferTo: 0
Destination position after transferFrom: 0
Copies match: true
~~~

### Đọc kỹ ví dụ

1. Chuỗi `"Java NIO.2\n"` có 11 byte UTF-8: 10 ký tự ASCII hiển thị và một ký tự xuống dòng. Trong ví dụ này, số ký tự và byte trùng nhau vì toàn bộ là ASCII; **điều đó không đúng với mọi chuỗi Unicode**.
2. `source.size()` được lấy làm số byte dự kiến. Với nguồn ổn định, vòng lặp sao chép cho đến khi tổng `n` đạt `required`; nếu một lần trả 0, chương trình báo lỗi thay vì coi là thành công hoặc lặp vô hạn.
3. `transferTo(offset, remaining, target)` giữ nguyên `source.position()`. Vì nguồn mới mở ở vị trí 0 và không có thao tác nào thay đổi nó, giá trị in ra bằng 0.
4. `target.transferFrom(source, destinationOffset, remaining)` dùng offset ghi tường minh và không thay đổi `target.position()`. Vì channel đích mới mở ở vị trí 0, giá trị in ra vẫn là 0, **dù tệp đích đã chứa 11 byte**.
5. `Files.mismatch(a, b) == -1` xác nhận byte nội dung bằng nhau, bổ sung cho kiểm tra tổng byte.
6. `try-with-resources` đóng các channel ngay cả khi phát sinh lỗi; khối `finally` dọn các tệp tạm được tạo trong ví dụ.

Các giá trị byte và vị trí ở trên không phụ thuộc vào tên thư mục tạm. Nếu môi trường từ chối một thao tác I/O, chương trình báo exception và có thể không in đủ stdout; đây là đường lỗi có chủ đích.

## 8. Đừng nhầm EOF với việc tạm thời chưa có tiến triển

Giả sử cần nhận 1.000 byte từ một `ReadableByteChannel` mạng không chặn và gọi:

~~~java
long n = destination.transferFrom(networkSource, offset, 1000 - offset);
~~~

Nếu `n == 0`, có nhiều khả năng: hiện chưa có byte để đọc, phía gửi đã đóng sau khi hết dữ liệu, hoặc cơ chế transfer trực tiếp tạm thời không chuyển được. **Kết quả 0 riêng lẻ không cung cấp đủ thông tin để kết luận EOF**. Với channel hỗ trợ chế độ không chặn, việc chờ thông qua `Selector` hoặc cơ chế đồng bộ/sự kiện phù hợp cần được thiết kế theo loại channel và nghiệp vụ, có thể kết hợp timeout hoặc hủy.

Với **tệp nguồn thường đã biết kích thước**, chương trình có thể yêu cầu chuyển đúng số byte đã xác định. Nếu nguồn đã bị rút ngắn hoặc không còn byte ở offset đọc, việc nhận 0 trước khi đủ yêu cầu nên được coi là lỗi chuyển thiếu; không đánh dấu thành công.

Khi chuyển dữ liệu từ **nguồn không biết tổng độ dài**, không thể chỉ đặt `expectedBytes` tùy ý lớn rồi coi 0 là EOF. Cần giao thức xác định kết thúc (ví dụ tổng độ dài từ header hoặc tín hiệu kết thúc rõ ràng), hay dùng vòng lặp `read` cho phép phân biệt `-1` (EOF) với `0` (chưa đọc byte), tùy giao thức.

Một mẫu **fallback** cho FileChannel-to-FileChannel khi tối ưu transfer không tiến triển có thể dùng `ByteBuffer` để đọc từ một offset cụ thể và ghi vào vị trí đích; khi đó vẫn phải xử lý số byte thực tế của cả `read` lẫn `write`. Fallback phức tạp hơn nên chỉ thêm khi thực sự cần đáp ứng môi trường cụ thể, và tuyệt đối không viết vòng lặp retry liên tục không giới hạn.

## 9. Sao chép vùng tệp: offset, số byte và giới hạn

Để sao chép 4 KiB bắt đầu tại byte thứ 8 KiB của tệp nguồn:

~~~java
long start = 8L * 1024;
long requested = 4L * 1024;
long size = source.size();

if (start > size || requested > size - start) {
    throw new IOException("Vùng yêu cầu vượt dữ liệu hiện có");
}

long copied = 0;
while (copied < requested) {
    long n = source.transferTo(
            start + copied, requested - copied, target);
    if (n == 0) {
        throw new IOException("Chuyển thiếu dữ liệu trong vùng yêu cầu");
    }
    copied += n;
}
~~~

Đây là đoạn minh họa sử dụng `source` (`FileChannel`), `target` (`WritableByteChannel`) đã mở và import `IOException`. Nếu không muốn lặp đến đủ, phải **chủ động chấp nhận** rằng kết quả chỉ là số byte đã chuyển; API không tự hoàn thiện phần còn thiếu.

Phép kiểm tra `requested > size - start` (sau khi chắc chắn `start <= size`) tránh tính `start + requested` quá sớm gây tràn `long`. Trong ứng dụng thật, xác minh cả `start` và `requested` không âm.

**Với tệp rất lớn:** biến tổng, offset và remaining nên dùng kiểu `long`; không ép `size` về `int`. Một yêu cầu hàng GiB có thể được API/hệ điều hành thực hiện qua nhiều lần chuyển ngắn. Chỉ dừng khi đã đạt tổng mong muốn hoặc gặp tình trạng không thể hoàn thành một cách có kiểm soát.

## 10. Ghi vào tệp đích và tránh dữ liệu thừa

`transferTo` ghi từ **vị trí hiện tại của channel đích** nếu đích là FileChannel. Nếu mở tệp đích cũ mà không truncate và nội dung mới ngắn hơn nội dung cũ, phần đuôi cũ có thể vẫn còn trong tệp. Để sao chép thành một tệp mới, nên:

- Mở tệp chưa tồn tại bằng `CREATE_NEW, WRITE`, hoặc
- Mở tệp đã tồn tại có chủ đích bằng `CREATE, WRITE, TRUNCATE_EXISTING` nếu được phép thay thế nội dung, rồi bảo đảm vị trí ghi là 0.

Với `transferFrom`, offset ghi được truyền trực tiếp; ghi vào một tệp cũ cũng có thể để lại dữ liệu thừa ngoài phạm vi ghi. Tùy hợp đồng ứng dụng, `FileChannel.truncate(expectedLength)` sau khi hoàn thành có thể dùng để giới hạn kích thước đích, nhưng **phải hiểu rõ dữ liệu nào được phép xóa**. Không dùng truncate tùy tiện nếu tệp còn chứa các vùng dữ liệu khác.

Tránh hai luồng cùng thay đổi vị trí của chung một channel trong khi chuyển. Vị trí có thể là trạng thái dùng chung, nên việc xen kẽ với `position()` hoặc hoạt động ghi khác có thể làm kết quả khác mong đợi. Tổ chức ownership channel rõ ràng và đồng bộ nếu thực sự chia sẻ channel.

## 11. Độ đúng, lỗi I/O và tính toàn vẹn dữ liệu

Một vòng lặp cộng tổng byte là **cần thiết nhưng chưa đủ** để chứng minh bản sao chính xác trong mọi trường hợp.

- **Nguồn thay đổi trong quá trình đọc:** `source.size()` lấy trước có thể không còn đúng. Nếu cần bản sao nhất quán, phải phối hợp khóa/đóng băng dữ liệu, snapshot hoặc một cơ chế quản lý phiên bản phù hợp; `FileChannel.lock()` có hạn chế về tính chất và sự hợp tác của các tiến trình.
- **Đích gặp lỗi sau một phần dữ liệu:** file đích có thể chứa bản sao chưa hoàn chỉnh. Dùng file tạm, kiểm tra rồi đổi tên/di chuyển theo chính sách ứng dụng để hạn chế việc công bố bản sao lỗi.
- **Tổng byte đúng nhưng nội dung không đúng:** cùng độ dài chưa đủ bảo đảm cùng dữ liệu. Có thể so sánh byte với `Files.mismatch`; với hệ thống phân tán hoặc cần kiểm tra về sau có thể thêm checksum/hash và cơ chế tin cậy thích hợp.
- **`force()` và độ bền dữ liệu:** chuyển đủ byte vào FileChannel không đồng nghĩa tất cả byte đã bền vững trên thiết bị lưu trữ. Nếu yêu cầu durability, cân nhắc `FileChannel.force(true)` trên đích và quy trình ghi/đổi tên phù hợp với nền tảng.
- **Tài nguyên:** dùng `try-with-resources` để đóng nguồn và đích; không che mất exception gốc nếu cleanup cũng thất bại.

Trong quy trình copy file quan trọng, báo cáo kết quả nên chứa số byte dự kiến, số byte thực tế, cờ kiểm tra toàn vẹn và thông tin lỗi nếu thao tác thất bại.

## 12. Những lỗi phổ biến

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Gọi `transferTo(0, size, target)` một lần rồi mặc định xong | Có thể thiếu byte trên một số hệ thống | Đọc giá trị trả về; lặp với offset tăng theo byte thực tế |
| Gọi `transferFrom(src, 0, count)` nhiều lần khi có partial transfer | Ghi đè phần đã chuyển vào đầu file đích | Tăng `position` ghi theo tổng byte thực |
| Tự tăng `source.position()` sau `transferFrom` với FileChannel nguồn | Đọc bỏ qua dữ liệu | Để channel nguồn tiến vị trí theo thao tác đọc |
| Giả định `FileChannel.position()` của đối tượng gọi sẽ tăng | Đọc/ghi tiếp từ vị trí sai | Dùng offset truyền vào API và theo dõi riêng |
| Coi `0` luôn là EOF | Kết thúc sớm với channel không chặn | Phân biệt nguồn/file/giao thức; chờ readiness hoặc báo lỗi đúng |
| Retry vô hạn khi `0` | Busy-spin, CPU cao | Có chính sách chờ, timeout, fallback hoặc fail fast |
| Dùng `int` để đếm byte của file lớn | Tràn số, cắt ngắn dữ liệu | Dùng `long` |
| Bỏ qua file đích tồn tại và vị trí ghi | Dữ liệu cũ còn sót hoặc bị ghi ở vị trí không mong muốn | Quy định rõ create/truncate và offset |
| Chỉ so kích thước hai file | Không phát hiện byte nội dung sai | So sánh nội dung hoặc checksum phù hợp |
| Cho rằng transfer luôn là zero-copy | Phụ thuộc đặc tính không được API đảm bảo | Đo đạc hiệu năng thực và có chiến lược xử lý partial |

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Tệp nguồn dài 1.000 byte. `source.transferTo(0, 1000, target)` trả về 600. Nên chuyển tiếp thế nào?

**Đáp án:** Chưa thể coi bản sao hoàn chỉnh. Nếu dữ liệu nguồn và đích còn sẵn sàng, gọi `source.transferTo(600, 400, target)`, tiếp tục dựa vào giá trị trả về.

**Câu 2.** `destination.transferFrom(source, 100, 50)` trả về 20. `destination.position()` có chắc tăng 20 không?

**Đáp án:** Không. Vị trí channel đích được gọi **không đổi**. Lần chuyển tiếp ghi tại offset `120`; nguồn có vị trí thường đã tiến theo dữ liệu được đọc.

**Câu 3.** `transferFrom` trả về 0 từ một `SocketChannel` không chặn. Có thể kết luận peer đã đóng kết nối chưa?

**Đáp án:** Không. Có thể hiện chưa có dữ liệu hoặc chưa thể tiến hành transfer; phải dựa vào cơ chế sẵn sàng và giao thức đọc để xác định EOF.

**Câu 4.** Khi sao chép file 8 GiB, có thể yêu cầu `count = 8 GiB` một lần rồi không kiểm tra kết quả không?

**Đáp án:** Không. Dù `count` dùng `long`, giới hạn nền tảng có thể khiến một lần chỉ chuyển được một phần. Luôn đếm tổng byte thực tế.

**Câu 5.** Hai bản sao đều dài 11 byte có chắc cùng nội dung không?

**Đáp án:** Không. Tổng byte bằng nhau chỉ là một điều kiện; ví dụ dùng `Files.mismatch` để so sánh byte.

## 14. Ghi nhớ

- **`transferTo`:** `FileChannel` nguồn → `WritableByteChannel` đích; `position` là offset **nguồn**.
- **`transferFrom`:** `ReadableByteChannel` nguồn → `FileChannel` đích; `position` là offset **đích**.
- Cả hai trả về **số byte chuyển thực tế**, không mặc định bằng `count`, và không tự thay đổi vị trí của `FileChannel` mà phương thức được gọi trên đó.
- Muốn chuyển đủ dữ liệu, dùng vòng lặp `long`, tăng offset theo kết quả từng lần, kiểm soát tình huống `0` và kiểm tra toàn vẹn sau khi hoàn thành.

