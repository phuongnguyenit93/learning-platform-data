# Phối hợp nén tại ứng dụng, reverse proxy và CDN

Một request HTTP trong hệ thống Spring Boot hiện đại thường đi qua nhiều lớp: **ứng dụng (origin)** → **reverse proxy/ingress** → **CDN/edge** → **trình duyệt**. Cả ba lớp đầu đều có thể nén response bằng gzip, Brotli hoặc thuật toán khác. Nếu cấu hình thiếu chủ đích, có thể vừa lãng phí CPU, vừa làm sai `Content-Encoding`, vừa lưu nhầm các biến thể vào cache. Kết quả là phản hồi bị lỗi giải nén, người dùng có thiết bị không hỗ trợ thuật toán vẫn nhận nội dung nén, cache hit kém hoặc dữ liệu cá nhân bị cache dùng chung.

**Nguyên tắc cốt lõi:** xác định rõ **lớp chịu trách nhiệm nén cho từng nhóm tài nguyên và từng chặng mạng**, giữ đúng hợp đồng HTTP `Accept-Encoding` / `Content-Encoding` / `Vary`, và thiết kế cache theo **biến thể representation**. Không phải lúc nào cũng cần bật nén ở cả Spring Boot, NGINX và CDN.

Bài học nằm trong chủ đề *Cache và nén HTTP* của Spring Boot web-runtime. Ví dụ dùng **Spring Boot 3.x, Java 17+, Spring MVC, NGINX và một CDN có hỗ trợ nén tại edge**. Các thuộc tính, khả năng Brotli hoặc Zstandard thay đổi theo server/CDN/version; hãy kiểm tra tài liệu của phiên bản triển khai trước khi đưa vào production.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Đọc và giải thích `Accept-Encoding`, `Content-Encoding`, `Vary: Accept-Encoding`, `Content-Type`, `Content-Length` và `Cache-Control`.
- Phân biệt *response compression* với *HTTP transfer framing* và *TLS*; hiểu vì sao không nên nén lại dữ liệu đã nén.
- Quyết định khi nào nén ở Spring Boot, reverse proxy hoặc CDN, trong đó public static assets khác dynamic API và response chứa dữ liệu cá nhân.
- Cấu hình `server.compression.*` trong Spring Boot 3.x và nén gzip tại NGINX khi ứng dụng trả body chưa nén.
- Phối hợp CDN cache keys với biến thể gzip/Brotli/identity; hiểu tại sao chỉ đặt `Vary` chưa đủ nếu một CDN/custom cache được cấu hình sai.
- Thực hành dùng `curl` để kiểm tra nén, cache header, body và hiệu quả truyền tải xuyên qua từng hop.
- Nhận biết các lỗi: nén hai lần, thiếu `Vary`, `Content-Length` sai, ETag không phù hợp biến thể, byte range và phản hồi nhạy cảm có nguy cơ side channel.
- Đo p95 latency, CPU, size trên đường truyền và cache hit trước khi chọn giải pháp.

## 2. Mô hình phân lớp và vị trí nén

Giả sử có một tuyến triển khai:

```text
[Spring Boot origin :8080]
    |
    | HTTP giữa origin và proxy
    v
[NGINX / Ingress / Reverse Proxy]
    |
    | HTTP(S) giữa proxy và CDN/origin shield
    v
[CDN / Edge cache]
    |
    | HTTPS tới browser
    v
[Browser / HTTP client]
```

Trong thực tế, CDN thường đứng **trước** reverse proxy theo hướng request: browser → CDN → reverse proxy → app. Hình trên mô tả **hướng response đi từ app ra browser**. Mỗi mũi tên là một chặng có thể mang dữ liệu dạng identity hoặc đã áp dụng content coding. Một CDN có thể cache representation đã mã hóa hoặc tái mã hóa cho client nếu chính sách và khả năng sản phẩm cho phép.

| Lớp | Quyền quyết định | Ưu điểm khi nén ở lớp đó | Hạn chế cần cân nhắc |
| --- | --- | --- | --- |
| Spring Boot | Biết endpoint, MIME type, ngữ cảnh nghiệp vụ | Nén response động ngay từ origin, có lợi khi đường app→proxy xa | CPU/memory của JVM, nén lặp trên mọi replica, không phải mọi connector hỗ trợ mọi coding |
| Reverse proxy (ví dụ NGINX) | Biết upstream, route, response headers | Tập trung chính sách, giảm CPU ở app, nén cho nhiều origin | Cần xử lý đúng body đã nén, cache, ETag và nội dung nhạy cảm |
| CDN / edge | Biết loại thiết bị, viewer `Accept-Encoding` và cache | Nén gần client, tái sử dụng cached objects, có thể hỗ trợ Brotli | Tính năng tùy CDN; origin/CDN cache policy phải đồng bộ, không tự sửa toàn bộ lỗi origin |
| Build pipeline cho static files | Biết asset không đổi khi build | Có thể tạo `.gz`/`.br` một lần với mức nén cao | Cần server/CDN đàm phán variant và trả header đúng; không dùng file nén cho client không hỗ trợ |

Một hệ thống tốt thường có **một “chủ chính” của quá trình nén cho mỗi response từ góc nhìn client**, với chính sách rõ ở các hop. Không đồng nghĩa mọi hop bắt buộc gửi identity: nếu app đã nén payload theo coding hợp lệ, proxy/CDN có thể **chuyển tiếp** nguyên representation đó mà không nén lại.

## 3. Nắm chính xác HTTP content negotiation

### 3.1. Client nói mình hỗ trợ gì: Accept-Encoding

Request có thể gửi:

```http
GET /api/catalog HTTP/1.1
Host: example.com
Accept-Encoding: br, gzip;q=0.8, identity;q=0.1
```

`br` là Brotli, `gzip` là GZIP; `identity` biểu thị không áp dụng content coding. `q` là trọng số ưu tiên từ 0 đến 1; `q=0` nghĩa là client không chấp nhận coding đó. Server/CDN chọn một coding hợp lệ trong khả năng của mình; không được suy rằng phải chọn `br` nếu chưa hỗ trợ Brotli. Các quy tắc khi header **vắng mặt** khác với header có giá trị rỗng hoặc chứa `identity;q=0`; tham khảo RFC 9110 thay vì viết một parser tùy tiện chỉ bằng phép `String.contains("gzip")`.

Ví dụ:

- `Accept-Encoding: gzip`: client chấp nhận gzip; origin có thể nén nếu điều kiện kích thước/MIME phù hợp.
- `Accept-Encoding: identity`: yêu cầu biểu diễn không nén; đừng gửi response với `Content-Encoding: gzip`.
- `Accept-Encoding: gzip;q=0`: gzip **không được phép** chỉ vì chuỗi có chứa chữ `gzip`.
- `Accept-Encoding: br, gzip`: client hỗ trợ cả hai; CDN có thể chọn br nếu triển khai hỗ trợ và chính sách thích hợp.
- `Accept-Encoding` không tự quyết định cacheability; việc lưu trong cache còn phụ thuộc response status và `Cache-Control`.

### 3.2. Server cho biết đã áp dụng coding gì: Content-Encoding

Response được nén có thể có:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Encoding: gzip
Vary: Accept-Encoding
Cache-Control: public, max-age=60
```

Response body ở ví dụ này là **bytes đã được gzip mã hóa**. Browser giải mã theo `Content-Encoding` trước khi cho JavaScript hoặc renderer đọc nội dung ứng dụng. Một request `curl --compressed` cũng yêu cầu những coding mà phiên bản curl hỗ trợ và **giải nén body để in ra**, nhưng vẫn cho phép xem `Content-Encoding` trong headers. Nếu chỉ dùng `curl -H 'Accept-Encoding: gzip'` rồi in body, output thô có thể nhìn như dữ liệu nhị phân.

**`Content-Type`** mô tả media type của representation khi giải mã, chẳng hạn JSON hoặc HTML; **`Content-Encoding`** mô tả phép mã hóa nội dung. `application/json` không biến thành `application/gzip` chỉ vì JSON được gzip cho vận chuyển.

### 3.3. Vary: Accept-Encoding là điều kiện cốt lõi của cache

Khi URL có thể trả về nhiều representation tùy request `Accept-Encoding`, response cần công bố:

```http
Vary: Accept-Encoding
```

Ý nghĩa: một cache tuân thủ chuẩn phải xét `Accept-Encoding` của request gốc và request mới trước khi tái sử dụng phản hồi. Cùng URL có thể tồn tại ít nhất hai biến thể:

```text
GET /app.js + Accept-Encoding: gzip
  -> Content-Encoding: gzip
  -> bytes G

GET /app.js + Accept-Encoding: identity
  -> không có Content-Encoding
  -> bytes I

G và I không có cùng byte sequence.
Cache không được nhầm G thành I.
```

Nếu cache chỉ dùng URL làm key mà bỏ qua `Vary` hoặc không chuẩn hóa encoding đúng, nó có thể phát bytes gzip cho một client chỉ chấp nhận identity. Kết quả có thể là lỗi giải nén, tải JS/CSS thất bại hoặc response không đọc được.

**Lưu ý CDN:** một số CDN có cơ chế normalize/whitelist `Accept-Encoding` và tạo cache key riêng cho gzip/Brotli; cấu hình phải theo **tài liệu sản phẩm**. Chỉ kiểm tra nhìn thấy `Vary: Accept-Encoding` ở origin **không đủ** để bảo đảm cấu hình CDN đúng. Khi một response còn vary theo `Accept-Language` hay content negotiation khác, cần xem toàn bộ cache policy để tránh cache key bùng nổ.

### 3.4. Đừng nhầm Content-Encoding với Transfer-Encoding

- `Content-Encoding: gzip`: body representation được nén; coding có ý nghĩa đến cách đọc nội dung.
- `Transfer-Encoding: chunked` trong HTTP/1.1: kỹ thuật framing để gửi body theo chunk; không đồng nghĩa gzip.
- HTTP/2/HTTP/3 dùng cơ chế framing riêng, không sử dụng `Transfer-Encoding: chunked` theo cách HTTP/1.1.
- TLS mã hóa đường truyền và cung cấp bảo mật kênh; gzip/Brotli giảm kích thước dữ liệu **trước khi truyền** ở tầng HTTP representation. Nén HTTP không thay thế TLS.

Có thể vừa có response gzip vừa dùng chunked HTTP/1.1. Ngược lại, một response chunked không có `Content-Encoding` vẫn là body identity nếu không có content coding khác.

## 4. Chọn ai nén: bốn topology thực tế

### Phương án A — Nén tại Spring Boot, proxy và CDN chuyển tiếp

```text
Boot -> (gzip bytes) -> NGINX pass-through -> CDN/cache variant -> Browser
```

Dùng khi origin cần tự nén vì đường origin→proxy/CDN tốn băng thông, response động không cache được nhưng lớn, hoặc proxy không có tính năng nén mong muốn. Spring Boot cấu hình nén, proxy không cố nén lại body đã có `Content-Encoding`. Cache ở proxy/CDN (nếu được phép) cần phân biệt các biến thể hoặc chỉ cache một representation theo contract.

Đánh đổi: CPU nén nằm ở mỗi JVM; nếu origin tạo gzip cho tất cả khách, CDN không nhất thiết tự chuyển thành Brotli. Đừng hứa rằng CDN sẽ tự recompress mọi response đã có coding; kiểm tra từng sản phẩm. Nếu edge cần Brotli còn origin chỉ có gzip, đôi khi tối ưu hơn để origin gửi identity và edge tự chọn.

### Phương án B — App trả identity, reverse proxy nén

```text
Boot identity -> NGINX gzip theo viewer Accept-Encoding -> CDN/Browser
```

Thích hợp khi muốn một chỗ quản lý policy cho nhiều ứng dụng, app đang CPU-bound, hoặc muốn giảm cấu hình nén ở từng Spring service. NGINX có thể yêu cầu upstream gửi identity bằng cách **không chuyển `Accept-Encoding` của client xuống origin**; sau đó nó gzip theo request client, dựa trên MIME type và kích thước. Đừng vô tình xóa header `Accept-Encoding` từ client gửi tới NGINX: chỉ loại header **trên hop NGINX→origin** nếu topology yêu cầu.

Khi có CDN phía trước NGINX, NGINX nhìn thấy request do CDN gửi; CDN có thể chuẩn hóa `Accept-Encoding` trên hop tới NGINX. Phải kiểm tra request thực tế và cache policy của CDN, không đoán chỉ từ header browser.

### Phương án C — App và reverse proxy trả identity, CDN nén ở edge

```text
Boot identity -> Reverse proxy identity -> CDN (br/gzip) -> Browser
```

Đây là phương án phổ biến cho **public static assets** và JSON công khai có thể cache: edge biết khả năng của viewer và có thể nén một lần gần người dùng. Đồng thời cache các biến thể phù hợp. Origin ít tốn CPU nén hơn; đổi lại đường từ origin đến CDN có thể truyền nhiều byte hơn khi cache miss. Với mạng/private origin nội vùng và CDN cache hit cao, thường đáng đánh giá đầu tiên.

Không nén ở origin không có nghĩa CDN sẽ tự nén: phải bật tùy chọn compression, chọn cache policy, MIME/size phù hợp và xác nhận thực tế. Nếu CDN không hỗ trợ một coding trên loại response đang dùng, client sẽ nhận identity hoặc coding khác hợp lệ.

### Phương án D — Precompress static assets ở build time

```text
Build JS/CSS -> app.js + app.js.gz + app.js.br
                              |
                       Edge/proxy chọn đúng variant
                              |
                           Browser
```

Dùng cho JS/CSS/HTML tĩnh có thể build và version theo hash. Nén Brotli mức cao ngay trong CI có thể cho kích thước tốt mà không đòi hỏi CPU nén ở runtime. Nhưng máy chủ phải phát đúng `Content-Encoding: br` hoặc `gzip`, giữ `Content-Type` là loại tài nguyên gốc, và chọn identity khi client không hỗ trợ. Tạo file `.br` rồi trả nó như `application/octet-stream` không giải quyết vấn đề.

NGINX có module `gzip_static` để phục vụ `.gz`, **không phải lúc nào cũng được build sẵn**; Brotli static cần module hoặc server/CDN hỗ trợ riêng. Đừng bật `gzip_static always` vô điều kiện nếu không có bước decompress cho client không hỗ trợ.

### Bảng chọn nhanh

| Loại response | Điểm nén thường nên ưu tiên | Cache policy | Cần lưu ý |
| --- | --- | --- | --- |
| JS/CSS có hash tên file | Build/CDN, hoặc NGINX static | `public, max-age` dài, `immutable` khi filename versioned | Chọn br/gzip/identity đúng viewer |
| HTML public cập nhật thường xuyên | CDN hoặc NGINX | TTL ngắn/điều kiện revalidate | ETag, Vary, purge khi cập nhật |
| JSON công khai dung lượng lớn | CDN nếu cache được; nếu không, NGINX/app | Theo dữ liệu, ví dụ `public, max-age=60` | Không cache nhầm dữ liệu theo user |
| JSON có cookie/login và dữ liệu cá nhân | App/NGINX theo chính sách bảo mật riêng; thường tránh shared cache | `private` hoặc `no-store` tùy độ nhạy | BREACH/secret reflection, Cache-Control và CDN bypass |
| SSE/streaming real-time | Thường hạn chế nén/buffering có độ trễ cao | Thường không chia sẻ cache | Latency, flush, proxy buffering |
| JPEG/PNG/WebP/AVIF, MP4, ZIP/PDF nén sẵn | Thường không gzip lại | Cache riêng theo asset | Ít lợi ích và tốn CPU; range/download |
| Payload rất nhỏ | Thường không nén | Theo nghiệp vụ | gzip header overhead, CPU lớn hơn byte tiết kiệm |

Bảng là gợi ý khởi đầu, không phải cấu hình tuyệt đối. Hãy benchmark với kích thước, loại dữ liệu, mạng, CPU, TTFB và thực tế CDN hit của hệ thống.

## 5. Spring Boot 3.x: cấu hình nén tại ứng dụng

Spring Boot 3.3 có các property:

```properties
server.compression.enabled=true
server.compression.mime-types=text/html,text/plain,text/css,application/json,application/javascript,application/xml
server.compression.min-response-size=1KB
```

Các property trong ví dụ **thay đổi cấu hình ứng dụng gốc**. Nếu chọn phương án B/C (nén ở proxy/CDN) thì đặt `server.compression.enabled=false` hoặc bỏ property vì Boot 3.3 mặc định **false**.

Theo bảng properties Spring Boot 3.3:

- `server.compression.enabled`: mặc định `false`.
- `server.compression.min-response-size`: mặc định **`2KB`**, mô tả ngưỡng theo `Content-Length`.
- `server.compression.mime-types`: mặc định gồm `text/html`, `text/xml`, `text/plain`, `text/css`, `text/javascript`, `application/javascript`, `application/json` và `application/xml`.
- `server.compression.excluded-user-agents`: danh sách user-agent bị loại khỏi nén nếu cần trong phạm vi hỗ trợ của container.

Bật thuộc tính không có nghĩa **mọi response** đều nén. Điều kiện thực tế phụ thuộc embedded server (Tomcat/Jetty/Undertow/Reactor Netty), MIME type, nội dung, kích thước, headers, khả năng client và cách streaming. Spring Boot có hỗ trợ HTTP response compression qua các embedded servers này, nhưng **không mặc định rằng property trên sẽ tạo Brotli**: hãy kiểm tra coding được runtime hiện tại hỗ trợ. Trong ví dụ Spring MVC/Tomcat, mục tiêu minh họa là gzip.

Khi chuyển sang Spring WebFlux/Reactor Netty, app có thể dùng cùng nhóm property của Boot tùy phiên bản, nhưng đường xử lý là reactive và cần đo CPU/event-loop/streaming riêng. Không trộn servlet filters của MVC với reactive handler chỉ để có nén.

## 6. Ví dụ Java 17+ chạy được: một Spring Boot origin

Ví dụ cung cấp một JSON đủ dài để thấy nén, một response ngắn và một response demo không cho cache. Dữ liệu được tạo cố định để kiểm tra, không có thông tin cá nhân hoặc secrets.

### 6.1. Tạo dự án

Dùng [Spring Initializr](https://start.spring.io/) tạo project Java 17+ với **Spring Boot 3.x**, Gradle/Groovy và dependency **Spring Web**. Trong `build.gradle` do Initializr tạo, phần dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Đây là snippet của file Gradle, **không phải `build.gradle` hoàn chỉnh**. Initializr cung cấp Boot plugin, dependency management, repositories, Java toolchain và Gradle Wrapper. Với Spring Boot 4.x cần đối chiếu starter/thuộc tính của major version đó.

Tạo cấu trúc:

```text
src/main/
├── java/demo/
│   └── CompressionDemoApplication.java
└── resources/
    └── application.properties
```

### 6.2. Java source

File `src/main/java/demo/CompressionDemoApplication.java`:

```java
package demo;

import java.time.Duration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CompressionDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CompressionDemoApplication.class, args);
    }
}

@RestController
class DemoController {

    @GetMapping(
            value = "/api/catalog",
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<String> catalog() {
        StringBuilder json = new StringBuilder("{\"items\":[");

        for (int i = 0; i < 300; i++) {
            if (i > 0) {
                json.append(',');
            }
            json.append("{\"id\":")
                    .append(i)
                    .append(",\"category\":\"books\"")
                    .append(",\"title\":\"Spring Boot Guide\"}");
        }

        json.append("]}");
        return ResponseEntity.ok()
                .cacheControl(
                        CacheControl.maxAge(Duration.ofMinutes(5))
                                .cachePublic())
                .body(json.toString());
    }

    @GetMapping(
            value = "/api/small",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    public String small() {
        return "ok";
    }

    @GetMapping(
            value = "/api/no-store",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    public ResponseEntity<String> noStore() {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body("no-store-example");
    }
}
```

Giải thích:

1. `@SpringBootApplication` ở package `demo` phát hiện `DemoController` cùng package. Chỉ class khởi động là `public`, nên một file Java chứa hai class như trên hợp lệ.
2. `catalog()` xây dựng JSON hợp lệ với 300 phần tử đơn giản, không cần database. Nội dung lặp lại có tính nén cao; endpoint này chỉ phục vụ **đo đạc cơ chế**, không phải benchmark đại diện dữ liệu production.
3. `ResponseEntity` công bố `Cache-Control: public, max-age=300` cho JSON công khai giả định. **Không** copy chính sách đó vào endpoint chứa thông tin theo người dùng.
4. `small()` cho response ngắn có thể không đáng nén do ngưỡng kích thước.
5. `noStore()` minh họa `Cache-Control: no-store`; nó chỉ điều khiển cache, **không đồng nghĩa cấm nén HTTP**. Muốn cấm transform/nén phải có chính sách riêng và kiểm tra ở mọi lớp.
6. Không tự thêm `Content-Encoding` hay `Content-Length` bằng tay; embedded server/proxy có trách nhiệm chọn và xuất đúng headers khi nén.

### 6.3. application.properties

File `src/main/resources/application.properties`:

```properties
server.port=8080

# Chỉ cho kịch bản A: Spring Boot làm nơi nén
server.compression.enabled=true
server.compression.min-response-size=1KB
server.compression.mime-types=text/plain,application/json,text/html,text/css,application/javascript
```

Đây là cấu hình origin-compression cho thử nghiệm A. Khi chuyển sang NGINX-compression của mục 8, đổi thành `server.compression.enabled=false` và **khởi động lại ứng dụng**, không bật đồng thời hai chiến lược chỉ vì muốn “nén mạnh hơn”.

### 6.4. Khởi chạy

Từ thư mục dự án:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Spring Boot sẽ chạy ở `http://localhost:8080` nếu port khả dụng. Các class cần Spring framework trên classpath nên không thể chỉ dùng `javac CompressionDemoApplication.java` đơn lẻ; Gradle Wrapper sẽ compile/chạy cùng dependencies.

### 6.5. Kiểm tra content negotiation bằng curl

Trong terminal khác, yêu cầu hỗ trợ gzip:

```bash
curl -sS -D - -o /dev/null \
  -H 'Accept-Encoding: gzip' \
  http://localhost:8080/api/catalog
```

Với curl trên Linux/macOS, bạn kỳ vọng phản hồi `200 OK` có `Content-Type: application/json`, `Cache-Control: public, max-age=300` và, nếu response đủ điều kiện và container nén, `Content-Encoding: gzip`. Header `Vary: Accept-Encoding` cần có khi representation thay đổi theo encoding; kiểm tra trên thực tế vì việc phát header tùy runtime/filter.

Yêu cầu identity:

```bash
curl -sS -D - -o /dev/null \
  -H 'Accept-Encoding: identity' \
  http://localhost:8080/api/catalog
```

Kỳ vọng response **không có** `Content-Encoding: gzip`. So sánh số byte thực sự trên wire với request gzip để đánh giá hiệu quả. Một header `Content-Length` có thể không được đưa ra trên phản hồi streaming/chunked; đừng ép có header chỉ để nén hoạt động.

Đọc nội dung với curl tự giải nén:

```bash
curl -sS --compressed http://localhost:8080/api/catalog
```

Kết quả là JSON (rất dài) với 300 phần tử. `curl --compressed` yêu cầu những coding mà bản curl được biên dịch hỗ trợ rồi giải mã body; nếu curl không hỗ trợ `br`, đừng dùng nó làm bằng chứng server không thể gửi Brotli cho browser khác.

Yêu cầu response nhỏ:

```bash
curl -sS -D - -o /dev/null \
  -H 'Accept-Encoding: gzip' \
  http://localhost:8080/api/small
```

Nội dung `ok` rất ngắn; với ngưỡng 1KB, thường không được nén. **Không chỉ dựa vào độ dài** để định nghĩa hợp đồng HTTP chính xác: runtime có thể có điều kiện khác về MIME, `Content-Length` và streaming.

Trên Windows PowerShell: dùng `curl.exe`, thay `/dev/null` bằng `NUL`, viết cả lệnh một dòng hoặc dùng cú pháp nối dòng PowerShell. Ví dụ:

```powershell
curl.exe -sS -D - -o NUL -H "Accept-Encoding: gzip" http://localhost:8080/api/catalog
```

### 6.6. Kiểm tra “nén không tự bằng cache”

```bash
curl -sS -D - -o /dev/null http://localhost:8080/api/no-store
```

Response có `Cache-Control: no-store` theo code. Dù gzip có bật toàn hệ thống, header này **không tự disable compression**; nó yêu cầu caches không lưu nội dung. Ngược lại `Cache-Control: public` không tự bắt buộc phải nén. Đây là hai quyết định độc lập: **có được lưu response không** và **response được mã hóa bằng coding nào**.

## 7. Bộ quy tắc chọn MIME, size và mức nén

### 7.1. Những loại dữ liệu thường nén tốt

Văn bản lặp lại (HTML, CSS, JS, JSON, XML, plain text, SVG text) thường có lợi từ gzip/Brotli. Nội dung đã nén như JPEG, PNG, WebP, AVIF, MP4, ZIP, nhiều PDF thường không giảm đáng kể khi gzip lần hai. Compression là một phép biến đổi; CPU tăng có thể vượt lợi ích nếu payload nhỏ hoặc không nén được.

Trong proxy/CDN, danh sách MIME phải bao phủ các content type của origin. Nếu API trả `application/problem+json` hoặc vendor JSON `application/vnd.example+json`, khả năng matching `application/json` có thể phụ thuộc server/module; test thực tế và thêm type chính xác khi cần. Với response chỉ có `application/octet-stream`, không tự gzip mọi nội dung nhị phân thiếu căn cứ.

### 7.2. Ngưỡng nén tối thiểu

Gzip có header/footer và chi phí CPU. Payload vài chục byte thường không đáng nén. Spring Boot 3.3 mặc định ngưỡng 2KB khi bật compression; NGINX có `gzip_min_length`. Không đặt cả hai ngưỡng chỉ để đạt cùng một điểm nén nếu một lớp được chỉ định là origin identity.

Cần hiểu **size trước nén** và **size sau nén** là hai đại lượng khác nhau. Ngưỡng cấu hình chọn khi nào bắt đầu nén, còn `Content-Length` (nếu được gửi) của response encoded phải phản ánh số byte thực sự được gửi theo representation tương ứng, không phải độ dài JSON/HTML ban đầu. Với streaming hoặc khi nén bắt đầu sau headers, server có thể không thể xác định kích thước mã hóa từ trước và dùng framing thích hợp.

### 7.3. Mức nén và CPU

Mức gzip cao hơn thường làm tăng CPU và độ trễ nén để tiết kiệm thêm byte, nhưng lợi ích biên giảm. Với dynamic content có p95 latency chặt, chọn mức cân bằng; với static files có thể precompress trong CI ở mức cao. Không có một “gzip level 9 luôn tốt nhất” cho mọi workload.

Đo ít nhất:

- CPU percent và thời gian nén trên từng node.
- Payload bytes trước/sau nén và tỷ lệ tiết kiệm.
- TTFB, p50/p95/p99 end-to-end latency, throughput requests/s.
- Cache hit/miss và số lần origin được gọi.
- Memory và GC ở Spring Boot nếu nén/đệm tại JVM.
- Traffic và chi phí đường mạng trên các hop có tính phí khác nhau.

Một request nhanh trên localhost không chứng minh nén tốt qua mạng di động 4G hoặc trên CPU constrained pods. Benchmark cả trường hợp tải đồng thời.

## 8. Reverse proxy NGINX: nén một lần ở proxy

Phần này minh họa **phương án B** với Spring Boot trả body identity và NGINX nén gzip theo yêu cầu của client. Cần NGINX đã cài và quyền chỉnh cấu hình; ví dụ server block đặt trong ngữ cảnh `http` của NGINX.

**Ở ứng dụng Spring Boot:** thay property bằng:

```properties
server.compression.enabled=false
```

Sau đó restart Boot. Đặt một block NGINX minh họa:

```nginx
server {
    listen 8081;
    server_name localhost;

    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_comp_level 5;
    gzip_types
        text/plain
        text/css
        application/json
        application/javascript
        application/xml;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Chỉ áp dụng trên hop NGINX -> Spring Boot.
        # Yêu cầu origin trả identity, để proxy làm bên nén.
        proxy_set_header Accept-Encoding "";
    }
}
```

Đây là **một server block**, không phải `nginx.conf` đầy đủ. Nó giả định NGINX và ứng dụng chạy cùng host; nếu NGINX trong container khác thì `127.0.0.1:8080` thường trỏ vào chính container NGINX, **không phải** Spring Boot. Trong Docker/Kubernetes cần thay upstream bằng DNS/service name và port đúng.

Những điều cần biết:

1. `gzip on` bật gzip runtime của NGINX cho response đủ điều kiện.
2. `gzip_types` bổ sung MIME types; `text/html` vốn được NGINX xử lý mặc định khi gzip bật.
3. `gzip_min_length 1024` đặt ngưỡng, được NGINX quyết định từ `Content-Length` response theo docs; nếu header thiếu, hành vi thực tế có thể khác trường hợp body length biết trước.
4. `gzip_vary on` cho phép thêm `Vary: Accept-Encoding` khi gzip/gzip_static/gunzip đang dùng.
5. `proxy_set_header Accept-Encoding ""` **xóa header trên request tới upstream**; điều đó hướng origin trả identity theo khả năng của nó. NGINX **vẫn nhìn được** `Accept-Encoding` của client/CDN ở request tới chính NGINX để quyết định gzip.
6. `gzip_comp_level 5` là mức minh họa, cần đo CPU/latency; không coi là giá trị tối ưu mặc định.
7. NGINX mặc định **không gzip lại response đã mã hóa gzip** theo cách nén gzip thông thường; tuy vậy, một tổ hợp custom filters/modules hoặc origin khai báo header sai vẫn có thể gây encode sai. Chủ động chọn một lớp nén chính giúp dễ debug.

**Lưu ý `gzip_proxied`:** tên directive dễ gây nhầm. NGINX xem request từ một proxy phía trước dựa trên `Via` request header, rồi chọn có nén các response dành cho kiểu request đó hay không (ví dụ `gzip_proxied no-cache no-store private expired auth`). Nó **không chỉ có nghĩa** “nén mọi response được lấy qua `proxy_pass`”. Chỉ bật giá trị phù hợp với chuỗi proxies và cache policy của hệ thống; không dùng `gzip_proxied any` vô điều kiện khi chưa phân tích.

### 8.1. Kiểm tra tại NGINX và so sánh với origin

Với origin `:8080` trả identity, NGINX ở `:8081`:

```bash
curl -sS -D - -o /dev/null \
  -H 'Accept-Encoding: gzip' \
  http://localhost:8081/api/catalog
```

Kỳ vọng (khi đủ điều kiện) header từ NGINX tới client chứa `Content-Encoding: gzip` và `Vary: Accept-Encoding`.

Trong khi đó gọi trực tiếp origin:

```bash
curl -sS -D - -o /dev/null \
  -H 'Accept-Encoding: gzip' \
  http://localhost:8080/api/catalog
```

Với `server.compression.enabled=false` và không có bộ lọc khác, response origin **không có** `Content-Encoding: gzip`. So sánh hai kết quả xác định lớp nào đã nén.

Sau khi sửa NGINX, kiểm tra cấu hình bằng `nginx -t` rồi reload theo phương thức quản lý phù hợp môi trường (systemd, container rollout, v.v.). Không restart ngẫu nhiên production server chỉ để thử một snippet.

### 8.2. Nếu origin đã nén thì làm gì?

Nếu chọn **phương án A**, bỏ cấu hình ép identity ở upstream và cấu hình proxy xử lý/forward đúng response encoded. Đừng nén thêm vào payload chỉ vì proxy cũng có `gzip on`. Nếu CDN muốn Brotli mà origin đã trả gzip, hãy quyết định rõ một trong ba việc:

- Chấp nhận gửi gzip đến viewer nếu nó hỗ trợ và CDN giữ đúng header.
- Để CDN/origin đàm phán các variant mà chúng thực sự hỗ trợ.
- Yêu cầu origin gửi identity để CDN chọn Brotli/gzip.

Việc “giải gzip rồi nén Brotli” là **transcoding** có thể cần CPU lớn và sửa metadata representation; không nên coi là tối ưu miễn phí hay tự diễn ra trên mọi CDN.

## 9. CDN và cache: biến thể nội dung theo Accept-Encoding

### 9.1. Cùng URL, nhiều body khác nhau

Với tài nguyên `/assets/app.4d92.js`, viewer có thể gửi:

```http
Accept-Encoding: br, gzip
```

CDN có thể trả:

```http
HTTP/2 200
Content-Type: application/javascript
Content-Encoding: br
Vary: Accept-Encoding
Cache-Control: public, max-age=31536000, immutable
```

Client khác chỉ hỗ trợ gzip có thể nhận `Content-Encoding: gzip` hoặc identity. **Không được** sử dụng lại bytes br cho client không hỗ trợ br. `immutable` chỉ thích hợp khi tên tài nguyên thực sự versioned/content-hashed; đừng gắn `immutable` dài hạn lên `/index.html` luôn được cập nhật cùng URL.

Một cache hợp lệ tính hit dựa trên URL và các điều kiện của `Vary`. Cache policy của sản phẩm CDN có thể **normalize** các Accept-Encoding options để tránh vô số key tương đương; chi tiết không giống nhau giữa các nhà cung cấp. Không tự thêm mọi request header vào cache key vì sẽ làm vỡ tỷ lệ hit.

### 9.2. Ví dụ cụ thể với Amazon CloudFront

Theo tài liệu CloudFront, để CDN hỗ trợ nén tự động có thể:

1. Bật **Compress objects automatically** trên cache behavior phù hợp.
2. Sử dụng cache policy có bật **Gzip** và **Brotli**.
3. CloudFront tự đưa encoding được hỗ trợ vào quá trình tính cache key/origin request theo thiết lập này.
4. Kiểm tra với viewer gửi `Accept-Encoding: br, gzip` và viewer chỉ gửi `gzip`, đồng thời kiểm tra cache hit thực tế.

CloudFront thường ưu tiên Brotli khi viewer hỗ trợ cả gzip và Brotli trong các điều kiện sản phẩm cho phép. Tuy nhiên, một response origin đã có `Content-Encoding` có thể không được CloudFront recompress giống response identity, và một object **đã cache trước khi bật nén** không tự nhất thiết được nén lại ngay. Hãy kiểm tra docs/behavior của phiên bản và invalidation khi thay đổi cấu hình.

Ví dụ ở đây là quy tắc thực hành, **không phải** hướng dẫn CloudFront/Terraform/CloudFormation đầy đủ. Với Cloudflare, Fastly, Azure Front Door hay CDN khác, tên setting, hỗ trợ br/zstd/gzip, cache key normalization và transforms có thể khác.

### 9.3. Public và private cache không được lẫn nhau

Nén là một việc; *được dùng chung nội dung cho nhiều người* là việc khác.

| Response | Cache-Control thường thích hợp | Hệ quả CDN |
| --- | --- | --- |
| JS/CSS hashed công khai | `public, max-age=31536000, immutable` | Cache dài, purge/version theo hash |
| Danh sách catalog public cập nhật thường xuyên | `public, max-age=60` hoặc TTL phù hợp | Có thể cache nếu policy cho phép |
| Trang/JSON chứa thông tin cá nhân | `private` hoặc `no-store` theo yêu cầu | Shared CDN không được dùng lại dữ liệu riêng |
| API có Authorization | Thường bypass shared cache, trừ thiết kế cache rõ ràng đáp ứng RFC | Không cache chỉ vì request “trông giống GET” |
| Response chứa set-cookie/user context | Chính sách đặc biệt/cẩn trọng | Tránh CDN vô tình nhân bản cookie hoặc nội dung theo user |

`Cache-Control: private` ngăn **shared caches** lưu response theo nghĩa chuẩn, nhưng browser private cache vẫn có thể lưu tùy các directive khác. `no-store` yêu cầu cache không lưu; nó phù hợp khi không muốn cả browser cache giữ body nhạy cảm. Không coi `private` và `no-store` là đồng nghĩa.

Đừng chỉ thêm `Vary: Cookie` rồi nghĩ đã an toàn khi cache nội dung cá nhân tại CDN. Vary theo Cookie có thể tạo cache cardinality khổng lồ và vẫn sai nếu hệ thống cache bỏ qua hoặc normalize cookie không đúng. Với authenticated/private responses, mặc định an toàn hơn là **bypass shared caching** trừ khi đã thiết kế chính xác sự cô lập dữ liệu.

### 9.4. Purge/invalidation và variant

Khi purge một URL CDN, phải biết sản phẩm purge **mọi variants** hay chỉ một dạng cache key. Nếu đã cache identity/gzip/br riêng, triển khai purge hoặc versioning phải làm chúng nhất quán. Assets hashed thường thuận tiện hơn purge thủ công; HTML có cùng URL thường cần TTL ngắn hoặc cơ chế revalidate hợp lý.

## 10. ETag, 304 và Content-Length khi representation thay đổi

### 10.1. ETag phải phù hợp với biến thể đã mã hóa

Ví dụ một file JS có body identity và body gzip: **bytes khác nhau**. Theo HTTP, strong validator dùng để nhận diện representation ở mức byte của dạng đã mã hóa. Không nên gán cùng **strong ETag** cho hai representation khác byte và mong byte-range/revalidation an toàn.

Minh họa:

```http
# Identity representation
Content-Type: application/javascript
ETag: "app-42-identity"
Vary: Accept-Encoding

# Gzip representation
Content-Type: application/javascript
Content-Encoding: gzip
ETag: "app-42-gzip"
Vary: Accept-Encoding
```

Một intermediary biến đổi body có thể phải sửa/loại bỏ ETag mạnh hoặc dùng cơ chế validator thích hợp. **Weak ETag** (có tiền tố `W/`) có ngữ nghĩa yếu hơn, nhưng không được giả định nó giải quyết mọi vấn đề cache key. Tốt nhất kiểm tra server/proxy/CDN tự xử lý validators thế nào thay vì tự gắn một ETag cố định vào tất cả phiên bản.

### 10.2. 304 Not Modified không có body

`304 Not Modified` giúp client/cache dùng response đã lưu nếu validator phù hợp. Khi một biến thể gzip được lưu và revalidate, metadata như `Vary`, `ETag`, cache directives phải nhất quán với representation đang xét. Không tự thêm `Content-Encoding: gzip` và một `Content-Length` của bản khác vào response 304 rồi khiến cache trộn metadata.

### 10.3. Content-Length của dữ liệu đã mã hóa

Nếu body JSON identity dài 20.000 byte nhưng gzip còn 2.000 byte, `Content-Length` của response gzip (nếu phát) phải phản ánh **2.000 byte encoded**, không phải 20.000. Nếu không biết chính xác trước khi gửi headers, server có thể bỏ Content-Length và dùng framing theo HTTP version. Tránh filter tự set Content-Length dựa trên string gốc trước khi compressor chạy.

Khi một proxy giải nén/đổi coding, nó cần bảo đảm `Content-Length`, `Content-Encoding`, validators và các metadata gắn với body được cập nhật/loại bỏ chính xác; đây là lý do dùng module nén chuẩn thay vì tự thêm header.

### 10.4. Range requests và nội dung nén

HTTP `Range: bytes=...` với representation encoded áp dụng offset trên **bytes của encoded representation**, không phải offset của text đã giải nén. Vì thế, nén/chuyển coding tùy tiện khi đang phục vụ `206 Partial Content` có thể làm hỏng cơ chế resume download. Đặc biệt cẩn thận với video, PDF, archive, download manager và CDN range caching.

Với tài nguyên cần range/resume, ưu tiên server/CDN có hỗ trợ range + content coding đúng chuẩn hoặc giữ identity khi phù hợp. Không “gzip mọi response status 206” bằng custom filter. Kiểm tra `Accept-Ranges`, `Content-Range`, `ETag` và khả năng giải mã của client thực tế.

## 11. Precompressed assets: tiết kiệm CPU nhưng cần phân phối đúng

Build pipeline có thể tạo ba file:

```text
app.4d92.js       -> identity
app.4d92.js.gz    -> gzip
app.4d92.js.br    -> Brotli
```

Một reverse proxy/CDN **được cấu hình đúng** sẽ chọn file phù hợp `Accept-Encoding`, giữ `Content-Type: application/javascript`, thêm `Content-Encoding` tương ứng và `Vary: Accept-Encoding`. Không đổi URL public thành `/app.4d92.js.br` cho tất cả client nếu server không báo encoding đúng.

NGINX có module `ngx_http_gzip_static_module` để phục vụ `.gz`:

```nginx
location /assets/ {
    root /srv/site;
    gzip_static on;
    gzip_vary on;
}
```

Đây là **snippet** cần root/path khớp với cấu trúc file thực tế và NGINX binary có module `gzip_static` (không phải build nào cũng bật). Nó tìm file `.gz` tương ứng khi client phù hợp; nếu không có bản precompressed hoặc client không hỗ trợ thì cần bản identity. Bộ xử lý `.br` là module/tính năng khác, không được bật chỉ nhờ `gzip_static on`.

**Đừng mặc định “precompressed = always smaller”**: kiểm tra file size đầu ra và có thể bỏ variant nếu lợi ích không đáng kể. Việc build trước phù hợp cho assets bất biến, ít phù hợp cho JSON theo từng user/request.

Spring Boot có resource chain cho precompressed resources (ví dụ property `spring.web.resources.chain.compressed` ở bản 3.x), nhưng nó chỉ liên quan đến tài nguyên tĩnh được resource handling quản lý. Đừng coi đó là thay thế nén động của API hoặc cache policy CDN. Chọn **một nơi phục vụ static variants** (app, proxy hoặc CDN) để tránh xung đột.

## 12. Compression và response streaming/SSE

Không phải mọi luồng dữ liệu nên tối ưu chủ yếu theo tổng byte.

Ví dụ:

- **Server-Sent Events (SSE)**: ứng dụng cần flush sự kiện với độ trễ thấp. Gzip hoặc proxy buffering có thể giữ dữ liệu chờ đủ block và khiến browser nhận event muộn.
- **Streaming JSON/NDJSON**: nén streaming có thể giảm bandwidth nhưng tăng latency, cần kiểm tra flush và backpressure.
- **Downloads/range**: nén lại có thể không hữu ích và khó phối hợp Content-Range.
- **gRPC**: dùng quy tắc nén của protocol và proxy gRPC riêng; đừng giả định header HTTP `Content-Encoding` cho JSON cũng áp dụng nguyên như vậy.
- **WebSocket**: có cơ chế per-message deflate/extension riêng, không đồng nhất với gzip toàn HTTP response body của handshake.

Với endpoint SSE, thường ưu tiên **latency ổn định và không buffering**; có thể phải loại `text/event-stream` khỏi danh sách nén và cấu hình reverse proxy/CDN bypass hoặc stream passthrough tùy sản phẩm. Đừng đặt `gzip off` cho toàn site nếu chỉ một vài route cần streaming, nhưng cũng đừng nén/đệm mọi route theo chính sách toàn cục mà không thử.

## 13. Rủi ro bảo mật: nén nội dung nhạy cảm

### 13.1. BREACH và side channel qua độ dài

HTTP response compression dưới HTTPS có thể tạo **side channel** khi cùng một response chứa **bí mật** (ví dụ CSRF token) và phần dữ liệu mà attacker có thể khiến server phản chiếu, sau đó attacker quan sát sự thay đổi độ dài response. Đây là lớp tấn công BREACH; TLS vẫn mã hóa nội dung nhưng kích thước bản mã có thể làm lộ thông tin thống kê.

Giảm thiểu tùy threat model:

- Không đưa secrets vào response nếu không cần.
- Tránh phản chiếu attacker-controlled text cạnh cùng bí mật trong một response nén.
- Tắt HTTP response compression cho **route nhạy cảm** hoặc dạng response có kết hợp secret + input không đáng tin, ở **mọi lớp có thể nén**, không chỉ Spring Boot.
- Bảo vệ CSRF, token/session/cookie, rate limiting và chính sách ứng dụng theo kiến trúc.
- Kiểm tra CDN có tự nén lại một response mà app đã cố tình để identity hay không.

`Cache-Control: no-store` **không tắt nén**. `Cache-Control: no-transform` có ngữ nghĩa chuẩn yêu cầu intermediaries không biến đổi nội dung, hữu ích khi thực sự cần chặn transform ở proxy/CDN tuân thủ chuẩn; tuy nhiên phải **kiểm thử cấu hình thực tế**. Đừng cho rằng chỉ một header tự chữa mọi cấu hình CDN.

### 13.2. Không cache public nội dung có xác thực

Nếu một API trả lời dựa trên cookie hoặc Authorization và chứa thông tin riêng, việc gắn `Cache-Control: public` chỉ để tăng cache hit là rủi ro nghiêm trọng. Trong các phản hồi nhạy cảm, `no-store` hoặc `private` cùng CDN bypass đúng thiết kế thường quan trọng hơn việc tiết kiệm thêm một vài byte nhờ nén.

### 13.3. Không tin Content-Encoding do client tùy tiện khai báo

Ở request **body** (upload), `Content-Encoding` có thể biểu thị request payload đã nén; đó là luồng riêng với response compression. Backend/proxy có thể không hỗ trợ giải nén request tự động; nếu hỗ trợ phải giới hạn kích thước **sau giải nén**, tránh decompression bomb. Đừng lấy `Accept-Encoding` của request để tự giải nén request body: nó nói client có thể nhận **response** nào, không phải body request đã mã hóa gì.

## 14. Caching và compression phải được kiểm chứng xuyên ba lớp

Một lỗi thường xuất hiện khi mỗi bộ phận tự test lớp mình:

- App test thấy gzip hợp lệ.
- NGINX test thấy response 200.
- CDN test thấy cache hit.
- Nhưng người dùng nhận response nén sai biến thể vì cache policy không xét Accept-Encoding.

Vì vậy cần một ma trận test theo **hop** và theo **kiểu client**.

### 14.1. Ma trận test tối thiểu

| Điểm gọi | Accept-Encoding | Kỳ vọng khi response đủ lớn/nén được |
| --- | --- | --- |
| Origin Boot compression enabled | `gzip` | Gzip nếu container hỗ trợ và policy match |
| Origin Boot compression disabled | `gzip` | Identity |
| NGINX gzip enabled + origin identity | `gzip` | Gzip do NGINX tạo |
| NGINX gzip enabled + origin identity | `identity` | Identity, không có Content-Encoding gzip |
| CDN có Brotli và gzip | `br, gzip` | Coding được CDN chọn hợp lệ, thường br khi policy hỗ trợ |
| CDN chỉ nhận gzip từ viewer | `gzip` | Gzip hoặc identity hợp lệ, không được trả br |
| CDN nhận identity | `identity` | Không trả body gzip/br |
| API cá nhân | `gzip` hoặc `br` | Không bị shared CDN cache; nén theo chính sách bảo mật |
| Response ngắn/mime không hỗ trợ | `gzip` | Thường identity theo ngưỡng/filter |
| SSE/streaming | Bất kỳ | Không bị gom lâu, event latency đúng mục tiêu |

Đừng kiểm tra bằng duy nhất một URL và một trình duyệt; cần test ít nhất HTML, JS/CSS, JSON lớn, JSON nhỏ, response cá nhân, 304 và download/range khi có.

### 14.2. Dùng curl giữ lại raw bytes

Để kiểm tra response gzip có thực sự là bytes nén:

```bash
curl -sS -D headers.txt -o body.bin \
  -H 'Accept-Encoding: gzip' \
  https://example.com/api/catalog
```

Mở `headers.txt`, nếu có `Content-Encoding: gzip` thì `body.bin` chứa bytes nén. Dùng `gzip -dc body.bin` trên máy có GNU gzip để giải nén; hoặc gửi request thứ hai bằng `curl --compressed` và nhận text đã giải mã:

```bash
curl -sS --compressed https://example.com/api/catalog
```

Không tự giải gzip `body.bin` nếu headers chỉ ra `identity` hoặc một coding khác như `br`. Với Windows, có thể dùng `curl.exe` và công cụ giải nén phù hợp. Cần nhớ có thể nhận HTTP 304 nếu request mang conditional headers; test body nên tránh gửi `If-None-Match` khi muốn đo bytes 200.

### 14.3. So sánh header, không chỉ nhìn body

```bash
curl -sS -I -H 'Accept-Encoding: gzip' https://example.com/app.js
curl -sS -I -H 'Accept-Encoding: identity' https://example.com/app.js
```

`-I` gửi **HEAD**; không phải mọi proxy/cache xử lý HEAD giống GET. Dùng GET với `-D - -o /dev/null` khi kiểm chứng nén thực sự vì một số server khác nhau về Content-Length, body hoặc policy với HEAD. Chú ý các header:

- `Content-Encoding`: coding cuối cùng tới client.
- `Vary`: các request headers quyết định representation.
- `Content-Type`: media type gốc.
- `Content-Length`: bytes của encoded response nếu có.
- `Cache-Control` và `Age`: cacheability và tuổi của bản cache.
- CDN-specific headers như `X-Cache`/`CF-Cache-Status` nếu vendor cung cấp: hit/miss/edge status, không nhất thiết cùng tên.
- `ETag`/`Last-Modified`: revalidation và tính nhất quán của variant.
- `Server-Timing` hoặc metrics hỗ trợ: phân biệt thời gian origin và edge khi có thể.

### 14.4. Kịch bản test hai client liên tiếp

1. Gọi `Accept-Encoding: gzip` đến CDN, lưu header và bytes.
2. Ngay sau đó gọi **cùng URL** với `Accept-Encoding: identity`.
3. Nếu CDN hit, xác nhận body thứ hai là identity và không có `Content-Encoding: gzip`.
4. Gọi lại gzip và xác nhận giải nén thành công, nội dung ứng dụng giống representation identity sau decode.
5. Nếu CDN hỗ trợ Brotli, lặp với `Accept-Encoding: br`, xác nhận không trả br cho client chỉ hỗ trợ gzip.
6. Lặp sau cache expiration/revalidation, invalidate và deploy phiên bản mới.
7. Với dữ liệu cá nhân, test hai user khác nhau và xác nhận CDN **không** dùng lại response riêng của user A cho user B.

Bước cuối là kiểm thử an toàn dữ liệu, không chỉ correctness của compression.

## 15. Quan sát hiệu năng và cách phân tích số liệu

### 15.1. Chỉ số cần biết ở từng chặng

| Metric | Cách hiểu |
| --- | --- |
| Uncompressed response bytes | Tổng bytes payload logic trước nén |
| Encoded response bytes | Bytes thực trên wire của content coding |
| Compression saving % | `(1 - encoded/original) × 100%` nếu original > 0 |
| App CPU / proxy CPU / edge costs | Lớp nào gánh công nén |
| CDN cache hit ratio | Tỷ lệ response phục vụ từ edge, bị ảnh hưởng bởi variant keys |
| p95/p99 TTFB | Thời gian tới byte đầu; có thể tăng vì buffering |
| p95/p99 total time | Thời gian hoàn tất response của client |
| Origin bandwidth | Bytes giữa app/proxy/CDN, không giống bandwidth tới viewer |
| 4xx/5xx / decode failures | Vấn đề từ negotiation, cache hoặc server |

Ví dụ đo được: 100 KB JSON identity, 18 KB gzip, 15 KB br. Gzip tiết kiệm 82%, br tiết kiệm 85% so với identity. **Đây là ví dụ số học, không phải benchmark phổ quát.** Nếu CPU để tạo br quá cao hoặc CDN đã hit 99%, kết luận nén br tại Spring Boot cho mỗi request có thể kém hơn nén ở edge.

### 15.2. Đo tại chỗ bằng curl

Dùng curl để xem thời gian và tải xuống:

```bash
curl -sS -o /dev/null \
  -w 'code=%{http_code} download=%{size_download}B total=%{time_total}s\n' \
  -H 'Accept-Encoding: gzip' \
  https://example.com/api/catalog
```

`size_download` đo bytes body tải xuống theo góc nhìn curl/libcurl và có thể khác dữ liệu ứng dụng đã giải nén; xác nhận chế độ curl và body thực tế. `time_total` là end-to-end một request duy nhất; muốn p95/p99 cần nhiều mẫu có kiểm soát, không rút kết luận từ một lần chạy.

Trước khi so sánh, giữ ổn định route, TLS handshake reuse/keep-alive, địa lý edge, cache hit/miss, concurrency, kích thước content và phiên bản server. Phân biệt **cache hit nhanh** với **compression giảm size** vì hai yếu tố có thể che tác động của nhau.

### 15.3. Nên triển khai theo thứ tự nào?

- **Baseline:** ghi headers/byte size/latency/CPU và cache hit khi chưa sửa.
- **Chọn owner:** mỗi nhóm route public/private/static/dynamic định rõ lớp nén.
- **Bật nén tại một lớp:** app hoặc NGINX hoặc CDN, không đồng thời bật vô thức.
- **Kiểm tra HTTP correctness:** Accept-Encoding variants, Vary, status, Content-Type, ETag, 304, 206/range.
- **Kiểm tra bảo mật:** private responses bypass shared cache; route có secret reflection không bị nén nguy hiểm.
- **Đo tải:** CPU/bandwidth/TTFB/p95/p99, so sánh mạng gần và xa.
- **Rollout theo canary:** quan sát decode errors/cache hit trước khi bật rộng.
- **Giữ rollback:** có thể tắt compression ở lớp vừa bật mà không làm app/CDN khác sinh metadata sai.

## 16. Những lỗi phổ biến và hướng khắc phục

| Hiện tượng | Khả năng nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `Content-Encoding: gzip` nhưng browser không đọc được | Body không phải gzip, body bị mã hóa hai lần hoặc bytes bị cắt | Kiểm tra raw bytes, proxy transformations, Content-Length |
| Client chỉ gửi `identity` nhưng nhận gzip | Proxy/CDN bỏ qua Accept-Encoding hoặc cache key sai | Sửa negotiation và variant cache |
| CDN cache hit cao nhưng JS/CSS lỗi ngẫu nhiên | `Vary` thiếu, cache variant bị trộn | Kiểm tra `Vary: Accept-Encoding` và CDN cache policy |
| Compression đã bật mà response không gzip | MIME không match, payload nhỏ, không có request hỗ trợ, response status/connector khác | Xem property, Content-Type, Accept-Encoding, actual bytes |
| API response 2KB nhưng gzip không xuất hiện | Ngưỡng, Content-Length hoặc container/streaming | Test với body lớn hơn và header chính xác |
| Origin có gzip, NGINX gzip on nhưng size không giảm thêm | NGINX thường không gzip lại body đã gzip | Chỉ định một điểm nén, đo CPU thay vì kỳ vọng “nén hai lần” |
| p95 TTFB tăng sau bật nén | Buffering, CPU nén hoặc resource contention | Giảm mức nén, nén ở edge, loại SSE |
| 304/ETag hoạt động sai | Validators không gắn đúng variant | Tạo/mapping ETag phù hợp, giữ Vary và thử revalidation |
| Download resume lỗi sau nén | Range của encoded vs identity representation | Kiểm tra 206/Content-Range, không biến đổi tùy tiện |
| Private data xuất hiện ở user khác | Cache shared nhầm authenticated response | Bypass CDN shared cache, sửa Cache-Control và purge |
| `no-store` nhưng response vẫn gzip | `no-store` không cấm compression | Dùng chính sách nén riêng/no-transform khi cần |
| CPU của từng Spring pod tăng sau bật gzip | Origin làm công nén cho mỗi request | Cân nhắc proxy/CDN hoặc precompression |
| Brotli không được chọn dù browser hỗ trợ | CDN/module không bật, origin gửi sẵn gzip hoặc cache cũ | Xem edge policy và cách CDN xử lý encoded origin |
| Cache hit giảm sau bật Vary | Quá nhiều encoding/header variants | Dùng normalization theo CDN, tránh vary không cần thiết |
| File `.gz` được tải xuống như binary file | Server chưa phát Content-Encoding/Content-Type hợp lệ | Cấu hình precompressed resource serving đúng |

## 17. Bài tập tự kiểm tra

**Bài 1 — cùng URL, hai client.** Client A gửi `Accept-Encoding: gzip`; client B chỉ gửi `identity`. CDN cache chung một body gzip theo URL. Sai ở đâu?  
**Đáp án:** Cache key/`Vary` không xét biến thể representation; B không chấp nhận gzip. Cần sửa content negotiation và cache variant policy.

**Bài 2 — đặt gzip ở đâu?** Một website công khai có JS/CSS hashed ít đổi và CDN hit cao. Nên bật gzip trên mọi Spring Boot pod?  
**Gợi ý:** Không nhất thiết. Ưu tiên precompress assets ở build hoặc nén tại CDN/edge, thử cache policy và đo băng thông/CPU. Origin gzip có thể không mang nhiều lợi ích khi hầu hết request được CDN phục vụ.

**Bài 3 — API chứa dữ liệu user.** `GET /account` trả thông tin cá nhân, dùng cookie để xác thực. Có nên đặt `Cache-Control: public, max-age=3600` chỉ vì CDN sẽ nén nhanh?  
**Đáp án:** Không. Quyết định nén và caching độc lập; không cho shared cache dùng lại response cá nhân. Cần policy `private`/`no-store` và CDN bypass theo yêu cầu.

**Bài 4 — Content-Length.** JSON identity dài 12.000 bytes, gzip còn 1.900 bytes, filter tự đặt `Content-Length: 12000` trên response encoded. Có hợp lệ?  
**Đáp án:** Không. Content-Length của encoded representation nếu được phát phải phản ánh số byte thực sự gửi. Để server/proxy compression module quản lý.

**Bài 5 — ETag.** Hai variant identity và gzip khác bytes nhưng cùng strong ETag. Có ổn?  
**Đáp án:** Không phù hợp ngữ nghĩa strong validator cho encoded representations khác nhau. Phải quản lý validators theo representation hoặc dùng cơ chế phù hợp với intermediary; vẫn cần `Vary`.

**Bài 6 — no-store.** Một response có `Cache-Control: no-store` nhưng NGINX vẫn gzip body. Đây có phải NGINX vi phạm `no-store`?  
**Đáp án:** Không. `no-store` điều khiển caching, không có nghĩa cấm response compression. Nếu muốn cấm transform, áp dụng chính sách nén phù hợp và xem `no-transform`.

**Bài 7 — streaming.** Sau khi bật gzip ở ingress, SSE nhận event sau từng cụm lớn thay vì thời gian thực. Kiểm tra gì?  
**Đáp án:** Buffering/compression flush của ingress/CDN, MIME type, route bypass, và tính chất streaming; đừng chỉ tăng timeout vì nguyên nhân có thể là dữ liệu bị giữ trong compressor/buffer.

**Bài 8 — NGINX header.** Tại sao dùng `proxy_set_header Accept-Encoding "";` ở hop NGINX→Boot trong phương án B?  
**Đáp án:** Để origin ưu tiên trả identity, giữ NGINX là lớp nén được chọn. Header của viewer tới NGINX vẫn dùng để NGINX quyết định gzip; cần kiểm tra các reverse proxies/CDN phía trước thay đổi header thế nào.

**Bài 9 — nén hơn bằng hai lần.** Spring Boot đã gửi `Content-Encoding: gzip`. Bật gzip trong CDN để “nén thêm” có phải tối ưu hợp lý?  
**Đáp án:** Thông thường không. Cần pass-through, transcode đúng contract nếu thật sự cần, hoặc đổi owner nén sang edge; nén dữ liệu đã nén có thể tốn CPU và không giảm size.

**Bài 10 — Brotli và origin.** Browser hỗ trợ br/gzip, nhưng CDN chỉ nhận gzip từ origin. Có thể khẳng định browser luôn được br không?  
**Đáp án:** Không. Phụ thuộc CDN có transcode hoặc tự nén response identity, cache policy, MIME/size và cached object; phải đo headers ở browser.

## 18. Checklist khi đưa vào production

- [ ] Đã phân nhóm URL thành public static, public dynamic, private/authenticated, streaming và already-compressed binaries.
- [ ] Đã xác định lớp nén chính cho từng nhóm: Boot, NGINX, CDN hoặc build.
- [ ] Chỉ bật `server.compression.enabled` khi Spring Boot thực sự được giao nhiệm vụ nén.
- [ ] MIME types, ngưỡng và thuật toán đã được kiểm tra trên runtime/version thực tế.
- [ ] Proxy không nén lại body encoded không kiểm soát và không làm mất/sai `Content-Encoding`.
- [ ] `Vary: Accept-Encoding` hiện diện khi representation thay đổi theo client negotiation.
- [ ] CDN cache policy phân biệt/normalize variants đúng; không xem URL là cache key duy nhất khi coding khác nhau.
- [ ] Không cache shared dữ liệu cá nhân/authenticated responses sai policy; cookies và Authorization được kiểm tra.
- [ ] `Content-Length`, `ETag`, 304/206/range, `Content-Type` vẫn nhất quán qua các lớp.
- [ ] Không nén lãng phí các tệp vốn đã nén; static hashed assets có cache lifetime/versioning hợp lý.
- [ ] SSE/streaming được đo về buffering/flush latency; các route nhạy cảm được đánh giá rủi ro BREACH.
- [ ] Thử gzip, br (khi có), identity và client không hỗ trợ nén với cùng URL trên từng hop.
- [ ] Đã test cache hit/miss, cache invalidation và rolling deployment nhiều phiên bản assets.
- [ ] Đã đo bytes tiết kiệm, CPU, p95/p99 TTFB, tổng latency, edge hit ratio và lỗi decode trước/sau.
- [ ] Có khả năng rollback nén ở một lớp mà không làm mất tính đúng đắn HTTP ở lớp khác.

## Tài liệu chính thức

1. [Spring Boot 3.3 — Common Application Properties / Server Compression](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
2. [Spring Boot 3.3 — Web Server Compression](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
3. [NGINX — ngx_http_gzip_module](https://nginx.org/en/docs/http/ngx_http_gzip_module.html)
4. [NGINX — Compression and Decompression](https://docs.nginx.com/nginx/admin-guide/web-server/compression/)
5. [NGINX — gzip_static module](https://nginx.org/en/docs/http/ngx_http_gzip_static_module.html)
6. [Amazon CloudFront — Serve compressed files](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/ServingCompressedFiles.html)
7. [RFC 9110 — HTTP Semantics: Accept-Encoding, Content-Encoding, Vary, Range](https://www.rfc-editor.org/rfc/rfc9110)
8. [RFC 9111 — HTTP Caching: Vary, Cache-Control, no-transform](https://www.rfc-editor.org/rfc/rfc9111)

**Kết luận:** nén HTTP hiệu quả không có nghĩa “bật gzip ở mọi nơi”. Hãy chọn **đúng lớp nén**, giữ content negotiation/metadata nhất quán, quản lý cache theo **biến thể encoding** và tách rõ dữ liệu công khai với dữ liệu riêng tư. Một cấu hình đơn giản, đo được và đúng chuẩn thường tốt hơn một chuỗi biến đổi nhiều lớp khó kiểm soát.
