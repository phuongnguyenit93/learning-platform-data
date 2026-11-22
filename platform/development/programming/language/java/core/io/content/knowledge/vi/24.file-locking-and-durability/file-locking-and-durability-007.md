# Ghi ra tệp tạm rồi thay thế đích trong Java NIO.2

## 1. Vì sao nên ghi ra tệp tạm trước khi thay thế?

Khi cập nhật một tệp quan trọng như `config.json`, `settings.properties`, chỉ mục nhỏ hoặc file lưu trạng thái, cách ghi trực tiếp vào tệp đích có một vấn đề: nếu chương trình bị dừng giữa chừng, tệp có thể chỉ chứa **một phần nội dung mới**, bị cắt ngắn hoặc không còn hợp lệ.

Ví dụ thao tác dễ gây rủi ro:

```java
Files.writeString(
        Path.of("config.txt"),
        "version=2\nmode=production\n",
        StandardCharsets.UTF_8
);
```

Đây chỉ là đoạn minh họa, cần import `java.nio.file.Files`, `Path` và `java.nio.charset.StandardCharsets`. Nếu tệp đích đang tồn tại, `Files.writeString` với tùy chọn mặc định có thể ghi đè và cắt nội dung cũ. Nếu lỗi I/O hoặc tiến trình chết sau khi đã thay đổi một phần dữ liệu, người đọc có thể gặp nội dung hỏng.

Mẫu **write temporary file, then replace destination** giải quyết vấn đề ở cấp cấu trúc:

1. **Tạo một tệp tạm mới** nằm cùng thư mục/cùng filesystem với đích.
2. **Viết toàn bộ nội dung mới** vào tệp tạm và kiểm tra tính hợp lệ.
3. Nếu yêu cầu độ bền, **đồng bộ dữ liệu tệp tạm** bằng `FileChannel.force(true)`.
4. **Đóng handle** tệp tạm.
5. Dùng `Files.move(temp, destination, ...)` để thay thế tên đích bằng tệp mới; ưu tiên `ATOMIC_MOVE` nếu hệ thống hỗ trợ.
6. **Dọn tệp tạm** nếu chưa được chuyển thành công; thiết kế recovery cho tệp tạm còn sót khi hệ thống sập.

Trước khi thay thế, tệp đích vẫn chứa bản cũ hoàn chỉnh. Nếu bước rename/move được hỗ trợ **nguyên tử**, bên đọc qua tên đích sẽ thấy bản cũ hoặc bản mới, không thấy một tệp đang được ghi dở do chính quy trình này.

Điều đó **không đồng nghĩa giao dịch cơ sở dữ liệu**, không đảm bảo mọi filesystem có atomic replace, và chưa đủ để kết luận “mất điện cũng không mất bản mới”. Chúng ta cần phân biệt ba khái niệm: tính nguyên vẹn nội dung trước khi công bố, tính nguyên tử khi thay thế tên, và độ bền trên lưu trữ.

## 2. Mô hình trạng thái trước và sau

Giả sử `settings.json` chứa bản V1 và muốn cập nhật V2:

```text
Giai đoạn A — trước khi ghi:
  settings.json                 [V1 hoàn chỉnh]

Giai đoạn B — ghi tệp tạm:
  settings.json                 [V1 hoàn chỉnh]
  .settings-47392.tmp           [V2 đang ghi, chưa công bố]

Giai đoạn C — đã ghi/validate/force/đóng:
  settings.json                 [V1 hoàn chỉnh]
  .settings-47392.tmp           [V2 hoàn chỉnh]

Giai đoạn D — move/replace nguyên tử:
  settings.json                 [V2 hoàn chỉnh]
  .settings-47392.tmp           [không còn ở tên tạm]
```

Nếu `move` nguyên tử được filesystem hỗ trợ, tên `settings.json` đổi đối tượng tệp được tham chiếu trong một thao tác công bố. Nếu move **không nguyên tử**, giữa chừng có thể có khoảng thời gian không nhìn thấy đích hoặc những trạng thái khác tùy cách filesystem/provider thực hiện.

Khi đang ghi V2 vào tệp tạm, không nên vô tình sử dụng tên cố định `settings.tmp` khiến hai tiến trình tranh nhau ghi đè. `Files.createTempFile(parent, prefix, suffix)` cấp một tên mới chưa tồn tại bằng thao tác tạo tệp của filesystem, thuận tiện hơn tự ghép tên dựa trên thời gian.

## 3. “Nguyên tử”, “bền” và “nhất quán” là ba yêu cầu khác nhau

| Yêu cầu | Câu hỏi | Công cụ thường dùng | Giới hạn |
|---|---|---|---|
| Nội dung mới hợp lệ trước khi công bố | Có ghi đủ và validate V2 chưa? | Ghi tệp tạm, kiểm tra size/checksum/format | Chỉ tốt nếu kiểm tra đúng định dạng |
| Atomic visibility của tên đích | Reader mở đường dẫn đích có thấy V1 hoặc V2 hoàn chỉnh? | `Files.move(..., ATOMIC_MOVE)` khi được hỗ trợ | Không phải mọi filesystem/provider hoặc cách replace đều hỗ trợ |
| Độ bền sau sự cố | Khi máy mất điện, V2 có còn sau reboot? | `FileChannel.force(true)` cho tệp tạm; cơ chế đồng bộ metadata/thư mục theo OS | API Java chuẩn không cung cấp cam kết portable đầy đủ cho directory fsync + rename |
| Tránh ghi đè bản cập nhật từ writer khác | Writer A có đè mất bản vừa công bố của B? | Điều phối writer, version/CAS, lock ở tầng phù hợp | Atomic rename chỉ nguyên tử bước công bố, không giải quyết lost update |
| Nhiều file cùng cập nhật | Hai file có cùng chuyển V1 sang V2 một lượt không? | Thiết kế manifest/version, journal hoặc transaction chuyên dụng | Một lần move chỉ liên quan một mục nhập đích |

**Atomic visibility ≠ crash durability.** Dù move thành công và reader thấy V2, ứng dụng không nên mặc định rằng mọi directory metadata đã an toàn qua mất điện. Nếu có yêu cầu nghiêm ngặt về phục hồi sau sự cố, cần hợp đồng filesystem/OS cụ thể, có thể đồng bộ thư mục theo giao diện hệ thống, hoặc dùng cơ chế transaction/journal đã được kiểm chứng.

## 4. Vì sao tệp tạm nên ở cùng thư mục với đích?

Một rename nguyên tử thông thường hoạt động **trong cùng filesystem**. Nếu tạo tệp tạm trong thư mục temp toàn hệ thống, tệp đích có thể nằm trên volume khác, khiến `ATOMIC_MOVE` không được hỗ trợ.

Ví dụ không nên mặc định an toàn:

```java
Path temporary = Files.createTempFile("update-", ".tmp");
Path destination = Path.of("/mnt/data/config.json");
```

Đoạn minh họa có thể tạo tệp tạm tại thư mục `java.io.tmpdir`, trong khi đích ở filesystem khác. Ngay cả nếu tên đích và temp trông như cùng ổ đĩa, mount/bind mount/network filesystem có thể ảnh hưởng semantics.

Thay vào đó, chọn **thư mục cha của chính đích**:

```java
Path destination = Path.of("config.json").toAbsolutePath();
Path parent = destination.getParent();
Path temporary = Files.createTempFile(parent, ".config-", ".tmp");
```

- `Files.createTempFile` tạo tệp mới và trả `Path` thực, tránh trùng tên trong điều kiện bình thường.
- Temp và đích nằm cùng thư mục, qua đó tăng khả năng hỗ trợ move nguyên tử.
- Đường dẫn temp thường **không** phải file backup lâu dài: sau move, tên tạm bị xóa vì tệp được đổi sang tên đích.
- Thư mục cha cần tồn tại và phải có quyền tạo/rename/xóa mục nhập.
- Với thông tin nhạy cảm, xem xét quyền mặc định của temp ngay từ khi tạo và điều chỉnh quyền/ACL theo policy trước khi công bố, vì temp là một **đối tượng tệp mới**.

Nằm cùng thư mục chỉ là **điều kiện thuận lợi**, không bảo đảm `ATOMIC_MOVE` hoạt động; provider/filesystem vẫn có thể không hỗ trợ hoặc có quy tắc replace riêng.

## 5. Ghi đủ dữ liệu vào tệp tạm

Khi dùng `FileChannel`, việc gọi `write(ByteBuffer)` một lần **không đảm bảo** đã ghi hết buffer. Cần kiểm tra `hasRemaining()` và số byte trả về:

```java
static void writeFully(FileChannel channel, ByteBuffer source)
        throws IOException {
    while (source.hasRemaining()) {
        int n = channel.write(source);
        if (n == 0) {
            throw new IOException("Write made no progress");
        }
    }
}
```

Đây là phương thức minh họa, cần import `FileChannel`, `ByteBuffer` và `IOException`. Nếu format có nhiều trường nhị phân, hãy thiết lập `ByteOrder` nhất quán. Nếu ghi UTF-8, mã hóa tường minh bằng `StandardCharsets.UTF_8`. Không dùng số ký tự làm số byte; ký tự UTF-8 có thể chiếm hơn một byte.

Với tệp tạm đã tồn tại do `createTempFile`, mở channel để ghi:

```java
try (FileChannel channel = FileChannel.open(
        temporary,
        StandardOpenOption.WRITE,
        StandardOpenOption.TRUNCATE_EXISTING)) {
    ByteBuffer bytes = StandardCharsets.UTF_8.encode("version=2\n");
    writeFully(channel, bytes);
    channel.force(true);
}
```

Đoạn này giả định `temporary` đã được tạo và quyền ghi hợp lệ; các import tương ứng phải được khai báo. `TRUNCATE_EXISTING` ở đây là **tệp tạm**, không phải file đích, nên không làm hỏng V1. Đóng channel trước khi move cũng giúp tránh một số hạn chế khi thay tên file trên các hệ điều hành có xử lý handle khác nhau.

### Xác thực tệp trước khi công bố

Việc `write` hoàn tất mới chỉ xác nhận đã chuyển các byte cho I/O. Nếu dữ liệu có định dạng JSON, CSV, bản ghi nhị phân, chứng chỉ, manifest hoặc index, nên **validate trước move**:

- Kích thước hợp lý và không bị cắt đuôi.
- Có cấu trúc/phiên bản/schema đúng yêu cầu.
- Các giá trị, liên kết tham chiếu, checksum hoặc hash hợp lệ nếu định dạng yêu cầu.
- Quyền truy cập/owner/ACL phù hợp với ứng dụng sau khi tệp tạm trở thành đích.

Không nhất thiết phải đọc toàn bộ temp lần nữa với mọi loại file; lựa chọn validation theo độ tin cậy của serializer và mức thiệt hại nếu công bố file lỗi. Với dữ liệu giao dịch quan trọng, thiết kế kiểm tra có chủ đích thay vì chỉ đợi `write` trả về.

## 6. `Files.move`, `ATOMIC_MOVE` và `REPLACE_EXISTING`

API Java NIO.2:

```java
Files.move(
        temporary,
        destination,
        StandardCopyOption.ATOMIC_MOVE,
        StandardCopyOption.REPLACE_EXISTING
);
```

- `ATOMIC_MOVE` **yêu cầu** hệ thống thực hiện di chuyển như thao tác filesystem nguyên tử. Nếu không thể, có thể ném `AtomicMoveNotSupportedException`.
- `REPLACE_EXISTING` dùng cho cách move thông thường để cho phép thay tên đích đã tồn tại, chịu các giới hạn khác của provider.
- **Chi tiết quan trọng:** theo tài liệu `Files.move`, khi có `ATOMIC_MOVE`, **các tùy chọn khác bị bỏ qua**; nếu mục tiêu đã tồn tại, hành vi thay thế/không thay thế là **phụ thuộc implementation**. Vì vậy chỉ đặt cả hai option không bảo đảm atomic replacement được hỗ trợ trên mọi hệ thống.
- Nếu `ATOMIC_MOVE` thất bại, không nên âm thầm bỏ nó rồi tiếp tục như thể thao tác vẫn atomic.
- Nếu lựa chọn fallback sang move không atomic, phải coi đây là **thay đổi mức bảo đảm** có ảnh hưởng đến reader và phục hồi lỗi.

Có thể thử atomic move trước:

```java
try {
    Files.move(temp, target,
            StandardCopyOption.ATOMIC_MOVE,
            StandardCopyOption.REPLACE_EXISTING);
} catch (AtomicMoveNotSupportedException ex) {
    // Chính sách 1: báo lỗi và giữ nguyên đích; dọn temp khi phù hợp.
    throw new IOException("Filesystem không hỗ trợ atomic move", ex);
}
```

Đây là đoạn minh họa cần import `Path`, `Files`, `StandardCopyOption`, `AtomicMoveNotSupportedException` và `IOException`. Nó là chính sách **yêu cầu atomic**: nếu không hỗ trợ thì dừng, không tự hạ bảo đảm.

Trên một số provider, atomic move khi mục tiêu đã tồn tại có thể thất bại với `FileAlreadyExistsException` theo quy tắc implementation. Khi cần strict atomic replacement, không coi kết quả đó là tín hiệu để xóa đích trước rồi rename: **xóa đích trước sẽ tạo một khoảng trống có thể quan sát được**.

## 7. Chương trình Java 17+ hoàn chỉnh: viết tệp tạm rồi thay đích

Ví dụ sau tạo tệp đích chứa `old`, viết `new` vào temp **trong cùng thư mục**, gọi `force(true)` rồi đóng channel trước khi move. Ví dụ có **chính sách fallback được khai báo rõ**: nếu không thể atomic replace do provider không hỗ trợ atomic move hoặc không cho replace mục tiêu đang tồn tại theo chế độ atomic, chương trình cho phép dùng `REPLACE_EXISTING` không atomic. Trong sản phẩm yêu cầu atomic nghiêm ngặt, chuyển `ALLOW_NON_ATOMIC_FALLBACK` thành `false` để dừng thay vì hạ mức bảo đảm.

Lưu thành **`TempFileReplaceDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.channels.FileChannel;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;

public class TempFileReplaceDemo {
    // Ví dụ cho phép fallback để chạy trên nhiều filesystem.
    // Đặt false nếu nghiệp vụ bắt buộc atomic replacement.
    private static final boolean ALLOW_NON_ATOMIC_FALLBACK = true;

    public static void main(String[] args) throws IOException {
        Path folder = Files.createTempDirectory("replace-demo-");
        Path target = folder.resolve("config.txt");

        try {
            Files.writeString(target, "old\n", StandardCharsets.UTF_8);
            replaceWithText(target, "new\n");

            System.out.println("Destination: "
                    + Files.readString(target, StandardCharsets.UTF_8).strip());
            System.out.println("Destination exists: " + Files.exists(target));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(folder);
        }
    }

    private static void replaceWithText(Path target, String text)
            throws IOException {
        Path parent = target.toAbsolutePath().getParent();
        Path temporary = Files.createTempFile(
                parent, ".config-", ".tmp");

        try {
            ByteBuffer data = StandardCharsets.UTF_8.encode(text);

            try (FileChannel channel = FileChannel.open(
                    temporary,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {
                while (data.hasRemaining()) {
                    int written = channel.write(data);
                    if (written == 0) {
                        throw new IOException("Write made no progress");
                    }
                }
                channel.force(true);
            }

            try {
                Files.move(
                        temporary,
                        target,
                        StandardCopyOption.ATOMIC_MOVE,
                        StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException
                     | FileAlreadyExistsException ex) {
                if (!ALLOW_NON_ATOMIC_FALLBACK) {
                    throw ex;
                }
                // Fallback minh bạch: không còn bảo đảm atomic.
                Files.move(
                        temporary,
                        target,
                        StandardCopyOption.REPLACE_EXISTING);
            }
        } finally {
            // Nếu move đã thành công, path tạm không còn tồn tại.
            // Nếu lỗi xảy ra trước move, dọn tệp tạm tốt nhất có thể.
            Files.deleteIfExists(temporary);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac TempFileReplaceDemo.java
java TempFileReplaceDemo
```

**Stdout khi thao tác tạo/ghi/đọc/move/xóa thành công** (dù nhánh atomic hay fallback được sử dụng):

```text
Destination: new
Destination exists: true
```

Giải thích:

1. `Files.writeString(target,"old\n")` chỉ tạo trạng thái ban đầu cho ví dụ. Trong ứng dụng thực, đây sẽ là file có sẵn và không được ghi lại trước mỗi lần cập nhật.
2. `Files.createTempFile(parent,...)` sinh một file riêng trong cùng thư mục với đích. V1 chưa bị ảnh hưởng khi code bắt đầu ghi V2.
3. `ByteBuffer` mã hóa UTF-8; vòng lặp `write` đảm bảo gửi hết dữ liệu vào channel. `force(true)` yêu cầu đồng bộ nội dung và metadata liên quan của file theo ngữ nghĩa API.
4. Thoát try-with-resources đóng channel. Sau đó mới thử `Files.move` atomic.
5. Nếu provider báo không hỗ trợ atomic hoặc không cho atomic replace đích hiện tại theo hành vi implementation, ví dụ **có chủ ý** fallback sang move thường. Kết quả vẫn có thể là `new`, nhưng fallback **không bảo đảm atomic visibility**.
6. `finally` ở helper dọn temp nếu nó còn tồn tại. Khi move thành công, temp đã được đổi tên và `deleteIfExists(temporary)` không xóa đích.
7. `main` dọn file và thư mục demo sau khi đọc/in kết quả. Trong ứng dụng thực **không được xóa đích sau khi publish**; việc dọn trong `main` chỉ dành cho môi trường ví dụ.

Trường hợp môi trường từ chối rename vì file đang mở, thiếu quyền, filesystem bị khóa, thiếu dung lượng hoặc lỗi I/O khác, chương trình có thể ném `IOException` thay vì in hai dòng trên. Ví dụ không nuốt các lỗi đó. Nhánh fallback chỉ được kích hoạt cho hai loại ngoại lệ đã nêu; không giả định mọi `FileSystemException` đều có thể phục hồi bằng move thường.

**Vì sao không tự động fallback trong hệ thống nghiêm ngặt?** Vì writer và reader cần cùng hiểu bảo đảm. Một sản phẩm yêu cầu reader chỉ thấy snapshot hoàn chỉnh phải khai báo atomic replacement là điều kiện bắt buộc; nếu filesystem không hỗ trợ thì nên báo lỗi, giữ nguyên V1 và phục hồi thích hợp thay vì giả định fallback tương đương.

## 8. `force(true)` giúp gì, và chưa bảo đảm điều gì?

`FileChannel.force(boolean metaData)` yêu cầu buộc cập nhật tệp qua channel xuống thiết bị lưu trữ theo hợp đồng API:

```java
channel.force(true);
```

- `force(false)`: yêu cầu đồng bộ **nội dung** tệp.
- `force(true)`: yêu cầu đồng bộ nội dung **và metadata của tệp**.
- Việc gọi `force` trước khi thay tên giúp giảm rủi ro công bố một đối tượng tệp mà byte mới chỉ đang ở cache chưa được đẩy xuống lưu trữ.
- `force` không giải quyết nhiều bản ghi thành transaction; không chứng minh reader không thể thấy file đích đang bị thay thế theo cách không nguyên tử.
- Mức đảm bảo thực sự còn tùy loại thiết bị và filesystem; hợp đồng Java có khác biệt với tệp không nằm trên thiết bị lưu trữ cục bộ.

**Metadata của tệp tạm không đồng nghĩa metadata của thư mục chứa tên đích.** Rename thường làm thay đổi directory entry. Trên hệ POSIX, quy trình bảo đảm crash durability mạnh hơn thường yêu cầu đồng bộ dữ liệu tệp, rename, rồi đồng bộ **thư mục chứa đích**. Java SE 17 chuẩn **không có API portable, được bảo đảm hỗ trợ đồng bộ thư mục trên mọi provider**; việc mở directory để force có thể bị từ chối. Không nên viết ví dụ Java chung rồi khẳng định `force(true)` trên temp đã hoàn tất mọi bước crash-safe rename.

Nếu yêu cầu độ bền sau mất điện rất cao, cần tài liệu và kiểm thử theo OS/filesystem đích hoặc chọn kho lưu trữ có transaction/journal phù hợp. Một lần chạy thành công không chứng minh bảo đảm khi mất điện.

## 9. Điều gì xảy ra nếu ứng dụng chết ở từng giai đoạn?

| Thời điểm xảy ra lỗi | Tình trạng thường gặp | Điều cần làm |
|---|---|---|
| Trước khi tạo temp | Đích vẫn chứa V1 | Có thể thử lại |
| Đang ghi temp, trước move | Đích vẫn V1; temp có thể dang dở | Không publish temp lỗi; dọn/kiểm tra theo policy |
| Đã ghi temp và đóng nhưng chưa move | Đích V1; temp là ứng viên V2 | Có thể validate và phục hồi nếu có manifest/version |
| Atomic move hoàn tất | Reader mở theo tên đích sau move thấy V2 | Vẫn phải xét durability directory nếu mất điện |
| Fallback move không atomic bị gián đoạn | Trạng thái đích tùy filesystem/provider; không có bảo đảm V1 hoặc V2 trọn vẹn | Recovery, kiểm tra checksum/version, giữ backup nếu cần |
| Move thành công nhưng tiến trình chết trước khi nhận phản hồi | Đích **có thể đã là V2**; writer chưa biết commit có hiệu lực hay chưa | Thiết kế retry/idempotency và kiểm tra version/hash |

`finally` trong Java **không chạy khi mất điện, kill -9 hoặc hệ thống sập đột ngột**. Vì vậy phải có chiến lược tìm và xử lý tệp temp còn sót. Không dọn theo tên prefix một cách mù quáng khi nhiều writer vẫn có thể đang hoạt động; cần ownership, tuổi tệp, lock hoặc định danh transaction phù hợp.

## 10. Đọc đồng thời trong lúc thay thế

Khi rename/replace thực sự nguyên tử:

- Reader **mở đường dẫn đích trước** thời điểm replace có thể tiếp tục đọc từ handle đang trỏ vào đối tượng tệp cũ, tùy OS và filesystem.
- Reader **mở đường dẫn đích sau** thời điểm replace sẽ tra cứu mục nhập tên mới và thường nhìn thấy V2.
- Reader không nhất thiết tự “nhảy” sang V2 chỉ vì path đã được rename khi nó giữ handle mở. Nếu cần reload cấu hình, chương trình cần chủ động mở lại/tải lại.
- Việc thay tên không đồng bộ logic nội bộ của reader. Ví dụ reader đọc hai file riêng hoặc đọc V2 rồi cache một phần V1 ở chỗ khác vẫn có thể xảy ra bất nhất nghiệp vụ.

Do đó mẫu temp + rename rất hữu ích cho **một file hoàn chỉnh**: công bố tệp bằng một điểm chuyển đổi tên, còn reader quyết định thời điểm mở lại.

Đừng nhầm `Files.move` với việc **ghi nội dung tại chỗ**. Nếu chương trình khác giữ hard link tới đối tượng file V1, hard link đó có thể tiếp tục thấy V1 sau khi tên đích được thay bằng đối tượng V2. Nếu có symlink trỏ theo tên đích, việc đọc lại symlink có thể dẫn tới tệp mới; nhưng bản thân target là symlink lại có quy tắc thay thế riêng.

## 11. Đồng thời nhiều writer và lost update

Atomic replace đảm bảo về thao tác thay tên nếu được hỗ trợ, **không bảo đảm chỉ có một writer hợp lệ**.

Ví dụ:

```text
Writer A đọc V1, tính V2-A, ghi temp-A.
Writer B đọc V1, tính V2-B, ghi temp-B.
Writer A atomic replace → đích là V2-A.
Writer B atomic replace → đích là V2-B.
Kết quả: thay đổi của A có thể bị mất (lost update).
```

Giải pháp tùy bài toán:

1. Chỉ cho một writer chịu trách nhiệm tệp, mọi request đi qua một hàng đợi.
2. Dùng khóa ở mức ứng dụng hoặc một lock file riêng, với giao thức lock/recovery được thiết kế rõ.
3. Dùng version/checksum và điều kiện cập nhật ở tầng dữ liệu; riêng `Files.move` không có CAS “chỉ replace nếu bản cũ vẫn là V1”.
4. Với cập nhật đồng thời nhiều thực thể, dùng cơ chế transaction đúng nghĩa thay vì chỉ rename một file.

**Đừng cho rằng `FileLock` trên tệp đích hiện tại luôn bảo vệ tên đích qua mọi lần replace.** Khóa file có thể gắn với đối tượng/handle cũ, trong khi rename thay object dưới tên đích; mức bắt buộc của file lock còn phụ thuộc nền tảng. Nếu chọn lock, dùng hợp đồng phù hợp và không đồng nhất “khóa tệp cũ” với “khóa quyền xuất bản tên đích”.

## 12. Quyền, metadata và symbolic link

### Metadata có thể thay đổi

Vì temp là một **tệp mới**, khi nó thay đích, các thuộc tính của tệp đích cũ không tự động trở thành thuộc tính của temp:

- Quyền truy cập/ACL, owner/group.
- Timestamps và các thuộc tính đặc thù filesystem.
- Extended attributes, nhãn bảo mật, sparse/compression flags trong một số hệ thống.
- Các liên kết cứng đang tham chiếu tệp cũ.

Nếu nghiệp vụ phải giữ quyền/owner/ACL cụ thể, cần xác định policy và áp dụng/kiểm tra thuộc tính lên temp **trước khi công bố**. Tránh sao chép quyền nguy hiểm một cách vô điều kiện; quyền nên phù hợp security model. `Files.createTempFile` và `Files.getFileAttributeView`/`setAttribute` hỗ trợ một phần tùy provider, không phải mọi thuộc tính đều có API portable.

### Symlink và thư mục không tin cậy

Nếu đường dẫn đích là symbolic link, `Files.move(temp, destination, ...)` thường thao tác tới **mục nhập tên đích**, chứ không được giả định nó sẽ mở symlink rồi ghi nội dung file được symlink trỏ tới. Kết quả thay symlink hay thất bại phụ thuộc ngữ nghĩa move và provider.

Nếu kẻ khác có thể thay tệp/link/thư mục giữa khi kiểm tra và move (TOCTOU), các kiểm tra `Files.exists`/`Files.isSymbolicLink` trước đó không tạo bảo đảm an toàn tuyệt đối. Khi xử lý đường dẫn do người dùng không tin cậy cung cấp, cần kiểm soát thư mục, quyền, ownership, symlink policy và kiến trúc xuất bản phù hợp; không dựa vào một lần kiểm tra rồi giả định path không đổi.

## 13. Những cách làm sai thường gặp

1. **Ghi trực tiếp vào file đích với `TRUNCATE_EXISTING` rồi mới ghi dữ liệu mới.** Reader có thể thấy file trống hoặc nửa bản ghi nếu lỗi ở giữa.
2. **Tạo temp ở `java.io.tmpdir` dù đích ở volume khác.** Atomic move qua filesystem thường không được hỗ trợ; hãy tạo temp cùng thư mục đích.
3. **Không xử lý short write.** `FileChannel.write(ByteBuffer)` có thể ghi ít byte hơn remaining. Cần lặp tới khi hết buffer.
4. **Không đóng temp trước rename.** Trên một số OS, handle chưa đóng có thể gây lỗi move/replace.
5. **Chỉ bắt `AtomicMoveNotSupportedException` rồi âm thầm fallback.** Nếu hệ thống yêu cầu atomic, fallback phải bị từ chối; nếu chấp nhận, phải nêu rõ mức bảo đảm giảm xuống.
6. **Tin rằng `ATOMIC_MOVE + REPLACE_EXISTING` luôn đảm bảo atomic overwrite.** Khi có ATOMIC_MOVE, option khác bị bỏ qua; target đã tồn tại là hành vi phụ thuộc implementation.
7. **Xóa đích trước rồi rename temp.** Tạo một giai đoạn tên đích không tồn tại và có thể đánh mất V1 khi lỗi.
8. **Cho rằng `force(true)` trên temp đồng nghĩa rename bền tuyệt đối.** Metadata thư mục cũng quan trọng; Java không cung cấp directory fsync portable cho mọi môi trường.
9. **Ghi file tạm xong nhưng chưa kiểm tra định dạng.** Atomic publish một file sai schema vẫn tạo ra dữ liệu nghiệp vụ lỗi hoàn chỉnh.
10. **Quên quyền/ACL của temp.** Tệp được công bố là đối tượng tệp mới, có thể khác metadata của đích cũ.
11. **Coi atomic replace là lock/CAS.** Hai writer vẫn có thể đè kết quả nhau; phải có cơ chế phối hợp.
12. **Cho rằng finally luôn dọn temp.** Sau mất điện hoặc kill đột ngột vẫn có thể tồn tại temp, cần recovery khi khởi động.
13. **Tưởng mọi reader đang mở handle tự thấy nội dung mới.** Handle cũ có thể vẫn trỏ đối tượng V1; reader phải mở lại khi cần snapshot mới.
14. **Tưởng một move giải quyết transaction nhiều file.** Một file được publish nguyên tử không đồng nghĩa nhiều file đồng bộ phiên bản.

## 14. Khi nào cần backup hoặc manifest?

Temp + replace giúp giảm rủi ro tệp bị **ghi dở**, nhưng không tự bảo vệ trước:

- Đã công bố **dữ liệu hợp lệ về cú pháp nhưng sai về nghiệp vụ**.
- Writer mới ghi đè mất cập nhật trước đó.
- Lỗi lưu trữ hoặc file bị xóa sau khi công bố.
- Cần rollback sang bản cũ khi một thành phần phụ thuộc V2 không tương thích.

Trong các trường hợp đó, cân nhắc **giữ bản sao V1 độc lập**, lịch sử phiên bản có checksum, hoặc manifest chỉ tới tệp dữ liệu được đặt tên theo version:

```text
data-v1.bin
data-v2.bin
manifest.json  → {"active":"data-v2.bin"}
```

Ý tưởng: ghi và xác nhận file V2 trước, sau đó cập nhật **một manifest nhỏ** bằng temp + atomic replacement. Reader lấy manifest, rồi mở file version tương ứng. Thiết kế này giúp định danh snapshot rõ, nhưng vẫn đòi hỏi chiến lược dọn phiên bản cũ và đảm bảo metadata/durability; một lần thay manifest không giải quyết mọi vấn đề transaction hoặc đồng thời.

Đây là hướng mở rộng phù hợp cho ứng dụng có tệp dữ liệu lớn, reader cần snapshot cố định hoặc rollback; với một file cấu hình nhỏ, giải pháp temp + replace kèm validation có thể đủ.

## 15. Checklist áp dụng trong ứng dụng

Trước khi công bố tệp mới, kiểm tra theo thứ tự:

1. **Xác định đích và thư mục tin cậy:** có quyền tạo temp và replace; thống nhất chính sách symlink.
2. **Tạo temp độc lập trong cùng thư mục:** tránh tên cố định dễ tranh chấp.
3. **Ghi đúng toàn bộ byte:** dùng encoding, định dạng và vòng lặp I/O rõ ràng.
4. **Validate và thiết lập metadata cần thiết:** schema/checksum, quyền/ACL, kích thước.
5. **Đồng bộ temp nếu nghiệp vụ yêu cầu:** `FileChannel.force(true)`, hiểu giới hạn filesystem.
6. **Đóng temp trước khi move.**
7. **Thử công bố theo bảo đảm đã chọn:** strict atomic hoặc policy fallback đã được phê duyệt về mặt thiết kế; không tự xóa đích trước.
8. **Xác nhận trạng thái cuối khi cần:** file đích tồn tại, phiên bản/hash đúng, log kết quả; nhận diện khả năng lỗi xảy ra sau khi đã commit.
9. **Dọn temp còn lại:** `finally` khi chạy bình thường và quy trình startup recovery khi crash.
10. **Điều phối writer/reader:** tránh lost update; reader mở lại khi cần dữ liệu mới.

Với yêu cầu **không bao giờ để reader thấy bản dang dở**, bắt buộc môi trường phải hỗ trợ một cơ chế công bố nguyên tử phù hợp; nếu không thể đáp ứng, từ chối cập nhật hoặc đổi thiết kế lưu trữ. Với yêu cầu **khôi phục qua mất điện**, cần thêm giải pháp bảo đảm durability của filesystem/OS và kiểm thử sự cố, không chỉ dựa vào một lệnh move.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao không ghi trực tiếp nội dung V2 vào file đích V1?  
**Đáp án:** Ghi trực tiếp có thể cắt/ghi dở V1 trước khi V2 hoàn tất. Ghi temp giữ V1 trong suốt giai đoạn xây dựng V2, sau đó mới công bố.

**Câu 2.** Dùng `ATOMIC_MOVE` thì `REPLACE_EXISTING` có chắc chắn buộc thay mục tiêu tồn tại không?  
**Đáp án:** Không. Theo tài liệu `Files.move`, khi có `ATOMIC_MOVE` thì các tùy chọn khác bị bỏ qua; thay thế target hiện hữu phụ thuộc implementation.

**Câu 3.** Sau `channel.force(true)` trên temp và `Files.move(..., ATOMIC_MOVE)` thành công, đã bảo đảm mất điện không thể làm mất tên đích mới chưa?  
**Đáp án:** Chưa thể kết luận portable. Việc đồng bộ directory entry/rename còn phụ thuộc filesystem/OS, trong khi Java chuẩn không bảo đảm directory fsync trên mọi provider.

**Câu 4.** Writer A và B cùng build bản mới từ V1, cả hai atomic replace. Có tránh được lost update không?  
**Đáp án:** Không. Bản publish sau có thể đè bản của writer trước. Cần serialize, version checking hoặc transaction phù hợp.

**Câu 5.** Nếu atomic rename không được hỗ trợ thì luôn dùng `REPLACE_EXISTING` để chương trình tiếp tục được không?  
**Đáp án:** Chỉ khi nghiệp vụ **chấp nhận mất bảo đảm atomic** và đã có phương án đọc/khôi phục tương ứng. Khi yêu cầu nguyên tử bắt buộc, nên báo lỗi.

**Câu 6.** Nếu Java process bị kill giữa lúc ghi temp, `finally` có chắc chạy không?  
**Đáp án:** Không. Cần phương án phát hiện và dọn/khôi phục temp tồn dư sau crash, tránh đụng file đang được writer hợp lệ dùng.

**Câu 7.** Sau atomic replace, một reader đang mở handle tới V1 có nhất thiết thấy V2 ngay khi đọc tiếp không?  
**Đáp án:** Không. Handle cũ có thể tiếp tục tham chiếu V1; reader cần mở lại tên đích nếu muốn snapshot hiện hành.

## 17. Ghi nhớ

- **Viết đủ + kiểm tra tệp tạm trước, thay tên đích sau** giúp tránh công bố file đang ghi dở.
- **Tạo temp cùng thư mục** để tăng khả năng move nguyên tử; dùng `Files.createTempFile` tránh trùng tên.
- **`Files.move(..., ATOMIC_MOVE)` phải được provider hỗ trợ**, và cách xử lý đích tồn tại phụ thuộc implementation. Không âm thầm giả định fallback là nguyên tử.
- **`FileChannel.force(true)` hỗ trợ durability của tệp**, nhưng không đồng nghĩa directory rename đã được flush bền trên mọi nền tảng.
- **Atomic replace không phải transaction, CAS hay khóa nhiều writer**. Cần cơ chế riêng cho consistency, rollback và crash recovery khi bài toán đòi hỏi.

### Tài liệu API Java 17

- [Files.move](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#move(java.nio.file.Path,java.nio.file.Path,java.nio.file.CopyOption...))
- [StandardCopyOption.ATOMIC_MOVE / REPLACE_EXISTING](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html)
- [FileChannel.force](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html#force(boolean))
- [Files.createTempFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#createTempFile(java.nio.file.Path,java.lang.String,java.lang.String,java.nio.file.attribute.FileAttribute...))
