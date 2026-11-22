# Quản lý luồng đọc phản hồi theo vòng đời tài nguyên trong Java 17

Khi một chương trình Java gửi yêu cầu HTTP và nhận phản hồi dưới dạng luồng byte, việc nhận được đối tượng phản hồi chưa có nghĩa là toàn bộ nội dung đã được đọc. Ứng dụng vẫn phải tiêu thụ hoặc đóng luồng phản hồi đúng lúc để giải phóng tài nguyên, tránh giữ kết nối và tránh rò rỉ tài nguyên khi có lỗi.

Trong Java 17, cách phổ biến để thực hiện HTTP là dùng `java.net.http.HttpClient`. Với `HttpResponse.BodyHandlers.ofInputStream()`, body của phản hồi được cung cấp dưới dạng `InputStream`. **Ứng dụng sở hữu trách nhiệm đóng stream này** sau khi đọc xong hoặc quyết định bỏ phần còn lại.

Bài học tập trung vào vòng đời của response body, cách dùng `try-with-resources`, xử lý phản hồi thành công và lỗi, đọc dữ liệu có giới hạn, chuyển byte thành văn bản đúng charset, và quản lý stream trong luồng xử lý bất đồng bộ.

## 1. Một HTTP response gồm những phần nào?

Một phản hồi HTTP có thể hình dung gồm:

- **Status code:** cho biết kết quả ở mức giao thức, ví dụ `200`, `404`, `500`.
- **Headers:** metadata như `Content-Type`, `Content-Length`, `Cache-Control`.
- **Body:** dữ liệu phản hồi, có thể là JSON, văn bản, ảnh, file hoặc nội dung nhị phân.

Trong Java 17, `HttpResponse<T>` chứa status, headers, request liên quan và body có kiểu `T` do `BodyHandler<T>` quyết định.

Ví dụ, nếu dùng `BodyHandlers.ofString()`, body là `String`; nếu dùng `BodyHandlers.ofByteArray()`, body là `byte[]`; nếu dùng `BodyHandlers.ofInputStream()`, body là `InputStream`.

~~~java
HttpResponse<String> textResponse =
        client.send(request, HttpResponse.BodyHandlers.ofString());

HttpResponse<byte[]> binaryResponse =
        client.send(request, HttpResponse.BodyHandlers.ofByteArray());

HttpResponse<InputStream> streamResponse =
        client.send(request, HttpResponse.BodyHandlers.ofInputStream());
~~~

Ba cách trên có đặc điểm vòng đời khác nhau. `String` và `byte[]` đã được handler thu thập thành dữ liệu trong bộ nhớ trước khi trả response. Với `InputStream`, ứng dụng nhận một stream để tự đọc và đóng.

## 2. BodyHandlers.ofInputStream và trách nhiệm đóng stream

`HttpResponse.BodyHandlers.ofInputStream()` phù hợp khi:

- Body có thể lớn và không muốn nạp toàn bộ vào RAM.
- Muốn đọc dữ liệu theo từng phần.
- Muốn chuyển body trực tiếp sang một file hoặc một parser dạng stream.
- Muốn kiểm soát cách đọc, giới hạn dữ liệu hoặc xử lý nội dung theo tiến trình.

Ví dụ tối thiểu:

~~~java
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class HttpStreamDemo {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com"))
                .GET()
                .build();

        HttpResponse<InputStream> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofInputStream());

        try (InputStream body = response.body()) {
            byte[] firstBytes = body.readNBytes(128);
            System.out.println("Status: " + response.statusCode());
            System.out.println("Read bytes: " + firstBytes.length);
        }
    }
}
~~~

`try-with-resources` đảm bảo `body.close()` được gọi khi khối kết thúc bình thường hoặc khi có exception. Đây là cách đơn giản để bảo đảm luồng không bị bỏ quên.

Không nên viết:

~~~java
HttpResponse<InputStream> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofInputStream());

InputStream body = response.body();
byte[] data = body.readAllBytes();
// Quên body.close()
~~~

Nếu không đóng body sau khi dùng, ứng dụng có thể giữ tài nguyên liên quan đến việc truyền response lâu hơn cần thiết. Điều này đặc biệt đáng chú ý khi service xử lý nhiều request, response lớn hoặc nhiều lần đọc bị lỗi giữa chừng.

## 3. Vòng đời tài nguyên từ lúc gửi request đến lúc đóng body

Với `ofInputStream()`, luồng công việc thường là:

~~~text
Tạo HttpClient / HttpRequest
          |
          v
Gửi request
          |
          v
Nhận status và headers
          |
          v
BodyHandler cung cấp InputStream
          |
          v
Ứng dụng đọc body theo nhu cầu
          |
          +---- Đọc hết body
          |
          +---- Dừng sớm / gặp lỗi
          |
          v
Đóng InputStream trong mọi trường hợp
          |
          v
Kết thúc xử lý response
~~~

Điểm quan trọng là **response body có vòng đời riêng**. Đối tượng `HttpResponse` không phải tài nguyên cần đóng; stream ở `response.body()` mới là tài nguyên mà ứng dụng phải quản lý.

Khi body đã đọc hết, đóng stream vẫn là cách kết thúc vòng đời rõ ràng. Nếu chỉ đọc một phần, đóng stream báo cho implementation rằng ứng dụng không cần tiếp tục tiêu thụ body. Việc implementation có tái sử dụng kết nối vật lý hay phải bỏ kết nối/stream còn phụ thuộc giao thức và implementation; không nên dựa vào một giả định cụ thể để bỏ qua việc đóng.

## 4. Dùng try-with-resources khi đọc toàn bộ body

Nếu body có kích thước nhỏ và đã có giới hạn đáng tin cậy, có thể đọc hết vào byte array:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class ReadAllBodyDemo {
    public static void main(String[] args)
            throws IOException, InterruptedException {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/data"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<InputStream> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofInputStream());

        try (InputStream body = response.body()) {
            byte[] bytes = body.readAllBytes();
            System.out.println("Status: " + response.statusCode());
            System.out.println("Body size: " + bytes.length);
        }
    }
}
~~~

`readAllBytes()` đọc đến EOF và tạo một mảng chứa toàn bộ dữ liệu. Cách này dễ dùng nhưng cần cân nhắc kích thước body: nếu server gửi dữ liệu rất lớn hoặc không giới hạn, mảng có thể tiêu tốn nhiều bộ nhớ hoặc gây `OutOfMemoryError`.

`connectTimeout` giới hạn thời gian thiết lập kết nối. `HttpRequest.timeout` đặt thời hạn cho request theo hợp đồng API, nhưng với body handler trả `InputStream`, ứng dụng cần chú ý rằng việc đọc stream có thể tiếp tục sau khi response và headers đã được giao cho caller. Không coi request timeout là giới hạn tài nguyên hoặc giới hạn dung lượng cho toàn bộ quá trình tiêu thụ body.

## 5. Xử lý status code và vẫn đóng body

HTTP status không tự động biến thành exception khi dùng `HttpClient.send`. Một response `404` hoặc `500` vẫn có thể được trả về bình thường. Ứng dụng phải kiểm tra `statusCode()` và quyết định đọc body lỗi hay bỏ qua.

Điều quan trọng: **dù status thành công hay thất bại, nếu đã nhận `InputStream` thì phải đóng stream**.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

public class StatusAndBodyDemo {
    public static void main(String[] args)
            throws IOException, InterruptedException {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/api/items"))
                .GET()
                .build();

        HttpResponse<InputStream> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofInputStream());

        try (InputStream body = response.body()) {
            int status = response.statusCode();

            if (status >= 200 && status < 300) {
                byte[] bytes = body.readAllBytes();
                System.out.println("Success, bytes: " + bytes.length);
            } else {
                byte[] errorBytes = body.readNBytes(4096);
                String errorText =
                        new String(errorBytes, StandardCharsets.UTF_8);

                throw new IOException(
                        "HTTP " + status + ": " + errorText);
            }
        }
    }
}
~~~

Nhánh lỗi chỉ đọc tối đa 4096 byte để tạo thông tin chẩn đoán, sau đó ném exception. Khi exception thoát khỏi khối `try`, stream vẫn được đóng.

Trong ứng dụng thật, status code nào được xem là thành công phụ thuộc hợp đồng API. Không phải mọi endpoint đều chỉ dùng `2xx`; ví dụ một số luồng có thể coi `304 Not Modified` là kết quả bình thường. Hãy định nghĩa chính sách theo API đang gọi.

## 6. Đọc body theo từng phần và giới hạn dung lượng

Khi nhận dữ liệu từ mạng, không nên mặc định body có kích thước nhỏ. Header `Content-Length` có thể không có, có thể không đáng tin hoặc body có thể được truyền theo cơ chế không cung cấp trước kích thước cuối cùng.

Để giới hạn dung lượng, có thể đọc tối đa `MAX_BYTES + 1` byte. Nếu nhận nhiều hơn giới hạn, từ chối:

~~~java
import java.io.IOException;
import java.io.InputStream;

static byte[] readAtMost(InputStream input, int maxBytes)
        throws IOException {
    if (maxBytes < 0 || maxBytes == Integer.MAX_VALUE) {
        throw new IllegalArgumentException("Invalid maxBytes");
    }

    byte[] bytes = input.readNBytes(maxBytes + 1);
    if (bytes.length > maxBytes) {
        throw new IOException("Response body exceeds size limit");
    }
    return bytes;
}
~~~

Sử dụng:

~~~java
private static final int MAX_RESPONSE_BYTES = 1_000_000;

try (InputStream body = response.body()) {
    byte[] data = readAtMost(body, MAX_RESPONSE_BYTES);
    process(data);
}
~~~

Nếu body vượt giới hạn, exception được ném ra nhưng `try-with-resources` vẫn đóng stream. Cách đọc này chỉ lấy tối đa một byte vượt ngưỡng để phát hiện body quá lớn; phần còn lại sẽ không được tiêu thụ.

Với body lớn nhưng cần xử lý đầy đủ, hãy đọc theo buffer và đếm tổng byte bằng `long`:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;

static byte[] readBounded(InputStream input, long maxBytes)
        throws IOException {
    if (maxBytes < 0) {
        throw new IllegalArgumentException("maxBytes must be non-negative");
    }

    ByteArrayOutputStream output = new ByteArrayOutputStream();
    byte[] buffer = new byte[8192];
    long total = 0;

    int count;
    while ((count = input.read(buffer)) != -1) {
        total += count;
        if (total > maxBytes) {
            throw new IOException("Response body exceeds size limit");
        }
        output.write(buffer, 0, count);
    }

    return output.toByteArray();
}
~~~

Ví dụ này vẫn giữ toàn bộ body trong RAM, vì vậy chỉ phù hợp khi giới hạn đủ nhỏ. Nếu dữ liệu lớn, hãy ghi từng buffer ra file hoặc xử lý trực tiếp thay vì gom vào `ByteArrayOutputStream`.

## 7. Stream body trực tiếp ra file

Khi tải file, tránh nạp toàn bộ response vào một `byte[]`. Có thể sao chép stream sang file theo buffer:

~~~java
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class DownloadDemo {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/archive.bin"))
                .GET()
                .build();

        HttpResponse<InputStream> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofInputStream());

        Path destination = Path.of("archive.bin");

        try (InputStream body = response.body()) {
            if (response.statusCode() != 200) {
                throw new IllegalStateException(
                        "Unexpected HTTP status: " + response.statusCode());
            }

            Files.copy(
                    body,
                    destination,
                    StandardCopyOption.REPLACE_EXISTING);
        }
    }
}
~~~

`Files.copy(InputStream, Path, ...)` đọc stream đến EOF hoặc khi có lỗi. `try-with-resources` vẫn cần thiết để đóng body sau khi copy xong hoặc thất bại.

Trong ứng dụng tải file quan trọng, nên ghi vào file tạm rồi đổi tên sau khi tải và xác thực thành công. Cách đó tránh để lại một file đích có vẻ hoàn chỉnh nhưng thực tế chỉ chứa một phần dữ liệu. Cũng cần áp dụng giới hạn kích thước, kiểm tra checksum/chữ ký nếu giao thức yêu cầu và xử lý trường hợp đĩa đầy.

## 8. Chuyển response body thành văn bản đúng charset

HTTP body là byte. Nếu nội dung là văn bản, ứng dụng phải biết charset theo hợp đồng response, thường được mô tả trong `Content-Type`, ví dụ `text/plain; charset=UTF-8`.

Khi API quy định UTF-8, hãy dùng `StandardCharsets.UTF_8`:

~~~java
import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

try (InputStream body = response.body();
     BufferedReader reader = new BufferedReader(
             new InputStreamReader(body, StandardCharsets.UTF_8))) {

    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
~~~

Ở đây cả `body` và `reader` đều được khai báo trong try-with-resources. `BufferedReader.close()` sẽ đóng reader bên dưới và stream; việc khai báo cả hai có thể khiến stream được close thêm lần nữa. Thông thường `InputStream.close()` được thiết kế để gọi lặp lại an toàn, nhưng có thể viết gọn hơn bằng cách chỉ quản lý reader:

~~~java
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(
                response.body(),
                StandardCharsets.UTF_8))) {
    String line;
    while ((line = reader.readLine()) != null) {
        processLine(line);
    }
}
~~~

Reader sở hữu stream được bọc bên trong và đóng nó khi kết thúc.

Nếu charset do server cung cấp và ứng dụng cần tuân thủ header, hãy parse `Content-Type` theo chính sách API. Không nên lấy `Charset.defaultCharset()` của máy client làm charset mặc định cho một giao thức đã quy định encoding.

## 9. BodyHandlers khác nhau và hệ quả về vòng đời

`HttpResponse.BodyHandlers` có nhiều lựa chọn. Hãy chọn theo kích thước và cách sử dụng body:

| Body handler | Kiểu body | Đặc điểm vòng đời |
| --- | --- | --- |
| `ofString()` | `String` | Handler đọc body và tạo chuỗi trước khi response hoàn tất; không có stream body để caller đóng. |
| `ofByteArray()` | `byte[]` | Đọc toàn bộ body vào RAM; phù hợp payload nhỏ, có giới hạn. |
| `ofInputStream()` | `InputStream` | Caller đọc và phải đóng stream. Phù hợp streaming hoặc body lớn. |
| `ofFile(path)` | `Path` | Handler ghi body vào file; caller quản lý file sau khi response hoàn tất. |
| `discarding()` | `Void` | Bỏ body khi nội dung không cần dùng. |

### 9.1. Khi dùng ofString

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString());

System.out.println(response.body());
~~~

Không cần đóng một body stream vì body là `String`. Tuy nhiên, toàn bộ nội dung được giữ trong bộ nhớ; đừng dùng cách này cho response có thể rất lớn.

Nếu cần chỉ định charset:

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
~~~

### 9.2. Khi dùng ofByteArray

~~~java
HttpResponse<byte[]> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofByteArray());

byte[] body = response.body();
~~~

Body đã được thu thập vào mảng. Caller không có stream để đóng, nhưng phải kiểm soát kích thước response để tránh dùng bộ nhớ không giới hạn.

### 9.3. Khi dùng ofFile

~~~java
HttpResponse<Path> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofFile(Path.of("download.bin")));
~~~

Handler ghi nội dung vào file và response body là đường dẫn. Tài nguyên file stream nội bộ được handler quản lý; sau đó ứng dụng chịu trách nhiệm quản lý file đã tạo, bao gồm xóa file tạm nếu xử lý thất bại hoặc dữ liệu không hợp lệ.

### 9.4. Khi dùng discarding

Nếu chỉ cần status/header mà không cần body:

~~~java
HttpResponse<Void> response = client.send(
        request,
        HttpResponse.BodyHandlers.discarding());
~~~

Handler chủ động bỏ body thay cho việc giao một stream cho caller. Đây là lựa chọn rõ ràng hơn khi ứng dụng không cần nội dung phản hồi.

## 10. Đóng stream khi có exception hoặc đọc dở

Vòng đời tài nguyên phải đúng trong cả trường hợp thành công và thất bại. Các lỗi có thể xảy ra trong khi đọc:

- Server đóng kết nối trước khi gửi hết body.
- Mạng bị ngắt.
- Dữ liệu không đúng định dạng.
- Parser ném exception.
- Ứng dụng quyết định dừng vì body quá lớn.
- File đích không ghi được hoặc hết dung lượng.

`try-with-resources` đóng stream ngay cả khi phần thân khối ném exception:

~~~java
try (InputStream body = response.body()) {
    byte[] data = body.readNBytes(4096);
    parse(data); // Nếu parse ném exception, body vẫn được đóng.
}
~~~

Không nên đóng stream chỉ ở cuối đường chạy thành công:

~~~java
InputStream body = response.body();
byte[] data = body.readAllBytes();
parse(data);
body.close(); // Không chạy nếu readAllBytes hoặc parse ném exception.
~~~

Nếu không thể dùng try-with-resources vì API cũ, dùng `finally` để đóng. Nhưng với Java 17, try-with-resources thường là cách rõ ràng và ít lỗi hơn.

## 11. sendAsync và quản lý body bất đồng bộ

`HttpClient.sendAsync()` trả về `CompletableFuture`. Khi dùng `ofInputStream()`, future hoàn tất khi response body handler cung cấp `HttpResponse<InputStream>`; việc đọc stream có thể diễn ra sau đó.

Ví dụ:

~~~java
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.concurrent.CompletableFuture;

public class AsyncStreamDemo {
    public static void main(String[] args) {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/data"))
                .GET()
                .build();

        CompletableFuture<HttpResponse<InputStream>> future =
                client.sendAsync(
                        request,
                        HttpResponse.BodyHandlers.ofInputStream());

        future.thenAccept(response -> {
            try (InputStream body = response.body()) {
                byte[] data = body.readAllBytes();
                System.out.println("Status: " + response.statusCode());
                System.out.println("Bytes: " + data.length);
            } catch (Exception e) {
                System.err.println("Could not read response: " + e);
            }
        });
    }
}
~~~

Điều cần nhớ:

- Khi future đã hoàn tất và trả response, caller nhận trách nhiệm đóng `response.body()`.
- Nếu xử lý body bất đồng bộ, stream phải được đóng trong chính callback hoặc thành phần nhận quyền sở hữu stream.
- Không trả stream ra ngoài mà không quy định ai sở hữu và ai đóng.
- Nếu callback không chạy vì future bị hủy hoặc hoàn tất lỗi trước khi có response, không có body stream để caller đóng.
- Nếu callback đã nhận response rồi nhưng xử lý bị bỏ qua, vẫn phải đóng body.

### 11.1. Tránh đọc stream blocking trên completion thread

Đọc `InputStream` có thể chặn thread cho tới khi có byte hoặc EOF. Nếu callback chạy trên thread dùng để hoàn tất future, thực hiện một thao tác đọc lâu hoặc xử lý nặng ngay trong callback có thể ảnh hưởng các tác vụ khác.

Có thể chuyển phần xử lý sang executor riêng:

~~~java
ExecutorService bodyExecutor = Executors.newFixedThreadPool(4);

CompletableFuture<Void> processing = future.thenAcceptAsync(response -> {
    try (InputStream body = response.body()) {
        processStream(body);
    } catch (IOException e) {
        throw new UncheckedIOException(e);
    }
}, bodyExecutor);
~~~

Trong ứng dụng thật, executor cũng có vòng đời riêng và phải được quản lý/đóng theo API của nó. Không tạo một executor mới cho mỗi request rồi bỏ quên. Cũng cần xử lý exception của `CompletableFuture` ở nơi gọi để lỗi không bị bỏ qua.

## 12. Hủy request và hủy đọc body

Hủy một `CompletableFuture` hoặc ngừng chờ kết quả không đồng nghĩa mọi tài nguyên liên quan tự động được giải phóng trong mọi thời điểm. Cần phân biệt:

1. **Trước khi có response:** request/future có thể bị hủy; implementation sẽ xử lý việc dừng trao đổi theo khả năng của giao thức.
2. **Sau khi đã nhận response có InputStream:** caller đang sở hữu stream và phải đóng stream khi không đọc tiếp.
3. **Trong khi đang đọc:** đóng stream là tín hiệu kết thúc việc tiêu thụ body; thao tác đọc có thể kết thúc bằng EOF hoặc exception tùy tình trạng truyền dữ liệu.

Nếu ứng dụng có deadline hoặc cancellation token riêng, cần truyền trạng thái hủy vào lớp đọc và bảo đảm nhánh hủy đóng stream. Đừng chỉ bỏ tham chiếu tới body rồi mong garbage collector đóng tài nguyên đúng lúc.

## 13. Timeout: kết nối, request và đọc stream

Java 17 `HttpClient` cung cấp một số cấu hình timeout:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .build();

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com"))
        .timeout(Duration.ofSeconds(15))
        .GET()
        .build();
~~~

Phân biệt:

| Cấu hình | Ý nghĩa |
| --- | --- |
| `HttpClient.Builder.connectTimeout(...)` | Giới hạn thời gian thiết lập kết nối. |
| `HttpRequest.Builder.timeout(...)` | Thời hạn cho request theo hợp đồng API; quá hạn có thể dẫn đến `HttpTimeoutException`. |
| Deadline đọc body của ứng dụng | Giới hạn tổng thời gian hoặc thời lượng chờ trong giai đoạn tiêu thụ stream; cần thiết kế ở tầng ứng dụng nếu yêu cầu cụ thể. |

Với `ofInputStream()`, response có thể được giao cho caller trước khi caller đọc hết body. Vì thế, không được xem request timeout là cơ chế giới hạn số byte hoặc là bảo đảm duy nhất rằng mọi lần `InputStream.read()` sau đó sẽ hoàn tất trong cùng khoảng thời gian.

Nếu body có thể kéo dài, cần kết hợp giới hạn kích thước, deadline nghiệp vụ, cơ chế hủy và đóng stream. Với yêu cầu timeout rất cụ thể cho từng lần đọc, cân nhắc kiến trúc streaming/`BodySubscriber` phù hợp thay vì dựa vào một timeout duy nhất.

## 14. HttpClient có cần đóng như InputStream không?

Trong Java 17, `HttpClient` không triển khai `AutoCloseable` và không có phương thức `close()` như các API được bổ sung ở các JDK mới hơn. Vì vậy, không viết:

~~~java
try (HttpClient client = HttpClient.newHttpClient()) {
    // Không hợp lệ với API Java 17.
}
~~~

Thông thường, tạo một `HttpClient` và tái sử dụng nó cho nhiều request thay vì tạo client mới cho từng request. Client là đối tượng bất biến, có thể được chia sẻ giữa nhiều request; việc tái sử dụng cũng cho phép implementation quản lý connection pooling hiệu quả.

Điều này không làm thay đổi trách nhiệm đóng body stream. Trong Java 17:

- Tái sử dụng `HttpClient`.
- Đóng `InputStream` body do `ofInputStream()` trả về.
- Đóng file, reader, writer hoặc tài nguyên khác do ứng dụng trực tiếp mở.
- Không cố gọi `close()` trên `HttpClient` theo API của các phiên bản Java mới hơn khi code mục tiêu là Java 17.

## 15. Đọc body trong khi vẫn kiểm tra Content-Length

Header `Content-Length` có thể giúp ứng dụng từ chối response quá lớn sớm:

~~~java
long declaredLength = response.headers()
        .firstValueAsLong("Content-Length")
        .orElse(-1L);

if (declaredLength > MAX_RESPONSE_BYTES) {
    try (InputStream body = response.body()) {
        // Đóng body ngay vì không chấp nhận payload này.
    }
    throw new IOException("Response is too large");
}
~~~

Nhưng không được chỉ dựa vào `Content-Length`:

- Header có thể không có.
- Giá trị có thể không đáng tin.
- Cách truyền body có thể không cung cấp độ dài trước.
- Dữ liệu thực tế vẫn cần được đếm khi đọc.

Vì vậy, dùng header như một kiểm tra sớm, rồi vẫn giới hạn byte thực đọc. Nếu từ chối response sau khi nhận body stream, hãy đóng stream trước khi thoát.

## 16. Xử lý lỗi khi đọc và phân biệt lỗi HTTP với lỗi truyền tải

Có hai nhóm lỗi khác nhau:

**Lỗi ở tầng HTTP:** server trả status như `400`, `401`, `404`, `500`. Đây vẫn là một response hợp lệ ở mức HTTP; caller kiểm tra status và quyết định đọc body thông tin lỗi.

**Lỗi ở tầng truyền tải/đọc:** DNS thất bại, kết nối bị từ chối, timeout, kết nối bị ngắt hoặc đọc stream thất bại. Các trường hợp này có thể phát sinh `IOException`, `HttpTimeoutException` hoặc exception liên quan.

Ví dụ:

~~~java
try {
    HttpResponse<InputStream> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofInputStream());

    try (InputStream body = response.body()) {
        if (response.statusCode() != 200) {
            throw new IOException(
                    "Unexpected status: " + response.statusCode());
        }
        processStream(body);
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IOException("HTTP request was interrupted", e);
}
~~~

Nếu thread bị interrupt khi chờ `send`, hãy khôi phục interrupt status bằng `Thread.currentThread().interrupt()` trước khi chuyển tiếp exception hoặc kết thúc xử lý. Đừng nuốt `InterruptedException` rồi tiếp tục chạy như thể không có yêu cầu hủy.

## 17. Những lỗi quản lý tài nguyên thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Quên đóng `response.body()` | Giữ tài nguyên truyền tải lâu hơn cần thiết | Dùng try-with-resources. |
| Chỉ đóng stream ở cuối nhánh thành công | Exception có thể khiến lệnh close không chạy | Đặt stream trong try-with-resources ngay sau khi nhận response. |
| Đọc body lỗi nhưng không đóng | Tài nguyên bị giữ khi server trả status không thành công | Đóng body cả trong nhánh lỗi. |
| Dùng `readAllBytes()` với body không giới hạn | Có thể tiêu tốn quá nhiều RAM | Đặt giới hạn hoặc xử lý theo buffer/ghi file. |
| Bỏ qua stream sau khi đọc một phần | Body còn lại không được tiêu thụ | Đóng stream khi quyết định dừng. |
| Chuyển stream sang callback khác mà không bàn giao quyền sở hữu | Không rõ thành phần nào phải đóng | Quy định rõ owner và đóng trong callback nhận stream. |
| Dùng charset mặc định để đọc body văn bản | Nội dung có thể sai giữa môi trường | Theo `Content-Type`/hợp đồng API và chỉ định charset. |
| Nghĩ `HttpClient` Java 17 cần đóng như stream | Dùng API không có ở Java 17 | Tái sử dụng client; đóng response body và tài nguyên ứng dụng sở hữu. |
| Chỉ tin `Content-Length` | Không giới hạn được body khi header thiếu hoặc sai | Đếm byte thực tế trong lúc đọc. |
| Nuốt `InterruptedException` | Mất tín hiệu hủy từ thread quản lý | Khôi phục interrupt status hoặc truyền tiếp exception. |

## 18. Mẫu triển khai: đọc JSON response có giới hạn và đóng đúng vòng đời

Ví dụ sau kết hợp kiểm tra status, giới hạn dung lượng, charset UTF-8 và đóng body:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class BoundedJsonClient {
    private static final int MAX_BODY_BYTES = 1_000_000;

    private final HttpClient client;

    public BoundedJsonClient() {
        this.client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();
    }

    public String getJson(URI uri)
            throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(uri)
                .timeout(Duration.ofSeconds(15))
                .header("Accept", "application/json")
                .GET()
                .build();

        HttpResponse<InputStream> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofInputStream());

        try (InputStream body = response.body()) {
            if (response.statusCode() < 200
                    || response.statusCode() >= 300) {
                byte[] errorBytes = body.readNBytes(4096);
                String error = new String(
                        errorBytes,
                        StandardCharsets.UTF_8);
                throw new IOException(
                        "HTTP " + response.statusCode() + ": " + error);
            }

            byte[] bytes = body.readNBytes(MAX_BODY_BYTES + 1);
            if (bytes.length > MAX_BODY_BYTES) {
                throw new IOException("JSON response exceeds size limit");
            }

            return new String(bytes, StandardCharsets.UTF_8);
        }
    }
}
~~~

Lớp giữ một `HttpClient` để tái sử dụng. Mỗi lần gọi `getJson`, request nhận một response body stream mới; khối try-with-resources đảm bảo stream đó được đóng dù status lỗi, body quá lớn hay xử lý thành công.

Ví dụ giả định endpoint trả JSON UTF-8. Trong hệ thống thật, cần xác thực `Content-Type`, chính sách charset, schema JSON và status code được chấp nhận. Nếu body có thể lớn hơn giới hạn, code từ chối sau khi đọc tối đa thêm một byte để phát hiện vượt ngưỡng.

## 19. Câu hỏi tự kiểm tra

**1. Với `BodyHandlers.ofInputStream()`, ai chịu trách nhiệm đóng body stream?**  
Caller nhận `HttpResponse<InputStream>` chịu trách nhiệm đóng `response.body()` sau khi đọc xong hoặc dừng đọc.

**2. Vì sao nên dùng try-with-resources?**  
Vì stream được đóng cả khi khối kết thúc bình thường lẫn khi có exception.

**3. `HttpResponse` có phải tài nguyên cần gọi `close()` không?**  
Không. Với body kiểu `InputStream`, tài nguyên cần đóng là stream trong `response.body()`.

**4. HTTP status 404 có khiến `HttpClient.send` tự ném exception không?**  
Không. Nó thường trả một response có status 404; ứng dụng phải kiểm tra status và xử lý body.

**5. Khi nào `ofString()` hoặc `ofByteArray()` phù hợp hơn `ofInputStream()`?**  
Khi body nhỏ, có giới hạn và muốn nhận dữ liệu đã thu thập hoàn chỉnh; chúng không giao stream body cho caller.

**6. Vì sao không nên gọi `readAllBytes()` với body không giới hạn?**  
Vì toàn bộ body được giữ trong RAM và có thể gây áp lực bộ nhớ hoặc `OutOfMemoryError`.

**7. Nếu chỉ đọc một phần body rồi dừng thì sao?**  
Đóng stream ngay khi quyết định dừng; không bỏ stream đang mở.

**8. Có thể dựa hoàn toàn vào Content-Length để giới hạn response không?**  
Không. Header có thể thiếu hoặc không đáng tin; cần giới hạn số byte thực đọc.

**9. Với `sendAsync` và `ofInputStream`, khi nào caller đóng stream?**  
Sau khi future trả response và callback/consumer nhận quyền sở hữu body; đóng stream trong thành phần đó.

**10. `HttpClient` Java 17 có cần dùng try-with-resources không?**  
Không. `HttpClient` trong Java 17 không triển khai `AutoCloseable`; hãy tái sử dụng client và quản lý riêng các body stream.

**11. `HttpRequest.timeout` có phải giới hạn dung lượng body không?**  
Không. Timeout và giới hạn byte là hai chính sách riêng; ứng dụng phải kiểm soát dung lượng khi đọc.

**12. Vì sao cần chỉ định charset khi đọc response văn bản?**  
Body là byte; charset phải khớp hợp đồng API để giải mã đúng, không phụ thuộc charset mặc định của máy.

## Tài liệu tham khảo chính thức

- [Java SE 17 API — `HttpClient`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): gửi request đồng bộ/bất đồng bộ và cấu hình client.
- [Java SE 17 API — `HttpResponse`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): status, headers và body của response.
- [Java SE 17 API — `HttpResponse.BodyHandlers`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): các body handler như `ofString`, `ofByteArray`, `ofInputStream`, `ofFile` và `discarding`.
- [Java SE 17 API — `InputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): đọc byte, `readNBytes`, `readAllBytes`, `transferTo` và đóng stream.
- [Java SE 17 API — `Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): sao chép stream ra file và quản lý file.
- [Java SE 17 API — `StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): charset chuẩn để giải mã văn bản.
