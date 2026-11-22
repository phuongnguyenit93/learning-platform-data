# Xử lý tệp đích đã tồn tại và thư mục không rỗng trong Java I/O

## 1. Bài toán thực tế

Khi tạo, sao chép, di chuyển hoặc xóa file bằng Java, hai tình huống rất thường gặp là:

1. **Đường dẫn đích đã tồn tại**: bạn muốn tạo **report.txt**, nhưng ở đó đã có file hay thư mục. Có được ghi đè không? Nên từ chối, đổi tên mới, ghi nối hay thay thế?
2. **Thư mục không rỗng**: bạn muốn xóa **reports/**, nhưng trong đó vẫn có file hoặc thư mục con. Một lời gọi xóa trực tiếp có xóa toàn bộ cây không? Làm sao tránh xóa nhầm?

Câu trả lời phải xuất phát từ **hợp đồng nghiệp vụ**. Java có các API **java.io.File** truyền thống và **java.nio.file.Files** hiện đại, nhưng không API nào tự biết bạn có quyền phá hủy dữ liệu cũ hay không.

> Quy tắc an toàn: **mặc định từ chối ghi đè hoặc xóa đệ quy khi chưa có yêu cầu rõ ràng**. Chỉ dùng tùy chọn thay thế hoặc dọn cây khi đã xác định phạm vi, quyền, phương án xử lý lỗi và rủi ro thay đổi đồng thời.

Bài này tập trung vào **tệp đích đã có** khi tạo/copy/move/ghi nội dung và **thư mục không rỗng** khi xóa. Mã ví dụ dùng Java 17+.

## 2. Phân biệt “đường dẫn tồn tại” với “đúng loại tài nguyên”

Một đường dẫn **Path** có thể đại diện cho:

- File thông thường.
- Thư mục, có thể rỗng hoặc không rỗng.
- Symbolic link, nếu filesystem hỗ trợ.
- Tài nguyên đặc biệt hoặc một đường dẫn chưa tồn tại.

Ví dụ:

~~~java
Path destination = Path.of("data", "report.txt");

boolean exists = Files.exists(destination);
boolean regular = Files.isRegularFile(destination);
boolean directory = Files.isDirectory(destination);
~~~

Đây là **mảnh code minh họa**; cần import **java.nio.file.Files** và **java.nio.file.Path**.

**Files.exists(path)** không đủ để quyết định “an toàn ghi đè”: một đường dẫn có thể là thư mục chứ không phải file thường; symlink có thể trỏ đến vị trí khác; quyền truy cập có thể khiến phép kiểm tra không kết luận chắc chắn. Với **Files.exists** hoặc **Files.notExists**, hai kết quả đều có thể false khi trạng thái không xác định do quyền hoặc lỗi I/O.

Quan trọng hơn, **kiểm tra rồi thao tác** không phải một giao dịch nguyên tử:

~~~text
Tiến trình A: Files.exists(target) → false
Tiến trình B: tạo target
Tiến trình A: bắt đầu ghi target → có nguy cơ đụng dữ liệu vừa tạo
~~~

Đây là race condition kiểu **TOCTOU** (*time of check to time of use*). Nếu yêu cầu chỉ tạo file mới khi tên chưa tồn tại, dùng tùy chọn **CREATE_NEW** của thao tác ghi hoặc **Files.createFile**, thay vì tin vào một kết quả exists đã kiểm tra trước.

## 3. Các chính sách xử lý file đích đã tồn tại

| Chính sách | Khi nào chọn | API phù hợp |
| --- | --- | --- |
| **Từ chối** nếu đích đã tồn tại | Tránh làm mất file người dùng; tạo báo cáo duy nhất | **Files.createFile**, **CREATE_NEW**, hoặc **Files.copy** mặc định |
| **Thay thế** file đích cũ | Đã có quyền cập nhật và chính sách backup/khôi phục | **Files.copy(..., REPLACE_EXISTING)**, **Files.move(..., REPLACE_EXISTING)**, hoặc ghi truncate |
| **Ghi tiếp (append)** | Nhật ký/những bản ghi có thể nối, không thay dữ liệu cũ | **Files.writeString(..., CREATE, APPEND)** hay **Files.newOutputStream(..., APPEND)** |
| **Đổi sang tên khác** | Lưu cả phiên bản cũ và mới | Sinh tên đích khác; **CREATE_NEW** để chốt quyền tạo |
| **Thay thế qua file tạm** | Giảm nguy cơ bản cũ bị hỏng do thao tác ghi dở | Ghi tạm + **Files.move** theo option và filesystem phù hợp |

Đừng đánh đồng **ghi đè** với **append**. Ghi đè thường loại bỏ nội dung cũ hoặc thay file; append đặt dữ liệu mới phía sau dữ liệu hiện có. Với file có định dạng hoàn chỉnh (PDF, ZIP, ảnh), append tùy tiện thường tạo file sai định dạng.

## 4. Tạo file mới: Files.createFile và CREATE_NEW

### 4.1. Files.createFile không âm thầm ghi đè

~~~java
Path path = Path.of("output.txt");
Files.createFile(path);
~~~

Đây là **mảnh code** cần import Files/Path và xử lý **IOException**.

**Files.createFile(path)** tạo file mới rỗng nếu đường dẫn chưa tồn tại. Nếu một mục filesystem đã chiếm tên đó, thông thường API ném **FileAlreadyExistsException** (một lớp con của **IOException**) thay vì ghi đè dữ liệu cũ. Hoạt động kiểm tra-chưa-tồn-tại và tạo file được yêu cầu thực hiện nguyên tử trong phạm vi hợp đồng API/provider.

**Không nên dùng** mẫu kiểm tra rồi tạo:

~~~java
if (!Files.exists(path)) {
    Files.createFile(path);
}
~~~

Kết quả **exists()** có thể cũ khi lời gọi tạo file thực sự chạy. Gọi trực tiếp **createFile** và xử lý **FileAlreadyExistsException** rõ ràng hơn.

### 4.2. Muốn mở file để ghi, dùng CREATE_NEW

Nếu mục tiêu là **tạo file và ghi nội dung ngay**, có thể dùng:

~~~java
Files.writeString(
        path,
        "Nội dung mới",
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE);
~~~

Đây là **mảnh code**, cần import **StandardCharsets** và **StandardOpenOption**. Nếu tên đã tồn tại, thao tác sẽ không mở theo chính sách ghi đè. Cách này tránh khoảng trống giữa “tạo file rỗng” và “mở file để ghi”.

Lưu ý: **CREATE_NEW không biến việc ghi hàng nghìn byte thành giao dịch nguyên tử**. Nếu hết dung lượng đĩa hoặc I/O lỗi giữa chừng, file mới có thể đã được tạo nhưng nội dung chưa đủ. Cần xử lý/đánh dấu file dở dang theo quy tắc ứng dụng.

### 4.3. So sánh với java.io.File.createNewFile

~~~java
File legacy = new File("output.txt");
boolean created = legacy.createNewFile();
~~~

Đây là **mảnh code** cần import **java.io.File** và xử lý IOException. **created == true** nghĩa là lần gọi tạo được file rỗng; **false** nghĩa là tên đó đã tồn tại. Khác với Files.createFile, kết quả false không có exception mô tả riêng trường hợp đã tồn tại.

**File.createNewFile()** cũng có hợp đồng thao tác kiểm tra-tạo mới nguyên tử, nhưng nếu cần ghi ngay với chính sách “không thay thế”, **CREATE_NEW** tích hợp trực tiếp vào thao tác mở/ghi thường diễn đạt ý định tốt hơn.

## 5. Files.copy: mặc định từ chối, REPLACE_EXISTING khi được phép

Chữ ký sử dụng thường gặp:

~~~java
Files.copy(source, target);
Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
~~~

Các mảnh code giả định **source**, **target** là Path và đã import **Files**, **StandardCopyOption**.

### 5.1. Không có REPLACE_EXISTING

Với file nguồn và file đích **khác nhau**, nếu **target đã tồn tại**, **Files.copy(source, target)** thông thường ném **FileAlreadyExistsException**. Đây là mặc định tốt khi không muốn phá hủy dữ liệu đích.

~~~text
source.txt = "NEW"
target.txt = "OLD"

Files.copy(source, target)
    → FileAlreadyExistsException
target.txt vẫn chứa "OLD" (trong trường hợp lỗi vì đã tồn tại)
~~~

### 5.2. Có REPLACE_EXISTING

Khi đã xác nhận muốn thay thế:

~~~java
Files.copy(
        source,
        target,
        StandardCopyOption.REPLACE_EXISTING);
~~~

API cố thay mục đích để bản sao dữ liệu nguồn xuất hiện ở **target**. Tuy nhiên:

- **Không bảo đảm thao tác copy là nguyên tử.** Nếu lỗi giữa chừng, trạng thái target có thể không còn nguyên vẹn.
- **Không mặc định giữ tất cả metadata** của nguồn. Muốn sao chép các thuộc tính được hỗ trợ, có thể xét **COPY_ATTRIBUTES**, nhưng không phải mọi attribute đều sao chép được.
- **Không sử dụng REPLACE_EXISTING như lệnh xóa mọi cây thư mục.** Nếu target là **thư mục không rỗng**, provider có thể không thể thay thế; **DirectoryNotEmptyException** hoặc IOException liên quan có thể xảy ra.
- Nếu **source là thư mục**, thao tác Files.copy trên directory **không có nghĩa là sao chép đệ quy toàn bộ nội dung con**. Cần thuật toán riêng nếu thực sự muốn copy cả cây.
- Trạng thái khác nhau của symlink, filesystem hoặc file đang mở có thể ảnh hưởng kết quả; không đoán dựa trên phần mở rộng tên file.

**Hậu điều kiện cần kiểm tra**: nếu việc copy hoàn thành, target phải đáp ứng yêu cầu nội dung và thuộc tính mà ứng dụng đã định. Với dữ liệu quan trọng, đối chiếu kích thước/hash hoặc dùng **Files.mismatch(source, target)** sau copy khi hai file còn ổn định.

## 6. Files.move: đích tồn tại và tính nguyên tử

Lệnh chuyển tên/vị trí:

~~~java
Files.move(source, target);
~~~

Theo quy tắc thông thường, **nếu target đã tồn tại**, move không có REPLACE_EXISTING sẽ thất bại (thường **FileAlreadyExistsException**); có ngoại lệ phụ thuộc provider và tình huống đường dẫn nguồn/đích trỏ cùng một file. Vì vậy đừng dựa vào hành vi ngoài hợp đồng đối với tài nguyên đặc biệt.

Nếu chính sách cho phép thay:

~~~java
Files.move(source, target, StandardCopyOption.REPLACE_EXISTING);
~~~

**Không nên coi REPLACE_EXISTING là bảo đảm ghi đè mọi dạng đích**. Ví dụ target là **thư mục không rỗng** có thể không thể được thay; file đang được sử dụng, filesystem khác nhau, quyền truy cập, hoặc hệ điều hành cũng có thể làm move thất bại.

### 6.1. REPLACE_EXISTING và ATOMIC_MOVE giải quyết hai mục tiêu khác nhau

- **REPLACE_EXISTING**: diễn đạt **mong muốn thay đối tượng đích hiện có** nếu provider và tình huống hỗ trợ.
- **ATOMIC_MOVE**: yêu cầu **di chuyển nguyên tử như một thao tác filesystem**, nếu provider hỗ trợ.

Ví dụ:

~~~java
Files.move(
        temporary,
        target,
        StandardCopyOption.ATOMIC_MOVE,
        StandardCopyOption.REPLACE_EXISTING);
~~~

Đây là **mảnh minh họa** (temporary và target là Path). Với **ATOMIC_MOVE**, hợp đồng API quy định các option khác có thể bị bỏ qua và **hành vi khi target đã tồn tại phụ thuộc triển khai**. Do đó **không suy ra** rằng ghép hai option là phép “thay thế nguyên tử” portable ở mọi provider.

Nếu không hỗ trợ atomic move, có thể nhận **AtomicMoveNotSupportedException**. Ứng dụng phải có **chính sách fallback**: từ chối cập nhật, chấp nhận move không atomic theo yêu cầu, hoặc chọn cơ chế lưu trữ khác. Không lặng lẽ bỏ option ATOMIC_MOVE trong quy trình bắt buộc nguyên tử.

### 6.2. Ghi ra file tạm rồi di chuyển

Để cập nhật file cấu hình quan trọng, chiến lược phổ biến:

1. Tạo **file tạm mới** trong thư mục chứa đích hoặc ít nhất cùng filesystem, bằng cách tạo duy nhất để không đè file khác.
2. Ghi đầy đủ nội dung và đóng tài nguyên; đồng bộ dữ liệu/metadata đến mức độ bền yêu cầu nếu ứng dụng cần.
3. Nếu có kiểm tra định dạng hoặc checksum, làm trước khi thay thế đích.
4. Thử move sang đích với chính sách atomic/replacement rõ ràng và xử lý trường hợp filesystem không hỗ trợ.
5. Nếu có lỗi, dọn file tạm do mình tạo nhưng **không xóa nhầm bản đích cũ**.

**Ghi file tạm không tự biến mọi quy trình thành giao dịch bền vững sau mất điện**. Cần xét FileChannel.force, đồng bộ thư mục và hợp đồng hệ thống file nếu ứng dụng có yêu cầu durability rất cao.

## 7. Files.writeString và Files.newOutputStream: vì sao file bị mất nội dung cũ?

Ví dụ:

~~~java
Files.writeString(path, "NEW");
~~~

**Files.writeString** mặc định dùng UTF-8 và, khi không truyền option, mở với chính sách tương đương **CREATE + TRUNCATE_EXISTING + WRITE**. Với file đã có, nội dung cũ bị cắt trước khi ghi nội dung mới. Đây là **ghi đè** có chủ đích của API, khác với Files.copy mặc định từ chối đích đã tồn tại.

Tương tự:

~~~java
try (OutputStream out = Files.newOutputStream(path)) {
    out.write(new byte[] {1, 2, 3});
}
~~~

Đây là **mảnh code**, cần import **java.io.OutputStream** và **java.nio.file.Files**; phải xử lý IOException. Với options mặc định của Files.newOutputStream, một file đã tồn tại thường bị truncate để ghi mới.

Muốn **ghi thêm** thay vì cắt:

~~~java
Files.writeString(
        path,
        "\nNEW",
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND);
~~~

Ví dụ cần import **StandardOpenOption**. Dấu xuống dòng **\n** do code chủ động chèn, không phải do APPEND tự thêm. Trên nhiều tiến trình cùng ghi, APPEND **không thay cho thiết kế đồng bộ/locking ở cấp bản ghi**.

**Tương phản cần nhớ:**

| Thao tác | Khi file đích đã tồn tại |
| --- | --- |
| **Files.createFile(path)** | Thường **ném FileAlreadyExistsException** |
| **Files.copy(source, target)** | Thường **ném FileAlreadyExistsException** |
| **Files.move(source, target)** | Thường báo lỗi, không mặc định thay thế |
| **Files.writeString(path, text)** | Mặc định **truncate rồi ghi lại** |
| **Files.newOutputStream(path)** | Mặc định **truncate để ghi mới** |
| **Files.writeString(..., CREATE_NEW, WRITE)** | Từ chối nếu tên đích đã có |
| **Files.writeString(..., CREATE, APPEND)** | Ghi thêm ở cuối |

Đừng kết luận “mọi phương thức Files đều mặc định không ghi đè” hoặc “mọi phương thức Files đều ghi đè”: **hợp đồng của từng phương thức khác nhau**.

## 8. Thư mục không rỗng: tại sao delete() thất bại?

Giả sử:

~~~text
reports/
├── 2026/
│   └── october.csv
└── notes.txt
~~~

**reports/** là thư mục không rỗng. Gọi:

~~~java
Files.delete(Path.of("reports"));
~~~

sẽ không tự xóa toàn bộ các file con. Trên filesystem thông thường, thao tác ném **DirectoryNotEmptyException** (một IOException); nhiều hệ thống khác có thể dùng IOException khác.

Tương tự, dùng API cũ:

~~~java
File directory = new File("reports");
boolean deleted = directory.delete();
~~~

**File.delete()** chỉ xóa được thư mục **rỗng** theo quy tắc thông thường và trả **false** nếu không thể xóa, không cho chẩn đoán chi tiết như Files.delete.

### 8.1. Files.delete và Files.deleteIfExists

| API | Nếu mục tiêu chưa tồn tại | Nếu mục tiêu là thư mục không rỗng |
| --- | --- | --- |
| **Files.delete(path)** | Thường ném **NoSuchFileException** | Ném **DirectoryNotEmptyException** hoặc IOException liên quan |
| **Files.deleteIfExists(path)** | Trả **false** | **Vẫn ném IOException**; không tự dọn cây |
| **new File(...).delete()** | Thường trả **false** | Thường trả **false**, ít thông tin hơn |

**deleteIfExists** chỉ bỏ qua **lỗi thiếu tên đích**, **không phải** “xóa nếu có bất kể trong đó có gì”. Với thư mục không rỗng, phương thức vẫn có thể ném lỗi.

### 8.2. Xóa thư mục rỗng

Nếu thực sự muốn xóa một thư mục đã biết phải rỗng:

~~~java
Files.delete(directoryPath);
~~~

Nếu thư mục có con, hãy **báo lỗi và yêu cầu quyết định rõ** trước khi chọn xóa nội dung. Không nên bí mật đổi từ xóa thư mục thành xóa đệ quy vì điều này có thể phá hủy dữ liệu người dùng ngoài dự kiến.

## 9. Nếu nghiệp vụ thật sự cần xóa toàn bộ cây thư mục

Xóa đệ quy là tác vụ **nguy hiểm**: người dùng có thể đưa sai đường dẫn; một symbolic link có thể dẫn tới tài nguyên ngoài phạm vi; tiến trình khác có thể tạo thêm file trong khi đang duyệt. **java.nio.file.Files** không có một hàm **deleteTree(path)** chung bảo đảm an toàn cho mọi trường hợp.

Nguyên tắc khi thực sự được phép:

1. Xác nhận đường dẫn gốc thuộc **phạm vi mà chương trình sở hữu**, không phải thư mục hệ thống hoặc dữ liệu người dùng ngoài chính sách.
2. Xác định rõ cách xử lý symbolic link; không tự động **follow** links đến cây khác.
3. Duyệt cây và xóa **file/con trước, thư mục cha sau**.
4. Xử lý **IOException**, phân quyền, file đang mở và trường hợp một mục xuất hiện/biến mất trong lúc duyệt.
5. Ghi nhận kết quả đã xóa đến đâu. Không coi xóa đệ quy là một transaction có thể rollback.
6. Với rủi ro bảo mật hoặc filesystem thay đổi đồng thời, cần thiết kế dựa trên directory handle/cơ chế thích hợp (ví dụ **SecureDirectoryStream** khi provider hỗ trợ), không chỉ tin vào phép nối đường dẫn.

Ví dụ chỉ cho **cây tạm do chính chương trình tạo**, không thay tên bằng đường dẫn do người dùng nhập:

~~~java
Path ownedTemp = Files.createTempDirectory("owned-tree-");
Path child = Files.createDirectories(ownedTemp.resolve("nested"));
Files.writeString(child.resolve("example.txt"), "example");

try (var paths = Files.walk(ownedTemp)) {
    for (Path entry :
            paths.sorted(java.util.Comparator.reverseOrder()).toList()) {
        Files.delete(entry);
    }
}
~~~

Đây là **mảnh code minh họa**, cần import **Files**, **Path** và xử lý IOException. **Files.walk** mặc định **không đi theo symbolic links** khi không truyền FOLLOW_LINKS. Sắp xếp đường dẫn đảo thứ tự thông thường giúp trong cây minh họa có đường dẫn con trước đường dẫn cha. Với chương trình xóa cây nói chung, **Files.walkFileTree** dùng FileVisitor, **visitFile** và **postVisitDirectory** sẽ biểu đạt rõ hơn việc duyệt theo thứ tự, hỗ trợ xử lý lỗi theo từng mục; không nên dùng một mẫu ngắn như trên làm công cụ xóa thư mục tùy ý.

Trong sản phẩm thực tế, nếu bất kỳ file nào không thể xóa, có thể cần dừng và báo trạng thái đã xóa một phần, thay vì bỏ lỗi rồi tiếp tục như thể không có rủi ro.

## 10. Ví dụ Java 17+ chạy độc lập: xử lý đích tồn tại và thư mục không rỗng

Chương trình sau tạo một **thư mục tạm riêng** cho mỗi lần chạy, không động đến file người dùng. Nó minh họa chính sách không ghi đè, ghi đè có chủ đích, di chuyển, CREATE_NEW, lỗi thư mục không rỗng và dọn theo thứ tự.

Lưu thành **ExistingTargetDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryNotEmptyException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;

public class ExistingTargetDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("target-demo-");
        Path source = root.resolve("source.txt");
        Path target = root.resolve("target.txt");
        Path exclusive = root.resolve("exclusive.txt");
        Path folder = root.resolve("folder");
        Path child = folder.resolve("keep.txt");

        try {
            Files.writeString(source, "NEW", StandardCharsets.UTF_8);
            Files.writeString(target, "OLD", StandardCharsets.UTF_8);

            // Copy mặc định từ chối file đích đã có.
            try {
                Files.copy(source, target);
            } catch (FileAlreadyExistsException ex) {
                System.out.println("copy-existing=blocked");
            }

            // REPLACE_EXISTING: được phép thay nội dung đích.
            Files.copy(source, target,
                    StandardCopyOption.REPLACE_EXISTING);
            System.out.println("copy-replaced=" +
                    Files.readString(target));

            // Move mặc định từ chối đích đã tồn tại.
            Files.writeString(source, "MOVE", StandardCharsets.UTF_8);
            try {
                Files.move(source, target);
            } catch (FileAlreadyExistsException ex) {
                System.out.println("move-existing=blocked");
            }

            // Chỉ thay khi hợp đồng cho phép.
            Files.move(source, target,
                    StandardCopyOption.REPLACE_EXISTING);
            System.out.println("move-replaced=" +
                    Files.readString(target));
            System.out.println("source-gone=" +
                    Files.notExists(source));

            // CREATE_NEW: cố tạo lại một tên đã có.
            Files.writeString(exclusive, "FIRST",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE);
            try {
                Files.writeString(exclusive, "SECOND",
                        StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE);
            } catch (FileAlreadyExistsException ex) {
                System.out.println("create-new-existing=blocked");
            }
            System.out.println("exclusive=" +
                    Files.readString(exclusive));

            // Thư mục không rỗng: xóa trực tiếp bị từ chối.
            Files.createDirectory(folder);
            Files.writeString(child, "KEEP", StandardCharsets.UTF_8);
            try {
                Files.delete(folder);
            } catch (DirectoryNotEmptyException ex) {
                System.out.println("nonempty-directory=blocked");
            }

            // Xóa con trước, xóa thư mục rỗng sau.
            Files.delete(child);
            Files.delete(folder);
            System.out.println("folder-gone=" +
                    Files.notExists(folder));
        } finally {
            // Chỉ dọn các đường dẫn do chính demo tạo.
            Files.deleteIfExists(child);
            Files.deleteIfExists(folder);
            Files.deleteIfExists(source);
            Files.deleteIfExists(target);
            Files.deleteIfExists(exclusive);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Chạy:

~~~bash
javac ExistingTargetDemo.java
java ExistingTargetDemo
~~~

Trên một filesystem cục bộ thông thường cho phép các thao tác thử nghiệm, stdout dự kiến:

~~~text
copy-existing=blocked
copy-replaced=NEW
move-existing=blocked
move-replaced=MOVE
source-gone=true
create-new-existing=blocked
exclusive=FIRST
nonempty-directory=blocked
folder-gone=true
~~~

**Lưu ý:** Một số provider có thể có quy tắc khác với hoạt động move và thông báo ngoại lệ; mô tả trên áp dụng cho filesystem cục bộ điển hình. Nếu provider không ném đúng **FileAlreadyExistsException** hoặc **DirectoryNotEmptyException** mà ném **IOException** khác, chương trình có thể dừng và báo lỗi thay vì in đủ các dòng. Demo không ép mọi filesystem phải cho cùng kết quả.

Giải thích:

- Lần **Files.copy(source,target)** không có REPLACE_EXISTING nên từ chối target đang chứa "OLD". Tên đích không bị ghi đè bởi bước copy thất bại kiểu đã tồn tại.
- **Files.copy(..., REPLACE_EXISTING)** thay target bằng dữ liệu "NEW".
- Sau đó source được ghi "MOVE"; move không có option bị từ chối vì target đang có. Move có REPLACE_EXISTING cập nhật target và làm source không còn ở đường dẫn cũ.
- **CREATE_NEW** không ghi đè "FIRST" bằng "SECOND" khi tên đích đã tồn tại.
- **Files.delete(folder)** với child bên trong bị từ chối; xóa child rồi folder thành công.

Cách viết **finally** cố dọn mọi đường dẫn tạm do demo sở hữu. Nếu hệ thống file lỗi trong quá trình cleanup, IOException có thể phát sinh; chương trình không nên khẳng định đã dọn sạch khi thực tế thất bại.

## 11. Cách xử lý lỗi: đừng chỉ dựa vào tên exception

Các ngoại lệ phổ biến của **java.nio.file**:

| Ngoại lệ | Tình huống tiêu biểu |
| --- | --- |
| **FileAlreadyExistsException** | Tạo mới/copy/move mà tên đích đã có |
| **DirectoryNotEmptyException** | Xóa thư mục đang chứa mục con |
| **NoSuchFileException** | Thiếu đường dẫn nguồn/đích cần thiết |
| **AccessDeniedException** | Hệ thống từ chối quyền truy cập |
| **AtomicMoveNotSupportedException** | Yêu cầu ATOMIC_MOVE nhưng provider không hỗ trợ |
| **IOException** | Các lỗi I/O khác, bao gồm trường hợp provider báo lỗi bằng loại tổng quát |

Các loại exception cụ thể **không phải luôn được mọi hệ thống file ném giống nhau**; Javadoc dùng các loại exception tùy chọn trong nhiều hợp đồng. Phải luôn có xử lý cho **IOException** tổng quát, hoặc để nó lan ra cho tầng trên xử lý.

Một policy rõ ràng:

~~~java
try {
    Files.copy(source, target); // Chính sách từ chối ghi đè.
} catch (FileAlreadyExistsException ex) {
    // Báo người dùng: đổi tên đích hoặc xác nhận thay thế.
} catch (IOException ex) {
    // Ghi log/chẩn đoán lỗi I/O khác; không coi là "file đã tồn tại".
    throw ex;
}
~~~

Đây là **mảnh code minh họa**, không phải chương trình chạy độc lập. Khi chọn REPLACE_EXISTING, vẫn bắt IOException; không ngầm hiểu mọi việc ghi đè đều thành công.

## 12. Quy tắc kiểm tra hậu điều kiện và an toàn thao tác

### 12.1. So sánh nội dung thay vì chỉ so đường dẫn

Sau copy cần bảo đảm byte giống nhau, có thể sử dụng:

~~~java
long mismatch = Files.mismatch(source, target);
if (mismatch != -1L) {
    throw new IOException(
            "File đích khác nguồn tại byte: " + mismatch);
}
~~~

Đây là **mảnh code**, dùng khi cả source và target là file phù hợp có thể đọc và không bị sửa đồng thời. **Files.mismatch** (Java 12+) trả -1 nếu không phát hiện byte khác nhau. Không đủ nếu chỉ so kích thước hoặc chỉ dựa vào tên file.

### 12.2. Đừng xóa trước rồi mới copy nếu cần giữ bản cũ

Một mẫu rủi ro:

~~~java
Files.delete(target);
Files.copy(source, target);
~~~

Nếu bước copy thất bại, bản cũ đã mất. Cũng không nên dùng Files.deleteIfExists(target) rồi copy như cách “tạo điều kiện” mặc định. Khi có quyền thay thế, cân nhắc **copy vào file tạm, kiểm tra rồi move**, và xác định rõ khả năng atomic move/hỗ trợ provider.

### 12.3. Đừng giả định exists() xác nhận quyền hoặc tính an toàn

Một quy trình kiểu:

~~~java
if (Files.exists(target)) {
    Files.delete(target);
}
Files.move(source, target);
~~~

vẫn có race condition giữa check/delete/move. Đặc biệt nguy hiểm nếu target do người khác có thể thay đổi hoặc trỏ tới symlink. Dùng **option** diễn đạt trực tiếp điều kiện và chỉ thao tác trong đường dẫn được phép.

### 12.4. Bảo vệ dữ liệu người dùng

Không chấp nhận trực tiếp đường dẫn tùy ý rồi gọi xóa đệ quy hoặc replace. Khi nhận tên file từ người dùng, cần chuẩn hóa và kiểm tra phạm vi trong thư mục cho phép, xử lý đường dẫn tuyệt đối, **..**, symbolic links và quyền truy cập. Với môi trường đối kháng, phép kiểm tra path thông thường vẫn có thể bị race; dùng cơ chế file handle/quyền hoặc dịch vụ lưu trữ an toàn phù hợp.

Trong các thao tác hủy dữ liệu, hãy phân biệt “**tên đích thuộc ứng dụng**” và “**nội dung đích có thể phá hủy**”. Thư mục thuộc ứng dụng vẫn có thể chứa dữ liệu người dùng không được phép xóa.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** File target đã có; gọi **Files.copy(source,target)** không option thì sao?  
**Đáp:** Thông thường ném **FileAlreadyExistsException**; không mặc định thay thế dữ liệu cũ.

**Câu 2.** **REPLACE_EXISTING** có cho phép Files.copy thay một thư mục không rỗng bằng file không?  
**Đáp:** Không được mặc định như vậy. Target là thư mục không rỗng có thể không thể thay; DirectoryNotEmptyException/IOException có thể phát sinh.

**Câu 3.** **Files.writeString(path, "X")** có mặc định từ chối file đang tồn tại như Files.copy không?  
**Đáp:** Không. Với các option mặc định, nó tạo file khi thiếu hoặc **truncate** file hiện có rồi ghi nội dung.

**Câu 4.** **Files.deleteIfExists(directory)** có tự xóa mọi file con không?  
**Đáp:** Không. Nó chỉ cho phép bỏ qua trường hợp đường dẫn thiếu; thư mục không rỗng vẫn không xóa trực tiếp được.

**Câu 5.** Vì sao dùng **Files.exists(target)** rồi **Files.createFile(target)** không thay CREATE_NEW?  
**Đáp:** Giữa kiểm tra và tạo có cửa sổ race; CREATE_NEW/CreateFile ràng buộc điều kiện không tồn tại ngay tại thao tác tạo.

**Câu 6.** **REPLACE_EXISTING** và **ATOMIC_MOVE** giống nhau không?  
**Đáp:** Không. REPLACE_EXISTING quy định mong muốn thay đích; ATOMIC_MOVE yêu cầu di chuyển nguyên tử nếu provider hỗ trợ, và khi đi cùng ATOMIC_MOVE các option khác có thể bị bỏ qua.

**Câu 7.** Muốn xóa thư mục không rỗng mà vẫn an toàn, trước hết cần làm gì?  
**Đáp:** Xác định **phạm vi được phép xóa**, hiểu cây dữ liệu và symlink, chọn giải pháp duyệt con trước cha có xử lý lỗi; không tự động gọi xóa đệ quy với đường dẫn không tin cậy.

**Câu 8.** Để không mất bản đích cũ khi ghi cập nhật lỗi giữa chừng, hướng tiếp cận nào tốt hơn?  
**Đáp:** Tạo file tạm riêng, ghi/kiểm tra đầy đủ rồi move theo chính sách atomic/replacement được hỗ trợ. Vẫn cần xử lý failure và không tự suy diễn hỗ trợ atomic trên mọi filesystem.

## 14. Tổng kết

**Tệp đích đã tồn tại** không phải một lỗi có cách chữa duy nhất: cần chọn **từ chối**, **thay thế**, **ghi tiếp**, **đổi tên mới** hoặc **cập nhật thông qua file tạm**. API mang những mặc định khác nhau: **Files.copy/move** thường từ chối target đã tồn tại, nhưng **Files.writeString/newOutputStream** mặc định có thể truncate file đang có. **CREATE_NEW** giúp tạo mới không ghi đè; **REPLACE_EXISTING** biểu diễn chính sách thay thế nhưng không bảo đảm copy/move nguyên tử hay khả năng thay thư mục không rỗng.

**Thư mục không rỗng** không được xóa bởi **Files.delete**, **Files.deleteIfExists** hay **File.delete** như một phép xóa đệ quy. Muốn dọn cây phải có phạm vi sở hữu và chiến lược duyệt/xóa rõ ràng, xử lý symlink, quyền, race và thất bại một phần.

Khi thao tác trên dữ liệu quan trọng, **đừng coi boolean, option hay lời gọi Files thành cam kết giao dịch**. Kiểm tra hậu điều kiện và thiết kế để lỗi không biến thành mất dữ liệu.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): Files.copy, Files.move, Files.createFile, Files.delete, Files.deleteIfExists, Files.writeString và Files.walk.
- [Oracle Java SE 17 — StandardCopyOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html): REPLACE_EXISTING, COPY_ATTRIBUTES, ATOMIC_MOVE.
- [Oracle Java SE 17 — StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): CREATE_NEW, CREATE, TRUNCATE_EXISTING, APPEND.
- [Oracle Java SE 17 — DirectoryNotEmptyException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/DirectoryNotEmptyException.html): thư mục có mục con.
- [Oracle Java SE 17 — FileAlreadyExistsException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileAlreadyExistsException.html): đường dẫn đích đã chiếm tên.
- [Oracle Java SE 17 — java.io.File](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/File.html): createNewFile, delete và renameTo trong API truyền thống.
