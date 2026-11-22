# Ai mở, ai đóng: quy tắc sở hữu tài nguyên trong thiết kế API Java I/O

> **Ngữ cảnh:** Java Core → I/O → **Tài nguyên và lỗi**. Bài này trả lời câu hỏi tưởng chừng đơn giản nhưng dễ gây rò rỉ và lỗi khó dò: **ai chịu trách nhiệm gọi `close()`, khi nào được chuyển trách nhiệm, và một hàm đọc/ghi có nên đóng stream mà caller truyền vào không?** Kiến thức áp dụng cho `InputStream`, `OutputStream`, `Reader`, `Writer`, kênh/tệp và các đối tượng I/O mở. Các ví dụ chạy độc lập dùng Java 17; phần lớn hợp đồng nền tảng đã có từ trước.

## 1. Sở hữu tài nguyên là một hợp đồng, không chỉ là thao tác gọi close

Tài nguyên I/O như file descriptor, socket, directory handle hoặc channel thường có **vòng đời độc lập** với đối tượng Java đang tham chiếu nó. Khi mở một tệp, JVM/OS có thể cấp phát handle hữu hạn; bỏ quên `close()` có thể khiến cạn handle, file vẫn bị khóa, buffer không được flush đúng lúc hoặc tài nguyên tồn tại lâu hơn dự kiến.

**Resource owner (chủ sở hữu)** là thành phần chịu trách nhiệm quyết định vòng đời và **đóng** tài nguyên đúng lúc, kể cả lúc có exception. Quyền sở hữu cần được thể hiện trong **hợp đồng API**: parameter là nguồn được mượn hay nguồn được chuyển giao, kết quả trả về đã mở có cần caller đóng hay method đã tự dọn xong?

Quy tắc thường dùng là:

- **Hàm tự mở để dùng nội bộ → hàm đó thường tự đóng** trước khi trả kết quả đã tính.
- **Hàm nhận stream do caller cung cấp → mặc định nên coi stream là được mượn, chỉ sử dụng chứ không đóng**, trừ khi API nói rõ việc chuyển ownership.
- **Hàm trả về một stream/channel còn mở → caller nhận quyền sở hữu và chịu trách nhiệm đóng**.
- **Hàm bọc stream (decorator/wrapper) → phải đọc hợp đồng `close()` của wrapper**: đóng lớp ngoài thường đóng luôn nguồn bên trong.
- **Tài nguyên dùng chung hoặc do framework/JVM quản lý → không tự ý đóng từ một hàm tiện ích**.

Những câu trên là **quy ước thiết kế API**, không phải luật cứng của ngôn ngữ Java. Việc bạn gọi `new` hay nhận reference **không tự chứng minh** quyền sở hữu. Một factory có thể mở resource rồi **chuyển** quyền đóng cho caller; một constructor có thể nhận resource do caller mở nhưng hợp đồng quy định wrapper được sở hữu nó. Cần ghi rõ và nhất quán.

### Điều gì xảy ra nếu ownership không rõ?

| Sai lệch vòng đời | Hậu quả |
| --- | --- |
| Không ai gọi `close()` | Rò rỉ file descriptor, socket, directory handle; giải phóng muộn và không xác định |
| Hai bên tưởng mình có quyền đóng và một bên đóng sớm | `IOException: Stream closed` hoặc thao tác đọc/ghi thất bại ở bên còn dùng |
| Một hàm tiện ích đóng stream caller đang dùng | Hỏng pipeline, file/socket chung không dùng tiếp được |
| Method mở stream rồi trả `Stream` lazy mà không ghi trách nhiệm đóng | Caller tưởng terminal operation tự đóng; file/directory vẫn mở |
| Wrapper bị đóng sau một lần xử lý, làm đóng luôn underlying stream | Bên khác dùng nguồn gốc bị lỗi dù không gọi `close()` trực tiếp |
| Không flush/close output theo đúng vòng đời | Dữ liệu còn trong buffer, tệp có thể thiếu nội dung sau khi tiến trình kết thúc bất thường |
| Resource phục vụ tác vụ async bị đóng trước khi tác vụ chạy xong | Race giữa `close()` và I/O, lỗi không ổn định theo timing |

## 2. Ba kiểu ownership nên định nghĩa rõ trong Java API

### 2.1. Borrowed: hàm chỉ mượn resource

Caller vẫn sở hữu `InputStream` hoặc `OutputStream`. Hàm tiện ích được **đọc/ghi**, nhưng **không đóng** chúng và không giữ reference để dùng sau khi trả về, trừ khi có thỏa thuận riêng.

~~~java
// Hợp đồng: borrowed input/output; method không close hai stream.
static long copy(InputStream in, OutputStream out) throws IOException {
    byte[] buffer = new byte[8192];
    long copied = 0;
    int n;
    while ((n = in.read(buffer)) != -1) {
        out.write(buffer, 0, n);
        copied += n;
    }
    return copied;
}
~~~

Đây là fragment bên trong một class, cần import `java.io.InputStream`, `java.io.OutputStream` và `java.io.IOException`. Hàm chỉ truyền byte, **không đóng** hoặc flush `out`: caller có thể còn muốn ghi thêm dữ liệu, hoặc output này thuộc request/transaction lớn hơn. Nếu hợp đồng ứng dụng yêu cầu flush tại một điểm cụ thể, điều đó cũng phải ghi rõ; không âm thầm flush trên mọi lần gọi.

### 2.2. Owned: hàm nhận trách nhiệm đóng resource

Nếu hàm nhận `Path` và **tự mở** tệp trong thân hàm, nó thường sở hữu reader vừa mở:

~~~java
// Hợp đồng: method tự mở và tự đóng BufferedReader.
static long countLines(Path path) throws IOException {
    try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        long count = 0;
        while (reader.readLine() != null) {
            count++;
        }
        return count;
    }
}
~~~

Đây là fragment với import `java.io.BufferedReader`, `java.io.IOException`, `java.nio.file.Files`, `java.nio.file.Path` và `java.nio.charset.StandardCharsets`. Caller chỉ truyền đường dẫn, không quản lý reader nội bộ. `try-with-resources` đóng reader trên cả đường thành công lẫn ngoại lệ.

### 2.3. Transferred: hàm giao quyền đóng cho bên nhận

~~~java
// Hàm mở rồi trả một resource còn sống.
// Caller trở thành owner khi return thành công.
static InputStream openDocument(Path path) throws IOException {
    return Files.newInputStream(path);
}

// Cách gọi đúng:
try (InputStream stream = openDocument(path)) {
    // Đọc stream...
}
~~~

Đây là fragment, cần import tương ứng. Trả về `InputStream` **không tự động** làm stream được đóng; hãy ghi trong Javadoc rằng **caller must close returned stream**. Caller phải đóng kể cả khi chỉ đọc vài byte hoặc sau khi parse thất bại. Nếu method nhận một stream và **nhận chuyển giao ownership** vào đối tượng giữ lâu, hợp đồng phải ghi rõ thời điểm đối tượng sở hữu sẽ đóng nó.

## 3. Bảng quyết định: ai đóng trong những thao tác I/O quen thuộc?

| Nguồn hoặc hành động | Ai mở / tạo | Ai nên đóng | Ghi chú |
| --- | --- | --- | --- |
| `Files.newInputStream(path)` | Method `Files` mở handle; caller nhận return | **Caller** | Dùng try-with-resources bao quanh đoạn sử dụng. |
| `Files.newBufferedReader(path, UTF_8)` | `Files` mở reader | **Caller** | Trả `BufferedReader` mở, gọi `close()` sau đọc. |
| `Files.readString(path)` hoặc `Files.readAllBytes(path)` | API tự thực hiện đọc tệp | **API** quản lý handle nội bộ | Caller nhận `String`/`byte[]`, không nhận resource mở để đóng. |
| `Files.lines(path)` | API mở file và trả stream lazy | **Caller** đóng `Stream<String>` | `count()`, `findFirst()`, `forEach()` **không tự thay thế** `close()`. |
| `Files.list(dir)` / `Files.walk(dir)` | API mở directory handle | **Caller** đóng stream | Dùng try-with-resources ngay cả khi đã xử lý xong terminal operation. |
| `Files.newDirectoryStream(dir)` | API mở directory stream | **Caller** | Không để directory handle sống quá phạm vi liệt kê. |
| `new BufferedInputStream(input)` | Wrapper tạo buffer, nguồn `input` có trước | **Phụ thuộc hợp đồng sở hữu wrapper** | `close()` wrapper gọi close xuống nguồn bên trong. |
| `new BufferedReader(reader)` | Wrapper mới, reader có trước | **Phụ thuộc ownership nguồn** | Đóng wrapper cũng đóng reader được bọc. |
| `new Scanner(input)` | Scanner mới dùng nguồn caller truyền | Phải quyết định rõ trước khi đóng scanner | Khi `Scanner.close()` và nguồn implement `Closeable`, scanner cũng đóng nguồn. |
| `System.in` / `System.out` / `System.err` | JVM/môi trường cung cấp standard streams | Thường **không đóng** ở hàm tiện ích | Nếu đóng, những phần khác của ứng dụng có thể mất stdin/stdout/stderr. |
| `InputStream.transferTo(output)` | Hai stream do các bên cung cấp | **Caller/owner của từng stream** | Method sao chép không tự đóng input/output. |
| `ByteArrayInputStream` / `ByteArrayOutputStream` | Bộ nhớ trong JVM | Theo contract, close có thể không làm gì | Vẫn nhất quán về ownership khi đổi sang nguồn file/socket trong tương lai. |
| Stream/channel do server framework cấp | Runtime hoặc container | Theo **hợp đồng framework** | Không suy ra caller phải đóng chỉ vì kiểu là `InputStream`. |

**Phân biệt quan trọng:** một object implement `Closeable` không nhất thiết là nơi cần close; đó chỉ là **khả năng đóng**. Ownership được quyết định bởi **hợp đồng** và vòng đời. Ngược lại, không phải thứ cần đóng đều có kiểu `InputStream`: `Stream<String>` từ `Files.lines` cũng phải đóng vì giữ file handle.

## 4. Ví dụ độc lập: phương thức mượn stream không tự đóng

Lưu file **`BorrowedCopyDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class BorrowedCopyDemo {
    // Bộ đếm giúp quan sát chính xác ai gọi close().
    static final class TrackedInput extends FilterInputStream {
        int closes;

        TrackedInput(byte[] source) {
            super(new ByteArrayInputStream(source));
        }

        @Override
        public void close() throws IOException {
            closes++;
            super.close();
        }
    }

    // API borrowed: method không sở hữu input/output.
    static long copyBorrowed(InputStream input, OutputStream output)
            throws IOException {
        byte[] buffer = new byte[8];
        long total = 0;
        int n;
        while ((n = input.read(buffer)) != -1) {
            output.write(buffer, 0, n);
            total += n;
        }
        return total;
    }

    public static void main(String[] args) throws IOException {
        TrackedInput in = new TrackedInput(
                "abc".getBytes(StandardCharsets.UTF_8));
        ByteArrayOutputStream out = new ByteArrayOutputStream();

        try (in) { // Caller sở hữu và đóng input.
            System.out.println("bytes=" + copyBorrowed(in, out));
            System.out.println("closesInside=" + in.closes);
        }

        System.out.println("closesAfter=" + in.closes);
        System.out.println("text=" +
                new String(out.toByteArray(), StandardCharsets.UTF_8));
    }
}
~~~

~~~bash
javac --release 17 BorrowedCopyDemo.java
java BorrowedCopyDemo
~~~

Stdout:

~~~text
bytes=3
closesInside=0
closesAfter=1
text=abc
~~~

`TrackedInput` chỉ phục vụ bài học: bộ đếm tăng mỗi lần wrapper nhận `close()`, giúp chứng minh hàm `copyBorrowed` **không đóng stream**. Tài nguyên thật trong demo là `ByteArrayInputStream` đã nằm trong bộ nhớ, nên close của nguồn đó không có hiệu ứng giải phóng file descriptor. Ở file/socket thực, việc đóng sớm có thể ảnh hưởng mạnh hơn.

Đặc biệt, `ByteArrayOutputStream.close()` không làm vô hiệu hóa các phương thức của lớp này theo contract, nhưng **không được** dùng tính chất đó để suy ra `FileOutputStream` hoặc network stream sẽ hành xử tương tự.

### Vì sao không đặt try-with-resources bên trong copyBorrowed?

Đây là **sai hợp đồng** khi parameter là borrowed:

~~~java
// Phản ví dụ thiết kế: không dùng khi caller vẫn sở hữu input.
static long wrongCopy(InputStream input, OutputStream output)
        throws IOException {
    try (input; output) { // TỰ ĐỘNG đóng cả hai khi method kết thúc!
        return input.transferTo(output);
    }
}
~~~

Trong Java 9+, `try (input; output)` hợp lệ nếu hai biến effectively final, nhưng nó **chuyển hành vi thành đóng cả input và output** khi thoát method. Thậm chí nếu `transferTo` tự nó không đóng hai stream, try-with-resources đã làm điều đó. Hàm này chỉ hợp lệ nếu contract **nêu rõ nhận ownership của cả hai**. Đừng chọn đóng chỉ vì nhìn thấy interface `AutoCloseable`.

## 5. Ví dụ độc lập: hai kiểu API đọc tệp và hai điểm đóng

Lưu file **`OpenVsReturnDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class OpenVsReturnDemo {
    // Method tiêu thụ nội bộ: tự mở, tự đóng.
    static long countLines(Path path) throws IOException {
        try (BufferedReader reader =
                     Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            long count = 0;
            while (reader.readLine() != null) {
                count++;
            }
            return count;
        }
    }

    // Factory chuyển quyền đóng Stream<String> sang caller.
    static Stream<String> openLines(Path path) throws IOException {
        return Files.lines(path, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("ownership-", ".txt");
        try {
            Files.writeString(
                    file, "one\ntwo\n", StandardCharsets.UTF_8);

            System.out.println("count=" + countLines(file));

            // Stream từ Files.lines giữ file handle đến lúc close.
            try (Stream<String> lines = openLines(file)) {
                System.out.println(
                        "first=" + lines.findFirst().orElse("none"));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac --release 17 OpenVsReturnDemo.java
java OpenVsReturnDemo
~~~

Stdout:

~~~text
count=2
first=one
~~~

Bài học chính:

- `countLines(Path)` mở `BufferedReader` **và tự đóng** trước khi return `long`. Không có resource mở được trả về caller.
- `openLines(Path)` trả `Stream<String>` có file handle. Caller phải dùng `try (Stream<String> lines = ...)` dù chỉ gọi `findFirst()`. Tập tin cần được đóng **trước** khi đoạn `finally` cố xóa tệp tạm.
- `Files.writeString` tự quản lý thao tác mở/đóng file khi nó trả về; `Files.createTempFile` tạo tệp, nhưng xóa **tệp vật lý** là trách nhiệm cleanup khác với close handle. Đừng nhầm `close()` với `Files.deleteIfExists()`.
- Với file có dữ liệu tùy ý lớn, `countLines` chỉ đọc từng dòng bằng buffer, không gom toàn bộ vào một `List` hoặc `String`.

## 6. API nhận callback: mượn resource trong một phạm vi được kiểm soát

Một lựa chọn hữu ích là **lifetime-scoped callback**: method mở/đóng resource, callback chỉ được sử dụng trong thời gian method gọi nó. Ví dụ:

~~~java
@FunctionalInterface
interface ReaderTask<T> {
    T apply(BufferedReader reader) throws IOException;
}

// Fragment: hàm tự mở và tự đóng reader.
static <T> T withReader(Path path, ReaderTask<T> task)
        throws IOException {
    try (BufferedReader reader =
                 Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        return task.apply(reader);
    }
}

// Cách dùng minh họa:
String first = withReader(path, BufferedReader::readLine);
~~~

Đây là **fragment**, cần đặt trong class, import `java.io.BufferedReader`, `java.io.IOException`, `java.nio.file.Files`, `java.nio.file.Path`, `java.nio.charset.StandardCharsets`; biến `path` là `Path` hợp lệ. Callback được **mượn** reader; sau callback (dù thành công hay thất bại), `withReader` đóng nó.

Điểm mạnh: caller không cần nhớ close, method giới hạn tài nguyên tồn tại trong một lexical scope, lỗi I/O/close có đường đi rõ ràng. Điểm cần nêu trong hợp đồng: callback **không được đóng**, giữ reference, trả resource đang mở ra ngoài hoặc bắt đầu tác vụ nền tiếp tục dùng reader sau khi callback return. Java generic không tự ngăn caller trả reference ra khỏi scope, nên đây vẫn là **ràng buộc contract**; có thể thiết kế kiểu trả về giới hạn để giảm khả năng vi phạm.

Với callback xử lý `OutputStream`, tương tự: method tạo stream và đóng sau callback; callback phải hoàn tất ghi **trong** callback. Nếu asynchronous I/O cần sống sau khi hàm return, không dùng thiết kế callback ngắn hạn như thể công việc đã hoàn tất đồng bộ.

## 7. Wrapper và decorator: đóng lớp ngoài thường đóng lớp trong

Ví dụ:

~~~java
// Method tạo cả input stream và reader, nên sở hữu cả chuỗi wrapper.
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(
                Files.newInputStream(path), StandardCharsets.UTF_8))) {
    String firstLine = reader.readLine();
}
~~~

Đoạn này là **fragment** nằm trong method xử lý `IOException` với các import tương ứng. `BufferedReader.close()` gọi close của reader bên trong; `InputStreamReader.close()` đóng underlying input stream. Như vậy **đóng wrapper ngoài cùng** có thể giải phóng cả chuỗi nguồn. Không cần khai báo mọi tầng bằng nhiều biến trong try-with-resources chỉ để gọi close lặp lại.

Nhưng nếu tài nguyên bên trong **được caller cho mượn**, cùng cơ chế lan truyền close đó trở thành bẫy:

~~~java
// Phản ví dụ khi 'borrowed' còn được caller dùng:
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(borrowed, StandardCharsets.UTF_8))) {
    return reader.readLine();
} // reader.close() kéo theo borrowed.close().
~~~

Nếu method muốn đóng wrapper nhưng giữ nguồn sống, cần một **hợp đồng chia sẻ thực sự**, thiết kế lớp adapter không đóng underlying theo yêu cầu cụ thể, hoặc để owner tạo wrapper và chuyển ownership. Không đơn giản bỏ `close()` của wrapper rồi cho rằng mọi thứ ổn: buffer có thể đã **đọc trước** nhiều byte, làm vị trí nguồn của caller thay đổi ngoài dự kiến. Chọn **một owner rõ ràng cho chuỗi wrapper** là thiết kế dễ kiểm chứng nhất.

Một ví dụ khác là `Scanner`: tài liệu chuẩn nêu rằng nếu Scanner được đóng, nó sẽ đóng nguồn underlying nếu nguồn đó implement `Closeable`. Vì vậy:

~~~java
// Nguy hiểm trong ứng dụng còn cần tiếp tục đọc System.in:
try (java.util.Scanner scanner =
             new java.util.Scanner(System.in)) {
    String command = scanner.nextLine();
} // Scanner.close() có thể đóng System.in.
~~~

Nếu scanner đọc `System.in` cho toàn bộ vòng đời CLI, thường để thành phần **đầu vào cấp ứng dụng** sở hữu scanner và quyết định khi nào đóng, thay vì tạo/đóng scanner mỗi lần đọc một token. Không tạo nhiều lớp scanner/reader có buffer trên cùng input để đọc xen kẽ.

## 8. Nên flush, close hay cả hai?

`flush()` và `close()` có mục đích khác nhau:

- **`flush()`** trên một output có buffering nhằm đẩy dữ liệu đang nằm trong buffer của lớp đó về sink phía dưới theo contract; **không đồng nghĩa** bảo đảm OS đã ghi bền vững xuống ổ đĩa, và **không giải phóng** handle.
- **`close()`** kết thúc vòng đời resource, giải phóng những tài nguyên nó nắm giữ. Nhiều buffered output có thể flush dữ liệu còn lại trong quá trình close; **close có thể thất bại**. Không được coi lời gọi close thành công chỉ vì vòng lặp ghi đã xong.
- Với API borrowed, method copy thường **không tự flush/close output** trừ khi được yêu cầu; owner quyết định khi dữ liệu đã đầy đủ và bao giờ kết thúc.
- Với API owned, hãy đóng output trong try-with-resources. Nếu cần bảo đảm độ bền dữ liệu trên storage, đó là vấn đề khác: `FileChannel.force(...)` hoặc `FileDescriptor.sync()` có contract riêng và phụ thuộc hệ thống tệp.

Ví dụ:

~~~java
// Fragment: method sở hữu writer vì tự mở file.
try (BufferedWriter writer =
         Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("Đã hoàn thành\n");
} // BufferedWriter được close dù body có lỗi.
~~~

Không diễn giải `writer.flush()` là thay thế được `writer.close()`. Ngược lại, **không gọi `close()` của một output caller mượn** chỉ để “chắc đã flush”, vì nó chấm dứt quyền sử dụng của owner.

## 9. Try-with-resources: ai đóng, đóng khi nào?

`try-with-resources` dùng với object implement `AutoCloseable`; block thoát bằng return, exception hoặc chạy hết thì resource được close theo thứ tự ngược với khai báo.

~~~java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(target)) {
    in.transferTo(out);
} // out.close() trước, sau đó in.close().
~~~

Đây là fragment; `source`/`target` là `Path` được cung cấp, cùng import I/O và Files. Code **sở hữu hai stream** vì vừa mở cả hai trong block. Từ Java 9, `InputStream.transferTo` không tự đóng hai stream; khối try đảm nhiệm trách nhiệm đóng.

Các trường hợp quan trọng:

1. Khi khởi tạo resource thứ hai ném lỗi, resource thứ nhất đã tạo thành công vẫn được đóng tự động.
2. Nếu code trong body ném exception **và** close cũng ném, exception của body là **primary exception**; lỗi close được gắn vào `getSuppressed()`.
3. Nếu body thành công nhưng close ném exception, exception từ close được truyền ra ngoài theo loại ngoại lệ tương ứng. Không bỏ qua nó nếu kết quả ghi cần được xác nhận.
4. Khi có nhiều resource, Java đóng theo **thứ tự ngược** lúc khai báo; đừng giả định dependency được đóng theo thứ tự tùy ý.
5. `try (resourceVariable)` từ Java 9 cho phép dùng biến local/parameter final hoặc effectively final đã tồn tại, nhưng **đó vẫn là yêu cầu đóng resource đó**. Dùng cú pháp này với parameter mượn sẽ chuyển đổi contract một cách âm thầm.
6. `Closeable.close()` theo hợp đồng chuẩn có tính idempotent khi gọi lại; `AutoCloseable` tổng quát **không bắt buộc** mọi implementation đều idempotent. Không dựa vào double-close như chiến lược ownership.

`try-with-resources` là **cơ chế thực hiện việc đóng**; nó không tự quyết định **ai có quyền đóng**. Quyết định ownership phải có trước khi đặt đối tượng vào dấu ngoặc `try (...)`.

## 10. Ví dụ độc lập: lỗi trong body và lỗi khi đóng

Lưu file **`SuppressedCloseDemo.java`**:

~~~java
public class SuppressedCloseDemo {
    static final class Faulty implements AutoCloseable {
        private final String name;

        Faulty(String name) {
            this.name = name;
        }

        @Override
        public void close() throws Exception {
            throw new Exception("close-" + name);
        }
    }

    public static void main(String[] args) {
        try (Faulty a = new Faulty("A");
             Faulty b = new Faulty("B")) {
            throw new IllegalStateException("body");
        } catch (Exception ex) {
            System.out.println("main=" + ex.getMessage());
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println(
                        "suppressed=" + suppressed.getMessage());
            }
        }
    }
}
~~~

~~~bash
javac --release 17 SuppressedCloseDemo.java
java SuppressedCloseDemo
~~~

Stdout:

~~~text
main=body
suppressed=close-B
suppressed=close-A
~~~

**Giải thích:** body thất bại với `IllegalStateException("body")`. Java vẫn gọi `close()` trên `b` rồi `a`, nhưng không đánh mất exception gốc; hai lỗi đóng trở thành **suppressed exceptions**. Nếu logger chỉ in `ex.getMessage()` mà bỏ stack trace/suppressed, có thể mất thông tin quan trọng về việc release tài nguyên thất bại. Với ứng dụng server, cần log/report cả exception chính và suppressed theo chính sách bảo mật/logging phù hợp.

Ví dụ dùng lớp tự tạo `Faulty` để bảo đảm output xác định và không cần file; đây là tình huống minh họa chủ đích, không phải cách implement `close()` thông thường.

## 11. Kiểu trả về và tên hàm nên diễn đạt ownership

Nhìn vào chữ ký:

~~~java
byte[] readAll(Path path);        // Trả dữ liệu đã đọc, resource nội bộ đóng.
InputStream open(Path path);      // Trả resource mở, caller đóng.
void copy(InputStream in, OutputStream out); // Borrowed cả hai, không đóng.
~~~

Ba dòng này là **API sketch**, không có implementation, chưa khai báo `IOException`; dùng để so sánh contract chứ không phải mã chạy độc lập.

Tên `readAll` gợi ý xử lý kết thúc trong method; `open` gợi ý caller nhận handle đang sống; `copy` gợi ý thao tác trên các handle được cho sẵn. Tuy vậy tên chỉ hỗ trợ người đọc, **không thay thế Javadoc**.

Mẫu Javadoc rõ ràng cho API borrowed:

~~~java
/**
 * Copies remaining bytes from input to output.
 *
 * <p>Both streams are owned by the caller. This method neither closes
 * nor flushes either stream; caller controls their lifetimes.
 *
 * @param input an open, caller-owned source stream
 * @param output an open, caller-owned destination stream
 * @return number of bytes copied
 * @throws IOException if an I/O operation fails
 */
public static long copyBorrowed(InputStream input,
                                OutputStream output)
        throws IOException {
    return input.transferTo(output); // Java 9+; transferTo không đóng stream.
}
~~~

Method này có thể nằm trong class Java 17 và cần import I/O tương ứng. Nếu muốn hỗ trợ Java 8, thay `transferTo` bằng vòng lặp buffer như ví dụ trên. Có thể xác nhận `null` không được phép bằng `Objects.requireNonNull` nếu muốn fail sớm theo contract.

Mẫu Javadoc cho API transferred:

~~~java
/**
 * Opens an input stream. The returned stream is open and its
 * caller MUST close it, preferably with try-with-resources.
 */
public static InputStream open(Path path) throws IOException {
    return Files.newInputStream(path);
}
~~~

Các phương án khác cũng hợp lệ: method nhận `Supplier` tạo nguồn bên trong, method nhận callback tiêu thụ trong một scope, hoặc object có `close()` sở hữu nhiều resource. Hãy chọn một contract nhất quán và nói rõ khi nào owner thay đổi.

## 12. Những trường hợp đặc biệt cần thận trọng

### 12.1. Standard streams và tài nguyên dùng chung

`System.in`, `System.out`, `System.err` thường phục vụ **toàn bộ tiến trình**. Một hàm tiện ích nhận `System.in` thường chỉ nên đọc và để caller/runtime sở hữu vòng đời. Ví dụ `new BufferedReader(new InputStreamReader(System.in, UTF_8))` rồi đóng reader có thể đóng luôn `System.in`. Đóng `System.out` cũng có thể làm những lần xuất tiếp theo thất bại; `PrintStream` không nhất thiết ném ngoại lệ ghi theo cách bạn mong đợi.

Nếu thực sự có trường hợp chương trình cần đóng standard stream, đó là quyết định cấp ứng dụng có chủ đích, không nên xảy ra bên trong helper đọc một dòng. Nếu chỉ muốn chắc prompt xuất ra, `System.out.flush()` không có nghĩa đóng `System.out`.

### 12.2. Resource do framework/container cấp

Một framework có thể trao request body stream, response writer hoặc connection được quản lý theo vòng đời request/transaction. Cho dù object có `close()`, thư viện nhận nó không nên tự đóng nếu framework giữ ownership. Phải theo tài liệu chính thức của framework cụ thể; cùng kiểu `InputStream` không nói lên ownership. Nếu phương thức API của bạn **nhận quyền sở hữu** thay vì mượn, hãy ghi rõ và bảo đảm lỗi/cleanup đúng trong mọi đường đi.

### 12.3. Shared resource giữa nhiều thành phần

Hai service cùng dùng một stream không nên đều tin rằng mình là owner độc lập. Có thể để một owner cấp reference mượn, dùng cơ chế lease hoặc một service có trách nhiệm quản lý vòng đời. Nếu resource có thể được nhiều thread dùng đồng thời, cần thêm hợp đồng **thread safety** và đồng bộ hóa: ownership không tự làm việc đọc/ghi đồng thời an toàn.

### 12.4. Async: thời gian sống của task lớn hơn thời gian sống của method

~~~java
// PHẢN VÍ DỤ THIẾT KẾ — không thực thi như code production.
try (InputStream in = Files.newInputStream(path)) {
    CompletableFuture.runAsync(() -> consume(in));
} // in.close() có thể xảy ra trước khi task consume(in) đọc xong.
~~~

Đây là **sketch** minh họa lifecycle, không phải chương trình chạy độc lập; `consume` là hàm do ứng dụng định nghĩa và cần xử lý `IOException`. Vấn đề là `runAsync` trả về trước khi task hoàn thành. Nếu callback còn đang đọc khi khối try kết thúc, resource đã đóng quá sớm.

Cách đúng là để **task sở hữu việc mở/đóng** bên trong chính tác vụ, hoặc để owner **chờ task hoàn tất** trước khi đóng, có xử lý timeout/cancel/exception. Không đặt try-with-resources bên ngoài rồi phát task nền với resource bị ràng buộc vào scope ngắn hơn task.

### 12.5. Kết thúc xử lý và đóng nguồn là hai việc khác nhau

Một parser có thể dừng sau vài byte header; điều đó **không** cho phép nó đóng stream borrowed. Một reader đọc hết EOF vẫn cần owner quyết định khi đóng handle. Một file reader được đóng không có nghĩa xóa file trên filesystem. Ngược lại, file có thể vẫn tồn tại sau khi mọi handle đã đóng.

## 13. Kiểm thử quy tắc sở hữu

Đừng chỉ kiểm tra rằng dữ liệu được copy đúng. Kiểm thử cũng cần trả lời **ai gọi close và gọi bao nhiêu lần**.

- Với API borrowed, dùng stream bọc có biến `closeCalls`; gọi hàm rồi xác nhận **không bị đóng** khi hàm return, kể cả trường hợp exception. Demo `BorrowedCopyDemo` là ví dụ dễ quan sát.
- Với API owned, dùng fake `Closeable` hoặc bộ đếm close; bảo đảm resource được đóng cả khi thành công lẫn khi body ném lỗi.
- Với API trả resource, nhận stream rồi dùng try-with-resources ở caller; kiểm tra ví dụ/test documentation thể hiện nghĩa vụ của caller.
- Với wrapper, kiểm tra đóng outer có đóng delegate không, dựa trên contract từng lớp. Nếu delegate là resource borrowed, không “sửa” bằng cách đóng outer một cách vô thức.
- Với output, kiểm tra việc flush/close theo đúng thời điểm; test dữ liệu đã ghi là cần thiết nhưng không thay thế kiểm tra resource release.
- Nếu không có fake, có thể dùng file tạm và kiểm tra handle/resource phù hợp OS hoặc công cụ theo dõi file descriptors, nhưng không suy ra mọi OS xử lý file đang mở giống nhau.
- Kiểm tra đường exception và suppressed close errors khi release cũng có thể thất bại.

**Không cần test rằng mọi object Java đều phải bị close chính xác một lần.** Ví dụ `ByteArrayInputStream.close()` được tài liệu quy định không có tác dụng; điều quan trọng là **contract ownership** của API được tuân thủ và không tạo hành vi bất ngờ khi implementation đổi từ bộ nhớ sang tệp hoặc socket.

## 14. Checklist thiết kế API I/O trước khi công bố

| Câu hỏi | Quyết định cần ghi rõ |
| --- | --- |
| Resource được **tạo ở đâu**? | Hàm tự mở, caller mở, factory chuyển ownership hay framework quản lý? |
| Resource được **dùng trong bao lâu**? | Chỉ trong method, sau return, vòng đời của object, request, hay tác vụ async? |
| Ai có quyền **close**? | Callee, caller, callback boundary, framework hay owner cấp ứng dụng? |
| Method trả về dữ liệu hay **resource còn mở**? | `String/byte[]` đã đọc xong khác `InputStream/Stream<String>` lazy. |
| Có wrapper không? | `close()` lớp ngoài có lan tới nguồn bên trong không? |
| Method có **flush** không? | Nếu có, khi nào; không coi flush đồng nghĩa với close hoặc sync đĩa. |
| Khi exception xảy ra? | Ai vẫn đóng resource, lỗi close được báo thế nào, suppressed được giữ không? |
| Có shared access/thread khác dùng không? | Ai điều phối đóng, tránh đóng khi còn người đang đọc/ghi? |
| Resource được giao **ownership mới** như thế nào? | Factory return, constructor transfer, explicit close-on-completion hoặc callback scope? |
| Người gọi sẽ biết contract ở đâu? | Tên method, Javadoc, kiểu trả về, test và ví dụ gọi minh bạch. |

## 15. Những lỗi phổ biến trong code review

1. **“Ai tạo thì luôn phải đóng.”** Không hoàn toàn đúng: factory tạo rồi trả resource có thể chuyển ownership cho caller; framework có thể tạo resource vẫn giữ trách nhiệm dọn.
2. **“Method nhận `InputStream` thì cứ `try (in)`.”** Sai nếu input chỉ borrowed; try tự đóng stream được mượn.
3. **“Không thấy `close()` trong helper nghĩa là leak.”** Có thể owner ở caller; xem toàn bộ vòng đời và contract.
4. **“Đóng BufferedReader chỉ đóng buffer của nó.”** Sai với wrapper chuẩn: thường đóng luôn reader/stream bên trong.
5. **“Scanner đóng không ảnh hưởng System.in.”** Sai nếu Scanner được tạo từ `System.in`; đóng Scanner sẽ đóng nguồn `Closeable`.
6. **“`findFirst()`/`count()` làm `Files.lines` tự đóng.”** Sai: đóng `Stream` có resource bằng try-with-resources.
7. **“`transferTo` tự đóng input và output.”** Sai: phương thức copy không nhận ownership hai stream.
8. **“`flush()` là đủ, không cần close.”** Flush không kết thúc vòng đời hoặc giải phóng handle.
9. **“close không thể ném lỗi.”** Sai: `IOException` hoặc exception trong `AutoCloseable.close()` có thể xuất hiện lúc cleanup.
10. **“Khi body ném lỗi, close không chạy.”** Sai với try-with-resources; close vẫn diễn ra và lỗi phụ nằm trong `getSuppressed()`.
11. **“Dùng resource sau khi method callback return vẫn được.”** Sai nếu scope owner đã đóng tài nguyên; đây là lỗi lifetime escape.
12. **“Chạy async trong try, rồi return là ổn.”** Task có thể sống lâu hơn scope; resource bị đóng khi task còn dùng.
13. **“Cứ gọi close hai lần cho chắc.”** `Closeable` nói close lại không có hiệu lực, nhưng `AutoCloseable` rộng hơn không bắt buộc idempotent; cần một owner rõ ràng.
14. **“Đóng file đồng nghĩa xóa file.”** Hai thao tác độc lập, resource close và file deletion có vòng đời khác.
15. **“Bỏ qua lỗi đóng tệp vì thao tác write đã thành công.”** Close có thể là lúc buffer flush hoặc lỗi được phát hiện; phải xử lý theo mức bảo đảm dữ liệu yêu cầu.

## 16. Câu hỏi tự kiểm tra

1. Hàm `copy(InputStream in, OutputStream out)` do thư viện cung cấp, caller truyền vào socket output còn dùng sau đó. Ai nên đóng `out` và vì sao?
2. `Files.readString(path)` và `Files.lines(path)` khác nhau thế nào về ownership?
3. Khi bạn đóng `BufferedReader` được tạo từ `InputStreamReader(System.in)`, điều gì có thể xảy ra với `System.in`?
4. Một factory `openLog(Path)` trả `InputStream`. Javadoc nào phải có để caller không quên close?
5. Vì sao `try (InputStream in = callerInput)` bên trong method có thể vi phạm contract?
6. Nếu body ném exception và hai resource close cũng ném, chúng được báo ra sao?
7. Tại sao `new Scanner(System.in)` rồi close scanner sau một lần đọc có thể phá CLI còn câu hỏi tiếp theo?
8. Callback được mượn reader trong `withReader(path, callback)` có được giữ reader vào field để thread nền dùng sau không?
9. Nếu resource được mở ở main nhưng truyền vào một task async, ai phải quyết định thời điểm đóng?
10. Có nên sửa resource leak bằng cách đóng mọi `AutoCloseable` nhìn thấy trong code không? Hãy nêu hợp đồng nào cần xác nhận trước.

**Gợi ý đáp án:** (1) Caller/owner vì helper chỉ mượn stream; (2) readString tự quản lý handle, lines trả stream lazy caller phải close; (3) wrapper close có thể đóng stdin; (4) mô tả returned stream đang mở và caller phải đóng; (5) try sẽ close biến borrowed; (6) exception body là primary, lỗi close được suppressed và thứ tự close ngược khai báo; (7) scanner có thể đóng source; (8) không nếu owner đóng khi callback kết thúc; (9) owner đóng khi task đã xong hoặc task tự nhận quyền sở hữu; (10) không, phải biết ownership và wrapper propagation.

## 17. Tài liệu API chuẩn

- [Oracle Java SE 21 — Closeable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Closeable.html): close giải phóng tài nguyên I/O, contract về close lại và lỗi IOException.
- [Oracle Java SE 21 — AutoCloseable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/AutoCloseable.html): try-with-resources và lưu ý về close có thể ném exception.
- [Oracle Java SE 21 — Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): phương thức tự đọc dữ liệu, phương thức trả stream còn mở, và yêu cầu đóng `Files.lines/list/walk`.
- [Oracle Java SE 21 — Scanner](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Scanner.html): đóng scanner cũng đóng nguồn đầu vào nếu nguồn implement `Closeable`.
- [Oracle Java SE 21 — InputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStream.html): `close()`, `transferTo()` và phân biệt hành vi copy với đóng resource.
- [Oracle Java SE 21 — BufferedReader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/BufferedReader.html) và [InputStreamReader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStreamReader.html): quan hệ giữa wrapper và nguồn bên dưới.

**Ghi nhớ thực hành:** **“Ai mở, ai đóng” là câu hỏi về contract ownership, không phải về vị trí của từ khóa `new`.** Nếu bạn tạo resource để dùng nội bộ, hãy dùng try-with-resources và dọn nó trong scope. Nếu mượn resource từ caller, đừng tự đóng. Nếu trả resource còn mở, hãy chuyển nghĩa vụ đóng một cách tường minh. Với wrapper, callback và async task, luôn kiểm tra vòng đời thực của underlying resource.