# TLS version

## 1. Mục tiêu và phạm vi

TLS version là phiên bản giao thức Transport Layer Security mà hai đầu kết nối sử dụng để thiết lập kênh truyền được bảo vệ. Với một dịch vụ HTTP, có HTTPS chưa đủ để kết luận chính sách phiên bản TLS đã được đáp ứng: hệ thống có thể vẫn chấp nhận phiên bản bị cấm, chỉ bật phiên bản mong muốn ở một số listener hoặc kết thúc TLS ở proxy rồi dùng một kết nối khác không đạt yêu cầu ở phía sau.

Trong thiết kế yêu cầu bảo mật, cần chuyển mục tiêu “bảo vệ dữ liệu trên đường truyền” thành một hợp đồng có thể kiểm chứng. Hợp đồng đó phải xác định từng kết nối, tập phiên bản được phép, cách xử lý khi không có phiên bản chung và bằng chứng về phiên bản thực tế đã thương lượng.

Sau bài này, người học có thể:

- Phân biệt phiên bản được hỗ trợ, được bật và thực tế được thương lượng.
- Viết chính sách phiên bản TLS theo từng listener và từng kết nối đi ra.
- Xác định đúng phạm vi khi TLS kết thúc ở CDN, gateway, load balancer hoặc service proxy.
- Đặc tả hành vi từ chối, ngoại lệ tương thích và giới hạn của việc fallback.
- Thiết kế bằng chứng nghiệm thu cho cả trường hợp được phép và phiên bản bị cấm.

Bài tập trung vào chính sách phiên bản và cách biến nó thành yêu cầu hệ thống. Cipher suite, xác thực chứng chỉ, quản lý khóa, xác thực client và vòng đời thư viện là các điều kiện liên quan nhưng cần yêu cầu riêng; chỉ chọn phiên bản TLS không hoàn tất mọi mục tiêu an toàn truyền thông.

## 2. Những khái niệm phải tách biệt

### 2.1. Hỗ trợ không có nghĩa là đang sử dụng

Một thư viện có thể hỗ trợ nhiều phiên bản nhưng cấu hình kết nối chỉ bật một phần trong số đó. Trong những phiên bản được bật ở cả hai phía, handshake mới xác định phiên bản được dùng cho kết nối cụ thể.

| Khái niệm | Câu hỏi cần trả lời | Ví dụ bằng chứng |
| --- | --- | --- |
| Supported | Thành phần có khả năng thực hiện phiên bản nào? | Khả năng của TLS provider hoặc sản phẩm |
| Enabled | Chính sách hiện tại cho phép đề xuất hoặc chấp nhận phiên bản nào? | Cấu hình có hiệu lực của listener hoặc client |
| Negotiated | Kết nối cụ thể đã sử dụng phiên bản nào? | Kết quả handshake hoặc thông tin phiên ở điểm kết thúc TLS |

Một ảnh chụp cho thấy runtime hỗ trợ TLS 1.3 không chứng minh listener đã bật nó. Một lần kết nối thành công bằng TLS 1.3 cũng chưa chứng minh TLS 1.0 đã bị tắt.

### 2.2. Phiên bản TLS khác phiên bản HTTP

HTTP và TLS là các lớp khác nhau. Một con số HTTP/1.1 hoặc HTTP/2 trong công cụ không phải là phiên bản TLS của kết nối. Kết quả kiểm chứng cần ghi đúng thông tin của từng lớp thay vì suy ra lớp bảo vệ từ tên giao thức ứng dụng.

Nếu hệ thống có nhiều phương thức vận chuyển HTTP, cần kiểm kê cách áp dụng TLS cho từng loại. Không nên dùng một phép thử trên một listener để suy ra mọi đường truy cập đều dùng cùng cơ chế.

### 2.3. Chọn phiên bản không thay cho xác thực peer

Một client chấp nhận TLS 1.3 nhưng bỏ kiểm tra chuỗi chứng chỉ hoặc tên máy chủ vẫn chưa đáp ứng mục tiêu kết nối đúng dịch vụ. Ngược lại, chứng chỉ hợp lệ không chứng minh listener đã loại bỏ mọi phiên bản bị cấm.

Yêu cầu cần giữ các kiểm tra này độc lập: phiên bản, cấu hình mật mã, nguồn tin cậy chứng chỉ và định danh peer đều phải đạt chính sách tương ứng.

### 2.4. Từ chối TLS xảy ra trước HTTP

Khi hai phía không có phiên bản TLS chung được phép, kết nối không được hoàn tất để trao đổi dữ liệu ứng dụng được bảo vệ. Không nên viết tiêu chí bắt buộc server trả một HTTP status cụ thể cho mọi client dùng phiên bản TLS bị cấm, vì request HTTP có thể chưa được gửi hoặc xử lý.

Một trang lỗi đẹp ở tầng HTTP không phải bằng chứng thay thế cho việc handshake bị từ chối đúng.

## 3. Đặt chính sách dựa trên chuẩn và phạm vi sản phẩm

### 3.1. Không dùng các phiên bản đã bị loại bỏ

TLS 1.0 và TLS 1.1 đã bị IETF loại bỏ khỏi sử dụng theo RFC 8996. Chính sách cho dịch vụ HTTP không nên giữ chúng chỉ vì một client cũ vẫn thử kết nối. [RFC 8996](https://www.rfc-editor.org/rfc/rfc8996.html)

Các phiên bản SSL cũ cũng không thuộc tập cho phép của chính sách mẫu trong bài. Khuyến nghị TLS của RFC 9325 yêu cầu không thương lượng SSL 2.0 và SSL 3.0. [RFC 9325](https://www.rfc-editor.org/rfc/rfc9325.html)

### 3.2. Theo dõi tài liệu đã được cập nhật

RFC 9846, công bố tháng 7 năm 2026, là đặc tả TLS 1.3 thay thế RFC 8446. Khi ghi căn cứ thiết kế, cần kiểm tra trạng thái tài liệu thay vì mặc định một số RFC quen thuộc vẫn là bản hiện hành. [RFC 9846](https://www.rfc-editor.org/info/rfc9846/)

RFC 9852 cập nhật RFC 9325 về yêu cầu đối với giao thức mới dùng TLS: phải hỗ trợ và yêu cầu TLS 1.3; hỗ trợ TLS 1.2 có thể được giữ theo phạm vi tài liệu. Đây là yêu cầu cho giao thức mới, không phải căn cứ để đồng nhất mọi endpoint mới của một sản phẩm với một giao thức mới được chuẩn hóa. [RFC 9852](https://www.rfc-editor.org/info/rfc9852/)

### 3.3. Chuyển căn cứ thành profile cụ thể

Một hệ thống có thể chọn các profile triển khai sau, tùy tập client và rủi ro đã được đánh giá:

| Profile minh họa | Tập phiên bản được phép | Điều kiện áp dụng |
| --- | --- | --- |
| Kết nối do hai đầu cùng kiểm soát | TLS 1.3 | Các client và server thuộc phạm vi đã xác nhận tương thích |
| Dịch vụ hiện hữu cần tương thích có kiểm soát | TLS 1.3 và TLS 1.2 | Có căn cứ cần TLS 1.2 và cấu hình đầy đủ cho phiên bản này |
| Kết nối đối tác trong giai đoạn chuyển đổi | Tập được phê duyệt riêng cho kết nối đó | Có chủ sở hữu, phạm vi, thời hạn và kế hoạch chuyển đổi |

Đây là các lựa chọn chính sách minh họa, không phải tuyên bố rằng mọi hệ thống đều phải bật cùng một tập phiên bản. Không tự mở rộng tập cho phép bằng một lựa chọn như “mọi phiên bản mà runtime hỗ trợ”.

Nếu giữ TLS 1.2, không nên hiểu rằng chỉ cần bật con số phiên bản là đủ. Các lựa chọn trao đổi khóa và mật mã vẫn cần đáp ứng chính sách cập nhật; chẳng hạn RFC 10015 thay đổi yêu cầu đối với những cơ chế trao đổi khóa cũ trong TLS 1.2. [RFC 10015](https://www.rfc-editor.org/info/rfc10015/)

### 3.4. Phiên bản tài liệu không phải quyền mở rộng cấu hình

Việc xuất hiện tài liệu chuẩn mới không có nghĩa runtime đang hỗ trợ đúng mọi thay đổi hoặc sản phẩm tự được phép thêm phiên bản. Cần đánh giá khả năng triển khai, các ràng buộc tương thích và kết quả kiểm chứng.

Tương tự, việc một RFC bị thay thế không tự biến thành một quyết định chặn toàn bộ hệ thống đang triển khai giao thức liên quan. Căn cứ chuẩn phải được đọc cùng nội dung cập nhật và chuyển thành profile áp dụng rõ ràng.

## 4. Kiểm kê đúng từng đoạn kết nối

### 4.1. TLS kết thúc ở đâu?

Một đường đi có thể gồm:

```text
Trình duyệt
    ── TLS A ──> CDN hoặc gateway
    ── TLS B ──> load balancer nội bộ
    ── TLS C ──> ứng dụng Java

Ứng dụng Java
    ── TLS D ──> dịch vụ đối tác
```

Các nhãn A, B, C và D chỉ những kết nối độc lập, không phải một phiên TLS kéo dài qua mọi thành phần. Phiên bản trên A không chứng minh phiên bản trên B hoặc C.

Nếu một đoạn được thiết kế không dùng TLS, cần ghi rõ đoạn đó trong mô hình đe dọa và quyết định bảo vệ truyền thông tương ứng. Không gọi toàn bộ đường đi là đã mã hóa đầu cuối chỉ vì phía người dùng nhìn thấy HTTPS.

### 4.2. Cả inbound và outbound đều có chính sách

Inbound là các listener mà hệ thống chấp nhận kết nối tới. Outbound là các client của hệ thống khi gọi dịch vụ khác, callback, webhook hoặc API đối tác.

Một tổ chức có thể khóa cấu hình TLS ở gateway rất tốt nhưng vẫn có một HTTP client dùng cấu hình riêng, một thư viện kết nối cũ hoặc một job gọi đối tác theo profile không được phê duyệt. Các đường đi này phải nằm trong phạm vi nếu chúng mang dữ liệu thuộc mục tiêu bảo vệ.

### 4.3. Danh mục có thể dùng để giao trách nhiệm

| Trường | Ý nghĩa |
| --- | --- |
| Connection ID | Định danh đoạn kết nối cần kiểm chứng |
| Client và TLS terminator | Hai đầu thực sự thực hiện handshake |
| Hostname, port, SNI hoặc listener | Cách chọn đúng cấu hình cần kiểm tra |
| Dữ liệu đi qua | Căn cứ đánh giá rủi ro và profile |
| Tập phiên bản cho phép | Chính sách cụ thể cho đoạn kết nối |
| Cấu hình do ai sở hữu | Nhóm chịu trách nhiệm thực thi |
| Bằng chứng | Cấu hình có hiệu lực và kết quả handshake |

Các hostname khác nhau trên cùng IP có thể đi tới cấu hình khác. Một đường truy cập trực tiếp vào backend cũng có thể bỏ qua gateway dự kiến. Vì vậy, phải kiểm tra đúng listener và các đường đi thực sự có thể tiếp cận.

### 4.4. Header không chứng minh một phiên TLS khác

Một header báo giao thức hoặc phiên bản client do proxy chuyển tiếp chỉ có giá trị trong mô hình tin cậy được xác định. Ứng dụng không thể coi header caller tự gửi là bằng chứng handshake đã đạt chính sách.

Ngay cả một header hợp lệ từ proxy cũng mô tả thông tin mà proxy báo về một đoạn kết nối. Nó không tự chứng minh đoạn proxy tới backend đang dùng cùng phiên bản.

## 5. Viết yêu cầu có thể nghiệm thu

### 5.1. Một yêu cầu còn thiếu

```text
Hệ thống phải dùng TLS mới và an toàn.
```

Câu này không xác định tập phiên bản, phạm vi listener, đầu ra khi client không tương thích, chủ sở hữu cấu hình hay bằng chứng cần thu thập. Từ “mới” cũng không tạo được một tiêu chí ổn định khi runtime hoặc tài liệu chuẩn thay đổi.

### 5.2. Một đặc tả cụ thể cho profile mẫu

```text
REQ-TLS-VER-01 — Chính sách phiên bản của listener công khai

Đối với listener HTTPS của api.example.test:443 trong profile STANDARD,
hệ thống chỉ được hoàn tất handshake sử dụng TLS 1.3.

Client không đề xuất được phiên bản được phép phải không thiết lập được
kênh dữ liệu ứng dụng trên listener đó. Hệ thống không được chuyển sang
phiên bản ngoài tập cho phép hoặc kết nối plaintext để tiếp tục request.

Yêu cầu áp dụng cho mọi instance và đường phục vụ của listener, bao gồm
cấu hình mặc định và cấu hình được chọn bằng SNI trong phạm vi đã kiểm kê.
```

Tên miền trong ví dụ chỉ là địa chỉ minh họa. Tập chỉ có TLS 1.3 là chính sách của profile mẫu; nếu sản phẩm phê duyệt một profile tương thích khác, phải ghi rõ tập phiên bản của profile đó.

### 5.3. Các yêu cầu bổ sung

| Mã | Nội dung yêu cầu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| REQ-TLS-VER-02 | Mỗi kết nối đi ra phải áp dụng một profile được phê duyệt; client không được tự bật lại phiên bản ngoài profile khi gặp lỗi | Cấu hình client và tình huống peer không tương thích |
| REQ-TLS-VER-03 | Cấu hình các đoạn gateway/backend phải được xác định độc lập và không suy từ kết nối phía trước | Danh mục kết nối và kết quả handshake từng đoạn |
| REQ-TLS-VER-04 | Mọi listener thuộc phạm vi phải từ chối các phiên bản bị cấm trong policy tương ứng | Các phép thử âm tính có nguồn thử hợp lệ |
| REQ-TLS-VER-05 | Runtime không đáp ứng profile phải tạo lỗi cấu hình hoặc lỗi kết nối được xử lý rõ, không âm thầm dùng profile yếu hơn | Kết quả thiếu hỗ trợ hoặc bị ràng buộc bởi chính sách runtime |
| REQ-TLS-VER-06 | Tính hợp lệ của chứng chỉ và định danh peer vẫn phải được kiểm tra theo yêu cầu riêng khi thay đổi phiên bản | Kết quả kiểm tra chứng chỉ và hostname |
| REQ-TLS-VER-07 | Ngoại lệ tương thích phải có phạm vi, chủ sở hữu, thời hạn và kế hoạch kết thúc | Hồ sơ ngoại lệ và quan sát các kết nối thuộc ngoại lệ |
| REQ-TLS-VER-08 | Thay đổi cấu hình không được làm xuất hiện listener hoặc client ngoài tập phiên bản đã phê duyệt | So sánh cấu hình có hiệu lực và bằng chứng sau triển khai |

Tiêu chí “mọi kết nối đều dùng TLS 1.3” chỉ phù hợp khi profile thực sự yêu cầu điều đó. Với profile cho phép cả TLS 1.2 và TLS 1.3, cần nghiệm thu từng phiên bản được phép và các phiên bản bị cấm, thay vì đánh dấu mọi phiên TLS 1.2 là lỗi ngoài hợp đồng.

## 6. Thương lượng, fallback và những thông tin dễ đọc sai

### 6.1. Không có phiên bản chung thì dừng

Nếu client chỉ cho phép TLS 1.3 còn peer chỉ hỗ trợ tập khác, handshake phải thất bại theo profile đó. Hệ thống có thể báo lỗi khả dụng hoặc lỗi tích hợp theo hợp đồng, nhưng không được tự chuyển sang kết nối không đáp ứng yêu cầu để che lỗi.

Một ngoại lệ tương thích phải được phê duyệt trước và gắn với kết nối cụ thể. Việc “thử mọi phiên bản cho tới khi kết nối được” không phải một chính sách phiên bản có kiểm soát.

### 6.2. Không nhầm trường legacy với phiên bản được chọn

Trong TLS 1.3, trường `legacy_version` có thể mang giá trị tương ứng TLS 1.2; việc thương lượng phiên bản dùng extension `supported_versions`. Do đó, chỉ đọc một trường legacy từ bản tin không đủ để kết luận phiên TLS 1.3 thực tế là TLS 1.2. [RFC 9846, mục 4.2–4.3](https://www.rfc-editor.org/info/rfc9846/)

Bằng chứng nên lấy từ kết quả handshake hoặc công cụ hiểu đầy đủ phiên bản đang kiểm tra. Nếu phân tích gói tin, phải biết công cụ đang hiển thị phiên bản record, trường tương thích hay kết quả thương lượng.

### 6.3. Không coi mọi lỗi handshake là lỗi phiên bản

Handshake có thể thất bại vì phiên bản không khớp, cấu hình mật mã không tương thích, chứng chỉ không được tin, tên máy chủ sai hoặc một yêu cầu xác thực khác chưa được đáp ứng.

Khi kiểm chứng phiên bản, cần kiểm soát các điều kiện khác để kết quả có ý nghĩa. Một client không có khả năng gửi handshake phiên bản bị cấm không thể cung cấp bằng chứng rằng server đã từ chối phiên bản đó.

### 6.4. TLS 1.3 không tự cho phép mọi tối ưu

Dữ liệu 0-RTT có đặc tính chống replay yếu hơn luồng thông thường và cần quyết định riêng của ứng dụng. Không nên coi “đã chọn TLS 1.3” là đủ để bật early data cho mọi thao tác có tác động nghiệp vụ. [RFC 9846, mục 8](https://www.rfc-editor.org/info/rfc9846/)

Trong một profile không cần tính năng này, có thể quy định không bật 0-RTT. Nếu muốn sử dụng, cần đặc tả các thông điệp được phép, cách xử lý lặp và bằng chứng cho chính tính năng đó; đây là yêu cầu bổ sung, không phải điều kiện suy ra từ số phiên bản.

## 7. Ví dụ Java: giới hạn và quan sát một kết nối TLS

### 7.1. Cấu hình trên đúng đối tượng thực hiện handshake

JSSE cung cấp `SSLParameters` để đặt các phiên bản được phép cho kết nối; các tham số phải được áp dụng vào đối tượng thực sự sử dụng chúng. Việc tạo một bộ tham số nhưng không gắn vào socket hoặc client không thay đổi cấu hình của kết nối. [Java SE 21: SSLParameters](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLParameters.html)

Ví dụ sau minh họa một kết nối kiểm chứng chỉ cho phép TLS 1.3, với hostname lấy từ danh mục dịch vụ đã được xác định. Nó mở kênh TCP có timeout, giữ kiểm tra định danh HTTPS và không gửi request HTTP:

```java
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.List;
import javax.net.ssl.SNIHostName;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;

public final class TlsVersionProbe {

    private TlsVersionProbe() {
    }

    public static String verifyTls13(String host, int port)
            throws IOException, NoSuchAlgorithmException {

        SSLContext context = SSLContext.getDefault();
        SSLSocketFactory factory = context.getSocketFactory();

        try (Socket tcp = new Socket()) {
            tcp.connect(new InetSocketAddress(host, port), 5_000);
            tcp.setSoTimeout(5_000);

            try (SSLSocket tls = (SSLSocket) factory.createSocket(
                    tcp, host, port, true)) {

                boolean supported = Arrays.asList(tls.getSupportedProtocols())
                        .contains("TLSv1.3");

                if (!supported) {
                    throw new IOException("Runtime does not support TLSv1.3");
                }

                SSLParameters parameters = tls.getSSLParameters();
                parameters.setProtocols(new String[] {"TLSv1.3"});
                parameters.setEndpointIdentificationAlgorithm("HTTPS");
                parameters.setServerNames(List.of(new SNIHostName(host)));
                tls.setSSLParameters(parameters);
                tls.setSoTimeout(5_000);

                tls.startHandshake();

                String negotiated = tls.getSession().getProtocol();
                if (!"TLSv1.3".equals(negotiated)) {
                    throw new IOException("Unexpected negotiated protocol");
                }

                return negotiated;
            }
        }
    }
}
```

`startHandshake()` chủ động thực hiện handshake; kết quả của `SSLSession.getProtocol()` cho biết tên phiên bản đã được sử dụng. Đây là thông tin khác với danh sách khả năng mà `getSupportedProtocols()` trả về trước đó. [Java SE 21: SSLSocket](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLSocket.html), [Java SE 21: SSLSession](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLSession.html)

### 7.2. Những giả định của ví dụ

Host trong ví dụ là DNS hostname phù hợp để dùng SNI, không phải một địa chỉ tùy ý nhận từ caller. Nguồn tin cậy chứng chỉ của runtime phải được cấu hình cho môi trường đích. Nếu dịch vụ yêu cầu chứng chỉ client, ví dụ cần ngữ cảnh có key material phù hợp với yêu cầu đó.

Code không cài trust manager chấp nhận mọi chứng chỉ và không tắt kiểm tra hostname để làm cho phép thử thành công. Nếu xác thực peer thất bại, cần xử lý đúng nguyên nhân thay vì giảm yêu cầu.

Kiểm tra `supported` chỉ phát hiện một trường hợp thiếu khả năng. Một phiên bản có tên trong danh sách hỗ trợ vẫn có thể không được sử dụng do các ràng buộc runtime hoặc cấu hình mật mã; kết quả handshake mới xác nhận kết nối cụ thể.

### 7.3. Giới hạn bằng chứng của ví dụ

Phép thử chỉ cho biết một hostname, port và đường kết nối đã đạt TLS 1.3 trong điều kiện thực hiện. Nó chưa chứng minh server không chấp nhận TLS 1.2, chưa kiểm kê mọi instance và chưa quan sát các đoạn phía sau một TLS terminator.

Ví dụ cũng không cấu hình server hoặc HTTP client nghiệp vụ của sản phẩm. Nếu ứng dụng dùng connection pool hoặc thư viện HTTP riêng, profile phải được áp dụng ở cấu hình của thành phần đó. Không thể coi một socket kiểm chứng đạt là bằng chứng mọi request nghiệp vụ đang đi qua đúng cấu hình.

## 8. Thiết kế tiêu chí nghiệm thu

### 8.1. Kiểm tra cả tập cho phép và tập bị cấm

Đối với profile chỉ cho TLS 1.3, một ma trận tối thiểu có thể là:

| Client thử nghiệm | Kỳ vọng đối với listener | Bằng chứng |
| --- | --- | --- |
| Chỉ đề xuất TLS 1.3 và các điều kiện khác hợp lệ | Handshake thành công bằng TLS 1.3 | Kết quả thương lượng ở client hoặc terminator |
| Chỉ đề xuất TLS 1.2 | Không hoàn tất handshake | Kết quả kết nối và bằng chứng request không tới xử lý ứng dụng |
| Chỉ đề xuất TLS 1.1 hoặc TLS 1.0 | Không hoàn tất handshake | Nguồn thử có khả năng gửi đề xuất và kết quả từ đích |
| Đề xuất nhiều phiên bản, có TLS 1.3 | Chỉ hoàn tất bằng phiên bản thuộc profile | Phiên bản thực tế được chọn |
| Không có phiên bản chung | Dừng kết nối, không fallback ra ngoài policy | Quan sát cả lần thử đầu và cơ chế retry nếu có |

Ma trận này xuất phát từ profile minh họa, không phải yêu cầu cho mọi dịch vụ. Với profile tương thích cho phép TLS 1.2, cần bổ sung trường hợp TLS 1.2 thành công trong các điều kiện được phê duyệt và vẫn giữ kiểm tra các phiên bản bị cấm.

### 8.2. Xác nhận nguồn thử thực sự đề xuất được phiên bản

Một TLS client hiện đại có thể đã vô hiệu hóa phiên bản cũ ở mức runtime. Nếu nó thất bại trước khi gửi một handshake thích hợp, kết quả đó chưa chứng minh đích đã chặn phiên bản cũ.

Hồ sơ kiểm chứng cần phân biệt lỗi cục bộ của công cụ, lỗi mạng và từ chối của TLS endpoint. Có thể cần một công cụ kiểm chứng chuyên biệt trong môi trường được phép, với khả năng đề xuất đúng phiên bản cần kiểm tra.

Không thay đổi chính sách production của ứng dụng để phục vụ việc thử các phiên bản cũ. Khả năng của nguồn thử và cấu hình của đích là hai đối tượng độc lập.

### 8.3. Đúng hostname, SNI và địa chỉ phục vụ

Kết nối trực tiếp tới một IP với SNI khác hoặc không có SNI có thể chọn listener hoặc chứng chỉ mặc định khác. Bằng chứng phải ghi rõ hostname, port, SNI, đường đi và môi trường kiểm tra.

Nếu có IPv4, IPv6, nhiều vùng, nhiều load balancer hoặc đường truy cập nội bộ khác nhau, cần xác định đường nào thuộc phạm vi. Không suy ra tính đồng nhất toàn hệ thống từ một kết quả ngẫu nhiên qua DNS.

### 8.4. Kiểm tra ở từng TLS terminator

```text
Given:
  Người dùng kết nối tới gateway bằng TLS.
  Gateway tạo kết nối riêng tới ứng dụng Java.

When:
  Thu thập phiên bản của kết nối người dùng/gateway và gateway/ứng dụng.

Then:
  Mỗi phiên bản được đối chiếu với profile của chính đoạn kết nối đó.
  Kết quả đạt ở đoạn đầu không thay cho kết quả của đoạn sau.
  Không có đường truy cập ngoài danh mục bỏ qua chính sách dự kiến.
```

Nếu TLS được terminate ở sidecar hoặc một proxy khác, bằng chứng phải thu từ đúng thành phần đó. Ứng dụng Java không thể cung cấp thông tin phiên mà nó không trực tiếp thiết lập hoặc quan sát qua cơ chế tin cậy đã thiết kế.

### 8.5. Chính sách sau thay đổi và trên các kết nối tồn tại

Khi tắt một phiên bản, yêu cầu cần nói rõ thời điểm có hiệu lực đối với handshake mới. Cần xác định riêng cách xử lý connection pool và các kết nối đang tồn tại nếu chúng tiếp tục được dùng trong thời gian chuyển đổi.

Một profile có thể yêu cầu xoay vòng các kết nối cũ hoặc có thời gian drain cụ thể. Chỉ cập nhật file cấu hình chưa chứng minh các phiên đang hoạt động đã thay đổi, và một phiên TLS đã thiết lập không tự biến thành phiên bản khác khi sửa cấu hình.

Luồng tái sử dụng phiên hoặc ticket cũng phải được kiểm chứng theo yêu cầu có hiệu lực sau thay đổi. Không để một cơ chế tối ưu tiếp tục sử dụng điều kiện ngoài policy mà không có quyết định rõ ràng.

## 9. Tương thích, ngoại lệ và kế hoạch chuyển đổi

### 9.1. Kiểm kê trước khi thu hẹp tập phiên bản

Dữ liệu vận hành về phiên bản đã thương lượng giúp xác định client hoặc kết nối còn phụ thuộc profile cũ. Cần thu từ đúng terminator và trong khoảng quan sát đủ đại diện cho các tác vụ ít chạy, không chỉ các request thường xuyên.

Không có lưu lượng trong một giờ không chứng minh một job cuối tháng đã tương thích. Cũng không nên mặc định mọi client có cùng runtime hoặc được cập nhật cùng thời điểm.

### 9.2. Ngoại lệ phải có ranh giới

Một hồ sơ ngoại lệ cho đối tác hiện hữu có thể gồm:

```text
Connection ID: outbound-partner-report.
Chủ sở hữu: nhóm tích hợp đối tác.
Phạm vi: đúng hostname và port được phê duyệt của đối tác.
Profile tạm thời: tập phiên bản được phê duyệt cho kết nối này.
Căn cứ: kết quả xác nhận khả năng của peer và nhu cầu nghiệp vụ.
Thời hạn: một ngày cụ thể đã được phê duyệt.
Kế hoạch: nâng cấp peer, kiểm chứng profile đích và đóng ngoại lệ.
Quan sát: số kết nối dùng profile tạm và lỗi handshake liên quan.
```

Không thay một ngoại lệ hẹp bằng việc mở mọi phiên bản trên toàn bộ dịch vụ. Nếu dữ liệu hoặc rủi ro không cho phép duy trì tương thích, cần chọn một cách tích hợp đáp ứng yêu cầu hoặc dừng kết nối; nhu cầu khả dụng không tự tạo quyền giảm bảo vệ.

### 9.3. Triển khai và rollback có giới hạn

Có thể triển khai cấu hình theo từng nhóm endpoint để phát hiện lỗi tương thích, với điều kiện mỗi bước vẫn đáp ứng chính sách đã phê duyệt cho nhóm đó. Theo dõi lỗi handshake cần tách được lỗi phiên bản khỏi lỗi chứng chỉ, mạng hoặc cấu hình khác.

Kế hoạch rollback phải chỉ rõ phạm vi cấu hình được phép khôi phục. Không dùng một rollback tổng quát có thể bật lại phiên bản bị cấm hoặc cơ chế bỏ xác thực peer chỉ để khôi phục tỷ lệ kết nối thành công.

Nếu một thay đổi chính sách làm ngừng tích hợp, cần có thông tin đủ để xử lý ở đúng peer hoặc đúng profile. Thông báo lỗi chung không nên che việc client đã tự fallback ngoài policy.

### 9.4. Kiểm soát cấu hình lệch

Một instance cũ, listener mặc định hoặc đường health/management riêng có thể giữ cấu hình khác. Cần xác định cách phát hiện và sửa cấu hình lệch trong phạm vi yêu cầu, đặc biệt sau scale hoặc phục hồi từ template cũ.

Artifact triển khai và cấu hình hạ tầng phải mang được profile đúng. Một thay đổi thủ công trên một máy không tạo bằng chứng rằng máy mới sẽ được sinh ra với cùng chính sách.

## 10. Quan sát và phân công trách nhiệm

### 10.1. Quan sát đúng dữ liệu cần thiết

Các chỉ số có thể gồm số phiên theo phiên bản đã thương lượng, số lỗi handshake theo nhóm nguyên nhân, listener và profile đang áp dụng. Mục tiêu là phát hiện phiên bản ngoài policy và theo dõi phụ thuộc tương thích.

Không cần ghi payload, khóa phiên hoặc secret để biết phiên bản TLS. Nếu thu log debug handshake để điều tra, phải kiểm soát phạm vi, lượng dữ liệu và quyền truy cập theo yêu cầu vận hành tương ứng.

Thông tin do proxy báo cần có nguồn gốc đáng tin. Một metric tổng hợp của gateway không thay cho kiểm chứng cấu hình outbound của ứng dụng.

### 10.2. Mỗi đoạn kết nối có một chủ sở hữu

| Thành phần | Trách nhiệm điển hình |
| --- | --- |
| Nhóm bảo mật và kiến trúc | Phê duyệt profile, căn cứ và ranh giới ngoại lệ |
| Nhóm hạ tầng biên | Cấu hình listener công khai và TLS terminator do họ sở hữu |
| Nhóm nền tảng nội bộ | Cấu hình TLS giữa proxy, load balancer và dịch vụ nội bộ |
| Nhóm ứng dụng Java | Áp dụng profile cho connector hoặc client TLS thuộc ứng dụng |
| Nhóm tích hợp | Xác nhận khả năng peer và quản lý kế hoạch chuyển đổi đối tác |
| Nhóm kiểm chứng | Thu bằng chứng cho tập cho phép, tập bị cấm và đường đi thực tế |

Phân công theo ranh giới thực hiện giúp tránh tình trạng đội ứng dụng cho rằng gateway đã bảo vệ mọi kết nối, còn đội hạ tầng cho rằng cấu hình client đi ra không thuộc phạm vi cần kiểm tra.

## 11. Những kết luận cần tránh

### 11.1. “Có HTTPS nên đã đạt yêu cầu TLS version”

HTTPS chứng minh một cách truy cập có sử dụng TLS khi kết nối được thiết lập đúng, nhưng không chỉ ra tập phiên bản server còn chấp nhận hoặc mọi đoạn nội bộ. Cần bằng chứng theo profile và danh mục kết nối.

### 11.2. “Thêm TLS 1.3 thì phiên bản cũ tự biến mất”

Bật thêm một phiên bản không đồng nghĩa tắt các phiên bản khác. Danh sách được bật và kết quả thử âm tính mới trả lời phần yêu cầu loại bỏ.

### 11.3. “Một HTTP header có thể từ chối TLS cũ cho request hiện tại”

Header của response ứng dụng chỉ có thể tới client sau khi các lớp trước đã xử lý đủ để trao đổi HTTP. Nó không thay cấu hình phiên bản tại điểm thực hiện handshake. Các chính sách trình duyệt ở lớp HTTP có mục tiêu khác và không tự cấu hình mọi TLS listener.

### 11.4. “TLS 1.3 làm mọi cấu hình khác đều an toàn”

Phiên bản là một chiều của profile. Chứng chỉ sai peer, trust store quá rộng, client authentication thiếu hoặc một tính năng được bật sai mục đích vẫn cần được đánh giá riêng.

### 11.5. “Một lần quét đạt là bằng chứng lâu dài”

Kết quả kiểm chứng gắn với thời điểm, đường đi và cấu hình có hiệu lực. Thay proxy, runtime, TLS provider, template triển khai hoặc thư viện client đều có thể làm thay đổi hành vi.

Yêu cầu cần xác định những loại thay đổi nào buộc phải thu lại bằng chứng, thay vì chỉ lưu một báo cáo ban đầu rồi coi chính sách luôn đúng.

## 12. Hồ sơ yêu cầu mẫu

Một hồ sơ ngắn cho một listener do hệ thống kiểm soát có thể viết:

```text
Connection ID: public-api-primary.
Hai đầu: client được hỗ trợ và gateway công khai.
Đích: hostname, port và tập listener đã kiểm kê.

Mục tiêu:
  Chỉ cho thiết lập kênh ứng dụng bằng phiên bản được profile phê duyệt.

Profile STANDARD minh họa:
  Tập cho phép là TLS 1.3.
  Không fallback sang phiên bản khác hoặc plaintext khi kết nối thất bại.
  Kiểm tra chứng chỉ và định danh peer vẫn có hiệu lực theo yêu cầu riêng.

Phạm vi:
  Mọi instance và đường phục vụ thuộc listener.
  Các đoạn gateway/backend và kết nối outbound có hồ sơ độc lập.

Nghiệm thu:
  Client TLS 1.3 phù hợp hoàn tất handshake bằng đúng phiên bản.
  Client chỉ đề xuất phiên bản ngoài profile không thiết lập được kênh.
  Nguồn thử có khả năng thực hiện phép thử và đúng hostname/SNI.
  Quan sát cả cấu hình có hiệu lực và kết quả handshake sau triển khai.

Vòng đời:
  Ngoại lệ có chủ sở hữu và thời hạn.
  Thay đổi runtime, terminator hoặc profile phải kiểm chứng lại phạm vi bị ảnh hưởng.
```

Yêu cầu TLS version đạt mục tiêu khi mỗi đoạn kết nối chỉ thương lượng trong tập được phê duyệt và không tự giảm bảo vệ để tiếp tục truyền dữ liệu. Bằng chứng cần nối được chính sách, cấu hình có hiệu lực và kết quả handshake của đúng hai đầu kết nối, thay vì chỉ dựa vào nhãn HTTPS hoặc khả năng của thư viện.
