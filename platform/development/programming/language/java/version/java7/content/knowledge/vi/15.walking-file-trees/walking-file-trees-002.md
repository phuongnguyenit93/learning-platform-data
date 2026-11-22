# Đóng luồng duyệt và xử lý DirectoryIteratorException trong Java

**Chủ đề:** Java 7 — Duyệt cây tệp  
**Bài học:** Đóng luồng duyệt và xử lý `DirectoryIteratorException`  
**Yêu cầu thực hành:** Java 17+; các API NIO.2 giới thiệu từ Java 7 vẫn đang được sử dụng và không phải kỹ thuật legacy. Các ví dụ dùng thư mục tạm và dọn dữ liệu ở `finally`, đồng thời ưu tiên thông báo stdout độc lập với đường dẫn hệ điều hành.

## 1. Hai rủi ro khác nhau khi duyệt thư mục

Liệt kê các entry trong một thư mục là một tác vụ I/O, không chỉ là vòng lặp trên một `List<Path>` có sẵn. Có hai trách nhiệm phải được xử lý song song:

1. **Đóng tài nguyên đang mở:** `Files.newDirectoryStream(dir)` có thể mở và giữ một directory handle. Nếu không đóng sau khi duyệt, process có thể giữ tài nguyên không cần thiết, gây áp lực giới hạn handle và khiến các thao tác đổi tên/xóa thư mục gặp khó trên một số hệ điều hành.
2. **Phân biệt lỗi mở và lỗi lặp:** khi factory mở directory, lỗi có thể là checked `IOException`. Khi directory đã mở nhưng iterator gặp lỗi I/O **trong lúc duyệt**, nó ném unchecked `DirectoryIteratorException` với `IOException` gốc nằm trong `getCause()`.

Chỉ viết `catch (IOException)` không đủ cho lỗi của iterator. Chỉ viết `catch (DirectoryIteratorException)` không đủ cho lỗi khi mở directory. Và bắt lỗi chính xác nhưng không `close` vẫn là thiết kế có rủi ro resource leak.

Mẫu quan trọng nhất:

```java
Path dir = Path.of("documents");

try (DirectoryStream<Path> stream =
         Files.newDirectoryStream(dir)) {
    for (Path entry : stream) {
        System.out.println(entry.getFileName());
    }
} catch (DirectoryIteratorException ex) {
    throw ex.getCause();
}
```

Đây là **snippet trong một method** khai báo `throws IOException`, có các import `Path`, `Files`, `DirectoryStream`, `DirectoryIteratorException`, `IOException`. Nó không tự tạo thư mục `documents`. Với `try-with-resources` (TWR), directory stream được đóng ngay cả khi xử lý gặp lỗi. Khi một iterator I/O error được bọc trong `DirectoryIteratorException`, catch chuyển lại thành checked `IOException` theo contract của method.

**Giá trị cốt lõi:** xử lý đúng *lifecycle* và giữ đúng *bản chất nguyên nhân lỗi*.

## 2. DirectoryStream là gì?

`java.nio.file.DirectoryStream<T>` là một interface extends `Closeable` và `Iterable<T>`. Trường hợp dùng nhiều nhất là `DirectoryStream<Path>` để đọc **các entry trực tiếp** bên trong một directory.

Các factory của `Files`:

```java
// Duyệt tất cả entry trực tiếp:
DirectoryStream<Path> entries =
        Files.newDirectoryStream(dir);

// Lọc theo glob ở tên file:
DirectoryStream<Path> textFiles =
        Files.newDirectoryStream(dir, "*.txt");

// Lọc theo logic tùy chỉnh:
DirectoryStream<Path> regular =
        Files.newDirectoryStream(
            dir, path -> Files.isRegularFile(path));
```

Đây là các **đoạn minh họa**, không phải chương trình độc lập. Mỗi `DirectoryStream` được mở phải được đóng đúng ownership; không tạo nhiều stream như trên rồi bỏ mặc.

Những tính chất đáng nhớ:

| Tính chất | Hành vi |
| --- | --- |
| Thời điểm mở | `Files.newDirectoryStream` trả về một stream đã mở, có thể giữ tài nguyên |
| Đóng | `close()` hoặc TWR; xử lý resource ở cuối scope |
| Lặp qua entries | `for (Path entry : stream)` nhờ `Iterable` |
| Số iterator | **Một iterator duy nhất** trên mỗi `DirectoryStream` |
| Thứ tự | Không có thứ tự entry được bảo đảm |
| Tính nhất quán | **Weakly consistent**; directory có thể thay đổi trong lúc duyệt |
| Độ sâu | Liệt kê **một cấp**, không tự đệ quy |
| Lỗi I/O trong lúc lặp | `DirectoryIteratorException` có `IOException` làm cause |
| Sự tồn tại của mỗi entry | Một `Path` được liệt kê có thể bị xóa/sửa ngay sau đó |

Không nhầm `DirectoryStream<Path>` với `java.util.stream.Stream<Path>`. Chúng có tên giống nhau nhưng **khác interface, cách sử dụng và exception behavior**.

### 2.1. Khác với List<Path>

Một `List<Path>` đã được thu thập vào memory thường không giữ directory handle và có thể dùng nhiều iterator. Trong khi đó, `DirectoryStream` đang gắn với filesystem:

- Nó chỉ cho phép gọi `iterator()` thành công **một lần**.
- Một lần `hasNext()` tiếp theo có thể làm I/O và ném `DirectoryIteratorException`.
- Không nên trả iterator của stream ra khỏi scope đã đóng.
- Không phải snapshot toàn diện của directory, kể cả khi bạn đọc toàn bộ entries không lỗi.

Nếu application chỉ cần một danh sách tên file nhỏ/vừa, có thể thu thập `List<String>` trong TWR rồi **trả bản sao bất biến** ra ngoài. Nếu cần streaming thực sự qua nhiều tầng, API phải nói rõ **caller chịu trách nhiệm close** và giới hạn vòng đời.

## 3. Đóng đúng với try-with-resources

`DirectoryStream` extends `Closeable`, nên có thể dùng trực tiếp:

```java
try (DirectoryStream<Path> stream =
         Files.newDirectoryStream(dir)) {
    for (Path entry : stream) {
        process(entry);
    }
}
```

Đây là snippet trong method đã xử lý `IOException` và có hàm `process` do ứng dụng cung cấp.

**TWR đóng stream khi:**

- Lặp xong toàn bộ entries.
- Có `break` vì đã tìm thấy file.
- Có `return` từ method.
- Iterator ném `DirectoryIteratorException`.
- `process` ném exception riêng.
- Bất kỳ exception nào làm thoát thân `try`.

`DirectoryStream.close()` có thể ném `IOException`. TWR có quy tắc bảo toàn lỗi chính và **suppressed exceptions** để lỗi cleanup không tự che lỗi body. Phần 8 sẽ minh họa bằng test có kiểm soát.

### 3.1. Không trả iterator ra khỏi scope đã đóng

Đoạn sau có vấn đề:

```java
Iterator<Path> broken(Path dir) throws IOException {
    try (DirectoryStream<Path> stream =
            Files.newDirectoryStream(dir)) {
        return stream.iterator();
    }
}
```

Đây là method minh họa lỗi, không phải chương trình chạy độc lập. Khi caller nhận iterator, `stream` **đã đóng**. Iterator từng read-ahead có thể trả thêm một vài entry, nhưng không có bảo đảm cho phép dùng như một traversal còn mở.

Nếu cần trả lazy resource, thiết kế kiểu `AutoCloseable` có ownership rõ và caller dùng trong TWR. Nếu chỉ cần kết quả hữu hạn, thu thập rồi trả `List` sau khi đóng.

### 3.2. Break không làm mất cleanup

```java
Path first = null;

try (DirectoryStream<Path> stream =
        Files.newDirectoryStream(dir, "*.csv")) {
    for (Path entry : stream) {
        first = entry;
        break;
    }
}
```

Đây là snippet. Dù ngừng ở entry đầu tiên, TWR vẫn gọi `close()`. Không cần đọc đến hết directory để tài nguyên được đóng.

### 3.3. Ví dụ runnable: chỉ một iterator, đóng đúng scope

Tạo `DirectoryStreamLifecycleDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class DirectoryStreamLifecycleDemo {
    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("ds-life-");
        Path a = dir.resolve("a.txt");
        Path b = dir.resolve("b.txt");
        Path other = dir.resolve("skip.log");

        try {
            Files.writeString(a, "A", StandardCharsets.UTF_8);
            Files.writeString(b, "B", StandardCharsets.UTF_8);
            Files.writeString(
                    other, "X", StandardCharsets.UTF_8);

            DirectoryStream<Path> opened =
                    Files.newDirectoryStream(dir, "*.txt");

            try (opened) {
                List<String> names = new ArrayList<>();
                for (Path entry : opened) {
                    names.add(entry.getFileName().toString());
                }
                Collections.sort(names);
                System.out.println("txt=" + names);

                try {
                    opened.iterator();
                    System.out.println("unexpected-second");
                } catch (IllegalStateException ex) {
                    System.out.println(
                            "second-iterator-rejected=true");
                }
            }

            try {
                opened.iterator();
                System.out.println("unexpected-after-close");
            } catch (IllegalStateException ex) {
                System.out.println(
                        "closed-iterator-rejected=true");
            }
        } finally {
            Files.deleteIfExists(a);
            Files.deleteIfExists(b);
            Files.deleteIfExists(other);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all DirectoryStreamLifecycleDemo.java
java DirectoryStreamLifecycleDemo
```

**stdout chính xác:**

```text
txt=[a.txt, b.txt]
second-iterator-rejected=true
closed-iterator-rejected=true
```

Vì directory không cam kết thứ tự entry, ví dụ **sort** tên trước khi in. `try (opened)` dùng một biến effectively final đã được khai báo, cú pháp hợp lệ từ Java 9. Nếu dùng Java 7, cần khai báo resource trong dấu ngoặc TWR.

**Chú ý:** việc gọi `iterator()` lần thứ hai ném `IllegalStateException` là lỗi về **hợp đồng iterator**, không phải lỗi I/O. `DirectoryIteratorException` lại cho thấy một lỗi I/O phát sinh trong quá trình lặp. Hai exception này không thay thế nhau.

## 4. Phân biệt IOException và DirectoryIteratorException

Bảng điều hướng khi ứng dụng gặp lỗi:

| Bước thực thi | Ví dụ | Kiểu lỗi cần chuẩn bị |
| --- | --- | --- |
| Mở directory | `Files.newDirectoryStream(dir)` | `IOException` checked; có thể là `NotDirectoryException`, `NoSuchFileException`... |
| Lấy iterator thứ hai | `stream.iterator()` | `IllegalStateException` |
| Lấy iterator của stream đã đóng | `stream.iterator()` | `IllegalStateException` |
| Đang tìm entry tiếp theo | `iterator.hasNext()`/`next()` | `DirectoryIteratorException` bao `IOException` |
| Filter gọi thao tác I/O thất bại | `filter.accept(path)` ném `IOException` | Iterator bọc vào `DirectoryIteratorException` |
| Đọc nội dung của một entry | `Files.readString(path, UTF_8)` | `IOException` **của operation đọc file**, không tự thành DIEx |
| Đóng directory stream | `stream.close()` | `IOException` hoặc suppressed khi body có lỗi chính |

**Tại sao DIEx là unchecked?** `java.util.Iterator` khai báo `hasNext()` và `next()` mà không khai báo checked `throws IOException`. Khi việc lấy entry cần I/O và thất bại, NIO.2 phải truyền lỗi theo một loại exception phù hợp giao diện iterator: `DirectoryIteratorException` extends `ConcurrentModificationException`, là unchecked exception.

**Không vì vậy mà cho rằng directory đã bị concurrent modification.** Dù DIEx có superclass `ConcurrentModificationException`, mục đích của nó ở đây là biểu diễn lỗi I/O trong lúc duyệt; hãy xem `getCause()`.

### 4.1. Mẫu chuyển lỗi iterator về checked IOException

```java
static List<Path> collect(Path dir)
        throws IOException {
    List<Path> found = new ArrayList<>();

    try (DirectoryStream<Path> stream =
            Files.newDirectoryStream(dir)) {
        for (Path file : stream) {
            found.add(file);
        }
    } catch (DirectoryIteratorException ex) {
        throw ex.getCause();
    }

    return found;
}
```

Đây là method minh họa, cần import `ArrayList`, `List`, `Path`, `Files`, `DirectoryStream`, `DirectoryIteratorException` và `IOException`. `DirectoryIteratorException.getCause()` được khai báo trả về **`IOException`**, nên có thể ném lại trong method `throws IOException`.

Nếu mở directory lỗi ngay, checked `IOException` đã propagate tự nhiên. Nếu iterator lỗi, TWR đóng resource rồi catch chuyển lỗi về đúng kiểu checked.

**Không dùng `catch(Exception ex) { return List.of(); }`**. Một directory bị lỗi khi duyệt **không đồng nghĩa directory rỗng**. Với backup, indexing và audit, trả một danh sách rỗng có thể làm hỏng kết quả nghiệp vụ.

### 4.2. Ví dụ runnable: lỗi ngay lúc mở

Tạo `DirectoryOpenFailureDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class DirectoryOpenFailureDemo {
    public static void main(String[] args)
            throws IOException {
        Path file = Files.createTempFile(
                "not-a-directory-", ".txt");

        try {
            Files.writeString(
                    file, "content", StandardCharsets.UTF_8);

            try (DirectoryStream<Path> opened =
                    Files.newDirectoryStream(file)) {
                System.out.println(
                        "unexpected-open="
                        + opened.iterator().hasNext());
            } catch (IOException ex) {
                System.out.println(
                        "open-failed-as-io=true");
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all DirectoryOpenFailureDemo.java
java DirectoryOpenFailureDemo
```

```text
open-failed-as-io=true
```

Chương trình dùng một **tệp thường** làm đối số yêu cầu mở **directory**. Operation thất bại ngay khi gọi factory, nên bắt được `IOException`. Ví dụ không hard-code subtype ngoại lệ vì provider có thể báo chi tiết khác nhau. Phần thân `try` có tham chiếu resource để `-Xlint:all` không cảnh báo một biến bị bỏ qua.

## 5. DirectoryIteratorException trong lúc lặp

`DirectoryIteratorException` là exception có `IOException` gốc:

```java
try (DirectoryStream<Path> stream =
        Files.newDirectoryStream(dir)) {
    for (Path entry : stream) {
        process(entry);
    }
} catch (DirectoryIteratorException ex) {
    IOException underlying = ex.getCause();
    throw underlying;
}
```

Đây là snippet trong một method `throws IOException`. Lỗi gốc có thể là disk I/O, sự thay đổi của directory, quyền truy cập, filter đọc metadata thất bại hoặc vấn đề provider khác.

Đừng phân loại mọi exception phát sinh trong thân `for` là DIEx:

```java
for (Path entry : stream) {
    String data = Files.readString(
            entry, StandardCharsets.UTF_8);
    validate(data);
}
```

Ở đây có thể có:

- `DirectoryIteratorException` khi iterator không lấy được entry.
- Checked `IOException` trực tiếp khi `Files.readString` đọc nội dung file thất bại.
- Lỗi domain như `IllegalArgumentException` từ `validate`.

Cách xử lý có thể khác: một file hỏng có thể được ghi nhận và tiếp tục nếu chính sách cho phép, còn **iterator directory bị lỗi** có thể khiến việc quét chưa đầy đủ và phải dừng/báo thất bại.

### 5.1. Lỗi filter cũng được bọc

`Files.newDirectoryStream(dir, filter)` nhận một `DirectoryStream.Filter<Path>`, có method:

```java
boolean accept(Path entry) throws IOException;
```

Vì filter có thể gọi I/O như `Files.size(entry)` hoặc `Files.readAttributes(entry, ...)`, lỗi `IOException` từ `accept` sẽ được iterator chuyển thành `DirectoryIteratorException`. Nếu filter ném một `RuntimeException` khác, nó có thể được propagate nguyên dạng.

**Kiểm thử lỗi I/O đáng tin:** thay vì thay permission thư mục hoặc xóa entry đúng một thời điểm (dễ khác nhau giữa Windows/Linux), có thể dùng filter **cố ý ném IOException**. Đó là một failure injection hợp lệ theo JavaDoc.

### 5.2. Ví dụ runnable: filter ném IOException và chuyển lại kiểu checked

Tạo `DirectoryFilterFailureDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryIteratorException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class DirectoryFilterFailureDemo {
    static void translate(Path dir) throws IOException {
        try (DirectoryStream<Path> stream =
                Files.newDirectoryStream(
                    dir, entry -> {
                        throw new IOException("filter-io");
                    })) {
            for (Path ignored : stream) {
                System.out.println("unreachable");
            }
        } catch (DirectoryIteratorException ex) {
            throw ex.getCause();
        }
    }

    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("filter-io-");
        Path entry = dir.resolve("entry.txt");

        try {
            Files.writeString(
                    entry, "x", StandardCharsets.UTF_8);

            try (DirectoryStream<Path> stream =
                    Files.newDirectoryStream(
                        dir, path -> {
                            throw new IOException("filter-io");
                        })) {
                for (Path ignored : stream) {
                    System.out.println("unreachable");
                }
            } catch (DirectoryIteratorException ex) {
                System.out.println(
                        "iterator-wrapped=true");
                System.out.println(
                        "cause=" + ex.getCause().getMessage());
            }

            try {
                translate(dir);
            } catch (IOException ex) {
                System.out.println(
                        "translated=" + ex.getMessage());
            }
        } finally {
            Files.deleteIfExists(entry);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all DirectoryFilterFailureDemo.java
java DirectoryFilterFailureDemo
```

```text
iterator-wrapped=true
cause=filter-io
translated=filter-io
```

Đây là **mô phỏng lỗi có chủ đích**, không phải pattern filter production. Directory có đúng một entry; filter chắc chắn được gọi khi duyệt. Lần đầu in lớp bao và cause; lần thứ hai `translate` ném lại `IOException` để một method public có thể dùng cùng contract checked. Cả hai lần TWR đóng stream.

**Quan trọng:** DIEx xuất phát từ **quá trình lấy entry**, không phải từ việc tạo `Path` hay gọi `toString()` trên tên. Khi xảy ra lỗi, không giả định có thể tiếp tục đọc iterator còn lại đúng và đủ.

## 6. Read-ahead, một iterator và trạng thái sau close

JavaDoc `DirectoryStream` có những bảo đảm không hiển nhiên:

- Iterator có **read-ahead** ít nhất một entry ở `hasNext()`.
- Nếu `hasNext()` trả `true` và ngay sau đó gọi `next()`, `next()` không bị lỗi I/O hoặc lỗi do stream đóng cho entry đã đọc trước.
- Lỗi ở lần `hasNext()` tiếp theo vẫn có thể xảy ra. Vì vậy phải đặt catch quanh **toàn bộ traversal**.
- Sau `close()`, iterator **đã lấy trước đó** có thể tiếp tục trả một số entry đã đệm. Khi hết buffer, `hasNext()` trả false và `next()` ném `NoSuchElementException`.
- Gọi `stream.iterator()` lần thứ hai (hoặc sau close) ném `IllegalStateException`.
- Iterator là weakly consistent, nên kết quả có thể phản ánh một số thay đổi trong directory khi traversal đang chạy.

**Không dựa vào read-ahead như cách tiếp tục sử dụng stream đã đóng.** Số entry đệm không được API cam kết, có thể khác nhau giữa providers. Một service dùng `return stream.iterator()` ở bên trong TWR có lỗi lifecycle cho dù thỉnh thoảng vẫn đọc được vài entry.

**Không lấy thứ tự traversal làm thứ tự tạo file** hoặc thứ tự alphabet. Khi cần order cố định, materialize rồi sort.

### 6.1. Một API không thể bị lặp hai lần

`DirectoryStream` extends `Iterable` nhưng không giống collection:

```java
try (DirectoryStream<Path> stream =
        Files.newDirectoryStream(dir)) {
    for (Path file : stream) {
        process(file);
    }
    // Lượt thứ hai không hợp lệ trên cùng stream:
    for (Path file : stream) {
        processAgain(file);
    }
}
```

Đây là snippet minh họa lỗi (cần `process`/`processAgain`). Nếu cần hai lượt, hãy mở lại stream cho lượt hai hoặc thu thập snapshot sau lượt một. Mở lại stream có thể thấy trạng thái khác vì directory không bị khóa như snapshot.

## 7. Error policy: dừng, chuyển lỗi hay cho phép partial?

Một hệ thống duyệt file cần xác định chính sách từ đầu:

| Tình huống | Hành vi thường hợp lý |
| --- | --- |
| Directory không mở được | Fail operation, có context về directory và cause |
| Iterator không đọc được entry kế tiếp | Fail hoặc trả kết quả partial được đánh dấu rõ; **không** báo full success |
| Một entry không đọc được nội dung | Theo nghiệp vụ: fail-fast hoặc record per-file error, nhưng đừng che giấu |
| Filter trả false | Bỏ qua một entry theo chủ đích |
| Filter ném IOException | Bắt DIEx/cause và báo lỗi, không đồng nhất với “không match” |
| Close IOException | Không nuốt im lặng; cần log/propagate tùy primary/suppressed |
| Entry bị xóa giữa lúc list và read | Xử lý file I/O fail riêng; không coi việc list Path là bảo đảm file tồn tại |

Ví dụ application quét thư mục làm backup: sau khi đã xử lý 100 tệp, iterator lỗi ở tệp tiếp theo. Không thể khẳng định backup hoàn chỉnh. Có thể cần trả `PARTIAL` với danh sách đã xử lý và lỗi, hoặc xóa staging để fail toàn bộ.

Một web UI đơn giản liệt kê tên file có thể chấp nhận “partial + cảnh báo”, nhưng phải **hiển thị rằng danh sách chưa đầy đủ**, không vờ directory chỉ có từng ấy file.

### 7.1. Bắt ở đâu?

`try-with-resources` bảo đảm cleanup trước khi exception đến `catch` bên ngoài:

```java
try (DirectoryStream<Path> stream =
        Files.newDirectoryStream(dir)) {
    for (Path entry : stream) {
        process(entry);
    }
} catch (DirectoryIteratorException ex) {
    // Thời điểm này stream đã được đóng hoặc đã thử đóng.
    throw ex.getCause();
}
```

Nếu cần giữ **toàn bộ exception chain**, có thể wrap DIEx thay vì chỉ ném cause:

```java
try (DirectoryStream<Path> stream =
        Files.newDirectoryStream(dir)) {
    for (Path entry : stream) {
        process(entry);
    }
} catch (DirectoryIteratorException ex) {
    throw new IllegalStateException(
            "Failed listing " + dir, ex);
}
```

Đây đều là snippets. Hướng thứ nhất giữ API checked `throws IOException`. Hướng thứ hai giữ DIEx trong cause chain nhưng đổi API thành unchecked error. Chọn theo contract; không tùy tiện sửa loại lỗi chỉ để ẩn vấn đề.

## 8. Suppressed exceptions khi close cũng thất bại

`DirectoryStream.close()` có thể ném `IOException`. Với TWR, nếu:

- Thân `try` ném `DirectoryIteratorException` (lỗi iterator chính).
- `close()` sau đó ném `IOException` (lỗi cleanup bổ sung).

thì **lỗi iterator vẫn là primary**; lỗi close nằm trong `getSuppressed()` của primary.

**Phân biệt cause và suppressed:**

- `DirectoryIteratorException.getCause()` trả lỗi `IOException` đã làm iterator thất bại.
- `DirectoryIteratorException.getSuppressed()` có thể chứa các lỗi thêm khi đóng resource.
- Nếu thân `try` chạy thành công nhưng close thất bại, close exception có thể trở thành primary.

Không dễ tạo một lỗi close thực tế lặp lại ổn định trên tất cả OS. Ví dụ dưới đây tạo một `DirectoryStream` giả lập có chủ đích để xác minh hợp đồng TWR và exception.

### 8.1. Ví dụ runnable: primary từ iterator, suppressed từ close

Tạo `SuppressedDirectoryFailureDemo.java`:

```java
import java.io.IOException;
import java.nio.file.DirectoryIteratorException;
import java.nio.file.DirectoryStream;
import java.nio.file.Path;
import java.util.Iterator;
import java.util.NoSuchElementException;

public class SuppressedDirectoryFailureDemo {
    static final class FailingStream
            implements DirectoryStream<Path> {

        @Override
        public Iterator<Path> iterator() {
            return new Iterator<>() {
                @Override
                public boolean hasNext() {
                    throw new DirectoryIteratorException(
                            new IOException("iteration-io"));
                }

                @Override
                public Path next() {
                    throw new NoSuchElementException();
                }
            };
        }

        @Override
        public void close() throws IOException {
            throw new IOException("close-io");
        }
    }

    public static void main(String[] args) {
        try (FailingStream stream = new FailingStream()) {
            for (Path unused : stream) {
                System.out.println("unreachable");
            }
        } catch (DirectoryIteratorException ex) {
            System.out.println(
                    "primary=" + ex.getCause().getMessage());
            System.out.println(
                    "suppressed-count="
                    + ex.getSuppressed().length);
            System.out.println(
                    "suppressed-close="
                    + ex.getSuppressed()[0].getMessage());
        } catch (IOException ex) {
            System.out.println("unexpected-close-primary");
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all SuppressedDirectoryFailureDemo.java
java SuppressedDirectoryFailureDemo
```

```text
primary=iteration-io
suppressed-count=1
suppressed-close=close-io
```

Đây là test **injected failures**, không phải cách cài đặt DirectoryStream thật trong production. Nó cho thấy vì sao TWR đáng dùng hơn một `finally` gọi close tùy tiện (có thể che lỗi body nếu không giữ suppression đúng).

**Lưu ý khi `throw ex.getCause()`:** suppressed exceptions gắn trên DIEx **không tự chuyển** lên đối tượng `IOException` gốc được ném lại. Với hệ thống cần forensic details, hãy log toàn bộ DIEx hoặc duy trì chain phù hợp. Đừng chỉ in `cause.getMessage()` rồi loại bỏ stacktrace và suppressed cleanup error.

## 9. Files.list và Files.walk: Stream cũng phải đóng

Với Java 8+ và đặc biệt Java 17+, còn các API trả `java.util.stream.Stream<Path>`:

- `Files.list(dir)`: chỉ các entry trực tiếp của thư mục, **không recursive**.
- `Files.walk(root)`: traversal **depth-first** qua cây file, có overload giới hạn `maxDepth`.
- `Files.find(root, maxDepth, matcher, options...)`: duyệt có matcher dùng thuộc tính file.

Những stream này có thể giữ tài nguyên của directory. Khác stream từ `List.of(...).stream()`, chúng **cần close**, thường bằng TWR, dù terminal operation đã chạy xong hoặc dừng sớm.

**Lỗi I/O phải xử lý khác:**

| API | Kiểu trả về | Lỗi mở | Lỗi I/O lúc đang tiêu thụ | Đóng |
| --- | --- | --- | --- | --- |
| `Files.newDirectoryStream` | `DirectoryStream<Path>` | `IOException` | `DirectoryIteratorException` | TWR trên DirectoryStream |
| `Files.list` | `Stream<Path>` | `IOException` | `UncheckedIOException` | TWR trên Stream |
| `Files.walk` | `Stream<Path>` | `IOException` | `UncheckedIOException` | TWR trên Stream |
| `Files.find` | `Stream<Path>` | `IOException` | `UncheckedIOException` | TWR trên Stream |
| `Files.walkFileTree` | `Path` | `IOException` | Checked IOException/visitor policy | Method tự quản lý traversal |

**Không bắt `DirectoryIteratorException` để xử lý mặc định một pipeline `Files.walk`**. Theo API, lỗi I/O phát sinh sau khi stream được trả thường được bọc thành `UncheckedIOException`. Và không coi mọi `RuntimeException` từ stream là I/O: filter/mapper do ứng dụng viết cũng có thể ném lỗi logic.

### 9.1. Ví dụ runnable: Files.list khác Files.walk

Tạo `FilesStreamTraversalDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public class FilesStreamTraversalDemo {
    static String portable(Path path) {
        return path.toString().replace('\\', '/');
    }

    public static void main(String[] args)
            throws IOException {
        Path root =
                Files.createTempDirectory("list-walk-");
        Path nested = root.resolve("nested");
        Path a = root.resolve("alpha.txt");
        Path child = nested.resolve("child.txt");

        try {
            Files.createDirectory(nested);
            Files.writeString(
                    a, "a", StandardCharsets.UTF_8);
            Files.writeString(
                    child, "b", StandardCharsets.UTF_8);

            List<String> top;
            try (Stream<Path> entries = Files.list(root)) {
                top = entries
                        .map(p -> p.getFileName().toString())
                        .sorted()
                        .toList();
            }

            List<String> allFiles;
            try (Stream<Path> entries = Files.walk(root)) {
                allFiles = entries
                        .filter(Files::isRegularFile)
                        .map(root::relativize)
                        .map(FilesStreamTraversalDemo::portable)
                        .sorted()
                        .toList();
            }

            System.out.println("list=" + top);
            System.out.println("walk-files=" + allFiles);
        } finally {
            Files.deleteIfExists(child);
            Files.deleteIfExists(a);
            Files.deleteIfExists(nested);
            Files.deleteIfExists(root);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all FilesStreamTraversalDemo.java
java FilesStreamTraversalDemo
```

```text
list=[alpha.txt, nested]
walk-files=[alpha.txt, nested/child.txt]
```

Cả hai stream được đóng đúng scope. `Files.list` trả entries trực tiếp gồm directory `nested`, còn `Files.walk` đi xuống lấy thêm `nested/child.txt`; filter chỉ giữ file thường. Các tên được sort, và dấu phân tách được thay đổi **chỉ cho phần in stdout**.

### 9.2. Chuyển UncheckedIOException về checked IOException

Ví dụ method phục vụ API `throws IOException`:

```java
static List<Path> sortedEntries(Path dir)
        throws IOException {
    try (Stream<Path> paths = Files.list(dir)) {
        return paths.sorted().toList();
    } catch (UncheckedIOException ex) {
        throw ex.getCause();
    }
}
```

Đây là **method minh họa** với import `List`, `Path`, `Files`, `Stream`, `IOException`, `UncheckedIOException`. Lỗi lúc mở `Files.list` vốn là checked `IOException` và tự propagate; lỗi trong terminal pipeline có thể là `UncheckedIOException`.

**Cần hiểu lazy evaluation:** chỉ tạo `Stream<Path>` hoặc chỉ gọi `filter`/`map` không làm thao tác duyệt hoàn thành. Khi terminal operation thực thi trong phạm vi TWR, directory resource vẫn mở và được đóng ngay sau đó.

**Không làm:**

```java
// Anti-pattern:
Stream<Path> paths = Files.walk(root);
List<Path> data = paths.toList();
// Terminal operation không thay thế trách nhiệm close.
```

Ngay cả khi đã lấy `toList()`, code đúng cần `try(Stream<Path> paths = Files.walk(root))` để đóng nguồn I/O.

## 10. Files.walkFileTree: visitor quản lý cây và checked errors

`Files.walkFileTree` có hợp đồng khác `Files.walk`. Nó thực hiện traversal đồng bộ và gọi `FileVisitor<Path>`. Thường dùng `SimpleFileVisitor<Path>` với callbacks:

- `preVisitDirectory(dir, attrs)`: bắt đầu duyệt directory.
- `visitFile(file, attrs)`: thăm một file.
- `visitFileFailed(file, exc)`: không thể thăm/đọc thuộc tính.
- `postVisitDirectory(dir, exc)`: hoàn tất directory, `exc` có thể mang lỗi I/O khi traversal thư mục.

Mỗi callback trả `FileVisitResult` (`CONTINUE`, `SKIP_SUBTREE`, `SKIP_SIBLINGS` hoặc `TERMINATE` theo quy tắc tương ứng) hoặc ném exception phù hợp. `walkFileTree` tự quản lý các directory streams nội bộ; **không phải caller tự đóng một Stream trả về**, vì nó trả `Path` sau khi hoàn thành.

**Không bỏ qua `exc` ở `postVisitDirectory`** nếu ứng dụng yêu cầu kết quả hoàn chỉnh. Lỗi iterator khi đi qua một directory có thể được đưa tới visitor qua callback theo contract.

### 10.1. Ví dụ runnable: checked error và completion policy

Tạo `FileTreeVisitorDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.List;

public class FileTreeVisitorDemo {
    static String portable(Path path) {
        return path.toString().replace('\\', '/');
    }

    public static void main(String[] args)
            throws IOException {
        Path root =
                Files.createTempDirectory("visitor-");
        Path sub = root.resolve("nested");
        Path rootFile = root.resolve("root.txt");
        Path child = sub.resolve("child.txt");

        try {
            Files.createDirectory(sub);
            Files.writeString(
                    rootFile, "root", StandardCharsets.UTF_8);
            Files.writeString(
                    child, "child", StandardCharsets.UTF_8);

            List<String> visited = new ArrayList<>();
            Path returned = Files.walkFileTree(
                    root, new SimpleFileVisitor<>() {
                        @Override
                        public FileVisitResult visitFile(
                                Path file, BasicFileAttributes attrs) {
                            visited.add(portable(
                                    root.relativize(file)));
                            return FileVisitResult.CONTINUE;
                        }

                        @Override
                        public FileVisitResult visitFileFailed(
                                Path file, IOException exc)
                                throws IOException {
                            throw exc;
                        }

                        @Override
                        public FileVisitResult postVisitDirectory(
                                Path dir, IOException exc)
                                throws IOException {
                            if (exc != null) {
                                throw exc;
                            }
                            return FileVisitResult.CONTINUE;
                        }
                    });

            visited.sort(String::compareTo);
            System.out.println("files=" + visited);
            System.out.println(
                    "returned-root=" + returned.equals(root));

            try {
                Files.walkFileTree(
                        root, new SimpleFileVisitor<>() {
                            @Override
                            public FileVisitResult visitFile(
                                    Path file,
                                    BasicFileAttributes attrs)
                                    throws IOException {
                                throw new IOException("visitor-failure");
                            }
                        });
                System.out.println("unexpected-visitor-success");
            } catch (IOException ex) {
                System.out.println(
                        "visitor-error=" + ex.getMessage());
            }
        } finally {
            Files.deleteIfExists(child);
            Files.deleteIfExists(rootFile);
            Files.deleteIfExists(sub);
            Files.deleteIfExists(root);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all FileTreeVisitorDemo.java
java FileTreeVisitorDemo
```

```text
files=[nested/child.txt, root.txt]
returned-root=true
visitor-error=visitor-failure
```

Đây là ví dụ duyệt cây có xử lý `visitFileFailed` và `postVisitDirectory` minh bạch. Danh sách sau traversal được sort để không phụ thuộc thứ tự entry.

Nếu visitor chủ động ném `IOException`, `walkFileTree` truyền lỗi đó ra caller. Nếu chính directory traversal bị lỗi, visitor nhận thông tin qua cơ chế thích hợp và phải quyết định dừng hay ghi trạng thái partial.

**Không đồng nhất `Files.walkFileTree` với `Files.walk`:**

- `walkFileTree`: callbacks, checked errors, method quản lý traversal/lifecycle.
- `walk`: lazy `Stream<Path>`, cần TWR và có thể ném `UncheckedIOException` trong pipeline.

Khi cần logic phức tạp như bỏ qua subtree, giới hạn độ sâu, visitor error policy hay xử lý backup/indexing, `walkFileTree` thường là lựa chọn rõ ràng.

## 11. API service: không để một iterator sống sau close

Một API phục vụ UI hoặc service có thể trả kết quả bất biến:

```text
listTxtNames(Path dir) -> List<String> immutable

- Chỉ lấy file .txt trực tiếp trong directory.
- Đọc và đóng DirectoryStream hoàn toàn trong method.
- Có thể propagate IOException khi mở/duyệt/đóng.
- Sắp xếp kết quả để thống nhất thứ tự.
- Không trả iterator/stream còn phụ thuộc filesystem handle.
```

### 11.1. Ví dụ runnable: một service liệt kê tệp

Tạo `SafeDirectoryListingDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryIteratorException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public class SafeDirectoryListingDemo {
    static List<String> listTxtNames(Path dir)
            throws IOException {
        List<String> result = new ArrayList<>();

        try (DirectoryStream<Path> entries =
                Files.newDirectoryStream(dir, "*.txt")) {
            for (Path entry : entries) {
                if (Files.isRegularFile(entry)) {
                    result.add(
                        entry.getFileName().toString());
                }
            }
        } catch (DirectoryIteratorException ex) {
            throw ex.getCause();
        }

        result.sort(String::compareTo);
        return List.copyOf(result);
    }

    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("safe-list-");
        Path a = dir.resolve("alpha.txt");
        Path b = dir.resolve("beta.txt");
        Path log = dir.resolve("ignored.log");

        try {
            Files.writeString(a, "a", StandardCharsets.UTF_8);
            Files.writeString(b, "b", StandardCharsets.UTF_8);
            Files.writeString(
                    log, "log", StandardCharsets.UTF_8);

            List<String> names = listTxtNames(dir);
            System.out.println("names=" + names);
            System.out.println("count=" + names.size());

            try {
                names.add("other.txt");
                System.out.println("unexpected-mutable");
            } catch (UnsupportedOperationException ex) {
                System.out.println(
                        "immutable-result=true");
            }
        } finally {
            Files.deleteIfExists(a);
            Files.deleteIfExists(b);
            Files.deleteIfExists(log);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all SafeDirectoryListingDemo.java
java SafeDirectoryListingDemo
```

```text
names=[alpha.txt, beta.txt]
count=2
immutable-result=true
```

TWR đóng directory stream trước khi trả `List.copyOf(result)`. Caller có một collection bất biến theo interface, không giữ resource của traversal. Nếu iterator xảy ra I/O error, method ném `IOException` thay vì trả danh sách còn thiếu.

**Giới hạn quan trọng:** `Files.isRegularFile` có thể trả false nếu không đọc được attributes. Nếu yêu cầu backup/audit tuyệt đối không bỏ sót file, hãy dùng `Files.readAttributes` và xử lý lỗi cụ thể. Nếu có symbolic link, `isRegularFile` mặc định có thể follow link; policy bảo mật cần được xác định riêng.

## 12. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Mở DirectoryStream không close | Rò rỉ directory handle | Dùng TWR |
| Chỉ close khi vòng lặp kết thúc tự nhiên | `break`/exception để lại resource | TWR tự close mọi exit path |
| Chỉ catch `IOException` quanh for-each | Bỏ sót DIEx unchecked | Catch `DirectoryIteratorException` riêng |
| Bắt DIEx rồi trả `List.of()` | Đánh đồng lỗi quét với directory rỗng | Propagate/đánh dấu partial failure |
| Bắt `ConcurrentModificationException` chung | Dễ hiểu nhầm lỗi chỉ do concurrency | Bắt chính xác DIEx, xem cause |
| Gọi `iterator()` nhiều lần | `IllegalStateException` | Một iterator hoặc mở stream khác |
| Trả iterator trong TWR | Caller nhận iterator đã đóng | Trả snapshot hoặc chuyển ownership |
| Kỳ vọng iterator đã đóng luôn hết buffer | Read-ahead có thể còn entry | Không tiếp tục dùng sau close |
| Dựa vào thứ tự directory | Kết quả không ổn định | Sort khi cần |
| Dùng `DirectoryStream` để recursive traversal | Chỉ một cấp | `Files.walk`/`walkFileTree` |
| Dùng `Files.list` không TWR | Java Stream vẫn giữ directory handle | TWR trên Stream<Path> |
| Bắt DIEx cho `Files.walk` | Pipeline thường bọc trong UncheckedIOException | Catch `UncheckedIOException` |
| Nghĩ terminal `toList` auto-close IO stream | Không bảo đảm release đúng scope | TWR |
| Bỏ qua `postVisitDirectory(exc)` | Không báo traversal chưa hoàn chỉnh | Rethrow/ghi partial |
| Dùng `Files.isRegularFile` làm phép audit không lỗi | Có thể trả false khi inaccessible | `readAttributes` và xử lý IOException |
| Log mỗi `getCause().getMessage()` | Mất stacktrace/suppressed | Giữ exception chain khi cần |
| Unit test bằng chmod hoặc race timing | Không ổn định giữa OS | Injection bằng filter/fake stream |
| Không kiểm tra symlink/TOCTOU | Đọc/xóa ngoài root | Chính sách filesystem/permission rõ |
| Duyệt triệu file rồi `sorted().toList()` | Bộ nhớ tăng theo số entry | Streaming bounded hoặc thiết kế khác |

## 13. Bảo mật, resource limits và tính nhất quán

Đóng DirectoryStream đúng là điều kiện cần, **không phải sandbox hoặc authorization**. Khi duyệt thư mục do người dùng chọn:

- **Root tin cậy:** kiểm soát thư mục nào process được phép truy cập; không cho tên có `..`/absolute path tùy ý thoát khỏi scope.
- **Symlink và junction:** entry có thể trỏ ra ngoài root; `Files.isRegularFile` mặc định có thể follow symbolic links. Nếu policy yêu cầu không follow, dùng API với `LinkOption.NOFOLLOW_LINKS` và kiểm soát thao tác thực tế.
- **TOCTOU:** file có thể bị sửa/xóa/thay thành link giữa lúc list và lúc mở. Nếu cần hạn chế race, xem `SecureDirectoryStream` khi provider hỗ trợ, cùng policy dùng directory handle và quyền OS.
- **Weak consistency:** DirectoryStream không đóng băng directory. Retry có thể lặp lại entry cũ hoặc thấy entry mới. Định nghĩa idempotency nếu mỗi entry gây side effects.
- **Quota:** giới hạn độ sâu, số file, tổng byte và thời gian khi scan dữ liệu không đáng tin. `DirectoryStream` giúp duyệt lazy nhưng không giới hạn tổng công việc.
- **Partial result:** không trả `SUCCESS` nếu I/O error đã ngăn quét hết directory. Nếu chấp nhận partial, ghi rõ danh sách đã xử lý và lỗi.
- **Không giả định close sẽ ngắt ngay thread khác:** JavaDoc không yêu cầu DirectoryStream hỗ trợ asynchronous close; một thread đang block ở iterator có thể khiến close từ thread khác chờ.
- **Logging:** path/tên file có thể là dữ liệu nhạy cảm. Ghi nhận exception có kiểm soát, không lộ đường dẫn riêng tư trong response công khai.
- **Recursive resource usage:** không mở hàng trăm directory stream lồng nhau mà không có giới hạn và cleanup. Với cây lớn, `Files.walkFileTree` thường rõ hơn.

### 13.1. Khi dùng Stream, sorted có chi phí

`Files.list` và `Files.walk` lazy, nhưng pipeline `sorted().toList()` có thể cần giữ nhiều entry trong bộ nhớ. Nếu mục tiêu chỉ là xử lý lần lượt một tập file lớn, cân nhắc `forEach` trong TWR hoặc visitor, với cách thu thập errors phù hợp. **Streaming và đóng đúng** không tự giúp throughput vô hạn: I/O bandwidth, giới hạn handle, filesystem latency và CPU còn tác động.

## 14. Checklist code review

1. `Files.newDirectoryStream` có được đặt trong TWR không?
2. Có thể `break`, `return` hoặc ném exception giữa loop không? TWR vẫn bảo vệ chứ?
3. Lỗi **khi mở** và lỗi **trong iterator** được phân biệt chưa?
4. Có bắt `DirectoryIteratorException`, đọc `getCause()` và không che I/O error không?
5. Có hiểu `DirectoryIteratorException` extends `ConcurrentModificationException` nhưng là lỗi I/O không?
6. Filter có dùng `Files.size`/`readAttributes` và có thể ném IOException không?
7. Có nhầm IOException của operation trên entry với lỗi iterator không?
8. Có log/giữ suppressed close exception khi cần không?
9. Có gọi `iterator()` lần hai hoặc sử dụng iterator sau khi close không?
10. Có trả một lazy iterator từ method đã đóng stream không?
11. Đã xử lý thứ tự không bảo đảm, weak consistency và directory thay đổi chưa?
12. `Files.list`/`Files.walk` có TWR và xử lý `UncheckedIOException` không?
13. `Files.walkFileTree` có policy cho `visitFileFailed` và `postVisitDirectory(exc)` không?
14. Khi có lỗi giữa chừng, kết quả được đánh dấu `FAILED/PARTIAL` thay vì success chưa?
15. Có giới hạn số entry, memory, depth và operations không?
16. Có xem symlink, root boundary, permissions và TOCTOU chưa?
17. Unit tests có inject lỗi xác định thay vì phụ thuộc chmod/OS timing chưa?
18. Có giữ ranh giới đúng Java 17+ và dùng API hiện hành chứ không dựa vào chi tiết provider không?
19. Nếu service trả result sau TWR, result có hoàn chỉnh và không giữ resource không?
20. Có đảm bảo stream đóng trước khi dọn thư mục tạm trên Windows không?

## 15. Bài tập thực hành

**Bài 1 — Lifecycle.** Chạy `DirectoryStreamLifecycleDemo`. Bỏ TWR có thể dẫn đến rủi ro gì? Vì sao gọi iterator lần hai không giống lặp lại một `List`?

**Bài 2 — Lỗi mở.** Chạy `DirectoryOpenFailureDemo`. Thử trỏ tới đường dẫn chưa tồn tại; so sánh subtype IOException trả về trên filesystem của bạn.

**Bài 3 — Filter IOException.** Chạy `DirectoryFilterFailureDemo`. Chỉnh filter chỉ ném IOException khi gặp file tên `trigger.txt`. Giải thích vì sao không nên dự đoán thứ tự hay số file đã được xử lý trước lỗi.

**Bài 4 — Suppression.** Chạy `SuppressedDirectoryFailureDemo`. Thay fake stream để body không lỗi mà close ném IOException; quan sát lỗi primary. Thử dùng TWR với hai resources và giải thích thứ tự đóng ngược khai báo.

**Bài 5 — Stream traversal.** Chạy `FilesStreamTraversalDemo`; thêm thư mục con thứ hai. Viết code tìm file đầu tiên bằng `findFirst()` và vẫn đóng resource đúng TWR.

**Bài 6 — Visitor.** Chạy `FileTreeVisitorDemo`, thêm nhánh `visitFileFailed` ghi nhận lỗi rồi `CONTINUE`; so sánh khi nào partial result hợp lệ với khi nào cần abort.

**Bài 7 — Immutable result.** Chạy `SafeDirectoryListingDemo`, đổi danh sách result thành dữ liệu lớn và phân tích bộ nhớ. Vì sao không thể trả một iterator sau khi đóng DirectoryStream?

**Bài 8 — Failure policy.** Thiết kế backup cho 10.000 file. Nếu iteration thất bại ở file thứ 7.000, định nghĩa status, idempotent retry và cách xử lý side effects đã xảy ra.

**Bài 9 — Security.** Cho một entry là symlink ra ngoài root. Vì sao đúng `try-with-resources` không ngăn đọc file sai vùng? Đề xuất chính sách kiểm soát symlink/TOCTOU.

## 16. Ghi nhớ cuối bài

- **`DirectoryStream` cần close** bằng TWR, kể cả khi dừng lặp sớm hoặc có exception.
- **`Files.newDirectoryStream` lỗi khi mở** thường ném checked `IOException`.
- **Lỗi I/O khi iterator đọc entry** ném unchecked `DirectoryIteratorException`; đọc `getCause()` để lấy checked `IOException` gốc.
- **Filter.accept` có thể ném IOException**, và iterator sẽ bọc lỗi đó thành `DirectoryIteratorException` theo contract.
- **Một DirectoryStream chỉ có một iterator**, không có thứ tự entry bảo đảm và không phải snapshot directory.
- **TWR xử lý suppressed exceptions** khi iteration và close cùng lỗi. Đừng bỏ cause chain khi cần chẩn đoán.
- **`Files.list/walk/find` trả Stream<Path> cần close**, nhưng lỗi I/O trong pipeline thường là `UncheckedIOException`.
- **`Files.walkFileTree` quản lý traversal và callback checked errors**, phù hợp khi cần visitor policy trên cây.
- **Đóng tài nguyên không thay thế bảo mật/path validation**, nhất là symlink, TOCTOU, weak consistency và dữ liệu chưa duyệt hết.
- Các kiến thức trên **vẫn áp dụng với Java 17+**, không phải workaround lỗi thời.

## Tài liệu chính thức

- [DirectoryStream — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/DirectoryStream.html): vòng đời, single iterator, read-ahead và DirectoryIteratorException.
- [DirectoryIteratorException — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/DirectoryIteratorException.html): unchecked wrapper và IOException cause.
- [DirectoryStream.Filter — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/DirectoryStream.Filter.html): filter được phép ném IOException.
- [Files — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): newDirectoryStream, list, walk, find, walkFileTree.
- [Stream — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html): resource closure và stream lifecycle.
- [JLS `14.20.3 — Try-with-resources](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3): primary và suppressed exceptions.
