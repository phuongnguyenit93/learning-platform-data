# `ofFile`, `ofFileDownload` và đường dẫn đầu ra của HTTP Response (Java 11 trở lên)

## 1. Vì sao tải HTTP Response xuống file không chỉ là chọn một tên file?

Trong HTTP Client chuẩn được đưa vào Java 11 (`java.net.http`), một HTTP response body có thể chứa văn bản, hình ảnh, tài liệu PDF, tệp ZIP hoặc bất kỳ dãy byte nào. Khi nội dung tương đối lớn hoặc cần lưu lâu dài, cách thuận tiện là yêu cầu HTTP Client **ghi body trực tiếp xuống file**, thay vì gom toàn bộ vào `String` hoặc `byte[]` trong bộ nhớ.

Hai API thường gặp:

```java
HttpResponse.BodyHandlers.ofFile(path);

HttpResponse.BodyHandlers.ofFileDownload(directory, options);
```

Cả hai đều cho `HttpResponse<Path>`, nhưng cách quyết định **đường dẫn đầu ra** khác nhau:

- **`ofFile(Path file)`:** ứng dụng **chỉ định toàn bộ đường dẫn file đích**, kể cả tên file.
- **`ofFileDownload(Path directory, OpenOption... options)`:** ứng dụng chỉ định **thư mục**; tên file được lấy từ header `Content-Disposition` của HTTP response, theo quy tắc được JDK hỗ trợ.

Sự khác biệt này liên quan trực tiếp đến việc tin cậy metadata của server, tránh ghi đè file, kiểm tra HTTP status, quy tắc `Path` và trách nhiệm dọn file khi download thất bại.

**Phạm vi bài:** Java 11+ và các API vẫn được hỗ trợ trong JDK hiện hành. Không dùng HTTP Client `com.sun.*` cũ hoặc ví dụ phụ thuộc JavaFX/third-party download manager. Không dùng `SecurityManager` làm biện pháp bảo vệ hiện đại: các ứng dụng nên tự kiểm soát đường dẫn, phân quyền hệ điều hành, quy tắc mạng và dữ liệu tải về.

## 2. Mô hình dữ liệu: `BodyHandler<Path>` và `HttpResponse<Path>`

HTTP Client dùng generic type của `BodyHandler<T>` để quyết định kiểu `T` của response body trong ứng dụng.

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;

HttpClient client = HttpClient.newHttpClient();
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/report.bin"))
        .GET()
        .build();

Path destination = Path.of("downloads", "report.bin");

// Đây là đoạn minh họa: cần URL thật và thư mục tồn tại.
HttpResponse<Path> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofFile(destination));

Path savedFile = response.body();
```

Các bước:

1. `HttpRequest` xác định request; `GET()` không mang ý nghĩa đặt tên file.
2. `BodyHandlers.ofFile(destination)` tạo handler biết **file nào** sẽ nhận response body.
3. `HttpClient.send(request, handler)` gửi request và tiêu thụ response theo handler.
4. Khi `send` trả về **thành công** với file handler, body đã được ghi đầy đủ vào file theo hợp đồng API; `response.body()` là `Path` của file được ghi.
5. `response.statusCode()` và `response.headers()` vẫn truy cập được. **Đừng coi việc có `Path` đồng nghĩa HTTP status là 200.**

`HttpResponse<Path>` không chứa byte payload dưới dạng `String`; `response.body()` không phải nội dung file và không phải "URL download", mà là **đối tượng đường dẫn** tới file local. Nếu muốn đọc nội dung sau đó, sử dụng `Files` hoặc API xử lý binary tương ứng.

### Bảng so sánh

| Đặc tính | `BodyHandlers.ofFile(file)` | `BodyHandlers.ofFileDownload(directory, options)` |
| --- | --- | --- |
| Đường dẫn caller cung cấp | **Đường dẫn file hoàn chỉnh** | **Đường dẫn thư mục** |
| Ai quyết định tên file? | Ứng dụng | Server qua `Content-Disposition` |
| Kiểu trả về của `response.body()` | `Path` | `Path` |
| Cần header `Content-Disposition`? | **Không** | **Có**: `attachment` và `filename` |
| Thư mục cha tồn tại? | Nên tạo/kiểm tra trước | **Phải** là thư mục tồn tại, ghi được |
| Cho phép thiết lập `OpenOption`? | Có overload hai đối số | Có tham số varargs |
| Khi header tải về sai/thiếu | Không phụ thuộc header đặt tên | Không xác định được tên file; request có thể thất bại |
| Rủi ro ghi đè file | Phụ thuộc target và open options | Phụ thuộc tên từ server và open options |
| Nên dùng khi | Cần tên file **do ứng dụng kiểm soát** | Chấp nhận tên do server đặt trong môi trường tin cậy/được kiểm soát |

**Lựa chọn thực tế:** Mặc định nên dùng `ofFile` với một target path do ứng dụng kiểm soát. Chọn `ofFileDownload` khi giao thức download yêu cầu lấy tên từ server và đã có chính sách xử lý tên, xung đột và quyền ghi.

## 3. `ofFile(Path file)`: chọn chính xác file đích

### 3.1. Cách dùng cơ bản

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.net.http.HttpResponse;

Path directory = Path.of("downloads").toAbsolutePath().normalize();
Files.createDirectories(directory);

Path file = directory.resolve("manual.pdf");

HttpResponse.BodyHandler<Path> handler =
        HttpResponse.BodyHandlers.ofFile(file);
```

Đây là **đoạn code nằm trong phương thức khai báo `throws IOException`**, chưa gửi request. `Files.createDirectories` bảo đảm thư mục tồn tại; nó không tự tạo file PDF. Khi gửi HTTP response thành công, file sẽ do body subscriber mở/tạo theo open options.

Nếu response là `404 Not Found`, một handler `ofFile(file)` **vẫn có thể ghi body lỗi** (ví dụ trang HTML) vào `manual.pdf`. Lý do: các predefined body handlers **không tự kiểm tra HTTP status code**. Phần sau trình bày cách chặn status trước khi ghi.

### 3.2. Bẫy cực quan trọng: mặc định **không** truncate file cũ

Theo Javadoc Java SE 11:

```java
BodyHandlers.ofFile(file)
```

tương đương:

```java
BodyHandlers.ofFile(
        file,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE)
```

Các options mặc định này **không có `TRUNCATE_EXISTING`**. Khi file đã tồn tại và body mới ngắn hơn dữ liệu cũ, việc ghi từ đầu không tự cắt bỏ byte cũ ở cuối file.

Ví dụ:

```text
File cũ:      OLD_LONG_DATA
Body mới:     FILE

Dùng ofFile(file) mặc định:
Kết quả:      FILELONG_DATA

Dùng TRUNCATE_EXISTING:
Kết quả:      FILE
```

Đây không chỉ là vấn đề thẩm mỹ: phần byte cũ còn lại có thể làm hỏng PDF, ZIP, JSON, chữ ký số hay dữ liệu nhị phân. Khi muốn **thay thế toàn bộ** một file đích, chỉ định options rõ ràng:

```java
import static java.nio.file.StandardOpenOption.CREATE;
import static java.nio.file.StandardOpenOption.TRUNCATE_EXISTING;
import static java.nio.file.StandardOpenOption.WRITE;

HttpResponse.BodyHandler<Path> replaceHandler =
        HttpResponse.BodyHandlers.ofFile(
                file, CREATE, WRITE, TRUNCATE_EXISTING);
```

Còn khi **không muốn ghi đè** file có sẵn:

```java
import static java.nio.file.StandardOpenOption.CREATE_NEW;
import static java.nio.file.StandardOpenOption.WRITE;

HttpResponse.BodyHandler<Path> newFileOnly =
        HttpResponse.BodyHandlers.ofFile(
                file, CREATE_NEW, WRITE);
```

`CREATE_NEW` yêu cầu tạo file mới và sẽ thất bại nếu file đã tồn tại. Đây thường là lựa chọn an toàn với tên file của bản tải xuống mới; tuy nhiên **không thay thế** kiểm tra đường dẫn và quyền truy cập.

### 3.3. Các `StandardOpenOption` cần biết

| Option | Tác dụng | Khi nào phù hợp? |
| --- | --- | --- |
| `CREATE` | Tạo file nếu chưa tồn tại; mở file cũ nếu đã có | Ứng dụng cho phép dùng lại đích |
| `CREATE_NEW` | Chỉ tạo khi chưa tồn tại, nếu đã có thì thất bại | Tránh vô tình ghi đè |
| `WRITE` | Mở để ghi byte | Gần như luôn cần cho download |
| `TRUNCATE_EXISTING` | Nếu file đã có, cắt chiều dài về 0 trước khi ghi | Muốn thay toàn bộ nội dung file cũ |
| `APPEND` | Ghi nối ở cuối file | Thường **không phù hợp** với một HTTP response download bình thường |
| `READ` | Mở cho mục đích đọc | Không phải lựa chọn thông thường của file body output |

Không kết hợp options không tương thích hoặc không được implementation chấp nhận: API có thể ném `IllegalArgumentException`; lỗi mở file cũng có thể báo qua `IOException` khi xử lý body. Không dựa vào việc tự thêm `APPEND` để "resume download": resume HTTP cần quản lý `Range`, `Content-Range`, ETag/If-Range, offset và sự toàn vẹn riêng; append mù quáng có thể làm hỏng file.

Lưu ý `CREATE_NEW` không phải alias của `CREATE + TRUNCATE_EXISTING`: một bên **từ chối file đã tồn tại**, bên kia **có thể xóa nội dung cũ**.

## 4. `ofFileDownload(Path directory, OpenOption...)`: lấy tên file từ server

### 4.1. Điểm khác biệt so với ofFile

```java
Path downloads = Path.of("downloads")
        .toAbsolutePath()
        .normalize();

Files.createDirectories(downloads);

HttpResponse.BodyHandler<Path> handler =
        HttpResponse.BodyHandlers.ofFileDownload(
                downloads,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE);
```

`ofFileDownload` nhận **đường dẫn thư mục**, không phải đường dẫn file. JDK xác định tên file từ header HTTP response, ví dụ:

```http
HTTP/1.1 200 OK
Content-Disposition: attachment; filename="report-2026.csv"
Content-Type: text/csv
```

Sau khi download thành công:

```java
HttpResponse<Path> response = client.send(request, handler);
Path actualFile = response.body();

// actualFile trỏ tới tệp report-2026.csv trong thư mục downloads
```

`response.body()` là nguồn xác định đường dẫn thực sự được dùng. Không nên tự giả định tất cả server đều trả tên file tương ứng với URL. Ví dụ, URL `/download?id=42` có thể trả `filename="statement.pdf"`.

### 4.2. Header `Content-Disposition` cần có gì?

Hợp đồng của `ofFileDownload` trên Java 11 yêu cầu header `Content-Disposition`:

1. Có disposition type là **`attachment`**.
2. Có tham số **`filename`**.
3. Nếu tên file chứa nhiều thành phần đường dẫn, implementation chỉ dùng **thành phần cuối** kết hợp với thư mục caller đã chỉ định.

Ví dụ hợp lệ thông thường:

```http
Content-Disposition: attachment; filename="report.txt"
```

Ví dụ không đủ theo hợp đồng:

```http
Content-Disposition: inline; filename="report.txt"
```

```http
Content-Disposition: attachment
```

Nếu thiếu/không phù hợp header bắt buộc, quá trình xử lý download sẽ thất bại thay vì tự lấy tên từ segment cuối của URL. Trong chương trình thử nghiệm, response thiếu `Content-Disposition` dẫn đến `IOException`. **Không viết ứng dụng dựa trên giả định JDK sẽ tự đặt `download.bin` hoặc tự dùng tên từ URL**.

### 4.3. Thư mục phải tồn tại và ghi được

Với `ofFileDownload`, `directory` phải trỏ tới thư mục hợp lệ, thuộc file system phù hợp với implementation, và có thể ghi; Javadoc nêu `IllegalArgumentException` cho đường dẫn thư mục không hợp lệ/không tồn tại/không ghi được ngay khi tạo handler, cũng như `IOException` nếu việc lưu tệp thất bại.

Vì vậy, tạo thư mục bằng chính ứng dụng **trước khi** gọi:

```java
Path downloads = Path.of("downloads")
        .toAbsolutePath()
        .normalize();
Files.createDirectories(downloads);
```

Không truyền `downloads.resolve("file.pdf")` cho `ofFileDownload` — đó là **file path**, không phải directory. Ngược lại, `ofFile` nhận đúng file path.

### 4.4. Chú ý bảo mật khi tin vào tên file từ HTTP header

Tên file trong `Content-Disposition` là **metadata do server gửi**, có thể khác dự kiến, trùng file hiện có, có ký tự không hợp lệ trên hệ điều hành, hoặc cố tình gây xung đột. Javadoc có quy tắc chỉ dùng thành phần cuối nếu tên có nhiều path component, nhưng điều này **không phải cơ chế kiểm chứng toàn diện** cho file không tin cậy.

Các biện pháp thích hợp:

- Chỉ tải từ endpoint/source đã được ứng dụng tin cậy và kiểm soát.
- Dùng thư mục dành riêng cho download, tránh thư mục chứa file cấu hình hoặc file thực thi quan trọng.
- Ưu tiên `CREATE_NEW` để không âm thầm ghi đè file trùng tên.
- Sau khi nhận `response.body()`, kiểm tra đường dẫn, tên file, extension, giới hạn kích thước và nội dung theo nghiệp vụ **trước khi đưa vào sử dụng**.
- Nếu cần tuyệt đối kiểm soát tên, **đừng dùng `ofFileDownload`**; hãy tự chọn tên an toàn rồi dùng `ofFile`.
- Không coi extension từ header là bằng chứng file an toàn; `.pdf`, `.csv` hay `.jpg` vẫn có thể chứa dữ liệu sai hoặc độc hại.
- Trên các nền tảng khác nhau, cách hiểu dấu slash/backslash có thể khác; không dùng regex tự viết để "chắc chắn" tái hiện cách mọi file system xử lý tên.

## 5. `Path`: tên tương đối, tuyệt đối, thư mục cha và file kết quả

`java.nio.file.Path` chỉ là **đối tượng biểu diễn đường dẫn**; tạo một `Path` không tự tạo file hoặc thư mục.

Ví dụ:

```java
Path relative = Path.of("downloads", "report.pdf");
Path absolute = relative.toAbsolutePath().normalize();

System.out.println(relative.isAbsolute()); // false
System.out.println(absolute.isAbsolute()); // true
```

Với đường dẫn tương đối, ý nghĩa phụ thuộc **working directory** của tiến trình JVM tại môi trường chạy. Trong IDE, CI, service, container hoặc hệ điều hành khác nhau, một `downloads/report.pdf` có thể chỉ vào nơi khác dự kiến.

Nếu ứng dụng có một thư mục lưu trữ đã kiểm soát:

```java
import java.nio.file.Files;
import java.nio.file.Path;

Path storageRoot = Path.of("app-data", "downloads")
        .toAbsolutePath()
        .normalize();

Files.createDirectories(storageRoot);

String safeName = "invoice-42.pdf";
Path file = storageRoot.resolve(safeName).normalize();

if (!file.getParent().equals(storageRoot)) {
    throw new IllegalArgumentException("Invalid destination");
}
```

Đây là ví dụ khi `safeName` là một **tên file đơn giản do ứng dụng quyết định**. Nếu `safeName` đến từ người dùng, cần validate chặt hơn trước khi `resolve`: không cho separator, dot segment, tên file rỗng, ký tự không hợp lệ, tên dành riêng của hệ điều hành... Kiểm tra `normalize()`/`startsWith(root)` chỉ xử lý **cú pháp đường dẫn**, chưa loại trừ symbolic link và thay đổi file system đồng thời (TOCTOU).

Dùng `response.body()` để biết file đã lưu:

```java
Path saved = response.body();

System.out.println(saved.getFileName());   // tên file
System.out.println(saved.getParent());     // thư mục cha
System.out.println(saved.toAbsolutePath().normalize());
```

Không khẳng định `response.body()` luôn tự là đường dẫn tuyệt đối; nó phản ánh đường dẫn được body handler sử dụng. `Path.getFileName()` trả **segment cuối** theo provider hiện tại, khác việc parse query hay segment của URI HTTP.

### Tên file từ URL không phải tên file trên disk

Ba khái niệm nên tách ra:

| Loại | Ví dụ | Được quyết định bởi |
| --- | --- | --- |
| Remote resource URI | `https://api.example.com/export?id=42` | Server API/HTTP request |
| `Content-Disposition filename` | `statement-42.csv` | Metadata HTTP response |
| Local output path | `/safe/downloads/statement-42.csv` | Caller chọn directory và body handler chọn file name |

Dù URI remote kết thúc bằng `/report`, `ofFileDownload` vẫn dựa vào Content-Disposition theo hợp đồng. Dù `Content-Disposition` đưa ra `report.csv`, `ofFile(customPath)` vẫn ghi vào `customPath` do caller chỉ định.

## 6. HTTP status: vì sao 404 vẫn có thể ghi thành file?

Một hiểu nhầm quan trọng: `BodyHandlers.ofFile` và `ofFileDownload` mặc định **không kiểm tra `statusCode()`**. Chúng quyết định cách tiêu thụ body, không tự diễn giải "200 là tốt, 404 là lỗi" cho ứng dụng.

Nếu server trả:

```http
HTTP/1.1 404 Not Found
Content-Type: text/plain

NOT_FOUND
```

mà caller dùng:

```java
HttpResponse<Path> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofFile(errorPath));
```

thì `response.statusCode() == 404`, nhưng file tại `errorPath` **có thể đã chứa `NOT_FOUND`**. Chỉ kiểm tra status **sau** `send` không giúp ngăn các byte lỗi đã được ghi lên disk.

Giải pháp đúng khi muốn **chỉ ghi file với status cho phép** là sử dụng `HttpResponse.BodyHandler<Path>` tùy chỉnh; handler nhận `ResponseInfo` **sau khi có headers/status nhưng trước khi body được xử lý**:

```java
import java.net.http.HttpResponse;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

// Đặt trong phương thức; destination là Path đã xác thực.
HttpResponse.BodyHandler<Path> onlySuccess = info ->
        info.statusCode() == 200
                ? HttpResponse.BodyHandlers.ofFile(
                        destination,
                        StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE).apply(info)
                : HttpResponse.BodySubscribers.replacing(
                        (Path) null);
```

- Khi status là **200**, handler sử dụng file subscriber để ghi.
- Khi status khác 200, subscriber `replacing((Path)null)` tiêu thụ/bỏ qua body và response body là `null`; **không tạo file đích** qua nhánh này.
- Sau `send`, caller **vẫn phải kiểm tra status code** và báo lỗi theo API contract.
- Nếu endpoint hợp lệ trả `201` hoặc `206`, hãy thay điều kiện `== 200` bằng một predicate phù hợp. Không mặc định `206 Partial Content` là file đầy đủ; đó là tình huống resume/range cần xử lý riêng.

Không được dùng `response.body() != null` để thay kiểm tra status trong các luồng có handler khác. HTTP status, media type và tính hợp lệ của file là các bước xác thực riêng.

## 7. Chương trình Java 11+ hoàn chỉnh, chạy offline với HTTP server nội bộ

Ví dụ sử dụng `com.sun.net.httpserver.HttpServer` để tạo server HTTP **trong máy**, không cần kết nối Internet. Đây là công cụ dựng fixture kiểm thử thuộc module chuẩn JDK `jdk.httpserver`, không phải thư viện bên ngoài, và không phải khuyến nghị sử dụng nó như production web server.

Chương trình tái hiện:

1. `ofFile` mặc định giữ byte dư của file cũ.
2. Thêm `TRUNCATE_EXISTING` giúp file bằng đúng body mới.
3. `ofFileDownload` lấy tên từ `Content-Disposition: attachment; filename="report.txt"`.
4. Thiếu header tên file gây lỗi.
5. Handler mặc định vẫn lưu body response `404`.
6. Handler tự xét status từ chối lưu body `404`.

Lưu đoạn sau thành **`ResponseToFileDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Comparator;
import java.util.stream.Stream;

public class ResponseToFileDemo {
    static void respond(HttpExchange exchange, int status,
                        String text, String contentDisposition)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        if (contentDisposition != null) {
            exchange.getResponseHeaders().add(
                    "Content-Disposition", contentDisposition);
        }
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("response-file-demo-");
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        server.createContext("/fixed",
                e -> respond(e, 200, "FILE", null));
        server.createContext("/download",
                e -> respond(e, 200, "REPORT",
                        "attachment; filename=\"report.txt\""));
        server.createContext("/missing",
                e -> respond(e, 200, "NO_HEADER", null));
        server.createContext("/error",
                e -> respond(e, 404, "NOT_FOUND", null));
        server.start();

        try {
            URI base = URI.create("http://" +
                    server.getAddress().getHostString() + ":" +
                    server.getAddress().getPort());
            HttpClient client = HttpClient.newHttpClient();
            HttpRequest fixed = HttpRequest.newBuilder(
                    base.resolve("/fixed")).GET().build();

            Path output = dir.resolve("fixed.txt");
            Files.writeString(
                    output, "OLD_LONG_DATA", StandardCharsets.UTF_8);

            HttpResponse<Path> first = client.send(
                    fixed, HttpResponse.BodyHandlers.ofFile(output));
            System.out.println("ofFileStatus=" + first.statusCode());
            System.out.println("pathMatched=" + first.body().equals(output));
            System.out.println("defaultContent=" +
                    Files.readString(output, StandardCharsets.UTF_8));

            client.send(fixed, HttpResponse.BodyHandlers.ofFile(
                    output, StandardOpenOption.CREATE,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING));
            System.out.println("truncatedContent=" +
                    Files.readString(output, StandardCharsets.UTF_8));

            HttpResponse<Path> downloaded = client.send(
                    HttpRequest.newBuilder(
                            base.resolve("/download")).GET().build(),
                    HttpResponse.BodyHandlers.ofFileDownload(
                            dir, StandardOpenOption.CREATE_NEW,
                            StandardOpenOption.WRITE));
            System.out.println("downloadName=" +
                    downloaded.body().getFileName());
            System.out.println("downloadContent=" +
                    Files.readString(
                            downloaded.body(), StandardCharsets.UTF_8));

            try {
                client.send(
                        HttpRequest.newBuilder(
                                base.resolve("/missing")).GET().build(),
                        HttpResponse.BodyHandlers.ofFileDownload(
                                dir, StandardOpenOption.CREATE_NEW,
                                StandardOpenOption.WRITE));
            } catch (IOException ex) {
                System.out.println("missingFilename=IOException");
            }

            Path errorPath = dir.resolve("error.txt");
            HttpResponse<Path> error = client.send(
                    HttpRequest.newBuilder(
                            base.resolve("/error")).GET().build(),
                    HttpResponse.BodyHandlers.ofFile(errorPath));
            System.out.println("errorStatus=" + error.statusCode());
            System.out.println("errorFileContent=" +
                    Files.readString(errorPath, StandardCharsets.UTF_8));

            Path guardedPath = dir.resolve("guarded.txt");
            HttpResponse.BodyHandler<Path> only200 = info ->
                    info.statusCode() == 200
                            ? HttpResponse.BodyHandlers.ofFile(
                                    guardedPath,
                                    StandardOpenOption.CREATE_NEW,
                                    StandardOpenOption.WRITE).apply(info)
                            : HttpResponse.BodySubscribers.replacing(
                                    (Path) null);

            HttpResponse<Path> guarded = client.send(
                    HttpRequest.newBuilder(
                            base.resolve("/error")).GET().build(),
                    only200);
            System.out.println("guardedStatus=" + guarded.statusCode());
            System.out.println("guardedFileExists=" +
                    Files.exists(guardedPath));
        } finally {
            server.stop(0);
            try (Stream<Path> paths = Files.walk(dir)) {
                paths.sorted(Comparator.reverseOrder()).forEach(p -> {
                    try {
                        Files.deleteIfExists(p);
                    } catch (IOException ex) {
                        throw new java.io.UncheckedIOException(ex);
                    }
                });
            }
        }
    }
}
```

Biên dịch/chạy bằng JDK 11 trở lên, bật module `jdk.httpserver` dùng cho fixture:

```bash
javac --release 11 --add-modules jdk.httpserver ResponseToFileDemo.java
java --add-modules jdk.httpserver ResponseToFileDemo
```

**Stdout đã kiểm chứng:**

```text
ofFileStatus=200
pathMatched=true
defaultContent=FILELONG_DATA
truncatedContent=FILE
downloadName=report.txt
downloadContent=REPORT
missingFilename=IOException
errorStatus=404
errorFileContent=NOT_FOUND
guardedStatus=404
guardedFileExists=false
```

### Phân tích kết quả

- File có dữ liệu cũ `OLD_LONG_DATA`; response mới chứa `FILE`. Với `ofFile(output)` mặc định, output là `FILELONG_DATA` do **không tự truncate**.
- Khi thêm `TRUNCATE_EXISTING`, file chỉ còn `FILE`; đây mới là lựa chọn phù hợp với hành vi thay thế file toàn bộ.
- `downloadName=report.txt` chứng minh `ofFileDownload` không lấy tên từ URL `/download` mà từ header `Content-Disposition`.
- `missingFilename=IOException` xuất hiện vì response không có metadata `attachment; filename=...` cần thiết.
- `errorStatus=404` nhưng `errorFileContent=NOT_FOUND`: predefined `ofFile` có thể lưu cả body lỗi.
- `guardedFileExists=false`: custom `BodyHandler` kiểm tra status trước khi chọn subscriber, nên với `404` không tạo file.

Ví dụ sử dụng thư mục **tạm** và xóa sau khi chạy, không để lại dữ liệu trong project. Kết quả không in đường dẫn tuyệt đối hay cổng server ngẫu nhiên, nhờ đó stdout có thể kiểm tra ổn định trên hệ thống có JDK phù hợp.

## 8. Mẫu thực tế: file do ứng dụng chọn, không ghi đè và kiểm tra trạng thái

Trong phần mềm thật, bạn thường muốn tải một file cụ thể về tên đã kiểm soát. Mẫu sau dành cho **một phương thức khai báo `throws IOException, InterruptedException`**. URL là minh họa: cần thay bằng endpoint hợp lệ của hệ thống.

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Duration;

Path storage = Path.of("app-data", "downloads")
        .toAbsolutePath()
        .normalize();
Files.createDirectories(storage);

Path target = storage.resolve("invoice-42.pdf");
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.com/invoices/42/pdf"))
        .timeout(Duration.ofSeconds(30))
        .GET()
        .build();

HttpResponse.BodyHandler<Path> handler = info ->
        info.statusCode() == 200
                ? HttpResponse.BodyHandlers.ofFile(
                        target,
                        StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE).apply(info)
                : HttpResponse.BodySubscribers.replacing((Path) null);

HttpResponse<Path> response =
        HttpClient.newHttpClient().send(request, handler);

if (response.statusCode() != 200) {
    throw new IOException("Download failed: HTTP " +
            response.statusCode());
}

Path savedFile = response.body();
// File đã được ghi hoàn tất khi send trả về thành công.
```

**Đây không phải chương trình độc lập** vì được viết như một đoạn trong phương thức và cần endpoint thực tế. Các bước an toàn đã có:

- File đích do ứng dụng xác định: `invoice-42.pdf`.
- Thư mục được tạo chủ động.
- `CREATE_NEW` từ chối file có sẵn.
- Chỉ response status `200` mới được chọn để ghi file.
- Sau `send` vẫn kiểm tra status trước khi coi request thành công.
- `Path` thực được đọc từ `response.body()`.

Tuy nhiên, mẫu chưa thay thế **xác thực nội dung**, giới hạn kích thước, kiểm tra checksum hoặc cơ chế hoàn tất file nguyên tử. Chúng là trách nhiệm cần bổ sung khi mức độ tin cậy/tầm quan trọng của dữ liệu cao.

### Nếu muốn thay thế file có sẵn

Có thể dùng:

```java
HttpResponse.BodyHandlers.ofFile(
        target,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.TRUNCATE_EXISTING);
```

Nhưng lưu ý file cũ bị truncate **trước khi** body mới tải đủ. Nếu network lỗi giữa chừng, bạn có thể mất dữ liệu cũ và để lại file mới dở dang.

**Giải pháp an toàn hơn khi dữ liệu quan trọng:** tạo một file tạm trong cùng thư mục, ghi response vào file tạm, xác thực kích thước/checksum/định dạng, rồi chuyển file tạm sang tên cuối bằng `Files.move`. Nếu yêu cầu atomic replacement, dùng `ATOMIC_MOVE` khi file system hỗ trợ; phải xử lý `AtomicMoveNotSupportedException` và chính sách fallback phù hợp. Dọn file tạm ở nhánh lỗi. Việc dùng atomic move không tự chứng minh nội dung tải về đáng tin; vẫn cần bước validation.

## 9. File không nhất thiết là text: handler ghi các byte của body

`BodyHandlers.ofFile` và `ofFileDownload` là lựa chọn phù hợp cho **binary output** như PDF, hình ảnh, archive; chúng không yêu cầu biết charset.

```text
HTTP response bytes
     |
     v
BodyHandler<Path> → filesystem file
     |
     +-- xử lý PDF/ZIP/ảnh bằng API phù hợp
     |
     +-- nếu thật sự là text: đọc bằng Charset đã được biết
```

Ví dụ chỉ khi file **đúng là text UTF-8**:

```java
String text = Files.readString(
        response.body(), java.nio.charset.StandardCharsets.UTF_8);
```

Đừng gọi `Files.readString` cho PDF/ZIP và đừng suy từ extension rằng file là text. `ofFile` **không tự động** chuyển văn bản sang UTF-8; nó không tương đương `BodyHandlers.ofString(charset)` rồi `Files.writeString`. Nó chuyển những byte của response body vào file.

Cần phân biệt thêm:

- **`Content-Type`**: media type do server công bố; dùng để quyết định parser/validation, không tự đổi tên file trong `ofFile`.
- **`Content-Disposition`**: gợi ý cơ chế hiển thị/tải file và tên; `ofFileDownload` dựa vào nó.
- **`Content-Length`**: thông tin về chiều dài body nếu server cung cấp; có thể thiếu hoặc không đáng tin khi đối diện nguồn không tin cậy.
- **`Content-Encoding`**: nếu response mang payload đã nén theo protocol, yêu cầu giải mã/giải nén có thể phụ thuộc thiết kế ứng dụng và HTTP client. Không mặc định file đã là nội dung dạng cuối chỉ vì extension.

Nếu cần giới hạn kích thước, chỉ xem `Content-Length` là một **kiểm tra ban đầu**. Một peer có thể không gửi header hoặc có dữ liệu khác so với thông tin đó. Với yêu cầu giới hạn byte nghiêm ngặt, cần subscriber/streaming pipeline có giới hạn thực tế; file handler mặc định không cung cấp sẵn quota download toàn cục.

## 10. Lỗi I/O, file dở dang và vòng đời request

### 10.1. Thành công của `send` và sự hoàn tất file

Với handler ghi file, Javadoc xác nhận: khi `HttpResponse<Path>` được trả về **bình thường**, body đã được ghi hoàn chỉnh vào file, `response.body()` là đường dẫn của file đó.

Đối với `sendAsync`:

```java
java.util.concurrent.CompletableFuture<HttpResponse<Path>> future =
        client.sendAsync(
                request, HttpResponse.BodyHandlers.ofFile(file));
```

Khi future hoàn thành bình thường và cung cấp `HttpResponse<Path>`, quy tắc kết quả file của handler tương tự. Trong khi future **chưa hoàn thành**, không coi file đang xuất hiện trên disk là một bản tải về đã hoàn chỉnh.

### 10.2. Lỗi trước hoặc giữa lúc ghi

Các vấn đề thường gặp:

- DNS/network/TLS/timeouts, kết nối reset, server đóng sớm.
- Không có quyền ghi hoặc thư mục cha chưa tồn tại.
- `CREATE_NEW` đụng file đã có; `TRUNCATE_EXISTING` làm mất dữ liệu cũ nếu tải thất bại.
- Disk đầy, file system lỗi hoặc target bị thay đổi bởi tiến trình khác.
- `ofFileDownload` không thể lấy filename từ `Content-Disposition`.
- Tệp có thể đã **được tạo hoặc ghi một phần** trước khi một `IOException`/completion failure xuất hiện.

Vì vậy, đoạn code này **không an toàn nếu chỉ tin rằng đã có file trên disk**:

```java
// KHÔNG dùng tồn tại file làm bằng chứng download thành công.
if (Files.exists(target)) {
    process(target);
}
```

Thay bằng kiểm tra trạng thái hoàn tất (response/future thành công), status, content validation, kích thước/checksum và chính sách cleanup. Với file quan trọng, dùng file tạm riêng biệt và chỉ chuyển tên sau khi đã xác minh.

### 10.3. Quyền ghi và đường dẫn

`Files.createDirectories(directory)` có thể tạo thư mục nhưng không bảo đảm chương trình được phép ghi file bên trong mãi mãi. File system permission, antivirus, quota và symlink có thể tác động ở thời điểm mở file thực.

Đừng lấy đường dẫn tuyệt đối từ HTTP response header để ghép trực tiếp vào file system nếu không có chính sách. Dù API `ofFileDownload` dùng thành phần tên cuối, ứng dụng vẫn cần giới hạn nơi ghi và đối tượng được phép tạo. Để giảm nguy cơ path traversal/overwrite, ưu tiên đặt tên file server-side hoặc app-side **theo allowlist** tại `ofFile`; dùng `CREATE_NEW` trong thư mục cô lập.

## 11. Kết hợp status, header và nội dung cho download an toàn

Một luồng xử lý download dễ bảo trì có thể chia thành bốn tầng:

1. **Request policy:** URL/host/scheme được phép, timeout hợp lý, redirects được kiểm soát.
2. **Response policy:** status có hợp lệ không? Content-Type phù hợp? Có yêu cầu `Content-Disposition` hay không?
3. **Storage policy:** output directory an toàn, tên file tin cậy, có được overwrite không, giới hạn dung lượng/loại file, cấp quyền filesystem.
4. **Completion policy:** response/future hoàn thành, file hợp lệ, checksum/số byte đúng, chuyển file tạm thành file cuối, cleanup khi lỗi.

`BodyHandler` tùy chỉnh giúp **bước 2** được thực hiện trước khi body ghi ra file:

```java
HttpResponse.BodyHandler<Path> guarded = info -> {
    int status = info.statusCode();
    String mediaType = info.headers()
            .firstValue("Content-Type")
            .orElse("");

    if (status != 200 || !mediaType.startsWith("application/pdf")) {
        return HttpResponse.BodySubscribers.replacing((Path) null);
    }

    return HttpResponse.BodyHandlers.ofFile(
            target,
            StandardOpenOption.CREATE_NEW,
            StandardOpenOption.WRITE).apply(info);
};
```

Đoạn này là **khung minh họa trong phương thức**, giả định `target` đã xác thực. Với hệ thống thật, kiểm tra Content-Type nên parse media type đầy đủ, không chỉ `startsWith` nếu cần nghiêm ngặt; content type do peer công bố cũng **không thay thế** kiểm tra byte thực. Đối với response nhiều status hợp lệ (ví dụ 201), policy phải phù hợp giao thức API.

### Các phép xác thực sau khi ghi

Sau khi thành công và trước khi phát hành file:

- Kiểm tra `Files.size(path)` với giới hạn nghiệp vụ; với file lớn giới hạn phải được áp trong lúc tải thay vì chờ đến cuối.
- Nếu có checksum/hash đáng tin cậy từ nguồn độc lập, so sánh với file đã lưu. Không coi checksum do cùng một nguồn không tin cậy cung cấp là bằng chứng duy nhất của tính xác thực.
- Xác thực định dạng binary/signature, cấu trúc PDF/ZIP/JSON... theo mục đích sử dụng.
- Không tự động thực thi hoặc mở file tải về bằng chương trình không đáng tin cậy.
- Dọn file lỗi/tạm và log đủ thông tin status, destination, nguyên nhân. Tránh log URL chứa token hoặc dữ liệu nhạy cảm.

**Không có API nào tự biến một response body chưa xác thực thành file an toàn chỉ nhờ dùng `Path`.**

## 12. `ofFile`/`ofFileDownload` so với các BodyHandler khác

| API | Kết quả | Ưu điểm | Giới hạn / dùng khi nào? |
| --- | --- | --- | --- |
| `ofFile(path)` | `HttpResponse<Path>` | Stream byte xuống file do app đặt tên | Cần tự quản lý đường dẫn, overwrite, status, cleanup |
| `ofFileDownload(directory, opts)` | `HttpResponse<Path>` | Tự lấy tên từ `Content-Disposition` | Phụ thuộc header `attachment; filename` và tên từ server |
| `ofByteArray()` | `HttpResponse<byte[]>` | Dễ kiểm tra/parse byte trong RAM | Giữ toàn bộ body trong bộ nhớ |
| `ofString(charset)` | `HttpResponse<String>` | Tiện cho response văn bản | Charset phải đúng; không phù hợp cho binary |
| `ofInputStream()` | `HttpResponse<InputStream>` | Caller có thể đọc theo luồng và tự giới hạn | Cần tự đóng InputStream, response có thể trả trước khi body nhận hết |
| `discarding()` | `HttpResponse<Void>` | Bỏ body khi không cần | Không có file/kết quả body |

Nếu cần đọc một file JSON nhỏ, `ofString(UTF_8)` có thể đơn giản. Nếu server gửi ZIP nhiều MB, `ofFile` giúp tránh việc gom một `byte[]` lớn trong RAM. Nếu cần kiểm soát byte từng phần, phát hiện header, giới hạn kích thước theo dòng dữ liệu hoặc xử lý mã hóa phức tạp, `ofInputStream` hoặc custom body subscriber có thể phù hợp.

**Đừng nhầm** `HttpRequest.BodyPublishers.ofFile(path)` với `HttpResponse.BodyHandlers.ofFile(path)`:

- `BodyPublishers.ofFile(path)` đọc file **local để gửi trong HTTP request** (upload).
- `BodyHandlers.ofFile(path)` ghi body của **HTTP response xuống file local** (download).

Tên gần giống nhưng **hướng truyền dữ liệu ngược nhau**.

## 13. Các lỗi thường gặp và cách sửa

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| File mới chứa byte thừa cuối | `ofFile(file)` mặc định chỉ `CREATE, WRITE`, không truncate | Thêm `TRUNCATE_EXISTING` hoặc tải ra file mới bằng `CREATE_NEW` |
| File có nội dung HTML lỗi nhưng tên `.pdf` | Predefined handler vẫn lưu body 404/500 | Kiểm tra status trong custom `BodyHandler` trước khi ghi |
| `ofFileDownload` không tạo file | Header thiếu `attachment` hoặc `filename`, thư mục không hợp lệ, quyền ghi lỗi | Xác minh HTTP headers, directory, permissions; dùng `ofFile` nếu cần tên app-side |
| File đích bị ghi đè ngoài ý muốn | Dùng `CREATE`/`TRUNCATE_EXISTING` với tên trùng | Dùng `CREATE_NEW` hoặc cấp tên duy nhất do app quyết định |
| `FileAlreadyExistsException` / `IOException` | `CREATE_NEW` gặp file có sẵn hoặc file system từ chối | Không ghi đè im lặng; chọn tên mới hoặc báo người dùng |
| Save vào sai thư mục | Dùng relative Path dưới working directory khác mong đợi | Anchor vào thư mục ứng dụng, dùng `toAbsolutePath().normalize()` |
| `IllegalArgumentException` khi tạo handler | Invalid options hoặc directory của `ofFileDownload` không hợp lệ | Kiểm tra combination options và `Files.isDirectory`/khả năng ghi |
| File tồn tại nhưng ứng dụng đọc không được | Download bị lỗi giữa chừng, để lại file dở dang | Chỉ dùng sau khi response/future thành công và đã xác minh |
| Kết quả `response.body()` không giống URL file | `Path` là file **local**, không phải remote URI | Dùng `Path`, `Files`; không gọi `URI.resolve` trên nó |
| Server trả tên file lạ | `ofFileDownload` tin `Content-Disposition` | Đưa vào thư mục cô lập, kiểm tra tên/định dạng, dùng `ofFile` nếu cần tên cố định |
| Tải file lớn làm đầy disk | Không có quota/giới hạn output | Áp chính sách byte limit và filesystem quota, giám sát trong lúc streaming |
| Dùng `ofFile` để upload | Nhầm BodyHandler/BodyPublisher | Upload: `HttpRequest.BodyPublishers.ofFile`; download: `HttpResponse.BodyHandlers.ofFile` |
| Trả về `HttpResponse<Path>` nhưng code mong nội dung text | Nhầm kiểu kết quả với payload | `response.body()` là `Path`; đọc text chỉ khi media type/charset phù hợp |
| Retry tải về nhưng file bị hỏng | Append/truncate mà không quản lý resume | Dùng filename tạm + retry lại từ đầu hoặc implement Range/ETag đúng protocol |

## 14. Câu hỏi tự kiểm tra (có đáp án)

**1.** `BodyHandlers.ofFile(Path.of("a.txt"))` có tự đặt tên từ header `Content-Disposition` không?

**Đáp án:** Không. File đích là `a.txt` do caller chỉ định, bất kể server gợi ý tên nào. `ofFileDownload` mới dùng tên từ header.

**2.** `ofFile(file)` mặc định dùng open options nào?

**Đáp án:** `CREATE` và `WRITE`. Mặc định **không** bao gồm `TRUNCATE_EXISTING`. Nếu file cũ dài hơn body mới, phần byte dư có thể còn lại.

**3.** Dùng `CREATE_NEW, WRITE` thì khi file đã tồn tại sẽ thế nào?

**Đáp án:** Tạo file mới thất bại; caller phải xử lý lỗi, không vô tình ghi đè dữ liệu cũ.

**4.** `ofFileDownload(dir, CREATE_NEW, WRITE)` nhận response `Content-Disposition: inline; filename="x.csv"`. Có đáp ứng hợp đồng không?

**Đáp án:** Không. Javadoc yêu cầu disposition type `attachment` cùng tham số `filename`. Không giả định nó sẽ fallback sang URL file name.

**5.** Server trả `404` với body `NOT_FOUND`. `BodyHandlers.ofFile(errorPath)` có ngăn ghi vì status không phải 200 không?

**Đáp án:** Không. Predefined body handlers không tự kiểm tra status; body lỗi có thể đã được lưu. Dùng custom `BodyHandler` để xét status trước khi chọn file subscriber.

**6.** Với `HttpResponse<Path>`, `response.body()` là gì?

**Đáp án:** Một `Path` trỏ tới file đã được ghi trên máy local theo handler, không phải `String` chứa payload hoặc URI remote.

**7.** Nếu file đã xuất hiện trong filesystem nhưng `client.send` còn đang chạy hoặc đã ném `IOException`, có nên xử lý nó ngay không?

**Đáp án:** Không. File có thể chưa hoàn chỉnh. Chỉ phát hành sau khi request hoàn thành, status hợp lệ và dữ liệu đã qua validation.

**8.** Nếu muốn lưu vào `downloads/report-42.zip` bất kể server đặt tên gì, chọn API nào?

**Đáp án:** `BodyHandlers.ofFile(Path.of("downloads", "report-42.zip"), ...)`. Tạo/kiểm tra directory trước, chọn `CREATE_NEW` hoặc truncate theo chính sách.

**9.** Nếu header `Content-Disposition` yêu cầu `attachment; filename="report.csv"`, `ofFileDownload` lưu đường dẫn nào?

**Đáp án:** Một `Path` kết hợp **thư mục caller cung cấp** với tên `report.csv`. Đường dẫn chính xác lấy từ `response.body()` khi hoàn thành.

**10.** Mặc định `ofFile` ghi body ra file dưới dạng UTF-8 text phải không?

**Đáp án:** Không. Nó ghi byte của HTTP response body; không tự biến PDF/ZIP thành text hoặc transcoding charset.

**11.** `BodyPublishers.ofFile` và `BodyHandlers.ofFile` có cùng chức năng không?

**Đáp án:** Không. Một API là nguồn dữ liệu **gửi đi** trong request, API còn lại là đích **nhận về** từ response.

**12.** Khi muốn thay thế file quan trọng và không chấp nhận file dở dang, có nên ghi trực tiếp bằng `TRUNCATE_EXISTING` không?

**Đáp án:** Thường không. Tải vào file tạm riêng, xác thực, rồi move sang đích là hướng an toàn hơn; xử lý hỗ trợ atomic move và cleanup theo file system.

## Tài liệu chuẩn hiện hành

- [Oracle Java SE 11 — `HttpResponse.BodyHandlers`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): `ofFile`, `ofFileDownload`, yêu cầu `Content-Disposition`, kiểu `Path` và quy tắc các handler mặc định không xét status.
- [Oracle Java SE 27 — `HttpResponse.BodyHandlers`](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): xác nhận các API tải file vẫn hiện hành.
- [Oracle Java SE 11 — `HttpResponse.BodyHandler`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandler.html): `ResponseInfo`, lựa chọn `BodySubscriber` dựa trên status/headers trước khi đọc body.
- [Oracle Java SE 11 — `StandardOpenOption`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/StandardOpenOption.html): `CREATE`, `CREATE_NEW`, `WRITE`, `TRUNCATE_EXISTING` và `APPEND`.
- [Oracle Java SE 11 — `Path`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Path.html): biểu diễn đường dẫn, `resolve`, `getFileName` và chuẩn hóa.
- [Oracle Java SE 11 — `Files`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html): `createDirectories`, `size`, `move`, `exists` và hoạt động I/O.
- [RFC 6266 — Use of the Content-Disposition Header Field in HTTP](https://www.rfc-editor.org/rfc/rfc6266): ý nghĩa header attachment, filename, các yêu cầu thận trọng khi áp dụng tên do bên gửi đề xuất.

**Điểm cần nhớ:** `ofFile` cho ứng dụng **kiểm soát toàn bộ file path**, còn `ofFileDownload` dùng **directory của ứng dụng + filename từ `Content-Disposition`**. Cả hai đều trả `HttpResponse<Path>` sau khi file được ghi hoàn chỉnh nếu response xử lý thành công. Luôn đặt open options có chủ đích, kiểm tra status trước khi ghi khi cần, giữ output trong thư mục tin cậy và xác thực file trước khi sử dụng.