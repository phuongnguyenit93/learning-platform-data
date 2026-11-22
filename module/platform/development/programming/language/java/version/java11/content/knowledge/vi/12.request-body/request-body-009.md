# Phân biệt phần request body với header mô tả nội dung (Java 11+)

## 1. Mục tiêu: dữ liệu được gửi khác với thông tin mô tả dữ liệu

Trong một **HTTP request**, **body** và **headers** có hai chức năng khác nhau:

- **Request body (phần thân):** chứa **dữ liệu thực tế** mà client gửi, chẳng hạn chuỗi JSON, văn bản, các byte của ảnh hoặc nội dung tệp. Trong Java 11+, `HttpRequest.BodyPublisher` chịu trách nhiệm phát các **byte** của phần thân khi `HttpClient` gửi yêu cầu.
- **Request headers (phần đầu):** chứa **metadata** giúp phía nhận biết cách hiểu yêu cầu. Header `Content-Type` mô tả **media type** của body (ví dụ `application/json` hay `image/png`); `Accept` mô tả **kiểu phản hồi client mong muốn**; các header khác có mục đích riêng.

Hai khái niệm **không thay thế lẫn nhau**:

- Chỉ ghi `Content-Type: application/json` **không tự tạo body JSON**.
- Chỉ đặt `BodyPublishers.ofString(json)` **không tự thêm `Content-Type: application/json`**.
- `Content-Type` **không ép chuỗi tùy ý thành JSON hợp lệ**, không chọn thư viện serialize và không tự mã hóa lại dữ liệu.
- Header có thể hiện diện **khi không có body**; body có thể hiện diện **khi thiếu header mô tả**. Java có thể xây dựng các request như vậy, dù server có thể từ chối hoặc diễn giải khác mong muốn.

Đây là các nguyên tắc vẫn áp dụng trên các JDK hiện đại. Module HTTP Client `java.net.http` được chuẩn hóa trong **Java 11** (JEP 321); bài này dùng API Java 11 đang được hỗ trợ hiện nay, không dựa vào kỹ thuật legacy.

## 2. Hình dung cấu trúc HTTP request

Ví dụ minh họa một yêu cầu **HTTP/1.1 ở mức khái niệm**:

```http
POST /api/messages HTTP/1.1
Host: example.com
Content-Type: application/json
Accept: application/json

{"message":"Xin chào"}
```

Phân tách:

1. `POST /api/messages HTTP/1.1` là **request line**: phương thức, đích và phiên bản giao thức.
2. `Host`, `Content-Type`, `Accept` là **headers**; đây là cặp tên–giá trị, không phải phần JSON.
3. Dòng trống phân tách headers và body trong cách biểu diễn HTTP/1.1.
4. `{"message":"Xin chào"}` là **body** (được mã hóa thành byte khi gửi); server dựa vào `Content-Type` và contract API để biết nên dùng bộ giải mã/parse nào.

Ví dụ này **không phải dump chính xác bytes do Java phát ra trên mạng**. `HttpClient` có thể sử dụng HTTP/2, vốn dùng cách đóng khung nhị phân khác HTTP/1.1; client còn tự điều khiển một số trường transport. Điều quan trọng là **ngữ nghĩa**: headers mô tả, body chứa nội dung.

Không nhầm **URI query** như `/search?q=java` với body. Query nằm trong URI của yêu cầu; body là phần dữ liệu được phát riêng bằng `BodyPublisher`.

## 3. Hai thành phần tương ứng trong Java 11

### 3.1. Tạo body bằng `HttpRequest.BodyPublishers`

`HttpRequest.BodyPublishers` cung cấp các cách tạo `BodyPublisher`:

```java
// Đã có biến String json:
HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.ofString(
                json, java.nio.charset.StandardCharsets.UTF_8);
```

Publisher chuyển dữ liệu thành các buffer byte để `HttpClient` gửi. Khi tạo builder, gắn publisher bằng các phương thức như:

```java
HttpRequest request = HttpRequest.newBuilder(uri)
        .POST(body)
        .build();
```

Các đoạn trên là **mã minh họa**, cần khai báo `json`, `uri`, các import và class/phương thức chứa mã. Chương trình hoàn chỉnh ở mục 6 chạy độc lập.

**Lưu ý:** `build()` mới chỉ đóng gói request; publisher thông thường phát byte **khi request thực sự được gửi**, chứ không phải cứ tạo `HttpRequest` là đã gọi network.

### 3.2. Đặt header bằng `HttpRequest.Builder`

```java
HttpRequest request = HttpRequest.newBuilder(uri)
        .setHeader("Content-Type", "application/json")
        .setHeader("Accept", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(
                json, java.nio.charset.StandardCharsets.UTF_8))
        .build();
```

Hai lệnh `setHeader` làm việc với **metadata**, còn `POST(...)` cung cấp **body publisher**. Chúng độc lập:

| Chỗ cấu hình | Ví dụ | Tác dụng |
| --- | --- | --- |
| Header mô tả body | `setHeader("Content-Type", "application/json")` | Báo cho server body có định dạng JSON |
| Header yêu cầu response | `setHeader("Accept", "application/json")` | Báo client muốn nhận response JSON |
| Body thực tế | `POST(BodyPublishers.ofString(json, UTF_8))` | Cung cấp byte JSON để gửi |
| HTTP method | `POST(...)` | Chọn hành vi HTTP POST của request |
| Gửi request | `HttpClient.send(request, handler)` | Bắt đầu thao tác mạng |

`Content-Type` và `Accept` có thể có giá trị giống nhau nhưng **không cùng ý nghĩa**. Một endpoint có thể nhận body JSON mà trả lại văn bản, hoặc nhận dữ liệu nhị phân mà trả JSON. Đừng đặt chúng theo thói quen mà không đọc hợp đồng API.

## 4. Bốn trạng thái dễ gây nhầm lẫn

Các trường hợp sau đều có thể biểu diễn bằng Java 11, nhưng ý nghĩa sử dụng khác nhau:

| Trường hợp | Header `Content-Type` | Body publisher | Điều thực sự xảy ra |
| --- | --- | --- | --- |
| POST JSON được khai báo rõ | `application/json` | `ofString(json, UTF_8)` | Có dữ liệu byte; header mô tả chúng là JSON |
| POST có body nhưng **thiếu `Content-Type`** | Không có | `ofString(json, UTF_8)` | Vẫn có body; server phải dựa vào contract hoặc có thể từ chối |
| GET có `Content-Type` nhưng **không có body** | `application/json` | Không có | Header tồn tại; **không có body** chỉ vì đã ghi header |
| POST với `BodyPublishers.noBody()` | Có thể có hoặc không | Publisher **không phát byte** | Có thể có `BodyPublisher` trong request nhưng **độ dài body = 0** |

**Phân biệt ba khái niệm:**

- **Không có body publisher:** `request.bodyPublisher().isPresent() == false`. GET được tạo bằng `GET()` thường thuộc trường hợp này.
- **Có publisher nhưng body dài 0 byte:** ví dụ `POST(BodyPublishers.noBody())` hoặc publisher tạo từ chuỗi rỗng `""`. `bodyPublisher().isPresent()` có thể là `true` nhưng `contentLength() == 0`.
- **Có body không rỗng:** publisher phát một hay nhiều byte; `contentLength()` có thể là số dương nếu biết trước, hoặc **âm** khi độ dài chưa xác định. Không dùng phép kiểm tra chỉ dựa trên `isPresent()` để khẳng định có dữ liệu.

Đừng suy đoán rằng Java sẽ tự phát sinh nội dung JSON từ `Content-Type` hoặc tự xóa header nếu request không có body. Builder chỉ làm những gì phương thức cấu hình của nó quy định.

## 5. Kiểu dữ liệu, charset và số byte thực sự gửi

### 5.1. Body là byte, không phải số ký tự Java

`String` trong Java sử dụng UTF-16; `String.length()` đếm **code unit**, không phải số byte sẽ được gửi. Ví dụ:

```java
String json = "{\"message\":\"Xin chào\"}";
byte[] payload = json.getBytes(StandardCharsets.UTF_8);

int javaLength = json.length(); // 22 UTF-16 code units
int byteLength = payload.length; // 23 byte UTF-8
```

Vì ký tự có dấu được UTF-8 mã hóa bằng nhiều byte, **độ dài byte có thể khác `String.length()`**. Muốn biết độ dài thực của body dạng chuỗi khi dùng UTF-8, quan tâm tới `getBytes(UTF_8).length` hoặc `BodyPublisher.contentLength()` khi publisher biết trước độ dài.

### 5.2. `ofString` và encoding

```java
HttpRequest.BodyPublishers.ofString(json);
HttpRequest.BodyPublishers.ofString(json, StandardCharsets.UTF_8);
```

Trong Java 11, hai lời gọi trên đều tạo publisher mã hóa `String` bằng **UTF-8**. Lời gọi có `Charset` tường minh giúp người đọc thấy rõ ý định.

**Encoding không phải media type:** UTF-8 cho biết cách chuyển ký tự thành byte; `application/json` cho biết cấu trúc nội dung (JSON). Bạn phải bảo đảm dữ liệu và header phù hợp nhau. `BodyPublishers.ofString` không kiểm tra chuỗi có là JSON hợp lệ hay không.

Với JSON trao đổi giữa các hệ thống, hãy dùng UTF-8 theo chuẩn JSON hiện hành. `Content-Type: application/json` thường đủ; media type `application/json` không định nghĩa tham số `charset` trong đăng ký chuẩn, dù một số API chấp nhận `application/json; charset=utf-8`. **Theo hợp đồng của server** khi quyết định có gửi tham số này hay không.

### 5.3. `Content-Length` mô tả **byte**, không phải chuỗi

Trong HTTP, độ dài nội dung liên quan số **byte** của message body được truyền, không phải số ký tự Java hay số dấu cách trong JSON. Với `BodyPublisher`, gọi:

```java
long length = request.bodyPublisher()
        .orElseThrow()
        .contentLength();
```

Giá trị `contentLength()` theo API:

- **`> 0`:** publisher biết số byte cố định sẽ phát.
- **`== 0`:** publisher không có byte body để gửi.
- **`< 0`:** publisher không biết trước tổng độ dài.

Không nhầm `BodyPublisher.contentLength()` với header do người dùng tự thêm vào builder. `Content-Length` là header thường được HTTP client/transport **tự quản lý**, có thể không xuất hiện trong `request.headers()` của đối tượng vừa `build()` và có thể bị builder từ chối nếu tự đặt. Cách truyền tải thực tế còn phụ thuộc HTTP/1.1 hoặc HTTP/2, và không nhất thiết lúc nào cũng có một dòng header Content-Length trên dây.

**Không tự đặt `Content-Length` bằng `setHeader`** để “khớp” `String.length()`. Làm vậy vừa dễ sai số byte vừa xung đột với việc client quản lý framing.

## 6. Chương trình Java 11 hoàn chỉnh: chứng minh body và header độc lập

Tạo tệp **`RequestBodyAndHeadersDemo.java`**:

```java
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;

public class RequestBodyAndHeadersDemo {
    public static void main(String[] args) {
        URI uri = URI.create("https://example.com/api/messages");
        String json = "{\"message\":\"Xin chào\"}";
        byte[] payload = json.getBytes(StandardCharsets.UTF_8);

        HttpRequest post = HttpRequest.newBuilder(uri)
                .setHeader("Content-Type", "application/json; charset=utf-8")
                .setHeader("Accept", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json, StandardCharsets.UTF_8))
                .build();

        System.out.println("POST method: " + post.method());
        System.out.println("content type: " +
                post.headers().firstValue("content-type").orElse("missing"));
        System.out.println("accept: " +
                post.headers().firstValue("Accept").orElse("missing"));
        System.out.println("body publisher present: " + post.bodyPublisher().isPresent());
        System.out.println("body byte length: " +
                post.bodyPublisher().orElseThrow().contentLength());
        System.out.println("UTF-8 bytes: " + payload.length);
        System.out.println("String UTF-16 length: " + json.length());

        HttpRequest withoutContentType = HttpRequest.newBuilder(uri)
                .POST(HttpRequest.BodyPublishers.ofString(json, StandardCharsets.UTF_8))
                .build();
        System.out.println("body without content type: " +
                withoutContentType.bodyPublisher().isPresent());
        System.out.println("header without content type: " +
                withoutContentType.headers().firstValue("Content-Type").isPresent());

        HttpRequest headerOnly = HttpRequest.newBuilder(uri)
                .setHeader("Content-Type", "application/json")
                .GET()
                .build();
        System.out.println("GET content type header: " +
                headerOnly.headers().firstValue("Content-Type").isPresent());
        System.out.println("GET body publisher present: " +
                headerOnly.bodyPublisher().isPresent());

        HttpRequest noBody = HttpRequest.newBuilder(uri)
                .POST(HttpRequest.BodyPublishers.noBody())
                .build();
        System.out.println("POST noBody publisher present: " + noBody.bodyPublisher().isPresent());
        System.out.println("POST noBody bytes: " +
                noBody.bodyPublisher().orElseThrow().contentLength());

        HttpRequest binary = HttpRequest.newBuilder(uri)
                .setHeader("Content-Type", "application/octet-stream")
                .POST(HttpRequest.BodyPublishers.ofByteArray(new byte[] {1, 2, 3}))
                .build();
        System.out.println("binary body bytes: " +
                binary.bodyPublisher().orElseThrow().contentLength());

        HttpRequest mislabeled = HttpRequest.newBuilder(uri)
                .setHeader("Content-Type", "text/plain")
                .POST(HttpRequest.BodyPublishers.ofString(json, StandardCharsets.UTF_8))
                .build();
        System.out.println("mislabeled type: " +
                mislabeled.headers().firstValue("Content-Type").orElse("missing"));
        System.out.println("mislabeled length: " +
                mislabeled.bodyPublisher().orElseThrow().contentLength());

        System.out.println("request headers contain content-length: " +
                post.headers().firstValue("Content-Length").isPresent());
    }
}
```

Dùng JDK 11 trở lên. Với JDK mới, `--release 11` kiểm tra mã chỉ dùng ngôn ngữ/API có trong Java 11:

```bash
javac --release 11 -encoding UTF-8 RequestBodyAndHeadersDemo.java
java RequestBodyAndHeadersDemo
```

**Đầu ra chính xác đã kiểm thử:**

```text
POST method: POST
content type: application/json; charset=utf-8
accept: application/json
body publisher present: true
body byte length: 23
UTF-8 bytes: 23
String UTF-16 length: 22
body without content type: true
header without content type: false
GET content type header: true
GET body publisher present: false
POST noBody publisher present: true
POST noBody bytes: 0
binary body bytes: 3
mislabeled type: text/plain
mislabeled length: 23
request headers contain content-length: false
```

### 6.1. Cách đọc các kết quả

1. `POST` được build với **header `Content-Type` và `Accept`** cùng một body publisher. `headers().firstValue(...)` đọc giá trị header; `bodyPublisher()` truy cập phần thân. Hai nơi độc lập.
2. Chuỗi JSON trong ví dụ có **22 UTF-16 code units**, nhưng khi encode thành UTF-8 có **23 byte**. `contentLength()` của publisher bằng `23`, khớp `payload.length`.
3. `withoutContentType` **có body publisher** nhưng `Content-Type` vắng mặt. Builder **không tự suy đoán** media type từ `ofString`.
4. `headerOnly` là GET có `Content-Type` nhưng **không có body publisher**. Điều này chứng minh header mô tả không tự sinh dữ liệu body. Không phải khuyến nghị đặt `Content-Type` cho GET không có body.
5. `POST(BodyPublishers.noBody())` có publisher được gắn vào request nhưng **số byte bằng 0**. Vì vậy “có publisher” không đồng nghĩa “có nội dung”.
6. `ofByteArray(new byte[] {1,2,3})` tạo body dài 3 byte. `application/octet-stream` mô tả nội dung nhị phân nhưng bản thân header không làm biến đổi ba byte đó.
7. `mislabeled` có body JSON được tạo từ chuỗi, nhưng header tự khai báo `text/plain`. Java **không tự phát hiện hoặc sửa sự sai lệch này**. Phía server có thể xử lý như văn bản, trả lỗi hoặc thực hiện logic riêng.
8. `post.headers()` không chứa `Content-Length` do ứng dụng đặt; điều đó **không có nghĩa** request không thể gửi body hay client sẽ không quản lý độ dài/framing lúc thực thi.

Chương trình chỉ tạo và kiểm tra `HttpRequest` **trong bộ nhớ**, không truy cập Internet và không phụ thuộc phản hồi của `example.com`. Đây là cách phù hợp để kiểm thử đơn vị rằng phần mô tả và phần dữ liệu được cấu hình đúng.

## 7. Phân biệt các header liên quan tới nội dung

| Header | Nó mô tả gì? | Không nên hiểu thành gì? |
| --- | --- | --- |
| `Content-Type` | Media type của **body đang gửi**, có thể kèm tham số theo loại media | Không tự tạo JSON, multipart hoặc thay đổi byte |
| `Accept` | Media type của **response mong muốn** | Không phải định dạng body gửi đi |
| `Content-Encoding` | Content coding đã được áp dụng cho representation/body, ví dụ `gzip` | Không phải charset; chỉ đặt header không tự nén dữ liệu |
| `Content-Length` | Độ dài theo **byte** của body theo quy tắc HTTP | Không phải `String.length()`; để HTTP client xử lý framing |
| `Authorization` | Thông tin xác thực cho yêu cầu | Không phải mô tả kiểu dữ liệu; cần bảo mật, tránh log |
| `Content-Disposition` (khi dùng) | Gợi ý cách trình bày/đặt tên dữ liệu, hoặc metadata trong từng phần multipart | Không tự sinh nội dung file hoặc các phần multipart |

**`Content-Type` với `Content-Encoding` là hai khía cạnh khác nhau.** Ví dụ JSON được nén gzip trước khi gửi có thể mang:

```http
Content-Type: application/json
Content-Encoding: gzip
```

Nhưng trong trường hợp này, **byte body phải thực sự là dữ liệu gzip** chứ không phải chuỗi JSON chưa nén. Chỉ thêm `Content-Encoding: gzip` bằng builder mà vẫn dùng `ofString(json)` sẽ gửi byte JSON thường trong khi header nói sai. Với dữ liệu chưa nén, không thêm header gzip.

**`Accept-Encoding`**, nếu được dùng, thể hiện cách mã hóa nội dung phản hồi client có thể chấp nhận; không nên lẫn với `Content-Encoding` của body đang gửi. Việc tự giải nén phản hồi và hỗ trợ thuật toán nào cần đối chiếu với hành vi cụ thể của `HttpClient` và contract ứng dụng.

## 8. Chọn `Content-Type` phù hợp với body

Dưới đây là các tình huống thường gặp, tất cả vẫn áp dụng hiện nay:

| Body được phát | `Content-Type` điển hình | Cách tạo trong Java 11 |
| --- | --- | --- |
| JSON encode UTF-8 | `application/json` | `BodyPublishers.ofString(json, UTF_8)` |
| Văn bản thường UTF-8 | `text/plain; charset=utf-8` | `BodyPublishers.ofString(text, UTF_8)` |
| Byte nhị phân không có media type cụ thể | `application/octet-stream` | `BodyPublishers.ofByteArray(bytes)` |
| Nội dung ảnh PNG | `image/png` | `BodyPublishers.ofByteArray(pngBytes)` hoặc `ofFile(path)` |
| Form URL-encoded | `application/x-www-form-urlencoded` | Publisher phát chuỗi **đã form-encode từng trường** |
| Multipart | `multipart/form-data; boundary=...` | Publisher phát đúng cấu trúc **multipart với boundary khớp header** |

`ofFile(path)` đọc byte từ tệp; nó không tự suy rằng tệp `.png` là `image/png` hay `.json` là `application/json`. Khi dùng publisher tùy chỉnh hoặc stream từ file, phải tự biết **dữ liệu thực tế** và xác lập header thích hợp.

**Với form URL-encoded:** body không phải JSON. Nó thường có dạng `name=Lan&city=Ha+Noi` sau khi form-encode giá trị; khoảng trắng có thể trở thành `+` theo quy tắc form encoding. Không chỉ đặt `Content-Type: application/x-www-form-urlencoded` rồi gửi một chuỗi JSON và cho rằng đúng.

**Với multipart:** `boundary` là chuỗi phân tách các phần trong **byte body**, phải khớp chính xác tham số `boundary` của `Content-Type`. `BodyPublishers.ofString` không tự tạo multipart, và `BodyPublishers.ofFile` không tự thêm boundary. Nên dùng thư viện hoặc builder multipart đáng tin cậy khi phải gửi nhiều phần.

## 9. Phân biệt `BodyPublisher` và `BodyHandler`

Hai giao diện này nằm ở **hai chiều dữ liệu** khác nhau:

- **`HttpRequest.BodyPublisher`:** chuẩn bị các byte **request gửi đi**. Nó được truyền vào `POST(...)`, `PUT(...)` hoặc `method(...)`.
- **`HttpResponse.BodyHandler<T>`:** quyết định cách xử lý các byte **response nhận về** thành `String`, `byte[]`, stream, tệp hoặc kiểu khác. Nó được truyền cho `HttpClient.send(...)` hoặc `sendAsync(...)`.

Ví dụ ngắn:

```java
// Mã minh họa: đã có HttpClient client và URI uri.
HttpRequest req = HttpRequest.newBuilder(uri)
        .setHeader("Content-Type", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(
                "{\"id\":7}", StandardCharsets.UTF_8))
        .build();

HttpResponse<String> response = client.send(
        req, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
```

Đoạn này **không độc lập**: cần import `HttpRequest`, `HttpResponse`, `StandardCharsets`; cung cấp `client` và `uri`; xử lý `IOException` và `InterruptedException`; cần endpoint mạng thật. Không có mã trạng thái/response cố định nào được giả định.

**Sai lầm thường gặp:** đặt `Accept: application/json` không thay thế được bước parse response JSON. `BodyHandlers.ofString(UTF_8)` chỉ giải mã byte thành String; nếu muốn cấu trúc object từ JSON, phải dùng parser/serializer JSON thích hợp.

## 10. Cách gửi body từ stream hoặc file và các lưu ý hiện hành

### 10.1. Các lựa chọn của `BodyPublishers`

| Publisher | Nguồn dữ liệu | Độ dài thường có biết trước không? |
| --- | --- | --- |
| `noBody()` | Không phát byte | Có: 0 |
| `ofString(s, charset)` | Byte đã encode từ String | Có: số byte |
| `ofByteArray(bytes)` | Mảng byte | Có: số byte |
| `ofFile(path)` | Nội dung file | Tùy khả năng truy cập và thông tin file của publisher |
| `ofInputStream(supplier)` | InputStream do supplier tạo khi cần gửi | Thường không biết trước; xem `contentLength()` |
| `fromPublisher(publisher)` | Publisher các `ByteBuffer` | Không mặc định biết trước nếu không được cung cấp |

Các API trên có từ Java 11. Nếu body là tệp dung lượng lớn hoặc nguồn stream, không nhất thiết nên tải toàn bộ vào `byte[]` hay `String` trước; chọn publisher hỗ trợ phát từng phần để kiểm soát bộ nhớ. Đồng thời, vẫn cần chính sách giới hạn độ lớn, timeout và xử lý lỗi I/O phù hợp.

### 10.2. Lưu ý khi request cần gửi lại

Đối với body tạo từ `ofInputStream(supplier)`, supplier có thể được gọi cho **mỗi lần client subscribe**. Retry, redirect hoặc xác thực lại có thể đòi phát lại body; vì vậy supplier cần có khả năng tạo luồng mới hợp lệ khi contract yêu cầu, không dùng một `InputStream` đã đọc cạn rồi trả lại mù quáng.

`HttpRequest` sau `build()` có cấu hình bất biến, nhưng điều này không đảm bảo **nội dung nguồn ngoài** như file hoặc stream bất biến. Cân nhắc tính nhất quán và an toàn khi retry dữ liệu quan trọng.

Không đặt header `Content-Length` theo cảm tính để “sửa” độ dài unknown của stream. Để HTTP client chọn framing hợp lệ và chỉ định kích thước chính xác khi API publisher hỗ trợ/hợp đồng bắt buộc.

## 11. Những lỗi phổ biến và cách khắc phục

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Server báo body rỗng dù có `Content-Type: application/json` | Chỉ đặt header, chưa gắn body publisher | Gắn `POST(BodyPublishers.ofString(json, UTF_8))` hoặc publisher phù hợp |
| Server không parse JSON | Body không phải JSON hợp lệ hoặc `Content-Type` sai/thiếu | Serialize JSON thật, encode UTF-8, khai báo media type đúng |
| Server trả HTTP `415 Unsupported Media Type` | Media type không được endpoint chấp nhận | Kiểm tra contract và `Content-Type` |
| Server trả HTTP `400 Bad Request` | Dữ liệu sai cấu trúc, JSON hỏng hoặc validation không đạt | Xem lỗi server, validate/serialize body đúng schema |
| Server trả HTTP `406 Not Acceptable` | Server không thể trả media type đáp ứng `Accept` | Kiểm tra định dạng phản hồi mà endpoint hỗ trợ |
| Tiếng Việt bị lỗi ký tự | Charset dùng để encode body không khớp cách decode của server | Đặt quy tắc UTF-8 nhất quán; kiểm tra byte thật |
| `Content-Length` không bằng `String.length()` | Ký tự Unicode có thể dùng nhiều byte UTF-8 | Đếm byte encoded; để client quản lý `Content-Length` |
| Có `Content-Type` nhưng `bodyPublisher().isPresent() == false` | Header và body độc lập | Kiểm tra request method và publisher |
| `bodyPublisher().isPresent() == true` nhưng không có nội dung | Publisher như `noBody()` phát 0 byte | Xem `contentLength()` và nguồn dữ liệu thực tế |
| Tưởng `Accept` quyết định format gửi đi | `Accept` chỉ mô tả response mong muốn | Đặt `Content-Type` cho body và `Accept` cho response khi phù hợp |
| Đặt `Content-Encoding: gzip` nhưng gửi JSON text chưa nén | Header mô tả sai content coding | Nén byte bằng gzip thật hoặc bỏ header |
| Multipart bị lỗi phân tách | `boundary` không khớp với byte body | Tạo multipart đúng cấu trúc và boundary |
| Ứng dụng cố thêm `Content-Length` thủ công | HTTP client có thể hạn chế header tự quản lý | Không tự thêm; xem độ dài publisher và dùng API được hỗ trợ |
| HTTP request build thành công nhưng không có phản hồi | `build()` không gửi mạng | Dùng `HttpClient.send`/`sendAsync` và xử lý response |
| Ghi log lộ token hoặc dữ liệu nhạy cảm | Log nguyên headers/body | Redact `Authorization`, cookie, thông tin cá nhân trước khi log |

Mã HTTP 400, 406, 415 chỉ là **ví dụ các tình huống server có thể lựa chọn**, không phải kết quả được Java `HttpClient` bảo đảm. Phản hồi thực tế phải dựa vào server và contract cụ thể.

## 12. An toàn và best practices

1. **Thiết kế dữ liệu trước, metadata sau:** biết chính xác bạn gửi JSON, form, file hay byte stream nào; serialize và encode rồi chọn `Content-Type` tương ứng. Không dùng header để chữa body sai.
2. **Đặt đúng chiều thông tin:** `Content-Type` cho nội dung request, `Accept` cho response mong muốn; `Content-Encoding` chỉ khi body đã trải qua content coding tương ứng.
3. **Đừng tự xây JSON bằng nối chuỗi người dùng** nếu có dữ liệu nhập phức tạp; dùng JSON serializer phù hợp để escape và validate, tránh tạo JSON sai cú pháp.
4. **Chọn UTF-8 nhất quán** cho JSON và văn bản khi endpoint hỗ trợ; không dựa vào platform default charset.
5. **Không hardcode hoặc log bí mật.** Giới hạn thông tin in ra từ headers, query và body; tránh ghi credential, token, cookie, dữ liệu cá nhân vào log.
6. **Giới hạn kích thước body và kiểm soát nguồn file/stream** để tránh tăng bộ nhớ, I/O không kiểm soát và truyền dữ liệu ngoài mong muốn.
7. **Kiểm tra `request.headers()` và `request.bodyPublisher()` trong unit test** để xác nhận cấu hình; nhớ rằng đây chưa phải kiểm chứng toàn bộ HTTP giao tiếp trên dây.
8. **Xử lý response thực tế** bằng status code, headers, body handler và timeout. Việc có header đúng không bảo đảm server chấp nhận nội dung.
9. **Dùng HTTPS** cho dữ liệu quan trọng; đồng thời xác thực URI đích và các redirect theo chính sách để tránh gửi body hoặc token đến host không đáng tin.
10. **Dùng API hiện hành của Java 11+:** `HttpRequest.Builder`, `BodyPublisher` và `HttpClient` vẫn được duy trì trong các JDK hiện đại.

## 13. Bài tập tự kiểm tra

**Câu 1:** Nếu builder chỉ gọi `setHeader("Content-Type","application/json")` rồi `GET().build()`, body có tự xuất hiện không?  
**Đáp án:** Không. Header không tạo byte body; request GET này không có body publisher.

**Câu 2:** Nếu gọi `POST(BodyPublishers.ofString(json))` nhưng không đặt `Content-Type`, có gửi body không?  
**Đáp án:** Có publisher cho body; nhưng không tự gán media type JSON. Server có thể xử lý khác dự kiến.

**Câu 3:** `Content-Type` và `Accept` khác nhau thế nào?  
**Đáp án:** `Content-Type` mô tả body yêu cầu đang gửi; `Accept` mô tả kiểu phản hồi mong muốn từ server.

**Câu 4:** JSON String dài 22 code unit Java nhưng sau UTF-8 dài 23 byte. `Content-Length` nên dựa trên số nào?  
**Đáp án:** Byte body theo quy tắc HTTP, không dựa vào `String.length()`; để client quản lý header/framing.

**Câu 5:** `POST(BodyPublishers.noBody())` có `bodyPublisher().isPresent()` là `true` không?  
**Đáp án:** Có, vì đã gắn một publisher; nhưng `contentLength()` bằng `0`, không có byte body.

**Câu 6:** Có thể gửi dữ liệu JSON chưa nén nhưng đặt `Content-Encoding: gzip` để server tự nén không?  
**Đáp án:** Không. Header nói rằng body **đã được mã hóa/nén bằng gzip**, nên phải nén thật trước khi gửi.

**Câu 7:** `HttpResponse.BodyHandlers.ofString(...)` dùng cho request body hay response body?  
**Đáp án:** Dùng cho **response body nhận về**; request body được phát qua `HttpRequest.BodyPublisher`.

**Câu 8:** Nếu body là ảnh PNG, đặt `Content-Type: image/png` đã đủ chưa?  
**Đáp án:** Chưa. Phải cung cấp **byte ảnh PNG thực tế** qua publisher; header chỉ mô tả loại nội dung.

## 14. Ghi nhớ

- **Body = byte dữ liệu thực**, được phát qua `HttpRequest.BodyPublisher`.
- **Headers = metadata** mô tả request; `Content-Type` mô tả body gửi đi, `Accept` mô tả response mong muốn.
- **Header có thể có mà body không có**, hoặc **body có nhưng thiếu Content-Type**. `build()` không tự sửa sự không nhất quán.
- `BodyPublishers.ofString` mã hóa UTF-8 theo mặc định; nó không tự tạo JSON hợp lệ hoặc đặt media type JSON.
- **Độ dài body theo byte**, không theo `String.length()`; `BodyPublisher.contentLength()` có thể dương, 0 hoặc âm khi chưa biết.
- Với JSON, file, binary, form hoặc multipart, **byte thực tế** và `Content-Type` phải cùng tuân thủ contract API. `Content-Encoding` chỉ khai báo content coding đã thực hiện.
- `HttpClient.send` / `sendAsync` mới thực sự gửi dữ liệu; phân biệt `BodyPublisher` cho request với `BodyHandler` cho response.

**Tài liệu chính thức:** [JEP 321 — HTTP Client (Standard)](https://openjdk.org/jeps/321); [Java 11 — HttpRequest](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.html); [Java 11 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html); [Java 11 — BodyPublishers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html); [Java 11 — BodyPublisher](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html); [Java 25 — BodyPublisher](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html); [RFC 8259 — JSON](https://www.rfc-editor.org/rfc/rfc8259).