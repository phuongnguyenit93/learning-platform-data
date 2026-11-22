# Mục đích và cú pháp try-with-resources từ Java 7

> **Bối cảnh:** Java Core → Exception → Try-with-resources. Từ **Java 7**, Java cung cấp cấu trúc **try-with-resources** (thường viết tắt **TWR**) để tự động gọi `close()` trên các đối tượng tài nguyên khi rời khối `try`. Cấu trúc này giúp tránh quên đóng file, stream, socket, JDBC resource và nhiều đối tượng `AutoCloseable` khác, kể cả khi thao tác chính ném exception. Từ Java 9, cú pháp được mở rộng để sử dụng một số biến tài nguyên đã khai báo sẵn; quy tắc cốt lõi vẫn là tự đóng tài nguyên và bảo toàn lỗi theo thứ tự xác định.

## 1. Vì sao cần try-with-resources?

Một chương trình Java thường sử dụng **tài nguyên có vòng đời**: file, stream, reader, writer, kết nối, result set hoặc đối tượng quản lý tài nguyên do ứng dụng tự tạo. Nhiều tài nguyên ngoài heap (file descriptor, socket, connection, native handle) cần được đóng đúng lúc; chỉ chờ garbage collector không phải chính sách giải phóng tài nguyên đáng tin cậy.

Đoạn mã dễ mắc lỗi:

```java
// Minh họa ý tưởng bên trong một method, chưa phải chương trình độc lập.
java.io.BufferedReader reader =
        new java.io.BufferedReader(new java.io.FileReader("input.txt"));

String line = reader.readLine();
System.out.println(line);
reader.close();
```

Nếu `readLine()` hoặc `println(...)` phát sinh exception trước `reader.close()`, đường thực thi bình thường bị gián đoạn và câu `close()` **không được gọi**. Đoạn trên cũng thiếu chính sách xử lý checked `IOException` và phụ thuộc file trên đĩa.

Trước Java 7, cách thường gặp là dùng `finally` với nhiều mã dọn dẹp thủ công:

```java
// Phương thức minh họa hợp lệ khi đặt bên trong một lớp.
static String readFirstLineBeforeJava7(String path)
        throws java.io.IOException {
    java.io.BufferedReader reader = null;
    try {
        reader = new java.io.BufferedReader(
                new java.io.FileReader(path));
        return reader.readLine();
    } finally {
        if (reader != null) {
            reader.close();
        }
    }
}
```

Cách này tốt hơn quên `close()`, nhưng vẫn có các khó khăn:

- Phải tự khai báo biến ngoài `try`, kiểm tra `null` và viết `finally`.
- Khi có nhiều tài nguyên, mã dọn dẹp dễ dài, lặp, hoặc bỏ sót.
- Khi phần thân `try` **và** `close()` đều ném exception, một exception từ `finally` có thể **che mất lỗi gốc** nếu không tự xử lý cẩn thận.
- Mọi nhánh `return`/exception đều phải được suy xét để bảo đảm dọn dẹp và giữ nguyên thông tin chẩn đoán.

TWR giải quyết phần lớn việc **quản lý vòng đời đóng tài nguyên**:

```java
// Phương thức minh họa hợp lệ khi đặt bên trong một lớp.
static String readFirstLine(String path) throws java.io.IOException {
    try (java.io.BufferedReader reader =
                 new java.io.BufferedReader(
                         new java.io.FileReader(path))) {
        return reader.readLine();
    }
}
```

Khi rời cấu trúc `try`, Java tự gọi `reader.close()` theo quy tắc ngôn ngữ; ta không cần viết `finally` chỉ để đóng `reader`.

**Giới hạn:** TWR không bảo đảm thao tác đọc/ghi thành công, không tự rollback dữ liệu đã ghi và không cứu được mọi trường hợp process/JVM bị kết thúc bất thường. Nó giải quyết **vòng đời tài nguyên** theo cơ chế Java, không tự thay thế transaction hay recovery nghiệp vụ.

## 2. Cú pháp gốc được hỗ trợ từ Java 7

Dạng phổ biến nhất:

```java
try (ResourceType resource = resourceInitializer) {
    // Sử dụng resource.
}
```

Trong đó:

- `try` mở đầu cấu trúc.
- Dấu ngoặc tròn `(...)` là **resource specification**, chứa một hoặc nhiều khai báo tài nguyên.
- Mỗi tài nguyên phải có kiểu tương thích với `java.lang.AutoCloseable`.
- `resourceInitializer` tạo/nhận đối tượng; nếu khởi tạo thành công, tài nguyên thuộc phạm vi được TWR quản lý.
- Dấu ngoặc nhọn `{...}` chứa công việc chính.
- Kết thúc khối (bình thường, `return`, `break`, `continue` hợp lệ, hoặc exception), các tài nguyên đã khởi tạo được đóng theo quy tắc.
- `catch` và `finally` có thể được gắn thêm nếu cần xử lý lỗi/dọn các trạng thái khác; **không bắt buộc phải có**.

Ví dụ tối thiểu:

```java
try (java.io.StringReader reader = new java.io.StringReader("Java")) {
    System.out.println(reader.read());
}
```

Đây là một đoạn code bên trong method, không phải file độc lập. `StringReader` hỗ trợ `Closeable` nên dùng được trong TWR. `reader.read()` trả về mã Unicode của ký tự đầu tiên (ở đây ký tự `J`); ví dụ chỉ minh họa cú pháp.

### 2.1. Một tài nguyên hoặc nhiều tài nguyên

TWR với nhiều tài nguyên trong Java 7:

```java
try (FirstResource first = openFirst();
     SecondResource second = openSecond()) {
    // Dùng cả first và second.
}
```

Đây là **mã minh họa**; `FirstResource`/`SecondResource`/`openFirst()`/`openSecond()` cần được định nghĩa. Dấu `;` ngăn cách các tài nguyên; có thể đặt xuống dòng để dễ đọc. Java khởi tạo theo thứ tự **từ trái sang phải**, sau đó đóng theo thứ tự **ngược lại**.

Ví dụ thực tế với reader/writer:

```java
try (java.io.BufferedReader reader =
                 new java.io.BufferedReader(new java.io.FileReader("in.txt"));
     java.io.BufferedWriter writer =
                 new java.io.BufferedWriter(new java.io.FileWriter("out.txt"))) {
    String line;
    while ((line = reader.readLine()) != null) {
        writer.write(line);
        writer.newLine();
    }
}
```

Đây là đoạn dùng I/O thật, cần đặt trong method có `throws IOException` hoặc handler phù hợp và có hai tệp/dường dẫn thích hợp. Khi rời khối, `writer` được đóng **trước** `reader`, không phụ thuộc thứ tự ta sử dụng chúng trong thân.

### 2.2. Có thể dùng `catch` và `finally` cùng TWR

```java
try (MyResource resource = open()) {
    use(resource);
} catch (java.io.IOException e) {
    report(e);
} finally {
    finishRequest();
}
```

Đoạn chỉ là mẫu, `MyResource` và các method chưa được định nghĩa. Điểm đáng nhớ là **đóng tài nguyên diễn ra trước khi thực thi các `catch`/`finally` gắn với cấu trúc đó**. Vì vậy handler có thể nhận cả lỗi từ thân `try` lẫn lỗi phát sinh trong quá trình `close()`, tùy kiểu và thứ tự ngoại lệ.

Không cần viết `finally { resource.close(); }` chỉ vì muốn đóng lại tài nguyên đã được TWR quản lý. Đóng thủ công lần hai có thể gây lỗi hoặc side effect tùy implementation; để TWR chịu trách nhiệm đóng.

## 3. Điều kiện kiểu: tài nguyên phải là `AutoCloseable`

`java.lang.AutoCloseable` được đưa vào Java 7; interface này có phương thức:

```java
public interface AutoCloseable {
    void close() throws Exception;
}
```

Đây là **khai báo API minh họa**, không phải toàn bộ mã nguồn JDK. `AutoCloseable` thiết lập giao thức đóng tài nguyên khi thoát phạm vi.

Các kiểu quen thuộc:

- `java.io.InputStream`, `OutputStream`, `Reader` và `Writer` thuộc nhánh các kiểu đóng được trong hệ I/O.
- `java.io.Closeable` kế thừa `AutoCloseable`; `close()` của `Closeable` khai báo `throws IOException`, hẹp hơn `throws Exception`.
- `java.sql.Connection`, `Statement` và `ResultSet` hỗ trợ `AutoCloseable`, với phương thức đóng có thể ném `SQLException`.
- Lớp tự tạo có thể `implements AutoCloseable` để đưa vòng đời riêng vào TWR.

Điều kiện không phải “tài nguyên bắt buộc là file” hoặc “bắt buộc khai báo checked exception”. Bất kỳ đối tượng nào triển khai giao thức `AutoCloseable` phù hợp đều có thể được quản lý.

### 3.1. Hai interface liên quan nhưng không đồng nhất

| Đặc điểm | `AutoCloseable` | `Closeable` |
| --- | --- | --- |
| Xuất hiện | Java 7 | Trước Java 7; từ Java 7 là subtype của `AutoCloseable` |
| Phương thức cốt lõi | `close() throws Exception` | `close() throws IOException` |
| Kiểu lỗi checked tối đa theo chữ ký interface | `Exception` | `IOException` |
| Có thể dùng trong TWR? | Có | Có |
| Giao ước về đóng lặp lại | Không bảo đảm mọi implementation idempotent | Giao ước của `Closeable.close()` yêu cầu đóng resource đã đóng không có tác dụng |

Nếu khai báo tài nguyên dưới kiểu `AutoCloseable`, compiler có thể buộc method xử lý/khai báo `Exception` ngay cả khi đối tượng runtime cụ thể có `close()` không ném checked exception. Với biến kiểu cụ thể hơn, compiler có thể nhìn thấy chữ ký `close()` hẹp hơn.

Lưu ý: các lớp `AutoCloseable` có thể tự định nghĩa `close()` không khai báo checked exception nào, ví dụ:

```java
final class SimpleResource implements AutoCloseable {
    @Override
    public void close() {
        System.out.println("Đã đóng");
    }
}
```

Đây là một lớp hợp lệ nhưng chưa có `main`. Không cần `throws Exception` ở `close()` vì implementation được phép thu hẹp tập checked exception của interface.

### 3.2. Code nào không dùng được trong resource specification?

Các kiểu không thực hiện `AutoCloseable` không hợp lệ:

```java
// Ví dụ CỐ Ý SAI, không biên dịch:
try (String message = "hello") {
    System.out.println(message);
}
```

`String` không triển khai `AutoCloseable`. Việc biến “có thể thoát khỏi phạm vi” không đủ; TWR cần khả năng gọi `close()` theo interface.

Một lỗi khác là quên **dấu ngoặc tròn** hoặc viết danh sách tài nguyên như tham số thông thường:

```java
// CỐ Ý SAI:
try (new java.io.StringReader("x")) {
    // Trong Java 7 không được dùng biểu thức tạo object trực tiếp như khai báo.
}
```

Trong cú pháp Java 7, resource phải được khai báo bằng biến trong `(...)`. Java 9 mở rộng khả năng dùng một biến đã khai báo sẵn và effectively final, được giải thích ở Mục 8.

## 4. Chương trình Java 17 số 1: tự đóng sau đường thành công và thất bại

Ví dụ không phụ thuộc file trên đĩa. Ta tự cài một resource để quan sát chính xác `close()` được gọi khi nào.

Tạo tệp `TryWithResourcesBasics.java`:

```java
public class TryWithResourcesBasics {
    static final class TrackedResource implements AutoCloseable {
        private final String name;

        TrackedResource(String name) {
            this.name = name;
            System.out.println("Mở " + name);
        }

        void use() {
            System.out.println("Dùng " + name);
        }

        @Override
        public void close() {
            System.out.println("Đóng " + name);
        }
    }

    static void run(boolean fail) {
        try (TrackedResource resource = new TrackedResource("R")) {
            resource.use();
            if (fail) {
                throw new IllegalStateException("Thao tác lỗi");
            }
            System.out.println("Thân try thành công");
        } catch (IllegalStateException e) {
            System.out.println("Bắt: " + e.getMessage());
        } finally {
            System.out.println("Kết thúc run");
        }
    }

    public static void main(String[] args) {
        run(false);
        System.out.println("---");
        run(true);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 TryWithResourcesBasics.java
java TryWithResourcesBasics
```

Stdout chính xác:

```text
Mở R
Dùng R
Thân try thành công
Đóng R
Kết thúc run
---
Mở R
Dùng R
Đóng R
Bắt: Thao tác lỗi
Kết thúc run
```

**Phân tích:**

1. Lượt `run(false)` tạo tài nguyên, sử dụng và hoàn tất thân `try`. `close()` được gọi **trước khi** ra khỏi cấu trúc, rồi chạy `finally`.
2. Lượt `run(true)` ném `IllegalStateException` ngay trong thân. Dòng “Thân try thành công” không chạy; TWR vẫn gọi `close()` rồi mới chạy `catch`.
3. `catch` xử lý lỗi nghiệp vụ, không phải nơi chịu trách nhiệm đóng resource. `finally` ở đây chỉ minh họa tác vụ chung ngoài việc đóng tài nguyên.
4. Resource được mở mới mỗi lần gọi; đầu ra không phụ thuộc GC, thời gian hoặc file hệ thống.

**Không nên kết luận mọi chương trình luôn hoàn thành close:** TWR thực hiện lệnh đóng theo luồng điều khiển Java; dừng JVM/process bất thường, lỗi native hoặc sự cố nghiêm trọng có thể làm điều này không diễn ra. Những sự kiện đó cần chính sách độ bền dữ liệu riêng.

## 5. Thứ tự khởi tạo và thứ tự đóng nhiều tài nguyên

Java khởi tạo theo thứ tự tài nguyên xuất hiện trong `(...)`, từ **trái sang phải**. Khi rời phạm vi TWR, Java đóng chúng theo **thứ tự ngược lại**: tài nguyên cuối được khai báo sẽ được đóng trước.

Tạo `ResourceCloseOrderDemo.java`:

```java
public class ResourceCloseOrderDemo {
    static final class NamedResource implements AutoCloseable {
        private final String name;

        NamedResource(String name) {
            this.name = name;
            System.out.println("Mở " + name);
        }

        @Override
        public void close() {
            System.out.println("Đóng " + name);
        }
    }

    public static void main(String[] args) {
        try (NamedResource first = new NamedResource("A");
             NamedResource second = new NamedResource("B");
             NamedResource third = new NamedResource("C")) {
            System.out.println("Thân try");
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ResourceCloseOrderDemo.java
java ResourceCloseOrderDemo
```

Stdout:

```text
Mở A
Mở B
Mở C
Thân try
Đóng C
Đóng B
Đóng A
```

Thứ tự này giúp viết pipeline: nếu tài nguyên `B` sử dụng tài nguyên `A`, khai báo `A` trước rồi `B` sau thường cho phép đóng `B` trước khi đóng `A`.

### 5.1. Nếu một resource initializer thất bại?

Một ưu điểm quan trọng: những resource **đã khởi tạo thành công trước đó** vẫn được đóng, ngay cả khi việc tạo tài nguyên sau bị lỗi.

Ví dụ ý tưởng:

```java
try (Resource first = openFirst();
     Resource second = openSecondThatThrows()) {
    work(first, second);
}
```

Đây là mã minh họa; các lớp và method chưa được định nghĩa. Nếu `openFirst()` thành công nhưng `openSecondThatThrows()` ném exception, `first` vẫn được đóng theo quy tắc. `second` chưa được khởi tạo thành công nên không được đóng như một resource đã có. Nếu `openSecondThatThrows()` đã cấp phát tài nguyên bên trong rồi tự ném mà chưa trả object, trách nhiệm dọn nội bộ của nó vẫn thuộc implementation của chính hàm khởi tạo; TWR bên ngoài không thể đóng một tài nguyên chưa nhận được.

### 5.2. Khởi tạo resource có giá trị `null`

Một initializer có thể cho ra `null` đối với kiểu tham chiếu resource. Quy tắc TWR **không gọi `close()` trên resource có giá trị `null`**. Điều này khác với việc gọi trực tiếp `resource.close()` khi `resource == null`, vốn ném `NullPointerException`.

Dù ngôn ngữ xử lý được trường hợp này, API không nên dùng giá trị `null` làm resource hợp lệ một cách mơ hồ. Cần thể hiện rõ trường hợp “không mở được” qua hợp đồng, exception hoặc kết quả có cấu trúc phù hợp.

## 6. Trường hợp đặc biệt: cả thân try và `close()` đều ném exception

Đây là lý do TWR tốt hơn một `finally` đơn giản trong nhiều trường hợp. Java không bỏ mất lỗi chính chỉ vì `close()` cũng lỗi.

**Khái niệm:**

- **Primary exception:** ngoại lệ thoát ra từ thân `try`/giai đoạn thao tác đang được ưu tiên giữ nguyên.
- **Suppressed exception:** ngoại lệ phát sinh khi đóng tài nguyên trong lúc một ngoại lệ chính đã tồn tại; được gắn vào đối tượng chính qua `Throwable.addSuppressed(...)` theo cơ chế TWR.
- `Throwable.getSuppressed()` trả về mảng các ngoại lệ đã được ghi nhận theo cách này.
- `getCause()` và `getSuppressed()` là hai quan hệ khác nhau: cause diễn tả chuỗi nguyên nhân, suppressed ghi nhận lỗi phụ trong quá trình dọn dẹp.

### 6.1. Ví dụ Java 17 số 3: primary và suppressed

Tạo `SuppressedExceptionDemo.java`:

```java
import java.io.IOException;

public class SuppressedExceptionDemo {
    static final class BrokenClose implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("Đang đóng");
            throw new IOException("Lỗi đóng");
        }
    }

    public static void main(String[] args) {
        try (BrokenClose resource = new BrokenClose()) {
            System.out.println("Đang xử lý");
            throw new IOException("Lỗi xử lý");
        } catch (IOException e) {
            System.out.println("Primary: " + e.getMessage());
            System.out.println("Số suppressed: "
                    + e.getSuppressed().length);
            System.out.println("Suppressed: "
                    + e.getSuppressed()[0].getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 SuppressedExceptionDemo.java
java SuppressedExceptionDemo
```

Stdout:

```text
Đang xử lý
Đang đóng
Primary: Lỗi xử lý
Số suppressed: 1
Suppressed: Lỗi đóng
```

**Luồng thực thi:**

1. Resource được tạo thành công.
2. Thân `try` in “Đang xử lý” rồi ném `IOException("Lỗi xử lý")`.
3. Java vẫn gọi `resource.close()`; method in “Đang đóng” rồi ném `IOException("Lỗi đóng")`.
4. Exception từ thân là **primary**. Lỗi từ `close()` được **suppress** vào exception chính.
5. `catch (IOException e)` nhận exception chính, dùng `getSuppressed()` để xem lỗi khi đóng.

Nếu chỉ dùng `finally { resource.close(); }` trong một mẫu cũ không xử lý riêng lỗi đóng, exception từ `close()` có thể thay thế lỗi ban đầu và làm mất thông tin quan trọng về nguyên nhân thao tác.

### 6.2. Nếu thân `try` thành công nhưng `close()` ném lỗi?

Khi chưa có primary exception từ thân `try`, lỗi phát sinh lúc `close()` có thể trở thành **exception chính thoát khỏi construct**. Nói “TWR luôn ưu tiên lỗi từ thân `try`” chỉ đúng **khi lỗi thân tồn tại**.

Với nhiều tài nguyên, nếu thân thành công nhưng một hoặc nhiều `close()` thất bại, lỗi đóng từ **resource được đóng đầu tiên** (resource khai báo cuối) là lỗi chính và các lỗi đóng sau có thể trở thành suppressed exceptions.

### 6.3. Ví dụ Java 17 số 4: hai lần đóng đều lỗi

Tạo `MultipleCloseFailuresDemo.java`:

```java
import java.io.IOException;

public class MultipleCloseFailuresDemo {
    static final class Failing implements AutoCloseable {
        private final String name;

        Failing(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            System.out.println("Đóng " + name);
            throw new IOException("close " + name);
        }
    }

    public static void main(String[] args) {
        try (Failing first = new Failing("A");
             Failing second = new Failing("B")) {
            System.out.println("Thân thành công");
        } catch (IOException e) {
            System.out.println("Primary: " + e.getMessage());
            System.out.println("Suppressed count: "
                    + e.getSuppressed().length);
            System.out.println("Suppressed first: "
                    + e.getSuppressed()[0].getMessage());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 MultipleCloseFailuresDemo.java
java MultipleCloseFailuresDemo
```

Stdout:

```text
Thân thành công
Đóng B
Đóng A
Primary: close B
Suppressed count: 1
Suppressed first: close A
```

Resource `B` được đóng trước. Khi `B.close()` thất bại, nó trở thành primary. Java tiếp tục đóng `A`; exception của `A.close()` được gắn suppressed.

**Lưu ý chẩn đoán:** nếu chỉ in `e.getMessage()` rồi bỏ qua suppressed exceptions, rất dễ không nhìn thấy các lỗi đóng thứ cấp. Một logger in stack trace đầy đủ của `Throwable` thường thể hiện các suppressed exceptions; nếu dùng định dạng log tự xây, nên xác nhận nó không làm mất thông tin này.

## 7. `catch` và `finally` chạy vào lúc nào?

Với cấu trúc:

```java
try (Resource r = open()) {
    use(r);
} catch (Exception e) {
    handle(e);
} finally {
    reportEnd();
}
```

Đây là mẫu minh họa phụ thuộc các định nghĩa phù hợp. Thứ tự khái quát:

```text
Khởi tạo tài nguyên
        ↓
Thân try
        ↓
Đóng tài nguyên theo thứ tự ngược
        ↓
catch phù hợp (nếu exception đang lan truyền)
        ↓
finally (nếu có và không bị sự cố kết thúc bất thường bên ngoài)
        ↓
Kết quả/exception tiếp tục về caller
```

Đối với `return` trong thân `try`, TWR cũng đóng các tài nguyên trước khi lời gọi hoàn tất bình thường. Nếu `close()` ném exception sau khi giá trị trả về đã được tính, lỗi đóng có thể khiến method **không hoàn tất bằng return dự kiến**. Không nên giả định rằng `return` miễn trách nhiệm đóng.

### 7.1. Khối `catch` có thể bắt cả lỗi thân và lỗi close

Trong ví dụ `SuppressedExceptionDemo`, `catch(IOException)` nhận lỗi thân; với ví dụ `MultipleCloseFailuresDemo`, nó nhận lỗi đóng. Cùng cú pháp nhưng nguồn primary khác nhau.

Compiler xét checked exceptions của initializer, các lời gọi trong thân **và `close()`**, nên ví dụ sau vẫn cần bắt/khai báo `IOException` ngay cả khi thân khối chỉ in văn bản:

```java
// Phương thức minh họa, Resource.close() throws IOException.
try (Resource r = new Resource()) {
    System.out.println("Không có I/O trong thân");
} catch (java.io.IOException e) {
    System.out.println("Đóng lỗi: " + e.getMessage());
}
```

Đây là đoạn giải thích giả định `Resource` đã được định nghĩa. Khi bạn thay resource bằng lớp có `close()` không khai báo checked exception, khả năng bắt checked `IOException` cũng cần được xem lại theo chính xác chữ ký của initializer và thân khối.

### 7.2. TWR không phải thứ tự xử lý `catch` thông thường bị đảo ngược

Java không gọi `catch` trước rồi mới đóng resource. Resource được đóng khi rời phần TWR; các handler gắn kèm chạy sau quy trình này. Đây là điểm khác với ý tưởng đặt `close()` trong chính `catch`, vốn bỏ sót đường thành công.

## 8. Cú pháp Java 7 khác gì với Java 9 và Java 10+?

Đây là điểm quan trọng khi đề bài yêu cầu **“từ Java 7”**: cần phân biệt tính năng ra đời với những cú pháp được bổ sung ở phiên bản sau.

### 8.1. Java 7: khai báo biến resource ngay trong ngoặc try

```java
try (java.io.BufferedReader reader =
             new java.io.BufferedReader(
                     new java.io.StringReader("Hello"))) {
    System.out.println(reader.readLine());
}
```

Đoạn này dùng cú pháp TWR từ Java 7. Biến `reader` được khai báo trong resource specification; nó không thể bị gán lại sau đó trong thân `try`. Sau khi TWR kết thúc, biến resource khai báo kiểu này nằm ngoài phạm vi sử dụng thông thường của code sau đó.

### 8.2. Java 9: dùng biến đã khai báo sẵn nếu `final` hoặc effectively final

Từ **Java 9**, có thể viết:

```java
java.io.BufferedReader reader =
        new java.io.BufferedReader(
                new java.io.StringReader("Hello"));
try (reader) {
    System.out.println(reader.readLine());
}
```

Đây là đoạn minh họa trong method, hợp lệ trên Java 9+ (gồm Java 17). `reader` được khai báo trước `try`, không bị gán lại sau khi khởi tạo, nên là **effectively final**. Cú pháp **`try (reader)` không có khai báo biến bên trong** không hợp lệ nếu biên dịch với chế độ ngôn ngữ Java 7.

Nếu `reader` được gán sang đối tượng khác sau khai báo, nó không còn effectively final và không đủ điều kiện dùng trực tiếp trong resource specification Java 9.

Đọc đúng ý nghĩa:

- `try (reader)` **không tự khởi tạo** resource mới; nó dùng đối tượng mà biến đã tham chiếu.
- Khi khối kết thúc, resource được **đóng**, dù biến `reader` vẫn còn nằm trong phạm vi từ vựng ngoài `try`.
- Biến còn tồn tại **không** có nghĩa đối tượng đã đóng có thể tiếp tục sử dụng. Phải tuân theo hợp đồng của resource.
- Nếu mở resource trước khi vào `try`, một exception xảy ra **giữa lúc mở và lúc bắt đầu `try`** có thể khiến resource chưa được TWR quản lý. Khi có thể, khai báo và khởi tạo ngay trong `try(...)` thường đơn giản hơn.

### 8.3. Java 10+: `var` trong khai báo resource

Java 10 giới thiệu local-variable type inference `var`, nên trong Java 10+ có thể viết:

```java
try (var reader =
             new java.io.BufferedReader(
                     new java.io.StringReader("Hello"))) {
    System.out.println(reader.readLine());
}
```

Đây cũng là đoạn minh họa hợp lệ ở Java 17. TWR xuất hiện từ Java 7, nhưng cú pháp `var` **không** được hỗ trợ ở Java 7 hoặc Java 9. Chọn cú pháp tùy phiên bản Java của dự án; nếu muốn ví dụ chạy trên Java 7, dùng khai báo kiểu tường minh trong ngoặc tài nguyên.

### 8.4. Tóm tắt phiên bản

| Phiên bản Java | Cú pháp tài nguyên tiêu biểu | Ghi nhớ |
| --- | --- | --- |
| Java 7/8 | `try (BufferedReader r = new BufferedReader(...))` | Khai báo resource trực tiếp trong `try`; có thể nhiều resource phân cách `;`. |
| Java 9 | `BufferedReader r = ...; try (r)` | Dùng biến có sẵn `final` hoặc effectively final. |
| Java 10+ | `try (var r = new BufferedReader(...))` | Dùng `var` cho biến resource cục bộ có initializer. |
| Java 17 | Hỗ trợ cả ba dạng phù hợp | Lựa chọn tùy mục tiêu tương thích mã nguồn và kiểu dữ liệu. |

**Đừng nói** “Java 7 cho phép `try (existingVariable)`” hoặc “TWR chỉ có từ Java 9”. Cả hai nhận định đều sai.

## 9. Chương trình Java 17 số 5: dùng biến effectively final

Tạo `ExistingResourceDemo.java`:

```java
import java.io.BufferedReader;
import java.io.StringReader;
import java.io.IOException;

public class ExistingResourceDemo {
    public static void main(String[] args) throws IOException {
        BufferedReader reader =
                new BufferedReader(new StringReader("Java 17"));

        try (reader) {
            System.out.println("Đọc: " + reader.readLine());
        }
        System.out.println("Đã ra khỏi try-with-resources");
    }
}
```

Chạy bằng JDK 17:

```bash
javac -encoding UTF-8 ExistingResourceDemo.java
java ExistingResourceDemo
```

Stdout:

```text
Đọc: Java 17
Đã ra khỏi try-with-resources
```

`reader` vẫn là biến cục bộ hợp lệ sau khối `try`, nhưng tài nguyên đã bị đóng. Chương trình chủ động **không gọi `readLine()` sau khi đóng**; việc tiếp tục sử dụng tùy hành vi cụ thể của resource và thường không hợp lệ với stream/reader.

Nếu đổi code thành:

```java
BufferedReader reader =
        new BufferedReader(new StringReader("a"));
reader = new BufferedReader(new StringReader("b"));
try (reader) {
    // Không biên dịch: reader đã bị gán lại, không effectively final.
}
```

thì Java 17 từ chối dạng `try (reader)` do biến đã được gán lại. Đây là **đoạn cố ý không biên dịch**; cần dùng một biến resource mới được khai báo trong ngoặc hoặc thay đổi thiết kế vòng đời.

## 10. Cách thiết kế lớp `AutoCloseable` an toàn

Bạn có thể đưa đối tượng tự tạo vào TWR bằng cách triển khai `AutoCloseable`:

```java
final class Session implements AutoCloseable {
    private boolean closed;

    void send(String message) {
        if (closed) {
            throw new IllegalStateException("Session đã đóng");
        }
        System.out.println("Gửi: " + message);
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            System.out.println("Đóng session");
        }
    }
}
```

Đây là định nghĩa lớp không có `main`; nó có thể dùng cùng một program Java có entrypoint khác. Điểm thiết kế:

- Bảo đảm resource ở trạng thái hợp lệ từ lúc constructor hoàn tất.
- `close()` nên giải phóng đúng các resource mà instance sở hữu; không nên tùy tiện đóng tài nguyên chia sẻ đang được đối tượng khác quản lý.
- Cân nhắc tính idempotent nếu thích hợp: ví dụ trên đóng lần hai không in lại. Với `AutoCloseable` nói chung, không được giả định mọi implementation đều idempotent.
- Khi đã đóng, các thao tác yêu cầu trạng thái mở nên từ chối rõ ràng.
- Nếu `close()` có thể thất bại, chọn kiểu checked exception phù hợp và giải thích trạng thái còn lại trong API.
- Khi resource được sử dụng giữa nhiều thread, cần chính sách đồng bộ hóa riêng; TWR không tạo thread safety.

Ví dụ sử dụng:

```java
try (Session session = new Session()) {
    session.send("Xin chào");
}
```

Đây là đoạn trong method; khi chạy, in `Gửi: Xin chào` rồi `Đóng session`. Không cần `catch` hoặc `throws` vì `Session.close()` không khai báo checked exception.

### 10.1. Quyền sở hữu tài nguyên (ownership) là quan trọng

Không phải biến `AutoCloseable` nào cũng nên đưa vào một TWR ngắn. Nếu caller **không sở hữu** resource, việc tự đóng có thể phá hoạt động của bên khác.

Ví dụ:

- Một method tự mở file để đọc: thường **sở hữu** reader, nên nên đóng.
- Một method nhận `InputStream` do caller truyền vào: phải đọc hợp đồng; có thể caller muốn stream vẫn mở để dùng tiếp.
- Connection pool: một đối tượng `Connection` có thể đại diện connection được “trả về pool” khi gọi `close()`; ngữ nghĩa triển khai do thư viện/pool quy định.
- `System.in`: đóng wrapper quanh standard input có thể đóng luôn luồng nhập chuẩn, ảnh hưởng phần còn lại của chương trình.

**Mẫu suy nghĩ:** “Ai mở/thu nhận resource và ai chịu trách nhiệm kết thúc vòng đời?” Đừng áp dụng TWR mù quáng lên đối tượng được chia sẻ.

## 11. TWR có thay thế `finally` hoàn toàn không?

**Không.** TWR chuyên xử lý tài nguyên `AutoCloseable`. `finally` vẫn hữu ích cho những hành động không gắn với một resource `AutoCloseable` hoặc cần thực hiện dù thao tác thành công hay thất bại, như ghi nhận mốc kết thúc, giải phóng một khóa theo hợp đồng, hoặc khôi phục context thread theo chính sách.

Ví dụ minh họa:

```java
try (Resource resource = acquire()) {
    perform(resource);
} catch (java.io.IOException e) {
    reportFailure(e);
} finally {
    recordCompletion();
}
```

Đây là mã mẫu phụ thuộc resource và các method chưa được định nghĩa. Khi resource đã được TWR tự đóng, `finally` không cần đóng nó lần nữa. Nếu có lock, transaction hoặc trạng thái riêng cần hoàn tác, phải thiết kế trách nhiệm tương ứng chứ không ngầm giao hết cho `close()`.

### 11.1. Không biến đóng resource thành xử lý ngoại lệ nghiệp vụ

Một kết nối đóng thành công **không** chứng minh transaction đã commit/rollback theo ý định. Một writer đóng thành công **không** có nghĩa toàn bộ file đã được ghi một cách bền vững trước sự cố mất điện. Nếu cần tính nguyên tử, độ bền hay khả năng phục hồi, hãy chọn transaction, ghi vào file tạm rồi thay thế, kiểm tra kết quả hoặc giao thức ứng dụng phù hợp.

TWR chỉ quản lý **việc gọi `close()`** trên những resource đã được cấp cho nó trong đường điều khiển bình thường của Java.

### 11.2. Exception trong `finally` có thể che lỗi chính

Nếu phần dọn dẹp thủ công trong `finally` ném exception, nó có thể ghi đè exception đang lan truyền từ thân `try`. Đây là một trong các lý do dùng TWR: Java tự tổ chức suppressed exceptions khi `close()` cũng thất bại.

Không nên dùng `return` hoặc ném exception mới trong `finally` nếu không chủ động chấp nhận việc thay đổi kết quả/che lỗi trước đó.

## 12. Try-with-resources và checked exception

Các nguồn checked exception mà compiler có thể yêu cầu xử lý gồm:

1. Constructor/initializer của resource.
2. Các method được gọi trong thân `try`.
3. Phương thức `close()` trên kiểu resource theo chữ ký mà compiler nhìn thấy.

Ví dụ `AutoCloseable` có `close() throws Exception` nên dùng qua biến có kiểu interface này có thể làm method phải khai báo `throws Exception`; qua một lớp cụ thể với `close() throws IOException` có thể chỉ cần `throws IOException`.

So sánh hai ví dụ **trong thân lớp**:

```java
static void broad() throws Exception {
    try (AutoCloseable resource = createResource()) {
        System.out.println("Đang xử lý");
    }
}
```

`createResource()` chưa được định nghĩa; giả sử bản thân nó không có checked exception khác. Vì biến `resource` có kiểu tĩnh `AutoCloseable`, compiler xét `close() throws Exception`. Đây là mã minh họa.

```java
static void narrow() throws java.io.IOException {
    try (java.io.BufferedReader reader =
                 new java.io.BufferedReader(
                         new java.io.StringReader("x"))) {
        System.out.println(reader.readLine());
    }
}
```

`BufferedReader` có phương thức đọc/đóng công bố `IOException`, nên khai báo `throws IOException` phù hợp. Thực tế dữ liệu `StringReader` nằm trong bộ nhớ, nhưng hợp đồng kiểu `BufferedReader` vẫn có checked exception.

### 12.1. `close()` thất bại khi method đã chuẩn bị `return`

Xét ý tưởng:

```java
static String load() throws java.io.IOException {
    try (MyReader reader = createReader()) {
        return "OK";
    }
}
```

Đây là ví dụ minh họa; `MyReader`/`createReader()` chưa có triển khai, giả sử `close() throws IOException`. Java tính giá trị định trả, nhưng vẫn đóng resource trước khi kết thúc lời gọi. Nếu `close()` ném `IOException`, lời gọi có thể thoát bằng exception thay vì trả `"OK"`. Vì vậy đường kết thúc của method phải được thiết kế và kiểm thử với cả lỗi lúc close.

### 12.2. Có nên bắt mọi `Exception` để “nuốt” lỗi đóng?

Không. Nếu đóng thất bại, resource hoặc dữ liệu có thể ở trạng thái chưa xác định. Việc bắt rộng rồi giả báo thành công dễ che nguyên nhân. Khi lỗi cần xử lý, bắt loại phù hợp, ghi nhận cả primary và suppressed exceptions khi có giá trị, và chuyển trạng thái công việc thành thất bại nếu cần.

## 13. TWR trong thực tế: đọc file và xử lý dữ liệu

Ví dụ Java 17 đầy đủ thao tác với file tạm để không cần chuẩn bị đầu vào. Nó tạo một tệp tạm, ghi ba dòng, đọc lại bằng TWR, sau đó xóa file trong `finally` của ví dụ; thao tác xóa được kiểm soát và có thể ném `IOException`.

Tạo `FileResourceDemo.java`:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileResourceDemo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("twr-learning-", ".txt");
        try {
            try (BufferedWriter writer =
                         Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
                writer.write("Java");
                writer.newLine();
                writer.write("Try-with-resources");
                writer.newLine();
            }

            try (BufferedReader reader =
                         Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
                String line;
                while ((line = reader.readLine()) != null) {
                    System.out.println(line);
                }
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 FileResourceDemo.java
java FileResourceDemo
```

**Stdout khi các thao tác file thành công:**

```text
Java
Try-with-resources
```

Đây là ví dụ I/O thực, nên có thể thất bại do quyền truy cập, thiếu dung lượng, tệp bị tác nhân khác thay đổi hoặc lỗi hệ thống. **Không** coi hai dòng trên là kết quả bảo đảm nếu môi trường không cho phép tạo/xóa file; khi lỗi, chương trình có thể ném `IOException` và in stack trace ra stderr vì `main throws IOException`.

Điểm nổi bật:

- TWR thứ nhất sở hữu `BufferedWriter`, nên tự đóng sau khi ghi, giúp hoàn tất quá trình đóng writer trước khi mở reader.
- TWR thứ hai sở hữu `BufferedReader` và tự đóng sau vòng lặp.
- `finally` của khối ngoài chịu trách nhiệm dọn **tệp tạm**, khác với đóng stream.
- `StandardCharsets.UTF_8` làm encoding rõ ràng, tránh phụ thuộc charset mặc định.
- Dùng hai TWR liên tiếp thể hiện vòng đời tách biệt của writer và reader; không cần quản lý thủ công các lệnh `close()`.

### 13.1. Có thể vừa đọc vừa ghi trong một TWR không?

Có, nếu muốn đồng thời sở hữu các resource và không cần đợi writer được đóng trước khi đọc. Tuy nhiên với dữ liệu file cần đọc sau khi ghi, một writer còn buffer có thể chưa đẩy hết dữ liệu ra ngoài. Đóng hoặc `flush()` đúng thời điểm trước khi đọc giúp làm rõ hợp đồng. `flush()` không đồng nghĩa dữ liệu đã bền vững trên đĩa khi mất điện.

## 14. Những lỗi phổ biến với try-with-resources

| Hiểu nhầm hoặc lỗi | Vấn đề | Cách xử lý |
| --- | --- | --- |
| “TWR chỉ dùng để đọc file.” | Mọi `AutoCloseable` phù hợp đều có thể dùng. | Dùng cho JDBC, stream, resource tùy biến khi có ownership rõ. |
| “Đóng tài nguyên chỉ xảy ra nếu thân try thành công.” | `close()` cũng được gọi khi rời khối vì exception. | Kiểm thử cả đường thành công và lỗi. |
| “Có thể đưa `String` vào ngoặc try.” | `String` không triển khai `AutoCloseable`. | Dùng kiểu đúng hoặc chuyển logic về `try` thường. |
| “Java 7 cho phép `try (reader)` với biến ngoài.” | Cú pháp biến có sẵn được mở rộng từ Java 9. | Java 7/8 dùng khai báo resource trực tiếp trong `(...)`. |
| “Java 7 hỗ trợ `var` cho resource.” | `var` xuất hiện từ Java 10. | Dùng kiểu tường minh nếu cần tương thích Java 7. |
| “Resource nào đóng trước cũng được.” | TWR đóng ngược thứ tự khai báo. | Sắp xếp resource phụ thuộc sao cho thứ tự đóng phù hợp. |
| “Nếu initializer thứ hai ném thì resource đầu không được đóng.” | Các resource đã khởi tạo thành công được dọn khi khởi tạo tiếp thất bại. | Đảm bảo constructor không làm rò rỉ tài nguyên chưa bàn giao. |
| “Khi cả thân và close lỗi, close sẽ làm mất lỗi thân.” | TWR giữ lỗi thân làm primary, close có thể thành suppressed. | Xem `getSuppressed()` và log đầy đủ. |
| “Nếu thân không lỗi, close lỗi sẽ bị bỏ qua.” | Lỗi close có thể trở thành primary. | Bắt/khai báo checked exception từ `close()`. |
| “TWR tự động commit/rollback database.” | Đóng resource không tự bảo đảm toàn vẹn giao dịch. | Sử dụng chính sách transaction/commit/rollback tường minh theo API. |
| “Biến khai báo ngoài `try` vẫn dùng được nên resource còn mở.” | Biến có thể còn trong scope nhưng resource đã đóng. | Không thao tác sau close trừ khi API cho phép. |
| “`catch (IOException)` luôn hợp lệ vì TWR luôn có I/O.” | TWR có thể quản lý resource không khai báo `IOException`. | Dựa trên kiểu initializer, thân, và `close()` thực tế. |
| “Đóng một stream được chia sẻ không ảnh hưởng bên ngoài.” | `close()` có thể kết thúc resource do caller/ứng dụng khác dùng. | Thỏa thuận quyền sở hữu trước khi dùng TWR. |
| “Có TWR nên không cần finally nữa.” | `finally` vẫn hữu ích với hành động không phải `AutoCloseable`. | Phân chia trách nhiệm rõ; không đóng lại resource vô cớ. |
| “Có thể gọi reader sau TWR nếu reader chưa bị GC.” | Vòng đời resource không phụ thuộc GC. | Tôn trọng trạng thái đã đóng. |

## 15. Các câu hỏi thường gặp

### 15.1. Có thể viết `try (...)` mà không có `catch` và `finally` không?

**Có**, nếu đó là **try-with-resources** hợp lệ. Với `try` thông thường (không có resource specification), Java yêu cầu có `catch`, `finally`, hoặc cả hai. TWR cho phép không có cả hai vì chính cấu trúc đã định nghĩa hành vi đóng tài nguyên.

### 15.2. Nhiều resource đóng theo thứ tự nào?

Theo thứ tự **ngược** với khai báo trong `(...)`. Trong `try (A a = ...; B b = ...; C c = ...)`, thứ tự mở A → B → C, thứ tự đóng C → B → A.

### 15.3. `close()` có được gọi nếu trong thân `try` có `return`?

**Có** theo đường thực thi Java bình thường. Giá trị return có thể đã được tính nhưng việc đóng diễn ra trước khi method hoàn thành; lỗi trong `close()` có thể thay thế return.

### 15.4. `close()` có chạy khi resource initializer trả `null`?

Không, resource có giá trị `null` được bỏ qua khi đóng. Nhưng caller vẫn cần hiểu liệu giá trị null có phải một trạng thái hợp lệ theo hợp đồng.

### 15.5. TWR có tự khởi động giao dịch database không?

Không. JDBC `Connection` có giao thức transaction riêng. TWR giúp đóng connection, statement, result set; commit/rollback phải được thiết kế theo cấu hình auto-commit, giao thức driver/pool và yêu cầu nghiệp vụ. Không suy luận transaction thành công chỉ vì `close()` chạy.

### 15.6. Nếu thân try và `close()` cùng thất bại thì handler bắt exception nào?

Nếu thân ném exception và khi đóng lại có exception, exception từ thân thường là primary, các lỗi đóng được gắn dưới `getSuppressed()`. Handler so kiểu **primary Throwable đang được ném**, không tự chọn một suppressed exception có kiểu tương thích.

### 15.7. `AutoCloseable` và `Closeable` khác gì?

`AutoCloseable.close()` khai báo `throws Exception`; `Closeable.close()` khai báo `throws IOException` và có hợp đồng đóng lặp lại cụ thể. Cả hai có thể dùng trong TWR. Compiler xem chữ ký theo kiểu tĩnh của resource.

### 15.8. Tại sao dùng biến existing resource trong Java 9+ vẫn cần cẩn thận?

Nếu biến được khai báo bên ngoài, resource vẫn được đóng sau TWR; các đoạn code ngoài có thể còn giữ tham chiếu và vô tình thao tác trên resource đã đóng. Ngoài ra việc mở resource ngoài khối khiến bạn cần suy nghĩ về mọi code nằm giữa lúc mở và lúc bắt đầu quản lý TWR.

## 16. Bài tập tự luyện

### Bài 1 — Chuyển `finally` sang TWR

Cho method minh họa:

```java
static String firstLine(String path) throws java.io.IOException {
    java.io.BufferedReader reader = null;
    try {
        reader = new java.io.BufferedReader(
                new java.io.FileReader(path));
        return reader.readLine();
    } finally {
        if (reader != null) {
            reader.close();
        }
    }
}
```

Viết lại bằng `try (BufferedReader reader = ...) { return reader.readLine(); }`. So sánh số dòng, ý định và điều gì xảy ra nếu `readLine()` cũng như `close()` cùng ném lỗi.

### Bài 2 — Dự đoán thứ tự stdout

Chạy `ResourceCloseOrderDemo` với thứ tự khai báo `A, B, C`. Sau đó đổi thành `C, A, B`. Dự đoán thứ tự mở và đóng mà không chạy; hãy giải thích tại sao đóng luôn ngược thứ tự khai báo.

### Bài 3 — Lỗi thân và lỗi đóng

Chạy `SuppressedExceptionDemo`. Thay khối thân bằng một lời in không ném lỗi. Khi `close()` vẫn ném `IOException`, dòng primary sẽ đổi như thế nào? `getSuppressed()` trong trường hợp chỉ có một lỗi đóng sẽ có bao nhiêu phần tử?

### Bài 4 — Tự viết `AutoCloseable`

Tạo lớp `TimerScope implements AutoCloseable` ghi nhận tên và in `Start name` ở constructor, `End name` ở `close()`. Dùng TWR để quan sát cả nhánh thành công và ném `IllegalStateException`. Không dựa vào thời gian hệ thống để xuất stdout cố định.

### Bài 5 — So sánh Java 7 và Java 9

Viết hai phiên bản code đọc dòng từ `StringReader`: (A) khai báo `BufferedReader` trong `try (...)`, (B) khai báo trước rồi `try (reader)`. Giải thích phiên bản nào biên dịch với `--release 7` (nếu bộ JDK cho phép biên dịch mức đó) và vì sao phiên bản (B) chỉ hợp lệ từ Java 9. Trong ví dụ Java 17, cả hai cách đều có thể dùng.

### Bài 6 — Tìm lỗi ownership

Một API nhận `InputStream input` do caller cung cấp và chỉ cần đọc 5 byte. Có luôn nên viết `try (input)` để đóng không? Hãy giải thích vì sao cần biết contract về quyền sở hữu, và đề xuất tài liệu hóa việc “method sẽ đóng stream” hoặc “caller chịu trách nhiệm đóng”.

### Bài 7 — Quan hệ checked exceptions

Tạo `AutoCloseable` có `close() throws Exception` nhưng thân `try` không ném checked exception. Khi viết method chứa TWR, compiler đòi hỏi khai báo/handler loại checked nào? Thử thay kiểu resource thành lớp con có `close()` không khai báo checked exception để nhận ra tác dụng của kiểu tĩnh.

### Bài 8 — Kiểm thử khi khởi tạo một resource mới thất bại

Tạo `AutoCloseable` thứ nhất có `close()` in `"closed first"`, initializer thứ hai ném `IllegalStateException`. Xác nhận rằng resource thứ nhất vẫn được đóng. Giải thích vì sao tài nguyên chưa được cấp thành công cho TWR phải tự quản lý phần cấp phát nội bộ của initializer.

## 17. Checklist trước khi áp dụng TWR

- [ ] Tài nguyên thực sự triển khai `AutoCloseable` hoặc `Closeable` chưa?
- [ ] Tôi biết rõ **ai sở hữu** tài nguyên và ai chịu trách nhiệm đóng không?
- [ ] Tất cả resource cần quản lý có được đưa vào `try (...)` trong đúng thứ tự không?
- [ ] Tôi đã phân biệt cú pháp khai báo Java 7 với biến effectively final của Java 9 chưa?
- [ ] Tôi có đang dùng `var` dù dự án cần biên dịch Java 7 hoặc 8 không?
- [ ] Tôi đã xét checked exceptions từ initializer, thân và `close()` chưa?
- [ ] Tôi biết tài nguyên đóng theo thứ tự ngược khi có nhiều resource không?
- [ ] Tôi đã kiểm tra đường lỗi trong initializer làm tài nguyên trước vẫn được đóng chưa?
- [ ] Tôi hiểu primary/suppressed và không vô tình làm mất thông tin chẩn đoán không?
- [ ] Tôi đã tránh đóng lại resource thủ công trong `finally` vô cớ chưa?
- [ ] Nếu có resource còn tham chiếu sau TWR, tôi có tránh dùng nó sai trạng thái không?
- [ ] Tôi đã phân biệt dọn dẹp tài nguyên với transaction/rollback nghiệp vụ chưa?
- [ ] Với I/O thật, tôi đã chọn charset, xử lý lỗi file và thiết kế vòng đời dữ liệu hợp lý chưa?
- [ ] Test có bao gồm thành công, lỗi thân, lỗi đóng, nhiều resource và lỗi initializer chưa?

**Ghi nhớ:** try-with-resources có từ **Java 7**, dùng `try (Resource r = ...) { ... }` để tự động đóng `AutoCloseable`. Java khởi tạo resource theo thứ tự khai báo, đóng theo thứ tự ngược và giữ lỗi đóng dưới dạng **suppressed** khi đã có lỗi chính. Từ **Java 9**, có thể viết `try (existingResource)` với biến `final`/effectively final; từ **Java 10**, có thể dùng `var` trong resource declaration. TWR giúp quản lý vòng đời tài nguyên đáng tin cậy hơn, nhưng không thay cho xử lý ngoại lệ có ngữ cảnh hoặc giao dịch bảo toàn dữ liệu.