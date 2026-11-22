# `Files.move()`, đổi tên tệp và lựa chọn `ATOMIC_MOVE` trong Java

Đổi tên (`rename`) và di chuyển (`move`) là hai thao tác thường gặp trong Java I/O: đổi `draft.txt` thành `report.txt`, chuyển file từ thư mục tạm sang thư mục công bố, hoặc thay tên của một thư mục. API hiện đại là **`java.nio.file.Files.move(Path source, Path target, CopyOption... options)`**. Trong Java NIO.2, đổi tên thường chính là một trường hợp của `move`: đường dẫn nguồn và đường dẫn đích khác tên nhưng có thể cùng thư mục.

Điểm dễ nhầm nhất là **`Files.move()` không mặc định bảo đảm tính nguyên tử**. Khi ứng dụng cần thao tác đổi tên/di chuyển diễn ra như một bước thống nhất mà các tiến trình khác không quan sát trạng thái trung gian, ta có thể yêu cầu **`StandardCopyOption.ATOMIC_MOVE`**. Tuy nhiên, khả năng đáp ứng tùy hệ thống tệp/provider, và lựa chọn này có những quy tắc đặc biệt khi đích đã tồn tại.

Bài học giải thích cú pháp, cách đổi tên và di chuyển, các lựa chọn `REPLACE_EXISTING` và `ATOMIC_MOVE`, phạm vi bảo đảm, lỗi thường gặp, giới hạn khi đi qua nhiều filesystem và cách xây dựng quy trình công bố tệp an toàn.

## 1. Đổi tên là trường hợp của `move`

Một file có thể được đổi tên trong cùng thư mục bằng cách tạo `Path target` mới:

```java
// Đoạn minh họa: source đã được khai báo là java.nio.file.Path.
Path target = source.resolveSibling("renamed.txt");
Files.move(source, target);
```

`resolveSibling("renamed.txt")` đặt tên mới **cạnh** nguồn, tức dưới cùng đường dẫn cha (nếu có). `Files.move(source, target)` yêu cầu chuyển mục nguồn sang đường dẫn đích. Nếu thành công, tên cũ thường không còn dùng để tìm mục đó, còn tên mới dùng để truy cập.

Di chuyển sang một thư mục khác:

```java
// Đoạn minh họa: source và targetDirectory là Path có sẵn.
Path target = targetDirectory.resolve(source.getFileName());
Files.move(source, target);
```

Với cùng một file, API không hề có hai cơ chế độc lập “rename” và “move”: khác nhau chủ yếu là cách xác định **đường dẫn đích**.

**Lưu ý:** `Path` chỉ biểu diễn đường dẫn. `Files.move` mới là thao tác I/O thật; nó có thể ném `IOException` vì thiếu file, đích đã tồn tại, quyền truy cập, filesystem, file đang được dùng hoặc các điều kiện khác. `move()` không tự tạo toàn bộ các thư mục cha của đích.

### Ví dụ 1 — đổi tên một file thật, độc lập với thư mục dự án

```java
// MoveRenameDemo.java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class MoveRenameDemo {
    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("move-rename-");
        Path source = directory.resolve("draft.txt");
        Path target = source.resolveSibling("report.txt");

        try {
            Files.writeString(source, "Java I/O", StandardCharsets.UTF_8);

            Path moved = Files.move(source, target);

            System.out.println("resultName=" + moved.getFileName());
            System.out.println("oldExists=" + Files.exists(source));
            System.out.println("newExists=" + Files.exists(target));
            System.out.println("content="
                    + Files.readString(target, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(target);
            Files.deleteIfExists(directory);
        }
    }
}
```

Chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 MoveRenameDemo.java
java MoveRenameDemo
```

Kết quả khi hệ thống tệp thực hiện các thao tác thành công:

```text
resultName=report.txt
oldExists=false
newExists=true
content=Java I/O
```

`Files.move()` trả về `Path` đại diện đường dẫn đích; ví dụ không dùng tên thư mục tạm để tạo stdout nên kết quả dễ kiểm tra. Khối `finally` dọn các mục ví dụ tạo ra; nếu có lỗi I/O ngay trong phần dọn, lỗi ấy cũng cần được xử lý theo chính sách ứng dụng thực tế.

## 2. `Files.move(...)` nhận các đối số nào?

Chữ ký:

```java
public static Path move(
        Path source,
        Path target,
        CopyOption... options) throws IOException;
```

Đây là **chữ ký API rút gọn để giải thích**, không phải phương thức cần tự cài đặt lại.

- `source`: đường dẫn mục muốn di chuyển.
- `target`: đường dẫn đích, gồm cả tên file/thư mục mới.
- `options`: các tùy chọn của thao tác, trong đó hay dùng `StandardCopyOption.REPLACE_EXISTING` và `StandardCopyOption.ATOMIC_MOVE`.
- Kết quả: `Path` đại diện đích nếu thành công.
- Có thể phát sinh `IOException` và các subtype tùy nguyên nhân; một số điều kiện như quyền Java security hoặc provider không tương thích có lỗi khác theo API.

Ba kiểu gọi thường gặp:

```java
Files.move(source, target);

Files.move(source, target,
        StandardCopyOption.REPLACE_EXISTING);

Files.move(source, target,
        StandardCopyOption.ATOMIC_MOVE);
```

**Điểm cần nhớ:** `REPLACE_EXISTING` và `ATOMIC_MOVE` không phải hai mức “an toàn tăng dần” của cùng một tính chất. Một lựa chọn nói về **cách xử lý mục đích đã tồn tại** trong thao tác thông thường; lựa chọn còn lại yêu cầu **tính nguyên tử của bước move**. Và khi có `ATOMIC_MOVE`, những option khác bị bỏ qua theo hợp đồng `Files.move()`.

## 3. Không truyền option: điều gì xảy ra nếu đích đã tồn tại?

Mặc định, `Files.move(source, target)` **không yêu cầu thay thế đích đã tồn tại**. Nếu target đã có một mục khác, thao tác thường thất bại với `FileAlreadyExistsException`. Có những ngoại lệ/chi tiết implementation, nhưng trong mã ứng dụng hãy coi xung đột đích là một lỗi phải được xử lý, không dựa vào việc ghi đè ngầm.

Ví dụ: `draft.txt` và `final.txt` đều tồn tại. Lệnh:

```java
Files.move(Path.of("draft.txt"), Path.of("final.txt"));
```

không nên được dùng với kỳ vọng chắc chắn ghi đè `final.txt`. Nếu yêu cầu nghiệp vụ là **không thay thế** tệp đích, hãy giữ thao tác không có `REPLACE_EXISTING`, bắt lỗi xung đột và xem thêm các lưu ý về tính nguyên tử nếu cần đảm bảo mạnh trước cạnh tranh đồng thời.

Khi source và target trỏ tới **cùng một file**, `Files.move` có thể trả về mà không làm gì theo hợp đồng. Đừng coi mọi lần gọi `move` đều đồng nghĩa với thay đổi tên thực tế.

## 4. `REPLACE_EXISTING`: cho phép thay thế đích trong move thông thường

`StandardCopyOption.REPLACE_EXISTING` yêu cầu **thay thế mục ở đường dẫn đích nếu nó đã tồn tại**, theo các giới hạn của provider và loại mục:

```java
Files.move(source, target,
        StandardCopyOption.REPLACE_EXISTING);
```

Giả sử `source` và `target` đều là regular file. Sau khi thành công, target thường chứa mục/file được chuyển từ source, chứ không còn nội dung cũ.

Nhưng **không được** hiểu đây là cam kết “mọi loại đích đều thay được”: ví dụ đích là thư mục không rỗng có thể không thay thế được. Các hệ thống tệp có quy tắc khác nhau cho file đang mở, ACL, symbolic link, mục đặc biệt và đường dẫn ở nhiều provider.

### Ví dụ 2 — xung đột và thay thế có chủ đích

```java
// MoveReplaceDemo.java
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class MoveReplaceDemo {
    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("move-replace-");
        Path source = directory.resolve("source.txt");
        Path target = directory.resolve("target.txt");

        try {
            Files.writeString(source, "NEW", StandardCharsets.UTF_8);
            Files.writeString(target, "OLD", StandardCharsets.UTF_8);

            try {
                Files.move(source, target);
                System.out.println("unexpected: move without replace");
            } catch (FileAlreadyExistsException expected) {
                System.out.println("collision=true");
            }

            Files.move(source, target,
                    StandardCopyOption.REPLACE_EXISTING);

            System.out.println("targetText="
                    + Files.readString(target, StandardCharsets.UTF_8));
            System.out.println("sourceExists=" + Files.exists(source));
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(target);
            Files.deleteIfExists(directory);
        }
    }
}
```

```bash
javac MoveReplaceDemo.java
java MoveReplaceDemo
```

Kết quả điển hình trên filesystem cục bộ thông dụng, khi file tồn tại và quyền cho phép:

```text
collision=true
targetText=NEW
sourceExists=false
```

Ở đây việc thay thế là **chủ đích**; không có ý nghĩa nếu yêu cầu nghiệp vụ là “không bao giờ làm mất nội dung đích cũ”. Cũng không được kết luận rằng chỉ cần thêm `REPLACE_EXISTING` là thao tác trở nên nguyên tử.

### Tệp đích là symbolic link

Khi target là symbolic link, quy tắc thay thế của `Files.move(..., REPLACE_EXISTING)` liên quan đến **mục liên kết** chứ không phải tự động xóa target mà nó trỏ tới. Với source là symbolic link, `Files.move()` di chuyển chính **link** thay vì chuyển nội dung đích của link theo kiểu copy dereference.

Điều này quan trọng khi xử lý link hỏng hoặc link trỏ ra ngoài thư mục mong muốn. Nếu source/target liên quan symbolic link hoặc junction, hãy xác định hợp đồng thao tác dựa trên provider và bài toán; không giả định logic đối với file thông thường áp dụng y hệt cho mọi loại mục.

## 5. `ATOMIC_MOVE`: yêu cầu một bước di chuyển nguyên tử

Một thao tác di chuyển được thực hiện **nguyên tử** khi filesystem/provider có thể làm nó thành một thao tác đối với namespace của hệ thống tệp, thay vì ứng dụng/tiến trình khác quan sát trạng thái trung gian của một chuỗi thao tác như copy từng khối dữ liệu rồi xóa nguồn.

Trong Java:

```java
Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
```

`ATOMIC_MOVE` là **yêu cầu** đối với provider, không phải bảo đảm rằng bất kỳ hệ thống tệp nào cũng làm được. Khi không hỗ trợ atomic move giữa hai đường dẫn đã cho, Java có thể ném `AtomicMoveNotSupportedException`. Đây là tín hiệu để ứng dụng đưa ra quyết định nghiệp vụ: **dừng** nếu atomicity bắt buộc, hoặc dùng phương án không nguyên tử nếu được cho phép.

### Những gì atomic move thường hướng tới

- Thay đổi tên/đường dẫn của mục như **một bước** ở mức namespace của filesystem.
- Tránh một trạng thái nửa vời mà chương trình khác thấy một target mới đang được **copy dở** trong chính thao tác di chuyển nguyên tử.
- Làm nền tảng cho mô hình “chuẩn bị file riêng, rồi công bố tên cuối cùng” trên provider hỗ trợ.

### Những gì atomic move **không** tự bảo đảm

- **Không phải giao dịch nhiều file**: hai lệnh move riêng không được ghép thành một transaction.
- **Không chứng minh byte đã bền vững sau mất điện**: tính nguyên tử khi đổi tên không đồng nghĩa với `fsync`/độ bền lưu trữ.
- **Không bảo đảm không ai sửa nội dung file** trước, trong hoặc sau thao tác. Nó không tự đặt lock cho toàn bộ vòng đời đọc/ghi.
- **Không đảm bảo thành công khi source/target ở khác filesystem**, volume, mount hoặc provider.
- **Không bảo đảm fallback nguyên tử** nếu `ATOMIC_MOVE` bị từ chối.
- **Không bảo đảm xử lý target đã tồn tại giống mọi nền tảng**.

Nếu cần cả atomic visibility, quyền truy cập, tính bền vững khi crash và cập nhật nhiều file, phải thiết kế thêm cơ chế khác ngoài một `Files.move` duy nhất.

### Ví dụ 3 — yêu cầu `ATOMIC_MOVE` và xử lý trường hợp không hỗ trợ

```java
// AtomicMoveDemo.java
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class AtomicMoveDemo {
    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("atomic-demo-");
        Path source = directory.resolve("temporary.txt");
        Path target = directory.resolve("published.txt");

        try {
            Files.writeString(source, "COMPLETE", StandardCharsets.UTF_8);

            try {
                Files.move(source, target,
                        StandardCopyOption.ATOMIC_MOVE);
                System.out.println("atomicMove=performed");
                System.out.println("published="
                        + Files.readString(target, StandardCharsets.UTF_8));
            } catch (AtomicMoveNotSupportedException ex) {
                System.out.println("atomicMove=unsupported");
            }
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(target);
            Files.deleteIfExists(directory);
        }
    }
}
```

```bash
javac AtomicMoveDemo.java
java AtomicMoveDemo
```

Nếu provider hỗ trợ move nguyên tử trong thư mục tạm:

```text
atomicMove=performed
published=COMPLETE
```

Nếu provider báo đúng loại lỗi vì không hỗ trợ:

```text
atomicMove=unsupported
```

**Không có một stdout cố định trên mọi filesystem.** Những lỗi `IOException` khác (chẳng hạn không đủ quyền hoặc lỗi ổ đĩa) vẫn được truyền ra theo `throws Exception` và không bị nhận nhầm là “không hỗ trợ atomic”. Đây là ứng xử tốt hơn việc bắt mọi `IOException` rồi âm thầm thực hiện fallback.

Dù hai đường dẫn nằm trong **cùng thư mục**, atomicity vẫn cần được provider hỗ trợ; cùng thư mục làm khả năng hỗ trợ tốt hơn trong thực tế nhưng không thay thế kiểm tra lỗi.

## 6. Bẫy quan trọng: `ATOMIC_MOVE` khiến các option khác bị bỏ qua

Ví dụ dễ gây hiểu nhầm:

```java
Files.move(source, target,
        StandardCopyOption.ATOMIC_MOVE,
        StandardCopyOption.REPLACE_EXISTING);
```

Bạn có thể tưởng rằng lệnh trên cam kết đồng thời hai điều:

1. Thay tên nguyên tử.
2. Luôn thay thế target hiện có.

**Không đúng để suy ra như vậy.** Theo hợp đồng của `Files.move()`, **khi có `ATOMIC_MOVE`, các option khác bị bỏ qua**. Việc một atomic move có thay thế target hiện có hay không là **implementation-specific**, và không thể bảo đảm bằng cách chỉ kèm `REPLACE_EXISTING`.

Điều này cũng có nghĩa không thể viết một tiện ích “ghi đè atomically trên mọi hệ thống” chỉ bằng cách truyền cả hai hằng số mà không kiểm tra provider, loại mục và yêu cầu của ứng dụng.

| Lời gọi | Yêu cầu chính | Target đã tồn tại |
| --- | --- | --- |
| `Files.move(src, dst)` | Move thông thường, không yêu cầu atomicity | Thường thất bại, không tự cho phép overwrite |
| `Files.move(src, dst, REPLACE_EXISTING)` | Cho phép thay target theo quy tắc move thông thường | Có thể thay thế mục đích hợp lệ, nhưng không cam kết atomic |
| `Files.move(src, dst, ATOMIC_MOVE)` | Yêu cầu move nguyên tử | Hành vi nếu target tồn tại phụ thuộc implementation |
| `Files.move(src, dst, ATOMIC_MOVE, REPLACE_EXISTING)` | Vẫn là yêu cầu atomic move | `REPLACE_EXISTING` bị bỏ qua; hành vi target tồn tại vẫn phụ thuộc implementation |

Bảng phân biệt **quy tắc API** với **hành vi thường gặp**. Muốn biết mức đảm bảo về thay thế target trên một nền tảng cụ thể, cần xét hợp đồng/documentation của filesystem/provider và các trường hợp thực tế. Việc kiểm tra `Files.exists(target)` trước move không đủ loại bỏ race: file có thể xuất hiện hoặc biến mất ngay sau kiểm tra.

## 7. Khi nào nên bắt buộc nguyên tử? Khi nào cho phép fallback?

Ví dụ nghiệp vụ:

- Công bố một file cấu hình hoàn chỉnh bằng tên được consumer theo dõi: atomic rename thường quan trọng để consumer không thấy file đang ghi dở.
- Đổi tên một file cá nhân trong thư mục: có thể chấp nhận move không nguyên tử nếu thao tác và hệ thống tệp cho phép.
- Chuyển file từ ổ đĩa nội bộ sang ổ mạng: có thể phải copy rồi xóa; nếu ứng dụng cần transactional semantics thì phải có thiết kế riêng.
- Thay thế một file quan trọng đang được ứng dụng khác đọc: phải xác định đồng thời chính sách tồn tại đích, phiên bản nội dung, atomicity và cách consumer mở file.

### Chính sách A: không có atomicity thì thất bại

```java
// Minh họa; source và target đã là Path hợp lệ.
try {
    Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
} catch (AtomicMoveNotSupportedException ex) {
    // Không tự copy/delete khi atomicity là yêu cầu bắt buộc.
    throw ex;
}
```

Đây là **đoạn mã minh họa**, cần import tương ứng và nằm trong phương thức cho phép `IOException`. Trong thiết kế này, lỗi “atomic không được hỗ trợ” là lỗi điều kiện tiên quyết, không phải lý do để âm thầm dùng cách yếu hơn.

### Chính sách B: chỉ fallback nếu nghiệp vụ cho phép

```java
// Minh họa; các Path đã có sẵn, không phải chương trình độc lập.
try {
    Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
} catch (AtomicMoveNotSupportedException ex) {
    // Chỉ dùng khi đã chấp nhận non-atomic và chính sách đích.
    Files.move(source, target);
}
```

**Giới hạn của fallback:** lệnh thứ hai **không bảo đảm nguyên tử**. Nếu nó phải copy rồi delete và phát sinh lỗi ở giữa, trạng thái nguồn/đích có thể không như dự kiến. Cũng phải xử lý trường hợp target bị tiến trình khác tạo ra, thư mục cha thay đổi hoặc hệ thống tệp gặp lỗi. Nếu fallback muốn **thay thế** đích, phải quyết định riêng việc dùng `REPLACE_EXISTING`; nó cũng không tạo ra atomicity.

Chỉ bắt `AtomicMoveNotSupportedException` cho quyết định không hỗ trợ atomicity. Không nên catch mọi `IOException` rồi fallback, vì lỗi quyền truy cập, thiếu dung lượng hoặc hỏng filesystem không được sửa bằng cách thực hiện lại dưới ngữ nghĩa yếu hơn.

## 8. Move giữa các ổ đĩa/filesystem

Một rename cấp filesystem thường dễ thực hiện nguyên tử **trong cùng filesystem** hơn là qua ranh giới volume/mount. Ví dụ:

```text
Ổ/volume A                  Ổ/volume B
/data/draft.bin    ------>  /archive/draft.bin
```

Nếu filesystem không hỗ trợ move nguyên tử giữa hai bên, yêu cầu `ATOMIC_MOVE` có thể dẫn đến `AtomicMoveNotSupportedException`. Một move thông thường được provider cho phép có thể được thực hiện bằng copy dữ liệu sang đích rồi xóa nguồn, hoặc thất bại tùy loại mục và provider. Không được giả định mọi thư mục nhiều cấp đều được copy đệ quy chỉ vì gọi `Files.move` một lần.

Một khác biệt quan trọng: **khi move không nguyên tử ném `IOException`, trạng thái file có thể không xác định**. Source và target có thể đều còn, target có thể không hoàn chỉnh, hoặc một phần metadata chưa được sao chép. Ứng dụng phải kiểm tra/phục hồi theo chính sách thay vì mặc định “move lỗi thì chắc chắn chưa thay đổi gì”.

| Kịch bản | Rủi ro hoặc kết quả |
| --- | --- |
| Rename trong cùng thư mục của filesystem hỗ trợ | Thường là thao tác đơn giản, atomicity chỉ được yêu cầu/kiểm tra khi dùng `ATOMIC_MOVE` |
| Move giữa hai thư mục cùng filesystem | Có thể được hỗ trợ nguyên tử; vẫn phụ thuộc provider |
| Move khác volume, mount, provider | Yêu cầu atomic có thể bị từ chối; move thông thường có thể thực hiện nhiều bước hoặc thất bại |
| Move mục là thư mục | Hợp đồng phụ thuộc provider, trạng thái target, ranh giới filesystem, cấu trúc thư mục |
| Move một symbolic link | Move bản thân link, không mặc định copy nội dung target |
| Move khi file đang được mở | Hành vi OS/provider quyết định; có thể thành công hoặc gặp lỗi chia sẻ/quyền |

Không lấy việc chương trình chạy thành công trên ổ đĩa nội bộ làm bằng chứng rằng nó chắc chắn hoạt động trên network share, container volume, mounted drive hoặc provider lưu trữ ảo.

## 9. Mẫu công bố file qua tên tạm, rồi chuyển sang tên đích

Một ứng dụng thường muốn producer tạo nội dung **đầy đủ** trước khi người khác đọc tên đích:

```text
(1) Tạo file tạm tại thư mục đích
          |
(2) Ghi đủ nội dung và đóng writer
          |
(3) Files.move(temp, finalName, ATOMIC_MOVE)
          |
(4) Người đọc truy cập tên finalName
```

Lý do đặt file tạm **trong cùng thư mục với đích**: tăng khả năng các mục ở cùng filesystem, giảm khả năng move trở thành chuyển volume. Nhưng điều này không tự chứng minh provider hỗ trợ `ATOMIC_MOVE`.

### Ví dụ 4 — công bố một file mới chỉ khi có atomic move

Ví dụ chọn **tên đích mới, chưa tồn tại** khi bắt đầu, tránh cố mô phỏng cập nhật/ghi đè một target hiện có. Nó yêu cầu atomic move; nếu không được hỗ trợ thì báo lỗi và **không có fallback ngầm**.

```java
// AtomicPublishDemo.java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class AtomicPublishDemo {
    static void publishNew(Path target, String text) throws IOException {
        Path absoluteTarget = target.toAbsolutePath();
        Path parent = absoluteTarget.getParent();
        Path temporary = Files.createTempFile(parent, ".draft-", ".tmp");

        try {
            Files.writeString(temporary, text, StandardCharsets.UTF_8);

            // Yêu cầu atomic move; không âm thầm dùng copy/delete.
            // Chính sách target trùng tên trong cạnh tranh phải được
            // xử lý riêng: ATOMIC_MOVE không bảo đảm no-overwrite.
            Files.move(temporary, absoluteTarget,
                    StandardCopyOption.ATOMIC_MOVE);
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("publish-demo-");
        Path published = directory.resolve("result.txt");

        try {
            publishNew(published, "complete");
            System.out.println("published="
                    + Files.readString(published, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(published);
            Files.deleteIfExists(directory);
        }
    }
}
```

```bash
javac AtomicPublishDemo.java
java AtomicPublishDemo
```

Khi provider hỗ trợ atomic move, không có xung đột đích và các thao tác thành công:

```text
published=complete
```

Nếu không hỗ trợ atomic move, chương trình **ném `AtomicMoveNotSupportedException`**, không in dòng `published=...`. Đây là kết quả được thiết kế để **không hạ cấp ngữ nghĩa một cách âm thầm**. `finally` cố dọn file tạm trong cả hai trường hợp.

**Cảnh báo về cạnh tranh:** đây không phải API “create only if absent” mang bảo đảm hoàn chỉnh cho các hệ thống khác nhau. Một tác vụ khác có thể tạo target sau khi mã chọn tên. Ngữ nghĩa của `ATOMIC_MOVE` khi target tồn tại là implementation-specific, nên nếu yêu cầu nghiêm ngặt **không bao giờ ghi đè file của người khác**, phải thiết kế chính sách phối hợp/đặt tên hoặc dùng API tạo mới phù hợp, thay vì tin vào `ATOMIC_MOVE` cộng một bước `exists()`.

### Nếu cần ghi đè bản cấu hình cũ?

Một mô hình thực tế là ghi toàn bộ phiên bản mới vào file tạm cùng filesystem, hoàn tất ghi, rồi công bố dưới tên ổn định. Nhưng cần thêm những quyết định:

- Có cho phép **replace** file đích không? Nếu cho phép, provider có atomic replace với mục đang tồn tại theo hợp đồng được kiểm chứng không?
- File đang được tiến trình khác mở thì hành vi ra sao? Đặc biệt Windows và Unix có sự khác biệt về rename/open handle.
- Có yêu cầu dữ liệu sống sót sau mất điện không? Việc đóng writer và đổi tên nguyên tử **không tự đảm bảo durability**; cần xem `FileChannel.force(...)`, đồng bộ metadata/thư mục và những bảo đảm của OS/filesystem.
- Có nhiều writer cạnh tranh không? Cần cơ chế version/lock/compare-and-swap phù hợp thay vì giả định atomic rename tự ngăn lost update.
- Consumer đang đọc một handle đã mở từ trước có cần tự chuyển sang phiên bản mới không? Không thể mặc định một rename sẽ làm nội dung của handle đang mở thay đổi theo cách ứng dụng mong muốn.

Đối với một ứng dụng cần tính nhất quán mạnh, phải mô tả **cấp độ bảo đảm** chứ không dùng từ “atomic” cho mọi tính chất.

## 10. Thứ tự ghi dữ liệu, đóng luồng và move

Không chuyển file sang tên công bố khi writer vẫn giữ dữ liệu trong bộ đệm:

```java
// Minh họa: temp và finalPath là Path đã có,
// charset UTF_8; code nằm trong phương thức throws IOException.
try (BufferedWriter writer =
        Files.newBufferedWriter(temp, StandardCharsets.UTF_8)) {
    writer.write("new configuration");
}

// Writer đã đóng trước khi công bố tên mới.
Files.move(temp, finalPath, StandardCopyOption.ATOMIC_MOVE);
```

Khi đóng `BufferedWriter`, dữ liệu chưa đẩy trong bộ đệm được xử lý và luồng bên dưới được đóng. Tuy nhiên, **close thành công không tự đồng nghĩa dữ liệu được đồng bộ bền vững xuống thiết bị**. Với bài toán chống mất điện, cần xác định riêng cơ chế durability.

Nếu move không có `ATOMIC_MOVE`, kết quả có thể vẫn thành công và trong cùng filesystem thường được thực hiện như rename, nhưng **API không bắt buộc** atomicity trong mọi hoàn cảnh. Chỉ khi **yêu cầu** atomicity và thao tác thành công theo hợp đồng provider bạn mới có thể dựa vào thuộc tính này.

## 11. Các ngoại lệ thường gặp khi move

| Exception | Ý nghĩa thường gặp | Cách xử lý |
| --- | --- | --- |
| `NoSuchFileException` | Nguồn hoặc một thành phần cần thiết không tồn tại | Xem lại source/parent; xử lý thay đổi đồng thời |
| `FileAlreadyExistsException` | Target xung đột trong thao tác không thay thế | Báo xung đột hoặc chuyển sang nhánh có chính sách replace rõ ràng |
| `AtomicMoveNotSupportedException` | Provider không hỗ trợ move nguyên tử cho cặp đường dẫn/tình huống | Nếu atomic bắt buộc: dừng; nếu không: fallback được chấp thuận |
| `DirectoryNotEmptyException` | Cố thay một thư mục đích không rỗng trong tình huống không được hỗ trợ | Không tự xóa nội dung của thư mục mà không có yêu cầu |
| `AccessDeniedException` | Provider báo thiếu quyền truy cập | Báo lỗi hoặc yêu cầu quyền đúng; không tự đổi quyền tùy tiện |
| `FileSystemException` | Lỗi filesystem có thông tin bổ sung | Log thông tin source/target và nguyên nhân; xử lý theo nghiệp vụ |
| `IOException` | Những lỗi I/O còn lại | Không giả định source/target bất biến sau một non-atomic failure |

Không phải mọi provider đều ném đúng subtype như bảng cho mọi lỗi. Đôi khi lỗi chung `IOException` được dùng thay subtype cụ thể. Khi ghi log, nên lưu path nguồn/đích theo cách không lộ dữ liệu nhạy cảm và giữ stack trace/exception liên quan.

### Không bắt mọi lỗi rồi thử ghi đè

Đây là một anti-pattern:

```java
// Đoạn minh họa cách làm KHÔNG AN TOÀN:
try {
    Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
} catch (IOException ex) {
    Files.move(source, target, StandardCopyOption.REPLACE_EXISTING);
}
```

Lý do: `IOException` có thể là lỗi quyền truy cập hoặc vấn đề hỏng filesystem, không nhất thiết do thiếu hỗ trợ atomic. Cách fallback trên cũng có thể **ghi đè một target khác** vốn được tạo trong lúc chạy. Ngoài ra sau một số lỗi non-atomic, trạng thái thực tế có thể phải được kiểm tra trước khi quyết định lại.

### Kiểm tra `exists()` không loại bỏ race condition

```java
if (!Files.exists(target)) {
    Files.move(source, target);
}
```

Đây là **đoạn mã minh họa có race**, không phải cách bảo đảm target vẫn vắng mặt tại thời điểm move. Đây là vấn đề **TOCTOU** (time of check to time of use). Một thread/process khác có thể tạo target ngay sau bước kiểm tra.

Tùy yêu cầu, hãy dựa vào ngữ nghĩa operation do provider bảo đảm, xử lý exception chính thức, hoặc dùng cơ chế phối hợp giữa những writer. Không ghép một `exists()` rồi suy ra “chắc chắn sẽ move thành công”.

## 12. So sánh với API truyền thống `File.renameTo()`

Java trước NIO.2 thường dùng:

```java
// Đoạn minh họa với oldFile và newFile thuộc java.io.File.
boolean renamed = oldFile.renameTo(newFile);
```

`File.renameTo(File)` vẫn tồn tại nhưng thường kém thích hợp cho logic cần kiểm soát lỗi:

- Trả về `boolean`, nên khi thất bại thường **không cung cấp chi tiết bằng exception I/O chuyên biệt**.
- Hành vi phụ thuộc nền tảng; có thể không làm được qua filesystem hoặc khi file đang mở.
- Không có đối số `ATOMIC_MOVE` tương đương để **yêu cầu** atomicity theo API này.
- Hành vi đối với target hiện hữu và nhiều loại mục khác nhau có thể khó dự đoán giữa các hệ thống.

Đối với mã Java 17+ cần xử lý rõ ràng, ưu tiên:

```java
Files.move(oldFile.toPath(), newFile.toPath());
```

Đây là đoạn minh họa. Chuyển `File` sang `Path` bằng `toPath()` không tự move hay tạo file; hành động thật diễn ra ở `Files.move(...)`.

| Tiêu chí | `File.renameTo()` | `Files.move()` |
| --- | --- | --- |
| Đổi tên trong cùng thư mục | Có thể làm được | Có |
| Chuyển sang thư mục khác | Phụ thuộc nền tảng | Có API rõ ràng, vẫn phụ thuộc filesystem/provider |
| Báo lỗi I/O | Thường là `false` | `IOException` và subtype hữu ích |
| Cho phép replace target có chủ đích | Không có option NIO.2 tương đương | `REPLACE_EXISTING` cho move thường |
| Yêu cầu atomic move | Không có tùy chọn chuẩn tương tự | `ATOMIC_MOVE` |
| Khả năng xử lý Path/provider | `File` gắn với đường dẫn truyền thống | `Path` là abstraction của filesystem provider |

## 13. Di chuyển thư mục, file mở và symbolic link

### Thư mục

`Files.move()` có thể áp dụng với thư mục, nhưng không có nghĩa nó sẽ thực hiện **recursive copy toàn bộ cây dữ liệu sang ổ đĩa khác** trong mọi tình huống. Trong cùng filesystem, đổi tên thư mục có thể là thao tác metadata; qua filesystem khác, yêu cầu có thể không được hỗ trợ. Đích là thư mục không rỗng cũng là trường hợp đặc biệt.

Không nhầm:

```text
đổi tên thư mục (move directory entry)
```

với:

```text
duyệt từng file con -> copy -> verify -> delete source tree
```

Hai quy trình có đặc tính lỗi, thời gian, quyền và atomicity rất khác nhau.

### File đang được mở

Một số hệ thống cho phép rename/move một file khi tiến trình vẫn giữ handle đọc; một số hệ thống có thể từ chối do quy tắc chia sẻ/quyền. Java không cam kết cùng một kết quả trên Windows, Unix, network share và mọi provider. Đừng dùng kết quả một test trên máy cá nhân làm hợp đồng đa nền tảng.

### Symbolic link

Với source là symbolic link, `Files.move` di chuyển **chính đối tượng link**. Link có thể tiếp tục trỏ tới đường dẫn cũ và trở thành broken link sau move nếu giá trị target của link là relative path và ngữ cảnh thư mục thay đổi. Nếu ứng dụng muốn chuyển nội dung đích của link, cần xử lý theo chính sách riêng.

### Thuộc tính và quyền

Việc di chuyển mục có thể tác động metadata theo cách phụ thuộc provider/volume. Đừng mặc định mọi timestamp, ACL, owner, file key hoặc thuộc tính đặc thù vẫn được giữ nguyên, đặc biệt ở move qua filesystem khác. Nếu nghiệp vụ cần các thuộc tính nhất định, hãy đọc/kiểm tra chúng theo API thích hợp sau khi thực hiện.

## 14. Checklist chọn cách move phù hợp

1. **Mục tiêu là gì?** Đổi tên trong cùng thư mục, di chuyển sang nơi khác hay công bố phiên bản mới?
2. **Nguồn có tồn tại?** Không chỉ kiểm tra trước; vẫn cần xử lý kết quả I/O thật và lỗi do thay đổi đồng thời.
3. **Target có thể tồn tại không?** Xác định rõ “từ chối”, “cho phép thay thế”, hoặc “đổi sang tên khác”.
4. **Có cần atomicity không?** Nếu cần, yêu cầu `ATOMIC_MOVE` và thất bại có kiểm soát khi không hỗ trợ.
5. **Có cần replace atomic không?** Không được mặc định `ATOMIC_MOVE + REPLACE_EXISTING` là bảo đảm di động; behavior của target tồn tại là implementation-specific.
6. **Cùng filesystem hay không?** Đặt temp cùng thư mục đích để tăng khả năng atomic move, nhưng không suy ra chắc chắn.
7. **Đã hoàn tất ghi và đóng writer chưa?** Move không tự đảm bảo dữ liệu còn trong buffer của writer đã được đẩy xuống.
8. **Có yêu cầu chống mất điện/durability không?** Tách khỏi vấn đề atomic rename; có thể cần `FileChannel.force()` và các bước đồng bộ metadata.
9. **Có nguồn/đích là thư mục, symbolic link hoặc file đang mở?** Xét hợp đồng từng provider và loại mục.
10. **Nếu move lỗi thì phục hồi thế nào?** Đặc biệt với non-atomic move, không mặc định source/target giữ nguyên trạng thái.
11. **Có nhiều writer cạnh tranh không?** Cần một giao thức đồng bộ/phiên bản thay vì chỉ dựa vào tên file.
12. **Làm sao kiểm thử?** Thử trường hợp file đích có/không có, provider hỗ trợ/không hỗ trợ atomic move, quyền truy cập và crash/failure phù hợp.

## 15. Lỗi phổ biến và cách khắc phục

| Lỗi hiểu hoặc thực hành | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| Gọi `Files.move()` mặc định rồi nói chắc chắn atomic | API không yêu cầu atomic nếu không có option | Sử dụng `ATOMIC_MOVE` khi cần và xử lý exception |
| Nghĩ `REPLACE_EXISTING` cũng đồng nghĩa atomic | Replace và atomic là các thuộc tính khác nhau | Phân biệt rõ điều kiện replace và atomicity |
| Nghĩ `ATOMIC_MOVE, REPLACE_EXISTING` chắc chắn ghi đè atomically | Khi có atomic option, các option còn lại bị bỏ qua | Xác minh ngữ nghĩa provider và chính sách target |
| Bắt `IOException` rồi fallback non-atomic | Che lỗi thực sự, có thể làm mất tính nhất quán | Chỉ fallback khi gặp `AtomicMoveNotSupportedException` và được chấp thuận |
| Tạo temp ở volume khác đích | Atomic move thường không hỗ trợ qua filesystem | Tạo temp cạnh target khi phù hợp |
| Move file trước khi đóng `BufferedWriter` | Nội dung có thể còn trong buffer | Hoàn tất ghi/đóng writer trước khi move |
| Coi atomic rename là bảo đảm chống mất điện | Namespace atomicity khác độ bền dữ liệu | Thiết kế đồng bộ dữ liệu và metadata riêng |
| Sau lỗi non-atomic move, giả sử source còn nguyên | Có thể cả hai file còn hoặc target dang dở | Kiểm tra trạng thái và phục hồi cẩn trọng |
| Tự dùng `File.renameTo()` trong code cần nguyên nhân lỗi rõ | Kết quả boolean thiếu nhiều thông tin | Dùng `Files.move()` và bắt lỗi cụ thể |
| Coi move thư mục khác ổ là recursive copy | Không phải hợp đồng move chung | Thiết kế copy/verify/delete riêng nếu thật sự cần |
| Kiểm tra `!exists(target)` rồi tin không ai tạo target | Có TOCTOU | Dựa vào hợp đồng operation và đồng bộ giữa writer |
| Coi mọi symlink là file đích của nó | Move link không mặc định move nội dung target | Phân biệt link và target |

## 16. Tự kiểm tra

**Câu 1.** Đổi `a.txt` thành `b.txt` cùng thư mục có phải một dạng move không?

**Đáp án:** Có. Với NIO.2, dùng `Files.move(source, source.resolveSibling("b.txt"))`.

**Câu 2.** `Files.move(source, target)` mặc định có cam kết atomicity không?

**Đáp án:** Không. Nếu cần move nguyên tử, phải yêu cầu `StandardCopyOption.ATOMIC_MOVE` và xử lý trường hợp không hỗ trợ.

**Câu 3.** Hai file `source.txt` và `target.txt` cùng tồn tại. Cần thay target theo quy tắc move thông thường thì chọn option nào?

**Đáp án:** `StandardCopyOption.REPLACE_EXISTING`, lưu ý quy tắc thay thế phụ thuộc loại mục/provider và không tự cam kết atomicity.

**Câu 4.** Vì sao `Files.move(src, dst, ATOMIC_MOVE, REPLACE_EXISTING)` không có nghĩa chắc chắn “atomic replace”?

**Đáp án:** Khi có `ATOMIC_MOVE`, các option khác bị bỏ qua; hành vi khi target đã tồn tại là implementation-specific.

**Câu 5.** Một file ở ổ A cần move sang ổ B; có luôn thực hiện `ATOMIC_MOVE` được không?

**Đáp án:** Không. Qua filesystem/volume có thể không hỗ trợ nguyên tử và ném `AtomicMoveNotSupportedException`.

**Câu 6.** Có nên bắt mọi `IOException` của atomic move để tự gọi non-atomic move không?

**Đáp án:** Không. Chỉ fallback khi nguyên nhân phù hợp (thường là `AtomicMoveNotSupportedException`) và nghiệp vụ cho phép từ bỏ atomicity.

**Câu 7.** `Files.move` trả về `Path` nào khi thành công?

**Đáp án:** Đường dẫn đại diện **target**.

**Câu 8.** Atomic move có đủ để bảo đảm dữ liệu vẫn còn sau mất điện không?

**Đáp án:** Không. Atomicity của thao tác đổi tên không đồng nghĩa durability của nội dung hoặc metadata.

**Câu 9.** Khi source là symbolic link, `Files.move` chuyển nội dung file ở đầu kia của link hay chuyển chính link?

**Đáp án:** Chuyển **chính symbolic link**, theo hợp đồng move.

**Câu 10.** Vì sao không thể mặc định non-atomic move lỗi thì “chưa có gì thay đổi”?

**Đáp án:** Có thể thao tác đã copy được một phần hoặc thay đổi metadata trước khi thất bại; API không bảo đảm trạng thái source/target sau lỗi non-atomic.

**Câu 11.** Tạo file tạm ở cùng thư mục đích có đảm bảo mọi move nguyên tử không?

**Đáp án:** Không. Nó làm giảm rủi ro khác filesystem, nhưng provider vẫn có thể không hỗ trợ `ATOMIC_MOVE`.

**Câu 12.** Khi ứng dụng cần publish file mới mà không cho phép bất kỳ ghi đè nào, có nên chỉ dùng `ATOMIC_MOVE` và `Files.exists(target)==false` không?

**Đáp án:** Không đủ. `exists()` dễ bị race và khi atomic move gặp target đã tồn tại, ngữ nghĩa xử lý phụ thuộc implementation. Cần chính sách tên, khóa/điều phối hoặc cơ chế tạo mới và kiểm tra tương ứng với yêu cầu.

**Ghi nhớ:** `Files.move()` là API ưu tiên để **đổi tên hoặc di chuyển** tệp. `REPLACE_EXISTING` giải quyết chính sách **đích đã tồn tại** trong move thông thường; `ATOMIC_MOVE` yêu cầu **di chuyển nguyên tử** nhưng có thể không được hỗ trợ, và khi dùng nó, **các option còn lại bị bỏ qua**. Atomic rename không tương đương giao dịch nhiều file hoặc bảo đảm độ bền sau mất điện. Chỉ cho phép fallback non-atomic nếu ứng dụng chủ động chấp nhận rủi ro, đồng thời luôn xử lý trạng thái và exception của thao tác thật.
