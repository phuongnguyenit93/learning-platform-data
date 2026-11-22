# `Files` trong Java: Tạo tệp tạm và quản lý việc dọn dẹp

## 1. Mục tiêu: tài nguyên tạm phải có vòng đời rõ ràng

Ứng dụng Java cần tệp tạm (*temporary file*) khi tạo nội dung trung gian trước lúc xuất báo cáo, xử lý upload, giải nén trong vùng làm việc biệt lập, chuẩn bị dữ liệu cho thư viện chỉ nhận đường dẫn tệp hoặc thực hiện kiểm thử có thao tác I/O. Tệp tạm vẫn là **một tệp thật trên hệ thống tệp**, có thể chiếm dung lượng, chứa dữ liệu nhạy cảm và bị giữ lại nếu chương trình không dọn dẹp.

Java cung cấp các API chuẩn của `java.nio.file.Files`:

- `Files.createTempFile(prefix, suffix)`: tạo **tệp rỗng** có tên do provider sinh ra trong thư mục tạm mặc định.
- `Files.createTempFile(dir, prefix, suffix)`: tạo tệp tạm **bên trong thư mục được chỉ định**.
- `Files.createTempDirectory(prefix)`: tạo **thư mục tạm rỗng** ở thư mục tạm mặc định.
- `Files.createTempDirectory(dir, prefix)`: tạo thư mục tạm rỗng bên trong `dir`.
- `Files.delete(path)`: xóa đối tượng được chỉ định; báo lỗi nếu không xóa được.
- `Files.deleteIfExists(path)`: xóa nếu tồn tại; trả `false` nếu không tồn tại, nhưng **vẫn có thể ném `IOException`** nếu thao tác xóa thất bại.

**Điều quyết định tính đúng:** `createTempFile`/**`createTempDirectory` không tự đăng ký xóa khi hết phương thức hoặc khi JVM dừng**. Mã tạo tệp phải có kế hoạch dọn dẹp **trong cả trường hợp thành công và thất bại**.

Ví dụ tư duy vòng đời:

```text
Tạo tệp/không gian tạm
        ↓
Ghi / đọc / xử lý dữ liệu
        ↓
Đóng tất cả stream, channel, reader, writer đang mở
        ↓
Xóa các tệp con và thư mục con (nếu có)
        ↓
Xóa thư mục tạm gốc
        ↓
Xác nhận đã dọn sạch hoặc báo lỗi dọn dẹp
```

Trong bài này, ví dụ chạy bằng **Java 17+**, chỉ dùng JDK chuẩn. Các phương thức `Files.createTempFile`, `createTempDirectory`, `delete`, `walkFileTree` đã có từ Java 7 và vẫn còn được sử dụng trong Java hiện đại; `Files.writeString`/`readString` là tiện ích có từ Java 11.

## 2. Tạo một tệp tạm bằng `Files.createTempFile`

### 2.1. Tạo trong thư mục tạm mặc định

```java
import java.nio.file.Files;
import java.nio.file.Path;

Path temp = Files.createTempFile("report-", ".txt");
```

Đoạn này là **mã minh họa bên trong phương thức có xử lý `IOException`**. Nếu thành công, `temp` đại diện một **tệp rỗng đã được tạo thật** với tên có phần bắt đầu là `report-` và kết thúc là `.txt` theo quy tắc provider.

Ví dụ một tên có thể xuất hiện:

```text
/tmp/report-482173106824536789.txt
```

**Không có tên nào cố định hoặc được bảo đảm giống ví dụ:** phần tên được sinh là chi tiết triển khai, đường dẫn thư mục tạm phụ thuộc hệ điều hành và cấu hình môi trường. Khi viết test, hãy kiểm tra thuộc tính (ví dụ `Files.isRegularFile(temp)`), không hard-code toàn bộ đường dẫn được tạo.

Thông số:

| Tham số | Ví dụ | Vai trò |
| --- | --- | --- |
| `prefix` | `"report-"` | Gợi ý tiền tố tên tệp để nhận biết mục đích |
| `suffix` | `".txt"` | Gợi ý hậu tố hoặc đuôi tên tệp |
| `dir` (tùy overload) | `Path` tới thư mục đã tồn tại | Nơi tạo tệp tạm |
| `attrs` (tùy overload) | `FileAttribute<?>...` | Thuộc tính cần thiết lập khi tạo, nếu provider hỗ trợ |

Theo API `Files`, `prefix` có thể là `null` và `suffix` có thể là `null` (nếu `suffix` là `null`, giá trị mặc định thường là `.tmp`); các ràng buộc tên cụ thể phụ thuộc file-system provider. Không nhầm với một số yêu cầu cũ của `java.io.File.createTempFile`, trong đó prefix phải dài ít nhất ba ký tự.

`Files.createTempFile` tạo tệp mới chưa tồn tại trước lời gọi đó. **Không cần tự tạo tên ngẫu nhiên rồi `Files.exists` trước khi tạo**: cách “check rồi create” không nguyên tử, có thể có cạnh tranh giữa tiến trình và rủi ro tên bị chiếm.

### 2.2. Tạo trong thư mục ứng dụng kiểm soát

Khi cần tệp tạm cùng vùng làm việc hoặc cùng filesystem với dữ liệu đích:

```java
Path workDir = Path.of("work-area");
Files.createDirectories(workDir);

Path temp = Files.createTempFile(
        workDir, "render-", ".partial");
```

Đây là **đoạn minh họa** có import `java.nio.file.Files` và `Path`, không phải chương trình chạy độc lập.

Điểm cần phân biệt:

- `Files.createDirectories(workDir)` tạo cây thư mục cha nếu cần, nhưng **không tự khiến workDir trở thành tạm** và không tự dọn thư mục.
- `Files.createTempFile(workDir, ...)` **tạo ngay** một tệp mới trong `workDir`. Không thêm `.resolve("render.tmp")` rồi tự ghi đè tên chung.
- Tạo tệp trung gian cùng filesystem với tệp đích có thể hữu ích cho các quy trình cần chuyển tệp bằng `Files.move`; nhưng **`ATOMIC_MOVE` có được hỗ trợ hay không vẫn phụ thuộc provider/filesystem** và phải xử lý lỗi.
- Nếu thư mục nằm trong vùng do các thành phần khác dùng, chỉ xóa **đúng path mà bạn sở hữu**, không xóa bừa toàn bộ `workDir`.

### 2.3. Prefix/suffix không phải chính sách bảo mật

Chọn prefix gợi nghĩa như `"upload-"` hoặc `"invoice-"` giúp log dễ đọc, nhưng không nên nhét **mật khẩu, mã khách hàng, token, email hoặc thông tin nhạy cảm** vào tên tệp. Tên và đường dẫn có thể xuất hiện trong log, danh sách thư mục, thông tin lỗi hoặc công cụ giám sát.

Tệp mới không nhất thiết có quyền truy cập giống mọi hệ điều hành; `Files.createTempFile` theo API có thể áp quyền mặc định chặt hơn một số cách tạo tệp cũ. Tuy nhiên, **không coi điều đó là lời hứa tuyệt đối rằng mọi tệp tạm mặc định chỉ mình ứng dụng đọc được**. Khi xử lý dữ liệu nhạy cảm, phải kiểm tra quyền truy cập thực tế và cấu hình vùng tạm theo hệ điều hành/provider.

## 3. Tạo một thư mục tạm riêng cho cả tác vụ

### 3.1. Vì sao không chỉ tạo từng tệp ở thư mục tạm toàn cục?

Một tác vụ có thể sinh nhiều tệp đầu ra, bản ghi phụ, thư mục con, ảnh hoặc kết quả giải nén. Nếu mọi file nằm chung trong thư mục tạm của OS, việc xác định **file nào thuộc về tác vụ nào** dễ sai.

Giải pháp thường rõ ràng hơn:

```java
Path workspace = Files.createTempDirectory("job-");

Path first = Files.createTempFile(
        workspace, "input-", ".dat");

Path nested = Files.createTempDirectory(
        workspace, "images-");

Path second = Files.createTempFile(
        nested, "preview-", ".png");
```

Đây là **đoạn minh họa**, cần bao quanh bằng cơ chế cleanup sẽ trình bày sau.

Lợi ích:

- Mỗi tác vụ có một **root riêng** (tên do `Files` tạo).
- Tất cả tệp con nằm trong root do tác vụ sở hữu, dễ xác định phạm vi xóa.
- Không cần tìm và xóa theo wildcard trong thư mục tạm chung của hệ điều hành.
- Các tác vụ đồng thời ít có nguy cơ đụng tên file.
- Có thể tổ chức dữ liệu theo cây con, miễn có chiến lược dọn dẹp **đệ quy**.

**Đừng nhầm `Files.createTempDirectory(...)` với “tạo thư mục sẽ tự biến mất khi task xong”.** Nó tạo **đúng một thư mục mới**, không quản lý vòng đời về sau.

### 3.2. Thư mục tạm phải tồn tại nếu dùng overload nhận `dir`

`Files.createTempFile(dir, prefix, suffix)` và `Files.createTempDirectory(dir, prefix)` yêu cầu `dir` là một thư mục có thể dùng được theo filesystem provider. Chúng không thay thế `Files.createDirectories(dir)` để tự dựng mọi thư mục cha.

Nếu truyền một `dir` không tồn tại, không có quyền hoặc bị thay đổi đồng thời, có thể nhận `IOException`. Không dùng tên path cố định trong một thư mục chia sẻ rồi mặc định tác vụ luôn được tạo thành công.

## 4. Mẫu tối thiểu đúng: `try`/`finally` và `deleteIfExists`

Nếu chỉ có **một tệp tạm** và công việc đơn giản, mẫu dễ đọc là:

```java
Path temp = Files.createTempFile("notes-", ".txt");

try {
    Files.writeString(
            temp, "Nội dung tạm", StandardCharsets.UTF_8);

    String text = Files.readString(
            temp, StandardCharsets.UTF_8);

    System.out.println(text);
} finally {
    Files.deleteIfExists(temp);
}
```

Đây là **mã minh họa trong một phương thức** có `throws IOException` hoặc xử lý lỗi phù hợp; cần import `Files`, `Path` và `StandardCharsets`.

- Nếu tạo tệp **thất bại**, chương trình chưa có path mới thành công để xóa. Nếu tạo thành công thì biến `temp` đã giữ đúng path của tệp mới.
- Mọi câu lệnh **bên trong `try`** có thể hoàn tất hoặc ném exception; `finally` vẫn được chạy theo ngữ nghĩa Java khi luồng điều khiển rời khối bình thường.
- `deleteIfExists` làm mã cleanup dễ chịu hơn nếu file đã bị xóa trước đó, nhưng **không biến lỗi quyền, file đang bị khóa hay I/O thành thành công giả**. Nếu xóa thất bại, nó có thể ném `IOException`.
- Không “dọn dẹp” bằng cách đoán lại tên file tạm. Chỉ xóa **đúng `Path` mà API tạo trả về**.

**Giới hạn:** nếu công việc trong `try` ném lỗi A và `Files.deleteIfExists` trong `finally` ném lỗi B, B có thể **che mất exception A**. Với ứng dụng cần giữ đủ lỗi để chẩn đoán, dùng một lớp tài nguyên do mình sở hữu đóng theo `AutoCloseable` hoặc xử lý suppressed exception có chủ đích (mục 7).

### 4.1. `delete` hay `deleteIfExists`?

| API | Nếu path không tồn tại | Nếu xóa thành công | Nếu không xóa được do I/O/quyền |
| --- | --- | --- | --- |
| `Files.delete(path)` | Ném `NoSuchFileException` hoặc lỗi tương ứng | Trả về bình thường | Ném `IOException` |
| `Files.deleteIfExists(path)` | Trả `false` | Trả `true` | **Vẫn có thể ném `IOException`** |

Dùng `delete` khi **thiếu tệp** là một vi phạm invariant cần phát hiện; dùng `deleteIfExists` khi việc tệp đã biến mất là trường hợp có thể chấp nhận. **Không bỏ qua kết quả/lỗi xóa** nếu việc dọn sạch là yêu cầu quan trọng của ứng dụng.

### 4.2. Không nhầm xóa path với đóng stream

`Path` chỉ đại diện **tên đường dẫn**, **không triển khai `AutoCloseable`**. Vì vậy:

```java
// Không hợp lệ: Path không phải AutoCloseable
// try (Path temp = Files.createTempFile("a-", ".tmp")) { ... }
```

Nếu bạn mở `InputStream`, `OutputStream` hoặc `BufferedReader` từ tệp, `try-with-resources` sẽ **đóng stream** khi kết thúc, nhưng **không tự xóa tệp**:

```java
Path temp = Files.createTempFile("data-", ".txt");

try {
    try (var writer = Files.newBufferedWriter(
            temp, StandardCharsets.UTF_8)) {
        writer.write("hello");
    }
    // writer đã đóng, nhưng tệp temp vẫn tồn tại.
} finally {
    Files.deleteIfExists(temp);
}
```

Đây là đoạn minh họa Java 17+ với `var` và các import phù hợp. Dù `close()` của stream có thể ném lỗi, `finally` vẫn **cố xóa** tệp. Nếu cả đóng stream và xóa tệp đều lỗi, cần quản lý exception như mục 7 để giữ nguyên nguyên nhân chính.

## 5. Thư mục tạm có nội dung: xóa từ tệp con tới thư mục cha

### 5.1. Vì sao `Files.deleteIfExists(workspace)` thường chưa đủ?

`Files.delete` và `deleteIfExists` **không xóa đệ quy một thư mục có nội dung**. Khi `workspace` còn tệp hoặc thư mục con, có thể nhận `DirectoryNotEmptyException` hoặc `IOException` tương ứng.

Sai về ý định:

```java
Path workspace = Files.createTempDirectory("job-");
Files.writeString(workspace.resolve("result.txt"), "done");

// Files.deleteIfExists(workspace); // thường lỗi: directory not empty
```

Đây là đoạn minh họa. Ngay cả khi có `Files.deleteIfExists(workspace)` trong `finally`, **chỉ gọi một lần ở root không tự xóa hết cây thư mục**.

Muốn xóa an toàn theo quan hệ cha/con, cần xóa **các tệp trước**, rồi mới xóa **thư mục chứa chúng**. Java có `Files.walkFileTree` cho mục đích này.

### 5.2. Dùng `Files.walkFileTree` cùng `SimpleFileVisitor`

```java
static void deleteTree(Path root) throws IOException {
    Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
        @Override
        public FileVisitResult visitFile(
                Path file, BasicFileAttributes attrs)
                throws IOException {
            Files.delete(file);
            return FileVisitResult.CONTINUE;
        }

        @Override
        public FileVisitResult postVisitDirectory(
                Path dir, IOException error)
                throws IOException {
            if (error != null) {
                throw error;
            }

            Files.delete(dir);
            return FileVisitResult.CONTINUE;
        }
    });
}
```

Đây là **phương thức minh họa bên trong một lớp**, cần import `java.nio.file.Files`, `Path`, `SimpleFileVisitor`, `FileVisitResult`, `java.nio.file.attribute.BasicFileAttributes` và `java.io.IOException`. Chương trình chạy độc lập ở mục 10 dùng cùng logic này.

Cơ chế:

1. `walkFileTree` đi vào cây thư mục theo cách traversal được API quy định.
2. `visitFile` được gọi khi gặp file; callback xóa file rồi trả `CONTINUE`.
3. `postVisitDirectory` chạy sau khi xử lý các mục con; callback xóa thư mục **khi đã rỗng**.
4. Nếu việc duyệt thư mục có lỗi, tham số `error` có thể khác `null`; phải xử lý hoặc ném lại, **không coi kết quả thành công khi chưa chắc đã duyệt hết**.
5. Nếu không xóa được một mục, `Files.delete` ném `IOException`; việc cleanup có thể dừng và **còn sót một phần cây**.

**Không nên tự viết `Files.list(root)` rồi xóa root trước**, hoặc chỉ sắp xếp chuỗi đường dẫn theo độ dài để giả định luôn đúng; cấu trúc cây và lỗi duyệt cần được xử lý đúng.

### 5.3. Kiểm soát phạm vi xóa: chỉ xóa workspace của mình

`deleteTree(root)` là một phép toán **phá hủy dữ liệu**. Đừng gọi nó trên:

- Thư mục tạm chung của hệ điều hành (ví dụ toàn bộ thư mục tạm mặc định).
- `Path.of(".")` hay thư mục hiện hành.
- Một path tự ráp từ dữ liệu người dùng chưa được xác minh.
- Thư mục dự án chứa nội dung không do tác vụ tạo.
- Một thư mục có thể đang được tiến trình khác sở hữu.

**Mô hình an toàn:** `Files.createTempDirectory("job-")` tạo một root riêng; truyền **chính Path trả về** cho đối tượng quản lý vòng đời; chỉ xóa root đó khi đối tượng kết thúc. Với các tác vụ đồng thời, mỗi tác vụ có root riêng.

### 5.4. Symbolic link và file ngoài root

`Files.walkFileTree(root, visitor)` với overload thông thường **không bật `FOLLOW_LINKS`**, nên nó không tự đi theo các symbolic link trỏ sang thư mục ngoài như một subtree cần duyệt. Khi gặp symbolic link trong cây, visitor xử lý **link như một file entry** và lời gọi `Files.delete(link)` xóa bản thân link, không xóa đối tượng đích.

Đây là hành vi có ích cho cleanup workspace, nhưng **không biến thao tác thành sandbox chống mọi tấn công**: file hoặc symlink có thể bị tiến trình khác thay đổi trong lúc duyệt; quyền hoặc provider cũng có thể ảnh hưởng hành vi. Với workspace chứa dữ liệu không tin cậy hoặc có sự thay đổi đồng thời, cần có chính sách bảo mật và cơ chế quyền/OS phù hợp. **Không dùng `FOLLOW_LINKS` tùy tiện khi xóa đệ quy**.

## 6. Kết hợp với `try-with-resources` để đóng tài nguyên và dọn tệp

### 6.1. `try-with-resources` quản lý `AutoCloseable`, không quản lý `Path`

Trong Java:

```java
try (InputStream in = Files.newInputStream(path)) {
    // Đọc bytes...
}
```

Cấu trúc này **đóng `in`**, còn **path vẫn đại diện tệp trên hệ thống tệp**. Nếu tệp là tạm và phương thức có quyền sở hữu, phải **xóa riêng** sau khi stream đã đóng.

Đóng handle trước rồi xóa là chiến lược portable hơn; trên một số hệ điều hành, file đang mở có thể không xóa được, hoặc cách xóa file đang mở phụ thuộc implementation.

### 6.2. Tạo một tài nguyên sở hữu thư mục tạm

Để tránh quên cleanup khi có exception hoặc `return`, có thể gói thư mục tạm vào một đối tượng `AutoCloseable`:

```java
static final class TempWorkspace implements AutoCloseable {
    final Path root;

    TempWorkspace() throws IOException {
        root = Files.createTempDirectory("lesson-work-");
    }

    @Override
    public void close() throws IOException {
        deleteTree(root);
    }
}
```

Đây là **thành phần minh họa**, không phải chương trình độc lập. Nó chỉ chứa **root mà constructor đã tạo**. Khi đưa đối tượng này vào `try-with-resources`:

```java
try (TempWorkspace workspace = new TempWorkspace()) {
    Path file = Files.createTempFile(
            workspace.root, "stage-", ".txt");

    Files.writeString(
            file, "intermediate", StandardCharsets.UTF_8);

    // Xử lý dữ liệu...
}
```

Java gọi `workspace.close()` lúc rời khối, nên cleanup được **thử thực hiện trên cả đường thành công, exception và return**. Các đoạn code ở trên cần đặt trong lớp có `deleteTree(...)` và import tương ứng; mục 10 là chương trình đầy đủ.

**Đây không phải phép màu:** Nếu `close()` thất bại vì file đang bị dùng/không có quyền, chương trình vẫn phải xử lý exception và có thể còn dữ liệu trên ổ. Trách nhiệm của lớp là **thực thi cleanup và báo lỗi**, không phải cam kết rằng không thể xảy ra sự cố I/O.

### 6.3. Vì sao dùng custom `AutoCloseable` giúp bảo toàn exception?

Giả sử công việc ném `IOException("operation-failed")`, rồi cleanup trong `close()` cũng ném `IOException("cleanup-failed")`. Theo `try-with-resources`:

- Lỗi của phần thân `try` là exception **chính**.
- Lỗi `close()` được thêm vào `getSuppressed()` của exception chính.
- Người gọi có thể kiểm tra **cả hai** để chẩn đoán.

Ngược lại, nếu chỉ đặt `Files.delete(...)` trong `finally` mà không xử lý thêm, lỗi xóa có thể làm exception ban đầu bị che. Vì vậy **đóng tài nguyên bằng `try-with-resources` là lựa chọn hợp lý khi muốn sử dụng cơ chế suppressed exceptions của Java**.

### 6.4. Nếu không muốn tạo custom wrapper thì sao?

Với một tệp rất đơn giản, `try/finally` vẫn là giải pháp tốt. Không bắt buộc phải tạo hẳn một lớp cho mỗi tệp.

Hãy chọn theo yêu cầu:

- **Một tệp và thao tác ngắn:** `try/finally` với `Files.deleteIfExists`.
- **Nhiều file và thư mục con:** một workspace tạm được sở hữu rõ, kèm một cleanup đệ quy.
- **Luồng stream:** `try-with-resources` cho stream; cleanup file sau khi stream đóng.
- **Cần bảo vệ exception chính:** custom `AutoCloseable` cho cleanup hoặc xử lý suppressed exception cẩn thận.
- **File còn phải dùng sau khi method trả về:** không xóa ở cuối method; chuyển ownership và thời điểm cleanup rõ cho caller.

## 7. Lỗi khi dọn dẹp: không nuốt, không vô tình che lỗi nghiệp vụ

### 7.1. Khi `finally` cũng có lỗi

```java
try {
    doWork();
} finally {
    Files.deleteIfExists(temp);
}
```

Đây là đoạn **minh họa**, với `doWork()` và `temp` đã được khai báo. Nếu `doWork()` ném lỗi A nhưng xóa `temp` ném lỗi B, Java có thể truyền B ra ngoài và caller không còn nhận A trực tiếp như mong muốn.

Một hướng nâng cấp là đặt thao tác dọn trong `AutoCloseable` và dùng `try-with-resources` để Java tự quản lý **primary/suppressed**. Với code không thể dùng cách đó, cần xử lý lỗi xóa và gắn nó vào exception chính một cách tường minh nếu hệ thống yêu cầu. Không bắt exception rồi bỏ qua hoàn toàn vì “đó chỉ là file tạm”: rò rỉ tệp có thể tiêu thụ dung lượng hoặc giữ dữ liệu nhạy cảm.

### 7.2. Không phải cứ xóa lỗi là phải bỏ mất kết quả chính

Tùy nghiệp vụ, lỗi cleanup có thể được:

- **Truyền ra** cho caller khi việc dọn sạch là yêu cầu bắt buộc.
- **Gắn suppressed** vào exception chính nếu công việc cũng lỗi.
- **Ghi log và lập lịch retry theo chính sách vận hành**, khi hệ thống quyết định lỗi cleanup không được làm thất bại kết quả công việc.

Chính sách phải được quy định rõ: một công việc xuất báo cáo thành công nhưng không xóa tệp trung gian nhạy cảm có thể là **lỗi nghiêm trọng**, không nên luôn chỉ ghi debug log.

### 7.3. Test failure path, không chỉ success path

Tối thiểu cần một phép thử:

1. Tạo tệp tạm thành công.
2. Ghi nội dung trung gian.
3. Ném `IOException` giả lập từ thân công việc.
4. Xác nhận root do tác vụ sở hữu đã được dọn sau khi exception đi ra.
5. Xác nhận exception gốc vẫn giữ nguyên.
6. Nếu `close()`/cleanup cũng lỗi, kiểm tra `getSuppressed()`.

Không nên test bằng cách để tệp tạm **thật** bị khóa lâu hoặc phá quyền truy cập của thư mục người dùng. Đối với logic exception, một `AutoCloseable` giả có `close()` ném lỗi giúp kiểm chứng sạch và an toàn.

## 8. `DELETE_ON_CLOSE`: tiện nhưng không phải bảo đảm tuyệt đối

`StandardOpenOption.DELETE_ON_CLOSE` (Java 7+) yêu cầu provider **cố gắng xóa** file khi handle mở với option đó được đóng. Ví dụ:

```java
Path temp = Files.createTempFile("stream-", ".bin");

try (OutputStream out = Files.newOutputStream(
        temp,
        StandardOpenOption.WRITE,
        StandardOpenOption.DELETE_ON_CLOSE)) {
    out.write(new byte[]{1, 2, 3});
}
```

Đây là **đoạn minh họa** có import `java.nio.file.Files`, `Path`, `StandardOpenOption` và `java.io.OutputStream`. Tệp đã được tạo trước, nên không dùng `CREATE_NEW` cho lần mở ghi này; nếu cần ghi đè toàn bộ dữ liệu hãy chọn `TRUNCATE_EXISTING` rõ ràng.

Tài liệu Java API nêu rõ:

- Đây là **best effort**, có nhiều chi tiết triển khai phụ thuộc provider.
- Mục đích chính là file làm việc của **một JVM**; không nên dùng khi file được nhiều thực thể mở đồng thời.
- Nếu `close()` không được gọi, provider có thể cố xóa khi JVM kết thúc, **không bảo đảm** thành công.
- Việc file được thay thế đồng thời, symlink hoặc các điều kiện bảo mật có thể tạo rủi ro; không dùng như cơ chế bảo vệ dữ liệu tuyệt đối.
- Option có thể không được hỗ trợ trong một số file system/provider. Xem tài liệu và xử lý `IOException`/`UnsupportedOperationException` thích hợp.

**Khi nào hợp lý?** Một file rất ngắn hạn, chỉ sử dụng thông qua **handle được giữ riêng**, không cần mở lại theo path sau khi handle đóng và provider hỗ trợ.

**Khi nào nên tránh?** Một pipeline phải đóng stream xong **rồi mở lại file ở bước sau**, hoặc file cần được chuyển cho thư viện khác. Trong trường hợp đó, xóa tường minh sau khi mọi consumer kết thúc thường dễ kiểm soát hơn.

## 9. `File.deleteOnExit()` không phải chính sách cleanup chính

Java vẫn hỗ trợ:

```java
Path temp = Files.createTempFile("process-", ".txt");
temp.toFile().deleteOnExit();
```

Tuy nhiên, đây **không phải lựa chọn nên dùng mặc định trong ứng dụng dài hạn**:

- `deleteOnExit()` yêu cầu JVM cố xóa file **khi JVM kết thúc bình thường**, không xóa khi method/task hoàn tất.
- Nếu tiến trình bị kill, máy mất điện hoặc runtime dừng bất thường, không nên dựa vào việc cleanup sẽ diễn ra.
- Lệnh đăng ký không có cơ chế **hủy đăng ký** trong API đó. Với một process tạo rất nhiều tệp tạm, danh sách các đường dẫn đã đăng ký có thể làm tăng bộ nhớ trong vòng đời JVM.
- Nếu là thư mục chứa nội dung, lệnh này không tự xóa đệ quy như `walkFileTree`. Việc đăng ký file con và thư mục cha phải xét đúng thứ tự, nhưng vẫn có giới hạn nêu trên.
- Cách đăng ký không tự giải quyết file đang mở, quyền truy cập hoặc lỗi I/O.

**Lựa chọn ưu tiên:** dọn trong `finally` hoặc `close()` khi **tác vụ kết thúc**. Chỉ cân nhắc `deleteOnExit()` như cơ chế bổ sung trong tình huống đã hiểu rõ giới hạn, không phải giải pháp thay thế cleanup theo scope.

Tương tự, JVM shutdown hook chỉ chạy trong những điều kiện cụ thể, không phải bảo đảm xóa trên mọi kiểu crash hoặc khi host container bị dừng cưỡng bức. Một hệ thống cần dọn dẹp có độ tin cậy cao có thể cần **cơ chế vận hành riêng** để rà soát và xóa file tạm đã quá hạn trong một thư mục do ứng dụng quản lý.

## 10. Chương trình Java 17+ đầy đủ: thành công, lỗi và dọn đệ quy

Chương trình sau chỉ thao tác trong các **tệp/thư mục tạm mới được chính nó tạo**, không đụng vào thư mục dự án hoặc tệp của người dùng. Mọi path ngẫu nhiên chỉ dùng nội bộ, nên stdout **không phụ thuộc tên file do OS tạo**.

Bốn bài thử:

1. Một file tạm: ghi/đọc nội dung UTF-8 rồi xóa trong `finally`.
2. Một thư mục tạm có file và thư mục con: xóa **từ con lên cha** bằng `walkFileTree`.
3. Thân công việc ném `IOException`: `AutoCloseable` vẫn dọn root; exception chính giữ đúng object.
4. Một tài nguyên giả có `close()` cũng lỗi: chứng minh `getSuppressed()` giữ lỗi cleanup và exception của thân vẫn là primary.

Tạo tệp **`TempCleanupDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

public final class TempCleanupDemo {

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static final class TempWorkspace implements AutoCloseable {
        final Path root;

        TempWorkspace() throws IOException {
            root = Files.createTempDirectory("lesson-work-");
        }

        @Override
        public void close() throws IOException {
            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {

                @Override
                public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attrs)
                        throws IOException {
                    Files.delete(file);
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult postVisitDirectory(
                        Path dir, IOException error)
                        throws IOException {
                    if (error != null) {
                        throw error;
                    }
                    Files.delete(dir);
                    return FileVisitResult.CONTINUE;
                }
            });
        }
    }

    static void singleFile() throws IOException {
        Path temp = Files.createTempFile("lesson-note-", ".txt");
        check(Files.isRegularFile(temp), "temp file not created");

        try {
            Files.writeString(
                    temp, "Xin chao", StandardCharsets.UTF_8);

            check(Files.readString(
                    temp, StandardCharsets.UTF_8).equals("Xin chao"),
                    "content mismatch");

            System.out.println("single.content=true");
        } finally {
            Files.deleteIfExists(temp);
        }

        System.out.println(
                "single.cleaned=" + !Files.exists(temp));
    }

    static void nestedSuccess() throws IOException {
        Path savedRoot;

        try (TempWorkspace workspace = new TempWorkspace()) {
            savedRoot = workspace.root;

            Path nested = Files.createTempDirectory(
                    workspace.root, "nested-");

            Path one = Files.createTempFile(
                    workspace.root, "item-", ".tmp");

            Path two = Files.createTempFile(
                    nested, "child-", ".txt");

            Files.writeString(one, "A", StandardCharsets.UTF_8);
            Files.writeString(two, "B", StandardCharsets.UTF_8);

            check(Files.isRegularFile(one)
                    && Files.isRegularFile(two),
                    "expected both files");

            System.out.println("nested.files=true");
        }

        System.out.println(
                "nested.cleaned=" + !Files.exists(savedRoot));
    }

    static void failure() throws IOException {
        Path savedRoot = null;
        IOException original = new IOException("job-failed");

        try (TempWorkspace workspace = new TempWorkspace()) {
            savedRoot = workspace.root;

            Path file = Files.createTempFile(
                    workspace.root, "intermediate-", ".dat");

            Files.writeString(
                    file, "partial", StandardCharsets.UTF_8);

            throw original;
        } catch (IOException caught) {
            check(caught == original,
                    "must preserve original");

            System.out.println(
                    "failure.primary=" + caught.getMessage());
            System.out.println(
                    "failure.suppressed="
                            + caught.getSuppressed().length);
        }

        System.out.println(
                "failure.cleaned=" + !Files.exists(savedRoot));
    }

    static void suppressed() throws IOException {
        IOException original =
                new IOException("operation-failed");

        try (AutoCloseable resource = () -> {
            throw new IOException("cleanup-failed");
        }) {
            throw original;
        } catch (Exception caught) {
            check(caught == original,
                    "must preserve primary exception");
            check(caught.getSuppressed().length == 1,
                    "expect suppressed cleanup");

            System.out.println(
                    "suppressed.primary=" + caught.getMessage());
            System.out.println(
                    "suppressed.cleanup="
                            + caught.getSuppressed()[0].getMessage());
        }
    }

    public static void main(String[] args) throws Exception {
        singleFile();
        nestedSuccess();
        failure();
        suppressed();
        System.out.println("checks=PASS");
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac -encoding UTF-8 TempCleanupDemo.java
java TempCleanupDemo
```

**Stdout chính xác trong điều kiện file system cho phép tạo/xóa file tạm:**

```text
single.content=true
single.cleaned=true
nested.files=true
nested.cleaned=true
failure.primary=job-failed
failure.suppressed=0
failure.cleaned=true
suppressed.primary=operation-failed
suppressed.cleanup=cleanup-failed
checks=PASS
```

### 10.1. Cách đọc kết quả

- `single.content=true`: file vừa tạo có thể ghi/đọc như một file bình thường.
- `single.cleaned=true`: sau `finally`, path tạo ra không còn tồn tại.
- `nested.files=true`: file nằm ở cả root và một thư mục con được tạo thành công.
- `nested.cleaned=true`: `walkFileTree` xóa file trước rồi xóa thư mục con và root.
- `failure.primary=job-failed`: lỗi công việc giả lập vẫn là exception chính.
- `failure.suppressed=0`: trong lần chạy này việc dọn workspace thành công, nên không có lỗi phụ.
- `failure.cleaned=true`: việc thất bại trong thân tác vụ không làm bỏ qua cleanup.
- `suppressed.primary=operation-failed` và `suppressed.cleanup=cleanup-failed`: test với `AutoCloseable` giả xác nhận lỗi cleanup **được giữ lại** chứ không thay lỗi chính.
- `checks=PASS`: các phép kiểm tra quan trọng đã chạy; nếu một phép kiểm tra sai sẽ ném `AssertionError`.

**Lưu ý thiết kế:** `TempWorkspace.close()` dùng `walkFileTree` để xóa **mọi nội dung** trong root nó sở hữu. Đừng tái sử dụng lớp này với root do người dùng/tiến trình khác cung cấp mà không thiết kế lại chính sách an toàn. Lớp chỉ sinh root mới trong constructor.

### 10.2. Phạm vi của ví dụ

Ví dụ được thiết kế để **không in path ngẫu nhiên** và không cần framework test ngoài JDK. Nó không thể chứng minh rằng file system bất kỳ luôn cho xóa file, không thể mô phỏng mọi lỗi quyền/file lock, và không tự giải quyết việc JVM bị kill giữa chừng. Những điều này cần integration test và chính sách vận hành phù hợp.

Khi thay đoạn xóa bằng triển khai có thể ném lỗi thực, hãy luôn kiểm tra exception từ `close()` và `getSuppressed()` khi cần chẩn đoán. Không dùng sự thành công trên một máy làm bằng chứng cho mọi provider.

## 11. Bảo mật, dữ liệu nhạy cảm và tính di động

### 11.1. Tên file được tạo tự động không phải mật khẩu

`Files.createTempFile` giúp tránh đụng tên và tạo mới đúng API, nhưng **tên ngẫu nhiên không thay thế phân quyền và bảo vệ dữ liệu**. Tránh đặt nội dung nhạy cảm vào prefix, suffix, đường dẫn hiển thị hoặc message log.

Nếu chứa token, thông tin cá nhân, khóa hoặc bản sao dữ liệu nội bộ, hãy:

- Chọn thư mục tạm thuộc vùng do ứng dụng quản lý, có chính sách quyền truy cập phù hợp.
- Không ghi dữ liệu đó ra log hoặc exception message không cần thiết.
- Chỉ giữ file trong thời gian thực sự cần thiết.
- Dọn file cả khi tác vụ hoàn tất bất thường.
- Cân nhắc mã hóa/lưu trữ theo yêu cầu bảo mật và bảo vệ khóa riêng nếu định dạng đòi hỏi.
- Không dựa vào việc xóa bình thường như cam kết xóa vật lý không thể phục hồi trên mọi loại ổ đĩa/SSD/snapshot.

### 11.2. Thuộc tính file: sử dụng khi provider hỗ trợ

Một số hệ thống Unix/POSIX cho phép đặt quyền ngay lúc tạo:

```java
// Minh họa chỉ áp dụng với file-system hỗ trợ POSIX attributes.
var attrs = PosixFilePermissions.asFileAttribute(
        Set.of(PosixFilePermission.OWNER_READ,
               PosixFilePermission.OWNER_WRITE));

Path temp = Files.createTempFile(
        "private-", ".dat", attrs);
```

Đây là **đoạn minh họa không độc lập**, cần import `java.nio.file.attribute.PosixFilePermissions`, `PosixFilePermission`, `java.util.Set`, `Files` và `Path`. Trên Windows/provider không hỗ trợ POSIX, có thể gặp `UnsupportedOperationException`. Không mặc định POSIX permissions có ý nghĩa phổ quát cho mọi OS.

Hãy quy định quyền mong muốn và kiểm thử triển khai trên các môi trường mà sản phẩm hỗ trợ; không tạo file trước rồi thay quyền ở bước sau nếu yêu cầu bảo mật đòi hỏi thiết lập thuộc tính **ngay lúc tạo**.

### 11.3. Xóa an toàn và symbolic link

`walkFileTree` mặc định không theo symbolic link, nhưng môi trường có nhiều tiến trình cùng ghi vẫn có rủi ro **race condition**: một file có thể bị thay đổi hoặc đổi tên giữa lúc duyệt và xóa.

Với workload không tin cậy, đừng dùng một thao tác `Path.normalize()` hoặc `startsWith(root)` làm bảo đảm đầy đủ trước symlink và thay đổi đồng thời. Cân nhắc filesystem permissions, thư mục riêng không chia sẻ, quyền tối thiểu, các API hạn chế race như `SecureDirectoryStream` nếu provider hỗ trợ, hoặc tách tác vụ vào một sandbox đủ mạnh.

Không tự xóa bằng shell command với string từ user input như một cách “đơn giản hơn”: dấu cách, metacharacter, đường dẫn sai và quyền shell có thể biến một thao tác cleanup thành thao tác nguy hiểm.

### 11.4. Dung lượng, quota và tiến trình chết

File tạm có thể lấp đầy disk hoặc phân vùng temp; tạo quá nhiều thư mục nhỏ cũng tăng chi phí I/O. Với dịch vụ dài hạn:

- Giới hạn số lượng, kích thước và tuổi file tạm theo nghiệp vụ.
- Đóng handle kịp thời; không giữ file mở ngoài scope cần thiết.
- Nếu ứng dụng có thể crash, cân nhắc một **job cleanup vận hành** cho root do ứng dụng quản lý, có xác minh tuổi/ownership và không xóa dữ liệu của job đang chạy.
- Có metric/alert khi việc xóa thất bại hoặc dung lượng temp tăng bất thường.
- Tránh mặc định temp storage sẽ được OS dọn “ngay sau vài phút”; mỗi môi trường có chính sách khác nhau.

## 12. Kiểm thử tệp tạm: tránh đường dẫn cố định và test bị nhiễm bẩn

### 12.1. Unit test không nên để file rác

Trong một test kiểm tra code ghi file:

```java
Path temp = Files.createTempFile("test-", ".txt");

try {
    Files.writeString(
            temp, "hello", StandardCharsets.UTF_8);

    if (!Files.readString(temp, StandardCharsets.UTF_8)
            .equals("hello")) {
        throw new AssertionError("wrong content");
    }
} finally {
    Files.deleteIfExists(temp);
}
```

Đây là một đoạn **minh họa trong method test**. Chỉ dùng tên cố định như `"test-output.txt"` trong working directory khi thực sự có yêu cầu và đã bảo đảm cô lập; nếu không, hai lần test song song có thể đè lên nhau.

### 12.2. Trong JUnit Jupiter, `@TempDir` giảm boilerplate

Nếu dự án dùng **JUnit Jupiter** và đã có dependency/test engine tương ứng, `@TempDir` cung cấp một thư mục tạm do framework quản lý:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.*;

class ExportTest {
    @TempDir
    Path tempDir;

    @Test
    void writesFile() throws Exception {
        Path file = tempDir.resolve("export.txt");

        Files.writeString(
                file, "ok", StandardCharsets.UTF_8);

        assertEquals("ok", Files.readString(
                file, StandardCharsets.UTF_8));
    }
}
```

Đây là **ví dụ JUnit Jupiter**, không thể chạy chỉ bằng `javac` không có JUnit. Việc dọn dẹp do extension của framework thực hiện theo chính sách của `@TempDir`, không phải do Java SE tự áp dụng cho mọi `Path`.

Có thể cần cấu hình cleanup mode của JUnit khi muốn giữ file phục vụ debug lúc test thất bại. Đừng trộn trách nhiệm framework với tự xóa cùng thư mục của nó theo cách gây race. Khi cần kiểm tra logic cleanup của **ứng dụng**, hãy test riêng đối tượng sở hữu resource chứ không chỉ dựa vào việc framework xóa thư mục cuối test.

### 12.3. Những nhánh nên kiểm tra

| Tình huống | Mong đợi |
| --- | --- |
| Tạo file thành công | Path mới, là file thật, nội dung rỗng ban đầu |
| Ghi và đọc file | Dữ liệu khớp, stream được đóng |
| Tác vụ ném exception | Cleanup vẫn được thử; exception chính không mất |
| Cleanup ném exception | Lỗi được truyền/ghi nhận theo policy, suppressed nếu thích hợp |
| Workspace có thư mục con | Xóa file trước, thư mục sau |
| File bị xóa từ nơi khác trước cleanup | `deleteIfExists` có thể trả `false` |
| File bị khóa/quyền không đủ | Có `IOException`, không tuyên bố cleanup thành công |
| Nhiều tác vụ đồng thời | Tên/root tạm khác nhau, không xóa nhầm |
| Symlink trong workspace | Không tự đi theo ra ngoài theo mặc định; kiểm tra bảo mật bổ sung |
| Crash hoặc kill JVM | Không coi `finally`/`deleteOnExit()` là bảo đảm chạy |
| Tệp nhạy cảm | Quyền và vòng đời được thực thi đúng hợp đồng |

## 13. Những lỗi phổ biến

| Sai lầm | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| Tự tạo path `/tmp/data.tmp` rồi ghi trực tiếp | Có thể đụng tên, ghi đè, không portable | `Files.createTempFile` |
| Dùng `Files.exists` rồi tạo tệp với tên mình đoán | Cửa sổ race giữa check và create | API tạo tệp mới nguyên tử |
| Tưởng `createTempFile` tự xóa khi method kết thúc | Nó chỉ tạo tệp, không quản lý lifecycle | `finally`, custom `AutoCloseable` hoặc policy rõ |
| Nghĩ `try (InputStream in = ...)` xóa tệp | Nó chỉ đóng stream | Xóa `Path` sau khi đóng handle |
| Đưa `Path` trực tiếp vào `try-with-resources` | `Path` không phải `AutoCloseable` | Quản lý stream hoặc wrapper sở hữu path |
| Chỉ gọi `deleteIfExists(root)` cho thư mục có file | Thư mục có nội dung không bị xóa đệ quy | `Files.walkFileTree` xóa con trước cha |
| Bỏ qua mọi `IOException` khi xóa | File rác tiếp tục chiếm dung lượng hoặc chứa dữ liệu nhạy cảm | Giữ/ghi lỗi theo policy |
| Dọn file bằng `finally` nhưng không xét lỗi thứ hai | Có thể che lỗi nghiệp vụ ban đầu | Dùng `try-with-resources`/suppressed |
| Dùng `deleteOnExit` để dọn sau mỗi request | Chỉ chạy khi JVM kết thúc bình thường | Cleanup theo scope của request/job |
| Quên đóng stream trước khi xóa | Provider/OS có thể không cho xóa file đang mở | Đóng handles bằng `try-with-resources` |
| Xóa nguyên thư mục temp của OS | Có thể xóa dữ liệu các tiến trình khác | Chỉ xóa root mới do job sở hữu |
| Bật `FOLLOW_LINKS` khi xóa cây mà không hiểu | Có nguy cơ duyệt tới vị trí ngoài root | Không follow link mặc định, đánh giá security |
| Dùng tên tệp ngẫu nhiên như biện pháp bảo mật duy nhất | Không thay thế permissions và chính sách dữ liệu | Đặt quyền, giới hạn truy cập và tuổi file |
| Cho rằng `DELETE_ON_CLOSE` luôn xóa chắc chắn | API chỉ hứa best effort | Đánh giá provider/OS và xử lý lỗi |
| Không test đường thất bại | Có thể rò rỉ khi exception xảy ra | Test failure/cleanup/suppressed paths |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `Files.createTempFile("job-", ".txt")` có tạo file thật ngay không?  
**Đáp án:** Có. Nếu lời gọi trả về thành công, một file mới đã được tạo trên filesystem và trả về một `Path` tương ứng.

**Câu 2.** Khi phương thức kết thúc, tệp mới có tự bị xóa không?  
**Đáp án:** Không. `createTempFile` không tự đặt lịch xóa; phải thiết kế cleanup theo ownership.

**Câu 3.** Dùng `try (OutputStream out = Files.newOutputStream(temp))` đã đủ để xóa temp chưa?  
**Đáp án:** Chưa. Cấu trúc này đóng `out`, không tự xóa file được tham chiếu bởi `temp`.

**Câu 4.** `Files.deleteIfExists(path)` có bảo đảm “không bao giờ ném lỗi” vì tên là “IfExists”?  
**Đáp án:** Không. Nó trả `false` nếu path không tồn tại, nhưng lỗi quyền, khóa hoặc I/O vẫn có thể gây `IOException`.

**Câu 5.** Vì sao phải xóa file con trước khi xóa thư mục temp?  
**Đáp án:** Vì `Files.delete(dir)` không xóa đệ quy thư mục có nội dung; thường cần xóa hết nội dung trước rồi xóa root.

**Câu 6.** Tại sao không xóa toàn bộ thư mục tạm của OS?  
**Đáp án:** Nó thường được nhiều chương trình dùng chung. Chỉ xóa những file/root do chính job tạo và sở hữu.

**Câu 7.** Nếu thân `try` và `close()` cùng ném exception, làm sao giữ cả hai?  
**Đáp án:** `try-with-resources` giữ exception của thân là primary và thêm lỗi `close()` qua `getSuppressed()`.

**Câu 8.** `File.deleteOnExit()` có phù hợp làm cleanup chính của một HTTP request trong server chạy nhiều ngày không?  
**Đáp án:** Không. Nó chỉ dọn khi JVM kết thúc theo điều kiện hỗ trợ, không dọn ngay cuối request; còn có giới hạn khi đăng ký rất nhiều path.

**Câu 9.** `DELETE_ON_CLOSE` có đảm bảo xóa được trong mọi provider không?  
**Đáp án:** Không. Tài liệu gọi đây là best effort với nhiều chi tiết phụ thuộc implementation.

**Câu 10.** Tệp có nội dung nhạy cảm có an toàn chỉ vì tên có chuỗi ngẫu nhiên không?  
**Đáp án:** Không. Cần permissions, thời gian lưu, vị trí thư mục, quản lý handle và xử lý lỗi cleanup phù hợp.

**Câu 11.** `Files.createTempDirectory` có tự thu thập file con được tạo bên trong để dọn không?  
**Đáp án:** Không. Cần một vòng đời workspace có ownership rõ, ví dụ `AutoCloseable` gọi `walkFileTree`.

**Câu 12.** Tại sao bài thử với exception giả hữu ích?  
**Đáp án:** Nó buộc code chạy nhánh thất bại để phát hiện tệp còn sót và xác nhận exception chính/suppressed, thay vì chỉ test trường hợp thành công.

## 15. Checklist triển khai trong ứng dụng

- [ ] Tệp tạm được tạo bằng `Files.createTempFile` hoặc thư mục tạm bằng `Files.createTempDirectory`.
- [ ] Không hard-code một tên có thể đụng giữa các job.
- [ ] Có một **owner** xác định chịu trách nhiệm dọn file/root.
- [ ] Thư mục tạm do job tự tạo, không phải thư mục chia sẻ cần giữ dữ liệu.
- [ ] Đã dùng `try-with-resources` để đóng stream/channel/reader/writer đúng lúc.
- [ ] Đã xử lý `finally` hoặc `AutoCloseable.close()` để xóa file tạm.
- [ ] Với cây thư mục, đã xóa từ tệp con đến thư mục cha.
- [ ] Không đi theo symbolic link tùy tiện khi cleanup.
- [ ] Xóa thất bại được báo/ghi nhận; không âm thầm bỏ qua.
- [ ] Nếu công việc và cleanup cùng lỗi, exception chính vẫn được giữ.
- [ ] Không dựa vào `deleteOnExit()` như cleanup chính.
- [ ] Nếu dùng `DELETE_ON_CLOSE`, đã kiểm tra giới hạn provider và việc file có cần dùng sau khi đóng không.
- [ ] Đã xét permissions, thông tin nhạy cảm, quota và dữ liệu còn lại khi JVM crash.
- [ ] Đã test đường thành công, lỗi nghiệp vụ, lỗi cleanup và cây nested.
- [ ] Nếu dùng JUnit Jupiter, đã phân biệt `@TempDir` của framework với cleanup ứng dụng.
- [ ] Không xóa nhầm tệp và thư mục ngoài phạm vi mà ứng dụng sở hữu.

## 16. Kết luận và tài liệu chính thức còn hiệu lực

**Tạo tệp tạm bằng `Files` chỉ giải quyết bài toán tạo tên và file mới an toàn hơn cách tự đoán tên. Quản lý dọn dẹp là một trách nhiệm riêng phải được thiết kế chủ động.**

Với **một file**, `try/finally` cộng `Files.deleteIfExists` thường đủ rõ. Với **một workspace gồm nhiều file/thư mục**, dùng root riêng và `Files.walkFileTree` xóa từ con lên cha. Để giữ exception chính nếu cleanup cũng thất bại, có thể gói workspace thành `AutoCloseable` và dùng `try-with-resources`. Không nhầm **đóng stream** với **xóa file**, không xóa thư mục chia sẻ, và không dựa vào `deleteOnExit` hay `DELETE_ON_CLOSE` như một bảo đảm tuyệt đối.

Tài liệu chuẩn:

- [Java SE 17 API — `java.nio.file.Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `createTempFile`, `createTempDirectory`, `delete`, `deleteIfExists`, `walkFileTree`.
- [Java SE 17 API — `SimpleFileVisitor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SimpleFileVisitor.html): `visitFile`, `postVisitDirectory`, xử lý lỗi traversal.
- [Java SE 17 API — `StandardOpenOption.DELETE_ON_CLOSE`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): cơ chế best-effort và giới hạn áp dụng.
- [Java SE 17 API — `java.io.File.deleteOnExit`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/File.html#deleteOnExit()): yêu cầu xóa khi JVM kết thúc và các giới hạn.
- [Java SE 17 API — `AutoCloseable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng `close()`, xử lý ngoại lệ trong `try-with-resources`.
- [Dev.java — Walking the File Tree](https://dev.java/learn/api/io/java-io/file-system/walking-tree/): hướng dẫn visitor để xử lý tệp con và thư mục cha.
- [JUnit Jupiter User Guide — `@TempDir`](https://docs.junit.org/current/user-guide/#writing-tests-built-in-extensions-TempDirectory): cơ chế thư mục tạm trong test khi dự án có JUnit Jupiter.