# Tái sử dụng HttpClient và quản lý connection pool

Trong ứng dụng Java, hãy tạo một HttpClient cho mỗi cấu hình giao tiếp cần dùng lâu dài và tái sử dụng nó cho nhiều request. Mỗi HttpClient của JDK thường quản lý các connection pool riêng; tạo client mới cho từng request thường làm mất cơ hội tái sử dụng kết nối và phát sinh thêm chi phí thiết lập TCP, TLS hoặc QUIC.

Java 26 cung cấp API HttpClient chính thức trong module java.net.http. API cho phép gửi request đồng bộ hoặc bất đồng bộ, dùng HTTP/1.1, HTTP/2 và HTTP/3, đồng thời quản lý kết nối ở bên trong client. Ứng dụng cần hiểu vòng đời client, cách response body được tiêu thụ và phạm vi thật sự của các system property trước khi điều chỉnh connection pool.

## 1. Vì sao cần tái sử dụng HttpClient?

Thiết lập một kết nối HTTP mới có thể cần nhiều bước: phân giải DNS, mở TCP connection, thực hiện TLS handshake và thương lượng HTTP/2 qua ALPN. Với HTTP/3, client cần thiết lập QUIC connection và bắt tay TLS tích hợp trong QUIC. Những bước này tiêu tốn thời gian, CPU và tài nguyên mạng.

Khi dùng lại một HttpClient, triển khai có thể tái sử dụng kết nối còn hợp lệ đến cùng origin. Lợi ích thường thấy:

- Giảm số lần mở socket và thực hiện handshake.
- Giảm độ trễ cho request tiếp theo đến cùng máy chủ.
- Giảm chi phí CPU cho TLS và thiết lập giao thức.
- Dùng lại connection HTTP/2 hoặc HTTP/3 để truyền nhiều stream đồng thời khi máy chủ và mạng cho phép.
- Tập trung cấu hình proxy, TLS, authenticator, cookie và chính sách redirect tại một nơi.
- Giảm số lượng client, executor và tài nguyên nền cần quản lý.

Một HttpClient đã được tạo là immutable: cấu hình của client không thay đổi sau khi build. Có thể dùng cùng instance để gửi nhiều request từ nhiều phần của ứng dụng. Mỗi client thường quản lý pool kết nối của chính nó; pool thường không được chia sẻ giữa các HttpClient khác nhau.

Vì vậy, cách tạo client mới trong mỗi lần gọi API thường không có lợi:

~~~java
// Không nên tạo client mới trong mỗi request.
HttpResponse<String> fetch(URI uri)
        throws IOException, InterruptedException {

    HttpClient client = HttpClient.newHttpClient();

    HttpRequest request = HttpRequest.newBuilder(uri)
            .GET()
            .build();

    return client.send(
            request,
            HttpResponse.BodyHandlers.ofString());
}
~~~

Client trong ví dụ trên chỉ được dùng một lần. Những request tiếp theo tạo ra client khác và thường không thể tái sử dụng pool của client trước. Ngoài ra, ứng dụng khó kiểm soát vòng đời các tài nguyên nền do nhiều client tạo ra.

## 2. Connection pool hoạt động khác nhau theo phiên bản HTTP

Connection pool là cơ chế nội bộ giữ lại các kết nối có thể tái sử dụng. Java API không yêu cầu ứng dụng tự quản lý socket hoặc tự đưa connection vào pool.

| Giao thức | Cách tái sử dụng thường gặp | Điều cần lưu ý |
|---|---|---|
| HTTP/1.1 | Kết nối keep-alive có thể phục vụ các request nối tiếp đến cùng origin | Request đồng thời có thể cần nhiều kết nối; response body cần được tiêu thụ hoặc đóng để kết nối có cơ hội được tái sử dụng |
| HTTP/2 | Một connection có nhiều stream, cho phép nhiều request/response cùng hoạt động | Số stream đồng thời chịu ảnh hưởng bởi giới hạn peer và triển khai; không mặc định một request luôn có một connection |
| HTTP/3 | Một QUIC connection có thể mang nhiều stream HTTP/3 | Connection sử dụng UDP và QUIC; thời gian giữ connection nhàn rỗi có thể được cấu hình bằng property riêng của JDK |

**HTTP/1.1:** sau khi một response được đọc hết, connection keep-alive có thể quay lại cache để phục vụ request tiếp theo. Nếu ứng dụng giữ response body dạng stream mà không đọc hết hoặc đóng, kết nối có thể chưa sẵn sàng để tái sử dụng.

**HTTP/2:** multiplexing cho phép nhiều stream trên cùng một connection. Client có thể gửi nhiều request đồng thời mà không cần mở một TCP connection cho từng request. Tuy nhiên, server có thể giới hạn số stream đồng thời, và client có thể cần thêm connection trong những tình huống cụ thể.

**HTTP/3:** nhiều stream có thể chạy trên cùng QUIC connection. Connection có thể được tái sử dụng cho các request tiếp theo khi còn hợp lệ. Cấu hình proxy, UDP, TLS và cơ chế phát hiện HTTP/3 vẫn ảnh hưởng việc giao thức có được sử dụng hay không.

Ứng dụng không được giả định rằng một origin luôn chỉ có đúng một connection, hoặc rằng mọi request sẽ luôn dùng cùng một connection. Quyết định cụ thể thuộc về HttpClient và phụ thuộc giao thức, trạng thái mạng, giới hạn server, thời gian nhàn rỗi và lỗi kết nối.

## 3. Tạo một HttpClient dùng chung trong ứng dụng

Một ứng dụng thường nên quản lý HttpClient ở phạm vi phù hợp với vòng đời ứng dụng:

- Ứng dụng dòng lệnh: tạo client ở đầu chương trình, truyền vào các hàm cần gửi request và đóng khi chương trình hoàn tất.
- Ứng dụng web hoặc dịch vụ: đăng ký client như một dependency dùng chung hoặc singleton do container quản lý.
- Ứng dụng có nhiều nhóm endpoint cần cấu hình TLS, proxy hoặc xác thực khác nhau: tạo một client cho mỗi cấu hình cần cách ly và tái sử dụng từng client đó.

Ví dụ dưới đây tạo client một lần, sau đó dùng cho nhiều request:

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class ReusedHttpClientDemo {

    private static HttpResponse<String> get(
            HttpClient client,
            URI uri)
            throws IOException, InterruptedException {

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(15))
                .GET()
                .build();

        return client.send(
                request,
                HttpResponse.BodyHandlers.ofString());
    }

    public static void main(String[] args)
            throws IOException, InterruptedException {

        try (HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2)
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build()) {

            URI firstUri = URI.create("https://api.example.test/profile");
            URI secondUri = URI.create("https://api.example.test/orders");

            HttpResponse<String> first = get(client, firstUri);
            HttpResponse<String> second = get(client, secondUri);

            System.out.println(first.statusCode());
            System.out.println(second.statusCode());
        }
    }
}
~~~

Đây là ví dụ minh họa cách truyền cùng client cho hai thao tác. Thay hai URI bằng endpoint HTTPS thực tế của ứng dụng. Nếu hai URI cùng origin và connection vẫn hợp lệ, HttpClient có thể tái sử dụng connection đã mở.

Trong ứng dụng dùng dependency injection, không đặt việc build client bên trong phương thức xử lý từng request. Hãy đăng ký client ở tầng cấu hình ứng dụng và tiêm instance đó vào service cần gọi HTTP. Nếu cần nhiều client, phân biệt chúng bằng cấu hình và mục đích rõ ràng, chẳng hạn client gọi dịch vụ nội bộ và client gọi đối tác có truststore riêng.

Không chia sẻ một client nếu các nhóm request cần cấu hình bảo mật hoặc proxy khác nhau mà không thể biểu diễn an toàn bằng cùng cấu hình client. Khi đó, tạo các client riêng theo ranh giới cấu hình và vẫn tái sử dụng từng instance.

## 4. Quản lý vòng đời: tạo một lần, đóng đúng lúc

Từ Java 21, HttpClient triển khai AutoCloseable và cung cấp các phương thức quản lý vòng đời như close(), shutdown(), shutdownNow() và awaitTermination(). Đây là API có sẵn trong Java 26.

Quy tắc thực hành:

1. Tạo client khi thành phần ứng dụng bắt đầu hoạt động.
2. Dùng client đó cho các request trong suốt vòng đời thành phần.
3. Khi ứng dụng dừng, ngừng nhận công việc mới và đợi request đang chạy hoàn tất.
4. Đóng client sau khi các tác vụ đã hoàn thành hoặc đã được xử lý theo chính sách shutdown.

Ví dụ try-with-resources ở hàm main phù hợp với ứng dụng ngắn hạn:

~~~java
try (HttpClient client = HttpClient.newHttpClient()) {
    // Gửi các request cần thiết tại đây.
    // Khi thoát khỏi khối, client được đóng.
}
~~~

Không đặt try-with-resources quanh từng request trong một service chạy lâu dài:

~~~java
// Không nên: đóng client sau mỗi lần gọi.
HttpResponse<String> getOne(URI uri)
        throws IOException, InterruptedException {

    try (HttpClient client = HttpClient.newHttpClient()) {
        HttpRequest request = HttpRequest.newBuilder(uri).GET().build();
        return client.send(
                request,
                HttpResponse.BodyHandlers.ofString());
    }
}
~~~

Việc đóng client ngay sau mỗi thao tác sẽ triệt tiêu lợi ích tái sử dụng connection và tạo thêm chu kỳ khởi tạo/đóng tài nguyên.

### Các phương thức shutdown

| Phương thức | Ý nghĩa |
|---|---|
| shutdown() | Ngừng nhận request mới và cho các request đã gửi tiếp tục hoàn tất; không tự chờ |
| awaitTermination(Duration) | Chờ các hoạt động đã gửi hoàn tất trong khoảng thời gian chỉ định |
| close() | Thực hiện shutdown có trật tự và chờ client kết thúc |
| shutdownNow() | Yêu cầu dừng ngay; hoạt động đang chạy có thể bị gián đoạn và không có bảo đảm mọi thao tác kết thúc tức thì |
| isTerminated() | Kiểm tra client đã kết thúc sau khi shutdown hay chưa |

Với dịch vụ đang chạy, hãy đóng client trong hook dừng ứng dụng hoặc callback lifecycle của container. Đảm bảo không còn thành phần khác gửi request sau thời điểm bắt đầu shutdown.

Không cần gọi shutdownNow() theo thói quen sau mỗi request. Đây là lựa chọn dừng khẩn cấp, có thể làm gián đoạn hoạt động đang chạy. Ưu tiên shutdown có trật tự và close() khi cần chờ hoàn tất.

## 5. Tiêu thụ response body để giải phóng tài nguyên

Một request không chỉ kết thúc khi đã nhận status code hoặc header. Việc đọc response body cũng là một phần của vòng đời trao đổi HTTP.

Các BodyHandler phổ biến có cách quản lý khác nhau:

- BodyHandlers.ofString() đọc body thành chuỗi trước khi response hoàn tất.
- BodyHandlers.ofByteArray() đọc body vào mảng byte.
- BodyHandlers.ofFile() ghi body vào file.
- BodyHandlers.ofInputStream() trả về InputStream để ứng dụng tự đọc và đóng.
- BodyHandlers.ofPublisher() cung cấp body theo cơ chế reactive publisher; subscriber phải tuân thủ flow control và hoàn tất hoặc hủy subscription.

Ví dụ với BodyHandlers.ofInputStream():

~~~java
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.test/large-export"))
        .GET()
        .build();

HttpResponse<InputStream> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    body.transferTo(java.io.OutputStream.nullOutputStream());
}
~~~

Ví dụ này đọc hết body và đóng stream. Trong ứng dụng thật, thay null output bằng nơi lưu trữ hoặc bộ xử lý dữ liệu phù hợp. Nếu cần dừng giữa chừng, hãy đóng stream để báo cho client biết ứng dụng không tiếp tục đọc dữ liệu.

Với custom BodySubscriber, phải yêu cầu dữ liệu cho đến khi nhận onComplete hoặc onError, hoặc hủy subscription khi không cần dữ liệu nữa. Nếu không đọc, đóng hoặc hủy body đúng cách, request có thể còn mở, làm chậm việc giải phóng tài nguyên và khiến close() phải chờ lâu.

Không giữ InputStream response trong cache hoặc trường đối tượng sau khi đã xử lý xong. Đóng stream ở đúng phạm vi sử dụng, kể cả khi việc xử lý phát sinh exception.

## 6. Dùng sendAsync và kiểm soát số request đồng thời

sendAsync() cho phép gửi request mà không chặn luồng gọi. Nhiều request có thể dùng chung một HttpClient. Đây là cách hữu ích khi cần gọi nhiều endpoint độc lập hoặc xây dựng pipeline I/O.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.List;
import java.util.concurrent.CompletableFuture;

List<URI> uris = List.of(
        URI.create("https://api.example.test/users"),
        URI.create("https://api.example.test/products"),
        URI.create("https://api.example.test/orders"));

List<CompletableFuture<HttpResponse<String>>> futures =
        uris.stream()
                .map(uri -> {
                    HttpRequest request = HttpRequest.newBuilder(uri)
                            .GET()
                            .build();

                    return client.sendAsync(
                            request,
                            HttpResponse.BodyHandlers.ofString());
                })
                .toList();

CompletableFuture.allOf(
        futures.toArray(CompletableFuture[]::new)).join();

for (CompletableFuture<HttpResponse<String>> future : futures) {
    HttpResponse<String> response = future.join();
    System.out.println(
            response.statusCode() + " " + response.version());
}
~~~

allOf(...).join() hoàn tất khi mọi future hoàn tất, nhưng sẽ ném CompletionException nếu có request thất bại. Trong ứng dụng thực tế, hãy xử lý lỗi cho từng future hoặc dùng các nhánh exceptionally/handle phù hợp để một request lỗi không làm mất thông tin kết quả của những request còn lại.

Cùng một client được dùng cho tất cả request. Nếu các URI cùng origin và client đã thương lượng HTTP/2 hoặc HTTP/3 với server, chúng có thể được multiplex trên cùng connection. Với HTTP/1.1, nhiều request đồng thời có thể cần nhiều connection hơn.

Không gửi một số lượng request không giới hạn chỉ vì sendAsync() không chặn. Một lượng lớn future đồng thời vẫn tiêu thụ bộ nhớ, băng thông, socket, luồng xử lý và hạn mức của server. Connection pool không phải cơ chế giới hạn tải nghiệp vụ.

Trong ứng dụng thực tế, nên đặt giới hạn đồng thời ở tầng ứng dụng bằng một hàng đợi có giới hạn, Semaphore hoặc cơ chế bulkhead của framework. Có thể phân loại giới hạn theo dịch vụ đích, độ ưu tiên hoặc loại thao tác. Khi đạt giới hạn, hệ thống cần chờ, từ chối có kiểm soát hoặc trả lỗi phù hợp thay vì tiếp tục tạo vô hạn request.

Ví dụ ý tưởng dùng Semaphore:

~~~java
Semaphore permits = new Semaphore(32);

// Trước khi gửi request:
permits.acquire();

CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

future.whenComplete((response, error) -> permits.release());
~~~

Đoạn minh họa trên giới hạn tối đa 32 request đang chờ hoặc đang chạy trong phạm vi dùng chung Semaphore. Trong mã production, cần xử lý InterruptedException khi acquire, bảo đảm permit được giải phóng đúng một lần trong mọi nhánh lỗi, và không giữ permit quá thời gian xử lý cần thiết. Nếu có nhiều loại request, hãy chọn giới hạn theo tải thực tế thay vì mặc định 32.

Giới hạn số stream mà server quảng bá qua HTTP/2 hoặc HTTP/3 và giới hạn đồng thời ở tầng ứng dụng là hai vấn đề khác nhau. Đừng dùng một system property về HTTP/2/HTTP/3 push stream để thay thế cơ chế kiểm soát số request nghiệp vụ.

## 7. Những thuộc tính cấu hình connection pool trong JDK 26

API công khai của HttpClient không cung cấp phương thức kiểu setMaxConnections(), getPoolSize() hoặc lấy danh sách socket đang được giữ. Cơ chế pool là chi tiết triển khai. Tuy vậy, tài liệu module java.net.http của JDK 26 có công bố một số system property phục vụ cấu hình implementation tích hợp của JDK.

Hai thuộc tính liên quan trực tiếp đến cache kết nối nhàn rỗi:

| System property | Mặc định trong JDK 26 | Phạm vi |
|---|---:|---|
| jdk.httpclient.connectionPoolSize | 0 | Số kết nối tối đa được giữ trong HTTP/1.1 keep-alive cache; 0 nghĩa là cache không giới hạn theo thuộc tính này |
| jdk.httpclient.keepalive.timeout | 30 giây | Thời gian giữ kết nối HTTP nhàn rỗi trong keep-alive cache; mặc định áp dụng HTTP/1.1, HTTP/2 và HTTP/3 |
| jdk.httpclient.keepalive.timeout.h2 | Theo keepalive.timeout | Thời gian giữ kết nối HTTP/2 nhàn rỗi; nếu không đặt thì dùng keepalive.timeout |
| jdk.httpclient.keepalive.timeout.h3 | Theo keepalive.timeout.h2 | Thời gian giữ kết nối HTTP/3 nhàn rỗi; nếu không đặt thì dùng giá trị HTTP/2 |

Cần hiểu đúng phạm vi:

- connectionPoolSize chỉ mô tả số kết nối được giữ trong cache HTTP/1.1 keep-alive. Đây không phải giới hạn tổng số request đồng thời, cũng không phải giới hạn tổng số connection đang hoạt động của mọi giao thức.
- HTTP/2 và HTTP/3 multiplex nhiều stream trên connection. Không dùng connectionPoolSize để suy ra số stream hoặc số request có thể chạy đồng thời.
- keepalive.timeout điều khiển thời gian giữ kết nối nhàn rỗi trong cache. Đây không phải request timeout, connect timeout hoặc thời gian tối đa một request đang chạy.
- Các property này áp dụng cho implementation HttpClient tích hợp trong JDK. Một implementation khác có thể không hỗ trợ.
- Tài liệu JDK không bảo đảm thay đổi property bằng System.setProperty() trong lúc ứng dụng chạy sẽ có hiệu lực. Nên cấu hình từ đầu JVM hoặc trong conf/net.properties theo hướng dẫn của JDK.

Ví dụ cấu hình ở lúc khởi chạy JVM:

~~~powershell
java -Djdk.httpclient.connectionPoolSize=32 -Djdk.httpclient.keepalive.timeout=20 -Djdk.httpclient.keepalive.timeout.h2=45 -Djdk.httpclient.keepalive.timeout.h3=45 -jar app.jar
~~~

Trong ví dụ, cache HTTP/1.1 được giới hạn ở 32 kết nối nhàn rỗi; thời gian giữ mặc định là 20 giây, còn HTTP/2 và HTTP/3 được đặt riêng thành 45 giây. Các con số chỉ minh họa cách cấu hình, không phải giá trị tối ưu cho mọi ứng dụng. Đo tải và quan sát server trước khi thay đổi.

Nếu muốn cấu hình cho một JDK cụ thể, có thể xem file conf/net.properties trong thư mục cài đặt JDK và thêm property theo tài liệu của phiên bản đó. Giá trị ở dòng lệnh JVM sẽ ghi đè cấu hình trong file. Ghi lại các giá trị đã thay đổi trong tài liệu vận hành để tránh khác biệt khó phát hiện giữa máy phát triển và production.

Không nhầm các property của java.net.http với các thuộc tính cũ của URLConnection như http.keepAlive, http.maxConnections hoặc http.keepAlive.time.server. Chúng không phải API cấu hình connection pool được công bố cho java.net.http.HttpClient. Tránh sao chép cấu hình từ hướng dẫn HttpURLConnection cũ sang ứng dụng dùng HttpClient hiện đại.

Các property có tiền tố jdk.httpclient là cấu hình triển khai của JDK, không phải hợp đồng Java SE portable. Khi nâng cấp JDK hoặc đổi nhà cung cấp, hãy kiểm tra lại tài liệu module và đo kiểm trước khi dựa vào chúng.

## 8. Timeout và thời gian giữ kết nối là các khái niệm khác nhau

Các giá trị thời gian thường bị nhầm lẫn:

| Cấu hình | Mục đích | Nơi đặt |
|---|---|---|
| connectTimeout | Giới hạn thời gian thiết lập kết nối mới | HttpClient.Builder.connectTimeout() |
| HttpRequest.timeout | Giới hạn thời gian thực hiện một request | HttpRequest.Builder.timeout() |
| keepalive.timeout | Thời gian giữ connection nhàn rỗi trong cache | System property của JDK |
| keepalive.timeout.h2 / keepalive.timeout.h3 | Thời gian giữ connection HTTP/2 hoặc HTTP/3 nhàn rỗi | System property của JDK |

Ví dụ cấu hình timeout:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.test/data"))
        .timeout(Duration.ofSeconds(20))
        .GET()
        .build();
~~~

Connect timeout chỉ liên quan đến việc thiết lập kết nối mới. Nếu client đã có connection phù hợp trong pool, request có thể không cần tạo connection mới. Request timeout áp dụng cho thao tác request theo API; nó không phải chính sách giữ connection nhàn rỗi.

Không giảm keepalive timeout để xử lý một API phản hồi chậm. Hãy tìm nguyên nhân bằng request timeout, log, thời gian xử lý server và trạng thái mạng. Tương tự, không tăng connect timeout để làm connection pool giữ socket lâu hơn.

## 9. Quan sát việc tái sử dụng connection

Không có API Java SE công khai để hỏi HttpClient hiện có bao nhiêu connection trong pool hoặc connection nào đang được tái sử dụng. Không nên dùng reflection vào lớp nội bộ của JDK để lấy thông tin này vì implementation có thể thay đổi giữa các bản cập nhật.

Có thể kiểm chứng bằng nhiều nguồn bằng chứng:

1. **HTTP Client logging:** bật log ở môi trường thử nghiệm để quan sát request, lỗi và hoạt động channel.
2. **Server access/connection logs:** ghi nhận connection ID, peer port hoặc số lần handshake tại server nếu nền tảng server hỗ trợ.
3. **Packet capture:** quan sát số lần mở TCP/TLS connection hoặc QUIC handshake bằng Wireshark.
4. **Đo thời gian:** so sánh request đầu tiên và request tiếp theo trong cùng điều kiện; đây là chỉ báo hiệu năng, không phải bằng chứng duy nhất.
5. **Response metadata:** ghi response.version() để biết request dùng HTTP/1.1, HTTP/2 hay HTTP/3; phiên bản HTTP không trực tiếp cho biết pool đã tái sử dụng connection nào.

JDK 26 công bố property jdk.httpclient.HttpClient.log cho implementation HttpClient tích hợp. Có thể bật các nhóm log như errors, requests, trace và channel bằng tùy chọn JVM:

~~~powershell
java -Djdk.httpclient.HttpClient.log=errors,requests,trace,channel -jar app.jar
~~~

Logger được đặt tên jdk.httpclient.HttpClient và sử dụng Platform Logging API ở mức INFO. Cần cấu hình logging backend phù hợp để thu nhận log. Khi phân tích HTTP/3, JDK 26 còn hỗ trợ nhóm log http3 và quic; ví dụ quic:control:retransmit có thể giúp quan sát điều khiển QUIC và phục hồi packet.

Chỉ bật log chi tiết trong môi trường kiểm thử hoặc trong khoảng thời gian cần điều tra. Tránh bật headers hoặc content ở production nếu log có thể chứa access token, cookie, dữ liệu cá nhân hoặc nội dung nghiệp vụ nhạy cảm. Bảo vệ file log, giới hạn quyền truy cập và xóa dữ liệu theo chính sách lưu trữ.

Một phép thử cơ bản:

- Gửi 10 request tuần tự đến cùng origin bằng cùng một HttpClient.
- Gửi lại 10 request bằng cách tạo client mới cho từng request trong một chương trình thử nghiệm riêng.
- So sánh số lần thiết lập connection/handshake trên server hoặc packet capture.
- Lặp lại với HTTP/1.1 và HTTP/2; nếu môi trường hỗ trợ, thử HTTP/3.
- Đọc hết response body trong cả hai trường hợp để phép so sánh công bằng.
- Lặp lại phép thử nhiều lần, bỏ qua ảnh hưởng của DNS, cache ứng dụng, tải server và kết nối đã tồn tại từ trước.

Kết quả có thể khác nhau theo server, proxy, giao thức và phiên bản JDK. Mục tiêu là xác nhận xu hướng tái sử dụng trong môi trường cụ thể, không suy ra một số lượng connection cố định từ một lần đo.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Mỗi request đều tạo kết nối mới | Ứng dụng tạo HttpClient mới cho từng request | Dùng lại cùng instance trong phạm vi cấu hình phù hợp |
| Request tiếp theo vẫn không dùng connection cũ | Server đóng connection, connection hết thời gian nhàn rỗi, body chưa được đọc/đóng hoặc có lỗi mạng | Kiểm tra server log, body lifecycle, timeout và log HttpClient |
| Số connection HTTP/1.1 tăng cao | Nhiều request đồng thời hoặc nhiều HttpClient độc lập | Tái sử dụng client; đặt giới hạn đồng thời ở tầng ứng dụng; xem lại pool size nếu có bằng chứng cần thiết |
| Tăng connectionPoolSize nhưng số request đồng thời không đổi | Thuộc tính này chỉ giới hạn cache HTTP/1.1 keep-alive | Quản lý concurrency bằng hàng đợi hoặc Semaphore; không dùng cache size làm request limit |
| HTTP/2 hoặc HTTP/3 không multiplex như kỳ vọng | Server giới hạn stream, kết nối không được thương lượng hoặc có proxy/network constraint | Kiểm tra response.version(), server settings và log giao thức |
| Ứng dụng shutdown bị treo | Request chưa hoàn tất hoặc streaming body chưa được đóng/đọc hết | Ngừng nhận request mới, xử lý hoặc hủy body, chờ hoạt động hoàn tất rồi close client |
| Property không có tác dụng | Đặt sai tên, sai JDK, đặt sau khi client đã khởi tạo hoặc dùng implementation khác | Kiểm tra module summary của đúng JDK; cấu hình từ lúc JVM khởi chạy |
| Không tìm thấy API shutdown/close khi biên dịch | Compiler đang dùng JDK cũ hơn Java 21 | Kiểm tra toolchain; các phương thức quản lý vòng đời này có từ Java 21 |
| Bật log nhưng không thấy output | Chưa cấu hình logging backend hoặc mức logger | Kiểm tra Platform Logging API và cấu hình logger jdk.httpclient.HttpClient |

## 11. Bài thực hành kiểm chứng

Tạo một chương trình Java 26 có thể gửi nhiều request đến cùng một server thử nghiệm. Ưu tiên endpoint do bạn kiểm soát để có thể xem log connection ở phía server.

1. Tạo một HttpClient bên ngoài phương thức gửi request và truyền cùng instance vào các lần gọi.
2. Gửi 10 request tuần tự đến cùng origin bằng BodyHandlers.ofString(). Ghi status code, response.version() và thời gian từng request.
3. Tạo chương trình thử nghiệm thứ hai, tạo HttpClient mới cho từng request. So sánh số lần mở connection và handshake.
4. Chạy lại với HTTP/1.1 và HTTP/2. Xác định sự khác biệt giữa keep-alive connection và multiplexed streams.
5. Nếu server và mạng hỗ trợ HTTP/3, thử HTTP_3 và xác nhận response.version() thực tế.
6. Thử sendAsync() với một nhóm request độc lập. Sau đó đặt giới hạn concurrency bằng Semaphore hoặc hàng đợi có giới hạn.
7. Thử response body dạng InputStream. Quan sát việc đóng stream và đọc hết dữ liệu ảnh hưởng thế nào đến khả năng hoàn tất request và shutdown.
8. Trong môi trường thử nghiệm, cấu hình jdk.httpclient.keepalive.timeout và quan sát tác động đến connection nhàn rỗi.
9. Nếu cần, đặt jdk.httpclient.connectionPoolSize và xác nhận nó tác động đến HTTP/1.1 keep-alive cache, không phải giới hạn tổng request đồng thời.
10. Bật logging có chọn lọc và đối chiếu với log server hoặc Wireshark. Không bật log nội dung nhạy cảm.
11. Đóng client ở cuối vòng đời ứng dụng và xác nhận các request đang chạy đã hoàn tất.

**Tiêu chí hoàn thành:** giải thích được vì sao HttpClient nên được tái sử dụng; phân biệt được pool HTTP/1.1 với multiplexing HTTP/2 và HTTP/3; quản lý đúng vòng đời client và response body; sử dụng được sendAsync với giới hạn tải ở tầng ứng dụng; hiểu chính xác phạm vi của connectionPoolSize và keepalive.timeout; biết cách quan sát kết nối mà không phụ thuộc lớp nội bộ của JDK.

## 12. Tài liệu tham khảo chính thức

- [Java 26 HttpClient API](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html) — tính immutable, tái sử dụng client, connection pools, gửi request đồng bộ/bất đồng bộ và quản lý vòng đời.
- [Java 26 java.net.http module summary](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/module-summary.html) — danh sách system property của implementation JDK, phạm vi connectionPoolSize và keepalive timeout.
- [Java 26 HttpClient.Builder](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Builder.html) — cấu hình client, executor, timeout, proxy và phiên bản HTTP.
- [Java 26 HttpRequest.Builder](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html) — timeout và cấu hình request.
- [Java 26 HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html) — cách xử lý response body bằng String, byte array, file, InputStream và publisher.
- [Java 26 System Properties](https://docs.oracle.com/en/java/javase/26/docs/api/system-properties.html) — danh mục property và module sử dụng.
- [RFC 9113: HTTP/2](https://www.rfc-editor.org/rfc/rfc9113.html) — multiplexing, stream và giới hạn giao thức HTTP/2.
- [RFC 9114: HTTP/3](https://www.rfc-editor.org/rfc/rfc9114.html) — stream và kết nối HTTP/3 trên QUIC.

Các system property có tiền tố jdk.httpclient là chi tiết cấu hình của implementation JDK. Khi đổi phiên bản JDK hoặc nhà cung cấp, hãy kiểm tra tài liệu của đúng bản phát hành và đo kiểm lại trước khi áp dụng vào production.


