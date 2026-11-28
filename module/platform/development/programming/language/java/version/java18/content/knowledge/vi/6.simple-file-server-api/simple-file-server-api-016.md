# Kiểm chứng IllegalArgumentException, NullPointerException và lỗi nhập xuất lúc tạo máy chủ

> **Chương:** API SimpleFileServer  
> **Module học:** JAVA_VERSION_JAVA18 — SimpleFileServer được bổ sung từ Java 18; các factory, quy tắc kiểm tra tham số và cơ chế bind của HttpServer vẫn áp dụng trên JDK hiện đại.  
> **Mục tiêu:** Phân biệt lỗi tham số không hợp lệ, tham số null và lỗi I/O khi tạo/bind HttpServer hoặc SimpleFileServer; biết API nào ném checked exception, API nào bọc lỗi I/O thành UncheckedIOException.

## 1. Tạo server gồm nhiều bước có thể thất bại

Một file server đơn giản thường cần:

1. Chọn địa chỉ IP và cổng.
2. Chọn thư mục gốc được phép phục vụ.
3. Tạo HttpServer và bind socket.
4. Tạo file handler, context và filter nếu cần.
5. Cấu hình executor rồi gọi start().

Javadoc định vị SimpleFileServer là công cụ đơn giản phục vụ testing, development và debugging. Bài này tập trung vào factory và hợp đồng exception khi dựng server cục bộ.

Mỗi API kiểm tra những điều kiện khác nhau. Vì vậy, khi thấy server không tạo được, cần xác định lỗi phát sinh ở bước nào:

| Giai đoạn | API tiêu biểu | Lỗi cần phân biệt |
| --- | --- | --- |
| Kiểm tra root directory | `SimpleFileServer.createFileHandler(root)` | `IllegalArgumentException`, `NullPointerException` |
| Tạo file server hoàn chỉnh | `SimpleFileServer.createFileServer(addr, root, level)` | `IllegalArgumentException`, `NullPointerException`, `UncheckedIOException` |
| Tạo/bind HttpServer | `HttpServer.create(addr, backlog)` | `BindException`, `IOException` |
| Tạo server kèm context ban đầu | `HttpServer.create(addr, backlog, path, handler, filters)` | `IllegalArgumentException`, `NullPointerException`, `BindException`, `IOException` |
| Tạo context sau khi tạo server | `server.createContext(path, handler)` | `IllegalArgumentException`, `NullPointerException` |

Điểm cần nhớ: các lỗi này không có cùng một kiểu. `IllegalArgumentException` và `NullPointerException` là unchecked exceptions; `IOException` là checked exception; `UncheckedIOException` là runtime exception bọc một `IOException`.

## 2. IllegalArgumentException: đối số có giá trị hoặc trạng thái không hợp lệ

`IllegalArgumentException` thường có nghĩa đối số không null nhưng vi phạm hợp đồng của API.

### 2.1. Root directory không hợp lệ

`SimpleFileServer.createFileHandler(rootDirectory)` yêu cầu root:

- Tồn tại.
- Là đường dẫn tuyệt đối.
- Trỏ đến một thư mục.
- Có thể đọc được.

Nếu vi phạm một trong các điều kiện trên, factory ném `IllegalArgumentException`.

Ví dụ:

~~~java
Path relative = Path.of("public");
SimpleFileServer.createFileHandler(relative); // IllegalArgumentException
~~~

Đường dẫn tương đối không hợp lệ ngay cả khi thư mục `public` tồn tại trong working directory. Hãy chuyển sang đường dẫn tuyệt đối:

~~~java
Path root = Path.of("public").toAbsolutePath().normalize();
HttpHandler handler = SimpleFileServer.createFileHandler(root);
~~~

Một file thường cũng không thể dùng làm root directory:

~~~java
Path file = Files.createTempFile("not-a-directory-", ".txt");
SimpleFileServer.createFileHandler(file); // IllegalArgumentException
~~~

Tương tự, đường dẫn không tồn tại cũng bị từ chối. Đừng coi việc tạo được đối tượng `Path` là bằng chứng file hoặc thư mục đã tồn tại; `Path.of(...)` chỉ biểu diễn đường dẫn.

### 2.2. Path của HttpContext không hợp lệ

Overload:

~~~java
HttpServer.create(
        InetSocketAddress addr,
        int backlog,
        String path,
        HttpHandler handler,
        Filter... filters)
~~~

yêu cầu `path` là URI path tuyệt đối, bắt đầu bằng `/`. Ví dụ `"/"` và `"/assets/"` hợp lệ; `"assets/"` không hợp lệ.

Nếu path không hợp lệ, API ném `IllegalArgumentException`. `server.createContext(path, handler)` cũng ném lỗi này nếu path sai hoặc context có cùng path đã tồn tại.

### 2.3. OutputLevel.NONE: cần phân biệt hai factory

Hai API có hợp đồng khác nhau:

| API | Truyền `OutputLevel.NONE` |
| --- | --- |
| `SimpleFileServer.createFileServer(addr, root, OutputLevel.NONE)` | **Hợp lệ**: tạo file server không ghi log. |
| `SimpleFileServer.createOutputFilter(out, OutputLevel.NONE)` | **Không hợp lệ**: ném `IllegalArgumentException`. |

Nếu không muốn ghi log cho một context, cách được khuyến nghị là không gắn output filter. Đừng dùng `NONE` để tạo filter rồi mong filter im lặng.

### 2.4. Backlog không phải nguyên nhân IllegalArgumentException

Với `HttpServer.create(addr, backlog)` và `server.bind(addr, backlog)`:

- `backlog > 0`: chỉ định giới hạn hàng đợi kết nối TCP đang chờ được accept.
- `backlog <= 0`: dùng giá trị mặc định của hệ thống.

Do đó, `backlog = 0` và cả số âm không tự động gây `IllegalArgumentException` theo hợp đồng API. Backlog là hàng đợi kết nối TCP, không phải số worker thread của Executor.

## 3. NullPointerException: tham số bắt buộc bị null

`NullPointerException` xuất hiện khi một tham số mà API yêu cầu phải có giá trị lại nhận `null`.

### 3.1. SimpleFileServer factory

Theo hợp đồng:

| API | Tham số null gây lỗi |
| --- | --- |
| `SimpleFileServer.createFileHandler(rootDirectory)` | `rootDirectory` |
| `SimpleFileServer.createFileServer(addr, rootDirectory, outputLevel)` | Bất kỳ tham số nào: `addr`, `rootDirectory`, `outputLevel` |
| `SimpleFileServer.createOutputFilter(out, outputLevel)` | Bất kỳ tham số nào: `out`, `outputLevel` |

Ví dụ:

~~~java
SimpleFileServer.createFileHandler(null); // NullPointerException
~~~

### 3.2. HttpServer overload có context ban đầu

`HttpServer.create(addr, backlog)` có một quy tắc riêng: nếu `addr == null`, API tạo server chưa bind; ứng dụng phải gọi `bind(...)` sau đó. Vì vậy, không nên kết luận mọi tham số `addr == null` trong HttpServer đều gây `NullPointerException`.

Ngược lại, overload tạo server cùng context ban đầu yêu cầu:

- `path` khác null.
- `handler` khác null.
- Mảng `filters` khác null.
- Mọi phần tử trong `filters` khác null.

Nếu một điều kiện bị vi phạm, API ném `NullPointerException`.

Ví dụ:

~~~java
HttpServer.create(
        null,  // Cho phép server chưa bind
        0,
        null,  // path là null: NullPointerException
        exchange -> {},
        new Filter[0]);
~~~

Ví dụ trên minh họa rằng `addr == null` không phải nguyên nhân; `path == null` mới là tham số sai theo overload đang gọi.

### 3.3. bind(null, backlog) khác create(null, backlog)

Hai lời gọi sau có ý nghĩa khác nhau:

~~~java
HttpServer unbound = HttpServer.create(null, 0); // Tạo server chưa bind
unbound.bind(address, 0);                       // Bind sau
~~~

~~~java
HttpServer unbound = HttpServer.create();
unbound.bind(null, 0); // NullPointerException
~~~

`bind(...)` cần một địa chỉ cụ thể để bind nên `addr == null` không hợp lệ.

## 4. IOException và BindException khi bind socket

`HttpServer.create(addr, backlog)` tạo và bind server vào địa chỉ được chỉ định. API khai báo `throws IOException`; một trường hợp cụ thể là `BindException` khi không thể bind vào địa chỉ/cổng yêu cầu hoặc server đã được bind.

Các nguyên nhân thường gặp:

- Một tiến trình khác đang dùng cổng đó.
- Địa chỉ IP không thuộc giao diện mạng hiện có.
- Hệ điều hành từ chối bind vì quyền hoặc chính sách mạng.
- Có lỗi I/O ở tầng socket/provider.

`BindException` kế thừa `IOException`, vì vậy có thể bắt riêng bind failure trước rồi bắt `IOException` tổng quát:

~~~java
try {
    HttpServer server = HttpServer.create(address, 0);
    // Cấu hình context và start server.
} catch (BindException e) {
    System.err.println("Không thể bind địa chỉ/cổng: " + e.getMessage());
} catch (IOException e) {
    System.err.println("Lỗi I/O khi tạo server: " + e.getMessage());
}
~~~

Không nên bắt `Exception` chung rồi bỏ qua. Thông tin exception giúp phân biệt cổng đang bận với lỗi I/O khác.

### 4.1. Tạo server chưa bind rồi bind sau

Nếu muốn tách bước tạo instance khỏi bước chọn địa chỉ:

~~~java
HttpServer server = HttpServer.create();
try {
    server.bind(address, 0);
    server.createContext("/", handler);
    server.start();
} catch (IOException e) {
    System.err.println("Không thể bind server: " + e.getMessage());
    throw e;
}
~~~

`HttpServer.create()` cũng khai báo `IOException`. `bind(...)` khai báo `IOException`, ném `BindException` nếu địa chỉ không thể bind hoặc server đã bind, và ném `NullPointerException` nếu địa chỉ null.

## 5. UncheckedIOException khi dùng SimpleFileServer.createFileServer()

Một khác biệt quan trọng giữa hai factory:

~~~java
HttpServer server = HttpServer.create(address, 0);
~~~

Phương thức này khai báo checked `IOException`.

Trong khi đó:

~~~java
HttpServer server = SimpleFileServer.createFileServer(
        address, root, SimpleFileServer.OutputLevel.NONE);
~~~

`createFileServer(...)` không khai báo checked `IOException`. Theo Javadoc, nếu có lỗi I/O trong quá trình tạo file server, factory ném `UncheckedIOException`.

Factory trả về một `HttpServer` đã bind và có context phục vụ file, nhưng **chưa gọi start()**. Ứng dụng vẫn phải gọi `server.start()` sau khi cấu hình xong.

`UncheckedIOException` giữ nguyên nguyên nhân I/O trong `getCause()`:

~~~java
try {
    HttpServer server = SimpleFileServer.createFileServer(
            address, root, SimpleFileServer.OutputLevel.INFO);
} catch (IllegalArgumentException e) {
    System.err.println("Root directory không hợp lệ: " + e.getMessage());
} catch (NullPointerException e) {
    System.err.println("Thiếu tham số bắt buộc: " + e.getMessage());
} catch (UncheckedIOException e) {
    IOException cause = e.getCause();
    System.err.println("Lỗi I/O khi tạo file server: " + cause.getMessage());
}
~~~

Không bắt `IOException` trực tiếp quanh lời gọi `createFileServer(...)` vì chữ ký phương thức không ném checked exception đó. Nếu cần xử lý ở tầng checked exception, có thể lấy `e.getCause()` sau khi bắt `UncheckedIOException`.

## 6. Bảng tổng hợp exception theo API

| API | `IllegalArgumentException` | `NullPointerException` | Lỗi I/O |
| --- | --- | --- | --- |
| `SimpleFileServer.createFileHandler(root)` | Root không tồn tại, không tuyệt đối, không phải directory hoặc không đọc được | `root == null` | Không khai báo lỗi I/O checked trong factory |
| `SimpleFileServer.createFileServer(addr, root, level)` | Root không tồn tại, không tuyệt đối, không phải directory hoặc không đọc được | Bất kỳ tham số nào null | `UncheckedIOException` |
| `SimpleFileServer.createOutputFilter(out, level)` | `level == NONE` | `out` hoặc `level` null | Lỗi ghi stream có thể xuất hiện khi filter xử lý exchange, không phải lỗi bind server |
| `HttpServer.create(addr, backlog)` | Không dùng backlog âm làm điều kiện lỗi; `backlog <= 0` dùng mặc định | `addr == null` được phép để tạo server chưa bind | `BindException` hoặc `IOException` khi bind/tạo |
| `HttpServer.create(addr, backlog, path, handler, filters)` | `path` không hợp lệ | `path`, `handler`, `filters` hoặc phần tử filter null | `BindException` hoặc `IOException` |
| `server.bind(addr, backlog)` | Không dùng backlog âm làm điều kiện lỗi; `backlog <= 0` dùng mặc định | `addr == null` | `BindException` hoặc `IOException` |
| `server.createContext(path, handler)` | Path sai hoặc context trùng path | `path` hoặc `handler` null | Không phải API bind socket |

Bảng trên tập trung vào các hợp đồng chính được dùng khi khởi tạo file server. Các lỗi phát sinh sau khi server chạy — ví dụ file bị xóa, stream log lỗi hoặc client ngắt kết nối — thuộc giai đoạn xử lý exchange và cần được chẩn đoán riêng.

## 7. Ví dụ kiểm chứng các lỗi tham số

Đoạn mã sau minh họa các trường hợp có thể tái hiện ổn định mà không cần chiếm cổng:

~~~java
import com.sun.net.httpserver.Filter;
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.SimpleFileServer;

import java.nio.file.Files;
import java.nio.file.Path;

public class ServerArgumentChecks {
    public static void main(String[] args) throws Exception {
        // 1. Null root -> NullPointerException.
        try {
            SimpleFileServer.createFileHandler(null);
        } catch (NullPointerException e) {
            System.out.println("Null root: " + e.getClass().getSimpleName());
        }

        // 2. File thay vì directory -> IllegalArgumentException.
        Path file = Files.createTempFile("not-a-root-", ".txt");
        try {
            SimpleFileServer.createFileHandler(file);
        } catch (IllegalArgumentException e) {
            System.out.println("File as root: "
                    + e.getClass().getSimpleName());
        } finally {
            Files.deleteIfExists(file);
        }

        // 3. Relative root -> IllegalArgumentException.
        try {
            SimpleFileServer.createFileHandler(Path.of("."));
        } catch (IllegalArgumentException e) {
            System.out.println("Relative root: "
                    + e.getClass().getSimpleName());
        }

        // 4. OutputLevel.NONE hợp lệ với createFileServer,
        // nhưng không hợp lệ với createOutputFilter.
        try {
            SimpleFileServer.createOutputFilter(
                    System.out, SimpleFileServer.OutputLevel.NONE);
        } catch (IllegalArgumentException e) {
            System.out.println("NONE filter: "
                    + e.getClass().getSimpleName());
        }

        // 5. addr=null được phép khi tạo server chưa bind.
        HttpServer unbound = HttpServer.create(null, 0);
        System.out.println("Unbound server created: "
                + (unbound.getAddress() == null));

        // 6. Path context tương đối -> IllegalArgumentException.
        try {
            HttpServer.create(
                    null,
                    0,
                    "relative",
                    exchange -> {},
                    new Filter[0]);
        } catch (IllegalArgumentException e) {
            System.out.println("Relative context: "
                    + e.getClass().getSimpleName());
        }

        // 7. path=null -> NullPointerException; addr=null vẫn hợp lệ.
        try {
            HttpServer.create(
                    null,
                    0,
                    null,
                    exchange -> {},
                    new Filter[0]);
        } catch (NullPointerException e) {
            System.out.println("Null context path: "
                    + e.getClass().getSimpleName());
        }

        // 8. bind(null, ...) -> NullPointerException.
        try {
            unbound.bind(null, 0);
        } catch (NullPointerException e) {
            System.out.println("Null bind address: "
                    + e.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 18 trở lên:

~~~bash
javac ServerArgumentChecks.java
java ServerArgumentChecks
~~~

Kết quả có dạng:

~~~text
Null root: NullPointerException
File as root: IllegalArgumentException
Relative root: IllegalArgumentException
NONE filter: IllegalArgumentException
Unbound server created: true
Relative context: IllegalArgumentException
Null context path: NullPointerException
Null bind address: NullPointerException
~~~

`createOutputFilter(..., NONE)` chỉ được gọi để kiểm tra hợp đồng factory; filter không được tạo nên không cần gắn vào context. `createFileServer(..., NONE)` là trường hợp hợp lệ để tạo server tắt logging.

## 8. Ví dụ kiểm chứng BindException

Để tái hiện lỗi cổng đã được sử dụng, có thể mở một `ServerSocket` trên loopback rồi yêu cầu `HttpServer` bind cùng địa chỉ/cổng:

~~~java
import com.sun.net.httpserver.HttpServer;

import java.net.BindException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;

public class BindFailureCheck {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (ServerSocket occupied = new ServerSocket()) {
            occupied.bind(new InetSocketAddress(loopback, 0));
            InetSocketAddress sameAddress = new InetSocketAddress(
                    loopback, occupied.getLocalPort());

            try {
                HttpServer.create(sameAddress, 0);
                throw new AssertionError(
                        "Mong đợi BindException vì cổng đang được sử dụng");
            } catch (BindException e) {
                System.out.println("Bind failed as expected: "
                        + e.getClass().getSimpleName());
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BindFailureCheck.java
java BindFailureCheck
~~~

Trên hệ thống thông thường, kết quả là:

~~~text
Bind failed as expected: BindException
~~~

Ví dụ này phụ thuộc vào hành vi bind của hệ điều hành và socket provider. Nếu môi trường cho phép chia sẻ địa chỉ/cổng theo chính sách socket đặc biệt, hãy dùng một cổng đang được tiến trình khác sở hữu hoặc kiểm thử `BindException` trong môi trường cô lập.

## 9. Cách chuẩn bị đầu vào trước khi tạo server

Để lỗi dễ hiểu và không bind socket trước khi phát hiện root sai, hãy xác thực root trước:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

static Path validateRoot(Path root) {
    Objects.requireNonNull(root, "root must not be null");

    Path absolute = root.toAbsolutePath().normalize();
    if (!Files.isDirectory(absolute) || !Files.isReadable(absolute)) {
        throw new IllegalArgumentException(
                "Root phải tồn tại, là directory và đọc được: " + absolute);
    }
    return absolute;
}
~~~

Sau đó tạo file handler rồi mới bind:

~~~java
Path root = validateRoot(Path.of("public"));
HttpHandler files = SimpleFileServer.createFileHandler(root);

HttpServer server = HttpServer.create(
        new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
server.createContext("/", files);
server.start();
~~~

Đây là cách chia lỗi theo giai đoạn: tham số root được kiểm tra trước, lỗi bind được báo ở bước tạo HttpServer. Tuy vậy, kiểm tra trước không loại bỏ hoàn toàn race condition của filesystem; quyền truy cập hoặc trạng thái thư mục vẫn có thể thay đổi sau khi kiểm tra.

Nếu dùng factory một bước `SimpleFileServer.createFileServer(...)`, factory đã thực hiện kiểm tra root và tạo server. Khi cần xử lý lỗi I/O, bắt `UncheckedIOException` theo đúng chữ ký API.

## 10. Các lỗi chẩn đoán thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `IllegalArgumentException` từ `createFileHandler` | Root không tồn tại, tương đối, không phải directory hoặc không đọc được. | Dùng root tuyệt đối và kiểm tra directory/readability. |
| `NullPointerException` từ `createFileServer` | `addr`, `rootDirectory` hoặc `outputLevel` null. | Kiểm tra từng tham số trước khi gọi factory. |
| `UncheckedIOException` từ `createFileServer` | I/O lỗi khi tạo file server. | Xem `getCause()` để lấy IOException gốc. |
| `BindException` từ `HttpServer.create` | Địa chỉ/cổng không bind được hoặc server đã bind. | Dùng cổng khả dụng, địa chỉ local hợp lệ và chỉ bind một lần. |
| `IOException` khác từ `HttpServer.create` | Lỗi I/O tầng socket/provider. | Ghi nhận cause, địa chỉ, cổng và môi trường chạy. |
| `IllegalArgumentException` từ overload có path | Context path không hợp lệ. | Dùng URI path bắt đầu bằng `/`. |
| `NullPointerException` từ overload có context | `path`, `handler`, `filters` hoặc phần tử filter null. | Tạo đầy đủ tham số và không truyền null vào varargs. |
| Nghĩ backlog âm là lỗi | Nhầm backlog với một số lượng bắt buộc dương. | Nhớ rằng `backlog <= 0` yêu cầu system default. |
| Nghĩ `addr == null` luôn là lỗi | Nhầm overload create với bind. | `create(null, backlog)` tạo server chưa bind; `bind(null, backlog)` ném NPE. |
| Nghĩ `OutputLevel.NONE` luôn lỗi | Nhầm createFileServer với createOutputFilter. | NONE hợp lệ cho createFileServer, nhưng không hợp lệ cho createOutputFilter. |

## 11. Nguyên tắc xử lý exception

1. **Đọc đúng chữ ký API:** xác định checked exception và unchecked exception trước khi viết catch.
2. **Bắt lỗi cụ thể trước:** bắt `BindException` trước `IOException`.
3. **Không chuyển mọi lỗi thành null:** nếu tạo server thất bại, báo lỗi rõ ràng hoặc truyền exception lên caller.
4. **Giữ nguyên nguyên nhân:** với `UncheckedIOException`, đọc `getCause()` thay vì chỉ ghi message ngoài.
5. **Xác thực root trước khi bind:** tránh chiếm cổng trong lúc phát hiện thư mục không hợp lệ.
6. **Phân biệt các overload:** `create(null, backlog)` có thể tạo server chưa bind; `bind(null, backlog)` không hợp lệ.
7. **Không tự suy ra lỗi từ tên tham số:** backlog âm không phải IAE; `OutputLevel.NONE` có hợp đồng khác nhau giữa hai factory.
8. **Không coi lỗi tạo server là lỗi HTTP response:** nếu factory chưa tạo được server, chưa có request nào để trả 4xx/5xx.
9. **Chỉ dùng các hợp đồng còn áp dụng:** tập trung Javadoc hiện đại; không dựa vào nhánh xử lý Security Manager cũ đã không còn là mô hình bảo mật hiện hành.

## 12. Câu hỏi tự kiểm tra

1. Khi nào `SimpleFileServer.createFileHandler(root)` ném `IllegalArgumentException`?
2. Vì sao `Path.of("public")` có thể không hợp lệ dù thư mục tồn tại?
3. Những tham số nào của `SimpleFileServer.createFileServer(...)` không được null?
4. Vì sao `createFileServer(...)` ném `UncheckedIOException` thay vì khai báo `IOException`?
5. `OutputLevel.NONE` hợp lệ với factory nào và không hợp lệ với factory nào?
6. `HttpServer.create(null, 0)` có ném `NullPointerException` không? Vì sao?
7. `HttpServer.bind(null, 0)` ném exception nào?
8. `backlog = 0` hoặc số âm có nghĩa gì?
9. `BindException` có quan hệ kế thừa thế nào với `IOException`?
10. Overload `HttpServer.create(addr, backlog, path, handler, filters)` có thể ném IAE và NPE trong những trường hợp nào?
11. Vì sao nên validate root trước khi bind socket?
12. Khi nhận `UncheckedIOException`, lấy IOException gốc bằng cách nào?

**Bài thực hành:** chạy `ServerArgumentChecks` để quan sát IAE/NPE, sau đó chạy `BindFailureCheck` để tái hiện BindException. Thử thay `OutputLevel.NONE` bằng `INFO` trong `createFileServer`, rồi so sánh với `createOutputFilter`. Cuối cùng thử `HttpServer.create(null, 0)` và `bind(null, 0)` để ghi lại khác biệt giữa server chưa bind và địa chỉ bind không hợp lệ.

## Tài liệu tham khảo chính thức

- [Oracle JDK 27 — `SimpleFileServer`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): hợp đồng root directory, `createFileServer`, `createFileHandler`, `createOutputFilter` và các exception.
- [Oracle JDK 18 — `SimpleFileServer`](https://docs.oracle.com/en/java/javase/18/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): đối chiếu các factory được giới thiệu trong Java 18.
- [Oracle JDK 27 — `HttpServer`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): các overload `create`, `bind`, backlog, context và lỗi bind.
- [Oracle JDK 18 — `HttpServer`](https://docs.oracle.com/en/java/javase/18/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): đối chiếu hợp đồng tạo và bind server từ Java 18.
- [Oracle JDK 27 — `BindException`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/BindException.html): lỗi bind socket và quan hệ kế thừa với IOException.
- [Oracle JDK 27 — `UncheckedIOException`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/UncheckedIOException.html): runtime wrapper cho IOException.
