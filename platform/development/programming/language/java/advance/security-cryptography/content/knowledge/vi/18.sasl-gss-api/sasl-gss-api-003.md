# 18.3. Thương lượng SASL mechanism, authentication identity và authorization identity

> Phạm vi: SASL (Simple Authentication and Security Layer) trong hệ thống Java, với bối cảnh GSS-API/Kerberos; tập trung vào việc chọn cơ chế xác thực và phân biệt người đã chứng minh danh tính với danh tính mà phiên được phép đại diện.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao máy khách và máy chủ phải thống nhất một SASL mechanism trước khi trao đổi challenge/response, và ai chịu trách nhiệm lựa chọn cơ chế.
2. Phân biệt **authentication identity** (`authcid` hoặc `authnId`) và **authorization identity** (`authzid`), kể cả khi hai chuỗi giống nhau.
3. Mô tả quy tắc mặc định khi `authzid` bị bỏ trống và điều kiện để thực hiện proxy/delegated authorization.
4. Nhận ra ranh giới giữa việc xác thực bằng một mechanism (ví dụ `GSSAPI`) và việc áp dụng chính sách phân quyền.
5. Dùng đúng các điểm tích hợp `SaslClient`, `SaslServer`, `CallbackHandler` và `AuthorizeCallback` trong Java; tránh downgrade và giả mạo `authzid`.

## 2. Ba lớp khái niệm thường bị gộp nhầm

**SASL là một framework**, không phải một thuật toán mật mã đơn lẻ. Nó đưa cơ chế xác thực vào một giao thức ứng dụng như IMAP, SMTP, LDAP hoặc một giao thức riêng. Giao thức ứng dụng quy định cách công bố danh sách cơ chế, cách đóng gói thông điệp, thông báo thành công/thất bại và hành vi phiên sau xác thực.

**Mechanism** là cách hai phía chứng minh danh tính và có thể thương lượng dịch vụ bảo vệ phiên, chẳng hạn `PLAIN`, `SCRAM-SHA-256`, `GSSAPI` hoặc `EXTERNAL`. Không phải mọi mechanism đều xuất hiện trong mọi giao thức hay mọi bản Java provider.

**Identity** gồm hai khái niệm khác nhau:

| Khái niệm | Câu hỏi mà nó trả lời | Nguồn gốc và cách dùng |
| --- | --- | --- |
| Authentication identity (`authcid` / `authnId`) | **Ai đã chứng minh sở hữu thông tin xác thực?** | Server suy ra/xác minh từ password, ticket Kerberos, certificate, token… theo mechanism; không tin một username gửi lên khi chưa kiểm chứng. |
| Requested authorization identity (`authzid`) | **Client muốn hành động dưới danh tính nào?** | Client có thể đề nghị một danh tính khác; cú pháp và chuẩn hóa do giao thức ứng dụng quy định. |
| Effective authorization identity | **Sau khi kiểm tra, phiên thực sự được phép đại diện cho ai?** | Server quyết định sau khi xác thực và kiểm tra quyền đại diện; dùng cho ngữ cảnh phiên và kiểm soát truy cập tiếp theo. |

Ví dụ: service account `svc-report` đăng nhập hợp lệ bằng Kerberos và đề nghị `authzid=reports-reader`. Server đã biết `authcid=svc-report`, nhưng chỉ được chấp nhận `reports-reader` nếu chính sách cho `svc-report` quyền đại diện cho danh tính đó. Nếu người dùng `alice` yêu cầu `authzid=admin` mà không có quyền, *bắt buộc từ chối cả trao đổi SASL*. Việc đã xác thực thành công `alice` không làm yêu cầu chuyển quyền hợp lệ.

**Quan trọng:** bước SASL kiểm tra quyền **đại diện cho một identity**; sau đó ứng dụng vẫn phải kiểm tra identity ấy được đọc, ghi, xóa tài nguyên nào (RBAC/ABAC/ACL). `authzid=admin` không tự tạo ra vai trò quản trị.

## 3. Thương lượng mechanism diễn ra ở đâu?

RFC 4422 nêu rằng **mechanism negotiation là phần riêng của giao thức ứng dụng**. Thông thường server quảng bá các mechanism đang bật; client giao tập này với khả năng của mình rồi chọn một mechanism thỏa chính sách bảo mật và điều kiện triển khai. Chính SASL không định nghĩa một gói tin chung kiểu “NEGOTIATE” cho mọi ứng dụng.

Một phiên điển hình:

```text
(0) Thiết lập kênh, kiểm chứng server/TLS nếu giao thức yêu cầu.
(1) S -> C: danh sách mechanism server chấp nhận (ví dụ: GSSAPI, SCRAM-SHA-256, PLAIN)
(2) C: lọc theo local policy + provider + credentials sẵn có.
(3) C -> S: yêu cầu AUTHENTICATE <mechanism đã chọn> [initial response nếu có]
(4) S: kiểm tra mechanism có được cho phép trên kết nối này.
(5) C <-> S: trao đổi response/challenge đặc thù của mechanism.
(6) S: xác minh credentials -> tìm authcid; xác định authzid được yêu cầu.
(7) S: kiểm tra authcid có được đại diện cho authzid không.
(8) S -> C: SUCCESS hoặc FAILURE; khi thành công mới có effective authzid.
(9) Ứng dụng dùng effective authzid để kiểm tra từng hành động tiếp theo.
```

### Ví dụ lựa chọn có chính sách

Giả sử server quảng bá `[PLAIN, GSSAPI, SCRAM-SHA-256]`, client hỗ trợ `[SCRAM-SHA-256, PLAIN]`, chính sách ứng dụng từ chối `PLAIN` và ưu tiên `SCRAM-SHA-256`; đồng thời có provider tương thích. Kết quả là `SCRAM-SHA-256`. Nếu client chỉ hỗ trợ `PLAIN` thì phải báo **không có mechanism phù hợp**, không âm thầm hạ yêu cầu bảo mật.

Đừng suy ra “mechanism mạnh nhất” chỉ từ thứ tự server công bố: lựa chọn còn phụ thuộc vào TLS đã xác thực, mức bảo vệ cần thiết, dạng credentials, server identity, hỗ trợ provider, chống downgrade và chính sách tổ chức.

**Nguy cơ downgrade:** danh sách mechanism ban đầu có thể nằm ngoài thông điệp đã được xác thực, nên kẻ tấn công trên đường truyền có thể tìm cách loại bỏ cơ chế mạnh để ép client chọn cơ chế yếu. Với giao thức hỗ trợ STARTTLS, thực hiện TLS theo yêu cầu, xác minh certificate/hostname, rồi hỏi lại capabilities theo đúng đặc tả giao thức; không gửi password/token trước khi kênh đã được bảo vệ đầy đủ. Tắt fallback ngoài chính sách. Nếu giao thức cho phép, kiểm chứng capabilities sau khi hình thành security layer có integrity để phát hiện thay đổi.

### Các bước kiểm tra trước khi chấp nhận lựa chọn

- **Phía client:** whitelist mechanism; local provider thực sự tạo được `SaslClient`; credentials/JAAS phù hợp; TLS và xác thực server đạt ngưỡng; không fallback tùy tiện khi cơ chế mạnh lỗi.
- **Phía server:** chỉ quảng bá/nhận mechanism đã cấu hình; áp dụng điều kiện theo kết nối (ví dụ chỉ cho `PLAIN` trên TLS hợp lệ); có `SaslServer` provider; áp dụng giới hạn kích thước, thời gian và số lần thử.
- **Cả hai:** nhất trí mechanism theo giao thức, xử lý thông điệp đúng thứ tự, không tiếp tục sử dụng phiên khi trao đổi thất bại.

## 4. Authentication identity và authorization identity trong trao đổi thực

### 4.1. Không đưa authzid: server tự suy ra

Client có thể **không gửi** authorization identity, hoặc gửi chuỗi rỗng khi mechanism/protocol cho phép. Theo mô hình SASL, điều này yêu cầu server xác định identity thích hợp từ credentials đã xác thực. Đó thường là cùng người dùng nhưng *không bắt buộc là cùng chuỗi ký tự*: ví dụ Kerberos principal `alice@EXAMPLE.COM` có thể được ánh xạ thành tài khoản ứng dụng `alice`.

### 4.2. Có authzid: yêu cầu đại diện, không phải mệnh lệnh

Khi gửi `authzid=bob`, client đang **đề nghị** server cho phép authcid của mình hành động với danh tính `bob`. Server phải kiểm tra quy tắc ủy quyền/proxy, không đơn giản gán session user bằng trường client cung cấp.

| Credentials đã xác thực thành | Authzid được yêu cầu | Chính sách ví dụ | Kết quả |
| --- | --- | --- | --- |
| `alice` | bỏ trống | Server map credentials thành `alice` | Phiên mang quyền `alice`. |
| `alice` | `alice` | Self-authorization được phép | Phiên mang quyền `alice`. |
| `alice` | `admin` | Không có quyền đại diện | Từ chối trao đổi SASL. |
| `svc-report` | `reports-reader` | Có rule ủy quyền đúng cặp | Phiên mang quyền `reports-reader`. |
| `svc-report` | `root` | Không có rule | Từ chối, dù credentials hợp lệ. |

Quy tắc phân quyền cần làm việc với **định danh chuẩn hóa đáng tin cậy** (realm, tenant, case-sensitivity, principal mapping); chuẩn hóa nhất quán cả hai phía để tránh `Alice`/`alice`, tên rút gọn/full principal hoặc ký tự Unicode gây nhầm. Không loại bỏ realm/tenant theo thói quen.

### 4.3. Nhìn ở mức wire: mechanism PLAIN

RFC 4616 định nghĩa payload UTF-8 của `PLAIN` theo dạng:

```text
[authzid] <NUL> authcid <NUL> password
```

`<NUL>` là byte `0x00`, không phải dấu cách hoặc chuỗi sáu ký tự “<NUL>”. Khi không muốn đề nghị authzid riêng, trường đầu tiên **rỗng**. Trong `PLAIN`, cả username/password được đưa vào thông điệp SASL; mechanism **không cung cấp bí mật hoặc toàn vẹn** cho thông điệp, vì vậy phải có bảo vệ kênh như TLS đã xác minh trước. Không log/trace payload, không tự mã hóa Base64 rồi coi như đã được bảo mật: Base64 chỉ là biểu diễn dữ liệu.

### 4.4. Với GSSAPI/Kerberos

Trong SASL mechanism `GSSAPI`, GSS-API xác lập security context dựa trên credentials Kerberos; thông tin này giúp server biết principal đã được xác thực. Service principal của đích thường có dạng `imap/mail.example.com@EXAMPLE.COM` (minh họa; chính xác phải khớp môi trường). Application vẫn phải quyết định cách ánh xạ principal đó thành authcid nội bộ, xử lý authzid rỗng/được yêu cầu và từ chối ủy quyền trái phép. Ticket hợp lệ **không** đồng nghĩa được phép làm người dùng tùy ý.

Phân biệt:

- `GSS-API` là API dùng để xác lập context bảo mật trừu tượng; Kerberos là một công nghệ thường đứng bên dưới.
- `GSSAPI` là tên một SASL mechanism sử dụng dịch vụ GSS-API; nó hoạt động trong vòng đời `SaslClient` / `SaslServer`.
- `javax.security.sasl.AuthorizeCallback` hỏi chính sách có cho authcid hành động như authzid không. Nó không thay việc kiểm chứng Kerberos ticket.

## 5. Một số mechanism để đặt lựa chọn vào đúng bối cảnh

| Mechanism | Dữ liệu dùng để xác thực | Lưu ý khi lựa chọn và xác định identity |
| --- | --- | --- |
| `GSSAPI` | Context GSS-API, thường là Kerberos ticket | Cần cấu hình realm, principal/service name, ticket/JAAS; hỗ trợ xác thực hai chiều và lớp bảo vệ tùy thương lượng. Bắt buộc kiểm tra mapping và quyền đại diện. |
| `SCRAM-SHA-256` / `SCRAM-SHA-256-PLUS` | Challenge/response dựa trên password và salt, không truyền password trần | `-PLUS` có channel binding; vẫn cần TLS và cấu hình đúng. Provider Java chuẩn không được mặc định coi là hỗ trợ mechanism này. |
| `PLAIN` | Authcid + password, có thể kèm authzid | Chỉ cho phép trong kênh được bảo vệ phù hợp; mechanism tự nó không bảo vệ password. |
| `EXTERNAL` | Danh tính được chứng minh ở lớp ngoài (ví dụ TLS client certificate) | Server phải tin cậy, xác minh và ánh xạ danh tính của lớp ngoài; authzid được đề nghị vẫn cần kiểm tra. |

Không đưa `CRAM-MD5`, `DIGEST-MD5` hoặc thuật toán cũ vào giải pháp mới chỉ vì provider hỗ trợ. Tên mechanism được đăng ký theo đặc tả, còn việc mechanism nào có trên **runtime hiện tại** do provider, phiên bản và cấu hình quyết định.

## 6. Ví dụ Java 17+ chạy độc lập: chọn mechanism và chặn giả mạo authzid

Ví dụ sau có hai phần: chọn mechanism từ tập đã được chính sách cho phép và mô phỏng **bước kiểm tra authorization sau khi authcid đã được xác thực** bằng `AuthorizeCallback`. Nó không thực hiện password/Kerberos handshake; không được dùng các chuỗi `authn` tự nhập từ request thực tế để thay cho kết quả xác thực.

Lưu tệp `SaslIdentityDemo.java`:

```java
import java.io.IOException;
import java.util.List;
import java.util.Set;
import javax.security.auth.callback.Callback;
import javax.security.auth.callback.CallbackHandler;
import javax.security.auth.callback.UnsupportedCallbackException;
import javax.security.sasl.AuthorizeCallback;

public class SaslIdentityDemo {
    static String choose(List<String> advertised,
                         List<String> preferred,
                         Set<String> allowed) {
        for (String mech : preferred) {
            if (allowed.contains(mech) && advertised.contains(mech)) {
                return mech;
            }
        }
        throw new IllegalStateException("No allowed common SASL mechanism");
    }

    // Quy tắc ví dụ: tự đại diện; riêng svc-report được đại diện reports-reader.
    static boolean mayAssume(String authn, String authz) {
        return authn.equals(authz)
                || (authn.equals("svc-report") && authz.equals("reports-reader"));
    }

    static boolean check(String authn, String authz)
            throws IOException, UnsupportedCallbackException {
        CallbackHandler handler = callbacks -> {
            for (Callback callback : callbacks) {
                if (callback instanceof AuthorizeCallback request) {
                    boolean grant = mayAssume(
                            request.getAuthenticationID(),
                            request.getAuthorizationID());
                    request.setAuthorized(grant);
                    if (grant) {
                        request.setAuthorizedID(request.getAuthorizationID());
                    }
                } else {
                    throw new UnsupportedCallbackException(callback);
                }
            }
        };

        AuthorizeCallback request = new AuthorizeCallback(authn, authz);
        handler.handle(new Callback[] {request});
        return request.isAuthorized();
    }

    public static void main(String[] args) throws Exception {
        List<String> advertised = List.of("PLAIN", "GSSAPI", "SCRAM-SHA-256");
        List<String> preferred = List.of("SCRAM-SHA-256", "GSSAPI", "PLAIN");
        Set<String> allowed = Set.of("SCRAM-SHA-256", "GSSAPI");

        System.out.println("mechanism=" + choose(advertised, preferred, allowed));
        System.out.println("alice -> alice: " + check("alice", "alice"));
        System.out.println("alice -> admin: " + check("alice", "admin"));
        System.out.println("svc-report -> reports-reader: "
                + check("svc-report", "reports-reader"));
    }
}
```

Chạy với JDK 17+:

```bash
javac --release 17 SaslIdentityDemo.java
java SaslIdentityDemo
```

Stdout:

```text
mechanism=SCRAM-SHA-256
alice -> alice: true
alice -> admin: false
svc-report -> reports-reader: true
```

Điều ví dụ chứng minh:

- Server quảng bá `PLAIN` không có nghĩa client bắt buộc dùng nó: chính sách loại bỏ `PLAIN`.
- `alice` đã xác thực vẫn không được lấy session identity `admin`.
- Cho phép proxy phải dựa trên một **quy tắc cụ thể**, ở đây chỉ cặp `svc-report -> reports-reader`; deny by default.
- Trong ứng dụng thật, principal đầu vào `AuthorizeCallback` phải đến từ mechanism đã xác minh credentials. Code mô phỏng không thay thế xác thực hoặc một hệ thống phân quyền sản xuất.

## 7. Ánh xạ sang Java SASL API thật

Java SE cung cấp package `javax.security.sasl` và các factory dựa trên Security Provider Framework. Sau khi protocol/client đã chọn mechanism hợp lệ, client tạo implementation:

```java
// Đoạn khung: các biến mechanism, requestedAuthzid và clientCallbacks
// đến từ negotiation, chính sách và cấu hình credential thực của ứng dụng.
SaslClient client = Sasl.createSaslClient(
        new String[] {mechanism}, requestedAuthzid,
        "imap", "mail.example.com",
        Map.of(Sasl.QOP, "auth"),
        clientCallbacks);
if (client == null) {
    throw new SaslException("No eligible SASL client provider: " + mechanism);
}
```

Các import cần cho đoạn khung là `javax.security.sasl.Sasl`, `SaslClient`, `SaslException` và `java.util.Map`. Đây **không phải chương trình độc lập**: cần transport, cơ chế discovery, credentials/JAAS và `CallbackHandler` thực tế. Argument `requestedAuthzid` có thể `null` để server suy ra danh tính. Với các provider khác nhau, cùng một tên mechanism có thể được hỗ trợ hoặc không.

Ở server, sau khi đã kiểm tra client chọn mechanism được bật trên kết nối này:

```java
// Đoạn khung; serverCallbacks phải đáp ứng callbacks của mechanism
// và thực hiện chính sách AuthorizeCallback trên identity đáng tin.
SaslServer server = Sasl.createSaslServer(
        mechanism, "imap", "mail.example.com", serverProperties,
        serverCallbacks);
if (server == null) {
    throw new SaslException("No eligible SASL server provider: " + mechanism);
}

// Với mỗi response nhận được theo framing của protocol:
// byte[] response = server.evaluateResponse(clientResponseBytes);
// Gửi challenge tiếp nếu chưa complete; xử lý ngoại lệ như thất bại.
if (server.isComplete()) {
    String sessionIdentity = server.getAuthorizationID();
    // Chỉ lúc này mới gắn sessionIdentity vào principal của phiên.
}
```

Đoạn khung server cần import `javax.security.sasl.Sasl`, `SaslServer`, `SaslException`. Lệnh `evaluateResponse(...)` (được chú thích) phải thực sự được gọi cho từng thông điệp theo giao thức; kiểm tra `isComplete()` chỉ có ý nghĩa sau vòng trao đổi. Client tương ứng dùng `hasInitialResponse()`, `evaluateChallenge(...)` và `isComplete()`. Luôn gọi `dispose()` cho client/server khi kết thúc để giải phóng tài nguyên. Không tự sáng tác challenge, response hoặc message framing: giao thức ứng dụng định nghĩa phần vận chuyển, implementation mechanism tạo/xử lý token.

### AuthorizeCallback được dùng ở đâu?

Khi một server mechanism cần quyết định authnId có thể hành động như authzid hay không, nó có thể gọi `CallbackHandler.handle(...)` với `AuthorizeCallback`:

1. `getAuthenticationID()`: identity đã xác thực, do implementation mechanism cung cấp.
2. `getAuthorizationID()`: identity được yêu cầu/đã suy ra theo cơ chế và giao thức.
3. Server áp dụng policy: cùng identity, delegation đúng quyền/tenant, hoặc từ chối.
4. `setAuthorized(true/false)` và, nếu chấp nhận, `setAuthorizedID(canonicalId)` để trả về identity được cho phép.

Handler thực tế có thể còn gặp `NameCallback`, `PasswordCallback`, `RealmCallback` hoặc callback đặc thù của provider. Không nên giả định mọi mechanism sẽ dùng cùng một bộ callback: triển khai theo provider và credentials được sử dụng. Không cấp quyền trong code `PasswordCallback` dựa vào username; password verification và delegation policy là hai trách nhiệm khác nhau.

### SASL security layer và QOP

Property `Sasl.QOP` có thể thương lượng các giá trị (nếu mechanism hỗ trợ):

| QOP | Ý nghĩa | Ứng dụng phải làm gì? |
| --- | --- | --- |
| `auth` | Chỉ xác thực | Dùng TLS/transport bảo vệ theo chính sách; không có SASL integrity/confidentiality layer. |
| `auth-int` | Xác thực + integrity | Dùng `wrap/unwrap` cho dữ liệu qua lớp SASL nếu layer này đã được thương lượng. |
| `auth-conf` | Xác thực + integrity + confidentiality | Dùng `wrap/unwrap` và framing/buffer size theo protocol; cũng cần xác minh các điều kiện triển khai. |

Sau khi hoàn tất, kiểm tra `getNegotiatedProperty(Sasl.QOP)` thay vì chỉ tin giá trị mong muốn lúc tạo client. Không gọi `wrap/unwrap` khi không có security layer thích hợp, và không tự thay transport protocol bằng cách gửi các byte bảo vệ mà peer không mong đợi. `PLAIN` không cung cấp lớp bảo vệ SASL; `SCRAM` thông thường dựa vào TLS để bảo vệ dữ liệu ứng dụng.

## 8. Tình huống GSSAPI/Kerberos hay gặp

Giả sử LDAP hoặc IMAP server xác thực Kerberos principal `svc-report@EXAMPLE.COM`. Client yêu cầu hoạt động dưới `reports-reader`:

1. Client xác định service name đúng với server, ví dụ `imap/mail.example.com@EXAMPLE.COM`, và dùng Kerberos credentials hợp lệ (ticket cache, JAAS hoặc cơ chế được provider hỗ trợ).
2. SASL `GSSAPI` xây dựng security context. Server kiểm chứng token, mục tiêu dịch vụ và principal; một số điều kiện như mutual authentication/QOP do cơ chế và cấu hình thương lượng.
3. Server ánh xạ `svc-report@EXAMPLE.COM` thành authcid nội bộ theo quy tắc của tổ chức. Không mặc nhiên bỏ realm hay tenant.
4. Server nhận requested authzid `reports-reader`, hỏi chính sách ủy quyền và chỉ cấp khi rule cho phép; nếu không, báo thất bại.
5. Sau khi thành công, quyền truy cập tài nguyên của `reports-reader` vẫn được ứng dụng kiểm tra trên từng thao tác.

Cấu hình Kerberos cần kiểm tra đồng bộ DNS/hostname, service principal name, keytab hoặc ticket, realm trust, clock skew và quyền đọc credential. Đăng nhập JAAS thành công hay `Subject` có principal không tự chứng minh rằng SASL server đã xác thực đúng peer hoặc đã chấp thuận một `authzid` cụ thể.

## 9. Failure modes, dấu hiệu và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Phản ứng an toàn |
| --- | --- | --- |
| Không có mechanism chung | Server/client/policy/provider không giao nhau | Báo lỗi; không tự bật cơ chế yếu để “cho chạy được”. |
| Client chọn `GSSAPI` nhưng `createSaslClient` trả `null` | Provider hoặc cấu hình không hỗ trợ | Kiểm tra factories/JAAS và cấu hình triển khai; không đoán cơ chế đã tồn tại. |
| Kerberos token thất bại | Ticket hết hạn, realm/SPN sai, hostname không khớp, clock skew | Chẩn đoán cấu hình/credentials; tránh lộ ticket và secret trong log. |
| Credentials đúng nhưng SASL thất bại | Requested `authzid` không được ủy quyền | Trả lỗi authorization; không thay bằng identity yêu cầu nếu chưa được cấp. |
| Đăng nhập được nhưng sai người dùng | Dùng raw authzid hoặc map principal không nhất quán | Chỉ dùng effective authorization ID sau khi server hoàn tất, kiểm tra canonical mapping. |
| `PLAIN` xuất hiện trước TLS | Capability công bố/điều kiện kết nối sai | Chỉ quảng bá/chấp nhận khi kênh có bảo vệ thích hợp; refresh capabilities sau TLS theo protocol. |
| Nhầm QOP với TLS | `auth` bị tưởng là đã mã hóa dữ liệu | Kiểm tra negotiated QOP và trạng thái TLS thực tế. |

### Checklist triển khai

- Xác định rõ cơ chế nào **được phép** ở từng môi trường; không dựa vào “cơ chế đầu tiên server gửi”.
- Bảo vệ bước discovery/negotiation theo giao thức; chống downgrade và xác thực peer/kênh trước khi gửi bí mật.
- Tách ba bước: **verify credential -> map authcid -> authorize requested authzid**. Bất kỳ bước nào lỗi đều thất bại.
- Định danh có realm/tenant được ánh xạ/chuẩn hóa có chủ đích; không cấp proxy bởi so sánh chuỗi tùy tiện.
- Chỉ tin `getAuthorizationID()` sau khi `SaslServer.isComplete()`; không lấy requested authzid từ request làm principal phiên.
- Quyền hoạt động trên resource vẫn do application authorization kiểm tra; ghi audit **cả authcid lẫn effective authzid** (không ghi credential, secret hoặc SASL token).
- Kiểm thử các trường hợp sai mật khẩu/ticket, authzid rỗng, authzid khác cùng quyền, authzid khác không quyền, không có mechanism chung, lỗi TLS/certificate, và client cố chọn mechanism bị cấm.

## 10. Câu hỏi tự kiểm tra và bài tập

1. Server quảng bá `GSSAPI, PLAIN`, client chỉ có `PLAIN` nhưng đang kết nối không TLS. Nên chọn gì? **Không chọn gì** nếu chính sách đòi kênh bảo vệ; dừng hoặc thiết lập TLS đúng giao thức trước.
2. Alice chứng minh credentials hợp lệ và gửi `authzid=admin`. Có thể trả SASL success rồi cho role `alice` không? Theo logic ở đây, **không**: yêu cầu identity trái phép làm trao đổi thất bại; không âm thầm thay nghĩa của requested identity.
3. Kerberos principal `alice@EXAMPLE.COM` và session identity `alice` khác chuỗi, có đồng nghĩa proxy authorization không? **Không nhất thiết**: đó có thể chỉ là mapping định danh mặc định; phải theo quy tắc server.
4. Chỉnh chương trình demo để thêm rule `svc-report -> audit-reader`, rồi kiểm tra `svc-report -> admin` vẫn `false`. Thử xóa `SCRAM-SHA-256` khỏi whitelist và quan sát cơ chế được chọn nếu client/server hỗ trợ `GSSAPI`.
5. Viết một bảng test gồm (`authcid`, `requested authzid`, kết quả ủy quyền) cho hai tenant khác nhau; chứng minh tài khoản thuộc tenant A không thể đại diện cho tài khoản trùng tên ở tenant B.

## Tài liệu đối chiếu

- RFC 4422 — *Simple Authentication and Security Layer (SASL)*: https://www.rfc-editor.org/rfc/rfc4422
- RFC 4616 — *The PLAIN SASL Mechanism*: https://www.rfc-editor.org/rfc/rfc4616
- RFC 5802 — *SCRAM SASL and GSS-API Mechanisms*: https://www.rfc-editor.org/rfc/rfc5802
- RFC 7677 — *SCRAM-SHA-256 and SCRAM-SHA-256-PLUS*: https://www.rfc-editor.org/rfc/rfc7677
- Java SE 17 `javax.security.sasl.Sasl`: https://docs.oracle.com/en/java/javase/17/docs/api/java.security.sasl/javax/security/sasl/Sasl.html
- Java SE 17 `javax.security.sasl.AuthorizeCallback`: https://docs.oracle.com/en/java/javase/17/docs/api/java.security.sasl/javax/security/sasl/AuthorizeCallback.html
