# Mã hóa biểu mẫu, JSON và multipart: ranh giới giữa HTTP API với bộ mã hóa dữ liệu

## 1. Bài toán: cùng POST một dữ liệu, tại sao server có thể hiểu thành ba kiểu khác nhau?

Một ứng dụng Java muốn gửi tên người dùng, ghi chú và tệp đính kèm tới HTTP server. Nếu dùng `HttpClient`, nó có thể gửi yêu cầu `POST` bằng các loại body khác nhau:

- `application/x-www-form-urlencoded`: các **trường tên–giá trị** được mã hóa thành chuỗi byte, thường có dạng `name=Lan+Anh&note=a%2Bb`.
- `application/json`: dữ liệu được **tuần tự hóa theo cú pháp JSON**, chẳng hạn `{"name":"Lan Anh","active":true}`.
- `multipart/form-data`: một **MIME multipart body** với các phần (part) được phân cách bằng boundary; mỗi part có header riêng, có thể chứa trường text hoặc **byte tệp nhị phân**.

Cả ba đều có thể dùng **cùng HTTP method POST, cùng URL, cùng phiên bản HTTP, cùng TCP/TLS**, nhưng **cấu trúc byte của request body và quy trình giải mã ở phía server khác nhau**. Nếu client gửi JSON mà đặt header `Content-Type: application/x-www-form-urlencoded`, server có thể chọn sai parser và báo lỗi; nó không tự “nhìn ra” JSON chỉ vì nội dung có dấu ngoặc nhọn.

**Nguyên tắc chính:**

> HTTP API quản lý method, URI, headers, status và việc truyền nội dung. **Bộ mã hóa/serializer** quyết định chuyển đối tượng/trường/tệp thành những byte nào; **bộ giải mã/parser** phía server phải giải thích các byte đó theo media type và contract phù hợp.

Trong Java 17, `HttpClient` và `HttpRequest.BodyPublishers` **không tự động biến một POJO thành JSON hoặc một Map thành multipart** chỉ vì bạn chọn `POST`. Lập trình viên hoặc thư viện chuyên biệt phải tạo đúng representation, gắn header chính xác, kiểm thử khả năng giải mã và bảo vệ giới hạn tài nguyên.

Bài học tập trung vào **ranh giới giữa HTTP API và bộ mã hóa dữ liệu**, không đánh đồng encoding với transport, URL, content compression hay TLS.

## 2. Tách bốn trách nhiệm: dữ liệu → byte → HTTP → nghiệp vụ

Một request đi qua các ranh giới sau:

```text
Dữ liệu trong ứng dụng Java
  Map<String,String>, DTO, String, File/byte[]
         |
         | (1) Serializer / content encoder
         v
Dãy byte của biểu diễn
  form percent-encoding / JSON UTF-8 / multipart MIME
         |
         | (2) HttpRequest.BodyPublisher + Content-Type
         v
HTTP message
  method + URI + request headers + request body
         |
         | (3) HttpClient + HTTP framing + TCP/TLS, tùy kết nối
         v
HTTP server
         |
         | (4) Kiểm tra Content-Type, size, parser, validation
         v
Thực thể/command Java phía server → xử lý nghiệp vụ
```

Một số ranh giới quan trọng:

1. **`Content-Type` mô tả media type của request content.** Nó không tự thực hiện serialization. Đặt `Content-Type: application/json` trên một body chưa phải JSON là sai.
2. **`BodyPublisher` cung cấp byte cho HTTP client.** `BodyPublishers.ofString(x, UTF_8)` mã hóa chuỗi x thành UTF-8, **không tự escape field JSON, không tự percent-encode form và không tự tạo boundary multipart**.
3. **`Content-Length` hoặc HTTP transfer framing** mô tả cách truyền số byte; không quyết định cú pháp form/JSON/multipart. Chuyển từ HTTP/1.1 sang HTTP/2 không biến JSON thành form.
4. **Response status/body** là chuyện khác: server có thể trả JSON response dù request gửi multipart; request `Content-Type` và response `Content-Type` là hai header ở **hai chiều khác nhau**.
5. **Nghiệp vụ** nằm sau parser: body giải mã đúng chưa có nghĩa user có quyền upload, dữ liệu hợp lệ hay thanh toán đã thành công.

### `Content-Type` và `Accept` không thể tráo cho nhau

- `Content-Type: application/json` trên **request** nói: “Tôi đang gửi JSON”.
- `Accept: application/json` trên **request** nói: “Tôi muốn nhận response thuộc media type được chấp nhận này, nếu server có thể cung cấp”.
- `Content-Type: application/json` trên **response** nói: “Body phản hồi là JSON”.

`Accept` không phải nút bật JSON serializer của `HttpClient`. Nếu API bắt buộc gửi/nhận JSON, cả request body và các header tương ứng đều phải được xử lý theo hợp đồng.

## 3. So sánh ba kiểu content phổ biến

| Tiêu chí | URL-encoded form | JSON | Multipart form-data |
|---|---|---|---|
| Header media type | `application/x-www-form-urlencoded` | `application/json` | `multipart/form-data; boundary=...` |
| Cấu trúc body | `key=value&key2=value2`, percent-encoding | Đối tượng, mảng, chuỗi, số, boolean, null theo JSON | Nhiều part, boundary + header từng part + nội dung |
| Dữ liệu thích hợp | Form text đơn giản, fields ngắn | API cấu trúc lồng nhau, DTO | Kết hợp fields và upload tệp |
| Cách mã hóa text | Quy tắc form URL encoding, thường dùng UTF-8 | JSON serialization, UTF-8 cho trao đổi qua mạng | Text theo quy ước charset của part/form; binary giữ nguyên byte |
| Binary file | Không thuận tiện: phải biểu diễn dưới dạng text/encoding thêm | Cần chuyển sang chuỗi như base64 theo contract | **Hỗ trợ tệp dưới dạng raw bytes trong part** |
| Parser phía server | Form decoder | JSON parser | MIME multipart parser |
| Dấu phân tách | `&`, `=` và `%HH` | Các token JSON/escape | `--boundary` và CRLF theo MIME |
| Java 17 sẵn có | `URLEncoder`/`URLDecoder` + BodyPublisher | BodyPublisher nhận String/bytes; **không có JSON object mapper chuẩn tích hợp trong HttpClient** | Có thể tự tạo bytes/stream; **không có helper high-level multipart form builder tích hợp trong HttpClient** |
| Lỗi hay gặp | Encode sai toàn chuỗi, nhầm `+` và `%2B` | Ghép JSON thủ công, sai escape/types | Sai boundary, hỏng CRLF, chuyển binary thành text |
| Bảo vệ tài nguyên | Giới hạn field count/size | Giới hạn nesting/depth/size | Giới hạn số part, file size, tổng size, tên tệp |

**Không chọn media type dựa trên HTTP method.** `POST`/`PUT` có thể mang JSON, form hoặc multipart tùy endpoint; `GET` thường không có request content được định nghĩa theo semantics chung. Quan trọng là **server và client đồng ý cùng một hợp đồng media type và schema**.

## 4. `application/x-www-form-urlencoded`: cặp trường được mã hóa

### 4.1. Cấu trúc

Giả sử form có:

```text
name = Cà phê
note = a+b&c=d
```

Khi dùng UTF-8 và form encoding, body trở thành:

```text
name=C%C3%A0+ph%C3%AA&note=a%2Bb%26c%3Dd
```

Giải thích:

- Dấu `=` **phân cách tên trường và giá trị đã mã hóa**.
- Dấu `&` **phân cách các cặp trường**.
- Dấu cách **trong giá trị** được biểu diễn bằng `+` theo quy tắc `application/x-www-form-urlencoded`.
- Dấu cộng **thực sự là dữ liệu** phải mã hóa thành `%2B`; nếu để trần, decoder sẽ hiểu nó là dấu cách.
- Dấu `&` nằm trong giá trị phải mã hóa thành `%26`; dấu `=` trong giá trị thành `%3D`.
- Ký tự Unicode như `à` được chuyển thành byte UTF-8 rồi thành các `%HH`; ví dụ `à` UTF-8 là `C3 A0` nên biểu diễn `%C3%A0`.

Đây là **quy tắc form encoding**, không đơn giản là “URL encode toàn bộ URL”. Phân biệt với cú pháp URI: form decoding coi `+` là space, còn trong URL path, dấu cộng literal không mặc nhiên là space.

### 4.2. Java 17: encode từng key/value

```java
// Đoạn minh họa bên trong một phương thức.
String encoded = "name="
        + URLEncoder.encode("Cà phê", StandardCharsets.UTF_8)
        + "&note="
        + URLEncoder.encode("a+b&c=d", StandardCharsets.UTF_8);

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/form"))
        .header("Content-Type",
                "application/x-www-form-urlencoded; charset=UTF-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                encoded, StandardCharsets.UTF_8))
        .build();
```

Lưu ý `URLEncoder.encode` thuộc `java.net.URLEncoder`, không phải `HttpClient`. Nó mã hóa **giá trị trường** theo quy tắc form, không cung cấp URL builder chung cho path/query/fragment.

**Sai:**

```java
// Mã cố ý sai: encode nguyên body sau khi đã ghép dấu & và =.
String wholeForm = "name=Cà phê&note=a+b";
String wrong = URLEncoder.encode(
        wholeForm, StandardCharsets.UTF_8);
// Dấu = và & phân cách trường cũng bị encode -> mất cấu trúc form.
```

**Đúng:** encode **từng tên trường và từng giá trị**, rồi ghép các cặp bằng `=` và `&`. Với nhiều giá trị cùng tên (ví dụ checkbox `tag=A&tag=B`), server phải biết contract về **repeated keys**; đừng chuyển ngẫu nhiên thành một Map chỉ giữ giá trị cuối.

### 4.3. `URLDecoder` chỉ dùng cho dữ liệu form-encoded

Ở phía nhận, form parser thường:

1. Xác định charset và nhận byte body trong giới hạn.
2. Phân tách đúng các cặp và key/value, xử lý percent-escape theo chuẩn.
3. Decode `+` thành space, `%HH` thành byte.
4. Giải mã byte bằng charset được thỏa thuận (thường UTF-8).
5. Áp validation kiểu dữ liệu, required fields, kích thước, duplicate policy.

Không gọi `URLDecoder.decode` lên mọi URL/path/raw JSON tùy tiện: việc biến `+` thành space sẽ làm sai URI hoặc dữ liệu không phải form. Decode hai lần còn có thể dẫn tới bypass filter; tránh double-encoding/double-decoding giữa reverse proxy và application.

### 4.4. Khi nào form phù hợp?

- Form field text đơn giản từ HTML hoặc client legacy.
- Endpoint OAuth/token hoặc API có contract rõ `application/x-www-form-urlencoded`.
- Payload nhỏ và phẳng, không có binary file.

Form không phải cấu trúc nested JSON. Nếu cần mảng, object sâu hoặc sự phân biệt số/boolean/null, dùng contract riêng hoặc JSON thường dễ rõ ràng hơn. Một field form luôn được truyền về cơ bản dưới dạng text; server phải validate/conversion, không mặc định `"42"` là integer an toàn.

## 5. `application/json`: serialization có cú pháp và kiểu dữ liệu riêng

### 5.1. JSON biểu diễn dữ liệu có cấu trúc

Body JSON mẫu:

```json
{
  "name": "Cà phê",
  "active": true,
  "quantity": 2,
  "tags": ["drink", "local"],
  "address": null
}
```

Khác form:

- Chuỗi phải được đặt trong dấu ngoặc kép và các ký tự đặc biệt được **escape đúng cú pháp JSON**.
- `true`, `false`, `null`, số và mảng/object có ngữ nghĩa riêng. `"42"` khác số `42`.
- JSON có thể lồng nhiều cấp; parser nên giới hạn tổng kích thước, nesting depth và complexity.
- Property names và schema/validation do API quyết định. Không phải mọi object JSON đều hợp lệ chỉ vì parser chấp nhận cú pháp.

### 5.2. BodyPublisher.ofString không phải JSON serializer

```java
// Mã minh họa: JSON literal đã hợp lệ, không phụ thuộc biến ngoài.
String json = "{\"name\":\"Cà phê\",\"active\":true}";

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/api/items"))
        .header("Content-Type", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(
                json, StandardCharsets.UTF_8))
        .build();
```

Đoạn trên gửi bytes của chuỗi JSON có sẵn. **`BodyPublishers.ofString` không kiểm tra JSON hợp lệ, không tự escape một DTO, không biết JSON schema**. Nếu `json` là `"hello"` với dấu ngoặc kép đúng, nó vẫn gửi chuỗi bytes đó; còn một Java string `hello` chưa có JSON quoting sẽ không phải JSON string hợp lệ.

### 5.3. Không ghép JSON từ dữ liệu không tin cậy

**Sai:**

```java
// Mã cố ý sai: input bên ngoài có thể chứa dấu " và ký tự điều khiển.
String json = "{\"name\":\"" + userInput + "\"}";
```

Nếu `userInput` là `Alice "QA"`, JSON ghép thủ công có thể bị sai cú pháp. Nếu input có ký tự escape, control characters hoặc cấu trúc không mong muốn, bug còn nghiêm trọng hơn.

**Đúng trong ứng dụng thực:** dùng serializer như Jackson/Gson/Jakarta JSON để chuyển DTO/Map thành JSON bytes; API validation và whitelist fields riêng. Ví dụ về ý tưởng (không phải code độc lập vì cần dependency bên ngoài):

```java
// Đoạn minh họa với Jackson khi dự án đã có thư viện.
byte[] jsonBytes = objectMapper.writeValueAsBytes(dto);
HttpRequest.BodyPublisher publisher =
        HttpRequest.BodyPublishers.ofByteArray(jsonBytes);
```

Một bộ serializer thật phải xử lý escape, Unicode, type mapping, cấu hình unknown properties, date/time, số lớn, null và các kiểu đa hình an toàn. **Không tin dữ liệu từ JSON response/request chỉ vì serializer chạy được**; schema validation, authorization và business rules vẫn cần thiết.

### 5.4. Charset của JSON

JSON trao đổi giữa các hệ thống qua Internet được chuẩn hóa sử dụng UTF-8 (RFC 8259). Media type `application/json` **không có tham số `charset` được định nghĩa trong đăng ký media type theo RFC 8259**; có những API legacy dùng `application/json; charset=UTF-8` để truyền đạt quy ước, nhưng **không nên phụ thuộc vào tham số charset để thay đổi cách giải mã JSON hiện đại**. Khi dùng Java, hãy chủ động tạo UTF-8 bytes.

Trong ví dụ chạy được bên dưới, header có `application/json; charset=UTF-8` để so sánh với form và kiểm chứng chính xác cùng client/server demo, **không phải khuyến nghị bắt buộc gắn charset cho mọi JSON request**. Trong ứng dụng mới, `Content-Type: application/json` + UTF-8 bytes là lựa chọn bình thường.

### 5.5. JSON và binary

Một JSON string không thể mang raw bytes nhị phân tùy ý mà vẫn là text JSON hợp lệ. Nếu API thực sự cần đính kèm file bằng JSON, có thể quy ước base64 string rồi decode, nhưng payload tăng kích thước và làm phức tạp memory/validation. Với upload file kèm fields, **multipart** thường phù hợp hơn. Cũng có trường hợp gửi trực tiếp raw `application/octet-stream` hoặc `image/png` cho một resource được biết trước; không phải mọi upload đều bắt buộc multipart.

## 6. `multipart/form-data`: boundary và từng MIME part

### 6.1. Tại sao multipart khác form/JSON?

Khi browser gửi form có file, body có thể gồm **nhiều part**. Mỗi part chứa:

- **Delimiter** để phân cách part theo `boundary`.
- **Part headers**, đặc biệt `Content-Disposition: form-data; name="..."`; với file thường có `filename="..."` và `Content-Type`.
- **Dòng trống CRLF**, sau đó là **nội dung part**: text đã được mã hóa hoặc bytes file.
- Cuối body có **closing delimiter** `--boundary--`.

Ví dụ mô tả (text field + file text nhỏ, không phải body nhị phân đầy đủ):

```http
POST /upload HTTP/1.1
Host: example.test
Content-Type: multipart/form-data; boundary=DemoBoundaryX9

--DemoBoundaryX9
Content-Disposition: form-data; name="label"

Cà phê
--DemoBoundaryX9
Content-Disposition: form-data; name="file"; filename="data.bin"
Content-Type: application/octet-stream

...raw binary file bytes...
--DemoBoundaryX9--
```

Trong bytes **thật**, các dòng MIME/boundary được ngăn bằng **CRLF = `\r\n`**, không phải newline `\n` bất kỳ; ví dụ trên dùng trình bày để dễ đọc. Nên nhớ header `Content-Type` của request **phải có tham số boundary khớp chính xác với delimiter body**.

### 6.2. Boundary là gì?

Với header:

```http
Content-Type: multipart/form-data; boundary=DemoBoundaryX9
```

Các delimiter trong body có tiền tố thêm hai dấu gạch:

- Bắt đầu part: `--DemoBoundaryX9\r\n`
- Kết thúc headers part: `\r\n\r\n`
- Tới part tiếp: `\r\n--DemoBoundaryX9\r\n`
- Kết thúc multipart: `\r\n--DemoBoundaryX9--\r\n`

**Không nhầm tham số `boundary=...` với dòng delimiter `--boundary`**. Giá trị header **không** tự động có hai dấu gạch prefix; delimiter thêm `--` theo định dạng multipart.

Boundary cần được tạo phù hợp cú pháp và **không xuất hiện như chuỗi delimiter ở bên trong nội dung các part**. Ở production, dùng boundary ASCII đủ khó trùng, đảm bảo mọi body part, content-type header và stream builder cùng dùng **một giá trị**. Một số thư viện tự tạo boundary; **không ghi đè Content-Type thủ công khác với boundary mà thư viện sinh ra**.

### 6.3. File được giữ dưới dạng byte

Một file binary như `00 0D 0A FF 2A` phải đi vào part **theo đúng byte**, không được chuyển `new String(fileBytes, UTF_8)` rồi `getBytes(UTF_8)` để gửi. Byte `FF` có thể không phải UTF-8 hợp lệ, sẽ bị thay đổi khi giải mã text.

Với part văn bản như `label = Cà phê`, ứng dụng có thể chủ động chọn UTF-8, và server/parser cần biết charset tương ứng. Với part file, `Content-Type: application/octet-stream` hoặc media type chính xác của file mô tả dữ liệu; nhưng server vẫn phải kiểm tra file thực thay vì tin tuyệt đối header do client gửi.

### 6.4. Content-Disposition, name, filename

Một part thường có:

```http
Content-Disposition: form-data; name="file"; filename="photo.png"
Content-Type: image/png
```

- `name` là **tên field**, để server mapping vào form API.
- `filename` là **tên do phía gửi khai báo**, không phải đường dẫn được phép ghi trực tiếp trên server.
- `Content-Type` của part mô tả **loại content trong part**, khác với `Content-Type: multipart/form-data` ở mức toàn request.

**Bảo mật tên file:** không tin `filename` từ client. Loại path separators, tên đặc biệt, NUL/control characters; tạo tên server-side và ghi vào thư mục đã phân quyền. Kiểm tra extension/MIME signature và malware theo policy; không được phép ghi file ra ngoài thư mục dự định (path traversal).

### 6.5. Text fields và file trong cùng request

Một multipart request có thể có nhiều field cùng tên, nhiều file, parts theo thứ tự, và có part không có filename. Server cần contract về việc xử lý **lặp field**, tối đa part count, empty file/empty field và giới hạn size. Tránh giả định “multipart = đúng một file”.

**Không có cơ chế checksum/đảm bảo business success tự động** chỉ vì multipart đã truyền qua HTTP. Nếu upload cần toàn vẹn, verify bytes/hash, lưu tạm, kiểm tra file, commit và phản hồi resource ID theo contract.

## 7. Ranh giới với API Java 17: BodyPublisher + Content-Type

Trong `java.net.http`, `HttpRequest.BodyPublisher` cung cấp body bytes cho request; `HttpRequest.Builder.header("Content-Type", ...)` thêm metadata. Hai thao tác này **không đồng bộ hóa format cho nhau một cách thần kỳ**.

| Dữ liệu muốn gửi | BodyPublisher thường dùng | Content-Type phù hợp |
|---|---|---|
| Form đã percent-encode UTF-8 | `BodyPublishers.ofString(form, UTF_8)` | `application/x-www-form-urlencoded`, có thể ghi rõ charset |
| JSON được serializer tạo | `ofString(json, UTF_8)` hoặc `ofByteArray(jsonBytes)` | `application/json` |
| Multipart do builder tạo thành bytes | `ofByteArray(multipartBytes)` | `multipart/form-data; boundary=...` |
| Multipart lớn có cơ chế streaming | `BodyPublishers.ofInputStream(supplier)` hoặc publisher tùy biến | `multipart/form-data; boundary=...` |
| File nhị phân nguyên khối | `BodyPublishers.ofFile(path)` | `application/octet-stream` hoặc media type của file |
| Không có request body | `BodyPublishers.noBody()` | Thường không cần header Content-Type |

**Lưu ý:** `HttpClient` JDK 17 không có factory high-level `multipartBuilder()` tiêu chuẩn. Những ví dụ dùng `MultipartEntityBuilder` thuộc Apache HttpClient hoặc thư viện khác, **không phải** `java.net.http.HttpClient` tích hợp JDK. Có thể tự lắp byte như demo, nhưng nên dùng thư viện multipart đáng tin cậy cho server/client production.

### Content-Length do đâu?

- `ofString` tạo bytes theo charset và runtime có thể biết độ dài body.
- `ofByteArray` thường biết độ dài theo số byte trong mảng.
- `ofInputStream` có thể không biết trước tổng số byte, HTTP framing tùy protocol/implementation.

Bạn **không nên tự tính Content-Length bằng `String.length()`**, vì Java String đo UTF-16 code units, trong khi HTTP content length tính theo **byte content**. Với Unicode, một ký tự có thể có nhiều byte UTF-8.

### Không tự sửa Transfer-Encoding

`Transfer-Encoding` trong HTTP/1.1 và framing trong HTTP/2 thuộc trách nhiệm HTTP client/transport. Không sửa Content-Type để “bật chunked”, không dùng URL-encoding như giải pháp cho framing. **Content-Encoding** (ví dụ gzip) là tầng coding/biến đổi content khác với MIME media type và form percent-encoding.

### Đồng bộ hay bất đồng bộ không thay đổi representation

`client.send(...)` và `client.sendAsync(...)` có thể cùng dùng một `HttpRequest`/`BodyPublisher`. Khác biệt chính ở cách **đợi phản hồi và quản lý completion**, không ở định nghĩa `application/json`/`multipart/form-data`. Sai percent-encoding hoặc boundary sẽ sai dù dùng API sync hay async.

## 8. Java 17 chạy thật: ba POST cùng HttpClient, khác BodyPublisher và Content-Type

Để kiểm chứng kiến thức **không cần Internet, DNS hay framework**, chương trình sau dựng một `com.sun.net.httpserver.HttpServer` trên loopback, gửi ba request POST tới ba path, rồi in kết quả:

1. **Form:** dùng `URLEncoder.encode` trên từng giá trị, tạo chuỗi form, gửi bằng `ofString(form, UTF_8)`.
2. **JSON:** dùng một **JSON literal hợp lệ đã cố định** cho demo, gửi UTF-8 bằng `ofString`. Production phải dùng serializer để chuyển dữ liệu động.
3. **Multipart:** dùng `ByteArrayOutputStream` tạo delimiter CRLF, hai part `label` và `file`, giữ nguyên file bytes `00 0D 0A FF 2A`, gửi bằng `ofByteArray` với Content-Type chứa **cùng boundary**.

Server demo **không phải multipart parser tổng quát**. Nó kiểm tra Content-Type và so sánh dãy bytes nhận được với một fixture sinh bằng `multipartBody()`. Cách kiểm tra nguyên vẹn này chứng minh bytes binary được giữ đúng trong transport, không thay thế việc parse MIME multipart, giới hạn size, streaming và validation thực tế.

Tạo file **`HttpEntityEncodingDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Arrays;

public class HttpEntityEncodingDemo {
    private static final String BOUNDARY = "DemoBoundaryX9";
    private static final String FORM_TYPE =
            "application/x-www-form-urlencoded; charset=UTF-8";
    private static final String JSON_TYPE =
            "application/json; charset=UTF-8";
    private static final String MULTIPART_TYPE =
            "multipart/form-data; boundary=" + BOUNDARY;
    private static final byte[] FILE_BYTES =
            {0, 13, 10, (byte) 0xff, 42};

    private static void writeAscii(
            ByteArrayOutputStream out, String value) {
        out.writeBytes(value.getBytes(StandardCharsets.US_ASCII));
    }

    private static byte[] multipartBody() {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        writeAscii(out, "--" + BOUNDARY + "\r\n");
        writeAscii(out,
                "Content-Disposition: form-data; name=\"label\"\r\n"
                + "\r\n");
        out.writeBytes("Cà phê".getBytes(StandardCharsets.UTF_8));

        writeAscii(out, "\r\n--" + BOUNDARY + "\r\n");
        writeAscii(out,
                "Content-Disposition: form-data; name=\"file\";"
                + " filename=\"data.bin\"\r\n");
        writeAscii(out,
                "Content-Type: application/octet-stream\r\n\r\n");
        out.writeBytes(FILE_BYTES);

        writeAscii(out, "\r\n--" + BOUNDARY + "--\r\n");
        return out.toByteArray();
    }

    private static void respond(
            HttpExchange exchange, int code, String message)
            throws IOException {
        byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        exchange.sendResponseHeaders(code, bytes.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
        exchange.close();
    }

    private static void handle(HttpExchange exchange)
            throws IOException {
        if (!"POST".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "Only POST");
            return;
        }

        String path = exchange.getRequestURI().getPath();
        String contentType = exchange.getRequestHeaders()
                .getFirst("Content-Type");
        byte[] received = exchange.getRequestBody().readAllBytes();

        if ("/form".equals(path) && FORM_TYPE.equals(contentType)) {
            respond(exchange, 200, "FORM "
                    + new String(received, StandardCharsets.UTF_8));
        } else if ("/json".equals(path)
                && JSON_TYPE.equals(contentType)) {
            respond(exchange, 200, "JSON "
                    + new String(received, StandardCharsets.UTF_8));
        } else if ("/multipart".equals(path)
                && MULTIPART_TYPE.equals(contentType)) {
            // Kiem tra bytes cua payload test, khong phai MIME parser.
            boolean exact = Arrays.equals(
                    received, multipartBody());
            respond(exchange, exact ? 200 : 400,
                    "MULTIPART integrity=" + exact);
        } else {
            respond(exchange, 415, "Unsupported content type");
        }
    }

    private static HttpResponse<String> post(
            HttpClient client, String base, String path,
            String contentType, HttpRequest.BodyPublisher publisher)
            throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(base + path))
                .header("Content-Type", contentType)
                .timeout(Duration.ofSeconds(3))
                .POST(publisher)
                .build();
        return client.send(request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByAddress(
                                new byte[] {127, 0, 0, 1}), 0), 0);
        server.createContext("/", HttpEntityEncodingDemo::handle);
        server.start();

        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();

            // HttpClient khong la AutoCloseable trong Java 17.
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2))
                    .build();

            String form = "name="
                    + URLEncoder.encode(
                            "Cà phê", StandardCharsets.UTF_8)
                    + "&note="
                    + URLEncoder.encode(
                            "a+b&c=d", StandardCharsets.UTF_8);
            HttpResponse<String> formResult = post(
                    client, base, "/form", FORM_TYPE,
                    HttpRequest.BodyPublishers.ofString(
                            form, StandardCharsets.UTF_8));

            // JSON nay la literal tin cay de demo, khong ghep du lieu
            // nguoi dung vao JSON bang string concatenation.
            String json = "{\"name\":\"Cà phê\",\"active\":true}";
            HttpResponse<String> jsonResult = post(
                    client, base, "/json", JSON_TYPE,
                    HttpRequest.BodyPublishers.ofString(
                            json, StandardCharsets.UTF_8));

            byte[] multipart = multipartBody();
            HttpResponse<String> multiResult = post(
                    client, base, "/multipart", MULTIPART_TYPE,
                    HttpRequest.BodyPublishers.ofByteArray(multipart));

            if (formResult.statusCode() != 200
                    || jsonResult.statusCode() != 200
                    || multiResult.statusCode() != 200) {
                throw new IllegalStateException(
                        "Unexpected HTTP response");
            }

            System.out.println(
                    "FORM status=" + formResult.statusCode());
            System.out.println("FORM data="
                    + formResult.body().substring("FORM ".length()));
            System.out.println(
                    "JSON status=" + jsonResult.statusCode());
            System.out.println("JSON data="
                    + jsonResult.body().substring("JSON ".length()));
            System.out.println(
                    "MULTIPART status=" + multiResult.statusCode());
            System.out.println(multiResult.body());
            System.out.println(
                    "Binary file bytes=" + FILE_BYTES.length);
        } finally {
            server.stop(0);
        }
    }
}
```

Biên dịch/chạy bằng **JDK 17 trở lên**, chỉ dùng các module tích hợp của JDK; `HttpServer` thuộc module `jdk.httpserver`:

```bash
javac --release 17 --add-modules jdk.httpserver -encoding UTF-8 HttpEntityEncodingDemo.java
java --add-modules jdk.httpserver HttpEntityEncodingDemo
```

**Stdout chính xác trên môi trường cho phép TCP loopback:**

```text
FORM status=200
FORM data=name=C%C3%A0+ph%C3%AA&note=a%2Bb%26c%3Dd
JSON status=200
JSON data={"name":"Cà phê","active":true}
MULTIPART status=200
MULTIPART integrity=true
Binary file bytes=5
```

### Đọc kết quả

- `FORM data` cho thấy `URLEncoder` xử lý dấu cách thành `+`, ký tự `à` thành `%C3%A0` và dấu `+&=` bên trong dữ liệu thành percent-escape.
- `JSON data` là **JSON text với nguyên cú pháp**, không phải một Java object được `HttpClient` tự serialize. Trong demo, JSON là chuỗi literal cố định, đã hợp lệ.
- `MULTIPART integrity=true` nghĩa là raw bytes của toàn bộ multipart body đến server đúng bằng bytes fixture; file bytes chứa `00`, `0D`, `0A`, `FF` và `2A` **không đi qua String decoding**.
- Cùng một `HttpClient` và cùng HTTP method `POST` đã gửi ba kiểu content khác nhau nhờ **BodyPublisher** và **Content-Type** được cấu hình tương ứng.
- Server demo gọi `readAllBytes()` chỉ vì body **nhỏ, cố định và được kiểm soát**. Không copy mô hình này sang upload công khai: production phải giới hạn request size, dùng streaming parser, kiểm soát quota/timeouts và validate từng part.
- `HttpClient` trong Java 17 không phải `AutoCloseable`; không dùng try-with-resources trên client. Server có `stop(0)` trong `finally` để cleanup.

**Điểm không được suy diễn:** `integrity=true` từ phép so sánh fixture **không chứng minh** chương trình có multipart parser tổng quát. Trình phân tích MIME thực cần tìm delimiter đúng trong luồng binary, xử lý tên field, headers, charset, nhiều file, nhiều phần, filename, lỗi và giới hạn tài nguyên.

## 9. Đầu server: chọn đúng decoder theo Content-Type

Khi server nhận HTTP request, nó phải giải quyết **hai tầng kiểm tra khác nhau**:

1. **Media type được phép hay không?** Endpoint `/upload` có thể cho phép `multipart/form-data`, còn `/api/items` chỉ cho `application/json`. Nếu kiểu body không hỗ trợ, status **`415 Unsupported Media Type`** là một lựa chọn chuẩn thường gặp.
2. **Bytes có hợp cú pháp/schema hay không?** JSON syntax sai, percent-escape không hợp lệ, multipart thiếu boundary/closing delimiter đều phải được xử lý theo lỗi input; có thể trả `400 Bad Request` hoặc status validation khác theo contract.

Đừng suy ra request được chấp nhận chỉ vì Content-Type đúng. Header có thể do kẻ tấn công tự khai báo; parser vẫn phải kiểm tra bytes và giới hạn.

### 9.1. Form parser không phải JSON parser

`Content-Type: application/x-www-form-urlencoded` thường được server framework parse thành multi-map tên–giá trị. Trường lặp `tag=one&tag=two` phải theo chính sách cụ thể; một implementation chỉ giữ giá trị cuối có thể làm mất dữ liệu. Trong client, từng giá trị được percent-encode, không viết thô dấu `&` trong dữ liệu.

### 9.2. JSON parser cần validation ngoài cú pháp

Nhận `{"role":"admin"}` có thể hoàn toàn hợp JSON nhưng trái quyền sửa role của người gọi. Server cần whitelist trường có thể ghi, kiểm tra enum, số, độ dài, chống prototype/property injection tùy ngôn ngữ/framework, và xác thực authorization. Với polymorphic deserialization, dùng cấu hình an toàn; không deserialize class tùy ý từ input.

### 9.3. Multipart parser phải xử lý binary đúng nghĩa

- Dùng thư viện biết đọc MIME multipart và streaming.
- Giới hạn tổng body, size một part, số part, tên file, header size và thời gian nhận.
- Tạo tên file server-side, dùng vùng lưu tạm hạn chế quyền, quét nội dung khi policy yêu cầu.
- Không tin Content-Type của file, không thực thi hay đưa tệp lên public URL ngay.
- Không nối file bytes thành Java String để tách boundary; nếu cần parser tự viết cho nghiên cứu, xử lý byte/stream và tiêu chuẩn MIME cẩn thận.
- Với tên field lặp và nhiều tệp, định nghĩa rõ mapping thành danh sách/collection ở tầng ứng dụng.

**Không nên** dựa vào `filename` hoặc `Content-Length` bên ngoài để cấp phát mảng không giới hạn. Request body có thể vắng Content-Length hoặc dài hơn limit ứng dụng; phải có quota trong quá trình đọc, không chỉ kiểm tra sau khi đã gom toàn bộ bytes.

## 10. Encoding, charset, Content-Type, Content-Encoding và TLS

Các thuật ngữ này có thể cùng xuất hiện trong một request nhưng là **những lớp khác nhau**:

| Thuật ngữ | Nhiệm vụ | Ví dụ |
|---|---|---|
| **Form percent-encoding** | Biểu diễn ký tự của tên/giá trị thành cú pháp `%HH`, `+` | `a+b%26c` |
| **JSON serialization** | Biến dữ liệu có cấu trúc thành JSON text chuẩn | `{"count":2}` |
| **Multipart MIME encoding** | Ghép nhiều part với boundary, headers và bytes | `--B\r\n...` |
| **Charset (UTF-8)** | Chuyển text thành bytes và ngược lại | `Cà phê` → bytes UTF-8 |
| **Content-Type** | Định danh media type của content | `application/json` |
| **Content-Encoding** | Content coding (nếu áp dụng) như gzip | `Content-Encoding: gzip` |
| **HTTP framing** | Truyền thông điệp với ranh giới byte thích hợp | Content-Length/HTTP/1.1 chunked/HTTP/2 frames |
| **TLS** | Bảo mật kênh truyền, xác thực peer theo cấu hình | HTTPS |

**Sai lầm:** “Tôi đặt Content-Type là JSON rồi HttpClient sẽ escape user input thành JSON.” Header chỉ mô tả content. Ngược lại, bạn có thể serialize JSON chính xác nhưng quên Content-Type; server middleware có thể chọn decoder khác, từ chối hoặc không parse.

**Sai lầm:** “Multipart đã chứa file nên tự mã hóa/chống đọc trộm.” Multipart là format nội dung, **không phải mã hóa bảo mật**. Muốn bảo vệ kênh truyền dùng HTTPS/TLS và kiểm soát access; muốn bảo vệ dữ liệu lưu trữ cần cơ chế khác.

**Sai lầm:** “UTF-8 là gzip.” UTF-8 chuyển ký tự thành bytes, gzip nén bytes; trình tự xử lý và headers khác nhau.

## 11. Streaming và quản lý bộ nhớ khi body lớn

`BodyPublishers.ofByteArray` và `ofString` thường biểu diễn content đã nằm trong bộ nhớ. Với file hàng trăm MiB hoặc upload nhiều tệp, tạo một `byte[]` cho toàn bộ multipart có thể gây áp lực heap lớn.

Có những phương án:

- **Streaming multipart builder**: tạo chuỗi các publisher/đọc file theo luồng, phát headers/part data/boundary theo đúng thứ tự, không gom toàn bộ bytes trước. Dùng thư viện hỗ trợ nếu có.
- **`BodyPublishers.ofFile(path)`**: phù hợp khi request body chính là file (không tự đóng gói multipart); nếu endpoint muốn multipart thì phải có thêm lớp builder.
- **`BodyPublishers.ofInputStream(supplier)`**: có thể cấp nguồn input stream, nhưng supplier, khả năng retry/replay và cleanup phải được thiết kế. Không mặc định một stream dùng một lần có thể được replay an toàn sau redirect/auth challenge.
- **Reactive/custom publisher**: dùng khi cần backpressure và lifecycle rõ, với giới hạn concurrency, outstanding writes và hủy operation.
- **Server-side streaming parser**: nhận từng chunk và enforce quota sớm, thay vì `readAllBytes()` trên input không tin cậy.

**Cẩn thận với retry:** Nếu client phải gửi lại request sau lỗi, một BodyPublisher chứa file/stream có thể không khả năng replay tự động hoặc dữ liệu có thể đã thay đổi giữa lần gửi. Thiết kế nguồn content có khả năng tạo stream mới/định danh file bất biến, hoặc không tự retry khi không có bảo đảm.

### Budget cho toàn yêu cầu

Giới hạn cần có:

- Kích thước request tổng.
- Kích thước mỗi field, mỗi file, số field/part.
- Thời gian nhận body và thời gian parse.
- CPU cho JSON nesting/number parsing và multipart boundary search.
- Không gian đĩa tạm, tổng quota theo user/tenant.
- Số upload đồng thời, concurrency và backpressure.
- Timeout nghiệp vụ, authorization và cleanup file tạm khi thất bại.

**Không có một header `Content-Type` nào tự thiết lập các giới hạn này.**

## 12. Rủi ro bảo mật trong từng format

### 12.1. Form

- Decode sai hoặc hai lần có thể gây bypass kiểm tra truy cập/lọc dữ liệu.
- Trường lặp bất ngờ có thể làm bypass policy nếu gateway và application chọn giá trị khác nhau.
- Dữ liệu form vẫn cần CSRF protection khi dùng cookie-based browser workflow; percent-encoding **không chống CSRF**.
- Không coi form là safe để đưa mật khẩu vào log chỉ vì body “nhìn như query string”.

### 12.2. JSON

- Input JSON hợp cú pháp vẫn có thể sai schema: amount âm, quyền admin, enum không được phép.
- Parser cần xử lý duplicate object names theo contract. Không giả định mọi parser cùng giữ key đầu/cuối.
- Giới hạn nesting depth, số lượng phần tử và kích thước để giảm nguy cơ DoS.
- Thư viện serializer/deserializer cần cấu hình an toàn với polymorphism và kiểu dữ liệu; không dùng arbitrary class loading từ input.

### 12.3. Multipart

- Tên file, path, extensions, MIME header và file contents đều là dữ liệu không tin cậy.
- Boundary dài/sai, hàng triệu part nhỏ, file quá lớn hoặc headers part bất thường có thể làm parser cạn tài nguyên.
- Kiểm tra hash/virus/signature khi nghiệp vụ yêu cầu; lưu tạm và commit an toàn.
- Part text/filename Unicode có thể cần quy tắc mã hóa riêng; tránh tự biến `filename` thành filesystem path trực tiếp.
- Không cho attacker chọn file server-side qua `filename=../../secret`.
- File upload hoàn tất về HTTP không đồng nghĩa file đã được scan/index/commit vào domain storage.

## 13. Chọn format theo yêu cầu và kiểm thử

| Nhu cầu thực tế | Gợi ý format | Lý do |
|---|---|---|
| Một form text đơn giản truyền cặp key–value | `application/x-www-form-urlencoded` | Dễ tương thích với form endpoints, nhưng phải encode từng field |
| API tạo object với số, boolean, mảng, nested fields | `application/json` | Cú pháp/kiểu dữ liệu rõ, dùng serializer/parser chuẩn |
| Upload file kèm description, category và nhiều fields | `multipart/form-data` | Từng part có metadata, file truyền bytes không phải JSON escape |
| Upload chỉ một file nguyên khối tại URI xác định | `application/octet-stream` hoặc media type file | Không nhất thiết cần multipart overhead |
| Client gửi payload nén | Media type thực + `Content-Encoding` phù hợp | Content coding độc lập với serialization |
| API không nhận loại body đã gửi | Trả `415` khi đúng ngữ nghĩa | Client phải điều chỉnh Content-Type/representation theo contract |

### Kiểm thử client/server ở ranh giới

1. **Golden bytes test**: với form, kiểm tra percent-encoding chính xác; với JSON, kiểm tra parser đọc đúng kiểu; với multipart, kiểm tra binary hash/byte-for-byte.
2. **Media type test**: đúng Content-Type thành công; sai media type bị từ chối có kiểm soát, không parse tùy tiện.
3. **Charset test**: Unicode `Cà phê`, emoji, ký tự có dấu, dấu cộng, ampersand, quote, backslash, control characters.
4. **Multipart boundary test**: thiếu/mismatch boundary, thiếu closing delimiter, CRLF không chuẩn, part header sai, part lặp.
5. **Limits**: file vượt quota, quá nhiều parts, JSON quá sâu, form quá nhiều field, timeout, request body cắt giữa chừng.
6. **Security**: `filename` chứa `../`, tên tuyệt đối, NUL, MIME giả, payload HTML/script, tệp độc hại.
7. **Response**: status `200/201/202/204/400/413/415/422` theo API contract; client không nhầm body lỗi với response thành công.
8. **Concurrency**: nhiều upload cùng lúc, tài nguyên tạm được cleanup, không có ghi đè file chéo tenant.
9. **Retry**: BodyPublisher có thể replay theo thiết kế hay không; lệnh có side effect có idempotency key và deadline.

Đừng chỉ so sánh `String` sau khi decode multipart binary: nó có thể làm mất byte. Dùng byte-for-byte hoặc checksum phù hợp cho payload gốc, và parser chuyên dụng cho cấu trúc MIME.

## 14. Các lỗi phổ biến: phân biệt sai tầng

| Sai lầm | Vì sao sai | Cách khắc phục |
|---|---|---|
| Đặt `Content-Type: application/json` nhưng gửi text `name=Lan` | Header không biến text thành JSON | Serialize đúng JSON, đặt header khớp |
| Cho `BodyPublishers.ofString(dto.toString())` là JSON | `toString()` không tuân JSON schema/escaping | Dùng serializer |
| Ghép JSON bằng `"{...}" + userInput` | Thiếu escaping, sai types, injection vào cấu trúc | Serialize object qua thư viện |
| URL-encode **toàn form string** | Encode mất dấu phân tách `&`/`=` | Encode từng key/value rồi ghép |
| Dùng `URLEncoder` cho toàn URL/path | `+`, `/` và ký tự reserved có semantics khác | Dùng URI builder/escape theo đúng component |
| Quên mã hóa dấu `+` trong field | Decoder hiểu `+` là space | `URLEncoder.encode("a+b", UTF_8)` tạo `a%2Bb` |
| Quên charset nhất quán | Unicode thành ký tự lỗi | UTF-8 phía encode/decode, quy định rõ contract |
| Gửi `multipart/form-data` nhưng thiếu boundary | Server không biết delimiter | Để builder tạo header/boundary khớp |
| Ghi header boundary A nhưng body boundary B | Parser thất bại/cắt part sai | Dùng một giá trị boundary cho cả hai |
| Dùng `\n` thay `\r\n` ở MIME part delimiters | Sai format multipart wire | Dùng CRLF đúng chuẩn |
| Convert file bytes sang String rồi back to bytes | Có thể hỏng binary (ví dụ 0xFF) | Ghi raw bytes vào stream/publisher |
| Tin `filename` do client cung cấp | Path traversal/ghi đè file | Sinh tên server-side, validate, sandbox |
| Tin MIME header của file là file an toàn | Client có thể giả mạo media type | Inspect/scan/content policy |
| Dùng `readAllBytes()` cho upload public không giới hạn | Memory exhaustion | Streaming + quota |
| Cho `ofFile(path)` tự đóng gói multipart | Nó phát file content, không tự thêm form fields/boundary | Dùng multipart builder |
| Tính `Content-Length` bằng `String.length()` | Ký tự Unicode UTF-8 có byte length khác | Để BodyPublisher/HTTP client tính/stream đúng |
| Tưởng `Content-Type` là gzip hoặc TLS | Nhầm ba lớp serialization/compression/transport | Phân biệt Content-Type, Content-Encoding, HTTPS |
| Nghĩ POST luôn dùng JSON | POST nhận nhiều media type theo contract | Chọn đúng endpoint/format |
| Chỉ nhìn HTTP 200 và coi upload đã được xử lý hết | Server có thể lưu tạm, scan/commit sau | Dựa vào resource/status contract |
| Retry multipart upload vô hạn khi timeout | Có thể tạo nhiều tài nguyên và tiêu tốn băng thông | Idempotency + giới hạn retry + resume policy |
| Không đóng input/file stream khi lỗi | Rò rỉ descriptor/tệp tạm | `try-with-resources`/cleanup |
| Tưởng `HttpClient` Java 17 có JSON/multipart serializer | `HttpClient` chỉ transport request/response body publisher | Dùng serializer/parser/builder phù hợp |

## 15. Bài tập và câu hỏi tự kiểm tra

**Câu 1.** Vì sao cả form, JSON và multipart đều có thể gửi bằng `POST`?

**Trả lời:** POST là HTTP method quy định ngữ nghĩa xử lý request tại resource. Cú pháp **request content** được mô tả riêng bằng Content-Type và bytes mà serializer/BodyPublisher tạo ra.

**Câu 2.** `name=Lan+Anh` trong form được decode thành gì? Muốn gửi literal `Lan+Anh` thì làm sao?

**Trả lời:** `Lan Anh`, vì `+` biểu diễn dấu cách trong form encoding. Để gửi dấu cộng literal, phải percent-encode `+` thành `%2B`.

**Câu 3.** Tại sao `URLEncoder.encode("name=A&B", UTF_8)` không thể thay bước encode từng field rồi ghép?

**Trả lời:** Nó encode luôn dấu `=`/`&` vốn là dấu phân tách của form, biến toàn bộ thành một thành phần giá trị và làm mất cấu trúc field.

**Câu 4.** `HttpRequest.BodyPublishers.ofString(json, UTF_8)` có đảm bảo json là JSON hợp lệ không?

**Trả lời:** Không. Nó chỉ biến String thành byte theo charset. Dùng JSON serializer để tạo content và parser/validator phía server để xác nhận.

**Câu 5.** Một object Java có trường `active=true` và `count=2` nên gửi JSON dưới kiểu string `"true"`, `"2"` hay boolean/number?

**Trả lời:** Nếu contract cần boolean và number, JSON phải mang `true` và `2` không có quote. Serializer phù hợp giữ đúng loại dữ liệu theo model; form encoding chủ yếu chuyển field thành text.

**Câu 6.** Header multipart ghi `boundary=abc123`. Delimiter bắt đầu một part là gì?

**Trả lời:** `--abc123\r\n`. Dấu `--` được thêm vào trước giá trị boundary trong body; closing delimiter là `--abc123--` có CRLF ở vị trí thích hợp.

**Câu 7.** Nếu file chứa byte 0xFF không phải UTF-8 hợp lệ, có thể đọc file thành String rồi encode lại trước khi gửi multipart không?

**Trả lời:** Không. Conversion qua String có thể thay byte không hợp lệ và phá dữ liệu. Giữ file bytes nguyên vẹn trong part.

**Câu 8.** `BodyPublishers.ofFile(path)` có tự tạo multipart part header và closing boundary không?

**Trả lời:** Không. Nó cung cấp content file; cần builder riêng nếu endpoint đòi `multipart/form-data`.

**Câu 9.** Server thấy `Content-Type: application/json` nhưng payload là `name=A&b=B`. Nên làm gì?

**Trả lời:** Kiểm tra parser theo media type, trả lỗi client rõ ràng khi không hợp cú pháp/schema. Không tự suy đoán rồi deserialize tùy tiện nếu contract không cho phép.

**Câu 10.** `application/json` bắt buộc phải có `charset=UTF-8` trong header không?

**Trả lời:** Không. RFC 8259 quy định UTF-8 cho trao đổi JSON giữa các hệ thống và không định nghĩa charset parameter của media type. Tạo UTF-8 bytes, đặt `Content-Type: application/json` theo contract.

**Câu 11.** Nếu browser đã tự tạo boundary cho FormData, có nên ghi đè Content-Type thành literal `multipart/form-data` không?

**Trả lời:** Không. Ghi đè có thể làm thiếu/mismatch boundary. Để browser/thư viện tạo Content-Type khớp boundary của payload.

**Câu 12.** Phần header `Content-Disposition: form-data; name="file"; filename="../../secret"` có cho phép server ghi ra đường dẫn ấy không?

**Trả lời:** Không. Filename là dữ liệu không tin cậy, có nguy cơ path traversal; server phải dùng tên/path do mình kiểm soát và validate policy.

**Câu 13.** Tại sao `Content-Length` không nên lấy từ `json.length()`?

**Trả lời:** `String.length()` đếm UTF-16 code units, còn HTTP length tính theo byte body sau mã hóa. Unicode UTF-8 có thể chiếm nhiều byte.

**Câu 14.** Tại sao server demo trả `MULTIPART integrity=true` không chứng minh đã có multipart parser production?

**Trả lời:** Demo chỉ so sánh toàn bộ bytes nhận với fixture biết trước. Parser thực phải tách part/boundary trên dữ liệu tùy ý, xử lý binary, charset, số part, tên file và giới hạn tài nguyên.

**Câu 15.** Nếu upload endpoint trả `202 Accepted`, có nghĩa tệp đã được virus scan, lưu bền vững và publish chưa?

**Trả lời:** Không. 202 chỉ báo chấp nhận xử lý; phải theo dõi trạng thái, xác nhận tiến độ/commit theo contract.

**Câu 16.** Một client POST multipart có file stream không thể đọc lại; HTTP request bị timeout. Có nên retry ngay vô điều kiện không?

**Trả lời:** Không. Stream có thể không replay được, server có thể đã nhận một phần/toàn bộ file và tạo tài nguyên. Cần request ID/idempotency, retry budget, khả năng mở stream mới hoặc giao thức upload có resume phù hợp.

## 16. Checklist thực hành: hợp đồng media type và encoder/parser

Trước khi gửi một request body trong Java 17:

1. **Chốt contract**: endpoint nhận form, JSON, multipart hay raw bytes? Có bắt buộc media type và charset không?
2. **Tách lớp serialization**: form encode từng key/value bằng UTF-8; JSON dùng serializer; multipart builder tạo boundary/parts và giữ file raw bytes.
3. **BodyPublisher phải phát đúng byte**: `ofString` dùng charset rõ, `ofByteArray` dùng binary không sửa, streaming nguồn lớn có lifecycle.
4. **Content-Type phải khớp representation**: form vs JSON vs multipart có boundary; đừng gắn header tùy ý không tương ứng payload.
5. **Không tự gán Content-Length dựa trên String.length**; để HTTP client/BodyPublisher quản lý framing.
6. **Với multipart**, xác định name, filename, part Content-Type, closing delimiter, CRLF và boundary không trùng trong dữ liệu.
7. **Phía server** chỉ dùng parser hợp media type, kiểm tra cú pháp/schema, required fields, duplicate policy, type conversion và quyền truy cập.
8. **Giới hạn tài nguyên**: total bytes, số fields/parts, file size, timeout, CPU, disk quota và concurrency.
9. **Không tin filename/MIME từ client**, chống path traversal, kiểm tra file, lưu tạm và commit có kiểm soát.
10. **Kiểm thử Unicode, +, &, =, quotes, null bytes và binary** bằng golden bytes/hash, không chỉ nhìn JSON/text.
11. **Xem status, headers và error body** sau `send`; `400/413/415` thường là phản hồi HTTP hợp lệ, không tự động thành IOException.
12. **Không nhầm truyền thành công với nghiệp vụ thành công**: validation/scan/commit/đối soát phải có trạng thái rõ.
13. **Retry có chính sách**: body streaming có replay không, operation có idempotency không, deadline tổng và cleanup ở đâu.

**Ghi nhớ cuối:** `HttpClient`/HTTP API chuyên tạo và vận chuyển **request/response**; `URLEncoder`, JSON serializer và multipart builder chuyên tạo **biểu diễn dữ liệu thành byte**. Header `Content-Type` mô tả để server chọn parser; nó không tự biến đổi payload. Form dùng percent-encoding, JSON dùng JSON serialization, multipart dùng boundary/part headers và raw file bytes. Tách đúng các trách nhiệm này sẽ tránh lỗi ký tự, sai content type, mất file nhị phân, parser mismatch và lỗ hổng upload.

### Nguồn tham khảo

- [RFC 9110 — HTTP Semantics, request content và Content-Type](https://www.rfc-editor.org/rfc/rfc9110)
- [HTML Living Standard — form URL encoding](https://html.spec.whatwg.org/multipage/form-control-infrastructure.html#application/x-www-form-urlencoded-encoding-algorithm)
- [RFC 8259 — JSON Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259)
- [RFC 7578 — multipart/form-data](https://www.rfc-editor.org/rfc/rfc7578)
- [RFC 2046 — MIME multipart media types và boundary](https://www.rfc-editor.org/rfc/rfc2046)
- [Java SE 17 — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html)
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 17 — URLEncoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLEncoder.html)
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)