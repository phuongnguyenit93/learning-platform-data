# TLS, xác minh chứng chỉ và cấu hình kết nối an toàn

Spring Data Neo4j sử dụng Neo4j Java Driver để trao đổi dữ liệu với DBMS qua giao thức Bolt. Nếu ứng dụng kết nối từ xa bằng một kênh không mã hóa, thông tin đăng nhập, câu lệnh Cypher và dữ liệu trả về có thể bị quan sát hoặc sửa đổi trên đường truyền. TLS bảo vệ kênh truyền, còn xác minh chứng chỉ giúp ứng dụng biết nó đang kết nối đúng máy chủ Neo4j.

Một kết nối an toàn cần phối hợp nhiều lớp: máy chủ bật TLS trên Bolt, chứng chỉ máy chủ hợp lệ, ứng dụng tin cậy CA phát hành chứng chỉ, hostname được kiểm tra, và ứng dụng vẫn sử dụng cơ chế xác thực người dùng Neo4j. Spring Boot cung cấp các thuộc tính dưới tiền tố `spring.neo4j.security` để cấu hình phần lớn nhu cầu TLS mà không phải tự tạo Driver.

Sau bài học, bạn có thể:

- Phân biệt mã hóa TLS, xác minh chứng chỉ, xác thực người dùng và mutual TLS.
- Chọn URI `bolt+s`, `neo4j+s` hoặc cấu hình trust riêng cho CA nội bộ.
- Giải thích vì sao `+ssc` mã hóa dữ liệu nhưng không xác minh danh tính máy chủ.
- Cấu hình Spring Boot để dùng CA hệ thống hoặc CA tùy chỉnh.
- Bật TLS cho Bolt ở phía Neo4j và yêu cầu mọi client dùng kết nối mã hóa.
- Kiểm tra certificate chain, SAN, thời hạn và private key.
- Kiểm thử kết nối bằng OpenSSL và Neo4j Java Driver.
- Lập kế hoạch xoay vòng chứng chỉ và xử lý các lỗi TLS phổ biến.

## 1. TLS bảo vệ điều gì?

TLS (Transport Layer Security) tạo một kênh truyền được mã hóa giữa ứng dụng và Neo4j. Trong quá trình bắt tay TLS, client và server thương lượng phiên mã hóa, đồng thời client kiểm tra chứng chỉ server để xác minh danh tính máy chủ.

Ba khái niệm cần tách biệt:

| Khái niệm | Câu hỏi được trả lời | Cơ chế |
|---|---|---|
| Mã hóa đường truyền | Người khác có đọc được dữ liệu khi truyền qua mạng không? | TLS mã hóa traffic |
| Xác minh chứng chỉ server | Client có đang nói chuyện với đúng Neo4j server không? | Kiểm tra certificate chain, CA và hostname |
| Xác thực người dùng | Ai được phép đăng nhập và truy vấn database? | Neo4j authentication token, ví dụ username/password |

TLS không thay thế xác thực và phân quyền của Neo4j. Một kết nối mã hóa vẫn phải dùng tài khoản ứng dụng với quyền tối thiểu cần thiết. TLS cũng chỉ bảo vệ dữ liệu khi truyền; nó không thay thế mã hóa ổ đĩa, bảo vệ backup hoặc kiểm soát quyền truy cập file.

### TLS một chiều và mutual TLS

Trong cấu hình phổ biến, server gửi chứng chỉ để client xác minh. Client sau đó đăng nhập bằng token Neo4j. Đây là TLS một chiều theo hướng xác thực server.

Mutual TLS (mTLS) bổ sung chứng chỉ client: server cũng xác minh danh tính ứng dụng gọi tới. Với Neo4j, chứng chỉ client có thể được dùng như yếu tố xác thực bổ sung cùng authentication token. mTLS không đồng nghĩa với việc tắt username/password.

## 2. Chọn đúng Bolt URI scheme

Neo4j Java Driver nhận biết chính sách mã hóa và trust thông qua scheme trong URI. Hai nhóm scheme chính là `neo4j` và `bolt`:

| URI scheme | Mã hóa TLS | Xác minh chứng chỉ server | Routing |
|---|---|---|---|
| `bolt://` | Không theo mặc định | Không | Kết nối trực tiếp một máy |
| `bolt+s://` | Có | Có, theo CA hệ thống | Kết nối trực tiếp một máy |
| `bolt+ssc://` | Có | Bỏ qua kiểm tra chứng chỉ | Kết nối trực tiếp một máy |
| `neo4j://` | Không theo mặc định | Không | Có routing |
| `neo4j+s://` | Có | Có, theo CA hệ thống | Có routing |
| `neo4j+ssc://` | Có | Bỏ qua kiểm tra chứng chỉ | Có routing |

Chọn scheme theo topology:

- Dùng `neo4j+s://` khi ứng dụng kết nối tới cụm hoặc deployment cần routing. Driver nhận routing table và có thể chuyển truy vấn tới các thành viên phù hợp.
- Dùng `bolt+s://` khi cần kết nối trực tiếp một máy Neo4j cụ thể, chẳng hạn một instance độc lập hoặc một endpoint đã được cố định.
- Dùng `+ssc` chỉ cho môi trường phát triển được cô lập khi đang thử nghiệm với chứng chỉ tự ký. Scheme này vẫn mã hóa traffic nhưng không xác minh danh tính server; một máy trung gian có thể giả mạo server.
- Tránh `bolt://` và `neo4j://` cho truy cập từ xa qua mạng không tin cậy.

Với Neo4j Aura, scheme thường được cung cấp dưới dạng `neo4j+s://`. Với self-managed Neo4j, quản trị viên cần xác nhận Bolt endpoint đã bật TLS và scheme mà client phải dùng. Driver không thể tự dò ra chính sách bảo mật trước khi kết nối.

### `+s` khác `+ssc` ở đâu?

`+s` yêu cầu TLS và kiểm tra certificate chain bằng CA được hệ thống tin cậy. `+ssc` cũng yêu cầu TLS nhưng chấp nhận chứng chỉ mà không kiểm tra danh tính theo CA. Vì vậy, chỉ nhìn thấy traffic đã mã hóa chưa đủ để kết luận kết nối chống được giả mạo server.

Nếu tổ chức dùng CA nội bộ, không cần hạ xuống `+ssc`. Hãy cung cấp CA đó cho ứng dụng thông qua trust store hoặc cấu hình trust tùy chỉnh của Spring Boot.

## 3. Chứng chỉ server cần đáp ứng điều gì?

Chứng chỉ server là chứng thư X.509 chứa public key và thông tin nhận dạng máy chủ. Private key tương ứng được giữ trên Neo4j server. Client nhận chứng chỉ trong TLS handshake và kiểm tra:

1. Chứng chỉ còn trong thời hạn hiệu lực.
2. Chuỗi chứng chỉ dẫn tới CA mà client tin cậy.
3. Chứng chỉ được phát hành cho mục đích xác thực server.
4. Hostname mà ứng dụng dùng trong URI khớp với Subject Alternative Name (SAN) của chứng chỉ.

SAN là phần quan trọng để xác định tên DNS hoặc địa chỉ IP được chứng chỉ bảo vệ. Ví dụ ứng dụng kết nối `graph.internal.example`, chứng chỉ phải có DNS SAN tương ứng. Nếu client dùng IP, chứng chỉ cần có IP SAN phù hợp; DNS SAN không tự khớp với địa chỉ IP.

Đối với cụm Neo4j, mỗi hostname mà routing table quảng bá và Driver thực sự kết nối tới phải được chứng chỉ tương ứng xác nhận. Một chứng chỉ chỉ chứa hostname của load balancer ban đầu có thể không đủ nếu Driver được chuyển hướng tới tên của các thành viên cụm.

### Certificate chain và CA

Certificate chain thường gồm chứng chỉ server (leaf) và các intermediate certificate dẫn tới root CA. CA có thể là CA công cộng hoặc CA nội bộ của tổ chức. Client chỉ cần tin cậy CA phù hợp để kiểm tra chữ ký của chuỗi chứng chỉ.

File chain trên server thường được ghép theo thứ tự chứng chỉ server trước, sau đó tới intermediate certificate và CA gốc. Hãy dùng đúng định dạng PEM và kiểm tra chain từ chính máy ứng dụng.

Không đặt private key của server trong ứng dụng. Client chỉ cần CA certificate hoặc trust bundle để xác minh server. Private key phải được giữ trên máy chủ Neo4j và giới hạn quyền đọc cho tài khoản dịch vụ Neo4j.

Neo4j yêu cầu chứng chỉ ở định dạng PEM. Private key nên ở định dạng PKCS #8 PEM. Nếu chứng chỉ được cấp ở định dạng DER, cần chuyển sang PEM trước khi cấu hình.

## 4. Cấu hình Spring Boot khi server dùng CA công cộng

Nếu chứng chỉ Neo4j được ký bởi CA đã có trong trust store hệ điều hành/JVM, có thể dùng URI có hậu tố `+s`:

~~~yaml
spring:
  neo4j:
    uri: neo4j+s://graph.example.com:7687
    authentication:
      username: app_user
      password: ${NEO4J_PASSWORD}
~~~

Hoặc nếu ứng dụng kết nối trực tiếp tới một instance:

~~~yaml
spring:
  neo4j:
    uri: bolt+s://graph.example.com:7687
    authentication:
      username: app_user
      password: ${NEO4J_PASSWORD}
~~~

Trong ví dụ:

- `spring.neo4j.uri` chọn endpoint và TLS scheme.
- `spring.neo4j.authentication.username` và `password` cung cấp thông tin đăng nhập Neo4j.
- `+s` yêu cầu mã hóa và xác minh chứng chỉ theo CA hệ thống.

Không commit mật khẩu vào repository. Dùng environment variable hoặc secret manager của môi trường triển khai:

~~~yaml
spring:
  neo4j:
    uri: neo4j+s://graph.example.com:7687
    authentication:
      username: app_user
      password: ${NEO4J_PASSWORD}
~~~

Đặt biến môi trường `NEO4J_PASSWORD` ở secret store, container runtime hoặc nền tảng triển khai. Không ghi giá trị bí mật vào log hoặc thông tin chẩn đoán.

## 5. Cấu hình Spring Boot với CA nội bộ

Nếu server dùng chứng chỉ do CA riêng của công ty phát hành, có thể cấu hình trust strategy và file CA thông qua các thuộc tính Neo4j của Spring Boot. Trong cách này, để scheme URI ở dạng `bolt://` hoặc `neo4j://`; Spring Boot bật TLS và chỉ định CA được tin cậy.

Ví dụ `application.yml` dùng routing:

~~~yaml
spring:
  neo4j:
    uri: neo4j://graph.internal.example:7687
    authentication:
      username: app_user
      password: ${NEO4J_PASSWORD}
    security:
      encrypted: true
      trust-strategy: trust-custom-ca-signed-certificates
      cert-file: /etc/neo4j/trust/company-root-ca.pem
      hostname-verification-enabled: true
~~~

Ví dụ kết nối trực tiếp một instance có thể thay URI thành `bolt://graph.internal.example:7687`.

Ý nghĩa các thuộc tính:

| Thuộc tính | Ý nghĩa |
|---|---|
| `spring.neo4j.security.encrypted` | Yêu cầu Driver dùng traffic mã hóa |
| `spring.neo4j.security.trust-strategy` | Chọn cách xác minh chứng chỉ server |
| `spring.neo4j.security.cert-file` | File PEM chứa CA certificate được tin cậy khi dùng custom CA |
| `spring.neo4j.security.hostname-verification-enabled` | Kiểm tra hostname client dùng có khớp chứng chỉ server không |

Các giá trị trust strategy được Spring Boot hỗ trợ:

| Giá trị cấu hình | Ý nghĩa |
|---|---|
| `trust-system-ca-signed-certificates` | Tin cậy chứng chỉ xác minh được qua trust store hệ thống |
| `trust-custom-ca-signed-certificates` | Tin cậy chứng chỉ được ký bởi CA trong file cấu hình |
| `trust-all-certificates` | Chấp nhận mọi chứng chỉ; chỉ dùng trong tình huống thử nghiệm rất hạn chế |

Giá trị mặc định của `hostname-verification-enabled` là `true`. Hãy giữ kiểm tra hostname bật. Nếu dùng custom CA, file `cert-file` cần chứa CA certificate hoặc bundle CA phù hợp, và file phải tồn tại bên trong filesystem của tiến trình ứng dụng (bao gồm cả container nếu chạy trong container).

Các thuộc tính trên thuộc cấu hình Neo4j của Spring Boot hiện đại. Hãy kiểm tra phiên bản Spring Boot và metadata cấu hình của dự án trước khi sao chép cấu hình sang một phiên bản cũ hơn.

### Không trộn hai cách khai báo TLS

Có hai cách thể hiện chính sách TLS:

- Scheme `+s` hoặc `+ssc` trong URI tự chọn encryption và trust policy.
- Scheme không có hậu tố kết hợp với `spring.neo4j.security.*` để Spring Boot cấu hình encryption và trust strategy.

Hãy chọn một cách nhất quán. Không khai báo các giá trị trái ngược nhau, chẳng hạn URI yêu cầu xác minh CA nhưng cấu hình khác lại yêu cầu trust tất cả chứng chỉ. Khi cần custom CA, dùng URI không có hậu tố và cấu hình `encrypted`, `trust-strategy`, `cert-file` cùng hostname verification như ví dụ.

## 6. Bật TLS ở phía Neo4j server

Client không thể tự bật TLS nếu Bolt connector trên server chưa được cấu hình. Với Neo4j self-managed, cần cài đặt chứng chỉ và private key cho SSL policy `bolt`, sau đó yêu cầu connector chỉ nhận kết nối mã hóa.

Một cấu trúc thư mục điển hình:

~~~text
NEO4J_HOME/
  certificates/
    bolt/
      private.key
      public.crt
      trusted/
      revoked/
~~~

`public.crt` chứa chứng chỉ server và chain cần thiết. `private.key` là private key tương ứng. Thư mục `trusted` dùng khi server cần xác minh chứng chỉ client trong mTLS; `revoked` chứa certificate revocation list nếu được sử dụng.

Trong `neo4j.conf`:

~~~properties
dbms.ssl.policy.bolt.enabled=true
dbms.ssl.policy.bolt.base_directory=certificates/bolt
dbms.ssl.policy.bolt.private_key=private.key
dbms.ssl.policy.bolt.public_certificate=public.crt
dbms.ssl.policy.bolt.client_auth=NONE

server.bolt.enabled=true
server.bolt.tls_level=REQUIRED
~~~

Các thuộc tính có vai trò:

- `dbms.ssl.policy.bolt.enabled=true` bật SSL policy cho Bolt.
- `private_key` và `public_certificate` chỉ tới cặp key/certificate của server.
- `client_auth=NONE` chọn TLS một chiều khi server không yêu cầu chứng chỉ client.
- `server.bolt.tls_level=REQUIRED` chỉ nhận kết nối TLS và từ chối Bolt không mã hóa.

Giá trị `OPTIONAL` cho phép cả kết nối mã hóa và không mã hóa. Nó có thể hữu ích trong giai đoạn chuyển đổi có kiểm soát, nhưng không bảo đảm mọi client đều dùng TLS. Với môi trường production, đặt `REQUIRED` sau khi tất cả client đã được chuyển sang URI/configuration an toàn. Mặc định Bolt encryption có thể bị tắt nếu chưa cấu hình SSL policy và TLS level.

### Bảo vệ private key

Private key chỉ cần đọc được bởi tài khoản chạy Neo4j. Ví dụ trên Linux, quyền file có thể giới hạn ở owner như `0400`, còn chứng chỉ public có thể đọc rộng hơn. Không cấp quyền đọc private key cho user không cần thiết, không đưa private key vào Git hoặc image ứng dụng.

Nếu private key được mã hóa bằng passphrase, cấu hình passphrase qua cơ chế secret phù hợp. Tránh ghi passphrase trực tiếp trong file cấu hình có quyền đọc rộng.

Neo4j hiện mặc định cho phép TLS 1.2 và TLS 1.3. Chỉ tùy chỉnh phiên bản TLS hoặc cipher suite khi có yêu cầu tương thích rõ ràng; cấu hình quá hẹp có thể làm client và server không tìm được bộ thông số chung để bắt tay.

## 7. HTTPS và Bolt là hai kênh khác nhau

Spring Data Neo4j sử dụng Bolt qua Neo4j Java Driver. Bật TLS cho Bolt không tự động bật HTTPS cho Neo4j Browser hoặc HTTP API.

| Kênh | Cổng mặc định | Mục đích |
|---|---:|---|
| Bolt | `7687` | Driver, Cypher Shell và truy cập ứng dụng |
| HTTP | `7474` | Neo4j Browser/HTTP API không mã hóa |
| HTTPS | `7473` | Neo4j Browser/HTTP API có mã hóa |

Nếu tổ chức cho phép Browser hoặc HTTP API truy cập từ xa, cần cấu hình SSL policy riêng cho `https`, bật `server.https.enabled=true` và cân nhắc tắt HTTP connector bằng `server.http.enabled=false`. Chính sách HTTPS độc lập với SSL policy Bolt.

Trong cluster, mã hóa Bolt client traffic cũng không tự động cấu hình mã hóa intra-cluster hoặc backup traffic. Các kênh này có SSL policy và cấu hình riêng; hãy bật theo kiến trúc triển khai và checklist bảo mật của Neo4j.

## 8. Kiểm tra chứng chỉ trước khi khởi động ứng dụng

Trước khi điều tra Spring Boot, hãy xác minh file certificate và private key.

Xem subject, issuer, thời hạn và SAN:

~~~bash
openssl x509 -in public.crt -noout -subject -issuer -dates -ext subjectAltName
~~~

Kiểm tra private key:

~~~bash
openssl pkey -in private.key -check -noout
~~~

Kiểm tra hostname cần có trong SAN. Ví dụ ứng dụng dùng `graph.internal.example`, chứng chỉ phải xác nhận hostname đó. Nếu có load balancer, routing hoặc nhiều server advertised address, xác minh tất cả hostname mà client sẽ kết nối.

Nếu cần kiểm tra cặp certificate/key có khớp nhau, so sánh public key được trích từ certificate và private key bằng OpenSSL. Không gửi private key tới công cụ kiểm tra trực tuyến hoặc đính kèm nó vào ticket.

## 9. Kiểm tra TLS handshake từ máy ứng dụng

Có thể dùng OpenSSL để xem chứng chỉ server và xác minh chuỗi CA từ máy chạy ứng dụng:

~~~bash
openssl s_client \
  -connect graph.internal.example:7687 \
  -servername graph.internal.example \
  -CAfile company-root-ca.pem \
  -verify_return_error \
  -verify_hostname graph.internal.example \
  -showcerts
~~~

Các tham số quan trọng:

- `-connect` chỉ định hostname và cổng Bolt.
- `-servername` gửi SNI để server chọn chứng chỉ phù hợp.
- `-CAfile` chỉ định CA bundle mà client tin cậy.
- `-verify_return_error` yêu cầu OpenSSL báo lỗi nếu xác minh thất bại.
- `-verify_hostname` kiểm tra tên máy chủ với chứng chỉ.
- `-showcerts` hiển thị các chứng chỉ server gửi trong handshake.

Lệnh này kiểm tra TLS handshake và certificate chain; nó không đăng nhập Neo4j hoặc thực thi Cypher. Sau khi TLS thành công, vẫn cần kiểm tra authentication và quyền truy cập database bằng Driver.

## 10. Kiểm tra kết nối bằng Neo4j Java Driver

Một smoke test độc lập có thể xác minh Driver bắt tay thành công và đang dùng encryption:

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;

public class Neo4jTlsSmokeTest {

    public static void main(String[] args) {
        String uri = System.getenv("NEO4J_URI");
        String username = System.getenv("NEO4J_USERNAME");
        String password = System.getenv("NEO4J_PASSWORD");

        try (Driver driver = GraphDatabase.driver(
                uri,
                AuthTokens.basic(username, password))) {

            driver.verifyConnectivity();

            if (!driver.isEncrypted()) {
                throw new IllegalStateException(
                    "Neo4j connection is not encrypted"
                );
            }
        }
    }
}
~~~

Nếu dùng URI `+s`, scheme yêu cầu Driver kiểm tra CA theo trust store hệ thống. Nếu dùng Spring Boot custom CA properties, hãy kiểm tra trong đúng application context đã tạo Driver được cấu hình với `encrypted=true`, custom CA và hostname verification.

Trong ứng dụng Spring Boot, có thể kiểm tra qua health check hoặc một integration test gọi `Driver.verifyConnectivity()` trên bean Driver được inject. Test nên chạy từ cùng network namespace và cùng filesystem chứa CA bundle như ứng dụng production.

## 11. Mutual TLS (mTLS) khi cần xác minh cả client

mTLS phù hợp khi server cần xác minh danh tính ứng dụng bằng chứng chỉ client ngoài username/password. Trình tự khái quát:

1. Server bật TLS và đặt `dbms.ssl.policy.bolt.client_auth=REQUIRE`.
2. Public certificate của client được đặt trong thư mục `certificates/bolt/trusted` trên server.
3. Ứng dụng giữ client certificate và private key tương ứng.
4. Driver kết nối qua URI có TLS (`+s` hoặc `+ssc`) và gửi client certificate trong handshake.
5. Ứng dụng vẫn cung cấp authentication token Neo4j, trừ khi server được cấu hình không yêu cầu authentication.

Neo4j Java Driver cung cấp ClientCertificateManagers để quản lý client certificate, bao gồm khả năng xoay vòng. Ví dụ tạo manager:

~~~java
import java.io.File;

import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.ClientCertificateManagers;
import org.neo4j.driver.ClientCertificates;
import org.neo4j.driver.GraphDatabase;

var certificate = ClientCertificates.of(
    new File("/run/secrets/neo4j-client.crt"),
    new File("/run/secrets/neo4j-client.key")
);

var certificateManager =
    ClientCertificateManagers.rotating(certificate);

try (var driver = GraphDatabase.driver(
        "neo4j+s://graph.example.com:7687",
        AuthTokens.basic(username, password),
        certificateManager)) {

    driver.verifyConnectivity();
}
~~~

Đây là ví dụ dùng Driver trực tiếp. Nếu Spring Boot đang tự cấu hình Driver cho SDN, cần tích hợp `ClientCertificateManager` vào Driver do application context quản lý thay vì tạo thêm một Driver riêng không được SDN sử dụng. mTLS không được hỗ trợ trên Neo4j Aura theo tài liệu Driver hiện tại.

Không nhầm `cert-file` trong cấu hình Spring Boot với client certificate. `spring.neo4j.security.cert-file` là file CA được dùng để tin cậy chứng chỉ server; client certificate và private key dùng cho mTLS có vòng đời và mục đích khác.

## 12. Xoay vòng chứng chỉ

Chứng chỉ có thời hạn nên phải có quy trình gia hạn trước ngày hết hạn. Một đợt rotation cần phối hợp server, client trust store và các thành viên cluster:

1. Cấp chứng chỉ mới với SAN đúng cho hostname mà ứng dụng sử dụng.
2. Kiểm tra certificate chain, thời hạn và cặp private key/public certificate.
3. Cập nhật CA trust bundle phía client nếu CA phát hành thay đổi.
4. Triển khai chứng chỉ mới tới các Neo4j server/cluster member.
5. Xác minh TLS handshake bằng hostname và CA bundle mới.
6. Theo dõi kết nối mới, lỗi handshake và trạng thái cluster trước khi loại bỏ chứng chỉ cũ.

Với Neo4j từ phiên bản 2025.03 hỗ trợ dynamic TLS reload, có thể bật:

~~~properties
dbms.security.tls_reload_enabled=true
~~~

Thiết lập này cần được bật trước và có hiệu lực theo yêu cầu phiên bản. Sau khi cập nhật chứng chỉ và SSL policy trên các server, chạy thủ tục reload trên từng thành viên:

~~~cypher
CALL dbms.security.reloadTLS()
~~~

Kết nối đã được thiết lập trước thời điểm reload không bị ngắt ngay; kết nối mới sẽ dùng chứng chỉ mới. Vì vậy, phải kiểm tra các kết nối mới và vẫn theo dõi pool kết nối cũ trong giai đoạn chuyển tiếp. Với phiên bản Neo4j không hỗ trợ dynamic reload, thực hiện quy trình restart phù hợp với topology.

Khi xoay vòng CA, nên có giai đoạn chuyển tiếp mà ứng dụng tin cậy cả CA cũ và CA mới, sau đó mới gỡ CA cũ khi mọi server đã dùng certificate chain mới. Với mTLS, client certificate manager hỗ trợ `.rotate()` để các kết nối mới dùng chứng chỉ client mới.

## 13. Lỗi TLS thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `PKIX path building failed` | Client không tìm được CA tin cậy để xây dựng certificate chain | Kiểm tra CA bundle, intermediate certificate và trust strategy |
| `No subject alternative DNS name matching ...` | Hostname trong URI không khớp SAN của server certificate | Dùng hostname có trong SAN hoặc cấp lại certificate |
| `CertificateExpiredException` | Chứng chỉ server hoặc CA đã hết hạn | Kiểm tra `notAfter`, gia hạn và triển khai chain mới |
| `SSLHandshakeException` | TLS level, protocol, certificate hoặc trust policy không tương thích | Kiểm tra server SSL policy, client URI và log handshake |
| Kết nối bị từ chối trước handshake | Bolt chưa bật, sai cổng hoặc firewall chặn | Kiểm tra `server.bolt.enabled`, listen address và cổng `7687` |
| Server từ chối client certificate | mTLS yêu cầu chứng chỉ nhưng client không gửi hoặc chứng chỉ không được tin cậy | Kiểm tra `client_auth`, client cert và thư mục `trusted` |
| Kết nối thành công nhưng đăng nhập thất bại | TLS đúng nhưng credentials hoặc quyền Neo4j sai | Kiểm tra authentication token và quyền user |

Khi cần log sâu, có thể bật debug TLS tạm thời trên JVM:

~~~properties
server.jvm.additional=-Djavax.net.debug=ssl:handshake
~~~

Log TLS rất chi tiết và có thể tăng nhanh theo số lần kết nối. Chỉ bật trong khoảng thời gian chẩn đoán, giới hạn quyền truy cập log và tắt ngay sau khi thu thập đủ thông tin. Không bật mức log có thể lộ credentials hoặc dữ liệu nhạy cảm trong môi trường production kéo dài.

## 14. Checklist cấu hình kết nối an toàn

Trước khi phát hành ứng dụng SDN có kết nối Neo4j từ xa, xác minh:

- [ ] Bolt connector đã bật SSL policy và `server.bolt.tls_level=REQUIRED`.
- [ ] Ứng dụng dùng `neo4j+s` hoặc `bolt+s`, hoặc dùng Spring Boot security properties với encryption bật.
- [ ] CA phát hành server certificate nằm trong trust store hệ thống hoặc custom CA bundle của ứng dụng.
- [ ] Hostname dùng trong URI khớp SAN của chứng chỉ.
- [ ] Certificate còn hạn và chain đầy đủ.
- [ ] Private key chỉ có tài khoản Neo4j được phép đọc.
- [ ] Mật khẩu Neo4j và passphrase được lưu trong secret manager/environment, không commit.
- [ ] User ứng dụng có quyền tối thiểu cần thiết.
- [ ] Không dùng `+ssc`, `trust-all-certificates` hoặc tắt hostname verification trong production.
- [ ] Nếu dùng cluster, tất cả advertised hostname đều có chứng chỉ hợp lệ.
- [ ] Có quy trình gia hạn/rotation và giám sát ngày hết hạn.
- [ ] Nếu dùng mTLS, client certificate được quản lý riêng và server chỉ tin cậy đúng client certificate/CA cần thiết.

## 15. Những lỗi thường gặp

**Chỉ đổi URI sang `bolt+s` mà server chưa bật TLS.** Client yêu cầu TLS nhưng server chỉ chấp nhận Bolt không mã hóa. Cấu hình SSL policy và TLS level ở server trước.

**Dùng `+ssc` trong production vì chứng chỉ tự ký.** Traffic có mã hóa nhưng client không xác minh danh tính server. Hãy dùng CA nội bộ và cấu hình trust custom CA.

**Tắt hostname verification để hết lỗi SAN.** Điều này bỏ một lớp xác minh quan trọng. Cấp chứng chỉ có SAN khớp hostname thật và giữ verification bật.

**Nhầm `cert-file` là server certificate.** File này thuộc cấu hình trust phía client. Server certificate và private key được cài trên Neo4j server.

**Dùng CA certificate nhưng thiếu intermediate chain.** Client có thể không xây dựng được chain tới root CA. Cài đầy đủ intermediate và xác minh bằng OpenSSL.

**Dùng `bolt+s` với cụm có routing.** Scheme này kết nối trực tiếp một host; với routing cluster, dùng `neo4j+s` và đảm bảo certificate SAN khớp các địa chỉ được quảng bá.

**Bật TLS ở Bolt nhưng quên HTTPS hoặc cluster channel.** Mỗi channel có SSL policy riêng. Kiểm tra các kênh mà hệ thống thực sự sử dụng.

**Coi mTLS là thay thế hoàn toàn authentication token.** Client certificate là yếu tố bổ sung trong cấu hình thông thường. Tiếp tục dùng token Neo4j và phân quyền user.

**Thay chứng chỉ mà không cập nhật trust store hoặc pool kết nối.** Kết nối cũ có thể còn hoạt động trong khi kết nối mới thất bại. Lập kế hoạch rotation có giai đoạn chuyển tiếp và kiểm thử handshake mới.

## 16. Tự kiểm tra

1. TLS mã hóa traffic và xác minh chứng chỉ giải quyết hai vấn đề nào?
2. `bolt+s` và `neo4j+s` khác nhau ở khả năng routing nào?
3. Vì sao `+ssc` không phù hợp cho production dù traffic đã mã hóa?
4. Certificate chain, CA và SAN tham gia vào quá trình xác minh server ra sao?
5. Spring Boot dùng thuộc tính nào để bật TLS, chọn custom CA và bật hostname verification?
6. Vì sao `server.bolt.tls_level=REQUIRED` quan trọng ở phía Neo4j?
7. TLS cho Bolt khác HTTPS và intra-cluster encryption như thế nào?
8. mTLS khác xác minh server certificate ở điểm nào?
9. Cần kiểm tra gì khi gặp lỗi `PKIX path building failed`?
10. Vì sao phải phối hợp cập nhật trust store client và chứng chỉ server khi rotation?

**Bài tập thực hành:** Thiết lập một Neo4j self-managed có Bolt TLS với chứng chỉ do CA nội bộ ký. Cấu hình server bằng SSL policy `bolt` và `server.bolt.tls_level=REQUIRED`. Trong ứng dụng Spring Boot, cấu hình `spring.neo4j.security.encrypted=true`, `trust-strategy=trust-custom-ca-signed-certificates`, đường dẫn `cert-file` tới CA bundle và giữ hostname verification bật. Kiểm tra certificate SAN, chain và thời hạn bằng OpenSSL; sau đó gọi `Driver.verifyConnectivity()` và xác nhận `Driver.isEncrypted()`. Thử lần lượt hostname sai, CA không được tin cậy và URI không mã hóa để quan sát lỗi. Cuối cùng, mô phỏng quy trình thay CA/certificate và ghi lại các bước rotation, reload và xác minh kết nối mới.

## Tài liệu tham khảo

- [Neo4j Java Driver Manual — Advanced connection information](https://neo4j.com/docs/java-manual/current/connect-advanced/)
- [Neo4j Java Driver API — Config.TrustStrategy](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/Config.TrustStrategy.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Boot API — Neo4jProperties.Security](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/neo4j/autoconfigure/Neo4jProperties.Security.html)
- [Spring Boot API — Neo4jProperties.Security.TrustStrategy](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/neo4j/autoconfigure/Neo4jProperties.Security.TrustStrategy.html)
- [Neo4j Operations Manual — SSL framework](https://neo4j.com/docs/operations-manual/current/security/ssl-framework/)
- [Neo4j Operations Manual — Configure network connectors](https://neo4j.com/docs/operations-manual/current/configuration/connectors/)
- [Neo4j Operations Manual — Security checklist](https://neo4j.com/docs/operations-manual/current/security/checklist/)
