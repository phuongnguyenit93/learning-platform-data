# Tạo Stream từ tệp, dòng văn bản và các API JDK khác

## 1. Mục tiêu

`Stream` trong Java không chỉ xuất phát từ `List`, `Set` hay mảng. JDK còn cung cấp các nguồn phù hợp với những kiểu dữ liệu khác nhau: nội dung tệp, các dòng văn bản, cây thư mục, token được tách từ văn bản, kết quả `Optional`, dãy số được sinh ra và các nguồn được cung cấp qua `Spliterator`.

Bài học này giúp bạn:

1. Tạo Stream từ tệp và dòng văn bản bằng `Files.lines`, `BufferedReader.lines`, `String.lines`.
2. Duyệt file/thư mục qua `Files.list`, `Files.walk`, `Files.find`, hiểu rõ phạm vi và thứ tự.
3. Dùng `Scanner.tokens`, `Pattern.splitAsStream` và các API JDK khác để tạo Stream khi dữ liệu không nằm trong collection.
4. Phân biệt Stream có tài nguyên I/O cần đóng với Stream thuần bộ nhớ.
5. Xử lý đúng tính lười, lỗi I/O, vòng đời dùng một lần, bộ nhớ, thứ tự và hạn chế của dữ liệu vô hạn.
6. Thực hành một chương trình Java 17 hoàn chỉnh và đối chiếu kết quả xác định.

Điểm cốt lõi: Stream là **một pipeline xử lý phần tử từ nguồn**, không phải nơi chứa vĩnh viễn các phần tử. Nguồn có thể là một tập hợp có sẵn, một đối tượng đọc tệp hoặc một thuật toán tạo phần tử theo yêu cầu.

## 2. Các họ nguồn Stream trong JDK

| Nguồn | Cách tạo | Kiểu Stream | Cần đóng? | Ghi chú |
| --- | --- | --- | --- | --- |
| Dòng trong tệp | `Files.lines(path, charset)` | `Stream<String>` | **Có** | Đọc khi tiêu thụ; Stream giữ tài nguyên tệp |
| Dòng từ reader | `reader.lines()` với `BufferedReader` | `Stream<String>` | **Đóng reader** | Reader là tài nguyên do người gọi quản lý |
| Chuỗi có xuống dòng | `text.lines()` | `Stream<String>` | Không | Java 11+, xử lý văn bản trong bộ nhớ |
| Mục trực tiếp của thư mục | `Files.list(directory)` | `Stream<Path>` | **Có** | Không duyệt thư mục con |
| Cây thư mục | `Files.walk(directory)` | `Stream<Path>` | **Có** | Duyệt đệ quy, gồm cả đường dẫn gốc |
| Tìm trong cây | `Files.find(directory, maxDepth, matcher)` | `Stream<Path>` | **Có** | Matcher nhận `Path` và thuộc tính tệp |
| Token của `Scanner` | `scanner.tokens()` | `Stream<String>` | **Đóng scanner** | Phụ thuộc delimiter và nguồn Scanner |
| Tách bằng regex | `pattern.splitAsStream(text)` | `Stream<String>` | Không | Regex phân chia chuỗi trong bộ nhớ |
| Các dòng trong `Optional` | `optional.stream()` | `Stream<T>` | Không | `0` hoặc `1` phần tử |
| Giá trị có thể null | `Stream.ofNullable(value)` | `Stream<T>` | Không | Java 9+, `0` hoặc `1` phần tử |
| Dãy số nguyên | `IntStream.range(a, b)` | `IntStream` | Không | Cận trên không bao gồm |
| Dãy sinh theo thuật toán | `Stream.iterate(...)`, `Stream.generate(...)` | `Stream<T>` | Thường không | Có thể vô hạn, cần giới hạn hoặc kết thúc |
| Số giả ngẫu nhiên | `random.ints(...)` | `IntStream` | Không | Có overload hữu hạn hoặc vô hạn |
| Nguồn tự định nghĩa | `StreamSupport.stream(spliterator, false)` | `Stream<T>` | Tùy nguồn | Cần quản lý vòng đời tài nguyên riêng |

Cột “cần đóng” mô tả trách nhiệm của ứng dụng đối với **nguồn hoặc Stream sở hữu tài nguyên bên ngoài**. Không phải mọi Stream đều phải gọi `close()`. Stream được tạo từ `List`, `String.lines()` hoặc `IntStream.range` thông thường không có file handle cần giải phóng.

## 3. `Files.lines`: đọc tệp theo dòng

### Cú pháp và hành vi

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path path = Path.of("data.txt");

try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    long nonEmpty = lines
            .map(String::strip)
            .filter(s -> !s.isEmpty())
            .count();
    System.out.println(nonEmpty);
}
```

Đoạn này minh họa, cần có tệp `data.txt` để chạy. API có overload `Files.lines(path)` mặc định dùng UTF-8; truyền `StandardCharsets.UTF_8` giúp hợp đồng encoding hiển thị rõ trong code.

Mỗi phần tử là một **dòng văn bản không bao gồm ký tự kết thúc dòng**. Stream chỉ được tiêu thụ khi terminal operation như `count`, `toList`, `forEach`, `collect` thực thi. Không nên coi `Files.lines` là thao tác đọc toàn bộ tệp vào một `List` ngay tại lúc gọi. JDK có thể giữ bộ đệm và tài nguyên trong quá trình duyệt.

**Quan trọng:** Stream do `Files.lines` trả về có tài nguyên I/O cần đóng. Dùng `try-with-resources`, kể cả khi pipeline ném lỗi hoặc dừng sớm:

```java
try (Stream<String> lines = Files.lines(path)) {
    String first = lines.findFirst().orElse("<empty>");
    System.out.println(first);
}
// close() được gọi khi ra khỏi khối try.
```

`findFirst()` không tự bảo đảm đóng Stream; ngữ nghĩa đóng do `try-with-resources` đảm nhiệm. Đừng trả Stream chưa tiêu thụ ra ngoài phương thức sau khi nó đã bị đóng trong `try`; lời gọi terminal ở nơi nhận sẽ không còn quyền sử dụng nguồn. Nếu API của bạn trả Stream có tài nguyên, phải công bố trách nhiệm đóng cho bên gọi hoặc thiết kế API callback để tài nguyên sống đủ lâu.

### Ngoại lệ khi đọc

Việc mở tệp có thể ném `IOException`. Lỗi I/O trong lúc duyệt lười có thể xuất hiện dưới dạng `UncheckedIOException` từ terminal operation, thay vì xảy ra ngay tại lúc tạo Stream. Những lỗi này cần được báo lên hoặc xử lý theo chính sách nghiệp vụ; không dùng `catch` rỗng để Stream “vẫn chạy”.

Đối với tập tin rất lớn, xử lý theo luồng có thể giảm nhu cầu giữ toàn bộ dòng trong RAM. Nhưng nếu terminal kết thúc bằng `.toList()`, **kết quả vẫn được thu thập trong bộ nhớ**. `sorted()` và một số thao tác stateful cũng có thể giữ dữ liệu trung gian lớn. Cân nhắc `forEach`, tổng hợp `count`/`reduce`, hoặc xử lý từng lô khi hợp đồng cho phép.

## 4. `BufferedReader.lines`: khi bạn đã có Reader

Nếu code đã sở hữu `BufferedReader`, gọi `lines()` để biến phần văn bản còn lại thành Stream:

```java
try (java.io.BufferedReader reader =
             java.nio.file.Files.newBufferedReader(
                     path, java.nio.charset.StandardCharsets.UTF_8)) {
    long count = reader.lines()
            .filter(line -> !line.isBlank())
            .count();
    System.out.println(count);
}
```

`BufferedReader.lines()` đọc từ **vị trí hiện tại** của reader; nếu trước đó đã gọi `readLine()`, Stream không đọc lại phần đã tiêu thụ. Trong lúc Stream từ `lines()` đang được sử dụng, không nên đọc trực tiếp từ cùng reader bằng các cách khác. Lỗi I/O phát sinh khi duyệt có thể được bọc thành `UncheckedIOException`.

Khác với `Files.lines`, trách nhiệm quản lý vòng đời rõ ràng nhất là đóng chính `BufferedReader`. Dùng `try (BufferedReader reader = ...)`; không cần tạo hai vòng đời độc lập hay tiếp tục đọc reader sau khi đã đóng. Nếu reader bọc socket hoặc một nguồn đặc biệt, hành vi đóng thường lan đến tài nguyên bên dưới và phải được thiết kế phù hợp.

`Files.lines` là cách trực tiếp khi chỉ cần một Stream các dòng từ tệp. `BufferedReader.lines` tiện khi reader đã tồn tại hoặc khi cần phối hợp với những phương thức đọc từ `BufferedReader`, miễn là không trộn thao tác trong lúc Stream đang duyệt.

## 5. `String.lines`: các dòng của một chuỗi trong bộ nhớ

Từ Java 11, `String.lines()` tạo `Stream<String>` của các dòng phân cách bởi `\n`, `\r` hoặc `\r\n`:

```java
String text = "first\r\nsecond\n";

List<String> lines = text.lines().toList();
System.out.println(lines); // [first, second]
```

`String.lines()` không đưa dấu kết thúc dòng vào từng phần tử. Một dấu xuống dòng ở cuối chuỗi không tự sinh một dòng trống dư ở cuối; chuỗi rỗng tạo Stream không có phần tử. Khác với `Files.lines`, dữ liệu đã nằm trong bộ nhớ nên Stream không cần đóng file handle.

Ứng dụng thực tế: phân tích dữ liệu nhận từ API, response hoặc chuỗi đọc sẵn khi bạn muốn xử lý theo từng dòng. Nếu văn bản quá lớn, việc đã chứa toàn bộ nội dung trong `String` có thể tốn RAM; `String.lines` không biến nguồn đó thành phép đọc file trực tiếp.

## 6. `Files.list`, `Files.walk` và `Files.find`: nguồn từ hệ thống tệp

### `Files.list`: chỉ một cấp

```java
try (Stream<Path> entries = Files.list(directory)) {
    List<String> names = entries
            .map(path -> path.getFileName().toString())
            .sorted()
            .toList();
    System.out.println(names);
}
```

`Files.list(directory)` tạo Stream gồm các mục trực tiếp trong thư mục: tệp và thư mục con. Nó **không tự đệ quy**. Không có cam kết chung về thứ tự liệt kê của hệ thống tệp; nếu muốn kết quả xác định, hãy `.sorted()` theo tiêu chí của bạn.

### `Files.walk`: duyệt cây thư mục

```java
try (Stream<Path> paths = Files.walk(directory)) {
    List<Path> regularFiles = paths
            .filter(Files::isRegularFile)
            .toList();
}
```

Theo mặc định, `Files.walk` bắt đầu từ chính đường dẫn gốc và duyệt các mục con theo độ sâu, không đi xuyên qua symbolic link nếu không chỉ định `FileVisitOption.FOLLOW_LINKS`. Bạn có thể giới hạn độ sâu:

```java
try (Stream<Path> paths = Files.walk(directory, 1)) {
    // Đường dẫn gốc và các mục trực tiếp (nếu truy cập được).
    long pathsAtDepthZeroOrOne = paths.count();
}
```

`Files.walk(directory, 1)` không tương đương hoàn toàn `Files.list(directory)` vì `walk` **bao gồm cả đường dẫn gốc** và cách xử lý lỗi/cây thư mục khác nhau.

### `Files.find`: lọc dựa trên `Path` và thuộc tính

```java
try (Stream<Path> matching = Files.find(
        directory,
        10,
        (path, attrs) -> attrs.isRegularFile()
                && path.getFileName().toString().endsWith(".txt"))) {
    long txtCount = matching.count();
    System.out.println(txtCount);
}
```

`Files.find` dùng `BiPredicate<Path, BasicFileAttributes>` để nhận quyết định dựa trên đường dẫn và thuộc tính tệp. Khi cần thuộc tính như `isRegularFile`, API này hữu ích vì có thể dùng thuộc tính đã lấy cho quá trình duyệt. `Files.walk(...).filter(...)` thường dễ đọc hơn khi không cần các thuộc tính ấy.

Cả `Files.list`, `Files.walk` và `Files.find` đều tạo Stream có tài nguyên mở liên quan đến việc liệt kê thư mục, vì thế **phải đóng Stream bằng `try-with-resources`**. Lỗi mở nguồn thường là checked `IOException`, còn lỗi I/O khi duyệt lười có thể xuất hiện như `UncheckedIOException`.

Với cây rất lớn hoặc đường dẫn do người dùng cung cấp, cần đặt giới hạn về độ sâu, số lượng phần tử, quyền truy cập, lỗi và chính sách theo dõi symbolic link. Không nên sử dụng `.toList()` để thu thập hàng triệu đường dẫn nếu chỉ cần đếm, lọc hoặc tổng hợp.

## 7. `Scanner.tokens` và `Pattern.splitAsStream`: biến văn bản thành token

### `Scanner.tokens()`

Từ Java 9, `Scanner.tokens()` trả về `Stream<String>` theo delimiter của scanner.

```java
try (java.util.Scanner scanner =
             new java.util.Scanner("red, blue,green")) {
    scanner.useDelimiter("[,\\s]+");
    List<String> tokens = scanner.tokens().toList();
    System.out.println(tokens); // [red, blue, green]
}
```

Ở đây dấu phẩy và các khoảng trắng theo quy tắc regex dùng làm dấu tách. `Scanner` có thể đọc từ `String`, `Readable`, `Path` hoặc luồng vào. Khi scanner sở hữu nguồn I/O, hãy đóng Scanner đúng vòng đời; đóng Scanner sẽ đóng nguồn bên dưới nếu nguồn đó là `Closeable`. Không thay đổi delimiter hay xen kẽ các thao tác đọc scanner khi đang tiêu thụ Stream token.

**Lưu ý:** `Scanner` có nhiều tính năng phân tích token và hỗ trợ locale. Nó không đơn giản là `String.split`; kiểm tra delimiter, lỗi đọc đầu vào và hành vi token thật sự khi thiết kế parser dữ liệu.

### `Pattern.splitAsStream()`

`Pattern` đã biên dịch có thể tách một chuỗi thành Stream:

```java
java.util.regex.Pattern comma =
        java.util.regex.Pattern.compile("\\s*,\\s*");

List<String> parts =
        comma.splitAsStream("red, blue,green").toList();

System.out.println(parts); // [red, blue, green]
```

Đây là thao tác trên chuỗi đã có, không sở hữu tài nguyên tệp. `splitAsStream` hữu ích khi muốn nối bước tách token với `map`, `filter`, `flatMap` và không cần tự xây một danh sách kết quả giữa chừng.

Đừng mặc định `Pattern.splitAsStream` là trình phân tích CSV đầy đủ. Văn bản CSV có dấu ngoặc kép, dấu phẩy bên trong trường, escape hoặc dòng nhiều phần cần parser theo đúng đặc tả CSV.

## 8. Các API JDK khác tạo Stream

### `Optional.stream()` và `Stream.ofNullable()`

`Optional<T>.stream()` cho 0 hoặc 1 phần tử, thích hợp khi cần `flatMap` nhiều kết quả tùy chọn:

```java
List<String> names = List.of(
        java.util.Optional.of("Lan"),
        java.util.Optional.<String>empty(),
        java.util.Optional.of("Minh"))
        .stream()
        .flatMap(java.util.Optional::stream)
        .toList();

System.out.println(names); // [Lan, Minh]
```

`Stream.ofNullable(value)` có 0 phần tử nếu `value == null`, 1 phần tử nếu khác null:

```java
String maybeName = null;

long count = Stream.ofNullable(maybeName).count();
System.out.println(count); // 0
```

Hai API này giúp biểu diễn **giá trị có thể vắng mặt**, nhưng không tự phân loại lỗi dữ liệu. Nếu thiếu giá trị là tình huống lỗi cần báo, hãy giữ thông tin lỗi thay vì âm thầm bỏ qua mọi giá trị null.

### Dãy nguyên thủy và `Random`

Các Stream chuyên biệt như `IntStream`, `LongStream`, `DoubleStream` tránh boxing trong nhiều phép toán số học:

```java
int sum = java.util.stream.IntStream.rangeClosed(1, 3).sum();
System.out.println(sum); // 6

long total = new java.util.Random(7)
        .ints(3, 0, 10)
        .count();
System.out.println(total); // 3
```

`rangeClosed(1, 3)` bao gồm cả 1 lẫn 3; `range(1, 3)` chỉ gồm 1 và 2. `Random.ints(3, 0, 10)` có kích thước 3, tạo các giá trị trong khoảng `[0, 10)`. Kết quả `count()` bằng 3; không nên dùng tác dụng phụ của bước trung gian để chứng minh số ngẫu nhiên đã thực sự được tạo vì Stream có thể tối ưu pipeline.

### `Stream.iterate`, `Stream.generate` và `Stream.Builder`

```java
List<Integer> even = Stream.iterate(2, n -> n + 2)
        .limit(4)
        .toList();
System.out.println(even); // [2, 4, 6, 8]

List<String> repeated = Stream.generate(() -> "x")
        .limit(3)
        .toList();
System.out.println(repeated); // [x, x, x]

Stream.Builder<String> builder = Stream.builder();
builder.add("a").add("b");
List<String> built = builder.build().toList();
System.out.println(built); // [a, b]
```

Không giới hạn `iterate`/`generate` có thể tạo Stream vô hạn. Khi terminal operation yêu cầu duyệt hết (như `count()` không có điều kiện dừng thích hợp), chương trình có thể không kết thúc. Ngoài overload vô hạn, Java 9 còn có `Stream.iterate(seed, hasNext, next)` cho phép kết thúc dựa trên predicate.

Sau `build()`, builder không phải nơi thêm tiếp các phần tử cho Stream đã xây. Cũng như các Stream khác, Stream tạo từ builder là đối tượng tiêu thụ một lần.

### `StreamSupport.stream`: nguồn Iterable/Spliterator tự định nghĩa

```java
Iterable<Integer> values = java.util.List.of(4, 5, 6);

List<Integer> copied = java.util.stream.StreamSupport
        .stream(values.spliterator(), false)
        .toList();

System.out.println(copied); // [4, 5, 6]
```

Tham số `false` yêu cầu Stream tuần tự. `StreamSupport` là cầu nối cho một nguồn có `Spliterator`, đặc biệt khi tự triển khai cấu trúc hoặc cơ chế duyệt. Tính đúng đắn khi dùng song song phụ thuộc các đặc điểm của spliterator như khả năng phân chia, thứ tự, kích thước và chính sách đồng thời. Không nên viết spliterator tùy chỉnh nếu các API cấp cao hiện có đã đủ.

Nếu spliterator đọc socket, tệp hoặc nguồn đặc biệt, việc chuyển thành Stream **không tự thiết lập chính sách đóng tài nguyên**; thường phải bổ sung vòng đời rõ ràng hoặc đăng ký `onClose` thích hợp và vẫn yêu cầu bên gọi đóng.

## 9. Ví dụ Java 17+ hoàn chỉnh: kết hợp nguồn tệp và nguồn JDK

Chương trình sau tự tạo thư mục tạm, ghi dữ liệu mẫu, xử lý bằng nhiều kiểu nguồn Stream, đóng tài nguyên và xóa dữ liệu mẫu ở cuối. Không cần chuẩn bị tệp thủ công hoặc thư viện ngoài JDK.

Tạo file `JdkStreamSourcesDemo.java`:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Random;
import java.util.Scanner;
import java.util.regex.Pattern;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class JdkStreamSourcesDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("jdk-stream-sources-");
        Path notes = directory.resolve("notes.txt");
        Path colors = directory.resolve("colors.txt");
        Path archive = directory.resolve("archive");
        Path oldNote = archive.resolve("old.txt");

        try {
            Files.createDirectory(archive);
            Files.writeString(notes, "  Java  \n\nStream\n",
                    StandardCharsets.UTF_8);
            Files.writeString(colors, "red, blue,green\n",
                    StandardCharsets.UTF_8);
            Files.writeString(oldNote, "Old entry\n",
                    StandardCharsets.UTF_8);

            // Stream sở hữu tài nguyên tệp: phải close.
            try (Stream<String> lines =
                         Files.lines(notes, StandardCharsets.UTF_8)) {
                List<String> words = lines
                        .map(String::strip)
                        .filter(s -> !s.isBlank())
                        .toList();
                System.out.println("fileLines=" + words);
            }

            // Reader là tài nguyên cần đóng.
            try (BufferedReader reader =
                         Files.newBufferedReader(
                                 notes, StandardCharsets.UTF_8)) {
                long count = reader.lines()
                        .filter(s -> !s.isBlank())
                        .count();
                System.out.println("readerCount=" + count);
            }

            // Dòng từ chuỗi trong bộ nhớ, không có file handle.
            List<String> memoryLines =
                    "first\r\nsecond\n".lines().toList();
            System.out.println("stringLines=" + memoryLines);

            // Files.list: chỉ các mục trực tiếp.
            try (Stream<Path> entries = Files.list(directory)) {
                List<String> names = entries
                        .map(path -> path.getFileName().toString())
                        .sorted()
                        .toList();
                System.out.println("list=" + names);
            }

            // Files.walk: có cả tệp trong thư mục archive.
            try (Stream<Path> paths = Files.walk(directory)) {
                List<String> names = paths
                        .filter(Files::isRegularFile)
                        .map(directory::relativize)
                        .map(Path::toString)
                        .map(path -> path.replace('\\', '/'))
                        .sorted()
                        .toList();
                System.out.println("walkFiles=" + names);
            }

            // Files.find: lọc bằng Path và BasicFileAttributes.
            try (Stream<Path> matching = Files.find(
                    directory, 5,
                    (path, attrs) -> attrs.isRegularFile()
                            && path.getFileName().toString()
                                    .endsWith(".txt"))) {
                System.out.println("findTxtCount=" + matching.count());
            }

            // Scanner quản lý vòng đời reader mà nó bao bọc.
            try (Scanner scanner = new Scanner(
                    Files.newBufferedReader(
                            colors, StandardCharsets.UTF_8))) {
                scanner.useDelimiter("[,\\s]+");
                System.out.println(
                        "tokens=" + scanner.tokens().toList());
            }

            Pattern comma = Pattern.compile("\\s*,\\s*");
            System.out.println("pattern="
                    + comma.splitAsStream("one,two, three").toList());

            System.out.println("range="
                    + IntStream.rangeClosed(1, 3).boxed().toList());

            System.out.println("generatedCount="
                    + new Random(7).ints(3, 0, 10).count());

            System.out.println("nullableCount="
                    + Stream.ofNullable((String) null).count());
        } finally {
            // Xóa theo thứ tự con trước cha, kể cả khi xử lý thất bại.
            Files.deleteIfExists(oldNote);
            Files.deleteIfExists(archive);
            Files.deleteIfExists(colors);
            Files.deleteIfExists(notes);
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch và chạy trên JDK 17 hoặc mới hơn:

```bash
javac JdkStreamSourcesDemo.java
java JdkStreamSourcesDemo
```

Stdout kỳ vọng (đường dẫn tạm ngẫu nhiên không được in; thứ tự đã được sắp xếp):

```text
fileLines=[Java, Stream]
readerCount=2
stringLines=[first, second]
list=[archive, colors.txt, notes.txt]
walkFiles=[archive/old.txt, colors.txt, notes.txt]
findTxtCount=3
tokens=[red, blue, green]
pattern=[one, two, three]
range=[1, 2, 3]
generatedCount=3
nullableCount=0
```

Lưu ý:

- `Files.list` thấy `archive` là một mục trực tiếp, nhưng không tự liệt kê `old.txt` bên trong. `Files.walk` duyệt sâu và sau khi lọc regular files sẽ có `archive/old.txt`.
- `map(path -> path.replace('\\', '/'))` chỉ chuẩn hóa **chuỗi in minh họa** trên Windows/Linux; không thay thế cơ chế xử lý `Path` của Java.
- Sắp xếp bằng `.sorted()` giúp đầu ra của `list`/`walk` ổn định, vì thứ tự liệt kê thư mục không được bảo đảm.
- `Files.find` đếm ba tệp `.txt`, bao gồm một tệp trong `archive`.
- Mỗi Stream tệp/thư mục tồn tại đúng trong một khối `try-with-resources`. Đối với Scanner, khối `try` đóng Scanner và reader mà Scanner sở hữu.
- `finally` giải phóng thư mục tạm; đoạn này dành cho demo có cấu trúc và tên tệp biết trước. Với tệp thực tế, không tự xóa dữ liệu nguồn sau khi xử lý.
- Nếu gặp lỗi xóa dữ liệu tạm, `IOException` từ cleanup có thể được ném; chương trình minh họa không bỏ qua lỗi để giả vờ mọi việc thành công.

## 10. Quy tắc về hiệu năng, vòng đời và an toàn

### Không tiêu thụ lại cùng Stream

```java
Stream<String> lines = "a\nb".lines();
long count = lines.count();
// lines.toList(); // Không hợp lệ: đã tiêu thụ Stream.
```

Muốn xử lý thêm, tạo Stream mới từ nguồn có thể tạo lại. Với tệp, mỗi lần `Files.lines(...)` mở một nguồn mới và phải đóng riêng. Với reader vốn đã đọc xong, gọi lại `lines()` không khiến nội dung cũ xuất hiện trở lại; nếu cần đọc lại tệp, mở reader mới.

### Tránh rò rỉ tài nguyên với nguồn I/O

Cách viết nguy hiểm:

```java
// Không nên: Stream từ Files.lines không có scope đóng rõ ràng.
// List<String> lines = Files.lines(path).toList();
```

Dù terminal operation kết thúc, không nên dựa vào garbage collector để dọn file descriptor. Hãy bọc `Files.lines`, `Files.list`, `Files.walk`, `Files.find` trong `try-with-resources`. Với `Scanner` và `BufferedReader`, đóng đối tượng sở hữu tài nguyên.

### Không khẳng định dữ liệu luôn được đọc hết

Một pipeline như `findFirst`, `anyMatch` hoặc `limit` có thể dừng sớm. Ví dụ:

```java
try (Stream<String> lines = Files.lines(path)) {
    boolean hasHeader = lines.anyMatch(s -> s.startsWith("HEADER"));
}
```

Nếu tìm thấy header sớm, Stream có thể không đọc những dòng sau. `close()` vẫn cần xảy ra. Tránh phụ thuộc vào tác dụng phụ trong `peek` hay `map` như thể mọi phần tử chắc chắn đều được duyệt.

### Không đồng nhất lỗi tạo nguồn với lỗi khi duyệt

`Files.lines(path)` có thể thất bại ngay khi mở file và ném `IOException`. Khi đã có Stream, lỗi đọc muộn có thể phát sinh ở terminal operation dưới dạng `UncheckedIOException`. Nếu cần chuyển chính sách retry hoặc thông báo lỗi, phân biệt được hai giai đoạn này; không `catch (Exception ignored)` rồi trả danh sách rỗng.

### Không mặc định mọi Stream có thứ tự

Nguồn file theo dòng thường duy trì thứ tự văn bản. `Files.list` không cam kết thứ tự liệt kê theo tên; dùng `.sorted()` nếu yêu cầu kết quả xác định. `findAny` đặc biệt trong parallel Stream không đồng nghĩa `findFirst`. Các nguồn từ `HashSet`, splitter tùy chỉnh hoặc generator có thể có đặc tính thứ tự khác.

### Không tùy tiện sửa nguồn trong khi Stream hoạt động

Trong khi duyệt một thư mục, việc tạo/xóa mục ngay tại nguồn có thể làm kết quả liệt kê không nhất quán; Stream không tự bảo đảm snapshot bất biến. Với file có nội dung được tiến trình khác ghi đồng thời, cách thấy dữ liệu phụ thuộc hệ thống tệp, buffering và hợp đồng cụ thể. Khi cần nhất quán, ứng dụng phải có snapshot/giao dịch/đồng bộ thích hợp.

### Cân nhắc độ sâu và symlink khi duyệt cây

`Files.walk` mặc định không theo symbolic link. Bật `FOLLOW_LINKS` chỉ khi thực sự cần và đã xét quyền, cây có chu kỳ, độ sâu và giới hạn I/O. `Files.find` có tham số `maxDepth` bắt buộc; nếu không cần đi sâu, đặt giới hạn nhỏ để tránh duyệt ngoài phạm vi.

### Không dùng Stream để thay thế parser chuyên dụng

`Files.lines` cung cấp dòng, không tự hiểu CSV nhiều dòng, JSON, YAML hoặc định dạng dữ liệu có escape. `Scanner.tokens` và `Pattern.splitAsStream` hữu ích với quy tắc tách đơn giản; với dữ liệu cấu trúc phức tạp, cần parser đúng đặc tả, charset phù hợp và thông báo lỗi có vị trí.

## 11. Chọn API nào cho từng yêu cầu?

| Yêu cầu | API phù hợp | Lý do |
| --- | --- | --- |
| Lọc/đếm dòng tệp lớn | `Files.lines` + terminal aggregate | Tránh giữ toàn bộ dòng trong List nếu không cần |
| Đã có reader cho file/socket | `BufferedReader.lines` | Dùng vị trí hiện tại của reader và đóng owner |
| Tách dòng của String đã tải | `String.lines` | Không cần tạo reader hoặc file handle |
| Liệt kê file/dir ngay trong một thư mục | `Files.list` | Không cần đi sâu |
| Duyệt toàn bộ cây thư mục | `Files.walk` | Có độ sâu, đường dẫn con, lọc file/dir |
| Tìm theo metadata của tệp | `Files.find` | Matcher nhận thuộc tính cùng đường dẫn |
| Tách token theo delimiter | `Scanner.tokens` | Tận dụng cấu hình token của Scanner |
| Tách chuỗi bằng regex có sẵn | `Pattern.splitAsStream` | Ghép được với pipeline mà không tạo List trung gian |
| Gộp nhiều Optional | `flatMap(Optional::stream)` | Biến `0 hoặc 1` giá trị thành Stream phần tử |
| Dãy số không cần List đầu vào | `IntStream.range`/`rangeClosed` | Tạo phần tử theo dải số |
| Dữ liệu tự sinh | `Stream.iterate`/`generate` | Tạo theo thuật toán, cần kiểm soát kết thúc |
| Nguồn Iterable/Spliterator tùy chỉnh | `StreamSupport.stream` | Dùng khi API cấp cao không đáp ứng |

## 12. Bài tập và tiêu chí tự kiểm tra

1. Tạo tệp UTF-8 gồm ba dòng `" Java "`, dòng trống và `"Stream"`. Dùng `Files.lines` với `try-with-resources` để lấy `List.of("Java", "Stream")`. Giải thích nơi tài nguyên được đóng.
2. Cho thư mục chứa `a.txt`, `b.csv` và thư mục con `archive/c.txt`. So sánh kết quả của `Files.list`, `Files.walk` và `Files.find` khi chỉ lấy `.txt` và sort theo đường dẫn tương đối.
3. Sử dụng `BufferedReader.lines` sau một lời gọi `reader.readLine()`. Dự đoán Stream nhìn thấy những dòng nào; giải thích vì sao không nên trộn thao tác đọc khác khi Stream đang duyệt.
4. Với chuỗi `"A\r\nB\n"`, dùng `String.lines` để lấy danh sách; thử thêm một dấu xuống dòng nữa để quan sát số phần tử.
5. Dùng `Pattern.compile("\\s*,\\s*").splitAsStream("a, b,c")` rồi `.map(String::toUpperCase).toList()`; dự đoán `[A, B, C]`.
6. Dùng `Optional.of("ok").stream()` và `Optional.empty().stream()`; ghép cả hai qua `Stream.of(...).flatMap(Optional::stream)` và lý giải vì sao có một phần tử.
7. Tạo `Stream.iterate(2, n -> n + 2).limit(5)`, tính tổng mà không gọi `toList()`. Kết quả cần đạt là `30`.
8. Mô tả vì sao `Files.lines(path).findFirst()` không phải cách quản lý tài nguyên đúng nếu không đóng Stream, ngay cả khi đã tìm được kết quả.

Khi tự đánh giá, hãy luôn trả lời bốn câu hỏi: **Nguồn dữ liệu nằm ở đâu? Phần tử được cung cấp khi nào? Ai đóng tài nguyên? Terminal operation tạo kết quả gì?** Trả lời đúng bốn câu này giúp lựa chọn nguồn Stream chính xác, tránh rò rỉ file handle, tránh đọc thừa dữ liệu và không nhầm pipeline với cấu trúc lưu trữ.
