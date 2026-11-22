# Java 11+ — HTTP Request Body: Độ dài nội dung biết trước hoặc chưa biết

## 1. Vấn đề: vì sao HTTP client cần biết độ dài request body?

Khi gửi một HTTP request có **body** (ví dụ POST/PUT), Java HttpClient trong module `java.net.http` lấy byte nội dung từ một đối tượng **`HttpRequest.BodyPublisher`**. Một publisher không nhất thiết đã giữ sẵn toàn bộ nội dung: nó có thể biến một `String` thành byte, phát byte từ mảng, đọc tệp, đọc `InputStream` hoặc nhận một luồng dữ liệu `Flow.Publisher<ByteBuffer>`.

Độ dài request body được hiểu là **tổng số byte** cần gửi đi, không phải số ký tự Java, số dòng, số phần tử trong tập hợp hoặc dung lượng bộ nhớ của đối tượng. Có hai tình huống:

- **Known length (biết trước):** có thể xác định chính xác số byte trước khi bắt đầu phát body, ví dụ một mảng byte có kích thước cố định.
- **Unknown length (chưa biết):** dữ liệu có thể được tạo/đọc dần và chưa thể biết chính xác tổng byte trước khi stream hoàn tất.

Đây là một phần của Java 11 HttpClient vẫn còn áp dụng trên các bản Java hiện đại. Không nên thay bằng API cũ hay tự đặt header tùy tiện để “đoán” độ dài.

## 2. Hợp đồng cốt lõi của `BodyPublisher.contentLength()`

`HttpRequest.BodyPublisher` mở rộng `Flow.Publisher<ByteBuffer>` và cung cấp:

```java
long contentLength();
```

Theo Java API:

| Giá trị `contentLength()` | Ý nghĩa |
| --- | --- |
| `> 0` | Độ dài chính xác, bằng **số byte body mà publisher dự kiến sẽ phát**. |
| `== 0` | Không có byte body để gửi. HTTP client thậm chí có thể không subscribe publisher có độ dài 0. |
| `< 0` | Độ dài **không được biết trước**. Các publisher JDK thông dụng thường trả `-1` cho trường hợp này. |

**`-1` không có nghĩa “gửi âm một byte”, “body lỗi”, “EOF” hay “body rỗng”**. Nó chỉ là metadata nói rằng chưa xác định số byte. Body có độ dài chưa biết hoàn toàn có thể phát **0 byte**, 14 byte hoặc nhiều byte rồi kết thúc thành công.

Ngoài ra:

- `contentLength()` có thể được HttpClient gọi **trước** khi subscribe và **nhiều lần**; cùng publisher phải trả **một giá trị không đổi** qua các lần gọi.
- Các `ByteBuffer` được phát ra mới là dữ liệu thật. Giá trị content length **không** thay thế việc phát byte và hoàn thành `Flow.Publisher`.
- Khi một request cần được gửi lại, HttpClient có thể tạo **subscription mới**; publisher phải có khả năng cung cấp cùng body theo yêu cầu của hợp đồng.
- Metadata này mô tả **request body**. Nó **không** phải `HttpResponse`, `BodyHandler`, kích thước response, hay tổng kích thước HTTP request bao gồm header và framing.

`HttpRequest.Builder.POST(...)` nhận `BodyPublisher` và `HttpRequest.bodyPublisher()` trả `Optional<BodyPublisher>` để lấy metadata của một request đã xây dựng.

## 3. Những factory có độ dài biết trước

Các factory trong `HttpRequest.BodyPublishers` thường dùng khi số byte đã xác định:

### 3.1. Chuỗi: `ofString`

```java
HttpRequest.BodyPublisher body = HttpRequest.BodyPublishers.ofString("HELLO");
System.out.println(body.contentLength()); // 5 byte UTF-8
```

`ofString(String)` mã hóa chuỗi bằng **UTF-8**. Nếu muốn charset khác, dùng `ofString(String, Charset)` để chỉ định tường minh. Giá trị `contentLength()` là kích thước **sau khi mã hóa**, không phải `String.length()`.

Ví dụ tiếng Việt/emoji:

```java
String text = "Xin ch\u00E0o \uD83C\uDF0D"; // "Xin chào 🌍"
int utf16Units = text.length();  // 11 đơn vị UTF-16
int utf8Bytes = text.getBytes(StandardCharsets.UTF_8).length; // 14 byte
```

Java `String.length()` đếm đơn vị UTF-16; chữ có dấu và emoji có thể cần nhiều byte trong UTF-8. Vì vậy nếu định dạng request là JSON, text/plain hoặc bất cứ văn bản nào, hãy tính kích thước **đúng theo encoding và bytes thực tế**.

### 3.2. Mảng byte: `ofByteArray`

```java
byte[] payload = {10, 20, 30};
HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.ofByteArray(payload);
System.out.println(body.contentLength()); // 3
```

Bởi byte đã có sẵn, độ dài được biết trước. Với `ofByteArray(byte[], offset, length)`, nội dung là đoạn mảng được chỉ định, nên độ dài chính là `length` của đoạn — **không phải `buf.length`**. Offset/length không hợp lệ sẽ gây `IndexOutOfBoundsException`.

Với dữ liệu có thể bị bên khác sửa, nên thiết kế ownership rõ ràng; tránh thay đổi mảng gốc khi việc gửi body đang diễn ra. Khi body lớn, giữ toàn bộ byte trong RAM có thể không phù hợp.

### 3.3. Tệp: `ofFile(Path)`

```java
// Đoạn minh họa trong phương thức có xử lý FileNotFoundException/IOException.
Path file = Path.of("payload.bin");
HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.ofFile(file);
long expectedBytes = body.contentLength();
```

Publisher tệp có thể xác định kích thước bằng byte của tệp, và trong chương trình Java 11 kiểm chứng ở mục 7, tệp 14 byte cho `contentLength() == 14`. **Không cần đọc toàn bộ tệp vào byte[]** chỉ để tạo một request body.

Tuy nhiên, đừng sửa/ghi đè/xóa tệp trong lúc dùng nó làm body: metadata độ dài và byte thực tế có thể không còn nhất quán. Khi upload tệp thật, cần đảm bảo tệp tồn tại, quyền đọc hợp lệ và nội dung ổn định qua các lần gửi lại. Tệp lớn vẫn cần giới hạn dung lượng theo chính sách hệ thống.

### 3.4. Không có body: `noBody()`

```java
HttpRequest.BodyPublisher empty = HttpRequest.BodyPublishers.noBody();
System.out.println(empty.contentLength()); // 0
```

`noBody()` là **0 byte có chủ đích**, khác hẳn `-1` (chưa biết độ dài). `ofString("")` hay `ofByteArray(new byte[0])` cũng mô tả nội dung 0 byte. Việc HTTP request có body logic bằng 0 byte không tự động quyết định mọi header trong mọi phương thức HTTP; header sẽ được HttpClient và giao thức xử lý.

## 4. Những factory thường có độ dài chưa biết

### 4.1. Đọc stream khi gửi: `ofInputStream(Supplier<? extends InputStream>)`

```java
byte[] data = "HELLO".getBytes(StandardCharsets.UTF_8);
HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.ofInputStream(
                () -> new ByteArrayInputStream(data));
System.out.println(body.contentLength()); // -1 trong JDK
```

Dù `data.length` trong ví dụ là 5, **`ofInputStream` vẫn báo unknown length** vì hợp đồng factory là stream được đọc dần. Trường hợp biết kích thước thực sự nhưng dùng factory unknown length **không có nghĩa dữ liệu sẽ bị mất**.

**Supplier phải cung cấp một `InputStream` mới đang mở** mỗi khi cần phát lại body. Tránh các mẫu sai:

```java
// Sai về replay: tái sử dụng một stream đã bị đọc hết/đã đóng.
InputStream oneShot = new ByteArrayInputStream(data);
HttpRequest.BodyPublisher unsafe =
        HttpRequest.BodyPublishers.ofInputStream(() -> oneShot);
```

Với tệp, có thể tạo stream mới bằng supplier:

```java
// Minh họa ý tưởng, cần xử lý IOException khi mở tệp.
// java.util.function.Supplier không khai báo checked IOException:
HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.ofInputStream(() -> {
            try {
                return Files.newInputStream(file);
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        });
```

Đoạn này dùng `java.nio.file.Files`, `java.nio.file.Path` và `java.io.UncheckedIOException`; `file` là `Path` được khai báo ở môi trường bao. Nhưng nếu đã có file thông thường, `ofFile(file)` thường đơn giản hơn và có thể báo độ dài biết trước. Nếu supplier bất ngờ trả `null` trong lần gửi lại, request có thể thất bại; phải có chính sách replay phù hợp khi upload dữ liệu không thể mở lại.

### 4.2. Iterable các mảng byte: `ofByteArrays`

```java
List<byte[]> chunks = Arrays.asList(new byte[]{1}, new byte[]{2, 3});
HttpRequest.BodyPublisher parts =
        HttpRequest.BodyPublishers.ofByteArrays(chunks);
System.out.println(parts.contentLength()); // -1 trong JDK được kiểm thử
```

Ví dụ cần import `java.util.List` và `java.util.Arrays`. Dù lập trình viên có thể nhìn thấy 3 byte trong `chunks`, factory `ofByteArrays(Iterable<byte[]>)` không nhất thiết tính trước tổng độ dài. `Iterable` có thể tạo các phần dữ liệu tại thời điểm lặp; mỗi lần gửi lại request có thể yêu cầu một iterator mới. Hãy đảm bảo dữ liệu có thể lặp lại nhất quán, không phụ thuộc vào một iterator one-shot đã tiêu thụ.

### 4.3. Adapter từ `Flow.Publisher<ByteBuffer>`

Java 11 có hai overload:

```java
HttpRequest.BodyPublisher unknown =
        HttpRequest.BodyPublishers.fromPublisher(flowPublisher);

HttpRequest.BodyPublisher known =
        HttpRequest.BodyPublishers.fromPublisher(flowPublisher, exactByteCount);
```

Trong đó `flowPublisher` là `Flow.Publisher<? extends ByteBuffer>` đã được tạo, `exactByteCount` là `long` dương đã xác định **chính xác**. Hai dòng là minh họa trong phương thức có khai báo biến tương ứng.

- `fromPublisher(flowPublisher)`: `contentLength() == -1`, không xác định tổng byte.
- `fromPublisher(flowPublisher, exactByteCount)`: `contentLength() == exactByteCount`, **phải đúng bằng số byte publisher thực sự phát**.
- `exactByteCount <= 0`: overload thứ hai ném `IllegalArgumentException`. Muốn gửi 0 byte, dùng `noBody()` hoặc `ofByteArray(new byte[0])` thay vì truyền 0 vào overload positive-only.

**Cẩn thận:** overload có content length **không tự đo byte thực tế** và không tự biến nguồn không xác định thành nguồn có độ dài đúng. Bạn đang **cam kết** với HTTP client rằng tổng byte phát ra bằng giá trị khai báo. Nếu stream phát thiếu hoặc thừa, có thể gây lỗi truyền, lỗi giao thức, hủy request hoặc khiến bên nhận chờ/sai framing. Đừng “ước lượng” rồi đưa vào overload này.

Nếu custom `BodyPublisher` được tự triển khai, `contentLength()` phải trả một số cố định không đổi qua nhiều lời gọi. Khi chưa xác định chính xác, trả giá trị âm theo hợp đồng (thường `-1`) thay vì dự đoán; đồng thời tuân thủ `Flow.Publisher`, backpressure, subscription mới và vòng đời `ByteBuffer`.

## 5. Known và unknown length ảnh hưởng HTTP wire-format thế nào?

`BodyPublisher.contentLength()` là **metadata đầu vào cho HttpClient**. Nó không phải cú pháp byte trực tiếp của HTTP. Tùy phiên bản HTTP được sử dụng và trạng thái request, HttpClient sẽ quyết định cách đóng khung nội dung:

| Trường hợp | Cơ chế thường gặp |
| --- | --- |
| **HTTP/1.1, body có độ dài biết trước** | Client thường dùng `Content-Length` bằng đúng số byte. |
| **HTTP/1.1, body có độ dài chưa biết** | Client thường dùng `Transfer-Encoding: chunked` để truyền theo từng chunk mà không phải biết tổng số byte trước. |
| **HTTP/2** | Body được gửi trong các **DATA frame** và kết thúc luồng bằng cờ kết thúc tương ứng; không dùng `Transfer-Encoding: chunked` của HTTP/1.1. |
| Body rỗng | Cách thể hiện `Content-Length`/không có body phụ thuộc phương thức và chi tiết HTTP client/protocol; về mặt `BodyPublisher`, lượng byte là 0. |

**Đây là hành vi framing, không phải thao tác để bạn tự gắn header trong builder.** Trong JDK HttpClient, `Content-Length` là một header hạn chế (restricted) đối với code ứng dụng theo cấu hình mặc định, vì HttpClient có trách nhiệm xác định theo publisher. Làm điều sau thường sai:

```java
// KHÔNG làm như vậy để ép độ dài body:
HttpRequest.newBuilder(uri)
        .header("Content-Length", "14")
        .POST(publisher)
        .build();
```

Đoạn trên chỉ minh họa **anti-pattern**, không phải code cần chạy; `uri` và `publisher` phải được khai báo nếu sử dụng. Việc cố tự đặt header có thể ném `IllegalArgumentException` và nếu vượt rào bảo vệ bằng cấu hình riêng còn có thể gây vấn đề giao thức. Hãy chọn đúng `BodyPublisher` và khai báo độ dài bằng API publisher khi thật sự có số byte chính xác.

Một số server/proxy HTTP/1.1 yêu cầu `Content-Length` và có thể trả **411 Length Required** khi client gửi body dạng chunked. Đây là ràng buộc của đầu nhận, **không phải lý do để bịa độ dài**. Khi yêu cầu biết độ dài trước, có thể tính đúng byte, dùng mảng byte/tệp ổn định hoặc buffer giới hạn để biết tổng kích thước trước khi gửi.

**Không suy ra header thực tế chỉ từ `HttpRequest.bodyPublisher().get().contentLength()`**: một request chưa được gửi có thể được thực thi bằng phiên bản HTTP khác với phiên bản bạn mong đợi, và cách dựng header/framing do client quyết định.

## 6. Độ dài byte, Unicode, dữ liệu rỗng và nội dung sinh động

Giả sử bạn chuẩn bị gửi JSON:

```java
String json = "{\"message\":\"Xin ch\u00E0o\"}";
byte[] encoded = json.getBytes(StandardCharsets.UTF_8);
long length = encoded.length;
```

Các độ dài sau **không luôn bằng nhau**:

- `json.length()`: số đơn vị mã UTF-16 của Java `String`.
- `json.codePointCount(0, json.length())`: số Unicode code point, chưa chắc bằng số ký tự hiển thị.
- `encoded.length`: số **byte** sau khi mã hóa UTF-8; đây mới là kích thước liên quan đến request body.
- `publisher.contentLength()`: metadata byte do publisher báo; có thể là số chính xác hoặc âm (unknown).

Không cộng độ dài theo `String.length()` rồi gán làm body length khi gửi UTF-8. Tương tự, **nén, mã hóa, chuyển đổi base64, multipart boundary, hay thêm ký tự xuống dòng** sẽ làm số byte cuối cùng khác nội dung ban đầu. Chỉ khai báo known length khi bạn tính trên **byte thực sự sẽ được phát đi**, bao gồm phần metadata của multipart nếu có.

Với payload sinh động không biết tổng size, streaming là lựa chọn hợp lý. `-1` không đồng nghĩa kém an toàn; nhưng bạn vẫn cần đặt **giới hạn tổng dữ liệu**, giới hạn thời gian, backpressure và xử lý lỗi. Nếu ứng dụng cần một tệp/stream có thể gửi lại, thiết kế replayability rõ ràng.

## 7. Ví dụ Java 11+ chạy độc lập: đo và so sánh các publisher

Ví dụ này **không gửi request ra Internet**, chỉ tạo publisher và xem metadata để tập trung đúng vào chủ đề known/unknown length. Một `HttpRequest` được tạo với URI minh họa, nhưng không gọi `HttpClient.send(...)`.

Lưu thành tệp **`HttpBodyLengthDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpRequest;
import java.net.http.HttpRequest.BodyPublisher;
import java.net.http.HttpRequest.BodyPublishers;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.concurrent.Flow;

public final class HttpBodyLengthDemo {
    public static void main(String[] args) throws IOException {
        String text = "Xin ch\u00E0o \uD83C\uDF0D";
        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
        System.out.println("utf16-units=" + text.length());
        System.out.println("utf8-bytes=" + utf8.length);

        BodyPublisher fromString = BodyPublishers.ofString(text);
        BodyPublisher fromBytes = BodyPublishers.ofByteArray(utf8);
        BodyPublisher fromStream = BodyPublishers.ofInputStream(
                () -> new ByteArrayInputStream(utf8));
        BodyPublisher fromParts = BodyPublishers.ofByteArrays(Arrays.asList(
                new byte[]{1}, new byte[]{2, 3}));

        Flow.Publisher<? extends ByteBuffer> source = fromBytes;
        BodyPublisher dynamicAdapter = BodyPublishers.fromPublisher(source);
        BodyPublisher fixedAdapter = BodyPublishers.fromPublisher(source, utf8.length);

        Path file = Files.createTempFile("http-body-", ".txt");
        try {
            Files.write(file, utf8);
            BodyPublisher fromFile = BodyPublishers.ofFile(file);

            System.out.println("string-length=" + fromString.contentLength());
            System.out.println("bytes-length=" + fromBytes.contentLength());
            System.out.println("file-length=" + fromFile.contentLength());
            System.out.println("stream-length=" + fromStream.contentLength());
            System.out.println("parts-length=" + fromParts.contentLength());
            System.out.println("adapter-unknown=" + dynamicAdapter.contentLength());
            System.out.println("adapter-fixed=" + fixedAdapter.contentLength());
            System.out.println("no-body=" + BodyPublishers.noBody().contentLength());

            HttpRequest request = HttpRequest.newBuilder(
                    URI.create("https://example.invalid/upload"))
                    .header("Content-Type", "text/plain; charset=UTF-8")
                    .POST(fromStream)
                    .build();
            System.out.println("request-body-length=" +
                    request.bodyPublisher().orElseThrow().contentLength());

            try {
                BodyPublishers.fromPublisher(source, 0L);
                System.out.println("fixed-zero=unexpected-success");
            } catch (IllegalArgumentException ex) {
                System.out.println("fixed-zero=IllegalArgumentException");
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy bằng **JDK 11 trở lên**. Tham số `--release 11` kiểm tra cú pháp và API tương thích Java 11:

```bash
javac -encoding UTF-8 --release 11 HttpBodyLengthDemo.java
java HttpBodyLengthDemo
```

**Stdout đã kiểm chứng:**

```text
utf16-units=11
utf8-bytes=14
string-length=14
bytes-length=14
file-length=14
stream-length=-1
parts-length=-1
adapter-unknown=-1
adapter-fixed=14
no-body=0
request-body-length=-1
fixed-zero=IllegalArgumentException
```

Giải thích các dòng đầu ra:

1. `utf16-units=11` nhưng `utf8-bytes=14` chứng minh byte count khác độ dài `String` với tiếng Việt và emoji.
2. `string-length`, `bytes-length`, `file-length` đều là 14 trong dữ liệu kiểm chứng. Đó là số byte UTF-8 được dùng trong mỗi trường hợp.
3. `stream-length=-1` và `parts-length=-1` cho biết hai factory này không báo tổng byte trước; không có byte nào được gửi đi trong chương trình.
4. `adapter-unknown=-1` dù đầu vào `source` vốn là một `BodyPublisher` biết độ dài; overload một tham số **chủ ý** tạo adapter unknown.
5. `adapter-fixed=14` chứng minh overload hai tham số nhận **độ dài byte đã xác định chính xác**.
6. `no-body=0` khác hoàn toàn `-1`.
7. `request-body-length=-1` lấy publisher từ `HttpRequest` đã build và đọc metadata; không có request thực sự được gửi đến hostname `example.invalid`.
8. `fixed-zero=IllegalArgumentException` vì overload có contentLength chỉ chấp nhận giá trị **dương**.
9. `finally` xóa tệp tạm, tránh để lại dữ liệu trong thư mục dự án.

## 8. Ví dụ gửi HTTP request với known hoặc unknown body

Khi thực sự gửi request, bạn tạo publisher **trước** và chuyển nó cho builder:

```java
// Đoạn minh họa trong phương thức có đủ import và xử lý IOException/InterruptedException.
// endpoint là URI được cấu hình, bytes là byte[]; client là HttpClient.

HttpRequest knownLength = HttpRequest.newBuilder(endpoint)
        .header("Content-Type", "application/octet-stream")
        .POST(HttpRequest.BodyPublishers.ofByteArray(bytes))
        .build();

HttpRequest unknownLength = HttpRequest.newBuilder(endpoint)
        .header("Content-Type", "application/octet-stream")
        .POST(HttpRequest.BodyPublishers.ofInputStream(
                () -> new ByteArrayInputStream(bytes)))
        .build();

// Ví dụ cách gửi đồng bộ:
// HttpResponse<Void> reply = client.send(knownLength,
//         HttpResponse.BodyHandlers.discarding());
```

Đoạn này **chỉ là ví dụ tích hợp**, không độc lập như chương trình ở mục 7; cần import `java.net.http.HttpClient`, `HttpRequest`, `HttpResponse`, `java.net.URI`, `java.io.ByteArrayInputStream` và định nghĩa `endpoint`/`bytes`/`client`.

Với dữ liệu nhỏ đã nằm trong `byte[]`, `ofByteArray` thường rõ ràng và có độ dài biết trước. Với nguồn lớn hoặc sinh theo thời gian, `ofInputStream`/`fromPublisher` không khai báo độ dài có thể tránh buffer toàn bộ payload, nhưng cần thiết kế luồng và replayability.

**Request body không đồng nghĩa response body.** `HttpResponse.BodyHandlers.discarding()` trong dòng minh họa chỉ bỏ **nội dung phản hồi**; nó không thay đổi độ dài byte của request đã gửi.

## 9. Độ dài sai và cách phòng lỗi

### 9.1. Khi khai báo known length sai

Giả sử publisher thực sự phát 14 byte nhưng developer viết:

```java
// Ví dụ lỗi logic: tuyên bố 10 byte cho nguồn thực tế phát 14 byte.
HttpRequest.BodyPublisher wrong =
        HttpRequest.BodyPublishers.fromPublisher(source, 10L);
```

Factory có thể xây dựng đối tượng vì `10L > 0`; **nó không tự kiểm tra dữ liệu khi tạo publisher**. Sai lệch có thể chỉ bị phát hiện khi phát request và gây lỗi truyền hoặc framing. Đừng coi việc gọi factory thành công là bằng chứng số byte đúng.

### 9.2. Khi không biết chắc tổng byte

Dùng:

```java
HttpRequest.BodyPublisher unknown =
        HttpRequest.BodyPublishers.fromPublisher(source);
```

Hoặc `ofInputStream` với supplier phát stream mới. **Không** dùng `0` để đại diện “chưa biết” vì 0 là body rỗng theo `contentLength()`, còn overload fixed length của `fromPublisher` từ chối 0.

### 9.3. Khi cần fixed length mà dữ liệu sinh động

Một hướng giải quyết là ghi dữ liệu vào tệp tạm hoặc một bộ đệm **có giới hạn kích thước**, xác định byte count, cố định nội dung rồi dùng `ofFile`/`ofByteArray`. Cách làm này tốn I/O hoặc RAM bổ sung, đổi lại dễ đáp ứng server/proxy bắt buộc biết độ dài.

Nếu chọn file upload, giữ file không đổi trong suốt vòng đời request và xử lý retry. Không cần “đọc hết stream trước để đếm, rồi tiếp tục đọc chính stream đã hết”; nguồn một lần đọc có thể không reset được.

## 10. Replay, retry và backpressure là vấn đề độc lập với độ dài

`BodyPublisher` là `Flow.Publisher<ByteBuffer>`. Khi HttpClient gửi request, client subscribe để lấy byte. Khi xảy ra việc **gửi lại** do một số tình huống redirect/xác thực/connection handling, publisher có thể phải tạo lại dòng byte:

- `ofString`, `ofByteArray`: thường dễ tái phát cùng dữ liệu đã có.
- `ofFile`: nội dung tệp phải ổn định và vẫn đọc được trong lần gửi mới.
- `ofInputStream(supplier)`: **mỗi lần mở phải cung cấp stream mới** cho cùng nội dung nếu request cần được replay. Đưa cùng một `InputStream` đã tiêu thụ vào mọi lần gọi là lỗi thiết kế.
- `fromPublisher(flowPublisher)`: publisher nguồn phải tuân thủ quy tắc `Flow`, hỗ trợ subscription theo điều kiện ứng dụng và có thể phát đúng dữ liệu khi cần gửi lại.

Độ dài được báo đúng **không tự bảo đảm** replayability, backpressure, memory safety, idempotency hay thành công mạng. POST có thể không an toàn khi tự gửi lại ở cấp ứng dụng; chỉ retry khi yêu cầu và server có cơ chế chống tạo tác dụng phụ trùng lặp (ví dụ idempotency key, nếu API hỗ trợ).

Trong custom publisher, không tái sử dụng hoặc sửa một `ByteBuffer` sau khi đã giao nó cho HttpClient khi hợp đồng yêu cầu publisher không truy cập lại buffer đó; xử lý `Subscription.request(n)` và `cancel()` đúng. Với dữ liệu đầu vào không đáng tin cậy, thiết lập quota cho số byte thực tế, timeout và hủy request dù `contentLength() == -1`.

## 11. Nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`contentLength() == -1` tức là body rỗng.” | Không: **-1 = chưa biết**, còn 0 là rỗng. |
| “`contentLength()` là số ký tự `String.length()`.” | Không: tính theo **byte** sau encoding. |
| “Có một mảng byte nguồn nên `ofInputStream` tự biết length.” | Không: factory này báo unknown length trong JDK, kể cả khi supplier đọc mảng byte. |
| “Dùng `ofByteArrays` thì JVM cộng sẵn mọi phần tử.” | Factory này có thể báo unknown length; không giả định tổng byte được tính trước. |
| “`fromPublisher(source, 0)` biểu diễn body rỗng.” | Overload có length yêu cầu **số dương**; dùng `noBody()` hoặc mảng byte rỗng. |
| “Có thể đoán 10 byte rồi khai báo, nếu sai client sẽ tự sửa.” | Known length phải **chính xác**. Sai lệch có thể làm request thất bại. |
| “`contentLength()` âm nghĩa HTTP/1.1 luôn phải có `Content-Length: -1`.” | Không bao giờ coi số âm là header truyền tải; HTTP/1.1 có thể dùng chunked. |
| “HTTP/2 dùng chunked Transfer-Encoding giống HTTP/1.1.” | Không: HTTP/2 dùng DATA frames và cơ chế kết thúc luồng của HTTP/2. |
| “Gắn `header("Content-Length", "...")` là cách chuẩn.” | Không: HttpClient quyết định header/framing và hạn chế set `Content-Length` theo mặc định. |
| “Tệp không đổi kích thước nhưng có thể đổi nội dung trong lúc gửi.” | Rủi ro body bị thay đổi hoặc replay sai; giữ đầu vào ổn định. |
| “`ofInputStream(() -> sameStream)` có thể retry thoải mái.” | Phải cung cấp stream mới và dữ liệu có thể phát lại. |
| “Publisher biết length sẽ không tốn RAM, không cần giới hạn.” | Length chỉ là metadata; chọn nguồn/buffer và áp dụng quota phù hợp. |

## 12. Checklist chọn publisher cho request body

1. **Xác định byte đã cố định chưa.** Nếu đã có `String`/`byte[]` nhỏ hoặc tệp ổn định, chọn `ofString`, `ofByteArray` hoặc `ofFile`.
2. **Tính độ dài theo byte.** Với văn bản dùng đúng charset: `text.getBytes(charset).length`; không dùng `String.length()` làm `Content-Length`.
3. **Nếu chưa biết độ dài,** dùng `ofInputStream(supplier)` hoặc `fromPublisher(publisher)`; chấp nhận metadata `-1`.
4. **Nếu biết chính xác độ dài stream,** `fromPublisher(publisher, positiveExactBytes)` có thể dùng, nhưng phải bảo đảm tổng byte phát thực tế bằng số khai báo.
5. **Body rỗng:** dùng `noBody()` hoặc một publisher 0 byte; không nhầm với unknown length.
6. **Không tự ép `Content-Length` header** trong `HttpRequest.Builder`. Hãy để HttpClient quyết định framing theo body publisher và HTTP version.
7. **Xử lý retry/replay:** nguồn file, mảng hoặc stream supplier phải cung cấp cùng dữ liệu khi client subscribe lại; kiểm soát tính nhất quán nghiệp vụ.
8. **Giới hạn tài nguyên:** kích thước tối đa, bộ nhớ, tệp tạm, timeout, cancellation và backpressure, nhất là với unknown length.
9. **Xét yêu cầu server:** nếu hệ thống đích yêu cầu fixed length, chuẩn bị byte count chính xác bằng một quy trình có thể bảo toàn nội dung; đừng khai báo ước lượng.
10. **Kiểm thử ở hai lớp:** kiểm tra `contentLength()` (đặc biệt 0 và -1), sau đó dùng server test để xác minh **byte thực tế nhận được** và framing theo HTTP/1.1 hoặc HTTP/2 khi cần. Chỉ kiểm tra metadata chưa chứng minh truyền mạng thành công.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 11 — `HttpRequest.BodyPublisher`, định nghĩa `contentLength()`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html)
- [Oracle Java SE 11 — `HttpRequest.BodyPublishers` và tất cả factory Java 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html)
- [Oracle Java SE 25 — `BodyPublishers` hiện hành](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html)
- [Oracle Java SE 11 — `HttpClient`, gửi yêu cầu và các phiên bản HTTP](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html)
- [RFC 9112 — HTTP/1.1: body framing và tình huống `411 Length Required`](https://www.rfc-editor.org/rfc/rfc9112.html)
