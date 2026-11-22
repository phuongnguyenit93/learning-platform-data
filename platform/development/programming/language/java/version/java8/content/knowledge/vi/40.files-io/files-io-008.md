# UncheckedIOException và lỗi xảy ra khi duyệt tệp, thư mục trong Java

## 1. Vấn đề thực tế: stream được tạo thành công nhưng duyệt lại thất bại

Java 8 bổ sung cách đọc tệp và duyệt thư mục bằng `Stream`, ví dụ `Files.lines(path)`, `Files.list(directory)`, `Files.walk(root)` và `Files.find(root, depth, predicate)`. Các API này **lười đọc** (*lazy*): việc gọi phương thức tạo stream không có nghĩa tất cả dòng tệp hay tất cả phần tử của cây thư mục đã được đọc xong. I/O có thể xảy ra **khi terminal operation chạy**, tức là **sau khi phương thức đã trả stream**.

Ví dụ:

```java
try (Stream<Path> paths = Files.walk(root)) {
    long total = paths.filter(Files::isRegularFile).count();
    System.out.println(total);
}
```

Đây là **snippet trong method**, cần import `java.nio.file.Files`, `java.nio.file.Path` và `java.util.stream.Stream`; biến `root` được ứng dụng cung cấp. `Files.walk(root)` có thể đọc thông tin root rồi trả một stream hợp lệ; khi `count()` bắt đầu duyệt sâu, filesystem có thể trả lỗi I/O — chẳng hạn thư mục bị xóa, quyền truy cập thay đổi hoặc thiết bị không còn khả dụng.

**Câu hỏi:** `IOException` là *checked exception*, nhưng `Stream.filter`, `count` và `forEach` không khai báo `throws IOException`. Làm sao biểu diễn lỗi I/O phát sinh giữa lúc stream đang chạy?

**Câu trả lời:** Java dùng `java.io.UncheckedIOException`, một **unchecked exception** bọc bên trong một `IOException`. Nó được giới thiệu trong Java 8 và vẫn được sử dụng ở Java hiện đại.

- Lỗi I/O **khi mở tệp/thư mục**: nhiều factory như `Files.lines`, `Files.list`, `Files.walk` khai báo **`throws IOException`**.
- Lỗi I/O **sau khi stream đã được tạo**, trong lúc đọc/duyệt: API có thể ném **`UncheckedIOException`** từ thao tác stream đang kích hoạt việc đọc.
- Lỗi nghiệp vụ hoặc bug trong lambda: có thể là `IllegalArgumentException`, `NullPointerException` hoặc một runtime exception **khác**; không được giả định mọi lỗi trong stream là I/O.

Bài này tập trung vào sự khác nhau đó, cách phân loại lỗi, đóng tài nguyên, xử lý kết quả đã duyệt một phần và các chiến lược an toàn khi đọc/duyệt tệp.

## 2. `UncheckedIOException` là lớp gì?

Khai báo rút gọn trong Java:

```java
public class UncheckedIOException extends RuntimeException {
    public UncheckedIOException(IOException cause);
    public UncheckedIOException(String message, IOException cause);
    @Override
    public IOException getCause();
}
```

Đây là **sơ đồ chữ ký API**, không phải source code tạo lại lớp. Những điểm quan trọng:

1. `UncheckedIOException` là **`RuntimeException`**, nên method không cần bắt/khai báo checked exception này.
2. Nó **chỉ nhận một `IOException` làm cause** khi tạo bằng các constructor chuẩn. `getCause()` được override để trả kiểu `IOException`, không chỉ `Throwable` chung chung.
3. Constructor yêu cầu **cause khác `null`**; truyền null dẫn tới `NullPointerException`.
4. Có thể chỉ cung cấp cause hoặc kèm thêm message có ngữ cảnh như tên thao tác I/O.
5. Đây là cơ chế **chuyển hình thức truyền lỗi** qua một API không hỗ trợ checked exceptions; nó **không sửa lỗi tệp**, không tự retry và không thể biến phép duyệt dở thành kết quả đúng.

```java
IOException diskError = new IOException("disk failure");
UncheckedIOException wrapper =
    new UncheckedIOException("reading input failed", diskError);

boolean sameCause = wrapper.getCause() == diskError; // true
boolean unchecked = wrapper instanceof RuntimeException; // true
```

Đây là snippet trong method, cần `import java.io.IOException;` và `import java.io.UncheckedIOException;`. Bọc lỗi giữ lại cause và stack trace liên quan để lớp nhận biết lỗi có thể xử lý, thay vì nuốt exception hoặc chỉ ghi message.

### 2.1. `IOException` và `UncheckedIOException` không thay thế nhau ở mọi tầng

| Tình huống | Kiểu lỗi thường gặp | Cách hiểu |
| --- | --- | --- |
| `Files.lines(missingPath)` không mở được tệp | `IOException`, có thể là `NoSuchFileException` | Lỗi khi **tạo/mở** tài nguyên |
| `Files.walk(start)` lỗi khi truy cập start | `IOException` | Factory chưa trả stream hợp lệ |
| `Files.walk(start)` đã trả stream, sau đó duyệt sâu lỗi | `UncheckedIOException` | Lỗi I/O **trong lazy traversal** |
| `Files.list(dir)` đã trả stream, sau đó đọc danh sách lỗi | `UncheckedIOException` | Lỗi đọc entry sau lúc mở |
| `Files.lines(path, charset)` đọc bị lỗi hoặc giải mã không hợp lệ sau lúc mở | `UncheckedIOException` | Lỗi khi tiêu thụ stream |
| `BufferedReader.lines()` bị `readLine()` ném `IOException` | `UncheckedIOException` | Reader chuyển checked lỗi thành unchecked |
| Lambda `Integer.parseInt("bad")` | `NumberFormatException` | Lỗi dữ liệu, **không phải I/O** |
| Caller đưa `null` vào API yêu cầu non-null | Có thể `NullPointerException` | Lỗi tham số, không nên gắn nhãn I/O |
| `Files.walkFileTree` và visitor nhận `IOException` | Checked `IOException` hoặc visitor xử lý riêng | API duyệt theo callback, không phải stream lazy |

**Không catch mọi `RuntimeException` rồi tự động biến thành “lỗi đọc tệp”.** Điều đó che bug và có thể gây hành vi fallback sai.

## 3. Vì sao lỗi có thể xuất hiện muộn? Hiểu lazy stream

Một Stream có **hai thời điểm**:

1. **Thiết lập nguồn/pipeline:** tạo stream từ tệp hoặc thư mục, thêm `filter`, `map`, `peek`. Với nhiều API, phần tử chưa được lấy hết và lambda chưa chạy.
2. **Terminal operation:** `forEach`, `collect`, `count`, `reduce`, `findFirst`... bắt đầu yêu cầu phần tử từ nguồn. I/O có thể phát sinh khi thực thi terminal operation.

```java
Stream<String> stream = Files.lines(path, StandardCharsets.UTF_8);
Stream<String> filtered = stream.filter(s -> !s.isEmpty());
// Chưa có cam kết toàn bộ nội dung tệp đã được đọc.

long nonEmpty = filtered.count();
// Chính lúc tiêu thụ này có thể gặp UncheckedIOException.
```

Đây là **snippet minh họa**, chưa có đóng stream: code production phải đặt `Files.lines` trong `try-with-resources` ở cùng phạm vi sử dụng. Cần import `Files`, `StandardCharsets`, `Stream` và biến `path`.

### 3.1. Vị trí catch quyết định có bắt được lỗi hay không

**Chưa đủ:** chỉ bắt `IOException` quanh lời gọi mở tệp rồi trả stream ra ngoài, để consumer tự duyệt mà không có chiến lược xử lý lỗi.

```java
Stream<String> open(Path path) throws IOException {
    return Files.lines(path, StandardCharsets.UTF_8);
}
// Consumer ở nơi khác có thể nhận UncheckedIOException
// trong forEach/collect/count và còn phải nhớ close stream.
```

Đây là method snippet. Trong thực tế, trả một stream đang giữ resource ra bên ngoài đẩy trách nhiệm **đóng tệp** và **bắt lỗi trong lúc duyệt** cho consumer, rất dễ bị quên.

**Mẫu gọn hơn** khi service sở hữu toàn bộ lần đọc:

```java
List<String> loadLines(Path path) throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        try {
            return lines.collect(Collectors.toList());
        } catch (UncheckedIOException failure) {
            throw failure.getCause(); // chuyển về checked IOException
        }
    }
}
```

Đây là method snippet cần import `List`, `Path`, `Stream`, `Collectors`, `Files`, `StandardCharsets`, `UncheckedIOException`, `IOException`. Nó **cố ý** công bố một hợp đồng checked `throws IOException` cho tất cả lỗi I/O trong lúc đọc. Nếu phát sinh lỗi khác như một bug trong collector, lỗi đó vẫn được lan truyền như chính nó.

Lưu ý: thao tác đóng stream trong `try-with-resources` cũng có thể phát sinh lỗi; với `Files.lines` trên JDK hiện đại, lỗi close ở stream có thể được bọc thành `UncheckedIOException`. Nếu một API cần **tuyệt đối chuẩn hóa mọi lỗi I/O thành checked IOException**, phải thiết kế phạm vi catch bao trùm cả bước close và quyết định cách giữ suppressed exceptions, thay vì chỉ catch bên trong terminal operation như snippet trên. Với nhiều service, giữ nguyên runtime wrapper ở boundary đơn giản hơn và xử lý tại một lớp duy nhất.

### 3.2. Intermediate operations không nhất thiết chạy ngay

`Stream.filter`/`map` tạo pipeline. `peek` thường dùng để quan sát/debug, nhưng không nên dựa vào nó để ghi nhận **tất cả phần tử**: short-circuit operators như `findFirst`/`anyMatch` hoặc tối ưu hóa stream có thể khiến một số phần tử không được chạy qua action bạn nghĩ.

```java
try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    Optional<String> first = lines.findFirst();
    // Chỉ cần một phần dữ liệu; không có nghĩa toàn bộ tệp hợp lệ.
}
```

Đây là snippet, cần `Optional`. Việc lấy thành công phần tử đầu tiên **không chứng minh không có I/O error ở những dòng tiếp theo**. Nếu nghiệp vụ yêu cầu kiểm tra toàn bộ file, hãy thực sự tiêu thụ toàn bộ nội dung và xử lý lỗi theo contract.

## 4. `BufferedReader.lines()`: mô hình điển hình của lỗi phát sinh khi duyệt

`BufferedReader.lines()` là API có từ Java 8, trả `Stream<String>` được nạp từ các lời gọi `readLine()`. Nếu có `IOException` khi đọc, stream báo **`UncheckedIOException`** ở method tiêu thụ.

```java
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    reader.lines().forEach(System.out::println);
} catch (IOException openOrCloseError) {
    // Có thể lỗi ở bước mở/đóng BufferedReader.
} catch (UncheckedIOException readError) {
    IOException rootCause = readError.getCause();
    // Lỗi trong lúc terminal operation tiêu thụ dòng.
}
```

Đây là snippet trong method, cần `BufferedReader`, `IOException`, `UncheckedIOException`, `Files`, `StandardCharsets`. Có hai đường lỗi khác nhau: constructor `Files.newBufferedReader` và việc đọc lười qua `lines()`. Dùng cả hai nhánh catch để không bỏ sót.

### 4.1. `BufferedReader.lines()` không tự sở hữu trách nhiệm đóng reader

`BufferedReader.lines()` trả stream tham chiếu tới reader đang mở; **đóng Stream không thay thế một cách đáng tin cho việc đóng BufferedReader**, vì API này không cam kết chuyển quyền sở hữu resource sang stream. Hãy đặt **`BufferedReader` trong `try-with-resources`** như ví dụ, hoặc chủ động gắn `onClose` nếu đang xây abstraction cần quản lý close.

Ngược lại, `Files.lines(path)` trả stream **sở hữu tham chiếu tới tệp đang mở**, và Javadoc yêu cầu **đóng chính stream** để giải phóng tệp. Phân biệt trách nhiệm của nguồn dữ liệu giúp tránh leak file descriptor.

### 4.2. Không tương tác reader trực tiếp trong lúc stream đang tiêu thụ

Javadoc `BufferedReader.lines` yêu cầu không thao tác reader trong lúc terminal operation của stream đang diễn ra; nếu không, kết quả không được xác định.

```java
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    Stream<String> lines = reader.lines();
    // Không gọi reader.readLine() từ luồng khác
    // trong lúc lines.forEach(...) đang xử lý.
}
```

Đây là snippet. Không dùng một `BufferedReader` làm nguồn đọc **đồng thời** cho nhiều stream hoặc một luồng khác mà không có quy tắc đồng bộ đặc biệt. API stream không biến bộ đọc tệp tuần tự thành một nguồn có thể đọc song song vô điều kiện.

## 5. `Files.lines()`: lỗi mở tệp và lỗi đọc dữ liệu có thể khác loại

`Files.lines(Path, Charset)` và `Files.lines(Path)` có từ Java 8. Đặc điểm:

- Lời gọi `Files.lines(...)` **có thể ném checked IOException ngay khi mở file**.
- Các dòng được đọc lười khi terminal operation cần chúng; lỗi đọc hoặc dữ liệu **không giải mã được** sau khi stream đã trả được bọc trong `UncheckedIOException`.
- `Files.lines(path)` mặc định dùng **UTF-8**, nhưng truyền `StandardCharsets.UTF_8` tường minh có thể giúp thể hiện rõ hợp đồng của service.
- Stream trả về phải được đóng bằng `try-with-resources`; chỉ thu thập hết dòng vào `List` **không tự cam kết đóng tệp**.
- Không sửa file trong lúc terminal operation đang tiêu thụ; tài liệu API cảnh báo kết quả lúc đó có thể không xác định.

```java
Path path = Paths.get("data", "events.txt");

try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    long errors = lines.filter(line -> line.startsWith("ERROR")).count();
    System.out.println(errors);
} catch (UncheckedIOException duringRead) {
    // Lỗi xảy ra khi stream đọc/đóng tệp sau bước mở.
} catch (IOException duringOpen) {
    // Không mở được tệp.
}
```

Đây là snippet, cần import `Paths`, `Path`, `Files`, `StandardCharsets`, `Stream`, `UncheckedIOException`, `IOException`. Nếu dùng pattern catch ở tầng service, cả hai trường hợp đều nên được ánh xạ sang error code có ý nghĩa, không gửi raw filesystem path/stack trace ra người dùng ngoài.

### 5.1. Lỗi encoding là lỗi I/O, không phải chỉ một dòng sai nghiệp vụ

Ví dụ file thực tế chứa bytes không phải UTF-8 hợp lệ trong khi client yêu cầu UTF-8. `Files.lines` có thể báo lỗi giải mã trong quá trình đọc bằng `UncheckedIOException`. Đừng bắt lỗi đó rồi bỏ qua một dòng mà vẫn tuyên bố “file đã đọc hoàn chỉnh”.

Nếu định dạng tệp là Windows-1252/UTF-16, hãy xác định charset theo contract bằng `StandardCharsets` hoặc `Charset.forName` thích hợp; không đổi charset ngẫu nhiên chỉ để exception biến mất. Một input cần chuyển đổi encoding có thể phải được xử lý như một bước import riêng.

### 5.2. `readAllLines` khác `lines` ở thời điểm lỗi và bộ nhớ

`Files.readAllLines(path, charset)` đọc **toàn bộ nội dung** thành `List<String>` rồi trả; nó khai báo `throws IOException`, đóng file trong method. Nó đơn giản khi file nhỏ nhưng dùng nhiều bộ nhớ khi file lớn.

`Files.lines(path, charset)` tiết kiệm bộ nhớ hơn trong nhiều kịch bản streaming, nhưng người dùng phải **đóng stream**, chấp nhận lỗi có thể xảy ra khi duyệt và cẩn thận nếu không tiêu thụ hết nội dung. Không có một API "tốt hơn tuyệt đối"; lựa chọn theo kích thước và yêu cầu xử lý.

## 6. `Files.list()`: liệt kê thư mục theo stream lười

`Files.list(dir)` trả stream của **các entry trực tiếp** dưới `dir`, **không đi sâu đệ quy**. Mở thư mục có thể ném checked `IOException`; sau khi đã trả stream, I/O lúc đọc entry có thể bị bọc thành `UncheckedIOException`.

```java
try (Stream<Path> entries = Files.list(directory)) {
    entries.forEach(path -> {
        // Xử lý từng path trực tiếp trong directory.
    });
}
```

Đây là snippet trong method với `directory` là `Path` hợp lệ và được khai báo `throws IOException` hoặc xử lý catch; cần `Stream` và `Files`.

**Bẫy:** Hệ thống file có thể thay đổi trong khi listing đang diễn ra. Stream của `Files.list` là **weakly consistent**: không đóng băng nội dung thư mục, có thể phản ánh hoặc không phản ánh thay đổi xảy ra sau lúc tạo. Vì vậy, danh sách trả về không phải snapshot giao dịch của hệ thống file.

### 6.1. `Files.list` khác `Files.walk`

| API | Phạm vi | Ghi chú |
| --- | --- | --- |
| `Files.list(dir)` | Một cấp thư mục, liệt kê entry con | Không đệ quy, trả stream giữ thư mục mở |
| `Files.walk(root)` | Duyệt sâu cây từ root | Có thể giới hạn `maxDepth`, stream chứa cả root |
| `Files.find(root,maxDepth,predicate)` | Duyệt cây và lọc với attributes | Predicate nhận cả `Path` và `BasicFileAttributes` |
| `Files.walkFileTree(root,visitor)` | Duyệt bằng callback/visitor | Xử lý `visitFileFailed`, `postVisitDirectory` theo policy |

`Files.list` không tự liệt kê metadata chi tiết của từng entry. Một lời gọi thêm như `Files.size(entry)` trong `map` lại có thể ném checked `IOException`; đó là lỗi **của thao tác trong lambda**, cần xử lý riêng ngoài lỗi liệt kê thư mục.

## 7. `Files.walk()`: duyệt sâu và lỗi giữa chừng

`Files.walk(start)` trả `Stream<Path>` được tạo theo kiểu đi sâu từng thư mục, lazy. Nó thường bắt đầu bằng chính `start`; nếu `start` là thư mục, các entry con rồi hậu duệ xuất hiện trong quá trình tiêu thụ.

```java
try (Stream<Path> paths = Files.walk(root)) {
    List<Path> files = paths
        .filter(Files::isRegularFile)
        .collect(Collectors.toList());
}
```

Đây là snippet cần import `Files`, `Path`, `Stream`, `List`, `Collectors` và biến `root`. Lệnh mở có thể ném checked `IOException`; lỗi I/O phát sinh trong lúc mở thư mục con **sau khi stream trả về** được bọc thành `UncheckedIOException`.

### 7.1. `walk` không “bỏ qua mọi thư mục lỗi” để tiếp tục

Nếu việc duyệt lazy gặp một `IOException` không xử lý được, stream có thể kết thúc bằng `UncheckedIOException`. **Không có bảo đảm** `Stream` này sẽ tự chuyển sang thư mục anh em và tiếp tục như thể không có vấn đề.

Nếu nghiệp vụ **bắt buộc bỏ qua những thư mục lỗi có chọn lọc**, xem `Files.walkFileTree` với `FileVisitor.visitFileFailed` hoặc một traversal riêng có policy. Đừng catch lỗi ngoài `forEach` rồi cố tiếp tục tiêu thụ lại **cùng stream đã lỗi**; sau một terminal operation có exception, không được tái sử dụng stream như mới.

### 7.2. `maxDepth` giúp giới hạn phạm vi và chi phí

`Files.walk(root,maxDepth)` giới hạn số cấp:

- `maxDepth=0`: chỉ truy cập root.
- `maxDepth=1`: root và các entry con trực tiếp.
- `maxDepth=Integer.MAX_VALUE`: ý định duyệt toàn cây (cũng là overload `walk(root)`).

```java
try (Stream<Path> paths = Files.walk(root, 1)) {
    long entries = paths.count();
}
```

Đây là snippet, cần xử lý checked `IOException` cho factory. Với directory lớn hoặc input không đáng tin, giới hạn depth, danh sách file được phép xử lý, số phần tử và deadline có thể cần thiết; **maxDepth không phải giới hạn số lượng phần tử**.

### 7.3. Symbolic links, vòng lặp và quyền truy cập

`Files.walk` **không tự theo symbolic links** theo mặc định. Nếu truyền `FileVisitOption.FOLLOW_LINKS`, file tree có thể chứa chu trình; JDK phát hiện chu trình và có thể báo `FileSystemLoopException`, là một loại `FileSystemException`/`IOException`, được bọc theo đường lazy stream.

Không bật FOLLOW_LINKS nếu hệ thống không yêu cầu, nhất là khi duyệt thư mục do người dùng kiểm soát. Khi cần theo symlink, đặt giới hạn depth, xác minh chính sách an toàn đường dẫn và xử lý lỗi loop theo contract.

## 8. `Files.find()`: duyệt kết hợp lọc theo attributes

`Files.find(start,maxDepth,matcher)` và overload có options trả `Stream<Path>` được duyệt lười tương tự `Files.walk`. Khác biệt hữu ích là matcher nhận **`Path` và `BasicFileAttributes`**, nên có thể tránh việc truy vấn lại attributes trong một `filter` riêng khi cần phân loại file.

```java
try (Stream<Path> found = Files.find(
        root, 2,
        (path, attributes) ->
            attributes.isRegularFile() && attributes.size() > 0)) {
    long nonEmptyFiles = found.count();
}
```

Đây là snippet cần import `Files`, `Path`, `Stream` và biến `root`; method bao ngoài khai báo hoặc xử lý `IOException`. Thao tác duyệt vẫn có thể thất bại về I/O sau khi tạo stream và bị bọc `UncheckedIOException`.

Đừng cho rằng predicate này được chạy trên một snapshot bất biến của filesystem. Trong lúc xử lý, file có thể bị đổi/xóa; thông tin attributes có thể cũ trước khi bạn mở file. Nếu ứng dụng yêu cầu trạng thái nhất quán, cần một thiết kế giao dịch/đối chiếu riêng; `Files.find` không giữ khóa filesystem cho mọi tệp.

## 9. Lỗi do `Stream` duyệt nguồn khác lỗi do lambda xử lý từng tệp

Hai loại exception thường bị nhầm:

**A. Nguồn stream không lấy được phần tử tiếp theo:**

```java
try (Stream<Path> paths = Files.walk(root)) {
    paths.forEach(this::recordPath);
}
// Nếu walker không thể duyệt thư mục con, nguồn có thể
// ném UncheckedIOException từ terminal operation.
```

**B. Lambda nhận Path rồi làm I/O khác và gặp checked exception:**

```java
try (Stream<Path> paths = Files.list(root)) {
    paths.map(path -> {
        try {
            return Files.size(path);
        } catch (IOException error) {
            throw new UncheckedIOException(
                "Cannot read file size: " + path.getFileName(),
                error);
        }
    }).forEach(System.out::println);
}
```

Cả hai là snippet trong class/method phù hợp, cần `Files`, `Path`, `Stream`, `IOException`, `UncheckedIOException`; snippet A giả định có method `recordPath`. Trong B, `Stream.map` nhận một `Function<Path,Long>` không khai báo checked `IOException`, nên cần bắt lỗi và **bọc lại có ngữ cảnh**. Đó là code **tự ném** `UncheckedIOException`, không phải bản thân `Files.list` bắt buộc tự bọc lỗi của `Files.size`.

### 9.1. Java lambda không tự chấp nhận checked `IOException`

Đoạn sau **không biên dịch** khi `Files.size` khai báo checked exception:

```java
// Không compile:
// Stream<Path> paths = ...;
// paths.map(path -> Files.size(path)).forEach(System.out::println);
```

Java không tự đổi tất cả checked exceptions trong lambda thành unchecked. Cần `try/catch` trong lambda, một helper có chiến lược lỗi rõ ràng, hoặc API xử lý tuần tự trong method `throws IOException`. Đừng vội tạo generic “sneaky throws” để trốn checked exception vì làm hợp đồng I/O khó nhìn thấy hơn.

### 9.2. Helper để bọc đúng lỗi I/O

```java
static long fileSizeUnchecked(Path file) {
    try {
        return Files.size(file);
    } catch (IOException error) {
        throw new UncheckedIOException(
            "Cannot read size: " + file.getFileName(),
            error);
    }
}
```

Đây là **method snippet** cần import `Path`, `Files`, `IOException`, `UncheckedIOException`. Việc thêm tên file vào exception kỹ thuật hữu ích cho log nội bộ; nhưng trong hệ thống có dữ liệu nhạy cảm, cần **redact** hoặc thay bằng ID an toàn khi xuất thông báo ra client.

### 9.3. Không bọc mọi `RuntimeException` thành `UncheckedIOException`

`UncheckedIOException` nhận `IOException` làm cause. Một lỗi `NullPointerException` do code là loại vấn đề khác. Không tạo `new IOException(originalRuntime)` rồi bọc lại chỉ để tất cả lỗi trông như I/O: làm mất taxonomy và khiến chương trình xử lý sai. Tách lỗi dữ liệu, lỗi cấu hình, lỗi I/O và bug lập trình.

## 10. Lỗi trong lúc duyệt có thể để lại xử lý một phần

Lazy traversal thường xử lý từng phần tử trước khi lấy phần tử kế tiếp. Nếu sau hai dòng đầu I/O mới lỗi tại dòng thứ ba, hai callback trước có thể **đã chạy**.

```text
Dòng 1 -> forEach: ghi DB / tăng counter
Dòng 2 -> forEach: ghi DB / tăng counter
Dòng 3 -> đọc lỗi IOException
      -> UncheckedIOException được ném ra
      -> terminal operation dừng bất thường
```

**Không nên coi đây là kết quả thành công hoàn chỉnh**, cũng không nên giả định Java tự rollback những callback của hai dòng đầu.

### 10.1. `collect` và `forEach` có mức rủi ro khác nhau

- `collect(toList())` thông thường **không trả List hoàn chỉnh cho caller** nếu terminal operation ném exception. Nhưng những xử lý phụ nằm trong `map`/`peek`/collector tùy biến trước lỗi vẫn có thể đã chạy.
- `forEach` cập nhật database, gửi email hoặc `list.add` bên ngoài có thể tạo **side effects** trước khi gặp lỗi.
- Với `parallel()`, một số task có thể tiếp tục hoặc hoàn thành sau khi một nhánh đã lỗi; số phần tử có side effects có thể không đoán được bằng thứ tự tuyến tính.
- `findFirst` có thể trả thành công trước khi chạm vùng tệp hỏng; điều đó **không** chứng minh phần còn lại của tệp hợp lệ.

Vì vậy khi import tệp cần **all-or-nothing**, đừng chỉ dùng `Files.lines(...).forEach(this::persist)`. Cân nhắc đọc/validate từng bản ghi vào staging, transaction database, rồi commit khi toàn bộ bước cần kiểm chứng đã thành công. Với file lớn, có thể dùng batch transaction và cơ chế đánh dấu trạng thái nhập một phần theo hợp đồng nghiệp vụ.

### 10.2. Kiểm soát side effect và retry

Nếu một lần import đã xử lý 2.000 dòng rồi gặp lỗi, retry nguyên file có thể tạo dữ liệu trùng. Hệ thống cần một trong các chính sách:

1. **Idempotent import:** mỗi bản ghi có khóa nghiệp vụ/unique constraint, retry an toàn.
2. **Staging + commit:** chưa công bố dữ liệu tới khi đã đọc và validate xong toàn bộ lô.
3. **Checkpoint/resume:** lưu trạng thái đọc đã xác nhận theo thiết kế có thể tiếp tục.
4. **Best effort:** bỏ qua lỗi theo chính sách được công bố và **báo rõ dữ liệu thiếu**, không gọi là thành công đầy đủ.

`UncheckedIOException` chỉ báo **có lỗi I/O**. Chính sách rollback/retry thuộc về nghiệp vụ và kho dữ liệu, không phải Stream API.

## 11. Tài nguyên phải được đóng ngay cả khi duyệt lỗi

`Files.lines`, `Files.list`, `Files.walk` và `Files.find` trả stream có liên kết với tệp hoặc directory handles đang mở. Cần dùng `try-with-resources`:

```java
try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
         .forEach(System.out::println);
} catch (UncheckedIOException duringTraversal) {
    // Phân loại nguyên nhân / báo lỗi công việc.
} catch (IOException duringOpen) {
    // Không mở được root.
}
```

`try-with-resources` thực hiện `close()` khi rời block, kể cả terminal operation ném exception. Nó **không** biến kết quả duyệt dở thành thành công và cũng không tự trả về những file đã được duyệt.

### 11.1. Đóng stream khác tiêu thụ hết stream

`Stream.count()` hoặc `forEach` đi hết pipeline **không thay thế `close()`** của nguồn I/O. Một vài stream thuần từ `List` không cần đóng tài nguyên ngoài, nhưng các stream do `Files` trả trong bài này có resource cần giải phóng. Đóng sớm giúp tránh giữ file descriptors, directory handles và gây lỗi xóa/move file trên một số OS.

### 11.2. Trường hợp đóng cũng thất bại

Trong `try-with-resources`, nếu code bên trong ném exception và thao tác `close()` cũng ném exception, Java thường **giữ exception chính** và đính kèm lỗi đóng vào danh sách `getSuppressed()`. Do đó, khi điều tra, xem cả exception chain/suppressed exceptions (trong log bảo vệ) nếu kết quả chưa rõ.

Đối với `Files.lines`, lỗi I/O khi close có thể được bọc thành `UncheckedIOException` theo Javadoc. Với `BufferedReader` sở hữu trực tiếp trong try-with-resources, `close` có thể ném checked `IOException`. Thiết kế catch quanh **toàn bộ** try block nếu mục tiêu là ánh xạ nhất quán cả lỗi đọc và lỗi đóng; không chỉ catch trong lambda.

### 11.3. Không trả stream từ helper rồi quên tài nguyên

```java
Stream<Path> listFiles(Path root) throws IOException {
    return Files.walk(root);
}
```

Đây là snippet **có thể hợp lệ** nếu hợp đồng helper quy định caller phải gọi `close`. Nhưng việc trao stream cho caller làm việc quản lý resource khó theo dõi. Với những API service có thể dùng đơn giản hơn, hãy cân nhắc **consumer callback** hoặc method tự thu thập/đóng trước khi trả kết quả.

Ví dụ API theo callback:

```java
void visitPaths(Path root, Consumer<Path> visitor)
        throws IOException {
    try (Stream<Path> paths = Files.walk(root)) {
        paths.forEach(visitor);
    }
}
```

Snippet này cần `Consumer`, `Stream`, `Path`, `Files` và có thể lan truyền `UncheckedIOException` trong runtime. Helper sở hữu tài nguyên và đóng đúng lúc, caller không phải nhớ đóng stream; tuy nhiên vẫn cần tài liệu hóa **hai dạng lỗi** để caller phân loại.

## 12. Muốn tiếp tục khi một entry lỗi: chọn `walkFileTree` khi phù hợp

Một `Stream<Path>` của `Files.walk` có thể dừng vì lỗi lấy phần tử từ nguồn. Nếu cần **chính sách xử lý theo từng file/directory** với khả năng bỏ qua một số lỗi, `Files.walkFileTree` và `FileVisitor` thường biểu đạt rõ hơn:

```java
Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
    @Override
    public FileVisitResult visitFileFailed(
            Path file, IOException error) throws IOException {
        recordSkippedFile(file, error);
        return FileVisitResult.CONTINUE;
    }

    @Override
    public FileVisitResult postVisitDirectory(
            Path dir, IOException error) throws IOException {
        if (error != null) {
            recordDirectoryFailure(dir, error);
        }
        return FileVisitResult.CONTINUE;
    }
});
```

Đây là **snippet kiến trúc**, cần `SimpleFileVisitor`, `FileVisitResult`, `Files`, `Path`, `IOException` và hai method `recordSkippedFile`/`recordDirectoryFailure` do ứng dụng tự định nghĩa. Lớp visitor nhận được lỗi ở `visitFileFailed` hoặc `postVisitDirectory` theo đường duyệt của API, giúp policy quyết định **CONTINUE**, **SKIP_SIBLINGS** hoặc **TERMINATE** khi phù hợp.

### 12.1. Khi nào vẫn cần `throws IOException`?

`Files.walkFileTree` khai báo `throws IOException`; lỗi do visitor tự ném, lỗi không được xử lý theo đường duyệt hoặc một số lỗi nền có thể được truyền ra. **Không** tuyên bố chỉ override `visitFileFailed` là đã bảo đảm tuyệt đối không có exception. Nếu nghiệp vụ cần ghi nhận lỗi per-file, vẫn phải xác định policy với lỗi ở `postVisitDirectory`, lỗi của visitor và lỗi commit ngoài I/O.

### 12.2. Không mọi lỗi đều nên bỏ qua

Nếu duyệt thư mục backup để lập danh sách bắt buộc đầy đủ, việc gặp một thư mục không truy cập được mà trả `CONTINUE` sẽ tạo **danh sách thiếu**. Một hệ thống backup/audit phải đánh dấu job là **PARTIAL/FAILED** hoặc dừng, không thể báo SUCCESS chỉ vì visitor đi hết các phần còn truy cập được.

Với ứng dụng tìm kiếm thumbnail nơi tính đầy đủ không quan trọng, best-effort có thể hợp lý; nhưng UI/log phải thể hiện số item bỏ qua và khả năng kết quả không đầy đủ.

### 12.3. Chống symlink loops và path escapes

`Files.walkFileTree` mặc định không theo symbolic links. Nếu bật `FOLLOW_LINKS`, visitor có thể gặp `FileSystemLoopException` trong `visitFileFailed`. Với thư mục do người dùng kiểm soát, cần kết hợp chính sách root, depth, symlink và quyền truy cập trước khi dùng kết quả làm thao tác xóa/copy. Không coi việc duyệt bằng stream hoặc visitor tự là một sandbox path-security.

## 13. Mẫu chiến lược xử lý lỗi theo loại

Một lớp xử lý tốt thường phân biệt:

| Loại lỗi | Ví dụ | Chiến lược |
| --- | --- | --- |
| Không mở được input | `NoSuchFileException`, `AccessDeniedException` trong `Files.lines` | Trả lỗi rõ input và quyền |
| Lỗi lazy traversal | `UncheckedIOException` từ `Files.walk`/`list` | Gắn job FAILED hoặc PARTIAL theo contract, luôn đóng stream |
| Mất kết nối/thiết bị I/O | `IOException` làm cause | Retry có điều kiện nếu nguồn hỗ trợ và idempotent |
| Encoding không phù hợp | Lỗi decode được bọc | Kiểm tra charset/file encoding, không tự bỏ dòng |
| File bị thay đổi khi đang duyệt | Có thể IOException hoặc kết quả yếu nhất quán | Xác định snapshot/locking/versioning nếu yêu cầu |
| Lỗi parsing nội dung | `NumberFormatException`, lỗi JSON/domain | Báo lỗi dữ liệu, không đổi thành I/O |
| Lỗi do `Stream` sử dụng sai | `IllegalStateException` khi reuse stream | Sửa code, không retry filesystem |
| Lỗi khi close | IOException/UncheckedIOException tùy resource | Ghi nhận cả lỗi chính và suppressed, tránh leak |

### 13.1. Lấy cause thật để phân loại

```java
try {
    importFile();
} catch (UncheckedIOException failure) {
    IOException io = failure.getCause();
    if (io instanceof NoSuchFileException) {
        // Có thể file bị xóa sau khi liệt kê.
    } else if (io instanceof AccessDeniedException) {
        // Quyền đọc có thể thay đổi.
    } else {
        // Lỗi I/O khác: báo/ghi nhận theo policy.
    }
}
```

Đây là snippet cần `importFile` do ứng dụng định nghĩa và import `IOException`, `UncheckedIOException`, `NoSuchFileException`, `AccessDeniedException`. Các subtype IOException phụ thuộc filesystem/provider/OS; không nên suy ra rằng mọi lỗi quyền đều **bắt buộc** dùng AccessDeniedException. Nếu cần chẩn đoán từ log, giữ các metadata an toàn và cause chain.

### 13.2. Chỉ bóc wrapper ở ranh giới muốn đổi hợp đồng

`UncheckedIOException.getCause()` trả `IOException`. Nếu method service đã khai báo `throws IOException`, bạn có thể chuyển lại checked exception cho caller. Nhưng không cần bóc ra ở mọi method trong pipeline; quá nhiều catch/rethrow làm code khó bảo trì và có thể đánh mất ngữ cảnh thao tác.

Có thể tạo error type domain như `IMPORT_IO_ERROR`, `PARTIAL_IMPORT` với định danh job/đường dẫn đã redacted, thay vì đưa raw exception ra API HTTP.

### 13.3. Đừng bắt rồi trả collection rỗng trong mọi trường hợp

```java
// Cách làm rủi ro:
try (Stream<Path> paths = Files.walk(root)) {
    return paths.collect(Collectors.toList());
} catch (IOException | UncheckedIOException error) {
    return Collections.emptyList();
}
```

Đây là **snippet anti-pattern** trong method có kiểu trả `List<Path>`. Trả list rỗng khiến caller tưởng "không có file" trong khi nguồn có thể không mở được hoặc duyệt thất bại sau một phần. Chỉ có thể dùng fallback nếu **nghiệp vụ đã định nghĩa rõ** lỗi đọc = không dữ liệu; thường tốt hơn là báo lỗi hoặc trả một kết quả có trạng thái `PARTIAL/FAILED`.

## 14. Chương trình chạy được: lỗi lazy stream giả lập và duyệt tệp thật

Ví dụ sau được viết cho **Java 8**, sử dụng những API vẫn còn áp dụng ở JDK hiện đại. Để không phụ thuộc vào quyền truy cập ngẫu nhiên hay thời điểm file bị xóa, nó tạo một `FailingReader` cố ý ném `IOException` vào lời gọi `readLine()` thứ ba. `BufferedReader.lines()` sẽ chuyển lỗi này thành **`UncheckedIOException` trong terminal operation**.

Chương trình còn tạo **thư mục tạm**, ghi hai tệp nhỏ, dùng `Files.lines`/`list`/`walk`/`find`, thử mở một tệp không tồn tại và trình bày cách **lambda tự bọc checked IOException**. Cuối cùng, nó xóa thư mục/tệp tạm; không ghi vào source repo.

Lưu thành **UncheckedIOExceptionTraversalDemo.java**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class UncheckedIOExceptionTraversalDemo {
    static final class FailingReader extends BufferedReader {
        private final int failAtCall;
        private int readCalls;

        FailingReader(String text, int failAtCall) {
            super(new StringReader(text));
            this.failAtCall = failAtCall;
        }

        @Override
        public String readLine() throws IOException {
            readCalls++;
            if (readCalls == failAtCall) {
                throw new IOException("simulated read failure");
            }
            return super.readLine();
        }
    }

    public static void main(String[] args) throws IOException {
        IOException original = new IOException("disk failure");
        UncheckedIOException wrapper = new UncheckedIOException(
            "wrapped failure", original);
        System.out.println("Wrapper cause is IOException: "
            + (wrapper.getCause() == original));
        System.out.println("Wrapper runtime: "
            + (wrapper instanceof RuntimeException));

        try (BufferedReader normal =
                new BufferedReader(new StringReader("one\ntwo\n"))) {
            System.out.println("Normal reader lines: "
                + normal.lines().count());
        }

        List<String> seen = new ArrayList<>();
        try (BufferedReader broken =
                new FailingReader("alpha\nbeta\ngamma\n", 3)) {
            Stream<String> lines = broken.lines();
            System.out.println("Lazy stream created: true");
            try {
                lines.forEach(seen::add);
            } catch (UncheckedIOException error) {
                System.out.println("Lazy traversal cause: "
                    + error.getCause().getMessage());
            }
        }
        System.out.println("Lines visited before failure: " + seen);
        System.out.println("Traversal did not finish: " + (seen.size() == 2));

        Path root = Files.createTempDirectory("unchecked-io-example-");
        try {
            Path textFile = root.resolve("alpha.txt");
            Path logFile = root.resolve("beta.log");
            Files.write(textFile, Arrays.asList("first", "second"),
                StandardCharsets.UTF_8);
            Files.write(logFile, Arrays.asList("log"),
                StandardCharsets.UTF_8);

            try (Stream<String> lines =
                    Files.lines(textFile, StandardCharsets.UTF_8)) {
                System.out.println("Files.lines count: " + lines.count());
            }
            try (Stream<Path> entries = Files.list(root)) {
                System.out.println("Files.list count: " + entries.count());
            }
            try (Stream<Path> paths = Files.walk(root, 1)) {
                List<String> names = paths
                    .filter(Files::isRegularFile)
                    .map(p -> p.getFileName().toString())
                    .sorted()
                    .collect(Collectors.toList());
                System.out.println("Files.walk names: " + names);
            }
            try (Stream<Path> found = Files.find(
                    root, 1, (path, attributes) ->
                        attributes.isRegularFile())) {
                System.out.println("Files.find count: " + found.count());
            }

            Path missing = root.resolve("missing.txt");
            try (Stream<String> ignored =
                    Files.lines(missing, StandardCharsets.UTF_8)) {
                ignored.count();
            } catch (NoSuchFileException error) {
                System.out.println("Missing file at open: "
                    + error.getClass().getSimpleName());
            }

            AtomicInteger alreadyRead = new AtomicInteger();
            try {
                Stream.of(textFile, missing).mapToLong(path -> {
                    try {
                        long size = Files.size(path);
                        alreadyRead.incrementAndGet();
                        return size;
                    } catch (IOException error) {
                        throw new UncheckedIOException(
                            "Cannot read file size", error);
                    }
                }).sum();
            } catch (UncheckedIOException error) {
                System.out.println("Lambda cause: "
                    + error.getCause().getClass().getSimpleName());
            }
            System.out.println("Files measured before failure: "
                + alreadyRead.get());
        } finally {
            try (Stream<Path> paths = Files.walk(root)) {
                List<Path> toDelete = paths
                    .sorted(Comparator.reverseOrder())
                    .collect(Collectors.toList());
                for (Path path : toDelete) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
```

Biên dịch và chạy trên JDK có hỗ trợ `--release`:

```bash
javac --release 8 -encoding UTF-8 UncheckedIOExceptionTraversalDemo.java
java UncheckedIOExceptionTraversalDemo
```

Nếu chạy **trực tiếp trên JDK 8**, bỏ tham số `--release 8` khỏi lệnh `javac`. Chương trình sử dụng các API Java 8, không dùng `Files.readString`/`writeString` (được thêm sau Java 8).

**Stdout xác định:**

```text
Wrapper cause is IOException: true
Wrapper runtime: true
Normal reader lines: 2
Lazy stream created: true
Lazy traversal cause: simulated read failure
Lines visited before failure: [alpha, beta]
Traversal did not finish: true
Files.lines count: 2
Files.list count: 2
Files.walk names: [alpha.txt, beta.log]
Files.find count: 2
Missing file at open: NoSuchFileException
Lambda cause: NoSuchFileException
Files measured before failure: 1
```

### 14.1. Giải thích từng nhóm output

1. **Wrapper và cause:** `new UncheckedIOException(message, original)` giữ chính đối tượng `IOException` gốc, và là runtime exception.
2. **Reader thành công:** hai dòng `one` và `two` được đọc bình thường; số dòng bằng 2.
3. **Reader mô phỏng lỗi:** tạo stream vẫn thành công (`Lazy stream created`). Khi `forEach` yêu cầu dòng thứ ba, `readLine` ném checked `IOException`; `BufferedReader.lines` đổi nó thành `UncheckedIOException` và cause message là `simulated read failure`.
4. **Dữ liệu đã xử lý một phần:** `forEach` đã thêm `alpha`, `beta` vào `seen` trước khi lỗi. Hai dòng đó không được rollback. Điều kiện "2 dòng" của bài test chỉ là **hành vi được kiểm soát trong bộ đọc giả lập**, không phải số phần tử cố định của mọi lỗi thật.
5. **`Files.lines`, `list`, `walk`, `find`:** hai tệp tạm hợp lệ được liệt kê/đọc; `Files.walk(root,1)` còn có root nhưng `filter(Files::isRegularFile)` loại root directory. Tên tệp được sort để kết quả ổn định.
6. **Lỗi lúc mở:** `Files.lines(missing)` thất bại **ngay tại factory**, ví dụ tạo `NoSuchFileException` là một checked subtype `IOException`. Không cần chờ terminal operation để thấy lỗi này.
7. **Lambda tự bọc:** `Stream.of(textFile,missing).mapToLong` gọi `Files.size`; tệp đầu đọc được, tệp thứ hai không tồn tại và ném `NoSuchFileException`. Lambda phải bắt checked exception và bọc thành `UncheckedIOException`. Counter đã tăng một lần trước khi lỗi.
8. **Đóng và dọn dữ liệu:** `try-with-resources` đóng stream I/O; block `finally` duyệt thư mục tạm rồi xóa theo thứ tự con trước cha. Bản demo không yêu cầu file ngoài và không thay đổi repository.

## 15. Kiểm thử bắt lỗi đúng giai đoạn

### 15.1. Tách test open failure và traversal failure

| Test | Cách dựng | Kỳ vọng |
| --- | --- | --- |
| Mở tệp không tồn tại | `Files.lines(missing)` | `IOException` (thường `NoSuchFileException`) ngay ở factory |
| Mở tệp hợp lệ | `Files.lines(existing)` | Tạo stream thành công |
| Lỗi giữa chừng | `FailingReader` ném ở lời gọi `readLine` thứ ba | `UncheckedIOException` trong terminal operation |
| Kiểm tra cause | `exception.getCause()` | Chính `IOException` gốc |
| Tác động trước lỗi | `forEach(seen::add)` | Các phần tử đã thấy có thể còn trong list |
| Đóng resource sau lỗi | `try-with-resources` hoặc wrapper test close | Phải đóng trong cả đường thành công/lỗi |
| Lambda truy cập file mất tích | `Files.size(missing)` bên trong `map` | Lambda bọc `IOException` thành `UncheckedIOException` |
| Lỗi xử lý dữ liệu | `Integer.parseInt("abc")` trong `map` | `NumberFormatException`, không đổi thành IOException |
| Bật FOLLOW_LINKS với symlink loop | Môi trường kiểm thử hỗ trợ symlink | Xử lý `FileSystemLoopException`/I/O theo hợp đồng |
| Visitor chọn CONTINUE | `Files.walkFileTree` trên cây có entry lỗi | Report PARTIAL; không đánh dấu SUCCESS đầy đủ |

**Hạn chế:** test dựa vào quyền của file thật có thể không ổn định giữa Windows/Linux, container, CI user hoặc filesystem provider. Do đó nên dùng **bộ đọc giả lập phát sinh lỗi theo số lần đọc** để kiểm tra điều khiển luồng, và chỉ dùng integration test có kiểm soát để kiểm thử permission/symlink/platform-specific behavior.

### 15.2. Không dựa vào message text của JDK

Đừng assert nguyên văn `getMessage()` do filesystem provider tạo cho `NoSuchFileException`/`AccessDeniedException`. Tên path, dấu phân cách và wording có thể khác giữa hệ điều hành/JDK. Kiểm tra **exception class/cause**, error code của ứng dụng và trạng thái job.

### 15.3. Test rằng không báo SUCCESS nếu duyệt dở

Trong hệ thống nhập liệu, sau khi bắt `UncheckedIOException` hãy kiểm tra trạng thái nghiệp vụ là `FAILED` hoặc `PARTIAL` đúng policy. Một test chỉ kiểm tra "không ném exception" sau khi catch là chưa đủ: code có thể đã lặng lẽ trả dữ liệu thiếu.

### 15.4. Dùng test với tài nguyên tự đóng

Có thể xây `Reader` fake theo dõi `close()` để xác nhận try-with-resources được thực thi ngay cả khi terminal operation ném lỗi. Đây là cách ổn định hơn so với đo số file descriptor đang mở vốn phụ thuộc OS và cần hạ tầng giám sát riêng.

## 16. Xử lý khi duyệt song song và khi bất đồng bộ

### 16.1. Parallel stream không khiến I/O có thể tự phục hồi

`Files.walk(root).parallel()` có thể đổi cách xử lý pipeline tùy khả năng chia nguồn; nó **không** biến mọi thao tác filesystem thành thread-safe snapshot và không bảo đảm source sẽ tự retry khi có lỗi.

```java
try (Stream<Path> paths = Files.walk(root)) {
    paths.parallel().forEach(this::processOne);
}
```

Đây là snippet kiến trúc, giả định `processOne` của ứng dụng. Nếu một task ném `UncheckedIOException`, việc ghi side effect từ các task khác có thể đã xảy ra; không dựa vào thứ tự thực hiện hoặc giả định mọi task đã dừng tại cùng thời điểm. Với I/O blocking, còn cần cân nhắc không chiếm Common ForkJoinPool cho công việc chờ dài.

### 16.2. `CompletableFuture` có thể bọc lỗi thêm một tầng

Nếu bạn gọi đọc tệp bên trong `CompletableFuture.supplyAsync`:

```java
CompletableFuture<Long> job = CompletableFuture.supplyAsync(() -> {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.count();
    } catch (IOException error) {
        throw new UncheckedIOException(error);
    }
});
```

Đây là snippet trong method, cần `CompletableFuture`, `Files`, `Path`, `Stream`, `StandardCharsets`, `IOException`, `UncheckedIOException`. I/O khi tạo stream được code bọc thành unchecked; I/O trong terminal operation có thể đã là `UncheckedIOException` và truyền ra.

Khi caller gọi `job.join()`, failure từ supplier có thể được **bọc thêm bằng `CompletionException`**. Trong `exceptionally(error -> ...)`, hãy kiểm tra nguyên nhân theo các lớp wrapper thực có, không chỉ tìm `error instanceof UncheckedIOException` ở ngoài cùng.

### 16.3. Chọn executor cho I/O blocking

`CompletableFuture.supplyAsync` không truyền executor mặc định thường dùng `ForkJoinPool.commonPool` (với ngoại lệ theo cấu hình JVM). Đọc file hoặc network chậm có thể chiếm worker chung. Trong một service có tải cao, cân nhắc **executor I/O được quản lý** hoặc API không chặn thực sự, cùng giới hạn queue, số file mở và backpressure.

Đây là quyết định kiến trúc, không phải một yêu cầu rằng mọi `Files.lines` đều phải chạy trên executor riêng. Với ứng dụng CLI đọc file từng bước, vòng duyệt tuần tự đơn giản có thể là lựa chọn dễ đúng hơn.

## 17. An toàn, hiệu năng và quản lý khối lượng duyệt

### 17.1. Giới hạn cây thư mục và dữ liệu không đáng tin

Khi root do người dùng cung cấp, cần xem:

- Root phải nằm trong miền dữ liệu được phép, không chỉ kiểm tra prefix chuỗi path thiếu chuẩn hóa.
- `maxDepth` để tránh duyệt cây quá sâu.
- Chính sách FOLLOW_LINKS và symlink loops.
- Giới hạn số file, tổng bytes, kích thước từng file.
- Deadline, timeout của I/O nếu filesystem/provider hỗ trợ.
- Giới hạn số file descriptors/streams mở đồng thời.
- Chính sách xử lý file bị đổi/xóa trong khi quét.

`Files.walk` không tự trở thành một sandbox bảo mật. `Files.isRegularFile(path)` chỉ kiểm tra trạng thái ở một thời điểm; file có thể được thay đổi ngay sau đó. Nếu ứng dụng cần bảo đảm file identity/atomicity mạnh, cần thêm cơ chế provider-specific và thiết kế chống TOCTOU.

### 17.2. Đừng đọc hết file lớn nếu chỉ cần thống kê

`Files.readAllLines`/`collect(toList())` có thể tốn bộ nhớ lớn. `Files.lines` cho phép xử lý streaming, nhưng nếu cần transaction toàn bộ nhập, có thể phải dùng staging/batch và cách xác nhận đầy đủ riêng. Đánh đổi bộ nhớ và tính nhất quán cần rõ.

### 17.3. Không dùng `parallelStream` như mặc định cho I/O

Lợi ích của parallelism phụ thuộc khả năng tách nguồn, latency I/O, giới hạn OS và chi phí contention. Nhiều luồng cùng mở file có thể làm dịch vụ chậm hoặc quá số file descriptors. Benchmark có dữ liệu thật trước khi tăng độ song song.

### 17.4. Quan sát đầy đủ lỗi trong log có kiểm soát

Log có thể lưu error code, job ID, số file/row đã xử lý, stage `OPEN`/`ITERATE`/`CLOSE`, kiểu cause, metadata path đã redacted và correlation ID. Đừng gửi nguyên `IOException.toString()`, đường dẫn nội bộ, stack trace hoặc toàn bộ file content ra HTTP response.

Đối với lỗi đóng/tác vụ thất bại đồng thời, có thể cần xem `getSuppressed()` bên cạnh `getCause()` trong log kỹ thuật. Nhưng không tạo alert hai lần cho cùng một lỗi chỉ vì nó xuất hiện ở cả exception chính và suppressed.

## 18. Các lỗi thường gặp và cách sửa

1. **Chỉ catch `IOException` ngoài terminal operation.** Sai vì lazy traversal có thể ném `UncheckedIOException`. **Sửa:** bắt cả hai đường theo boundary thích hợp.
2. **Tưởng `Files.walk(root)` trả stream là đã duyệt xong.** Sai; chỉ một phần root có thể được mở. **Sửa:** hiểu terminal operation mới tiêu thụ nguồn.
3. **Tưởng `Files.lines(path).count()` thành công thì mọi consumer khác sau đó không thể lỗi.** Không đúng nếu file thay đổi/đọc lại. **Sửa:** mỗi lần đọc có error handling và policy riêng.
4. **Quên `try-with-resources`.** Stream I/O giữ tài nguyên. **Sửa:** đóng đúng `Stream` trả bởi `Files`; với `BufferedReader.lines` đóng reader.
5. **Dùng lại stream sau khi đã terminal operation hoặc thất bại.** Sai lifecycle. **Sửa:** tạo stream mới nếu được phép retry và xây dựng policy idempotent.
6. **Bắt `UncheckedIOException` rồi trả `Collections.emptyList()`.** Làm caller tưởng thư mục trống. **Sửa:** trả lỗi hoặc trạng thái PARTIAL/FAILED.
7. **Gộp mọi lỗi lambda thành IOException.** Che bug như NullPointerException. **Sửa:** chỉ bọc checked IOException vào `UncheckedIOException` khi thật sự là I/O.
8. **Quên kiểm tra `getCause()`.** Mất loại lỗi filesystem cần phân loại. **Sửa:** dùng IOException cause và subtypes, không parse message.
9. **Tưởng `UncheckedIOException` tự retry.** Không. **Sửa:** retry có điều kiện theo error type, idempotency và giới hạn.
10. **Cho rằng `forEach` là transaction.** Side effects đã chạy không tự rollback. **Sửa:** staging/transaction/checkpoint theo domain.
11. **Xử lý lỗi một nhánh parallel rồi báo hoàn tất toàn bộ.** Các task khác có thể còn side effects. **Sửa:** điều phối completion và trạng thái job rõ ràng.
12. **Dùng `Files.walk` nhưng cần bỏ qua riêng thư mục lỗi.** Stream có thể abort khi source lỗi. **Sửa:** dùng `walkFileTree` với `visitFileFailed` và policy rõ.
13. **Trộn lỗi mở và lỗi duyệt thành cùng thông điệp “không tồn tại”.** Nguyên nhân có thể do permission/thiết bị/encoding. **Sửa:** phân loại stage, cause và action.
14. **Dùng `Files.isRegularFile` làm lời bảo đảm file luôn tồn tại.** Có race giữa kiểm tra và xử lý. **Sửa:** xử lý I/O error của thao tác thực, không dựa vào precheck.
15. **Thao tác reader trực tiếp trong khi `reader.lines()` đang chạy.** API không cam kết hành vi đúng. **Sửa:** một owner cho reader, không interleave.
16. **Bật `FOLLOW_LINKS` không giới hạn.** Có thể gặp vòng symlink/thoát root. **Sửa:** depth, policy và kiểm tra path.
17. **Đóng stream rồi vẫn tiếp tục lấy phần tử.** Đó là lỗi lifecycle, không phải giải pháp phục hồi. **Sửa:** quản lý phạm vi stream nhất quán.
18. **Dùng file permissions thật để test lỗi lazy trên mọi CI.** Test dễ thay đổi giữa OS/runner. **Sửa:** fake `BufferedReader` hoặc nguồn injected exception xác định.
19. **Gán thành công cho import chỉ vì bắt được exception.** Không đảm bảo completeness. **Sửa:** trạng thái và số bản ghi đã xử lý phải phản ánh đúng.
20. **Dùng API mới mà không ghi phiên bản:** `Files.readString`/`Files.writeString` chỉ có từ Java 11, khác bài Java 8 này. **Sửa:** dùng `Files.lines`/`newBufferedReader`/`Files.write` khi build Java 8 hoặc ghi rõ yêu cầu JDK cao hơn.

## 19. Bảng quyết định sử dụng API

| Mục tiêu | API nên cân nhắc | Xử lý lỗi đúng |
| --- | --- | --- |
| Đọc toàn bộ file text nhỏ | `Files.readAllLines(path,charset)` | Checked `IOException`, file được đóng trong method |
| Đọc file text lớn theo stream | `Files.lines(path,charset)` | Checked khi mở, UncheckedIOException khi đọc lazy, đóng stream |
| Đọc qua reader đã có | `BufferedReader.lines()` | UncheckedIOException khi terminal operation đọc lỗi, đóng reader |
| Liệt kê entry trực tiếp | `Files.list(dir)` | Checked khi mở, UncheckedIOException khi duyệt, đóng stream |
| Duyệt nhiều cấp đơn giản | `Files.walk(root,maxDepth)` | Lỗi duyệt lazy có thể abort; đóng stream |
| Tìm file theo attributes | `Files.find(root,depth,predicate)` | Lỗi lazy tương tự walk, đóng stream |
| Duyệt có policy bỏ qua/tiếp tục khi lỗi từng entry | `Files.walkFileTree(root,visitor)` | `visitFileFailed`/`postVisitDirectory` và checked IOException |
| Lambda gọi I/O checked | `try/catch IOException` bên trong lambda | `throw new UncheckedIOException(error)` nếu muốn propagate |
| Service cam kết `throws IOException` | Bóc `UncheckedIOException.getCause()` tại boundary | Đảm bảo cả lỗi close theo policy |
| Best-effort scan | Visitor/kết quả trạng thái có error list | Không giấu partial |
| Import all-or-nothing | Staging/transaction | Lỗi duyệt làm rollback/không commit |
| Đầu vào có symlink không đáng tin | Walk với depth/option rõ | Chống loop, path escape, TOCTOU |
| Test lazy failure xác định | Fake `BufferedReader` ném ở Nth read | Kiểm tra cause, partial side effects, close |
| Thống kê nhiều file với tải cao | Pipeline I/O có concurrency limit | Không mặc định parallel stream là tối ưu |

## 20. Câu hỏi tự luyện (có đáp án)

**1. `UncheckedIOException` thuộc checked hay unchecked exception?**  
Unchecked, vì kế thừa `RuntimeException`.

**2. Vì sao `Files.walk(root)` có thể vừa khai báo `throws IOException` vừa ném `UncheckedIOException`?**  
Lỗi mở/truy cập ban đầu thuộc factory, còn lỗi xảy ra **sau khi trả stream** trong lazy traversal không thể khai báo như checked exception qua Stream API.

**3. `UncheckedIOException.getCause()` có kiểu trả về gì?**  
`IOException`.

**4. Có thể tạo `new UncheckedIOException((IOException)null)` không?**  
Không. Constructor yêu cầu cause khác null, nếu null sẽ ném `NullPointerException`.

**5. Lệnh `Files.lines(path, UTF_8).filter(...)` đã đọc hết file chưa?**  
Chưa. Pipeline lười; terminal operation mới buộc đọc theo nhu cầu.

**6. `BufferedReader.lines()` gặp lỗi ở dòng thứ ba khi `forEach` thì hai dòng trước có thể đã xử lý chưa?**  
Có; callback đã chạy không tự rollback. Phải quản lý side effect theo hợp đồng nghiệp vụ.

**7. `try-with-resources` có giúp đóng resource khi terminal operation ném exception không?**  
Có, nó thực hiện close khi rời block; close cũng có thể lỗi và tạo suppressed exception.

**8. Stream từ `Files.lines` và `BufferedReader.lines` khác ở việc đóng thế nào?**  
`Files.lines` trả stream có resource file phải **đóng stream**; với `BufferedReader.lines` nên **đóng reader** mà app đang sở hữu.

**9. `Files.list(dir)` có đi sâu vào thư mục con không?**  
Không, nó liệt kê entry ở một cấp.

**10. `Files.walk(root,1)` có chứa root không?**  
Có, bắt đầu từ root rồi đến entry con trực tiếp trong phạm vi tối đa một cấp.

**11. `Files.find` cung cấp thêm gì so với walk/filter?**  
Predicate nhận cả Path và BasicFileAttributes, hữu ích khi lọc theo metadata mà không cần truy vấn lặp lại.

**12. Trong `map(path -> Files.size(path))`, vì sao Java compiler báo lỗi?**  
`Files.size` khai báo checked IOException nhưng `Function.apply` không cho khai báo checked exception ấy; phải bắt/bọc hoặc đổi cách xử lý.

**13. Mọi `RuntimeException` trong stream có phải là UncheckedIOException không?**  
Không. Bug và lỗi parse dữ liệu dùng loại exception khác.

**14. Catch lỗi lazy `Files.walk` rồi có thể dùng lại cùng stream để “tiếp tục nơi dừng” không?**  
Không. Stream là single-use; nguồn có thể ở trạng thái dở dang/đã lỗi, không có hợp đồng resume.

**15. `Files.walkFileTree` hữu ích hơn `Files.walk` khi nào?**  
Khi cần điều khiển từng lỗi truy cập file/directory thông qua visitor và tiếp tục/bỏ qua/dừng theo policy.

**16. Có nên mặc định `return Collections.emptyList()` cho mọi IOException/UncheckedIOException?**  
Không. Nó đánh đồng lỗi I/O với "không có dữ liệu".

**17. Vì sao lỗi I/O khi `parallel()` có thể gây khó quản lý side effects?**  
Nhiều phần tử có thể đã được xử lý trên các thread khác; khi một nhánh lỗi, side effects trước đó không tự rollback.

**18. Nếu file vừa được kiểm tra tồn tại rồi bị xóa trước lúc đọc thì sao?**  
Phải xử lý IOException/NoSuchFileException của thao tác thực; precheck không bảo đảm file tồn tại về sau.

**19. Có nên test I/O lazy failure bằng `Thread.sleep()` và thay đổi quyền file không?**  
Thường không; khó xác định giữa OS/CI. Fake reader ném theo số lần đọc ổn định hơn.

**20. `Files.readString` có từ Java 8 không?**  
Không, có từ Java 11. Với module Java 8, dùng API tương thích hoặc ghi rõ mức JDK cần có.

## 21. Nguồn tham khảo chính thức (API hiện vẫn áp dụng)

Các API được học trong bài được giới thiệu từ **Java 8** và còn được duy trì ở JDK hiện đại. Các phương thức phát hành sau Java 8 đã được ghi rõ để tránh nhầm compatibility:

- [`UncheckedIOException` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/UncheckedIOException.html): constructor, quan hệ `RuntimeException`, `IOException getCause()`, yêu cầu cause khác null.
- [`Files` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): `lines`, `list`, `walk`, `find`, `walkFileTree`, lazy traversal, tài nguyên stream và lỗi I/O ở hai giai đoạn.
- [`BufferedReader` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/BufferedReader.html): `lines()`, lazy reading, cách bọc IOException và yêu cầu không tương tác reader đồng thời với terminal operation.
- [`FileVisitor` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/FileVisitor.html): `visitFileFailed`, `postVisitDirectory` và cách điều khiển duyệt cây.
- [`SimpleFileVisitor` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/SimpleFileVisitor.html): lớp tiện ích xây visitor có chọn lọc.
- [`Stream` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): pipeline lazy, terminal operations, single-use streams và close semantics.
- [`IOException` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/IOException.html): exception I/O checked và phân loại cause.
- [`NoSuchFileException` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/NoSuchFileException.html): subtype dùng khi tệp không tồn tại.
- [`Files` — Java 8 API](https://docs.oracle.com/javase/8/docs/api/java/nio/file/Files.html): đối chiếu các API tương thích Java 8.

**Nguyên tắc kết luận:** Lỗi I/O có thể xảy ra **trong lúc duyệt chứ không chỉ lúc mở**. Khi dùng Stream với tệp/thư mục, cần dự trù `UncheckedIOException`, bảo tồn `IOException` cause, đóng tài nguyên, và không đánh dấu thành công cho một traversal đã xử lý dở. Nếu cần policy tiếp tục qua từng entry lỗi, chọn API visitor và ghi nhận kết quả thiếu rõ ràng.
