# Quyền đóng luồng vào và luồng ra: ai sở hữu và ai chịu trách nhiệm?

Trong Java, `InputStream` và `OutputStream` thường đại diện cho tài nguyên cần được giải phóng như file, socket hoặc pipe. Gọi `close()` kết thúc việc sử dụng luồng theo hợp đồng của implementation và có thể giải phóng tài nguyên hệ thống. Khi nhiều phương thức cùng sử dụng một luồng, cần xác định rõ phương thức nào có trách nhiệm đóng nó.

Java không có cơ chế ownership trong hệ thống kiểu để tự ngăn một phương thức đóng luồng do nơi khác mở. Trách nhiệm này được xác định bằng hợp đồng API: nơi tạo và sở hữu tài nguyên thường đóng nó; nơi chỉ nhận một luồng để xử lý thường mượn luồng và để bên gọi quyết định thời điểm đóng, trừ khi tài liệu phương thức nói rõ quyền sở hữu được chuyển giao.

## 1. `close()` làm gì?

`InputStream` và `OutputStream` đều triển khai `Closeable` và `AutoCloseable`. Vì vậy, chúng có thể được quản lý bằng `try-with-resources`. `close()` thường giải phóng tài nguyên gắn với luồng, chẳng hạn file descriptor hoặc kết nối. Sau khi đóng, các thao tác đọc/ghi tiếp theo thường không còn hợp lệ theo hợp đồng của implementation và có thể ném `IOException`.

Đóng luồng vào và luồng ra là hai thao tác riêng. Với file, chương trình có thể mở một input stream và một output stream độc lập rồi phải đóng cả hai. Với một số loại tài nguyên như socket, stream được lấy từ socket có quan hệ vòng đời với socket; đóng stream có thể đóng luôn socket liên quan. Hãy đọc tài liệu của API tạo ra stream để hiểu chính xác phạm vi ảnh hưởng của `close()`.

`close()` không đồng nghĩa với `flush()`. `flush()` yêu cầu dữ liệu đang đệm ở đầu ra được đẩy xuống tầng bên dưới, còn `close()` kết thúc việc sử dụng tài nguyên. Các lớp đệm như `BufferedOutputStream` và `BufferedWriter` flush phần dữ liệu còn lại khi đóng. Nếu cần dữ liệu được đẩy đi trước khi tiếp tục dùng luồng, hãy gọi `flush()` theo hợp đồng của ứng dụng; việc flush không thay thế trách nhiệm đóng tài nguyên.

## 2. Quy tắc ownership: ai mở thì người đó đóng

Có thể áp dụng các quy tắc thực hành sau:

1. **Phương thức tự mở tài nguyên:** phương thức đó sở hữu tài nguyên và phải đóng nó, thường bằng `try-with-resources` ngay trong phạm vi mở.
2. **Phương thức nhận stream do caller truyền vào:** mặc định phương thức chỉ mượn stream. Nó đọc/ghi theo nhiệm vụ được giao nhưng không tự đóng stream; caller vẫn sở hữu và chịu trách nhiệm đóng.
3. **Phương thức trả về một stream mới mở:** caller nhận quyền quản lý vòng đời và phải đóng stream sau khi dùng.
4. **Phương thức nhận quyền sở hữu theo thỏa thuận riêng:** nếu API chủ ý tiếp nhận ownership và tự đóng stream, điều đó phải được ghi rõ trong tài liệu phương thức. Caller không tiếp tục sử dụng stream sau khi chuyển giao.

Đây là quy ước thiết kế API, không phải quyền được trình biên dịch kiểm tra. Tên phương thức, Javadoc và tài liệu cần nói rõ phương thức có đóng stream được truyền vào hay không. Không nên để caller phải đoán.

## 3. Phương thức mượn stream không nên tự đóng

Ví dụ một hàm sao chép dữ liệu từ input sang output. Hai stream được caller truyền vào, vì vậy hàm chỉ thực hiện đọc và ghi:

```java
static void copy(InputStream input, OutputStream output) throws IOException {
    byte[] buffer = new byte[8192];
    int count;
    while ((count = input.read(buffer)) != -1) {
        output.write(buffer, 0, count);
    }
}
```

Hàm `copy` không mở stream và cũng không đóng chúng. Caller có thể tiếp tục đọc từ input hoặc ghi thêm vào output sau khi `copy` kết thúc. Nếu hàm đặt các stream được truyền vào trong `try-with-resources`, nó sẽ đóng tài nguyên mà caller đang sở hữu và có thể làm hỏng những thao tác tiếp theo.

Cách gọi phù hợp khi caller mở cả hai file:

```java
try (InputStream input = Files.newInputStream(source);
     OutputStream output = Files.newOutputStream(target)) {
    copy(input, output);
}
```

Caller mở hai stream và cũng đóng cả hai. Khi khối `try` kết thúc, Java đóng tài nguyên theo thứ tự ngược với thứ tự khai báo: `output` được đóng trước, sau đó `input`. Nếu `copy` ném exception, cả hai stream vẫn được đóng.

Nếu `copy` cần flush output trước khi trả về, hãy ghi rõ điều đó trong hợp đồng hoặc để caller tự gọi `flush()`. Không tự ý đóng output chỉ để buộc dữ liệu được flush.

## 4. Phương thức tự mở stream phải đóng stream

Khi một phương thức tự tạo stream từ `Path`, nó cũng chịu trách nhiệm giải phóng tài nguyên đó:

```java
static void printFile(Path path) throws IOException {
    try (InputStream input = Files.newInputStream(path)) {
        byte[] buffer = new byte[4096];
        int count;
        while ((count = input.read(buffer)) != -1) {
            System.out.write(buffer, 0, count);
        }
    }
}
```

Ở đây phương thức tự mở `input`, nên nó đóng stream khi hoàn tất, kể cả khi vòng lặp ném exception. `System.out` là stream chuẩn của tiến trình và không thuộc quyền sở hữu của phương thức; ví dụ không đóng `System.out`.

Một trường hợp khác là factory mở stream rồi trả về:

```java
static InputStream openFile(Path path) throws IOException {
    return Files.newInputStream(path);
}
```

Caller nhận một stream đang mở và phải quản lý nó:

```java
try (InputStream input = openFile(path)) {
    // Đọc dữ liệu ở đây.
}
```

Không đóng stream trước khi trả về, vì caller cần dùng nó. Cũng không nên trả về một stream đã được đóng trong phạm vi factory.

## 5. Wrapper thường đóng luôn stream bên dưới

Các lớp như `BufferedInputStream`, `BufferedOutputStream`, `DataInputStream`, `DataOutputStream`, `InputStreamReader` và `BufferedReader` thường bọc một stream hoặc reader khác. Khi đóng wrapper, thao tác `close()` được chuyển tiếp xuống tài nguyên bên dưới theo hợp đồng của lớp wrapper.

Ví dụ:

```java
InputStream raw = Files.newInputStream(path);
try (InputStream input = new BufferedInputStream(raw)) {
    // Đọc từ input.
}
```

Khi `input` được đóng, `BufferedInputStream` đóng `raw` cùng với nó. Wrapper đang quản lý stream bên dưới.

Không cần khai báo cả `raw` và `input` như hai tài nguyên độc lập trong cùng một `try-with-resources` nếu wrapper đã chịu trách nhiệm đóng delegate:

```java
// Tránh đóng cùng một delegate hai lần qua hai biến resource.
InputStream raw = Files.newInputStream(path);
try (InputStream input = new BufferedInputStream(raw)) {
    // Đọc dữ liệu.
}
```

Điểm cần chú ý hơn là khi wrapper được tạo quanh một stream mượn từ caller. Nếu phương thức đóng wrapper, nó cũng có thể đóng stream của caller. Không được coi wrapper là một tài nguyên độc lập với delegate nếu `close()` của wrapper truyền tiếp xuống dưới.

## 6. `try-with-resources` đóng theo thứ tự nào?

Java tự gọi `close()` khi rời khỏi khối `try`, dù khối đó kết thúc bình thường hay do exception. Nếu có nhiều tài nguyên, chúng được đóng theo thứ tự ngược với thứ tự khai báo. Điều này hữu ích khi tài nguyên thứ hai phụ thuộc vào tài nguyên thứ nhất: tài nguyên phụ thuộc được đóng trước.

```java
try (InputStream input = Files.newInputStream(source);
     OutputStream output = Files.newOutputStream(target)) {
    copy(input, output);
} // output đóng trước, input đóng sau
```

Nếu thân `try` ném exception và `close()` cũng ném exception, exception từ thân khối vẫn là exception chính. Exception phát sinh trong lúc đóng được lưu dưới dạng *suppressed exception* và có thể lấy bằng `getSuppressed()`. Nếu thân khối không ném exception nhưng `close()` thất bại, lỗi đóng sẽ được truyền ra caller.

Không nên tự viết `finally { input.close(); }` sơ sài rồi bỏ qua lỗi đóng hoặc vô tình che exception gốc. `try-with-resources` xử lý thứ tự đóng và suppressed exception nhất quán hơn.

## 7. Không đóng stream dùng chung của tiến trình

`System.in`, `System.out` và `System.err` là các stream chuẩn dùng chung trong toàn bộ tiến trình Java. Một thư viện hoặc helper thông thường không nên đóng chúng, vì thao tác đó có thể khiến phần còn lại của ứng dụng không thể tiếp tục đọc từ đầu vào chuẩn hoặc ghi ra đầu ra/lỗi chuẩn.

Cẩn thận khi bọc stream chuẩn:

```java
BufferedReader reader = new BufferedReader(
        new InputStreamReader(System.in, StandardCharsets.UTF_8)
);
```

Nếu đóng `reader`, thao tác đóng có thể truyền xuống `System.in`. Trong ứng dụng cần giữ đầu vào chuẩn mở cho phần khác, đừng đóng wrapper này; hãy để thành phần quản lý vòng đời tiến trình quyết định thời điểm kết thúc sử dụng stream chuẩn. Quy tắc tương tự áp dụng cho wrapper quanh `System.out` và `System.err`.

Với socket, hãy xem stream là một phần của vòng đời kết nối: tài liệu `Socket` quy định đóng stream lấy từ socket sẽ đóng socket liên quan. Nếu nhiều thành phần cùng dùng kết nối, cần có một nơi quản lý ownership và đóng socket khi không còn thành phần nào cần nó.

## 8. Đóng lặp lại và lớp stream tùy chỉnh

`Closeable` quy định rằng nếu luồng đã đóng thì gọi `close()` thêm lần nữa không có tác dụng. Nhiều stream chuẩn tuân theo hợp đồng này. Tuy nhiên, không nên dựa vào việc đóng lặp lại như một cách tổ chức ownership: một wrapper và delegate được quản lý riêng có thể gây khó hiểu, còn các implementation `AutoCloseable` tùy chỉnh không bắt buộc phải có hành vi idempotent như `Closeable`.

Thiết kế rõ một nơi chịu trách nhiệm đóng mỗi tài nguyên. Nếu viết lớp tài nguyên riêng, hãy xác định rõ trạng thái sau khi đóng, hành vi khi đóng lần hai và exception có thể phát sinh; ghi các quy tắc đó trong Javadoc.

## 9. Ví dụ hoàn chỉnh: kiểm tra ownership và thứ tự đóng

Ví dụ dưới đây dùng stream theo dõi lời gọi `close()` để chứng minh ba điểm: hàm mượn stream không đóng tài nguyên, đóng wrapper đóng luôn delegate, và `try-with-resources` đóng theo thứ tự ngược. Phần cuối minh họa exception từ `close()` được giữ lại dưới dạng suppressed khi thân `try` đã thất bại.

Tạo tệp `StreamOwnershipDemo.java`:

```java
import java.io.BufferedInputStream;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

public class StreamOwnershipDemo {
    private static final class TrackingInputStream extends ByteArrayInputStream {
        private boolean closed;
        TrackingInputStream(byte[] data) { super(data); }
        @Override public void close() { closed = true; }
        boolean isClosed() { return closed; }
    }

    private static final class TrackingOutputStream extends ByteArrayOutputStream {
        private boolean closed;
        @Override public void close() { closed = true; }
        boolean isClosed() { return closed; }
    }

    private static final class NamedResource implements AutoCloseable {
        private final String name;
        private final List<String> events;
        NamedResource(String name, List<String> events) {
            this.name = name;
            this.events = events;
        }
        @Override public void close() { events.add(name); }
    }

    // Borrows both streams: the caller remains responsible for closing them.
    private static void copy(InputStream input, java.io.OutputStream output)
            throws IOException {
        byte[] buffer = new byte[4];
        int count;
        while ((count = input.read(buffer)) != -1) {
            output.write(buffer, 0, count);
        }
    }

    @SuppressWarnings("try")
    public static void main(String[] args) throws Exception {
        TrackingInputStream input = new TrackingInputStream(
                "Java".getBytes(StandardCharsets.UTF_8));
        TrackingOutputStream output = new TrackingOutputStream();
        copy(input, output);
        System.out.println("Copied: " + new String(output.toByteArray(), StandardCharsets.UTF_8));
        System.out.println("Caller streams still open: " + (!input.isClosed() && !output.isClosed()));
        input.close();
        output.close();

        TrackingInputStream delegate = new TrackingInputStream(new byte[] {1, 2, 3});
        try (InputStream buffered = new BufferedInputStream(delegate)) {
            buffered.read();
        }
        System.out.println("Wrapper closed delegate: " + delegate.isClosed());

        List<String> closeOrder = new ArrayList<>();
        try (NamedResource first = new NamedResource("first", closeOrder);
             NamedResource second = new NamedResource("second", closeOrder)) {
            closeOrder.add("body");
        }
        System.out.println("Try-with-resources order: " + String.join(" -> ", closeOrder));

        try (AutoCloseable resource = () -> {
            throw new IOException("close failure");
        }) {
            throw new IOException("body failure");
        } catch (Exception ex) {
            System.out.println("Primary exception: " + ex.getMessage());
            System.out.println("Suppressed exception: " + ex.getSuppressed()[0].getMessage());
        }
    }
}
```

Biên dịch bằng JDK 9 trở lên:

```bash
javac --release 9 -Xlint:all StreamOwnershipDemo.java
java StreamOwnershipDemo
```

Kết quả stdout:

```text
Copied: Java
Caller streams still open: true
Wrapper closed delegate: true
Try-with-resources order: body -> second -> first
Primary exception: body failure
Suppressed exception: close failure
```

`copy()` chỉ mượn hai stream nên sau khi hàm trả về, cả hai vẫn mở. Đóng `BufferedInputStream` làm delegate bị đóng theo. Hai `NamedResource` được đóng theo thứ tự `second` rồi `first`. Cuối cùng, lỗi trong thân `try` được giữ làm exception chính và lỗi khi đóng tài nguyên được đính kèm bằng `getSuppressed()`.

## 10. Checklist khi thiết kế API nhận hoặc trả stream

1. Ghi rõ phương thức mở stream hay nhận stream do caller cung cấp.
2. Nếu phương thức tự mở tài nguyên, đóng nó bằng `try-with-resources` trong cùng phạm vi.
3. Nếu chỉ mượn stream đầu vào/đầu ra, không đóng stream hoặc wrapper có thể đóng delegate của caller.
4. Nếu trả về stream đang mở, ghi rõ caller phải đóng nó.
5. Nếu chuyển ownership cho phương thức khác, ghi rõ thời điểm chuyển giao và bên chịu trách nhiệm đóng.
6. Xác định wrapper có truyền `close()` xuống delegate hay không; tránh quản lý delegate như hai resource độc lập.
7. Dùng `try-with-resources` để bảo đảm đóng khi có exception và giữ lại suppressed exceptions.
8. Phân biệt `flush()` với `close()`; không đóng stream chuẩn hoặc stream dùng chung của ứng dụng.

Quyền đóng stream trong Java là một phần của hợp đồng ownership. Thành phần mở tài nguyên thường chịu trách nhiệm đóng; thành phần chỉ mượn stream phải tôn trọng vòng đời do caller quản lý. Khi hợp đồng này rõ ràng, wrapper, luồng vào/ra và xử lý exception sẽ phối hợp an toàn hơn.