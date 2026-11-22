# URL.openConnection, protocol handler và vòng đời trước/sau connect

## 1. Mục tiêu và bức tranh tổng quan

Trong Java networking, **java.net.URL** mô tả địa chỉ tài nguyên, còn **java.net.URLConnection** biểu diễn một đối tượng có thể thiết lập kết nối đến tài nguyên đó. Khi viết:

~~~java
URL url = new URL("https://example.com/data");
URLConnection connection = url.openConnection();
~~~

chúng ta **chưa mặc nhiên tải dữ liệu HTTP hoặc thực hiện TLS handshake**. Theo hợp đồng URL của Java 17, **openConnection() tạo một URLConnection mới thông qua URLStreamHandler của protocol**, nhưng **không thiết lập kết nối mạng thật tại thời điểm tạo đối tượng**. Trước khi kết nối, ứng dụng có cơ hội đặt request properties, timeout, cache flags và các tùy chọn khác.

Sau đó, kết nối có thể được thiết lập **tường minh** qua **connection.connect()**, hoặc **ngầm** khi ứng dụng gọi thao tác cần kết nối như **getInputStream()**, **getContentLength()** hay một số phương thức đọc response. Khi đã connected, phần lớn cấu hình request phải được coi là **đã khóa**, vì việc chỉnh headers, method hoặc option cấu hình lúc này quá muộn.

Bài học này trả lời năm câu hỏi trọng tâm:

1. **URL.openConnection() làm gì và chưa làm gì?**
2. **URLStreamHandler (protocol handler) được chọn như thế nào và nó tạo ra URLConnection loại gì?**
3. **Trước và sau connect() khác nhau ra sao; gọi phương thức nào có thể tự kích hoạt connect?**
4. **Khi dùng HTTP/HTTPS, nên xử lý request headers, response, timeout, proxy, lỗi và cleanup thế nào?**
5. **Làm thế nào tự kiểm tra được hành vi bằng chương trình Java 17 chạy thật, kể cả protocol handler tùy chỉnh?**

### Mô hình đơn giản

~~~text
URL("http://127.0.0.1:PORT/hello")
               |
           openConnection()
               |
   URLStreamHandler của "http"
               |
      HttpURLConnection object
      [chưa thiết lập request]
               |
      setRequestProperty(...)
      setConnectTimeout(...)
      setReadTimeout(...)
      setRequestMethod("GET")
               |
     connect() hoặc getInputStream()
               |
       [đã connected / I/O]
               |
     đọc status, headers và body
               |
      close InputStream, disconnect()
~~~

**Khái niệm cần nhớ:** Một đối tượng URLConnection biểu diễn **một lần cấu hình/kết nối cụ thể**. Nó không phải **HttpClient connection pool** và không được thiết kế để cứ thay URL hoặc method rồi tái sử dụng như một request mới.

## 2. Vai trò URL, URLConnection, URLStreamHandler và lớp con

| Thành phần | Trách nhiệm | Lưu ý |
| --- | --- | --- |
| **URL** | Chứa protocol, host, port, path, query, fragment; cung cấp openConnection | Tạo URL không đồng nghĩa gửi HTTP |
| **URLStreamHandler** | Biết cách phân tích và mở URL cho một scheme/protocol | Handler được chọn khi URL được tạo/khởi tạo theo quy tắc API |
| **URLStreamHandler.openConnection(URL)** | Tạo URLConnection phù hợp protocol | Không cần có kết nối mạng tại thời điểm trả về |
| **URLConnection** | Cấu hình và truy cập resource được URL trỏ tới | Có hai giai đoạn: chưa connected và đã connected |
| **HttpURLConnection** | URLConnection chuyên biệt cho **http** | Có method, status code, redirect, error stream, disconnect |
| **HttpsURLConnection** | HTTP trên TLS/HTTPS, là subclass của HttpURLConnection | Có thêm TLS peer, certificate và xác minh HTTPS |
| **JarURLConnection** | Truy cập nội dung trong JAR URL | Không phải mọi URLConnection là HTTP |
| **Proxy** và **ProxySelector** | Điều hướng đường đi kết nối khi handler hỗ trợ | Proxy không quyết định URL protocol hoặc nội dung resource |

Ví dụ đúng về kiểu đối tượng:

~~~java
URLConnection generic =
        new URL("http://127.0.0.1:8080/").openConnection();

if (generic instanceof HttpURLConnection http) {
    http.setRequestMethod("GET");
}
~~~

Ví dụ trên **chỉ minh họa class/type**; sẽ cần một HTTP server thật nếu muốn thực hiện network I/O. Không cast mù quáng mọi URLConnection sang HttpURLConnection: một URL **file:** hoặc **jar:** sẽ không phải HTTP.

Với URL HTTPS, **HttpsURLConnection** vẫn là một HttpURLConnection và có thêm logic SSL/TLS. Vì vậy **instanceof HttpURLConnection** có thể đúng cho cả HTTP và HTTPS, nhưng **HttpsURLConnection** không nên được coi như plaintext HTTP.

### URL và URI không giống hệt nhau

**URI** là định danh cú pháp, còn **URL** gắn với việc lựa chọn protocol handler/cách truy cập. Trong Java 17 có thể sử dụng:

~~~java
URI uri = URI.create("https://example.com/data");
URL url = uri.toURL();
URLConnection connection = url.openConnection();
~~~

Lệnh trên là snippet, cần import **java.net.URI, URL, URLConnection** và xử lý exceptions trong chương trình thực. Không được lấy bất kỳ chuỗi người dùng cung cấp rồi mở URL trực tiếp mà không kiểm tra scheme, host, port và quyền truy cập (xem phần bảo mật).

**Ghi chú phiên bản:** Một số constructor của URL bị deprecated trong các phiên bản Java mới hơn; với JDK hiện đại thường ưu tiên tạo URI rồi chuyển sang URL khi cần. Bài này vẫn dùng API **Java 17** đúng theo phạm vi học tập.

## 3. Protocol handler: vì sao cùng openConnection nhưng có các kết quả khác nhau?

### 3.1. URL chọn handler theo protocol

Trong một URL:

~~~text
https://api.example.com:443/orders?id=42
  |           |       |         |
protocol     host    port   path + query
~~~

**protocol** là phần đầu như **http, https, file, jar**. Khi URL được tạo, Java tìm **URLStreamHandler** phù hợp. Với JDK 17, Java bảo đảm có handler cho bốn protocol **http**, **https**, **file**, **jar**; có thể còn những protocol khác theo environment/provider.

Một URL handler được chọn **không chỉ từ chuỗi protocol** mà còn theo cấu hình hệ thống và SPI. Các con đường tiêu biểu trong Java 17:

1. **URLStreamHandlerFactory** được ứng dụng cài bằng **URL.setURLStreamHandlerFactory(factory)**, nếu có.
2. **java.net.spi.URLStreamHandlerProvider** được tìm theo cơ chế provider/ServiceLoader khi phù hợp.
3. Các package được khai báo trong system property **java.protocol.handler.pkgs**.
4. Handler tích hợp cho những protocol tiêu chuẩn.

Đây là tóm tắt đúng trọng tâm; Javadoc URL mô tả chi tiết việc xử lý khi provider trả null, class không có, ngoại lệ và tính implementation-specific của caching/order.

**Không tự tạo custom handler toàn JVM chỉ để thay đổi behavior của một URL thử nghiệm.** Có cách gắn một URLStreamHandler **trực tiếp cho URL instance**:

~~~java
URL special = new URL(null, "inmemdemo:/resource",
        new URLStreamHandler() {
            @Override
            protected URLConnection openConnection(URL u) {
                // Trả URLConnection tùy chỉnh.
                return new MyConnection(u);
            }
        });
~~~

**MyConnection ở snippet này chỉ là lớp minh họa**, không có sẵn trong JDK. Ví dụ hoàn chỉnh có **MemoryConnection** phía dưới và thực sự biên dịch/chạy được.

### 3.2. URL.openConnection() gọi handler.openConnection(URL)

Dòng:

~~~java
URLConnection connection = url.openConnection();
~~~

về mặt khái niệm tương đương luồng:

~~~text
URL object
  |
  +-- associated URLStreamHandler
           |
           +-- openConnection(url)
                     |
                     +-- new URLConnection subclass instance
                             (có thể là HttpURLConnection,
                              HttpsURLConnection, JarURLConnection
                              hoặc custom URLConnection)
~~~

**Mỗi lần URL.openConnection() tạo một URLConnection instance mới** thông qua handler. Hai lần gọi có thể cho hai object độc lập ngay cả khi dùng cùng một URL. Với HTTP, việc mở một HttpURLConnection mới **không đảm bảo có một TCP socket mới**: implementation có thể tái sử dụng socket/keep-alive ở tầng nội bộ sau khi các request trước được xử lý; phải phân biệt **request object** và **underlying transport connection**.

**URL.openStream()** là cách viết tắt để mở connection rồi lấy InputStream. Nó tiện khi chỉ cần đọc resource nhưng kém linh hoạt hơn nếu cần set timeout, HTTP method, request headers hoặc kiểm tra status.

### 3.3. Factory toàn JVM và provider cần được dùng có chủ đích

**URL.setURLStreamHandlerFactory(...)** là API cấu hình **global cho một JVM**, chỉ gọi thành công tối đa **một lần**. Gọi lần nữa có thể ném **Error**. Nó ảnh hưởng đến việc giải quyết protocol handler trên toàn application và class libraries, nên không phù hợp làm thay đổi ngầm trong một thư viện.

**URLStreamHandlerProvider** cho phép khai báo custom protocol handler thông qua service-provider mechanism; cách đóng gói module/service phải phù hợp với deployment. **java.protocol.handler.pkgs** dùng danh sách package phân cách bằng ký tự **|**, với class handler có quy ước **package.protocol.Handler**.

Để minh họa vòng đời trong một bài học, dùng **handler instance truyền thẳng vào URL** sẽ rõ phạm vi và tránh hiệu ứng global.

### 3.4. Không phải protocol nào cũng dùng HTTP

| Protocol | Loại handler/connection thường thấy | Điểm cần nhớ |
| --- | --- | --- |
| **http** | HttpURLConnection | Request method, status, response headers/body |
| **https** | HttpsURLConnection | HTTP + TLS, certificate/hostname verification |
| **file** | URLConnection do file handler cung cấp | Truy cập local file; không có HTTP status code |
| **jar** | JarURLConnection | Truy xuất resource trong JAR archive |
| **inmemdemo** trong ví dụ | MemoryConnection custom | Không có network; connect là trạng thái do custom class định nghĩa |

Không gọi getResponseCode() trên URLConnection bất kỳ vì đó là method của **HttpURLConnection**, không phải URLConnection generic. Khi thiết kế custom handler, subclass phải định nghĩa rõ ý nghĩa **connect()**, stream, headers, cache và trạng thái, thay vì giả định HTTP semantics.

## 4. Hai giai đoạn chính: trước connect và sau connect

Javadoc URLConnection mô tả quá trình chuẩn:

~~~text
CREATE
  |
  +-- url.openConnection()
  |       connected = false (đối với lifecycle thông thường)
  |
CONFIGURE
  | setConnectTimeout, setReadTimeout
  | setRequestProperty, addRequestProperty
  | setDoInput, setDoOutput, setUseCaches
  | setIfModifiedSince, request method (HTTP)
  |
CONNECT / FIRST OPERATION THAT NEEDS CONNECTION
  | connect()
  | getInputStream() / getOutputStream()
  | getContentLength() / một số response metadata getters
  |
CONNECTED
  | request đã bắt đầu theo protocol
  | request headers/method thường đã khóa
  | response headers/status/body có thể đọc
  |
CLEANUP
  | close opened streams
  | HttpURLConnection.disconnect() khi thích hợp
~~~

**Gọi connect() hai lần trên một URLConnection đã connected** được mô tả là lần sau bị bỏ qua theo hợp đồng URLConnection. Tuy nhiên điều đó **không biến object thành request reusable**. Muốn thực hiện một request khác với cấu hình khác, dùng **url.openConnection()** lần mới.

### 4.1. Những cấu hình cần làm trước connect

Ví dụ HTTP GET:

~~~java
HttpURLConnection connection =
        (HttpURLConnection) url.openConnection();

connection.setConnectTimeout(3_000); // milliseconds
connection.setReadTimeout(5_000);
connection.setRequestMethod("GET");
connection.setRequestProperty("Accept", "application/json");
connection.setRequestProperty("X-Request-Id", "example-42");
connection.setUseCaches(false);
connection.setDoInput(true);
~~~

**Đây là snippet có biến url**, không phải file độc lập. Các cấu hình này phải được thiết lập **trước khi thực hiện bất cứ operation nào có thể connect ngầm**.

| API | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| **setConnectTimeout(ms)** | Giới hạn thời gian chờ mở communications link | **0** là không giới hạn timeout này; chọn giá trị dương |
| **setReadTimeout(ms)** | Giới hạn chờ khi đọc dữ liệu | Không phải tổng deadline end-to-end; 0 tương ứng chờ vô thời hạn |
| **setRequestMethod("GET")** | Chọn phương thức HTTP | Chỉ dùng với HttpURLConnection và trước khi kết nối |
| **setRequestProperty(k,v)** | Đặt/ghi đè một request header | Sau connected có thể ném IllegalStateException |
| **addRequestProperty(k,v)** | Thêm một giá trị cho request property | Không phải cứ dùng với header bất kỳ là hợp lệ về HTTP |
| **setDoInput(true)** | Yêu cầu dùng connection cho input | Thường cần khi đọc response |
| **setDoOutput(true)** | Cho phép sử dụng output stream | Đặt trước khi lấy output stream/kết nối |
| **setUseCaches(false)** | Quyết định dùng cache do protocol handler hỗ trợ hay không | Không vô hiệu mọi proxy/server/CDN cache |
| **setIfModifiedSince(timeMillis)** | Gợi ý request chỉ lấy resource nếu mới hơn mốc chỉ định | Hành vi tùy protocol/HTTP handler |
| **setInstanceFollowRedirects(...)** | Chính sách redirect của **HttpURLConnection instance** | Cần suy xét bảo mật khi redirect sang host khác |

**Không coi setReadTimeout(5000) là giới hạn tối đa 5 giây cho toàn bộ request.** Read timeout liên quan tới thao tác đọc đang block, có thể lặp nhiều lần. Muốn deadline tổng, cần cơ chế timeout ở tầng application phù hợp.

### 4.2. Những API có thể kích hoạt kết nối ngầm

~~~java
URLConnection c = url.openConnection();
c.setConnectTimeout(3000);
c.setReadTimeout(3000);

try (InputStream input = c.getInputStream()) {
    byte[] data = input.readAllBytes();
}
~~~

Code không gọi **connect()** trực tiếp, nhưng **getInputStream() cần resource**, do đó tự thực hiện các bước kết nối. Một số getters response metadata như **getContentLength()**, **getContentType()**, **getHeaderField(...)** cũng có thể buộc URLConnection kết nối để đọc response.

**Cảnh báo:** đọc response headers **quá sớm** có thể vô tình đóng băng request settings. Không thực hiện getHeaderField, getContentLength hoặc getInputStream trước khi set đầy đủ method, timeout và headers.

Với HttpURLConnection, **getResponseCode()** cũng có thể khiến HTTP request được gửi để lấy status. Do đó **getResponseCode() không phải một thao tác kiểm tra metadata an toàn trước khi thiết lập request**.

### 4.3. Sau connect: request configuration bị khóa

Một số thay đổi sau khi đã connected là **sai trạng thái**:

~~~java
connection.connect();

// IllegalStateException đối với HttpURLConnection đã connected.
connection.setRequestProperty("Accept", "text/plain");
~~~

**HttpURLConnection.setRequestMethod(...)** sau connected cũng ném **ProtocolException** do kết nối đã thiết lập. Tùy API, việc set các tùy chọn sau connect có thể bị từ chối hoặc không có hiệu lực cho request hiện tại; quy tắc thực hành an toàn là **set request options trước mọi thao tác có thể kết nối**.

**Không nên đưa thông tin mới bằng một header sau khi response đã bắt đầu.** Header nào phải có trong request thì phải set trước khi request gửi đi.

### 4.4. Request objects và connections là hai khái niệm

~~~java
URLConnection first = url.openConnection();
URLConnection second = url.openConnection();
~~~

**first != second** ở mức đối tượng URLConnection mới trong cách dùng chuẩn; việc reuse TCP ở tầng implementation không làm hai object URLConnection thành cùng một instance. Một HttpURLConnection **không nên được tái sử dụng để gửi GET rồi sửa sang POST trên cùng object**. Tạo object mới khi cần request mới.

## 5. HTTP: connect() không luôn đồng nghĩa đã nhận response

Với HTTP, có nhiều mốc:

1. **Tạo HttpURLConnection object**: chưa gửi request theo lifecycle chuẩn.
2. **connect()**: mở liên kết liên lạc khi cần, có thể khởi tạo socket/proxy/TLS tùy handler. Không suy ra response body đã được tải đầy đủ.
3. **getOutputStream()** (nếu gửi body): có thể tự connect và bắt đầu quá trình gửi request.
4. **getResponseCode() / getInputStream()**: thực hiện I/O để lấy response status, headers hoặc body.
5. **Đóng stream / disconnect**: giải phóng tài nguyên được giữ bởi request object; tầng keep-alive có thể có policy riêng.

Trong ví dụ Java ở phần 8, chương trình xác nhận **openConnection() chưa tạo request được server quan sát**, còn **getInputStream()** có thể làm điều đó mà không gọi connect() rõ ràng.

**Không biến một lần chạy thành khẳng định connect() luôn gửi ngay HTTP request.** HttpURLConnection có thể trì hoãn từng bước giao thức tới khi cần I/O. Để xác minh một HTTP request thực sự đã đến server, kiểm tra hành vi ở server/status/body, không chỉ kiểm tra rằng đã gọi connect().

### 5.1. Đọc response HTTP đúng theo status

~~~java
HttpURLConnection http =
        (HttpURLConnection) url.openConnection();

http.setConnectTimeout(3000);
http.setReadTimeout(5000);
http.setRequestMethod("GET");
try {
    int status = http.getResponseCode();

    InputStream source = status >= 400
            ? http.getErrorStream()
            : http.getInputStream();

    if (source != null) {
        try (InputStream in = source) {
            // Đọc và xử lý body theo Content-Type/charset phù hợp.
        }
    }
} finally {
    http.disconnect();
}
~~~

Đoạn trên là snippet, không phải chương trình độc lập. **getErrorStream() có thể trả null** nếu không có error payload; khi response là 4xx/5xx, getInputStream() thường ném IOException, nên không dùng một nhánh getInputStream() duy nhất rồi xem mọi lỗi là lỗi network.

**HTTP status 404/500 là response của server**, không tự đồng nghĩa lỗi TCP hay TLS. Nếu cần ghi log hoặc retry, phải phân loại lỗi transport, lỗi HTTP response và logic nghiệp vụ.

### 5.2. GET và POST khác nhau ở bước cấu hình

Khi gửi POST có request body:

~~~java
HttpURLConnection post =
        (HttpURLConnection) url.openConnection();

post.setConnectTimeout(3000);
post.setReadTimeout(5000);
post.setRequestMethod("POST");
post.setDoOutput(true);
post.setRequestProperty("Content-Type", "application/json; charset=UTF-8");
post.setFixedLengthStreamingMode(bodyBytes.length);

try {
    try (OutputStream out = post.getOutputStream()) {
        out.write(bodyBytes);
    }
    int status = post.getResponseCode();
    // Đọc response body/error stream nếu cần.
} finally {
    post.disconnect();
}
~~~

**Đây là snippet có biến bodyBytes/url**, chưa phải file Java độc lập. Cần set request method, doOutput, Content-Type và streaming mode **trước getOutputStream()**, vì getOutputStream() có thể kết nối ngầm. Nếu dùng fixed length streaming mode, phải ghi đúng số byte đã khai báo; khi không đáp ứng có thể xảy ra IOException.

**Đừng tự giả định setDoOutput(true) là cách chuẩn để quyết định method POST.** Đặt method tường minh để hành vi rõ ràng trên các handler/protocol implementations.

### 5.3. Redirect, cache và response headers

HttpURLConnection có thể theo redirect theo cấu hình, nhưng **không phải mọi redirect HTTP 3xx luôn được follow**, và redirect thay đổi host/protocol/method có các hạn chế. Nếu request có header Authorization hoặc Cookie, cần kiểm tra chính sách chuyển tiếp credentials khi redirect; không tự chuyển secrets sang host khác.

**setUseCaches(false)** chỉ áp dụng cho behavior cache của URLConnection/handler theo khả năng của implementation, không thay mọi HTTP cache proxy/CDN hoặc server cache-control. **setIfModifiedSince(...)** có thể tạo một conditional request; response **304 Not Modified** là kết quả hợp lệ của caching/conditional HTTP, không phải lỗi connect.

**getHeaderFields()** trả metadata của response khi đã có; không dùng nó trước khi cấu hình hết request vì có thể gây kết nối ngầm. **getRequestProperties()** dùng để xem cấu hình request trước khi connected; sau khi connected có thể ném IllegalStateException.

## 6. HTTPS: cùng vòng đời nhưng có TLS/identity verification

Với URL HTTPS:

~~~java
URLConnection generic =
        new URL("https://example.com/api").openConnection();

if (generic instanceof HttpsURLConnection https) {
    https.setConnectTimeout(3000);
    https.setReadTimeout(5000);
    https.setRequestProperty("Accept", "application/json");
    // Lấy response/stream sẽ thực hiện kết nối HTTPS khi cần.
}
~~~

Handler HTTPS tạo **HttpsURLConnection**, là subclass của HttpURLConnection. HTTP request đi qua TLS; tùy implementation **connect()** hoặc thao tác I/O tiếp theo có thể dẫn tới TCP/proxy CONNECT, TLS handshake, certificate chain validation và hostname verification.

**Không tắt xác minh chứng chỉ hoặc hostname** để sửa kết nối HTTPS. Các anti-pattern phải tránh:

- TrustManager có **checkServerTrusted(...) rỗng**.
- HostnameVerifier trả **true** cho mọi hostname.
- SSLContext chấp nhận mọi server certificate.
- Chuyển về plaintext HTTP chỉ vì TLS báo lỗi.

Nếu gặp SSLHandshakeException, cần kiểm tra **chain/truststore, SAN/hostname, thời gian, TLS algorithm policy và proxy/TLS termination**. Một SSLContext hoặc SSLSocketFactory tùy chỉnh phải giữ việc xác minh phù hợp.

### HTTPS và thời điểm không thể thay đổi cấu hình

Nếu cần **HttpsURLConnection.setSSLSocketFactory(...)** hay **setHostnameVerifier(...)** hợp lệ (theo policy), phải thực hiện trước khi kết nối. Tốt nhất dùng **default verification** của JVM, hoặc truststore được quản trị với CA đã xác minh. Sau khi đã kết nối, đổi các cấu hình đó không làm handshake đã xảy ra được xác minh lại.

**HTTPS không thay đổi nguyên tắc hai pha:** openConnection tạo object trước; connect/I/O mới yêu cầu liên kết và dữ liệu. Những nơi một HTTPS handler thực thi TLS handshake cụ thể là chi tiết của implementation, không suy ra từ câu lệnh new URL(...) đơn thuần.

## 7. Proxy, timeout, cache và vòng đời tài nguyên

### 7.1. URL.openConnection(Proxy)

Một overload hỗ trợ proxy tường minh:

~~~java
Proxy proxy = new Proxy(
        Proxy.Type.HTTP,
        new InetSocketAddress("proxy.example.test", 3128));

URLConnection connection = url.openConnection(proxy);
~~~

Theo Javadoc Java 17, **openConnection(proxy)** ưu tiên lựa chọn proxy tường minh thay cho **ProxySelector mặc định** của hệ thống; protocol handler có thể không hỗ trợ proxying và bỏ qua proxy parameter hoặc ném UnsupportedOperationException tùy handler. Nếu muốn kết nối direct theo API, dùng **Proxy.NO_PROXY** thay vì **null**.

**Tuyệt đối không tự thử proxy.example.test trong ví dụ này nếu chưa được cấu hình môi trường thực tế**; đây chỉ là snippet minh họa và không được sử dụng bởi test loopback ở phần 8.

### 7.2. Connect timeout và read timeout

- **setConnectTimeout(ms)**: giới hạn chờ mở communications link; không bao trùm toàn bộ xử lý request.
- **setReadTimeout(ms)**: giới hạn chờ dữ liệu khi một read block; nếu không có dữ liệu trong giới hạn, có thể gặp **SocketTimeoutException**.
- **0** thường có nghĩa không giới hạn chờ cho timeout tương ứng.
- Có thể cần **deadline tổng** do ứng dụng quản lý nếu tải dữ liệu lớn hoặc server liên tục gửi byte nhỏ để tránh read timeout nhưng kéo dài toàn request.

Nếu timeout xảy ra, **luôn đóng stream/cleanup** trong finally/try-with-resources. Đừng giữ URLConnection object rồi dùng lại cho retry như một request mới. Khi cần retry, tạo URLConnection mới, tính lại thời gian/giới hạn số lần và chỉ retry operation hợp lệ theo idempotency.

### 7.3. Dọn stream và disconnect

~~~java
HttpURLConnection http =
        (HttpURLConnection) url.openConnection();
try {
    http.setConnectTimeout(3000);
    http.setReadTimeout(5000);
    try (InputStream input = http.getInputStream()) {
        // Đọc body, đóng stream tự động.
    }
} finally {
    http.disconnect();
}
~~~

**Đóng InputStream** là cách giải phóng tài nguyên của stream. **disconnect()** báo rằng các request khác tới server có thể không còn được thực hiện trong thời gian gần, và **không làm HttpURLConnection instance dùng lại được**. Bên dưới, HTTP keep-alive/connection pool có thể quyết định khi nào socket vật lý được đóng hay tái sử dụng. Không diễn giải một lệnh disconnect() như bằng chứng rằng mọi TCP connection liên quan đã bị đóng lập tức trong mọi implementation.

Nếu response có error body, dùng **getErrorStream()** đúng khi có; stream đó cũng cần đóng. Không đọc body vô hạn vào RAM nếu response không tin cậy; dùng giới hạn bytes/streaming và Content-Length chỉ là hint.

### 7.4. Không chia sẻ HttpURLConnection như một object mutable giữa threads

URLConnection được cấu hình qua nhiều setter mutable và có một trạng thái connected cụ thể. Không thiết kế nhiều thread đồng thời sửa request properties/connect/read cùng một instance mà không có đồng bộ/ownership rõ. Cách đơn giản: **mỗi request dùng một URLConnection mới**, phân định trách nhiệm đóng tài nguyên rõ ràng.

Đây là API kiểu blocking; nếu cần nhiều request bất đồng bộ, HTTP/2, cancellation, streaming và thread-management cao cấp, **java.net.http.HttpClient** (Java 11+) thường phù hợp hơn. Đừng nhầm **HttpClient.sendAsync** với **URL.openConnection**: chúng là các API khác nhau.

## 8. Chương trình Java 17+ chạy thật: HTTP loopback và protocol handler tùy chỉnh

Chương trình **URLConnectionLifecycleDemo.java** không cần Internet. Nó tạo một HTTP server trong JVM trên **127.0.0.1** và cổng động, sau đó:

1. Gọi **URL.openConnection()** cho URL HTTP, assert trả về **HttpURLConnection** và **server chưa nhận request**.
2. Set timeout, GET, header và useCaches trước khi connect.
3. Gọi **connect()**, thử **setRequestProperty(...)** muộn, assert ném **IllegalStateException**.
4. Gọi **getInputStream()** để đọc response **HELLO:explicit**.
5. Tạo URLConnection mới từ **cùng URL**, **không gọi connect()** mà gọi trực tiếp **getInputStream()**. Server nhận request và trả **HELLO:implicit**.
6. Xác nhận server xử lý đúng **2 HTTP requests**.
7. Tạo URL **inmemdemo:/resource** với một **URLStreamHandler custom** truyền trực tiếp vào constructor, trả **MemoryConnection** không dùng mạng.
8. MemoryConnection chỉ tăng bộ đếm khi connect lần đầu; đọc stream làm connect ngầm, gọi connect lần hai không tăng bộ đếm.
9. Đóng streams, disconnect hai HttpURLConnection, stop local server và shutdown worker pool.

Mã dùng **JDK 17** và module chuẩn **jdk.httpserver**. Không đụng tới URLStreamHandlerFactory global, proxy global hay cấu hình certificate. Handler **inmemdemo** chỉ gắn với URL instance được tạo trong chương trình; không tự đăng ký thành protocol global cho mọi URL string.

### Tệp URLConnectionLifecycleDemo.java

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URL;
import java.net.URLConnection;
import java.net.URLStreamHandler;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class URLConnectionLifecycleDemo {
    static void require(boolean ok, String why) {
        if (!ok) throw new AssertionError(why);
    }

    static String readText(URLConnection connection) throws IOException {
        try (InputStream input = connection.getInputStream()) {
            return new String(
                    input.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    static final class MemoryConnection extends URLConnection {
        final AtomicInteger connects;

        MemoryConnection(URL url, AtomicInteger connects) {
            super(url);
            this.connects = connects;
        }

        @Override
        public void connect() {
            if (!connected) {
                connected = true;
                connects.incrementAndGet();
            }
        }

        @Override
        public InputStream getInputStream() {
            if (!connected) connect();
            return new ByteArrayInputStream(
                    "MEMORY_OK".getBytes(StandardCharsets.UTF_8));
        }
    }

    public static void main(String[] args) throws Exception {
        AtomicInteger hits = new AtomicInteger();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);
        ExecutorService serverWorkers =
                Executors.newFixedThreadPool(2);
        server.setExecutor(serverWorkers);

        server.createContext("/hello", exchange -> {
            try {
                hits.incrementAndGet();
                String header = exchange.getRequestHeaders()
                        .getFirst("X-Lifecycle");
                byte[] bytes = ("HELLO:" + header)
                        .getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(200, bytes.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(bytes);
                }
            } finally {
                exchange.close();
            }
        });

        try {
            server.start();
            URL endpoint = new URL("http://127.0.0.1:" +
                    server.getAddress().getPort() + "/hello");
            URLConnection opened = endpoint.openConnection();

            require(opened instanceof HttpURLConnection,
                    "Wrong HTTP handler type");
            require(hits.get() == 0,
                    "openConnection sent a request");
            System.out.println("HTTP handler selected: true");
            System.out.println(
                    "No request at openConnection: true");

            HttpURLConnection explicit =
                    (HttpURLConnection) opened;
            explicit.setConnectTimeout(3000);
            explicit.setReadTimeout(3000);
            explicit.setRequestMethod("GET");
            explicit.setRequestProperty(
                    "X-Lifecycle", "explicit");
            explicit.setUseCaches(false);

            try {
                explicit.connect();

                boolean rejected = false;
                try {
                    explicit.setRequestProperty(
                            "X-Lifecycle", "too-late");
                } catch (IllegalStateException expected) {
                    rejected = true;
                }

                require(rejected,
                        "Mutable setting allowed after connect");
                System.out.println(
                        "Post-connect mutation rejected: true");

                String response = readText(explicit);
                require("HELLO:explicit".equals(response),
                        "Explicit response mismatch");
                System.out.println(
                        "Explicit response: " + response);
            } finally {
                explicit.disconnect();
            }

            HttpURLConnection implicit =
                    (HttpURLConnection) endpoint.openConnection();
            implicit.setConnectTimeout(3000);
            implicit.setReadTimeout(3000);
            implicit.setRequestProperty(
                    "X-Lifecycle", "implicit");

            try {
                String response = readText(implicit);
                require("HELLO:implicit".equals(response),
                        "Implicit response mismatch");
                System.out.println(
                        "Implicit response: " + response);
            } finally {
                implicit.disconnect();
            }

            require(hits.get() == 2,
                    "HTTP server request count mismatch");
            System.out.println(
                    "HTTP requests observed: " + hits.get());

            AtomicInteger connects = new AtomicInteger();
            URL special = new URL(
                    null, "inmemdemo:/resource",
                    new URLStreamHandler() {
                        @Override
                        protected URLConnection openConnection(URL u) {
                            return new MemoryConnection(u, connects);
                        }
                    });

            URLConnection virtual = special.openConnection();
            require(virtual instanceof MemoryConnection,
                    "Custom protocol handler not selected");
            require(connects.get() == 0,
                    "Custom connection too early");

            String text = readText(virtual);
            require("MEMORY_OK".equals(text),
                    "Custom body mismatch");

            virtual.connect();
            require(connects.get() == 1,
                    "connect is not idempotent");

            System.out.println(
                    "Custom protocol: " + special.getProtocol());
            System.out.println("Custom response: " + text);
            System.out.println(
                    "Custom connect calls: " + connects.get());
        } finally {
            server.stop(0);
            serverWorkers.shutdown();
            if (!serverWorkers.awaitTermination(
                    5, TimeUnit.SECONDS)) {
                serverWorkers.shutdownNow();
            }
        }

        require(serverWorkers.isTerminated(),
                "Server workers still running");
        System.out.println(
                "Server executor terminated: true");
    }
}
~~~

### Cách biên dịch và chạy

Lưu file với tên chính xác **URLConnectionLifecycleDemo.java**. Dùng **JDK 17 trở lên**:

~~~bash
javac --release 17 --add-modules jdk.httpserver -encoding UTF-8 URLConnectionLifecycleDemo.java
java --add-modules jdk.httpserver URLConnectionLifecycleDemo
~~~

**Stdout đã biên dịch/chạy thực tế với mã Java 17 tương đương trên JVM và được xác minh từng dòng:**

~~~text
HTTP handler selected: true
No request at openConnection: true
Post-connect mutation rejected: true
Explicit response: HELLO:explicit
Implicit response: HELLO:implicit
HTTP requests observed: 2
Custom protocol: inmemdemo
Custom response: MEMORY_OK
Custom connect calls: 1
Server executor terminated: true
~~~

**Tại sao kết quả có thể dự đoán?** Chương trình dùng loopback và **port 0** (hệ điều hành chọn một cổng còn trống); nó không in port hoặc ID ngẫu nhiên. Bộ đếm server **hits** tăng khi handler nhận request và cả hai response được so sánh với giá trị mong đợi. Custom handler không dùng socket nên connect count do chương trình tự kiểm soát. Việc kiểm tra gọi connect muộn được thực hiện với **cờ boolean** dựa trên exception, không phụ thuộc vào chuỗi thông báo lỗi có thể khác giữa JDK vendors.

**Điểm hạn chế có chủ đích:** Chương trình dùng HTTP/1.1 loopback chứ không có HTTPS certificate hay proxy; phần TLS/proxy chỉ được hướng dẫn dưới dạng minh họa API để tránh phát sinh phụ thuộc môi trường. Demo không chứng minh một HTTPS endpoint công khai hoạt động, mà xác minh rõ lifecycle của URLConnection và handler.

### Phân tích các dòng kết quả

- **HTTP handler selected: true**: URL protocol **http** tạo một đối tượng HttpURLConnection.
- **No request at openConnection: true**: server chưa quan sát request sau khi chỉ tạo object.
- **Post-connect mutation rejected: true**: setRequestProperty sau connect ném IllegalStateException như kỳ vọng.
- **Explicit response: HELLO:explicit**: cấu hình header trước connect đã được server đọc.
- **Implicit response: HELLO:implicit**: getInputStream đã thực hiện kết nối dù code không gọi connect trực tiếp.
- **HTTP requests observed: 2**: openConnection lần hai tạo request object khác, và hai lần đọc đã tạo hai HTTP requests.
- **Custom protocol: inmemdemo**: URL instance dùng handler mà chương trình đã cung cấp.
- **Custom response: MEMORY_OK**: MemoryConnection trả resource từ bộ nhớ mà không dùng network.
- **Custom connect calls: 1**: getInputStream gọi connect nếu cần; gọi connect tiếp bị bỏ qua trong custom implementation.
- **Server executor terminated: true**: local server worker pool đã shutdown và không giữ thread sống sau khi chương trình kết thúc.

## 9. Khi nào protocol handler custom có ích?

Custom URLStreamHandler và URLConnection có thể dùng cho:

1. **Testing/in-memory resource** không muốn phụ thuộc mạng.
2. **Protocol nội bộ** có resource naming riêng.
3. **Adapter cho resource storage** có semantics URL-like.
4. **Resource loaders hoặc integration hooks** với một hệ thống đã có nhu cầu quản lý protocol thực sự.

Tuy nhiên, thiết kế handler có những nghĩa vụ:

- **Protocol parser** phải phân tích URL đúng, không chấp nhận input mơ hồ gây rủi ro.
- **openConnection** phải tạo đối tượng có lifecycle rõ ràng, không lén giữ network/background tasks mà caller không biết.
- **connect()** cần đặt connected flag nhất quán, quản lý failure và tránh tạo resource trùng khi gọi nhiều lần.
- **getInputStream()/getOutputStream()** phải xử lý I/O, lỗi và đóng stream đúng hợp đồng.
- **Request metadata và response metadata** phải có semantics được tài liệu hóa; đừng giả vờ custom protocol có HTTP status.
- **Thread safety và ownership** phải được quyết định rõ nếu ứng dụng chia sẻ URL/handler state.
- **Global registration** qua factory hoặc provider phải xét thứ tự khởi tạo, security, classloading và khả năng ảnh hưởng toàn JVM.

Ví dụ MemoryConnection cố tình đơn giản: connect chỉ đánh dấu trạng thái, stream đọc từ byte[] bất biến. Đây là protocol handler có thể kiểm thử chính xác lifecycle, không phải lời hứa về behavior của tất cả handler trong JDK.

### Protocol không nhận diện được thì sao?

Nếu không tìm được handler phù hợp với protocol khi tạo URL, Java có thể ném **MalformedURLException: unknown protocol**. Không phải mọi chuỗi có dấu hai chấm đều là URL được hỗ trợ bởi JVM.

Nếu muốn protocol custom xuất hiện qua **new URL("inmemdemo:...")** ở nhiều nơi trong ứng dụng, cần đăng ký handler qua cơ chế thích hợp (factory/provider/property) thay vì chỉ gắn handler cho một URL instance như demo.

## 10. Những lỗi thường gặp

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| **Cho rằng openConnection() đã gửi request** | Nó tạo URLConnection object, không thiết lập kết nối mạng ngay | Cấu hình trước, connect/read sau |
| **Gọi getInputStream trước setRequestProperty** | getInputStream có thể connect ngầm | Đặt method, headers, timeout trước mọi response getter |
| **Đặt request header sau connect()** | IllegalStateException hoặc quá muộn | Tạo URLConnection mới nếu cần request khác |
| **Dùng cùng HttpURLConnection cho nhiều HTTP requests** | Đối tượng không phải reusable request builder | Mỗi request tạo connection object mới |
| **Cast file:/jar: sang HttpURLConnection** | Handler trả loại URLConnection khác | Dùng instanceof và phân loại protocol |
| **Cho rằng connect() luôn tải hết body** | HTTP có thể trì hoãn gửi/lấy response tới I/O tiếp theo | Xem getResponseCode, stream và server-side evidence |
| **Đọc mọi status bằng getInputStream** | Với 4xx/5xx có thể ném IOException | Xem status và getErrorStream |
| **Không đóng InputStream hoặc error stream** | Giữ file/socket/buffer | try-with-resources và cleanup trong finally |
| **Cho rằng disconnect() bảo đảm socket vật lý đóng ngay** | Keep-alive/resource management tùy implementation | Hiểu API semantics, đo sockets thực nếu cần |
| **Không set timeout** | Client có thể chờ lâu/vô hạn | setConnectTimeout, setReadTimeout và deadline ứng dụng |
| **Tin setUseCaches(false) vô hiệu mọi CDN** | Nó chỉ là option handler | Phân biệt client cache, proxy/CDN và server cache |
| **Thay toàn JVM URLStreamHandlerFactory trong library** | Chỉ set một lần và ảnh hưởng global | Dùng handler instance hoặc provider có quản trị |
| **Dùng URL.openConnection(Proxy) để truyền null** | API yêu cầu Proxy hợp lệ | Dùng Proxy.NO_PROXY nếu muốn direct |
| **Tắt xác minh hostname/certificate khi HTTPS lỗi** | Làm yếu TLS identity | Sửa CA/chain/SAN hoặc proxy/TLS config |
| **Open URL từ input không tin cậy mà không kiểm tra** | Rủi ro SSRF, truy cập metadata/internal network | Allowlist scheme/host/port; chặn redirect và địa chỉ nội bộ không được phép |
| **Dùng HttpURLConnection từ nhiều thread và sửa đồng thời** | Request object mutable và lifecycle khó kiểm soát | Sở hữu một request ở một flow/thread rõ ràng |
| **Nhầm URLConnection với HttpClient.sendAsync** | Hai API khác nhau | Chọn HTTP client theo nhu cầu concurrency, streaming và timeout |

## 11. Bảo mật khi URL đến từ dữ liệu không tin cậy

**SSRF (Server-Side Request Forgery)** có thể xảy ra nếu một service cho client gửi bất kỳ URL rồi server lập tức openConnection/getInputStream với quyền mạng nội bộ của server.

Ví dụ kẻ tấn công có thể thử URL trỏ tới:

- **127.0.0.1 hoặc ::1**, các dịch vụ chỉ mở localhost.
- **Private network** hoặc internal hostname.
- **Cloud metadata endpoint** không dành cho người dùng.
- **file:** URL để cố truy cập file cục bộ.
- **jar:** hay protocol handler custom có side effects.
- URL **http(s)** công khai nhưng chuyển **redirect** tới địa chỉ nội bộ.

Hướng phòng vệ:

1. **Parse URI** và chấp nhận **chỉ scheme cần thiết**, thường chỉ HTTPS.
2. **Allowlist hostname và port** theo nghiệp vụ; không dùng blacklist chuỗi thô làm kiểm soát chính.
3. Kiểm tra URL **sau mỗi redirect**, không chỉ URL ban đầu; nếu có thể thì tắt auto-follow và kiểm tra redirect thủ công.
4. Kiểm soát **DNS resolution, IP ranges, rebinding** phù hợp với môi trường; allowlist hostname đơn giản không đủ bảo vệ mọi DNS-based SSRF.
5. Đặt **timeouts, giới hạn redirect, response size và concurrency**.
6. Không đưa Authorization/Cookie/token sang một origin mới nếu chưa được phép.
7. Không cho phép một URL custom protocol handler thực hiện local file/process access trái quyền.

**Gọi openConnection() tự nó chưa phát request không có nghĩa URL đó an toàn**: nó tạo handler-specific object, và các I/O sau đó có thể xảy ra trong một code path tưởng như chỉ đọc metadata.

## 12. Các câu hỏi tự kiểm tra

**Câu 1.** URL.openConnection() có lập tức kết nối mạng không?  
**Trả lời:** Theo hợp đồng Java 17, nó tạo một URLConnection object mới qua protocol handler mà không tự thiết lập kết nối mạng tại thời điểm tạo.

**Câu 2.** URL.openConnection() tạo một instance mới mỗi lần hay trả cùng object?  
**Trả lời:** Tạo URLConnection instance mới qua URLStreamHandler.openConnection(URL) mỗi lần. Điều đó không đảm bảo một TCP socket vật lý mới mỗi lần.

**Câu 3.** Tại sao HttpURLConnection và HttpsURLConnection đều là URLConnection?  
**Trả lời:** Chúng là các lớp con chuyên biệt thực thi hành vi HTTP/HTTPS; URL chọn handler theo protocol.

**Câu 4.** Có thể gọi setRequestProperty sau connect()?  
**Trả lời:** Không; với HttpURLConnection đã connected, nó ném IllegalStateException.

**Câu 5.** Nếu không gọi connect(), getInputStream() có thể làm request chạy không?  
**Trả lời:** Có. Thao tác cần resource sẽ tự kết nối khi cần.

**Câu 6.** getContentLength() và getResponseCode() có luôn là metadata getter không cần I/O không?  
**Trả lời:** Không. Khi cần response chúng có thể kích hoạt kết nối ngầm.

**Câu 7.** setConnectTimeout(3000) tính bằng giây hay milliseconds?  
**Trả lời:** Milliseconds; 3000 ms = 3 giây.

**Câu 8.** setReadTimeout có phải deadline tổng cho cả request?  
**Trả lời:** Không. Nó liên quan tới các thao tác read chờ dữ liệu; cần deadline tổng riêng.

**Câu 9.** Tại sao không cast mọi URLConnection thành HttpURLConnection?  
**Trả lời:** Handler có thể trả JarURLConnection, file URLConnection hoặc custom URLConnection không hỗ trợ HTTP.

**Câu 10.** Khi request trả HTTP 404, nên đọc response bằng gì?  
**Trả lời:** Kiểm tra getResponseCode và có thể đọc getErrorStream nếu tồn tại, không mặc định getInputStream sẽ trả body bình thường.

**Câu 11.** HttpURLConnection.disconnect() có làm object sẵn sàng để gửi request mới không?  
**Trả lời:** Không. Tạo một HttpURLConnection khác từ url.openConnection() cho request mới.

**Câu 12.** Dùng URL.setURLStreamHandlerFactory bao nhiêu lần trong một JVM?  
**Trả lời:** Chỉ cài thành công tối đa một lần. Đây là cấu hình global, cần dùng thận trọng.

**Câu 13.** Có phải custom URLStreamHandler luôn yêu cầu network?  
**Trả lời:** Không. Trong demo, MemoryConnection trả stream từ byte[] và không tạo socket.

**Câu 14.** Gọi URL.openConnection(Proxy.NO_PROXY) để làm gì?  
**Trả lời:** Chọn đường direct thay vì proxy, khi handler hỗ trợ overload; khác truyền null không hợp lệ.

**Câu 15.** Vì sao SSRF vẫn là rủi ro nếu openConnection chưa kết nối?  
**Trả lời:** Vì getInputStream/getResponseCode và các thao tác về sau có thể kết nối ngầm tới URL do input không tin cậy chỉ định.

**Câu 16.** HTTPS có cho phép tắt hostname check để tránh handshake error không?  
**Trả lời:** Không nên. Cần sửa CA/chain/SAN và trust policy đúng để giữ TLS server authentication.

## Kết luận

Hãy nhớ chuỗi **URL → protocol handler → URLConnection object → configure → connect/implicit I/O → read/write → cleanup**.

**openConnection() chuẩn bị đối tượng**, không tự gửi resource request. **connect()** đánh dấu/thiết lập liên kết và là ranh giới cấu hình; các phương thức cần response có thể tự connect mà code không viết connect rõ ràng. **Protocol handler** quyết định subclass và semantics cụ thể: HTTP có HttpURLConnection, HTTPS có HttpsURLConnection, file/jar có cơ chế riêng và custom handler có thể tạo resource hoàn toàn không cần network.

Với HTTP/HTTPS, cần **thiết lập trước tất cả request properties và timeouts**, xử lý status/error stream, đóng streams/disconnect đúng vòng đời, không dùng lại cùng HttpURLConnection instance cho request khác. Khi URL nhận từ input, phải đặc biệt kiểm soát SSRF, redirects và TLS identity.

### Tài liệu tham khảo chính thức

- [Java SE 17 — URL](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URL.html): openConnection(), handler resolution, openStream, proxy overload và factory.
- [Java SE 17 — URLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLConnection.html): hai giai đoạn, connect() và các setters/getters.
- [Java SE 17 — URLStreamHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLStreamHandler.html): openConnection(URL) và protocol-dependent behavior.
- [Java SE 17 — URLStreamHandlerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLStreamHandlerFactory.html): tạo URLStreamHandler.
- [Java SE 17 — URLStreamHandlerProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/spi/URLStreamHandlerProvider.html): service provider cho custom protocol.
- [Java SE 17 — HttpURLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpURLConnection.html): HTTP method, response status, error stream, redirects, disconnect.
- [Java SE 17 — HttpsURLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/HttpsURLConnection.html): HTTPS và TLS session.
- [Java SE 17 — Proxy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Proxy.html): explicit proxy và Proxy.NO_PROXY.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): server loopback thử nghiệm.
- [RFC 3986 — URI Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986.html): xử lý URI/URL và vấn đề security considerations.
