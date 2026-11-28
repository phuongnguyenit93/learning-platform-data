# Giới hạn HTTP/1.1, nội dung tĩnh và việc lựa chọn công cụ khác khi cần HTTPS hoặc xử lý ứng dụng

## 1. Vai trò thực tế của jwebserver

Từ **Java 18**, JDK cung cấp **Simple Web Server** qua lệnh `jwebserver`. Đây là máy chủ HTTP tối giản để phục vụ nhanh một cây thư mục trong quá trình phát triển, thử nghiệm và gỡ lỗi. Công cụ vẫn có trong JDK hiện đại, bao gồm JDK 27.

Lệnh `jwebserver` được thiết kế cho một mục đích hẹp: nhận request HTTP/1.1 và trả các tệp tĩnh trong document root. Khi chạy, server có thể:

- Trả nội dung một tệp khi URL ánh xạ tới tệp đó.
- Trả tệp index khi URL trỏ tới thư mục có index.
- Sinh directory listing khi thư mục không có index.
- Nhận request GET và HEAD.
- Tự chọn MIME type từ bảng tích hợp và ghi log request.

Công cụ không cung cấp HTTPS, HTTP/2, HTTP/3, xử lý nội dung động, đăng nhập, session, truy cập cơ sở dữ liệu hoặc các quy trình nghiệp vụ. Đây là giới hạn thiết kế có chủ ý, không phải một cấu hình cần bật thêm.

Ví dụ, khi muốn xem nhanh website tĩnh trong thư mục `public`:

```sh
jwebserver -d ./public -p 8000
```

Mở:

```text
http://127.0.0.1:8000/
```

Lệnh này đủ cho việc xem HTML, CSS, JavaScript, ảnh và các tài nguyên tĩnh trong lúc phát triển.

> **Phạm vi sử dụng:** Oracle mô tả Simple Web Server dành cho prototyping, testing và debugging. Tài liệu JDK 27 cũng xác nhận chỉ HTTP/1.1 được hỗ trợ; HTTP/2 và HTTPS không được hỗ trợ. Không xem `jwebserver` là máy chủ production.

## 2. HTTP/1.1 only có ý nghĩa gì?

HTTP là giao thức mà client và server dùng để trao đổi request/response. `jwebserver` chỉ hỗ trợ HTTP/1.1.

Điều đó có nghĩa client có thể gửi request HTTP/1.1 như:

```http
GET /index.html HTTP/1.1
Host: 127.0.0.1:8000
```

Server trả status, headers và nội dung tệp theo HTTP/1.1.

Các phiên bản giao thức khác có đặc điểm riêng:

| Giao thức | Đặc điểm khái quát | jwebserver |
| --- | --- | --- |
| HTTP/1.1 | Giao thức request/response phổ biến, có thể tái sử dụng kết nối. | Có. |
| HTTP/2 | Có multiplexing trên một kết nối, nén header và framing nhị phân. | Không hỗ trợ. |
| HTTP/3 | HTTP chạy trên QUIC, sử dụng UDP và TLS tích hợp trong QUIC. | Không hỗ trợ. |
| HTTPS | HTTP được bảo vệ bằng TLS. HTTPS là HTTP qua kết nối TLS, không phải một phiên bản HTTP riêng. | Không hỗ trợ trong CLI. |

HTTP/2 và HTTP/3 có thể cải thiện hiệu quả kết nối trong những môi trường phù hợp, nhưng không phải mọi website đều cần chúng. Nếu yêu cầu triển khai đòi hỏi một phiên bản giao thức cụ thể, hãy chọn server hoặc gateway có công bố hỗ trợ phiên bản đó.

Không thể biến `jwebserver` thành HTTP/2 hoặc HTTP/3 server bằng cách đổi cổng, thêm tham số bind hay sửa tên URL.

## 3. Nội dung tĩnh khác nội dung động

### 3.1. Tệp tĩnh

Tệp tĩnh là tài nguyên đã tồn tại trên file system trước khi request đến server. Ví dụ:

```text
public/
├── index.html
├── about.html
├── css/
│   └── site.css
├── js/
│   └── app.js
└── images/
    └── logo.png
```

Khi client yêu cầu `/css/site.css`, server đọc tệp tương ứng và trả byte của tệp. Nội dung không được tính toán lại theo từng người dùng hoặc theo dữ liệu request.

Các tài nguyên thường được phục vụ như tệp tĩnh:

- HTML, CSS và JavaScript đã được build.
- Hình ảnh, font, video và tài liệu tải xuống.
- Tệp JSON hoặc dữ liệu mẫu đã chuẩn bị sẵn.
- Tài liệu hướng dẫn và trang demo.

### 3.2. Nội dung động

Nội dung động được tạo hoặc xử lý khi request đến. Ví dụ:

- `GET /api/orders/123` đọc dữ liệu đơn hàng từ database.
- `POST /login` xác minh thông tin đăng nhập.
- `POST /files` kiểm tra và lưu tệp người dùng tải lên.
- `GET /reports?month=11` tính toán báo cáo dựa trên tham số.
- Một trang cá nhân hóa nội dung theo người dùng hiện tại.

Những hành vi này cần code ứng dụng, kiểm tra request, truy cập dữ liệu và tạo response theo kết quả xử lý. `jwebserver` không chạy mã Java hoặc script phía server khi client yêu cầu một URL; nó chỉ trả tài nguyên tĩnh.

### 3.3. JavaScript chạy trong trình duyệt không biến server thành dynamic server

Một website có thể có JavaScript chạy trong trình duyệt, gọi API từ xa và cập nhật giao diện. Điều đó không có nghĩa `jwebserver` xử lý logic ứng dụng ở phía server.

Ví dụ:

```html
<script>
  fetch("/api/products")
    .then(response => response.json())
    .then(products => renderProducts(products));
</script>
```

`jwebserver` có thể phục vụ tệp HTML/JavaScript chứa đoạn code trên. Nhưng khi trình duyệt gọi `/api/products`, server chỉ tìm một tệp tĩnh tương ứng. Nó không tự truy vấn database hoặc tạo JSON động.

Muốn website có API động, cần có backend xử lý request hoặc một dịch vụ API khác.

## 4. Các giới hạn cần nhận biết trước khi chọn jwebserver

| Nhu cầu | jwebserver có đáp ứng? | Giải thích |
| --- | --- | --- |
| Xem website tĩnh trên máy cá nhân | Có. | Đây là mục đích chính. |
| Phục vụ HTML/CSS/JS đã build | Có. | Các tệp được trả như tài nguyên tĩnh. |
| Duyệt directory listing | Có. | Server sinh trang HTML nếu thư mục không có index. |
| Nhận GET và HEAD | Có. | Đây là hai method được hỗ trợ. |
| Nhận POST để đăng nhập | Không. | Không có handler nghiệp vụ mặc định. |
| Upload, sửa hoặc xóa tệp qua HTTP | Không. | Không có API ghi dữ liệu. |
| Truy vấn database | Không. | Không có lớp nghiệp vụ hoặc kết nối dữ liệu. |
| Dùng HTTPS/TLS trong CLI | Không. | CLI không có tùy chọn chứng chỉ hoặc TLS. |
| Dùng HTTP/2 hoặc HTTP/3 | Không. | CLI chỉ hỗ trợ HTTP/1.1. |
| Xác thực, session, phân quyền người dùng | Không. | Không có cơ chế tài khoản hoặc session. |
| Cân bằng tải, rate limit, reverse proxy | Không. | Cần thành phần hạ tầng khác. |

Một điểm cần phân biệt: JDK có API HTTP server rộng hơn lệnh CLI. API `HttpServer` và `HttpsServer` có thể được dùng để viết server nhúng và đăng ký handler. Nhưng đó là lập trình ứng dụng bằng API, không phải một tùy chọn cấu hình của `jwebserver`.

## 5. Khi nào vẫn nên dùng jwebserver?

Chọn `jwebserver` khi cần một công cụ ngắn gọn, ít cấu hình và chỉ cần phục vụ nội dung tĩnh.

Các tình huống phù hợp:

1. Xem nhanh website frontend đã build.
2. Kiểm tra HTML, CSS, ảnh và đường dẫn tương đối.
3. Thử nghiệm MIME type và response headers.
4. Phục vụ tài liệu hoặc dữ liệu mẫu trong một buổi làm việc nội bộ.
5. Kiểm tra hành vi GET/HEAD và directory listing.
6. Tái hiện một lỗi liên quan đến tài nguyên tĩnh trong môi trường local.
7. Chạy một server tạm thời để thiết bị khác trong mạng thử nghiệm truy cập, khi đã hiểu rõ phạm vi truy cập.

Ví dụ:

```sh
jwebserver -b 127.0.0.1 -p 8000 -d ./dist -o info
```

Lệnh trên phục vụ thư mục build `dist` tại loopback. Mặc định bind của CLI cũng là loopback và cổng mặc định là 8000.

Nếu chỉ cần xem nội dung từ chính máy đang phát triển, hãy giữ bind address loopback. Khi bind tới `0.0.0.0` hoặc `::`, server lắng nghe trên mọi network interface và có thể truy cập từ các máy khác trong mạng. Tài liệu Oracle cảnh báo chỉ dùng cách này khi chắc chắn server không làm lộ dữ liệu nhạy cảm.

## 6. Khi cần HTTPS cho website tĩnh

HTTPS bảo vệ dữ liệu trên đường truyền bằng TLS. Nó giúp client xác minh danh tính server và bảo vệ tính bí mật/toàn vẹn của dữ liệu trong kết nối.

CLI `jwebserver` không hỗ trợ HTTPS. Khi cần phục vụ website tĩnh qua HTTPS, có hai hướng phổ biến.

### 6.1. Dùng web server hoặc reverse proxy có TLS

Một web server chuyên dụng có thể phục vụ trực tiếp tệp tĩnh và quản lý TLS. Reverse proxy cũng có thể nhận HTTPS ở phía client, sau đó chuyển tiếp request tới một dịch vụ phía sau.

Ví dụ về sơ đồ:

```text
Browser
   |
   | HTTPS
   v
Reverse proxy / web server
   |  - TLS certificate
   |  - HTTP policy
   |  - static file delivery
   |
   v
Application server (nếu có)
```

Các công cụ thường gặp:

- **Caddy:** phù hợp khi muốn cấu hình TLS tự động trong nhiều trường hợp triển khai.
- **Nginx:** thường dùng làm web server, reverse proxy và điểm kết thúc TLS.
- **Apache HTTP Server:** có thể phục vụ tệp tĩnh và cấu hình TLS/reverse proxy.

Đây là các ví dụ để lựa chọn theo môi trường vận hành. Cần kiểm tra yêu cầu chứng chỉ, DNS, tự động gia hạn, cấu hình TLS và cách triển khai của tổ chức.

Với website tĩnh đơn giản, web server có TLS có thể phục vụ thư mục build trực tiếp. Không cần chạy `jwebserver` ở phía sau nếu không có nhu cầu cụ thể.

### 6.2. Reverse proxy chuyển TLS tới backend HTTP

Một kiến trúc khác là:

```text
Browser
   |
   | HTTPS
   v
Reverse proxy
   |  TLS termination
   |
   | HTTP nội bộ
   v
Backend
```

Trong mô hình này, client kết nối HTTPS tới reverse proxy. Proxy giải mã TLS và chuyển request tới backend qua một kết nối HTTP nội bộ.

Nếu backend nằm cùng máy hoặc trong một mạng riêng được kiểm soát, HTTP nội bộ có thể là lựa chọn phù hợp. Nếu lưu lượng đi qua mạng không tin cậy hoặc ranh giới mạng, cần đánh giá mã hóa giữa các hop và cấu hình TLS nội bộ khi cần.

Không nên hiểu rằng chỉ cần reverse proxy bật HTTPS là toàn bộ đường truyền phía sau cũng tự động được mã hóa.

### 6.3. Kiểm thử HTTPS đúng cách

Khi đã cấu hình server với chứng chỉ hợp lệ, kiểm tra bằng:

```sh
curl -I https://example.test/
```

Nếu đang dùng CA nội bộ hoặc CA thử nghiệm, cung cấp CA tin cậy cho curl:

```sh
curl --cacert ./dev-ca.pem -I https://example.test/
```

Tránh dùng tùy chọn `-k` hoặc `--insecure` như một cách cấu hình lâu dài. Tùy chọn này bỏ qua xác minh chứng chỉ và có thể che giấu lỗi xác thực server.

## 7. Khi muốn giữ Java và tự xây dựng HTTPS server

JDK có module `jdk.httpserver` cung cấp API `HttpServer`, `HttpsServer`, `HttpHandler` và các lớp cấu hình liên quan.

- `HttpServer` cung cấp server HTTP nhúng.
- `HttpsServer` mở rộng `HttpServer` để hỗ trợ HTTPS.
- `HttpsConfigurator` cấu hình SSL/TLS cho các kết nối HTTPS.
- `HttpHandler` xử lý request và tạo response.

Đây là lựa chọn khi ứng dụng Java cần một HTTP/HTTPS server nhỏ được nhúng trong tiến trình của chính ứng dụng. Nó cho phép bạn kiểm soát route và xử lý request bằng Java code.

### 7.1. HttpsServer cần SSLContext

Không thể chỉ đổi URL từ `http://` thành `https://` rồi mong `HttpServer` tự bật TLS.

Một `HttpsServer` cần được gắn `HttpsConfigurator`, và configurator này sử dụng `SSLContext` để thiết lập TLS.

`SSLContext` phía server thường được khởi tạo với key material chứa private key và certificate chain của server. Ví dụ dưới đây dùng một tệp PKCS12 tên `server.p12` và lấy mật khẩu từ biến môi trường.

### 7.2. Ví dụ HTTPS server nhúng tối giản

```java
import com.sun.net.httpserver.HttpsConfigurator;
import com.sun.net.httpserver.HttpsServer;

import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;

public class EmbeddedHttpsServer {
    public static void main(String[] args) throws Exception {
        String passwordValue = System.getenv("KEYSTORE_PASSWORD");
        if (passwordValue == null || passwordValue.isBlank()) {
            throw new IllegalStateException(
                "Set the KEYSTORE_PASSWORD environment variable first.");
        }
        char[] password = passwordValue.toCharArray();

        KeyStore keyStore = KeyStore.getInstance("PKCS12");
        try (var input = Files.newInputStream(Path.of("server.p12"))) {
            keyStore.load(input, password);
        }

        KeyManagerFactory keyManagers = KeyManagerFactory.getInstance(
            KeyManagerFactory.getDefaultAlgorithm());
        keyManagers.init(keyStore, password);

        SSLContext sslContext = SSLContext.getInstance("TLS");
        sslContext.init(
            keyManagers.getKeyManagers(),
            null,
            new SecureRandom());

        HttpsServer server = HttpsServer.create(
            new InetSocketAddress("127.0.0.1", 8443), 0);

        server.setHttpsConfigurator(new HttpsConfigurator(sslContext));

        server.createContext("/api/hello", exchange -> {
            if (!"GET".equals(exchange.getRequestMethod())) {
                exchange.getResponseHeaders().set("Allow", "GET");
                exchange.sendResponseHeaders(405, -1);
                exchange.close();
                return;
            }

            byte[] body = "Xin chào từ HttpsServer"
                .getBytes(StandardCharsets.UTF_8);

            exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");

            exchange.sendResponseHeaders(200, body.length);
            try (var output = exchange.getResponseBody()) {
                output.write(body);
            }
        });

        server.start();
    }
}
```

Trong ví dụ:

1. Tệp `server.p12` chứa private key và certificate chain của server.
2. `KeyManagerFactory` tạo key managers từ keystore.
3. `SSLContext` khởi tạo cấu hình TLS.
4. `HttpsConfigurator` gắn SSL context vào server.
5. `createContext` đăng ký route `/api/hello`.
6. Handler xử lý GET và trả văn bản UTF-8.

Đây là ví dụ học API, không phải một cấu hình production hoàn chỉnh. Ứng dụng thực tế cần quản lý vòng đời chứng chỉ, bảo vệ private key, xác thực và phân quyền, giới hạn kích thước request, xử lý lỗi, log, timeout, concurrency và giám sát.

### 7.3. Tạo keystore thử nghiệm

Có thể tạo một keystore PKCS12 cho môi trường local bằng `keytool`:

```sh
keytool -genkeypair \
  -alias local-server \
  -keyalg RSA \
  -keysize 3072 \
  -storetype PKCS12 \
  -keystore server.p12 \
  -validity 30 \
  -dname "CN=localhost" \
  -ext "SAN=dns:localhost,ip:127.0.0.1"
```

Lệnh trên tạo chứng chỉ tự ký cho thử nghiệm. Trình duyệt hoặc curl sẽ không tự tin cậy chứng chỉ này nếu CA chưa được tin cậy. Với triển khai thật, dùng chứng chỉ được cấp bởi CA phù hợp và bảo vệ private key.

Mật khẩu keystore trong ví dụ được đọc từ biến môi trường `KEYSTORE_PASSWORD`. Không commit mật khẩu hoặc private key vào source control.

## 8. Khi cần xử lý ứng dụng động

Nếu ứng dụng cần endpoint, validation, database, authentication hoặc workflow nghiệp vụ, có thể viết handler bằng API JDK hoặc chọn framework ứng dụng.

### 8.1. Dùng HttpServer/HttpsServer cho dịch vụ nhúng nhỏ

API `HttpServer` và `HttpsServer` cho phép đăng ký các `HttpHandler` theo context path. Một handler có thể:

- Đọc method, URI, request headers và body.
- Kiểm tra dữ liệu đầu vào.
- Gọi service hoặc database.
- Chọn status và response headers.
- Gửi response body.

Đây là hướng phù hợp cho một endpoint nội bộ hoặc một embedded service nhỏ có yêu cầu đơn giản. Bạn phải tự thiết kế các thành phần như authentication, authorization, validation, error mapping, logging, request limits và lifecycle.

API `com.sun.net.httpserver` có thiết kế tối giản. Tài liệu module JDK 27 nói rõ API/SPI được thiết kế để hỗ trợ HTTP server tối thiểu và ngữ nghĩa HTTP đơn giản; implementation mặc định không hướng tới một HTTP server đầy đủ tính năng hoặc hiệu năng cao.

### 8.2. Dùng framework ứng dụng cho backend thực tế

Khi ứng dụng có nhiều route và nhiều thành phần nghiệp vụ, framework thường giúp tổ chức code và tích hợp hạ tầng tốt hơn.

Một số ví dụ hiện hành:

- **Spring Boot:** xây dựng ứng dụng web/API với hệ sinh thái Spring và embedded server.
- **Quarkus:** xây dựng dịch vụ Java tối ưu cho cloud/container và nhiều kiểu triển khai.
- **Micronaut:** xây dựng ứng dụng và microservice Java với dependency injection và HTTP server tích hợp.

Chọn framework dựa trên yêu cầu runtime, đội ngũ, hệ sinh thái, cách triển khai và vận hành. Không nên chọn framework chỉ vì nó có thể trả một response HTTP; hãy cân nhắc vòng đời ứng dụng, bảo mật, kiểm thử, metrics, tracing và khả năng bảo trì.

### 8.3. Phân biệt file server với application server

| Tiêu chí | jwebserver | HttpServer/HttpsServer API | Framework ứng dụng |
| --- | --- | --- | --- |
| Mục tiêu | Phục vụ tệp tĩnh nhanh. | Tự xây dựng server nhúng nhỏ. | Tổ chức và vận hành ứng dụng web/API. |
| Nội dung tĩnh | Có. | Có thể gắn file handler. | Thường có static resource support hoặc tích hợp web server. |
| Route động | Không. | Có qua HttpHandler. | Có hệ thống routing/controller. |
| HTTPS | Không trong CLI. | Có qua HttpsServer. | Tùy server/runtime và cấu hình. |
| Validation/authentication | Không. | Tự triển khai. | Có cơ chế và tích hợp phong phú hơn. |
| Database/business logic | Không. | Tự viết trong handler/service. | Có hệ sinh thái tích hợp. |
| Phù hợp production | Không. | Chỉ khi tự xây dựng và vận hành đầy đủ, đúng giới hạn. | Thường phù hợp hơn khi được cấu hình và vận hành đúng cách. |

## 9. Kiến trúc lựa chọn theo nhu cầu

Sơ đồ sau thể hiện cách chọn công cụ:

```text
Bạn cần phục vụ gì?
        |
        +-- Chỉ là website/tệp tĩnh để thử nhanh?
        |        |
        |        +-- Có --> jwebserver
        |
        +-- Tệp tĩnh cần HTTPS/public?
        |        |
        |        +-- Có --> Web server / reverse proxy có TLS
        |
        +-- Dịch vụ Java nhúng nhỏ cần HTTPS?
        |        |
        |        +-- Có --> HttpsServer + SSLContext
        |
        +-- Backend có route, auth, database, workflow?
        |        |
        |        +-- Có --> Framework ứng dụng hoặc server phù hợp
        |
        +-- Cần HTTP/2, HTTP/3, scale hoặc gateway?
                 |
                 +-- Có --> Chọn server/proxy công bố hỗ trợ yêu cầu đó
```

Bảng quyết định nhanh:

| Tình huống | Lựa chọn nên cân nhắc |
| --- | --- |
| Xem frontend build ở local | `jwebserver`. |
| Phục vụ tài liệu tĩnh trong môi trường dev | `jwebserver`. |
| Website tĩnh công khai qua HTTPS | Web server chuyên dụng có TLS. |
| Ứng dụng Java nhúng có vài endpoint HTTPS | `HttpsServer` nếu chấp nhận tự quản lý các phần còn thiếu. |
| REST API có xác thực và database | Framework ứng dụng Java. |
| Ứng dụng cần HTTP/2/HTTP/3 hoặc reverse proxy | Server/proxy có hỗ trợ giao thức và tính năng đó. |
| Cần static content cùng backend động | Reverse proxy/web server phía trước và ứng dụng backend phía sau. |

## 10. Thực hành: phục vụ static site rồi xác định lúc cần đổi công cụ

### 10.1. Tạo một website tĩnh

Tạo cấu trúc:

```text
demo/
└── public/
    ├── index.html
    ├── about.html
    ├── css/
    │   └── site.css
    └── api/
        └── sample.json
```

Nội dung `public/index.html`:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <link rel="stylesheet" href="/css/site.css">
  <title>Static site</title>
</head>
<body>
  <h1>Website tĩnh</h1>
  <a href="/about.html">Giới thiệu</a>
</body>
</html>
```

Nội dung `public/css/site.css`:

```css
body {
  font-family: sans-serif;
  max-width: 48rem;
  margin: 3rem auto;
}
```

Nội dung `public/api/sample.json`:

```json
{
  "message": "Static JSON sample",
  "version": 1
}
```

### 10.2. Chạy jwebserver

Từ thư mục `demo`:

```sh
jwebserver -b 127.0.0.1 -p 8000 -d ./public -o info
```

Mở `http://127.0.0.1:8000/` trong trình duyệt.

### 10.3. Kiểm tra tài nguyên tĩnh

```sh
curl -i http://127.0.0.1:8000/
curl -I http://127.0.0.1:8000/css/site.css
curl -i http://127.0.0.1:8000/api/sample.json
```

Các URL trỏ tới tệp đã tồn tại được phục vụ như tài nguyên tĩnh. JSON trong ví dụ là tệp có sẵn; server không tạo JSON dựa trên database.

### 10.4. Thử request động

```sh
curl -i http://127.0.0.1:8000/api/products
curl -i -X POST -d "name=demo" http://127.0.0.1:8000/api/products
```

Không có handler nghiệp vụ cho `/api/products`. Request GET có thể trả 404 nếu không có tệp hoặc thư mục tương ứng; POST không được phục vụ vì CLI chỉ hỗ trợ GET/HEAD và có thể trả 405 hoặc 501.

Điều này cho thấy việc đặt thư mục tên `api` không tự tạo API backend. Tệp JSON tĩnh và endpoint JSON động là hai loại tài nguyên khác nhau.

### 10.5. Xác định yêu cầu tiếp theo

Sau bài thử, trả lời:

- Nếu chỉ cần hiển thị nội dung `public` trên máy local, công cụ hiện tại có đáp ứng không?
- Nếu cần gửi thông tin đăng nhập bằng HTTPS, cần thêm thành phần nào?
- Nếu cần POST dữ liệu và lưu vào database, cần lớp xử lý nào?
- Nếu cần HTTP/2, server hoặc proxy được chọn phải công bố hỗ trợ giao thức nào?
- Nếu muốn dùng Java API để tự xử lý HTTPS, lớp nào tạo server và lớp nào cấu hình TLS?

Sau khi hoàn thành, dừng server bằng **Ctrl+C**.

## 11. Ranh giới bảo mật và vận hành

### 11.1. HTTP không mã hóa dữ liệu trên đường truyền

Request tới `http://` không được bảo vệ bằng TLS. Nếu truyền thông tin nhạy cảm qua một mạng không tin cậy, dữ liệu có thể bị quan sát hoặc thay đổi trên đường truyền.

Không dùng HTTP thuần để gửi mật khẩu, token hoặc dữ liệu cá nhân qua mạng công cộng.

### 11.2. Bind address quyết định phạm vi truy cập

Mặc định `jwebserver` bind loopback. Ví dụ:

```sh
jwebserver -d ./public
```

Mặc định server chỉ lắng nghe loopback trên cổng 8000.

Nếu dùng:

```sh
jwebserver -b 0.0.0.0 -p 8000 -d ./public
```

server lắng nghe trên mọi IPv4 interface. Máy khác trong mạng có thể truy cập nếu firewall và routing cho phép.

Không bind tất cả interface chỉ để sửa lỗi truy cập local. Trước tiên hãy kiểm tra URL loopback, port và document root.

### 11.3. Document root phải chỉ chứa nội dung được phép công khai

Tệp trong document root có thể được truy cập bằng URL nếu server phục vụ nó. Không đặt source secrets, private keys, file cấu hình chứa mật khẩu, bản sao lưu hoặc dữ liệu người dùng vào thư mục này.

Hidden file và symbolic link bị loại khỏi hành vi phục vụ mặc định, nhưng không nên dùng quy tắc đó làm cơ chế phân quyền ứng dụng.

### 11.4. TLS không thay thế authentication

HTTPS bảo vệ kết nối và xác minh danh tính server theo chứng chỉ. Nó không tự xác định người dùng có được phép xem một đơn hàng, tải tệp hoặc thực hiện thao tác quản trị hay không.

Ứng dụng vẫn cần authentication, authorization, validation và audit phù hợp với dữ liệu, hành động mà nó cung cấp.

### 11.5. Đánh giá vận hành trước khi public

Một dịch vụ public cần cân nhắc:

- TLS certificate lifecycle và cấu hình giao thức.
- Authentication, authorization và session nếu có.
- Giới hạn request size, timeout và connection.
- Logging, metrics, tracing và cảnh báo.
- Rate limiting và khả năng chống lạm dụng.
- Cập nhật bảo mật, backup và quy trình khôi phục.
- Reverse proxy, load balancing và triển khai nhiều instance khi cần.

`jwebserver` không được thiết kế để cung cấp các khả năng vận hành này.

## 12. Chẩn đoán lựa chọn sai công cụ

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Trình duyệt báo lỗi khi mở `https://localhost:8000` | CLI chỉ hỗ trợ HTTP, không có TLS listener. | Dùng URL HTTP cho thử nghiệm local hoặc chọn HTTPS server/proxy. |
| Request HTTP/2 không hoạt động | CLI chỉ hỗ trợ HTTP/1.1. | Chọn server/proxy hỗ trợ HTTP/2. |
| Gọi API nhưng nhận 404 | Server đang tìm tệp tĩnh; không có route xử lý nghiệp vụ. | Tạo backend handler hoặc dùng framework ứng dụng. |
| POST trả 405/501 | Method ngoài GET/HEAD. | Chọn API server có handler phù hợp. |
| Tệp được tải về thay vì hiển thị | MIME type hoặc hành vi trình duyệt không phù hợp. | Kiểm tra Content-Type; dùng handler/server cấu hình MIME nếu cần. |
| Người dùng khác không truy cập được server local | Server bind loopback hoặc firewall chặn. | Chỉ thay bind address khi thực sự cần truy cập từ mạng và đã kiểm soát document root. |
| Website tĩnh chạy tốt nhưng đăng nhập không hoạt động | File server không có authentication/session. | Tích hợp backend ứng dụng có xác thực. |
| Cần upload nhưng tệp không được tạo | CLI không xử lý POST/PUT. | Dùng API backend có kiểm tra quyền và lưu trữ. |
| HttpsServer chạy nhưng client báo chứng chỉ không tin cậy | Certificate không được client tin cậy hoặc hostname không khớp SAN. | Dùng certificate/CA phù hợp và kiểm tra hostname. |
| HTTPS đã hoạt động nhưng người dùng vẫn truy cập dữ liệu trái phép | TLS chỉ bảo vệ đường truyền; ứng dụng thiếu authorization. | Thiết kế kiểm soát quyền trên từng tài nguyên và hành động. |

## 13. Bài tập tự kiểm tra

1. Khởi động `jwebserver` và xác định phiên bản HTTP được hỗ trợ.
2. Giải thích vì sao đổi URL từ `http://` sang `https://` không bật TLS cho CLI.
3. Phân biệt một tệp JSON tĩnh với endpoint JSON động.
4. Gửi POST tới `jwebserver` và giải thích status nhận được.
5. So sánh vai trò của `HttpServer` và `HttpsServer`.
6. Giải thích vì sao `HttpsServer` cần `SSLContext` và `HttpsConfigurator`.
7. Mô tả reverse proxy kết thúc TLS và chuyển tiếp request tới backend.
8. Nêu trường hợp nên dùng web server tĩnh có TLS thay vì viết Java handler.
9. Nêu trường hợp một embedded `HttpsServer` có thể phù hợp và những phần bảo mật cần tự triển khai.
10. Liệt kê các yêu cầu khiến ứng dụng nên dùng framework hoặc server production đầy đủ.
11. Giải thích vì sao HTTPS không thay thế authentication và authorization.
12. Giải thích vì sao không nên bind `0.0.0.0` khi chỉ cần thử nghiệm local.

**Tiêu chí hoàn thành:** bạn nêu được chính xác giới hạn của `jwebserver` trên JDK hiện đại, phân biệt HTTP/1.1 với HTTPS và nội dung tĩnh với xử lý ứng dụng, chọn được hướng triển khai phù hợp cho website tĩnh, dịch vụ Java nhúng hoặc backend production, đồng thời giải thích được vai trò của `HttpsServer`, TLS và reverse proxy.

## 14. Tài liệu tham khảo

- [Oracle Java SE 27 — The jwebserver Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jwebserver.html): phạm vi CLI, HTTP/1.1, chỉ tệp tĩnh, GET/HEAD, không hỗ trợ HTTP/2 và HTTPS, bind address và document root.
- [Oracle Java SE 27 — Module jdk.httpserver](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/module-summary.html): phân biệt SimpleFileServer HTTP-only với API HTTP/HTTPS; ghi rõ API/SPI được thiết kế cho server tối giản và không hướng tới server đầy đủ tính năng, hiệu năng cao.
- [Oracle Java SE 27 — HttpServer API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): đăng ký HttpHandler theo HttpContext và quản lý server nhúng.
- [Oracle Java SE 27 — HttpsServer API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html): HttpsServer mở rộng HttpServer để hỗ trợ HTTPS và yêu cầu HttpsConfigurator.
- [Oracle Java SE 27 — HttpsConfigurator API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsConfigurator.html): cấu hình SSL/TLS parameters cho kết nối HTTPS.
- [OpenJDK JEP 408 — Simple Web Server](https://openjdk.org/jeps/408): mục tiêu thiết kế Simple Web Server được giới thiệu trong Java 18.
- [Spring Boot Documentation](https://docs.spring.io/spring-boot/index.html): tài liệu framework xây dựng ứng dụng Java và web service.
- [Quarkus Guides](https://quarkus.io/guides/): tài liệu xây dựng ứng dụng Java và dịch vụ cloud-native.
- [Micronaut Documentation](https://docs.micronaut.io/latest/guide/): tài liệu framework xây dựng ứng dụng và HTTP service Java.
