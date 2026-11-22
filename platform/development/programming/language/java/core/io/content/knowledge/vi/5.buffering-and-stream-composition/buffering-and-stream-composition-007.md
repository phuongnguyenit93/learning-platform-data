# `close()` lớp ngoài cùng và việc đóng tài nguyên bên dưới trong Java I/O

Trong Java I/O, các lớp thường được **ghép thành chuỗi (wrapper/decorator)** để bổ sung chức năng. Ví dụ, một `BufferedReader` bổ sung đọc có bộ đệm cho `InputStreamReader`, còn `InputStreamReader` giải mã byte lấy từ `FileInputStream` thành ký tự:

```text
Mã ứng dụng
    |
    v
BufferedReader                 <- lớp ngoài cùng, ứng dụng gọi read()/close()
    |
    v
InputStreamReader              <- giải mã byte thành ký tự
    |
    v
FileInputStream                <- nắm giữ tài nguyên file/descriptor
    |
    v
Tệp trên hệ điều hành
```

**Quy tắc thực hành:** Với các wrapper I/O chuẩn đóng tầng bên dưới theo hợp đồng của chúng, hãy **đóng lớp ngoài cùng mà ứng dụng sở hữu**. Lệnh `close()` được chuyển xuống các tầng được bọc, giúp giải phóng tài nguyên gốc; đối với luồng đầu ra, việc đóng còn hoàn tất/đẩy dữ liệu đang nằm trong bộ đệm. Tuy nhiên, **không được mặc định mọi wrapper tự viết hoặc mọi API đều sở hữu tài nguyên được truyền vào**. Phải xét hợp đồng ownership và hành vi `close()` của lớp cụ thể.

Bài này phân biệt rõ: cơ chế đóng lan truyền, trình tự đóng, `flush()` so với `close()`, ranh giới sở hữu tài nguyên, xử lý lỗi khi đóng và cách kiểm chứng bằng Java 17+.

## 1. Vì sao các luồng được bọc nhiều tầng?

Các wrapper chia trách nhiệm, thay vì nhét mọi chức năng vào một lớp:

| Tầng | Vai trò | Có thể sở hữu / bọc |
| --- | --- | --- |
| `FileInputStream`, `FileOutputStream` | Đọc/ghi byte với tệp | Handle/descriptor của tệp |
| `InputStreamReader`, `OutputStreamWriter` | Chuyển giữa byte và ký tự theo `Charset` | `InputStream` / `OutputStream` |
| `BufferedInputStream`, `BufferedOutputStream` | Giảm các lần I/O tầng dưới nhờ bộ đệm byte | Luồng byte được bọc |
| `BufferedReader`, `BufferedWriter` | Bộ đệm ký tự; `BufferedReader` hỗ trợ `readLine()` | `Reader` / `Writer` |
| `DataInputStream`, `DataOutputStream` | Đọc/ghi các kiểu nguyên thủy và định dạng nhị phân | Luồng byte được bọc |
| `GZIPInputStream`, `GZIPOutputStream` | Giải nén/nén dữ liệu GZIP | Luồng byte được bọc |

Ví dụ mở file ở ba tầng:

```java
InputStream raw = Files.newInputStream(path);
Reader decoder = new InputStreamReader(raw, StandardCharsets.UTF_8);
BufferedReader reader = new BufferedReader(decoder);
```

Đây là **mã minh họa**: `path`, các import và cách xử lý exception chưa được trình bày thành chương trình độc lập. Một lần `reader.readLine()` có thể đọc qua cả ba tầng. Việc đóng lớp ngoài cùng `reader.close()` cũng đi theo chuỗi đóng các tầng **đối với các lớp chuẩn này**. Để tránh bỏ sót khi có exception, hãy dùng `try-with-resources` ngay khi tạo wrapper.

## 2. `close()` của lớp ngoài cùng đóng những gì?

Với nhiều wrapper chuẩn của `java.io`, phương thức `close()` **ủy quyền (delegate)** đến luồng/reader/writer được bọc. Vì vậy:

```text
reader.close()
    -> BufferedReader đóng Reader bên dưới
        -> InputStreamReader đóng InputStream bên dưới
            -> FileInputStream giải phóng file descriptor
```

Tương tự, luồng ghi có thể tạo chuỗi:

```text
BufferedWriter.close()
    -> đẩy ký tự còn trong bộ đệm
    -> OutputStreamWriter.close()
        -> hoàn tất trạng thái bộ mã hóa và đóng OutputStream
            -> FileOutputStream.close()
                -> giải phóng tài nguyên file
```

**Lưu ý về thuật ngữ:** Trong chuỗi trên, gọi `close()` ở wrapper ngoài cùng và đi xuống các tầng là hành vi đóng **lan truyền theo quan hệ bọc**, không phải cơ chế đệ quy đặc biệt của JVM. Mỗi lớp thực hiện logic `close()` của chính nó theo hợp đồng. Nếu sử dụng wrapper tự viết, bạn phải kiểm tra xem implementation có chuyển tiếp `close()` hay không.

### Ví dụ 1 — quan sát trực tiếp quá trình đóng tầng dưới

Ví dụ sau dùng `FilterInputStream` để theo dõi thời điểm nguồn bên dưới được yêu cầu đóng. Nguồn dữ liệu ở đây là `ByteArrayInputStream` để có kết quả lặp lại chính xác; lớp `TrackingInputStream` quan sát việc gọi `close()`, chứ không dựa vào việc tệp có bị khóa hay không.

```java
// CloseChainDemo.java
import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class CloseChainDemo {
    static final class TrackingInputStream extends FilterInputStream {
        boolean closed;

        TrackingInputStream(InputStream source) {
            super(source);
        }

        @Override
        public void close() throws IOException {
            super.close();
            closed = true;
            System.out.println("closed: underlying input");
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] sourceBytes = "Xin chào".getBytes(StandardCharsets.UTF_8);
        TrackingInputStream source = new TrackingInputStream(
                new ByteArrayInputStream(sourceBytes));

        try (BufferedReader outer = new BufferedReader(
                new InputStreamReader(source, StandardCharsets.UTF_8))) {
            System.out.println("read: " + outer.readLine());
        }

        System.out.println("underlying.closed=" + source.closed);
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 CloseChainDemo.java
java CloseChainDemo
```

Kết quả:

```text
read: Xin chào
closed: underlying input
underlying.closed=true
```

Vì `try-with-resources` quản lý **chính `BufferedReader` ngoài cùng**, khi thoát khối `try`, Java gọi `outer.close()`. `BufferedReader` đóng `InputStreamReader`, rồi `InputStreamReader` đóng `TrackingInputStream`. Dòng `closed: underlying input` xác nhận yêu cầu đóng đã tới tầng dưới.

`ByteArrayInputStream.close()` vốn không cần giải phóng tài nguyên hệ điều hành và không cấm đọc tiếp; ở ví dụ này cờ `closed` đo **việc gọi close**, không khẳng định mọi loại stream trở nên không đọc được sau khi đóng. Với `FileInputStream`, hành vi đóng còn giải phóng handle file.

## 3. `try-with-resources`: cách đóng wrapper đúng và an toàn

Cách sử dụng nên ưu tiên cho một file do chương trình mở:

```java
Path path = Path.of("data.txt");
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(
                Files.newInputStream(path), StandardCharsets.UTF_8))) {
    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
```

Đây là **đoạn mã minh họa**; cần các import tương ứng và một tệp `data.txt` tồn tại. Nguyên tắc quan trọng: một resource là `BufferedReader` ngoài cùng đã đủ để đóng chuỗi chuẩn của ví dụ. Không cần gọi thủ công `reader.close()` trong `finally`.

`try-with-resources` bảo đảm lệnh `close()` xảy ra khi rời khối, kể cả khi:

- hoàn thành bình thường;
- gặp `return` hoặc `break`;
- code bên trong ném exception.

Dùng một tầng ngoài cùng có ý nghĩa vì chính nó biết việc hoàn tất dữ liệu đang giữ và cách đóng tầng dưới. Nếu chỉ đóng `FileOutputStream` thô trước khi bộ đệm wrapper được đẩy xuống, dữ liệu đang nằm ở wrapper có thể chưa được ghi và những lệnh ghi tiếp theo sẽ lỗi.

**Không bắt buộc khai báo tất cả tầng là tài nguyên `try-with-resources`.** Ví dụ này thường không cần thiết:

```java
try (InputStream raw = Files.newInputStream(path);
     BufferedInputStream buffered = new BufferedInputStream(raw)) {
    // ...
}
```

Khi kết thúc khối, Java đóng `buffered` trước, rồi đóng `raw` thêm lần nữa vì cả hai đều có khai báo resource. Những lớp chuẩn thường chịu được việc đóng lặp, nhưng không phải mọi resource tùy biến đều có hợp đồng `close()` idempotent. Nếu đã chọn wrapper chuẩn ngoài cùng làm owner, thường chỉ khai báo wrapper này.

### Các resource *độc lập* được đóng theo thứ tự ngược

Khác với chuỗi wrapper, khi khai báo nhiều tài nguyên thật sự **độc lập** trong một `try`, Java tự đóng theo thứ tự từ phải sang trái (ngược thứ tự khai báo). Ví dụ chạy độc lập:

```java
// CloseOrderDemo.java
public class CloseOrderDemo {
    static final class NamedResource implements AutoCloseable {
        private final String name;

        NamedResource(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        try (NamedResource first = new NamedResource("A");
             NamedResource second = new NamedResource("B")) {
            System.out.println("work");
        }
    }
}
```

```bash
javac CloseOrderDemo.java
java CloseOrderDemo
```

Kết quả:

```text
open A
open B
work
close B
close A
```

Đây là **thứ tự đóng những biến resource khai báo trong `try`**; còn việc đóng lan truyền của chuỗi wrapper xảy ra bên trong phương thức `close()` của từng wrapper.

## 4. `flush()` khác `close()`: phần dữ liệu còn trong bộ đệm

Với luồng đầu ra, cần phân biệt hai thao tác:

- **`flush()`** yêu cầu đẩy phần dữ liệu đang đệm của wrapper xuống tầng bên dưới. Luồng **vẫn mở** và còn được phép ghi tiếp.
- **`close()`** hoàn tất việc sử dụng resource. Wrapper đầu ra thông dụng sẽ thực hiện công việc cần thiết để đẩy dữ liệu còn đệm rồi đóng tầng được bọc.

`flush()` không đồng nghĩa với dữ liệu đã được ghi **bền vững trên thiết bị lưu trữ**; dữ liệu có thể vẫn còn trong cache của hệ điều hành hoặc phần cứng. Nếu cần yêu cầu độ bền với tệp, tìm hiểu `FileChannel.force(...)` và những bảo đảm cụ thể của hệ thống tệp.

### Ví dụ 2 — bộ đệm chưa ghi ra nguồn bên dưới cho đến khi flush/close

```java
// BufferedCloseDemo.java
import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class BufferedCloseDemo {
    static final class TrackingOutputStream extends FilterOutputStream {
        boolean closed;

        TrackingOutputStream(OutputStream destination) {
            super(destination);
        }

        @Override
        public void close() throws IOException {
            super.close();
            closed = true;
            System.out.println("closed: underlying output");
        }
    }

    public static void main(String[] args) throws Exception {
        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        TrackingOutputStream underlying = new TrackingOutputStream(sink);

        try (BufferedOutputStream outer =
                     new BufferedOutputStream(underlying)) {
            outer.write("ABC".getBytes(StandardCharsets.UTF_8));
            System.out.println("before close bytes=" + sink.size());
        }

        System.out.println("after close bytes=" + sink.size());
        System.out.println("underlying.closed=" + underlying.closed);
        System.out.println("text=" + sink.toString(StandardCharsets.UTF_8));
    }
}
```

```bash
javac BufferedCloseDemo.java
java BufferedCloseDemo
```

Kết quả:

```text
before close bytes=0
closed: underlying output
after close bytes=3
underlying.closed=true
text=ABC
```

Ba byte `ABC` đủ nhỏ nên nằm trong bộ đệm mặc định của `BufferedOutputStream`. Việc đóng `outer` khiến dữ liệu được chuyển xuống `TrackingOutputStream`/`ByteArrayOutputStream` và yêu cầu đóng cả tầng dưới. Vì `ByteArrayOutputStream` hoạt động trong RAM nên `close()` của chính nó không làm mất dữ liệu; trạng thái `underlying.closed` do lớp theo dõi ghi nhận.

Nếu thay bên trong `try` bằng:

```java
outer.write("ABC".getBytes(StandardCharsets.UTF_8));
outer.flush();
System.out.println(sink.size()); // 3
```

đây là **đoạn minh họa thay thế**, `flush()` làm dữ liệu xuất hiện trong `sink` ngay trong khối, nhưng không đóng luồng. Khi muốn ghi tiếp sau `flush()` thì vẫn làm được; sau `close()` không nên sử dụng tiếp wrapper.

**Không đóng tầng dưới trước tầng ngoài:** Ví dụ nếu gọi `underlying.close()` trước rồi mới `outer.close()`, các byte vẫn ở `BufferedOutputStream` có thể phải đẩy qua một tầng đã đóng; đối với nguồn thực như tệp/socket có thể gây mất dữ liệu hoặc lỗi. Hãy để wrapper đầu ra ngoài cùng thực hiện đóng theo thứ tự hợp lệ.

## 5. Những wrapper có công việc hoàn tất khi `close()`

Một số wrapper không chỉ đệm mà còn **định dạng dữ liệu**:

- `GZIPOutputStream` phải hoàn tất cấu trúc nén; `close()` hoàn tất và đóng luồng bên dưới. Nếu muốn hoàn tất GZIP nhưng **giữ luồng bên dưới mở** trong thiết kế có chủ đích, xem `finish()`; `flush()` thông thường không thay cho hoàn tất định dạng.
- `ZipOutputStream` cần ghi các cấu trúc kết thúc ZIP (chẳng hạn central directory) để tệp ZIP hoàn chỉnh. `close()` đóng cả archive và luồng bên dưới; `finish()` hoàn tất archive mà chưa đóng luồng bên dưới.
- `OutputStreamWriter` chuyển ký tự sang byte bằng `CharsetEncoder`. Dữ liệu/ trạng thái bộ mã hóa có thể cần được xử lý khi `flush()` hoặc `close()`, nên không thể cho rằng chỉ ghi vào wrapper là nguồn dưới đã nhận đầy đủ.
- `BufferedWriter` và `BufferedOutputStream` giữ dữ liệu ở RAM để giảm số thao tác ở tầng dưới; đóng đúng wrapper giúp tránh bỏ sót phần còn đệm.

**Phân biệt `finish()` và `close()` khi API có hỗ trợ:** `finish()` hoàn tất định dạng của một luồng đặc thù; `close()` còn giải phóng/đóng đối tượng và thường cả luồng bên dưới. Không phải `OutputStream` nào cũng có `finish()`.

Đừng thay thế `close()` bằng `flush()` ở mọi nơi. Tài nguyên tệp/socket vẫn phải được đóng bởi owner; một định dạng nén có thể chưa hoàn chỉnh nếu chưa chạy logic kết thúc.

## 6. Ai thực sự sở hữu luồng bên dưới?

Điều kiện quan trọng nhất khi quyết định đóng tầng ngoài là **quyền sở hữu tài nguyên (resource ownership)**:

| Tình huống | Ai nên đóng? | Lý do |
| --- | --- | --- |
| Phương thức tự mở file và tạo wrapper trên file ấy | Phương thức, thông qua wrapper ngoài cùng | Đã tạo và sở hữu toàn bộ chuỗi. |
| Hàm nhận `InputStream`/`OutputStream` từ caller và chỉ đọc/ghi một phần | Thường là caller, trừ khi hợp đồng chuyển quyền sở hữu rõ ràng | Hàm không nên làm hỏng nguồn dùng chung. |
| `System.in`, `System.out`, `System.err` | Vòng đời ứng dụng/môi trường quản lý | Đóng wrapper bọc chúng có thể đóng standard stream mà nơi khác còn cần. |
| Một socket có nhiều thành phần dùng chung | Thành phần được chỉ định owner của socket | Đóng stream do socket cung cấp có thể đóng kết nối, ảnh hưởng thành phần khác. |
| Wrapper tùy biến có `close()` override đặc biệt | Theo hợp đồng của wrapper đó | Không được suy rằng `close()` luôn delegate. |

Quy tắc thiết kế API thực tiễn:

- **Tạo ở đâu, quản lý vòng đời ở đó**, trừ khi tài liệu hoặc giao diện chuyển giao ownership.
- Ghi rõ trong Javadoc/hợp đồng hàm rằng `OutputStream`/`Reader` truyền vào sẽ được đóng hay vẫn thuộc caller.
- Nếu hàm chỉ *mượn* stream, nó có thể `flush()` khi cần đẩy dữ liệu, nhưng thường **không `close()`** nó.
- Nếu hàm *nhận chuyển quyền sở hữu*, hãy đảm bảo đóng khi hoàn thành hoặc gặp lỗi, tốt nhất dùng `try-with-resources`.

Ví dụ hàm chỉ mượn `OutputStream`:

```java
// Đoạn minh họa, không tự chạy nếu thiếu import/lớp bao.
static void sendMessage(OutputStream borrowed, String text)
        throws IOException {
    borrowed.write(text.getBytes(StandardCharsets.UTF_8));
    // Không gọi borrowed.close(): caller vẫn sở hữu stream.
}
```

Đặc biệt tránh mẫu `try (BufferedWriter writer = new BufferedWriter(new OutputStreamWriter(System.out)))` trong hàm chỉ in thử ra console: đóng `writer` sẽ lan xuống `System.out` và có thể làm các lệnh in sau không còn hoạt động. Với `Scanner` bọc `System.in`, `scanner.close()` cũng có thể đóng nguồn nhập chuẩn đang được chia sẻ.

### Khi cần wrapper nhưng không được đóng nguồn của caller

Có ba cách tùy kiến trúc:

1. Caller chủ động tạo wrapper và giữ quyền kiểm soát vòng đời của **cả wrapper lẫn nguồn**; hàm chỉ nhận wrapper để sử dụng.
2. Hàm mượn nguồn nhưng tự tạo bộ đệm tạm; phải `flush()` trước khi trả lại nếu có dữ liệu đầu ra và không đóng wrapper có cơ chế close lan truyền. Cần xác định rõ lỗi và trạng thái đệm còn tồn tại.
3. Dùng một wrapper **close-shield / non-closing wrapper** khi tầng ngoài cần được đóng để hoàn tất nội dung nhưng tầng dưới thuộc caller. Cách này phải được thiết kế và kiểm thử riêng; không phải mặc định của `BufferedOutputStream`.

Ví dụ minh họa về close-shield cho đầu ra (mã nằm trong lớp Java phù hợp, có import `FilterOutputStream`, `OutputStream`, `IOException`):

```java
static final class NonClosingOutputStream extends FilterOutputStream {
    NonClosingOutputStream(OutputStream delegate) {
        super(delegate);
    }

    @Override
    public void close() throws IOException {
        flush(); // Không gọi super.close(), do đó giữ delegate mở.
    }
}
```

Nếu tạo `new BufferedOutputStream(new NonClosingOutputStream(borrowed))`, `close()` của `BufferedOutputStream` sẽ đẩy dữ liệu và đóng wrapper shield; shield chỉ flush, **không gọi `borrowed.close()`**. Đây là ví dụ về chính sách sở hữu, không thay thế việc kiểm tra những wrapper phía trên có cần `close()` để hoàn tất định dạng hoặc những luồng có trạng thái phức tạp.

## 7. Exception khi đọc/ghi và cả khi đóng tài nguyên

`close()` có thể ném `IOException`. Lỗi có thể xuất hiện ở lúc đẩy phần buffer còn lại xuống file, hoàn tất mã hóa/nén, hoặc đóng tài nguyên. Vì vậy exception liên quan đến `close()` **không phải chuyện chỉ xảy ra sau khi công việc đã thành công**.

Với `try-with-resources`:

- Nếu thân khối `try` thành công nhưng `close()` thất bại, exception từ `close()` được truyền ra.
- Nếu thân `try` đã ném exception và `close()` cũng ném, exception của thân được giữ là **primary exception**, còn exception từ `close()` được đính vào mảng **suppressed exceptions**.
- Nếu nhiều resource được khai báo, chúng được đóng theo thứ tự ngược; exception trong quá trình đóng những resource tiếp theo có thể được giữ dưới dạng suppressed.

Ví dụ Java 17+ độc lập:

```java
// SuppressedCloseDemo.java
import java.io.IOException;

public class SuppressedCloseDemo {
    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        try (FailingResource resource = new FailingResource()) {
            throw new IOException("body failed");
        } catch (IOException ex) {
            System.out.println("primary=" + ex.getMessage());
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("suppressed=" + suppressed.getMessage());
            }
        }
    }
}
```

```bash
javac SuppressedCloseDemo.java
java SuppressedCloseDemo
```

Kết quả:

```text
primary=body failed
suppressed=close failed
```

Khi điều tra sự cố mất dữ liệu hay file bị hỏng, đừng chỉ đọc `ex.getMessage()` của lỗi đầu tiên. Có thể phải xem `getSuppressed()` để tìm lỗi đóng/flushing tài nguyên. Cũng đừng dùng `finally { stream.close(); }` một cách ngây thơ nếu việc đóng có nguy cơ **che mất exception chính** của thân khối; `try-with-resources` có quy tắc suppression rõ ràng.

Một điểm giới hạn: dù nhiều wrapper chuẩn truyền `close()` xuống bên dưới, **không thể kết luận mọi tài nguyên chắc chắn đã đóng thành công khi `close()` ném lỗi**. Tình trạng cụ thể phụ thuộc implementation, hệ điều hành và lỗi; chính vì vậy cần giữ ngoại lệ và thiết kế khôi phục phù hợp.

## 8. Một số trường hợp khác dễ hiểu nhầm

### `close()` thường khác với EOF

Khi đọc dữ liệu, EOF cho biết nguồn không còn ký tự/byte trong luồng. `close()` là hành động giải phóng tài nguyên do ứng dụng quản lý, có thể xảy ra **trước EOF** nếu chỉ cần đọc một phần. Đọc tiếp sau `close()` không phải cách kiểm tra EOF hợp lệ; nhiều stream sẽ ném `IOException`.

### Không phải mọi đối tượng đóng rồi đều “không thể dùng” như nhau

`ByteArrayInputStream` và `ByteArrayOutputStream` hoạt động trên bộ nhớ, nên việc `close()` của chúng **không có hiệu lực** theo hợp đồng. Một `FileInputStream` đã đóng thì các thao tác đọc tiếp thường ném lỗi. Không suy từ một lớp trong bộ nhớ ra hành vi của tài nguyên hệ điều hành.

### `PrintWriter`/`PrintStream` có khác biệt về báo lỗi

`PrintWriter` thường **không ném `IOException` từ nhiều phương thức ghi**; có thể kiểm tra trạng thái lỗi với `checkError()`. Đóng `PrintWriter` vẫn có thể đóng writer/stream bên dưới, nhưng việc không thấy exception từ một lời gọi ghi không có nghĩa dữ liệu đã được ghi thành công. Với logic cần báo lỗi I/O rõ ràng, cân nhắc `BufferedWriter`/`Writer` và bắt `IOException`.

### Tầng nén hoặc định dạng có thể cần hoàn tất đúng cách

Nếu chỉ đóng `FileOutputStream` bên dưới một `GZIPOutputStream` hoặc `ZipOutputStream` đang mở, cấu trúc đầu ra có thể thiếu phần kết thúc. Luôn để owner đóng wrapper định dạng ngoài cùng hoặc gọi `finish()` đúng hợp đồng rồi đóng tầng do mình sở hữu.

### Không suy diễn cho mọi Java API

Lớp chuẩn `FilterInputStream`, `FilterOutputStream`, `BufferedReader`, `BufferedWriter`, `InputStreamReader`, `OutputStreamWriter` thường có close propagation theo thiết kế. Nhưng một `Reader` tùy biến, bộ đệm do thư viện ngoài quản lý, stream trong servlet, hay API tự động quản lý vòng đời có thể có hợp đồng khác. Khi không chắc, xem tài liệu `close()` của **chính implementation**.

## 9. Cách chọn thiết kế đóng tài nguyên

Khi tạo chuỗi I/O, trả lời bốn câu hỏi trước:

1. **Nguồn gốc tài nguyên:** Ai mở file, socket hoặc kết nối?
2. **Chủ sở hữu vòng đời:** Ai có trách nhiệm đóng?
3. **Wrapper ngoài cùng cần hoàn tất gì:** flush bộ đệm, xử lý charset, `finish()` định dạng nén?
4. **Khi có lỗi:** `try-with-resources` có giữ được exception gốc và lỗi khi đóng không?

Một sơ đồ quyết định:

```text
Tôi tự tạo nguồn và sở hữu nó?
  |
  +-- Có --> Bọc theo nhu cầu, try-with-resources trên lớp ngoài cùng.
  |           Để close() lan xuống qua các wrapper chuẩn.
  |
  +-- Không --> Xác nhận hợp đồng có chuyển ownership không.
                |
                +-- Có --> Quản lý close() theo hợp đồng đã nhận.
                |
                +-- Không --> Không close() nguồn dùng chung.
                              Nếu tạo wrapper, thiết kế flush/shield
                              và bàn giao vòng đời một cách rõ ràng.
```

Với các luồng chuẩn, mẫu ngắn gọn thường đúng nhất cho *nguồn do chính hàm tạo*:

```java
try (BufferedWriter writer = Files.newBufferedWriter(
        path, StandardCharsets.UTF_8)) {
    writer.write("Dữ liệu cần lưu");
}
```

Đoạn minh họa này giả định `path` đã được xác định. `Files.newBufferedWriter` sở hữu cơ chế mở tệp và trả wrapper có bộ đệm. Kết thúc khối sẽ đóng writer, xử lý phần buffer còn lại và giải phóng tài nguyên tệp. Không cần `writer.flush()` ngay trước `close()` chỉ vì muốn chắc chắn; nếu cần quan sát dữ liệu khi luồng **vẫn mở**, đó mới là lý do gọi `flush()`.

## 10. Câu hỏi tự kiểm tra

**1.** `BufferedReader` bọc `InputStreamReader` bọc `FileInputStream`. Nếu chính hàm đã mở file, nên đóng gì?

**Đáp án:** Đóng `BufferedReader` ngoài cùng bằng `try-with-resources`; các wrapper chuẩn sẽ chuyển tiếp việc đóng xuống tầng file.

**2.** Việc đóng `FileOutputStream` bên dưới trước khi đóng `BufferedOutputStream` có an toàn không?

**Đáp án:** Không nên. Buffer phía ngoài có thể còn byte chưa chuyển xuống nguồn. Hãy đóng wrapper ngoài cùng để flush và đóng theo thứ tự.

**3.** `flush()` có thay cho `close()` không?

**Đáp án:** Không. `flush()` chuyển dữ liệu còn đệm xuống dưới và vẫn để stream mở; `close()` kết thúc vòng đời, và wrapper định dạng có thể phải ghi thêm phần kết thúc.

**4.** Một hàm nhận `OutputStream` của caller, dùng xong có tự động đóng không?

**Đáp án:** Chỉ khi hợp đồng ghi rõ caller chuyển ownership. Mặc định thiết kế nên để caller quản lý vòng đời của nguồn đã truyền vào.

**5.** `try (A a=...; B b=...)` đóng tài nguyên theo thứ tự nào?

**Đáp án:** `b` trước, `a` sau. Đây là thứ tự giữa các **resource khai báo**, không phải thay thế close propagation của wrapper.

**6.** Nếu thân `try-with-resources` ném lỗi và `close()` ném lỗi khác, tìm lỗi đóng ở đâu?

**Đáp án:** Thường trong `primaryException.getSuppressed()`. Đừng bỏ qua các suppressed exceptions khi chẩn đoán.

**7.** Đóng wrapper bọc `System.out` có thể ảnh hưởng phần khác của ứng dụng không?

**Đáp án:** Có. Các standard stream là tài nguyên dùng chung; tránh để helper đóng chúng nếu helper không sở hữu.

**8.** `ByteArrayOutputStream.close()` không ngăn đọc lại dữ liệu; vậy `FileOutputStream.close()` cũng thế?

**Đáp án:** Không. `ByteArrayOutputStream` đặc biệt vì không giữ tài nguyên I/O hệ điều hành; không lấy nó làm bằng chứng cho file/socket stream.

**Ghi nhớ:** Khi **sở hữu cả chuỗi wrapper I/O chuẩn**, đóng **wrapper ngoài cùng** là cách để dữ liệu/định dạng hoàn tất và tài nguyên bên dưới được đóng. Khi chỉ **mượn nguồn**, quyền quyết định `close()` thuộc owner; phải ghi rõ hợp đồng và xử lý `flush()`/close-shield nếu cần.
