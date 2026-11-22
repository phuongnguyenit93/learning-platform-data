# Phân biệt metadata của biểu diễn với metadata của kết nối

Một API trả đúng JSON vẫn có thể hoạt động sai nếu các HTTP field mô tả sai dữ liệu hoặc bị chuyển tiếp sai qua gateway. Chẳng hạn, giữ `Content-Encoding: gzip` sau khi đã giải nén có thể làm client giải nén lần nữa; chuyển nguyên `Connection: close` từ một chặng nội bộ sang HTTP/2 lại vi phạm quy tắc giao thức.

Trong chương **Nền tảng HTTP** của module **INTEGRATION_API_REST**, bài học này giúp bạn phân biệt thông tin mô tả biểu diễn với thông tin phục vụ truyền thông điệp và quản lý từng chặng kết nối. Việc phân biệt này hỗ trợ thiết kế hợp đồng REST, xử lý nén, proxy, cache và triển khai API bằng Java/Spring hoặc công nghệ tương đương.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích tài nguyên, biểu diễn, nội dung thông điệp, framing và kết nối khác nhau thế nào.
- Nhận diện vai trò của `Content-Type`, `Content-Encoding`, `Content-Language`, `Content-Length`, `Transfer-Encoding` và `Connection`.
- Phân biệt metadata đi cùng ý nghĩa nội dung với thông tin chỉ dành cho bên nhận trực tiếp của một chặng.
- Giải thích vì sao proxy có thể đổi cách truyền mà không đổi dữ liệu ứng dụng.
- Tránh những lỗi thường gặp khi nén, chuyển tiếp header và chuyển đổi giữa HTTP/1.1, HTTP/2, HTTP/3.

## 2. Đặt thông tin vào đúng lớp

### 2.1. Tài nguyên và biểu diễn

**Tài nguyên** là đối tượng được định danh, chẳng hạn đơn hàng `/orders/42`. **Biểu diễn** là dữ liệu mô tả trạng thái của tài nguyên trong một dạng cụ thể: JSON, XML, HTML, ảnh hoặc một định dạng khác.

Cùng một tài nguyên có thể có nhiều biểu diễn: JSON hoặc HTML, tiếng Việt hoặc tiếng Anh, có nén hoặc không nén. Không nên đồng nhất tài nguyên với một chuỗi JSON cố định.

Metadata của biểu diễn giúp bên nhận biết cách diễn giải dữ liệu. Ví dụ:

~~~http
Content-Type: application/json
Content-Encoding: gzip
~~~

Hai field này cho biết nội dung biểu diễn đã được mã hóa bằng gzip và sau khi giải mã content coding thì được diễn giải theo media type JSON. RFC 9110 tách representation data khỏi representation metadata và mô tả quan hệ giữa media type với content coding. [RFC 9110, mục 8.1–8.4](https://www.rfc-editor.org/rfc/rfc9110.html#section-8).

### 2.2. Nội dung thông điệp và framing

**Nội dung thông điệp**, gọi là content trong các đặc tả HTTP hiện đại, là luồng byte được thông điệp mang theo theo ngữ nghĩa của request hoặc response.

**Framing** là cách giao thức xác định ranh giới thông điệp hoặc phần dữ liệu: đọc bao nhiêu byte, kết thúc ở đâu, frame nào thuộc stream nào. Nó giúp HTTP parser tách được các thông điệp, không giải thích ý nghĩa nghiệp vụ của JSON.

Trong HTTP/1.1, `Content-Length` hoặc transfer coding như `chunked` có thể tham gia xác định ranh giới. Trong HTTP/2 và HTTP/3, cơ chế frame và stream đảm nhiệm việc truyền nội dung.

Không phải content nào cũng là toàn bộ biểu diễn hiện tại của tài nguyên đích. Nó có thể là dữ liệu yêu cầu tạo mới, một phần nội dung, kết quả thao tác hoặc một biểu diễn lỗi. Cần đọc cả phương thức và mã trạng thái để hiểu.

### 2.3. Kết nối và từng chặng

Một client có thể không kết nối trực tiếp tới ứng dụng:

~~~mermaid
flowchart LR
    C[Client] -->|Chặng 1: HTTP/2| G[Gateway]
    G -->|Chặng 2: HTTP/1.1| S[Dịch vụ API]
~~~

Gateway là bên nhận của chặng 1 và bên gửi của chặng 2. Hai chặng có thể dùng phiên bản HTTP, vòng đời kết nối và framing khác nhau.

Thông tin “đóng kết nối sau response này” ở chặng dịch vụ–gateway không tự có nghĩa là phải đóng cả kết nối client–gateway. Đó là quyết định của một chặng, không phải thuộc tính của tài nguyên đơn hàng.

### 2.4. Không phải mọi field đều thuộc đúng một trong hai nhóm

Ngoài metadata biểu diễn và thông tin kết nối, HTTP còn có field phục vụ định tuyến, thương lượng, cache, xác thực và điều khiển request.

| Nhóm vai trò | Câu hỏi chính | Ví dụ |
|---|---|---|
| Metadata biểu diễn | Dữ liệu này được diễn giải thế nào? | `Content-Type`, `Content-Encoding`, `Content-Language` |
| Kích thước/framing | Nội dung dài bao nhiêu, thông điệp kết thúc ở đâu? | `Content-Length`, `Transfer-Encoding` trong ngữ cảnh thích hợp |
| Điều khiển một chặng kết nối | Bên nhận trực tiếp phải xử lý gì với chặng hiện tại? | `Connection`, các connection option của HTTP/1.1 |
| Thương lượng | Bên nhận mong muốn loại biểu diễn nào? | `Accept`, `Accept-Encoding`, `Accept-Language` |
| Định tuyến và ngữ cảnh request | Request hướng tới đâu, được gửi bởi ai? | `Host`, `Authorization` |
| Cache và điều kiện | Có được lưu, dùng lại hoặc cập nhật dựa trên phiên bản nào? | `Cache-Control`, `Vary`, `ETag`, `If-Match` |

Bảng phân loại theo mục đích học, không khẳng định mỗi field chỉ có một tác dụng. `Content-Length` là ví dụ quan trọng: mô tả kích thước dữ liệu liên quan tới biểu diễn và còn tham gia framing trong HTTP/1.1.

## 3. Nhận diện các field mô tả biểu diễn

### 3.1. Content-Type: loại dữ liệu đang được mô tả

~~~http
Content-Type: application/json
~~~

Field này mô tả media type của biểu diễn liên quan đến thông điệp. Nó không mô tả TCP, TLS hay cách chia chunk.

Nếu body là một đối tượng JSON thì `application/json` phù hợp với cú pháp đó, nhưng API vẫn cần schema để client hiểu field, kiểu dữ liệu và ý nghĩa nghiệp vụ. Media type không tự kiểm chứng dữ liệu tuân thủ schema.

Tham số như `charset` chỉ có ý nghĩa theo định nghĩa của media type tương ứng. Không suy ra rằng mọi media type đều xử lý tham số giống nhau.

### 3.2. Content-Encoding: phép biến đổi áp dụng lên biểu diễn

~~~http
Content-Encoding: gzip
~~~

Đây là thông tin về content coding đã áp dụng. Nếu gửi byte gzip, bên nhận cần xử lý lớp đó trước khi đưa dữ liệu cho JSON parser.

Ba điều dễ nhầm:

- Gzip trong `Content-Encoding` không biến media type JSON thành `application/gzip`.
- TLS mã hóa đường truyền không đồng nghĩa phải có `Content-Encoding`.
- Không thể giữ field này nếu dữ liệu gửi tiếp đã được giải nén mà không còn coding tương ứng.

Nếu nhiều content coding được áp dụng, thứ tự có ý nghĩa. Đừng sắp xếp danh sách như một tập giá trị không thứ tự.

### 3.3. Content-Language: ngôn ngữ hướng tới người nhận

~~~http
Content-Language: vi
~~~

Field này biểu đạt ngôn ngữ hướng tới đối tượng tiếp nhận biểu diễn. Nó không phải bảng mã ký tự. Một tài liệu tiếng Việt có thể dùng UTF-8; “tiếng Việt” và “UTF-8” trả lời hai câu hỏi khác nhau.

Với JSON chỉ chứa mã định danh và số, có thể không cần khai báo ngôn ngữ. Không gắn `Content-Language` chỉ vì server đang chạy tại Việt Nam.

### 3.4. Content-Location và các metadata liên quan

`Content-Location` liên hệ biểu diễn với một URI theo ngữ nghĩa của field đó; không đồng nhất nó với `Location` dùng trong các ngữ cảnh như tạo tài nguyên hoặc chuyển hướng.

`ETag` và `Last-Modified` là validator liên quan tới biểu diễn được chọn. Chúng hỗ trợ điều kiện và tái xác thực, không mô tả trạng thái socket.

Cần biết đủ vai trò để phân loại, nhưng khi triển khai phải đọc định nghĩa riêng của từng field. Tiền tố `Content-` hoặc việc field xuất hiện trong response không thay thế được định nghĩa ngữ nghĩa.

## 4. Đọc một response hoàn chỉnh

Giả sử tài nguyên kiểm tra `/checks/chk-42` có response sau:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 11
Cache-Control: no-store
Connection: close

{"ok":true}
~~~

Ở ví dụ này, body gồm đúng 11 byte ASCII của `{"ok":true}`, không tính một ký tự xuống dòng bổ sung sau dấu `}`.

| Thành phần | Ý nghĩa | Có mô tả nội dung JSON không? |
|---|---|---|
| `200 OK` | Kết quả xử lý theo ngữ nghĩa HTTP | Không trực tiếp mô tả định dạng |
| `Content-Type` | Body được diễn giải là JSON | Có |
| `Content-Length: 11` | Kích thước content; ở đây cũng hỗ trợ framing HTTP/1.1 | Mô tả độ dài, không phải schema |
| `Cache-Control: no-store` | Chính sách lưu trữ trong cache | Không phải điều khiển đóng/mở kết nối |
| `Connection: close` | Không tiếp tục sử dụng kết nối HTTP/1.1 này sau response | Không |
| `{"ok":true}` | Nội dung ứng dụng | Chính là dữ liệu |

Đóng kết nối không biến một response thành lỗi nghiệp vụ. Tương tự, body JSON hợp lệ không chứng minh thông điệp HTTP đã được framing đúng.

## 5. Content-Encoding và Transfer-Encoding khác nhau thế nào?

### 5.1. Một bên mô tả biểu diễn, một bên mô tả cách truyền thông điệp

| Tiêu chí | Content-Encoding | Transfer-Encoding |
|---|---|---|
| Câu hỏi | Những coding nào đã áp dụng lên biểu diễn? | Những transfer coding nào đang dùng cho thông điệp HTTP/1.1 này? |
| Ví dụ quen thuộc | `gzip` | `chunked` |
| Phạm vi cần quan tâm | Bên giải thích biểu diễn phải biết coding thực tế | Bên xử lý chặng truyền phải giải được coding của thông điệp |
| Khi proxy chỉ đổi framing | Có thể giữ nếu byte biểu diễn không đổi | Được xử lý và tạo lại theo chặng gửi tiếp |
| HTTP/2, HTTP/3 | Vẫn có thể dùng cho nội dung | Không chuyển tiếp `Transfer-Encoding: chunked` sang các phiên bản này |

Transfer coding thuộc thông điệp thay vì biểu diễn. Chunked chia nội dung thành các chunk kèm kích thước để truyền và nhận biết kết thúc. [RFC 9112 về transfer coding và chunked](https://www.rfc-editor.org/rfc/rfc9112.html#section-7).

Không suy ra vai trò chỉ từ tên thuật toán: việc một coding nén được sử dụng ở đâu phụ thuộc field và lớp giao thức đang mô tả nó.

### 5.2. Ví dụ chunked không nén JSON

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Transfer-Encoding: chunked

B
{"ok":true}
0

~~~

Đây là cách trình bày văn bản để học; đường truyền HTTP/1.1 dùng CRLF tại các vị trí cú pháp tương ứng. `B` là số hex của 11, và chunk-data có 11 byte. Dòng kích thước cùng dấu kết thúc chunk không phải một phần của JSON.

Sau khi HTTP parser giải chunked, lớp ứng dụng nhận content:

~~~json
{"ok":true}
~~~

Chunked không có nghĩa là gzip và không làm JSON tự được nén. Một JSON parser bình thường không nên nhận nguyên dòng `B` và `0` của framing.

### 5.3. Có thể vừa nén biểu diễn vừa dùng chunked

Một response HTTP/1.1 có thể có:

~~~http
Content-Type: application/json
Content-Encoding: gzip
Transfer-Encoding: chunked
~~~

Đoạn trên chỉ minh họa header, không phải message hoàn chỉnh. Luồng xử lý khái niệm:

~~~text
Phía gửi:
Dữ liệu ứng dụng
    -> serialize thành JSON
    -> mã hóa ký tự thành byte
    -> nén gzip cho biểu diễn
    -> đóng khung HTTP/1.1 bằng chunked
    -> truyền trên kết nối

Phía nhận:
Nhận byte
    -> HTTP parser giải framing/chunked
    -> thu được content đã nén
    -> giải Content-Encoding
    -> giải mã ký tự và parse JSON
    -> xử lý dữ liệu nghiệp vụ
~~~

Nếu thư viện HTTP đã tự giải nén, lớp ứng dụng không nên giải lần thứ hai. Cần kiểm tra dữ liệu và header mà lớp thư viện thực sự đưa cho mình, vì chúng có thể là dạng đã được xử lý.

### 5.4. Nén header không phải nén body

HTTP/2 dùng HPACK cho field section; HTTP/3 dùng QPACK. Những cơ chế này khác với gzip của nội dung và không được quảng bá bằng `Content-Encoding: gzip`. [RFC 9113 về nén field](https://www.rfc-editor.org/rfc/rfc9113.html#section-4.3), [RFC 9114 về QPACK](https://www.rfc-editor.org/rfc/rfc9114.html#section-4.2.1).

Có thể đồng thời có nén header, nén body và mã hóa đường truyền. Khi gỡ lỗi, phải biết mình đang quan sát lớp nào.

## 6. Content-Length là trường hợp cần đọc theo ngữ cảnh

### 6.1. Đếm byte, không đếm ký tự Java

`Content-Length` dùng đơn vị octet, thường hiểu là byte 8 bit. Đếm số ký tự của chuỗi có thể sai khi có tiếng Việt hoặc ký tự ngoài ASCII.

Ví dụ Java minh họa:

~~~java
import java.nio.charset.StandardCharsets;

String json = "{\"message\":\"Đã tạo\"}";
byte[] utf8Content = json.getBytes(StandardCharsets.UTF_8);

System.out.println(json.length());        // Đơn vị UTF-16 của String
System.out.println(utf8Content.length);   // Số byte đã mã hóa UTF-8
~~~

Đây là minh họa tính kích thước, không phải một HTTP handler hoàn chỉnh. Nếu serializer tạo ra byte khác, chẳng hạn thêm khoảng trắng hoặc escape Unicode, phải tính trên byte thật mà serializer xuất ra.

Nếu còn nén gzip sau đó, độ dài JSON UTF-8 chưa nén cũng chưa phải kích thước content đã nén.

### 6.2. Độ dài không bao gồm mọi byte trên mạng

Khi truyền content đã nén, độ dài content liên quan tới byte ở dạng đã áp dụng content coding. Không cộng kích thước header HTTP, cú pháp chunked, frame, TLS record hay IP packet vào `Content-Length`.

Ví dụ tính byte gzip bằng Java:

~~~java
ByteArrayOutputStream buffer = new ByteArrayOutputStream();
try (GZIPOutputStream gzip = new GZIPOutputStream(buffer)) {
    gzip.write(utf8Content);
}
byte[] gzipContent = buffer.toByteArray();
~~~

Đoạn mã dùng các lớp trong `java.io` và `java.util.zip`. Nếu chọn gửi chính `gzipContent` làm content cùng `Content-Encoding: gzip`, kích thước liên quan là `gzipContent.length`, trước framing. Không sao chép độ dài đó sang một đường gửi mà framework tiếp tục biến đổi dữ liệu.

Trong triển khai thông thường, hãy để tầng HTTP tính framing và kích thước từ dữ liệu cuối cùng mà nó gửi.

### 6.3. HEAD và 304 có thể có Content-Length nhưng không có body

Với `HEAD`, response không mang content như một lần `GET`; nếu có `Content-Length`, giá trị phải tương ứng với content của lần GET tương ứng. Với `304`, nếu gửi field này thì nó phải phản ánh độ dài của response `200` tương ứng, không phải số byte body đi kèm 304. `204` không được gửi `Content-Length`, kể cả giá trị 0. [RFC 9110, mục 8.6](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.6).

Ví dụ phản hồi HEAD cho cùng biểu diễn 11 byte:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 11

~~~

Không thêm 11 byte JSON sau phần header này. Nếu chỉ nhìn `Content-Length` mà bỏ qua phương thức, parser tự viết có thể chờ dữ liệu không bao giờ tới.

### 6.4. Không tự kết hợp Content-Length với Transfer-Encoding

Khi gửi message HTTP/1.1 có `Transfer-Encoding`, không gửi thêm `Content-Length`. Hai cách diễn giải ranh giới không thống nhất qua các thành phần trung gian có thể dẫn tới lỗi phân tách thông điệp. [RFC 9112, mục 6.2–6.3](https://www.rfc-editor.org/rfc/rfc9112.html#section-6.2).

Không sửa lỗi bằng cách “giữ cả hai cho chắc”. Hãy để HTTP server hoặc proxy xử lý theo quy tắc phiên bản giao thức, đồng thời chặn hoặc xử lý message không hợp lệ tại đúng tầng.

## 7. Metadata của kết nối và phạm vi hop-by-hop

### 7.1. Connection nói về chặng hiện tại

Trong HTTP/1.1:

~~~http
Connection: close
~~~

Thông tin này điều khiển việc sử dụng lại kết nối hiện tại. Nó không nói tài nguyên đã bị xóa, người dùng đã đăng xuất hay mọi kết nối trong hệ thống phải đóng.

HTTP/1.1 hỗ trợ kết nối bền vững theo mặc định theo các quy tắc của giao thức. Không bắt buộc gắn `Connection: keep-alive` vào mọi response để API hoạt động. Keep-alive của HTTP cũng khác cơ chế kiểm tra sống ở TCP và khác trạng thái phiên ứng dụng.

### 7.2. Connection có thể chỉ định field cần xử lý cục bộ

Ví dụ dành cho HTTP/1.1:

~~~http
Connection: close, X-Hop-Debug
X-Hop-Debug: upstream-socket-17
~~~

`X-Hop-Debug` là field tự đặt cho ví dụ. Tên field có trong danh sách connection option cho biết nó chỉ phục vụ chặng hiện tại. Không phải tiền tố `X-` làm field trở thành hop-by-hop.

Intermediary cần phân tích `Connection`, loại bỏ field được chỉ định cho chặng nhận và xử lý `Connection` trước khi gửi tiếp. Nó còn phải xử lý các field có ngữ nghĩa cục bộ đã biết, không chỉ dựa vào một danh sách tên cố định. [RFC 9110, mục 7.6.1](https://www.rfc-editor.org/rfc/rfc9110.html#section-7.6.1).

Chỉ xóa dòng `Connection` nhưng giữ nguyên `X-Hop-Debug` là chưa giải quyết yêu cầu của ví dụ.

### 7.3. Những field thường gặp ở ranh giới chặng

| Field | Vai trò cần nhớ |
|---|---|
| `Connection` | Connection option của HTTP/1.1 |
| `Keep-Alive` | Thông tin liên quan giữ kết nối trong các cơ chế tương ứng, không phải thời hạn dữ liệu |
| `Transfer-Encoding` | Transfer coding của message HTTP/1.1 |
| `TE` | Khả năng tiếp nhận transfer coding/trailer theo phiên bản và quy tắc tương ứng |
| `Upgrade` | Cơ chế chuyển giao thức trên kết nối trong ngữ cảnh được hỗ trợ |
| `Proxy-Connection` | Field không chuẩn xuất hiện ở một số triển khai cũ; không dùng làm hợp đồng API |

Đây không phải chỉ dẫn để controller tự sinh đủ các field trên. Đặc biệt, HTTP/2 và HTTP/3 không cho phép mang nguyên bộ field điều khiển kết nối của HTTP/1.1 sang.

### 7.4. End-to-end không đồng nghĩa byte header bất biến

Một field không phải hop-by-hop vẫn có thể được thêm, thay đổi hoặc bỏ theo ngữ nghĩa và vai trò hợp lệ của intermediary. Ví dụ, nếu gateway biến đổi nội dung thì các metadata mô tả nội dung phải được điều chỉnh tương ứng.

Không dùng hai quy tắc cực đoan “copy mọi header” hoặc “xóa mọi header server không hiểu”. Hạ tầng cần áp dụng định nghĩa field, phiên bản HTTP và chính sách tin cậy.

## 8. Theo dõi response qua gateway

### 8.1. Dịch vụ gửi HTTP/1.1

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 11
Connection: close, X-Hop-Debug
X-Hop-Debug: upstream-socket-17

{"ok":true}
~~~

Gateway nhận đủ content, kết thúc chặng upstream theo quy tắc kết nối. Giả sử nó không biến đổi nội dung và phía client đang dùng HTTP/2.

### 8.2. Gateway dựng response HTTP/2

Dạng hiển thị đã giải mã field có thể là:

~~~text
:status: 200
content-type: application/json
content-length: 11
~~~

Content `{"ok":true}` được mang trong DATA frame của stream tương ứng. Đây là bản hiển thị để học, không phải một response HTTP/2 có status line dạng văn bản.

Gateway không mang `Connection`, `X-Hop-Debug` từ ví dụ sang chặng HTTP/2. Nó có thể giữ `Content-Type` và độ dài vì content không đổi. Đóng kết nối upstream không bắt buộc đóng kết nối HTTP/2 với client.

### 8.3. Nếu gateway giải nén hoặc sửa nội dung

Giả sử dịch vụ gửi gzip nhưng gateway quyết định giải nén trước khi trả client. Khi đó phải xem lại:

- `Content-Encoding`: có còn coding nào thực sự áp dụng không?
- `Content-Length`: giá trị cũ còn đúng với content mới không?
- Validator: có còn đại diện đúng cho biểu diễn mới, đặc biệt nếu dùng strong ETag?
- Các metadata phụ thuộc nội dung và chính sách biến đổi/cache: có còn phù hợp không?

Một gateway không được tự ý biến đổi mọi response. Cần tuân thủ chính sách của response và cấu hình xử lý. Nếu nó biến đổi hợp lệ, metadata phải nhất quán với dữ liệu thực gửi, thay vì sao chép cơ học từ upstream.

## 9. HTTP/1.1, HTTP/2 và HTTP/3

| Khía cạnh | HTTP/1.1 | HTTP/2 | HTTP/3 |
|---|---|---|---|
| Dạng truyền message | Cú pháp dòng và body theo framing của HTTP/1.1 | Frame trên stream | Frame trên stream QUIC |
| Chunked transfer coding | Có cơ chế chunked | Không dùng | Không dùng |
| Content-Encoding cho nội dung | Có thể dùng | Có thể dùng | Có thể dùng |
| Connection và các field connection-specific kiểu HTTP/1.1 | Xử lý theo định nghĩa field | Không được mang vào message | Không được mang vào field section |
| Content-Length | Có thể tham gia framing | Không thay thế framing bằng frame/stream | Không thay thế framing bằng frame/stream |

HTTP/2 cấm các field connection-specific như `Connection`, `Keep-Alive`, `Proxy-Connection`, `Transfer-Encoding` và `Upgrade`. Ngoại lệ là `TE` trong request với giá trị chỉ là `trailers`. HTTP/3 cũng quy định loại bỏ thông tin connection-specific và có ngoại lệ tương ứng cho `TE: trailers`. [RFC 9113, mục 8.2.2](https://www.rfc-editor.org/rfc/rfc9113.html#section-8.2.2), [RFC 9114, mục 4.2](https://www.rfc-editor.org/rfc/rfc9114.html#section-4.2).

`Content-Length` vẫn có thể xuất hiện trong HTTP/2 và HTTP/3. Khi message có content, giá trị phải nhất quán với content thực được truyền; sự tồn tại của frame không biến một độ dài sai thành hợp lệ. Các response không có content phải tiếp tục được đọc theo ngữ nghĩa riêng, chẳng hạn HEAD.

Không nhầm `TE` với `Transfer-Encoding`. Cũng không kết luận mọi field liên quan trailer đều là thông tin kết nối: vị trí truyền một field và ngữ nghĩa của field là hai vấn đề cần kiểm tra riêng.

## 10. Những field không nên bị phân loại nhầm

### 10.1. Accept khác Content-Type

~~~http
Accept: application/json
Content-Type: application/xml
~~~

Hai field này có thể cùng xuất hiện trong một request có body: bên gửi muốn nhận JSON nhưng body đang gửi là XML, nếu hợp đồng endpoint cho phép.

Tương tự, `Accept-Encoding: gzip` biểu đạt khả năng hoặc lựa chọn liên quan tới coding được chấp nhận; `Content-Encoding: gzip` mô tả coding đã áp dụng lên biểu diễn liên quan. Không dùng `Accept-Encoding` để khẳng định request body đang nén.

### 10.2. Host và authority phục vụ định tuyến

`Host` trong HTTP/1.1 và thông tin authority trong các phiên bản tương ứng giúp xác định đích request. Chúng không nói dữ liệu là JSON hay gzip.

Khi gateway chuyển tiếp sang hệ thống khác, xử lý đích và authority thuộc trách nhiệm định tuyến có kiểm soát. Không giữ hoặc sửa cơ học chỉ vì field đó không phải metadata biểu diễn.

### 10.3. Authorization và Cookie không phải mô tả biểu diễn

Các field xác thực hoặc phiên mang ngữ cảnh người gọi. Không phân loại chúng là metadata kết nối chỉ vì chúng nằm trong header.

Quyền đọc một tài nguyên phải được kiểm tra theo danh tính và chính sách. Việc được phép giữ lại hay chuyển tiếp thông tin xác thực còn phụ thuộc ranh giới tin cậy; “không phải hop-by-hop” không phải giấy phép chuyển credential tới mọi host.

### 10.4. Cache-Control, Vary và ETag không điều khiển socket

Chúng liên quan tới lưu trữ, lựa chọn biểu diễn và kiểm tra điều kiện. Nếu một URI có nhiều dạng nội dung hoặc coding, chiến lược cache và validator phải phù hợp với các biến thể đó.

Không dùng thời gian sống của cache làm thời gian giữ kết nối. Một biểu diễn có thể còn tươi trong cache dù kết nối tạo ra response đã đóng từ lâu.

### 10.5. Thông tin TLS không tự có thẩm quyền chỉ vì được đưa vào header

TLS có các thuộc tính kết nối riêng. Header như `X-Forwarded-Proto` do một proxy thêm chỉ đáng tin theo cấu hình và ranh giới hạ tầng đã xác định.

Ứng dụng không nên xem mọi giá trị forwarded header do bên ngoài gửi là bằng chứng request gốc dùng HTTPS. Điều này khác với việc đọc `Content-Type` để biết cách parse content.

## 11. Phân chia trách nhiệm trong Java/Spring

Một cách tổ chức phù hợp:

~~~text
Nghiệp vụ:
    Tạo kết quả miền, kiểm tra quyền và quy tắc nghiệp vụ.

HTTP adapter/controller:
    Chọn mã trạng thái, DTO, media type và các header có ý nghĩa API.

Serializer/content-coding layer:
    Tạo byte, áp dụng coding được cấu hình và giữ metadata nhất quán.

HTTP server/connector và proxy:
    Xử lý framing, phiên bản giao thức, stream và vòng đời kết nối.
~~~

Đây là phân chia trách nhiệm khái niệm; tên lớp thực tế phụ thuộc nền tảng. Nén có thể được thực hiện ở ứng dụng, server hoặc gateway, nên phải biết thành phần nào là nguồn có thẩm quyền.

Những quy tắc thực hành:

- Không đặt `Content-Length` bằng `String.length()`.
- Không thêm `Transfer-Encoding: chunked` vào controller rồi giả định connector nào cũng hỗ trợ cách đó.
- Không ép `Connection: keep-alive` vào mọi response, đặc biệt khi gateway có thể phục vụ HTTP/2 hoặc HTTP/3.
- Khi xử lý proxy, dùng thành phần HTTP có chức năng chuyển tiếp phù hợp; không biến một bản copy map header thành proxy hoàn chỉnh.
- Khi client tự giải nén, xác định rõ byte và header mà API client trả ra cho lớp gọi.
- Đặc tả hợp đồng dữ liệu bằng schema và quy tắc API; không bắt client phụ thuộc framing của một chặng nội bộ.

OpenAPI có thể mô tả media type, schema và response header có ý nghĩa với client. Chi tiết framing hoặc giữ kết nối của một tuyến hạ tầng không nên trở thành yêu cầu nghiệp vụ mà mọi client phải tự triển khai.

## 12. Gỡ lỗi bằng câu hỏi theo lớp

Khi gặp lỗi, kiểm tra từ lớp truyền lên lớp dữ liệu:

1. Request/response dùng phiên bản HTTP nào ở từng chặng?
2. Message được parser xác định kết thúc bằng cơ chế nào?
3. Content đã nhận đủ chưa, có bị biến đổi hay giải mã ở thư viện không?
4. Content coding được khai báo có khớp byte đang nhận không?
5. Byte sau giải coding có đúng media type và cách mã hóa ký tự không?
6. Dữ liệu đã parse có tuân thủ schema và nghiệp vụ không?

Ví dụ ánh xạ triệu chứng:

| Triệu chứng | Giả thuyết cần kiểm tra |
|---|---|
| JSON parser thấy dòng kích thước chunk | Tầng ứng dụng đang nhận framing thô hoặc pipeline xử lý sai |
| Gzip decoder báo dữ liệu không đúng định dạng | Body đã giải nén nhưng còn khai báo gzip, hoặc dữ liệu bị cắt/hỏng |
| Client chờ mãi sau phản hồi HEAD | Đang suy body chỉ từ Content-Length, bỏ qua phương thức |
| Response lỗi khi bật HTTP/2 | Có thể còn field connection-specific từ đường HTTP/1.1 |
| Body bị cắt hoặc có byte dư ở message kế tiếp | Content-Length/framing hoặc biến đổi nội dung không nhất quán |
| Chữ tiếng Việt lỗi nhưng framing đúng | Kiểm tra mã hóa ký tự, serializer và quy trình decode |
| Cache trả nhầm biến thể | Kiểm tra thương lượng, Vary, khóa cache và metadata tương ứng |

Đây là giả thuyết để điều tra, không phải kết luận từ một triệu chứng. Nên đối chiếu log ở từng điểm và xác định log chứa byte trên đường truyền hay dữ liệu đã được thư viện xử lý. Tránh ghi credential hoặc nội dung nhạy cảm chỉ để xem header.

## 13. Bài tập tình huống

### Tình huống A: gateway giải nén nhưng giữ nguyên header

Dịch vụ trả `Content-Encoding: gzip`. Gateway giải nén thành JSON rõ rồi gửi tiếp cùng header và độ dài cũ.

**Phân tích:** Metadata không còn khớp content. Bên nhận có thể giải nén sai hoặc xác định độ dài sai. Cần xác định chính sách biến đổi, cập nhật metadata liên quan và để tầng HTTP dựng framing phù hợp với byte thực gửi.

### Tình huống B: copy response HTTP/1.1 sang HTTP/2

Một bộ chuyển tiếp sao chép `Connection: close`, `Transfer-Encoding: chunked` và các field khác vào response HTTP/2.

**Phân tích:** Nó đã mang điều khiển của chặng cũ sang giao thức không cho phép chúng. Bộ chuyển tiếp cần xử lý framing phía nhận, giữ ngữ nghĩa nội dung phù hợp rồi dựng message mới theo HTTP/2.

### Tình huống C: tính độ dài theo ký tự

Một endpoint có dữ liệu tiếng Việt lấy `json.length()` đặt vào `Content-Length`, trong khi serializer gửi UTF-8.

**Phân tích:** Số đơn vị UTF-16 không bằng số byte UTF-8. Nếu còn nén hoặc sửa dữ liệu sau đó, sai lệch có thể thêm. Tính trên byte cuối cùng ở đúng tầng hoặc giao cho HTTP runtime xử lý.

### Tình huống D: xóa Connection nhưng không xóa field được chỉ định

Message HTTP/1.1 có `Connection: X-Hop-Debug`. Proxy xóa riêng `Connection` rồi gửi tiếp `X-Hop-Debug`.

**Phân tích:** Proxy chưa xử lý đầy đủ connection option. Cần đọc danh sách trước khi xóa và xử lý field tương ứng. Không thể chỉ dựa vào một danh sách hop-by-hop cố định.

### Tình huống E: GET có body, HEAD không có body

GET trả JSON 11 byte. HEAD tương ứng trả `Content-Length: 11` và không gửi JSON.

**Phân tích:** Đây có thể là hành vi đúng. Metadata của HEAD mô tả biểu diễn GET tương ứng; không được bắt server gửi body chỉ để khớp cách hiểu giản lược về độ dài.

## 14. Checklist vận dụng

- [ ] Đã xác định field mô tả biểu diễn, điều khiển request hay phục vụ từng chặng.
- [ ] Không coi tất cả HTTP header là metadata của kết nối.
- [ ] Content-Type và Content-Encoding khớp dữ liệu thực tế.
- [ ] Content-Length được hiểu theo byte và ngữ nghĩa phương thức/mã trạng thái.
- [ ] Không gửi đồng thời Content-Length và Transfer-Encoding trong message HTTP/1.1.
- [ ] Proxy xử lý cả Connection và field được connection option chỉ định.
- [ ] Chuyển đổi phiên bản HTTP không mang theo field bị cấm.
- [ ] Biến đổi nội dung đi kèm cập nhật metadata liên quan.
- [ ] Nghiệp vụ và schema không phụ thuộc cách chia chunk hoặc vòng đời socket.
- [ ] Log và công cụ kiểm thử phân biệt dữ liệu trên đường truyền với dữ liệu đã decode.

Khi đọc một field, hãy hỏi nó mô tả điều gì và có phạm vi hiệu lực ở đâu. Cách đọc đó giúp giữ đúng ý nghĩa biểu diễn khi dữ liệu đi qua nhiều thành phần, đồng thời để mỗi chặng HTTP lựa chọn cơ chế truyền phù hợp.
