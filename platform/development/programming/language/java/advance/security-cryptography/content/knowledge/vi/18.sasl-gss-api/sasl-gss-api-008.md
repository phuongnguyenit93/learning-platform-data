# 18.8. SPNEGO, ủy quyền credential và ranh giới bảo vệ của từng cơ chế

## Mục tiêu học tập

Sau bài này, bạn có thể giải thích SPNEGO chọn cơ chế xác thực như thế nào; phân biệt xác thực, ủy quyền truy cập và **chuyển giao thông tin xác thực (credential delegation)**; nhận biết mức bảo vệ thật sự của Kerberos/GSS-API, SASL GSSAPI, HTTP Negotiate và TLS; đồng thời cấu hình một luồng Java GSS-API theo nguyên tắc tối thiểu quyền. Trọng tâm là **ranh giới tin cậy của từng bước**, đặc biệt với ứng dụng nhiều tầng (frontend → backend).

> Thuật ngữ: `initiator` là phía mở ngữ cảnh bảo mật (thường là client), `acceptor` là phía nhận (thường là service). `Credential` là khả năng chứng minh danh tính trong một cơ chế; nó có thể là ticket/khóa hay đối tượng đại diện cho chúng, **không đồng nghĩa mật khẩu**. `Delegation` cho phép một service dùng credential được ủy quyền để xác thực tiếp với service khác dưới danh tính người dùng, tùy cơ chế và chính sách.

## 1. Đặt SPNEGO đúng tầng

| Thành phần | Vai trò chính | Không tự bảo đảm |
| --- | --- | --- |
| **GSS-API / JGSS** (`org.ietf.jgss`) | API thống nhất để lập security context, xác thực đối tác và tùy cơ chế dùng MIC/wrap bảo vệ bản tin | Không tự vận chuyển token trên mạng, không quyết định quyền nghiệp vụ |
| **Kerberos V5 GSS mechanism** | Chứng minh danh tính bằng ticket/khóa phiên; có thể hỗ trợ xác thực hai chiều, kiểm tra toàn vẹn, mã hóa từng bản tin | Không tự mã hóa toàn bộ HTTP/TCP; không cấp quyền truy cập dữ liệu |
| **SPNEGO** | Cơ chế giả (pseudo-mechanism) để hai phía chọn một GSS mechanism chung | Không là thuật toán mật mã ứng dụng; không tự cấp quyền hay delegation |
| **HTTP Negotiate** | Chở các token GSS/SPNEGO qua header HTTP trong chuỗi challenge/response | Không bảo vệ HTTP headers/body; không tự bật TLS |
| **SASL GSSAPI** | Cơ chế SASL dùng Kerberos V5 GSS-API cho giao thức như LDAP; có thể thương lượng tầng `auth`/`auth-int`/`auth-conf` | Không phải SPNEGO; không đồng nghĩa mọi luồng dữ liệu đã được bảo vệ |
| **TLS** | Bảo vệ kết nối vận chuyển: mã hóa, toàn vẹn và xác thực endpoint theo chứng chỉ/cấu hình | Không mặc nhiên biết user Kerberos; không tự chuyển quyền qua reverse proxy |
| **Application authorization** | Kiểm tra principal đã xác thực được phép làm gì trên tài nguyên nào | Không thể thay bằng thành công của handshake SPNEGO |

**Ba câu hỏi khác nhau:** (1) “Ai đang kết nối?” là authentication. (2) “Người ấy được làm gì?” là authorization. (3) “Service trung gian có được đại diện người ấy kết nối nơi khác?” là credential delegation. Trả lời “đã SSO” không đủ cho (2) hoặc (3).

### OID và tên thường gặp

- Kerberos V5 GSS mechanism: `1.2.840.113554.1.2.2`.
- SPNEGO: `1.3.6.1.5.5.2`.
- GSS host-based service name ví dụ `HTTP@api.example.com`; cơ chế Kerberos thường ánh xạ sang service principal `HTTP/api.example.com@REALM`. Tên service, FQDN, realm và keytab phải thống nhất với KDC.
- Tên SASL `GSSAPI` theo RFC 4752 chỉ **Kerberos V5**, dù GSS-API nói chung hỗ trợ nhiều cơ chế. Tên HTTP `Negotiate` là tên scheme HTTP, không phải tên một principal hay một cipher.

Không đồng nhất một OID đã *yêu cầu* với cơ chế cuối cùng đã *thiết lập*. Khi chọn SPNEGO, xác thực phải đi tới ngữ cảnh hoàn tất; sau đó mới kiểm tra cơ chế thực, tên đối tác và các trạng thái bảo vệ mà triển khai cung cấp.

## 2. SPNEGO thương lượng cơ chế như thế nào?

RFC 4178 mô tả SPNEGO như một lớp thương lượng có bảo vệ nằm trên GSS-API:

1. Initiator tạo `NegTokenInit` chứa danh sách các cơ chế nó hỗ trợ theo thứ tự ưu tiên; có thể kèm **optimistic token** của cơ chế ưu tiên để giảm số lượt đi-về.
2. Acceptor chọn một cơ chế nằm trong danh sách mà nó hỗ trợ hoặc từ chối. Phản hồi `NegTokenResp` có trạng thái như `accept-incomplete`, `accept-completed`, `reject` hay `request-mic` cùng token của cơ chế đã chọn nếu cần.
3. Hai phía trao đổi tiếp token cho cơ chế bên dưới (ví dụ Kerberos AP-REQ/AP-REP) đến khi ngữ cảnh hoàn tất. Không được coi một token khởi đầu hay HTTP 401 đơn lẻ là bằng chứng xác thực xong.
4. Khi cơ chế đã chọn cung cấp integrity, SPNEGO dùng `mechListMIC` trong các trường hợp RFC yêu cầu để bảo vệ danh sách cơ chế khỏi sửa đổi/downgrade. MIC có thể là tùy chọn khi sự lựa chọn đã là ưu tiên của cả hai phía; nếu cơ chế không có integrity thì lớp MIC này không có sẵn.

`mechListMIC` bảo vệ **quá trình chọn cơ chế**, không mã hóa payload của ứng dụng. Nếu policy bắt buộc Kerberos thì phải từ chối các kết quả khác, dù SPNEGO thương lượng “thành công”. Đừng tự bật fallback sang cơ chế yếu hơn khi Kerberos thất bại.

### Ví dụ luồng HTTP Negotiate

```text
Browser/Java client                 Server HTTP (acceptor)        KDC
        | GET /private                     |                       |
        |--------------------------------->|                       |
        | 401 WWW-Authenticate: Negotiate  |                       |
        |<---------------------------------|                       |
        | lấy ticket cho HTTP/server       |                       |
        |<------------------------------------------------------->|
        | Authorization: Negotiate <base64 GSS token>              |
        |--------------------------------->|                       |
        |<---- 401/200 + WWW-Authenticate: Negotiate <token>? ----|
        | tiếp tục initSecContext() cho tới khi established       |
        |<================================>|                       |
        |     application authorization sau authentication         |
```

Đây là luồng khái quát: có thể có thêm vòng trao đổi; token cuối từ server đôi khi đi cùng phản hồi 200 và **client vẫn phải xử lý**. `Authorization: Negotiate` chứa token nhị phân đã Base64 hóa, **không phải** “Bearer token” tùy ý tái sử dụng. Server phải kiểm tra context, principal, target service và chính sách truy cập trước khi trả dữ liệu riêng tư.

Theo RFC 4559, HTTP Negotiate phục vụ authentication; nó không bảo vệ các HTTP header/body. Vì vậy triển khai HTTP thực tế cần **HTTPS/TLS** (và TLS đến từng hop nhạy cảm), giới hạn nơi nhận token, chống ghi log token và bảo vệ phản hồi HTTP theo chính sách.

### SPNEGO có phải Kerberos không?

Không. SPNEGO là bộ chọn; Kerberos có thể là cơ chế được chọn. Một số hệ sinh thái SPNEGO/HTTP Negotiate có thể tương tác với NTLM, nhưng tập cơ chế thực tế phụ thuộc provider/nền tảng. Nhà cung cấp SunJGSS trong JDK chủ yếu triển khai Kerberos và SPNEGO trên Kerberos; **không suy ra** Java mặc định sẽ hỗ trợ NTLM qua JGSS. Nếu ứng dụng yêu cầu Kerberos, hãy cấu hình allow-list và kiểm tra kết quả thiết lập; đừng dựa vào chuỗi “Negotiate” ở header làm bằng chứng cơ chế đã chọn.

## 3. Credential delegation: cho phép làm gì và không cho phép làm gì?

Xét luồng ba tầng:

```text
Alice (initiator)  -- GSS context A -->  Frontend (acceptor)
                                           |
                                           | GSS context B tới backend
                                           | dùng delegated credential của Alice
                                           v
                                        Backend
```

Ở context A, Alice xác thực với Frontend. Nếu Alice **chủ động yêu cầu**, cơ chế **hỗ trợ**, credentials **có khả năng chuyển giao** và policy **cho phép**, frontend có thể nhận một `GSSCredential` ủy quyền. Sau đó frontend tạo context B tới Backend dưới danh tính Alice. Backend vẫn phải xác thực frontend/ủy quyền, và **tự đánh giá Alice được làm gì**. Frontend nhận được credential có thể trở thành điểm rủi ro lớn: nếu bị chiếm quyền, kẻ tấn công có thể lạm dụng khả năng đại diện người dùng trong thời hạn và phạm vi được cấp.

Điều kiện trong thực tế phụ thuộc Kerberos và môi trường: ticket có khả năng forward (`forwardable`), chính sách client/KDC/service, thuộc tính delegation của service, cross-realm trust, credential cache và provider. Yêu cầu delegation trong API **không bảo đảm** đã được cấp. Trường hợp không có delegation là kết quả bình thường, không nên tự động “sửa” bằng tài khoản service toàn quyền.

### Phân biệt các loại quyền

| Khái niệm | Ví dụ | Điều cần nhớ |
| --- | --- | --- |
| Authentication | Alice đăng nhập vào Frontend bằng Kerberos | Chứng minh danh tính trong context A |
| Authorization | Frontend cho Alice đọc báo cáo số 42 | Quy tắc ứng dụng; Kerberos không ra quyết định nghiệp vụ |
| SASL authorization identity (`authzid`) | Client yêu cầu hành động theo một tên authorization nhất định | Server phải kiểm tra quyền ủy nhiệm; không phải GSS credential delegation |
| GSS credential delegation | Frontend dùng `getDelegCred()` để gọi Backend với credential được chuyển giao | Cho phép xác thực tiếp; phải giới hạn vòng đời, đích và quyền |
| Proxy identity/headers | Gateway gửi `X-User` cho microservice | Chỉ đáng tin khi có quan hệ tin cậy, xác thực và bảo vệ hop gateway → service |
| Kerberos constrained delegation | Cơ chế ví dụ S4U2proxy giới hạn service đích | Là mô hình cấu hình/protocol riêng; không đồng nhất với `requestCredDeleg(true)` trong JGSS |

Đừng nhầm delegation với “forward lại header `Authorization: Negotiate`”. Token Kerberos được tạo cho một target/context; gửi nguyên token sang service thứ hai không biến nó thành credential cho service thứ hai. Tương tự, tên `authzid` trong SASL không cho phép client tự lấy quyền của người dùng khác nếu server kiểm tra đúng.

### Quy tắc thiết kế delegation an toàn

1. Mặc định **không yêu cầu** delegation. Chỉ bật cho một luồng nghiệp vụ có nhu cầu rõ và người dùng/administrator cho phép.
2. Ràng buộc service đích (SPN/FQDN), principal được chấp nhận, phạm vi action và quyền backend. Ưu tiên constrained delegation hoặc cách thức cấp quyền phạm vi hẹp khi nền tảng hỗ trợ.
3. Sau khi context A hoàn tất, kiểm tra `getCredDelegState()`; acceptor chỉ gọi `getDelegCred()` sau khi established. `null` nghĩa là không có credential đã chuyển giao.
4. Không log, serialize ra JSON, lưu DB hoặc chuyển qua message queue credential/ticket. Không gộp credential của nhiều người dùng vào pool toàn cục. Đóng context và `dispose()` credential khi hết sử dụng.
5. Authorization ở Backend phải dùng identity đã xác thực tại Backend, không tin chuỗi tên do Frontend tự khai. Có audit theo principal, service đích và hành động, tránh ghi token hoặc secret.
6. Cần kế hoạch khi không được delegation: trả lỗi nghiệp vụ rõ ràng hoặc dùng flow cấp quyền khác được thiết kế riêng. Không tự “fallback” sang quyền cao hơn.

## 4. Java 17+: thiết lập context SPNEGO và kiểm tra điều kiện

API chuẩn: module `java.security.jgss`, package `org.ietf.jgss`. Class `GSSManager` tạo `GSSName`, `GSSCredential`, `GSSContext`. JGSS **không truyền token qua mạng**; ứng dụng hoặc HTTP/SASL library phải đóng gói/gửi/nhận đúng theo giao thức.

Ví dụ dưới đây là **chương trình Java 17 độc lập, biên dịch/chạy được** để xác nhận OID và cung cấp hàm tạo context phía client. Hàm tạo context chưa thực hiện handshake; kết nối Kerberos thực cần KDC, principal, credential và kênh trao đổi token.

```java
// SpnegoContextSetup.java
import org.ietf.jgss.GSSContext;
import org.ietf.jgss.GSSException;
import org.ietf.jgss.GSSManager;
import org.ietf.jgss.GSSName;
import org.ietf.jgss.Oid;

public final class SpnegoContextSetup {
    private static final Oid SPNEGO = oid("1.3.6.1.5.5.2");
    private static final Oid KERBEROS = oid("1.2.840.113554.1.2.2");

    private SpnegoContextSetup() {}

    private static Oid oid(String value) {
        try {
            return new Oid(value);
        } catch (GSSException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    // Gọi trong môi trường đã có Kerberos credentials phù hợp.
    public static GSSContext createClient(String host, boolean allowDelegation)
            throws GSSException {
        GSSManager manager = GSSManager.getInstance();
        GSSName target = manager.createName(
                "HTTP@" + host, GSSName.NT_HOSTBASED_SERVICE);
        GSSContext context = manager.createContext(
                target, SPNEGO, null, GSSContext.DEFAULT_LIFETIME);

        // Chỉ có hiệu lực khi gọi trước initSecContext() lần đầu.
        context.requestMutualAuth(true);
        context.requestInteg(true);
        context.requestConf(true);
        context.requestReplayDet(true);
        context.requestSequenceDet(true);
        context.requestCredDeleg(allowDelegation);
        return context;
    }

    // Chỉ gọi sau khi token exchange đã hoàn tất.
    public static void requireClientPolicy(GSSContext context)
            throws GSSException {
        if (!context.isEstablished()) {
            throw new SecurityException("GSS context not established");
        }
        if (!context.getMutualAuthState()) {
            throw new SecurityException("Mutual authentication unavailable");
        }
        // Provider phải báo được cơ chế Kerberos cuối cùng; nếu không, từ chối.
        if (!KERBEROS.equals(context.getMech())) {
            throw new SecurityException("Selected GSS mechanism is not Kerberos");
        }
    }

    public static void main(String[] args) {
        System.out.println("SPNEGO: " + SPNEGO);
        System.out.println("Kerberos: " + KERBEROS);
    }
}
```

Biên dịch và chạy (JDK 17+, không cần KDC vì `main` chỉ in OID):

```bash
javac SpnegoContextSetup.java
java SpnegoContextSetup
```

Stdout chính xác:

```text
SPNEGO: 1.3.6.1.5.5.2
Kerberos: 1.2.840.113554.1.2.2
```

Đối với hệ thống Kerberos thật, hàm `createClient` được gọi trong một identity/`Subject` đã có credential phù hợp hoặc cơ chế lấy credential của provider đã cấu hình. `null` ở tham số credential nghĩa là để provider dùng credential mặc định phù hợp, **không** tự động tạo danh tính mới. Tên `HTTP@host` phải trỏ đúng SPN của server, không lấy host từ input không tin cậy. Sử dụng `requestCredDeleg(false)` trừ khi có yêu cầu delegation cụ thể.

### Exchange token: hiểu đúng state machine

**Đoạn dưới đây là mã minh họa nằm trong phương thức xử lý kênh I/O do bạn tự viết**, không phải chương trình độc lập; `sendToken` và `receiveToken` là hai hàm của giao thức vận chuyển.

```java
// Initiator (phần thân phương thức; context đã được tạo):
byte[] incoming = new byte[0];
while (!context.isEstablished()) {
    byte[] outgoing = context.initSecContext(
            incoming, 0, incoming.length);
    if (outgoing != null) {
        sendToken(outgoing);             // Có thể vẫn phải gửi token cuối.
    }
    if (!context.isEstablished()) {
        incoming = receiveToken();       // Token trả về từ đúng acceptor.
    }
}
requireClientPolicy(context);
// Cuối phiên: context.dispose() trong finally.
```

Ở acceptor, tạo credential `ACCEPT_ONLY` phù hợp với principal/keytab (hoặc credential mặc định theo provider), dùng `manager.createContext(acceptorCredential)`, liên tục gọi `acceptSecContext(incoming, 0, incoming.length)`, trả token đầu ra nếu có, đến khi `isEstablished()`. Sau đó xác minh `getSrcName()`, `getMech()` và chính sách ứng dụng. Không trộn token giữa request, connection, user hoặc context.

Lưu ý: token GSS là **opaque**; đừng phân tích ASN.1 hay Base64 để tự suy ra authentication success hoặc principal. Định dạng truyền token (framing, thứ tự, timeout, kích thước tối đa) do giao thức bên ngoài chịu trách nhiệm. Trong HTTP Negotiate, library HTTP thường điều khiển vòng 401/200 và Base64; trong socket tùy chỉnh, developer phải thiết kế framing an toàn.

### Acceptor đọc delegated credential

**Fragment minh họa sau chỉ được gọi sau khi `acceptSecContext` hoàn tất thành công**, trên context phía acceptor và sau khi server đã quyết định yêu cầu này có được phép dùng delegation hay không:

```java
if (!acceptorContext.isEstablished()) {
    throw new SecurityException("Incomplete client authentication");
}
GSSName authenticatedUser = acceptorContext.getSrcName();
if (!isAuthorized(authenticatedUser)) { // Hàm policy của ứng dụng.
    throw new SecurityException("User is not authorized");
}

if (acceptorContext.getCredDelegState()) {
    GSSCredential delegated = acceptorContext.getDelegCred();
    if (delegated != null) {
        try {
            GSSManager manager = GSSManager.getInstance();
            GSSName backend = manager.createName(
                    "ldap@directory.internal.example",
                    GSSName.NT_HOSTBASED_SERVICE);
            GSSContext downstream = manager.createContext(
                    backend, new Oid("1.2.840.113554.1.2.2"),
                    delegated, GSSContext.DEFAULT_LIFETIME);
            try {
                downstream.requestMutualAuth(true);
                downstream.requestCredDeleg(false); // Không tự động chuyển tiếp.
                // Thực hiện exchange token với backend theo protocol thực tế.
                // Chỉ truy cập backend sau khi downstream.isEstablished().
            } finally {
                downstream.dispose();
            }
        } finally {
            delegated.dispose();
        }
    }
}
```

`isAuthorized` và token exchange tới backend là thành phần **phải được ứng dụng triển khai**, không có trong JDK. `delegated.dispose()` chỉ nên gọi khi application sở hữu vòng đời credential và không còn context nào cần nó. Trong hệ thống thật, thêm kiểm tra principal đích, policy delegation, account mapping, timeout và exception handling. Không coi `getCredDelegState()==true` là authorization của nghiệp vụ.

### Request flag khác negotiated flag

| Lời gọi phía initiator, **trước** `initSecContext` | Đọc kết quả **sau** `isEstablished` |
| --- | --- |
| `requestMutualAuth(true)` | `getMutualAuthState()` |
| `requestCredDeleg(true/false)` | `getCredDelegState()` |
| `requestInteg(true)` | `getIntegState()` |
| `requestConf(true)` | `getConfState()` |
| `requestReplayDet(true)` | `getReplayDetState()` |
| `requestSequenceDet(true)` | `getSequenceDetState()` |

Flag được **yêu cầu** không phải bằng chứng cơ chế đã đáp ứng. Nếu policy cần thuộc tính nào thì kiểm tra trạng thái đã thương lượng và fail closed khi thiếu. `getMech()` có thể thay đổi trong lúc thương lượng; kiểm tra sau khi context hoàn tất và xác nhận behavior của provider. `getCredDelegState()` chỉ có câu trả lời dứt khoát sau khi established; `getDelegCred()` được dùng ở acceptor, có thể trả `null`.

`requestConf(true)` chỉ yêu cầu khả năng confidentiality cho **GSS `wrap()`**; nó **không mã hóa HTTP body** chỉ vì đã gọi flag đó. Nếu ứng dụng dùng `wrap(..., new MessageProp(0, true))` để bảo vệ bản tin riêng, phải xác nhận context có confidentiality, bên nhận `unwrap()`, và giao thức truyền đúng token. `getMIC()/verifyMIC()` cung cấp integrity, không cung cấp secrecy. Trong HTTP, HTTPS/TLS vẫn cần được cấu hình đúng.

## 5. SASL GSSAPI và SPNEGO: không nhập làm một

Một ứng dụng có thể gặp cả hai API:

- **JGSS trực tiếp hoặc HTTP Negotiate:** chọn OID SPNEGO và trao token cho peer để lập `GSSContext`; cơ chế thực có thể là Kerberos tùy provider/policy.
- **SASL `GSSAPI` (RFC 4752):** cơ chế SASL **cố định Kerberos V5 GSS-API** và thương lượng tầng bảo vệ dữ liệu sau authentication. Các giao thức như LDAP quy định cách đóng gói/trao challenge-response; `SaslClient`/`SaslServer` chỉ xử lý logic SASL.
- **GS2 family (RFC 5801):** bridge GSS-API sang SASL khác với SASL `GSSAPI` kiểu RFC 4752. Ví dụ `GS2-KRB5` và `GS2-KRB5-PLUS`; biến thể PLUS dùng channel binding. Không giả định mọi SASL provider/giao thức đều hỗ trợ GS2.

Trong Java (`javax.security.sasl`), `Sasl.QOP` có các giá trị:

| QOP | Bảo vệ do SASL security layer |
| --- | --- |
| `auth` | Xác thực; **không** thêm tầng bảo vệ dữ liệu SASL |
| `auth-int` | Xác thực + toàn vẹn cho message được `wrap()/unwrap()` |
| `auth-conf` | Xác thực + toàn vẹn + bí mật cho message được `wrap()/unwrap()` |

Nếu không cấu hình `Sasl.QOP`, giá trị mặc định theo Javadoc Java là `auth`. Đặt danh sách ưu tiên không ép server chấp nhận lựa chọn cao nhất; phải đọc **`getNegotiatedProperty(Sasl.QOP)` sau khi `isComplete()`** và từ chối khi kết quả thấp hơn yêu cầu. Với `auth-int`/`auth-conf`, ứng dụng/giao thức phải dùng `SaslClient.wrap()/unwrap()` hoặc `SaslServer.wrap()/unwrap()` cho dữ liệu tiếp theo; chỉ thương lượng xong rồi gửi plaintext là sai ranh giới bảo vệ.

Fragment minh họa (nằm trong phương thức có xử lý `SaslException` và vòng challenge/response của giao thức):

```java
Map<String, String> properties = Map.of(
        Sasl.QOP, "auth-conf,auth-int,auth");

SaslClient client = Sasl.createSaslClient(
        new String[] { "GSSAPI" },
        null,             // authorizationId: không yêu cầu giả danh ai.
        "ldap",           // protocol theo SASL profile.
        "directory.example.com",
        properties,
        null);            // CallbackHandler tùy cấu hình provider.

if (client == null) {
    throw new SaslException("No GSSAPI SASL provider");
}

// Chuyển challenge/response đến khi client.isComplete() theo protocol LDAP.
if (!client.isComplete()) {
    throw new SaslException("SASL exchange incomplete");
}
String negotiatedQop = (String) client.getNegotiatedProperty(Sasl.QOP);
if (!"auth-conf".equals(negotiatedQop)) {
    throw new SaslException("Required SASL confidentiality unavailable");
}
// Tiếp theo: truyền dữ liệu qua client.wrap()/unwrap() theo protocol.
// Cuối phiên: client.dispose().
```

Fragment cần import `java.util.Map`, `javax.security.sasl.Sasl`, `SaslClient` và `SaslException`. Ở luồng thực, bạn phải **thực hiện** exchange qua LDAP hoặc protocol liên quan trước khi kiểm tra `isComplete()`; snippet không tự tiến hành authentication.

SASL authorization identity khác với credential delegation: máy chủ SASL phải tự xét client đã xác thực có được hành động dưới authzid yêu cầu không. Không tự động tạo `GSSCredential` chuyển tiếp khi chỉ sử dụng `Sasl.createSaslClient("GSSAPI")`.

## 6. Những ranh giới bảo vệ dễ bị hiểu nhầm

### 6.1. Xác thực đối tác không bằng mã hóa toàn bộ kết nối

Kerberos GSS có thể xác thực và tạo khóa cho context; `wrap`/`getMIC` chỉ bảo vệ **những bản tin ứng dụng chủ động đưa qua API tương ứng**. Một request HTTP chứa token SPNEGO nhưng truyền body không qua `wrap` vẫn cần TLS. TLS bảo vệ đường truyền giữa **hai TLS endpoints**, không tự bảo vệ dữ liệu sau khi proxy giải mã hoặc khi lưu vào log/DB.

### 6.2. SPNEGO negotiation protection không là chống downgrade toàn hệ thống

`mechListMIC` của RFC 4178 có điều kiện theo integrity của underlying mechanism và tình huống thương lượng. Nó không thay policy “chỉ cho Kerberos”, không bảo vệ việc server ứng dụng quảng cáo các scheme HTTP khác, và không tự bảo vệ HTTP redirect hoặc DNS. Khi Kerberos bắt buộc: chỉ chấp nhận cơ chế thực phù hợp, không retry im lặng sang NTLM/Basic, và xác minh service principal đích.

### 6.3. Mutual authentication khác với “đã có TLS”

Kerberos mutual auth (nếu được negotiated) chứng minh acceptor có thông tin phù hợp để kết thúc cơ chế Kerberos. TLS server authentication kiểm tra certificate của TLS endpoint. Hai thuộc tính gắn với **hai lớp/đối tượng** khác nhau, có thể trỏ tới hai chủ thể khác nhau khi có reverse proxy. Nếu yêu cầu ràng buộc xác thực ứng dụng vào chính TLS channel, cần channel binding được cả hai đầu hỗ trợ và cùng cấu hình; không mặc định JGSS hay HTTP client tự làm việc đó.

Java GSS cung cấp `GSSContext.setChannelBinding(ChannelBinding)` trước handshake; dữ liệu binding phải được lấy từ kênh đã xác thực và thống nhất ở hai phía. Với các tiêu chuẩn SASL hiện đại, RFC 9266 xác định `tls-exporter` cho TLS 1.3; RFC 5929 mô tả các loại binding trước đó. Chọn đúng loại và dữ liệu theo **protocol/provider thực tế**, không tự chế chuỗi chứng chỉ hoặc gắn cờ “channel bound” khi chưa được peer xác nhận.

### 6.4. Endpoint/identity scope

Ticket/service name phải khớp service đích. Credential của user cho `HTTP/front.example.com` không có nghĩa backend `ldap/directory.example.com` đã xác thực user. Khi proxy nhận Negotiate, backend chỉ thấy hop do proxy tạo; nếu backend cần danh tính user, phải có delegation đã được policy cho phép hoặc một giao thức ủy quyền/identity propagation được bảo vệ và xác minh riêng. Header `X-User` do bên ngoài tự gửi không đáng tin.

### 6.5. Replay, lifetime và token handling

Kerberos và GSS context có cơ chế phát hiện replay/sequence tùy cấu hình, nhưng không thay chống replay ở nghiệp vụ (ví dụ chuyển tiền hai lần), idempotency key, authorization từng request hoặc thời hạn session. Token có thể lộ cấu trúc/metadata và phải coi là dữ liệu nhạy cảm; không đưa `Authorization: Negotiate`, vé Kerberos, keytab, dump credential hoặc SASL challenge vào log. Giới hạn kích thước token, số vòng handshake, timeout và số context đồng thời để tránh DoS.

## 7. Ma trận quyết định theo nhu cầu

| Yêu cầu | Cơ chế/cấu hình cần thiết | Kiểm tra bắt buộc |
| --- | --- | --- |
| User đăng nhập SSO vào web nội bộ | HTTPS + HTTP Negotiate/SPNEGO với Kerberos được cho phép | Context hoàn tất, principal, SPN và authorization |
| Giữ bí mật HTTP headers/body | TLS đến các endpoint/hop cần bảo vệ | Certificate, hostname, TLS policy, nơi kết thúc TLS |
| Bảo vệ message của GSS socket tùy chỉnh | `GSSContext.wrap/unwrap` hoặc MIC thích hợp | `getIntegState/getConfState`, tính đúng framing và token |
| LDAP dùng SASL GSSAPI | SASL challenge/response với Kerberos | `isComplete`, `authzid`, QOP đã thương lượng; TLS nếu cần |
| Backend hành động thay user | Credential delegation hoặc giải pháp delegation được kiểm soát | Sự đồng ý/policy, `getCredDelegState`, identity, scope và audit |
| Chống MITM giữa GSS/SASL với TLS | Channel binding được giao thức/provider hỗ trợ | Hai phía bind cùng TLS channel, thất bại phải dừng |
| Chỉ cho phép Kerberos, tránh fallback | Allow-list GSS mechanism và HTTP authentication policy | Cơ chế cuối, không downgrade sang NTLM/Basic |

**Ví dụ lựa chọn:** Công ty có web portal dùng Negotiate. Người dùng Alice xem thông tin của mình từ database. Nếu portal chỉ đọc dữ liệu bằng service account với **authorization của portal theo Alice**, không nhất thiết cần Kerberos delegation. Nếu database bắt buộc xác thực từng user bằng Kerberos, mới xem xét chuyển giao credential/ủy quyền ràng buộc service đích. Hai mô hình đều cần policy ở database hoặc portal; việc delegation làm gia tăng phạm vi quyền nếu sai cấu hình.

## 8. Triển khai, xử lý lỗi và kiểm thử

### Checklist triển khai Java + Kerberos/SPNEGO

1. **Danh tính:** xác định user principal, FQDN và service principal thực (`HTTP/...`, `ldap/...`), realm và quan hệ trust. Bảo đảm DNS/canonicalization không khiến client tạo ticket cho host khác mong muốn.
2. **Credential store:** bố trí JAAS/Kerberos login, ticket cache, keytab và quyền đọc file cho đúng process. Chỉ bật debug khi điều tra, xóa log trước khi chia sẻ.
3. **Negotiate:** quyết định cơ chế được phép. Tạo context đúng OID, thiết lập yêu cầu mutual auth, integrity, delegation trước lần `initSecContext` đầu tiên. Không coi một HTTP 401 là lỗi cuối cùng; xử lý mọi token phản hồi.
4. **Policy sau handshake:** xác minh context established, negotiated mechanism, expected acceptor/service và authenticated user; kiểm tra quyền tài nguyên riêng.
5. **Bảo vệ dữ liệu:** xác định chính xác hop TLS, việc dùng GSS/SASL `wrap`, channel binding, proxy và log. Với dữ liệu nhạy cảm, kiểm tra confidentiality tại lớp **thực sự chuyển dữ liệu**.
6. **Delegation:** khai báo luồng nào cần, người nào được, service nào được nhận, lifetime nào; test “không được delegation”. Không tự động yêu cầu lại hoặc nâng quyền khi `getDelegCred()` bằng `null`.
7. **Vòng đời:** mỗi context gắn đúng phiên/identity; bảo vệ chống concurrency/race, đặt timeout và giới hạn token; dispose context/credential khi xong. Không dùng chung mutable `GSSContext` giữa các request độc lập.

### Tình huống lỗi và hướng chẩn đoán

| Dấu hiệu | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| `GSSException: No valid credentials` | Chưa login Kerberos, credential cache không đúng process/`Subject`, ticket hết hạn | Kiểm tra credential source và principal; không đưa password vào code |
| `KRB_AP_ERR_MODIFIED`/service ticket không chấp nhận | SPN trỏ nhầm service, keytab/kvno/key không khớp, duplicate SPN | So lại target FQDN, SPN, keytab và KDC |
| `Clock skew too great` | Client/server/KDC lệch giờ | Đồng bộ thời gian theo chính sách hệ thống |
| HTTP lặp 401 Negotiate | Không hoàn tất token exchange, server không có acceptor cred, proxy bỏ header, sai SPN | Trace trạng thái/hop ở mức an toàn; không log raw token |
| Auth thành công nhưng backend từ chối | Chưa delegation, backend kiểm tra role riêng, principal đích sai | Kiểm tra `getCredDelegState`, backend identity/authorization |
| Có `auth` nhưng cần confidentiality | SASL QOP đã thương lượng thấp hơn yêu cầu | Fail closed hoặc dùng kênh TLS được chấp nhận theo policy |
| Channel binding mismatch | Hai phía lấy binding từ TLS connection khác nhau, hoặc loại binding không tương thích | Kiểm tra TLS termination và hỗ trợ provider/protocol |

Lệnh vận hành như `klist`, `kinit` hoặc `setspn` tùy hệ điều hành và môi trường có thể giúp kiểm tra ticket/SPN; kết quả phải xử lý như thông tin bảo mật. Không suy ra cơ chế, quyền hay tính bảo mật từ việc một command trả exit code 0.

### Bộ tình huống QA tối thiểu

- **Đường tốt:** client/server Kerberos đúng SPN; context hoàn tất; user được authorization đúng tài nguyên.
- **Không có common mechanism:** từ chối; không fallback sang cơ chế bị cấm.
- **Sai SPN/keytab/realm hoặc token bị sửa:** không cấp quyền; không tạo session ứng dụng.
- **Không bật delegation:** acceptor không nhận delegated credential; backend được xử lý theo phương án không delegation.
- **Có yêu cầu delegation nhưng policy/ticket không cho phép:** không tự nâng quyền hoặc chia sẻ tài khoản service toàn quyền.
- **Delegation được phép:** chỉ gọi backend đã cho phép; principal và audit khớp; credential không còn được dùng sau kết thúc phiên.
- **SASL QOP thấp:** ứng dụng cần `auth-conf` phải từ chối `auth`/`auth-int`; kiểm tra rằng dữ liệu hậu xác thực thực sự đi qua bảo vệ đã chọn.
- **Proxy/TLS:** thử kết thúc TLS tại gateway, đổi channel binding, mất header ở hop sau và HTTP không TLS; xác nhận policy phát hiện sai phạm và bảo vệ đúng phạm vi.
- **Replay/concurrency:** gửi lại yêu cầu nghiệp vụ và token không hợp lệ, thử quá số vòng/token size; hệ thống không làm lộ credential, không nhầm lẫn danh tính giữa phiên.

## 9. Những kết luận cần nhớ

1. **SPNEGO chọn cơ chế GSS**; chất lượng authentication, integrity, confidentiality và delegation phụ thuộc cơ chế được chọn và policy đã được thực thi.
2. **Delegation khác authorization**: delegated `GSSCredential` có thể cho phép hop B xác thực tới hop C dưới danh tính người dùng, nhưng cả B và C vẫn phải giới hạn quyền. `requestCredDeleg(true)` là yêu cầu, không phải chứng nhận đã cấp.
3. **Mỗi lớp bảo vệ một phạm vi riêng:** HTTP Negotiate chở token; Kerberos xác thực và có khả năng bảo vệ message GSS; SASL GSSAPI có QOP cho dữ liệu đi qua security layer; TLS bảo vệ các TLS hop; ứng dụng tự quyết định quyền truy cập.
4. **Kiểm tra sau khi thương lượng, fail closed:** `isEstablished()`/`isComplete()`, cơ chế/QOP/flag thật, principal, TLS/channel binding và application authorization. Không thay bằng giả định “SSO thành công nên an toàn”.

## Tài liệu chuẩn để đọc sâu

- [RFC 4178 — SPNEGO](https://www.rfc-editor.org/rfc/rfc4178): danh sách cơ chế, token và `mechListMIC`.
- [RFC 4559 — HTTP Negotiate](https://www.rfc-editor.org/rfc/rfc4559): quy trình 401/Authorization và ranh giới bảo vệ HTTP.
- [RFC 4121 — Kerberos V5 GSS mechanism](https://www.rfc-editor.org/rfc/rfc4121): MIC, Wrap và bảo vệ theo message.
- [RFC 4752 — SASL GSSAPI (Kerberos V5)](https://www.rfc-editor.org/rfc/rfc4752): SASL GSSAPI và security layer.
- [RFC 5801 — SASL GS2 family](https://www.rfc-editor.org/rfc/rfc5801) và [RFC 9266 — TLS 1.3 channel binding](https://www.rfc-editor.org/rfc/rfc9266): biến thể channel binding.
- [Java 17 `GSSContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/GSSContext.html), [`GSSManager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/GSSManager.html), [`Sasl`](https://docs.oracle.com/en/java/javase/17/docs/api/java.security.sasl/javax/security/sasl/Sasl.html): API và trạng thái negotiated.
