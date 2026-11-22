# Tái cấu trúc khối xử lý tài nguyên và kiểm chứng đường lỗi

## Mục tiêu

Khi một đoạn mã mở nhiều tài nguyên, thực hiện công việc rồi đóng chúng trong khối finally, việc xử lý ngoại lệ và thứ tự đóng có thể trở nên khó kiểm soát. Try-with-resources giúp gom vòng đời tài nguyên vào một cấu trúc rõ ràng: tài nguyên được đóng tự động, kể cả khi phần thân phát sinh ngoại lệ hoặc việc khởi tạo một tài nguyên tiếp theo thất bại.

Tái cấu trúc đúng cần bảo toàn hành vi nghiệp vụ, thứ tự phụ thuộc giữa các tài nguyên và thông tin của ngoại lệ. Sau khi refactor, hãy kiểm chứng cả đường chạy thành công lẫn các đường lỗi quan trọng.

## 1. Nhận diện vấn đề trong cách đóng thủ công

Một mẫu cũ thường khai báo biến trước, gán tài nguyên bên trong try rồi đóng trong finally:

~~~java
InputStream input = null;
OutputStream output = null;

try {
    input = Files.newInputStream(source);
    output = Files.newOutputStream(target);
    input.transferTo(output);
} finally {
    if (output != null) {
        output.close();
    }
    if (input != null) {
        input.close();
    }
}
~~~

Đoạn mã này có một số điểm dễ sai:

- Mỗi tài nguyên cần được kiểm tra null và đóng đúng thứ tự.
- Nếu output.close() phát sinh ngoại lệ, input.close() có thể không được gọi nếu không có cấu trúc xử lý bổ sung.
- Nếu phần thân đã phát sinh ngoại lệ nhưng lệnh close() trong finally tiếp tục phát sinh ngoại lệ, ngoại lệ khi đóng có thể che mất nguyên nhân ban đầu.
- Khi thêm tài nguyên mới, số nhánh khởi tạo một phần và dọn dẹp thủ công tăng lên.

Với các kiểu triển khai AutoCloseable, hãy ưu tiên try-with-resources. Khối này quản lý việc đóng và duy trì quan hệ giữa ngoại lệ chính với ngoại lệ phát sinh khi đóng.

## 2. Refactor sang try-with-resources

Ví dụ sao chép dữ liệu giữa hai luồng:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileCopier {
    public static void copy(Path source, Path target) throws IOException {
        try (InputStream input = Files.newInputStream(source);
             OutputStream output = Files.newOutputStream(target)) {
            input.transferTo(output);
        }
    }
}
~~~

Cách tổ chức này thể hiện rõ ba việc:

1. Mở tài nguyên tại phần khai báo của try.
2. Thực hiện thao tác chính trong phần thân.
3. Để Java tự đóng tài nguyên khi rời khối try.

InputStream và OutputStream đều triển khai AutoCloseable thông qua Closeable. Phương thức transferTo có từ Java 9 và chuyển dữ liệu từ luồng vào sang luồng đích. Ví dụ trên chạy được với JDK 17 trở lên.

Khi có nhiều tài nguyên, Java đóng theo thứ tự ngược với thứ tự khai báo. Trong ví dụ, output được đóng trước input. Đây là thứ tự phù hợp vì luồng đích được hoàn tất và đóng trước khi luồng nguồn được đóng.

Nếu một tài nguyên phụ thuộc vào tài nguyên khác trong suốt vòng đời, hãy khai báo tài nguyên nền trước và tài nguyên phụ thuộc sau để tài nguyên phụ thuộc được đóng trước. Kiểm tra thứ tự này khi refactor, đặc biệt với writer, stream, wrapper và session.

## 3. Khởi tạo một phần và thứ tự đóng

Mỗi biểu thức khởi tạo tài nguyên được đánh giá từ trái sang phải. Nếu tài nguyên thứ hai không thể khởi tạo, các tài nguyên đã khởi tạo thành công trước đó vẫn được đóng.

Ví dụ:

~~~java
try (InputStream input = Files.newInputStream(source);
     OutputStream output = openOutput(target)) {
    input.transferTo(output);
}
~~~

Nếu openOutput(target) thất bại, input đã được mở nên Java vẫn gọi input.close(). Phần thân try không được chạy vì tất cả tài nguyên chưa khởi tạo thành công.

Với nhiều tài nguyên, quá trình đóng luôn diễn ra theo thứ tự ngược. Nếu một lần đóng thất bại, Java vẫn tiếp tục thử đóng những tài nguyên còn lại. Các lỗi phát sinh thêm trong quá trình đóng được lưu thành suppressed exceptions theo quy tắc của try-with-resources.

Tài nguyên đã được tạo bên ngoài cũng có thể được dùng trực tiếp trong phần tài nguyên từ Java 9 nếu biến là final hoặc effectively final:

~~~java
InputStream input = Files.newInputStream(source);

try (input) {
    // Xử lý input
}
~~~

Không gọi close() thủ công thêm lần nữa trong finally sau khi đã đưa cùng tài nguyên vào try-with-resources. Làm vậy có thể gây đóng lặp và khiến hành vi lỗi khó dự đoán.

## 4. Hiểu ngoại lệ chính và suppressed exception

Try-with-resources phân biệt lỗi trong phần thân với lỗi phát sinh khi đóng tài nguyên.

| Tình huống | Ngoại lệ được truyền ra |
|---|---|
| Phần thân thành công, đóng tài nguyên thành công | Không có ngoại lệ |
| Phần thân phát sinh ngoại lệ, đóng thành công | Ngoại lệ từ phần thân |
| Phần thân thành công, close() phát sinh ngoại lệ | Ngoại lệ từ close() |
| Phần thân và close() đều phát sinh ngoại lệ | Ngoại lệ từ phần thân là ngoại lệ chính; lỗi đóng được gắn vào bằng getSuppressed() |
| Khởi tạo tài nguyên sau thất bại | Lỗi khởi tạo là ngoại lệ chính; các lỗi khi đóng tài nguyên đã mở được gắn dưới dạng suppressed |

Ví dụ kiểm tra ngoại lệ bị suppressed:

~~~java
try (java.io.Closeable resource = () -> {
    throw new java.io.IOException("close failed");
}) {
    throw new java.io.IOException("operation failed");
} catch (java.io.IOException ex) {
    System.out.println(ex.getMessage());
    for (Throwable suppressed : ex.getSuppressed()) {
        System.out.println(suppressed.getMessage());
    }
}
~~~

Kết quả:

~~~text
operation failed
close failed
~~~

Giữ nguyên ngoại lệ chính giúp người gọi biết thao tác nghiệp vụ nào thất bại. Các ngoại lệ đóng tài nguyên vẫn có thể được kiểm tra qua getSuppressed().

Nếu cần bổ sung ngữ cảnh, hãy bọc ngoại lệ nhưng giữ nguyên nguyên nhân:

~~~java
try {
    FileCopier.copy(source, target);
} catch (IOException ex) {
    throw new IOException("Cannot copy " + source + " to " + target, ex);
}
~~~

Ngoại lệ gốc được giữ trong cause. Nếu lỗi đóng tài nguyên đã bị suppressed trên ngoại lệ gốc, người xử lý có thể kiểm tra ngoại lệ gốc qua getCause() và các suppressed exceptions của nó. Tránh tạo ngoại lệ mới rồi bỏ mất cause.

## 5. Kiểm chứng đường lỗi bằng tài nguyên kiểm thử

Một cách kiểm tra ổn định là tạo một tài nguyên thử nghiệm triển khai AutoCloseable. Tài nguyên có thể ghi lại thứ tự gọi close() và chủ động phát sinh IOException. Nhờ đó, ta kiểm tra được các nhánh lỗi mà không phụ thuộc vào trạng thái ổ đĩa hoặc thiết bị bên ngoài.

Tệp ResourceFailurePaths.java:

~~~java
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public class ResourceFailurePaths {
    public static void main(String[] args) throws IOException {
        verifySuccessfulPath();
        verifyBodyAndCloseFailure();
        verifyCloseFailureOnly();
        verifyInitializationFailure();
        System.out.println("All resource-path checks passed.");
    }

    private static void verifySuccessfulPath() throws IOException {
        List<String> events = new ArrayList<>();

        try (TestResource first =
                     new TestResource("first", events, false);
             TestResource second =
                     new TestResource("second", events, false)) {
            events.add("body");
        }

        assertEquals(
                List.of("body", "close second", "close first"),
                events,
                "reverse close order"
        );
        System.out.println("success events: " + events);
    }

    private static void verifyBodyAndCloseFailure() {
        List<String> events = new ArrayList<>();
        IOException primary = null;

        try (TestResource resource =
                     new TestResource("resource", events, true)) {
            events.add("body");
            throw new IOException("operation failed");
        } catch (IOException ex) {
            primary = ex;
        }

        if (primary == null) {
            throw new AssertionError("Expected operation failure");
        }

        assertEquals("operation failed", primary.getMessage(),
                "primary exception");
        assertEquals(1, primary.getSuppressed().length,
                "suppressed exception count");
        assertEquals("close failed: resource",
                primary.getSuppressed()[0].getMessage(),
                "suppressed exception message");

        System.out.println("body failure: primary="
                + primary.getMessage()
                + "; suppressed="
                + primary.getSuppressed()[0].getMessage());
    }

    private static void verifyCloseFailureOnly() {
        List<String> events = new ArrayList<>();
        IOException primary = null;

        try (TestResource resource =
                     new TestResource("resource", events, true)) {
            events.add("body");
        } catch (IOException ex) {
            primary = ex;
        }

        if (primary == null) {
            throw new AssertionError("Expected close failure");
        }

        assertEquals("close failed: resource", primary.getMessage(),
                "close exception");
        assertEquals(0, primary.getSuppressed().length,
                "suppressed exception count");

        System.out.println("close failure: primary=" + primary.getMessage());
    }

    private static void verifyInitializationFailure() {
        List<String> events = new ArrayList<>();
        IOException primary = null;

        try (TestResource first =
                     new TestResource("first", events, false);
             TestResource second = failToOpenSecond(events)) {
            events.add("body");
        } catch (IOException ex) {
            primary = ex;
        }

        if (primary == null) {
            throw new AssertionError("Expected initialization failure");
        }

        assertEquals("open failed: second", primary.getMessage(),
                "initialization exception");
        assertEquals(List.of("open second", "close first"),
                events,
                "cleanup after partial initialization");

        System.out.println("initialization failure: primary="
                + primary.getMessage() + "; events=" + events);
    }

    private static TestResource failToOpenSecond(List<String> events)
            throws IOException {
        events.add("open second");
        throw new IOException("open failed: second");
    }

    private static void assertEquals(
            Object expected, Object actual, String label) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    label + ": expected " + expected + ", got " + actual);
        }
    }

    private static final class TestResource implements AutoCloseable {
        private final String name;
        private final List<String> events;
        private final boolean failOnClose;

        private TestResource(
                String name, List<String> events, boolean failOnClose) {
            this.name = name;
            this.events = events;
            this.failOnClose = failOnClose;
        }

        @Override
        public void close() throws IOException {
            events.add("close " + name);
            if (failOnClose) {
                throw new IOException("close failed: " + name);
            }
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 ResourceFailurePaths.java
java ResourceFailurePaths
~~~

Kết quả chuẩn:

~~~text
success events: [body, close second, close first]
body failure: primary=operation failed; suppressed=close failed: resource
close failure: primary=close failed: resource
initialization failure: primary=open failed: second; events=[open second, close first]
All resource-path checks passed.
~~~

Chương trình kiểm chứng bốn trường hợp:

1. **Thành công:** phần thân chạy trước, tài nguyên thứ hai đóng trước tài nguyên thứ nhất.
2. **Lỗi trong phần thân và lỗi khi đóng:** lỗi thao tác vẫn là ngoại lệ chính; lỗi đóng xuất hiện trong getSuppressed().
3. **Chỉ lỗi khi đóng:** ngoại lệ từ close() được truyền ra ngoài.
4. **Khởi tạo một phần:** khi tài nguyên thứ hai thất bại lúc khởi tạo, tài nguyên thứ nhất vẫn được đóng và phần thân không chạy.

Test double này kiểm chứng quy tắc điều khiển của try-with-resources. Với mã dùng tệp, socket hoặc kết nối thật, vẫn nên có kiểm thử tích hợp riêng cho thao tác mở, đọc/ghi, quyền truy cập và trạng thái hệ thống.

## 6. Checklist refactor và review

Trước khi hoàn tất thay đổi, hãy kiểm tra:

- Mọi tài nguyên cần tự đóng đều triển khai AutoCloseable hoặc một kiểu con phù hợp.
- Việc mở tài nguyên nằm trong phần khai báo try để lỗi khởi tạo cũng được quản lý.
- Thứ tự khai báo phản ánh đúng quan hệ phụ thuộc và thứ tự đóng mong muốn.
- Không còn lời gọi close() thủ công cho tài nguyên đã được quản lý bởi try-with-resources.
- Ngoại lệ chính được giữ lại; không nuốt lỗi và không làm mất cause khi bọc ngoại lệ.
- Có kiểm thử cho đường thành công, lỗi phần thân, lỗi đóng và lỗi khởi tạo một phần.
- Kiểm thử xác nhận thứ tự đóng và nội dung suppressed exceptions khi các nhánh đó phát sinh.
- Mã kiểm thử không phụ thuộc vào thứ tự không xác định, thời gian chờ tùy tiện hoặc trạng thái môi trường ngoài.

## 7. Lưu ý khi triển khai

Try-with-resources phù hợp với tài nguyên có vòng đời hữu hạn và có thao tác đóng rõ ràng. Nó không thay thế việc thiết kế timeout, hủy tác vụ, đồng bộ truy cập hoặc xử lý trạng thái kết nối trong ứng dụng.

AutoCloseable cho phép close() khai báo ngoại lệ tổng quát hơn; Closeable thường dùng IOException cho tài nguyên I/O. Khi thiết kế lớp tài nguyên riêng, nên khai báo loại ngoại lệ cụ thể và giữ thao tác close() dễ dự đoán.

Nếu phần thân có thể thất bại, hãy xem ngoại lệ chính là thông tin quan trọng nhất của thao tác. Dùng getSuppressed() khi cần điều tra lỗi dọn dẹp. Cách refactor tốt vừa làm vòng đời tài nguyên rõ ràng, vừa giữ được bằng chứng cần thiết để chẩn đoán các đường lỗi.