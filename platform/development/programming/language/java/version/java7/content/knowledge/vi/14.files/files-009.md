# Di chuyển nguyên tử bằng `Files.move` và xử lý `AtomicMoveNotSupportedException`

> **Chủ đề:** `java.nio.file.Files.move(Path source, Path target, CopyOption... options)` và `StandardCopyOption.ATOMIC_MOVE`, hai API NIO.2 có từ **Java 7** và vẫn dùng trong Java hiện đại. Bài giải thích khi nào một thao tác đổi tên/di chuyển có thể được thực hiện **nguyên tử** ở mức filesystem, cách bắt đúng `AtomicMoveNotSupportedException`, lựa chọn **fail-closed** hay **fallback không nguyên tử** theo hợp đồng ứng dụng, sự khác biệt với `REPLACE_EXISTING`, và những giới hạn về độ bền dữ liệu, symlink, quyền truy cập, file đang mở và khả năng hỗ trợ của file-system provider. Các ví dụ đầy đủ được biên dịch trên **JDK 17+**.

## 1. Tại sao cần một phép di chuyển nguyên tử?

Giả sử ứng dụng đang tạo báo cáo `report.json` để một tiến trình khác đọc. Nếu ghi thẳng nội dung mới vào đường dẫn được công khai, tiến trình đọc có thể mở file **khi tác vụ ghi vẫn đang diễn ra** và thấy tệp chưa hoàn chỉnh.

Một ý tưởng thường dùng:

1. Tạo một **file staging** riêng bên trong thư mục đích hoặc cùng file store.
2. Ghi đầy đủ nội dung vào staging rồi **đóng** writer/stream.
3. Yêu cầu filesystem di chuyển/đổi tên staging sang vị trí công khai bằng **một thao tác nguyên tử** nếu khả dụng.
4. Chỉ khi bước 3 thành công mới coi **việc công bố tên đích** hoàn tất.

Minh họa:

```text
Trong lúc ghi:
output/
  .staging-123.tmp   (đang ghi, không dùng làm tên công khai)
  report.json        (chưa có, hoặc phiên bản cũ)

Sau khi đóng file staging và atomic move thành công:
output/
  report.json        (tên công khai trỏ đến tệp đã chuẩn bị)
```

Ở đây **nguyên tử** có nghĩa thao tác filesystem không được quan sát như một chuỗi bước di chuyển tạm thời có trạng thái trung gian theo hợp đồng `ATOMIC_MOVE`. Không có nghĩa mọi thao tác bên trong chương trình tự động là transaction, và **không** tự bảo đảm dữ liệu còn nguyên sau crash/mất điện.

Đối với việc thay thế file **đã tồn tại**, còn một ràng buộc nữa: theo Javadoc, nếu dùng `ATOMIC_MOVE` mà target đã tồn tại thì **hành vi thay thế hay báo lỗi là phụ thuộc implementation**. Vì vậy mẫu “công bố file mới khi target chưa có” đơn giản hơn mẫu “thay thế bản hiện tại” về yêu cầu tương thích đa nền tảng.

## 2. Các API phải nắm

Chữ ký chính:

```java
public static Path move(
        Path source,
        Path target,
        CopyOption... options
) throws IOException;
```

Đây là **chữ ký minh họa** của method trong `java.nio.file.Files`, không phải code người học phải khai báo lại. Vì dùng varargs `CopyOption...`, lời gọi có thể không truyền option hoặc truyền một số option như `StandardCopyOption.ATOMIC_MOVE`.

Cách gọi nguyên tử:

```java
Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
```

Đây là **snippet**; `source` và `target` là `Path` đã xác định, method caller cần khai báo hoặc xử lý `IOException`. Các import thông dụng:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.AtomicMoveNotSupportedException;
```

Hai enum constant nên phân biệt:

| Option | Ý nghĩa chính | Điều cần nhớ |
| --- | --- | --- |
| Không có option | Di chuyển/đổi tên theo mặc định | Có thể không nguyên tử, thường từ chối khi target tồn tại |
| `StandardCopyOption.REPLACE_EXISTING` | Yêu cầu thay thế target khi có thể | **Không** tự làm move nguyên tử |
| `StandardCopyOption.ATOMIC_MOVE` | Yêu cầu thao tác move nguyên tử | Có thể ném `AtomicMoveNotSupportedException`; khi dùng, **mọi option khác bị bỏ qua** |

### 2.1. Ý nghĩa của chữ “atomic”

Đối với một lần move thành công có `ATOMIC_MOVE`, filesystem xử lý thao tác chuyển vị trí/tên theo cam kết nguyên tử của provider. Điều này phù hợp với việc publish một file đã chuẩn bị hoàn chỉnh: tên công khai xuất hiện theo một sự kiện chuyển đổi, thay vì để người đọc quan sát một lần copy từng phần từ source sang target.

Nhưng một chương trình có thể cần làm nhiều bước:

```text
Tạo file staging → ghi → đóng → move → cập nhật database → gửi thông báo
```

Chỉ **bước move** là ứng viên cho atomic filesystem operation. Toàn bộ chuỗi không thành **một transaction phân tán**. Nếu database update thất bại sau move, Java không tự rollback file. Nếu hệ thống mất điện sau rename, độ bền metadata và nội dung đã ghi còn phụ thuộc OS/filesystem và chính sách flush.

### 2.2. `ATOMIC_MOVE` không phải một lời hứa thành công

Javadoc định nghĩa rằng nếu move không thể thực hiện như một atomic filesystem operation, Java ném `AtomicMoveNotSupportedException`. Các nguyên nhân có thể gồm:

- Source và target nằm trên **FileStore khác nhau**, cần copy dữ liệu chứ không chỉ rename một directory entry.
- Hai đường dẫn thuộc **provider khác nhau**.
- Provider hoặc filesystem không hỗ trợ kiểu atomic move yêu cầu trong tình huống cụ thể.
- Những giới hạn của tài nguyên và môi trường có thể dẫn đến **IOException khác** (thiếu quyền, file đang được sử dụng, target không phù hợp...), không nhất thiết là `AtomicMoveNotSupportedException`.

**Không đoán khả năng hỗ trợ chỉ từ tên hệ điều hành.** Một Windows/Linux/macOS có thể gắn nhiều filesystem, network mounts hoặc providers với đặc tính khác nhau. Cần thử thao tác thật hoặc kiểm tra capability trong một môi trường có kiểm soát.

## 3. Mẫu cơ bản: yêu cầu move nguyên tử và bắt đúng ngoại lệ

```java
try {
    Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
    // Chỉ vào đây khi Files.move trả về bình thường.
} catch (AtomicMoveNotSupportedException unsupported) {
    // Quyết định: dừng, giữ staging, hoặc fallback nếu hợp đồng cho phép.
}
```

Đây là snippet với các biến/import đã có. `AtomicMoveNotSupportedException` là một **checked exception**, phân lớp dưới:

```text
Exception
  └─ IOException
       └─ FileSystemException
            └─ AtomicMoveNotSupportedException
```

Vì là subtype của `IOException`, handler riêng cho unsupported phải đứng **trước** `catch (IOException error)` nếu dùng cả hai:

```java
try {
    Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
} catch (AtomicMoveNotSupportedException unsupported) {
    // Không có bảo đảm atomic trong tình huống này.
} catch (IOException otherIoError) {
    // Lỗi I/O khác: không tự động coi là thiếu hỗ trợ atomic.
}
```

Nếu đảo hai `catch`, nhánh cụ thể có thể bị compiler báo unreachable do lỗi đã bị bắt bởi superclass.

**Nguyên tắc:** chỉ fallback vì thiếu hỗ trợ nguyên tử khi bạn **cố ý** cho phép giảm mức bảo đảm. Đừng viết `catch(IOException e)` rồi mặc nhiên gọi lại `Files.move` không option; một lỗi thiếu quyền, file đang bị khóa hay filesystem hỏng **không phải tín hiệu cho phép hạ chuẩn bảo đảm**.

## 4. Chương trình đầy đủ: kiểm tra atomic move trên filesystem hiện tại

Lưu thành `AtomicMoveBasicDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class AtomicMoveBasicDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("atomic-basic-");
        Path source = dir.resolve("incoming.tmp");
        Path target = dir.resolve("ready.txt");
        try {
            Files.writeString(source, "READY", StandardCharsets.UTF_8);
            try {
                Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
                System.out.println("atomic=SUPPORTED");
                System.out.println("sourceExists=" + Files.exists(source));
                System.out.println("targetContent=" +
                        Files.readString(target, StandardCharsets.UTF_8));
            } catch (AtomicMoveNotSupportedException unsupported) {
                System.out.println("atomic=UNSUPPORTED");
                System.out.println("sourceStillExists=" + Files.exists(source));
            }
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(target);
            Files.deleteIfExists(dir);
        }
    }
}
```

Chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 --release 17 AtomicMoveBasicDemo.java
java AtomicMoveBasicDemo
```

**Kết quả đã chạy trên filesystem kiểm thử có hỗ trợ**:

```text
atomic=SUPPORTED
sourceExists=false
targetContent=READY
```

**Khi provider không hỗ trợ atomic move** và phát sinh đúng exception yêu cầu, nhánh dự kiến là:

```text
atomic=UNSUPPORTED
sourceStillExists=true
```

Hai nhánh **không phải hai lần kiểm thử thật**: nhánh hỗ trợ đã chạy thành công trên máy kiểm thử, còn nhánh unsupported là hành vi theo hợp đồng và được kiểm chứng độc lập bằng test mô phỏng ở mục 6.

### 4.1. Tại sao đặt source và target trong cùng thư mục?

`Files.createTempDirectory` tạo một thư mục thử nghiệm. `source` và `target` cùng ở đó nên có cơ hội cao để provider thực hiện một rename nguyên tử, không cần copy giữa file stores. Nhưng **cùng thư mục không phải bằng chứng tuyệt đối** rằng mọi provider luôn hỗ trợ atomic move.

Với ứng dụng thật, tạo staging **ngay trong thư mục đích** thường là lựa chọn hợp lý. Không tạo staging ở thư mục temp mặc định rồi mặc nhiên giả định nó nằm cùng volume với thư mục xuất bản.

### 4.2. Sự khác nhau giữa tên và nội dung

Đầu vào có tên `incoming.tmp` và chứa chuỗi `READY`. Sau move thành công:
- `sourceExists=false` theo phép kiểm tra ngay sau lệnh.
- `targetContent=READY`, đọc từ đường dẫn mới.
- Không có bước `Files.copy` tường minh trong code.
- `Files.move(...)` trả về `Path target` nếu hoàn thành bình thường.

Việc in `sourceExists=false` là quan sát **khi không có tiến trình nào khác can thiệp** trong demo. Trong chương trình đồng thời thực tế, có tác nhân khác tạo lại tên source sau thao tác; không suy ra bảo đảm dài hạn chỉ từ một lệnh `Files.exists`.

### 4.3. Vì sao không có `REPLACE_EXISTING` ở ví dụ này?

`target` được tạo tên nhưng **không có file tương ứng trước move**. Demo tập trung vào atomic move không đụng đến luật thay thế file đã có. Đối với target hiện hữu, hành vi cùng `ATOMIC_MOVE` là **implementation-specific**, sẽ được phân tích riêng.

## 5. Phân biệt “không hỗ trợ nguyên tử” với lỗi di chuyển khác

Các tình huống thường gặp:

| Điều kiện | Loại lỗi thường gặp | Cách hiểu |
| --- | --- | --- |
| Provider không thể thực hiện atomic move | `AtomicMoveNotSupportedException` | Yêu cầu tính nguyên tử không đáp ứng |
| Source không còn tồn tại | `NoSuchFileException` hoặc `IOException` tương ứng | Vấn đề nguồn, không phải lời mời fallback |
| Không đủ quyền truy cập/ghi | `AccessDeniedException` hoặc `IOException` | Vấn đề quyền/cấu hình/tài nguyên |
| Target đã có và bị từ chối | `FileAlreadyExistsException` hoặc `IOException` | Tùy option/provider; với `ATOMIC_MOVE` hành vi target tồn tại phụ thuộc implementation |
| Target là thư mục không rỗng hoặc không phù hợp | `DirectoryNotEmptyException` hoặc `IOException` | Không được suy ra atomic unsupported |
| Source/target ở FileStore khác nhau | Có thể phát sinh `AtomicMoveNotSupportedException` khi yêu cầu atomic | Provider không thể đảm bảo một move nguyên tử qua ranh giới đó |
| Tên không hợp lệ theo provider | `InvalidPathException` khi tạo Path hoặc lỗi filesystem sau đó | Kiểm tra input/path schema riêng |
| File bị tiến trình khác dùng/khóa | Có thể là `IOException` tùy OS | Điều kiện tương tranh và file handle |

Danh sách các subclass cụ thể không phải “luôn đúng y hệt trên mọi hệ điều hành”. Javadoc gọi một số specific exceptions là **optional**. Điều vững chắc để thiết kế là hợp đồng API và phân biệt nhánh unsupported với các lỗi I/O khác.

### 5.1. Dùng chi tiết exception để chẩn đoán

`AtomicMoveNotSupportedException` kế thừa `FileSystemException`, nên có các method:

```java
String sourcePath = unsupported.getFile();
String targetPath = unsupported.getOtherFile();
String detail = unsupported.getReason();
```

Đây là snippet bên trong handler `catch (AtomicMoveNotSupportedException unsupported)`. Các giá trị có thể null nếu thông tin không được biết/cung cấp. Vì là đường dẫn nội bộ, cần **kiểm soát việc ghi log và không lộ full path máy chủ** ra response công khai.

Những thông tin hữu ích khác khi điều tra:
- Source và target thuộc provider nào?
- Chúng nằm trên file store nào?
- Operation đang dùng `ATOMIC_MOVE` cùng những option gì?
- File/dir hiện hữu nào có quyền truy cập bất thường?
- Có antivirus, indexing, network filesystem, tiến trình khác hoặc background service can thiệp không?

Không đoán rằng chỉ vì `FileStore` giống nhau thì atomic move **chắc chắn** khả dụng; đó chỉ là một tín hiệu hỗ trợ phân tích.

## 6. Hai chính sách xử lý `AtomicMoveNotSupportedException`

Khi yêu cầu atomic move thất bại, có **hai chiến lược đúng trong những điều kiện khác nhau**.

### 6.1. Fail-closed: không giảm bảo đảm nguyên tử

Nếu dữ liệu cần **không bao giờ xuất hiện ở target dưới dạng chưa hoàn chỉnh**, hoặc giao diện hợp đồng quy định atomic publish là bắt buộc, hãy **ném lại exception** hoặc chuyển thành lỗi ứng dụng có thể xử lý. Không tự động chuyển sang non-atomic move.

```java
try {
    Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
} catch (AtomicMoveNotSupportedException unsupported) {
    // Log có kiểm soát rồi dừng công bố.
    throw unsupported;
}
```

Đây là snippet trong method khai báo `throws IOException`. Khi throw lại, caller biết yêu cầu atomic **không được đáp ứng**. File staging có thể được giữ để retry/hỗ trợ vận hành hoặc dọn theo một chính sách rollback/cleanup rõ ràng. Không xóa file cũ/dữ liệu tạm một cách mù quáng nếu sự cố cần điều tra.

### 6.2. Fallback: chủ động chấp nhận một move không nguyên tử

Một ứng dụng có thể chỉ muốn chuyển file tạm để sắp xếp thư mục, chấp nhận rằng reader có thể thấy trạng thái trung gian khi provider phải copy. Khi đó fallback là một **quyết định chính sách**, không phải cách “sửa lỗi” về mặt kỹ thuật.

```java
try {
    Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
} catch (AtomicMoveNotSupportedException unsupported) {
    Files.move(source, target); // Fallback không có bảo đảm atomic.
}
```

Đây là snippet, không phải hướng dẫn áp dụng chung. Nó chỉ phù hợp nếu dữ liệu cho phép thao tác không nguyên tử, và ứng dụng đã xem xét **trạng thái khi move không nguyên tử thất bại**.

**Đừng ghi log “atomic move succeeded” sau fallback.** Kết quả nghiệp vụ nên phân biệt `ATOMIC` với `NON_ATOMIC` nếu khác biệt có ý nghĩa cho người dùng hoặc hệ thống downstream.

### 6.3. Vì sao không fallback sau mọi `IOException`?

Một `IOException` khác có thể xuất hiện vì thiếu quyền, không đủ dung lượng, file đã bị xóa, target sai loại hoặc lỗi I/O thực. Việc gọi move lại mà không có nguyên nhân rõ có thể:
- Ghi đè dữ liệu ngoài ý muốn nếu thêm sai option.
- Làm khó xác định source/target hiện đang ở trạng thái nào.
- Biến một lỗi cấu hình/permission thành một chuỗi thao tác mới nguy hiểm.
- Thay đổi tính nguyên tử của sản phẩm mà caller không được biết.

Hãy chỉ bắt loại exception bạn **biết cách phục hồi**, còn các lỗi khác để caller xử lý theo hợp đồng.

## 7. Chương trình đầy đủ: mô phỏng ngoại lệ để kiểm thử chính sách

Một vấn đề khi test: nếu máy lập trình hỗ trợ atomic move, làm sao **kiểm thử được nhánh unsupported** mà không phải gắn thêm một filesystem khác?

Giải pháp: đưa thao tác atomic vào một interface nhỏ và dùng **test double** có chủ đích ném `AtomicMoveNotSupportedException`. Điều này kiểm chứng đúng đường điều khiển của ứng dụng, nhưng **không chứng minh** filesystem thật có hay không có khả năng atomic move. Test tích hợp thật vẫn cần riêng.

Lưu thành `AtomicMovePolicyDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class AtomicMovePolicyDemo {
    @FunctionalInterface
    interface AtomicMover {
        void move(Path source, Path target) throws IOException;
    }

    static boolean publish(Path source, Path target, boolean allowFallback,
                           AtomicMover atomicMover) throws IOException {
        try {
            atomicMover.move(source, target);
            return true;
        } catch (AtomicMoveNotSupportedException unsupported) {
            if (!allowFallback) {
                throw unsupported;
            }
            Files.move(source, target);
            return false;
        }
    }

    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("atomic-policy-");
        Path sourceStrict = dir.resolve("strict.tmp");
        Path targetStrict = dir.resolve("strict.txt");
        Path sourceFallback = dir.resolve("fallback.tmp");
        Path targetFallback = dir.resolve("fallback.txt");
        Path sourceError = dir.resolve("other-error.tmp");
        Path targetError = dir.resolve("other-error.txt");

        AtomicMover simulatedUnsupported = (source, target) -> {
            throw new AtomicMoveNotSupportedException(
                    source.toString(), target.toString(), "test simulation");
        };

        try {
            Files.writeString(sourceStrict, "strict", StandardCharsets.UTF_8);
            try {
                publish(sourceStrict, targetStrict, false, simulatedUnsupported);
                throw new AssertionError("Expected unsupported atomic move");
            } catch (AtomicMoveNotSupportedException expected) {
                System.out.println("failClosed=UNSUPPORTED");
            }
            System.out.println("strictSourceRemains=" + Files.exists(sourceStrict));
            System.out.println("strictTargetAbsent=" + Files.notExists(targetStrict));

            Files.writeString(sourceFallback, "fallback", StandardCharsets.UTF_8);
            boolean atomic = publish(
                    sourceFallback, targetFallback, true, simulatedUnsupported);
            System.out.println("fallbackAtomic=" + atomic);
            System.out.println("fallbackContent=" +
                    Files.readString(targetFallback, StandardCharsets.UTF_8));

            Files.writeString(sourceError, "data", StandardCharsets.UTF_8);
            try {
                publish(sourceError, targetError, true, (source, target) -> {
                    throw new IOException("simulated I/O failure");
                });
                throw new AssertionError("Expected I/O failure");
            } catch (IOException expected) {
                System.out.println("otherError=" + expected.getMessage());
            }
            System.out.println("otherSourceRemains=" + Files.exists(sourceError));
        } finally {
            Files.deleteIfExists(sourceStrict);
            Files.deleteIfExists(targetStrict);
            Files.deleteIfExists(sourceFallback);
            Files.deleteIfExists(targetFallback);
            Files.deleteIfExists(sourceError);
            Files.deleteIfExists(targetError);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 AtomicMovePolicyDemo.java
java AtomicMovePolicyDemo
```

Stdout **đã chạy thực tế**:

```text
failClosed=UNSUPPORTED
strictSourceRemains=true
strictTargetAbsent=true
fallbackAtomic=false
fallbackContent=fallback
otherError=simulated I/O failure
otherSourceRemains=true
```

### 7.1. Vì sao bộ test này có giá trị?

- `simulatedUnsupported` cố ý ném đúng subclass cần thử. Nhờ thế test có thể đi vào nhánh `catch` mà không phụ thuộc vào file store.
- Với `allowFallback=false`, `publish` ném lại; source vẫn còn, target chưa xuất hiện.
- Với `allowFallback=true`, nó gọi `Files.move` **không có ATOMIC_MOVE**; `false` trả về để diễn đạt kết quả không bảo đảm atomic, dù move thực tế có thể tình cờ được provider thực hiện bằng rename.
- Một `IOException("simulated I/O failure")` **không phải** `AtomicMoveNotSupportedException`, nên không kích hoạt fallback. Điều đó chứng minh code không bắt tràn lan mọi IOException.

**Chính xác về ý nghĩa boolean:** `publish` trả true khi đường đi qua `AtomicMover` hoàn tất bình thường theo hợp đồng interface. Trong production, hãy truyền implementation thực sự gọi `Files.move(..., ATOMIC_MOVE)`. Với test double cố ý ném ngoại lệ, không có tình huống trả true; giá trị false biểu thị đường fallback. Điều này **không** đo được atomicity của lần `Files.move` không option: nó chỉ xác nhận ứng dụng không yêu cầu/không có bảo đảm atomic cho fallback.

### 7.2. Cách gắn mover thật vào cùng thiết kế

Trong code ứng dụng có thể truyền:

```java
AtomicMovePolicyDemo.publish(
        source,
        target,
        false,
        (s, t) -> {
            Files.move(s, t, StandardCopyOption.ATOMIC_MOVE);
        }
);
```

Đây là **snippet trong ngữ cảnh có class/biến ở chương trình đầy đủ**, với policy `false` nghĩa là không fallback. Lựa chọn có inject interface hay dùng thẳng `Files.move` tùy mức độ cần test lỗi/hỗ trợ provider; không nhất thiết mọi method nhỏ đều cần abstraction.

### 7.3. Khi nào fallback có thể khiến dữ liệu không an toàn?

Nếu ứng dụng cho phép reader mở `target` ngay khi nó xuất hiện, và non-atomic move phải copy một file lớn giữa file stores, reader có thể quan sát target chưa hoàn chỉnh. Nếu đó là điều **không chấp nhận**, đặt `allowFallback=false` và không triển khai non-atomic publication.

Nếu fallback được phép, nên cân nhắc thiết kế để reader không bao giờ đọc target đang copy, ví dụ chuyển sang một staging **không phải tên công khai** trong file store đích, hoàn tất copy, sau đó thử một atomic rename **ở file store đích**. Kế hoạch này vẫn phụ thuộc atomic capability của bước cuối và phải có cleanup/recovery riêng.

## 8. Quy trình staging → đóng → atomic publish

Một use case hiện đại: tạo dữ liệu mới, để downstream chỉ thấy một file đã ghi xong. Chương trình:

1. Tạo thư mục thử nghiệm do code sở hữu.
2. Tạo file staging **ngay trong thư mục đích**.
3. Ghi String UTF-8 vào staging rồi đóng resource của `Files.writeString`.
4. Gọi `Files.move(staging, target, ATOMIC_MOVE)` với target chưa tồn tại.
5. Nếu unsupported, **không fallback**; báo rõ sự cố.
6. Dọn dữ liệu thử nghiệm.

### 8.1. Chương trình đầy đủ

Lưu thành `StagedAtomicPublishDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class StagedAtomicPublishDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("atomic-publish-");
        Path target = dir.resolve("published.txt");
        Path staging = null;
        try {
            staging = Files.createTempFile(dir, ".staging-", ".tmp");
            Files.writeString(staging, "COMPLETE", StandardCharsets.UTF_8);

            try {
                Files.move(staging, target, StandardCopyOption.ATOMIC_MOVE);
                System.out.println("publish=ATOMIC");
                System.out.println("content=" +
                        Files.readString(target, StandardCharsets.UTF_8));
                System.out.println("stagingGone=" + Files.notExists(staging));
            } catch (AtomicMoveNotSupportedException unsupported) {
                System.out.println("publish=UNSUPPORTED");
                System.out.println("stagingRetained=" + Files.exists(staging));
            }
        } finally {
            if (staging != null) {
                Files.deleteIfExists(staging);
            }
            Files.deleteIfExists(target);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 StagedAtomicPublishDemo.java
java StagedAtomicPublishDemo
```

Stdout đã kiểm chứng ở file store hỗ trợ:

```text
publish=ATOMIC
content=COMPLETE
stagingGone=true
```

Khi provider không thể di chuyển nguyên tử, nhánh dự kiến:

```text
publish=UNSUPPORTED
stagingRetained=true
```

Ở nhánh unsupported, code **không xuất bản `published.txt`** bằng một move không nguyên tử. Nó giữ staging đến bước cleanup `finally` và báo rằng thao tác chưa đạt điều kiện cần. Đây là một minh họa **fail-closed**; ứng dụng thật có thể chọn giữ staging để retry an toàn, chuyển sang một file store thích hợp hoặc trả lỗi cho caller, thay vì luôn xóa.

### 8.2. Tại sao `Files.createTempFile(dir, ...)` thay vì `Files.createTempFile(prefix,suffix)`?

Overload có tham số `dir` tạo staging trong **thư mục đích mà ứng dụng đã chọn**. Overload không có `dir` chọn vị trí temp mặc định, có thể nằm trên volume khác. Atomic move qua các volume không được giả định hỗ trợ.

**Lưu ý về tên target:** ví dụ tạo target mới hoàn toàn. Nếu tác nhân khác có thể tạo tên `published.txt` trước lúc move, hành vi với `ATOMIC_MOVE`/target đã tồn tại là implementation-specific. Do đó một quy trình yêu cầu **không ghi đè** trong môi trường đồng thời cần chiến lược quản lý tên/locking/quyền khác; một `Files.notExists(target)` trước move **không tự tạo ra atomic check-and-create**.

### 8.3. Dữ liệu đã ghi đầy đủ nhưng có bền vững sau mất điện không?

Bước ghi đã hoàn tất và stream đã đóng là điều kiện hợp lý để publish, nhưng **atomic visibility** và **crash durability** là hai tính chất khác nhau.

- Atomic rename thường kiểm soát cách directory entry chuyển từ trạng thái trước sang sau trong khi hệ thống đang chạy.
- Nếu có mất điện, nội dung file và metadata directory entry có thể chưa được lưu bền xuống thiết bị theo mọi cấu hình.
- Khi cần độ bền cấp hệ thống, cần nghiên cứu `FileChannel.force(...)`/`FileDescriptor.sync()` cùng chính sách flush metadata thư mục và bảo đảm thực tế của OS/filesystem. Java không cung cấp một câu lệnh portable “atomic move + durable file + durable directory” cho mọi provider.

**Kết luận:** Đừng trình bày `ATOMIC_MOVE` như sự thay thế cho durable storage, transaction log, backup hoặc yêu cầu về thứ tự commit trong database.

## 9. `REPLACE_EXISTING` khác `ATOMIC_MOVE` như thế nào?

Hai option giải quyết **hai câu hỏi khác nhau**:

- **`REPLACE_EXISTING`:** khi dùng theo non-atomic move, cho phép thay thế file đích đang tồn tại (với giới hạn như thư mục không rỗng).
- **`ATOMIC_MOVE`:** yêu cầu **động tác move** được provider thực hiện nguyên tử.

Điểm quan trọng nhất trong Javadoc `Files.move`: **khi có `ATOMIC_MOVE`, mọi option khác bị bỏ qua**. Nếu target đã tồn tại, việc provider thay thế target hay ném IOException là **implementation-specific**.

Vì vậy đoạn này **không phải một bảo đảm portable** rằng phép thay thế vừa nguyên tử vừa luôn ghi đè:

```java
Files.move(
    source,
    target,
    StandardCopyOption.ATOMIC_MOVE,
    StandardCopyOption.REPLACE_EXISTING
);
```

Đây là snippet minh họa tình huống phải cảnh giác. Không thể diễn giải như “Java thực hiện atomic replace nếu đích tồn tại nhờ REPLACE_EXISTING”. Provider có thể thay thế hoặc từ chối theo hợp đồng `ATOMIC_MOVE`.

### 9.1. Nếu target đã tồn tại và nghiệp vụ muốn thay thế

Một ứng dụng publish cấu hình có thể cần **đổi từ nội dung cũ sang nội dung mới** mà reader không thấy file dở dang. Trên file store/provider đã được kiểm thử và tài liệu hóa khả năng atomic replacement, một giải pháp dùng staging + atomic rename có thể phù hợp.

Nhưng để có **thiết kế đa nền tảng**, cần nêu rõ:
- Sản phẩm có bắt buộc **atomic replacement** không?
- Filesystem đích có hỗ trợ replace khi `ATOMIC_MOVE` không?
- Có nhiều writer đồng thời không?
- Reader có giữ file handle mở không?
- Có cần giữ bản backup/version/rollback không?
- Những thao tác metadata và durability nào còn phải xử lý?

Nếu không kiểm soát được các điều kiện này, không hứa rằng thêm `REPLACE_EXISTING` cùng `ATOMIC_MOVE` sẽ giải quyết mọi vấn đề.

### 9.2. Khi chỉ cần replace nhưng không yêu cầu nguyên tử

Ví dụ:

```java
Files.move(source, target, StandardCopyOption.REPLACE_EXISTING);
```

Đây là snippet với `source`/`target` hợp lệ. Nó cho phép replace ở non-atomic move nhưng **không** cung cấp bảo đảm atomic visibility. Trước khi dùng trong production cần cân nhắc overwrite policy, backup và trạng thái khi I/O thất bại.

## 10. Chương trình đầy đủ: từ chối target đã có và dùng replace có chủ đích

Lưu thành `NonAtomicReplaceDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class NonAtomicReplaceDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("replace-demo-");
        Path source = dir.resolve("new.txt");
        Path target = dir.resolve("existing.txt");
        try {
            Files.writeString(source, "NEW", StandardCharsets.UTF_8);
            Files.writeString(target, "OLD", StandardCharsets.UTF_8);

            try {
                Files.move(source, target);
                throw new AssertionError("Existing target should be rejected");
            } catch (FileAlreadyExistsException expected) {
                System.out.println("withoutReplace=REJECTED");
            }
            System.out.println("sourceStillExists=" + Files.exists(source));
            System.out.println("targetBefore=" +
                    Files.readString(target, StandardCharsets.UTF_8));

            Files.move(source, target, StandardCopyOption.REPLACE_EXISTING);
            System.out.println("targetAfter=" +
                    Files.readString(target, StandardCharsets.UTF_8));
            System.out.println("sourceGone=" + Files.notExists(source));
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(target);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 NonAtomicReplaceDemo.java
java NonAtomicReplaceDemo
```

Stdout trên provider mặc định của máy kiểm thử:

```text
withoutReplace=REJECTED
sourceStillExists=true
targetBefore=OLD
targetAfter=NEW
sourceGone=true
```

Phân tích:

1. Source chứa `NEW`, target chứa `OLD`.
2. Lần move đầu **không có** `REPLACE_EXISTING`, nên provider mặc định từ chối với `FileAlreadyExistsException`, source/target vẫn giữ nội dung.
3. Lần move thứ hai có `REPLACE_EXISTING`, target trở thành `NEW`, source không còn tại tên ban đầu.
4. Code **không** sử dụng `ATOMIC_MOVE`, nên không thể từ stdout suy ra lần replace này là nguyên tử, dù implementation có thể đã dùng một phép rename ở tầng OS.

**Giới hạn portable:** `FileAlreadyExistsException` là một specific exception có thể phụ thuộc provider; các lỗi I/O khác vẫn có thể xuất hiện. Ví dụ này được kiểm thử trên file store cục bộ hỗ trợ hành vi đã quan sát, không phải lời hứa mọi filesystem đều in stdout giống hệt trong mọi tình huống.

## 11. Khi source/target khác FileStore hoặc provider

Một atomic move có thể không khả dụng khi source và target ở hai volume, mount hoặc provider khác nhau. Trong một số trường hợp non-atomic move được thực hiện dưới dạng **copy + delete**; đó là một cơ chế khác hẳn phép đổi tên directory entry.

Đặc điểm cần nhớ:

| Điều kiện | Tác động cần xét |
| --- | --- |
| Cùng thư mục/cùng file store | Tăng khả năng rename nguyên tử nhưng **không bảo đảm tuyệt đối** |
| Khác FileStore | Có thể cần copy; `ATOMIC_MOVE` có thể bị từ chối |
| Khác provider | Hành vi và mức hỗ trợ phụ thuộc provider, có thể bị từ chối |
| Network filesystem | Metadata, cache và semantics về rename/locking có thể khác local filesystem |
| Filesystem có quyền truy cập đặc biệt | Quyền, share modes, file đang mở có thể làm move thất bại |

### 11.1. `Files.getFileStore` có giúp dự đoán hỗ trợ không?

`Files.getFileStore(path)` lấy thông tin file store cho một path thực. Nó có thể giúp chẩn đoán hai đường dẫn thuộc khu vực lưu trữ nào, nhưng **không phải API đảm bảo rằng ATOMIC_MOVE sẽ thành công**. Hai path cùng file store vẫn có thể gặp giới hạn khác.

Đặc biệt, nếu target chưa tồn tại, thường nên xem thư mục cha tồn tại của target, không gọi `getFileStore` trực tiếp trên tên file chưa có rồi kỳ vọng nó hoạt động trên mọi provider.

### 11.2. Chiến lược khi cần publish qua file stores

Nếu source nằm trên volume A còn public target nằm trên volume B, một phương án thiết kế là:

1. Copy nội dung tới **staging riêng trên volume B** (không phải tên công khai).
2. Ghi xong, verify dữ liệu cần thiết và đóng tất cả stream.
3. Di chuyển **staging của volume B** tới tên public target bằng `ATOMIC_MOVE` nếu được hỗ trợ ở volume B.
4. Chỉ sau khi thành công mới cập nhật trạng thái ứng dụng và dọn nguồn ở A theo hợp đồng.

Phương án này **không phải một atomic move xuyên hai file stores**. Copy là bước riêng, có thể thất bại, và move cuối vẫn có thể unsupported. Cần cleanup/retry/verification của riêng nó.

## 12. Lỗi trong non-atomic move và khả năng phục hồi

Theo Javadoc `Files.move`, khi move **không nguyên tử** và phát sinh IOException, trạng thái file **không được xác định**. Có thể:
- Source và target đều còn tồn tại.
- Target tồn tại nhưng chưa hoàn chỉnh.
- Một số file attributes chưa được sao chép.
- Trạng thái khác tùy provider và thời điểm lỗi.

Vì vậy nếu policy đã cho phép non-atomic fallback, không nên viết:

```java
try {
    Files.move(source, target);
} catch (IOException ignored) {
    Files.deleteIfExists(source); // Nguy hiểm: chưa biết trạng thái.
}
```

Đây là **snippet cố ý minh họa cách xử lý sai**, không chạy trong production. Nếu fallback thất bại, xóa source ngay có thể làm mất bản dữ liệu còn lành lặn. Cần xác minh trạng thái source/target, kiểm tra checksum/kích thước nếu có, thiết kế staging/recovery và báo lỗi đủ để xử lý.

### 12.1. Phục hồi sau `AtomicMoveNotSupportedException`

Ngoại lệ này thông báo rằng **yêu cầu atomic move không được đáp ứng**. Nó không phải lệnh “hãy thử cùng thao tác liên tục với backoff”. Nếu giới hạn là khác FileStore hoặc thiếu capability của provider, chờ rồi retry vô điều kiện có thể không thay đổi điều gì.

Các hướng xử lý:
- Dừng và báo rằng môi trường không hỗ trợ yêu cầu.
- Chọn staging trong thư mục/file store thích hợp rồi thử lại với một **kế hoạch khác**.
- Cho phép fallback nếu đặc tả chức năng chấp nhận mất atomicity.
- Ghi log thông tin chẩn đoán có kiểm soát, giữ hoặc dọn staging theo chính sách.
- Xác minh kết quả cuối khi có bất kỳ thao tác không nguyên tử nào xảy ra.

### 12.2. Có cần retry với mọi IOException không?

Không. Một lỗi transient có thể có chính sách retry, nhưng phải kiểm tra idempotence, destination state, file đang mở, quyền và điều kiện cạnh tranh. Những lệnh ghi hoặc move lặp không kiểm soát có thể ghi đè phiên bản mới hơn. Hãy thiết kế retry như một workflow có trạng thái, không chỉ thêm vòng `while(true)`.

## 13. Atomic move không đồng nghĩa nhiều tài nguyên cùng thay đổi

Nếu ứng dụng cần cập nhật:
- `config.json`
- `users.json`
- `index.json`

thì ba lần `Files.move(..., ATOMIC_MOVE)` là **ba thao tác nguyên tử riêng**, không tạo thành một transaction cho cả ba file. Reader có thể thấy hai file ở phiên bản mới và một file ở phiên bản cũ nếu đọc giữa các lần move.

Muốn công bố một phiên bản logic gồm nhiều file, các hướng thường cân nhắc:
- Tạo một thư mục phiên bản bất biến rồi công bố một **manifest hoặc con trỏ phiên bản** bằng bước cập nhật tên phù hợp.
- Có khóa/coordination với reader.
- Dùng database/transaction store khi ràng buộc nhất quán cần thiết.
- Gắn version ID vào manifest để reader xác nhận bộ dữ liệu nhất quán.

Bước công bố con trỏ vẫn có các giới hạn riêng về atomicity provider, replacement behavior và durability. Không tự suy ra “manifest atomic” tức mọi dữ liệu phía sau đã durable.

## 14. Những bẫy liên quan đến thư mục, symlink và file đang mở

### 14.1. Move một thư mục

`Files.move` có thể di chuyển/đổi tên một directory nếu implementation có thể làm điều đó phù hợp. Nếu move một directory có nhiều entries mà thao tác đòi hỏi thực sự di chuyển tất cả entries riêng lẻ, provider có thể báo IOException. **Đừng mặc định atomic move của mọi cây thư mục qua nhiều file stores là được hỗ trợ.**

Nếu mục tiêu là chuyển cả file tree qua những nơi lưu trữ khác nhau, có thể cần `Files.walkFileTree` với copy/delete, nhưng đây là một workflow khác, không còn là **một atomic move của toàn bộ tree**.

### 14.2. Move symbolic link

Theo hợp đồng `Files.move`, nếu **source là symbolic link**, thao tác move di chuyển **chính link**, không phải nội dung file mà link trỏ tới. Điều này rất quan trọng khi input có thể do người dùng kiểm soát.

Một `ATOMIC_MOVE` thành công không phải kiểm tra rằng đường dẫn thuộc thư mục cho phép. Với ứng dụng nhạy cảm về bảo mật, phải kiểm tra root/path ownership, symlink policy và quyền filesystem riêng; atomicity và authorization là hai vấn đề tách biệt.

### 14.3. File đã được tiến trình khác mở

Trên một số hệ điều hành và provider, move một file đang mở có thể thành công theo semantics của OS; trên hệ thống khác, việc đang sử dụng có thể khiến move bị từ chối. Đừng giả định luôn thành công khi cùng volume hoặc luôn thất bại khi file có reader đang mở.

Để giảm biến số trong các ví dụ, hãy **đóng stream/writer trước khi move**, rồi mới mở target đọc để kiểm chứng. Nếu ứng dụng phải hot-swap file mà nhiều reader đang dùng, cần kiểm thử trên các OS/provider được sản phẩm hỗ trợ.

### 14.4. Mất metadata và thuộc tính

`Files.move` có thể sao chép thời gian sửa cuối nếu hai file stores hỗ trợ; provider có thể cố sao chép thuộc tính khác nhưng không bắt buộc fail nếu không thực hiện được. Đừng mặc định quyền truy cập, owner, ACL, extended attributes hay timestamp precision luôn giữ nguyên qua move giữa providers.

Kiểm tra rõ metadata quan trọng sau khi chuyển trong workflow phù hợp, và tránh tự dùng `COPY_ATTRIBUTES` để “ép” `ATOMIC_MOVE` vừa di chuyển nguyên tử vừa sao chép tất cả metadata: theo Javadoc, khi `ATOMIC_MOVE` được chỉ định, **option khác bị bỏ qua**.

## 15. Bảo mật và quyền ghi: bước cần thiết bên ngoài tính nguyên tử

Nếu tên source/target do người dùng gửi vào, chỉ chọn `ATOMIC_MOVE` **không khiến đường dẫn an toàn**. Ứng dụng phải xác định thư mục được phép, kiểm tra `Path` dưới root và chính sách symlink/permission; nếu có attacker có quyền thay thư mục giữa check và move, còn có rủi ro TOCTOU.

Một số nguyên tắc:
- Root lưu trữ phải đến từ cấu hình đáng tin.
- Không cho caller tự chỉ định full path ngoài vùng được phép nếu ứng dụng chỉ cần tên file tương đối.
- File staging và thư mục chứa nó nên thuộc quyền quản lý của ứng dụng, có permissions phù hợp.
- Tên public target không nên cho phép ghi đè tài liệu người dùng khác chỉ vì có `REPLACE_EXISTING`.
- Không trả full server path/stack trace thô cho client.
- Với nhiều tenant, kiểm tra quyền tài liệu/tenant riêng, không chỉ kiểm tra path prefix.
- Nếu yêu cầu race-resistant path traversal, cân nhắc các directory-handle-relative APIs và giới hạn provider, không giả định `normalize()` đã kiểm soát symlink.

**Giới hạn bài học:** Phân tích sâu path containment và symlink authorization là một chuyên đề riêng. Trong phạm vi này, điều quan trọng là **atomic move không phải một biện pháp thay thế cho quyền truy cập và validation đường dẫn**.

## 16. Định nghĩa trạng thái nghiệp vụ cho kết quả di chuyển

Một số hệ thống cần phân biệt tối thiểu:

| Trạng thái | Khi nào xuất hiện | Điều nên báo |
| --- | --- | --- |
| `ATOMIC_OK` | Move với `ATOMIC_MOVE` trả bình thường | Bước move đã được provider thực hiện nguyên tử theo hợp đồng |
| `ATOMIC_UNSUPPORTED` | Bắt `AtomicMoveNotSupportedException` và không fallback | Chưa có công bố nguyên tử; cần xử lý môi trường/chính sách |
| `NON_ATOMIC_OK` | Fallback được cho phép và move không có `ATOMIC_MOVE` trả bình thường | Move thành công nhưng không có bảo đảm atomicity |
| `FAILED_IO` | Một IOException khác hoặc fallback cũng thất bại | Không báo thành công; điều tra source/target state |
| `REJECTED_POLICY` | Input/operation vượt quyền, thiếu điều kiện theo hợp đồng | Từ chối trước khi tác động tới file |
| `UNKNOWN_OUTCOME` | Bị gián đoạn/không xác định trạng thái sau non-atomic error | Cần reconciliation trước retry |

Tên trạng thái chỉ là **gợi ý thiết kế ứng dụng**, không phải enum có sẵn của JDK. Nên thiết kế API nội bộ báo rõ kết quả hay dùng exception hợp lý thay vì biến mọi trường hợp thành một boolean “đã move xong”.

### 16.1. Có nên trả boolean như ví dụ PolicyDemo?

Trong `AtomicMovePolicyDemo`, boolean được dùng để tối giản test: `true` đại diện đường atomic, `false` đại diện đường fallback. Trong hệ thống thật, một `enum MoveMode { ATOMIC, NON_ATOMIC }` hoặc kiểu kết quả chứa target, mode và details thường diễn đạt rõ hơn.

Nhưng **không** được trả trạng thái `ATOMIC` khi code chỉ thử `Files.move(source, target)` và giả định provider đã dùng rename. Nếu không yêu cầu `ATOMIC_MOVE` thì code không có cam kết nguyên tử từ API.

## 17. Thiết kế kiểm thử đáng tin

Cần ít nhất **hai lớp kiểm thử**.

### 17.1. Unit test nhánh xử lý exception

Dùng test double như `simulatedUnsupported` để ép nhánh unsupported được thực thi. Xác nhận:
- Fail-closed ném lại exception và không gọi non-atomic move.
- Fallback được bật thì chuyển sang bước không atomic và báo đúng mức bảo đảm.
- Lỗi IOException khác không kích hoạt fallback.
- Không có thao tác ghi đè trái policy.
- Cleanup staging không xóa nhầm bản cũ.

Đây là test deterministic, không phụ thuộc filesystem hỗ trợ ATOMIC_MOVE trên máy đang chạy.

### 17.2. Integration test khả năng provider thật

Trên từng OS/file store thuộc môi trường triển khai:
- Tạo source và target trong **cùng thư mục** thử nghiệm.
- Gọi `Files.move(..., ATOMIC_MOVE)` và ghi nhận `SUPPORTED` hoặc `UNSUPPORTED`.
- Nếu thiết kế cần **atomic replacement** của file đã tồn tại, kiểm tra riêng với provider mục tiêu và chính sách overwrite thật.
- Kiểm tra trường hợp target không tồn tại, target đã tồn tại, source không tồn tại và quyền truy cập.
- Với cross-store, ghi nhận lỗi thực mà provider trả về; không giả định mọi filesystem đều ném cùng một subclass trong mọi tình huống.
- Kiểm tra startup/cleanup khi file staging còn lại từ lần chạy trước.

**Không dùng một bài test in chữ `SUPPORTED` trên laptop như bằng chứng** cho mọi file store mạng hoặc cluster production.

### 17.3. Kiểm tra reader không thấy nội dung dở dang

Nếu cần đánh giá atomic publish trong môi trường thực, có thể thiết kế integration test với reader và writer điều phối bằng concurrency primitives, cho reader mở target nhiều lần trong quá trình update. Tuy nhiên test **không thấy lỗi** không phải chứng minh toán học rằng mọi race đã được loại bỏ. Dựa vào hợp đồng filesystem và API, kết hợp test như một lớp kiểm chứng thực tế.

Đặc biệt, stdout một lần đọc target sau khi move thành công **không tự chứng minh** reader đồng thời không thấy dữ liệu trung gian. Chương trình `AtomicMoveBasicDemo` chỉ chứng minh nhánh call thành công và nội dung sau move, còn bảo đảm atomic thuộc hợp đồng `ATOMIC_MOVE` khi provider thực thi được.

## 18. Lỗi thường gặp và cách tránh

| Sai lầm | Hậu quả | Hướng đúng |
| --- | --- | --- |
| Dùng `Files.move(source,target)` rồi gọi là atomic | Không có yêu cầu/bảo đảm atomic | Thêm `ATOMIC_MOVE` và xử lý unsupported |
| Bắt `IOException` rồi luôn fallback | Che lỗi quyền, I/O và sai chính sách | Chỉ bắt `AtomicMoveNotSupportedException` khi phù hợp |
| Fallback dù ứng dụng đòi atomic publish | Reader có thể thấy nội dung chưa hoàn chỉnh | Fail-closed |
| Kết hợp `ATOMIC_MOVE` + `REPLACE_EXISTING` và hứa luôn overwrite | Option khác bị bỏ qua; hành vi target tồn tại phụ thuộc implementation | Kiểm thử/công bố chính sách provider |
| Kiểm tra `Files.exists(target)` trước atomic move rồi tin không thể overwrite | Race giữa check và move | Quản lý tên/quyền/lock phù hợp |
| Tạo staging ở temp mặc định rồi publish sang volume khác | Cross-store atomic thường không hỗ trợ | Tạo staging tại file store đích |
| Cho rằng cùng FileStore luôn hỗ trợ atomic | Provider còn có giới hạn khác | Kiểm tra hoạt động và xử lý ngoại lệ |
| Dùng `Files.move(..., REPLACE_EXISTING)` cho publish nguyên tử | Replace không bảo đảm atomic | Yêu cầu `ATOMIC_MOVE` nếu thật sự cần |
| Bỏ qua `IOException` của fallback và báo thành công | Có thể target dở dang hoặc source chưa xóa | Báo lỗi và reconciliation |
| Xóa source ngay sau một non-atomic move lỗi | Có thể mất bản dữ liệu còn đầy đủ | Kiểm tra và khôi phục theo workflow |
| Dùng `ATOMIC_MOVE` như fsync/durable storage | Dữ liệu/metadata có thể chưa bền sau crash | Thiết kế flush/durability riêng |
| Thay nhiều file bằng nhiều atomic moves rồi gọi transaction | Reader có thể thấy phiên bản trộn | Manifest/version coordination hoặc DB transaction |
| Giả định move symlink là move file đích của link | Files.move di chuyển link itself | Theo hợp đồng link và quyền |
| Cho rằng mọi directory tree move được nguyên tử | Provider có thể phải move entries riêng | Xem giới hạn directory/FileStore |
| Mở stream chưa đóng rồi move | Hành vi OS/provider có thể khác nhau | Đóng stream trước move nếu có thể |
| Dùng input path của client mà không validate | Nguy cơ di chuyển file ngoài phạm vi | Containment + authorization + permissions |
| Biên dịch `Files.writeString` với Java 7 | Method xuất hiện từ Java 11 | JDK17+ hoặc dùng `Files.write` của Java7 |
| Chỉ test trường hợp ATOMIC_MOVE thành công | Không có coverage nhánh unsupported | Test double và integration test |
| Tự retry vĩnh viễn khi unsupported | Giới hạn provider có thể cố hữu | Thay kế hoạch hoặc fail rõ |
| Log full path/exception ra client | Có thể lộ cấu trúc máy | Tách internal diagnostics và public response |

## 19. Những vấn đề hay nhầm về Java version

`Files.move`, `StandardCopyOption.ATOMIC_MOVE`, `AtomicMoveNotSupportedException`, `FileSystemException`, `Files.createTempFile` và `try-with-resources` đều là **API/cú pháp từ Java 7**, vẫn dùng tốt trong Java hiện nay.

Các ví dụ học trong bài chọn **JDK 17+** để dùng `Files.writeString`, `Files.readString` (được bổ sung ở **Java 11**) cho phần tạo/đọc nội dung tệp ngắn gọn. Nếu dự án vẫn cần build source/target Java 7, có thể thay chúng bằng `Files.write(path, bytes)` và `new String(Files.readAllBytes(path), StandardCharsets.UTF_8)` cùng quy tắc xử lý tài nguyên phù hợp; đây là lựa chọn tương thích, **không phải lời khuyên quay về API lỗi thời**.

Ví dụ snippet tương đương khi cần API có từ Java 7:

```java
Files.write(path, "READY".getBytes(StandardCharsets.UTF_8));
String content = new String(
        Files.readAllBytes(path),
        StandardCharsets.UTF_8
);
```

Đây là snippet với `Path path` và các import đã có. Với file lớn, nên dùng stream thay vì đọc toàn bộ vào RAM. Chủ đề atomic move **không phụ thuộc** vào việc bạn dùng API nào để ghi nội dung staging.

## 20. Bài tập với lời giải định hướng

**Câu 1.** Khi nào `Files.move(source,target)` được coi là có cam kết atomic?  
**Đáp án:** Khi dùng `StandardCopyOption.ATOMIC_MOVE` và method trả bình thường theo hợp đồng của provider. Lời gọi không option không được tự nâng thành bảo đảm atomic.

**Câu 2.** `AtomicMoveNotSupportedException` là checked hay unchecked?  
**Đáp án:** Checked, vì là subclass của `IOException`. Caller cần bắt hoặc khai báo.

**Câu 3.** Source nằm ở volume A, target ở volume B. Có thể mặc định ATOMIC_MOVE thành công không?  
**Đáp án:** Không. Provider có thể cần copy dữ liệu giữa file stores, không làm được như một atomic move và ném `AtomicMoveNotSupportedException`.

**Câu 4.** Nếu atomic move không hỗ trợ nhưng hợp đồng yêu cầu reader chỉ thấy file hoàn chỉnh, có nên fallback tự động không?  
**Đáp án:** Không. Dừng/khôi phục hoặc xây lại chiến lược staging trên file store đích; không tự hạ mức bảo đảm.

**Câu 5.** Vì sao catch `IOException` rồi gọi `Files.move` lại ngay có thể nguy hiểm?  
**Đáp án:** IOException có thể là lỗi không có quyền, storage, source missing... Không phải mọi lỗi đều là atomic unsupported; retry/fallback sai có thể làm trạng thái khó kiểm soát.

**Câu 6.** Thêm `REPLACE_EXISTING` vào `ATOMIC_MOVE` có đảm bảo target đã có sẽ luôn bị thay thế không?  
**Đáp án:** Không. Khi có ATOMIC_MOVE, các option khác bị bỏ qua; target tồn tại dẫn đến replace hay IOException phụ thuộc implementation.

**Câu 7.** `Files.move(source,target,REPLACE_EXISTING)` có cam kết atomic không?  
**Đáp án:** Không. Nó yêu cầu replace khi được hỗ trợ, nhưng không yêu cầu atomic filesystem operation.

**Câu 8.** Vì sao tạo staging trong cùng thư mục đích thường hữu ích?  
**Đáp án:** Giảm nguy cơ phải copy giữa file stores, tăng cơ hội thực hiện atomic rename, nhưng không phải bảo đảm mọi provider hỗ trợ.

**Câu 9.** Sau atomic move, file có chắc bền vững qua mất điện không?  
**Đáp án:** Không thể khẳng định chỉ dựa vào `ATOMIC_MOVE`. Crash durability/flush của file và metadata cần thiết kế riêng.

**Câu 10.** Có thể dùng ba atomic moves để cập nhật ba file rồi gọi đó là transaction không?  
**Đáp án:** Không. Mỗi move nguyên tử riêng; cần coordination/versioning nếu yêu cầu bộ dữ liệu nhất quán.

**Câu 11.** Nếu fallback không nguyên tử bị IOException, trạng thái source và target có luôn được bảo toàn không?  
**Đáp án:** Không. Javadoc nói trạng thái khi non-atomic move lỗi có thể không xác định; cần reconciliation.

**Câu 12.** `Files.move` với source là symbolic link di chuyển link hay file đích?  
**Đáp án:** Di chuyển chính symbolic link theo hợp đồng, không phải file mà link trỏ tới.

**Câu 13.** Có cần thử nhánh unsupported bằng cách tìm một ổ cứng khác cho mọi unit test không?  
**Đáp án:** Không. Dùng test double ném `AtomicMoveNotSupportedException` để test policy; integration test có thể kiểm tra provider thật riêng.

**Câu 14.** Vì sao `Files.exists(target) == false` trước move không đảm bảo target vẫn chưa tồn tại lúc move?  
**Đáp án:** Có race giữa check và use; một tác nhân khác có thể tạo tên đó.

**Câu 15.** Một atomic move thành công có xác nhận ứng dụng đủ quyền truy cập tài liệu không?  
**Đáp án:** Không. Quyền theo người dùng/tài liệu và containment phải kiểm tra riêng.

### Thực hành A — Fail-closed

Chạy `AtomicMovePolicyDemo`, giữ `allowFallback=false` và xác nhận source vẫn còn, target chưa có khi mock ném unsupported. Đổi sang true và xác minh luồng dữ liệu khác biệt.

### Thực hành B — Lỗi không phải unsupported

Sửa test double để ném `NoSuchFileException` hoặc `AccessDeniedException`. Kiểm tra chúng **không** bị handler unsupported “nuốt” rồi fallback.

### Thực hành C — Staging cùng file store

Chạy `StagedAtomicPublishDemo`, sau đó sửa code tạo staging bằng overload `Files.createTempFile("x", ".tmp")` không truyền thư mục. So sánh vị trí thực của staging và target, lý giải vì sao chọn cùng thư mục đích đáng tin hơn. Không cần ép tạo trường hợp khác volume nếu máy không có điều kiện.

### Thực hành D — Target đã tồn tại

Chạy `NonAtomicReplaceDemo`, kiểm tra vì sao move không option bị từ chối, còn `REPLACE_EXISTING` thay thế thành công trên provider kiểm thử. **Đừng suy ra hành vi đó cho `ATOMIC_MOVE`**; đọc lại Javadoc để hiểu khác biệt.

### Thực hành E — Atomic capability

Chạy `AtomicMoveBasicDemo` trên filesystem cục bộ và trong môi trường thử nghiệm khác nếu có quyền. Ghi rõ `SUPPORTED`/`UNSUPPORTED` và loại file store; không cố tạo lỗi giả rồi gọi là kết quả integration test thực.

### Thực hành F — Cấu trúc trạng thái

Viết một enum `MoveOutcome { ATOMIC, NON_ATOMIC }` và thay boolean trong PolicyDemo thành enum. Giữ nguyên việc truyền thông tin khác biệt cho caller. Thiết kế đường lỗi ném IOException hoặc trả một kết quả có trạng thái thật.

### Thực hành G — Người đọc và người ghi

Thiết kế một thử nghiệm có writer ghi staging, đóng rồi publish và reader đọc tên public. Với provider hỗ trợ atomic rename, test không được khẳng định một file bị copy dở dang từ **bước move**. Phân biệt việc verify nội dung sau move với bảo đảm concurrency của provider.

### Thực hành H — Kiểm tra recovery

Giả lập fallback non-atomic thất bại bằng một test double và thiết kế quy trình kiểm tra sự tồn tại, kích thước, hash của source/target trước khi retry. Không xóa source khi chưa có đủ bằng chứng về dữ liệu đã được lưu an toàn.

## 21. Checklist trước khi đưa vào sản phẩm

1. **Có thực sự cần atomicity không?** Nếu không, `Files.move` với option phù hợp có thể đủ.
2. **Source và target ở file store/provider nào?** Staging có được tạo trong thư mục đích không?
3. **Target đã tồn tại chưa?** Nếu có, việc thay thế bằng `ATOMIC_MOVE` đã được xác minh trên provider mục tiêu chưa?
4. **Có fallback không?** Nếu có, sản phẩm có chấp nhận reader thấy trạng thái trung gian không?
5. **Bắt riêng `AtomicMoveNotSupportedException` chưa?** IOException khác có được truyền ra đúng hợp đồng không?
6. **Đã đóng file stream/writer trước khi move chưa?** Có handles/processes khác đang dùng file không?
7. **Có lưu kết quả atomic/non-atomic khác nhau không?** Có bỏ qua đường lỗi bất thường không?
8. **Có khả năng thay đổi target trong khi move không?** Có quyền, locking, tên staging và race policies thích hợp không?
9. **Có kiểm tra path containment, symlink và authorization không?** Atomicity không giải quyết chúng.
10. **Đã thiết kế cleanup và retry an toàn chưa?** Đặc biệt sau lỗi của non-atomic fallback.
11. **Có yêu cầu durability qua crash không?** Đã nghiên cứu file/directory flush tương ứng với OS/filesystem chưa?
12. **Có nhiều file cùng tạo một phiên bản logic không?** Đã có coordination/manifest/transaction layer chưa?
13. **Có test unit cho nhánh unsupported và test integration trên provider thật không?**
14. **Lệnh build đúng Java target chưa?** Ví dụ dùng Java 17+ cho `Files.readString/writeString`; atomic move core có từ Java 7.
15. **Thông báo lỗi có lộ file path hoặc dữ liệu nội bộ không?** Phân biệt log chẩn đoán và response công khai.

## 22. Tài liệu chính thức

- [Java SE 17 — Files.move](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#move(java.nio.file.Path,java.nio.file.Path,java.nio.file.CopyOption...)): định nghĩa move, `ATOMIC_MOVE`, behavior target tồn tại, lỗi, metadata và trạng thái khi non-atomic move thất bại.
- [Java SE 17 — StandardCopyOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html): các enum constant `ATOMIC_MOVE`, `REPLACE_EXISTING`, `COPY_ATTRIBUTES`.
- [Java SE 17 — AtomicMoveNotSupportedException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/AtomicMoveNotSupportedException.html): checked exception khi không thể move nguyên tử.
- [Java SE 17 — FileSystemException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystemException.html): `getFile`, `getOtherFile`, `getReason` phục vụ chẩn đoán.
- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `resolve`/`resolveSibling`/`toAbsolutePath` và cấu trúc đường dẫn.
- [Java SE 17 — FileStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileStore.html): thông tin kho lưu trữ bên dưới.
- [Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): `force` và các lưu ý về việc đẩy thay đổi xuống thiết bị lưu trữ.
- [Dev.java — Moving, Copying and Deleting Files](https://dev.java/learn/api/io/java-io/file-system/move-copy-delete/): ví dụ sử dụng API NIO.2 và ý nghĩa atomic operations.

**Ghi nhớ cốt lõi:** `Files.move(source, target, ATOMIC_MOVE)` chỉ thành công như một **atomic filesystem operation** khi provider hỗ trợ; nếu không, `AtomicMoveNotSupportedException` cho ứng dụng cơ hội **dừng an toàn** hoặc **fallback có chủ đích**. `ATOMIC_MOVE` không tự bảo đảm overwrite target hiện hữu, không đồng nghĩa durability hay transaction nhiều file, và không thay quyền truy cập. Tạo staging trên file store đích, đóng dữ liệu trước publish, bắt đúng ngoại lệ và thiết kế recovery theo mức bảo đảm mà ứng dụng thật sự cần.
