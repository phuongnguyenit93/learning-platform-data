# SYNC, DSYNC, DELETE_ON_CLOSE và tính hỗ trợ của filesystem provider

## 1. Vì sao các tùy chọn mở file này quan trọng?

Khi làm việc với `java.nio.file.Files`, `FileChannel` và các API file khác, ứng dụng không chỉ quyết định **đọc/ghi gì** mà còn có thể chỉ định **cách tệp được mở và duy trì vòng đời** thông qua `OpenOption`. Ba tùy chọn dễ bị hiểu sai là:

- **`StandardOpenOption.SYNC`**: yêu cầu mỗi lần cập nhật **nội dung hoặc metadata** của file được đồng bộ xuống thiết bị lưu trữ bên dưới.
- **`StandardOpenOption.DSYNC`**: yêu cầu mỗi lần cập nhật **nội dung file** được đồng bộ xuống thiết bị lưu trữ bên dưới; khác `SYNC` ở phạm vi metadata.
- **`StandardOpenOption.DELETE_ON_CLOSE`**: yêu cầu provider **cố gắng xóa file khi resource được đóng** (*best effort*), phù hợp chủ yếu cho work file ngắn hạn.

Đây là ba `StandardOpenOption` trong `java.nio.file`, thuộc nhóm **tùy chọn khi mở tệp**. Chúng không biến Java thành hệ thống giao dịch dữ liệu, không tự đảm bảo mọi provider đều hỗ trợ, và không loại bỏ nhu cầu xử lý lỗi I/O.

```text
Chọn OpenOption
       │
       ▼
Files.newByteChannel / Files.newOutputStream / FileChannel.open
       │
       ├─ SYNC: cập nhật content + metadata đồng bộ
       │
       ├─ DSYNC: cập nhật content đồng bộ
       │
       └─ DELETE_ON_CLOSE: yêu cầu xóa khi close (best effort)
       │
       ▼
Filesystem provider + OS + filesystem + thiết bị lưu trữ
       │
       ▼
Kết quả phụ thuộc khả năng và hợp đồng của tầng dưới
```

Hai nhóm vấn đề cần phân biệt:

1. **Durability (độ bền ghi):** sau một lệnh ghi thành công, hệ thống đã yêu cầu dữ liệu được đồng bộ ở mức nào? `SYNC`, `DSYNC` và `FileChannel.force` liên quan tới câu hỏi này.
2. **Lifecycle (vòng đời tệp tạm):** một tệp được tự động yêu cầu xóa vào thời điểm nào, và việc xóa có được bảo đảm tuyệt đối không? `DELETE_ON_CLOSE` liên quan tới câu hỏi này.

Các ví dụ sử dụng **Java 17+**. Hãy nhớ rằng API cho phép *yêu cầu* hành vi; việc mở thành công và mức hỗ trợ thực tế còn liên quan đến provider, filesystem và hệ điều hành.

## 2. StandardOpenOption hoạt động ở đâu?

`StandardOpenOption` là enum triển khai `OpenOption`. Ta có thể chỉ định khi mở tệp bằng một số API, chẳng hạn:

```java
Path file = Path.of("result.bin");

try (OutputStream output = Files.newOutputStream(
        file,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.SYNC)) {
    output.write(new byte[]{1, 2, 3});
}
```

Đây là **đoạn minh họa**, cần import `Path`, `Files`, `OutputStream`, `StandardOpenOption` và xử lý `IOException`. `CREATE` tạo tệp khi thiếu, `WRITE` cho phép ghi, và `SYNC` yêu cầu cập nhật đồng bộ. Nếu file đã tồn tại, ví dụ không dùng `TRUNCATE_EXISTING`; ghi bắt đầu tại vị trí đầu thay vì mặc định xóa sạch nội dung cũ. Trong ví dụ thực tế, phải chọn thêm policy ghi đè/truncate/append có chủ đích.

Các tùy chọn mở file thông dụng:

| OpenOption | Ý nghĩa |
| --- | --- |
| `READ` | Mở để đọc |
| `WRITE` | Mở để ghi |
| `APPEND` | Ghi ở cuối file khi được mở để ghi |
| `TRUNCATE_EXISTING` | Xóa nội dung file hiện có bằng cách đặt kích thước về 0 nếu mở để ghi |
| `CREATE` | Tạo file nếu thiếu |
| `CREATE_NEW` | Tạo file mới, thất bại nếu tên đã tồn tại; kiểm tra tồn tại và tạo là thao tác nguyên tử theo hợp đồng |
| `SYNC` | Đồng bộ cập nhật content hoặc metadata |
| `DSYNC` | Đồng bộ cập nhật content |
| `DELETE_ON_CLOSE` | Cố gắng xóa file khi close |
| `SPARSE` | Gợi ý tạo file sparse; provider có thể bỏ qua khi không hỗ trợ |

**Các OpenOption không hoàn toàn độc lập với nhau.** Một tổ hợp không hợp lệ có thể gây `IllegalArgumentException`; một tùy chọn mà provider không hỗ trợ có thể gây `UnsupportedOperationException`. Ví dụ `FileChannel.open` không cho kết hợp `APPEND` với `READ` hay `TRUNCATE_EXISTING` theo hợp đồng của nó.

## 3. SYNC: đồng bộ nội dung và metadata

`StandardOpenOption.SYNC` quy định yêu cầu **mỗi cập nhật vào nội dung hoặc metadata của file** được ghi đồng bộ tới thiết bị lưu trữ bên dưới.

```java
try (FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE,
        StandardOpenOption.SYNC)) {
    // Ghi dữ liệu vào channel...
}
```

Đây là **đoạn minh họa**, có `Path path` và các import tương ứng. `CREATE_NEW` thất bại nếu file đã tồn tại, giúp tránh vô tình ghi đè; `WRITE` là hướng truy cập; `SYNC` chỉ định yêu cầu đồng bộ.

“Metadata” có thể bao gồm thông tin file như kích thước, thời gian sửa đổi và các thuộc tính liên quan, nhưng phạm vi cập nhật metadata thực tế phụ thuộc filesystem và cách thao tác. `SYNC` có phạm vi rộng hơn `DSYNC`, vì nó không chỉ nói về byte nội dung file.

### SYNC không bảo đảm những gì?

- Không biến nhiều lời gọi `write` thành **một transaction nguyên tử**.
- Không bảo đảm hai thread/process ghi đồng thời sẽ tạo bản ghi không xen kẽ.
- Không đảm bảo dữ liệu ứng dụng hợp lệ nếu định dạng đang ghi dở thì tiến trình bị dừng.
- Không tự sao lưu dữ liệu sang máy khác, không thay cho replication hay backup.
- Không tự khóa file hoặc ngăn sửa đổi bởi tiến trình khác.
- Không loại bỏ khả năng lỗi thiết bị, hỏng phần cứng, mất điện vượt ngoài cam kết của tầng lưu trữ.
- Không chứng minh provider hoặc filesystem thực sự đáp ứng được một yêu cầu mà API không hỗ trợ.

**Đồng bộ (synchronous update) khác với tính nguyên tử (atomicity).** Một lần ghi có thể yêu cầu đồng bộ xuống lưu trữ nhưng ứng dụng vẫn chỉ mới ghi được nửa bản ghi logic nếu lỗi xảy ra trước khi hoàn tất toàn bộ chuỗi ghi.

## 4. DSYNC: đồng bộ nội dung file

`StandardOpenOption.DSYNC` yêu cầu cập nhật **nội dung** file được ghi đồng bộ xuống thiết bị lưu trữ. Khác biệt so với `SYNC` là `DSYNC` không yêu cầu cùng phạm vi metadata theo mô tả của API.

```java
try (FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE,
        StandardOpenOption.DSYNC)) {
    // Ghi byte...
}
```

Đây là ví dụ minh họa, cần import `FileChannel`, `Path`, `StandardOpenOption` và xử lý `IOException`.

Một cách hiểu gần đúng:

- **SYNC:** yêu cầu đồng bộ nội dung **và** metadata liên quan đến cập nhật.
- **DSYNC:** yêu cầu đồng bộ nội dung; không đòi mọi metadata theo cùng mức của SYNC.

Tuy nhiên, trong các filesystem thực tế, một số metadata cần thiết để có thể truy cập lại nội dung đã ghi (ví dụ kích thước file khi append) có thể phải được cập nhật cùng dữ liệu để đáp ứng khả năng phục hồi. Không nên dùng một mô tả đơn giản về metadata để suy ra số lời gọi ghi đĩa hay kết quả crash recovery tuyệt đối trong mọi hệ.

### DSYNC có nhanh hơn SYNC không?

**Có thể**, nếu filesystem/OS có thể tránh đồng bộ một số metadata ở những lần ghi; nhưng đây không phải định lý rằng `DSYNC` luôn nhanh hơn. Kết quả đo phụ thuộc loại thiết bị, filesystem, kích thước/số lần write, ghi append hay overwrite, cache, hệ điều hành và provider.

Nếu hiệu năng quan trọng, benchmark đúng workload và yêu cầu durability của ứng dụng. Đừng chọn DSYNC chỉ vì tên nghe giống tối ưu, khi nghiệp vụ cần metadata được đồng bộ ở mức cao hơn.

## 5. So sánh SYNC và DSYNC bằng bảng quyết định

| Tiêu chí | `SYNC` | `DSYNC` |
| --- | --- | --- |
| Yêu cầu đồng bộ cập nhật nội dung | Có | Có |
| Yêu cầu đồng bộ mọi cập nhật metadata theo mô tả API | Có | Không ở cùng mức SYNC |
| Có phải một lời gọi `flush()` đơn lẻ không? | Không; là option khi mở file | Không; là option khi mở file |
| Bảo đảm giao dịch nguyên tử nhiều bước | Không | Không |
| Thích hợp khi | Muốn phạm vi đồng bộ content + metadata rộng hơn | Muốn tập trung đồng bộ content |
| Luôn chạy trên mọi provider | Không được giả định | Không được giả định |
| Chi phí | Có thể tăng so với ghi không đồng bộ | Cũng có thể tăng; đôi khi nhẹ hơn SYNC |

Trong một hệ thống log hoặc nhật ký giao dịch, lựa chọn giữa SYNC/DSYNC nên dựa trên **yêu cầu mất dữ liệu tối đa có thể chấp nhận**, chính sách crash recovery và hành vi filesystem. Không nên quyết định chỉ dựa trên API mà bỏ qua định dạng record, cách commit hay phục hồi.

## 6. Ví dụ chạy được: ghi qua FileChannel với SYNC

Ví dụ tạo một tệp tạm được kiểm soát, mở nó bằng `SYNC`, ghi UTF-8 và đọc lại để kiểm tra nội dung. Chương trình chỉ chạy qua nhánh thành công khi provider hỗ trợ lựa chọn này.

**Tệp `SyncWriteDemo.java`:**

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class SyncWriteDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("sync-write-", ".txt");
        try {
            byte[] content = "hello".getBytes(StandardCharsets.UTF_8);

            try (FileChannel channel = FileChannel.open(
                    file,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING,
                    StandardOpenOption.SYNC)) {

                ByteBuffer buffer = ByteBuffer.wrap(content);
                while (buffer.hasRemaining()) {
                    channel.write(buffer);
                }
            }

            System.out.println("Content: "
                    + Files.readString(file, StandardCharsets.UTF_8));
            System.out.println("Bytes: " + Files.size(file));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac SyncWriteDemo.java
java SyncWriteDemo
```

**Stdout chính xác nếu thao tác file và SYNC được hỗ trợ, hoàn tất thành công:**

```text
Content: hello
Bytes: 5
```

Giải thích:

1. `Files.createTempFile` tạo một file riêng, tránh đè file của người dùng.
2. `FileChannel.open(file, WRITE, TRUNCATE_EXISTING, SYNC)` mở để ghi và xóa nội dung cũ của file tạm.
3. `ByteBuffer` có vị trí (position) và giới hạn (limit). Vòng `while (buffer.hasRemaining())` đảm bảo xử lý phần byte chưa được channel ghi trong mỗi lần `write`.
4. `try-with-resources` đóng channel ngay khi ghi xong, rồi đọc lại bằng `Files.readString`.
5. File tạm được xóa trong `finally`.

Ví dụ **không chứng minh bằng phép đo** rằng dữ liệu đã được đồng bộ ở phần cứng: nó chỉ dùng đúng API để **yêu cầu** hành vi SYNC. Việc đọc lại thành công không phải phép thử crash recovery; hệ điều hành có thể trả dữ liệu từ cache. Đây là sự khác biệt quan trọng giữa test chức năng và kiểm chứng durability.

## 7. FileChannel.force(boolean) khác gì với SYNC/DSYNC?

`FileChannel.force(boolean metaData)` cho phép ứng dụng **chủ động yêu cầu đồng bộ tại một thời điểm** thay vì yêu cầu mọi cập nhật trên một channel luôn đồng bộ.

```java
try (FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE)) {
    // Ghi nhiều block, có thể có buffer ở tầng ứng dụng.
    channel.force(false); // Yêu cầu đồng bộ nội dung.
    // ...
    channel.force(true);  // Yêu cầu đồng bộ cả nội dung và metadata.
}
```

Đây là đoạn minh họa, không phải chương trình độc lập; `path` đã có và cần các import tương ứng. Nếu dùng wrapper có đệm bên ngoài channel, cần **đưa dữ liệu từ buffer ứng dụng tới channel** trước khi gọi `force`, nếu không những byte còn kẹt trong buffer ứng dụng chưa trở thành cập nhật trên channel.

Các khác biệt chính:

| Nhu cầu | Lựa chọn |
| --- | --- |
| Mỗi cập nhật content/metadata phải được yêu cầu đồng bộ | Mở file với `SYNC` |
| Mỗi cập nhật content phải được yêu cầu đồng bộ | Mở file với `DSYNC` |
| Ghi nhiều phần rồi đồng bộ tại checkpoint/commit | `FileChannel.force(false/true)` |

`force(false)` tập trung vào content; `force(true)` yêu cầu cả metadata. Theo tài liệu `FileChannel`, cam kết đồng bộ khi trả về được nêu cho tệp nằm trên **thiết bị lưu trữ cục bộ**; với tệp trên thiết bị không cục bộ, tài liệu **không đưa cùng một bảo đảm**. Hành vi thực tế của tham số metadata còn phụ thuộc hệ điều hành.

`force()` được đảm bảo trong phạm vi các cập nhật thực hiện qua những phương thức của channel; với cập nhật qua `MappedByteBuffer`, có thể cần `MappedByteBuffer.force()` theo hợp đồng riêng. Đừng coi `channel.force()` là lời gọi có thể ép đồng bộ mọi cache và mọi writer trong toàn JVM.

### force() có thay cho close() không?

Không. `force` yêu cầu cập nhật dữ liệu, còn `close` giải phóng resource/channel. Chương trình vẫn phải đóng channel bằng `try-with-resources`. Ngược lại, **đóng channel không tự đồng nghĩa** với một cam kết durability tương đương `SYNC` hoặc `force(true)` trong mọi môi trường.

## 8. DELETE_ON_CLOSE: yêu cầu xóa khi đóng, không phải bảo đảm tuyệt đối

`StandardOpenOption.DELETE_ON_CLOSE` yêu cầu implementation **cố gắng xóa file khi channel/stream phù hợp được đóng**. Đây là cơ chế rất hữu ích cho một số **work file** chỉ dùng trong một JVM.

Theo hợp đồng của Java:

- Khi option được chỉ định, implementation thực hiện **best effort** để xóa tệp trong quá trình `close()`.
- Nếu `close()` không được gọi, JVM có thể thực hiện một nỗ lực best effort khi kết thúc, trong điều kiện có thể.
- Thời điểm xóa, cách xóa và nhiều chi tiết khác là **implementation-specific**.
- Không nên dùng tùy tiện cho file đang được các thực thể khác mở đồng thời.
- Một số hệ điều hành không cho phép xóa file đang được process khác sử dụng theo cách nhất định.
- Với một số provider, option có thể hàm ý không theo symbolic link vì lý do bảo mật, và việc mở một link có thể thất bại.

Từ khóa quan trọng nhất là **best effort**. `DELETE_ON_CLOSE` **không phải bằng chứng chắc chắn file đã biến mất**, không đảm bảo secure erase và không thay thế chính sách quản lý tệp tạm.

### Tại sao DELETE_ON_CLOSE cần close đúng?

Nếu lập trình viên quên đóng stream, thời điểm file được yêu cầu xóa trở nên khó đoán. Ví dụ sau đáng lo ngại:

```java
OutputStream out = Files.newOutputStream(
        tempPath,
        StandardOpenOption.WRITE,
        StandardOpenOption.DELETE_ON_CLOSE);
// ...
// Quên close: file có thể không được dọn ngay.
```

Đây là đoạn minh họa, không phải cách viết khuyến nghị. Ưu tiên:

```java
try (OutputStream out = Files.newOutputStream(
        tempPath,
        StandardOpenOption.WRITE,
        StandardOpenOption.DELETE_ON_CLOSE)) {
    // Ghi dữ liệu tạm.
}
```

Đây là đoạn minh họa với file đã tồn tại hợp lệ. Resource được đóng theo scope, kích hoạt hành vi xóa best effort.

### Có nên áp dụng cho mọi file tạm?

Không nhất thiết. Nếu file cần mở lại sau khi đóng một channel, hoặc cần được một tiến trình khác sử dụng, `DELETE_ON_CLOSE` có thể xóa nó sớm hơn mong muốn. Đối với file tạm dùng chung giữa nhiều process, cần giao kèo về lifecycle rõ ràng.

## 9. Ví dụ chạy được: DELETE_ON_CLOSE với file tạm riêng

**Tệp `DeleteOnCloseDemo.java`:**

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.EnumSet;

public class DeleteOnCloseDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("delete-on-close-");
        Path file = directory.resolve("scratch.bin");

        try {
            try (SeekableByteChannel channel = Files.newByteChannel(
                    file,
                    EnumSet.of(
                            StandardOpenOption.CREATE_NEW,
                            StandardOpenOption.WRITE,
                            StandardOpenOption.DELETE_ON_CLOSE))) {
                channel.write(ByteBuffer.wrap(new byte[]{1, 2, 3}));
                System.out.println("Open in scope: " + channel.isOpen());
            }

            System.out.println("Exists after close: " + Files.exists(file));
        } finally {
            // Dự phòng khi provider không thể xóa ngay.
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac DeleteOnCloseDemo.java
java DeleteOnCloseDemo
```

**Stdout thường thấy trên provider hỗ trợ và xóa được khi close:**

```text
Open in scope: true
Exists after close: false
```

Ở đây dùng `CREATE_NEW` để chỉ tạo một file mới trong thư mục tạm, `WRITE` để ghi byte, và `DELETE_ON_CLOSE` để yêu cầu dọn. **Không kiểm tra `Files.exists(file)` khi channel còn mở**, vì provider có thể có thời điểm xóa khác nhau. Sau khi đóng, `Files.exists(file)` thường là `false` khi xóa thành công, nhưng không nên viết test portable đòi luôn nhận kết quả này trên mọi provider.

Khối `finally` vẫn có `Files.deleteIfExists` như phương án dọn dẹp rõ ràng. Nếu provider không hỗ trợ option, việc mở có thể ném `UnsupportedOperationException` hoặc ngoại lệ thích hợp; chương trình không âm thầm bỏ option rồi tuyên bố đã xóa.

**Lưu ý:** `Files.exists(file)` trả `false` cả trong một số trường hợp không xác định được sự tồn tại do lỗi truy cập; không coi một phép kiểm tra này là bằng chứng pháp lý về việc mọi bản sao dữ liệu đã bị xóa hoàn toàn khỏi thiết bị.

## 10. Best effort không đồng nghĩa secure delete

Một sai lầm nguy hiểm là xem `DELETE_ON_CLOSE` như thao tác **xóa dữ liệu nhạy cảm không thể phục hồi**. API chỉ nói về cố gắng xóa file entry, không đưa cam kết xóa vật lý toàn bộ block trên ổ đĩa, bản sao cache, snapshot, backup, SSD wear leveling hoặc nội dung trên filesystem từ xa.

Với dữ liệu nhạy cảm, cần thiết kế theo chính sách bảo mật của hệ thống: hạn chế quyền truy cập, tránh ghi ra file không cần thiết, chọn lưu trữ mã hóa và quản lý khóa phù hợp. `DELETE_ON_CLOSE` có thể là một thành phần dọn dẹp, không phải toàn bộ giải pháp.

Cũng không thể giả định JVM luôn thực hiện được hành vi khi kết thúc bất thường (mất nguồn điện, lỗi kernel hoặc process bị kill không cho chạy cleanup). Vì vậy file tạm quan trọng có thể cần cơ chế quét dọn theo tuổi hoặc cơ chế quản lý khác ngoài quy trình đóng thông thường.

## 11. Files.createTempFile khác DELETE_ON_CLOSE

`Files.createTempFile` tạo một tệp với tên mới, thường trong thư mục tạm. Bản thân phương thức này **không tự đặt chính sách xóa khi đóng các stream đọc/ghi sau đó**.

```java
Path temp = Files.createTempFile("job-", ".bin");
try {
    // Mở, đọc/ghi file temp.
} finally {
    Files.deleteIfExists(temp);
}
```

Đây là đoạn minh họa, xử lý `IOException`. Nếu cần mở file với `DELETE_ON_CLOSE` sau khi tạo temp file, có thể dùng option ấy khi mở channel/stream, nhưng nhớ rằng file có thể không còn truy cập qua tên khi một provider xử lý xóa sớm.

Điều kiện chọn:

| Nhu cầu | Hướng tiếp cận |
| --- | --- |
| File tạm được mở một lần, chỉ cần tồn tại trong scope | Có thể dùng `DELETE_ON_CLOSE` nếu provider hỗ trợ |
| File phải đóng rồi mở lại nhiều lần | Quản lý `Files.createTempFile` và xóa chủ động |
| File phải chia sẻ cho process khác | Tránh `DELETE_ON_CLOSE` nếu lifecycle không tương thích |
| File phải phục hồi sau crash hoặc được audit | Cần chính sách lưu trữ/dọn dẹp riêng |
| Dữ liệu nhạy cảm phải xóa an toàn | `DELETE_ON_CLOSE` không đủ để cam kết secure erase |

## 12. Provider là gì và tại sao tính hỗ trợ không đồng nhất?

Java NIO.2 cho phép nhiều **filesystem provider** thông qua `java.nio.file.spi.FileSystemProvider`. Một `Path` gắn với một `FileSystem` cụ thể; những thao tác như `Files.newByteChannel(path, options)` được chuyển tới provider của Path.

Các ví dụ bối cảnh provider:

- Filesystem mặc định của hệ điều hành.
- ZIP/JAR filesystem (ví dụ qua `FileSystems.newFileSystem`).
- Một số provider do thư viện/ứng dụng bổ sung để truy cập lưu trữ khác.

Tính năng mà filesystem mặc định hỗ trợ không có nghĩa provider ZIP hoặc provider tùy chỉnh hỗ trợ giống hệt. Provider có thể hỗ trợ `CREATE_NEW` nhưng không hỗ trợ `SYNC`, hoặc không cung cấp `FileChannel` cho mọi loại Path.

**Khả năng hỗ trợ là một phần của hợp đồng runtime.** Nếu người dùng yêu cầu tính bền ghi cao, ứng dụng cần chọn chiến lược có thể xác minh trên provider đang dùng, hoặc **báo lỗi rõ ràng** khi không thể đáp ứng. Không âm thầm bỏ `SYNC` để ghi theo cách thường rồi nói rằng dữ liệu đã được đồng bộ.

### Cách nhận diện provider trong code

```java
FileSystemProvider provider = path.getFileSystem().provider();
System.out.println(provider.getClass().getName());
```

Đây là đoạn minh họa, cần import `Path`, `FileSystemProvider`. Tên class chỉ giúp biết provider đang được dùng; **không chứng minh mọi tùy chọn mở file đều được hỗ trợ**. Provider có thể phụ thuộc filesystem mount, hệ điều hành và các ràng buộc cụ thể của file.

## 13. Lỗi cần dự liệu khi mở với tùy chọn đặc biệt

Khi gọi `FileChannel.open(path, options)` hoặc `Files.newByteChannel`, các nhóm lỗi đáng chú ý:

| Tình huống | Ngoại lệ/cách xử lý |
| --- | --- |
| Tùy chọn không được provider hỗ trợ | `UnsupportedOperationException` |
| Tổ hợp tùy chọn không hợp lệ | `IllegalArgumentException` |
| Tệp đã tồn tại và mở `CREATE_NEW` | Có thể có `FileAlreadyExistsException` |
| Không thể mở/ghi/xóa file vì I/O | `IOException` hoặc subclass |
| Không đủ quyền truy cập | Có thể `AccessDeniedException`, `SecurityException` tùy API/môi trường |
| Đóng resource lỗi | `IOException` cần xử lý; try-with-resources giữ suppressed exception khi có lỗi chính |
| File bị process khác giữ hoặc provider không thể xóa | Tùy cơ chế filesystem; không hứa `DELETE_ON_CLOSE` luôn thành công |

**`UnsupportedOperationException` và `IllegalArgumentException` là unchecked**, nên một khối `catch(IOException)` **không bắt tất cả lỗi cấu hình option**. Cần nhận diện chúng nếu ứng dụng định làm fallback hoặc báo thông điệp rõ.

Không nên catch chung mọi exception rồi tiếp tục ghi như không có vấn đề. Với ứng dụng cần durability, nếu provider từ chối `SYNC`, việc bỏ nó đi là **thay đổi yêu cầu dữ liệu**, phải được quyết định có chủ đích.

## 14. Fallback khi provider không hỗ trợ: lựa chọn nghiệp vụ

Giả sử ứng dụng muốn mở channel với `SYNC`. Có một số chính sách:

1. **Fail closed:** nếu provider không hỗ trợ, từ chối thao tác. Phù hợp khi đồng bộ là yêu cầu bắt buộc.
2. **Chuyển sang DSYNC:** chỉ hợp lệ khi nghiệp vụ đã chấp nhận mức metadata khác và DSYNC được hỗ trợ; không coi hai option hoàn toàn tương đương.
3. **Mở channel bình thường rồi gọi `force(true)` ở checkpoint:** phù hợp với một số thiết kế commit nhưng thay đổi đặc tính “mỗi cập nhật đồng bộ” thành “đồng bộ theo lô”; cần tài liệu hóa và kiểm thử.
4. **Giảm yêu cầu để ghi best-effort:** chỉ dành cho dữ liệu mà mất mát có thể chấp nhận; phải thông báo chính sách, không giả vờ có durability như trước.

Một đoạn khung lựa chọn:

```java
try (FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.WRITE,
        StandardOpenOption.SYNC)) {
    // Ghi theo yêu cầu SYNC.
} catch (UnsupportedOperationException unsupported) {
    throw new IllegalStateException(
            "Configured filesystem cannot satisfy required SYNC", unsupported);
}
```

Đây là đoạn minh họa trong ứng dụng đã xác định `Path path` hợp lệ và xử lý `IOException`. Thông điệp báo rõ rằng lựa chọn đồng bộ bắt buộc không thể đáp ứng. Không tự mở lại với `WRITE` thường nếu nghiệp vụ cần cam kết SYNC.

**Kiểm thử hỗ trợ:** một “probe” mở file tạm với option có thể cho biết provider/filesystem đang chấp nhận cấu hình trong điều kiện hiện tại. Nhưng nó không chứng minh mọi file và mọi mount đều hỗ trợ giống nhau, hoặc đảm bảo các tình huống phần cứng/OS bất thường. Luôn xử lý lỗi tại **thao tác thật**, không chỉ ở lúc khởi động.

## 15. Tùy chọn nào có ở Files API và FileChannel?

Không nên mặc định mọi API đều cho phép mọi OpenOption trong mọi cấu hình. Ví dụ:

- `Files.newOutputStream(path, options...)` nhận `OpenOption`, có các default khi không đưa option.
- `Files.newByteChannel(path, options, attrs...)` cho thao tác read/write qua `SeekableByteChannel`.
- `FileChannel.open(path, options...)` có tập option được mô tả rõ, bao gồm `SYNC`, `DSYNC`, `DELETE_ON_CLOSE`.
- `Files.writeString(path, text, charset, options...)` cho phép định nghĩa cách mở file nhưng các option được hỗ trợ cần kiểm tra tài liệu API cụ thể; không suy ra mọi tùy chọn đặc biệt từ `FileChannel` sẽ hợp lệ trên tất cả provider.
- `Files.copy` và `Files.move` có các `CopyOption` riêng; không nhầm với `StandardOpenOption`.

**Đặc biệt:** khi gọi `Files.newOutputStream(path)` mà **không có option**, phương thức dùng ngữ nghĩa mở ghi mặc định, thường tương đương `CREATE`, `TRUNCATE_EXISTING`, `WRITE`. Nhưng một khi truyền option một cách tường minh, phải hiểu tập option đang chỉ định và tác động tới việc tạo/truncate file.

## 16. Một ví dụ kết hợp DSYNC và FileChannel.force

Nếu cần minh họa hai cách yêu cầu đồng bộ, có thể dùng chương trình nhỏ sau để ghi một file mới với DSYNC, rồi dùng một file khác với `force(true)` theo đợt.

**Tệp `DsyncVsForceDemo.java`:**

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class DsyncVsForceDemo {
    static void writeAll(FileChannel channel, byte[] bytes) throws IOException {
        ByteBuffer buffer = ByteBuffer.wrap(bytes);
        while (buffer.hasRemaining()) {
            channel.write(buffer);
        }
    }

    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("durability-demo-");
        Path dsyncFile = directory.resolve("dsync.txt");
        Path forcedFile = directory.resolve("forced.txt");

        try {
            try (FileChannel channel = FileChannel.open(
                    dsyncFile,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.DSYNC)) {
                writeAll(channel, "one".getBytes(StandardCharsets.UTF_8));
            }

            try (FileChannel channel = FileChannel.open(
                    forcedFile,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE)) {
                writeAll(channel, "two".getBytes(StandardCharsets.UTF_8));
                channel.force(true);
            }

            System.out.println("DSYNC content: "
                    + Files.readString(dsyncFile, StandardCharsets.UTF_8));
            System.out.println("force content: "
                    + Files.readString(forcedFile, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(dsyncFile);
            Files.deleteIfExists(forcedFile);
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac DsyncVsForceDemo.java
java DsyncVsForceDemo
```

**Stdout nếu provider hỗ trợ các thao tác và chương trình thành công:**

```text
DSYNC content: one
force content: two
```

Ví dụ không đo độ trễ và không mô phỏng crash. Mục đích là thấy **cách đặt yêu cầu**:

- File thứ nhất mở với DSYNC từ đầu, nên từng cập nhật content trên channel chịu yêu cầu tương ứng.
- File thứ hai mở ghi thông thường, rồi `force(true)` được gọi tại checkpoint cuối để yêu cầu đồng bộ nội dung và metadata.

Nếu mục tiêu là độ bền ghi của nhiều tệp cùng lúc hoặc các thao tác metadata ở thư mục, các lời gọi này đơn lẻ không chứng minh toàn bộ transaction nhiều bước sẽ khôi phục nguyên tử sau crash.

## 17. SYNC/DSYNC và atomicity: đừng nhầm với ATOMIC_MOVE

Trong Java NIO, `StandardCopyOption.ATOMIC_MOVE` dành cho di chuyển/đổi tên file theo cơ chế atomic move khi provider hỗ trợ. Nó giải quyết **khía cạnh đổi tên nguyên tử**, trong khi `SYNC`/`DSYNC` là yêu cầu **đồng bộ cập nhật file**.

```text
Ghi file tạm       ───► đồng bộ content (theo policy)
       │
       ▼
Đóng file tạm
       │
       ▼
Đổi tên / move tới file đích ───► có thể yêu cầu atomic move
       │
       ▼
Cân nhắc durability của metadata thư mục / filesystem
```

Ngay cả khi một file đã được ghi đồng bộ, bước **rename** có thể có yêu cầu riêng về độ bền của entry thư mục. Một giao dịch crash-safe cần hiểu filesystem, hành vi directory metadata và cơ chế phục hồi, không chỉ thêm `SYNC` hoặc `ATOMIC_MOVE` một cách cơ học.

`ATOMIC_MOVE` có thể gây `AtomicMoveNotSupportedException` nếu không được hỗ trợ. Không nên tự fallback sang move thường rồi khẳng định thao tác vẫn atomic. Việc file được tạo bằng `DELETE_ON_CLOSE` thường còn làm phức tạp quy trình đổi tên vì mục đích option đó là xóa work file khi close.

## 18. Logging, hiệu năng và tính nhất quán

Yêu cầu đồng bộ sau mỗi cập nhật có thể tốn chi phí lớn. Ví dụ một service ghi 10.000 record nhỏ mà mỗi record có một syscall/write đồng bộ có thể khác hẳn mô hình gom nhiều record rồi force tại những điểm commit.

**Nhưng batching có đánh đổi:** nếu chờ một khoảng thời gian rồi mới `force`, dữ liệu ở giữa các checkpoint có thể bị mất khi hệ thống bị lỗi. Chọn phương án theo yêu cầu của nghiệp vụ:

| Đặc tính mong muốn | Hướng triển khai thường gặp |
| --- | --- |
| Ưu tiên ghi tuần tự nhanh, có thể chấp nhận mất một ít dữ liệu | Buffered writes + checkpoints theo lô |
| Mỗi cập nhật cần mức đồng bộ cao hơn | `SYNC` hoặc `DSYNC` theo policy |
| Muốn kiểm soát thời điểm đồng bộ tại transaction boundary | `FileChannel.force(true/false)` |
| Cần thay thế file cấu hình nguyên tử | Tệp tạm + move atomic khi hỗ trợ + kế hoạch durability riêng |
| Cần file tạm dùng một lần tự dọn | `DELETE_ON_CLOSE` nếu phù hợp và được hỗ trợ |

Đừng đo tốc độ `Files.writeString` rồi suy ra trực tiếp về mọi chế độ mở file. Benchmark nên dùng đúng loại tệp, kích thước record, filesystem, máy thật và chế độ durability.

## 19. Quan hệ với try-with-resources và wrapper streams

Các option như `DELETE_ON_CLOSE` có tác dụng ở **resource được mở**. Nếu output stream được bọc bằng `BufferedOutputStream`, việc đóng wrapper ngoài thường đóng delegate bên dưới, từ đó kích hoạt hành vi xóa best effort.

```java
try (OutputStream output = new BufferedOutputStream(
        Files.newOutputStream(temp,
                StandardOpenOption.WRITE,
                StandardOpenOption.DELETE_ON_CLOSE))) {
    output.write(payload);
}
```

Đây là đoạn minh họa với file tạm `temp` đã tồn tại và `byte[] payload`, cần import liên quan. `BufferedOutputStream` có thể giữ dữ liệu trong RAM đến khi flush/close, trong khi `SYNC`/ `DSYNC` ở resource tầng dưới chỉ liên quan đến **cập nhật đã thực sự đến tầng file**. Nếu cần cam kết về thời điểm đồng bộ, hãy kiểm soát thứ tự flush của wrapper trước khi đồng bộ channel thích hợp.

Nếu resource là **tài nguyên do caller sở hữu**, không được tự ý đóng chỉ để kích hoạt `DELETE_ON_CLOSE`; phải làm rõ quyền sở hữu. Đặc biệt không bọc `System.out` hoặc các stream chia sẻ rồi gọi `close()` tùy tiện.

## 20. Các lỗi phổ biến

| Nhầm lẫn | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| `SYNC` chỉ giống `flush()` | Flush xử lý buffer ứng dụng; SYNC là open option về đồng bộ cập nhật file | Phân biệt tầng buffer và thiết bị |
| `DSYNC` và `SYNC` giống nhau hoàn toàn | Metadata nằm trong phạm vi khác nhau | Chọn theo policy content/metadata |
| DSYNC luôn nhanh hơn SYNC | Hiệu năng phụ thuộc workload/provider/OS | Đo trên môi trường thật |
| SYNC bảo đảm toàn bộ transaction nhiều file là atomic | Không có cơ chế transaction tổng quát | Thiết kế commit/rename/recovery riêng |
| Gọi `FileChannel.force(false)` đồng bộ cả mọi metadata | `false` chỉ yêu cầu content | Dùng `true` khi cần metadata theo hợp đồng |
| `DELETE_ON_CLOSE` luôn xóa tệp tức thì | Chỉ best effort, thời điểm implementation-specific | Quản lý cleanup và xác minh phù hợp |
| DELETE_ON_CLOSE là secure erase | Không bảo đảm xóa vật lý/backup | Có chính sách bảo mật dữ liệu riêng |
| `Files.createTempFile` tự xóa khi close bất kỳ stream nào | Không có policy xóa mặc định như vậy | Xóa chủ động hoặc mở với option phù hợp |
| Mọi provider hỗ trợ SYNC/DSYNC/DELETE_ON_CLOSE | Không bảo đảm | Xử lý `UnsupportedOperationException` |
| Chỉ catch `IOException` là đủ cho mọi open-option error | Tùy chọn không hợp lệ có thể gây unchecked | Kiểm tra `IllegalArgumentException`, `UnsupportedOperationException` |
| Thử một lần ở khởi động là chứng minh vĩnh viễn | Filesystem/mount có thể khác hoặc thay đổi | Xử lý lỗi ở thao tác thực |
| Fallback bỏ SYNC nhưng vẫn báo “durable” | Thay đổi hợp đồng durability | Fail hoặc ghi rõ giảm yêu cầu |
| Chọn APPEND/TRUNCATE tùy tiện khi kết hợp option | Có tổ hợp không hợp lệ hoặc semantics khác | Đọc hợp đồng API và test |
| Chỉ đọc file lại để kiểm tra durability | OS cache có thể cho kết quả đọc đúng | Phân biệt chức năng và crash recovery |

## 21. Bài tập thực hành

1. Chạy `SyncWriteDemo` trên hệ điều hành/provider của bạn. Quan sát kết quả rồi giải thích vì sao đọc lại nội dung thành công không chứng minh crash durability.
2. Thay `SYNC` bằng `DSYNC` trong `SyncWriteDemo`. Kiểm tra output và nêu sự khác biệt trong phạm vi cam kết metadata.
3. Chạy `DsyncVsForceDemo`, thử `channel.force(false)` thay `true`; giải thích ý nghĩa của tham số.
4. Đo thời gian ghi nhiều record nhỏ với ghi thường, DSYNC và SYNC. Ghi rõ máy, filesystem, số lần ghi và cảnh báo cache/benchmark.
5. Chạy `DeleteOnCloseDemo`, in trạng thái tồn tại trước/sau `close()` trên provider hiện tại và đối chiếu với ý nghĩa best effort.
6. Bỏ `try-with-resources` trong `DeleteOnCloseDemo` và giải thích vì sao vòng đời file trở nên không đáng tin cậy; sau đó khôi phục cách đúng.
7. Tạo file tạm bằng `Files.createTempFile` mà không dùng DELETE_ON_CLOSE. Xác nhận việc đóng `OutputStream` bình thường không đồng nghĩa xóa file.
8. Viết test với `CREATE_NEW`: mở một file đã tồn tại và xác nhận lỗi; giải thích vì sao tùy chọn này hữu ích tránh ghi đè.
9. Thử một provider khác (ví dụ ZIP filesystem nếu môi trường có hỗ trợ). Ghi nhận nếu `SYNC` hoặc `DELETE_ON_CLOSE` bị từ chối; không bỏ qua lỗi một cách im lặng.
10. Thiết kế một chính sách fallback: nếu SYNC bị từ chối, service nên từ chối thao tác hay có thể giảm yêu cầu? Giải thích tác động nghiệp vụ.
11. Giải thích tại sao một `BufferedOutputStream` chưa flush không thể được đồng bộ xuống đĩa chỉ bằng việc yêu cầu một `FileChannel` khác force dữ liệu của nó.
12. Phân biệt `DELETE_ON_CLOSE` với file deletion an toàn đối với dữ liệu nhạy cảm.
13. Thiết kế quy trình thay thế file cấu hình: tệp tạm, ghi, đồng bộ, đóng, move và cleanup. Nêu rõ giới hạn `ATOMIC_MOVE` cũng như durability của metadata thư mục.
14. Giải thích vì sao việc provider chấp nhận mở file với `SYNC` không có nghĩa ứng dụng tự động có transaction và recovery logic.

## 22. Ghi nhớ

`SYNC`, `DSYNC` và `DELETE_ON_CLOSE` là những **yêu cầu về cách mở và quản lý tệp**, được thực hiện bởi provider/OS/filesystem với những giới hạn cụ thể.

1. **SYNC:** yêu cầu cập nhật content hoặc metadata đồng bộ xuống thiết bị lưu trữ.
2. **DSYNC:** yêu cầu cập nhật content đồng bộ; không đồng nhất phạm vi metadata với SYNC.
3. **DELETE_ON_CLOSE:** yêu cầu xóa file khi đóng trên cơ sở **best effort**, không phải bảo đảm xóa chắc chắn hoặc secure erase.
4. **FileChannel.force():** cho phép yêu cầu đồng bộ tại thời điểm được chọn; cần hiểu giới hạn thiết bị local/non-local và metadata.
5. **Provider support:** không coi các tùy chọn là phổ quát. Xử lý `UnsupportedOperationException`, `IllegalArgumentException`, `IOException` theo hợp đồng, không âm thầm thay đổi yêu cầu durability.
6. **Đúng lifecycle:** luôn đóng resource do mình sở hữu bằng `try-with-resources`; đừng dựa vào finalizer hoặc thời điểm JVM thoát để xóa file tạm.
7. **Đúng kiến trúc:** synchronous updates khác atomicity; một file hoặc nhiều file cần recovery protocol tùy bài toán.

### Tài liệu tham khảo chính thức

- [Java SE 17: `StandardOpenOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html), phần SYNC, DSYNC và DELETE_ON_CLOSE.
- [Java SE 17: `FileChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html), các overload `open` và `force(boolean)`.
- [Java SE 17: `Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html), các hàm mở/ghi/xóa file.
- [Java SE 17: `FileSystemProvider`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/spi/FileSystemProvider.html), điểm mở rộng hệ thống tệp.
- [Java SE 17: `StandardCopyOption.ATOMIC_MOVE`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html), phân biệt atomic move với chính sách ghi đồng bộ.
