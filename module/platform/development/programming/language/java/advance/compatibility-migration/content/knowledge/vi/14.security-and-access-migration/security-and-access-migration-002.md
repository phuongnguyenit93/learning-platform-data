# TLS, cipher suite và khả năng kết nối với hệ thống cũ

Khi chuyển ứng dụng sang phiên bản Java mới, có những trường hợp code vẫn biên dịch, dependency vẫn resolve và kết nối TCP vẫn thành công, nhưng request HTTPS, JDBC qua TLS hoặc kết nối tới một hệ thống đối tác bất ngờ thất bại. Lỗi thường xuất hiện trong quá trình TLS handshake: hai đầu không thống nhất được phiên bản giao thức hoặc cipher suite, chứng chỉ không còn đáp ứng chính sách bảo mật, thuật toán chữ ký bị hạn chế, hay tên máy chủ trên chứng chỉ không khớp với endpoint thực tế.

Đặc biệt, một hệ thống cũ có thể chỉ hỗ trợ TLS 1.0/1.1, cipher suite dùng thuật toán yếu, certificate chain dựa trên CA cũ, hoặc firmware không hiểu các extension được TLS client hiện đại gửi. Khi Java tăng mức bảo mật mặc định, những kết nối trước đây “vẫn chạy” có thể bị từ chối. Đây là biểu hiện mong đợi của tiến hóa chính sách an toàn, không nên xử lý bằng cách tắt xác thực chứng chỉ hoặc mở lại mọi thuật toán yếu.

Bài học thuộc chủ đề **Java Advance Compatibility Migration**, chương **Bảo mật và quyền truy cập**. Trọng tâm là cách TLS hoạt động trong hệ sinh thái Java, cách đánh giá mức tương thích với hệ thống legacy, nhận diện chính xác nguyên nhân handshake failure, thiết kế hướng chuyển đổi ít rủi ro và kiểm thử kết nối trên JDK đích.

## 1. Phân biệt các lớp tương thích khi kết nối TLS

Một kết nối thành công phải vượt qua nhiều lớp điều kiện:

~~~text
Ứng dụng Java
      |
      v
DNS / hostname / proxy
      |
      v
Kết nối TCP tới endpoint
      |
      v
TLS ClientHello
      |
      +--> Protocol version
      +--> Cipher suites
      +--> Supported groups / key exchange
      +--> Signature algorithms
      +--> SNI / ALPN / extensions
      |
      v
ServerHello và lựa chọn tham số
      |
      v
Certificate / authentication / key exchange
      |
      v
Trust chain + hostname verification
      |
      v
TLS connection established
      |
      v
HTTP / database protocol / application data
~~~

Không phải mọi bước có thứ tự giống nhau giữa TLS 1.2 và TLS 1.3; sơ đồ chỉ mô tả các nhóm điều kiện cần thỏa.

Một lỗi ở lớp network như Connection refused hoặc DNS timeout không nên tự động được phân loại là lỗi TLS. Ngược lại, việc telnet hoặc kiểm tra cổng TCP thành công chưa chứng minh TLS negotiation sẽ thành công.

Các chiều cần kiểm tra:

| Chiều tương thích | Câu hỏi |
|---|---|
| Protocol version | Client và server có cùng phiên bản TLS được cho phép không? |
| Cipher suite | Có bộ thuật toán được cả hai bên hỗ trợ và chính sách cho phép không? |
| Key exchange / group | Hai bên có nhóm khóa và tham số mật mã tương thích không? |
| Signature algorithms | Thuật toán ký chứng chỉ/handshake có được chấp nhận không? |
| Certificate chain | Client tin cậy chuỗi CA của server không? |
| Hostname identity | SAN của chứng chỉ có khớp hostname đã kết nối không? |
| Client certificate / mTLS | Server có yêu cầu và tin cậy chứng chỉ client không? |
| TLS extensions | SNI, ALPN hoặc extension khác có tương tác đúng không? |
| Security provider | JSSE provider, chính sách crypto và FIPS mode có đáp ứng không? |
| Application protocol | Sau TLS, HTTP, JDBC hoặc giao thức ứng dụng có hoạt động không? |

**TLS handshake thành công không chứng minh ứng dụng nghiệp vụ tương thích hoàn toàn.** Sau đó vẫn có thể xảy ra lỗi HTTP/2, authentication, serialization hoặc database protocol.

## 2. TLS là gì và tại sao việc nâng Java làm thay đổi kết nối?

Transport Layer Security (TLS) bảo vệ dữ liệu trên đường truyền bằng cách xác thực đối tác, thống nhất khóa phiên và mã hóa/integrity-check application data.

Trong Java, nhiều ứng dụng sử dụng TLS qua Java Secure Socket Extension (JSSE), bao gồm:

- javax.net.ssl.SSLContext;
- javax.net.ssl.SSLSocket và SSLServerSocket;
- javax.net.ssl.SSLEngine;
- javax.net.ssl.KeyManager và TrustManager;
- HttpsURLConnection;
- Java HttpClient;
- Các thư viện như Apache HttpClient, Netty, gRPC, JDBC drivers hoặc framework sử dụng provider riêng hay kết hợp JSSE.

Một dependency có thể dùng JSSE mặc định; dependency khác có thể cấu hình SSLContext riêng hoặc dùng native TLS engine như OpenSSL qua một adapter. Do đó, khi đánh giá migration phải xác định **thư viện thực sự thực hiện TLS handshake**, chứ không chỉ phiên bản JDK.

### 2.1. Java nâng chính sách bảo mật, không chỉ nâng API

Những thay đổi thường gặp khi nâng JDK hoặc cập nhật security patch:

- Bật TLS 1.3 theo môi trường hỗ trợ.
- Hạn chế hoặc vô hiệu hóa mặc định TLS 1.0/1.1.
- Loại bỏ cipher suite không an toàn khỏi danh sách mặc định.
- Chặn thuật toán, độ dài khóa hoặc chữ ký yếu.
- Cập nhật danh sách CA trong truststore mặc định.
- Thay đổi quy tắc chứng chỉ và hostname verification.
- Điều chỉnh extension, signature scheme và cách xử lý TLS handshake.

Một số thay đổi được đưa vào **security update của cùng dòng JDK**, không chỉ trong major upgrade. Bởi vậy, không nên kết luận môi trường tương thích dựa trên nhãn “Java 8” hoặc “Java 11” mà không biết update level, vendor, provider và cấu hình.

## 3. Các phiên bản TLS và mức độ phù hợp

| Giao thức | Đánh giá hiện đại | Hướng xử lý khi gặp hệ thống cũ |
|---|---|---|
| SSLv2, SSLv3 | Lỗi thời, không phù hợp để dùng | Không bật lại; thay endpoint/gateway |
| TLS 1.0 | Lỗi thời, thường bị vô hiệu hóa | Ưu tiên nâng server, chỉ cân nhắc ngoại lệ cô lập nếu chính sách cho phép |
| TLS 1.1 | Lỗi thời, thường bị vô hiệu hóa | Tương tự TLS 1.0 |
| TLS 1.2 | Giao thức được triển khai rộng, có thể bảo mật khi cấu hình tốt | Baseline thực tế cho nhiều hệ thống tương thích |
| TLS 1.3 | Phiên bản hiện đại, handshake/cipher suite được thiết kế lại | Ưu tiên khi cả hai bên hỗ trợ và đã kiểm thử |

JDK 11 đưa TLS 1.3 vào SunJSSE theo hướng hỗ trợ chính thức. Một số bản JDK 8 hoặc bản phân phối có backport có thể hỗ trợ TLS 1.3; vì vậy không nên suy luận chỉ theo major version. Hãy kiểm tra giao thức supported/enabled thực tế.

Trên nhiều JDK hiện đại, cấu hình mặc định thường ưu tiên TLS 1.3 và TLS 1.2, nhưng tập giao thức cụ thể có thể bị thay đổi bởi provider, thuộc tính bảo mật, tham số dòng lệnh và API của thư viện client.

### 3.1. Supported khác enabled

JSSE phân biệt:

- **Supported protocols:** giao thức implementation có khả năng hỗ trợ.
- **Enabled protocols:** giao thức được bật để một socket/engine cụ thể có thể đàm phán.
- **Permitted by security policy:** giao thức không bị chặn bởi các ràng buộc như jdk.tls.disabledAlgorithms.

Một giao thức xuất hiện trong getSupportedProtocols() không bảo đảm có thể kết nối, vì nó có thể bị vô hiệu hóa ở lớp security policy hoặc có những giới hạn khác.

### 3.2. Vì sao TLS 1.0/1.1 là vấn đề?

TLS 1.0 và 1.1 không đáp ứng kỳ vọng bảo mật hiện đại. Những client mới có thể từ chối đàm phán khi server chỉ hỗ trợ các giao thức này. Bật lại giao thức cũ có thể tạo bề mặt tấn công và vi phạm chính sách tuân thủ.

Với endpoint bên ngoài do đối tác sở hữu, cách xử lý tốt nhất là yêu cầu đối tác hỗ trợ TLS 1.2 trở lên với cipher suite và certificate hợp lệ. Nếu chưa thể nâng ngay, cần giải pháp chuyển tiếp được đánh giá rủi ro, có phân vùng mạng và thời hạn loại bỏ rõ ràng.

## 4. Cipher suite là gì?

Cipher suite xác định bộ thuật toán được dùng cho một phiên TLS. Cách cấu tạo và ngữ nghĩa tên suite khác nhau giữa TLS 1.2 và TLS 1.3.

### 4.1. Ví dụ TLS 1.2

Một cipher suite điển hình:

~~~text
TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
~~~

Có thể diễn giải ở mức khái quát:

- ECDHE: cơ chế trao đổi khóa tạm thời, thường đem lại forward secrecy.
- RSA: loại authentication/signature gắn với cipher suite trong TLS 1.2.
- AES_128_GCM: thuật toán mã hóa xác thực (AEAD).
- SHA256: thành phần hash trong cấu trúc suite tương ứng.

Tên suite TLS 1.2 có thể thể hiện key exchange và authentication. Những tên như TLS_RSA_WITH_* có cấu trúc khác và không nên được chọn làm baseline hiện đại khi có ECDHE và AEAD phù hợp.

### 4.2. Ví dụ TLS 1.3

TLS 1.3 định nghĩa tên suite như:

~~~text
TLS_AES_128_GCM_SHA256
TLS_AES_256_GCM_SHA384
TLS_CHACHA20_POLY1305_SHA256
~~~

Trong TLS 1.3, cipher suite không còn mã hóa đầy đủ thông tin key exchange/authentication theo kiểu tên TLS 1.2. Những lựa chọn như supported groups và signature algorithms được thương lượng theo các trường riêng.

**Không thể suy ra TLS 1.3 hỗ trợ hay không chỉ bằng cách tìm tên TLS_ECDHE_RSA_WITH_... trong danh sách suite.** Cần kiểm tra protocol version và danh sách suite tương ứng.

### 4.3. Cipher suite phù hợp cho hệ thống mới

Thông thường, nên dùng cấu hình mặc định của JDK/provider đã được cập nhật và qua kiểm thử thay vì cố định một suite duy nhất. Lựa chọn cụ thể phụ thuộc:

- JDK/security provider.
- Loại chứng chỉ server.
- Hỗ trợ phần cứng và hiệu năng.
- FIPS hoặc chính sách tuân thủ.
- Nhu cầu tương thích đối tác.
- Phạm vi TLS 1.2 và TLS 1.3.

Những cipher suite cũ dùng RC4, 3DES, DES, export-grade crypto hoặc anonymous key exchange không phải lựa chọn an toàn cho migration.

## 5. TLS negotiation và nguyên nhân “no shared cipher”

Trong handshake, client quảng bá những protocol version, cipher suite và thuật toán mà nó cho phép. Server chọn một tổ hợp được cả hai hỗ trợ và phù hợp với certificate, key exchange, security policy.

Ví dụ:

~~~text
Client Java mới:
  TLS 1.3
  TLS 1.2
  Cipher suites AEAD hiện đại

Server legacy:
  TLS 1.0
  Cipher suites cũ dùng 3DES

Giao nhau:
  Không có
~~~

Kết quả có thể là handshake failure hoặc thông báo không tìm được protocol/cipher suite phù hợp.

Một trường hợp khác:

~~~text
Client:
  TLS 1.2
  TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256

Server:
  TLS 1.2
  Chỉ bật TLS_RSA_WITH_AES_128_CBC_SHA

Giao nhau:
  Không có suite chung
~~~

Dù cả hai hỗ trợ TLS 1.2, vẫn không thể bắt tay vì danh sách cipher suite không giao nhau.

**Cần phân biệt “giao thức chung” với “toàn bộ cấu hình mật mã chung”.** Nếu một đầu dùng certificate ECDSA còn đầu kia chỉ hỗ trợ những signature schemes không phù hợp, TLS vẫn có thể thất bại dù protocol và tên suite trông tương thích.

## 6. Java security policy ảnh hưởng handshake như thế nào?

JDK cung cấp các security properties trong file java.security và qua những cơ chế cấu hình phù hợp. Một số property quan trọng:

| Property | Tác động |
|---|---|
| jdk.tls.disabledAlgorithms | Thuật toán, giao thức hoặc yếu tố crypto không được phép dùng trong TLS |
| jdk.certpath.disabledAlgorithms | Hạn chế thuật toán khi kiểm tra certificate path |
| jdk.tls.legacyAlgorithms | Tác động tới việc xét các thuật toán cũ trong một số ngữ cảnh negotiation |
| jdk.tls.client.protocols | Tác động tới default protocol versions cho một số JSSE client context |
| https.protocols | Thường liên quan cấu hình giao thức cho HttpsURLConnection |
| javax.net.ssl.trustStore | Chỉ định truststore mặc định được dùng trong phạm vi JSSE phù hợp |
| javax.net.ssl.keyStore | Chỉ định keystore mặc định trong các ngữ cảnh sử dụng tương ứng |

Tên property không có nghĩa mọi HTTP framework, native TLS provider hoặc custom SSLContext đều bắt buộc sử dụng cùng một cấu hình. Cần đọc tài liệu của client library và kiểm tra runtime thực tế.

### 6.1. Disabled algorithms là ràng buộc, không chỉ danh sách đề xuất

Nếu một thuật toán hoặc protocol bị security policy chặn, việc gọi setEnabledProtocols hoặc setEnabledCipherSuites không bảo đảm có thể dùng nó. JSSE cần tuân thủ algorithm constraints và provider rules.

Ví dụ một chương trình gọi:

~~~java
socket.setEnabledProtocols(new String[] { "TLSv1.2" });
~~~

nhưng thư viện hoặc chính sách hệ thống không cho phép một cipher suite cần thiết, handshake vẫn thất bại.

### 6.2. Không vội sửa file java.security để mở lại crypto yếu

Sửa global JDK security policy có thể ảnh hưởng **mọi ứng dụng dùng runtime đó**, không chỉ một endpoint legacy. Điều này có thể làm tăng bề mặt tấn công cho những kết nối vốn đã an toàn.

Đừng coi việc xóa TLSv1, TLSv1.1 hoặc thuật toán yếu khỏi disabledAlgorithms là một biện pháp tương thích mặc định. Nếu có ngoại lệ thật sự được phê duyệt, phải giới hạn môi trường, đánh giá bảo mật và xây dựng mốc chấm dứt ngoại lệ.

Với hệ thống production, nên ưu tiên xử lý ở phía server, gateway riêng hoặc endpoint configuration rõ ràng hơn là hạ policy của toàn JVM.

## 7. Chứng chỉ và truststore: lỗi thường bị nhầm thành cipher mismatch

Nhiều lỗi SSLHandshakeException không liên quan tới cipher suite. Client có thể đàm phán được thuật toán nhưng không xác thực được danh tính server.

Một số tình huống:

- Certificate server hết hạn hoặc chưa có hiệu lực.
- Chuỗi CA không đầy đủ.
- Root CA không nằm trong truststore phù hợp.
- Hostname không khớp Subject Alternative Name (SAN).
- Chứng chỉ dùng thuật toán chữ ký hoặc khóa yếu bị JDK chặn.
- Certificate bị thu hồi theo policy kiểm tra của môi trường.
- Server chọn certificate khác dự kiến do SNI.
- Client dùng truststore tùy biến thiếu CA mà JDK mặc định vốn có.

### 7.1. Truststore và keystore có vai trò khác nhau

**Truststore** chứa những chứng chỉ/CA được tin cậy để xác thực peer. **Keystore** có thể chứa private key và certificate chain mà chương trình dùng khi tự chứng minh danh tính, ví dụ server TLS hoặc client mTLS.

Một số tên file thường gặp:

~~~text
cacerts
client-keystore.p12
partner-truststore.p12
~~~

Đây là tên minh họa. Nhiều JDK dùng truststore mặc định được đóng gói cùng runtime, nhưng đường dẫn và nội dung phụ thuộc vendor và cấu hình.

### 7.2. Kiểm tra certificate bằng keytool

Liệt kê keystore/truststore:

~~~bash
keytool -list -v -keystore partner-truststore.p12 -storetype PKCS12
~~~

Liệt kê certificate theo alias:

~~~bash
keytool -list -v -alias partner-ca -keystore partner-truststore.p12
~~~

Khi làm việc với certificate của đối tác, phải xác minh fingerprint, subject, issuer, validity và đúng CA theo kênh tin cậy. Không nên import một certificate chỉ vì handshake hiện tại đang lỗi.

### 7.3. Vì sao truststore tùy biến làm kết nối mới hỏng?

Nếu ứng dụng chỉ định:

~~~bash
-Djavax.net.ssl.trustStore=/config/partner-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

thì một số đường khởi tạo SSLContext mặc định có thể sử dụng truststore đã chỉ định thay vì tập CA mặc định mà người vận hành kỳ vọng. Nếu truststore này chỉ chứa một CA nội bộ, kết nối tới dịch vụ công cộng có thể thất bại.

Vì vậy, trước khi thêm truststore tùy biến, cần quyết định có nên dùng truststore riêng cho một client cụ thể hay cần tập hợp CA phù hợp với toàn bộ kết nối của ứng dụng.

## 8. Hostname verification không được tắt để “sửa TLS”

Chứng chỉ hợp lệ theo CA không đủ nếu tên endpoint không khớp danh tính được xác thực.

Ví dụ ứng dụng kết nối:

~~~text
https://payments.example.internal
~~~

nhưng chứng chỉ chỉ có SAN:

~~~text
DNS:old-payments.example.internal
~~~

Client HTTPS có thể báo lỗi hostname verification, dù CA được tin cậy và cipher suite đàm phán thành công.

Cách khắc phục:

1. Cấp lại chứng chỉ với SAN hợp lệ.
2. Cập nhật DNS hoặc endpoint đúng tên trong chứng chỉ.
3. Kiểm tra cấu hình proxy/load balancer/SNI.
4. Bảo đảm client thực hiện hostname verification theo ngữ cảnh HTTPS.

**Không cài TrustManager tin mọi chứng chỉ hoặc HostnameVerifier luôn trả true.** Hai cách này có thể biến một kênh tưởng là TLS an toàn thành kết nối dễ bị mạo danh hoặc tấn công man-in-the-middle.

Đối với hệ thống dùng IP address thay vì DNS name, yêu cầu xác thực danh tính và SAN phải được xem xét theo đúng loại identifier. Không nên mặc định chứng chỉ cho DNS name cũng hợp lệ khi kết nối qua IP.

## 9. SNI và ALPN với hệ thống legacy

### 9.1. SNI

Server Name Indication (SNI) cho phép client gửi hostname dự kiến trong TLS handshake, giúp một server dùng cùng địa chỉ IP phục vụ nhiều chứng chỉ/dịch vụ.

Ví dụ:

~~~text
Client yêu cầu:
  payments.example.org

Gateway trên 203.0.113.10:
  payments.example.org -> certificate A
  reports.example.org  -> certificate B
  default              -> certificate C
~~~

Nếu client không gửi SNI đúng hoặc kết nối bằng IP literal, gateway có thể trả certificate mặc định không khớp hostname. Điều này tạo lỗi hostname verification hoặc server có thể từ chối handshake.

Khi kiểm tra endpoint legacy, cần dùng hostname thực tế và SNI tương ứng. Một bài thử chỉ đến IP có thể cho kết quả khác với ứng dụng production.

### 9.2. ALPN

Application-Layer Protocol Negotiation (ALPN) giúp các bên thống nhất giao thức tầng ứng dụng như h2 hoặc http/1.1.

Một endpoint có thể hoàn tất TLS handshake nhưng ứng dụng lỗi vì:

- Client yêu cầu HTTP/2 nhưng server/proxy không hoạt động đúng.
- Reverse proxy chọn giao thức không được ứng dụng kỳ vọng.
- Library client đổi mặc định sau upgrade.

Vì vậy, khi lỗi xảy ra **sau TLS handshake**, cần xem protocol application đã được chọn. Không nên quy mọi lỗi HTTPS trên Java mới cho cipher suite.

## 10. mTLS: khi cả server và client cần chứng chỉ

Mutual TLS (mTLS) yêu cầu hai phía xác thực danh tính bằng chứng chỉ. Một hệ thống cũ có thể yêu cầu client certificate từ Java application.

Sơ đồ:

~~~text
Java client                          Partner server
    |                                      |
    |-------- TLS ClientHello ----------->|
    |<------- Server certificate ---------|
    |                                      |
    |   Verify server trust + hostname     |
    |                                      |
    |<------- Request client cert --------|
    |-------- Client certificate -------->|
    |-------- Proof of key ownership ---->|
    |                                      |
    |<------- TLS handshake finished ---->|
~~~

Sơ đồ là khái quát; thứ tự message cụ thể khác giữa TLS 1.2 và TLS 1.3.

Các điểm hay gặp khi migration:

- Client keystore không được load vì format/type/password khác.
- Certificate chain của client thiếu intermediate.
- Server chỉ tin CA cũ.
- Client certificate dùng thuật toán không còn được chấp nhận.
- Server giới hạn danh sách signature algorithms hoặc certificate types.
- Ứng dụng chuyển sang một SSLContext khác nên không còn sử dụng key manager chứa client key.
- TLS version hoặc cipher suite không phù hợp ngay cả khi chứng chỉ đúng.

### 10.1. Không trộn lẫn trust manager với key manager

Trong JSSE:

- **TrustManager** quyết định có tin cậy certificate của peer không.
- **KeyManager** cung cấp key/certificate để ứng dụng tự xác thực khi được yêu cầu.

Lỗi “client certificate not accepted” không thể được sửa chỉ bằng cách import CA server vào truststore. Cần kiểm tra keystore client, certificate chain, private key, thuật toán và chính sách xác thực của server.

## 11. Mã Java đơn giản để quan sát giao thức và cipher suite

Dùng một chương trình chẩn đoán nhỏ có thể giúp xác nhận kết nối từ **đúng JDK và môi trường mạng** mà ứng dụng sẽ sử dụng.

Ví dụ dùng SSLSocket:

~~~java
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;

public final class TlsProbe {
    public static void main(String[] args) throws Exception {
        String host = args.length > 0
            ? args[0] : "example.org";
        int port = args.length > 1
            ? Integer.parseInt(args[1]) : 443;

        SSLSocketFactory factory =
            (SSLSocketFactory) SSLSocketFactory.getDefault();

        try (SSLSocket socket = (SSLSocket)
                factory.createSocket(host, port)) {

            socket.setSoTimeout(5000);

            SSLParameters parameters = socket.getSSLParameters();
            parameters.setEndpointIdentificationAlgorithm("HTTPS");
            socket.setSSLParameters(parameters);

            socket.startHandshake();

            System.out.println(
                "Protocol: " + socket.getSession().getProtocol());
            System.out.println(
                "Cipher: " + socket.getSession().getCipherSuite());
            System.out.println(
                "Peer: " + socket.getSession().getPeerPrincipal());
        }
    }
}
~~~

Lưu ý:

- Đây là ví dụ chẩn đoán TLS cho một endpoint có chứng chỉ HTTPS; không phải một HTTP client hoàn chỉnh.
- Việc dùng getDefault() khiến kết quả phụ thuộc JSSE provider và cấu hình truststore/keystore của runtime.
- SSLParameters.setEndpointIdentificationAlgorithm("HTTPS") yêu cầu kiểm tra danh tính peer theo thuật toán HTTPS phù hợp.
- Ví dụ để JSSE chọn protocol/cipher suite được cho phép, không ép bật TLS cũ.
- Timeout ở ví dụ là read timeout; trong ứng dụng production cần thêm connection timeout, deadline và các chính sách mạng phù hợp.
- Khi chạy với hostname, JSSE có thể dùng SNI theo điều kiện provider/implementation. Cần xác minh SNI thực tế trong handshake log nếu endpoint phụ thuộc vào nó.

### 11.1. Xem protocol được hỗ trợ và được bật

Một đoạn kiểm tra cấu hình:

~~~java
import java.util.Arrays;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLEngine;

public final class TlsCapabilities {
    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getDefault();
        SSLEngine engine = context.createSSLEngine();

        System.out.println(
            "Supported protocols: " +
            Arrays.toString(engine.getSupportedProtocols()));

        System.out.println(
            "Enabled protocols: " +
            Arrays.toString(engine.getEnabledProtocols()));

        System.out.println(
            "Enabled suites: " +
            Arrays.toString(engine.getEnabledCipherSuites()));
    }
}
~~~

Danh sách supported/enabled là thông tin của engine/default context tại thời điểm kiểm tra. Nó không tự chứng minh remote endpoint sẽ chấp nhận một suite nào đó.

### 11.2. Không ép suite một cách thiếu căn cứ

Ví dụ:

~~~java
socket.setEnabledCipherSuites(
    new String[] { "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256" }
);
~~~

chỉ nên áp dụng nếu đội ngũ chủ động quản lý policy, xác minh suite được hỗ trợ và hiểu protocol/certificate compatibility. Với TLS 1.3, việc pin một suite TLS 1.2 có thể làm hỏng khả năng negotiation mong muốn.

Đối với client bình thường, nên ưu tiên defaults được JDK cập nhật và cấu hình tập trung có kiểm chứng.

## 12. Dùng OpenSSL để đối chiếu endpoint

OpenSSL là công cụ hữu ích để quan sát phía server, nhưng kết quả của OpenSSL **không thay thế** kết quả từ JSSE. Hai implementation có thể khác danh sách suite, security policy, CA store và extension.

Kiểm tra endpoint với SNI:

~~~bash
openssl s_client \
  -connect legacy.example.org:443 \
  -servername legacy.example.org \
  -showcerts
~~~

Chủ động thử TLS 1.2:

~~~bash
openssl s_client \
  -connect legacy.example.org:443 \
  -servername legacy.example.org \
  -tls1_2
~~~

Thử TLS 1.3 khi phía server hỗ trợ:

~~~bash
openssl s_client \
  -connect modern.example.org:443 \
  -servername modern.example.org \
  -tls1_3
~~~

Các lệnh trên là mẫu thực hành, không phải kiểm tra đã chạy trong bài học này.

Cần phân tích:

- Protocol được đàm phán.
- Cipher suite cuối cùng.
- Certificate chain do server gửi.
- Subject, issuer, validity và SAN.
- TLS alert hoặc handshake error.
- TLS extension và lựa chọn protocol ứng dụng khi cần.

OpenSSL có thể hiển thị tên cipher suite khác quy ước Java. Không nên so sánh text string mà không hiểu hai cách đặt tên và version tương ứng.

### 12.1. Kết quả OpenSSL tốt nhưng Java vẫn lỗi?

Các khả năng:

- Java truststore không chứa CA tương ứng.
- Java security property chặn thuật toán hoặc độ dài khóa.
- Java client gửi SNI khác.
- Java client dùng provider khác OpenSSL.
- Java library giới hạn enabled protocols/suites.
- Java kiểm tra hostname identity mà lệnh OpenSSL chưa thực hiện như kỳ vọng.
- Java dùng mTLS hoặc proxy route khác.

Phải kiểm tra từ đúng container, host, DNS, network path và JDK của ứng dụng. Một phép thử từ laptop có thể đi qua đường khác với production.

## 13. Bật debug TLS trong JSSE

JSSE có cơ chế debug hữu ích trong quá trình điều tra.

Ví dụ:

~~~bash
java -Djavax.net.debug=ssl:handshake -jar app.jar
~~~

Tùy phiên bản JDK và mức chi tiết mong muốn, có thể dùng cấu hình debug phù hợp theo tài liệu JSSE. Một số trường hợp cần thêm:

~~~bash
java -Djavax.net.debug=ssl:handshake:verbose -jar app.jar
~~~

Thông tin quan trọng thường gồm:

- ClientHello/ServerHello.
- Phiên bản TLS được đề xuất và chọn.
- Danh sách cipher suite, signature schemes, supported groups.
- Chứng chỉ và các bước xác thực.
- Các thuật toán không được chấp nhận.
- TLS alert và thời điểm handshake thất bại.

**Cảnh báo bảo mật:** handshake debug có thể in thông tin định danh, tên máy chủ, chứng chỉ và metadata nhạy cảm. Không bật debug chi tiết vô thời hạn trên production; giới hạn thời gian, nơi thu thập, quyền truy cập và chính sách lưu log.

### 13.1. Khi cần kiểm tra certificate path

Có thể dùng debug riêng cho Java security/certpath theo tài liệu JDK phù hợp, ví dụ:

~~~bash
java -Djava.security.debug=certpath -jar app.jar
~~~

Thông tin giúp xác định tại sao một certificate chain bị từ chối: thiếu trust anchor, algorithm constraint, path building hoặc các điều kiện khác.

Đừng thêm nhiều debug flag cùng lúc nếu không biết cần nhìn sự kiện nào. Log quá lớn có thể che mất tín hiệu cần thiết và tăng rủi ro lộ thông tin.

## 14. Bản đồ thông báo lỗi TLS thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| SSLHandshakeException: handshake_failure | Không tìm được bộ tham số, client auth hoặc server policy | Protocol, suite, signature, mTLS, debug handshake |
| Received fatal alert: protocol_version | Hai bên không thống nhất TLS version | Enabled protocols của cả hai |
| No appropriate protocol | Protocol bị tắt hoặc suite không phù hợp | Security policy và enabled configuration |
| No cipher suites in common | Không có suite tương thích | Danh sách suites, provider, certificate |
| PKIX path building failed | Không xây được certificate path tin cậy | Chain, CA, truststore, proxy |
| CertificateExpiredException | Certificate hết hạn | Validity và thời gian hệ thống |
| Certificates do not conform to algorithm constraints | Certificate/thuật toán bị ràng buộc | jdk.certpath.disabledAlgorithms, key/signature |
| No subject alternative DNS name matching | Hostname không khớp SAN | Endpoint name, certificate, SNI |
| bad_certificate / certificate_required | Phía peer từ chối hoặc cần client certificate | mTLS, keystore và CA phía server |
| Connection reset / EOF | Peer/proxy đóng kết nối, có thể ở trước/trong handshake | Network trace, gateway logs, TLS alerts |
| Unsupported or unrecognized SSL message | Có thể nói TLS với endpoint plaintext hoặc sai port/proxy | Kiểm tra protocol scheme và routing |
| HTTP/2 stream/protocol error sau handshake | TLS có thể đã xong, lỗi application protocol | ALPN và HTTP version |

Bảng chỉ là gợi ý khoanh vùng. Cùng một lỗi có thể có nhiều nguyên nhân; **stack trace, handshake log và cấu hình của cả hai phía** mới giúp xác nhận gốc lỗi.

## 15. Quy trình xác định nguyên nhân từ handshake failure

Một quy trình thực hành có thể đi theo thứ tự sau.

### Bước 1 — Xác định endpoint chính xác

Ghi:

- Hostname, port, URL hoặc JDBC URL.
- Có dùng HTTPS proxy, reverse proxy, ingress hay service mesh không.
- Có TLS termination ở load balancer không.
- Có khác biệt giữa staging và production không.
- Đường kết nối là client Java → server hay server Java ← client khác.
- Có dùng mTLS không.

### Bước 2 — Xác định JDK và JSSE provider

Ghi:

- Java major/update/build và vendor.
- Java executable thực tế đang chạy trong container.
- Security provider đang dùng.
- Có FIPS mode hoặc crypto policy riêng không.
- JVM properties và custom SSLContext.
- Phiên bản HTTP/JDBC/gRPC library.

Không chỉ đọc output java -version từ máy người phát triển; phải xác minh runtime thực tế của service.

### Bước 3 — Thu thập kết quả handshake

Chạy một TLS probe từ cùng network path, hoặc thu log JSSE có giới hạn. Ghi protocol, suite, certificate chain và alert. Dùng OpenSSL để đối chiếu cấu hình server, không coi đó là kết quả thay thế Java client.

### Bước 4 — Phân loại lỗi

~~~text
TCP connection established?
    |
    +-- No --> DNS, routing, firewall, proxy, port
    |
    +-- Yes --> TLS handshake started?
                   |
                   +-- No --> Sai protocol/endpoint/termination
                   |
                   +-- Yes --> Protocol overlap?
                                  |
                                  +-- No --> Upgrade TLS endpoint
                                  |
                                  +-- Yes --> Crypto overlap?
                                                 |
                                                 +-- No --> Suites/groups/signatures/policy
                                                 |
                                                 +-- Yes --> Certificate/identity valid?
                                                                |
                                                                +-- No --> CA/SAN/mTLS/algorithm
                                                                |
                                                                +-- Yes --> Check ALPN/application layer
~~~

Sơ đồ mang tính chẩn đoán, không phải handshake state machine chuẩn.

### Bước 5 — Đối chiếu kết quả trên JDK cũ và JDK mới

Dùng cùng endpoint, certificate, network path và dữ liệu yêu cầu nếu có thể. Ghi:

- Java cũ negotiated version/suite gì.
- Java mới đưa ra các protocol/suite gì.
- Có thay đổi CA store hoặc chain không.
- Lỗi xuất hiện ở bước nào.
- Library/client configuration có đổi không.

So sánh này giúp tránh kết luận sai rằng “Java mới không hỗ trợ server”, trong khi nguyên nhân là cấu hình truststore bị thay đổi khi chuyển container image.

## 16. Tình huống 1: server chỉ hỗ trợ TLS 1.0

Giả sử một thiết bị cũ chỉ mở:

~~~text
TLS 1.0
RSA key exchange
3DES-based cipher suites
~~~

Một Java client hiện đại dùng TLS 1.2/1.3 và policy loại bỏ thuật toán yếu sẽ không có cấu hình tương thích.

### Cách xử lý ưu tiên

1. Kiểm tra firmware hoặc bản cập nhật của server/thiết bị.
2. Yêu cầu nhà cung cấp bổ sung TLS 1.2+ và suite được hỗ trợ.
3. Nếu không thể nâng thiết bị, xem xét một **gateway chuyên biệt** ở vùng mạng hạn chế.
4. Ghi nhận ngoại lệ bảo mật và thời hạn loại bỏ.
5. Không mở lại TLS yếu trên toàn bộ ứng dụng Java chính.

### Gateway chuyển tiếp có giới hạn

~~~text
Ứng dụng Java hiện đại
      |
      | TLS 1.2/1.3 (xác thực đầy đủ)
      v
Gateway được cô lập
      |
      | Kết nối legacy có giới hạn,
      | được phê duyệt theo chính sách
      v
Thiết bị cũ
~~~

Gateway không làm chân kết nối legacy trở nên an toàn. Nó chỉ cô lập phạm vi rủi ro để ứng dụng chính không phải hạ bảo mật toàn JVM. Cần giới hạn network ACL, giám sát, xác thực, bảo vệ secret, kiểm soát endpoint, tránh Internet exposure và có kế hoạch loại bỏ.

Trong những hệ thống có yêu cầu tuân thủ chặt, ngoại lệ này có thể **không được phép**. Khi đó phải thay hoặc nâng thiết bị.

## 17. Tình huống 2: TLS 1.2 được hỗ trợ nhưng cipher suite không giao nhau

Một server legacy có TLS 1.2 nhưng chỉ bật những suite cũ. Nâng firmware/server configuration thường giải quyết tốt hơn việc hạ Java client.

Quy trình:

1. Liệt kê danh sách suite enabled phía server.
2. Liệt kê suite enabled phía Java client.
3. Xác nhận certificate type và signature algorithms.
4. Xác định suite hiện đại mà cả hai bên có thể hỗ trợ.
5. Bật một tập suite AEAD/ECDHE phù hợp ở server.
6. Kiểm tra kết nối bằng JDK đích.
7. Kiểm tra client cũ khác vẫn tương thích với cấu hình mới.

Không nên kết luận tất cả TLS 1.2 suites đều bảo mật tương đương. Bản thân phiên bản TLS không thể thay thế đánh giá cipher suite.

### 17.1. Tại sao không pin một suite duy nhất?

Cố định một suite có thể gây lỗi khi:

- Certificate server chuyển RSA ↔ ECDSA.
- Client hoặc server ưu tiên AES-GCM so với ChaCha20.
- JDK thêm hoặc thay default algorithms.
- Một cluster có node chưa được cập nhật cùng cấu hình.
- Thay security provider hoặc FIPS mode.

Cấu hình nên định nghĩa một **tập lựa chọn hợp lệ**, được review và test, thay vì pin thiếu căn cứ.

## 18. Tình huống 3: CA hoặc chứng chỉ không còn được tin cậy

Sau khi nâng container image hoặc JDK, ứng dụng gặp:

~~~text
PKIX path building failed
unable to find valid certification path to requested target
~~~

Những câu hỏi cần trả lời:

- Server đã gửi đầy đủ certificate chain chưa?
- Truststore mới có CA cần thiết không?
- Đường dẫn javax.net.ssl.trustStore có đúng không?
- Keystore/truststore có đúng type/password không?
- Có proxy nội bộ chèn certificate khác không?
- Certificate có bị giới hạn bởi thuật toán hoặc độ dài khóa không?
- Đồng hồ hệ thống có chính xác không?

Nếu CA nội bộ hợp lệ cần được tin cậy, hãy thêm CA đó vào truststore qua quy trình phê duyệt, xác minh fingerprint và quản lý vòng đời. Nếu server thiếu intermediate certificate, ưu tiên sửa certificate chain của server.

Không khắc phục bằng TrustManager chấp nhận mọi chứng chỉ. Cách này loại bỏ một thành phần cốt lõi của xác thực TLS.

## 19. Tình huống 4: hệ thống đối tác dùng mTLS

Một Java client có thể kết nối thành công tới server trong test không yêu cầu client certificate, nhưng thất bại ở production khi partner bắt buộc mTLS.

Cần đối chiếu cả hai hướng tin cậy:

~~~text
Java client                        Partner
  truststore CA partner     <---  server certificate
  client key + cert chain   --->  truststore CA client
~~~

Các thông tin cần đồng bộ với đối tác:

- Client certificate issuer, SAN/subject và mục đích sử dụng.
- Loại private key, thuật toán chữ ký và độ dài khóa.
- Certificate chain phải gửi.
- TLS versions và cipher suites.
- Trusted CA list của server.
- Chính sách rotation và thời gian overlap giữa chứng chỉ cũ/mới.

Nếu client certificate sắp hết hạn, cần có rotation plan. Một thay đổi JDK không nên biến thành sự cố do keystore path khác giữa môi trường.

## 20. Tình huống 5: TLS handshake thành công nhưng request vẫn lỗi

Nếu log cho thấy handshake hoàn tất, tiếp tục kiểm tra:

- ALPN lựa chọn HTTP/1.1 hay HTTP/2.
- HTTP host header và SNI có đồng nhất không.
- Reverse proxy có cấu hình path/routing khác không.
- Application-level authentication hoặc token.
- JDBC protocol version.
- Request timeout, session resumption và connection pooling.
- Reused TLS session khi certificate hoặc endpoint thay đổi.

Một ứng dụng Java 11+ sử dụng java.net.http.HttpClient có thể có hành vi negotiation khác một client cũ dùng HttpsURLConnection, kể cả khi cả hai dùng JSSE. Khi chuyển thư viện HTTP đồng thời với nâng JDK, cần ghi nhận cả hai thay đổi thay vì quy tất cả cho TLS.

## 21. Cấu hình Java theo đúng phạm vi

Không phải mọi đường TLS được cấu hình bằng cùng một property.

| Mức cấu hình | Phạm vi | Rủi ro |
|---|---|---|
| JVM security properties | Có thể ảnh hưởng nhiều kết nối trong JVM | Thay đổi bảo mật trên diện rộng |
| System properties JSSE | Áp dụng trong những ngữ cảnh JSSE tương ứng | Có thể khác với custom provider/client |
| SSLContext riêng | Một nhóm client/socket/engine | Cần quản lý key/trust managers |
| SSLParameters trên socket/engine | Một kết nối hoặc loại kết nối | Dễ cấu hình quá chặt |
| Framework-specific TLS config | Client/server của framework | Phụ thuộc version và implementation |
| Gateway/server TLS policy | Endpoint hoặc network boundary | Cần quản lý vận hành tập trung |

### 21.1. Không lạm dụng https.protocols

Một số ứng dụng dùng:

~~~bash
-Dhttps.protocols=TLSv1.2
~~~

Property này thường liên quan đến HttpsURLConnection. Nó không nhất thiết ảnh hưởng mọi thư viện HTTP hoặc SSLContext custom.

Nếu ứng dụng dùng Apache HttpClient, Netty, gRPC hoặc JDBC, hãy xem API cấu hình TLS của **đúng thư viện và đúng phiên bản**.

### 21.2. Cấu hình enabled protocols khi thực sự cần

Ví dụ:

~~~java
javax.net.ssl.SSLParameters parameters =
    socket.getSSLParameters();

parameters.setProtocols(new String[] {
    "TLSv1.3",
    "TLSv1.2"
});

socket.setSSLParameters(parameters);
~~~

Đây là ví dụ chủ động giới hạn giao thức cho một socket. Nó yêu cầu provider hỗ trợ các protocol đó; trong code đa JDK cần đối chiếu getSupportedProtocols trước khi yêu cầu protocol không tồn tại.

Thông thường nên để TLS library/JDK hiện đại tự chọn mặc định, trừ khi sản phẩm có policy chính thức và đã xác minh.

### 21.3. Custom TrustManager an toàn

Khi một client cần CA nội bộ, có thể tạo SSLContext riêng bằng TrustManagerFactory đã khởi tạo từ một truststore được quản trị. Đó là lựa chọn tốt hơn việc thay global truststore hoặc vô hiệu hóa certificate validation cho mọi kết nối.

Một thiết kế an toàn cần:

- Truststore chứa CA được phê duyệt.
- Không bỏ qua hostname verification.
- Cấu hình mTLS riêng nếu có client certificate.
- Rotation và expiry monitoring.
- Logging đủ xác định endpoint và trust configuration mà không in secret.
- Kiểm thử đường thất bại khi certificate không hợp lệ.

Không nên hard-code password keystore trong source hoặc command line bị log lại.

## 22. Testing matrix khi nâng JDK

Nên xây ma trận kiểm thử dựa trên **endpoint thực tế**, không chỉ một mock server hiện đại.

| Client runtime | Endpoint | Yêu cầu | Kiểm tra |
|---|---|---|---|
| JDK cũ | Server legacy | Baseline | Protocol/suite/cert đã đàm phán |
| JDK mới | Server legacy | Phát hiện incompatibility | Handshake và lỗi chính xác |
| JDK mới | Server đã nâng TLS 1.2 | Tương thích mục tiêu | Handshake, request, timeout |
| JDK mới | Server TLS 1.3 | Tận dụng protocol mới | TLS version, response |
| JDK mới | Endpoint mTLS | Xác thực hai chiều | Client key, chain, trust |
| JDK mới | Endpoint qua proxy | Đúng đường production | SNI, certificate, ALPN |
| JDK mới | Certificate hết hạn / sai host | Negative test | Phải từ chối |
| JDK mới | Server chỉ TLS cũ | Negative test | Phải từ chối theo policy |
| JDK mới | Rollout với cluster mixed nodes | Tính nhất quán | Không có node handshake lỗi |

Một test thành công khi gửi request không đủ nếu nó đi qua load balancer chỉ tới một node. Nên kiểm tra tất cả nhóm endpoint hoặc quan sát log để biết các node có cấu hình TLS đồng nhất.

### 22.1. Test về bảo mật phải có negative cases

Để chứng minh không đánh đổi bảo mật lấy tương thích, hãy kiểm tra kết nối thất bại đúng cách khi:

- Certificate không được tin cậy.
- Hostname không khớp.
- Certificate hết hạn.
- Thuật toán/chữ ký bị chính sách chặn.
- Protocol không được phép.
- Server yêu cầu client certificate nhưng client không cung cấp.
- SNI trỏ sai virtual host.

Nếu các negative tests lại thành công sau một “bản sửa TLS”, có thể ứng dụng đã vô hiệu hóa bước xác thực quan trọng.

## 23. Quy trình migration TLS cho một hệ thống lớn

### Bước 1 — Lập danh mục endpoint và ownership

Ghi rõ:

- URL, port, DNS và IP liên quan.
- Environment: dev, staging, production, disaster recovery.
- Chủ sở hữu server hoặc đối tác.
- Yêu cầu TLS, mTLS và client certificate.
- Connection library.
- Tần suất sử dụng và mức độ quan trọng.
- Ngày hết hạn certificate/firmware support.

### Bước 2 — Đo baseline trên JDK hiện tại

Lưu:

- JDK vendor/version/update.
- JSSE/native TLS provider.
- Negotiated protocol và cipher suite.
- Certificate chain và truststore.
- JVM flags.
- Endpoint network path, SNI và proxy.
- Kết quả integration test.

Cần có dữ liệu thực tế thay vì chỉ đọc tài liệu server cũ.

### Bước 3 — Chạy smoke test trên JDK mục tiêu

Test từng nhóm endpoint và thu thông báo lỗi. Không bắt đầu bằng cách chỉnh jdk.tls.disabledAlgorithms. Xác định lỗi là protocol, cipher, certificate, hostname, mTLS hay tầng ứng dụng.

### Bước 4 — Phân loại hành động

| Nhóm | Giải pháp đề xuất |
|---|---|
| Server có thể nâng TLS/cipher | Nâng server/gateway configuration |
| Certificate chain thiếu hoặc sai | Sửa chain, CA, SAN và rotation |
| Truststore ứng dụng cấu hình sai | Sửa trust configuration theo phạm vi |
| Client library cũ | Nâng library hỗ trợ JDK mục tiêu |
| Server chỉ hỗ trợ crypto yếu | Thay/upgrade endpoint, hoặc gateway cô lập được phê duyệt |
| mTLS certificate không phù hợp | Cập nhật keystore/chain/signature |
| Proxy/SNI/ALPN không phù hợp | Sửa routing và cấu hình protocol |
| Native TLS provider không tương thích | Nâng provider và dependency |

### Bước 5 — Ưu tiên nâng đầu cũ thay vì hạ đầu mới

Bật TLS 1.2 trở lên, cipher suite phù hợp và certificate hợp lệ ở server thường đem lại lợi ích cho mọi client. Hạ global JVM policy để tương thích một server cũ có thể làm yếu nhiều kết nối khác.

### Bước 6 — Kiểm thử lại và triển khai theo giai đoạn

- Thử toàn bộ endpoint.
- Test certificate negative cases.
- Canary một nhóm instance với JDK mới.
- So sánh TLS handshake error rate và latency.
- Có rollback plan cho cả JDK và TLS server configuration.
- Tránh đổi JDK, HTTP client, gateway và certificate cùng lúc nếu chưa có test tách bạch.

### Bước 7 — Loại bỏ ngoại lệ legacy

Sau khi đối tác nâng hệ thống, gỡ bỏ tạm thời:

- Gateway legacy không còn cần thiết.
- JVM flags mở quyền crypto cũ.
- Custom trust hoặc cipher policy không còn phù hợp.
- Bản client library cũ.
- Các nhánh fallback yếu bảo mật.

## 24. Theo dõi vận hành sau migration

Những chỉ số hữu ích:

- Số handshake thất bại theo endpoint.
- Phân loại lỗi: protocol, cipher, PKIX, hostname, mTLS, timeout.
- Negotiated TLS version/cipher ở mức tổng hợp khi có cơ chế thu thập phù hợp.
- Thời gian handshake và connection establishment.
- Tỷ lệ retry do connection reset.
- Expiry horizon của certificate.
- Số endpoint còn phụ thuộc TLS/cipher legacy.
- Số ngoại lệ bảo mật chưa có mốc loại bỏ.
- Ảnh hưởng lên latency và error rate của nghiệp vụ.

Cần giới hạn log để tránh lộ certificate details nhạy cảm, tenant hostname, token, private key và những thông tin ứng dụng không cần thiết. Không đưa private key vào báo cáo chẩn đoán.

## 25. Mẫu hồ sơ đánh giá một endpoint TLS

~~~text
APPLICATION
  Service name:
  Java runtime/vendor/build:
  HTTP/JDBC/TLS client library:
  JSSE or native provider:
  Container/base image:
  Network path and proxy:

ENDPOINT
  Hostname / port:
  Environment:
  Server owner:
  Business criticality:
  SNI name:
  mTLS required?:

CURRENT HANDSHAKE
  Negotiated TLS version:
  Negotiated cipher suite:
  Certificate subject/SAN:
  Issuer/chain:
  Client certificate:
  Truststore configuration:
  JVM TLS properties:

TARGET CHECK
  Target JDK:
  Supported/enabled protocols:
  Security policy constraints:
  Handshake result:
  Error/alert:
  Certificate validation:
  Application request result:

DECISION
  Server upgrade:
  Certificate/truststore repair:
  Client library upgrade:
  Isolated gateway exception:
  Risk owner:
  Time limit / removal milestone:

VALIDATION
  Positive handshake:
  Negative certificate tests:
  mTLS test:
  SNI/ALPN test:
  Full application flow:
  Canary metrics:
  Rollback tested:
~~~

Bản ghi nên nêu rõ **endpoint nào**, **JDK nào**, **phiên bản TLS/cipher nào**, **certificate nào được xác thực** và **bằng chứng nào cho thấy rủi ro đã được xử lý**. Không nên ghi chung “đã bật SSL” hoặc “TLS OK”.

## 26. Các hiểu lầm phổ biến

### “Kết nối TCP thành công nghĩa là TLS không có vấn đề”

Sai. TCP chỉ là điều kiện trước handshake, không chứng minh protocol, cipher, certificate hoặc application layer tương thích.

### “Server hỗ trợ TLS 1.2 nên Java mới chắc chắn kết nối được”

Không đủ. Phải có cipher suite, key exchange, signature, certificate và security policy tương thích.

### “Set enabled protocol là sẽ vượt qua disabledAlgorithms”

Không đúng. Security policy của JVM vẫn có thể loại protocol hoặc thuật toán.

### “SSLHandshakeException luôn là lỗi cipher”

Không đúng. Lỗi này có thể do certificate path, hostname, mTLS, protocol hoặc constraint khác.

### “TrustManager tin mọi chứng chỉ là cách sửa nhanh an toàn”

Không đúng. Nó phá vỡ xác thực peer và có thể tạo cơ hội mạo danh server. Không dùng làm workaround.

### “OpenSSL kết nối được thì Java cũng phải kết nối được”

Không đúng. Hai client có provider, truststore, thuật toán cho phép, extension và validation khác nhau.

### “TLS 1.3 dùng tên cipher suite giống TLS 1.2”

Không đúng. TLS 1.3 tách key exchange/signature khỏi cấu trúc cipher suite tên kiểu TLS 1.2.

### “Chỉ cần sửa Java application, không cần hỏi đội sở hữu server”

Không đúng. Nguyên nhân thường là server legacy không có giao thức/thuật toán hợp lệ. Nâng server thường là hướng xử lý tốt nhất.

### “Mở TLS yếu cho toàn JVM chỉ ảnh hưởng đối tác cũ”

Không đúng. Thay đổi global security policy có thể ảnh hưởng nhiều kết nối và vi phạm yêu cầu bảo mật của các luồng khác.

### “Handshake thành công là kiểm thử migration xong”

Không đúng. Cần kiểm tra request, application protocol, mTLS, load balancer, certificate rotation, timeout và production routing.

## 27. Ghi nhớ

Khi xử lý TLS trong Java compatibility migration, hãy trả lời bảy câu hỏi:

1. **Hai đầu có giao thức chung được phép không?** Ưu tiên TLS 1.2/1.3; không bật lại SSL/TLS lỗi thời theo thói quen.
2. **Có cipher suite và thuật toán phù hợp không?** Kiểm tra cả protocol, groups, signature schemes và policy.
3. **Certificate có được xác thực đúng không?** Tin cậy CA, chain, thời hạn, key/signature và hostname identity.
4. **Có mTLS, SNI, ALPN hoặc proxy tham gia không?** Xem đúng network path và client library.
5. **JDK nào thật sự đang chạy?** Xác nhận vendor, update level, provider, security properties và truststore.
6. **Giải pháp có làm yếu hệ thống khác không?** Ưu tiên nâng server, thư viện hoặc sử dụng gateway ngoại lệ được cô lập, thay vì sửa global policy.
7. **Đã kiểm chứng cả trường hợp thành công lẫn từ chối chưa?** Chạy handshake, integration, certificate negative tests và canary trên runtime mục tiêu.

Một migration TLS tốt không chỉ làm kết nối với hệ thống cũ hoạt động trở lại. Nó phải giữ được **xác thực danh tính, tính bảo mật của đường truyền, khả năng vận hành và lộ trình loại bỏ giao thức lỗi thời**. Khi các quyết định dựa trên handshake evidence, certificate validation và ranh giới rủi ro rõ ràng, việc nâng Java có thể tiến hành mà không biến ngoại lệ legacy thành một lỗ hổng lâu dài.

