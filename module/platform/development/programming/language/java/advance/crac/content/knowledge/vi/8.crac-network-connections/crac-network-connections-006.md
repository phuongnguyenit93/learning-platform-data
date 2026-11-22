# TLS, chứng chỉ và phiên kết nối sau khoảng tạm dừng

Ứng dụng Java thường sử dụng TLS để bảo vệ kết nối tới database, API, message broker, service mesh hoặc dịch vụ bên ngoài. Một kết nối TLS đang hoạt động gồm nhiều trạng thái ở cả hai phía: socket TCP, trạng thái mã hóa của TLS, khóa phiên, bộ đếm bản ghi, trạng thái giao thức và có thể cả trạng thái xác thực của ứng dụng. Khi CRaC tạo checkpoint, JVM tạm ngừng hoạt động trong khi máy chủ, load balancer, firewall, DNS, hệ thống cấp chứng chỉ và các dịch vụ khác vẫn tiếp tục vận hành.

Trong khoảng tạm dừng đó, kết nối đang mở có thể bị phía bên kia đóng do idle timeout, phiên làm việc có thể hết hạn, máy chủ có thể được triển khai lại và chứng chỉ có thể được thay mới. Khi restore, một đối tượng Java vẫn giữ tham chiếu tới socket hoặc client không chứng minh rằng kết nối TLS còn sử dụng được. Ứng dụng cần kiểm tra và thường phải tạo kết nối mới.

Cũng cần phân biệt **kết nối TLS** với **TLS session resumption**. Kết nối TLS là một phiên truyền dữ liệu được bảo vệ trên một kết nối mạng cụ thể. Session resumption dùng thông tin phiên hoặc ticket để giảm chi phí xác thực khi thiết lập một kết nối TLS mới. Nó không khôi phục socket TCP cũ và không bảo đảm rằng các điều kiện chứng thực, chính sách bảo mật hoặc trạng thái phía máy chủ vẫn còn hợp lệ.

Trong ứng dụng dùng CRaC, cách tiếp cận phổ biến là dừng và đóng các kết nối TLS trước checkpoint, rồi sau restore tạo lại client hoặc connection pool, tải lại thông tin chứng thực cần thiết, thực hiện handshake mới và chỉ nhận lưu lượng khi các phụ thuộc đã sẵn sàng.

## 1. Những lớp trạng thái trong một kết nối TLS

Khi một ứng dụng kết nối tới dịch vụ HTTPS, database hoặc broker qua TLS, có nhiều lớp trạng thái khác nhau:

| Lớp | Ví dụ | Có thể thay đổi khi JVM tạm dừng? |
|---|---|---|
| Kết nối mạng | TCP socket, route, NAT mapping, firewall state | Có. Thiết bị mạng hoặc máy chủ có thể timeout, đóng hoặc thay đổi đường đi |
| Kết nối TLS đang hoạt động | Khóa traffic, sequence number, trạng thái mã hóa, record layer | Có thể không còn dùng được nếu socket bị đóng hoặc peer đã hủy phiên |
| TLS session | Session ID, session ticket, trạng thái dùng cho resumption | Có. Session hoặc ticket có thể hết hạn, bị thu hồi hoặc bị máy chủ từ chối |
| Chứng thực | Chứng chỉ máy chủ, chứng chỉ client, truststore, private key | Có. Chứng chỉ có thể được rotate, hết hạn hoặc bị thu hồi; trust material có thể thay đổi |
| Trạng thái ứng dụng | HTTP request, transaction, subscription, authentication token | Có. Session nghiệp vụ và transaction có thể hết hạn hoặc bị dịch vụ hủy |

Một socket có thể vẫn tồn tại ở phía JVM nhưng không còn được peer chấp nhận. Ngược lại, một TLS session ticket có thể còn hiệu lực nhưng kết nối TCP trước đó đã biến mất. Hai tình huống này cần cách xử lý khác nhau.

### 1.1. Kết nối TLS đang mở

Sau khi TLS handshake hoàn tất, hai đầu kết nối sử dụng các khóa và trạng thái phiên đã thương lượng để bảo vệ dữ liệu. Các bản ghi TLS tiếp theo phụ thuộc vào đúng trạng thái của kết nối đó. Nếu một bên đóng socket, khởi động lại hoặc quên trạng thái kết nối, phía còn lại không thể tiếp tục trao đổi dữ liệu chỉ bằng cách giữ đối tượng socket trong heap.

Trong thời gian checkpoint, các thành phần bên ngoài có thể:

- Đóng kết nối vì idle timeout hoặc giới hạn thời gian sống của connection.
- Hủy NAT mapping hoặc trạng thái firewall do không còn lưu lượng.
- Chuyển traffic sang máy chủ khác sau khi load balancer thay đổi backend.
- Khởi động lại dịch vụ hoặc thay thế pod/container.
- Thu hồi session ở tầng ứng dụng hoặc yêu cầu client xác thực lại.

Vì vậy, không nên giả định một socket TLS đã mở trước checkpoint vẫn còn hợp lệ sau restore. Với connection pool, cần đóng hoặc loại bỏ các connection đang mở theo hướng dẫn của pool. Với client tự quản lý socket, cần đóng socket trong callback trước checkpoint và tạo socket mới sau restore.

### 1.2. TLS session resumption

TLS session resumption cho phép hai bên sử dụng thông tin đã thiết lập trước đó để giảm chi phí handshake khi tạo kết nối mới. Tùy phiên bản TLS và cách triển khai, cơ chế có thể sử dụng session ID, session cache hoặc session ticket/Pre-Shared Key (PSK).

Điểm quan trọng:

- Resumption vẫn thiết lập một kết nối mạng mới; nó không hồi sinh TCP socket cũ.
- Ticket có thể có thời hạn và máy chủ có thể từ chối ticket vì đã thay khóa, restart hoặc thay chính sách.
- Client và server có thể không còn trạng thái session tương thích sau một khoảng dừng dài.
- Resumption không thay thế việc kiểm tra hostname, chính sách chứng thực và quyền truy cập ở tầng ứng dụng.
- Ứng dụng phải xử lý được trường hợp resumption thất bại và handshake đầy đủ được thực hiện lại.

Với TLS 1.3, server có thể cấp session ticket sau handshake để client dùng trong kết nối tiếp theo. Ticket là một cơ chế tối ưu handshake, không phải một bảo đảm rằng kết nối cũ hoặc danh tính ứng dụng vẫn được chấp nhận mãi mãi. Cách xác minh chứng chỉ và trạng thái xác thực trong một lần resumption còn phụ thuộc giao thức, thư viện và chính sách server; không nên giả định mọi lần resumption đều thực hiện lại toàn bộ quy trình giống một handshake mới.

Nếu ứng dụng cần áp dụng ngay truststore hoặc chứng chỉ mới sau restore, cần xem xét session cache và ticket lifetime. Một SSLContext mới thường tạo session context mới ở phía client và giúp tránh dùng lại cache thuộc context cũ. Chính sách phía server vẫn cần được cấu hình phù hợp, nhất là khi có yêu cầu thu hồi hoặc thay đổi danh tính ngay lập tức.

### 1.3. TLS 1.3 và dữ liệu 0-RTT

TLS 1.3 có thể hỗ trợ early data (0-RTT) khi resumption. Dữ liệu được gửi sớm giúp giảm độ trễ, nhưng có rủi ro bị replay trong một số mô hình tấn công. Vì vậy, không nên gửi thao tác có tác động không thể lặp an toàn như thanh toán, tạo đơn hàng, chuyển tiền hoặc cập nhật trạng thái quan trọng dưới dạng early data nếu hệ thống chưa có cơ chế chống replay phù hợp.

Sau một khoảng tạm dừng, nếu client hoặc thư viện tự động dùng 0-RTT, hãy kiểm tra chính sách của thư viện và server. Với thao tác nghiệp vụ có side effect, ưu tiên handshake bình thường rồi gửi request sau khi kết nối được xác thực; đồng thời dùng idempotency key ở tầng ứng dụng khi request có thể được gửi lại.

## 2. Chứng chỉ có thể thay đổi trong lúc JVM dừng

TLS dựa vào chứng chỉ số và chuỗi tin cậy để xác minh danh tính. Chứng chỉ có thời hạn hiệu lực, có thể được thay mới hoặc bị thu hồi. Truststore và keystore của ứng dụng cũng có thể được cập nhật độc lập với tiến trình Java.

### 2.1. Chứng chỉ máy chủ hết hạn hoặc được rotate

Trong một handshake đầy đủ, client xác minh chứng chỉ máy chủ theo cấu hình trust manager và các quy tắc xác minh danh tính. Những kiểm tra thường gặp gồm:

- Chuỗi chứng chỉ dẫn tới trust anchor được tin cậy.
- Thời điểm hiện tại nằm trong khoảng hiệu lực của chứng chỉ.
- Tên máy chủ khớp với Subject Alternative Name (SAN) theo hostname đang kết nối.
- Key usage, extended key usage và thuật toán đáp ứng chính sách bảo mật.
- Trạng thái thu hồi được kiểm tra nếu ứng dụng và môi trường đã cấu hình OCSP, CRL hoặc cơ chế tương ứng.

Nếu chứng chỉ máy chủ được thay trong lúc JVM dừng, kết nối mới sau restore sẽ gặp chứng chỉ mới. Nếu truststore không tin cậy CA mới, handshake sẽ thất bại. Nếu hostname không khớp, việc tin cậy CA cũng không đủ để kết nối an toàn.

Chứng chỉ hết hạn không nhất thiết làm một kết nối TLS đã thiết lập tự động dừng ngay tại thời điểm hết hạn. Việc xác minh chứng chỉ thường diễn ra trong quá trình handshake; một kết nối đang tồn tại có thể tiếp tục cho đến khi một đầu đóng nó hoặc chính sách tầng ứng dụng kết thúc phiên. Tuy nhiên, khi reconnect, chứng chỉ được kiểm tra theo thời điểm và chính sách của handshake mới.

Điều đó khiến restore là thời điểm cần kiểm tra lại kết nối và chứng thực. Nếu ứng dụng giữ socket cũ, nó có thể tiếp tục sử dụng một phiên đã được xác thực trước khi chứng chỉ thay đổi. Nếu ứng dụng đóng socket và handshake lại, nó sẽ thực hiện xác minh theo trạng thái chứng chỉ và trust material mới đang được sử dụng.

### 2.2. Truststore được cập nhật

Truststore chứa các CA hoặc chứng chỉ được ứng dụng tin cậy. Nhiều ứng dụng nạp truststore khi tạo SSLContext hoặc khi khởi động JVM. Sau khi trust manager đã được khởi tạo, thay đổi tệp truststore trên đĩa thường không tự cập nhật các đối tượng đang nằm trong heap.

Ví dụ:

1. JVM khởi động và đọc truststore có CA cũ.
2. Quản trị viên thay truststore trên volume để tin cậy CA mới.
3. JVM tiếp tục chạy hoặc được restore từ checkpoint.
4. SSLContext cũ vẫn có thể sử dụng TrustManager đã được tạo từ nội dung cũ.
5. Kết nối tới server dùng chứng chỉ do CA mới cấp có thể thất bại dù tệp truststore trên đĩa đã được cập nhật.

Nếu muốn sử dụng truststore mới, ứng dụng cần nạp lại KeyStore, tạo TrustManagerFactory mới và khởi tạo SSLContext mới. Chỉ mở lại socket bằng SSLContext cũ không làm trust manager tự đọc lại tệp.

### 2.3. Chứng chỉ client và mutual TLS

Trong mutual TLS (mTLS), cả client và server đều xác minh chứng chỉ của phía còn lại. Client có thể cần private key và chứng chỉ client để chứng minh danh tính với server.

Trong khoảng checkpoint, chứng chỉ client có thể được rotate, private key có thể thay đổi hoặc chứng chỉ cũ có thể bị thu hồi. Sau restore, nếu ứng dụng tiếp tục dùng KeyManager đã khởi tạo từ keystore cũ, nó có thể trình ra chứng chỉ không còn được server chấp nhận.

Để dùng chứng chỉ client mới, cần nạp lại keystore, tạo KeyManagerFactory mới và khởi tạo SSLContext mới với cả key managers và trust managers. Private key phải được bảo vệ; không ghi ra log và không đưa bí mật vào ảnh checkpoint nếu có thể lấy lại từ secret manager sau restore.

### 2.4. Thu hồi chứng chỉ và kiểm tra trạng thái thu hồi

Chứng chỉ có thể bị thu hồi trước ngày hết hạn. Việc kiểm tra OCSP hoặc CRL phụ thuộc vào cấu hình TLS provider, trust manager, chính sách của ứng dụng và khả năng truy cập tới dịch vụ kiểm tra thu hồi.

Không nên mặc định rằng chỉ cần tạo kết nối mới là mọi triển khai Java đều tự kiểm tra trạng thái thu hồi theo cùng một cách. Hãy xác minh cấu hình revocation checking thực tế. Nếu trust manager hoặc provider có cache kết quả OCSP/CRL, cần hiểu thời hạn cache và cách làm mới sau restore.

Nếu chính sách bảo mật yêu cầu thu hồi có hiệu lực ngay, hãy phối hợp thời gian sống của TLS session, session ticket, cache và kết nối với yêu cầu đó. Session resumption có thể làm thay đổi cách handshake xử lý chứng thực; quyết định cho phép resumption phải phù hợp với chính sách xác minh danh tính của hệ thống.

## 3. Thời gian tạm dừng ảnh hưởng đến kết nối như thế nào?

JVM không xử lý callback, heartbeat hoặc request trong lúc tiến trình bị dừng để checkpoint. Trong khi đó, đồng hồ của hệ thống và dịch vụ bên ngoài vẫn tiếp tục chạy. Khoảng thời gian này có thể làm hết hạn nhiều trạng thái:

- TCP connection bị đóng do idle timeout.
- Connection pool loại bỏ connection do max lifetime.
- TLS session hoặc ticket hết hạn.
- Token truy cập hết hạn.
- Chứng chỉ đi qua thời điểm notAfter hoặc chưa tới notBefore theo đồng hồ hiện tại.
- Session đăng nhập hoặc lease ở tầng ứng dụng hết hạn.
- DNS record hoặc backend của load balancer thay đổi.
- Server triển khai lại và không còn giữ session cache trước đó.

Khi restore, hãy dùng thời gian hiện tại để xác định trạng thái hợp lệ. Không nên tiếp tục dùng một bộ đếm thời gian hoặc cờ boolean trong heap để kết luận rằng token, session hay lease vẫn còn hiệu lực.

Đồng hồ hệ thống cũng rất quan trọng đối với xác minh chứng chỉ. Nếu máy restore có clock sai, chứng chỉ có thể bị xem là chưa có hiệu lực hoặc đã hết hạn dù nội dung chứng chỉ không đổi. Môi trường triển khai cần đồng bộ thời gian và ứng dụng cần xử lý lỗi xác minh theo cách có thể chẩn đoán được.

## 4. Những thông tin TLS cần làm mới sau restore

Không phải mọi thành phần TLS đều cần được tạo lại trong mọi ứng dụng. Quyết định phụ thuộc vào cách client và thư viện quản lý trạng thái. Bảng dưới đây là hướng dẫn để phân loại:

| Thành phần | Hành động thường cần sau restore | Lý do |
|---|---|---|
| TCP/TLS socket đang mở | Đóng trước checkpoint, tạo kết nối mới sau restore | Peer, firewall hoặc NAT có thể đã đóng trạng thái cũ |
| HTTP/database/broker connection pool | Drain và đóng pool, tạo pool mới | Pool có thể giữ nhiều socket cũ và trạng thái xác thực cũ |
| SSLContext | Cân nhắc tạo mới nếu truststore, keystore hoặc chính sách có thể thay đổi | TrustManager, KeyManager và session cache được khởi tạo cùng context |
| Truststore | Nạp lại khi CA hoặc trust policy được rotate | Tệp trên đĩa thay đổi không tự cập nhật trust manager đã tạo |
| Keystore và private key | Nạp lại khi chứng chỉ client hoặc key được rotate | KeyManager cũ có thể tiếp tục trình ra chứng chỉ cũ |
| TLS session cache/ticket | Kiểm tra thời hạn và chính sách resumption | Session có thể hết hạn hoặc không còn phù hợp với chính sách mới |
| DNS và endpoint | Phân giải lại hostname khi tạo kết nối mới | Backend hoặc địa chỉ IP có thể đã thay đổi |
| Token tầng ứng dụng | Refresh hoặc xác thực lại | Token có thể hết hạn độc lập với TLS |
| ALPN và protocol policy | Thương lượng lại khi tạo kết nối mới | Server hoặc cấu hình có thể đã thay đổi giao thức được hỗ trợ |

Một SSLContext có thể được dùng để tạo nhiều kết nối. Nếu ứng dụng giữ context cũ và chỉ tạo socket mới, kết nối mới vẫn có thể sử dụng trust/key material cũ và session cache cũ. Khi cần tiếp nhận thay đổi chứng chỉ hoặc truststore, hãy tái tạo context từ nguồn cấu hình hiện hành.

## 5. Quản lý TLS bằng Resource của CRaC

Một resource chịu trách nhiệm quản lý TLS có thể triển khai org.crac.Resource và đăng ký với global context:

~~~java
Core.getGlobalContext().register(tlsResource);
~~~

beforeCheckpoint() nên:

1. Ngừng nhận request hoặc message mới qua client đang quản lý.
2. Chờ request đang chạy hoàn tất trong thời hạn đã định.
3. Flush hoặc hoàn tất thao tác cần thiết theo giao thức ứng dụng.
4. Đóng socket TLS và các connection thuộc pool.
5. Xóa tham chiếu tới trạng thái kết nối cũ để tránh code nghiệp vụ sử dụng lại.

afterRestore() nên:

1. Đọc lại cấu hình endpoint, truststore và keystore nếu chúng có thể thay đổi.
2. Tạo KeyManagerFactory và TrustManagerFactory mới khi cần.
3. Khởi tạo SSLContext mới theo chính sách TLS hiện hành.
4. Tạo connection pool hoặc socket mới và thực hiện handshake.
5. Xác minh hostname, chứng chỉ, mTLS và trạng thái xác thực ứng dụng.
6. Chỉ mở readiness khi các kết nối bắt buộc đã sẵn sàng.

Callback chỉ là điểm điều phối vòng đời. Việc đóng pool phải theo API của thư viện; không nên tự đóng socket bên dưới một HTTP client trong khi client vẫn giữ tham chiếu tới connection đó. Nếu thư viện đã có CRaC integration, hãy dùng integration được hỗ trợ và tránh quản lý trùng một tài nguyên.

## 6. Ví dụ: tạo lại SSLContext và TLS socket sau restore

Ví dụ dưới đây minh họa một client kết nối tới một dịch vụ TLS bằng truststore riêng. Resource đóng socket trước checkpoint. Sau restore, nó đọc lại đường dẫn và mật khẩu truststore từ cấu hình môi trường, tạo TrustManagerFactory mới, tạo SSLContext mới và thực hiện TLS handshake mới.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.Arrays;

import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManagerFactory;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class TlsConnectionResource implements Resource {
    private final String host;
    private final int port;
    private SSLSocket socket;
    private SSLContext sslContext;

    public TlsConnectionResource(String host, int port)
            throws Exception {
        this.host = host;
        this.port = port;

        openConnection();
        Core.getGlobalContext().register(this);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws IOException {
        closeConnection();
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        openConnection();
    }

    private synchronized void openConnection() throws Exception {
        SSLContext freshContext = createSslContext();
        Socket transport = new Socket();
        SSLSocket candidate = null;

        try {
            transport.connect(
                    new InetSocketAddress(host, port),
                    5_000
            );

            candidate = (SSLSocket) freshContext.getSocketFactory()
                    .createSocket(transport, host, port, true);
            transport = null; // TLS socket đã nhận quyền sở hữu socket nền.

            candidate.setSoTimeout(5_000);

            SSLParameters parameters = candidate.getSSLParameters();
            parameters.setEndpointIdentificationAlgorithm("HTTPS");
            candidate.setSSLParameters(parameters);

            // Thực hiện handshake trước khi công bố kết nối sẵn sàng.
            candidate.startHandshake();

            this.sslContext = freshContext;
            this.socket = candidate;
        } catch (Exception failure) {
            try {
                if (candidate != null) {
                    candidate.close();
                } else if (transport != null) {
                    transport.close();
                }
            } catch (IOException closeFailure) {
                failure.addSuppressed(closeFailure);
            }
            throw failure;
        }
    }

    private SSLContext createSslContext()
            throws IOException, GeneralSecurityException {
        String trustStoreLocation =
                System.getenv("TLS_TRUSTSTORE");
        if (trustStoreLocation == null
                || trustStoreLocation.isBlank()) {
            throw new IllegalStateException(
                    "TLS_TRUSTSTORE is not configured");
        }

        String passwordValue =
                System.getenv("TLS_TRUSTSTORE_PASSWORD");
        char[] password = passwordValue == null
                ? new char[0]
                : passwordValue.toCharArray();

        try {
            KeyStore trustStore =
                    KeyStore.getInstance(KeyStore.getDefaultType());

            try (InputStream input = Files.newInputStream(
                    Path.of(trustStoreLocation))) {
                trustStore.load(input, password);
            }

            TrustManagerFactory trustManagers =
                    TrustManagerFactory.getInstance(
                            TrustManagerFactory.getDefaultAlgorithm());
            trustManagers.init(trustStore);

            SSLContext context = SSLContext.getInstance("TLS");
            context.init(
                    null,
                    trustManagers.getTrustManagers(),
                    new SecureRandom()
            );
            return context;
        } finally {
            Arrays.fill(password, '\0');
        }
    }

    private synchronized void closeConnection() throws IOException {
        SSLSocket current = socket;
        socket = null;
        sslContext = null;

        if (current != null) {
            current.close();
        }
    }
}
~~~

Các điểm đáng chú ý:

- Resource tạo kết nối ban đầu rồi đăng ký với global context.
- Trước checkpoint, socket TLS được đóng và các trường tham chiếu tới kết nối cũ được xóa.
- Sau restore, truststore được đọc lại từ đường dẫn hiện hành và SSLContext mới được tạo.
- Socket TCP mới được mở với timeout kết nối, sau đó được bọc bằng SSLSocket.
- Endpoint identification được bật với thuật toán HTTPS, để hostname của dịch vụ được xác minh trong handshake.
- Kết nối chỉ được gán vào resource sau khi handshake hoàn tất.
- Nếu kết nối hoặc handshake thất bại, socket đang tạo được đóng và lỗi được truyền lên callback.

Ví dụ dùng truststore riêng và giả định định dạng truststore khớp với KeyStore.getDefaultType(). Trong hệ thống thực tế, hãy cấu hình rõ loại keystore, đường dẫn, secret provider, thuật toán và chính sách TLS. Mật khẩu trong ví dụ chỉ để minh họa cách nạp cấu hình; biến môi trường dạng String vẫn có thể tồn tại trong heap. Với bí mật quan trọng, nên lấy từ secret manager theo cơ chế phù hợp và hạn chế thời gian giữ bản sao trong bộ nhớ.

Ví dụ cũng chưa cấu hình client certificate cho mTLS. Nếu server yêu cầu chứng chỉ client, cần nạp keystore chứa private key và chứng chỉ client, tạo KeyManagerFactory, rồi truyền key managers vào tham số đầu tiên của SSLContext.init(). Không dùng truststore thay cho keystore: truststore xác định CA/chứng chỉ mà client tin cậy, còn keystore cung cấp danh tính và private key mà client có thể trình ra.

Trong ví dụ, endpoint identification dùng HTTPS. Nếu kết nối tới một giao thức TLS khác, hãy dùng cơ chế xác minh hostname tương ứng của client hoặc thư viện giao thức đó. Không tắt xác minh hostname để khắc phục lỗi chứng chỉ; cần sửa hostname, SAN hoặc cấu hình tin cậy đúng.

## 7. HTTP client, database và connection pool

Trong ứng dụng thực tế, TLS socket thường được quản lý gián tiếp bởi HTTP client, JDBC driver hoặc broker client. Resource CRaC nên quản lý đối tượng cấp cao nhất mà thư viện công bố là chủ sở hữu lifecycle.

### 7.1. HTTP client

HTTP client có thể giữ connection pool, TLS session cache, DNS cache, executor và các kết nối HTTP/2 đang mở. Sau restore, một client cũ có thể còn tham chiếu tới kết nối mà peer đã đóng hoặc tới SSLContext cũ.

Hướng xử lý:

- Ngừng gửi request mới và chờ request đang chạy kết thúc.
- Đóng hoặc dừng client theo API của phiên bản JDK/thư viện đang dùng.
- Tạo client mới với SSLContext mới nếu truststore, keystore hoặc TLS policy có thể đã thay đổi.
- Phân giải lại hostname và thương lượng ALPN khi kết nối mới được tạo.
- Thực hiện health check trước khi mở readiness.

Không giả định mọi phiên bản java.net.http.HttpClient có cùng API đóng client. Ví dụ, API lifecycle có khác biệt theo phiên bản JDK. Hãy dùng đúng API được cung cấp bởi JDK hoặc thư viện cụ thể.

### 7.2. JDBC và database client

JDBC connection pool có thể giữ các socket TLS tới database. Trước checkpoint, cần drain transaction, đóng connection và pool theo hướng dẫn của pool. Sau restore, tạo pool mới để driver thiết lập kết nối TLS mới.

Nếu database dùng CA hoặc chứng chỉ server được rotate, cần bảo đảm driver nhận truststore mới. Một pool mới nhưng vẫn dùng SSLContext hoặc cấu hình trust cũ có thể tiếp tục thất bại. Kiểm tra cách JDBC driver nạp truststore và SSLContext; một số driver có cấu hình riêng hoặc cache nội bộ.

Transaction đang mở không được bảo đảm tiếp tục sau restore. Hãy hoàn tất hoặc rollback transaction trước checkpoint và dùng transaction ID, idempotency hoặc cơ chế phục hồi phù hợp nếu kết quả commit chưa rõ ràng.

### 7.3. Message broker và service mesh

Broker client có thể giữ TLS connection cùng consumer group, heartbeat và subscription. Trước checkpoint, dừng consumer và xử lý acknowledgment theo chính sách. Sau restore, tạo kết nối mới, xác thực lại, đăng ký subscription và xác minh trạng thái group.

Trong môi trường service mesh, TLS có thể được terminate hoặc khởi tạo lại ở sidecar/proxy. Vòng đời certificate và connection pool có thể thuộc về proxy thay vì ứng dụng. Cần xác định chính xác TLS được kết thúc ở đâu để resource của ứng dụng không cố đóng một tài nguyên do sidecar quản lý.

## 8. Hostname, SNI, DNS và ALPN sau restore

Kết nối TLS không chỉ xác minh CA. Danh tính máy chủ còn gắn với hostname, và handshake có thể thương lượng giao thức ứng dụng.

### 8.1. Hostname verification và SNI

Client cần xác minh tên máy chủ khớp với SAN trong chứng chỉ. Server có thể sử dụng Server Name Indication (SNI) để chọn chứng chỉ phù hợp với hostname client yêu cầu.

Khi reconnect:

- Dùng hostname dịch vụ được cấu hình thay vì một IP cố định nếu kiến trúc yêu cầu định tuyến theo tên.
- Bảo đảm client gửi SNI phù hợp.
- Giữ hostname verification bật.
- Nếu dịch vụ đổi tên hoặc chứng chỉ đổi SAN, cập nhật cấu hình và kiểm thử handshake.

Một kết nối mới tới đúng IP nhưng không gửi đúng SNI hoặc không xác minh hostname vẫn có thể không an toàn.

### 8.2. DNS và load balancer

Trong khoảng JVM dừng, DNS record có thể đổi và load balancer có thể chuyển endpoint sang backend khác. Một client giữ connection cũ không tự phân giải DNS lại. Khi tạo kết nối mới, cần kiểm tra TTL, DNS cache và cách thư viện phân giải hostname.

Không nên giả định rằng tạo socket mới luôn đồng nghĩa với DNS được truy vấn lại; một số HTTP client hoặc resolver có cache riêng. Nếu cần nhận endpoint mới sau restore, hãy kiểm tra và cấu hình cache theo tài liệu của client.

### 8.3. ALPN và phiên bản TLS

Application-Layer Protocol Negotiation (ALPN) cho phép hai phía thương lượng giao thức như HTTP/2 hoặc HTTP/1.1 trong TLS handshake. Server hoặc proxy có thể thay đổi giao thức được hỗ trợ trong lúc JVM dừng. Kết nối mới sẽ thương lượng lại theo cấu hình hiện tại.

Nếu ứng dụng phụ thuộc HTTP/2, gRPC hoặc một protocol cụ thể, cần xác minh kết quả thương lượng sau restore. Đồng thời, chỉ cho phép phiên bản TLS và cipher suite phù hợp với chính sách bảo mật của tổ chức; không hạ cấp giao thức chỉ để làm cho handshake thành công.

## 9. Xử lý lỗi handshake và readiness

Kết nối TLS có thể thất bại sau restore vì nhiều nguyên nhân:

| Lỗi hoặc tình huống | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Certificate expired | Chứng chỉ server hoặc client đã hết hạn | Cấp/triển khai chứng chỉ mới và tạo lại TLS context |
| PKIX path building failed | Truststore không có CA cần thiết hoặc chain không đầy đủ | Cập nhật truststore và xác minh certificate chain |
| Hostname mismatch | SAN không khớp hostname client kết nối | Sửa hostname hoặc chứng chỉ; giữ hostname verification |
| Handshake timeout | Server chưa sẵn sàng, mạng chậm hoặc route thay đổi | Timeout hữu hạn, retry có backoff và health check |
| Peer closed connection | Server, proxy hoặc firewall đã đóng socket cũ | Tạo connection mới và xác minh trạng thái peer |
| Client certificate rejected | Keystore hoặc chứng chỉ mTLS cũ, sai EKU hoặc bị thu hồi | Nạp key material mới và kiểm tra chính sách phía server |
| Session resumption rejected | Ticket hết hạn, cache mất hoặc server thay trạng thái | Cho phép thư viện fallback sang handshake đầy đủ |
| Unknown CA | Server chuyển sang CA chưa được client tin cậy | Cập nhật trust chain từ nguồn tin cậy |
| Protocol/cipher mismatch | Client và server không còn bộ giao thức chung | Đồng bộ TLS policy và cấu hình server/client |
| DNS resolution failure | DNS hoặc endpoint chưa sẵn sàng | Retry có giới hạn và kiểm tra resolver |

afterRestore() có thể chạy trong lúc database, broker hoặc API chưa sẵn sàng. Không nên retry vô hạn trong callback. Hãy dùng timeout, backoff, jitter và một trạng thái readiness rõ ràng. Nếu kết nối TLS là phụ thuộc bắt buộc, instance chỉ nên nhận lưu lượng sau khi handshake và xác minh cần thiết đã thành công.

Nếu một số dịch vụ không bắt buộc cho mọi request, có thể khôi phục chúng bất đồng bộ sau khi JVM restore. Khi đó, readiness cần phản ánh chính xác khả năng xử lý của ứng dụng; không được đánh dấu sẵn sàng khi một luồng nghiệp vụ quan trọng vẫn không thể kết nối.

## 10. Quy trình trước checkpoint và sau restore

Một quy trình tổng quát:

### Trước checkpoint

1. Ngừng nhận request hoặc message mới trên các client TLS sắp được đóng.
2. Drain request, transaction và thao tác đang chạy theo giới hạn thời gian.
3. Hoàn tất hoặc rollback transaction; bảo đảm request có thể retry an toàn nếu kết quả không rõ.
4. Đóng connection pool, HTTP client, broker client hoặc socket theo API lifecycle được hỗ trợ.
5. Giải phóng session và trạng thái xác thực không thể tiếp tục dùng an toàn.
6. Đưa ứng dụng về trạng thái có thể checkpoint.

### Sau restore

1. Đọc lại endpoint, DNS policy, truststore, keystore và secret nếu các cấu hình này có thể thay đổi.
2. Tạo TrustManagerFactory và KeyManagerFactory mới khi cần.
3. Khởi tạo SSLContext mới nếu trust/key material hoặc chính sách session cần được làm mới.
4. Tạo client hoặc connection pool mới.
5. Thực hiện TLS handshake, hostname verification, mTLS và ALPN negotiation.
6. Refresh token tầng ứng dụng và đăng ký lại session/subscription.
7. Chạy health check và chỉ mở readiness khi phụ thuộc bắt buộc đã sẵn sàng.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A[Ứng dụng đang dùng kết nối TLS] --> B[Ngừng nhận request mới]
    B --> C[Drain request và transaction]
    C --> D[Đóng client, pool và socket]
    D --> E[CRaC checkpoint]
    E --> F[Thời gian tạm dừng]
    F --> G[Restore JVM]
    G --> H[Đọc cấu hình và chứng chỉ hiện hành]
    H --> I[Tạo SSLContext/client mới]
    I --> J[TLS handshake và xác minh hostname]
    J --> K[Refresh token và session ứng dụng]
    K --> L[Health check]
    L --> M[Readiness và nhận lưu lượng]
~~~

Thứ tự thực tế phụ thuộc vào quan hệ giữa client, pool, token provider và dịch vụ. Ví dụ, client cần secret manager để tải chứng chỉ thì secret manager phải sẵn sàng trước khi client phục hồi. Nếu nhiều resource phụ thuộc nhau, hãy đăng ký chúng theo thứ tự callback phù hợp.

## 11. Kiểm thử TLS khi khoảng tạm dừng kéo dài

Kiểm thử chỉ với checkpoint và restore ngay lập tức chưa đủ để mô phỏng tình huống vận hành. Hãy thử nhiều khoảng thời gian và thay đổi trạng thái hệ thống bên ngoài trong lúc JVM dừng.

Một số tình huống cần kiểm tra:

- Server đóng idle connection trong lúc JVM dừng. Client có tạo kết nối mới sau restore không?
- Session ticket hết hạn. Client có fallback sang handshake đầy đủ không?
- Server thay chứng chỉ bằng chứng chỉ do CA mới cấp. Client có nạp truststore mới và xác minh đúng không?
- Chứng chỉ client mTLS được rotate. Client có nạp key material mới không?
- Chứng chỉ hết hạn trong thời gian tạm dừng. Kết nối mới có thất bại với lỗi có thể chẩn đoán không?
- Server thu hồi chứng chỉ hoặc thay đổi chính sách xác thực. Client có áp dụng chính sách revocation/session tương ứng không?
- DNS trỏ sang backend mới. Client có phân giải và kết nối đúng endpoint không?
- Load balancer hoặc service mesh thay đổi cấu hình TLS/ALPN. Client có thương lượng lại thành công không?
- Đồng hồ máy thay đổi hoặc bị lệch. Lỗi notBefore/notAfter có được phát hiện và xử lý đúng không?
- Database hoặc broker chưa sẵn sàng sau restore. Ứng dụng có giữ readiness ở trạng thái phù hợp không?
- Request bị gửi lại sau khi không biết chắc kết quả trước checkpoint. Cơ chế idempotency có ngăn tác động trùng không?
- Nhiều replica restore từ cùng checkpoint. Mỗi replica có tạo kết nối và session riêng không?

Ghi nhận thời gian checkpoint, thời gian restore, thời điểm handshake, phiên bản TLS, kết quả ALPN và thông tin chứng chỉ đã được xác minh. Không ghi private key, mật khẩu, token hoặc nội dung nhạy cảm vào log.

## 12. Những giả định cần tránh

| Giả định | Thực tế |
|---|---|
| Giữ socket trong heap nghĩa là kết nối vẫn sống | Peer, NAT, firewall hoặc server có thể đã đóng kết nối |
| TLS session resumption khôi phục socket cũ | Resumption thiết lập kết nối mới và chỉ tối ưu handshake |
| Chứng chỉ hết hạn lập tức cắt mọi kết nối đang mở | Chứng chỉ thường được xác minh trong handshake; kết nối đang tồn tại có thể tiếp tục đến khi bị đóng hoặc chính sách khác kết thúc |
| Thay truststore trên đĩa tự cập nhật SSLContext | TrustManager đã khởi tạo thường giữ trạng thái cũ; cần nạp lại và tạo context mới |
| Tạo socket mới là đủ để nhận chứng chỉ mới | Socket mới vẫn có thể dùng SSLContext và trust/key manager cũ |
| Mọi TLS ticket đều còn hiệu lực sau restore | Ticket có thời hạn và server có thể từ chối hoặc không còn giữ trạng thái |
| Handshake thành công đồng nghĩa token ứng dụng còn hiệu lực | Token, session và quyền truy cập ở tầng ứng dụng có vòng đời riêng |
| TLS 1.3 0-RTT an toàn cho mọi request | Early data có rủi ro replay; thao tác có side effect cần chính sách riêng |
| DNS sẽ tự được làm mới khi restore | Resolver hoặc client có thể cache DNS; cần kiểm tra chính sách cache |
| Có thể bỏ hostname verification để sửa lỗi | Việc đó loại bỏ một lớp xác minh danh tính quan trọng |

## 13. Nguyên tắc thiết kế

- Xem socket TLS và connection pool là tài nguyên có thể mất hiệu lực trong thời gian checkpoint.
- Đóng kết nối theo API của client hoặc pool trước checkpoint; không đóng socket nội bộ mà thư viện vẫn quản lý.
- Tạo kết nối mới sau restore và xác minh hostname.
- Nạp lại truststore/keystore và tạo SSLContext mới khi chứng chỉ, CA hoặc chính sách có thể đã thay đổi.
- Phân biệt truststore (CA được tin cậy) với keystore (private key và danh tính client).
- Xử lý session resumption như một tối ưu có thể thất bại; không phụ thuộc ticket để bảo đảm tính đúng đắn.
- Không dùng 0-RTT cho thao tác nghiệp vụ có side effect nếu chưa có bảo vệ replay phù hợp.
- Refresh token và session ở tầng ứng dụng độc lập với TLS.
- Dùng timeout, retry có giới hạn, backoff và readiness để quản lý dịch vụ chưa sẵn sàng.
- Kiểm thử với thời gian tạm dừng, rotation chứng chỉ, thay đổi DNS và sự cố mạng giống môi trường triển khai.

CRaC giúp JVM tiếp tục nhanh từ checkpoint, nhưng thời gian bên ngoài vẫn trôi và các bên tham gia TLS vẫn có thể thay đổi trạng thái. Ứng dụng cần quản lý riêng vòng đời socket, TLS session, chứng chỉ, trust/key material và token nghiệp vụ. Đóng các kết nối cũ trước checkpoint, tạo lại SSLContext hoặc client khi cần, thực hiện handshake mới và xác minh phụ thuộc trước khi phục vụ sẽ giúp ứng dụng tránh dựa vào những phiên bảo mật đã lỗi thời.
