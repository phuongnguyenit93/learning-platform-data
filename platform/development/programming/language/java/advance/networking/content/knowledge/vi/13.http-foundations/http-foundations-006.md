# HTTP/1.1: tái sử dụng kết nối và ranh giới nội dung

## Mục tiêu

Trong HTTP/1.1, client thường không đóng TCP connection ngay sau mỗi response. Một kết nối có thể mang **nhiều cặp request–response liên tiếp**. Việc này tiết kiệm chi phí thiết lập TCP/TLS, nhưng chỉ an toàn khi hai bên xác định chính xác **mỗi HTTP message kết thúc tại byte nào**. Nếu server đọc sót request body, các byte còn lại có thể bị hiểu nhầm là request tiếp theo. Nếu client đọc thừa response body, những byte của response kế tiếp có thể bị nuốt vào message trước.

Bài học giải thích quan hệ giữa **persistent connection (keep-alive)** và **HTTP message framing**, các quy tắc ưu tiên của `Content-Length`, `Transfer-Encoding: chunked`, status/method không có body và phản hồi kết thúc bằng đóng connection. Bạn sẽ biết vì sao HTTP/1.1 mặc định cho phép reuse nhưng **không đồng nghĩa mọi connection luôn được tái sử dụng**, cách phát hiện lỗi parser và cách dùng Java 17+ thay vì tự triển khai HTTP parser cho ứng dụng thật.

Sau bài này, bạn có thể:

1. Phân biệt **TCP connection**, **HTTP message**, **header section**, **message body** và **representation/content**.
2. Giải thích `Connection: close`, keep-alive mặc định trong HTTP/1.1, nguyên tắc đọc hết message trước khi gửi/nhận message kế tiếp.
3. Tính đúng ranh giới body theo **quy tắc ưu tiên của RFC 9112 `6.3**, bao gồm trường hợp không có body.
4. Đọc đúng `Content-Length` theo **số byte (octets)**, giải mã `chunked` cho đến zero-sized chunk và trailer terminator.
5. Nhận diện close-delimited response và lý do nó thường **không thể tiếp tục dùng cùng connection**.
6. Hiểu pipelining, HTTP/1.1 response ordering, khác biệt với HTTP/2 multiplexing và giới hạn retry.
7. Chạy ba chương trình Java 17+: hai request/response trên **một TCP connection**, đọc hai response liền nhau theo chunk framing, và kiểm tra những response có HTTP message body dài bằng zero theo ngữ nghĩa protocol.

## 1. Hai vòng đời khác nhau: kết nối và thông điệp

TCP cung cấp một **byte stream có thứ tự**, không cung cấp ranh giới HTTP message. Một lần `Socket.getOutputStream().write(...)` có thể bị chia thành nhiều lần `InputStream.read(...)`, hoặc nhiều lần ghi có thể được đọc gộp. Cách HTTP/1.1 định dạng message là cơ chế **tầng ứng dụng**, không phụ thuộc vào số segment TCP hay số lần đọc Java.

Một kết nối HTTP/1.1 persistent thường có dạng:

```text
          Một TCP connection duy nhất, mở trong nhiều message
Client                                                       Server
  │   REQUEST #1: start-line + headers + [body]                │
  ├───────────────────────────────────────────────────────────►│
  │   RESPONSE #1: status-line + headers + [body]               │
  │◄───────────────────────────────────────────────────────────┤
  │                                                             │
  │   REQUEST #2: start-line + headers + [body]                │
  ├───────────────────────────────────────────────────────────►│
  │   RESPONSE #2: status-line + headers + [body]               │
  │◄───────────────────────────────────────────────────────────┤
  │                                                             │
  │   Connection: close / server idle timeout / ...              │
  └──────────────────────── đóng TCP ───────────────────────────┘
```

**Một TCP connection khác với một HTTP request**: connection là kênh vận chuyển; request/response là các message theo cú pháp HTTP. Kết thúc request không tự đồng nghĩa đóng TCP. Kết thúc response cũng vậy.

**Tái sử dụng kết nối** là sử dụng connection đã mở cho nhiều request/response, còn **connection pool** của HTTP client là cơ chế ứng dụng quản lý nhiều connection để tái sử dụng khi phù hợp. Có thể một request dùng connection đang rảnh trong pool, nhưng cũng có thể client phải tạo connection mới vì origin khác, connection cũ đã đóng, chính sách timeout, lỗi truyền thông hoặc giới hạn pooling.

### HTTP/1.1 không giống HTTP/2

HTTP/1.1 đặt nhiều message trên một byte stream nhưng không có stream ID/multiplexing như HTTP/2. HTTP/1.1 **pipelining** về mặt giao thức cho phép client gửi nhiều request trước khi nhận hết response, nhưng server phải trả các response cuối theo **đúng thứ tự** request nhận được. Nó gây vấn đề head-of-line blocking ở tầng ứng dụng và không phổ biến trong nhiều client hiện đại.

**Không coi HTTP/1.1 keep-alive là pipelining**: keep-alive chỉ yêu cầu connection có thể mang nhiều request tuần tự; code thực hành của bài gửi request #2 **sau khi đã đọc hết response #1**. Đây là cách đơn giản để quan sát ranh giới và an toàn với demo.

## 2. Cú pháp HTTP/1.1: phần header và body

Về khái niệm, request:

```http
POST /echo HTTP/1.1
Host: example.test
Content-Type: text/plain; charset=utf-8
Content-Length: 5

hello
```

Response:

```http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=utf-8
Content-Length: 5

HELLO
```

**Trong byte thực tế**, các dòng HTTP/1.1 được phân cách bằng `\r\n` (CRLF), và có một **dòng trống CRLF** kết thúc header section. Các code fence hiển thị trên chỉ để dễ đọc; khi gửi bằng raw TCP, phải bảo đảm đúng cú pháp CRLF và encoding. `Content-Length: 5` nghĩa là có đúng **5 octets của message body** sau dòng trống, không phải “đọc cho đến khi thấy dòng trống tiếp theo”.

Cấu trúc thực:

```text
Request:
  request-line CRLF
  *(header-field CRLF)
  CRLF
  [message-body xác định bằng quy tắc framing]

Response:
  status-line CRLF
  *(header-field CRLF)
  CRLF
  [message-body xác định bằng quy tắc framing]
```

HTTP header field names **không phân biệt chữ hoa/chữ thường**. Trong code demo bên dưới, parser chuyển header name về lowercase để so sánh. Không tự coi một dòng trắng **bên trong body** là dấu kết thúc body: body có thể chứa byte bất kỳ, từ JSON, ảnh nhị phân, dữ liệu nén đến ký tự CRLF.

### Content, message body và transfer coding

- **HTTP message body**: các octets trên wire sau header section, nếu có; được đóng khung theo quy tắc HTTP/1.1.
- **Content**: thông tin do request/response mang theo theo HTTP semantics; có thể khác message body nếu có transfer coding.
- **Content-Encoding** như `gzip`: thuộc cách mã hóa content/representation; không phải quy tắc xác định điểm kết thúc HTTP message trên connection.
- **Transfer-Encoding** như `chunked`: cơ chế mã hóa truyền tải, trong đó chunked có **chỉ dấu kết thúc rõ ràng**.
- **Connection**: điều khiển các tùy chọn theo từng connection; không biến byte stream thành message frames.

Có thể response là `200 OK` mà không có content ứng dụng (ví dụ `Content-Length: 0`), hoặc response theo method/status **không được có HTTP message body**. Không suy luận “mọi response status 200 đều có body dài hơn zero”.

## 3. Persistent connection và `Connection: close`

RFC 9112 quy định **HTTP/1.1 mặc định là persistent** nếu không có chỉ thị hoặc điều kiện khiến connection phải đóng. Về ý tưởng:

```http
GET /resource HTTP/1.1
Host: example.test
```

Không cần thêm `Connection: keep-alive` để bật tính persistent trong HTTP/1.1. Header `Connection: keep-alive` thường thấy vì tương thích/đặc tính triển khai, nhưng **không phải điều kiện bắt buộc** cho persistent HTTP/1.1.

Nếu muốn báo không tái sử dụng connection sau response hiện tại:

```http
GET /resource HTTP/1.1
Host: example.test
Connection: close
```

hoặc phía server trả:

```http
HTTP/1.1 200 OK
Connection: close
Content-Length: 2

OK
```

Khi nhận tùy chọn `close`, kết nối không còn được xem là persistent sau response tương ứng. Client **không tiếp tục gửi các request mới trên connection đó**. Server có thể có chính sách đóng connection nhàn rỗi ngay cả khi không có `Connection: close`; không client nào được coi connection có thể tồn tại vô thời hạn.

### 3.1. HTTP/1.1 và HTTP/1.0 khác nhau

| Đặc điểm | HTTP/1.1 | HTTP/1.0 |
|---|---|---|
| Persistence mặc định | Có, trừ chỉ thị/điều kiện đóng | Không mặc định |
| Muốn dừng reuse | `Connection: close` | Đóng là hành vi mặc định khi không có thương lượng |
| `Connection: keep-alive` | Không cần để bật mặc định | Có cơ chế keep-alive cũ, phụ thuộc hai phía |
| Body framing phù hợp reuse | Length-delimited hoặc transfer-delimited | Hạn chế hơn; close-delimited phổ biến lịch sử |
| Proxy compatibility | Cần tuân thủ HTTP/1.1 và hop-by-hop fields | Không được giữ persistent connection với HTTP/1.0 client theo RFC 9112 `9.3 |

`Connection: close` là **HTTP protocol option**, không phải lệnh Java `Socket.close()` xảy ra ngay lúc parser đọc header. Phần message hiện tại vẫn cần được truyền/đọc theo quy tắc. Một response có `Content-Length` hoàn chỉnh, `Connection: close` và sau đó TCP FIN là hợp lệ.

### 3.2. Điều kiện thật sự để reuse an toàn

Hai bên phải **biết chính xác cuối của message trước**. RFC 9112 `9.3 yêu cầu:

- **Server** phải đọc hết request body hoặc đóng connection sau khi gửi response; không được đọc sót bytes của request #1 rồi giải thích các bytes ấy thành request #2.
- **Client** muốn reuse cùng connection phải đọc hết response body của response #1 (hoặc xử lý theo hợp đồng client library để giải phóng connection an toàn).
- Mỗi message trên connection persistent phải có **self-defined length** — không trông chờ đóng connection để xác định cuối body.

Đây là mối liên hệ quan trọng nhất của bài: **keep-alive chỉ khả thi khi framing không lệ thuộc EOF**.

## 4. Bảng quyết định độ dài body theo RFC 9112 `6.3

HTTP/1.1 có quy tắc **ưu tiên**; không thể đơn giản viết “có `Content-Length` thì cứ đọc đúng bấy nhiêu” cho mọi response. Phải xét **method của request tương ứng, status response, Transfer-Encoding và Content-Length**.

| Thứ tự xem xét | Điều kiện | Ranh giới message body | Kết luận cho reuse |
|---|---|---|---|
| 1 | Response cho `HEAD`, hoặc status `1xx`, `204`, `304` | Kết thúc ngay sau dòng trống cuối header; **không có message body** | Có thể tiếp tục parse message phù hợp tiếp theo trên connection |
| 2 | `2xx` response cho `CONNECT` | Sau header chuyển connection thành **tunnel**, không còn HTTP message framing thường | Không parse tunnel bytes như HTTP response kế tiếp |
| 3 | Có cả `Transfer-Encoding` và `Content-Length` | TE **ưu tiên** theo RFC, nhưng đây là framing đáng ngờ/không nên chấp nhận | Nên xử lý như lỗi; với request dạng này RFC yêu cầu server đóng sau response |
| 4 | Có `Transfer-Encoding` với **final coding = chunked** | Đọc và decode chunks tới last-chunk, trailers và dòng trống | Có điểm kết thúc xác định, có thể reuse nếu các điều kiện khác cho phép |
| 5 | Có `Transfer-Encoding` nhưng **final coding không phải chunked** | Response: đọc tới khi server đóng; request: không xác định đáng tin, server phải trả `400` và đóng | Response không reuse; request phải từ chối/đóng |
| 6 | Không TE, có `Content-Length` hợp lệ | Đúng **n octets** theo trường độ dài | Có thể reuse khi đọc đủ |
| 7 | Request không thuộc nhánh trên, không TE/CL | Độ dài body **bằng zero** | Có thể parse request kế tiếp |
| 8 | Response còn lại không có framing định độ dài | Body kết thúc bằng **đóng connection** | Không reuse connection ấy cho message kế tiếp |

Đây là thứ tự áp dụng đúng nghĩa **framing**, không phải bảng “mọi status có content hay không” giản lược. Phần sau giải thích từng nhánh, các trường hợp đặc biệt và lý do bảo mật.

### Quy tắc cần nhớ ngay

- Với **request** không có `Content-Length`/`Transfer-Encoding`, **không đợi EOF** để xác định request body: body dài 0.
- Với **response** thông thường không có CL/TE và được phép có body, phải đọc tới khi peer đóng; không còn cơ hội reuse.
- Với **HEAD/1xx/204/304 response**, không được đọc body dù thấy một số header liên quan tới content length. Chúng là ngoại lệ có ưu tiên cao hơn.
- Với **2xx CONNECT**, sau header là tunnel bytes, không được giải thích bằng HTTP parser như một chuỗi response thông thường.
- **TE + CL cùng tồn tại là tín hiệu nguy hiểm**. Không xây hệ thống sản xuất với hai parser có cách hiểu khác nhau.

## 5. `Content-Length`: số byte chính xác, không phải độ dài String

`Content-Length: n` thông báo kích thước **message body tính bằng octets**, không phải số code point hoặc UTF-16 code unit của Java.

Ví dụ:

```java
String text = "Chào";
byte[] bytes = text.getBytes(
        java.nio.charset.StandardCharsets.UTF_8);
System.out.println("Java String length: " + text.length());
System.out.println("UTF-8 byte count: " + bytes.length);
```

Đây là **đoạn mã minh họa**, chưa có class `main` độc lập. Với `Chào`, số UTF-16 code unit và số byte UTF-8 khác nhau. Nếu thiết kế HTTP response raw, phải dùng `bytes.length` cho `Content-Length`, không dùng `text.length()`.

### 5.1. Đọc body đúng n bytes

Nếu headers đã cho `Content-Length: 5` thì parser phải:

```text
... CRLF
Content-Length: 5 CRLF
CRLF
HELLO
[next HTTP message bytes nếu connection còn persistent]
```

Với body dài 5, phải đọc **đúng 5 bytes**. Nếu lần `read` đầu chỉ nhận 2, lần sau nhận 3, hai lần ghép lại tạo đủ body. Không được coi `read` trả ít hơn buffer length là hết body. Khi đọc đủ 5 bytes, byte tiếp theo **không** thuộc body này nữa.

Java 17 có `InputStream.readNBytes(int)`, trả tối đa `n` bytes, có thể trả ít hơn nếu EOF. Phải so kết quả:

```java
// Trích đoạn minh họa: 'in' là InputStream, 'length' đã được
// validate trong giới hạn an toàn của ứng dụng.
byte[] body = in.readNBytes(length);
if (body.length != length) {
    throw new java.io.EOFException("Incomplete HTTP body");
}
```

Đây là **đoạn minh họa**, không phải parser HTTP/1.1 đầy đủ; chưa có xử lý TE, no-body status, headers xung đột và kích thước lớn. Với body lớn, nên đọc theo buffer nhỏ/streaming thay vì cấp phát mảng tùy ý theo độ dài do peer cung cấp.

### 5.2. Không đọc quá n bytes

Trên một connection persistent, ngay sau 5 bytes có thể là `HTTP/1.1 ...` của response tiếp theo (trong pipeline) hoặc khi server bắt đầu gửi message khác. Nếu parser đọc dư rồi bỏ phần thừa, nó có thể làm **mất đồng bộ protocol**.

Nếu dùng `BufferedInputStream`, buffer có thể đọc trước (prefetch) nhiều bytes từ TCP, **nhưng phải giữ nguyên chúng trong cùng parser/input wrapper**. Prefetch không sai khi trạng thái buffer được bảo toàn; sai ở chỗ đọc headers bằng một `BufferedReader` rồi đột nhiên đọc body trực tiếp từ `Socket.getInputStream()`: reader có thể đã giữ bytes body/next message trong buffer riêng.

### 5.3. Body rỗng không cần EOF

Một response có `Content-Length: 0` kết thúc ngay sau headers. Nếu client gọi `readAllBytes()` trên raw socket để “đọc cho hết response” thì nó lại đợi **EOF của connection**; server vẫn giữ connection mở để reuse, khiến chương trình có thể block vô hạn. Quy tắc đúng là đọc đúng `0` bytes trong trường hợp đó.

### 5.4. Độ dài không hợp lệ

Một giá trị `Content-Length` không phải số thập phân hợp lệ, quá lớn, âm, hoặc có các dòng CL mâu thuẫn là **lỗi framing**, không nên cố “đoán” rồi tiếp tục reuse. HTTP specs có một số tình huống danh sách giá trị CL lặp **đồng nhất** được phép chuẩn hóa, nhưng parser demo trong bài **chủ động từ chối duplicate** để tránh mơ hồ. Khi làm sản phẩm thật, hãy để thư viện HTTP đáng tin xử lý các trường hợp chuẩn và lỗi chéo giữa proxy/server; không tự viết parser raw cho dữ liệu không tin cậy.

## 6. `Transfer-Encoding: chunked` và last-chunk

Khi chưa biết trước kích thước body hoặc muốn streaming, sender HTTP/1.1 có thể dùng transfer coding `chunked`, trong đó từng chunk gồm:

```text
<chunk-size dưới dạng hex>[;extensions] CRLF
<chính xác chunk-size bytes> CRLF
...
0[;extensions] CRLF
[trailer-field CRLF]*
CRLF
```

**Kết thúc message body không phải lúc nhìn thấy một dòng `0` bất kỳ trong payload**; parser phải ở đúng trạng thái đọc **chunk-size line**, giải mã số hex 0, rồi tiếp tục đọc **trailer section tới dòng trống**. Chỉ khi đó mới xác định vị trí byte đầu tiên của message HTTP tiếp theo.

Ví dụ response chunked hợp lệ:

```http
HTTP/1.1 200 OK
Transfer-Encoding: chunked

4
Wiki
5
pedia
0
X-Demo: yes

```

Đây là bản trình bày **theo dòng**. Trên wire là chuỗi `\r\n`, kích thước `4` và `5` tính bằng byte. Sau khi giải mã, content là `Wikipedia`. `X-Demo: yes` ở đoạn sau last-chunk là một trailer minh họa, không thuộc 9 bytes content.

### 6.1. `chunked` không phải `Content-Length`

Không phát `Content-Length` đồng thời với `Transfer-Encoding`. RFC quy định người gửi không được làm vậy; nguy cơ parser phía proxy/server hiểu ranh giới khác nhau có thể dẫn đến **HTTP request smuggling** hoặc response splitting.

Khi `Transfer-Encoding` tồn tại và **chunked là coding cuối**, ranh giới message là zero-size chunk/trailer terminator, không phải EOF. Nếu một header như `Transfer-Encoding: gzip, chunked` xuất hiện, việc tách chunked vẫn dựa trên coding cuối, rồi mới giải mã những transfer coding trước theo thứ tự thích hợp. Demo chunk parser ở phần thực hành chỉ chấp nhận đúng `Transfer-Encoding: chunked` và từ chối những coding khác.

### 6.2. Không nhầm `Content-Encoding: gzip`

`Content-Encoding: gzip` nghĩa content được mã hóa nén. Có thể vẫn dùng `Content-Length` để định khung số bytes **đã nén trên wire**, hoặc dùng transfer-encoding chunked cho cách truyền. Không suy luận “body hết khi gzip decoder ngừng” thay cho HTTP framing. Parser phải xử lý đúng message length trước; thư viện có thể cung cấp stream giải mã sau đó.

### 6.3. Trailer không phải request mới

HTTP chunk trailers nằm **sau zero-sized chunk** và trước dòng trống cuối. Tránh kết thúc parser ngay khi thấy `0\r\n` mà không đọc hết trailers. Nếu không, byte trailer còn lại có thể bị nhìn nhầm thành HTTP message mới trên persistent connection.

Một số trường trong trailers có ràng buộc riêng; ứng dụng không được mặc định dùng trailers chưa xác thực để ghi đè các trường quyết định routing, body framing hoặc security. Mục tiêu ở đây là **xác định đúng ranh giới**.

## 7. Những response không có HTTP message body

Đây là trường hợp sinh nhiều bug dù `Content-Length` hoặc `Transfer-Encoding` có vẻ hiện diện. RFC 9112 đặt ưu tiên **method/status** lên trước framing headers:

| Response | Có HTTP message body không? | Điểm kết thúc response |
|---|---|---|
| Phản hồi cho `HEAD` | Không | Ngay sau dòng trống kết thúc headers |
| Bất kỳ `1xx` response (ví dụ `100 Continue`) | Không | Ngay sau headers; còn có thể có final response tiếp theo |
| `204 No Content` | Không | Ngay sau headers |
| `304 Not Modified` | Không | Ngay sau headers |
| `2xx` cho `CONNECT` | Không phải body HTTP thường; chuyển thành tunnel | Ngay sau headers, bytes tiếp theo thuộc tunnel |
| `200 OK` cho `GET` | Có thể có body hoặc body 0 | Dùng CL/TE/close theo quy tắc tương ứng |

**HEAD với Content-Length:** server có thể cung cấp `Content-Length` biểu thị kích thước representation mà một yêu cầu GET tương ứng sẽ trả, nhưng **không được gửi message body** trong chính response HEAD. Nếu client thấy `Content-Length: 1048576` sau HEAD rồi cố đọc 1.048.576 bytes trên persistent connection, nó có thể block hoặc nuốt message khác.

**`304 Not Modified`:** cũng có thể kèm một số metadata về representation, nhưng body response vẫn vắng mặt. `204` tương tự có zero message body theo quy tắc HTTP. `1xx` không phải final response, nên client còn phải tiếp tục đọc response kết thúc tương ứng trong request lifecycle.

**`CONNECT 2xx`:** một proxy đồng ý tạo tunnel (thường dùng cho TLS qua HTTP proxy). Bytes sau header của response thành công trở thành **traffic của tunnel**, không phải response HTTP/1.1 thứ hai. `Connection: Upgrade`/`101 Switching Protocols` cũng làm thay đổi giao thức sau headers theo contract tương ứng, cần parser riêng; không tiếp tục coi bytes đã upgrade là HTTP/1.1 thông thường.

### Không đọc “đến khi server đóng” cho mọi status

Nếu connection đang persistent và client gọi `readAllBytes()` sau response `204`, nó có thể chờ vô hạn; server chưa đóng vì mong dùng connection cho request khác. Đúng ra `204` kết thúc ngay sau headers.

Nếu parser áp dụng `Content-Length` **trước** status/method, có thể coi response no-body là message có body và mất đồng bộ. Với các trạng thái đặc biệt, **thứ tự quy tắc framing** là yêu cầu cốt lõi.

## 8. Response kết thúc bằng đóng connection

Nếu một response được phép có body **không có `Transfer-Encoding` và không có `Content-Length`**, ranh giới body thường được xác định bằng **EOF khi server đóng connection**.

```http
HTTP/1.1 200 OK
Content-Type: text/plain
Connection: close

This body ends only when the peer closes its output.
```

Đây là ví dụ response close-delimited; **không** có dấu kết thúc thông điệp khác trong headers. Nếu TCP connection không đóng, client không thể chắc đã đọc hết body. Vì vậy reuse trên **chính connection đó** là không thể: EOF vừa xác định hết response thì connection không còn được dùng để gửi request tiếp theo.

Điểm yếu khác: nếu network connection bị ngắt đột ngột, rất khó phân biệt **body đã thực sự hoàn chỉnh** với **body bị cắt giữa chừng** khi framing chỉ dựa vào đóng connection. RFC 9112 khuyến nghị sender dùng length-delimited/chunked khi có thể.

**Request không có kiểu close-delimited.** Nếu request không khai báo CL/TE theo các quy tắc, body dài **0**, không phải “đợi client đóng output”. Một server `readAllBytes()` cho mọi HTTP request sẽ dễ bị deadlock: client giữ connection để nhận response trong khi server lại chờ EOF.

### Ví dụ deadlock

```text
Client: POST /demo + Content-Length: 5 + "hello"
        -> chờ response, giữ connection persistent

Server sai: đọc toàn bộ Socket InputStream đến EOF
            -> chờ client đóng connection

Cả hai đứng đợi nhau dù đủ 5 bytes đã đến.
```

Cách sửa: server parse header, đọc **chính xác 5 bytes** rồi tạo response. Không “đợi thêm chút”, tăng buffer size hay thêm `Thread.sleep()` để giải quyết lỗi protocol framing.

## 9. Java 17+: hai request/response trên **một TCP connection**

Ví dụ độc lập sau sử dụng `java.net.ServerSocket` và `Socket` trên loopback để **nhìn thấy trực tiếp bytes HTTP/1.1**. Server chỉ gọi `accept()` **một lần**, sau đó parse hai request tuần tự trên cùng socket:

1. Client gửi `POST /echo` với `Content-Length: 5` và body `hello`.
2. Server trả `HELLO` với `Content-Length: 5` và `Connection: keep-alive`.
3. Client **đọc đúng 5 bytes response** rồi gửi `GET /status` (không có `Content-Length`, body request dài 0).
4. Server trả `OK` với `Content-Length: 2` và `Connection: close`, rồi đóng accepted socket.
5. Client đọc đúng 2 bytes và quan sát EOF.

**Đây là parser demo giới hạn**, chỉ hỗ trợ start-line, headers ASCII, `Content-Length` đơn, body tối đa 1.024 bytes và **từ chối Transfer-Encoding**. Không dùng nguyên code này làm HTTP server công khai; HTTP parser production còn nhiều quy tắc cú pháp, giới hạn/timeout/security mà ví dụ không xử lý.

**Tệp `Http11KeepAliveDemo.java`:**

```java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;

public class Http11KeepAliveDemo {
    private record Message(String firstLine, byte[] body) {}

    private static String readLine(InputStream in) throws IOException {
        ByteArrayOutputStream data = new ByteArrayOutputStream();
        while (true) {
            int b = in.read();
            if (b == -1) throw new EOFException("Unexpected EOF in header");
            if (b == '\r') {
                if (in.read() != '\n') throw new IOException("Expected CRLF");
                return data.toString(StandardCharsets.US_ASCII);
            }
            if (b == '\n' || data.size() >= 8192)
                throw new IOException("Invalid or oversized header line");
            data.write(b);
        }
    }

    private static Message readMessage(InputStream in) throws IOException {
        String first = readLine(in);
        int length = 0;
        boolean foundLength = false;
        for (int i = 0; i < 32; i++) {
            String header = readLine(in);
            if (header.isEmpty()) {
                byte[] body = in.readNBytes(length);
                if (body.length != length) throw new EOFException("Short body");
                return new Message(first, body);
            }
            int colon = header.indexOf(':');
            if (colon <= 0) throw new IOException("Bad header");
            String name = header.substring(0, colon).toLowerCase(Locale.ROOT);
            String value = header.substring(colon + 1).trim();
            if (name.equals("transfer-encoding"))
                throw new IOException("Chunked not supported by this demo");
            if (name.equals("content-length")) {
                if (foundLength || !value.matches("[0-9]+"))
                    throw new IOException("Ambiguous Content-Length");
                try { length = Integer.parseInt(value); }
                catch (NumberFormatException e) { throw new IOException("Too large", e); }
                if (length > 1024) throw new IOException("Body exceeds demo limit");
                foundLength = true;
            }
        }
        throw new IOException("Too many headers");
    }

    private static void send(OutputStream out, String start, String extra,
                             String body) throws IOException {
        byte[] payload = body.getBytes(StandardCharsets.UTF_8);
        String head = start + "\r\n" + extra
                + "Content-Length: " + payload.length + "\r\n\r\n";
        out.write(head.getBytes(StandardCharsets.US_ASCII));
        out.write(payload);
        out.flush();
    }

    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try (ServerSocket listener = new ServerSocket()) {
            InetAddress loopback = InetAddress.getLoopbackAddress();
            listener.bind(new InetSocketAddress(loopback, 0));
            listener.setSoTimeout(4000);

            Future<List<String>> server = worker.submit(() -> {
                try (Socket peer = listener.accept()) {
                    peer.setSoTimeout(4000);
                    InputStream in = peer.getInputStream();
                    OutputStream out = peer.getOutputStream();
                    Message first = readMessage(in);
                    if (!first.firstLine().equals("POST /echo HTTP/1.1"))
                        throw new IOException("Unexpected first request");
                    String body = new String(first.body(), StandardCharsets.UTF_8);
                    send(out, "HTTP/1.1 200 OK", "Connection: keep-alive\r\n",
                            body.toUpperCase(Locale.ROOT));

                    Message second = readMessage(in);
                    if (!second.firstLine().equals("GET /status HTTP/1.1"))
                        throw new IOException("Unexpected second request");
                    send(out, "HTTP/1.1 200 OK", "Connection: close\r\n", "OK");
                    return List.of(
                            "TCP connections accepted: 1",
                            "Server first: " + first.firstLine() + " / " + body,
                            "Server second: " + second.firstLine()
                                    + " / body-bytes=" + second.body().length);
                }
            });

            try (Socket client = new Socket()) {
                client.connect(new InetSocketAddress(loopback, listener.getLocalPort()), 4000);
                client.setSoTimeout(4000);
                InputStream in = client.getInputStream();
                OutputStream out = client.getOutputStream();

                send(out, "POST /echo HTTP/1.1",
                        "Host: localhost\r\nConnection: keep-alive\r\n", "hello");
                Message first = readMessage(in);

                out.write(("GET /status HTTP/1.1\r\nHost: localhost\r\n"
                        + "Connection: close\r\n\r\n")
                        .getBytes(StandardCharsets.US_ASCII));
                out.flush();
                Message second = readMessage(in);
                int eof = in.read();

                for (String line : server.get(5, TimeUnit.SECONDS))
                    System.out.println(line);
                System.out.println("Client response1: "
                        + new String(first.body(), StandardCharsets.UTF_8));
                System.out.println("Client response2: "
                        + new String(second.body(), StandardCharsets.UTF_8));
                System.out.println("EOF after second response: " + eof);
            }
        } finally {
            worker.shutdownNow();
        }
    }
}
```

**Biên dịch và chạy với JDK 17 hoặc mới hơn:**

```bash
javac --release 17 -encoding UTF-8 Http11KeepAliveDemo.java
java Http11KeepAliveDemo
```

**Stdout đã kiểm chứng khi chạy TCP loopback:**

```text
TCP connections accepted: 1
Server first: POST /echo HTTP/1.1 / hello
Server second: GET /status HTTP/1.1 / body-bytes=0
Client response1: HELLO
Client response2: OK
EOF after second response: -1
```

**Phân tích quan trọng:**

- `listener.accept()` chỉ xảy ra **một lần**. Hai request được đọc bằng `readMessage(in)` trên cùng `peer.getInputStream()`. Đây là minh chứng rõ ràng rằng một TCP connection có thể chứa nhiều HTTP/1.1 request/response tuần tự.
- `POST` gửi body `hello` và server đọc đúng 5 bytes; body không phải tín hiệu hết request dựa vào EOF.
- Response đầu `Content-Length: 5`; client dừng đọc body sau 5 bytes rồi lập tức gửi GET thứ hai. Server vẫn chờ GET trên cùng socket, không có deadlock.
- Request GET thứ hai không có CL/TE, vì vậy `readMessage` đặt độ dài body bằng 0 theo quy tắc dành cho **request**.
- Server trả response #2 dài 2 bytes và báo `Connection: close`. Sau khi server ra khỏi `try`, TCP socket đóng; client quan sát `read()==-1`.
- Timeout 4 giây giúp thí nghiệm không treo vô hạn khi loopback bất thường. Khi môi trường không cho TCP loopback hoặc quá chậm, chương trình có thể ném exception; stdout trên là kết quả đã xác minh cho một lần chạy thành công.
- Parser đọc từng header line theo CRLF **không dùng hai wrapper có read-ahead khác nhau**. Điều đó giữ byte body/next message tại đúng stream, nhưng **không đồng nghĩa parser đủ chặt cho Internet**.
- Số lượng header, kích thước body được giới hạn để tránh cấp phát không giới hạn; ví dụ không thực hiện đầy đủ security checks, proxy routing, Host validation, chunked, informational responses, hop-by-hop headers hoặc close-delimited responses.

Bài học thực tế là **phải đọc hết message** trước khi tái sử dụng connection, không cần đóng TCP sau mỗi request.

## 10. Java 17+: giải mã chunked rồi đọc response tiếp theo

Thử nghiệm thứ hai không cần mở socket; nó dùng `ByteArrayInputStream` chứa **hai HTTP responses liên tiếp trên cùng một byte stream**. Đây là cách kiểm thử deterministic logic framing trước khi thêm yếu tố mạng.

Response #1 có `Transfer-Encoding: chunked`, hai chunks `Wiki` và `pedia`, sau đó last-chunk, trailer `X-Demo: yes` và dòng trống. Response #2 có `Content-Length: 2` với body `OK`. Parser phải dừng response #1 **đúng sau trailer terminator** và bắt đầu đọc status line của response #2 ngay sau đó.

**Tệp `Http11ChunkedBoundaryDemo.java`:**

```java
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

public class Http11ChunkedBoundaryDemo {
    private record Message(String status, byte[] body) {}

    private static String readLine(InputStream in) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        while (true) {
            int b = in.read();
            if (b == -1) throw new EOFException("Incomplete line");
            if (b == '\r') {
                if (in.read() != '\n') throw new IOException("Expected CRLF");
                return bytes.toString(StandardCharsets.US_ASCII);
            }
            if (b == '\n' || bytes.size() >= 8192)
                throw new IOException("Malformed line");
            bytes.write(b);
        }
    }

    private static byte[] exact(InputStream in, int count) throws IOException {
        byte[] bytes = in.readNBytes(count);
        if (bytes.length != count) throw new EOFException("Incomplete body");
        return bytes;
    }

    private static byte[] chunks(InputStream in) throws IOException {
        ByteArrayOutputStream decoded = new ByteArrayOutputStream();
        while (true) {
            String line = readLine(in);
            String token = line.split(";", 2)[0].trim();
            if (!token.matches("[0-9a-fA-F]+"))
                throw new IOException("Invalid chunk size");
            long size = Long.parseLong(token, 16);
            if (size > 1024 - decoded.size())
                throw new IOException("Body exceeds demo limit");
            if (size == 0) {
                for (int i = 0; i < 32; i++) {
                    String trailer = readLine(in);
                    if (trailer.isEmpty()) return decoded.toByteArray();
                    if (trailer.indexOf(':') <= 0)
                        throw new IOException("Invalid trailer field");
                }
                throw new IOException("Too many trailers");
            }
            decoded.write(exact(in, (int) size));
            if (in.read() != '\r' || in.read() != '\n')
                throw new IOException("Missing chunk terminator");
        }
    }

    private static Message readResponse(InputStream in) throws IOException {
        String status = readLine(in);
        String transfer = null;
        Integer contentLength = null;
        for (int i = 0; i < 32; i++) {
            String header = readLine(in);
            if (header.isEmpty()) {
                if (transfer != null && contentLength != null)
                    throw new IOException("Ambiguous framing");
                if (transfer != null) {
                    if (!transfer.equalsIgnoreCase("chunked"))
                        throw new IOException("Unsupported transfer coding");
                    return new Message(status, chunks(in));
                }
                if (contentLength == null)
                    throw new IOException("Length required in this demo");
                return new Message(status, exact(in, contentLength));
            }
            int colon = header.indexOf(':');
            if (colon <= 0) throw new IOException("Malformed header");
            String name = header.substring(0, colon).toLowerCase(Locale.ROOT);
            String value = header.substring(colon + 1).trim();
            if (name.equals("transfer-encoding")) {
                if (transfer != null) throw new IOException("Duplicate TE");
                transfer = value;
            }
            if (name.equals("content-length")) {
                if (contentLength != null || !value.matches("[0-9]+"))
                    throw new IOException("Bad Content-Length");
                try { contentLength = Integer.parseInt(value); }
                catch (NumberFormatException e) { throw new IOException("Too large", e); }
                if (contentLength > 1024) throw new IOException("Body too large");
            }
        }
        throw new IOException("Too many headers");
    }

    public static void main(String[] args) throws Exception {
        String stream =
                "HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
                + "4\r\nWiki\r\n5\r\npedia\r\n"
                + "0\r\nX-Demo: yes\r\n\r\n"
                + "HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK";
        try (InputStream input = new ByteArrayInputStream(
                stream.getBytes(StandardCharsets.US_ASCII))) {
            Message first = readResponse(input);
            Message second = readResponse(input);
            System.out.println("First body: "
                    + new String(first.body(), StandardCharsets.UTF_8));
            System.out.println("Second status: " + second.status());
            System.out.println("Second body: "
                    + new String(second.body(), StandardCharsets.UTF_8));
            System.out.println("Bytes remaining: " + input.available());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 Http11ChunkedBoundaryDemo.java
java Http11ChunkedBoundaryDemo
```

**Stdout đã kiểm chứng:**

```text
First body: Wikipedia
Second status: HTTP/1.1 200 OK
Second body: OK
Bytes remaining: 0
```

Giải thích:

1. `readResponse` đọc status line và header section. Trong demo, nếu cả `Transfer-Encoding` và `Content-Length` xuất hiện, parser **từ chối** thay vì cố chọn một giá trị mơ hồ. Đây là chính sách an toàn của ví dụ, dù RFC có mô tả thứ tự ưu tiên khi nhận.
2. Với `chunked`, `chunks` đọc kích thước hex, đúng số bytes data, CRLF sau chunk, rồi lặp. Khi size `0`, nó đọc **đến hết trailer section**; chỉ sau dòng trống cuối mới trả content.
3. Stream vẫn còn nguyên response #2. Parser đọc đúng `Content-Length: 2` và trả `OK`; cuối cùng `available()==0` trong **ByteArrayInputStream này**, là kiểm tra test data đã tiêu thụ hết. **Không** dùng `available()==0` trên network socket để kết luận HTTP message đã kết thúc.
4. Đây là **parser học tập**: giới hạn 1.024 bytes, tối đa 32 headers/trailers, chỉ hỗ trợ `Transfer-Encoding: chunked` duy nhất hoặc một CL, không xử lý mọi status/method/transfer coding/tình huống cú pháp. `Long.parseLong` với giá trị chunk-size cực lớn có thể báo lỗi; production cần xử lý chuẩn hóa, overflow, extension/trailer policy và validation kỹ hơn.
5. Bộ đệm content sau decode là UTF-8 string khi in; **byte count chunk** được tính trước khi chuyển thành chuỗi, không lấy số ký tự để đọc payload.

Ví dụ chứng minh **zero-sized chunk + trailer terminator**, không phải TCP EOF, xác định điểm có thể bắt đầu HTTP message tiếp theo.

## 11. Java 17+: kiểm tra ngoại lệ HEAD, 1xx, 204, 304 và CONNECT

Chương trình nhỏ sau không parse socket; nó cô lập **nhánh quyết định** xem response thuộc nhóm **không có HTTP message body** theo RFC 9112 `6.3.

**Tệp `Http11NoBodyRulesDemo.java`:**

```java
public class Http11NoBodyRulesDemo {
    static boolean hasHttpMessageBody(String requestMethod, int status) {
        if (requestMethod.equals("HEAD")) return false;
        if (status >= 100 && status < 200) return false;
        if (status == 204 || status == 304) return false;
        if (requestMethod.equals("CONNECT")
                && status >= 200 && status < 300) return false;
        return true;
    }

    public static void main(String[] args) {
        System.out.println("HEAD 200 HTTP body: "
                + hasHttpMessageBody("HEAD", 200));
        System.out.println("GET 204 HTTP body: "
                + hasHttpMessageBody("GET", 204));
        System.out.println("GET 304 HTTP body: "
                + hasHttpMessageBody("GET", 304));
        System.out.println("GET 200 HTTP body: "
                + hasHttpMessageBody("GET", 200));
        System.out.println("CONNECT 200 HTTP body: "
                + hasHttpMessageBody("CONNECT", 200));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 Http11NoBodyRulesDemo.java
java Http11NoBodyRulesDemo
```

**Stdout đã kiểm chứng:**

```text
HEAD 200 HTTP body: false
GET 204 HTTP body: false
GET 304 HTTP body: false
GET 200 HTTP body: true
CONNECT 200 HTTP body: false
```

**Giới hạn của bảng boolean này:** `true` chỉ nghĩa là **không thuộc các nhóm no-body/tunnel đặc biệt đang kiểm tra**, không nghĩa body bắt buộc có bytes. GET 200 có thể `Content-Length: 0`. Một parser đầy đủ còn phải parse status/method đã được đối chiếu với request đang chờ, hỗ trợ các nhánh TE/CL/close theo thứ tự, xử lý 101 protocol upgrade và tuân thủ yêu cầu semantic khác như `205 Reset Content` không được tạo content.

Đừng dùng hàm boolean này làm HTTP parser hoàn chỉnh; nó chỉ nhắc rằng **method/status được xét trước độ dài header**.

## 12. Dùng `java.net.http.HttpClient` của Java 17 để reuse đúng trách nhiệm

Trong ứng dụng thông thường, **không tự xây parser raw TCP** như ba ví dụ. Java 17 có `java.net.http.HttpClient` hỗ trợ HTTP/1.1 và HTTP/2, xử lý HTTP message framing, connection pooling và nhiều khía cạnh protocol.

Mẫu sử dụng:

```java
// Đoạn minh họa, cần import java.net.URI;
// java.net.http.HttpClient, HttpRequest, HttpResponse.
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_1_1)
        .connectTimeout(java.time.Duration.ofSeconds(3))
        .build();

HttpRequest first = HttpRequest.newBuilder(
        URI.create("https://example.com/status"))
        .timeout(java.time.Duration.ofSeconds(5))
        .GET()
        .build();

HttpResponse<String> firstResult =
        client.send(first, HttpResponse.BodyHandlers.ofString());

HttpResponse<String> secondResult =
        client.send(first, HttpResponse.BodyHandlers.ofString());
```

Đây là **đoạn minh họa không độc lập**: cần import như ghi chú, kiểm tra exception/trạng thái nghiệp vụ, và một endpoint thực sự phù hợp. Không chạy thử endpoint public chỉ để xác minh reuse trong bài; demo raw loopback ở phần trước là phép kiểm chứng deterministic hơn.

Ý nghĩa:

- **Tái sử dụng cùng đối tượng `HttpClient`** cho nhiều requests là cách cho phép connection pool hoạt động khi có thể. Tạo `HttpClient.newHttpClient()` mới sau từng request có thể phá cơ hội reuse.
- `.version(HTTP_1_1)` yêu cầu dùng phiên bản HTTP/1.1 cho ví dụ này; không diễn giải behavior của HTTP/2 giống HTTP/1.1.
- `BodyHandlers.ofString()` tiêu thụ body thành chuỗi và cho bạn một kết quả hoàn tất; với streaming handler như `ofInputStream()`, ứng dụng phải **đọc hết hoặc đóng stream đúng cách** để không giữ tài nguyên/connection bị kẹt.
- Client library tự xử lý `Content-Length`, `chunked` và những trường hợp no-body trong các điều kiện được hỗ trợ. Bạn **không** cần `readAllBytes()` trên raw socket cho HTTP response.
- **Không có lời hứa “hai lệnh `send` chắc chắn dùng cùng một TCP connection”.** Pool có thể mở connection mới do server đóng, idle timeout, TLS/proxy configuration, origin khác, retry hoặc policy nội bộ.
- Connection reuse và **HTTP caching** là hai khái niệm khác nhau. Một response được cache có thể tránh gửi network request, trong khi một request không cache vẫn có thể dùng TCP connection đang mở.

### Connection reuse không làm request idempotent

Nếu client gửi POST thay đổi trạng thái, bị timeout và ứng dụng thử lại, không nhận được response **không chứng minh server chưa xử lý**. Sử dụng connection mới hay cũ không giải quyết xử lý trùng. Với thao tác có side effect, phải có request ID/idempotency key và logic phù hợp ở server khi API có hợp đồng retry. Chỉ retry khi biết thao tác an toàn hoặc đã có cơ chế chống thực thi trùng.

## 13. Framing và bảo mật: tránh request smuggling, desync và DoS

HTTP/1.1 framing không chỉ là chuyện hiệu năng; nó là **ranh giới tin cậy** giữa client, reverse proxy, load balancer và backend. Khi hai parser hiểu **độ dài request khác nhau**, byte còn lại có thể bị hiểu là request mới ngoài ý định ban đầu. Đây là một dạng **HTTP request smuggling/desynchronization**.

### 13.1. Các dấu hiệu phải xử lý nhất quán

- `Content-Length` sai định dạng, âm, vượt giới hạn, quá dài hoặc số không biểu diễn được.
- Nhiều `Content-Length` có giá trị không nhất quán.
- `Transfer-Encoding` và `Content-Length` cùng xuất hiện.
- `Transfer-Encoding` có coding cuối không phải `chunked` trong request.
- Chunk size sai hex, thiếu CRLF sau chunk, last-chunk/trailer chưa kết thúc, hoặc tổng số bytes vượt giới hạn.
- Header line không kết thúc đúng CRLF, header folding/obs-fold không được xử lý theo chính sách nhất quán, request line có byte không hợp lệ.
- Body thực ngắn hơn `Content-Length` mà peer đóng hoặc timeout: message **không hoàn chỉnh**, phải đóng connection/thất bại chứ không coi là response thành công.
- Server gửi response nhưng chưa đọc hết request body, rồi vẫn reuse connection: bytes còn lại có thể thành request khác.

**Mẫu nguy hiểm về mặt thiết kế:** proxy A ưu tiên `Transfer-Encoding: chunked`, backend B lại ưu tiên `Content-Length`. Hai bên chia stream thành message ở các vị trí khác nhau; không nên gửi malformed HTTP để “thử” hệ thống ngoài phạm vi cho phép. Khi phát hiện bất nhất framing trong hệ thống mình quản lý, sửa parser/library/proxy, đồng bộ version, từ chối message mơ hồ và đóng connection thích hợp.

### 13.2. RFC quy định gì về TE + CL?

RFC 9112 mô tả TE **ưu tiên về message length** khi cùng tồn tại, đồng thời cảnh báo đây là trường hợp nên coi là lỗi. Server **có thể từ chối** request có cả hai; nếu vẫn xử lý theo TE, server **bắt buộc đóng connection sau response** để giảm khả năng desync. Intermediary chọn chuyển tiếp phải loại CL nhận được và xử lý TE theo quy tắc trước khi forward.

Quy tắc thiết kế an toàn nhất cho ứng dụng của bạn: **không chủ động gửi cả hai header** và không viết parser tự đoán cách phân giải message xung đột. Thư viện HTTP hiện đại, reverse proxy và backend phải nhất quán về normalization và giới hạn.

### 13.3. Giới hạn tài nguyên

Một parser production cần giới hạn tổng số header bytes, số lượng fields, độ dài từng field, body bytes, chunks count, trailer bytes, thời gian nhận headers và toàn request. Nếu peer gửi `Content-Length: 999999999999999999`, đừng cố cấp phát buffer theo giá trị đó. Nếu client gửi từng byte rất chậm, cần deadline chống resource exhaustion, không chỉ timeout giữa hai lần đọc riêng lẻ.

### 13.4. EOF và timeout là hai trường hợp khác nhau

- `InputStream.read() == -1`: đầu kia đã đóng chiều gửi, sau khi byte trước EOF đã được đọc hết.
- `SocketTimeoutException`: trong khoảng chờ không có đủ tiến triển để đọc; **không tự có nghĩa message đã kết thúc**.
- `IOException`/`SocketException`: lỗi I/O; message có thể bị cắt.
- Với response close-delimited, EOF có thể dùng làm ranh giới theo protocol, nhưng không loại bỏ hoàn toàn rủi ro nội dung bị mất một phần khi có lỗi kết nối.
- Với `Content-Length` hoặc `chunked`, nếu chưa đạt ranh giới hoàn chỉnh mà connection đóng, đó là **incomplete message**, không nên biến thành một response thành công.

## 14. Quan sát và debug HTTP/1.1 persistent connections

### 14.1. Không lấy số `write()`/`read()` làm số message

TCP có thể chia/gộp bytes tùy buffer và scheduling. Một response 10 KB có thể đọc thành nhiều phần; hai response pipelined có thể nằm trong cùng một buffer mạng. Quan sát đúng cần **header framing, request ID/timing và parser state**, không phải “lệnh read đầu tiên nhận được bao nhiêu”.

### 14.2. Ma trận triệu chứng

| Triệu chứng | Khả năng ưu tiên kiểm tra | Bằng chứng tiếp theo |
|---|---|---|
| Request #1 OK nhưng request #2 treo | Client/server đọc đến EOF thay vì CL/chunked; connection còn mở | Kiểm tra header và bytes đã đọc; có logic chờ EOF không? |
| Server parse request #2 thành byte cuối body #1 | Request #1 chưa được đọc hết; CL sai hoặc parser read-ahead bị mất | Ghi content length dự kiến/thực tế, bộ đệm còn lại |
| Client nhận status line hỏng ở response #2 | Response #1 chưa được consume đủ hoặc đọc thừa | So framing của response #1 với bytes đã nhận |
| Một POST bị thực thi hai lần khi mất kết nối | Retry nghiệp vụ không có idempotency | Đối chiếu request ID, commit và retry policy |
| Rất nhiều TCP connections mới | Pool không reuse, server gửi close, idle timeout hoặc origin khác | Bật client connection logs, server TCP accept count |
| HTTP/1.1 keep-alive vẫn có TCP FIN | Peer có thể đóng idle connection hoặc dùng `Connection: close` | Đối chiếu header, thời điểm và TCP trace |
| HEAD bị treo dù response headers đã về | Parser cố đọc body theo CL | Xem request method và status ưu tiên |
| Response chunked bị “dính” trailers vào message sau | Parser dừng ngay ở zero chunk, bỏ qua trailer terminator | Kiểm tra chunk-state machine và trailer parse |
| Chunked parser nhận thiếu dữ liệu | Xem chunk size hex, CRLF, partial read, timeout | So wire bytes với parser state |
| `400 Bad Request` khi reverse proxy xử lý | Header framing mơ hồ, TE cuối không chunked, CL lỗi | Xem proxy/backend validation và log lỗi, tránh suy đoán |
| Client giữ socket khi chỉ muốn đọc một response | `readAllBytes()` trên persistent socket | Dùng CL/chunk parser hoặc HttpClient |
| Đọc text bị lỗi ký tự đa byte | Decode UTF-8 từng fragment read, chia giữa code points | Ghép đúng body bytes rồi decode streaming/whole message |
| HTTP client dùng connection khác dù cùng host | Connection cũ đã đóng/không eligible, library pool policy | Log connection ID/remote port, TLS/proxy và timeout |

### 14.3. Bằng chứng tối thiểu trong log

```text
timestamp | connectionId | remoteEndpoint | requestId
          | method | path | httpVersion | status
          | transferEncoding | contentLength
          | bodyBytesConsumed | messageComplete
          | connectionCloseRequested | socketClosed
          | elapsedMs | errorClass
```

Không log body hoặc credentials nhạy cảm một cách tùy tiện. Với nhiều request trên cùng TCP connection, **connectionId** sẽ lặp trong log còn **requestId** thay đổi — dấu hiệu tích cực của reuse nếu đã xác định đúng các request.

### 14.4. Cách đọc bản tin bằng công cụ

Ví dụ kiểm tra header qua một HTTP/1.1 client đã được phép dùng:

```bash
curl --http1.1 -v https://example.com/
```

Lệnh này có thể hiện headers và thông tin kết nối, nhưng **một lần gọi curl đơn lẻ không chứng minh connection đã được reuse**. Để xác minh reuse, cần cùng một client session thực hiện nhiều requests tới cùng origin và xem connection logs/IDs; những chính sách của curl, proxy, TLS và server có thể khác nhau. Không dùng các endpoint không thuộc quyền quản lý để thử lỗi giao thức malformed.

Với Wireshark/tcpdump và HTTP không mã hóa, có thể xem request line, headers và stream byte. Với HTTPS, TLS mã hóa dữ liệu nên packet capture bình thường không hiện rõ HTTP headers/body. Muốn debug tầng HTTP phải dùng logging của client/server hoặc cơ chế capture/giải mã **được phép**.

## 15. Những tình huống cần tự trả lời

**Tình huống 1.** Client gửi `GET / HTTP/1.1` không có CL/TE và vẫn giữ TCP connection mở. Server nên chờ EOF để biết request đã kết thúc?  
**Đáp án:** Không. Request body có độ dài **0** theo RFC 9112 nếu không có framing fields và không thuộc các nhánh trước. Request kết thúc sau header section.

**Tình huống 2.** Response `HTTP/1.1 200 OK` có `Content-Length: 5`; client đọc được 2 bytes rồi chờ. Đã hết response chưa?  
**Đáp án:** Chưa. Cần đọc đủ **5 octets**; nếu socket đóng sau 2 bytes thì response incomplete.

**Tình huống 3.** Server dùng `Transfer-Encoding: chunked`, sau last-chunk `0` gửi thêm trailer `X-Demo: yes` rồi dòng trống. Được coi response kết thúc ngay khi vừa đọc dòng `0`?  
**Đáp án:** Không. Phải đọc hết trailer section, bao gồm dòng trống kết thúc. Chỉ sau đó byte kế tiếp có thể thuộc message sau.

**Tình huống 4.** Server trả response cho `HEAD` kèm `Content-Length: 1000`. Client phải đọc 1.000 bytes?  
**Đáp án:** Không. Response HEAD **không có HTTP message body**; header có thể mô tả kích thước representation tương ứng với GET.

**Tình huống 5.** Client nhận `HTTP/1.1 204 No Content` không có `Content-Length` và giữ connection. Phải đọc đến EOF?  
**Đáp án:** Không. Message body dài zero và kết thúc ngay sau headers.

**Tình huống 6.** Response GET 200 không có CL và TE. Khi nào hết body?  
**Đáp án:** Khi server đóng chiều gửi/connection theo framing close-delimited. Connection đó không thể tiếp tục reuse; rủi ro body bị cắt khó phân biệt với kết thúc bình thường.

**Tình huống 7.** Response có cả `Transfer-Encoding` và `Content-Length`. Có nên client tự chọn header dễ xử lý hơn?  
**Đáp án:** Không. RFC có thứ tự ưu tiên, nhưng đây là message đáng ngờ có nguy cơ desync; ứng dụng nên dùng parser chuẩn và xử lý lỗi/close phù hợp.

**Tình huống 8.** Client gửi hai request liên tiếp trên HTTP/1.1 TCP connection và server xử lý request thứ hai nhanh hơn. Server có được trả response cuối của #2 trước #1 trong pipelining?  
**Đáp án:** Không trong thứ tự response HTTP/1.1 pipelining: server phải duy trì thứ tự phản hồi ứng với request. HTTP/2 mới có mô hình multiplexing với stream identifiers khác.

**Tình huống 9.** `Connection: keep-alive` vắng mặt trong HTTP/1.1 response. Tức connection không thể reuse?  
**Đáp án:** Không. HTTP/1.1 mặc định persistent khi không có điều kiện đóng. Tuy nhiên vẫn còn chính sách server/client, framing và connection health.

**Tình huống 10.** Java `HttpClient` cùng instance gửi hai requests tới một origin. Chắc chắn một TCP connection?  
**Đáp án:** Không. Nó tạo điều kiện pooling/reuse, không cam kết số connection thực tế; cần instrument/observability để xác nhận.

**Tình huống 11.** Gọi `InputStream.available()==0` sau khi nhận response headers. Có phải body kết thúc?  
**Đáp án:** Không. `available` chỉ là khả năng đọc ngay, không phải HTTP framing hay EOF. Phải áp dụng phương pháp xác định body length.

**Tình huống 12.** Response #1 `Content-Length: 4` nhưng sender gửi `OK` rồi đóng socket. Client nên coi `OK` là hoàn chỉnh?  
**Đáp án:** Không. Received body chỉ 2 octets nên message incomplete và connection phải được xử lý như lỗi.

**Tình huống 13.** Client muốn gửi POST body `Chào` bằng UTF-8. Có nên lấy `String.length()` làm `Content-Length`?  
**Đáp án:** Không. Phải đo `text.getBytes(UTF_8).length`, vì `Content-Length` tính theo octets.

**Tình huống 14.** Reverse proxy giữ `Content-Length` từ client trong khi thêm `Transfer-Encoding: chunked` khi forward. Có an toàn?  
**Đáp án:** Không. HTTP/1.1 sender không được phát cả hai; intermediary phải xử lý/loại bỏ CL nhận được theo RFC khi forward message sử dụng TE, hoặc từ chối thông điệp đáng ngờ.

**Tình huống 15.** Một client đã nhận xong `Content-Length: 0` nhưng tiếp tục chờ socket đóng trước khi gửi request #2. Lỗi nào?  
**Đáp án:** Lỗi nhầm **HTTP message completion** với **TCP EOF**, làm mất lợi ích keep-alive và có thể gây deadlock nếu server vẫn chờ request tiếp theo.

## 16. Checklist ứng dụng và tóm tắt

Khi review một thành phần HTTP/1.1, kiểm tra:

- [ ] Phân biệt rõ một **TCP connection** với từng **HTTP message** trên connection đó.
- [ ] HTTP/1.1 mặc định persistent, nhưng tôn trọng `Connection: close` và idle close từ peer.
- [ ] Với response, xét **HEAD/1xx/204/304** và `2xx CONNECT` **trước** TE/CL.
- [ ] Nếu có `Transfer-Encoding` với chunked cuối, đọc đến **zero-size chunk + trailers + dòng trống**.
- [ ] Nếu có CL hợp lệ, đọc **đúng số bytes**; byte thừa thuộc message khác hoặc lỗi protocol, không trộn.
- [ ] Với request không có CL/TE, body dài **0**, không chờ EOF.
- [ ] Với response thường không có TE/CL, body **close-delimited** nên không tiếp tục reuse.
- [ ] Không chủ động gửi TE+CL hoặc chấp nhận framing mơ hồ một cách tùy tiện.
- [ ] Không lấy `read()` count, `available()`, `readAllBytes()` hoặc packet boundary làm ranh giới HTTP message.
- [ ] Server đọc hết request body trước khi reuse; client đọc hết response body trước khi reuse.
- [ ] Body UTF-8 tính byte, không tính theo `String.length()`.
- [ ] Có giới hạn header/body/trailer/chunk, timeout, chính sách lỗi và xử lý incomplete message.
- [ ] Dùng `java.net.http.HttpClient` hay thư viện HTTP production khi làm dịch vụ thật; raw socket parser chỉ phục vụ học giao thức.
- [ ] Khi debug reuse, theo dõi **connection ID** khác với **request ID** và xem logs tại cả client/server.
- [ ] Retry một request không-idempotent cần hợp đồng nghiệp vụ riêng, không dựa trên TCP keep-alive.

**Ghi nhớ cốt lõi:** HTTP/1.1 cho phép **nhiều message trên một connection** bởi vì mỗi message có **quy tắc kết thúc rõ ràng**. Không đọc đúng ranh giới thì hoặc bị treo vì đợi EOF, hoặc mất đồng bộ và gây lỗi/bảo mật nghiêm trọng. `Content-Length`, `chunked` và các trường hợp no-body là công cụ xác định **message completion**; `Connection: close` và chính sách idle là vấn đề **connection lifecycle**.

### Tài liệu chuẩn và Java 17

- [RFC 9112 — HTTP/1.1, `6 Message Body, `6.3 Message Body Length, `9.3 Persistence](https://www.rfc-editor.org/rfc/rfc9112.html)
- [RFC 9110 — HTTP Semantics, `8.6 Content-Length, status semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
- [Java 17 `Socket` — TCP streams và SO_TIMEOUT](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html)
- [Java 17 `InputStream` — `readNBytes`, `readAllBytes`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html)
- [Java 17 `HttpClient` — version/connection management](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java 17 `HttpResponse.BodyHandlers` — xử lý và tiêu thụ response body](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
