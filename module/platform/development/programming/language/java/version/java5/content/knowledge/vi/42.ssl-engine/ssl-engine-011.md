# Xác minh danh tính đối tác, chứng thư và tham số TLS với SSLEngine

## 1. Kênh có mã hóa chưa đủ để biết đang nói chuyện với ai

Khi kết nối đến `api.example.com`, máy khách cần biết cả hai điều: dữ liệu được bảo vệ trên đường truyền, và đầu bên kia đúng là dịch vụ dự định gọi. Một chứng thư hợp lệ cho `other.example.com` không trở thành chứng thư đúng cho `api.example.com` chỉ vì được một CA đáng tin cấp.

Với `SSLEngine`, ứng dụng tự điều khiển bắt tay và I/O. Do đó, ứng dụng phải cấu hình chính sách xác thực **trước bắt tay**, rồi chỉ cho dữ liệu nghiệp vụ đi qua sau khi TLS và các kiểm tra ứng dụng cần thiết đã thành công.

Ba lớp câu hỏi cần tách rõ:

| Lớp kiểm tra | Câu hỏi |
| --- | --- |
| Tin cậy chứng thư | Chuỗi chứng thư có được chấp nhận theo nguồn tin cậy và chính sách chứng thư không? |
| Danh tính đầu cuối | Danh tính trong chứng thư có khớp dịch vụ mà máy khách dự định gọi không? |
| Quyền ứng dụng | Đối tác đã xác thực có quyền thực hiện thao tác này không? |

Bài này dùng API Java 17+ và chính sách TLS hiện đại. Không dùng cách bỏ qua xác thực để làm bắt tay “chạy được”.

## 2. Những thành phần nào chịu trách nhiệm?

| Thành phần | Trách nhiệm |
| --- | --- |
| `SSLContext` | Cung cấp engine với bộ quản lý khóa và tin cậy đã cấu hình |
| `KeyManager` | Chọn danh tính cục bộ: khóa riêng và chuỗi chứng thư để xuất trình |
| `TrustManager` | Quyết định có chấp nhận chứng thư của đối tác không |
| `SSLParameters` | Cấu hình giao thức, bộ mã, SNI, kiểm tra danh tính, ALPN, xác thực máy khách |
| `SSLSession` | Cho đọc thông tin đã thương lượng sau bắt tay |

Không nhầm **kho khóa** với **kho tin cậy** chỉ vì cả hai có thể được lưu bằng `KeyStore`. Kho khóa phục vụ danh tính mà ta xuất trình; kho tin cậy chứa các điểm tin cậy để đánh giá đối tác. Tệp chứa chứng thư công khai không tự cung cấp khóa riêng để ký trong bắt tay.

Vai trò của bộ quản lý khóa được định nghĩa trong [KeyManagerFactory API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html). Vai trò của nguồn tin cậy nằm trong [TrustManagerFactory API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html).

## 3. Xác thực chuỗi chứng thư

Trong mô hình chứng thư X.509, đối tác thường gửi chứng thư đầu cuối cùng các chứng thư trung gian cần thiết. Bộ kiểm tra phải xây dựng và đánh giá đường dẫn tới một điểm tin cậy được cấu hình.

Các khía cạnh thường liên quan gồm thời hạn hiệu lực, chữ ký, ràng buộc CA, mục đích sử dụng khóa/chứng thư và giới hạn thuật toán. Không tự thay toàn bộ quá trình bằng một phép so sánh tên người cấp hoặc gọi riêng `certificate.checkValidity()`: kiểm tra thời hạn chỉ trả lời một phần nhỏ của bài toán.

Nên dùng bộ kiểm tra PKIX của nền tảng hoặc thành phần được tổ chức phê duyệt. Khi cần tùy biến `TrustManager` cho engine, phải bảo toàn ngữ cảnh kết nối và hành vi xác thực; `X509ExtendedTrustManager` có các overload nhận `SSLEngine` để kiểm tra gắn với tham số của kết nối. Xem [X509ExtendedTrustManager API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/X509ExtendedTrustManager.html).

Một số tình huống suy luận:

- Chứng thư còn hạn nhưng không có đường dẫn tới điểm tin cậy phù hợp: chưa đủ để chấp nhận.
- CA được tin nhưng chứng thư không dùng cho mục đích cần thiết: chưa đủ để chấp nhận.
- Chuỗi hợp lệ nhưng sai tên dịch vụ: vẫn phải từ chối theo chính sách xác minh danh tính.
- Chứng thư phát triển tự ký: chỉ đưa điểm tin cậy đã kiểm chứng vào môi trường thử nghiệm có phạm vi rõ ràng; không chấp nhận mọi chứng thư.

Kiểm tra thu hồi bằng OCSP/CRL và hành vi khi dịch vụ kiểm tra không truy cập được là một phần chính sách triển khai. Không mặc định rằng mọi JDK, nhà cung cấp và ngữ cảnh đều bật cùng một chế độ thu hồi. Cần cấu hình, kiểm thử lỗi và quan sát thời gian chờ phù hợp; không gắn nhãn “đã kiểm tra thu hồi” chỉ vì bắt tay thành công.

## 4. Danh tính tham chiếu, SAN và SNI

### 4.1. Danh tính mong đợi phải đến từ yêu cầu của máy khách

Danh tính tham chiếu là tên dịch vụ mà máy khách **dự định** kết nối, ví dụ tên trong cấu hình đích hoặc URL đã được ứng dụng chấp nhận. Không lấy tên do chứng thư đối tác tự khai rồi dùng chính tên đó làm điều kiện đối chiếu.

Với chứng thư dịch vụ hiện đại, cần cấp các tên phù hợp trong `subjectAltName` (SAN). Tên DNS và địa chỉ IP là các dạng định danh khác nhau. Một chứng thư có DNS SAN `api.example.com` không tự bảo đảm hợp lệ khi máy khách chủ đích gọi bằng địa chỉ IP.

Không tự viết thuật toán so khớp chuỗi đơn giản để xử lý wildcard, chữ hoa/thường hoặc tên miền quốc tế. Yêu cầu về nhận diện dịch vụ và SAN được trình bày trong [RFC 9525](https://www.rfc-editor.org/rfc/rfc9525.html). Hành vi chi tiết của bộ kiểm tra cụ thể cần được kiểm thử trên JDK triển khai; không thiết kế chứng thư mới dựa vào việc dự phòng tên Common Name.

### 4.2. SNI giúp chọn dịch vụ, không chứng minh danh tính

SNI gửi tên máy chủ trong bắt tay để phía máy chủ chọn cấu hình hoặc chứng thư phù hợp khi nhiều dịch vụ dùng chung địa chỉ mạng. Nó không thay thế xác minh chuỗi và đối chiếu danh tính.

Ví dụ thiết kế:

```text
Dịch vụ mong đợi: api.example.com
Địa chỉ vận chuyển đã phân giải: một địa chỉ IP
SNI: api.example.com
Tên đối chiếu chứng thư: api.example.com
```

Ứng dụng có thể kết nối socket tới địa chỉ IP đã phân giải, nhưng không vì thế thay danh tính dịch vụ mong đợi bằng một tên ngược DNS tùy ý.

`SNIHostName` dành cho tên DNS hợp lệ; không dùng nó để gửi một IP literal như tên SNI. Khi đích thực sự là IP, cần chính sách chứng thư IP tương ứng và xử lý SNI phù hợp. Quy tắc API được mô tả trong [SNIHostName API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SNIHostName.html).

### 4.3. Máy khách HTTPS phải bật endpoint identification

Với engine làm máy khách HTTPS, cấu hình:

```java
// Đoạn cấu hình; context đã được khởi tạo đúng.
SSLEngine engine = context.createSSLEngine("api.example.com", 443);
engine.setUseClientMode(true);

SSLParameters parameters = engine.getSSLParameters();
parameters.setEndpointIdentificationAlgorithm("HTTPS");
engine.setSSLParameters(parameters);
```

Truyền host cho `createSSLEngine(host, port)` không tự mở kết nối và không thay thế việc bật kiểm tra danh tính. Thuật toán `"HTTPS"` phù hợp cho ngữ cảnh HTTPS; giao thức khác cần chính sách nhận diện phù hợp. Cấu hình phải được áp dụng trước `beginHandshake()` hoặc lời gọi I/O đầu tiên khởi động bắt tay.

## 5. Cấu hình tham số TLS theo chính sách

Có ba khái niệm khác nhau:

- **Được hỗ trợ:** nhà cung cấp biết xử lý giao thức hoặc bộ mã đó.
- **Được bật:** kết nối hiện cho phép thương lượng mục đó.
- **Đã thương lượng:** lựa chọn thực tế sau bắt tay với đối tác.

Không bật tất cả mục được hỗ trợ. Danh sách hỗ trợ không phải danh sách khuyến nghị an toàn.

Ưu tiên TLS 1.3; cho phép TLS 1.2 khi chính sách tương thích yêu cầu và cấu hình đáp ứng yêu cầu an toàn hiện hành. Không bật lại SSL hoặc TLS 1.0/1.1 để né lỗi tương thích. Ví dụ trong bài dùng hai phiên bản TLS 1.3 và 1.2, nhưng hệ thống có thể chọn chỉ TLS 1.3 theo yêu cầu riêng.

Giữ các bộ mã mặc định an toàn của JDK được cập nhật thường ít rủi ro hơn sao chép một danh sách cũ. Nếu tổ chức cần danh sách riêng, phải xem xét tính tương thích giao thức, thuật toán, chứng thư và chính sách JDK. Việc một tên xuất hiện trong `getSupportedCipherSuites()` không bảo đảm nó vượt qua các giới hạn thuật toán của môi trường.

ALPN dùng để thương lượng giao thức ứng dụng, ví dụ `h2` hoặc `http/1.1`. Chỉ quảng bá những giao thức mà ứng dụng thật sự triển khai. Nếu ứng dụng chỉ có bộ phân tích HTTP/1.1 thì không được khai `h2` chỉ để danh sách trông đầy đủ.

API cấu hình các tham số này nằm trong [SSLParameters API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLParameters.html).

## 6. Chương trình Java 17+: kiểm tra chính sách máy khách HTTPS

Chương trình sau tạo engine và kiểm tra **cấu hình trước bắt tay**. Nó không mở socket, không liên hệ `api.example.com` và không chứng minh chứng thư của dịch vụ đó hợp lệ.

Lưu thành `TlsPeerPolicyDemo.java`:

```java
import java.util.Arrays;
import java.util.List;
import javax.net.ssl.SNIHostName;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLParameters;

public class TlsPeerPolicyDemo {
    public static void main(String[] args) throws Exception {
        String expectedHost = "api.example.com";

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, null, null);

        SSLEngine engine = context.createSSLEngine(expectedHost, 443);
        engine.setUseClientMode(true);

        List<String> supported = Arrays.asList(
                engine.getSupportedProtocols());
        String[] enabled = List.of("TLSv1.3", "TLSv1.2").stream()
                .filter(supported::contains)
                .toArray(String[]::new);
        if (enabled.length == 0) {
            throw new IllegalStateException("No allowed TLS protocol");
        }

        SSLParameters policy = engine.getSSLParameters();
        policy.setProtocols(enabled);
        policy.setEndpointIdentificationAlgorithm("HTTPS");
        policy.setServerNames(List.of(new SNIHostName(expectedHost)));
        policy.setApplicationProtocols(new String[] {"http/1.1"});
        engine.setSSLParameters(policy);

        SSLParameters actual = engine.getSSLParameters();
        SNIHostName serverName =
                (SNIHostName) actual.getServerNames().get(0);

        System.out.println("client=" + engine.getUseClientMode());
        System.out.println("referenceHost=" + engine.getPeerHost());
        System.out.println("endpoint="
                + actual.getEndpointIdentificationAlgorithm());
        System.out.println("sni=" + serverName.getAsciiName());
        System.out.println("alpn="
                + String.join(",", actual.getApplicationProtocols()));
    }
}
```

Chạy bằng JDK 17+ có nhà cung cấp JSSE thông thường:

```shell
javac TlsPeerPolicyDemo.java
java TlsPeerPolicyDemo
```

Stdout:

```text
client=true
referenceHost=api.example.com
endpoint=HTTPS
sni=api.example.com
alpn=http/1.1
```

Chương trình lấy giao của danh sách được chính sách cho phép với danh sách nhà cung cấp hỗ trợ; nó không tự mở rộng sang giao thức cũ khi giao rỗng. Để kiểm chứng bắt tay thật, còn cần vận chuyển byte giữa hai đầu, chứng thư phù hợp và kiểm tra cả tình huống từ chối.

`context.init(null, null, null)` sử dụng lựa chọn quản lý mặc định của nhà cung cấp. Đây không phải một cấu hình kho tin cậy riêng của tổ chức và cũng không có nghĩa chấp nhận mọi chứng thư.

## 7. Dùng kho tin cậy riêng có phạm vi rõ ràng

Nếu dịch vụ dùng CA nội bộ, có thể tạo một `SSLContext` riêng từ kho tin cậy đã kiểm chứng, thay vì thay đổi chính sách chung của toàn bộ JVM.

Ví dụ lớp tiện ích Java 17+ sau có thể biên dịch riêng; phương thức cần một tệp PKCS12 thực và mật khẩu do cơ chế cấu hình bí mật của ứng dụng cung cấp:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class ScopedTlsContext {
    private ScopedTlsContext() {
    }

    public static SSLContext fromTrustStore(
            Path file, char[] storePassword)
            throws GeneralSecurityException, IOException {
        KeyStore trustStore = KeyStore.getInstance("PKCS12");
        try (InputStream input = Files.newInputStream(file)) {
            trustStore.load(input, storePassword);
        }

        TrustManagerFactory factory =
                TrustManagerFactory.getInstance("PKIX");
        factory.init(trustStore);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, factory.getTrustManagers(), null);
        return context;
    }
}
```

Lưu thành `ScopedTlsContext.java` và biên dịch:

```shell
javac ScopedTlsContext.java
```

Lớp không có `main()`, vì vậy không có stdout khi chỉ biên dịch thành công. Hàm không nuốt lỗi đọc kho hoặc lỗi khởi tạo để quay về chế độ bỏ kiểm tra. Người gọi quản lý vòng đời mật khẩu, hạn chế bản sao và xóa mảng khi đã dùng xong; không ghi mật khẩu hoặc khóa riêng vào log.

Kho riêng này là nguồn tin cậy của context, không tự hợp nhất với toàn bộ CA công cộng. Cần xác định đúng phạm vi CA mong muốn trước triển khai. Nhập bừa chứng thư lấy từ kết nối đang lỗi có thể biến chính lỗi danh tính thành một điểm tin cậy mới.

## 8. Xác thực hai chiều: chứng thư máy khách không phải quyền truy cập

Trong TLS thông thường cho HTTPS, máy khách kiểm tra máy chủ. Với mTLS, máy chủ còn kiểm tra chứng thư máy khách, và máy khách phải có khóa riêng cùng chuỗi chứng thư phù hợp để xuất trình.

Phía máy chủ yêu cầu chứng thư máy khách bằng cấu hình:

```java
// Minh họa phía máy chủ: serverContext đã có KeyManager và TrustManager phù hợp.
SSLEngine server = serverContext.createSSLEngine();
server.setUseClientMode(false);
SSLParameters parameters = server.getSSLParameters();
parameters.setNeedClientAuth(true);
server.setSSLParameters(parameters);
```

`setNeedClientAuth(true)` yêu cầu xác thực máy khách; `setWantClientAuth(true)` chỉ yêu cầu theo chế độ tùy chọn. Không dùng chế độ tùy chọn nếu chính sách bắt buộc mọi kết nối đều phải có chứng thư máy khách. Hai chế độ không phải hai cờ cộng dồn; cấu hình một chế độ có thể xóa chế độ kia theo hợp đồng API.

Phía máy khách dùng `KeyManager` để lựa chọn chứng thư/khóa phù hợp với yêu cầu máy chủ. Việc có một chứng thư trong tệp chưa bảo đảm khóa riêng tương ứng có mặt hoặc được chọn.

Sau khi chuỗi chứng thư máy khách được chấp nhận, ứng dụng vẫn cần ánh xạ danh tính sang tài khoản dịch vụ và kiểm tra quyền. Không gán quyền quản trị chỉ vì chứng thư do CA nội bộ cấp, hoặc vì chuỗi Subject có chứa một từ mong muốn.

## 9. Đọc thông tin phiên sau bắt tay

Sau khi engine xác nhận bắt tay hoàn tất thành công, có thể đọc:

```java
// Minh họa trong luồng xử lý hoàn tất bắt tay.
// Phương thức chứa đoạn này phải xử lý SSLPeerUnverifiedException.
SSLSession session = engine.getSession();

String protocol = session.getProtocol();
String cipher = session.getCipherSuite();
String applicationProtocol = engine.getApplicationProtocol();

java.security.cert.Certificate[] peerCertificates =
        session.getPeerCertificates();
java.security.Principal peer = session.getPeerPrincipal();
```

Dùng `getPeerCertificates()` trả `java.security.cert.Certificate[]`; không dùng API chứng thư cũ đã bị đánh dấu loại bỏ. `getPeerPrincipal()` và việc đọc chứng thư có thể báo `SSLPeerUnverifiedException` khi không có danh tính đối tác được xác thực. Điều này đặc biệt cần xét ở máy chủ không yêu cầu chứng thư máy khách.

Không lấy `session.getPeerHost()` làm bằng chứng chứng thư đã khớp tên: đó không phải phép đối chiếu danh tính. Không lấy riêng `session.isValid()` làm kiểm tra quyền hoặc bằng chứng kết nối hiện đang mở. Các thuộc tính và giới hạn của phiên nằm trong [SSLSession API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLSession.html).

Thông tin phiên hữu ích cho quan sát và kiểm tra chính sách sau thương lượng. Nếu ứng dụng yêu cầu ALPN cụ thể, phải kiểm tra giá trị thực tế; danh sách đã cấu hình trước bắt tay không phải kết quả được chọn.

## 10. Kiểm thử để biết chính sách thật sự được thực thi

Ngoài ca thành công, cần kiểm thử các ca từ chối trong một môi trường kiểm soát:

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| Đúng tên SAN và chuỗi được tin | Bắt tay thành công nếu các điều kiện khác phù hợp |
| Chuỗi được tin nhưng sai tên dịch vụ | Máy khách từ chối |
| Đúng tên nhưng CA không được tin | Máy khách từ chối |
| Chứng thư đầu cuối hết hạn | Bị từ chối theo kiểm tra chứng thư |
| Không có giao thức/bộ mã phù hợp | Bắt tay thất bại |
| Máy chủ bắt buộc mTLS, máy khách không xuất trình danh tính phù hợp | Bắt tay thất bại |
| Chứng thư máy khách được tin nhưng thiếu quyền nghiệp vụ | TLS có thể thành công; thao tác nghiệp vụ bị từ chối |

Chuỗi lỗi cụ thể phụ thuộc nhà cung cấp và thời điểm xảy ra; không kiểm thử bằng cách gắn cứng toàn bộ thông báo ngoại lệ.

Khi gặp lỗi xây dựng đường dẫn, kiểm tra chuỗi trung gian và nguồn tin cậy. Khi sai tên, kiểm tra danh tính tham chiếu, SAN và cấu hình SNI. Khi không có thuật toán tương thích, kiểm tra giao thức, bộ mã, loại khóa và chính sách JDK. Không “sửa” cả ba loại lỗi bằng một `TrustManager` chấp nhận tất cả.

Các tính năng và trách nhiệm cấu hình JSSE được tổng hợp trong [hướng dẫn JSSE hiện hành](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html).

## 11. Tự kiểm tra

1. Vì sao CA đáng tin chưa đủ? **Còn phải đối chiếu đúng danh tính dịch vụ và thỏa chính sách chứng thư.**
2. SNI có xác minh máy chủ không? **Không; nó giúp máy chủ chọn dịch vụ/chứng thư.**
3. Truyền host cho `createSSLEngine()` có bật kiểm tra HTTPS đầy đủ không? **Không; cần cấu hình endpoint identification và nguồn tin cậy phù hợp.**
4. `KeyManager` và `TrustManager` khác nhau thế nào? **Một bên chọn danh tính ta xuất trình, một bên đánh giá đối tác.**
5. Vì sao mTLS không thay thế phân quyền? **Chứng thư xác thực danh tính theo chính sách TLS; quyền thao tác do ứng dụng quyết định.**
6. Chương trình cấu hình chạy thành công có chứng minh bắt tay an toàn không? **Không; cần kiểm chứng kết nối thật và các ca từ chối.**
