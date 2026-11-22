# FOLLOW_LINKS và vòng lặp liên kết tượng trưng khi duyệt tệp trong Java

Khi duyệt cây thư mục bằng Java NIO.2, một liên kết tượng trưng (*symbolic link*, thường gọi *symlink*) có thể dẫn tới một tệp, một thư mục khác, hoặc thậm chí dẫn ngược tới **thư mục tổ tiên** của đường đang duyệt. Nếu chương trình tự đệ quy mà không có chiến lược theo dõi liên kết và phát hiện vòng lặp, nó có thể đọc trùng tệp, đi ra ngoài thư mục được phép, chạy rất lâu hoặc đi vào vòng lặp vô hạn.

API hiện hành của `java.nio.file` cung cấp lựa chọn `FileVisitOption.FOLLOW_LINKS` khi duyệt cây qua `Files.walkFileTree`, `Files.walk` hoặc `Files.find`. **Mặc định các phép duyệt này không tự đi theo symbolic links**. Khi bật `FOLLOW_LINKS`, Java có cơ chế nhận biết **chu kỳ trỏ về thư mục tổ tiên** và biểu diễn tình huống đó bằng `FileSystemLoopException`.

Ví dụ cây thư mục:

~~~text
demo/
└── child/
    └── back -> ..

Đường dẫn "demo/child/back" là symbolic link.
Target ".." được hiểu tương đối từ thư mục chứa link: "demo/child".
Do đó back trỏ về "demo", tổ tiên của "child".
~~~

Khi bật `FOLLOW_LINKS` và duyệt từ `demo`, đi vào `child/back` sẽ trỏ trở về `demo`. Đó là **vòng lặp liên kết tượng trưng**. Với `walkFileTree`, Java gọi `visitFileFailed` với `FileSystemLoopException`. Với `Files.walk`, lỗi phát sinh trong lúc stream được tiêu thụ có thể được bọc trong `UncheckedIOException`.

**Kết luận sớm:** chỉ bật `FOLLOW_LINKS` khi thật sự cần đọc nội dung phía sau liên kết và đã xác định chính sách **xử lý vòng lặp, giới hạn độ sâu, ranh giới thư mục, quyền truy cập, dọn tài nguyên và dữ liệu thay đổi đồng thời**. Đừng dùng `Path.normalize()` rồi suy mọi symlink đã được giải quyết.

Bài thuộc mục **Tệp và I/O** của Java 8, tập trung trực tiếp vào **FOLLOW_LINKS và vòng lặp liên kết tượng trưng**, có bảng so sánh API, cơ chế phát hiện, ví dụ Java chạy được, xử lý lỗi, bảo mật, giới hạn traversal và checklist. Các API trình bày đều có từ Java 7/8 và **vẫn được hỗ trợ trong các JDK hiện đại**; không đưa vào kỹ thuật đã lỗi thời.

## 1. Symbolic link là gì?

Symbolic link là một đối tượng filesystem đặc biệt lưu **tham chiếu đến đường dẫn đích**. Nó khác một thư mục bình thường và khác một bản sao của tệp. Khi ứng dụng mở một link theo cách có **follow**, hệ thống tệp thường chuyển thao tác đến đích mà link chỉ tới.

Ba trường hợp thường gặp:

~~~text
A. Link đến tệp:
project/config-current -> config-v3.properties

B. Link đến thư mục:
project/deps -> ../shared-libs

C. Link tạo vòng lặp:
project/src/back -> ..
~~~

**Link có thể tuyệt đối hoặc tương đối.** Với relative link target, đích được diễn giải tương đối với **thư mục chứa chính liên kết**, không phải mặc định tương đối với working directory của ứng dụng Java.

Ví dụ:

~~~java
Path target = Files.readSymbolicLink(link);
// target có thể là một Path tương đối như Paths.get("..")
~~~

Đây là **mã minh họa**, `link` là đối tượng `Path` được cung cấp từ ngoài. `Files.readSymbolicLink` trả nội dung path được lưu trong liên kết; **không** bảo đảm trả đường dẫn thực đã phân giải đến đích.

### 1.1. Link không phải hard link

**Hard link** là một tên khác tham chiếu cùng đối tượng tệp ở filesystem hỗ trợ. Symbolic link chứa một tham chiếu theo đường dẫn và có thể trỏ qua những vùng khác hoặc đến đối tượng chưa tồn tại. Bài này bàn về **symbolic links**, không đánh đồng cơ chế vòng lặp của symlink với hard link.

### 1.2. Broken/dangling symbolic link

Nếu target không còn tồn tại, symlink vẫn có thể tồn tại như một file đặc biệt:

~~~java
boolean existsFollow = Files.exists(link);
boolean existsLink = Files.exists(
    link, LinkOption.NOFOLLOW_LINKS);
boolean isLink = Files.isSymbolicLink(link);
~~~

Đây là mã minh họa; kết quả thực tế phụ thuộc trạng thái filesystem/quyền truy cập. Trường hợp target thiếu, `existsFollow` có thể là false trong khi `existsLink` và `isLink` là true.

Đừng mặc định `Files.exists(...) == false` có nghĩa bạn có quyền kết luận chắc chắn đường dẫn không tồn tại: tài liệu lưu ý một phép kiểm tra có thể không xác minh được sự tồn tại. Kết quả trạng thái tệp cũng có thể trở nên cũ ngay khi phép kiểm tra trả về.

## 2. Phân biệt FileVisitOption.FOLLOW_LINKS và LinkOption.NOFOLLOW_LINKS

Hai enum có tên gần nhau nhưng dùng ở **ngữ cảnh API khác nhau**:

| Enum | Giá trị quan trọng | Được dùng ở đâu? | Ý nghĩa |
| --- | --- | --- | --- |
| `FileVisitOption` | `FOLLOW_LINKS` | `Files.walkFileTree`, `Files.walk`, `Files.find` | Cho phép traversal **đi theo** symlink khi duyệt cây |
| `LinkOption` | `NOFOLLOW_LINKS` | `Files.isDirectory`, `Files.readAttributes`, `Files.exists`, `Path.toRealPath` và API thuộc tính phù hợp | Khi kiểm tra/thao tác được hỗ trợ, xét **link bản thân nó** thay vì target |

**Sai kiểu API:**

~~~java
// PHẢN VÍ DỤ: LinkOption không phải FileVisitOption.
// Files.walk(start, LinkOption.NOFOLLOW_LINKS);
~~~

**Cách đúng:**

~~~java
// Mặc định không theo symlink:
Files.walk(start);

// Tùy chọn rõ ràng đi theo symlink:
Files.walk(start, FileVisitOption.FOLLOW_LINKS);

// Kiểm tra thuộc tính của chính link:
Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS);
~~~

Đây là **mã minh họa**; `start`/`path` phải được cung cấp, và stream do `Files.walk` tạo cần được đóng bằng try-with-resources. Không đem `LinkOption.NOFOLLOW_LINKS` truyền cho `Files.walk`; muốn không theo link thì **không truyền `FOLLOW_LINKS`**.

### 2.1. Files.isSymbolicLink, isDirectory và NOFOLLOW_LINKS

~~~java
Files.isSymbolicLink(path); // Kiểm tra bản thân path có là symlink.
Files.isDirectory(path);    // Mặc định thường follow link.
Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS);
~~~

Với một link `back` trỏ đến **thư mục có thật**:

- `Files.isSymbolicLink(back)` → true.
- `Files.isDirectory(back)` → true khi target có thể truy cập.
- `Files.isDirectory(back, NOFOLLOW_LINKS)` → false vì bản thân entry `back` là link, không phải directory.

Một `false` từ các phép `isDirectory` có thể còn do không xác định được thuộc tính hoặc không có quyền; đừng chỉ dựa trên boolean để diễn dịch loại lỗi. Khi cần thông tin/ngoại lệ chi tiết, dùng `Files.readAttributes`.

## 3. Các cách duyệt cây: walkFileTree, walk và find

| API | Kiểu trả về | Có callback xử lý I/O/cycle trực tiếp? | Quản lý tài nguyên |
| --- | --- | --- | --- |
| `Files.walkFileTree(start, visitor)` | `Path` sau khi traversal hoàn tất | Có: `FileVisitor.visitFileFailed` | NIO đóng directory handles trong cơ chế duyệt |
| `Files.walkFileTree(start, options, maxDepth, visitor)` | `Path` | Có: `visitFileFailed` và `postVisitDirectory` | NIO quản lý mở/đóng thư mục trong traversal |
| `Files.walk(start, options...)` | `Stream<Path>` | Không có FileVisitor; lỗi duyệt lười có thể là `UncheckedIOException` | **Caller phải đóng stream** |
| `Files.walk(start, maxDepth, options...)` | `Stream<Path>` | Lỗi I/O khi tiêu thụ stream có thể bị bọc | **try-with-resources** |
| `Files.find(start, maxDepth, matcher, options...)` | `Stream<Path>` | Nhận `BasicFileAttributes` cùng `Path` trong matcher | **try-with-resources** |

**`walkFileTree` có từ Java 7**, `Files.walk` và `Files.find` được bổ sung trong **Java 8**. Tất cả vẫn phù hợp trong Java hiện đại. Không dùng API Java 9+/21+ rồi gọi nhầm là ví dụ tương thích Java 8.

### 3.1. Files.walkFileTree mặc định không follow

~~~java
Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
    @Override
    public FileVisitResult visitFile(
            Path file, BasicFileAttributes attrs) {
        if (attrs.isSymbolicLink()) {
            System.out.println("Link: " + file);
        }
        return FileVisitResult.CONTINUE;
    }
});
~~~

Đây là **mã minh họa**, cần import các lớp `java.nio.file` và `BasicFileAttributes`; `root` là một `Path` có thật. Khi mặc định không follow, symlink đến thư mục được xem như **một entry** để `visitFile` xử lý, thay vì tự động đi sâu xuống target.

Nếu callback cần thông tin target, nó phải chủ động gọi các phép đọc phù hợp và có chính sách lỗi; bản thân `attrs` trong mặc định no-follow mô tả **link entry**.

### 3.2. Files.walkFileTree có FOLLOW_LINKS

~~~java
Files.walkFileTree(
    root,
    EnumSet.of(FileVisitOption.FOLLOW_LINKS),
    Integer.MAX_VALUE,
    visitor
);
~~~

Đây là mã minh họa, `visitor` là `FileVisitor<Path>` đã tạo. Chữ ký yêu cầu `Set<FileVisitOption>` và `maxDepth`; không thay `EnumSet` bằng `LinkOption.NOFOLLOW_LINKS`.

Khi một directory symlink trỏ đến directory khác, traversal có thể đi vào target. Nhưng Java giữ thông tin nhận diện các directory trên **đường đang duyệt** để kiểm tra nếu một entry trỏ về **ancestor directory**.

### 3.3. Files.walk trả Stream<Path>

~~~java
try (Stream<Path> paths =
         Files.walk(root, FileVisitOption.FOLLOW_LINKS)) {
    paths.filter(Files::isRegularFile)
         .forEach(System.out::println);
}
~~~

Đây là **mã minh họa**, cần import `java.util.stream.Stream`; `root` được cung cấp. Stream được điền **lazily** khi tiêu thụ, không đọc toàn bộ cây ngay tại lời gọi `walk`. Nó có thể giữ **directory handles mở**, nên phải đóng bằng try-with-resources.

Nếu traversal gặp vòng lặp trong quá trình tiêu thụ, pipeline có thể ném `UncheckedIOException` có cause `FileSystemLoopException`. Đừng chỉ đặt catch `IOException` quanh lời gọi `Files.walk` rồi tin rằng mọi lỗi trong `forEach` đã được xử lý.

### 3.4. Files.find và matcher nhận thuộc tính

~~~java
try (Stream<Path> paths = Files.find(
        root,
        12,
        (path, attrs) -> attrs.isRegularFile(),
        FileVisitOption.FOLLOW_LINKS)) {
    paths.forEach(System.out::println);
}
~~~

Đây là đoạn minh họa, cần import `Stream` và cung cấp `root`. Matcher được đưa `BasicFileAttributes` của từng entry, có thể tránh một số lần gọi `Files.readAttributes` lặp khi so với `walk(...).filter(path -> Files.isRegularFile(path))`.

**Nhưng `Files.find` vẫn phải tuân thủ xử lý liên kết và vòng lặp như cách đi cây tương ứng.** Không phải một phép tìm kiếm miễn nhiễm cycle. Cũng cần đóng stream.

## 4. Vòng lặp liên kết tượng trưng hình thành thế nào?

Hãy hình dung:

~~~text
backup/
└── current/
    ├── manifest.txt
    └── back -> ..

Duyệt:
backup -> current -> back -> backup -> current -> back -> ...
~~~

Ở đây `back` là link chứa target tương đối `..`. Nếu không giới hạn hoặc phát hiện cycle, một thuật toán đệ quy tự viết có thể lặp vô hạn.

### 4.1. Chu kỳ đối với một ancestor

Javadoc `Files.walkFileTree` mô tả tình huống cycle khi một entry trong directory dẫn tới directory **tổ tiên** của đường duyệt hiện tại. Khi bật `FOLLOW_LINKS`, Java theo dõi directory đã vào trên đường đó. Việc nhận biết dùng:

- `BasicFileAttributes.fileKey()` khi filesystem provider cung cấp key phù hợp, hoặc
- `Files.isSameFile(...)` nếu không có file key để xác định directory có phải cùng đối tượng với ancestor.

Khi phát hiện, hành vi được chuẩn hóa thành **một lỗi I/O có kiểu `FileSystemLoopException`**.

### 4.2. Không phải mọi symlink đều là cycle

~~~text
root/
├── shared/
│   └── data.txt
├── folderA/
│   └── sharedLink -> ../shared
└── folderB/
    └── anotherLink -> ../shared
~~~

Hai link đến cùng một thư mục `shared` không nhất thiết là **cycle về ancestor tại bước duyệt**. Chúng có thể khiến cùng nội dung được quan sát **qua nhiều đường dẫn**. Cơ chế phát hiện vòng lặp không phải cam kết **mỗi physical file chỉ được duyệt một lần toàn cục**.

Nếu ứng dụng cần de-duplicate theo file identity (ví dụ tính dung lượng mà không tính trùng), phải thiết kế nhận diện riêng bằng file key hoặc `Files.isSameFile`/canonical identity phù hợp, cân nhắc provider, quyền và khả năng thay đổi tệp đồng thời.

### 4.3. Không phải mọi filesystem hỗ trợ symlink giống nhau

Khả năng tạo hoặc theo link phụ thuộc filesystem provider, hệ điều hành, sandbox và quyền. Trên Windows, việc tạo một symbolic link có thể bị giới hạn bởi cấu hình/quyền của tiến trình. Trên filesystem không hỗ trợ link, `Files.createSymbolicLink` có thể ném `UnsupportedOperationException`; lỗi I/O/quyền có thể được báo bằng `IOException` hoặc `SecurityException`.

**Đừng viết test phụ thuộc symlink creation luôn thành công trên mọi máy CI.** Ví dụ đầy đủ phía dưới có một nhánh thông báo môi trường không cho tạo link, nhưng trên môi trường hỗ trợ symlink đã được biên dịch và chạy xác minh.

## 5. FileSystemLoopException xuất hiện ở đâu?

`FileSystemLoopException` là checked exception thuộc package `java.nio.file`, kế thừa `FileSystemException` → `IOException`. Tuy nhiên, cách API **báo** exception cho caller khác nhau.

### 5.1. walkFileTree: visitFileFailed

~~~java
FileVisitor<Path> visitor = new SimpleFileVisitor<Path>() {
    @Override
    public FileVisitResult visitFileFailed(
            Path file, IOException exc) throws IOException {
        if (exc instanceof FileSystemLoopException) {
            System.out.println("Cycle: " + file);
            return FileVisitResult.CONTINUE;
        }
        throw exc;
    }
};

Files.walkFileTree(
    root,
    EnumSet.of(FileVisitOption.FOLLOW_LINKS),
    Integer.MAX_VALUE,
    visitor
);
~~~

Đây là đoạn minh họa (cần `root` và imports). Khi tìm thấy directory symlink trỏ đến ancestor, Java gọi `visitFileFailed` với `FileSystemLoopException`. Callback có thể **xử lý riêng** rồi trả `CONTINUE` để tiếp tục các entry khác, hoặc ném exception để dừng traversal.

**Lưu ý:** `SimpleFileVisitor.visitFileFailed` mặc định **ném lại IOException**. Muốn bỏ qua vòng lặp và tiếp tục, phải override phương thức này. Không dùng `catch (FileSystemLoopException)` bên ngoài rồi kỳ vọng có thể xử lý mọi vòng một cách tinh tế như trong callback.

### 5.2. Files.walk: lỗi có thể phát sinh khi stream đang chạy

~~~java
try (Stream<Path> stream =
         Files.walk(root, FileVisitOption.FOLLOW_LINKS)) {
    stream.forEach(path -> {
        // Xử lý đường dẫn được tìm thấy.
    });
} catch (UncheckedIOException error) {
    IOException cause = error.getCause();
    if (cause instanceof FileSystemLoopException) {
        System.err.println("Cycle found: " + cause.getMessage());
    } else {
        throw error;
    }
}
~~~

Đây là mã minh họa (cần imports). Khi lỗi I/O xuất hiện trong quá trình tiêu thụ stream, `Files.walk` có thể bọc thành `UncheckedIOException`. Phải phân biệt lỗi loop với lỗi quyền, đọc thư mục, mount không truy cập hoặc lỗi I/O khác; **không bắt mọi `UncheckedIOException` rồi âm thầm cho là loop**.

**Tại lúc mở stream**, `Files.walk(...)` vẫn khai báo `throws IOException`, chẳng hạn khi không truy cập được starting file. Ở đoạn minh họa, method bên ngoài cần khai báo hoặc xử lý IOException này. Vì thế hai tầng cần kiểm soát:

1. **IOException khi bắt đầu traversal**.
2. **UncheckedIOException trong khi stream được duyệt lazily**.

### 5.3. Vì sao walkFileTree hữu ích hơn khi cần bỏ qua loop?

`walkFileTree` có callback `visitFileFailed` trên từng entry và cho phép trả `CONTINUE`. Bạn có thể ghi log mỗi vòng được phát hiện rồi tiếp tục các sibling hợp lệ.

Ngược lại, nếu `Files.walk` stream đã ném `UncheckedIOException` trong một terminal operation, **không thể coi việc catch lỗi xong là có thể tiếp tục duyệt phần còn lại bằng chính stream đó một cách đáng tin**. Khi ứng dụng cần khả năng **skip lỗi riêng lẻ rồi tiếp tục quét**, visitor là lựa chọn rõ ràng hơn.

## 6. Broken link khác vòng lặp liên kết

Giả sử:

~~~text
root/
├── broken -> missing-target
└── sub/
    └── back -> ..
~~~

Hai tình huống khác nhau:

- **`broken`:** target không tồn tại/không đọc được.
- **`back`:** target là ancestor directory trên traversal, tạo cycle.

Javadoc `walkFileTree` quy định: khi bật `FOLLOW_LINKS` mà không đọc được thuộc tính của **target**, API thử lấy `BasicFileAttributes` của **link bản thân nó**. Nếu lấy được, `visitFile` có thể được gọi với thuộc tính link, **không nhất thiết `visitFileFailed`** chỉ vì target không tồn tại.

Vì vậy, đừng viết quy tắc cứng “symlink hỏng luôn ném FileSystemLoopException” hoặc “mọi symlink target lỗi đều vào visitFileFailed”. Phải nhận diện loại lỗi, link state và thuộc tính.

### 6.1. Phân biệt I/O và chính sách bỏ qua

~~~java
@Override
public FileVisitResult visitFileFailed(
        Path file, IOException exc) throws IOException {
    if (exc instanceof FileSystemLoopException) {
        logLoop(file);
        return FileVisitResult.CONTINUE;
    }
    throw exc;
}
~~~

Đoạn trên là **phương thức minh họa trong visitor**, với `logLoop` do ứng dụng cung cấp. Nó minh họa policy “bỏ qua loop, nhưng **không giấu lỗi khác**”. Trong một công cụ backup quan trọng, bạn có thể chọn `TERMINATE` hoặc ném lỗi ngay cả với loop; policy phải gắn với mục tiêu dữ liệu.

## 7. FileVisitor và các kết quả điều khiển traversal

`FileVisitor<Path>` có bốn callback:

| Callback | Khi nào gọi? | Mục đích thường gặp |
| --- | --- | --- |
| `preVisitDirectory(dir, attrs)` | Trước khi duyệt nội dung một directory | Quyết định vào sâu, loại trừ folder, kiểm soát scope |
| `visitFile(file, attrs)` | Gặp file hoặc entry không đi xuống như directory | Xử lý file và cả link không được follow |
| `visitFileFailed(file, exc)` | Không thể visit file/directory; gồm vòng lặp đã phát hiện | Xử lý/ghi nhận lỗi rồi quyết định |
| `postVisitDirectory(dir, exc)` | Sau khi duyệt children hoặc có lỗi khi iterate directory | Dọn tài nguyên/chốt thông tin directory, xử lý lỗi iteration |

`FileVisitResult` gồm:

- `CONTINUE`: tiếp tục traversal.
- `SKIP_SUBTREE`: dùng ở `preVisitDirectory` để bỏ qua descendants của directory hiện tại.
- `SKIP_SIBLINGS`: bỏ qua siblings còn lại theo hợp đồng visitor.
- `TERMINATE`: chấm dứt traversal.

**Đừng trả `null`**: Javadoc `walkFileTree` nêu visitor trả `null` sẽ phát sinh `NullPointerException`.

### 7.1. Giới hạn thư mục trong preVisitDirectory

~~~java
@Override
public FileVisitResult preVisitDirectory(
        Path dir, BasicFileAttributes attrs) throws IOException {
    if (shouldSkip(dir)) {
        return FileVisitResult.SKIP_SUBTREE;
    }
    return FileVisitResult.CONTINUE;
}
~~~

Đây là phương thức minh họa, `shouldSkip` là predicate của ứng dụng. Với `FOLLOW_LINKS`, một directory đi qua symlink có thể dẫn **ra ngoài root logic**. Để kiểm tra confinement, cần biết đường dẫn thực và chính sách bảo mật; `SKIP_SUBTREE` là công cụ điều khiển traversal, **không tự chứng minh path nằm trong phạm vi cho phép**.

### 7.2. postVisitDirectory phải chú ý exception

~~~java
@Override
public FileVisitResult postVisitDirectory(
        Path dir, IOException exc) throws IOException {
    if (exc != null) {
        throw exc;
    }
    return FileVisitResult.CONTINUE;
}
~~~

Đây là phương thức minh họa. Khi đọc entry trong directory gặp lỗi I/O, `postVisitDirectory` có thể nhận exception; đừng bỏ qua `exc` rồi báo rằng toàn bộ cây đã được đọc thành công. Với backup/export, cần ghi nhận lỗi bằng cơ chế rõ ràng trước khi chốt “đủ dữ liệu”.

## 8. maxDepth giới hạn mức đi sâu nhưng không thay thế kiểm soát vòng lặp

Cả `walkFileTree` và `walk` cho phép đặt `maxDepth`:

~~~java
Files.walkFileTree(
    root,
    EnumSet.of(FileVisitOption.FOLLOW_LINKS),
    4,
    visitor
);
~~~

Đây là mã minh họa. **Root ở độ sâu 0**. Khi maxDepth=0, chỉ starting path được visit. Các file **và directory** tại maxDepth được xử lý như leaf theo hợp đồng, không tiếp tục duyệt descendants.

### 8.1. maxDepth có tác dụng gì?

- Giảm số lớp directory được đi vào.
- Giới hạn công việc trong cây rất sâu hoặc dữ liệu không tin cậy.
- Giúp tránh đệ quy tự viết tăng vô hạn tầng stack khi structure quá sâu.

### 8.2. maxDepth không có tác dụng gì?

- Không bảo đảm “không có symlink đi ra ngoài root”.
- Không bảo đảm mọi path là duy nhất về file identity.
- Không tự hạn chế **số lượng entry trong một level**; một thư mục rất rộng vẫn có thể tốn nhiều tài nguyên.
- Không tự giới hạn tổng byte đọc, lượng dữ liệu backup hay CPU.
- Không tạo snapshot cố định khi filesystem thay đổi đồng thời.

**Khi có symlink cycle**, vẫn cần hiểu và xử lý `FileSystemLoopException`. Đừng tăng maxDepth lên `Integer.MAX_VALUE` rồi tin Java sẽ không bao giờ gặp lỗi; Java **phát hiện vòng**, chứ không biến mọi symlink topology thành một cây hợp lệ.

## 9. Path.normalize, toRealPath và isSameFile: ba điều khác nhau

### 9.1. Path.normalize() chỉ là thao tác đường dẫn mang tính cú pháp

~~~java
Path normalized =
    Paths.get("a", "b", "..", "file.txt").normalize();
~~~

Đây là mã minh họa. `normalize()` có thể loại phần `.`/`..` dư thừa theo quy tắc lexical mà **không truy cập filesystem**.

**Quan trọng:** nếu `b` là symlink, việc xóa `b/..` theo ký tự đường dẫn có thể tạo path trỏ đến tệp **khác** so với khi filesystem giải quyết symlink thật. Không coi `normalize()` là “canonicalize an toàn” hay “bảo đảm vẫn ở trong root được phép”.

### 9.2. Path.toRealPath() truy vấn đường dẫn thực

~~~java
Path actual = path.toRealPath();
Path linkItself = path.toRealPath(
    LinkOption.NOFOLLOW_LINKS);
~~~

Đây là mã minh họa; `path` phải tồn tại và truy cập được. `toRealPath()` mặc định **theo symlink** và trả một đường dẫn thực đại diện cùng file; `toRealPath(NOFOLLOW_LINKS)` không theo symlink theo hợp đồng tùy provider.

`toRealPath()` có thể ném `IOException` khi path không tồn tại hoặc xảy ra lỗi, và không có khả năng đảm bảo đường dẫn không bị writer khác sửa ngay sau lúc resolve.

### 9.3. Files.isSameFile() so identity, không chỉ so chữ

~~~java
boolean same = Files.isSameFile(
    someSymlink,
    targetDirectory
);
~~~

Đây là mã minh họa; `someSymlink` và `targetDirectory` phải là các `Path` hợp lệ. `Files.isSameFile` có thể theo symlink để xác định hai path có chỉ cùng file hay không và có thể ném `IOException`. Hai chuỗi đường dẫn khác nhau **có thể** chỉ cùng directory.

Chính vì vậy, phát hiện cycle của `walkFileTree` dùng `fileKey` hoặc `isSameFile` khi cần: so mỗi path theo String không đủ nếu có nhiều alias/symlink.

### 9.4. FileKey có sẵn ở mọi filesystem không?

Không. `BasicFileAttributes.fileKey()` có thể trả `null` nếu provider không có khóa định danh phù hợp. Không xây thiết kế portable dựa trên giả định mọi fileKey đều có giá trị hoặc có cùng kiểu giữa các provider.

Nếu tự viết dedup toàn cục, bạn cần định nghĩa: identity là **cùng physical file**, cùng symlink target, cùng path thật, hay cùng nội dung? Mỗi định nghĩa có trade-off khi filesystem có hard links, mount, network shares và thay đổi đồng thời.

## 10. Ví dụ Java hoàn chỉnh: tạo vòng link thật, xử lý qua hai API

Lưu chương trình sau thành **`FollowLinksCycleDemo.java`**. Chương trình:

1. Tạo một thư mục tạm, directory `child` và symbolic link `child/back -> ..` (back trỏ về root).
2. Kiểm tra `Files.isSymbolicLink`, `Files.isDirectory` có/không có `NOFOLLOW_LINKS`, `readSymbolicLink` và `isSameFile`.
3. Dùng `walkFileTree` **không FOLLOW_LINKS** để đếm link như một entry.
4. Dùng `walkFileTree` **có FOLLOW_LINKS** và override `visitFileFailed` để ghi nhận vòng lặp rồi `CONTINUE`.
5. Dùng `Files.walk` có `FOLLOW_LINKS` trong try-with-resources; nhận biết `UncheckedIOException` có cause `FileSystemLoopException`.
6. Dọn dẹp toàn bộ thư mục tạm bằng `walkFileTree` **không theo link** để không xóa target ngoài ý muốn.
7. Có nhánh xử lý khi môi trường không hỗ trợ/không cho phép tạo symlink.

**Mã dùng API có từ Java 8**, biên dịch/chạy được trên JDK 17+. Ví dụ đã được **biên dịch và chạy thử trên OpenJDK 21** trong môi trường cho phép tạo symbolic links.

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.EnumSet;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

public final class FollowLinksCycleDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("link-walk-demo-");

        try {
            Path child = Files.createDirectory(
                root.resolve("child"));
            Path link = child.resolve("back");

            try {
                // Relative target "..": từ child quay lên root.
                Files.createSymbolicLink(link, Paths.get(".."));
            } catch (UnsupportedOperationException
                    | SecurityException | IOException ex) {
                System.out.println("linkAvailable=false");
                return;
            }

            System.out.println("linkAvailable=true");
            System.out.println("isSymbolicLink="
                + Files.isSymbolicLink(link));
            System.out.println("isDirectoryFollow="
                + Files.isDirectory(link));
            System.out.println("isDirectoryNoFollow="
                + Files.isDirectory(
                    link, LinkOption.NOFOLLOW_LINKS));
            System.out.println("target="
                + Files.readSymbolicLink(link));
            System.out.println("sameFile="
                + Files.isSameFile(link, root));

            AtomicInteger seenLinks = new AtomicInteger();

            // Không FOLLOW_LINKS: link được visit như file.
            Files.walkFileTree(root,
                new SimpleFileVisitor<Path>() {
                    @Override
                    public FileVisitResult visitFile(
                            Path file, BasicFileAttributes attrs) {
                        if (attrs.isSymbolicLink()) {
                            seenLinks.incrementAndGet();
                        }
                        return FileVisitResult.CONTINUE;
                    }
                });

            System.out.println("defaultVisitorSeesLinks="
                + seenLinks.get());

            AtomicInteger loopCount = new AtomicInteger();

            // FOLLOW_LINKS: back trỏ về directory tổ tiên.
            Files.walkFileTree(
                root,
                EnumSet.of(FileVisitOption.FOLLOW_LINKS),
                Integer.MAX_VALUE,
                new SimpleFileVisitor<Path>() {
                    @Override
                    public FileVisitResult visitFileFailed(
                            Path file, IOException exc)
                            throws IOException {
                        if (exc instanceof FileSystemLoopException) {
                            loopCount.incrementAndGet();
                            return FileVisitResult.CONTINUE;
                        }
                        throw exc;
                    }
                });

            System.out.println("fileVisitorLoops="
                + loopCount.get());

            boolean loopWrapped = false;

            // Stream traversal báo lỗi lazily.
            try (Stream<Path> paths = Files.walk(
                    root, FileVisitOption.FOLLOW_LINKS)) {
                paths.forEach(path -> { });
            } catch (UncheckedIOException exc) {
                if (!(exc.getCause()
                        instanceof FileSystemLoopException)) {
                    throw exc;
                }
                loopWrapped = true;
            }

            System.out.println("streamLoopWrapped="
                + loopWrapped);

        } finally {
            // Không FOLLOW_LINKS khi dọn: chỉ xóa link,
            // không đệ quy theo đường link quay lại root.
            Files.walkFileTree(root,
                new SimpleFileVisitor<Path>() {
                    @Override
                    public FileVisitResult visitFile(
                            Path file, BasicFileAttributes attrs)
                            throws IOException {
                        Files.delete(file);
                        return FileVisitResult.CONTINUE;
                    }

                    @Override
                    public FileVisitResult postVisitDirectory(
                            Path dir, IOException exc)
                            throws IOException {
                        if (exc != null) {
                            throw exc;
                        }
                        Files.delete(dir);
                        return FileVisitResult.CONTINUE;
                    }
                });

            System.out.println("cleanup=true");
        }
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac -encoding UTF-8 FollowLinksCycleDemo.java
java FollowLinksCycleDemo
~~~

### Đầu ra trên filesystem có symlink được phép

~~~text
linkAvailable=true
isSymbolicLink=true
isDirectoryFollow=true
isDirectoryNoFollow=false
target=..
sameFile=true
defaultVisitorSeesLinks=1
fileVisitorLoops=1
streamLoopWrapped=true
cleanup=true
~~~

**Đây là đầu ra đã được kiểm tra trên OpenJDK 21 với filesystem hỗ trợ link.** Nó không in đường dẫn tạm ngẫu nhiên, nên các dòng được cố định theo cấu trúc bài thử, không phụ thuộc tên directory do `createTempDirectory` chọn.

### Đầu ra khi không tạo được symbolic link

~~~text
linkAvailable=false
cleanup=true
~~~

Nhánh này dành cho môi trường không hỗ trợ symlink hoặc không cấp quyền tạo link. Nó **không có nghĩa JDK không hỗ trợ `FOLLOW_LINKS`**; hạn chế có thể đến từ filesystem hoặc quyền OS/CI.

### Giải thích từng dòng quan trọng

- **`isSymbolicLink=true`**: bản thân entry `back` là symbolic link.
- **`isDirectoryFollow=true`**: khi theo link, đích `..` là root directory.
- **`isDirectoryNoFollow=false`**: khi không follow, bản thân entry là link chứ không phải directory.
- **`target=..`**: `readSymbolicLink` trả target được lưu dạng relative path, không tự đổi thành absolute.
- **`sameFile=true`**: target của `back` là đúng directory `root`, cho thấy một path alias quay lại tổ tiên.
- **`defaultVisitorSeesLinks=1`**: cách duyệt mặc định coi link là file-like entry trong callback `visitFile`.
- **`fileVisitorLoops=1`**: với `FOLLOW_LINKS`, visitor nhận một `FileSystemLoopException` trên đường `child/back`. Code tăng counter và trả `CONTINUE`.
- **`streamLoopWrapped=true`**: khi tiêu thụ `Files.walk(..., FOLLOW_LINKS)`, lỗi được ném theo cơ chế lazy stream và cause là `FileSystemLoopException`.
- **`cleanup=true`**: cleanup không bật FOLLOW_LINKS nên xóa entry `back` như một link, sau đó xóa `child` và `root`; không chạy vòng lặp.

### Điều chương trình không tuyên bố

- Không tuyên bố mọi provider đều cho phép tạo symlink.
- Không dùng `Thread.sleep` hoặc thứ tự filesystem entries để cố đoán output.
- Không tuyên bố vòng lặp là exception trực tiếp từ `Files.walk` terminal operation; stream có thể bọc vào `UncheckedIOException`.
- Không đọc hoặc xóa bất kỳ thư mục ứng dụng nào bên ngoài vùng tạm mà ví dụ tự tạo.
- Không chứng minh symlink scan luôn an toàn đối với thư mục chứa dữ liệu do attacker kiểm soát; môi trường thật cần chính sách quyền và chống TOCTOU.

## 11. Tại sao nên đóng Stream<Path>?

`Files.walk` và `Files.find` có thể giữ một hoặc nhiều directory handle đang mở khi stream chưa được tiêu thụ hết. Một stream chỉ là pipeline lazily evaluated, không phải bản liệt kê đã đọc sạch vào RAM tại thời điểm khởi tạo.

**Cách đúng:**

~~~java
try (Stream<Path> paths = Files.walk(root)) {
    long number = paths.count();
    System.out.println(number);
}
~~~

Đây là mã minh họa, cần xử lý/khai báo `IOException` ở method chứa nó. Try-with-resources sẽ gọi `close` ngay cả nếu terminal operation phát sinh exception.

**Cách dễ rò tài nguyên:**

~~~java
Stream<Path> paths = Files.walk(root);
return paths.filter(Files::isRegularFile).count();
// Không có đoạn finally/try-with-resources để bảo đảm close.
~~~

Đây là phản ví dụ. Nếu buộc phải trả stream ra ngoài method, trách nhiệm close phải được thiết kế/được caller biết rõ, nhưng thường đơn giản và an toàn hơn nếu tiêu thụ trong phạm vi try-with-resources.

`Files.walkFileTree` dùng visitor và tự quản lý các thư mục được mở trong traversal. Không cần tạo stream rồi đóng thủ công cho chính `walkFileTree`.

## 12. Cẩn trọng với TOCTOU và đường dẫn không tin cậy

TOCTOU (*time of check to time of use*) nghĩa là **trạng thái filesystem có thể bị đổi giữa lúc kiểm tra và lúc sử dụng**. Một ứng dụng có thể kiểm tra `path` đang nằm trong root được phép, nhưng trước khi mở, attacker thay symlink để nó chỉ ra ngoài.

### 12.1. Vì sao Path.startsWith chưa đủ làm sandbox?

~~~java
Path allowedRoot = Paths.get("/srv/allowed");
Path requested = allowedRoot.resolve("upload/data.txt");

if (requested.normalize().startsWith(allowedRoot)) {
    // VẪN KHÔNG chứng minh requested
    // không đi qua một symlink ra ngoài allowedRoot.
}
~~~

Đây là pseudocode cho filesystem dùng dấu phân cách Unix; đường dẫn thật phụ thuộc OS. `normalize` chỉ xử lý thành phần tên đường dẫn về mặt cú pháp. Một thành phần trung gian như `upload` có thể là symlink trỏ sang filesystem khác.

### 12.2. Kiểm tra real path giúp gì?

~~~java
Path rootReal = allowedRoot.toRealPath();
Path candidateReal = requested.toRealPath();

if (!candidateReal.startsWith(rootReal)) {
    throw new SecurityException("outside allowed root");
}
~~~

Đây là minh họa **best-effort**, không phải cơ chế bảo mật hoàn chỉnh. Nó giải quyết symlink tại **thời điểm kiểm tra**, nhưng attacker có thể thay link hoặc thư mục giữa thời điểm check và open. Muốn xử lý path không tin cậy với mức an toàn cao, thiết kế quyền OS, filesystem isolation, thao tác tương đối với directory handle và xem xét `SecureDirectoryStream` **nếu provider hỗ trợ**; không hứa mọi provider hỗ trợ secure directory operations.

### 12.3. Ngay cả không FOLLOW_LINKS vẫn cần chính sách bảo mật

Việc không follow link trong traversal ngăn tự động đệ quy xuyên symlink directory, nhưng các hành động của ứng dụng **trong `visitFile`** có thể theo link khi đọc nội dung, copy hoặc mở file bằng API mặc định. Nếu file là link đến tài nguyên nhạy cảm, callback không nên vô tình đọc target.

Ví dụ backup chỉ muốn lưu symbolic link như metadata thay vì copy target: cần áp dụng đúng chính sách `NOFOLLOW_LINKS` ở **từng phép đọc/copy được hỗ trợ**, không chỉ ở traversal. Với `Files.copy`, các `CopyOption` liên quan có semantics riêng; kiểm tra tài liệu của method thay vì mặc định mọi API nhận cùng một tùy chọn.

## 13. Giới hạn tài nguyên khi follow liên kết

Một cây có thể có số lượng file cực lớn, nhiều link chéo hoặc link tới network filesystem. Ngay cả khi Java phát hiện ancestor cycle, chương trình vẫn có thể chịu tải cao vì **traversal hợp lệ nhưng trùng lặp** hoặc bị chặn bởi I/O.

Những giới hạn cần cân nhắc:

| Rủi ro | Cách giảm |
| --- | --- |
| Cây quá sâu | Đặt `maxDepth` phù hợp |
| Một directory có quá nhiều entries | Đếm/giới hạn số entry đã xử lý; có chính sách dừng |
| Link ra ngoài root | Mặc định không follow; nếu follow thì confinement + quyền OS/secure operations |
| Duplicate files qua nhiều alias | Định nghĩa file identity/dedup theo nhu cầu |
| Thư mục network chậm | Timeout/quản lý task ở tầng ứng dụng; không tin rằng stream tự có deadline |
| Permission denied | Xử lý `visitFileFailed`/`UncheckedIOException`, phân biệt với loop |
| File biến mất khi đang duyệt | Coi filesystem là mutable, xử lý `NoSuchFileException` hoặc IOException phù hợp |
| Symlink cycle | `FileSystemLoopException` và policy continue/stop |
| Dữ liệu thay đổi khi đọc | Không xem traversal là snapshot giao dịch |
| Mở nhiều handle | Luôn đóng stream; tránh giữ mọi stream mở song song |
| Callback làm I/O nặng | Thiết kế queue/concurrency/backpressure; không tự spawn thread vô hạn |

**Lưu ý:** `Files.walk` được mô tả là **weakly consistent**. Nó không đóng băng cây thư mục. Các thay đổi sau lúc lấy stream **có thể được quan sát hoặc không**, nên một lần quét không tự đảm bảo “mọi file từng tồn tại trong khoảng thời gian đó đều được thấy”.

## 14. Đi theo link có thể gây xử lý trùng dù không có vòng

Cây ví dụ:

~~~text
root/
├── shared/data.txt
├── alpha/sharedRef -> ../shared
└── beta/sharedRef -> ../shared
~~~

Khi `FOLLOW_LINKS` được bật, `data.txt` có thể xuất hiện dưới nhiều path:

~~~text
root/shared/data.txt
root/alpha/sharedRef/data.txt
root/beta/sharedRef/data.txt
~~~

Chúng có thể là **cùng physical file** nhưng khác đường dẫn lexical. `FileSystemLoopException` không bắt buộc xuất hiện vì alias đến `shared` không trỏ về tổ tiên của mỗi đường đi.

### 14.1. Ý nghĩa đối với công cụ tính dung lượng

~~~java
long bytes = Files.walk(root, FileVisitOption.FOLLOW_LINKS)
    .filter(Files::isRegularFile)
    .mapToLong(path -> {
        try {
            return Files.size(path);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    })
    .sum();
~~~

Đây là **mã minh họa thiếu try-with-resources**, nhằm nhấn mạnh bẫy logic: nếu không deduplicate file identity, một file truy cập qua nhiều alias có thể bị cộng nhiều lần. **Khi viết code thật**, phải bọc stream bằng try-with-resources và xử lý overflow/chính sách lỗi.

### 14.2. Định nghĩa identity theo nhu cầu

Có thể dùng `Files.isSameFile` hoặc fileKey/real path để giảm trùng, nhưng phải tính tới:

- Symlink và hard link.
- Provider trả `fileKey == null`.
- File đổi/được thay thế trong lúc duyệt.
- Những filesystem case-insensitive.
- Network storage có latency/caching.
- Mục tiêu: dedup theo physical file hay theo nội dung, hai vấn đề khác nhau.

Không dùng `Path.toString()` hoặc `Path.normalize()` làm tiêu chuẩn duy nhất cho physical identity.

## 15. Các tình huống xử lý lỗi thường gặp

### 15.1. visitFileFailed không đồng nghĩa cycle

~~~java
@Override
public FileVisitResult visitFileFailed(
        Path file, IOException exc) throws IOException {
    if (exc instanceof FileSystemLoopException) {
        // Đã phát hiện vòng ancestor.
        return FileVisitResult.CONTINUE;
    }
    // Các lỗi khác cần chính sách riêng.
    throw exc;
}
~~~

Ví dụ chỉ bỏ qua lỗi loop, không bỏ qua `AccessDeniedException` hoặc `NoSuchFileException` một cách âm thầm. Trong sản phẩm cần scan best-effort, bạn có thể ghi nhận lỗi và tiếp tục tất cả; nhưng kết quả phải được đánh dấu **không đầy đủ**, không coi là backup thành công.

### 15.2. Không che mọi IOException trong stream

~~~java
try (Stream<Path> stream =
         Files.walk(root, FileVisitOption.FOLLOW_LINKS)) {
    stream.forEach(System.out::println);
} catch (UncheckedIOException ex) {
    if (ex.getCause() instanceof FileSystemLoopException) {
        // Vòng được phát hiện khi tiêu thụ.
    } else {
        throw ex;
    }
}
~~~

Đây là đoạn minh họa; method cần xử lý checked IOException từ khởi tạo stream. Stream exception không phải tín hiệu để “đóng rồi mở lại và chắc chắn sẽ tiếp tục từ đúng vị trí”; nếu cần xử lý lỗi từng entry, dùng visitor.

### 15.3. Dọn cây luôn kiểm tra link semantics

Một công cụ xóa thư mục tạm có link trỏ ra thư mục khác không nên dùng callback tùy tiện “đi theo link và xóa mọi file gặp”. Với cleanup, thường **không bật FOLLOW_LINKS** để xóa chính symbolic link và những entry nằm trong tree do ứng dụng sở hữu. Vẫn phải kiểm soát input và quyền/xác minh ownership, vì filesystem có thể thay đổi đồng thời.

### 15.4. Đừng bỏ qua lỗi postVisitDirectory

Nếu một directory được mở nhưng đọc entries phát sinh I/O exception, `postVisitDirectory` có thể nhận lỗi. Với ứng dụng sao lưu, xuất báo cáo hoặc kiểm toán, ghi nhận trạng thái incomplete và dừng/tiếp tục theo chính sách.

## 16. Các lỗi lập trình phổ biến

1. **Bật FOLLOW_LINKS mọi nơi.** Tăng diện tích filesystem được truy cập, nguy cơ đi ra ngoài root, đọc trùng hoặc gặp vòng lặp.
2. **Dùng LinkOption.NOFOLLOW_LINKS làm FileVisitOption.** Đây là hai enum khác nhau; `walkFileTree`/`walk` dùng `FOLLOW_LINKS` của `FileVisitOption`, và mặc định không follow.
3. **Nghĩ một symbolic link tới folder luôn phải đi sâu.** Với traversal mặc định, link được visit như file-like entry.
4. **Nghĩ link target được tính từ working directory.** Relative target được giải quyết từ **thư mục chứa link**.
5. **Không override visitFileFailed.** Mặc định `SimpleFileVisitor` ném lại lỗi; vòng lặp có thể làm traversal dừng.
6. **Bắt mọi IOException như FileSystemLoopException.** Lỗi access, missing file, broken link và cycle có chính sách khác nhau.
7. **Chỉ catch IOException ở ngoài Files.walk.** Lỗi khi terminal operation đọc lazily có thể thành `UncheckedIOException`.
8. **Quên try-with-resources.** Stream có thể giữ directory handles mở và gây rò tài nguyên.
9. **Tưởng Path.normalize giải được symlink.** Nó là lexical, không phải filesystem resolve.
10. **So path bằng String để tìm cycle.** Symlink tạo alias; file identity không tương đương chuỗi path.
11. **Nghĩ fileKey luôn có.** Provider có thể trả null; Java dùng `isSameFile` làm cách khác trong cơ chế cycle detection.
12. **Coi cycle detection như dedup toàn cục.** Hai alias tới cùng thư mục không là ancestor cycle vẫn có thể bị duyệt trùng.
13. **Tưởng maxDepth luôn ngăn escape.** Nó giới hạn mức duyệt, không giới hạn target symlink nằm ở đâu.
14. **Bỏ qua postVisitDirectory(exc).** Lỗi đọc entries có thể khiến kết quả thiếu dữ liệu.
15. **Dùng Files.exists rồi tin state không đổi.** Có TOCTOU giữa check và open.
16. **Duyệt path do người dùng nhập như một sandbox.** Cần quyền OS, confinement và xử lý symlink theo toàn bộ chuỗi operation.
17. **Dùng parallelStream với stream filesystem rồi bỏ qua tài nguyên.** Không tự nhanh hơn hoặc đúng hơn; phải đóng stream và kiểm soát I/O.
18. **Bỏ qua giới hạn số entry/byte/time.** Cây rộng hoặc network filesystem có thể tốn tài nguyên dù không có cycle.
19. **Tưởng Files.walk là snapshot.** Nó weakly consistent, không đóng băng cây đang được cập nhật.
20. **Mặc định symlink creation luôn được phép trên CI.** Cần test có điều kiện hoặc dùng filesystem phù hợp.
21. **Cho rằng xóa link là xóa target.** Khi xóa một symbolic link theo API phù hợp, link entry bị xóa; nếu cố đi theo link và xóa children, có thể gây hậu quả lớn.
22. **Dùng FOLLOW_LINKS để đếm dung lượng mà không dedup.** Cùng file có thể được tính nhiều lần qua alias.

## 17. Kiểm thử: xác nhận điều API bảo đảm

Một test đáng tin nên:

- Tạo **thư mục tạm biệt lập** thay vì sửa cây dự án có thật.
- Tạo một directory, một symlink trỏ về **ancestor** và tùy chọn một link đến target hợp lệ khác.
- Có nhánh **skip có giải thích** nếu filesystem không hỗ trợ hoặc không cho phép tạo link.
- Với **no-follow**, kiểm tra link được báo như entry và không tự đi sâu target.
- Với `walkFileTree(..., FOLLOW_LINKS, ...)`, assert callback `visitFileFailed` nhận `FileSystemLoopException`.
- Với `Files.walk(..., FOLLOW_LINKS)`, tiêu thụ stream và bắt `UncheckedIOException` có cause loop; luôn close stream.
- Không hardcode thứ tự các entries khi filesystem không có encounter order được đảm bảo.
- Không dùng `Thread.sleep` để “giữ” cây cố định: chỉ dùng một thread kiểm soát fixture hoặc phối hợp writers.
- Test thêm broken link, permission denied, maxDepth=0/1, symlink alias trỏ ra ngoài root, callback ném IOException.
- Test cleanup **không follow** và không đụng path ngoài thư mục tạm.
- Trong test an ninh, không dựa vào `normalize/startsWith` lexical để kết luận không escape; dùng cơ chế truy cập an toàn theo threat model.

### 17.1. Test nào không nên assert?

Không nên assert:

- Mọi filesystem đều cho phép tạo `symbolicLink`.
- `Files.walk` luôn ném trực tiếp `FileSystemLoopException` thay vì bọc.
- Một broken link **luôn** bị gọi `visitFileFailed`; khi follow thất bại, Java có cơ chế thử đọc attributes của link.
- Cùng một physical file chỉ xuất hiện một lần nếu link chéo nhưng không tạo ancestor cycle.
- `Path.toRealPath` là một “security lock” khiến filesystem không bao giờ đổi ngay sau check.
- Mọi stream đang duyệt sẽ thấy tất cả thay đổi mới của một writer khác.

### 17.2. Test bổ sung về maxDepth

~~~java
try (Stream<Path> paths = Files.walk(
        root, 0, FileVisitOption.FOLLOW_LINKS)) {
    // Root depth=0; chỉ bắt đầu từ root,
    // không duyệt children.
    paths.forEach(System.out::println);
}
~~~

Đây là minh họa; method cần khai báo/handle IOException. Việc maxDepth=0 hạn chế traversal trong ví dụ nhưng **không chứng minh root là path an toàn** nếu chính starting path được tạo từ input không tin cậy.

## 18. Những tình huống thực tế cần chính sách rõ

### 18.1. Backup file tree

Một chương trình backup có thể chọn **giữ symlink như metadata** thay vì follow. Cách này tránh việc cùng dữ liệu xuất hiện nhiều lần và tránh vô tình đi sang mount khác. Nếu yêu cầu follow, phải có luật xử lý cycle, dedup, giới hạn, permission, I/O error, snapshot consistency và thất bại một phần.

Nếu backup bị lỗi quyền ở 1 thư mục nhưng tiếp tục quét còn lại, kết quả cần ghi rõ **partial backup**, không tuyên bố thành công hoàn toàn.

### 18.2. Indexer / file search

Một indexer có thể cần follow symlink vào thư viện dùng chung. Nhưng nếu không dedup identity, một file có thể được index nhiều lần dưới path alias, dẫn đến search results trùng. Dùng `Files.find`/`walkFileTree` phù hợp, lưu thông tin path hiển thị và identity theo chính sách, kiểm soát cycle và giới hạn I/O.

### 18.3. Dọn thư mục upload

Với nội dung người dùng upload, **mặc định không follow symlink** thường an toàn hơn, và cần chính sách từ chối/kiểm tra link trước các thao tác đọc/copy/delete. Đừng đưa `FOLLOW_LINKS` vào công cụ xóa recursive mà không đánh giá nguy cơ link trỏ tới thư mục nằm ngoài vùng sở hữu.

### 18.4. Công cụ phân tích dependency

Một dự án có thể có các link trỏ tới thư mục dependency dùng chung để tránh copy dữ liệu. Nếu chỉ muốn liệt kê nội dung dưới root theo directory names, có thể cần follow có kiểm soát; nếu muốn tính dung lượng vật lý, cần de-duplicate theo identity. Cả hai bài toán khác nhau, không có một flag tự giải quyết toàn bộ.

### 18.5. Walk trên network filesystem

Network filesystem có thể không cung cấp cùng fileKey, có latency cao, có lỗi tạm thời hoặc namespace thay đổi. Java có cơ chế fallback theo `isSameFile` để kiểm tra ancestor identity, nhưng ứng dụng vẫn cần timeout/quota/observability. Một vòng walk thành công ở local SSD không nói lên độ ổn định khi đi qua share mạng.

## 19. Checklist trước khi bật FOLLOW_LINKS trong production

- [ ] Nghiệp vụ có thật sự cần đi vào target symlink hay chỉ cần ghi nhận link?
- [ ] Đã phân biệt `FileVisitOption.FOLLOW_LINKS` với `LinkOption.NOFOLLOW_LINKS`?
- [ ] Có hiểu target tương đối được tính từ thư mục chứa link?
- [ ] Đã xác định các API sử dụng: `walkFileTree`, `walk`, `find` và trách nhiệm close stream?
- [ ] Nếu dùng visitor, `visitFileFailed` có nhận diện `FileSystemLoopException`?
- [ ] Policy với loop là **CONTINUE**, **TERMINATE** hay throw IOException? Có ghi nhận log/metric không?
- [ ] Có phân biệt broken link, permission denied, path missing và cycle?
- [ ] `postVisitDirectory` có xử lý IOException từ iteration không?
- [ ] Có giới hạn `maxDepth`, tổng số entries, thời gian và byte cần đọc?
- [ ] Có ngăn đường symlink trỏ ra ngoài root được phép không? Có xem xét TOCTOU?
- [ ] Có tránh tin `normalize()` là giải quyết symlink an toàn?
- [ ] Nếu cần identity/dedup, đã dùng chính sách fileKey/isSameFile/real path phù hợp với filesystem?
- [ ] Có hiểu detect ancestor cycle không đồng nghĩa tránh duyệt trùng toàn cục?
- [ ] Callback dùng thao tác đọc/copy/xóa có tuân thủ chính sách link không?
- [ ] Có xử lý lỗi phát sinh **lazily** từ stream, không chỉ lỗi lúc tạo stream?
- [ ] Có đóng `Stream<Path>` bằng try-with-resources trong cả nhánh thành công/lỗi?
- [ ] Có cân nhắc file tree **weakly consistent**, không phải snapshot nguyên tử?
- [ ] Nếu triển khai cleanup, có tránh follow symlink khi xóa recursively?
- [ ] Test trên Linux/Windows/CI có nhánh khi createSymbolicLink bị hạn chế?
- [ ] Khi scan chưa đầy đủ, có báo kết quả **partial/incomplete**, không âm thầm báo success?

**Ghi nhớ:** `FOLLOW_LINKS` là lựa chọn **chủ động** khi đi cây thư mục bằng Java NIO; mặc định traversal không đi theo symbolic link. Khi đi theo, Java phát hiện link dẫn ngược về một **ancestor directory** và báo `FileSystemLoopException`. Dùng `walkFileTree` nếu cần xử lý từng loop qua `visitFileFailed` và tiếp tục; dùng `Files.walk`/`find` khi phù hợp pipeline stream nhưng phải **đóng stream** và xử lý cả `UncheckedIOException` xuất hiện lúc duyệt. **Không** biến việc phát hiện cycle thành giả định “không thể đi ra ngoài root”, “không có tệp trùng” hoặc “đã có một snapshot ổn định”. Các nguyên tắc này vẫn áp dụng trong Java hiện đại.

## Tài liệu chính thức

- [Oracle Java SE 26 — Files.walkFileTree, Files.walk, Files.find, createSymbolicLink, readSymbolicLink và cycle detection](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html)
- [Oracle Java SE 26 — FileVisitOption.FOLLOW_LINKS](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/FileVisitOption.html)
- [Oracle Java SE 26 — LinkOption.NOFOLLOW_LINKS](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/LinkOption.html)
- [Oracle Java SE 26 — FileVisitor và callback preVisitDirectory/visitFileFailed/postVisitDirectory](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/FileVisitor.html)
- [Oracle Java SE 26 — SimpleFileVisitor và chính sách exception mặc định](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/SimpleFileVisitor.html)
- [Oracle Java SE 26 — FileSystemLoopException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/FileSystemLoopException.html)
- [Oracle Java SE 26 — Path.toRealPath và Path.normalize](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Path.html)
- [Oracle Java SE 26 — SecureDirectoryStream (khi filesystem provider hỗ trợ)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/SecureDirectoryStream.html)
- [Oracle Java SE 26 — BasicFileAttributes.fileKey](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html)
