# Kiểm thử HTTP/3 với máy chủ thực sự hỗ trợ

## 1. Mục tiêu và phiên bản cần dùng

Bài thực hành này xác nhận ứng dụng Java đã trao đổi bằng HTTP/3 với một máy chủ thật. Điểm kiểm tra quan trọng là phiên bản giao thức mà `HttpResponse` trả về, không phải việc ứng dụng đã đặt HTTP/3 làm phiên bản ưu tiên hoặc máy chủ có gửi header `Alt-Svc`.

HTTP/3 cho HTTP Client API được đưa vào JDK 26 qua JEP 517. Đây là API chính thức của Java SE, không phải preview hay incubator. Các API `HttpClient.Version.HTTP_3`, `HttpOption.H3_DISCOVERY` và `HttpOption.Http3DiscoveryMode` tiếp tục có trong JDK 27.

Tính đến ngày 27/11/2026, JDK 27 là feature release mới hơn. Nên thực hiện bài lab trên JDK 27 hoặc một bản JDK 26 vẫn được nhà cung cấp của bạn hỗ trợ. JDK 25 LTS chưa có HTTP/3 tích hợp trong `java.net.http.HttpClient`; mã dùng `HTTP_3` cần JDK 26 trở lên.

Mục tiêu sau khi thực hành:

- Gửi một request HTTPS tới máy chủ công khai đã được xác nhận có hỗ trợ HTTP/3.
- Yêu cầu chỉ dùng HTTP/3 để kết quả không bị che bởi fallback.
- Đọc `HttpResponse.version()` và xác nhận giá trị là `HTTP_3`.
- So sánh với chế độ tự lựa chọn và khám phá qua `Alt-Svc`.
- Phân biệt lỗi từ máy chủ, mạng UDP, proxy, TLS và phiên bản JDK.

## 2. Chọn máy chủ kiểm thử thật

Dùng endpoint công khai:

~~~text
https://www.google.com/
~~~

Đây là endpoint đã được thành viên nhóm Java tại Oracle kiểm thử trực tiếp trong bài viết về HTTP/3 của JDK 26. Bài viết dùng `HTTP_3_URI_ONLY` và ghi nhận response có status 200 cùng phiên bản `HTTP_3`. Bài viết cũng quan sát header `Alt-Svc` của Google và thử lại bằng cùng một `HttpClient`.

Đây là bằng chứng kỹ thuật có thể tái hiện, không phải cam kết dịch vụ kiểm thử cố định. Google sử dụng hạ tầng phân phối nội dung và kết quả có thể thay đổi theo thời điểm, vùng mạng, DNS, chính sách truy cập hoặc thiết bị trung gian. Hãy xác nhận lại từ chính môi trường mà ứng dụng sẽ chạy.

Có thể chọn một máy chủ khác nếu nó đáp ứng đủ hai điều kiện:

1. Máy chủ công bố hoặc xác nhận hỗ trợ HTTP/3.
2. HTTP/3 hoạt động trực tiếp tại đúng host và port của URI, thường là UDP 443.

Một response có header `Alt-Svc: h3=...` cho biết server quảng bá dịch vụ HTTP/3. Header đó chưa chứng minh request hiện tại đã đi qua HTTP/3. Bằng chứng cuối cùng vẫn là phiên bản response hoặc kết quả kiểm tra HTTP/3 nghiêm ngặt.

## 3. Kiểm tra môi trường trước khi chạy

### 3.1. Xác nhận JDK

Mở terminal trong môi trường chạy ứng dụng:

~~~bash
java --version
javac --version
~~~

Cần xác nhận cả Java runtime và compiler đều từ JDK 26 trở lên. Trường hợp máy có nhiều JDK, IDE, terminal, Maven/Gradle và container có thể đang dùng các runtime khác nhau. Bài lab này chỉ dùng lệnh `javac` và `java` trực tiếp.

Không cần bật preview hoặc thêm module incubator cho HTTP/3. Nếu compiler báo không tìm thấy `HTTP_3` hoặc `HttpOption`, hãy kiểm tra JDK đang dùng và tùy chọn `--release`; không thay API bằng một thư viện cũ chỉ để bỏ qua lỗi cấu hình.

### 3.2. Kiểm tra đường mạng

HTTP/3 chạy trên QUIC qua UDP. Trước khi chạy, kiểm tra:

- Mạng cho phép lưu lượng UDP tới cổng của máy chủ, thông thường là UDP 443.
- Firewall, VPN, NAT, security gateway và load balancer không chặn hoặc làm gián đoạn QUIC.
- Máy có thể phân giải DNS của endpoint và xác thực được chứng chỉ TLS.
- JDK built-in `HttpClient` không gửi HTTP/3 qua proxy. Nếu proxy được chọn cho request, chế độ nghiêm ngặt `HTTP_3_URI_ONLY` sẽ thất bại; các chế độ khác có thể hạ xuống HTTP/2 hoặc HTTP/1.1.

Nếu mạng công ty bắt buộc dùng proxy, hãy làm việc với đội quản trị mạng để có môi trường kiểm thử HTTP/3 được cho phép. Không tắt xác minh chứng chỉ hoặc tự ý vượt qua chính sách proxy để làm cho bài lab chạy được.

## 4. Viết chương trình chỉ chấp nhận HTTP/3

Chương trình dưới đây dùng `HTTP_3_URI_ONLY`. Mode này yêu cầu client thử QUIC trực tiếp tới host và port trong URI, không dùng Alt-Svc và không chuyển sang HTTP/2 hoặc HTTP/1.1.

Tạo file `Http3StrictProbe.java`:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpOption;
import java.net.http.HttpOption.Http3DiscoveryMode;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class Http3StrictProbe {
    public static void main(String[] args) throws Exception {
        URI uri = args.length == 0
                ? URI.create("https://www.google.com/")
                : URI.create(args[0]);

        HttpRequest request = HttpRequest.newBuilder(uri)
                .version(HttpClient.Version.HTTP_3)
                .setOption(
                        HttpOption.H3_DISCOVERY,
                        Http3DiscoveryMode.HTTP_3_URI_ONLY
                )
                .timeout(Duration.ofSeconds(20))
                .GET()
                .build();

        try (HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(8))
                .build()) {

            HttpResponse<Void> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.discarding()
            );

            System.out.println("URI: " + response.uri());
            System.out.println("Status: " + response.statusCode());
            System.out.println("HTTP version: " + response.version());

            response.headers().firstValue("alt-svc")
                    .ifPresent(value -> System.out.println("Alt-Svc: " + value));

            if (response.version() != HttpClient.Version.HTTP_3) {
                throw new IllegalStateException(
                        "Không xác nhận được HTTP/3: " + response.version()
                );
            }

            System.out.println("PASS: response đã được nhận qua HTTP/3.");
        }
    }
}
~~~

Một số quyết định trong ví dụ:

- Đặt `HTTP_3` ở cấp request để yêu cầu phiên bản cho chính request này.
- Đặt `HTTP_3_URI_ONLY` để phép thử thất bại nếu không thể kết nối HTTP/3 trực tiếp.
- Dùng `BodyHandlers.discarding()` vì bài lab chỉ cần status, header và phiên bản giao thức; không cần tải toàn bộ nội dung trang.
- Đặt timeout cho kết nối và request để lỗi mạng không khiến bài kiểm thử chờ vô hạn.
- In `response.version()` và kiểm tra rõ giá trị `HTTP_3`.

Chương trình không tự retry bằng HTTP/2 sau lỗi. Điều này giữ cho kết quả có ý nghĩa: nếu chương trình in PASS thì response đã được nhận bằng HTTP/3.

## 5. Biên dịch và chạy

Nếu dùng JDK 27:

~~~bash
javac --release 27 -d out Http3StrictProbe.java
java -cp out Http3StrictProbe
~~~

Nếu đang dùng JDK 26 còn được nhà cung cấp hỗ trợ, thay `27` bằng `26`:

~~~bash
javac --release 26 -d out Http3StrictProbe.java
java -cp out Http3StrictProbe
~~~

Có thể truyền một endpoint khác đã được xác nhận hỗ trợ HTTP/3:

~~~bash
java -cp out Http3StrictProbe https://www.google.com/
~~~

Không cần `--enable-preview`, `--add-modules` hoặc module incubator. Đây là API chính thức của HTTP Client API kể từ JDK 26.

Kết quả thành công có dạng:

~~~text
URI: https://www.google.com/
Status: 200
HTTP version: HTTP_3
Alt-Svc: h3=":443"; ma=...
PASS: response đã được nhận qua HTTP/3.
~~~

Header `Alt-Svc` có thể không xuất hiện hoặc giá trị có thể khác nhau. Status code cũng có thể thay đổi theo chính sách của server. Điều kiện xác nhận giao thức là:

~~~text
HTTP version: HTTP_3
~~~

Nếu server trả về status 403 hoặc 429 nhưng `response.version()` vẫn là `HTTP_3`, tầng HTTP/3 đã hoạt động; status đó là quyết định của ứng dụng hoặc chính sách server. Không nhầm lỗi quyền truy cập tài nguyên với lỗi thiết lập giao thức.

## 6. So sánh HTTP/2 và HTTP/3

Sau khi kiểm tra strict HTTP/3, có thể chạy một request HTTP/2 làm đối chứng. Thay phần xây dựng request bằng:

~~~java
HttpRequest request = HttpRequest.newBuilder(uri)
        .version(HttpClient.Version.HTTP_2)
        .timeout(Duration.ofSeconds(20))
        .GET()
        .build();
~~~

Gửi request bằng cùng cách gọi:

~~~java
HttpResponse<Void> response = client.send(
        request,
        HttpResponse.BodyHandlers.discarding()
);

System.out.println("Status: " + response.statusCode());
System.out.println("HTTP version: " + response.version());
~~~

Kết quả mong đợi là `HTTP_2` khi server và mạng hỗ trợ HTTP/2. Phép thử này xác nhận đường HTTPS/TCP hoạt động; nó không thay thế phép thử HTTP/3 qua QUIC/UDP.

| Phép thử | Cấu hình | Kết quả cần quan sát |
|---|---|---|
| HTTP/2 đối chứng | `HTTP_2` | `HTTP_2` nếu server thương lượng HTTP/2 thành công |
| HTTP/3 nghiêm ngặt | `HTTP_3` + `HTTP_3_URI_ONLY` | `HTTP_3`; nếu không kết nối được thì request thất bại |
| HTTP/3 ưu tiên | `HTTP_3` + `ANY` | Có thể là `HTTP_3`, `HTTP_2` hoặc `HTTP_1_1` |
| Khám phá bằng Alt-Svc | `HTTP_3` + `ALT_SVC` | Có thể bắt đầu bằng HTTP/2/1.1; các request sau có thể dùng HTTP/3 nếu nhận được Alt-Svc h3 |

Điểm quan trọng: nếu `ANY` trả về `HTTP_2`, điều đó không chứng minh server không hỗ trợ HTTP/3. Thuật toán của client có thể thiết lập TCP trước, hoặc client chưa có thông tin alternative service. Muốn chứng minh endpoint trực tiếp có thể dùng HTTP/3, hãy dùng phép thử nghiêm ngặt ở phần 4.

## 7. Quan sát quá trình học Alt-Svc bằng cùng một HttpClient

Máy chủ có thể quảng bá endpoint HTTP/3 qua response header `Alt-Svc`. Khi dùng cùng một `HttpClient`, client có thể ghi nhận thông tin đó và dùng cho request tiếp theo.

Ví dụ sau dùng mode `ALT_SVC` và gửi hai request liên tiếp tới cùng origin:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpOption;
import java.net.http.HttpOption.Http3DiscoveryMode;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class Http3AltSvcExperiment {
    public static void main(String[] args) throws Exception {
        URI uri = URI.create("https://www.google.com/");

        try (HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_3)
                .connectTimeout(Duration.ofSeconds(8))
                .build()) {

            HttpRequest request = HttpRequest.newBuilder(uri)
                    .version(HttpClient.Version.HTTP_3)
                    .setOption(
                            HttpOption.H3_DISCOVERY,
                            Http3DiscoveryMode.ALT_SVC
                    )
                    .timeout(Duration.ofSeconds(20))
                    .GET()
                    .build();

            for (int i = 1; i <= 2; i++) {
                HttpResponse<Void> response = client.send(
                        request,
                        HttpResponse.BodyHandlers.discarding()
                );

                String altSvc = response.headers()
                        .firstValue("alt-svc")
                        .orElse("(không có Alt-Svc)");

                System.out.printf(
                        "Request %d: status=%d, version=%s, alt-svc=%s%n",
                        i,
                        response.statusCode(),
                        response.version(),
                        altSvc
                );
            }
        }
    }
}
~~~

Với một máy chủ quảng bá `Alt-Svc: h3=...`, có thể quan sát:

- Request đầu tiên dùng HTTP/2 hoặc HTTP/1.1 vì client chưa nhận được bản ghi h3.
- Response đầu tiên có thể chứa header `Alt-Svc`.
- Request thứ hai dùng cùng client có thể thiết lập QUIC và nhận response bằng HTTP/3.

Đây là thí nghiệm về cơ chế khám phá, không phải assertion cứng cho mọi server. Server có thể không gửi `Alt-Svc`, thay đổi thời hạn quảng bá, hoặc mạng không cho phép UDP. Vì vậy, request thứ hai vẫn có thể dùng HTTP/2/HTTP/1.1.

Đừng tạo một `HttpClient` mới cho mỗi request trong thí nghiệm này. Việc tạo client mới làm mất lợi ích của connection pool và trạng thái khám phá được duy trì trong vòng đời client.

## 8. Kiểm tra độc lập bằng curl

Có thể dùng curl để kiểm tra cùng endpoint bằng một HTTP client khác. Cách này giúp phân biệt lỗi do JDK với lỗi do mạng hoặc server.

Trên Windows PowerShell, dùng `curl.exe` để gọi chương trình curl thật:

~~~powershell
curl.exe --version
curl.exe --http3-only --verbose https://www.google.com/
~~~

Trên Linux hoặc macOS:

~~~bash
curl --version
curl --http3-only --verbose https://www.google.com/
~~~

`--http3-only` yêu cầu curl chỉ dùng HTTP/3; nếu QUIC không thiết lập được thì lệnh thất bại, không tự chuyển về HTTP/2 hoặc HTTP/1.1. Khi thành công, verbose output hiển thị phiên bản HTTP/3.

Có thể bỏ phần thân response và chỉ in phiên bản giao thức:

~~~powershell
curl.exe --http3-only -sS -o NUL -w "HTTP version: %{http_version}\n" https://www.google.com/
~~~

~~~bash
curl --http3-only -sS -o /dev/null -w 'HTTP version: %{http_version}\n' https://www.google.com/
~~~

Lưu ý:

- Build curl phải được biên dịch với hỗ trợ HTTP/3; không phải bản curl nào cũng có.
- `--http3-only` có từ curl 7.88.0. Nếu lệnh không nhận option hoặc báo không hỗ trợ giao thức, kiểm tra build curl trước khi kết luận về server.
- `--http3` có thể fallback về HTTP/2 hoặc HTTP/1.1. Khi mục tiêu là chứng minh HTTP/3, dùng `--http3-only`.
- curl cũng không dùng HTTP/3 qua proxy theo tài liệu hiện hành của curl.

Không dùng `--insecure` hoặc tùy chọn bỏ xác minh TLS để làm phép thử thành công. Cần giữ nguyên kiểm tra chứng chỉ như khi chạy ứng dụng thật.

## 9. Chẩn đoán khi kiểm thử thất bại

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra tiếp |
|---|---|---|
| Compiler không tìm thấy `HTTP_3` hoặc `HttpOption` | JDK nhỏ hơn 26 hoặc biên dịch với `--release` thấp | Kiểm tra `java --version`, `javac --version` và `--release` |
| `HTTP_3_URI_ONLY` timeout | UDP bị chặn, server không nghe QUIC tại đúng host:port, DNS hoặc tuyến mạng có vấn đề | Thử `curl --http3-only`, kiểm tra firewall/NAT và xác nhận endpoint |
| `UnsupportedProtocolVersionException` | Implementation không hỗ trợ HTTP/3 hoặc cấu hình `SSLContext`/`SSLParameters` không tương thích QUIC | Dùng JDK built-in HttpClient mặc định và kiểm tra cấu hình TLS tùy biến |
| `SSLHandshakeException` | Chứng chỉ, hostname, trust store hoặc TLS configuration không hợp lệ | Kiểm tra chuỗi chứng chỉ và trust store; không tắt xác minh TLS |
| `ANY` trả về `HTTP_2` | TCP thắng trước QUIC hoặc chưa có Alt-Svc | Chạy `HTTP_3_URI_ONLY` để kiểm tra trực tiếp |
| `ALT_SVC` luôn trả về HTTP/2 | Server không quảng bá h3, Alt-Svc hết hạn hoặc client không thể kết nối UDP | Kiểm tra response header và thử strict URI-only |
| Java strict mode thất bại nhưng curl strict thành công | Khác biệt JDK, SSLContext, proxy hoặc cấu hình runtime | Dùng cùng URI và mạng; kiểm tra proxy, provider TLS và JDK build |
| Cả Java và curl đều thất bại nhưng HTTP/2 thành công | Đường TCP hoạt động nhưng QUIC/UDP hoặc listener HTTP/3 không hoạt động | Kiểm tra UDP 443, server HTTP/3 và chính sách mạng |
| HTTP version là HTTP_3 nhưng status là 403/429 | HTTP/3 thành công, server từ chối request theo chính sách | Xử lý status, xác thực hoặc rate limit riêng với transport |

### Phân biệt các lỗi quan trọng

**HTTP/3 không được dùng vì proxy:** JDK built-in HttpClient không hỗ trợ HTTP/3 qua proxy. Khi proxy được chọn, `HTTP_3_URI_ONLY` thất bại; các mode khác có thể bị hạ xuống HTTP/2 hoặc HTTP/1.1. Hãy xác định proxy có được chọn từ cấu hình client hay từ `ProxySelector` mặc định.

**HTTP/3 không được dùng vì UDP:** HTTP/2 có thể chạy bình thường qua TCP trong khi UDP bị firewall chặn. Do đó, một request HTTPS thành công chưa chứng minh QUIC hoạt động.

**HTTP/3 không được dùng vì cấu hình TLS:** Không nên dùng custom `SSLContext` hoặc `SSLParameters` trong phép thử đầu tiên. Hãy bắt đầu bằng default SSL context để tách lỗi cấu hình ứng dụng khỏi lỗi mạng. Sau khi strict probe thành công, mới thêm trust store hoặc cấu hình TLS tùy biến và kiểm thử lại.

**Server có Alt-Svc nhưng request hiện tại là HTTP/2:** Header `Alt-Svc` chỉ là quảng bá endpoint thay thế. Nó không chứng minh response vừa nhận đã đi qua endpoint đó. Xác nhận bằng `response.version()` hoặc phép thử `HTTP_3_URI_ONLY`.

## 10. Checklist xác nhận kết quả

Một lần kiểm thử được xem là xác nhận HTTP/3 khi:

1. Ứng dụng chạy trên JDK 26 trở lên và dùng JDK built-in `HttpClient`.
2. URI dùng `https`.
3. Request đặt phiên bản ưu tiên `HTTP_3`.
4. Request dùng `HTTP_3_URI_ONLY` để loại trừ fallback.
5. Mạng cho phép kết nối QUIC qua UDP tới đúng endpoint.
6. Request nhận được response.
7. `HttpResponse.version()` trả về `HTTP_3`.
8. Không có tùy chọn bỏ xác minh chứng chỉ TLS.
9. Kết quả được ghi nhận từ đúng runtime và mạng của môi trường cần kiểm thử.

Khi kiểm thử khả năng khám phá thay vì chỉ kiểm tra endpoint, hãy bổ sung một lần chạy `ALT_SVC` với cùng `HttpClient` và ghi lại header `Alt-Svc` cùng phiên bản của từng response.

## 11. Kết luận

Để kiểm tra HTTP/3 bằng máy chủ thật, hãy dùng một endpoint công khai đã được xác nhận hỗ trợ như `https://www.google.com/`, sau đó gửi request bằng JDK built-in HttpClient với `HTTP_3_URI_ONLY`. Chỉ kết luận thành công khi `HttpResponse.version()` là `HTTP_3`.

Chế độ `ANY` phù hợp để quan sát lựa chọn giao thức trong điều kiện bình thường; nó có thể trả HTTP/2 dù server hỗ trợ HTTP/3. `ALT_SVC` phù hợp để kiểm tra quá trình server quảng bá endpoint và client sử dụng thông tin đó ở request tiếp theo. Dùng `curl --http3-only` như một phép đối chứng độc lập nếu build curl có hỗ trợ.

HTTP/3 phụ thuộc QUIC/UDP, proxy, TLS và endpoint cụ thể. Khi strict probe thất bại, hãy phân loại lỗi theo các yếu tố đó thay vì tự động coi server không hỗ trợ HTTP/3.

## Tài liệu tham khảo chính thức

- [JEP 517 — HTTP/3 for the HTTP Client API](https://openjdk.org/jeps/517)
- [HTTP/3 Support in JDK 26 — Inside Java](https://inside.java/2025/10/22/http3-support/)
- [HTTP Client Updates in Java 26 — Inside Java](https://inside.java/2026/03/04/jdk-26-http-client/)
- [HttpClient — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpClient.html)
- [HttpOption — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpOption.html)
- [HttpOption.Http3DiscoveryMode — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpOption.Http3DiscoveryMode.html)
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [curl — HTTP/3](https://curl.se/docs/http3.html)
- [curl command-line manual](https://curl.se/docs/manpage.html)
- [RFC 9114 — HTTP/3](https://www.rfc-editor.org/rfc/rfc9114.html)
- [RFC 7838 — HTTP Alternative Services](https://www.rfc-editor.org/rfc/rfc7838.html)

