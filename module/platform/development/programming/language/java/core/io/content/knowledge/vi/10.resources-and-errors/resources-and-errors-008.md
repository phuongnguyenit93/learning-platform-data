# UncheckedIOException khi kết hợp I/O với Stream API

## 1. Vì sao cần UncheckedIOException?

Trong Java, nhiều thao tác I/O có thể ném **`IOException`**, một *checked exception*. Trình biên dịch yêu cầu phương thức gọi phải bắt (`catch`) hoặc khai báo (`throws IOException`) ngoại lệ ấy. Nhưng các functional interface thông dụng của **Stream API** như `Function<T,R>`, `Predicate<T>`, `Consumer<T>` không khai báo checked exception ở phương thức trừu tượng.

Do đó, cách viết có vẻ tự nhiên này **không biên dịch**:

```java
// Ví dụ cố ý SAI: Files.readString có thể throws IOException.
List<String> contents = paths.stream()
        .map(path -> Files.readString(path))
        .toList();
```

`Stream.map` nhận một `Function`; `Function.apply` không khai báo `throws IOException`. Dù phương thức bao quanh có `throws IOException`, bản thân lambda vẫn bị ràng buộc bởi chữ ký `Function.apply`.

`java.io.UncheckedIOException` giải quyết ranh giới đó: đây là một **`RuntimeException` chuyên dùng để bao bọc `IOException`**. Ta có thể chuyển một lỗi I/O checked thành lỗi unchecked tại chỗ lambda, cho phép ngoại lệ thoát qua `map`, `filter`, `forEach` hoặc phép biến đổi khác, rồi quyết định xử lý ở ranh giới thích hợp.

```text
File / network / Reader
      │
      ▼
Phương thức I/O throws IOException  (checked)
      │
      ▼
catch (IOException cause)
      │
      ▼
throw new UncheckedIOException(cause)
      │
      ▼
Stream pipeline / terminal operation  (unchecked)
      │
      ▼
catch (UncheckedIOException ex)
      └─ ex.getCause()  → IOException ban đầu
```

**Mục tiêu của UncheckedIOException không phải che giấu lỗi.** Nó bảo toàn **nguyên nhân `IOException`** để code có thể báo lỗi, huỷ xử lý, retry có kiểm soát, hoặc chuyển ngoại lệ về API checked ở lớp trên.

### Phân biệt các khái niệm

| Khái niệm | Ý nghĩa |
| --- | --- |
| `IOException` | Checked exception mô tả lỗi đọc/ghi hay nguồn dữ liệu |
| `UncheckedIOException` | Runtime exception bọc một `IOException`, tiện cho nơi không khai báo checked exception |
| `RuntimeException` | Nhóm exception unchecked rộng hơn; không riêng cho I/O |
| Stream pipeline | Chuỗi các bước biến đổi thường chạy **lazy** |
| Terminal operation | `toList()`, `collect()`, `count()`, `forEach()`, `findFirst()`... kích hoạt thực thi |
| Resource-owning stream | Một số Stream API giữ file/directory handle và cần `close()` |

Một pipeline thuần xử lý dữ liệu trong bộ nhớ có thể hoàn toàn không cần `UncheckedIOException`; nó xuất hiện khi **một thao tác I/O thật** được thực hiện hoặc khi API Java chuẩn sử dụng chính kiểu ngoại lệ này để truyền lỗi trong quá trình duyệt stream.

## 2. API và quan hệ với IOException

`UncheckedIOException` nằm trong `java.io`. Nó kế thừa `RuntimeException`, nên trình biên dịch không yêu cầu caller bắt hoặc khai báo. Các constructor quan trọng:

```java
new UncheckedIOException(IOException cause)
new UncheckedIOException(String message, IOException cause)
```

Đoạn này là **biểu thức minh họa**, cần import `java.io.UncheckedIOException`, `java.io.IOException`; `cause` phải là một `IOException` không null. Đây **không phải constructor nhận Throwable bất kỳ**. Đừng dùng kiểu này để bọc `IllegalArgumentException` hoặc `NullPointerException` vì chúng không biểu thị lỗi I/O.

Các thao tác:

- `getCause()` trả chính `IOException` gốc.
- `getMessage()` trả thông điệp của wrapper (có thể thêm ngữ cảnh).
- Stack trace cho biết nơi bọc và chuỗi `cause` giúp lần về điểm phát sinh I/O.
- Vì là unchecked, `UncheckedIOException` có thể truyền qua `Function.apply`, `Predicate.test`, `Consumer.accept` mà không đòi khai báo `throws`.

Một lựa chọn tốt khi bọc là thêm **ngữ cảnh thực tế** như đường dẫn tương đối, thao tác đang làm, ID bản ghi, hoặc định dạng cần đọc:

```java
try {
    return Files.readString(path, StandardCharsets.UTF_8);
} catch (IOException cause) {
    throw new UncheckedIOException(
            "Cannot read: " + path, cause);
}
```

Đây là đoạn nằm trong **một phương thức trả String** có `Path path` và import cần thiết. Không trả `""` chỉ để tránh lỗi trừ khi ứng dụng đã định nghĩa rõ “không đọc được thì coi là chuỗi rỗng”, vì như vậy sẽ trộn lỗi I/O với dữ liệu hợp lệ.

## 3. Checked exception và chữ ký của lambda

Xét `java.util.function.Function<T,R>`:

```java
@FunctionalInterface
public interface Function<T, R> {
    R apply(T value);
}
```

Đây là **hình thức rút gọn để giải thích chữ ký**, không sao chép đầy đủ nội dung interface chuẩn. `apply` không khai báo checked exceptions. Một lambda dùng làm `Function<Path, String>` vì vậy không thể để `IOException` từ `Files.readString` thoát trực tiếp.

### Cách phổ biến: catch ngay trong lambda rồi bọc

```java
List<String> texts = paths.stream()
        .map(path -> {
            try {
                return Files.readString(path, StandardCharsets.UTF_8);
            } catch (IOException cause) {
                throw new UncheckedIOException(
                        "Cannot read " + path, cause);
            }
        })
        .toList();
```

Đây là đoạn minh họa; `paths` là `List<Path>` đã có. Cần `Files`, `StandardCharsets`, `IOException`, `UncheckedIOException`, `List`. Lời gọi `toList()` là terminal operation và có từ **Java 16**.

Nếu mọi tệp đều đọc được, `texts` chứa nội dung lần lượt theo encounter order của một list-stream tuần tự. Nếu một tệp gây `IOException`, lambda bọc nó thành `UncheckedIOException`, phép `toList()` thất bại và không trả danh sách hoàn chỉnh.

**Không có tính giao dịch tự động:** nếu lambda còn ghi file, cập nhật cơ sở dữ liệu hoặc thay đổi trạng thái, các phần đã xử lý trước lỗi có thể vẫn có side effect. Stream API không rollback những tác động đó.

### Cách khác: đưa I/O vào phương thức adapter có tên

```java
static String readUtf8Unchecked(Path path) {
    try {
        return Files.readString(path, StandardCharsets.UTF_8);
    } catch (IOException cause) {
        throw new UncheckedIOException(
                "Failed to read " + path, cause);
    }
}
```

Đây là **phương thức minh họa**; caller dùng `paths.stream().map(MyClass::readUtf8Unchecked)`. Đặt logic bọc trong một method giúp code stream dễ đọc và dễ kiểm thử. Một thư viện tổng quát có thể có adapter cho “throwing function”, nhưng cũng cần chính sách rõ rằng **chỉ `IOException` được bọc bằng `UncheckedIOException`**; lỗi lập trình khác giữ nguyên kiểu.

## 4. Ví dụ Java 17 chạy được: wrapper trong pipeline

Chương trình mô phỏng nguồn I/O xác định để thấy sự khác biệt giữa exception gốc và wrapper. Nó không cần tệp bên ngoài, nên output ổn định.

**Tệp `UncheckedIoPipelineDemo.java`:**

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.Locale;

public class UncheckedIoPipelineDemo {
    static String load(String name) throws IOException {
        if ("broken".equals(name)) {
            throw new IOException("synthetic read failure");
        }
        return name.toUpperCase(Locale.ROOT);
    }

    static String loadUnchecked(String name) {
        try {
            return load(name);
        } catch (IOException cause) {
            throw new UncheckedIOException("Loading " + name, cause);
        }
    }

    public static void main(String[] args) {
        List<String> good = List.of("alpha", "beta").stream()
                .map(UncheckedIoPipelineDemo::loadUnchecked)
                .toList();
        System.out.println("Success: " + good);

        try {
            List.of("alpha", "broken", "beta").stream()
                    .map(UncheckedIoPipelineDemo::loadUnchecked)
                    .toList();
        } catch (UncheckedIOException failure) {
            System.out.println("Wrapper: "
                    + failure.getClass().getSimpleName());
            System.out.println("Cause: "
                    + failure.getCause().getClass().getSimpleName());
            System.out.println("Cause message: "
                    + failure.getCause().getMessage());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac UncheckedIoPipelineDemo.java
java UncheckedIoPipelineDemo
```

**Stdout chính xác:**

```text
Success: [ALPHA, BETA]
Wrapper: UncheckedIOException
Cause: IOException
Cause message: synthetic read failure
```

Điểm cần quan sát:

1. `load` khai báo `throws IOException`; nó vẫn giữ API checked nếu được gọi trực tiếp.
2. `loadUnchecked` bắt và bọc lỗi; có thể dùng làm method reference cho `map`.
3. `toList()` mới thực thi pipeline. Khi một phần tử ném lỗi, kết quả list không được trả về.
4. `getCause()` giữ `IOException` gốc với thông điệp ban đầu.

Không nhất thiết mọi test phải tạo file lỗi thực. Test bằng phương thức giả lập như trên giúp xác minh **chính sách truyền ngoại lệ** một cách rõ ràng, còn integration test nên kiểm tra quyền truy cập, tệp biến mất, ổ đĩa hoặc network khi cần.

## 5. Stream API thực thi lazy: lỗi xảy ra khi nào?

Các phép biến đổi trung gian như `map`, `filter`, `peek`, `flatMap` thường xây dựng pipeline **mà chưa xử lý phần tử nào**. Vì vậy việc khai báo pipeline có thể không gây lỗi; lỗi có thể xuất hiện khi gọi terminal operation:

```java
Stream<String> pipeline = paths.stream()
        .map(MyClass::readUtf8Unchecked); // Chưa nhất thiết đọc tệp.

// Đây mới là thời điểm các phần tử thực sự được đọc:
List<String> result = pipeline.toList();
```

Đoạn minh họa trên giả định method `readUtf8Unchecked` có sẵn và các import tương ứng. Không nên kết luận “pipeline tạo thành công nên I/O thành công”.

**Short-circuit operation** cũng thay đổi phạm vi lỗi có thể xảy ra:

- `findFirst()`, `anyMatch()`, `limit(n)` có thể chỉ đọc một phần nguồn.
- Một phần tử lỗi ở phía sau có thể **không được chạm tới**.
- `count()` trên một số nguồn và pipeline có thể được tối ưu, không gọi mọi intermediate operation không ảnh hưởng kết quả. Không đặt I/O side effects vào `peek` rồi cho rằng chúng luôn chạy.

Nếu nghiệp vụ cần đảm bảo **mọi tệp đều được xác minh**, phải chọn terminal operation và cấu trúc xử lý thích hợp. Stream API là công cụ xử lý dữ liệu, không phải engine giao dịch đảm bảo mọi side effect đã xảy ra đúng một lần.

### Đưa I/O vào map có luôn là lựa chọn tốt?

Không. Khi quá trình có nhiều trạng thái, cơ chế retry, yêu cầu rollback hoặc nhiều ngoại lệ cần thu thập, một vòng `for` thông thường có thể rõ ràng hơn. `UncheckedIOException` là công cụ kỹ thuật khi **checked exception chạm biên functional interface**, không phải lý do để ép mọi công việc I/O vào một pipeline.

## 6. Files.lines: IOException ở lúc mở và UncheckedIOException khi đọc lười

`Files.lines(Path, Charset)` trả `Stream<String>` đọc dòng từ file theo cách lazy. Có **hai thời điểm lỗi** cần phân biệt:

1. **Lúc mở**: `Files.lines(path, charset)` có thể ném **`IOException` (checked)** nếu không mở được tệp.
2. **Lúc tiêu thụ**: sau khi stream được tạo, nếu xảy ra lỗi I/O trong lúc đọc các dòng, lỗi thường được truyền ra dưới dạng **`UncheckedIOException`** từ operation đang duyệt stream.

```java
try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines.filter(s -> !s.isBlank()).count();
    System.out.println(count);
} catch (UncheckedIOException duringRead) {
    // Lỗi xảy ra khi duyệt stream.
} catch (IOException duringOpenOrClose) {
    // Lỗi checked lúc mở hoặc tại một lời gọi I/O khai báo checked.
}
```

Đây là **đoạn minh họa**, cần import `Stream`, `Files`, `Path`, `StandardCharsets`, `UncheckedIOException`, `IOException`. `Stream.close()` không khai báo checked `IOException`, vì vậy không thể giả định một lỗi giải phóng file luôn đi ra ở nhánh catch checked. Quan trọng nhất là luôn dùng `try-with-resources` để đóng `Stream<String>` do `Files.lines` trả về.

**Không phải terminal operation tự đóng stream.** Gọi `count()`, `toList()` hoặc `forEach()` hoàn thành không thay thế `close()` khi stream sở hữu file handle.

### Ví dụ Java 17 chạy được: Files.lines và quản lý tài nguyên

**Tệp `FileLinesDemo.java`:**

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class FileLinesDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("io-lines-", ".txt");

        try {
            Files.writeString(file, "alpha\n\nbeta\n",
                    StandardCharsets.UTF_8);

            try (Stream<String> lines =
                         Files.lines(file, StandardCharsets.UTF_8)) {
                long nonBlank = lines.filter(s -> !s.isBlank()).count();
                System.out.println("Nonblank lines: " + nonBlank);
            }

            try (Stream<String> lines =
                         Files.lines(file, StandardCharsets.UTF_8)) {
                String joined = lines
                        .filter(s -> !s.isBlank())
                        .map(String::toUpperCase)
                        .reduce((a, b) -> a + "," + b)
                        .orElse("");
                System.out.println("Joined: " + joined);
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Lệnh:

```bash
javac FileLinesDemo.java
java FileLinesDemo
```

**Stdout chính xác khi thao tác tệp thành công:**

```text
Nonblank lines: 2
Joined: ALPHA,BETA
```

Một stream đã dùng terminal operation **không được sử dụng lại**; ví dụ mở `Files.lines` lần thứ hai cho phép chạy một phép tính khác. Tệp tạm được xóa trong `finally`. Nếu thao tác xóa lỗi, chương trình có thể ném `IOException`, vì thế output nêu trên là trường hợp chạy thành công.

Với tệp có encoding lỗi hoặc nội dung đọc trong lúc tệp bị thay đổi, cách thức báo lỗi phụ thuộc API và charset; ứng dụng cần xử lý `UncheckedIOException` theo chính sách của mình, không chỉ bắt `IOException` checked ở lời gọi mở.

## 7. BufferedReader.lines và tài nguyên thuộc về ai?

`BufferedReader.lines()` cũng trả `Stream<String>` lấy dòng từ reader. Khi có lỗi I/O trong lúc đọc, stream có thể ném `UncheckedIOException`. Tuy nhiên cần phân biệt rõ ownership:

```java
try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    long lines = reader.lines().count();
    System.out.println(lines);
}
```

Đây là đoạn minh họa. Ở đây `BufferedReader` là tài nguyên được mở và **chính try-with-resources trên reader** chịu trách nhiệm đóng. Đừng tự suy luận rằng chỉ vì một đối tượng có kiểu `Stream<String>`, việc đóng nó luôn đóng reader bên dưới; **`BufferedReader.lines()` không phải cùng hợp đồng tài nguyên với `Files.lines()`**.

Cần lưu ý: khi một Stream đang tiêu thụ `BufferedReader`, tránh thao tác trực tiếp trên reader từ luồng khác hoặc giữa các bước stream. Reader là nguồn có trạng thái, dễ dẫn đến dữ liệu bị bỏ qua hoặc tiêu thụ không theo ý.

### So sánh nhanh

| API | Ai mở nguồn? | Ai cần đóng? | Lỗi khi duyệt |
| --- | --- | --- | --- |
| `Files.lines(path, charset)` | API mở file | Caller đóng `Stream<String>` trả về | Có thể là `UncheckedIOException` |
| `reader.lines()` | Caller đã có `BufferedReader` | Caller quản lý và đóng reader | Có thể là `UncheckedIOException` |
| `Files.readAllLines(path, charset)` | API đọc trong lời gọi | Không trả stream sống; trả `List<String>` | `IOException` checked từ lời gọi |
| `Files.readString(path, charset)` | API đọc trong lời gọi | Không trả stream sống; trả `String` | `IOException` checked từ lời gọi |

API trả về toàn bộ dữ liệu thường đơn giản về ownership, nhưng tiêu tốn bộ nhớ theo kích thước file. API lazy hữu ích cho dữ liệu lớn nhưng cần quản lý đúng thời điểm đóng.

## 8. Files.list, Files.walk và Files.find

Không chỉ `Files.lines`, các API duyệt thư mục cũng thường trả **Stream API gắn với resource I/O**:

- `Files.list(directory)`: trả một stream duyệt các phần tử trực tiếp của thư mục.
- `Files.walk(start, maxDepth, ...)`: duyệt cây tệp và thư mục theo độ sâu quy định.
- `Files.find(start, maxDepth, matcher, ...)`: duyệt cây và lọc qua `BiPredicate<Path,BasicFileAttributes>`.

Lời gọi **mở** những stream này có thể ném `IOException` checked. Trong khi duyệt lazy, nếu phát sinh lỗi khi đọc directory hoặc attributes, có thể ném `UncheckedIOException`. Các stream đó **phải được đóng** để giải phóng tài nguyên dùng để duyệt thư mục.

```java
try (Stream<Path> entries = Files.list(directory)) {
    List<Path> names = entries.sorted().toList();
    // Dùng names ở đây.
}
```

Đây là đoạn minh họa, giả định `Path directory` đã có. Việc `toList()` trả về danh sách các `Path` không kéo theo việc giữ directory stream mở sau khi khối `try` kết thúc.

### Lồng I/O trong Files.walk

Một pattern hay gặp là vừa duyệt file, vừa đọc nội dung:

```java
try (Stream<Path> files = Files.walk(root)) {
    List<String> texts = files
            .filter(Files::isRegularFile)
            .map(UncheckedFileReader::readUtf8Unchecked)
            .toList();
}
```

Đây là đoạn minh họa: class `UncheckedFileReader` giả định có `readUtf8Unchecked(Path)` như phương thức adapter ở mục 3. Có **hai nguồn lỗi**:

1. Bản thân `Files.walk` khi duyệt hệ thống tệp (và truy vấn thuộc tính), có thể ném `UncheckedIOException`.
2. `readUtf8Unchecked` do ứng dụng tự viết cũng có thể ném `UncheckedIOException`.

Để chẩn đoán, nên thêm ngữ cảnh thao tác/đường dẫn ngay khi bọc nguyên nhân. **Không chạy song song tùy tiện** trên cây tệp nếu chưa kiểm soát file descriptor, tác động từ việc file bị thay đổi, quyền đọc và giới hạn bộ nhớ khi tích lũy mọi nội dung.

## 9. Ví dụ thực tế: đọc nhiều tệp và trả lỗi có ngữ cảnh

Một hàm nhận danh sách đường dẫn muốn dùng Stream API nhưng vẫn khai báo **`throws IOException`** với caller. Có thể bọc trong lambda rồi **gỡ wrapper tại ranh giới public API**.

**Tệp `ReadFilesWithStream.java`:**

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class ReadFilesWithStream {
    static List<String> readAll(List<Path> paths) throws IOException {
        try {
            return paths.stream()
                    .map(path -> {
                        try {
                            return Files.readString(
                                    path, StandardCharsets.UTF_8);
                        } catch (IOException cause) {
                            throw new UncheckedIOException(
                                    "Reading " + path.getFileName(), cause);
                        }
                    })
                    .toList();
        } catch (UncheckedIOException failure) {
            throw failure.getCause();
        }
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("io-batch-", ".txt");
        try {
            Files.writeString(file, "hello",
                    StandardCharsets.UTF_8);

            System.out.println("Read: " + readAll(List.of(file)));

            Path missing = file.resolveSibling(
                    "missing-" + file.getFileName());
            try {
                readAll(List.of(missing));
            } catch (IOException failure) {
                System.out.println("Missing file reported: "
                        + (failure instanceof java.nio.file.NoSuchFileException));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ReadFilesWithStream.java
java ReadFilesWithStream
```

**Stdout trong tình huống chuẩn (tệp missing thực sự không tồn tại):**

```text
Read: [hello]
Missing file reported: true
```

Đầu vào `file` là một tệp tạm được tạo ở runtime. Biến `missing` trỏ tới một tên khác trong cùng thư mục, có tiền tố `missing-`; ví dụ giả định nó không tồn tại để sinh `NoSuchFileException`. Trong hệ thống thật, đối tượng file có thể bị tạo bởi một quá trình khác đồng thời, vì vậy khi viết test nghiêm ngặt nên chọn một thư mục tạm riêng và chủ động kiểm soát fixture.

### Một đánh đổi đáng lưu ý

Trong `readAll`, việc `throw failure.getCause()` giữ nguyên kiểu `IOException` gốc, nhưng **loại bỏ thông điệp ngữ cảnh của wrapper** khỏi exception được ném ra cho caller. Nếu ngữ cảnh đường dẫn là thông tin quan trọng, có thể:

- Khai báo API trả `UncheckedIOException` và để wrapper được truyền nguyên vẹn.
- Ném một `IOException` mới với message chứa ngữ cảnh và `failure.getCause()` làm cause.
- Ghi ngữ cảnh qua logging/diagnostics thích hợp trước khi quyết định lan truyền lỗi.

Không nên “unwrap” theo thói quen nếu nó khiến người vận hành không biết file nào lỗi. Chọn kiểu exception ở **ranh giới API** phải phù hợp với hợp đồng công khai và nhu cầu chẩn đoán.

## 10. Một policy thiết kế: unchecked bên trong, checked ở bên ngoài

Có ba phong cách API phổ biến:

**Phong cách A — Giữ checked IOException ở API public.** Bên trong Stream API có thể tạm bọc; trước khi trả ra, unwrap hoặc tạo một `IOException` mới có thêm ngữ cảnh.

```java
static List<String> process(List<Path> paths) throws IOException {
    try {
        return paths.stream()
                .map(MyClass::readUtf8Unchecked)
                .toList();
    } catch (UncheckedIOException ex) {
        throw new IOException("Batch read failed", ex.getCause());
    }
}
```

Đây là phương thức minh họa; `MyClass::readUtf8Unchecked` cần được định nghĩa tương ứng.

**Phong cách B — API public cho phép UncheckedIOException thoát ra.** Một số API chuẩn như `Files.lines` khi duyệt lazy tuân theo cách này. Caller phải biết rằng lỗi có thể xảy ra **muộn** khi tiêu thụ stream.

**Phong cách C — Xử lý lỗi trên từng phần tử.** Thay vì để lỗi đầu tiên dừng toàn pipeline, hệ thống trả kết quả như `Success(value)` hoặc `Failure(path, error)`. Khi đó tất cả phần tử có thể được xét và báo nhiều lỗi cùng lúc. Không nên tự thay lỗi bằng `null`, `""`, `Optional.empty()` nếu nghiệp vụ cần phân biệt “file rỗng”, “không có dữ liệu” và “đọc lỗi”.

Lựa chọn phụ thuộc câu hỏi nghiệp vụ: **một lỗi có làm thất bại toàn bộ batch không**, hay người dùng muốn xem danh sách thành công và thất bại riêng?

## 11. Biến một phương thức IOException thành Function tái sử dụng

Nếu codebase có nhiều lambda cần đọc/ghi, có thể định nghĩa interface riêng khai báo `IOException`, rồi tạo adapter:

```java
@FunctionalInterface
interface IOFunction<T, R> {
    R apply(T value) throws IOException;
}

static <T, R> java.util.function.Function<T, R> unchecked(
        IOFunction<T, R> operation) {
    return value -> {
        try {
            return operation.apply(value);
        } catch (IOException cause) {
            throw new UncheckedIOException(cause);
        }
    };
}
```

Đây là **đoạn minh họa trong một lớp Java**, cần `java.io.IOException`, `java.io.UncheckedIOException`. Có thể dùng:

```java
List<String> texts = paths.stream()
        .map(unchecked(path -> Files.readString(path,
                StandardCharsets.UTF_8)))
        .toList();
```

Adapter gom logic catch/bọc về một nơi. Tuy nhiên nó cũng có giới hạn:

- Không tự bổ sung ngữ cảnh về đường dẫn/record; có thể dùng adapter nhận thông điệp từ caller nếu cần.
- Chỉ bọc `IOException`. Không được bắt toàn bộ `Exception` rồi biến lỗi lập trình thành “I/O problem”.
- Nếu I/O có side effect và retry, adapter không làm thao tác trở thành idempotent.
- Về mặt đọc code, adapter giúp ngắn hơn nhưng đôi khi che mất vị trí đọc/ghi; dùng khi thực sự làm kiến trúc dễ hiểu.

Một adapter tương tự có thể xây cho `IOConsumer`, `IOPredicate` hoặc `IOBiFunction`. Không cần xây thư viện wrapper quá lớn cho vài chỗ catch riêng lẻ.

## 12. Không dùng UncheckedIOException cho mọi ngoại lệ

`UncheckedIOException` chỉ biểu đạt “đã gặp `IOException` nhưng API ở đây không khai báo checked exception”. Các trường hợp sau cần phân biệt:

| Sự cố | Loại lỗi tự nhiên | Có nên tự bọc UncheckedIOException? |
| --- | --- | --- |
| `Files.readString` bị từ chối quyền đọc | `IOException`/subclass | Có, khi phải qua lambda không throws checked |
| File biến mất lúc đang mở | `NoSuchFileException` (subclass `IOException`) | Có thể bọc như trên |
| Parser thấy số trong văn bản không hợp lệ | `NumberFormatException` | Không; đây là lỗi dữ liệu/parse, không phải IOException |
| `String.substring` dùng index sai | `IndexOutOfBoundsException` | Không; lỗi logic hoặc input |
| Null bất ngờ trong lambda | `NullPointerException` | Không; xử lý nguyên nhân null |
| Java heap hết bộ nhớ | `OutOfMemoryError` | Không; không phải IOException |
| `Files.lines` lỗi khi duyệt nội dung | `UncheckedIOException` từ API | Giữ/catch ở ranh giới phù hợp, không cần bọc lồng thêm vô ích |

Nếu một luồng báo `UncheckedIOException`, luôn xem `getCause()` để hiểu lỗi gốc, nhưng cũng giữ context của wrapper nếu có. Đừng chỉ log `failure.getMessage()` rồi bỏ stack trace và cause khi chẩn đoán lỗi khó.

## 13. Tài nguyên và ngoại lệ: try-with-resources bao quanh terminal operation

Một lỗi I/O có thể xảy ra **giữa quá trình duyệt**. Nếu stream được mở từ file hoặc directory, resource vẫn phải được đóng khi operation ném exception.

```java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    lines.map(this::transform)
         .forEach(this::accept);
} catch (UncheckedIOException failure) {
    // Resource của Files.lines đã được đóng trước khi vào catch.
    handleIoError(failure.getCause());
}
```

Đây là **mã minh họa có các method theo ứng dụng** (`transform`, `accept`, `handleIoError`) chưa định nghĩa; không phải chương trình độc lập. `try-with-resources` đảm bảo gọi `close()` cho Stream, kể cả khi `map` hoặc `forEach` bị lỗi. Còn việc **close có thành công tuyệt đối hay không** vẫn tùy resource và hành vi API.

Nếu chỉ đóng stream trong nhánh thành công:

```java
// Sai về lifecycle nếu terminal operation ném exception.
Stream<String> lines = Files.lines(path);
lines.forEach(System.out::println);
lines.close();
```

thì lúc `forEach` ném lỗi, câu lệnh `close()` không chạy. Hãy mở và dùng trong cùng một `try-with-resources`.

### Suppressed exception

Khi thân `try` phát sinh exception, rồi việc đóng resource cũng phát sinh exception, Java gắn lỗi đóng thành **suppressed** của lỗi chính theo quy tắc try-with-resources. Nếu bọc hoặc tạo mới exception tùy tiện ở tầng cao mà không giữ nguyên chain, thông tin dọn dẹp có thể bị mất. Khi điều tra lỗi I/O nhiều lớp, xem cả `getCause()` và `getSuppressed()`.

## 14. Stream tuần tự, parallel stream và khả năng quan sát lỗi

Trong một **sequential stream**, các thao tác thực hiện theo cơ chế duyệt tuần tự của pipeline. Khi lỗi đầu tiên được ném, terminal operation có thể dừng; các phần tử sau không nhất thiết được xử lý.

Trong **parallel stream**:

- Nhiều file có thể được đọc đồng thời.
- Thứ tự bắt đầu/hoàn tất I/O có thể khác encounter order.
- Một exception ở một nhánh không có nghĩa mọi task đã dừng tức thời; một số thao tác khác có thể đã tạo side effect.
- Cần cân nhắc tài nguyên như file descriptor, ổ đĩa, network, và giới hạn concurrency.

Không nên chuyển sang `parallel()` chỉ vì I/O chậm. Với I/O có số lượng task lớn, chọn mô hình concurrency/queue phù hợp, giới hạn số request đồng thời và xác định rõ cơ chế hủy/đóng resource.

Các pipeline kết hợp `parallel`, side effects, retry và khôi phục dữ liệu thường dễ kiểm soát bằng một kiến trúc executor/service rõ ràng hơn là dùng lambda bắt lỗi ở khắp nơi.

## 15. Ghi lỗi có ngữ cảnh và tránh rò rỉ thông tin

Một thông điệp exception hữu ích cần mô tả **thao tác nào** thất bại:

```java
throw new UncheckedIOException(
        "Reading configuration: " + path.getFileName(), cause);
```

Đây là ví dụ minh họa, không phải class độc lập. Không phải mọi đường dẫn đầy đủ, tên người dùng hoặc nội dung file đều phù hợp để in ra log công khai. Khi logging trong ứng dụng nhiều người dùng, xem xét việc tránh lộ path tuyệt đối hoặc dữ liệu nhạy cảm.

Log **một lần ở nơi có ngữ cảnh thích hợp** và giữ nguyên exception cause. Nếu mọi tầng vừa log vừa ném lại, cùng một lỗi có thể xuất hiện nhiều lần mà không thêm thông tin hữu ích.

Một chiến lược hợp lý:

- Tầng I/O thấp: bọc `IOException` với thao tác/nguồn hữu ích.
- Tầng nghiệp vụ: quyết định retry, fail-fast hoặc ghi nhận thất bại theo từng phần tử.
- Tầng API/CLI: chuyển lỗi thành response/error code và thông điệp dành cho người dùng; giữ stack trace cho kênh diagnostics phù hợp.

## 16. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi `Files.readString(path)` trực tiếp trong `map` | Lambda không biên dịch vì checked IOException | catch/bọc `UncheckedIOException` hoặc xử lý I/O ngoài stream |
| Chỉ catch `IOException` bên ngoài terminal operation | Có thể không bắt lỗi `UncheckedIOException` từ quá trình duyệt lazy | Bắt đúng kiểu ở ranh giới tương ứng |
| Cho rằng `map` chạy ngay khi pipeline được khai báo | Lỗi có thể chỉ xuất hiện khi `toList()`/terminal operation | Hiểu lazy evaluation |
| Không đóng `Files.lines`/`Files.walk` | Có thể rò rỉ file/directory handles | `try-with-resources` quanh toàn bộ terminal operation |
| Nghĩ `count()` tự đóng stream | Resource vẫn cần close | Dùng `try-with-resources` |
| Dùng `reader.lines()` rồi chỉ đóng Stream API | Reader do caller sở hữu vẫn cần đóng | Quản lý vòng đời `BufferedReader` |
| Bọc bất kỳ `Exception` vào `UncheckedIOException` | Sai kiểu hoặc che lỗi không thuộc I/O | Chỉ bọc `IOException` |
| Catch rồi trả chuỗi rỗng cho lỗi đọc file | Mất phân biệt giữa file rỗng và đọc lỗi | Truyền lỗi hoặc model hóa kết quả lỗi |
| Unwrap và vứt hết message chứa path | Khó biết tệp nào lỗi | Giữ context trong wrapper hoặc `IOException` mới có cause |
| Dùng `peek` cho một side effect I/O bắt buộc | Có thể không chạy do short-circuit/optimization | Dùng phép xử lý rõ ràng, không dựa vào peek |
| Dùng `parallel()` không giới hạn khi duyệt file | Quá nhiều I/O đồng thời, khó đoán side effects | Giới hạn đồng thời, chọn kiến trúc phù hợp |
| Cho rằng xử lý thành công vài phần tử đầu là batch thành công | Lỗi giữa chừng làm pipeline dừng | Kiểm tra terminal operation hoàn tất; quyết định rollback/partial results |
| Đóng file stream chỉ sau `forEach` | Ngoại lệ ngăn câu lệnh close | Đặt cả xử lý và resource trong try-with-resources |
| Chỉ log wrapper message rồi bỏ cause | Mất vị trí lỗi gốc | Truyền/ghi cause và suppressed đúng cách |

## 17. Khi nào nên dùng vòng for thay vì Stream API?

Stream API phù hợp khi phép biến đổi dữ liệu gọn, các phần tử phần lớn độc lập và chính sách lỗi đơn giản. Nhưng nếu yêu cầu:

- Retry từng file với backoff rõ ràng;
- Tổng hợp mọi lỗi và vẫn tiếp tục phần tử khác;
- Transaction, rollback hoặc tài nguyên liên quan nhiều bước;
- Phải đóng nhiều nguồn theo thứ tự phức tạp;
- Phải bảo đảm tất cả phần tử được xử lý, kể cả khi một phần tử lỗi;
- Cần báo tiến độ chính xác, xử lý hủy hoặc resource contention;

thì một vòng `for` thường đơn giản và minh bạch hơn:

```java
List<String> contents = new ArrayList<>();
for (Path path : paths) {
    contents.add(Files.readString(path, StandardCharsets.UTF_8));
}
```

Đây là **đoạn minh họa** nằm trong phương thức có `throws IOException`, cần `List`, `ArrayList`, `Path`, `Files` và `StandardCharsets`. Không cần wrapper unchecked vì vòng `for` cho phép phương thức khai báo `throws IOException` trực tiếp.

Không có yêu cầu rằng dùng Stream API sẽ nhanh hơn, gọn hơn hay đúng hơn trong mọi bài toán I/O. Chọn công cụ giúp **thể hiện chính xác hành vi lỗi và vòng đời tài nguyên**.

## 18. Bài tập thực hành

1. Viết lambda `path -> Files.readString(path)` trong `Stream.map` rồi biên dịch. Giải thích vì sao compiler yêu cầu xử lý checked exception.
2. Chạy `UncheckedIoPipelineDemo` và thêm `"gamma"` sau `"broken"`. Giải thích vì sao kết quả list thứ hai không được trả về khi lỗi xảy ra.
3. Tạo một phương thức `readUtf8Unchecked(Path)`, thêm message chứa tên file và kiểm tra `getCause()` vẫn là `IOException`.
4. Chạy `FileLinesDemo` trên Java 17 và bổ sung dòng `"  "`; so sánh `isBlank()` với `isEmpty()`.
5. Sửa `FileLinesDemo` để đọc một tệp không tồn tại; phân biệt lỗi xuất hiện lúc `Files.lines` với lỗi xuất hiện khi terminal operation duyệt source đã mở.
6. Viết một chương trình `Files.list(directory)` có `try-with-resources`, in tên file sau khi `sorted()`, rồi so sánh với việc không đóng stream.
7. Thực hành `BufferedReader.lines()` bên trong một `try (BufferedReader reader = ...)`; giải thích owner là reader hay stream trả về.
8. Chạy `ReadFilesWithStream`, thay `throw failure.getCause()` bằng `throw new IOException("Batch failed", failure)` và quan sát cause chain trong stack trace.
9. Viết adapter `IOFunction<T,R>`/ `unchecked`, dùng cho `Files.readString`, sau đó thêm unit test bảo đảm lỗi `IllegalArgumentException` không bị đổi thành `UncheckedIOException`.
10. Thiết kế một kiểu `Result<T>` chứa thành công hoặc `IOException` theo từng file. So sánh hành vi với pipeline fail-fast khi một trong mười tệp không đọc được.
11. Dùng `limit(1)` và `findFirst()` để chứng minh pipeline có thể không đọc mọi phần tử; giải thích tại sao không dùng `peek` cho I/O bắt buộc.
12. Đề xuất cách giới hạn đồng thời nếu cần kiểm tra 10.000 tệp nhưng chỉ được phép mở tối đa 16 tệp một lúc.

## 19. Tóm tắt

`UncheckedIOException` là cầu nối hợp lý giữa thế giới **I/O checked exceptions** và **Stream API/lambda không khai báo checked exceptions**. Nó giữ lại `IOException` gốc qua `getCause()` mà vẫn cho phép lỗi lan truyền qua `Function`, `Predicate`, `Consumer` hoặc các pipeline lazy.

Ba nguyên tắc quan trọng:

1. **Bọc đúng biên:** chỉ chuyển `IOException` sang `UncheckedIOException` khi cần, kèm ngữ cảnh hữu ích; tại API bên ngoài, chọn giữ unchecked hay chuyển lại checked theo hợp đồng.
2. **Nhớ tính lazy:** lỗi có thể xảy ra khi terminal operation chạy, không phải lúc pipeline được tạo; short-circuit và parallelism ảnh hưởng phần dữ liệu được xử lý.
3. **Giữ vòng đời resource:** `Files.lines`, `Files.list`, `Files.walk`, `Files.find` có thể mở tài nguyên cần đóng. `try-with-resources` bao quanh **toàn bộ thời gian tiêu thụ stream**; với `BufferedReader.lines()`, owner thường là reader mà caller đã mở.

Nếu một quy trình I/O cần báo cáo nhiều lỗi, retry, rollback hoặc quản lý resource phức tạp, hãy cân nhắc dùng vòng `for` hay một abstraction riêng. Mục tiêu là **đúng ngữ nghĩa dữ liệu, chính sách lỗi và ownership**, không phải sử dụng Stream API bằng mọi giá.

### Tài liệu tham khảo

- Java SE 17 API: [`UncheckedIOException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/UncheckedIOException.html), [`IOException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html).
- Java SE 17 API: [`Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html), [`BufferedReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html).
- Java SE 17 API: [`Stream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html), [`Function`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html), [`AutoCloseable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html).
