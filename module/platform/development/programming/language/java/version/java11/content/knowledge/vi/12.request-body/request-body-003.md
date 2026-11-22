# Request body: BodyPublishers.ofByteArray và phạm vi mảng dữ liệu trong Java 11

## Mục tiêu học tập

Khi gửi dữ liệu nhị phân hoặc một phần dữ liệu đã được mã hóa sẵn qua HTTP, Java 11 cung cấp hai overload của `HttpRequest.BodyPublishers.ofByteArray`. Trường hợp dễ sai nhất là truyền nhầm **độ dài** thành **chỉ số kết thúc**, hoặc cắt một chuỗi Unicode theo chỉ số `char` dù phương thức cần **chỉ số byte**.

Bài học này giúp bạn:

1. Dùng đúng `ofByteArray(byte[] buf)` và `ofByteArray(byte[] buf, int offset, int length)` để tạo HTTP **request body**.
2. Phân biệt `offset`, `length`, chỉ số kết thúc **exclusive**, cùng các trường hợp phạm vi rỗng và vượt biên.
3. Hiểu `BodyPublisher.contentLength()` là **số byte**, không phải `String.length()`, số code point, hay HTTP response body.
4. Gửi được payload có byte `0x00`, `0xFF`, tiếng Việt và ký tự Unicode bổ sung mà không làm mất dữ liệu.
5. Kiểm soát tính ổn định của mảng `byte[]` khi mã gửi bất đồng bộ có thể đọc nội dung sau thời điểm tạo publisher.
6. Kiểm thử end-to-end bằng server loopback có sẵn trong JDK, không phụ thuộc Internet hoặc thư viện ngoài.

Hai overload `ofByteArray` thuộc module chuẩn `java.net.http`, xuất hiện từ **Java 11** và tiếp tục hiện diện trong Javadoc của các bản JDK mới. Nội dung tập trung vào API đang được hỗ trợ, không sử dụng tên phương thức hay HTTP Client incubator trước Java 11.

## 1. API `BodyPublishers.ofByteArray` dùng để làm gì?

`HttpRequest.BodyPublisher` đại diện cho **nguồn byte sẽ gửi đi** trong request HTTP. Có thể xem nó là một `Flow.Publisher<ByteBuffer>` chuyên dùng cho request: HTTP Client đăng ký nhận các `ByteBuffer` khi cần phát dữ liệu ra mạng. Một publisher không phải là response, không trực tiếp gửi request và không tự chọn URL/method/header.

Javadoc Java 11 định nghĩa hai phương thức:

~~~java
public static HttpRequest.BodyPublisher ofByteArray(byte[] buf)

public static HttpRequest.BodyPublisher ofByteArray(
        byte[] buf, int offset, int length)
~~~

Cả hai là factory method tĩnh của `HttpRequest.BodyPublishers`.

### 1.1. Gửi toàn bộ mảng

~~~java
byte[] payload = {65, 0, (byte) 0xFF};
HttpRequest.BodyPublisher publisher =
        HttpRequest.BodyPublishers.ofByteArray(payload);
~~~

Publisher đại diện cho **cả ba byte**:

| Java byte | Giá trị octet trên dây | Giải thích |
| --- | --- | --- |
| `65` | `0x41` | Chữ `A` theo ASCII |
| `0` | `0x00` | NUL vẫn là một byte của body |
| `(byte) 0xFF` | `0xFF` | `byte` Java mang dấu nên thường hiển thị là `-1`, nhưng bit pattern là `FF` |

Đây là **đoạn minh họa**, không phải chương trình chạy độc lập: cần đặt bên trong một method/class thích hợp. `ofByteArray` không tự giải mã byte, không xóa `NUL`, không chuyển byte `FF` thành văn bản; nó phát **dữ liệu byte** làm request body.

### 1.2. Chỉ gửi một đoạn mảng

~~~java
byte[] buffer = {99, 65, 66, 67, 100};
HttpRequest.BodyPublisher publisher =
        HttpRequest.BodyPublishers.ofByteArray(buffer, 1, 3);
~~~

Dữ liệu có index:

~~~text
index:    0    1    2    3    4
value:   99   65   66   67  100
         bỏ  [-----gửi-----]  bỏ
sent:          65   66   67
text:           A    B    C
~~~

- `offset = 1`: byte **đầu tiên được lấy**, tính từ **0**.
- `length = 3`: **số lượng byte** cần lấy, không phải index 3 hoặc chỉ số end.
- Phạm vi gửi là `[offset, offset + length)`, tức từ index 1 **bao gồm** đến index 4 **không bao gồm**.
- Byte tại các vị trí 0 và 4 bị loại khỏi body, dù chúng vẫn nằm trong mảng Java.

**Kết luận cốt lõi:** lời gọi `ofByteArray(buffer, 1, 3)` gửi `buffer[1]`, `buffer[2]` và `buffer[3]`. Nếu bạn muốn gửi từ index `start` đến index `endExclusive`, tham số thứ ba phải là **`endExclusive - start`**.

~~~java
int start = 1;
int endExclusive = 4;
var publisher = HttpRequest.BodyPublishers.ofByteArray(
        buffer, start, endExclusive - start);
~~~

Ký hiệu `var` dùng được với biến cục bộ trong Java 11, nhưng có thể khai báo đầy đủ `HttpRequest.BodyPublisher` để giao diện người học rõ ràng hơn.

## 2. Quy tắc phạm vi và ngoại lệ

Với mảng không `null` và độ dài `n = buf.length`, điều kiện cho phạm vi hợp lệ là:

~~~text
0 <= offset <= n
0 <= length <= n - offset
~~~

Đây là cách kiểm **không cần cộng `offset + length` trước khi xét biên**, nên tránh lỗi tràn `int` khi dữ liệu đầu vào không đáng tin. Phạm vi hợp lệ có thể rỗng.

| `buf.length` | `offset` | `length` | Hợp lệ? | Phạm vi |
| --- | ---: | ---: | --- | --- |
| 5 | 0 | 5 | Có | Toàn bộ mảng |
| 5 | 1 | 3 | Có | Index 1, 2, 3 |
| 5 | 5 | 0 | Có | Rỗng, bắt đầu ngay sau byte cuối |
| 5 | 0 | 0 | Có | Rỗng |
| 5 | 3 | 2 | Có | Index 3, 4 |
| 5 | 3 | 3 | **Không** | Kết thúc vượt biên |
| 5 | -1 | 1 | **Không** | Offset âm |
| 5 | 0 | -1 | **Không** | Length âm |
| 5 | 5 | 1 | **Không** | Không còn byte nào để lấy |
| 5 | `Integer.MAX_VALUE` | `Integer.MAX_VALUE` | **Không** | Các index không nằm trong mảng |

Nếu subrange vượt biên, overload ba tham số ném **`IndexOutOfBoundsException`** khi tạo publisher. Đừng tự bắt lỗi rồi im lặng gửi toàn bộ mảng: đó là một lỗi tính phạm vi cần sửa ở nơi tạo request.

`buf` cũng không được là `null`; truyền `null` không tạo một body rỗng hợp lệ mà dẫn đến lỗi tham chiếu (thông thường là `NullPointerException`). Nếu muốn gửi body dài 0, tạo mảng `new byte[0]` hoặc dùng `ofByteArray(buf, offset, 0)` hợp lệ; `BodyPublishers.noBody()` cũng tồn tại cho request không có body theo thiết kế.

### 2.1. Phạm vi rỗng có nghĩa gì?

~~~java
byte[] padded = {1, 2, 3};
HttpRequest.BodyPublisher empty =
        HttpRequest.BodyPublishers.ofByteArray(
                padded, padded.length, 0);
System.out.println(empty.contentLength()); // 0
~~~

Đây là **publisher có số byte bằng 0**, không phải null và cũng không phải «gửi toàn bộ phần còn lại». Theo hợp đồng `BodyPublisher`, publisher báo `contentLength() == 0` thậm chí có thể không được HTTP Client subscribe vì không có byte nào để phát.

**Phân biệt về nghiệp vụ:** một request POST body rỗng và một request không có body thường đều không phát byte nội dung, nhưng máy chủ hoặc middleware có thể diễn giải method/header khác nhau. Hãy test điều mà HTTP API đích yêu cầu; không suy luận chỉ từ một phép so sánh số byte.

### 2.2. Ý nghĩa của `contentLength()`

`HttpRequest.BodyPublisher.contentLength()` trả `long`:

- `0`: publisher biết body có **0 byte**.
- Giá trị dương: số byte body đã biết.
- Giá trị âm: độ dài không xác định ở một số publisher khác.

Với `ofByteArray(buf)`, số byte được biết trước nên `contentLength() == buf.length`. Với overload phạm vi, `contentLength() == length`. Kết quả là **độ dài byte**, không phải số ký tự Unicode.

~~~java
byte[] raw = {10, 20, 30, 40};
long whole = HttpRequest.BodyPublishers
        .ofByteArray(raw).contentLength();      // 4
long part = HttpRequest.BodyPublishers
        .ofByteArray(raw, 1, 2).contentLength(); // 2
~~~

HTTP Client chịu trách nhiệm đóng gói request và xử lý framing/`Content-Length` phù hợp giao thức. **Không tự đặt header `Content-Length` bằng một phép tính trên số ký tự Java**; header thuộc các tên bị HTTP Client hạn chế và giá trị có thể phụ thuộc transport (HTTP/1.1 so với HTTP/2). Khi kiểm thử, xác minh byte ở phía server và `publisher.contentLength()` thay vì giả định một dạng wire header cố định ở mọi phiên bản/protocol.

## 3. Phạm vi byte và phạm vi ký tự Unicode là hai thứ khác nhau

### 3.1. `String.length()` không phải độ dài UTF-8

Java `String` dùng UTF-16. Một ký tự tiếng Việt có thể có **nhiều byte UTF-8**; ký tự ngoài BMP thường có **hai code units UTF-16** nhưng **bốn byte UTF-8**.

~~~java
String text = "Ti\u1EBFng Vi\u1EC7t "
        + new String(Character.toChars(0x1F642));
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);

int javaUnits = text.length();  // số UTF-16 code units
int bodyBytes = bytes.length;   // số byte sẽ gửi
~~~

Với `BodyPublishers.ofByteArray`, mọi `offset` và `length` phải được tính trên **`bytes`**. Không dùng trực tiếp `text.length()` hoặc `text.indexOf(...)` làm offset vào UTF-8 byte array nếu dữ liệu trước đó có ký tự đa byte.

Giả sử tạo buffer có một vùng tiền tố và hậu tố:

~~~java
String prefix = "IGNORE|";
String content = "Ti\u1EBFng Vi\u1EC7t";
String suffix = "|SKIP";

byte[] all = (prefix + content + suffix)
        .getBytes(StandardCharsets.UTF_8);
int offset = prefix.getBytes(StandardCharsets.UTF_8).length;
int length = content.getBytes(StandardCharsets.UTF_8).length;

HttpRequest.BodyPublisher publisher =
        HttpRequest.BodyPublishers.ofByteArray(
                all, offset, length);
~~~

Ở ví dụ trên, tiền tố ASCII khiến số `char` và số byte trùng nhau, **nhưng vẫn tính bằng UTF-8 bytes** để bảo toàn quy tắc tổng quát. Với tiền tố có dấu tiếng Việt, dùng số `char` sẽ dẫn đến sai offset.

### 3.2. Cắt giữa một chuỗi UTF-8 nhiều byte thì sao?

Phạm vi là byte range thuần túy. JDK **không kiểm tra** ranh giới ký tự UTF-8 khi bạn tạo `ofByteArray(buf, offset, length)`. Do đó một subrange hợp lệ về chỉ số vẫn có thể không phải văn bản UTF-8 hợp lệ.

Ví dụ ký tự **é** được mã hóa UTF-8 thành hai byte `C3 A9`:

~~~java
byte[] eAcute = "\u00E9".getBytes(StandardCharsets.UTF_8);
// Chọn một byte đầu: hợp lệ về chỉ số, nhưng không đủ để tạo văn bản UTF-8.
HttpRequest.BodyPublisher half =
        HttpRequest.BodyPublishers.ofByteArray(eAcute, 0, 1);
~~~

Publisher này hợp lệ cho **dữ liệu nhị phân một byte `C3`**, nhưng nếu gắn header `text/plain; charset=UTF-8` thì byte body không tạo một chuỗi UTF-8 hoàn chỉnh. Phần giải mã bên nhận có thể thay bằng ký tự `U+FFFD` hoặc báo lỗi, tùy decoder/chính sách.

**Quy tắc:** khi payload mang ý nghĩa văn bản, hãy xác định vùng theo ký tự trước rồi **mã hóa đúng đoạn cần gửi thành UTF-8**, hoặc tính byte offsets từ các phần đã được mã hóa hoàn chỉnh; không tự cắt giữa code points. Khi payload mang ý nghĩa binary, giữ nguyên bytes và chọn media type tương ứng.

## 4. HTTP request thật: gắn publisher vào HttpRequest

`ofByteArray` chỉ tạo nguồn body; để gửi, đặt nó vào builder của `HttpRequest`, rồi dùng `HttpClient.send` hoặc `sendAsync`.

~~~java
// Đoạn minh họa: cần imports, xử lý IOException/InterruptedException,
// và URL là endpoint thực đã được ứng dụng cho phép gửi.
byte[] payload = {65, 66, 67};

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/upload"))
        .header("Content-Type", "application/octet-stream")
        .POST(HttpRequest.BodyPublishers.ofByteArray(payload))
        .build();

HttpClient client = HttpClient.newHttpClient();
HttpResponse<byte[]> response = client.send(
        request, HttpResponse.BodyHandlers.ofByteArray());
~~~

Bốn điểm phải phân biệt:

- **`HttpRequest.BodyPublishers.ofByteArray(...)`** tạo **request body publisher** — dữ liệu được gửi đi.
- **`HttpResponse.BodyHandlers.ofByteArray()`** tiêu thụ **response body** — dữ liệu nhận về. Tên tương tự nhưng chức năng ngược nhau.
- `Content-Type` **không tự được xác định là `application/octet-stream` hay `text/plain` chỉ vì dùng `ofByteArray`**. Tầng ứng dụng chọn đúng media type theo giao thức.
- `HttpResponse.statusCode()` cho biết kết quả HTTP; status 4xx/5xx vẫn có thể là một response hoàn chỉnh và phải được kiểm tra theo nghiệp vụ.

Dùng `sendAsync` nếu không muốn chặn luồng gửi:

~~~java
CompletableFuture<HttpResponse<byte[]>> future = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofByteArray());

CompletableFuture<byte[]> received = future.thenApply(response -> {
    if (response.statusCode() != 200) {
        throw new IllegalStateException(
                "Unexpected HTTP status: " + response.statusCode());
    }
    return response.body();
});
~~~

Đây là **đoạn minh họa**, giả định `client`, `request` có sẵn và các imports phù hợp. `sendAsync` trả future; dùng `thenApply` để biến đổi khi hoàn tất. Không gọi `join()` ngay trong event loop nếu mục tiêu là không chặn luồng hiện tại. `ofByteArray` dùng được cho cả đồng bộ và bất đồng bộ.

## 5. Tính ổn định của `byte[]` trước và trong khi gửi

Mảng `byte[]` là đối tượng **mutable**. Khi publisher đã được tạo, một số bước phát dữ liệu có thể diễn ra về sau (đặc biệt với `sendAsync`), và request có thể được subscribe lại khi implementation cần gửi lại nội dung. Không nên giả định việc gọi factory luôn tạo một **bản chụp bất biến của toàn bộ mảng ngay tại thời điểm tạo**: Javadoc `ofByteArray` chỉ mô tả nguồn dữ liệu và phạm vi byte, không cam kết cơ chế sao chép tại thời điểm đó.

**Chính sách an toàn:** hoặc không chỉnh sửa mảng nguồn trong suốt thời gian publisher có thể dùng nó, hoặc chủ động **sao chép phạm vi cần gửi** trước khi tạo publisher.

~~~java
// Đoạn minh họa: đầu vào đã được kiểm soát đúng phạm vi.
byte[] source = {10, 20, 30, 40, 50};
int offset = 1;
int length = 3;

java.util.Objects.checkFromIndexSize(offset, length, source.length);
byte[] stableBytes =
        java.util.Arrays.copyOfRange(source, offset, offset + length);

HttpRequest.BodyPublisher publisher =
        HttpRequest.BodyPublishers.ofByteArray(stableBytes);
~~~

Kết quả `stableBytes` là ba byte `20, 30, 40`. Đây là **bản sao do mã ứng dụng chủ động tạo**. Bạn có thể sửa `source` sau đó mà không ảnh hưởng tới `stableBytes`. Tuy nhiên cũng không sửa `stableBytes` trong lúc publisher còn có thể sử dụng nó.

Cẩn thận: `Arrays.copyOfRange` **có thể đệm byte 0** nếu end index vượt quá chiều dài mảng. Vì vậy kiểm tra `Objects.checkFromIndexSize` **trước khi copy**, chứ không dùng `copyOfRange` để «tự sửa» phạm vi sai. `Objects.checkFromIndexSize` có sẵn trong Java 11.

### 5.1. Sao chép có chi phí; chọn phương án phù hợp

| Dữ liệu cần gửi | Publisher phù hợp | Ghi chú |
| --- | --- | --- |
| Mảng nhỏ, đã mã hóa đúng và không bị thay đổi | `ofByteArray(bytes)` | Dễ dùng, biết trước độ dài. |
| Một phần mảng lớn, nguồn ổn định | `ofByteArray(bytes, offset, length)` | Không cần tự cắt ra mảng con chỉ để chỉ định phạm vi. |
| Vùng dữ liệu có thể bị luồng khác thay đổi | `ofByteArray(Arrays.copyOfRange(...))` sau khi xác minh phạm vi | Snapshot dữ liệu ứng dụng; đổi lấy chi phí sao chép. |
| `String` cần mã hóa theo charset | `ofString(text, StandardCharsets.UTF_8)` | Tránh tự tính phạm vi byte nếu không cần. |
| File lớn, không muốn tự tải toàn bộ vào RAM | `ofFile(path)` hoặc `ofInputStream(supplier)` | Phải xử lý vòng đời dữ liệu và việc request được gửi lại theo hợp đồng. |
| Nhiều đoạn mảng tạo thành một body | `ofByteArrays(Iterable<byte[]>)` | Tên **số nhiều**, có hợp đồng khác `ofByteArray`. |

`ofByteArray` thích hợp với payload nhỏ/vừa đã nằm trong RAM. Đừng mặc định đây là kỹ thuật *zero-copy*: implementation có quyền tạo `ByteBuffer` và copy dữ liệu khi phát để đáp ứng hợp đồng của HTTP Client; performance cần đo và đánh giá theo ứng dụng cụ thể.

## 6. Chương trình Java 11 chạy được: kiểm thử phạm vi mảng qua HTTP

Chương trình **ByteArrayRangeDemo.java** khởi chạy một HTTP server nội bộ trên `127.0.0.1` với cổng động. Server nhận request body **dưới dạng bytes nguyên vẹn**, ghi nhận `Content-Type` và echo bytes về client. Nhờ vậy các phép kiểm chứng dựa trên **bytes mà server thực sự nhận**, không chỉ dựa trên `contentLength()` của publisher.

Các nhóm kiểm thử:

1. Gửi toàn bộ mảng có `NUL` và byte `FF`, nhận đúng từng byte.
2. Chọn đoạn bytes UTF-8 chứa tiếng Việt và ký tự bổ sung; loại bỏ tiền tố/hậu tố.
3. Chọn dải `[1, 4)` trong mảng dữ liệu ASCII có hai byte đệm ngoài phạm vi.
4. Chọn phạm vi rỗng tại `offset == buf.length`.
5. Sao chép phòng vệ trước khi gửi và thay đổi mảng nguồn ban đầu.
6. Xác nhận `IndexOutOfBoundsException` với offset/length không hợp lệ.

Tạo file **ByteArrayRangeDemo.java**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Arrays;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicReference;

public class ByteArrayRangeDemo {
    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    private static byte[] post(HttpClient client, URI url,
                               HttpRequest.BodyPublisher publisher,
                               String type) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(url)
                .timeout(Duration.ofSeconds(5))
                .header("Content-Type", type)
                .POST(publisher)
                .build();
        HttpResponse<byte[]> response = client.send(request,
                HttpResponse.BodyHandlers.ofByteArray());
        check(response.statusCode() == 200, "HTTP status must be 200");
        return response.body();
    }

    private static void invalid(byte[] bytes, int offset, int length) {
        boolean rejected = false;
        try {
            HttpRequest.BodyPublishers.ofByteArray(bytes, offset, length);
        } catch (IndexOutOfBoundsException expected) {
            rejected = true;
        }
        check(rejected, "invalid range must be rejected");
    }

    public static void main(String[] args) throws Exception {
        AtomicReference<byte[]> observed = new AtomicReference<>();
        AtomicReference<String> observedType = new AtomicReference<>();

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService workers = Executors.newSingleThreadExecutor();
        server.setExecutor(workers);
        server.createContext("/echo", exchange -> {
            byte[] incoming;
            try (InputStream body = exchange.getRequestBody()) {
                incoming = body.readAllBytes();
            }
            observed.set(incoming);
            observedType.set(exchange.getRequestHeaders()
                    .getFirst("Content-Type"));
            exchange.getResponseHeaders()
                    .set("Content-Type", "application/octet-stream");
            if (incoming.length == 0) {
                exchange.sendResponseHeaders(200, -1);
                exchange.close();
            } else {
                exchange.sendResponseHeaders(200, incoming.length);
                try (OutputStream body = exchange.getResponseBody()) {
                    body.write(incoming);
                }
            }
        });
        server.start();

        try {
            URI url = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/echo");
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            byte[] binary = new byte[] { 65, 0, (byte) 0xFF };
            HttpRequest.BodyPublisher full =
                    HttpRequest.BodyPublishers.ofByteArray(binary);
            check(full.contentLength() == binary.length,
                    "full publisher length");
            check(Arrays.equals(binary, post(client, url, full,
                    "application/octet-stream")), "binary round trip");
            check(Arrays.equals(binary, observed.get()),
                    "server received full binary body");
            check("application/octet-stream".equals(observedType.get()),
                    "binary Content-Type");
            System.out.println("PASS full byte array");

            String text = "Ti\u1EBFng Vi\u1EC7t "
                    + new String(Character.toChars(0x1F642));
            String prefix = "IGNORE|";
            String suffix = "|SKIP";
            byte[] packed = (prefix + text + suffix)
                    .getBytes(StandardCharsets.UTF_8);
            int offset = prefix.getBytes(StandardCharsets.UTF_8).length;
            byte[] wanted = text.getBytes(StandardCharsets.UTF_8);
            int length = wanted.length;
            HttpRequest.BodyPublisher slice =
                    HttpRequest.BodyPublishers.ofByteArray(
                            packed, offset, length);
            check(slice.contentLength() == length,
                    "slice publisher byte length");
            check(length > text.length(),
                    "UTF-8 byte length differs from String.length");
            byte[] echoed = post(client, url, slice,
                    "text/plain; charset=UTF-8");
            check(Arrays.equals(wanted, echoed), "UTF-8 slice bytes");
            check(Arrays.equals(wanted, observed.get()),
                    "server received only selected bytes");
            check(text.equals(new String(echoed, StandardCharsets.UTF_8)),
                    "UTF-8 slice text");
            check("text/plain; charset=UTF-8".equals(observedType.get()),
                    "text Content-Type");
            System.out.println("PASS offset and length for UTF-8");

            byte[] padded = new byte[] { 99, 65, 66, 67, 100 };
            HttpRequest.BodyPublisher middle =
                    HttpRequest.BodyPublishers.ofByteArray(padded, 1, 3);
            check(middle.contentLength() == 3, "middle slice length");
            check(Arrays.equals(new byte[] { 65, 66, 67 },
                    post(client, url, middle, "application/octet-stream")),
                    "middle slice");
            System.out.println("PASS excludes prefix and suffix");

            HttpRequest.BodyPublisher empty =
                    HttpRequest.BodyPublishers.ofByteArray(
                            padded, padded.length, 0);
            check(empty.contentLength() == 0,
                    "empty subrange has zero length");
            check(post(client, url, empty,
                    "application/octet-stream").length == 0,
                    "zero-length body response");
            check(observed.get().length == 0, "zero-length upload");
            System.out.println("PASS empty range");

            byte[] mutable = "SAFE".getBytes(StandardCharsets.UTF_8);
            byte[] snapshot = Arrays.copyOf(mutable, mutable.length);
            HttpRequest.BodyPublisher stable =
                    HttpRequest.BodyPublishers.ofByteArray(snapshot);
            mutable[0] = (byte) 'X';
            check("SAFE".equals(new String(
                    post(client, url, stable, "application/octet-stream"),
                    StandardCharsets.UTF_8)), "defensive snapshot");
            System.out.println("PASS defensive copy");

            invalid(padded, -1, 1);
            invalid(padded, 0, -1);
            invalid(padded, padded.length, 1);
            invalid(padded, 3, 3);
            invalid(padded, Integer.MAX_VALUE, Integer.MAX_VALUE);
            System.out.println("PASS invalid ranges rejected");

            System.out.println("ALL BYTE ARRAY RANGE TESTS PASSED");
        } finally {
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
~~~

### Chạy trên Java 11

Cần JDK 11 (hoặc JDK mới có hỗ trợ target 11) để biên dịch. Server test dùng module `jdk.httpserver` đi kèm JDK; **ứng dụng chỉ sử dụng `HttpClient` thật không cần import module server này**.

~~~bash
javac --release 11 --add-modules jdk.httpserver -encoding UTF-8 ByteArrayRangeDemo.java
java --add-modules jdk.httpserver -cp . ByteArrayRangeDemo
~~~

**Đầu ra chính xác khi các điều kiện thành công:**

~~~text
PASS full byte array
PASS offset and length for UTF-8
PASS excludes prefix and suffix
PASS empty range
PASS defensive copy
PASS invalid ranges rejected
ALL BYTE ARRAY RANGE TESTS PASSED
~~~

### Giải thích vì sao bài test này đáng tin

- Server dùng cổng tự cấp (`port 0`) trên loopback, nên không gọi API ngoài Internet và giảm xung đột cổng.
- Server đọc body bằng `InputStream.readAllBytes()` trong JDK 11 và trả về **đúng bytes đã nhận**; client kiểm `Arrays.equals` nên bắt được cả các byte `0x00` và `0xFF`.
- Client kiểm `BodyPublisher.contentLength()` bằng **số bytes** thật, không dùng `String.length()` cho văn bản UTF-8.
- Với phạm vi UTF-8, tiền tố/hậu tố chỉ dùng để minh họa loại bỏ dữ liệu không nằm trong range; chuỗi được gửi vẫn giữ tiếng Việt và ký tự bổ sung.
- Với phạm vi rỗng, server không cần phát response body; test xác minh upload thực sự có 0 byte.
- Với snapshot, chính mã ứng dụng `Arrays.copyOf` giữ dữ liệu độc lập với mảng `mutable`. Test **không** dựa vào một giả định không được Javadoc cam kết về thời điểm copy nội bộ của publisher.
- Mỗi phạm vi sai được kiểm tại lúc tạo publisher; phép thử không che giấu lỗi bằng cách gửi một đoạn khác.
- Bộ test sử dụng `check` ném `AssertionError` khi thất bại, không phụ thuộc tùy chọn `-ea` của Java.

`HttpClient.send(...)` trong ví dụ là đồng bộ để stdout ổn định và bài tập tập trung đúng vào **request body publisher**. Khi chuyển thành `sendAsync(...)`, các quy tắc về phạm vi và payload không đổi; phải đồng thời quản lý lỗi, timeout và vòng đời request theo ứng dụng.

## 7. Những lỗi thường gặp trong sản phẩm

### 7.1. Nhầm end index với length

~~~java
int start = 4;
int endExclusive = 9;

// Sai mục tiêu: 9 duoc hieu la 9 byte, khong phai end index.
HttpRequest.BodyPublisher wrong =
        HttpRequest.BodyPublishers.ofByteArray(buffer, start, 9);

// Dung: so byte = endExclusive - start.
HttpRequest.BodyPublisher right =
        HttpRequest.BodyPublishers.ofByteArray(
                buffer, start, endExclusive - start);
~~~

**Đây là đoạn minh họa** (cần có `buffer` đủ lớn), không phải một chương trình độc lập. Lỗi này có thể khiến request gửi dư payload hoặc ném `IndexOutOfBoundsException`.

### 7.2. Sử dụng `String.length()` làm byte count

~~~java
String text = "Ti\u1EBFng Vi\u1EC7t";
byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);

// Sai: do dai String la UTF-16 code units, khong phai byte UTF-8.
int wrongLength = text.length();

// Dung:
int byteLength = utf8.length;
HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.ofByteArray(utf8, 0, byteLength);
~~~

Nếu cần gửi nguyên một văn bản, `BodyPublishers.ofString(text, UTF_8)` thường rõ mục đích hơn. Nếu cần gửi dữ liệu byte đã có sẵn, `ofByteArray` là lựa chọn phù hợp.

### 7.3. Quên bảo vệ dữ liệu mutable

Mã khác có thể tái sử dụng mảng chứa request body trước khi publisher hoàn tất; khi ấy payload có nguy cơ không còn nhất quán. Chọn bản copy nếu cần snapshot, rồi giữ bản copy không bị sửa trong thời gian gửi. Không xem việc thay đổi `byte[]` sau khi tạo publisher là cách hợp lệ để «cập nhật request đang chờ».

### 7.4. Gửi kiểu nội dung sai

`ofByteArray` không biết dữ liệu là JSON, text, ảnh hay binary. Chọn `Content-Type` đúng theo giao thức như `application/octet-stream` cho binary, `text/plain; charset=UTF-8` cho văn bản UTF-8 hoặc `application/json` nếu bytes thực sự là JSON được mã hóa đúng. **Chỉ thay header không biến bytes bất kỳ thành JSON hợp lệ**.

### 7.5. Tưởng request body publisher đã gửi request

~~~java
HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.ofByteArray(payload);
~~~

Dòng này chỉ tạo **nguồn body**, chưa thực hiện I/O HTTP. Phải tạo `HttpRequest` có method/URL và gọi `HttpClient.send(...)` hoặc `sendAsync(...)`. Phân biệt thêm `BodyHandlers.ofByteArray()` dành cho **đọc response body**.

### 7.6. Gửi mảng quá lớn mà không xét bộ nhớ

`ofByteArray` làm việc với mảng `byte[]` đã ở trong RAM. Mảng có thể chiếm lượng bộ nhớ lớn, và publisher/HTTP Client có thể tạo thêm vùng đệm; không nên mặc định không có copy. Với file lớn hoặc payload stream, xem xét `BodyPublishers.ofFile` / `ofInputStream` và viết test cho việc tái gửi, giải phóng tài nguyên và xử lý lỗi. Chọn API theo tính chất dữ liệu, không dựa duy nhất vào tốc độ trên một bài microbenchmark.

### 7.7. Giả định một mask header mạng cụ thể

`contentLength()` cho biết số byte source chuẩn bị phát; nhưng trên HTTP/2 cách đóng khung dữ liệu khác HTTP/1.1. Đừng test thành công chỉ bằng sự có mặt của một `Content-Length` header ở mọi transport. So sánh **byte phía server nhận** và hành vi HTTP thực tế quan trọng hơn.

## 8. Câu hỏi tự đánh giá

**Câu 1.** Mảng có 5 phần tử, `ofByteArray(buf, 1, 3)` gửi những phần tử nào?

**Đáp án:** `buf[1]`, `buf[2]`, `buf[3]`. `length = 3` là số bytes cần lấy, không phải end index.

**Câu 2.** Muốn gửi phạm vi index `[3, 8)`, phải truyền `offset` và `length` bao nhiêu?

**Đáp án:** `offset = 3` và `length = 5`, với điều kiện mảng đủ lớn.

**Câu 3.** `ofByteArray(buf, buf.length, 0)` có hợp lệ không?

**Đáp án:** Có. Đây là phạm vi rỗng hợp lệ ngay sau phần tử cuối; `contentLength() == 0`.

**Câu 4.** `ofByteArray(buf, -1, 2)` gây gì?

**Đáp án:** `IndexOutOfBoundsException` vì offset âm.

**Câu 5.** Tại sao `ofByteArray("Tiếng Việt".getBytes(UTF_8), 0, "Tiếng Việt".length())` không phải cách chắc chắn để gửi toàn bộ văn bản?

**Đáp án:** `String.length()` đếm UTF-16 code units, không phải bytes UTF-8. Dùng `byteArray.length` sau khi mã hóa, hoặc `BodyPublishers.ofString(text, UTF_8)`.

**Câu 6.** Một byte `0xFF` trong mảng Java được hiển thị thành số âm. HTTP Client có chuyển nó thành ký tự hay xóa đi không?

**Đáp án:** Không. `byte` của Java mang dấu nhưng `0xFF` vẫn là octet có cùng bit pattern khi phát dữ liệu binary.

**Câu 7.** Vì sao nên dùng `Arrays.copyOfRange` trong một số trường hợp?

**Đáp án:** Để tạo snapshot byte độc lập với mảng nguồn mutable khi các luồng khác có thể chỉnh sửa nguồn trước/đang gửi. Cần xác minh offset/length trước, và không sửa snapshot trong lúc publisher sử dụng.

**Câu 8.** `BodyPublishers.ofByteArray` và `BodyHandlers.ofByteArray` khác nhau như thế nào?

**Đáp án:** `BodyPublishers` cung cấp bytes **gửi đi trong request**; `BodyHandlers` thu bytes **nhận về trong response**.

**Câu 9.** Nếu cắt một ký tự UTF-8 hai byte chỉ lấy byte đầu, lời gọi `ofByteArray` có tự ném lỗi «UTF-8 không hợp lệ» không?

**Đáp án:** Không. Về API, đây là byte range hợp lệ nếu chỉ số nằm trong mảng; việc giải mã thành text ở phía nhận mới có thể lỗi hoặc thay thế ký tự.

**Câu 10.** `BodyPublisher.contentLength()` cho range dài 3 trả về gì?

**Đáp án:** `3L` về mặt kiểu `long`: số bytes body, không phải số bytes của cả mảng nguồn.

## 9. Checklist hoàn thành

- [ ] Dùng đúng overload `ofByteArray(byte[])` hoặc `ofByteArray(byte[], offset, length)`.
- [ ] Tính phạm vi theo **bytes**, với `length = endExclusive - start`.
- [ ] Kiểm `offset >= 0` và `0 <= length <= buf.length - offset` (sau khi xác minh offset nằm trong mảng).
- [ ] Phân biệt phạm vi rỗng và phạm vi out-of-bounds.
- [ ] Hiểu `BodyPublisher.contentLength()` không phải số ký tự Java, và không dùng sai `Content-Length` header.
- [ ] Chỉ định `Content-Type` theo kiểu payload và kiểm body phía server nhận.
- [ ] Kiểm thử payload NUL, byte cao `FF`, UTF-8 tiếng Việt và supplementary code point.
- [ ] Không thay đổi mảng nguồn đang được dùng cho request; sao chép phạm vi nếu cần snapshot.
- [ ] Biết lúc nào nên chuyển sang `ofString`, `ofFile` hoặc `ofInputStream`.
- [ ] Biên dịch được ví dụ bằng `javac --release 11` và chạy đủ 6 nhóm PASS.
- [ ] Phân biệt rõ **request publisher** và **response body handler**.

## Tài liệu tham khảo chính thức

1. [Java SE 11 — HttpRequest.BodyPublishers: ofByteArray và overload offset/length](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html)
2. [Java SE 11 — HttpRequest.BodyPublisher: Flow.Publisher và contentLength](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html)
3. [Java SE 11 — HttpRequest.Builder: POST và header](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
4. [Java SE 11 — HttpClient: send và sendAsync](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html)
5. [Java SE 11 — HttpResponse.BodyHandlers: ofByteArray cho dữ liệu nhận](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
6. [Java SE 11 — java.util.Arrays: copyOfRange](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/Arrays.html)
7. [Java SE 26 — HttpRequest.BodyPublishers, đối chiếu các overload vẫn được hỗ trợ](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html)
