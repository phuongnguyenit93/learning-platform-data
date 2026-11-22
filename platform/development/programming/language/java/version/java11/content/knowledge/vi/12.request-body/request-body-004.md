# Java 11 — ofByteArrays và nhiều phần dữ liệu

**Chủ đề:** Java 11 → Request body. Bài học tập trung vào `HttpRequest.BodyPublishers.ofByteArrays(Iterable<byte[]>)`: gửi một HTTP request body từ nhiều mảng byte, hiểu thứ tự dữ liệu, vòng đời của `Iterable`, giới hạn bộ nhớ, cách gửi lại request khi cần, việc mã hóa UTF-8 và sự khác nhau giữa **nhiều đoạn byte** với định dạng **multipart/form-data**. Chỉ sử dụng API được hỗ trợ trên Java 11 và các nguyên tắc còn áp dụng hiện nay, không sử dụng API incubator cũ hoặc giả định có phương thức chỉ ra đời ở Java mới hơn.

**Mục tiêu:** Sau bài, người học có thể tạo request POST từ nhiều `byte[]`, giải thích vì sao server nhận một body nối liên tục, xử lý `Content-Type` và độ dài nội dung đúng cách, thiết kế dữ liệu có thể phát lại cho redirect/authentication/retry, kiểm thử bằng HTTP server cục bộ và chọn API khác khi upload file lớn.

## 1. Request body và BodyPublisher là gì?

Một HTTP request có thể có **method**, **URI**, **headers** và **body**. Body là chuỗi **byte** biểu diễn payload, ví dụ văn bản UTF-8, JSON, dữ liệu nhị phân hoặc multipart theo hợp đồng giữa client và server.

Trong Java 11, module chuẩn `java.net.http` cung cấp:

- `HttpClient` để gửi request và nhận response; có thể gọi `send` đồng bộ hoặc `sendAsync` bất đồng bộ.
- `HttpRequest` để mô tả method, URI, headers, thời gian chờ và body.
- `HttpRequest.BodyPublisher` để phát dữ liệu body ra các `ByteBuffer` cho HTTP client tiêu thụ.
- `HttpRequest.BodyPublishers` chứa các factory tạo publisher cho String, mảng byte, tệp, input stream và nhiều mảng byte.
- `HttpResponse.BodyHandlers` để xác định cách **nhận body phản hồi**. Đây là API khác với request body publisher.

Một `BodyPublisher` là một `Flow.Publisher<ByteBuffer>` có thêm `contentLength()`. HTTP client đăng ký subscriber để lấy byte cần gửi. Bạn thường **không phải** tự cài subscriber, thread, flow control hoặc đóng gói HTTP framing khi dùng các publisher có sẵn.

Không nên hiểu một lần phát ra `ByteBuffer` tương đương một TCP packet, HTTP/2 frame hay một phần multipart; các ranh giới truyền tải có thể được kết hợp hoặc chia tách.

## 2. `ofByteArrays(Iterable<byte[]>)` có chức năng gì?

Chữ ký Java 11:

~~~java
public static HttpRequest.BodyPublisher ofByteArrays(
    Iterable<byte[]> iter)
~~~

Đây là **chữ ký API** để đọc hiểu, không phải source cần tự định nghĩa. Factory nhận một `Iterable` cung cấp các mảng byte theo thứ tự iterator duyệt. Dữ liệu request body có nội dung logic tương đương phép **nối các byte của từng mảng** theo thứ tự đó.

Ví dụ:

~~~text
Mảng 1: [65, 66]        -> "AB"
Mảng 2: [67]            -> "C"
Mảng 3: [68, 69, 70]    -> "DEF"

Body nhìn từ server: [65, 66, 67, 68, 69, 70] -> "ABCDEF"
~~~

**Điều đúng:** Một request có một body với sáu byte được gửi theo thứ tự `ABCDEF`.

**Điều không đúng:** Server tự nhận ba request, ba field JSON, ba form part, hoặc ba chuỗi độc lập có ranh giới được HTTP cam kết bảo toàn. Các kích thước mảng không tạo metadata giải thích “đoạn 1/2/3”.

### 2.1. Viết request POST tối thiểu

~~~java
List<byte[]> pieces = List.of(
    "Xin ".getBytes(StandardCharsets.UTF_8),
    "chào".getBytes(StandardCharsets.UTF_8),
    " Java 11".getBytes(StandardCharsets.UTF_8)
);

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.test/echo"))
    .header("Content-Type", "text/plain; charset=utf-8")
    .POST(HttpRequest.BodyPublishers.ofByteArrays(pieces))
    .build();
~~~

Đây là **đoạn minh họa**, cần import `java.util.List`, `java.net.URI`, `java.net.http.HttpRequest` và `java.nio.charset.StandardCharsets`; địa chỉ `api.example.test` chỉ là placeholder tài liệu, **không phải endpoint có thể gọi**. Nội dung body nhận được nếu server đọc toàn bộ là `Xin chào Java 11`. Khi gửi thực, phải chọn URI hợp lệ, có quyền truy cập và timeout phù hợp.

`ofByteArrays` **không** tự thêm dấu cách, dấu phẩy, ký tự xuống dòng hoặc separator giữa các mảng. Nếu muốn separator, hãy đưa **byte của separator** vào một mảng dữ liệu; nếu muốn JSON hợp lệ, hãy serialize thành JSON hợp lệ trước khi truyền.

### 2.2. Phân biệt số byte và số ký tự

`String.length()` đo UTF-16 code units, **không** phải byte UTF-8. Ví dụ chữ `à` trong `chào` chiếm nhiều hơn một byte UTF-8. Khi kiểm soát kích thước, giới hạn upload và kiểm tra chiều dài body, phải cộng `byte[].length` của dữ liệu đã mã hóa, không cộng số ký tự.

Nếu một ký tự Unicode nhiều byte được chia ngang ranh giới hai mảng, điều đó vẫn **hợp lệ về mặt truyền byte** khi các byte được nối lại đúng thứ tự. Tuy nhiên, phía nhận không nên `new String(chunk, UTF_8)` độc lập cho từng chunk nếu có khả năng một ký tự nằm giữa hai chunk; cần decode như **một luồng liên tục**.

## 3. Chọn đúng factory: một mảng hay nhiều mảng?

| API Java 11 | Nguồn body | Khi nào ưu tiên |
| --- | --- | --- |
| `BodyPublishers.ofString(text, UTF_8)` | Một `String` được mã hóa bằng charset chỉ định. | Text/JSON nhỏ, đã serialize. |
| `BodyPublishers.ofByteArray(bytes)` | Một mảng byte. | Payload nhị phân đã có sẵn. |
| `BodyPublishers.ofByteArray(bytes, offset, length)` | Một đoạn trong một mảng. | Muốn chỉ gửi `length` byte hợp lệ từ buffer. |
| `BodyPublishers.ofByteArrays(iterable)` | Nhiều mảng byte theo thứ tự duyệt. | Đang có/chủ động sinh body dưới dạng nhiều đoạn, muốn nối logic. |
| `BodyPublishers.ofFile(path)` | Nội dung file. | Upload tệp mà không cần tự chia thành nhiều mảng. |
| `BodyPublishers.ofInputStream(supplier)` | Đọc từ stream được supplier cấp cho từng lần gửi. | Nguồn streaming, có thể mở mới khi phát lại. |
| `BodyPublishers.fromPublisher(publisher)` | `Flow.Publisher<? extends ByteBuffer>` tự cung cấp. | Luồng/điều phối đặc biệt, cần quản lý reactive backpressure. |
| `BodyPublishers.noBody()` | Không có body. | Request không cần payload. |

Các phương thức trong bảng có trên Java 11. **Không dùng `BodyPublishers.concat(...)` nếu đang nhắm Java 11**: phương thức đó được bổ sung trong Java mới hơn. `ofByteArrays` là công cụ hợp lệ để nối các mảng byte ở phiên bản 11, nhưng chỉ ghép những **byte bạn đã thiết kế** — không tự ghép nhiều publisher hoặc tạo format multipart.

Cân nhắc: Nếu cả payload đã nằm trong một `byte[]`, `ofByteArray` thường đơn giản hơn. Nếu có các đoạn nhỏ nhưng số lượng và tổng kích thước đáng kể, cần tính đến chi phí tạo mảng, giữ tham chiếu, sao chép và đồng bộ dữ liệu.

## 4. Chương trình Java 11 hoàn chỉnh: POST ba mảng, server nhận một body

Chương trình sau **không cần Internet**: nó mở một HTTP/1.1 server tại loopback `127.0.0.1` trên một cổng ngẫu nhiên, dùng client Java 11 gửi body tạo từ ba mảng byte, và server trả lại **đúng chuỗi byte đã nhận**. Việc dùng server nội bộ khiến kết quả không phụ thuộc website công cộng. Mã chỉ dùng JDK; test server là `com.sun.net.httpserver.HttpServer` thuộc module `jdk.httpserver`, không phải framework để dùng mặc định cho ứng dụng production.

Lưu nguyên nội dung sau vào file **`ByteArraysDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;

public final class ByteArraysDemo {
    private ByteArraysDemo() {
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
            new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 0);

        server.createContext("/echo", exchange -> {
            try {
                byte[] received = exchange.getRequestBody().readAllBytes();
                exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");
                exchange.sendResponseHeaders(200, received.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(received);
                }
            } finally {
                exchange.close();
            }
        });

        server.start();
        try {
            List<byte[]> chunks = List.of(
                "Xin ".getBytes(StandardCharsets.UTF_8),
                "chào ".getBytes(StandardCharsets.UTF_8),
                "Java 11".getBytes(StandardCharsets.UTF_8));

            int bytes = chunks.stream()
                .mapToInt(part -> part.length)
                .sum();

            URI uri = URI.create(
                "http://127.0.0.1:" +
                server.getAddress().getPort() + "/echo");

            HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(3))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

            HttpRequest request = HttpRequest.newBuilder(uri)
                .header("Content-Type",
                        "text/plain; charset=utf-8")
                .timeout(Duration.ofSeconds(5))
                .POST(HttpRequest.BodyPublishers.ofByteArrays(chunks))
                .build();

            HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                    StandardCharsets.UTF_8));

            System.out.println("chunks=" + chunks.size());
            System.out.println("payloadBytes=" + bytes);
            System.out.println("status=" + response.statusCode());
            System.out.println("echo=" + response.body());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Biên dịch/chạy bằng **JDK 11** (hoặc JDK mới hỗ trợ những API Java 11 này), với file lưu UTF-8:

~~~bash
javac -encoding UTF-8 --add-modules jdk.httpserver ByteArraysDemo.java
java --add-modules jdk.httpserver ByteArraysDemo
~~~

**Stdout chính xác khi hệ thống cho phép sử dụng loopback socket:**

~~~text
chunks=3
payloadBytes=17
status=200
echo=Xin chào Java 11
~~~

**Tại sao là 17 byte?** Mảng thứ nhất `"Xin "` có 4 byte ASCII; mảng thứ hai `"chào "` có 6 byte UTF-8 (vì ký tự `à` chiếm 2 byte); mảng cuối `"Java 11"` có 7 byte. Tổng 4 + 6 + 7 = 17 byte. Server không nhìn thấy ba field tách biệt; nó nhận chuỗi byte liên tục, rồi echo lại.

**Điểm cần lưu ý trong demo:**

1. `List.of(...)` tạo một **danh sách không thể thêm/xóa phần tử**, nhưng `byte[]` bên trong **vẫn có thể bị sửa**. Không sửa chúng khi request đang gửi.
2. `ofByteArrays(chunks)` tạo request body publisher, `POST(...)` gắn publisher vào request. Việc xây request chưa tạo network request; `client.send(...)` mới thực sự gửi.
3. `HttpClient.Version.HTTP_1_1` được đặt để chạy ổn định với test server chỉ hỗ trợ HTTP/1.1. Nó không thay đổi byte body. Bài học về HTTP/2 cũng vẫn áp dụng: ranh giới mảng không bảo đảm tương ứng với frame ở giao thức mạng.
4. `send(...)` có thể ném `IOException` hoặc `InterruptedException`; `main throws Exception` chỉ giúp demo ngắn gọn. Trong ứng dụng thật, cần xử lý lỗi theo hợp đồng.
5. Server dùng `readAllBytes()` để demo với payload rất nhỏ. **Không dùng cách này cho request body lớn hoặc không đáng tin cậy mà không đặt giới hạn**: client có thể gửi dữ liệu cực lớn, gây tràn bộ nhớ.
6. `HttpResponse.BodyHandlers.ofString(...)` đọc **response**; nó không quyết định cách **request** được phát. Đây là hai nửa độc lập của HTTP exchange.
7. Port `0` yêu cầu hệ điều hành chọn một cổng còn trống; chương trình không giả định sẵn 8080. Nếu máy cấm bind loopback thì không thể tạo server, không có stdout hoàn chỉnh.
8. Chỉ dữ liệu body được echo; bản thân server không kiểm tra xem các phần đến bằng bao nhiêu TCP packet hoặc HTTP chunk, vì điều đó không thuộc hợp đồng body ứng dụng.

## 5. Iterable và Iterator: yêu cầu có thể được gửi nhiều lần

Theo tài liệu `BodyPublishers.ofByteArrays` của Java 11, một `Iterable<byte[]>` cung cấp các `Iterator`. **Mỗi lần HTTP client cần gửi body** sẽ có một lần gọi lấy iterator từ Iterable. Điều này đặc biệt quan trọng khi có authentication challenge, redirect, retry do lỗi kết nối hoặc cơ chế gửi lại theo chính sách client.

Ví dụ dễ đọc:

~~~java
List<byte[]> stableChunks = List.of(
    "part-A".getBytes(StandardCharsets.UTF_8),
    "part-B".getBytes(StandardCharsets.UTF_8)
);

HttpRequest.BodyPublisher body =
    HttpRequest.BodyPublishers.ofByteArrays(stableChunks);
~~~

Đây là **đoạn minh họa**, cần import `List`, `StandardCharsets` và `HttpRequest`. `List` cung cấp iterator mới mỗi khi được yêu cầu. Nếu dữ liệu byte không bị thay đổi trong suốt vòng đời request, publisher có thể phát lại cùng body khi cần. Tuy nhiên, **việc Java có thể gửi lại không có nghĩa Java nhất định sẽ retry**, và không có nghĩa retry an toàn với mọi method.

### 5.1. Tránh nguồn chỉ dùng được một lần

Không thiết kế `Iterable` luôn trả về **cùng một Iterator đã bị tiêu thụ**. Ví dụ sai:

~~~java
Iterator<byte[]> once = chunks.iterator();
Iterable<byte[]> broken = () -> once;
~~~

Đây là **đoạn minh họa lỗi**, `chunks` giả sử đã được định nghĩa. Lần phát đầu có thể lấy hết các phần tử; lần sau iterator có thể đang ở cuối, làm body trống/thiếu byte hoặc phát sinh lỗi. Sự cố thường chỉ xuất hiện khi có redirect/401, khi client cố gửi lại hoặc khi test tạo hai request từ cùng publisher.

**Thiết kế đúng:** Iterable phải có khả năng sinh **một iterator mới, độc lập** cho mỗi lần được gọi và tạo ra cùng dãy byte theo hợp đồng nếu cần replay.

### 5.2. Iterable sinh dữ liệu theo nhu cầu

~~~java
Iterable<byte[]> repeatable = () -> List.of(
    "alpha".getBytes(StandardCharsets.UTF_8),
    "-".getBytes(StandardCharsets.UTF_8),
    "beta".getBytes(StandardCharsets.UTF_8)
).iterator();

HttpRequest.BodyPublisher publisher =
    HttpRequest.BodyPublishers.ofByteArrays(repeatable);
~~~

Đây là **đoạn minh họa**. Mỗi lần `iterator()` chạy, lambda tạo các mảng mới trong ví dụ; nội dung logic vẫn là `alpha-beta`. Với dữ liệu thực, iterator có thể đọc từ nguồn theo từng phần, nhưng hãy bảo đảm nguồn có thể mở lại khi HTTP client tạo subscription tiếp theo.

**Không nên** triển khai lazy iterator dựa trên một file descriptor/DB cursor đã đóng hay một stream không thể mở lại, rồi cho rằng publisher sẽ luôn có đúng một subscription.

### 5.3. Mutability và thời điểm tiêu thụ

Không mặc định rằng `ofByteArrays` **copy toàn bộ mảng ngay khi tạo publisher**. Dữ liệu có thể được lấy ở thời điểm gửi. Một cách an toàn với payload nhỏ là **chụp bản sao byte** trước khi đưa vào publisher:

~~~java
List<byte[]> immutableSnapshotOfBytes = sourceChunks.stream()
    .map(byte[]::clone)
    .collect(java.util.stream.Collectors.toUnmodifiableList());
~~~

Đây là **đoạn minh họa**, `sourceChunks` là `List<byte[]>`, dữ liệu bên trong không null; `Collectors.toUnmodifiableList()` có từ Java 10 và chạy được với Java 11. Bản sao giúp tách mảng khỏi phía đang sửa `sourceChunks`, nhưng bạn vẫn phải **không sửa các mảng đã đưa vào publisher**. Không gọi danh sách này là “deeply immutable” tuyệt đối: các `byte[]` vẫn mutable đối với code còn giữ tham chiếu.

Nếu dữ liệu đến từ nhiều thread, tránh sửa danh sách, thay các phần tử hoặc tái sử dụng backing array trong khi request chưa hoàn tất. Với luồng dữ liệu lớn, không nhất thiết copy tất cả; thay vào đó dùng ownership rõ ràng hoặc supplier mở nguồn mới cho mỗi lượt gửi.

## 6. Request body có một thứ tự byte; mảng không phải ranh giới mạng

Với `ofByteArrays`:

~~~text
Iterable<byte[]> -> Iterator -> byte[] A -> byte[] B -> byte[] C
                                 \          |          /
                                  \         |         /
                                   ---- HTTP body ----
                                             |
                            HTTP Client + HTTP framing
                                             |
                                       Mạng/proxy
                                             |
                                   Server đọc body
~~~

**Không có cam kết** mỗi `byte[]` tương ứng một lần `InputStream.read()` ở server. Trên HTTP/1.1, client có thể dùng framing chunked khi không biết trước tổng chiều dài; trên HTTP/2 dữ liệu được chuyển qua frames. Các ranh giới này phục vụ transport và **không phải delimiter dữ liệu ứng dụng**. Bất kỳ proxy hoặc layer mạng nào cũng có thể chia/gộp phần dữ liệu.

Ví dụ nếu muốn gửi ba dòng, phải chèn newline:

~~~java
List<byte[]> lines = List.of(
    "first\n".getBytes(StandardCharsets.UTF_8),
    "second\n".getBytes(StandardCharsets.UTF_8),
    "third\n".getBytes(StandardCharsets.UTF_8)
);
~~~

Server nhận body `first\nsecond\nthird\n` vì **newline đã có trong byte nguồn**, không phải vì mỗi mảng tự được ngăn bằng newline.

Nếu định dạng yêu cầu độ dài từng record, hãy tự thiết kế framing ứng dụng (ví dụ length-prefix với kiểm tra giới hạn, NDJSON có newline, hoặc multipart theo chuẩn). Nhiều mảng byte một mình không mang cấu trúc record.

## 7. Content-Length, transfer encoding và độ dài chưa biết

`BodyPublisher.contentLength()` mô tả **số byte của toàn bộ body** khi biết chính xác, hoặc giá trị âm khi chiều dài chưa biết. Đây là contract của publisher; nó **không phải** kích thước của một mảng riêng lẻ và **không phải** số ký tự String.

Tài liệu Java 11 không hứa `ofByteArrays` phải tính tổng byte trước khi đăng ký iterator; đó là một Iterable có thể sinh dữ liệu theo nhu cầu. Vì vậy đừng thiết kế hệ thống dựa trên giả định `ofByteArrays` luôn cung cấp một `Content-Length` cố định.

Ở HTTP/1.1, khi body length chưa biết, HTTP Client có thể dùng `Transfer-Encoding: chunked`. Trên HTTP/2, dữ liệu chạy trong frame/stream và **không có header transfer-encoding chunked kiểu HTTP/1.1**. Cả hai cách đều có thể mang **cùng body byte** tới application server.

**Đừng tự đặt header `Content-Length` theo phép đoán** khi dùng HTTP Client chuẩn. Một số header giao thức có thể bị hạn chế do implementation tự quản lý; sai Content-Length có thể làm request thất bại hoặc khiến server đợi thiếu/thừa byte. Nếu cần byte length cố định, hãy dùng API có body cố định hoặc triển khai publisher có contract length chính xác.

### 7.1. So sánh độ dài đã biết và chưa biết

~~~java
byte[] one = "abc".getBytes(StandardCharsets.UTF_8);

HttpRequest.BodyPublisher fixed =
    HttpRequest.BodyPublishers.ofByteArray(one);

HttpRequest.BodyPublisher many =
    HttpRequest.BodyPublishers.ofByteArrays(
        List.of(one, new byte[]{(byte) 'd'}));
~~~

Đây là **đoạn minh họa**. `fixed.contentLength()` có thể báo `3` vì mảng đã có kích thước cố định; `many` có nguồn Iterable nên không nên dựa vào một giá trị cố định trước khi gửi. Dù vậy, **nội dung logic** của `many` là bốn byte `abcd`.

Nếu tự cung cấp một `Flow.Publisher<ByteBuffer>` và chắc chắn số byte là `n > 0`, Java 11 có `BodyPublishers.fromPublisher(publisher, n)`. Giá trị `n` phải **chính xác** và bất biến qua các lần gọi; nếu publisher phát ít hơn/nhiều hơn, request có thể lỗi hoặc mắc kẹt tùy implementation/tình huống. Dùng overload không kèm length khi không biết trước. Không đánh đổi tính đúng đắn để “ép” header Content-Length.

## 8. Những phần dữ liệu khác nhau không tự thành multipart/form-data

**Cần phân biệt hai nghĩa của “nhiều phần”:**

- **Nhiều `byte[]` trong `ofByteArrays`:** chỉ là các mảnh của **một body liên tục**. Không có MIME headers, field name, boundary hoặc filename.
- **`multipart/form-data`:** là **định dạng body ứng dụng** có boundary, header của từng part, nội dung part và kết thúc theo quy tắc MIME/HTTP. Nó vẫn được gửi dưới dạng **một HTTP request body**, nhưng có cấu trúc bên trong.

Đây là ví dụ về body multipart có **một field text**:

~~~text
--BOUNDARY_EXAMPLE
Content-Disposition: form-data; name="note"
Content-Type: text/plain; charset=utf-8

Xin chào
--BOUNDARY_EXAMPLE--
~~~

Đoạn trên chỉ giúp đọc cấu trúc; **byte thực tế** dùng ký tự `\r\n` theo chuẩn ở các ranh giới MIME, không chỉ newline `\n` như cách hiển thị text.

Đoạn Java 11 minh họa cấu trúc byte cho một part:

~~~java
String boundary = "boundary-" + java.util.UUID.randomUUID();
String value = "Xin chào";
byte[] prefix = (
    "--" + boundary + "\r\n" +
    "Content-Disposition: form-data; name=\"note\"\r\n" +
    "Content-Type: text/plain; charset=utf-8\r\n" +
    "\r\n").getBytes(StandardCharsets.UTF_8);
byte[] data = value.getBytes(StandardCharsets.UTF_8);
byte[] suffix = (
    "\r\n--" + boundary + "--\r\n"
).getBytes(StandardCharsets.UTF_8);

HttpRequest request = HttpRequest.newBuilder(uri)
    .header("Content-Type",
        "multipart/form-data; boundary=" + boundary)
    .POST(HttpRequest.BodyPublishers.ofByteArrays(
        List.of(prefix, data, suffix)))
    .build();
~~~

Đây là **đoạn minh họa**, `uri` là URI HTTPS hợp lệ và cần import `HttpRequest`, `List`, `StandardCharsets`. Dữ liệu thực tế là các byte của `prefix + data + suffix`, với boundary được khai báo trong header. Đây chỉ là một field text; **upload file hay nhiều field** cần thêm các part có `Content-Disposition`, `filename` (nếu có), `Content-Type`, phần kết thúc chuẩn và escape/validation thích hợp.

Với multipart từ dữ liệu người dùng, phải tránh **boundary collision** trong nội dung, CRLF/header injection từ tên field/filename, vượt giới hạn kích thước và rò rỉ file nhạy cảm. Sử dụng HTTP client library có hỗ trợ multipart được duy trì khi định dạng phức tạp; `java.net.http.HttpClient` của Java 11 không tự sinh form-data chỉ vì dùng `ofByteArrays`. Tránh dựng multipart bằng phép nối String tùy tiện cho file nhị phân, vì có thể hỏng dữ liệu.

**Nếu chỉ cần JSON:** serialize **một document JSON hợp lệ**, đặt `Content-Type: application/json` và phát byte JSON. Đừng tưởng ba mảng `{"a":`, `1,`, `"b":2}` tự trở thành ba field HTTP độc lập; chúng chỉ ghép thành một JSON document khi concatenation thực sự hợp lệ.

## 9. UTF-8, nhị phân và các ranh giới dữ liệu

`ofByteArrays` phát **byte đúng thứ tự**, không tự mã hóa lại String và không tự kiểm tra xem body có hợp lệ theo `Content-Type` hay không. Vì thế:

- Text: mã hóa bằng `StandardCharsets.UTF_8` ở phía tạo từng `byte[]`; khớp `charset=utf-8` nếu media type cần charset.
- Binary (PNG, ZIP, protobuf, v.v.): truyền byte nguyên trạng, không chuyển qua `String` tùy tiện.
- JSON: cần serializer tạo JSON đúng syntax và charset, có schema/validation phù hợp.
- Form-url-encoded: phải mã hóa `application/x-www-form-urlencoded` đúng cách, không chỉ ghép key và value thô.
- Multipart: phải xây boundary và các phần theo định dạng, như mục trước.
- Nội dung nén: `Content-Encoding: gzip` có nghĩa **body bytes thực sự là gzip stream**; nhiều mảng byte chưa nén không tự biến thành gzip.

Ví dụ chia nhỏ một payload UTF-8 **theo byte**, kể cả giữa ký tự nhiều byte:

~~~java
byte[] utf8 = "Tiếng Việt".getBytes(StandardCharsets.UTF_8);
byte[] left = java.util.Arrays.copyOfRange(utf8, 0, 3);
byte[] right = java.util.Arrays.copyOfRange(utf8, 3, utf8.length);
List<byte[]> chunks = List.of(left, right);
~~~

Đây là đoạn minh họa. Ghép `left` rồi `right` tái tạo đúng `utf8`. Nhưng nếu một bên decode `left` riêng và `right` riêng, có thể tạo ký tự thay thế vì một code point bị cắt đôi; server nên decode trên **toàn body hoặc một decoder streaming** có trạng thái.

Khi dùng byte array tái sử dụng sau khi đọc từ file/socket:

~~~java
byte[] scratch = new byte[4096];
int n = input.read(scratch);
if (n > 0) {
    byte[] valid = java.util.Arrays.copyOf(scratch, n);
    pieces.add(valid);
}
~~~

Đây là **đoạn minh họa** với `input` là `InputStream`, `pieces` là collection hợp lệ và đã xử lý `IOException`. Chỉ `n` byte đầu là dữ liệu mới trong lượt đọc; cần copy vì `scratch` sẽ bị ghi đè ở lần đọc tiếp theo. **Không** đưa cùng `scratch` vào danh sách nhiều lần rồi sửa nó liên tục: khi client gửi, nhiều phần có thể trỏ tới nội dung của lượt đọc cuối, gây lặp và hỏng dữ liệu.

Nếu file lớn, copy toàn bộ các chunk vào danh sách có thể vẫn chiếm RAM bằng tổng dung lượng file. Khi đó `ofFile`, `ofInputStream` hoặc streaming publisher có backpressure phù hợp tốt hơn.

## 10. Backpressure và Flow: biết ranh giới trách nhiệm

`HttpRequest.BodyPublisher` mở rộng `Flow.Publisher<ByteBuffer>`. Khi gửi, HTTP Client đăng ký subscriber, yêu cầu (`request(n)`) các phần dữ liệu theo khả năng tiêu thụ, nhận `onNext` và kết thúc qua `onComplete`/`onError` theo contract Flow.

Với `BodyPublishers.ofByteArrays`, phần **Flow protocol** do implementation của JDK xử lý. Việc của bạn là tạo iterable:

1. Có thể cung cấp iterator hợp lệ và không tạo vô hạn payload ngoài kiểm soát.
2. Không phát phần tử null hoặc thay đổi byte sau khi giao cho publisher.
3. Không giữ lock/tài nguyên rồi block mãi trong `iterator/next`.
4. Có thể phát lại nội dung từ đầu nếu HTTP client cần một subscription mới.
5. Kiểm soát dung lượng, lỗi nguồn dữ liệu và vòng đời request.

**Không hiểu “có Iterable” là tự động async/backpressure ở mọi tầng**. Ví dụ `List<byte[]>` đã chứa toàn bộ payload trong RAM trước khi gửi. Publisher có thể phát dữ liệu theo nhu cầu subscriber, nhưng memory dùng để chuẩn bị list vẫn đã được cấp phát.

Với dòng dữ liệu lớn hoặc producer bất đồng bộ, `BodyPublishers.fromPublisher(Flow.Publisher<? extends ByteBuffer>)` có thể là giải pháp nâng cao. Khi tự cài Publisher, cần tuân thủ chính xác Reactive Streams/Flow: không phát vượt demand, xử lý cancel, error, terminal signals, request lặp và ownership của từng `ByteBuffer`. Không tự cài publisher chỉ để nối ba đoạn String đơn giản.

## 11. Retry, redirect, authentication và idempotency

Một nguyên tắc quan trọng từ JDK 11: nếu request cần được gửi lại, HTTP Client có thể đăng ký subscription mới và mong body publisher tạo lại **cùng nội dung**. `ofByteArrays` gọi iterable một lần cho mỗi lần gửi body; điều này làm khả năng replay trở thành vấn đề thiết kế dữ liệu, không chỉ là chi tiết API.

Nhưng **replayability ≠ retry safety**:

- `GET`/`HEAD` theo ngữ nghĩa chuẩn thường là an toàn/idempotent khi API tuân thủ hợp đồng.
- `PUT` và `DELETE` được định nghĩa idempotent theo HTTP semantics, nhưng vẫn có thể có side effects quan sát được trong hệ thống thực.
- `POST` thường **không idempotent**. Nếu server đã xử lý rồi network fail trước lúc nhận response, gửi lại có thể tạo giao dịch trùng.
- Redirect có thể đổi method/URI tùy status và policy. HTTP client không nhất thiết được phép replay body trong mọi tình huống.
- Authentication challenge cũng có thể dẫn đến nhiều lần gửi hoặc nhiều lượt đăng ký; custom one-shot source dễ lỗi.
- App-level retry nên có **timeout/deadline**, backoff, giới hạn số lần thử, nhận diện lỗi tạm thời và **idempotency key** khi API server hỗ trợ.

**Không tự viết vòng lặp “catch IOException → gửi lại POST mãi”**. Dù dữ liệu body có thể tái tạo chính xác, điều đó không chứng minh thao tác nghiệp vụ có thể lặp an toàn. Cần tách hai câu hỏi: *Tôi có tái tạo được byte body?* và *Nếu request được xử lý hai lần, kết quả nghiệp vụ có an toàn?*

Nếu có dữ liệu nhạy cảm, tuyệt đối không log raw body hoặc token để debug replay; lưu metadata hữu ích đã được kiểm soát như số byte, loại payload, request ID và mã lỗi.

## 12. Timeout, lỗi I/O và vòng đời tài nguyên

Request POST với body nhiều mảng vẫn có thể gặp timeout, bị cancel, server trả 4xx/5xx hoặc network ngắt giữa chừng. Trên Java 11:

~~~java
HttpClient client = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(5))
    .build();

HttpRequest request = HttpRequest.newBuilder(uri)
    .timeout(Duration.ofSeconds(15))
    .POST(HttpRequest.BodyPublishers.ofByteArrays(pieces))
    .build();

try {
    HttpResponse<Void> response =
        client.send(request, HttpResponse.BodyHandlers.discarding());
    if (response.statusCode() / 100 != 2) {
        reportStatus(response.statusCode());
    }
} catch (java.io.IOException e) {
    reportIoFailure(e);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    reportInterrupted(e);
}
~~~

Đây là **đoạn minh họa**, giả sử `uri`, `pieces` và các hàm `report...` được định nghĩa; cần import `HttpClient`, `HttpRequest`, `HttpResponse`, `Duration`. Khi chạy thật, phân biệt lỗi **trước khi nhận response** với status 4xx/5xx **đã nhận được**; đừng biến mọi status != 200 thành IOException.

`sendAsync` trả `CompletableFuture<HttpResponse<T>>`; bạn phải quản lý hoàn tất, exception/cancellation, timeout và ownership nguồn byte. Không giả định rằng gọi `cancel(true)` ngay lập tức đảm bảo server không nhận bất kỳ byte nào; một phần request có thể đã được truyền và xử lý.

**Khi iterator phát sinh lỗi:** ví dụ đọc file hỏng ở phần thứ mười, quá trình gửi có thể fail sau khi server đã nhận các phần trước đó. Thiết kế server phải validate toàn body trước khi commit nếu hợp đồng cần atomicity. Nếu client upload dữ liệu lớn, cân nhắc streaming có framing, checksum, hạn mức và transaction/staging ở server.

## 13. Kiểm thử đúng: chứng minh thứ tự byte và tình huống biên

Unit/integration tests cần kiểm tra body mà server nhận **không có phân cách tự động** và đúng thứ tự. Bảng kiểm tra:

| Case | Input | Điều phải đúng |
| --- | --- | --- |
| Ba mảng ngắn | `[AB], [C], [DEF]` | Body là `ABCDEF`, tổng 6 byte. |
| Một mảng rỗng ở giữa | `[AB], [], [CD]` | Body là `ABCD`; không tự chèn separator. |
| Iterable rỗng | Không có mảng | Body rỗng; không tự thêm bytes. |
| UTF-8 tiếng Việt | Các mảng ghép ra `Xin chào` | Server decode UTF-8 đúng từ toàn body. |
| Ký tự chia giữa 2 mảng | Tách byte UTF-8 ở giữa một code point | Sau khi ghép, decoder vẫn đọc đúng. |
| Mảng được tái sử dụng | Producer sửa một `byte[]` sau khi lưu vào list | Test phải phát hiện dữ liệu không ổn định, cần copy/ownership. |
| Nhiều lần gửi | Cùng Iterable dùng cho request mới | Iterator mới phát cùng dãy byte, nếu design replay. |
| HTTP/1.1 chunked | Nhiều mảng, tổng length không biết | Server vẫn xử lý **một** body; network chunk không phải form part. |
| Lỗi giữa lượt | Iterator đọc nguồn rồi ném exception | Client fail; không nuốt lỗi/không tự commit dữ liệu một phần. |
| Redirect/401 | Request có thể cần phát lại | Hành vi theo policy; không dùng iterable một lần. |

### 13.1. JUnit Jupiter integration test với test server local

Đoạn kiểm thử sau cần **JUnit Jupiter 5.x tương thích JDK 11**, module `jdk.httpserver` và cấu hình test runner Maven/Gradle. Đây là lớp test hoàn chỉnh đặt trong **`ByteArraysIntegrationTest.java`** khi những dependency đó đã được cấu hình. Không có cuộc gọi Internet công cộng:

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;

class ByteArraysIntegrationTest {
    @Test
    void partsArriveAsOneOrderedBody() throws Exception {
        AtomicReference<byte[]> received = new AtomicReference<>();
        HttpServer server = HttpServer.create(
            new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 0);

        server.createContext("/test", exchange -> {
            try {
                received.set(exchange.getRequestBody().readAllBytes());
                byte[] reply = "ok".getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(200, reply.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(reply);
                }
            } finally {
                exchange.close();
            }
        });
        server.start();

        try {
            URI uri = URI.create(
                "http://127.0.0.1:" +
                server.getAddress().getPort() + "/test");

            HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(2))
                .build();

            List<byte[]> parts = List.of(
                "AB".getBytes(StandardCharsets.UTF_8),
                new byte[0],
                "CD".getBytes(StandardCharsets.UTF_8));

            HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5))
                .POST(HttpRequest.BodyPublishers.ofByteArrays(parts))
                .build();

            HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());

            assertEquals(200, response.statusCode());
            assertArrayEquals(
                "ABCD".getBytes(StandardCharsets.UTF_8),
                received.get());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Test xác nhận server nhận `ABCD`, không phải `AB|CD` và không có byte tự sinh cho mảng rỗng. Không khẳng định test này chứng minh H2 hoặc thử hết các giao thức mạng; nó dùng H1.1 local để test **contract byte body**. Nên thêm test H2 với server hỗ trợ H2 khi dự án thực tế đòi khả năng tương thích đa giao thức.

### 13.2. Test replay nên kiểm tra byte, không chỉ số iterator

Khi thiết kế một Iterable sinh chunk theo nhu cầu, tạo thêm test gửi **hai request riêng** bằng publisher có thể tái sử dụng rồi so sánh bytes server nhận ở cả hai lần. Không chỉ kiểm tra `iterator()` được gọi bao nhiêu lần, vì client có thể cancel/retry theo hoàn cảnh. Phép kiểm có ý nghĩa là **mỗi request thành công tạo cùng body theo hợp đồng**.

## 14. Lỗi phổ biến và cách sửa

| Cách làm sai | Hậu quả | Cách sửa |
| --- | --- | --- |
| Tưởng ba `byte[]` là ba HTTP parts | Server không biết ranh giới mảng. | Thêm framing chuẩn: JSON/NDJSON/length-prefix/multipart đúng schema. |
| Dùng `Content-Type: multipart/form-data` nhưng không tạo boundary | Server parse lỗi. | Tạo MIME parts và header boundary phù hợp, hoặc dùng library multipart. |
| Dùng một Iterator đã bị tiêu thụ cho mọi attempt | Gửi lại thiếu hoặc không có dữ liệu. | Iterable cung cấp iterator mới, nguồn có thể replay. |
| Sửa `byte[]` sau khi tạo publisher hoặc trong lúc gửi | Body sai, race và dữ liệu bị lặp. | Tạo snapshot/ownership, không mutate chunk đang phát. |
| Dùng buffer 4096 byte khi chỉ đọc 137 byte | Có 3959 byte cũ/rác bị gửi. | Chỉ lấy `n` byte thực tế, copy khi buffer sẽ tái sử dụng. |
| Tưởng kích thước mỗi array được bảo toàn ở network | Server đọc ra chunk khác kích thước. | Parse theo định dạng body, không theo số lần `read()`. |
| Dùng `String.length()` làm Content-Length UTF-8 | Sai byte length với Unicode. | Dùng `getBytes(UTF_8).length` hoặc body publisher phù hợp. |
| Chèn `Transfer-Encoding` thủ công để “bật streaming” | Tranh chấp với framing do client quản lý. | Để HTTP Client chọn framing, theo dõi khi cần. |
| Đặt `Content-Type: application/json` rồi nối các fragment JSON sai cú pháp | Server từ chối body. | Serialize thành một JSON document hợp lệ. |
| Dùng `new String(chunk, UTF_8)` trên mỗi chunk byte | Dễ cắt hỏng ký tự UTF-8 nhiều byte. | Decode sau ghép hoặc dùng decoder streaming. |
| Gom toàn bộ file lớn vào `List<byte[]>` | Bộ nhớ tỷ lệ theo dung lượng file, nguy cơ OOM. | Dùng `ofFile`/`ofInputStream`/publisher stream phù hợp. |
| Tự tạo Flow publisher mà phát không theo demand | Backpressure bị phá, lỗi protocol/tiêu thụ bộ nhớ. | Tuân thủ `Flow` hoặc dùng publisher có sẵn. |
| Lặp POST khi timeout mà không có idempotency | Có thể tạo giao dịch trùng. | Retry có giới hạn và idempotency contract. |
| Nghĩ `BodyHandlers.ofByteArray` là publisher | Nhầm chiều request/response. | `BodyPublishers` gửi, `BodyHandlers` nhận. |
| Dùng `BodyPublishers.concat` trong Java 11 | Method không có trong target JDK 11. | Dùng `ofByteArrays` nếu nguồn là nhiều byte arrays. |
| Log toàn bộ payload khi có lỗi upload | Rò rỉ dữ liệu nhạy cảm. | Log metadata và error category an toàn. |

## 15. Quy trình thiết kế body nhiều phần trong ứng dụng

Khi cần gửi body có nhiều phần dữ liệu, chọn các quyết định theo thứ tự:

1. **Xác định format của server:** text, JSON, multipart/form-data, binary protocol hay stream record? Không lựa chọn chỉ dựa vào API phía Java.
2. **Xác định nội dung byte:** mã hóa UTF-8/nhị phân, separator, framing, hash/checksum, file metadata và schema.
3. **Xác định nguồn:** có sẵn một `byte[]`, nhiều `byte[]`, file, InputStream có thể mở lại hoặc reactive producer?
4. **Xác định giới hạn:** tổng bytes, số chunks, max chunk size, memory budget, timeout và cancellation.
5. **Xác định replayability:** mỗi lần gửi lại có thể sinh cùng byte không; có cần ổn định snapshot và bảo vệ array khỏi mutation không?
6. **Xác định HTTP framing:** để HttpClient quản lý `Content-Length`, chunked transfer hoặc H2 frames; chỉ áp đặt length nếu biết chắc.
7. **Xác định retry safety:** operation có idempotent không, có idempotency key và cơ chế server chống gửi trùng không?
8. **Gửi và xử lý response:** phân biệt HTTP status với lỗi kết nối và đọc body response bằng BodyHandler thích hợp.
9. **Kiểm thử offline:** dùng test server nhận toàn bộ byte và assert nội dung, kể cả mảng rỗng và Unicode.
10. **Kiểm thử integration thực:** chỉ khi có môi trường server/proxy thật, so sánh byte count, content type, schema, timeout và lỗi trên nhiều request.

Với payload text nhỏ, `ofString(text, UTF_8)` thường rõ hơn. Với payload binary cố định, `ofByteArray` rất gọn. Với các chunk nhỏ đã có hoặc có thể tái tạo, `ofByteArrays` mô tả đúng ý định. Với file lớn, ưu tiên `ofFile` hoặc stream có kiểm soát thay vì làm giàu bộ nhớ bằng danh sách tất cả các chunk.

## 16. Bài tự luyện có đáp án định hướng

**Bài 1 — byte count:** Cho `List.of("A".getBytes(UTF_8), "à".getBytes(UTF_8), "B".getBytes(UTF_8))`. Body gửi có bao nhiêu byte? **Đáp án:** 1 + 2 + 1 = 4 byte, biểu diễn văn bản `AàB` sau khi giải mã toàn bộ UTF-8.

**Bài 2 — phân cách:** Với ba mảng `"A"`, `"B"`, `"C"`, server có tự thấy ba dòng không? **Không.** Body là `ABC`. Muốn ba dòng, tạo `"A\n"`, `"B\n"`, `"C\n"` hoặc dùng framing được quy định.

**Bài 3 — nguồn dùng một lần:** Một Iterable trả về cùng Iterator đã hết sau lần POST đầu tiên. Request thứ hai có thể ra sao? Thiết kế `Iterable` trả iterator mới mỗi lần, chứng minh test nhận bytes giống nhau.

**Bài 4 — multipart:** So sánh `List.of(fileChunk1, fileChunk2)` với một MIME multipart có hai part. Tại sao hai mảng byte không đủ để server biết filename và field name? **Gợi ý:** thiếu `Content-Disposition`, boundary và cấu trúc header/CRLF của MIME.

**Bài 5 — UTF-8:** Cắt một byte giữa ký tự `ế`. Vì sao hai lần giải mã từng chunk có thể lỗi, nhưng nối byte rồi giải mã vẫn đúng? Viết test với `StandardCharsets.UTF_8` và `Arrays.copyOfRange`.

**Bài 6 — chunk cuối:** Một `InputStream` có buffer 8192 byte, lượt cuối chỉ đọc 11 byte. Hãy sửa code để chỉ thêm 11 byte đó vào Iterable và không giữ tham chiếu tới mảng scratch sẽ bị ghi đè.

**Bài 7 — retry:** API POST tạo đơn hàng đã nhận bytes nhưng client timeout trước response. Có thể gửi lại tự động không? **Chỉ khi** có idempotency contract phù hợp hoặc đã xác định an toàn; body replayable không đủ.

**Bài 8 — chọn factory:** Với file 4 GB, giải thích vì sao không nên tạo trước hàng triệu mảng byte chỉ để dùng `ofByteArrays`. Đề xuất `ofFile`/`ofInputStream` hoặc streaming publisher và nêu các giới hạn resource.

## 17. Tài liệu chính thức và ghi nhớ

- [Java SE 11 — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html): chữ ký `ofByteArrays(Iterable<byte[]>)`, các publisher chuẩn và lưu ý iterator mới mỗi attempt.
- [Java SE 11 — HttpRequest.BodyPublisher](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html): `Flow.Publisher<ByteBuffer>`, subscription, re-send và `contentLength()`.
- [Java SE 11 — HttpRequest](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.html): builder gắn request body vào POST/PUT và các method khác.
- [Java SE 11 — HttpClient](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): `send`, `sendAsync`, timeout và response.
- [RFC 7578 — multipart/form-data](https://www.rfc-editor.org/rfc/rfc7578): cấu trúc boundary và form parts (khi thật sự cần multipart).
- [JEP 321 — HTTP Client API](https://openjdk.org/jeps/321): chuẩn hóa HTTP Client trong JDK 11.

**Ghi nhớ:** `ofByteArrays` tạo một **body byte liên tục** từ nhiều mảng; thứ tự byte quan trọng, ranh giới mảng **không** trở thành ranh giới HTTP/multipart. Khi client cần gửi lại, Iterable phải có thể cung cấp iterator mới với cùng dữ liệu; còn việc có nên retry hay không là quyết định **nghiệp vụ riêng**. Hãy chọn charset/Content-Type đúng, giới hạn bộ nhớ, và kiểm thử nội dung server thực nhận thay vì dựa trên giả định về packet hay chunk.