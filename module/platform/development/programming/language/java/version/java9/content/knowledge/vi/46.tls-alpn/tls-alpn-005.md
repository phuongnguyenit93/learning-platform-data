# Phân biệt ALPN với lựa chọn phiên bản TLS trong Java 9+

## 1. Hai câu hỏi khác nhau trong một TLS handshake

Khi client và server thiết lập kết nối TLS, chúng phải thống nhất **phiên bản giao thức bảo mật** để bảo vệ đường truyền. Với nhiều dịch vụ, chúng còn cần thống nhất **giao thức ứng dụng** sẽ chạy *bên trong* đường truyền đó. Hai quyết định này có liên hệ nhưng giải quyết hai vấn đề khác nhau.

- **Lựa chọn phiên bản TLS (TLS version negotiation):** “Kết nối sẽ dùng `TLSv1.3` hay `TLSv1.2` để bảo vệ dữ liệu?” Đây là quyết định ở **tầng TLS**.
- **ALPN (Application-Layer Protocol Negotiation):** “Sau khi kết nối TLS được thiết lập, hai phía sẽ nói `h2` (HTTP/2) hay `http/1.1`?” Đây là quyết định về **giao thức tầng ứng dụng chạy trên TLS**.
- **Cả hai có thể diễn ra trong cùng một TLS handshake.** ALPN là một phần mở rộng của TLS handshake; nó **không phải** cơ chế thay thế việc chọn TLS version.
- Java 9 bổ sung API ALPN cho JSSE theo JEP 244. Những API đó vẫn được hỗ trợ trên các JDK hiện hành. Để học và triển khai mới, ví dụ dùng Java 17+ và tập trung vào `TLSv1.3`, `TLSv1.2` cùng các tên ALPN còn dùng như `h2`, `http/1.1`.

Ví dụ minh họa kết quả hợp lệ:

~~~text
TLS version được chọn: TLSv1.3
ALPN application protocol: h2

=> HTTP/2 chạy trên một kết nối được bảo vệ bằng TLS 1.3.
~~~

Một kết quả khác cũng có thể hợp lệ (tùy chính sách, cipher và hệ thống):

~~~text
TLS version được chọn: TLSv1.2
ALPN application protocol: h2

=> HTTP/2 chạy trên TLS 1.2, nếu đáp ứng các ràng buộc HTTP/2/TLS.
~~~

**Lỗi cần tránh ngay từ đầu:** `h2` **không phải phiên bản TLS**, còn `TLSv1.3` **không phải phiên bản HTTP**.

## 2. Bảng so sánh trực tiếp

| Tiêu chí | Lựa chọn phiên bản TLS | ALPN |
|---|---|---|
| Quyết định | Phiên bản **giao thức bảo mật**. | Giao thức **ứng dụng** truyền trên kênh TLS. |
| Giá trị thường gặp | `TLSv1.3`, `TLSv1.2`. | `h2`, `http/1.1`; dịch vụ khác có identifier riêng. |
| Mục đích | Thống nhất định dạng handshake, thuật toán/mô hình bảo mật và cách bảo vệ dữ liệu. | Giúp client và server thống nhất giao thức ứng dụng trong cùng handshake, không cần thêm vòng thương lượng riêng sau khi kết nối. |
| Chỗ cấu hình trong JSSE | `SSLParameters.setProtocols(String[])` hoặc `SSLSocket/SSLEngine.setEnabledProtocols(String[])`. | `SSLParameters.setApplicationProtocols(String[])`. |
| Kết quả sau handshake | `SSLSession.getProtocol()`, ví dụ `TLSv1.3`. | `SSLSocket.getApplicationProtocol()` hoặc `SSLEngine.getApplicationProtocol()`, ví dụ `h2`. |
| Cơ chế trong TLS 1.3 | Client gửi `supported_versions`; server chọn một phiên bản hợp lệ và trả trong `ServerHello`. | Client gửi danh sách ALPN trong `ClientHello`; server trả ALPN đã chọn trong `EncryptedExtensions`. |
| Nếu không có lựa chọn tương thích | TLS handshake không thể hoàn tất với phiên bản/cấu hình được phép. | Nếu ALPN được gửi và server không hỗ trợ identifier nào được đề xuất, theo RFC 7301 server phải báo lỗi `no_application_protocol`; nếu ALPN không được dùng thì kết quả còn tùy giao thức ứng dụng. |
| Có bảo đảm kết nối an toàn không? | Việc chọn version chỉ là một phần: còn chứng chỉ, kiểm tra hostname, cipher suite, trust policy... | **Không.** ALPN không xác thực server hoặc tự mã hóa thêm dữ liệu. |

Trong JSSE, các mục cấu hình này có thể cùng nằm trong **một** đối tượng `SSLParameters`, nhưng tác động lên **hai trường khác nhau**. Thiết lập một trường không tự thiết lập trường còn lại.

## 3. Tại sao Java 9 có ALPN, và điều gì vẫn được dùng?

ALPN được chuẩn hóa trong **RFC 7301** nhằm cho phép client gửi danh sách giao thức ứng dụng mà nó có thể sử dụng ngay trong `ClientHello`. Server chọn một giao thức mà cả hai cùng hỗ trợ. ALPN đặc biệt quan trọng với HTTP/2 over TLS vì client và server cần thống nhất `h2` trước khi trao đổi frame HTTP/2.

**Java 9 / JEP 244** bổ sung các phương thức cho `javax.net.ssl.SSLParameters`, `SSLSocket` và `SSLEngine`, gồm:

- `SSLParameters.setApplicationProtocols(String[])` và `getApplicationProtocols()`: cấu hình/đọc danh sách identifier ứng dụng, ví dụ `{"h2", "http/1.1"}`.
- `SSLSocket.getApplicationProtocol()`, `SSLEngine.getApplicationProtocol()`: đọc ứng dụng đã được thương lượng trên kết nối.
- `getHandshakeApplicationProtocol()`: quan sát kết quả ALPN trong khi handshake đang diễn ra.
- `setHandshakeApplicationProtocolSelector(...)`: tùy chỉnh việc chọn ứng dụng ở phía server khi cần; không phải nơi chọn TLS version.

Các phương thức này vẫn có trong API Java SE hiện nay. **Đừng nhầm dấu mốc Java 9 của ALPN với yêu cầu phải dùng TLS 1.3**: TLS 1.3 được hỗ trợ trong các JDK sau Java 9; ALPN có thể hoạt động cùng TLS 1.2 hoặc TLS 1.3 trong các triển khai hiện đại phù hợp.

Ứng dụng thường chỉ cần đặt danh sách ALPN trước handshake, để JSSE thực hiện thương lượng. Không cần tự xây `ClientHello` hay tự viết parser cho extension TLS.

## 4. Hai quá trình diễn ra thế nào?

### 4.1. Trường hợp TLS 1.3

Trong TLS 1.3 (RFC 8446), client có thể gửi cả `supported_versions` và `application_layer_protocol_negotiation` trong `ClientHello`.

~~~text
CLIENT                                               SERVER
  |                                                     |
  | ClientHello                                         |
  |   supported_versions = [TLS 1.3, TLS 1.2]            |
  |   ALPN = [h2, http/1.1]                              |
  |---------------------------------------------------->|
  |                                                     |
  |                     ServerHello                     |
  |                       supported_versions = TLS 1.3  |
  |<----------------------------------------------------|
  |                                                     |
  |        {EncryptedExtensions: ALPN = h2}              |
  |<----------------------------------------------------|
  |                                                     |
  |      ... certificate / Finished / Finished ...       |
  |<===================================================>|
  |                                                     |
  | Ứng dụng gửi HTTP/2 frame qua kênh TLS 1.3           |
  |<===================================================>|
~~~

Ký hiệu `{...}` ở đây thể hiện thông điệp được bảo vệ theo quy trình TLS 1.3; biểu đồ chỉ lược bớt các thông điệp không liên quan tới hai mục đang học.

Điểm quan trọng:

1. **Phiên bản TLS** được chọn trong quá trình thiết lập ngữ cảnh bảo mật, dùng `supported_versions` ở TLS 1.3.
2. **ALPN** xác định ứng dụng, không quyết định khóa mật mã. Ở TLS 1.3, server đưa ALPN được chọn vào **`EncryptedExtensions`**.
3. ALPN không mang “TLSv1.3” như một lựa chọn ứng dụng. Tương tự, `supported_versions` không mang `h2` hay `http/1.1`.

### 4.2. Trường hợp TLS 1.2

Trong TLS 1.2, server có thể trả kết quả ALPN ở extension thuộc **`ServerHello`** theo RFC 7301. Điểm này **khác vị trí ALPN trong TLS 1.3**. Lựa chọn phiên bản TLS 1.2 dùng cơ chế thương lượng phiên bản của TLS thế hệ đó.

Điều không đổi là **ý nghĩa**:

~~~text
TLS version: TLSv1.2     <- giao thức bảo mật
ALPN:        h2          <- giao thức ứng dụng
~~~

Không nên dùng chi tiết “ALPN nằm trong `ServerHello`” như một quy tắc phổ quát cho mọi phiên bản TLS: với TLS 1.3, thông điệp chứa ALPN phía server là `EncryptedExtensions`.

## 5. Hai kết quả độc lập nhưng có ràng buộc tương thích

Giả sử client cho phép `TLSv1.3` và `TLSv1.2`, đồng thời đề xuất `h2`, `http/1.1`. Nếu server và chính sách bảo mật cho phép, một số cặp kết quả có thể là:

| TLS đã chọn | ALPN đã chọn | Ý nghĩa |
|---|---|---|
| `TLSv1.3` | `h2` | HTTP/2 chạy trên TLS 1.3. |
| `TLSv1.3` | `http/1.1` | HTTP/1.1 chạy trên TLS 1.3. |
| `TLSv1.2` | `h2` | HTTP/2 chạy trên TLS 1.2 **khi thỏa các giới hạn TLS/cipher của HTTP/2**. |
| `TLSv1.2` | `http/1.1` | HTTP/1.1 chạy trên TLS 1.2. |

**Không được coi bảng trên là 4 lựa chọn luôn khả dụng.** Hai đầu phải có tập version giao nhau, giao thức ứng dụng phù hợp, cipher/thuật toán hợp lệ, chính sách triển khai tương thích và chứng chỉ được xác thực.

Theo **RFC 9113**, HTTP/2 qua TLS yêu cầu ít nhất TLS 1.2 và có hạn chế với một số TLS 1.2 cipher suites. HTTP/2 trên TLS **sử dụng identifier ALPN `h2`**. `h2c` không phải identifier ALPN dùng trong kết nối HTTPS; không đưa `h2c` vào `setApplicationProtocols` để thương lượng HTTP/2 qua TLS.

**ALPN không tự nâng TLS 1.2 lên TLS 1.3:** nếu chính sách chỉ cho phép TLS 1.2 thì server có thể chọn `h2` trên TLS 1.2, nhưng không vì có `h2` mà tự biến thành TLS 1.3.

**TLS 1.3 không tự ép HTTP/2:** nếu server chỉ có `http/1.1` và client đồng ý, ALPN vẫn có thể chọn `http/1.1` trong kênh TLS 1.3.

## 6. Cấu hình Java bằng `SSLParameters`

### 6.1. Danh sách TLS version được phép

~~~java
SSLParameters p = engine.getSSLParameters();
p.setProtocols(new String[] {"TLSv1.3", "TLSv1.2"});
engine.setSSLParameters(p);
~~~

`SSLParameters.setProtocols(...)` **giới hạn các phiên bản TLS có thể thương lượng**, không tuyên bố rằng đã chọn `TLSv1.3`. Kết quả thực tế chỉ được biết **sau handshake**. `engine.getEnabledProtocols()` đọc danh sách đang được bật, còn `engine.getSupportedProtocols()` đọc danh sách provider có thể hỗ trợ (chưa chắc đang được bật hoặc chính sách bảo mật cho phép dùng).

### 6.2. Danh sách ALPN được đề xuất

~~~java
SSLParameters p = engine.getSSLParameters();
p.setApplicationProtocols(new String[] {"h2", "http/1.1"});
engine.setSSLParameters(p);
~~~

`setApplicationProtocols` cấu hình **identifier ứng dụng**, không bật/tắt các phiên bản TLS. Mảng sắp theo **thứ tự ưu tiên**; phía chọn ứng dụng (thường là server) xác định kết quả phù hợp. Client đề xuất `h2` trước không đảm bảo server sẽ chọn `h2` nếu server có thứ tự ưu tiên khác hoặc quy tắc lựa chọn riêng.

Nếu mảng ALPN rỗng (`new String[0]`), phần mở rộng chỉ định giao thức ứng dụng sẽ không được sử dụng. Phương thức từ chối tham số `null` hoặc phần tử `null`/chuỗi rỗng. Tên ALPN là **identifier giao thức** theo quy ước đã đăng ký; `h2` và `http/1.1` là hai giá trị chuẩn, không phải chữ tự do đặt theo số TLS.

Cả hai loại cấu hình có thể được áp dụng trên `SSLEngine` hoặc `SSLSocket` bằng `setSSLParameters(...)`. Đặt trước khi bắt đầu handshake. Nếu server dùng danh sách lựa chọn ALPN, `SSLSocket`/`SSLEngine` còn có `setHandshakeApplicationProtocolSelector(...)` để tùy chỉnh lựa chọn.

### 6.3. Đọc kết quả sau handshake

| Giá trị cần đọc | Java API đúng | Giá trị minh họa |
|---|---|---|
| Phiên bản **TLS đã thương lượng** | `engine.getSession().getProtocol()` hoặc `socket.getSession().getProtocol()` sau handshake | `TLSv1.3` |
| Giao thức ứng dụng **ALPN đã thương lượng** | `engine.getApplicationProtocol()` hoặc `socket.getApplicationProtocol()` | `h2` |
| Giá trị ALPN trong handshake đang tiến hành | `getHandshakeApplicationProtocol()` | Có thể chưa sẵn sàng tại một thời điểm cụ thể |

**Chú ý kết quả của `getApplicationProtocol()`:** `null` nghĩa là chưa xác định việc dùng giao thức ứng dụng; chuỗi rỗng `""` nghĩa là không sử dụng application protocol; chuỗi khác rỗng là identifier được chọn. Với provider không triển khai thao tác này, có thể có `UnsupportedOperationException`. Không được hiểu `null`/`""` là `http/1.1` theo mặc định; giao thức ứng dụng cần xử lý theo quy định của nó.

`getHandshakeApplicationProtocol()` chỉ hữu ích trong tiến trình handshake và có thể trả `null` khi kết quả chưa được xác định. Trong ứng dụng bình thường, gọi `getApplicationProtocol()` sau khi `startHandshake()` thành công là đủ.

## 7. Ví dụ Java 17+ chạy được: cấu hình riêng TLS và ALPN

Ví dụ tự chứa sau chỉ dùng JSSE có sẵn trong JDK, **không truy cập mạng, không cần certificate hoặc server**. Nó tạo một `SSLEngine`, cấu hình danh sách TLS version và ALPN riêng biệt, rồi chỉ rõ **chưa có phiên bản hay ALPN thực sự được thương lượng vì chưa handshake**.

Tạo file **`TlsAlpnDemo.java`**:

~~~java
import java.util.Arrays;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLParameters;

public class TlsAlpnDemo {
    public static void main(String[] args) throws Exception {
        SSLEngine engine = SSLContext.getDefault()
                .createSSLEngine("example.invalid", 443);
        engine.setUseClientMode(true);

        // Câu hỏi 1: Phiên bản bảo mật TLS nào được phép?
        SSLParameters p = engine.getSSLParameters();
        p.setProtocols(new String[] {"TLSv1.3", "TLSv1.2"});

        // Câu hỏi 2: Giao thức ứng dụng nào được đề xuất qua ALPN?
        p.setApplicationProtocols(new String[] {"h2", "http/1.1"});

        // Áp dụng cả hai cấu hình lên chính SSLEngine.
        engine.setSSLParameters(p);

        System.out.println("Allowed TLS versions: "
                + Arrays.toString(engine.getEnabledProtocols()));
        System.out.println("Offered ALPN protocols: "
                + Arrays.toString(
                        engine.getSSLParameters().getApplicationProtocols()));

        // Chưa chạy handshake: chưa thể đọc kết quả thương lượng.
        String alpn = engine.getApplicationProtocol();
        System.out.println("ALPN before handshake: "
                + (alpn == null ? "undetermined"
                        : alpn.isEmpty() ? "none" : alpn));
        System.out.println("TLS negotiated: "
                + (engine.getHandshakeSession() == null
                        ? "not yet" : "handshake in progress"));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+ thông dụng có TLS 1.3/1.2:

~~~bash
javac TlsAlpnDemo.java
java TlsAlpnDemo
~~~

**Stdout đã kiểm tra với OpenJDK 24/SunJSSE:**

~~~text
Allowed TLS versions: [TLSv1.3, TLSv1.2]
Offered ALPN protocols: [h2, http/1.1]
ALPN before handshake: undetermined
TLS negotiated: not yet
~~~

Kết quả này thể hiện rõ:

1. `[TLSv1.3, TLSv1.2]` là tập **cho phép**, chưa phải version được chọn.
2. `[h2, http/1.1]` là danh sách **đề xuất**, chưa phải ALPN đã chọn.
3. `ALPN before handshake: undetermined` nghĩa là chưa đủ dữ kiện để kết luận giao thức ứng dụng.
4. `TLS negotiated: not yet` nghĩa là `SSLEngine` chưa thực hiện một vòng handshake, nên không có kết quả TLS version.

Ví dụ sử dụng `example.invalid` chỉ làm *peer host* khi khởi tạo engine, không mở socket. Nó là chương trình độc lập đầy đủ và không chứng minh kết quả thương lượng với server thực.

## 8. Đọc đồng thời kết quả khi kết nối TLS thực

Khi có server thật và certificate/truststore hợp lệ, ứng dụng có thể dùng `SSLSocket` và đọc **cả hai kết quả sau khi handshake hoàn tất**. Đoạn sau là **mã tích hợp** để đưa vào phương thức phù hợp; không có stdout cố định vì kết quả phụ thuộc server, chứng chỉ và chính sách TLS.

~~~java
// Mã tích hợp: cần các import javax.net.ssl.* và Java phù hợp.
String host = "example.com";

try (SSLSocket socket = (SSLSocket) SSLContext.getDefault()
        .getSocketFactory().createSocket(host, 443)) {

    SSLParameters p = socket.getSSLParameters();
    p.setProtocols(new String[] {"TLSv1.3", "TLSv1.2"});
    p.setApplicationProtocols(new String[] {"h2", "http/1.1"});
    p.setEndpointIdentificationAlgorithm("HTTPS");
    socket.setSSLParameters(p);

    socket.startHandshake(); // Server và truststore quyết định thành công hay lỗi.

    String selectedTls = socket.getSession().getProtocol();
    String selectedAlpn = socket.getApplicationProtocol();

    System.out.println("Negotiated TLS: " + selectedTls);
    System.out.println("Negotiated ALPN: "
            + (selectedAlpn == null ? "undetermined"
                : selectedAlpn.isEmpty() ? "(none)" : selectedAlpn));

    // Phần gửi HTTP/1.1 hoặc HTTP/2 phải tuân thủ selectedAlpn.
}
~~~

`setEndpointIdentificationAlgorithm("HTTPS")` chỉ định kiểm tra danh tính host theo quy tắc HTTPS. Đây là một phần của bảo mật kết nối, **không phải thao tác ALPN**. Với ứng dụng HTTPS thực tế, thường nên dùng `java.net.http.HttpClient` (Java 11+) hoặc thư viện HTTP tin cậy, để thư viện tự xử lý HTTP framing, ALPN và xác thực TLS đúng chuẩn. Đoạn `SSLSocket` dùng để **quan sát rõ hai kết quả**.

Nếu server không thỏa TLS versions/cipher hoặc chứng chỉ không hợp lệ, handshake có thể ném `SSLHandshakeException` trước khi đọc kết quả. Nếu cả hai phía dùng ALPN nhưng **không có identifier ứng dụng chung**, `no_application_protocol` có thể làm handshake thất bại. Không sửa lỗi ALPN bằng cách bỏ kiểm tra chứng chỉ hoặc cho phép TLS phiên bản yếu.

## 9. Những nhầm lẫn khi triển khai

### Nhầm lẫn 1: “`TLSv1.3` đồng nghĩa với HTTP/2”

**Sai.** TLS 1.3 bảo vệ kết nối, còn HTTP/2 là giao thức ứng dụng. Kết nối TLS 1.3 có thể nói HTTP/1.1 nếu ALPN chọn `http/1.1`. ALPN không thay đổi version TLS.

### Nhầm lẫn 2: “`h2` có nghĩa là TLS 1.2”

**Sai.** `h2` là tên ALPN cho HTTP/2 chạy qua TLS. HTTP/2 có thể hoạt động trên TLS 1.2 hoặc TLS 1.3 nếu đáp ứng yêu cầu của RFC 9113. Identifier `h2` không chứa thông tin phiên bản TLS.

### Nhầm lẫn 3: “`setApplicationProtocols(...)` bật TLS 1.3”

**Sai.** Nó chỉ xác định lựa chọn **giao thức ứng dụng**. Muốn điều chỉnh phiên bản TLS cho phép, sử dụng `setProtocols(...)` hoặc `setEnabledProtocols(...)`.

### Nhầm lẫn 4: “`setProtocols(...)` buộc server chạy HTTP/2”

**Sai.** Nó chỉ thay đổi tập TLS version. Muốn đề xuất HTTP/2 qua ALPN, cấu hình `setApplicationProtocols(new String[] {"h2", "http/1.1"})` và bảo đảm server hỗ trợ.

### Nhầm lẫn 5: “Danh sách đã cấu hình là kết quả đã thương lượng”

**Sai.** `getEnabledProtocols()` và `getApplicationProtocols()` trả danh sách **được phép/đề xuất**. Chỉ `SSLSession.getProtocol()` và `getApplicationProtocol()` **sau handshake** mới cho biết kết quả thực tế.

### Nhầm lẫn 6: “ALPN lúc nào cũng nằm trong ServerHello”

**Không đúng với TLS 1.3.** Theo RFC 7301 trong ngữ cảnh TLS 1.2, server chọn ALPN ở `ServerHello`. Với TLS 1.3, kết quả ALPN ở `EncryptedExtensions`. Đừng chẩn đoán packet capture TLS 1.3 theo bố cục của TLS 1.2.

### Nhầm lẫn 7: “Client ưu tiên `h2` trước thì chắc chắn dùng HTTP/2”

**Sai.** Server chọn giao thức từ các tên hai phía cùng hỗ trợ theo chính sách/ưu tiên của mình. Nếu không có giao nhau trong lúc dùng ALPN, có thể kết thúc handshake với `no_application_protocol`. Nếu ALPN không được dùng, quy tắc ứng dụng quyết định cách xử lý, không có phép ánh xạ phổ quát sang HTTP/1.1.

### Nhầm lẫn 8: “ALPN làm kết nối an toàn”

**Sai.** ALPN chỉ chọn giao thức ứng dụng. Kiểm tra certificate chain, hostname, TLS version/cipher được phép và các chính sách của runtime vẫn cần đúng. Tập trung cấu hình TLS 1.3; giữ TLS 1.2 khi thực sự cần tương thích và có cấu hình an toàn. Không dựa vào TLS 1.0/1.1 trong triển khai mới.

### Nhầm lẫn 9: “`getApplicationProtocol()` trả `null` tức là HTTP/1.1”

**Sai.** Theo Javadoc, `null` nghĩa chưa xác định việc dùng ALPN; chuỗi rỗng nghĩa không dùng application protocol; chỉ chuỗi khác rỗng mới là identifier đã thương lượng. Một ứng dụng có thể tự định nghĩa hành vi khi không có ALPN theo chuẩn riêng, nhưng không được coi đó là giá trị do ALPN trả về.

## 10. Khắc phục lỗi theo đúng tầng

| Triệu chứng | Kiểm tra trước | Không nên làm |
|---|---|---|
| `SSLHandshakeException` do không có TLS version/cipher chung | Danh sách từ `getEnabledProtocols()` hai phía, chính sách JDK/OS và cipher suites. | Thêm `h2` vào ALPN để “sửa phiên bản TLS”. |
| Handshake báo `no_application_protocol` | Tập tên ALPN của client và server (`h2`, `http/1.1`...) cùng thứ tự/logic lựa chọn server. | Bật TLS phiên bản yếu hơn khi lỗi là không có protocol ứng dụng chung. |
| Kết nối thành công với `TLSv1.3` nhưng ứng dụng là HTTP/1.1 | Đọc `getApplicationProtocol()` và cấu hình HTTP/2 phía server, proxy, load balancer. | Coi TLS 1.3 tự động kích hoạt HTTP/2. |
| ALPN không có giá trị trước handshake | `startHandshake()`/điều phối `SSLEngine.wrap/unwrap` đã hoàn tất chưa? | Sử dụng danh sách cấu hình như một kết quả đã chọn. |
| `h2` được chọn nhưng HTTP/2 vẫn lỗi | Kiểm tra framing/HTTP/2 preface, HTTP/2 yêu cầu TLS/cipher, thư viện HTTP. | Quy tất cả lỗi HTTP/2 cho thương lượng TLS version. |
| Sai khác khi qua reverse proxy | Kiểm tra cả hai đoạn TLS (client-proxy, proxy-backend); mỗi đoạn có thể có TLS version và ALPN riêng. | Cho rằng ALPN ở kết nối phía client luôn giống phía backend. |

Có thể bật chẩn đoán JSSE khi phát triển:

~~~bash
java -Djavax.net.debug=ssl,handshake TlsAlpnDemo
~~~

**Lưu ý:** vì ví dụ `TlsAlpnDemo` không chạy handshake, cờ debug trên không tạo transcript thương lượng thực. Với ứng dụng thật đã kết nối server, log handshake mới giúp quan sát `supported_versions`, `application_layer_protocol_negotiation` và lỗi liên quan. Log TLS có thể chứa thông tin nhạy cảm về kết nối và môi trường; chỉ bật có kiểm soát khi điều tra.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Client đề xuất `TLSv1.3`, `TLSv1.2` và ALPN `h2`, `http/1.1`. Server chọn `TLSv1.2` và `h2`. Có mâu thuẫn không?

**Đáp án:** Không. Hai quyết định khác nhau. Cặp này hợp lệ nếu triển khai HTTP/2 trên TLS 1.2 đáp ứng yêu cầu RFC 9113.

**Câu 2.** Cần biết phiên bản TLS thực tế của một `SSLSocket` đã handshake xong. Dùng phương thức nào?

**Đáp án:** `socket.getSession().getProtocol()`, chẳng hạn `TLSv1.3`. Không dùng `getApplicationProtocol()`.

**Câu 3.** Cần biết kết quả ALPN của kết nối. Dùng phương thức nào?

**Đáp án:** `socket.getApplicationProtocol()` hoặc `engine.getApplicationProtocol()` sau handshake; có thể nhận `h2` hay `http/1.1`.

**Câu 4.** `SSLParameters.setProtocols(...)` và `setApplicationProtocols(...)` có thể thay thế nhau không?

**Đáp án:** Không. Phương thức thứ nhất chọn **tập TLS versions** cho phép, phương thức thứ hai đề xuất **giao thức ứng dụng**.

**Câu 5.** Tại sao RFC 7301 nhắc tới ALPN ở `ServerHello`, còn TLS 1.3 lại ở `EncryptedExtensions`?

**Đáp án:** Bố cục handshake khác nhau. TLS 1.3 giữ các phần cần cho lựa chọn mật mã/phiên bản ở `ServerHello` và chuyển các extension khác như ALPN sang `EncryptedExtensions` được bảo vệ.

**Câu 6.** ALPN có thay thế kiểm tra hostname/chứng chỉ không?

**Đáp án:** Không. ALPN chỉ đồng thuận tên ứng dụng. Xác thực và chính sách mã hóa TLS vẫn là trách nhiệm riêng.

## Tài liệu tham khảo còn áp dụng

- [Java SE 26 — `SSLParameters`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLParameters.html): `setProtocols`, `setApplicationProtocols`, cách cấu hình trên `SSLSocket`/`SSLEngine`.
- [Java SE 26 — `SSLEngine`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLEngine.html): `getApplicationProtocol`, `getHandshakeApplicationProtocol`, cấu hình handshake.
- [Java SE 26 — `SSLSocket`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLSocket.html): `startHandshake`, đọc ALPN đã thương lượng.
- [Java SE 26 — `SSLSession`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLSession.html): `getProtocol()` trả phiên bản TLS/DTLS được dùng cho phiên kết nối.
- [Java SE 26 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/26/security/java-secure-socket-extension-jsse-reference-guide.html): cách thiết lập ALPN và kết quả với TLS thực.
- [JEP 244 — TLS Application-Layer Protocol Negotiation Extension](https://openjdk.org/jeps/244): bổ sung ALPN trong Java 9 và API JSSE.
- [RFC 7301 — TLS ALPN](https://www.rfc-editor.org/rfc/rfc7301): tên ALPN, quy trình đề xuất/chọn và lỗi `no_application_protocol`.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): `supported_versions`, `EncryptedExtensions` và vị trí ALPN trong TLS 1.3.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): ALPN identifier `h2` và ràng buộc TLS của HTTP/2.

**Nhớ đúng hai kết quả sau handshake:** `SSLSession.getProtocol()` trả lời **“TLS version nào?”**; `getApplicationProtocol()` trả lời **“Ứng dụng nào chạy qua TLS?”**. Hai lựa chọn phối hợp để kết nối hoạt động, nhưng không thay thế nhau.
