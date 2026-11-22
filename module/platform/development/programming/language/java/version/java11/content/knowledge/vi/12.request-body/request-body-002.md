# `HttpRequest.BodyPublishers.ofString` với charset trong Java 11

## 1. Tổng quan: gửi `String` là gửi byte, không phải gửi đối tượng Java

Từ **Java 11**, HTTP Client chuẩn nằm trong module `java.net.http`. Khi tạo một HTTP request có body là văn bản, cách phổ biến là dùng:

```java
HttpRequest.BodyPublisher publisher =
        HttpRequest.BodyPublishers.ofString(
                "Xin chào", StandardCharsets.UTF_8);
```

`BodyPublishers.ofString(String, Charset)` tạo một `HttpRequest.BodyPublisher` đưa nội dung `String` qua bước **mã hóa ký tự thành byte** bằng charset được chỉ định. Đây là phần quan trọng của request body: HTTP truyền các byte của payload, không truyền trực tiếp đối tượng `String` hay các đơn vị UTF-16 mà Java dùng để lưu chuỗi.

Có hai overload cùng tồn tại trên Java 11 và các JDK hiện hành:

```java
// Dùng UTF-8 mặc định theo hợp đồng API.
HttpRequest.BodyPublisher p1 =
        HttpRequest.BodyPublishers.ofString(text);

// Chỉ định charset rõ ràng.
HttpRequest.BodyPublisher p2 =
        HttpRequest.BodyPublishers.ofString(
                text, StandardCharsets.UTF_8);
```

**`ofString(text)` mặc định là UTF-8**, không dùng charset mặc định của hệ điều hành. `ofString(text, charset)` dùng đúng charset do caller cung cấp. Trường hợp hai overload đều dùng UTF-8, chúng sinh cùng nội dung byte cho cùng một `String`.

Điểm cần nhớ: **charset mã hóa request body** và **header `Content-Type` mô tả request body** là hai việc khác nhau. `ofString` không tự tạo `Content-Type` tương ứng.

## 2. Các khái niệm thường bị trộn lẫn

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| Chuỗi logic | `"Xin chào ☕"` | Nội dung văn bản ứng dụng muốn gửi |
| `Charset` | `StandardCharsets.UTF_8` | Quy tắc chuyển ký tự thành các byte |
| Body publisher | `BodyPublishers.ofString(text, UTF_8)` | Nguồn cung cấp các byte cho HTTP Client |
| Media type | `text/plain`, `application/json` | Mô tả dạng dữ liệu |
| Header `Content-Type` | `text/plain; charset=UTF-8` | Giúp phía nhận biết cách diễn giải payload |
| Độ dài body | `publisher.contentLength()` | Số **byte**, không phải số ký tự |
| `HttpRequest` | `HttpRequest.newBuilder(uri).POST(publisher).build()` | Mô tả một yêu cầu HTTP; chưa gửi dữ liệu |
| `HttpClient` | `client.send(request, handler)` | Gửi yêu cầu và xử lý phản hồi |

Luồng dữ liệu:

```text
String của Java
    |
    | ofString(body, Charset) — mã hóa ký tự
    v
byte[] / luồng các ByteBuffer của BodyPublisher
    |
    | HttpRequest.POST(publisher) + Content-Type
    v
HttpClient gửi HTTP request
    |
    v
Server nhận byte + giải mã/parse theo hợp đồng Content-Type
```

`BodyPublisher` là một `Flow.Publisher<ByteBuffer>`. HTTP Client sẽ subscribe vào publisher khi truyền body. Điều này **không có nghĩa text được lấy từ file hay socket theo kiểu streaming**: với `ofString`, ứng dụng đã có toàn bộ `String` và publisher đại diện cho nội dung đã được mã hóa từ chuỗi đó.

Nếu cần truyền dữ liệu rất lớn từ nguồn khác, cân nhắc `ofFile` hoặc `ofInputStream` thay vì dựng một `String` khổng lồ; lựa chọn phụ thuộc bộ nhớ, hiệu năng và yêu cầu lặp lại request.

## 3. API: chữ ký, charset mặc định và giá trị trả về

### 3.1. Hai overload chính

```java
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;

// String body
HttpRequest.BodyPublisher defaultUtf8 =
        HttpRequest.BodyPublishers.ofString(body);

// String body, Charset charset
HttpRequest.BodyPublisher explicitUtf8 =
        HttpRequest.BodyPublishers.ofString(
                body, StandardCharsets.UTF_8);
```

Cả hai đều có từ Java 11. Loại trả về là `HttpRequest.BodyPublisher`, không phải `String`, `byte[]` hay `HttpRequest`. Gọi `ofString` **không gửi request**. Phải gắn publisher vào `HttpRequest.Builder` và gọi `HttpClient.send` hoặc `sendAsync` khi thật sự muốn gửi qua mạng.

### 3.2. Dùng `StandardCharsets` thay vì đoán charset hệ thống

Các hằng chuẩn hữu ích:

- `StandardCharsets.UTF_8` — lựa chọn ưu tiên cho API văn bản hiện đại; tương thích rộng và hỗ trợ Unicode.
- `StandardCharsets.UTF_16BE`, `StandardCharsets.UTF_16LE` — dùng khi giao thức thực sự quy định mã hóa UTF-16 với byte order cụ thể.
- `StandardCharsets.UTF_16` — UTF-16 có quy ước BOM/byte-order riêng; **không tự coi nó tương đương UTF-16BE**.
- `StandardCharsets.ISO_8859_1`, `US_ASCII` — chỉ chọn khi endpoint hoặc định dạng đầu vào **quy định rõ**. Chúng không biểu diễn đầy đủ Unicode, dễ mất thông tin.

Thông thường:

```java
HttpRequest.BodyPublishers.ofString(text, StandardCharsets.UTF_8)
```

tốt hơn việc phụ thuộc charset hệ thống qua các thao tác như `text.getBytes()` **không có đối số**. Không cần `Charset.forName("UTF-8")` nếu đã có `StandardCharsets.UTF_8`, vừa rõ ý nghĩa vừa tránh sai tên charset ở runtime.

### 3.3. `contentLength()` đo số byte đã mã hóa

Ví dụ:

```java
String text = "Xin chào ☕";

System.out.println(text.length()); // 10 — đơn vị UTF-16

HttpRequest.BodyPublisher p =
        HttpRequest.BodyPublishers.ofString(
                text, StandardCharsets.UTF_8);

System.out.println(p.contentLength()); // 13 — byte UTF-8
```

Chuỗi trên có 10 đơn vị UTF-16 nhưng thành 13 byte UTF-8. Ký tự `à` cần 2 byte UTF-8 và `☕` cần 3 byte, trong khi chữ ASCII thông thường cần 1 byte.

`contentLength()` trả số byte body mà publisher dự kiến phát đi, **không phải số ký tự, code point hay tổng độ dài HTTP request**. Interface `BodyPublisher` cho phép một số publisher khác báo `-1` nếu không biết độ dài trước, nhưng `ofString` biết độ dài nội dung đã mã hóa. Với body rỗng, publisher có độ dài 0.

**Không tự thiết lập `Content-Length` bằng `text.length()`.** HTTP Client xử lý phần framing/request content length theo body publisher và giao thức HTTP tương ứng; tên header này cũng có thể bị implementation hạn chế không cho người dùng tùy ý đặt.

## 4. Charset trong body và `Content-Type` phải khớp nhau

Một request text/plain UTF-8 thông thường:

```java
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;

String message = "Xin chào ☕";

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.com/messages"))
        .header("Content-Type", "text/plain; charset=UTF-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                message, StandardCharsets.UTF_8))
        .build();
```

`ofString(..., UTF_8)` quyết định **byte thật**. Header `Content-Type: text/plain; charset=UTF-8` thông báo cho server rằng body là văn bản thuần mã hóa UTF-8. Hai thành phần cần phù hợp; Java không tự kiểm tra xem nhãn charset trong header có khớp charset bạn dùng để tạo byte hay không.

Ví dụ về **hai cách viết không nhất quán**:

```java
// Sai contract: body là UTF-16BE nhưng header nói UTF-8.
HttpRequest inconsistent = HttpRequest.newBuilder(
        URI.create("https://api.example.com/messages"))
        .header("Content-Type", "text/plain; charset=UTF-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                message, StandardCharsets.UTF_16BE))
        .build();
```

Đoạn mã có thể xây request hợp lệ về mặt Java, nhưng server giải mã body theo UTF-8 sẽ đọc sai hoặc từ chối dữ liệu. Builder không tự chuyển đổi UTF-16BE về UTF-8 để khớp header.

Một số media type có quy tắc charset riêng. Chẳng hạn với JSON trao đổi giữa các hệ thống hiện đại, định dạng theo RFC 8259 sử dụng UTF-8 và `Content-Type: application/json` là cách khai báo thông thường. Với `text/plain`, nêu `charset=UTF-8` rõ ràng giúp tránh nhầm lẫn. **Ưu tiên hợp đồng API/server**, không áp một quy tắc charset header cho mọi media type.

### Có tự sinh `Content-Type` khi gọi `ofString` không?

**Không.** So sánh:

```java
HttpRequest noType = HttpRequest.newBuilder(
        URI.create("https://api.example.com/messages"))
        .POST(HttpRequest.BodyPublishers.ofString(message))
        .build();

System.out.println(
        noType.headers().firstValue("Content-Type").isEmpty());
// true
```

`BodyPublishers.ofString` xác định cách biến chuỗi thành byte. Nếu cần header, caller phải đặt `.header("Content-Type", "...")` theo format của payload. Không nên nghĩ việc có charset là tự động suy ra media type.

## 5. Chương trình Java 11+ có thể chạy: xem chính xác byte do publisher tạo

Chương trình sau không cần mạng: nó tạo HTTP request với `ofString`, rồi dùng một `Flow.Subscriber<ByteBuffer>` để lấy các byte mà publisher phát. Đây là cách **kiểm thử publisher**; khi chạy production, HTTP Client sẽ thực hiện subscription thay ứng dụng.

Lưu nguyên đoạn code vào file **`OfStringCharsetDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Flow;
import java.util.concurrent.TimeUnit;

public class OfStringCharsetDemo {
    // Helper kiểm thử: thu byte đã được BodyPublisher publish.
    static byte[] collect(HttpRequest.BodyPublisher publisher)
            throws Exception {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        CompletableFuture<byte[]> finished = new CompletableFuture<>();

        publisher.subscribe(new Flow.Subscriber<ByteBuffer>() {
            public void onSubscribe(Flow.Subscription subscription) {
                subscription.request(Long.MAX_VALUE);
            }

            public void onNext(ByteBuffer chunk) {
                byte[] bytes = new byte[chunk.remaining()];
                chunk.get(bytes);
                output.write(bytes, 0, bytes.length);
            }

            public void onError(Throwable error) {
                finished.completeExceptionally(error);
            }

            public void onComplete() {
                finished.complete(output.toByteArray());
            }
        });

        return finished.get(5, TimeUnit.SECONDS);
    }

    public static void main(String[] args) throws Exception {
        String text = "Xin ch\u00E0o \u2615";

        HttpRequest.BodyPublisher utf8 =
                HttpRequest.BodyPublishers.ofString(
                        text, StandardCharsets.UTF_8);

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://api.example.com/messages"))
                .header("Content-Type",
                        "text/plain; charset=UTF-8")
                .POST(utf8)
                .build();

        byte[] bytes = collect(
                request.bodyPublisher().orElseThrow());

        System.out.println("method=" + request.method());
        System.out.println("contentType=" +
                request.headers()
                        .firstValue("Content-Type").orElse("missing"));
        System.out.println("chars=" + text.length());
        System.out.println("utf8Bytes=" + bytes.length);
        System.out.println("publisherLength=" + utf8.contentLength());
        System.out.println("utf8RoundTrip=" +
                text.equals(new String(bytes, StandardCharsets.UTF_8)));

        System.out.println("defaultIsUtf8=" +
                Arrays.equals(bytes, collect(
                        HttpRequest.BodyPublishers.ofString(text))));

        System.out.println("wrongDecodeWorks=" +
                text.equals(new String(
                        bytes, StandardCharsets.ISO_8859_1)));

        HttpRequest.BodyPublisher utf16 =
                HttpRequest.BodyPublishers.ofString(
                        text, StandardCharsets.UTF_16BE);
        byte[] utf16Bytes = collect(utf16);

        System.out.println("utf16beBytes=" + utf16Bytes.length);
        System.out.println("utf16beRoundTrip=" +
                text.equals(new String(
                        utf16Bytes, StandardCharsets.UTF_16BE)));

        HttpRequest.BodyPublisher latin1 =
                HttpRequest.BodyPublishers.ofString(
                        text, StandardCharsets.ISO_8859_1);
        System.out.println("latin1RoundTrip=" +
                text.equals(new String(
                        collect(latin1), StandardCharsets.ISO_8859_1)));

        HttpRequest noType = HttpRequest.newBuilder(
                URI.create("https://api.example.com/messages"))
                .POST(HttpRequest.BodyPublishers.ofString(text))
                .build();

        System.out.println("contentTypeMissing=" +
                noType.headers()
                        .firstValue("Content-Type").isEmpty());

        System.out.println("emptyLength=" +
                HttpRequest.BodyPublishers.ofString("")
                        .contentLength());
    }
}
```

Biên dịch và chạy bằng JDK 11 trở lên:

```bash
javac --release 11 OfStringCharsetDemo.java
java OfStringCharsetDemo
```

Stdout đã kiểm tra:

```text
method=POST
contentType=text/plain; charset=UTF-8
chars=10
utf8Bytes=13
publisherLength=13
utf8RoundTrip=true
defaultIsUtf8=true
wrongDecodeWorks=false
utf16beBytes=20
utf16beRoundTrip=true
latin1RoundTrip=false
contentTypeMissing=true
emptyLength=0
```

**Giải thích:**

1. `method=POST`: builder đã được cấu hình để gửi POST, nhưng trong chương trình này **chưa gọi `HttpClient.send`** nên không có kết nối mạng.
2. `contentType=...`: header được đặt rõ ràng bằng `.header(...)`, không tự xuất hiện nhờ `ofString`.
3. `chars=10` khác `utf8Bytes=13`: số đơn vị UTF-16 không phải số byte UTF-8.
4. `publisherLength=13`: publisher biết trước độ dài byte cần publish.
5. `utf8RoundTrip=true`: giải mã bằng cùng UTF-8 khôi phục chính xác chuỗi.
6. `defaultIsUtf8=true`: overload `ofString(text)` tạo cùng byte với `ofString(text, UTF_8)`.
7. `wrongDecodeWorks=false`: giải mã byte UTF-8 bằng Latin-1 cho kết quả khác. Charset hai phía không khớp.
8. `utf16beBytes=20`: cùng 10 đơn vị UTF-16 khi encode UTF-16BE chiếm 20 byte, vì charset này dùng 2 byte cho mỗi đơn vị UTF-16 của chuỗi mẫu.
9. `latin1RoundTrip=false`: `ISO_8859_1` không biểu diễn được ký tự `☕`, nên chuyển đổi qua charset ấy không bảo toàn dữ liệu. Đây là **ví dụ lỗi để cảnh báo**, không khuyến nghị Latin-1 cho API Unicode.
10. `contentTypeMissing=true` xác nhận `ofString` không tự gắn media type; `emptyLength=0` cho body rỗng.

Một điểm kỹ thuật: `Flow.Subscriber` trong ví dụ là test helper gom toàn bộ byte vào RAM và có timeout, không phải thiết kế mặc định cho body lớn. Trong thực tế, `HttpClient` tự subscribe để lấy byte; code ứng dụng thường chỉ cần `ofString` và request builder.

## 6. Hiểu sai charset có thể gây hỏng dữ liệu ở đâu?

### 6.1. Mã hóa và giải mã phải thống nhất

Ví dụ body `"Xin chào ☕"` encode UTF-8 tạo byte. Nếu phía nhận decode những byte ấy bằng ISO-8859-1 hoặc UTF-16BE, ký tự có dấu và ký tự Unicode ngoài ASCII có thể bị sai.

```text
Client Java String
      |
      | ofString(body, UTF_8)
      v
UTF-8 bytes  -- HTTP -->  server
                              |
                              | decode UTF-8 (đúng) -> chuỗi ban đầu
                              | decode Latin-1 (sai) -> văn bản lỗi
```

Không có cơ chế tự nhận diện chắc chắn charset chỉ từ một dãy byte bất kỳ. Cách đúng là **định nghĩa charset theo giao thức**, ghi nhãn Content-Type phù hợp khi cần và sử dụng cùng quy tắc ở phía nhận.

### 6.2. `String.length()` không đủ để tính byte

Trong Java, `String.length()` là số **đơn vị UTF-16**, không phải số Unicode code point hay byte. Một code point ngoài BMP có thể chiếm 2 đơn vị UTF-16; trong UTF-8 thường là 4 byte. Vì vậy:

```java
String text = "Xin chào ☕";
long charactersAsUtf16Units = text.length(); // 10

int encodedByteLength =
        text.getBytes(StandardCharsets.UTF_8).length; // 13
```

Không dùng `String.length()` để tính `Content-Length` hoặc để cắt byte payload theo chiều dài ký tự. `BodyPublisher.contentLength()` mới thể hiện độ dài body theo byte của publisher này.

### 6.3. Charset không biểu diễn được ký tự và replacement

Không phải charset nào cũng chứa toàn bộ Unicode. Với các charset hạn chế, những ký tự không thể biểu diễn có thể bị **thay bằng ký tự thay thế** khi encode qua các API chuyển chuỗi thông thường. Ví dụ `ISO_8859_1` không có ký tự `☕`, nên khi encode rồi decode lại sẽ không bằng chuỗi ban đầu.

Nếu hệ thống đòi hỏi **không chấp nhận bất kỳ mất mát dữ liệu nào**, nên ưu tiên UTF-8 nếu protocol cho phép. Khi bắt buộc dùng charset hạn chế, validate tập ký tự đầu vào hoặc dùng `CharsetEncoder` với `CodingErrorAction.REPORT` trước khi tạo publisher từ byte đã kiểm chứng.

Ví dụ helper **đặt trong lớp**, dùng khi protocol bắt buộc charset khác và yêu cầu báo lỗi thay vì âm thầm thay thế:

```java
import java.net.http.HttpRequest;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.Charset;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.CharacterCodingException;

static HttpRequest.BodyPublisher encodeStrictly(
        String text, Charset charset)
        throws CharacterCodingException {
    CharsetEncoder encoder = charset.newEncoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT);

    ByteBuffer encoded = encoder.encode(CharBuffer.wrap(text));
    byte[] bytes = new byte[encoded.remaining()];
    encoded.get(bytes);
    return HttpRequest.BodyPublishers.ofByteArray(bytes);
}
```

Lý do dùng `ofByteArray` ở đây: helper đã thực hiện mã hóa một lần bằng một encoder có chính sách lỗi rõ ràng; publisher chỉ cần xuất **đúng byte đã được kiểm tra**. Không phải cứ gọi `ofByteArray` là dữ liệu tự nhiên đã đúng charset — nội dung byte vẫn do caller chịu trách nhiệm.

### 6.4. Tránh lẫn mã hóa ký tự với nén hoặc mã hóa URL

- Charset encoding: `String -> byte[]` theo UTF-8, UTF-16BE, ...
- Percent-encoding của URL/form: dữ liệu được biểu diễn với `%HH` hoặc `+` theo quy tắc thành phần URI/form.
- Compression: nén byte bằng gzip/deflate (nếu được yêu cầu), khác việc chọn charset.
- Encryption: mã hóa bảo mật dữ liệu; không phải `Charset`.

`ofString` thực hiện **charset encoding**, **không tự** JSON-serialize, URL-encode, gzip, tạo multipart boundary hoặc mã hóa bảo mật. Các biến đổi khác phải do code hoặc thư viện chuyên dụng thực hiện theo format.

## 7. Thực hành POST body dạng văn bản và dạng JSON

### 7.1. Văn bản thuần `text/plain`

Ví dụ chuẩn:

```java
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;

String note = "Đã xử lý đơn hàng #42";

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.com/notes"))
        .header("Content-Type", "text/plain; charset=UTF-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                note, StandardCharsets.UTF_8))
        .build();
```

Dấu `#`, dấu cách và ký tự tiếng Việt ở **request body** chỉ là dữ liệu văn bản; không phải dấu `#fragment` của URI, vì code không đặt chúng vào URL. `ofString` chuyển chuỗi thành byte UTF-8; không percent-encode dấu `#` trong body text.

### 7.2. JSON cần serialization trước khi tạo body

Giả sử endpoint nhận JSON. Có thể tạo `HttpRequest`:

```java
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;

// JSON hợp lệ được tạo sẵn trong ví dụ, không có dữ liệu nhập tự do.
String json = "{\"message\":\"Xin chào ☕\"}";

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.com/messages"))
        .header("Content-Type", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(
                json, StandardCharsets.UTF_8))
        .build();
```

Trong trao đổi JSON giữa các hệ thống hiện đại, **UTF-8** là lựa chọn chuẩn theo RFC 8259. Header `application/json` là dạng phổ biến; không cần suy luận rằng mọi JSON endpoint phải có `charset=UTF-8` parameter. Chú ý:

- `ofString` không xác nhận chuỗi là JSON hợp lệ.
- `ofString` không escape dấu ngoặc kép, backslash, newline hoặc các ký tự cần escape theo JSON.
- Không ghép chuỗi JSON thủ công với dữ liệu người dùng chưa được serialize; hãy dùng JSON serializer (ví dụ Jackson, Gson hoặc thư viện JSON đã được dự án lựa chọn) để sinh văn bản JSON đúng.
- Sau khi đã có JSON string đúng, `ofString(json, UTF_8)` chịu trách nhiệm chuyển nó thành byte.
- Header và contract server quyết định kiểu nội dung, không phải extension của đối tượng Java.

Lưu ý **không có API JSON serializer tích hợp trong `BodyPublishers.ofString`**. Dù gọi `POST(BodyPublishers.ofString(s))`, Java không tự hiểu `s` là object hoặc định dạng JSON.

### 7.3. Form body `application/x-www-form-urlencoded`

Khi endpoint **quy định** body dạng HTML form, cần chuẩn hóa các tên/giá trị theo form encoding **trước khi** chuyển cả chuỗi form thành byte:

```java
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;

String value = "C++ & Java";
String form = "message=" +
        URLEncoder.encode(value, StandardCharsets.UTF_8);

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.com/forms"))
        .header("Content-Type",
                "application/x-www-form-urlencoded; charset=UTF-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                form, StandardCharsets.UTF_8))
        .build();

System.out.println(form);
// message=C%2B%2B+%26+Java

System.out.println(request.bodyPublisher()
        .orElseThrow().contentLength());
// 24
```

Hai bước có chức năng **khác nhau**:

1. `URLEncoder.encode(value, UTF_8)` biến **giá trị form** thành ký tự `%HH`/`+` để `&`, `+` và các ký tự đặc biệt không phá cấu trúc form.
2. `BodyPublishers.ofString(form, UTF_8)` biến toàn bộ chuỗi form đã đúng cú pháp thành các byte HTTP body.

Không dùng `URLEncoder` cho **toàn bộ JSON** hoặc text/plain. Nếu server chờ `application/json` mà client gửi một chuỗi percent-encoded, payload sẽ không còn là JSON hợp lệ.

## 8. Gửi request thực tế: `HttpClient` dùng publisher như thế nào?

Bài tập trên không cần mạng để test charset. Khi thực sự gửi đến endpoint đã xác thực, trình tự thường là:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

// Đặt trong phương thức khai báo throws Exception.
HttpClient client = HttpClient.newHttpClient();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.com/messages"))
        .timeout(Duration.ofSeconds(15))
        .header("Content-Type", "text/plain; charset=UTF-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                "Xin chào", StandardCharsets.UTF_8))
        .build();

HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));

System.out.println(response.statusCode());
```

Đây là **đoạn minh họa** yêu cầu server thật, không có stdout cố định vì kết quả phụ thuộc endpoint, kết nối và API. Ở Java 11, `HttpClient.send` có thể ném `IOException` hoặc `InterruptedException`; API mạng cũng cần chính sách timeout, retry và xử lý HTTP status phù hợp.

**Không nhầm hai phía mã hóa:**

- `HttpRequest.BodyPublishers.ofString(text, charset)`: **encode** body gửi **đi**.
- `HttpResponse.BodyHandlers.ofString(charset)`: **decode** body phản hồi nhận **về**.

Charset phản hồi có thể khác charset yêu cầu. `BodyHandlers.ofString()` không tham số có chính sách chọn charset theo response `Content-Type` với UTF-8 fallback, nhưng nó **không quyết định** charset của request. Hai phía có hợp đồng dữ liệu riêng.

### Content-Type, Content-Length và các header khác

`Content-Type` mô tả **loại payload**, có thể có charset theo media type. `Content-Length` (khi dùng) mô tả **số byte của payload**. Do `ofString` tạo publisher với độ dài byte xác định, HTTP Client có thể chọn framing phù hợp.

Không hard-code `Content-Length` theo `String.length()` và không tự thêm header thuộc nhóm bị HTTP Client quản lý/hạn chế. Với Java 11 `HttpRequest.Builder`, việc cố ghi một số header như `Content-Length` có thể bị từ chối bằng `IllegalArgumentException`.

Độ dài body cũng **không** bao gồm header, phương thức HTTP, URL hay độ dài ký tự trong query. Kiểm tra bằng `publisher.contentLength()` hoặc số byte thực được encode.

## 9. Phân biệt các publisher để chọn đúng nhu cầu

| Publisher | Dữ liệu đầu vào | Ai quyết định charset? | Khi phù hợp |
| --- | --- | --- | --- |
| `ofString(text)` | `String` | API dùng **UTF-8** | Text/JSON đã chuẩn bị sẵn, không cần charset khác |
| `ofString(text, charset)` | `String` | Caller truyền `Charset` | Muốn khai báo rõ encoding hoặc server yêu cầu charset cụ thể |
| `ofByteArray(bytes)` | Byte thô đã chuẩn bị | Người đã tạo `bytes` | Đã encode bằng cơ chế kiểm soát chặt; binary format |
| `ofFile(path)` | Nội dung file | Không tự chuyển mã; gửi byte từ file | Payload có sẵn dưới dạng file, tránh dựng text lớn |
| `ofInputStream(supplier)` | Dữ liệu theo stream | Không tự chuyển mã; caller phải chuẩn bị byte | Body tạo dần hoặc nguồn stream lớn |

`ofFile` và `ofInputStream` không có nhiệm vụ "đọc file text rồi tự encode UTF-8". Nếu file hoặc stream chứa byte sai charset với `Content-Type` đã công bố, phía nhận vẫn sẽ lỗi. Với `ofInputStream`, supplier nên cung cấp stream phù hợp mỗi lần HTTP Client cần subscribe/retry.

`ofString` rất tiện với body **vừa hoặc nhỏ**. Với body rất lớn, việc giữ toàn bộ text và byte đã encode trong bộ nhớ có thể kém hiệu quả. Xem xét nguồn byte streaming, JSON streaming generator hoặc file tạm được quản lý an toàn tùy trường hợp. Không chọn publisher streaming chỉ vì "HTTP có thể gửi theo chunk": đó là tầng framing khác với việc dữ liệu nguồn đã tồn tại trong RAM hay chưa.

## 10. Bẫy dễ gặp trong ứng dụng thực tế

### Bẫy A: Nghĩ `ofString(s)` dùng default charset của máy

Sai. Tài liệu Java 11 quy định rõ `ofString(String)` dùng **UTF-8**. Nếu server cần một charset khác, phải dùng overload có `Charset` và công bố hợp đồng tương ứng. Không dựa vào khác biệt Windows/Linux làm lời giải thích khi overload này đã định nghĩa charset cụ thể.

### Bẫy B: Khai báo `Content-Type` khác với cách encode

Ví dụ header `charset=ISO-8859-1` nhưng publisher tạo UTF-8. Nếu dữ liệu chỉ có ASCII, bug dễ bị che giấu. Khi xuất hiện tiếng Việt hoặc Unicode, lỗi lộ ra. Nên test cả ký tự có dấu và ký tự ngoài ASCII.

### Bẫy C: Nhầm độ dài ký tự với byte

`text.length()` hoặc `text.codePointCount(...)` không phải độ dài body. Với text Unicode, `contentLength()` có thể lớn hơn số ký tự. Giao việc tính HTTP framing cho HTTP Client.

### Bẫy D: Dùng charset không biểu diễn hết dữ liệu

Mã hóa với Latin-1 hoặc US-ASCII có thể mất ký tự. Nếu protocol cho phép, dùng UTF-8. Nếu bị ràng buộc charset khác, validate/encode strict và báo lỗi khi gặp ký tự ngoài miền biểu diễn.

### Bẫy E: Tưởng `ofString` tự tạo JSON hoặc form

`ofString` chỉ mã hóa **chuỗi đã cung cấp**. Nó không serialize POJO, không percent-encode form field, không xác nhận JSON đúng schema. Tạo body đúng định dạng trước rồi mới publish.

### Bẫy F: Nhầm `Content-Type` của request và response

Header của request do client đặt cho body gửi đi. Response là dữ liệu do server tạo; dùng `BodyHandlers.ofString(charset)` phù hợp với encoding phản hồi. Charset ở hai chiều có thể khác nhau.

### Bẫy G: Nhầm build request với gửi request

`HttpRequest.newBuilder(...).POST(...).build()` chỉ tạo request immutable. Phải gọi `HttpClient.send` hoặc `sendAsync` để giao tiếp mạng. Bài test publisher không chứng minh remote server đã nhận request.

### Bẫy H: Tự thiết lập `Content-Length` sai hoặc dùng encode nhiều lần

Độ dài của publisher là độ dài **byte đã encode**. Nếu đã percent-encode các trường form, chỉ encode thành byte **một lần**. Không dùng `URLEncoder.encode` trên toàn bộ string đã encode rồi lại coi nó là raw body.

### Bẫy I: Không kiểm tra định dạng Unicode đầu vào

Java `String` có thể chứa chuỗi UTF-16 không hợp lệ (ví dụ surrogate đứng một mình). Các đường chuyển mã tiện lợi có thể thay thế ký tự lỗi; khi tính toàn vẹn quan trọng cần xác thực đầu vào hoặc dùng `CharsetEncoder` cấu hình `REPORT`.

## 11. Checklist cho một POST body dạng text

1. Xác định **media type** endpoint cần: `text/plain`, `application/json`, `application/x-www-form-urlencoded` hay kiểu khác.
2. Chuẩn bị **nội dung logic** đúng cú pháp của media type trước. Với JSON, dùng serializer; với form, encode từng field theo quy tắc form.
3. Chọn **Charset** theo contract — thông thường `StandardCharsets.UTF_8`.
4. Tạo publisher bằng `BodyPublishers.ofString(body, UTF_8)`, hoặc `ofString(body)` khi cố ý dùng default UTF-8.
5. Đặt header `Content-Type` phù hợp định dạng và charset theo quy tắc media type.
6. Không tính `Content-Length` bằng ký tự; tin vào byte length của publisher và HTTP Client.
7. Với dữ liệu cần bảo toàn tuyệt đối, kiểm tra Unicode và xử lý charset không hỗ trợ thay vì chấp nhận replacement âm thầm.
8. Biên dịch và test với tiếng Việt, dấu, ký tự ngoài ASCII và chuỗi rỗng.
9. Phân biệt việc tạo `HttpRequest` với việc gửi `HttpClient.send/sendAsync`; xử lý timeout, response status, retry và bảo mật riêng.
10. Đối chiếu log/test ở mức **byte và Content-Type**, tránh chỉ nhìn chuỗi đã được IDE hiển thị.

## 12. Câu hỏi luyện tập (kèm đáp án)

**1.** `BodyPublishers.ofString("Xin chào")` dùng charset nào nếu không truyền đối số thứ hai?

**Đáp án:** UTF-8 theo hợp đồng Java 11. Không phụ thuộc charset mặc định của OS.

**2.** Sự khác biệt giữa `ofString(s)` và `ofString(s, StandardCharsets.UTF_8)` là gì?

**Đáp án:** Với cùng `s`, hai overload sinh cùng body byte UTF-8. Overload hai tham số ghi rõ charset và cho phép chọn charset khác khi protocol yêu cầu.

**3.** Khi `text.length() == 10` và `publisher.contentLength() == 13`, có phải publisher tạo sai không?

**Đáp án:** Không. `String.length()` đếm đơn vị UTF-16, `contentLength()` đếm byte sau encoding; các ký tự Unicode có thể cần nhiều byte trong UTF-8.

**4.** Gọi `ofString(text, UTF_16BE)` rồi gắn header `text/plain; charset=UTF-8` có lỗi biên dịch không?

**Đáp án:** Không. Nhưng header và byte body không thống nhất, server có thể giải mã sai. Java builder không tự điều chỉnh charset.

**5.** `ofString` có tự thêm `Content-Type: text/plain; charset=UTF-8` không?

**Đáp án:** Không. Caller đặt header khi cần; media type phải đến từ hợp đồng API.

**6.** Có nên gọi `URLEncoder.encode(json, UTF_8)` trước khi `ofString(json, UTF_8)` để gửi JSON không?

**Đáp án:** Không. URLEncoder dành cho form encoding, không phải JSON serialization. Tạo JSON hợp lệ bằng serializer rồi mã hóa UTF-8 với `ofString`.

**7.** Khi gửi request với `application/x-www-form-urlencoded`, vì sao có thể cần cả `URLEncoder` và `BodyPublishers.ofString`?

**Đáp án:** `URLEncoder` bảo vệ cấu trúc các field `key=value&...`, còn `ofString` chuyển **chuỗi form đã định dạng đúng** thành byte gửi qua HTTP.

**8.** Có thể dùng `BodyHandlers.ofString(StandardCharsets.UTF_8)` để quyết định charset của request body không?

**Đáp án:** Không. `BodyHandlers` xử lý body của **response**. `BodyPublishers` tạo body của **request**.

**9.** Nếu chuỗi chứa `☕` và charset `ISO_8859_1` không biểu diễn được, có bảo đảm roundtrip chính xác không?

**Đáp án:** Không. Có thể xảy ra thay thế/mất thông tin. Dùng UTF-8 nếu protocol cho phép, hoặc encoder strict và báo lỗi.

**10.** `HttpRequest.newBuilder(uri).POST(publisher).build()` đã gửi byte lên server chưa?

**Đáp án:** Chưa. Nó mới xây request; cần `HttpClient.send` hoặc `sendAsync`.

## Tài liệu chính thức

- [Oracle Java SE 11 — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html): `ofString(String)` mặc định UTF-8 và `ofString(String, Charset)`.
- [Oracle Java SE 26 — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html): các overload vẫn được hỗ trợ trong JDK hiện hành.
- [Oracle Java SE 11 — HttpRequest.BodyPublisher](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html): publisher kế thừa `Flow.Publisher<ByteBuffer>`, `contentLength()` là số byte.
- [Oracle Java SE 11 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): `POST`, `header`, `build` và các header hạn chế.
- [Oracle Java SE 11 — StandardCharsets](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset được hỗ trợ chuẩn.
- [Oracle Java SE 11 — CharsetEncoder](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/charset/CharsetEncoder.html): kiểm soát encoding và xử lý ký tự không thể biểu diễn.
- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259.html): quy tắc UTF-8 cho JSON trao đổi giữa các hệ thống.

**Ghi nhớ:** `BodyPublishers.ofString` giải quyết bước **String → bytes**. Overload một đối số dùng UTF-8, overload hai đối số dùng charset được chỉ định. Header `Content-Type` cần phản ánh đúng format/charset thực tế; `contentLength()` đo byte, không đo ký tự. Việc sinh JSON, form-encode, gọi mạng và giải mã response là những trách nhiệm riêng.