# Java HttpClient: gửi String, byte[], file và InputStream bằng BodyPublishers

## 1. Bối cảnh và mục tiêu

Khi gọi một HTTP API từ Java, phần **request body** có thể là văn bản JSON, một mảng byte nhị phân, nội dung tệp trên đĩa, hoặc dữ liệu chỉ đọc được lần lượt từ `InputStream`. Trong Java 17+, `java.net.http.HttpClient` cung cấp `HttpRequest.BodyPublishers` để mô tả **các byte sẽ gửi** mà không bắt mọi loại nguồn dữ liệu phải biến thành một `String` hay mảng byte trong heap.

Bốn lựa chọn trọng tâm của bài:

~~~java
HttpRequest.BodyPublishers.ofString(text, StandardCharsets.UTF_8)
HttpRequest.BodyPublishers.ofByteArray(bytes)
HttpRequest.BodyPublishers.ofFile(path)
HttpRequest.BodyPublishers.ofInputStream(streamSupplier)
~~~

Đây là **biểu thức minh họa**; cần đặt trong phương thức đã khai báo `text`, `bytes`, `path` và `streamSupplier`. Từng biểu thức trả về một `HttpRequest.BodyPublisher` có thể truyền vào `POST(...)` hoặc `method("PUT", publisher)`. Sự khác biệt quan trọng nằm ở **nguồn byte, cách mã hóa, kích thước được biết trước, thời điểm đọc và khả năng gửi lại**.

Sau khi học, bạn có thể: chọn đúng publisher cho String/byte[]/file/InputStream; khai báo `Content-Type` phù hợp; hiểu `contentLength()`, UTF-8 và request framing; triển khai upload không cần đọc cả tệp vào RAM; xử lý stream supplier an toàn; phân biệt request `BodyPublisher` với response `BodyHandler`; và chạy demo Java 17+ gửi cả bốn loại tới HTTP server loopback.

## 2. Nhìn tổng thể HTTP request body và BodyPublisher

Một request HTTP có **request line/method**, **headers** và **body**. Ví dụ:

~~~http
POST /messages HTTP/1.1
Host: api.example.test
Content-Type: application/json; charset=utf-8
Content-Length: 23

{"message":"hello Java"}
~~~

`Content-Length: 23` chỉ là ví dụ tính theo **byte** của đoạn body ASCII minh họa, không phải một giá trị do bạn luôn phải ghi bằng tay. Khi gửi một String có ký tự tiếng Việt hoặc emoji, **số ký tự Java và số byte UTF-8 có thể khác nhau**. `Content-Type` nói body là định dạng gì; `Content-Length` (nếu có) nói số byte trên wire. Cả hai không do nội dung `String` tự làm cho server đoán được đúng.

Luồng Java `HttpClient`:

~~~text
               Java application
                      |
                      | tạo HttpRequest
                      v
HttpRequest.BodyPublisher (String / byte[] / File / InputStream)
                      |
                      | cung cấp ByteBuffer theo Flow.Publisher contract
                      v
                HttpClient
                      |
                      | HTTP framing: HTTP/1.1 hoặc HTTP/2
                      v
               HTTP request bytes
                      |
                 Network / TLS
                      v
                 HTTP server
                      |
               đọc request body
                      v
                 gửi response
                      |
                      v
HttpResponse.BodyHandler<T> -> response body T
~~~

`BodyPublisher` **xuất bản body của request**, không phải parser/reader response. Đối với dữ liệu **nhận về**, client dùng `BodyHandlers.ofString()`, `ofByteArray()`, `ofFile()`, `ofInputStream()`... với semantics khác. Hai nhóm API thường có tên giống nhau nhưng **hai chiều dữ liệu ngược nhau**.

### 2.1. Lúc build request chưa chắc đã gửi byte nào

~~~java
HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://api.example.test/upload"))
        .header("Content-Type", "text/plain; charset=utf-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                "Xin chào", StandardCharsets.UTF_8))
        .build();

// Chưa gọi client.send() hoặc client.sendAsync():
// request được cấu hình, không có request mạng nào do riêng build() tạo ra.
~~~

Mã trên là **đoạn minh họa** (cần import `java.net.URI`, `java.net.http.HttpRequest` và `java.nio.charset.StandardCharsets`). `HttpRequest` mô tả phương thức/URI/headers/body; `HttpClient.send(...)` hoặc `sendAsync(...)` mới thực hiện việc truyền.

Cụ thể với file hoặc InputStream, việc tạo BodyPublisher **không có nghĩa tất cả nội dung đã được đọc hết**. Đó là lợi ích quan trọng khi dữ liệu lớn, nhưng cũng yêu cầu **giữ nguồn dữ liệu khả dụng tới lúc request thực sự hoàn tất**.

## 3. Bảng chọn nhanh bốn loại BodyPublisher

| Nguồn body | API | Nguồn byte | `contentLength()` điển hình | Tình huống |
| --- | --- | --- | --- | --- |
| `String` | `BodyPublishers.ofString(text, charset)` | Encode String theo charset | **Biết trước** sau encode | JSON, văn bản, XML nhỏ/vừa |
| `byte[]` | `BodyPublishers.ofByteArray(bytes)` | Byte nhị phân đã có trong RAM | **Biết trước** theo số byte | Protobuf, ảnh/byte nhị phân đã tạo |
| Tệp `Path` | `BodyPublishers.ofFile(path)` | Nội dung file trên filesystem | **Thường biết** từ kích thước file | Upload một file lớn mà không `readAllBytes` |
| `InputStream` supplier | `BodyPublishers.ofInputStream(supplier)` | Stream được supplier mở khi publisher cần | **-1**, tức không biết trước | Dữ liệu sinh dần hoặc stream từ nguồn khác |

**Giới hạn:** các ô “biết trước” mô tả `BodyPublisher.contentLength()`, **không phải bảo đảm một header Content-Length cụ thể sẽ xuất hiện trong mọi phiên bản HTTP**. Với HTTP/1.1, body không biết độ dài có thể sử dụng chunked transfer coding; với HTTP/2, payload đi trong DATA frames và quy tắc framing khác. Hãy để `HttpClient` quản lý wire framing; đừng tự đặt `Transfer-Encoding`/`Content-Length` để ép kết quả không phù hợp.

Trong bài, String và byte[] nhỏ có thể dùng bộ nhớ sẵn; tệp lớn nên dùng `ofFile`; khi chỉ có một nguồn sinh/đọc theo luồng và **có thể cấp stream mới khi cần**, dùng `ofInputStream`.

## 4. `BodyPublishers.ofString`: gửi văn bản và chọn charset

### 4.1. Hai overload phổ biến

~~~java
HttpRequest.BodyPublisher a =
        HttpRequest.BodyPublishers.ofString("Hello");
// Mặc định UTF-8 trong overload không chỉ định charset.

HttpRequest.BodyPublisher b =
        HttpRequest.BodyPublishers.ofString(
                "Xin chào", StandardCharsets.UTF_8);
// Chỉ định charset tường minh, tránh hiểu nhầm encoding.
~~~

Mã minh họa cần import `java.net.http.HttpRequest` và `java.nio.charset.StandardCharsets`. `ofString` chuyển String thành byte theo charset được chọn. Bản thân client không tự suy ra header `Content-Type` chỉ vì publisher nhận String; **bạn phải khai báo media type hợp đồng API yêu cầu**.

Ví dụ gửi JSON:

~~~java
String json = "{\"name\":\"Mai\",\"active\":true}";

HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://api.example.test/users"))
        .header("Content-Type", "application/json; charset=utf-8")
        .header("Accept", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(
                json, StandardCharsets.UTF_8))
        .build();
~~~

Đây là **mã minh họa không có `main`**; cần import `java.net.URI` và `HttpRequest`. `Content-Type` mô tả **request body bạn gửi**; `Accept` mô tả **các representation bạn muốn ở response**. Hai header không thay thế nhau.

### 4.2. Số ký tự không bằng số byte UTF-8

~~~java
String text = "Xin chào";
byte[] encoded = text.getBytes(StandardCharsets.UTF_8);
System.out.println(text.length());      // 8 UTF-16 code units.
System.out.println(encoded.length);     // 9 bytes UTF-8.
~~~

Chữ `à` chiếm một UTF-16 code unit nhưng **hai byte UTF-8**. Nếu server/khách hàng áp dụng giới hạn 10 KiB hoặc một giao thức yêu cầu độ dài payload, phải xét **độ dài byte**, không lấy `text.length()` làm số byte. Emoji thường còn có nhiều UTF-16 code units và byte UTF-8 khác nữa.

Trong demo chạy được ở phần 9, ta viết chữ `à` dưới dạng escape Java `\u00e0` để chuỗi đầu ra vẫn là **“Xin chào”**, đồng thời tránh lệ thuộc vào encoding khi copy code qua một số shell/terminal.

### 4.3. Ưu/nhược điểm của ofString

**Phù hợp:** request body là text đã được tạo sẵn như JSON, một biểu mẫu được serialize trước, XML hoặc plain text. API dễ đọc, ít boilerplate.

**Cần lưu ý:** String phải tồn tại trong bộ nhớ và publisher encode thành byte; nếu JSON/text rất lớn, đồng thời có nhiều requests, dễ phát sinh bộ nhớ đỉnh cao. Với nội dung được tạo dần, cân nhắc InputStream supplier hoặc cách publish byte chunks; không cố ghép nhiều gigabyte vào một String.

Không tự nối chuỗi JSON bằng cách đưa thẳng dữ liệu user mà không escape; hãy dùng JSON serializer đúng chuẩn và validate schema. `ofString` chỉ mã hóa **text sang byte**, không tự bảo đảm JSON hợp lệ hay chống injection.

## 5. `BodyPublishers.ofByteArray`: khi đã có byte nhị phân

### 5.1. Gửi mảng byte nguyên vẹn

~~~java
byte[] payload = {0x00, 0x01, (byte) 0xFF, 0x7F};

HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://api.example.test/binary"))
        .header("Content-Type", "application/octet-stream")
        .POST(HttpRequest.BodyPublishers.ofByteArray(payload))
        .build();
~~~

Mã minh họa cần import `java.net.URI`/`HttpRequest`. `(byte) 0xFF` có giá trị `-1` trong kiểu `byte` có dấu của Java nhưng **giữ nguyên bit byte `FF` khi gửi**. Đừng biến dữ liệu nhị phân bất kỳ thành String nếu không có một encoding văn bản thực sự; nó có thể mất thông tin hoặc thay thế các byte không hợp lệ.

**Độ dài publisher = số byte**. Ví dụ trên có 4 byte, `contentLength() == 4`. Khác với `String`, không có bước encode charset khi bạn đã sở hữu đúng bytes.

### 5.2. Chỉ gửi một lát cắt

Nếu muốn gửi một đoạn trong mảng:

~~~java
byte[] all = {9, 8, 7, 6, 5, 4};

// Gửi ba byte bắt đầu tại offset=2: {7,6,5}.
HttpRequest.BodyPublisher portion =
        HttpRequest.BodyPublishers.ofByteArray(all, 2, 3);
~~~

**`offset` là vị trí bắt đầu**, `length` là **số byte gửi**, không phải vị trí kết thúc. Đoạn trên có `contentLength()==3`. Cần kiểm tra offset/length trong phạm vi mảng; nếu tham số không hợp lệ, API sẽ báo lỗi thay vì tự đoán vùng byte.

### 5.3. Mảng mutable và chuyện gửi lại

Mảng `byte[]` là đối tượng có thể sửa. Khi làm việc với publisher/request có thể được gửi bất đồng bộ hoặc chuyển qua thread khác, **đừng sửa nội dung mảng** trong quá trình xây dựng và truyền body. Nếu nguồn đang được thread khác cập nhật, hãy tạo snapshot được kiểm soát hoặc đồng bộ ở tầng ứng dụng để bảo đảm những byte thực sự được gửi đúng như mong muốn.

Đừng suy luận rằng publisher lưu một tham chiếu có/không copy array theo cách bạn có thể dựa vào như hợp đồng nghiệp vụ. Điều quan trọng là body **phải nhất quán** trong suốt một lần gửi, và application không đưa mutable state không đồng bộ vào đường I/O.

### 5.4. Khi nào không dùng ofByteArray?

Không nên gọi `Files.readAllBytes(hugeFile)` rồi `ofByteArray(...)` chỉ để upload file lớn nếu không cần xử lý toàn bộ file trong RAM. Cách đó làm kích thước heap/bộ nhớ đỉnh tăng theo file size, có thể làm OOM khi có nhiều uploads đồng thời. Dùng `ofFile(path)` hoặc stream publisher khi dữ liệu không cần nạp hết.

## 6. `BodyPublishers.ofFile`: gửi nội dung file trực tiếp

### 6.1. Cú pháp đơn giản

~~~java
Path path = Path.of("reports", "daily.csv");

HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://api.example.test/upload"))
        .header("Content-Type", "text/csv; charset=utf-8")
        .POST(HttpRequest.BodyPublishers.ofFile(path))
        .build();
~~~

Mã trên là **đoạn minh họa** bên trong phương thức có thể ném `IOException`/`FileNotFoundException`, cần import `java.nio.file.Path`. `ofFile` tạo publisher lấy byte từ **nội dung file**, thay vì bạn phải gọi `Files.readAllBytes(path)` trước. Đây là cách hợp lý cho upload tệp lớn với footprint tốt hơn.

**Không đồng nghĩa multipart:** `ofFile(path)` gửi **nội dung byte của file** làm request body. Nó không tự sinh `multipart/form-data`, không tự thêm `Content-Disposition`, filename hoặc boundary. Server API yêu cầu multipart phải nhận đúng cấu trúc multipart (thường dùng thư viện HTTP có hỗ trợ multipart hoặc tự đóng gói đúng chuẩn), không chỉ đổi header thành `multipart/form-data`.

### 6.2. Vòng đời file và lỗi

- Đường dẫn phải trỏ tới **file được phép đọc**, không phải một tên tệp do người dùng nhập mà chưa được kiểm tra.
- `ofFile(path)` có thể báo lỗi sớm khi file không tồn tại/không đọc được; nếu file mất quyền, bị di chuyển, đổi nội dung hoặc lỗi I/O **trong lúc gửi**, việc gửi cũng có thể thất bại.
- Giữ nội dung file **ổn định trong suốt request**, nhất là khi server phụ thuộc hash/chữ ký/Content-Length. Không sửa/truncate file song song với upload rồi kỳ vọng client tiếp tục gửi một snapshot nhất quán.
- Với file do ứng dụng tạo để gửi, chỉ dọn/xóa **sau khi request đã hoàn tất** (bao gồm request gửi bất đồng bộ). Xóa file ngay sau `request.build()` có thể làm body không còn tồn tại lúc client cần đọc.
- `Files.size(path)` chỉ phản ánh trạng thái tại thời điểm kiểm tra; không dùng nó để tự ghi header `Content-Length` tách rời cơ chế publisher.
- Không dùng dữ liệu `Path` từ nguồn không đáng tin để cho phép đọc file nhạy cảm trên server/client. Cần whitelist thư mục, kiểm tra symlink/traversal theo chính sách bảo mật.

### 6.3. Gửi file bằng PUT

~~~java
Path file = Path.of("uploads", "data.bin");

HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://api.example.test/files/data.bin"))
        .header("Content-Type", "application/octet-stream")
        .method("PUT", HttpRequest.BodyPublishers.ofFile(file))
        .build();
~~~

`POST` là một lựa chọn thường gặp, nhưng BodyPublisher **không quyết định HTTP method**. Với endpoint dùng `PUT`, bạn có thể dùng `PUT(publisher)` hoặc `method("PUT", publisher)`. Với `PATCH` (nếu API hỗ trợ), dùng `method("PATCH", publisher)`. Semantics POST/PUT/PATCH và tính idempotent/conditional write là chuyện của protocol server, **không phải tính chất của ofFile**.

### 6.4. MIME type: không tự đồng nghĩa với đuôi file

Nếu file `.png` chứa ảnh, bạn cần thiết lập media type đúng như `image/png` theo API contract; nếu file `.csv`, thường `text/csv` với charset phù hợp. `ofFile` **không tự biết chuẩn media type mong muốn của endpoint** chỉ từ file extension; phần HTTP header `Content-Type` thuộc trách nhiệm caller.

Không tin hoàn toàn vào extension do người dùng cung cấp cho kiểm soát upload. Server phải giới hạn size, xác thực, kiểm tra loại nội dung thực và quét theo chính sách vì `Content-Type` là metadata mà client có thể giả mạo.

## 7. `BodyPublishers.ofInputStream`: mở một stream khi cần gửi

### 7.1. Tại sao API nhận Supplier chứ không nhận InputStream?

Chữ ký ý tưởng:

~~~java
BodyPublishers.ofInputStream(Supplier<? extends InputStream> supplier)
~~~

Thay vì đưa **một stream đã mở**, bạn đưa một **hàm tạo/đưa ra stream mới** khi publisher bắt đầu một lần subscription/gửi. Điều này cần thiết vì HTTP client có thể phải **subscribe lại** body khi phát sinh một số tình huống như xác thực, chuyển hướng hoặc retry tùy policy; một stream đã đọc hết thường không thể tua về đầu.

Ví dụ phát byte từ bộ nhớ qua stream:

~~~java
byte[] data = "stream-body".getBytes(StandardCharsets.UTF_8);

Supplier<InputStream> supplier =
        () -> new ByteArrayInputStream(data);

HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.ofInputStream(supplier);
~~~

Mã trên cần import `java.io.ByteArrayInputStream`, `java.io.InputStream` và `java.util.function.Supplier`. **Mỗi lần supplier được gọi**, nó tạo một `ByteArrayInputStream` mới có vị trí đọc từ đầu; đây là minh họa cho yêu cầu tính **repeatability/replayability**. Trường hợp chỉ có một live socket stream không thể mở lại, retry body có thể không thực hiện được.

### 7.2. Dùng InputStream từ file hoặc nguồn đọc dần

Ví dụ supplier mở file mới mỗi lần:

~~~java
Path file = Path.of("uploads", "large.log");

Supplier<InputStream> supplier = () -> {
    try {
        return Files.newInputStream(file);
    } catch (IOException ex) {
        throw new UncheckedIOException(ex);
    }
};

HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.ofInputStream(supplier);
~~~

Đây là **mã minh họa trong phương thức**, cần import `java.io.*`, `java.nio.file.*` và `java.util.function.Supplier`. Vì `Supplier.get()` không khai báo checked exceptions, khi `Files.newInputStream` ném `IOException` ta bọc thành `UncheckedIOException`; nếu không chương trình **không biên dịch**.

Stream supplier có thể dựa vào tệp, source byte stream được sinh từ một quy trình khác, hoặc nguồn có thể mở lại. **Không được trả về một stream đã tiêu thụ hết hoặc đã bị đóng** cho lần subscription sau; và không trả `null` để giả vờ một body rỗng, vì publisher không thể lấy nguồn dữ liệu hợp lệ.

### 7.3. `contentLength() == -1` và truyền chunked

Với `BodyPublishers.ofInputStream(...)`, kích thước thường **chưa biết trước** nên `contentLength()` trả **`-1`**, nghĩa là *unknown content length*. Điều đó **không** có nghĩa body có âm một byte hoặc không có body.

Client chọn cơ chế framing phù hợp:

- **HTTP/1.1:** một body không xác định kích thước trước có thể được gửi bằng `Transfer-Encoding: chunked`, theo khả năng client/điều kiện request.
- **HTTP/2:** body được đóng gói trong DATA frames theo quy tắc HTTP/2; không sử dụng HTTP/1.1 chunked transfer coding.
- **Cả hai:** application không nên tự đặt `Transfer-Encoding` hoặc `Content-Length` không nhất quán với publisher; để thư viện điều phối framing.

Một số server/proxy cũ hoặc endpoint ký request bằng fixed `Content-Length` yêu cầu biết trước độ dài. Nếu body có kích thước không xác định, cần thương lượng khả năng tương thích hoặc dùng cách biết length (`ofByteArray`, `ofFile`) theo yêu cầu, không tự đoán.

### 7.4. Không bảo đảm retry chỉ vì có supplier

Ngay cả supplier có thể mở stream mới, **HttpClient không cam kết tự retry mọi lỗi**. Có thể không thể retry request đã gửi một phần, không thể biết server đã thực hiện side effect hay chưa, hoặc một policy khác không cho phép retry.

Nếu request là `POST /payments` hoặc tạo tài nguyên có tác dụng phụ, tự gửi lại toàn bộ body sau timeout có thể **tạo hai giao dịch**. Khi cần retry an toàn, hãy dùng idempotency key/request identifier, timeout và transaction semantics được API quy định. Khả năng replay body là **điều kiện kỹ thuật**, không đồng nghĩa request **idempotent về nghiệp vụ**.

### 7.5. Blocking trong Supplier và quản lý nguồn tài nguyên

`InputStream.read()` có thể bị chặn khi nguồn chưa có dữ liệu. Dù caller dùng `sendAsync`, publisher có thể cần worker để đọc stream; mã trong supplier/stream vẫn có thể block. Đừng đặt các thao tác nguy hiểm/lâu vô hạn vào supplier, và hãy thiết kế timeout/cancellation/lifecycle thích hợp.

Không mở stream một lần ngoài supplier rồi gọi `ofInputStream(() -> alreadyOpenStream)`: lần tiếp theo sẽ trả cùng stream ở cuối, hoặc nhiều hoạt động vô tình chia sẻ cursor. Hãy trả **fresh stream** cho mỗi subscription khi nguồn cho phép.

Nếu stream là tài nguyên do một subsystem khác quản lý và không được phép đóng, cần một wrapper/publisher có hợp đồng vòng đời rõ ràng; không suy đoán rằng mỗi phiên bản HttpClient luôn đóng stream của bạn vào một thời điểm cố định. Với resource thông thường, sử dụng supplier có vòng đời phù hợp và xử lý failure/cancellation.

## 8. HTTP method, headers, length và response: ghép đúng các phần

### 8.1. POST, PUT, PATCH và DELETE

~~~java
HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.ofString(
                "{\"ok\":true}", StandardCharsets.UTF_8);

HttpRequest post = HttpRequest.newBuilder(uri)
        .header("Content-Type", "application/json")
        .POST(body)
        .build();

HttpRequest put = HttpRequest.newBuilder(uri)
        .header("Content-Type", "application/json")
        .PUT(body)
        .build();

HttpRequest patch = HttpRequest.newBuilder(uri)
        .header("Content-Type", "application/json")
        .method("PATCH", body)
        .build();

HttpRequest deleteNoBody = HttpRequest.newBuilder(uri)
        .DELETE()
        .build();
~~~

Đây là **đoạn minh họa**, biến `uri` đã được khai báo. Một publisher có thể dùng cho nhiều request nếu có semantics subscription phù hợp, nhưng **không** có nghĩa mọi endpoint chấp nhận cùng body/method. `DELETE()` mặc định không có request body; dùng `BodyPublishers.noBody()` khi cần body rỗng cho các method khác.

### 8.2. `Content-Type` không được BodyPublisher tự suy đoán

Một request gửi byte có thể là JSON, protobuf, ảnh, zip hay text. Cùng một `byte[]` không nói được media type. Vì vậy:

~~~java
HttpRequest.newBuilder(uri)
        .header("Content-Type", "application/json; charset=utf-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                json, StandardCharsets.UTF_8))
        .build();
~~~

Hãy đảm bảo `Content-Type` **khớp byte thực tế**. Gửi UTF-8 nhưng quảng cáo `charset=iso-8859-1` là lỗi metadata; server có thể giải mã sai. Gửi file PNG nhưng `Content-Type: text/plain` có thể làm validation sai hoặc tạo nguy cơ nếu server/client sniff nội dung.

### 8.3. `BodyPublisher.contentLength()` chỉ là metadata byte count

Ví dụ có thể kiểm tra bằng Java:

~~~java
int byteCount = "Xin chào".getBytes(StandardCharsets.UTF_8).length;
// byteCount = 9

HttpRequest.BodyPublisher p =
        HttpRequest.BodyPublishers.ofString(
                "Xin chào", StandardCharsets.UTF_8);
// p.contentLength() trả 9 với String này.
~~~

Khi `contentLength() >= 0`, publisher biết số byte sẽ publish. Khi bằng `-1`, length không biết trước. **Đừng** tự thêm header `Content-Length` không khớp, vì điều đó có thể khiến request thất bại, treo ở server hoặc vi phạm framing.

Với dữ liệu nhị phân, length là **byte count**, không phải số phần tử Unicode hay số bản ghi. Với `ofFile`, length gắn với nội dung file; thay đổi file trong lúc gửi có thể khiến nội dung/độ dài không còn nhất quán.

### 8.4. Response BodyHandler là API khác

~~~java
HttpResponse<String> response =
        client.send(request, HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));

int status = response.statusCode();
String responseBody = response.body();
~~~

Ở đây `BodyHandlers.ofString(...)` **đọc response**. Nó không ảnh hưởng việc request body được publish bằng `ofFile` hay `ofInputStream`. Còn `BodyHandlers.ofByteArray()` đọc response binary, `BodyHandlers.ofFile(path)` lưu response vào file và `BodyHandlers.ofInputStream()` trả response InputStream để caller tự đọc/đóng theo hướng dẫn API.

Các API cùng tên `ofString`, `ofFile` ở hai hướng khác nhau rất dễ gây nhầm. Hãy nhìn kiểu đầy đủ `HttpRequest.BodyPublishers` (gửi) so với `HttpResponse.BodyHandlers` (nhận).

## 9. Demo Java 17+ hoàn chỉnh: gửi đủ bốn loại tới HTTP server loopback

Chương trình sau không cần API bên ngoài. Nó tạo một **HTTP server trên `127.0.0.1` và cổng ngẫu nhiên**, sau đó `HttpClient` gửi bốn POST:

1. String `"Xin chào"` dùng UTF-8, có **9 byte**.
2. byte[] chứa 4 byte nhị phân: `00 01 FF 7F`.
3. File tạm chứa ASCII `file-body`, dài **9 byte**.
4. `InputStream` supplier tạo stream chứa ASCII `stream-body`, dài **11 byte**; `contentLength()==-1` vì publisher không biết trước.

Server phản hồi tên method, đường dẫn, số byte thực nhận và `Content-Type`. Nó **không in raw binary** để tránh hỏng ký tự. Đây là demo giáo dục chạy hoàn toàn trên loopback. Trong production, **không đọc toàn bộ request body bằng `readAllBytes()` thiếu giới hạn**; phải áp dụng max upload size/streaming parse/timeout.

Lưu thành file **BodyPublisherDemo.java**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
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
import java.util.function.Supplier;

public class BodyPublisherDemo {
    static void handle(HttpExchange exchange) throws IOException {
        try (exchange) {
            // Chỉ dùng readAllBytes vì demo nhận payload rất nhỏ.
            byte[] data = exchange.getRequestBody().readAllBytes();
            String contentType = exchange.getRequestHeaders()
                    .getFirst("Content-Type");

            String answer = exchange.getRequestMethod()
                    + " " + exchange.getRequestURI().getPath()
                    + " bytes=" + data.length
                    + " type=" + contentType;

            byte[] response =
                    answer.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(200, response.length);

            try (OutputStream out = exchange.getResponseBody()) {
                out.write(response);
            }
        }
    }

    static void post(HttpClient client, URI base,
                     String path, String contentType,
                     HttpRequest.BodyPublisher body, String label)
            throws IOException, InterruptedException {

        HttpRequest request = HttpRequest.newBuilder(
                    base.resolve(path))
                .header("Content-Type", contentType)
                .POST(body)
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        System.out.println(label + ": " + response.statusCode()
                + " " + response.body());
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("body-demo-", ".txt");

        try {
            Files.writeString(
                    file, "file-body", StandardCharsets.UTF_8);

            HttpServer server = HttpServer.create(
                    new InetSocketAddress(
                            InetAddress.getByName("127.0.0.1"), 0), 0);
            server.createContext("/", BodyPublisherDemo::handle);
            server.start();

            try {
                URI base = URI.create(
                        "http://127.0.0.1:"
                        + server.getAddress().getPort() + "/");
                HttpClient client = HttpClient.newHttpClient();

                // Unicode escape tạo đúng ký tự 'à' trên mọi shell.
                HttpRequest.BodyPublisher text =
                        HttpRequest.BodyPublishers.ofString(
                                "Xin ch\u00e0o", StandardCharsets.UTF_8);

                byte[] raw = {0x00, 0x01, (byte) 0xFF, 0x7F};
                HttpRequest.BodyPublisher bytes =
                        HttpRequest.BodyPublishers.ofByteArray(raw);

                HttpRequest.BodyPublisher fromFile =
                        HttpRequest.BodyPublishers.ofFile(file);

                byte[] streamBytes = "stream-body".getBytes(
                        StandardCharsets.UTF_8);
                Supplier<InputStream> supplier =
                        () -> new ByteArrayInputStream(streamBytes);
                HttpRequest.BodyPublisher stream =
                        HttpRequest.BodyPublishers.ofInputStream(supplier);

                System.out.println(
                        "Lengths: " + text.contentLength()
                        + ", " + bytes.contentLength()
                        + ", " + fromFile.contentLength()
                        + ", " + stream.contentLength());

                post(client, base, "string",
                        "text/plain; charset=utf-8", text, "String");
                post(client, base, "bytes",
                        "application/octet-stream", bytes, "byte[]");
                post(client, base, "file",
                        "text/plain; charset=utf-8", fromFile, "File");
                post(client, base, "stream",
                        "application/octet-stream", stream, "InputStream");
            } finally {
                server.stop(0);
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch/chạy bằng **JDK 17+**:

~~~bash
javac -encoding UTF-8 BodyPublisherDemo.java
java BodyPublisherDemo
~~~

Stdout đã kiểm tra với JDK 17 và module `jdk.httpserver` khả dụng:

~~~text
Lengths: 9, 4, 9, -1
String: 200 POST /string bytes=9 type=text/plain; charset=utf-8
byte[]: 200 POST /bytes bytes=4 type=application/octet-stream
File: 200 POST /file bytes=9 type=text/plain; charset=utf-8
InputStream: 200 POST /stream bytes=11 type=application/octet-stream
~~~

### 9.1. Giải thích stdout

- **`Lengths: 9, 4, 9, -1`** lần lượt là `contentLength()` của `ofString`, `ofByteArray`, `ofFile`, `ofInputStream`. `-1` là **unknown length**, không phải HTTP lỗi hoặc body không có bytes.
- **String 9 bytes:** `"Xin ch\u00e0o"` tạo nội dung tiếng Việt “Xin chào”; UTF-8 dùng 9 byte, dù Java `String.length()` bằng 8.
- **byte[] 4 bytes:** gồm cả `0x00` và `0xFF` — server đếm đúng 4 byte, không diễn giải thành text.
- **File 9 bytes:** file tạm chứa `file-body` được stream làm request body; file được xóa sau khi kết thúc tất cả requests.
- **InputStream 11 bytes:** supplier trả một `ByteArrayInputStream` mới trên mảng chứa `stream-body`. Publisher không khai báo trước kích thước, nhưng server **vẫn nhận đủ 11 byte**.
- Cả bốn request được gửi qua `POST` và đều được **server demo** trả `200`. Một server thực tế có thể trả `201`, `204` hoặc `4xx/5xx` theo contract; client phải kiểm tra `statusCode()`.

### 9.2. Vì sao server không in `Transfer-Encoding`?

Mục tiêu demo là **so sánh bytes thực nhận và kiểu BodyPublisher**, không khóa vào một phiên bản HTTP/wire framing duy nhất. `HttpClient` có thể chọn HTTP/1.1 hoặc HTTP/2 tùy peer; server `jdk.httpserver` trong demo xử lý HTTP/1.1 nhưng app không nên dựa vào một header framing để kết luận BodyPublisher hoạt động.

Ở phía server, đọc request body từ `exchange.getRequestBody()` trả về **body bytes sau khi HTTP parser đã xử lý framing**. Vì vậy 11 byte của `InputStream` vẫn được nhận đúng dù publisher công bố length `-1`.

### 9.3. Vì sao dùng file tạm trong demo?

Để chương trình chạy lại không phụ thuộc file có sẵn, nó tạo tệp với `Files.createTempFile`, ghi một nội dung đã biết rồi gửi bằng `ofFile`. `finally` bảo đảm server dừng và xóa file tạm ngay cả khi request lỗi, **sau khi `send` đã kết thúc hoặc ném lỗi**. Khi dùng `sendAsync`, phải dọn file **sau khi CompletionStage thực sự hoàn tất**, không chạy cleanup ngay khi tạo future.

### 9.4. An toàn ở production

Server demo dùng `readAllBytes` để minh họa dữ liệu rất nhỏ. Không copy nguyên pattern này sang endpoint upload file tùy ý mà không giới hạn byte; attacker có thể gửi body không biết length hoặc quá lớn và làm cạn heap. Production cần kiểm soát tối đa số byte, thời gian đọc, loại nội dung, xác thực, quotas, storage và cleanup.

## 10. Xử lý upload file lớn mà không chiếm nhiều RAM

Hai cách:

~~~java
// Cách A: Nạp cả file vào bộ nhớ. Không tốt cho file rất lớn.
byte[] all = Files.readAllBytes(path);
HttpRequest.BodyPublisher fromMemory =
        HttpRequest.BodyPublishers.ofByteArray(all);

// Cách B: Publisher đọc trực tiếp nội dung file.
HttpRequest.BodyPublisher fromDisk =
        HttpRequest.BodyPublishers.ofFile(path);
~~~

Đây là mã minh họa với `path` hợp lệ. Với file 2 GiB, cách A có thể không khả thi về heap, trong khi cách B không đòi tạo một mảng byte dài 2 GiB trước. **Không bảo đảm RAM luôn bằng hằng số nhỏ tuyệt đối**: HttpClient/provider vẫn có internal buffers, TLS, OS buffering và request concurrency.

### 10.1. Phân bổ tài nguyên theo luồng

Nếu chạy 100 uploads đồng thời, phải tính:

- Kích thước file/stream và tốc độ đọc trên disk.
- HTTP client connection pool, TLS, CPU, outbound network bandwidth.
- Số file descriptors/InputStreams đang mở cùng lúc.
- Timeout và khả năng server đọc chậm.
- Băng thông outbound, retry và áp lực buffer/backpressure.
- Quota của endpoint, số requests đồng thời và ứng dụng có cho phép cancel upload hay không.

`ofFile`/`ofInputStream` giúp tránh một bản copy lớn ở heap, nhưng **không tự giải quyết giới hạn đồng thời, retry an toàn hay timeout**. Sử dụng `Semaphore`, executor và metrics theo workload nếu có hàng nghìn upload tasks.

### 10.2. Không cần tự chunk file bằng tay chỉ vì file lớn

Một file có thể được publisher/client gửi qua nhiều network writes/frames. HTTP/TCP phân mảnh ở tầng phù hợp. Việc tự chia file thành nhiều HTTP requests chỉ cần khi **server hỗ trợ resumable/chunked upload theo protocol ứng dụng** hoặc cần quản lý retry từng phần.

`Transfer-Encoding: chunked` trong HTTP/1.1 là **wire framing**, không đồng nghĩa upload chia thành nhiều request. Tương tự, HTTP/2 DATA frames không phải những chunk dữ liệu ứng dụng có thể tự ghép tùy ý nếu server yêu cầu multipart hoặc một hash thống nhất.

## 11. InputStream theo luồng: những lỗi lifecycle thường gặp

### 11.1. Sai: dùng lại một InputStream đã mở

~~~java
InputStream once = Files.newInputStream(path);
HttpRequest.BodyPublisher wrong =
        HttpRequest.BodyPublishers.ofInputStream(() -> once);
~~~

Đây là **mã minh họa sai**. Supplier trả cùng một stream cho mọi lần gọi; sau subscription đầu tiên, stream đã ở EOF hoặc đã đóng. Nếu HttpClient cần publish lần sau, body có thể bị thiếu hoặc thất bại. Cách đúng là supplier **mở một stream mới mỗi lần** (khi nguồn có thể replay).

### 11.2. Sai: đóng file/stream quá sớm

~~~java
// SAI khi request chưa gửi:
Path temp = createTempFileSomehow();
HttpRequest request = HttpRequest.newBuilder(uri)
        .POST(HttpRequest.BodyPublishers.ofFile(temp))
        .build();
Files.delete(temp); // File có thể mất trước khi body được đọc!
client.send(request, HttpResponse.BodyHandlers.discarding());
~~~

Đoạn code trên có tên hàm giả định `createTempFileSomehow` và biến ứng dụng; **không phải ví dụ chạy độc lập**. Nó minh họa lỗi lifecycle: việc build request không đồng nghĩa đã nạp xong file.

Với `sendAsync`:

~~~java
CompletableFuture<HttpResponse<Void>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.discarding());

// Không xóa temp ngay ở đây.
// Dọn khi future hoàn tất và đã xử lý kết quả/lỗi.
future.whenComplete((response, error) -> {
    try {
        Files.deleteIfExists(temp);
    } catch (IOException closeError) {
        // Ghi log, không bỏ qua rò rỉ file tạm.
    }
});
~~~

Đây là **đoạn minh họa có biến đã khai báo**, cần import `java.util.concurrent.CompletableFuture`, `java.nio.file.Files` và `java.io.IOException`. Trong sản phẩm thật còn phải xử lý resource của publisher, cancellation, security và backpressure; `whenComplete` dùng để gắn cleanup khi future kết thúc, không thay thế chính sách retry.

### 11.3. Sai: supplier ném checked IOException trực tiếp

~~~java
// SAI: lambda Supplier.get() không cho throw checked IOException.
Supplier<InputStream> bad =
        () -> Files.newInputStream(path);
~~~

Cách sửa:

~~~java
Supplier<InputStream> good = () -> {
    try {
        return Files.newInputStream(path);
    } catch (IOException ex) {
        throw new UncheckedIOException(ex);
    }
};
~~~

Đây là mã minh họa; cần import `java.io.*`, `java.nio.file.*` và `java.util.function.Supplier`. Nếu file không thể mở, request **phải thất bại**, không đổi thành một stream rỗng để giả vờ upload thành công.

### 11.4. Nguồn chỉ đọc một lần

Một camera stream, process stdout hoặc socket đầu vào có thể **không thể tạo lại từ byte đầu**. `ofInputStream` vẫn có thể tiêu thụ một stream trong một lần gửi, nhưng không đảm bảo body có thể được replay khi retry, redirect hoặc xác thực yêu cầu subscribe lại.

Nếu tính đúng đắn đòi retry, cần chọn: lưu snapshot ra file trước; lưu body thành chunk có IDs và phục hồi theo protocol; hoặc báo thất bại và yêu cầu người dùng tạo lại dữ liệu. Đừng âm thầm gửi “phần còn lại” như toàn bộ body sau khi kết nối HTTP cũ lỗi.

## 12. File upload không đồng nghĩa multipart/form-data

### 12.1. Raw body

Nếu server định nghĩa:

~~~http
POST /upload/raw HTTP/1.1
Content-Type: application/octet-stream

<raw file bytes>
~~~

thì `ofFile(path)` rất phù hợp. Body là **byte của file**, không có trường form hay tên file tự động. Server có thể nhận filename qua URL hoặc metadata header được thiết kế riêng.

### 12.2. Multipart form body

Một form upload phổ biến đòi:

~~~http
POST /upload/form HTTP/1.1
Content-Type: multipart/form-data; boundary=Boundary123

--Boundary123
Content-Disposition: form-data; name="file"; filename="demo.txt"
Content-Type: text/plain

<file bytes>
--Boundary123--
~~~

Ở wire format thật, multipart dùng **CRLF** (carriage return + line feed) đúng cú pháp, và boundary phải đúng/safe. `ofFile(path)` **không tự sinh** các dòng `Content-Disposition`, boundary hoặc phần tử biểu mẫu. Chỉ sửa header thành `multipart/form-data` mà không đóng gói body là lỗi phổ biến.

Trong Java 17, có thể tạo multipart bằng cách ghép publishers (API `BodyPublishers.concat(...)`) và headers/CRLF đúng, nhưng việc tự xử lý filename quoting, charset, boundary collisions và size/streaming an toàn rất dễ sai. Với hệ thống thật, ưu tiên multipart builder/framework đã được kiểm thử, hoặc theo đúng hợp đồng endpoint raw-body nếu server cho phép.

### 12.3. Dùng JSON với file binary?

Base64-encode một file rồi nhét vào JSON là một contract **khác** với raw upload hoặc multipart. Base64 làm tăng dung lượng và yêu cầu encode/decode; chỉ dùng khi server API thật sự định nghĩa định dạng đó. `ofByteArray` hoặc `ofFile` không tự base64 hóa nội dung.

## 13. `send`, `sendAsync`, retry và timeout

### 13.1. Gửi đồng bộ

~~~java
HttpResponse<String> response =
        client.send(request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

if (response.statusCode() >= 200
        && response.statusCode() < 300) {
    // Thành công theo lớp mã HTTP 2xx;
    // vẫn phải kiểm tra contract của API cụ thể.
} else {
    // Xử lý status và response body/error.
}
~~~

Đoạn minh họa yêu cầu biến `client`/`request` và checked exceptions. `send` chờ response theo API; phần upload diễn ra trong quá trình request được truyền. **Status 200 chỉ nói server trả OK**, không tự đảm bảo đã xử lý đúng nghiệp vụ hoặc lưu tệp vĩnh viễn; API có thể dùng 201/202/204.

### 13.2. Gửi bất đồng bộ

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

future.thenAccept(response -> {
    System.out.println("HTTP " + response.statusCode());
}).exceptionally(error -> {
    // Ghi log, xử lý upload thất bại.
    return null;
});
~~~

Đây là mã minh họa; cần import `CompletableFuture`. `sendAsync` trả Future/CompletionStage sớm, **không có nghĩa body file/stream đã được đọc xong** vào lúc nó trả về. Cần quản lý nguồn tệp và lifecycle theo hoàn tất thực tế; callback/CompletionStage có thể chạy trên thread khác.

### 13.3. Timeout

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(30))
        .POST(publisher)
        .build();
~~~

Đoạn mã minh họa cần import `java.time.Duration` và các type HTTP. `connectTimeout` liên quan giai đoạn kết nối; `request.timeout` là ngưỡng thời gian cho request theo semantics của `HttpClient`. Không coi chúng là chính sách duy nhất chống nguồn InputStream treo hoặc server không đọc: cần kiểm thử hành vi cancel, timeout và tài nguyên thực tế.

### 13.4. Retry có thể gửi trùng side effect

Nếu client gửi 90% body, kết nối đứt và không nhận response, **không biết chắc server đã xử lý xong hay chưa**. Dù dùng `ofFile` hay supplier mở lại được, retry `POST` có thể nhân đôi tác dụng. Chỉ retry khi endpoint cho phép hoặc có request ID/idempotency key. Đừng suy luận “BodyPublisher replayable = HTTP request an toàn để tự động retry”.

Nếu upload rất lớn, cân nhắc protocol **resumable upload** do server định nghĩa, thường có upload session ID, offset, checksum và khả năng đối soát. Tự tiếp tục ở giữa luồng TCP cũ sau lỗi không phải một cơ chế upload resume hợp lệ.

## 14. Các failure modes và cách xử lý

| Lỗi | Triệu chứng | Cách xử lý |
| --- | --- | --- |
| Gửi JSON bằng ofString nhưng không đặt Content-Type | Server không biết media type đúng | Đặt `application/json; charset=utf-8` |
| Dùng default charset không chủ đích | Server giải mã sai text | Dùng `StandardCharsets.UTF_8` và metadata nhất quán |
| Lấy `String.length()` làm byte count | Số byte sai với tiếng Việt/emoji | Đo bytes sau encode hoặc để publisher tính |
| Dùng ofByteArray cho file cực lớn bằng readAllBytes | OOM/heap pressure | Dùng `ofFile` hoặc InputStream theo luồng |
| Gọi ofFile cho file không tồn tại/không đọc được | Request không thể publish body | Xử lý `FileNotFoundException`/I/O, kiểm tra path |
| Xóa file sau build nhưng trước send | File không còn khi client muốn đọc | Đợi send/sendAsync hoàn tất mới cleanup |
| File bị ghi đè/truncate trong lúc upload | Nội dung/length sai, request fail | Tạo snapshot hoặc khóa logic vòng đời |
| Dùng ofFile nhưng server cần multipart | Server báo thiếu boundary/form field | Dùng multipart encoder đúng, không chỉ đổi Content-Type |
| Supplier trả lại một InputStream cũ | Retry/subscription sau bị EOF | Mở stream mới mỗi lần supplier được gọi |
| Supplier có checked IOException trực tiếp | Mã không biên dịch | Catch, bọc `UncheckedIOException` |
| Diễn giải `contentLength()==-1` là không có body | Báo sai body length | `-1` nghĩa là độ dài chưa biết |
| Tự đặt Content-Length không khớp | Request framing sai/HTTP client từ chối | Để HttpClient quản lý |
| Nghĩ ofInputStream mã hóa text tự động | Byte stream không có charset magic | Encode trước hoặc xác định chuẩn dữ liệu |
| Coi HTTP status 4xx/5xx là không có response body | Bỏ thông tin lỗi | Đọc response và xử lý status rõ |
| Dùng sendAsync rồi xóa file ngay | Upload đang đọc thì mất file | Cleanup qua completion callback |
| Retry POST không có idempotency key | Có thể tạo hai giao dịch | Theo hợp đồng API, idempotency / đối soát |
| Dùng HTTPS nhưng không xác minh server | Rủi ro gửi dữ liệu nhạy cảm sai peer | Để trust/identity validation đúng, không bypass TLS |
| Server demo đọc upload vô hạn bằng readAllBytes | Cạn RAM khi upload lớn | Giới hạn body size, streaming parser, quotas |

## 15. Tình huống vận dụng

### Tình huống A — Gửi JSON tạo người dùng

Bạn đã có JSON String do serializer tạo. Endpoint `POST /users` muốn UTF-8 JSON, dữ liệu nhỏ. Publisher nào hợp lý?

**Đáp án:** `ofString(json, StandardCharsets.UTF_8)` và `Content-Type: application/json; charset=utf-8`. Client parse response bằng BodyHandler riêng. Không cần chuyển JSON thành `byte[]` thủ công trừ khi đã có bytes.

### Tình huống B — Gửi protobuf bytes đã serialize

Bạn có `byte[] protobufBytes`, endpoint nhận `application/x-protobuf` và yêu cầu giữ byte chính xác.

**Đáp án:** `ofByteArray(protobufBytes)` với media type đúng, không gọi `new String(bytes)`. Nếu chỉ gửi một segment, dùng overload `ofByteArray(array, offset, length)`.

### Tình huống C — Upload một file 500 MiB

Bạn có `Path` tới file đã được validate, server nhận raw body. Có nên `Files.readAllBytes` rồi `ofByteArray` không?

**Đáp án:** thường không. `ofFile(path)` giảm nhu cầu giữ toàn bộ file trong RAM; giữ file ổn định trong suốt upload, đặt timeout/limits và xác minh contract server. Không tự cho rằng file sẽ được gửi thành multipart.

### Tình huống D — Stream sinh dữ liệu theo nhu cầu

Một bộ lọc tạo dữ liệu khi đọc và chỉ cung cấp `InputStream`. Dung lượng không biết trước.

**Đáp án:** `ofInputStream(() -> freshStream())` nếu source có thể cấp stream mới theo yêu cầu. `contentLength()==-1`; HTTP client chọn framing. Nếu chỉ tạo được một stream duy nhất, phải xác định retry/redirect policy, cancel và điều kiện thất bại rõ ràng.

### Tình huống E — Gặp 307/308 redirect khi upload

Một endpoint trả redirect mà method/body có thể phải gửi lại tới URL mới. Supplier đang trả cùng InputStream đã dùng hết.

**Đáp án:** có thể thất bại hoặc body không còn đúng khi request được phát lại. Supplier cần **fresh stream**, và **không** tự cho phép redirect upload nhạy cảm sang origin bất kỳ. Kiểm tra `HttpClient.Redirect`, auth/headers, scheme, host allowlist và idempotency.

### Tình huống F — File được tạo tạm cho upload async

Code xây `ofFile(temp)`, gọi `sendAsync`, rồi `Files.delete(temp)` ngay ở dòng kế.

**Đáp án:** sai vòng đời. Khi `sendAsync` trả, upload có thể chưa bắt đầu/hoàn tất. Chỉ dọn file sau khi future thực sự hoàn thành và đã xử lý lỗi.

### Tình huống G — Server cần Content-Length cố định

Một proxy/endpoint cũ từ chối request body có unknown length. Bạn đang dùng `ofInputStream`.

**Đáp án:** cần thay chiến lược theo contract: tạo file tạm rồi `ofFile`, hoặc nạp vào byte[] nếu nhỏ và có giới hạn, hoặc dùng một publisher có khả năng tuyên bố chính xác độ dài khi đảm bảo điều đó. Đừng chỉ tự đặt Content-Length khác với `contentLength()==-1`.

### Tình huống H — Unicode và Content-Type

Client gửi `"Xin chào"` nhưng khai báo `text/plain; charset=us-ascii`. Vấn đề?

**Đáp án:** bytes UTF-8 chứa chuỗi đa byte cho `à`, nhưng header quảng cáo US-ASCII. Server có thể giải mã sai hoặc từ chối. Dùng charset đúng với phép encode, và test số byte thực sự gửi.

### Tình huống I — API trả 201 Created

Client upload bằng `ofFile`; response trả `201 Created` và header `Location` thay vì `200`. Có phải upload thất bại?

**Đáp án:** không. 201 là một mã thành công HTTP cho tài nguyên được tạo; hãy kiểm tra contract API, Location và response body; đừng cứng mã chỉ status 200 mới được coi là thành công.

### Tình huống J — Mã hóa và bảo mật

File có dữ liệu nhạy cảm, request dùng HTTP thường qua Internet. BodyPublisher có tự mã hóa không?

**Đáp án:** không. BodyPublisher chọn **nguồn request body bytes**, không tự tạo TLS. Dùng HTTPS và kiểm tra chứng chỉ/tên server, authz, phạm vi URL/redirect, log và kiểm soát nguồn file. Không gửi bí mật cho host do người dùng điều khiển chỉ vì “có SSL ở nơi khác”.

## 16. Checklist lập trình HTTP request body

- [ ] Biết body thực sự là text, byte nhị phân, raw file hay stream có thể mở lại?
- [ ] Dùng đúng `ofString` / `ofByteArray` / `ofFile` / `ofInputStream`?
- [ ] Với String, mã hóa bằng UTF-8 và khai báo charset/media type nhất quán?
- [ ] Với bytes, không biến dữ liệu nhị phân thành String tùy tiện?
- [ ] Với file lớn, không `readAllBytes` vào heap nếu không cần?
- [ ] Đã phân biệt raw file upload với `multipart/form-data` và boundary/filename?
- [ ] InputStream supplier tạo stream **mới** mỗi lần được gọi, không trả stream cũ/đã đóng?
- [ ] Khi nguồn stream không replay được, đã có chính sách retry/redirect/timeout rõ?
- [ ] Đã kiểm tra `contentLength()` = kích thước byte hoặc -1 (unknown)?
- [ ] Không tự đặt `Content-Length`/`Transfer-Encoding` mâu thuẫn với HttpClient?
- [ ] HTTP method và `Content-Type` đúng với contract của endpoint?
- [ ] Phân biệt BodyPublisher (gửi) và BodyHandler (nhận)?
- [ ] Không xóa/mutate file hoặc byte source trước khi send/sendAsync kết thúc?
- [ ] Đã kiểm tra response status 2xx/4xx/5xx, parse lỗi và đóng resource hợp lý?
- [ ] Có giới hạn kích thước payload, số upload đồng thời, thời gian, băng thông và quota?
- [ ] Có HTTPS/trust/auth phù hợp khi gửi dữ liệu nhạy cảm, và chính sách redirect an toàn?
- [ ] Với thao tác có side effects, retry sử dụng idempotency key hoặc đối soát?
- [ ] Đã test non-ASCII string, byte 0x00, file rỗng/lớn, stream unknown-length, server từ chối và hủy upload?

**Kết luận:** `HttpRequest.BodyPublishers` chuyển **nguồn dữ liệu ứng dụng** thành request body cho Java `HttpClient`. `ofString` phù hợp văn bản với charset, `ofByteArray` phù hợp bytes có sẵn, `ofFile` phù hợp đọc file trực tiếp không cần nạp trọn vào RAM, và `ofInputStream` phù hợp dữ liệu theo luồng với **supplier tạo stream khi cần**. Để gửi HTTP đúng, vẫn phải kết hợp **Content-Type, số byte thực, HTTP method, source lifecycle, retry/idempotency, timeout và server contract** — BodyPublisher không tự giải quyết toàn bộ những vấn đề đó.

## 17. Tài liệu API chính thức

- **Java 17 — HttpRequest.BodyPublishers:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html
- **Java 17 — HttpRequest.BodyPublisher:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html
- **Java 17 — HttpRequest:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html
- **Java 17 — HttpClient:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- **Java 17 — HttpResponse.BodyHandlers:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html
- **Java 17 — HttpServer (demo nội bộ):** https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html

Các API ở đây thuộc Java 17+ theo mục tiêu bài học. Khi chạy trên một JDK/provider khác hoặc với HTTP/2, proxy, redirect, authentication và nguồn stream chậm, hãy kiểm tra phản hồi thực tế, chính sách retry và API contract thay vì suy đoán dựa trên một lần upload đơn giản.