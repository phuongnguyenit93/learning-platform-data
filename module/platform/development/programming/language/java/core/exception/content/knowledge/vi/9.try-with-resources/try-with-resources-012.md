# Quyền sở hữu tài nguyên và trường hợp không nên tự động đóng trong Java

## 1. Mục tiêu bài học

`try-with-resources` giúp Java tự gọi `close()` khi rời một vùng mã. Nhưng **có thể đóng** và **có quyền đóng** là hai chuyện khác nhau: đối tượng triển khai `AutoCloseable` không có nghĩa bất kỳ phương thức nào được nhận tham chiếu đến nó cũng nên tự động kết thúc vòng đời đối tượng đó.

Một phương thức đọc dữ liệu được truyền `InputStream` từ bên ngoài có thể chỉ **mượn** tài nguyên. Trái lại, một phương thức tự mở tệp để hoàn thành công việc thường phải **sở hữu trách nhiệm đóng** tệp ấy. Trong ứng dụng có framework, connection pool, giao dịch hoặc vòng đời request, việc đóng tài nguyên tại một scope quá nhỏ có thể làm thành phần khác mất khả năng sử dụng tài nguyên, dù mã có vẻ “đúng mẫu” `try-with-resources`.

Sau bài này, bạn có thể:

- Phân biệt tài nguyên **owned (sở hữu)**, **borrowed (mượn)**, **transferred (chuyển giao quyền đóng)** và **framework-managed (do tầng khác quản lý vòng đời)**.
- Chọn có dùng `try-with-resources` hay không dựa trên **hợp đồng quyền sở hữu** và vòng đời thực tế, không chỉ dựa trên kiểu `AutoCloseable`.
- Nhận diện trường hợp đóng một wrapper kéo theo đóng stream/reader mà nó bao bọc.
- Hiểu vì sao `try (resource)` của Java 9+ vẫn tự đóng đối tượng dù biến được khai báo bên ngoài.
- Thiết kế các hàm nhận `InputStream`, `Reader`, `Connection` và các factory trả resource sao cho người gọi biết ai phải đóng.
- Tránh leak, double-close, trả một tài nguyên đã đóng, đóng nhầm `System.in`/`System.out` hoặc tài nguyên do framework sở hữu.
- Xử lý cleanup khi khởi tạo nhiều resource hoặc xảy ra ngoại lệ mà không phá vỡ hợp đồng của bên gọi.

Các ví dụ Java 17+ độc lập có lệnh biên dịch/chạy và kết quả `stdout` xác định. Những đoạn chỉ minh họa chữ ký hoặc phụ thuộc API bên ngoài được ghi rõ.

## 2. `try-with-resources` bảo đảm điều gì — và không bảo đảm điều gì?

Cấu trúc Java quen thuộc:

```java
try (java.io.BufferedReader reader =
        java.nio.file.Files.newBufferedReader(path)) {
    System.out.println(reader.readLine());
}
```

Đây là **mảnh mã** trong một phương thức có biến `path` kiểu `Path` và xử lý/khai báo `IOException`. `reader` là resource được khai báo trong header. Khi phạm vi kết thúc, Java gọi `reader.close()`, ngay cả khi phần thân kết thúc đột ngột do ngoại lệ hoặc `return`.

Mệnh đề `try-with-resources` quản lý việc gọi `close()` theo cú pháp, nhưng **không tự biết**:

1. Resource có phải do phương thức này sở hữu hay chỉ được mượn.
2. Resource còn phải được nơi khác dùng sau đó hay không.
3. `close()` có kết thúc socket/file vật lý, trả connection về pool, flush dữ liệu, hay thực hiện hành vi khác.
4. Wrapper đóng có kéo theo đóng tài nguyên nền hay không.
5. Một resource được tham chiếu ở hai vị trí của header có thực chất là cùng một đối tượng hay không.
6. Liệu đóng ở thời điểm này có đúng với transaction/request/session lifecycle hay không.

Điểm mấu chốt: **`try-with-resources` là cơ chế đóng tự động; nó không phải hệ thống kiểm tra quyền sở hữu.** Java không có trình biên dịch theo kiểu “ownership type system” bắt buộc bạn chứng minh đã sở hữu resource trước khi đưa vào header.

### `AutoCloseable` không đồng nghĩa “luôn đóng ngay khi dùng xong một phương thức”

`java.lang.AutoCloseable` công bố phương thức `close()`. Một số implementation của `close()` có thể có side effect và ném ngoại lệ. `Closeable` dành cho nhiều tài nguyên I/O và có hợp đồng riêng. Tuy nhiên, **interface không cho biết ai là owner**; điều đó đến từ hợp đồng API, kiến trúc và đối tượng tạo/quản lý tài nguyên.

Do vậy, cách sử dụng tốt không phải “không bao giờ dùng `try-with-resources` với tham số”, mà là “dùng khi **scope đó đã nhận quyền sở hữu và trách nhiệm đóng** theo hợp đồng”.

## 3. Bốn mô hình quyền sở hữu thường gặp

| Mô hình | Ví dụ | Ai quyết định đóng? | Khuyến nghị |
| --- | --- | --- | --- |
| **Owned** | Phương thức tự mở tệp, tự tạo reader/stream để dùng nội bộ | Chính phương thức hoặc component nhận quyền sở hữu rõ ràng | Đóng trong đúng scope, thường bằng `try-with-resources` |
| **Borrowed** | Hàm parse nhận `Reader` từ người gọi chỉ để đọc | Người gọi vẫn sở hữu | Hàm parse **không** tự đóng tham số, trừ khi hợp đồng nói khác |
| **Ownership transfer** | Factory trả về `InputStream` mới mở và chuyển trách nhiệm cho caller | Caller sau khi nhận thành công | API phải ghi rõ caller phải đóng; caller dùng `try-with-resources` |
| **Framework-managed / pooled** | Connection/session/stream do container, transaction manager hoặc pool cấp | Theo hợp đồng framework/pool hoặc đơn vị giữ lifecycle | Không tự đóng chỉ vì có thể gọi `close()`; tuân thủ phạm vi và quy tắc trả về do API quy định |

**Lưu ý quan trọng về pool:** Nhiều `Connection` được cấp từ pool có `close()` mang nghĩa **trả logical connection về pool**, không nhất thiết đóng kết nối vật lý. Nếu bạn là người được pool giao quyền sử dụng một connection với trách nhiệm trả về, `try-with-resources` có thể hoàn toàn đúng. Nếu một connection được *mượn* từ caller/transaction manager đang quản lý chung, đóng trong hàm phụ trợ có thể quá sớm.

### Quyền sở hữu nên được xác định bằng hợp đồng, không bằng phỏng đoán

Hãy trả lời trước khi thêm `try (resource)`:

- **Ai tạo hoặc nhận resource từ factory?** Người tạo thường chịu trách nhiệm ban đầu, nhưng có thể chuyển quyền sở hữu.
- **Ai được phép kết thúc vòng đời?** Có thể là caller, callee, transaction manager, container hoặc application shutdown.
- **Sau lời gọi này, có nơi nào còn cần resource không?**
- **`close()` thực hiện chính xác điều gì?** Chỉ đóng wrapper, đóng cả delegate, flush output, trả connection về pool hay rollback transaction?
- **Có xảy ra đóng trùng hoặc leak trên đường lỗi không?**
- **Hợp đồng API đã mô tả trách nhiệm đóng và tình huống lỗi chưa?**

Đừng căn cứ duy nhất vào việc “đối tượng không còn được dùng trong phương thức hiện tại”. Nó có thể vẫn còn được dùng bởi caller hoặc các phần khác của ứng dụng.

## 4. Khi nào nên tự động đóng?

### 4.1. Resource do phương thức tự tạo và không thoát ra ngoài

Ví dụ hợp lệ:

```java
static String readFirstLine(java.nio.file.Path path)
        throws java.io.IOException {
    try (java.io.BufferedReader reader =
            java.nio.file.Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
```

Đây là **mảnh phương thức**. Reader được tạo trong phương thức, dữ liệu trả về là một `String` chứ không phải chính reader. Scope của công việc và vòng đời resource trùng nhau: mở, đọc, đóng, trả giá trị.

`try-with-resources` còn gọi `close()` khi `readLine()` ném ngoại lệ; thao tác close vẫn có thể ném ngoại lệ riêng, được xử lý theo quy tắc suppressed exception.

### 4.2. Caller nhận quyền sở hữu rõ ràng

Khi API của một factory trả một tài nguyên **đang mở** và tuyên bố người gọi có trách nhiệm đóng, caller thường nên dùng:

```java
try (java.io.InputStream input = openOwnedStream()) {
    useInput(input);
}
```

Đây là **mảnh minh họa**, cần định nghĩa `openOwnedStream()` và `useInput(...)`, đồng thời xử lý checked exception phù hợp. Quyền sở hữu **được chuyển** từ factory sang caller ở kết quả thành công; caller chịu trách nhiệm đóng.

Nếu factory trả resource nhưng nó thực ra thuộc vòng đời của đối tượng khác, API đó phải mô tả rõ; đừng suy luận chỉ từ tên `open...`.

### 4.3. Scope quản lý trùng scope sử dụng

Trong một CLI đọc tệp một lần, scope có thể nằm gọn trong một phương thức. Trong service kết nối cơ sở dữ liệu nhiều bước, scope có thể là cả transaction. Trong server, scope của một request hoặc của ứng dụng là hai thứ khác nhau. Chọn scope theo **đơn vị công việc cần tài nguyên tồn tại**, không theo số dòng ngắn nhất có thể đưa vào `try`.

## 5. Khi nào **không nên tự động đóng**?

### 5.1. Hàm chỉ mượn `InputStream` hoặc `Reader`

Ví dụ một parser nhận `Reader` do caller truyền và chỉ cần đọc dữ liệu. Nếu parser tự viết:

```java
static String parse(java.io.Reader source)
        throws java.io.IOException {
    try (source) {
        char[] buffer = new char[16];
        int count = source.read(buffer);
        return count < 0 ? "" : new String(buffer, 0, count);
    }
}
```

Đây là **mảnh phương thức hợp lệ từ Java 9+** nếu tham số `source` effectively final, nhưng có thể **sai về hợp đồng**: nó tự đóng reader mà caller đưa vào.

Nếu hợp đồng nói “caller retains ownership”, nên giữ nguyên reader mở:

```java
static String parseBorrowed(java.io.Reader source)
        throws java.io.IOException {
    char[] buffer = new char[16];
    int count = source.read(buffer);
    return count < 0 ? "" : new String(buffer, 0, count);
}
```

Đây là mảnh phương thức dùng reader mượn; caller vẫn chịu trách nhiệm đóng. Cả hai phương thức đều có thể đọc và trả `String`; khác biệt nằm ở **quyền kết thúc vòng đời**.

**Không nên đóng tài nguyên mượn kể cả khi xử lý thất bại** nếu hợp đồng yêu cầu caller giữ quyền sở hữu. Hãy truyền ngoại lệ ra, để caller quyết định retry, reset, tiếp tục hoặc đóng.

### 5.2. Stream chuẩn do tiến trình quản lý

Các stream như `System.in`, `System.out` và `System.err` thường được dùng bởi nhiều phần của ứng dụng. Một helper không nên tùy ý:

```java
try (java.io.InputStream input = System.in) {
    // ...
}
```

Đây là mảnh mã hợp lệ nhưng **rủi ro**: nó sẽ đóng `System.in` khi rời khối. Các bước nhập liệu sau đó có thể không còn dùng được stream này.

Tương tự, đóng một `Scanner` được tạo trên `System.in` thường cũng đóng stream nền, vì `Scanner.close()` đóng nguồn nếu nguồn triển khai `Closeable`. Nếu một ứng dụng xác định riêng rằng đã kết thúc hoàn toàn việc đọc stdin, chủ sở hữu cấp ứng dụng có thể có chính sách đóng phù hợp. Nhưng **helper ngắn hạn** không nên áp chính sách đó cho toàn tiến trình.

`System.out` và `System.err` cũng không nên bị helper đóng sớm; việc đóng wrapper/output có thể khiến các bước log/in tiếp theo gặp lỗi hoặc không còn hoạt động như mong đợi.

### 5.3. Tài nguyên thuộc framework, container hoặc transaction

Những trường hợp cần xem hợp đồng framework:

- Request/response body stream do web server/container quản lý.
- Một `Connection` được caller truyền để tham gia transaction đang mở.
- Session hoặc entity manager được transaction manager quản lý.
- Stream nằm trong một pipeline do tầng điều phối cần tiếp tục xử lý.
- Resource dùng chung nhiều lời gọi hoặc sống đến khi component/service shutdown.

Một phương thức phục vụ nghiệp vụ **không tự động trở thành owner** của resource chỉ vì nó nhận được tham chiếu. Nếu framework giao quyền đóng cho ứng dụng trong phạm vi cụ thể (ví dụ connection checkout độc lập), hãy đóng đúng hạn theo tài liệu của framework.

### 5.4. Resource còn được trả về hoặc lưu lại để dùng sau

Sai lầm điển hình:

```java
static java.io.BufferedReader openBroken(java.nio.file.Path path)
        throws java.io.IOException {
    try (java.io.BufferedReader reader =
            java.nio.file.Files.newBufferedReader(path)) {
        return reader; // Trả tham chiếu đến reader đang chuẩn bị bị đóng.
    }
}
```

Đây là mảnh phương thức **biên dịch được nhưng sai về vòng đời**. Trong quá trình `return`, `try-with-resources` đóng `reader` trước khi caller nhận giá trị. Caller nhận đối tượng đã đóng. Gọi `readLine()` sau đó có thể phát sinh `IOException` vì stream không còn mở.

Cách đúng nếu muốn chuyển quyền sở hữu:

```java
static java.io.BufferedReader openOwned(java.nio.file.Path path)
        throws java.io.IOException {
    return java.nio.file.Files.newBufferedReader(path);
}
```

Caller sau đó chịu trách nhiệm:

```java
try (java.io.BufferedReader reader = openOwned(path)) {
    System.out.println(reader.readLine());
}
```

Các đoạn trên là **mảnh mã minh họa**; `path` phải là biến hợp lệ và caller xử lý/khai báo `IOException`. Không đóng resource ở factory trên đường thành công nếu hợp đồng đã **chuyển quyền sở hữu** cho caller.

## 6. Chương trình chạy được: resource mượn và resource được sở hữu

Tạo file **`BorrowedOwnedDemo.java`**:

```java
import java.io.IOException;
import java.io.StringReader;

public class BorrowedOwnedDemo {
    static class TrackedReader extends StringReader {
        private boolean closeCalled;

        TrackedReader(String text) {
            super(text);
        }

        @Override
        public void close() {
            closeCalled = true;
            super.close();
        }

        boolean closeCalled() {
            return closeCalled;
        }
    }

    static String readBorrowed(TrackedReader source)
            throws IOException {
        char[] chars = new char[16];
        int count = source.read(chars);
        return count < 0 ? "" : new String(chars, 0, count);
    }

    public static void main(String[] args) throws IOException {
        TrackedReader external = new TrackedReader("alpha");

        System.out.println("borrowed=" + readBorrowed(external));
        System.out.println("borrowed closed=" + external.closeCalled());

        TrackedReader owned = new TrackedReader("beta");
        try (owned) {
            System.out.println("owned=" + readBorrowed(owned));
        }
        System.out.println("owned closed=" + owned.closeCalled());

        external.close();
        System.out.println("external closed by owner="
                + external.closeCalled());
    }
}
```

Chạy bằng JDK 17+:

```bash
javac BorrowedOwnedDemo.java
java BorrowedOwnedDemo
```

`stdout`:

```text
borrowed=alpha
borrowed closed=false
owned=beta
owned closed=true
external closed by owner=true
```

Giải thích:

1. `external` được tạo ở `main` và truyền cho `readBorrowed`, nhưng hàm đó **không** đặt resource vào header `try` và không gọi `close()`.
2. Sau khi đọc, `external.closeCalled()` vẫn là `false`; `main` còn quyền quyết định vòng đời.
3. `owned` là resource mà scope `main` chủ động quản lý bằng `try (owned)`. Java 9+ cho phép cú pháp này vì biến effectively final.
4. Khi rời khối, Java gọi `owned.close()` nên cờ theo dõi thành `true`.
5. Cuối cùng, `main` tự đóng `external` tại nơi có quyền sở hữu.

Cờ `closeCalled` là cơ chế theo dõi **được thiết kế trong ví dụ**, không phải API chung có sẵn của mọi `Reader`. Ví dụ không cần tệp hoặc network, nên đầu ra ổn định.

## 7. Đóng wrapper có thể đóng cả tài nguyên nền

Một nguồn lỗi khác là **wrapper cascading close**. Các lớp bọc tài nguyên thường chuyển tiếp thao tác `close()` xuống delegate.

Ví dụ:

```java
java.io.InputStream borrowedInput = getBorrowedInput();

try (java.io.BufferedReader reader = new java.io.BufferedReader(
        new java.io.InputStreamReader(borrowedInput))) {
    System.out.println(reader.readLine());
}
```

Đây là **mảnh minh họa**, cần định nghĩa `getBorrowedInput()` và xử lý checked exception. Đóng `BufferedReader` sẽ đóng `InputStreamReader`, từ đó đóng `borrowedInput`. **Chỉ vì tên `borrowedInput` không xuất hiện trong header không có nghĩa nó không bị đóng.**

Đây là một lý do quan trọng để tra hợp đồng `close()` của wrapper: `BufferedReader`, `InputStreamReader`, `BufferedInputStream` và nhiều wrapper khác thường sở hữu việc đóng delegate.

### Ví dụ chạy được: `close()` lan qua wrapper

Tạo tệp **`WrapperCascadeDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class WrapperCascadeDemo {
    static class TrackedInput extends ByteArrayInputStream {
        private boolean closeCalled;

        TrackedInput(String text) {
            super(text.getBytes(StandardCharsets.UTF_8));
        }

        @Override
        public void close() {
            closeCalled = true;
            super.close();
        }

        boolean closeCalled() {
            return closeCalled;
        }
    }

    public static void main(String[] args) throws IOException {
        TrackedInput input = new TrackedInput("hello");

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(input, StandardCharsets.UTF_8))) {
            System.out.println("read=" + reader.readLine());
        }

        System.out.println("underlying close called="
                + input.closeCalled());
    }
}
```

```bash
javac WrapperCascadeDemo.java
java WrapperCascadeDemo
```

`stdout`:

```text
read=hello
underlying close called=true
```

`ByteArrayInputStream` gốc được override `close()` chỉ để ghi nhận lời gọi; class này bình thường có `close()` không gây tác động đáng kể. Dù vậy, cờ chứng minh lời gọi **đã được chuyển tiếp** qua lớp bọc. Với file, socket hoặc tài nguyên bên ngoài, tác động đóng có thể là thực sự giải phóng tài nguyên.

### Khi nào dùng wrapper mà vẫn muốn giữ stream nền mở?

Nếu hợp đồng yêu cầu giữ delegate mở, có ba hướng thường phù hợp:

- Tránh tạo wrapper có quyền đóng delegate trong phạm vi ngắn; trực tiếp dùng API trên borrowed stream nếu đủ nhu cầu.
- Điều chỉnh API để **caller tạo, sở hữu và đóng wrapper**, trong khi helper chỉ mượn wrapper để đọc.
- Khi thật sự cần, dùng một wrapper **leave-open/non-closing** có hành vi đóng được xác định rõ, và kiểm tra tác động đến buffer, flush, trạng thái stream, lỗi và việc đóng resource. Đây là thiết kế cần chủ đích, không phải thủ thuật áp dụng mặc định.

Không nên đơn giản bỏ `close()` trong mọi trường hợp: một số wrapper có buffer đầu ra cần flush/finish để bảo đảm tính toàn vẹn dữ liệu. Việc giữ stream nền mở phải đi cùng chính sách kết thúc wrapper và flush dữ liệu rõ ràng.

## 8. Chương trình chạy được: wrapper không đóng input mượn

Đôi khi phải sử dụng API của wrapper nhưng vẫn để caller sở hữu stream nền. Một cách minh họa là tạo một lớp bọc `InputStream` mà `close()` **không đóng delegate**.

Tạo file **`LeaveOpenDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class LeaveOpenDemo {
    static class TrackedInput extends ByteArrayInputStream {
        private boolean closeCalled;

        TrackedInput(String text) {
            super(text.getBytes(StandardCharsets.UTF_8));
        }

        @Override
        public void close() {
            closeCalled = true;
            super.close();
        }

        boolean closeCalled() {
            return closeCalled;
        }
    }

    static class LeaveOpenInput extends FilterInputStream {
        LeaveOpenInput(InputStream source) {
            super(source);
        }

        @Override
        public void close() {
            // Chủ ý không đóng delegate: ownership vẫn thuộc caller.
        }
    }

    static String readBorrowed(InputStream source)
            throws IOException {
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                        new LeaveOpenInput(source),
                        StandardCharsets.UTF_8))) {
            return reader.readLine();
        }
    }

    public static void main(String[] args) throws IOException {
        TrackedInput external = new TrackedInput("line one\nline two");

        System.out.println("line=" + readBorrowed(external));
        System.out.println("closed by helper=" + external.closeCalled());
        external.close();
        System.out.println("closed by caller=" + external.closeCalled());
    }
}
```

```bash
javac LeaveOpenDemo.java
java LeaveOpenDemo
```

`stdout`:

```text
line=line one
closed by helper=false
closed by caller=true
```

Đây là một **cơ chế minh họa có chủ đích**, không phải quy tắc mọi wrapper `AutoCloseable`. `BufferedReader.close()` vẫn được gọi theo `try-with-resources`, nhưng thao tác đóng đến `LeaveOpenInput` không được chuyển tiếp xuống `external`.

**Cảnh báo với buffering:** một wrapper có thể đã đọc trước nhiều byte hơn kết quả trả về. Trong ví dụ, `BufferedReader.readLine()` có thể buffer cả `line two` trước khi trả về `line one`; đóng wrapper rồi tiếp tục đọc trực tiếp từ `external` có thể làm mất dữ liệu logic đối với caller. Vì vậy, chỉ dùng mẫu leave-open khi hợp đồng thật sự cho phép sự khác biệt giữa **trạng thái stream nền** và **trạng thái buffer của wrapper**. Với giao thức cần giữ nguyên vị trí đọc, hãy thống nhất wrapper do caller sở hữu và tái sử dụng nó, thay vì tạo wrapper tạm chỉ để đọc một phần.

Ví dụ trên chỉ kiểm chứng **không gọi `close()` trên stream nền**, không cam kết dữ liệu còn lại sẽ luôn đọc được theo cách ban đầu.

## 9. `try (resource)` Java 9+ vẫn đóng đối tượng mượn nếu dùng sai

Từ Java 9, có thể viết:

```java
static void process(java.io.Reader borrowed)
        throws java.io.IOException {
    try (borrowed) {
        // Đọc dữ liệu.
    }
}
```

Đây là mảnh phương thức cú pháp **hợp lệ** vì tham số `borrowed` không bị gán lại (effectively final) và `Reader` thực thi `Closeable`/`AutoCloseable`. Tuy nhiên, khi rời `try`, `close()` sẽ được gọi trên **đúng đối tượng mà caller truyền vào**.

Điều kiện final/effectively final chỉ quyết định **tính hợp lệ của biến trong header**, không quyết định **quyền sở hữu**.

So sánh:

| Mã | Hành vi | Đúng khi nào? |
| --- | --- | --- |
| `try (Reader r = openMyFile())` | Scope mở và đóng reader | Khi scope này sở hữu resource |
| `try (borrowedReader)` | Đóng reader đã được caller cấp | Chỉ khi caller giao quyền đóng |
| `try (Reader alias = borrowedReader)` | Đóng cùng đối tượng qua alias | Không bảo vệ reader mượn khỏi bị đóng |
| `try (BufferedReader b = new BufferedReader(borrowedReader))` | Thường đóng cả borrowed reader qua wrapper | Chỉ nếu có quyền đóng cả delegate |
| Không dùng TWR trên tham số mượn | Không tự động đóng tham số | Khi caller vẫn sở hữu và tự đóng |
| `try (Reader r = factoryTransfersOwnership())` | Caller nhận và đóng resource | Khi factory đã chuyển giao quyền đóng |

**Alias không tạo bản sao resource.** Việc khai báo `Reader managed = borrowedReader` chỉ tạo một tham chiếu khác; đóng một trong hai alias vẫn đóng cùng đối tượng, trừ khi một lớp bọc đã định nghĩa hành vi khác rõ ràng.

## 10. Quyền sở hữu với JDBC và connection pool

JDBC là ví dụ mà việc hiểu sai quyền sở hữu gây hậu quả lớn.

### 10.1. Hàm nhận `Connection` từ caller: thường không đóng `Connection`

Ví dụ đoạn mã **minh họa, không có `main` hoặc database thật**:

```java
static int countRows(java.sql.Connection connection)
        throws java.sql.SQLException {
    try (java.sql.PreparedStatement statement =
            connection.prepareStatement(
                    "SELECT COUNT(*) FROM inventory");
         java.sql.ResultSet rows = statement.executeQuery()) {
        rows.next();
        return rows.getInt(1);
    }
}
```

Trong ví dụ, `connection` là **borrowed resource** được caller truyền vào. Hàm này chỉ quản lý statement và result set mà nó tạo cho truy vấn; nó **không tự đóng connection**. Caller/transaction manager có thể tiếp tục sử dụng connection cho nhiều câu lệnh hoặc quyết định commit/rollback ở phạm vi lớn hơn.

Đóng `ResultSet` trước `PreparedStatement` phù hợp thứ tự đóng ngược trong header. Thực tế JDBC cũng có quy tắc statement đóng các result set phụ thuộc, nên tránh dựa vào một số lần gọi close cố định; hãy theo hợp đồng driver/framework và không giả định mọi đối tượng đều đóng lặp an toàn theo mọi cách.

**Điểm quan trọng:** câu “không đóng connection” ở đây bắt nguồn từ giả định **callee chỉ mượn connection**. Nếu chính phương thức lấy connection từ `DataSource`, chịu trách nhiệm cho một unit of work và không chuyển quyền đóng đi, thì `try (Connection connection = dataSource.getConnection())` có thể là lựa chọn đúng để trả connection về pool đúng hạn.

### 10.2. Đừng nhầm đóng connection với kết thúc transaction

`Connection.close()` và `commit()`/`rollback()` là những hành động khác nhau. Không được coi việc kết thúc một scope TWR là cách duy nhất để quyết định transaction thành công hay thất bại. Nếu auto-commit tắt, cần có chính sách commit/rollback do tầng sở hữu transaction quyết định, với các quy tắc của JDBC, driver và pool đang dùng.

Nếu một hàm phụ trợ tự đóng connection đang thuộc transaction của caller, nó có thể làm gián đoạn transaction, trả connection về pool quá sớm hoặc khiến những thao tác kế tiếp thất bại.

### 10.3. Pool có thể thay đổi ý nghĩa của `close()`

Một connection proxy do pool trả về thường dùng `close()` để **trả logical handle về pool**, không nhất thiết ngắt kết nối TCP vật lý. Vì vậy, không đúng khi nói “tuyệt đối không đóng pooled connection”: nếu ứng dụng checkout connection theo hợp đồng và cần trả về sau công việc, **phải đóng/return đúng lúc**. Điều sai là đóng resource **không thuộc quyền sở hữu hiện tại** hoặc đóng **quá sớm**.

## 11. Trả resource từ factory: chuyển quyền sở hữu một cách tường minh

Một API mở tệp rồi trả `InputStream` có thể định nghĩa: “Caller must close the returned stream.” Khi đó **không dùng** TWR bao quanh resource trong chính factory nếu đường thành công muốn trả resource đang mở.

Tạo chương trình **`OwnershipTransferDemo.java`**:

```java
public class OwnershipTransferDemo {
    static class TrackedResource implements AutoCloseable {
        private final String name;

        TrackedResource(String name) {
            this.name = name;
        }

        void use() {
            System.out.println("use " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    // Hợp đồng: caller phải đóng đối tượng được trả về.
    static TrackedResource openOwned() {
        return new TrackedResource("report");
    }

    public static void main(String[] args) {
        try (TrackedResource resource = openOwned()) {
            resource.use();
        }
        System.out.println("done");
    }
}
```

```bash
javac OwnershipTransferDemo.java
java OwnershipTransferDemo
```

`stdout`:

```text
use report
close report
done
```

Quá trình:

1. `openOwned()` tạo resource và **chuyển trách nhiệm đóng** cho caller khi trả về thành công.
2. `main` khai báo resource trong header và trở thành owner cho phạm vi này.
3. Sau `use()`, Java tự gọi `close()`, rồi `main` in `done`.

Với factory thực tế có nhiều bước khởi tạo có thể thất bại, factory cần đóng những tài nguyên nó đã mở nhưng **chưa kịp chuyển giao quyền sở hữu** trên đường lỗi. Quyền sở hữu chỉ chuyển thành công sau khi kết quả hợp lệ được bàn giao.

### Factory không nên trả một tài nguyên đang đóng

Một lỗi dễ mắc:

```java
static TrackedResource openBroken() {
    try (TrackedResource resource = new TrackedResource("report")) {
        return resource;
    }
}
```

Đây là **mảnh phương thức** giả định lớp `TrackedResource` ở ví dụ trên. Trước khi caller nhận đối tượng, `try-with-resources` đã gọi `close()`. Trả tham chiếu vẫn có thể biên dịch, nhưng API “trả resource đang mở” bị vi phạm.

## 12. Tạo nhiều resource: tránh leak trước khi vào TWR

Khi khởi tạo tài nguyên bên ngoài header:

```java
Resource first = openFirst();      // Thành công.
Resource second = openSecond();    // Có thể ném ngoại lệ.
try (first; second) {
    use(first, second);
}
```

Đây là **mảnh minh họa**, cần định nghĩa `Resource` và các hàm. Nếu `openSecond()` ném ngoại lệ, chương trình **chưa thực thi** câu lệnh `try`; phạm vi TWR đó chưa chịu trách nhiệm đóng `first`. Điều này có thể gây leak.

Một cách phổ biến để tránh lỗi:

```java
try (Resource first = openFirst();
     Resource second = openSecond()) {
    use(first, second);
}
```

Đây cũng là mảnh minh họa. Khi resource thứ hai trong header khởi tạo thất bại, resource thứ nhất đã được tạo và quản lý sẽ được đóng theo ngữ nghĩa TWR.

### Khi buộc phải có resource trước header

Đôi khi resource được một tầng khác tạo và chuyển quyền sở hữu trước lời gọi. Hãy thiết kế **scope bảo vệ bắt đầu đủ sớm** để mọi đường lỗi sau thời điểm nhận quyền sở hữu đều có cleanup. Nếu caller vẫn sở hữu, **không** cố khắc phục nguy cơ leak bằng cách âm thầm nhận quyền đóng.

Cách tốt nhất phụ thuộc API: truyền factory/supplier để scope tự mở resource, dùng một object quản lý lifecycle, hoặc thiết lập hợp đồng chuyển quyền rõ ràng với try-with-resources ở caller.

## 13. Ngoại lệ từ `close()`: quyền sở hữu còn liên quan đến xử lý lỗi

Nếu đã nhận quyền đóng, bạn còn chịu trách nhiệm **quan sát lỗi đóng** phù hợp với hợp đồng.

Trong TWR:

- Nếu thân `try` thành công nhưng `close()` ném checked exception, cần bắt hoặc khai báo ngoại lệ đó.
- Nếu thân `try` ném một lỗi và `close()` cũng ném lỗi, lỗi của thân thường được giữ làm primary; lỗi từ `close()` nằm trong `getSuppressed()`.
- Nếu có nhiều resource, Java cố đóng theo thứ tự ngược và ghi nhận các lỗi đóng theo quy tắc suppressed.
- Đừng viết `finally` tự đóng trùng một resource đã được TWR quản lý, trừ khi API có yêu cầu rất cụ thể.

### Chương trình chạy được: primary và suppressed exception

Tạo file **`CloseFailureDemo.java`**:

```java
public class CloseFailureDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("close failed");
        }
    }

    public static void main(String[] args) {
        Resource resource = new Resource();

        try (resource) {
            throw new IllegalArgumentException("work failed");
        } catch (IllegalArgumentException failure) {
            System.out.println("primary=" + failure.getMessage());
            System.out.println("suppressed="
                    + failure.getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac CloseFailureDemo.java
java CloseFailureDemo
```

`stdout`:

```text
primary=work failed
suppressed=close failed
```

Ví dụ sử dụng resource thuộc sở hữu của scope `main`. Nếu đó là resource do caller khác sở hữu, việc đưa vào TWR sẽ tạo **thêm rủi ro**: không chỉ đóng quá sớm mà còn có thể xuất hiện lỗi đóng tại nơi không có quyền quyết định lifecycle.

### Nếu `close()` có side effect hoặc không idempotent

`AutoCloseable` không bắt buộc mọi implementation của `close()` hoàn toàn idempotent; một số có side effect và có thể ném nếu được gọi lại. Tránh tạo hai wrapper cùng sở hữu delegate hoặc đưa cùng resource vào nhiều scope TWR chồng lấn mà không có hợp đồng cụ thể.

Các API khác nhau có thể có bảo đảm riêng về việc đóng nhiều lần; hãy kiểm tra tài liệu của implementation thay vì áp một giả định cho mọi `AutoCloseable`.

## 14. Quyền sở hữu trong API thiết kế mới

### 14.1. Ghi rõ ai phải đóng trong JavaDoc

Đối với phương thức nhận borrowed stream:

```java
/**
 * Đọc dữ liệu từ stream do caller sở hữu.
 * Phương thức không đóng {@code source}.
 *
 * @param source stream đang mở do caller quản lý
 * @throws java.io.IOException nếu thao tác đọc thất bại
 */
static void decode(java.io.InputStream source)
        throws java.io.IOException {
    int first = source.read();
    System.out.println(first);
}
```

Đây là **mảnh phương thức minh họa**. Mục đích chính là mô tả **không đóng tham số** một cách tường minh. JavaDoc `@throws` giải thích loại lỗi, còn văn bản mô tả phải nói rõ trách nhiệm resource.

Đối với factory trả resource:

```java
/**
 * Mở một reader mới.
 * Caller nhận quyền sở hữu và phải đóng reader được trả về.
 */
static java.io.BufferedReader openDocument(java.nio.file.Path path)
        throws java.io.IOException {
    return java.nio.file.Files.newBufferedReader(path);
}
```

Đây cũng là mảnh phương thức. Trên đường thành công, reader được trả khi còn mở; trách nhiệm đóng thuộc caller.

### 14.2. Đặt tên API thể hiện ý định, nhưng không chỉ dựa vào tên

Tên như `readBorrowed`, `openOwned`, `withReader` hoặc `executeInTransaction` có thể gợi ý hợp đồng. Nhưng tên không thay thế JavaDoc và quy tắc lifecycle của framework. Khi API nhận callback để dùng resource rồi tự đóng, nó phải bảo đảm callback không lưu resource để sử dụng sau scope.

### 14.3. Không lưu resource mượn lâu hơn thời gian được phép mượn

Nếu helper nhận resource borrowed và ghi lại vào field để dùng bất đồng bộ sau khi caller rời scope, helper có thể truy cập resource đã bị owner đóng. Điều này sai ngay cả khi helper **không hề gọi `close()`**. Quyền sở hữu liên quan không chỉ “ai đóng” mà cả **thời gian được phép sử dụng**.

### 14.4. Thread-safety là yêu cầu riêng

Borrowed/owned không tự cho biết resource có dùng được đồng thời từ nhiều thread không. Với một stream, JDBC connection hay session, cần tuân thủ hợp đồng thread-safety của API. Không dùng “caller giữ ownership” để suy ra được chia sẻ resource vô hạn giữa các luồng.

## 15. Bảng tình huống quyết định

| Tình huống | Có nên dùng `try-with-resources` trong phương thức này? | Lý do |
| --- | --- | --- |
| Tự `Files.newInputStream(path)` để đọc một lần | **Có** | Scope mở và sở hữu resource |
| Nhận `InputStream` do caller giữ quyền đóng | **Không** trên chính stream đó | Caller cần tiếp tục quản lý |
| Nhận `Reader` và parse một phần dữ liệu, không chuyển quyền | **Không** trên reader nhận vào | Đóng có thể làm caller mất resource |
| Factory mới mở stream và trả cho caller | **Không** đóng trên đường trả về thành công | Quyền sở hữu được chuyển cho caller |
| Caller nhận stream mới từ factory có hợp đồng caller đóng | **Có** | Caller chịu trách nhiệm đóng |
| Mượn `System.in` để đọc tạm | **Không** trong helper | Stream dùng chung toàn tiến trình |
| Dùng wrapper đóng kéo theo borrowed stream | **Chỉ khi có quyền đóng delegate** | Closing cascade không phụ thuộc tên biến |
| Caller trực tiếp checkout connection từ pool theo hợp đồng phải trả | **Thường có**, ở phạm vi công việc phù hợp | `close()` thường trả handle về pool |
| Hàm nhận connection thuộc transaction của caller | **Không** trên connection đó | Transaction owner quyết định lifecycle |
| Tạo statement và result set nội bộ trên connection mượn | **Có** trên statement/result set | Các resource con có phạm vi của truy vấn |
| API được container giao một response stream | **Theo hợp đồng container** | Container có thể quản lý close hoặc có quy tắc riêng |
| Resource đã được đóng nhưng biến còn trong scope | Không dùng tiếp trừ khi API cho phép rõ ràng | Scope biến khác lifecycle mở |
| Nhiều resource mới có thể thất bại khi tạo lần lượt | **Ưu tiên header khai báo từ đầu** | Đảm bảo cleanup nếu khởi tạo resource sau thất bại |

Các lựa chọn trong bảng dựa trên **giả định quyền sở hữu đã nêu ở từng hàng**. Chúng không thể thay thế tài liệu riêng của driver, pool, library hoặc framework đang dùng.

## 16. Những sai lầm dễ mắc

**“`AutoCloseable` thì hễ thấy là phải tự gọi `close()` ngay.”** Không. Interface chỉ cho biết cơ chế đóng; việc ai có quyền đóng phải đến từ hợp đồng vòng đời.

**“`try-with-resources` tự phát hiện resource mượn và không đóng.”** Sai. Nếu resource được liệt kê trong header và không null, cơ chế sẽ gọi `close()` theo quy tắc Java, bất kể ai tạo đối tượng.

**“Đóng một wrapper thì delegate vẫn mở vì không nằm trong header.”** Sai với nhiều wrapper: `close()` có thể truyền xuống resource bên dưới.

**“Tạo alias `try (Reader alias = borrowed)` là cách giữ borrowed reader mở.”** Sai. Alias cùng tham chiếu đến một đối tượng; close qua alias có thể đóng chính borrowed reader.

**“Hàm trả stream trong `try-with-resources` vẫn trả stream đang mở.”** Thường sai: khi rời `try` để `return`, resource được đóng trước khi caller nhận kết quả.

**“`System.in` chỉ là một `InputStream` bình thường nên helper đóng cũng không sao.”** Sai về vòng đời dùng chung. Đóng có thể ảnh hưởng toàn bộ tiến trình.

**“Pooled connection tuyệt đối không được gọi `close()`.”** Sai. Khi ứng dụng được pool giao connection với hợp đồng trả về, `close()` có thể là thao tác cần thiết để trả handle về pool.

**“`close()` của JDBC connection chính là `commit()`.”** Sai. Quản lý transaction có semantics riêng; phải dùng API phù hợp và hợp đồng framework.

**“Reader đã mượn thì có thể lưu vào field rồi dùng sau bất cứ lúc nào.”** Sai. Bên mượn phải tuân thủ thời hạn mượn; owner có thể đóng resource khi hết thời hạn.

**“`try (resource)` Java 9 sẽ không đóng vì biến được khai báo bên ngoài.”** Sai. Tính năng Java 9 chỉ làm cú pháp ngắn hơn; resource vẫn được đóng khi thoát scope.

**“Đóng hai lần luôn an toàn.”** Không. Có API cho phép close lặp, có API có side effect hoặc không bảo đảm idempotent.

**“Không dùng TWR cho borrowed stream nghĩa là không cần xử lý ngoại lệ.”** Sai. Checked exception từ `read()` vẫn phải bắt/khai báo; caller vẫn cần cleanup ở scope sở hữu.

**“Sau khi parser đọc xong, caller không thể cần stream nữa.”** Sai. Caller có thể đọc nhiều phần, xử lý giao thức nhiều giai đoạn, retry hoặc quyết định đóng trong scope lớn hơn.

**“Resource mở trước TWR mà bước tạo kế tiếp thất bại thì TWR luôn cleanup được nó.”** Sai. Nếu chưa vào `try`, header chưa quản lý tài nguyên đó.

## 17. Tự kiểm tra

1. **Một hàm nhận `Reader` để đọc và JavaDoc nói caller sở hữu. Có nên `try (reader)` không?** Không; nó sẽ đóng resource của caller.
2. **Từ Java 9, tham số method effectively final có được dùng trong `try (reader)` về cú pháp không?** Có, nhưng phải xét quyền sở hữu trước khi dùng.
3. **Factory tạo và trả `BufferedReader` còn mở, ai đóng?** Caller nếu hợp đồng đã chuyển quyền sở hữu.
4. **Đóng `BufferedReader` bọc `InputStreamReader` có thể đóng `InputStream` gốc không?** Có, do chuỗi close của wrapper/delegate.
5. **Có thể dùng `try-with-resources` để tự đóng `PreparedStatement` nhưng giữ `Connection` mượn mở không?** Có, nếu method sở hữu statement và caller giữ quyền quản lý connection.
6. **Một pooled `Connection` được checkout cho unit of work và phải trả pool, nên đóng hay không?** Theo hợp đồng pool: thường phải gọi `close()` khi xong để trả handle.
7. **Một helper nhận `System.in` có nên tự tạo `Scanner` rồi `try (scanner)` không?** Thường không vì close của scanner có thể đóng `System.in`.
8. **Lỗi xảy ra khi mở resource thứ hai trước khi vào `try (first; second)`, `first` có chắc được đóng không?** Không; scope chưa bắt đầu.
9. **Resource chưa đóng và một helper chỉ mượn nhưng ghi lại để dùng sau khi owner kết thúc scope, hợp lệ không?** Không nếu vượt thời hạn mượn.
10. **Nếu `close()` cũng ném khi thân TWR đã ném lỗi, xem lỗi đóng ở đâu?** Thường ở `getSuppressed()` của lỗi chính.
11. **Việc đổi biến thành `final` có xác lập quyền sở hữu resource không?** Không. `final` ràng buộc gán lại biến, không xác định ai được phép đóng.
12. **Khi nào nên dùng lớp bọc leave-open?** Chỉ khi hợp đồng cần giữ delegate mở và đã phân tích side effect, buffering, flush và quy tắc đọc tiếp; không dùng mặc định.
13. **Đóng một wrapper và dùng lại stream nền sau đó có luôn giữ vị trí đọc như cũ không?** Không. Wrapper có thể đọc trước vào buffer.
14. **Nên tìm nguồn chính xác của trách nhiệm đóng ở đâu?** JavaDoc/API contract, hợp đồng framework/pool và kiến trúc quản lý lifecycle của ứng dụng.

## 18. Tài liệu tham khảo chính thức

- [Java Language Specification 17 — §14.20.3, try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): cơ chế đóng, đường lỗi và suppressed exceptions.
- [Java SE 17 API — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng `close()` và lưu ý về idempotency.
- [Java SE 17 API — Closeable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html): contract đóng tài nguyên I/O.
- [Java SE 17 API — BufferedReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html) và [InputStreamReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html): lớp bọc reader và hành vi đóng.
- [Java SE 17 API — Scanner](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Scanner.html): đóng scanner và nguồn đầu vào liên quan.
- [Java SE 17 API — Connection](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): lifecycle và transaction của JDBC connection.
- [Java SE 17 API — Throwable.getSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getSuppressed()): đọc suppressed exceptions do đóng resource.
- [Java Language Specification 17 — §4.12.4 final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): biến final/effectively final dùng trong resource access.

**Nguyên tắc trọng tâm:** `try-with-resources` rất hữu ích khi **scope hiện tại có quyền và nghĩa vụ đóng** tài nguyên. Không đặt tài nguyên chỉ **mượn** hoặc do thành phần khác quản lý vào TWR một cách máy móc. Hãy làm rõ người sở hữu, thời hạn sử dụng, closing cascade của wrapper, semantics của pool/framework và cả đường lỗi khi bàn giao resource; từ đó đặt việc tự động đóng ở **đúng ranh giới vòng đời**.
