# Resource được khai báo trong `try-with-resources` và phạm vi sử dụng trong Java

`try-with-resources` cho phép Java **tự động đóng tài nguyên** khi rời một khối xử lý, kể cả khi phần thân `try` ném ngoại lệ hoặc `return`. Cú pháp này đặc biệt hữu ích với tệp, stream, reader, writer, kết nối hoặc các đối tượng tự quản lý vòng đời. Tuy nhiên, để sử dụng đúng, cần phân biệt rõ **biến resource được khai báo ở đâu**, **nó còn nằm trong phạm vi truy cập (scope) ở đâu** và **đối tượng đã được đóng vào thời điểm nào**.

Một ví dụ đơn giản:

```java
try (var reader = java.nio.file.Files.newBufferedReader(path)) {
    String line = reader.readLine();
    System.out.println(line);
}
```

Đây là **đoạn minh họa**, giả định `path` có kiểu `java.nio.file.Path` và lời gọi nằm trong phương thức có xử lý hoặc khai báo `IOException`. Biến `reader` được khai báo trong *resource specification* — cặp ngoặc tròn ngay sau `try`. Java đóng `reader` khi thoát khỏi phần thân `try`; sau đó tên biến `reader` không còn nằm trong phạm vi truy cập.

Có hai trường hợp cần phân biệt:

- **Khai báo resource mới trong `try`:** `try (Reader r = ...) { ... }`. Tên `r` dùng được trong phần thân `try` và, theo quy tắc scope, trong những phần thích hợp của danh sách khai báo resource theo sau nó, **không** dùng được từ `catch`, `finally` hay mã phía sau cấu trúc.
- **Sử dụng biến đã khai báo bên ngoài:** từ Java 9 có thể viết `try (existingResource) { ... }` nếu biến là `final` hoặc *effectively final*. Tên biến vẫn có phạm vi theo khai báo ban đầu, có thể xuất hiện sau khối `try`, **nhưng đối tượng đã được đóng**. “Biến vẫn còn tên” không có nghĩa “resource còn sử dụng được”.

## 1. Tại sao `try-with-resources` cần một phạm vi riêng?

Một chương trình thường phải thực hiện hai hành động đối với tài nguyên:

1. **Lấy quyền sở hữu hoặc mở tài nguyên:** ví dụ mở reader cho tệp.
2. **Đóng tài nguyên dù thành công hay thất bại:** ví dụ giải phóng file handle.

Cách thủ công dễ mắc lỗi:

```java
var reader = java.nio.file.Files.newBufferedReader(path);
String line = reader.readLine();
reader.close();
```

Đây là **mã minh họa chưa xử lý checked exception**. Nếu `readLine()` ném `IOException`, dòng `close()` phía sau có thể không được thực hiện. Viết `try-finally` thủ công có thể khắc phục một phần, nhưng phải cẩn thận với lỗi xảy ra khi mở, đọc và đóng.

`try-with-resources` biến việc đóng tài nguyên thành **một phần ngữ nghĩa của cú pháp**. Tài nguyên được đóng khi khối `try` kết thúc, không phụ thuộc việc bạn có nhớ gọi `close()` ở từng nhánh `return` hay không.

```java
try (var reader = java.nio.file.Files.newBufferedReader(path)) {
    return reader.readLine();
}
```

Đây là **thân phương thức minh họa** có kiểu trả về `String` và hợp đồng `throws IOException` phù hợp. Reader được đóng trước khi phương thức thực sự trả kết quả; nếu đóng gây ngoại lệ, đường trả kết quả có thể bị thay bằng đường ném ngoại lệ.

Phạm vi ngắn giúp **giới hạn vòng đời tài nguyên**: đọc/ghi nằm trong vùng được quản lý, còn câu lệnh sau vùng đó không vô tình tiếp tục dùng resource đang mở.

## 2. Điều kiện để một đối tượng là resource

Tài nguyên trong `try-with-resources` phải có kiểu tương thích với **`java.lang.AutoCloseable`**. Interface này có phương thức:

```java
public interface AutoCloseable {
    void close() throws Exception;
}
```

Đây là **chữ ký minh họa của API**, không phải mã cần tự khai báo lại trong ứng dụng. Một số lớp thường dùng:

| Tài nguyên | Interface/class liên quan | Tác dụng điển hình |
| --- | --- | --- |
| `BufferedReader` | `java.io.Closeable` → `AutoCloseable` | Đọc văn bản và đóng reader |
| `InputStream` | `java.io.Closeable` → `AutoCloseable` | Đọc byte, giải phóng nguồn đọc |
| `OutputStream` | `java.io.Closeable` → `AutoCloseable` | Ghi byte và đóng nguồn ghi |
| `Scanner` | `java.io.Closeable` → `AutoCloseable` | Đóng scanner và nguồn nếu phù hợp |
| `java.sql.Connection` | `AutoCloseable` | Trả/đóng kết nối theo triển khai |
| Lớp tự viết `implements AutoCloseable` | `AutoCloseable` | Định nghĩa công việc đóng cụ thể |

Một đối tượng bất kỳ **không trở thành resource hợp lệ chỉ vì nó có phương thức tên `close()`**. Kiểu của nó phải triển khai `AutoCloseable` để dùng trực tiếp trong resource specification.

Nếu lớp tự viết:

```java
final class LocalResource implements AutoCloseable {
    @Override
    public void close() {
        System.out.println("closed");
    }
}
```

thì một biến kiểu `LocalResource` có thể được quản lý bởi `try-with-resources`. Ví dụ này là **lớp minh họa**; `close()` được override không khai báo checked exception, nên người dùng lớp này không phải xử lý checked `Exception` chỉ vì gọi `close()`.

### `AutoCloseable` và checked exception

Interface `AutoCloseable.close()` cho phép khai báo `throws Exception`; các lớp cụ thể thường khai báo một kiểu hẹp hơn hoặc không khai báo checked exception. Trình biên dịch dựa trên **kiểu tĩnh của resource** và lời gọi liên quan để kiểm tra các checked exception có thể xảy ra khi khởi tạo, dùng và đóng.

Ví dụ nếu giữ tài nguyên bằng biến kiểu `AutoCloseable` và `close()` có thể ném checked `Exception`, một phương thức dùng nó có thể cần `catch` hoặc `throws Exception` phù hợp. Không nên mặc định mọi `try-with-resources` đều chỉ cần `catch (IOException)`.

## 3. Resource specification: khai báo trong ngoặc ngay sau `try`

Dạng khai báo mới:

```java
try (ResourceType resource = createResource()) {
    useResource(resource);
}
```

Đây là **cấu trúc minh họa**, yêu cầu `ResourceType implements AutoCloseable` và có các phương thức tương ứng. Cụm `ResourceType resource = createResource()` gồm:

- **Kiểu resource:** phải tương thích `AutoCloseable`.
- **Tên biến:** ví dụ `resource`, dùng trong phạm vi mà Java cho phép.
- **Initializer:** biểu thức tạo hoặc cung cấp tham chiếu tới resource, được đánh giá lúc đi vào cấu trúc.

Có thể khai báo nhiều resource, ngăn cách bằng dấu chấm phẩy:

```java
try (FirstResource first = openFirst();
     SecondResource second = openSecond()) {
    useBoth(first, second);
}
```

Hai kiểu, hai hàm mở và hàm sử dụng ở đây là **cấu trúc minh họa**, không phải chương trình độc lập.

Tính chất chính:

1. Các initializer được đánh giá **theo thứ tự từ trái sang phải**.
2. Phần thân `try` chạy sau khi việc khởi tạo resource hoàn tất.
3. Khi thoát, các resource đã được khởi tạo thành công sẽ được đóng theo **thứ tự ngược**: cuối cùng mở/khai báo thì đóng trước.
4. Nếu khởi tạo resource thứ hai thất bại, resource thứ nhất đã được khởi tạo vẫn được đóng, dù phần thân `try` chưa chạy.
5. Sau khi đóng xong, `catch` và `finally` gắn với cấu trúc `try-with-resources` mới được thực thi khi thích hợp.

Dấu `;` cuối danh sách resource có thể được dùng theo cú pháp Java; nó không tạo thêm một resource rỗng.

## 4. Phạm vi của biến resource khai báo mới

Với cấu trúc:

```java
try (var reader = java.nio.file.Files.newBufferedReader(path)) {
    System.out.println(reader.readLine());
}
```

biến `reader` thuộc phạm vi tài nguyên của cấu trúc, **không phải biến cục bộ của cả phương thức**.

### Dùng được trong phần thân `try`

```java
try (var reader = java.nio.file.Files.newBufferedReader(path)) {
    String first = reader.readLine();
    String second = reader.readLine();
    System.out.println(first);
    System.out.println(second);
}
```

Đây là đoạn minh họa với `path` và hợp đồng `IOException` thích hợp. Cả hai lần đọc đều dùng cùng reader đang được quản lý. Sau khi khối kết thúc, Java đóng reader.

### Không dùng tên resource đó trong `catch` cùng cấp

Đoạn sau **cố ý không biên dịch**:

```java
try (var reader = java.nio.file.Files.newBufferedReader(path)) {
    System.out.println(reader.readLine());
} catch (java.io.IOException ex) {
    reader.close(); // Lỗi: reader không nằm trong scope.
}
```

Điều cần sửa không phải thêm `throws` cho `close()`, mà là hiểu đúng **scope**. `reader` khai báo trong resource specification không được nhìn thấy ở thân `catch`. Java vốn đã gọi `close()` khi thoát khỏi phần thân `try`, nên câu đóng thêm cũng không cần thiết.

### Không dùng tên resource đó trong `finally` cùng cấp

```java
try (var reader = java.nio.file.Files.newBufferedReader(path)) {
    System.out.println(reader.readLine());
} finally {
    // reader.close(); // Sai scope; resource đã được quản lý tự động.
    System.out.println("read attempt finished");
}
```

Đây là cấu trúc minh họa, cần xử lý hoặc khai báo `IOException` có thể phát sinh. `finally` có thể thực hiện công việc tổng kết nhưng không truy cập trực tiếp biến `reader` vừa khai báo trong resource specification. Việc đóng resource xảy ra **trước** `finally` đi kèm.

### Không dùng tên resource ở các câu sau `try`

```java
try (LocalResource r = new LocalResource()) {
    System.out.println("inside");
}
// r.close(); // Lỗi biên dịch: không còn scope.
```

Đây là đoạn minh họa khi `LocalResource` được định nghĩa như ở phần trước. Không nên biến một resource cục bộ chỉ tồn tại trong vùng quản lý thành phụ thuộc lâu dài ở bên ngoài.

**Ghi nhớ:** “biến resource không còn scope” và “đối tượng resource đã được đóng” là hai sự thật **khác nhau** nhưng thường cùng xảy ra khi rời cấu trúc `try-with-resources` khai báo mới.

## 5. Nhiều resource: biến khai báo trước có thể được dùng để khởi tạo resource sau

Các khai báo trong resource specification được xử lý tuần tự. Một resource đứng sau có thể phụ thuộc vào resource đứng trước khi được khởi tạo.

Ví dụ đọc văn bản bằng cách bọc stream trong reader:

```java
try (var input = java.nio.file.Files.newInputStream(path);
     var reader = new java.io.BufferedReader(
             new java.io.InputStreamReader(
                     input, java.nio.charset.StandardCharsets.UTF_8))) {
    System.out.println(reader.readLine());
}
```

Đây là **đoạn minh họa**, yêu cầu biến `path` hợp lệ và xử lý hoặc khai báo `IOException`.

- Biến `input` được khai báo trước, nên initializer của `reader` có thể tham chiếu tới `input`.
- `reader` sử dụng `input` làm nguồn dữ liệu.
- Java sẽ gọi `reader.close()` trước, sau đó gọi `input.close()` theo quy tắc ngược thứ tự.
- Vì `reader.close()` có thể đã đóng stream bên dưới, `input.close()` có thể là lần đóng thứ hai. Nhiều implementation đóng lặp an toàn, nhưng không nên mặc định mọi tài nguyên đều chịu được double-close giống nhau.

Đối với stream được reader **sở hữu hoàn toàn**, thường chỉ cần đăng ký **reader** trong resource specification để tránh đóng chồng không cần thiết:

```java
try (var reader = java.nio.file.Files.newBufferedReader(
        path, java.nio.charset.StandardCharsets.UTF_8)) {
    System.out.println(reader.readLine());
}
```

Quyết định đăng ký resource nào phụ thuộc **ownership**: đối tượng nào chịu trách nhiệm đóng đối tượng nào, và mỗi resource có độc lập cần đóng hay không.

### Không dùng resource khai báo sau trong initializer của resource trước

Các khai báo resource tuân theo quy tắc phạm vi và definite assignment của Java. Không thể dùng một biến chưa được khai báo hoặc chưa có giá trị hợp lệ ở vị trí khởi tạo resource phía trước.

```java
// Cố ý sai: second chưa được khai báo tại initializer của first.
try (LocalResource first = second;
     LocalResource second = new LocalResource()) {
    // ...
}
```

Khi cần quan hệ phụ thuộc, hãy khai báo **nguồn trước, đối tượng phụ thuộc sau**, và cân nhắc vòng đời/ownership để tránh lỗi đóng chồng.

## 6. Biến resource khai báo trong ngoặc có thể gán lại không?

**Không.** Các biến resource được khai báo trực tiếp trong resource specification có ngữ nghĩa **`final`**: bạn không được gán cho biến resource một tham chiếu khác trong phần thân `try`.

```java
try (LocalResource resource = new LocalResource()) {
    // resource = new LocalResource(); // Lỗi biên dịch.
}
```

Dòng bị comment là lỗi nếu bỏ comment. Nhưng `final` ở đây **không khiến đối tượng resource bất biến**. Bạn vẫn có thể gọi các phương thức hợp lệ của nó, đọc dữ liệu, ghi vào stream hoặc thay đổi trạng thái nội bộ theo API.

Cấm gán lại biến mang ý nghĩa quan trọng đối với dọn dẹp: Java cần biết **đối tượng đã được đăng ký đóng**. Nếu có thể âm thầm thay biến sang đối tượng khác, một đối tượng có thể bị mất tham chiếu và rò rỉ tài nguyên.

Hãy phân biệt:

- **Biến tham chiếu `final`:** không thể bị gán lại.
- **Đối tượng resource:** có thể có trạng thái mutable.
- **Trạng thái đóng/mở:** là một phần vòng đời của resource; `final` không bảo đảm đối tượng còn mở.
- **Tính an toàn đa luồng:** `final` không tự biến phương thức của resource thành thread-safe.

Tương tự `catch (final IOException ex)`, từ khóa `final` không có nghĩa là không được gọi phương thức trên đối tượng.

## 7. Dùng resource đã khai báo bên ngoài — Java 9 trở lên

Từ **Java 9**, resource specification còn có thể sử dụng **tên biến đã tồn tại** (hoặc biểu thức truy cập biến phù hợp), với điều kiện biến cục bộ được tham chiếu là `final` hoặc **effectively final** và đã được gán chắc chắn.

Ví dụ Java 17:

```java
var reader = java.nio.file.Files.newBufferedReader(path);
try (reader) {
    System.out.println(reader.readLine());
}
```

Đây là **đoạn minh họa** trong một phương thức có `path` và xử lý `IOException` phù hợp.

Điểm khác biệt với `try (var reader = ...)`:

- `reader` được khai báo **bên ngoài** resource specification, nên tên biến vẫn có thể nằm trong scope **sau** cấu trúc `try`.
- Java vẫn gọi `reader.close()` khi rời `try`.
- Người viết không được gán lại `reader` nếu đang dùng nó dưới dạng resource variable-access theo điều kiện *effectively final*.
- Đọc lại hoặc ghi tiếp qua `reader` **sau khi bị đóng** thường không hợp lệ về vòng đời và có thể ném ngoại lệ như `IOException`, tùy implementation.

Ví dụ minh họa:

```java
var reader = java.nio.file.Files.newBufferedReader(path);
try (reader) {
    System.out.println(reader.readLine());
}
System.out.println(reader != null); // Biến còn scope; reader đã đóng.
```

Dòng in boolean ở đây chỉ kiểm tra tham chiếu không null, **không** nói rằng resource còn mở. Chỉ nên kiểm tra trạng thái đóng/mở thông qua hợp đồng API phù hợp; nhiều tài nguyên không cung cấp `isOpen()` hay `isClosed()` công khai.

### *Effectively final* nghĩa là gì?

Một biến cục bộ được coi là **effectively final** khi không bị gán lại theo quy tắc của Java mặc dù không viết từ khóa `final`.

Ví dụ hợp lệ:

```java
LocalResource reusable = new LocalResource();
try (reusable) {
    System.out.println("using reusable");
}
```

Biến `reusable` đã được gán một lần tại khai báo và không bị gán lại.

Ví dụ **cố ý không biên dịch**:

```java
LocalResource reusable = new LocalResource();
reusable = new LocalResource(); // Gán lại biến.
try (reusable) {
    System.out.println("using reusable");
}
```

Vì `reusable` bị gán lại, nó không còn *effectively final*. Đừng giải quyết bằng cách thêm `final` vào vị trí không phù hợp; cách đúng là quản lý rõ một tham chiếu resource duy nhất trong suốt phạm vi sử dụng hoặc khai báo mới trực tiếp bên trong `try`.

**Lưu ý về phiên bản:** cú pháp `try (existingResource)` không dùng được trong Java 7/8. Đối với Java 17+ thì đây là cách viết hợp lệ, miễn thỏa các ràng buộc của ngôn ngữ.

## 8. Ví dụ Java 17+ hoàn chỉnh: resource khai báo trong và ngoài

Lưu tệp **`ResourceScopeDemo.java`**:

```java
public class ResourceScopeDemo {

    static final class TrackedResource implements AutoCloseable {
        private final String name;
        private boolean closed;

        TrackedResource(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        void use() {
            if (closed) {
                throw new IllegalStateException(
                        name + " is already closed");
            }
            System.out.println("use " + name);
        }

        boolean isClosed() {
            return closed;
        }

        @Override
        public void close() {
            closed = true;
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        System.out.println("CASE declared-inside");

        try (TrackedResource first = new TrackedResource("first");
             TrackedResource second = new TrackedResource("second")) {
            first.use();
            second.use();
        }

        System.out.println("CASE declared-outside");

        TrackedResource external = new TrackedResource("external");

        // Java 9+: biến ngoài try, không bị gán lại.
        try (external) {
            external.use();
        }

        System.out.println(
                "external still in scope=" + (external != null));
        System.out.println(
                "external closed=" + external.isClosed());
    }
}
```

Lệnh biên dịch/chạy:

```bash
javac -encoding UTF-8 ResourceScopeDemo.java
java ResourceScopeDemo
```

**Stdout chính xác:**

```text
CASE declared-inside
open first
open second
use first
use second
close second
close first
CASE declared-outside
open external
use external
close external
external still in scope=true
external closed=true
```

### Giải thích

**Trường hợp khai báo trong `try`:**

1. Tạo `first` rồi `second`, nên in `open first`, `open second`.
2. Trong thân `try`, cả hai biến đang nằm trong scope; gọi `use` là hợp lệ.
3. Khi rời khối, Java đóng `second` trước `first`, nên dòng đóng xuất hiện theo thứ tự ngược.
4. Sau cấu trúc này, tên `first` và `second` không được truy cập từ `main` nữa; chương trình cố ý không chứa tham chiếu ngoài phạm vi.

**Trường hợp khai báo ngoài `try`:**

1. `external` được tạo ở phạm vi của `main`, sau đó dùng cú pháp `try (external)`.
2. `external.use()` chạy khi tài nguyên đang mở.
3. Java gọi `external.close()` trước khi tới hai câu in cuối.
4. Biến `external` vẫn còn trong scope, nhưng phương thức `isClosed()` của lớp giả lập trả `true`. Nếu gọi `external.use()` lúc này, lớp sẽ chủ động ném `IllegalStateException`.

Lớp `TrackedResource` được viết để đầu ra không phụ thuộc tệp thực, hệ điều hành hay chính sách log. Nó cũng cho thấy **scope của biến** và **trạng thái vòng đời của resource** là hai đặc điểm khác nhau.

## 9. Resource nào được đóng khi việc khởi tạo thất bại?

Xét:

```java
try (ResourceA a = openA();
     ResourceB b = openB()) {
    process(a, b);
}
```

Đây là sơ đồ minh họa. Nếu `openB()` ném ngoại lệ:

- `a` đã khởi tạo thành công sẽ được đóng.
- `b` không khởi tạo thành công nên **không** có đối tượng `b` hợp lệ để Java đóng theo declaration đó.
- Phần thân `process(a,b)` **không chạy**.
- Ngoại lệ từ initializer của `b` sẽ tiếp tục được xử lý theo `catch` phù hợp của cấu trúc sau khi đóng tài nguyên đã khởi tạo.
- Nếu `a.close()` cũng thất bại, ngoại lệ khi đóng có thể được lưu vào **suppressed exceptions** của ngoại lệ chính từ initializer `b`.

Không đúng nếu cho rằng Java “chỉ đóng tài nguyên khi đã vào phần thân `try`”. Resource được khởi tạo trước điểm lỗi vẫn được quản lý trong quá trình thoát khi khởi tạo tài nguyên sau thất bại.

### Thời điểm đóng so với `catch` và `finally`

Nếu viết:

```java
try (LocalResource r = new LocalResource()) {
    process(r);
} catch (RuntimeException ex) {
    handle(ex);
} finally {
    afterAttempt();
}
```

đây là một khung minh họa với các phương thức được định nghĩa phù hợp. Trình tự chuẩn là:

1. Khởi tạo resource.
2. Thực thi thân `try`.
3. Đóng resource khi rời thân `try` (hoặc sau lỗi xảy ra trong lúc khởi tạo).
4. Chuyển tới `catch` tương thích, nếu có ngoại lệ.
5. Thực hiện `finally` gắn với cấu trúc, nếu có.

Điều này giải thích tại sao handler `catch` có thể quan sát **lỗi từ `close()`** dù tên biến resource khai báo mới không nằm trong scope của handler. Handler nhận **đối tượng ngoại lệ**, không cần và không được dựa vào quyền truy cập biến resource đó.

## 10. Ví dụ Java 17+ hoàn chỉnh: lỗi trong thân, lỗi đóng và lỗi khởi tạo

Lưu mã thành **`ResourceFailureDemo.java`**:

```java
public class ResourceFailureDemo {

    static final class Tracked implements AutoCloseable {
        private final String name;
        private final boolean failOnClose;

        Tracked(String name, boolean failOnClose) {
            this.name = name;
            this.failOnClose = failOnClose;
            System.out.println("open " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);

            if (failOnClose) {
                throw new IllegalStateException(
                        "close failed: " + name);
            }
        }
    }

    static Tracked open(
            String name, boolean failOpen, boolean failClose) {
        if (failOpen) {
            System.out.println("open failed: " + name);
            throw new IllegalArgumentException(
                    "init failed: " + name);
        }

        return new Tracked(name, failClose);
    }

    static void bodyAndCloseFailure() {
        System.out.println("CASE body-and-close");

        try (Tracked first = open("A", false, true);
             Tracked second = open("B", false, true)) {
            System.out.println("body: failed");
            throw new IllegalArgumentException("body failed");

        } catch (IllegalArgumentException ex) {
            System.out.println("primary: " + ex.getMessage());
            System.out.println(
                    "suppressed count: " + ex.getSuppressed().length);

            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println(
                        "suppressed: " + suppressed.getMessage());
            }
        }
    }

    static void initializationFailure() {
        System.out.println("CASE initializer");

        try (Tracked first = open("X", false, false);
             Tracked second = open("Y", true, false)) {
            System.out.println("body: never runs");

        } catch (IllegalArgumentException ex) {
            System.out.println("caught: " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        bodyAndCloseFailure();
        initializationFailure();
    }
}
```

Chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 ResourceFailureDemo.java
java ResourceFailureDemo
```

**Stdout chính xác:**

```text
CASE body-and-close
open A
open B
body: failed
close B
close A
primary: body failed
suppressed count: 2
suppressed: close failed: B
suppressed: close failed: A
CASE initializer
open X
open failed: Y
close X
caught: init failed: Y
```

### Phân tích kết quả

**Trường hợp body và cả hai lệnh đóng đều ném ngoại lệ:**

- Resource A mở trước, B mở sau.
- Phần thân ném `IllegalArgumentException("body failed")`. Đây là **ngoại lệ chính**.
- Java gọi `B.close()` trước, rồi `A.close()`; mỗi phương thức ném `IllegalStateException`.
- Hai lỗi khi đóng được thêm vào danh sách `getSuppressed()` của ngoại lệ chính theo thứ tự B rồi A.
- `catch (IllegalArgumentException)` chạy **sau khi hoàn thành quá trình đóng**, nên đọc được `getSuppressed().length == 2`.

**Trường hợp initializer thứ hai thất bại:**

- `first` khởi tạo thành công từ `open("X", false, false)`.
- `open("Y", true, false)` ném lỗi trước khi tạo `Tracked` thứ hai.
- Java đóng `first`; thân `try` không thực thi.
- Handler bắt `IllegalArgumentException("init failed: Y")`.
- Đối tượng `second` không được tạo, vì vậy không có dòng `close Y`.

Điểm chung: tài nguyên đã được khởi tạo thành công được đóng trước khi người gọi đi tiếp, bất kể lý do thoát là lỗi từ initializer hay lỗi từ phần thân.

## 11. Scope, vòng đời, ownership: ba câu hỏi không thể thay thế nhau

Ba khái niệm thường bị trộn lẫn:

| Khía cạnh | Câu hỏi | Cách xác định |
| --- | --- | --- |
| **Scope** | Mã hiện tại có nhìn thấy tên biến resource không? | Quy tắc khai báo và phạm vi khối Java |
| **Lifetime / trạng thái đóng** | Tài nguyên đang mở hay đã đóng? | Hợp đồng của `AutoCloseable` và API cụ thể |
| **Ownership** | Ai chịu trách nhiệm đóng tài nguyên? | Thiết kế hàm/API và quy ước sở hữu |

Ví dụ một phương thức **nhận** reader từ caller:

```java
static String readOneLine(java.io.BufferedReader reader)
        throws java.io.IOException {
    return reader.readLine();
}
```

Nếu caller vẫn sở hữu reader và muốn đọc nhiều lần, phương thức `readOneLine` thường **không nên tự đóng** reader mà nó không sở hữu. Ngược lại, hàm tự mở tệp riêng cho một thao tác thường nên tự đóng bằng `try-with-resources` trong phạm vi đó.

Ví dụ phương thức tự sở hữu reader:

```java
static String readFirstLine(java.nio.file.Path path)
        throws java.io.IOException {
    try (var reader = java.nio.file.Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
```

`reader` chỉ nằm trong scope của `try`; caller nhận kết quả `String` nhưng không nắm resource. Cách này giúp encapsulation và giảm nguy cơ dùng tài nguyên sau khi đóng.

Không nên mở tài nguyên, trả trực tiếp một đối tượng phụ thuộc vào tài nguyên ấy rồi đóng tài nguyên trước khi caller sử dụng, trừ khi API đã định nghĩa rõ dữ liệu trả về độc lập với resource. Ví dụ, trả về một `Stream<String>` đọc lười từ file sau khi reader bị đóng có thể gây lỗi khi caller duyệt stream.

## 12. Dùng resource sau khi `try`: tên biến còn không có nghĩa là còn dùng được

Với biến khai báo ngoài:

```java
var stream = java.nio.file.Files.newInputStream(path);

try (stream) {
    System.out.println(stream.read());
}

int next = stream.read(); // Cố ý sai về vòng đời tài nguyên.
```

Đoạn trên có thể **hợp lệ về phạm vi và kiểu**, nhưng đọc sau khi đóng là hành vi không phù hợp với hợp đồng của phần lớn stream đọc tệp và có thể ném `IOException`. Nên bỏ dòng đọc cuối.

Nếu một phương thức cần sử dụng tài nguyên trong nhiều bước, hãy gộp những bước thật sự cần tài nguyên **trước khi thoát `try`**:

```java
try (var stream = java.nio.file.Files.newInputStream(path)) {
    int first = stream.read();
    int second = stream.read();
    consume(first, second);
}
```

Đây là **đoạn minh họa**, giả định `consume` đã được định nghĩa và mã xử lý `IOException`. Nếu cần dữ liệu sau khi đóng, đọc/copy dữ liệu sang dạng độc lập trước khi rời khối, thay vì đưa resource còn phụ thuộc tới caller.

### Resource không nhất thiết chỉ “đóng một lần”

Khi đóng stream bọc, reader, wrapper hoặc resource được chia sẻ giữa nhiều thành phần, một đối tượng có thể bị gọi `close()` nhiều lần qua các đường quản lý khác nhau. Java không bảo đảm **mọi lớp `AutoCloseable` đều chịu được đóng nhiều lần giống nhau**. Cần đọc hợp đồng loại tài nguyên cụ thể và tránh đăng ký đóng trùng một đối tượng khi không cần.

Nếu resource còn được dùng bởi thành phần khác, việc đóng trong `try-with-resources` hiện tại có thể phá vỡ công việc bên ngoài. Vì thế `try-with-resources` nên áp dụng cho tài nguyên mà phạm vi hiện tại **chịu trách nhiệm sở hữu và đóng**.

## 13. Resource trong `try` lồng nhau

Có thể lồng nhiều vùng quản lý tài nguyên:

```java
try (OuterResource outer = openOuter()) {
    useOuter(outer);

    try (InnerResource inner = openInner(outer)) {
        useInner(inner);
    }

    continueWithOuter(outer);
}
```

Đây là **cấu trúc minh họa**, các kiểu/phương thức cần được định nghĩa. Ý nghĩa:

1. `outer` được mở và nằm trong scope của toàn bộ thân `try` ngoài.
2. `inner` được mở trong `try` trong; tên nó chỉ ở phạm vi trong.
3. Khi rời `try` trong, `inner` được đóng.
4. `outer` vẫn còn nằm trong vùng quản lý của `try` ngoài và có thể tiếp tục được dùng **nếu API/ownership không khiến việc đóng `inner` đồng thời đóng `outer`**.
5. Khi rời `try` ngoài, `outer` được đóng.

Ví dụ này nhấn mạnh rằng thứ tự scope là có tính lồng nhau. Tuy nhiên, một wrapper `inner` có thể sở hữu resource `outer` và đóng nó khi `inner.close()` chạy. Khi đó câu `continueWithOuter(outer)` có thể không hợp lệ về **vòng đời**, dù hợp lệ về **scope**. Hãy đọc hợp đồng ownership của lớp wrapper.

## 14. Ngoại lệ khi đóng và thời điểm `catch` chạy

Một mô hình dễ nhớ:

```text
Khởi tạo resource theo thứ tự khai báo
                 ↓
          Chạy thân try
                 ↓
Thoát try: bình thường / return / throw
                 ↓
Đóng các resource đã khởi tạo, ngược thứ tự
                 ↓
       catch tương thích, nếu có
                 ↓
       finally đi kèm, nếu có
                 ↓
Tiếp tục, trả giá trị hoặc ném ngoại lệ theo kết quả cuối
```

Vì đóng xảy ra trước `catch` cùng cấp, handler có thể bắt được ngoại lệ khi `close()` ném lỗi. Trường hợp thân `try` cũng ném lỗi, đối tượng lỗi đóng thường có mặt dưới dạng suppressed exception của lỗi chính theo quy tắc `try-with-resources`.

### Nếu phần thân định `return` nhưng `close()` ném lỗi?

Giả sử:

```java
static int readValue() {
    try (ClosingResource r = new ClosingResource()) {
        return 42;
    }
}
```

Đây là **khung minh họa**, `ClosingResource` cần là lớp `AutoCloseable` đã định nghĩa. Nếu `close()` ném unchecked `IllegalStateException`, phương thức **không trả `42`**; ngoại lệ đóng có thể lan ra. Nếu `close()` ném checked exception thì phương thức còn phải tuân thủ hợp đồng `catch`/`throws`.

Ngược lại, nếu **phần thân ném ngoại lệ E1** rồi `close()` ném E2, `try-with-resources` ưu tiên E1 là lỗi chính và thêm E2 vào suppressed. Đây là khác biệt với `finally` thủ công ném E2 có thể trực tiếp ghi đè E1.

### Nếu phần thân chạy thành công, `close()` vẫn có thể thất bại

`try-with-resources` không “nuốt mọi lỗi đóng” để bảo đảm thành công. Nếu chỉ có lỗi đóng, lỗi đó trở thành ngoại lệ được xử lý/lan truyền. Vì vậy một phép ghi có thể ghi xong phần thân nhưng lại gặp lỗi khi flush/close, dẫn tới thất bại cuối cùng; cần xử lý dựa trên hợp đồng thao tác cụ thể.

## 15. Hướng dẫn thiết kế API và lựa chọn phạm vi

### Mở tài nguyên càng gần phạm vi sử dụng càng tốt

Khi một bước chỉ cần reader trong một phương thức, thường nên viết:

```java
static long countLines(java.nio.file.Path path)
        throws java.io.IOException {
    try (var reader = java.nio.file.Files.newBufferedReader(path)) {
        long count = 0;
        while (reader.readLine() != null) {
            count++;
        }
        return count;
    }
}
```

Đây là phương thức minh họa có thể đặt trong một lớp Java. Reader được đóng khi rời phạm vi, dù có ngoại lệ trong lúc đọc. Phương thức trả một số `long` độc lập với trạng thái reader, nên caller không cần tự quản lý tài nguyên.

### Không kéo dài scope chỉ vì muốn log tên resource

Nếu cần bối cảnh trong `catch`, lưu **dữ liệu mô tả phù hợp** ở ngoài resource specification:

```java
String logicalName = "configuration";

try (var reader = java.nio.file.Files.newBufferedReader(path)) {
    System.out.println(reader.readLine());
} catch (java.io.IOException ex) {
    System.out.println("Cannot read " + logicalName);
}
```

Ở đây `logicalName` nằm ngoài `try` nên handler truy cập được. Không cần đưa `reader` ra ngoài chỉ để đọc một chuỗi mô tả; tên resource không nằm trong scope của handler và resource đã được đóng trước khi handler chạy.

### Đừng vô tình đóng tài nguyên không thuộc quyền sở hữu

Ví dụ `System.in` là stream tiêu chuẩn của tiến trình. Nếu một phạm vi ngắn tự đóng một wrapper sở hữu `System.in`, các phần khác của chương trình có thể không đọc được đầu vào nữa. Trước khi đăng ký resource trong `try-with-resources`, hãy xác định **ai cấp phát, ai sử dụng tiếp và ai chịu trách nhiệm đóng**.

### Kết hợp với logging và handler ở đúng tầng

Tầng thao tác nên tự quản lý reader hoặc stream của mình; tầng caller chỉ cần xử lý `IOException` theo hợp đồng. Không yêu cầu caller biết resource tên gì hoặc phải gọi `close()` thủ công trên biến mà nó không sở hữu.

Một `catch` quá rộng rồi trả dữ liệu “thành công giả” có thể che lỗi khi đọc. Chỉ chọn fallback nếu đó là chính sách thật. Nếu dữ liệu bắt buộc, việc báo lỗi phù hợp thường tốt hơn trả `null` hoặc chuỗi rỗng.

## 16. Những lỗi thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Dùng tên resource khai báo trong `try (...)` ở `catch` | Resource variable không nằm trong scope của handler | Dùng metadata khai báo ngoài, không truy cập resource để đóng lại |
| Gọi resource sau khi `try (existingResource)` kết thúc | Biến có thể còn scope nhưng object đã đóng | Dùng toàn bộ thao tác phụ thuộc trước khi thoát `try` |
| Gán lại biến resource khai báo trong ngoặc | Resource variable ngầm `final` | Không gán lại; dùng biến mới khi cần |
| Gán lại biến rồi dùng `try (variable)` | Biến cục bộ không còn *effectively final* | Khai báo mới trong `try` hoặc giữ một tham chiếu không bị gán lại |
| Tưởng `AutoCloseable` luôn chỉ ném `IOException` | `close()` có thể khai báo checked `Exception` hoặc kiểu khác | Kiểm tra chữ ký kiểu resource và hợp đồng `throws` |
| Tưởng resource thứ nhất không đóng nếu mở thứ hai lỗi | Java đóng các resource đã khởi tạo thành công | Tin cậy cơ chế khởi tạo/đóng của `try-with-resources` |
| Tưởng nhiều resource đóng từ trái sang phải | Java đóng theo thứ tự ngược | Kiểm tra phụ thuộc để quản lý ownership |
| Cố bắt lỗi `close()` bằng cách đóng lại trong `catch` | Lần đóng tự động đã xảy ra, có thể gây lỗi mới | Xử lý exception, suppressed và chính sách vận hành |
| Trả một stream lazy phụ thuộc reader đã bị đóng | Caller sử dụng dữ liệu sau khi nguồn đóng | Giữ vòng đời sở hữu đúng phạm vi hoặc trả dữ liệu đã vật hóa |
| Bọc stream rồi đăng ký đóng cả wrapper và nguồn không cần thiết | Có thể double-close và làm mờ ownership | Xác định lớp nào đóng nguồn bên dưới |
| Đóng tài nguyên được cho mượn từ caller | Có thể làm hỏng công việc của caller | Thống nhất hợp đồng ai đóng resource |
| Bỏ qua suppressed exceptions khi body và close cùng lỗi | Mất bối cảnh lỗi đóng phụ | Xem `getSuppressed()` nếu cần chẩn đoán |

## 17. Bài tập tự kiểm tra

**Bài A.** Resource khai báo `try (var reader = open())` có thể được dùng ở `catch` cùng cấp không?

**Không.** Tên `reader` không thuộc phạm vi của `catch`. Tuy nhiên, ngoại lệ từ khởi tạo, đọc hoặc đóng reader vẫn có thể đến handler thích hợp.

**Bài B.** Một biến `reader` khai báo trước `try (reader)` (Java 17) có còn trong scope sau cấu trúc không?

**Có**, theo phạm vi khai báo ngoài. Nhưng reader đã được đóng; không nên đọc tiếp chỉ vì tên biến còn dùng được.

**Bài C.** Trong `try (R a = openA(); R b = openB())`, resource nào được đóng trước?

**`b`**, rồi `a`, nếu cả hai được khởi tạo thành công.

**Bài D.** `openA()` thành công, `openB()` ném lỗi. Phần thân `try` có chạy không, và `a` có đóng không?

**Phần thân không chạy; `a` được đóng.** Nếu `a.close()` cũng lỗi, lỗi đóng có thể bị suppressed dưới lỗi khởi tạo `b`.

**Bài E.** Có thể viết `try (resource)` khi `resource` là biến cục bộ đã bị gán lại không?

**Không** theo cú pháp Java 9+ này: biến cục bộ phải `final` hoặc *effectively final*. Dùng một biến mới không gán lại hoặc khai báo trực tiếp trong resource specification.

**Bài F.** `close()` ném một `IllegalStateException` trong khi phần thân `try` đã ném `IllegalArgumentException`. Với `try-with-resources`, lỗi nào là lỗi chính?

Thông thường **`IllegalArgumentException` từ thân `try`** là lỗi chính; lỗi lúc đóng xuất hiện trong `getSuppressed()` của nó.

**Bài G.** Phần thân `try` chuẩn bị `return 42`, nhưng resource `close()` ném lỗi. Caller có chắc nhận `42` không?

**Không.** Nếu lỗi từ `close()` không được xử lý, lời gọi có thể kết thúc bằng ngoại lệ thay vì trả `42`.

**Bài H.** Một reader bọc input stream và tự đóng input stream khi reader đóng. Có nhất thiết khai báo cả hai trong danh sách resource không?

**Không nhất thiết.** Nếu reader sở hữu và đóng stream, thường chỉ đăng ký reader là đủ. Đọc hợp đồng lớp và ownership để tránh đóng lặp hoặc sử dụng sau đóng.

**Bài I.** Resource variable khai báo trong resource specification có thể thay đổi trạng thái đối tượng không?

**Có**, nếu API cho phép. Biến resource ngầm `final` chỉ cấm **gán lại tham chiếu**, không khiến đối tượng bất biến.

**Bài J.** Có nên để phương thức nhận reader do caller sở hữu tự đóng nó trong mọi trường hợp?

**Không mặc định.** Quyết định dựa vào hợp đồng ownership. Phương thức mượn reader để đọc thường không nên tự đóng nếu caller còn cần sử dụng tiếp.

## 18. Checklist áp dụng trong dự án Java

Trước khi viết `try-with-resources`, hãy kiểm tra:

1. **Resource có triển khai `AutoCloseable` không?** Nếu không, nó không phải resource hợp lệ theo cú pháp này.
2. **Ai sở hữu resource?** Có phải phạm vi hiện tại cần đóng nó khi xong hay không?
3. **Khai báo biến ở đâu?** Khai báo mới trong ngoặc `try` nếu chỉ dùng cục bộ; dùng `try (existingResource)` khi biến bên ngoài là `final`/*effectively final* và mục tiêu quản lý vòng đời phù hợp.
4. **Tất cả thao tác cần resource đã nằm trước khi khối kết thúc chưa?** Đừng trả về một đối tượng còn phụ thuộc vào resource đã đóng.
5. **Có nhiều resource không?** Xác minh thứ tự khởi tạo trái→phải và đóng phải→trái, đặc biệt với wrapper sở hữu nguồn.
6. **Initializer có thể ném lỗi không?** Resource đã khởi tạo trước đó sẽ được đóng; phần thân `try` có thể chưa hề chạy.
7. **`close()` có thể ném checked exception nào?** Xác định kiểu tĩnh và chữ ký `throws` cần xử lý.
8. **Thời điểm `catch` chạy đã đúng chưa?** Resource được đóng trước khi handler cùng cấp nhận lỗi.
9. **Có cần điều tra suppressed exception không?** Khi body và close cùng lỗi, đừng chỉ xem message chính rồi bỏ mất tình trạng dọn dẹp.
10. **Biến resource có bị gán lại không?** Biến khai báo trong resource specification ngầm `final`; biến ngoài phải giữ `final`/*effectively final* khi dùng `try (variable)`.
11. **Người gọi có biết cách xử lý lỗi không?** Tầng thấp quản lý resource; tầng phù hợp quyết định phục hồi, trả lỗi hoặc retry.
12. **Có dùng resource sau khi đóng không?** Scope và vòng đời không phải một. Cần dừng dùng resource khi vùng quản lý của nó kết thúc.

## Kết luận

`try-with-resources` gắn **vòng đời của tài nguyên** với **một vùng thực thi xác định**. Khi khai báo resource mới trong `try (...)`, tên biến được sử dụng trong phạm vi tài nguyên và phần thân `try`, nhưng không ở `catch`, `finally` hoặc câu lệnh sau cấu trúc. Khi dùng `try (existingResource)` từ Java 9 trở lên, biến bên ngoài có thể vẫn còn scope nhưng **đối tượng đã được đóng**. Với nhiều resource, Java **khởi tạo từ trái sang phải, đóng từ phải sang trái**, đóng cả những resource đã mở nếu initializer sau thất bại, và có cơ chế **suppressed exceptions** để không đánh mất lỗi chính khi đóng tài nguyên cũng lỗi.

Hiểu rõ **scope, lifetime và ownership** giúp viết mã Java đúng hợp đồng, tránh dùng tài nguyên sau khi đóng và hạn chế rò rỉ tài nguyên cùng các lỗi bị che khuất.