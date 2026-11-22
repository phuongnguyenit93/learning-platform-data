# Quản lý vòng đời Stream con trong `flatMap` và `mapMulti`

## 1. Vấn đề: một pipeline có thể sở hữu nhiều tài nguyên

Một trong những ưu điểm của **JAVA_STREAM_API** là xử lý dữ liệu khai báo: từ nguồn, ta ghép `filter`, `map`, `flatMap`, `reduce` và `collect` thành pipeline lazy. Với danh sách trong bộ nhớ, việc đóng stream thường không đáng chú ý. Nhưng khi dữ liệu đến từ tệp, thư mục, socket hoặc nguồn có tài nguyên hệ thống, **stream không còn chỉ là một dãy giá trị**.

Xét yêu cầu: tìm những dòng không rỗng trong nhiều tệp văn bản của một thư mục.

```text
Files.list(directory)   -> Stream<Path>         (stream nguồn, giữ tài nguyên thư mục)
       │
       ├── file-a.txt  -> Files.lines(a)        (stream con, giữ tài nguyên tệp A)
       ├── file-b.txt  -> Files.lines(b)        (stream con, giữ tài nguyên tệp B)
       └── file-c.txt  -> Files.lines(c)        (stream con, giữ tài nguyên tệp C)
                                    │
                                    ▼
                              Stream<String>
                                    │
                         filter / limit / collect
```

Cần trả lời **hai câu hỏi khác nhau**:

1. **Ai đóng stream nguồn** mà `Files.list` tạo ra?
2. **Ai đóng từng stream con** mà việc mở các tệp tạo ra?

Khi dùng `flatMap`, hợp đồng API có cơ chế đóng các stream con do mapper trả về. Khi dùng `mapMulti`, mapper **không trả về stream con** mà chủ động phát từng giá trị qua một `Consumer`; nếu mapper mở stream hoặc tài nguyên khác, **chính mapper phải tổ chức đóng tài nguyên đó**.

Sau bài học, bạn có thể:

- Phân biệt stream không nắm tài nguyên và stream phụ thuộc tài nguyên I/O.
- Xác định quyền sở hữu và vòng đời của stream nguồn, stream con và kết quả cuối.
- Sử dụng `try-with-resources`, `BaseStream.close` và `onClose` đúng chỗ.
- Thiết kế `flatMap` với `Files.lines` và `mapMulti` có vòng đời tài nguyên rõ ràng.
- Xử lý lỗi mở/đọc/đóng tệp, bao gồm `IOException` và `UncheckedIOException`.
- Hiểu ảnh hưởng của `limit`, `findFirst`, nguồn vô hạn và xử lý song song.
- Kiểm thử cả **giá trị trả về** lẫn **việc đóng tài nguyên**, không chỉ kiểm tra đầu ra.

Các ví dụ dùng **JDK 17 trở lên** (có `mapMulti` từ JDK 16 và `Stream.toList()` từ JDK 16). `flatMap` và `BaseStream.close` đã có từ JDK 8.

## 2. Không phải mọi `Stream` đều cần đóng

`Stream` kế thừa `BaseStream`, mà `BaseStream` mở rộng `AutoCloseable`. Vì vậy, stream có phương thức `close()` và có thể được dùng với `try-with-resources`. Nhưng **việc cần đóng hay không phụ thuộc nguồn tạo stream**.

| Nguồn | Có tài nguyên bên ngoài cần quản lý? | Cách sử dụng thường gặp |
| --- | --- | --- |
| `List.stream()`, `Set.stream()` | Thường không | Không cần `try-with-resources` |
| `Stream.of(...)`, `IntStream.range(...)` | Không, nếu chỉ tạo giá trị trong bộ nhớ | Không cần đóng chỉ vì có Stream |
| `Files.lines(path)` | Có: tài nguyên đọc tệp | Đóng stream hoặc chuyển quyền đóng theo hợp đồng |
| `Files.list(directory)` | Có: tài nguyên duyệt thư mục | `try-with-resources` |
| `Files.walk(directory)`, `Files.find(...)` | Có: tài nguyên duyệt cây tệp | `try-with-resources` |
| `BufferedReader.lines()` | Reader bên dưới vẫn cần được đóng | Đóng **`BufferedReader`**, không giả định đóng stream sẽ đóng reader |
| Stream do ứng dụng tự tạo kèm `onClose` | Tùy handler và tài nguyên liên quan | Làm rõ quyền sở hữu với caller |

**Quy tắc:** khi gọi một API trả stream, hãy đọc Javadoc của **API tạo nguồn**, không chỉ đọc Javadoc chung của `Stream`. Một terminal operation như `count()` hoặc `toList()` **không tự động gọi `close()` trên stream nguồn**.

Ví dụ đúng:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long countLines(Path file) throws IOException {
    try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
        return lines.count();
    }
}
```

`count()` tiêu thụ pipeline; khi thoát khỏi khối `try`, `lines.close()` được gọi dù không có dòng nào hay terminal operation ném lỗi.

Ngược lại:

```java
// Không cần try-with-resources cho nguồn trong bộ nhớ thông thường:
long count = java.util.List.of("Java", "Stream")
    .stream()
    .filter(s -> s.length() > 4)
    .count();
```

## 3. Hiểu `close()` và `onClose()` trước khi lồng stream

### 3.1. `close()` không giống terminal operation

Trong Java Stream API:

- `collect`, `count`, `findFirst`, `forEach` là **terminal operations**: kích hoạt/tiêu thụ pipeline.
- `close()` là hành động **giải phóng tài nguyên** và kích hoạt các close handlers đã đăng ký.
- Terminal operation kết thúc **không đồng nghĩa** stream tự được đóng.
- Stream đã đóng không được tiếp tục xử lý như pipeline mới; muốn chạy lại, phải mở nguồn mới.

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

AtomicInteger closed = new AtomicInteger();
Stream<String> source = Stream.of("A", "B")
    .onClose(closed::incrementAndGet);

long count = source.count();
System.out.println(count);        // 2
System.out.println(closed.get()); // 0: count() không tự close.

source.close();
System.out.println(closed.get()); // 1
```

Ví dụ dùng `AtomicInteger` chỉ để **quan sát vòng đời trong bài thử**, không phải khuyến khích đưa trạng thái ngoài vào mapper nghiệp vụ.

### 3.2. `onClose` đăng ký hành động dọn dẹp

`BaseStream.onClose(Runnable)` trả về stream kèm một close handler. Khi stream được đóng, các handler được thực hiện theo thứ tự đã đăng ký. Nếu có nhiều handler ném ngoại lệ, các ngoại lệ tiếp theo có thể được gắn vào ngoại lệ ban đầu dưới dạng *suppressed exceptions*.

```java
import java.util.stream.Stream;

try (Stream<String> s = Stream.of("A", "B")
        .onClose(() -> System.out.println("Đã đóng"))) {
    System.out.println(s.findFirst().orElse("Rỗng"));
}
// A
// Đã đóng
```

`onClose` không biến `count` hay `findFirst` thành thao tác tự đóng; chính `try-with-resources` trong ví dụ gọi `close`.

### 3.3. Với `BufferedReader.lines()`, chủ sở hữu là reader

`BufferedReader.lines()` cung cấp một stream đọc từ reader nhưng không chuyển quyền đóng reader cho stream một cách mặc định. Cách an toàn là đóng **chính reader**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

static long countNonBlank(Path path) throws IOException {
    try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        return reader.lines()
            .filter(line -> !line.isBlank())
            .count();
    }
}
```

Với `Files.lines(path)`, stream do chính `Files` tạo là tài nguyên cần đóng. Đừng đánh đồng hai API chỉ vì cả hai đều trả về `Stream<String>`.

## 4. `flatMap`: stream con được đóng theo hợp đồng

Chữ ký rút gọn:

```java
<R> Stream<R> flatMap(
    Function<? super T, ? extends Stream<? extends R>> mapper
)
```

Với mỗi phần tử `T`, mapper tạo một `Stream<R>`. `flatMap` kết hợp các phần tử của những stream con để trả về một stream duy nhất.

**Điểm đặc biệt của vòng đời:** Javadoc quy định **mỗi stream con do mapper tạo ra được đóng sau khi nội dung của nó được đưa vào stream kết quả**. Điều này cho phép:

```java
files.stream()
    .flatMap(path -> openLines(path))
    .filter(line -> !line.isBlank())
    .toList();
```

Ở đây `openLines(path)` phải trả **một stream còn mở**. Khi nội dung stream con được xử lý trong `flatMap`, framework chịu trách nhiệm đóng stream con. `files.stream()` từ `List<Path>` thường không nắm tài nguyên, nên không cần `try-with-resources` cho stream nguồn trong ví dụ này.

Sơ đồ quyền sở hữu:

```text
Caller
  │
  ├── sở hữu Stream<Path> nguồn khi Files.list / Files.walk tạo ra nó
  │       └── đóng bằng try-with-resources
  │
  └── flatMap
          ├── mapper trả Stream<String> cho file A (đang mở)
          │       └── flatMap quản lý close của stream A
          ├── mapper trả Stream<String> cho file B (đang mở)
          │       └── flatMap quản lý close của stream B
          └── ...
```

### 4.1. Không đóng stream con trước khi trả về

Phản ví dụ:

```java
// SAI: trả về một stream đã đóng.
paths.stream()
    .flatMap(path -> {
        try (Stream<String> lines = Files.lines(path)) {
            return lines;
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    })
    .toList();
```

Khi lambda trả `lines`, khối `try-with-resources` đã kết thúc và stream bị đóng trước khi `flatMap` sử dụng. Việc duyệt có thể ném `IllegalStateException` do stream đã đóng. **Không bọc stream sẽ được trả về cho `flatMap` trong một `try-with-resources` kết thúc ngay bên trong mapper.**

### 4.2. Không mở stream con rồi bỏ quên quyền đóng

Phản ví dụ khác:

```java
// Sai về quản lý tài nguyên: giữ lại các stream con trong một List.
List<Stream<String>> childStreams = paths.stream()
    .map(path -> openLines(path))
    .toList();

// Các stream con không được flatMap quản lý, cũng chưa được close.
```

`map` chỉ tạo `Stream<Stream<String>>`; nó không có hợp đồng **đóng từng stream con** giống `flatMap`. Nếu ứng dụng thật sự cần lưu stream con riêng rẽ, phải định nghĩa chủ sở hữu và đóng mọi stream đã mở, kể cả khi có ngoại lệ. Thường đơn giản hơn là dùng `flatMap` hoặc một vòng lặp `try-with-resources` đúng chỗ.

## 5. Ví dụ hoàn chỉnh: xử lý nhiều tệp bằng `flatMap`

Giả sử muốn duyệt mọi tệp thông thường trong một thư mục và đếm tổng số dòng không trắng. Có **hai tầng tài nguyên**:

1. `Files.list(directory)` tạo stream nguồn chứa tài nguyên duyệt thư mục.
2. `Files.lines(file)` tạo stream con chứa tài nguyên đọc tệp.

Mã hoàn chỉnh, có thể chạy trên **JDK 17+**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public final class FileLinePipelines {

    private FileLinePipelines() {}

    static Stream<String> openLinesUnchecked(Path path) {
        try {
            // Chuyển quyền quản lý stream còn mở cho caller.
            return Files.lines(path, StandardCharsets.UTF_8);
        } catch (IOException ex) {
            throw new UncheckedIOException("Không mở được: " + path, ex);
        }
    }

    public static long countFlatMap(Path directory) throws IOException {
        // Caller sở hữu stream thư mục.
        try (Stream<Path> paths = Files.list(directory)) {
            return paths
                .filter(Files::isRegularFile)
                .flatMap(FileLinePipelines::openLinesUnchecked)
                // flatMap quản lý close của từng stream Files.lines.
                .map(String::strip)
                .filter(line -> !line.isEmpty())
                .count();
        }
    }

    public static long countMapMulti(Path directory) throws IOException {
        try (Stream<Path> paths = Files.list(directory)) {
            return paths
                .filter(Files::isRegularFile)
                .<String>mapMulti((path, emit) -> {
                    // mapMulti KHÔNG đóng stream thay mapper.
                    try (Stream<String> lines = openLinesUnchecked(path)) {
                        lines.forEachOrdered(emit);
                    }
                })
                .map(String::strip)
                .filter(line -> !line.isEmpty())
                .count();
        }
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.out.println("Cách dùng: java FileLinePipelines <directory>");
            return;
        }

        Path directory = Path.of(args[0]);
        System.out.println("flatMap = " + countFlatMap(directory));
        System.out.println("mapMulti = " + countMapMulti(directory));
    }
}
```

Hai phương thức có cùng **nghĩa kết quả** với nguồn tệp không thay đổi và cùng chính sách đọc: mỗi dòng không trắng đóng góp một đơn vị vào bộ đếm. Nhưng **vòng đời và khả năng dừng sớm bên trong tệp** không giống nhau.

Trong ví dụ:

- `Files.list` có thể đưa các `Path` theo thứ tự không xác định. Vì chỉ đếm, điều này không ảnh hưởng kết quả.
- `Files.isRegularFile` chỉ kiểm tra tại thời điểm gọi; tệp vẫn có thể thay đổi, bị xóa hoặc mất quyền truy cập trước lúc mở.
- `openLinesUnchecked` dùng khi lambda không được khai báo `throws IOException`; nó không nuốt lỗi.
- Nếu đọc tệp xảy ra lỗi khi terminal operation duyệt, ngoại lệ có thể là `UncheckedIOException`; nguồn thư mục vẫn được đóng khi thoát `try`.
- Ví dụ xử lý **tệp trực tiếp trong thư mục**, không đệ quy. Muốn duyệt cây thư mục có thể dùng `Files.walk` nhưng phải đóng stream nguồn như `Files.list`.
- Ví dụ không áp đặt thứ tự tệp để tránh chi phí sắp xếp khi chỉ cần đếm.

## 6. Vì sao `mapMulti` có quy tắc quản lý khác?

`Stream.mapMulti` được bổ sung từ **JDK 16**, với chữ ký:

```java
<R> Stream<R> mapMulti(
    BiConsumer<? super T, ? super Consumer<R>> mapper
)
```

Không giống `flatMap`:

- `flatMap` cần mapper **trả một `Stream<R>`**.
- `mapMulti` cho mapper một `Consumer<R>` tên tùy chọn (ví dụ `emit`, `downstream`). Mapper gọi `emit.accept(value)` **không, một hoặc nhiều lần** để phát các giá trị.
- Mapper của `mapMulti` trả `void`, nên **không có đối tượng stream con được trả cho framework để nó đóng theo hợp đồng `flatMap`**.

Ví dụ trong bộ nhớ:

```java
import java.util.List;

List<List<String>> groups = List.of(
    List.of("Java", "Stream"),
    List.of(),
    List.of("API")
);

List<String> values = groups.stream()
    .<String>mapMulti((group, emit) -> group.forEach(emit))
    .toList();

System.out.println(values); // [Java, Stream, API]
```

Với `List` trong bộ nhớ, không có tài nguyên I/O đặc biệt. Nhưng khi mapper mở `Files.lines`, `BufferedReader` hoặc một tài nguyên riêng, **mapper phải tự sở hữu và đóng nó**.

### 6.1. Mẫu chuẩn cho `mapMulti` với nguồn I/O

```java
paths.stream()
    .<String>mapMulti((path, emit) -> {
        try (Stream<String> lines = openLinesUnchecked(path)) {
            lines.forEachOrdered(emit);
        }
    })
    .toList();
```

Ở đây `try-with-resources` **đúng** vì mapper phát các dòng **ngay trong lần gọi của nó**, không trả stream còn mở để xử lý về sau. Dù `forEachOrdered` kết thúc bình thường hay ném ngoại lệ, `lines` được đóng khi thoát khối `try`.

### 6.2. Không lưu lại `emit` để dùng ngoài mapper

`Consumer<R>` được truyền vào `mapMulti` chỉ dành cho việc phát kết quả **trong phạm vi thực thi mapper**. Không lưu consumer vào biến toàn cục, không dùng nó từ callback bất đồng bộ sau khi mapper đã trả về, không khởi chạy tác vụ nền dùng lại nó.

Sai về mô hình sử dụng:

```java
// Không làm: giữ Consumer do mapMulti đưa vào để phát giá trị về sau.
// savedConsumers.add(emit);
// asyncExecutor.submit(() -> emit.accept("late"));
```

Nếu dữ liệu đến từ một nguồn bất đồng bộ, cần mô hình quản lý bất đồng bộ và backpressure riêng. `mapMulti` không tự biến Java Stream API thành một reactive-stream API.

## 7. `flatMap` so với `mapMulti`: khi nào chọn cách nào?

| Tiêu chí | `flatMap` | `mapMulti` |
| --- | --- | --- |
| Mapper trả về | `Stream<R>` | `void`; phát qua `Consumer<R>` |
| Quan hệ một-nhiều | Thể hiện bằng stream con | Thể hiện bằng các lần `emit.accept` |
| Stream con được framework đóng? | Có, theo hợp đồng `flatMap` | Không có stream con được trả |
| Mở tệp ngay trong mapper | Trả `Files.lines` còn mở; để `flatMap` đóng | Dùng `try-with-resources` trong mapper |
| Dừng sớm của downstream | Có thể làm việc kết hợp với cơ chế duyệt stream con | Không có tín hiệu dừng sớm truyền trực tiếp vào vòng lặp phát của mapper |
| Biểu diễn nguồn I/O lớn | Tự nhiên nếu có API trả `Stream<R>` | Cần tự điều khiển vòng lặp và đóng tài nguyên |
| Phát ít giá trị/không muốn tạo stream con | Có thể tạo nhiều stream nhỏ | Có thể tiện hơn |
| Bảo đảm luôn nhanh hơn? | Không | Không |
| Phiên bản xuất hiện | Java 8 | JDK 16 |

**Lưu ý hiệu năng:** Javadoc nêu implementation mặc định của `mapMulti` có thể dùng một buffer và gọi `flatMap` bên trong. Vì thế, “`mapMulti` chắc chắn không cấp phát” hoặc “`mapMulti` luôn nhanh hơn” là kết luận không có cơ sở. Hãy đo trên JDK, nguồn dữ liệu và terminal operation thực tế.

## 8. `limit`, `findFirst` và dừng sớm: khác biệt quan trọng

Với pipeline có terminal operation **short-circuit** hoặc intermediate operation như `limit`, có thể không cần đọc toàn bộ dữ liệu. Nhưng cách phát giá trị ảnh hưởng khả năng tiết kiệm công việc.

### 8.1. `flatMap` có thể hỗ trợ dừng khi downstream đã đủ

```java
import java.util.List;

List<String> firstThree = paths.stream()
    .flatMap(FileLinePipelines::openLinesUnchecked)
    .limit(3)
    .toList();
```

Trong pipeline tuần tự, `limit(3)` không yêu cầu thu tất cả các dòng từ mọi tệp: sau khi đủ ba phần tử, pipeline có thể dừng. **Không nên viết test ép chính xác bao nhiêu lần mapper/reader được gọi**, vì chi tiết duyệt và tối ưu hóa có thể khác giữa các JDK hoặc chế độ song song.

Nếu `paths` thực chất đến từ `Files.list`, caller vẫn phải bảo đảm đóng **stream thư mục** bằng `try-with-resources`. Việc `limit` hoàn tất không đóng stream nguồn.

### 8.2. `mapMulti` có thể tiêu thụ hết nguồn con trước khi giới hạn phát huy tác dụng

Ví dụ:

```java
import java.util.List;

List<String> firstThree = paths.stream()
    .<String>mapMulti((path, emit) -> {
        try (Stream<String> lines =
                 FileLinePipelines.openLinesUnchecked(path)) {
            lines.forEachOrdered(emit);
        }
    })
    .limit(3)
    .toList();
```

`lines.forEachOrdered(emit)` có nghĩa là mapper chủ động duyệt các dòng của tệp đang mở. `mapMulti` không trao cho mapper một API tiêu chuẩn để hỏi “downstream đã nhận đủ ba phần tử chưa?”. Vì vậy, **không kỳ vọng `limit(3)` sẽ ngăn vòng lặp `forEachOrdered` đọc tiếp bên trong tệp đang xử lý**. Nếu một tệp rất lớn, đó có thể là lãng phí đáng kể.

Mọi thứ vẫn được đóng bằng `try-with-resources`, nhưng **đóng đúng không đồng nghĩa đọc tiết kiệm**.

### 8.3. Thứ tự nguồn và kết quả “đầu tiên”

`Files.list(directory)` không bảo đảm thứ tự đường dẫn. Do đó, “ba dòng đầu tiên của thư mục” là yêu cầu mơ hồ nếu không nêu thứ tự tệp.

Nếu cần thứ tự **tên tệp tăng dần**, có thể thêm:

```java
try (Stream<Path> paths = Files.list(directory)) {
    List<String> firstThree = paths
        .filter(Files::isRegularFile)
        .sorted(java.util.Comparator.comparing(
            path -> path.getFileName().toString()
        ))
        .flatMap(FileLinePipelines::openLinesUnchecked)
        .limit(3)
        .toList();
}
```

`sorted` phải có khả năng sắp xếp các đường dẫn, vì vậy có thể cần giữ toàn bộ danh sách đường dẫn trước khi phát phần tử. Cân nhắc chi phí nếu thư mục rất lớn. Cũng cần phân biệt thứ tự tên tệp, thứ tự thời gian và thứ tự dòng bên trong mỗi tệp.

### 8.4. Nguồn vô hạn

Nếu mapper của `mapMulti` chạy một vòng lặp **không bao giờ kết thúc** để tiếp tục gọi `emit.accept`, một `limit` phía sau **không bảo đảm cứu được** pipeline khỏi việc mắc kẹt trong mapper. Trong mô hình thông thường, `flatMap` với một stream con có khả năng short-circuit thích hợp hơn cho nguồn rất dài hoặc tiềm năng vô hạn, nhưng vẫn phải tuân hợp đồng tài nguyên của nguồn và bảo đảm terminal operation có đường kết thúc.

## 9. Ngoại lệ: mở, duyệt và đóng là ba thời điểm khác nhau

Các API I/O có thể phát sinh lỗi ở **nhiều giai đoạn**:

1. **Mở nguồn:** `Files.list` hoặc `Files.lines` có thể ném checked `IOException`.
2. **Duyệt nguồn:** một stream đã mở có thể phát sinh lỗi trong quá trình đọc; những lỗi I/O khi duyệt có thể xuất hiện dưới dạng `UncheckedIOException`.
3. **Đóng nguồn:** thao tác giải phóng tài nguyên có thể gây lỗi; `try-with-resources` vẫn có cơ chế xử lý ngoại lệ và suppressed exceptions.

Chữ ký `Function`/`BiConsumer` trong Stream API **không khai báo `throws IOException`**, nên đoạn mã này không biên dịch:

```java
// Không biên dịch: Files.lines có checked IOException.
// paths.stream().flatMap(path -> Files.lines(path)).count();
```

Một phương thức adapter có thể chuyển lỗi mở sang `UncheckedIOException`:

```java
static Stream<String> openLinesUnchecked(Path path) {
    try {
        return Files.lines(path, StandardCharsets.UTF_8);
    } catch (IOException ex) {
        throw new UncheckedIOException("Không mở được: " + path, ex);
    }
}
```

**Không nuốt lỗi I/O bằng `Stream.empty()`** nếu hợp đồng nghiệp vụ đòi đủ dữ liệu. Làm như vậy có thể khiến báo cáo được ghi nhận thành công nhưng thiếu toàn bộ một tệp.

Phân biệt hai thiết kế:

- **Fail fast:** tệp không đọc được thì phép tổng hợp thất bại với ngoại lệ có nguyên nhân.
- **Best effort:** ứng dụng chấp nhận bỏ qua tệp lỗi nhưng phải **ghi nhận đường dẫn, lý do và số tệp thất bại** trong một kiểu kết quả rõ ràng. Việc quyết định bỏ qua lỗi thuộc tầng nghiệp vụ, không phải mặc định của `flatMap` hay `mapMulti`.

### 9.1. `try-with-resources` bảo vệ đường đi lỗi

```java
try (Stream<Path> files = Files.list(directory)) {
    return files
        .flatMap(FileLinePipelines::openLinesUnchecked)
        .filter(line -> !line.isBlank())
        .count();
}
```

Nếu việc đọc một tệp ném ngoại lệ, khối `try` vẫn đóng stream thư mục. Các stream con được `flatMap` quản lý theo hợp đồng của nó; tránh gắn thêm một cơ chế đóng thủ công bên ngoài cho đúng cùng stream con theo cách gây nhập nhằng ownership.

### 9.2. Nếu mở nhiều tài nguyên trong một mapper

Giả sử mapper cần mở **cả reader và một tài nguyên khác**, rồi mới tạo stream. Nếu mở tài nguyên đầu thành công nhưng mở tài nguyên thứ hai thất bại, mapper phải đóng tài nguyên đã mở. Đừng nghĩ rằng `flatMap` có thể dọn một tài nguyên chưa từng được gói vào stream được trả về.

Mẫu xử lý phải thiết kế theo owner:

```java
// Ý tưởng: trong mapMulti, đóng mọi tài nguyên ngay trong lambda.
.<String>mapMulti((path, emit) -> {
    try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        reader.lines().forEachOrdered(emit);
    } catch (IOException ex) {
        throw new UncheckedIOException("Không đọc được: " + path, ex);
    }
})
```

Đoạn trên là **phần nối tiếp của một pipeline `Stream<Path>`**, không phải một chương trình Java độc lập. Nó đóng `BufferedReader` thay vì chỉ đóng `reader.lines()`; nếu lỗi đọc xuất hiện muộn dưới dạng `UncheckedIOException`, khối `try` vẫn đóng reader trước khi ngoại lệ truyền ra ngoài.

## 10. Kiểm thử vòng đời stream con bằng `onClose`

Kiểm thử `toList` trả đúng dữ liệu là chưa đủ với bài toán I/O. Một pipeline có thể cho đúng giá trị nhưng **rò rỉ descriptor** hoặc để nguồn thư mục chưa đóng.

Để kiểm tra mà không cần tạo tệp thật, dùng `onClose` trên stream giả lập và bộ đếm chỉ phục vụ test.

### 10.1. `flatMap` đóng từng stream con

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

class StreamResourceLifecycleTest {

    @Test
    void flatMapClosesMappedStreams() {
        AtomicInteger childCloseCount = new AtomicInteger();

        List<String> result = List.of(1, 2, 3).stream()
            .flatMap(n -> Stream.of("N-" + n)
                .onClose(childCloseCount::incrementAndGet))
            .toList();

        assertEquals(List.of("N-1", "N-2", "N-3"), result);
        assertEquals(3, childCloseCount.get());
    }

    @Test
    void terminalOperationDoesNotCloseOuterSource() {
        AtomicInteger sourceClosed = new AtomicInteger();
        Stream<Integer> source = Stream.of(1, 2, 3)
            .onClose(sourceClosed::incrementAndGet);

        assertEquals(3L, source.count());
        assertEquals(0, sourceClosed.get());

        source.close();
        assertEquals(1, sourceClosed.get());
    }

    @Test
    void tryWithResourcesClosesOuterEvenAfterLimit() {
        AtomicInteger sourceClosed = new AtomicInteger();

        try (Stream<Integer> source = Stream.of(1, 2, 3)
                 .onClose(sourceClosed::incrementAndGet)) {
            assertEquals(
                List.of(1),
                source.limit(1).toList()
            );
        }

        assertEquals(1, sourceClosed.get());
    }

    @Test
    void mapMultiClosesResourcesOpenedByMapper() {
        AtomicInteger childCloseCount = new AtomicInteger();

        List<String> result = List.of(
            List.of("A", "B"),
            List.of("C")
        ).stream()
            .<String>mapMulti((items, emit) -> {
                try (Stream<String> child = items.stream()
                        .onClose(childCloseCount::incrementAndGet)) {
                    child.forEachOrdered(emit);
                }
            })
            .toList();

        assertEquals(List.of("A", "B", "C"), result);
        assertEquals(2, childCloseCount.get());
    }
}
```

Đây là **bài kiểm thử vòng đời**, không phải benchmark. `AtomicInteger` quan sát close handler sau khi pipeline hoàn tất, không tham gia quyết định đầu ra nghiệp vụ. Mọi ví dụ kiểm thử ở đây dùng nguồn tuần tự và hữu hạn để kỳ vọng có thể xác định.

### 10.2. Kiểm thử khi mapper ném ngoại lệ

Với `mapMulti`, hãy kiểm chứng tài nguyên được đóng kể cả khi phát dữ liệu bị lỗi:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

class MapMultiFailureTest {

    @Test
    void closesChildIfMappingThrows() {
        AtomicInteger closed = new AtomicInteger();

        assertThrows(IllegalStateException.class, () ->
            List.of(1).stream()
                .<String>mapMulti((n, emit) -> {
                    try (Stream<String> child = Stream.of("A")
                            .onClose(closed::incrementAndGet)) {
                        child.forEachOrdered(emit);
                        throw new IllegalStateException("Lỗi kiểm thử");
                    }
                })
                .toList()
        );

        assertEquals(1, closed.get());
    }
}
```

Nếu dùng file thật, thêm test cho tệp rỗng, tệp không tồn tại, file bị khóa/quyền truy cập không đủ (tùy hệ điều hành) và lỗi trong quá trình đọc. **Không để kiểm thử phụ thuộc thứ tự `Files.list`**, vì thứ tự duyệt thư mục không được cam kết.

## 11. Các lỗi thiết kế và phản ví dụ cần tránh

### 11.1. Chỉ đóng một nguồn, quên nguồn còn lại

```java
// Phản ví dụ: Files.list chưa được đặt trong try-with-resources.
// Files.list(directory)
//     .flatMap(FileLinePipelines::openLinesUnchecked)
//     .count();
```

`flatMap` chịu trách nhiệm đóng **stream con** nhưng không thay việc đóng **stream nguồn `Files.list`**. Đặt `Files.list` trong `try-with-resources` của caller.

### 11.2. Đóng stream con quá sớm khi dùng `flatMap`

```java
// Trả stream từ bên trong try: stream bị đóng trước khi dùng.
// .flatMap(path -> {
//     try (Stream<String> lines = openLinesUnchecked(path)) {
//         return lines;
//     }
// })
```

Khi muốn để framework đóng con, trả stream **còn mở**. Khi muốn tự đóng tài nguyên **trong mapper**, dùng mô hình phát dữ liệu đồng bộ của `mapMulti` hoặc vòng lặp xử lý trực tiếp.

### 11.3. Dùng `mapMulti` nhưng không đóng stream mở bên trong

```java
// Phản ví dụ: tạo stream I/O bên trong mapper mà không close.
// .<String>mapMulti((path, emit) -> {
//     Stream<String> lines = openLinesUnchecked(path);
//     lines.forEachOrdered(emit);
// })
```

Nếu `forEachOrdered` kết thúc hay ném ngoại lệ, đoạn trên vẫn không tự đóng `lines`. Thêm `try-with-resources` bao quanh mọi lần sử dụng tài nguyên.

### 11.4. Dùng `mapMulti` và kỳ vọng downstream `limit` ngăn đọc toàn bộ tệp

Mapper kiểu `lines.forEachOrdered(emit)` không có tín hiệu dừng tiêu chuẩn từ `limit` xuống vòng lặp này. Nếu yêu cầu quan trọng là lấy vài dòng đầu và **không đọc tiếp**, `flatMap` thường rõ ràng hơn cho nguồn đã biểu diễn bằng `Stream<String>`.

### 11.5. Bỏ qua mọi `IOException` thành stream rỗng

```java
// Phản ví dụ nguy hiểm về tính đúng đắn số liệu:
// .flatMap(path -> {
//     try { return Files.lines(path); }
//     catch (IOException ex) { return Stream.empty(); }
// })
```

Một tệp không đọc được là lỗi dữ liệu nguồn, không tự động tương đương một tệp rỗng. Nếu nghiệp vụ chấp nhận best effort, báo cáo phải thể hiện số tệp bỏ qua và nguyên nhân, không được âm thầm đánh dấu dữ liệu đầy đủ.

### 11.6. Mở file trong `peek` hoặc mapper chỉ để gây side effect

`peek` phục vụ quan sát hoặc gỡ lỗi có điều kiện, không phải cơ chế I/O bắt buộc. Stream API có thể tối ưu một số pipeline, kết thúc sớm hoặc thực thi song song; đừng dựa vào số lần gọi `peek`/mapper để đảm bảo một tệp được xử lý hoặc ghi log đúng một lần. Logic nghiệp vụ có side effect cần được thiết kế thành tác vụ có owner, điều kiện thành công và chính sách lỗi rõ ràng.

## 12. Xử lý song song: tài nguyên có thể mở đồng thời

`flatMap` hoặc `mapMulti` có thể xuất hiện sau `parallel()`:

```java
try (Stream<Path> paths = Files.list(directory)) {
    long result = paths.parallel()
        .filter(Files::isRegularFile)
        .flatMap(FileLinePipelines::openLinesUnchecked)
        .filter(line -> !line.isBlank())
        .count();
}
```

Về mặt API, pipeline có thể hợp lệ; nhưng xử lý I/O song song đặt ra những vấn đề thực tế:

- Nhiều mapper có thể **đang mở các stream tệp khác nhau đồng thời**; số lượng descriptor và tài nguyên I/O có thể tăng.
- Tệp lớn, tệp nhỏ, đĩa cục bộ và network filesystem có đặc tính rất khác; parallel không mặc nhiên tăng tốc.
- Các lời gọi đọc tệp là blocking I/O; cần cân nhắc cấu hình thread pool và hệ thống tải thực tế.
- `Files.list` không bảo đảm thứ tự đường dẫn, còn `forEach` trên parallel stream không bảo đảm thứ tự thực thi.
- Mapper không được can thiệp collection nguồn hoặc cập nhật trạng thái mutable bên ngoài không được quản lý. Đếm bằng `count`/collector thay vì sửa một `ArrayList` dùng chung từ `forEach`.
- Lỗi ở một tác vụ có thể làm pipeline thất bại và cần đóng các tài nguyên đã mở theo đúng ownership; không dựa vào thứ tự ngoại lệ để suy ra file nào được xử lý cuối cùng.

Nếu phải giới hạn số file mở đồng thời hoặc có yêu cầu thứ tự xử lý nghiêm ngặt, một pipeline tuần tự có thể phù hợp hơn. Với bài toán I/O phức tạp, có thể cần cơ chế điều phối đồng thời chuyên dụng thay vì chỉ thêm `parallel()`.

## 13. Hiệu năng và bộ nhớ: chọn công cụ theo dạng nguồn

### 13.1. Tạo stream con hay phát trực tiếp?

Với dữ liệu thuần trong bộ nhớ, `mapMulti` có thể tiện khi một phần tử tạo rất ít kết quả:

```java
import java.util.List;

record Pair(String first, String second) {}

List<String> values = List.of(
    new Pair("A", "B"),
    new Pair("C", "D")
).stream()
    .<String>mapMulti((pair, emit) -> {
        emit.accept(pair.first());
        emit.accept(pair.second());
    })
    .toList();

System.out.println(values); // [A, B, C, D]
```

Việc này không tạo stream con ở cấp biểu thức của mapper. Nhưng implementation mặc định của `mapMulti` có thể đệm kết quả; đo hiệu năng trước khi khẳng định tối ưu allocation.

### 13.2. Với file lớn, ưu tiên khả năng tiêu thụ lười

`Files.lines` tạo stream đọc dòng lười. Nếu chỉ cần một phần nhỏ dữ liệu, kết hợp `flatMap` với `findFirst`, `limit` hoặc `takeWhile` có thể tránh việc phải duyệt toàn bộ tệp. Với `mapMulti` tự gọi `lines.forEachOrdered(emit)`, mapper có thể duyệt trọn file để phát dữ liệu, kể cả khi downstream không cần nhiều như vậy.

Ngược lại, nếu nghiệp vụ **bắt buộc** xử lý toàn bộ dòng của mọi file và cần phát nhiều loại đối tượng từ mỗi dòng, `mapMulti` có thể diễn đạt rõ logic 0–n phần tử, miễn là tài nguyên được đóng ở đúng phạm vi.

### 13.3. Giữ tất cả dòng trong `List` có thể rất tốn RAM

`toList()` sẽ materialize kết quả. Nếu chỉ cần số lượng hoặc tổng hợp, dùng `count`, `mapToLong`/`sum`, `reduce` hay collector thống kê thay vì giữ toàn bộ chuỗi:

```java
try (Stream<Path> paths = Files.list(directory)) {
    long totalCharacters = paths
        .filter(Files::isRegularFile)
        .flatMap(FileLinePipelines::openLinesUnchecked)
        .mapToLong(String::length)
        .sum();
}
```

Khi dùng `Files.lines`, giảm bộ nhớ kết quả không thay thế trách nhiệm đóng file. Tối ưu về **dung lượng trạng thái**, **số file đang mở** và **lượng I/O đã đọc** là ba vấn đề khác nhau.

## 14. Quy trình kiểm tra quyền sở hữu tài nguyên

Trước khi đưa một pipeline lồng stream vào sản xuất, trả lời lần lượt:

1. **Nguồn đến từ đâu?** `List`, `Stream.of`, `Files.list`, `Files.walk`, `BufferedReader` hay API riêng?
2. **Có tài nguyên phải đóng không?** Javadoc của API tạo nguồn nói gì?
3. **Ai là owner?** Caller, `flatMap` với stream con, hay mapper `mapMulti`?
4. **Khi nào terminal operation dừng?** Duyệt hết hay có `limit`/`findFirst`?
5. **Dừng sớm có đóng được các tài nguyên đã mở không?** Có `try-with-resources` ở nguồn và phạm vi mapper phù hợp không?
6. **Lỗi mở, đọc và đóng được truyền đi thế nào?** Có đang nuốt lỗi thành dữ liệu rỗng?
7. **Nguồn có thứ tự không?** Nếu lấy “dòng đầu tiên”, thứ tự file đã được định nghĩa chưa?
8. **Pipeline chạy song song?** Có giới hạn số file mở, yêu cầu thứ tự và đo hiệu năng không?
9. **Kết quả có cần giữ toàn bộ?** Có thể dùng terminal operation tổng hợp thay vì `toList`?
10. **Đã có kiểm thử vòng đời?** Không chỉ test giá trị; cần test close và trường hợp ném ngoại lệ.

## 15. Bài tập áp dụng

### Bài 1 — Đóng đúng hai tầng tài nguyên

Viết phương thức nhận `Path directory`, dùng `Files.list` và `flatMap` để đọc tất cả dòng văn bản ở các file thông thường rồi đếm số dòng chứa chuỗi `"ERROR"`. Xác định chính xác:

- Stream nào do caller đóng bằng `try-with-resources`?
- Stream nào được `flatMap` đóng?
- Lỗi `Files.lines` được chuyển sang `UncheckedIOException` thế nào?

### Bài 2 — Chuyển từ `flatMap` sang `mapMulti`

Viết lại Bài 1 bằng `mapMulti`. Phải đặt `Files.lines` trong `try-with-resources` ngay trong mapper và chỉ phát từng dòng trong phạm vi ấy. Giải thích vì sao không được tạo stream rồi bỏ quên hoặc lưu `emit` để gọi bất đồng bộ.

### Bài 3 — Kiểm thử `close`

Dùng `Stream.of("A")` kèm `onClose` để tạo hai stream con. Chạy `flatMap(...).toList()` rồi xác nhận cả hai close handlers đã chạy. Làm thí nghiệm riêng cho stream nguồn kèm `onClose`, so sánh terminal `count()` với việc đóng trong `try-with-resources`.

### Bài 4 — Short-circuit

Cho một tệp có một triệu dòng nhưng chỉ cần ba dòng đầu. So sánh:

```java
paths.stream().flatMap(FileLinePipelines::openLinesUnchecked)
    .limit(3).toList();
```

và phiên bản `mapMulti` mở `Files.lines`, gọi `lines.forEachOrdered(emit)` rồi đặt `limit(3)` phía sau. Nêu hệ quả về **lượng I/O** và **vòng đời tài nguyên**. Không kết luận số lần đọc chính xác mà không đo hoặc kiểm thử cách triển khai.

### Bài 5 — Lỗi dữ liệu

Giả sử ba file tồn tại nhưng file thứ hai không đọc được. Chọn giữa hợp đồng:

- Dừng ngay và báo lỗi có đường dẫn.
- Tiếp tục đọc file khác, nhưng trả **kết quả và danh sách file thất bại**.

Không được dùng `Stream.empty()` để âm thầm báo thành công. Mô tả cách tránh mở tài nguyên mới khi không cần thiết và cách đóng nguồn sau khi thất bại.

### Bài 6 — Reader ownership

Viết một pipeline dùng `BufferedReader.lines()` để đếm dòng không trắng. Chứng minh bằng `try-with-resources` rằng **reader** được đóng sau khi terminal operation hoàn tất hoặc ném lỗi. So sánh với `Files.lines(path)` về đối tượng phải đóng.

### Bài 7 — Hiệu năng và song song

Một thư mục có 10.000 file rất nhỏ trên network filesystem. Lập kế hoạch đo benchmark `stream()` và `parallel()` cho cùng phép đếm dòng; nêu cách theo dõi **số file mở đồng thời**, CPU, I/O, bộ nhớ và thời gian. Giải thích vì sao chỉ thay đổi sang `parallel()` chưa đủ chứng minh giải pháp đúng hoặc nhanh.

## 16. Bảng quyết định

| Tình huống | Hướng xử lý phù hợp |
| --- | --- |
| Duyệt `List<List<T>>` trong bộ nhớ | `flatMap(List::stream)` hoặc `mapMulti` không tài nguyên I/O |
| Mapper có sẵn một `Stream<R>` nắm tài nguyên | Trả stream còn mở cho `flatMap` để nó đóng theo hợp đồng |
| Mapper mở tài nguyên rồi **phát đồng bộ** các giá trị | `mapMulti` + `try-with-resources` bên trong mapper |
| Nguồn là `Files.list` hoặc `Files.walk` | Caller đóng stream nguồn bằng `try-with-resources` |
| Nguồn là `BufferedReader.lines()` | Đóng `BufferedReader` owner |
| Terminal operation là `count` hoặc `toList` | **Không** tự đóng stream nguồn; vẫn cần quản lý close |
| Có `limit`/`findFirst` và file rất lớn | Cân nhắc `flatMap` để tận dụng short-circuit của stream con |
| `mapMulti` đang gọi `lines.forEachOrdered(emit)` | Không giả định downstream giới hạn số dòng được đọc trong mapper |
| Mở file ném checked `IOException` trong lambda | Chuyển có nguyên nhân sang `UncheckedIOException` hoặc xử lý bằng API nghiệp vụ tường minh |
| Có thể lỗi khi duyệt hoặc đóng | Dùng owner/try-with-resources; không nuốt lỗi |
| Nguồn không cam kết thứ tự | Định nghĩa thứ tự trước khi nói “dòng đầu tiên” |
| Xử lý file song song | Kiểm soát số tài nguyên đồng thời, thread-safety và đo hiệu năng |
| Chỉ cần count/sum | Dùng terminal operation thống kê thay vì `toList` toàn bộ dữ liệu |

`flatMap` và `mapMulti` đều diễn đạt biến đổi **một phần tử đầu vào thành không, một hoặc nhiều phần tử đầu ra**, nhưng không có cùng **hợp đồng sở hữu tài nguyên**. Với `flatMap`, stream con được trả về còn mở để framework quản lý việc đóng; với `mapMulti`, tài nguyên mở bên trong mapper phải được đóng tại phạm vi mapper, thường bằng `try-with-resources`. Trong cả hai trường hợp, stream nguồn có tài nguyên như `Files.list` vẫn thuộc trách nhiệm của caller. Chú ý ba việc độc lập — **đúng kết quả, đóng đúng tài nguyên và chỉ đọc lượng dữ liệu cần thiết** — sẽ giúp các pipeline I/O trong Java Stream API an toàn và dễ tối ưu hơn.
