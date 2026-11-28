# HttpContext và tiền tố đường dẫn: kiểm chứng cách URI được ánh xạ khi gắn file handler

## 1. HttpContext là gì?

Một HttpServer có thể phục vụ nhiều phần của ứng dụng trên cùng địa chỉ IP và cổng. Mỗi phần được gắn với một HttpContext: đối tượng liên kết một URI path gốc với một HttpHandler. Context cũng chứa danh sách Filter và các thuộc tính dùng chung cho những exchange được xử lý qua context đó.

Ví dụ:

| Context path | Handler | Mục đích |
| --- | --- | --- |
| / | File handler | Phục vụ nội dung tĩnh mặc định. |
| /assets/ | File handler | Phục vụ tài nguyên tĩnh dưới vùng assets. |
| /api/health/ | Handler tự viết | Trả trạng thái health. |

Tạo context bằng API:

~~~java
HttpContext context = server.createContext(
        "/assets/", SimpleFileServer.createFileHandler(root));
~~~

Trong đó:

- **server** là HttpServer đã được tạo và bind.
- **/assets/** là context path, phải bắt đầu bằng dấu gạch chéo.
- **createFileHandler(root)** trả về HttpHandler phục vụ tệp trong root.
- **HttpContext** là nơi có thể gắn Filter, Authenticator và cấu hình khác.

Phương thức createContext(path, handler) ném IllegalArgumentException nếu path không hợp lệ hoặc context cùng path đã tồn tại; ném NullPointerException nếu path hoặc handler là null. Context path là đường dẫn URI, không phải đường dẫn thư mục trên ổ đĩa.

## 2. HttpServer chọn context như thế nào?

Khi nhận HTTP request, HttpServer lấy **path của request URI** và tìm context có path là **tiền tố khớp dài nhất** (*longest matching prefix*). Context cụ thể hơn được ưu tiên trước context tổng quát.

Ví dụ có ba context:

~~~text
/                  -> context gốc
/assets/           -> context tài nguyên
/assets/icons/     -> context biểu tượng
~~~

Request /assets/icons/logo.svg khớp cả ba tiền tố, nhưng /assets/icons/ dài nhất nên context này được chọn. Request /assets/site.css chọn /assets/; request /index.html chọn /.

Quy tắc định tuyến có thể hình dung:

~~~text
HTTP request
    |
    v
Lấy URI path (không lấy query string)
    |
    v
Tìm các HttpContext có path khớp
    |
    v
Chọn context có tiền tố khớp dài nhất
    |
    +---- không có context phù hợp ----> 404 Not Found
    |
    v
Chạy Filter chain của context đó
    |
    v
Gọi HttpHandler của context
    |
    v
HTTP response
~~~

Thứ tự đăng ký context không quyết định context nào thắng. Độ dài của tiền tố khớp mới là yếu tố quyết định. Nếu hai context có cùng path, createContext không cho đăng ký trùng path.

## 3. Hành vi path matching trên JDK hiện đại

Đây là điểm cần kiểm chứng theo JDK đang dùng. Tài liệu JDK 27 mô tả hai khái niệm:

- **Path prefix matching:** các segment đường dẫn phải khớp đầy đủ. Context /assets khớp /assets, /assets/ và /assets/site.css, nhưng không khớp /assets-old/site.css.
- **String prefix matching:** chỉ so sánh tiền tố chuỗi. Theo cách này /assets cũng khớp /assets-old/site.css.

**JDK built-in hiện nay:** triển khai HttpServer mặc định của JDK dùng **path prefix matching** trên JDK 26 và JDK 27. Khi dùng triển khai mặc định này, ranh giới segment được giữ nguyên:

| Context path | Request path | Khớp? | Lý do |
| --- | --- | --- | --- |
| /assets | /assets | Có | Path giống nhau. |
| /assets | /assets/ | Có | Segment assets khớp. |
| /assets | /assets/site.css | Có | Request đi tiếp từ segment assets. |
| /assets | /assets-old/site.css | Không | assets và assets-old là hai segment khác nhau. |
| /assets/ | /assets | Không | Request thiếu dấu / cuối của context path. |
| /assets/ | /assets/site.css | Có | Request bắt đầu bằng context path. |
| /assets/ | /assets-old/site.css | Không | Không có segment / sau assets. |
| /Assets/ | /assets/site.css | Không | So khớp phân biệt chữ hoa/chữ thường. |

API Note của HttpServer lưu ý các HttpServerProvider khác nhau có thể triển khai cách so khớp khác nhau khi context path không kết thúc bằng dấu gạch chéo. Vì vậy, khi thiết kế route, **nên kết thúc context path theo ranh giới thư mục**, ví dụ /assets/, /api/, /health/. Cách viết này thể hiện rõ phạm vi route và giảm phụ thuộc vào khác biệt giữa các implementation.

Không nên bê nguyên giả định string-prefix từ ví dụ cũ sang JDK hiện đại. Khi cần hành vi nhất quán, hãy dùng context path có dấu gạch chéo cuối và kiểm thử trên đúng JDK/provider được triển khai.

## 4. So khớp literal, phân biệt hoa thường và encoded path

Javadoc JDK 27 mô tả path matching là **literal**:

- So sánh phân biệt chữ hoa/chữ thường.
- Không tự chuyển đổi URI path từ dạng percent-encoded sang dạng đã decode để tìm context.
- Không tự chuyển đổi ngược từ dạng đã decode sang encoded để tìm context.
- Phần query string không thuộc URI path nên không quyết định context.

Ví dụ context /café/ không nên được kỳ vọng tự khớp request path /caf%C3%A9/. Khi URL có ký tự cần percent-encode, hãy kiểm tra request URI thực tế và dùng một quy ước route rõ ràng, ưu tiên path ASCII cho context.

| Request URI | URI path dùng để định tuyến | Ghi chú |
| --- | --- | --- |
| /assets/site.css?v=2 | /assets/site.css | Query ?v=2 không tham gia chọn context. |
| /assets/site.css | /assets/site.css | Khớp context /assets/. |
| /Assets/site.css | /Assets/site.css | Khác chữ hoa/thường với /assets/. |
| /caf%C3%A9/menu | /caf%C3%A9/menu | Không được tự coi %C3%A9 là é khi so context. |

Định tuyến context không phải cơ chế chuẩn hóa URL hoặc kiểm tra quyền truy cập file. Sau khi context được chọn, handler vẫn phải xử lý tài nguyên theo hợp đồng riêng.

## 5. Gắn SimpleFileServer file handler vào context

SimpleFileServer.createFileHandler(rootDirectory) tạo một HttpHandler độc lập. Khi gắn vào context, có hai khái niệm đường dẫn khác nhau:

- **Context path** xác định request nào được chuyển tới handler.
- **rootDirectory** là thư mục hệ thống tệp mà file handler dùng làm gốc để phân giải request URI thành tài nguyên.

Javadoc mô tả file handler phân giải request URI dựa trên rootDirectory. Context path không biến thành một đường dẫn thư mục trên ổ đĩa và không nên giả định rằng server sẽ tự cắt context prefix khỏi URI trước khi handler nhận request.

Điểm này cũng giải thích khác biệt giữa hai factory:

- SimpleFileServer.createFileServer(addr, root, level) tạo sẵn file handler tại context gốc /.
- SimpleFileServer.createFileHandler(root) chỉ trả về handler. Khi muốn mount handler ở /assets/ hoặc một path riêng, ứng dụng tự tạo HttpServer và gọi createContext(path, handler).

Vì vậy, muốn dùng file handler ở nhiều context hoặc kết hợp với route API riêng, hãy dùng createFileHandler. Factory createFileServer phù hợp khi muốn một file server đơn giản phục vụ từ context /.

Ví dụ, với root là public và context /assets/, cấu trúc phù hợp là:

~~~text
public/
    index.html
    assets/
        site.css
        icons/
            logo.svg
~~~

Các request được định tuyến và tài nguyên tương ứng:

| Request URI | Context được chọn | Tài nguyên dưới root |
| --- | --- | --- |
| /index.html | / | public/index.html |
| /assets/site.css | /assets/ | public/assets/site.css |
| /assets/icons/logo.svg | /assets/icons/ | public/assets/icons/logo.svg |

Nếu gắn file handler vào /assets/, hãy tổ chức root sao cho đường dẫn URI đầy đủ có thể được phân giải bên dưới root. Đừng chỉ tạo public/site.css rồi mong request /assets/site.css tự động bỏ đoạn /assets/.

## 6. Ví dụ hoàn chỉnh: kiểm chứng context được chọn

Ví dụ sau tạo ba context file handler lồng nhau. Một wrapper handler thêm response header X-Demo-Context để cho biết context nào đã xử lý request. Các handler đều dùng chung root public, vì vậy request /assets/icons/logo.svg sẽ được phục vụ từ public/assets/icons/logo.svg.

Chuẩn bị thư mục:

~~~text
public/
    index.html
    assets/
        site.css
        icons/
            logo.svg
~~~

Lưu thành ContextMappingDemo.java:

~~~java
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.SimpleFileServer;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.file.Files;
import java.nio.file.Path;

public class ContextMappingDemo {
    private static HttpHandler markContext(
            String contextName, HttpHandler delegate) {
        return exchange -> {
            exchange.getResponseHeaders()
                    .set("X-Demo-Context", contextName);
            delegate.handle(exchange);
        };
    }

    public static void main(String[] args) throws IOException {
        Path root = Path.of("public").toAbsolutePath().normalize();
        if (!Files.isDirectory(root) || !Files.isReadable(root)) {
            throw new IllegalArgumentException(
                    "Thư mục public không hợp lệ: " + root);
        }

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        // Context tổng quát: nhận request không có route cụ thể hơn.
        server.createContext("/", markContext(
                "root",
                SimpleFileServer.createFileHandler(root)));

        // Context tài nguyên: khớp /assets/... nhưng không khớp /assets-old/...
        server.createContext("/assets/", markContext(
                "assets",
                SimpleFileServer.createFileHandler(root)));

        // Context cụ thể nhất: ưu tiên cho /assets/icons/...
        server.createContext("/assets/icons/", markContext(
                "icons",
                SimpleFileServer.createFileHandler(root)));

        server.start();
        try {
            int port = server.getAddress().getPort();
            System.out.println("Server: http://127.0.0.1:" + port + "/");
            System.out.println("Nhấn Enter để dừng...");
            System.in.read();
        } finally {
            server.stop(1);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 18 trở lên:

~~~bash
javac ContextMappingDemo.java
java ContextMappingDemo
~~~

Thay <port> bằng cổng được chương trình in ra:

~~~bash
curl -i http://127.0.0.1:<port>/index.html
curl -i http://127.0.0.1:<port>/assets/site.css
curl -i http://127.0.0.1:<port>/assets/icons/logo.svg
curl -i http://127.0.0.1:<port>/assets-old/site.css
curl -i http://127.0.0.1:<port>/Assets/site.css
~~~

Quan sát response header X-Demo-Context:

| Request | Header mong đợi | Giải thích |
| --- | --- | --- |
| /index.html | root | Chỉ context / khớp. |
| /assets/site.css | assets | /assets/ cụ thể hơn /. |
| /assets/icons/logo.svg | icons | /assets/icons/ là tiền tố khớp dài nhất. |
| /assets-old/site.css | root | /assets/ không khớp ranh giới segment. |
| /Assets/site.css | root | Path phân biệt hoa thường. |

Ở hai request cuối, root handler vẫn nhận request vì có context /. Nếu bỏ context /, những request không khớp /assets/ hoặc context nào khác sẽ nhận 404.

File handler chỉ hỗ trợ GET và HEAD; các method khác nhận 405 Method Not Allowed. Nếu cần route cho POST, PUT hoặc OPTIONS, hãy đăng ký handler riêng hoặc kết hợp handler có điều kiện.

## 7. Context path không phải file path

Ba khái niệm thường bị nhầm:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Context path | /assets/ | Tiền tố URI dùng để chọn HttpContext. |
| Request URI path | /assets/site.css | Path client yêu cầu; dùng trong quá trình định tuyến và xử lý request. |
| Root directory | D:/demo/public hoặc /opt/demo/public | Thư mục hệ thống tệp làm gốc cho file handler. |

Context /assets/ không có nghĩa root phải là thư mục tên assets. Tuy nhiên, do file handler phân giải URI path đối với root, nếu request là /assets/site.css thì cấu trúc file nên có root/assets/site.css.

Nếu muốn URL ngắn hơn nhưng lưu file ở một cấu trúc khác, có thể tự viết HttpHandler để ánh xạ URI theo quy tắc của ứng dụng rồi đọc file an toàn. Không nên giả định createFileHandler có tùy chọn cấu hình prefix stripping hoặc base path; API factory không cung cấp tham số đó.

## 8. Lỗi thường gặp khi thiết kế context

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| /assets-old/a.css đi vào context /assets/ | Context path được đăng ký không có dấu / cuối hoặc provider dùng cách so khớp khác. | Dùng /assets/ và xác minh behavior của JDK/provider. |
| /Assets/a.css không vào /assets/ | Path matching phân biệt chữ hoa/chữ thường. | Thống nhất casing trong URL và context path. |
| /assets/a.css chọn handler root thay vì assets | Context assets không được đăng ký, path sai hoặc URI không khớp literal. | Kiểm tra context.getPath() và request URI path thực tế. |
| Request đã vào file handler nhưng nhận 404 | File không nằm ở đường dẫn được phân giải từ root và request URI. | Kiểm tra cấu trúc root/assets/..., không chỉ context path. |
| Request không khớp context nào | Server không có context gốc/fallback phù hợp. | Đăng ký context cần thiết hoặc xử lý route fallback. |
| Đăng ký hai context cùng path bị lỗi | Context path phải duy nhất trong một server. | Chọn path riêng hoặc thay handler của context hiện có theo API. |
| %2F hoặc encoded path không vào context dự kiến | Context matching không tự decode encoded URI forms. | Dùng URL/path nhất quán; xử lý decode có kiểm soát ở tầng handler nếu nghiệp vụ yêu cầu. |

## 9. Nguyên tắc thiết kế route hiện đại

1. **Dùng context path kết thúc bằng / cho route dạng thư mục:** ví dụ /assets/, /api/, /health/. Điều này giúp thể hiện ranh giới segment và tránh nhập nhằng với tên gần giống.
2. **Đặt route cụ thể trước về mặt thiết kế:** dù thứ tự đăng ký không quyết định ưu tiên, cấu trúc /assets/icons/ rõ ràng là route con của /assets/.
3. **Dùng longest matching prefix có chủ đích:** route con nhận request trước route cha; kiểm thử cả trường hợp đúng, sai casing và segment gần giống.
4. **Tách context path khỏi filesystem layout:** xác định rõ request URI sẽ được file handler phân giải thành đường dẫn nào dưới root.
5. **Không dựa vào legacy string-prefix behavior:** trên JDK built-in hiện đại, mặc định là path-prefix matching. Khi dùng provider khác, đọc tài liệu provider và kiểm thử route thực tế.
6. **Không coi route matching là bảo mật file:** file handler vẫn cần root directory được chọn an toàn; không phục vụ thư mục chứa secret hoặc dữ liệu riêng.

## 10. Câu hỏi tự kiểm tra

1. HttpContext liên kết những thành phần nào của HttpServer?
2. Vì sao request /assets/icons/logo.svg chọn /assets/icons/ thay vì /assets/?
3. Trên JDK built-in 26/27, /assets/ có khớp /assets-old/ không? Vì sao?
4. Vì sao context path nên kết thúc bằng / khi đại diện một thư mục route?
5. Request /assets/site.css?v=3 được định tuyến dựa trên phần nào của URI?
6. Vì sao /Assets/site.css không khớp context /assets/?
7. Khi gắn createFileHandler(root) vào context /assets/, root cần chứa file theo cấu trúc nào?
8. Nếu không có context nào khớp request URI, server trả kết quả gì?
9. Vì sao không nên giả định context prefix được cắt bỏ khỏi URI trước khi file handler phân giải đường dẫn?
10. Vì sao nên kiểm thử behavior trên đúng JDK và HttpServerProvider sẽ được dùng?

**Bài thực hành:** chạy ContextMappingDemo, gửi năm request trong ví dụ và ghi lại X-Demo-Context. Sau đó thay context /assets/ bằng /assets và thử /assets-old/site.css; quan sát rằng JDK built-in hiện đại vẫn dùng ranh giới segment. Thử thêm context /assets/icons/ và kiểm tra longest matching prefix. Khôi phục context có dấu / cuối sau khi thử.

## Tài liệu tham khảo chính thức

- [Oracle JDK 27 — HttpServer](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): quy tắc longest matching prefix, so khớp literal, case-sensitive và API createContext.
- [Oracle JDK 27 — module jdk.httpserver](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/module-summary.html): path matching mặc định của JDK built-in là pathPrefix; ví dụ ranh giới segment và phạm vi triển khai.
- [Oracle JDK 27 — HttpContext](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html): quan hệ giữa URI path, handler, filter và context.
- [Oracle JDK 27 — SimpleFileServer](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): createFileHandler, cách phân giải request URI đối với root directory, method được hỗ trợ và directory listing.
- [Oracle JDK 18 — HttpServer](https://docs.oracle.com/en/java/javase/18/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): API context và định tuyến được dùng từ phiên bản giới thiệu.
