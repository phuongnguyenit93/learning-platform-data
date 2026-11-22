# Duyệt cây tệp trong Java: Thiết kế tìm kiếm, thống kê và sao chép cây thư mục

## 1. Bài toán: một cây thư mục, ba nhiệm vụ khác nhau

Giả sử một công cụ Java cần duyệt thư mục dự án để:

1. **Tìm kiếm:** liệt kê các tệp Markdown (`.md`) hoặc một loại tệp phù hợp điều kiện.
2. **Thống kê:** đếm thư mục, tệp, liên kết tượng trưng và cộng tổng kích thước logic.
3. **Sao chép:** tạo một bản sao cấu trúc thư mục, nội dung các file và giữ lại các thư mục rỗng ở một vị trí mới.

Ba nhiệm vụ dùng chung một nền tảng là **duyệt cây tệp**, nhưng cần phân biệt trách nhiệm:

```text
                   Thư mục nguồn (Path)
                            |
              +-------------+-------------+
              |                           |
        Đọc thông tin                  Thay đổi dữ liệu
              |                           |
       walkFileTree(...)             walkFileTree(...)
              |                           |
       preVisitDirectory             preVisitDirectory
       visitFile                     visitFile
       visitFileFailed               postVisitDirectory
              |                           |
      +-------+-------+             Sao chép các mục
      |               |             và metadata cần thiết
    Tìm kiếm        Thống kê                  |
      |               |                  Kiểm tra bản sao
      +-------+-------+
              |
       Báo cáo kết quả
```

Với Java 17+, các API chuẩn được dùng:

- `java.nio.file.Path`: đại diện đường dẫn theo filesystem.
- `java.nio.file.Files`: đọc thuộc tính, duyệt cây, tạo thư mục, sao chép và so sánh tệp.
- `Files.walkFileTree`: duyệt cây theo cơ chế visitor.
- `SimpleFileVisitor<Path>`: triển khai callback mà không phải viết toàn bộ `FileVisitor`.
- `BasicFileAttributes`: thông tin loại tệp, kích thước và thời điểm.
- `PathMatcher`: so khớp tên/path theo `glob` hoặc `regex`.
- `StandardCopyOption.COPY_ATTRIBUTES` và `LinkOption.NOFOLLOW_LINKS`: kiểm soát mục tiêu sao chép ở mức API.
- `Files.mismatch` (Java 12+): so nội dung byte của hai file.

Các API duyệt/copy cơ bản thuộc NIO.2 từ Java 7 và **vẫn còn dùng hiện nay**. Ví dụ độc lập ở bài này dùng **JDK 17+**, vì có `Path.of`, `Files.writeString`, `Files.mismatch` và các tiện ích mới hơn.

**Điểm cần nhớ:** Thống kê thành công không tự bảo đảm đã sao chép thành công; sao chép thành công ở mức API không tự bảo đảm dữ liệu là một snapshot nhất quán; tìm thấy tên file không tự đồng nghĩa caller có quyền mở file. Thiết kế tốt phân tách rõ từng loại bảo đảm.

## 2. Bắt đầu bằng hợp đồng đầu vào và kết quả

Trước khi viết vòng lặp duyệt cây, hãy xác định các câu hỏi sau.

| Quyết định | Câu hỏi cần trả lời | Ví dụ cho bài thực hành |
| --- | --- | --- |
| **Nguồn** | Duyệt cây từ path nào? Có phải thư mục thật? | Thư mục `source` vừa tạo |
| **Độ sâu** | Chỉ một cấp hay đi hết cây? | Đi hết cây |
| **Kiểu tệp** | Tính cả symlink, file đặc biệt không? | Đếm symlink riêng, không tính vào regular files |
| **Tìm kiếm** | Lọc tên cuối hay đường dẫn tương đối? | `glob:*.md` trên `getFileName()` |
| **Thống kê** | Tính thư mục gốc vào số lượng không? | **Có**, tính cả root |
| **Kích thước** | Tổng byte logic hay dung lượng đĩa cấp phát? | Tổng `BasicFileAttributes.size()` của regular files |
| **Sao chép** | Copy cây đầy đủ hay chỉ các file phù hợp bộ lọc? | Copy mọi regular file và mọi thư mục |
| **Symbolic link** | Follow, giữ link hay từ chối? | Không follow; thống kê link; **từ chối link khi copy** |
| **Đích** | Đã tồn tại chưa, có được ghi đè không? | Phải **chưa tồn tại** |
| **Lỗi** | Bỏ qua file không đọc được hay dừng? | Dừng và báo lỗi, tránh kết quả “đầy đủ” giả |
| **Xác minh** | Đếm số entry, so nội dung hay metadata? | So số entry, kích thước và bytes của từng file |
| **Dọn dẹp** | Ai xóa dữ liệu tạm/đích bị tạo dở? | Trong demo, chỉ xóa workspace riêng do chương trình tạo |

Hợp đồng cụ thể làm chương trình dễ kiểm thử. Ví dụ nếu một công cụ backup yêu cầu **giữ symbolic links**, không thể chỉ đổi một dòng trong visitor thành `Files.copy` tùy ý rồi coi mọi tình huống đã được giải quyết. Phải quyết định ý nghĩa target của link, vòng lặp, symlink vượt root và khả năng filesystem đích.

### 2.1. Mô hình cây dùng trong bài

```text
source/
├── README.md              6 byte: "Readme"
├── docs/
│   ├── intro.md           5 byte: "Intro"
│   └── guides/
│       ├── setup.md       5 byte: "Setup"
│       └── draft.txt      5 byte: "Draft"
├── assets/
│   └── logo.png           4 byte: 01 02 03 04
└── empty/
    (không có tệp nào)
```

Nếu **đếm cả root**, tổng số:

- **5 thư mục:** `source`, `docs`, `guides`, `assets` và `empty`.
- **5 tệp thường:** `README.md`, `intro.md`, `setup.md`, `draft.txt`, `logo.png`.
- **25 byte logic:** `6+5+5+5+4`.
- **3 tệp Markdown:** `README.md`, `docs/intro.md` và `docs/guides/setup.md`.

Thư mục rỗng `empty` đặc biệt quan trọng: một hàm copy chỉ duyệt file mà không xử lý thư mục sẽ **bỏ mất nó**.

## 3. Tại sao chọn `Files.walkFileTree`?

`Files.walkFileTree(start, visitor)` là API phù hợp khi cần **sự kiện theo cấu trúc cây**, đặc biệt trong việc sao chép nơi **thư mục phải được tạo trước file con** và có thể phải áp metadata thư mục **sau khi đã tạo nội dung**.

Luồng callback cơ bản:

```text
preVisitDirectory(source)
    preVisitDirectory(source/docs)
        visitFile(source/docs/intro.md)
        preVisitDirectory(source/docs/guides)
            visitFile(source/docs/guides/setup.md)
            visitFile(source/docs/guides/draft.txt)
        postVisitDirectory(source/docs/guides)
    postVisitDirectory(source/docs)
    preVisitDirectory(source/assets)
        visitFile(source/assets/logo.png)
    postVisitDirectory(source/assets)
    preVisitDirectory(source/empty)
    postVisitDirectory(source/empty)
    visitFile(source/README.md)
postVisitDirectory(source)
```

Đây là **một thứ tự minh họa**, không phải bảo đảm tên được duyệt theo thứ tự trong filesystem. Các API traversal không hứa mỗi hệ điều hành luôn trả tên theo cùng thứ tự.

Bốn callback của `FileVisitor`:

| Callback | Khi nào chạy? | Dùng cho mục tiêu nào? |
| --- | --- | --- |
| `preVisitDirectory(dir, attrs)` | Trước khi đi vào các entry của thư mục | Đếm thư mục, tạo thư mục đích, quyết định bỏ nhánh |
| `visitFile(file, attrs)` | Khi thăm một mục file/link không phải directory được duyệt vào | Lọc tên, cộng số byte, copy regular file |
| `visitFileFailed(file, exc)` | Khi không thể truy cập một mục | Dừng, ghi lỗi hoặc xử lý theo chính sách |
| `postVisitDirectory(dir, exc)` | Sau khi thăm các entry con của thư mục | Xóa thư mục sau con, cập nhật timestamp thư mục sau copy |

`SimpleFileVisitor<Path>` cung cấp cách triển khai mặc định; chỉ override các callback cần thiết. Mặc định, nó **ném lại lỗi I/O** khi không thể thăm file hoặc khi traversal thư mục thất bại, giúp tránh kết quả thành công giả.

### 3.1. Hai cách nhìn về một cây

**Duyệt để quan sát** có thể tích lũy kết quả mà không thay đổi filesystem:

```java
Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
    @Override
    public FileVisitResult visitFile(
            Path file, BasicFileAttributes attrs) {

        if (attrs.isRegularFile()) {
            System.out.println(file);
        }
        return FileVisitResult.CONTINUE;
    }
});
```

Đây là đoạn minh họa trong phương thức `throws IOException`, với `root` đã khai báo và import `java.nio.file.*` cùng `BasicFileAttributes`.

**Duyệt để copy** phải tạo thư mục đích trong `preVisitDirectory` và copy regular file trong `visitFile`. Chỉ có `Files.copy(sourceDirectory, targetDirectory)` **không tự đệ quy**: nếu source là directory, lời gọi đơn chỉ tạo directory đích rỗng.

### 3.2. Các kết quả điều khiển traversal

`FileVisitResult` có các giá trị:

- `CONTINUE`: tiếp tục duyệt bình thường.
- `SKIP_SUBTREE`: bỏ qua các entry bên trong thư mục hiện tại (hữu ích tại `preVisitDirectory`).
- `SKIP_SIBLINGS`: bỏ qua những entry cùng cấp chưa được thăm tiếp.
- `TERMINATE`: kết thúc traversal.

Ví dụ tìm tệp và dừng khi gặp một điều kiện có thể dùng `TERMINATE`. Nhưng khi **thống kê toàn bộ cây** hoặc **copy đầy đủ**, không nên dừng sớm: kết quả sẽ thiếu entry. Nếu cố ý bỏ nhánh `build` thì phải ghi rõ thống kê là **chỉ phần được duyệt**, không phải tất cả dữ liệu trong root.

## 4. Thiết kế tìm kiếm: chỉ chọn tên file hay cả vị trí trong cây?

### 4.1. `PathMatcher` cho file extension

Để tìm mọi tên kết thúc bằng `.md`:

```java
PathMatcher markdown = root.getFileSystem()
        .getPathMatcher("glob:*.md");
```

Với visitor:

```java
@Override
public FileVisitResult visitFile(
        Path file, BasicFileAttributes attrs) {

    if (attrs.isRegularFile()
            && markdown.matches(file.getFileName())) {
        System.out.println(root.relativize(file));
    }
    return FileVisitResult.CONTINUE;
}
```

Đây là **mã minh họa thuộc một lớp visitor**, với `markdown` và `root` có sẵn.

Tại sao dùng `file.getFileName()`?

- `glob:*.md` chọn một **tên file**, không tự vượt dấu phân cách thư mục.
- `file` mà visitor nhận thường có đường dẫn gồm root và nhiều thư mục cha.
- Nếu so cả `file` bằng `glob:*.md`, tệp trong nhánh sâu có thể **không khớp** dù tên cuối là `setup.md`.

`PathMatcher` chỉ kiểm tra mẫu trên `Path`; nó **không tự đi tìm file**. Việc tìm kiếm được hình thành bằng **traversal + predicate/matcher**.

### 4.2. Muốn lọc theo nhánh thư mục

Khi điều kiện là “tất cả file Markdown trong `docs`”, có thể:

1. Duyệt cây từ `root.resolve("docs")` nếu đó là phạm vi được phép và thật sự tồn tại.
2. Hoặc so `root.relativize(file)` với một mẫu mô tả đường dẫn tương đối.

```java
Path relative = root.relativize(file);
// Ví dụ: docs/guides/setup.md
```

Đừng suy rằng pattern trên **tên cuối** biết file thuộc `docs` hay `assets`. Nếu chỉ cần đuôi file, khớp tên cuối thường dễ duy trì hơn; nếu cần ngữ cảnh thư mục, chọn relative path và kiểm tra quy tắc dấu phân cách của provider.

### 4.3. Lưu kết quả dưới dạng tương đối

```java
String shown = root.relativize(file).toString();
```

Lưu các tên đường dẫn tương đối thay vì absolute path giúp output không phụ thuộc thư mục tạm ngẫu nhiên hoặc đường dẫn máy người phát triển. Nhưng `Path.toString()` có thể dùng `\` trên Windows và `/` trên Unix.

Ví dụ độc lập trong bài chỉ chuyển dấu phân cách sang `/` **để in kết quả có thể so sánh được**, không dùng chuỗi đã thay dấu để mở/ghi file. Trong ứng dụng thật hãy giữ `Path` làm kiểu dữ liệu thao tác filesystem.

### 4.4. Kết quả có thứ tự ổn định

`walkFileTree` không hứa trả mục theo thứ tự chữ cái. Nếu giao diện, báo cáo hoặc test cần thứ tự:

```java
Collections.sort(relativeNames);
```

đối với `List<String>` đã chuyển sang quy ước hiển thị nhất quán. Không nên dùng thứ tự traversal tự nhiên để đưa ra giả định về “file đầu tiên” trên mọi máy.

Với cây cực lớn, việc gom toàn bộ tên vào `List` để sort có thể tốn bộ nhớ. Nếu không cần thứ tự, phát hiện và xử lý ngay trong visitor thường nhẹ hơn.

## 5. Thống kê: định nghĩa rõ “số file” và “tổng byte”

### 5.1. Đếm thư mục trong `preVisitDirectory`

```java
long directories = 0L;

// Trong preVisitDirectory:
// directories++;
```

Đây là mã minh họa; biến cần nằm trong object giữ trạng thái hoặc một lớp visitor có thể thay đổi nó.

Với hợp đồng của bài này, **thư mục gốc cũng được đếm**. Nếu một công cụ chỉ muốn đếm **thư mục con**, có thể trừ 1 sau traversal đã thành công, hoặc chỉ đếm khi `!dir.equals(root)`. Đừng thay đổi định nghĩa im lặng giữa các báo cáo.

### 5.2. Đếm regular files trong `visitFile`

`BasicFileAttributes` cung cấp `isRegularFile()`, `isDirectory()`, `isSymbolicLink()`, `isOther()` và `size()`.

```java
if (attrs.isRegularFile()) {
    files++;
    totalBytes = Math.addExact(totalBytes, attrs.size());
} else if (attrs.isSymbolicLink()) {
    links++;
}
```

Đoạn code ở trong callback visitor, các biến đã có trong đối tượng thống kê.

**Số file thường không đồng nghĩa số entry:** một symbolic link có thể xuất hiện như một entry riêng mà không được tính vào `files`. File đặc biệt như socket/FIFO (nếu provider có) cũng không nhất thiết là regular file. Mọi nhóm cần chính sách thống kê rõ ràng.

### 5.3. `attrs.size()` là số byte logic, không phải dung lượng vật lý

`BasicFileAttributes.size()` trả về kích thước theo ngữ nghĩa thuộc tính cơ bản của file. Với regular file, nó thường là kích thước **logic** bằng byte.

Nó không bảo đảm:

- Số byte vật lý được cấp phát trên ổ cứng.
- Số block thực sự chiếm trên filesystem.
- Dung lượng của file nén/sparse file khi tính theo phân bổ.
- Dung lượng backup thực tế sau khi nén.
- Một ảnh chụp bất biến nếu file bị ghi thay đổi trong lúc duyệt.

Vì thế báo cáo nên đặt tên **`totalLogicalBytes`** thay vì mơ hồ như `diskUsage`.

### 5.4. Tránh tràn số khi cộng byte

`attrs.size()` có kiểu `long`. Nếu cộng một cây dữ liệu cực lớn:

```java
totalBytes = Math.addExact(totalBytes, attrs.size());
```

`Math.addExact` ném `ArithmeticException` nếu cộng tràn `long`, tránh giá trị âm bị ghi nhận như tổng hợp lệ. Ứng dụng cần xử lý lỗi tràn theo chính sách, có thể chuyển sang `BigInteger` nếu yêu cầu thực sự vượt phạm vi `long`.

Cũng cần cân nhắc số file và thư mục: dùng `long` thay vì `int` giảm nguy cơ tràn, nhưng không biến phép đếm thành vô hạn.

### 5.5. Hard links và symlinks ảnh hưởng thống kê

- **Hard link:** hai đường dẫn khác nhau có thể trỏ tới cùng nội dung/file thực; visitor thấy hai entry và có thể cộng kích thước hai lần. Cách đếm này có nghĩa **tổng kích thước logic theo tên file**, không nhất thiết là dung lượng vật lý unique.
- **Symbolic link:** nếu không follow, visitor có thể thấy entry symlink với `attrs.isSymbolicLink()` và đếm riêng. Nếu bật `FOLLOW_LINKS`, cây có thể đi ra ngoài root hoặc gặp vòng lặp.
- **File đang bị ghi:** metadata nhận được trong lúc traversal không phải một snapshot đồng thời của toàn bộ cây.

Nếu cần thống kê physical storage chính xác hoặc chỉ đếm unique files, phải định nghĩa thế nào là “unique”, cân nhắc `fileKey()` (có thể `null`) và giới hạn provider, thay vì chỉ cộng `attrs.size()`.

## 6. Thiết kế sao chép: thư mục trước, tệp sau, thuộc tính thư mục cuối

### 6.1. Dùng `root.relativize(file)` để ánh xạ sang đích

Giả sử:

```text
sourceRoot = /workspace/source
targetRoot = /workspace/backup
file       = /workspace/source/docs/guides/setup.md

relative   = docs/guides/setup.md
destination= /workspace/backup/docs/guides/setup.md
```

Dùng API `Path`:

```java
Path relative = sourceRoot.relativize(file);
Path targetFile = targetRoot.resolve(relative);
```

**Không dùng `String.replace(sourceRoot.toString(), targetRoot.toString())` để chuyển đường dẫn.** Đó là thao tác văn bản có thể nhầm các prefix trùng ký tự, separator và provider. `Path.relativize/resolve` mô tả quan hệ thành phần của đường dẫn chính xác hơn.

### 6.2. Tạo thư mục đích ở `preVisitDirectory`

```java
@Override
public FileVisitResult preVisitDirectory(
        Path dir, BasicFileAttributes attrs)
        throws IOException {

    Path mapped = targetRoot.resolve(
            sourceRoot.relativize(dir));

    Files.createDirectory(mapped);
    return FileVisitResult.CONTINUE;
}
```

Đây là **phương thức minh họa** ở trong visitor, với `sourceRoot` và `targetRoot` đã có.

Với root nguồn, `sourceRoot.relativize(sourceRoot)` là empty path nên `mapped` chính là `targetRoot`. Vì vậy `targetRoot` phải **chưa tồn tại** khi thiết kế ví dụ dùng `Files.createDirectory`. Chọn `createDirectory` thay vì luôn `createDirectories` giúp thất bại rõ khi bản sao đích đã có, tránh vô tình trộn các file cũ và mới.

**Vì sao tạo thư mục trước?** Khi visitor gặp `docs/guides/setup.md`, các callback `preVisitDirectory` của `docs` và `guides` đã chạy, nên thư mục cha đích đã tồn tại.

### 6.3. Copy regular file ở `visitFile`

```java
@Override
public FileVisitResult visitFile(
        Path file, BasicFileAttributes attrs)
        throws IOException {

    if (!attrs.isRegularFile()) {
        throw new IOException("Unsupported entry: " + file);
    }

    Path mapped = targetRoot.resolve(
            sourceRoot.relativize(file));

    Files.copy(
            file,
            mapped,
            StandardCopyOption.COPY_ATTRIBUTES,
            LinkOption.NOFOLLOW_LINKS);

    return FileVisitResult.CONTINUE;
}
```

Đây là mã minh họa trong visitor của **ứng dụng chọn chính sách từ chối file đặc biệt và symlink**. `NOFOLLOW_LINKS` nhấn mạnh không follow source symlink; với một link, code từ chối trước khi copy. Hai tùy chọn trên không tự khiến việc copy nguyên tử hoặc portable hoàn toàn.

`COPY_ATTRIBUTES` yêu cầu Java **cố sao chép thuộc tính**; tập thuộc tính thực sự được giữ phụ thuộc source/target stores. Tối thiểu last-modified-time được copy khi cả hai file stores hỗ trợ, nhưng timestamp vẫn có thể mất độ chính xác.

### 6.4. Đặt thời gian thư mục ở `postVisitDirectory`

Nếu bạn đặt timestamp của một thư mục đích **ngay khi nó vừa được tạo**, sau đó ghi các file con, metadata thư mục có thể thay đổi. Nếu nghiệp vụ yêu cầu giữ `lastModifiedTime` của thư mục, làm trong callback **sau khi đã copy entry con**:

```java
@Override
public FileVisitResult postVisitDirectory(
        Path dir, IOException error) throws IOException {

    if (error != null) {
        throw error;
    }

    Path mapped = targetRoot.resolve(
            sourceRoot.relativize(dir));

    Files.setLastModifiedTime(
            mapped,
            Files.getLastModifiedTime(
                    dir, LinkOption.NOFOLLOW_LINKS));

    return FileVisitResult.CONTINUE;
}
```

Đoạn này không cam kết tất cả timestamp/ACL/owner đều giữ. Nếu provider không hỗ trợ hoặc không cho đặt timestamp, Java có thể ném `IOException`. Khi thuộc tính **bắt buộc**, cần đọc lại và so sánh theo độ phân giải được hỗ trợ.

### 6.5. Giữ thư mục rỗng

Một thiết kế chỉ gọi `Files.walk` rồi lọc `Files.isRegularFile` để copy sẽ không tự tạo thư mục `empty`. Với visitor, `preVisitDirectory` vẫn chạy cho `empty` dù không có file con, nên tạo đúng cấu trúc.

Đây là khác biệt quan trọng giữa “copy các file đang tìm thấy” và “copy **cây thư mục**”.

## 7. Không đặt đích copy bên trong cây nguồn

### 7.1. Bẫy sao chép `source` sang `source/backup`

Sai về thiết kế:

```text
source/
├── docs/
└── backup/       ← target nằm ngay trong source!
```

Khi traversal đang chạy và code tạo `backup`, thư mục này có thể được thăm như một phần của **source tree**, dẫn tới việc chương trình copy cả bản sao vừa tạo: `backup/backup/...`. Hậu quả có thể là lặp, tăng dung lượng ngoài ý muốn hoặc lỗi I/O.

Trước khi copy có thể kiểm tra từ vựng (*lexical*):

```java
Path from = source.toAbsolutePath().normalize();
Path to = destination.toAbsolutePath().normalize();

if (to.startsWith(from)) {
    throw new IllegalArgumentException(
            "Destination cannot be inside source");
}
```

**Lưu ý quan trọng:** đây chỉ là kiểm tra **cấu trúc tên path**. Nó không ngăn mọi trường hợp symlink, mount alias, hard link hoặc thay đổi filesystem đồng thời. Một ứng dụng nhận đường dẫn không tin cậy cần chính sách root, quyền, xử lý symlink và race riêng; không xem `startsWith` là một sandbox hoàn chỉnh.

### 7.2. Trường hợp target đã tồn tại

Trong ví dụ thực hành, target là một tên mới không tồn tại. `Files.createDirectory(target)` thất bại nếu target đã có; `Files.copy` cho file không dùng `REPLACE_EXISTING` nên tránh tự ghi đè file cũ.

Với chức năng đồng bộ hoặc incremental backup, chính sách khác có thể cho phép target tồn tại. Khi đó phải định nghĩa:

- Ghi đè file nào và giữ file nào?
- Xóa file cũ ở target không còn trong source hay không?
- Khi copy bị lỗi giữa chừng thì rollback ra sao?
- Có copy ACL/owner/timestamp hay không?
- Nếu source/target chứa symlink thì tính thế nào?
- Làm sao tránh copy một cây vào chính nó qua đường dẫn alias?

Đừng chỉ đổi `Files.createDirectory` thành `Files.createDirectories` rồi nghĩ đã có một chương trình sync hoàn chỉnh.

## 8. Chính sách symbolic link và file đặc biệt

### 8.1. Mặc định `walkFileTree` không follow symlink

Với overload đơn giản:

```java
Files.walkFileTree(root, visitor);
```

không truyền `FileVisitOption.FOLLOW_LINKS`, traversal **không tự đi theo symbolic links** đến những thư mục ngoài như một cây con. Với một symlink, `visitFile` có thể nhận `BasicFileAttributes.isSymbolicLink() == true`.

Chính sách trong chương trình:

- Trong bước **thống kê**, regular file được đếm riêng; symbolic link tăng `links`.
- Trong bước **sao chép**, nếu gặp bất kỳ entry nào không phải regular file bên trong `visitFile`, code **báo lỗi và dừng**. Vì thế chương trình không âm thầm copy theo symlink và không âm thầm bỏ mất link trong bản sao.
- Source root phải là **một thư mục thật**, không phải symlink tới directory (kiểm tra `Files.isDirectory(root, NOFOLLOW_LINKS)`).

Đây là lựa chọn chủ ý cho bài học, **không phải một chính sách bắt buộc của mọi chương trình sao chép**.

### 8.2. Ba chính sách có thể chọn

| Chính sách | Ý nghĩa | Cần chú ý |
| --- | --- | --- |
| Không follow, **từ chối** symlink | Backup chỉ khi source tree là regular files + directories | Rõ ràng, tránh mất dữ liệu âm thầm |
| Không follow, **copy chính link** | Giữ bản thân entry link nếu provider hỗ trợ | Target tương đối của link có thể đổi nghĩa khi tới vị trí mới |
| **FOLLOW_LINKS** | Duyệt theo đích của symlink | Nguy cơ vòng lặp, đi ngoài root, duyệt trùng nội dung, race |

Để copy chính link, `Files.copy(sourceLink, targetLink, LinkOption.NOFOLLOW_LINKS)` là API liên quan, nhưng vẫn phụ thuộc provider; copy metadata của link có thể không được hỗ trợ đầy đủ. Với app lưu trữ lâu dài, phải xác định liệu link target tương đối có còn hợp lệ ở vị trí mới hay không.

### 8.3. Tránh khẳng định “không follow” là bảo mật tuyệt đối

Ngay cả khi không follow link trong traversal, source hoặc thành phần path có thể bị thay thế bởi một tiến trình khác giữa lúc đọc attributes và lúc copy. Kiểm tra lexical và `NOFOLLOW_LINKS` không phải một sandbox có khả năng chống mọi race.

Cần xem xét filesystem permissions, thư mục do app sở hữu, ranh giới người dùng và API chuyên biệt như `SecureDirectoryStream` khi provider hỗ trợ nếu mô hình an ninh thực sự cần chống path manipulation.

## 9. Xử lý lỗi: đừng trả thống kê/sao chép “đầy đủ” nếu đã bỏ sót entry

### 9.1. Những loại lỗi thường gặp

| Lỗi | Có thể xuất hiện khi | Hướng xử lý |
| --- | --- | --- |
| `NoSuchFileException` | File/thư mục biến mất trong lúc quét | Báo lỗi hoặc đánh dấu bản quét không hoàn chỉnh |
| `AccessDeniedException` | Thiếu quyền đọc/ghi | Theo chính sách bảo mật; không tự bỏ qua và báo thành công |
| `FileAlreadyExistsException` | Target đã có dù thiết kế yêu cầu mới | Dừng, không ghi đè |
| `DirectoryNotEmptyException` | Xóa/ghi đè thư mục không rỗng | Không tự xóa dữ liệu ngoài quyền sở hữu |
| `FileSystemLoopException` | Đi theo symlink và phát hiện chu trình | Dừng/bỏ link theo chính sách |
| `IOException` | Bất kỳ lỗi I/O, hết quota, read/write lỗi | Giữ nguyên nguyên nhân và trạng thái bản sao |
| `ArithmeticException` | Tổng số byte vượt phạm vi `long` với `addExact` | Không xuất thống kê sai |
| `UnsupportedOperationException` | Provider không hỗ trợ tùy chọn/thuộc tính | Báo không hỗ trợ hoặc fallback đã được thiết kế |

Mỗi exception có thể khác theo filesystem/provider và bối cảnh. Không hard-code chỉ một subclass là “tất cả các lỗi sao chép”.

### 9.2. `visitFileFailed` nên được quyết định rõ

Ví dụ dừng:

```java
@Override
public FileVisitResult visitFileFailed(
        Path file, IOException error) throws IOException {
    throw error;
}
```

Nếu nghiệp vụ cho phép bỏ qua một file, bạn có thể ghi lại nó và trả `CONTINUE`; **nhưng báo cáo phải có số lượng/lý do bỏ qua** và đánh dấu rằng bản sao hoặc thống kê **không đầy đủ**. Việc trả `CONTINUE` không biến file lỗi thành file đã được sao chép.

### 9.3. Copy dở dang phải có trách nhiệm cleanup

`Files.copy` **không phải thao tác nguyên tử**. Nếu copy file thứ tư thất bại, ba file đầu và một số thư mục có thể đã tồn tại ở target. Chương trình ví dụ dùng workspace tạm riêng nên cả `source` và `backup` sẽ được xóa khi thử nghiệm kết thúc, kể cả khi copy lỗi trong khối `try`.

Trong ứng dụng thực:

- Nếu target phải được công bố như một bản sao hoàn chỉnh, hãy copy vào **staging directory** do app sở hữu.
- Chỉ publish khi đã kiểm tra cấu trúc, nội dung và các thuộc tính bắt buộc.
- Nếu thất bại, có kế hoạch dọn staging; không nhầm bản sao chưa hoàn chỉnh với kết quả thành công.
- Nếu cleanup cũng thất bại, giữ lỗi gốc và xử lý thêm lỗi dọn dẹp (ví dụ qua suppressed exceptions hoặc policy rõ).
- Không tự động xóa cả một thư mục người dùng chỉ vì copy thất bại; chỉ dọn **cây do công việc tạo và sở hữu**.

## 10. Kiểm tra bản sao: số lượng, cấu trúc, nội dung và thuộc tính

Sao chép xong chỉ là bước đầu; ứng dụng có thể cần **verification**.

### 10.1. Cùng số lượng entry và bytes

```java
boolean sameNumbers =
        before.directories == after.directories
        && before.files == after.files
        && before.bytes == after.bytes;
```

Đây là đoạn minh họa, với hai đối tượng chứa kết quả thống kê.

Điều kiện này hữu ích nhưng **không đủ chứng minh nội dung giống nhau**: hai file có thể có cùng kích thước mà bytes khác; các tên tệp cũng có thể khác nhưng số lượng bằng nhau.

### 10.2. Xác minh các đường dẫn tương đối

Duyệt source lần nữa, với mỗi tệp:

```java
Path relative = sourceRoot.relativize(file);
Path copiedFile = targetRoot.resolve(relative);
```

Với thư mục, kiểm tra `Files.isDirectory(copiedDirectory, NOFOLLOW_LINKS)`. Với regular file, kiểm tra đích cùng loại và bytes.

### 10.3. `Files.mismatch` so byte

Từ Java 12, `Files.mismatch(a,b)` trả:

- `-1L` nếu hai file không có byte nào khác nhau.
- Vị trí byte đầu tiên khác nhau nếu có khác biệt.

```java
boolean sameBytes =
        Files.mismatch(sourceFile, copiedFile) == -1L;
```

Đây là **mã minh họa** với các biến `Path` đã khai báo và xử lý `IOException`.

Không nên chỉ dùng `Files.size` cho toàn vẹn nội dung. Đối với file rất lớn, `Files.mismatch` tránh phải gọi `Files.readAllBytes` để giữ toàn bộ file trong RAM. Nếu hệ thống cần checksum manifest, có thể dùng `MessageDigest` theo hợp đồng, nhưng checksum cũng không tự kiểm tra ACL hoặc symlink.

### 10.4. Metadata cần xác minh riêng

`StandardCopyOption.COPY_ATTRIBUTES` chỉ **cố** sao chép thuộc tính; tập thực tế phụ thuộc provider. Nếu cần giữ `lastModifiedTime` của cả file và directory, hãy kiểm tra sau copy và xét độ phân giải. Nếu cần quyền POSIX, DOS, ACL hoặc ownership, phải kiểm tra attribute views của source/target theo contract. Không dùng `sameContents=true` để khẳng định cả metadata cũng giống.

### 10.5. Source biến đổi đồng thời gây lệch kết quả

Ví dụ thống kê source lúc 10:00, copy lúc 10:01 và kiểm tra lúc 10:02. Nếu người khác thêm hoặc sửa file ở 10:01:30, **ba lần quét có thể mô tả ba trạng thái khác nhau**.

`walkFileTree` không phải snapshot toàn cục. Nếu nghiệp vụ cần backup nhất quán, phải phối hợp lock, snapshot của filesystem/storage hoặc cơ chế ghi dữ liệu có version phù hợp. Một bản copy “đã duyệt đủ entry nhìn thấy” không tự là một snapshot giao dịch.

## 11. Ví dụ Java 17+ độc lập: tìm kiếm, thống kê, copy và xác minh

Chương trình dưới đây tạo một cây tệp nhỏ hoàn toàn **trong thư mục tạm riêng do nó sở hữu**. Nó không xóa hay ghi đè thư mục của người dùng.

Ý đồ thiết kế:

1. `inventory` dùng visitor để **đếm 5 thư mục, 5 regular files, 25 bytes** và chọn các filename khớp `glob:*.md`.
2. `copyTree` tạo thư mục đích trong `preVisitDirectory`, copy file trong `visitFile`, rồi phục hồi `lastModifiedTime` của thư mục đích ở `postVisitDirectory`.
3. `sameContents` duyệt lại source, ánh xạ sang target và dùng `Files.mismatch` để so bytes.
4. `copyTree` từ chối target nằm trong source ở mức lexical, phòng lỗi dễ gặp nhất khi target tạo lồng bên trong cây đang quét.
5. `deleteTree` dọn đúng workspace của demo sau khi chạy. Nếu bất kỳ bước nào ném exception, khối `finally` vẫn cố thực hiện dọn dẹp.
6. Các dòng in ra không chứa path ngẫu nhiên hoặc separator phụ thuộc hệ điều hành.

Tạo tệp **`TreeSearchStatsCopyDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.*;

public final class TreeSearchStatsCopyDemo {

    static final class Inventory {
        long directories;
        long files;
        long bytes;
        long links;
        final List<String> markdown = new ArrayList<>();
    }

    static String display(Path path) {
        return path.toString().replace('\\', '/');
    }

    static Inventory inventory(Path root, PathMatcher markdown)
            throws IOException {

        Inventory result = new Inventory();

        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {

            @Override
            public FileVisitResult preVisitDirectory(
                    Path dir, BasicFileAttributes attrs) {
                result.directories++;
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attrs) {

                if (attrs.isRegularFile()) {
                    result.files++;
                    result.bytes = Math.addExact(
                            result.bytes, attrs.size());

                    if (markdown.matches(file.getFileName())) {
                        result.markdown.add(
                                display(root.relativize(file)));
                    }
                } else if (attrs.isSymbolicLink()) {
                    result.links++;
                }

                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult visitFileFailed(
                    Path file, IOException cause) throws IOException {
                throw cause;
            }
        });

        Collections.sort(result.markdown);
        return result;
    }

    static void copyTree(Path source, Path destination)
            throws IOException {

        Path from = source.toAbsolutePath().normalize();
        Path to = destination.toAbsolutePath().normalize();

        if (!Files.isDirectory(
                from, LinkOption.NOFOLLOW_LINKS)) {
            throw new IllegalArgumentException(
                    "Source must be a real directory");
        }

        if (to.startsWith(from)) {
            throw new IllegalArgumentException(
                    "Destination cannot be inside source");
        }

        Files.walkFileTree(from, new SimpleFileVisitor<Path>() {

            @Override
            public FileVisitResult preVisitDirectory(
                    Path dir, BasicFileAttributes attrs)
                    throws IOException {

                Files.createDirectory(
                        to.resolve(from.relativize(dir)));

                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attrs)
                    throws IOException {

                if (!attrs.isRegularFile()) {
                    throw new IOException(
                            "Unsupported source entry: " + file);
                }

                Files.copy(
                        file,
                        to.resolve(from.relativize(file)),
                        StandardCopyOption.COPY_ATTRIBUTES,
                        LinkOption.NOFOLLOW_LINKS);

                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult visitFileFailed(
                    Path file, IOException cause)
                    throws IOException {
                throw cause;
            }

            @Override
            public FileVisitResult postVisitDirectory(
                    Path dir, IOException cause)
                    throws IOException {

                if (cause != null) {
                    throw cause;
                }

                Files.setLastModifiedTime(
                        to.resolve(from.relativize(dir)),
                        Files.getLastModifiedTime(
                                dir, LinkOption.NOFOLLOW_LINKS));

                return FileVisitResult.CONTINUE;
            }
        });
    }

    static boolean sameContents(Path source, Path destination)
            throws IOException {

        final boolean[] equal = {true};

        Files.walkFileTree(source, new SimpleFileVisitor<Path>() {

            @Override
            public FileVisitResult preVisitDirectory(
                    Path dir, BasicFileAttributes attrs) {

                if (!Files.isDirectory(
                        destination.resolve(
                                source.relativize(dir)),
                        LinkOption.NOFOLLOW_LINKS)) {
                    equal[0] = false;
                }

                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attrs)
                    throws IOException {

                Path copied = destination.resolve(
                        source.relativize(file));

                if (!attrs.isRegularFile()
                        || !Files.isRegularFile(
                                copied, LinkOption.NOFOLLOW_LINKS)
                        || Files.mismatch(file, copied) != -1L) {
                    equal[0] = false;
                }

                return FileVisitResult.CONTINUE;
            }
        });

        return equal[0];
    }

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
                    Path dir, IOException cause)
                    throws IOException {

                if (cause != null) {
                    throw cause;
                }

                Files.delete(dir);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    static void check(boolean pass, String name) {
        if (!pass) {
            throw new AssertionError(name);
        }
    }

    public static void main(String[] args) throws IOException {
        Path workspace = Files.createTempDirectory("tree-lesson-");

        try {
            Path source = Files.createDirectory(
                    workspace.resolve("source"));

            Path docs = Files.createDirectory(
                    source.resolve("docs"));

            Path guides = Files.createDirectory(
                    docs.resolve("guides"));

            Path assets = Files.createDirectory(
                    source.resolve("assets"));

            Files.createDirectory(source.resolve("empty"));

            Files.writeString(
                    source.resolve("README.md"),
                    "Readme", StandardCharsets.UTF_8);

            Files.writeString(
                    docs.resolve("intro.md"),
                    "Intro", StandardCharsets.UTF_8);

            Files.writeString(
                    guides.resolve("setup.md"),
                    "Setup", StandardCharsets.UTF_8);

            Files.writeString(
                    guides.resolve("draft.txt"),
                    "Draft", StandardCharsets.UTF_8);

            Files.write(
                    assets.resolve("logo.png"),
                    new byte[]{1, 2, 3, 4});

            PathMatcher markdown = source.getFileSystem()
                    .getPathMatcher("glob:*.md");

            Inventory before = inventory(source, markdown);

            System.out.println(
                    "source.directories=" + before.directories);
            System.out.println(
                    "source.files=" + before.files);
            System.out.println(
                    "source.bytes=" + before.bytes);
            System.out.println(
                    "source.markdown="
                            + String.join(", ", before.markdown));

            Path destination = workspace.resolve("backup");
            copyTree(source, destination);

            Inventory after = inventory(destination, markdown);

            System.out.println(
                    "copied.directories=" + after.directories);
            System.out.println(
                    "copied.files=" + after.files);
            System.out.println(
                    "copied.bytes=" + after.bytes);

            boolean equal = sameContents(source, destination);
            boolean sameSearch =
                    before.markdown.equals(after.markdown);
            boolean emptyDir = Files.isDirectory(
                    destination.resolve("empty"));

            System.out.println(
                    "copied.contentsEqual=" + equal);
            System.out.println(
                    "copied.matchesEqual=" + sameSearch);
            System.out.println(
                    "copied.emptyDir=" + emptyDir);

            boolean rejected = false;

            try {
                copyTree(
                        source,
                        source.resolve("nested-backup"));
            } catch (IllegalArgumentException expected) {
                rejected = true;
            }

            System.out.println(
                    "nestedDestinationRejected=" + rejected);

            check(before.directories == 5
                    && before.files == 5
                    && before.bytes == 25
                    && before.markdown.size() == 3,
                    "inventory source");

            check(after.directories == before.directories
                    && after.files == before.files
                    && after.bytes == before.bytes,
                    "inventory copy");

            check(equal && sameSearch && emptyDir && rejected,
                    "copy verification");

            System.out.println("checks=PASS");
        } finally {
            deleteTree(workspace);
        }

        System.out.println(
                "workspace.cleaned=" + !Files.exists(workspace));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 TreeSearchStatsCopyDemo.java
java TreeSearchStatsCopyDemo
```

**Stdout chính xác đã kiểm thử bằng `javac` và `java` trên JDK 17+:**

```text
source.directories=5
source.files=5
source.bytes=25
source.markdown=README.md, docs/guides/setup.md, docs/intro.md
copied.directories=5
copied.files=5
copied.bytes=25
copied.contentsEqual=true
copied.matchesEqual=true
copied.emptyDir=true
nestedDestinationRejected=true
checks=PASS
workspace.cleaned=true
```

**Phạm vi kết quả:** Chương trình dùng một cây file tự tạo, cùng default filesystem, các file nhỏ không đổi trong lúc chạy, và không tạo symbolic link. Nếu filesystem không cho đặt `lastModifiedTime` hoặc không có quyền tạo/xóa file tạm, thao tác có thể ném `IOException`; đây không phải dấu hiệu Java tự bảo đảm backup thất bại hay thành công trên mọi nhà cung cấp storage.

### 11.1. Đọc kết quả thống kê

- `source.directories=5` tính **cả thư mục root** và cả `empty`.
- `source.files=5` chỉ tính regular files do demo tạo.
- `source.bytes=25` là tổng **kích thước logic** của các regular files, không phải dung lượng cấp phát của filesystem.
- `source.markdown` có 3 tên tệp relative, được sort để stdout ổn định.

### 11.2. Đọc kết quả bản sao

- `copied.directories=5` và `copied.emptyDir=true` xác nhận **thư mục rỗng** không bị mất.
- `copied.files=5` và `copied.bytes=25` xác nhận những thống kê cơ bản giống nhau.
- `copied.contentsEqual=true` được tính bằng cách duyệt nguồn và dùng `Files.mismatch` cho từng regular file ở đường tương ứng.
- `copied.matchesEqual=true` xác nhận danh sách các tệp Markdown tương đối giống nhau.
- `nestedDestinationRejected=true` chứng minh code từ chối destination nằm trong source ở mức lexical.
- `checks=PASS` chỉ được in khi các phép xác nhận trong chương trình đã vượt qua.
- `workspace.cleaned=true` xác nhận workspace tạm của chương trình đã được xóa sau lần chạy thành công.

### 11.3. Vì sao `Inventory` có `links` dù cây demo không có link?

`links` cho phép ứng dụng ghi nhận symlink riêng nếu một cây thật có chúng, ngay cả khi `files` chỉ đếm regular files. Ở ví dụ này, không tạo link để code chạy trên các môi trường không hỗ trợ hoặc không cho quyền tạo symlink.

Một hệ thống production nên **xuất cả `links` và báo cáo loại entry không hỗ trợ** nếu muốn trình bày đầy đủ trạng thái tree; demo tập trung vào số thư mục/file/bytes và search results như đề bài.

### 11.4. Mức độ bảo đảm mà chương trình thực sự cung cấp

Đây là ví dụ **thiết kế thuật toán**, không phải chương trình backup transaction/snapshot hoàn chỉnh. Cụ thể:

- `copyTree` không phải atomic.
- Nếu copy thất bại, target có thể đã được tạo một phần; trong demo, khối `finally` xóa workspace riêng.
- Hàm `sameContents` kiểm tra **cấu trúc source tương ứng và nội dung bytes**, còn `inventory` so các số lượng; nó không kiểm toán tất cả permission/ACL hoặc chống source thay đổi đồng thời.
- Kiểm tra `to.startsWith(from)` không an toàn tuyệt đối trước symlink/path alias hoặc race nếu đường dẫn không tin cậy.
- `COPY_ATTRIBUTES` và `setLastModifiedTime` tùy khả năng provider.

Khi dùng cho backup thực tế, hãy thêm staging, metadata verification, snapshot consistency và chính sách xử lý các entry đặc biệt.

## 12. Khi nào chọn `Files.walk`, `Files.find`, `Files.list` hay `walkFileTree`?

| API | Dùng khi | Điểm cần nhớ |
| --- | --- | --- |
| `Files.list(dir)` | Liệt kê entry **trực tiếp một cấp** | Trả `Stream<Path>` cần đóng; không tự đệ quy |
| `Files.walk(root)` | Duyệt sâu và xử lý stream/filter/map | Có `IOException`/`UncheckedIOException`; stream cần đóng |
| `Files.find(root, maxDepth, matcher)` | Duyệt cây và kiểm tra predicate nhận `Path` + `BasicFileAttributes` | Cần đóng stream; hỗ trợ độ sâu |
| `Files.walkFileTree(root, visitor)` | Cần callback theo cấu trúc, skip subtree, xử lý lỗi chi tiết, copy/delete cây | Visitor trả `FileVisitResult`, không phải stream |
| `Files.newDirectoryStream(dir, glob)` | Duyệt trực tiếp một thư mục với filter tên | Không tự đệ quy; `DirectoryStream` cần đóng |

Nếu bài toán chỉ “in các file `.md`”, `Files.walk(root)` có thể ngắn gọn:

```java
PathMatcher md = root.getFileSystem()
        .getPathMatcher("glob:*.md");

try (var stream = Files.walk(root)) {
    stream.filter(p ->
                    Files.isRegularFile(
                            p, LinkOption.NOFOLLOW_LINKS))
          .filter(p -> md.matches(p.getFileName()))
          .forEach(System.out::println);
}
```

Đây là đoạn **minh họa Java 17+** trong phương thức xử lý `IOException`. `Files.walk` là stream dùng tài nguyên filesystem, nên phải đóng. Nếu một lỗi I/O xảy ra **trong lúc tiêu thụ stream**, có thể thấy `UncheckedIOException`.

Nếu muốn vừa thống kê vừa copy theo đúng thứ tự **thư mục trước/file sau**, `walkFileTree` thuận tiện hơn một pipeline stream tuyến tính. Một visitor cũng có thể đồng thời tích lũy thống kê và copy, nhưng bài tách các lượt cho dễ kiểm chứng, rollback và trình bày trách nhiệm.

### 12.1. Trade-off: một lượt hay nhiều lượt?

**Một lượt** duyệt có thể đồng thời đếm và tìm file:

- Ít thao tác filesystem traversal hơn.
- Thích hợp khi source rất lớn và không cần snapshot riêng.
- Nhưng trộn quá nhiều trách nhiệm có thể làm visitor khó hiểu và khó test.

**Nhiều lượt** như demo:

- `inventory(source)` → `copyTree(source,target)` → `inventory(target)` → `sameContents(source,target)`.
- Dễ chỉ ra kết quả từng giai đoạn và xác minh.
- Tốn nhiều I/O hơn; **không tạo tính nhất quán snapshot** nếu cây thay đổi trong khoảng giữa các lượt.

Chọn theo yêu cầu thực tế: với file lớn, một pipeline có checksum theo lúc copy hoặc storage snapshot có thể phù hợp hơn việc đọc lại toàn bộ data nhiều lần.

## 13. Kiến trúc cho dự án thực tế: tách tìm kiếm, thống kê, sao chép

### 13.1. Tách kiểu kết quả

Một API ứng dụng có thể trả:

```java
record TreeStats(
        long directories,
        long regularFiles,
        long symbolicLinks,
        long totalLogicalBytes) { }
```

Đây là **minh họa Java 17+** (record đã có trong Java 16). Không cần dùng một `Map<String,Object>` không rõ kiểu cho mọi giá trị thống kê nếu mô hình dữ liệu ổn định.

Tìm kiếm có thể trả `List<Path>` tương đối, còn copy có thể trả một báo cáo tách riêng:

```java
record CopyReport(
        long copiedFiles,
        long copiedDirectories,
        boolean verified) { }
```

Không nên chỉ dùng `boolean success` để mô tả nhiều trạng thái như nội dung đã copy, timestamp đã giữ, ACL còn thiếu và một số file bị bỏ qua.

### 13.2. Tách policy khỏi traversal

Trong ứng dụng lớn, những lựa chọn sau nên trở thành **tham số hoặc chiến lược rõ ràng**:

- `Predicate<Path>` chọn file cần tìm.
- Bộ lọc thư mục được phép đi vào.
- Có theo symlink không.
- Có cho file đặc biệt không.
- Có copy metadata không.
- Có overwrite target không.
- Có cố tiếp tục khi một file đọc lỗi không.
- Có giới hạn tổng bytes/file count/depth hay không.
- Có cần sort kết quả hay giữ cơ chế xử lý streaming.
- Cần kiểm tra checksum/ACL/owner ở mức nào.

Những thay đổi này không nhất thiết đòi hỏi nhiều class phức tạp; nhưng chúng cần **được đặt tên và kiểm thử** chứ không nên ẩn trong một visitor làm tất cả mà không có contract.

### 13.3. Mối quan hệ giữa search và copy

Không nên tự động copy **chỉ các file tìm thấy** nếu mục tiêu của người dùng là sao chép **toàn bộ cây**. Nếu thực sự copy theo filter, phải định nghĩa liệu các thư mục chứa file phù hợp có được tạo không, thư mục rỗng có giữ không và quan hệ đường dẫn có giữ không.

Ví dụ copy chỉ `.md`:

```text
source/docs/intro.md      -> target/docs/intro.md
source/docs/guides/setup.md -> target/docs/guides/setup.md
source/assets/logo.png    -> không copy
source/empty/              -> giữ hay bỏ? theo policy
```

Đây là bài toán **selective copy**, không tương đương full tree copy. Trong chương trình mục 11, bộ lọc Markdown chỉ dùng **tìm kiếm**, còn copy vẫn copy **tất cả regular files**.

## 14. Tính nguyên tử và cách publish bản sao

### 14.1. Copy vào staging directory

Đối với ứng dụng dùng bản sao ngay sau khi copy, không nên cho người đọc coi một target đang viết dở là kết quả hoàn chỉnh. Chiến lược có thể là:

```text
source/
   |
   | copy tree
   v
staging-unique/       (chưa công bố)
   |
   | verify content / metadata / size
   v
published-backup/     (chỉ công bố khi đáp ứng contract)
```

Thư mục staging nên nằm trong vùng app sở hữu, có quyền và quota phù hợp. Đích publish phải không gây ghi đè ngoài ý muốn.

### 14.2. `Files.move(..., ATOMIC_MOVE)` có giới hạn

`StandardCopyOption.ATOMIC_MOVE` là option của `Files.move`, **không phải một option bảo đảm copy atomic của `Files.copy`**.

```java
Files.move(
        staging,
        published,
        StandardCopyOption.ATOMIC_MOVE);
```

Đây là mã minh họa với hai `Path` phù hợp. Provider có thể ném `AtomicMoveNotSupportedException`. Khả năng move nguyên tử và việc target đã tồn tại được xử lý ra sao phụ thuộc provider. Với nhiều cây hoặc file stores khác nhau, không có bảo đảm chung rằng có thể thay một cây lớn bằng một thao tác transaction hoàn chỉnh.

**Đừng âm thầm fallback** sang move không atomic nếu hợp đồng bắt buộc atomic publish. Nếu chọn fallback, cần ghi rõ trạng thái và rủi ro cho caller.

### 14.3. Atomicity khác durability và consistency

- **Atomicity:** các bên quan sát không thấy một trạng thái chuyển tiếp mà provider hứa sẽ tránh.
- **Durability:** dữ liệu đã được ghi bền vững trước sự cố nguồn điện/crash.
- **Consistency:** toàn bộ bản copy phản ánh cùng một thời điểm nguồn và giữ những ràng buộc metadata.

Một `ATOMIC_MOVE` thành công **không tự cam kết** mọi mục trên đĩa được fsync theo ý bạn, và một `walkFileTree` không tự tạo snapshot. Backup nghiêm ngặt cần thiết kế riêng cho cả ba khía cạnh này.

## 15. Hiệu năng và giới hạn tài nguyên khi duyệt cây lớn

### 15.1. Độ phức tạp

Với `N` entries trong cây:

- Duyệt `walkFileTree` để đếm/search: khoảng `O(N)` thao tác thăm entry, chưa tính I/O mở nội dung.
- Copy nội dung: tối thiểu phải truyền dữ liệu tỷ lệ **tổng số byte** cần sao chép.
- Verify byte bằng `Files.mismatch`: có thể đọc lại nhiều byte, tốn thêm I/O.
- Sort `M` tên tệp tìm thấy: thường `O(M log M)` và cần bộ nhớ lưu tên.

Không có pattern matcher nào biến việc duyệt cả filesystem thành miễn phí; nếu muốn **không mở** các subtree không liên quan, phải tổ chức traversal cho phép skip từ thư mục cha.

### 15.2. Không giữ tất cả file trong RAM nếu không cần

`walkFileTree` gọi callback theo từng entry nên có thể xử lý file ngay; chỉ lưu danh sách file phù hợp khi ứng dụng cần trả danh sách/sort. Đối với thống kê tổng, chỉ cần vài số `long`, không cần thu `List<Path>` của toàn bộ cây.

Trong demo, danh sách Markdown nhỏ; với hàng triệu kết quả, cần phân trang, ghi kết quả ra sink, stream xử lý hoặc thiết kế chỉ số tìm kiếm thay vì giữ toàn bộ trong heap.

### 15.3. Cân nhắc quota và cancellation

Ứng dụng đọc cây từ nơi không tin cậy có thể gặp:

- Hàng triệu file nhỏ.
- File cực lớn.
- Độ sâu rất lớn.
- Thư mục không đọc được.
- Filesystem mạng chậm hoặc ngắt kết nối.
- Symlink bị thay đổi đồng thời.
- Người dùng hủy tác vụ ở giữa.

Nên có giới hạn **số file/bytes/thời gian/độ sâu** và một cơ chế hủy tác vụ phối hợp với traversal. Khi hủy copy, target tạm có thể bị dở và phải tuân theo policy cleanup.

### 15.4. Tránh bắt lỗi rồi tiếp tục vô điều kiện

Ví dụ `visitFileFailed` chỉ `System.err.println(error)` rồi trả `CONTINUE` có thể phù hợp cho công cụ kiểm tra best-effort, nhưng **không phù hợp** nếu phía gọi yêu cầu chứng minh đã backup tất cả file. Khi bỏ qua lỗi, thống kê phải có trạng thái **partial** và danh sách entry không xử lý được.

## 16. An toàn filesystem: những rủi ro ngoài thuật toán visitor

### 16.1. Không biến tên path thành quyền truy cập

Một path khớp `glob:*.md` không có nghĩa người dùng được phép đọc nội dung tệp đó. Search/filter, authorization và I/O là các bước độc lập.

Không ghép root với một đường dẫn do người dùng cung cấp rồi mở mà chưa kiểm soát absolute path, `..`, symlink và quyền truy cập. `Path.normalize()` chỉ là biến đổi lexical; `Path.startsWith(root)` không bảo vệ đầy đủ trước symlink hoặc race.

### 16.2. Đừng xóa bừa khi rollback

`deleteTree(root)` là thao tác phá hủy dữ liệu. Chỉ dùng trên **thư mục staging do chính job tạo và sở hữu** hoặc trong trường hợp rõ quyền. Không đưa nguyên method từ ví dụ rồi gọi trên `Path.of(".")`, thư mục project hoặc đường do user nhập chỉ vì muốn “dọn dẹp nhanh”.

Chương trình mẫu chỉ gọi `deleteTree(workspace)` với một thư mục tạm mới được `Files.createTempDirectory` tạo.

### 16.3. Chạy nhiều job song song

Hai job copy cùng target có thể tranh nhau tạo tên, overwrite hoặc xóa staging. Nên dùng target/staging riêng, cơ chế phối hợp publish, id nhiệm vụ và chính sách ownership. Việc kiểm tra `Files.exists` trước `Files.createDirectory` không làm hai thao tác trở thành nguyên tử; code cần xử lý tình huống đích xuất hiện giữa các bước.

### 16.4. Không dùng dữ liệu thống kê như quyền hạn xóa

Đếm được 5 file không cho phép chương trình kết luận tất cả đều thuộc job và có thể xóa. Ownership không được suy từ số lượng, tên khớp pattern hoặc việc tệp nằm dưới một path lexical. Nó phải do contract và cơ chế bảo vệ dữ liệu của ứng dụng xác định.

## 17. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Dùng `Files.copy(sourceDir,targetDir)` và tưởng đã copy đệ quy | Target chỉ là thư mục rỗng | `walkFileTree`, tạo thư mục và copy từng file |
| Chỉ copy regular files, không tạo directory | Mất cấu trúc, mất thư mục rỗng | `preVisitDirectory` tạo từng directory |
| Đặt timestamp directory trước khi copy nội dung | Thao tác tạo file có thể thay đổi timestamp | Áp timestamp directory trong `postVisitDirectory` |
| Đưa target vào bên trong source | Có thể copy đích lồng lặp, tăng vô hạn | Chọn target ngoài cây nguồn; kiểm tra và xử lý alias |
| So `glob:*.md` với absolute path nhiều thành phần | Bỏ sót file đúng extension | Match `file.getFileName()` |
| Không quy định đếm cả root hay không | Thống kê lệch 1 thư mục | Ghi rõ định nghĩa và test |
| Gọi size của mọi loại entry như regular file | Số byte vô nghĩa với symlink/file đặc biệt | Kiểm tra `attrs.isRegularFile()` |
| Cộng bytes bằng `int` | Tràn khi file lớn | Dùng `long`, `Math.addExact` nếu cần |
| Coi tổng bytes là dung lượng ổ thực | Sai với sparse file/dedup | Đặt tên `totalLogicalBytes` |
| Quên xử lý `visitFileFailed` | Có thể báo kết quả đầy đủ giả | Dừng hoặc trả partial có báo lỗi |
| Bật `FOLLOW_LINKS` tùy tiện | Có thể đi ngoài root/vòng lặp | Chọn symlink policy trước |
| Copy symlink như file thường mà không xác định mục tiêu | Bản copy thay đổi nghĩa liên kết | Từ chối, giữ link hoặc follow có chủ đích |
| Chỉ so số files và bytes sau copy | Không phát hiện file khác byte hoặc tên sai | Map theo relative path và dùng `Files.mismatch` |
| Cho rằng `COPY_ATTRIBUTES` giữ mọi ACL/quyền | Metadata phụ thuộc file stores | Đọc lại thuộc tính cần thiết |
| Cho rằng copy tree là atomic | Target có thể được tạo dở | Staging, verify, publish |
| Xóa target chung khi copy thất bại | Có thể mất dữ liệu của job/user khác | Chỉ dọn cây do job sở hữu |
| Dựa vào thứ tự của visitor | Test khác giữa OS/provider | Sort khi cần |
| Dùng `Path.toString().replace(...)` để tính đường thật | Có thể phá nghĩa path | Giữ `Path`, chỉ chuẩn hóa hiển thị |
| Xem `walkFileTree` là snapshot nguồn | File có thể thay đổi giữa các callback | Snapshot/locking nếu cần |
| Không có quota/timeouts | Cây lớn khiến chương trình chạy lâu và cạn disk | Giới hạn phạm vi, bytes và hủy tác vụ |

## 18. Bộ kiểm thử nên có trước khi áp dụng vào hệ thống thật

### 18.1. Kiểm thử đường đúng

- Cây chỉ có **root rỗng**: một directory, không file, không bytes.
- Một tệp ở root: kiểm tra tên tương đối không có thư mục cha.
- Nhiều thư mục lồng nhau: kiểm tra relative mapping.
- Một **thư mục rỗng**: vẫn có trong bản sao.
- Tệp .md và .txt: filter chọn đúng extension.
- File có tên bắt đầu dấu chấm: glob Java không tự bỏ hidden dot.
- Tệp dung lượng 0 byte: count là file, bytes không tăng.
- Tệp nhị phân: copy byte trực tiếp, không convert thành `String`.
- Target mới: không ghi đè thư mục có sẵn.

### 18.2. Kiểm thử lỗi và cạnh tranh

- Root nguồn không tồn tại hoặc là file thường.
- Target đã có.
- Target là hậu duệ của source.
- Mục không đọc được, thiếu quyền hoặc biến mất trong quá trình quét.
- Hết dung lượng/quota khi copy.
- Source có symlink và file đặc biệt: kiểm tra policy từ chối/giữ/follow.
- Symlink cycle nếu app cho `FOLLOW_LINKS`.
- Source thay đổi giữa inventory và copy.
- Copy thất bại giữa chừng: xác minh staging được dọn hoặc báo partial.
- Cleanup thất bại: exception gốc và lỗi dọn dẹp được ghi nhận.
- Tên file Unicode, độ sâu lớn, số file nhiều.

### 18.3. Kiểm thử cross-platform

Nếu sản phẩm chạy trên Windows, Linux và filesystem mạng:

- Không assert đường hiển thị có separator cố định nếu chưa chuẩn hóa.
- Kiểm tra khả năng đọc/ghi/copy timestamp trên provider thật.
- Tránh giả định case sensitivity giống nhau.
- Nếu cần copy symlink/ACL/owner, test trên filesystem có hỗ trợ.
- Tách test của demo (chỉ regular files) khỏi integration test của storage thật.
- Không dùng một assertion thành công trên một máy để suy ra mọi provider đều có cùng khả năng.

### 18.4. Xác minh từng mục tiêu riêng

Báo cáo QA tốt nên có:

| Mục tiêu | Kiểm tra |
| --- | --- |
| Tìm kiếm | Danh sách relative paths khớp bộ lọc, sort nếu cần |
| Thống kê | Số dirs/files/links, tổng logical bytes và chính sách các mục bị bỏ qua |
| Sao chép cấu trúc | Tồn tại đúng các directory, kể cả directory rỗng |
| Nội dung | Mỗi file nguồn tương ứng một file đích với bytes giống |
| Metadata | Những timestamp/quyền thật sự bắt buộc, theo khả năng provider |
| Lỗi | Không báo full success sau lỗi đọc/copy |
| Cleanup | Chỉ xóa workspace/staging thuộc quyền sở hữu |
| An toàn | Không copy vào cây nguồn, không đọc ngoài root vì symlink/user input |

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Muốn tìm mọi file `.md` ở mọi độ sâu, `PathMatcher` có tự đi qua thư mục không?  
**Đáp án:** Không. Cần duyệt cây bằng `Files.walk` hoặc `walkFileTree`, rồi kiểm tra `markdown.matches(file.getFileName())` nếu chỉ lọc tên cuối.

**Câu 2.** Vì sao `Files.copy(sourceDir,targetDir)` chưa đủ để backup một cây?  
**Đáp án:** Nếu source là directory, lời gọi đơn chỉ tạo một directory đích rỗng; phải duyệt và copy các entry con.

**Câu 3.** Vì sao `preVisitDirectory` phù hợp tạo thư mục đích?  
**Đáp án:** Nó được gọi trước các entry con, nên khi copy một file lồng sâu, thư mục cha đích đã được tạo.

**Câu 4.** Vì sao `postVisitDirectory` phù hợp khôi phục last-modified-time của directory?  
**Đáp án:** Vì việc tạo file/subdirectory bên trong có thể làm thay đổi timestamp directory; áp sau cùng giúp tránh bị thay ngay bởi thao tác copy tiếp theo.

**Câu 5.** Tổng `BasicFileAttributes.size()` có là dung lượng disk sử dụng thật không?  
**Đáp án:** Không chắc. Nó thể hiện kích thước logic của file theo provider, không bắt buộc phản ánh sparse allocation/deduplication.

**Câu 6.** Một symlink có nên được đếm như regular file?  
**Đáp án:** Tùy hợp đồng; chương trình mẫu không follow symlink, đếm nó riêng `links` và không cộng vào `files`/`bytes`.

**Câu 7.** Nếu source có 5 file và target cũng có 5 file cùng tổng bytes, đã chứng minh backup đúng chưa?  
**Đáp án:** Chưa. Có thể tên hoặc nội dung khác. Cần kiểm tra relative paths và bytes của từng file (ví dụ `Files.mismatch`).

**Câu 8.** Vì sao không đặt target ở `source/backup`?  
**Đáp án:** Traversal có thể gặp chính target mới tạo và copy lặp. Chọn target nằm ngoài cây nguồn; kiểm tra alias/symlink bổ sung nếu input không tin cậy.

**Câu 9.** `walkFileTree` có bảo đảm một snapshot của source khi có người khác ghi file không?  
**Đáp án:** Không. Các callback có thể thấy những trạng thái khác nhau theo thời gian. Backup nhất quán cần snapshot hoặc coordination riêng.

**Câu 10.** `COPY_ATTRIBUTES` có bảo đảm giữ tất cả permission, ACL và timestamps không?  
**Đáp án:** Không. Nó yêu cầu thử copy thuộc tính; tập cụ thể và độ chính xác phụ thuộc file stores. Phải đọc lại những thuộc tính bắt buộc.

**Câu 11.** Nếu một file không đọc được, có nên trả thống kê như thể toàn bộ cây đã quét xong không?  
**Đáp án:** Không. Hoặc dừng báo lỗi, hoặc báo partial với danh sách những mục bị bỏ qua theo policy.

**Câu 12.** `Files.mismatch(a,b) == -1L` kiểm tra điều gì?  
**Đáp án:** Không phát hiện bytes khác nhau giữa hai file được so ở thời điểm kiểm tra; không có nghĩa metadata hoặc trạng thái source luôn bất biến.

## 20. Tổng kết và tài liệu chính thức còn hiệu lực

**Thiết kế tìm kiếm, thống kê và sao chép cây thư mục** nên bắt đầu từ một hợp đồng về root, độ sâu, file types, symlink, lỗi, metadata và ownership. Sau đó:

1. Dùng `walkFileTree` cùng `SimpleFileVisitor` cho callback có cấu trúc rõ.
2. Dùng `PathMatcher` hoặc predicate để tìm kiếm **tên file** hay **relative path** theo ý định.
3. Tích lũy số directories, regular files và tổng logical bytes trong visitor; phân biệt symbolic links và file đặc biệt.
4. Copy cây bằng `preVisitDirectory` tạo thư mục, `visitFile` copy regular file và `postVisitDirectory` cho metadata thư mục cần khôi phục.
5. Map source sang destination bằng `Path.relativize` và `resolve`, không tự sửa chuỗi đường dẫn.
6. Kiểm tra bản sao theo relative paths, số lượng và **bytes**, không suy tính toàn vẹn chỉ từ số file.
7. Xử lý lỗi/partial target, symlink và thay đổi đồng thời; dùng staging/snapshot nếu nghiệp vụ cần.
8. Không coi copy tree tự có tính atomic hoặc mọi metadata được bảo toàn trên tất cả filesystem.

### Tham khảo Oracle và Dev.java

- [Java SE 17 — `Files.walkFileTree`, `Files.copy`, `Files.mismatch` và các phương thức liên quan](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): traversal, sao chép và đối chiếu dữ liệu.
- [Java SE 17 — `SimpleFileVisitor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SimpleFileVisitor.html): các callback `preVisitDirectory`, `visitFile`, `visitFileFailed`, `postVisitDirectory`.
- [Java SE 17 — `FileVisitResult`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitResult.html): `CONTINUE`, `SKIP_SUBTREE`, `SKIP_SIBLINGS`, `TERMINATE`.
- [Java SE 17 — `BasicFileAttributes`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html): loại file và kích thước cơ bản.
- [Java SE 17 — `Path`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `relativize`, `resolve`, `normalize`, `startsWith`.
- [Java SE 17 — `PathMatcher`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/PathMatcher.html) và [`FileSystem.getPathMatcher`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html): glob/regex trên `Path`.
- [Dev.java — Walking the File Tree](https://dev.java/learn/api/io/java-io/file-system/walking-tree/): hướng dẫn visitor và xử lý việc duyệt.
- [Dev.java — Manipulating Files and Directories](https://dev.java/learn/api/io/java-io/file-system/move-copy-delete/): những điều cần lưu ý khi copy/move/delete.
