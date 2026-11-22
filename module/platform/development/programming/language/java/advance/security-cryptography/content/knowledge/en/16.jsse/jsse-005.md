# 16.5. Yêu cầu hoặc đề nghị chứng thư phía khách bằng needClientAuth và wantClientAuth

## 1. Bài toán: server TLS có bắt buộc khách hàng trình chứng thư không?

Trong HTTPS/TLS thông thường, **máy chủ (server)** trình chứng thư để phía **khách (client)** xác minh danh tính server. Client thường **không cần** chứng thư X.509; người dùng có thể đăng nhập ở lớp ứng dụng bằng session, OAuth 2.0, token hoặc cơ chế khác.

Trong **mutual TLS (mTLS)**, server còn **yêu cầu hoặc đề nghị client cung cấp chứng thư**, và dùng cơ chế tin cậy tương ứng để xác minh client certificate. Java Secure Socket Extension (**JSSE**) cho phép cấu hình hai chế độ quan trọng:

- `setNeedClientAuth(true)`: **bắt buộc** client authentication trong TLS handshake. Không có chứng thư/thông tin xác thực client phù hợp thì server **không chấp nhận kết nối TLS**.
- `setWantClientAuth(true)`: server **đề nghị** client authentication. Nếu client không cung cấp chứng thư, handshake **vẫn có thể thành công**; nếu client trình chứng thư, chứng thư đó vẫn phải được kiểm tra theo trust policy.

**Cả hai là chính sách ở phía server**, không phải nút để client “bắt” server đưa chứng thư. Và **cả hai không tự cấp quyền nghiệp vụ** cho client: một certificate đáng tin về mặt mật mã chỉ tạo đầu vào để ứng dụng ánh xạ identity, role, tenant và scope.

Bài này tập trung vào vòng đời các cờ `needClientAuth` và `wantClientAuth` trong JSSE, trường hợp không có/có/sai certificate, vai trò `KeyManager`–`TrustManager`, việc kiểm tra peer bằng `SSLSession`, các khác biệt có thể quan sát ở TLS 1.3, cùng một chương trình **Java 17+** có thể chạy với bốn phép thử TLS thật trên loopback.

### Kết quả mong đợi sau bài

1. Phân biệt **required**, **requested/optional** và **not requested**.
2. Biết cấu hình trên `SSLServerSocket`, `SSLSocket` hoặc `SSLParameters` trước khi handshake.
3. Hiểu vì sao `wantClientAuth` **không** có nghĩa “chấp nhận certificate nào cũng được”.
4. Phân biệt **xác thực client TLS** với **authorization**.
5. Tạo keystore/truststore thử nghiệm bằng `keytool`, kiểm thử bốn tình huống trên JDK 17+.
6. Biết cách đọc `getPeerCertificates()`, xử lý client không xác thực và tránh những cấu hình bỏ qua trust validation.

## 2. Phân biệt server authentication và client authentication

### 2.1. HTTPS một chiều

Mô hình thường gặp:

```text
HTTPS CLIENT                                   TLS SERVER
    |                                            |
    | ----- ClientHello -----------------------> |
    | <----- Server cert / handshake ----------- |
    |                                            |
    | Client xác minh chuỗi CA, hostname/IP,     |
    | thời hạn, EKU và chính sách TLS            |
    |                                            |
    +---- Kênh TLS được thiết lập ---------------+
    |                                            |
    | POST /login, bearer token, session... ---> |
```

Server identity được xác minh qua chứng thư của **server**. Việc client có tài khoản hoặc token đăng nhập ở lớp ứng dụng là chuyện khác.

### 2.2. TLS hai chiều (mutual TLS)

Khi server có yêu cầu nhận dạng client bằng certificate:

```text
TLS CLIENT                                      TLS SERVER
    |                                                |
    | --------- ClientHello ------------------------> |
    | <-------- Server Certificate / handshake ----- |
    | <-------- CertificateRequest (nếu cấu hình) -- |
    |                                                |
    | ---- Client Certificate (nếu có/phù hợp) -----> |
    | ---- Bằng chứng sở hữu private key ----------> |
    |                                                |
    |                                  TrustManager xác minh
    |                                  cert chain / policy
    |                                                |
    +----- TLS handshake thành công hoặc bị từ chối --+
```

Đây là sơ đồ **logic**. Trình tự chính xác của thông điệp TLS khác nhau giữa **TLS 1.2 và TLS 1.3**. Trong TLS 1.3, client có thể gửi thông điệp `Certificate` rỗng khi không có certificate phù hợp; phía server sẽ áp dụng chính sách required/optional. Không nên suy từ thứ tự hình vẽ rằng mọi phiên TLS gửi certificate như nhau.

### 2.3. Client certificate là gì?

Client certificate là chứng thư X.509 có public key; client phải có **private key tương ứng** để tham gia client-authentication handshake. Một file `client.cer` chỉ chứa **public certificate** không đủ làm identity để client trình chứng cứ sở hữu khóa riêng.

Một cấu hình mTLS bình thường cần:

- **Server:** private key + certificate chain của **server**, và **TrustManager** biết tin loại client certificates được cho phép.
- **Client:** **TrustManager** xác minh server certificate; nếu được yêu cầu/đề nghị mTLS, **KeyManager** có private key và client certificate chain tương ứng.
- **Cả hai phía:** cấu hình thuật toán/TLS version, trust anchors, policy sử dụng chứng thư và danh tính endpoint hợp lệ.

## 3. Ba chế độ client authentication

Với accepted `SSLSocket` hoạt động ở **server mode**, có ba trạng thái logic:

| Chế độ | Cấu hình | Khi client **không có** chứng thư | Khi client có chứng thư **được trust và phù hợp** | Khi client **trình** chứng thư nhưng không được trust |
| --- | --- | --- | --- | --- |
| **Không yêu cầu** | `setNeedClientAuth(false)` hoặc `setWantClientAuth(false)` theo trạng thái | Có thể handshake thành công | Server thường không chủ động yêu cầu client cert ở handshake này | Không nên suy diễn: nếu không yêu cầu, client có thể không gửi cert |
| **Đề nghị / optional** | `setWantClientAuth(true)` | **Handshake có thể thành công** nhưng **không có identity mTLS** | Handshake thành công; server có peer certificate đã xác minh | Nếu certificate thật sự được gửi và validation fail, **handshake bị từ chối** |
| **Bắt buộc / required** | `setNeedClientAuth(true)` | **Handshake bị từ chối** | Handshake thành công; client-authentication TLS được thực hiện | **Handshake bị từ chối** |

Các kết quả “thành công” trong bảng còn phụ thuộc các điều kiện TLS khác: server certificate có tin cậy không, hostname có khớp không, version/cipher suite được phép không, và chứng thư client có phù hợp certificate policy không.

**Từ khóa cần nhớ:**

- `need` = **MUST**: không có chứng thư client phù hợp thì không cho handshake server-side hoàn tất.
- `want` = **ASK / OPTIONAL**: không có chứng thư client vẫn có thể cho TLS thành công.
- `want` **không** = “chứng thư sai vẫn chấp nhận”. Nếu đã gửi chứng thư và `TrustManager` từ chối, kết nối phải thất bại theo chính sách an toàn.
- Cờ client-auth không liên quan trực tiếp tới việc client xác minh **server hostname**; đừng bỏ quên kiểm tra HTTPS endpoint chỉ vì đang bật mTLS.

### 3.1. Optional client authentication có điểm nhạy cảm

Nếu server đặt `wantClientAuth(true)` và client không trình chứng thư, ứng dụng có thể vẫn nhận được một kết nối TLS hợp lệ về **mã hóa kênh**, nhưng **không có danh tính được xác thực bằng client certificate**.

Ví dụ hệ thống cho phép cả người dùng thông thường và robot có chứng thư:

```text
TCP/TLS accepted with wantClientAuth=true
                  |
                  v
Server kiểm tra: peer có client certificate đã xác minh?
        | không                              | có
        v                                    v
   Nhánh anonymous/                       Ánh xạ identity
   xác thực khác                           từ cert đáng tin
        |                                    |
   Chỉ cho API public                Kiểm role, tenant, scope
   hoặc yêu cầu login                trước API được bảo vệ
```

Nếu một API quản trị **bắt buộc mTLS**, chỉ đặt `wantClientAuth(true)` là **không đủ**. Phải từ chối phiên không có certificate ngay ở TLS bằng `needClientAuth(true)` (trên listener tương ứng), hoặc có rào chắn bắt buộc và được kiểm thử ở lớp ứng dụng/proxy trước khi thực thi, tùy kiến trúc. Không gắn nhãn “mTLS required” chỉ vì listener có `wantClientAuth`.

### 3.2. Required client authentication cũng chưa phải authorization

`needClientAuth(true)` chứng minh server đã yêu cầu một chứng thư **được trust manager chấp nhận** trong handshake; nó **chưa chứng minh client đó được phép gọi tất cả chức năng**.

Nếu truststore chứa một CA nội bộ cấp chứng thư cho nhiều ứng dụng hoặc nhiều tenant, một certificate hợp lệ của ứng dụng A có thể vẫn thuộc trust domain đó dù đang truy cập API của ứng dụng B.

Sau handshake cần ánh xạ certificate identity (theo policy DNS SAN, URI SAN, subject, issuer, public-key binding...), kiểm tra mục đích clientAuth/EKU, thời hạn, trạng thái thu hồi và cấp quyền theo **danh tính thật sự được hệ thống tin**. Không sử dụng `CN` hoặc `SAN` thô mà không định nghĩa cách xác thực/định danh.

## 4. JSSE dùng API nào để đặt needClientAuth/wantClientAuth?

### 4.1. SSLServerSocket: áp dụng cho kết nối mới được accept

Ví dụ **đoạn mã minh họa**:

```java
SSLServerSocket listener = (SSLServerSocket)
        serverContext.getServerSocketFactory().createServerSocket(8443);

listener.setNeedClientAuth(true); // Client cert bắt buộc.
System.out.println(listener.getNeedClientAuth()); // true
System.out.println(listener.getWantClientAuth()); // false
```

`SSLServerSocket` là **listening socket**; khi `accept()` tạo `SSLSocket` ở server mode, socket mới **kế thừa cấu hình ban đầu** của listener. Khi server gọi `setNeedClientAuth(true)`, client không cung cấp thông tin xác thực sẽ làm TLS negotiation dừng và kết nối bị ngắt theo Javadoc Java 17.

Khi dùng:

```java
listener.setWantClientAuth(true);
```

server chỉ **đề nghị** client authentication và cho phép client không trình chứng thư. Lời gọi đó **ghi đè** cấu hình `setNeedClientAuth` trước đó trên listener.

**Cần tránh:** thay cờ trên listening socket rồi mong những kết nối **đã accept/đã handshake** tự nhận cấu hình mới. Thay listener chỉ ảnh hưởng cách khởi tạo các accepted sockets tiếp theo; với accepted socket, cấu hình cần được đặt **trước initial handshake**. Đối với những session đã thiết lập, không nên trông chờ đổi cờ có thể bắt client xuất trình chứng thư giữa phiên.

### 4.2. SSLSocket ở phía server

Khi cần chính sách riêng từng kết nối:

```java
try (SSLSocket peer = (SSLSocket) listener.accept()) {
    peer.setNeedClientAuth(true); // Trước khi bắt đầu handshake.
    peer.startHandshake();
    // Peer auth/TLS handshake đã được kiểm tra theo cấu hình.
}
```

Đoạn mã phụ thuộc `listener` và `serverContext` đã được tạo; **không phải chương trình độc lập**. Phương thức `SSLSocket.setNeedClientAuth` hoặc `setWantClientAuth` chỉ hữu ích khi socket hoạt động ở **server mode**.

Phân biệt:

- `SSLServerSocket.setNeedClientAuth`: cấu hình **ban đầu cho accepted sockets mới**.
- `SSLSocket.setNeedClientAuth`: cấu hình **accepted socket cụ thể** trước handshake.
- `SSLParameters.setNeedClientAuth`: lưu chính sách để áp vào socket/engine, thường bằng `setSSLParameters(...)`.

Khi phát triển server có nhiều nhóm endpoint, hãy cấu hình listener/port hoặc policy chuyên biệt đã được kiểm soát, không dựa vào việc thay cờ theo dữ liệu client chưa xác thực.

### 4.3. SSLParameters: cần/want là trạng thái loại trừ nhau

Ví dụ:

```java
SSLParameters params = socket.getSSLParameters();
params.setNeedClientAuth(true);
System.out.println(params.getNeedClientAuth()); // true
System.out.println(params.getWantClientAuth()); // false

params.setWantClientAuth(true);
System.out.println(params.getNeedClientAuth()); // false
System.out.println(params.getWantClientAuth()); // true

socket.setSSLParameters(params); // Áp vào socket trước handshake.
```

**Quy tắc theo Javadoc Java 17:**

- `SSLParameters.setNeedClientAuth(...)` **xóa cờ wantClientAuth**.
- `SSLParameters.setWantClientAuth(...)` **xóa cờ needClientAuth**.
- Hai cờ **không cộng dồn**. Nếu vô tình gọi cả hai với `true`, lời gọi sau thay đổi chính sách.
- `SSLServerSocket` và `SSLSocket` cũng có cơ chế override các setting liên quan: gọi `setWantClientAuth(true)` sau `setNeedClientAuth(true)` khiến trạng thái cuối trở thành **want** chứ không còn **need**.

Nếu code cấu hình phân tán trong nhiều lớp (framework, adapter, method cấu hình bảo mật), cần đọc **trạng thái cuối cùng sau khi mọi setter đã chạy** bằng `getNeedClientAuth()` và `getWantClientAuth()`. Một thay đổi cấu hình nhỏ có thể vô tình hạ yêu cầu mTLS từ **required** xuống **optional**.

### 4.4. SSLEngine

Với NIO/Netty hoặc một transport tự quản lý bằng `SSLEngine`, có thể dùng:

```java
SSLEngine engine = sslContext.createSSLEngine();
engine.setUseClientMode(false); // Engine ở phía TLS server.
SSLParameters params = engine.getSSLParameters();
params.setNeedClientAuth(true);
engine.setSSLParameters(params);
```

Đây là đoạn mã minh họa. Phần tạo `SSLEngine`, cấu hình TLS/hostname, buffer, tasks và bắt tay non-blocking cần được thực hiện đầy đủ theo JSSE/transport library. Điều cốt lõi vẫn là **đặt chế độ server và client-auth policy trước handshake**. Nếu dùng framework, phải biết option `clientAuth=REQUIRE/OPTIONAL/NONE` của framework được ánh xạ vào JSSE ở đâu.

## 5. Chứng thư được chấp nhận bằng KeyManager và TrustManager như thế nào?

### 5.1. Hai vai trò dễ bị đảo ngược

Trong `SSLContext.init(KeyManager[], TrustManager[], SecureRandom)`:

- **`KeyManager`** chọn local private key + certificate chain để **chính bên này trình ra** khi giao thức cần.
- **`TrustManager`** xác minh certificate của **peer** (bên kia) khi certificate được trình ra.

Với server mTLS:

| Thành phần server | Cần có | Chức năng |
| --- | --- | --- |
| `KeyManagerFactory` khởi tạo từ `server.p12` | Server private key + certificate chain | Đưa danh tính server cho client; chứng minh sở hữu private key server. |
| `TrustManagerFactory` khởi tạo từ `server-trust.p12` | Các CA/client cert được server tin theo policy | Xác minh chứng thư được client trình ra. |
| `setNeedClientAuth(true)` hoặc `setWantClientAuth(true)` | Cờ policy của server-side socket | Quy định có bắt buộc client certificate trong handshake không. |

Với client:

| Thành phần client | Cần có | Chức năng |
| --- | --- | --- |
| `TrustManagerFactory` từ `client-trust.p12` | Certificate/CA của server được client tin | Xác minh server; **còn phải kiểm hostname/IP** nếu giao thức cần. |
| `KeyManagerFactory` từ `client.p12` | Private key + certificate chain của client (khi có) | Có thể chọn và gửi chứng thư client khi server đề nghị/yêu cầu. |
| `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` | Reference identity từ endpoint client định gọi | Kiểm tên server khi thực hiện HTTPS/TLS theo JSSE. |

**Lỗi phổ biến:** chỉ tạo `server.p12` cho server và bật `needClientAuth(true)`, nhưng không cấu hình truststore để server **tin issuer của client certificate**. Client có chứng thư vẫn có thể bị từ chối.

Ngược lại, client có `client.p12` nhưng **không có** truststore tin server certificate thì client sẽ từ chối **server authentication**; lỗi này độc lập với cấu hình want/need trên server.

### 5.2. Client phải có private key phù hợp, không chỉ certificate công khai

`KeyManagerFactory` chọn certificate chain/private key theo các thuật toán và danh sách acceptable issuers mà server gửi. Nếu không có alias/chứng thư phù hợp, client có thể **không gửi certificate**, dù keystore có một entry khác.

Với `wantClientAuth`, tình huống này có thể khiến handshake **thành công mà không có peer cert** — không có bằng chứng client đã xác thực bằng mTLS. Với `needClientAuth`, server sẽ **từ chối**.

Điều đó khác với “client chắc chắn đã gửi một certificate không được tin cậy”: nếu certificate **được gửi** nhưng trust validation fail, handshake không được tự động cho qua chỉ vì want=optional.

### 5.3. Trust không tự đồng nghĩa “có quyền”

`TrustManagerFactory` theo PKIX/truststore có thể công nhận nhiều client certificates do cùng CA phát hành. Để cho phép một service cụ thể:

- Chọn **identity attribute** và chuẩn ánh xạ ổn định, ví dụ URI SAN của workload theo profile service mesh, hoặc public-key identity được pin trong registry.
- Xác minh issuer/trust anchor và các thuộc tính liên quan (EKU `clientAuth`, key usage, validity, revocation nếu policy áp dụng).
- Ánh xạ certificate → principal ứng dụng → role/tenant/scope.
- Không chỉ so chuỗi `CN` như tên tài khoản tùy ý hoặc cho mọi chứng thư của CA nội bộ quyền admin.
- Cân nhắc certificate rotation: không gắn authorization vào serial number/subject dễ thay đổi nếu kiến trúc cần danh tính ổn định.

### 5.4. Bắt buộc client certificate vẫn không thay thế xác minh server

Client cần xác thực server trước khi gửi dữ liệu nhạy cảm hoặc credential; mTLS **không** cho phép client bỏ hostname verification. Nếu client kết nối theo URL `https://api.example.test`, server certificate phải có SAN phù hợp cho `api.example.test` và PKIX trust path phải được kiểm tra theo policy.

Trong lab dưới đây kết nối theo IP `127.0.0.1`, do đó chứng thư server thử nghiệm chứa **SAN:IP Address 127.0.0.1**. Client gọi `setEndpointIdentificationAlgorithm("HTTPS")` để minh họa kiểm tra endpoint ở lớp JSSE; không có trust-all manager.

## 6. Java 17+ lab: bốn TLS 1.3 handshakes thực sự

Ví dụ này dùng các tiện ích có sẵn trong JDK (`keytool`, `javac`, `java`) và một file Java duy nhất. Chúng ta tạo **bốn PKCS#12 test stores**:

```text
server.p12         -- private key + cert của localhost
client.p12         -- private key + cert của demo-client
server-trust.p12   -- server tin client certificate thử nghiệm
client-trust.p12   -- client tin server certificate thử nghiệm

Client không chứng thư:
  SSLContext.init(null, clientTrustManagers, random)

Client có chứng thư:
  SSLContext.init(clientKeyManagers, clientTrustManagers, random)

Server luôn có:
  SSLContext.init(serverKeyManagers, serverTrustManagers, random)
```

Ở đây chứng thư là **self-signed chỉ cho test**, nhưng mỗi bên **chủ động cài chứng thư bên kia vào truststore riêng**. Đây là cách cố tình tạo test anchors của lab, **không** phải mô hình đề xuất cho production. Trong môi trường thật, cần CA/PKI, provisioning và quản lý vòng đời chứng thư phù hợp.

### 6.1. Tạo chứng thư và truststores bằng keytool

Tạo **thư mục lab mới** và chạy các lệnh sau tại thư mục đó. Các command `keytool` bên dưới viết trên từng dòng để dùng được cả trong shell thông thường lẫn PowerShell (khi đã có JDK trên PATH):

```bash
mkdir client-auth-lab
cd client-auth-lab

keytool -genkeypair -alias server -keyalg RSA -keysize 2048 -validity 365 -dname "CN=localhost, O=TLS Demo, C=US" -ext "SAN=dns:localhost,ip:127.0.0.1" -ext "EKU=serverAuth" -keystore server.p12 -storetype PKCS12 -storepass changeit -keypass changeit -noprompt

keytool -genkeypair -alias client -keyalg RSA -keysize 2048 -validity 365 -dname "CN=demo-client, O=TLS Demo, C=US" -ext "EKU=clientAuth" -keystore client.p12 -storetype PKCS12 -storepass changeit -keypass changeit -noprompt

keytool -exportcert -alias server -keystore server.p12 -storepass changeit -file server.cer

keytool -exportcert -alias client -keystore client.p12 -storepass changeit -file client.cer

keytool -importcert -alias server -file server.cer -keystore client-trust.p12 -storetype PKCS12 -storepass changeit -noprompt

keytool -importcert -alias client -file client.cer -keystore server-trust.p12 -storetype PKCS12 -storepass changeit -noprompt
```

**Cảnh báo:** password `changeit`, self-signed certificates và khóa RSA thử nghiệm trong các lệnh này **chỉ để lab**. Không dùng cho môi trường thật, không commit `*.p12`, `*.jks`, `*.key` vào repository, không gửi private key vào chat/ticket, không dùng test CA làm trust anchor production. Sau lab, xóa thư mục thử nghiệm theo chính sách. Khóa test có thời hạn **365 ngày kể từ lúc sinh**, nên khi làm bài sau đó hãy sinh lại thay vì tái sử dụng keystore đã hết hạn.

Các file `server.cer` và `client.cer` chỉ chứa **chứng thư công khai**, không có private key. Chúng được import vào truststores để phục vụ trust decision; khi client xác thực mình, private key nằm ở `client.p12`.

### 6.2. Chương trình ClientAuthDemo.java

Tạo file `ClientAuthDemo.java` ngay trong thư mục có bốn `.p12`:

```java
import java.io.IOException;
import java.io.InputStream;
import java.net.InetAddress;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLPeerUnverifiedException;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManagerFactory;

public final class ClientAuthDemo {
    private static final char[] PASSWORD = "changeit".toCharArray(); // Test only.
    private record Outcome(boolean accepted, boolean peerCertificate) {}

    private static KeyStore load(Path file) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(file)) {
            store.load(in, PASSWORD);
        }
        return store;
    }

    private static SSLContext context(String identityFile, String trustFile)
            throws Exception {
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(load(Path.of(trustFile)));

        KeyManagerFactory kmf = null;
        if (identityFile != null) {
            kmf = KeyManagerFactory.getInstance(
                    KeyManagerFactory.getDefaultAlgorithm());
            kmf.init(load(Path.of(identityFile)), PASSWORD);
        }

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(kmf == null ? null : kmf.getKeyManagers(),
                tmf.getTrustManagers(), new SecureRandom());
        return context;
    }

    private static Outcome run(SSLContext serverContext,
                               SSLContext clientContext,
                               boolean need) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try (SSLServerSocket listener = (SSLServerSocket)
                serverContext.getServerSocketFactory().createServerSocket(
                        0, 5, InetAddress.getByName("127.0.0.1"))) {
            listener.setSoTimeout(5000);
            listener.setEnabledProtocols(new String[]{"TLSv1.3"});
            if (need) {
                listener.setNeedClientAuth(true);
            } else {
                listener.setWantClientAuth(true);
            }

            Future<Outcome> serverResult = executor.submit(() -> {
                try (SSLSocket peer = (SSLSocket) listener.accept()) {
                    peer.setSoTimeout(5000);
                    peer.startHandshake();
                    boolean hasCertificate;
                    try {
                        peer.getSession().getPeerCertificates();
                        hasCertificate = true;
                    } catch (SSLPeerUnverifiedException noCertificate) {
                        hasCertificate = false;
                    }
                    return new Outcome(true, hasCertificate);
                } catch (IOException handshakeOrSocketFailure) {
                    return new Outcome(false, false);
                }
            });

            try (SSLSocket client = (SSLSocket)
                    clientContext.getSocketFactory().createSocket(
                            "127.0.0.1", listener.getLocalPort())) {
                client.setSoTimeout(5000);
                client.setEnabledProtocols(new String[]{"TLSv1.3"});
                SSLParameters parameters = client.getSSLParameters();
                parameters.setEndpointIdentificationAlgorithm("HTTPS");
                client.setSSLParameters(parameters);
                try {
                    client.startHandshake();
                } catch (IOException expectedForRejectedHandshake) {
                    // We report the server's result, not an early TLS 1.3 client result.
                }
                return serverResult.get(10, TimeUnit.SECONDS);
            }
        } finally {
            executor.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        try {
            SSLContext server = context("server.p12", "server-trust.p12");
            SSLContext withoutCertificate = context(null, "client-trust.p12");
            SSLContext withCertificate = context("client.p12", "client-trust.p12");

            Outcome optionalAbsent = run(server, withoutCertificate, false);
            Outcome requiredAbsent = run(server, withoutCertificate, true);
            Outcome optionalPresent = run(server, withCertificate, false);
            Outcome requiredPresent = run(server, withCertificate, true);

            System.out.println("want + no cert: accepted=" +
                    optionalAbsent.accepted() + ", authenticated=" +
                    optionalAbsent.peerCertificate());
            System.out.println("need + no cert: accepted=" +
                    requiredAbsent.accepted() + ", authenticated=" +
                    requiredAbsent.peerCertificate());
            System.out.println("want + trusted cert: accepted=" +
                    optionalPresent.accepted() + ", authenticated=" +
                    optionalPresent.peerCertificate());
            System.out.println("need + trusted cert: accepted=" +
                    requiredPresent.accepted() + ", authenticated=" +
                    requiredPresent.peerCertificate());
        } finally {
            Arrays.fill(PASSWORD, '\0');
        }
    }
}
```

### 6.3. Chạy chương trình và stdout

```bash
javac ClientAuthDemo.java
java ClientAuthDemo
```

Sau khi các lệnh `keytool` trên hoàn tất, Java program in chính xác:

```text
want + no cert: accepted=true, authenticated=false
need + no cert: accepted=false, authenticated=false
want + trusted cert: accepted=true, authenticated=true
need + trusted cert: accepted=true, authenticated=true
```

**Giải thích bốn dòng:**

1. `want + no cert: accepted=true, authenticated=false`: server yêu cầu mềm. Client không có `KeyManager` chứa client identity nên không trình chứng thư; TLS server-side handshake hoàn tất; `SSLSession.getPeerCertificates()` ném `SSLPeerUnverifiedException`, được chuyển thành cờ `authenticated=false`.
2. `need + no cert: accepted=false, authenticated=false`: server yêu cầu cứng. Client không có chứng thư phù hợp, nên TLS server-side handshake bị từ chối; không có kết nối client-authentication để xử lý request.
3. `want + trusted cert: accepted=true, authenticated=true`: server chỉ đề nghị, nhưng client có private key và cert được server trust, nên client có thể trình chứng thư và TLS server handshake chấp nhận.
4. `need + trusted cert: accepted=true, authenticated=true`: server bắt buộc chứng thư, client có chứng thư được tin; handshake hoàn tất và server đọc được `peerCertificates` đã qua handshake validation.

Đây là các **kết quả từ server**. Demo có một thread riêng xử lý `listener.accept()` và `peer.startHandshake()`, trong khi main thread tạo client connection. Trong TLS 1.3, một số lỗi ở server có thể xuất hiện **sau khi một phía nghĩ rằng bước startHandshake cục bộ của mình đã hoàn tất**; vì vậy code trả kết quả **sau khi nhận Future của server** thay vì coi riêng return của `client.startHandshake()` là bằng chứng server đã cho phép client.

Cách bắt `IOException` và rút gọn thành boolean trong demo chỉ nhằm có stdout ổn định. **Production không nên bỏ qua nguyên nhân TLS failure**; cần ghi loại lỗi không nhạy cảm và có xử lý fail-closed. Thử nghiệm cũng dùng thời gian chờ 5–10 giây để tránh treo vô hạn trong môi trường lab; đó không phải timeout bắt buộc của JSSE.

### 6.4. Những gì chương trình thực sự chứng minh

- Nó mở **kết nối TCP trên 127.0.0.1**, dùng **SSLServerSocket/SSLSocket thực**, không mô phỏng handshake bằng cờ booleans thuần túy.
- Cả hai phía bật `TLSv1.3`; chương trình sẽ lỗi nếu JDK/provider đang dùng không hỗ trợ.
- Server sử dụng `server.p12` để trình chứng thư cho client; client có truststore riêng.
- Server dùng `server-trust.p12` để xác thực client certificate khi client gửi.
- Client bật `setEndpointIdentificationAlgorithm("HTTPS")` và kết nối theo `127.0.0.1`, khớp SAN IP thử nghiệm.
- Sau handshake, server kiểm tra `getPeerCertificates()` để biết peer có một certificate chain được xác minh trong chính phiên TLS hay không.
- Khi client không có identity, `SSLContext` nhận mảng `KeyManager[]` là `null`: client vẫn **xác minh server** bằng `TrustManager[]`, nhưng không có private key để xác thực client.

### 6.5. Những gì chương trình không chứng minh

- Demo **không phải public PKI** và không có CA certificate chain đúng mô hình production; truststores chứa test leaf certificates được import trực tiếp.
- Không có URL thật, không có DNS/public server, không có request HTTP, không có kiểm tra role/tenant/scope sau TLS.
- Nó không tự chứng minh mọi certificate có cùng CA đều được phép; lab tin đúng một certificate ở mỗi hướng để thử hành vi.
- Không kiểm tra thu hồi CRL/OCSP, HSM, certificate rotation, truststore updates hay phân tách credential production.
- Không kiểm thử tình huống **client đã gửi chứng thư thực sự nhưng chain không được tin**: khi JSSE nhìn danh sách acceptable CAs mà không chọn được alias, client có thể **không gửi** chứng thư ngay từ đầu. Vì vậy cần test riêng loại lỗi “untrusted presented certificate” bằng cấu hình lab thích hợp.
- Không bảo đảm rằng mọi phiên bản JDK/provider báo cùng thông điệp exception; kết quả logic required/optional là đặc điểm API, còn phần message/stack trace có thể khác.

## 7. SSLSession: xác định client đã xác thực bằng chứng thư chưa

Sau khi **server-side TLS handshake thành công**, có thể đọc certificate chain của peer:

```java
SSLSession session = peerSocket.getSession();
try {
    Certificate[] chain = session.getPeerCertificates();
    // Ở server mode: peer chính là client.
    // Còn phải ánh xạ danh tính/authorization theo policy.
} catch (SSLPeerUnverifiedException noClientCertificate) {
    // Có thể xảy ra với wantClientAuth; xử lý như chưa xác thực mTLS.
}
```

Đoạn mã minh họa trên cần imports `javax.net.ssl.SSLSession`, `javax.net.ssl.SSLPeerUnverifiedException` và `java.security.cert.Certificate`, đồng thời `peerSocket` là accepted `SSLSocket` của server đã thực hiện handshake thành công.

**Chú ý:**

- `SSLSession.getPeerCertificates()` có thể ném `SSLPeerUnverifiedException` nếu không có certificate-based peer authentication. Đừng gọi rồi giả định luôn có mảng khác rỗng.
- Ở **server-side socket**, peer certificate là **client certificate**. Ở **client-side socket**, peer certificate là **server certificate**. Đừng nhầm ngữ cảnh.
- Trong một TLS session được xác minh bằng trust manager đúng, chain đã được JSSE xem xét theo trust policy. Nhưng chain hiện diện **không thay thế** ánh xạ danh tính/authorization của ứng dụng.
- `session.getPeerPrincipal()` có thể cho biết principal liên quan; tuy nhiên chỉ `CN` hoặc `X500Principal.toString()` thường không đủ làm chính sách định danh cho mọi mô hình mTLS.
- `getLocalCertificates()` (nếu có) nói về chứng thư **của chính bên cục bộ**, khác với `getPeerCertificates()`. Dùng sai sẽ khiến code tưởng client đã xác thực trong khi mới chỉ thấy cert server.

### 7.1. Kiểm soát cả nhánh anonymous của wantClientAuth

Nếu muốn dùng optional mTLS cho hai nhóm API, phải có một quy tắc như:

```text
if TLS handshake failed:
    drop connection
else if verified client identity exists:
    map certificate -> approved principal -> authorized routes/scopes
else:
    restrict to anonymous/public routes or require other authentication
```

Đây là giả mã, không phải Java executable. Không cho phép logic kiểu `if (TLS session exists) allowAdmin()` vì **TLS session thành công với want/no-cert không có nghĩa mTLS identity tồn tại**.

Nếu chỉ một số endpoint yêu cầu chứng thư, còn phần khác cho anonymous, cân nhắc tách listener/hostname có `needClientAuth` riêng để việc enforce chính sách rõ ràng. Thay cờ sau handshake theo URL path **không làm client tự thực hiện lại bước authentication ban đầu**, đặc biệt ở TLS 1.3.

## 8. Tại sao wantClientAuth không có nghĩa chấp nhận mọi certificate?

Cần tách hai loại thất bại:

### A. Không có client certificate

Client có thể không sở hữu private key/client certificate hoặc KeyManager không tìm được alias phù hợp. Với `wantClientAuth`, TLS có thể thành công và ứng dụng nhận **unauthenticated client connection**.

### B. Certificate được gửi nhưng không qua validation

Khi client thực sự trình một certificate chain, server cần kiểm tra thông qua `TrustManager` được cấu hình đúng; ví dụ:

- Certificate không dẫn tới trust anchor mà server chấp nhận.
- Certificate hết hạn, chưa hiệu lực hoặc bị thu hồi theo policy.
- EKU/KeyUsage không phù hợp `clientAuth`.
- Certificate chain hoặc chữ ký không hợp lệ, thuật toán không được phép.
- Các hạn chế issuer/subject/name constraints hay các chính sách mTLS khác không đạt.

Nếu certificate đã được trình và bước xác minh chứng thư thất bại, server **không được** tiếp tục như client anonymous chỉ vì `wantClientAuth(true)`. Optional nghĩa là **có thể không có chứng thư**, không phải “một chứng thư sai cũng được”.

**Rủi ro khi kiểm thử:** JSSE KeyManager có thể không gửi một cert nếu acceptable issuers list không phù hợp. Khi server muốn cert nhưng client không gửi, optional mode có thể thành công. Kết quả đó **không chứng minh** server chấp nhận một cert không được tin. Muốn test “untrusted certificate was presented”, phải có bằng chứng từ handshake trace hoặc cấu hình KeyManager tùy biến test-only để đảm bảo cert thật sự được gửi.

Không tạo `X509TrustManager` “trust-all” để tránh lỗi client certificate. Việc đó làm mất ý nghĩa của cả need và want: một certificate tự ký từ attacker có thể bị xem là “đã xác thực”.

## 9. Need/want và TLS 1.2 so với TLS 1.3

### 9.1. Chính sách required/optional tồn tại ở cả hai

Ý nghĩa chức năng của `setNeedClientAuth` và `setWantClientAuth` không đổi ở cấp JSSE: server yêu cầu hay đề nghị client certificate. Thay đổi nằm ở **cơ chế và thời điểm thông điệp handshake**, alerts và session/resumption.

Với TLS 1.3, server có thể gửi `CertificateRequest` trong initial handshake. Nếu client không gửi certificate khi server yêu cầu, server sẽ từ chối (ví dụ với cảnh báo `certificate_required` theo TLS 1.3). Một số stack có thể báo exception ở các thời điểm khác nhau giữa client và server. Đừng kiểm thử chỉ bằng việc `client.startHandshake()` có trả về hay không; phải kiểm tra **phía server có thực sự hoàn tất/cho phép phiên**.

### 9.2. Không dựa vào TLS renegotiation để “nâng cấp” optional thành required

Một cách làm cũ từng tồn tại là: bắt đầu TLS không có client cert, rồi đến một HTTP route nhạy cảm mới bật required client auth và cố kích hoạt renegotiation. **Không nên thiết kế như vậy.** TLS 1.3 không có renegotiation theo kiểu TLS 1.2; post-handshake authentication có các điều kiện hỗ trợ riêng và **không tự xuất hiện** chỉ vì Java code gọi `setNeedClientAuth(true)` trên socket đã handshake.

Một thiết kế vững hơn:

- Định rõ từ **initial handshake** listener nào bắt buộc mTLS.
- Nếu ứng dụng muốn nâng cấp identity, dùng một kết nối mới có chính sách required hoặc giao thức có xác thực lại được thiết kế/kiểm toán.
- Không cho thao tác nhạy cảm chạy trước khi identity mong muốn được thiết lập và kiểm tra.
- Kiểm soát session resumption, TLS termination ở proxy và caching để không vô tình dùng lại trạng thái authentication không phù hợp.

### 9.3. Cần hiểu đâu là server “thực sự” chấm chứng thư

Trong hệ thống có load balancer, API gateway hoặc service mesh, TLS có thể được **terminate trước khi đến Java backend**. Lúc đó:

```text
Internet client --(mTLS)--> Gateway --(HTTP hoặc TLS mới)--> Java backend
                            |
                            +-- gateway kiểm client cert
```

Backend Java không thể chỉ gọi `SSLSocket.getPeerCertificates()` rồi giả định nó đang nhìn certificate của Internet client nếu TLS ngoài đã kết thúc ở gateway. Một số proxy đưa identity qua header, nhưng header chỉ được tin khi đến từ gateway đã xác thực, được chặn spoofing, có bảo vệ hop-by-hop và policy authorization. Nếu không, attacker có thể tự gửi header giả.

Cũng không thể bật `needClientAuth` ở backend rồi coi đã ép chứng thư cho kết nối **client → gateway** nếu TLS ngoài do gateway quản lý; cần cấu hình đúng điểm TLS termination.

## 10. SSLParameters.setNeedClientAuth và setWantClientAuth: lỗi thứ tự thường gặp

### 10.1. Hai cờ không thể vừa true

```java
SSLParameters p = new SSLParameters();
p.setNeedClientAuth(true);
System.out.println(p.getNeedClientAuth()); // true
System.out.println(p.getWantClientAuth()); // false

p.setWantClientAuth(true);
System.out.println(p.getNeedClientAuth()); // false
System.out.println(p.getWantClientAuth()); // true
```

Nếu có một module cấu hình đặt required trước, rồi module khác đặt optional sau, **chính sách cuối cùng là optional**. Ngược lại cũng vậy.

Hãy kiểm trạng thái **sau khi kết thúc xây dựng cấu hình**, không chỉ grep source code để xem đã có `setNeedClientAuth(true)` ở đâu hay chưa. Ở framework cấp cao, cần kiểm mapping ra JSSE và test handshake negative.

### 10.2. Không phải mọi lớp trong ứng dụng đều tự nhiên ở server mode

Một `SSLSocket` được khởi tạo để gọi API bên ngoài thường là **client-mode**; đặt `setWantClientAuth(true)` trên nó **không** có nghĩa client đang bảo server gửi chứng thư. Server authentication được thực hiện bằng trust manager và endpoint identification của TLS client, còn client certificate (nếu server yêu cầu) được chọn bằng KeyManager.

Phía **server-mode SSLSocket** mới là nơi need/want có tác dụng theo Javadoc. Nếu dùng `SSLEngine`, cần xác định `setUseClientMode(false)` khi vai trò là TLS server.

### 10.3. Không sửa trạng thái sau handshake như cách bắt buộc khách

Đặt client auth policy khi socket chưa bắt đầu handshake. Một khi có phiên đã xác lập, đổi cờ có thể không khiến peer cung cấp certificate ở cùng phiên và hành vi liên quan đến renegotiation không nên dựa vào cho thiết kế mới. Dùng listener/handshake mới có policy đúng.

### 10.4. Không quên cấu hình TrustManager

`setNeedClientAuth(true)` **không** chỉ định CA nào được phép ký client certificates. Đó là trách nhiệm của trust management. Nếu không cấu hình đúng, server có thể từ chối client hợp lệ hoặc chấp nhận phạm vi rộng hơn mong muốn nếu dùng truststore quá rộng/manager sai.

## 11. Thiết kế production với mTLS bắt buộc và optional

### 11.1. Khi nên dùng needClientAuth

- Kết nối service-to-service nội bộ mà policy yêu cầu mọi client phải có workload certificate.
- API quản trị/đặc quyền chỉ truy cập từ máy hoặc service identity được cấp chứng thư.
- Kênh nhận dữ liệu giữa đối tác có đăng ký client certificate và chính sách identity mapping rõ ràng.
- Listener dành riêng cho robot/batch jobs với yêu cầu xác thực ở TLS handshake.

Trong mỗi trường hợp, kiểm tra đủ: TLS client certificate **được tin** và **đúng client identity** cho service đó; sau đó gán quyền cụ thể. `needClientAuth` không thay thế phân quyền ứng dụng.

### 11.2. Khi muốn dùng wantClientAuth

- Một listener phục vụ cả client có mTLS identity và khách anonymous, với **phân tuyến/ủy quyền** rõ ràng sau handshake.
- Giai đoạn chuyển tiếp client certificates, nếu các API nhạy cảm vẫn được **chặn server-side** khi không có identity, và có kế hoạch chuyển sang required.
- Mô hình muốn lấy thêm tín hiệu nhận dạng máy/service bằng certificate nhưng **không mặc định** cho thêm quyền khi thiếu chứng thư.

**Nguy cơ cao:** cấu hình want trong khi marketing/security policy tuyên bố “mọi API đều bắt buộc mTLS”. Bất kỳ client không có cert nào có thể thiết lập TLS; nếu application check thiếu một route, kết nối anonymous có thể đi qua.

Nếu thật sự cần bắt buộc ở mọi đường xử lý, dùng `needClientAuth` hoặc lớp gateway enforcing client certificate tương đương, có negative tests.

### 11.3. Tránh truststore quá rộng

Tin một root CA công khai/bộ CA rộng để xác thực **client machine identity** có thể khiến server chấp nhận những chứng thư không được phát hành theo quy trình tổ chức bạn kỳ vọng. Để mTLS production an toàn, kiểm issuer/policy/OID/EKU, SAN identity, quyền cấp phát, trust rotation và revocation; có thể chọn một CA nội bộ giới hạn cho client certificates thay vì truststore mặc định dùng cho HTTPS server.

### 11.4. Certificate lifecycle và revocation

- Client private key cần bảo vệ: KeyStore có password mạnh, OS secret manager, HSM/TPM nếu threat model yêu cầu; không hardcode credential test.
- Certificate rotation phải tính trước việc cả hai phía cập nhật trust anchors, accepted issuers, identity mapping và overlap phù hợp.
- Nếu private key client bị lộ, cần revoke/disable identity và thay certificate/keys; **want/need không tự biết khóa đã bị đánh cắp**.
- PKIX validity/revocation/algorithm policy phải được cấu hình phù hợp môi trường; đừng tắt kiểm trust/thu hồi chỉ để demo pass.
- Không lấy subject DN do client cung cấp ngoài TLS và tự coi đó là authenticated certificate identity.

## 12. Các lỗi và biểu hiện khi vận hành

| Hiện tượng | Nguyên nhân khả dĩ | Hướng khắc phục |
| --- | --- | --- |
| `needClientAuth=true`, client không có cert, handshake fail | **Đúng thiết kế**: required nhưng không có chứng thư | Cấp client cert/private key hoặc điều chỉnh loại listener theo policy, không tắt trust. |
| `wantClientAuth=true`, client không có cert, handshake thành công | **Đúng thiết kế**: optional | Ở ứng dụng, không cho quyền mTLS khi peer cert vắng mặt. |
| Client có `client.p12` nhưng server vẫn thấy không có certificate | KeyManager không chọn được alias, issuer list/algorithm không phù hợp, private key không được load | Kiểm client key entry, certificate chain, acceptable issuers, handshake trace và KeyManager. |
| Client cert được trình nhưng handshake fail | CA không được trust, expired, EKU/key usage không đúng, chain invalid | Cấu hình truststore và PKIX policy, phát hành lại cert hợp lệ. |
| Server certificate được trình nhưng client từ chối | Client truststore không tin server hoặc SAN hostname/IP không khớp | Sửa server cert/truststore/reference identity, không bỏ hostname check. |
| `SSLPeerUnverifiedException` khi gọi `getPeerCertificates()` trên server | Không có peer certificate-based authentication | Xử lý nhánh anonymous của optional mTLS; nếu bắt buộc thì xem lại listener/policy. |
| `SSLHandshakeException` với `bad_certificate` hoặc alert khác | Trust/certificate/handshake policy fail; thông điệp tùy provider | Ghi nguyên nhân an toàn, kiểm thực tế handshake logs. |
| Server vẫn cho anonymous dù đã gọi `setNeedClientAuth(true)` | Có nơi gọi `setWantClientAuth(true)` sau đó; cấu hình đúng ở sai socket; proxy terminate TLS | Kiểm trạng thái cuối, TLS termination point và negative handshake test. |
| `needClientAuth` bật cho backend nhưng API gateway vẫn cho public clients | TLS client ngoài terminate ở gateway | Bật client-auth ở gateway hoặc bảo vệ backend hop đúng. |
| Một số client authenticate, một số không với want | Chỉ một phần client có private key và certificate chain phù hợp | Thiết kế identity fallback/authorization rõ, không giả định tất cả đã mTLS. |
| Certificate client hợp lệ nhưng bị từ chối API | TLS trust thành công nhưng authorization application thiếu role/scope | Xem mapping identity và policy, không hạ TLS. |
| Nâng want lên need nhưng kết nối cũ còn hoạt động | Session/handshake đã tạo trước thay đổi | Cắt/đóng session cũ theo policy hoặc áp dụng quy trình chuyển tiếp an toàn. |

### 12.1. Debug JSSE mà không làm yếu bảo mật

Trong lab, có thể bật chẩn đoán TLS handshake bằng JVM flag:

```bash
java -Djavax.net.debug=ssl:handshake -cp . ClientAuthDemo
```

Tùy hệ thống, output có thể rất dài và có chi tiết nhạy cảm (hostname, certificate chain, tên định danh, TLS metadata). Chỉ bật khi được phép, bảo vệ log và **không đưa private keys, passwords hay secrets** vào log. Chỉ dùng trên máy thử nghiệm, không mặc định mở trên production.

Cần phân biệt:

- **Client không trình certificate**: với want có thể tiếp tục; với need bị từ chối.
- **Server không trust client certificate đã trình**: bị từ chối, không “rơi xuống anonymous” như một thiết kế an toàn.
- **Client không trust server**: client từ chối, không liên quan directly need/want.
- **Application không cấp quyền**: TLS handshake vẫn có thể thành công; HTTP API trả 401/403 theo policy — đây là lớp khác.

Không khuyên cấu hình `trustAll()` hoặc `HostnameVerifier((h,s)->true)` khi debug. Cách sửa đúng là sửa danh tính/chứng thư/truststore hoặc policy.

## 13. Test matrix nên có trước khi phát hành

| Server mode | Client identity | Trình chứng thư? | Kết quả TLS server-side mong đợi | Identity trong ứng dụng |
| --- | --- | --- | --- | --- |
| None | Không có | Không yêu cầu | TLS có thể thành công | Không có mTLS identity. |
| Want | Không có keypair | Không | **Thành công** nếu các điều kiện khác đạt | Anonymous / xác thực khác, không mTLS identity. |
| Need | Không có keypair | Không | **Thất bại** | Không xử lý request. |
| Want | Có cert được trust | Có | **Thành công** | Có certificate identity, vẫn kiểm authorization. |
| Need | Có cert được trust | Có | **Thành công** | Có certificate identity, vẫn kiểm authorization. |
| Want | Có cert thật sự gửi nhưng không được trust | Có | **Thất bại** | Không xử lý request. |
| Need | Có cert thật sự gửi nhưng không được trust | Có | **Thất bại** | Không xử lý request. |
| Need | Có cert đúng CA nhưng sai role/tenant | Có | TLS có thể thành công | **Application phải từ chối** nếu không được phép. |
| Want | Có cert nhưng KeyManager không chọn được alias | Không | TLS có thể thành công | Không có mTLS identity. |
| Need | Client có cert nhưng client không trust server | Có thể chưa gửi | TLS thất bại do server identity/trust | Không xử lý request. |

**Đừng chỉ test positive case** `need + valid cert`. Ca âm **need + no cert** bắt buộc phải bị chặn; ca **want + no cert** bắt buộc không bị gán mTLS identity. Khi policy cho một route yêu cầu mTLS, phải test request qua **mọi điểm TLS termination**, không chỉ test một class JSSE riêng lẻ.

### 13.1. Assertions nên đưa vào integration test

1. `getNeedClientAuth()`/`getWantClientAuth()` phản ánh **trạng thái cuối cùng** của listener/engine.
2. Không có client cert + required → server-side TLS handshake **không thành công**.
3. Không có client cert + optional → server-side TLS handshake **có thể thành công**; `getPeerCertificates()` báo không có authenticated peer.
4. Client cert hợp lệ và được tin → handshake thành công; server nhận được peer cert.
5. Client cert sai hoặc bị thu hồi → handshake từ chối theo trust policy, kể cả optional khi cert thực sự được gửi.
6. Client cert hợp lệ nhưng không có quyền của tenant → application trả từ chối, không xem chứng thư là quyền admin chung.
7. Server cert có SAN sai → client handshake fail dù server yêu cầu client cert đúng.
8. Rotation và cập nhật truststore không tạo cửa sổ chấp nhận alias/issuer không mong muốn.
9. Proxy/gateway chặn header giả danh identity từ nguồn không đáng tin.
10. TLS 1.3 session reuse/connection pooling không tái sử dụng authentication state sai cho protected routes.

## 14. FAQ và những hiểu lầm cần loại bỏ

**Hỏi: `wantClientAuth(true)` khác `needClientAuth(true)` đúng một chữ “không bắt buộc” thôi sao?**

Khác nhau chính là **hành vi handshake khi client không cung cấp certificate**. Với want, server có thể chấp nhận kết nối không có chứng thư, nên **lớp ứng dụng bắt buộc phân biệt rõ anonymous**. Với need, server không nên cho handshake hoàn tất nếu client không thể xác thực bằng certificate phù hợp.

**Hỏi: Khi want=true, nếu client gửi certificate hết hạn hoặc không tin cậy, server có tiếp tục như anonymous không?**

Không nên. Khi **certificate đã được gửi và validation thất bại**, handshake phải thất bại. Optional nghĩa là không cần xuất trình chứng thư, chứ không phải được phép trình chứng thư sai. Tuy nhiên khi KeyManager không chọn được alias, client có thể **không gửi cert**, lúc đó muốn kết luận cần xem handshake trace.

**Hỏi: Khi need=true, tôi có thể bỏ KeyManager của server vì server chỉ kiểm client cert không?**

Không. Trong mô hình TLS server authentication tiêu chuẩn, server cũng cần local identity/private key để client xác minh server; mTLS thêm bước **client certificate**, không thay thế server certificate.

**Hỏi: `serverTruststore` cần chứa những gì?**

Những trust anchors hoặc certificates mà **server được phép tin để xác minh client** theo policy; có thể là CA nội bộ chuyên cấp client cert, không nhất thiết cùng store với truststore mà client dùng để tin server. Nhưng trust anchor rộng chưa đủ: cần identity/authorization mapping.

**Hỏi: Client có `client.cer` trong classpath thì đã được mTLS chưa?**

Chưa. Client phải có private key tương ứng và KeyManager có thể chọn credential phù hợp. Một public certificate file không tạo bằng chứng sở hữu khóa riêng.

**Hỏi: `getPeerCertificates()` cho biết điều gì?**

Nó cho biết certificate chain của peer trong session được xác minh bằng certificate authentication (với trust manager phù hợp); có thể ném `SSLPeerUnverifiedException` nếu peer không được xác minh theo cách đó. Nó không tự đánh giá ứng dụng có nên cấp role hay không.

**Hỏi: Có nên mở wantClientAuth ở mọi API trước, đến route admin mới đổi need không?**

Không nên dựa vào đổi cờ giữa phiên TLS. Đặt chính sách required trên listener phù hợp **ngay từ handshake**, hoặc thiết kế xác thực/ủy quyền cấp ứng dụng và gateway thật chặt. TLS 1.3 không có renegotiation kiểu cũ để tự nâng cấp như vậy.

**Hỏi: Nếu server TLS nằm sau load balancer, đặt needClientAuth trong Java có kiểm Internet client không?**

Không chắc. Nếu TLS terminate ở gateway, Java chỉ thấy kết nối tiếp theo từ gateway (hoặc plain HTTP). Cần enforce client certificate **ở đúng điểm kết thúc TLS** và truyền identity đã xác thực qua boundary đáng tin, có chống spoofing.

**Hỏi: Nếu tôi bật needClientAuth thì server certificate có tự được xác minh DNS SAN không?**

Không. Việc **client kiểm server** là hướng khác. HTTPS client cần trust path và endpoint identification phù hợp, không liên quan trực tiếp đến cờ server yêu cầu client cert.

## 15. Checklist triển khai

- [ ] Có quyết định rõ **NONE**, **WANT** hay **NEED** cho từng listener/port/route/proxy.
- [ ] Với API cần mTLS cứng, server-side handshake phải **từ chối client không có cert**.
- [ ] Đã kiểm tra trạng thái cuối của `getNeedClientAuth()` và `getWantClientAuth()`; không có cấu hình đè ngược ngoài ý muốn.
- [ ] Server có KeyManager/certificate/private key hợp lệ; client có TrustManager tin server và hostname verification đúng.
- [ ] Server có TrustManager tin đúng client issuers/certificates theo PKIX policy; không dùng accept-all.
- [ ] Client có private key/cert chain nếu muốn hoặc bắt buộc xác thực bằng certificate.
- [ ] Chứng thư client có EKU/KeyUsage, hiệu lực, policy/revocation phù hợp; root CA được phân phối qua kênh tin cậy.
- [ ] Khi want/optional, ứng dụng xử lý **không có peer certificate** như anonymous hoặc yêu cầu xác thực khác.
- [ ] Khi có peer cert, ứng dụng còn kiểm **identity mapping, authorization, role, tenant và scope**.
- [ ] Không cố nâng cấp optional thành required sau khi handshake mà thiếu giao thức hỗ trợ rõ ràng.
- [ ] Đã test bốn trường hợp căn bản và những ca client cert sai/hostname server sai.
- [ ] Truststore/keystore/password demo không được copy vào production; private keys không nằm trong repo.
- [ ] Đã xác định điểm TLS termination của gateway/proxy/service mesh; header identity không thể bị client giả.
- [ ] Có giám sát và kế hoạch rotation/revocation các client certificates, session/connection pooling và fail-closed.

## 16. Bài tập tự luyện

1. Phân biệt chính xác `setNeedClientAuth(true)` và `setWantClientAuth(true)` trong trường hợp client không có chứng thư.
2. Vì sao `wantClientAuth` **không** là cơ chế cho qua certificate bị TrustManager từ chối?
3. Server có `needClientAuth=true` nhưng không có truststore phù hợp; client có certificate. Handshake có chắc thành công không?
4. Trong `SSLContext.init(keyManagers, trustManagers, random)`, bên server dùng từng array để làm gì? Bên client thì sao?
5. Nếu client chỉ có `client.cer` mà không có private key, nó có thể trình chứng cứ sở hữu khóa riêng không?
6. Nếu `SSLParameters` gọi `setNeedClientAuth(true)` rồi `setWantClientAuth(true)`, trạng thái cuối là gì?
7. Vì sao `SSLSession.getPeerCertificates()` có thể ném `SSLPeerUnverifiedException` khi want=true?
8. Vì sao `needClientAuth=true` không cho biết role, tenant, scope hay quyền đọc database của client?
9. Khi TLS terminate tại gateway, backend Java cần tin thông tin client identity từ đâu và chống giả mạo thế nào?
10. TLS 1.3 có cho phép bạn chỉ đổi cờ trên socket đã handshake để buộc client trình cert ngay lập tức không? Vì sao không nên dựa vào điều đó?
11. Nếu server chỉ xác minh client cert nhưng HTTPS client tắt hostname verification cho server, còn rủi ro gì?
12. Bạn sẽ viết negative tests nào để chứng minh một API “mTLS required” thật sự không mở cho kết nối anonymous?

**Bài tập A:** chạy `ClientAuthDemo` và ghi lại bốn dòng. Sau đó đổi code từ `listener.setWantClientAuth(true)` thành `listener.setNeedClientAuth(true)` trong mọi trường hợp; dự đoán kết quả khi client không có cert.

**Bài tập B:** thay `server-trust.p12` bằng một truststore test không chứa issuer của `client.p12`. Kiểm handshake có thất bại hay client có thể chọn không gửi cert; dùng `javax.net.debug=ssl:handshake` trong môi trường test để phân biệt.

**Bài tập C:** thêm một local HTTP handler phía sau TLS với route `/public` và `/admin`. Khi listener ở want mode, đảm bảo `/public` cho phép client anonymous theo policy, còn `/admin` từ chối nếu session không có client certificate identity đáng tin và quyền admin. Sau đó so sánh với listener need mode.

**Bài tập D:** tạo một cert client thứ hai được cấp bởi cùng CA test nhưng ánh xạ sang tenant khác. Chứng minh `needClientAuth` có thể chấp nhận certificate theo trust policy nhưng authorization vẫn từ chối route của tenant không tương ứng.

**Bài tập E:** giả lập một lần đổi cấu hình bất cẩn: gọi need=true ở lớp cấu hình bảo mật rồi want=true ở lớp framework. Viết assertion `getNeedClientAuth() == true` tại thời điểm listener sẵn sàng nhận kết nối để phát hiện regression.

## 17. Tài liệu API chính thức

- [SSLServerSocket — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLServerSocket.html): `setNeedClientAuth`, `setWantClientAuth`, getter, trạng thái ba lựa chọn và ý nghĩa trên accepted sockets.
- [SSLSocket — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html): cấu hình server-side socket, `startHandshake` và `getSSLParameters`.
- [SSLParameters — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): `setNeedClientAuth` xóa want flag, `setWantClientAuth` xóa need flag, `setEndpointIdentificationAlgorithm`.
- [SSLContext — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html): `init(KeyManager[], TrustManager[], SecureRandom)` và TLS socket factories.
- [SSLSession — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSession.html): `getPeerCertificates()`, `getPeerPrincipal()` và `SSLPeerUnverifiedException`.
- [KeyManagerFactory — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html): sử dụng key stores/private keys để chọn local identity.
- [TrustManagerFactory — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): tạo trust managers từ truststore.
- [X509ExtendedTrustManager — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/X509ExtendedTrustManager.html): xác minh chứng thư theo TLS peer/socket/engine context.
- [Java Secure Socket Extension (JSSE) Reference Guide — Java SE 17](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): mô hình key/trust managers, TLS 1.3 và lập trình SSL/TLS.
- [RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446): CertificateRequest, client authentication, certificate_required alert và khác biệt TLS 1.3.
