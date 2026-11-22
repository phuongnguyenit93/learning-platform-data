# Xử lý lỗi từng bước trong các thao tác nhiều tệp với Java NIO.2

## 1. Vấn đề: một thao tác nhiều tệp không phải một giao dịch nguyên tử

Một chức năng Java có thể cần **sao chép 50 tệp**, **đổi tên hàng loạt**, **xuất nhiều tài liệu** hoặc **di chuyển nhiều ảnh** sang thư mục đích. Nếu tệp thứ 37 gặp lỗi, điều gì xảy ra với 36 tệp đã xử lý trước đó? Nếu một thao tác chỉ hoàn tất một phần, chương trình biết trạng thái nào để khôi phục?

Các lời gọi như `Files.copy`, `Files.move`, `Files.delete` và `Files.write` vận hành với **một đối tượng đường dẫn ở mỗi lần gọi**. Lặp nhiều lời gọi **không tự biến thành một transaction**: lỗi ở bước sau không tự đảo ngược các bước trước. Một lệnh copy/move cá biệt cũng có những ràng buộc về trạng thái sau lỗi, nhất là qua filesystem khác nhau.

Ví dụ:

```text
Nguồn:     a.txt    b.txt    c.txt
             |        |        |
Bước:       COPY     COPY     COPY
             OK       OK       LỖI
Đích:      a.txt    b.txt     (thiếu)
```

Chương trình cần biết **đích đang ở trạng thái nào** và ứng dụng yêu cầu:

- **Fail-fast:** dừng ngay ở lỗi đầu tiên, thường dùng khi cần một tập đầu ra đầy đủ và nhất quán.
- **Best-effort:** tiếp tục với các tệp độc lập, ghi nhận thành công/thất bại riêng cho từng tệp.
- **Staging + publish:** chuẩn bị các tệp tạm, xác minh trước, rồi công bố kết quả; nếu lỗi thì dọn phần đã tạo khi an toàn.
- **Khôi phục sau crash:** dùng manifest/journal và quy trình phục hồi nếu cần xử lý cả trường hợp tiến trình bị tắt đột ngột.

Bài học thuộc nhóm **Thao tác tệp** của Java Core I/O. Mục tiêu là thiết kế **các bước rõ ràng, phạm vi quyền sở hữu, khả năng phục hồi, quan sát lỗi và trách nhiệm dọn dẹp** thay vì chỉ đặt một khối `try/catch` quanh toàn bộ vòng lặp.

## 2. Xác định yêu cầu trước khi viết code

Trước tiên trả lời các câu hỏi:

1. **Đầu ra phải đủ bộ hay chấp nhận thiếu tệp?** Ví dụ bản phát hành cần 100% thành phần; tác vụ copy ảnh cá nhân có thể cho phép 97/100 thành công.
2. **Đã có tệp đích chưa?** Có được ghi đè không, hay tuyệt đối phải giữ bản cũ?
3. **Có tiến trình khác truy cập/cập nhật thư mục không?** Nếu có, việc kiểm tra tồn tại trước khi ghi không chặn được race.
4. **Các tệp có liên hệ với nhau không?** Một bộ metadata + payload cần đồng nhất; nhiều bản ghi log độc lập có thể xử lý riêng.
5. **Độ lớn, số lượng và vị trí tệp?** Hàng chục tệp nhỏ trên cùng filesystem khác hàng triệu tệp lớn trải nhiều volume hoặc cloud storage.
6. **Lỗi nào có thể thử lại?** Hết quyền truy cập khác mạng gián đoạn; retry phải tính tới việc tệp đích có thể đã tồn tại một phần.
7. **Khi lỗi xảy ra, điều gì được phép xóa?** Chỉ được dọn tài nguyên do chính lần chạy **sở hữu**, không xóa dữ liệu có sẵn của người dùng.
8. **Đầu ra xuất hiện với người đọc ở thời điểm nào?** Ghi trực tiếp ra tên cuối khiến người khác có thể đọc bản chưa đầy đủ.

Đối với tác vụ nhiều tệp, cần chọn một **chính sách thành công** có thể kiểm chứng, không chỉ “vòng lặp chạy xong không ném ngoại lệ”.

### 2.1. Bảng chọn chiến lược

| Yêu cầu | Chiến lược bắt đầu | Giới hạn |
| --- | --- | --- |
| Mọi tệp phải được chuẩn bị thành công | Fail-fast khi chuẩn bị, sau đó publish | Công bố nhiều tệp vẫn không tự atomic |
| Các tệp độc lập, cho phép thất bại riêng | Best-effort và kết quả từng tệp | Người gọi phải biết bản nào thất bại |
| Không được đụng tới bản đích đang có | `CREATE_NEW` hoặc copy/move không `REPLACE_EXISTING`; kiểm tra phù hợp | Vẫn cần xử lý race, ngoại lệ |
| Giữ bản cũ nếu tạo bản mới thất bại | Staging trong thư mục riêng, xác minh rồi chuyển | Đổi nhiều tệp không có transaction chung |
| Dừng/crash giữa quy trình vẫn phải phục hồi | Manifest/journal, idempotency, recovery | Tăng độ phức tạp và cần thiết kế dữ liệu |
| File đơn lẻ cần đổi tên nguyên tử nếu có hỗ trợ | `Files.move` với `ATOMIC_MOVE` | Chỉ phạm vi từng move, provider có thể không hỗ trợ |
| Sao chép nhiều tệp lớn | Streaming, quota, giới hạn đồng thời | Không đọc hết file vào heap |
| Nhiều writer cùng cập nhật cùng thư mục | Đồng bộ giao thức hoặc khóa thích hợp | Kiểm tra `exists` trước thao tác không đủ |

## 3. Phân tách quy trình thành các giai đoạn

Một thiết kế thực dụng gồm bốn giai đoạn:

```text
PLAN / VALIDATE
  │ Kiểm tra nguồn, đích, trùng tên, quyền, quota dự kiến
  ▼
STAGE
  │ Tạo tệp tạm trong vùng mình quản lý; copy/ghi; checksum nếu cần
  ▼
VERIFY
  │ Xác minh số file, kích thước, checksum/định dạng theo yêu cầu
  ▼
PUBLISH
  │ Chuyển sang tên chính thức, cập nhật manifest/điểm công bố
  ▼
CLEANUP / RECOVERY
    Dọn tạm, tổng hợp lỗi, khôi phục khi khả thi
```

Các bước chuẩn bị giúp giảm rủi ro nhưng **không loại bỏ mọi race**. Ví dụ `Files.exists(source)` trả `true` hôm nay không đảm bảo `Files.copy(source, target)` thành công ngay sau đó; nguồn có thể bị xóa/đổi tên hoặc bị đổi quyền giữa hai lời gọi. Vì vậy **thao tác thực tế vẫn phải bắt và phân loại lỗi**.

### 3.1. Lập kế hoạch trước khi tác động filesystem

Một bản kế hoạch (plan) cho mỗi tệp có thể gồm:

| Trường | Ý nghĩa |
| --- | --- |
| Source | `Path` của nguồn |
| Destination | `Path` đích cuối, đã quyết định tên |
| Stage | `Path` tạm do tác vụ này tạo |
| Expected length/hash | Kích thước hoặc checksum nếu có hợp đồng kiểm tra |
| State | `PLANNED`, `STAGED`, `VERIFIED`, `PUBLISHED`, `FAILED`, `CLEANED` |
| Error | Loại ngoại lệ, bước xảy ra, thông điệp và nguyên nhân |
| Owned by task? | Có được phép xóa trong rollback không |

Nên **phát hiện đích trùng nhau** trong danh sách trước khi chạy; ví dụ hai source khác nhau cùng được ánh xạ thành `output/report.pdf`. Nếu không kiểm tra, nguồn đến sau có thể ghi đè kết quả của nguồn đến trước.

### 3.2. Phân biệt kiểm tra trước và bảo đảm thực sự

- `Files.exists`, `Files.isReadable`, `Files.isWritable` chỉ là **snapshot**, có thể lỗi thời ngay sau khi trả kết quả.
- `Files.createDirectories(parent)` có thể tạo thư mục cha thiếu, nhưng không đảm bảo quyền, quota hoặc tình trạng filesystem sẽ giữ nguyên.
- Với trường hợp **không được ghi đè**, hạn chế kiểm tra `if (!Files.exists(target))` rồi mở với chế độ ghi đè; có cửa sổ race. Dùng thao tác/file option thể hiện ý định không ghi đè (ví dụ `CREATE_NEW` khi tạo file mới), và xử lý `FileAlreadyExistsException`.
- Khi di chuyển, chọn các options theo hợp đồng `Files.move`; `REPLACE_EXISTING` chủ động cho phép thay thế, còn `ATOMIC_MOVE` có semantics riêng tùy provider.

## 4. Phân loại lỗi đúng với từng bước

`java.nio.file.Files` thường ném `IOException` hoặc các lớp con để mô tả lỗi tác vụ I/O. Một số tình huống:

| Loại lỗi | Tình huống thường gặp | Cách xử lý |
| --- | --- | --- |
| `NoSuchFileException` | Nguồn biến mất, đường dẫn không tồn tại | Ghi nhận tệp bị thiếu; có thể báo lỗi dữ liệu đầu vào |
| `FileAlreadyExistsException` | Đích đã tồn tại nhưng tác vụ không cho phép thay thế | Bảo toàn đích; quyết định đổi tên/từ chối |
| `AccessDeniedException` | Thiếu quyền file hoặc thư mục | Báo quyền truy cập, tránh retry mù |
| `DirectoryNotEmptyException` | Xóa thư mục vẫn có nội dung | Không xóa đệ quy ngoài phạm vi sở hữu |
| `AtomicMoveNotSupportedException` | Không hỗ trợ `ATOMIC_MOVE` ở filesystem/provider này | Theo chính sách: fail hoặc fallback có thông báo rõ |
| `FileSystemException` | Lỗi filesystem có thông tin nguồn/đích/lý do | Giữ ngữ cảnh, phân tích nguyên nhân |
| `EOFException` | Có thể gặp ở các thao tác đọc nhị phân có hợp đồng đủ byte | Không chấp nhận tệp/bản ghi cắt ngắn |
| `IOException` chung | Đầy đĩa, mất kết nối, lỗi ghi, lỗi filesystem | Xác định bước đã hoàn tất và đầu ra có thể dở |

**Không phải mọi lỗi đều là `IOException`.** `IllegalArgumentException` có thể xuất hiện khi arguments/options không hợp lệ; `SecurityException` có thể xuất hiện theo môi trường/quyền; lỗi logic cũng cần được xử lý ở tầng phù hợp. Không nên bắt `Exception` rồi in “copy failed” và bỏ qua trạng thái không rõ.

### 4.1. Ghi thông tin đủ để xử lý

Một bản ghi lỗi có giá trị gồm: **tệp nguồn, tệp đích, tên bước, loại ngoại lệ, thông báo, timestamp/request ID, số phần tử đã thành công và trạng thái cleanup**. Không log đường dẫn hoặc nội dung nhạy cảm nếu môi trường không cho phép.

Ví dụ minh họa (không phải chương trình độc lập):

```java
try {
    Files.copy(source, target);
} catch (NoSuchFileException e) {
    System.err.println("Missing input: " + source);
    throw e;
} catch (FileAlreadyExistsException e) {
    System.err.println("Destination conflict: " + target);
    throw e;
} catch (IOException e) {
    System.err.println("Copy failed: " + source + " -> " + target);
    throw e;
}
```

Ở đây `source` và `target` phải là các `Path` hợp lệ. Trật tự `catch` đặt **lớp con trước lớp cha `IOException`**; nếu bắt `IOException` đầu tiên, hai nhánh chuyên biệt phía sau sẽ không thể biên dịch vì đã bị bắt bởi kiểu cha.

## 5. Fail-fast, best-effort và kết quả trả về

### 5.1. Fail-fast

Trong mô hình fail-fast, khi một tệp thất bại, dừng các bước tiếp theo và trả thông tin lỗi:

```java
// Minh họa: sources là List<Path>, destinationDir là Path,
// và các tên nguồn phải được kiểm tra để tránh trùng đích.
for (Path source : sources) {
    Path target = destinationDir.resolve(source.getFileName());
    Files.copy(source, target);
}
```

Mã này **không rollback tự động**: nếu 3 tệp đã copy thành công rồi tệp thứ tư lỗi, 3 tệp đầu vẫn tồn tại. Fail-fast là chính sách **dừng**, không phải chính sách **hoàn tác**.

### 5.2. Best-effort

Nếu mỗi tệp độc lập, có thể bắt `IOException` **ở bên trong vòng lặp**, rồi tiếp tục. Kết quả phải ghi nhận cả thành công và thất bại thay vì chỉ in ra console; ví dụ trả danh sách `FileResult(source, destination, status, error)` cho tầng gọi.

Điều tối thiểu là không gộp một batch 95% thành công thành “thành công toàn bộ”. Hãy báo `total`, `succeeded`, `failed`, và danh sách tệp lỗi. Retry có thể thực hiện với các phần thất bại, nhưng phải bảo đảm tính **idempotency** của từng bước.

### 5.3. Hai trường hợp phù hợp với từng chiến lược

- **Xuất bộ cấu hình gồm metadata + dữ liệu:** chỉ công bố khi toàn bộ thành phần hợp lệ; staging rồi publish thường hợp lý.
- **Chuyển ảnh cá nhân độc lập:** có thể cho phép vài ảnh bị lỗi, tiếp tục các ảnh khác và trả báo cáo chi tiết.

Cả hai vẫn cần xác định khả năng làm dở **một tệp riêng lẻ** và chính sách tệp đích có sẵn.

## 6. Ví dụ Java 17+: thử từng tệp, tiếp tục khi lỗi

Chương trình sau tạo nguồn thử trong thư mục tạm. Nó copy một tệp có thật, thử copy tệp thiếu, rồi copy tệp còn lại. Mỗi lần thử có kết quả riêng; cuối cùng in tổng số thành công/thất bại. Không có file người dùng nào bị thay đổi.

Lưu thành **`BestEffortFilesDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class BestEffortFilesDemo {
    static boolean copyOne(Path source, Path target) {
        try {
            Files.copy(source, target);
            System.out.println("OK: " + source.getFileName());
            return true;
        } catch (IOException failure) {
            System.out.println("FAIL: " + source.getFileName()
                    + " (" + failure.getClass().getSimpleName() + ")");
            return false;
        }
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("best-effort-");
        Path inputs = Files.createDirectory(root.resolve("inputs"));
        Path outputs = Files.createDirectory(root.resolve("outputs"));
        Path first = inputs.resolve("first.txt");
        Path missing = inputs.resolve("missing.txt");
        Path second = inputs.resolve("second.txt");

        try {
            Files.writeString(first, "one", StandardCharsets.UTF_8);
            Files.writeString(second, "two", StandardCharsets.UTF_8);

            int succeeded = 0;
            for (Path source : List.of(first, missing, second)) {
                Path target = outputs.resolve(source.getFileName());
                if (copyOne(source, target)) {
                    succeeded++;
                }
            }

            System.out.println("Succeeded: " + succeeded);
            System.out.println("Failed: " + (3 - succeeded));
        } finally {
            Files.deleteIfExists(outputs.resolve("first.txt"));
            Files.deleteIfExists(outputs.resolve("second.txt"));
            Files.deleteIfExists(first);
            Files.deleteIfExists(second);
            Files.deleteIfExists(outputs);
            Files.deleteIfExists(inputs);
            Files.deleteIfExists(root);
        }
    }
}
```

Lệnh chạy với JDK 17+:

```bash
javac -encoding UTF-8 BestEffortFilesDemo.java
java BestEffortFilesDemo
```

**Stdout trên filesystem mặc định thông thường khi các thao tác thử thành công:**

```text
OK: first.txt
FAIL: missing.txt (NoSuchFileException)
OK: second.txt
Succeeded: 2
Failed: 1
```

**Giải thích:**

1. `first.txt` tồn tại và được copy sang thư mục `outputs`.
2. `missing.txt` **cố ý không được tạo**, vì vậy `Files.copy` báo lỗi. Lớp `NoSuchFileException` là kết quả thông thường khi nguồn không có; các provider khác có thể biểu diễn lỗi khác, do đó code in **tên lớp ngoại lệ thực tế**.
3. Vòng lặp vẫn tiếp tục và copy `second.txt`.
4. Tổng kết phân biệt tệp thành công và tệp thất bại. `copyOne` không ném lại lỗi vì đây là ví dụ chính sách best-effort; trong ứng dụng thực, nên **trả/ghi nhận nguyên nhân chi tiết**, không chỉ boolean.
5. `finally` chỉ cố xóa các file và thư mục nằm trong vùng tạm do ví dụ tạo. Nếu cleanup ném lỗi, `IOException` đó có thể che ngoại lệ trước đó; ứng dụng sản xuất cần cơ chế lưu cả lỗi chính lẫn lỗi dọn dẹp.

**Giới hạn quan trọng:** `Files.copy` thông thường **không thay thế file đích đang tồn tại** nếu không có `REPLACE_EXISTING`. Với tải đồng thời, phải xử lý cả xung đột đích và kết quả copy dở. Bản demo thực hiện trên thư mục đích mới tạo, nên không có dữ liệu cũ.

## 7. Ví dụ Java 17+: staging và hoàn tác best-effort khi publish thất bại

Khi cả nhóm tệp phải cùng thuộc một lần phát hành, phương pháp hữu ích là:

1. Copy từng nguồn sang tên **tạm** trong thư mục đích riêng.
2. Chỉ khi toàn bộ bước chuẩn bị thành công mới đổi tên các file tạm thành tên cuối.
3. Nếu publish có lỗi, cố xóa những file thuộc sở hữu lần phát hành này.
4. Không xóa file có sẵn từ trước của người dùng.

Ví dụ dưới **cố tình gây lỗi sau khi publish tệp đầu tiên** để kiểm tra rollback. Nó hoạt động trong **thư mục đích mới, riêng tư và ban đầu rỗng**; nhờ vậy chương trình sở hữu mọi tên kết quả trong thư mục này.

Lưu thành **`StagedBatchFilesDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

public class StagedBatchFilesDemo {
    static void publish(List<Path> sources, Path outputDir,
            boolean injectFailure) throws IOException {

        List<Path> staged = new ArrayList<>();
        List<Path> published = new ArrayList<>();

        try {
            // Phase 1: prepare every file in the private output directory.
            for (Path source : sources) {
                Path temp = Files.createTempFile(
                        outputDir, ".stage-", ".tmp");
                staged.add(temp);
                Files.copy(source, temp,
                        StandardCopyOption.REPLACE_EXISTING);
            }

            // Phase 2: publish under the known final filenames.
            for (int i = 0; i < staged.size(); i++) {
                Path target = outputDir.resolve(
                        "part-" + (i + 1) + ".txt");
                Files.move(staged.get(i), target);
                published.add(target);

                if (injectFailure && i == 0) {
                    throw new IOException(
                            "Simulated failure after first publish");
                }
            }
        } catch (IOException failure) {
            // Only remove files owned by this run.
            for (int i = published.size() - 1; i >= 0; i--) {
                try {
                    Files.deleteIfExists(published.get(i));
                } catch (IOException cleanup) {
                    failure.addSuppressed(cleanup);
                }
            }
            for (int i = staged.size() - 1; i >= 0; i--) {
                try {
                    Files.deleteIfExists(staged.get(i));
                } catch (IOException cleanup) {
                    failure.addSuppressed(cleanup);
                }
            }
            throw failure;
        }
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("batch-files-");
        Path inputs = Files.createDirectory(root.resolve("inputs"));
        Path outputs = Files.createDirectory(root.resolve("outputs"));
        Path one = inputs.resolve("one.txt");
        Path two = inputs.resolve("two.txt");

        try {
            Files.writeString(one, "alpha", StandardCharsets.UTF_8);
            Files.writeString(two, "beta", StandardCharsets.UTF_8);
            List<Path> sources = List.of(one, two);

            try {
                publish(sources, outputs, true);
            } catch (IOException failure) {
                System.out.println("First attempt: "
                        + failure.getMessage());
            }

            try (Stream<Path> files = Files.list(outputs)) {
                System.out.println("After rollback: " + files.count());
            }

            publish(sources, outputs, false);
            System.out.println("Published: "
                    + Files.readString(outputs.resolve("part-1.txt"))
                    + ","
                    + Files.readString(outputs.resolve("part-2.txt")));
        } finally {
            Files.deleteIfExists(outputs.resolve("part-2.txt"));
            Files.deleteIfExists(outputs.resolve("part-1.txt"));
            Files.deleteIfExists(one);
            Files.deleteIfExists(two);
            Files.deleteIfExists(outputs);
            Files.deleteIfExists(inputs);
            Files.deleteIfExists(root);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 StagedBatchFilesDemo.java
java StagedBatchFilesDemo
```

**Stdout dự kiến trong môi trường thử nghiệm bình thường:**

```text
First attempt: Simulated failure after first publish
After rollback: 0
Published: alpha,beta
```

**Tại sao kết quả như vậy?**

- Hai tệp gốc được copy vào hai file tạm cùng thư mục `outputs`. Tệp nguồn luôn được giữ nguyên.
- Trong lần đầu, sau khi di chuyển file tạm thứ nhất thành `part-1.txt`, chương trình ném lỗi giả lập. Khối `catch` xóa file đã publish và các file tạm chưa chuyển, nên thư mục `outputs` không còn file.
- Lần thứ hai không tạo lỗi giả lập và công bố cả hai file. `Files.readString` dùng để quan sát **các tệp thử rất nhỏ**; trong batch file lớn nên tránh đọc toàn bộ tệp chỉ để xác minh.
- Các lệnh dọn dẹp trong `catch` dùng `addSuppressed`: nếu xóa một file cũng thất bại, **lỗi gốc được giữ lại** và thông tin cleanup được đính kèm qua `Throwable.getSuppressed()`. Chương trình thực tế nên log cả những lỗi bị suppress.

**Giới hạn của mẫu này không được bỏ qua:**

1. Đây chỉ là **rollback bù trừ best-effort**, không phải một transaction nguyên tử của filesystem. Trong thời gian giữa các lần `Files.move`, người đọc khác có thể nhìn thấy một phần kết quả.
2. Khi `Files.move` thất bại theo cách không nguyên tử, trạng thái file nguồn/đích có thể không xác định hoàn toàn. Danh sách `published` chỉ ghi lại các bước **đã trả về thành công**; nếu move đang thất bại để lại một phần kết quả, chỉ dọn danh sách này có thể chưa đủ. Hệ thống sản xuất cần quét/xác minh trạng thái theo **manifest** trong vùng mà tác vụ sở hữu.
3. Mẫu **chỉ an toàn khi output directory là vùng riêng, không có file đích trước đó và không có writer ngoài thay đổi cùng các tên tệp**. Với file có sẵn, không được ghi đè rồi xóa khi rollback; cần giữ bản trước đó bằng versioning/backup và quy trình restore được thiết kế riêng.
4. `Files.createTempFile` tạo file tạm trước, nên `Files.copy(..., REPLACE_EXISTING)` chỉ thay nội dung của **file tạm do tác vụ này vừa tạo**. Không áp dụng `REPLACE_EXISTING` bừa bãi lên tên đích của người dùng.
5. `Files.move` ở đây **không được yêu cầu `ATOMIC_MOVE`**. Dù file tạm và đích cùng thư mục, không được khẳng định mọi provider làm move nguyên tử. Nếu muốn một lần rename nguyên tử, yêu cầu `ATOMIC_MOVE` với xử lý `AtomicMoveNotSupportedException` phù hợp.
6. Nếu JVM bị kill hoặc máy mất điện giữa chừng, khối `catch`/`finally` **không được bảo đảm chạy**. Cần cơ chế recovery chạy lại dựa trên manifest, trạng thái thực tế và ownership.
7. Không có checksum hay validation nội dung thực; nếu nghiệp vụ đòi tính toàn vẹn, phải kiểm tra sau khi ghi stage và trước publish.
8. Khi cleanup thất bại, tài nguyên còn lại cần được ghi nhận để có thể xử lý sau. Không được báo “rollback thành công tuyệt đối” chỉ vì đã chạy vòng xóa.

**Ý nghĩa thực hành:** staging giúp tránh công bố dữ liệu chưa chuẩn bị xong, còn danh sách trạng thái giúp biết đã làm gì và cố hoàn tác những thao tác thuộc sở hữu mình. Nhưng **việc công bố nhiều tên file vẫn có cửa sổ quan sát trạng thái không đầy đủ**.

## 8. `Files.copy`, `Files.move` và `Files.delete`: khác nhau ở trạng thái sau lỗi

### 8.1. Copy

`Files.copy(source, target, options...)` sao chép nội dung và, tùy options, một số thuộc tính. Thao tác có thể thất bại sau khi tệp đích đã được tạo hoặc đang chứa một phần dữ liệu. Với `REPLACE_EXISTING`, tệp cũ có thể đã bị thay thế; lựa chọn này cần sự cho phép rõ.

Nếu đầu ra phải nguyên vẹn, tránh copy thẳng vào tên kết quả cuối khi tác vụ chưa được kiểm tra. Dùng tên tạm trong vùng sở hữu và công bố khi đủ điều kiện.

### 8.2. Move

`Files.move` có thể dùng:

```java
// Đoạn minh họa; staged và finalPath là các Path phù hợp.
Files.move(staged, finalPath);
```

Khi muốn yêu cầu một lần move nguyên tử:

```java
Files.move(staged, finalPath, StandardCopyOption.ATOMIC_MOVE);
```

**Cần biết:**

- `ATOMIC_MOVE` có thể không được filesystem/provider hỗ trợ; khi đó có thể ném `AtomicMoveNotSupportedException`.
- Khi `ATOMIC_MOVE` được dùng, semantics về việc đích đã tồn tại phụ thuộc hợp đồng provider; không dùng nó như một cách phổ quát để bảo đảm “không ghi đè” trong mọi môi trường.
- **Nguyên tử của một move không phải nguyên tử của một batch gồm 20 move.** Những tệp đã chuyển vẫn có thể lộ ra trước khi toàn bộ batch hoàn thành.
- Khi move không nguyên tử thất bại, nguồn và đích có thể ở trạng thái chưa rõ; phải kiểm tra trước khi retry hoặc cleanup.

Một mô hình publish mạnh hơn có thể là đưa **toàn bộ batch vào một thư mục phiên bản mới**, xác minh rồi chuyển một tên directory/pointer manifest như một thao tác công bố cuối. Ngay cả thiết kế đó vẫn cần xét giới hạn của filesystem, việc có thể thay thế tên, và khôi phục sau crash.

### 8.3. Delete

`Files.delete(path)` yêu cầu xóa và báo lỗi nếu không thể xóa; `Files.deleteIfExists(path)` không xem file thiếu là lỗi. Cả hai có thể thất bại vì quyền, lock, thư mục không rỗng hoặc lỗi filesystem.

**Chỉ dùng `deleteIfExists` khi đúng chính sách:** với rollback, file không còn tồn tại có thể là bình thường; với yêu cầu “phải xóa chính xác file X”, đôi khi cần ghi nhận file thiếu như một trạng thái khác. Tuyệt đối không xóa đệ quy một thư mục do người dùng cung cấp nếu chưa chứng minh phạm vi được phép.

## 9. Cách giữ ngoại lệ chính và lỗi cleanup

### 9.1. `try-with-resources`

Đối với các tài nguyên mở bằng `Files.newInputStream`, `Files.newOutputStream`, `Files.newBufferedReader` hoặc `Files.newBufferedWriter`, ưu tiên `try-with-resources`:

```java
// Đoạn minh họa: inputPath và outputPath phải là Path hợp lệ.
try (InputStream in = Files.newInputStream(inputPath);
     OutputStream out = Files.newOutputStream(outputPath)) {
    in.transferTo(out);
}
```

Nếu thân `try` ném ngoại lệ và quá trình đóng stream cũng lỗi, Java giữ ngoại lệ chính và có thể gắn ngoại lệ đóng tài nguyên vào danh sách **suppressed exceptions**. Đây là lợi ích quan trọng khi chẩn đoán tác vụ nhiều bước.

Khai báo stream đầu ra phải rất cẩn thận: `Files.newOutputStream(outputPath)` với options mặc định sẽ tạo file nếu thiếu và có thể **truncate** file đã có. Khi cần tránh hủy nội dung cũ, chọn chính sách mở tương ứng (ví dụ tạo tên tạm hoặc `CREATE_NEW`).

### 9.2. `finally` không tự bảo đảm rollback

`finally` chạy khi thực thi rời khối theo cơ chế thông thường, nhưng không được bảo đảm khi tiến trình bị kill, mất điện hoặc hệ thống sập. Ngoài ra, nếu `finally` ném ngoại lệ mới, nó có thể **che lỗi gốc**.

Nếu buộc cleanup thủ công, hãy giữ ngoại lệ gốc và gắn lỗi cleanup bằng `addSuppressed`, đồng thời ghi log/manifest cho công việc dọn còn tồn đọng. Không chọn việc im lặng bỏ qua ngoại lệ cleanup trong các hệ thống cần biết trạng thái file.

### 9.3. Không bắt lỗi quá rộng

Một `catch (Exception ignored)` quanh toàn batch khiến không biết bước nào lỗi. Ngược lại, catch quá hẹp ở mỗi byte thao tác cũng khó bảo trì. Nên phân tầng:

- Mỗi bước I/O trả lỗi có ngữ cảnh `source → target` và tên bước.
- Bộ điều phối batch chọn dừng hay tiếp tục.
- Tầng ngoài cùng tổng hợp/report trạng thái và cleanup.
- Các lỗi lập trình và vi phạm bất biến không bị che dưới nhãn “file missing”.

## 10. Retry và tính idempotent

Thử lại thao tác là cần thiết với lỗi tạm thời, nhưng **retry mù quáng** có thể gây tác hại:

- Copy lại với `REPLACE_EXISTING` có thể ghi đè file đã được tiến trình khác cập nhật.
- Append log lại có thể tạo bản ghi trùng.
- Di chuyển nguồn đã được move thành công nhưng client tưởng thất bại có thể gặp `NoSuchFileException` ở lần retry.
- Xóa một tên tệp bị tái sử dụng bởi writer khác có thể xóa nhầm dữ liệu mới.

**Idempotent** nghĩa là lặp cùng yêu cầu không làm kết quả nghiệp vụ thay đổi sau lần thành công đầu tiên, dưới những giả định rõ. Một thiết kế có thể dùng mã batch duy nhất, target versioned, manifest và checksum để phát hiện thao tác đã hoàn tất.

Quy trình retry cần:

1. Phân loại nguyên nhân (thiếu quyền, đầy đĩa, nguồn tạm thời không khả dụng, xung đột đích).
2. Kiểm tra trạng thái thực tế của source, stage và destination.
3. Chỉ thử lại khi đủ điều kiện tránh đè dữ liệu không thuộc sở hữu.
4. Giới hạn số lượt/thời gian retry, ghi lại lần thử và nguyên nhân thất bại.
5. Không retry vô hạn trên lỗi xác định như sai quyền hoặc input không hợp lệ.

Với batch lớn, manifest nên ghi **ID, source, target, checksum nếu cần, trạng thái từng bước**. Đây là dữ liệu hỗ trợ recovery; không nhất thiết phải có database cho mọi bài toán nhỏ.

## 11. Sao lưu, ghi đè và khôi phục bản cũ

Nếu target đã tồn tại và phải giữ nó khi lỗi, mô hình “xóa mọi output mới” **không đủ**, vì một bước ghi đè có thể đã làm mất bản cũ.

Các hướng thiết kế:

- **Không ghi đè:** tạo tên độc nhất bằng `CREATE_NEW` hoặc thư mục versioned; công bố phiên bản khi hoàn chỉnh.
- **Staging riêng + backup:** tạo bản sao/version của đích trước khi thay thế và có quy trình rollback từ backup, phải kiểm tra backup thật sự khả dụng.
- **Thay đổi pointer/manifest:** file nội dung được ghi vào phiên bản mới, sau đó cập nhật một tên/file chỉ dẫn nhỏ để người đọc chọn phiên bản đã hoàn tất.
- **Transaction ở tầng ứng dụng:** nếu cần đồng bộ nhiều đối tượng, cân nhắc kho dữ liệu/metadata giao dịch và quy trình recovery được thiết kế riêng.

**Không hứa hẹn rằng nhiều file có thể được thay thế nguyên tử chỉ bằng `Files.move` nhiều lần.** Atomicity của từng file khác với atomicity của cả tập. Đồng thời, khôi phục “bản cũ” cần kiểm soát tệp nguồn, file backup và quyền sở hữu; lệnh copy ngược không tự khắc phục mọi tình huống mất điện hoặc thay đổi đồng thời.

### 11.1. Tạo file tạm đúng chỗ

`Files.createTempFile(targetDir, prefix, suffix)` giúp đặt file stage cùng vùng đích, có thể thuận lợi cho move trong cùng filesystem. Tuy nhiên:

- Tên tạm phải duy nhất; lưu danh sách để cleanup.
- Có thể tồn tại quota/permission, và tạo tệp tạm cũng có thể thất bại.
- Nếu cần secure permissions, xem cách đặt thuộc tính file khi tạo.
- Không dựng tệp tạm bằng một đường dẫn cố định dễ bị người khác chiếm dụng, đặc biệt ở thư mục công cộng.

## 12. An toàn đường dẫn và giới hạn tài nguyên

Batch thao tác hàng loạt thường nhận danh sách đường dẫn từ file cấu hình hoặc API. Cần bảo vệ cả **tệp đích** và **tài nguyên hệ thống**:

- Kiểm tra đường dẫn nguồn/đích, xử lý `..`, tên tuyệt đối, symlink và các quy tắc giới hạn thư mục. `Path.normalize()` chỉ xử lý cú pháp; không ngăn tự động TOCTOU.
- Đừng dùng `source.getFileName()` rồi cho rằng mọi trùng tên đã biến mất: hai tệp ở thư mục khác nhau có thể cùng tên.
- Giới hạn số tệp, tổng byte, số stream mở đồng thời, thời gian và kích thước tệp staging.
- Với file nhiều GB, dùng API copy/streaming; không dùng `Files.readAllBytes`/`readString` cho toàn bộ batch.
- Dùng một tập tên đầu ra xác định; không tự xóa bất kỳ mục nào nằm ngoài phạm vi batch.
- Thao tác nhiều tệp trên filesystem mạng/khác volume có semantics khác với một ổ đĩa cục bộ; kiểm thử ở môi trường triển khai thực.

## 13. Những lỗi thiết kế phổ biến

1. **Cho rằng vòng lặp `Files.copy` là transaction:** thực tế một lỗi có thể để lại tệp đã copy từ trước.
2. **Bắt lỗi ở ngoài cùng nhưng không biết file nào thất bại:** mất khả năng chẩn đoán và retry chọn lọc.
3. **Bắt lỗi từng tệp rồi báo cả batch thành công:** che số lượng và danh sách thất bại.
4. **Dọn mọi file trong thư mục đích khi rollback:** có thể xóa tài nguyên cũ của người khác.
5. **Không theo dõi các file stage đã tạo:** có thể để lại file tạm lâu dài.
6. **Dùng `REPLACE_EXISTING` tùy tiện:** có thể mất dữ liệu cũ không khôi phục được.
7. **Dùng `Files.exists` rồi tự tin rằng đích không thể đổi:** time-of-check-to-time-of-use vẫn tồn tại.
8. **Không xử lý cleanup thất bại:** thông tin file còn sót bị thất lạc.
9. **Tin mọi `move` đều nguyên tử:** `ATOMIC_MOVE` cần hỗ trợ; move từng tệp không làm cả batch nguyên tử.
10. **Tin catch/finally luôn chạy khi crash:** tiến trình có thể chết bất ngờ; cần recovery nếu yêu cầu.
11. **Giữ hàng nghìn stream mở cùng lúc:** dễ cạn file descriptor; mở/đóng theo phạm vi mỗi tệp.
12. **Chỉ đo số file, không đo byte/checksum:** nội dung có thể bị sai hoặc dở mà vẫn có tên file.
13. **Retry ngay lập tức không kiểm tra trạng thái:** có thể làm trùng bản ghi hoặc ghi đè bản mới.
14. **Bỏ qua symlink:** path “nằm trong thư mục” theo chuỗi có thể dẫn tới file khác qua link.
15. **Log tên file mà quên bước bị lỗi:** không phân biệt lỗi stage, verify, publish hay cleanup.
16. **Không có manifest khi cần hồi phục sau crash:** không biết tệp nào đã publish và tệp nào cần xử lý tiếp.

## 14. Bài tập thực hành

1. Với ba tệp `a.txt`, `b.txt`, `c.txt`, giả lập lỗi sao chép `b.txt`. Phân biệt trạng thái còn lại khi dùng **fail-fast** và **best-effort**.
2. Sửa `BestEffortFilesDemo` để trả danh sách kết quả gồm source, target, thành công/thất bại và nguyên nhân, thay vì boolean.
3. Thêm kiểm tra tên đích trùng nhau trước khi chạy batch. Hai nguồn `x/a.txt` và `y/a.txt` cần xử lý thế nào?
4. Thử tạo sẵn `outputs/first.txt` trước khi copy. `Files.copy` không có `REPLACE_EXISTING` báo ngoại lệ gì?
5. Thay giả lập lỗi trong `StagedBatchFilesDemo` bằng thất bại khi tạo stage. Danh sách cleanup có đủ để dọn các file do tác vụ sở hữu không?
6. Làm cho `Files.deleteIfExists` của rollback thất bại trong một môi trường thử. Kiểm tra `getSuppressed()` của ngoại lệ ban đầu.
7. Mô tả trường hợp `Files.move` thất bại sau khi tạo một phần đích. Vì sao chỉ dựa vào danh sách các bước “đã return thành công” có thể chưa đủ?
8. Thiết kế một manifest cho batch 10 tệp với các trạng thái `STAGED`, `VERIFIED`, `PUBLISHED`, `FAILED`; xử lý resume sau khi tiến trình bị kill.
9. Mô tả vì sao backup trước ghi đè chưa đủ nếu backup cũng có thể thất bại hoặc bị ghi đè.
10. So sánh “10 lần move có `ATOMIC_MOVE`” và “một thao tác công bố cả thư mục/version đã xây xong”. Cả hai có những điều kiện gì trên filesystem?
11. Với 1.000 tệp nhiều GB, hãy xây chính sách giới hạn số stream đang mở, tổng byte, dung lượng tạm và thời gian.
12. Giải thích tại sao `Path.normalize()` không thay thế kiểm tra symbolic link và permission khi cho người dùng tải lên file vào thư mục được kiểm soát.

## 15. Checklist trước khi triển khai

- [ ] Đã xác định fail-fast, best-effort hay staging/publish?
- [ ] Đã kiểm tra mapping source → target, trùng tên và chính sách ghi đè?
- [ ] Đã xác định rõ tài nguyên nào thuộc sở hữu batch, tài nguyên nào tuyệt đối không được xóa?
- [ ] Đã giới hạn tổng số file, tổng byte, mức đồng thời và thời gian?
- [ ] Đã tách lỗi chuẩn bị, kiểm tra, publish và cleanup?
- [ ] Đã giữ nguyên ngoại lệ chính cùng suppressed exceptions từ cleanup?
- [ ] Đã định nghĩa trạng thái sau lỗi, sau retry và sau crash?
- [ ] Đã kiểm tra cách công bố kết quả khi chỉ một phần batch thành công?
- [ ] Đã xác định semantics của `Files.copy`/`move`/`delete` trên filesystem thật?
- [ ] Đã xử lý quyền, symlink, thay đổi đồng thời và trường hợp hết đĩa?
- [ ] Đã xác định cần checksum/version/manifest hay không?
- [ ] Đã kiểm thử fail injection ở từng bước quan trọng?

## 16. Tổng kết

Xử lý nhiều tệp là **bài toán về trạng thái và quyền sở hữu**, không chỉ vòng lặp `Files.copy`. Một thiết kế đúng cần quyết định rõ **dừng hay tiếp tục**, tách **plan → stage → verify → publish → cleanup**, ghi nhận thành công/thất bại theo từng bước, và tuyệt đối tránh dọn những tài nguyên không thuộc tác vụ.

`try-with-resources` và `IOException` giúp quản lý lỗi I/O; `addSuppressed` giúp giữ thông tin cleanup; `ATOMIC_MOVE` (khi hỗ trợ) có thể giúp cho **một bước chuyển**, nhưng không tự tạo transaction cho toàn bộ batch. Với tính nhất quán cao, cần staged output, manifest/versioning, kiểm tra toàn vẹn, chính sách retry và recovery phù hợp.

**Nguyên tắc thực hành:** Sau mỗi bước, phải trả lời được **“đã thay đổi những file nào, file nào vẫn thuộc quyền của lần chạy này, và nếu bước tiếp theo thất bại thì sẽ làm gì?”**. Khi trả lời được câu hỏi đó bằng dữ liệu cụ thể, hệ thống mới có thể xử lý lỗi nhiều tệp một cách kiểm chứng và an toàn.