# Đóng Stream của tài nguyên bằng try-with-resources trong Java

## 1. Mục tiêu: xử lý xong dữ liệu phải trả lại tài nguyên

Trong Java, đọc một tệp hoặc duyệt một thư mục thường cần tài nguyên bên ngoài heap JVM: file descriptor, handle của hệ điều hành, bộ đệm, đối tượng giải mã ký tự hoặc kết nối với nguồn dữ liệu. Một số tài nguyên vẫn tồn tại trong khi chương trình đang xử lý các phần tử từ một `Stream`. Nếu sử dụng xong nhưng không đóng đúng cách, hệ thống có thể gặp:

- Cạn số lượng file handles hoặc file descriptors khi phục vụ nhiều yêu cầu.
- Không thể xóa, đổi tên hay ghi đè tệp vào lúc mong muốn trên một số hệ điều hành.
- Kết nối hoặc bộ đệm tiếp tục chiếm tài nguyên dù tác vụ xử lý logic đã kết thúc.
- Dữ liệu ghi ra chưa hoàn tất quy trình đóng bộ đệm, nên file nhận được có thể thiếu nội dung.
- Lỗi I/O trong lúc đóng bị bỏ qua hoặc che khuất nguyên nhân lỗi trong lúc xử lý.

Java cung cấp **try-with-resources** để ràng buộc vòng đời tài nguyên vào một khối từ vựng. Cơ chế này có từ Java 7, còn hiệu lực trong Java 8 và JDK mới, và là lựa chọn mặc định cho những đối tượng sở hữu tài nguyên và triển khai `AutoCloseable` hoặc `Closeable`.

Ví dụ cốt lõi:

```java
Path path = Path.of("data.txt");
try (Stream<String> lines = Files.lines(path)) {
    long nonEmpty = lines.filter(s -> !s.isBlank()).count();
    System.out.println(nonEmpty);
}
```

Đây là ví dụ minh họa, yêu cầu file `data.txt` tồn tại và import `java.nio.file.*`, `java.util.stream.*`. `Files.lines` trả về một `java.util.stream.Stream<String>` **đang giữ tài nguyên file**; khi kết thúc khối `try`, JVM gọi `close()` trên stream, kể cả nếu xử lý gặp exception hoặc `return` sớm.

**Chủ đề trực tiếp:** “Đóng Stream của tài nguyên bằng try-with-resources”, thuộc mục “Tệp và I/O”. Bài tập trung vào **những Stream thực sự sở hữu tài nguyên**, đối chiếu `java.io.InputStream/OutputStream` với `java.util.stream.Stream<T>`, hợp đồng đóng, scope sử dụng, ngoại lệ khi đóng và cách viết mã có thể chạy.

Sau khi học, bạn cần trả lời chính xác:

1. Stream nào phải đóng? Stream nào thường không giữ tài nguyên ngoài JVM?
2. `Files.lines`, `Files.list`, `Files.walk` trả Stream thế nào, vì sao cần `try`?
3. `BufferedReader.lines()` có tự làm Stream trở thành owner của `BufferedReader` không?
4. Một terminal operation như `count()`, `findFirst()`, `forEach()` có tự đóng Stream không?
5. Khi có nhiều resources, chúng được đóng theo thứ tự nào?
6. Nếu thân `try` và `close()` cùng ném lỗi, lỗi nào được ưu tiên?
7. Resource đã được mở từ trước có thể xuất hiện trong đầu mục `try` từ Java 9 như thế nào?
8. Ai là người chịu trách nhiệm đóng khi trả Stream cho caller?
9. Đóng writer có đồng nghĩa atomic write hay đảm bảo dữ liệu đã bền vững trên ổ đĩa không?
10. Làm sao test tự động các tình huống **normal, short-circuit, exception, close failure và initializer failure**?

## 2. Phân biệt hai họ “Stream” trong Java

Tên `Stream` có thể làm người học nhầm vì Java có hai họ API khác nhau:

| Họ API | Kiểu ví dụ | Vai trò | Phải đóng khi nào? |
| --- | --- | --- | --- |
| I/O byte stream | `InputStream`, `OutputStream`, `FileInputStream` | Đọc/ghi chuỗi byte từ file, socket, bộ nhớ… | Khi sở hữu nguồn/đích có tài nguyên cần đóng |
| I/O character stream | `Reader`, `Writer`, `BufferedReader`, `BufferedWriter` | Đọc/ghi ký tự với charset/buffer | Khi sở hữu reader/writer có tài nguyên cần đóng |
| Stream xử lý dữ liệu | `java.util.stream.Stream<T>` | Pipeline `filter/map/flatMap/count/findFirst…` | **Tùy nguồn**: stream backed bởi I/O phải đóng |
| Primitive processing stream | `IntStream`, `LongStream`, `DoubleStream` | Pipeline kiểu primitive, implements `BaseStream` | Tùy nguồn, như Stream<T> |
| Directory stream của NIO | `DirectoryStream<Path>` | Duyệt directory entries, implements `Closeable` | Cần đóng sau khi duyệt |

### 2.1. `InputStream` không phải `Stream<T>`

`java.io.InputStream` là lớp trừu tượng đọc **byte**. Nó không có phương thức `filter` hoặc `map` của Stream API. `java.util.stream.Stream<String>` là pipeline xử lý phần tử, không có `read(byte[])` của InputStream.

Cả hai có phương thức đóng theo hợp đồng tương ứng, nhưng **không thể thay thế cho nhau** trong lời gọi API.

Ví dụ:

```java
try (InputStream in = Files.newInputStream(path)) {
    int firstByte = in.read();
}
```

và:

```java
try (Stream<String> lines = Files.lines(path)) {
    Optional<String> firstLine = lines.findFirst();
}
```

Hai đoạn ở trong method có `Path path` và imports phù hợp. Đoạn đầu đóng **byte stream**. Đoạn sau đóng **stream pipeline sở hữu một nguồn file**.

### 2.2. Stream từ Collection thường không có tài nguyên cần đóng

```java
List<String> names = List.of("Lan", "Minh", "Hoa");

long count = names.stream()
        .filter(name -> name.length() >= 3)
        .count();
```

Ở ví dụ này Stream được tạo từ một `List` trong bộ nhớ, không mở file descriptor. Không cần viết `try-with-resources` chỉ để tránh “rò rỉ file” vì không có file nào được mở. Javadoc `Stream` ghi rõ đa số Stream từ collection, array hoặc generating function **không cần đóng**.

Ngược lại:

```java
try (Stream<String> lines = Files.lines(path)) {
    // ...
}
```

bắt buộc xem xét vòng đời file handle vì Stream được trả về gắn với một **file đang mở**.

**Nguyên tắc:** Hãy hỏi **nguồn của Stream có tài nguyên I/O không**, chứ đừng suy luận rằng mọi `Stream<T>` đều cần đóng hoặc mọi `Stream<T>` đều tự đóng khi xong.

## 3. Try-with-resources thực sự hoạt động thế nào?

Hình thức cơ bản:

```java
try (ResourceType resource = openResource()) {
    use(resource);
}
```

Đây là template; `ResourceType` cần implement `AutoCloseable`, còn `openResource`/`use` phải tồn tại.

Biểu thức khởi tạo resource được đánh giá trước thân `try`. Khi resource được khởi tạo thành công, Java tự chèn logic đóng resource vào đường thoát của khối, cả khi:

- Code xử lý kết thúc bình thường.
- Có `return`/`break`/`continue` thoát khỏi khối tương ứng.
- Code xử lý ném exception.
- Một tài nguyên **được khai báo sau** thất bại trong giai đoạn khởi tạo.
- Có nhiều tài nguyên cần đóng, một lần `close()` gặp exception.

Nếu tài nguyên trong header có giá trị `null`, nó không được gọi `close()`. Để giữ hợp đồng rõ ràng, tốt hơn là thiết kế factory trả một đối tượng hợp lệ hoặc throw, thay vì trả null có ý nghĩa mơ hồ.

### 3.1. Khác với try/finally thủ công

Không khuyến nghị viết mỗi lần:

```java
InputStream in = Files.newInputStream(path);
try {
    use(in);
} finally {
    in.close();
}
```

Cách thủ công này có thể đúng cho trường hợp đơn giản, nhưng việc tự xử lý **nhiều resources, lỗi trong body và lỗi khi close** phức tạp hơn. Trong `try-with-resources`, compiler tạo cấu trúc xử lý đóng và **suppressed exceptions** theo Java Language Specification.

Dùng:

```java
try (InputStream in = Files.newInputStream(path)) {
    use(in);
}
```

khi bạn là **owner** của stream. Không cần `finally { in.close(); }` thêm lần nữa vì sẽ thành double close không cần thiết.

### 3.2. Closeable và AutoCloseable

- `AutoCloseable` có `void close() throws Exception`: giao diện tổng quát cho resource dùng trong try-with-resources.
- `Closeable` trong `java.io` extends `AutoCloseable` và có `close() throws IOException`: phổ biến với I/O streams, readers, writers và directory streams.
- `BaseStream` của Stream API extends `AutoCloseable`; `close()` trên interface này **không khai báo checked exception**.
- Từng implementation có thể có cơ chế close riêng; đừng giả định tất cả `close()` không thể thất bại.

Theo hợp đồng `AutoCloseable`, resource implementer nên giải phóng tài nguyên kịp thời ngay cả trong trường hợp close có lỗi. **Không phải mọi AutoCloseable đều idempotent**; chỉ gọi close lặp nếu implementation cụ thể cho phép.

### 3.3. Thời điểm close

`close()` diễn ra **khi thoát khỏi block `try`**, không phải khi phương thức `Files.lines(...)` trả về, không phải sau mỗi phần tử, và **không tự xảy ra chỉ vì một terminal operation hoàn tất**.

Đây là ưu điểm: bạn có một scope dễ xem bằng mắt, giúp reviewer biết lúc nào file được giải phóng.

## 4. Trường hợp trọng tâm: Files.lines(Path)

`Files.lines(Path)` mở file và trả một `Stream<String>` đọc các dòng theo kiểu lazy. Phiên bản Java hiện hành cũng có overload:

```java
Stream<String> lines(Path path) throws IOException;
Stream<String> lines(Path path, Charset cs) throws IOException;
```

Đây là chữ ký rút gọn; cả hai là static method của `Files`. Biến thể không truyền charset dùng **UTF-8**.

### 4.1. Mẫu đúng

```java
Path file = Path.of("logs", "service.log");

try (Stream<String> lines =
             Files.lines(file, StandardCharsets.UTF_8)) {
    long errors = lines
            .filter(line -> line.contains("ERROR"))
            .count();
    System.out.println(errors);
}
```

Code minh họa này cần file được tạo sẵn và imports `java.nio.file.*`, `java.nio.charset.*`, `java.util.stream.*`. Stream được tiêu thụ **trước khi block try kết thúc**. Khi ra khỏi block, file handle được đóng.

### 4.2. Tránh mở file rồi quên đóng

Anti-pattern:

```java
Stream<String> lines = Files.lines(file);
long errors = lines.filter(s -> s.contains("ERROR")).count();
// Không close.
```

Kể cả khi `count()` hoàn tất, code không thực thi `lines.close()`. Khi nhiều request lặp mẫu này, các file handles có thể tồn tại lâu hơn dự kiến. Đừng trông chờ garbage collector “cuối cùng sẽ dọn” thay cho vòng đời resource rõ ràng.

### 4.3. Short-circuit operation không tự đóng tài nguyên

`findFirst()`, `anyMatch()`, `findAny()`, `limit(n)` thường không đọc hết nguồn. Nhưng kết thúc pipeline **không gọi `close()` cho file-backed Stream**.

Đúng:

```java
try (Stream<String> lines = Files.lines(file)) {
    Optional<String> firstError = lines
            .filter(s -> s.startsWith("ERROR"))
            .findFirst();
}
```

`finally` do try-with-resources tạo sẽ đóng file **dù chỉ đọc một phần**. Tránh suy luận “đã gặp dòng cần tìm thì stream tự đóng”.

### 4.4. File có thể thay đổi khi stream còn đang đọc

Javadoc `Files.lines` ghi rõ nội dung file **không nên được sửa trong lúc thực hiện terminal operation**; nếu sửa, kết quả có thể không xác định theo contract. Try-with-resources xử lý vòng đời file, **không cung cấp snapshot bất biến hoặc khóa tệp**.

Nếu ứng dụng cần đọc phiên bản nhất quán, phải thiết kế cơ chế phát hành/đổi tên tệp, snapshot hoặc transaction phù hợp, không chỉ thêm `try`.

## 5. Files.list, Files.walk và Files.find: Stream giữ thư mục đang mở

Các API NIO thường gặp:

```java
Stream<Path> list(Path dir) throws IOException;
Stream<Path> walk(Path start, FileVisitOption... options)
        throws IOException;
Stream<Path> find(Path start, int maxDepth,
        BiPredicate<Path, BasicFileAttributes> matcher,
        FileVisitOption... options) throws IOException;
```

Đây là các chữ ký rút gọn của `Files`; `BasicFileAttributes` từ `java.nio.file.attribute` và `BiPredicate` từ `java.util.function`.

Chúng có thể giữ **directory handles** và duyệt lazy. Javadoc yêu cầu đóng stream kịp thời, thường bằng try-with-resources.

### 5.1. Liệt kê thư mục một cấp

```java
Path folder = Path.of("uploads");

try (Stream<Path> entries = Files.list(folder)) {
    List<String> names = entries
            .map(path -> path.getFileName().toString())
            .sorted()
            .toList();
    System.out.println(names);
}
```

`Files.list` chỉ liệt kê **entries trực tiếp** trong thư mục, không đi sâu đệ quy. `Stream.toList()` cần Java 16+, phù hợp chương trình Java 17+ của bài.

**Không viết** `Files.list(folder).toList()` liên tục mà không giữ/đóng stream; method ngắn vẫn có thể leak thư mục đang mở.

### 5.2. Duyệt cây thư mục

```java
try (Stream<Path> paths = Files.walk(folder)) {
    long files = paths
            .filter(Files::isRegularFile)
            .count();
    System.out.println(files);
}
```

`Files.walk` đi theo cây thư mục một cách lazy, có thể mở directory handles trong quá trình duyệt. Đóng stream để giải phóng những directory handles còn mở. Mặc định không đi theo symbolic links trừ khi truyền option phù hợp; đừng dùng kết quả như ảnh chụp bất biến nếu cây thư mục bị cập nhật đồng thời.

### 5.3. Files.find cũng phải đóng

`Files.find` trả Stream<Path> phù hợp predicate theo thuộc tính file. Nó cùng họ với `Files.walk` và chứa references đến các directory đang mở. Mẫu:

```java
try (Stream<Path> matches =
        Files.find(folder, 5,
                (path, attrs) -> attrs.isRegularFile())) {
    long count = matches.count();
}
```

Đây là snippet với `Path folder` đã có, Java 17+.

### 5.4. Không trả Files.walk trực tiếp nếu caller không biết phải close

Rủi ro:

```java
public Stream<Path> findPaths(Path folder) throws IOException {
    return Files.walk(folder); // Chuyển quyền sở hữu resource cho caller.
}
```

Đoạn này **không tự sai về mặt cú pháp**, nhưng API dễ dùng sai nếu caller không biết nó phải close. Nếu bạn cố tình trả Stream, **document ownership** và yêu cầu caller:

```java
try (Stream<Path> paths = findPaths(folder)) {
    // Duyệt ngay trong scope còn mở.
}
```

Nếu caller chỉ cần danh sách nhỏ, cân nhắc thu dữ liệu thành List dưới try-with-resources ở service rồi trả **dữ liệu đã tách khỏi tài nguyên**.

## 6. BufferedReader.lines: đóng Reader chứ không chỉ đóng pipeline

`BufferedReader` là một `Reader` sở hữu nguồn I/O bên dưới. Phương thức `reader.lines()` trả `Stream<String>` để duyệt các dòng.

Mẫu nên dùng:

```java
try (BufferedReader reader =
        Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
    long count = reader.lines().count();
    System.out.println(count);
}
```

Ở đây **reader** là resource trong header. Khi kết thúc try, `reader.close()` giải phóng file handle.

### 6.1. Bẫy: chỉ close stream tạo từ reader

Không dùng mô hình sau như một cam kết reader được đóng:

```java
BufferedReader reader =
        Files.newBufferedReader(file, StandardCharsets.UTF_8);

try (Stream<String> lines = reader.lines()) {
    System.out.println(lines.count());
}
// reader vẫn cần close; không giả định Stream.close() đóng reader.
```

`BufferedReader.lines()` không được hứa là thiết lập một `onClose` handler để đóng chính Reader. Hãy quản lý vòng đời **BufferedReader** tường minh.

Nếu muốn đặt cả reader và stream vào header, có thể làm:

```java
try (BufferedReader reader = Files.newBufferedReader(file);
     Stream<String> lines = reader.lines()) {
    long count = lines.count();
}
```

Khi thoát, stream được close trước, reader được close sau. Dù vậy, với Reader như nguồn sở hữu file, **mẫu chỉ khai báo reader** thường đơn giản và đủ.

### 6.2. BufferedReader.readLine cũng cần close

`readLine()` có thể được gọi vòng lặp và không dùng java.util.stream.Stream. Reader vẫn là I/O resource:

```java
try (BufferedReader reader = Files.newBufferedReader(file)) {
    String line;
    while ((line = reader.readLine()) != null) {
        process(line);
    }
}
```

Đây là code minh họa với `process` do ứng dụng định nghĩa. Cùng nguyên tắc ownership như `reader.lines()`.

## 7. Đọc InputStream và ghi OutputStream trong try-with-resources

Khi cần xử lý binary data, chọn `InputStream` và `OutputStream`. Từ Java 9, `InputStream.transferTo(OutputStream)` là cách chuyển bytes giữa hai streams:

```java
Path source = Path.of("input.bin");
Path target = Path.of("output.bin");

try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(target)) {
    long copied = in.transferTo(out);
    System.out.println(copied);
}
```

Đây là ví dụ file đã có và có quyền tạo target. `Files.newInputStream` và `Files.newOutputStream` mở resources; việc đóng cả hai được xử lý theo thứ tự **`out.close()` trước, `in.close()` sau**.

### 7.1. Phân biệt close và flush

`OutputStream.flush()` yêu cầu chuyển bytes đang được buffer ra output destination theo hợp đồng của implementation. `close()` kết thúc resource lifecycle, có thể flush các buffers tương ứng rồi giải phóng handle.

**Không dùng `flush()` như thay thế cho `close()`**. Một output stream đã flush vẫn có thể giữ file descriptor/socket.

Ngược lại, **close thành công không tự bảo đảm mọi cập nhật đã durable trên thiết bị lưu trữ** hay một file replacement là atomic. Nếu hệ thống cần durability/atomic replace, dùng những API/protocol tương ứng như file-channel force, temp file + atomic move khi filesystem hỗ trợ; đó là bài toán riêng ngoài vòng đời resource.

### 7.2. Nếu writer gặp lỗi khi close

Một số lỗi ghi có thể chỉ lộ ra trong lúc flush/close. Khi dùng try-with-resources, exception từ close được propagate hoặc lưu suppressed theo ngữ cảnh. Không được catch rồi bỏ qua mọi `IOException` chỉ để cho ứng dụng tiếp tục như thể dữ liệu đã ghi thành công.

### 7.3. Đầu vào/đầu ra của process và socket

Streams từ socket, process hoặc kết nối ngoài cũng có resource ownership, nhưng tác động đóng có thể khác nhau: close một network stream có thể kết thúc một phần hoặc toàn bộ giao tiếp, tùy implementation. Không giả định đóng một wrapper chỉ ảnh hưởng “một object vô hại”.

Trước khi tự động close, xác định ai sở hữu kết nối, còn code khác có cần nó không và có kỳ vọng half-close hay giao thức riêng hay không.

## 8. Charset và các Reader/Writer nên dùng

Trong Java hiện đại, nên **chỉ rõ charset** khi dữ liệu có định dạng quy định, thường là UTF-8:

```java
try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String firstLine = reader.readLine();
}
```

và:

```java
try (BufferedWriter writer =
             Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("Xin chào Java");
    writer.newLine();
}
```

Hai ví dụ minh họa với `Path path`, và phải đảm bảo logic đọc/ghi đúng đường dẫn. `newBufferedWriter` mở nguồn ghi có thể tạo/ghi đè file theo options; xem quy tắc overwrite khi làm việc với file production.

### 8.1. Files.readString / Files.writeString có cần caller close không?

Các convenience methods như:

```java
String content = Files.readString(path, StandardCharsets.UTF_8);
Files.writeString(path, content, StandardCharsets.UTF_8);
```

quản lý tài nguyên file nội bộ trong quá trình gọi. Chúng **không trả về một open Stream** để caller đóng. Chúng phù hợp cho file vừa phải, nhưng đọc toàn bộ file vào bộ nhớ; với file lớn hoặc yêu cầu streaming, cân nhắc `Files.lines`/BufferedReader trong try-with-resources.

### 8.2. Files.readAllLines cũng không trả open stream

`Files.readAllLines(path, charset)` trả một `List<String>` chứa nội dung đã đọc vào bộ nhớ, không phải một file-backed `Stream<String>` cần caller close. Khác với `Files.lines(path)` trả lazy Stream phải close.

Bảng:

| API | Kết quả | Caller cần close result? | Lưu ý |
| --- | --- | --- | --- |
| `Files.lines(path)` | `Stream<String>` lazy | **Có** | Stream gắn file handle |
| `Files.newBufferedReader(path)` | `BufferedReader` | **Có** | Reader giữ file |
| `BufferedReader.lines()` | `Stream<String>` trên reader | **Đóng reader sở hữu** | Không thay ownership reader |
| `Files.readAllLines(path)` | `List<String>` | Không | Đọc hết vào memory |
| `Files.readString(path)` | `String` | Không | Đọc hết vào memory |
| `Files.writeString(path,text)` | `Path` | Không | Resource được quản lý trong method |
| `Files.list(dir)` | `Stream<Path>` lazy | **Có** | Stream gắn directory |
| `Files.walk(dir)` | `Stream<Path>` lazy | **Có** | Có thể mở nhiều directories |
| `Files.find(dir,depth,predicate)` | `Stream<Path>` lazy | **Có** | Tương tự walk |
| `list.stream()` | Stream từ List in-memory | Thường không | Không có I/O ownership |

**Lưu ý:** “Không cần caller close” không nói rằng file hoàn toàn không thể có lỗi. `Files.readString` và `writeString` vẫn có thể ném `IOException`, nhưng chúng không trao tài nguyên mở cho caller giữ qua nhiều thao tác.

## 9. Nhiều resource trong cùng try: đóng từ phải sang trái

`try-with-resources` có thể khai báo nhiều đối tượng `AutoCloseable`, phân tách bằng dấu chấm phẩy:

```java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(target)) {
    in.transferTo(out);
}
```

Theo Java Language Specification:

1. Các resource được **khởi tạo từ trái sang phải**: `in` rồi `out`.
2. Khi thoát, các resource **được đóng theo thứ tự ngược lại**: `out.close()` rồi `in.close()`.
3. Nếu đóng một resource ném lỗi, Java **vẫn cố đóng** các resource khác đã khởi tạo thành công.
4. Nếu resource thứ hai **khởi tạo thất bại**, resource đầu tiên đã mở sẽ được đóng tự động.

Điều này giúp quản lý đúng cả resource xếp lớp và các resources độc lập.

### 9.1. Minh họa thứ tự deterministic

Một resource giả chỉ ghi log:

```java
final class LoggedResource implements AutoCloseable {
    private final String name;
    private final List<String> events;

    LoggedResource(String name, List<String> events) {
        this.name = name;
        this.events = events;
        events.add("open:" + name);
    }

    @Override
    public void close() {
        events.add("close:" + name);
    }
}
```

Sau đó:

```java
List<String> events = new ArrayList<>();

try (LoggedResource a = new LoggedResource("A", events);
     LoggedResource b = new LoggedResource("B", events)) {
    events.add("body");
}

System.out.println(events);
```

Output:

```text
[open:A, open:B, body, close:B, close:A]
```

Đây là minh họa tách snippet, với imports `java.util.*`; ví dụ chạy đầy đủ ở mục 18 có resource giả tương đương và kiểm thử cả lỗi.

### 9.2. Có nên khai báo cả wrapper và nguồn gốc cùng header?

Ví dụ:

```java
try (InputStream raw = Files.newInputStream(file);
     BufferedInputStream buffered = new BufferedInputStream(raw)) {
    // Đọc từ buffered.
}
```

`BufferedInputStream.close()` đóng nguồn `raw` bên dưới theo implementation. Khi thoát try, Java sẽ close `buffered` rồi close `raw` một lần nữa. Với các lớp chuẩn có close lặp được hỗ trợ, cách này thường không gây vấn đề, nhưng **không nên suy rộng double close an toàn cho mọi loại resource**.

Một pattern đơn giản hơn khi wrapper sở hữu nguồn:

```java
try (BufferedInputStream in = new BufferedInputStream(
        Files.newInputStream(file))) {
    // Đọc từ in.
}
```

Trong trường hợp này, close **wrapper ngoài cùng** sẽ close nguồn bên trong. Chỉ dùng pattern này khi hợp đồng của wrapper xác nhận nó sở hữu nguồn và đóng được nguồn đó. Nếu wrapper **không** nên đóng nguồn do caller sở hữu, phải thiết kế ownership khác.

## 10. Lỗi trong try và lỗi khi close: suppressed exceptions

Một phần tinh tế nhất của try-with-resources là **thứ tự ưu tiên lỗi**.

Giả sử:

- Trong thân `try`, code ném `IllegalStateException("body-failed")`.
- Resource Y đóng lỗi `IOException("close-Y")`.
- Resource X đóng lỗi `IOException("close-X")`.

Thay vì để lỗi cuối cùng từ close **che mất lỗi chính**, Java:

1. Propagate lỗi chính trong body: `IllegalStateException("body-failed")`.
2. Đưa lỗi close-Y và close-X vào danh sách **suppressed** của lỗi chính, theo thứ tự được gặp khi close resource.
3. Cho phép caller truy xuất bằng `Throwable.getSuppressed()`.

```java
try (Resource x = openX();
     Resource y = openY()) {
    throw new IllegalStateException("body-failed");
} catch (IllegalStateException error) {
    Throwable[] suppressed = error.getSuppressed();
    // Có thể gồm lỗi đóng Y rồi X.
}
```

Đây là **mẫu minh họa** giả định các factory và Resource tồn tại.

### 10.1. Suppressed khác cause

- **Cause** (`getCause()`) là lý do gốc của một exception được **bọc bởi exception khác**, chẳng hạn một IOException được wrap thành UncheckedIOException.
- **Suppressed exceptions** (`getSuppressed()`) là những lỗi độc lập xảy ra trong lúc cleanup nhưng bị giữ lại để **không làm mất lỗi chính**.

Một exception có thể **đồng thời** có cause và suppressed exceptions. Không thay thế `getSuppressed()` bằng `getCause()` và ngược lại.

### 10.2. Khi thân try không ném lỗi nhưng close lỗi

Nếu body thành công nhưng `close()` của resource ném exception, exception khi close có thể là **lỗi chính được propagate**. Nếu có nhiều resource đều lỗi lúc close, một lỗi được chọn làm primary, các lỗi close sau được suppressed theo trình tự đóng.

Vì vậy “try-with-resources luôn nuốt lỗi close” là **sai**. Nó quản lý ưu tiên lỗi rõ ràng, không biến thất bại đóng tài nguyên thành thành công.

### 10.3. Quan sát đầy đủ trong logging

Khi xử lý ngoại lệ:

```java
catch (IOException error) {
    logger.error("I/O operation failed", error);
}
```

Đây là snippet với `logger` do ứng dụng cung cấp. Các thư viện logging chuẩn thường hiển thị suppressed trong stack trace; để chẩn đoán lập trình, có thể duyệt `error.getSuppressed()`. Không chỉ log `error.getMessage()` rồi bỏ qua toàn bộ chain nguyên nhân/suppressed.

### 10.4. Không catch Throwable rồi bỏ qua

Không viết:

```java
catch (Throwable ignored) {
    // Bỏ qua hết, kể cả lỗi I/O quan trọng.
}
```

Trong Java, việc bắt mọi `Throwable` có thể nuốt cả những tình trạng nghiêm trọng không nên bị bỏ qua. Với các đoạn xử lý dữ liệu, bắt các loại checked/unchecked exception mà nghiệp vụ thực sự hiểu được và báo lỗi có ngữ cảnh. Resource vẫn được đóng dù exception propagate.

## 11. Lỗi khi khởi tạo resource thứ hai

Xem:

```java
try (Resource first = openFirst();
     Resource second = openSecond()) {
    use(first, second);
}
```

Nếu `openFirst()` thành công nhưng `openSecond()` ném exception **trước khi trả Resource**, `first` sẽ được Java tự động close. Thân `try` **không chạy**.

Nếu first.close cũng lỗi, lỗi close có thể được đưa vào suppressed của lỗi khởi tạo second.

Đây là điểm giúp try-with-resources tránh leak trong chuỗi khởi tạo phức tạp. Nếu viết bằng code thủ công, bạn phải có nested try/finally đúng để không quên đóng first khi mở second thất bại.

### 11.1. Null resources

Nếu một initializer trả `null` thay vì ném lỗi, try-with-resources không gọi `close()` trên biến null. Nhưng code bên trong có thể vẫn gây `NullPointerException` khi sử dụng. Khuyến nghị các factory quản lý tài nguyên **trả một đối tượng hợp lệ hoặc báo lỗi rõ ràng**, không dùng null để thể hiện lỗi mở file.

## 12. Cú pháp Java 9+: try với biến đã tồn tại và effectively final

Từ **Java 9**, resource có thể là một biến **đã được khai báo trước**, nếu biến đó là `final` hoặc **effectively final** (không bị gán lại) và đã được khởi tạo chắc chắn.

Ví dụ Java 17+:

```java
BufferedReader reader =
        Files.newBufferedReader(file, StandardCharsets.UTF_8);

try (reader) {
    String first = reader.readLine();
}
```

Khác với cú pháp khai báo trực tiếp trong header:

```java
try (BufferedReader reader =
        Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
    String first = reader.readLine();
}
```

Cả hai có tác dụng tự động close resource đúng scope. Nhưng nếu một biến `reader` đã có sẵn và resource không thuộc quyền sở hữu của method này, **đừng tùy tiện đưa vào `try(reader)`**, vì như vậy caller có thể bị mất quyền sử dụng reader sau khi method trả về.

### 12.1. “Effectively final” là gì?

```java
BufferedReader reader = Files.newBufferedReader(file);
try (reader) {
    // ...
}
```

Biến `reader` không được gán lại nên là effectively final.

Ngược lại:

```java
BufferedReader reader = Files.newBufferedReader(file);
reader = Files.newBufferedReader(otherFile); // Gán lại.
// try (reader) { ... } // Lỗi biên dịch do không effectively final.
```

Đây là ví dụ cố ý về **compile error**, không chạy độc lập. Ngoài lỗi compile, việc gán lại sau khi mở cũng có nguy cơ leak reader đầu nếu không được đóng. Dùng biến mới cho mỗi resource, giữ scope ngắn.

### 12.2. Chú ý tên Java 8

Bài thuộc module Java 8 vì nhiều API về `Stream` và `Files.lines/list/walk` xuất hiện từ Java 8. Nhưng cú pháp `try (existingResource)` là **bổ sung từ Java 9**, không có trong Java 8 gốc. Nếu source level thực sự phải là `--release 8`, dùng resource declaration ngay trong header; đừng dùng cú pháp Java 9 hoặc `Stream.toList()` của Java 16.

Trong chương trình hoàn chỉnh của bài, yêu cầu **Java 17+**, nên cú pháp Java 9 này được dùng và giải thích rõ.

## 13. Stream terminal operation không đồng nghĩa close

Đây là điều cốt lõi cho `java.util.stream.Stream`.

### 13.1. Pipeline hoàn tất nhưng file còn mở nếu chưa close

```java
Stream<String> lines = Files.lines(file);

long count = lines.count();
// Count đã xong, nhưng cần lines.close() nếu đây là I/O-backed stream.
```

Kết thúc terminal operation giúp stream không thể được tái sử dụng hợp lệ theo contract, nhưng **không tự gọi `close`** chỉ vì count đã xong. Tránh dựa vào implementation mà không có ownership protocol.

### 13.2. Dùng try-with-resources cho mọi đường thoát

```java
try (Stream<String> lines = Files.lines(file)) {
    if (someCondition) {
        return lines.findFirst().orElse(null);
    }
    return lines.filter(s -> !s.isBlank()).findFirst().orElse(null);
}
```

Đây là method minh họa trả `String`, biến `file`/`someCondition` có sẵn. Dù một trong hai `return` được thực hiện, JVM vẫn gọi `lines.close()`.

### 13.3. Stream không được dùng lại sau terminal operation

Ví dụ:

```java
try (Stream<String> lines = Files.lines(file)) {
    long all = lines.count();
    // long second = lines.count(); // Sai: không dùng lại stream.
}
```

Phải tạo stream mới nếu cần pipeline mới; nếu tài nguyên file cần mở lại, đọc từ `Files.lines(file)` trong một try-with-resources mới, không tái sử dụng stream đã tiêu thụ.

### 13.4. Close sau khi short-circuit vẫn quan trọng

Nếu pipeline dùng:

```java
try (Stream<String> lines = Files.lines(file)) {
    return lines
            .filter(s -> s.contains("FATAL"))
            .findAny()
            .isPresent();
}
```

đoạn minh họa này chỉ cần một dòng phù hợp để dừng. Tuy nhiên Stream backed bởi file vẫn phải đóng. **Không đợi đọc hết file mới close**, vì short-circuit thường là mục đích của việc duyệt lazy.

## 14. Stream.onClose(): hook được gọi khi close thật sự

`BaseStream.onClose(Runnable closeHandler)` đăng ký handler chạy khi Stream được đóng. Đây không phải callback “terminal operation đã xong”.

Ví dụ:

```java
AtomicInteger closed = new AtomicInteger();

try (Stream<String> values =
        Stream.of("A", "B").onClose(closed::incrementAndGet)) {
    System.out.println(values.findFirst().orElseThrow());
}

System.out.println(closed.get()); // 1.
```

Trong ví dụ, `Stream.of` không giữ file handle nhưng ta gắn một `onClose` hook để minh họa lifecycle. Handler chỉ chạy khi resource `values` được đóng do try-with-resources.

### 14.1. onClose không phải “tự close”

Sai:

```java
Stream<String> stream = Files.lines(file)
        .onClose(() -> log("closed"));

stream.count();
// Handler chưa được bảo đảm chạy nếu không gọi close.
```

`onClose` chỉ đăng ký hành động khi close xảy ra. Muốn handler chạy và file được giải phóng, vẫn phải dùng `try-with-resources` hoặc `close()` đúng ownership.

### 14.2. Nhiều onClose handlers

Theo Javadoc, close handlers được thực thi theo **thứ tự đăng ký**; nếu một handler ném exception, các handler còn lại vẫn được chạy và các ngoại lệ tiếp theo có thể được lưu dạng suppressed. Không nên viết handler chứa logic phức tạp, chặn network hoặc cố gắng tái sử dụng stream đã đóng.

### 14.3. Stream.map/filter không phải resource ownership boundary mới

Khi:

```java
try (Stream<String> lines = Files.lines(file)) {
    long n = lines
            .filter(s -> !s.isBlank())
            .map(String::trim)
            .count();
}
```

các intermediate operations là một phần của cùng pipeline. Không cần khai báo thêm resource cho mỗi `filter` hoặc `map`. Đóng root I/O-backed stream trong try-with-resources là mô hình dễ kiểm soát.

**Không tách pipeline ra khỏi scope** rồi đóng nguồn quá sớm, vì những operations lazy chỉ chạy lúc terminal được gọi.

## 15. API boundary và quyền sở hữu: ai phải đóng?

Một thiết kế có thể **tạo và xử lý resource trong cùng method**:

```java
long countNonEmpty(Path file) throws IOException {
    try (Stream<String> lines = Files.lines(file)) {
        return lines.filter(s -> !s.isBlank()).count();
    }
}
```

Ở đây service mở, dùng và đóng stream; caller chỉ nhận primitive `long`, không thể vô tình dùng resource đã đóng.

Hoặc service **trả Stream**:

```java
Stream<String> streamLines(Path file) throws IOException {
    return Files.lines(file);
}
```

Lúc này quyền sở hữu được **chuyển cho caller**. Cần ghi contract:

> Caller phải đóng Stream bằng try-with-resources sau khi tiêu thụ; các thao tác lazy chỉ hợp lệ trước close.

Caller đúng:

```java
try (Stream<String> stream = streamLines(file)) {
    List<String> lines = stream.limit(10).toList();
}
```

### 15.1. Bẫy: trả stream đã bị đóng

Sai:

```java
Stream<String> badStream(Path file) throws IOException {
    try (Stream<String> lines = Files.lines(file)) {
        return lines; // Trả reference sẽ bị đóng ngay khi rời block.
    }
}
```

Caller nhận một stream không còn sống và có thể gặp `IllegalStateException` khi terminal operation. Chỉ trả **dữ liệu đã materialize** khỏi block, hoặc trả **stream sống và chuyển ownership** như mẫu trước.

### 15.2. Bẫy: borrowed resource bị đóng nhầm

Giả sử caller đã có reader sẽ dùng tiếp:

```java
long countBorrowed(BufferedReader reader) {
    return reader.lines().count();
}
```

Ví dụ này **không sở hữu reader** và không đóng nó. Nhưng nó vẫn **tiêu thụ nội dung reader**, nên phải document vị trí đọc sau khi phương thức chạy. Không đưa `reader` vào `try (reader)` nếu caller dự kiến sử dụng tiếp.

Nếu method nhận reader và có ý định đóng sau khi dùng, phải ghi rõ nó **nhận ownership**, chẳng hạn đặt tên `consumeAndCloseReader` hoặc ghi Javadoc contract.

### 15.3. Hướng thiết kế ưu tiên

- API cấp thấp trả Stream I/O-backed khi caller cần xử lý lazy và chấp nhận ownership contract.
- API dịch vụ cấp cao thường nên trả **dữ liệu đã hoàn thành** hoặc một đối tượng quản lý scope, giúp ít caller phải nhớ close.
- Không tạo một field singleton `Stream<String>` từ Files.lines rồi chia sẻ cho nhiều requests; Stream không dành để chạy lặp/tiêu thụ đa lần, và file handle có vòng đời riêng.
- Nếu cần cache, cache **dữ liệu đã đọc** hoặc thiết kế cache có lifecycle rõ, không cache stream đang mở vô hạn.

## 16. Xử lý lỗi I/O: checked IOException và UncheckedIOException

`Files.lines(file)` có thể ném **`IOException` khi mở file**. Nhưng nó là lazy stream: lỗi đọc file xảy ra **sau khi method đã trả về**, trong khi bạn đang gọi terminal operation.

Với API stream-backed I/O, những lỗi đọc trong pipeline có thể xuất hiện dưới dạng **`UncheckedIOException`** vì chức năng pipeline không khai báo checked `IOException`.

Ví dụ:

```java
try (Stream<String> lines = Files.lines(file)) {
    long count = lines.count();
} catch (UncheckedIOException error) {
    IOException cause = error.getCause();
    // Xử lý lỗi I/O xảy ra trong quá trình duyệt.
} catch (IOException error) {
    // Xử lý lỗi mở file.
}
```

Đây là ví dụ khái quát; chi tiết chính xác của exception có thể phụ thuộc API và tình huống thực tế. Code phải import `java.io.*` và `java.nio.file.*`.

**Lưu ý:** Trong Java, `UncheckedIOException` extends `RuntimeException`, không phải `IOException`; bắt `IOException` đơn lẻ không phủ hết lỗi I/O được wrap trong pipeline.

### 16.1. Không catch rồi trả số liệu sai mà không báo

Sai về nghiệp vụ:

```java
try (Stream<String> lines = Files.lines(file)) {
    return lines.count();
} catch (Exception error) {
    return 0; // Nhầm lỗi I/O với file có 0 dòng.
}
```

Nếu file không mở được hoặc đọc lỗi, trả 0 sẽ che lỗi và làm số liệu có vẻ hợp lệ. Chỉ fallback khi domain thực sự cho phép, và cần phân biệt “không có dữ liệu” với “đọc thất bại”.

### 16.2. Close có thể tự phát sinh lỗi

Ngay cả khi toàn bộ body thành công, `close()` có thể throw theo implementation. Với `InputStream/Reader/Writer`, lỗi thường là `IOException`; với `Stream.close` không khai báo checked exception, lỗi có thể được wrap trong unchecked type.

Đừng giả định try-with-resources **luôn khiến operation thành công**. Nó bảo đảm có nỗ lực close theo hợp đồng, nhưng không biến một lỗi nền tảng thành dữ liệu đúng.

### 16.3. InterruptedException và resource closing

Một công việc có thể bị interrupt trong lúc đang xử lý; nếu exception thoát ra khỏi body của try, các resource đã mở vẫn được đóng theo quy tắc. Tuy nhiên, try-with-resources không tự làm một I/O bất đồng bộ bên ngoài ngừng lại và không thay thế timeout/cancellation của network client.

Nếu tự implement `AutoCloseable.close()`, Javadoc khuyến cáo không ném `InterruptedException` từ close vì tương tác với interrupted status và suppression có thể gây hành vi khó dự đoán.

## 17. Một số nguyên tắc vận hành quan trọng

### 17.1. Tránh giữ file handle quá lâu

Đừng mở `Files.lines` ở đầu một HTTP request rồi thực hiện rất nhiều công việc khác trước khi tiêu thụ; giữ scope try hẹp quanh việc đọc dữ liệu. Không gọi network/database IO chậm trong một `filter` callback nếu không cần: stream nguồn file sẽ giữ handle mở suốt lúc terminal operation chạy.

### 17.2. Kiểm soát file lớn

`Files.readAllLines` và `Files.readString` thuận tiện nhưng đưa toàn bộ nội dung vào memory. Với file lớn, dùng streaming/splitting theo dòng khi phù hợp; vẫn phải close. Bản thân lazy processing **không bảo đảm memory constant** nếu pipeline có `sorted()`, `distinct()`, `toList()` hoặc phép gom lớn; hãy xét đặc tính stateful và output size.

### 17.3. Không xóa file trong khi stream vẫn đang mở theo giả định chung

Hệ điều hành có khác biệt về việc xóa/đổi tên file đang được dùng. Để code đa nền tảng, hoàn tất xử lý và close stream trước khi `Files.delete` hoặc `Files.move` nếu có thể. Không dựa vào hành vi của một máy Linux/Windows làm contract chung.

### 17.4. Đóng một wrapper có thể đóng cả nguồn dưới

Ví dụ `BufferedReader` được tạo trên `InputStreamReader`, vốn bọc một `InputStream`. Khi đóng wrapper ngoài, implementation tiêu chuẩn thường đóng nguồn bên dưới. Nếu bạn không muốn đóng nguồn underlying (ví dụ `System.in`), đừng quên rằng wrapper ngoài có thể giành luôn ownership.

### 17.5. Đừng vô tình đóng System.in/System.out

`System.in` và `System.out` là streams toàn process được cấp bởi runtime. Trong ứng dụng thông thường, không nên:

```java
try (InputStream in = System.in) {
    // Sau block, System.in bị đóng cho những phần khác của chương trình.
}
```

Hoặc:

```java
try (PrintStream out = System.out) {
    out.println("hello");
}
```

Về mặt cú pháp hợp lệ, nhưng **đóng shared global stream** có thể ảnh hưởng toàn ứng dụng. Chỉ close tài nguyên mà method/module thực sự sở hữu. Nếu cần ghi ra `System.out`, thường chỉ dùng nó, không cần đóng sau mỗi lời gọi.

### 17.6. File copy và atomic write là hai yêu cầu khác nhau

`try-with-resources` bảo đảm đóng InputStream/OutputStream khi kết thúc, nhưng không đảm bảo file đích được cập nhật theo kiểu all-or-nothing. Nếu chương trình crash giữa chừng, target có thể chứa dữ liệu một phần.

Khi cần cập nhật file cấu hình quan trọng:

1. Ghi dữ liệu vào **file tạm** trong cùng filesystem khi phù hợp.
2. Đóng writer/output stream thành công.
3. Kiểm tra nội dung/metadata nếu nghiệp vụ yêu cầu.
4. Dùng `Files.move` với `ATOMIC_MOVE` nếu hệ thống file hỗ trợ, có xử lý `AtomicMoveNotSupportedException`.
5. Có chính sách backup/rollback/durability nếu cần.

Đây là bổ sung về vận hành, không thay thế nguyên tắc close.

## 18. Chương trình Java 17+ hoàn chỉnh: đọc/ghi, đóng nhiều resources và suppressed exceptions

Tạo file **`ResourceStreamDemo.java`**. Chương trình:

- Tạo một thư mục tạm và một file UTF-8 chứa các dòng kể cả dòng trống.
- Dùng `Files.lines` để đếm non-empty lines và tìm dòng đầu bằng `findFirst`.
- Dùng `BufferedReader.lines()` nhưng quản lý đóng chính reader.
- Dùng `BufferedWriter` ghi text và xác minh nội dung sau close.
- Sao chép byte qua `InputStream.transferTo(OutputStream)` trong một try gồm hai resources.
- Duyệt thư mục qua `Files.list` và `Files.walk`, đóng Stream đúng scope.
- Gắn `Stream.onClose` để kiểm tra hook chạy sau khi close.
- Dùng resource giả để kiểm chứng thứ tự close **ngược thứ tự mở**.
- Kiểm chứng lỗi body được giữ lại, lỗi đóng nằm trong `getSuppressed()`.
- Kiểm chứng khi initializer của resource sau thất bại, resource trước vẫn được đóng.
- Dùng cú pháp Java 9 `try(existing)` cho một resource effectively final.
- Xóa thư mục tạm trong `finally` bằng một `Files.walk` riêng có try-with-resources.

```java
import java.io.*;
import java.nio.charset.*;
import java.nio.file.*;
import java.util.*;
import java.util.stream.*;
import java.util.concurrent.atomic.*;

public class ResourceStreamDemo {
    static final class LoggedResource implements AutoCloseable {
        final String name;
        final List<String> events;
        final boolean failOnClose;

        LoggedResource(String name,
                       List<String> events,
                       boolean failOnClose) {
            this.name = name;
            this.events = events;
            this.failOnClose = failOnClose;
            events.add("open:" + name);
        }

        void touch() {
            events.add("use:" + name);
        }

        @Override
        public void close() throws IOException {
            events.add("close:" + name);
            if (failOnClose) {
                throw new IOException("close-" + name);
            }
        }
    }

    static LoggedResource failToOpenSecond() throws IOException {
        throw new IOException("open-second-failed");
    }

    static void require(boolean ok, String why) {
        if (!ok) {
            throw new AssertionError(why);
        }
    }

    static void deleteTree(Path root) throws IOException {
        if (root == null || !Files.exists(root)) {
            return;
        }
        try (Stream<Path> walk = Files.walk(root)) {
            for (Path path : walk
                    .sorted(Comparator.reverseOrder())
                    .toList()) {
                Files.deleteIfExists(path);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory(
                "java-twr-stream-");
        try {
            Path file = root.resolve("words.txt");
            Files.writeString(file,
                    "alpha\n\nbeta\nalpha\n",
                    StandardCharsets.UTF_8);

            try (Stream<String> lines =
                    Files.lines(file, StandardCharsets.UTF_8)) {
                long count = lines
                        .filter(s -> !s.isBlank())
                        .count();
                require(count == 3, "nonEmpty");
                System.out.println("nonEmptyLines=" + count);
            }

            try (Stream<String> lines = Files.lines(file)) {
                String first = lines
                        .filter(s -> !s.isBlank())
                        .findFirst()
                        .orElseThrow();
                System.out.println("firstNonEmpty=" + first);
            }

            try (BufferedReader reader =
                    Files.newBufferedReader(
                            file, StandardCharsets.UTF_8)) {
                System.out.println("bufferedReaderLines="
                        + reader.lines().count());
            }

            Path out = root.resolve("out.txt");
            try (BufferedWriter writer =
                    Files.newBufferedWriter(
                            out, StandardCharsets.UTF_8)) {
                writer.write("OUT");
                writer.newLine();
            }

            System.out.println("writtenText="
                    + Files.readString(
                            out, StandardCharsets.UTF_8)
                            .strip());

            Path copy = root.resolve("copy.txt");
            long bytesCopied;
            try (InputStream in = Files.newInputStream(file);
                 OutputStream outBinary =
                         Files.newOutputStream(copy)) {
                bytesCopied = in.transferTo(outBinary);
            }

            require(bytesCopied == 18
                    && Files.mismatch(file, copy) == -1,
                    "copy");
            System.out.println("copyBytes=" + bytesCopied);
            System.out.println("copyMatches="
                    + (Files.mismatch(file, copy) == -1));

            try (Stream<Path> entries = Files.list(root)) {
                System.out.println("listedFiles="
                        + entries
                                .map(p -> p.getFileName().toString())
                                .sorted()
                                .toList());
            }

            try (Stream<Path> walked = Files.walk(root)) {
                System.out.println("walkedPaths="
                        + walked.count());
            }

            AtomicInteger closes = new AtomicInteger();
            try (Stream<String> values = Stream
                    .of("x", "y")
                    .onClose(closes::incrementAndGet)) {
                System.out.println("collectionStreamFirst="
                        + values.findFirst().orElseThrow());
            }
            System.out.println("onCloseCount=" + closes.get());

            List<String> events = new ArrayList<>();
            try (LoggedResource a =
                         new LoggedResource(
                                 "A", events, false);
                 LoggedResource b =
                         new LoggedResource(
                                 "B", events, false)) {
                a.touch();
                b.touch();
            }
            System.out.println("closeOrder="
                    + String.join(",", events));

            List<String> failureEvents = new ArrayList<>();
            String primary = "none";
            List<String> suppressed = new ArrayList<>();

            try (LoggedResource x =
                         new LoggedResource(
                                 "X", failureEvents, true);
                 LoggedResource y =
                         new LoggedResource(
                                 "Y", failureEvents, true)) {
                throw new IllegalStateException("body-failed");
            } catch (IllegalStateException error) {
                primary = error.getMessage();
                for (Throwable item : error.getSuppressed()) {
                    suppressed.add(item.getMessage());
                }
            }

            require(primary.equals("body-failed")
                    && suppressed.equals(
                            List.of("close-Y", "close-X")),
                    "suppression");
            System.out.println("primaryFailure=" + primary);
            System.out.println("suppressedCloseFailures="
                    + suppressed);
            System.out.println("failureCloseOrder="
                    + String.join(",", failureEvents));

            List<String> initEvents = new ArrayList<>();
            String init = "none";
            try (LoggedResource first =
                         new LoggedResource(
                                 "first", initEvents, false);
                 LoggedResource second = failToOpenSecond()) {
                first.touch();
            } catch (IOException error) {
                init = error.getMessage();
            }
            System.out.println("initializationFailure=" + init);
            System.out.println("openedBeforeFailure="
                    + String.join(",", initEvents));

            LoggedResource existing =
                    new LoggedResource(
                            "existing", new ArrayList<>(), false);
            List<String> existingEvents = existing.events;

            try (existing) {
                existing.touch();
            }
            System.out.println("existingResource="
                    + String.join(",", existingEvents));

            System.out.println("ALL CHECKS PASSED");
        } finally {
            deleteTree(root);
        }
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac ResourceStreamDemo.java
java ResourceStreamDemo
```

**Stdout chính xác**, không in đường dẫn random của thư mục tạm:

```text
nonEmptyLines=3
firstNonEmpty=alpha
bufferedReaderLines=4
writtenText=OUT
copyBytes=18
copyMatches=true
listedFiles=[copy.txt, out.txt, words.txt]
walkedPaths=4
collectionStreamFirst=x
onCloseCount=1
closeOrder=open:A,open:B,use:A,use:B,close:B,close:A
primaryFailure=body-failed
suppressedCloseFailures=[close-Y, close-X]
failureCloseOrder=open:X,open:Y,close:Y,close:X
initializationFailure=open-second-failed
openedBeforeFailure=open:first,close:first
existingResource=open:existing,use:existing,close:existing
ALL CHECKS PASSED
```

### 18.1. Giải thích phần Files.lines

`Files.writeString` tạo file chứa bốn dòng logic: "alpha", dòng trống, "beta", "alpha". Lọc `!isBlank()` cho **3 dòng**, còn `reader.lines().count()` đếm cả dòng trống nên bằng **4**. Dòng đầu tiên không trống là "alpha".

Khi hai khối try cho `Files.lines` kết thúc, các streams được đóng. Đặc biệt `findFirst` không cần đọc tới cuối file nhưng vẫn được close nhờ try-with-resources.

### 18.2. Giải thích phần ghi và copy

`BufferedWriter` ghi "OUT" và một dấu xuống dòng, rồi được close trước khi `Files.readString` đọc lại nội dung. Kết quả `strip()` là "OUT".

File nguồn UTF-8 chỉ dùng ký tự ASCII và newline `\n`, tổng cộng **18 bytes**. `InputStream.transferTo` sao chép 18 bytes; `Files.mismatch(file,copy)==-1` chứng minh không có chỗ khác biệt theo API.

`Files.mismatch` có từ Java 12; đúng với target Java 17+ của ví dụ. Với Java 8 gốc, bạn có thể dùng so sánh byte array phù hợp nhưng không cần thay trong bài này.

### 18.3. Giải thích phần thư mục

Lúc gọi `Files.list(root)` có ba file: `copy.txt`, `out.txt`, `words.txt`. Pipeline `sorted()` đảm bảo output tên file có thứ tự xác định. `Files.walk(root)` tính cả root path và ba file bên dưới, nên count **4**. Cả hai directory streams được đóng trong try.

### 18.4. Giải thích onClose

Stream từ `Stream.of("x","y")` không cần giải phóng file, nhưng handler `onClose` đếm được **1** vì block try gọi `close()` một lần. `findFirst` không tự kích hoạt handler; sự kiện xảy ra khi resource scope đóng.

### 18.5. Giải thích reverse close order

`open:A,open:B,use:A,use:B,close:B,close:A` thể hiện thứ tự mở trái sang phải, đóng phải sang trái. Thứ tự đóng được xác định bởi ngôn ngữ, không dựa vào thread scheduling.

### 18.6. Giải thích suppressed exceptions

Lỗi chính `"body-failed"` được propagate. Hai `close()` lần lượt ném `IOException("close-Y")` và `IOException("close-X")`, được giữ lại trong danh sách suppressed theo thứ tự **Y rồi X**. Đây là lý do try-with-resources phù hợp hơn cleanup thủ công dễ làm mất lỗi đầu tiên.

### 18.7. Giải thích initializer failure

`first` mở thành công, `failToOpenSecond()` ném `IOException("open-second-failed")`. Body không được gọi, và `first.close()` vẫn được thực thi. Log `open:first,close:first` xác minh điều này.

### 18.8. Giải thích try(existing)

Đối tượng `existing` đã tạo bên ngoài try; biến là effectively final. Java 9+ cho phép viết `try (existing)`; khi ra scope, close được thực thi. Đừng dùng pattern này với resource “mượn” từ caller nếu method không sở hữu nó.

### 18.9. Vì sao deleteTree cũng phải đóng Files.walk

`deleteTree` tạo một Stream<Path> từ `Files.walk(root)` và thu danh sách `sorted(reverseOrder())` để xóa file trước rồi tới thư mục. Nó cũng dùng try-with-resources để đóng directory handles; không để cleanup gây leak thứ hai.

Trong ứng dụng lớn, hãy cân nhắc xử lý lỗi cleanup và giới hạn kích thước cây thư mục. Bài demo tạo một thư mục tạm rất nhỏ nên cách thu `toList` phù hợp.

## 19. Các lỗi phổ biến cần tránh

### Lỗi 1: Nghĩ mọi Stream<T> đều cần close

Stream từ `List.stream()` thường không giữ file descriptor; yêu cầu close nằm ở **nguồn I/O-backed** hoặc `onClose` handlers. **Sửa:** xác định source và ownership thay vì áp một quy tắc mơ hồ theo tên kiểu.

### Lỗi 2: Nghĩ terminal operation tự đóng Files.lines

`count/forEach/findFirst` không đảm bảo close file. **Sửa:** `try (Stream<String> lines = Files.lines(...))` quanh toàn bộ tiêu thụ.

### Lỗi 3: Dùng Files.list hoặc Files.walk mà bỏ qua close

Các operations này có thể giữ directory handles; **phải close returned stream** sau khi duyệt. Đừng gọi trực tiếp `Files.walk(root).count()` liên tục mà không giữ/đóng stream.

### Lỗi 4: Chỉ đóng stream của BufferedReader.lines, không đóng reader

`BufferedReader` là resource sở hữu file; stream do `reader.lines()` không được hứa tự đóng reader. **Sửa:** đặt reader vào try-with-resources.

### Lỗi 5: Trả Files.lines stream đã bị đóng

`return lines` bên trong try khiến resource close trước khi caller dùng. **Sửa:** materialize kết quả trong try, hoặc trả stream sống và ghi rõ caller phải close.

### Lỗi 6: Quên ownership khi API trả Stream

Caller không biết cần close nên dễ leak file. **Sửa:** Javadoc rõ, wrapper scope hoặc API trả List/summary tùy nhu cầu.

### Lỗi 7: Đóng stream global System.in/System.out

Đây là resources chia sẻ toàn process. **Sửa:** chỉ close những resources mình thực sự sở hữu; tránh chấm dứt input/output của phần khác.

### Lỗi 8: Đóng cả wrapper và underlying resource không suy nghĩ

Double close có thể vô hại với một số lớp chuẩn, nhưng không phải bảo đảm của mọi AutoCloseable. **Sửa:** khi wrapper sở hữu nguồn, thường chỉ quản lý wrapper ngoài cùng.

### Lỗi 9: Dùng flush thay cho close

`flush` không giải phóng file handle. **Sửa:** luôn kết thúc writer/output lifecycle bằng close theo contract.

### Lỗi 10: Nghĩ close đảm bảo file update atomic/durable

Đóng writer không biến việc ghi nhiều bytes thành một transaction. **Sửa:** dùng temp file/atomic move/durability protocol nếu business yêu cầu.

### Lỗi 11: Bỏ qua IOException trong khi đóng

Thất bại lúc close có thể có nghĩa dữ liệu chưa ghi hoàn chỉnh. **Sửa:** xử lý/propagate đúng lỗi; kiểm tra suppressed khi body cũng lỗi.

### Lỗi 12: Nhầm getCause và getSuppressed

Cause là lỗi bên dưới bị wrap; suppressed là lỗi cleanup được giữ khi exception khác ưu tiên. **Sửa:** hiểu cả hai để debug.

### Lỗi 13: Viết finally thủ công làm lỗi close che lỗi body

Nếu thiếu logic suppression, exception close có thể làm mất context lỗi chính. **Sửa:** ưu tiên try-with-resources.

### Lỗi 14: Mở hai resource nhưng chỉ đóng khi cả hai khởi tạo thành công

Nếu mở resource thứ hai lỗi, resource thứ nhất có thể leak. **Sửa:** khai báo cùng try-with-resources để Java tự đóng resources đã mở.

### Lỗi 15: Có return/throw sớm rồi bỏ qua close

Nếu dùng try-with-resources, close vẫn chạy. **Sửa:** dùng scope try bao phủ toàn bộ đường ra; đừng tự tách pipeline ra ngoài scope.

### Lỗi 16: Chỉ mở file nhưng không định nghĩa charset

Mặc định charset của một API có thể khác nhau theo phiên bản và cách gọi. **Sửa:** dùng `StandardCharsets.UTF_8` khi file format quy định UTF-8; phân biệt overload default cụ thể đã có contract.

### Lỗi 17: Giả định Files.lines đọc toàn bộ file ngay khi gọi

`Files.lines` trả lazy stream. **Sửa:** giữ nguồn mở khi terminal operation chạy; hiểu checked IOException khi open và UncheckedIOException khi lazy traversal.

### Lỗi 18: Bắt IOException nhưng quên UncheckedIOException

Một số lỗi đọc trong pipeline được wrap thành unchecked type. **Sửa:** xác định loại lỗi có thể xuất hiện từ API và quan sát `getCause()`.

### Lỗi 19: Duyệt Stream hai lần

Stream đã consumable một lần; không được reuse để chạy terminal operation thứ hai. **Sửa:** tạo stream mới trong một scope mới hoặc materialize dữ liệu đủ nhỏ.

### Lỗi 20: Dùng Stream.onClose rồi nghĩ nó tự close

`onClose` là callback khi close, không phải auto-closer. **Sửa:** thực sự đóng bằng try-with-resources.

### Lỗi 21: Đóng resource ngay sau khi trả lazy pipeline ra ngoài

Caller chỉ xử lý pipeline sau khi nguồn đã bị đóng, dẫn đến lỗi. **Sửa:** tiêu thụ trong try hoặc chuyển ownership đúng.

### Lỗi 22: Không giới hạn file size rồi dùng readAllLines/toList/sorted

Đọc/gom toàn bộ dữ liệu có thể gây áp lực memory. **Sửa:** chọn streaming và bounded operations phù hợp, tránh stateful pipeline không cần thiết.

### Lỗi 23: Đóng resource “mượn” từ caller

Caller còn cần reader/stream mà method đóng nó. **Sửa:** phân biệt owned và borrowed resources trong API contract.

### Lỗi 24: Dùng FileSystem của ZIP/JAR mà không đóng owner

Một số file system/providers trả `FileSystem` hoặc `ZipFile` có lifecycle riêng. **Sửa:** đóng **owner resource** phù hợp theo Javadoc, không tưởng một `Stream<Path>` tùy ý tự đóng toàn bộ provider.

### Lỗi 25: Ỷ lại GC hoặc shutdown JVM để giải phóng handles

Cleanup có thể chậm, gây lỗi tải cao hoặc leak cho request kế tiếp. **Sửa:** close chủ động ngay khi không còn cần resource.

### Lỗi 26: Đọc hoặc xóa file khi stream còn đang mở và dựa vào hành vi một OS

Hệ điều hành khác nhau trong file locking/unlink semantics. **Sửa:** đóng stream trước khi xóa/move khi có thể; không dựa vào đặc điểm một máy dev.

### Lỗi 27: Không dọn tài nguyên tạo trong unit test

Tests tạo file/temp directory có thể để lại rác và bị khóa trên Windows. **Sửa:** dùng finally cleanup, đóng directory stream dùng để duyệt tệp cần xóa.

### Lỗi 28: Ghi catch(Exception) rồi trả số 0 cho mọi lỗi

Báo mất file hoặc đọc lỗi thành “file có 0 dòng” là sai dữ liệu. **Sửa:** phân biệt invalid path, empty file, decode errors và I/O failure.

### Lỗi 29: Viết API mở resource trong constructor rồi không có close

Một class giữ BufferedReader/Stream lâu dài cần contract close tại lifecycle component. **Sửa:** implement AutoCloseable nếu thực sự sở hữu resources, hoặc thiết kế mở-đóng per operation.

### Lỗi 30: Giữ Files.walk mở qua nhiều công việc không liên quan

Directory handles chiếm tài nguyên trong khi không được sử dụng. **Sửa:** giới hạn scope của try theo thao tác duyệt thật sự cần thiết.

## 20. Bài tập thực hành và đáp án

**Bài 1.** `Files.lines(path)` trả kiểu gì và có cần close không?

**Đáp án:** Trả `Stream<String>` gắn với file đang mở; dùng try-with-resources hoặc cấu trúc tương tự để close sau khi dùng.

**Bài 2.** `List.of(1,2,3).stream().count()` có cần try-with-resources để đóng file không?

**Đáp án:** Không, đây là Stream backed bởi List in-memory, không có file resource. Tuy nhiên stream có thể có onClose hook trong những trường hợp đặc biệt.

**Bài 3.** Đọc `InputStream` xong thì phương thức nào giải phóng tài nguyên?

**Đáp án:** `close()`. Nếu method sở hữu stream, đưa InputStream vào header try-with-resources để close tự động.

**Bài 4.** `Files.lines(path).findFirst()` đã chạy xong. Có thể cho rằng file đã đóng không?

**Đáp án:** Không. Terminal operation kể cả short-circuit không tự bảo đảm close stream; cần try-with-resources.

**Bài 5.** `Files.list(dir)` và `Files.walk(dir)` khác nhau thế nào về traversal?

**Đáp án:** `list` cho entries trực tiếp, `walk` duyệt cây thư mục từ path bắt đầu. Cả hai trả Stream có thể giữ directory handles và cần close.

**Bài 6.** `Files.find(...)` có cần close không?

**Đáp án:** Có. Nó trả Stream<Path> dựa trên việc duyệt file tree, cần đóng resources.

**Bài 7.** Một `BufferedReader reader` có `reader.lines()`. Chỉ close Stream trả về có đủ để bảo đảm reader được đóng không?

**Đáp án:** Không theo contract. Đặt chính BufferedReader vào try-with-resources.

**Bài 8.** Vì sao `Files.readAllLines` không yêu cầu close return value?

**Đáp án:** Nó trả `List<String>` đã đọc vào memory, không trả open file-backed Stream. Method tự quản lý file access nội bộ.

**Bài 9.** Khi header có resource A rồi B, JVM đóng theo thứ tự nào?

**Đáp án:** Đóng B trước rồi A; khởi tạo A trước rồi B.

**Bài 10.** Nếu body throw E và B.close throw F, exception nào là primary?

**Đáp án:** E; F được thêm vào `E.getSuppressed()`. Nếu A.close cũng lỗi, lỗi A thường được bổ sung suppressed tiếp theo.

**Bài 11.** Nếu body bình thường nhưng close ném IOException thì try-with-resources có trả thành công không?

**Đáp án:** Không nhất thiết. Lỗi close có thể trở thành lỗi propagate chính; không được coi tài nguyên đã được ghi/đóng thành công nếu có failure.

**Bài 12.** Nếu mở A thành công, mở B thất bại, A có được close không?

**Đáp án:** Có. Java đóng resources đã khởi tạo thành công khi một resource sau thất bại, kể cả body chưa chạy.

**Bài 13.** `getCause()` và `getSuppressed()` khác nhau?

**Đáp án:** Cause biểu thị quan hệ exception được wrap, suppressed ghi nhận các lỗi phụ thường phát sinh trong cleanup khi một lỗi khác đã được ưu tiên.

**Bài 14.** `try (reader)` với reader khai báo trước hỗ trợ từ phiên bản nào?

**Đáp án:** Java 9, khi biến final/effectively final và được khởi tạo chắc chắn. Java 8 gốc cần khai báo resource trong header.

**Bài 15.** Một method trả `Stream<String>` từ Files.lines. Ai phải close?

**Đáp án:** Caller nếu method chuyển ownership cho caller. Phải ghi rõ hợp đồng và hướng dẫn caller dùng try-with-resources.

**Bài 16.** Vì sao `return lines` bên trong `try (Stream<String> lines = Files.lines(...))` sai?

**Đáp án:** Try tự đóng stream khi rời block, nên caller nhận reference đã đóng; lazy traversal sau đó sẽ lỗi.

**Bài 17.** Mẫu `try(BufferedWriter w = Files.newBufferedWriter(...))` có đảm bảo file được cập nhật atomic trên filesystem không?

**Đáp án:** Không. Nó bảo đảm close theo lifecycle; atomic replacement/durability cần cơ chế khác.

**Bài 18.** `Stream.onClose(handler)` có chạy ngay sau `count()` không?

**Đáp án:** Không tự động; handler chạy khi `close()` được gọi. Try-with-resources gọi close khi thoát block.

**Bài 19.** Vì sao không nên đóng System.out sau khi in một báo cáo?

**Đáp án:** Đây là stream chia sẻ toàn process; đóng nó có thể làm phần khác của ứng dụng không in được nữa.

**Bài 20.** `Files.lines` có thể ném IOException khi open và UncheckedIOException khi pipeline chạy không?

**Đáp án:** Có, tùy thời điểm lỗi. Vì stream lazy, lỗi đọc sau khi tạo stream có thể được wrap thành UncheckedIOException.

**Bài 21.** Stream dùng `limit(5)` trên Files.walk vẫn cần close?

**Đáp án:** Có. Partial traversal không đảm bảo đóng directory handles; cần try-with-resources.

**Bài 22.** Chỉ đóng BufferedInputStream wrapper ngoài có thể đóng nguồn FileInputStream không?

**Đáp án:** Có theo implementation chuẩn của wrapper khi nó sở hữu nguồn; vẫn phải hiểu ownership và không suy ra mọi AutoCloseable double close đều an toàn.

**Bài 23.** Trong chương trình demo, tại sao file words.txt chứa 4 dòng nhưng `nonEmptyLines=3`?

**Đáp án:** Một dòng là rỗng; filter bỏ dòng trống trước khi count.

**Bài 24.** Tại sao `Files.walk(root).count()` trong demo cho 4?

**Đáp án:** Có root directory và ba file bên trong. Khi duyệt root, Files.walk bao gồm cả root.

**Bài 25.** Nếu app cần stream một file cực lớn, `Files.readAllLines` có phải lựa chọn tối ưu cho memory không?

**Đáp án:** Không. Nó materialize toàn bộ danh sách; Files.lines/BufferedReader có thể duyệt lazy nhưng phải close và tránh pipeline gom toàn bộ dữ liệu không cần thiết.

## 21. Checklist production

- [ ] Phân biệt `java.io.InputStream/OutputStream` với `java.util.stream.Stream<T>`.
- [ ] Xác định nguồn Stream có tài nguyên I/O (file, directory, socket, process) hay chỉ là in-memory collection.
- [ ] `Files.lines` được tiêu thụ bên trong `try (Stream<?> ... )` và close kịp thời.
- [ ] `Files.list`, `Files.walk` và `Files.find` đều được đặt trong một scope đảm bảo close.
- [ ] Với `BufferedReader.lines()`, đóng **BufferedReader owner**, không chỉ đóng pipeline.
- [ ] InputStream/OutputStream/Reader/Writer do method sở hữu được quản lý bằng try-with-resources.
- [ ] Mỗi resource được đóng theo đúng ownership contract; không tùy tiện đóng System.in/System.out.
- [ ] Không dựa vào `count/findFirst/forEach/toList/limit` để tự close Stream.
- [ ] Không trả Stream đã bị đóng ra ngoài phạm vi try.
- [ ] Nếu method trả Stream sống, có Javadoc nêu caller phải close.
- [ ] Cú pháp Java 9 `try(existing)` chỉ dùng khi variable final/effectively final và resource thuộc owner phù hợp.
- [ ] Nhiều resources khai báo trái sang phải và tự close phải sang trái.
- [ ] Nếu resource sau open thất bại, resources đã mở trước vẫn được close.
- [ ] Có test/log cho cả lỗi body và lỗi close, quan sát `getSuppressed()`.
- [ ] Không nhầm suppressed với cause, không chỉ log exception message nếu cần diagnostics.
- [ ] Biết `AutoCloseable.close` có thể ném exception; không mặc định close không thể fail.
- [ ] Không cố close một wrapper hai lần nếu chưa chắc contract hỗ trợ.
- [ ] Dùng charset được quy định rõ, thường `StandardCharsets.UTF_8`.
- [ ] Phân biệt `Files.readString/readAllLines` trả dữ liệu đã materialize với `Files.lines` trả Stream lazy.
- [ ] Không materialize file rất lớn bằng `toList/sorted/readAllLines` nếu memory budget không cho phép.
- [ ] Không coi close/flush là transaction/atomic file replacement/durability.
- [ ] Test có cả short-circuit, exception, close failure, initializer failure, onClose và early return nếu phù hợp.
- [ ] Tạo/xóa tệp tạm có cleanup riêng, và stream phục vụ cleanup cũng được close.
- [ ] Không để resource còn mở qua công việc không liên quan, không trông chờ GC để dọn kịp thời.
- [ ] Không nuốt `UncheckedIOException`/`IOException` rồi trả dữ liệu giả có vẻ hợp lệ.
- [ ] Đánh dấu chính xác những API bổ sung sau Java 8 trong ví dụ Java 17+.

## 22. Tài liệu chính thức đang áp dụng

1. [Oracle Java SE 26 — Files: lines/list/walk/find, newBufferedReader/newBufferedWriter, readString/readAllLines và hợp đồng đóng](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html)
2. [Oracle Java SE 26 — Stream: đa số stream in-memory không cần đóng; I/O-backed stream cần try-with-resources](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)
3. [Oracle Java SE 26 — BaseStream: close/onClose và AutoCloseable](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/BaseStream.html)
4. [Oracle Java SE 26 — AutoCloseable: hợp đồng close và hướng dẫn khi close có thể lỗi](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/AutoCloseable.html)
5. [Oracle Java SE 26 — Closeable: IOException, đóng resources I/O](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/Closeable.html)
6. [Oracle Java SE 26 — BufferedReader: readLine/lines và lifecycle của reader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/BufferedReader.html)
7. [Oracle Java SE 26 — InputStream: transferTo và close](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/InputStream.html)
8. [Oracle Java SE 26 — OutputStream: flush và close](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/OutputStream.html)
9. [Oracle Java SE 26 — Throwable: getSuppressed/addSuppressed và lỗi khi try-with-resources cleanup](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Throwable.html)
10. [Java Language Specification (JLS 26) — `14.20.3 Try-With-Resources: thứ tự close, initializer failure, suppressed và existing resource](https://docs.oracle.com/javase/specs/jls/se26/html/jls-14.html#jls-14.20.3)
11. [dev.java — Catching and Handling Exceptions: try-with-resources và suppressed exceptions](https://dev.java/learn/exceptions/catching-handling/)

**Ghi nhớ:** Cái cần đóng không phải “mọi pipeline có tên Stream”, mà là **resource đang được mở và do code của bạn sở hữu**. Với `Files.lines`, `Files.list`, `Files.walk` và những I/O-backed Stream tương tự, luôn đặt nguồn vào **try-with-resources** và tiêu thụ trong scope ấy. Terminal operation không tự thay thế `close()`; Java đóng resources tự động theo thứ tự ngược, giữ lỗi thân try làm primary và bảo tồn lỗi đóng trong `getSuppressed()`. Với tài nguyên do caller sở hữu, hãy định nghĩa quyền đóng rõ trước khi thiết kế API.
