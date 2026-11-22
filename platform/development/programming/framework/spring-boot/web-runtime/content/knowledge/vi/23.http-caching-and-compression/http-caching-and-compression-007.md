# Ngưỡng kích thước nén và tác động tới CPU, độ trễ

**Module:** Spring Boot - web-runtime  
**Chủ đề cha:** Cache và nén HTTP

## 1. Bài toán: vì sao không nên nén mọi phản hồi?

Một ứng dụng Spring Boot trả về ba loại HTTP response:

- API xác nhận thao tác với JSON chỉ vài trăm byte.
- API danh sách với JSON vài chục hoặc vài trăm kilobyte.
- Trang HTML, CSS, JavaScript, ảnh và file tải xuống với kích thước khác nhau.

Khi client hỗ trợ **gzip**, nén phản hồi có thể giảm đáng kể số byte truyền qua mạng, nhất là JSON/HTML/JavaScript chứa nhiều chuỗi lặp. Nhưng nén có chi phí: server phải dùng **CPU** để mã hóa, có thể cần buffer dữ liệu, client phải giải nén và công việc này có thể làm tăng thời gian chờ ở các luồng xử lý hoặc hàng đợi dưới tải cao.

Nếu response rất nhỏ, gzip có cả header và metadata riêng, nên phần tiết kiệm có thể ít hơn chi phí tính toán, thậm chí **response nén lớn hơn bản gốc**. Nếu body đã là JPEG/PNG/WebP/MP4/ZIP, nén lại thường không đáng giá. Ngược lại, một JSON 500 KB có độ lặp cao đi qua mạng chậm có thể được lợi đáng kể.

**Ngưỡng kích thước nén (compression threshold)** là một trong các điều kiện để server quyết định có nén response hay không. Trong Spring Boot, nó được cấu hình bằng **server.compression.min-response-size**.

Sau bài học, bạn sẽ:

1. Hiểu **Accept-Encoding**, **Content-Encoding**, **Vary: Accept-Encoding** và phân biệt nén body với HTTP/2 header compression.
2. Biết các thuộc tính **server.compression.enabled**, **min-response-size**, **mime-types** trong Spring Boot 3.x và mặc định thực tế.
3. Hiểu giới hạn của ngưỡng khi **Content-Length chưa biết**, response stream, proxy, cache và file đã nén.
4. Tự chạy một ví dụ **Spring Boot 3.x / Java 17+** để kiểm thử JSON nhỏ/lớn bằng curl.
5. Đo tác động đến **CPU, throughput, bandwidth, TTFB, p95/p99 latency** và chọn ngưỡng dựa trên kết quả đo, không dựa vào con số cố định cho mọi hệ thống.

## 2. HTTP content negotiation: nén chỉ xảy ra khi các điều kiện phù hợp

Client cho server biết những content encoding mà mình hiểu:

~~~http
GET /api/items HTTP/1.1
Host: example.test
Accept-Encoding: gzip, br
~~~

Server có thể chọn thuật toán được hỗ trợ và trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Encoding: gzip
Vary: Accept-Encoding

<bytes JSON da duoc gzip nen>
~~~

Dòng trong ngoặc nhọn chỉ mô tả payload nhị phân, không phải JSON thật. Browser sẽ giải nén response theo **Content-Encoding** rồi đưa nội dung logic cho ứng dụng.

Ba header chính:

| Header | Nằm ở đâu? | Vai trò |
| --- | --- | --- |
| **Accept-Encoding** | Request | Client công bố thuật toán có thể giải mã, ví dụ **gzip, br, zstd**; có thể dùng **q-value** để ưu tiên. |
| **Content-Encoding** | Response | Cho client biết server đã áp dụng content encoding nào, ví dụ **gzip**. Vắng header này thường nghĩa response không dùng content encoding được khai báo. |
| **Vary: Accept-Encoding** | Response | Giúp shared cache phân biệt representation cho các giá trị Accept-Encoding khác nhau, tránh phát nhầm bytes gzip cho client không giải mã được. |

**Server không bắt buộc nén chỉ vì client gửi Accept-Encoding: gzip.** Nó còn xét cấu hình, MIME type, response size, trạng thái hệ thống, nội dung đã nén hay chưa, khả năng của connector và proxy.

**Content-Type** vẫn là loại nội dung gốc, chẳng hạn **application/json**. **Content-Encoding: gzip** nói tới dạng biểu diễn của body; đó không phải MIME type mới. Khi representation được nén, **Content-Length nếu xuất hiện mô tả kích thước encoded representation trên wire**, không phải độ dài JSON sau giải nén. Với truyền dạng chunked hoặc HTTP/2 DATA frames, Content-Length có thể không được gửi.

Ví dụ khi client không chấp nhận gzip:

~~~http
GET /api/items HTTP/1.1
Host: example.test
Accept-Encoding: identity
~~~

**identity** chỉ biểu diễn không mã hóa nén. Server được phép trả body nguyên bản nếu hợp lệ theo negotiation. Một số proxy/CDN có thể xử lý lại representation ở chặng sau, nên phải đo response thực tế tại client.

### Nén body khác nén header của HTTP/2 và HTTP/3

- **gzip/br/zstd theo Content-Encoding** xử lý **HTTP representation body** (HTML/JSON/CSS/JS).
- **HTTP/2 HPACK** nén **header fields** giữa hai HTTP/2 peer; **HTTP/3 QPACK** cũng phục vụ header compression. Chúng không tự làm body JSON trở thành gzip.
- **Transfer-Encoding: chunked** của HTTP/1.1 là kỹ thuật đóng khung truyền dữ liệu, **không phải content compression**.
- **TLS** mã hóa đường truyền, không tự quyết định gzip hay ngưỡng kích thước nén.

Vì vậy chuyển server từ HTTP/1.1 lên HTTP/2 hoặc bật TLS **không thay thế** cấu hình response compression.

## 3. Các thuộc tính server.compression.* trong Spring Boot 3.x

Theo tài liệu **Spring Boot 3.3**, các cấu hình chính:

| Thuộc tính | Mặc định Spring Boot 3.3 | Chức năng |
| --- | --- | --- |
| **server.compression.enabled** | **false** | Cho phép embedded server nén HTTP response khi đáp ứng điều kiện. |
| **server.compression.min-response-size** | **2KB (2.048 byte)** | Ngưỡng tối thiểu **Content-Length** dùng để xét nén response. |
| **server.compression.mime-types** | Một danh sách MIME kiểu văn bản/JSON/XML | Giới hạn các loại response được phép nén. |
| **server.compression.excluded-user-agents** | Không có danh sách mặc định | Loại trừ các User-Agent cần tránh compression nếu có lý do tương thích. |

Danh sách **mime-types mặc định** của Spring Boot 3.3:

~~~text
text/html
text/xml
text/plain
text/css
text/javascript
application/javascript
application/json
application/xml
~~~

Một số hướng dẫn chỉ viết **server.compression.enabled=true** rồi cho rằng mọi response sẽ được gzip. Điều đó sai: client phải thương lượng được encoding phù hợp, MIME phải nằm trong danh sách và kích thước phải đạt điều kiện mà server sử dụng. File như **image/jpeg**, **image/png**, **application/zip** thường không có trong danh sách mặc định, vì bản thân định dạng đã được nén hoặc không hưởng lợi nhiều.

**2KB không phải 2.000 byte.** Kiểu DataSize trong Spring Boot sử dụng quy tắc binary sizes: **1KB = 1.024 byte**, nên **2KB = 2.048 byte**, **4KB = 4.096 byte**, **16KB = 16.384 byte**.

### Ví dụ bật nén cho JSON/HTML/JS

~~~properties
server.compression.enabled=true
server.compression.min-response-size=4KB

# Neu khong khai bao mime-types, Spring Boot 3.3 dung danh sach mac dinh.
# Vi du duoi day minh hoa cach khai bao ro cac loai can nen:
server.compression.mime-types=text/html,text/plain,text/css,text/javascript,application/javascript,application/json,application/xml,text/xml
~~~

**min-response-size=4KB** là một **lựa chọn thí nghiệm**, không phải giá trị luôn tối ưu. Với JSON 3 KB, ngưỡng này có thể tránh tốn công nén; với JSON 100 KB, nén thường có lợi nếu mạng đủ chậm và CPU còn dư. Muốn thay giá trị, cần đo workload thật.

**mime-types** khai báo cả danh sách cần hỗ trợ trong cấu hình này, không mặc định xem việc gán một MIME type mới là “nối thêm” vào danh sách cũ. Đừng cấu hình quá rộng, đặc biệt đừng vội đưa **application/octet-stream** hoặc mọi dạng ảnh/video vào nhóm nén.

### Các property không nên suy đoán

**server.compression.min-response-size** là ngưỡng **độ dài response**, **không phải** số byte client tải được trong một giây, tốc độ CPU hay cường độ gzip level. Trong Spring Boot 3.3, **không có một property chuẩn đa container tên server.compression.level** để chỉnh mức nén gzip chung cho Tomcat, Jetty, Undertow và Reactor Netty. Nếu cần fine tuning algorithm/level, phải xem cấu hình connector hoặc tầng proxy/CDN cụ thể.

Tài liệu Spring Boot 3.3 xác nhận response compression được hỗ trợ khi dùng các embedded web server **Tomcat, Jetty, Undertow và Reactor Netty**, nhưng mỗi server có chi tiết triển khai khác nhau. Không giả định bật flag trong Boot thì backend tự hỗ trợ Brotli hoặc Zstandard; **gzip** là trường hợp cơ sở phổ biến, còn **br/zstd** phụ thuộc server, phiên bản thư viện hoặc CDN/edge.

## 4. Ngưỡng được xét lúc nào? Vấn đề Content-Length chưa biết

Tài liệu property định nghĩa **min-response-size** là **minimum Content-Length value required for compression**. Diễn đạt này rất quan trọng: server cần thông tin kích thước **tại thời điểm quyết định**.

Với một response được buffer và biết trước độ dài:

~~~text
Content-Length = 1024 B   ; threshold = 4096 B -> thuong khong nen
Content-Length = 8192 B   ; threshold = 4096 B -> co the nen
~~~

Nhưng với response streaming, async output hoặc body phát từng phần, **Content-Length có thể không biết trước**. Trình xử lý kết nối phải quyết định cách viết response khi dữ liệu còn đang đến. Ví dụ Tomcat có tài liệu: khi compression bật và độ dài chưa xác định, connector **cũng có thể nén** dù không áp dụng trực giác “ít hơn 4 KB thì không nén”.

Do đó:

- **4KB không phải bảo đảm tuyệt đối rằng mọi response dưới 4KB đều không được nén.**
- Một response được gửi với **Content-Length** biết trước có thể hành xử khác response dùng chunked transfer hoặc reactive stream.
- Các container/versions/filters/proxies có thể quyết định nén ở thời điểm khác nhau.
- Nếu có nhiều layer nén, kết quả cuối có thể bị thay đổi bởi **reverse proxy/CDN**, không chỉ bởi Spring Boot.
- Hãy kiểm bằng **HTTP thật và cấu hình môi trường thật**, không chỉ đọc application.properties.

Ví dụ **Flux** trong WebFlux, **StreamingResponseBody** trong MVC, Server-Sent Events (**text/event-stream**) hoặc response được flush theo từng item có thể có độ dài chưa biết. Đừng suy rằng response 300 byte nằm dưới threshold là chắc chắn không nén; cũng đừng suy rằng nén sẽ giúp streaming, vì gzip cần flush và có thể tăng độ trễ nhận từng event.

### Nén có thay đổi Content-Length không?

Nếu response nguyên bản có **Content-Length: 8203**, khi server nén ở connector, trên wire các bytes đã nhỏ hơn. Server phải cập nhật/loại bỏ Content-Length cho phù hợp với biểu diễn đã mã hóa. Không lấy **Content-Length** cuối cùng sau gzip để so ngưỡng vốn được quyết định trước hoặc trong quá trình encode theo cách của container.

Một response đã nén có thể được chuyển bằng **Transfer-Encoding: chunked** trên HTTP/1.1; **HTTP/2** dùng DATA frames. Điều này không chứng minh nén thành công hay thất bại: hãy kiểm tra **Content-Encoding** và số byte thực nhận.

## 5. CPU, latency và bandwidth đổi chác với nhau ra sao?

Ta có thể hình dung đường đi khi server nén:

~~~text
API/Controller tao du lieu
       |
       v
Serialize JSON / render HTML
       |
       v
Compression encoder (CPU + buffer/flush)
       |
       v
Connector, socket, TLS, network
       |
       v
Browser/client decompression (CPU)
       |
       v
Parse JSON, render UI
~~~

Ở server, compression cạnh tranh CPU với serialize JSON, chạy business logic, garbage collection, TLS và các request khác. Khi CPU chưa bận, chi phí encode có thể nhỏ. Khi CPU gần bão hòa, một ít CPU bổ sung trên **mỗi request** có thể làm hàng đợi tăng mạnh và khiến **p95/p99 latency** xấu đi.

Đặt:

- **S** = số byte body trước nén.
- **C** = số byte body sau nén.
- **B** = thông lượng network hiệu dụng (byte/giây).
- **Tenc** = thời gian CPU/wall time encode; **Tdec** = thời gian giải mã phía client.
- **Tbuf** = độ trễ do buffering, chờ flush hoặc điều phối; **Tqueue** = độ trễ chờ CPU/network khi quá tải.

Một mô hình đơn giản để so sánh (không phải phương trình mô tả chính xác mọi server):

~~~text
Khong nen: Traw  ~= Tcommon + S / B
Co nen:    Tgzip ~= Tcommon + Tenc + C / B + Tdec + Tbuf

Muc tiet kiem network ~= (S - C) / B
Nen co loi ve latency neu tiet kiem network
    lon hon chi phi encode + decode + buffer/queue phat sinh.
~~~

**Tcommon** gồm những phần gần như không đổi như xử lý nghiệp vụ; trên thực tế CPU và truyền mạng có thể **chồng lấp theo pipeline**, nên tổng thời gian không luôn bằng tổng tuần tự. Thời gian **TTFB** có thể xấu đi khi encoder giữ buffer chờ đủ dữ liệu/flush, trong khi **time-to-last-byte** có thể giảm do tổng bytes ít hơn.

Ví dụ minh họa, **không phải benchmark thực đo**:

- JSON gốc 50 KB, gzip còn 10 KB → tiết kiệm 40 KB.
- Với throughput hiệu dụng 2 MB/s, thời gian truyền tiết kiệm khoảng 20 ms.
- Nếu encode tốn 3 ms, giải mã 0,5 ms và buffering 1 ms, kết quả gần đúng có thể **lợi khoảng 15,5 ms** trong mô hình cộng đơn giản.
- Trên mạng 100 MB/s, việc truyền bớt 40 KB chỉ tiết kiệm khoảng 0,4 ms; cùng chi phí encode/decode có thể khiến tổng latency xấu hơn, đặc biệt khi CPU server bận.

Kết luận không phải “luôn tắt gzip trên LAN”. Vì dữ liệu thật, CPU, queue, RTT, cache và trình duyệt khác nhau, **phải đo trong bối cảnh triển khai**. JSON có nhiều chuỗi lặp thường nén tốt; dữ liệu gần như ngẫu nhiên không có cùng tỉ lệ.

### Compression ratio

Định nghĩa:

~~~text
Compression ratio (ty le kich thuoc) = C / S
Bandwidth saved (%) = (1 - C / S) * 100%
~~~

Ví dụ S = 100 KB, C = 25 KB → kích thước compressed bằng 25% bản gốc, tiết kiệm 75% bytes body. Chú ý **HTTP headers, TLS records, packet overhead** vẫn tồn tại; tổng network bytes không giảm đúng 75% trong mọi điều kiện.

### Throughput và CPU trên nhiều request

Nếu một request cần thêm **2 ms CPU** cho encode và server phục vụ **500 request/giây**, nhu cầu CPU lý thuyết tăng khoảng **1 CPU-second mỗi giây** chỉ cho compression (khi các con số là CPU time thực). Đây là ví dụ tính tải, không phải số đo định mức của gzip. Ở nhiều core, công việc có thể phân tán; ở event loop bị nghẽn hoặc có cgroup CPU quota, tăng CPU còn kéo theo scheduling và tail latency.

**Một vài request thử bằng curl không đủ để chọn threshold**. Đo thêm under concurrency, CPU throttling và p99.

## 6. Chọn MIME type nào nên nén?

| Loại dữ liệu | Tính chất | Quyết định ban đầu |
| --- | --- | --- |
| **text/html**, **text/css**, **application/javascript** | Văn bản nhiều mẫu lặp, thường tiết kiệm byte. | Có thể bật nén nếu payload đủ lớn. |
| **application/json**, **application/xml**, **text/plain** | Dữ liệu text dễ nén, ratio tùy payload. | Thử trên dữ liệu thực; thường hưởng lợi. |
| **application/x-ndjson**, **text/event-stream** | Có thể stream dài, cần flush và độ trễ từng record. | Cần đánh giá riêng codec, buffering và latency; không mặc định dùng chính sách giống JSON một khối. |
| **image/jpeg**, **image/png**, **image/webp**, **image/avif** | Định dạng thường đã nén. | Không nén gzip lại theo mặc định. |
| **application/zip**, gzip, PDF đã tối ưu, MP4 | Có thể đã nén hoặc khó nén tiếp. | Tránh encode lại trừ khi số liệu thực chứng minh. |
| **application/octet-stream** | MIME chung chung, chưa biết nội dung. | Không thêm vào danh sách chỉ vì muốn nén mọi response. |
| **application/pdf** | Tùy cấu trúc/nén nội bộ. | Kiểm tra mức giảm thực tế và đặc tính Range/download; thường không phải ưu tiên. |

**Đối với file static** được build sẵn, một phương án là tạo **.br/.gz precompressed assets** ở build/CDN và phục vụ theo Accept-Encoding thay vì nén cùng bytes mỗi request. Với những đường dẫn không thay đổi nội dung, precompression giúp giảm CPU runtime. Nhưng cần cấu hình **Vary**, **Content-Encoding**, content type và cache key đúng, cũng như xử lý URL fingerprint/ETag tương ứng. Không giả định bật server.compression.enabled tự tạo file .br trên disk.

## 7. Demo hoàn chỉnh Spring Boot 3.x + Java 17+: tự kiểm ngưỡng 4KB

Bài demo dùng **spring-boot-starter-web** và embedded **Tomcat** mặc định. Đặt **Content-Length** biết trước để quan sát threshold rõ ràng, không phụ thuộc kích thước streaming body chưa xác định.

### 7.1. Dependency

Với project Spring Boot 3.x có Java 17+, Gradle wrapper và plugin Boot đã cấu hình, trong **build.gradle** (Groovy DSL):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

### 7.2. application.properties

Tạo **src/main/resources/application.properties**:

~~~properties
server.port=8080
server.compression.enabled=true
server.compression.min-response-size=4KB
server.compression.mime-types=application/json,text/html,text/plain,text/css,text/javascript,application/javascript,application/xml,text/xml
~~~

Cấu hình 4KB dành cho ví dụ và vẫn cần **Accept-Encoding: gzip** ở request. Nếu bật Spring Security, thêm reverse proxy hoặc đổi embedded server, kết quả cần đánh giá lại.

### 7.3. Một tệp Java chạy được

Tạo **src/main/java/com/example/compression/CompressionDemoApplication.java**:

~~~java
package com.example.compression;

import java.nio.charset.StandardCharsets;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class CompressionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CompressionDemoApplication.class, args);
    }
}

@RestController
class CompressionController {

    @GetMapping(
            value = "/api/payload/{characters}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<byte[]> payload(@PathVariable int characters) {
        if (characters < 0 || characters > 65536) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "invalid payload size");
        }

        String json = "{\"data\":\"" + "a".repeat(characters) + "\"}";
        byte[] body = json.getBytes(StandardCharsets.UTF_8);

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .cacheControl(CacheControl.noStore())
                // Quyet dinh do dai truoc khi HTTP connector nen response.
                .contentLength(body.length)
                .body(body);
    }
}
~~~

Tệp có **một public top-level class** khớp tên file; **CompressionController** package-private được Spring Boot quét trong cùng package. **String.repeat** hỗ trợ từ Java 11, hợp lệ với Java 17. Không có tệp class phụ cần tạo thêm.

Các body JSON tạo ra đều hợp lệ và chứa ký tự ASCII. Với **N ký tự a**, chuỗi **{"data":"..."}** dài **N + 11 bytes**, cụ thể:

| URL | Raw body size theo UTF-8 | So với threshold 4KB |
| --- | --- | --- |
| **/api/payload/256** | **267 byte** | Nhỏ hơn 4.096 byte |
| **/api/payload/8192** | **8.203 byte** | Lớn hơn 4.096 byte |
| **/api/payload/65536** | **65.547 byte** | Lớn hơn 4.096 byte |

**CacheControl.noStore()** được dùng để giảm ảnh hưởng cache khi quan sát demo, không có nghĩa nên no-store mọi JSON trong production. **contentLength(body.length)** giúp container biết kích thước chưa nén; khi gzip thực sự được áp dụng, header Content-Length cuối cùng trên wire có thể đổi/bị bỏ theo cách connector gửi compressed response.

**Giới hạn của demo:** chuỗi lặp **a** nén **rất tốt**, nhưng không đại diện một JSON thực tế chứa nhiều dữ liệu khó nén. Demo phù hợp xác minh cấu hình; benchmark cần dữ liệu, kích thước và tỉ lệ lặp đại diện traffic production.

### 7.4. Chạy server

~~~bash
./gradlew bootRun
~~~

Trên Windows, dùng **gradlew.bat bootRun** trong cmd/PowerShell. Khi ứng dụng chạy, dùng terminal Bash khác để thử HTTP.

### 7.5. Test nhỏ và lớn, giữ raw encoded bytes

**Test nhỏ 267 B:**

~~~bash
curl -sS -D small.headers -o small.wire \
  -H 'Accept-Encoding: gzip' \
  http://localhost:8080/api/payload/256
~~~

**Test lớn 8.203 B:**

~~~bash
curl -sS -D large.headers -o large.wire \
  -H 'Accept-Encoding: gzip' \
  http://localhost:8080/api/payload/8192
~~~

**Xem header và số bytes download:**

~~~bash
grep -iE '^(HTTP/|content-type:|content-encoding:|content-length:|vary:|cache-control:)' \
  small.headers large.headers
wc -c small.wire large.wire
~~~

Khi dùng Tomcat mặc định và response đủ điều kiện:

- **small.headers** thông thường **không có Content-Encoding: gzip** do Content-Length 267 B nhỏ hơn 4KB.
- **large.headers** thường có **Content-Encoding: gzip**; file **large.wire** chứa bytes gzip, nhỏ hơn nhiều 8.203 B do chuỗi a rất dễ nén.
- **Vary: Accept-Encoding** cần được xem xét khi compression negotiation xảy ra; nếu một intermediary xử lý representation, phải kiểm ở client và CDN.
- Content-Length trên wire **không nhất thiết còn bằng 8.203** sau gzip.

**Tại sao không dùng --compressed cho lệnh đo raw body?** Tùy chọn **curl --compressed** thường tự quảng bá encoding được hỗ trợ **và tự giải nén body trước khi ghi -o**. Điều đó phù hợp để kiểm nội dung logic, nhưng file kết quả **không đại diện số encoded bytes trên wire**. Trong hai lệnh trên ta chủ động gửi **-H 'Accept-Encoding: gzip'** và lưu raw response body do curl chưa bật tự giải nén.

Sau khi xác nhận **large.headers có Content-Encoding: gzip**, bạn có thể kiểm tính hợp lệ của file:

~~~bash
gzip -t large.wire
gzip -cd large.wire | head -c 80
~~~

Dòng đầu không xuất ra gì và kết thúc với exit code 0 nếu gzip bytes hợp lệ; dòng sau in phần đầu JSON đã giải nén. Nếu header không nói gzip, đừng chạy gzip -t rồi kết luận file/application hỏng — hãy tìm vì sao response chưa được nén.

**Test client tự giải nén:**

~~~bash
curl -sS --compressed \
  http://localhost:8080/api/payload/8192 \
  -o large-decoded.json

wc -c large-decoded.json
~~~

File decoded có **8.203 byte** bất kể raw transfer đã được gzip hay chưa, nếu response logic đúng. Test này **không phải** cách đo bandwidth tiết kiệm.

### 7.6. So với request không nén

~~~bash
curl -sS -D identity.headers -o identity.wire \
  -H 'Accept-Encoding: identity' \
  http://localhost:8080/api/payload/8192

wc -c identity.wire large.wire
~~~

Trong môi trường không có proxy tự ý biến đổi, **identity.wire** có **8.203 byte**, còn **large.wire** nhỏ hơn khi gzip thực sự bật. Số byte nén chính xác phụ thuộc gzip encoder và config, nên không khẳng định một giá trị cứng.

Dùng **curl -w** nếu muốn đo TTFB và total time:

~~~bash
curl -sS -o /dev/null \
  -H 'Accept-Encoding: identity' \
  -w 'identity ttfb=%{time_starttransfer}s total=%{time_total}s\n' \
  http://localhost:8080/api/payload/8192

curl -sS -o /dev/null \
  -H 'Accept-Encoding: gzip' \
  -w 'gzip ttfb=%{time_starttransfer}s total=%{time_total}s\n' \
  http://localhost:8080/api/payload/8192
~~~

**Các số đo của một request localhost gần như vô dụng để kết luận hiệu năng production** vì noise, JVM warm-up, connection setup và bộ nhớ cache. Chúng chỉ minh họa cách lấy metric. Với Windows không có **/dev/null**, có thể thay bằng output file tạm thích hợp hoặc chạy trên terminal Bash.

## 8. Tăng hoặc giảm threshold gây tác động gì?

Giả sử cùng server và nhiều response có Content-Length đã biết:

| Thay đổi | Ảnh hưởng có thể xảy ra | Rủi ro cần đo |
| --- | --- | --- |
| **2KB → 1KB** | Nhiều response nhỏ được nén hơn; tiết kiệm thêm một số byte mỗi request. | CPU/QPS tăng, gzip overhead, latency nhỏ có thể xấu đi. |
| **2KB → 4KB** | Bỏ nén response 2–4KB; giảm số lần encode. | Tăng bytes truyền đối với nhóm response đó, ảnh hưởng client mạng chậm. |
| **4KB → 16KB** | Chỉ nén body lớn hơn, giảm chi phí nhiều request nhỏ/trung bình. | Mất lợi ích bandwidth của JSON 5–15KB vốn nén tốt. |
| **Threshold rất thấp** | Cố nén phần lớn text responses. | CPU tăng, nhiều payload nhỏ giảm không đáng kể hoặc phình kích thước. |
| **Threshold quá cao** | Bớt encoder work. | Bandwidth/egress cost và transfer time tăng đáng kể nếu nhiều text payload vừa và lớn. |

Đây là xu hướng có thể xảy ra, **không phải định luật bất biến**: với Content-Length không biết, container/proxy có thể nén khác; HTTP cache, static precompression và request mix cũng làm thay đổi kết quả.

Đừng chỉ chọn threshold bằng cách tối ưu **compression ratio**. Cần xem **latency (đặc biệt p95/p99)**, throughput, CPU usage, CPU throttling, tỉ lệ lỗi và chi phí egress. Một threshold tiết kiệm nhiều byte nhất không nhất thiết là cấu hình đem lại user experience tốt nhất.

### Hai ví dụ đối nghịch

**Trường hợp A — API nhỏ, tải cao:** Một API gọi hàng nghìn lần mỗi giây, body trung bình 700 B. Bật nén ngay từ vài byte có thể tạo rất nhiều encode jobs nhưng chỉ tiết kiệm một lượng data rất nhỏ. Giữ threshold vừa phải, giảm số request hoặc dùng cache/HTTP keep-alive có thể hiệu quả hơn.

**Trường hợp B — dashboard JSON lớn qua mạng di động:** Response 400 KB với nhiều trường trùng lặp, client ở mạng yếu. Nén có thể cắt phần lớn dữ liệu cần truyền, cải thiện thời gian hoàn tất và data usage. Chi phí CPU có thể hợp lý, hoặc có thể được chuyển sang edge/CDN nếu response cacheable.

Kết luận cần từ phép đo cùng traffic, không phải chọn hai giá trị trên như một cấu hình mặc định áp dụng mọi ứng dụng.

## 9. Buffering, streaming và thời gian tới byte đầu tiên

Một HTTP response thông thường có thể được tạo đủ dữ liệu trước khi gửi; một response streaming lại xuất từng phần. Nén streaming có thể gây trade-off riêng:

~~~text
Server tao event 1 ----+
Server tao event 2 ----+--> encoder giu buffer? --> flush --> client
Server tao event 3 ----+
~~~

Nếu gzip encoder chờ buffer đủ lớn trước khi phát một block nén, **TTFB** hoặc khoảng cách giữa các event ở client có thể tăng. Một số connector/streaming framework hỗ trợ flush, nhưng flush thường xuyên có thể giảm compression ratio và tăng overhead.

Những trường hợp cần thử riêng:

- **Server-Sent Events (text/event-stream)**: mục tiêu thường là thời gian nhận từng event thấp. Nếu nén làm event bị dồn, có thể chọn không nén tuyến SSE hoặc điều chỉnh flush ở connector/proxy; không phải cứ MIME type text là nên nén.
- **NDJSON (application/x-ndjson)**: có thể stream mỗi record; đánh đổi ratio với latency/buffering, xem container và proxy.
- **StreamingResponseBody** trong Spring MVC hoặc **Flux<DataBuffer>** trong WebFlux: độ dài có thể chưa biết; không áp dụng thô cứng “ngưỡng 4KB”.
- **File download lớn**: nếu file đã nén, gzip thêm có thể tăng CPU mà không giảm bytes. Nếu file static đã có .gz/.br precompressed, phục vụ đúng representation thường tốt hơn runtime compression.
- **HTTP/2 multiplexing**: nhiều stream cùng connection, nhưng CPU nén cho một stream vẫn có thể ảnh hưởng tài nguyên chung; HPACK header compression không xóa chi phí body gzip.

Nếu proxy như Nginx hoặc CDN có buffering, phải kiểm tra **server → proxy** lẫn **proxy → browser**. Có thể backend flush ngay nhưng edge tích luỹ response, hoặc backend gửi raw còn edge gzip ở đầu ra. Một phép đo từ browser không đủ xác định stage gây chậm nếu thiếu tracing/metrics.

## 10. Cache và nén: cần tránh sai representation

Khi endpoint công khai có thể cache và hỗ trợ cả gzip lẫn identity:

~~~text
GET /assets/app.js (Accept-Encoding: gzip)   -> representation gzip
GET /assets/app.js (Accept-Encoding: identity)-> representation raw
~~~

**Vary: Accept-Encoding** là chìa khóa để shared cache phân biệt đúng các representation theo negotiation. Nếu CDN không để ý tới encoding trong cache key, một client không hỗ trợ gzip có thể nhận dữ liệu gzip không mong muốn, hoặc cache miss/hit bị xử lý kém hiệu quả.

**ETag** có thể gắn với representation và content coding; không mặc định dùng một strong ETag cho hai byte representation khác nhau. Kiểm tra server/CDN xử lý validator và **304 Not Modified** sau compression; đừng so raw bytes với encoded bytes rồi cho rằng ETag sai chỉ vì khác độ dài.

**Cache-Control** quyết định response được lưu/tái sử dụng, **không bật/tắt gzip**. Ví dụ:

- HTML entrypoint thường cần revalidation/TTL ngắn để cập nhật reference tới asset mới.
- Asset fingerprint có thể cache dài và được **precompress** một lần khi build.
- API dữ liệu riêng tư phải có chính sách cache phù hợp; không bật public caching chỉ vì bật gzip.
- Với response được phục vụ từ cache, CPU compression tại origin có thể chỉ phát sinh khi **cache miss**, nên benchmark cần phân biệt warm/cold cache.

**Không nên nén cùng response hai lần.** Backend đã trả **Content-Encoding: gzip** thì proxy không được mù quáng gzip tiếp mà không xử lý encoding đúng. Cấu hình CDN/ingress và embedded server phải có trách nhiệm rõ ràng: origin nén, edge nén, hay serve precompressed representation.

### Caching có thể che chi phí CPU

Một API được CDN cache với TTL cao có thể được gzip tại edge rồi phân phối rất nhiều lần mà không bắt JVM nén lại từng request. Ngược lại API cá nhân hóa không cache được vẫn khiến origin phải xử lý mỗi request. Vì vậy tác động CPU của gzip **phụ thuộc tầng nào thật sự nén và tỉ lệ cache hit**, không chỉ tỷ lệ traffic có Accept-Encoding: gzip.

## 11. Proxy/CDN có thể thay đổi kết luận từ Spring Boot

Các topology điển hình:

**A. Client gọi trực tiếp Spring Boot:** server.compression.enabled và mime/threshold ở Boot có ảnh hưởng rõ. Đo Content-Encoding, bytes, CPU trên JVM và network.

**B. Client → Nginx → Spring Boot:** Nginx có thể bật gzip, buffer, cache hoặc chuyển tiếp Accept-Encoding theo chính sách khác. Client thấy gzip có thể do **Nginx**, không phải do Boot. Boot có thể trả identity và Nginx nén; hoặc Boot trả gzip và Nginx giữ nguyên.

**C. Client → CDN/ingress → nhiều Spring Boot instances:** Edge chọn br/gzip, lưu biến thể và trả cho browser; JVM có thể chỉ phục vụ identity trong nội bộ. Ngưỡng ở CDN và Boot có thể không đồng nhất; cần xác định layer nào là source of truth cho encoding.

Một số lỗi phổ biến:

- **CDN nén file JPEG/ZIP** do MIME rule quá rộng, làm tăng CPU mà không giảm bytes.
- **Vary thiếu hoặc cache key sai**, khiến cache chứa nhiều biến thể không mong đợi.
- **Brotli chỉ được bật ở edge**, trong khi test trực tiếp localhost chỉ cho gzip; kết luận nhầm Boot “không hoạt động”.
- **Origin và proxy đều nén** nhưng metric trên JVM không phản ánh đúng bytes tại client.
- **Proxy response buffering** làm SSE/stream chậm dù network bytes giảm.
- **Backend dùng Content-Length đã biết, proxy stream không biết length**, dẫn tới kết quả threshold khác nhau ở hai hop.

Cần lấy header và metric ở **mỗi chặng** nếu yêu cầu điều tra latency cao.

## 12. Nén và bảo mật

Compression là tối ưu hiệu năng, nhưng có rủi ro nếu nén chung **bí mật và dữ liệu kẻ tấn công điều khiển được** trong một response. Các tấn công đo kích thước như **BREACH** khai thác việc kích thước ciphertext thay đổi theo mức độ giống nhau của các chuỗi trong response đã nén, nhất là khi có token bí mật và dữ liệu phản chiếu.

Những lưu ý:

1. Không phản chiếu tùy tiện dữ liệu user-controlled cạnh token/secret nhạy cảm trong cùng response nén.
2. Với các endpoint có **CSRF token hoặc secret** được đưa vào HTML, đánh giá threat model và biện pháp giảm thiểu như không nén phản hồi đó, tách secret khỏi phần bị phản chiếu, padding có chủ đích, token randomization, hạn chế rate hoặc các kiểm soát phù hợp.
3. **HTTPS/TLS không tự loại bỏ rủi ro side channel theo kích thước**; nó bảo vệ nội dung nhưng kích thước traffic vẫn có thể quan sát được ở một số kịch bản.
4. **Secure, HttpOnly, SameSite cookie** vẫn quan trọng, nhưng không tự biến một trang nén chứa secret phản chiếu thành an toàn.
5. Không log raw body chứa secret chỉ để đo compression ratio; đo theo bucket kích thước hoặc dữ liệu đã được khử nhạy cảm.

Ngoài ra, client giải nén response rất nhỏ thành dữ liệu cực lớn có thể gặp **decompression bomb** nếu nội dung từ nguồn không tin cậy; phía client cũng cần giới hạn body, decoded size và memory. **server.compression.*** là cấu hình response compression ở server, không phải giới hạn inbound upload/request hay hạn mức decompression ở client.

## 13. Quy trình benchmark để chọn min-response-size có cơ sở

**Bước 1 – Chốt dữ liệu đại diện.** Thu các lớp response: JSON nhỏ (0–2 KB), vừa (2–16 KB), lớn (16–256 KB), HTML/JS/CSS, stream và file đã nén. Dùng dữ liệu thử không chứa bí mật, có mức độ lặp tương tự production. Tránh chỉ benchmark chuỗi a trong demo.

**Bước 2 – Đặt các ứng viên threshold.** Ví dụ thử: **disabled**, **2KB**, **4KB**, **8KB** và **16KB**. Không chọn ứng viên chỉ vì phổ biến. Giữ MIME policy, container, JVM heap, CPU limit và client environment giống nhau giữa các lượt.

**Bước 3 – Kiểm chứng functional HTTP trước.** Với mỗi case, xác nhận:

- Request **Accept-Encoding** đúng; không dùng curl auto-decompression khi đang đo encoded bytes.
- Response **Content-Encoding** đúng; **Vary** và Content-Type không hỏng.
- Body giải nén về đúng bytes logic; nếu bị 304/cache hit thì loại khỏi phép đo không liên quan.
- Response có **Content-Length** hay streaming không; ghi nhận sự khác biệt.
- Edge/CDN có đổi encoding không; xác định tầng đang nén.

**Bước 4 – Đo cả latency và CPU dưới concurrency.** Dùng một công cụ tải phù hợp (k6, Gatling, wrk/JMeter tùy khả năng dự án), chạy warm-up JVM ổn định. Đo đồng thời:

| Nhóm metric | Chỉ số cần quan sát |
| --- | --- |
| **HTTP latency** | p50, p95, p99, **TTFB**, time-to-last-byte, error rate |
| **Throughput** | Requests/s, responses/s, số byte raw và encoded được truyền |
| **CPU server** | CPU usage/time, cgroup throttling, runnable queue, thread/event-loop saturation |
| **Memory** | Heap/direct memory, allocation/GC, buffer sizes, active connections |
| **Network** | Egress bytes/s, tốc độ client, RTT, packet retransmits khi thích hợp |
| **Cache** | Origin vs CDN hit rate, compressed variant cache hit/miss |
| **Client** | Decode time, CPU trên thiết bị yếu, parse/render time, hiệu quả tải trang |

**Bước 5 – Chạy hai môi trường mạng.** Mạng local nhanh có thể che lợi ích giảm bytes; mạng di động hoặc mạng qua chặng xa làm lợi ích rõ hơn. Mô phỏng RTT/bandwidth một cách có kiểm soát; đo với HTTP version và TLS giống production. Giữ **connection reuse**, tỷ lệ cache hit, số client và mix endpoints nhất quán.

**Bước 6 – So sánh theo mục tiêu SLO.** Ví dụ:

- Nếu mục tiêu là p99 dưới 200 ms, đừng chỉ giảm 20% egress mà làm p99 tăng vượt SLO.
- Nếu CPU gần hết ngân sách, threshold cao hơn hoặc precompression tại CDN có thể tốt hơn nén mọi API nhỏ.
- Nếu người dùng thường ở mạng chậm, nén response vừa/lớn có thể đem lại lợi ích lớn dù tăng vài ms encode.
- Nếu endpoint SSE yêu cầu nhận event trong vài trăm ms, đo thời gian từng event và cân nhắc tách quy tắc compression thay vì tối ưu size thuần túy.

**Bước 7 – Canary và theo dõi.** Triển khai thay đổi theo một phần traffic, đo cả tail latency, CPU throttling, compressed ratio, request errors, cache behavior và network egress. Có rollback khi SLO xấu đi. Thay threshold mà không theo dõi thực tế mới chỉ là giả thuyết, chưa phải kết quả tối ưu.

### Những bẫy đo lường cần tránh

- **Chỉ đo curl localhost vài lần:** quá ít sample, bị JIT warm-up, scheduler và connection setup ảnh hưởng.
- **Đo --compressed -o file rồi so kích thước file:** curl đã giải nén, không đo wire bytes.
- **Dùng payload toàn a:** ratio cực tốt nhưng không đại diện response JSON thật.
- **So response cache hit với cache miss:** CPU và latency origin khác nhau.
- **Không kiểm Content-Encoding:** có thể bạn tưởng so gzip/identity nhưng server đã gửi cùng một representation.
- **Chỉ nhìn average latency:** compression có thể làm **p99** xấu đi trong khi p50 ổn.
- **Bật đồng thời gzip ở Boot và CDN không rõ trách nhiệm:** gây khó so sánh resource usage/encoding thực.
- **Benchmark file ảnh/ZIP rồi kết luận gzip vô dụng cho JSON:** loại dữ liệu và entropy khác nhau.

## 14. Những lỗi phổ biến trong ứng dụng Spring Boot

| Hiện tượng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| Đặt **min-response-size=1KB** nhưng response không nén | **server.compression.enabled=false**, MIME không có trong danh sách hoặc client không gửi Accept-Encoding phù hợp. | Xem properties đã bind, Content-Type/Accept-Encoding, server connector. |
| JSON nhỏ hơn ngưỡng vẫn có gzip | Response streaming/không có Content-Length biết trước; proxy nén ở edge. | Kiểm tra headers origin vs edge, transfer mode, connector thực. |
| Nén rồi nhưng TTFB xấu hơn | Encoder buffering, CPU encode, proxy response buffering. | Đo TTFB, flush, CPU và stream timeline. |
| Bandwidth giảm, p99 tăng mạnh | CPU compression đẩy server gần bão hòa hoặc throttle trong container. | Đo CPU throttling, queue, p95/p99, hạ compression work hoặc chuyển sang precompression. |
| gzip file JPEG/MP4 không giảm size | Dữ liệu đã nén, overhead gzip. | Loại MIME đó, kiểm bytes trước/sau trên wire. |
| Vừa bật nén thì SSE cập nhật theo đợt | Compression/proxy buffering giữ data trước flush. | Đo event arrival, xem chính sách streaming và vô hiệu hóa nén cho SSE nếu cần. |
| Browser lỗi vì response bytes không đúng | Cache variant/Vary, Content-Encoding, proxy double compression hoặc corrupt transform. | Kiểm response header và decode, cache key ở mỗi hop. |
| Curl báo body chưa giải nén | Client gửi Accept-Encoding thủ công nên curl giữ raw compressed body. | Dùng **--compressed** khi muốn đọc nội dung đã decode. |
| Bật gzip ở Boot nhưng browser thấy Brotli | CDN/edge xử lý Content-Encoding hoặc browser negotiation khác. | Đo origin và edge riêng; xem ai tạo br. |
| Body nhỏ nhưng response trễ | RTT, TTFB, encode, parse, GC hoặc business logic mới là nút thắt. | Tracing từ app tới network, đừng quy mọi chậm vào threshold. |
| Nén response chứa token + reflected input | Nguy cơ side channel theo kích thước. | Đánh giá BREACH và giảm thiểu ở endpoint nhạy cảm. |

## 15. Câu hỏi vận dụng

**Tình huống 1:** Spring Boot đặt **server.compression.enabled=true** và **min-response-size=4KB**. Một endpoint JSON trả 1 KB, có **Content-Length** chính xác. Có chắc gzip không? Với connector mặc định thực hiện kiểm threshold theo known Content-Length, **thường không nén**. Nhưng khi có proxy hoặc triển khai khác, phải kiểm response cuối; không coi cấu hình là lời hứa tuyệt đối của mọi hop.

**Tình huống 2:** Server trả JSON 1 KB dạng stream không có Content-Length. Browser thấy **Content-Encoding: gzip** dù threshold 4KB. Có phải bug Spring Boot? **Không nhất thiết**: connector có thể nén response độ dài chưa biết, hoặc edge nén sau. Kiểm origin/edge và cơ chế streaming.

**Tình huống 3:** JSON 80 KB giảm còn 16 KB khi gzip, nhưng CPU usage tăng từ 65% lên 95% và p99 latency tăng. Nên luôn giữ gzip vì tiết kiệm 80% bandwidth? **Không.** Cần cân nhắc SLO, CPU, concurrency, CDN/precompression và tác động client; có thể đổi threshold/MIME/điểm nén hoặc tăng năng lực.

**Tình huống 4:** File PNG 1 MB gần như không giảm khi gzip. Có nên tăng gzip level cực đại? **Không nên mặc định**; định dạng đã nén, cần đo xem ratio có cải thiện đủ bù CPU không. Thường loại khỏi MIME list.

**Tình huống 5:** CDN trả bản gzip cho client không chấp nhận gzip. Lỗi ở Spring Boot threshold? **Chưa chắc**; phải xem **Vary: Accept-Encoding** và CDN cache key/variant negotiation.

**Tình huống 6:** Response từ **curl --compressed** được ghi ra tệp 8.203 byte, đúng bằng JSON gốc. Có nghĩa server không nén? **Không.** curl có thể đã nhận gzip rồi tự giải nén trước khi ghi file. Cần kiểm Content-Encoding/raw wire representation.

**Tình huống 7:** Một API JSON được cache 99% tại edge, còn origin phải nén chỉ 1% requests. Nên đo CPU ở đâu? **Cả edge và origin**, bởi CPU của Boot không phản ánh toàn bộ compression work ở CDN.

**Tình huống 8:** Một HTML response chứa CSRF token bí mật và phần text do attacker kiểm soát. Có nên chỉ nhìn bandwidth saved rồi bật gzip? **Không**; cần kiểm threat model side channel theo kích thước và áp dụng biện pháp giảm thiểu.

## 16. Checklist áp dụng vào dự án thật

1. Xác nhận stack **Spring MVC/Tomcat** hay **WebFlux/Reactor Netty**, proxy và CDN nào đang nén.
2. Xem **enabled**, **min-response-size**, **mime-types** ở cấu hình đang chạy, không chỉ file properties nguồn.
3. Phân loại response theo **size**, **MIME**, **compression ratio**, **có stream hay không**, **có chứa secret không**.
4. Kiểm **Accept-Encoding**, **Content-Encoding**, **Vary: Accept-Encoding** và body decode thật.
5. Không dùng gzip cho tài nguyên đã nén nếu không có lợi ích được đo.
6. Thử candidate thresholds theo một bộ tải đại diện; nhìn **p95/p99**, CPU và bandwidth, không chỉ average.
7. Kiểm precompression/caching cho static assets để giảm CPU ở runtime.
8. Test riêng stream/SSE và Content-Length không xác định.
9. Xem SLO, CPU quota, CDN bill/egress và network của khách hàng.
10. Canary thay đổi, theo dõi metric, rollback khi latency/error rate xấu đi.

**Kết luận:** **Ngưỡng nén không phải “càng thấp càng tốt” hoặc “càng cao càng ít tốn CPU nên luôn tốt”.** Nó là một điểm điều khiển giúp cân bằng chi phí encode/decode/buffer với lượng byte tiết kiệm trên mạng. Trong Spring Boot 3.3, compression **tắt theo mặc định** và ngưỡng mặc định **2KB** chỉ có ý nghĩa khi bật nén; quyết định production cần kết hợp MIME, header, Content-Length, topology proxy và benchmark dưới tải thật.

## 17. Tài liệu tham khảo chính thống

- **Spring Boot 3.3 – Embedded Web Servers / Enable HTTP Response Compression:** https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- **Spring Boot 3.3 – Common Application Properties:** https://docs.spring.io/spring-boot/3.3/appendix/application-properties/ (server.compression.enabled, mime-types, min-response-size).
- **Spring Boot 3.3 – Compression API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/server/Compression.html
- **Apache Tomcat – HTTP Connector compression:** https://tomcat.apache.org/tomcat-10.1-doc/config/http.html (nén khi Content-Length chưa biết, MIME type, connector semantics).
- **MDN – HTTP Compression:** https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Compression
- **MDN – Accept-Encoding:** https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Accept-Encoding
- **MDN – Content-Encoding:** https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Encoding
- **MDN – Vary:** https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Vary
- **RFC 9110 – HTTP Semantics:** https://www.rfc-editor.org/rfc/rfc9110 (content codings, representation metadata và content negotiation).
