# Quyền sở hữu và thời điểm kết thúc tài nguyên với try-with-resources

**Chủ đề:** Java 7 — `try-with-resources`  
**Bài học:** Quyền sở hữu và thời điểm kết thúc tài nguyên  
**Phiên bản thực hành:** Java 17+ (các quy tắc cơ bản của `try-with-resources` đã có từ Java 7; cú pháp `try (existingVariable)` có từ Java 9).

## 1. Vấn đề cần giải quyết

Đọc tệp, mở socket, xử lý ZIP, làm việc với JDBC hay xử lý một stream gắn với tệp đều sử dụng **tài nguyên có vòng đời**. Bên cạnh việc thực hiện đúng thao tác, chương trình còn phải biết:

1. **Ai có trách nhiệm đóng?** Đối tượng có thể do phương thức hiện tại tạo, do caller cho mượn hoặc do framework/pool quản lý.
2. **Đóng lúc nào?** Sau thao tác bình thường, khi `return` sớm, khi exception xuất hiện hoặc khi khởi tạo tài nguyên tiếp theo thất bại.
3. **Nếu đóng thất bại thì sao?** Không được làm mất exception gốc hay coi giải phóng tài nguyên tương đương với việc commit dữ liệu.

`try-with-resources` (TWR) giúp tự động gọi `close()` cho những tài nguyên được đăng ký trong phần `try (...)`. Tuy nhiên, **TWR quyết định thời điểm đóng theo phạm vi; nó không tự quyết định ai thực sự sở hữu tài nguyên**. Trước khi viết TWR, phải xác định hợp đồng ownership.

## 2. Ba trạng thái ownership cần phân biệt

| Trạng thái | Ý nghĩa | Nguyên tắc đóng |
| --- | --- | --- |
| **Owned** (sở hữu) | Scope/method hiện tại tạo hoặc nhận trách nhiệm quản lý tài nguyên | Đóng bằng TWR sau khi sử dụng, hoặc chuyển giao ownership một cách rõ ràng |
| **Borrowed** (mượn) | Method được dùng resource do caller sở hữu, không nhận trách nhiệm kết thúc vòng đời | Không đóng; caller vẫn quản lý thời điểm đóng |
| **Transferred** (chuyển quyền) | Caller/factory bàn giao trách nhiệm đóng cho bên nhận | Bên nhận đóng; bên giao không còn dùng resource như thể nó còn hợp lệ |

Ví dụ:

- `Files.newBufferedReader(path)` được mở trong một method để trả ra `String`: method đó là **owner** của reader, nên đóng reader trước khi trả dữ liệu.
- `parse(BufferedReader reader)` nhận reader từ caller để đọc: nếu hợp đồng nói chỉ **borrow**, không tự đóng reader.
- `openStream(Path path)` trả về một `InputStream` đang mở: factory chuyển ownership cho **caller**, cần ghi rõ caller phải `close()`.
- `System.in` do process quản lý và còn được dùng ở nơi khác: helper chỉ **mượn**, không được đóng chỉ vì helper xử lý xong.
- `Connection` do pool cho mượn: code có thể sở hữu một **lượt mượn** và cần `close()` để trả connection về pool, nhưng không sở hữu cả pool.

**Quy tắc:** *Bên sở hữu đóng, bên mượn không tự đóng*. Tên `close()` trong API không trao quyền tự động cho mọi nơi cầm tham chiếu gọi nó. Quyền đóng phải đến từ thiết kế và tài liệu của API.

### 2.1. Một scope ngắn là một hợp đồng dễ kiểm chứng

Mở gần nơi dùng, xử lý xong thì đóng ngay giúp tránh rò rỉ và giảm thời gian giữ file handle, connection hay khóa. Đối với dữ liệu có thể vật hóa trong bộ nhớ, thường tốt hơn là **trả kết quả đã đọc** thay vì trả resource đang sống.

Nếu bắt buộc trả resource đang mở, hãy ghi rõ trong JavaDoc hoặc hợp đồng phương thức rằng **caller phải đóng**. Đừng vừa đặt resource trong TWR vừa trả chính resource đó ra ngoài; nó sẽ bị đóng **trước khi caller dùng**.

## 3. TWR quản lý vòng đời như thế nào?

Cú pháp minh họa (các tên class/hàm cần được định nghĩa trong ứng dụng):

```java
try (Reader reader = openReader()) {
    use(reader);
}
```

`Reader` triển khai `Closeable`, là subtype của `AutoCloseable`. Trình tự TWR:

1. Đánh giá biểu thức khởi tạo tài nguyên.
2. Nếu khởi tạo thành công, thực hiện thân `try`.
3. Khi rời thân `try`, **gọi `close()`** trước khi chuyển sang phần xử lý tiếp theo.
4. Việc đóng xảy ra ngay cả khi thân `try` ném exception, `return`, `break` hoặc `continue`.
5. Nếu TWR có `catch`/`finally`, quá trình đóng tài nguyên đã diễn ra **trước khi** chạy các block đó.

TWR không cần chờ garbage collector. Việc tài nguyên bị mất tham chiếu hoặc đối tượng Java được thu hồi **không phải chiến lược đóng handle**.

### 3.1. Nhiều tài nguyên

Khi có nhiều resource:

```java
try (Connection connection = openConnection();
     Statement statement = connection.createStatement();
     ResultSet rows = statement.executeQuery("SELECT 1")) {
    // Sử dụng rows.
}
```

Đây là **mã minh họa JDBC**; không thể chạy độc lập nếu thiếu DB connection và import. Thứ tự **khởi tạo từ trái sang phải**: `connection` → `statement` → `rows`. Thứ tự **đóng từ phải sang trái**: `rows` → `statement` → `connection`.

```text
open A -> open B -> body -> close B -> close A -> đi tiếp
```

**Lý do thiết kế:** resource phụ thuộc nên được kết thúc trước resource nền mà nó dựa vào. TWR xử lý đúng thứ tự cho những resource được khai báo trong cùng câu lệnh.

### 3.2. Ví dụ đầy đủ: đóng ngược và đóng trước return

Tạo `ResourceOrderDemo.java`:

```java
public class ResourceOrderDemo {
    static final class Tracked implements AutoCloseable {
        private final String name;

        Tracked(String name) {
            this.name = name;
            System.out.println("open:" + name);
        }

        @Override
        public void close() {
            System.out.println("close:" + name);
        }
    }

    static int calculate() {
        try (Tracked early = new Tracked("early")) {
            System.out.println("returning");
            return 7;
        }
    }

    public static void main(String[] args) {
        try (Tracked first = new Tracked("first");
             Tracked second = new Tracked("second")) {
            System.out.println("body");
        }

        System.out.println("after");
        System.out.println("result=" + calculate());
    }
}
```

```bash
javac -encoding UTF-8 ResourceOrderDemo.java
java ResourceOrderDemo
```

**stdout chính xác:**

```text
open:first
open:second
body
close:second
close:first
after
open:early
returning
close:early
result=7
```

Chú ý `calculate()`: biểu thức `return 7` đã được tính nhưng `early.close()` chạy **trước** khi caller nhận kết quả `7`. Do đó `close:early` xuất hiện trước `result=7`. Nếu `close()` ném exception, lệnh return đang chờ có thể bị thay bằng việc ném exception: không thể giả định có `return` thì hoàn toàn bỏ qua lỗi đóng.

Trong ví dụ này, các resource được tạo **chỉ để ghi lại thứ tự close** nên không cần gọi method nghiệp vụ trên chúng trong thân `try`. Khi bật mọi tùy chọn `javac -Xlint:all`, compiler có thể báo cảnh báo `[try]` rằng resource variable không được nhắc đến trong body; cảnh báo này **không có nghĩa TWR không đóng tài nguyên**. Đó là lựa chọn có chủ đích để đo vòng đời.

## 4. Nếu khởi tạo tài nguyên chưa hoàn tất

TWR chỉ nhận ownership đối với các **resource đã được khởi tạo thành công** trong danh sách resource. Nếu khởi tạo resource thứ hai thất bại, resource thứ nhất vẫn được đóng, resource thứ hai chưa được đăng ký thì không có `close()`.

Tạo `AcquisitionFailureDemo.java`:

```java
public class AcquisitionFailureDemo {
    static final class Tracked implements AutoCloseable {
        private final String name;

        Tracked(String name) {
            this.name = name;
        }

        @Override
        public void close() {
            System.out.println("close:" + name);
        }
    }

    static Tracked open(String name, boolean fail) {
        System.out.println("open:" + name);
        if (fail) {
            throw new IllegalArgumentException("failed:" + name);
        }
        return new Tracked(name);
    }

    public static void main(String[] args) {
        try (Tracked first = open("first", false);
             Tracked second = open("second", true)) {
            System.out.println("not-reached");
        } catch (IllegalArgumentException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 AcquisitionFailureDemo.java
java AcquisitionFailureDemo
```

```text
open:first
open:second
close:first
caught=failed:second
```

Vì lời gọi `open("second", true)` ném lỗi trước khi trả về một `Tracked`, không có `close:second`. Tuy nhiên, `first` đã được mở thành công nên vẫn được đóng trước `catch`.

**Phân biệt việc mở dở bên trong factory:** nếu `openResource()` tự mở nhiều handle nội bộ rồi ném exception trước khi trả object cho bên ngoài, TWR bên ngoài **không biết** về các handle chưa bàn giao đó. Factory phải tự dọn phần khởi tạo dở, hoặc dùng TWR **bên trong factory** để bảo đảm không rò rỉ. Đây là ranh giới trách nhiệm thường bị bỏ sót.

## 5. Owned và borrowed khi truyền Reader giữa các hàm

Đây là một quy ước API dễ áp dụng:

- `readFile(Path path)`: method **mở** reader và chịu trách nhiệm đóng.
- `parse(BufferedReader borrowed)`: method **chỉ dùng** reader, caller chịu trách nhiệm đóng.
- `consumeTransferred(BufferedReader transferred)`: method nhận quyền quản lý và **đóng reader**, caller không nên sử dụng tiếp.

Tạo `OwnershipDemo.java`:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class OwnershipDemo {
    static int countNonBlank(BufferedReader borrowed)
            throws IOException {
        int count = 0;
        String line;
        while ((line = borrowed.readLine()) != null) {
            if (!line.isBlank()) {
                count++;
            }
        }
        return count;
    }

    static String readFileFirstLine(Path path)
            throws IOException {
        try (BufferedReader owned = Files.newBufferedReader(
                path, StandardCharsets.UTF_8)) {
            return owned.readLine();
        }
    }

    static String consumeTransferred(BufferedReader transferred)
            throws IOException {
        try (transferred) {
            return transferred.readLine();
        }
    }

    public static void main(String[] args) throws IOException {
        try (BufferedReader callerOwned = new BufferedReader(
                new StringReader("one\n \ntwo\n"))) {
            System.out.println(
                "borrowed-count=" + countNonBlank(callerOwned));
            System.out.println(
                "caller-can-still-read="
                + (callerOwned.readLine() == null));
        }

        BufferedReader transferred = new BufferedReader(
                new StringReader("sent\n"));
        System.out.println(
            "transferred-first=" + consumeTransferred(transferred));
        try {
            transferred.readLine();
        } catch (IOException ex) {
            System.out.println(
                "transferred-closed="
                + ex.getClass().getSimpleName());
        }
    }
}
```

```bash
javac -encoding UTF-8 OwnershipDemo.java
java OwnershipDemo
```

```text
borrowed-count=2
caller-can-still-read=true
transferred-first=sent
transferred-closed=IOException
```

**Diễn giải ownership:**

- Caller tự mở `callerOwned` trong TWR, sau đó **cho `countNonBlank` mượn**. Helper đọc đến EOF nhưng không đóng. Caller vẫn có thể gọi `readLine()` (nhận `null` ở EOF, không bị exception) rồi chính TWR của caller đóng.
- `readFileFirstLine` (minh họa cách dùng thực tế, không cần có file để chạy `main`) mở reader từ `Path`, trả về **`String` đã đọc** chứ không trả handle; TWR của method đóng reader đúng lúc.
- `consumeTransferred` dùng cú pháp `try (transferred)`, cho phép từ **Java 9** nếu biến tham chiếu đã khai báo là **final hoặc effectively final**. Method **nhận quyền đóng theo hợp đồng chuyển ownership**, nên reader bị đóng trước khi method trả về `"sent"`. Caller không thể tiếp tục đọc.

Nếu đổi `countNonBlank` thành `try (borrowed)`, helper sẽ vô tình **đóng resource thuộc caller**, dù tên biến và hợp đồng nói chỉ mượn. Code có thể vẫn biên dịch nhưng sai lifecycle. Không dùng TWR chỉ vì IDE gợi ý “resource có close()”; phải xác nhận owner.

`String.isBlank()` được dùng trong code để bỏ qua dòng toàn khoảng trắng và có từ Java 11; ví dụ chạy trên Java 17+ như đã công bố.

### 5.1. Khi trả tài nguyên mở ra ngoài

Một factory có thể chủ đích trả `InputStream` để caller tự xử lý:

```java
static java.io.InputStream openOwnedStream(
        java.nio.file.Path path) throws java.io.IOException {
    return java.nio.file.Files.newInputStream(path);
}
```

Đây là **phương thức minh họa**, đặt trong lớp. Vì method **chuyển quyền sở hữu sang caller**, nó không đặt stream trả về trong một TWR của chính mình. Caller phải viết:

```java
try (java.io.InputStream owned = openOwnedStream(path)) {
    // Đọc từ owned...
}
```

Đây là snippet, `path` cần được khai báo trước. Nếu viết `try (InputStream stream = ...){ return stream; }`, stream sẽ bị **đóng trước khi caller có cơ hội đọc**. Không nhầm việc trả tham chiếu với việc chuyển ownership thành công: đối tượng đã đóng không thể trở lại mở chỉ vì có caller mới.

## 6. TWR đóng những đối tượng nào?

Tài nguyên trong TWR phải có kiểu triển khai `AutoCloseable` hoặc subtype. `Closeable` là subtype của `AutoCloseable` và có hợp đồng `close() throws IOException`; trong khi `AutoCloseable.close()` khai báo `throws Exception`, implementation có thể thu hẹp loại lỗi hoặc không ném checked exception.

| Loại thường gặp | Phạm vi owner | Lưu ý |
| --- | --- | --- |
| `InputStream`, `OutputStream`, `Reader`, `Writer` | Scope xử lý I/O tương ứng | Đóng có thể giải phóng handle, flush buffer hoặc ném `IOException`. |
| `BufferedReader`/`BufferedWriter` | Scope sở hữu wrapper | Đóng wrapper tiêu chuẩn thường **đóng tiếp nguồn được bọc**. |
| `FileChannel`, `ZipFile` | Scope thao tác file/ZIP | Không dựa vào GC để giải phóng handle. |
| `Connection`, `PreparedStatement`, `ResultSet` | Scope mượn/khai thác JDBC | Kiểm tra ownership của connection và transaction. |
| `Stream<String>` do `Files.lines(path)` trả về | Scope xử lý file-backed stream | Đóng stream để giải phóng tài nguyên I/O của pipeline. |
| `StringReader` | Scope nếu caller thật sự sở hữu | Có thể không giữ handle OS, nhưng việc quyền đóng vẫn do hợp đồng quyết định. |

### 6.1. Tài nguyên wrapper và hiệu ứng đóng theo chuỗi

`BufferedReader` có thể bọc `InputStreamReader`, bên trong lại bọc `InputStream`. Với các wrapper I/O tiêu chuẩn, đóng wrapper ngoài **thường đóng cả stream bên dưới**. Nếu method chỉ **mượn** `InputStream` mà tự tạo wrapper rồi đóng wrapper, nó có thể làm đóng luôn stream của caller.

Một mẫu chỉ phù hợp khi method sở hữu cả pipeline:

```java
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(
            Files.newInputStream(path),
            StandardCharsets.UTF_8))) {
    // Xử lý reader.
}
```

Đây là **đoạn minh họa** trong phương thức, cần import và xử lý `IOException`. Đóng `reader` sẽ dẫn đến đóng các lớp bọc tiêu chuẩn bên dưới. Nếu việc khởi tạo wrapper có thể thất bại **sau khi stream nguồn đã mở**, cần thiết kế để không làm rò rỉ stream mở dở; nhưng không nên tùy tiện đăng ký cả wrapper và underlying như hai owner độc lập nếu API không cam kết close nhiều lần là an toàn.

**Không giả định `close()` idempotent cho mọi `AutoCloseable`.** Interface không yêu cầu hành vi an toàn khi gọi close lặp; một vài implementation có thể ném lỗi hoặc thực hiện side effect.

### 6.2. `System.in`, `System.out` và tài nguyên dùng chung

Standard streams thường thuộc vòng đời của process. Một helper tạm thời đọc từ `System.in` **không nên** viết TWR làm đóng luồng chuẩn khi ứng dụng còn dùng nó. `BufferedReader.close()` cũng có thể đóng underlying `System.in` nếu wrapper chứa luồng đó.

Với `System.out`/`System.err`, đừng đóng từ helper như một cách thay `flush()`. Nếu cần flush, dùng API phù hợp với hợp đồng luồng, còn việc kết thúc vòng đời nguồn chia sẻ thuộc phạm vi ứng dụng.

## 7. File-backed stream phải được đóng sau terminal operation

`Files.lines(path, UTF_8)` trả về một `Stream<String>` được backed bởi file. Việc gọi `count()`/`forEach()` **không đồng nghĩa** có thể bỏ qua close; cần giải phóng handle khi hoàn thành pipeline.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

// Đoạn minh họa thành viên của một lớp:
static long countNonBlankLines(Path path) throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.filter(line -> !line.isBlank()).count();
    }
}
```

Method **trả `long`**, không trả `Stream` đã bị đóng. Nếu cần trả stream đang mở, factory phải trả stream **chưa đóng** và công bố caller sẽ đóng nó. Với công việc đơn giản, trả dữ liệu được tính xong trong scope là cách thiết kế ít rủi ro hơn.

**Quan trọng:** không phải mọi stream Java đều gắn OS handle. `Stream.of(...)` hay `list.stream()` thường không cần close để giải phóng tài nguyên hệ thống; `Files.lines` thì có hợp đồng giải phóng tài nguyên I/O. Đừng máy móc thêm TWR vào mọi stream, nhưng đừng bỏ TWR đối với stream đọc từ file.

## 8. Primary exception và suppressed exception

Giả sử body ném lỗi và `close()` cũng ném lỗi. Nếu cleanup được viết vụng trong `finally`, exception của cleanup có thể **che** lỗi gốc. TWR được thiết kế để lưu cả hai:

- **Primary exception**: lỗi được ném từ body hoặc từ bước phù hợp của quá trình thực thi.
- **Suppressed exception**: lỗi `close()` khi đã có một lỗi primary trước đó; truy cập bằng `Throwable.getSuppressed()`.
- Nếu body bình thường nhưng nhiều resource cùng lỗi khi đóng, exception do tài nguyên **đóng đầu tiên** (theo thứ tự ngược) có thể là primary, lỗi từ các lần đóng sau là suppressed.

Tạo tệp `CloseFailureDemo.java`:

```java
import java.io.IOException;

public class CloseFailureDemo {
    static final class Noisy implements AutoCloseable {
        private final String name;

        Noisy(String name) {
            this.name = name;
            System.out.println("open:" + name);
        }

        @Override
        public void close() throws IOException {
            System.out.println("close:" + name);
            throw new IOException("close-" + name);
        }
    }

    public static void main(String[] args) {
        try (Noisy a = new Noisy("A");
             Noisy b = new Noisy("B")) {
            System.out.println("body-fails");
            throw new IllegalStateException("body");
        } catch (Exception ex) {
            System.out.println(
                "primary=" + ex.getClass().getSimpleName()
                + ":" + ex.getMessage());
            System.out.println(
                "suppressed=" + ex.getSuppressed().length);
            for (Throwable failure : ex.getSuppressed()) {
                System.out.println(
                    "suppressed="
                    + failure.getClass().getSimpleName()
                    + ":" + failure.getMessage());
            }
        }

        try (Noisy c = new Noisy("C");
             Noisy d = new Noisy("D")) {
            System.out.println("body-ok");
        } catch (IOException ex) {
            System.out.println(
                "primary-close=" + ex.getMessage());
            System.out.println(
                "secondary-close="
                + ex.getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 CloseFailureDemo.java
java CloseFailureDemo
```

```text
open:A
open:B
body-fails
close:B
close:A
primary=IllegalStateException:body
suppressed=2
suppressed=IOException:close-B
suppressed=IOException:close-A
open:C
open:D
body-ok
close:D
close:C
primary-close=close-D
secondary-close=close-C
```

Lần thứ nhất, `IllegalStateException("body")` là primary và hai lỗi đóng được gắn vào nó theo thứ tự `B` rồi `A`. Lần thứ hai, body thành công, `D.close()` ném exception primary còn lỗi của `C.close()` được gắn suppressed. **TWR vẫn cố đóng các resource còn lại** dù một `close()` đã thất bại.

Mã production cần logging bảo toàn stack trace, cause và suppressed exceptions khi cần chẩn đoán. Không nuốt hết `IOException` trong một khối `catch` rỗng chỉ vì “body đã hoàn thành”.

### 8.1. TWR với `catch` và `finally`

`catch` và `finally` vẫn có thể xuất hiện cùng TWR. **Resource đã được đóng (hoặc đã được cố đóng) trước khi các block `catch`/`finally` đó chạy**. `finally` dùng cho việc khác như đánh dấu trạng thái hoặc gửi metric, không phải nơi để lặp close của resource đã được TWR quản lý.

Một exception mới ném từ `finally` có thể che exception đang lan truyền nếu code viết sai. TWR làm rõ cleanup; đừng tái tạo vấn đề bằng nhiều nơi đóng cùng object.

## 9. Thời điểm và quyền đóng ở JDBC

Trong một scope **tự nhận quyền mượn** connection từ pool:

```java
try (Connection conn = dataSource.getConnection();
     PreparedStatement ps =
            conn.prepareStatement("SELECT name FROM users");
     ResultSet rs = ps.executeQuery()) {
    while (rs.next()) {
        System.out.println(rs.getString("name"));
    }
}
```

Đây là **mã minh họa JDBC**, cần `dataSource`/schema/import thực tế. Thứ tự đóng là `rs` → `ps` → `conn`. Với pooled connection, `conn.close()` thường biểu thị **trả connection về pool**, không có nghĩa đóng toàn bộ pool.

**TWR không đồng nghĩa transaction management:** nếu dùng `setAutoCommit(false)`, nghiệp vụ vẫn phải quyết định `commit()` khi thành công và `rollback()` khi thất bại. Không suy ra “đã close thì dữ liệu đã commit”. Nếu một helper chỉ **mượn connection** đang thuộc transaction của caller, helper không được tự ý đóng connection làm kết thúc scope ngoài dự kiến.

Với connection pool, transaction boundary và resource scope có thể do framework quản lý; cần đọc hợp đồng framework trước khi tự thêm TWR vào một connection đang được tiêm vào từ tầng khác.

## 10. Java 9+ cho phép tham chiếu biến resource đã khai báo

Cú pháp Java 7 dạng:

```java
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    System.out.println(reader.readLine());
}
```

Từ Java 9, có thể viết:

```java
BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8);
try (reader) {
    System.out.println(reader.readLine());
}
```

Cả hai là **đoạn minh họa** trong phương thức có import và xử lý `IOException`. Ở dạng thứ hai, `reader` là một biến **final hoặc effectively final** (không được gán lại). TWR vẫn đóng object **trước khi** kết thúc statement, dù tên biến `reader` còn nằm trong scope của method.

Điểm đặc biệt đáng nhớ: **cú pháp hợp lệ không làm thay đổi ownership**. Nếu `reader` là tham số method chỉ mượn của caller, đặt nó vào `try (reader)` sẽ đóng một tài nguyên **không thuộc sở hữu method**.

## 11. Bảng thời điểm đóng cần nhớ

| Điều xảy ra | Đóng tài nguyên khi nào? | Điều cần kiểm tra |
| --- | --- | --- |
| Thân `try` thành công | Ngay khi rời body, trước statement tiếp theo | Lỗi close vẫn có thể làm TWR kết thúc bằng exception |
| Có `return` trong body | Trước khi caller nhận return | Lỗi close có thể ngăn return hoàn thành |
| Body ném exception | Đóng ngược thứ tự rồi mới lan truyền lỗi | Body exception primary; lỗi close được suppressed |
| Resource thứ hai khởi tạo lỗi | Resource đầu đã mở sẽ được đóng | Factory phải dọn handle nội bộ chưa bàn giao |
| Nhiều resource cùng lỗi lúc close | Vẫn cố đóng tất cả theo thứ tự ngược | Lỗi đóng đầu tiên có thể là primary, các lỗi còn lại suppressed |
| Method chỉ mượn resource | Không được tự đóng | Owner bên ngoài quyết định thời điểm close |
| Factory trả resource đang mở | Caller đóng sau khi sử dụng | Không trả resource từ scope TWR đã đóng nó |

**Resource reference bằng `null`:** TWR không gọi `close()` trên resource bằng `null`. Nhưng không nên dùng điều này để xây dựng hợp đồng ownership mơ hồ; việc mở không thành công cần chính sách riêng.

**Không giả định close có thể gọi nhiều lần:** `AutoCloseable` không bắt buộc idempotent, nên chỉ có một owner và một điểm đóng có trách nhiệm là cách thiết kế dễ dự đoán hơn.

**Không coi close là đảm bảo lưu trữ bền vững:** `close()`/flush và `fsync`/transaction commit/protocol acknowledgement là những mức bảo đảm khác nhau, tùy loại tài nguyên.

## 12. Checklist code review

1. **Tìm owner:** ai mở tài nguyên? Caller, callee hay framework/pool? Có chuyển ownership không?
2. **Giữ scope ngắn:** có thể trả dữ liệu đã tính thay vì trả handle mở không?
3. **Kiểm tra đường thành công và thất bại:** close có chạy khi `return`, exception và khởi tạo resource sau thất bại?
4. **Kiểm tra thứ tự phụ thuộc:** resource nào cần đóng trước resource nào?
5. **Tìm resource rò rỉ trong factory:** có mở dở rồi ném exception trước khi trả object ra ngoài không?
6. **Không đóng resource borrowed:** nhất là `System.in`, connection của transaction ngoài, stream caller còn dùng.
7. **Kiểm tra wrapper:** đóng wrapper có đóng underlying resource không, và ai sở hữu underlying?
8. **Không trả object đã đóng:** tránh `return reader`/`return stream` từ trong scope TWR của chính chúng.
9. **Quan sát suppressed exceptions:** logging phải giữ cause, stack trace và suppressed nếu có lỗi cleanup.
10. **Đừng nhầm close với commit/durability:** xác định bước nghiệp vụ cần commit, rollback hoặc flush bền vững riêng.
11. **Kiểm tra đúng phiên bản:** `try (variable)` cần Java 9+, `String.isBlank()` cần Java 11+, các chương trình ở đây chạy trên Java 17+.
12. **Đảm bảo test không chỉ kiểm tra đường vui:** mô phỏng đóng lỗi, mở lỗi, body lỗi và thứ tự đóng.

## 13. Bài tập thực hành

**Bài 1 — Đo vòng đời.** Chạy `ResourceOrderDemo`, đoán thứ tự `open`/`close` và vị trí dòng `result=7` trước khi xem output. Giải thích vì sao `return` không bỏ qua close.

**Bài 2 — Khởi tạo thất bại.** Chạy `AcquisitionFailureDemo`, thử làm lỗi xuất hiện ở resource đầu tiên thay vì thứ hai. Resource nào được đăng ký với TWR, resource nào bị đóng?

**Bài 3 — Borrowed và transferred.** Chạy `OwnershipDemo`. Vì sao `countNonBlank` không đóng reader? Vì sao `consumeTransferred` được phép đóng? Mô tả điều gì sai nếu caller vẫn cần đọc tiếp sau khi gọi `consumeTransferred`.

**Bài 4 — Lỗi khi đóng.** Chạy `CloseFailureDemo`, ghi rõ primary và từng suppressed exception. Thay một resource không còn ném lỗi khi đóng và so sánh kết quả.

**Bài 5 — File-backed Stream.** Viết phương thức đếm số dòng có chữ bằng `Files.lines(path, UTF_8)`. Đặt terminal operation bên trong TWR và chỉ trả `long`. Giải thích vì sao không trả trực tiếp stream từ TWR.

**Bài 6 — JDBC.** Vẽ sơ đồ sở hữu và thứ tự close cho `Connection`/`PreparedStatement`/`ResultSet`. Nếu transaction thuộc caller, helper có quyền đóng connection không? Viết bước commit/rollback riêng.

**Bài 7 — Contract.** Viết JavaDoc cho API nhận `InputStream borrowed` và API trả `InputStream` cho caller. Ghi rõ owner, nghĩa vụ close, và cách xử lý ngoại lệ. Thiết kế test để phát hiện helper đóng nhầm stream được mượn.

## 14. Tổng kết

- **Ownership trả lời “ai đóng”; TWR trả lời “khi nào đóng”.**
- Mỗi tài nguyên thuộc scope TWR được đóng khi rời scope, **cả trên đường bình thường, `return` và exception**.
- Khởi tạo nhiều tài nguyên theo chiều trái → phải; đóng các tài nguyên thành công theo chiều **phải → trái**.
- **Borrowed không được tự đóng; transferred phải có hợp đồng rõ.** Factory không tự đóng resource mà nó chuyển ownership cho caller.
- **Không trả resource đã bị TWR đóng** và không đóng tùy tiện stream dùng chung hay wrapper chứa stream được mượn.
- **Close có thể ném lỗi.** Khi body thất bại, lỗi close thường ở `getSuppressed()`; khi body thành công, lỗi close có thể thành primary.
- **Close không thay commit/rollback hay durability guarantee.**
- `try-with-resources` là kỹ thuật Java 7 **vẫn hiện hành**; Java 9+ cho phép `try (existingVariable)` khi final/effectively final, và các API JDK hiện đại nên được dùng theo hợp đồng ownership của chúng.

## Tài liệu chính thức

- [JLS `14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3): thứ tự khởi tạo, close, exceptions/suppressed, resource variables.
- [AutoCloseable JavaDoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng `close()`, exception và tính idempotent.
- [Files JavaDoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): file-backed streams và vòng đời resource.
