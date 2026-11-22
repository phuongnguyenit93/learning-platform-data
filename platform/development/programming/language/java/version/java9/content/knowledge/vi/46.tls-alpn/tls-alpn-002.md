# Cấu hình danh sách giao thức qua SSLParameters: TLS và ALPN trong Java 9+

## 1. Mục tiêu: chọn giao thức ứng dụng ngay trong bắt tay TLS

Một kết nối TLS bảo vệ dữ liệu trên đường truyền, nhưng **TLS không tự nói ứng dụng sẽ trao đổi dữ liệu theo HTTP/2, HTTP/1.1 hay một giao thức riêng**. Khi máy khách và máy chủ cùng hỗ trợ nhiều giao thức ứng dụng trên một cổng, chúng cần thống nhất sử dụng giao thức nào.

**ALPN** (*Application-Layer Protocol Negotiation*) là phần mở rộng của TLS giúp hai phía thỏa thuận giao thức ứng dụng **trong quá trình bắt tay TLS** (*TLS handshake*), không cần thêm một lượt trao đổi riêng sau khi kết nối an toàn được thiết lập. Ví dụ:

```text
Máy khách                                      Máy chủ
    |                                              |
    | ClientHello: ALPN = ["h2", "http/1.1"]        |
    |--------------------------------------------->|
    |                                              | Có hỗ trợ:
    |                                              | ["http/1.1", "h2"]
    |        TLS handshake: chọn "http/1.1"         | (ưu tiên server)
    |<---------------------------------------------|
    |                                              |
    |    Kết nối TLS hoàn tất; ứng dụng dùng        |
    |    đúng giao thức đã được chọn               |
    |<============================================>|
```

Với thuật toán lựa chọn mặc định của SunJSSE trong JDK, **máy chủ** duyệt danh sách ALPN của mình theo thứ tự ưu tiên và chọn giá trị đầu tiên cũng có trong danh sách máy khách; vì thế ví dụ chọn `http/1.1`. Một bộ chọn tùy biến của máy chủ có thể thực hiện chính sách khác.

**Bối cảnh Java:** API ALPN chuẩn cho `javax.net.ssl.SSLParameters`, `SSLSocket` và `SSLEngine` được bổ sung từ **Java 9** (JEP 244) và vẫn là API hiện hành trên các bản Java mới. Các ví dụ dưới đây dùng Java 17+ và các tên giao thức vẫn đang áp dụng. Trọng tâm bài học là **cấu hình danh sách ALPN qua `SSLParameters`**, kiểm tra kết quả đàm phán và vận dụng đúng trong TLS hiện đại.

## 2. Phân biệt ba loại “giao thức” dễ bị nhầm

`SSLParameters` chứa nhiều nhóm tham số cho kết nối TLS. Quan trọng nhất trong chủ đề này:

| API | Điều khiển gì? | Ví dụ |
|---|---|---|
| `setApplicationProtocols(String[])` | Danh sách **giao thức tầng ứng dụng** để thương lượng bằng ALPN | `"h2"`, `"http/1.1"` |
| `setProtocols(String[])` | Các **phiên bản giao thức TLS/DTLS** được phép dùng | `"TLSv1.3"`, `"TLSv1.2"` |
| `setCipherSuites(String[])` | Các **bộ mật mã TLS** được phép sử dụng theo cấu hình/provider | Tên cipher suite được JDK và provider hỗ trợ |

Ví dụ đúng:

```java
SSLParameters parameters = sslSocket.getSSLParameters();
parameters.setApplicationProtocols(new String[] {"h2", "http/1.1"});
parameters.setProtocols(new String[] {"TLSv1.3", "TLSv1.2"});
sslSocket.setSSLParameters(parameters);
```

Đây là **mảnh mã minh họa**; `sslSocket` là một `SSLSocket` đã được tạo. Hai lần gọi `set...` giải quyết **hai câu hỏi độc lập**:

- Bắt tay TLS có thể dùng phiên bản nào? → `TLSv1.3` hoặc `TLSv1.2`.
- Sau khi thiết lập TLS, hai phía trao đổi thông điệp theo giao thức nào? → `h2` hoặc `http/1.1` nếu có giá trị chung và thương lượng thành công.

Không truyền `"TLSv1.3"` vào `setApplicationProtocols` để chọn TLS 1.3, và không truyền `"h2"` vào `setProtocols`. Tên `h2` chỉ biểu thị HTTP/2 trên TLS trong ALPN; riêng việc chọn `h2` **không tự biến** dữ liệu từ chương trình thành khung HTTP/2, và cũng không tự cài đặt giao thức đó.

### Từ khóa cần nhớ

- **Danh sách chào mời (offered protocols):** phía máy khách gửi các định danh ALPN mà mình hỗ trợ trong `ClientHello`.
- **Danh sách ưu tiên của máy chủ:** phía máy chủ dùng để chọn một định danh phù hợp.
- **Giao thức đã thương lượng (negotiated application protocol):** một giá trị đơn được chọn trong bắt tay, đọc qua `getApplicationProtocol()` sau khi bắt tay hoàn tất.
- **SSLParameters:** đối tượng **cấu hình**; nó không chứa kết quả ALPN của một phiên kết nối cụ thể.

## 3. Hai phương thức chính của SSLParameters

### `setApplicationProtocols(String[] protocols)`

Phương thức khai báo **danh sách có thứ tự ưu tiên** của các giao thức ứng dụng mà kết nối có thể thương lượng.

```java
parameters.setApplicationProtocols(
        new String[] {"h2", "http/1.1"});
```

Đây là mảnh mã. Phần tử đứng đầu được khai báo là ưu tiên cao nhất. Đối với SunJSSE, khi máy chủ dùng chế độ lựa chọn mặc định, danh sách của **máy chủ** quyết định thứ tự chọn giá trị chung; không giả định thứ tự chào mời phía máy khách buộc máy chủ phải chọn `h2`.

Các quy tắc theo API hiện hành:

1. `protocols` **không được `null`**.
2. Trong một mảng có phần tử, **không phần tử nào được `null` hoặc chuỗi rỗng `""`**; vi phạm ném `IllegalArgumentException`.
3. Mảng rỗng `new String[0]` là **hợp lệ** và có nghĩa phía này **không sử dụng chỉ báo giao thức ứng dụng** (không dùng danh sách ALPN).
4. Mỗi giá trị nên là **định danh giao thức ALPN được phía kia hiểu**, chẳng hạn `h2` và `http/1.1`. Các định danh ALPN trên mạng là chuỗi **byte**; với tên tùy chỉnh có byte phi ASCII, cần tuân thủ quy tắc mã hóa dạng byte của nhà cung cấp JSSE. Không tùy tiện truyền câu tiếng Việt làm tên giao thức.
5. Phương thức **sao chép mảng đầu vào**. Thay đổi mảng Java ban đầu sau lời gọi không sửa danh sách đã đặt trong đối tượng `SSLParameters`.
6. Các định danh giao thức được dùng tại thời điểm **bắt tay TLS**, nên cần cấu hình trước khi bắt tay bắt đầu. Gọi `setApplicationProtocols` trên một `SSLParameters` chưa áp dụng lên socket/engine sẽ **không** ảnh hưởng kết nối.

Ví dụ kiểm tra giá trị không hợp lệ:

```java
// Hợp lệ: tắt danh sách ALPN ở đối tượng cấu hình.
parameters.setApplicationProtocols(new String[0]);

// Không hợp lệ: IllegalArgumentException.
parameters.setApplicationProtocols(null);
parameters.setApplicationProtocols(new String[] { "h2", "" });
```

Các dòng ví dụ trên **không phải một chương trình chạy liên tiếp**: hai dòng cuối minh họa lỗi và phải được thử riêng với xử lý ngoại lệ nếu muốn quan sát.

### `getApplicationProtocols()`

Phương thức trả về một mảng `String[]` **không bao giờ `null`**, có thể rỗng; các phần tử theo thứ tự ưu tiên đã cấu hình. Mỗi lần gọi đều nhận **một bản sao mảng mới**. Điều này hữu ích khi kiểm tra cấu hình mà không làm hỏng dữ liệu bên trong:

```java
String[] configured = parameters.getApplicationProtocols();
System.out.println(Arrays.toString(configured));
```

Đây là mảnh mã; cần `import java.util.Arrays;` và biến `parameters`. Nếu trước đó có `{"h2", "http/1.1"}`, kết quả là `[h2, http/1.1]`.

**Cảnh báo quan trọng:** `getApplicationProtocols()` trả về **danh sách được cấu hình**, **không phải giao thức cuối cùng đã thương lượng**. Muốn biết một kết nối đã chọn giao thức nào, sau bắt tay hãy gọi `SSLSocket.getApplicationProtocol()` hoặc `SSLEngine.getApplicationProtocol()`.

## 4. Áp dụng cấu hình lên một kết nối

Quy trình chung cho một `SSLSocket` hoặc `SSLEngine`:

1. Tạo kết nối/engine từ một `SSLContext` thích hợp đã cấu hình chứng chỉ và chính sách tin cậy.
2. Lấy cấu hình hiện tại bằng `getSSLParameters()`.
3. Gọi `setApplicationProtocols(...)` để thêm danh sách ALPN, điều chỉnh các tham số khác nếu thực sự cần.
4. **Gọi ngược lại `setSSLParameters(parameters)`** để áp dụng.
5. Bắt đầu TLS handshake hoặc chạy vòng `wrap/unwrap` của `SSLEngine`.
6. Sau khi bắt tay hoàn thành, đọc `getApplicationProtocol()`, kiểm tra kết quả rồi chuyển sang bộ xử lý giao thức ứng dụng tương ứng.

Sơ đồ trạng thái:

```text
SSLContext
   |
   +--> SSLSocket / SSLEngine
            |
            +--> getSSLParameters()
            |       |
            |       +--> setApplicationProtocols(...)
            |       +--> [tùy chọn] setProtocols(...)
            |
            +--> setSSLParameters(parameters)
            |
            +--> TLS handshake
            |
            +--> getApplicationProtocol()
                         |
                +--------+---------+
                |        |         |
               "h2"  "http/1.1"    "" / null
                |        |         |
              HTTP/2  HTTP/1.1  xử lý rõ theo chính sách
```

Lưu ý: mã `null` ở giai đoạn quá sớm có nghĩa **chưa xác định liệu kết nối sẽ sử dụng ALPN hay không**; chuỗi rỗng `""` nghĩa **không sử dụng một giao thức ứng dụng đã thương lượng**. Sau khi bắt tay hoàn tất, chương trình phải kiểm tra trường hợp không có giao thức hoặc lỗi thương lượng, thay vì âm thầm giả định `http/1.1`.

### Dùng với SSLServerSocket

Trên phía máy chủ, có thể gọi `SSLServerSocket.setSSLParameters(parameters)` để cấu hình thông số cho các kết nối sẽ được chấp nhận. Một cách dễ quan sát hơn khi ví dụ tập trung ALPN là **đặt thông số trên từng `SSLSocket` nhận từ `accept()` trước khi `startHandshake()`**. Nếu môi trường có kết nối đồng thời, hãy đặt danh sách trên socket tương ứng trước handshake; không đổi cấu hình tùy tiện khi handshake đã chạy.

### Dùng với SSLEngine

`SSLEngine` là API TLS không tự thực hiện I/O mạng, thường được máy chủ bất đồng bộ hoặc framework mạng sử dụng. Các bước `getSSLParameters()` → `setApplicationProtocols(...)` → `setSSLParameters(...)` giống `SSLSocket`, nhưng bên gọi phải điều khiển trạng thái bắt tay, `wrap`/`unwrap` và truyền byte tới peer. Chỉ tạo `SSLEngine` **không đồng nghĩa đã thương lượng** bất kỳ ALPN nào.

## 5. Ví dụ Java 17+ chạy độc lập: cấu hình và đọc lại danh sách

Ví dụ sau chỉ dùng JDK; **không mở cổng, không cần chứng chỉ và không bắt tay với máy chủ thật**. Nó kiểm tra việc áp dụng cấu hình và việc mảng được sao chép theo hợp đồng API.

**Tệp `AlpnParametersDemo.java`:**

```java
import java.util.Arrays;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLParameters;

public final class AlpnParametersDemo {

    private AlpnParametersDemo() {}

    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, null, null);

        SSLEngine engine = context.createSSLEngine("example.com", 443);
        engine.setUseClientMode(true);

        // Sửa các tham số lấy từ engine, rồi áp dụng lại.
        SSLParameters parameters = engine.getSSLParameters();
        String[] offered = {"h2", "http/1.1"};

        parameters.setApplicationProtocols(offered);
        parameters.setProtocols(new String[] {"TLSv1.3", "TLSv1.2"});
        engine.setSSLParameters(parameters);

        // Chứng minh setApplicationProtocols không giữ lại mảng đầu vào.
        offered[0] = "changed";

        // Chứng minh getApplicationProtocols trả về bản sao mảng.
        String[] retrieved =
                engine.getSSLParameters().getApplicationProtocols();
        retrieved[0] = "also-changed";

        System.out.println("ALPN offer: " +
                Arrays.toString(
                        engine.getSSLParameters().getApplicationProtocols()));
        System.out.println("TLS versions: " +
                Arrays.toString(
                        engine.getSSLParameters().getProtocols()));
        System.out.println("Before handshake: " +
                String.valueOf(engine.getApplicationProtocol()));
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac --release 17 -encoding UTF-8 AlpnParametersDemo.java
java AlpnParametersDemo
```

**Stdout với provider SunJSSE thông dụng của JDK:**

```text
ALPN offer: [h2, http/1.1]
TLS versions: [TLSv1.3, TLSv1.2]
Before handshake: null
```

Giải thích:

- `[h2, http/1.1]` vẫn được giữ nguyên dù mảng nguồn `offered` và mảng trả về `retrieved` đã bị sửa; đây là tác dụng của **sao chép phòng vệ**.
- `[TLSv1.3, TLSv1.2]` là các phiên bản TLS được cấu hình, hoàn toàn tách biệt khỏi danh sách ALPN.
- `null` trước bắt tay thể hiện **chưa có kết quả thương lượng**. Giá trị từ `getApplicationProtocol()` trước handshake hoặc trên một provider khác có thể khác theo trạng thái/hỗ trợ API; chương trình này không giả vờ đã kết nối đến `example.com`.

Ví dụ đã sử dụng `setSSLParameters(parameters)` sau khi sửa. Nếu bỏ bước áp dụng, `engine.getSSLParameters()` vẫn là cấu hình trước đó, không phải mảng ALPN vừa thiết lập trên bản sao `parameters`.

## 6. Cách cấu hình máy khách SSLSocket trong kết nối thật

Trong một ứng dụng có `SSLContext` đã cấu hình trust manager đúng, có thể áp dụng ALPN như sau:

```java
// MẢNH MÃ: các biến sslContext, host và port phải được cung cấp.
// sslContext phải tin cậy đúng chứng chỉ của máy chủ.
try (SSLSocket socket = (SSLSocket)
        sslContext.getSocketFactory().createSocket(host, port)) {

    SSLParameters parameters = socket.getSSLParameters();
    parameters.setApplicationProtocols(
            new String[] {"h2", "http/1.1"});

    // Khi kết nối tới dịch vụ HTTPS, yêu cầu kiểm tra tên máy chủ.
    parameters.setEndpointIdentificationAlgorithm("HTTPS");
    socket.setSSLParameters(parameters);

    socket.startHandshake();

    String selected = socket.getApplicationProtocol();
    if ("h2".equals(selected)) {
        // Chuyển cho bộ xử lý HTTP/2 đã được cài đặt thực sự.
    } else if ("http/1.1".equals(selected)) {
        // Chuyển cho bộ xử lý HTTP/1.1 đã được cài đặt thực sự.
    } else {
        throw new SSLHandshakeException(
                "Không thương lượng được ALPN được ứng dụng hỗ trợ");
    }
}
```

**Đây là mảnh mã tích hợp**, không chạy độc lập. Cần các lớp `SSLSocket`, `SSLParameters` và `SSLHandshakeException` từ `javax.net.ssl`, cộng với `sslContext`, `host`, `port` phù hợp. Nó cũng chỉ minh họa **lựa chọn giao thức**: để giao tiếp HTTP/2 thực sự, ứng dụng cần một triển khai HTTP/2 đúng chuẩn.

Đối với máy khách HTTPS dùng thư viện hoặc framework HTTP hiện đại (ví dụ `java.net.http.HttpClient`), thư viện thường đã quản lý TLS và ALPN. Nên dùng API cấu hình được hỗ trợ của thư viện đó thay vì cố gắng can thiệp vào socket nội bộ. Mẫu `SSLSocket` trực tiếp phù hợp khi **chính ứng dụng quản lý kết nối TLS**.

**Cấu hình an toàn:** `setEndpointIdentificationAlgorithm("HTTPS")` làm cho TLS client kiểm tra danh tính máy chủ khi áp dụng quy tắc HTTPS; vẫn cần trust manager phù hợp để xác minh chuỗi chứng chỉ. Không dùng trust manager chấp nhận mọi chứng chỉ trong ứng dụng thật chỉ để ví dụ ALPN hoạt động.

## 7. Cách cấu hình máy chủ và thứ tự ưu tiên

Trên máy chủ, việc cấu hình danh sách ALPN tương tự nhưng có khác biệt quan trọng: theo thuật toán mặc định trong SunJSSE, **thứ tự ưu tiên của máy chủ quyết định protocol đầu tiên được chọn trong phần giao nhau**.

Ví dụ sau nhận **một kết nối**. Nó giả định `serverContext` có key manager cùng chứng chỉ máy chủ hợp lệ và `port` đã được cấu hình:

```java
// MẢNH MÃ: serverContext và port được ứng dụng cung cấp.
try (SSLServerSocket server = (SSLServerSocket)
        serverContext.getServerSocketFactory().createServerSocket(port);
     SSLSocket socket = (SSLSocket) server.accept()) {

    SSLParameters parameters = socket.getSSLParameters();
    parameters.setApplicationProtocols(
            new String[] {"h2", "http/1.1"});
    socket.setSSLParameters(parameters);

    socket.startHandshake();

    String selected = socket.getApplicationProtocol();
    if ("h2".equals(selected)) {
        // Phục vụ HTTP/2 trên kết nối này.
    } else if ("http/1.1".equals(selected)) {
        // Phục vụ HTTP/1.1 trên kết nối này.
    } else {
        throw new SSLHandshakeException(
                "Không có giao thức ứng dụng phù hợp");
    }
}
```

Đây là **mảnh mã**, không có cấu hình chứng chỉ, không có vòng lặp máy chủ và không cài đặt HTTP. Cần import `SSLSocket`, `SSLServerSocket`, `SSLParameters` và `SSLHandshakeException` từ `javax.net.ssl`.

Nếu máy khách quảng bá `["http/1.1", "h2"]` và máy chủ cấu hình `["h2", "http/1.1"]`, SunJSSE mặc định có thể chọn `h2` vì `h2` đứng đầu danh sách máy chủ. Nếu danh sách máy chủ là `["http/1.1", "h2"]`, lựa chọn mặc định với cùng máy khách sẽ là `http/1.1`.

**Không xem việc đặt danh sách là bảo đảm bắt tay thành công.** Để một giao thức được lựa chọn, hai phía phải chia sẻ định danh phù hợp, TLS cũng phải chọn được tham số bảo mật, chứng chỉ hợp lệ và provider phải hỗ trợ ALPN. Nếu không có giao thức chung, hành động cụ thể phụ thuộc cơ chế TLS/ALPN; SunJSSE thường kết thúc handshake bằng cảnh báo `no_application_protocol`. Đừng đánh tráo tình huống “không có giao thức chung” với tình huống “một phía chủ động không dùng ALPN”.

## 8. Bộ chọn ALPN tùy biến của máy chủ

Trong trường hợp máy chủ phải cân nhắc thêm thông tin (chẳng hạn SNI, định tuyến dịch vụ hoặc khả năng xử lý HTTP/2 thực tế), `SSLSocket` và `SSLEngine` cung cấp:

- `setHandshakeApplicationProtocolSelector(BiFunction<SSLSocket, List<String>, String>)` cho `SSLSocket`;
- overload tương ứng với `SSLEngine` cho giao tiếp TLS không chặn.

Mẫu bộ chọn trên một `SSLSocket` máy chủ, **đăng ký trước khi bắt tay**:

```java
// MẢNH MÃ: socket là SSLSocket phía server,
// serverSupportsHttp2 là boolean từ cấu hình thực tế.
socket.setHandshakeApplicationProtocolSelector(
        (handshakingSocket, clientProtocols) -> {
            if (serverSupportsHttp2 && clientProtocols.contains("h2")) {
                return "h2";
            }
            if (clientProtocols.contains("http/1.1")) {
                return "http/1.1";
            }
            return null;
        });
```

Đây là mảnh mã, các biến cần được cung cấp trong ứng dụng. Tham số `clientProtocols` là các định danh ALPN mà **peer đã quảng bá**. Khi dùng bộ chọn này, kết quả do callback quyết định và **ghi đè quy tắc danh sách mặc định** của `SSLParameters.setApplicationProtocols`.

Giá trị trả về của bộ chọn:

| Callback trả về | Ý nghĩa |
|---|---|
| Một chuỗi có trong danh sách client (ví dụ `"h2"`) | Đề nghị chọn giao thức ứng dụng đó |
| `""` | Không sử dụng chỉ báo giao thức ứng dụng cho handshake này |
| `null` | Không chấp nhận giao thức nào mà peer chào mời; triển khai ALPN thường báo lỗi và dừng handshake |
| Chuỗi không hề được client quảng bá | Không hợp lệ với quy tắc lựa chọn ALPN; có thể dẫn đến lỗi handshake |

Không dùng callback chỉ để đổi thứ tự danh sách khi danh sách ưu tiên mặc định đã đáp ứng yêu cầu. Việc tùy biến tăng độ phức tạp và phải phù hợp với định dạng thông điệp được giao thức đã chọn yêu cầu.

**Phân biệt hai API đọc kết quả:**

- `getHandshakeApplicationProtocol()` đọc giao thức được quyết định **trong lúc bắt tay đang diễn ra**; nếu chưa xác định có thể trả `null`.
- `getApplicationProtocol()` đọc giao thức mới nhất đã thương lượng **trên kết nối** và thường được dùng sau `startHandshake()`.

Đừng dựa vào `SSLSession.getProtocol()` để lấy `h2` hay `http/1.1`: phương thức đó trả **phiên bản TLS**, ví dụ `TLSv1.3`. ALPN là thuộc tính của kết nối và được lấy từ `SSLSocket` hoặc `SSLEngine`.

## 9. Các trường hợp lỗi và cách kiểm tra

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `getApplicationProtocols()` trả `[]` | Chưa cấu hình ALPN hoặc đã đặt mảng rỗng | Đặt danh sách trước bắt tay và áp dụng lên socket/engine |
| Đã gọi `parameters.setApplicationProtocols(...)` nhưng kết nối vẫn không chào mời ALPN | Quên `socket.setSSLParameters(parameters)` hoặc đặt quá muộn | Lấy tham số từ đúng kết nối, sửa rồi áp dụng trước handshake |
| `getApplicationProtocol()` là `null` | Chưa hoàn thành/xác định thương lượng, hoặc provider chưa hỗ trợ cách gọi | Xem đúng thời điểm bắt tay, tránh đọc ngay sau khi khởi tạo engine |
| `getApplicationProtocol()` là `""` | Không có giao thức ứng dụng nào được sử dụng cho kết nối | Quy định rõ có cho phép tiếp tục theo giao thức khác không; không mặc định đó là `http/1.1` |
| `SSLHandshakeException` hoặc `no_application_protocol` | Không có giao thức chung hoặc chính sách chọn không chấp nhận kết quả | Đối chiếu danh sách hai phía, callback và khả năng xử lý giao thức thực tế |
| `IllegalArgumentException` khi đặt danh sách | Truyền mảng `null` hoặc phần tử `null`/`""` | Truyền mảng hợp lệ; dùng `new String[0]` nếu thực sự muốn không dùng ALPN |
| `UnsupportedOperationException` | Một SSL provider không triển khai API ALPN tương ứng | Kiểm tra JSSE provider/JDK được triển khai; không giả định mọi nhà cung cấp giống nhau |
| Bắt tay TLS thành công nhưng ứng dụng đọc dữ liệu sai | Chọn `h2` trong ALPN nhưng dùng parser HTTP/1.1 hoặc ngược lại | Chuyển đến bộ xử lý đúng với giao thức đã chọn |
| Bắt tay lỗi chứng chỉ hoặc hostname | Cấu hình trust store, chứng chỉ hoặc xác thực tên máy chủ không đúng | Sửa cấu hình xác thực TLS; ALPN không thay thế kiểm tra danh tính |
| Đặt `"TLSv1.3"` vào danh sách ALPN | Nhầm phiên bản TLS với giao thức ứng dụng | Dùng `setProtocols` cho TLS, `setApplicationProtocols` cho ALPN |

### Gỡ lỗi đúng lớp

Khi thử tích hợp, kiểm tra theo thứ tự:

1. **Có bảo mật TLS đúng không?** Xác nhận chứng chỉ/trust, tên máy chủ, phiên bản TLS đang bật và cipher suite phù hợp.
2. **Đã cấu hình trước handshake chưa?** Kiểm tra `getSSLParameters().getApplicationProtocols()` trên **chính** socket/engine.
3. **Hai phía có định danh ALPN giao nhau không?** Ví dụ `"h2"` và `"http/1.1"` phải viết **khớp chính xác**.
4. **Có callback chọn giao thức không?** Nếu có, kiểm tra kết quả callback và giá trị peer đã chào mời.
5. **Sau handshake thực sự chọn gì?** Gọi `getApplicationProtocol()`, ghi nhận kết quả an toàn rồi chuyển đúng bộ xử lý tầng ứng dụng.

Khi cần xem handshake tại môi trường thử nghiệm, có thể bật công cụ gỡ lỗi JSSE, chẳng hạn:

```bash
java -Djavax.net.debug=ssl,handshake AlpnParametersDemo
```

**Lưu ý:** Lệnh với `AlpnParametersDemo` ở mục 5 **không thực hiện handshake**, nên không thể có vết đàm phán ALPN thật. Để thấy `ClientHello`, phần mở rộng ALPN và kết quả chọn, bật debug trên **ứng dụng thực sự kết nối TLS**. Nhật ký handshake có thể chứa thông tin cấu hình và danh tính máy chủ; chỉ thu thập/chia sẻ ở phạm vi phù hợp.

## 10. Những lưu ý hiện đại khi áp dụng

**Chỉ quảng bá những giao thức ứng dụng mà chương trình thực sự xử lý được.** Nếu ứng dụng không có bộ xử lý HTTP/2, đừng đặt `h2` chỉ vì muốn “ưu tiên giao thức mới”. Đàm phán thành công sẽ buộc hai đầu nói chuyện theo giao thức tương ứng.

**Không dùng ALPN làm cơ chế mã hóa.** Việc bảo vệ dữ liệu phụ thuộc vào bắt tay TLS, xác thực danh tính và các thuật toán mật mã; ALPN chỉ chọn giao thức ứng dụng. Một phiên TLS an toàn vẫn có thể thương lượng `http/1.1`.

**TLS 1.2 và TLS 1.3 vẫn là các lựa chọn hiện đại phổ biến.** Không cần cố bật phiên bản TLS cũ để sử dụng ALPN. Khi muốn giới hạn phiên bản, hãy đối chiếu chuẩn và chính sách TLS của hệ thống, không tự ý phá vỡ mặc định an toàn của provider.

**Ưu tiên API của framework khi framework sở hữu kết nối.** Trong ứng dụng HTTP hiện đại, thư viện HTTP client/server có thể tự điều khiển ALPN. Chỉnh trực tiếp một `SSLSocket` mà framework không dùng sẽ không có tác dụng; thay đổi tùy tiện thông số TLS của framework cũng có thể gây xung đột.

**Sử dụng đúng trạng thái và vòng đời.** Việc thương lượng diễn ra trong handshake. Sau đó, `getApplicationProtocol()` thể hiện giao thức của **kết nối cụ thể**, không phải cấu hình toàn cục trong `SSLParameters`; mỗi kết nối cần được kiểm tra riêng.

**Ghi nhớ tính tương thích của provider.** Một số API có sẵn trong JDK từ Java 9 nhưng triển khai ALPN và hành vi cảnh báo chi tiết vẫn phụ thuộc SSL provider, chính sách bảo mật và hệ thống đối tác. Kiểm tra liên thông với phiên bản JDK/driver TLS sẽ triển khai thực tế.

## 11. Câu hỏi tự kiểm tra

1. **Đâu là điểm khác nhau giữa `setProtocols` và `setApplicationProtocols`?** Phương thức thứ nhất cấu hình phiên bản TLS; phương thức thứ hai cấu hình định danh giao thức ứng dụng cho ALPN.
2. **Vì sao gọi `setApplicationProtocols` trên một `SSLParameters` có thể chưa đủ?** Vì còn cần `SSLSocket.setSSLParameters` hoặc `SSLEngine.setSSLParameters` để đưa cấu hình vào kết nối.
3. **Mảng `{"h2", "http/1.1"}` có nghĩa cả hai sẽ được dùng đồng thời không?** Không. Nó là danh sách ứng viên; nếu thương lượng ALPN thành công, chọn **một** giao thức cho kết nối.
4. **Server đặt `{"http/1.1", "h2"}`, client chào `{"h2", "http/1.1"}`. SunJSSE mặc định chọn gì?** `http/1.1`, vì là giá trị chung đứng đầu trong thứ tự ưu tiên của server.
5. **`getApplicationProtocols()` trả về gì sau khi đã cấu hình?** Mảng chứa **các giao thức được cấu hình**, không phải kết quả đã thương lượng.
6. **Sau bắt tay gọi API nào để biết giao thức đã chọn?** `SSLSocket.getApplicationProtocol()` hoặc `SSLEngine.getApplicationProtocol()`.
7. **Truyền `null` hoặc `{""}` vào `setApplicationProtocols` có tắt ALPN không?** Không. Cả hai là đầu vào không hợp lệ; để không dùng danh sách ALPN, truyền **mảng rỗng** `new String[0]`.
8. **Đã cấu hình `h2` có nghĩa HTTP/2 hoạt động ngay chưa?** Chưa. Chương trình vẫn phải thực sự hỗ trợ framing, luồng và quy tắc HTTP/2.
9. **Vì sao không được tắt xác thực chứng chỉ chỉ để ALPN hoạt động?** Vì ALPN không xác minh danh tính peer; tắt xác thực khiến TLS không còn bảo vệ đúng khỏi máy chủ giả mạo.

## Tài liệu chính thức

- [SSLParameters — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLParameters.html)
- [SSLSocket — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLSocket.html)
- [SSLEngine — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLEngine.html)
- [SSLServerSocket — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLServerSocket.html)
- [Java Secure Socket Extension (JSSE) Reference Guide — Oracle JDK 25](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html)
- [JEP 244 — TLS Application-Layer Protocol Negotiation Extension](https://openjdk.org/jeps/244)
- [RFC 7301 — TLS Application-Layer Protocol Negotiation](https://www.rfc-editor.org/rfc/rfc7301)
